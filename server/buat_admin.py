import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from db import Database, baca_pengaturan


def main():
    db = Database(baca_pengaturan()["mysql"], 2)
    print("Buat / reset akun Admin Dashboard Monitoring DOCS\n")
    username = (input("Username [admin]: ").strip() or "admin").lower()
    ada = db.kueri("SELECT id, nama, peran FROM pengguna WHERE username = %s", (username,), satu=True)
    if ada:
        print("Akun '{}' sudah ada (peran {}). Password akan direset dan peran dijadikan Admin.".format(username, ada["peran"]))
        nama = ada["nama"]
    else:
        nama = input("Nama lengkap: ").strip() or username
    while True:
        pw = getpass.getpass("Password (min 8 karakter, tidak tampil saat diketik): ")
        if len(pw) < 8:
            print("Terlalu pendek.")
            continue
        if getpass.getpass("Ulangi password: ") != pw:
            print("Tidak sama, ulangi.")
            continue
        break
    h = generate_password_hash(pw)
    if ada:
        db.jalankan("UPDATE pengguna SET password_hash = %s, peran = 'Admin', aktif = 1 WHERE id = %s", (h, ada["id"]))
    else:
        db.jalankan("INSERT INTO pengguna (username, nama, password_hash, peran, aktif) VALUES (%s,%s,%s,'Admin',1)",
                    (username, nama, h))
    db.jalankan("INSERT INTO audit (waktu, pengguna, aksi, objek) VALUES (NOW(), 'buat_admin.py', %s, %s)",
                ("reset admin" if ada else "tambah admin", username))
    print("\nSelesai. Login dengan username '{}' di dashboard.".format(username))
    return 0


if __name__ == "__main__":
    sys.exit(main())
