(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  const ROTASI_MS = 15000;
  let data = null, halaman = 0, perHalaman = 6, timerRotasi = null;

  const HARI = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
  const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  function jam() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    document.getElementById("jam").textContent = p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
    document.getElementById("tgl").textContent = HARI[d.getDay()] + ", " + d.getDate() + " " + BULAN[d.getMonth()] + " " + d.getFullYear();
  }
  setInterval(jam, 1000);
  jam();

  function hitungKolom(n) {
    const lebar = window.innerWidth;
    const maks = lebar >= 2400 ? 4 : lebar >= 1500 ? 3 : lebar >= 1000 ? 2 : 1;
    const kol = Math.max(1, Math.min(maks, n || 1));
    perHalaman = kol * (window.innerHeight >= 1000 ? 3 : 2);
    return kol;
  }

  function gambar() {
    if (!data) return;
    const unit = data.unit;
    const kol = hitungKolom(unit.length);
    const grid = G.kosongkan(document.getElementById("grid"));
    grid.style.setProperty("--kol", kol);
    G.kosongkan(document.getElementById("hitung")).append(...G.tombolHitung(data.hitung));
    const jmlHal = Math.max(1, Math.ceil(unit.length / perHalaman));
    const adaKritis = (data.hitung.Kritis || 0) > 0;
    if (adaKritis) halaman = 0;
    if (halaman >= jmlHal) halaman = 0;
    unit.slice(halaman * perHalaman, (halaman + 1) * perHalaman).forEach((u) => grid.appendChild(G.kartu(u, data)));
    if (!unit.length) grid.appendChild(h("div", { class: "kosong", text: "Belum ada unit aktif." }));
    document.getElementById("halInfo").textContent = jmlHal > 1 ?
      "Halaman " + (halaman + 1) + " / " + jmlHal + (adaKritis ? " · rotasi berhenti karena ada unit KRITIS" : " · berganti tiap " + ROTASI_MS / 1000 + " detik") :
      unit.length + " unit";
    clearTimeout(timerRotasi);
    if (jmlHal > 1 && !adaKritis) timerRotasi = setTimeout(() => { halaman = (halaman + 1) % jmlHal; gambar(); }, ROTASI_MS);
  }
  window.addEventListener("resize", gambar);

  const ajak = document.getElementById("ajakSuara");
  ajak.hidden = G.Suara.siap();
  document.getElementById("btnAjak").addEventListener("click", () => { G.Suara.aktifkan(); ajak.hidden = true; });
  document.getElementById("btnTanpa").addEventListener("click", () => { ajak.hidden = true; });
  document.getElementById("btnLayar").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => G.toast("Layar penuh ditolak browser; tekan F11", true));
  });

  G.ulang(async () => {
    try {
      data = await G.api("/api/ringkasan");
      G.catatAmbil();
      G.tandaiUpdate(true);
      G.terapkanSistem(data);
      gambar();
    } catch (e) {
      G.tandaiUpdate(false);
    }
  }, 5000);
})();
