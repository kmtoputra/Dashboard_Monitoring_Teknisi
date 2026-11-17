import datetime as dt
import threading
import time
import traceback

PARAMETER = ["purity", "rt1", "fvsa", "fbst", "purge"]
KOLOM = {"purity": "avgpur", "rt1": "rtd_1", "fvsa": "fvsa", "fbst": "fbst", "purge": "purgeest"}
LABEL = {"purity": "Purity", "rt1": "RT1", "fvsa": "Fvsa", "fbst": "Booster", "purge": "PurgEst", "data": "Data"}
SATUAN = {"purity": "%", "rt1": "°F", "fvsa": "Hz", "fbst": "Hz", "purge": ""}
VSA_JALAN_HZ = 5.0
URUTAN_STATUS = ["Kritis", "Offline", "Terlambat", "Peringatan", "Start-up", "Normal"]


def angka_id(x, des=1):
    if x is None:
        return "--"
    return ("{:,.%df}" % des).format(float(x)).replace(",", "X").replace(".", ",").replace("X", ".")


def angka_ringkas(x):
    if x is None:
        return "--"
    return angka_id(x, 0 if float(x) == int(float(x)) else 1)


def _f(x):
    return None if x is None else float(x)


class Aturan:
    __slots__ = ("id", "parameter", "sumber", "normal_min", "normal_max", "maks1m_max", "kritis_min",
                 "kritis_max", "syarat_vsa", "delay_p", "delay_k", "pulih", "pulih_min", "naik_menit")

    def __init__(self, r):
        self.id = r.get("id")
        self.parameter = r["parameter"]
        self.sumber = r["sumber"]
        self.normal_min, self.normal_max = _f(r.get("normal_min")), _f(r.get("normal_max"))
        self.maks1m_max = _f(r.get("maks1m_max"))
        self.kritis_min, self.kritis_max = _f(r.get("kritis_min")), _f(r.get("kritis_max"))
        self.syarat_vsa = bool(r.get("kritis_syarat_vsa_jalan"))
        self.delay_p = int(r.get("delay_peringatan_detik") or 0)
        self.delay_k = None if r.get("delay_kritis_detik") is None else int(r["delay_kritis_detik"])
        self.pulih = int(r.get("pulih_detik") or 0)
        self.pulih_min = _f(r.get("pulih_min"))
        self.naik_menit = None if r.get("naik_kritis_menit") is None else int(r["naik_kritis_menit"])

    def ada_kritis(self):
        return self.kritis_min is not None or self.kritis_max is not None


def pilih_aturan(baris_aturan, mesin):
    hasil = {}
    for prioritas in (
        lambda a: a["mesin_id"] == mesin["id"],
        lambda a: a["mesin_id"] is None and (a["jenis_mesin"] or "").lower() == (mesin.get("jenis_mesin") or "").lower(),
        lambda a: a["mesin_id"] is None and not a["jenis_mesin"],
    ):
        for a in baris_aturan:
            if a["aktif"] and a["parameter"] not in hasil and prioritas(a):
                hasil[a["parameter"]] = Aturan(a)
    return hasil


