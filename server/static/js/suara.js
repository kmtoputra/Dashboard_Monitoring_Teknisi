(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  const KUNCI = "gpi_suara", KUNCI_BERKAS = "gpi_suara_berkas", KUNCI_SENYAP = "gpi_suara_senyap";
  const LEVEL = ["Kritis", "Offline", "Peringatan"];
  const KEY = { Kritis: "kritis", Offline: "offline", Peringatan: "peringatan" };
  const DEFAULT = {
    aktif: true, kritis: true, peringatan: true, offline: true,
    suara_kritis: "sirene", suara_peringatan: "bip_lembut", suara_offline: "lonceng",
    volume: 70, ulang: 30,
  };
  const NAMA = { sirene: "Sirene", bip: "Bip tiga kali", bip_lembut: "Bip lembut (dua kali)", lonceng: "Lonceng", buzzer: "Buzzer", berkas: "File suara sendiri" };
  const MAKS_BERKAS = 1024 * 1024;

  let P = muat();
  let ctx = null, audioBerkas = null, timer = null, levelAktif = null;
  let hitung = { Kritis: 0, Offline: 0, Peringatan: 0 }, hitungLama = { Kritis: 0, Offline: 0, Peringatan: 0 };

  function muat() {
    try { return Object.assign({}, DEFAULT, JSON.parse(localStorage.getItem(KUNCI) || "{}")); } catch (e) { return Object.assign({}, DEFAULT); }
  }
  function simpan() { try { localStorage.setItem(KUNCI, JSON.stringify(P)); } catch (e) { G.toast("Pengaturan suara tidak bisa disimpan di browser ini", true); } }
  function berkas() { try { return localStorage.getItem(KUNCI_BERKAS); } catch (e) { return null; } }
  function namaBerkas() { try { return localStorage.getItem(KUNCI_BERKAS + "_nama"); } catch (e) { return null; } }
  function senyapSampai() { try { return +(localStorage.getItem(KUNCI_SENYAP) || 0); } catch (e) { return 0; } }

  function konteks() {
    if (!ctx) {
      try { ctx = new (window.AudioContext || window.webkitAudioContext)(); ctx.onstatechange = perbaruiTombol; } catch (e) { ctx = null; }
    }
    return ctx;
  }
  function siap() { return !!(ctx && ctx.state === "running"); }
  function aktifkan() {
    const c = konteks();
    if (c && c.state !== "running") c.resume().then(() => { perbaruiTombol(); if (levelAktif) bunyi(levelAktif); }).catch(() => {});
  }
  ["pointerdown", "keydown", "touchstart"].forEach((ev) => document.addEventListener(ev, aktifkan, { capture: true, passive: true }));

  function nada(c, t0, frek, lama, tipe, vol, frekAkhir, tahan) {
    const o = c.createOscillator(), g = c.createGain();
    o.type = tipe;
    o.frequency.setValueAtTime(frek, t0);
    if (frekAkhir) o.frequency.linearRampToValueAtTime(frekAkhir, t0 + lama);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.02);
    if (tahan) g.gain.setValueAtTime(vol, t0 + lama - 0.06);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + lama);
    o.connect(g).connect(c.destination);
    o.start(t0);
    o.stop(t0 + lama + 0.05);
  }
  const POLA = {
    sirene: (c, t, v) => { for (let i = 0; i < 2; i++) { nada(c, t + i * 1.4, 620, 0.7, "triangle", v, 1250, true); nada(c, t + i * 1.4 + 0.7, 1250, 0.7, "triangle", v, 620, true); } },
    bip: (c, t, v) => [0, 0.28, 0.56].forEach((d, i) => nada(c, t + d, i === 2 ? 1046 : 880, 0.22, "square", v * 0.55, null, true)),
    bip_lembut: (c, t, v) => [0, 0.38].forEach((d) => nada(c, t + d, 660, 0.26, "sine", v, null, true)),
    lonceng: (c, t, v) => [0, 0.7].forEach((d) => { nada(c, t + d, 1046, 1.3, "sine", v); nada(c, t + d, 1568, 1.0, "sine", v * 0.45); nada(c, t + d, 2093, 0.6, "sine", v * 0.2); }),
    buzzer: (c, t, v) => [0, 0.45, 0.9].forEach((d) => nada(c, t + d, 196, 0.35, "sawtooth", v * 0.45, null, true)),
  };

  function keBlob(dataUrl) {
    const koma = dataUrl.indexOf(","), tipe = (dataUrl.slice(5, koma).split(";")[0]) || "audio/mpeg";
    const biner = atob(dataUrl.slice(koma + 1)), isi = new Uint8Array(biner.length);
    for (let i = 0; i < biner.length; i++) isi[i] = biner.charCodeAt(i);
    return URL.createObjectURL(new Blob([isi], { type: tipe }));
  }
  function alasanGagal(e) {
    if (e && e.name === "NotAllowedError") return "browser belum mengizinkan suara. Klik halaman sekali lalu coba lagi.";
    if (e && e.name === "NotSupportedError") return "format file tidak didukung browser. Pakai mp3, wav, atau ogg.";
    return (e && e.message) || "sebab tidak diketahui";
  }

  function mainkan(jenis, lapor) {
    const vol = Math.max(0, Math.min(100, P.volume)) / 100;
    if (jenis === "berkas") {
      const data = berkas();
      if (data) {
        try {
          if (!audioBerkas || audioBerkas._sumber !== data) {
            if (audioBerkas && audioBerkas.src.startsWith("blob:")) URL.revokeObjectURL(audioBerkas.src);
            audioBerkas = new Audio(keBlob(data));
            audioBerkas._sumber = data;
          }
          audioBerkas.volume = vol;
          audioBerkas.currentTime = 0;
          audioBerkas.play().catch((e) => {
            if (lapor) G.toast("File suara tidak bisa diputar: " + alasanGagal(e), true);
            else mainkan("sirene");
          });
          return;
        } catch (e) {
          if (lapor) G.toast("File suara rusak: " + alasanGagal(e), true);
          jenis = "sirene";
        }
      } else {
        if (lapor) G.toast("Belum ada file suara. Unggah dulu di bagian File suara sendiri.", true);
        jenis = "sirene";
      }
    }
    const c = konteks();
    if (!c) return;
    if (c.state !== "running") { c.resume().catch(() => {}); }
    (POLA[jenis] || POLA.bip)(c, c.currentTime + 0.03, vol * 0.5);
  }
  function bunyi(level) {
    if (!P.aktif || !level || Date.now() < senyapSampai()) return;
    mainkan(P["suara_" + KEY[level]]);
  }
  function jadwal() {
    clearInterval(timer);
    timer = P.ulang > 0 ? setInterval(() => bunyi(levelAktif), P.ulang * 1000) : null;
  }

  function evaluasi(d) {
    hitung = { Kritis: 0, Offline: 0, Peringatan: 0 };
    (d.unit || []).forEach((u) => {
      hitung.Kritis += u.alarm.kritis_belum_ack || 0;
      hitung.Peringatan += u.alarm.peringatan_belum_ack || 0;
      hitung.Offline += u.alarm.offline_belum_ack || 0;
    });
    const dipilih = LEVEL.filter((l) => P.aktif && P[KEY[l]] && hitung[l] > 0);
    const baru = LEVEL.some((l) => P[KEY[l]] && hitung[l] > hitungLama[l]);
    const tertinggi = dipilih[0] || null;
    hitungLama = hitung;
    if (!tertinggi) {
      levelAktif = null;
      clearInterval(timer);
      timer = null;
    } else {
      if (baru || tertinggi !== levelAktif) { levelAktif = tertinggi; bunyi(tertinggi); jadwal(); }
      else if (!timer && P.ulang > 0) jadwal();
      levelAktif = tertinggi;
    }
    perbaruiTombol();
  }

  const IKON_ON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>';
  const IKON_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"/><path d="M17 17H3s3-2 3-9a4.67 4.67 0 0 1 .3-1.7"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="m2 2 20 20"/></svg>';
  function perbaruiTombol() {
    const b = document.getElementById("btnSuara");
    if (!b) return;
    const senyap = Date.now() < senyapSampai();
    const mati = !P.aktif || senyap;
    b.innerHTML = mati ? IKON_OFF : IKON_ON;
    b.classList.toggle("mati", mati);
    b.classList.toggle("perlu-klik", P.aktif && !senyap && !siap() && !(P["suara_" + KEY[levelAktif || "Kritis"]] === "berkas"));
    b.classList.toggle("bunyi", !mati && levelAktif !== null && levelAktif !== "Peringatan");
    b.classList.toggle("bunyi-p", !mati && levelAktif === "Peringatan");
    let t = "Pengaturan suara alarm";
    if (!P.aktif) t = "Suara alarm dimatikan di browser ini. Klik untuk mengatur.";
    else if (senyap) t = "Suara disenyapkan sampai " + new Date(senyapSampai()).toTimeString().slice(0, 5) + ". Klik untuk mengatur.";
    else if (!siap()) t = "Suara belum aktif: klik di mana saja pada halaman. Klik ikon ini untuk mengatur.";
    else if (levelAktif) t = "Berbunyi: " + ringkasHitung() + ". Ack alarmnya untuk menghentikan.";
    b.title = t;
    b.setAttribute("aria-label", t);
  }
  function ringkasHitung() {
    return LEVEL.filter((l) => hitung[l] > 0).map((l) => hitung[l] + " " + l).join(", ") + " belum di-ack";
  }

  function bukaPengaturan() {
    aktifkan();
    const status = h("div", { class: "suara-status" });
    const isiStatus = () => {
      const ada = LEVEL.some((l) => hitung[l] > 0);
      status.className = "suara-status" + (ada ? " ada" : !siap() ? " perlu" : "");
      status.textContent = (ada ? "Saat ini: " + ringkasHitung() + "." : "Tidak ada alarm yang belum di-ack.") +
        (!siap() ? " Suara browser belum aktif: klik di mana saja pada halaman sekali." : "") +
        (Date.now() < senyapSampai() ? " Disenyapkan sampai " + new Date(senyapSampai()).toTimeString().slice(0, 5) + "." : "");
    };
    isiStatus();
    const ubah = (k, v) => { P[k] = v; simpan(); jadwal(); perbaruiTombol(); isiStatus(); };
    const pilihSuara = (k) => {
      const s = h("select");
      Object.keys(NAMA).forEach((j) => s.appendChild(h("option", { value: j, text: NAMA[j] + (j === "berkas" && namaBerkas() ? " (" + namaBerkas() + ")" : ""), selected: P[k] === j })));
      s.addEventListener("change", () => ubah(k, s.value));
      return s;
    };
    const baris = (level, ket) => {
      const k = KEY[level];
      const cb = h("input", { type: "checkbox", checked: !!P[k] });
      cb.addEventListener("change", () => ubah(k, cb.checked));
      return h("div", { class: "suara-baris" },
        h("label", null, cb, h("span", { class: "lv-pill lv-" + level, text: level })),
        pilihSuara("suara_" + k),
        h("button", { class: "btn btn-secondary btn-sm", text: "Tes", onclick: () => { aktifkan(); mainkan(P["suara_" + k], true); } }),
        h("div", { class: "suara-sub", text: ket }));
    };
    const cbAktif = h("input", { type: "checkbox", checked: !!P.aktif });
    cbAktif.addEventListener("change", () => ubah("aktif", cbAktif.checked));
    const vol = h("input", { type: "range", min: 0, max: 100, step: 5, value: P.volume });
    const volTeks = h("span", { class: "muted", text: P.volume + "%" });
    vol.addEventListener("input", () => { volTeks.textContent = vol.value + "%"; });
    vol.addEventListener("change", () => { ubah("volume", +vol.value); mainkan(P.suara_kritis, true); });
    const ulang = h("select");
    [[0, "Tidak diulang (sekali saat alarm baru)"], [15, "Tiap 15 detik"], [30, "Tiap 30 detik"], [60, "Tiap 1 menit"], [120, "Tiap 2 menit"], [300, "Tiap 5 menit"]]
      .forEach((o) => ulang.appendChild(h("option", { value: o[0], text: o[1], selected: +P.ulang === o[0] })));
    ulang.addEventListener("change", () => ubah("ulang", +ulang.value));

    const infoBerkas = h("span", { class: "muted kecil", text: namaBerkas() ? "Tersimpan: " + namaBerkas() : "Belum ada file" });
    const inputBerkas = h("input", { type: "file", accept: "audio/*" });
    inputBerkas.addEventListener("change", () => {
      const f = inputBerkas.files[0];
      if (!f) return;
      if (f.size > MAKS_BERKAS) { G.toast("File terlalu besar (maks 1 MB). Potong jadi 2–5 detik.", true); inputBerkas.value = ""; return; }
      const r = new FileReader();
      r.onload = () => {
        try {
          localStorage.setItem(KUNCI_BERKAS, r.result);
          localStorage.setItem(KUNCI_BERKAS + "_nama", f.name);
        } catch (e) { G.toast("Browser menolak menyimpan file ini (penyimpanan penuh).", true); return; }
        audioBerkas = null;
        infoBerkas.textContent = "Tersimpan: " + f.name;
        G.toast("File suara disimpan. Pilih \"File suara sendiri\" pada level yang diinginkan.");
        mainkan("berkas", true);
      };
      r.readAsDataURL(f);
    });
    const hapusBerkas = h("button", { class: "btn btn-ghost btn-sm", text: "Hapus file", onclick: () => {
      try { localStorage.removeItem(KUNCI_BERKAS); localStorage.removeItem(KUNCI_BERKAS + "_nama"); } catch (e) { }
      audioBerkas = null;
      infoBerkas.textContent = "Belum ada file";
    } });

    const tombolSenyap = h("button", { class: "btn btn-secondary btn-sm" });
    const isiSenyap = () => { tombolSenyap.textContent = Date.now() < senyapSampai() ? "Batalkan senyap" : "Senyapkan 15 menit"; };
    isiSenyap();
    tombolSenyap.addEventListener("click", () => {
      try { localStorage.setItem(KUNCI_SENYAP, Date.now() < senyapSampai() ? "0" : String(Date.now() + 15 * 60000)); } catch (e) { }
      isiSenyap(); isiStatus(); perbaruiTombol();
    });

    const isi = h("div", null, status,
      h("div", { class: "suara-baris", style: { borderTop: "1px solid var(--border-soft)" } },
        h("label", null, cbAktif, "Suara aktif"), h("span", { class: "muted kecil", text: "Matikan kalau browser ini tidak perlu berbunyi (misalnya laptop pribadi)." }), tombolSenyap),
      baris("Kritis", "Purity di bawah batas kritis, VSA berhenti, atau Peringatan yang bertahan lama."),
      baris("Peringatan", "Parameter keluar dari batas normal (sudah lewat delay alarm)."),
      baris("Offline", "Tidak ada data dari RS lebih dari 5 menit."),
      h("div", { class: "suara-atur" },
        h("span", { text: "Volume" }), h("div", { class: "inline" }, vol, volTeks),
        h("span", { text: "Ulangi bunyi" }), ulang,
        h("span", { text: "File suara sendiri" }), h("div", null, h("div", { class: "inline" }, inputBerkas, hapusBerkas), infoBerkas)),
      h("div", { class: "catatan-kecil" },
        "Bunyi berhenti setelah alarm di-ack (peran Teknisi/Admin) atau parameter pulih. Pengaturan ini hanya untuk browser/PC ini. ",
        "Browser baru mengizinkan suara setelah halaman diklik sekali. Untuk PC monitoring dan TV, buat shortcut Chrome dengan tambahan ",
        h("code", { text: "--autoplay-policy=no-user-gesture-required" }), " supaya suara langsung aktif tanpa klik. ",
        "Batas parameter dan delay alarm diatur Admin di menu Admin → Ambang Alarm."));
    G.modal("Suara alarm", isi, [{ teks: "Tutup", kelas: "btn-primary" }], true);
  }

  G.Suara = { evaluasi, aktifkan, siap, mainkan, bukaPengaturan, perbaruiTombol };
  konteks();
  const b = document.getElementById("btnSuara");
  if (b) b.addEventListener("click", bukaPengaturan);
  perbaruiTombol();
  setInterval(perbaruiTombol, 5000);
})();
