(function () {
  "use strict";
  const G = window.GPI;
  document.getElementById("btnPw").addEventListener("click", async () => {
    const lama = document.getElementById("pwLama").value, baru = document.getElementById("pwBaru").value;
    const galat = document.getElementById("pwGalat");
    galat.textContent = "";
    if (baru !== document.getElementById("pwUlang").value) { galat.textContent = "Password baru tidak sama"; return; }
    try {
      await G.api("/api/akun/password", { json: { lama, baru } });
      G.toast("Password diganti");
      ["pwLama", "pwBaru", "pwUlang"].forEach((id) => { document.getElementById(id).value = ""; });
    } catch (e) { galat.textContent = e.message; }
  });
  G.tandaiUpdate(true);
  G.pantauSistem();
})();
