# Änderungen

Hier steht, was sich für die Menschen ändert, die Bindung benutzen. Jeder
Release bekommt einen eigenen Abschnitt, geschrieben vor dem Taggen.

## Unveröffentlicht

### Neu

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
  Hell und Dunkel folgen der Einstellung des Geräts. Noch ist alles leer: Personen,
  Tags und Kontakte kommen in den nächsten Versionen.
- **Datenordner.** Alles, was du einträgst, liegt in einem einzigen Ordner
  (auf dem Mac `~/Library/Application Support/Bindung`). `bindung ort` zeigt,
  wo er ist; mit der Umgebungsvariable `BINDUNG_DATEN` lässt er sich umstellen.
  Die Datenbank wird beim ersten Start angelegt.
- **Start.** `bindung serve` startet die App auf http://127.0.0.1:8785. Mit
  `BINDUNG_HOST` und `BINDUNG_PORT` (oder `--host` und `--port`) lässt sich
  Adresse und Port ändern; steht ein Server mit TLS davor, sorgt
  `BINDUNG_SICHER=1` dafür, dass das Anmelde-Cookie nur verschlüsselt geschickt wird.
