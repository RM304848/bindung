"""Seitenleiste, Liste und Personenseite (PLAN.md, Abschnitt 7).

`GET /` liefert die ganze Seite; alle anderen Wege liefern Teile, die HTMX in
die Spalten tauscht. Wie die Ansicht in der Adresse steht und wie die Teile
gebaut werden, steht in `bindung/web/ansicht.py`. Kontakte (eintragen,
Zuletzt besprochen) liegen in `routen/kontakte.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from bindung import personen
from bindung.web import basis
from bindung.web.ansicht import (
    Ansicht,
    aktualisierung,
    aktuelle_ansicht,
    antwort,
    faelligkeit_teil,
    fehler_in_spalte,
    formular_lesen,
    gepruefte_ansicht,
    hinweis_bauen,
    kontext_bauen,
    meldung_antwort,
    nur_htmx,
    person_oder_404,
    spalte_bauen,
    teil_rendern,
)

router = APIRouter()


def _tag_oder_404(request: Request, tag_id: int):
    zeile = personen.tag_laden(basis.con(request), basis.nutzer(request)["id"], tag_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


def _tags_der_seite(request: Request, kontext: dict, ansicht: Ansicht) -> list[str]:
    """Die Tag-Auswahl der offenen Person, falls eine offen ist (Tags haben sich geaendert)."""
    if ansicht.person is None:
        return []
    person = personen.laden(basis.con(request), basis.nutzer(request)["id"], ansicht.person)
    if person is None:
        return []
    gewaehlt = personen.tags_der_person(basis.con(request), basis.nutzer(request)["id"],
                                        person["id"])
    return [teil_rendern("_personentags.html", kontext, person=person, gewaehlt=gewaehlt,
                         oob_tags=True)]


def _eigene_tag_ids(request: Request, tag_id: list[int]) -> set[int]:
    """Die gewaehlten Tags; ist einer fremd, 404 -- bevor etwas angelegt wird."""
    gewaehlt = set(tag_id)
    for nummer in gewaehlt:
        _tag_oder_404(request, nummer)
    return gewaehlt


def _tag_ids(tag_id: list[int], neuer_tag: str, request: Request) -> set[int]:
    gewaehlt = _eigene_tag_ids(request, tag_id)
    if neuer_tag.strip():
        gewaehlt.add(personen.tag_finden_oder_anlegen(
            basis.con(request), basis.nutzer(request)["id"], neuer_tag))
    return gewaehlt


# -------------------------------------------------------------------- Seite

@router.get("/")
def start(request: Request):
    ansicht = gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                 streng=True)
    kontext = kontext_bauen(request, ansicht)
    person = (personen.laden(basis.con(request), basis.nutzer(request)["id"], ansicht.person)
              if ansicht.person is not None else None)
    return basis.seite(request, "start.html", **kontext, spalte=ansicht.spalte,
                       hinweis=hinweis_bauen(request),
                       pane=spalte_bauen(request, kontext, "person" if person else "leer", person))


@router.get("/liste")
def liste_oeffnen(request: Request):
    """Ein Eintrag der Seitenleiste: neue Liste, keine Person offen."""
    if (umleitung := nur_htmx(request, "/")):
        return umleitung
    ansicht = gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                 streng=True).mit(person=None)
    kontext = kontext_bauen(request, ansicht)
    teile = [teil_rendern("_liste.html", kontext),
             teil_rendern("_seitenleiste.html", kontext, oob_seitenleiste=True),
             spalte_bauen(request, kontext, "leer", oob_pane=True)]
    return antwort(teile, push=ansicht.url(), spalte="liste")


@router.get("/liste/suche")
def liste_suchen(request: Request):
    """Die Suche tippt: nur die Personen der Liste werden getauscht."""
    if (umleitung := nur_htmx(request, "/")):
        return umleitung
    ansicht = gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                streng=True)
    # Die offene Person steht nicht im Suchformular (sie aendert sich, ohne dass die
    # Suche neu gezeichnet wird), sondern in der Adresse der Seite -- und bleibt dort.
    ansicht = gepruefte_ansicht(
        request, ansicht.mit(person=Ansicht.von_seite(request).person), streng=False)
    return antwort([teil_rendern("_listenkoerper.html", kontext_bauen(request, ansicht))],
                   ersetzen=ansicht.url())


# ------------------------------------------------------------------ Personen

@router.get("/personen/leer")
def person_abwaehlen(request: Request):
    if (umleitung := nur_htmx(request, "/")):
        return umleitung
    ansicht = aktuelle_ansicht(request).mit(person=None)
    kontext = kontext_bauen(request, ansicht)
    teile = [spalte_bauen(request, kontext, "leer"), *aktualisierung(kontext, seitenleiste=False)]
    return antwort(teile, ersetzen=ansicht.url(), spalte="liste")


@router.get("/personen/neu")
def person_formular(request: Request):
    if (umleitung := nur_htmx(request, "/")):
        return umleitung
    ansicht = aktuelle_ansicht(request)
    kontext = kontext_bauen(request, ansicht)
    vorbelegt = {ansicht.tag} if ansicht.tag is not None else set()
    return antwort([spalte_bauen(request, kontext, "neu", gewaehlt=vorbelegt, werte={})],
                    spalte="person")


@router.get("/personen/mehrere")
def mehrere_formular(request: Request):
    if (umleitung := nur_htmx(request, "/")):
        return umleitung
    ansicht = aktuelle_ansicht(request)
    kontext = kontext_bauen(request, ansicht)
    vorbelegt = {ansicht.tag} if ansicht.tag is not None else set()
    return antwort([spalte_bauen(request, kontext, "mehrere", gewaehlt=vorbelegt, werte={})],
                    spalte="person")


@router.post("/personen")
def person_anlegen(request: Request, name: str = Form(""), firma: str = Form(""),
                   rolle: str = Form(""), telefon: str = Form(""), email: str = Form(""),
                   ort: str = Form(""), herkunft: str = Form(""), profilnotiz: str = Form(""),
                   tag_id: list[int] = Form([]), neuer_tag: str = Form("")):
    ansicht = aktuelle_ansicht(request)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    _eigene_tag_ids(request, tag_id)
    werte = {"name": name, "firma": firma, "rolle": rolle, "telefon": telefon, "email": email,
             "ort": ort, "herkunft": herkunft, "profilnotiz": profilnotiz,
             "neuer_tag": neuer_tag}
    try:
        person_id = personen.anlegen(con, nutzer_id, name, firma=firma, rolle=rolle,
                                     telefon=telefon, email=email, ort=ort,
                                     herkunft=herkunft, profilnotiz=profilnotiz)
        personen.tags_setzen(con, nutzer_id, person_id, _tag_ids(tag_id, neuer_tag, request))
    except personen.EingabeFehler as fehler:
        kontext = kontext_bauen(request, ansicht)
        return antwort(
            [spalte_bauen(request, kontext, "neu", gewaehlt=set(tag_id), werte=werte,
                     meldung=str(fehler))], status=422)
    ansicht = ansicht.mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    return antwort([spalte_bauen(request, kontext, "person", person), *aktualisierung(kontext)],
                    push=ansicht.url(), spalte="person")


@router.post("/personen/mehrere")
def mehrere_anlegen(request: Request, namen: str = Form(""), tag_id: list[int] = Form([]),
                    neuer_tag: str = Form(""), letzter_kontakt: str = Form("unbekannt")):
    ansicht = aktuelle_ansicht(request)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    _eigene_tag_ids(request, tag_id)
    try:
        if not namen.strip():
            raise personen.EingabeFehler("Trag mindestens einen Namen ein, einen pro Zeile.")
        ids = personen.mehrere_hinzufuegen(
            con, nutzer_id, namen, tag_ids=_tag_ids(tag_id, neuer_tag, request),
            grober_kontakt=letzter_kontakt)
    except personen.EingabeFehler as fehler:
        kontext = kontext_bauen(request, ansicht)
        werte = {"namen": namen, "neuer_tag": neuer_tag, "letzter_kontakt": letzter_kontakt}
        return antwort(
            [spalte_bauen(request, kontext, "mehrere", gewaehlt=set(tag_id), werte=werte,
                     meldung=str(fehler))], status=422)
    ansicht = ansicht.mit(person=ids[0])
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(con, nutzer_id, ids[0])
    return antwort(
        [spalte_bauen(request, kontext, "person", person, angelegt=len(ids)),
         *aktualisierung(kontext)],
        push=ansicht.url(), spalte="person")


@router.get("/personen/{person_id}")
def person_oeffnen(request: Request, person_id: int):
    person = person_oder_404(request, person_id)
    if (umleitung := nur_htmx(request, Ansicht(person=person_id).url())):
        return umleitung
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    return antwort(
        [spalte_bauen(request, kontext, "person", person),
         *aktualisierung(kontext, seitenleiste=False)],
        push=ansicht.url(), spalte="person")


@router.post("/personen/{person_id}")
def person_speichern(request: Request, person_id: int, formular: dict = Depends(formular_lesen)):
    """Speichert die Felder, die das Formular mitschickt; die uebrigen bleiben."""
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    try:
        personen.aendern(con, nutzer_id, person_id,
                         **{feld: wert for feld, wert in formular.items()
                            if feld in personen.FELDER})
    except personen.EingabeFehler as fehler:
        return fehler_in_spalte(request, kontext, personen.laden(con, nutzer_id, person_id),
                                 str(fehler))
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    return antwort([teil_rendern("_speicherstatus.html", kontext, person=person, oob_status=True),
                    teil_rendern("_kontaktlinks.html", kontext, person=person, oob_links=True),
                    faelligkeit_teil(request, kontext, person),
                    *aktualisierung(kontext, seitenleiste=False)])


@router.post("/personen/{person_id}/archivieren")
def person_archivieren(request: Request, person_id: int):
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    personen.archivieren(con, nutzer_id, person_id)
    return _person_neu_zeigen(request, person_id)


@router.post("/personen/{person_id}/wiederherstellen")
def person_wiederherstellen(request: Request, person_id: int):
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    personen.wiederherstellen(con, nutzer_id, person_id)
    return _person_neu_zeigen(request, person_id)


def _person_neu_zeigen(request: Request, person_id: int) -> HTMLResponse:
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(basis.con(request), basis.nutzer(request)["id"], person_id)
    return antwort([spalte_bauen(request, kontext, "person", person), *aktualisierung(kontext)],
                    ersetzen=ansicht.url())


# ---------------------------------------------------------------------- Tags

@router.post("/personen/{person_id}/tags")
def person_tags_setzen(request: Request, person_id: int, tag_id: list[int] = Form([])):
    """Die Auswahl der Chips: die Person traegt genau diese Tags."""
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tags_setzen(con, nutzer_id, person_id, tag_id)
    except personen.NichtGefunden:
        raise HTTPException(404) from None
    return _tags_antwort(request, person_id)


@router.post("/personen/{person_id}/tags/neu")
def person_tag_neu(request: Request, person_id: int, neuer_tag: str = Form("")):
    """Ein Tag, der noch fehlt, wird angelegt und gleich an die Person gehaengt."""
    person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        tag = personen.tag_finden_oder_anlegen(con, nutzer_id, neuer_tag)
        personen.tags_setzen(con, nutzer_id, person_id,
                             personen.tags_der_person(con, nutzer_id, person_id) | {tag})
    except personen.EingabeFehler as fehler:
        return _tags_antwort(request, person_id, meldung=str(fehler), status=422)
    return _tags_antwort(request, person_id)


def _tags_antwort(request: Request, person_id: int, *, meldung: str | None = None,
                  status: int = 200) -> HTMLResponse:
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    ansicht = aktuelle_ansicht(request).mit(person=person_id)
    kontext = kontext_bauen(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    gewaehlt = personen.tags_der_person(con, nutzer_id, person_id)
    return antwort(
        [teil_rendern("_personentags.html", kontext, person=person, gewaehlt=gewaehlt,
                      meldung=meldung),
         *aktualisierung(kontext)], status=status)


@router.post("/tags")
def tag_anlegen(request: Request, name: str = Form("")):
    """„Tag hinzufügen“ in der Seitenleiste."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tag_anlegen(con, nutzer_id, name)
    except personen.EingabeFehler as fehler:
        return meldung_antwort(str(fehler), "seitenleistenmeldung")
    return _tags_geaendert(request)


