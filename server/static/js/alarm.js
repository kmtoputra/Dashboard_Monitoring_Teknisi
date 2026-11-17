(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  const BATAS = 100;
  let riwayat = [], offset = 0, sekarang = null;

  async function muatAktif() {
    const d = await G.api("/api/alarm?status=aktif&batas=300");
    G.tandaiUpdate(true);
    document.getElementById("jmlAktif").textContent = d.alarm.length ? d.alarm.length + " event" : "";
    G.kosongkan(document.getElementById("tabelAktif")).appendChild(
      G.tabelAlarm(d.alarm, d.sekarang, { muatUlang: () => { muatAktif(); muatRiwayat(true); }, kosong: "Tidak ada alarm aktif. Semua unit normal atau belum ada data." }));
  }

  function query() {
    const q = new URLSearchParams({ status: "semua", batas: BATAS, mulai_dari: offset });
    const u = document.getElementById("fUnit").value, l = document.getElementById("fLevel").value;
    const a = document.getElementById("fDari").value, b = document.getElementById("fSampai").value;
    if (u) q.set("mesin_id", u);
    if (l) q.set("level", l);
    if (a) q.set("dari", a);
    if (b) q.set("sampai", b);
    return q.toString();
  }

  async function muatRiwayat(ulang) {
    if (ulang) { offset = 0; riwayat = []; }
    const d = await G.api("/api/alarm?" + query());
    sekarang = d.sekarang;
    riwayat = riwayat.concat(d.alarm);
    offset += d.alarm.length;
    G.kosongkan(document.getElementById("tabelRiwayat")).appendChild(
      G.tabelAlarm(riwayat, sekarang, { muatUlang: () => { muatAktif(); muatRiwayat(true); }, kosong: "Tidak ada alarm pada filter ini." }));
    document.getElementById("btnLagi").hidden = d.alarm.length < BATAS;
  }

  async function isiUnit() {
    const d = await G.api("/api/ringkasan");
    G.terapkanSistem(d);
    const sel = document.getElementById("fUnit");
    d.unit.concat(d.nonaktif).forEach((u) => sel.appendChild(h("option", { value: u.id, text: (u.nama_rs || u.kode_lokasi) + " · " + u.kode_unit })));
    const pilih = new URLSearchParams(location.search).get("mesin_id");
    if (pilih) sel.value = pilih;
  }

  document.getElementById("btnFilter").addEventListener("click", () => muatRiwayat(true).catch((e) => G.toast(e.message, true)));
  document.getElementById("btnLagi").addEventListener("click", () => muatRiwayat(false).catch((e) => G.toast(e.message, true)));
  isiUnit().then(() => muatRiwayat(true)).catch((e) => G.toast(e.message, true));
  G.ulang(async () => { try { await muatAktif(); } catch (e) { G.tandaiUpdate(false); } }, 15000);
  G.pantauSistem();
})();
