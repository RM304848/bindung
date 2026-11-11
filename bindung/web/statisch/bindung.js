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
    if (blatt) {
      if (window.Diktat) { window.Diktat.stoppen(); }   // kein Diktat in ein Feld, das weg ist
      blatt.remove();
    }
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

  // ------------------------------------------------------------------ Diktat
  // Der Mikrofonknopf in jedem Textfeld, das in der Vorlage in `<div class="diktat">` steht und
  // `data-diktat` traegt (PLAN.md, Abschnitt 8). Das Diktieren selbst macht `diktat.js`; hier
  // sind nur Knopf und Anzeige. Die Sprache steht am `<body>` (`data-diktat-sprache`, aus den
  // Einstellungen). Auch Felder, die HTMX spaeter einsetzt, bekommen den Knopf.
  var diktatFelder = new WeakMap();   // Textfeld -> { knopf, zwischen, fehler }

  function mikrofonZeichnen() {
    var ns = "http://www.w3.org/2000/svg";
    var bild = document.createElementNS(ns, "svg");
    bild.setAttribute("viewBox", "0 0 24 24");
    bild.setAttribute("width", "22");
    bild.setAttribute("height", "22");
    bild.setAttribute("aria-hidden", "true");
    bild.setAttribute("focusable", "false");
    [["rect", { x: "9", y: "3", width: "6", height: "12", rx: "3" }],
     ["path", { d: "M5 11a7 7 0 0 0 14 0M12 18v3" }]].forEach(function (teil) {
      var form = document.createElementNS(ns, teil[0]);
      Object.keys(teil[1]).forEach(function (name) { form.setAttribute(name, teil[1][name]); });
      bild.appendChild(form);
    });
    return bild;
  }

  function diktatKnopfAnbringen(rahmen) {
    var feld = rahmen.querySelector("textarea[data-diktat]");
    if (!feld || diktatFelder.has(feld)) { return; }
    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "diktat-knopf";
    knopf.setAttribute("aria-pressed", "false");
    knopf.setAttribute("aria-label", "Diktieren");
    knopf.title = "Diktieren";
    var punkt = document.createElement("span");
    punkt.className = "diktat-punkt";
    punkt.setAttribute("aria-hidden", "true");
    knopf.appendChild(mikrofonZeichnen());
    knopf.appendChild(punkt);
    rahmen.appendChild(knopf);
    rahmen.classList.add("diktat-mit-knopf");
    // Unter dem Feld: links vom Knopf, was der Browser gerade erkennt (grau), und darunter,
    // wenn es nicht klappt, warum.
    var zwischen = document.createElement("p");
    zwischen.className = "diktat-zwischen";
    zwischen.hidden = true;
    var fehler = document.createElement("p");
    fehler.className = "diktat-fehler";
    fehler.setAttribute("role", "alert");
    fehler.hidden = true;
    rahmen.appendChild(zwischen);
    rahmen.insertAdjacentElement("afterend", fehler);
    diktatFelder.set(feld, { knopf: knopf, zwischen: zwischen, fehler: fehler });
  }

  function diktatAnbringen() {
    if (!window.Diktat || !window.Diktat.verfuegbar()) { return; }   // ohne Erkennung kein Knopf
    Array.prototype.forEach.call(document.querySelectorAll(".diktat"), diktatKnopfAnbringen);
  }

  function diktatZeigen(feld, laeuft) {
    var teile = diktatFelder.get(feld);
    if (!teile) { return; }
    teile.knopf.setAttribute("aria-pressed", laeuft ? "true" : "false");
    var name = laeuft ? "Diktat beenden" : "Diktieren";
    teile.knopf.setAttribute("aria-label", name);
    teile.knopf.title = name;
  }

  // Der Knopf nimmt dem Feld den Fokus nicht (sonst verliert es Cursor und, auf dem Telefon,
  // die Tastatur geht zu): das Diktat landet dort, wo der Cursor steht.
  document.addEventListener("mousedown", function (ereignis) {
    if (ereignis.target.closest(".diktat-knopf")) { ereignis.preventDefault(); }
  });
  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest(".diktat-knopf");
    if (!knopf) { return; }
    var feld = knopf.parentNode.querySelector("textarea[data-diktat]");
    if (!feld) { return; }
    // Von der Tastatur (detail 0) hat der Knopf den Fokus: zurueck ins Feld, an den alten Cursor.
    if (ereignis.detail === 0) { feld.focus(); }
    window.Diktat.starten(feld, document.body.dataset.diktatSprache || "de-DE");
  });
  document.addEventListener("diktat:start", function (ereignis) {
    var teile = diktatFelder.get(ereignis.target);
    document.querySelectorAll('.diktat-knopf[aria-pressed="true"]').forEach(function (knopf) {
      knopf.setAttribute("aria-pressed", "false");   // immer nur ein Diktat zugleich
    });
    if (teile) { teile.fehler.hidden = true; teile.fehler.textContent = ""; }
    diktatZeigen(ereignis.target, true);
  });
  document.addEventListener("diktat:zwischen", function (ereignis) {
    var teile = diktatFelder.get(ereignis.target);
    if (!teile) { return; }
    teile.zwischen.textContent = ereignis.detail.text;
    teile.zwischen.hidden = !ereignis.detail.text;
  });
  document.addEventListener("diktat:fehler", function (ereignis) {
    var teile = diktatFelder.get(ereignis.target);
    if (!teile) { return; }
    teile.fehler.textContent = ereignis.detail.text;
    teile.fehler.hidden = false;
  });
  document.addEventListener("diktat:ende", function (ereignis) {
    // Beendet ein altes Diktat erst nach dem Start eines neuen, bleibt der neue Knopf an.
    if (window.Diktat.aktiv() !== ereignis.target) { diktatZeigen(ereignis.target, false); }
  });
  // Escape beendet das Diktat und schliesst nicht zugleich das Blatt dahinter.
  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.key === "Escape" && window.Diktat && window.Diktat.aktiv()) {
      window.Diktat.stoppen();
      ereignis.stopPropagation();
    }
  }, true);

  document.addEventListener("DOMContentLoaded", diktatAnbringen);
  document.addEventListener("htmx:afterSettle", diktatAnbringen);

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
