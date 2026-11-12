"""Die Einstellungen eines Nutzers (PLAN.md, Abschnitt 4), ohne Web.

Gelesen und geschrieben wird nur die Zeile des angemeldeten Nutzers in `nutzer`.
Das Passwort und die Kalenderadresse haben ihre eigenen Funktionen
(`auth.passwort_aendern`, `kalender.token_erneuern`).

Abgelehnte Werte werfen `EingabeFehler`, deren Text fuer den Nutzer gedacht ist.
"""

from __future__ import annotations

import re
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bindung.personen import EingabeFehler

INTERVALL_VON, INTERVALL_BIS = 1, 3650
VORLAUF_VON, VORLAUF_BIS = 0, 365

#: Gaengige Zeitzonen, die Vorgabe zuerst. Mehr braucht ein Auswahlmenue nicht;
#: wer eine andere eingetragen hat, behaelt sie (siehe `zeitzonen`).
ZEITZONEN = (
    "Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/Amsterdam", "Europe/Brussels",
    "Europe/Paris", "Europe/Madrid", "Europe/Lisbon", "Europe/Rome", "Europe/Copenhagen",
    "Europe/Stockholm", "Europe/Oslo", "Europe/Helsinki", "Europe/Warsaw", "Europe/Prague",
    "Europe/Athens", "Europe/Istanbul", "Europe/London", "Europe/Dublin", "Europe/Moscow",
    "Africa/Cairo", "Africa/Johannesburg", "Asia/Dubai", "Asia/Kolkata", "Asia/Bangkok",
    "Asia/Singapore", "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul", "Australia/Sydney",
    "Pacific/Auckland", "America/New_York", "America/Toronto", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Mexico_City", "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires", "UTC",
)

#: Die Sprachen des Diktats mit ihrem Wort in der Oberflaeche.
DIKTAT_SPRACHEN = {"de-DE": "Deutsch", "en-US": "Englisch (USA)"}

#: Die Darstellung mit ihrem Wort in der Oberflaeche; `system` folgt dem Geraet.
DARSTELLUNGEN = {"system": "System", "hell": "Hell", "dunkel": "Dunkel"}

_UHRZEIT = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def lesen(con: sqlite3.Connection, nutzer_id: int) -> sqlite3.Row:
    """Die Einstellungen des Nutzers."""
    return con.execute(
        "SELECT id, name, tagesmeldung_zeit, zeitzone, vorgabe_intervall_tage, "
        "vorgabe_vorlauf_tage, diktat_sprache, darstellung, kalender_token "
        "FROM nutzer WHERE id = ?",
        (nutzer_id,)).fetchone()


def zeitzonen(aktuell: str) -> list[str]:
    """Die Auswahl; hat der Nutzer eine andere gespeichert, steht sie dabei."""
    return list(ZEITZONEN) if aktuell in ZEITZONEN else [aktuell, *ZEITZONEN]


def _ganzzahl(wert: object, name: str, von: int, bis: int) -> int:
    text = str(wert if wert is not None else "").strip()
    try:
        zahl = int(text)
    except ValueError:
        raise EingabeFehler(f"{name} ist eine ganze Zahl in Tagen.") from None
    if not von <= zahl <= bis:
        raise EingabeFehler(f"{name} liegt zwischen {von} und {bis} Tagen.")
    return zahl


def _zeitzone(wert: object, aktuell: str) -> str:
    text = str(wert or "").strip()
    if text not in ZEITZONEN and text != aktuell:
        raise EingabeFehler("Diese Zeitzone kenne ich nicht. Wähle eine aus der Liste.")
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise EingabeFehler("Diese Zeitzone kenne ich nicht. Wähle eine aus der Liste.") \
            from None
    return text


def _uhrzeit(wert: object) -> str:
    text = str(wert or "").strip()
    # Ein Zeitfeld liefert mancherorts „08:00:00“; die Sekunden sind belanglos.
    if re.fullmatch(r"\d{2}:\d{2}:00", text):
        text = text[:5]
    if not _UHRZEIT.match(text):
        raise EingabeFehler("Die Uhrzeit ist von der Form 08:00.")
    return text


def erinnern_speichern(con: sqlite3.Connection, nutzer_id: int, *, vorgabe_intervall_tage: object,
                       vorgabe_vorlauf_tage: object, zeitzone: object,
                       tagesmeldung_zeit: object) -> None:
    """Speichert die Vorgaben zum Erinnern -- alle oder keine."""
    intervall = _ganzzahl(vorgabe_intervall_tage, "Das Intervall", INTERVALL_VON, INTERVALL_BIS)
    vorlauf = _ganzzahl(vorgabe_vorlauf_tage, "Der Vorlauf", VORLAUF_VON, VORLAUF_BIS)
    zone = _zeitzone(zeitzone, lesen(con, nutzer_id)["zeitzone"])
    uhrzeit = _uhrzeit(tagesmeldung_zeit)
    con.execute("UPDATE nutzer SET vorgabe_intervall_tage = ?, vorgabe_vorlauf_tage = ?, "
                "zeitzone = ?, tagesmeldung_zeit = ? WHERE id = ?",
                (intervall, vorlauf, zone, uhrzeit, nutzer_id))
    con.commit()


def diktat_speichern(con: sqlite3.Connection, nutzer_id: int, sprache: object) -> None:
    """Speichert die Sprache des Diktats."""
    text = str(sprache or "").strip()
    if text not in DIKTAT_SPRACHEN:
        raise EingabeFehler("Wähle eine der Sprachen aus der Liste.")
    con.execute("UPDATE nutzer SET diktat_sprache = ? WHERE id = ?", (text, nutzer_id))
    con.commit()


def darstellung_speichern(con: sqlite3.Connection, nutzer_id: int, darstellung: object) -> str:
    """Speichert die Darstellung (`system`, `hell` oder `dunkel`) und gibt sie zurueck."""
    text = str(darstellung or "").strip()
    if text not in DARSTELLUNGEN:
        raise EingabeFehler("Wähle System, Hell oder Dunkel.")
    con.execute("UPDATE nutzer SET darstellung = ? WHERE id = ?", (text, nutzer_id))
    con.commit()
    return text
