import argparse
import configparser
import datetime as dt
import json
import math
import os
import re
import sys
import time
import traceback

try:
    import mysql.connector
except ImportError:
    print("Paket mysql-connector-python belum terpasang. Jalankan:  pip install mysql-connector-python")
    sys.exit(1)

FOLDER = os.path.dirname(os.path.abspath(__file__))
KOLOM_KHUSUS = {"recno": "rec_no", "seconds": "detik_unit", "date": "waktu"}
EXCEL_EPOCH = dt.datetime(1899, 12, 30)


class Catatan:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def tulis(self, jenis, teks):
        baris = "{}  {:<11} {}".format(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), jenis, teks)
        print(baris, flush=True)
        path = os.path.join(self.folder, "docs_ke_mysql_{}.txt".format(dt.date.today().isoformat()))
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(baris + "\n")
        except OSError:
            pass


def baca_pengaturan():
    path = os.path.join(FOLDER, "pengaturan_mysql.ini")
    if not os.path.exists(path):
        print("File pengaturan tidak ditemukan: " + path)
        sys.exit(1)
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    return {
        "mysql": dict(
            host=cp.get("mysql", "host", fallback="127.0.0.1"),
            port=cp.getint("mysql", "port", fallback=3306),
            user=cp.get("mysql", "user"),
            password=cp.get("mysql", "password"),
            database=cp.get("mysql", "database", fallback="gpi_monitoring"),
        ),
        "interval": cp.getint("ingest", "interval_detik", fallback=5),
        "sheet": cp.get("ingest", "sheet", fallback="LOGDAT1"),
        "baris_per_baca": cp.getint("ingest", "baris_per_baca", fallback=2000),
        "batas_diam_menit": cp.getint("ingest", "batas_diam_menit", fallback=5),
        "ringkasan_menit": cp.getint("ingest", "ringkasan_menit", fallback=10),
    }


def nama_kolom(judul):
    s = re.sub(r"[^0-9a-z]+", "_", str(judul).strip().lower()).strip("_")
    return KOLOM_KHUSUS.get(s, s)


