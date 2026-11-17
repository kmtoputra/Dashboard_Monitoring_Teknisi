import csv
import datetime as dt
import functools
import io
import json
import logging
import math
import os
import re
import secrets
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

FOLDER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FOLDER)

from flask import (Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import Database, baca_pengaturan, bersih, buka_koneksi_tunggal, kunci_rahasia
from engine import KOLOM, LABEL, PARAMETER, SATUAN, URUTAN_STATUS, Engine, kondisi, pilih_aturan
from notifikasi import Notifier

VERSI = "1.2.2"
SUMBER_DEFAULT = {"purity": "terbaru", "rt1": "avg1m", "fvsa": "avg1m", "fbst": "avg1m", "purge": "terbaru"}
TREN_PEKA = {"purity": 0.2, "rt1": 2.0, "fvsa": 0.5, "fbst": 0.5, "purge": 2.0}
RENTANG = {"1j": 3600, "6j": 6 * 3600, "24j": 86400, "7h": 7 * 86400}
EPOCH = dt.datetime(1970, 1, 1)

os.makedirs(os.path.join(FOLDER, "log"), exist_ok=True)
_logger = logging.getLogger("gpi")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_h = RotatingFileHandler(os.path.join(FOLDER, "log", "dashboard.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
_logger.addHandler(_h)


def log(pesan):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), pesan, flush=True)
    _logger.info(pesan)


cfg = baca_pengaturan()
db = Database(cfg["mysql"])
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = kunci_rahasia()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=12), JSON_SORT_KEYS=False,
                  SEND_FILE_MAX_AGE_DEFAULT=3600, TEMPLATES_AUTO_RELOAD=True)
latar = {"engine": None, "notifier": None, "mulai": dt.datetime.now()}


_aset = {"t": 0.0, "v": None}


def versi_aset():
    if time.time() - _aset["t"] > 10 or not _aset["v"]:
        m = 0.0
        for akar in (os.path.join(FOLDER, "static"), os.path.join(FOLDER, "templates")):
            for r, _, berkas in os.walk(akar):
                for b in berkas:
                    try:
                        m = max(m, os.path.getmtime(os.path.join(r, b)))
                    except OSError:
                        pass
        _aset["v"] = "{}-{}".format(VERSI, int(m))
        _aset["t"] = time.time()
    return _aset["v"]


@app.context_processor
def _konteks_template():
    return {"aset": versi_aset()}


class Galat(Exception):
    pass


@app.errorhandler(Galat)
def _galat(e):
    return jsonify(galat=str(e)), 400


def jawab(obj, kode=200):
    return app.response_class(json.dumps(obj, default=bersih, ensure_ascii=False), status=kode,
                              mimetype="application/json")


def ep(t):
    return None if t is None else int((t - EPOCH).total_seconds())


def f(x):
    return None if x is None else float(x)


@app.after_request
def _header_keamanan(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "SAMEORIGIN"
    r.headers["Referrer-Policy"] = "same-origin"
    r.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; media-src 'self' data: blob:; "
                                            "style-src 'self' 'unsafe-inline'; "
                                            "script-src 'self'; connect-src 'self'; frame-ancestors 'self'")
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
        r.headers["X-GPI-Versi"] = versi_aset()
    return r


_cache_pengguna = {}
_gagal_login = {}
_kunci_login = threading.Lock()


def pengguna_sekarang():
    uid = session.get("uid")
    if not uid:
        return None
    c = _cache_pengguna.get(uid)
    if c and time.time() - c[0] < 30:
        return c[1]
    u = db.kueri("SELECT id, username, nama, peran, aktif FROM pengguna WHERE id = %s", (uid,), satu=True)
    if not u or not u["aktif"]:
        session.clear()
        return None
    _cache_pengguna[uid] = (time.time(), u)
    return u


def wajib(*peran):
    def dekorator(fungsi):
        @functools.wraps(fungsi)
        def bungkus(*a, **k):
            api = request.path.startswith("/api/")
            u = pengguna_sekarang()
            if not u:
                if api:
                    return jsonify(galat="Sesi berakhir, silakan login lagi"), 401
                return redirect(url_for("login", lanjut=request.path))
            if peran and u["peran"] not in peran:
                if api:
                    return jsonify(galat="Akses ditolak untuk peran {}".format(u["peran"])), 403
                abort(403)
            if api and request.method != "GET" and request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return jsonify(galat="Permintaan ditolak"), 403
            return fungsi(*a, **k)
        return bungkus
    return dekorator


def catat_audit(aksi, objek, lama=None, baru=None):
    u = pengguna_sekarang()
    db.jalankan("INSERT INTO audit (waktu, pengguna, aksi, objek, nilai_lama, nilai_baru) VALUES (NOW(),%s,%s,%s,%s,%s)",
                (u["username"] if u else "-", aksi, objek[:80],
                 None if lama is None else json.dumps(lama, default=bersih, ensure_ascii=False),
                 None if baru is None else json.dumps(baru, default=bersih, ensure_ascii=False)))


def _ip():
    return request.remote_addr or "-"


@app.route("/login", methods=["GET", "POST"])
def login():
    lanjut = request.values.get("lanjut") or "/"
    if not lanjut.startswith("/") or lanjut.startswith("//"):
        lanjut = "/"
    pesan = None
    if request.method == "POST":
        ip = _ip()
        with _kunci_login:
            daftar = [t for t in _gagal_login.get(ip, []) if time.time() - t < 600]
            _gagal_login[ip] = daftar
        if request.form.get("csrf") != session.get("csrf_login"):
            pesan = "Formulir kedaluwarsa, silakan coba lagi."
        elif len(daftar) >= 5:
            pesan = "Terlalu banyak percobaan gagal. Tunggu 10 menit."
        else:
            username = (request.form.get("username") or "").strip().lower()
            pw = request.form.get("password") or ""
            u = db.kueri("SELECT * FROM pengguna WHERE username = %s AND aktif = 1", (username,), satu=True)
            if u and check_password_hash(u["password_hash"], pw):
                session.clear()
                session.permanent = True
                session["uid"] = u["id"]
                db.jalankan("UPDATE pengguna SET login_terakhir = NOW() WHERE id = %s", (u["id"],))
                log("LOGIN {} ({}) dari {}".format(u["username"], u["peran"], ip))
                return redirect(lanjut)
            with _kunci_login:
                _gagal_login.setdefault(ip, []).append(time.time())
            log("LOGIN GAGAL '{}' dari {}".format(username, ip))
            pesan = "Username atau password salah."
    session["csrf_login"] = secrets.token_urlsafe(24)
    return render_template("login.html", csrf=session["csrf_login"], lanjut=lanjut, pesan=pesan, versi=VERSI)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _halaman(nama, **k):
    u = pengguna_sekarang()
    return render_template(nama + ".html", pengguna=u, zona=cfg["server"]["zona"], versi=VERSI,
                           notif_aktif=cfg["notif"]["aktif"], **k)


@app.route("/")
@wajib()
def halaman_ringkasan():
    return _halaman("ringkasan", halaman="ringkasan")


