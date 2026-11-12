"""Kontakte als Funktionen auf der Datenbank (ohne Web)."""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import auth, kontakte, personen

from .conftest import PASSWORT


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    """Mittwoch, 11. November 2026, 12:00 UTC."""
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC))


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def anna(con, nid) -> int:
    return personen.anlegen(con, nid, "Anna Beispiel")


@pytest.fixture
def fremder(con) -> int:
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


def test_eintragen_und_lesen(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="anruf",
                             notiz="  Plant den Umzug.  ")
    zeile = kontakte.laden(con, nid, kid)
    assert (zeile["datum"], zeile["art"], zeile["notiz"]) == ("2026-11-10", "anruf",
                                                              "Plant den Umzug.")


def test_leere_notiz_wird_zu_none(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="treffen", notiz="   ")
    assert kontakte.laden(con, nid, kid)["notiz"] is None


def test_datum_als_date_geht_auch(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum=dt.date(2026, 11, 1), art="email")
    assert kontakte.laden(con, nid, kid)["datum"] == "2026-11-01"


def test_heute_ist_erlaubt_morgen_nicht(con, nid, anna):
    kontakte.eintragen(con, nid, anna, datum="2026-11-11", art="anruf")
    with pytest.raises(personen.EingabeFehler, match="Zukunft"):
        kontakte.eintragen(con, nid, anna, datum="2026-11-12", art="anruf")
    assert len(kontakte.liste(con, nid, anna)) == 1


def test_heute_ist_der_tag_in_der_zeitzone_des_nutzers(con, nid, anna, monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 23, 30, tzinfo=dt.UTC))
    # in Berlin ist es schon der 12. November
    kontakte.eintragen(con, nid, anna, datum="2026-11-12", art="anruf")


@pytest.mark.parametrize("datum", ["", "gestern", "2026-13-01", "11.11.2026"])
def test_kaputtes_datum_wird_abgelehnt(con, nid, anna, datum):
    with pytest.raises(personen.EingabeFehler, match="ungültig"):
        kontakte.eintragen(con, nid, anna, datum=datum, art="anruf")


@pytest.mark.parametrize("art", ["", "schaetzung", "telepathie"])
def test_art_muss_eine_der_fuenf_sein(con, nid, anna, art):
    with pytest.raises(personen.EingabeFehler):
        kontakte.eintragen(con, nid, anna, datum="2026-11-10", art=art)


def test_eintragen_loescht_den_naechsten_termin(con, nid):
    p = personen.anlegen(con, nid, "Ben Muster", naechster_termin="2026-12-24",
                         intervall_tage=30)
    kontakte.eintragen(con, nid, p, datum="2026-11-10", art="anruf")
    zeile = personen.laden(con, nid, p)
    assert zeile["naechster_termin"] is None
    assert zeile["intervall_tage"] == 30  # nur der Termin geht


def test_ein_abgelehnter_kontakt_laesst_den_termin_stehen(con, nid):
    p = personen.anlegen(con, nid, "Ben Muster", naechster_termin="2026-12-24")
    with pytest.raises(personen.EingabeFehler):
        kontakte.eintragen(con, nid, p, datum="2030-01-01", art="anruf")
    assert personen.laden(con, nid, p)["naechster_termin"] == "2026-12-24"


def test_liste_juengster_zuerst_bei_gleichem_tag_der_spaetere_eintrag(con, nid, anna):
    kontakte.eintragen(con, nid, anna, datum="2026-10-01", art="anruf", notiz="alt")
    zweiter = kontakte.eintragen(con, nid, anna, datum="2026-11-01", art="anruf", notiz="a")
    dritter = kontakte.eintragen(con, nid, anna, datum="2026-11-01", art="treffen", notiz="b")
    reihe = kontakte.liste(con, nid, anna)
    assert [z["id"] for z in reihe][:2] == [dritter, zweiter]
    assert reihe[-1]["notiz"] == "alt"


def test_letzter_kontakt(con, nid, anna):
    assert kontakte.letzter_kontakt(con, nid, anna) is None
    kontakte.eintragen(con, nid, anna, datum="2026-10-01", art="anruf")
    kontakte.eintragen(con, nid, anna, datum="2026-11-01", art="anruf")
    kontakte.eintragen(con, nid, anna, datum="2026-09-01", art="anruf")
    assert kontakte.letzter_kontakt(con, nid, anna) == dt.date(2026, 11, 1)


def test_aendern(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="anruf", notiz="a")
    kontakte.aendern(con, nid, kid, art="treffen", notiz="")
    zeile = kontakte.laden(con, nid, kid)
    assert (zeile["datum"], zeile["art"], zeile["notiz"]) == ("2026-11-10", "treffen", None)
    kontakte.aendern(con, nid, kid, datum="2026-11-01")
    assert kontakte.laden(con, nid, kid)["datum"] == "2026-11-01"
    with pytest.raises(personen.EingabeFehler, match="Zukunft"):
        kontakte.aendern(con, nid, kid, datum="2026-11-20")


