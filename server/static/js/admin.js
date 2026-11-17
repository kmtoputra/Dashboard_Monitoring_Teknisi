(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  const isi = document.getElementById("isiTab");

  const field = (label, el, bantu, penuh) => h("div", { class: penuh ? "penuh" : "" }, h("label", { class: "f", text: label }), el, bantu ? h("div", { class: "bantu", text: bantu }) : null);
  const inp = (nama, nilai, attr) => h("input", Object.assign({ name: nama, value: nilai === null || nilai === undefined ? "" : nilai }, attr || {}));
  const sel = (nama, opsi, nilai) => {
    const s = h("select", { name: nama });
    opsi.forEach((o) => { const v = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : o; s.appendChild(h("option", { value: v, text: t, selected: String(v) === String(nilai) })); });
    return s;
  };
  const cek = (nama, label, nilai) => h("label", null, h("input", { type: "checkbox", name: nama, checked: !!nilai }), label);
  const baca = (form) => { const d = {}; form.querySelectorAll("[name]").forEach((el) => { d[el.name] = el.type === "checkbox" ? el.checked : el.value; }); return d; };
  const ya = (x) => (x ? "Ya" : "–");
  const kartu = (judul, kanan, ...anak) => h("div", { class: "card" }, h("div", { class: "card-head" }, h("div", { class: "card-title", text: judul }), h("div", { class: "kanan" }, kanan)), ...anak);
  const tabel = (kolom, baris) => h("div", { class: "tabel-wrap" }, h("table", { class: "t" },
    h("thead", null, h("tr", null, kolom.map((k) => h("th", { text: k })))), h("tbody", null, baris)));

  async function tabUnit() {
    const d = await G.api("/api/admin/master");
    const formRS = (r) => {
      r = r || { aktif: 1, zona_waktu: "WIB" };
      const f = h("div", { class: "form-grid" },
        field("Kode lokasi", inp("kode", r.kode, { disabled: !!r.id, placeholder: "contoh SEMARANG" }), r.id ? "Kode tidak bisa diubah (dipakai folder hasil skrip)" : "Huruf besar tanpa spasi"),
        field("Nama RS", inp("nama_rs", r.nama_rs)),
        field("Kota", inp("kota", r.kota)), field("Provinsi", inp("provinsi", r.provinsi)),
        field("Zona waktu RS", sel("zona_waktu", ["WIB", "WITA", "WIT"], r.zona_waktu)),
        field("Subnet router", inp("subnet_router", r.subnet_router, { placeholder: "192.168.100.0/24" })),
        h("div", { class: "penuh cek" }, cek("aktif", "Lokasi aktif", r.aktif)));
      G.modal(r.id ? "Ubah RS " + r.kode : "Tambah RS", f, [{ teks: "Batal" }, { teks: "Simpan", kelas: "btn-primary", aksi: async () => {
        await G.api("/api/admin/lokasi", { json: Object.assign(baca(f), { id: r.id }) });
        G.toast("RS disimpan"); tabUnit();
      } }], true);
    };
    const formUnit = (m) => {
      m = m || { status: "Nonaktif", jenis_mesin: "PCI DOCS 500", nama: "DOCS500" };
      const jenis = Array.from(new Set(d.jenis.concat(["PCI DOCS 200", "PCI DOCS 500"]))).sort();
      const f = h("div", { class: "form-grid" },
        field("Kode unit", inp("kode_unit", m.kode_unit, { placeholder: "DOCS-SMG-01" })),
        field("RS", sel("lokasi_id", d.lokasi.map((l) => [l.id, (l.nama_rs || l.kode) + " (" + l.kode + ")"]), m.lokasi_id)),
        field("Nama mesin", inp("nama", m.nama), "Dipakai bridge --impor KODE/NAMA, contoh DOCS500"),
        field("Jenis mesin", h("div", null, inp("jenis_mesin", m.jenis_mesin, { list: "daftarJenis" }), h("datalist", { id: "daftarJenis" }, jenis.map((j) => h("option", { value: j })))),
          "Menentukan ambang default yang dipakai"),
        field("Base File Name DOCSApp", inp("base_file_name", m.base_file_name, { placeholder: "DOCS_500_Semarang" }),
          "WAJIB unik. Sama persis dengan Base File Name di DOCSApp; workbook bernama [Base File Name][tanggal] akan dikenali otomatis.", true),
        field("Pola workbook lama (opsional)", inp("pola_workbook", m.pola_workbook), "Cadangan pencocokan, dipisah koma. Biarkan kosong kalau Base File Name sudah diisi."),
        field("Router", inp("router", m.router, { placeholder: "RUT241" })),
        field("IP di DOCSApp kantor", inp("ip_kantor", m.ip_kantor, { placeholder: "192.168.100.20" })),
        field("MAC controller", inp("mac", m.mac, { placeholder: "00:11:22:33:44:55" })),
        field("Status", sel("status", [["Aktif", "Aktif (dipantau)"], ["Maintenance", "Maintenance (alarm tanpa notifikasi)"], ["Nonaktif", "Nonaktif (belum terpasang)"]], m.status)));
      G.modal(m.id ? "Ubah unit " + m.kode_unit : "Tambah unit", f, [{ teks: "Batal" }, { teks: "Simpan", kelas: "btn-primary", aksi: async () => {
        const r = await G.api("/api/admin/mesin", { json: Object.assign(baca(f), { id: m.id }) });
        G.toast(r.peringatan ? "Disimpan. " + r.peringatan : "Unit disimpan", !!r.peringatan); tabUnit();
      } }], true);
    };
    G.kosongkan(isi).append(
      kartu("Unit mesin", h("button", { class: "btn btn-primary btn-sm", text: "Tambah unit", onclick: () => formUnit() }),
        h("p", { class: "muted kecil", style: { marginTop: 0 }, text: "Bridge membaca daftar ini ulang tiap 5 menit, jadi unit baru langsung dipantau tanpa restart. Unit Nonaktif tidak dipantau dan tidak memicu alarm Offline." }),
        tabel(["Kode", "RS", "Jenis", "Base File Name", "Router / IP", "Status", "Kondisi", ""], d.mesin.map((m) => h("tr", null,
          h("td", null, h("b", { text: m.kode_unit || "-" }), h("div", { class: "sub", text: m.nama })),
          h("td", { text: (m.nama_rs || m.kode_lokasi) }), h("td", { text: m.jenis_mesin }),
          h("td", null, m.base_file_name ? h("code", { text: m.base_file_name }) : h("span", { class: m.status === "Nonaktif" ? "muted" : "lv1", text: "belum diisi" })),
          h("td", null, m.router || "-", h("div", { class: "sub", text: m.ip_kantor || "" })),
          h("td", null, m.status === "Maintenance" ? h("span", { class: "tag-maint", text: "Maintenance" }) : m.status),
          h("td", null, m.status !== "Nonaktif" && m.status_live ? G.pillStatus(m.status_live) : "-", h("div", { class: "sub", text: m.data_terakhir ? "data " + G.tglJam(m.data_terakhir) : "" })),
          h("td", null, h("button", { class: "btn btn-secondary btn-tiny", text: "Ubah", onclick: () => formUnit(m) })))))),
      kartu("Rumah sakit / lokasi", h("button", { class: "btn btn-secondary btn-sm", text: "Tambah RS", onclick: () => formRS() }),
        tabel(["Kode", "Nama RS", "Kota", "Provinsi", "Zona", "Subnet router", "Aktif", ""], d.lokasi.map((l) => h("tr", null,
          h("td", null, h("b", { text: l.kode })), h("td", { text: l.nama_rs || "-" }), h("td", { text: l.kota }), h("td", { text: l.provinsi }),
          h("td", { text: l.zona_waktu }), h("td", { text: l.subnet_router || "-" }), h("td", { text: ya(l.aktif) }),
          h("td", null, h("button", { class: "btn btn-secondary btn-tiny", text: "Ubah", onclick: () => formRS(l) })))))));
  }

  let targetAturan = null;
  async function tabAturan() {
    const m = await G.api("/api/admin/master");
    if (!targetAturan) targetAturan = m.mesin.length ? "m:" + (m.mesin.find((x) => x.status !== "Nonaktif") || m.mesin[0]).id : "j:PCI DOCS 500";
    const pilihan = m.mesin.map((x) => ["m:" + x.id, "Unit " + x.kode_unit + " – " + (x.nama_rs || x.kode_lokasi) + " (" + x.jenis_mesin + ")"])
      .concat(m.jenis.map((j) => ["j:" + j, "Default semua unit " + j]));
    const s = sel("target", pilihan, targetAturan);
    s.style.maxWidth = "480px";
    s.addEventListener("change", () => { targetAturan = s.value; tabAturan(); });
    const d = await G.api("/api/admin/aturan?target=" + encodeURIComponent(targetAturan));
    const unitDipilih = targetAturan.startsWith("m:");
    const kartuParam = G.PARAM.map((p) => {
      const x = d.parameter[p], a = x.aturan, sat = G.SATUAN[p];
      const n = (v, s2) => (v === null || v === undefined ? "–" : G.angka(v, v % 1 ? 1 : 0) + (s2 === undefined ? (sat ? " " + sat : "") : s2));
      const dl = a ? h("dl", null,
        h("dt", { text: "Sumber nilai" }), h("dd", { text: a.sumber === "terbaru" ? "nilai terbaru" : "rata-rata 1 menit" }),
        h("dt", { text: "Normal" }), h("dd", { text: a.normal_min !== null && a.normal_max !== null ? n(a.normal_min, "") + " s.d. " + n(a.normal_max) :
          a.normal_min !== null ? "≥ " + n(a.normal_min) : a.normal_max !== null ? "≤ " + n(a.normal_max) : "–" }),
        a.maks1m_max !== null ? [h("dt", { text: "Maks 1 menit" }), h("dd", { text: "≤ " + n(a.maks1m_max) })] : null,
        h("dt", { text: "Kritis" }), h("dd", { text: (a.kritis_min !== null ? "< " + n(a.kritis_min) : "") + (a.kritis_max !== null ? " > " + n(a.kritis_max) : "") +
          (a.kritis_min === null && a.kritis_max === null ? (a.naik_kritis_menit ? "Peringatan ≥ " + a.naik_kritis_menit + " mnt" : "–") : "") + (a.kritis_syarat_vsa_jalan ? " (saat Fvsa ≥ 5)" : "") }),
        h("dt", { text: "Delay" }), h("dd", { text: "P " + G.durasi(a.delay_peringatan_detik) + (a.delay_kritis_detik !== null ? " · K " + G.durasi(a.delay_kritis_detik) : "") }),
        h("dt", { text: "Pulih" }), h("dd", { text: G.durasi(a.pulih_detik) + (a.pulih_min !== null ? " pada ≥ " + n(a.pulih_min) : "") }),
        a.naik_kritis_menit && (a.kritis_min !== null || a.kritis_max !== null) ? [h("dt", { text: "Naik Kritis" }), h("dd", { text: "Peringatan ≥ " + a.naik_kritis_menit + " mnt" })] : null,
        h("dt", { text: "Diubah" }), h("dd", { class: "muted", style: { fontWeight: 400 }, text: (a.diubah_oleh || "-") + " · " + G.tglJam(a.diubah) })) :
        h("p", { class: "muted kecil", text: "Belum ada aturan. Parameter ini tidak memicu alarm." });
      return h("div", { class: "aturan-k" },
        h("h3", null, G.LABEL[p], x.asal ? h("span", { class: "asal " + x.asal, text: x.asal === "unit" ? "khusus unit" : "default jenis" }) : null),
        dl,
        h("div", { class: "inline" },
          h("button", { class: "btn btn-secondary btn-tiny", text: unitDipilih && x.asal !== "unit" ? "Buat ambang khusus unit" : "Ubah", onclick: () => formAturan(p, a) }),
          unitDipilih && x.asal === "unit" ? h("button", { class: "btn btn-ghost btn-tiny", text: "Kembali ke default", onclick: () => resetAturan(p) }) : null));
    });
    G.kosongkan(isi).append(
      h("div", { class: "banner kuning", style: { marginTop: 0, marginBottom: 14 + "px" } }, h("div", null, h("b", { text: "Ambang awal masih draf dari data uji singkat. " }),
        "Hitung ulang dari log minimal 7 hari sebelum notifikasi diaktifkan: ", h("code", { text: "python replay_uji.py --unit DOCS-BDG-01 --statistik --hari 7" }),
        ". Perubahan berlaku pada siklus berikutnya (≤ 5 detik) dan tercatat di Audit Log.")),
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("div", { class: "card-title", text: "Ambang alarm" }), h("div", { class: "kanan" }, s)),
        h("div", { class: "aturan-grid" }, kartuParam)));
  }

  function formAturan(p, a) {
    a = a || { sumber: p === "purity" || p === "purge" ? "terbaru" : "avg1m", delay_peringatan_detik: 300, pulih_detik: 120, kritis_syarat_vsa_jalan: 0 };
    const sat = G.SATUAN[p] ? " (" + G.SATUAN[p] + ")" : "";
    const f = h("div", { class: "form-grid" },
      field("Sumber nilai", sel("sumber", [["terbaru", "Nilai terbaru"], ["avg1m", "Rata-rata 1 menit"]], a.sumber), "RT1, Fvsa, Booster sebaiknya rata-rata 1 menit (tahan lonjakan sesaat)", true),
      field("Normal minimum" + sat, inp("normal_min", a.normal_min), "Di bawah ini = Peringatan"),
      field("Normal maksimum" + sat, inp("normal_max", a.normal_max), "Di atas ini = Peringatan"),
      field("Maks 1 menit" + sat, inp("maks1m_max", a.maks1m_max), "Nilai MAKSIMUM 1 menit di atas ini = Peringatan (dipakai RT1)"),
      field("Pulih minimal" + sat, inp("pulih_min", a.pulih_min), "Histeresis: untuk pulih nilai harus ≥ ini (purity 91,5)"),
      field("Kritis jika di bawah" + sat, inp("kritis_min", a.kritis_min)),
      field("Kritis jika di atas" + sat, inp("kritis_max", a.kritis_max)),
      field("Delay Peringatan (detik)", inp("delay_peringatan_detik", a.delay_peringatan_detik, { type: "number", min: 0 }), "Kondisi harus bertahan selama ini sebelum alarm"),
      field("Delay Kritis (detik)", inp("delay_kritis_detik", a.delay_kritis_detik, { type: "number", min: 0 })),
      field("Waktu pulih (detik)", inp("pulih_detik", a.pulih_detik, { type: "number", min: 0 }), "Harus normal selama ini sebelum event ditutup"),
      field("Peringatan naik jadi Kritis setelah (menit)", inp("naik_kritis_menit", a.naik_kritis_menit, { type: "number", min: 1 }), "Kosongkan kalau tidak dipakai (AL-05)"),
      h("div", { class: "penuh cek" }, cek("kritis_syarat_vsa_jalan", "Kritis hanya berlaku saat Fvsa ≥ 5 Hz (VSA jalan) – dipakai Booster", a.kritis_syarat_vsa_jalan)));
    const judul = targetAturan.startsWith("m:") ? "Ambang khusus unit: " + G.LABEL[p] : "Ambang default " + targetAturan.slice(2) + ": " + G.LABEL[p];
    G.modal(judul, f, [{ teks: "Batal" }, { teks: "Simpan", kelas: "btn-primary", aksi: async () => {
      await G.api("/api/admin/aturan", { json: Object.assign(baca(f), { target: targetAturan, parameter: p }) });
      G.toast("Ambang " + G.LABEL[p] + " disimpan dan langsung berlaku"); tabAturan();
    } }], true);
  }

  function resetAturan(p) {
    G.modal("Kembali ke default", h("p", { text: "Ambang khusus " + G.LABEL[p] + " untuk unit ini dinonaktifkan dan unit kembali memakai default jenis mesinnya." }),
      [{ teks: "Batal" }, { teks: "Kembalikan", kelas: "btn-primary", aksi: async () => {
        await G.api("/api/admin/aturan/reset", { json: { target: targetAturan, parameter: p } });
        G.toast("Kembali ke default"); tabAturan();
      } }]);
  }

  async function tabPenerima() {
    const d = await G.api("/api/admin/penerima");
    const form = (r) => {
      r = r || { channel: "email", peran: "Teknisi", aktif: 1, terima_peringatan: 1, terima_kritis: 1, terima_offline: 1, terima_pulih: 1 };
      const f = h("div", { class: "form-grid" },
        field("Nama", inp("nama", r.nama, { placeholder: "Teknisi on-call / Grup Telegram Teknisi" })),
        field("Peran", sel("peran", ["Teknisi", "Supervisor"], r.peran), "Supervisor menerima eskalasi Kritis/Offline yang belum di-ack 30 menit"),
        field("Channel", sel("channel", [["email", "Email"], ["telegram", "Telegram"]], r.channel)),
        field("Alamat email / chat ID Telegram", inp("alamat", r.alamat), "Chat ID grup Telegram biasanya diawali -100"),
        field("Cakupan RS (kode lokasi, dipisah koma)", inp("cakupan_lokasi", r.cakupan_lokasi, { placeholder: "kosong = semua RS" }), "Contoh: BANDUNG,SEMARANG"),
        field("Jam on-call (kosong = 24 jam)", h("div", { class: "inline" }, inp("jam_mulai", r.jam_mulai, { type: "time" }), " s.d. ", inp("jam_selesai", r.jam_selesai, { type: "time" })), "Contoh 17:00 s.d. 08:00 untuk shift malam"),
        h("div", { class: "penuh" }, h("label", { class: "f", text: "Jenis pesan yang diterima" }), h("div", { class: "cek" },
          cek("terima_peringatan", "Peringatan", r.terima_peringatan), cek("terima_kritis", "Kritis (diulang tiap 30 mnt)", r.terima_kritis),
          cek("terima_offline", "Offline", r.terima_offline), cek("terima_pulih", "Pulih", r.terima_pulih))),
        h("div", { class: "penuh cek" }, cek("aktif", "Aktif", r.aktif)));
      G.modal(r.id ? "Ubah penerima" : "Tambah penerima", f, [{ teks: "Batal" }, { teks: "Simpan", kelas: "btn-primary", aksi: async () => {
        await G.api("/api/admin/penerima", { json: Object.assign(baca(f), { id: r.id }) });
        G.toast("Penerima disimpan"); tabPenerima();
      } }], true);
    };
    const uji = async (r, btn) => {
      btn.disabled = true; btn.textContent = "Mengirim…";
      try { const x = await G.api("/api/admin/penerima/" + r.id + "/uji", { json: {} }); G.toast("Uji ke " + r.nama + ": " + x.status, x.status !== "terkirim"); }
      catch (e) { G.toast(e.message, true); }
      btn.disabled = false; btn.textContent = "Uji kirim";
    };
    G.kosongkan(isi).append(
      h("div", { class: "banner " + (d.notifikasi_aktif ? "biru" : "kuning"), style: { marginTop: 0, marginBottom: "14px" } }, h("div", null,
        h("b", { text: d.notifikasi_aktif ? "Notifikasi AKTIF. " : "Notifikasi MODE UJI (belum dikirim). " }),
        d.notifikasi_aktif ? "Pesan alarm dikirim ke penerima di bawah." : "Pesan alarm hanya dicatat dengan status \"ditahan\" (lihat tab Sistem). Aktifkan di server\\pengaturan_dashboard.ini ([notifikasi] aktif = ya) setelah ambang dikalibrasi, lalu restart dashboard.",
        " SMTP: " + (d.smtp_siap ? "sudah diatur" : "belum diatur") + " · Telegram: " + (d.telegram_siap ? "token ada" : "belum diatur") + ". Tombol Uji kirim tetap mengirim walau mode uji.")),
      kartu("Penerima notifikasi", h("button", { class: "btn btn-primary btn-sm", text: "Tambah penerima", onclick: () => form() }),
        d.penerima.length ? tabel(["Nama", "Channel", "Peran", "Menerima", "Cakupan", "Jam", "Aktif", ""], d.penerima.map((r) => {
          const b = h("button", { class: "btn btn-secondary btn-tiny", text: "Uji kirim" });
          b.addEventListener("click", () => uji(r, b));
          return h("tr", null, h("td", null, h("b", { text: r.nama })), h("td", null, r.channel, h("div", { class: "sub", text: r.alamat })), h("td", { text: r.peran }),
            h("td", { text: [r.terima_peringatan && "Peringatan", r.terima_kritis && "Kritis", r.terima_offline && "Offline", r.terima_pulih && "Pulih"].filter(Boolean).join(", ") }),
            h("td", { text: r.cakupan_lokasi || "semua RS" }), h("td", { text: r.jam_mulai ? r.jam_mulai + "–" + r.jam_selesai : "24 jam" }), h("td", { text: ya(r.aktif) }),
            h("td", null, h("div", { class: "inline" }, h("button", { class: "btn btn-secondary btn-tiny", text: "Ubah", onclick: () => form(r) }), b)));
        })) : h("div", { class: "kosong", text: "Belum ada penerima. Tambahkan email teknisi on-call dan supervisor." })));
  }

  async function tabPengguna() {
    const d = await G.api("/api/admin/pengguna");
    const form = (r) => {
      r = r || { peran: "Viewer", aktif: 1 };
      const f = h("div", { class: "form-grid" },
        field("Username", inp("username", r.username, { disabled: !!r.id, autocomplete: "off" }), r.id ? null : "Huruf kecil, angka, titik, - atau _"),
        field("Nama", inp("nama", r.nama)),
        field("Peran", sel("peran", [["Viewer", "Viewer – lihat saja (akun TV)"], ["Teknisi", "Teknisi – lihat, ack, maintenance"], ["Admin", "Admin – semua termasuk pengaturan"]], r.peran)),
        field(r.id ? "Reset password (kosongkan kalau tidak diubah)" : "Password", inp("password", "", { type: "password", autocomplete: "new-password" }), "Minimal 8 karakter"),
        h("div", { class: "penuh cek" }, cek("aktif", "Aktif (bisa login)", r.aktif)));
      G.modal(r.id ? "Ubah pengguna " + r.username : "Tambah pengguna", f, [{ teks: "Batal" }, { teks: "Simpan", kelas: "btn-primary", aksi: async () => {
        await G.api("/api/admin/pengguna", { json: Object.assign(baca(f), { id: r.id, username: r.username || baca(f).username }) });
        G.toast("Pengguna disimpan"); tabPengguna();
      } }], true);
    };
    G.kosongkan(isi).append(kartu("Pengguna", h("button", { class: "btn btn-primary btn-sm", text: "Tambah pengguna", onclick: () => form() }),
      tabel(["Username", "Nama", "Peran", "Aktif", "Login terakhir", ""], d.pengguna.map((r) => h("tr", null,
        h("td", null, h("b", { text: r.username })), h("td", { text: r.nama }), h("td", { text: r.peran }), h("td", { text: ya(r.aktif) }),
        h("td", { text: r.login_terakhir ? G.tglJam(r.login_terakhir) : "belum pernah" }),
        h("td", null, h("button", { class: "btn btn-secondary btn-tiny", text: "Ubah", onclick: () => form(r) })))))));
  }

  async function tabAudit(cari) {
    const d = await G.api("/api/admin/audit?batas=300" + (cari ? "&cari=" + encodeURIComponent(cari) : ""));
    const c = inp("cari", cari || "", { placeholder: "Cari pengguna / aksi / objek" });
    c.style.width = "260px";
    c.addEventListener("keydown", (e) => { if (e.key === "Enter") tabAudit(c.value); });
    const js = (x) => (x === null || x === undefined ? "" : JSON.stringify(typeof x === "string" ? JSON.parse(x) : x));
    G.kosongkan(isi).append(kartu("Audit log", c,
      tabel(["Waktu", "Pengguna", "Aksi", "Objek", "Sebelum", "Sesudah"], d.audit.map((r) => h("tr", null,
        h("td", { text: G.tglJam(r.waktu) }), h("td", { text: r.pengguna }), h("td", { text: r.aksi }), h("td", { text: r.objek }),
        h("td", null, h("div", { class: "json", text: js(r.nilai_lama) })), h("td", null, h("div", { class: "json", text: js(r.nilai_baru) })))))));
  }

  async function tabSistem() {
    const d = await G.api("/api/admin/sistem");
    const s = d.sistem;
    const st = (ok, teks) => h("span", { class: "pill-st " + (ok ? "st-normal" : ok === null ? "st-offline" : "st-kritis"), text: teks });
    G.kosongkan(isi).append(
      kartu("Status komponen", null, tabel(["Komponen", "Status", "Keterangan"], [
        h("tr", null, h("td", { text: "Bridge DOCSApp → MySQL" }), h("td", null, st(s.bridge.hidup, s.bridge.hidup ? "berjalan" : s.bridge.hidup === null ? "belum ada heartbeat" : "mati")),
          h("td", { text: (s.bridge.waktu ? "heartbeat " + G.relatif(s.bridge.umur) + " · " : "") + (s.bridge.info || "") })),
        h("tr", null, h("td", { text: "Mesin alarm (dashboard)" }), h("td", null, st(s.mesin_alarm.hidup, s.mesin_alarm.hidup ? "berjalan" : "tidak berjalan")),
          h("td", { text: d.mesin_alarm_galat ? "galat: " + d.mesin_alarm_galat : "tanpa galat · server mulai " + G.tglJam(d.server_mulai) })),
        h("tr", null, h("td", { text: "Notifikasi" }), h("td", null, st(d.notifikasi.aktif ? true : null, d.notifikasi.aktif ? "aktif" : "mode uji")),
          h("td", { text: "SMTP " + d.notifikasi.smtp + " · Telegram " + d.notifikasi.telegram })),
      ])),
      kartu("Data per unit", null, tabel(["Unit", "Data pertama", "Data terakhir", "Total baris (RecNo)"], d.data_unit.map((r) => h("tr", null,
        h("td", { text: r.kode_unit }), h("td", { text: G.tglJam(r.pertama) }), h("td", { text: G.tglJam(r.terakhir) }), h("td", { class: "num", text: G.angka(r.baris, 0) }))))),
      kartu("Notifikasi terakhir (50)", null, d.log_notifikasi.length ? tabel(["Waktu", "Jenis", "Channel", "Penerima", "Status", "Pesan"], d.log_notifikasi.map((r) => h("tr", null,
        h("td", { text: G.tglJam(r.waktu_kirim) }), h("td", { text: r.jenis }), h("td", { text: r.channel }), h("td", { text: r.penerima }),
        h("td", { class: /GAGAL/.test(r.status) ? "lv2" : /ditahan|tidak ada/.test(r.status) ? "lv1" : "", text: r.status }),
        h("td", null, h("div", { class: "json", text: r.pesan || "" }))))) : h("div", { class: "kosong", text: "Belum ada notifikasi." })),
      kartu("Pengaturan mesin alarm (server\\pengaturan_dashboard.ini)", null, tabel(["Kunci", "Nilai"], Object.keys(d.pengaturan).map((k) => h("tr", null, h("td", { text: k }), h("td", { text: d.pengaturan[k] }))))),
      kartu("Ukuran tabel", null, tabel(["Tabel", "Perkiraan baris", "MB"], d.tabel.map((r) => h("tr", null, h("td", { text: r.nama }), h("td", { class: "num", text: G.angka(r.baris, 0) }), h("td", { class: "num", text: G.angka(r.mb, 1) }))))),
      h("p", { class: "muted kecil", text: "Versi dashboard " + d.versi + ". Jam server " + G.tglJam(d.sekarang) + "." }));
  }

  const TAB = { unit: tabUnit, aturan: tabAturan, penerima: tabPenerima, pengguna: tabPengguna, audit: () => tabAudit(""), sistem: tabSistem };
  function buka(nama) {
    if (!TAB[nama]) nama = "unit";
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("aktif", b.dataset.tab === nama));
    history.replaceState(null, "", "#" + nama);
    G.kosongkan(isi).appendChild(h("div", { class: "kosong", text: "Memuat…" }));
    TAB[nama]().catch((e) => { G.kosongkan(isi).appendChild(h("div", { class: "banner merah", text: e.message })); });
  }
  document.getElementById("tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) buka(b.dataset.tab); });
  window.addEventListener("hashchange", () => buka(location.hash.slice(1)));
  buka(location.hash.slice(1));
  G.tandaiUpdate(true);
  G.pantauSistem();
})();