@app.route("/unit/<int:mid>")
@wajib()
def halaman_detail(mid):
    if not db.nilai("SELECT COUNT(*) FROM mesin WHERE id = %s", (mid,)):
        abort(404)
    return _halaman("detail", halaman="detail", mesin_id=mid)


@app.route("/alarm")
@wajib()
def halaman_alarm():
    return _halaman("alarm", halaman="alarm")


@app.route("/tv")
@wajib()
def halaman_tv():
    return _halaman("tv", halaman="tv")


@app.route("/admin")
@wajib("Admin")
def halaman_admin():
    return _halaman("admin", halaman="admin")


@app.route("/akun")
@wajib()
def halaman_akun():
    return _halaman("akun", halaman="akun")


@app.errorhandler(403)
def _e403(e):
    return render_template("pesan.html", judul="Akses ditolak", isi="Peran akun Anda tidak boleh membuka halaman ini."), 403


@app.errorhandler(404)
def _e404(e):
    if request.path.startswith("/api/"):
        return jsonify(galat="Tidak ditemukan"), 404
    return render_template("pesan.html", judul="Halaman tidak ditemukan", isi="Periksa kembali alamatnya."), 404


def _aturan_semua():
    return db.kueri("SELECT * FROM aturan_alarm")


def _nilai(mid, t):
    akhir = db.kueri("SELECT waktu, avgpur, rtd_1, fvsa, fbst, purgeest, state, flow_est, ps1, cyccnt, vsacmd "
                     "FROM telemetri WHERE mesin_id = %s AND waktu <= %s ORDER BY waktu DESC, rec_no DESC LIMIT 1",
                     (mid, t), satu=True) or {}
    j = db.kueri("SELECT AVG(avgpur) a_purity, MAX(avgpur) m_purity, AVG(rtd_1) a_rt1, MAX(rtd_1) m_rt1, "
                 "AVG(fvsa) a_fvsa, MAX(fvsa) m_fvsa, AVG(fbst) a_fbst, MAX(fbst) m_fbst, "
                 "AVG(purgeest) a_purge, MAX(purgeest) m_purge FROM telemetri "
                 "WHERE mesin_id = %s AND waktu > %s - INTERVAL 60 SECOND AND waktu <= %s", (mid, t, t), satu=True) or {}
    v = {"terbaru": {p: f(akhir.get(KOLOM[p])) for p in PARAMETER},
         "avg": {p: f(j.get("a_" + p)) for p in PARAMETER},
         "max": {p: f(j.get("m_" + p)) for p in PARAMETER}}
    lain = {k: bersih(akhir.get(k)) for k in ("state", "flow_est", "ps1", "cyccnt", "vsacmd")}
    return v, lain


def _tampil(v, aturan):
    nilai, level, teks = {}, {}, {}
    for p in PARAMETER:
        a = aturan.get(p)
        sumber = a.sumber if a else SUMBER_DEFAULT[p]
        nilai[p] = v["terbaru"][p] if sumber == "terbaru" else v["avg"][p]
        level[p], teks[p] = None, ""
        if a and nilai[p] is not None:
            k = kondisi(a, v)
            if k:
                level[p], teks[p] = k[0], k[3]
    return nilai, level, teks


def _aturan_json(a):
    if not a:
        return None
    return {k: getattr(a, k) for k in ("id", "sumber", "normal_min", "normal_max", "maks1m_max", "kritis_min",
                                       "kritis_max", "syarat_vsa", "delay_p", "delay_k", "pulih", "pulih_min",
                                       "naik_menit")}


def _sistem(sekarang):
    hb = {r["nama"]: r for r in db.kueri("SELECT nama, waktu, info FROM heartbeat")}
    batas = cfg["engine"]["bridge_mati_detik"]
    b = hb.get("bridge")
    d = hb.get("dashboard")
    umur_b = None if not b else (sekarang - b["waktu"]).total_seconds()
    umur_d = None if not d else (sekarang - d["waktu"]).total_seconds()
    return {"bridge": {"waktu": b and b["waktu"], "umur": umur_b, "info": b and b["info"],
                       "hidup": None if b is None else umur_b <= batas},
            "mesin_alarm": {"waktu": d and d["waktu"], "umur": umur_d,
                            "hidup": d is not None and umur_d <= cfg["engine"]["interval"] * 3 + 15},
            "notifikasi_aktif": cfg["notif"]["aktif"]}


_cache_ringkasan = {"t": 0, "isi": None}
_kunci_ringkasan = threading.Lock()


def hapus_cache():
    _cache_ringkasan["t"] = 0


def _hitung_ringkasan():
    sekarang = db.sekarang()
    aturan_semua = _aturan_semua()
    unit = db.kueri(
        "SELECT m.id, m.kode_unit, m.nama, m.jenis_mesin, m.status AS status_mesin, l.kode AS kode_lokasi, "
        "l.nama_rs, l.kota, l.zona_waktu, s.status, s.sejak, s.startup_sampai, s.data_terakhir "
        "FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id LEFT JOIN status_unit s ON s.mesin_id = m.id "
        "WHERE l.aktif = 1 ORDER BY l.id, m.id")
    alarm = {r["mesin_id"]: r for r in db.kueri(
        "SELECT mesin_id, COUNT(*) aktif, SUM(ack_waktu IS NULL) belum_ack, SUM(level = 'Kritis') kritis, "
        "SUM(level = 'Kritis' AND ack_waktu IS NULL) kritis_belum_ack, "
        "SUM(level = 'Peringatan' AND ack_waktu IS NULL) peringatan_belum_ack, "
        "SUM(level = 'Offline' AND ack_waktu IS NULL) offline_belum_ack "
        "FROM event_alarm WHERE selesai IS NULL GROUP BY mesin_id")}
    hasil, nonaktif = [], []
    hitung = {s: 0 for s in URUTAN_STATUS}
    for u in unit:
        if u["status_mesin"] == "Nonaktif":
            nonaktif.append({k: u[k] for k in ("id", "kode_unit", "nama_rs", "kota", "jenis_mesin", "kode_lokasi")})
            continue
        status = u["status"] or "Offline"
        hitung[status] = hitung.get(status, 0) + 1
        data_terakhir = db.nilai("SELECT MAX(waktu_terakhir) FROM sesi_log WHERE mesin_id = %s", (u["id"],))
        aturan = pilih_aturan(aturan_semua, u)
        if data_terakhir:
            v, _ = _nilai(u["id"], data_terakhir)
            nilai, level, teks = _tampil(v, aturan)
        else:
            nilai, level, teks = {p: None for p in PARAMETER}, {p: None for p in PARAMETER}, {p: "" for p in PARAMETER}
        spark = db.kueri("SELECT menit, purity_avg FROM agregat_1menit WHERE mesin_id = %s AND menit >= %s "
                         "ORDER BY menit", (u["id"], sekarang - dt.timedelta(minutes=60)))
        a = alarm.get(u["id"]) or {}
        pa = aturan.get("purity")
        hasil.append({
            "id": u["id"], "kode_unit": u["kode_unit"], "nama": u["nama"], "jenis_mesin": u["jenis_mesin"],
            "kode_lokasi": u["kode_lokasi"], "nama_rs": u["nama_rs"], "kota": u["kota"],
            "status": status, "sejak": u["sejak"], "status_mesin": u["status_mesin"],
            "startup_sampai": u["startup_sampai"] if status == "Start-up" else None,
            "data_terakhir": data_terakhir,
            "umur_detik": None if data_terakhir is None else int((sekarang - data_terakhir).total_seconds()),
            "nilai": nilai, "level": level, "teks": teks,
            "spark": [[ep(r["menit"]), f(r["purity_avg"])] for r in spark],
            "batas_purity": {"normal_min": pa.normal_min, "kritis_min": pa.kritis_min} if pa else None,
            "alarm": {"aktif": int(a.get("aktif") or 0), "belum_ack": int(a.get("belum_ack") or 0),
                      "kritis": int(a.get("kritis") or 0), "kritis_belum_ack": int(a.get("kritis_belum_ack") or 0),
                      "peringatan_belum_ack": int(a.get("peringatan_belum_ack") or 0),
                      "offline_belum_ack": int(a.get("offline_belum_ack") or 0)},
            "ada_aturan": bool(aturan),
        })
    hasil.sort(key=lambda x: (URUTAN_STATUS.index(x["status"]) if x["status"] in URUTAN_STATUS else 9,
                              x["nama_rs"] or x["kode_lokasi"] or ""))
    return {"sekarang": sekarang, "sekarang_ep": ep(sekarang), "zona": cfg["server"]["zona"],
            "hitung": hitung, "unit": hasil, "nonaktif": nonaktif, "sistem": _sistem(sekarang)}


