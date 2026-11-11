"""Push: Anmeldung des Browsers, Testmeldung, Service Worker und Hinweis (PLAN.md, Abschnitt 10).

- `GET /push/schluessel`  der oeffentliche Schluessel, mit dem der Browser sich anmeldet
- `POST /push/abo`        der Browser meldet sich an (JSON: Endpunkt und Schluessel)
- `DELETE /push/abo`      der Browser meldet sich ab (JSON: Endpunkt)
- `POST /push/test`       eine Testmeldung an alle Abos des Nutzers
- `GET /sw.js`            der Service Worker, aus dem Wurzelpfad, damit er die ganze App abdeckt
- `POST /hinweis/weggeklickt`  der Hinweis ist fuer heute weg

Die Abos gehoeren dem Nutzer, der sie anlegt; gesehen und geloescht wird nur das eigene.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from bindung import personen, push, tagesmeldung
from bindung.personen import EingabeFehler
from bindung.web import basis
from bindung.web.routen.einstellungen import abschnitt_antwort

router = APIRouter()

SERVICE_WORKER = basis.STATISCH / "sw.js"


async def _json(request: Request) -> dict:
    """Der JSON-Koerper als Objekt; alles andere ist eine abgelehnte Eingabe."""
    try:
        daten = await request.json()
    except ValueError:
        raise EingabeFehler("Die Anfrage ist kein JSON.") from None
    if not isinstance(daten, dict):
        raise EingabeFehler("Die Anfrage ist kein JSON-Objekt.")
    return daten


def _abgelehnt(fehler: EingabeFehler) -> JSONResponse:
    return JSONResponse({"fehler": str(fehler)}, status_code=422)


@router.get("/push/schluessel")
def schluessel():
    return JSONResponse({"schluessel": push.oeffentlicher_schluessel()},
                        headers={"Cache-Control": "private, no-store"})


@router.post("/push/abo")
async def abo_anmelden(request: Request):
    try:
        daten = await _json(request)
        schluessel_ = daten.get("keys") if isinstance(daten.get("keys"), dict) else {}
        push.abo_speichern(basis.con(request), basis.nutzer(request)["id"],
                           daten.get("endpoint"), schluessel_.get("p256dh"),
                           schluessel_.get("auth"))
    except EingabeFehler as fehler:
        return _abgelehnt(fehler)
    return Response(status_code=204)


@router.delete("/push/abo")
async def abo_abmelden(request: Request):
    try:
        daten = await _json(request)
    except EingabeFehler as fehler:
        return _abgelehnt(fehler)
    # Auch ein Abo, das es nicht (mehr) gibt, ist abgemeldet: 204 in beiden Faellen.
    push.abo_loeschen(basis.con(request), basis.nutzer(request)["id"], daten.get("endpoint"))
    return Response(status_code=204)


TESTMELDUNG = {"titel": tagesmeldung.TITEL, "tag": "tagesmeldung", "url": "/",
               "icon": tagesmeldung.SYMBOL,
               "text": "Testmeldung: So sieht die Tagesmeldung aus."}


@router.post("/push/test")
def testmeldung(request: Request):
    """Sendet die Testmeldung an alle Abos und zeigt im Abschnitt, wie es ausgegangen ist."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    abos = push.abos(con, nutzer_id)
    gesendet = sum(push.senden(con, abo, TESTMELDUNG) for abo in abos)
    if not abos:
        text, gut = "Es ist noch kein Browser angemeldet.", False
    elif gesendet == len(abos):
        text, gut = f"Testmeldung an {_browser(gesendet)} gesendet.", True
    else:
        text, gut = (f"Nur {gesendet} von {_browser(len(abos))} haben die Testmeldung "
                     "angenommen. Mehr steht im Protokoll des Servers."), False
    return abschnitt_antwort(request, "benachrichtigungen", test={"text": text, "gut": gut})


def _browser(zahl: int) -> str:
    return "1 Browser" if zahl == 1 else f"{zahl} Browser"


@router.get("/sw.js")
def service_worker():
    """Aus dem Wurzelpfad, sonst deckt der Worker nur `/statisch/` ab; nie aus dem Cache."""
    return FileResponse(SERVICE_WORKER, media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@router.post("/hinweis/weggeklickt")
def hinweis_wegklicken(request: Request):
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    tagesmeldung.hinweis_wegklicken(con, nutzer_id, personen.heute(con, nutzer_id))
    if request.headers.get("hx-request"):
        return HTMLResponse("")   # der Streifen wird durch nichts ersetzt
    return RedirectResponse("/", status_code=303)
