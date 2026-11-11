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

  // Der Server sagt mit HX-Trigger {"spalte": ...}, wohin die Antwort fuehrt.
  document.addEventListener("spalte", function (ereignis) {
    zeigen(ereignis.detail.value);
  });
}());
