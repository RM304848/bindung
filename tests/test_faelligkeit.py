"""Faelligkeit und Zustand (PLAN.md, Abschnitt 6): jede Grenze, genau am Tag."""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import faelligkeit as f
from bindung import kontakte, personen

HEUTE = dt.date(2026, 11, 11)


def tage_her(n: int) -> dt.date:
    return HEUTE - dt.timedelta(days=n)


def in_tagen(n: int) -> dt.date:
    return HEUTE + dt.timedelta(days=n)


# ------------------------------------------------------------- reine Regeln

def test_kaelte_grenze_ist_das_doppelte_hoechstens_180():
    assert f.kaelte_grenze(7) == 14
    assert f.kaelte_grenze(56) == 112
    assert f.kaelte_grenze(90) == 180
    assert f.kaelte_grenze(91) == 180
    assert f.kaelte_grenze(3650) == 180


def test_faellig_am_ist_letzter_kontakt_plus_intervall():
    assert f.faellig_am(dt.date(2026, 1, 1), 56) == dt.date(2026, 2, 26)


def test_der_naechste_termin_ersetzt_das_intervall():
    assert f.faellig_am(dt.date(2026, 1, 1), 56, dt.date(2026, 3, 1)) == dt.date(2026, 3, 1)


def test_ohne_kontakt_gibt_es_keinen_tag():
    assert f.faellig_am(None, 56) is None


# (letzter Kontakt vor n Tagen | None, Intervall, naechster Termin in n Tagen | None) -> Zustand
ZUSTAENDE = [
    # unbekannt: nie faellig, auch nicht mit nächstem Termin
    (None, 56, None, f.UNBEKANNT),
    (None, 56, -10, f.UNBEKANNT),
    # ok: weit weg
    (0, 56, None, f.OK),
    (48, 56, None, f.OK),           # faellig in 8 Tagen: noch nicht bald
    # bald: heute bis +7
    (49, 56, None, f.BALD),         # faellig in genau 7 Tagen
    (56, 56, None, f.BALD),         # faellig heute
    # ueberfaellig: ab dem Tag nach dem Faelligkeitstag
    (57, 56, None, f.UEBERFAELLIG),
    (112, 56, None, f.UEBERFAELLIG),  # genau das Doppelte: noch nicht erkaltet
    # erkaltet: strikt mehr als min(2 x Intervall, 180)
    (113, 56, None, f.ERKALTET),
    (400, 56, None, f.ERKALTET),
    # Intervall 7: Grenze 14
    (14, 7, None, f.UEBERFAELLIG),
    (15, 7, None, f.ERKALTET),
    # Intervall 90 und 400: die Grenze ist 180, nicht das Doppelte
    (180, 90, None, f.UEBERFAELLIG),
    (181, 90, None, f.ERKALTET),
    (180, 400, None, f.OK),           # faellig erst in 220 Tagen
    (181, 400, None, f.ERKALTET),     # ... und trotzdem erkaltet: hartes Halbjahr
    # nächster Termin ersetzt das Intervall
    (10, 56, 3, f.BALD),
    (10, 56, 8, f.OK),
    (10, 56, -1, f.UEBERFAELLIG),
    (10, 56, 0, f.BALD),
    (10, 56, 7, f.BALD),
    # erkaltet geht vor ueberfaellig, auch mit späterem nächstem Termin
    (200, 56, 5, f.ERKALTET),
]


@pytest.mark.parametrize(("her", "intervall", "termin", "erwartet"), ZUSTAENDE)
def test_zustand_an_den_grenzen(her, intervall, termin, erwartet):
    letzter = None if her is None else tage_her(her)
    naechster = None if termin is None else in_tagen(termin)
    assert f.zustand(HEUTE, letzter, intervall, naechster) == erwartet


