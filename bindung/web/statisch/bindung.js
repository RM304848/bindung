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

  // Das Suchfeld der Auswahl „In der App“ sitzt in einem Formular; Enter soll dort nicht
  // speichern, sondern nur die Suche in Ruhe lassen.
  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.key === "Enter" && ereignis.target.matches("[data-ohne-enter]")) {
      ereignis.preventDefault();
    }
  });

  // „Kopieren“ neben einer Adresse (Einstellungen): der Wert des Feldes in die Zwischenablage.
  // `navigator.clipboard` gibt es nur auf sicheren Seiten (https, localhost); sonst bleibt das
  // alte `execCommand`, und im schlimmsten Fall ist der Text markiert und man kopiert selbst.
  function kopiert(knopf) {
    var vorher = knopf.dataset.text || knopf.textContent;
    knopf.dataset.text = vorher;
    knopf.textContent = "Kopiert";
    window.setTimeout(function () { knopf.textContent = vorher; }, 2000);
  }
  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-kopieren]");
    if (!knopf) { return; }
    var feld = document.getElementById(knopf.dataset.kopieren);
    if (!feld) { return; }
    feld.focus();
    feld.select();
    function ersatz() {
      try { if (document.execCommand("copy")) { kopiert(knopf); } } catch (fehler) { /* markiert bleibt es */ }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(feld.value).then(function () { kopiert(knopf); }, ersatz);
    } else {
      ersatz();
    }
  });

  // Der Server sagt mit HX-Trigger {"spalte": ...}, wohin die Antwort fuehrt.
  document.addEventListener("spalte", function (ereignis) {
    zeigen(ereignis.detail.value);
  });
}());
