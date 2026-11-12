"""Die Einstellungen (PLAN.md, Abschnitt 4): Passwort, Erinnern, Kalender, Diktat, Darstellung.

Eine Seite, sechs Abschnitte, jeder mit eigenem Formular. Ein Formular schickt per
HTMX nur seine Felder und tauscht nur seinen Abschnitt aus; eine abgelehnte
Eingabe kommt als 422 mit Meldung und den eingegebenen Werten. Ohne HTMX (kein
Skript) antworten dieselben Routen mit der ganzen Seite.

Gespeichert wird mit einem Knopf, nicht beim Verlassen des Feldes: ein halb
getipptes Passwort soll nie abgeschickt werden.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bindung import auth, einstellungen, kalender, push
from bindung.personen import EingabeFehler
from bindung.web import basis
from bindung.web.ansicht import formular_lesen, teil_rendern

router = APIRouter()

ABSCHNITTE = ("passwort", "erinnern", "benachrichtigungen", "kalender", "diktat", "darstellung")


def kontext(request: Request, **abweichend: dict) -> dict:
    """Was Seite und Abschnitte zeichnen; `abweichend` ersetzt Teile eines Abschnitts."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    e = einstellungen.lesen(con, nutzer_id)
    schema, host = basis.aussenadresse(request)
    pfad = kalender.pfad(e["kalender_token"])
    standard = {
        "passwort": {},
        "erinnern": {
            "werte": {name: e[name] for name in (
                "vorgabe_intervall_tage", "vorgabe_vorlauf_tage", "zeitzone",
                "tagesmeldung_zeit")},
            "zonen": einstellungen.zeitzonen(e["zeitzone"]),
        },
        "benachrichtigungen": {"anzahl": push.abos_zaehlen(con, nutzer_id)},
        "kalender": {"webcal": f"webcal://{host}{pfad}", "adresse": f"{schema}://{host}{pfad}",
                     "schema": schema},
        "diktat": {"sprache": e["diktat_sprache"], "sprachen": einstellungen.DIKTAT_SPRACHEN},
        "darstellung": {"wert": e["darstellung"], "werte": einstellungen.DARSTELLUNGEN},
    }
    kontext = {f"s_{name}": {**standard[name], **abweichend.get(name, {})} for name in ABSCHNITTE}
    kontext["grenzen"] = {"intervall": (einstellungen.INTERVALL_VON, einstellungen.INTERVALL_BIS),
                          "vorlauf": (einstellungen.VORLAUF_VON, einstellungen.VORLAUF_BIS)}
    return kontext


def abschnitt_antwort(request: Request, abschnitt: str, status: int = 200,
                      **mehr) -> HTMLResponse:
    """Der Abschnitt allein (HTMX) oder die ganze Seite."""
    daten = kontext(request, **{abschnitt: mehr})
    if request.headers.get("hx-request"):
        return HTMLResponse(teil_rendern(f"_einstellung_{abschnitt}.html", daten),
                            status_code=status)
    return basis.seite(request, "einstellungen.html", status_code=status, **daten)


@router.get("/einstellungen/benachrichtigungen", response_class=HTMLResponse)
def benachrichtigungen(request: Request):
    """Der Abschnitt allein, frisch gezaehlt: `bindung.js` holt ihn nach jedem An- und Abmelden."""
    if request.headers.get("hx-request"):
        return abschnitt_antwort(request, "benachrichtigungen")
    return RedirectResponse("/einstellungen", status_code=303)


@router.get("/einstellungen", response_class=HTMLResponse)
def seite(request: Request):
    return basis.seite(request, "einstellungen.html", **kontext(request))


@router.post("/einstellungen/passwort")
def passwort(request: Request, formular: dict = Depends(formular_lesen)):
    if formular.get("neu", "") != formular.get("wiederholung", ""):
        return abschnitt_antwort(request, "passwort", 422,
                        meldung="Die beiden neuen Passwörter sind nicht gleich.")
    try:
        auth.passwort_aendern(basis.con(request), basis.nutzer(request)["id"],
                              formular.get("aktuell", ""), formular.get("neu", ""),
                              request.cookies.get(auth.COOKIE))
    except auth.AuthFehler as fehler:  # auch ZuVieleVersuche
        return abschnitt_antwort(request, "passwort", 422, meldung=str(fehler))
    return abschnitt_antwort(request, "passwort", gespeichert=True)


@router.post("/einstellungen/erinnern")
def erinnern(request: Request, formular: dict = Depends(formular_lesen)):
    felder = ("vorgabe_intervall_tage", "vorgabe_vorlauf_tage", "zeitzone", "tagesmeldung_zeit")
    werte = {name: formular.get(name, "") for name in felder}
    try:
        einstellungen.erinnern_speichern(basis.con(request), basis.nutzer(request)["id"], **werte)
    except EingabeFehler as fehler:
        return abschnitt_antwort(request, "erinnern", 422, meldung=str(fehler), werte=werte)
    return abschnitt_antwort(request, "erinnern", gespeichert=True)


@router.post("/einstellungen/kalender/neu")
def kalender_neu(request: Request):
    kalender.token_erneuern(basis.con(request), basis.nutzer(request)["id"])
    return abschnitt_antwort(request, "kalender", neu=True)


@router.post("/einstellungen/diktat")
def diktat(request: Request, formular: dict = Depends(formular_lesen)):
    try:
        einstellungen.diktat_speichern(basis.con(request), basis.nutzer(request)["id"],
                                       formular.get("diktat_sprache", ""))
    except EingabeFehler as fehler:
        return abschnitt_antwort(request, "diktat", 422, meldung=str(fehler))
    return abschnitt_antwort(request, "diktat", gespeichert=True)


@router.post("/einstellungen/darstellung")
def darstellung(request: Request, formular: dict = Depends(formular_lesen)):
    try:
        wert = einstellungen.darstellung_speichern(
            basis.con(request), basis.nutzer(request)["id"], formular.get("darstellung", ""))
    except EingabeFehler as fehler:
        return abschnitt_antwort(request, "darstellung", 422, meldung=str(fehler))
    if not request.headers.get("hx-request"):
        # Ohne HTMX: die Seite neu laden, damit sie mit der neuen Darstellung gezeichnet wird.
        return RedirectResponse("/einstellungen", status_code=303)
    antwort = abschnitt_antwort(request, "darstellung", gespeichert=True, wert=wert)
    # bindung.js tauscht `data-darstellung` auf der offenen Seite aus, ohne Neuladen.
    antwort.headers["HX-Trigger"] = json.dumps({"darstellung": wert})
    return antwort