def test_jeder_zustand_kommt_vor():
    assert {f.zustand(HEUTE, None if h is None else tage_her(h), i,
                      None if t is None else in_tagen(t)) for h, i, t, _ in ZUSTAENDE} == {
        f.UNBEKANNT, f.OK, f.BALD, f.UEBERFAELLIG, f.ERKALTET}


# ------------------------------------------------------------------ Sortierung

def test_sortierung_erkaltet_zuerst_dann_faelligkeit_dann_name():
    def b(pid, her, intervall=56):
        return f.bindung_rechnen(HEUTE, pid, tage_her(her), intervall)

    bindungen = {1: b(1, 60), 2: b(2, 60), 3: b(3, 200), 4: b(4, 150), 5: b(5, 70)}
    namen = {1: "Zora", 2: "Anna", 3: "Ben", 4: "Cem", 5: "Dora"}
    # 3 und 4 sind erkaltet (200 und 150 Tage > 112), 3 ist laenger faellig.
    # Danach nach Faelligkeit: 5 (vor 70 Tagen) vor 1 und 2 (vor 60 Tagen);
    # 1 und 2 sind gleich faellig, also entscheidet der Name: Anna (2) vor Zora (1).
    reihe = sorted(bindungen, key=lambda i: f.sortierschluessel(bindungen[i], namen[i]))
    assert reihe == [3, 4, 5, 2, 1]


# -------------------------------------------------------------------- Karten

def test_karten_nummern():
    bindungen = {
        1: f.bindung_rechnen(HEUTE, 1, tage_her(70), 56),    # ueberfaellig
        2: f.bindung_rechnen(HEUTE, 2, tage_her(150), 56),   # erkaltet
        3: f.bindung_rechnen(HEUTE, 3, tage_her(50), 56),    # bald
        4: f.bindung_rechnen(HEUTE, 4, tage_her(5), 56),     # ok
        5: f.bindung_rechnen(HEUTE, 5, None, 56),            # unbekannt
    }
    karten = f.karten_nummern(bindungen)
    assert karten[f.KARTE_AUFMERKSAMKEIT] == {1, 2}
    assert karten[f.KARTE_ERKALTET] == {2}
    assert karten[f.KARTE_WOCHE] == {3}


def test_stichtage_gehoeren_auf_die_karte_woche_aber_aendern_den_zustand_nicht():
    bindungen = {1: f.bindung_rechnen(HEUTE, 1, tage_her(5), 56),
                 2: f.bindung_rechnen(HEUTE, 2, tage_her(50), 56)}
    karten = f.karten_nummern(bindungen, {1, 2, 99})
    assert karten[f.KARTE_WOCHE] == {1, 2}  # 2 nur einmal, 99 ist nicht aktiv
    assert bindungen[1].zustand == f.OK


# ---------------------------------------------------------------- Datenbank

def test_bindungen_rechnet_alle_in_einer_abfrage(con, nutzer):
    nid = con.execute("SELECT id FROM nutzer").fetchone()["id"]
    a = personen.anlegen(con, nid, "Anna Beispiel", intervall_tage=20)
    b = personen.anlegen(con, nid, "Ben Muster")
    c = personen.anlegen(con, nid, "Cem Probe")
    archiv = personen.anlegen(con, nid, "Archiv Beispiel")
    personen.archivieren(con, nid, archiv)
    con.executemany("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, ?, ?)",
                    [(nid, a, tage_her(25).isoformat(), "anruf"),
                     (nid, a, tage_her(30).isoformat(), "anruf"),
                     (nid, b, tage_her(10).isoformat(), "treffen")])
    gerechnet = f.bindungen(con, nid, HEUTE)
    assert set(gerechnet) == {a, b, c}
    assert gerechnet[a].letzter_kontakt == tage_her(25)
    assert gerechnet[a].intervall == 20 and gerechnet[a].zustand == f.UEBERFAELLIG
    assert gerechnet[b].intervall == 56 and gerechnet[b].zustand == f.OK
    assert gerechnet[c].zustand == f.UNBEKANNT
    einzeln = f.bindungen(con, nid, HEUTE, person_id=archiv)
    assert set(einzeln) == {archiv}