class Database:
    def __init__(self, cfg, catatan):
        self.cfg = cfg
        self.cat = catatan
        self.conn = None
        self.kolom = {}
        self.mesin = []

    def sambung(self):
        if self.conn is not None:
            try:
                if self.conn.is_connected():
                    return
            except Exception:
                pass
        self.conn = mysql.connector.connect(autocommit=False, connection_timeout=10, **self.cfg)
        self.muat_meta()

    def muat_meta(self):
        cur = self.conn.cursor(dictionary=True)
        cur.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, "
            "CHARACTER_MAXIMUM_LENGTH, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'telemetri'")
        self.kolom = {r["COLUMN_NAME"].lower(): r for r in cur.fetchall()}
        if not self.kolom:
            raise RuntimeError("Tabel telemetri belum ada. Jalankan dulu 01_skema_telemetri.sql")
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mesin'")
        ada = {r["COLUMN_NAME"].lower() for r in cur.fetchall()}
        kol_bfn = "m.base_file_name" if "base_file_name" in ada else "NULL"
        syarat = "m.status <> 'Nonaktif'" if "status" in ada else "m.aktif = 1"
        cur.execute(
            "SELECT m.id, l.kode, m.nama, m.pola_workbook, {} AS base_file_name FROM mesin m "
            "JOIN lokasi l ON l.id = m.lokasi_id WHERE {} AND l.aktif = 1".format(kol_bfn, syarat))
        self.mesin = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'heartbeat'")
        self.ada_heartbeat = cur.fetchone()["n"] > 0
        cur.close()
        self.conn.commit()

    def cari_mesin_kode(self, kode_nama):
        try:
            kode, nama = kode_nama.split("/", 1)
        except ValueError:
            return None
        for m in self.mesin:
            if m["kode"].upper() == kode.strip().upper() and m["nama"].upper() == nama.strip().upper():
                return m
        return None

    def cocokkan(self, nama_workbook):
        nama = (nama_workbook or "").lower()
        awalan = [m for m in self.mesin if m.get("base_file_name") and nama.startswith(m["base_file_name"].strip().lower())]
        if awalan:
            awalan.sort(key=lambda m: len(m["base_file_name"]), reverse=True)
            if len(awalan) == 1 or len(awalan[0]["base_file_name"]) > len(awalan[1]["base_file_name"]):
                return awalan[0], "cocok (Base File Name)"
            return None, "Base File Name sama di lebih dari satu unit: " + ", ".join(
                "{}/{}".format(m["kode"], m["nama"]) for m in awalan)
        cocok = []
        for m in self.mesin:
            for pola in (m["pola_workbook"] or "").split(","):
                pola = pola.strip().lower()
                if pola and pola in nama:
                    cocok.append(m)
                    break
        if len(cocok) == 1:
            return cocok[0], "cocok"
        if not cocok:
            return None, "tidak cocok dengan Base File Name / pola_workbook unit mana pun"
        return None, "cocok dengan lebih dari satu mesin: " + ", ".join(
            "{}/{}".format(m["kode"], m["nama"]) for m in cocok)

    def sesi(self, mesin_id, waktu_mulai, detik_mulai, nama_sumber):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sesi_log (mesin_id, waktu_mulai, detik_unit_mulai, nama_sumber) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), nama_sumber = COALESCE(nama_sumber, %s)",
            (mesin_id, waktu_mulai, detik_mulai, nama_sumber, nama_sumber))
        sesi_id = cur.lastrowid
        cur.execute("SELECT rec_no_terakhir FROM sesi_log WHERE id = %s", (sesi_id,))
        rec = cur.fetchone()[0]
        cur.close()
        self.conn.commit()
        return sesi_id, int(rec or 0)

    def simpan(self, sesi_id, mesin_id, baris):
        if not baris:
            return 0
        kolom = ["sesi_id", "mesin_id"] + [k for k in self.kolom_data() if any(k in b for b in baris)]
        if any("lainnya" in b for b in baris) and "lainnya" not in kolom:
            kolom.append("lainnya")
        tanda = "(" + ",".join(["%s"] * len(kolom)) + ")"
        awal = "INSERT INTO telemetri ({}) VALUES ".format(",".join("`{}`".format(k) for k in kolom))
        akhir = " ON DUPLICATE KEY UPDATE rec_no = rec_no"
        cur = self.conn.cursor()
        baru = 0
        try:
            for i in range(0, len(baris), 500):
                potong = baris[i:i + 500]
                nilai = []
                for b in potong:
                    nilai.extend([sesi_id, mesin_id] + [b.get(k) for k in kolom[2:]])
                cur.execute(awal + ",".join([tanda] * len(potong)) + akhir, nilai)
                baru += sum(1 for _ in potong)
            terakhir = max(baris, key=lambda b: b["rec_no"])
            cur.execute(
                "UPDATE sesi_log SET rec_no_terakhir = GREATEST(rec_no_terakhir, %s), "
                "waktu_terakhir = GREATEST(COALESCE(waktu_terakhir, %s), %s) WHERE id = %s",
                (terakhir["rec_no"], terakhir["waktu"], terakhir["waktu"], sesi_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()
        return baru

    def heartbeat(self, info):
        if not getattr(self, "ada_heartbeat", False):
            return
        cur = self.conn.cursor()
        try:
            cur.execute("INSERT INTO heartbeat (nama, waktu, info) VALUES ('bridge', NOW(), %s) "
                        "ON DUPLICATE KEY UPDATE waktu = NOW(), info = %s", (info[:255], info[:255]))
            self.conn.commit()
        finally:
            cur.close()

    def kolom_data(self):
        return [k for k in self.kolom if k not in ("sesi_id", "mesin_id", "lainnya", "masuk")]


def angka(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v
    if isinstance(v, str):
        try:
            x = float(v.strip().replace(",", "."))
            return None if (math.isnan(x) or math.isinf(x)) else x
        except ValueError:
            return None
    return None


def bersihkan(nilai, info):
    if nilai is None or (isinstance(nilai, str) and nilai.strip() == ""):
        return None, True
    t = info["DATA_TYPE"].lower()
    if t in ("decimal", "float", "double"):
        x = angka(nilai)
        if x is None:
            return None, False
        if t == "decimal":
            batas = 10 ** ((info["NUMERIC_PRECISION"] or 10) - (info["NUMERIC_SCALE"] or 0))
            if abs(x) >= batas:
                return None, False
            return round(float(x), info["NUMERIC_SCALE"] or 0), True
        return float(x), True
    if t in ("tinyint", "smallint", "mediumint", "int", "bigint"):
        x = angka(nilai)
        if x is None or x != x:
            return None, False
        x = int(round(x))
        if "unsigned" in info["COLUMN_TYPE"].lower() and x < 0:
            return None, False
        return x, True
    if t in ("datetime", "timestamp", "date"):
        if isinstance(nilai, dt.datetime):
            return nilai.replace(microsecond=0, tzinfo=None), True
        if isinstance(nilai, dt.date):
            return dt.datetime(nilai.year, nilai.month, nilai.day), True
        x = angka(nilai)
        if x is not None and 20000 < x < 80000:
            return (EXCEL_EPOCH + dt.timedelta(days=x)).replace(microsecond=0), True
        if isinstance(nilai, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
                try:
                    return dt.datetime.strptime(nilai.strip(), fmt), True
                except ValueError:
                    pass
        return None, False
    s = str(nilai).strip()
    if isinstance(nilai, float) and nilai.is_integer():
        s = str(int(nilai))
    maks = info["CHARACTER_MAXIMUM_LENGTH"]
    if maks and len(s) > maks:
        return s[:maks], False
    return s, True


def susun_baris(judul_kolom, data, db):
    hasil, lain = {}, {}
    for kol, v in zip(judul_kolom, data):
        if kol is None:
            continue
        info = db.kolom.get(kol)
        if info is None:
            if v is not None:
                lain[kol] = v if isinstance(v, (int, float, str)) else str(v)
            continue
        bersih, ok = bersihkan(v, info)
        hasil[kol] = bersih
        if not ok and v is not None:
            lain[kol] = v if isinstance(v, (int, float, str)) else str(v)
    if hasil.get("rec_no") is None or hasil.get("waktu") is None:
        return None
    if lain:
        hasil["lainnya"] = json.dumps(lain, default=str)
    return hasil


def siapkan_judul(baris_judul):
    return [nama_kolom(j) if j not in (None, "") else None for j in baris_judul]


def impor_file(path, kode_mesin, cfg, cat):
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("Paket openpyxl belum terpasang. Jalankan:  pip install openpyxl")
        sys.exit(1)
    db = Database(cfg["mysql"], cat)
    db.sambung()
    nama = os.path.basename(path)
    if kode_mesin:
        mesin = db.cari_mesin_kode(kode_mesin)
        alasan = "tidak ada di tabel mesin"
    else:
        mesin, alasan = db.cocokkan(nama)
    if not mesin:
        cat.tulis("GAGAL", "{}: mesin tidak dikenali ({}). Pakai --mesin KODE/NAMA, "
                           "misalnya --mesin BANDUNG/DOCS500.".format(nama, alasan))
        return 1
    wb = load_workbook(path, read_only=True, data_only=True)
    if cfg["sheet"] not in wb.sheetnames:
        cat.tulis("GAGAL", "{}: sheet {} tidak ada".format(nama, cfg["sheet"]))
        return 1
    ws = wb[cfg["sheet"]]
    baris_iter = ws.iter_rows(values_only=True)
    judul = siapkan_judul(next(baris_iter))
    label = "{}/{}".format(mesin["kode"], mesin["nama"])
    cat.tulis("IMPOR", "{} -> {}".format(nama, label))
    sesi_id, rec_terakhir, total, lewat, gagal = None, 0, 0, 0, 0
    kumpulan = []
    t0 = time.time()
    for data in baris_iter:
        b = susun_baris(judul, data, db)
        if b is None:
            if any(v is not None for v in data):
                gagal += 1
            continue
        if sesi_id is None:
            sesi_id, rec_terakhir = db.sesi(mesin["id"], b["waktu"], b.get("detik_unit") or 0, nama)
            cat.tulis("SESI", "{}: sesi {} mulai {}, sudah tersimpan sampai RecNo {}".format(
                label, sesi_id, b["waktu"], rec_terakhir))
        if b["rec_no"] <= rec_terakhir:
            lewat += 1
            continue
        kumpulan.append(b)
        if len(kumpulan) >= 2000:
            total += db.simpan(sesi_id, mesin["id"], kumpulan)
            kumpulan = []
    if kumpulan:
        total += db.simpan(sesi_id, mesin["id"], kumpulan)
    cat.tulis("SELESAI", "{}: {} baris diproses, {} sudah ada sebelumnya, {} baris tanpa RecNo/Date dilewati "
                         "({:.1f} detik)".format(label, total, lewat, gagal, time.time() - t0))
    return 0


def buka_xlwings():
    try:
        import xlwings as xw
        return xw
    except ImportError:
        print("Paket xlwings belum terpasang. Jalankan:  pip install xlwings")
        sys.exit(1)


def daftar_workbook(xw, nama_sheet):
    hasil = []
    for app in list(xw.apps):
        try:
            for book in app.books:
                sheet = None
                try:
                    for sh in book.sheets:
                        if sh.name.strip().upper() == nama_sheet.upper():
                            sheet = sh
                            break
                except Exception:
                    pass
                hasil.append((app.pid, book.name, sheet))
        except Exception as e:
            hasil.append((getattr(app, "pid", "?"), "<tidak terbaca: {}>".format(e), None))
    return hasil


def baris_terakhir(sheet):
    api = sheet.api
    return int(api.Cells(api.Rows.Count, 1).End(-4162).Row)


def kolom_terakhir(sheet):
    api = sheet.api
    return int(api.Cells(1, api.Columns.Count).End(-4159).Column)


def baca_rentang(sheet, r1, r2, ncol):
    nilai = sheet.range((r1, 1), (r2, ncol)).options(ndim=2).value
    return nilai or []


def mode_cek(cfg, cat):
    xw = buka_xlwings()
    db = None
    try:
        db = Database(cfg["mysql"], cat)
        db.sambung()
        print("MySQL: tersambung ke {}@{}:{}/{}".format(cfg["mysql"]["user"], cfg["mysql"]["host"],
                                                      cfg["mysql"]["port"], cfg["mysql"]["database"]))
        print("Mesin terdaftar:")
        for m in db.mesin:
            print("   {}/{}  Base File Name: {}  pola: {}".format(m["kode"], m["nama"], m.get("base_file_name") or "(kosong)",
                                                                 m["pola_workbook"] or "(kosong)"))
    except Exception as e:
        print("MySQL: GAGAL tersambung: {}".format(e))
    print("\nWorkbook Excel yang terbuka:")
    daftar = daftar_workbook(xw, cfg["sheet"])
    if not daftar:
        print("   (tidak ada Excel yang terbuka, atau Excel berjalan sebagai Administrator)")
    for pid, nama, sheet in daftar:
        if sheet is None:
            print("   [pid {}] {}  -> tidak ada sheet {}, diabaikan".format(pid, nama, cfg["sheet"]))
            continue
        try:
            akhir = baris_terakhir(sheet)
            ncol = kolom_terakhir(sheet)
            pertama = baca_rentang(sheet, 2, 2, ncol)[0] if akhir >= 2 else None
            judul = baca_rentang(sheet, 1, 1, ncol)[0]
            info = "{} baris data, {} kolom".format(max(akhir - 1, 0), ncol)
            if pertama:
                info += ", baris pertama {}".format(pertama[2] if len(pertama) > 2 else "?")
        except Exception as e:
            info = "tidak terbaca ({})".format(e)
            judul = []
        hasil = "MySQL belum tersambung"
        if db and db.mesin:
            m, ket = db.cocokkan(nama)
            hasil = "-> {}/{}".format(m["kode"], m["nama"]) if m else "-> TIDAK DIKENAL ({})".format(ket)
        print("   [pid {}] {}  sheet {}: {}  {}".format(pid, nama, cfg["sheet"], info, hasil))
        if db and db.kolom and judul:
            asing = [j for j in judul if j and nama_kolom(j) not in db.kolom]
            if asing:
                print("      kolom yang akan masuk ke 'lainnya': {}".format(", ".join(map(str, asing))))
    print("\nKalau ada workbook TIDAK DIKENAL, isi Base File Name unit itu di halaman Admin dashboard "
          "(awalan nama workbook, misalnya DOCS_500_Bandung).")
    return 0


class Pantau:
    def __init__(self, mesin):
        self.mesin = mesin
        self.tanda_awal = None
        self.sesi_id = None
        self.rec_terakhir = 0
        self.judul = None
        self.ncol = 0
        self.masuk_sejak_ringkasan = 0
        self.waktu_data = None
        self.data_terakhir_masuk = time.time()
        self.sudah_diperingatkan = False


def mode_jaga(cfg, cat):
    xw = buka_xlwings()
    db = Database(cfg["mysql"], cat)
    pantau = {}
    tak_dikenal = set()
    db_putus = False
    ringkasan_berikut = time.time() + cfg["ringkasan_menit"] * 60
    muat_ulang_berikut = time.time() + 300
    cat.tulis("MULAI", "cek tiap {} detik, sheet {}, database {}@{}:{}/{}".format(
        cfg["interval"], cfg["sheet"], cfg["mysql"]["user"], cfg["mysql"]["host"],
        cfg["mysql"]["port"], cfg["mysql"]["database"]))
    print("Biarkan jendela ini terbuka. Berhenti dengan Ctrl+C.")

    while True:
        t0 = time.time()
        try:
            db.sambung()
            if db_putus:
                cat.tulis("DB OK", "tersambung lagi ke MySQL")
                db_putus = False
            if time.time() >= muat_ulang_berikut:
                db.muat_meta()
                muat_ulang_berikut = time.time() + 300
                tak_dikenal.clear()
        except Exception as e:
            if not db_putus:
                cat.tulis("DB PUTUS", "tidak bisa tersambung ke MySQL: {}. Data tetap aman di Excel, "
                                      "akan dicoba lagi.".format(e))
                db_putus = True
            db.conn = None
            tidur(cfg["interval"], t0)
            continue

        try:
            daftar = daftar_workbook(xw, cfg["sheet"])
        except Exception as e:
            cat.tulis("EXCEL", "daftar workbook tidak terbaca: {}".format(e))
            tidur(cfg["interval"], t0)
            continue

        terlihat = set()
        for pid, nama, sheet in daftar:
            if sheet is None:
                continue
            kunci = (pid, nama)
            terlihat.add(kunci)
            p = pantau.get(kunci)
            if p is None:
                mesin, ket = db.cocokkan(nama)
                if not mesin:
                    if kunci not in tak_dikenal and nama.lower().startswith("book"):
                        tak_dikenal.add(kunci)
                    if kunci not in tak_dikenal:
                        cat.tulis("TAK DIKENAL", "workbook '{}' (pid {}): {}. Tidak dimasukkan.".format(nama, pid, ket))
                        tak_dikenal.add(kunci)
                    continue
                p = Pantau(mesin)
                pantau[kunci] = p
                cat.tulis("PANTAU", "workbook '{}' (pid {}) -> {}/{}".format(nama, pid, mesin["kode"], mesin["nama"]))
            try:
                proses_workbook(p, nama, sheet, db, cfg, cat)
            except Exception as e:
                pesan = str(e)
                if "-2147418111" in pesan or "Call was rejected" in pesan or "0x80010001" in pesan:
                    continue
                if isinstance(e, mysql.connector.Error):
                    cat.tulis("DB ERROR", "{}/{}: {}".format(p.mesin["kode"], p.mesin["nama"], pesan))
                    db.conn = None
                else:
                    cat.tulis("ERROR", "{}/{} '{}': {}".format(p.mesin["kode"], p.mesin["nama"], nama, pesan))

        for kunci in [k for k in pantau if k not in terlihat]:
            p = pantau.pop(kunci)
            cat.tulis("TUTUP", "workbook '{}' ({}/{}) tidak terbuka lagi".format(kunci[1], p.mesin["kode"], p.mesin["nama"]))

        try:
            db.heartbeat("{} workbook dipantau: {}".format(len(pantau), ", ".join(
                "{}/{}".format(p.mesin["kode"], p.mesin["nama"]) for p in pantau.values()) or "-"))
        except Exception as e:
            cat.tulis("DB ERROR", "heartbeat: {}".format(e))
            db.conn = None
        sekarang = time.time()
        for kunci, p in pantau.items():
            diam = (sekarang - p.data_terakhir_masuk) / 60
            if diam >= cfg["batas_diam_menit"] and not p.sudah_diperingatkan:
                cat.tulis("PERHATIAN", "{}/{}: tidak ada baris baru selama {:.0f} menit (data terakhir {})".format(
                    p.mesin["kode"], p.mesin["nama"], diam, p.waktu_data))
                p.sudah_diperingatkan = True
        if sekarang >= ringkasan_berikut:
            for kunci, p in pantau.items():
                cat.tulis("RINGKASAN", "{}/{}: +{} baris dalam {} menit, data terakhir {} (RecNo {})".format(
                    p.mesin["kode"], p.mesin["nama"], p.masuk_sejak_ringkasan, cfg["ringkasan_menit"],
                    p.waktu_data, p.rec_terakhir))
                p.masuk_sejak_ringkasan = 0
            ringkasan_berikut = sekarang + cfg["ringkasan_menit"] * 60
        tidur(cfg["interval"], t0)


def proses_workbook(p, nama, sheet, db, cfg, cat):
    akhir = baris_terakhir(sheet)
    if akhir < 3:
        return
    if p.judul is None:
        p.ncol = kolom_terakhir(sheet)
        p.judul = siapkan_judul(baca_rentang(sheet, 1, 1, p.ncol)[0])
        if "rec_no" not in p.judul or "waktu" not in p.judul:
            raise RuntimeError("judul kolom tidak memuat RecNo dan Date")
    baris_pertama = susun_baris(p.judul, baca_rentang(sheet, 2, 2, p.ncol)[0], db)
    if baris_pertama is None:
        return
    tanda = (baris_pertama["waktu"], baris_pertama.get("detik_unit"))
    if tanda != p.tanda_awal:
        p.sesi_id, p.rec_terakhir = db.sesi(p.mesin["id"], tanda[0], tanda[1] or 0, nama)
        p.tanda_awal = tanda
        cat.tulis("SESI", "{}/{}: sesi {} mulai {}, lanjut dari RecNo {}".format(
            p.mesin["kode"], p.mesin["nama"], p.sesi_id, tanda[0], p.rec_terakhir))
    batas = akhir - 1
    mulai = p.rec_terakhir + 2
    if mulai > batas:
        return
    for r1 in range(mulai, batas + 1, cfg["baris_per_baca"]):
        r2 = min(r1 + cfg["baris_per_baca"] - 1, batas)
        data = baca_rentang(sheet, r1, r2, p.ncol)
        baris = []
        for d in data:
            b = susun_baris(p.judul, d, db)
            if b is not None and b["rec_no"] > p.rec_terakhir:
                baris.append(b)
        if not baris:
            continue
        db.simpan(p.sesi_id, p.mesin["id"], baris)
        terakhir = max(baris, key=lambda b: b["rec_no"])
        p.rec_terakhir = terakhir["rec_no"]
        p.waktu_data = terakhir["waktu"]
        p.masuk_sejak_ringkasan += len(baris)
        p.data_terakhir_masuk = time.time()
        if p.sudah_diperingatkan:
            cat.tulis("PULIH", "{}/{}: baris baru masuk lagi (data {})".format(p.mesin["kode"], p.mesin["nama"], p.waktu_data))
            p.sudah_diperingatkan = False
        if r2 < batas:
            time.sleep(0.2)


def tidur(interval, t0):
    sisa = interval - (time.time() - t0)
    if sisa > 0:
        time.sleep(sisa)


def main():
    ap = argparse.ArgumentParser(description="Masukkan data DOCSApp (LOGDAT1) ke MySQL")
    ap.add_argument("--cek", action="store_true", help="hanya melihat workbook yang terbuka dan pencocokannya")
    ap.add_argument("--impor", metavar="FILE", help="masukkan file .xlsx DOCSApp yang sudah tersimpan")
    ap.add_argument("--mesin", metavar="KODE/NAMA", help="untuk --impor: misalnya BANDUNG/DOCS500")
    args = ap.parse_args()
    cfg = baca_pengaturan()
    cat = Catatan(os.path.join(FOLDER, "log"))
    try:
        if args.cek:
            return mode_cek(cfg, cat)
        if args.impor:
            return impor_file(args.impor, args.mesin, cfg, cat)
        return mode_jaga(cfg, cat)
    except KeyboardInterrupt:
        cat.tulis("BERHENTI", "dihentikan dengan Ctrl+C")
        return 0
    except Exception as e:
        cat.tulis("ERROR", "{}\n{}".format(e, traceback.format_exc()))
        return 1


if __name__ == "__main__":
    sys.exit(main())
