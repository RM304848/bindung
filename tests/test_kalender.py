"""Der Kalender: `.ics`-Text nach RFC 5545 (PLAN.md, Abschnitt 9).

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import angehoerige, auth, kalender, kontakte, personen, stichtage

from .conftest import PASSWORT

HEUTE = dt.date(2026, 11, 11)
JETZT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt", lambda: JETZT)
    monkeypatch.setattr(kalender, "_jetzt", lambda: JETZT)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def anna(con, nid) -> int:
    return personen.anlegen(con, nid, "Anna Beispiel")


def kontakt_vor(con, nid, pid, tage: int, notiz: str | None = None) -> None:
    kontakte.eintragen(con, nid, pid, datum=HEUTE - dt.timedelta(days=tage), art="anruf",
                       notiz=notiz)


# ------------------------------------------------------------- ein kleiner Leser

def entfalten(text: str) -> list[str]:
    """Die logischen Zeilen: Folgezeilen (Leerzeichen am Anfang) wieder angehaengt."""
    assert text.endswith("\r\n")
    zeilen: list[str] = []
    for zeile in text[:-2].split("\r\n"):
        if zeile.startswith(" "):
            zeilen[-1] += zeile[1:]
        else:
            zeilen.append(zeile)
    return zeilen


def entmaskieren(wert: str) -> str:
    aus, i = [], 0
    while i < len(wert):
        if wert[i] == "\\" and i + 1 < len(wert):
            aus.append("\n" if wert[i + 1] in "nN" else wert[i + 1])
            i += 2
        else:
            aus.append(wert[i])
            i += 1
    return "".join(aus)


def lesen(text: str) -> list[dict]:
    """Die VEVENTs als Woerterbuecher: Name -> Wert (mit Parametern im Namen), `VALARM` -> Liste."""
    zeilen = entfalten(text)
    assert zeilen[0] == "BEGIN:VCALENDAR" and zeilen[-1] == "END:VCALENDAR"
    ereignisse: list[dict] = []
    aktuell: dict | None = None
    alarm: dict | None = None
    for zeile in zeilen[1:-1]:
        if zeile == "BEGIN:VEVENT":
            assert aktuell is None
            aktuell = {"VALARM": []}
        elif zeile == "END:VEVENT":
            ereignisse.append(aktuell)
            aktuell = None
        elif zeile == "BEGIN:VALARM":
            alarm = {}
        elif zeile == "END:VALARM":
            aktuell["VALARM"].append(alarm)
            alarm = None
        elif aktuell is not None:
            name, wert = zeile.split(":", 1)
            (alarm if alarm is not None else aktuell)[name] = wert
    assert aktuell is None and alarm is None
    return ereignisse


def nach_uid(text: str) -> dict[str, dict]:
    ereignisse = lesen(text)
    uids = [e["UID"] for e in ereignisse]
    assert len(uids) == len(set(uids)), "doppelte UID"
    return {e["UID"]: e for e in ereignisse}


def summe(e: dict) -> str:
    return entmaskieren(e["SUMMARY"])


# ------------------------------------------------------------ Bausteine

def test_escape_comma_semicolon_backslash_and_newline():
    assert kalender.maskieren("a, b; c\\d\ne\r\nf") == "a\\, b\\; c\\\\d\\ne\\nf"


def test_escape_round_trips():
    text = "Zeile eins, zwei; drei\\vier\nfünf"
    assert entmaskieren(kalender.maskieren(text)) == text


def test_control_characters_are_dropped():
    assert kalender.maskieren("a\x00b\x07c\x7f") == "abc"


def test_short_lines_are_not_folded():
    zeile = "SUMMARY:" + "x" * 67
    assert len(zeile) == 75
    assert kalender.falten(zeile) == zeile


def test_long_lines_fold_at_75_octets():
    zeile = "DESCRIPTION:" + "abcdefghij" * 20
    gefaltet = kalender.falten(zeile)
    teile = gefaltet.split("\r\n")
    assert len(teile) > 1
    assert len(teile[0].encode()) == 75
    assert all(t.startswith(" ") and len(t.encode()) <= 75 for t in teile[1:])
    assert "".join([teile[0]] + [t[1:] for t in teile[1:]]) == zeile


def test_folding_never_splits_a_multibyte_character():
    zeile = "SUMMARY:" + "äöü€😀" * 30
    gefaltet = kalender.falten(zeile)
    for teil in gefaltet.split("\r\n"):
        assert len(teil.encode()) <= 75
        teil.encode().decode("utf-8")  # kein halbes Zeichen
    ohne = gefaltet.replace("\r\n ", "")
    assert ohne == zeile


def test_a_whole_calendar_ends_every_line_with_crlf_and_folds():
    lang = "x" * 300
    text = kalender.kalender([kalender.ereignis("a@bindung", HEUTE, lang, JETZT)])
    assert text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert all(len(z.encode()) <= 75 for z in text.split("\r\n"))
    assert summe(lesen(text)[0]) == lang


def test_header_names_the_calendar_and_asks_for_hourly_refresh():
    zeilen = entfalten(kalender.kalender([]))
    assert zeilen[:3] == ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bindung//Kalender//DE"]
    assert "X-WR-CALNAME:Bindung" in zeilen
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in zeilen
    assert "X-PUBLISHED-TTL:PT1H" in zeilen
    assert "METHOD:PUBLISH" in zeilen


def test_dtstamp_and_last_modified_are_utc():
    e = lesen(kalender.kalender([kalender.ereignis("a@bindung", HEUTE, "x", JETZT)]))[0]
    assert e["DTSTAMP"] == e["LAST-MODIFIED"] == "20261111T120000Z"


def test_a_non_utc_stamp_is_converted():
    berlin = dt.datetime(2026, 11, 11, 13, 0, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert kalender.zeitstempel(berlin) == "20261111T120000Z"


def test_all_day_event_ends_the_next_day():
    e = lesen(kalender.kalender([kalender.ereignis("a@bindung", dt.date(2026, 12, 31), "x",
                                                  JETZT)]))[0]
    assert e["DTSTART;VALUE=DATE"] == "20261231"
    assert e["DTEND;VALUE=DATE"] == "20270101"
    assert e["TRANSP"] == "TRANSPARENT"


# ------------------------------------------------------------ Stichtage

def test_empty_calendar_is_valid(con, nid):
    assert lesen(kalender.kalender_text(con, nid)) == []


def test_birthday_without_year_starts_at_the_next_occurrence_and_repeats_yearly(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--03-24")
    e = nach_uid(kalender.kalender_text(con, nid))[f"stichtag-{1}@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20270324"
    assert e["RRULE"] == "FREQ=YEARLY"
    assert summe(e) == "Geburtstag Anna Beispiel"
    assert "DESCRIPTION" not in e


def test_birthday_today_starts_today(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--11-11")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20261111"


def test_known_year_is_the_start_and_is_named_as_a_fact(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="1986-03-24")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "19860324"
    assert e["RRULE"] == "FREQ=YEARLY"
    assert entmaskieren(e["DESCRIPTION"]) == "Geburtsjahr 1986"
    # Kein Alter: die Beschreibung gilt fuer die ganze Reihe.
    assert "wird" not in e["DESCRIPTION"]


def test_named_day_reads_person_colon_name(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="Firmenjubiläum", art="jahrestag",
                      datum="2012-05-01")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert summe(e) == "Anna Beispiel: Firmenjubiläum"
    assert entmaskieren(e["DESCRIPTION"]) == "Seit 2012"


def test_default_label_of_an_anniversary_keeps_the_person_in_front(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="jahrestag", datum="--06-01")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert summe(e) == "Anna Beispiel: Jahrestag"


def test_family_birthday_names_the_parent(con, nid, anna):
    angehoerige.anlegen(con, nid, anna, name="Mia Beispiel", rolle="kind",
                        geburtstag="2018-08-09")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert summe(e) == "Geburtstag Mia Beispiel (Anna Beispiel)"
    assert e["DTSTART;VALUE=DATE"] == "20180809"


def test_leap_day_without_year_starts_on_a_real_29_february(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--02-29")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20280229"  # 2027 ist kein Schaltjahr
    assert e["RRULE"] == "FREQ=YEARLY"


def test_leap_day_start_skips_the_century_year_without_a_leap_day():
    assert kalender.erster_tag("--02-29", dt.date(2097, 1, 1)) == dt.date(2104, 2, 29)
    assert kalender.erster_tag("--02-29", dt.date(2028, 2, 29)) == dt.date(2028, 2, 29)
    assert kalender.erster_tag("--02-29", dt.date(2028, 3, 1)) == dt.date(2032, 2, 29)


def test_leap_day_with_year_starts_on_that_day(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="2000-02-29")
    e = nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20000229"
    assert e["DTEND;VALUE=DATE"] == "20000301"


def test_stichtag_uid_is_stable_across_runs_and_edits(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--03-24")
    vorher = set(nach_uid(kalender.kalender_text(con, nid)))
    stichtage.aendern(con, nid, 1, datum="--04-01")
    assert set(nach_uid(kalender.kalender_text(con, nid))) == vorher == {"stichtag-1@bindung"}


def test_archived_person_has_no_events(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--03-24")
    kontakt_vor(con, nid, anna, 70)
    assert len(lesen(kalender.kalender_text(con, nid))) == 2
    personen.archivieren(con, nid, anna)
    assert lesen(kalender.kalender_text(con, nid)) == []


def test_text_of_stichtag_is_escaped(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="Hochzeit, Standesamt; Berlin", art="jahrestag",
                      datum="--06-01")
    zeile = next(z for z in entfalten(kalender.kalender_text(con, nid))
                 if z.startswith("SUMMARY:"))
    assert zeile == "SUMMARY:Anna Beispiel: Hochzeit\\, Standesamt\\; Berlin"


# ------------------------------------------------------------ Melden bei

def test_person_without_contact_is_not_in_the_calendar(con, nid, anna):
    assert lesen(kalender.kalender_text(con, nid)) == []


def test_due_in_the_future_gets_an_event_on_the_due_day(con, nid, anna):
    kontakt_vor(con, nid, anna, 10)  # Intervall 56: faellig am 2026-12-27
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert summe(e) == "Melden bei Anna Beispiel"
    assert e["DTSTART;VALUE=DATE"] == "20261227"
    assert "RRULE" not in e


def test_overdue_person_gets_the_event_today_not_in_the_past(con, nid, anna):
    kontakt_vor(con, nid, anna, 70)  # faellig seit 14 Tagen, aber noch nicht erkaltet
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20261111"
    assert e["DTEND;VALUE=DATE"] == "20261112"


def test_cold_person_gets_the_event_today(con, nid, anna):
    kontakt_vor(con, nid, anna, 300)
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20261111"


def test_next_date_decides_the_day(con, nid, anna):
    kontakt_vor(con, nid, anna, 10)
    personen.aendern(con, nid, anna, naechster_termin="2026-11-20")
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert e["DTSTART;VALUE=DATE"] == "20261120"


def test_latest_note_first_line_is_the_description(con, nid, anna):
    kontakt_vor(con, nid, anna, 30, notiz="Alte Notiz")
    kontakt_vor(con, nid, anna, 10, notiz="\nUmzug nach Köln, Stelle gewechselt\nZweite Zeile")
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert entmaskieren(e["DESCRIPTION"]) == (
        "Zuletzt besprochen: Umzug nach Köln, Stelle gewechselt")
    assert "Zweite" not in e["DESCRIPTION"]


def test_no_note_no_description(con, nid, anna):
    kontakt_vor(con, nid, anna, 10)
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert "DESCRIPTION" not in e


def test_rough_contact_has_no_note_and_still_counts(con, nid, anna):
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, ?, ?)",
                (nid, anna, (HEUTE - dt.timedelta(days=15)).isoformat(), "schaetzung"))
    con.commit()
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert "DESCRIPTION" not in e


def test_reach_out_event_carries_an_alarm_at_nine_in_the_morning(con, nid, anna):
    kontakt_vor(con, nid, anna, 10)
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert e["VALARM"] == [{"ACTION": "DISPLAY", "DESCRIPTION": "Melden bei Anna Beispiel",
                            "TRIGGER": "PT9H"}]


def test_stichtag_has_no_alarm(con, nid, anna):
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--03-24")
    assert nach_uid(kalender.kalender_text(con, nid))["stichtag-1@bindung"]["VALARM"] == []


def test_melden_uid_is_stable_when_the_day_moves(con, nid, anna):
    kontakt_vor(con, nid, anna, 10)
    vorher = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    kontakt_vor(con, nid, anna, 0)
    nachher = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    assert vorher["DTSTART;VALUE=DATE"] == "20261227"
    assert nachher["DTSTART;VALUE=DATE"] == "20270106"


def test_the_time_zone_decides_what_today_is(con, nid, anna, monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 23, 30, tzinfo=dt.UTC))
    con.execute("UPDATE nutzer SET zeitzone = 'Europe/Berlin' WHERE id = ?", (nid,))
    con.commit()
    kontakte.eintragen(con, nid, anna, datum=dt.date(2026, 9, 1), art="anruf")
    e = nach_uid(kalender.kalender_text(con, nid))[f"melden-{anna}@bindung"]
    # In Berlin ist es schon der 12.: ueberfaellig, also heute = 12.
    assert e["DTSTART;VALUE=DATE"] == "20261112"


# ------------------------------------------------------------ Trennung der Nutzer

def test_only_the_own_people_come_along(con, nid, anna):
    fremd = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    bea = personen.anlegen(con, fremd, "Bea Fremd")
    stichtage.anlegen(con, fremd, bea, bezeichnung="", art="geburtstag", datum="--03-24")
    kontakt_vor(con, fremd, bea, 70)
    stichtage.anlegen(con, nid, anna, bezeichnung="", art="geburtstag", datum="--04-01")
    eigen = kalender.kalender_text(con, nid)
    assert "Bea" not in eigen and "Anna Beispiel" in eigen
    assert "Anna" not in kalender.kalender_text(con, fremd)


# ------------------------------------------------------------ Kalenderadresse

def test_token_belongs_to_exactly_one_user(con, nid):
    token = con.execute("SELECT kalender_token FROM nutzer WHERE id = ?", (nid,)).fetchone()[0]
    assert kalender.nutzer_zu_token(con, token) == nid
    assert kalender.nutzer_zu_token(con, token[:-1]) is None
    assert kalender.nutzer_zu_token(con, token + "x") is None
    assert kalender.nutzer_zu_token(con, "") is None


def test_renewing_the_token_kills_the_old_one(con, nid):
    alt = con.execute("SELECT kalender_token FROM nutzer WHERE id = ?", (nid,)).fetchone()[0]
    neu = kalender.token_erneuern(con, nid)
    assert neu != alt and len(neu) >= 43  # 32 Byte, base64
    assert kalender.nutzer_zu_token(con, alt) is None
    assert kalender.nutzer_zu_token(con, neu) == nid


def test_path_of_the_address():
    assert kalender.pfad("abc") == "/kalender/abc.ics"
