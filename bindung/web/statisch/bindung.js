// Bindung: das bisschen Skript, das HTMX nicht kann.
// Auf dem Telefon ist immer genau eine Spalte offen (stil.css, data-ansicht).
(function () {
  "use strict";

  function zeigen(spalte) {
    var app = document.getElementById("app");
    if (app) { app.dataset.ansicht = spalte; }
    window.scrollTo(0, 0);
  }

  // Der Zurueck-Pfeil im Kopf einer Spalte.
  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-zeige]");
    if (knopf) { zeigen(knopf.dataset.zeige); }
  });

  // Das Blatt „Kontakt eintragen“ liegt ueber der Seite: Abbrechen, Escape und ein Klick
  // daneben schliessen es, ohne den Server zu fragen (nichts wurde gespeichert).
  function blattSchliessen() {
    var blatt = document.querySelector("[data-blatt]");
    if (blatt) { blatt.remove(); }
  }
  document.addEventListener("click", function (ereignis) {
    if (ereignis.target.closest("[data-schliessen]") || ereignis.target.matches("[data-blatt]")) {
      blattSchliessen();
    }
  });
  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.key === "Escape") { blattSchliessen(); }
  });

  // Der Server sagt mit HX-Trigger {"spalte": ...}, wohin die Antwort fuehrt.
  document.addEventListener("spalte", function (ereignis) {
    zeigen(ereignis.detail.value);
  });
}());
