"""Angehoerige einer Person und ihre Verknuepfung (PLAN.md, Abschnitte 5 und 7).

Reine Funktionen auf einer `sqlite3.Connection`, ohne Web. Jede Funktion
bekommt die `nutzer_id` und filtert danach; eine Nummer, die einem anderen
Nutzer gehoert, ist fuer diese Funktionen nicht vorhanden (`NichtGefunden`).

Verknuepfung ist symmetrisch: Verknuepft der Nutzer einen Angehoerigen mit einer
anderen Person in der App, entsteht bei dieser das Gegenstueck mit der
umgekehrten Rolle, und beide Zeilen zeigen aufeinander (`gegenstueck_id`). Die
Rolle des Gegenstuecks ist danach eigenstaendig bearbeitbar. Loest der Nutzer die
Verknuepfung oder loescht er eine Seite, verschwindet die Gegenseite mit.

Ein Geburtstag am Angehoerigen ist ein Stichtag der Person (`stichtage.py`) und
wird hier mitgefuehrt: gleiche Aenderung, gleicher `commit`.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from bindung import personen, stichtage
from bindung.personen import EingabeFehler, NichtGefunden

#: Die Rollen mit ihrem Wort in der Oberflaeche.
ROLLEN = {"partner": "Partner/in", "kind": "Kind", "elternteil": "Elternteil",
          "geschwister": "Geschwister", "sonstiges": "Sonstiges"}
SONSTIGES = "sonstiges"

#: Die Rolle auf der anderen Seite: wer fuer mich ein Kind ist, fuer den bin ich Elternteil.
INVERSE = {"partner": "partner", "kind": "elternteil", "elternteil": "kind",
           "geschwister": "geschwister", "sonstiges": "sonstiges"}

FELDER = ("name", "rolle", "rolle_text", "geburtstag")

#: So viele Treffer zeigt die Auswahl beim Verknuepfen, mehr passt nicht in die Hand.
TREFFER_HOECHSTENS = 8

_ABFRAGE = ("SELECT a.*, v.name AS verknuepft_name, "
            " COALESCE(v.archiviert_am IS NOT NULL, 0) AS verknuepft_archiviert "
            "FROM angehoeriger a "
            "LEFT JOIN person v ON v.id = a.verknuepfte_person_id AND v.nutzer_id = a.nutzer_id ")


def rolle_wort(zeile: sqlite3.Row) -> str:
    """Die Rolle als Wort: bei „Sonstiges“ der Freitext, wenn einer da ist."""
    if zeile["rolle"] == SONSTIGES:
        return zeile["rolle_text"] or ROLLEN[SONSTIGES]
    return ROLLEN[zeile["rolle"]]


# ------------------------------------------------------------------ Eingaben

def _rolle(wert: object) -> str:
    rolle = str(wert or "").strip()
    if rolle not in ROLLEN:
        raise EingabeFehler("Wähle eine Rolle aus.")
    return rolle


def _name(wert: object) -> str:
    name = str(wert or "").strip()
    if not name:
        raise EingabeFehler("Der Name darf nicht leer sein.")
    return name


def _text_oder_none(wert: object) -> str | None:
    text = str(wert or "").strip()
    return text or None


def _geburtstag(wert: object, heute: dt.date) -> str | None:
    text = _text_oder_none(wert)
    return stichtage.pruefen(text, heute) if text else None


# ------------------------------------------------------------------ Zugriff

def laden(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int) -> sqlite3.Row | None:
    """Der Angehoerige (mit `verknuepft_name`), oder `None` -- auch wenn er fremd ist."""
    return con.execute(_ABFRAGE + "WHERE a.id = ? AND a.nutzer_id = ?",
                       (angehoeriger_id, nutzer_id)).fetchone()


def _eintrag(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int) -> sqlite3.Row:
    zeile = laden(con, nutzer_id, angehoeriger_id)
    if zeile is None:
        raise NichtGefunden(f"Angehöriger {angehoeriger_id}")
    return zeile


def liste(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> list[sqlite3.Row]:
    """Die Angehoerigen der Person in der Reihenfolge, in der sie eingetragen wurden."""
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    return con.execute(_ABFRAGE + "WHERE a.person_id = ? AND a.nutzer_id = ? ORDER BY a.id",
                       (person_id, nutzer_id)).fetchall()


def verknuepfbare(con: sqlite3.Connection, nutzer_id: int, person_id: int,
                  suche: str) -> tuple[list[sqlite3.Row], bool]:
    """Aktive Personen, die zur Suche passen, ohne die Person selbst -- fuer die Auswahl.

    Gibt (Treffer, gibt_es_mehr) zurueck; ohne Suchtext gibt es keine Treffer.
    """
    if not suche.strip():
        return [], False
    treffer = [p for p in personen.liste(con, nutzer_id, suche=suche) if p["id"] != person_id]
    return treffer[:TREFFER_HOECHSTENS], len(treffer) > TREFFER_HOECHSTENS


# ------------------------------------------------------- Anlegen, Aendern, Loeschen

def anlegen(con: sqlite3.Connection, nutzer_id: int, person_id: int, *, name: object,
            rolle: object, rolle_text: object = None, geburtstag: object = None,
            verknuepfte_person_id: int | None = None) -> int:
    """Legt einen Angehoerigen an; mit `verknuepfte_person_id` gleich verknuepft.

    Ist der Name leer und der Angehoerige verknuepft, ist es der Name der anderen Person.
    """
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    andere = None
    if verknuepfte_person_id is not None:
        andere = _verknuepfbare_person(con, nutzer_id, person_id, verknuepfte_person_id)
        if not str(name or "").strip():
            name = andere["name"]
    heute = personen.heute(con, nutzer_id)
    name, rolle = _name(name), _rolle(rolle)
    text = _text_oder_none(rolle_text) if rolle == SONSTIGES else None
    tag = _geburtstag(geburtstag, heute)
    try:
        neu = con.execute(
            "INSERT INTO angehoeriger (nutzer_id, person_id, name, rolle, rolle_text, geburtstag) "
            "VALUES (?, ?, ?, ?, ?, ?)", (nutzer_id, person_id, name, rolle, text, tag)).lastrowid
        stichtage.geburtstag_abgleichen(con, nutzer_id, _eintrag(con, nutzer_id, neu))
        if andere is not None:
            _verknuepfen(con, nutzer_id, _eintrag(con, nutzer_id, neu), andere)
    except Exception:
        con.rollback()
        raise
    con.commit()
    return neu


def aendern(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int, **felder) -> None:
    """Setzt die genannten Felder; die anderen bleiben, wie sie sind.

    Das Gegenstueck bleibt unberuehrt: jede Seite hat ihre eigene Rolle und ihren
    eigenen Namen. Der Geburtstag zieht den Stichtag der Person mit.
    """
    unbekannt = set(felder) - set(FELDER)
    if unbekannt:
        raise ValueError(f"Unbekannte Felder: {sorted(unbekannt)}")
    alt = _eintrag(con, nutzer_id, angehoeriger_id)
    werte: dict[str, object] = {}
    if "name" in felder:
        werte["name"] = _name(felder["name"])
    if "rolle" in felder:
        werte["rolle"] = _rolle(felder["rolle"])
    rolle = werte.get("rolle", alt["rolle"])
    if "rolle_text" in felder or "rolle" in werte:
        # Der Freitext gehoert zu „Sonstiges“; bei einer anderen Rolle bleibt er nicht stehen.
        quelle = felder["rolle_text"] if "rolle_text" in felder else alt["rolle_text"]
        werte["rolle_text"] = _text_oder_none(quelle) if rolle == SONSTIGES else None
    if "geburtstag" in felder:
        werte["geburtstag"] = _geburtstag(felder["geburtstag"], personen.heute(con, nutzer_id))
    if not werte:
        return
    zuweisung = ", ".join(f"{spalte} = ?" for spalte in werte)
    try:
        con.execute(f"UPDATE angehoeriger SET {zuweisung} WHERE id = ? AND nutzer_id = ?",
                    (*werte.values(), angehoeriger_id, nutzer_id))
        stichtage.geburtstag_abgleichen(con, nutzer_id, _eintrag(con, nutzer_id, angehoeriger_id))
    except Exception:
        con.rollback()
        raise
    con.commit()


def _gegenseite_entfernen(con: sqlite3.Connection, nutzer_id: int,
                          eintrag: sqlite3.Row) -> None:
    """Loescht das Gegenstueck von `eintrag` samt seinem Stichtag (kein `commit`)."""
    if eintrag["gegenstueck_id"] is None:
        return
    gegen = eintrag["gegenstueck_id"]
    con.execute("UPDATE angehoeriger SET gegenstueck_id = NULL WHERE id = ? AND nutzer_id = ?",
                (eintrag["id"], nutzer_id))
    con.execute("DELETE FROM stichtag WHERE angehoeriger_id = ? AND nutzer_id = ?",
                (gegen, nutzer_id))
    con.execute("DELETE FROM angehoeriger WHERE id = ? AND nutzer_id = ?", (gegen, nutzer_id))


def loeschen(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int) -> int:
    """Loescht den Angehoerigen, sein Gegenstueck und die Geburtstage dazu.

    Gibt die Nummer der Person zurueck, bei der er stand.
    """
    eintrag = _eintrag(con, nutzer_id, angehoeriger_id)
    try:
        _gegenseite_entfernen(con, nutzer_id, eintrag)
        con.execute("DELETE FROM stichtag WHERE angehoeriger_id = ? AND nutzer_id = ?",
                    (angehoeriger_id, nutzer_id))
        con.execute("DELETE FROM angehoeriger WHERE id = ? AND nutzer_id = ?",
                    (angehoeriger_id, nutzer_id))
    except Exception:
        con.rollback()
        raise
    con.commit()
    return eintrag["person_id"]


# ------------------------------------------------------------------ Verknuepfung

def _verknuepfbare_person(con: sqlite3.Connection, nutzer_id: int, person_id: int,
                          andere_id: int) -> sqlite3.Row:
    andere = personen.laden(con, nutzer_id, andere_id)
    if andere is None:
        raise NichtGefunden(f"Person {andere_id}")
    if andere_id == person_id:
        raise EingabeFehler("Eine Person lässt sich nicht mit sich selbst verknüpfen.")
    return andere


def _verknuepfen(con: sqlite3.Connection, nutzer_id: int, eintrag: sqlite3.Row,
                 andere: sqlite3.Row) -> int:
    """Schreibt die Verknuepfung und das Gegenstueck (kein `commit`); gibt dessen Nummer zurueck."""
    if eintrag["verknuepfte_person_id"] is not None:
        raise EingabeFehler(f"Dieser Angehörige ist schon mit {eintrag['verknuepft_name']} "
                            "verknüpft. Löse die Verknüpfung zuerst.")
    eigene = personen.laden(con, nutzer_id, eintrag["person_id"])
    rolle = INVERSE[eintrag["rolle"]]
    text = eintrag["rolle_text"] if rolle == SONSTIGES else None
    gegen = con.execute(
        "INSERT INTO angehoeriger (nutzer_id, person_id, name, rolle, rolle_text, "
        "verknuepfte_person_id, gegenstueck_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nutzer_id, andere["id"], eigene["name"], rolle, text, eintrag["person_id"],
         eintrag["id"])).lastrowid
    con.execute("UPDATE angehoeriger SET verknuepfte_person_id = ?, gegenstueck_id = ? "
                "WHERE id = ? AND nutzer_id = ?", (andere["id"], gegen, eintrag["id"], nutzer_id))
    return gegen


def verknuepfen(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int,
                person_id: int) -> int:
    """Verknuepft den Angehoerigen mit einer Person in der App und legt dort das Gegenstueck an.

    Gibt die Nummer des Gegenstuecks zurueck. Abgelehnt wird: eine fremde Person
    (`NichtGefunden`), die Person selbst, ein Angehoeriger, der schon verknuepft ist.
    """
    eintrag = _eintrag(con, nutzer_id, angehoeriger_id)
    andere = _verknuepfbare_person(con, nutzer_id, eintrag["person_id"], person_id)
    try:
        gegen = _verknuepfen(con, nutzer_id, eintrag, andere)
    except Exception:
        con.rollback()
        raise
    con.commit()
    return gegen


def entknuepfen(con: sqlite3.Connection, nutzer_id: int, angehoeriger_id: int) -> None:
    """Loest die Verknuepfung: dieser Eintrag bleibt als einfacher Eintrag, das Gegenstueck geht."""
    eintrag = _eintrag(con, nutzer_id, angehoeriger_id)
    if eintrag["verknuepfte_person_id"] is None:
        raise EingabeFehler("Dieser Angehörige ist nicht verknüpft.")
    try:
        _gegenseite_entfernen(con, nutzer_id, eintrag)
        con.execute("UPDATE angehoeriger SET verknuepfte_person_id = NULL, gegenstueck_id = NULL "
                    "WHERE id = ? AND nutzer_id = ?", (angehoeriger_id, nutzer_id))
    except Exception:
        con.rollback()
        raise
    con.commit()
