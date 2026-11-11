"""Die Tagesaufgabe: einmal am Tag die Tagesmeldung losschicken (PLAN.md, Abschnitt 10).

Im Prozess des Servers laeuft eine Schleife, die jede Minute `tick` aufruft. `tick`
ist eine gewoehnliche Funktion mit der Uhr als Parameter, damit jeder Test sie mit
festem Datum aufrufen kann; die Schleife tut nichts anderes als aufrufen.

Pro Nutzer gilt: ist seine Uhrzeit (in seiner Zeitzone) heute erreicht und steht in
`digest_protokoll.letzter_versand_am` nicht schon dieser Tag, dann wird die Tagesmeldung
gebaut und an alle seine Abos gesendet. Gibt es heute nichts zu sagen, wird der Tag
trotzdem eingetragen, damit nicht jede Minute neu gerechnet wird. Ein Tag, an dem der
Server aus war, wird nicht nachgeholt: `letzter_versand_am` ist der einzige Zustand.

Zwei Prozesse auf demselben Datenordner (zwei Instanzen, ein Neustart mitten im Tick)
senden nicht doppelt: den Tag einzutragen ist ein einziger bedingter Schreibzugriff
(`_beanspruchen`), und nur wer ihn gewinnt, sendet. Die Zeile der Datenbank ist das
Schloss -- eine Sperrdatei braeuchte einen zweiten Mechanismus mit eigenen Fehlern.
Beansprucht wird *vor* dem Senden: stuerzt der Prozess dazwischen ab, fehlt die
Meldung heute lieber, als dass sie doppelt kommt.

Nichts hier darf den Server mitreissen: jeder Nutzer wird einzeln abgesichert, die
Schleife faengt alles.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import os
import sqlite3
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bindung import db, push, tagesmeldung

log = logging.getLogger(__name__)

#: Wie oft die Schleife nachsieht.
INTERVALL_SEKUNDEN = 60
#: `BINDUNG_TAGESAUFGABE=0` schaltet die Schleife aus (Tests, eine zweite Instanz).
UMGEBUNG = "BINDUNG_TAGESAUFGABE"


@dataclass(frozen=True)
class Ergebnis:
    """Was `tick` fuer einen Nutzer getan hat."""

    nutzer_id: int
    tag: dt.date
    meldung: bool       # gab es heute etwas zu sagen?
    abos: int           # an wie viele Abos wurde gesendet?
    gesendet: int       # wie viele hat der Push-Dienst angenommen?


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("Europe/Berlin")


def _beanspruchen(con: sqlite3.Connection, nutzer_id: int, tag: dt.date) -> bool:
    """Traegt `tag` als Tag des Versands ein; `True`, wenn *dieser* Aufruf ihn bekommen hat."""
    zeile = con.execute(
        "INSERT INTO digest_protokoll (nutzer_id, letzter_versand_am) VALUES (?, ?) "
        "ON CONFLICT (nutzer_id) DO UPDATE SET letzter_versand_am = excluded.letzter_versand_am "
        "WHERE digest_protokoll.letzter_versand_am IS NOT excluded.letzter_versand_am",
        (nutzer_id, tag.isoformat()))
    con.commit()
    return zeile.rowcount == 1


def _nutzer_pruefen(con: sqlite3.Connection, nutzer: sqlite3.Row,
                    jetzt: dt.datetime) -> Ergebnis | None:
    lokal = jetzt.astimezone(_zone(nutzer["zeitzone"]))
    if lokal.strftime("%H:%M") < nutzer["tagesmeldung_zeit"]:
        return None
    heute = lokal.date()
    if not _beanspruchen(con, nutzer["id"], heute):
        return None
    abos = push.abos(con, nutzer["id"])
    if not abos:
        return Ergebnis(nutzer["id"], heute, False, 0, 0)
    meldung = tagesmeldung.bauen(con, nutzer["id"], heute)
    if meldung is None:
        return Ergebnis(nutzer["id"], heute, False, 0, 0)
    gesendet = sum(push.senden(con, abo, meldung.nutzlast) for abo in abos)
    return Ergebnis(nutzer["id"], heute, True, len(abos), gesendet)


def tick(con: sqlite3.Connection, jetzt: dt.datetime) -> list[Ergebnis]:
    """Ein Durchlauf fuer alle Nutzer; `jetzt` ist die Uhr (mit Zeitzone).

    Gibt zurueck, was fuer wen getan wurde; Nutzer, bei denen nichts anstand (Uhrzeit noch
    nicht erreicht, heute schon erledigt), fehlen in der Liste.
    """
    ergebnisse = []
    for nutzer in con.execute("SELECT id, zeitzone, tagesmeldung_zeit FROM nutzer ORDER BY id"
                              ).fetchall():
        try:
            ergebnis = _nutzer_pruefen(con, nutzer, jetzt)
        except Exception:
            log.exception("Tagesmeldung fuer Nutzer %s gescheitert", nutzer["id"])
            continue
        if ergebnis is not None:
            ergebnisse.append(ergebnis)
    return ergebnisse


# ------------------------------------------------------------------ Schleife

def _durchlauf() -> None:
    """Ein Tick mit eigener Verbindung -- im Arbeitsfaden, denn Senden wartet aufs Netz."""
    con = db.verbinden()
    try:
        tick(con, dt.datetime.now(dt.UTC))
    finally:
        con.close()


async def schleife() -> None:
    """Jede Minute ein Tick, bis die Aufgabe abgebrochen wird. Faellt nie wegen eines Fehlers."""
    while True:
        try:
            await asyncio.to_thread(_durchlauf)
        except Exception:
            log.exception("Die Tagesaufgabe hat einen Durchlauf verloren")
        await asyncio.sleep(INTERVALL_SEKUNDEN)


def aktiv() -> bool:
    return os.environ.get(UMGEBUNG, "1") != "0"


@contextlib.asynccontextmanager
async def laufen():
    """Startet die Schleife fuer die Dauer des `with`-Blocks (Lebensdauer der App)."""
    aufgabe = asyncio.create_task(schleife()) if aktiv() else None
    try:
        yield aufgabe
    finally:
        if aufgabe is not None:
            aufgabe.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await aufgabe
