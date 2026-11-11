// Bindung: Diktat (PLAN.md, Abschnitt 8). Ein kleines Modul mit drei Funktionen:
//   Diktat.verfuegbar()                -> kann dieser Browser diktieren?
//   Diktat.starten(feld, sprache)      -> in dieses Textfeld sprechen ("de-DE" oder "en-US")
//   Diktat.stoppen()                   -> beenden; was schon erkannt ist, kommt noch ins Feld
// Dazu Diktat.aktiv() (das Feld, in das gerade diktiert wird, sonst null).
//
// Rueckmeldungen kommen als Ereignisse am Textfeld (sie steigen im Dokument auf):
//   diktat:start, diktat:zwischen (detail.text, noch nicht im Feld), diktat:fehler
//   (detail.code, detail.text auf Deutsch), diktat:ende.
// Was endgueltig erkannt ist, schreibt das Modul selbst ins Feld, dorthin, wo der Cursor
// steht (sonst ans Ende), und meldet es mit `input`; am Ende der Sitzung kommt `change`,
// damit Formulare, die beim Verlassen des Feldes speichern (Personenseite), speichern.
//
// Der Anbieter dahinter ist das eine Objekt `backend` mit starten/stoppen, gewaehlt beim Laden.
// Heute die Spracherkennung des Browsers; ein Server, der Audio aufnimmt und
// transkribiert, ersetzt sie, ohne dass Vorlagen oder bindung.js etwas merken. Ein Anbieter
// hat diese Gestalt:
//   { verfuegbar() -> bool,
//     starten(sprache, hoerer) -> Sitzung mit stoppen() und abbrechen(),
//     hoerer = { zwischen(text), endgueltig(text), fehler(code), ende() } }
(function () {
  "use strict";

  // ------------------------------------------------------------ Anbieter: Browser

  var Erkennung = window.SpeechRecognition || window.webkitSpeechRecognition;

  var browserErkennung = {
    verfuegbar: function () { return typeof Erkennung === "function"; },
    starten: function (sprache, hoerer) {
      var erkennung = new Erkennung();
      erkennung.lang = sprache;
      erkennung.continuous = true;
      erkennung.interimResults = true;
      erkennung.maxAlternatives = 1;
      erkennung.onresult = function (ereignis) {
        var zwischen = "";
        for (var i = ereignis.resultIndex; i < ereignis.results.length; i += 1) {
          var ergebnis = ereignis.results[i];
          var text = ergebnis[0].transcript;
          if (ergebnis.isFinal) { hoerer.endgueltig(text); } else { zwischen += text; }
        }
        hoerer.zwischen(zwischen);
      };
      erkennung.onerror = function (ereignis) { hoerer.fehler(ereignis.error); };
      erkennung.onend = function () { hoerer.ende(); };
      erkennung.start();
      return {
        stoppen: function () { erkennung.stop(); },        // liefert noch Ergebnisse, dann `end`
        abbrechen: function () { erkennung.abort(); }
      };
    }
  };

  var backend = browserErkennung.verfuegbar() ? browserErkennung : null;

  // ------------------------------------------------------------------ Meldungen

  var FEHLER = {
    "not-allowed": "Das Mikrofon ist nicht erlaubt. Erlaube es in den Einstellungen des Browsers für diese Seite.",
    "service-not-allowed": "Das Mikrofon ist nicht erlaubt. Erlaube es in den Einstellungen des Browsers für diese Seite.",
    "no-speech": "Es war nichts zu hören. Versuch es noch einmal.",
    "network": "Die Spracherkennung des Browsers ist gerade nicht erreichbar. Prüfe die Verbindung.",
    "audio-capture": "Kein Mikrofon gefunden.",
    "language-not-supported": "Diese Sprache kann der Browser nicht erkennen."
  };

  function fehlertext(code) {
    return FEHLER[code] || "Das Diktat hat nicht geklappt (" + code + ").";
  }

  // ----------------------------------------------------------------- Sitzung

  var aktuell = null;   // { feld, sitzung, ort, zwischen }

  function melden(feld, name, detail) {
    feld.dispatchEvent(new CustomEvent("diktat:" + name, { bubbles: true, detail: detail || {} }));
  }

  // Schreibt endgueltig erkannten Text an den Cursor (sonst ans Ende), mit Leerzeichen
  // zum Nachbartext, und merkt sich, wo der naechste Text hin soll.
  function einfuegen(sitzung, text) {
    text = text.trim();
    if (!text) { return; }
    var feld = sitzung.feld;
    var wert = feld.value;
    var von = sitzung.ort;
    var bis = sitzung.ort;
    if (document.activeElement === feld) { von = feld.selectionStart; bis = feld.selectionEnd; }
    if (von === null || von > wert.length) { von = bis = wert.length; }
    if (von > 0 && !/\s/.test(wert.charAt(von - 1))) { text = " " + text; }
    if (bis < wert.length && !/\s/.test(wert.charAt(bis))) { text += " "; }
    feld.setRangeText(text, von, bis, "end");
    sitzung.ort = feld.selectionEnd;
    feld.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function beenden(sitzung) {
    if (sitzung.beendet) { return; }
    sitzung.beendet = true;
    if (aktuell === sitzung) { aktuell = null; }
    melden(sitzung.feld, "zwischen", { text: "" });
    // Einmal am Ende: Formulare, die bei `change` speichern, sehen den neuen Text.
    if (sitzung.eingefuegt) { sitzung.feld.dispatchEvent(new Event("change", { bubbles: true })); }
    melden(sitzung.feld, "ende");
  }

  function starten(feld, sprache) {
    if (!backend || !feld) { return false; }
    if (aktuell) {
      var dasselbe = aktuell.feld === feld;
      stoppen();
      if (dasselbe) { return false; }   // der Knopf schaltet um
    }
    var sitzung = { feld: feld, ort: feld.selectionStart, beendet: false, eingefuegt: false, handle: null };
    if (document.activeElement !== feld) { sitzung.ort = feld.value.length; }
    var hoerer = {
      zwischen: function (text) {
        if (sitzung.beendet) { return; }
        if (!feld.isConnected) { sitzung.handle.abbrechen(); return; }   // Blatt zu, Feld getauscht
        melden(feld, "zwischen", { text: text.trim() });
      },
      endgueltig: function (text) {
        if (sitzung.beendet || !feld.isConnected) { return; }
        sitzung.eingefuegt = sitzung.eingefuegt || Boolean(text.trim());
        einfuegen(sitzung, text);
      },
      fehler: function (code) {
        if (code === "aborted") { return; }   // vom Nutzer oder von uns beendet
        if (!sitzung.beendet) { melden(feld, "fehler", { code: code, text: fehlertext(code) }); }
        if (sitzung.handle) { sitzung.handle.abbrechen(); }
        beenden(sitzung);
      },
      ende: function () { beenden(sitzung); }
    };
    aktuell = sitzung;
    try {
      sitzung.handle = backend.starten(sprache || "de-DE", hoerer);
    } catch (fehler) {
      aktuell = null;
      melden(feld, "fehler", { code: "start", text: fehlertext("start") });
      return false;
    }
    melden(feld, "start");
    return true;
  }

  function stoppen() {
    if (aktuell && aktuell.handle) { aktuell.handle.stoppen(); }
  }

  window.Diktat = {
    verfuegbar: function () { return Boolean(backend); },
    starten: starten,
    stoppen: stoppen,
    aktiv: function () { return aktuell && !aktuell.beendet ? aktuell.feld : null; },
    // Nur fuer Tests und einen spaeteren Anbieter: den Anbieter tauschen.
    _anbieter: function (neu) { backend = neu; }
  };
}());
