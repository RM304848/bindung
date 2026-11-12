"""Das Protokoll von `bindung mcp`, ueber Pipes und mit aufgezeichneten JSON-RPC-Zeilen.

Die Zeilen unten sind die, die ein Client schickt (Claude Desktop: initialize, die
Benachrichtigung, tools/list, dann Aufrufe). Alle Namen sind erfunden.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import subprocess
import sys

import pytest

from bindung import auth, kontakte, personen
from bindung.mcp import protokoll, werkzeuge
from tests.conftest import PASSWORT


@pytest.fixture(autouse=True)
def feste_uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.UTC))


def zeile(kennung, methode: str, **params) -> str:
    nachricht = {"jsonrpc": "2.0", "method": methode}
    if kennung is not None:
        nachricht["id"] = kennung
    if params:
        nachricht["params"] = params
    return json.dumps(nachricht)


def aufruf(kennung, werkzeug: str, /, **args) -> str:
    return zeile(kennung, "tools/call", name=werkzeug, arguments=args)


def rohr(*zeilen: str, nutzer: str | None = None) -> list[dict]:
    """Die Zeilen durch `laufen` schicken, wie stdin es taete; die Antworten zurueck."""
    aus = io.StringIO()
    protokoll.laufen(io.StringIO("\n".join(zeilen) + "\n"), aus, nutzer)
    ausgabe = aus.getvalue()
    assert ausgabe == "" or ausgabe.endswith("\n")
    return [json.loads(z) for z in ausgabe.splitlines()]


def text_von(antwort: dict) -> tuple[str, bool]:
    ergebnis = antwort["result"]
    assert len(ergebnis["content"]) == 1 and ergebnis["content"][0]["type"] == "text"
    return ergebnis["content"][0]["text"], ergebnis["isError"]


# --------------------------------------------------------- Handshake

def test_initialize_und_benachrichtigung():
    antworten = rohr(
        zeile(1, "initialize", protocolVersion="2025-06-18", capabilities={},
              clientInfo={"name": "claude-ai", "version": "0.1.0"}),
        zeile(None, "notifications/initialized"),
        zeile(2, "ping"))
    assert [a["id"] for a in antworten] == [1, 2]          # die Benachrichtigung bekommt keine
    erg = antworten[0]["result"]
    assert erg["protocolVersion"] == "2025-06-18"
    assert erg["serverInfo"]["name"] == "bindung"
    assert erg["capabilities"] == {"tools": {}, "resources": {}}
    assert "Touchpoint" in erg["instructions"] and "rate nie" in erg["instructions"]
    assert antworten[1]["result"] == {}


def test_fassungen_werden_ausgehandelt():
    for gewuenscht, erwartet in (("2024-11-05", "2024-11-05"), ("2025-03-26", "2025-03-26"),
                                 ("1999-01-01", "2025-06-18")):
        antwort = rohr(zeile(1, "initialize", protocolVersion=gewuenscht))[0]
        assert antwort["result"]["protocolVersion"] == erwartet


def test_tools_list():
    antwort = rohr(zeile(1, "tools/list"))[0]
    werkzeug = {w["name"]: w for w in antwort["result"]["tools"]}
    assert list(werkzeug) == ["personen_suchen", "person", "wer_wartet", "diese_woche", "tags",
                              "person_anlegen", "touchpoint_eintragen", "profilnotiz_setzen",
                              "stichtag_anlegen"]
    for w in werkzeug.values():
        assert w["inputSchema"]["type"] == "object" and w["description"]
        assert w["inputSchema"]["additionalProperties"] is False
        assert set(w["inputSchema"]["required"]) <= set(w["inputSchema"]["properties"])
    lesend = {n for n, w in werkzeug.items() if w["annotations"]["readOnlyHint"]}
    assert lesend == {"personen_suchen", "person", "wer_wartet", "diese_woche", "tags"}
    # Die Beschreibung sagt, was ein Werkzeug aendert.
    assert all(w["description"].startswith("SCHREIBT") for n, w in werkzeug.items()
               if n not in lesend)
    assert all("Ändert nichts" in werkzeug[n]["description"] for n in lesend)
    schema = werkzeug["touchpoint_eintragen"]["inputSchema"]
    assert schema["required"] == ["person", "art"]
    assert schema["properties"]["person"]["type"] == ["integer", "string"]
    assert schema["properties"]["art"]["enum"] == ["anruf", "nachricht", "email", "treffen",
                                                   "sonstiges"]


def test_fehler_im_protokoll():
    antworten = rohr("kein json", zeile(1, "gibt/es/nicht"),
                     aufruf(2, "loeschen", person=1), "[1]", '{"jsonrpc":"2.0"}',
                     json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "tags", "arguments": [1]}}),
                     zeile(4, "resources/read", uri="bindung://nein"))
    codes = [a["error"]["code"] for a in antworten]
    assert codes == [-32700, -32601, -32602, -32600, -32600, -32602, -32602]
    assert "Unbekanntes Werkzeug: loeschen" in antworten[2]["error"]["message"]


def test_leere_zeilen_werden_uebersprungen():
    assert rohr("", zeile(1, "ping"), "   ")[0]["id"] == 1


def test_stdout_gehoert_dem_protokoll(monkeypatch, capsys, nutzer):
    def laut(k, args):
        print("das darf nicht auf stdout")
        return ["still"]
    monkeypatch.setitem(werkzeuge.WERKZEUGE, "tags",
                        werkzeuge.Werkzeug("tags", "x", laut))
    antworten = rohr(aufruf(1, "tags"))
    assert text_von(antworten[0]) == ("still", False)
    gedruckt = capsys.readouterr()
    assert gedruckt.out == "" and "das darf nicht auf stdout" in gedruckt.err


def test_unerwarteter_fehler_ist_ein_protokollfehler_und_laeuft_weiter(monkeypatch, nutzer):
    def kaputt(k, args):
        raise RuntimeError("Platte voll")
    monkeypatch.setitem(werkzeuge.WERKZEUGE, "tags", werkzeuge.Werkzeug("tags", "x", kaputt))
    antworten = rohr(aufruf(1, "tags"), zeile(2, "ping"))
    assert antworten[0]["error"]["code"] == -32603 and "Platte voll" in \
        antworten[0]["error"]["message"]
    assert antworten[1]["result"] == {}


# ----------------------------------------------- Aufgezeichnete Sitzung

def test_sitzung_person_mit_tags_suche_touchpoint_und_mehrdeutiger_name(nutzer, con):
    """Der Weg, den „Lege Anna Beispiel an, Tag Freunde. … Anruf mit Anna“ nimmt."""
    antworten = rohr(
        zeile(1, "initialize", protocolVersion="2025-06-18"),
        zeile(None, "notifications/initialized"),
        zeile(2, "tools/list"),
        aufruf(3, "person_anlegen", name="Anna Beispiel", firma="Muster GmbH",
               tags=["Freunde", "Chor"], letzter_touchpoint="vor_monaten"),
        aufruf(4, "personen_suchen", text="chor"),
        aufruf(5, "touchpoint_eintragen", person="Anna Beispiel", art="anruf",
               datum="2026-11-11", notiz="Wir haben über den Umzug gesprochen."),
        aufruf(6, "person_anlegen", name="Anna Probe"),
        aufruf(7, "touchpoint_eintragen", person="Anna", art="anruf"),
        aufruf(8, "wer_wartet", karte="aufmerksamkeit"),
        nutzer=nutzer)
    assert [a["id"] for a in antworten] == [1, 2, 3, 4, 5, 6, 7, 8]

    angelegt, fehl = text_von(antworten[2])
    assert not fehl and angelegt.startswith("Person angelegt: Anna Beispiel [")
    assert "Tags: Freunde, Chor" in angelegt and "Neu angelegte Tags: Freunde, Chor." in angelegt
    anna_id = int(angelegt.split("[")[1].split("]")[0])

    suche, fehl = text_von(antworten[3])
    assert not fehl and suche.splitlines()[0] == "1 Person:"
    assert f"- Anna Beispiel [{anna_id}] · Muster GmbH · Tags: Chor, Freunde · " in suche

    eintrag, fehl = text_von(antworten[4])
    assert not fehl
    assert f"Touchpoint eingetragen: Anruf mit Anna Beispiel [{anna_id}] am 2026-11-11" in eintrag
    assert "letzter Touchpoint gestern (2026-11-11)" in eintrag

    assert not text_von(antworten[5])[1]
    mehrdeutig, fehl = text_von(antworten[6])
    assert fehl and "passt auf 2 Personen" in mehrdeutig
    assert f"Anna Beispiel [{anna_id}]" in mehrdeutig and "Anna Probe [" in mehrdeutig

    # Die Sitzung hat wirklich in die Datenbank geschrieben, und nur einmal.
    nid = con.execute("SELECT id FROM nutzer").fetchone()["id"]
    touchpoints = [(t["datum"], t["art"], t["notiz"]) for t in kontakte.liste(con, nid, anna_id)]
    assert touchpoints == [("2026-11-11", "anruf", "Wir haben über den Umzug gesprochen."),
                           ("2026-08-14", "schaetzung", None)]
    assert text_von(antworten[7]) == (
        "Stand: 2026-11-12\n\nBraucht Aufmerksamkeit (0):\n- niemand", False)


def test_resources(nutzer, con):
    antworten = rohr(zeile(1, "resources/list"),
                     zeile(2, "resources/read", uri="bindung://glossar"),
                     zeile(3, "resources/read", uri="bindung://heute"), nutzer=nutzer)
    assert [r["uri"] for r in antworten[0]["result"]["resources"]] == [
        "bindung://glossar", "bindung://heute"]
    glossar = antworten[1]["result"]["contents"][0]
    assert glossar["uri"] == "bindung://glossar" and glossar["mimeType"] == "text/markdown"
    assert "**Touchpoint**" in glossar["text"]
    assert "Heute ist nichts zu sagen" in antworten[2]["result"]["contents"][0]["text"]


# ------------------------------------------------------ Fremde Nutzer

@pytest.fixture
def zwei(con) -> dict[str, int]:
    """Zwei Nutzer; jeder hat eine Person mit Touchpoint, Notiz und Stichtag."""
    ergebnis = {}
    for name, person in (("Eins", "Erika Eins"), ("Zwei", "Zacharias Zwei")):
        nid = auth.nutzer_anlegen(con, name, PASSWORT)
        pid = personen.anlegen(con, nid, person, profilnotiz=f"Geheim von {name}")
        kontakte.eintragen(con, nid, pid, datum="2026-11-01", art="anruf",
                           notiz=f"Notiz von {name}")
        personen.tags_setzen(con, nid, pid, {personen.tag_anlegen(con, nid, f"Tag{name}")})
        ergebnis[name] = pid
    return ergebnis


def test_ein_fremder_nutzer_ist_nie_sichtbar(zwei, con):
    zacharias = zwei["Zwei"]
    antworten = rohr(
        aufruf(1, "personen_suchen"),
        aufruf(2, "personen_suchen", text="Zacharias"),
        aufruf(3, "person", person=zacharias),
        aufruf(4, "person", person="Zacharias Zwei"),
        aufruf(5, "touchpoint_eintragen", person=zacharias, art="anruf", notiz="Eingeschmuggelt"),
        aufruf(6, "profilnotiz_setzen", person=zacharias, text="Überschrieben"),
        aufruf(7, "stichtag_anlegen", person=zacharias, art="geburtstag", datum="--01-01"),
        aufruf(8, "tags"),
        aufruf(9, "wer_wartet"),
        aufruf(10, "personen_suchen", tag="TagZwei"),
        nutzer="Eins")
    texte = [text_von(a) for a in antworten]
    assert "Erika Eins" in texte[0][0] and "Zacharias" not in texte[0][0]
    assert texte[1] == ("0 Personen.", False)
    assert texte[2] == (f"Es gibt keine Person mit der Nummer {zacharias}.", True)
    assert texte[3][1] and "Keine Person mit dem Namen" in texte[3][0]
    assert all(t[1] for t in texte[4:7]) and all(
        f"Nummer {zacharias}" in t[0] for t in texte[4:7])
    assert texte[7][0] == "Tags (Zahl der aktiven Personen):\n- TagEins (1)"
    assert "Zacharias" not in texte[8][0]
    assert texte[9][1] and "TagZwei" in texte[9][0] and "Vorhanden: TagEins" in texte[9][0]
    for gesehen in texte:
        assert "Geheim von Zwei" not in gesehen[0] and "Notiz von Zwei" not in gesehen[0]
    # ... und angefasst wurde nichts.
    zeile_zwei = personen.laden(con, con.execute(
        "SELECT id FROM nutzer WHERE name = 'Zwei'").fetchone()["id"], zacharias)
    assert zeile_zwei["profilnotiz"] == "Geheim von Zwei"
    assert con.execute("SELECT COUNT(*) FROM kontakt").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM stichtag").fetchone()[0] == 0


def test_mehrere_nutzer_ohne_angabe_ist_eine_meldung(zwei):
    text, fehl = text_von(rohr(aufruf(1, "tags"))[0])
    assert fehl and "mehrere Nutzer (Eins, Zwei)" in text and "--nutzer" in text


def test_neue_person_gehoert_dem_gewaehlten_nutzer(zwei, con):
    rohr(aufruf(1, "person_anlegen", name="Neu Dazu", tags=["TagEins"]), nutzer="zwei")
    zeile_ = con.execute("SELECT n.name FROM person p JOIN nutzer n ON n.id = p.nutzer_id "
                         "WHERE p.name = 'Neu Dazu'").fetchone()
    assert zeile_["name"] == "Zwei"
    # Der Tag „TagEins“ gehoert Nutzer Eins; Zwei bekommt einen eigenen.
    assert con.execute("SELECT COUNT(*) FROM tag WHERE name = 'TagEins'").fetchone()[0] == 2


# --------------------------------------------- Der echte Prozess ueber Pipes

def _prozess(daten, *argumente: str, eingabe: str) -> subprocess.CompletedProcess:
    umgebung = {**os.environ, "BINDUNG_DATEN": str(daten)}
    return subprocess.run(
        [sys.executable, "-c", "from bindung.cli import app; app()", "mcp", *argumente],
        input=eingabe, capture_output=True, text=True, encoding="utf-8", env=umgebung,
        timeout=60, check=False)


def test_prozess_stdout_besteht_nur_aus_protokollzeilen(daten, con, nutzer):
    ergebnis = _prozess(daten, eingabe="\n".join([
        zeile(1, "initialize", protocolVersion="2025-06-18"),
        zeile(None, "notifications/initialized"),
        aufruf(2, "person_anlegen", name="Prozess Probe", tags=["Test"]),
        aufruf(3, "personen_suchen", text="prozess"),
    ]) + "\n")
    assert ergebnis.returncode == 0, ergebnis.stderr
    antworten = [json.loads(z) for z in ergebnis.stdout.splitlines()]
    assert [a["id"] for a in antworten] == [1, 2, 3]
    assert "Person angelegt: Prozess Probe" in antworten[1]["result"]["content"][0]["text"]
    assert "1 Person:" in antworten[2]["result"]["content"][0]["text"]
    assert personen.liste(con, con.execute("SELECT id FROM nutzer").fetchone()["id"])


def test_prozess_mit_unbekanntem_nutzer_endet_mit_meldung_auf_stderr(daten, nutzer):
    ergebnis = _prozess(daten, "--nutzer", "Niemand", eingabe="")
    assert ergebnis.returncode == 1 and ergebnis.stdout == ""
    assert "Den Nutzer „Niemand“ gibt es nicht. Vorhanden: Beispiel." in ergebnis.stderr


def test_prozess_ohne_nutzer_in_der_datenbank(daten):
    ergebnis = _prozess(daten, eingabe="")
    assert ergebnis.returncode == 1 and ergebnis.stdout == ""
    assert "bindung nutzer anlegen" in ergebnis.stderr
