"""Was alle Seiten brauchen: Vorlagen, Verbindung, angemeldeter Nutzer.

Hier haengt nichts an der App: dieses Modul kennt weder `app` noch einen
Router, damit die Richtung der Abhaengigkeiten eindeutig bleibt
(`server.py` -> `routen/*` -> `basis.py`).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

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


TEMPLATES.env.filters["erste_zeile"] = _erste_zeile
TEMPLATES.env.filters["telefonnummer"] = _telefonnummer

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
