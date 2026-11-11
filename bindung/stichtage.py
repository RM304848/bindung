"""Stichtage: jaehrlich wiederkehrende Tage an einer Person (PLAN.md, Abschnitte 5 bis 7).

Reine Funktionen auf einer `sqlite3.Connection`, ohne Web. Jede Funktion
bekommt die `nutzer_id` und filtert danach; eine Nummer, die einem anderen
Nutzer gehoert, ist fuer diese Funktionen nicht vorhanden (`NichtGefunden`).

Ein Datum steht als Text in der Tabelle: `YYYY-MM-DD` mit Jahr, `--MM-DD` ohne.
`naechstes_vorkommen` und `im_vorlauf` rechnen beim Lesen; abgeleitet wird nichts
gespeichert. Ein Stichtag aendert den Zustand der Person nicht (Abschnitt 6) --
er stellt sie nur auf die Karte „Diese Woche“ und gibt ihr eine zweite Plakette.

Der Geburtstag eines Angehoerigen ist ein Stichtag der Person, der an dessen
Eintrag haengt (`angehoeriger_id`). `angehoerige.py` pflegt ihn ueber
`geburtstag_abgleichen`; hier laesst er sich weder aendern noch loeschen.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import sqlite3
from dataclasses import dataclass

from bindung import faelligkeit, personen
from bindung.personen import EingabeFehler, NichtGefunden

#: Die Arten mit ihrem Wort in der Oberflaeche.
ARTEN = {"geburtstag": "Geburtstag", "jahrestag": "Jahrestag", "sonstiges": "Sonstiges"}
ART_GEBURTSTAG = "geburtstag"

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember")

FELDER = ("bezeichnung", "art", "datum", "vorlauf_tage")

#: Laenger als ein Jahr vorher hat keinen Sinn; die Grenze faengt Tippfehler ab.
VORLAUF_HOECHSTENS = 365
#: Aelter als das gibt es nicht in einer Familie, die jemand in die App tippt.
ERSTES_JAHR = 1900

_MIT_JAHR = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_OHNE_JAHR = re.compile(r"^--(\d{2})-(\d{2})$")
# Ein Schaltjahr als Massstab: der 29. Februar ist ohne Jahr ein gueltiger Tag.
_SCHALTJAHR = 2000


# ------------------------------------------------------------------ Datum

def teile(datum: str) -> tuple[int, int, int | None]:
    """(Tag, Monat, Jahr oder None) eines gespeicherten Datums."""
    treffer = _MIT_JAHR.match(datum)
    if treffer:
        return int(treffer[3]), int(treffer[2]), int(treffer[1])
    treffer = _OHNE_JAHR.match(datum)
    if treffer:
        return int(treffer[2]), int(treffer[1]), None
    raise ValueError(f"Kein Stichtag-Datum: {datum!r}")


def _zahl(text: object, name: str) -> int | None:
    roh = str(text if text is not None else "").strip()
    if not roh:
        return None
    try:
        return int(roh)
    except ValueError:
        raise EingabeFehler(f"{name} ist eine Zahl.") from None


def bauen(tag: object, monat: object, jahr: object = None,
          heute: dt.date | None = None) -> str:
    """Tag, Monat und optional Jahr als gespeichertes Datum; wirft `EingabeFehler`.

    Mit `heute` wird ein Jahr in der Zukunft abgelehnt (ein Geburtstag, der noch
    nicht war, ist kein Geburtstag).
    """
    t, m, j = _zahl(tag, "Der Tag"), _zahl(monat, "Der Monat"), _zahl(jahr, "Das Jahr")
    if t is None or m is None:
        raise EingabeFehler("Gib Tag und Monat an.")
    if j is not None:
        if j < ERSTES_JAHR:
            raise EingabeFehler(f"Das Jahr muss ab {ERSTES_JAHR} sein, oder du lässt es leer.")
        if heute is not None and j > heute.year:
            raise EingabeFehler("Das Jahr liegt in der Zukunft.")
    try:
        dt.date(j if j is not None else _SCHALTJAHR, m, t)
    except ValueError:
        raise EingabeFehler("Dieses Datum gibt es nicht.") from None
    return f"{j:04d}-{m:02d}-{t:02d}" if j is not None else f"--{m:02d}-{t:02d}"


def bauen_oder_none(tag: object, monat: object, jahr: object = None,
                    heute: dt.date | None = None) -> str | None:
    """Wie `bauen`, aber sind alle drei Felder leer, gibt es kein Datum (`None`)."""
    if not any(str(wert if wert is not None else "").strip() for wert in (tag, monat, jahr)):
        return None
    return bauen(tag, monat, jahr, heute)


def pruefen(text: object, heute: dt.date | None = None) -> str:
    """Ein Datum als Text (`YYYY-MM-DD` oder `--MM-DD`), geprueft; wirft `EingabeFehler`."""
    roh = str(text or "").strip()
    try:
        tag, monat, jahr = teile(roh)
    except ValueError:
        raise EingabeFehler("Das Datum ist ungültig.") from None
    return bauen(tag, monat, jahr, heute)


def text_de(datum: str | None) -> str:
    """„24. März“ oder „24. März 1986“."""
    if not datum:
        return ""
    tag, monat, jahr = teile(datum)
    text = f"{tag}. {MONATE[monat - 1]}"
    return f"{text} {jahr}" if jahr else text


def _im_jahr(tag: int, monat: int, jahr: int) -> dt.date:
    """Der Tag in diesem Jahr; der 29. Februar faellt im Gemeinjahr auf den 28."""
    if monat == 2 and tag == 29 and not calendar.isleap(jahr):
        return dt.date(jahr, 2, 28)
    return dt.date(jahr, monat, tag)


def naechstes_vorkommen(datum: str, heute: dt.date) -> dt.date:
    """Der naechste Tag am oder nach `heute`, an dem sich der Stichtag jaehrt."""
    tag, monat, _ = teile(datum)
    for jahr in (heute.year, heute.year + 1):
        kandidat = _im_jahr(tag, monat, jahr)
        if kandidat >= heute:
            return kandidat
    raise AssertionError("unerreichbar: das naechste Jahr liegt immer nach heute")


# ------------------------------------------------------------- Vorkommen

def jahre_text(art: str, jahre: int | None) -> str:
    """„wird 40“ beim Geburtstag, „10 Jahre“ sonst; ohne Jahr (oder noch kein Jahr) leer."""
    if jahre is None or jahre < 1:
        return ""
    if art == ART_GEBURTSTAG:
        return f"wird {jahre}"
    return "1 Jahr" if jahre == 1 else f"{jahre} Jahre"


@dataclass(frozen=True)
class Vorkommen:
    """Ein Stichtag, von `heute` aus gesehen: wann er das naechste Mal ist und wie alt."""

    id: int
    person_id: int
    person_name: str
    bezeichnung: str
    art: str
    datum: str
    vorlauf_eigen: int | None
    vorlauf: int
    angehoeriger_id: int | None
    tag: dt.date
    tage: int
    jahre: int | None

    @property
    def im_vorlauf(self) -> bool:
        return self.tage <= self.vorlauf

    @property
    def jahre_text(self) -> str:
        return jahre_text(self.art, self.jahre)

    @property
    def tage_text(self) -> str:
        """„heute“, „morgen“, „in 4 Tagen“."""
        return faelligkeit.in_text(self.tage)

    @property
    def plakette_text(self) -> str:
        """Die zweite Plakette in der Zeile: „Geburtstag in 4 Tagen“, „Jahrestag heute“.

        Beim Geburtstag eines Angehoerigen steht dessen Name dabei, sonst wuesste
        man nicht, wessen Tag es ist; ein benannter Tag traegt seinen Namen.
        """
        if self.angehoeriger_id is not None or self.art == "sonstiges":
            wort = self.bezeichnung
        else:
            wort = ARTEN[self.art]
        return f"{wort} {self.tage_text}"


def _vorkommen(zeile: sqlite3.Row, heute: dt.date, vorgabe: int) -> Vorkommen:
    tag = naechstes_vorkommen(zeile["datum"], heute)
    jahr = teile(zeile["datum"])[2]
    return Vorkommen(
        id=zeile["id"], person_id=zeile["person_id"], person_name=zeile["person_name"],
        bezeichnung=zeile["bezeichnung"], art=zeile["art"], datum=zeile["datum"],
        vorlauf_eigen=zeile["vorlauf_tage"],
        vorlauf=zeile["vorlauf_tage"] if zeile["vorlauf_tage"] is not None else vorgabe,
        angehoeriger_id=zeile["angehoeriger_id"], tag=tag, tage=(tag - heute).days,
        jahre=tag.year - jahr if jahr else None)


_ABFRAGE = ("SELECT s.*, p.name AS person_name, n.vorgabe_vorlauf_tage AS vorgabe "
            "FROM stichtag s "
            "JOIN person p ON p.id = s.person_id AND p.nutzer_id = s.nutzer_id "
            "JOIN nutzer n ON n.id = s.nutzer_id ")


def _sortiert(vorkommen: list[Vorkommen]) -> list[Vorkommen]:
    return sorted(vorkommen, key=lambda v: (v.tage, v.bezeichnung.casefold(), v.id))


def liste(con: sqlite3.Connection, nutzer_id: int, person_id: int,
          heute: dt.date | None = None) -> list[Vorkommen]:
    """Die Stichtage der Person, der naechste zuerst."""
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    heute = heute or personen.heute(con, nutzer_id)
    zeilen = con.execute(_ABFRAGE + "WHERE s.nutzer_id = ? AND s.person_id = ?",
                         (nutzer_id, person_id)).fetchall()
    return _sortiert([_vorkommen(z, heute, z["vorgabe"]) for z in zeilen])


def im_vorlauf(con: sqlite3.Connection, nutzer_id: int,
               heute: dt.date | None = None) -> list[Vorkommen]:
    """Alle Stichtage aktiver Personen, die gerade im Vorlauf liegen, der naechste zuerst.

    Im Vorlauf heisst: das naechste Vorkommen ist heute oder liegt hoechstens
    `vorlauf_tage` Tage voraus -- die des Stichtags, sonst die Vorgabe des Nutzers.
    """
    heute = heute or personen.heute(con, nutzer_id)
    zeilen = con.execute(_ABFRAGE + "WHERE s.nutzer_id = ? AND p.archiviert_am IS NULL",
                         (nutzer_id,)).fetchall()
    return _sortiert([v for v in (_vorkommen(z, heute, z["vorgabe"]) for z in zeilen)
                      if v.im_vorlauf])


def je_person(vorkommen: list[Vorkommen]) -> dict[int, Vorkommen]:
    """Je Person der naechste Stichtag aus einer sortierten Liste (fuer die Plakette)."""
    ergebnis: dict[int, Vorkommen] = {}
    for v in vorkommen:
        ergebnis.setdefault(v.person_id, v)
    return ergebnis


# ---------------------------------------------------------------- Eingaben

def _bezeichnung(wert: object, art: str) -> str:
    text = str(wert or "").strip()
    if text:
        return text
    if art == "sonstiges":
        raise EingabeFehler("Gib dem Stichtag einen Namen.")
    return ARTEN[art]


def _art(wert: object) -> str:
    art = str(wert or "").strip()
    if art not in ARTEN:
        raise EingabeFehler("Wähle aus, was für ein Stichtag es ist.")
    return art


def _vorlauf(wert: object) -> int | None:
    text = str(wert if wert is not None else "").strip()
    if not text:
        return None
    try:
        tage = int(text)
    except ValueError:
        raise EingabeFehler("Der Vorlauf ist eine Zahl in Tagen.") from None
    if not 0 <= tage <= VORLAUF_HOECHSTENS:
        raise EingabeFehler(f"Der Vorlauf liegt zwischen 0 und {VORLAUF_HOECHSTENS} Tagen.")
    return tage


# ------------------------------------------------------------------ Zugriff

def laden(con: sqlite3.Connection, nutzer_id: int, stichtag_id: int) -> sqlite3.Row | None:
    """Der Stichtag, oder `None` -- auch wenn er einem anderen Nutzer gehoert."""
    return con.execute("SELECT * FROM stichtag WHERE id = ? AND nutzer_id = ?",
                       (stichtag_id, nutzer_id)).fetchone()


def vorkommen_von(con: sqlite3.Connection, nutzer_id: int, stichtag_id: int,
                  heute: dt.date | None = None) -> Vorkommen:
    """Der eine Stichtag mit allem Gerechneten; fremd oder unbekannt ist `NichtGefunden`."""
    zeile = con.execute(_ABFRAGE + "WHERE s.id = ? AND s.nutzer_id = ?",
                        (stichtag_id, nutzer_id)).fetchone()
    if zeile is None:
        raise NichtGefunden(f"Stichtag {stichtag_id}")
    return _vorkommen(zeile, heute or personen.heute(con, nutzer_id), zeile["vorgabe"])


def _eigener(con: sqlite3.Connection, nutzer_id: int, stichtag_id: int) -> sqlite3.Row:
    """Der Stichtag zum Aendern: nicht fremd, und keiner, der an einem Angehoerigen haengt."""
    zeile = laden(con, nutzer_id, stichtag_id)
    if zeile is None:
        raise NichtGefunden(f"Stichtag {stichtag_id}")
    if zeile["angehoeriger_id"] is not None:
        raise EingabeFehler("Dieser Geburtstag gehört zu einem Angehörigen. "
                            "Ändere ihn dort.")
    return zeile


def anlegen(con: sqlite3.Connection, nutzer_id: int, person_id: int, *, bezeichnung: object,
            art: object, datum: object, vorlauf_tage: object = None) -> int:
    """Legt einen Stichtag an und gibt seine Nummer zurueck."""
    if personen.laden(con, nutzer_id, person_id) is None:
        raise NichtGefunden(f"Person {person_id}")
    art = _art(art)
    name = _bezeichnung(bezeichnung, art)
    tag = pruefen(datum, personen.heute(con, nutzer_id))
    vorlauf = _vorlauf(vorlauf_tage)
    zeile = con.execute(
        "INSERT INTO stichtag (nutzer_id, person_id, bezeichnung, art, datum, vorlauf_tage) "
        "VALUES (?, ?, ?, ?, ?, ?)", (nutzer_id, person_id, name, art, tag, vorlauf))
    con.commit()
    return zeile.lastrowid


def aendern(con: sqlite3.Connection, nutzer_id: int, stichtag_id: int, **felder) -> None:
    """Setzt die genannten Felder; die anderen bleiben, wie sie sind."""
    unbekannt = set(felder) - set(FELDER)
    if unbekannt:
        raise ValueError(f"Unbekannte Felder: {sorted(unbekannt)}")
    alt = _eigener(con, nutzer_id, stichtag_id)
    art = _art(felder["art"]) if "art" in felder else alt["art"]
    werte: dict[str, object] = {}
    if "art" in felder:
        werte["art"] = art
    if "bezeichnung" in felder:
        werte["bezeichnung"] = _bezeichnung(felder["bezeichnung"], art)
    if "datum" in felder:
        werte["datum"] = pruefen(felder["datum"], personen.heute(con, nutzer_id))
    if "vorlauf_tage" in felder:
        werte["vorlauf_tage"] = _vorlauf(felder["vorlauf_tage"])
    if not werte:
        return
    zuweisung = ", ".join(f"{spalte} = ?" for spalte in werte)
    con.execute(f"UPDATE stichtag SET {zuweisung} WHERE id = ? AND nutzer_id = ?",
                (*werte.values(), stichtag_id, nutzer_id))
    con.commit()


def loeschen(con: sqlite3.Connection, nutzer_id: int, stichtag_id: int) -> int:
    """Loescht den Stichtag und gibt die Nummer seiner Person zurueck."""
    person_id = _eigener(con, nutzer_id, stichtag_id)["person_id"]
    con.execute("DELETE FROM stichtag WHERE id = ? AND nutzer_id = ?", (stichtag_id, nutzer_id))
    con.commit()
    return person_id


# ------------------------------------------------- Geburtstag eines Angehoerigen

def geburtstag_abgleichen(con: sqlite3.Connection, nutzer_id: int,
                          angehoeriger: sqlite3.Row) -> None:
    """Haelt den Stichtag zum Geburtstag eines Angehoerigen in Einklang mit dessen Eintrag.

    Ohne Geburtstag gibt es keinen Stichtag; sonst genau einen mit der
    Bezeichnung „Geburtstag <Name>“. Schreibt nur -- der Aufrufer committet, damit
    Eintrag und Stichtag zusammen gelten oder zusammen nicht.
    """
    vorhanden = con.execute(
        "SELECT id FROM stichtag WHERE angehoeriger_id = ? AND nutzer_id = ?",
        (angehoeriger["id"], nutzer_id)).fetchone()
    if not angehoeriger["geburtstag"]:
        if vorhanden:
            con.execute("DELETE FROM stichtag WHERE id = ?", (vorhanden["id"],))
        return
    bezeichnung = f"Geburtstag {angehoeriger['name']}"
    if vorhanden:
        con.execute("UPDATE stichtag SET bezeichnung = ?, datum = ? WHERE id = ?",
                    (bezeichnung, angehoeriger["geburtstag"], vorhanden["id"]))
    else:
        con.execute(
            "INSERT INTO stichtag (nutzer_id, person_id, bezeichnung, art, datum, "
            "angehoeriger_id) VALUES (?, ?, ?, 'geburtstag', ?, ?)",
            (nutzer_id, angehoeriger["person_id"], bezeichnung, angehoeriger["geburtstag"],
             angehoeriger["id"]))
