# Bindung

Eine kleine Web-App, um den Kontakt zu den Menschen zu halten, die einem
wichtig sind: Sie merkt sich, **worüber ihr zuletzt gesprochen habt**, und
erinnert dich, **bevor eine Bindung erkaltet**. Drei Spalten wie in Erinnerungen
am Mac: Seitenleiste mit Tags, Liste mit drei Karten, Seite zur Person.

Deine Daten bleiben auf deinem eigenen Rechner oder Server. Es gibt keine
KI zur Laufzeit; Fälligkeiten und Meldungen kommen aus festen Regeln.

Stand: Version 0.1.0, das erste Release (siehe [`CHANGELOG.md`](CHANGELOG.md)).
Der Plan steht in [`PLAN.md`](PLAN.md), die Begriffe in [`CONTEXT.md`](CONTEXT.md).

## Installation

### Im Terminal

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

Dann http://127.0.0.1:8785 aufrufen und anmelden. Weitere Befehle:
`bindung nutzer passwort <name>`, `bindung nutzer liste`, `bindung ort` (zeigt den
Datenordner und warum es dieser ist) und `bindung app` (startet Bindung wie die
Mac-App, siehe unten).

### Als Mac-App

Aus dem Disk-Image `Bindung-<Version>-mac.dmg` (Seite „Releases“ auf GitHub)
die App „Bindung“ in „Programme“ ziehen und starten. Die App ist nicht
signiert: ein heruntergeladenes Image öffnest du beim ersten Mal mit
Rechtsklick › „Öffnen“. Sie legt ein Symbol aus zwei Ringen in die Menüleiste
(kein Dock-Symbol), öffnet Bindung im Browser unter http://127.0.0.1:8788 und
fragt beim ersten Start nach Name und Passwort. „Beenden“ steht im Menü des
Symbols und unten in der Seitenleiste. Die Tagesmeldung kommt nur, solange die
App läuft; sie in den Anmeldeobjekten des Macs einzutragen (Systemeinstellungen
› Allgemein › Anmeldeobjekte) ist deshalb sinnvoll.

Selbst bauen (braucht die `paket`-Abhängigkeiten, siehe `pyproject.toml`):

```bash
.venv/bin/pip install -e '.[dev,paket]'
werkzeuge/paket/bauen.sh
```

Das erzeugt `dist/Bindung-<Version>-mac.dmg` und startet vorher den Rauchtest der
gebauten App in einem leeren Datenordner.

### Benachrichtigungen und Kalender

* **Mitteilungen (Tagesmeldung):** „Einstellungen › Benachrichtigungen › In diesem
  Browser aktivieren“. **Safari auf dem Mac** kann Mitteilungen erst, wenn Bindung
  im Dock liegt (Safari: Ablage › Zum Dock hinzufügen); auf dem iPhone muss
  Bindung auf dem Startbildschirm liegen (Teilen › Zum Home-Bildschirm) und über
  eine verschlüsselte Adresse (https) erreichbar sein.
* **Kalender abonnieren:** „Einstellungen › Kalender“ zeigt die Adresse. In Apple
  Kalender: Ablage › Neues Kalenderabonnement, Adresse einfügen, Aktualisierung
  stündlich.
* **Telefon:** Bindung lässt sich als App auf den Startbildschirm legen; dazu muss
  das Telefon den Server erreichen (nicht die Mac-App, die nur auf diesem Mac hört).

## Betrieb auf einem Server

Das gibt es heute: `bindung serve` mit Einstellungen aus der Umgebung (Tabelle
unten), die Daten in einem einzigen Ordner (`BINDUNG_DATEN`, im Container als
eingehängtes Volume gedacht), Nutzer von der Kommandozeile. Bindung selbst
spricht nur http und erwartet davor einen Proxy, der https übernimmt;
`BINDUNG_SICHER=1` sagt, dass er davorsteht. Ein **Docker-Image** mit
Compose-Datei und TLS-Proxy ist geplant, aber noch nicht gebaut.

## Einstellungen aus der Umgebung

| Variable | Wirkung | Vorgabe |
|---|---|---|
| `BINDUNG_DATEN` | Datenordner | `~/Library/Application Support/Bindung` (Mac) |
| `BINDUNG_HOST` | Adresse, an die der Server bindet | `127.0.0.1` |
| `BINDUNG_PORT` | Port von `bindung serve` | `8785` |
| `BINDUNG_SICHER` | `1`, wenn ein TLS-Proxy davorsteht (Cookie wird `Secure`) | aus |
| `BINDUNG_PUSH_KONTAKT` | Kontaktadresse (`sub`) in den Push-Schlüsseln | `mailto:bindung@localhost` |
| `BINDUNG_TAGESAUFGABE` | `0` schaltet die Tagesmeldung dieses Prozesses aus | an |

Nur für die Mac-App (`bindung app`): `BINDUNG_APP_PORT` (Vorgabe `8788`),
`BINDUNG_KEIN_BROWSER=1` (Browser nicht öffnen), `BINDUNG_KEINE_MENUELEISTE=1`.

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
