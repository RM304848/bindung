# Bindung

Eine kleine Web-App, um den Kontakt zu den Menschen zu halten, die einem
wichtig sind: Sie merkt sich, **worüber ihr zuletzt gesprochen habt**, und
erinnert dich, **bevor eine Bindung erkaltet**. Drei Spalten wie in Erinnerungen
am Mac: Seitenleiste mit Tags, Liste mit drei Karten, Seite zur Person.

Deine Daten bleiben auf deinem eigenen Rechner oder Server. Es gibt keine
KI zur Laufzeit; Fälligkeiten und Meldungen kommen aus festen Regeln.

Stand: Das Gerüst steht (Anmeldung, leere Startseite). Der Plan steht in
[`PLAN.md`](PLAN.md), die Begriffe in [`CONTEXT.md`](CONTEXT.md).

## Starten

Python 3.12 vorausgesetzt.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Einen Nutzer anlegen (das Passwort wird zweimal abgefragt):

```bash
.venv/bin/bindung nutzer anlegen anna
```

Den Server starten und im Browser öffnen:

```bash
.venv/bin/bindung serve
```

Dann http://127.0.0.1:8785 aufrufen und anmelden.

Weitere Befehle: `bindung nutzer passwort <name>`, `bindung nutzer liste`,
`bindung ort` (zeigt den Datenordner und warum es dieser ist).

## Einstellungen aus der Umgebung

| Variable | Wirkung | Vorgabe |
|---|---|---|
| `BINDUNG_DATEN` | Datenordner | `~/Library/Application Support/Bindung` (Mac) |
| `BINDUNG_HOST` | Adresse, an die der Server bindet | `127.0.0.1` |
| `BINDUNG_PORT` | Port | `8785` |
| `BINDUNG_SICHER` | `1`, wenn ein TLS-Proxy davorsteht (Cookie wird `Secure`) | aus |

## Prüfen

```bash
.venv/bin/python -m pytest
```

Die Tests laufen in einem Wegwerf-Datenordner und prüfen auch, dass `ruff`
keine Funde meldet.

## Lizenz und Fremdteile

Siehe [`LICENSE.md`](LICENSE.md). `bindung/web/statisch/htmx.min.js` ist
[htmx](https://htmx.org) 2.0.4 (Zero-Clause-BSD-Lizenz), mitgeliefert, damit die App
ohne Netz läuft.
