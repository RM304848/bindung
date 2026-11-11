"""Der Kalender: Stichtage und Faelligkeiten als `.ics`-Text (PLAN.md, Abschnitt 9).

Von Hand nach RFC 5545 geschrieben, ohne Bibliothek; die Teile sind klein und
einzeln pruefbar (`maskieren`, `falten`, `ereignis`). Kein Web hier: `web/routen/
kalender.py` liefert den Text aus und sucht den Nutzer zur Kalenderadresse.

Was im Kalender steht:

- Je Stichtag einer aktiven Person ein ganztaegiges, jaehrlich wiederkehrendes
  Ereignis. Der Beginn ist das gespeicherte Jahr, sonst das naechste Vorkommen.
  Der 29. Februar beginnt an einem 29. Februar; wie ein Kalender das Jahr ohne
  Schalttag behandelt, ueberlassen wir ihm (`BYMONTHDAY=-1` ist nicht portabel).
- Je Person mit Zustand ausser `unbekannt` ein ganztaegiges Ereignis „Melden
  bei ...“ am Tag `faellig_am`, mit einer Erinnerung um 9 Uhr morgens.
  Ueberfaellige und Erkaltete stehen nicht jeden Tag neu auf „heute“, sondern
  am naechsten Sonntag, dem Tag der Wochendurchsicht -- eine Erinnerung die
  Woche statt jeden Morgen.

Die UIDs sind je Stichtag und je Person fest, damit ein Kalender aktualisiert
statt zu verdoppeln, wenn sich der Tag verschiebt.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import secrets
import sqlite3

from bindung import faelligkeit, kontakte, personen, stichtage

PRODID = "-//Bindung//Kalender//DE"
#: Wie oft sich ein Abo neu holen soll (RFC 7986 und die weit verbreitete X-Variante).
AKTUALISIERUNG = "PT1H"
#: Die Erinnerung des Ereignisses „Melden bei“: Stunden nach Mitternacht des Tages.
ERINNERUNG = "PT9H"
#: Der Tag der Wochendurchsicht, auf den Ueberfaellige und Erkaltete fallen
#: (Montag = 0 ... Sonntag = 6).
DURCHSICHT_WOCHENTAG = 6

#: Laenger darf eine Zeile nicht sein, in Bytes ohne den Zeilenumbruch (RFC 5545, 3.1).
ZEILENLAENGE = 75

_STEUERZEICHEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ------------------------------------------------------------ kleine Bausteine

def maskieren(text: str) -> str:
    """Ein Textwert fuer eine Zeile: Backslash, Semikolon, Komma und Zeilenumbruch."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _STEUERZEICHEN.sub("", text)
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def falten(zeile: str) -> str:
    """Bricht eine Zeile nach 75 Bytes um (Folgezeilen beginnen mit einem Leerzeichen).

    Gebrochen wird nur zwischen zwei Zeichen, nie mitten in einem UTF-8-Zeichen.
    """
    roh = zeile.encode("utf-8")
    if len(roh) <= ZEILENLAENGE:
        return zeile
    teile = []
    start, platz = 0, ZEILENLAENGE
    while len(roh) - start > platz:
        ende = start + platz
        while roh[ende] & 0b1100_0000 == 0b1000_0000:  # Fortsetzungsbyte: ein Zeichen zurueck
            ende -= 1
        teile.append(roh[start:ende].decode("utf-8"))
        start, platz = ende, ZEILENLAENGE - 1  # das Leerzeichen der Folgezeile zaehlt mit
    teile.append(roh[start:].decode("utf-8"))
    return "\r\n ".join(teile)


def datum(tag: dt.date) -> str:
    """`20261111`."""
    return tag.strftime("%Y%m%d")


def zeitstempel(zeit: dt.datetime) -> str:
    """`20261111T120000Z` in UTC."""
    return zeit.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _jetzt() -> dt.datetime:
    """Die Uhr fuer DTSTAMP; Tests geben `jetzt` selbst mit."""
    return dt.datetime.now(dt.UTC)


