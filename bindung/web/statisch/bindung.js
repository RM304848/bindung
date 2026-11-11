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

  // ------------------------------------------------------------------- Push
  // Die Tagesmeldung als Mitteilung des Browsers (PLAN.md, Abschnitt 10). Die Erlaubnis
  // fragt nur ein Klick auf einen Knopf mit `data-push-aktivieren`, nie das Laden einer Seite.
  // Der Service Worker (`/sw.js`) zeigt die Mitteilung; hier wird nur angemeldet und abgemeldet.
  var pushMoeglich = "serviceWorker" in navigator && "PushManager" in window &&
    "Notification" in window;

  function schluesselDekodieren(text) {
    var roh = atob((text + "=".repeat((4 - text.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    var aus = new Uint8Array(roh.length);
    for (var i = 0; i < roh.length; i += 1) { aus[i] = roh.charCodeAt(i); }
    return aus;
  }

  function jsonSenden(adresse, methode, koerper) {
    return fetch(adresse, {
      method: methode, credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(koerper)
    });
  }

  function worker() {
    return navigator.serviceWorker.register("/sw.js").then(function () {
      return navigator.serviceWorker.ready;
    });
  }

  // Eins von: nicht_unterstuetzt, verweigert, offen, ohne_abo, aktiv.
  function pushZustand() {
    if (!pushMoeglich) { return Promise.resolve("nicht_unterstuetzt"); }
    if (Notification.permission === "denied") { return Promise.resolve("verweigert"); }
    if (Notification.permission === "default") { return Promise.resolve("offen"); }
    return navigator.serviceWorker.getRegistration("/").then(function (anmeldung) {
      return anmeldung ? anmeldung.pushManager.getSubscription() : null;
    }).then(function (abo) { return abo ? "aktiv" : "ohne_abo"; }, function () { return "ohne_abo"; });
  }

  function abonnieren(anmeldung, schluessel) {
    var optionen = { userVisibleOnly: true, applicationServerKey: schluesselDekodieren(schluessel) };
    return anmeldung.pushManager.subscribe(optionen).catch(function (fehler) {
      // Ein altes Abo mit anderem Server-Schluessel verhindert das neue: erst weg damit.
      return anmeldung.pushManager.getSubscription().then(function (alt) {
        if (!alt) { throw fehler; }
        return alt.unsubscribe().then(function () { return anmeldung.pushManager.subscribe(optionen); });
      });
    });
  }

  function pushAktivieren() {
    if (!pushMoeglich) { return Promise.reject(new Error("Dieser Browser kann keine Mitteilungen.")); }
    return Notification.requestPermission().then(function (erlaubnis) {
      if (erlaubnis !== "granted") { throw new Error("Mitteilungen sind nicht erlaubt."); }
      return worker();
    }).then(function (anmeldung) {
      return fetch("/push/schluessel", { credentials: "same-origin" })
        .then(function (antwort) { return antwort.json(); })
        .then(function (daten) { return abonnieren(anmeldung, daten.schluessel); });
    }).then(function (abo) {
      return jsonSenden("/push/abo", "POST", abo.toJSON()).then(function (antwort) {
        if (!antwort.ok) {
          return abo.unsubscribe().then(function () { throw new Error("Der Server hat die Anmeldung abgelehnt."); });
        }
        return abo;
      });
    });
  }

  function pushDeaktivieren() {
    return navigator.serviceWorker.getRegistration("/").then(function (anmeldung) {
      return anmeldung ? anmeldung.pushManager.getSubscription() : null;
    }).then(function (abo) {
      if (!abo) { return null; }
      return jsonSenden("/push/abo", "DELETE", { endpoint: abo.endpoint }).then(function () {
        return abo.unsubscribe();
      });
    });
  }

  // Der Server kennt das Abo auch dann, wenn die Datenbank zwischendurch ersetzt wurde oder ein
  // anderer Nutzer sich im selben Browser angemeldet hat: einmal am Tag wird es erneut gemeldet.
  function pushAbgleichen() {
    var heute = new Date().toISOString().slice(0, 10);
    try { if (window.localStorage.getItem("bindungPushAbgleich") === heute) { return; } } catch (fehler) { /* egal */ }
    navigator.serviceWorker.getRegistration("/").then(function (anmeldung) {
      return anmeldung ? anmeldung.pushManager.getSubscription() : null;
    }).then(function (abo) {
      if (!abo) { return null; }
      return jsonSenden("/push/abo", "POST", abo.toJSON()).then(function (antwort) {
        if (antwort.ok) {
          try { window.localStorage.setItem("bindungPushAbgleich", heute); } catch (fehler) { /* egal */ }
        }
      });
    }).catch(function () { /* naechstes Mal */ });
  }

  var PUSH_TEXTE = {
    nicht_unterstuetzt: "nicht unterstützt",
    verweigert: "nicht erlaubt (in den Einstellungen des Browsers änderbar)",
    offen: "noch nicht erlaubt",
    ohne_abo: "erlaubt, aber nicht angemeldet",
    aktiv: "erlaubt und angemeldet"
  };

  function zeigeWenn(knoepfe, an) {
    Array.prototype.forEach.call(knoepfe, function (knopf) { knopf.hidden = !an; });
  }

  // Zeichnet, was dieser Browser kann: Status in den Einstellungen, Knoepfe, der Hinweis.
  function pushAnzeigen(zustand, meldung) {
    var status = document.querySelector("[data-push-status]");
    if (status) { status.textContent = meldung || PUSH_TEXTE[zustand]; }
    var einstellung = document.getElementById("einstellung-benachrichtigungen");
    if (einstellung) {
      zeigeWenn(einstellung.querySelectorAll("[data-push-aktivieren]"),
        zustand === "offen" || zustand === "ohne_abo");
      zeigeWenn(einstellung.querySelectorAll("[data-push-deaktivieren]"), zustand === "aktiv");
    }
    var hinweis = document.getElementById("hinweis");
    if (hinweis) {
      if (zustand === "aktiv") {
        hinweis.remove();   // dieser Browser bekommt die Tagesmeldung als Push
      } else {
        hinweis.hidden = false;
        zeigeWenn(hinweis.querySelectorAll("[data-push-aktivieren]"), zustand === "offen" || zustand === "ohne_abo");
        zeigeWenn(hinweis.querySelectorAll("[data-hinweis-dock]"), zustand === "nicht_unterstuetzt");
      }
    }
    if (zustand === "aktiv") { pushAbgleichen(); }
  }

  function pushPruefen() {
    if (!document.querySelector("[data-push-status], [data-hinweis]")) { return; }
    pushZustand().then(function (zustand) { pushAnzeigen(zustand); });
  }

  function pushAbschnittNeu() {
    if (window.htmx && document.getElementById("einstellung-benachrichtigungen")) {
      window.htmx.ajax("GET", "/einstellungen/benachrichtigungen",
        { target: "#einstellung-benachrichtigungen", swap: "outerHTML" });
    }
  }

  document.addEventListener("click", function (ereignis) {
    var an = ereignis.target.closest("[data-push-aktivieren]");
    var aus = ereignis.target.closest("[data-push-deaktivieren]");
    if (!an && !aus) { return; }
    (an ? pushAktivieren() : pushDeaktivieren()).then(function () {
      pushAbschnittNeu();
      pushPruefen();
    }, function (fehler) {
      pushZustand().then(function (zustand) { pushAnzeigen(zustand, PUSH_TEXTE[zustand] + ". " + fehler.message); });
    });
  });

  document.addEventListener("DOMContentLoaded", pushPruefen);
  // HTMX tauscht den Abschnitt der Einstellungen aus: der Status muss neu hinein.
  document.addEventListener("htmx:afterSettle", pushPruefen);
}());
