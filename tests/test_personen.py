"""Personen und Tags als Funktionen auf der Datenbank (ohne Web)."""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import auth, personen

from .conftest import PASSWORT


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def anderer(con) -> int:
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


def _namen(zeilen) -> list[str]:
    return [z["name"] for z in zeilen]


@pytest.fixture
def bekannte(con, nid) -> dict[str, int]:
    """Vier erfundene Personen, zwei Tags: Familie (Anna, Ben) und Arbeit (Ben, Cem)."""
    ids = {
        "anna": personen.anlegen(con, nid, "Anna Beispiel", firma="Firma Muster", ort="Köln"),
        "ben": personen.anlegen(con, nid, "ben muster", ort="Bonn"),
        "cem": personen.anlegen(con, nid, "Cem Probe", firma="Probe GmbH"),
        "ärztin": personen.anlegen(con, nid, "Ärztin Beispiel"),
    }
    familie = personen.tag_anlegen(con, nid, "Familie")
    arbeit = personen.tag_anlegen(con, nid, "Arbeit")
    personen.tags_setzen(con, nid, ids["anna"], {familie})
    personen.tags_setzen(con, nid, ids["ben"], {familie, arbeit})
    personen.tags_setzen(con, nid, ids["cem"], {arbeit})
    ids["familie"], ids["arbeit"] = familie, arbeit
    return ids


# ------------------------------------------------------------------ Person

def test_anlegen_und_laden_mit_allen_feldern(con, nid):
    pid = personen.anlegen(
        con, nid, "  Anna Beispiel ", firma="Firma Muster", rolle="Leitung", telefon="0170 1",
        email="anna@example.org", ort="Köln", herkunft="Studium", profilnotiz="Mag Tee.",
        intervall_tage="30", naechster_termin="2027-01-15")
    p = personen.laden(con, nid, pid)
    assert (p["name"], p["firma"], p["rolle"], p["telefon"]) == (
        "Anna Beispiel", "Firma Muster", "Leitung", "0170 1")
    assert (p["email"], p["ort"], p["herkunft"]) == ("anna@example.org", "Köln", "Studium")
    assert (p["profilnotiz"], p["intervall_tage"], p["naechster_termin"]) == (
        "Mag Tee.", 30, "2027-01-15")
    assert p["archiviert_am"] is None


def test_leere_felder_werden_null(con, nid):
    pid = personen.anlegen(con, nid, "Anna", firma="  ", intervall_tage="", naechster_termin="")
    p = personen.laden(con, nid, pid)
    assert p["firma"] is None and p["intervall_tage"] is None and p["naechster_termin"] is None


@pytest.mark.parametrize("name", ["", "   "])
def test_name_ist_pflicht(con, nid, name):
    with pytest.raises(personen.EingabeFehler, match="Name"):
        personen.anlegen(con, nid, name)


@pytest.mark.parametrize(("feld", "wert"), [
    ("intervall_tage", "abc"), ("intervall_tage", "0"), ("intervall_tage", "-5"),
    ("naechster_termin", "morgen"), ("naechster_termin", "2027-13-40"),
])
def test_ungueltige_werte_werden_abgelehnt(con, nid, feld, wert):
    pid = personen.anlegen(con, nid, "Anna")
    with pytest.raises(personen.EingabeFehler):
        personen.aendern(con, nid, pid, **{feld: wert})


def test_aendern_setzt_nur_die_genannten_felder(con, nid):
    pid = personen.anlegen(con, nid, "Anna", firma="Firma Muster", ort="Köln")
    personen.aendern(con, nid, pid, ort="Bonn")
    p = personen.laden(con, nid, pid)
    assert (p["firma"], p["ort"]) == ("Firma Muster", "Bonn")


def test_aendern_kann_felder_leeren(con, nid):
    pid = personen.anlegen(con, nid, "Anna", firma="Firma Muster", intervall_tage=30)
    personen.aendern(con, nid, pid, firma="", intervall_tage="")
    p = personen.laden(con, nid, pid)
    assert p["firma"] is None and p["intervall_tage"] is None


