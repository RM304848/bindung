"""Startet die gebaute App und prueft, dass sie wirklich laeuft.

    python werkzeuge/paket/rauchtest.py "dist/Bindung.app/Contents/MacOS/Bindung"

In einem leeren Datenordner, ohne Browser: antwortet sie, richtet sie den ersten Nutzer ein,
zeigt sie ihre Seiten, liefert sie Manifest, Service Worker, Stylesheet und Symbole, laesst
sie sich beenden? Einer App, der eine Vorlage oder eine Datei fehlt, sieht man das beim Start
nicht an -- sie stuerzt erst bei der ersten Seite.

Die Menueleiste bleibt an: so wird auch geprueft, dass AppKit in der App steckt. Auf einem
Rechner ohne Bildschirm (ssh) hilft `BINDUNG_KEINE_MENUELEISTE=1` in der Umgebung.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 8798
BASIS = f"http://127.0.0.1:{PORT}"
NAME, PASSWORT = "Rauchtest", "rauchtest-passwort"


class _KeineUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_OEFFNER = urllib.request.build_opener(_KeineUmleitung)


def _holen(pfad: str, *, methode: str = "GET", daten: dict | None = None,
           cookie: str = "") -> tuple[int, dict, bytes]:
    """(Status, Kopfzeilen, Inhalt); Umleitungen werden nicht verfolgt, sondern gemeldet."""
    anfrage = urllib.request.Request(
        BASIS + pfad, method=methode, headers={"Cookie": cookie} if cookie else {},
        data=urllib.parse.urlencode(daten).encode() if daten is not None else None)
    try:
        with _OEFFNER.open(anfrage, timeout=15) as antwort:
            return antwort.status, dict(antwort.headers), antwort.read()
    except urllib.error.HTTPError as fehler:
        return fehler.code, dict(fehler.headers), fehler.read()


def _fehler(text: str) -> None:
    sys.exit(f"FEHLER: {text}")


def _erwarte(bedingung: bool, text: str) -> None:
    if not bedingung:
        _fehler(text)


def pruefen() -> int:
    """Alle Pruefungen gegen die laufende App; gibt die Zahl der Pruefungen zurueck."""
    n = 0

    def ok(bedingung: bool, text: str) -> None:
        nonlocal n
        _erwarte(bedingung, text)
        n += 1

    status, kopf, _ = _holen("/healthz")
    ok(status == 200, f"/healthz: {status}")
    # Erster Start: noch kein Nutzer, die Anmeldung fuehrt zum Einrichten.
    status, kopf, _ = _holen("/anmeldung")
    ok(status == 303 and kopf.get("location") == "/einrichten", f"/anmeldung: {status}")
    status, _, text = _holen("/einrichten")
    ok(status == 200 and "Einrichten" in text.decode(), f"/einrichten: {status}")
    status, kopf, _ = _holen("/einrichten", methode="POST",
                             daten={"name": NAME, "passwort": PASSWORT, "wiederholung": PASSWORT})
    ok(status == 303 and "set-cookie" in {k.lower() for k in kopf}, f"Einrichten: {status}")
    cookie = kopf.get("Set-Cookie", kopf.get("set-cookie", "")).split(";")[0]
    # Danach ist die Seite zu: es gibt jetzt einen Nutzer.
    ok(_holen("/einrichten")[0] == 404, "/einrichten blieb offen")

    status, _, seite = _holen("/", cookie=cookie)
    html = seite.decode("utf-8", "replace")
    ok(status == 200 and "Traceback" not in html, f"/: {status}")
    ok("data-beenden" in html, "Der Knopf Beenden fehlt.")
    for pfad in ("/?karte=aufmerksamkeit", "/einstellungen", "/?suche=anna"):
        status, _, text = _holen(pfad, cookie=cookie)
        ok(status == 200 and b"Traceback" not in text, f"{pfad}: {status}")

    # Stylesheet und Skripte mit Fingerabdruck, Symbole, Manifest, Service Worker.
    for muster, art in ((r'href="(/statisch/stil\.css\?v=[0-9a-f]{10})"', "text/css"),
                        (r'src="(/statisch/bindung\.js\?v=[0-9a-f]{10})"', "javascript"),
                        (r'href="(/statisch/symbol\.svg\?v=[0-9a-f]{10})"', "image/svg"),
                        (r'rel="apple-touch-icon" href="(/statisch/symbol-180\.png\?v=\w{10})"',
                         "image/png")):
        treffer = re.search(muster, html)
        ok(treffer is not None, f"Kopfzeile fehlt: {muster}")
        status, kopf, _ = _holen(treffer.group(1))
        ok(status == 200 and art in kopf.get("content-type", ""),
           f"{treffer.group(1)}: {status} {kopf.get('content-type')}")

    treffer = re.search(r'rel="manifest" href="(/manifest\.webmanifest\?v=[0-9a-f]{10})"', html)
    ok(treffer is not None, "Der Link auf das Manifest fehlt.")
    status, kopf, inhalt = _holen("/manifest.webmanifest")   # ohne Sitzung: offen
    ok(status == 200 and "manifest+json" in kopf.get("content-type", ""), f"Manifest: {status}")
    manifest = json.loads(inhalt)
    ok(manifest["name"] == "Bindung" and manifest["display"] == "standalone", "Manifest falsch")
    for symbol in manifest["icons"]:
        status, kopf, _ = _holen(symbol["src"])
        ok(status == 200, f"Symbol {symbol['src']}: {status}")
    status, kopf, inhalt = _holen("/sw.js")
    ok(status == 200 and "javascript" in kopf.get("content-type", "") and b"push" in inhalt,
       f"/sw.js: {status}")

    # Beenden braucht die Sitzung; fremder Ursprung wird abgelehnt.
    ok(_holen("/api/beenden", methode="POST", daten={})[0] == 303, "Beenden ohne Sitzung")
    return n


def main() -> None:
    programm = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        daten = Path(tmp) / "daten"
        umgebung = {**os.environ, "BINDUNG_DATEN": str(daten), "BINDUNG_KEIN_BROWSER": "1",
                    "BINDUNG_APP_PORT": str(PORT), "BINDUNG_PORT": "8797",
                    "BINDUNG_TAGESAUFGABE": "0"}
        lauf = subprocess.Popen([str(programm)], env=umgebung, cwd=tmp,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            zuletzt = "keine Antwort"
            for _ in range(120):
                try:
                    status, _, text = _holen("/healthz")
                    if status == 200 and json.loads(text).get("app") == "Bindung":
                        break
                    zuletzt = f"{status}: {text[:200]!r}"
                except (OSError, ValueError) as fehler:
                    zuletzt = repr(fehler)
                if lauf.poll() is not None:
                    sys.exit(f"Die App hat sich beendet ({lauf.returncode}).\n"
                             + lauf.stdout.read().decode("utf-8", "replace"))
                time.sleep(0.5)
            else:
                sys.exit(f"Die App kam nicht hoch. Zuletzt: {zuletzt}")
            zahl = pruefen()
            _erwarte((daten / "bindung.db").exists(), "Die Datenbank liegt nicht im Datenordner.")
            # Beenden braucht eine Sitzung; `pruefen` gibt ihren Cookie nicht heraus: neu anmelden.
            status, kopf, _ = _holen("/anmeldung", methode="POST",
                                     daten={"name": NAME, "passwort": PASSWORT})
            cookie = kopf.get("Set-Cookie", kopf.get("set-cookie", "")).split(";")[0]
            _erwarte(status == 303 and cookie, f"Anmeldung: {status}")
            _erwarte(_holen("/api/beenden", methode="POST", daten={}, cookie=cookie)[0] == 200,
                     "Beenden wurde abgelehnt.")
            lauf.wait(timeout=15)
            print(f"Rauchtest bestanden: {zahl} Pruefungen, beendet mit {lauf.returncode}.")
        finally:
            if lauf.poll() is None:
                lauf.kill()
                print(lauf.stdout.read().decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
