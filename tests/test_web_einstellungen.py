"""Die Einstellungen: Passwort, Erinnern, Kalender, Diktat (PLAN.md, Abschnitt 4).

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from bindung import auth, einstellungen, kalender, personen

from .conftest import PASSWORT

JETZT = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC)
HX = {"HX-Request": "true"}
NEUES_PASSWORT = "ein-neues-passwort"


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt", lambda: JETZT)
    monkeypatch.setattr(kalender, "_jetzt", lambda: JETZT)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def zeile(con, nid: int):
    return einstellungen.lesen(con, nid)


def gespeichert(text: str) -> bool:
    return bool(re.search(r'role="status">Gespeichert<', text))


def erinnern(**ueberschreibe) -> dict:
    felder = {"vorgabe_intervall_tage": "30", "vorgabe_vorlauf_tage": "3",
              "zeitzone": "Europe/Vienna", "tagesmeldung_zeit": "07:30"}
    return {**felder, **ueberschreibe}


# ---------------------------------------------------------------------- Seite

def test_page_needs_login(client):
    antwort = client.get("/einstellungen")
    assert antwort.status_code == 303 and antwort.headers["location"] == "/anmeldung"


@pytest.mark.parametrize("pfad", ["/einstellungen/passwort", "/einstellungen/erinnern",
                                  "/einstellungen/diktat", "/einstellungen/darstellung",
                                  "/einstellungen/kalender/neu"])
def test_every_save_needs_login(client, pfad):
    antwort = client.post(pfad, data={})
    assert antwort.status_code == 303 and antwort.headers["location"] == "/anmeldung"


def test_sidebar_links_to_the_page_and_the_page_links_back(angemeldet):
    assert 'href="/einstellungen"' in angemeldet.get("/").text
    seite = angemeldet.get("/einstellungen")
    assert seite.status_code == 200
    assert '<a class="knopf knopf-text" href="/">‹ Zurück</a>' in seite.text
    for abschnitt in ("passwort", "erinnern", "kalender", "diktat", "darstellung"):
        assert f'<section id="einstellung-{abschnitt}"' in seite.text


def test_page_shows_the_stored_values(angemeldet, con, nid):
    seite = angemeldet.get("/einstellungen").text
    assert 'name="vorgabe_intervall_tage" value="56"' in seite
    assert 'name="vorgabe_vorlauf_tage" value="7"' in seite
    assert 'name="tagesmeldung_zeit" value="08:00"' in seite
    assert '<option value="Europe/Berlin" selected>' in seite
    assert '<option value="de-DE" selected>' in seite
    assert not gespeichert(seite)


def test_europe_berlin_is_the_first_zone():
    assert einstellungen.ZEITZONEN[0] == "Europe/Berlin"


def test_every_listed_zone_exists():
    for zone in einstellungen.ZEITZONEN:
        ZoneInfo(zone)


def test_htmx_gets_only_the_section_and_plain_posts_the_whole_page(angemeldet):
    teil = angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "en-US"}, headers=HX)
    assert teil.text.lstrip().startswith('<section id="einstellung-diktat"')
    assert "<html" not in teil.text and "einstellung-erinnern" not in teil.text
    ganz = angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "de-DE"})
    assert "<html" in ganz.text and 'id="einstellung-erinnern"' in ganz.text
    assert gespeichert(ganz.text)


# ------------------------------------------------------------------- Passwort

def passwort_senden(client, aktuell=PASSWORT, neu=NEUES_PASSWORT, wiederholung=None):
    return client.post("/einstellungen/passwort", headers=HX, data={
        "aktuell": aktuell, "neu": neu,
        "wiederholung": neu if wiederholung is None else wiederholung})


def test_password_change_saves_and_keeps_the_user_logged_in(angemeldet, con):
    antwort = passwort_senden(angemeldet)
    assert antwort.status_code == 200 and gespeichert(antwort.text)
    assert auth.passwort_pruefen(NEUES_PASSWORT,
                                 con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0])
    # Weiter angemeldet, ohne dass ein neues Cookie noetig waere.
    assert angemeldet.get("/einstellungen").status_code == 200
    assert angemeldet.get("/").status_code == 200


def test_password_change_ends_the_other_sessions(angemeldet, nutzer):
    zweiter = TestClient(angemeldet.app, follow_redirects=False)
    try:
        assert zweiter.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT}
                            ).status_code == 303
        assert zweiter.get("/einstellungen").status_code == 200
        passwort_senden(angemeldet)
        assert zweiter.get("/einstellungen").status_code == 303
        assert angemeldet.get("/einstellungen").status_code == 200
    finally:
        zweiter.close()


def test_old_password_stops_working_and_the_new_one_logs_in(angemeldet, nutzer):
    passwort_senden(angemeldet)
    neu = TestClient(angemeldet.app, follow_redirects=False)
    try:
        assert neu.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT}
                        ).status_code == 401
        auth.fehlversuche_vergessen()
        assert neu.post("/anmeldung", data={"name": nutzer, "passwort": NEUES_PASSWORT}
                        ).status_code == 303
    finally:
        neu.close()


def test_wrong_current_password_is_rejected_and_nothing_changes(angemeldet, con):
    vorher = con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0]
    antwort = passwort_senden(angemeldet, aktuell="falsch-falsch")
    assert antwort.status_code == 422
    assert "Das aktuelle Passwort stimmt nicht." in antwort.text
    assert not gespeichert(antwort.text)
    assert con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0] == vorher


def test_a_wrong_current_password_slows_the_next_try_down(angemeldet, nutzer):
    passwort_senden(angemeldet, aktuell="falsch-falsch")
    assert auth.wartezeit(nutzer) > 0
    antwort = passwort_senden(angemeldet)  # diesmal richtig, aber zu frueh
    assert antwort.status_code == 422 and "Zu viele Versuche" in antwort.text


def test_two_different_new_passwords_are_rejected(angemeldet, con):
    vorher = con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0]
    antwort = passwort_senden(angemeldet, wiederholung="etwas-anderes-123")
    assert antwort.status_code == 422
    assert "nicht gleich" in antwort.text
    assert con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0] == vorher


def test_a_short_new_password_is_rejected(angemeldet):
    antwort = passwort_senden(angemeldet, neu="kurz")
    assert antwort.status_code == 422
    assert f"mindestens {auth.MIN_LAENGE} Zeichen" in antwort.text


def test_the_form_never_echoes_a_password(angemeldet):
    antwort = passwort_senden(angemeldet, aktuell="falsch-falsch", neu="geheim-neu-12345")
    assert "geheim-neu-12345" not in antwort.text and "falsch-falsch" not in antwort.text


# ------------------------------------------------------------------- Erinnern

def test_reminder_settings_save(angemeldet, con, nid):
    antwort = angemeldet.post("/einstellungen/erinnern", data=erinnern(), headers=HX)
    assert antwort.status_code == 200 and gespeichert(antwort.text)
    e = zeile(con, nid)
    assert (e["vorgabe_intervall_tage"], e["vorgabe_vorlauf_tage"], e["zeitzone"],
            e["tagesmeldung_zeit"]) == (30, 3, "Europe/Vienna", "07:30")
    assert 'value="30"' in antwort.text
    assert '<option value="Europe/Vienna" selected>' in antwort.text


def test_limits_are_accepted(angemeldet, con, nid):
    for intervall, vorlauf in ((1, 0), (3650, 365)):
        daten = erinnern(vorgabe_intervall_tage=str(intervall), vorgabe_vorlauf_tage=str(vorlauf))
        assert angemeldet.post("/einstellungen/erinnern", data=daten, headers=HX
                               ).status_code == 200
        assert zeile(con, nid)["vorgabe_intervall_tage"] == intervall
        assert zeile(con, nid)["vorgabe_vorlauf_tage"] == vorlauf


@pytest.mark.parametrize("feld,wert,wort", [
    ("vorgabe_intervall_tage", "0", "zwischen 1 und 3650"),
    ("vorgabe_intervall_tage", "3651", "zwischen 1 und 3650"),
    ("vorgabe_intervall_tage", "-5", "zwischen 1 und 3650"),
    ("vorgabe_intervall_tage", "viel", "ganze Zahl"),
    ("vorgabe_intervall_tage", "", "ganze Zahl"),
    ("vorgabe_vorlauf_tage", "-1", "zwischen 0 und 365"),
    ("vorgabe_vorlauf_tage", "366", "zwischen 0 und 365"),
    ("vorgabe_vorlauf_tage", "1.5", "ganze Zahl"),
    ("zeitzone", "Mars/Olympus", "Zeitzone"),
    ("zeitzone", "", "Zeitzone"),
    ("zeitzone", "../../etc/passwd", "Zeitzone"),
    ("tagesmeldung_zeit", "25:00", "Uhrzeit"),
    ("tagesmeldung_zeit", "08:60", "Uhrzeit"),
    ("tagesmeldung_zeit", "8:00", "Uhrzeit"),
    ("tagesmeldung_zeit", "", "Uhrzeit"),
    ("tagesmeldung_zeit", "morgens", "Uhrzeit"),
])
def test_invalid_reminder_values_are_rejected_and_save_nothing(angemeldet, con, nid,
                                                               feld, wert, wort):
    vorher = tuple(zeile(con, nid))
    antwort = angemeldet.post("/einstellungen/erinnern", data=erinnern(**{feld: wert}),
                              headers=HX)
    assert antwort.status_code == 422
    assert wort in antwort.text and 'role="alert"' in antwort.text
    assert not gespeichert(antwort.text)
    # Alles oder nichts: auch die gueltigen Felder des Formulars sind nicht gespeichert.
    assert tuple(zeile(con, nid)) == vorher


def test_a_rejected_form_keeps_what_was_typed(angemeldet):
    antwort = angemeldet.post("/einstellungen/erinnern", headers=HX,
                              data=erinnern(vorgabe_intervall_tage="0", tagesmeldung_zeit="19:45"))
    assert 'name="tagesmeldung_zeit" value="19:45"' in antwort.text
    assert 'name="vorgabe_vorlauf_tage" value="3"' in antwort.text


def test_time_with_seconds_is_accepted(angemeldet, con, nid):
    angemeldet.post("/einstellungen/erinnern", data=erinnern(tagesmeldung_zeit="06:15:00"),
                    headers=HX)
    assert zeile(con, nid)["tagesmeldung_zeit"] == "06:15"


def test_a_zone_stored_outside_the_list_stays_selectable(angemeldet, con, nid):
    con.execute("UPDATE nutzer SET zeitzone = 'Asia/Kathmandu' WHERE id = ?", (nid,))
    con.commit()
    seite = angemeldet.get("/einstellungen").text
    assert '<option value="Asia/Kathmandu" selected>' in seite
    antwort = angemeldet.post("/einstellungen/erinnern",
                              data=erinnern(zeitzone="Asia/Kathmandu"), headers=HX)
    assert antwort.status_code == 200 and zeile(con, nid)["zeitzone"] == "Asia/Kathmandu"
    # Aber nur die eigene: eine fremde aus der Luft gibt es nicht.
    assert angemeldet.post("/einstellungen/erinnern", data=erinnern(zeitzone="Asia/Tokyo"),
                           headers=HX).status_code == 200
    assert angemeldet.post("/einstellungen/erinnern", data=erinnern(zeitzone="Asia/Kathmandu"),
                           headers=HX).status_code == 422


def test_the_zone_decides_what_today_is(angemeldet, con, nid, monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 23, 30, tzinfo=dt.UTC))
    assert personen.heute(con, nid) == dt.date(2026, 11, 12)  # Berlin
    angemeldet.post("/einstellungen/erinnern", data=erinnern(zeitzone="America/Los_Angeles"),
                    headers=HX)
    assert personen.heute(con, nid) == dt.date(2026, 11, 11)


def test_the_hint_names_the_time_and_where_to_switch_it_on(angemeldet):
    seite = angemeldet.get("/einstellungen").text
    assert "Zu dieser Uhrzeit" in seite and "späteren Version" not in seite
    assert "Benachrichtigungen" in seite


def test_defaults_change_what_a_person_without_own_interval_needs(angemeldet, con, nid):
    from bindung import faelligkeit, kontakte

    pid = personen.anlegen(con, nid, "Anna Beispiel")
    kontakte.eintragen(con, nid, pid, datum=dt.date(2026, 10, 12), art="anruf")  # vor 30 Tagen
    heute = dt.date(2026, 11, 11)
    assert faelligkeit.bindungen(con, nid, heute)[pid].zustand == faelligkeit.OK  # 56 Tage
    angemeldet.post("/einstellungen/erinnern", data=erinnern(vorgabe_intervall_tage="20"),
                    headers=HX)
    assert faelligkeit.bindungen(con, nid, heute)[pid].zustand == faelligkeit.UEBERFAELLIG


# ---------------------------------------------------------------------- Diktat

def test_dictation_language_saves(angemeldet, con, nid):
    antwort = angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "en-US"},
                              headers=HX)
    assert antwort.status_code == 200 and gespeichert(antwort.text)
    assert zeile(con, nid)["diktat_sprache"] == "en-US"
    assert '<option value="en-US" selected>' in antwort.text


@pytest.mark.parametrize("wert", ["fr-FR", "", "de", "de-DE; drop table nutzer"])
def test_unknown_dictation_language_is_rejected(angemeldet, con, nid, wert):
    antwort = angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": wert}, headers=HX)
    assert antwort.status_code == 422 and 'role="alert"' in antwort.text
    assert zeile(con, nid)["diktat_sprache"] == "de-DE"


# --------------------------------------------------------------------- Kalender

def adressen(text: str) -> tuple[str, str]:
    webcal = re.search(r'id="kalender-webcal" value="([^"]+)"', text).group(1)
    adresse = re.search(r'id="kalender-adresse" value="([^"]+)"', text).group(1)
    return webcal, adresse


def test_addresses_match_the_token(angemeldet, con, nid):
    token = zeile(con, nid)["kalender_token"]
    webcal, adresse = adressen(angemeldet.get("/einstellungen").text)
    assert webcal == f"webcal://testserver/kalender/{token}.ics"
    assert adresse == f"http://testserver/kalender/{token}.ics"


def test_the_address_on_the_page_really_is_the_feed(angemeldet, con, nid):
    _, adresse = adressen(angemeldet.get("/einstellungen").text)
    pfad = adresse.removeprefix("http://testserver")
    anonym = TestClient(angemeldet.app, follow_redirects=False)
    try:
        assert anonym.get(pfad).status_code == 200
    finally:
        anonym.close()


def test_forwarded_proto_makes_it_https(angemeldet):
    seite = angemeldet.get("/einstellungen", headers={"X-Forwarded-Proto": "https"}).text
    webcal, adresse = adressen(seite)
    assert adresse.startswith("https://testserver/kalender/")
    assert webcal.startswith("webcal://testserver/kalender/")
    assert "Kalenderadresse (https)" in seite


def test_forwarded_host_and_proto_come_from_the_proxy(angemeldet):
    seite = angemeldet.get("/einstellungen", headers={
        "X-Forwarded-Proto": "https, http", "X-Forwarded-Host": "bindung.example.org"}).text
    webcal, adresse = adressen(seite)
    assert adresse.startswith("https://bindung.example.org/kalender/")
    assert webcal.startswith("webcal://bindung.example.org/kalender/")


def test_secure_mode_means_https(angemeldet, monkeypatch):
    monkeypatch.setenv("BINDUNG_SICHER", "1")
    _, adresse = adressen(angemeldet.get("/einstellungen").text)
    assert adresse.startswith("https://testserver/")


def test_an_unknown_forwarded_proto_is_ignored(angemeldet):
    _, adresse = adressen(angemeldet.get("/einstellungen",
                                         headers={"X-Forwarded-Proto": "javascript"}).text)
    assert adresse.startswith("http://testserver/")


def test_a_nonsense_host_falls_back_to_the_request(angemeldet):
    seite = angemeldet.get("/einstellungen",
                           headers={"X-Forwarded-Host": '"><script>x</script>'}).text
    assert "<script>x" not in seite
    assert adressen(seite)[1].startswith("http://testserver/")


def test_download_and_copy_controls_are_there(angemeldet):
    seite = angemeldet.get("/einstellungen").text
    assert 'href="/kalender/herunterladen"' in seite
    assert 'data-kopieren="kalender-webcal"' in seite
    assert 'data-kopieren="kalender-adresse"' in seite
    assert "Ablage › Neues Kalenderabonnement" in seite
    assert "stündlich" in seite


def test_rotating_asks_for_confirmation_in_the_markup(angemeldet):
    seite = angemeldet.get("/einstellungen").text
    assert re.search(r'hx-post="/einstellungen/kalender/neu"[^>]*hx-confirm="[^"]*funktioniert '
                     r'danach nicht mehr', seite)


def test_rotating_changes_the_token_and_the_page_shows_the_new_one(angemeldet, con, nid):
    alt = zeile(con, nid)["kalender_token"]
    antwort = angemeldet.post("/einstellungen/kalender/neu", headers=HX)
    neu = zeile(con, nid)["kalender_token"]
    assert neu != alt and len(neu) >= 43
    assert alt not in antwort.text and neu in antwort.text
    assert "Die alte funktioniert nicht mehr." in antwort.text
    assert neu in angemeldet.get("/einstellungen").text


# ------------------------------------------------------------- Trennung, Telefon

def test_settings_belong_to_the_user_who_saves_them(angemeldet, con, nid):
    fremd = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    vorher = tuple(zeile(con, fremd))
    angemeldet.post("/einstellungen/erinnern", data=erinnern(), headers=HX)
    angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "en-US"}, headers=HX)
    angemeldet.post("/einstellungen/kalender/neu", headers=HX)
    passwort_senden(angemeldet)
    assert tuple(zeile(con, fremd)) == vorher
    assert zeile(con, nid)["zeitzone"] == "Europe/Vienna"


def test_the_page_never_shows_another_users_address(angemeldet, con):
    fremd = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    assert zeile(con, fremd)["kalender_token"] not in angemeldet.get("/einstellungen").text


def test_the_page_is_built_for_375_px(angemeldet):
    seite = angemeldet.get("/einstellungen").text
    assert '<meta name="viewport" content="width=device-width' in seite
    assert seite.count('<main class="einstellungen">') == 1
    assert 'style="' not in seite and "<table" not in seite
    css = (re.compile(r"/\*.*?\*/", re.S)).sub(
        "", open("bindung/web/statisch/stil.css", encoding="utf-8").read())
    regel = re.search(r"\.einstellungen \{([^}]*)\}", css).group(1)
    assert "width: 100%" in regel and "max-width: 640px" in regel
    # Zwei Zahlenfelder nebeneinander, alles andere ueber die ganze Breite.
    assert seite.count('class="feld feld-breit"') == 2


# ------------------------------------------------------------------ Darstellung

def _html_kopf(text: str) -> str:
    return re.search(r"<html[^>]*>", text).group(0)


def test_darstellung_ist_vorgabe_system_und_steht_am_html(angemeldet, con, nid):
    assert zeile(con, nid)["darstellung"] == "system"
    assert 'data-darstellung="system"' in _html_kopf(angemeldet.get("/").text)
    seite = angemeldet.get("/einstellungen").text
    assert "<h2" in seite and ">Darstellung<" in seite
    # Drei Optionsfelder, „System“ ist gewählt.
    assert re.findall(r'name="darstellung" value="(\w+)"( checked)?', seite) == [
        ("system", " checked"), ("hell", ""), ("dunkel", "")]
    assert ">System<" in seite and ">Hell<" in seite and ">Dunkel<" in seite


def test_darstellung_speichern_tauscht_den_abschnitt_und_sagt_der_seite_bescheid(
        angemeldet, con, nid):
    antwort = angemeldet.post("/einstellungen/darstellung", data={"darstellung": "hell"},
                              headers=HX)
    assert antwort.status_code == 200
    assert antwort.text.lstrip().startswith('<section id="einstellung-darstellung"')
    assert gespeichert(antwort.text)
    assert json.loads(antwort.headers["hx-trigger"]) == {"darstellung": "hell"}
    assert zeile(con, nid)["darstellung"] == "hell"


def test_darstellung_ohne_htmx_leitet_zurueck_auf_die_seite(angemeldet, con, nid):
    antwort = angemeldet.post("/einstellungen/darstellung", data={"darstellung": "dunkel"},
                              follow_redirects=False)
    assert antwort.status_code == 303 and antwort.headers["location"] == "/einstellungen"
    assert zeile(con, nid)["darstellung"] == "dunkel"


def test_darstellung_nach_dem_speichern_steht_in_jeder_seite(angemeldet):
    angemeldet.post("/einstellungen/darstellung", data={"darstellung": "dunkel"}, headers=HX)
    for adresse in ("/", "/einstellungen"):
        kopf = _html_kopf(angemeldet.get(adresse).text)
        assert 'data-darstellung="dunkel"' in kopf, adresse


def test_darstellung_hell_und_dunkel_stellen_color_scheme_und_theme_color_um(angemeldet):
    angemeldet.post("/einstellungen/darstellung", data={"darstellung": "hell"}, headers=HX)
    seite = angemeldet.get("/").text
    assert '<meta name="color-scheme" content="light">' in seite
    metas = re.findall(r'<meta name="theme-color" content="(#\w+)" media="([^"]+)">', seite)
    assert [m for _, m in metas] == ["all", "not all"]
    angemeldet.post("/einstellungen/darstellung", data={"darstellung": "dunkel"}, headers=HX)
    seite = angemeldet.get("/").text
    assert '<meta name="color-scheme" content="dark">' in seite
    assert [m for _, m in re.findall(
        r'<meta name="theme-color" content="(#\w+)" media="([^"]+)">', seite)] == ["not all", "all"]
    angemeldet.post("/einstellungen/darstellung", data={"darstellung": "system"}, headers=HX)
    seite = angemeldet.get("/").text
    assert '<meta name="color-scheme" content="light dark">' in seite


@pytest.mark.parametrize("wert", ["", "bunt", "Hell", "dark"])
def test_darstellung_lehnt_unbekannte_werte_ab(angemeldet, con, nid, wert):
    antwort = angemeldet.post("/einstellungen/darstellung", data={"darstellung": wert},
                              headers=HX)
    assert antwort.status_code == 422
    assert "Wähle System, Hell oder Dunkel." in antwort.text
    assert zeile(con, nid)["darstellung"] == "system"


def test_darstellung_gehoert_dem_nutzer(angemeldet, con, nid):
    anderer = auth.nutzer_anlegen(con, "Anderer", PASSWORT)
    angemeldet.post("/einstellungen/darstellung", data={"darstellung": "hell"}, headers=HX)
    assert zeile(con, anderer)["darstellung"] == "system"


def test_anmeldung_und_einrichten_folgen_dem_geraet(client):
    assert 'data-darstellung="system"' in _html_kopf(client.get("/anmeldung").text)

