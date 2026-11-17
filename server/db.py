import configparser
import datetime as dt
import decimal
import os
import secrets
import threading

import mysql.connector
from mysql.connector import pooling

FOLDER = os.path.dirname(os.path.abspath(__file__))


def _bool(v):
    return str(v).strip().lower() in ("1", "ya", "yes", "true", "on", "aktif")


def baca_pengaturan():
    path = os.path.join(FOLDER, "pengaturan_dashboard.ini")
    if not os.path.exists(path):
        raise SystemExit("File pengaturan tidak ditemukan: " + path)
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    g = lambda s, k, d=None: cp.get(s, k, fallback=d)
    gi = lambda s, k, d: cp.getint(s, k, fallback=d)
    return {
        "mysql": dict(host=g("mysql", "host", "127.0.0.1"), port=gi("mysql", "port", 3306),
                      user=g("mysql", "user"), password=g("mysql", "password"),
                      database=g("mysql", "database", "gpi_monitoring_system")),
        "server": dict(host=g("server", "host", "0.0.0.0"), port=gi("server", "port", 8080),
                       alamat=g("server", "alamat_dashboard", "http://localhost:8080").rstrip("/"),
                       zona=g("server", "label_zona", "WIB")),
        "engine": dict(interval=gi("engine", "interval_detik", 5),
                       terlambat=gi("engine", "terlambat_detik", 60),
                       offline=gi("engine", "offline_detik", 300),
                       startup_menit=gi("engine", "startup_tahan_menit", 20),
                       ulang_kritis_menit=gi("engine", "ulang_kritis_menit", 30),
                       eskalasi_menit=gi("engine", "eskalasi_menit", 30),
                       bridge_mati_detik=gi("engine", "bridge_mati_detik", 60),
                       simpan_mentah_hari=gi("engine", "simpan_mentah_hari", 90),
                       simpan_agregat_hari=gi("engine", "simpan_agregat_hari", 730),
                       jam_retensi=gi("engine", "jam_retensi", 2)),
        "notif": dict(aktif=_bool(g("notifikasi", "aktif", "tidak")),
                      smtp_host=g("notifikasi", "smtp_host", ""), smtp_port=gi("notifikasi", "smtp_port", 587),
                      smtp_user=g("notifikasi", "smtp_user", ""), smtp_password=g("notifikasi", "smtp_password", ""),
                      smtp_dari=g("notifikasi", "smtp_dari", ""),
                      smtp_tls=_bool(g("notifikasi", "smtp_tls", "ya")),
                      telegram_token=g("notifikasi", "telegram_bot_token", "")),
    }


def kunci_rahasia():
    path = os.path.join(FOLDER, ".kunci_sesi")
    if os.path.exists(path):
        with open(path, "r", encoding="ascii") as f:
            k = f.read().strip()
            if len(k) >= 32:
                return k
    k = secrets.token_hex(32)
    with open(path, "w", encoding="ascii") as f:
        f.write(k)
    return k


def bersih(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        s = int(v.total_seconds())
        return "{:02d}:{:02d}".format(s // 3600, (s % 3600) // 60)
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


def bersih_baris(r):
    return {k: bersih(v) for k, v in r.items()} if r else r


def pesan_galat_koneksi(e, cfg):
    u, db = cfg.get("user"), cfg.get("database")
    if e.errno == 1045:
        return ("\nLOGIN MYSQL DITOLAK untuk user '{0}'.\n"
                "Password di server\\pengaturan_dashboard.ini tidak sama dengan password user '{0}' di MySQL,\n"
                "atau user '{0}' belum dibuat. Di MySQL Workbench (akun DBA) jalankan:\n"
                "  SELECT user, host FROM mysql.user WHERE user = '{0}';\n"
                "  - kosong  -> jalankan database\\02_skema_dashboard.sql (password-nya samakan dengan file .ini)\n"
                "  - ada     -> ALTER USER '{0}'@'localhost' IDENTIFIED BY 'password_yang_sama_dengan_ini';\n".format(u))
    if e.errno == 1049:
        return "\nDatabase '{}' tidak ditemukan. Cek baris database di pengaturan_dashboard.ini.\n".format(db)
    if e.errno in (2003, 2005):
        return ("\nTidak bisa menghubungi MySQL di {}:{}. Pastikan service MySQL84 berjalan "
                "(services.msc).\n".format(cfg.get("host"), cfg.get("port")))
    return "\nGagal tersambung ke MySQL: {}\n".format(e)


class Database:
    def __init__(self, cfg, ukuran_pool=12):
        self.cfg = cfg
        self._kunci = threading.Lock()
        try:
            self.pool = pooling.MySQLConnectionPool(pool_name="gpi_dashboard", pool_size=ukuran_pool,
                                                    pool_reset_session=True, autocommit=True, **cfg)
        except mysql.connector.Error as e:
            raise SystemExit(pesan_galat_koneksi(e, cfg)) from None

    def _sambung(self):
        conn = self.pool.get_connection()
        try:
            conn.ping(reconnect=True, attempts=2, delay=1)
        except Exception:
            pass
        return conn

    def kueri(self, sql, args=(), satu=False):
        conn = self._sambung()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, args)
            hasil = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        if satu:
            return hasil[0] if hasil else None
        return hasil

    def nilai(self, sql, args=()):
        r = self.kueri(sql, args, satu=True)
        return None if r is None else list(r.values())[0]

    def jalankan(self, sql, args=()):
        conn = self._sambung()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            hasil = cur.lastrowid or cur.rowcount
            cur.close()
            conn.commit()
        finally:
            conn.close()
        return hasil

    def sekarang(self):
        return self.nilai("SELECT NOW()")


def buka_koneksi_tunggal(cfg):
    return mysql.connector.connect(autocommit=True, connection_timeout=10, **cfg)
