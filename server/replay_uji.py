import argparse
import collections
import copy
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Database, baca_pengaturan
from engine import (KOLOM, LABEL, PARAMETER, SATUAN, VSA_JALAN_HZ, Evaluator, angka_id,
                    nilai_dari_jendela, pilih_aturan)


def ambil(db, mid, dari, sampai):
    kol = ", ".join(KOLOM[p] for p in PARAMETER)
    rows = db.kueri("SELECT waktu, {} FROM telemetri WHERE mesin_id = %s AND waktu >= %s AND waktu <= %s "
                    "ORDER BY waktu, rec_no".format(kol), (mid, dari, sampai))
    return [dict({"waktu": r["waktu"]}, **{p: None if r[KOLOM[p]] is None else float(r[KOLOM[p]]) for p in PARAMETER})
            for r in rows]


def putar(baris, aturan, startup_menit):
    ev = Evaluator(aturan, {}, startup_menit)
    jendela = collections.deque()
    kejadian, terbuka = [], {}
    for b in baris:
        t = b["waktu"]
        jendela.append(b)
        while jendela and (t - jendela[0]["waktu"]).total_seconds() >= 60:
            jendela.popleft()
        for a in ev.tick(t, nilai_dari_jendela(list(jendela))):
            p = a.get("param")
            if a["aksi"] == "buka":
                k = {"param": p, "level": a["level"], "mulai": t, "nilai": a["nilai"], "teks": a["teks"],
                     "naik": None, "selesai": None, "puncak": a["nilai"]}
                kejadian.append(k)
                terbuka[p] = k
            elif a["aksi"] == "naik" and p in terbuka:
                terbuka[p]["naik"] = t
                terbuka[p]["level"] = "Kritis"
                terbuka[p]["teks"] += " → " + a["teks"]
            elif a["aksi"] == "puncak" and p in terbuka:
                terbuka[p]["puncak"] = a["nilai"]
            elif a["aksi"] == "tutup" and p in terbuka:
                terbuka.pop(p)["selesai"] = t
            elif a["aksi"] == "startup":
                kejadian.append({"param": "startup", "mulai": t, "sampai": a["sampai"]})
    return kejadian


def cetak(kejadian):
    alarm = [k for k in kejadian if k["param"] != "startup"]
    for k in kejadian:
        if k["param"] == "startup":
            print("    {}  START-UP terdeteksi, alarm purity ditahan sampai {}".format(
                k["mulai"].strftime("%d/%m %H:%M:%S"), k["sampai"].strftime("%H:%M:%S")))
            continue
        sat = SATUAN.get(k["param"], "")
        print("    {}  {:<10} {:<8} nilai {}{} ({}), puncak {}{}{}{}".format(
            k["mulai"].strftime("%d/%m %H:%M:%S"), k["level"].upper(), LABEL[k["param"]], angka_id(k["nilai"]), sat,
            k["teks"], angka_id(k["puncak"]), sat,
            ", naik Kritis {}".format(k["naik"].strftime("%H:%M:%S")) if k["naik"] else "",
            ", pulih {}".format(k["selesai"].strftime("%H:%M:%S")) if k["selesai"] else ", MASIH AKTIF di akhir data"))
    if not alarm:
        print("    (tidak ada alarm)")
    return alarm


def ubah(baris, mulai_detik, lama_detik, fungsi):
    hasil = copy.deepcopy(baris)
    t0 = hasil[0]["waktu"]
    for b in hasil:
        s = (b["waktu"] - t0).total_seconds()
        if mulai_detik <= s < mulai_detik + lama_detik:
            fungsi(b, s - mulai_detik)
    return hasil