@app.get("/api/ringkasan")
@wajib()
def api_ringkasan():
    with _kunci_ringkasan:
        if time.time() - _cache_ringkasan["t"] > 3 or _cache_ringkasan["isi"] is None:
            _cache_ringkasan["isi"] = json.dumps(_hitung_ringkasan(), default=bersih, ensure_ascii=False)
            _cache_ringkasan["t"] = time.time()
        isi = _cache_ringkasan["isi"]
    return app.response_class(isi, mimetype="application/json")


def _unit(mid):
    u = db.kueri("SELECT m.*, m.status AS status_mesin, l.kode AS kode_lokasi, l.nama_rs, l.kota, l.provinsi, "
                 "l.zona_waktu FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id WHERE m.id = %s", (mid,), satu=True)
    if not u:
        abort(404)
    return u


@app.get("/api/unit/<int:mid>")
@wajib()
def api_unit(mid):
    u = _unit(mid)
    sekarang = db.sekarang()
    st = db.kueri("SELECT * FROM status_unit WHERE mesin_id = %s", (mid,), satu=True) or {}
    aturan = pilih_aturan(_aturan_semua(), u)
    data_terakhir = db.nilai("SELECT MAX(waktu_terakhir) FROM sesi_log WHERE mesin_id = %s", (mid,))
    nilai, level, teks, lain, tren = {}, {}, {}, {}, {}
    if data_terakhir:
        v, lain = _nilai(mid, data_terakhir)
        nilai, level, teks = _tampil(v, aturan)
        dulu = db.kueri("SELECT * FROM agregat_1menit WHERE mesin_id = %s AND menit <= %s AND menit >= %s "
                        "ORDER BY menit DESC LIMIT 1",
                        (mid, data_terakhir - dt.timedelta(minutes=5), data_terakhir - dt.timedelta(minutes=10)), satu=True)
        for p in PARAMETER:
            lama = f(dulu.get(p + "_avg")) if dulu else None
            if nilai.get(p) is None or lama is None:
                tren[p] = None
            elif nilai[p] - lama > TREN_PEKA[p]:
                tren[p] = "naik"
            elif lama - nilai[p] > TREN_PEKA[p]:
                tren[p] = "turun"
            else:
                tren[p] = "datar"
    sesi = db.kueri("SELECT nama_sumber, rec_no_terakhir FROM sesi_log WHERE mesin_id = %s "
                    "ORDER BY waktu_terakhir DESC LIMIT 1", (mid,), satu=True)
    return jawab({
        "sekarang": sekarang, "zona": cfg["server"]["zona"],
        "unit": {k: u.get(k) for k in ("id", "kode_unit", "nama", "jenis_mesin", "base_file_name", "router",
                                       "status_mesin", "kode_lokasi", "nama_rs", "kota", "provinsi", "zona_waktu")},
        "status": st.get("status") or ("Nonaktif" if u["status_mesin"] == "Nonaktif" else "Offline"),
        "sejak": st.get("sejak"), "startup_sampai": st.get("startup_sampai"),
        "data_terakhir": data_terakhir,
        "umur_detik": None if data_terakhir is None else int((sekarang - data_terakhir).total_seconds()),
        "nilai": nilai, "level": level, "teks": teks, "tren": tren, "lain": lain,
        "aturan": {p: _aturan_json(aturan.get(p)) for p in PARAMETER},
        "label": LABEL, "satuan": SATUAN,
        "sesi": sesi,
        "alarm_aktif": _alarm(mesin_id=mid, aktif=True),
    })


def _rentang():
    r = request.args.get("rentang", "1j")
    if r == "custom":
        try:
            dari = dt.datetime.strptime(request.args.get("dari", ""), "%Y-%m-%dT%H:%M")
            sampai = dt.datetime.strptime(request.args.get("sampai", ""), "%Y-%m-%dT%H:%M")
        except ValueError:
            raise Galat("Format tanggal salah")
        if sampai <= dari:
            raise Galat("Waktu akhir harus setelah waktu mulai")
        if (sampai - dari).days > 92:
            raise Galat("Rentang maksimal 92 hari")
        return r, dari, sampai
    sampai = db.sekarang()
    return r, sampai - dt.timedelta(seconds=RENTANG.get(r, 3600)), sampai


def _sisip_celah(t, seri, celah):
    if not t:
        return t, seri
    t2, s2 = [t[0]], {k: [v[0]] for k, v in seri.items()}
    for i in range(1, len(t)):
        if t[i] - t[i - 1] > celah:
            t2.append(t[i - 1] + 1)
            for k in s2:
                s2[k].append(None)
        t2.append(t[i])
        for k in s2:
            s2[k].append(seri[k][i])
    return t2, s2


