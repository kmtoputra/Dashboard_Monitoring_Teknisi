(function () {
  "use strict";
  var KUNCI = "gpi_tema";
  function baca() {
    try { return localStorage.getItem(KUNCI) === "dark" ? "dark" : "light"; } catch (e) { return "light"; }
  }
  function terapkan(t, kirim) {
    document.documentElement.setAttribute("data-theme", t);
    if (kirim) window.dispatchEvent(new CustomEvent("gpi-tema", { detail: t }));
  }
  terapkan(baca(), false);
  window.GPITema = {
    sekarang: function () { return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; },
    ganti: function () {
      var baru = this.sekarang() === "dark" ? "light" : "dark";
      try { localStorage.setItem(KUNCI, baru); } catch (e) { }
      terapkan(baru, true);
      return baru;
    },
  };
  window.addEventListener("storage", function (e) {
    if (e.key === KUNCI) terapkan(baca(), true);
  });
})();
