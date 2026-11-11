"""Angehoerige als Funktionen auf der Datenbank (ohne Web).

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import angehoerige, auth, personen, stichtage
from bindung.personen import EingabeFehler, NichtGefunden

from .conftest import PASSWORT


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


def eintrag(con, nid, aid):
    return angehoerige.laden(con, nid, aid)


def stichtage_von(con, person_id):
    return con.execute("SELECT * FROM stichtag WHERE person_id = ? ORDER BY id",
                       (person_id,)).fetchall()


def zeilen(con, tabelle="angehoeriger") -> int:
    return con.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0]


# ------------------------------------------------------------ Rollen

def test_jede_rolle_hat_ein_wort_und_eine_umgekehrte():
    assert set(angehoerige.ROLLEN) == set(angehoerige.INVERSE)
    assert angehoerige.ROLLEN == {
        "partner": "Partner/in", "kind": "Kind", "elternteil": "Elternteil",
        "geschwister": "Geschwister", "sonstiges": "Sonstiges"}


@pytest.mark.parametrize(("rolle", "umgekehrt"), [
    ("partner", "partner"), ("kind", "elternteil"), ("elternteil", "kind"),
    ("geschwister", "geschwister"), ("sonstiges", "sonstiges"),
])
def test_die_verknuepfung_legt_die_umgekehrte_rolle_an(con, nid, anna, ben, rolle, umgekehrt):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle=rolle)
    gegen = angehoerige.verknuepfen(con, nid, aid, ben)
    original, spiegel = eintrag(con, nid, aid), eintrag(con, nid, gegen)
    assert spiegel["rolle"] == umgekehrt
    assert spiegel["person_id"] == ben
    assert spiegel["name"] == "Anna Beispiel"
    assert (original["verknuepfte_person_id"], original["gegenstueck_id"]) == (ben, gegen)
    assert (spiegel["verknuepfte_person_id"], spiegel["gegenstueck_id"]) == (anna, aid)


def test_sonstiges_nimmt_den_freitext_mit(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="sonstiges",
                              rolle_text="Patenkind")
    gegen = angehoerige.verknuepfen(con, nid, aid, ben)
    assert eintrag(con, nid, gegen)["rolle_text"] == "Patenkind"
    assert angehoerige.rolle_wort(eintrag(con, nid, aid)) == "Patenkind"


def test_der_freitext_gehoert_nur_zu_sonstiges(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", rolle_text="Tochter")
    assert eintrag(con, nid, aid)["rolle_text"] is None
    angehoerige.aendern(con, nid, aid, rolle="sonstiges", rolle_text="Nichte")
    assert eintrag(con, nid, aid)["rolle_text"] == "Nichte"
    angehoerige.aendern(con, nid, aid, rolle="geschwister")
    assert eintrag(con, nid, aid)["rolle_text"] is None


def test_rolle_wort(con, nid, anna):
    kind = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    leer = angehoerige.anlegen(con, nid, anna, name="X", rolle="sonstiges")
    assert angehoerige.rolle_wort(eintrag(con, nid, kind)) == "Kind"
    assert angehoerige.rolle_wort(eintrag(con, nid, leer)) == "Sonstiges"


# ------------------------------------------------------------ Anlegen

def test_anlegen_ohne_geburtstag_und_ohne_verknuepfung(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="  Mia ", rolle="kind")
    zeile = eintrag(con, nid, aid)
    assert (zeile["person_id"], zeile["name"], zeile["rolle"], zeile["geburtstag"],
            zeile["verknuepfte_person_id"], zeile["gegenstueck_id"]) == (
        anna, "Mia", "kind", None, None, None)
    assert stichtage_von(con, anna) == []


@pytest.mark.parametrize(("felder", "teil"), [
    ({"name": " ", "rolle": "kind"}, "Name"),
    ({"name": None, "rolle": "kind"}, "Name"),
    ({"name": "Mia", "rolle": ""}, "Rolle"),
    ({"name": "Mia", "rolle": "freund"}, "Rolle"),
    ({"name": "Mia", "rolle": "kind", "geburtstag": "--02-30"}, "gibt es nicht"),
    ({"name": "Mia", "rolle": "kind", "geburtstag": "2999-01-01"}, "Zukunft"),
])
def test_anlegen_lehnt_ab(con, nid, anna, felder, teil):
    with pytest.raises(EingabeFehler, match=teil):
        angehoerige.anlegen(con, nid, anna, **felder)
    assert zeilen(con) == 0


def test_anlegen_bei_fremder_person(con, nid, anna, fremder):
    with pytest.raises(NichtGefunden):
        angehoerige.anlegen(con, fremder, anna, name="Mia", rolle="kind")
    assert zeilen(con) == 0


def test_anlegen_mit_verknuepfung_in_einem_schritt(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    zeile = eintrag(con, nid, aid)
    assert zeile["verknuepfte_person_id"] == ben
    assert zeile["verknuepft_name"] == "Ben Muster"
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert (gegen["rolle"], gegen["name"], gegen["gegenstueck_id"]) == (
        "partner", "Anna Beispiel", aid)


def test_ohne_namen_gilt_beim_verknuepfen_der_name_der_person(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="", rolle="geschwister",
                              verknuepfte_person_id=ben)
    assert eintrag(con, nid, aid)["name"] == "Ben Muster"


def test_ohne_namen_und_ohne_verknuepfung_geht_es_nicht(con, nid, anna):
    with pytest.raises(EingabeFehler, match="Name"):
        angehoerige.anlegen(con, nid, anna, name="", rolle="geschwister")


def test_anlegen_mit_fremder_person_als_ziel_legt_nichts_an(con, nid, anna, fremder):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    with pytest.raises(NichtGefunden):
        angehoerige.anlegen(con, nid, anna, name="Zoe", rolle="partner",
                            verknuepfte_person_id=fremde)
    assert zeilen(con) == 0


def test_anlegen_mit_sich_selbst_legt_nichts_an(con, nid, anna):
    with pytest.raises(EingabeFehler, match="mit sich selbst"):
        angehoerige.anlegen(con, nid, anna, name="Ich", rolle="partner",
                            verknuepfte_person_id=anna)
    assert zeilen(con) == 0


def test_liste_in_der_reihenfolge_des_eintragens(con, nid, anna):
    erst = angehoerige.anlegen(con, nid, anna, name="Zora", rolle="kind")
    dann = angehoerige.anlegen(con, nid, anna, name="Alex", rolle="partner")
    assert [z["id"] for z in angehoerige.liste(con, nid, anna)] == [erst, dann]


def test_liste_einer_fremden_person(con, nid, anna, fremder):
    with pytest.raises(NichtGefunden):
        angehoerige.liste(con, fremder, anna)


# ---------------------------------------------------------- Geburtstag

def test_ein_geburtstag_wird_ein_stichtag_der_person(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="2019-04-04")
    (s,) = stichtage_von(con, anna)
    assert (s["bezeichnung"], s["art"], s["datum"], s["angehoeriger_id"], s["vorlauf_tage"],
            s["person_id"]) == ("Geburtstag Mia", "geburtstag", "2019-04-04", aid, None, anna)


def test_der_geburtstag_ohne_jahr(con, nid, anna):
    angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--04-04")
    assert stichtage_von(con, anna)[0]["datum"] == "--04-04"


def test_aendern_zieht_den_stichtag_mit(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="2019-04-04")
    angehoerige.aendern(con, nid, aid, name="Mia Maria")
    (s,) = stichtage_von(con, anna)
    assert (s["bezeichnung"], s["datum"]) == ("Geburtstag Mia Maria", "2019-04-04")
    angehoerige.aendern(con, nid, aid, geburtstag="2019-05-05")
    (s,) = stichtage_von(con, anna)
    assert (s["bezeichnung"], s["datum"]) == ("Geburtstag Mia Maria", "2019-05-05")


def test_ein_geburtstag_nachtraeglich_und_wieder_weg(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    assert stichtage_von(con, anna) == []
    angehoerige.aendern(con, nid, aid, geburtstag="--04-04")
    assert len(stichtage_von(con, anna)) == 1
    angehoerige.aendern(con, nid, aid, geburtstag="")
    assert stichtage_von(con, anna) == []
    assert eintrag(con, nid, aid)["geburtstag"] is None


def test_andere_aenderungen_lassen_den_geburtstag_stehen(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--04-04")
    angehoerige.aendern(con, nid, aid, rolle="geschwister")
    assert len(stichtage_von(con, anna)) == 1


def test_loeschen_nimmt_den_stichtag_mit(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--04-04")
    assert angehoerige.loeschen(con, nid, aid) == anna
    assert stichtage_von(con, anna) == []
    assert zeilen(con) == 0


def test_ein_abgelehnter_geburtstag_aendert_nichts(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--04-04")
    with pytest.raises(EingabeFehler):
        angehoerige.aendern(con, nid, aid, name="Neu", geburtstag="--02-30")
    assert eintrag(con, nid, aid)["name"] == "Mia"
    assert stichtage_von(con, anna)[0]["bezeichnung"] == "Geburtstag Mia"


def test_der_geburtstag_kommt_in_den_vorlauf_der_person(con, nid, anna):
    angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="2019-11-14")
    (v,) = stichtage.im_vorlauf(con, nid)
    assert (v.person_id, v.angehoeriger_id is not None, v.tage, v.jahre_text) == (
        anna, True, 3, "wird 7")
    assert v.plakette_text == "Geburtstag Mia in 3 Tagen"


def test_der_geburtstag_wird_beim_verknuepfen_nicht_verdoppelt(con, nid, anna, ben):
    """Hat Ben einen eigenen Geburtstag, bleibt der von Annas Eintrag trotzdem Annas Stichtag."""
    stichtage.anlegen(con, nid, ben, bezeichnung="", art="geburtstag", datum="1990-06-06")
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              geburtstag="1990-06-06", verknuepfte_person_id=ben)
    assert [(s["person_id"], s["angehoeriger_id"]) for s in stichtage_von(con, anna)] == [
        (anna, aid)]
    assert [(s["person_id"], s["angehoeriger_id"]) for s in stichtage_von(con, ben)] == [
        (ben, None)]
    # Das Gegenstueck bekommt keinen Geburtstag dazu.
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert gegen["geburtstag"] is None


# ------------------------------------------------------------ Aendern

def test_aendern_setzt_nur_die_genannten_felder(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind", geburtstag="--04-04")
    angehoerige.aendern(con, nid, aid, name="Mia Neu")
    zeile = eintrag(con, nid, aid)
    assert (zeile["name"], zeile["rolle"], zeile["geburtstag"]) == ("Mia Neu", "kind", "--04-04")


def test_aendern_lehnt_ab(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    with pytest.raises(EingabeFehler, match="Name"):
        angehoerige.aendern(con, nid, aid, name=" ")
    with pytest.raises(EingabeFehler, match="Rolle"):
        angehoerige.aendern(con, nid, aid, rolle="freund")
    with pytest.raises(ValueError, match="Unbekannte Felder"):
        angehoerige.aendern(con, nid, aid, farbe="rot")
    assert angehoerige.aendern(con, nid, aid) is None
    assert eintrag(con, nid, aid)["name"] == "Mia"


def test_die_rolle_des_gegenstuecks_ist_eigenstaendig(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind",
                              verknuepfte_person_id=ben)
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert gegen["rolle"] == "elternteil"
    angehoerige.aendern(con, nid, gegen["id"], rolle="sonstiges", rolle_text="Stiefmutter",
                        name="Anna B.")
    assert eintrag(con, nid, aid)["rolle"] == "kind"
    assert eintrag(con, nid, aid)["name"] == "Ben"
    nachher = eintrag(con, nid, gegen["id"])
    assert (nachher["rolle"], nachher["rolle_text"], nachher["name"]) == (
        "sonstiges", "Stiefmutter", "Anna B.")
    # Die Verknuepfung selbst bleibt.
    assert (nachher["gegenstueck_id"], eintrag(con, nid, aid)["gegenstueck_id"]) == (
        aid, gegen["id"])


def test_aendern_des_originals_laesst_das_gegenstueck_in_ruhe(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind",
                              verknuepfte_person_id=ben)
    angehoerige.aendern(con, nid, aid, rolle="geschwister", name="Benni")
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert (gegen["rolle"], gegen["name"]) == ("elternteil", "Anna Beispiel")


# --------------------------------------------------------- Verknuepfen

def test_verknuepfen_nachtraeglich(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner")
    gegen = angehoerige.verknuepfen(con, nid, aid, ben)
    assert eintrag(con, nid, aid)["verknuepft_name"] == "Ben Muster"
    assert eintrag(con, nid, gegen)["verknuepft_name"] == "Anna Beispiel"
    assert zeilen(con) == 2


def test_eine_person_laesst_sich_nicht_mit_sich_selbst_verknuepfen(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Ich", rolle="partner")
    with pytest.raises(EingabeFehler, match="mit sich selbst"):
        angehoerige.verknuepfen(con, nid, aid, anna)
    assert eintrag(con, nid, aid)["verknuepfte_person_id"] is None
    assert zeilen(con) == 1


def test_ein_schon_verknuepfter_eintrag_wird_abgelehnt(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner")
    angehoerige.verknuepfen(con, nid, aid, ben)
    with pytest.raises(EingabeFehler, match="schon mit Ben Muster verknüpft"):
        angehoerige.verknuepfen(con, nid, aid, ben)
    cora = personen.anlegen(con, nid, "Cora Probe")
    with pytest.raises(EingabeFehler, match="schon mit Ben Muster verknüpft"):
        angehoerige.verknuepfen(con, nid, aid, cora)
    assert zeilen(con) == 2


def test_auch_das_gegenstueck_ist_schon_verknuepft(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner")
    gegen = angehoerige.verknuepfen(con, nid, aid, ben)
    cora = personen.anlegen(con, nid, "Cora Probe")
    with pytest.raises(EingabeFehler, match="schon mit Anna Beispiel verknüpft"):
        angehoerige.verknuepfen(con, nid, gegen, cora)


def test_verknuepfen_mit_fremder_person_oder_fremdem_eintrag(con, nid, anna, fremder):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    aid = angehoerige.anlegen(con, nid, anna, name="Zoe", rolle="partner")
    with pytest.raises(NichtGefunden):
        angehoerige.verknuepfen(con, nid, aid, fremde)
    with pytest.raises(NichtGefunden):
        angehoerige.verknuepfen(con, fremder, aid, fremde)
    with pytest.raises(NichtGefunden):
        angehoerige.verknuepfen(con, nid, aid, 99999)
    assert zeilen(con) == 1


def test_zwei_eintraege_duerfen_dieselbe_person_meinen(con, nid, anna, ben):
    """Ein Geschwister, das auch Geschaeftspartner ist: zwei Eintraege, zwei Gegenstuecke."""
    erst = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="geschwister")
    dann = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="sonstiges",
                               rolle_text="Kompagnon")
    angehoerige.verknuepfen(con, nid, erst, ben)
    angehoerige.verknuepfen(con, nid, dann, ben)
    assert len(angehoerige.liste(con, nid, ben)) == 2


def test_verknuepfbare_suchen_ohne_die_person_selbst(con, nid, anna, ben):
    personen.anlegen(con, nid, "Anne Probe")
    personen.archivieren(con, nid, personen.anlegen(con, nid, "Anton Alt"))
    treffer, mehr = angehoerige.verknuepfbare(con, nid, anna, "an")
    assert [p["name"] for p in treffer] == ["Anne Probe"]       # nicht Anna, nicht Anton (Archiv)
    assert mehr is False
    assert angehoerige.verknuepfbare(con, nid, anna, "  ") == ([], False)
    assert angehoerige.verknuepfbare(con, nid, anna, "zzz") == ([], False)


def test_verknuepfbare_begrenzt_die_treffer(con, nid, anna):
    for i in range(angehoerige.TREFFER_HOECHSTENS + 2):
        personen.anlegen(con, nid, f"Person {i:02d}")
    treffer, mehr = angehoerige.verknuepfbare(con, nid, anna, "Person")
    assert len(treffer) == angehoerige.TREFFER_HOECHSTENS
    assert mehr is True


def test_verknuepfbare_sieht_nur_eigene_personen(con, nid, anna, fremder):
    personen.anlegen(con, fremder, "Zoe Fremd")
    assert angehoerige.verknuepfbare(con, nid, anna, "Zoe") == ([], False)


# --------------------------------------------------------- Entknuepfen

def test_entknuepfen_entfernt_das_gegenstueck(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    angehoerige.entknuepfen(con, nid, aid)
    zeile = eintrag(con, nid, aid)
    assert (zeile["verknuepfte_person_id"], zeile["gegenstueck_id"], zeile["name"]) == (
        None, None, "Ben")
    assert angehoerige.liste(con, nid, ben) == []
    assert zeilen(con) == 1


def test_entknuepfen_vom_gegenstueck_aus_laesst_dessen_seite_stehen(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    (gegen,) = angehoerige.liste(con, nid, ben)
    angehoerige.entknuepfen(con, nid, gegen["id"])
    assert eintrag(con, nid, gegen["id"])["verknuepfte_person_id"] is None
    assert eintrag(con, nid, aid) is None          # das Gegenstueck des Gegenstuecks geht
    assert zeilen(con) == 1


def test_entknuepfen_nimmt_den_geburtstag_des_gegenstuecks_mit(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    (gegen,) = angehoerige.liste(con, nid, ben)
    angehoerige.aendern(con, nid, gegen["id"], geburtstag="--01-01")
    assert len(stichtage_von(con, ben)) == 1
    angehoerige.entknuepfen(con, nid, aid)
    assert stichtage_von(con, ben) == []


def test_entknuepfen_ohne_verknuepfung(con, nid, anna):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    with pytest.raises(EingabeFehler, match="nicht verknüpft"):
        angehoerige.entknuepfen(con, nid, aid)


def test_nach_dem_entknuepfen_geht_es_von_neuem(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    angehoerige.entknuepfen(con, nid, aid)
    angehoerige.verknuepfen(con, nid, aid, ben)
    assert len(angehoerige.liste(con, nid, ben)) == 1


def test_entknuepfen_eines_fremden_eintrags(con, nid, anna, ben, fremder):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    with pytest.raises(NichtGefunden):
        angehoerige.entknuepfen(con, fremder, aid)
    assert eintrag(con, nid, aid)["verknuepfte_person_id"] == ben


# ------------------------------------------------------------ Loeschen

def test_loeschen_entfernt_auch_das_gegenstueck(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind", geburtstag="--04-04",
                              verknuepfte_person_id=ben)
    assert angehoerige.loeschen(con, nid, aid) == anna
    assert zeilen(con) == 0
    assert zeilen(con, "stichtag") == 0


def test_loeschen_des_gegenstuecks_entfernt_auch_das_original(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="kind", geburtstag="--04-04",
                              verknuepfte_person_id=ben)
    (gegen,) = angehoerige.liste(con, nid, ben)
    assert angehoerige.loeschen(con, nid, gegen["id"]) == ben
    assert eintrag(con, nid, aid) is None
    assert zeilen(con) == 0
    assert zeilen(con, "stichtag") == 0


def test_loeschen_eines_einfachen_eintrags_laesst_die_anderen(con, nid, anna, ben):
    verknuepft = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                                     verknuepfte_person_id=ben)
    einfach = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    angehoerige.loeschen(con, nid, einfach)
    assert eintrag(con, nid, verknuepft) is not None
    assert zeilen(con) == 2


def test_loeschen_eines_fremden_eintrags(con, nid, anna, fremder):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    with pytest.raises(NichtGefunden):
        angehoerige.loeschen(con, fremder, aid)
    assert eintrag(con, nid, aid) is not None


def test_ein_fremder_eintrag_ist_nicht_zu_laden(con, nid, anna, fremder):
    aid = angehoerige.anlegen(con, nid, anna, name="Mia", rolle="kind")
    assert angehoerige.laden(con, fremder, aid) is None
    with pytest.raises(NichtGefunden):
        angehoerige.aendern(con, fremder, aid, name="X")


def test_das_archivieren_der_verknuepften_person_laesst_die_verknuepfung(con, nid, anna, ben):
    aid = angehoerige.anlegen(con, nid, anna, name="Ben", rolle="partner",
                              verknuepfte_person_id=ben)
    personen.archivieren(con, nid, ben)
    zeile = eintrag(con, nid, aid)
    assert zeile["verknuepfte_person_id"] == ben
    assert zeile["verknuepft_archiviert"] == 1