@app.get("/api/unit/<int:mid>/tren")
@wajib()
def api_tren(mid):
    u = _unit(mid)
    r, dari, sampai = _rentang()
    detik = (sampai - dari).total_seconds()
    if detik <= 3700:
        rows = db.kueri("SELECT waktu, avgpur, rtd_1, fvsa, fbst, purgeest FROM telemetri WHERE mesin_id = %s "
                        "AND waktu >= %s AND waktu <= %s ORDER BY waktu, rec_no", (mid, dari, sampai))
        t = [ep(x["waktu"]) for x in rows]
        seri = {p: [f(x[KOLOM[p]]) for x in rows] for p in PARAMETER}
        mode, langkah = "mentah", 1
        t, seri = _sisip_celah(t, seri, 30)
    else:
        langkah = max(1, math.ceil(detik / 60 / 2500))
        kol = ", ".join("AVG({0}_avg) {0}_avg, MIN({0}_min) {0}_min, MAX({0}_max) {0}_max".format(p) for p in PARAMETER)
        rows = db.kueri("SELECT FLOOR(TIMESTAMPDIFF(MINUTE, %s, menit) / %s) k, MIN(menit) menit, {} FROM agregat_1menit "
                        "WHERE mesin_id = %s AND menit >= %s AND menit <= %s GROUP BY k ORDER BY k".format(kol),
                        (dari, langkah, mid, dari, sampai))
        t = [ep(x["menit"]) for x in rows]
        seri = {}
        for p in PARAMETER:
            for s in ("avg", "min", "max"):
                seri[p + "_" + s] = [f(x[p + "_" + s]) for x in rows]
        mode = "agregat"
        t, seri = _sisip_celah(t, seri, langkah * 60 * 3)
    aturan = pilih_aturan(_aturan_semua(), u)
    return jawab({"mode": mode, "langkah_menit": langkah, "dari": ep(dari), "sampai": ep(sampai), "t": t, "seri": seri,
                  "aturan": {p: _aturan_json(aturan.get(p)) for p in PARAMETER}})


@app.get("/api/unit/<int:mid>/timeline")
@wajib()
def api_timeline(mid):
    _unit(mid)
    jam = min(max(int(request.args.get("jam", 24)), 1), 24 * 7)
    sampai = db.sekarang()
    dari = sampai - dt.timedelta(hours=jam)
    rows = db.kueri("SELECT status, mulai, selesai FROM riwayat_status WHERE mesin_id = %s AND mulai < %s "
                    "AND (selesai IS NULL OR selesai > %s) ORDER BY mulai", (mid, sampai, dari))
    seg = [{"status": x["status"], "mulai": ep(max(x["mulai"], dari)), "selesai": ep(min(x["selesai"] or sampai, sampai))}
           for x in rows]
    return jawab({"dari": ep(dari), "sampai": ep(sampai), "segmen": seg})


def _alarm(mesin_id=None, aktif=None, level=None, dari=None, sampai=None, batas=200, mulai_dari=0):
    w, a = [], []
    if mesin_id:
        w.append("e.mesin_id = %s")
        a.append(mesin_id)
    if aktif is True:
        w.append("e.selesai IS NULL")
    elif aktif is False:
        w.append("e.selesai IS NOT NULL")
    if level:
        w.append("e.level = %s")
        a.append(level)
    if dari:
        w.append("e.mulai >= %s")
        a.append(dari)
    if sampai:
        w.append("e.mulai < %s")
        a.append(sampai)
    sql = ("SELECT e.*, m.kode_unit, m.jenis_mesin, l.nama_rs, l.kota, l.kode AS kode_lokasi FROM event_alarm e "
           "JOIN mesin m ON m.id = e.mesin_id JOIN lokasi l ON l.id = m.lokasi_id {} "
           "ORDER BY (e.selesai IS NULL) DESC, FIELD(e.level, 'Kritis', 'Offline', 'Peringatan'), e.mulai DESC "
           "LIMIT %s OFFSET %s").format(("WHERE " + " AND ".join(w)) if w else "")
    rows = db.kueri(sql, a + [batas, mulai_dari])
    for r in rows:
        r["label"] = LABEL.get(r["parameter"], r["parameter"])
        r["satuan"] = SATUAN.get(r["parameter"], "")
    return rows


@app.get("/api/alarm")
@wajib()
def api_alarm():
    q = request.args
    status = q.get("status", "semua")
    dari = q.get("dari") or None
    sampai = q.get("sampai") or None
    try:
        dari = dt.datetime.strptime(dari, "%Y-%m-%d") if dari else None
        sampai = dt.datetime.strptime(sampai, "%Y-%m-%d") + dt.timedelta(days=1) if sampai else None
    except ValueError:
        raise Galat("Format tanggal salah")
    rows = _alarm(mesin_id=int(q["mesin_id"]) if q.get("mesin_id") else None,
                  aktif=True if status == "aktif" else (False if status == "selesai" else None),
                  level=q.get("level") or None, dari=dari, sampai=sampai,
                  batas=min(int(q.get("batas", 100)), 500), mulai_dari=int(q.get("mulai_dari", 0)))
    return jawab({"sekarang": db.sekarang(), "alarm": rows})


@app.post("/api/alarm/<int:eid>/ack")
@wajib("Admin", "Teknisi")
def api_ack(eid):
    d = request.get_json(silent=True) or {}
    catatan = (d.get("catatan") or "").strip()[:500]
    ev = db.kueri("SELECT * FROM event_alarm WHERE id = %s", (eid,), satu=True)
    if not ev:
        abort(404)
    if ev["ack_waktu"]:
        raise Galat("Alarm ini sudah di-ack oleh {} pada {}".format(ev["ack_oleh"], ev["ack_waktu"].strftime("%d/%m %H:%M")))
    u = pengguna_sekarang()
    db.jalankan("UPDATE event_alarm SET ack_oleh = %s, ack_waktu = NOW(), catatan = %s WHERE id = %s",
                (u["username"], catatan or None, eid))
    catat_audit("ack alarm", "event #{}".format(eid), None, {"catatan": catatan})
    hapus_cache()
    return jawab({"ok": True})


@app.post("/api/unit/<int:mid>/maintenance")
@wajib("Admin", "Teknisi")
def api_maintenance(mid):
    u = _unit(mid)
    if u["status_mesin"] == "Nonaktif":
        raise Galat("Unit Nonaktif tidak bisa diubah ke Maintenance. Aktifkan dulu di Admin.")
    d = request.get_json(silent=True) or {}
    baru = "Maintenance" if d.get("aktif") else "Aktif"
    if baru != u["status_mesin"]:
        db.jalankan("UPDATE mesin SET status = %s WHERE id = %s", (baru, mid))
        catat_audit("mode maintenance", u["kode_unit"] or "mesin #{}".format(mid), {"status": u["status_mesin"]},
                    {"status": baru, "catatan": (d.get("catatan") or "")[:200]})
        hapus_cache()
    return jawab({"ok": True, "status_mesin": baru})