@router.post("/tags/{tag_id}")
def tag_umbenennen(request: Request, tag_id: int, name: str = Form("")):
    _tag_oder_404(request, tag_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tag_umbenennen(con, nutzer_id, tag_id, name)
    except personen.EingabeFehler as fehler:
        return meldung_antwort(str(fehler), "listenmeldung")
    return _tags_geaendert(request, titel_tauschen=True)


@router.post("/tags/{tag_id}/loeschen")
def tag_loeschen(request: Request, tag_id: int):
    """Loescht den Tag; die Personen bleiben. Danach zeigt die Seite wieder „Alle“."""
    _tag_oder_404(request, tag_id)
    personen.tag_loeschen(basis.con(request), basis.nutzer(request)["id"], tag_id)
    return Response(status_code=204, headers={"HX-Redirect": "/"})


def _tags_geaendert(request: Request, *, titel_tauschen: bool = False) -> HTMLResponse:
    """Seitenleiste, Liste und die Tag-Auswahl der offenen Person sind veraltet."""
    ansicht = aktuelle_ansicht(request)
    kontext = kontext_bauen(request, ansicht)
    teile = [*aktualisierung(kontext), *_tags_der_seite(request, kontext, ansicht)]
    if titel_tauschen:
        teile.append(teil_rendern("_listentitel.html", kontext, oob_titel=True))
    return antwort(teile)
