"""Personen und Tags (PLAN.md, Abschnitte 5 und 7).

Reine Funktionen auf einer `sqlite3.Connection`, ohne Web. Jede Funktion
bekommt die `nutzer_id` und filtert danach; eine Nummer, die einem anderen
Nutzer gehoert, ist fuer diese Funktionen nicht vorhanden (`NichtGefunden`).

Zustand, Faelligkeit und Kontakte eintragen kommen in WP2 -- hier wird nur
gefragt, OB eine Person einen Kontakt hat ("Noch kein Touchpoint").
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from zoneinfo import ZoneInfo

#: Die Felder der Person, die `aendern` kennt (alle ausser Nummer und Zeitstempel).
FELDER = ("name", "firma", "rolle", "telefon", "email", "ort", "herkunft", "profilnotiz",
          "intervall_tage", "naechster_termin")

#: Grobe Angabe zum letzten Kontakt -> Tage vor heute (PLAN.md, Abschnitt 5).
GROBER_KONTAKT = {"diesen_monat": 15, "vor_monaten": 90, "ueber_ein_jahr": 400}
UNBEKANNT = "unbekannt"

FILTER_OHNE_KONTAKT = "ohne_kontakt"
FILTER_ARCHIV = "archiv"

_ZEITFORMAT = "%Y-%m-%dT%H:%M:%SZ"


class EingabeFehler(ValueError):
    """Eine Eingabe, die abgelehnt wird; der Text ist fuer den Nutzer gedacht."""


class NichtGefunden(LookupError):
    """Die Person oder der Tag gibt es nicht -- oder sie gehoeren einem anderen Nutzer."""


def _jetzt() -> dt.datetime:
    """Die Uhr; Tests biegen sie um."""
    return dt.datetime.now(dt.UTC)


def heute(con: sqlite3.Connection, nutzer_id: int) -> dt.date:
    """Der heutige Tag in der Zeitzone des Nutzers."""
    zeile = con.execute("SELECT zeitzone FROM nutzer WHERE id = ?", (nutzer_id,)).fetchone()
    zone = ZoneInfo(zeile["zeitzone"] if zeile else "Europe/Berlin")
    return _jetzt().astimezone(zone).date()


# --------------------------------------------------------------- Eingaben

def _text_oder_none(wert: object) -> str | None:
    if wert is None:
        return None
    text = str(wert).strip()
    return text or None


def _felder_pruefen(felder: dict) -> dict:
    """Bereinigt die Eingaben; wirft `EingabeFehler` mit deutschem Text."""
    unbekannt = set(felder) - set(FELDER)
    if unbekannt:
        raise ValueError(f"Unbekannte Felder: {sorted(unbekannt)}")
    sauber: dict = {}
    for feld, wert in felder.items():
        if feld == "name":
            name = (wert or "").strip()
            if not name:
                raise EingabeFehler("Der Name darf nicht leer sein.")
            sauber[feld] = name
        elif feld == "intervall_tage":
            text = _text_oder_none(wert)
            if text is None:
                sauber[feld] = None
                continue
            try:
                tage = int(text)
            except ValueError:
                raise EingabeFehler("Das Intervall ist eine Zahl in Tagen.") from None
            if tage < 1:
                raise EingabeFehler("Das Intervall muss mindestens 1 Tag sein.")
            sauber[feld] = tage
        elif feld == "naechster_termin":
            text = _text_oder_none(wert)
            if text is not None:
                try:
                    dt.date.fromisoformat(text)
                except ValueError:
                    raise EingabeFehler("Der nächste Termin ist kein gültiges Datum.") from None
            sauber[feld] = text
        else:
            sauber[feld] = _text_oder_none(wert)
    return sauber


# ------------------------------------------------------------------ Person

def anlegen(con: sqlite3.Connection, nutzer_id: int, name: str, **felder) -> int:
    """Legt eine Person an und gibt ihre Nummer zurueck."""
    werte = _felder_pruefen({"name": name, **felder})
    spalten = ", ".join(werte)
    marken = ", ".join("?" for _ in werte)
    zeile = con.execute(f"INSERT INTO person (nutzer_id, {spalten}) VALUES (?, {marken})",
                        (nutzer_id, *werte.values()))
    con.commit()
    return zeile.lastrowid


def laden(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> sqlite3.Row | None:
    """Die Person, oder `None` -- auch wenn sie einem anderen Nutzer gehoert."""
    return con.execute("SELECT * FROM person WHERE id = ? AND nutzer_id = ?",
                       (person_id, nutzer_id)).fetchone()


def _person(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> sqlite3.Row:
    zeile = laden(con, nutzer_id, person_id)
    if zeile is None:
        raise NichtGefunden(f"Person {person_id}")
    return zeile


def aendern(con: sqlite3.Connection, nutzer_id: int, person_id: int, **felder) -> None:
    """Setzt die genannten Felder; die anderen bleiben, wie sie sind."""
    _person(con, nutzer_id, person_id)
    werte = _felder_pruefen(felder)
    if not werte:
        return
    zuweisung = ", ".join(f"{spalte} = ?" for spalte in werte)
    con.execute(f"UPDATE person SET {zuweisung} WHERE id = ? AND nutzer_id = ?",
                (*werte.values(), person_id, nutzer_id))
    con.commit()


def archivieren(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> None:
    """Die Person geht ins Archiv; sie bleibt mit ihrer Geschichte da."""
    _person(con, nutzer_id, person_id)
    con.execute("UPDATE person SET archiviert_am = COALESCE(archiviert_am, ?) "
                "WHERE id = ? AND nutzer_id = ?",
                (_jetzt().strftime(_ZEITFORMAT), person_id, nutzer_id))
    con.commit()


def wiederherstellen(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> None:
    """Holt die Person aus dem Archiv zurueck."""
    _person(con, nutzer_id, person_id)
    con.execute("UPDATE person SET archiviert_am = NULL WHERE id = ? AND nutzer_id = ?",
                (person_id, nutzer_id))
    con.commit()


def liste(con: sqlite3.Connection, nutzer_id: int, *, tag_id: int | None = None,
          suche: str = "", ohne_kontakt: bool = False,
          archiviert: bool = False) -> list[sqlite3.Row]:
    """Personen nach Name, aufsteigend (Gross-/Kleinschreibung egal).

    `archiviert=False` zeigt das Aktive, `True` das Archiv. `suche` ist ein
    Teilstring ohne Beachtung der Gross-/Kleinschreibung (auch bei Umlauten)
    in Name, Firma, Ort und den Namen der Tags der Person.
    """
    zeilen = con.execute(
        "SELECT p.* FROM person p WHERE p.nutzer_id = ? "
        "AND (p.archiviert_am IS NOT NULL) = ? "
        "AND (? IS NULL OR EXISTS (SELECT 1 FROM person_tag pt WHERE pt.person_id = p.id "
        "                          AND pt.tag_id = ? AND pt.nutzer_id = p.nutzer_id)) "
        "AND (? = 0 OR NOT EXISTS (SELECT 1 FROM kontakt k WHERE k.person_id = p.id "
        "                          AND k.nutzer_id = p.nutzer_id))",
        (nutzer_id, int(archiviert), tag_id, tag_id, int(ohne_kontakt))).fetchall()
    begriff = suche.strip().casefold()
    if begriff:
        tagnamen = _tagnamen_je_person(con, nutzer_id)
        zeilen = [z for z in zeilen
                  if any(begriff in (wert or "").casefold()
                         for wert in (z["name"], z["firma"], z["ort"],
                                      *tagnamen.get(z["id"], ())))]
    return sorted(zeilen, key=lambda z: (z["name"].casefold(), z["id"]))


def _tagnamen_je_person(con: sqlite3.Connection, nutzer_id: int) -> dict[int, list[str]]:
    namen: dict[int, list[str]] = {}
    for zeile in con.execute(
            "SELECT pt.person_id, t.name FROM person_tag pt JOIN tag t ON t.id = pt.tag_id "
            "WHERE pt.nutzer_id = ? AND t.nutzer_id = ?", (nutzer_id, nutzer_id)):
        namen.setdefault(zeile["person_id"], []).append(zeile["name"])
    return namen


def zaehler(con: sqlite3.Connection, nutzer_id: int) -> dict[str, int]:
    """Die Zahlen der Seitenleiste: Alle, Noch kein Touchpoint, Archiv (ohne Tags)."""
    zeile = con.execute(
        "SELECT "
        " COALESCE(SUM(p.archiviert_am IS NULL), 0) AS alle, "
        " COALESCE(SUM(p.archiviert_am IS NULL AND NOT EXISTS ("
        "   SELECT 1 FROM kontakt k WHERE k.person_id = p.id AND k.nutzer_id = p.nutzer_id)), 0)"
        "   AS ohne_kontakt, "
        " COALESCE(SUM(p.archiviert_am IS NOT NULL), 0) AS archiv "
        "FROM person p WHERE p.nutzer_id = ?", (nutzer_id,)).fetchone()
    return dict(zeile)


# --------------------------------------------------------------------- Tags

def tag_name_pruefen(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise EingabeFehler("Der Tag braucht einen Namen.")
    return name


def tag_laden(con: sqlite3.Connection, nutzer_id: int, tag_id: int) -> sqlite3.Row | None:
    """Der Tag, oder `None` -- auch wenn er einem anderen Nutzer gehoert."""
    return con.execute("SELECT * FROM tag WHERE id = ? AND nutzer_id = ?",
                       (tag_id, nutzer_id)).fetchone()


def _tag(con: sqlite3.Connection, nutzer_id: int, tag_id: int) -> sqlite3.Row:
    zeile = tag_laden(con, nutzer_id, tag_id)
    if zeile is None:
        raise NichtGefunden(f"Tag {tag_id}")
    return zeile


def _tag_mit_namen(con: sqlite3.Connection, nutzer_id: int, name: str) -> sqlite3.Row | None:
    """Der Tag dieses Nutzers mit diesem Namen, Gross-/Kleinschreibung egal.

    `casefold` statt SQL: die NOCASE-Sortierung von SQLite kennt nur ASCII,
    „Ärzte“ und „ärzte“ waeren dort zwei Tags.
    """
    schluessel = name.casefold()
    for zeile in con.execute("SELECT * FROM tag WHERE nutzer_id = ?", (nutzer_id,)):
        if zeile["name"].casefold() == schluessel:
            return zeile
    return None


def tag_anlegen(con: sqlite3.Connection, nutzer_id: int, name: str) -> int:
    """Legt einen Tag an; den Namen gibt es je Nutzer nur einmal (Gross-/Kleinschreibung egal)."""
    name = tag_name_pruefen(name)
    if _tag_mit_namen(con, nutzer_id, name):
        raise EingabeFehler(f"Den Tag „{name}“ gibt es schon.")
    letzte = con.execute("SELECT COALESCE(MAX(reihenfolge), 0) FROM tag WHERE nutzer_id = ?",
                         (nutzer_id,)).fetchone()[0]
    zeile = con.execute("INSERT INTO tag (nutzer_id, name, reihenfolge) VALUES (?, ?, ?)",
                        (nutzer_id, name, letzte + 1))
    con.commit()
    return zeile.lastrowid


def tag_finden_oder_anlegen(con: sqlite3.Connection, nutzer_id: int, name: str) -> int:
    """Die Nummer des Tags mit diesem Namen; ihn gibt es noch nicht, wird er angelegt."""
    name = tag_name_pruefen(name)
    zeile = _tag_mit_namen(con, nutzer_id, name)
    return zeile["id"] if zeile else tag_anlegen(con, nutzer_id, name)


def tag_umbenennen(con: sqlite3.Connection, nutzer_id: int, tag_id: int, name: str) -> None:
    """Benennt den Tag um; ein anderer Tag mit demselben Namen verhindert das."""
    _tag(con, nutzer_id, tag_id)
    name = tag_name_pruefen(name)
    vorhanden = _tag_mit_namen(con, nutzer_id, name)
    if vorhanden and vorhanden["id"] != tag_id:
        raise EingabeFehler(f"Den Tag „{name}“ gibt es schon.")
    con.execute("UPDATE tag SET name = ? WHERE id = ? AND nutzer_id = ?",
                (name, tag_id, nutzer_id))
    con.commit()


def tag_loeschen(con: sqlite3.Connection, nutzer_id: int, tag_id: int) -> None:
    """Loescht den Tag. Die Personen bleiben; sie verlieren nur das Etikett."""
    _tag(con, nutzer_id, tag_id)
    con.execute("DELETE FROM person_tag WHERE tag_id = ? AND nutzer_id = ?",
                (tag_id, nutzer_id))
    con.execute("DELETE FROM tag WHERE id = ? AND nutzer_id = ?", (tag_id, nutzer_id))
    con.commit()


def tags_setzen(con: sqlite3.Connection, nutzer_id: int, person_id: int,
                tag_ids: list[int] | set[int]) -> None:
    """Die Person traegt genau diese Tags -- nicht mehr und nicht weniger."""
    _person(con, nutzer_id, person_id)
    gewollt = set(tag_ids)
    for tag_id in gewollt:
        _tag(con, nutzer_id, tag_id)
    con.execute("DELETE FROM person_tag WHERE person_id = ? AND nutzer_id = ?",
                (person_id, nutzer_id))
    con.executemany("INSERT INTO person_tag (nutzer_id, person_id, tag_id) VALUES (?, ?, ?)",
                    [(nutzer_id, person_id, tag_id) for tag_id in sorted(gewollt)])
    con.commit()


def tags_der_person(con: sqlite3.Connection, nutzer_id: int, person_id: int) -> set[int]:
    """Die Nummern der Tags dieser Person."""
    return {z["tag_id"] for z in con.execute(
        "SELECT tag_id FROM person_tag WHERE person_id = ? AND nutzer_id = ?",
        (person_id, nutzer_id))}


def tags_mit_zaehlern(con: sqlite3.Connection, nutzer_id: int) -> list[sqlite3.Row]:
    """Alle Tags des Nutzers in der Reihenfolge der Seitenleiste, mit `anzahl`.

    Gezaehlt werden die aktiven Personen: Archivierte stehen in keiner Liste.
    """
    return con.execute(
        "SELECT t.id, t.name, t.reihenfolge, COUNT(p.id) AS anzahl FROM tag t "
        "LEFT JOIN person_tag pt ON pt.tag_id = t.id AND pt.nutzer_id = t.nutzer_id "
        "LEFT JOIN person p ON p.id = pt.person_id AND p.nutzer_id = t.nutzer_id "
        "                  AND p.archiviert_am IS NULL "
        "WHERE t.nutzer_id = ? GROUP BY t.id "
        "ORDER BY t.reihenfolge, t.name COLLATE NOCASE, t.id", (nutzer_id,)).fetchall()


# ------------------------------------------------------- Mehrere hinzufuegen

def mehrere_hinzufuegen(con: sqlite3.Connection, nutzer_id: int, text: str, *,
                        tag_ids: list[int] | set[int] = (),
                        grober_kontakt: str = UNBEKANNT) -> list[int]:
    """Legt je Zeile eine Person an: `Name` oder `Name; Firma`.

    Leere Zeilen und Namen, die im Block schon vorkamen (Gross-/Kleinschreibung
    egal), werden uebersprungen. Alle bekommen dieselben Tags und -- ausser bei
    `unbekannt` -- einen Kontakt der Art `schaetzung` mit ungefaehrem Datum und
    ohne Notiz. Gibt die Nummern der angelegten Personen zurueck.
    """
    if grober_kontakt != UNBEKANNT and grober_kontakt not in GROBER_KONTAKT:
        raise EingabeFehler("Unbekannte Angabe zum letzten Touchpoint.")
    tags = set(tag_ids)
    for tag_id in tags:
        _tag(con, nutzer_id, tag_id)
    zeilen: list[tuple[str, str | None]] = []
    gesehen: set[str] = set()
    for rohzeile in text.splitlines():
        name, _, firma = rohzeile.partition(";")
        name = name.strip()
        if not name or name.casefold() in gesehen:
            continue
        gesehen.add(name.casefold())
        zeilen.append((name, firma.strip() or None))
    if not zeilen:
        raise EingabeFehler("Trag mindestens einen Namen ein, einen pro Zeile.")
    datum = None
    if grober_kontakt != UNBEKANNT:
        datum = (heute(con, nutzer_id)
                 - dt.timedelta(days=GROBER_KONTAKT[grober_kontakt])).isoformat()
    ids: list[int] = []
    try:
        for name, firma in zeilen:
            person_id = con.execute(
                "INSERT INTO person (nutzer_id, name, firma) VALUES (?, ?, ?)",
                (nutzer_id, name, firma)).lastrowid
            ids.append(person_id)
            con.executemany(
                "INSERT INTO person_tag (nutzer_id, person_id, tag_id) VALUES (?, ?, ?)",
                [(nutzer_id, person_id, tag_id) for tag_id in sorted(tags)])
            if datum:
                con.execute(
                    "INSERT INTO kontakt (nutzer_id, person_id, datum, art) "
                    "VALUES (?, ?, ?, 'schaetzung')", (nutzer_id, person_id, datum))
    except Exception:
        con.rollback()
        raise
    con.commit()
    return ids
