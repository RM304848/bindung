// Bindung: der Service Worker. Er kann nur eines: die Tagesmeldung anzeigen, wenn der
// Server sie per Push schickt, und beim Klick darauf die App oeffnen. Kein Cache, kein
// Offline-Betrieb (PLAN.md, Abschnitt 7): die App braucht ihren Server.
"use strict";

self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (ereignis) { ereignis.waitUntil(self.clients.claim()); });

self.addEventListener("push", function (ereignis) {
  var daten = {};
  try { daten = ereignis.data ? ereignis.data.json() : {}; } catch (fehler) { /* kein JSON */ }
  var optionen = {
    body: daten.text || "",
    data: { url: daten.url || "/" },
    // Gleiche Kennung: eine neue Tagesmeldung ersetzt die alte, statt sich zu stapeln.
    tag: daten.tag || "tagesmeldung",
    renotify: true
  };
  // Das Symbol kommt mit der Installierbarkeit (WP7); bis dahin nur, wenn der Server eines nennt.
  if (daten.icon) { optionen.icon = daten.icon; }
  ereignis.waitUntil(self.registration.showNotification(daten.titel || "Bindung", optionen));
});

self.addEventListener("notificationclick", function (ereignis) {
  ereignis.notification.close();
  var ziel = new URL((ereignis.notification.data && ereignis.notification.data.url) || "/",
                     self.location.origin).href;
  ereignis.waitUntil((async function () {
    var fenster = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (var i = 0; i < fenster.length; i += 1) {
      try {
        await fenster[i].focus();
        if ("navigate" in fenster[i]) { await fenster[i].navigate(ziel); }
        return;
      } catch (fehler) { /* dieses Fenster geht nicht, das naechste oder ein neues */ }
    }
    await self.clients.openWindow(ziel);
  }()));
});