def test_aendern_mit_leerem_namen_aendert_nichts(con, nid):
    pid = personen.anlegen(con, nid, "Anna", firma="Firma Muster")
    with pytest.raises(personen.EingabeFehler):
        personen.aendern(con, nid, pid, name=" ", firma="Neu")
    p = personen.laden(con, nid, pid)
    assert (p["name"], p["firma"]) == ("Anna", "Firma Muster")


def test_unbekanntes_feld_ist_ein_programmierfehler(con, nid):
    pid = personen.anlegen(con, nid, "Anna")
    with pytest.raises(ValueError, match="Unbekannte Felder"):
        personen.aendern(con, nid, pid, haarfarbe="grau")


def test_archivieren_und_wiederherstellen(con, nid, bekannte):
    anna = bekannte["anna"]
    personen.archivieren(con, nid, anna)
    assert personen.laden(con, nid, anna)["archiviert_am"]
    assert "Anna Beispiel" not in _namen(personen.liste(con, nid))
    assert _namen(personen.liste(con, nid, archiviert=True)) == ["Anna Beispiel"]
    personen.wiederherstellen(con, nid, anna)
    assert personen.laden(con, nid, anna)["archiviert_am"] is None
    assert "Anna Beispiel" in _namen(personen.liste(con, nid))
    assert personen.liste(con, nid, archiviert=True) == []


def test_archivieren_behaelt_tags_und_kontakte(con, nid, bekannte):
    anna = bekannte["anna"]
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, "
                "'2026-10-01', 'anruf')", (nid, anna))
    personen.archivieren(con, nid, anna)
    personen.wiederherstellen(con, nid, anna)
    assert personen.tags_der_person(con, nid, anna) == {bekannte["familie"]}
    assert con.execute("SELECT COUNT(*) FROM kontakt WHERE person_id = ?",
                       (anna,)).fetchone()[0] == 1


def test_fremde_person_gibt_es_nicht(con, nid, anderer):
    fremd = personen.anlegen(con, anderer, "Fremd Beispiel")
    assert personen.laden(con, nid, fremd) is None
    for aufruf in (personen.archivieren, personen.wiederherstellen):
        with pytest.raises(personen.NichtGefunden):
            aufruf(con, nid, fremd)
    with pytest.raises(personen.NichtGefunden):
        personen.aendern(con, nid, fremd, name="Gekapert")
    assert personen.laden(con, anderer, fremd)["name"] == "Fremd Beispiel"


# ------------------------------------------------------------------- Liste

def test_liste_sortiert_nach_name_ohne_gross_klein_und_umlaut(con, nid, bekannte):
    assert _namen(personen.liste(con, nid)) == [
        "Anna Beispiel", "ben muster", "Cem Probe", "Ärztin Beispiel"]


def test_liste_nach_tag(con, nid, bekannte):
    assert _namen(personen.liste(con, nid, tag_id=bekannte["familie"])) == [
        "Anna Beispiel", "ben muster"]
    assert _namen(personen.liste(con, nid, tag_id=bekannte["arbeit"])) == [
        "ben muster", "Cem Probe"]


@pytest.mark.parametrize(("suche", "erwartet"), [
    ("anna", ["Anna Beispiel"]),
    ("ANNA", ["Anna Beispiel"]),
    ("beispiel", ["Anna Beispiel", "Ärztin Beispiel"]),
    ("muster", ["Anna Beispiel", "ben muster"]),          # Firma und Name
    ("köln", ["Anna Beispiel"]),                          # Ort
    ("KÖLN", ["Anna Beispiel"]),
    ("ärztin", ["Ärztin Beispiel"]),
    ("ÄRZTIN", ["Ärztin Beispiel"]),                      # Umlaute, nicht nur ASCII
    ("familie", ["Anna Beispiel", "ben muster"]),         # Name eines Tags
    ("arbe", ["ben muster", "Cem Probe"]),                # Teilstring eines Tags
    ("gibt es nicht", []),
    ("  anna  ", ["Anna Beispiel"]),
])
def test_suche_ist_teilstring_ohne_gross_klein(con, nid, bekannte, suche, erwartet):
    assert _namen(personen.liste(con, nid, suche=suche)) == erwartet


