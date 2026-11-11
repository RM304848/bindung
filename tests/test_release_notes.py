"""`werkzeuge/release_notes.py`: der Abschnitt einer Version aus CHANGELOG.md."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

import bindung

WURZEL = Path(__file__).resolve().parent.parent
SKRIPT = WURZEL / "werkzeuge" / "release_notes.py"
CHANGELOG = WURZEL / "CHANGELOG.md"

BEISPIEL = """# Änderungen

Einleitung.

## Unveröffentlicht

### Neu

- Etwas Neues, noch nicht ausgeliefert.

## 0.2.0 (2027-01-05)

Das zweite.

### Neu

- Zwei.

## 0.1.0 (2026-11-11)

Das erste.

- Eins.
"""


def _modul():
    spec = importlib.util.spec_from_file_location("release_notes", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_a_section_is_exactly_what_stands_between_its_heading_and_the_next():
    notizen = _modul().abschnitt(BEISPIEL, "0.2.0")
    assert notizen == "Das zweite.\n\n### Neu\n\n- Zwei."


def test_the_last_section_runs_to_the_end_of_the_file():
    assert _modul().abschnitt(BEISPIEL, "0.1.0") == "Das erste.\n\n- Eins."


def test_unreleased_is_not_a_version_and_a_prefix_does_not_match():
    assert _modul().abschnitt(BEISPIEL, "0.2") == ""
    assert _modul().abschnitt(BEISPIEL, "0.3.0") == ""
    assert "Unveröffentlicht" not in _modul().abschnitt(BEISPIEL, "0.2.0")


def test_the_first_line_is_the_first_sentence_not_a_heading_or_a_bullet():
    erste = _modul().erste_zeile
    assert erste("Das erste.\n\n- Eins.") == "Das erste."
    assert erste("### Neu\n\n- Eins.\n\nDann Text.") == "Dann Text."


def _lauf(*argumente: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(SKRIPT), *argumente],
                          capture_output=True, text=True, check=False)


def test_the_script_prints_the_0_1_0_section_of_the_real_changelog():
    lauf = _lauf("0.1.0")
    assert lauf.returncode == 0, lauf.stderr
    erwartet = _modul().abschnitt(CHANGELOG.read_text(encoding="utf-8"), "0.1.0")
    assert lauf.stdout == erwartet + "\n"
    assert erwartet, "0.1.0 hat keine Notizen"
    assert not lauf.stdout.startswith("##")
    assert "Unveröffentlicht" not in lauf.stdout
    # Genau diese Version: nichts aus dem Abschnitt davor oder danach.
    assert "## " not in lauf.stdout.replace("###", "")


def test_the_script_accepts_a_leading_v_and_prints_the_first_line():
    erste = _lauf("v0.1.0", "--erste-zeile")
    assert erste.returncode == 0 and erste.stdout.count("\n") == 1
    assert erste.stdout.strip() == _modul().erste_zeile(_lauf("0.1.0").stdout)


def test_an_unknown_version_fails_instead_of_printing_nothing():
    lauf = _lauf("9.9.9")
    assert lauf.returncode != 0 and lauf.stdout == ""
    assert "9.9.9" in lauf.stderr


def test_the_version_in_the_package_has_release_notes():
    """Wer die Nummer erhoeht, schreibt vorher die Notizen (CLAUDE.md)."""
    assert _modul().abschnitt(CHANGELOG.read_text(encoding="utf-8"), bindung.__version__)


def test_unreleased_stays_the_first_section_of_the_changelog():
    ueberschriften = [z for z in CHANGELOG.read_text(encoding="utf-8").splitlines()
                      if z.startswith("## ")]
    assert ueberschriften[0] == "## Unveröffentlicht"


@pytest.mark.parametrize("text", ["## 1.0.0 (2027-01-01)\n\nA.\n", "## 1.0.0\n\nA.\n"])
def test_the_date_in_the_heading_is_optional(text):
    assert _modul().abschnitt(text, "1.0.0") == "A."