def test_aendern_laesst_den_naechsten_termin_in_ruhe(con, nid):
    p = personen.anlegen(con, nid, "Ben Muster")
    kid = kontakte.eintragen(con, nid, p, datum="2026-11-10", art="anruf")
    personen.aendern(con, nid, p, naechster_termin="2026-12-24")
    kontakte.aendern(con, nid, kid, notiz="nachgetragen")
    assert personen.laden(con, nid, p)["naechster_termin"] == "2026-12-24"


def test_eine_schaetzung_hat_nur_ein_datum(con, nid):
    ids = personen.mehrere_hinzufuegen(con, nid, "Cem Probe", grober_kontakt="vor_monaten")
    kid = kontakte.liste(con, nid, ids[0])[0]["id"]
    kontakte.aendern(con, nid, kid, datum="2026-06-01")
    assert kontakte.laden(con, nid, kid)["datum"] == "2026-06-01"
    with pytest.raises(personen.EingabeFehler, match="Schätzung"):
        kontakte.aendern(con, nid, kid, notiz="Ich war dabei")
    with pytest.raises(personen.EingabeFehler, match="Schätzung"):
        kontakte.aendern(con, nid, kid, art="anruf")


def test_art_laesst_sich_nicht_zur_schaetzung_machen(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="anruf")
    with pytest.raises(personen.EingabeFehler):
        kontakte.aendern(con, nid, kid, art="schaetzung")


def test_unbekannte_felder_sind_ein_programmierfehler(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="anruf")
    with pytest.raises(ValueError):
        kontakte.aendern(con, nid, kid, person_id=3)


def test_loeschen_gibt_die_person_zurueck(con, nid, anna):
    kid = kontakte.eintragen(con, nid, anna, datum="2026-11-10", art="anruf")
    assert kontakte.loeschen(con, nid, kid) == anna
    assert kontakte.laden(con, nid, kid) is None
    assert kontakte.letzter_kontakt(con, nid, anna) is None


def test_letzte_notizen_und_mit_echtem_kontakt(con, nid):
    anna = personen.anlegen(con, nid, "Anna Beispiel")
    ben = personen.anlegen(con, nid, "Ben Muster")
    cem = personen.mehrere_hinzufuegen(con, nid, "Cem Probe", grober_kontakt="vor_monaten")[0]
    kontakte.eintragen(con, nid, anna, datum="2026-10-01", art="anruf", notiz="alt")
    kontakte.eintragen(con, nid, anna, datum="2026-11-01", art="anruf", notiz="neu")
    kontakte.eintragen(con, nid, anna, datum="2026-11-05", art="anruf")  # ohne Notiz
    assert kontakte.letzte_notizen(con, nid) == {anna: "neu"}
    assert kontakte.mit_echtem_kontakt(con, nid) == {anna}
    assert ben not in kontakte.mit_echtem_kontakt(con, nid)
    assert cem not in kontakte.mit_echtem_kontakt(con, nid)  # eine Schätzung zählt nicht


# --------------------------------------------------------- Nutzer-Trennung

def test_fremde_person_und_fremder_kontakt_gibt_es_nicht(con, nid, fremder):
    fremde_person = personen.anlegen(con, fremder, "Fremd Beispiel")
    fremder_kontakt = kontakte.eintragen(con, fremder, fremde_person, datum="2026-11-10",
                                         art="anruf", notiz="geheim")
    with pytest.raises(personen.NichtGefunden):
        kontakte.eintragen(con, nid, fremde_person, datum="2026-11-10", art="anruf")
    with pytest.raises(personen.NichtGefunden):
        kontakte.liste(con, nid, fremde_person)
    with pytest.raises(personen.NichtGefunden):
        kontakte.aendern(con, nid, fremder_kontakt, notiz="x")
    with pytest.raises(personen.NichtGefunden):
        kontakte.loeschen(con, nid, fremder_kontakt)
    assert kontakte.laden(con, nid, fremder_kontakt) is None
    assert kontakte.letzte_notizen(con, nid) == {}
    assert kontakte.laden(con, fremder, fremder_kontakt)["notiz"] == "geheim"


# ------------------------------------------------------------- Schaetzung

def test_schaetzung_eintragen_wie_mehrere_hinzufuegen(con, nid, anna):
    kontakt_id = kontakte.schaetzung_eintragen(con, nid, anna, "vor_monaten")
    zeile = kontakte.laden(con, nid, kontakt_id)
    assert (zeile["art"], zeile["datum"], zeile["notiz"]) == ("schaetzung", "2026-08-13", None)
    assert kontakte.mit_echtem_kontakt(con, nid) == set()


def test_schaetzung_loescht_den_naechsten_termin_nicht(con, nid, anna):
    personen.aendern(con, nid, anna, naechster_termin="2026-12-01")
    kontakte.schaetzung_eintragen(con, nid, anna, "diesen_monat")
    assert personen.laden(con, nid, anna)["naechster_termin"] == "2026-12-01"


def test_schaetzung_lehnt_ab(con, nid, anna):
    with pytest.raises(personen.EingabeFehler):
        kontakte.schaetzung_eintragen(con, nid, anna, "gestern")
    with pytest.raises(personen.NichtGefunden):
        kontakte.schaetzung_eintragen(con, nid, 9999, "vor_monaten")
    assert kontakte.liste(con, nid, anna) == []
