"""Wo die Daten liegen -- an einer Stelle.

Jeder Pfad dieser App haengt an EINER Wurzel, dem Datenordner. Darin liegen
die Datenbank, die Push-Schluessel und die Sicherungen.

WER DIE WURZEL BESTIMMT, in dieser Reihenfolge:

1. `BINDUNG_DATEN`. Wer die Variable setzt, meint es -- fuer einen zweiten
   Bestand, fuer einen Test, im Container fuer das eingehaengte Volume.
2. Sonst die Vorgabe des Systems: `~/Library/Application Support/Bindung` auf
   macOS, `%APPDATA%\\Bindung` auf Windows, `~/.local/share/bindung` sonst.

DIE KONSTANTEN WERDEN BEIM IMPORT GELESEN. Module lesen sie als
`pfade.DB_PATH` (Attribut, nicht per `from ... import`), damit ein Test sie
umbiegen kann; `tests/conftest.py` setzt ausserdem `BINDUNG_DATEN` vor dem
ersten Import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Wie der Ordner heisst, den die App sich selbst anlegt. Gross, weil macOS und
#: Windows ihre Anwendungsordner so beschriften; auf Linux klein.
ORDNER = "Bindung"
ORDNER_UNIX = "bindung"


def standard() -> Path:
    """Wo der Datenordner liegt, wenn niemand etwas anderes sagt."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or "~/AppData/Roaming").expanduser() / ORDNER
    if sys.platform == "darwin":
        return Path("~/Library/Application Support").expanduser() / ORDNER
    basis = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return Path(basis).expanduser() / ORDNER_UNIX


def wurzel_mit_grund() -> tuple[Path, str]:
    """Der Datenordner und warum er es ist -- fuer `bindung ort`.

    Die Begruendung mitzugeben ist kein Luxus: wenn die App den falschen
    Bestand aufmacht, ist die einzige nuetzliche Auskunft, WELCHE Regel
    gegriffen hat.
    """
    gesetzt = os.environ.get("BINDUNG_DATEN")
    if gesetzt:
        return Path(gesetzt).expanduser(), "BINDUNG_DATEN"
    return standard(), "Vorgabe dieses Systems"


def wurzel() -> Path:
    """Der Datenordner."""
    return wurzel_mit_grund()[0]


#: Die Wurzel, einmal beim Import bestimmt.
DATEN = wurzel()

#: Die Datenbank.
DB_PATH = DATEN / "bindung.db"

#: Die Push-Schluessel (VAPID), beim ersten Start erzeugt (WP5).
VAPID_PATH = DATEN / "vapid.json"

#: Wohin `bindung sichern` die datierten JSON-Dateien schreibt.
SICHERUNG_DIR = DATEN / "sicherung"