def test_suche_und_tag_zusammen(con, nid, bekannte):
    assert _namen(personen.liste(con, nid, tag_id=bekannte["arbeit"], suche="muster")) == [
        "ben muster"]


def test_suche_sieht_das_archiv_nur_im_archiv(con, nid, bekannte):
    personen.archivieren(con, nid, bekannte["anna"])
    assert personen.liste(con, nid, suche="anna") == []
    assert _namen(personen.liste(con, nid, suche="anna", archiviert=True)) == ["Anna Beispiel"]


def test_noch_kein_kontakt(con, nid, bekannte):
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, "
                "'2026-10-01', 'anruf')", (nid, bekannte["anna"]))
    assert _namen(personen.liste(con, nid, ohne_kontakt=True)) == [
        "ben muster", "Cem Probe", "Ärztin Beispiel"]


def test_zaehler(con, nid, bekannte):
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, "
                "'2026-10-01', 'anruf')", (nid, bekannte["anna"]))
    personen.archivieren(con, nid, bekannte["cem"])
    assert personen.zaehler(con, nid) == {"alle": 3, "ohne_kontakt": 2, "archiv": 1}


def test_zaehler_ohne_personen(con, nid):
    assert personen.zaehler(con, nid) == {"alle": 0, "ohne_kontakt": 0, "archiv": 0}


def test_liste_und_zaehler_zeigen_nur_die_eigenen(con, nid, anderer, bekannte):
    personen.anlegen(con, anderer, "Fremd Beispiel")
    assert "Fremd Beispiel" not in _namen(personen.liste(con, nid))
    assert _namen(personen.liste(con, anderer)) == ["Fremd Beispiel"]
    assert personen.zaehler(con, anderer)["alle"] == 1


# -------------------------------------------------------------------- Tags

def test_tag_ist_je_nutzer_einmalig_ohne_gross_klein(con, nid, anderer):
    personen.tag_anlegen(con, nid, "Familie")
    for doppelt in ("Familie", "familie", "FAMILIE", " Familie "):
        with pytest.raises(personen.EingabeFehler, match="gibt es schon"):
            personen.tag_anlegen(con, nid, doppelt)
    assert personen.tag_anlegen(con, anderer, "Familie")      # anderer Nutzer: erlaubt


def test_tag_einmalig_auch_mit_umlauten(con, nid):
    personen.tag_anlegen(con, nid, "Ärzte")
    with pytest.raises(personen.EingabeFehler):
        personen.tag_anlegen(con, nid, "ärzte")


def test_tag_braucht_einen_namen(con, nid):
    with pytest.raises(personen.EingabeFehler):
        personen.tag_anlegen(con, nid, "  ")


def test_tag_finden_oder_anlegen(con, nid):
    erster = personen.tag_finden_oder_anlegen(con, nid, "Nachbarn")
    assert personen.tag_finden_oder_anlegen(con, nid, "nachbarn") == erster
    assert len(personen.tags_mit_zaehlern(con, nid)) == 1


def test_umbenennen(con, nid):
    tag = personen.tag_anlegen(con, nid, "Familie")
    andere = personen.tag_anlegen(con, nid, "Arbeit")
    personen.tag_umbenennen(con, nid, tag, "Verwandte")
    personen.tag_umbenennen(con, nid, tag, "verwandte")        # nur die Schreibweise
    assert personen.tag_laden(con, nid, tag)["name"] == "verwandte"
    with pytest.raises(personen.EingabeFehler, match="gibt es schon"):
        personen.tag_umbenennen(con, nid, tag, "ARBEIT")
    assert personen.tag_laden(con, nid, andere)["name"] == "Arbeit"


