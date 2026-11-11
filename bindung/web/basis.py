"""Was alle Seiten brauchen: Vorlagen, Verbindung, angemeldeter Nutzer.

Hier haengt nichts an der App: dieses Modul kennt weder `app` noch einen
Router, damit die Richtung der Abhaengigkeiten eindeutig bleibt
(`server.py` -> `routen/*` -> `basis.py`).
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from bindung import angehoerige, faelligkeit, stichtage

PAKET = Path(__file__).resolve().parent
VORLAGEN = PAKET / "vorlagen"
STATISCH = PAKET / "statisch"

TEMPLATES = Jinja2Templates(directory=str(VORLAGEN))


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

#: Pfade, die ohne Sitzung erreichbar sind. `/kalender/` ist die Kalenderadresse
#: mit ihrem eigenen Geheimnis in der URL (WP4).
OFFENE_PFADE = ("/anmeldung",)
OFFENE_PRAEFIXE = ("/statisch/", "/kalender/")


def ist_offen(pfad: str) -> bool:
    """Darf dieser Pfad ohne Anmeldung aufgerufen werden?"""
    return pfad in OFFENE_PFADE or pfad.startswith(OFFENE_PRAEFIXE)


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