def test_bindungen_nimmt_die_vorgabe_des_nutzers(con, nutzer):
    nid = con.execute("SELECT id FROM nutzer").fetchone()["id"]
    con.execute("UPDATE nutzer SET vorgabe_intervall_tage = 10 WHERE id = ?", (nid,))
    p = personen.anlegen(con, nid, "Anna Beispiel")
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, ?, 'anruf')",
                (nid, p, tage_her(11).isoformat()))
    assert f.bindungen(con, nid, HEUTE)[p].zustand == f.UEBERFAELLIG


def test_bindungen_sieht_nur_die_eigenen_personen(con, nutzer):
    from bindung import auth

    from .conftest import PASSWORT

    nid = con.execute("SELECT id FROM nutzer").fetchone()["id"]
    fremder = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    fremd = personen.anlegen(con, fremder, "Fremd Beispiel")
    assert fremd not in f.bindungen(con, nid, HEUTE)
    assert f.bindungen(con, nid, HEUTE, person_id=fremd) == {}


def test_ein_kontakt_aendert_den_zustand(con, nutzer, monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC))
    nid = con.execute("SELECT id FROM nutzer").fetchone()["id"]
    p = personen.anlegen(con, nid, "Anna Beispiel", naechster_termin="2026-11-01")
    assert f.bindungen(con, nid, HEUTE)[p].zustand == f.UNBEKANNT
    kontakte.eintragen(con, nid, p, datum="2026-11-05", art="anruf")
    assert f.bindungen(con, nid, HEUTE)[p].zustand == f.OK  # Termin gelöscht, Intervall greift


# ---------------------------------------------------------------- Worte

@pytest.mark.parametrize(("tage", "text"), [
    (0, "heute"), (-3, "heute"), (1, "gestern"), (2, "vor 2 Tagen"), (5, "vor 5 Tagen"),
    (13, "vor 13 Tagen"), (14, "vor 2 Wochen"), (21, "vor 3 Wochen"), (59, "vor 8 Wochen"),
    (60, "vor 2 Monaten"), (120, "vor 4 Monaten"), (364, "vor 12 Monaten"),
    (365, "vor über einem Jahr"), (900, "vor über einem Jahr"),
])
def test_vor_text(tage, text):
    assert f.vor_text(tage) == text


@pytest.mark.parametrize(("tage", "text"), [(0, "heute"), (1, "morgen"), (4, "in 4 Tagen")])
def test_in_text(tage, text):
    assert f.in_text(tage) == text


def _plakette(her, intervall=56, termin=None):
    letzter = None if her is None else tage_her(her)
    naechster = None if termin is None else in_tagen(termin)
    return f.plakette(f.bindung_rechnen(HEUTE, 1, letzter, intervall, naechster), HEUTE)


@pytest.mark.parametrize(("her", "intervall", "termin", "text", "ton"), [
    (None, 56, None, "noch kein Touchpoint", f.UNBEKANNT),
    (21, 56, None, "vor 3 Wochen", f.OK),
    (50, 56, None, "fällig in 6 Tagen", f.BALD),
    (56, 56, None, "fällig heute", f.BALD),
    (68, 56, None, "überfällig seit 12 Tagen", f.UEBERFAELLIG),
    (57, 56, None, "überfällig seit 1 Tag", f.UEBERFAELLIG),
    (200, 56, None, "erkaltet", f.ERKALTET),
])
def test_plakette(her, intervall, termin, text, ton):
    p = _plakette(her, intervall, termin)
    assert (p.text, p.ton) == (text, ton)


def test_zustand_text_kennt_alle_fuenf():
    assert {f.zustand_text(z) for z in (f.UNBEKANNT, f.OK, f.BALD, f.UEBERFAELLIG, f.ERKALTET)} \
        == {"unbekannt", "ok", "bald fällig", "überfällig", "erkaltet"}