def skenario(baris, aturan, startup_menit):
    hasil = []
    print("\n[UAT 3] Replay data apa adanya: data normal tidak boleh memunculkan alarm")
    alarm = cetak(putar(baris, aturan, startup_menit))
    hasil.append(("UAT 3 data normal tanpa alarm", not alarm,
                  "{} alarm muncul. Cek apakah datanya memang tidak normal, atau ambang perlu dikalibrasi"
                  .format(len(alarm)) if alarm else ""))

    mulai = 600
    print("\n[UAT 7] Purity dipaksa 89 % selama 90 detik mulai menit ke-10: harus KRITIS (delay 60 detik)")
    d = ubah(baris, mulai, 90, lambda b, s: b.update(purity=89.0))
    alarm = [k for k in cetak(putar(d, aturan, startup_menit)) if k["param"] == "purity"]
    ok = any(k["level"] == "Kritis" and 55 <= (k["mulai"] - d[0]["waktu"]).total_seconds() - mulai <= 70 for k in alarm)
    hasil.append(("UAT 7 purity 89 % 1 menit -> Kritis", ok, "" if ok else "tidak ada event Kritis purity sekitar 60 detik"))

    print("\n[UAT 8] RT1 lonjakan 250 °F selama 5 detik: TIDAK boleh alarm")
    d = ubah(baris, mulai, 5, lambda b, s: b.update(rt1=250.0))
    alarm = [k for k in cetak(putar(d, aturan, startup_menit)) if k["param"] == "rt1"
             and abs((k["mulai"] - d[0]["waktu"]).total_seconds() - mulai) < 900]
    hasil.append(("UAT 8 lonjakan RT1 5 detik tanpa alarm", not alarm, "{} alarm RT1".format(len(alarm)) if alarm else ""))

    print("\n[UAT 9] Mesin berhenti 3 menit (Fvsa 0), lalu start-up dengan purity naik pelan 85 -> 93 % dalam 12 menit")
    print("        Harus: Fvsa KRITIS saat berhenti; TIDAK ada alarm purity selama 20 menit start-up")
    beku = {}

    def mati_hidup(b, s):
        if s < 180:
            beku.setdefault("purity", b["purity"])
            b.update(fvsa=0.0, fbst=0.0, purity=beku["purity"])
        elif s < 180 + 720:
            b["purity"] = 85.0 + 8.0 * (s - 180) / 720
    d = ubah(baris, mulai, 180 + 720, mati_hidup)
    k9 = putar(d, aturan, startup_menit)
    cetak(k9)
    t_restart = d[0]["waktu"] + dt.timedelta(seconds=mulai + 180)
    ada_startup = any(k["param"] == "startup" for k in k9)
    purity_alarm = [k for k in k9 if k["param"] == "purity" and t_restart <= k["mulai"] <= t_restart + dt.timedelta(minutes=20)]
    fvsa_kritis = any(k["param"] == "fvsa" and k["level"] == "Kritis" for k in k9)
    ok = ada_startup and not purity_alarm and fvsa_kritis
    hasil.append(("UAT 9 penahanan start-up 20 menit", ok,
                  "" if ok else "start-up {}, alarm purity {}, Fvsa kritis {}".format(ada_startup, len(purity_alarm), fvsa_kritis)))
    print("        Pembanding tanpa penahanan start-up:")
    tanpa = [k for k in putar(d, aturan, 0) if k["param"] == "purity"]
    print("        -> {} alarm purity akan muncul kalau tidak ada penahanan".format(len(tanpa)))

    print("\n" + "=" * 72)
    for nama, ok, ket in hasil:
        print("  {:<6} {}{}".format("LULUS" if ok else "GAGAL", nama, "  ({})".format(ket) if ket else ""))
    print("=" * 72)
    return all(ok for _, ok, _ in hasil)


