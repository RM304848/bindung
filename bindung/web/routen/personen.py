"""Seitenleiste, Liste und Personenseite (PLAN.md, Abschnitt 7).

`GET /` liefert die ganze Seite; alle anderen Wege liefern Teile, die HTMX in
die Spalten tauscht. Der Zustand der Ansicht steht in der Adresse
(`/?tag=3&suche=anna&person=5`), damit Neuladen und Zurueck-Taste dasselbe
zeigen. Der Server schreibt die Adresse vor: er schickt `HX-Push-Url` oder
`HX-Replace-Url` mit, der Browser baut sie nicht selbst.

Aenderungen (anlegen, speichern, archivieren, Tags) kommen als POST von der
Seite. Welche Ansicht gerade offen ist, steht dann in `HX-Current-URL`, das
HTMX bei jeder Anfrage mitschickt; so bekommt die Antwort Seitenleiste und
Liste im richtigen Filter, ohne dass jedes Formular den Filter wiederholt.

Jede Nummer in einer Anfrage wird gegen den angemeldeten Nutzer geprueft. Was
einem anderen gehoert, ist ein 404 -- nie ein 403, das das Dasein verriete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from bindung import personen
from bindung.web import basis

router = APIRouter()

_FILTER = (personen.FILTER_OHNE_KONTAKT, personen.FILTER_ARCHIV)


# ------------------------------------------------------------------ Ansicht

@dataclass(frozen=True)
class Ansicht:
    """Was gerade offen ist: Filter der Liste, Suche, ausgewaehlte Person."""

    tag: int | None = None
    filter: str | None = None
    suche: str = ""
    person: int | None = None

    @classmethod
    def aus_parametern(cls, parameter) -> Ansicht:
        def zahl(wert: str | None) -> int | None:
            try:
                return int(wert) if wert else None
            except ValueError:
                return None

        filtername = parameter.get("filter")
        return cls(tag=zahl(parameter.get("tag")),
                   filter=filtername if filtername in _FILTER else None,
                   suche=(parameter.get("suche") or "").strip(),
                   person=zahl(parameter.get("person")))

    @classmethod
    def von_seite(cls, request: Request) -> Ansicht:
        """Die Ansicht der Seite, von der HTMX die Anfrage geschickt hat."""
        adresse = request.headers.get("hx-current-url", "")
        abfrage = parse_qs(urlparse(adresse).query)
        return cls.aus_parametern({name: werte[0] for name, werte in abfrage.items()})

    def mit(self, **aenderungen) -> Ansicht:
        return replace(self, **aenderungen)

    def url(self, pfad: str = "/") -> str:
        parameter = [(name, wert) for name, wert in (
            ("tag", self.tag), ("filter", self.filter), ("suche", self.suche),
            ("person", self.person)) if wert not in (None, "")]
        return f"{pfad}?{urlencode(parameter)}" if parameter else pfad

    @property
    def spalte(self) -> str:
        """Welche Spalte auf dem Telefon zuerst offen ist."""
        if self.person is not None:
            return "person"
        if self.tag is not None or self.filter or self.suche:
            return "liste"
        return "seitenleiste"


def _gepruefte_ansicht(request: Request, ansicht: Ansicht, *, streng: bool) -> Ansicht:
    """Tag und Person der Ansicht gehoeren dem Nutzer, sonst 404 (`streng`) oder weg."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    if ansicht.tag is not None and personen.tag_laden(con, nutzer_id, ansicht.tag) is None:
        if streng:
            raise HTTPException(404)
        ansicht = ansicht.mit(tag=None)
    if ansicht.person is not None and personen.laden(con, nutzer_id, ansicht.person) is None:
        if streng:
            raise HTTPException(404)
        ansicht = ansicht.mit(person=None)
    return ansicht


def _aktuelle_ansicht(request: Request) -> Ansicht:
    return _gepruefte_ansicht(request, Ansicht.von_seite(request), streng=False)


