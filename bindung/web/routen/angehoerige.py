"""Angehoerige auf der Personenseite (PLAN.md, Abschnitte 5 und 7).

Ein Abschnitt unter „Zuletzt besprochen“: Eintraege mit Name, Rolle und
Geburtstag, einfach oder mit einer Person in der App verknuepft. Jede
Aenderung zeichnet beide Abschnitte (der Geburtstag ist auch ein Stichtag) neu
und zieht Zeile, Karten und Seitenleiste per `hx-swap-oob` nach.

Die Auswahl beim Verknuepfen ist eine Suche ueber die aktiven Personen des
Nutzers (`GET /personen/<id>/kandidaten`). Jede Nummer gehoert dem angemeldeten
Nutzer, sonst 404.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from bindung import angehoerige, personen, stichtage
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

#: Die Kennung des Ziels der Auswahl: „neu“ oder die Nummer des Eintrags.
_ZIEL = re.compile(r"^[a-z0-9]{1,12}$")


def _eintrag_oder_404(request: Request, angehoeriger_id: int):
    zeile = angehoerige.laden(basis.con(request), basis.nutzer(request)["id"], angehoeriger_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


def _werte_aus_formular(formular: dict) -> dict[str, str]:
    return {name: formular.get(name, "") for name in
            ("name", "rolle", "rolle_text", "tag", "monat", "jahr")}


def werte_aus_eintrag(zeile) -> dict[str, str]:
    """Die Felder des Formulars zu einem gespeicherten Eintrag."""
    tag = monat = jahr = ""
    if zeile["geburtstag"]:
        t, m, j = stichtage.teile(zeile["geburtstag"])
        tag, monat, jahr = str(t), str(m), str(j or "")
    return {"name": zeile["name"], "rolle": zeile["rolle"], "rolle_text": zeile["rolle_text"] or "",
            "tag": tag, "monat": monat, "jahr": jahr}


def _geburtstag(formular: dict, heute) -> str | None:
    return stichtage.bauen_oder_none(formular.get("tag"), formular.get("monat"),
                                     formular.get("jahr"), heute)


def _nummer(wert: str | None, meldung: str) -> int | None:
    text = (wert or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise personen.EingabeFehler(meldung) from None


def _abschnitt(request: Request, person_id: int, *, status: int = 200,
               **mehr) -> HTMLResponse:
    """Beide Abschnitte der Person neu, dazu Zeile, Karten und Seitenleiste."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    person = personen.laden(con, nutzer_id, person_id)
    kontext = kontext_bauen(request, aktuelle_ansicht(request).mit(person=person_id))
    teile = [*familie_teile(request, kontext, person, haupt="angehoerige", **mehr),
             *aktualisierung(kontext)]
    # Eine abgelehnte Eingabe bleibt im Abschnitt, auch wenn ein einzelner Eintrag sie schickte.
    kopf = {"HX-Retarget": "#angehoerige", "HX-Reswap": "outerHTML"} if status != 200 else None
    return antwort(teile, status=status, kopf=kopf)


def _eintrag_antwort(request: Request, zeile, vorlage: str, **mehr) -> HTMLResponse:
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    person = personen.laden(con, nutzer_id, zeile["person_id"])
    kontext = kontext_bauen(request, aktuelle_ansicht(request).mit(person=person["id"]))
    daten = person_daten(request, person)
    return antwort([teil_rendern(vorlage, kontext, **{**daten, "a": zeile, **mehr})])


# ------------------------------------------------------------------ Auswahl

@router.get("/personen/{person_id}/kandidaten")
def kandidaten(request: Request, person_id: int, ziel: str = "neu", suche: str = ""):
    """Die Treffer der Suche im Auswahlfeld „In der App“."""
    person_oder_404(request, person_id)
    if not _ZIEL.match(ziel):
        raise HTTPException(404)
    if (umleitung := nur_htmx(request, f"/?person={person_id}")):
        return umleitung
    treffer, mehr = angehoerige.verknuepfbare(
        basis.con(request), basis.nutzer(request)["id"], person_id, suche)
    kontext = kontext_bauen(request, aktuelle_ansicht(request))
    return antwort([teil_rendern("_kandidaten.html", kontext, ziel=ziel, suche=suche.strip(),
                                 treffer=treffer, mehr=mehr)])


# ------------------------------------------------------------------ Anlegen

