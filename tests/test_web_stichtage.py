"""Angehoerige und Stichtage auf der Personenseite: die Teile, die HTMX tauscht.

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

from bindung import angehoerige, auth, faelligkeit, kontakte, personen, stichtage
from bindung.web import ansicht

from .conftest import PASSWORT

HEUTE = dt.date(2026, 11, 11)


def hx(aktuell: str = "/") -> dict:
    return {"HX-Request": "true", "HX-Current-URL": f"http://testserver{aktuell}"}


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC))


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def anna(con, nid) -> int:
    return personen.anlegen(con, nid, "Anna Beispiel")


@pytest.fixture
def ben(con, nid) -> int:
    return personen.anlegen(con, nid, "Ben Muster")


@pytest.fixture
def fremder(con) -> int:
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


def datum_in(tage: int, jahr: int | None = None) -> dict[str, str]:
    """Die Formularfelder tag, monat (und jahr) fuer einen Tag `tage` nach heute."""
    ziel = HEUTE + dt.timedelta(days=tage)
    return {"tag": str(ziel.day), "monat": str(ziel.month), "jahr": str(jahr) if jahr else ""}


def speicher(text: str, abschnitt: str) -> str:
    """Der Abschnitt (`angehoerige` oder `stichtage`) in einer Antwort, Leerraum zusammengezogen."""
    treffer = re.search(rf'<section id="{abschnitt}".*?</section>', text, flags=re.S)
    assert treffer, f"{abschnitt} fehlt in der Antwort"
    return re.sub(r"\s+", " ", treffer.group(0))


def karten(text: str) -> dict[str, int]:
    return {name: int(zahl) for zahl, name in re.findall(
        r'karte-zahl">(\d+)</span>\s*<span class="karte-name">([^<]+)<', text)}


def zeile(text: str, name: str) -> str:
    for li in re.findall(r'<li class="zeilenpunkt">.*?</li>', text, flags=re.S):
        if f">{name}<" in li:
            return re.sub(r"\s+", " ", li)
    raise AssertionError(f"{name} steht nicht in der Liste")


def kontakt_vor(con, nid, pid, tage: int) -> None:
    kontakte.eintragen(con, nid, pid, datum=HEUTE - dt.timedelta(days=tage), art="anruf")


# --------------------------------------------------------------- Abschnitte

def test_die_personenseite_hat_beide_abschnitte_unter_zuletzt_besprochen(angemeldet, anna):
    text = angemeldet.get(f"/?person={anna}").text
    reihe = [text.index(f'id="{name}"') for name in ("verlauf", "angehoerige", "stichtage")]
    assert reihe == sorted(reihe)
    assert text.index('id="stichtage"') < text.index('id="telefon"')
    assert ">Angehörige<" in text and ">Stichtage<" in text
    assert "Noch niemand eingetragen." in speicher(text, "angehoerige")
    assert "Noch kein Stichtag." in speicher(text, "stichtage")
    assert "7 Tage vorher" in speicher(text, "stichtage")


def test_die_abschnitte_bieten_die_formulare_an(angemeldet, anna):
    text = angemeldet.get(f"/?person={anna}").text
    familie = speicher(text, "angehoerige")
    assert f'hx-post="/personen/{anna}/angehoerige"' in familie
    assert "Angehörigen hinzufügen" in familie
    for rolle in ("Partner/in", "Kind", "Elternteil", "Geschwister", "Sonstiges"):
        assert f">{rolle}</option>" in familie
    assert 'name="tag"' in familie and 'name="monat"' in familie and 'name="jahr"' in familie
    assert "In der App" in familie
    termine = speicher(text, "stichtage")
    assert f'hx-post="/personen/{anna}/stichtage"' in termine
    for art in ("Geburtstag", "Jahrestag", "Sonstiges"):
        assert f"<span>{art}</span>" in termine
    assert re.search(r'name="art" value="geburtstag" checked', termine)
    assert 'name="vorlauf_tage"' in termine and "7 (Vorgabe)" in termine
    assert ">März</option>" in termine


def test_die_formulare_sind_zu_bis_ein_fehler_sie_oeffnet(angemeldet, anna):
    text = angemeldet.get(f"/?person={anna}").text
    assert "<details class=\"hinzufuegen\">" in speicher(text, "angehoerige")
    assert " open>" not in speicher(text, "angehoerige")


# ---------------------------------------------------------- Angehoerige

def test_angehoerigen_mit_geburtstag_anlegen(angemeldet, con, nid, anna):
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(f"/?person={anna}"),
                              data={"name": "Mia", "rolle": "kind", "rolle_text": "",
                                    **datum_in(3, 2019)})
    assert antwort.status_code == 200
    text = antwort.text
    (zeile_,) = angehoerige.liste(con, nid, anna)
    assert (zeile_["name"], zeile_["rolle"]) == ("Mia", "kind")
    # Hauptteil: der Abschnitt, ohne oob; der andere Abschnitt per oob
    assert text.lstrip().startswith('<section id="angehoerige"')
    assert not re.search(r'<section id="angehoerige"[^>]*hx-swap-oob', text)
    assert re.search(r'<section id="stichtage"[^>]*hx-swap-oob="true"', text)
    familie = speicher(text, "angehoerige")
    assert "Mia" in familie and ">Kind<" in familie and "Geburtstag 14. November 2019" in familie
    termine = speicher(text, "stichtage")
    assert "Geburtstag Mia" in termine and "wird 7" in termine and "in 3 Tagen" in termine
    # Zeile, Karten und Seitenleiste ziehen nach
    assert 'id="karten"' in text and 'id="listenkoerper"' in text and 'id="seitenleiste"' in text
    assert karten(text)["Diese Woche"] == 1
    assert "Geburtstag Mia in 3 Tagen" in zeile(text, "Anna Beispiel")


def test_ein_angehoeriger_ohne_geburtstag_legt_keinen_stichtag_an(angemeldet, con, nid, anna):
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(),
                              data={"name": "Mia", "rolle": "kind", "tag": "", "monat": "",
                                    "jahr": ""})
    assert antwort.status_code == 200
    assert "Noch kein Stichtag." in speicher(antwort.text, "stichtage")
    assert karten(antwort.text)["Diese Woche"] == 0


def test_sonstiges_zeigt_den_freitext_als_rolle(angemeldet, anna):
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(),
                              data={"name": "Leo", "rolle": "sonstiges",
                                    "rolle_text": "Patenkind"})
    assert ">Patenkind<" in speicher(antwort.text, "angehoerige")


@pytest.mark.parametrize(("eingabe", "meldung"), [
    ({"name": "", "rolle": "kind"}, "Der Name darf nicht leer sein."),
    ({"name": "Mia", "rolle": "freund"}, "Wähle eine Rolle aus."),
    ({"name": "Mia", "rolle": "kind", "tag": "5"}, "Gib Tag und Monat an."),
    ({"name": "Mia", "rolle": "kind", "tag": "30", "monat": "2"}, "Dieses Datum gibt es nicht."),
    ({"name": "Mia", "rolle": "kind", "tag": "1", "monat": "1", "jahr": "2999"},
     "Das Jahr liegt in der Zukunft."),
    ({"name": "Mia", "rolle": "kind", "verknuepfte_person_id": "abc"}, "Wähle eine Person aus."),
])
def test_angehoerigen_anlegen_lehnt_ab_und_behaelt_die_eingabe(angemeldet, con, nid, anna,
                                                               eingabe, meldung):
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(), data=eingabe)
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == "#angehoerige"
    assert antwort.headers["hx-reswap"] == "outerHTML"
    familie = speicher(antwort.text, "angehoerige")
    assert meldung in familie
    assert "<details class=\"hinzufuegen\" open>" in familie
    assert angehoerige.liste(con, nid, anna) == []
    if eingabe.get("name"):
        assert f'value="{eingabe["name"]}"' in familie


def test_angehoerigen_bearbeiten_und_speichern(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="2019-11-14")
    formular = angemeldet.get(f"/angehoerige/{aid}/bearbeiten", headers=hx())
    assert formular.status_code == 200
    assert f'<li class="posten posten-bearbeiten" id="angehoeriger-{aid}">' in formular.text
    assert 'value="Mia"' in formular.text
    assert re.search(r'<option value="kind" selected>', formular.text)
    assert re.search(r'<option value="11" selected>', formular.text)
    assert 'name="jahr" value="2019"' in formular.text
    antwort = angemeldet.post(f"/angehoerige/{aid}", headers=hx(),
                              data={"name": "Mia Maria", "rolle": "kind", "tag": "15",
                                    "monat": "11", "jahr": "2019"})
    assert antwort.status_code == 200
    assert "Mia Maria" in speicher(antwort.text, "angehoerige")
    assert "Geburtstag Mia Maria" in speicher(antwort.text, "stichtage")
    assert angehoerige.laden(con, nid, aid)["geburtstag"] == "2019-11-15"


def test_den_geburtstag_beim_bearbeiten_leeren_loescht_den_stichtag(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--11-14")
    antwort = angemeldet.post(f"/angehoerige/{aid}", headers=hx(),
                              data={"name": "Mia", "rolle": "kind", "tag": "", "monat": "",
                                    "jahr": ""})
    assert "Noch kein Stichtag." in speicher(antwort.text, "stichtage")
    assert karten(antwort.text)["Diese Woche"] == 0


def test_bearbeiten_mit_fehler_bleibt_im_eintrag(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    antwort = angemeldet.post(f"/angehoerige/{aid}", headers=hx(),
                              data={"name": " ", "rolle": "kind"})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == f"#angehoeriger-{aid}"
    assert "Der Name darf nicht leer sein." in antwort.text
    assert angehoerige.laden(con, nid, aid)["name"] == "Mia"


def test_abbrechen_zeigt_den_eintrag_wieder(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    antwort = angemeldet.get(f"/angehoerige/{aid}", headers=hx())
    assert antwort.status_code == 200
    assert f'id="angehoeriger-{aid}"' in antwort.text and "posten-bearbeiten" not in antwort.text


def test_angehoerigen_loeschen_nimmt_den_stichtag_mit(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--11-14")
    antwort = angemeldet.post(f"/angehoerige/{aid}/loeschen", headers=hx())
    assert antwort.status_code == 200
    assert "Noch niemand eingetragen." in speicher(antwort.text, "angehoerige")
    assert "Noch kein Stichtag." in speicher(antwort.text, "stichtage")
    assert karten(antwort.text)["Diese Woche"] == 0
    assert "Geburtstag" not in zeile(antwort.text, "Anna Beispiel")
    assert angehoerige.liste(con, nid, anna) == []


def test_loeschen_fragt_vorher_und_nennt_die_folgen(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--05-05",
                              verknuepfte_person_id=ben)
    familie = speicher(angemeldet.get(f"/?person={anna}").text, "angehoerige")
    treffer = re.search(rf'hx-post="/angehoerige/{aid}/loeschen"[^>]*hx-confirm="([^"]+)"', familie)
    assert treffer
    assert "Ben Muster wird mit gelöscht" in treffer.group(1)
    assert "Geburtstag verschwindet" in treffer.group(1)


# ---------------------------------------------------------- Verknuepfung

def test_die_auswahl_sucht_unter_den_aktiven_personen(angemeldet, con, nid, anna, ben):
    personen.archivieren(con, nid, personen.anlegen(con, nid, "Berta Alt"))
    antwort = angemeldet.get(f"/personen/{anna}/kandidaten?ziel=neu&suche=be", headers=hx())
    assert antwort.status_code == 200
    assert 'id="kandidaten-neu"' in antwort.text
    assert f'name="verknuepfte_person_id" value="{ben}"' in antwort.text
    assert "Ben Muster" in antwort.text and "Berta" not in antwort.text


def test_die_auswahl_bietet_die_person_selbst_nicht_an(angemeldet, anna, ben):
    antwort = angemeldet.get(f"/personen/{anna}/kandidaten?ziel=neu&suche=anna", headers=hx())
    assert "Niemand gefunden für „anna“." in antwort.text
    assert f'value="{anna}"' not in antwort.text


def test_die_auswahl_ohne_suchtext_und_ohne_treffer(angemeldet, anna):
    leer = angemeldet.get(f"/personen/{anna}/kandidaten?ziel=7", headers=hx())
    assert 'id="kandidaten-7"' in leer.text and "Tippe einen Namen" in leer.text
    kein = angemeldet.get(f"/personen/{anna}/kandidaten?ziel=7&suche=zzz", headers=hx())
    assert "Niemand gefunden" in kein.text


def test_die_auswahl_zeigt_keine_fremden_personen(angemeldet, con, anna, fremder):
    personen.anlegen(con, fremder, "Zoe Fremd")
    antwort = angemeldet.get(f"/personen/{anna}/kandidaten?ziel=neu&suche=zoe", headers=hx())
    assert "Zoe" not in antwort.text and "Niemand gefunden" in antwort.text


def test_die_auswahl_nimmt_nur_saubere_zielnamen(angemeldet, anna):
    assert angemeldet.get(f"/personen/{anna}/kandidaten?ziel=a%22%3E&suche=x",
                          headers=hx()).status_code == 404


def test_die_auswahl_ohne_htmx_leitet_auf_die_seite(angemeldet, anna):
    antwort = angemeldet.get(f"/personen/{anna}/kandidaten?suche=x")
    assert antwort.status_code == 303 and antwort.headers["location"] == f"/?person={anna}"


def test_verknuepfen_legt_das_gegenstueck_an_und_zeigt_es_bei_der_anderen_person(
        angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind")
    antwort = angemeldet.post(f"/angehoerige/{aid}/verknuepfen", headers=hx(),
                              data={"verknuepfte_person_id": str(ben)})
    assert antwort.status_code == 200
    familie = speicher(antwort.text, "angehoerige")
    assert f'href="/?person={ben}"' in familie and f'hx-get="/personen/{ben}"' in familie
    assert ">Ben Muster</a>" in familie
    assert "Verknüpfung lösen" in familie
    # Bens Seite zeigt das Gegenstueck: Anna als Elternteil
    seite = speicher(angemeldet.get(f"/?person={ben}").text, "angehoerige")
    assert ">Anna Beispiel<" in seite and ">Elternteil<" in seite
    assert f'href="/?person={anna}"' in seite


def test_ein_verknuepfter_eintrag_bietet_verknuepfen_nicht_mehr_an(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    familie = speicher(angemeldet.get(f"/?person={anna}").text, "angehoerige")
    assert f'hx-post="/angehoerige/{aid}/verknuepfen"' not in familie
    assert f'hx-post="/angehoerige/{aid}/entknuepfen"' in familie


def test_anlegen_und_gleich_verknuepfen(angemeldet, con, nid, anna, ben):
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(),
                              data={"name": "", "rolle": "partner",
                                    "verknuepfte_person_id": str(ben)})
    assert antwort.status_code == 200
    assert ">Ben Muster</a>" in speicher(antwort.text, "angehoerige")
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert (gegen["rolle"], gegen["name"]) == ("partner", "Anna Beispiel")


def test_verknuepfen_ohne_auswahl(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner")
    antwort = angemeldet.post(f"/angehoerige/{aid}/verknuepfen", headers=hx(), data={})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == "#angehoerige"
    assert "Wähle eine Person aus der Liste." in speicher(antwort.text, "angehoerige")


def test_verknuepfen_mit_sich_selbst_wird_abgelehnt(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Ich", rolle="partner")
    antwort = angemeldet.post(f"/angehoerige/{aid}/verknuepfen", headers=hx(),
                              data={"verknuepfte_person_id": str(anna)})
    assert antwort.status_code == 422
    assert "nicht mit sich selbst verknüpfen" in antwort.text
    assert angehoerige.laden(con, nid, aid)["verknuepfte_person_id"] is None


def test_zweimal_verknuepfen_wird_abgelehnt(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    antwort = angemeldet.post(f"/angehoerige/{aid}/verknuepfen", headers=hx(),
                              data={"verknuepfte_person_id": str(ben)})
    assert antwort.status_code == 422
    assert "schon mit Ben Muster verknüpft" in antwort.text
    assert len(angehoerige.liste(con, nid, ben)) == 1


def test_verknuepfung_loesen_entfernt_das_gegenstueck(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    antwort = angemeldet.post(f"/angehoerige/{aid}/entknuepfen", headers=hx())
    assert antwort.status_code == 200
    familie = speicher(antwort.text, "angehoerige")
    assert "Ben" in familie and "In der App" not in familie.split("Angehörigen hinzufügen")[0]
    assert "Noch niemand eingetragen." in speicher(
        angemeldet.get(f"/?person={ben}").text, "angehoerige")
    assert angehoerige.laden(con, nid, aid)["gegenstueck_id"] is None


def test_loeschen_bei_anna_entfernt_das_gegenstueck_bei_ben(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    angemeldet.post(f"/angehoerige/{aid}/loeschen", headers=hx())
    assert "Noch niemand eingetragen." in speicher(
        angemeldet.get(f"/?person={ben}").text, "angehoerige")


def test_die_rolle_des_gegenstuecks_bearbeitet_sich_getrennt(angemeldet, con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind",
                              verknuepfte_person_id=ben)
    (gegen,) = angehoerige.liste(con, nid, ben)
    angemeldet.post(f"/angehoerige/{gegen['id']}", headers=hx(),
                    data={"name": "Anna", "rolle": "sonstiges", "rolle_text": "Pflegemutter"})
    assert ">Pflegemutter<" in speicher(angemeldet.get(f"/?person={ben}").text, "angehoerige")
    assert ">Kind<" in speicher(angemeldet.get(f"/?person={anna}").text, "angehoerige")
    assert angehoerige.laden(con, nid, aid)["rolle"] == "kind"


def test_eine_archivierte_verknuepfte_person_wird_so_genannt(angemeldet, con, nid, anna, ben):
    angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner", verknuepfte_person_id=ben)
    personen.archivieren(con, nid, ben)
    assert "(im Archiv)" in speicher(angemeldet.get(f"/?person={anna}").text, "angehoerige")


# ---------------------------------------------------------- Stichtage

def test_stichtag_anlegen_ohne_und_mit_jahr(angemeldet, con, nid, anna):
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(),
                              data={"art": "jahrestag", "bezeichnung": "Hochzeitstag",
                                    **datum_in(30, 2016), "vorlauf_tage": ""})
    assert antwort.status_code == 200
    termine = speicher(antwort.text, "stichtage")
    assert antwort.text.lstrip().startswith('<section id="stichtage"')
    assert re.search(r'<section id="angehoerige"[^>]*hx-swap-oob="true"', antwort.text)
    assert "Hochzeitstag" in termine and "11. Dezember 2016" in termine
    assert "Jahrestag · 10 Jahre" in termine and "in 30 Tagen" in termine
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(),
                              data={"art": "geburtstag", "bezeichnung": "", **datum_in(100)})
    termine = speicher(antwort.text, "stichtage")
    assert "19. Februar" in termine and "19. Februar 2" not in termine
    assert [v.bezeichnung for v in stichtage.liste(con, nid, anna)] == [
        "Hochzeitstag", "Geburtstag"]


def test_ein_abweichender_vorlauf_steht_beim_stichtag(angemeldet, anna):
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(),
                              data={"art": "sonstiges", "bezeichnung": "Einzug",
                                    **datum_in(10), "vorlauf_tage": "14"})
    assert "Vorlauf 14 Tage" in speicher(antwort.text, "stichtage")
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(),
                              data={"art": "sonstiges", "bezeichnung": "Umzug",
                                    **datum_in(10), "vorlauf_tage": "1"})
    assert "Vorlauf 1 Tag<" in speicher(antwort.text, "stichtage")


@pytest.mark.parametrize(("eingabe", "meldung"), [
    ({"art": "geburtstag"}, "Gib Tag und Monat an."),
    ({"art": "geburtstag", "tag": "30", "monat": "2"}, "Dieses Datum gibt es nicht."),
    ({"art": "sonstiges", "bezeichnung": "", "tag": "1", "monat": "5"},
     "Gib dem Stichtag einen Namen."),
    ({"art": "feiertag", "tag": "1", "monat": "5"}, "Wähle aus, was für ein Stichtag es ist."),
    ({"art": "jahrestag", "tag": "1", "monat": "5", "vorlauf_tage": "x"},
     "Der Vorlauf ist eine Zahl in Tagen."),
    ({"art": "jahrestag", "tag": "1", "monat": "5", "vorlauf_tage": "400"},
     "Der Vorlauf liegt zwischen 0 und 365 Tagen."),
])
def test_stichtag_anlegen_lehnt_ab(angemeldet, con, nid, anna, eingabe, meldung):
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(), data=eingabe)
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == "#stichtage"
    termine = speicher(antwort.text, "stichtage")
    assert meldung in termine and "<details class=\"hinzufuegen\" open>" in termine
    assert stichtage.liste(con, nid, anna) == []


def test_stichtag_bearbeiten_speichern_und_abbrechen(angemeldet, con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges",
                            datum="2020-09-01", vorlauf_tage=3)
    formular = angemeldet.get(f"/stichtage/{sid}/bearbeiten", headers=hx())
    assert f'<li class="posten posten-bearbeiten" id="stichtag-{sid}">' in formular.text
    assert re.search(r'name="art" value="sonstiges" checked', formular.text)
    assert 'value="Einzug"' in formular.text and 'name="vorlauf_tage" value="3"' in formular.text
    assert re.search(r'<option value="9" selected>', formular.text)
    antwort = angemeldet.post(f"/stichtage/{sid}", headers=hx(),
                              data={"art": "jahrestag", "bezeichnung": "Einzug ins Haus",
                                    "tag": "2", "monat": "9", "jahr": "", "vorlauf_tage": ""})
    assert antwort.status_code == 200
    termine = speicher(antwort.text, "stichtage")
    assert "Einzug ins Haus" in termine and "2. September" in termine
    assert "Vorlauf 3 Tage" not in termine
    zeigen = angemeldet.get(f"/stichtage/{sid}", headers=hx())
    assert f'id="stichtag-{sid}"' in zeigen.text and "posten-bearbeiten" not in zeigen.text


def test_stichtag_bearbeiten_mit_fehler_bleibt_im_eintrag(angemeldet, con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges",
                            datum="2020-09-01")
    antwort = angemeldet.post(f"/stichtage/{sid}", headers=hx(),
                              data={"art": "sonstiges", "bezeichnung": "Einzug", "tag": "31",
                                    "monat": "9"})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == f"#stichtag-{sid}"
    assert "Dieses Datum gibt es nicht." in antwort.text
    assert stichtage.laden(con, nid, sid)["datum"] == "2020-09-01"


def test_stichtag_loeschen_fragt_vorher_und_zieht_alles_nach(angemeldet, con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges",
                            datum=stichtage.bauen(*datum_in(2).values()))
    text = angemeldet.get(f"/?person={anna}").text
    assert 'hx-confirm="Den Stichtag „Einzug“ löschen?"' in speicher(text, "stichtage")
    assert karten(text)["Diese Woche"] == 1
    antwort = angemeldet.post(f"/stichtage/{sid}/loeschen", headers=hx())
    assert antwort.status_code == 200
    assert "Noch kein Stichtag." in speicher(antwort.text, "stichtage")
    assert karten(antwort.text)["Diese Woche"] == 0
    assert "plakette-stichtag" not in zeile(antwort.text, "Anna Beispiel")


def test_der_geburtstag_eines_angehoerigen_hat_im_abschnitt_keine_knoepfe(
        angemeldet, con, nid, anna):
    angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--05-05")
    (v,) = stichtage.liste(con, nid, anna)
    termine = speicher(angemeldet.get(f"/?person={anna}").text, "stichtage")
    assert "Geburtstag Mia" in termine
    assert "Ändere ihn dort." in termine
    assert f"/stichtage/{v.id}/bearbeiten" not in termine
    assert f"/stichtage/{v.id}/loeschen" not in termine


def test_der_geburtstag_eines_angehoerigen_ist_per_post_nicht_zu_aendern(
        angemeldet, con, nid, anna):
    angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--05-05")
    (v,) = stichtage.liste(con, nid, anna)
    bearbeiten = angemeldet.get(f"/stichtage/{v.id}/bearbeiten", headers=hx())
    assert bearbeiten.status_code == 200 and "posten-bearbeiten" not in bearbeiten.text
    speichern = angemeldet.post(f"/stichtage/{v.id}", headers=hx(),
                                data={"art": "geburtstag", "bezeichnung": "x", "tag": "1",
                                      "monat": "1"})
    assert speichern.status_code == 422
    loeschen = angemeldet.post(f"/stichtage/{v.id}/loeschen", headers=hx())
    assert loeschen.status_code == 422 and "Ändere ihn dort" in loeschen.text
    assert len(stichtage.liste(con, nid, anna)) == 1


# ------------------------------------------------- Plakette und Karte

def test_ein_stichtag_im_vorlauf_gibt_der_zeile_die_zweite_plakette(angemeldet, con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                      datum=stichtage.bauen(*datum_in(4, 1986).values()))
    text = zeile(angemeldet.get("/").text, "Anna Beispiel")
    assert re.search(r'<span class="plakette plakette-stichtag">Geburtstag in 4 Tagen</span>',
                     text)
    assert "noch kein Kontakt" in text           # die Plakette des Zustands bleibt daneben


def test_jahrestag_heute_und_benannter_tag(angemeldet, con, nid, anna, ben):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="jahrestag", datum="--11-11")
    stichtage.anlegen(con, nid, ben, bezeichnung="Einzug", art="sonstiges", datum="--11-12")
    text = angemeldet.get("/").text
    assert ">Jahrestag heute<" in zeile(text, "Anna Beispiel")
    assert ">Einzug morgen<" in zeile(text, "Ben Muster")


def test_ausserhalb_des_vorlaufs_keine_plakette_und_nicht_auf_der_karte(
        angemeldet, con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                      datum=stichtage.bauen(*datum_in(8).values()))
    text = angemeldet.get("/").text
    assert "plakette-stichtag" not in zeile(text, "Anna Beispiel")
    assert karten(text)["Diese Woche"] == 0


def test_die_woche_listet_die_person_ohne_ihren_zustand_zu_aendern(angemeldet, con, nid, anna):
    kontakt_vor(con, nid, anna, 5)                       # Zustand ok: vor 5 Tagen
    vorher = faelligkeit.bindungen(con, nid, HEUTE)[anna].zustand
    assert vorher == faelligkeit.OK
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                      datum=stichtage.bauen(*datum_in(3, 1990).values()))
    assert faelligkeit.bindungen(con, nid, HEUTE)[anna].zustand == faelligkeit.OK
    text = angemeldet.get("/").text
    assert karten(text) == {"Braucht Aufmerksamkeit": 0, "Erkaltet": 0, "Diese Woche": 1}
    liste = angemeldet.get("/?karte=woche").text
    assert "Anna Beispiel" in liste
    assert "vor 5 Tagen" in zeile(liste, "Anna Beispiel")
    assert "Geburtstag in 3 Tagen" in zeile(liste, "Anna Beispiel")
    seite = angemeldet.get(f"/?person={anna}").text
    assert re.search(r'plakette plakette-ok">ok<', seite)       # der Zustand der Seite


def test_eine_person_zaehlt_auf_der_woche_nicht_doppelt(angemeldet, con, nid, anna):
    kontakt_vor(con, nid, anna, 52)                      # faellig in 4 Tagen: bald
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                      datum=stichtage.bauen(*datum_in(2).values()))
    stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges",
                      datum=stichtage.bauen(*datum_in(3).values()))
    assert karten(angemeldet.get("/").text)["Diese Woche"] == 1
    text = zeile(angemeldet.get("/?karte=woche").text, "Anna Beispiel")
    assert "Geburtstag in 2 Tagen" in text and "Einzug" not in text   # der naechste
    assert "fällig in 4 Tagen" in text


def test_der_haken_der_ansicht_liefert_die_personen_im_vorlauf(con, nid, anna, ben):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--11-13")
    stichtage.anlegen(con, nid, ben, bezeichnung="", art="geburtstag", datum="--12-24")
    assert ansicht.stichtag_personen(con, nid, HEUTE) == {anna}


def test_archivierte_personen_stehen_nicht_auf_der_woche(angemeldet, con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--11-13")
    personen.archivieren(con, nid, anna)
    assert karten(angemeldet.get("/").text)["Diese Woche"] == 0
    assert "plakette-stichtag" not in angemeldet.get("/?filter=archiv").text


def test_ein_stichtag_ohne_kontakt_macht_die_person_nicht_faellig(angemeldet, con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--11-13")
    text = angemeldet.get("/").text
    assert karten(text) == {"Braucht Aufmerksamkeit": 0, "Erkaltet": 0, "Diese Woche": 1}
    assert "noch kein Kontakt" in zeile(text, "Anna Beispiel")


def test_die_plakette_zieht_in_jeder_antwort_mit(angemeldet, con, nid, anna):
    """Anlegen, Bearbeiten und Loeschen liefern Zeile, Karten und Seitenleiste mit."""
    antwort = angemeldet.post(f"/personen/{anna}/stichtage", headers=hx(),
                              data={"art": "jahrestag", "bezeichnung": "", **datum_in(3)})
    assert "Jahrestag in 3 Tagen" in zeile(antwort.text, "Anna Beispiel")
    assert re.search(r'id="karten"[^>]*hx-swap-oob="true"', antwort.text)
    assert re.search(r'id="listenkoerper"[^>]*hx-swap-oob="true"', antwort.text)
    assert re.search(r'id="seitenleiste"[^>]*hx-swap-oob="true"', antwort.text)


# ----------------------------------------------------- Mehrere Nutzer, 404

def test_fremde_personen_sind_ueberall_404(angemeldet, con, fremder):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    for methode, pfad in (("post", f"/personen/{fremde}/angehoerige"),
                          ("post", f"/personen/{fremde}/stichtage"),
                          ("get", f"/personen/{fremde}/kandidaten?suche=x")):
        assert getattr(angemeldet, methode)(pfad, headers=hx()).status_code == 404, pfad
    assert angemeldet.get(f"/?person={fremde}").status_code == 404


def test_fremde_eintraege_sind_ueberall_404(angemeldet, con, nid, fremder, anna):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    aid = angehoerige.anlegen(con, fremder, fremde, name="Mia", rolle="kind")
    sid = stichtage.anlegen(con, fremder, fremde, bezeichnung="x", art="jahrestag",
                            datum="--05-05")
    daten = {"name": "x", "rolle": "kind", "art": "jahrestag", "tag": "1", "monat": "1",
             "verknuepfte_person_id": str(anna)}
    for methode, pfad in (("get", f"/angehoerige/{aid}"), ("get", f"/angehoerige/{aid}/bearbeiten"),
                          ("post", f"/angehoerige/{aid}"), ("post", f"/angehoerige/{aid}/loeschen"),
                          ("post", f"/angehoerige/{aid}/verknuepfen"),
                          ("post", f"/angehoerige/{aid}/entknuepfen"),
                          ("get", f"/stichtage/{sid}"), ("get", f"/stichtage/{sid}/bearbeiten"),
                          ("post", f"/stichtage/{sid}"), ("post", f"/stichtage/{sid}/loeschen")):
        antwort = (angemeldet.get(pfad, headers=hx()) if methode == "get"
                   else angemeldet.post(pfad, headers=hx(), data=daten))
        assert antwort.status_code == 404, pfad
    assert angehoerige.laden(con, fremder, aid) is not None
    assert stichtage.laden(con, fremder, sid) is not None


def test_eine_fremde_person_laesst_sich_nicht_verknuepfen(angemeldet, con, nid, fremder, anna):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    aid = angehoerige.anlegen(con, nid, anna, name="Zoe", rolle="partner")
    antwort = angemeldet.post(f"/angehoerige/{aid}/verknuepfen", headers=hx(),
                              data={"verknuepfte_person_id": str(fremde)})
    assert antwort.status_code == 404
    antwort = angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(),
                              data={"name": "Zoe", "rolle": "partner",
                                    "verknuepfte_person_id": str(fremde)})
    assert antwort.status_code == 404
    assert angehoerige.liste(con, fremder, fremde) == []
    assert [z["verknuepfte_person_id"] for z in angehoerige.liste(con, nid, anna)] == [None]


def test_stichtage_des_anderen_nutzers_erscheinen_nicht(angemeldet, con, nid, fremder, anna):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    stichtage.anlegen(con, fremder, fremde, bezeichnung="x", art="jahrestag", datum="--11-12")
    text = angemeldet.get("/").text
    assert "Zoe" not in text
    assert karten(text)["Diese Woche"] == 0


def test_ohne_anmeldung_geht_nichts(client, anna):
    for methode, pfad in (("post", f"/personen/{anna}/angehoerige"),
                          ("post", f"/personen/{anna}/stichtage"),
                          ("get", "/angehoerige/1"), ("get", "/stichtage/1"),
                          ("get", f"/personen/{anna}/kandidaten")):
        assert getattr(client, methode)(pfad).status_code == 303, pfad


def test_teile_ohne_htmx_leiten_auf_die_seite(angemeldet, con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="x", art="jahrestag", datum="--05-05")
    for pfad in (f"/angehoerige/{aid}", f"/angehoerige/{aid}/bearbeiten",
                 f"/stichtage/{sid}", f"/stichtage/{sid}/bearbeiten"):
        antwort = angemeldet.get(pfad)
        assert antwort.status_code == 303 and antwort.headers["location"] == f"/?person={anna}"


def test_umlaute_und_html_in_namen_werden_maskiert(angemeldet, con, nid, anna):
    angemeldet.post(f"/personen/{anna}/angehoerige", headers=hx(),
                    data={"name": "<b>Ürsula</b>", "rolle": "sonstiges",
                          "rolle_text": "<script>x</script>"})
    text = angemeldet.get(f"/?person={anna}").text
    assert "<b>Ürsula</b>" not in text and "&lt;b&gt;Ürsula&lt;/b&gt;" in text
    assert "<script>x</script>" not in text
