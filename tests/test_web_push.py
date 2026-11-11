"""Push im Web: Abos, Service Worker, Hinweis, Testmeldung (PLAN.md, Abschnitt 10).

Die Uhr steht auf Mittwoch, 11. November 2026. `webpush` ist ersetzt.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from bindung import auth, kontakte, personen, push, tagesmeldung

from .conftest import PASSWORT
from .test_push import ENDPUNKT, Webpush, antwort, browser_schluessel

JETZT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)
HEUTE = dt.date(2026, 11, 11)
HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt", lambda: JETZT)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def ersatz(monkeypatch) -> Webpush:
    ersatz = Webpush()
    monkeypatch.setattr(push, "webpush", ersatz)
    return ersatz


def abo_koerper(endpunkt: str = ENDPUNKT) -> dict:
    p256dh, auth_ = browser_schluessel()
    return {"endpoint": endpunkt, "expirationTime": None, "keys": {"p256dh": p256dh,
                                                                  "auth": auth_}}


def wartende(con, nid: int, name: str = "Anna Beispiel") -> int:
    pid = personen.anlegen(con, nid, name)
    kontakte.eintragen(con, nid, pid, datum=HEUTE - dt.timedelta(days=80), art="anruf")
    return pid


def abo_anlegen(con, nid: int, endpunkt: str = ENDPUNKT) -> None:
    koerper = abo_koerper(endpunkt)
    push.abo_speichern(con, nid, endpunkt, koerper["keys"]["p256dh"], koerper["keys"]["auth"])


# ------------------------------------------------------------------ Anmeldung

@pytest.mark.parametrize("methode, pfad", [
    ("get", "/push/schluessel"), ("post", "/push/abo"), ("delete", "/push/abo"),
    ("post", "/push/test"), ("post", "/hinweis/weggeklickt"),
    ("get", "/einstellungen/benachrichtigungen")])
def test_everything_but_the_worker_needs_login(client, methode, pfad):
    antwort_ = getattr(client, methode)(pfad)
    assert antwort_.status_code == 303 and antwort_.headers["location"] == "/anmeldung"


def test_the_public_key_is_served(angemeldet):
    antwort_ = angemeldet.get("/push/schluessel")
    assert antwort_.status_code == 200
    assert antwort_.json() == {"schluessel": push.oeffentlicher_schluessel()}
    assert "no-store" in antwort_.headers["cache-control"]


def test_subscribing_stores_the_subscription_once(angemeldet, con, nid):
    koerper = abo_koerper()
    for _ in range(2):
        assert angemeldet.post("/push/abo", json=koerper).status_code == 204
    zeilen = push.abos(con, nid)
    assert len(zeilen) == 1 and zeilen[0]["endpunkt"] == ENDPUNKT
    assert zeilen[0]["schluessel_auth"] == koerper["keys"]["auth"]


def test_unsubscribing_removes_it_and_is_idempotent(angemeldet, con, nid):
    angemeldet.post("/push/abo", json=abo_koerper())
    for _ in range(2):
        assert angemeldet.request("DELETE", "/push/abo", json={"endpoint": ENDPUNKT}
                                  ).status_code == 204
    assert push.abos_zaehlen(con, nid) == 0


@pytest.mark.parametrize("koerper", [
    {}, {"endpoint": ENDPUNKT}, {"endpoint": ENDPUNKT, "keys": "nein"},
    {"endpoint": "http://push.example.test/x", "keys": {"p256dh": "abc", "auth": "abc"}},
    {"endpoint": "https://127.0.0.1/x", "keys": {"p256dh": "abc", "auth": "abc"}},
    {"endpoint": ENDPUNKT, "keys": {"p256dh": "a b", "auth": "abc"}}, [], "text"])
def test_a_bad_subscription_is_refused_with_a_reason(angemeldet, con, nid, koerper):
    antwort_ = angemeldet.post("/push/abo", json=koerper)
    assert antwort_.status_code == 422 and antwort_.json()["fehler"]
    assert push.abos_zaehlen(con, nid) == 0


def test_a_body_that_is_not_json_is_refused(angemeldet):
    antwort_ = angemeldet.post("/push/abo", content=b"kein json",
                               headers={"Content-Type": "application/json"})
    assert antwort_.status_code == 422
    assert angemeldet.request("DELETE", "/push/abo", content=b"{").status_code == 422


def test_one_user_neither_counts_nor_removes_the_others_browsers(angemeldet, con, nid):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    abo_anlegen(con, anderer, "https://push.example.test/anderer")
    abo_anlegen(con, nid)
    assert "<strong>1</strong>" in angemeldet.get("/einstellungen").text
    # Fremden Endpunkt abmelden: 204 (wie jeder unbekannte), aber nichts passiert.
    angemeldet.request("DELETE", "/push/abo", json={"endpoint": "https://push.example.test/anderer"})
    assert push.abos_zaehlen(con, anderer) == 1 and push.abos_zaehlen(con, nid) == 1


# ------------------------------------------------------------ Service Worker

def test_the_worker_is_served_from_the_root_without_cache(client):
    antwort_ = client.get("/sw.js")    # ohne Anmeldung
    assert antwort_.status_code == 200
    assert antwort_.headers["content-type"].startswith("text/javascript")
    assert antwort_.headers["cache-control"] == "no-cache"
    assert antwort_.headers["service-worker-allowed"] == "/"
    assert 'addEventListener("push"' in antwort_.text
    assert 'addEventListener("notificationclick"' in antwort_.text


def test_the_worker_only_handles_push(client):
    """Kein Offline-Betrieb in v1: kein `fetch`-Ereignis, kein Cache (PLAN.md, Abschnitt 7)."""
    text = client.get("/sw.js").text
    assert 'addEventListener("fetch"' not in text and "caches." not in text
    assert 'tag: daten.tag || "tagesmeldung"' in text


# --------------------------------------------------------------------- Hinweis

def test_the_hinweis_shows_the_digest_above_the_app(angemeldet, con, nid):
    wartende(con, nid)
    seite = angemeldet.get("/").text
    assert 'id="hinweis"' in seite and "1 Person wartet" in seite and "Anna Beispiel" in seite
    assert seite.index('id="hinweis"') < seite.index('id="app"')
    assert "data-hinweis hidden" not in seite          # ohne Abo sofort sichtbar
    assert "Benachrichtigungen erlauben" in seite and "Heute ausblenden" in seite
    assert "Dock" in seite                              # der Satz fuer Safari


def test_no_hinweis_when_there_is_nothing_to_say(angemeldet, con, nid):
    personen.anlegen(con, nid, "Anna Beispiel")
    assert 'id="hinweis"' not in angemeldet.get("/").text


def test_dismissing_hides_it_for_today_only(angemeldet, con, nid, monkeypatch):
    wartende(con, nid)
    assert angemeldet.post("/hinweis/weggeklickt", headers=HX).text == ""
    assert tagesmeldung.hinweis_weggeklickt(con, nid, HEUTE)
    assert 'id="hinweis"' not in angemeldet.get("/").text
    monkeypatch.setattr(personen, "_jetzt", lambda: JETZT + dt.timedelta(days=1))
    assert 'id="hinweis"' in angemeldet.get("/").text


def test_dismissing_without_script_goes_back_to_the_start(angemeldet, con, nid):
    wartende(con, nid)
    antwort_ = angemeldet.post("/hinweis/weggeklickt")
    assert antwort_.status_code == 303 and antwort_.headers["location"] == "/"


def test_dismissal_belongs_to_the_user(angemeldet, con, nid):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    angemeldet.post("/hinweis/weggeklickt", headers=HX)
    assert not tagesmeldung.hinweis_weggeklickt(con, anderer, HEUTE)


def test_with_a_subscription_the_hinweis_waits_for_the_browser_to_decide(angemeldet, con, nid):
    """Der Server weiss nur, dass es irgendwo ein Abo gibt; ob DIESER Browser eines hat, sagt
    bindung.js. Bis dahin ist der Streifen versteckt (`hidden`), nicht entfernt."""
    wartende(con, nid)
    abo_anlegen(con, nid)
    assert "data-hinweis hidden" in angemeldet.get("/").text


def test_the_hinweis_is_not_part_of_list_answers(angemeldet, con, nid):
    wartende(con, nid)
    assert 'id="hinweis"' not in angemeldet.get("/liste?karte=aufmerksamkeit", headers=HX).text


def test_permission_is_asked_only_inside_the_click_handler_chain(client):
    """Die Erlaubnis fragt nur ein Klick: `requestPermission` steht einmal, in `pushAktivieren`,
    und das wird nur vom Klick auf `data-push-aktivieren` aufgerufen -- nie beim Laden."""
    skript = client.get("/statisch/bindung.js").text
    assert skript.count("requestPermission()") == 1
    kopf = skript[:skript.index("requestPermission()")].rsplit("function ", 1)[-1]
    assert kopf.startswith("pushAktivieren(")
    aufrufe = [z.strip() for z in skript.splitlines()
               if "pushAktivieren()" in z and "function pushAktivieren" not in z]
    assert aufrufe == ["(an ? pushAktivieren() : pushDeaktivieren()).then(function () {"]


# ------------------------------------------------------------- Einstellungen

def test_the_settings_block_shows_the_count_and_a_disabled_test_button(angemeldet):
    seite = angemeldet.get("/einstellungen").text
    assert 'id="einstellung-benachrichtigungen"' in seite
    assert "Angemeldete Browser: <strong>0</strong>" in seite
    assert "In diesem Browser aktivieren" in seite and "Deaktivieren" in seite
    assert "data-push-status" in seite
    assert 'class="knopf" disabled>Testmeldung senden' in seite
    assert "Dock" in seite


def test_the_count_and_the_test_button_follow_the_subscriptions(angemeldet, con, nid):
    abo_anlegen(con, nid)
    abo_anlegen(con, nid, "https://push.example.test/zweites")
    seite = angemeldet.get("/einstellungen").text
    assert "Angemeldete Browser: <strong>2</strong>" in seite
    assert "disabled>Testmeldung senden" not in seite


def test_the_section_alone_is_for_htmx(angemeldet, con, nid):
    abo_anlegen(con, nid)
    teil = angemeldet.get("/einstellungen/benachrichtigungen", headers=HX)
    assert teil.status_code == 200 and teil.text.lstrip().startswith("<section")
    assert "<strong>1</strong>" in teil.text and "<html" not in teil.text
    ganz = angemeldet.get("/einstellungen/benachrichtigungen")
    assert ganz.status_code == 303 and ganz.headers["location"] == "/einstellungen"


# ----------------------------------------------------------------- Testmeldung

def test_the_test_message_goes_to_every_browser(angemeldet, con, nid, ersatz):
    abo_anlegen(con, nid)
    abo_anlegen(con, nid, "https://push.example.test/zweites")
    antwort_ = angemeldet.post("/push/test", headers=HX)
    assert antwort_.status_code == 200
    assert "Testmeldung an 2 Browser gesendet." in antwort_.text
    assert len(ersatz.aufrufe) == 2
    nutzlast = json.loads(ersatz.aufrufe[0]["data"])
    assert nutzlast["titel"] == "Bindung" and nutzlast["tag"] == "tagesmeldung"
    assert nutzlast["text"].startswith("Testmeldung")


def test_the_test_message_goes_only_to_the_own_browsers(angemeldet, con, nid, ersatz):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    abo_anlegen(con, anderer, "https://push.example.test/anderer")
    abo_anlegen(con, nid)
    angemeldet.post("/push/test", headers=HX)
    assert [a["subscription_info"]["endpoint"] for a in ersatz.aufrufe] == [ENDPUNKT]


def test_a_single_browser_is_named_in_the_singular(angemeldet, con, nid, ersatz):
    abo_anlegen(con, nid)
    assert "Testmeldung an 1 Browser gesendet." in angemeldet.post("/push/test", headers=HX).text


def test_without_browsers_the_test_says_so_and_sends_nothing(angemeldet, ersatz):
    antwort_ = angemeldet.post("/push/test", headers=HX)
    assert "Es ist noch kein Browser angemeldet." in antwort_.text and ersatz.aufrufe == []


def test_a_failed_test_is_reported_and_a_dead_browser_is_dropped(angemeldet, con, nid,
                                                                  monkeypatch):
    abo_anlegen(con, nid)
    abo_anlegen(con, nid, "https://push.example.test/tot")

    def webpush(**kwargs):
        if kwargs["subscription_info"]["endpoint"].endswith("/tot"):
            raise antwort(410)

    monkeypatch.setattr(push, "webpush", webpush)
    teil = angemeldet.post("/push/test", headers=HX).text
    assert "Nur 1 von 2 Browser" in teil and "meldung-fehler" in teil
    assert push.abos_zaehlen(con, nid) == 1
    assert "<strong>1</strong>" in teil               # die Zahl ist schon die neue


def test_the_test_without_script_answers_with_the_whole_page(angemeldet, con, nid, ersatz):
    abo_anlegen(con, nid)
    seite = angemeldet.post("/push/test")
    assert seite.status_code == 200 and "<html" in seite.text
    assert "Testmeldung an 1 Browser gesendet." in seite.text
