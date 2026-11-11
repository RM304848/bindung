"""Push: Schluessel, Abos und das Senden (PLAN.md, Abschnitt 10). `webpush` ist ersetzt."""

from __future__ import annotations

import base64
import json
import os
import stat
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02
from pywebpush import WebPushException

from bindung import auth, pfade, push
from bindung.personen import EingabeFehler

from .conftest import PASSWORT


def b64(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode()


def browser_schluessel() -> tuple[str, str]:
    """Ein echtes Schluesselpaar, wie es ein Browser meldet: (p256dh, auth)."""
    privat = ec.generate_private_key(ec.SECP256R1())
    roh = privat.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return b64(roh), b64(os.urandom(16))


ENDPUNKT = "https://push.example.test/v1/abcdef"


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def abo(con, nid):
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, nid, ENDPUNKT, p256dh, auth_)
    return push.abos(con, nid)[0]


# --------------------------------------------------------------- Schluessel

def test_keys_are_made_on_first_use_and_read_afterwards(daten):
    assert not pfade.VAPID_PATH.exists()
    erster = push.schluessel()
    assert pfade.VAPID_PATH.exists()
    assert push.schluessel() == erster          # gelesen, nicht neu erzeugt
    assert push.oeffentlicher_schluessel() == erster["oeffentlich"]


def test_the_file_is_private_to_the_owner(daten):
    push.schluessel()
    assert stat.S_IMODE(pfade.VAPID_PATH.stat().st_mode) == 0o600
    assert [p.name for p in pfade.VAPID_PATH.parent.iterdir()] == [pfade.VAPID_PATH.name]


def test_the_public_key_is_what_a_browser_expects(daten):
    oeffentlich = push.oeffentlicher_schluessel()
    assert "=" not in oeffentlich and "+" not in oeffentlich and "/" not in oeffentlich
    roh = base64.urlsafe_b64decode(oeffentlich + "=" * (-len(oeffentlich) % 4))
    assert len(roh) == 65 and roh[0] == 4       # unkomprimierter Punkt auf P-256


def test_the_stored_private_key_belongs_to_the_public_one(daten):
    daten_ = push.schluessel()
    vapid = Vapid02.from_pem(daten_["privat_pem"].encode())
    assert push._oeffentlich(vapid) == daten_["oeffentlich"]
    assert json.loads(pfade.VAPID_PATH.read_text())["sub"] == "mailto:bindung@localhost"


def test_pywebpush_signs_with_the_stored_key(daten, monkeypatch):
    """Die Schluessel passen wirklich zu pywebpush (curl=True sendet nichts)."""
    monkeypatch.chdir(daten.parent)   # curl=True schreibt `encrypted.data` ins Arbeitsverzeichnis
    daten.parent.mkdir(exist_ok=True)
    from pywebpush import webpush

    p256dh, auth_ = browser_schluessel()
    text = webpush({"endpoint": ENDPUNKT, "keys": {"p256dh": p256dh, "auth": auth_}}, "x",
                   vapid_private_key=Vapid02.from_pem(push.schluessel()["privat_pem"].encode()),
                   vapid_claims={"sub": push.kontakt()}, curl=True)
    assert "authorization: vapid" in text and ENDPUNKT in text


def test_a_second_start_does_not_overwrite_the_first(daten):
    erster = push.schluessel()
    assert push._ablegen(push._erzeugen()) is False
    assert push.schluessel() == erster


def test_an_incomplete_file_is_an_error_not_a_new_key(daten):
    pfade.VAPID_PATH.parent.mkdir(parents=True)
    pfade.VAPID_PATH.write_text(json.dumps({"oeffentlich": "x"}))
    with pytest.raises(ValueError):
        push.schluessel()


def test_the_contact_comes_from_the_environment(daten, monkeypatch):
    assert push.kontakt() == "mailto:bindung@localhost"
    monkeypatch.setenv("BINDUNG_PUSH_KONTAKT", "mailto:server@example.test")
    assert push.kontakt() == "mailto:server@example.test"


# --------------------------------------------------------------------- Abos

def test_saving_the_same_endpoint_twice_keeps_one_row(con, nid):
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, nid, ENDPUNKT, p256dh, auth_)
    neu_p256dh, neu_auth = browser_schluessel()
    push.abo_speichern(con, nid, ENDPUNKT, neu_p256dh, neu_auth)
    zeilen = push.abos(con, nid)
    assert len(zeilen) == 1 and zeilen[0]["schluessel_p256dh"] == neu_p256dh


