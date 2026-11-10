"""Ruff laeuft als Test, nicht als Gewohnheit.

Ein Werkzeug, das man aufrufen muss, um davon zu profitieren, wird irgendwann
nicht mehr aufgerufen -- also laeuft es hier mit. Die Regelauswahl steht in
pyproject.toml, mit Begruendung je Ausnahme.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def test_ruff_finds_nothing():
    """Null Funde, nicht "wenige".

    Eine Liste geduldeter Funde waere nach dem dritten Eintrag nur noch eine
    Liste. Was geduldet wird, gehoert in die Konfiguration -- dort steht
    daneben, warum.
    """
    lauf = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "concise", "."],
        cwd=WURZEL, capture_output=True, text=True, check=False)
    assert lauf.returncode == 0, "ruff meldet:\n" + (lauf.stdout or lauf.stderr)