def test_loeschen_loest_nur_die_zuordnung(con, nid, bekannte):
    personen.tag_loeschen(con, nid, bekannte["familie"])
    assert personen.tag_laden(con, nid, bekannte["familie"]) is None
    assert len(personen.liste(con, nid)) == 4
    assert personen.tags_der_person(con, nid, bekannte["ben"]) == {bekannte["arbeit"]}


def test_tags_setzen_ersetzt_die_tags(con, nid, bekannte):
    personen.tags_setzen(con, nid, bekannte["anna"], {bekannte["arbeit"]})
    assert personen.tags_der_person(con, nid, bekannte["anna"]) == {bekannte["arbeit"]}
    personen.tags_setzen(con, nid, bekannte["anna"], [])
    assert personen.tags_der_person(con, nid, bekannte["anna"]) == set()


def test_tags_mit_zaehlern_zaehlt_nur_aktive_in_der_reihenfolge_der_anlage(con, nid, bekannte):
    assert [(t["name"], t["anzahl"]) for t in personen.tags_mit_zaehlern(con, nid)] == [
        ("Familie", 2), ("Arbeit", 2)]
    personen.archivieren(con, nid, bekannte["ben"])
    assert [(t["name"], t["anzahl"]) for t in personen.tags_mit_zaehlern(con, nid)] == [
        ("Familie", 1), ("Arbeit", 1)]


def test_leerer_tag_hat_den_zaehler_null(con, nid):
    personen.tag_anlegen(con, nid, "Leer")
    assert personen.tags_mit_zaehlern(con, nid)[0]["anzahl"] == 0


def test_fremde_tags_gibt_es_nicht(con, nid, anderer):
    fremd = personen.tag_anlegen(con, anderer, "Fremd")
    eigen = personen.anlegen(con, nid, "Anna")
    assert personen.tag_laden(con, nid, fremd) is None
    with pytest.raises(personen.NichtGefunden):
        personen.tags_setzen(con, nid, eigen, {fremd})
    with pytest.raises(personen.NichtGefunden):
        personen.tag_umbenennen(con, nid, fremd, "Meiner")
    with pytest.raises(personen.NichtGefunden):
        personen.tag_loeschen(con, nid, fremd)
    assert personen.tags_mit_zaehlern(con, nid) == []
    assert personen.tag_laden(con, anderer, fremd)["name"] == "Fremd"


def test_fremde_person_bekommt_keine_tags(con, nid, anderer):
    tag = personen.tag_anlegen(con, nid, "Familie")
    fremd = personen.anlegen(con, anderer, "Fremd")
    with pytest.raises(personen.NichtGefunden):
        personen.tags_setzen(con, nid, fremd, {tag})


# ------------------------------------------------------ Mehrere hinzufuegen

@pytest.fixture
def stichtag(monkeypatch):
    """Die Uhr steht auf Mittwoch, 11. November 2026, 12:00 UTC."""
    monkeypatch.setattr(personen, "_jetzt", lambda: dt.datetime(2026, 11, 11, 12, 0,
                                                                tzinfo=dt.UTC))


def _kontakte(con, pid):
    return con.execute("SELECT datum, art, notiz FROM kontakt WHERE person_id = ?",
                       (pid,)).fetchall()


@pytest.mark.parametrize(("auswahl", "datum"), [
    ("diesen_monat", "2026-10-27"),        # heute minus 15
    ("vor_monaten", "2026-07-14"),         # minus 120
    ("ueber_ein_jahr", "2025-10-07"),      # minus 400
])
def test_mehrere_legt_eine_schaetzung_an(con, nid, stichtag, auswahl, datum):
    ids = personen.mehrere_hinzufuegen(con, nid, "Anna Beispiel\nBen Muster",
                                       grober_kontakt=auswahl)
    assert len(ids) == 2
    for pid in ids:
        kontakte = _kontakte(con, pid)
        assert [(k["datum"], k["art"], k["notiz"]) for k in kontakte] == [
            (datum, "schaetzung", None)]


