"""Der Starter der Mac-App: Port, "laeuft schon", Tagesaufgabe, Menueleiste (PLAN.md, 3)."""

from __future__ import annotations

import http.server
import json
import sys
import threading
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from bindung import cli, menueleiste, starter, tagesaufgabe
from bindung.web import basis
from bindung.web.routen import anwendung


class _Antwort(http.server.BaseHTTPRequestHandler):
    inhalt: bytes = b"{}"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.inhalt)

    def log_message(self, *_args):
        pass


@pytest.fixture
def lauscher():
    """Ein kleiner Server auf einem freien Port, der einen festen JSON-Text liefert."""
    gestartet = []

    def start(inhalt: dict | bytes) -> int:
        handler = type("H", (_Antwort,), {
            "inhalt": inhalt if isinstance(inhalt, bytes) else json.dumps(inhalt).encode()})
        server = http.server.HTTPServer((starter.HOST, 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        gestartet.append(server)
        return server.server_address[1]

    yield start
    for server in gestartet:
        server.shutdown()
        server.server_close()


@pytest.fixture
def mac_app(monkeypatch):
    """`main` fasst die Welt an: Browser, Umgebung, Server. Alles wird ersetzt und gemerkt."""
    monkeypatch.setattr(basis, "BEENDEN", None)
    for name in ("BINDUNG_KEIN_BROWSER", "BINDUNG_APP_PORT", "BINDUNG_PORT",
                 "BINDUNG_KEINE_MENUELEISTE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(tagesaufgabe.UMGEBUNG, "1")
    geoeffnet = []
    monkeypatch.setattr(starter.webbrowser, "open", geoeffnet.append)
    monkeypatch.setattr(menueleiste, "verfuegbar", lambda: False)
    return geoeffnet


# ---------------------------------------------------------------------- Ports

def test_the_ports_are_the_planned_ones():
    assert starter.PORT == 8788 and starter.SERVE_PORT == 8785
    assert starter.HOST == "127.0.0.1"


def test_a_free_port_is_used_and_nothing_runs_yet(monkeypatch):
    monkeypatch.setattr(starter, "_frei", lambda port: True)
    assert starter.port_waehlen(8788) == (8788, False)


def test_if_bindung_already_answers_there_only_the_browser_opens(monkeypatch):
    monkeypatch.setattr(starter, "_frei", lambda port: False)
    monkeypatch.setattr(starter, "lebenszeichen", lambda port: {"app": "Bindung"})
    assert starter.port_waehlen(8788) == (8788, True)


def test_if_something_else_holds_the_port_a_free_one_is_taken(monkeypatch):
    monkeypatch.setattr(starter, "_frei", lambda port: False)
    monkeypatch.setattr(starter, "lebenszeichen", lambda port: None)
    port, laeuft = starter.port_waehlen(8788)
    assert laeuft is False and port not in (0, 8788)


def test_the_sign_of_life_is_only_bindungs(lauscher):
    eigene = lauscher({"ok": True, "app": "Bindung", "daten": "abc"})
    fremde = lauscher({"ok": True, "app": "Health OS"})
    kein_json = lauscher(b"<html>")
    assert starter.lebenszeichen(eigene)["daten"] == "abc"
    assert starter.lebenszeichen(fremde) is None
    assert starter.lebenszeichen(kein_json) is None
    assert starter.lebenszeichen(1) is None   # nichts hoert dort zu


def test_the_real_healthz_is_recognised(lauscher):
    port = lauscher({"ok": True, "app": "Bindung", "version": "0",
                     "daten": anwendung.daten_kennung()})
    assert starter.lebenszeichen(port)["daten"] == anwendung.daten_kennung()


# ------------------------------------------------------- bindung serve nebenan

def test_a_running_serve_with_the_same_data_means_no_second_daily_task(monkeypatch):
    monkeypatch.setattr(starter, "lebenszeichen",
                        lambda port: {"app": "Bindung", "daten": anwendung.daten_kennung()})
    assert starter.serve_teilt_die_daten() is True


def test_a_serve_with_other_data_or_none_does_not_count(monkeypatch):
    monkeypatch.setattr(starter, "lebenszeichen",
                        lambda port: {"app": "Bindung", "daten": "anders"})
    assert starter.serve_teilt_die_daten() is False
    monkeypatch.setattr(starter, "lebenszeichen", lambda port: None)
    assert starter.serve_teilt_die_daten() is False


def test_serve_is_looked_for_where_bindung_port_says(monkeypatch):
    gefragt = []
    monkeypatch.setenv("BINDUNG_PORT", "9123")
    monkeypatch.setattr(starter, "lebenszeichen", lambda port: gefragt.append(port))
    starter.serve_teilt_die_daten()
    assert gefragt == [9123]


# ----------------------------------------------------------------------- main

class _ErsatzServer:
    """Statt uvicorn: merkt sich, dass `run` gerufen wurde, und laeuft nicht wirklich."""

    instanzen: ClassVar[list] = []

    def __init__(self, config):
        self.config, self.started, self.should_exit, self.lief = config, True, False, False
        _ErsatzServer.instanzen.append(self)

    def run(self):
        self.lief = True


@pytest.fixture
def ersatz_uvicorn(monkeypatch):
    import uvicorn

    _ErsatzServer.instanzen = []
    monkeypatch.setattr(uvicorn, "Server", _ErsatzServer)
    monkeypatch.setattr(starter, "serve_teilt_die_daten", lambda: False)
    return _ErsatzServer


def test_main_opens_only_the_browser_when_bindung_runs(mac_app, ersatz_uvicorn, monkeypatch):
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, True))
    starter.main()
    assert mac_app == ["http://127.0.0.1:8788/"]
    assert ersatz_uvicorn.instanzen == []   # kein zweiter Server


def test_main_without_a_browser_when_asked_not_to(mac_app, ersatz_uvicorn, monkeypatch):
    monkeypatch.setenv("BINDUNG_KEIN_BROWSER", "1")
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, True))
    starter.main()
    assert mac_app == []


