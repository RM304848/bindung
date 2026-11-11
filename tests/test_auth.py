"""Passwort, Sitzung, Fehlversuche."""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import auth

from .conftest import PASSWORT


def test_hash_hin_und_zurueck():
    gespeichert = auth.passwort_hashen("ein-gutes-passwort")
    assert gespeichert.startswith("scrypt$")
    assert "ein-gutes-passwort" not in gespeichert
    assert auth.passwort_pruefen("ein-gutes-passwort", gespeichert)


def test_falsches_passwort_wird_abgelehnt():
    gespeichert = auth.passwort_hashen("ein-gutes-passwort")
    assert not auth.passwort_pruefen("ein-anderes-passwort", gespeichert)


def test_kaputter_hash_ist_kein_absturz():
    assert not auth.passwort_pruefen("x", "kein-hash")
    assert not auth.passwort_pruefen("x", "md5$1$2$3$ab$cd")


def test_jeder_nutzer_hat_sein_eigenes_salz():
    assert auth.passwort_hashen("gleich-gleich") != auth.passwort_hashen("gleich-gleich")


def test_nutzer_anlegen_prueft_name_und_laenge(con):
    with pytest.raises(auth.AuthFehler):
        auth.nutzer_anlegen(con, "  ", PASSWORT)
    with pytest.raises(auth.AuthFehler):
        auth.nutzer_anlegen(con, "Kurz", "1234567")
    auth.nutzer_anlegen(con, "Anna", PASSWORT)
    with pytest.raises(auth.AuthFehler):
        auth.nutzer_anlegen(con, "anna", PASSWORT)


def test_nutzer_bekommt_ein_geheimes_kalendertoken(con):
    auth.nutzer_anlegen(con, "Anna", PASSWORT)
    auth.nutzer_anlegen(con, "Ben", PASSWORT)
    token = [z["kalender_token"] for z in con.execute("SELECT kalender_token FROM nutzer")]
    assert len(set(token)) == 2
    assert all(len(t) >= 32 for t in token)


def test_anmelden_gibt_token_und_sitzung_gilt(con, nutzer):
    token = auth.anmelden(con, nutzer, PASSWORT)
    assert token
    assert auth.sitzung_pruefen(con, token)["name"] == nutzer
    assert con.execute("SELECT token_hash FROM sitzung").fetchone()[0] != token


def test_falsches_passwort_gibt_keine_sitzung(con, nutzer):
    assert auth.anmelden(con, nutzer, "falsch-falsch") is None
    assert auth.anmelden(con, "Niemand", PASSWORT) is None
    assert con.execute("SELECT COUNT(*) FROM sitzung").fetchone()[0] == 0


def test_unbekannter_token(con, nutzer):
    assert auth.sitzung_pruefen(con, None) is None
    assert auth.sitzung_pruefen(con, "gibt-es-nicht") is None


def test_abmelden_beendet_die_sitzung(con, nutzer):
    token = auth.anmelden(con, nutzer, PASSWORT)
    auth.abmelden(con, token)
    assert auth.sitzung_pruefen(con, token) is None


def _uhr(monkeypatch, start: dt.datetime) -> list[dt.datetime]:
    jetzt = [start]
    monkeypatch.setattr(auth, "_jetzt", lambda: jetzt[0])
    return jetzt


def test_sitzung_laeuft_nach_30_tagen_ab(con, nutzer, monkeypatch):
    jetzt = _uhr(monkeypatch, dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC))
    token = auth.anmelden(con, nutzer, PASSWORT)
    jetzt[0] += dt.timedelta(days=29)
    assert auth.sitzung_pruefen(con, token) is not None
    jetzt[0] += dt.timedelta(days=31)
    assert auth.sitzung_pruefen(con, token) is None
    assert con.execute("SELECT COUNT(*) FROM sitzung").fetchone()[0] == 0


