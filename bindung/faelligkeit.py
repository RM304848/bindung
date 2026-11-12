"""Faelligkeit und Zustand einer Bindung (PLAN.md, Abschnitt 6).

Der Kern sind reine Funktionen ueber Daten und Zahlen -- kein Zugriff auf die
Datenbank, keine Uhr --, damit jede Grenze (genau das Intervall, genau das
Doppelte, genau 180 Tage) mit einer Zeile zu pruefen ist. Nur `bindungen`
liest die Datenbank, und zwar in einer Abfrage fuer alle Personen.

Abgeleitetes steht nie in der Datenbank: Faelligkeit und Zustand werden beim
Lesen gerechnet.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

# Die fuenf Zustaende; eine Bindung hat genau einen.
UNBEKANNT = "unbekannt"
OK = "ok"
BALD = "bald"
UEBERFAELLIG = "ueberfaellig"
ERKALTET = "erkaltet"

#: Bald = in den naechsten sieben Tagen faellig (Wochendurchsicht).
BALD_TAGE = 7
#: Erkaltet ab dem Doppelten des Intervalls, hoechstens aber nach 180 Tagen.
ERKALTET_FAKTOR = 2
ERKALTET_HOECHSTENS = 180

# Die drei Karten (PLAN.md, Abschnitt 6) in der Reihenfolge der Oberflaeche.
KARTE_AUFMERKSAMKEIT = "aufmerksamkeit"
KARTE_ERKALTET = "erkaltet"
KARTE_WOCHE = "woche"
KARTEN = (KARTE_AUFMERKSAMKEIT, KARTE_ERKALTET, KARTE_WOCHE)


# ------------------------------------------------------------ reine Regeln

def kaelte_grenze(intervall: int) -> int:
    """Nach so vielen Tagen ohne Kontakt ist eine Bindung erkaltet (davor: nicht)."""
    return min(ERKALTET_FAKTOR * intervall, ERKALTET_HOECHSTENS)


def faellig_am(letzter_kontakt: dt.date | None, intervall: int,
               naechster_termin: dt.date | None = None) -> dt.date | None:
    """Der Tag der Erinnerung: der naechste Termin, sonst letzter Kontakt plus Intervall.

    Ohne Kontakt und ohne naechsten Termin gibt es keinen Tag.
    """
    if naechster_termin is not None:
        return naechster_termin
    if letzter_kontakt is None:
        return None
    return letzter_kontakt + dt.timedelta(days=intervall)


def zustand(heute: dt.date, letzter_kontakt: dt.date | None, intervall: int,
            naechster_termin: dt.date | None = None) -> str:
    """Genau ein Zustand. Ohne Kontakt ist er unbekannt, auch mit naechstem Termin."""
    if letzter_kontakt is None:
        return UNBEKANNT
    if (heute - letzter_kontakt).days > kaelte_grenze(intervall):
        return ERKALTET
    faellig = faellig_am(letzter_kontakt, intervall, naechster_termin)
    if heute > faellig:
        return UEBERFAELLIG
    if faellig <= heute + dt.timedelta(days=BALD_TAGE):
        return BALD
    return OK


@dataclass(frozen=True)
class Bindung:
    """Alles Gerechnete zu einer Person an einem Tag."""

    person_id: int
    letzter_kontakt: dt.date | None
    intervall: int
    naechster_termin: dt.date | None
    faellig_am: dt.date | None
    zustand: str

    @property
    def erkaltet(self) -> bool:
        return self.zustand == ERKALTET


def bindung_rechnen(heute: dt.date, person_id: int, letzter_kontakt: dt.date | None,
                    intervall: int, naechster_termin: dt.date | None = None) -> Bindung:
    return Bindung(person_id, letzter_kontakt, intervall, naechster_termin,
                   faellig_am(letzter_kontakt, intervall, naechster_termin),
                   zustand(heute, letzter_kontakt, intervall, naechster_termin))


def sortierschluessel(bindung: Bindung, name: str) -> tuple:
    """Gefilterte Listen: erkaltet zuerst, dann nach Faelligkeit, dann nach Name."""
    return (not bindung.erkaltet, bindung.faellig_am or dt.date.max, name.casefold(),
            bindung.person_id)


# ----------------------------------------------------------------- Karten

def karten_nummern(bindungen: dict[int, Bindung],
                   stichtag_person_ids: frozenset[int] | set[int] = frozenset()
                   ) -> dict[str, set[int]]:
    """Wer auf welcher Karte steht.

    `stichtag_person_ids` sind die Personen mit einem Stichtag im Vorlauf; sie
    gehoeren auf die Karte „Diese Woche“, ohne ihren Zustand zu aendern. Die
    Stichtage selbst kommen mit WP3 (siehe `stichtage_im_vorlauf` in der
    Route) -- bis dahin ist die Menge leer.
    """
    aktiv = set(bindungen)
    return {
        KARTE_AUFMERKSAMKEIT: {i for i, b in bindungen.items()
                               if b.zustand in (UEBERFAELLIG, ERKALTET)},
        KARTE_ERKALTET: {i for i, b in bindungen.items() if b.zustand == ERKALTET},
        KARTE_WOCHE: {i for i, b in bindungen.items() if b.zustand == BALD}
                     | (set(stichtag_person_ids) & aktiv),
    }


# ------------------------------------------------------------ Abfrage

def _tag_oder_none(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def bindungen(con: sqlite3.Connection, nutzer_id: int, heute: dt.date, *,
              person_id: int | None = None) -> dict[int, Bindung]:
    """Die Bindungen aller aktiven Personen des Nutzers -- eine Abfrage.

    Mit `person_id` nur die dieser einen Person, archiviert oder nicht.
    """
    zeilen = con.execute(
        "SELECT p.id, p.intervall_tage, p.naechster_termin, n.vorgabe_intervall_tage, "
        " (SELECT MAX(k.datum) FROM kontakt k "
        "   WHERE k.person_id = p.id AND k.nutzer_id = p.nutzer_id) AS letzter "
        "FROM person p JOIN nutzer n ON n.id = p.nutzer_id "
        "WHERE p.nutzer_id = ? AND (p.id = ? OR (? IS NULL AND p.archiviert_am IS NULL))",
        (nutzer_id, person_id, person_id)).fetchall()
    return {z["id"]: bindung_rechnen(
        heute, z["id"], _tag_oder_none(z["letzter"]),
        z["intervall_tage"] or z["vorgabe_intervall_tage"], _tag_oder_none(z["naechster_termin"]))
        for z in zeilen}


# ------------------------------------------------------------ Worte

def vor_text(tage: int) -> str:
    """„heute“, „gestern“, „vor 5 Tagen“, „vor 3 Wochen“, „vor 4 Monaten“, „vor über einem Jahr“."""
    if tage <= 0:
        return "heute"
    if tage == 1:
        return "gestern"
    if tage < 14:
        return f"vor {tage} Tagen"
    if tage < 60:
        return f"vor {tage // 7} Wochen"
    if tage < 365:
        return f"vor {tage // 30} Monaten"
    return "vor über einem Jahr"


def in_text(tage: int) -> str:
    """„heute“, „morgen“, „in 4 Tagen“ -- fuer die Faelligkeit in der Zukunft."""
    if tage <= 0:
        return "heute"
    if tage == 1:
        return "morgen"
    return f"in {tage} Tagen"


def tage_text(tage: int) -> str:
    return "1 Tag" if tage == 1 else f"{tage} Tagen"


@dataclass(frozen=True)
class Plakette:
    """Das kleine Schild einer Person in der Liste: Text und Ton."""

    text: str
    ton: str  # unbekannt | ok | bald | ueberfaellig | erkaltet -- haengt am Stil


def plakette(bindung: Bindung, heute: dt.date) -> Plakette:
    """Was rechts in der Zeile steht (PLAN.md, Abschnitt 7)."""
    if bindung.zustand == UNBEKANNT:
        return Plakette("noch kein Touchpoint", UNBEKANNT)
    if bindung.zustand == ERKALTET:
        return Plakette("erkaltet", ERKALTET)
    if bindung.zustand == UEBERFAELLIG:
        tage = (heute - bindung.faellig_am).days
        return Plakette(f"überfällig seit {tage_text(tage)}", UEBERFAELLIG)
    if bindung.zustand == BALD:
        return Plakette(f"fällig {in_text((bindung.faellig_am - heute).days)}", BALD)
    return Plakette(vor_text((heute - bindung.letzter_kontakt).days), OK)


def zustand_text(zustand_: str) -> str:
    """Der Zustand als Wort fuer die Personenseite."""
    return {UNBEKANNT: "unbekannt", OK: "ok", BALD: "bald fällig",
            UEBERFAELLIG: "überfällig", ERKALTET: "erkaltet"}[zustand_]
