"""Die Datenbank: verbinden, Schema anlegen, Versionen mitfuehren.

`verbinden()` ist der einzige Weg an die SQLite-Datei. Es legt den Ordner an,
wendet das Schema idempotent an und spielt fehlende Migrationen nach.

Eine spaetere Aenderung am Schema kommt NICHT in schema.sql allein, sondern als
neuer Eintrag in `MIGRATIONEN`: schema.sql legt frische Datenbanken auf dem
Stand von Version 1 an, die Migrationen bringen jede Datenbank von dort auf
den heutigen Stand. Eine bestehende Datenbank liest schema.sql nie neu ein --
`CREATE TABLE IF NOT EXISTS` aendert keine vorhandene Tabelle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bindung import pfade

SCHEMA = Path(__file__).with_name("schema.sql")

#: Nummerierte Migrationen ab Version 2. `MIGRATIONEN[0]` hebt Version 1 auf 2.
#: Jeder Eintrag ist ein SQL-Skript (mehrere Anweisungen erlaubt).
MIGRATIONEN: list[str] = [
    # 2: Darstellung (hell, dunkel oder dem Geraet folgen), je Nutzer.
    ("ALTER TABLE nutzer ADD COLUMN darstellung TEXT NOT NULL DEFAULT 'system' "
     "CHECK (darstellung IN ('system', 'hell', 'dunkel'));"),
]

#: Der Stand, auf dem schema.sql eine frische Datenbank anlegt.
BASISVERSION = 1


def aktuelle_version() -> int:
    """Die Version, die `verbinden()` herstellt."""
    return BASISVERSION + len(MIGRATIONEN)


def _version(con: sqlite3.Connection) -> int:
    zeile = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return zeile[0] if zeile and zeile[0] is not None else 0


def verbinden(pfad: Path | str | None = None) -> sqlite3.Connection:
    """Eine Verbindung mit Zeilen als `sqlite3.Row`, Fremdschluesseln und WAL.

    Ohne `pfad` gilt `pfade.DB_PATH`. Die Modulkonstante wird zur Laufzeit
    gelesen (nicht als Vorgabewert gebunden), damit ein Test sie am Modul
    umbiegen kann.
    """
    ziel = Path(pfad) if pfad is not None else pfade.DB_PATH
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Der Server oeffnet die Verbindung in der Schicht vor der Route und
    # benutzt sie im Arbeitsfaden der Route. Sie gehoert genau einer Anfrage
    # und wird nie gleichzeitig benutzt, also ist das sicher.
    con = sqlite3.connect(ziel, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrieren(con)
    return con


def _migrieren(con: sqlite3.Connection) -> None:
    stand = _version(con)
    if stand == 0:
        con.execute("INSERT INTO schema_version (version) VALUES (?)", (BASISVERSION,))
        stand = BASISVERSION
    for nummer in range(stand + 1, aktuelle_version() + 1):
        con.executescript(MIGRATIONEN[nummer - BASISVERSION - 1])
        con.execute("UPDATE schema_version SET version = ?", (nummer,))
    con.commit()


def version(con: sqlite3.Connection) -> int:
    """Der Stand der Datenbank hinter `con`."""
    return _version(con)