@app.get("/api/unit/<int:mid>/ekspor")
@wajib()
def api_ekspor(mid):
    u = _unit(mid)
    r, dari, sampai = _rentang()
    fmt = request.args.get("format", "xlsx")
    mentah = (sampai - dari).total_seconds() <= 3 * 86400
    if mentah:
        judul = ["Waktu", "RecNo", "Purity (AVGPUR) %", "RT1 (RTD-1) °F", "Fvsa Hz", "Booster (Fbst) Hz", "PurgEst",
                 "State", "Flow Est"]
        rows = db.kueri("SELECT waktu, rec_no, avgpur, rtd_1, fvsa, fbst, purgeest, state, flow_est FROM telemetri "
                        "WHERE mesin_id = %s AND waktu >= %s AND waktu <= %s ORDER BY waktu, rec_no", (mid, dari, sampai))
        isi = [[x["waktu"], x["rec_no"], f(x["avgpur"]), f(x["rtd_1"]), f(x["fvsa"]), f(x["fbst"]), f(x["purgeest"]),
                x["state"], f(x["flow_est"])] for x in rows]
    else:
        judul = ["Menit", "Jumlah baris"] + ["{} {}".format(LABEL[p], s) for p in PARAMETER for s in ("rata2", "min", "maks")]
        kol = ", ".join("{0}_avg, {0}_min, {0}_max".format(p) for p in PARAMETER)
        rows = db.kueri("SELECT menit, n, {} FROM agregat_1menit WHERE mesin_id = %s AND menit >= %s AND menit <= %s "
                        "ORDER BY menit".format(kol), (mid, dari, sampai))
        isi = [[x["menit"], x["n"]] + [f(x["{}_{}".format(p, s)]) for p in PARAMETER for s in ("avg", "min", "max")]
               for x in rows]
    nama = "{}_{}_{}".format(u["kode_unit"] or "unit{}".format(mid), dari.strftime("%Y%m%d-%H%M"), sampai.strftime("%Y%m%d-%H%M"))
    catat_audit("ekspor data", u["kode_unit"] or str(mid), None, {"format": fmt, "baris": len(isi),
                                                                   "dari": dari, "sampai": sampai})
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(judul)
        for b in isi:
            w.writerow([x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, dt.datetime)
                        else (str(x).replace(".", ",") if isinstance(x, float) else ("" if x is None else x)) for x in b])
        data = io.BytesIO(("﻿" + buf.getvalue()).encode("utf-8"))
        return send_file(data, mimetype="text/csv", as_attachment=True, download_name=nama + ".csv")
    from openpyxl import Workbook
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Data" if mentah else "Agregat 1 menit")
    ws.append(["{} – {} {} ({})".format(u["nama_rs"] or u["kode_lokasi"], u["kota"] or "", u["jenis_mesin"], u["kode_unit"])])
    ws.append(["Periode {} s.d. {} ({})".format(dari.strftime("%d/%m/%Y %H:%M"), sampai.strftime("%d/%m/%Y %H:%M"),
                                                cfg["server"]["zona"])])
    ws.append([])
    ws.append(judul)
    for b in isi:
        ws.append(b)
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    return send_file(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=nama + ".xlsx")


@app.post("/api/akun/password")
@wajib()
def api_ganti_password():
    d = request.get_json(silent=True) or {}
    u = pengguna_sekarang()
    row = db.kueri("SELECT password_hash FROM pengguna WHERE id = %s", (u["id"],), satu=True)
    if not check_password_hash(row["password_hash"], d.get("lama") or ""):
        raise Galat("Password lama salah")
    baru = d.get("baru") or ""
    if len(baru) < 8:
        raise Galat("Password baru minimal 8 karakter")
    db.jalankan("UPDATE pengguna SET password_hash = %s WHERE id = %s", (generate_password_hash(baru), u["id"]))
    catat_audit("ganti password", u["username"])
    return jawab({"ok": True})


def _teks(d, k, maks, wajib_isi=False, label=None):
    v = d.get(k)
    v = "" if v is None else str(v).strip()
    if wajib_isi and not v:
        raise Galat("{} wajib diisi".format(label or k))
    if len(v) > maks:
        raise Galat("{} maksimal {} karakter".format(label or k, maks))
    return v or None


def _angka(d, k, label=None, minimum=None, maksimum=None, bulat=False):
    v = d.get(k)
    if v is None or str(v).strip() == "":
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise Galat("{} harus angka".format(label or k))
    if minimum is not None and x < minimum or maksimum is not None and x > maksimum:
        raise Galat("{} harus di antara {} dan {}".format(label or k, minimum, maksimum))
    return int(round(x)) if bulat else round(x, 2)


def _bendera(d, k):
    return 1 if d.get(k) in (True, 1, "1", "on", "ya", "true") else 0


@app.get("/api/admin/master")
@wajib("Admin")
def api_master():
    lokasi = db.kueri("SELECT * FROM lokasi ORDER BY id")
    mesin = db.kueri("SELECT m.*, l.kode AS kode_lokasi, l.nama_rs, s.status AS status_live, s.data_terakhir "
                     "FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id LEFT JOIN status_unit s ON s.mesin_id = m.id "
                     "ORDER BY l.id, m.id")
    jenis = sorted({m["jenis_mesin"] for m in mesin if m["jenis_mesin"]} |
                   {r["jenis_mesin"] for r in db.kueri("SELECT DISTINCT jenis_mesin FROM aturan_alarm "
                                                       "WHERE jenis_mesin IS NOT NULL")})
    return jawab({"lokasi": lokasi, "mesin": mesin, "jenis": jenis})


@app.post("/api/admin/lokasi")
@wajib("Admin")
def api_lokasi_simpan():
    d = request.get_json(silent=True) or {}
    lid = d.get("id")
    data = {"nama_rs": _teks(d, "nama_rs", 100, True, "Nama RS"), "kota": _teks(d, "kota", 60, True, "Kota"),
            "provinsi": _teks(d, "provinsi", 60, True, "Provinsi"),
            "subnet_router": _teks(d, "subnet_router", 18, label="Subnet router"),
            "zona_waktu": d.get("zona_waktu") if d.get("zona_waktu") in ("WIB", "WITA", "WIT") else "WIB",
            "aktif": _bendera(d, "aktif")}
    if lid:
        lama = db.kueri("SELECT * FROM lokasi WHERE id = %s", (lid,), satu=True)
        if not lama:
            abort(404)
        db.jalankan("UPDATE lokasi SET {} WHERE id = %s".format(", ".join(k + " = %s" for k in data)),
                    list(data.values()) + [lid])
        catat_audit("ubah RS", lama["kode"], {k: lama[k] for k in data}, data)
    else:
        kode = (_teks(d, "kode", 20, True, "Kode lokasi") or "").upper()
        if not re.fullmatch(r"[A-Z0-9_]{2,20}", kode):
            raise Galat("Kode lokasi hanya huruf besar, angka, garis bawah (contoh: SEMARANG)")
        if db.nilai("SELECT COUNT(*) FROM lokasi WHERE kode = %s", (kode,)):
            raise Galat("Kode lokasi {} sudah ada".format(kode))
        data["kode"] = kode
        lid = db.jalankan("INSERT INTO lokasi ({}) VALUES ({})".format(", ".join(data), ", ".join(["%s"] * len(data))),
                          list(data.values()))
        catat_audit("tambah RS", kode, None, data)
    hapus_cache()
    return jawab({"ok": True, "id": lid})