def kondisi(a, v):
    p = a.parameter
    if a.sumber == "terbaru":
        x, xmax = v["terbaru"].get(p), None
    else:
        x, xmax = v["avg"].get(p), v["max"].get(p)
    if x is None:
        return None
    sat = SATUAN[p]
    if a.kritis_min is not None and x < a.kritis_min:
        if not a.syarat_vsa or (v["avg"].get("fvsa") or 0) >= VSA_JALAN_HZ:
            teks = "< {} {}".format(angka_ringkas(a.kritis_min), sat).strip()
            if p == "fvsa":
                teks += " (VSA berhenti)"
            if a.syarat_vsa:
                teks += " saat Fvsa ≥ 5 Hz (booster berhenti, VSA jalan)"
            return 2, x, "bawah", teks, False
    if a.kritis_max is not None and x > a.kritis_max:
        return 2, x, "atas", "> {} {}".format(angka_ringkas(a.kritis_max), sat).strip(), False
    if a.normal_min is not None and x < a.normal_min:
        if a.normal_max is not None:
            return 1, x, "bawah", "di luar {}–{} {}".format(angka_ringkas(a.normal_min), angka_ringkas(a.normal_max), sat).strip(), False
        return 1, x, "bawah", "< {} {}".format(angka_ringkas(a.normal_min), sat).strip(), False
    if a.normal_max is not None and x > a.normal_max:
        if a.normal_min is not None:
            return 1, x, "atas", "di luar {}–{} {}".format(angka_ringkas(a.normal_min), angka_ringkas(a.normal_max), sat).strip(), False
        teks = "rata-rata 1 menit > {} {}".format(angka_ringkas(a.normal_max), sat) if a.sumber == "avg1m" else "> {}".format(angka_ringkas(a.normal_max))
        return 1, x, "atas", teks.strip(), False
    if a.maks1m_max is not None and xmax is not None and xmax > a.maks1m_max:
        return 1, xmax, "atas", "maks 1 menit > {} {}".format(angka_ringkas(a.maks1m_max), sat).strip(), False
    pulih_ok = a.pulih_min is None or x >= a.pulih_min
    return 0, x, None, "", pulih_ok


class Evaluator:

    def __init__(self, aturan, aktif=None, startup_menit=20):
        self.aturan = aturan
        self.aktif = aktif or {}
        self.startup_menit = startup_menit
        self.st = {p: {"t1": None, "t2": None, "tpulih": None} for p in PARAMETER}
        self.startup_sampai = None
        self.fvsa_prev = None
        self.t_terakhir = None

    def dalam_startup(self, t):
        return self.startup_sampai is not None and t < self.startup_sampai

    def tick(self, t, v):
        aksi = []
        self.t_terakhir = t
        fv = v["terbaru"].get("fvsa")
        if fv is not None:
            if self.fvsa_prev is not None and self.fvsa_prev < VSA_JALAN_HZ <= fv:
                self.startup_sampai = t + dt.timedelta(minutes=self.startup_menit)
                aksi.append({"aksi": "startup", "sampai": self.startup_sampai, "t": t})
            self.fvsa_prev = fv

        for p, a in self.aturan.items():
            k = kondisi(a, v)
            if k is None:
                continue
            level, nilai, arah, teks, pulih_ok = k
            st = self.st[p]
            ev = self.aktif.get(p)
            tahan = p == "purity" and self.dalam_startup(t)
            if tahan and ev is None:
                st["t1"] = st["t2"] = st["tpulih"] = None
                continue
            st["t1"] = (st["t1"] or t) if level >= 1 else None
            st["t2"] = (st["t2"] or t) if level >= 2 else None

            if ev is None:
                if level == 2 and a.delay_k is not None and (t - st["t2"]).total_seconds() >= a.delay_k:
                    ev = self._buka(aksi, p, "Kritis", nilai, arah, teks, t)
                elif level >= 1 and (t - st["t1"]).total_seconds() >= a.delay_p:
                    ev = self._buka(aksi, p, "Peringatan", nilai, arah, teks, t)
                continue

            if level >= 1 and arah and nilai is not None and arah == ev["arah"]:
                if ev["puncak"] is None or (arah == "bawah" and nilai < ev["puncak"]) or (arah == "atas" and nilai > ev["puncak"]):
                    ev["puncak"] = nilai
                    aksi.append({"aksi": "puncak", "param": p, "nilai": nilai, "t": t})
            if ev["level"] == "Peringatan" and not tahan:
                if level == 2 and a.delay_k is not None and st["t2"] and (t - st["t2"]).total_seconds() >= a.delay_k:
                    ev["level"] = "Kritis"
                    aksi.append({"aksi": "naik", "param": p, "nilai": nilai, "teks": teks, "t": t})
                elif a.naik_menit and level >= 1 and (t - ev["mulai"]).total_seconds() >= a.naik_menit * 60:
                    ev["level"] = "Kritis"
                    aksi.append({"aksi": "naik", "param": p, "nilai": nilai, "t": t,
                                 "teks": "Peringatan bertahan ≥ {} menit".format(a.naik_menit)})
            if level == 0 and pulih_ok:
                st["tpulih"] = st["tpulih"] or t
                if (t - st["tpulih"]).total_seconds() >= a.pulih:
                    aksi.append({"aksi": "tutup", "param": p, "nilai": nilai, "t": t})
                    del self.aktif[p]
                    st["tpulih"] = None
            else:
                st["tpulih"] = None
        return aksi

    def _buka(self, aksi, p, level, nilai, arah, teks, t):
        ev = {"level": level, "mulai": t, "arah": arah, "puncak": nilai}
        self.aktif[p] = ev
        aksi.append({"aksi": "buka", "param": p, "level": level, "nilai": nilai, "teks": teks, "t": t})
        return ev


