# Änderungen

Hier steht, was sich für die Menschen ändert, die Bindung benutzen. Jeder
Release bekommt einen eigenen Abschnitt, geschrieben vor dem Taggen.

## Unveröffentlicht

### Neu

- **Personen anlegen und bearbeiten.** Mit „Person hinzufügen“ legst du eine
  Person an: Name, Firma, Rolle, Telefon, E-Mail, Ort, Herkunft und
  Profilnotiz. Auf der Personenseite bearbeitest du alles direkt am Feld; beim
  Verlassen des Feldes wird gespeichert („Gespeichert“ erscheint oben).
  Telefon und E-Mail sind Links zum Anrufen und Schreiben. Dazu kommen
  „Intervall in Tagen“ (leer: deine Vorgabe von 56 Tagen) und „Nächster
  Termin“.
- **Tags.** Mit „Tag hinzufügen“ in der Seitenleiste legst du Tags an; jeder
  hat seine eigene Liste mit Zähler. Auf der Personenseite wählst du die Tags
  einer Person als Chips an oder ab oder legst dort gleich einen neuen an. In
  der Liste eines Tags kannst du ihn mit „Tag bearbeiten“ umbenennen oder
  löschen – die Personen bleiben dabei erhalten.
- **Suche.** Das Suchfeld über der Liste filtert beim Tippen nach Name, Firma,
  Ort und Tag, ohne auf Groß- und Kleinschreibung zu achten.
- **Mehrere hinzufügen.** Ein Name pro Zeile (oder „Name; Firma“), dazu Tags
  für alle und eine grobe Angabe, wann ihr zuletzt gesprochen habt: „Diesen
  Monat“, „Vor ein paar Monaten“, „Über ein Jahr her“ oder „Unbekannt“. So
  kommen die ersten Leute in einer Sitzung in die App; doppelte Namen und leere
  Zeilen werden übersprungen.
- **Noch kein Kontakt und Archiv.** „Noch kein Kontakt“ zeigt, wen du noch gar
  nicht eingetragen hast. „Archivieren“ nimmt eine Person aus allen Listen,
  im „Archiv“ holst du sie mit „Wiederherstellen“ zurück.
- **Telefon.** Auf dem Telefon ist immer eine Spalte offen: Seitenleiste, Liste
  oder Person, mit „‹ Zurück“ zur vorigen. Die Adresse im Browser merkt sich
  Filter, Suche und die offene Person; Neuladen und die Zurück-Taste führen
  an dieselbe Stelle.

- **Anmeldung.** Bindung ist eine Web-App mit eigener Anmeldung: jeder Nutzer
  sieht nur seine eigenen Einträge. Angelegt werden Nutzer auf dem Server mit
  `bindung nutzer anlegen <name>` (das Passwort wird zweimal abgefragt und
  bleibt dabei unsichtbar); `bindung nutzer passwort <name>` setzt ein neues,
  `bindung nutzer liste` zeigt alle.
- **Angemeldet bleiben.** Die Sitzung hält 30 Tage und verlängert sich bei
  jeder Benutzung. Nach falschen Anmeldeversuchen muss man mit jedem Versuch
  länger warten. Abmelden geht unten in der Seitenleiste.
- **Drei Spalten wie in Erinnerungen.** Nach der Anmeldung öffnet sich die
  Startseite: links die Seitenleiste (Alle, Noch kein Kontakt, Archiv, Tags),
  in der Mitte die Liste mit den drei Karten „Braucht Aufmerksamkeit“,
  „Erkaltet“ und „Diese Woche“ sowie der Suche, rechts die Personenseite. Auf
  dem Telefon stehen die drei Bereiche untereinander, die Seitenleiste zuerst.
  Hell und Dunkel folgen der Einstellung des Geräts. Die Karten zeigen noch 0:
  Kontakte und Fälligkeit kommen in der nächsten Version.
- **Datenordner.** Alles, was du einträgst, liegt in einem einzigen Ordner
  (auf dem Mac `~/Library/Application Support/Bindung`). `bindung ort` zeigt,
  wo er ist; mit der Umgebungsvariable `BINDUNG_DATEN` lässt er sich umstellen.
  Die Datenbank wird beim ersten Start angelegt.
- **Start.** `bindung serve` startet die App auf http://127.0.0.1:8785. Mit
  `BINDUNG_HOST` und `BINDUNG_PORT` (oder `--host` und `--port`) lässt sich
  Adresse und Port ändern; steht ein Server mit TLS davor, sorgt
  `BINDUNG_SICHER=1` dafür, dass das Anmelde-Cookie nur verschlüsselt geschickt wird.