def test_main_serves_on_loopback_and_enables_the_quit_button(mac_app, ersatz_uvicorn, monkeypatch):
    monkeypatch.setenv("BINDUNG_KEIN_BROWSER", "1")
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, False))
    starter.main()
    server, = ersatz_uvicorn.instanzen
    assert server.lief
    assert server.config.host == "127.0.0.1" and server.config.port == 8788
    assert server.config.reload is False
    assert basis.BEENDEN is not None and server.should_exit is False
    basis.BEENDEN()
    assert server.should_exit is True


def test_main_takes_the_port_from_the_environment(mac_app, ersatz_uvicorn, monkeypatch):
    monkeypatch.setenv("BINDUNG_KEIN_BROWSER", "1")
    monkeypatch.setenv("BINDUNG_APP_PORT", "8799")
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, False))
    starter.main()
    assert ersatz_uvicorn.instanzen[0].config.port == 8799


def test_the_daily_task_runs_in_the_app_process(mac_app, ersatz_uvicorn, monkeypatch):
    monkeypatch.setenv("BINDUNG_KEIN_BROWSER", "1")
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, False))
    starter.main()
    assert tagesaufgabe.aktiv() is True   # die Lebensdauer der App startet sie


def test_the_daily_task_stays_off_when_serve_runs_on_the_same_data(
        mac_app, ersatz_uvicorn, monkeypatch, capsys):
    monkeypatch.setenv("BINDUNG_KEIN_BROWSER", "1")
    monkeypatch.setattr(starter, "port_waehlen", lambda wunsch: (wunsch, False))
    monkeypatch.setattr(starter, "serve_teilt_die_daten", lambda: True)
    starter.main()
    assert tagesaufgabe.aktiv() is False
    assert "bindung serve läuft schon" in capsys.readouterr().out


# -------------------------------------------------------------------- Befehl

def test_the_cli_has_the_app_command_and_it_calls_the_starter(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(starter, "main", lambda: aufrufe.append(True))
    laeufer = CliRunner()
    assert "app" in laeufer.invoke(cli.app, ["--help"]).output.split()
    assert laeufer.invoke(cli.app, ["app"]).exit_code == 0
    assert aufrufe == [True]


# ---------------------------------------------------------------- Menueleiste

def test_there_is_no_menu_bar_off_the_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert menueleiste.verfuegbar() is False


def test_the_menu_bar_image_is_the_symbol_of_the_app():
    assert menueleiste.SYMBOL.name == "symbol-menue.png" and menueleiste.SYMBOL.exists()


darwin = pytest.mark.skipif(sys.platform != "darwin", reason="Menüleiste gibt es nur auf dem Mac")


@darwin
def test_the_menu_has_open_data_folder_and_quit():
    """Das Menue selbst; das Symbol in der Leiste braucht ein Fenstersystem und wird von Hand
    und im Rauchtest der gebauten App geprueft."""
    pytest.importorskip("AppKit")
    ziel = menueleiste._ziel().alloc().init()
    menue = menueleiste._menue(ziel, "Bindung")
    titel = [punkt.title() for punkt in menue.itemArray() if not punkt.isSeparatorItem()]
    assert titel == ["Bindung öffnen", "Datenordner zeigen", "Beenden"]


@darwin
def test_the_menu_actions_do_what_they_say(monkeypatch):
    pytest.importorskip("AppKit")
    geoeffnet, ordner = [], []
    monkeypatch.setattr(menueleiste.webbrowser, "open", geoeffnet.append)
    monkeypatch.setattr(menueleiste, "datenordner_zeigen", lambda: ordner.append(True))
    server = type("S", (), {"should_exit": False})()
    ziel = menueleiste._ziel().alloc().init()
    ziel.adresse, ziel.server = "http://127.0.0.1:8788/", server
    ziel.oeffnen_(None)
    ziel.ordner_(None)
    ziel.beenden_(None)
    assert geoeffnet == ["http://127.0.0.1:8788/"] and ordner == [True]
    assert server.should_exit is True
