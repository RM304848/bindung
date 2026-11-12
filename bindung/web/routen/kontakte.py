"""Touchpoint eintragen und Zuletzt besprochen (PLAN.md, Abschnitte 6 und 7).

Das Blatt „Touchpoint eintragen“ liegt ueber der Personenseite; der Kreis in der
Liste oeffnet es fuer diese Person (und waehlt sie dabei aus), der Knopf auf
der Personenseite fuer die offene. Speichern tauscht die Personenseite und
zieht Zeile, Zaehler der Seitenleiste und Karten per `hx-swap-oob` nach.

Eintraege von „Zuletzt besprochen“ werden an Ort und Stelle bearbeitet; nach
jeder Aenderung (Datum, Art, Loeschen) stimmt der Zustand der Person nicht mehr,
deshalb kommen Faelligkeit, Liste, Karten und Seitenleiste immer mit.

Jede Nummer gehoert dem angemeldeten Nutzer, sonst 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from bindung import kontakte, personen
from bindung.web import basis
from bindung.web.ansicht import (
    aktualisierung,
    aktuelle_ansicht,
    antwort,
    faelligkeit_teil,
    formular_lesen,
    kontext_bauen,
    nur_htmx,
    person_daten,
    person_oder_404,
    spalte_bauen,
    teil_rendern,
)

router = APIRouter()

#: Was das Blatt vorbelegt, wenn nichts anderes im Formular stand.
VORGABE_ART = "anruf"


def _kontakt_oder_404(request: Request, kontakt_id: int):
    zeile = kontakte.laden(basis.con(request), basis.nutzer(request)["id"], kontakt_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


def _blatt_antwort(request: Request, person_id: int, *, werte: dict | None = None,
                   meldung: str | None = None, status: int = 200) -> HTMLResponse:
    """Die Personenseite mit offenem Blatt; die Person wird dabei die ausgewaehlte."""
    person = person_oder_404(request, person_id)
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    heute = personen.heute(basis.con(request), basis.nutzer(request)["id"])
    werte = werte or {"art": VORGABE_ART, "datum": heute.isoformat(), "notiz": ""}
    teile = [spalte_bauen(request, kontext, "person", person, blatt=True, kontakt_werte=werte,
                          blatt_meldung=meldung),
             *aktualisierung(kontext, seitenleiste=False)]
    if status != 200:
        return antwort(teile, status=status)
    return antwort(teile, push=ansicht.url(), spalte="person")


@router.get("/personen/{person_id}/kontakt/neu")
def blatt_oeffnen(request: Request, person_id: int):
    person_oder_404(request, person_id)
    if (umleitung := nur_htmx(request, f"/?person={person_id}")):
        return umleitung
    return _blatt_antwort(request, person_id)


@router.post("/personen/{person_id}/kontakte")
def kontakt_eintragen(request: Request, person_id: int,
                      formular: dict = Depends(formular_lesen)):
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        kontakte.eintragen(con, nutzer_id, person_id, datum=formular.get("datum", ""),
                           art=formular.get("art", ""), notiz=formular.get("notiz"))
    except personen.EingabeFehler as fehler:
        return _blatt_antwort(
            request, person_id, status=422, meldung=str(fehler),
            werte={"art": formular.get("art", VORGABE_ART), "datum": formular.get("datum", ""),
                   "notiz": formular.get("notiz", "")})
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    return antwort([spalte_bauen(request, kontext, "person", person), *aktualisierung(kontext)],
                   ersetzen=ansicht.url(), spalte="person")


# ---------------------------------------------------- Zuletzt besprochen

def _eintrag_teil(request: Request, kontext: dict, vorlage: str, kontakt, **mehr) -> str:
    person = personen.laden(basis.con(request), basis.nutzer(request)["id"],
                            kontakt["person_id"])
    daten = person_daten(request, person)
    return teil_rendern(vorlage, kontext, **{**daten, "k": kontakt, **mehr})


def _kontext_zu(request: Request, kontakt) -> dict:
    ansicht = aktuelle_ansicht(request).mit(person=kontakt["person_id"])
    return kontext_bauen(request, ansicht)


@router.get("/kontakte/{kontakt_id}")
def eintrag_zeigen(request: Request, kontakt_id: int):
    """Der Eintrag ohne Formular -- das Ziel von „Abbrechen“."""
    kontakt = _kontakt_oder_404(request, kontakt_id)
    if (umleitung := nur_htmx(request, f"/?person={kontakt['person_id']}")):
        return umleitung
    return antwort([_eintrag_teil(request, _kontext_zu(request, kontakt),
                                  "_kontakt_eintrag.html", kontakt)])


@router.get("/kontakte/{kontakt_id}/bearbeiten")
def eintrag_bearbeiten(request: Request, kontakt_id: int):
    kontakt = _kontakt_oder_404(request, kontakt_id)
    if (umleitung := nur_htmx(request, f"/?person={kontakt['person_id']}")):
        return umleitung
    werte = {"datum": kontakt["datum"], "art": kontakt["art"], "notiz": kontakt["notiz"] or ""}
    return antwort([_eintrag_teil(request, _kontext_zu(request, kontakt),
                                  "_kontakt_eintrag_form.html", kontakt, werte=werte)])


def _verlauf_antwort(request: Request, person_id: int) -> HTMLResponse:
    """„Zuletzt besprochen“ neu, dazu alles, was vom Zustand der Person abhaengt."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    person = personen.laden(con, nutzer_id, person_id)
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    daten = person_daten(request, person)
    return antwort([teil_rendern("_verlauf.html", kontext, **daten),
                    faelligkeit_teil(request, kontext, person),
                    *aktualisierung(kontext)])


@router.post("/kontakte/{kontakt_id}")
def eintrag_speichern(request: Request, kontakt_id: int,
                      formular: dict = Depends(formular_lesen)):
    kontakt = _kontakt_oder_404(request, kontakt_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    felder = {name: formular[name] for name in kontakte.FELDER if name in formular}
    try:
        kontakte.aendern(con, nutzer_id, kontakt_id, **felder)
    except personen.EingabeFehler as fehler:
        werte = {"datum": formular.get("datum", kontakt["datum"]),
                 "art": formular.get("art", kontakt["art"]),
                 "notiz": formular.get("notiz", kontakt["notiz"] or "")}
        return antwort(
            [_eintrag_teil(request, _kontext_zu(request, kontakt), "_kontakt_eintrag_form.html",
                           kontakt, werte=werte, meldung=str(fehler))],
            status=422, kopf={"HX-Retarget": f"#kontakt-{kontakt_id}",
                              "HX-Reswap": "outerHTML"})
    return _verlauf_antwort(request, kontakt["person_id"])


@router.post("/kontakte/{kontakt_id}/loeschen")
def eintrag_loeschen(request: Request, kontakt_id: int):
    _kontakt_oder_404(request, kontakt_id)
    person_id = kontakte.loeschen(basis.con(request), basis.nutzer(request)["id"], kontakt_id)
    return _verlauf_antwort(request, person_id)