@app.post("/api/admin/mesin")
@wajib("Admin")
def api_mesin_simpan():
    d = request.get_json(silent=True) or {}
    mid = d.get("id")
    status = d.get("status") if d.get("status") in ("Aktif", "Maintenance", "Nonaktif") else "Nonaktif"
    data = {"kode_unit": (_teks(d, "kode_unit", 20, True, "Kode unit") or "").upper(),
            "lokasi_id": int(d.get("lokasi_id") or 0),
            "nama": _teks(d, "nama", 50, True, "Nama mesin"),
            "jenis_mesin": _teks(d, "jenis_mesin", 40, True, "Jenis mesin"),
            "base_file_name": _teks(d, "base_file_name", 100, label="Base File Name"),
            "pola_workbook": _teks(d, "pola_workbook", 200, label="Pola workbook"),
            "router": _teks(d, "router", 40, label="Router"),
            "ip_kantor": _teks(d, "ip_kantor", 15, label="IP"),
            "mac": _teks(d, "mac", 17, label="MAC"),
            "status": status, "aktif": 0 if status == "Nonaktif" else 1}
    if not db.nilai("SELECT COUNT(*) FROM lokasi WHERE id = %s", (data["lokasi_id"],)):
        raise Galat("Pilih RS")
    if not re.fullmatch(r"[A-Z0-9_-]{3,20}", data["kode_unit"]):
        raise Galat("Kode unit hanya huruf besar, angka, - dan _ (contoh: DOCS-BDG-01)")
    if db.nilai("SELECT COUNT(*) FROM mesin WHERE kode_unit = %s AND id <> %s", (data["kode_unit"], mid or 0)):
        raise Galat("Kode unit {} sudah dipakai".format(data["kode_unit"]))
    bfn = data["base_file_name"]
    if bfn:
        if re.search(r'[\\/:*?"<>|]', bfn):
            raise Galat("Base File Name tidak boleh berisi \\ / : * ? \" < > |")
        bentrok = db.kueri("SELECT kode_unit FROM mesin WHERE LOWER(base_file_name) = LOWER(%s) AND id <> %s",
                           (bfn, mid or 0), satu=True)
        if bentrok:
            raise Galat("Base File Name '{}' sudah dipakai {}. Tiap unit wajib punya Base File Name unik, "
                        "kalau tidak data dua RS akan tercampur.".format(bfn, bentrok["kode_unit"]))
    peringatan = None
    if status != "Nonaktif" and not bfn and not data["pola_workbook"]:
        peringatan = ("Unit aktif tapi Base File Name kosong: bridge tidak akan mengenali workbook DOCSApp unit ini.")
    if mid:
        lama = db.kueri("SELECT * FROM mesin WHERE id = %s", (mid,), satu=True)
        if not lama:
            abort(404)
        db.jalankan("UPDATE mesin SET {} WHERE id = %s".format(", ".join(k + " = %s" for k in data)),
                    list(data.values()) + [mid])
        catat_audit("ubah unit", data["kode_unit"], {k: lama.get(k) for k in data}, data)
    else:
        mid = db.jalankan("INSERT INTO mesin ({}) VALUES ({})".format(", ".join(data), ", ".join(["%s"] * len(data))),
                          list(data.values()))
        catat_audit("tambah unit", data["kode_unit"], None, data)
    hapus_cache()
    return jawab({"ok": True, "id": mid, "peringatan": peringatan})


KOLOM_ATURAN = ("sumber", "normal_min", "normal_max", "maks1m_max", "kritis_min", "kritis_max",
                "kritis_syarat_vsa_jalan", "delay_peringatan_detik", "delay_kritis_detik", "pulih_detik",
                "pulih_min", "naik_kritis_menit")


def _target(teks):
    if not teks or ":" not in teks:
        raise Galat("Target aturan tidak valid")
    jenis, nilai = teks.split(":", 1)
    if jenis == "m":
        m = db.kueri("SELECT id, kode_unit, jenis_mesin FROM mesin WHERE id = %s", (int(nilai),), satu=True)
        if not m:
            raise Galat("Unit tidak ditemukan")
        return "m", m
    if jenis == "j" and nilai.strip():
        return "j", {"jenis_mesin": nilai.strip()[:40]}
    raise Galat("Target aturan tidak valid")


@app.get("/api/admin/aturan")
@wajib("Admin")
def api_aturan():
    jenis, t = _target(request.args.get("target"))
    semua = _aturan_semua()
    hasil = {}
    for p in PARAMETER:
        if jenis == "m":
            khusus = next((a for a in semua if a["mesin_id"] == t["id"] and a["parameter"] == p and a["aktif"]), None)
            dasar = next((a for a in semua if a["mesin_id"] is None and a["parameter"] == p and a["aktif"] and
                          (a["jenis_mesin"] or "").lower() == (t["jenis_mesin"] or "").lower()), None)
            hasil[p] = {"asal": "unit" if khusus else ("jenis" if dasar else None), "aturan": khusus or dasar,
                        "dasar": dasar}
        else:
            dasar = next((a for a in semua if a["mesin_id"] is None and a["parameter"] == p and a["aktif"] and
                          (a["jenis_mesin"] or "").lower() == t["jenis_mesin"].lower()), None)
            hasil[p] = {"asal": "jenis" if dasar else None, "aturan": dasar, "dasar": None}
    return jawab({"target": request.args.get("target"), "parameter": hasil, "label": LABEL, "satuan": SATUAN})


@app.post("/api/admin/aturan")
@wajib("Admin")
def api_aturan_simpan():
    d = request.get_json(silent=True) or {}
    jenis, t = _target(d.get("target"))
    p = d.get("parameter")
    if p not in PARAMETER:
        raise Galat("Parameter tidak valid")
    nama = LABEL[p]
    data = {"sumber": d.get("sumber") if d.get("sumber") in ("terbaru", "avg1m") else SUMBER_DEFAULT[p],
            "normal_min": _angka(d, "normal_min", nama + " batas bawah normal"),
            "normal_max": _angka(d, "normal_max", nama + " batas atas normal"),
            "maks1m_max": _angka(d, "maks1m_max", nama + " batas maks 1 menit"),
            "kritis_min": _angka(d, "kritis_min", nama + " batas kritis bawah"),
            "kritis_max": _angka(d, "kritis_max", nama + " batas kritis atas"),
            "kritis_syarat_vsa_jalan": _bendera(d, "kritis_syarat_vsa_jalan"),
            "delay_peringatan_detik": _angka(d, "delay_peringatan_detik", "Delay peringatan", 0, 86400, True) or 0,
            "delay_kritis_detik": _angka(d, "delay_kritis_detik", "Delay kritis", 0, 86400, True),
            "pulih_detik": _angka(d, "pulih_detik", "Waktu pulih", 0, 86400, True) or 0,
            "pulih_min": _angka(d, "pulih_min", "Batas pulih"),
            "naik_kritis_menit": _angka(d, "naik_kritis_menit", "Naik ke kritis", 1, 1440, True)}
    nmin, nmax, kmin, kmax = data["normal_min"], data["normal_max"], data["kritis_min"], data["kritis_max"]
    if nmin is None and nmax is None and kmin is None and kmax is None and data["maks1m_max"] is None:
        raise Galat("Isi minimal satu batas")
    if nmin is not None and nmax is not None and nmin >= nmax:
        raise Galat("Batas bawah normal harus lebih kecil dari batas atas")
    if kmin is not None and nmin is not None and kmin > nmin:
        raise Galat("Batas kritis bawah harus ≤ batas bawah normal")
    if kmax is not None and nmax is not None and kmax < nmax:
        raise Galat("Batas kritis atas harus ≥ batas atas normal")
    if (kmin is not None or kmax is not None) and data["delay_kritis_detik"] is None:
        raise Galat("Isi delay kritis (detik) untuk batas kritis")
    u = pengguna_sekarang()
    if jenis == "m":
        lama = db.kueri("SELECT * FROM aturan_alarm WHERE mesin_id = %s AND parameter = %s ORDER BY aktif DESC, id DESC "
                        "LIMIT 1", (t["id"], p), satu=True)
        objek = "{} {}".format(t["kode_unit"], nama)
    else:
        lama = db.kueri("SELECT * FROM aturan_alarm WHERE mesin_id IS NULL AND jenis_mesin = %s AND parameter = %s "
                        "ORDER BY aktif DESC, id DESC LIMIT 1", (t["jenis_mesin"], p), satu=True)
        objek = "default {} {}".format(t["jenis_mesin"], nama)
    if lama:
        db.jalankan("UPDATE aturan_alarm SET {}, aktif = 1, diubah_oleh = %s WHERE id = %s".format(
            ", ".join(k + " = %s" for k in data)), list(data.values()) + [u["username"], lama["id"]])
    else:
        db.jalankan("INSERT INTO aturan_alarm (jenis_mesin, mesin_id, parameter, {}, diubah_oleh) VALUES ({})".format(
            ", ".join(data), ", ".join(["%s"] * (len(data) + 4))),
            [t["jenis_mesin"] if jenis == "j" else None, t["id"] if jenis == "m" else None, p] +
            list(data.values()) + [u["username"]])
    catat_audit("ubah ambang", objek, {k: lama[k] for k in KOLOM_ATURAN} if lama and lama["aktif"] else None, data)
    hapus_cache()
    return jawab({"ok": True})


