"""Kontakte: eintragen, aendern, loeschen, lesen (PLAN.md, Abschnitte 5 bis 7).

Reine Funktionen auf einer `sqlite3.Connection`, ohne Web. Jede Funktion
bekommt die `nutzer_id` und filtert danach; eine Nummer, die einem anderen
Nutzer gehoert, ist fuer diese Funktionen nicht vorhanden (`NichtGefunden`).

Ein Kontakt wird nie ueberschrieben, nur ergaenzt -- `aendern` korrigiert einen
Tippfehler, es ersetzt keine Geschichte. Faelligkeit und Zustand rechnet
`faelligkeit.py`; hier steht nur, was in der Tabelle `kontakt` steht.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from bindung import personen
from bindung.personen import EingabeFehler, NichtGefunden

#: Die Arten, die der Nutzer waehlt, mit ihrem Namen in der Oberflaeche.
ARTEN = {"anruf": "Anruf", "nachricht": "Nachricht", "email": "E-Mail",
         "treffen": "Treffen", "sonstiges": "Sonstiges"}
#: Der grobe letzte Kontakt aus „Mehrere hinzufuegen“: ohne Notiz, nur ein Datum.
SCHAETZUNG = "schaetzung"
ART_NAMEN = {**ARTEN, SCHAETZUNG: "Schätzung"}

FELDER = ("datum", "art", "notiz")


def _tag(wert: object, heute: dt.date) -> str:
    """Ein Datum als ISO-Tag; kein Datum oder ein Tag in der Zukunft wird abgelehnt."""
    text = str(wert or "").strip()
    try:
        tag = dt.date.fromisoformat(text)
    except ValueError:
        raise EingabeFehler("Das Datum ist ungültig.") from None
    if tag > heute:
        raise EingabeFehler("Das Datum liegt in der Zukunft. Trag nur ein, was schon war.")
    return tag.isoformat()


def _art(wert: object) -> str:
    art = str(wert or "").strip()
    if art not in ARTEN:
        raise EingabeFehler("Wähle aus, wie ihr euch ausgetauscht habt.")
    return art


def _notiz(wert: object) -> str | None:
    text = str(wert or "").strip()
    return text or None


def laden(con: sqlite3.Connection, nutzer_id: int, kontakt_id: int) -> sqlite3.Row | None:
    """Der Kontakt, oder `None` -- auch wenn er einem anderen Nutzer gehoert."""
    return con.execute("SELECT * FROM kontakt WHERE id = ? AND nutzer_id = ?",
                       (kontakt_id, nutzer_id)).fetchone()


def _kontakt(con: sqlite3.Connection, nutzer_id: int, kontakt_id: int) -> sqlite3.Row:
    zeile = laden(con, nutzer_id, kontakt_id)
    if zeile is None:
        raise NichtGefunden(f"Kontakt {kontakt_id}")
    return zeile


def eintragen(con: sqlite3.Connection, nutzer_id: int, person_id: int, *,
              datum: str | dt.date, art: str, notiz: str | None = None) -> int:
    """Traegt einen Kontakt ein und loescht den naechsten Termin der Person.

    Der naechste Termin ersetzt das Intervall nur fuer ein Mal (PLAN.md,
    Abschnitt 6); mit dem Kontakt hat er seine Arbeit getan.
    """
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    tag = _tag(datum.isoformat() if isinstance(datum, dt.date) else datum,
               personen.heute(con, nutzer_id))
    art = _art(art)
    try:
        kontakt_id = con.execute(
            "INSERT INTO kontakt (nutzer_id, person_id, datum, art, notiz) VALUES (?, ?, ?, ?, ?)",
            (nutzer_id, person_id, tag, art, _notiz(notiz))).lastrowid
        con.execute("UPDATE person SET naechster_termin = NULL WHERE id = ? AND nutzer_id = ?",
                    (person_id, nutzer_id))
    except Exception:
        con.rollback()
        raise
    con.commit()
    return kontakt_id


def schaetzung_eintragen(con: sqlite3.Connection, nutzer_id: int, person_id: int,
                         grober_kontakt: str) -> int:
    """Traegt den groben letzten Touchpoint ein, wie „Mehrere hinzufuegen“ ihn setzt.

    `grober_kontakt` ist ein Schluessel aus `personen.GROBER_KONTAKT`.

    Eine Schaetzung hat ein ungefaehres Datum, keine Notiz, und loescht den naechsten Termin
    nicht: sie ist kein Gespraech, nur der Startwert fuer die Faelligkeit.
    """
    if grober_kontakt not in personen.GROBER_KONTAKT:
        raise EingabeFehler("Unbekannte Angabe zum letzten Touchpoint.")
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    tage = personen.GROBER_KONTAKT[grober_kontakt]
    tag = personen.heute(con, nutzer_id) - dt.timedelta(days=tage)
    kontakt_id = con.execute(
        "INSERT INTO kontakt (nutzer_id, person_id, datum, art) VALUES (?, ?, ?, ?)",
        (nutzer_id, person_id, tag.isoformat(), SCHAETZUNG)).lastrowid
    con.commit()
    return kontakt_id


def aendern(con: sqlite3.Connection, nutzer_id: int, kontakt_id: int, **felder) -> None:
    """Korrigiert Datum, Art oder Notiz; was nicht genannt ist, bleibt.

    Eine Schaetzung hat weder Art noch Notiz -- an ihr aenderst du nur das Datum.
    Der naechste Termin der Person bleibt unberuehrt.
    """
    unbekannt = set(felder) - set(FELDER)
    if unbekannt:
        raise ValueError(f"Unbekannte Felder: {sorted(unbekannt)}")
    alt = _kontakt(con, nutzer_id, kontakt_id)
    if alt["art"] == SCHAETZUNG and (set(felder) - {"datum"}):
        raise EingabeFehler("An einer Schätzung lässt sich nur das Datum ändern.")
    werte: dict[str, str | None] = {}
    if "datum" in felder:
        werte["datum"] = _tag(felder["datum"], personen.heute(con, nutzer_id))
    if "art" in felder:
        werte["art"] = _art(felder["art"])
    if "notiz" in felder:
        werte["notiz"] = _notiz(felder["notiz"])
    if not werte:
        return
    zuweisung = ", ".join(f"{spalte} = ?" for spalte in werte)
    con.execute(f"UPDATE kontakt SET {zuweisung} WHERE id = ? AND nutzer_id = ?",
                (*werte.values(), kontakt_id, nutzer_id))
    con.commit()


def loeschen(con: sqlite3.Connection, nutzer_id: int, kontakt_id: int) -> int:
    """Loescht den Kontakt und gibt die Nummer seiner Person zurueck."""
    person_id = _kontakt(con, nutzer_id, kontakt_id)["person_id"]
    con.execute("DELETE FROM kontakt WHERE id = ? AND nutzer_id = ?", (kontakt_id, nutzer_id))
    con.commit()
    return person_id


def liste(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> list[sqlite3.Row]:
    """Zuletzt besprochen: die Kontakte der Person, juengster zuerst."""
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    return con.execute(
        "SELECT * FROM kontakt WHERE person_id = ? AND nutzer_id = ? "
        "ORDER BY datum DESC, id DESC", (person_id, nutzer_id)).fetchall()


def letzter_kontakt(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> dt.date | None:
    """Das Datum des juengsten Kontakts, oder `None`."""
    zeile = con.execute(
        "SELECT MAX(datum) AS datum FROM kontakt WHERE person_id = ? AND nutzer_id = ?",
        (person_id, nutzer_id)).fetchone()
    return dt.date.fromisoformat(zeile["datum"]) if zeile["datum"] else None


def letzte_notizen(con: sqlite3.Connection, nutzer_id: int) -> dict[int, str]:
    """Je Person die Notiz des juengsten Kontakts, der eine hat -- fuer die Zeile der Liste.

    Eine Schaetzung hat nie eine Notiz und zaehlt deshalb nicht.
    """
    notizen: dict[int, str] = {}
    for zeile in con.execute(
            "SELECT person_id, notiz FROM kontakt WHERE nutzer_id = ? AND notiz IS NOT NULL "
            "AND art != ? ORDER BY datum DESC, id DESC", (nutzer_id, SCHAETZUNG)):
        notizen.setdefault(zeile["person_id"], zeile["notiz"])
    return notizen


def mit_echtem_kontakt(con: sqlite3.Connection, nutzer_id: int) -> set[int]:
    """Die Personen mit mindestens einem Kontakt, der keine Schaetzung ist."""
    return {z["person_id"] for z in con.execute(
        "SELECT DISTINCT person_id FROM kontakt WHERE nutzer_id = ? AND art != ?",
        (nutzer_id, SCHAETZUNG))}
