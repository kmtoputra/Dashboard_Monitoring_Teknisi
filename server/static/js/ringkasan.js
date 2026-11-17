(function () {
  "use strict";
  const G = window.GPI;
  const h = G.h;
  let data = null, filter = null;

  function gambar() {
    if (!data) return;
    const grid = G.kosongkan(document.getElementById("grid"));
    G.kosongkan(document.getElementById("hitung")).append(...G.tombolHitung(data.hitung, filter, (s) => {
      filter = filter === s ? null : s;
      gambar();
    }));
    const unit = data.unit.filter((u) => !filter || u.status === filter);
    if (!data.unit.length) grid.appendChild(h("div", { class: "kosong", text: "Belum ada unit aktif. Aktifkan unit di halaman Admin." }));
    else if (!unit.length) grid.appendChild(h("div", { class: "kosong", text: "Tidak ada unit berstatus " + filter + "." }));
    unit.forEach((u) => grid.appendChild(G.kartu(u, data)));
    const blok = document.getElementById("blokNonaktif");
    blok.hidden = !data.nonaktif.length;
    document.getElementById("judulNonaktif").textContent = data.nonaktif.length + " unit belum terhubung (status Nonaktif)";
    G.kosongkan(document.getElementById("gridNonaktif")).append(...data.nonaktif.map((u) =>
      h("div", { class: "mini" }, h("b", { text: u.nama_rs || u.kode_lokasi }), [u.kota, u.kode_unit, u.jenis_mesin].filter(Boolean).join(" · "))));
  }

  G.ulang(async () => {
    try {
      data = await G.api("/api/ringkasan");
      G.catatAmbil();
      G.tandaiUpdate(true);
      G.terapkanSistem(data);
      gambar();
      const k = data.hitung.Kritis || 0;
      document.title = (k ? "(" + k + " KRITIS) " : "") + "Ringkasan · GPI";
    } catch (e) {
      G.tandaiUpdate(false);
    }
  }, 5000);
})();
