"""Stichtage auf der Personenseite (PLAN.md, Abschnitte 6 und 7).

Ein Abschnitt unter „Angehörige“: Bezeichnung, Datum (mit oder ohne Jahr), das
naechste Mal, Vorlauf, wenn er vom Vorgabewert abweicht. Der Geburtstag eines
Angehoerigen steht dort auch, wird aber am Angehoerigen bearbeitet.

Jede Aenderung zeichnet beide Abschnitte neu und zieht Zeile (mit der zweiten
Plakette), Karten und Seitenleiste per `hx-swap-oob` nach: ein Stichtag im
Vorlauf stellt die Person auf „Diese Woche“. Jede Nummer gehoert dem
angemeldeten Nutzer, sonst 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from bindung import personen, stichtage
from bindung.web import basis
from bindung.web.ansicht import (
    aktualisierung,
    aktuelle_ansicht,
    antwort,
    familie_teile,
    formular_lesen,
    kontext_bauen,
    nur_htmx,
    person_daten,
    person_oder_404,
    teil_rendern,
)

router = APIRouter()

#: Was das Formular „Stichtag hinzufügen“ vorbelegt.
VORGABE_ART = "geburtstag"


def _stichtag_oder_404(request: Request, stichtag_id: int):
    zeile = stichtage.laden(basis.con(request), basis.nutzer(request)["id"], stichtag_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


def _werte_aus_formular(formular: dict) -> dict[str, str]:
    return {name: formular.get(name, "") for name in
            ("bezeichnung", "art", "tag", "monat", "jahr", "vorlauf_tage")}


def _werte_aus_stichtag(zeile) -> dict[str, str]:
    tag, monat, jahr = stichtage.teile(zeile["datum"])
    return {"bezeichnung": zeile["bezeichnung"], "art": zeile["art"], "tag": str(tag),
            "monat": str(monat), "jahr": str(jahr or ""),
            "vorlauf_tage": "" if zeile["vorlauf_tage"] is None else str(zeile["vorlauf_tage"])}


def _datum(formular: dict, heute) -> str:
    return stichtage.bauen(formular.get("tag"), formular.get("monat"), formular.get("jahr"),
                           heute)


def _abschnitt(request: Request, person_id: int, *, status: int = 200,
               **mehr) -> HTMLResponse:
    """Beide Abschnitte der Person neu, dazu Zeile, Karten und Seitenleiste."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    person = personen.laden(con, nutzer_id, person_id)
    kontext = kontext_bauen(request, aktuelle_ansicht(request).mit(person=person_id))
    teile = [*familie_teile(request, kontext, person, haupt="stichtage", **mehr),
             *aktualisierung(kontext)]
    kopf = {"HX-Retarget": "#stichtage", "HX-Reswap": "outerHTML"} if status != 200 else None
    return antwort(teile, status=status, kopf=kopf)


def _eintrag_antwort(request: Request, zeile, vorlage: str, **mehr) -> HTMLResponse:
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    person = personen.laden(con, nutzer_id, zeile["person_id"])
    kontext = kontext_bauen(request, aktuelle_ansicht(request).mit(person=person["id"]))
    daten = person_daten(request, person)
    vorkommen = stichtage.vorkommen_von(con, nutzer_id, zeile["id"], daten["heute"])
    return antwort([teil_rendern(vorlage, kontext, **{**daten, "s": vorkommen, **mehr})])


@router.post("/personen/{person_id}/stichtage")
def stichtag_anlegen(request: Request, person_id: int, formular: dict = Depends(formular_lesen)):
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        stichtage.anlegen(con, nutzer_id, person_id, bezeichnung=formular.get("bezeichnung"),
                          art=formular.get("art"),
                          datum=_datum(formular, personen.heute(con, nutzer_id)),
                          vorlauf_tage=formular.get("vorlauf_tage"))
    except personen.EingabeFehler as fehler:
        return _abschnitt(request, person_id, status=422, meldung=str(fehler), neu_offen=True,
                          neu_werte=_werte_aus_formular(formular))
    return _abschnitt(request, person_id)


@router.get("/stichtage/{stichtag_id}")
def eintrag_zeigen(request: Request, stichtag_id: int):
    """Der Eintrag ohne Formular -- das Ziel von „Abbrechen“."""
    zeile = _stichtag_oder_404(request, stichtag_id)
    if (umleitung := nur_htmx(request, f"/?person={zeile['person_id']}")):
        return umleitung
    return _eintrag_antwort(request, zeile, "_stichtag.html")


@router.get("/stichtage/{stichtag_id}/bearbeiten")
def eintrag_bearbeiten(request: Request, stichtag_id: int):
    zeile = _stichtag_oder_404(request, stichtag_id)
    if (umleitung := nur_htmx(request, f"/?person={zeile['person_id']}")):
        return umleitung
    if zeile["angehoeriger_id"] is not None:
        # Der Geburtstag eines Angehoerigen wird dort bearbeitet.
        return _eintrag_antwort(request, zeile, "_stichtag.html")
    return _eintrag_antwort(request, zeile, "_stichtag_form.html",
                            werte=_werte_aus_stichtag(zeile))


@router.post("/stichtage/{stichtag_id}")
def eintrag_speichern(request: Request, stichtag_id: int,
                      formular: dict = Depends(formular_lesen)):
    zeile = _stichtag_oder_404(request, stichtag_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        stichtage.aendern(con, nutzer_id, stichtag_id, bezeichnung=formular.get("bezeichnung"),
                          art=formular.get("art"),
                          datum=_datum(formular, personen.heute(con, nutzer_id)),
                          vorlauf_tage=formular.get("vorlauf_tage"))
    except personen.EingabeFehler as fehler:
        antwort_ = _eintrag_antwort(request, zeile, "_stichtag_form.html",
                                    werte=_werte_aus_formular(formular), meldung=str(fehler))
        antwort_.status_code = 422
        antwort_.headers["HX-Retarget"] = f"#stichtag-{stichtag_id}"
        antwort_.headers["HX-Reswap"] = "outerHTML"
        return antwort_
    return _abschnitt(request, zeile["person_id"])


@router.post("/stichtage/{stichtag_id}/loeschen")
def eintrag_loeschen(request: Request, stichtag_id: int):
    zeile = _stichtag_oder_404(request, stichtag_id)
    try:
        person_id = stichtage.loeschen(basis.con(request), basis.nutzer(request)["id"],
                                       stichtag_id)
    except personen.EingabeFehler as fehler:
        return _abschnitt(request, zeile["person_id"], status=422, meldung=str(fehler))
    return _abschnitt(request, person_id)
