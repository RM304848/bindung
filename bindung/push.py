"""Push: Schluessel, Abos und das Senden (PLAN.md, Abschnitt 10).

Der Server hat ein Schluesselpaar (VAPID), das er beim ersten Bedarf erzeugt und
im Datenordner ablegt (`pfade.VAPID_PATH`, Modus 0600). Der Browser bekommt den
oeffentlichen Teil und meldet sich damit beim Push-Dienst an; was dabei
herauskommt (Endpunkt, zwei Schluessel) speichert der Server als Abo des Nutzers.

Gesendet wird ueber `pywebpush.webpush`. Das ist der einzige Ort, an dem die App
etwas ins Netz schickt, und es traegt nur den Text der Tagesmeldung (CLAUDE.md,
Feste Rahmen). Ein Abo, das der Push-Dienst als tot meldet (404, 410), wird
geloescht; jeder andere Fehler wird geschrieben und das Abo bleibt.

Der Kontakt im Schluessel („sub“) ist `mailto:bindung@localhost`, solange
`BINDUNG_PUSH_KONTAKT` nicht gesetzt ist. Mancher Push-Dienst will eine echte
Adresse sehen; wer eine eintraegt, tut das bewusst und nur im Datenordner/Umfeld
des Servers, nie im Code.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import sqlite3
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

from bindung import pfade
from bindung.personen import EingabeFehler

log = logging.getLogger(__name__)

STANDARD_KONTAKT = "mailto:bindung@localhost"
#: So lange hebt der Push-Dienst eine Meldung auf, wenn der Browser aus ist. Eine
#: Tagesmeldung von gestern will niemand mehr sehen.
LEBENSDAUER_SEKUNDEN = 12 * 3600
#: Wie lange der Server auf den Push-Dienst wartet.
WARTEN_SEKUNDEN = 10

_MAX_ENDPUNKT = 2048
_MAX_SCHLUESSEL = 256
_BASE64URL = re.compile(r"^[A-Za-z0-9_\-]+={0,2}$")


# --------------------------------------------------------------- Schluessel

def _b64url(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode("ascii")


def _oeffentlich(vapid: Vapid02) -> str:
    """Der oeffentliche Schluessel in der Form, die der Browser verlangt (unkomprimierter Punkt)."""
    roh = vapid.public_key.public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    return _b64url(roh)


def _erzeugen() -> dict:
    vapid = Vapid02()
    vapid.generate_keys()
    return {"privat_pem": vapid.private_pem().decode("ascii"), "oeffentlich": _oeffentlich(vapid),
            "sub": STANDARD_KONTAKT}


def _lesen() -> dict | None:
    try:
        daten = json.loads(pfade.VAPID_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not all(isinstance(daten.get(feld), str) and daten[feld]
               for feld in ("privat_pem", "oeffentlich", "sub")):
        raise ValueError(f"Die Push-Schluessel in {pfade.VAPID_PATH} sind unvollstaendig.")
    return daten


def _ablegen(daten: dict) -> bool:
    """Schreibt die Schluessel, aber nur, wenn es die Datei noch nicht gibt.

    Zwei Prozesse, die gleichzeitig zum ersten Mal starten, schreiben nicht in
    dieselbe Datei: erst eine eigene, dann ein harter Link auf den Zielnamen, den
    das Dateisystem hoechstens einem von beiden gibt. Wer verliert, liest die
    Datei des Gewinners.
    """
    pfad = pfade.VAPID_PATH
    pfad.parent.mkdir(parents=True, exist_ok=True)
    zwischen = pfad.with_name(f"{pfad.name}.{secrets.token_hex(4)}.neu")
    fd = os.open(zwischen, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as datei:
            json.dump(daten, datei, indent=2)
        try:
            os.link(zwischen, pfad)
        except FileExistsError:
            return False
        return True
    finally:
        zwischen.unlink(missing_ok=True)


def schluessel() -> dict:
    """Das Schluesselpaar; beim ersten Aufruf erzeugt und abgelegt, danach gelesen."""
    daten = _lesen()
    if daten is None:
        _ablegen(_erzeugen())
        daten = _lesen()
    return daten


def oeffentlicher_schluessel() -> str:
    """Das, was der Browser zum Anmelden braucht (URL-sicheres Base64)."""
    return schluessel()["oeffentlich"]


def kontakt() -> str:
    """Der `sub` der Schluessel: `BINDUNG_PUSH_KONTAKT`, sonst der gespeicherte."""
    gesetzt = os.environ.get("BINDUNG_PUSH_KONTAKT", "").strip()
    return gesetzt or schluessel()["sub"]


# -------------------------------------------------------------------- Abos

def _pruefen_endpunkt(endpunkt: object) -> str:
    text = str(endpunkt or "").strip()
    teile = urlparse(text)
    host = (teile.hostname or "").lower()
    # Der Server schickt an diese Adresse: nur https, und nichts, das nach dem eigenen
    # Netz aussieht (Push-Dienste haben Namen, keine Zahlen).
    ist_zahl = bool(re.fullmatch(r"[0-9.]+|[0-9a-f:]+", host))
    if (not text or len(text) > _MAX_ENDPUNKT or teile.scheme != "https" or not host
            or ist_zahl or host == "localhost" or host.endswith((".localhost", ".local",
                                                                  ".internal"))):
        raise EingabeFehler("Dieser Push-Endpunkt ist nicht zulässig.")
    return text


def _pruefen_schluessel(wert: object, name: str) -> str:
    text = str(wert or "").strip()
    if not text or len(text) > _MAX_SCHLUESSEL or not _BASE64URL.match(text):
        raise EingabeFehler(f"Der Schlüssel {name} ist ungültig.")
    return text


def abo_speichern(con: sqlite3.Connection, nutzer_id: int, endpunkt: object,
                  p256dh: object, auth: object) -> None:
    """Merkt sich das Abo dieses Browsers; derselbe Endpunkt steht nie doppelt.

    Meldet sich ein Browser, der schon einem anderen Nutzer gehoerte, mit einem neuen
    Konto an (ein Rechner, zwei Leute), wechselt das Abo zum neuen Nutzer: sonst ginge
    dessen Tagesmeldung weiter an den Browser des anderen.
    """
    con.execute(
        "INSERT INTO push_abo (nutzer_id, endpunkt, schluessel_p256dh, schluessel_auth) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (endpunkt) DO UPDATE SET "
        "nutzer_id = excluded.nutzer_id, schluessel_p256dh = excluded.schluessel_p256dh, "
        "schluessel_auth = excluded.schluessel_auth",
        (nutzer_id, _pruefen_endpunkt(endpunkt), _pruefen_schluessel(p256dh, "p256dh"),
         _pruefen_schluessel(auth, "auth")))
    con.commit()


def abo_loeschen(con: sqlite3.Connection, nutzer_id: int, endpunkt: object) -> bool:
    """Loescht das Abo dieses Nutzers mit diesem Endpunkt; `False`, wenn es keines gab."""
    zeile = con.execute("DELETE FROM push_abo WHERE nutzer_id = ? AND endpunkt = ?",
                        (nutzer_id, str(endpunkt or "").strip()))
    con.commit()
    return zeile.rowcount > 0


def abos(con: sqlite3.Connection, nutzer_id: int) -> list[sqlite3.Row]:
    """Alle Abos des Nutzers, das aelteste zuerst."""
    return con.execute("SELECT * FROM push_abo WHERE nutzer_id = ? ORDER BY id",
                       (nutzer_id,)).fetchall()


def abos_zaehlen(con: sqlite3.Connection, nutzer_id: int) -> int:
    return con.execute("SELECT COUNT(*) FROM push_abo WHERE nutzer_id = ?",
                       (nutzer_id,)).fetchone()[0]


# ------------------------------------------------------------------ Senden

def senden(con: sqlite3.Connection, abo: sqlite3.Row, nutzlast: dict) -> bool:
    """Schickt die Nutzlast an ein Abo. `True`, wenn der Push-Dienst sie angenommen hat.

    404 und 410 heissen: dieses Abo gibt es nicht mehr -- es wird geloescht. Jeder
    andere Fehler (Netz, 5xx, Schluessel) wird geschrieben, das Abo bleibt: er kann
    morgen wieder gehen. Wirft nie.
    """
    try:
        webpush(
            subscription_info={"endpoint": abo["endpunkt"],
                               "keys": {"p256dh": abo["schluessel_p256dh"],
                                        "auth": abo["schluessel_auth"]}},
            data=json.dumps(nutzlast, ensure_ascii=False),
            vapid_private_key=Vapid02.from_pem(schluessel()["privat_pem"].encode("ascii")),
            vapid_claims={"sub": kontakt()},
            ttl=LEBENSDAUER_SEKUNDEN, timeout=WARTEN_SEKUNDEN)
    except WebPushException as fehler:
        antwort = getattr(fehler, "response", None)
        status = getattr(antwort, "status_code", None)
        if status in (404, 410):
            con.execute("DELETE FROM push_abo WHERE id = ?", (abo["id"],))
            con.commit()
            log.info("Push-Abo %s ist tot (%s) und wurde geloescht.", abo["id"], status)
        else:
            log.warning("Push an Abo %s fehlgeschlagen (%s): %s", abo["id"], status, fehler)
        return False
    except Exception as fehler:  # Netz, kaputter Schluessel: die Tagesaufgabe darf nie fallen
        log.warning("Push an Abo %s fehlgeschlagen: %s", abo["id"], fehler)
        return False
    return True
