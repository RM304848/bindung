# Ein Release veröffentlichen

Jeder Release (Tag) bekommt vor dem Taggen einen Abschnitt in `CHANGELOG.md`,
geschrieben für die Menschen, die Bindung benutzen (siehe `CLAUDE.md`). Das
Skript `werkzeuge/release_notes.py` holt diesen Abschnitt für GitHub; ohne
Abschnitt bricht es ab, und es gibt keinen Release ohne Notizen.

Alle Befehle laufen im Projektordner (`~/Projects/bindung`).

## 1. Vorbereiten (einmal je Version)

1. Die Nummer in `bindung/__init__.py` (`__version__`) setzen, nur dort.
2. In `CHANGELOG.md` die Überschrift `## Unveröffentlicht` zu
   `## <Version> (<Datum>)` machen, darüber eine neue, leere
   `## Unveröffentlicht` setzen. Den Abschnitt als Nutzer lesen: eine
   zusammenhängende Beschreibung, nach Dingen geordnet, die man bemerkt, mit den
   Namen aus der Oberfläche, ohne Entwicklerwörter.
3. Prüfen und committen:

   ```bash
   .venv/bin/python -m pytest
   .venv/bin/ruff check .
   git status --short
   ```

4. Den annotierten Tag auf den letzten Commit setzen, Nachricht ist der erste
   Satz des Abschnitts:

   ```bash
   git tag -a v0.1.0 -m "$(.venv/bin/python werkzeuge/release_notes.py 0.1.0 --erste-zeile)"
   ```

## 2. Das Disk-Image bauen

Vom getaggten Stand aus, damit das Image zum Tag passt (der Baum muss sauber
sein):

```bash
git describe --tags --exact-match    # muss v0.1.0 ausgeben
.venv/bin/pip install -e '.[dev,paket]'
werkzeuge/paket/bauen.sh
```

`bauen.sh` baut das Symbol, die App, lässt den Rauchtest gegen die gebaute App
laufen und schreibt `dist/Bindung-0.1.0-mac.dmg`. Schlägt der Rauchtest fehl,
gibt es kein Image und keinen Release.

## 3. Das Repository anlegen (nur beim allerersten Release)

Öffentlich, auf dem Konto `RM304848`:

```bash
gh repo create RM304848/bindung --public --source=. --remote=origin \
  --description "Bindung: den Kontakt zu den Menschen halten, die einem wichtig sind"
```

`--source=. --remote=origin` richtet nur die Fernadresse ein; hochgeladen wird
im nächsten Schritt. Vorher einmal ansehen, was öffentlich wird: `git log
--stat | less` und `git grep -n -i -E "@|/Users/"` (keine echten Namen, Adressen
oder Pfade; Testdaten sind erfunden, `CLAUDE.md`).

## 4. Hochladen

```bash
git push -u origin main
git push origin v0.1.0
```

## 5. Den Release anlegen

Die Notizen aus dem CHANGELOG in eine Datei (liegt in `build/`, ist ignoriert),
dann Release mit Notizen und Disk-Image:

```bash
.venv/bin/python werkzeuge/release_notes.py 0.1.0 > build/notizen-0.1.0.md
gh release create v0.1.0 --title "Bindung 0.1.0" --notes-file build/notizen-0.1.0.md \
  dist/Bindung-0.1.0-mac.dmg
```

## 6. Prüfen

```bash
gh release view v0.1.0
```

Es muss zu sehen sein: der Titel, die Notizen aus dem CHANGELOG (nicht nur
Download-Hinweise) und das Disk-Image als Anhang. Danach das Image einmal
herunterladen, öffnen (Rechtsklick › „Öffnen“, es ist nicht signiert) und prüfen,
dass die Anmeldeseite erscheint.