@app.post("/api/admin/aturan/reset")
@wajib("Admin")
def api_aturan_reset():
    d = request.get_json(silent=True) or {}
    jenis, t = _target(d.get("target"))
    p = d.get("parameter")
    if jenis != "m" or p not in PARAMETER:
        raise Galat("Hanya aturan khusus unit yang bisa dikembalikan ke default")
    lama = db.kueri("SELECT * FROM aturan_alarm WHERE mesin_id = %s AND parameter = %s AND aktif = 1", (t["id"], p), satu=True)
    if lama:
        db.jalankan("UPDATE aturan_alarm SET aktif = 0, diubah_oleh = %s WHERE id = %s",
                    (pengguna_sekarang()["username"], lama["id"]))
        catat_audit("ambang ke default", "{} {}".format(t["kode_unit"], LABEL[p]), {k: lama[k] for k in KOLOM_ATURAN}, None)
    hapus_cache()
    return jawab({"ok": True})


@app.get("/api/admin/penerima")
@wajib("Admin")
def api_penerima():
    return jawab({"penerima": db.kueri("SELECT * FROM penerima_notifikasi ORDER BY aktif DESC, peran, nama"),
                  "notifikasi_aktif": cfg["notif"]["aktif"],
                  "smtp_siap": bool(cfg["notif"]["smtp_host"]), "telegram_siap": bool(cfg["notif"]["telegram_token"])})


@app.post("/api/admin/penerima")
@wajib("Admin")
def api_penerima_simpan():
    d = request.get_json(silent=True) or {}
    pid = d.get("id")
    channel = d.get("channel") if d.get("channel") in ("email", "telegram") else "email"
    alamat = _teks(d, "alamat", 200, True, "Alamat / chat ID")
    if channel == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", alamat):
        raise Galat("Alamat email tidak valid")
    if channel == "telegram" and not re.fullmatch(r"-?\d{5,20}|@[A-Za-z0-9_]{5,64}", alamat):
        raise Galat("Chat ID Telegram berupa angka (grup biasanya diawali -100) atau @namachannel")
    cakupan = _teks(d, "cakupan_lokasi", 200)
    if cakupan:
        kode = [c.strip().upper() for c in cakupan.split(",") if c.strip()]
        ada = {r["kode"] for r in db.kueri("SELECT kode FROM lokasi")}
        salah = [k for k in kode if k not in ada]
        if salah:
            raise Galat("Kode lokasi tidak dikenal: {}".format(", ".join(salah)))
        cakupan = ",".join(kode)

    def jam(k):
        v = (d.get(k) or "").strip()
        if not v:
            return None
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise Galat("Jam harus format JJ:MM")
        return v + ":00"
    data = {"nama": _teks(d, "nama", 80, True, "Nama"), "channel": channel, "alamat": alamat,
            "peran": d.get("peran") if d.get("peran") in ("Teknisi", "Supervisor") else "Teknisi",
            "terima_peringatan": _bendera(d, "terima_peringatan"), "terima_kritis": _bendera(d, "terima_kritis"),
            "terima_offline": _bendera(d, "terima_offline"), "terima_pulih": _bendera(d, "terima_pulih"),
            "cakupan_lokasi": cakupan, "jam_mulai": jam("jam_mulai"), "jam_selesai": jam("jam_selesai"),
            "aktif": _bendera(d, "aktif")}
    if (data["jam_mulai"] is None) != (data["jam_selesai"] is None):
        raise Galat("Isi jam mulai dan jam selesai, atau kosongkan keduanya (24 jam)")
    if pid:
        lama = db.kueri("SELECT * FROM penerima_notifikasi WHERE id = %s", (pid,), satu=True)
        if not lama:
            abort(404)
        db.jalankan("UPDATE penerima_notifikasi SET {} WHERE id = %s".format(", ".join(k + " = %s" for k in data)),
                    list(data.values()) + [pid])
        catat_audit("ubah penerima", data["nama"], {k: lama[k] for k in data}, data)
    else:
        pid = db.jalankan("INSERT INTO penerima_notifikasi ({}) VALUES ({})".format(
            ", ".join(data), ", ".join(["%s"] * len(data))), list(data.values()))
        catat_audit("tambah penerima", data["nama"], None, data)
    return jawab({"ok": True, "id": pid})


@app.post("/api/admin/penerima/<int:pid>/uji")
@wajib("Admin")
def api_penerima_uji(pid):
    n = latar["notifier"] or Notifier(db, cfg, log)
    status = n.uji(pid)
    catat_audit("uji notifikasi", "penerima #{}".format(pid), None, {"status": status})
    return jawab({"status": status})


@app.get("/api/admin/pengguna")
@wajib("Admin")
def api_pengguna():
    return jawab({"pengguna": db.kueri("SELECT id, username, nama, peran, aktif, dibuat, login_terakhir FROM pengguna "
                                       "ORDER BY aktif DESC, peran, username")})


