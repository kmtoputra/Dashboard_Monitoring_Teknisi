(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  const MID = document.body.dataset.mesin;
  const SKALA = { purity: [85, 100], rt1: [150, 275], fvsa: [0, 30], fbst: [0, 40], purge: [100, 200] };
  const PAD_MIN = { purity: 0.3, rt1: 2, fvsa: 0.5, fbst: 0.5, purge: 2 };
  const warna = (p) => css("--s-" + p);
  const NAMA_SUMBER = { terbaru: "nilai terbaru", avg1m: "rata-rata 1 menit" };
  let info = null, rentang = "1j", custom = null, grafik = {}, modeGrafik = null, timerTren = null;

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function teksBatas(p, a) {
    if (!a) return "belum ada ambang alarm";
    const s = G.SATUAN[p], n = (x) => G.angka(x, x % 1 ? 1 : 0), bag = [];
    if (a.normal_min !== null && a.normal_max !== null) bag.push("Normal " + n(a.normal_min) + "–" + n(a.normal_max) + (s ? " " + s : ""));
    else if (a.normal_min !== null) bag.push("Normal ≥ " + n(a.normal_min) + (s ? " " + s : ""));
    else if (a.normal_max !== null) bag.push("Normal ≤ " + n(a.normal_max) + (s ? " " + s : ""));
    if (a.maks1m_max !== null) bag.push("maks 1m ≤ " + n(a.maks1m_max));
    if (a.kritis_min !== null) bag.push("Kritis < " + n(a.kritis_min));
    if (a.kritis_max !== null) bag.push("Kritis > " + n(a.kritis_max));
    return bag.join(" · ");
  }

  function gauge(p, nilai, a) {
    let lo = SKALA[p][0], hi = SKALA[p][1];
    if (a) [a.kritis_min, a.normal_min, a.normal_max, a.kritis_max, a.maks1m_max].forEach((x) => {
      if (x === null) return;
      if (x <= lo) lo = x - (hi - lo) * 0.06;
      if (x >= hi) hi = x + (hi - lo) * 0.06;
    });
    const seg = [];
    if (a) {
      let cur = lo;
      const ke = (to, warna) => { to = Math.min(Math.max(to, lo), hi); if (to > cur) { seg.push([cur, to, warna]); cur = to; } };
      if (a.kritis_min !== null) ke(a.kritis_min, "var(--red)");
      if (a.normal_min !== null) ke(a.normal_min, "var(--yellow)");
      if (a.normal_max !== null) ke(a.normal_max, "var(--green)");
      if (a.kritis_max !== null) ke(a.kritis_max, a.normal_max !== null ? "var(--yellow)" : "var(--green)");
      ke(hi, a.kritis_max !== null ? "var(--red)" : a.normal_max !== null ? "var(--yellow)" : "var(--green)");
    } else seg.push([lo, hi, "var(--border)"]);
    const R = 78, CX = 100, CY = 98;
    const titik = (v, r) => {
      const fr = Math.min(Math.max((v - lo) / (hi - lo), 0), 1), ang = Math.PI * (1 - fr);
      return [CX + r * Math.cos(ang), CY - r * Math.sin(ang)];
    };
    let svg = '<svg class="gauge" viewBox="0 0 200 116" aria-hidden="true">';
    seg.forEach((s) => {
      const p1 = titik(s[0], R), p2 = titik(s[1], R);
      svg += '<path d="M' + p1[0].toFixed(2) + " " + p1[1].toFixed(2) + " A" + R + " " + R + " 0 0 1 " + p2[0].toFixed(2) + " " + p2[1].toFixed(2) +
        '" fill="none" stroke="' + s[2] + '" stroke-width="13" opacity=".85"/>';
    });
    if (nilai !== null && nilai !== undefined) {
      const ujung = titik(nilai, R - 20);
      svg += '<line x1="' + CX + '" y1="' + CY + '" x2="' + ujung[0].toFixed(2) + '" y2="' + ujung[1].toFixed(2) +
        '" stroke="var(--text)" stroke-width="3.5" stroke-linecap="round"/><circle cx="' + CX + '" cy="' + CY + '" r="6" fill="var(--text)"/>';
    }
    const des = p === "purity" ? 0 : 0;
    svg += '<text x="22" y="114" font-size="11" fill="var(--text-tert)" text-anchor="middle">' + G.angka(lo, des) + "</text>" +
      '<text x="178" y="114" font-size="11" fill="var(--text-tert)" text-anchor="middle">' + G.angka(hi, des) + "</text></svg>";
    return svg;
  }

  async function muatInfo() {
    info = await G.api("/api/unit/" + MID);
    G.tandaiUpdate(true);
    const u = info.unit;
    document.title = (u.nama_rs || u.kode_lokasi) + " · Detail · GPI";
    document.getElementById("judulUnit").textContent = (u.nama_rs || u.kode_lokasi) + " – " + u.jenis_mesin;
    document.getElementById("subUnit").textContent = [u.kota + (u.provinsi ? ", " + u.provinsi : ""), u.kode_unit,
      u.base_file_name ? "Base File Name " + u.base_file_name : "Base File Name belum diisi", u.router].filter(Boolean).join(" · ");
    const st = G.kosongkan(document.getElementById("statusUnit"));
    st.append(G.pillStatus(info.status), " ", h("span", { class: "muted kecil", text: info.sejak ? "sejak " + G.tglJam(info.sejak) : "" }));
    if (u.status_mesin === "Maintenance") st.append(" ", h("span", { class: "tag-maint", text: "Maintenance" }));
    const bm = document.getElementById("btnMaint");
    bm.hidden = !G.bolehAksi || u.status_mesin === "Nonaktif";
    bm.textContent = u.status_mesin === "Maintenance" ? "Akhiri Maintenance" : "Mode Maintenance";

    const strip = G.kosongkan(document.getElementById("infoStrip"));
    strip.append(h("span", null, "Data terakhir ", h("b", { text: info.data_terakhir ? G.tglJam(info.data_terakhir) + ":" + info.data_terakhir.slice(17, 19) : "-" }),
      " (", h("span", { class: "umur", "data-umur": info.umur_detik === null ? "" : info.umur_detik, text: G.relatif(info.umur_detik) }), ")"));
    if (info.sesi) strip.append(h("span", null, "File ", h("b", { text: info.sesi.nama_sumber || "-" }), " · RecNo ", h("b", { text: info.sesi.rec_no_terakhir })));
    if (info.status === "Start-up" && info.startup_sampai) strip.append(h("span", { class: "lv1" }, "Start-up: alarm purity ditahan sampai ", h("b", { text: G.jam(info.startup_sampai) })));
    tAmbil = Date.now();

    const panel = G.kosongkan(document.getElementById("panel"));
    G.PARAM.forEach((p) => {
      const a = info.aturan[p], v = info.nilai[p], lv = info.level[p];
      const arah = { naik: "↑", turun: "↓", datar: "→" }[info.tren[p]] || "";
      const el = h("div", { class: "panel" + (lv === 2 ? " lvbg2" : lv === 1 ? " lvbg1" : "") },
        h("div", { class: "kepala" }, h("b", { text: G.LABEL[p] }), h("span", { text: NAMA_SUMBER[a ? a.sumber : (p === "purity" || p === "purge" ? "terbaru" : "avg1m")] })),
        h("div", { html: gauge(p, v, a) }),
        h("div", { class: "nilai " + (lv === 2 ? "lv2" : lv === 1 ? "lv1" : "") }, G.nilaiParam(p, v), G.SATUAN[p] ? h("small", { text: G.SATUAN[p] }) : null,
          arah ? h("span", { class: "arah", title: "dibanding rata-rata 5 menit lalu", text: arah }) : null),
        h("div", { class: "batas", text: teksBatas(p, a) }),
        h("div", { class: "ket " + (lv === 2 ? "lv2" : "lv1"), text: lv >= 1 ? info.teks[p] : "" }));
      panel.appendChild(el);
    });

    isiKepalaWidget();
    const lain = G.kosongkan(document.getElementById("lain"));
    [["State", info.lain.state], ["Flow Est", info.lain.flow_est], ["PS1", info.lain.ps1], ["Cycle count", info.lain.cyccnt], ["VSA cmd", info.lain.vsacmd],
      ["Zona RS", u.zona_waktu]].forEach((x) => lain.appendChild(h("div", null, h("span", { text: x[0] }), h("b", { text: x[1] === null || x[1] === undefined ? "-" : x[1] }))));
  }
  let tAmbil = Date.now();
  setInterval(() => {
    const el = document.querySelector("#infoStrip .umur");
    if (el && el.dataset.umur !== "") el.textContent = G.relatif(+el.dataset.umur + Math.round((Date.now() - tAmbil) / 1000));
  }, 1000);

  function rentangY(p, min, max, a) {
    if (min === null || max === null || !isFinite(min)) return SKALA[p].slice();
    let lo = min, hi = max;
    if (a) [a.normal_min, a.normal_max, a.maks1m_max].forEach((x) => { if (x !== null) { lo = Math.min(lo, x); hi = Math.max(hi, x); } });
    if (a) [a.kritis_min, a.kritis_max].forEach((x) => {
      const span = Math.max(hi - lo, 1);
      if (x !== null && x >= lo - span * 0.4 && x <= hi + span * 0.4) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
    });
    const pad = Math.max((hi - lo) * 0.08, PAD_MIN[p]);
    return [lo - pad, hi + pad];
  }

  function garisAmbang(u, a) {
    if (!a) return;
    const ctx = u.ctx, b = u.bbox, dpr = devicePixelRatio || 1;
    const garis = [];
    if (a.normal_min !== null) garis.push([a.normal_min, css("--yellow")]);
    if (a.normal_max !== null) garis.push([a.normal_max, css("--yellow")]);
    if (a.maks1m_max !== null) garis.push([a.maks1m_max, css("--yellow")]);
    if (a.kritis_min !== null) garis.push([a.kritis_min, css("--red")]);
    if (a.kritis_max !== null) garis.push([a.kritis_max, css("--red")]);
    ctx.save();
    ctx.lineWidth = 1.2 * dpr;
    ctx.setLineDash([6 * dpr, 4 * dpr]);
    ctx.font = 10 * dpr + "px -apple-system, Segoe UI, sans-serif";
    ctx.textAlign = "right";
    garis.forEach((g) => {
      const y = u.valToPos(g[0], "y", true);
      if (y < b.top || y > b.top + b.height) return;
      ctx.strokeStyle = g[1];
      ctx.beginPath(); ctx.moveTo(b.left, y); ctx.lineTo(b.left + b.width, y); ctx.stroke();
      ctx.fillStyle = g[1];
      ctx.fillText(G.angka(g[0], g[0] % 1 ? 1 : 0), b.left + b.width - 4 * dpr, y - 3 * dpr);
    });
    ctx.restore();
  }

  function labelX(u, splits, ai, ruang, langkah) {
    const span = u.scales.x.max - u.scales.x.min, p = (n) => String(n).padStart(2, "0");
    return splits.map((ts) => {
      const d = new Date(ts * 1000), jam = p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()), tgl = p(d.getUTCDate()) + "/" + p(d.getUTCMonth() + 1);
      if (span <= 26 * 3600) return jam;
      if (langkah >= 86400) return tgl;
      return tgl + "\n" + jam;
    });
  }

  const tzDate = (ts) => { const d = new Date(ts * 1e3); return new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()); };

  const JUDUL = { purity: "Purity O₂", rt1: "RT1", fvsa: "Fvsa", fbst: "Booster", purge: "PurgEst" };
  const SUB = { purity: "AVGPUR", rt1: "suhu RTD-1", fvsa: "frekuensi VSA", fbst: "frekuensi booster (Fbst)", purge: "estimasi purge" };
  const TINGGI = 190;
  const RATA1M = { rt1: true, fvsa: true, fbst: true };
  function rata1m(t, v) {
    const out = new Array(t.length);
    let j = 0, jumlah = 0, n = 0;
    for (let i = 0; i < t.length; i++) {
      if (v[i] === null || v[i] === undefined) { out[i] = null; j = i + 1; jumlah = 0; n = 0; continue; }
      jumlah += v[i]; n++;
      while (t[i] - t[j] >= 60) { if (v[j] !== null && v[j] !== undefined) { jumlah -= v[j]; n--; } j++; }
      out[i] = n ? jumlah / n : null;
    }
    return out;
  }
  let aturanTren = {}, widget = {}, pengamat = null, trenTerakhir = null;

  function opsiGrafik(p, mode, lebar) {
    const w = warna(p);
    const gradasi = (u) => {
      const b = u.bbox, g = u.ctx.createLinearGradient(0, b.top, 0, b.top + b.height);
      g.addColorStop(0, w + "3d");
      g.addColorStop(1, w + "00");
      return g;
    };
    const series = [{}];
    if (mode === "mentah" && RATA1M[p]) series.push({ stroke: w + "55", width: 1, spanGaps: false, points: { show: false } },
      { stroke: w, width: 2.4, spanGaps: false, points: { show: false } });
    else if (mode === "mentah") series.push({ stroke: w, width: 2, fill: gradasi, spanGaps: false, points: { show: false } });
    else series.push({ stroke: w, width: 2, spanGaps: false, points: { show: false } },
      { stroke: "transparent", width: 1, points: { show: false } },
      { stroke: "transparent", width: 1, points: { show: false } });
    const sumbu = css("--axis"), grid = css("--grid");
    return {
      width: lebar, height: TINGGI, tzDate, series,
      legend: { show: false },
      padding: [12, 10, 0, 0],
      cursor: { sync: { key: "gpi-" + MID }, drag: { x: true, y: false }, points: { size: 8, fill: w, stroke: css("--card"), width: 2 } },
      scales: { x: { time: true }, y: { range: (u, min, max) => rentangY(p, min, max, aturanTren[p]) } },
      axes: [{ stroke: sumbu, grid: { show: false }, ticks: { stroke: grid, width: 1, size: 4 }, values: labelX, font: "11px -apple-system, Segoe UI, sans-serif" },
        { stroke: sumbu, size: 44, grid: { stroke: grid, width: 1 }, ticks: { show: false }, font: "11px -apple-system, Segoe UI, sans-serif",
          values: (u, vals) => vals.map((v) => G.angka(v, Math.abs(u.scales.y.max - u.scales.y.min) < 5 ? 1 : 0)) }],
      bands: mode === "agregat" ? [{ series: [3, 2], fill: w + "33" }] : [],
      hooks: { draw: [(u) => garisAmbang(u, aturanTren[p])], setCursor: [(u) => bacaKursor(p, u)] },
    };
  }

  function bacaKursor(p, u) {
    const ww = widget[p];
    if (!ww) return;
    const i = u.cursor.idx;
    if (i === null || i === undefined || u.data[1][i] === null || u.data[1][i] === undefined) {
      ww.hover.textContent = "";
      ww.waktu.hidden = false;
      return;
    }
    const des = G.DESIMAL[p], sat = G.SATUAN[p] ? " " + G.SATUAN[p] : "";
    let t = G.dariEp(u.data[0][i], modeGrafik === "mentah") + " · " + G.angka(u.data[1][i], des) + sat;
    if (u.data.length > 3 && u.data[2][i] !== null) t += " (" + G.angka(u.data[2][i], des) + "–" + G.angka(u.data[3][i], des) + ")";
    else if (u.data.length === 3 && u.data[2][i] !== null) t += " · rata-rata 1m " + G.angka(u.data[2][i], des) + sat;
    ww.hover.textContent = t;
    ww.waktu.hidden = true;
  }

  function dataGrafik(p, d) {
    if (d.mode === "mentah" && RATA1M[p]) return [d.t, d.seri[p], d.seri[p + "_r1m"]];
    if (d.mode === "mentah") return [d.t, d.seri[p]];
    return [d.t, d.seri[p + "_avg"], d.seri[p + "_min"], d.seri[p + "_max"]];
  }

  function statistik(p, d) {
    const ada = (x) => x !== null && x !== undefined;
    const v = (d.mode === "mentah" ? d.seri[p] : d.seri[p + "_avg"]).filter(ada);
    if (!v.length) return [h("span", { text: "Tidak ada data pada rentang ini" })];
    const lo = d.mode === "mentah" ? v : d.seri[p + "_min"].filter(ada);
    const hi = d.mode === "mentah" ? v : d.seri[p + "_max"].filter(ada);
    const min = lo.reduce((a, x) => (x < a ? x : a), Infinity), max = hi.reduce((a, x) => (x > a ? x : a), -Infinity);
    const rata = v.reduce((a, x) => a + x, 0) / v.length;
    const des = G.DESIMAL[p];
    const sel = (label, nilai, kelas, judul) => h("div", { title: judul || null }, h("span", { text: label }), h("b", { class: kelas || "", text: nilai }));
    const hasil = [sel("Min", G.angka(min, des)), sel("Rata-rata", G.angka(rata, des)), sel("Maks", G.angka(max, des))];
    const a = aturanTren[p];
    if (a && (a.normal_min !== null || a.normal_max !== null)) {
      const dasar = d.mode === "mentah" && RATA1M[p] ? d.seri[p + "_r1m"].filter(ada) : v;
      const luar = (dasar.filter((x) => (a.normal_min !== null && x < a.normal_min) || (a.normal_max !== null && x > a.normal_max)).length / dasar.length) * 100;
      hasil.push(sel("Luar normal", G.angka(luar, luar > 0 && luar < 1 ? 1 : 0) + "%", luar >= 5 ? "lv2" : luar > 0 ? "lv1" : "",
        "Persen waktu nilai berada di luar batas normal" + (RATA1M[p] ? " (dihitung dari rata-rata 1 menit, sama dengan alarm)" : "")));
    }
    return hasil;
  }

  function isiKepalaWidget() {
    if (!info) return;
    const basi = info.umur_detik === null || info.umur_detik > 60;
    G.PARAM.forEach((p) => {
      const ww = widget[p];
      if (!ww) return;
      const lv = info.level[p], a = info.aturan[p];
      ww.el.classList.toggle("lvbg1", !basi && lv === 1);
      ww.el.classList.toggle("lvbg2", !basi && lv === 2);
      const v = info.nilai[p];
      if (v === null || v === undefined) G.kosongkan(ww.nilai).append("—");
      else G.kosongkan(ww.nilai).append(G.nilaiParam(p, v), G.SATUAN[p] ? h("small", { text: G.SATUAN[p] }) : "");
      ww.nilai.className = "w-nilai" + (basi ? " basi" : lv === 2 ? " lv2" : lv === 1 ? " lv1" : "");
      let chip;
      if (!info.data_terakhir) chip = ["abu", "◷ Belum ada data"];
      else if (basi) chip = ["abu", "◷ Data lama"];
      else if (!a || lv === null || lv === undefined) chip = ["abu", "Tanpa ambang"];
      else chip = lv === 2 ? ["merah", "● Kritis"] : lv === 1 ? ["kuning", "▲ Di luar normal"] : ["hijau", "✓ Normal"];
      ww.status.className = "w-status " + chip[0];
      ww.status.textContent = chip[1];
      ww.sumber.textContent = SUB[p] + " · " + NAMA_SUMBER[a ? a.sumber : (p === "purity" || p === "purge" ? "terbaru" : "avg1m")];
      ww.batas.textContent = teksBatas(p, a);
      ww.waktu.className = "w-waktu" + (basi ? " lv1" : "");
      ww.waktu.textContent = info.data_terakhir ? (basi ? "data terakhir " + G.tglJam(info.data_terakhir) : "data " + G.relatif(info.umur_detik)) : "belum ada data";
    });
    if (trenTerakhir) isiKosong(trenTerakhir);
  }

  function isiKosong(d) {
    G.PARAM.forEach((p) => {
      const ww = widget[p];
      if (!ww) return;
      const adaData = (d.mode === "mentah" ? d.seri[p] : d.seri[p + "_avg"]).some((x) => x !== null);
      ww.kosong.hidden = adaData;
      if (adaData) return;
      G.kosongkan(ww.kosong).append(h("b", { text: "Tidak ada data pada rentang ini" }),
        h("span", { text: info && info.data_terakhir ? "Data terakhir masuk " + G.tglJam(info.data_terakhir) + ". Cek DOCSApp sudah Start Log." : "Unit ini belum pernah mengirim data." }),
        rentang !== "7h" ? h("button", { class: "btn btn-secondary btn-sm", text: "Lihat 7 hari", onclick: () => pilihRentang("7h") }) : null);
    });
  }

  function bangunWidget(d) {
    Object.values(grafik).forEach((g) => g.destroy());
    if (pengamat) pengamat.disconnect();
    grafik = {};
    widget = {};
    const wadah = G.kosongkan(document.getElementById("grafik"));
    G.PARAM.forEach((p) => {
      const ww = { nilai: h("div", { class: "w-nilai" }), status: h("span", { class: "w-status" }), sumber: h("span", { class: "w-sumber" }),
        batas: h("div", { class: "w-batas" }), waktu: h("span", { class: "w-waktu" }), hover: h("span", { class: "w-hover" }),
        stat: h("div", { class: "w-stat" }), plot: h("div", { class: "w-plot" }), kosong: h("div", { class: "w-kosong", hidden: true }) };
      ww.el = h("section", { class: "widget w-" + p, "data-p": p },
        h("div", { class: "w-atas" },
          h("div", { class: "w-judul" }, h("i", { class: "w-tanda" }), h("div", null, h("b", { text: JUDUL[p] }), ww.sumber)),
          ww.status),
        h("div", { class: "w-angka" }, ww.nilai, h("div", { class: "w-kanan" }, ww.waktu, ww.hover)),
        ww.batas,
        h("div", { class: "w-plot-wrap" }, ww.plot, ww.kosong),
        ww.stat);
      wadah.appendChild(ww.el);
      widget[p] = ww;
    });
    G.PARAM.forEach((p) => { grafik[p] = new uPlot(opsiGrafik(p, d.mode, Math.floor(widget[p].plot.clientWidth) || 400), dataGrafik(p, d), widget[p].plot); });
    pengamat = new ResizeObserver((entri) => entri.forEach((e) => {
      const p = e.target.dataset.p, lebar = Math.floor(widget[p].plot.clientWidth);
      if (grafik[p] && lebar > 0 && Math.abs(grafik[p].width - lebar) > 2) grafik[p].setSize({ width: lebar, height: TINGGI });
    }));
    G.PARAM.forEach((p) => pengamat.observe(widget[p].el));
    modeGrafik = d.mode;
    isiKepalaWidget();
  }

  function urlRentang(dasar) {
    let q = "rentang=" + rentang;
    if (rentang === "custom" && custom) q += "&dari=" + encodeURIComponent(custom[0]) + "&sampai=" + encodeURIComponent(custom[1]);
    return dasar + (dasar.includes("?") ? "&" : "?") + q;
  }

  async function muatTren(paksa) {
    clearTimeout(timerTren);
    let d;
    try {
      d = await G.api(urlRentang("/api/unit/" + MID + "/tren"));
    } catch (e) {
      G.toast("Grafik gagal dimuat: " + e.message, true);
      return;
    }
    const cat = d.mode === "mentah" ? "data per detik" : "agregat " + (d.langkah_menit > 1 ? d.langkah_menit + " menit" : "1 menit") + " · garis = rata-rata, area = min–maks";
    document.getElementById("modeCat").textContent = G.dariEp(d.dari) + " – " + G.dariEp(d.sampai) + " " + G.zona + " · " + cat;
    if (d.mode === "mentah") Object.keys(RATA1M).forEach((p) => { d.seri[p + "_r1m"] = rata1m(d.t, d.seri[p]); });
    aturanTren = d.aturan;
    trenTerakhir = d;
    if (paksa === true || modeGrafik !== d.mode || !grafik.purity) bangunWidget(d);
    else G.PARAM.forEach((p) => grafik[p].setData(dataGrafik(p, d)));
    G.PARAM.forEach((p) => G.kosongkan(widget[p].stat).append(...statistik(p, d)));
    isiKosong(d);
    const jeda = { "1j": 15000, "6j": 60000, "24j": 60000 }[rentang];
    if (jeda) timerTren = setTimeout(muatTren, jeda);
  }
  function pilihRentang(r) {
    document.querySelectorAll("#segRentang button").forEach((x) => x.classList.toggle("aktif", x.dataset.r === r));
    document.getElementById("formCustom").hidden = true;
    rentang = r;
    muatTren();
  }
  window.addEventListener("gpi-tema", () => muatTren(true));

  document.getElementById("segRentang").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    document.querySelectorAll("#segRentang button").forEach((x) => x.classList.toggle("aktif", x === b));
    const fc = document.getElementById("formCustom");
    if (b.dataset.r === "custom") {
      fc.hidden = false;
      if (!document.getElementById("cDari").value && info) {
        const s = info.sekarang.slice(0, 16);
        const kemarin = new Date(G.keDetik(info.sekarang) * 1000 - 86400000).toISOString().slice(0, 16);
        document.getElementById("cDari").value = kemarin;
        document.getElementById("cSampai").value = s;
      }
      return;
    }
    fc.hidden = true;
    rentang = b.dataset.r;
    muatTren();
  });
  document.getElementById("btnCustom").addEventListener("click", () => {
    const a = document.getElementById("cDari").value, b = document.getElementById("cSampai").value;
    if (!a || !b) return G.toast("Isi waktu mulai dan akhir", true);
    rentang = "custom";
    custom = [a, b];
    muatTren();
  });
  const unduh = (fmt) => { location.href = urlRentang("/api/unit/" + MID + "/ekspor?format=" + fmt); };
  document.getElementById("btnXlsx").addEventListener("click", () => unduh("xlsx"));
  document.getElementById("btnCsv").addEventListener("click", () => unduh("csv"));

  const STATUS_TL = ["Normal", "Start-up", "Peringatan", "Kritis", "Terlambat", "Offline"];
  async function muatTimeline() {
    const d = await G.api("/api/unit/" + MID + "/timeline?jam=24");
    const tl = G.kosongkan(document.getElementById("timeline")), rentangDetik = d.sampai - d.dari;
    d.segmen.forEach((s) => {
      tl.appendChild(h("div", { class: "t-" + G.slug(s.status), style: { left: ((s.mulai - d.dari) / rentangDetik) * 100 + "%", width: Math.max(((s.selesai - s.mulai) / rentangDetik) * 100, 0.15) + "%" },
        title: s.status + " · " + G.dariEp(s.mulai) + " – " + G.dariEp(s.selesai) + " (" + G.durasi(s.selesai - s.mulai) + ")" }));
    });
    if (!d.segmen.length) tl.appendChild(h("div", { style: { left: 0, right: 0, textAlign: "center", fontSize: "11.5px", lineHeight: "26px", color: "var(--text-tert)" }, text: "belum ada riwayat status" }));
    const skala = G.kosongkan(document.getElementById("skalaJam"));
    let t = Math.ceil(d.dari / 3600) * 3600;
    for (; t <= d.sampai; t += 3600) {
      const jam = new Date(t * 1000).getUTCHours();
      if (jam % 3) continue;
      skala.appendChild(h("span", { style: { left: ((t - d.dari) / rentangDetik) * 100 + "%" }, text: String(jam).padStart(2, "0") + ":00" }));
    }
    const leg = G.kosongkan(document.getElementById("legenda"));
    STATUS_TL.forEach((s) => leg.appendChild(h("span", null, h("i", { class: "t-" + G.slug(s) + " i-" + G.slug(s) }), s === "Terlambat" ? "Data terlambat" : s)));
  }

  async function muatAlarm() {
    const d = await G.api("/api/alarm?mesin_id=" + MID + "&batas=30");
    G.kosongkan(document.getElementById("tabelAlarm")).appendChild(G.tabelAlarm(d.alarm, d.sekarang, { tanpaUnit: true, muatUlang: () => { muatAlarm(); muatInfo(); }, kosong: "Belum ada alarm untuk unit ini." }));
    document.getElementById("linkAlarm").href = "/alarm?mesin_id=" + MID;
  }

  document.getElementById("btnMaint").addEventListener("click", () => {
    if (!info) return;
    const nyala = info.unit.status_mesin !== "Maintenance";
    const ta = h("textarea", { rows: 2, maxlength: 200, placeholder: "Contoh: penggantian sieve bed, teknisi Budi" });
    G.modal(nyala ? "Aktifkan mode Maintenance" : "Akhiri mode Maintenance",
      h("div", null, h("p", { class: "muted", style: { marginTop: 0 }, text: nyala ?
        "Selama Maintenance, alarm tetap dicatat dan tampil di dashboard, tetapi notifikasi tidak dikirim (AL-10). Jangan lupa mengakhirinya setelah pekerjaan selesai." :
        "Notifikasi untuk unit ini akan berjalan normal lagi." }), h("label", { class: "f", text: "Catatan" }), ta),
      [{ teks: "Batal" }, { teks: nyala ? "Aktifkan" : "Akhiri", kelas: "btn-primary", aksi: async () => {
        await G.api("/api/unit/" + MID + "/maintenance", { json: { aktif: nyala, catatan: ta.value } });
        G.toast(nyala ? "Mode Maintenance aktif" : "Mode Maintenance berakhir");
        muatInfo();
      } }]);
  });

  G.ulang(async () => {
    try { await muatInfo(); } catch (e) { G.tandaiUpdate(false); if (/tidak ditemukan/i.test(e.message)) location.href = "/"; }
  }, 5000);
  muatTren();
  G.ulang(muatTimeline, 60000);
  G.ulang(muatAlarm, 15000);
  G.pantauSistem();
})();
