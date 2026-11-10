"""Pfade gibt es an einer Stelle: bindung/pfade.py.

Ein Modul, das seinen Pfad selbst baut, scheitert entweder von jedem anderen
Ordner aus oder legt eine zweite, leere Datenbank an. Der Test sucht nach den
Spuren: dem Namen des Systemordners, dem Namen der Datenbankdatei, dem
Heimatverzeichnis -- und nach Konstanten, die per `from ... import` gebunden
werden und sich dann nicht mehr umbiegen lassen.
"""

from __future__ import annotations

from pathlib import Path

from bindung import pfade

PAKET = Path(__file__).resolve().parent.parent / "bindung"
VERBOTEN = ["Application Support", "bindung.db", "vapid.json", "Path.home(", "expanduser(",
            "gettempdir", "from bindung.pfade import", "from .pfade import",
            "from bindung import pfade as"]


def test_keine_eigenen_pfade():
    funde = []
    for datei in PAKET.rglob("*.py"):
        if datei.name == "pfade.py" and datei.parent == PAKET:
            continue
        text = datei.read_text(encoding="utf-8")
        funde += [f"{datei.relative_to(PAKET.parent)}: {muster}"
                  for muster in VERBOTEN if muster in text]
    assert not funde, "Eigene Pfade gefunden:\n" + "\n".join(funde)


def test_wurzel_aus_umgebung(monkeypatch, tmp_path):
    monkeypatch.setenv("BINDUNG_DATEN", str(tmp_path / "x"))
    assert pfade.wurzel_mit_grund() == (tmp_path / "x", "BINDUNG_DATEN")


def test_vorgabe_des_systems(monkeypatch):
    monkeypatch.delenv("BINDUNG_DATEN", raising=False)
    wurzel, grund = pfade.wurzel_mit_grund()
    assert grund == "Vorgabe dieses Systems"
    assert wurzel.name in (pfade.ORDNER, pfade.ORDNER_UNIX)


def test_alle_pfade_haengen_an_der_wurzel():
    for pfad in (pfade.DB_PATH, pfade.VAPID_PATH, pfade.SICHERUNG_DIR):
        assert pfade.DATEN in pfad.parents


def test_tests_laufen_nicht_auf_echten_daten(daten):
    """Die Fixture `daten` biegt alle Konstanten in den Wegwerfordner des Tests."""
    for pfad in (pfade.DB_PATH, pfade.VAPID_PATH, pfade.SICHERUNG_DIR):
        assert daten in pfad.parents
    assert "Application Support" not in str(pfade.DB_PATH)