def ereignis(uid: str, beginn: dt.date, zusammenfassung: str, stempel: dt.datetime, *,
             beschreibung: str | None = None, jaehrlich: bool = False,
             erinnerung: bool = False) -> list[str]:
    """Ein ganztaegiges VEVENT als Liste ungefalteter Zeilen.

    `jaehrlich` haengt `RRULE:FREQ=YEARLY` an, `erinnerung` einen VALARM um 9 Uhr
    des Tages. Das Ereignis haelt den Kalender nicht belegt (`TRANSPARENT`).
    """
    zeilen = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{zeitstempel(stempel)}",
        f"LAST-MODIFIED:{zeitstempel(stempel)}",
        f"DTSTART;VALUE=DATE:{datum(beginn)}",
        f"DTEND;VALUE=DATE:{datum(beginn + dt.timedelta(days=1))}",
    ]
    if jaehrlich:
        zeilen.append("RRULE:FREQ=YEARLY")
    zeilen.append(f"SUMMARY:{maskieren(zusammenfassung)}")
    if beschreibung:
        zeilen.append(f"DESCRIPTION:{maskieren(beschreibung)}")
    zeilen.append("TRANSP:TRANSPARENT")
    if erinnerung:
        # Eine Dauer nach Beginn des Tages statt einer Uhrzeit in UTC: sie gilt in der
        # Zeitzone, in der der Kalender gerade steht, und braucht keine Zeitzonenrechnung.
        zeilen += ["BEGIN:VALARM", "ACTION:DISPLAY",
                   f"DESCRIPTION:{maskieren(zusammenfassung)}",
                   f"TRIGGER:{ERINNERUNG}", "END:VALARM"]
    zeilen.append("END:VEVENT")
    return zeilen


def kalender(ereignisse: list[list[str]]) -> str:
    """Der ganze Kalender: Kopf, Ereignisse, CRLF nach jeder Zeile, Zeilen gefaltet."""
    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Bindung",
        f"REFRESH-INTERVAL;VALUE=DURATION:{AKTUALISIERUNG}",
        f"X-PUBLISHED-TTL:{AKTUALISIERUNG}",
    ]
    for einzeln in ereignisse:
        zeilen += einzeln
    zeilen.append("END:VCALENDAR")
    return "".join(falten(z) + "\r\n" for z in zeilen)


# ----------------------------------------------------------------- Stichtage

def erster_tag(stichtag_datum: str, heute: dt.date) -> dt.date:
    """Der Beginn der Reihe: das gespeicherte Jahr, sonst das naechste Vorkommen.

    Ein 29. Februar ohne Jahr beginnt am naechsten 29. Februar, der wirklich
    existiert -- am 28. Februar beginnend wuerde die Reihe nie auf den 29. fallen.
    """
    tag, monat, jahr = stichtage.teile(stichtag_datum)
    if jahr is not None:
        return dt.date(jahr, monat, tag)
    if (monat, tag) == (2, 29):
        for kandidat in range(heute.year, heute.year + 9):  # laengste Luecke: 8 Jahre (2096)
            if calendar.isleap(kandidat) and dt.date(kandidat, 2, 29) >= heute:
                return dt.date(kandidat, 2, 29)
    return stichtage.naechstes_vorkommen(stichtag_datum, heute)


def stichtag_titel(art: str, bezeichnung: str, person_name: str,
                   angehoeriger_id: int | None) -> str:
    """„Geburtstag Anna“, „Geburtstag Mia (Anna)“, „Anna: Firmenjubiläum“."""
    if angehoeriger_id is not None:
        return f"{bezeichnung} ({person_name})"
    if art == stichtage.ART_GEBURTSTAG and bezeichnung == stichtage.ARTEN[art]:
        return f"{bezeichnung} {person_name}"
    return f"{person_name}: {bezeichnung}"


def stichtag_beschreibung(art: str, stichtag_datum: str) -> str | None:
    """Das Jahr, wenn es bekannt ist -- als Tatsache, nicht als Alter.

    Ein Alter („wird 40“) stimmt nur fuer ein Vorkommen; die Beschreibung gilt aber
    fuer die ganze Reihe, und ein Kalender zeigt auch das uebernaechste Jahr.
    """
    jahr = stichtage.teile(stichtag_datum)[2]
    if jahr is None:
        return None
    return f"Geburtsjahr {jahr}" if art == stichtage.ART_GEBURTSTAG else f"Seit {jahr}"