def test_a_browser_that_changes_user_changes_owner(con, nid):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, nid, ENDPUNKT, p256dh, auth_)
    push.abo_speichern(con, anderer, ENDPUNKT, p256dh, auth_)
    assert push.abos_zaehlen(con, nid) == 0 and push.abos_zaehlen(con, anderer) == 1


def test_deleting_only_touches_the_own_subscription(con, nid):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, anderer, ENDPUNKT, p256dh, auth_)
    assert push.abo_loeschen(con, nid, ENDPUNKT) is False
    assert push.abos_zaehlen(con, anderer) == 1
    assert push.abo_loeschen(con, anderer, ENDPUNKT) is True
    assert push.abo_loeschen(con, anderer, ENDPUNKT) is False


@pytest.mark.parametrize("endpunkt", [
    "", "http://push.example.test/x", "ftp://push.example.test/x", "https://",
    "https://127.0.0.1/x", "https://10.0.0.5/x", "https://[::1]/x", "https://localhost/x",
    "https://nas.local/x", "https://dienst.internal/x", "https://push.example.test/" + "x" * 2100,
    "javascript:alert(1)"])
def test_endpoints_must_be_public_https(con, nid, endpunkt):
    p256dh, auth_ = browser_schluessel()
    with pytest.raises(EingabeFehler):
        push.abo_speichern(con, nid, endpunkt, p256dh, auth_)
    assert push.abos_zaehlen(con, nid) == 0


@pytest.mark.parametrize("p256dh, auth_", [("", "abc"), ("abc", ""), ("a b", "abc"),
                                           ("abc", "x" * 300), (None, None)])
def test_keys_must_be_base64url(con, nid, p256dh, auth_):
    with pytest.raises(EingabeFehler):
        push.abo_speichern(con, nid, ENDPUNKT, p256dh, auth_)


# ------------------------------------------------------------------- Senden

class Webpush:
    """Ersetzt `push.webpush` und merkt sich die Aufrufe."""

    def __init__(self, fehler: Exception | None = None) -> None:
        self.aufrufe: list[dict] = []
        self.fehler = fehler

    def __call__(self, **kwargs):
        self.aufrufe.append(kwargs)
        if self.fehler:
            raise self.fehler
        return SimpleNamespace(status_code=201)


def antwort(status: int) -> WebPushException:
    return WebPushException(f"Push failed: {status}", response=SimpleNamespace(status_code=status))


def test_a_good_send_hands_over_the_payload(con, abo, monkeypatch):
    ersatz = Webpush()
    monkeypatch.setattr(push, "webpush", ersatz)
    nutzlast = {"titel": "Bindung", "text": "Zöe wartet", "url": "/", "tag": "tagesmeldung"}
    assert push.senden(con, abo, nutzlast) is True
    aufruf = ersatz.aufrufe[0]
    assert aufruf["subscription_info"] == {
        "endpoint": ENDPUNKT,
        "keys": {"p256dh": abo["schluessel_p256dh"], "auth": abo["schluessel_auth"]}}
    assert json.loads(aufruf["data"]) == nutzlast
    assert aufruf["vapid_claims"] == {"sub": "mailto:bindung@localhost"}
    assert aufruf["ttl"] == push.LEBENSDAUER_SEKUNDEN and aufruf["timeout"] == push.WARTEN_SEKUNDEN


@pytest.mark.parametrize("status", [404, 410])
def test_a_dead_subscription_is_deleted(con, nid, abo, monkeypatch, status):
    monkeypatch.setattr(push, "webpush", Webpush(antwort(status)))
    assert push.senden(con, abo, {"titel": "Bindung"}) is False
    assert push.abos_zaehlen(con, nid) == 0


@pytest.mark.parametrize("fehler", [antwort(500), antwort(429), antwort(403),
                                    WebPushException("kein Netz"), OSError("kein Netz"),
                                    ValueError("kaputt")])
def test_any_other_failure_keeps_the_subscription(con, nid, abo, monkeypatch, caplog, fehler):
    monkeypatch.setattr(push, "webpush", Webpush(fehler))
    with caplog.at_level("WARNING"):
        assert push.senden(con, abo, {"titel": "Bindung"}) is False
    assert push.abos_zaehlen(con, nid) == 1
    assert "fehlgeschlagen" in caplog.text


def test_deleting_a_dead_subscription_leaves_the_others(con, nid, abo, monkeypatch):
    p256dh, auth_ = browser_schluessel()
    push.abo_speichern(con, nid, ENDPUNKT + "2", p256dh, auth_)
    monkeypatch.setattr(push, "webpush", Webpush(antwort(410)))
    push.senden(con, abo, {"titel": "Bindung"})
    assert [z["endpunkt"] for z in push.abos(con, nid)] == [ENDPUNKT + "2"]