def test_benutzung_erneuert_die_sitzung(con, nutzer, monkeypatch):
    jetzt = _uhr(monkeypatch, dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC))
    token = auth.anmelden(con, nutzer, PASSWORT)
    for _ in range(4):
        jetzt[0] += dt.timedelta(days=20)
        assert auth.sitzung_pruefen(con, token) is not None
    # 80 Tage seit der Anmeldung, aber nie 30 Tage ohne Benutzung
    erwartet = (jetzt[0] + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert con.execute("SELECT laeuft_ab_am FROM sitzung").fetchone()[0] == erwartet


def test_neues_passwort_beendet_alle_sitzungen(con, nutzer):
    token = auth.anmelden(con, nutzer, PASSWORT)
    auth.passwort_setzen(con, nutzer, "ein-neues-passwort")
    assert auth.sitzung_pruefen(con, token) is None
    assert auth.anmelden(con, nutzer, "ein-neues-passwort")


def test_wartezeit_waechst_mit_jedem_fehlversuch(con, nutzer, monkeypatch):
    jetzt = _uhr(monkeypatch, dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC))
    waehrend = []
    for _ in range(4):
        assert auth.anmelden(con, nutzer, "falsch-falsch") is None
        waehrend.append(auth.wartezeit(nutzer))
        jetzt[0] += dt.timedelta(seconds=waehrend[-1])
    assert waehrend == [1, 2, 4, 8]


def test_waehrend_der_sperre_hilft_auch_das_richtige_passwort_nicht(con, nutzer):
    auth.anmelden(con, nutzer, "falsch-falsch")
    with pytest.raises(auth.ZuVieleVersuche) as fehler:
        auth.anmelden(con, nutzer, PASSWORT)
    assert fehler.value.sekunden >= 1


def test_sperre_gilt_je_name_und_loest_sich(con, nutzer, monkeypatch):
    jetzt = _uhr(monkeypatch, dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC))
    auth.anmelden(con, nutzer, "falsch-falsch")
    auth.nutzer_anlegen(con, "Zweite", PASSWORT)
    assert auth.anmelden(con, "Zweite", PASSWORT)
    jetzt[0] += dt.timedelta(seconds=2)
    assert auth.anmelden(con, nutzer, PASSWORT)
    assert auth.wartezeit(nutzer) == 0


def test_auch_unbekannte_namen_werden_gebremst(con):
    auth.anmelden(con, "Niemand", "irgendwas-langes")
    assert auth.wartezeit("niemand") >= 1


def test_cookie_optionen(monkeypatch):
    monkeypatch.delenv("BINDUNG_SICHER", raising=False)
    optionen = auth.cookie_optionen()
    assert optionen["httponly"] is True
    assert optionen["samesite"] == "lax"
    assert optionen["secure"] is False
    monkeypatch.setenv("BINDUNG_SICHER", "1")
    assert auth.cookie_optionen()["secure"] is True


def _ablauf(con) -> str:
    return con.execute("SELECT laeuft_ab_am FROM sitzung").fetchone()[0]


def test_erneuerung_schreibt_hoechstens_einmal_am_tag(con, nutzer, monkeypatch):
    jetzt = _uhr(monkeypatch, dt.datetime(2026, 1, 1, 12, tzinfo=dt.UTC))
    token = auth.anmelden(con, nutzer, PASSWORT)
    anfang = _ablauf(con)
    # Ein Telefon fragt alle paar Minuten: die Zeile bleibt unberuehrt ...
    for _ in range(5):
        jetzt[0] += dt.timedelta(hours=3)
        assert auth.sitzung_pruefen(con, token) is not None
    assert _ablauf(con) == anfang
    # ... am naechsten Tag wird verlaengert, und danach wieder nicht.
    jetzt[0] += dt.timedelta(hours=10)
    assert auth.sitzung_pruefen(con, token) is not None
    verlaengert = _ablauf(con)
    assert verlaengert > anfang
    jetzt[0] += dt.timedelta(hours=1)
    assert auth.sitzung_pruefen(con, token) is not None
    assert _ablauf(con) == verlaengert
