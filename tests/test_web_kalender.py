"""Die Kalenderadresse und der Download (PLAN.md, Abschnitt 9).

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import auth, kalender, kontakte, personen, stichtage

from .conftest import PASSWORT
from .test_kalender import entfalten, lesen

HEUTE = dt.date(2026, 11, 11)
JETZT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt", lambda: JETZT)
    monkeypatch.setattr(kalender, "_jetzt", lambda: JETZT)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def token_von(con, nid: int) -> str:
    return con.execute("SELECT kalender_token FROM nutzer WHERE id = ?", (nid,)).fetchone()[0]


@pytest.fixture
def anna(con, nid) -> int:
    pid = personen.anlegen(con, nid, "Anna Beispiel")
    stichtage.anlegen(con, nid, pid, bezeichnung="", art="geburtstag", datum="--03-24")
    kontakte.eintragen(con, nid, pid, datum=HEUTE - dt.timedelta(days=10), art="anruf",
                       notiz="Reise nach Lissabon")
    return pid


def summen(text: str) -> set[str]:
    return {z[len("SUMMARY:"):] for z in entfalten(text) if z.startswith("SUMMARY:")}


# ---------------------------------------------------------------- Abonnement

def test_feed_works_without_login(client, con, nid, anna):
    antwort = client.get(kalender.pfad(token_von(con, nid)))
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "text/calendar; charset=utf-8"
    assert antwort.headers["cache-control"] == "private, no-store"
    assert "content-disposition" not in antwort.headers
    assert antwort.content.startswith(b"BEGIN:VCALENDAR\r\n")
    assert summen(antwort.text) == {"Geburtstag Anna Beispiel", "Melden bei Anna Beispiel"}
    assert len(lesen(antwort.text)) == 2


def test_feed_sets_no_session_cookie(client, con, nid):
    antwort = client.get(kalender.pfad(token_von(con, nid)))
    assert "set-cookie" not in antwort.headers


def test_unknown_token_is_a_plain_404(client, con, nid):
    nirgends = client.get("/kalender/a/b.ics")  # offene Tuer, aber keine Route dahinter
    assert nirgends.status_code == 404
    for pfad in ("/kalender/falsch.ics", "/kalender/.ics",
                 kalender.pfad(token_von(con, nid)[:-1]),
                 kalender.pfad(token_von(con, nid) + "x"),
                 kalender.pfad(token_von(con, nid).swapcase())):
        antwort = client.get(pfad)
        assert antwort.status_code == 404, pfad
        # Dieselbe Antwort wie fuer jede unbekannte Seite: kein Hinweis, wie nah der Versuch war.
        assert antwort.content == nirgends.content, pfad
        assert "BEGIN:VCALENDAR" not in antwort.text


def test_logged_in_user_gets_a_404_for_a_wrong_token_too(angemeldet):
    assert angemeldet.get("/kalender/falsch.ics").status_code == 404


def test_token_without_ics_is_not_an_open_door(client, con, nid):
    antwort = client.get(f"/kalender/{token_von(con, nid)}")
    assert antwort.status_code == 303 and antwort.headers["location"] == "/anmeldung"


def test_feed_follows_changes(client, con, nid, anna):
    pfad = kalender.pfad(token_von(con, nid))
    assert "Melden bei Anna Beispiel" in summen(client.get(pfad).text)
    personen.archivieren(con, nid, anna)
    assert client.get(pfad).text.count("BEGIN:VEVENT") == 0


# ------------------------------------------------------------------ Download

def test_download_needs_login(client):
    antwort = client.get("/kalender/herunterladen")
    assert antwort.status_code == 303 and antwort.headers["location"] == "/anmeldung"


def test_download_is_an_attachment_with_the_same_content(angemeldet, con, nid, anna):
    antwort = angemeldet.get("/kalender/herunterladen")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "text/calendar; charset=utf-8"
    assert antwort.headers["content-disposition"] == 'attachment; filename="bindung.ics"'
    assert antwort.headers["cache-control"] == "private, no-store"
    assert antwort.text == angemeldet.get(kalender.pfad(token_von(con, nid))).text


def test_download_is_not_reachable_with_a_dead_session(angemeldet):
    angemeldet.post("/abmelden")
    assert angemeldet.get("/kalender/herunterladen").status_code == 303


# ------------------------------------------------------------ neue Adresse

def test_rotated_address_kills_the_old_one(angemeldet, con, nid, anna):
    alt = kalender.pfad(token_von(con, nid))
    assert angemeldet.get(alt).status_code == 200
    antwort = angemeldet.post("/einstellungen/kalender/neu", headers={"HX-Request": "true"})
    assert antwort.status_code == 200
    neu = kalender.pfad(token_von(con, nid))
    assert neu != alt and neu in antwort.text and alt not in antwort.text
    anonym = type(angemeldet)(angemeldet.app, follow_redirects=False)
    try:
        assert anonym.get(alt).status_code == 404
        assert anonym.get(neu).status_code == 200
    finally:
        anonym.close()


# ------------------------------------------------------------ Trennung der Nutzer

def test_each_token_shows_only_its_own_people(client, con, nid, anna):
    fremd = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    bea = personen.anlegen(con, fremd, "Bea Fremd")
    stichtage.anlegen(con, fremd, bea, bezeichnung="", art="geburtstag", datum="--05-05")
    kontakte.eintragen(con, fremd, bea, datum=HEUTE - dt.timedelta(days=80), art="anruf",
                       notiz="Geheimer Plan")
    meins = client.get(kalender.pfad(token_von(con, nid))).text
    seins = client.get(kalender.pfad(token_von(con, fremd))).text
    assert "Anna" in meins and "Bea" not in meins and "Geheimer" not in meins
    assert "Bea" in seins and "Anna" not in seins and "Lissabon" not in seins
    assert token_von(con, nid) != token_von(con, fremd)
