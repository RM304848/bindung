"""Die App und die Tuer davor: Anmeldung, Abmeldung, Sitzungspruefung.

Die Seiten selbst stehen in `bindung/web/routen/`, je Seitengruppe ein Modul.
Hier stehen nur die App, die Tuer und das Zusammenhaengen.

Kein CDN: die Seiten bringen ihr Stylesheet und HTMX selbst mit, die App laeuft
ohne Netz.
"""

from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from bindung import auth, db
from bindung.web import basis
from bindung.web.routen import kontakte, personen

app = FastAPI(title="Bindung", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/statisch", StaticFiles(directory=str(basis.STATISCH)), name="statisch")


@app.middleware("http")
async def _tuer(request: Request, call_next):
    """Sitzung lesen; wer keine hat, kommt nur auf offene Pfade.

    Die Verbindung gehoert der Anfrage: hier geoeffnet, am Ende geschlossen.
    Statische Dateien fassen die Datenbank nicht an.
    """
    pfad = request.url.path
    if pfad.startswith("/statisch/"):
        return await call_next(request)
    con = db.verbinden()
    try:
        token = request.cookies.get(auth.COOKIE)
        request.state.con = con
        request.state.nutzer = auth.sitzung_pruefen(con, token)
        if request.state.nutzer is None and not basis.ist_offen(pfad):
            return _zur_anmeldung(request)
        antwort = await call_next(request)
        if request.state.nutzer is not None and not _setzt_cookie(antwort):
            # Die Sitzung wurde in der Datenbank verlaengert; das Cookie folgt.
            antwort.set_cookie(auth.COOKIE, token, **auth.cookie_optionen())
        return antwort
    finally:
        con.close()


def _setzt_cookie(antwort: Response) -> bool:
    return any(h.startswith(f"{auth.COOKIE}=") for h in antwort.headers.getlist("set-cookie"))


def _zur_anmeldung(request: Request) -> Response:
    if request.headers.get("hx-request"):
        return Response(status_code=401, headers={"HX-Redirect": "/anmeldung"})
    return RedirectResponse("/anmeldung", status_code=303)


@app.get("/anmeldung", response_class=HTMLResponse)
def anmeldung_form(request: Request):
    if basis.nutzer(request) is not None:
        return RedirectResponse("/", status_code=303)
    return basis.seite(request, "anmeldung.html")


@app.post("/anmeldung")
def anmeldung(request: Request, name: str = Form(""), passwort: str = Form("")):
    try:
        token = auth.anmelden(basis.con(request), name, passwort)
    except auth.ZuVieleVersuche as sperre:
        return basis.seite(request, "anmeldung.html", status_code=429,
                           meldung=str(sperre), name=name)
    if token is None:
        return basis.seite(request, "anmeldung.html", status_code=401,
                           meldung="Name oder Passwort stimmt nicht.", name=name)
    antwort = RedirectResponse("/", status_code=303)
    antwort.set_cookie(auth.COOKIE, token, **auth.cookie_optionen())
    return antwort


@app.post("/abmelden")
def abmelden(request: Request):
    auth.abmelden(basis.con(request), request.cookies.get(auth.COOKIE))
    antwort = RedirectResponse("/anmeldung", status_code=303)
    antwort.delete_cookie(auth.COOKIE, path="/", httponly=True, samesite="lax",
                          secure=auth.cookie_sicher())
    return antwort


app.include_router(personen.router)
app.include_router(kontakte.router)
