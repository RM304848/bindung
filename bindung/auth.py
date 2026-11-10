"""Nutzer, Passwoerter und Sitzungen (PLAN.md, Abschnitt 4).

Kein Web hier: dieses Modul kennt weder FastAPI noch Cookies der Antwort,
sondern nur die Datenbank. `bindung/web/` ruft es auf, die CLI auch.

- Passwoerter: `hashlib.scrypt` mit eigenem Salz je Nutzer.
- Sitzung: ein zufaelliger Token im Cookie; in der Datenbank steht nur sein
  SHA-256. 30 Tage gueltig, bei jeder Benutzung erneuert.
- Fehlversuche: je Nutzername eine wachsende Wartezeit (1, 2, 4 ... bis
  300 Sekunden), im Speicher des Prozesses. Auch unbekannte Namen zaehlen,
  sonst verriete die Wartezeit, welche Namen es gibt.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import math
import os
import secrets
import sqlite3

#: Das Cookie der Sitzung.
COOKIE = "bindung_sitzung"
GUELTIG_TAGE = 30
GUELTIG_SEKUNDEN = GUELTIG_TAGE * 24 * 3600

MIN_LAENGE = 8

_N, _R, _P = 2**14, 8, 1
_ZEITFORMAT = "%Y-%m-%dT%H:%M:%SZ"


class AuthFehler(Exception):
    """Eine Eingabe, die abgelehnt wird; der Text ist fuer den Nutzer gedacht."""


class ZuVieleVersuche(AuthFehler):
    """Zu viele Fehlversuche: `sekunden` warten."""

    def __init__(self, sekunden: int) -> None:
        super().__init__(f"Zu viele Versuche. Bitte in {sekunden} Sekunden erneut versuchen.")
        self.sekunden = sekunden


def _jetzt() -> dt.datetime:
    """Die Uhr; Tests biegen sie um."""
    return dt.datetime.now(dt.UTC)


def _text(zeit: dt.datetime) -> str:
    return zeit.strftime(_ZEITFORMAT)


# ----------------------------------------------------------------- Passwort

def passwort_hashen(passwort: str) -> str:
    """`scrypt$n$r$p$salz$hash`, das Salz zufaellig je Aufruf."""
    salz = secrets.token_bytes(16)
    roh = hashlib.scrypt(passwort.encode(), salt=salz, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salz.hex()}${roh.hex()}"


def passwort_pruefen(passwort: str, gespeichert: str) -> bool:
    """Stimmt das Passwort mit dem gespeicherten Hash ueberein?"""
    try:
        verfahren, n, r, p, salz, roh = gespeichert.split("$")
        if verfahren != "scrypt":
            return False
        erwartet = bytes.fromhex(roh)
        berechnet = hashlib.scrypt(passwort.encode(), salt=bytes.fromhex(salz), n=int(n),
                                   r=int(r), p=int(p), dklen=len(erwartet))
    except ValueError:
        return False
    return hmac.compare_digest(berechnet, erwartet)


def _passwort_gueltig(passwort: str) -> None:
    if len(passwort) < MIN_LAENGE:
        raise AuthFehler(f"Das Passwort braucht mindestens {MIN_LAENGE} Zeichen.")


# ------------------------------------------------------------------- Nutzer

def nutzer_anlegen(con: sqlite3.Connection, name: str, passwort: str) -> int:
    """Legt einen Nutzer an und gibt seine Nummer zurueck."""
    name = name.strip()
    if not name:
        raise AuthFehler("Der Name darf nicht leer sein.")
    _passwort_gueltig(passwort)
    if con.execute("SELECT 1 FROM nutzer WHERE name = ?", (name,)).fetchone():
        raise AuthFehler(f"Den Nutzer „{name}“ gibt es schon.")
    zeile = con.execute(
        "INSERT INTO nutzer (name, passwort_hash, kalender_token) VALUES (?, ?, ?)",
        (name, passwort_hashen(passwort), secrets.token_urlsafe(32)))
    con.commit()
    return zeile.lastrowid


def passwort_setzen(con: sqlite3.Connection, name: str, passwort: str) -> None:
    """Setzt ein neues Passwort; alle Sitzungen des Nutzers enden."""
    _passwort_gueltig(passwort)
    zeile = con.execute("SELECT id FROM nutzer WHERE name = ?", (name.strip(),)).fetchone()
    if zeile is None:
        raise AuthFehler(f"Den Nutzer „{name}“ gibt es nicht.")
    con.execute("UPDATE nutzer SET passwort_hash = ? WHERE id = ?",
                (passwort_hashen(passwort), zeile["id"]))
    con.execute("DELETE FROM sitzung WHERE nutzer_id = ?", (zeile["id"],))
    con.commit()


def nutzer_liste(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Alle Nutzer, nach Name."""
    return con.execute("SELECT id, name, erstellt_am FROM nutzer ORDER BY name").fetchall()


# --------------------------------------------------------------- Fehlversuche

