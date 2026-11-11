"""Die Tagesaufgabe: `tick(con, jetzt)` mit festen Uhren (PLAN.md, Abschnitt 10).

Der Tag ist Mittwoch, der 11. November 2026. Berlin ist dann UTC+1, Los Angeles UTC-8.
Die Uhrzeit der Tagesmeldung ist 08:00 in der Zeitzone des Nutzers.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from bindung import auth, db, kontakte, personen, push, tagesaufgabe, tagesmeldung

from .conftest import PASSWORT
from .test_push import ENDPUNKT, Webpush, antwort, browser_schluessel

TAG = dt.date(2026, 11, 11)


def utc(stunde: int, minute: int = 0, tag: dt.date = TAG) -> dt.datetime:
    return dt.datetime(tag.year, tag.month, tag.day, stunde, minute, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    """`personen.heute` (fuer Kontakte eintragen) laeuft auf demselben Tag wie die Tests."""
    monkeypatch.setattr(personen, "_jetzt", lambda: utc(12))


@pytest.fixture
def ersatz(monkeypatch) -> Webpush:
    ersatz = Webpush()
    monkeypatch.setattr(push, "webpush", ersatz)
    return ersatz


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def wartende(con, nid: int, name: str = "Anna Beispiel") -> int:
    """Eine Person, die wartet (80 Tage ohne Kontakt bei 56 Tagen Intervall)."""
    pid = personen.anlegen(con, nid, name)
    kontakte.eintragen(con, nid, pid, datum=TAG - dt.timedelta(days=80), art="anruf")
    return pid


def abo(con, nid: int, endpunkt: str = ENDPUNKT) -> None:
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, nid, endpunkt, p256dh, auth_)


def einstellen(con, nid: int, *, zeit: str = "08:00", zone: str = "Europe/Berlin") -> None:
    con.execute("UPDATE nutzer SET tagesmeldung_zeit = ?, zeitzone = ? WHERE id = ?",
                (zeit, zone, nid))
    con.commit()


def versand_am(con, nid: int) -> str | None:
    zeile = con.execute("SELECT letzter_versand_am FROM digest_protokoll WHERE nutzer_id = ?",
                        (nid,)).fetchone()
    return zeile["letzter_versand_am"] if zeile else None


@pytest.fixture
def bereit(con, nid):
    """Ein Nutzer mit einer wartenden Person und einem Abo."""
    wartende(con, nid)
    abo(con, nid)
    return nid


# ------------------------------------------------------------ vor und nach der Uhrzeit

def test_nothing_happens_before_the_users_time(con, bereit, ersatz):
    assert tagesaufgabe.tick(con, utc(6, 59)) == []      # 07:59 in Berlin
    assert ersatz.aufrufe == [] and versand_am(con, bereit) is None


def test_the_digest_goes_out_at_the_users_time(con, bereit, ersatz):
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))         # 08:00 in Berlin
    assert [(e.nutzer_id, e.tag, e.meldung, e.abos, e.gesendet) for e in ergebnis] == \
        [(bereit, TAG, True, 1, 1)]
    assert len(ersatz.aufrufe) == 1
    nutzlast = json.loads(ersatz.aufrufe[0]["data"])
    assert nutzlast == {"titel": "Bindung", "text": "1 Person wartet\nAnna Beispiel",
                        "url": "/?karte=aufmerksamkeit", "tag": "tagesmeldung",
                        "icon": "/statisch/symbol-192.png"}
    assert versand_am(con, bereit) == "2026-11-11"


def test_a_late_start_still_sends_the_same_day(con, bereit, ersatz):
    """Der Server lief um 8 Uhr nicht, startet um 17 Uhr: die Meldung kommt noch heute."""
    tagesaufgabe.tick(con, utc(16, 0))
    assert len(ersatz.aufrufe) == 1


def test_only_once_per_day(con, bereit, ersatz):
    tagesaufgabe.tick(con, utc(7, 0))
    for minute in (1, 2, 59):
        assert tagesaufgabe.tick(con, utc(7, minute)) == []
    assert tagesaufgabe.tick(con, utc(20, 0)) == []
    assert len(ersatz.aufrufe) == 1


def test_the_next_day_sends_again(con, bereit, ersatz):
    tagesaufgabe.tick(con, utc(7, 0))
    morgen = TAG + dt.timedelta(days=1)
    assert tagesaufgabe.tick(con, utc(6, 0, morgen)) == []         # noch vor 08:00
    assert len(tagesaufgabe.tick(con, utc(7, 0, morgen))) == 1
    assert len(ersatz.aufrufe) == 2 and versand_am(con, bereit) == "2026-11-12"


def test_a_missed_day_is_not_sent_in_arrears(con, bereit, ersatz):
    """Der Server war am 11. aus und laeuft erst am 13.: nur der 13. wird gesendet."""
    uebermorgen = TAG + dt.timedelta(days=2)
    ergebnis = tagesaufgabe.tick(con, utc(9, 0, uebermorgen))
    assert [e.tag for e in ergebnis] == [uebermorgen]
    assert len(ersatz.aufrufe) == 1


def test_midnight_zero_means_the_first_tick_of_the_day(con, bereit, ersatz):
    einstellen(con, bereit, zeit="00:00")
    assert len(tagesaufgabe.tick(con, utc(23, 0, TAG - dt.timedelta(days=1)))) == 1   # 00:00 Berlin


# ------------------------------------------------------------ Zeitzonen

def test_the_day_and_the_hour_are_the_users_not_the_servers(con, bereit, ersatz):
    # 23:30 UTC am 11. ist in Berlin schon der 12., 00:30: vor 08:00, also nichts.
    assert tagesaufgabe.tick(con, utc(23, 30)) == []
    # 07:00 UTC am 12. ist in Berlin 08:00 am 12.: gesendet, als Tag zaehlt der 12.
    ergebnis = tagesaufgabe.tick(con, utc(7, 0, TAG + dt.timedelta(days=1)))
    assert [e.tag for e in ergebnis] == [dt.date(2026, 11, 12)]


def test_two_zones_get_their_digest_at_their_own_hour(con, bereit, ersatz):
    kalifornien = auth.nutzer_anlegen(con, "Westkueste", PASSWORT)
    einstellen(con, kalifornien, zone="America/Los_Angeles")
    wartende(con, kalifornien, "Ben Muster")
    abo(con, kalifornien, "https://push.example.test/westkueste")
    # 07:00 UTC: Berlin 08:00 am 11.; in Los Angeles ist es 23:00 am 10., die Uhrzeit des
    # 10. ist laengst vorbei -- der Server startet spaet, der 10. wird noch gesendet.
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert [(e.nutzer_id, e.tag) for e in ergebnis] == [
        (bereit, TAG), (kalifornien, dt.date(2026, 11, 10))]
    # 15:59 UTC ist in Los Angeles 07:59 am 11.: noch nichts.
    assert tagesaufgabe.tick(con, utc(15, 59)) == []
    # 16:00 UTC: Los Angeles 08:00, jetzt der 11.
    ergebnis = tagesaufgabe.tick(con, utc(16, 0))
    assert [(e.nutzer_id, e.tag) for e in ergebnis] == [(kalifornien, TAG)]
    assert versand_am(con, kalifornien) == "2026-11-11"


def test_an_unknown_zone_falls_back_to_berlin(con, bereit, ersatz):
    con.execute("UPDATE nutzer SET zeitzone = 'Nirgendwo/Stadt' WHERE id = ?", (bereit,))
    con.commit()
    assert len(tagesaufgabe.tick(con, utc(7, 0))) == 1


# ------------------------------------------------------------ nichts zu sagen, keine Abos

def test_nothing_due_sends_nothing_but_still_records_the_day(con, nid, ersatz):
    abo(con, nid)
    personen.anlegen(con, nid, "Anna Beispiel")       # unbekannt: wartet nicht
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert [(e.meldung, e.gesendet) for e in ergebnis] == [(False, 0)]
    assert ersatz.aufrufe == [] and versand_am(con, nid) == "2026-11-11"
    # Wer spaeter am Tag faellig wird, bekommt heute nichts mehr: der Tag ist abgehakt.
    wartende(con, nid, "Ben Muster")
    assert tagesaufgabe.tick(con, utc(9, 0)) == [] and ersatz.aufrufe == []


def test_no_subscription_means_no_push_but_the_day_is_recorded(con, nid, ersatz):
    wartende(con, nid)
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert [(e.abos, e.gesendet) for e in ergebnis] == [(0, 0)]
    assert ersatz.aufrufe == [] and versand_am(con, nid) == "2026-11-11"


# ------------------------------------------------------------ mehrere Nutzer und Abos

def test_two_users_get_their_own_digest(con, bereit, ersatz):
    zweiter = auth.nutzer_anlegen(con, "Zweiter", PASSWORT)
    wartende(con, zweiter, "Ben Muster")
    abo(con, zweiter, "https://push.example.test/zweiter")
    tagesaufgabe.tick(con, utc(7, 0))
    texte = {a["subscription_info"]["endpoint"]: json.loads(a["data"])["text"]
             for a in ersatz.aufrufe}
    assert texte == {ENDPUNKT: "1 Person wartet\nAnna Beispiel",
                     "https://push.example.test/zweiter": "1 Person wartet\nBen Muster"}


def test_every_subscription_of_the_user_gets_it(con, bereit, ersatz):
    abo(con, bereit, "https://push.example.test/zweites-geraet")
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert (ergebnis[0].abos, ergebnis[0].gesendet) == (2, 2)
    assert len(ersatz.aufrufe) == 2


def test_a_dead_subscription_is_dropped_and_the_others_still_get_it(con, bereit, monkeypatch):
    abo(con, bereit, "https://push.example.test/tot")
    aufrufe = []

    def webpush(**kwargs):
        aufrufe.append(kwargs["subscription_info"]["endpoint"])
        if kwargs["subscription_info"]["endpoint"].endswith("/tot"):
            raise antwort(410)

    monkeypatch.setattr(push, "webpush", webpush)
    ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert (ergebnis[0].abos, ergebnis[0].gesendet) == (2, 1)
    assert [a["endpunkt"] for a in push.abos(con, bereit)] == [ENDPUNKT]


# ------------------------------------------------------------ Sicherheit des Laufs

def test_two_processes_do_not_send_twice(con, bereit, ersatz):
    """Der zweite Prozess (anderes Verbindungsobjekt) sieht den Tag schon vergeben."""
    zweite = db.verbinden()
    try:
        assert len(tagesaufgabe.tick(con, utc(7, 0))) == 1
        assert tagesaufgabe.tick(zweite, utc(7, 0)) == []
    finally:
        zweite.close()
    assert len(ersatz.aufrufe) == 1


def test_claiming_the_day_is_one_atomic_step(con, nid):
    assert tagesaufgabe._beanspruchen(con, nid, TAG) is True
    assert tagesaufgabe._beanspruchen(con, nid, TAG) is False
    assert tagesaufgabe._beanspruchen(con, nid, TAG + dt.timedelta(days=1)) is True


def test_one_failing_user_does_not_stop_the_others(con, bereit, ersatz, monkeypatch, caplog):
    zweiter = auth.nutzer_anlegen(con, "Zweiter", PASSWORT)
    wartende(con, zweiter, "Ben Muster")
    abo(con, zweiter, "https://push.example.test/zweiter")
    echt = tagesmeldung.bauen

    def bauen(con_, nutzer_id, heute):
        if nutzer_id == bereit:
            raise RuntimeError("kaputt")
        return echt(con_, nutzer_id, heute)

    monkeypatch.setattr(tagesmeldung, "bauen", bauen)
    with caplog.at_level("ERROR"):
        ergebnis = tagesaufgabe.tick(con, utc(7, 0))
    assert [e.nutzer_id for e in ergebnis] == [zweiter]
    assert "kaputt" in caplog.text


def test_dismissing_the_hinweis_is_not_undone_by_the_tick(con, bereit, ersatz):
    tagesmeldung.hinweis_wegklicken(con, bereit, TAG)
    tagesaufgabe.tick(con, utc(7, 0))
    zeile = con.execute("SELECT * FROM digest_protokoll WHERE nutzer_id = ?", (bereit,)).fetchone()
    assert (zeile["letzter_versand_am"], zeile["hinweis_weggeklickt_am"]) == \
        ("2026-11-11", "2026-11-11")


# ------------------------------------------------------------ die Schleife

def test_one_run_uses_its_own_connection_and_the_real_clock(daten, nutzer, monkeypatch):
    jetzt = []
    monkeypatch.setattr(tagesaufgabe, "tick", lambda con, zeit: jetzt.append((con, zeit)))
    tagesaufgabe._durchlauf()
    (con, zeit), = jetzt
    assert zeit.tzinfo is not None
    with pytest.raises(Exception, match="closed"):
        con.execute("SELECT 1")


def test_the_loop_ticks_repeatedly_and_survives_an_error(monkeypatch, caplog):
    aufrufe = []

    def durchlauf():
        aufrufe.append(1)
        if len(aufrufe) == 1:
            raise RuntimeError("einmal kaputt")

    monkeypatch.setattr(tagesaufgabe, "_durchlauf", durchlauf)
    monkeypatch.setattr(tagesaufgabe, "INTERVALL_SEKUNDEN", 0.01)

    async def lauf():
        async with tagesaufgabe.laufen() as aufgabe:
            assert aufgabe is not None
            while len(aufrufe) < 3:
                await asyncio.sleep(0.01)
        assert aufgabe.cancelled() or aufgabe.done()

    monkeypatch.setenv("BINDUNG_TAGESAUFGABE", "1")
    with caplog.at_level("ERROR"):
        asyncio.run(asyncio.wait_for(lauf(), 5))
    assert len(aufrufe) >= 3 and "einmal kaputt" in caplog.text


def test_the_loop_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("BINDUNG_TAGESAUFGABE", "0")

    async def lauf():
        async with tagesaufgabe.laufen() as aufgabe:
            return aufgabe

    assert asyncio.run(lauf()) is None


def test_the_app_starts_and_stops_the_task(monkeypatch):
    from fastapi.testclient import TestClient

    from bindung.web.server import app

    aufrufe = []
    monkeypatch.setenv("BINDUNG_TAGESAUFGABE", "1")
    monkeypatch.setattr(tagesaufgabe, "_durchlauf", lambda: aufrufe.append(1))
    monkeypatch.setattr(tagesaufgabe, "INTERVALL_SEKUNDEN", 0.01)
    import time

    with TestClient(app):
        for _ in range(200):
            if aufrufe:
                break
            time.sleep(0.01)
    assert aufrufe
