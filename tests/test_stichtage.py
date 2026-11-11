"""Stichtage als Funktionen auf der Datenbank (ohne Web).

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import auth, personen, stichtage
from bindung.personen import EingabeFehler, NichtGefunden

from .conftest import PASSWORT

HEUTE = dt.date(2026, 11, 11)


def tag(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


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
def fremder(con) -> int:
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


def in_tagen(tage: int, jahr: int | None = None) -> str:
    """Ein Datum, das `tage` nach heute faellt; mit `jahr` ein Geburtsjahr dazu."""
    ziel = HEUTE + dt.timedelta(days=tage)
    rest = f"{ziel.month:02d}-{ziel.day:02d}"
    return f"{jahr:04d}-{rest}" if jahr else f"--{rest}"


# ------------------------------------------------------------------- Datum

@pytest.mark.parametrize(("eingabe", "erwartet"), [
    (("24", "3", None), "--03-24"),
    (("24", "3", ""), "--03-24"),
    ((" 24 ", " 03 ", " 1986 "), "1986-03-24"),
    ((1, 12, 2000), "2000-12-01"),
    (("29", "2", None), "--02-29"),        # ohne Jahr gibt es den Schalttag
    (("29", "2", "2000"), "2000-02-29"),
])
def test_bauen(eingabe, erwartet):
    assert stichtage.bauen(*eingabe) == erwartet


@pytest.mark.parametrize(("eingabe", "teil"), [
    (("", "3", None), "Tag und Monat"),
    (("24", "", None), "Tag und Monat"),
    (("abc", "3", None), "Tag ist eine Zahl"),
    (("24", "3", "abc"), "Jahr ist eine Zahl"),
    (("30", "2", None), "gibt es nicht"),
    (("29", "2", "2026"), "gibt es nicht"),     # 2026 ist kein Schaltjahr
    (("31", "4", None), "gibt es nicht"),
    (("1", "13", None), "gibt es nicht"),
    (("0", "1", None), "gibt es nicht"),
    (("1", "1", "1899"), "ab 1900"),
])
def test_bauen_lehnt_ab(eingabe, teil):
    with pytest.raises(EingabeFehler, match=teil):
        stichtage.bauen(*eingabe)


def test_ein_jahr_in_der_zukunft_wird_nur_mit_heute_abgelehnt():
    assert stichtage.bauen(1, 1, 2030) == "2030-01-01"
    with pytest.raises(EingabeFehler, match="Zukunft"):
        stichtage.bauen(1, 1, 2030, HEUTE)
    assert stichtage.bauen(1, 1, 2026, HEUTE) == "2026-01-01"


def test_bauen_oder_none_kennt_das_leere_datum():
    assert stichtage.bauen_oder_none("", "", "") is None
    assert stichtage.bauen_oder_none(None, None, None) is None
    with pytest.raises(EingabeFehler):
        stichtage.bauen_oder_none("1", "", "")     # halb ausgefuellt ist ein Fehler


@pytest.mark.parametrize("datum", ["1986-03-24", "--03-24", "--02-29", " 1986-03-24 "])
def test_pruefen_akzeptiert_beide_formen(datum):
    assert stichtage.pruefen(datum) == datum.strip()


@pytest.mark.parametrize("datum", ["", "24.03.1986", "1986-3-24", "1986-02-30", "--13-01",
                                   "--02-30", None])
def test_pruefen_lehnt_ab(datum):
    with pytest.raises(EingabeFehler):
        stichtage.pruefen(datum)


def test_text_de_mit_und_ohne_jahr():
    assert stichtage.text_de("--03-24") == "24. März"
    assert stichtage.text_de("1986-03-24") == "24. März 1986"
    assert stichtage.text_de("--12-01") == "1. Dezember"
    assert stichtage.text_de(None) == ""


def test_teile():
    assert stichtage.teile("1986-03-24") == (24, 3, 1986)
    assert stichtage.teile("--03-24") == (24, 3, None)
    with pytest.raises(ValueError, match="Kein Stichtag"):
        stichtage.teile("morgen")


# --------------------------------------------------- naechstes Vorkommen

@pytest.mark.parametrize(("datum", "heute", "erwartet"), [
    ("--11-11", "2026-11-11", "2026-11-11"),     # heute selbst zaehlt
    ("--11-12", "2026-11-11", "2026-11-12"),
    ("--11-10", "2026-11-11", "2027-11-10"),     # gestern: naechstes Jahr
    ("1986-03-24", "2026-11-11", "2027-03-24"),  # das Geburtsjahr spielt keine Rolle
    ("--01-01", "2026-12-31", "2027-01-01"),     # ueber den Jahreswechsel
    ("--12-31", "2026-12-31", "2026-12-31"),
    ("--12-31", "2027-01-01", "2027-12-31"),
    ("--01-01", "2027-01-01", "2027-01-01"),
    # 29. Februar: im Gemeinjahr der 28.
    ("--02-29", "2027-01-10", "2027-02-28"),
    ("--02-29", "2027-02-28", "2027-02-28"),
    ("--02-29", "2027-03-01", "2028-02-29"),     # das naechste ist ein Schaltjahr
    ("--02-29", "2028-01-01", "2028-02-29"),
    ("--02-29", "2028-02-29", "2028-02-29"),
    ("--02-29", "2028-03-01", "2029-02-28"),
    ("2000-02-29", "2026-11-11", "2027-02-28"),  # mit Jahr ebenso
])
def test_naechstes_vorkommen(datum, heute, erwartet):
    assert stichtage.naechstes_vorkommen(datum, tag(heute)) == tag(erwartet)


# ---------------------------------------------------------------- Worte

@pytest.mark.parametrize(("art", "jahre", "erwartet"), [
    ("geburtstag", 40, "wird 40"),
    ("geburtstag", 1, "wird 1"),
    ("jahrestag", 10, "10 Jahre"),
    ("sonstiges", 1, "1 Jahr"),
    ("geburtstag", None, ""),
    ("jahrestag", 0, ""),                  # das Jahr ist dieses: noch kein „Jahr“
    ("jahrestag", -1, ""),
])
def test_jahre_text(art, jahre, erwartet):
    assert stichtage.jahre_text(art, jahre) == erwartet


# ------------------------------------------------------- Anlegen, Aendern

def test_anlegen_und_lesen(con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="  Hochzeitstag ", art="jahrestag",
                            datum="2016-06-18", vorlauf_tage="14")
    zeile = stichtage.laden(con, nid, sid)
    assert (zeile["person_id"], zeile["bezeichnung"], zeile["art"], zeile["datum"],
            zeile["vorlauf_tage"], zeile["angehoeriger_id"]) == (
        anna, "Hochzeitstag", "jahrestag", "2016-06-18", 14, None)


def test_ohne_bezeichnung_gilt_das_wort_der_art(con, nid, anna):
    g = stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--03-24")
    j = stichtage.anlegen(con, nid, anna, bezeichnung=None, art="jahrestag", datum="--05-01")
    assert stichtage.laden(con, nid, g)["bezeichnung"] == "Geburtstag"
    assert stichtage.laden(con, nid, j)["bezeichnung"] == "Jahrestag"


def test_ein_sonstiger_stichtag_braucht_einen_namen(con, nid, anna):
    with pytest.raises(EingabeFehler, match="Namen"):
        stichtage.anlegen(con, nid, anna, bezeichnung=" ", art="sonstiges", datum="--05-01")


@pytest.mark.parametrize(("felder", "teil"), [
    ({"art": "feiertag"}, "was für ein Stichtag"),
    ({"art": ""}, "was für ein Stichtag"),
    ({"datum": "--02-30"}, "gibt es nicht"),
    ({"datum": ""}, "ungültig"),
    ({"datum": "2999-01-01"}, "Zukunft"),
    ({"vorlauf_tage": "x"}, "Zahl in Tagen"),
    ({"vorlauf_tage": "-1"}, "zwischen 0 und 365"),
    ({"vorlauf_tage": "366"}, "zwischen 0 und 365"),
])
def test_anlegen_lehnt_ab(con, nid, anna, felder, teil):
    werte = {"bezeichnung": "X", "art": "jahrestag", "datum": "--05-01", **felder}
    with pytest.raises(EingabeFehler, match=teil):
        stichtage.anlegen(con, nid, anna, **werte)
    assert con.execute("SELECT COUNT(*) FROM stichtag").fetchone()[0] == 0


def test_vorlauf_null_ist_erlaubt_und_leer_heisst_vorgabe(con, nid, anna):
    null = stichtage.anlegen(con, nid, anna, bezeichnung="a", art="sonstiges", datum="--05-01",
                             vorlauf_tage="0")
    leer = stichtage.anlegen(con, nid, anna, bezeichnung="b", art="sonstiges", datum="--05-01",
                             vorlauf_tage="")
    assert stichtage.laden(con, nid, null)["vorlauf_tage"] == 0
    assert stichtage.laden(con, nid, leer)["vorlauf_tage"] is None


def test_aendern_setzt_nur_die_genannten_felder(con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges",
                            datum="2020-09-01", vorlauf_tage=3)
    stichtage.aendern(con, nid, sid, bezeichnung="Einzug ins Haus")
    zeile = stichtage.laden(con, nid, sid)
    assert (zeile["bezeichnung"], zeile["datum"], zeile["vorlauf_tage"]) == (
        "Einzug ins Haus", "2020-09-01", 3)
    stichtage.aendern(con, nid, sid, datum="--09-02", vorlauf_tage="")
    zeile = stichtage.laden(con, nid, sid)
    assert (zeile["datum"], zeile["vorlauf_tage"]) == ("--09-02", None)
    stichtage.aendern(con, nid, sid, art="jahrestag")
    assert stichtage.laden(con, nid, sid)["art"] == "jahrestag"


def test_aendern_pruefte_dieselben_regeln(con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="a", art="jahrestag", datum="--05-01")
    with pytest.raises(EingabeFehler):
        stichtage.aendern(con, nid, sid, datum="--02-30")
    with pytest.raises(EingabeFehler, match="Namen"):
        stichtage.aendern(con, nid, sid, art="sonstiges", bezeichnung="")
    with pytest.raises(ValueError, match="Unbekannte Felder"):
        stichtage.aendern(con, nid, sid, farbe="rot")
    assert stichtage.laden(con, nid, sid)["datum"] == "--05-01"


def test_loeschen_gibt_die_person_zurueck(con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="a", art="jahrestag", datum="--05-01")
    assert stichtage.loeschen(con, nid, sid) == anna
    assert stichtage.laden(con, nid, sid) is None


def test_der_geburtstag_eines_angehoerigen_ist_hier_nicht_zu_aendern(con, nid, anna):
    kind = con.execute(
        "INSERT INTO angehoeriger (nutzer_id, person_id, name, rolle, geburtstag) "
        "VALUES (?, ?, 'Mia', 'kind', '--04-04')", (nid, anna)).lastrowid
    sid = con.execute(
        "INSERT INTO stichtag (nutzer_id, person_id, bezeichnung, art, datum, angehoeriger_id) "
        "VALUES (?, ?, 'Geburtstag Mia', 'geburtstag', '--04-04', ?)", (nid, anna, kind)).lastrowid
    con.commit()
    with pytest.raises(EingabeFehler, match="Angehörigen"):
        stichtage.aendern(con, nid, sid, datum="--04-05")
    with pytest.raises(EingabeFehler, match="Angehörigen"):
        stichtage.loeschen(con, nid, sid)
    assert stichtage.laden(con, nid, sid)["datum"] == "--04-04"


# --------------------------------------------------------------- Liste

def test_liste_sortiert_nach_dem_naechsten_mal(con, nid, anna):
    spaet = stichtage.anlegen(con, nid, anna, bezeichnung="spaet", art="sonstiges",
                              datum=in_tagen(200))
    bald = stichtage.anlegen(con, nid, anna, bezeichnung="bald", art="sonstiges",
                             datum=in_tagen(2))
    gestern = stichtage.anlegen(con, nid, anna, bezeichnung="gestern", art="sonstiges",
                                datum=in_tagen(-1))
    heute = stichtage.anlegen(con, nid, anna, bezeichnung="heute", art="sonstiges",
                              datum=in_tagen(0))
    assert [v.id for v in stichtage.liste(con, nid, anna)] == [heute, bald, spaet, gestern]
    assert [v.tage for v in stichtage.liste(con, nid, anna)] == [0, 2, 200, 364]


def test_liste_rechnet_alter_und_vorlauf(con, nid, anna):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                            datum=in_tagen(4, jahr=1986))
    (v,) = stichtage.liste(con, nid, anna)
    assert (v.id, v.tage, v.tag, v.jahre, v.vorlauf, v.vorlauf_eigen) == (
        sid, 4, HEUTE + dt.timedelta(days=4), 2026 - 1986, 7, None)
    assert v.jahre_text == "wird 40"
    assert v.tage_text == "in 4 Tagen"
    assert v.im_vorlauf
    assert v.plakette_text == "Geburtstag in 4 Tagen"


def test_liste_ohne_jahr_hat_kein_alter(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum=in_tagen(4))
    (v,) = stichtage.liste(con, nid, anna)
    assert v.jahre is None
    assert v.jahre_text == ""


def test_das_alter_zaehlt_am_naechsten_mal(con, nid, anna):
    """Gestern war der 40., das naechste Mal ist der 41."""
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag",
                      datum=in_tagen(-1, jahr=1986))
    (v,) = stichtage.liste(con, nid, anna)
    assert v.jahre == 41
    assert v.tag.year == 2027


def test_liste_einer_fremden_person_ist_nicht_gefunden(con, nid, anna, fremder):
    with pytest.raises(NichtGefunden):
        stichtage.liste(con, fremder, anna)
    with pytest.raises(NichtGefunden):
        stichtage.anlegen(con, fremder, anna, bezeichnung="x", art="jahrestag", datum="--05-01")


def test_ein_fremder_stichtag_ist_nicht_gefunden(con, nid, anna, fremder):
    sid = stichtage.anlegen(con, nid, anna, bezeichnung="a", art="jahrestag", datum="--05-01")
    assert stichtage.laden(con, fremder, sid) is None
    for aufruf in (lambda: stichtage.aendern(con, fremder, sid, bezeichnung="x"),
                   lambda: stichtage.loeschen(con, fremder, sid),
                   lambda: stichtage.vorkommen_von(con, fremder, sid)):
        with pytest.raises(NichtGefunden):
            aufruf()
    assert stichtage.laden(con, nid, sid)["bezeichnung"] == "a"


def test_plakette_text_nennt_je_nach_art(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="Hochzeitstag", art="jahrestag",
                      datum=in_tagen(0))
    stichtage.anlegen(con, nid, anna, bezeichnung="Einzug", art="sonstiges", datum=in_tagen(1))
    texte = [v.plakette_text for v in stichtage.liste(con, nid, anna)]
    assert texte == ["Jahrestag heute", "Einzug morgen"]


# ------------------------------------------------------------- Vorlauf

def test_im_vorlauf_mit_der_vorgabe_von_sieben_tagen(con, nid, anna):
    for tage in (0, 7, 8, 30):
        stichtage.anlegen(con, nid, anna, bezeichnung=f"in {tage}", art="sonstiges",
                          datum=in_tagen(tage))
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, nid)] == ["in 0", "in 7"]


def test_im_vorlauf_folgt_der_vorgabe_des_nutzers(con, nid, anna):
    con.execute("UPDATE nutzer SET vorgabe_vorlauf_tage = 14 WHERE id = ?", (nid,))
    con.commit()
    stichtage.anlegen(con, nid, anna, bezeichnung="in 14", art="sonstiges", datum=in_tagen(14))
    stichtage.anlegen(con, nid, anna, bezeichnung="in 15", art="sonstiges", datum=in_tagen(15))
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, nid)] == ["in 14"]


def test_der_vorlauf_des_stichtags_geht_vor(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="lang", art="sonstiges",
                      datum=in_tagen(20), vorlauf_tage=21)
    stichtage.anlegen(con, nid, anna, bezeichnung="kurz", art="sonstiges",
                      datum=in_tagen(3), vorlauf_tage=2)
    stichtage.anlegen(con, nid, anna, bezeichnung="nur heute", art="sonstiges",
                      datum=in_tagen(0), vorlauf_tage=0)
    stichtage.anlegen(con, nid, anna, bezeichnung="morgen nicht", art="sonstiges",
                      datum=in_tagen(1), vorlauf_tage=0)
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, nid)] == ["nur heute", "lang"]


def test_ein_gestriger_stichtag_ist_fuers_naechste_jahr_nicht_im_vorlauf(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="vorbei", art="sonstiges", datum=in_tagen(-1))
    assert stichtage.im_vorlauf(con, nid) == []


def test_der_vorlauf_reicht_ueber_den_jahreswechsel(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="Neujahr", art="sonstiges", datum="--01-02")
    assert stichtage.im_vorlauf(con, nid, tag("2026-12-30"))[0].tage == 3
    assert stichtage.im_vorlauf(con, nid, tag("2026-12-20")) == []


def test_im_vorlauf_ist_nach_dem_naechsten_sortiert(con, nid, anna):
    ben = personen.anlegen(con, nid, "Ben Muster")
    stichtage.anlegen(con, nid, anna, bezeichnung="drei", art="sonstiges", datum=in_tagen(3))
    stichtage.anlegen(con, nid, ben, bezeichnung="eins", art="sonstiges", datum=in_tagen(1))
    liste = stichtage.im_vorlauf(con, nid)
    assert [(v.person_id, v.person_name, v.tage) for v in liste] == [
        (ben, "Ben Muster", 1), (anna, "Anna Beispiel", 3)]
    assert {pid: v.bezeichnung for pid, v in stichtage.je_person(liste).items()} == {
        ben: "eins", anna: "drei"}


def test_je_person_nimmt_den_naechsten(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="spaeter", art="sonstiges", datum=in_tagen(5))
    stichtage.anlegen(con, nid, anna, bezeichnung="erst", art="sonstiges", datum=in_tagen(2))
    assert stichtage.je_person(stichtage.im_vorlauf(con, nid))[anna].bezeichnung == "erst"


def test_archivierte_personen_haben_keinen_stichtag_im_vorlauf(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="x", art="sonstiges", datum=in_tagen(1))
    personen.archivieren(con, nid, anna)
    assert stichtage.im_vorlauf(con, nid) == []
    assert len(stichtage.liste(con, nid, anna)) == 1      # die Seite zeigt ihn weiter


def test_im_vorlauf_sieht_nur_die_stichtage_des_nutzers(con, nid, anna, fremder):
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    stichtage.anlegen(con, fremder, fremde, bezeichnung="fremd", art="sonstiges",
                      datum=in_tagen(1))
    stichtage.anlegen(con, nid, anna, bezeichnung="mein", art="sonstiges", datum=in_tagen(1))
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, nid)] == ["mein"]
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, fremder)] == ["fremd"]


def test_im_vorlauf_nimmt_die_vorgabe_des_jeweiligen_nutzers(con, nid, anna, fremder):
    """Zwei Nutzer, zwei Vorgaben: keiner bekommt die des anderen."""
    con.execute("UPDATE nutzer SET vorgabe_vorlauf_tage = 30 WHERE id = ?", (fremder,))
    con.commit()
    fremde = personen.anlegen(con, fremder, "Zoe Fremd")
    stichtage.anlegen(con, fremder, fremde, bezeichnung="f", art="sonstiges", datum=in_tagen(20))
    stichtage.anlegen(con, nid, anna, bezeichnung="m", art="sonstiges", datum=in_tagen(20))
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, nid)] == []
    assert [v.bezeichnung for v in stichtage.im_vorlauf(con, fremder)] == ["f"]
