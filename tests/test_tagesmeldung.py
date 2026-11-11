"""Die Tagesmeldung: was heute zu sagen ist (PLAN.md, Abschnitt 10).

Die Uhr steht auf Mittwoch, 11. November 2026. Vorgabe-Intervall 56 Tage, Vorlauf 7.
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import angehoerige, kontakte, personen, stichtage, tagesmeldung

HEUTE = dt.date(2026, 11, 11)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def person(con, nid: int, name: str, vor_tagen: int | None) -> int:
    """Eine Person, mit dem letzten Kontakt vor `vor_tagen` Tagen (`None`: nie)."""
    pid = personen.anlegen(con, nid, name)
    if vor_tagen is not None:
        kontakte.eintragen(con, nid, pid, datum=HEUTE - dt.timedelta(days=vor_tagen),
                           art="anruf")
    return pid


def in_tagen(tage: int) -> str:
    ziel = HEUTE + dt.timedelta(days=tage)
    return f"--{ziel.month:02d}-{ziel.day:02d}"


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC))


# ------------------------------------------------------------ nichts zu sagen

def test_nobody_in_the_app_means_no_digest(con, nid):
    assert tagesmeldung.bauen(con, nid, HEUTE) is None


def test_people_who_are_fine_or_unknown_are_no_digest(con, nid):
    person(con, nid, "Anna Beispiel", 10)      # ok
    person(con, nid, "Ben Muster", None)       # unbekannt
    person(con, nid, "Clara Probe", 53)        # bald: faellig in 3 Tagen, nicht heute
    assert tagesmeldung.bauen(con, nid, HEUTE) is None


def test_archived_people_do_not_wait(con, nid):
    pid = person(con, nid, "Anna Beispiel", 200)
    personen.archivieren(con, nid, pid)
    assert tagesmeldung.bauen(con, nid, HEUTE) is None


def test_a_stichtag_outside_its_window_is_no_digest(con, nid):
    pid = person(con, nid, "Anna Beispiel", 10)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum=in_tagen(8))
    assert tagesmeldung.bauen(con, nid, HEUTE) is None


# ------------------------------------------------------------ wer wartet

def test_overdue_cold_and_due_today_all_wait(con, nid):
    person(con, nid, "Anna Beispiel", 70)    # ueberfaellig
    person(con, nid, "Ben Muster", 200)      # erkaltet
    person(con, nid, "Clara Probe", 56)      # faellig heute
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.wartende == 3
    assert meldung.zaehlzeile == "3 Personen warten"
    assert meldung.url == "/?karte=aufmerksamkeit"


def test_one_person_is_singular(con, nid):
    person(con, nid, "Anna Beispiel", 70)
    assert tagesmeldung.bauen(con, nid, HEUTE).zaehlzeile == "1 Person wartet"


def test_names_are_cold_first_then_by_due_date_then_name(con, nid):
    person(con, nid, "Dora Probe", 60)       # ueberfaellig seit 4 Tagen
    person(con, nid, "Anna Beispiel", 80)    # ueberfaellig seit 24 Tagen
    person(con, nid, "Ben Muster", 200)      # erkaltet: zuerst
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.namenzeile == "Ben Muster, Anna Beispiel, Dora Probe"


def test_at_most_three_names_and_an_ellipsis_for_the_rest(con, nid):
    for zahl, name in enumerate(["Anna Beispiel", "Ben Muster", "Clara Probe", "Dora Probe"]):
        person(con, nid, name, 80 - zahl)
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.zaehlzeile == "4 Personen warten"
    assert meldung.namenzeile == "Anna Beispiel, Ben Muster, Clara Probe …"
    assert "Dora" not in meldung.namenzeile


def test_exactly_three_names_have_no_ellipsis(con, nid):
    for zahl, name in enumerate(["Anna Beispiel", "Ben Muster", "Clara Probe"]):
        person(con, nid, name, 80 - zahl)
    assert tagesmeldung.bauen(con, nid, HEUTE).namenzeile == \
        "Anna Beispiel, Ben Muster, Clara Probe"


def test_other_users_people_do_not_count(con, nid):
    from bindung import auth

    fremd = auth.nutzer_anlegen(con, "Anderer", "geheimes-passwort")
    person(con, fremd, "Fremde Person", 200)
    assert tagesmeldung.bauen(con, nid, HEUTE) is None
    assert tagesmeldung.bauen(con, fremd, HEUTE).wartende == 1


# ------------------------------------------------------------ Stichtage

def test_a_birthday_in_three_days_has_its_own_line(con, nid):
    pid = person(con, nid, "Mia Beispiel", 10)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum=in_tagen(3))
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.zaehlzeile == "1 Geburtstag"
    assert meldung.stichtagzeile == "Geburtstag Mia Beispiel in 3 Tagen"
    assert meldung.namenzeile == ""


def test_only_stichtage_open_the_week_card(con, nid):
    pid = person(con, nid, "Mia Beispiel", 10)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum=in_tagen(3))
    assert tagesmeldung.bauen(con, nid, HEUTE).url == "/?karte=woche"


def test_waiting_people_win_the_url_over_stichtage(con, nid):
    pid = person(con, nid, "Mia Beispiel", 80)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum=in_tagen(0))
    assert tagesmeldung.bauen(con, nid, HEUTE).url == "/?karte=aufmerksamkeit"


def test_counts_and_nearest_stichtag_go_with_the_names(con, nid):
    anna = person(con, nid, "Anna Beispiel", 80)
    ben = person(con, nid, "Ben Muster", 10)
    person(con, nid, "Clara Probe", 200)
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum=in_tagen(5))
    stichtage.anlegen(con, nid, ben, bezeichnung="Firmenjubiläum", art="sonstiges",
                      datum=in_tagen(1))
    stichtage.anlegen(con, nid, ben, bezeichnung="", art="geburtstag", datum=in_tagen(2))
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.zaehlzeile == "2 Personen warten · 2 Geburtstage · 1 Stichtag"
    assert meldung.stichtagzeile == "Ben Muster: Firmenjubiläum morgen"
    assert meldung.text == "\n".join([meldung.zaehlzeile, "Clara Probe, Anna Beispiel",
                                      "Ben Muster: Firmenjubiläum morgen"])


def test_a_family_birthday_names_the_parent(con, nid):
    anna = person(con, nid, "Anna Beispiel", 10)
    angehoerige.anlegen(con, nid, anna, name="Mia Beispiel", rolle="kind",
                        geburtstag=in_tagen(3))
    assert tagesmeldung.bauen(con, nid, HEUTE).stichtagzeile == \
        "Geburtstag Mia Beispiel (Anna Beispiel) in 3 Tagen"


def test_a_stichtag_today_says_heute(con, nid):
    pid = person(con, nid, "Mia Beispiel", 10)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="jahrestag", datum=in_tagen(0))
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.zaehlzeile == "1 Jahrestag"
    assert meldung.stichtagzeile.endswith("heute")


def test_the_stichtage_of_archived_people_stay_quiet(con, nid):
    pid = person(con, nid, "Mia Beispiel", 10)
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum=in_tagen(1))
    personen.archivieren(con, nid, pid)
    assert tagesmeldung.bauen(con, nid, HEUTE) is None


# ------------------------------------------------------------ Nutzlast

def test_the_payload_carries_title_text_url_and_the_replace_tag(con, nid):
    person(con, nid, "Anna Beispiel", 80)
    meldung = tagesmeldung.bauen(con, nid, HEUTE)
    assert meldung.nutzlast == {"titel": "Bindung", "text": "1 Person wartet\nAnna Beispiel",
                                "url": "/?karte=aufmerksamkeit", "tag": "tagesmeldung"}


# ------------------------------------------------------------ Hinweis

def test_hinweis_is_the_digest_until_it_is_dismissed_for_today(con, nid):
    person(con, nid, "Anna Beispiel", 80)
    assert tagesmeldung.hinweis(con, nid, HEUTE) is not None
    tagesmeldung.hinweis_wegklicken(con, nid, HEUTE)
    assert tagesmeldung.hinweis(con, nid, HEUTE) is None
    # Morgen ist ein neuer Tag.
    assert tagesmeldung.hinweis(con, nid, HEUTE + dt.timedelta(days=1)) is not None


def test_dismissing_keeps_the_day_of_the_last_send(con, nid):
    con.execute("INSERT INTO digest_protokoll (nutzer_id, letzter_versand_am) VALUES (?, ?)",
                (nid, "2026-11-10"))
    tagesmeldung.hinweis_wegklicken(con, nid, HEUTE)
    zeile = con.execute("SELECT * FROM digest_protokoll WHERE nutzer_id = ?", (nid,)).fetchone()
    assert (zeile["letzter_versand_am"], zeile["hinweis_weggeklickt_am"]) == \
        ("2026-11-10", "2026-11-11")
