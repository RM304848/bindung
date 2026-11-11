"""Was alle Seiten brauchen: Vorlagen, Verbindung, angemeldeter Nutzer.

Hier haengt nichts an der App: dieses Modul kennt weder `app` noch einen
Router, damit die Richtung der Abhaengigkeiten eindeutig bleibt
(`server.py` -> `routen/*` -> `basis.py`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import sqlite3
from functools import cache
from pathlib import Path

from fastapi import Request
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
OFFENE_PFADE = ("/anmeldung", "/sw.js")
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
