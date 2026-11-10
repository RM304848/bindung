"""Das Schema: alle Tabellen aus PLAN.md Abschnitt 5, Version, Fremdschluessel."""

from __future__ import annotations

import sqlite3

import pytest

from bindung import db, pfade

TABELLEN = {"nutzer", "sitzung", "person", "tag", "person_tag", "kontakt", "angehoeriger",
            "stichtag", "push_abo", "digest_protokoll", "schema_version"}

# Tabellen mit Nutzerdaten: alle ausser der Versionstabelle.
NUTZERTABELLEN = TABELLEN - {"nutzer", "schema_version"}


def _tabellen(con) -> set[str]:
    zeilen = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    return {z["name"] for z in zeilen}


def _spalten(con, tabelle: str) -> set[str]:
    return {z["name"] for z in con.execute(f"PRAGMA table_info({tabelle})")}


def test_frische_datenbank_hat_alle_tabellen(con):
    assert _tabellen(con) == TABELLEN


def test_frische_datenbank_steht_auf_der_aktuellen_version(con):
    assert db.version(con) == db.aktuelle_version() == 1


def test_datenbank_liegt_im_datenordner_des_tests(con, daten):
    assert pfade.DB_PATH.exists()
    assert daten in pfade.DB_PATH.parents


def test_zweites_verbinden_aendert_nichts(con):
    db.verbinden().close()
    assert db.version(con) == 1
    assert con.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1


def test_fremdschluessel_und_wal(con):
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


@pytest.mark.parametrize("tabelle", sorted(NUTZERTABELLEN))
def test_jede_tabelle_mit_nutzerdaten_traegt_nutzer_id(con, tabelle):
    assert "nutzer_id" in _spalten(con, tabelle)


def test_spalten_laut_plan(con):
    assert {"name", "passwort_hash", "tagesmeldung_zeit", "zeitzone", "vorgabe_intervall_tage",
            "vorgabe_vorlauf_tage", "kalender_token", "diktat_sprache"} <= _spalten(con, "nutzer")
    assert {"name", "firma", "rolle", "telefon", "email", "ort", "herkunft", "profilnotiz",
            "intervall_tage", "naechster_termin", "archiviert_am"} <= _spalten(con, "person")
    assert {"datum", "art", "notiz"} <= _spalten(con, "kontakt")
    assert {"name", "rolle", "geburtstag", "verknuepfte_person_id",
            "gegenstueck_id"} <= _spalten(con, "angehoeriger")
    assert {"bezeichnung", "art", "datum", "vorlauf_tage",
            "angehoeriger_id"} <= _spalten(con, "stichtag")


def test_vorgaben_des_nutzers(con):
    con.execute("INSERT INTO nutzer (name, passwort_hash, kalender_token) VALUES ('a', 'x', 't')")
    zeile = con.execute("SELECT * FROM nutzer").fetchone()
    assert zeile["tagesmeldung_zeit"] == "08:00"
    assert zeile["zeitzone"] == "Europe/Berlin"
    assert zeile["vorgabe_intervall_tage"] == 56
    assert zeile["vorgabe_vorlauf_tage"] == 7
    assert zeile["diktat_sprache"] == "de-DE"
    assert zeile["erstellt_am"].endswith("Z")


def test_kontaktart_wird_geprueft(con):
    con.execute("INSERT INTO nutzer (name, passwort_hash, kalender_token) VALUES ('a', 'x', 't')")
    con.execute("INSERT INTO person (nutzer_id, name) VALUES (1, 'Anna Beispiel')")
    for art in ("anruf", "nachricht", "email", "treffen", "sonstiges", "schaetzung"):
        con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) "
                    "VALUES (1, 1, '2026-01-01', ?)", (art,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) "
                    "VALUES (1, 1, '2026-01-01', 'brief')")


def test_nutzer_loeschen_nimmt_seine_daten_mit(con):
    con.execute("INSERT INTO nutzer (name, passwort_hash, kalender_token) VALUES ('a', 'x', 't')")
    con.execute("INSERT INTO person (nutzer_id, name) VALUES (1, 'Anna Beispiel')")
    con.execute("INSERT INTO tag (nutzer_id, name) VALUES (1, 'Familie')")
    con.execute("INSERT INTO person_tag (nutzer_id, person_id, tag_id) VALUES (1, 1, 1)")
    con.execute("DELETE FROM nutzer")
    for tabelle in ("person", "tag", "person_tag"):
        assert con.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0] == 0


def test_tagnamen_sind_je_nutzer_eindeutig_ohne_gross_klein(con):
    con.execute("INSERT INTO nutzer (name, passwort_hash, kalender_token) VALUES ('a', 'x', 't')")
    con.execute("INSERT INTO tag (nutzer_id, name) VALUES (1, 'Familie')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO tag (nutzer_id, name) VALUES (1, 'familie')")


def test_migrationen_werden_nachgespielt(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "MIGRATIONEN", ["ALTER TABLE person ADD COLUMN spitzname TEXT;"])
    con = db.verbinden(tmp_path / "m.db")
    assert db.version(con) == 2
    assert "spitzname" in _spalten(con, "person")
    con.close()