def test_mehrere_unbekannt_legt_keinen_kontakt_an(con, nid):
    ids = personen.mehrere_hinzufuegen(con, nid, "Anna Beispiel", grober_kontakt="unbekannt")
    assert _kontakte(con, ids[0]) == []
    assert personen.zaehler(con, nid)["ohne_kontakt"] == 1


def test_mehrere_ohne_angabe_ist_unbekannt(con, nid):
    ids = personen.mehrere_hinzufuegen(con, nid, "Anna Beispiel")
    assert _kontakte(con, ids[0]) == []


def test_mehrere_nimmt_name_und_firma(con, nid):
    ids = personen.mehrere_hinzufuegen(
        con, nid, "Anna Beispiel; Firma Muster\nBen Muster ;\n  Cem Probe  ;  Probe GmbH ")
    assert [(personen.laden(con, nid, i)["name"], personen.laden(con, nid, i)["firma"])
            for i in ids] == [("Anna Beispiel", "Firma Muster"), ("Ben Muster", None),
                              ("Cem Probe", "Probe GmbH")]


def test_mehrere_ueberspringt_leere_zeilen_und_doppelte_namen(con, nid):
    ids = personen.mehrere_hinzufuegen(
        con, nid, "Anna Beispiel\n\n   \n;Firma ohne Name\nanna beispiel; Andere Firma\nBen Muster")
    assert [personen.laden(con, nid, i)["name"] for i in ids] == ["Anna Beispiel", "Ben Muster"]
    assert personen.laden(con, nid, ids[0])["firma"] is None     # die erste Zeile gilt


def test_mehrere_vergibt_die_tags(con, nid):
    familie = personen.tag_anlegen(con, nid, "Familie")
    arbeit = personen.tag_anlegen(con, nid, "Arbeit")
    ids = personen.mehrere_hinzufuegen(con, nid, "Anna\nBen", tag_ids={familie, arbeit})
    for pid in ids:
        assert personen.tags_der_person(con, nid, pid) == {familie, arbeit}


def test_mehrere_rechnet_in_der_zeit_des_nutzers(con, nid, monkeypatch):
    """Kurz nach Mitternacht in Berlin ist es in UTC noch der Vortag."""
    monkeypatch.setattr(personen, "_jetzt", lambda: dt.datetime(2026, 11, 10, 23, 30,
                                                                tzinfo=dt.UTC))
    ids = personen.mehrere_hinzufuegen(con, nid, "Anna", grober_kontakt="diesen_monat")
    assert _kontakte(con, ids[0])[0]["datum"] == "2026-10-27"       # Berlin: 11. November - 15
    con.execute("UPDATE nutzer SET zeitzone = 'America/Los_Angeles' WHERE id = ?", (nid,))
    ids = personen.mehrere_hinzufuegen(con, nid, "Ben", grober_kontakt="diesen_monat")
    assert _kontakte(con, ids[0])[0]["datum"] == "2026-10-26"       # Los Angeles: 10. November


@pytest.mark.parametrize("text", ["", "  \n \n", ";nur Firma"])
def test_mehrere_ohne_namen_ist_ein_fehler(con, nid, text):
    with pytest.raises(personen.EingabeFehler, match="mindestens einen Namen"):
        personen.mehrere_hinzufuegen(con, nid, text)


def test_mehrere_mit_falscher_auswahl_ist_ein_fehler(con, nid):
    with pytest.raises(personen.EingabeFehler):
        personen.mehrere_hinzufuegen(con, nid, "Anna", grober_kontakt="gestern")
    assert personen.liste(con, nid) == []


def test_mehrere_mit_fremdem_tag_legt_nichts_an(con, nid, anderer):
    fremd = personen.tag_anlegen(con, anderer, "Fremd")
    with pytest.raises(personen.NichtGefunden):
        personen.mehrere_hinzufuegen(con, nid, "Anna", tag_ids={fremd})
    assert personen.liste(con, nid) == []
