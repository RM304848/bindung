"""Was die App zum Doppelklicken braucht: Lebenszeichen, Manifest, Beenden.

- `GET /healthz`               sagt dem Starter und dem Rauchtest, dass hier Bindung antwortet
- `GET /manifest.webmanifest`  das Web-App-Manifest (Installieren auf dem Telefon, im Dock)
- `POST /api/beenden`          der Knopf "Beenden" in der Seitenleiste, nur in der Mac-App
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bindung import __version__, pfade
from bindung.web import basis

router = APIRouter()


def daten_kennung() -> str:
    """Ein Fingerabdruck des Datenordners -- nicht der Pfad selbst.

    `/healthz` ist offen. Der Starter vergleicht damit, ob ein laufender `bindung serve`
    denselben Datenordner benutzt wie er selbst, ohne dass jeder, der den Port erreicht,
    den Pfad (und damit den Benutzernamen des Rechners) erfaehrt.
    """
    return hashlib.sha256(str(pfade.DATEN.resolve()).encode("utf-8")).hexdigest()[:12]


@router.get("/healthz")
def healthz():
    return JSONResponse({"ok": True, "app": "Bindung", "version": __version__,
                         "daten": daten_kennung()}, headers={"Cache-Control": "no-store"})


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(basis.manifest(), media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


@router.post("/api/beenden", dependencies=[Depends(basis.nur_eigener_ursprung)])
def beenden():
    """Beendet den Server der Mac-App.

    Ohne Starter (`bindung serve`) gibt es nichts, was sich von hier beenden liesse: dann
    404, statt eines Servers, den eine fremde Seite abschaltet. Angemeldet sein muss man
    auch (die Tuer in `server.py`).
    """
    if basis.BEENDEN is None:
        return JSONResponse({"fehler": "läuft nicht als App"}, status_code=404)
    basis.BEENDEN()
    return {"ok": True}
