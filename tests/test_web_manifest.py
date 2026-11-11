"""Manifest, Symbole, Kopfzeilen, Beenden, erster Start der Mac-App (PLAN.md, Abschnitte 3, 7)."""

from __future__ import annotations

import importlib.util
import re
import struct
from pathlib import Path

import pytest

from bindung import auth, tagesmeldung
from bindung.web import basis
from bindung.web.routen import anwendung

from .conftest import PASSWORT

WURZEL = Path(__file__).resolve().parent.parent
STATISCH = WURZEL / "bindung" / "web" / "statisch"
CSS = (STATISCH / "stil.css").read_text(encoding="utf-8")


def _css_farben(dunkel: bool) -> dict[str, str]:
    """Die Farben aus stil.css, unabhaengig von `basis.palette` gelesen."""
    css = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    if dunkel:
        block = re.search(r"prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([^{}]*)\}", css).group(1)
    else:
        block = re.search(r":root\s*\{([^{}]*)\}", css).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-f]{6});", block))


def _png_kante(pfad: Path) -> tuple[int, int, int]:
    """(Breite, Hoehe, Farbart) aus dem Kopf einer PNG-Datei."""
    daten = pfad.read_bytes()
    assert daten[:8] == b"\x89PNG\r\n\x1a\n", pfad.name
    breite, hoehe, _tiefe, farbart = struct.unpack(">IIBB", daten[16:26])
    return breite, hoehe, farbart


@pytest.fixture
def app_modus(monkeypatch):
    """Als liefe der Starter: `BEENDEN` ist gesetzt, und es merkt sich, ob es gerufen wurde."""
    gerufen = []
    monkeypatch.setattr(basis, "BEENDEN", lambda: gerufen.append(True))
    return gerufen


# ------------------------------------------------------------------ Manifest

def test_the_manifest_is_open_and_valid_json(client):
    antwort = client.get("/manifest.webmanifest")   # keine Sitzung
    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("application/manifest+json")
    manifest = antwort.json()
    assert manifest["name"] == "Bindung" and manifest["short_name"] == "Bindung"
    assert manifest["start_url"] == "/" and manifest["scope"] == "/"
    assert manifest["display"] == "standalone" and manifest["lang"] == "de"


def test_the_manifest_colours_come_from_the_palette(client):
    manifest = client.get("/manifest.webmanifest").json()
    assert manifest["background_color"] == _css_farben(False)["grund"]
    assert manifest["theme_color"] == _css_farben(False)["grund"]


def test_the_palette_helper_reads_both_themes():
    assert basis.palette()["hell"]["akzent"] == _css_farben(False)["akzent"]
    assert basis.palette()["dunkel"]["akzent"] == _css_farben(True)["akzent"]
    assert basis.palette()["hell"]["grund"] != basis.palette()["dunkel"]["grund"]


def test_the_manifest_icons_exist_and_are_served(client):
    symbole = client.get("/manifest.webmanifest").json()["icons"]
    zwecke = {(s["sizes"], s["purpose"]) for s in symbole}
    assert ("192x192", "any") in zwecke and ("512x512", "any") in zwecke
    assert ("512x512", "maskable") in zwecke
    for symbol in symbole:
        antwort = client.get(symbol["src"])   # offen, mit Fingerabdruck
        assert antwort.status_code == 200, symbol["src"]
        assert antwort.headers["content-type"].startswith(symbol["type"])
        if symbol["type"] == "image/png":
            kante = int(symbol["sizes"].split("x")[0])
            datei = STATISCH / Path(symbol["src"].split("?")[0]).name
            assert _png_kante(datei)[:2] == (kante, kante), symbol["src"]


def test_the_icon_files_are_the_sizes_the_pages_promise():
    for name, kante in (("symbol-180.png", 180), ("symbol-192.png", 192), ("symbol-512.png", 512),
                        ("symbol-maskable-512.png", 512), ("symbol-menue.png", 44)):
        assert _png_kante(STATISCH / name)[:2] == (kante, kante), name
    # Das Menuebild braucht Durchsicht (RGBA): als Vorlage faerbt macOS es selbst ein.
    assert _png_kante(STATISCH / "symbol-menue.png")[2] == 6
    # Apple fuellt Durchsichtiges schwarz: das Symbol fuer den Home-Bildschirm ist deckend.
    daten = (STATISCH / "symbol-180.png").read_bytes()
    assert b"tRNS" not in daten


def test_the_svg_symbol_uses_the_accent_of_the_stylesheet():
    svg = (STATISCH / "symbol.svg").read_text(encoding="utf-8")
    assert _css_farben(False)["akzent"] in svg and _css_farben(True)["akzent"] in svg
    assert "<text" not in svg