def _person_oder_404(request: Request, person_id: int):
    zeile = personen.laden(basis.con(request), basis.nutzer(request)["id"], person_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


def _tag_oder_404(request: Request, tag_id: int):
    zeile = personen.tag_laden(basis.con(request), basis.nutzer(request)["id"], tag_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


# ------------------------------------------------------------------ Teile

def _kontext(request: Request, ansicht: Ansicht) -> dict:
    """Alles, was Seitenleiste und Liste zum Zeichnen brauchen."""
    con, nutzer = basis.con(request), basis.nutzer(request)
    nutzer_id = nutzer["id"]
    tag = personen.tag_laden(con, nutzer_id, ansicht.tag) if ansicht.tag is not None else None
    titel = {personen.FILTER_OHNE_KONTAKT: "Noch kein Kontakt",
             personen.FILTER_ARCHIV: "Archiv"}.get(ansicht.filter or "")
    return {
        "nutzer": nutzer,
        "ansicht": ansicht,
        "neue_ansicht": Ansicht,
        "zaehler": personen.zaehler(con, nutzer_id),
        "tags": personen.tags_mit_zaehlern(con, nutzer_id),
        "tag": tag,
        "titel": titel or (tag["name"] if tag else "Alle"),
        "personen": personen.liste(
            con, nutzer_id, tag_id=ansicht.tag, suche=ansicht.suche,
            ohne_kontakt=ansicht.filter == personen.FILTER_OHNE_KONTAKT,
            archiviert=ansicht.filter == personen.FILTER_ARCHIV),
    }


def _teil(name: str, kontext: dict, **mehr) -> str:
    return basis.TEMPLATES.get_template(name).render(**{**kontext, **mehr})


def _spalte(request: Request, kontext: dict, modus: str, person=None, **mehr) -> str:
    """Die Personenseite: leer, eine Person, das Formular `neu` oder `mehrere`."""
    if person is not None:
        mehr.setdefault("gewaehlt", personen.tags_der_person(
            basis.con(request), basis.nutzer(request)["id"], person["id"]))
    return _teil("_pane.html", kontext, modus=modus, person=person, **mehr)


def _aktualisierung(kontext: dict, *, seitenleiste: bool = True, liste: bool = True) -> list[str]:
    """Die Teile, die HTMX ausserhalb des Hauptziels tauscht."""
    teile = []
    if seitenleiste:
        teile.append(_teil("_seitenleiste.html", kontext, oob_seitenleiste=True))
    if liste:
        teile.append(_teil("_listenkoerper.html", kontext, oob_listenkoerper=True))
    return teile


def _tags_der_seite(request: Request, kontext: dict, ansicht: Ansicht) -> list[str]:
    """Die Tag-Auswahl der offenen Person, falls eine offen ist (Tags haben sich geaendert)."""
    if ansicht.person is None:
        return []
    person = personen.laden(basis.con(request), basis.nutzer(request)["id"], ansicht.person)
    if person is None:
        return []
    gewaehlt = personen.tags_der_person(basis.con(request), basis.nutzer(request)["id"],
                                        person["id"])
    return [_teil("_personentags.html", kontext, person=person, gewaehlt=gewaehlt,
                  oob_tags=True)]


def _antwort(teile: list[str], *, status: int = 200, push: str | None = None,
             ersetzen: str | None = None, spalte: str | None = None,
             kopf: dict | None = None) -> HTMLResponse:
    """Die Antwort aus Teilen; `spalte` sagt dem Telefon, welche Spalte nun offen ist."""
    kopfzeilen = dict(kopf or {})
    if push:
        kopfzeilen["HX-Push-Url"] = push
    if ersetzen:
        kopfzeilen["HX-Replace-Url"] = ersetzen
    if spalte:
        kopfzeilen["HX-Trigger"] = json.dumps({"spalte": spalte})
    return HTMLResponse("".join(teile), status_code=status, headers=kopfzeilen)


def _fehler_in_spalte(request: Request, kontext: dict, person, meldung: str) -> HTMLResponse:
    """Eine abgelehnte Eingabe an der offenen Person: die Seite neu, mit Meldung."""
    return _antwort(
        [_spalte(request, kontext, "person", person, meldung=meldung)], status=422,
        kopf={"HX-Retarget": "#personenseite", "HX-Reswap": "outerHTML"})


def _meldung(text: str, ziel: str, kontext: dict | None = None) -> HTMLResponse:
    """Eine Fehlermeldung in einen festen Platz (`ziel`, eine Kennung) der Seite."""
    teil = f'<p class="meldung meldung-fehler" role="alert">{_html_maskiert(text)}</p>'
    return _antwort([teil], status=422,
                    kopf={"HX-Retarget": f"#{ziel}", "HX-Reswap": "innerHTML"})


def _html_maskiert(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _nur_htmx(request: Request, ziel: str) -> Response | None:
    """Teile gibt es nur fuer HTMX; wer die Adresse direkt oeffnet, kommt auf die Seite."""
    if request.headers.get("hx-request"):
        return None
    return RedirectResponse(ziel, status_code=303)


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
    ansicht = _gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                 streng=True)
    kontext = _kontext(request, ansicht)
    person = (personen.laden(basis.con(request), basis.nutzer(request)["id"], ansicht.person)
              if ansicht.person is not None else None)
    return basis.seite(request, "start.html", **kontext, spalte=ansicht.spalte,
                       pane=_spalte(request, kontext, "person" if person else "leer", person))


@router.get("/liste")
def liste_oeffnen(request: Request):
    """Ein Eintrag der Seitenleiste: neue Liste, keine Person offen."""
    if (umleitung := _nur_htmx(request, "/")):
        return umleitung
    ansicht = _gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                 streng=True).mit(person=None)
    kontext = _kontext(request, ansicht)
    teile = [_teil("_liste.html", kontext),
             _teil("_seitenleiste.html", kontext, oob_seitenleiste=True),
             _spalte(request, kontext, "leer", oob_pane=True)]
    return _antwort(teile, push=ansicht.url(), spalte="liste")


@router.get("/liste/suche")
def liste_suchen(request: Request):
    """Die Suche tippt: nur die Personen der Liste werden getauscht."""
    if (umleitung := _nur_htmx(request, "/")):
        return umleitung
    ansicht = _gepruefte_ansicht(request, Ansicht.aus_parametern(request.query_params),
                                 streng=True)
    return _antwort([_teil("_listenkoerper.html", _kontext(request, ansicht))],
                    ersetzen=ansicht.url())


# ------------------------------------------------------------------ Personen

@router.get("/personen/leer")
def person_abwaehlen(request: Request):
    if (umleitung := _nur_htmx(request, "/")):
        return umleitung
    ansicht = _aktuelle_ansicht(request).mit(person=None)
    kontext = _kontext(request, ansicht)
    teile = [_spalte(request, kontext, "leer"), *_aktualisierung(kontext, seitenleiste=False)]
    return _antwort(teile, ersetzen=ansicht.url(), spalte="liste")


@router.get("/personen/neu")
def person_formular(request: Request):
    if (umleitung := _nur_htmx(request, "/")):
        return umleitung
    ansicht = _aktuelle_ansicht(request)
    kontext = _kontext(request, ansicht)
    vorbelegt = {ansicht.tag} if ansicht.tag is not None else set()
    return _antwort([_spalte(request, kontext, "neu", gewaehlt=vorbelegt, werte={})],
                    spalte="person")


@router.get("/personen/mehrere")
def mehrere_formular(request: Request):
    if (umleitung := _nur_htmx(request, "/")):
        return umleitung
    ansicht = _aktuelle_ansicht(request)
    kontext = _kontext(request, ansicht)
    vorbelegt = {ansicht.tag} if ansicht.tag is not None else set()
    return _antwort([_spalte(request, kontext, "mehrere", gewaehlt=vorbelegt, werte={})],
                    spalte="person")


@router.post("/personen")
def person_anlegen(request: Request, name: str = Form(""), firma: str = Form(""),
                   rolle: str = Form(""), telefon: str = Form(""), email: str = Form(""),
                   ort: str = Form(""), herkunft: str = Form(""), profilnotiz: str = Form(""),
                   tag_id: list[int] = Form([]), neuer_tag: str = Form("")):
    ansicht = _aktuelle_ansicht(request)
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
        kontext = _kontext(request, ansicht)
        return _antwort(
            [_spalte(request, kontext, "neu", gewaehlt=set(tag_id), werte=werte,
                     meldung=str(fehler))], status=422)
    ansicht = ansicht.mit(person=person_id)
    kontext = _kontext(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    return _antwort([_spalte(request, kontext, "person", person), *_aktualisierung(kontext)],
                    push=ansicht.url(), spalte="person")


@router.post("/personen/mehrere")
def mehrere_anlegen(request: Request, namen: str = Form(""), tag_id: list[int] = Form([]),
                    neuer_tag: str = Form(""), letzter_kontakt: str = Form("unbekannt")):
    ansicht = _aktuelle_ansicht(request)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    _eigene_tag_ids(request, tag_id)
    try:
        if not namen.strip():
            raise personen.EingabeFehler("Trag mindestens einen Namen ein, einen pro Zeile.")
        ids = personen.mehrere_hinzufuegen(
            con, nutzer_id, namen, tag_ids=_tag_ids(tag_id, neuer_tag, request),
            grober_kontakt=letzter_kontakt)
    except personen.EingabeFehler as fehler:
        kontext = _kontext(request, ansicht)
        werte = {"namen": namen, "neuer_tag": neuer_tag, "letzter_kontakt": letzter_kontakt}
        return _antwort(
            [_spalte(request, kontext, "mehrere", gewaehlt=set(tag_id), werte=werte,
                     meldung=str(fehler))], status=422)
    ansicht = ansicht.mit(person=ids[0])
    kontext = _kontext(request, ansicht)
    person = personen.laden(con, nutzer_id, ids[0])
    return _antwort(
        [_spalte(request, kontext, "person", person, angelegt=len(ids)),
         *_aktualisierung(kontext)],
        push=ansicht.url(), spalte="person")


@router.get("/personen/{person_id}")
def person_oeffnen(request: Request, person_id: int):
    person = _person_oder_404(request, person_id)
    if (umleitung := _nur_htmx(request, Ansicht(person=person_id).url())):
        return umleitung
    ansicht = _aktuelle_ansicht(request).mit(person=person_id)
    kontext = _kontext(request, ansicht)
    return _antwort(
        [_spalte(request, kontext, "person", person),
         *_aktualisierung(kontext, seitenleiste=False)],
        push=ansicht.url(), spalte="person")


async def _formular(request: Request) -> dict[str, str]:
    """Die Felder des Formulars, wie sie kamen -- auch die leeren.

    FastAPI macht aus einem leeren Formularwert bei einem optionalen Parameter
    `None`; dann liesse sich ein Feld nicht mehr leeren.
    """
    return {name: wert for name, wert in (await request.form()).items()
            if isinstance(wert, str)}


@router.post("/personen/{person_id}")
def person_speichern(request: Request, person_id: int, formular: dict = Depends(_formular)):
    """Speichert die Felder, die das Formular mitschickt; die uebrigen bleiben."""
    _person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    ansicht = _aktuelle_ansicht(request).mit(person=person_id)
    kontext = _kontext(request, ansicht)
    try:
        personen.aendern(con, nutzer_id, person_id,
                         **{feld: wert for feld, wert in formular.items()
                            if feld in personen.FELDER})
    except personen.EingabeFehler as fehler:
        return _fehler_in_spalte(request, kontext, personen.laden(con, nutzer_id, person_id),
                                 str(fehler))
    kontext = _kontext(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    return _antwort([_teil("_speicherstatus.html", kontext, person=person, oob_status=True),
                     _teil("_kontaktlinks.html", kontext, person=person, oob_links=True),
                     *_aktualisierung(kontext, seitenleiste=False)])


@router.post("/personen/{person_id}/archivieren")
def person_archivieren(request: Request, person_id: int):
    _person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    personen.archivieren(con, nutzer_id, person_id)
    return _person_neu_zeigen(request, person_id)


@router.post("/personen/{person_id}/wiederherstellen")
def person_wiederherstellen(request: Request, person_id: int):
    _person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    personen.wiederherstellen(con, nutzer_id, person_id)
    return _person_neu_zeigen(request, person_id)


def _person_neu_zeigen(request: Request, person_id: int) -> HTMLResponse:
    ansicht = _aktuelle_ansicht(request).mit(person=person_id)
    kontext = _kontext(request, ansicht)
    person = personen.laden(basis.con(request), basis.nutzer(request)["id"], person_id)
    return _antwort([_spalte(request, kontext, "person", person), *_aktualisierung(kontext)],
                    ersetzen=ansicht.url())


# ---------------------------------------------------------------------- Tags

@router.post("/personen/{person_id}/tags")
def person_tags_setzen(request: Request, person_id: int, tag_id: list[int] = Form([])):
    """Die Auswahl der Chips: die Person traegt genau diese Tags."""
    _person_oder_404(request, person_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tags_setzen(con, nutzer_id, person_id, tag_id)
    except personen.NichtGefunden:
        raise HTTPException(404) from None
    return _tags_antwort(request, person_id)


@router.post("/personen/{person_id}/tags/neu")
def person_tag_neu(request: Request, person_id: int, neuer_tag: str = Form("")):
    """Ein Tag, der noch fehlt, wird angelegt und gleich an die Person gehaengt."""
    _person_oder_404(request, person_id)
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
    ansicht = _aktuelle_ansicht(request).mit(person=person_id)
    kontext = _kontext(request, ansicht)
    person = personen.laden(con, nutzer_id, person_id)
    gewaehlt = personen.tags_der_person(con, nutzer_id, person_id)
    return _antwort(
        [_teil("_personentags.html", kontext, person=person, gewaehlt=gewaehlt, meldung=meldung),
         *_aktualisierung(kontext)], status=status)


@router.post("/tags")
def tag_anlegen(request: Request, name: str = Form("")):
    """„Tag hinzufügen“ in der Seitenleiste."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tag_anlegen(con, nutzer_id, name)
    except personen.EingabeFehler as fehler:
        return _meldung(str(fehler), "seitenleistenmeldung")
    return _tags_geaendert(request)


@router.post("/tags/{tag_id}")
def tag_umbenennen(request: Request, tag_id: int, name: str = Form("")):
    _tag_oder_404(request, tag_id)
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    try:
        personen.tag_umbenennen(con, nutzer_id, tag_id, name)
    except personen.EingabeFehler as fehler:
        return _meldung(str(fehler), "listenmeldung")
    return _tags_geaendert(request, titel_tauschen=True)


@router.post("/tags/{tag_id}/loeschen")
def tag_loeschen(request: Request, tag_id: int):
    """Loescht den Tag; die Personen bleiben. Danach zeigt die Seite wieder „Alle“."""
    _tag_oder_404(request, tag_id)
    personen.tag_loeschen(basis.con(request), basis.nutzer(request)["id"], tag_id)
    return Response(status_code=204, headers={"HX-Redirect": "/"})


def _tags_geaendert(request: Request, *, titel_tauschen: bool = False) -> HTMLResponse:
    """Seitenleiste, Liste und die Tag-Auswahl der offenen Person sind veraltet."""
    ansicht = _aktuelle_ansicht(request)
    kontext = _kontext(request, ansicht)
    teile = [*_aktualisierung(kontext), *_tags_der_seite(request, kontext, ansicht)]
    if titel_tauschen:
        teile.append(_teil("_listentitel.html", kontext, oob_titel=True))
    return _antwort(teile)
