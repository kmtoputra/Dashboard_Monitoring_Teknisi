import datetime as dt
import json
import queue
import smtplib
import ssl
import threading
import urllib.parse
import urllib.request
from email.message import EmailMessage

from engine import LABEL, SATUAN, angka_id


class Notifier:
    def __init__(self, db, cfg, log=print):
        self.db = db
        self.cfg = cfg["notif"]
        self.ecfg = cfg["engine"]
        self.alamat = cfg["server"]["alamat"]
        self.zona = cfg["server"]["zona"]
        self.log = log
        self.antrean = queue.Queue()
        threading.Thread(target=self._pekerja, daemon=True, name="notifikasi").start()

    def kejadian(self, jenis, event_id):
        ev = self._event(event_id)
        if not ev:
            return
        if jenis == "pulih":
            sasaran = "terima_pulih"
        elif ev["level"] == "Kritis":
            sasaran = "terima_kritis"
        elif ev["level"] == "Offline":
            sasaran = "terima_offline"
        else:
            sasaran = "terima_peringatan"
        pesan = self.susun_pesan(ev, jenis)
        self._kirim_ke(ev, sasaran, jenis, pesan)
        if jenis in ("buka", "naik") and ev["level"] == "Kritis":
            self.db.jalankan("UPDATE event_alarm SET notif_terakhir = NOW() WHERE id = %s", (event_id,))

    def periodik(self, sekarang):
        ulang = self.ecfg["ulang_kritis_menit"]
        for ev in self.db.kueri(
                "SELECT id FROM event_alarm WHERE selesai IS NULL AND ack_waktu IS NULL AND level = 'Kritis' "
                "AND (notif_terakhir IS NULL OR notif_terakhir <= %s - INTERVAL %s MINUTE)", (sekarang, ulang)):
            e = self._event(ev["id"])
            self._kirim_ke(e, "terima_kritis", "ulang", self.susun_pesan(e, "ulang"))
            self.db.jalankan("UPDATE event_alarm SET notif_terakhir = %s WHERE id = %s", (sekarang, ev["id"]))
        esk = self.ecfg["eskalasi_menit"]
        for ev in self.db.kueri(
                "SELECT id FROM event_alarm WHERE selesai IS NULL AND ack_waktu IS NULL AND eskalasi_waktu IS NULL "
                "AND level IN ('Kritis','Offline') AND COALESCE(naik_kritis, mulai) <= %s - INTERVAL %s MINUTE",
                (sekarang, esk)):
            e = self._event(ev["id"])
            self._kirim_ke(e, None, "eskalasi", self.susun_pesan(e, "eskalasi"), hanya_supervisor=True)
            self.db.jalankan("UPDATE event_alarm SET eskalasi_waktu = %s WHERE id = %s", (sekarang, ev["id"]))

    def sistem(self, teks):
        pesan = {"subjek": "[SISTEM] Dashboard Monitoring DOCS", "teks": "[SISTEM] " + teks + " | " + self.alamat}
        for p in self._penerima("terima_offline", None, False):
            self._antre(None, "sistem", p, pesan, ditahan=None)
        self.log("SISTEM: " + teks)

    def uji(self, penerima_id):
        p = self.db.kueri("SELECT * FROM penerima_notifikasi WHERE id = %s", (penerima_id,), satu=True)
        if not p:
            return "penerima tidak ditemukan"
        pesan = {"subjek": "[UJI] Notifikasi Dashboard Monitoring DOCS",
                 "teks": "[UJI] Pesan uji dari Dashboard Monitoring DOCS. Kalau pesan ini sampai, channel {} "
                         "untuk {} sudah benar. | {}".format(p["channel"], p["nama"], self.alamat)}
        return self._kirim_satu(None, "uji", p, pesan, abaikan_aktif=True)

    def _event(self, eid):
        return self.db.kueri(
            "SELECT e.*, m.kode_unit, m.jenis_mesin, m.status AS status_mesin, l.kode AS kode_lokasi, "
            "l.nama_rs, l.kota, l.zona_waktu FROM event_alarm e JOIN mesin m ON m.id = e.mesin_id "
            "JOIN lokasi l ON l.id = m.lokasi_id WHERE e.id = %s", (eid,), satu=True)

    def susun_pesan(self, ev, jenis):
        nama = ev["nama_rs"] or ev["kode_lokasi"]
        if ev["kota"] and ev["kota"].lower() not in nama.lower():
            nama += " " + ev["kota"]
        unit = "{} – {}".format(nama, ev["jenis_mesin"])
        p = ev["parameter"]
        jam = lambda t: t.strftime("%H:%M") + " " + self.zona if t else "-"
        link = "{}/unit/{}".format(self.alamat, ev["mesin_id"])
        if p == "data":
            if jenis == "pulih":
                isi = "[PULIH] {} | Data masuk lagi pukul {}".format(unit, jam(ev["selesai"]))
            else:
                isi = "[{}] {} | {} | Cek koneksi router/VPN (cek_koneksi.ps1)".format(
                    "ESKALASI OFFLINE" if jenis == "eskalasi" else "OFFLINE", unit, ev["keterangan"] or "")
        else:
            nama = LABEL.get(p, p)
            sat = SATUAN.get(p, "")
            nilai = ev["nilai_terakhir"] if ev["nilai_terakhir"] is not None else ev["nilai_awal"]
            if jenis == "pulih":
                durasi = int((ev["selesai"] - ev["mulai"]).total_seconds() // 60) if ev["selesai"] else 0
                isi = "[PULIH] {} | {} kembali normal ({}{}) | durasi {} mnt".format(
                    unit, nama, angka_id(nilai), sat, durasi)
            else:
                tag = {"buka": ev["level"].upper(), "naik": "KRITIS", "ulang": "KRITIS (ulang)",
                       "eskalasi": "ESKALASI KRITIS"}.get(jenis, ev["level"].upper())
                isi = "[{}] {} | {} {}{} ({}) sejak {}".format(
                    tag, unit, nama, angka_id(nilai), sat, ev["keterangan"] or "", jam(ev["mulai"]))
        if jenis != "pulih":
            isi += " | Ack: " + link
        return {"subjek": isi.split(" | ")[0] + " " + unit, "teks": isi}

    def _penerima(self, kolom, kode_lokasi, hanya_supervisor):
        sekarang = dt.datetime.now().time()
        hasil = []
        for p in self.db.kueri("SELECT * FROM penerima_notifikasi WHERE aktif = 1"):
            if hanya_supervisor and p["peran"] != "Supervisor":
                continue
            if kolom and not p[kolom]:
                continue
            if kode_lokasi and p["cakupan_lokasi"]:
                cakupan = [c.strip().upper() for c in p["cakupan_lokasi"].split(",") if c.strip()]
                if cakupan and kode_lokasi.upper() not in cakupan:
                    continue
            if p["jam_mulai"] is not None and p["jam_selesai"] is not None:
                m = (dt.datetime.min + p["jam_mulai"]).time()
                s = (dt.datetime.min + p["jam_selesai"]).time()
                dalam = (m <= sekarang < s) if m <= s else (sekarang >= m or sekarang < s)
                if not dalam:
                    continue
            hasil.append(p)
        return hasil

    def _kirim_ke(self, ev, kolom, jenis, pesan, hanya_supervisor=False):
        ditahan = "ditahan (unit Maintenance)" if ev["status_mesin"] == "Maintenance" or ev["saat_maintenance"] else None
        penerima = self._penerima(kolom, ev["kode_lokasi"], hanya_supervisor)
        if not penerima:
            self._catat(ev["id"], jenis, "-", "-", "tidak ada penerima yang cocok", pesan["teks"])
        for p in penerima:
            self._antre(ev["id"], jenis, p, pesan, ditahan)

    def _antre(self, eid, jenis, p, pesan, ditahan):
        self.antrean.put((eid, jenis, p, pesan, ditahan))

    def _pekerja(self):
        while True:
            eid, jenis, p, pesan, ditahan = self.antrean.get()
            try:
                if ditahan:
                    self._catat(eid, jenis, p["channel"], p["alamat"], ditahan, pesan["teks"])
                else:
                    self._kirim_satu(eid, jenis, p, pesan)
            except Exception as e:
                self.log("ERROR notifikasi: {}".format(e))

    def _kirim_satu(self, eid, jenis, p, pesan, abaikan_aktif=False):
        if not self.cfg["aktif"] and not abaikan_aktif:
            status = "ditahan (notifikasi belum diaktifkan)"
        else:
            try:
                if p["channel"] == "email":
                    self._email(p["alamat"], pesan["subjek"], pesan["teks"])
                else:
                    self._telegram(p["alamat"], pesan["teks"])
                status = "terkirim"
            except Exception as e:
                status = "GAGAL: {}".format(e)[:120]
        self._catat(eid, jenis, p["channel"], p["alamat"], status, pesan["teks"])
        return status

    def _catat(self, eid, jenis, channel, penerima, status, teks):
        try:
            self.db.jalankan("INSERT INTO log_notifikasi (event_id, jenis, channel, penerima, waktu_kirim, status, pesan) "
                             "VALUES (%s,%s,%s,%s,NOW(),%s,%s)", (eid, jenis, channel, penerima, status, teks))
        except Exception as e:
            self.log("ERROR catat notifikasi: {}".format(e))

    def _email(self, ke, subjek, teks):
        c = self.cfg
        if not c["smtp_host"]:
            raise RuntimeError("SMTP belum diatur di pengaturan_dashboard.ini")
        m = EmailMessage()
        m["Subject"] = subjek[:200]
        m["From"] = c["smtp_dari"] or c["smtp_user"]
        m["To"] = ke
        m.set_content(teks.replace(" | ", "\n") + "\n\n-- Dashboard Monitoring DOCS, PT Generator Pasifik Indonesia\n"
                      "Pesan otomatis. Dashboard ini alat bantu pemantauan, bukan pengganti alarm bawaan mesin.")
        with smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=20) as s:
            if c["smtp_tls"]:
                s.starttls(context=ssl.create_default_context())
            if c["smtp_user"]:
                s.login(c["smtp_user"], c["smtp_password"])
            s.send_message(m)

    def _telegram(self, chat_id, teks):
        token = self.cfg["telegram_token"]
        if not token:
            raise RuntimeError("telegram_bot_token belum diatur di pengaturan_dashboard.ini")
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": teks, "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen("https://api.telegram.org/bot{}/sendMessage".format(token), data, timeout=20) as r:
            hasil = json.loads(r.read().decode())
            if not hasil.get("ok"):
                raise RuntimeError(hasil.get("description", "Telegram menolak pesan"))