#: Name (klein) -> (Zahl der Fehlversuche, erst danach wieder erlaubt)
_fehlversuche: dict[str, tuple[int, dt.datetime]] = {}
_MAX_NAMEN = 1000
_MAX_WARTEN = 300


def _schluessel(name: str) -> str:
    return name.strip().casefold()


def wartezeit(name: str) -> int:
    """Wie viele Sekunden dieser Name noch gesperrt ist (0: frei)."""
    eintrag = _fehlversuche.get(_schluessel(name))
    if eintrag is None:
        return 0
    return max(0, math.ceil((eintrag[1] - _jetzt()).total_seconds()))


def _fehlversuch_merken(name: str) -> None:
    jetzt = _jetzt()
    if len(_fehlversuche) >= _MAX_NAMEN:
        for alt in [k for k, (_, bis) in _fehlversuche.items() if bis < jetzt]:
            del _fehlversuche[alt]
        if len(_fehlversuche) >= _MAX_NAMEN:
            _fehlversuche.clear()
    zahl = _fehlversuche.get(_schluessel(name), (0, jetzt))[0] + 1
    warten = min(2 ** (zahl - 1), _MAX_WARTEN)
    _fehlversuche[_schluessel(name)] = (zahl, jetzt + dt.timedelta(seconds=warten))


def fehlversuche_vergessen() -> None:
    """Fuer Tests: alle Zaehler loeschen."""
    _fehlversuche.clear()


# ------------------------------------------------------------------ Sitzung

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def anmelden(con: sqlite3.Connection, name: str, passwort: str) -> str | None:
    """Prueft Name und Passwort und gibt den Token einer neuen Sitzung zurueck.

    `None`, wenn Name oder Passwort nicht stimmen -- ohne zu sagen, welches.
    `ZuVieleVersuche`, solange der Name gesperrt ist (auch bei richtigem
    Passwort, sonst liesse sich die Sperre umgehen).
    """
    sekunden = wartezeit(name)
    if sekunden:
        raise ZuVieleVersuche(sekunden)
    zeile = con.execute("SELECT id, passwort_hash FROM nutzer WHERE name = ?",
                        (name.strip(),)).fetchone()
    # Auch bei unbekanntem Namen rechnen, damit die Antwortzeit nichts verraet.
    gespeichert = zeile["passwort_hash"] if zeile else _ATRAPPE
    stimmt = passwort_pruefen(passwort, gespeichert)
    if zeile is None or not stimmt:
        _fehlversuch_merken(name)
        return None
    _fehlversuche.pop(_schluessel(name), None)
    return sitzung_anlegen(con, zeile["id"])


_ATRAPPE = passwort_hashen(secrets.token_urlsafe(16))


def sitzung_anlegen(con: sqlite3.Connection, nutzer_id: int) -> str:
    """Eine neue Sitzung; gibt den Token fuers Cookie zurueck."""
    jetzt = _jetzt()
    con.execute("DELETE FROM sitzung WHERE laeuft_ab_am < ?", (_text(jetzt),))
    token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO sitzung (nutzer_id, token_hash, erstellt_am, laeuft_ab_am) "
        "VALUES (?, ?, ?, ?)",
        (nutzer_id, _token_hash(token), _text(jetzt),
         _text(jetzt + dt.timedelta(days=GUELTIG_TAGE))))
    con.commit()
    return token


def sitzung_pruefen(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """Der Nutzer zu diesem Token, oder `None`. Eine gueltige Sitzung wird erneuert."""
    if not token:
        return None
    jetzt = _jetzt()
    zeile = con.execute(
        "SELECT s.id AS sitzung_id, s.laeuft_ab_am, n.* FROM sitzung s "
        "JOIN nutzer n ON n.id = s.nutzer_id WHERE s.token_hash = ?",
        (_token_hash(token),)).fetchone()
    if zeile is None:
        return None
    if zeile["laeuft_ab_am"] < _text(jetzt):
        con.execute("DELETE FROM sitzung WHERE id = ?", (zeile["sitzung_id"],))
        con.commit()
        return None
    con.execute("UPDATE sitzung SET laeuft_ab_am = ? WHERE id = ?",
                (_text(jetzt + dt.timedelta(days=GUELTIG_TAGE)), zeile["sitzung_id"]))
    con.commit()
    return zeile


def abmelden(con: sqlite3.Connection, token: str | None) -> None:
    """Beendet die Sitzung zu diesem Token."""
    if token:
        con.execute("DELETE FROM sitzung WHERE token_hash = ?", (_token_hash(token),))
        con.commit()


# ------------------------------------------------------------------- Cookie

def cookie_sicher() -> bool:
    """`BINDUNG_SICHER=1`: ein TLS-Proxy steht davor, das Cookie wird `Secure`."""
    return os.environ.get("BINDUNG_SICHER") == "1"


def cookie_optionen() -> dict:
    """Die Attribute des Cookies, fuer `response.set_cookie(**...)`."""
    return {"max_age": GUELTIG_SEKUNDEN, "httponly": True, "samesite": "lax",
            "secure": cookie_sicher(), "path": "/"}
