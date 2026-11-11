"""Was alle Seiten brauchen: Vorlagen, Verbindung, angemeldeter Nutzer.

Hier haengt nichts an der App: dieses Modul kennt weder `app` noch einen
Router, damit die Richtung der Abhaengigkeiten eindeutig bleibt
(`server.py` -> `routen/*` -> `basis.py`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from functools import cache
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from bindung import angehoerige, auth, faelligkeit, stichtage

PAKET = Path(__file__).resolve().parent
VORLAGEN = PAKET / "vorlagen"
STATISCH = PAKET / "statisch"

TEMPLATES = Jinja2Templates(directory=str(VORLAGEN))


@cache
def statisch_kennung(name: str) -> str:
    """Ein kurzer Fingerabdruck des Inhalts einer statischen Datei.

    Er haengt als `?v=` an der Adresse: aendert sich die Datei mit einem Update,
    aendert sich die Adresse, und kein Browser zeigt ein altes Stylesheet oder
    Skript aus seinem Cache. Je Prozess einmal gelesen; `serve --reload`
    startet den Prozess neu.
    """
    return hashlib.sha256((STATISCH / name).read_bytes()).hexdigest()[:10]


def statisch(name: str) -> str:
    """Die Adresse einer statischen Datei mit Fingerabdruck, fuer die Vorlagen."""
    return f"/statisch/{name}?v={statisch_kennung(name)}"


TEMPLATES.env.globals["statisch"] = statisch

#: Gesetzt vom Starter der Mac-App (`bindung/starter.py`): beendet den Server. Nur dann
#: gibt es den Knopf "Beenden" und `POST /api/beenden`; unter `bindung serve` bleibt es `None`.
BEENDEN: Callable[[], None] | None = None

TEMPLATES.env.globals["app_modus"] = lambda: BEENDEN is not None


# ------------------------------------------------------------ Palette und Manifest

@cache
def palette() -> dict[str, dict[str, str]]:
    """Die Farben des Stylesheets: {"hell": {"grund": "#f2f2f5", ...}, "dunkel": {...}}.

    Gelesen aus den `:root`-Bloecken von `stil.css` -- dort stehen die Farben, und nur dort
    (docs/design_conventions.yaml). Die Kopfzeilen (`theme-color`) und das Manifest holen sie
    von hier und tragen keine eigene Farbe.
    """
    css = re.sub(r"/\*.*?\*/", " ", (STATISCH / "stil.css").read_text(encoding="utf-8"),
                 flags=re.S)

    def farben(block: str) -> dict[str, str]:
        return dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", block))

    hell = re.search(r":root\s*\{([^{}]*)\}", css)
    dunkel = re.search(r"prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^{}]*)\}", css)
    return {"hell": farben(hell.group(1)), "dunkel": farben(dunkel.group(1))}


def manifest() -> dict:
    """Das Web-App-Manifest (https://www.w3.org/TR/appmanifest/)."""
    hell = palette()["hell"]
    return {
        "name": "Bindung",
        "short_name": "Bindung",
        "description": "Den Kontakt zu den Menschen halten, die einem wichtig sind.",
        "lang": "de",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": hell["grund"],
        "theme_color": hell["grund"],
        "icons": [
            {"src": statisch("symbol-192.png"), "sizes": "192x192", "type": "image/png",
             "purpose": "any"},
            {"src": statisch("symbol-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
            {"src": statisch("symbol-maskable-512.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
            {"src": statisch("symbol.svg"), "sizes": "any", "type": "image/svg+xml",
             "purpose": "any"},
        ],
    }


@cache
def manifest_adresse() -> str:
    """`/manifest.webmanifest?v=...`: der Fingerabdruck haengt am Inhalt, wie bei `statisch`."""
    inhalt = json.dumps(manifest(), sort_keys=True).encode("utf-8")
    return f"/manifest.webmanifest?v={hashlib.sha256(inhalt).hexdigest()[:10]}"


TEMPLATES.env.globals["palette"] = palette
TEMPLATES.env.globals["manifest_adresse"] = manifest_adresse


def _erste_zeile(text: str | None) -> str:
    """Die erste nicht leere Zeile eines Freitexts."""
    for zeile in (text or "").splitlines():
        if zeile.strip():
            return zeile.strip()
    return ""


def _telefonnummer(text: str | None) -> str:
    """Eine Nummer fuer `tel:`: Ziffern und ein fuehrendes Plus, sonst nichts."""
    return re.sub(r"(?!^\+)\D", "", (text or "").strip())


def _tag(wert: str | dt.date) -> dt.date:
    return wert if isinstance(wert, dt.date) else dt.date.fromisoformat(wert)


def _datum_de(wert: str | dt.date | None) -> str:
    """Ein ISO-Tag als 24.09.2026."""
    return _tag(wert).strftime("%d.%m.%Y") if wert else ""


def _vor_datum(wert: str | dt.date, heute: dt.date) -> str:
    """„vor 3 Wochen“ fuer ein Datum, von `heute` aus gesehen."""
    return faelligkeit.vor_text((heute - _tag(wert)).days)


TEMPLATES.env.filters["erste_zeile"] = _erste_zeile
TEMPLATES.env.filters["telefonnummer"] = _telefonnummer
TEMPLATES.env.filters["datum_de"] = _datum_de
TEMPLATES.env.filters["vor_datum"] = _vor_datum
TEMPLATES.env.filters["zustand_text"] = faelligkeit.zustand_text
TEMPLATES.env.filters["rolle_wort"] = angehoerige.rolle_wort
TEMPLATES.env.filters["stichtag_de"] = stichtage.text_de

#: Pfade, die ohne Sitzung erreichbar sind.
#: `/sw.js` ist der Service Worker: eine Skriptdatei ohne Daten, die der Browser auch dann
#: abrufen muss, wenn gerade keine Sitzung im Spiel ist.
#: `/manifest.webmanifest` holt der Browser ohne Cookies ab (kein `use-credentials`), und
#: `/healthz` fragt der Starter der Mac-App, ob schon eine Bindung antwortet. Keines enthaelt Daten.
#: `/einrichten` (erster Nutzer der Mac-App) antwortet 404, sobald es einen Nutzer gibt.
OFFENE_PFADE = ("/anmeldung", "/sw.js", "/manifest.webmanifest", "/healthz", "/einrichten")
OFFENE_PRAEFIXE = ("/statisch/",)
#: Die Kalenderadresse (`/kalender/<geheimnis>.ics`) traegt ihr Geheimnis in der URL und
#: ist offen. `/kalender/herunterladen` (ohne `.ics`) bleibt hinter der Anmeldung.
KALENDER_PRAEFIX, KALENDER_ENDUNG = "/kalender/", ".ics"


def ist_offen(pfad: str) -> bool:
    """Darf dieser Pfad ohne Anmeldung aufgerufen werden?"""
    return (pfad in OFFENE_PFADE or pfad.startswith(OFFENE_PRAEFIXE)
            or (pfad.startswith(KALENDER_PRAEFIX) and pfad.endswith(KALENDER_ENDUNG)))


_HOST = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$|^\[[0-9A-Fa-f:]+\](:\d{1,5})?$")


def _kopf(request: Request, name: str) -> str:
    """Der erste Wert einer Kopfzeile (Proxys haengen weitere mit Komma an)."""
    return request.headers.get(name, "").split(",")[0].strip()


def aussenadresse(request: Request) -> tuple[str, str]:
    """(Schema, Host), unter denen der Nutzer die App erreicht -- fuer Adressen zum Kopieren.

    Hinter einem TLS-Proxy sieht die App `http` und den Host des Proxys. `BINDUNG_SICHER=1`
    sagt, dass er davorsteht (https); sonst gelten `X-Forwarded-Proto` und
    `X-Forwarded-Host`, wenn der Proxy sie setzt. Die Werte landen nur in der Seite des
    Nutzers selbst, deshalb muss man dem Proxy hier nicht vertrauen; ein ungueltiger Host
    faellt auf den der Anfrage zurueck.
    """
    weitergeleitet = _kopf(request, "x-forwarded-proto").lower()
    if auth.cookie_sicher():
        schema = "https"
    elif weitergeleitet in ("http", "https"):
        schema = weitergeleitet
    else:
        schema = request.url.scheme
    host = _kopf(request, "x-forwarded-host") or request.headers.get("host", "")
    return schema, host if _HOST.match(host) else request.url.netloc


def nur_eigener_ursprung(request: Request) -> None:
    """Schreibende Anfragen nur von der eigenen Seite.

    Eine fremde Webseite kann den Browser des Besitzers dazu bringen, an 127.0.0.1 zu
    schicken. `Origin` verraet, woher die Anfrage kommt; ein Formular dieser Seite nennt
    denselben Host. Ohne `Origin` (Kommandozeile, Tests) wird nichts blockiert.
    """
    ursprung = request.headers.get("origin")
    if ursprung and ursprung.split("://", 1)[-1] != request.headers.get("host"):
        raise HTTPException(403, "Anfrage von fremdem Ursprung abgelehnt")


def con(request: Request) -> sqlite3.Connection:
    """Die Verbindung dieser Anfrage; die Tuer in `server.py` oeffnet und schliesst sie."""
    return request.state.con


def nutzer(request: Request) -> sqlite3.Row | None:
    """Der angemeldete Nutzer, sonst `None`."""
    return request.state.nutzer


def seite(request: Request, vorlage: str, status_code: int = 200, **kontext):
    """Rendert eine Vorlage mit dem Nutzer im Kontext."""
    kontext.setdefault("nutzer", nutzer(request))
    return TEMPLATES.TemplateResponse(request, vorlage, kontext, status_code=status_code)