def statistik(db, mid, dari, sampai):
    print("\nStatistik rata-rata 1 menit saat VSA jalan (Fvsa >= {} Hz), {} s.d. {}".format(
        VSA_JALAN_HZ, dari.strftime("%d/%m/%Y %H:%M"), sampai.strftime("%d/%m/%Y %H:%M")))
    rows = db.kueri("SELECT * FROM agregat_1menit WHERE mesin_id = %s AND menit >= %s AND menit <= %s "
                    "AND fvsa_avg >= %s", (mid, dari, sampai, VSA_JALAN_HZ))
    total = db.nilai("SELECT COUNT(*) FROM agregat_1menit WHERE mesin_id = %s AND menit >= %s AND menit <= %s",
                     (mid, dari, sampai))
    print("Menit berisi data: {} (VSA jalan {}). Disarankan minimal 7 hari data.".format(total, len(rows)))
    if not rows:
        return
    pers = [0.5, 1, 5, 50, 95, 99, 99.5]
    print("\n  {:<9} {:>8}".format("Param", "min") + "".join("{:>8}".format("P{}".format(p)) for p in pers) + "{:>8}".format("maks"))
    for p in PARAMETER:
        nilai = sorted(float(r[p + "_avg"]) for r in rows if r[p + "_avg"] is not None)
        if not nilai:
            continue

        def q(x):
            i = (len(nilai) - 1) * x / 100
            a, b = int(i), min(int(i) + 1, len(nilai) - 1)
            return nilai[a] + (nilai[b] - nilai[a]) * (i - a)
        print("  {:<9} {:>8}".format(LABEL[p], angka_id(nilai[0])) + "".join("{:>8}".format(angka_id(q(x))) for x in pers)
              + "{:>8}".format(angka_id(nilai[-1])))
    mx = sorted(float(r["rt1_max"]) for r in rows if r["rt1_max"] is not None)
    if mx:
        print("  {:<9} {:>8}{:>48}{:>8}".format("RT1 maks", angka_id(mx[0]), "P99 " + angka_id(mx[int(0.99 * (len(mx) - 1))]),
                                               angka_id(mx[-1])))
    print("\nPanduan: batas normal sebaiknya di luar P1/P99 data normal, supaya alarm palsu < 1 per minggu.\n"
          "Ubah ambang di Dashboard > Admin > Ambang Alarm, lalu jalankan --skenario semua lagi.")


def main():
    ap = argparse.ArgumentParser(description="Uji replay alarm dan statistik ambang")
    ap.add_argument("--unit", required=True, help="kode unit, contoh DOCS-BDG-01")
    ap.add_argument("--dari", help='awal data, contoh "2026-11-11 09:00" (default: 6 jam terakhir yang ada data)')
    ap.add_argument("--sampai", help="akhir data")
    ap.add_argument("--skenario", choices=["normal", "semua"], default="normal")
    ap.add_argument("--statistik", action="store_true")
    ap.add_argument("--hari", type=int, default=7, help="untuk --statistik tanpa --dari")
    args = ap.parse_args()

    cfg = baca_pengaturan()
    db = Database(cfg["mysql"], 2)
    u = db.kueri("SELECT m.*, l.nama_rs FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id WHERE m.kode_unit = %s",
                 (args.unit.upper(),), satu=True)
    if not u:
        print("Unit {} tidak ada di tabel mesin".format(args.unit))
        return 1
    akhir = db.nilai("SELECT MAX(waktu) FROM telemetri WHERE mesin_id = %s", (u["id"],))
    if akhir is None:
        print("Belum ada data telemetri untuk {}".format(args.unit))
        return 1
    fmt = "%Y-%m-%d %H:%M"
    sampai = dt.datetime.strptime(args.sampai, fmt) if args.sampai else akhir
    if args.statistik:
        dari = dt.datetime.strptime(args.dari, fmt) if args.dari else sampai - dt.timedelta(days=args.hari)
        statistik(db, u["id"], dari, sampai)
        return 0
    dari = dt.datetime.strptime(args.dari, fmt) if args.dari else sampai - dt.timedelta(hours=6)
    baris = ambil(db, u["id"], dari, sampai)
    if len(baris) < 1800:
        print("Data terlalu sedikit untuk replay ({} baris, perlu minimal 30 menit)".format(len(baris)))
        return 1
    aturan = pilih_aturan(db.kueri("SELECT * FROM aturan_alarm"), u)
    print("Unit {} ({}), {} baris, {} s.d. {}".format(u["kode_unit"], u["nama_rs"], len(baris),
                                                     baris[0]["waktu"], baris[-1]["waktu"]))
    print("Aturan aktif: " + ", ".join(sorted(aturan)) if aturan else "PERHATIAN: unit ini belum punya aturan alarm")
    if args.skenario == "semua":
        return 0 if skenario(baris, aturan, cfg["engine"]["startup_menit"]) else 2
    print("\nReplay data apa adanya:")
    cetak(putar(baris, aturan, cfg["engine"]["startup_menit"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
