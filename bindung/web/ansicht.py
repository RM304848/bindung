"""Die offene Ansicht und das, was alle Routen zum Zeichnen der Spalten brauchen.

Der Zustand der Ansicht steht in der Adresse
(`/?tag=3&karte=erkaltet&suche=anna&person=5`), damit Neuladen und Zurueck-Taste
dasselbe zeigen. Der Server schreibt die Adresse vor: er schickt `HX-Push-Url`
oder `HX-Replace-Url` mit, der Browser baut sie nicht selbst.

Aenderungen (anlegen, speichern, archivieren, Touchpoint eintragen ...) kommen als
POST von der Seite. Welche Ansicht gerade offen ist, steht dann in
`HX-Current-URL`, das HTMX bei jeder Anfrage mitschickt; so bekommt die Antwort
Seitenleiste, Karten und Liste im richtigen Filter, ohne dass jedes Formular den
Filter wiederholt.

Jede Nummer in einer Anfrage wird gegen den angemeldeten Nutzer geprueft. Was
einem anderen gehoert, ist ein 404 -- nie ein 403, das das Dasein verriete.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from bindung import angehoerige, faelligkeit, kontakte, personen, push, stichtage, tagesmeldung
from bindung.web import basis

_FILTER = (personen.FILTER_OHNE_KONTAKT, personen.FILTER_ARCHIV)


# ------------------------------------------------------------------ Ansicht

@dataclass(frozen=True)
class Ansicht:
    """Was gerade offen ist: Liste (Tag oder Filter), Karte, Suche, Person."""

    tag: int | None = None
    filter: str | None = None
    karte: str | None = None
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
        filtername = filtername if filtername in _FILTER else None
        karte = parameter.get("karte")
        # Im Archiv stehen keine Karten: Archivierte zaehlen auf keiner.
        karte = karte if karte in faelligkeit.KARTEN and filtername != personen.FILTER_ARCHIV \
            else None
        return cls(tag=zahl(parameter.get("tag")), filter=filtername, karte=karte,
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
            ("tag", self.tag), ("filter", self.filter), ("karte", self.karte),
            ("suche", self.suche), ("person", self.person)) if wert not in (None, "")]
        return f"{pfad}?{urlencode(parameter)}" if parameter else pfad

    @property
    def spalte(self) -> str:
        """Welche Spalte auf dem Telefon zuerst offen ist."""
        if self.person is not None:
            return "person"
        if self.tag is not None or self.filter or self.karte or self.suche:
            return "liste"
        return "seitenleiste"


def gepruefte_ansicht(request: Request, ansicht: Ansicht, *, streng: bool) -> Ansicht:
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


def aktuelle_ansicht(request: Request) -> Ansicht:
    return gepruefte_ansicht(request, Ansicht.von_seite(request), streng=False)


def person_oder_404(request: Request, person_id: int):
    zeile = personen.laden(basis.con(request), basis.nutzer(request)["id"], person_id)
    if zeile is None:
        raise HTTPException(404)
    return zeile


# ------------------------------------------------------------------ Teile

@dataclass(frozen=True)
class Zeile:
    """Eine Person in der Liste, mit allem Gerechneten."""

    person: object
    bindung: faelligkeit.Bindung | None
    plakette: faelligkeit.Plakette | None
    notiz: str
    #: Der naechste Stichtag im Vorlauf: die zweite Plakette der Zeile.
    stichtag: stichtage.Vorkommen | None = None


def stichtag_personen(con, nutzer_id: int, heute: dt.date) -> set[int]:
    """Personen mit einem Stichtag im Vorlauf -- sie stehen auf der Karte „Diese Woche“.

    Ein Stichtag aendert den Zustand der Person nicht (PLAN.md, Abschnitt 6);
    `faelligkeit.karten_nummern` stellt sie nur zusaetzlich auf die Karte.
    """
    return {v.person_id for v in stichtage.im_vorlauf(con, nutzer_id, heute)}


def _zeilen(con, nutzer_id: int, ansicht: Ansicht, bindungen: dict,
            karten: dict[str, set[int]], vorlauf: dict[int, stichtage.Vorkommen]) -> list[Zeile]:
    heute = personen.heute(con, nutzer_id)
    archiv = ansicht.filter == personen.FILTER_ARCHIV
    gefunden = personen.liste(
        con, nutzer_id, tag_id=ansicht.tag, suche=ansicht.suche,
        ohne_kontakt=ansicht.filter == personen.FILTER_OHNE_KONTAKT, archiviert=archiv)
    if ansicht.karte:
        gefunden = sorted(
            (p for p in gefunden if p["id"] in karten[ansicht.karte]),
            key=lambda p: faelligkeit.sortierschluessel(bindungen[p["id"]], p["name"]))
    notizen = kontakte.letzte_notizen(con, nutzer_id)
    mit_kontakt = kontakte.mit_echtem_kontakt(con, nutzer_id)
    zeilen = []
    for person in gefunden:
        bindung = None if archiv else bindungen.get(person["id"])
        zeilen.append(Zeile(
            person, bindung, faelligkeit.plakette(bindung, heute) if bindung else None,
            # Was zuletzt besprochen wurde; die Profilnotiz nur, wo es noch keinen echten
            # Kontakt gibt (eine Schaetzung hat nie eine Notiz).
            notizen.get(person["id"], "") if person["id"] in mit_kontakt
            else (person["profilnotiz"] or ""),
            None if archiv else vorlauf.get(person["id"])))
    return zeilen


def kontext_bauen(request: Request, ansicht: Ansicht) -> dict:
    """Alles, was Seitenleiste, Karten und Liste zum Zeichnen brauchen."""
    con, nutzer = basis.con(request), basis.nutzer(request)
    nutzer_id = nutzer["id"]
    heute = personen.heute(con, nutzer_id)
    tag = personen.tag_laden(con, nutzer_id, ansicht.tag) if ansicht.tag is not None else None
    titel = {personen.FILTER_OHNE_KONTAKT: "Noch kein Touchpoint",
             personen.FILTER_ARCHIV: "Archiv"}.get(ansicht.filter or "")
    bindungen = faelligkeit.bindungen(con, nutzer_id, heute)
    vorlauf = stichtage.je_person(stichtage.im_vorlauf(con, nutzer_id, heute))
    karten = faelligkeit.karten_nummern(bindungen, set(vorlauf))
    return {
        "nutzer": nutzer,
        "ansicht": ansicht,
        "neue_ansicht": Ansicht,
        "heute": heute,
        "zaehler": personen.zaehler(con, nutzer_id),
        "tags": personen.tags_mit_zaehlern(con, nutzer_id),
        "tag": tag,
        "titel": titel or (tag["name"] if tag else "Alle"),
        "karten": {name: len(nummern) for name, nummern in karten.items()},
        "zeilen": _zeilen(con, nutzer_id, ansicht, bindungen, karten, vorlauf),
    }


def hinweis_bauen(request: Request) -> dict | None:
    """Der Hinweis (die Tagesmeldung als Streifen) fuer die Startseite, oder `None`.

    Hat der Nutzer irgendwo ein Push-Abo, ist der Streifen zunaechst versteckt: ob *dieser*
    Browser Push hat, weiss nur der Browser, und `bindung.js` zeigt den Streifen, wenn nicht.
    Ohne jedes Abo ist er sofort da.
    """
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    meldung = tagesmeldung.hinweis(con, nutzer_id, personen.heute(con, nutzer_id))
    if meldung is None:
        return None
    return {"meldung": meldung, "versteckt": push.abos_zaehlen(con, nutzer_id) > 0}


def teil_rendern(name: str, kontext: dict, **mehr) -> str:
    return basis.TEMPLATES.get_template(name).render(**{**kontext, **mehr})


def person_daten(request: Request, person) -> dict:
    """Was die Personenseite ueber die Liste hinaus braucht: Bindung, Zuletzt besprochen, Tags."""
    con, nutzer_id = basis.con(request), basis.nutzer(request)["id"]
    heute = personen.heute(con, nutzer_id)
    bindung = faelligkeit.bindungen(con, nutzer_id, heute, person_id=person["id"])[person["id"]]
    familie = angehoerige.liste(con, nutzer_id, person["id"])
    return {
        "person": person,
        "bindung": bindung,
        "plakette": faelligkeit.plakette(bindung, heute),
        "verlauf": kontakte.liste(con, nutzer_id, person["id"]),
        "heute": heute,
        "arten": kontakte.ARTEN,
        "art_namen": kontakte.ART_NAMEN,
        "gewaehlt": personen.tags_der_person(con, nutzer_id, person["id"]),
        "angehoerige": familie,
        # „Verknüpfen“ öffnet mit dem Namen des Angehörigen in der Suche und den Treffern dazu.
        "vorschlaege": {a["id"]: angehoerige.verknuepfbare(con, nutzer_id, person["id"], a["name"])
                        for a in familie if not a["verknuepfte_person_id"]},
        "rollen": angehoerige.ROLLEN,
        "stichtage": stichtage.liste(con, nutzer_id, person["id"], heute),
        "stichtag_arten": stichtage.ARTEN,
        "monate": stichtage.MONATE,
    }


def spalte_bauen(request: Request, kontext: dict, modus: str, person=None, **mehr) -> str:
    """Die Personenseite: leer, eine Person, das Formular `neu` oder `mehrere`."""
    if person is not None:
        for name, wert in person_daten(request, person).items():
            if name != "person":
                mehr.setdefault(name, wert)
    return teil_rendern("_pane.html", kontext, modus=modus, person=person, **mehr)


def faelligkeit_teil(request: Request, kontext: dict, person) -> str:
    """Zustand, letzter Kontakt und Faellig am der Person -- nach jeder Aenderung neu."""
    daten = person_daten(request, person)
    return teil_rendern("_faelligkeit.html", kontext, **daten, oob_faelligkeit=True)


def familie_teile(request: Request, kontext: dict, person, *, haupt: str, **mehr) -> list[str]:
    """Angehoerige und Stichtage der Person, neu gezeichnet.

    Beide haengen aneinander (der Geburtstag eines Angehoerigen ist ein Stichtag),
    deshalb kommen sie immer zusammen. `haupt` (`angehoerige` oder `stichtage`)
    ist der Teil, der ins Ziel der Anfrage geht; der andere tauscht sich per
    `hx-swap-oob`. `mehr` (Meldung, Formularwerte) geht nur an den Hauptteil.
    """
    daten = person_daten(request, person)
    teile = []
    # Der Hauptteil zuerst: HTMX tauscht den ersten Teil ins Ziel, die uebrigen per oob.
    for name in sorted(("angehoerige", "stichtage"), key=lambda n: n != haupt):
        oob = {f"oob_{name}": name != haupt}
        teile.append(teil_rendern(f"_{name}.html", kontext, **daten, **oob,
                                  **(mehr if name == haupt else {})))
    return teile


def aktualisierung(kontext: dict, *, seitenleiste: bool = True, liste: bool = True) -> list[str]:
    """Die Teile, die HTMX ausserhalb des Hauptziels tauscht."""
    teile = []
    if seitenleiste:
        teile.append(teil_rendern("_seitenleiste.html", kontext, oob_seitenleiste=True))
    if liste:
        teile.append(teil_rendern("_karten.html", kontext, oob_karten=True))
        teile.append(teil_rendern("_listenkoerper.html", kontext, oob_listenkoerper=True))
    return teile


def antwort(teile: list[str], *, status: int = 200, push: str | None = None,
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


def fehler_in_spalte(request: Request, kontext: dict, person, meldung: str) -> HTMLResponse:
    """Eine abgelehnte Eingabe an der offenen Person: die Seite neu, mit Meldung."""
    return antwort(
        [spalte_bauen(request, kontext, "person", person, meldung=meldung)], status=422,
        kopf={"HX-Retarget": "#personenseite", "HX-Reswap": "outerHTML"})


def meldung_antwort(text: str, ziel: str) -> HTMLResponse:
    """Eine Fehlermeldung in einen festen Platz (`ziel`, eine Kennung) der Seite."""
    teil = f'<p class="meldung meldung-fehler" role="alert">{html_maskiert(text)}</p>'
    return antwort([teil], status=422,
                   kopf={"HX-Retarget": f"#{ziel}", "HX-Reswap": "innerHTML"})


def html_maskiert(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def nur_htmx(request: Request, ziel: str) -> Response | None:
    """Teile gibt es nur fuer HTMX; wer die Adresse direkt oeffnet, kommt auf die Seite."""
    if request.headers.get("hx-request"):
        return None
    return RedirectResponse(ziel, status_code=303)


async def formular_lesen(request: Request) -> dict[str, str]:
    """Die Felder des Formulars, wie sie kamen -- auch die leeren.

    FastAPI macht aus einem leeren Formularwert bei einem optionalen Parameter
    `None`; dann liesse sich ein Feld nicht mehr leeren.
    """
    return {name: wert for name, wert in (await request.form()).items()
            if isinstance(wert, str)}
