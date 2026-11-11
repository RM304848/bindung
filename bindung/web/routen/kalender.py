"""Der Kalender als Adresse und als Datei (PLAN.md, Abschnitt 9).

`/kalender/<geheimnis>.ics` ist die einzige Route ohne Anmeldung: das Geheimnis
in der Adresse ersetzt sie (`basis.ist_offen`). `/kalender/herunterladen`
liefert dasselbe als Datei, aber nur mit Anmeldung -- die Tuer in `server.py`
schickt sonst zur Anmeldung.

Ein unbekanntes Geheimnis ist ein 404 wie jeder andere: kein Hinweis darauf, ob
es einem echten nahe kam, und keine Meldung, die sich von „gibt es nicht“
unterscheidet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from bindung import kalender
from bindung.web import basis

router = APIRouter()

TYP = "text/calendar; charset=utf-8"
#: Die Datei enthaelt Namen und Notizen: nirgends zwischenspeichern.
KOPF = {"Cache-Control": "private, no-store"}


@router.get("/kalender/herunterladen")
def herunterladen(request: Request) -> Response:
    text = kalender.kalender_text(basis.con(request), basis.nutzer(request)["id"])
    return Response(text, media_type=TYP, headers={
        **KOPF, "Content-Disposition": 'attachment; filename="bindung.ics"'})


@router.get("/kalender/{token}.ics")
def abonnement(request: Request, token: str) -> Response:
    con = basis.con(request)
    nutzer_id = kalender.nutzer_zu_token(con, token)
    if nutzer_id is None:
        raise HTTPException(404)
    return Response(kalender.kalender_text(con, nutzer_id), media_type=TYP, headers=KOPF)