def _stichtag_ereignisse(con: sqlite3.Connection, nutzer_id: int, heute: dt.date,
                         stempel: dt.datetime) -> list[list[str]]:
    zeilen = con.execute(
        "SELECT s.id, s.bezeichnung, s.art, s.datum, s.angehoeriger_id, p.name AS person_name "
        "FROM stichtag s JOIN person p ON p.id = s.person_id AND p.nutzer_id = s.nutzer_id "
        "WHERE s.nutzer_id = ? AND p.archiviert_am IS NULL ORDER BY s.id", (nutzer_id,))
    return [ereignis(
        f"stichtag-{z['id']}@bindung", erster_tag(z["datum"], heute),
        stichtag_titel(z["art"], z["bezeichnung"], z["person_name"], z["angehoeriger_id"]),
        stempel, beschreibung=stichtag_beschreibung(z["art"], z["datum"]), jaehrlich=True)
        for z in zeilen]


# ----------------------------------------------------------------- Melden bei

def naechste_durchsicht(heute: dt.date) -> dt.date:
    """Der naechste Tag der Wochendurchsicht, heute eingeschlossen."""
    return heute + dt.timedelta(days=(DURCHSICHT_WOCHENTAG - heute.weekday()) % 7)


def melden_tag(faellig_am: dt.date, heute: dt.date) -> dt.date:
    """Der Tag des Ereignisses: faellig_am; liegt der zurueck, die naechste Durchsicht.

    So wandert ein ueberfaelliger oder erkalteter Termin nicht jeden Tag auf
    „heute“ mit und klingelt jeden Morgen, sondern sammelt sich am Sonntag.
    """
    if faellig_am >= heute:
        return faellig_am
    return naechste_durchsicht(heute)


def _melden_ereignisse(con: sqlite3.Connection, nutzer_id: int, heute: dt.date,
                       stempel: dt.datetime) -> list[list[str]]:
    namen = {z["id"]: z["name"] for z in con.execute(
        "SELECT id, name FROM person WHERE nutzer_id = ? AND archiviert_am IS NULL", (nutzer_id,))}
    notizen = kontakte.letzte_notizen(con, nutzer_id)
    ergebnis = []
    for person_id, bindung in sorted(faelligkeit.bindungen(con, nutzer_id, heute).items()):
        if bindung.zustand == faelligkeit.UNBEKANNT or person_id not in namen:
            continue
        zeile = _erste_zeile(notizen.get(person_id))
        ergebnis.append(ereignis(
            f"melden-{person_id}@bindung", melden_tag(bindung.faellig_am, heute),
            f"Melden bei {namen[person_id]}", stempel,
            beschreibung=f"Zuletzt besprochen: {zeile}" if zeile else None, erinnerung=True))
    return ergebnis


def _erste_zeile(text: str | None) -> str:
    """Die erste nicht leere Zeile eines Freitexts."""
    for zeile in (text or "").splitlines():
        if zeile.strip():
            return zeile.strip()
    return ""


# ------------------------------------------------------------------ Zusammen

def kalender_text(con: sqlite3.Connection, nutzer_id: int, *, heute: dt.date | None = None,
                  jetzt: dt.datetime | None = None) -> str:
    """Der `.ics`-Text eines Nutzers. Nur seine Personen kommen vor."""
    heute = heute or personen.heute(con, nutzer_id)
    stempel = (jetzt or _jetzt()).replace(microsecond=0)
    return kalender(_stichtag_ereignisse(con, nutzer_id, heute, stempel)
                    + _melden_ereignisse(con, nutzer_id, heute, stempel))


# ---------------------------------------------------------- Kalenderadresse

def nutzer_zu_token(con: sqlite3.Connection, token: str) -> int | None:
    """Der Nutzer zur Kalenderadresse, oder `None`. Gleichheit in SQLite, kein Teilvergleich."""
    if not token:
        return None
    zeile = con.execute("SELECT id FROM nutzer WHERE kalender_token = ?", (token,)).fetchone()
    return zeile["id"] if zeile else None


def token_erneuern(con: sqlite3.Connection, nutzer_id: int) -> str:
    """Eine neue Kalenderadresse; die alte hoert damit auf zu gehen."""
    token = secrets.token_urlsafe(32)
    con.execute("UPDATE nutzer SET kalender_token = ? WHERE id = ?", (token, nutzer_id))
    con.commit()
    return token


def pfad(token: str) -> str:
    """Der Pfad der Kalenderadresse: `/kalender/<token>.ics`."""
    return f"/kalender/{token}.ics"
