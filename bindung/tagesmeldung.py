"""Die Tagesmeldung: was heute zu sagen ist (PLAN.md, Abschnitt 10).

Reine Regeln ueber Daten und einen Tag, ohne Uhr und ohne Netz: `bauen` liest die
Datenbank und gibt entweder die Meldung zurueck oder `None`. Wohin sie geht (Push
oder Hinweis in der App) entscheidet der Aufrufer; Titel und Text sind fuer beide
dieselben.

Was dazugehoert:

- Personen, die heute warten: ueberfaellig oder erkaltet, dazu die, die heute
  faellig werden (Zustand bald mit `faellig_am == heute`). Wer erst in drei Tagen
  faellig ist, ist eine Sache der Wochendurchsicht, keine der Tagesmeldung.
- Stichtage, die heute sind oder in ihrem Vorlauf liegen.

Ist nichts davon da, gibt es keine Tagesmeldung. Aus dem Text wird nichts
gerechnet; er ist Anzeige.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from bindung import faelligkeit, kalender, stichtage

TITEL = "Bindung"
#: Das Symbol der Meldung (der Service Worker zeigt es neben dem Text); liegt in `statisch/`.
SYMBOL = "/statisch/symbol-192.png"
#: Wie viele Namen im Text stehen; der Rest wird „…“.
NAMEN_HOECHSTENS = 3

URL_AUFMERKSAMKEIT = "/?karte=aufmerksamkeit"
URL_WOCHE = "/?karte=woche"

# Die Woerter der Stichtagsarten in der Zaehlzeile: (Einzahl, Mehrzahl).
_ARTWORTE = {"geburtstag": ("Geburtstag", "Geburtstage"),
             "jahrestag": ("Jahrestag", "Jahrestage"),
             "sonstiges": ("Stichtag", "Stichtage")}


@dataclass(frozen=True)
class Tagesmeldung:
    """Titel, Text und Ziel der Meldung -- und die Zahlen dahinter."""

    titel: str
    zaehlzeile: str
    namenzeile: str
    stichtagzeile: str
    url: str
    wartende: int
    stichtage: int

    @property
    def zeilen(self) -> list[str]:
        return [z for z in (self.zaehlzeile, self.namenzeile, self.stichtagzeile) if z]

    @property
    def text(self) -> str:
        """Der Text der Push-Nachricht: eine Zeile je Auskunft."""
        return "\n".join(self.zeilen)

    @property
    def nutzlast(self) -> dict:
        """Was der Service Worker bekommt. `tag` laesst eine neue Meldung die alte ersetzen."""
        return {"titel": self.titel, "text": self.text, "url": self.url, "tag": "tagesmeldung",
                "icon": SYMBOL}


# ------------------------------------------------------------------ Worte

def personen_text(zahl: int) -> str:
    return "1 Person wartet" if zahl == 1 else f"{zahl} Personen warten"


def stichtage_text(vorkommen: list[stichtage.Vorkommen]) -> str:
    """„1 Geburtstag“, „2 Geburtstage · 1 Jahrestag“ -- je Art, in fester Reihenfolge."""
    teile = []
    for art, (einzahl, mehrzahl) in _ARTWORTE.items():
        zahl = sum(1 for v in vorkommen if v.art == art)
        if zahl:
            teile.append(f"{zahl} {einzahl if zahl == 1 else mehrzahl}")
    return " · ".join(teile)


def namen_text(namen: list[str]) -> str:
    """Bis zu drei Namen, bei mehr mit „ …“: „Anna Beispiel, Ben Muster, Clara Probe …“."""
    text = ", ".join(namen[:NAMEN_HOECHSTENS])
    return f"{text} …" if len(namen) > NAMEN_HOECHSTENS else text


def stichtag_text(v: stichtage.Vorkommen) -> str:
    """„Geburtstag Mia Beispiel in 3 Tagen“ -- dieselben Worte wie der Titel im Kalender."""
    titel = kalender.stichtag_titel(v.art, v.bezeichnung, v.person_name, v.angehoeriger_id)
    return f"{titel} {v.tage_text}"


# ------------------------------------------------------------------ Inhalt

def _wartende(con: sqlite3.Connection, nutzer_id: int, heute: dt.date) -> list[str]:
    """Die Namen der Wartenden, erkaltete zuerst, dann nach Faelligkeit, dann nach Name."""
    bindungen = faelligkeit.bindungen(con, nutzer_id, heute)
    wartend = {i: b for i, b in bindungen.items()
               if b.zustand in (faelligkeit.UEBERFAELLIG, faelligkeit.ERKALTET)
               or (b.zustand == faelligkeit.BALD and b.faellig_am == heute)}
    if not wartend:
        return []
    namen = {z["id"]: z["name"] for z in con.execute(
        "SELECT id, name FROM person WHERE nutzer_id = ? AND archiviert_am IS NULL",
        (nutzer_id,))}
    return [namen[i] for i in sorted(
        wartend, key=lambda i: faelligkeit.sortierschluessel(wartend[i], namen[i]))]


def bauen(con: sqlite3.Connection, nutzer_id: int, heute: dt.date) -> Tagesmeldung | None:
    """Die Tagesmeldung des Nutzers fuer `heute`, oder `None`, wenn nichts zu sagen ist."""
    namen = _wartende(con, nutzer_id, heute)
    vorkommen = stichtage.im_vorlauf(con, nutzer_id, heute)
    if not namen and not vorkommen:
        return None
    zaehlung = [t for t in (personen_text(len(namen)) if namen else "",
                            stichtage_text(vorkommen)) if t]
    return Tagesmeldung(
        titel=TITEL, zaehlzeile=" · ".join(zaehlung), namenzeile=namen_text(namen),
        stichtagzeile=stichtag_text(vorkommen[0]) if vorkommen else "",
        url=URL_AUFMERKSAMKEIT if namen else URL_WOCHE,
        wartende=len(namen), stichtage=len(vorkommen))


# ------------------------------------------------------------------ Hinweis

def hinweis_weggeklickt(con: sqlite3.Connection, nutzer_id: int, heute: dt.date) -> bool:
    """Hat der Nutzer den Hinweis heute schon weggeklickt?"""
    zeile = con.execute("SELECT hinweis_weggeklickt_am FROM digest_protokoll WHERE nutzer_id = ?",
                        (nutzer_id,)).fetchone()
    return bool(zeile and zeile["hinweis_weggeklickt_am"] == heute.isoformat())


def hinweis_wegklicken(con: sqlite3.Connection, nutzer_id: int, heute: dt.date) -> None:
    """Merkt sich, dass der Hinweis heute weg ist. Der Versandtag bleibt, wie er ist."""
    con.execute(
        "INSERT INTO digest_protokoll (nutzer_id, hinweis_weggeklickt_am) VALUES (?, ?) "
        "ON CONFLICT (nutzer_id) DO UPDATE SET "
        "hinweis_weggeklickt_am = excluded.hinweis_weggeklickt_am",
        (nutzer_id, heute.isoformat()))
    con.commit()


def hinweis(con: sqlite3.Connection, nutzer_id: int, heute: dt.date) -> Tagesmeldung | None:
    """Die Tagesmeldung als Hinweis: nur, wenn es eine gibt und sie heute nicht weg ist."""
    if hinweis_weggeklickt(con, nutzer_id, heute):
        return None
    return bauen(con, nutzer_id, heute)