@app.post("/api/admin/pengguna")
@wajib("Admin")
def api_pengguna_simpan():
    d = request.get_json(silent=True) or {}
    uid = d.get("id")
    peran = d.get("peran") if d.get("peran") in ("Admin", "Teknisi", "Viewer") else "Viewer"
    aktif = _bendera(d, "aktif")
    nama = _teks(d, "nama", 80, True, "Nama")
    pw = d.get("password") or ""
    if pw and len(pw) < 8:
        raise Galat("Password minimal 8 karakter")
    saya = pengguna_sekarang()
    if uid:
        lama = db.kueri("SELECT id, username, nama, peran, aktif FROM pengguna WHERE id = %s", (uid,), satu=True)
        if not lama:
            abort(404)
        if lama["peran"] == "Admin" and lama["aktif"] and (peran != "Admin" or not aktif):
            if db.nilai("SELECT COUNT(*) FROM pengguna WHERE peran = 'Admin' AND aktif = 1 AND id <> %s", (uid,)) == 0:
                raise Galat("Harus ada minimal satu Admin aktif")
        db.jalankan("UPDATE pengguna SET nama = %s, peran = %s, aktif = %s WHERE id = %s", (nama, peran, aktif, uid))
        if pw:
            db.jalankan("UPDATE pengguna SET password_hash = %s WHERE id = %s", (generate_password_hash(pw), uid))
        _cache_pengguna.pop(int(uid), None)
        catat_audit("ubah pengguna", lama["username"], {k: lama[k] for k in ("nama", "peran", "aktif")},
                    {"nama": nama, "peran": peran, "aktif": aktif, "password_direset": bool(pw)})
    else:
        username = (_teks(d, "username", 50, True, "Username") or "").lower()
        if not re.fullmatch(r"[a-z0-9._-]{2,50}", username):
            raise Galat("Username 2-50 karakter: huruf kecil, angka, titik, - atau _")
        if db.nilai("SELECT COUNT(*) FROM pengguna WHERE username = %s", (username,)):
            raise Galat("Username sudah dipakai")
        if not pw:
            raise Galat("Password wajib diisi untuk pengguna baru")
        uid = db.jalankan("INSERT INTO pengguna (username, nama, password_hash, peran, aktif) VALUES (%s,%s,%s,%s,%s)",
                          (username, nama, generate_password_hash(pw), peran, aktif))
        catat_audit("tambah pengguna", username, None, {"nama": nama, "peran": peran, "aktif": aktif})
    return jawab({"ok": True, "id": uid, "saya": saya["id"] == uid})


@app.get("/api/admin/audit")
@wajib("Admin")
def api_audit():
    batas = min(int(request.args.get("batas", 200)), 1000)
    cari = (request.args.get("cari") or "").strip()
    if cari:
        rows = db.kueri("SELECT * FROM audit WHERE pengguna LIKE %s OR aksi LIKE %s OR objek LIKE %s "
                        "ORDER BY id DESC LIMIT %s", ("%" + cari + "%",) * 3 + (batas,))
    else:
        rows = db.kueri("SELECT * FROM audit ORDER BY id DESC LIMIT %s", (batas,))
    return jawab({"audit": rows})


@app.get("/api/admin/sistem")
@wajib("Admin")
def api_sistem():
    sekarang = db.sekarang()
    e = latar["engine"]
    tabel = db.kueri("SELECT TABLE_NAME nama, TABLE_ROWS baris, ROUND((DATA_LENGTH + INDEX_LENGTH) / 1048576, 1) mb "
                     "FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
                     "ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC")
    data = db.kueri("SELECT m.kode_unit, MIN(s.waktu_mulai) pertama, MAX(s.waktu_terakhir) terakhir, "
                    "SUM(s.rec_no_terakhir) baris FROM sesi_log s JOIN mesin m ON m.id = s.mesin_id GROUP BY m.id")
    return jawab({
        "sekarang": sekarang, "versi": VERSI, "server_mulai": latar["mulai"],
        "sistem": _sistem(sekarang),
        "mesin_alarm_galat": e.galat_terakhir if e else "mesin alarm belum berjalan",
        "pengaturan": {k: v for k, v in cfg["engine"].items()},
        "notifikasi": {"aktif": cfg["notif"]["aktif"], "smtp": cfg["notif"]["smtp_host"] or "-",
                       "telegram": "ada token" if cfg["notif"]["telegram_token"] else "-"},
        "tabel": tabel, "data_unit": data,
        "log_notifikasi": db.kueri("SELECT n.*, e.mesin_id FROM log_notifikasi n LEFT JOIN event_alarm e ON e.id = n.event_id "
                                   "ORDER BY n.id DESC LIMIT 50"),
    })


class KunciTunggal:
    NAMA = "gpi_monitoring_dashboard"

    def __init__(self, cfg_mysql):
        self.cfg = cfg_mysql
        self.conn = None

    def ambil(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = buka_koneksi_tunggal(self.cfg)
        cur = self.conn.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (self.NAMA,))
        ok = cur.fetchone()[0] == 1
        cur.close()
        return ok

    def jaga(self):
        while True:
            time.sleep(60)
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (self.NAMA,))
                masih = cur.fetchone()[0] == 1
                cur.close()
            except Exception:
                masih = False
            if not masih:
                try:
                    log("Kunci server terlepas (koneksi MySQL putus), mengambil ulang: " +
                        ("berhasil" if self.ambil() else "GAGAL - ada server dashboard lain"))
                except Exception as e:
                    log("Gagal mengambil ulang kunci server: {}".format(e))


def buka_port(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    except OSError:
        s.close()
        return None
    return s


def mulai_latar():
    if latar["engine"]:
        return
    n = Notifier(db, cfg, log)
    e = Engine(db, cfg, n, log)
    latar["notifier"], latar["engine"] = n, e
    e.start()


def main():
    log("=" * 70)
    log("Dashboard Monitoring DOCS v{} - database {}@{}:{}/{}".format(
        VERSI, cfg["mysql"]["user"], cfg["mysql"]["host"], cfg["mysql"]["port"], cfg["mysql"]["database"]))
    try:
        db.sekarang()
        db.nilai("SELECT COUNT(*) FROM aturan_alarm")
    except Exception as e:
        log("GAGAL tersambung / tabel dashboard belum ada: {}".format(e))
        log("Cek password di server\\pengaturan_dashboard.ini dan pastikan 02_skema_dashboard.sql sudah dijalankan.")
        return 1
    kunci = KunciTunggal(cfg["mysql"])
    if not kunci.ambil():
        log("BERHENTI: server dashboard lain sudah berjalan (memakai database yang sama).")
        log("Untuk mengganti dengan versi terbaru, jalankan skrip\\RESTART_DASHBOARD.bat")
        return 3
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    sock = buka_port(host, port)
    if sock is None:
        log("BERHENTI: port {} sedang dipakai program lain (kemungkinan server dashboard versi lama).".format(port))
        log("Jalankan skrip\\RESTART_DASHBOARD.bat untuk menutup semua server lama lalu menyalakan yang baru.")
        return 3
    threading.Thread(target=kunci.jaga, daemon=True, name="kunci").start()
    if not db.nilai("SELECT COUNT(*) FROM pengguna WHERE peran = 'Admin' AND aktif = 1"):
        log("PERHATIAN: belum ada akun Admin. Jalankan dulu:  python buat_admin.py")
    if not cfg["notif"]["aktif"]:
        log("Notifikasi MODE UJI: alarm dicatat di log_notifikasi dengan status 'ditahan', tidak dikirim.")
    mulai_latar()
    from waitress import serve
    log("Buka di browser: http://localhost:{}  (dari PC lain: {})".format(port, cfg["server"]["alamat"]))
    serve(app, sockets=[sock], threads=12, ident="GPI-Monitoring")
    return 0


if __name__ == "__main__":
    sys.exit(main())
