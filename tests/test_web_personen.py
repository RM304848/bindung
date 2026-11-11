"""Seitenleiste, Liste und Personenseite im Browser: Teile, die HTMX tauscht."""

from __future__ import annotations

import json
import re

import pytest

from bindung import auth, personen
from bindung.web.server import app

from .conftest import PASSWORT

HX = {"HX-Request": "true"}


def hx(aktuell: str = "/") -> dict:
    """Kopfzeilen einer HTMX-Anfrage von der Seite `aktuell`."""
    return {"HX-Request": "true", "HX-Current-URL": f"http://testserver{aktuell}"}


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def fremder(con) -> int:
    """Ein zweiter Nutzer mit einer Person und einem Tag."""
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


@pytest.fixture
def fremde_daten(con, fremder) -> dict:
    return {"person": personen.anlegen(con, fremder, "Fremd Beispiel", firma="Fremd GmbH"),
            "tag": personen.tag_anlegen(con, fremder, "Fremdtag")}


def _spalte(antwort) -> str | None:
    kopf = antwort.headers.get("hx-trigger")
    return json.loads(kopf)["spalte"] if kopf else None


# ------------------------------------------------------------- Startseite

def test_leere_startseite_hat_leerzustaende_und_nullen(angemeldet):
    text = angemeldet.get("/").text
    assert re.search(r'<span class="eintrag-name">Alle</span><span class="zahl">0</span>', text)
    assert "Noch keine Tags." in text
    assert "Noch keine Personen." in text
    assert "Wähle eine Person" in text
    assert re.search(r'karte-zahl">0</span>\s*<span class="karte-name">Diese Woche<', text)


def test_seitenleiste_zeigt_zahlen_und_tags(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.anlegen(con, nid, "Ben Muster")
    cem = personen.anlegen(con, nid, "Cem Probe")
    personen.tags_setzen(con, nid, anna, {familie})
    personen.archivieren(con, nid, cem)
    text = angemeldet.get("/").text
    assert re.search(r'<span class="eintrag-name">Alle</span><span class="zahl">2<', text)
    assert re.search(r'Noch kein Kontakt</span><span class="zahl">2<', text)
    assert re.search(r'Archiv</span><span class="zahl">1<', text)
    assert re.search(r'Familie</span><span class="zahl">1<', text)
    assert "Anna Beispiel" in text and "Cem Probe" not in text


def test_zeile_zeigt_name_firma_und_erste_zeile_der_notiz(angemeldet, con, nid):
    personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster",
                     profilnotiz="\nMag Tee.\nZweite Zeile")
    text = angemeldet.get("/").text
    assert ">Anna Beispiel<" in text and ">Firma Muster<" in text
    assert ">Mag Tee.<" in text and "Zweite Zeile" not in text


