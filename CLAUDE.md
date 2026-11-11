# bindung

Web-App, um den Kontakt zu den Menschen zu halten, die einem wichtig sind:
Python 3.12, SQLite, Typer-CLI `bindung`, FastAPI + Jinja2 (serverseitig
gerendert, HTMX fuer Teilaktualisierungen), ein handgeschriebenes
Stylesheet. Drei Spalten wie Apple Erinnerungen: Seitenleiste, Liste mit drei
Karten, Personenseite. Mehrere Nutzer mit eigener Anmeldung.
Start: `.venv/bin/bindung serve`, dann http://127.0.0.1:8785.

**`PLAN.md` ist die Vorgabe, `CONTEXT.md` das Vokabular.** Aendert sich eine
Entscheidung, wird der Plan im selben Schritt angepasst (Abschnitt 13). Der
Code benutzt die Woerter aus `CONTEXT.md` und keine anderen fuer dieselbe
Sache (Person, Kontakt, Zustand, Stichtag ...).

## Feste Rahmen

- Die Daten bleiben auf dem eigenen Server. Nichts geht irgendwohin, ausser
  der Web-Push-Nachricht an den Push-Dienst des Browsers (nur der Text der
  Tagesmeldung).
- Keine KI zur Laufzeit. Faelligkeit, Tagesmeldung und Kalender kommen aus
  festen Regeln. KI schreibt nur Code.
- Keine echten Menschen im Repository: keine echten Namen, Firmen,
  Telefonnummern oder Notizen in Code, Tests, Vorlagen oder Bildschirmfotos.
  Testdaten sind erfunden. Das Repository ist oeffentlich.
- Module bauen Pfade nicht selbst, sondern lesen sie aus `bindung/pfade.py`
  (`pfade.DB_PATH`, `pfade.VAPID_PATH`, `pfade.SICHERUNG_DIR`) -- als Attribut
  des Moduls, nicht per `from ... import`, damit ein Test sie umbiegen kann.
  Die Wurzel ist der Datenordner (`bindung ort`), `BINDUNG_DATEN` stellt ihn
  um. `tests/test_pfade.py` haelt die Zahl der eigenen Pfade auf null.
- Containertauglich von Anfang an: `BINDUNG_HOST` (Vorgabe `127.0.0.1`),
  `BINDUNG_PORT` (Vorgabe `8785`), `BINDUNG_SICHER=1` macht das Cookie
  `Secure`. Nichts im Code darf einen Mac voraussetzen.
- Jede Tabelle mit Nutzerdaten traegt `nutzer_id`, jede Abfrage filtert danach.
  Es gibt keine Sicht ueber Nutzer hinweg.
- Zeiten stehen als UTC-Text in der Datenbank, Tage als ISO-Tag in der
  Zeitzone des Nutzers (Vorgabe Europe/Berlin).
- Eine Schemaaenderung ist ein neuer Eintrag in `db.MIGRATIONEN`, nicht eine
  Aenderung an `schema.sql` allein.
- Code, Kommentare, Vorlagen, CLI-Text und Commit-Nachrichten sind deutsch;
  im Code ASCII-Umlaute (ae/oe/ue), in Vorlagen und Oberflaechentexten echte.
- Jeder Release (Tag) bekommt vor dem Taggen einen Abschnitt in `CHANGELOG.md`,
  geschrieben fuer die Nutzer.

## Wo was liegt

| Ort | Inhalt |
|---|---|
| `bindung/pfade.py` | die eine Wurzel und alle Pfade daraus |
| `bindung/db.py`, `schema.sql` | Verbindung (`verbinden()` ist der einzige Weg), Schema, Migrationen |
| `bindung/auth.py` | Nutzer, scrypt-Passwoerter, Sitzungen, Fehlversuche, Cookie-Optionen |
| `bindung/personen.py` | Personen und Tags als Funktionen auf der Verbindung (Suche, Archiv, "Mehrere hinzufuegen") |
| `bindung/cli.py` | Typer: `serve`, `ort`, `nutzer anlegen/passwort/liste` |
| `bindung/web/server.py` | App, Tuer (Sitzungspruefung), Anmeldung und Abmeldung |
| `bindung/web/basis.py` | Vorlagen, Verbindung und Nutzer der Anfrage, offene Pfade |
| `bindung/web/routen/` | je Seitengruppe ein Router (`personen.py`: Seite, Liste, Personenseite, Tags) |
| `bindung/web/vorlagen/` | Jinja-Vorlagen: `basis`, `anmeldung`, `start` (Huelle); Teile mit `_` (`_seitenleiste`, `_liste`, `_listenkoerper`, `_zeile`, `_pane`, `_personenseite`, `_person_form`, `_mehrere`, `_personentags`, `_kontaktlinks` ...) |
| `bindung/web/statisch/` | `stil.css` (Palette als Variablen, hell und dunkel), `htmx.min.js`, `bindung.js` (Spalte auf dem Telefon) |
| `docs/design_conventions.yaml` | Regeln fuer die Oberflaeche, mit Grund; `tests/test_design.py` prueft sie |

## Tests

`.venv/bin/python -m pytest` -- alle gruen, vor jedem Commit. Jeder Test laeuft
in einem Wegwerf-Datenordner (`tests/conftest.py`); nichts davon beruehrt die
echten Daten.

`ruff` laeuft mit (`tests/test_lint.py`): null Funde, nicht "wenige". Was
geduldet wird, gehoert mit Begruendung in `[tool.ruff.lint]` in
`pyproject.toml`. Browser-Tests mit Playwright (spaeter) laufen allein, nicht
im Gesamtlauf.

Vor einer Aenderung an Vorlagen oder Stylesheet in
`docs/design_conventions.yaml` nachschlagen; eine neue Konvention kommt dort
hinein.
