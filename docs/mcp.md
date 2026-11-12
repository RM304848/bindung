# Bindung mit einem Bot benutzen (MCP)

`bindung mcp` lässt einen Bot wie Claude Desktop Bindung abfragen und für dich
eintragen: „Wen habe ich lange nicht gesprochen?“, „Was haben Anna und ich zuletzt
besprochen?“, „Anruf mit Anna, wir haben über den Umzug gesprochen“, „Leg Ben
Muster an, Tag Chor“. Was der Bot einträgt, steht sofort in der App.

Der Zugang spricht das *Model Context Protocol* über Standardein- und -ausgabe. Er
öffnet keinen Port, schickt nichts ins Netz und läuft nur, solange der Client ihn
gestartet hat. Wie alles in Bindung bleiben die Daten auf deinem Rechner – was der Bot
liest, liest allerdings das Modell dahinter, also auch Profilnotizen und Notizen zu
Touchpoints. Verbinde nur einen Client, dem du das zutraust.

## Einrichten

Voraussetzung: Bindung ist installiert (`.venv` im Projektordner) und es gibt einen
Nutzer (`bindung nutzer anlegen <name>` oder in der Mac-App eingerichtet).

```bash
.venv/bin/bindung mcp --nutzer Anna
```

Der Befehl liest Zeilen von stdin und antwortet auf stdout; im Terminal sieht man nichts,
bis man JSON eintippt. Er ist dafür gedacht, vom Client gestartet zu werden.

- `--nutzer NAME`: als dieser Nutzer handeln (Groß-/Kleinschreibung egal). Ohne Angabe
  und mit genau einem Nutzer gilt dieser; bei mehreren Nutzern ist `--nutzer` Pflicht.
  Ein unbekannter Name beendet den Befehl mit einer Meldung auf stderr.
- `BINDUNG_DATEN`: der Datenordner. Ohne Angabe derselbe wie für die App; `bindung ort`
  zeigt ihn. Der Bot und der Server (oder die Mac-App) können gleichzeitig laufen.

### Claude Desktop

In `~/Library/Application Support/Claude/claude_desktop_config.json` unter
`mcpServers` ergänzen und Claude Desktop neu starten:

```json
{
  "mcpServers": {
    "bindung": {
      "command": "/Users/DEIN-NAME/Projects/bindung/.venv/bin/bindung",
      "args": ["mcp", "--nutzer", "Anna"],
      "env": {
        "BINDUNG_DATEN": "/Users/DEIN-NAME/Library/Application Support/Bindung"
      }
    }
  }
}
```

Der Pfad zu `bindung` muss vollständig sein: Claude Desktop startet den Befehl ohne deine
Shell. `env` kannst du weglassen, wenn die App den Standardordner benutzt.

### Ein anderer Client

Jeder Client, der einen MCP-Server über stdio starten kann, braucht dieselben drei
Angaben: den Befehl (`…/.venv/bin/bindung`), die Argumente (`mcp`, optional
`--nutzer NAME`) und optional die Umgebung (`BINDUNG_DATEN`). Unterstützt sind die
Protokollfassungen 2025-06-18, 2025-03-26 und 2024-11-05.

## Was der Bot kann

Lesen (ändert nichts):

| Werkzeug | Antwort |
|---|---|
| `personen_suchen` | Personen nach Text (Name, Firma, Ort, Tag), Tag, „Noch kein Touchpoint“ oder Archiv: Nummer, Name, Firma, Tags, Zustand, letzter Touchpoint |
| `person` | alles, was die Personenseite zeigt: Felder, Profilnotiz, Zustand, Fällig am, Zuletzt besprochen mit den Notizen, Angehörige, Stichtage |
| `wer_wartet` | die drei Karten (Braucht Aufmerksamkeit, Erkaltet, Diese Woche) mit Namen, sortiert wie in der App |
| `diese_woche` | wer in den nächsten sieben Tagen fällig wird und welche Stichtage im Vorlauf liegen |
| `tags` | die Tags mit der Zahl ihrer Personen |

Schreiben (jedes über dieselben Funktionen wie die Seiten, mit denselben Prüfungen und
denselben Fehlermeldungen):

| Werkzeug | Was es tut |
|---|---|
| `person_anlegen` | legt eine Person an: Name, optional Firma, Rolle, Telefon, E-Mail, Ort, Herkunft, Profilnotiz, Tags (mit Namen) und eine grobe Schätzung des letzten Touchpoints. Gibt es den Namen schon, lehnt es ab (außer mit `trotzdem`). |
| `touchpoint_eintragen` | trägt einen Touchpoint ein: Person (Nummer oder eindeutiger Name), Art, Datum (Standard heute, nicht in der Zukunft), Notiz. Löscht den Nächsten Termin der Person. |
| `profilnotiz_setzen` | ersetzt die Profilnotiz (die Antwort zeigt den alten Text) oder hängt Text an. |
| `stichtag_anlegen` | legt einen Geburtstag, Jahrestag oder benannten Tag an, mit oder ohne Jahr. |

Bewusst **nicht** dabei: Personen archivieren oder löschen, Touchpoints oder Stichtage
ändern oder löschen, Tags umbenennen oder löschen, Einstellungen. Ein Fehler dort fällt
nicht auf; das machst du in der App.

Ressourcen: `bindung://glossar` (die Begriffe der App aus `CONTEXT.md`, damit der Bot
„Touchpoint“ sagt) und `bindung://heute` (der Text der heutigen Tagesmeldung).

## Wie der Bot antwortet

Antworten sind Text, so formatiert wie die App („überfällig seit 12 Tagen“, „vor 3
Wochen“). Hinter jedem Namen steht die Nummer der Person in eckigen Klammern, `Anna
Beispiel [12]`; mit ihr kann der Bot eine Person sicher wieder aufrufen.

- **Mehrdeutige Namen werden nicht geraten.** Passt ein Name auf mehrere Personen, lehnt
  das Werkzeug ab und nennt die Kandidaten mit Nummer; der Bot soll nachfragen.
- **Fehler** (zum Beispiel ein Touchpoint in der Zukunft) kommen als Fehlerantwort mit
  dem Satz, den die Seite zeigen würde.
- **Doppeltes wird abgelehnt**: derselbe Touchpoint (Person, Datum, Art, Notiz) oder
  derselbe Stichtag ein zweites Mal, falls der Client einen Aufruf wiederholt.
- **Neue Tags** legt `person_anlegen` an, wenn es sie noch nicht gibt, und sagt es in der
  Antwort. Schreibweisen gleichen Namen (Groß-/Kleinschreibung egal) werden zugeordnet.

## Ausprobieren ohne Client

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"wer_wartet","arguments":{}}}' \
  | .venv/bin/bindung mcp
```

Eine JSON-Nachricht je Zeile; meldet sich der Befehl mit „Es gibt noch keinen Nutzer“,
fehlt der Nutzer im Datenordner (siehe `bindung ort`). Meldungen des Programms stehen auf
stderr, stdout gehört dem Protokoll.

## Hinweis für Entwickler

Das Glossar liest der Server aus `CONTEXT.md` neben dem Paket. Eine installierte Kopie
ohne den Quellordner (zum Beispiel die Mac-App) hat es nicht, dann antwortet die
Ressource mit einer Meldung; der Bot-Zugang ist für die Installation aus dem Quellordner
gedacht.