def test_filter_in_der_adresse(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.anlegen(con, nid, "Ben Muster")
    personen.tags_setzen(con, nid, anna, {familie})
    text = angemeldet.get(f"/?tag={familie}").text
    assert "Anna Beispiel" in text and "Ben Muster" not in text
    assert 'eintrag eintrag-aktiv" href="/?tag=' in text
    text = angemeldet.get("/?suche=ben").text
    assert "Ben Muster" in text and "Anna Beispiel" not in text
    assert 'value="ben"' in text


def test_ausgewaehlte_person_steht_in_der_personenseite(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel", telefon="0170 123 45",
                            email="anna@example.org", ort="Köln")
    text = angemeldet.get(f"/?person={anna}").text
    assert 'value="Anna Beispiel"' in text
    assert 'href="tel:017012345"' in text
    assert 'href="mailto:anna@example.org"' in text
    assert "zeile-ausgewaehlt" in text
    assert 'aria-current="true"' in text


# ------------------------------------------------------------- Personenseite

def test_personenseite_hat_alle_felder_inline_und_diktat_haken(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    teil = angemeldet.get(f"/personen/{anna}", headers=HX)
    assert teil.status_code == 200
    text = teil.text
    assert '<html' not in text
    assert f'hx-post="/personen/{anna}"' in text and 'hx-trigger="change, submit"' in text
    for feld in ("name", "firma", "rolle", "telefon", "email", "ort", "herkunft",
                 "profilnotiz", "intervall_tage", "naechster_termin"):
        assert f'name="{feld}"' in text, feld
    assert re.search(r"<textarea[^>]*data-diktat", text)
    assert "Archivieren" in text and "Wiederherstellen" not in text
    assert _spalte(teil) == "person"
    assert teil.headers["hx-push-url"] == f"/?person={anna}"


def test_personenseite_ohne_htmx_leitet_auf_die_seite(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.get(f"/personen/{anna}")
    assert antwort.status_code == 303
    assert antwort.headers["location"] == f"/?person={anna}"


def test_person_oeffnen_behaelt_den_filter_und_setzt_die_auswahl(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.tags_setzen(con, nid, anna, {familie})
    antwort = angemeldet.get(f"/personen/{anna}", headers=hx(f"/?tag={familie}"))
    assert antwort.headers["hx-push-url"] == f"/?tag={familie}&person={anna}"
    assert 'id="listenkoerper"' in antwort.text and 'hx-swap-oob="true"' in antwort.text
    assert "zeile-ausgewaehlt" in antwort.text


def test_neue_person_formular_und_anlegen(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    formular = angemeldet.get("/personen/neu", headers=hx(f"/?tag={familie}"))
    assert formular.status_code == 200
    assert 'hx-post="/personen"' in formular.text
    assert re.search(rf'value="{familie}" checked', formular.text), "Tag der Liste vorbelegt"
    antwort = angemeldet.post("/personen", headers=hx(), data={
        "name": "  Anna Beispiel ", "firma": "Firma Muster", "rolle": "Leitung",
        "telefon": "0170 1", "email": "anna@example.org", "ort": "Köln",
        "herkunft": "Studium", "profilnotiz": "Mag Tee.", "tag_id": [str(familie)]})
    assert antwort.status_code == 200
    (zeile,) = personen.liste(con, nid)
    assert (zeile["name"], zeile["firma"], zeile["rolle"]) == (
        "Anna Beispiel", "Firma Muster", "Leitung")
    assert personen.tags_der_person(con, nid, zeile["id"]) == {familie}
    assert antwort.headers["hx-push-url"] == f"/?person={zeile['id']}"
    assert _spalte(antwort) == "person"
    # Das Hauptziel ist die Personenseite, dazu Seitenleiste und Liste ausserhalb davon.
    assert 'id="personenseite"' in antwort.text
    assert 'id="seitenleiste"' in antwort.text and 'hx-swap-oob="true"' in antwort.text
    assert re.search(r'Alle</span><span class="zahl">1<', antwort.text)
    assert re.search(r'Familie</span><span class="zahl">1<', antwort.text)


def test_anlegen_mit_neuem_tag(angemeldet, con, nid):
    angemeldet.post("/personen", headers=hx(), data={"name": "Anna", "neuer_tag": "Nachbarn"})
    (tag,) = personen.tags_mit_zaehlern(con, nid)
    assert (tag["name"], tag["anzahl"]) == ("Nachbarn", 1)


def test_anlegen_ohne_name_zeigt_meldung_und_behaelt_eingaben(angemeldet, con, nid):
    antwort = angemeldet.post("/personen", headers=hx(),
                              data={"name": "  ", "firma": "Firma Muster"})
    assert antwort.status_code == 422
    assert "Der Name darf nicht leer sein." in antwort.text
    assert 'value="Firma Muster"' in antwort.text
    assert personen.liste(con, nid) == []


def test_inline_speichern_aendert_felder_und_antwortet_mit_teilen(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster")
    antwort = angemeldet.post(f"/personen/{anna}", headers=hx(f"/?person={anna}"), data={
        "name": "Anna Probe", "firma": "Firma Muster", "telefon": "+49 170 99",
        "intervall_tage": "30", "naechster_termin": "2027-02-01", "profilnotiz": "Neu."})
    assert antwort.status_code == 200
    p = personen.laden(con, nid, anna)
    assert (p["name"], p["telefon"], p["intervall_tage"], p["naechster_termin"],
            p["profilnotiz"]) == ("Anna Probe", "+49 170 99", 30, "2027-02-01", "Neu.")
    assert "Gespeichert" in antwort.text
    assert 'href="tel:+4917099"' in antwort.text         # die Links werden mit getauscht
    assert ">Anna Probe<" in antwort.text                # die Zeile in der Liste auch


def test_inline_speichern_laesst_nicht_gesendete_felder_in_ruhe(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster")
    angemeldet.post(f"/personen/{anna}", headers=hx(), data={"ort": "Köln"})
    p = personen.laden(con, nid, anna)
    assert (p["firma"], p["ort"]) == ("Firma Muster", "Köln")


def test_inline_leeren_eines_feldes(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster", intervall_tage=30)
    angemeldet.post(f"/personen/{anna}", headers=hx(), data={"firma": "", "intervall_tage": ""})
    p = personen.laden(con, nid, anna)
    assert p["firma"] is None and p["intervall_tage"] is None


@pytest.mark.parametrize(("feld", "wert", "text"), [
    ("name", "", "Der Name darf nicht leer sein."),
    ("intervall_tage", "0", "mindestens 1 Tag"),
    ("naechster_termin", "gestern", "kein gültiges Datum"),
])
def test_inline_fehler_zeigt_die_seite_neu_mit_meldung(angemeldet, con, nid, feld, wert, text):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post(f"/personen/{anna}", headers=hx(), data={feld: wert})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == "#personenseite"
    assert antwort.headers["hx-reswap"] == "outerHTML"
    assert text in antwort.text
    assert personen.laden(con, nid, anna)["name"] == "Anna Beispiel"


def test_archivieren_und_wiederherstellen(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.anlegen(con, nid, "Ben Muster")
    antwort = angemeldet.post(f"/personen/{anna}/archivieren", headers=hx(f"/?person={anna}"))
    assert antwort.status_code == 200
    assert personen.laden(con, nid, anna)["archiviert_am"]
    assert "Diese Person liegt im Archiv." in antwort.text
    assert "Wiederherstellen" in antwort.text and ">Archivieren<" not in antwort.text
    assert re.search(r'Archiv</span><span class="zahl">1<', antwort.text)
    assert re.search(r'Alle</span><span class="zahl">1<', antwort.text)
    assert "Anna Beispiel" not in angemeldet.get("/").text.split('id="personenseite"')[0]
    assert "Anna Beispiel" in angemeldet.get("/?filter=archiv").text

    antwort = angemeldet.post(f"/personen/{anna}/wiederherstellen",
                              headers=hx(f"/?filter=archiv&person={anna}"))
    assert personen.laden(con, nid, anna)["archiviert_am"] is None
    assert ">Archivieren<" in antwort.text
    assert re.search(r'Alle</span><span class="zahl">2<', antwort.text)


# ------------------------------------------------------------------ Listen

def test_sidebar_eintrag_liefert_liste_leert_die_person_und_schreibt_die_adresse(
        angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.anlegen(con, nid, "Ben Muster")
    personen.tags_setzen(con, nid, anna, {familie})
    antwort = angemeldet.get(f"/liste?tag={familie}", headers=hx(f"/?person={anna}"))
    assert antwort.status_code == 200
    assert antwort.headers["hx-push-url"] == f"/?tag={familie}"
    assert _spalte(antwort) == "liste"
    assert 'id="liste"' in antwort.text and "Anna Beispiel" in antwort.text
    assert "Ben Muster" not in antwort.text
    assert "Wähle eine Person" in antwort.text
    assert "aria-current=\"page\"" in antwort.text


def test_liste_ohne_kontakt_und_archiv(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    ben = personen.anlegen(con, nid, "Ben Muster")
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, "
                "'2026-10-01', 'anruf')", (nid, anna))
    con.commit()
    personen.archivieren(con, nid, ben)
    text = angemeldet.get("/liste?filter=ohne_kontakt", headers=HX).text
    assert "Zu allen ist ein Kontakt eingetragen." in text
    text = angemeldet.get("/liste?filter=archiv", headers=HX).text
    assert "Ben Muster" in text and "Anna Beispiel" not in text


def test_leerzustaende_der_listen(angemeldet, con, nid):
    tag = personen.tag_anlegen(con, nid, "Leer")
    assert "Diesem Tag ist noch niemand zugeordnet." in angemeldet.get(f"/?tag={tag}").text
    assert "Das Archiv ist leer." in angemeldet.get("/?filter=archiv").text
    assert "Niemand gefunden für „xyz“." in angemeldet.get("/?suche=xyz").text


def test_suche_tauscht_nur_den_listenkoerper(angemeldet, con, nid):
    personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster")
    personen.anlegen(con, nid, "Ben Muster")
    antwort = angemeldet.get("/liste/suche?suche=firma", headers=HX)
    assert antwort.status_code == 200
    assert antwort.text.lstrip().startswith('<div id="listenkoerper"')
    assert "hx-swap-oob" not in antwort.text and 'type="search"' not in antwort.text
    assert "Anna Beispiel" in antwort.text and "Ben Muster" not in antwort.text
    assert antwort.headers["hx-replace-url"] == "/?suche=firma"
    assert "hx-push-url" not in antwort.headers


def test_suche_hat_verzoegerung_und_gehoert_zu_einem_formular(angemeldet):
    text = angemeldet.get("/").text
    assert re.search(r'<form class="suche"[^>]*hx-get="/liste/suche"[^>]*'
                     r'hx-trigger="input delay:300ms', text)
    assert 'hx-target="#listenkoerper"' in text


def test_suche_findet_umlaute_ohne_gross_klein(angemeldet, con, nid):
    personen.anlegen(con, nid, "Ärztin Beispiel", ort="Köln")
    assert "Ärztin Beispiel" in angemeldet.get("/liste/suche?suche=ÄRZTIN", headers=HX).text
    assert "Ärztin Beispiel" in angemeldet.get("/liste/suche?suche=köln", headers=HX).text


def test_suche_behaelt_den_filter(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.anlegen(con, nid, "Anton Muster")
    personen.tags_setzen(con, nid, anna, {familie})
    antwort = angemeldet.get(f"/liste/suche?tag={familie}&suche=an", headers=HX)
    assert "Anna Beispiel" in antwort.text and "Anton Muster" not in antwort.text
    assert antwort.headers["hx-replace-url"] == f"/?tag={familie}&suche=an"


# -------------------------------------------------------------------- Tags

def test_tag_anlegen_ueber_die_seitenleiste(angemeldet, con, nid):
    antwort = angemeldet.post("/tags", headers=hx(), data={"name": " Familie "})
    assert antwort.status_code == 200
    assert [t["name"] for t in personen.tags_mit_zaehlern(con, nid)] == ["Familie"]
    assert 'id="seitenleiste"' in antwort.text and "Familie" in antwort.text


def test_doppelter_tag_zeigt_meldung_in_der_seitenleiste(angemeldet, con, nid):
    personen.tag_anlegen(con, nid, "Familie")
    antwort = angemeldet.post("/tags", headers=hx(), data={"name": "familie"})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == "#seitenleistenmeldung"
    assert "gibt es schon" in antwort.text
    assert len(personen.tags_mit_zaehlern(con, nid)) == 1


def test_tag_umbenennen_tauscht_titel_und_seitenleiste(angemeldet, con, nid):
    tag = personen.tag_anlegen(con, nid, "Familie")
    antwort = angemeldet.post(f"/tags/{tag}", headers=hx(f"/?tag={tag}"),
                              data={"name": "Verwandte"})
    assert antwort.status_code == 200
    assert personen.tag_laden(con, nid, tag)["name"] == "Verwandte"
    assert re.search(r'<h2 id="listentitel"[^>]*>Verwandte</h2>', antwort.text)
    assert "Verwandte" in antwort.text.split('id="listenkoerper"')[0]


def test_tag_umbenennen_auf_vorhandenen_namen_scheitert(angemeldet, con, nid):
    tag = personen.tag_anlegen(con, nid, "Familie")
    personen.tag_anlegen(con, nid, "Arbeit")
    antwort = angemeldet.post(f"/tags/{tag}", headers=hx(), data={"name": "arbeit"})
    assert antwort.status_code == 422 and antwort.headers["hx-retarget"] == "#listenmeldung"
    assert personen.tag_laden(con, nid, tag)["name"] == "Familie"


def test_tag_loeschen_loest_nur_die_zuordnung(angemeldet, con, nid):
    tag = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.tags_setzen(con, nid, anna, {tag})
    antwort = angemeldet.post(f"/tags/{tag}/loeschen", headers=hx(f"/?tag={tag}"))
    assert antwort.status_code == 204
    assert antwort.headers["hx-redirect"] == "/"
    assert personen.tag_laden(con, nid, tag) is None
    assert personen.laden(con, nid, anna)["archiviert_am"] is None
    assert "Anna Beispiel" in angemeldet.get("/").text


def test_tags_an_der_person_setzen_und_abwaehlen(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    arbeit = personen.tag_anlegen(con, nid, "Arbeit")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post(f"/personen/{anna}/tags", headers=hx(f"/?person={anna}"),
                              data={"tag_id": [str(familie), str(arbeit)]})
    assert antwort.status_code == 200
    assert personen.tags_der_person(con, nid, anna) == {familie, arbeit}
    assert antwort.text.lstrip().startswith('<section id="personentags"')
    assert re.search(r'Familie</span><span class="zahl">1<', antwort.text)
    antwort = angemeldet.post(f"/personen/{anna}/tags", headers=hx(),
                              data={"tag_id": [str(arbeit)]})
    assert personen.tags_der_person(con, nid, anna) == {arbeit}
    angemeldet.post(f"/personen/{anna}/tags", headers=hx())
    assert personen.tags_der_person(con, nid, anna) == set()


def test_tag_in_der_personenseite_neu_anlegen(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post(f"/personen/{anna}/tags/neu", headers=hx(),
                              data={"neuer_tag": "Nachbarn"})
    assert antwort.status_code == 200
    (tag,) = personen.tags_mit_zaehlern(con, nid)
    assert tag["name"] == "Nachbarn"
    assert personen.tags_der_person(con, nid, anna) == {tag["id"]}
    # Derselbe Name noch einmal haengt den vorhandenen Tag an, legt keinen zweiten an.
    ben = personen.anlegen(con, nid, "Ben Muster")
    angemeldet.post(f"/personen/{ben}/tags/neu", headers=hx(), data={"neuer_tag": "nachbarn"})
    assert len(personen.tags_mit_zaehlern(con, nid)) == 1
    assert personen.tags_der_person(con, nid, ben) == {tag["id"]}


def test_ein_neuer_tag_haelt_die_bisherigen_tags_der_person(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    personen.tags_setzen(con, nid, anna, {familie})
    angemeldet.post(f"/personen/{anna}/tags/neu", headers=hx(), data={"neuer_tag": "Nachbarn"})
    assert len(personen.tags_der_person(con, nid, anna)) == 2


def test_leerer_neuer_tag_an_der_person_ist_eine_meldung(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post(f"/personen/{anna}/tags/neu", headers=hx(),
                              data={"neuer_tag": " "})
    assert antwort.status_code == 422 and "braucht einen Namen" in antwort.text


def test_neuer_tag_in_der_seitenleiste_erscheint_in_der_offenen_personenseite(
        angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post("/tags", headers=hx(f"/?person={anna}"), data={"name": "Neu"})
    assert 'id="personentags"' in antwort.text and ">Neu<" in antwort.text.split(
        'id="personentags"')[1]


# ----------------------------------------------------------------- Mehrere

def test_mehrere_formular(angemeldet, con, nid):
    personen.tag_anlegen(con, nid, "Familie")
    antwort = angemeldet.get("/personen/mehrere", headers=HX)
    assert antwort.status_code == 200
    text = antwort.text
    assert 'hx-post="/personen/mehrere"' in text
    assert re.search(r"<textarea[^>]*data-diktat", text)
    for wert in ("diesen_monat", "vor_monaten", "ueber_ein_jahr", "unbekannt"):
        assert f'value="{wert}"' in text
    assert re.search(r'value="unbekannt" checked', text)
    assert "Familie" in text


def test_fuenf_personen_auf_einmal(angemeldet, con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    antwort = angemeldet.post("/personen/mehrere", headers=hx(), data={
        "namen": "Anna Beispiel\nBen Muster; Firma Muster\n\nCem Probe\nDora Test\nEva Muster",
        "tag_id": [str(familie)], "letzter_kontakt": "vor_monaten"})
    assert antwort.status_code == 200
    liste = personen.liste(con, nid)
    assert [z["name"] for z in liste] == ["Anna Beispiel", "Ben Muster", "Cem Probe",
                                          "Dora Test", "Eva Muster"]
    assert liste[1]["firma"] == "Firma Muster"
    assert all(personen.tags_der_person(con, nid, z["id"]) == {familie} for z in liste)
    arten = con.execute("SELECT DISTINCT art FROM kontakt").fetchall()
    assert [a["art"] for a in arten] == ["schaetzung"]
    assert con.execute("SELECT COUNT(*) FROM kontakt").fetchone()[0] == 5
    # Die erste angelegte Person ist ausgewaehlt (Annas Zeile, Annas Seite).
    erste = con.execute("SELECT MIN(id) FROM person").fetchone()[0]
    assert antwort.headers["hx-push-url"] == f"/?person={erste}"
    assert 'value="Anna Beispiel"' in antwort.text
    assert re.search(r'Alle</span><span class="zahl">5<', antwort.text)
    assert "Noch kein Kontakt</span><span class=\"zahl\">0<" in antwort.text


def test_mehrere_ohne_namen_ist_eine_meldung(angemeldet, con, nid):
    antwort = angemeldet.post("/personen/mehrere", headers=hx(), data={"namen": "  \n "})
    assert antwort.status_code == 422
    assert "mindestens einen Namen" in antwort.text
    assert personen.liste(con, nid) == []


def test_mehrere_behaelt_den_text_bei_einem_fehler(angemeldet, con, nid):
    antwort = angemeldet.post("/personen/mehrere", headers=hx(),
                              data={"namen": ";nur eine Firma", "letzter_kontakt": "vor_monaten"})
    assert antwort.status_code == 422
    assert ";nur eine Firma" in antwort.text
    assert re.search(r'value="vor_monaten" checked', antwort.text)


# ------------------------------------------------------- Mehrere Nutzer

@pytest.fixture
def anderer_client(fremder):
    from fastapi.testclient import TestClient

    with TestClient(app, follow_redirects=False) as c:
        assert c.post("/anmeldung", data={"name": "Anderer", "passwort": PASSWORT}
                      ).status_code == 303
        yield c


def test_ein_nutzer_sieht_die_personen_des_anderen_nicht(
        angemeldet, anderer_client, con, nid, fremde_daten):
    eigen = personen.anlegen(con, nid, "Anna Beispiel")
    text = angemeldet.get("/").text
    assert "Fremd Beispiel" not in text and "Fremdtag" not in text
    assert "Fremd Beispiel" in anderer_client.get("/").text
    assert "Anna Beispiel" not in anderer_client.get("/").text
    assert "Fremd Beispiel" not in angemeldet.get("/liste/suche?suche=fremd", headers=HX).text
    assert anderer_client.get(f"/personen/{eigen}", headers=HX).status_code == 404


@pytest.mark.parametrize("aufruf", [
    lambda c, p, t: c.get(f"/personen/{p}", headers=HX),
    lambda c, p, t: c.get(f"/?person={p}"),
    lambda c, p, t: c.get(f"/?tag={t}"),
    lambda c, p, t: c.get(f"/liste?tag={t}", headers=HX),
    lambda c, p, t: c.get(f"/liste/suche?tag={t}", headers=HX),
    lambda c, p, t: c.post(f"/personen/{p}", headers=HX, data={"name": "Gekapert"}),
    lambda c, p, t: c.post(f"/personen/{p}/archivieren", headers=HX),
    lambda c, p, t: c.post(f"/personen/{p}/wiederherstellen", headers=HX),
    lambda c, p, t: c.post(f"/personen/{p}/tags", headers=HX, data={"tag_id": [str(t)]}),
    lambda c, p, t: c.post(f"/personen/{p}/tags/neu", headers=HX, data={"neuer_tag": "X"}),
    lambda c, p, t: c.post(f"/tags/{t}", headers=HX, data={"name": "Gekapert"}),
    lambda c, p, t: c.post(f"/tags/{t}/loeschen", headers=HX),
], ids=["person-teil", "person-seite", "tag-seite", "tag-liste", "tag-suche", "person-speichern",
        "archivieren", "wiederherstellen", "person-tags", "person-tag-neu", "tag-umbenennen",
        "tag-loeschen"])
def test_fremde_nummern_sind_ein_404(angemeldet, con, fremder, fremde_daten, aufruf):
    antwort = aufruf(angemeldet, fremde_daten["person"], fremde_daten["tag"])
    assert antwort.status_code == 404
    assert "Fremd" not in antwort.text
    # ... und nichts hat sich beim anderen Nutzer geaendert.
    fremd = personen.laden(con, fremder, fremde_daten["person"])
    assert fremd["name"] == "Fremd Beispiel" and fremd["archiviert_am"] is None
    assert personen.tag_laden(con, fremder, fremde_daten["tag"])["name"] == "Fremdtag"
    assert personen.tags_der_person(con, fremder, fremde_daten["person"]) == set()


def test_eigene_person_mit_fremdem_tag_bekommt_ihn_nicht(angemeldet, con, nid, fremde_daten):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    antwort = angemeldet.post(f"/personen/{anna}/tags", headers=HX,
                              data={"tag_id": [str(fremde_daten["tag"])]})
    assert antwort.status_code == 404
    assert personen.tags_der_person(con, nid, anna) == set()


@pytest.mark.parametrize(("pfad", "eingabe"), [
    ("/personen", {"name": "Anna"}),
    ("/personen/mehrere", {"namen": "Anna\nBen"}),
])
def test_anlegen_mit_fremdem_tag_ist_ein_404_und_legt_nichts_an(
        angemeldet, con, nid, fremde_daten, pfad, eingabe):
    antwort = angemeldet.post(pfad, headers=HX,
                              data={**eingabe, "tag_id": [str(fremde_daten["tag"])]})
    assert antwort.status_code == 404
    assert personen.liste(con, nid) == []


def test_fremde_nummern_in_der_aktuellen_seite_werden_still_ignoriert(
        angemeldet, con, nid, fremde_daten):
    """HX-Current-URL ist vom Browser; ein fremder Tag dort darf nichts verraten."""
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    kopf = hx(f"/?tag={fremde_daten['tag']}&person={fremde_daten['person']}")
    antwort = angemeldet.post(f"/personen/{anna}", headers=kopf, data={"ort": "Köln"})
    assert antwort.status_code == 200
    assert "Fremd" not in antwort.text
    formular = angemeldet.get("/personen/neu", headers=kopf)
    assert "checked" not in formular.text.replace('checked="', "")


# ---------------------------------------------------------- Telefonbreite

@pytest.mark.parametrize(("adresse", "spalte"), [
    ("/", "seitenleiste"),
    ("/?tag={tag}", "liste"),
    ("/?filter=archiv", "liste"),
    ("/?suche=anna", "liste"),
    ("/?person={person}", "person"),
])
def test_auf_dem_telefon_ist_eine_spalte_offen(angemeldet, con, nid, adresse, spalte):
    tag = personen.tag_anlegen(con, nid, "Familie")
    person = personen.anlegen(con, nid, "Anna Beispiel")
    text = angemeldet.get(adresse.format(tag=tag, person=person)).text
    assert f'<div class="app" id="app" data-ansicht="{spalte}">' in text


def test_zurueck_pfeile_fuehren_eine_spalte_nach_links(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    text = angemeldet.get(f"/?person={anna}").text
    assert re.search(r'data-zeige="seitenleiste" aria-label="Zurück zur Seitenleiste">‹ Zurück<',
                     text)
    assert re.search(r'data-zeige="liste" aria-label="Zurück zur Liste">‹ Zurück<', text)
    assert 'src="/statisch/bindung.js"' in text


def test_der_server_sagt_dem_telefon_welche_spalte_offen_ist(angemeldet, con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    assert _spalte(angemeldet.get(f"/personen/{anna}", headers=HX)) == "person"
    assert _spalte(angemeldet.get("/liste?filter=archiv", headers=HX)) == "liste"
    assert _spalte(angemeldet.get("/personen/leer", headers=HX)) == "liste"
    assert _spalte(angemeldet.get("/personen/neu", headers=HX)) == "person"
    assert _spalte(angemeldet.get("/personen/mehrere", headers=HX)) == "person"


def test_stylesheet_zeigt_je_ansicht_genau_eine_spalte():
    from bindung.web.basis import STATISCH

    css = (STATISCH / "stil.css").read_text(encoding="utf-8")
    assert "@media (max-width: 767px)" in css
    for ansicht, versteckt in (("seitenleiste", ("liste", "personenseite")),
                               ("liste", ("seitenleiste", "personenseite")),
                               ("person", ("seitenleiste", "liste"))):
        for spalte in versteckt:
            assert f'.app[data-ansicht="{ansicht}"] > .{spalte}' in css
    assert "display: none" in css.split("@media (max-width: 767px)")[1]


def test_javascript_kennt_beide_wege():
    from bindung.web.basis import STATISCH

    js = (STATISCH / "bindung.js").read_text(encoding="utf-8")
    assert "data-zeige" in js or "dataset.zeige" in js
    assert '"spalte"' in js
