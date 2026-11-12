"""Anmeldung, Sitzungs-Tuer und die leere Startseite."""

from __future__ import annotations

import re

from bindung import auth

from .conftest import PASSWORT


def test_startseite_verlangt_anmeldung(client):
    antwort = client.get("/")
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/anmeldung"


def test_alles_andere_verlangt_auch_anmeldung(client):
    for pfad in ("/einstellungen", "/gibt-es-nicht", "/person/1"):
        assert client.get(pfad).status_code == 303, pfad
    assert client.post("/abmelden").status_code == 303


def test_htmx_bekommt_eine_weiterleitung_im_kopf(client):
    antwort = client.get("/", headers={"HX-Request": "true"})
    assert antwort.status_code == 401
    assert antwort.headers["hx-redirect"] == "/anmeldung"


def test_statische_dateien_ohne_anmeldung(client):
    assert client.get("/statisch/stil.css").status_code == 200
    assert client.get("/statisch/htmx.min.js").status_code == 200


def test_anmeldeseite_ist_deutsch_mit_beschrifteten_feldern(client):
    antwort = client.get("/anmeldung")
    assert antwort.status_code == 200
    assert '<html lang="de" data-darstellung="system">' in antwort.text
    assert '<label for="name">Name</label>' in antwort.text
    assert '<label for="passwort">Passwort</label>' in antwort.text
    assert "Anmelden" in antwort.text


def test_falsches_passwort_gibt_401(client, nutzer):
    antwort = client.post("/anmeldung", data={"name": nutzer, "passwort": "falsch-falsch"})
    assert antwort.status_code == 401
    assert "Name oder Passwort stimmt nicht." in antwort.text
    assert auth.COOKIE not in antwort.headers.get("set-cookie", "")


def test_unbekannter_name_gibt_dieselbe_antwort(client, nutzer):
    antwort = client.post("/anmeldung", data={"name": "Niemand", "passwort": PASSWORT})
    assert antwort.status_code == 401
    assert "Name oder Passwort stimmt nicht." in antwort.text


def test_nach_fehlversuch_wird_gebremst(client, nutzer):
    client.post("/anmeldung", data={"name": nutzer, "passwort": "falsch-falsch"})
    antwort = client.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT})
    assert antwort.status_code == 429
    assert "Zu viele Versuche" in antwort.text


def test_anmeldung_setzt_cookie_mit_den_richtigen_merkmalen(client, nutzer):
    antwort = client.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT})
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/"
    cookie = antwort.headers["set-cookie"]
    assert cookie.startswith(f"{auth.COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie


def test_cookie_ist_secure_wenn_ein_proxy_davorsteht(client, nutzer, monkeypatch):
    monkeypatch.setenv("BINDUNG_SICHER", "1")
    antwort = client.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT})
    assert "Secure" in antwort.headers["set-cookie"]


def test_nach_der_anmeldung_sieht_man_die_drei_spalten(angemeldet):
    antwort = angemeldet.get("/")
    assert antwort.status_code == 200
    text = antwort.text
    # Seitenleiste
    for beschriftung in ("Alle", "Noch kein Touchpoint", "Archiv", "Tags", "Tag hinzufügen",
                         "Einstellungen", "Beispiel"):
        assert beschriftung in text, beschriftung
    assert re.search(r"<summary[^>]*>Tag hinzufügen</summary>", text)
    # Liste: drei Karten mit 0
    for karte in ("Braucht Aufmerksamkeit", "Erkaltet", "Diese Woche"):
        assert re.search(rf'karte-zahl">0</span>\s*<span class="karte-name">{karte}<', text), karte
    assert 'type="search"' in text
    assert "Person hinzufügen" in text
    assert "Mehrere hinzufügen" in text
    assert "Noch keine Personen" in text
    # Personenseite
    assert 'aria-label="Personenseite"' in text
    assert "Wähle eine Person" in text


def test_startseite_zeigt_nur_den_eigenen_nutzer(angemeldet, con):
    auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    assert "Anderer" not in angemeldet.get("/").text


def test_anmeldeseite_leitet_angemeldete_zur_startseite(angemeldet):
    assert angemeldet.get("/anmeldung").headers["location"] == "/"


def test_abmelden_beendet_die_sitzung(angemeldet):
    antwort = angemeldet.post("/abmelden")
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/anmeldung"
    angemeldet.cookies.clear()
    assert angemeldet.get("/").status_code == 303


def test_abgemeldeter_token_gilt_nicht_mehr(angemeldet):
    token = angemeldet.cookies.get(auth.COOKIE)
    angemeldet.post("/abmelden")
    angemeldet.cookies.set(auth.COOKIE, token)
    assert angemeldet.get("/").status_code == 303


def test_gueltiger_besuch_erneuert_das_cookie(angemeldet):
    antwort = angemeldet.get("/")
    assert antwort.headers["set-cookie"].startswith(f"{auth.COOKIE}=")
    assert "Max-Age=2592000" in antwort.headers["set-cookie"]


def test_static_files_carry_a_content_fingerprint(angemeldet):
    """Nach einem Update darf kein Browser ein altes Skript aus dem Cache zeigen."""
    import hashlib

    from bindung.web import basis
    seite = angemeldet.get("/").text
    for name in ("stil.css", "htmx.min.js", "diktat.js", "bindung.js"):
        kennung = hashlib.sha256((basis.STATISCH / name).read_bytes()).hexdigest()[:10]
        assert f"/statisch/{name}?v={kennung}" in seite
