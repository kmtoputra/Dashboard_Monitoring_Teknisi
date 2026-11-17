(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;

  G.sparkline = function (titik, sekarangEp, batas, lebar, tinggi) {
    lebar = lebar || 220; tinggi = tinggi || 46;
    const nilai = titik.map((t) => t[1]).filter((v) => v !== null);
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + lebar + " " + tinggi);
    svg.setAttribute("preserveAspectRatio", "none");
    if (!nilai.length) {
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", lebar / 2); t.setAttribute("y", tinggi / 2 + 4); t.setAttribute("text-anchor", "middle");
      t.setAttribute("font-size", "11"); t.setAttribute("fill", "currentColor"); t.setAttribute("opacity", ".45");
      t.textContent = "tidak ada data 1 jam terakhir";
      svg.appendChild(t);
      return svg;
    }
    let lo = Math.min.apply(null, nilai), hi = Math.max.apply(null, nilai);
    const garis = [];
    if (batas) {
      if (batas.normal_min !== null && batas.normal_min !== undefined) { garis.push([batas.normal_min, "var(--yellow)"]); lo = Math.min(lo, batas.normal_min); hi = Math.max(hi, batas.normal_min); }
      if (batas.kritis_min !== null && batas.kritis_min !== undefined && batas.kritis_min >= lo - 1.5) { garis.push([batas.kritis_min, "var(--red)"]); lo = Math.min(lo, batas.kritis_min); }
    }
    const pad = Math.max((hi - lo) * 0.12, 0.3);
    lo -= pad; hi += pad;
    const x0 = sekarangEp - 3600;
    const X = (t) => ((t - x0) / 3600) * lebar;
    const Y = (v) => tinggi - ((v - lo) / (hi - lo)) * tinggi;
    garis.forEach((g) => {
      const l = document.createElementNS(svgNS, "line");
      l.setAttribute("x1", 0); l.setAttribute("x2", lebar); l.setAttribute("y1", Y(g[0])); l.setAttribute("y2", Y(g[0]));
      l.setAttribute("stroke", g[1]); l.setAttribute("stroke-width", "1"); l.setAttribute("stroke-dasharray", "4 3");
      l.setAttribute("vector-effect", "non-scaling-stroke");
      svg.appendChild(l);
    });
    let d = "", pena = false, tSebelum = null;
    titik.forEach((t) => {
      if (t[1] === null || (tSebelum !== null && t[0] - tSebelum > 180)) pena = false;
      if (t[1] !== null) { d += (pena ? "L" : "M") + X(t[0]).toFixed(1) + " " + Y(t[1]).toFixed(1); pena = true; }
      tSebelum = t[0];
    });
    const p = document.createElementNS(svgNS, "path");
    p.setAttribute("d", d); p.setAttribute("fill", "none"); p.setAttribute("stroke", "var(--blue)");
    p.setAttribute("stroke-width", "1.8"); p.setAttribute("vector-effect", "non-scaling-stroke"); p.setAttribute("stroke-linejoin", "round");
    svg.appendChild(p);
    return svg;
  };

  G.kartu = function (u, d) {
    const st = u.status;
    const lv = (p) => (u.level[p] === 2 ? "lv2" : u.level[p] === 1 ? "lv1" : "");
    const val = (p) => h("b", { class: lv(p), text: G.nilaiParam(p, u.nilai[p]) }, G.SATUAN[p] ? h("small", { text: G.SATUAN[p] }) : null);
    const masalah = G.PARAM.filter((p) => u.level[p] >= 1).map((p) => h("div", { class: "catatan " + lv(p),
      text: G.LABEL[p] + " " + G.nilaiParam(p, u.nilai[p]) + G.SATUAN[p] + " (" + u.teks[p] + ")" }));
    let kiriBawah;
    if (u.umur_detik === null) kiriBawah = h("span", { text: "belum pernah ada data" });
    else kiriBawah = h("span", null, h("span", { class: "titik " + (st === "Offline" ? "mati" : st === "Terlambat" ? "lambat" : "") }), " data ",
      h("span", { class: "umur", "data-umur": u.umur_detik, text: G.relatif(u.umur_detik) }));
    let kananBawah = null;
    if (u.alarm.aktif) kananBawah = h("span", { class: "alm", text: u.alarm.aktif + " alarm aktif" + (u.alarm.belum_ack ? " · " + u.alarm.belum_ack + " belum ack" : "") });
    else if (st === "Start-up" && u.startup_sampai) kananBawah = h("span", { text: "alarm purity ditahan s.d. " + G.jam(u.startup_sampai) });
    else if (!u.ada_aturan) kananBawah = h("span", { text: "belum ada ambang alarm" });
    return h("a", { class: "kartu k-" + G.slug(st), href: "/unit/" + u.id },
      h("div", { class: "pita" }),
      h("div", { class: "isi" },
        h("div", { class: "atas" },
          h("div", null, h("div", { class: "nama", text: u.nama_rs || u.kode_lokasi }),
            h("div", { class: "meta", text: [u.kota, u.kode_unit, u.jenis_mesin].filter(Boolean).join(" · ") })),
          h("div", { class: "kanan" }, G.pillStatus(st), u.status_mesin === "Maintenance" ? h("span", { class: "tag-maint", text: "Maintenance" }) : null)),
        h("div", { class: "utama" },
          h("div", null, h("div", { class: "lbl", text: "Purity O₂" }),
            h("div", { class: "besar " + lv("purity"), text: G.nilaiParam("purity", u.nilai.purity) }, h("small", { text: "%" }))),
          h("div", { class: "spark", title: "Purity rata-rata per menit, 1 jam terakhir" }, G.sparkline(u.spark, d.sekarang_ep, u.batas_purity))),
        masalah.length ? h("div", null, masalah) : null,
        h("div", { class: "param" },
          h("div", { title: "RT1 rata-rata 1 menit" }, h("span", { text: "RT1 · 1m" }), val("rt1")),
          h("div", { title: "Fvsa rata-rata 1 menit" }, h("span", { text: "Fvsa" }), val("fvsa")),
          h("div", { title: "Booster (Fbst) rata-rata 1 menit" }, h("span", { text: "Booster" }), val("fbst")),
          h("div", { title: "PurgEst terbaru" }, h("span", { text: "PurgEst" }), val("purge")))),
      h("div", { class: "bawah" }, kiriBawah, h("span", { class: "kanan" }, kananBawah)));
  };

  G.tombolHitung = function (hitung, pilih, klik) {
    return G.URUTAN.map((s) => {
      const n = hitung[s] || 0;
      return h("button", { class: (s === "Kritis" ? "kritis" : "") + (s === "Kritis" && n ? " ada" : "") + (n ? "" : " nol") + (pilih === s ? " pilih" : ""),
        title: klik ? "Tampilkan hanya " + s : s, onclick: klik ? () => klik(s) : null },
        h("i", { class: "i-" + G.slug(s) }), h("b", { text: n }), h("span", { text: s === "Terlambat" ? "Data terlambat" : s }));
    });
  };

  let tAmbil = Date.now();
  G.catatAmbil = () => { tAmbil = Date.now(); };
  setInterval(() => {
    const tambah = Math.round((Date.now() - tAmbil) / 1000);
    document.querySelectorAll(".umur[data-umur]").forEach((el) => { el.textContent = G.relatif(+el.dataset.umur + tambah); });
  }, 1000);
})();