def _erzeuger():
    spec = importlib.util.spec_from_file_location(
        "erzeugen", WURZEL / "werkzeuge" / "symbole" / "erzeugen.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_the_committed_pngs_are_what_the_script_makes_from_the_svg():
    """Wer symbol.svg oder die Palette aendert, ohne das Skript zu starten, faellt hier auf."""
    erzeuger = _erzeuger()
    for name, kante, art in erzeuger.PNGS:
        assert (STATISCH / name).read_bytes() == erzeuger.app_symbol(kante, art), name


def test_the_digest_icon_is_a_file_that_is_served(angemeldet):
    assert tagesmeldung.SYMBOL == "/statisch/symbol-192.png"
    assert angemeldet.get(tagesmeldung.SYMBOL).status_code == 200


# ----------------------------------------------------------------- Kopfzeilen

def _kopf(html: str) -> str:
    return html.split("</head>")[0]


def _kopf_pruefen(html: str) -> None:
    kopf = _kopf(html)
    assert kopf, "kein <head> gefunden"
    kennung = basis.statisch_kennung
    assert (f'rel="icon" type="image/svg+xml" href="/statisch/symbol.svg?v={kennung("symbol.svg")}"'
            in kopf)
    assert (f'rel="apple-touch-icon" href="/statisch/symbol-180.png?v={kennung("symbol-180.png")}"'
            in kopf)
    assert f'rel="manifest" href="{basis.manifest_adresse()}"' in kopf
    assert re.search(r'href="/manifest\.webmanifest\?v=[0-9a-f]{10}"', kopf)
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in kopf
    assert '<meta name="apple-mobile-web-app-title" content="Bindung">' in kopf


def test_the_login_page_carries_the_icon_manifest_and_theme_links(client):
    _kopf_pruefen(client.get("/anmeldung").text)


def test_the_app_page_carries_the_icon_manifest_and_theme_links(angemeldet):
    _kopf_pruefen(angemeldet.get("/").text)


def test_the_theme_colour_is_set_for_light_and_dark_from_the_palette(client):
    kopf = _kopf(client.get("/anmeldung").text)
    hell, dunkel = _css_farben(False)["grund"], _css_farben(True)["grund"]
    for farbe, thema in ((hell, "light"), (dunkel, "dark")):
        assert (f'<meta name="theme-color" content="{farbe}" '
                f'media="(prefers-color-scheme: {thema})">') in kopf


def test_the_manifest_link_follows_the_manifest(monkeypatch):
    """Der Fingerabdruck haengt am Inhalt: ein anderes Manifest, eine andere Adresse."""
    vorher = basis.manifest_adresse()
    basis.manifest_adresse.cache_clear()
    monkeypatch.setattr(basis, "manifest", lambda: {"name": "Anders"})
    try:
        assert basis.manifest_adresse() != vorher
    finally:
        basis.manifest_adresse.cache_clear()


# ---------------------------------------------------------------- Lebenszeichen

def test_healthz_is_open_and_does_not_reveal_the_data_folder(client, daten):
    antwort = client.get("/healthz")
    assert antwort.status_code == 200
    korper = antwort.json()
    assert korper["app"] == "Bindung" and korper["ok"] is True
    assert korper["daten"] == anwendung.daten_kennung()
    assert str(daten) not in antwort.text and "Users" not in antwort.text


def test_the_data_fingerprint_differs_per_folder(daten, monkeypatch, tmp_path):
    erste = anwendung.daten_kennung()
    monkeypatch.setattr("bindung.pfade.DATEN", tmp_path / "anderswo")
    assert anwendung.daten_kennung() != erste


# ---------------------------------------------------------------------- Beenden

def test_quit_is_a_404_outside_the_mac_app(angemeldet):
    assert angemeldet.post("/api/beenden").status_code == 404
    assert "data-beenden" not in angemeldet.get("/").text


def test_quit_needs_a_session(client, app_modus):
    assert client.post("/api/beenden").status_code == 303
    assert app_modus == []


def test_quit_works_inside_the_mac_app_and_the_button_is_there(angemeldet, app_modus):
    assert 'data-beenden>Beenden</button>' in angemeldet.get("/").text
    antwort = angemeldet.post("/api/beenden")
    assert antwort.status_code == 200 and antwort.json() == {"ok": True}
    assert app_modus == [True]


def test_quit_refuses_a_foreign_origin(angemeldet, app_modus):
    antwort = angemeldet.post("/api/beenden", headers={"Origin": "http://boese.example"})
    assert antwort.status_code == 403
    assert app_modus == []
    gleich = angemeldet.post("/api/beenden", headers={"Origin": "http://testserver"})
    assert gleich.status_code == 200


# ----------------------------------------------------- Erster Start der Mac-App

def test_setup_does_not_exist_on_a_server(client):
    assert client.get("/einrichten").status_code == 404
    assert client.post("/einrichten", data={"name": "x", "passwort": "abcdefgh",
                                            "wiederholung": "abcdefgh"}).status_code == 404
    assert client.get("/anmeldung").status_code == 200   # kein Umleiten


def test_the_first_start_of_the_mac_app_leads_to_setup_and_logs_in(client, app_modus, con):
    assert client.get("/anmeldung").headers["location"] == "/einrichten"
    assert client.get("/einrichten").status_code == 200
    antwort = client.post("/einrichten", data={"name": "Anna", "passwort": PASSWORT,
                                               "wiederholung": PASSWORT})
    assert antwort.status_code == 303 and antwort.headers["location"] == "/"
    assert [n["name"] for n in auth.nutzer_liste(con)] == ["Anna"]
    assert client.get("/").status_code == 200   # das Cookie ist gesetzt
    # Mit dem ersten Nutzer ist die Tuer zu.
    assert client.get("/einrichten").status_code == 404
    assert client.post("/einrichten", data={"name": "Zweiter", "passwort": PASSWORT,
                                            "wiederholung": PASSWORT}).status_code == 404


def test_setup_asks_for_the_same_password_twice_and_keeps_the_name(client, app_modus, con):
    antwort = client.post("/einrichten", data={"name": "Anna", "passwort": PASSWORT,
                                               "wiederholung": PASSWORT + "x"})
    assert antwort.status_code == 422
    assert "nicht gleich" in antwort.text and 'value="Anna"' in antwort.text
    assert auth.nutzer_liste(con) == []


def test_setup_refuses_a_short_password(client, app_modus, con):
    antwort = client.post("/einrichten", data={"name": "Anna", "passwort": "kurz",
                                               "wiederholung": "kurz"})
    assert antwort.status_code == 422 and "mindestens 8 Zeichen" in antwort.text
    assert auth.nutzer_liste(con) == []


def test_with_users_the_mac_app_shows_the_normal_login(client, app_modus, nutzer):
    assert client.get("/anmeldung").status_code == 200