@router.post("/personen/{person_id}/angehoerige")
def angehoeriger_anlegen(request: Request, person_id: int,
                         formular: dict = Depends(formular_lesen)):
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        andere = _nummer(formular.get("verknuepfte_person_id"), "Wähle eine Person aus.")
        angehoerige.anlegen(
            con, nutzer_id, person_id, name=formular.get("name"), rolle=formular.get("rolle"),
            rolle_text=formular.get("rolle_text"),
            geburtstag=_geburtstag(formular, personen.heute(con, nutzer_id)),
            verknuepfte_person_id=andere)
    except personen.NichtGefunden:
        raise HTTPException(404) from None
    except personen.EingabeFehler as fehler:
        return _abschnitt(request, person_id, status=422, meldung=str(fehler), neu_offen=True,
                          neu_werte=_werte_aus_formular(formular))
    return _abschnitt(request, person_id)


# ------------------------------------------------------- Bearbeiten, Loeschen

@router.get("/angehoerige/{angehoeriger_id}")
def eintrag_zeigen(request: Request, angehoeriger_id: int):
    """Der Eintrag ohne Formular -- das Ziel von „Abbrechen“."""
    zeile = _eintrag_oder_404(request, angehoeriger_id)
    if (umleitung := nur_htmx(request, f"/?person={zeile['person_id']}")):
        return umleitung
    return _eintrag_antwort(request, zeile, "_angehoeriger.html")


@router.get("/angehoerige/{angehoeriger_id}/bearbeiten")
def eintrag_bearbeiten(request: Request, angehoeriger_id: int):
    zeile = _eintrag_oder_404(request, angehoeriger_id)
    if (umleitung := nur_htmx(request, f"/?person={zeile['person_id']}")):
        return umleitung
    return _eintrag_antwort(request, zeile, "_angehoeriger_form.html",
                            werte=werte_aus_eintrag(zeile))


@router.post("/angehoerige/{angehoeriger_id}")
def eintrag_speichern(request: Request, angehoeriger_id: int,
                      formular: dict = Depends(formular_lesen)):
    zeile = _eintrag_oder_404(request, angehoeriger_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        angehoerige.aendern(
            con, nutzer_id, angehoeriger_id, name=formular.get("name"),
            rolle=formular.get("rolle"), rolle_text=formular.get("rolle_text"),
            geburtstag=_geburtstag(formular, personen.heute(con, nutzer_id)))
    except personen.EingabeFehler as fehler:
        antwort_ = _eintrag_antwort(request, zeile, "_angehoeriger_form.html",
                                    werte=_werte_aus_formular(formular), meldung=str(fehler))
        antwort_.status_code = 422
        antwort_.headers["HX-Retarget"] = f"#angehoeriger-{angehoeriger_id}"
        antwort_.headers["HX-Reswap"] = "outerHTML"
        return antwort_
    return _abschnitt(request, zeile["person_id"])


@router.post("/angehoerige/{angehoeriger_id}/loeschen")
def eintrag_loeschen(request: Request, angehoeriger_id: int):
    _eintrag_oder_404(request, angehoeriger_id)
    person_id = angehoerige.loeschen(basis.con(request), basis.nutzer(request)["id"],
                                     angehoeriger_id)
    return _abschnitt(request, person_id)


# --------------------------------------------------------------- Verknuepfung

@router.post("/angehoerige/{angehoeriger_id}/verknuepfen")
def eintrag_verknuepfen(request: Request, angehoeriger_id: int,
                        formular: dict = Depends(formular_lesen)):
    zeile = _eintrag_oder_404(request, angehoeriger_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        andere = _nummer(formular.get("verknuepfte_person_id"), "Wähle eine Person aus.")
        if andere is None:
            raise personen.EingabeFehler("Wähle eine Person aus der Liste.")
        angehoerige.verknuepfen(con, nutzer_id, angehoeriger_id, andere)
    except personen.NichtGefunden:
        raise HTTPException(404) from None
    except personen.EingabeFehler as fehler:
        return _abschnitt(request, zeile["person_id"], status=422, meldung=str(fehler))
    return _abschnitt(request, zeile["person_id"])


@router.post("/angehoerige/{angehoeriger_id}/entknuepfen")
def eintrag_entknuepfen(request: Request, angehoeriger_id: int):
    zeile = _eintrag_oder_404(request, angehoeriger_id)
    try:
        angehoerige.entknuepfen(basis.con(request), basis.nutzer(request)["id"], angehoeriger_id)
    except personen.EingabeFehler as fehler:
        return _abschnitt(request, zeile["person_id"], status=422, meldung=str(fehler))
    return _abschnitt(request, zeile["person_id"])
