(function () {
  "use strict";
  const G = (window.GPI = {});
  const body = document.body;
  G.peran = body.dataset.peran || "Viewer";
  G.zona = body.dataset.zona || "WIB";
  G.bolehAksi = G.peran === "Admin" || G.peran === "Teknisi";
  G.LABEL = { purity: "Purity", rt1: "RT1", fvsa: "Fvsa", fbst: "Booster", purge: "PurgEst", data: "Data" };
  G.SATUAN = { purity: "%", rt1: "°F", fvsa: "Hz", fbst: "Hz", purge: "" };
  G.DESIMAL = { purity: 1, rt1: 0, fvsa: 1, fbst: 1, purge: 0 };
  G.PARAM = ["purity", "rt1", "fvsa", "fbst", "purge"];
  G.URUTAN = ["Kritis", "Offline", "Terlambat", "Peringatan", "Start-up", "Normal"];

  G.api = async function (url, opsi) {
    opsi = opsi || {};
    const o = { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } };
    if (opsi.json !== undefined) {
      o.method = "POST";
      o.headers["Content-Type"] = "application/json";
      o.body = JSON.stringify(opsi.json);
    }
    const r = await fetch(url, o);
    cekVersi(r.headers.get("X-GPI-Versi"));
    if (r.status === 401) {
      location.href = "/login?lanjut=" + encodeURIComponent(location.pathname);
      throw new Error("Sesi berakhir");
    }
    let d = null;
    try { d = await r.json(); } catch (e) { }
    if (!r.ok) throw new Error((d && d.galat) || "Server menjawab " + r.status);
    return d;
  };

  G.versi = body.dataset.versi || null;
  function cekVersi(v) {
    if (!v || !G.versi || v === G.versi || G._muatUlang) return;
    let terakhir = 0;
    try { terakhir = +(sessionStorage.getItem("gpi_muat_ulang") || 0); sessionStorage.setItem("gpi_muat_ulang", String(Date.now())); } catch (e) { }
    if (Date.now() - terakhir < 60000) return;
    G._muatUlang = true;
    setTimeout(() => location.reload(), 1200);
  }

  G.h = function (tag, attr) {
    const el = document.createElement(tag);
    if (attr) {
      for (const k in attr) {
        const v = attr[k];
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "html") el.innerHTML = v;
        else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else el.setAttribute(k, v === true ? "" : v);
      }
    }
    for (let i = 2; i < arguments.length; i++) tambah(el, arguments[i]);
    return el;
  };
  function tambah(el, a) {
    if (a === null || a === undefined || a === false) return;
    if (Array.isArray(a)) a.forEach((x) => tambah(el, x));
    else el.appendChild(a instanceof Node ? a : document.createTextNode(String(a)));
  }
  G.kosongkan = function (el) { while (el.firstChild) el.removeChild(el.firstChild); return el; };
  G.esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  G.angka = function (x, des) {
    if (x === null || x === undefined || isNaN(x)) return "--";
    des = des === undefined ? 1 : des;
    return Number(x).toLocaleString("id-ID", { minimumFractionDigits: des, maximumFractionDigits: des });
  };
  G.nilaiParam = (p, x) => G.angka(x, G.DESIMAL[p]);
  G.jam = (s) => (s ? s.slice(11, 16) : "-");
  G.jamDetik = (s) => (s ? s.slice(11, 19) : "-");
  G.tgl = (s) => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : "-");
  G.tglJam = (s) => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + " " + s.slice(11, 16) : "-");
  G.keDetik = (s) => (s ? Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13), +s.slice(14, 16), +s.slice(17, 19)) / 1000 : null);
  G.dariEp = function (ep, detik) {
    const d = new Date(ep * 1000), p = (n) => String(n).padStart(2, "0");
    return p(d.getUTCDate()) + "/" + p(d.getUTCMonth() + 1) + " " + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + (detik ? ":" + p(d.getUTCSeconds()) : "");
  };
  G.durasi = function (detik) {
    if (detik === null || detik === undefined) return "-";
    detik = Math.max(0, Math.round(detik));
    if (detik < 60) return detik + " dtk";
    const m = Math.floor(detik / 60);
    if (m < 60) return m + " mnt";
    const j = Math.floor(m / 60);
    if (j < 24) return j + " j " + (m % 60) + " mnt";
    return Math.floor(j / 24) + " hr " + (j % 24) + " j";
  };
  G.relatif = (detik) => (detik === null || detik === undefined ? "belum ada data" : G.durasi(detik) + " lalu");
  G.slug = (s) => String(s || "").toLowerCase().replace(/\s+/g, "-");
  G.pillStatus = (s) => G.h("span", { class: "pill-st st-" + G.slug(s), text: s === "Terlambat" ? "Data terlambat" : s });

  G.toast = function (pesan, merah) {
    const t = G.h("div", { class: "toast" + (merah ? " merah" : ""), text: pesan });
    document.getElementById("toast").appendChild(t);
    setTimeout(() => t.remove(), merah ? 6000 : 3500);
  };
  G.modal = function (judul, isi, tombol, lebar) {
    const galat = G.h("div", { class: "galat-form" });
    const tutup = () => { latar.remove(); document.removeEventListener("keydown", esc); };
    const esc = (e) => { if (e.key === "Escape") tutup(); };
    const foot = G.h("div", { class: "modal-foot" });
    (tombol || []).forEach((t) => {
      const b = G.h("button", { class: "btn " + (t.kelas || "btn-secondary"), text: t.teks });
      b.addEventListener("click", async () => {
        if (!t.aksi) return tutup();
        b.disabled = true;
        galat.textContent = "";
        try {
          const ok = await t.aksi();
          if (ok !== false) tutup();
        } catch (e) {
          galat.textContent = e.message;
        } finally {
          b.disabled = false;
        }
      });
      foot.appendChild(b);
    });
    const latar = G.h("div", { class: "modal" },
      G.h("div", { class: "modal-card" + (lebar ? " lebar" : "") },
        G.h("div", { class: "modal-head" }, G.h("h3", { text: judul }), G.h("button", { class: "btn btn-ghost btn-sm", text: "Tutup", onclick: tutup })),
        G.h("div", { class: "modal-body" }, isi, galat), foot));
    latar.addEventListener("mousedown", (e) => { if (e.target === latar) tutup(); });
    document.addEventListener("keydown", esc);
    document.body.appendChild(latar);
    const f = latar.querySelector("input, textarea, select");
    if (f) f.focus();
    return tutup;
  };

  G.ack = function (ev, selesai) {
    const ta = G.h("textarea", { rows: 3, maxlength: 500, placeholder: "Contoh: sudah telepon teknisi RS, filter diganti" });
    const isi = G.h("div", null,
      G.h("p", { style: { marginTop: 0 } }, G.h("b", { text: (ev.nama_rs || ev.kode_lokasi || "") + " – " + ev.label }), " ",
        G.h("span", { class: "lv-pill lv-" + ev.level, text: ev.level })),
      G.h("p", { class: "muted kecil", text: (ev.keterangan || "") + " · mulai " + G.tglJam(ev.mulai) }),
      G.h("label", { class: "f", text: "Catatan tindakan (disarankan)" }), ta);
    G.modal("Acknowledge alarm", isi, [
      { teks: "Batal" },
      { teks: "Ack", kelas: "btn-primary", aksi: async () => {
          await G.api("/api/alarm/" + ev.id + "/ack", { json: { catatan: ta.value } });
          G.toast("Alarm di-ack");
          if (selesai) selesai();
        } },
    ]);
  };

  G.tabelAlarm = function (rows, sekarang, opsi) {
    opsi = opsi || {};
    if (!rows.length) return G.h("div", { class: "kosong", text: opsi.kosong || "Tidak ada alarm." });
    const tNow = G.keDetik(sekarang);
    const tb = G.h("tbody");
    rows.forEach((e) => {
      const sat = e.satuan || "";
      const dur = (e.selesai ? G.keDetik(e.selesai) : tNow) - G.keDetik(e.mulai);
      const nilai = e.parameter === "data" ? "–" :
        G.nilaiParam(e.parameter, e.nilai_awal) + sat + (e.nilai_puncak !== null && e.nilai_puncak !== e.nilai_awal ? " → puncak " + G.nilaiParam(e.parameter, e.nilai_puncak) + sat : "");
      let ack;
      if (e.ack_waktu) ack = G.h("div", null, G.h("div", { text: "✓ " + e.ack_oleh + " " + G.tglJam(e.ack_waktu) }), e.catatan ? G.h("div", { class: "sub", text: e.catatan }) : null);
      else if (G.bolehAksi) ack = G.h("button", { class: "btn btn-primary btn-tiny", text: "Ack", onclick: () => G.ack(e, opsi.muatUlang) });
      else ack = G.h("span", { class: "muted", text: "belum" });
      tb.appendChild(G.h("tr", { class: e.selesai ? "" : "aktif-row" },
        G.h("td", null, G.h("div", { text: G.tglJam(e.mulai) }), e.naik_kritis ? G.h("div", { class: "sub", text: "naik Kritis " + G.jam(e.naik_kritis) }) : null),
        opsi.tanpaUnit ? null : G.h("td", null, G.h("a", { href: "/unit/" + e.mesin_id, text: e.nama_rs || e.kode_lokasi }), G.h("div", { class: "sub", text: e.kode_unit })),
        G.h("td", null, G.h("b", { text: e.label })),
        G.h("td", null, G.h("span", { class: "lv-pill lv-" + e.level, text: e.level }), e.saat_maintenance ? G.h("div", { class: "sub", text: "saat maintenance" }) : null),
        G.h("td", null, G.h("div", { text: nilai }), G.h("div", { class: "sub", text: e.keterangan || "" })),
        G.h("td", null, e.selesai ? G.h("div", { text: "pulih " + G.tglJam(e.selesai) }) : G.h("b", { class: "lv2", text: "aktif" }), G.h("div", { class: "sub", text: G.durasi(dur) })),
        G.h("td", null, ack)));
    });
    return G.h("table", { class: "t" },
      G.h("thead", null, G.h("tr", null, G.h("th", { text: "Mulai" }), opsi.tanpaUnit ? null : G.h("th", { text: "Unit" }), G.h("th", { text: "Parameter" }),
        G.h("th", { text: "Level" }), G.h("th", { text: "Nilai / keterangan" }), G.h("th", { text: "Status" }), G.h("th", { text: "Ack" }))), tb);
  };

  G.terapkanSistem = function (d) {
    const ban = document.getElementById("banner");
    if (ban) {
      G.kosongkan(ban);
      const s = d.sistem || {};
      if (s.bridge && s.bridge.hidup === false)
        ban.appendChild(G.h("div", { class: "banner merah" }, G.h("b", { text: "Bridge DOCSApp → MySQL tidak berjalan." }),
          G.h("span", { text: " Heartbeat terakhir " + G.relatif(s.bridge.umur) + ". Semua unit akan terlihat Offline walau mesinnya jalan. Cek jendela docs_ke_mysql.py di PC monitoring." })));
      else if (s.bridge && s.bridge.hidup === null)
        ban.appendChild(G.h("div", { class: "banner kuning" }, G.h("b", { text: "Heartbeat bridge belum ada." }),
          G.h("span", { text: " Pastikan bridge versi 2 (folder bridge) yang dijalankan." })));
      if (s.mesin_alarm && !s.mesin_alarm.hidup)
        ban.appendChild(G.h("div", { class: "banner merah" }, G.h("b", { text: "Mesin alarm tidak berjalan." }),
          G.h("span", { text: " Status dan alarm tidak diperbarui. Restart JALANKAN_DASHBOARD.bat dan cek server\\log\\dashboard.log." })));
    }
    if (G.Suara && d.unit) G.Suara.evaluasi(d);
    const nb = document.getElementById("navAlarm");
    if (nb && d.unit) {
      const n = d.unit.reduce((a, u) => a + u.alarm.belum_ack, 0);
      nb.hidden = !n;
      nb.textContent = n;
    }
  };

  let tSukses = null, gagal = false;
  G.tandaiUpdate = function (ok) {
    if (ok) { tSukses = Date.now(); gagal = false; } else gagal = true;
    gambarPil();
  };
  function gambarPil() {
    const pil = document.getElementById("pillUpdate");
    if (!pil) return;
    const tx = pil.querySelector(".tx");
    if (tSukses === null) { pil.className = "status-pill" + (gagal ? " putus" : ""); tx.textContent = gagal ? "server tidak terjangkau" : "memuat…"; return; }
    const s = Math.round((Date.now() - tSukses) / 1000);
    pil.className = "status-pill " + (gagal || s > 30 ? "putus" : s > 12 ? "lambat" : "ok");
    tx.textContent = (gagal ? "gagal memuat · " : "diperbarui ") + (s < 2 ? "baru saja" : s + " dtk lalu");
  }
  setInterval(gambarPil, 1000);

  G.pantauSistem = function () {
    const jalan = async () => {
      try { G.terapkanSistem(await G.api("/api/ringkasan")); } catch (e) { }
    };
    jalan();
    setInterval(jalan, 10000);
  };

  const IKON_BULAN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
  const IKON_MATAHARI = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
  function ikonTema() {
    const b = document.getElementById("btnTema");
    if (!b || !window.GPITema) return;
    const gelap = window.GPITema.sekarang() === "dark";
    b.innerHTML = gelap ? IKON_MATAHARI : IKON_BULAN;
    b.title = gelap ? "Ganti ke tema terang" : "Ganti ke tema gelap";
    b.setAttribute("aria-label", b.title);
  }
  const btnTema = document.getElementById("btnTema");
  if (btnTema) btnTema.addEventListener("click", () => window.GPITema.ganti());
  window.addEventListener("gpi-tema", ikonTema);
  ikonTema();

  G.ulang = function (fungsi, ms) {
    let timer = null;
    const putar = async () => {
      clearTimeout(timer);
      try { await fungsi(); } catch (e) { console.error(e); }
      timer = setTimeout(putar, document.hidden ? ms * 4 : ms);
    };
    document.addEventListener("visibilitychange", () => { if (!document.hidden) putar(); });
    putar();
    return { segera: putar };
  };
})();