def nilai_dari_jendela(baris_jendela):
    terbaru, avg, mx = {}, {}, {}
    for p in PARAMETER:
        nilai = [b[p] for b in baris_jendela if b.get(p) is not None]
        terakhir = next((b[p] for b in reversed(baris_jendela) if b.get(p) is not None), None)
        terbaru[p] = terakhir
        avg[p] = sum(nilai) / len(nilai) if nilai else None
        mx[p] = max(nilai) if nilai else None
    return {"terbaru": terbaru, "avg": avg, "max": mx}


class Engine(threading.Thread):
    def __init__(self, db, cfg, notifier, log=print):
        super().__init__(daemon=True, name="mesin-alarm")
        self.db = db
        self.cfg = cfg["engine"]
        self.notifier = notifier
        self.log = log
        self.evaluator = {}
        self.rec_dikenal = {}
        self.agg_siap = set()
        self.status_lama = {}
        self.retensi_tanggal = None
        self.bridge_dilaporkan_mati = False
        self.berhenti = threading.Event()
        self.galat_terakhir = None

    def run(self):
        self.log("Mesin alarm berjalan, interval {} detik".format(self.cfg["interval"]))
        while not self.berhenti.is_set():
            t0 = time.time()
            try:
                self.siklus()
                self.galat_terakhir = None
            except Exception as e:
                pesan = "{}: {}".format(type(e).__name__, e)
                if pesan != self.galat_terakhir:
                    self.log("ERROR mesin alarm: " + pesan + "\n" + traceback.format_exc())
                    self.galat_terakhir = pesan
            sisa = self.cfg["interval"] - (time.time() - t0)
            self.berhenti.wait(max(sisa, 0.5))

    def siklus(self):
        db = self.db
        sekarang = db.sekarang()
        unit = db.kueri(
            "SELECT m.id, m.kode_unit, m.nama, m.jenis_mesin, m.status AS status_mesin, l.kode AS kode_lokasi, "
            "l.nama_rs, l.kota, l.zona_waktu FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id "
            "WHERE m.status <> 'Nonaktif' AND l.aktif = 1")
        aturan = db.kueri("SELECT * FROM aturan_alarm")
        hb = db.kueri("SELECT waktu FROM heartbeat WHERE nama = 'bridge'", satu=True)
        bridge_hidup = None if hb is None else (sekarang - hb["waktu"]).total_seconds() <= self.cfg["bridge_mati_detik"]
        self._cek_bridge(bridge_hidup, sekarang)

        for u in unit:
            mid = u["id"]
            self._agregasi(mid)
            ev = self.evaluator.get(mid)
            if ev is None:
                ev = self._evaluator_baru(u, aturan)
            else:
                ev.aturan = pilih_aturan(aturan, u)
            data_terakhir = db.nilai("SELECT MAX(waktu_terakhir) FROM sesi_log WHERE mesin_id = %s", (mid,))
            umur = None if data_terakhir is None else (sekarang - data_terakhir).total_seconds()

            if umur is not None and umur <= self.cfg["terlambat"] and (ev.t_terakhir is None or data_terakhir > ev.t_terakhir):
                v = self._nilai_live(mid, data_terakhir)
                for a in ev.tick(data_terakhir, v):
                    self._terapkan(u, a)

            offline = umur is None or umur > self.cfg["offline"]
            self._offline(u, offline, bridge_hidup is not False, data_terakhir, sekarang)

            if offline:
                status = "Offline"
            elif umur > self.cfg["terlambat"]:
                status = "Terlambat"
            elif any(e["level"] == "Kritis" for e in ev.aktif.values()):
                status = "Kritis"
            elif ev.aktif:
                status = "Peringatan"
            elif ev.dalam_startup(data_terakhir):
                status = "Start-up"
            else:
                status = "Normal"
            self._simpan_status(mid, status, sekarang, ev.startup_sampai, data_terakhir)

        self.notifier.periodik(sekarang)
        db.jalankan("INSERT INTO heartbeat (nama, waktu, info) VALUES ('dashboard', NOW(), %s) "
                    "ON DUPLICATE KEY UPDATE waktu = NOW(), info = %s",
                    ("{} unit dievaluasi".format(len(unit)),) * 2)
        self._retensi(sekarang)

    def _evaluator_baru(self, u, aturan):
        aktif = {}
        for r in self.db.kueri("SELECT * FROM event_alarm WHERE mesin_id = %s AND selesai IS NULL "
                               "AND parameter <> 'data'", (u["id"],)):
            aktif[r["parameter"]] = {"level": r["level"], "mulai": r["mulai"], "id": r["id"],
                                     "arah": "bawah" if r["parameter"] in ("purity", "fvsa", "fbst") else "atas",
                                     "puncak": _f(r["nilai_puncak"])}
        ev = Evaluator(pilih_aturan(aturan, u), aktif, self.cfg["startup_menit"])
        st = self.db.kueri("SELECT startup_sampai FROM status_unit WHERE mesin_id = %s", (u["id"],), satu=True)
        if st and st["startup_sampai"]:
            ev.startup_sampai = st["startup_sampai"]
        self.evaluator[u["id"]] = ev
        return ev

    def _nilai_live(self, mid, t):
        akhir = self.db.kueri(
            "SELECT avgpur, rtd_1, fvsa, fbst, purgeest FROM telemetri WHERE mesin_id = %s AND waktu <= %s "
            "ORDER BY waktu DESC, rec_no DESC LIMIT 1", (mid, t), satu=True) or {}
        j = self.db.kueri(
            "SELECT AVG(avgpur) a_purity, MAX(avgpur) m_purity, AVG(rtd_1) a_rt1, MAX(rtd_1) m_rt1, "
            "AVG(fvsa) a_fvsa, MAX(fvsa) m_fvsa, AVG(fbst) a_fbst, MAX(fbst) m_fbst, "
            "AVG(purgeest) a_purge, MAX(purgeest) m_purge FROM telemetri "
            "WHERE mesin_id = %s AND waktu > %s - INTERVAL 60 SECOND AND waktu <= %s", (mid, t, t), satu=True) or {}
        return {"terbaru": {p: _f(akhir.get(KOLOM[p])) for p in PARAMETER},
                "avg": {p: _f(j.get("a_" + p)) for p in PARAMETER},
                "max": {p: _f(j.get("m_" + p)) for p in PARAMETER}}

    def _terapkan(self, u, a):
        db = self.db
        mid, p = u["id"], a.get("param")
        maint = 1 if u["status_mesin"] == "Maintenance" else 0
        ev = self.evaluator[mid].aktif.get(p) if p else None
        if a["aksi"] == "startup":
            self.log("{} Start-up: alarm purity ditahan sampai {}".format(u["kode_unit"], a["sampai"]))
            return
        if a["aksi"] == "buka":
            eid = db.jalankan(
                "INSERT INTO event_alarm (mesin_id, parameter, level, level_awal, mulai, nilai_awal, nilai_puncak, "
                "nilai_terakhir, keterangan, saat_maintenance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (mid, p, a["level"], a["level"], a["t"], a["nilai"], a["nilai"], a["nilai"], a["teks"][:255], maint))
            ev["id"] = eid
            self.notifier.kejadian("buka", eid)
        elif a["aksi"] == "naik" and ev:
            db.jalankan("UPDATE event_alarm SET level = 'Kritis', naik_kritis = %s, nilai_terakhir = %s, "
                        "keterangan = %s WHERE id = %s", (a["t"], a["nilai"], a["teks"][:255], ev["id"]))
            self.notifier.kejadian("naik", ev["id"])
        elif a["aksi"] == "puncak" and ev and ev.get("id"):
            db.jalankan("UPDATE event_alarm SET nilai_puncak = %s, nilai_terakhir = %s WHERE id = %s",
                        (a["nilai"], a["nilai"], ev["id"]))
        elif a["aksi"] == "tutup":
            eid = db.nilai("SELECT id FROM event_alarm WHERE mesin_id = %s AND parameter = %s AND selesai IS NULL "
                           "ORDER BY id DESC LIMIT 1", (mid, p))
            if eid:
                db.jalankan("UPDATE event_alarm SET selesai = %s, nilai_terakhir = %s WHERE id = %s",
                            (a["t"], a["nilai"], eid))
                self.notifier.kejadian("pulih", eid)

    def _offline(self, u, offline, boleh_buka, data_terakhir, sekarang):
        db = self.db
        eid = db.nilai("SELECT id FROM event_alarm WHERE mesin_id = %s AND parameter = 'data' AND selesai IS NULL",
                       (u["id"],))
        if offline and not eid and boleh_buka:
            maint = 1 if u["status_mesin"] == "Maintenance" else 0
            ket = "Tidak ada data sejak {}".format(data_terakhir.strftime("%d/%m %H:%M")) if data_terakhir else "Belum pernah ada data"
            eid = db.jalankan(
                "INSERT INTO event_alarm (mesin_id, parameter, level, level_awal, mulai, keterangan, saat_maintenance) "
                "VALUES (%s, 'data', 'Offline', 'Offline', %s, %s, %s)", (u["id"], sekarang, ket, maint))
            self.notifier.kejadian("buka", eid)
        elif not offline and eid:
            db.jalankan("UPDATE event_alarm SET selesai = %s WHERE id = %s", (sekarang, eid))
            self.notifier.kejadian("pulih", eid)

    def _simpan_status(self, mid, status, sekarang, startup_sampai, data_terakhir):
        lama = self.status_lama.get(mid)
        if lama is None:
            r = self.db.kueri("SELECT status FROM status_unit WHERE mesin_id = %s", (mid,), satu=True)
            lama = r["status"] if r else None
        if lama != status:
            self.db.jalankan("UPDATE riwayat_status SET selesai = %s WHERE mesin_id = %s AND selesai IS NULL",
                             (sekarang, mid))
            self.db.jalankan("INSERT INTO riwayat_status (mesin_id, status, mulai) VALUES (%s,%s,%s)",
                             (mid, status, sekarang))
            self.db.jalankan(
                "INSERT INTO status_unit (mesin_id, status, sejak, startup_sampai, data_terakhir) VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE status = VALUES(status), sejak = VALUES(sejak), "
                "startup_sampai = VALUES(startup_sampai), data_terakhir = VALUES(data_terakhir)",
                (mid, status, sekarang, startup_sampai, data_terakhir))
        else:
            self.db.jalankan("UPDATE status_unit SET startup_sampai = %s, data_terakhir = %s WHERE mesin_id = %s",
                             (startup_sampai, data_terakhir, mid))
        self.status_lama[mid] = status

    def _cek_bridge(self, hidup, sekarang):
        if hidup is False and not self.bridge_dilaporkan_mati:
            self.notifier.sistem("Bridge DOCSApp ke MySQL tidak mengirim heartbeat lebih dari {} detik. "
                                 "Semua unit akan terlihat Offline. Cek jendela docs_ke_mysql.py di PC kantor."
                                 .format(self.cfg["bridge_mati_detik"]))
            self.bridge_dilaporkan_mati = True
        elif hidup and self.bridge_dilaporkan_mati:
            self.notifier.sistem("Bridge DOCSApp ke MySQL berjalan lagi.")
            self.bridge_dilaporkan_mati = False

    def _agregasi(self, mid):
        db = self.db
        sesi = db.kueri("SELECT id, rec_no_terakhir FROM sesi_log WHERE mesin_id = %s", (mid,))
        if mid not in self.agg_siap:
            dari = db.nilai("SELECT MAX(menit) FROM agregat_1menit WHERE mesin_id = %s", (mid,))
            if dari is None:
                dari = db.nilai("SELECT MIN(waktu) FROM telemetri WHERE mesin_id = %s", (mid,))
            if dari is not None:
                self._hitung_agregat(mid, dari)
            for s in sesi:
                self.rec_dikenal[s["id"]] = s["rec_no_terakhir"]
            self.agg_siap.add(mid)
            return
        dari = None
        for s in sesi:
            lama = self.rec_dikenal.get(s["id"], 0)
            if s["rec_no_terakhir"] > lama:
                t = db.nilai("SELECT MIN(waktu) FROM telemetri WHERE sesi_id = %s AND rec_no > %s", (s["id"], lama))
                if t is not None and (dari is None or t < dari):
                    dari = t
                self.rec_dikenal[s["id"]] = s["rec_no_terakhir"]
        if dari is not None:
            self._hitung_agregat(mid, dari)

    def _hitung_agregat(self, mid, dari):
        db = self.db
        mulai = dari.replace(second=0, microsecond=0)
        akhir = db.nilai("SELECT MAX(waktu) FROM telemetri WHERE mesin_id = %s", (mid,))
        if akhir is None:
            return
        while mulai <= akhir:
            sampai = mulai + dt.timedelta(days=1)
            db.jalankan(
                "INSERT INTO agregat_1menit (mesin_id, menit, n, purity_avg, purity_min, purity_max, rt1_avg, rt1_min, "
                "rt1_max, fvsa_avg, fvsa_min, fvsa_max, purge_avg, purge_min, purge_max, fbst_avg, fbst_min, fbst_max) "
                "SELECT mesin_id, DATE_FORMAT(waktu, '%Y-%m-%d %H:%i:00') AS mnt, COUNT(*), "
                "AVG(avgpur), MIN(avgpur), MAX(avgpur), AVG(rtd_1), MIN(rtd_1), MAX(rtd_1), "
                "AVG(fvsa), MIN(fvsa), MAX(fvsa), AVG(purgeest), MIN(purgeest), MAX(purgeest), "
                "AVG(fbst), MIN(fbst), MAX(fbst) FROM telemetri "
                "WHERE mesin_id = %s AND waktu >= %s AND waktu < %s GROUP BY mesin_id, mnt "
                "ON DUPLICATE KEY UPDATE n = VALUES(n), purity_avg = VALUES(purity_avg), purity_min = VALUES(purity_min), "
                "purity_max = VALUES(purity_max), rt1_avg = VALUES(rt1_avg), rt1_min = VALUES(rt1_min), "
                "rt1_max = VALUES(rt1_max), fvsa_avg = VALUES(fvsa_avg), fvsa_min = VALUES(fvsa_min), "
                "fvsa_max = VALUES(fvsa_max), purge_avg = VALUES(purge_avg), purge_min = VALUES(purge_min), "
                "purge_max = VALUES(purge_max), fbst_avg = VALUES(fbst_avg), fbst_min = VALUES(fbst_min), "
                "fbst_max = VALUES(fbst_max)", (mid, mulai, sampai))
            mulai = sampai

    def _retensi(self, sekarang):
        if sekarang.hour != self.cfg["jam_retensi"] or self.retensi_tanggal == sekarang.date():
            return
        self.retensi_tanggal = sekarang.date()
        total = 0
        for tabel, kolom, hari in (("telemetri", "waktu", self.cfg["simpan_mentah_hari"]),
                                   ("agregat_1menit", "menit", self.cfg["simpan_agregat_hari"]),
                                   ("riwayat_status", "mulai", self.cfg["simpan_agregat_hari"])):
            while True:
                n = self.db.jalankan("DELETE FROM {} WHERE {} < NOW() - INTERVAL %s DAY LIMIT 5000".format(tabel, kolom),
                                     (hari,))
                total += n or 0
                if not n or n < 5000:
                    break
                time.sleep(0.2)
        self.log("Retensi harian selesai: {} baris lama dihapus".format(total))
