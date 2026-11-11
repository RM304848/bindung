"""Diktat (PLAN.md, Abschnitt 8): was der Server dazu beitraegt.

Das Sprechen selbst macht der Browser (`diktat.js`); hier steht, dass die Seite das Skript und die
Sprache des Nutzers liefert und dass jedes Textfeld den Rahmen fuer den Mikrofonknopf traegt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bindung import personen

HX = {"HX-Request": "true"}
VORLAGEN = Path(__file__).resolve().parent.parent / "bindung" / "web" / "vorlagen"
STATISCH = Path(__file__).resolve().parent.parent / "bindung" / "web" / "statisch"


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def sprache(text: str) -> str:
    treffer = re.search(r'<body [^>]*data-diktat-sprache="([^"]*)"', text)
    assert treffer, "kein data-diktat-sprache am <body>"
    return treffer.group(1)


# --------------------------------------------------------------------- Seite

def test_base_page_loads_the_dictation_script_once_before_the_other_script(angemeldet):
    text = angemeldet.get("/").text
    assert text.count('src="/statisch/diktat.js"') == 1
    assert text.index("/statisch/diktat.js") < text.index("/statisch/bindung.js")


def test_login_page_also_carries_a_language(client):
    """Ohne Nutzer gilt die Vorgabe, die Seite soll deshalb nicht ohne Attribut sein."""
    assert sprache(client.get("/anmeldung").text) == "de-DE"


def test_the_script_is_served(angemeldet):
    antwort = angemeldet.get("/statisch/diktat.js")
    assert antwort.status_code == 200
    assert "Diktat" in antwort.text


def test_language_follows_the_setting_and_changes_after_saving_it(angemeldet):
    assert sprache(angemeldet.get("/").text) == "de-DE"
    angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "en-US"}, headers=HX)
    assert sprache(angemeldet.get("/").text) == "en-US"
    assert sprache(angemeldet.get("/einstellungen").text) == "en-US"
    angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "de-DE"}, headers=HX)
    assert sprache(angemeldet.get("/").text) == "de-DE"


def test_language_is_each_users_own(angemeldet, con, nid):
    from fastapi.testclient import TestClient

    from bindung import auth
    from bindung.web.server import app

    auth.nutzer_anlegen(con, "Zweite Person", "ein-anderes-passwort")
    angemeldet.post("/einstellungen/diktat", data={"diktat_sprache": "en-US"}, headers=HX)
    with TestClient(app, follow_redirects=False) as zweiter:
        zweiter.post("/anmeldung",
                     data={"name": "Zweite Person", "passwort": "ein-anderes-passwort"})
        assert sprache(zweiter.get("/").text) == "de-DE"
    assert sprache(angemeldet.get("/").text) == "en-US"


# -------------------------------------------------------------- Textfelder

def test_every_dictation_field_sits_alone_in_the_frame():
    """Der Rahmen steht in der Vorlage, damit das Skript kein Feld umsetzen muss."""
    gefunden = 0
    for vorlage in sorted(VORLAGEN.glob("*.html")):
        text = vorlage.read_text(encoding="utf-8")
        for feld in re.finditer(r"<textarea\b[^>]*\bdata-diktat\b", text):
            gefunden += 1
            davor = text[:feld.start()].rstrip()
            assert davor.endswith('<div class="diktat">'), f"{vorlage.name}: Feld ohne Rahmen"
            danach = text[feld.end():].split("</textarea>", 1)[1].lstrip()
            assert danach.startswith("</div>"), f"{vorlage.name}: Rahmen enthaelt mehr als das Feld"
    assert gefunden >= 5


def test_every_frame_holds_a_dictation_field():
    for vorlage in sorted(VORLAGEN.glob("*.html")):
        text = vorlage.read_text(encoding="utf-8")
        for rahmen in re.finditer(r'<div class="diktat">(.*?)</div>', text, flags=re.S):
            assert "data-diktat" in rahmen.group(1), vorlage.name


def test_the_pages_with_text_fields_deliver_the_frame(angemeldet, con, nid):
    pid = personen.anlegen(con, nid, "Anna Beispiel")
    seiten = {
        "Personenseite": f"/personen/{pid}",
        "Person hinzufuegen": "/personen/neu",
        "Mehrere hinzufuegen": "/personen/mehrere",
        "Kontakt eintragen": f"/personen/{pid}/kontakt/neu",
    }
    for name, adresse in seiten.items():
        text = angemeldet.get(adresse, headers=HX).text
        assert re.search(r'<div class="diktat">\s*<textarea\b[^>]*\bdata-diktat\b', text), name


def test_a_saved_kontakt_edit_form_has_the_frame(angemeldet, con, nid):
    """Die Notiz eines Eintrags in der Geschichte (inline bearbeiten) diktiert man auch."""
    from bindung import kontakte

    pid = personen.anlegen(con, nid, "Anna Beispiel")
    kid = kontakte.eintragen(con, nid, pid, art="anruf", datum="2026-11-01", notiz="Hallo")
    text = angemeldet.get(f"/kontakte/{kid}/bearbeiten", headers=HX).text
    assert re.search(r'<div class="diktat">\s*<textarea\b[^>]*\bdata-diktat\b', text)


# ---------------------------------------------------------------- Skript

def test_the_script_has_the_interface_of_the_plan():
    js = (STATISCH / "diktat.js").read_text(encoding="utf-8")
    for name in ("verfuegbar", "starten", "stoppen"):
        assert re.search(rf"\b{name}\b", js)
    assert "var backend" in js


def test_error_texts_are_german_and_name_the_microphone_setting():
    js = (STATISCH / "diktat.js").read_text(encoding="utf-8")
    for code in ("not-allowed", "no-speech", "network", "audio-capture"):
        assert f'"{code}"' in js
    assert "Einstellungen des Browsers" in js
