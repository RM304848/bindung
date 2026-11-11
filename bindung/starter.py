"""Die App zum Doppelklicken: Server starten, Browser oeffnen, fertig.

Was `bindung serve` fuer jemanden mit Terminal ist, ist das hier fuer die App aus der
.dmg (werkzeuge/paket/). Es laeuft genauso als `bindung app`.

WAS ER ANDERS MACHT ALS `serve` (wie der Starter von Health OS):

* Er bindet immer an 127.0.0.1 und laedt nicht neu: die App aendert ihren Code nicht.
* Er laeuft auf einem eigenen Port (8788), nicht auf 8785: wer daneben `bindung serve`
  benutzt, soll nicht zwei Programme auf einer Adresse haben. Antwortet dort schon Bindung,
  wird nur der Browser geoeffnet -- ein zweiter Doppelklick startet keinen zweiten Server.
  Antwortet dort etwas anderes, nimmt er einen freien Port.
* Er laesst sich aus der App beenden (Knopf "Beenden" in der Seitenleiste): auf dem Mac hat
  die App kein Fenster und kein Dock-Symbol, das man schliessen koennte. Dafuer steht sie
  in der Menueleiste (`menueleiste.py`): oeffnen, Datenordner zeigen, beenden.
  `BINDUNG_KEINE_MENUELEISTE=1` laesst das Symbol weg.
* Die Tagesaufgabe (Tagesmeldung per Push) laeuft in diesem Prozess: er ist der, der immer
  an ist. Laeuft schon ein `bindung serve` mit demselben Datenordner, laesst der Starter sie
  weg, damit nicht zwei Schleifen denselben Tag beanspruchen (PLAN.md, Abschnitt 13).

Die Datenbank legt `db.verbinden` beim ersten Zugriff selbst an. Den ersten Nutzer legt die
App beim ersten Start selbst an (Seite `/einrichten`, nur hier).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
import webbrowser

from bindung import menueleiste, pfade, tagesaufgabe

PORT = 8788
HOST = "127.0.0.1"
#: Wo `bindung serve` ohne Angabe lauscht.
SERVE_PORT = 8785


def lebenszeichen(port: int) -> dict | None:
    """Die Antwort von `/healthz`, wenn dort Bindung antwortet, sonst `None`."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/healthz", timeout=2) as antwort:
            daten = json.loads(antwort.read(4096).decode("utf-8", "replace"))
    except (OSError, ValueError):
        return None
    return daten if isinstance(daten, dict) and daten.get("app") == "Bindung" else None


def _antwortet_bindung(port: int) -> bool:
    return lebenszeichen(port) is not None


def _frei(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Wie uvicorn: nach einem Beenden haengt der Port noch in TIME_WAIT.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def _freier_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def port_waehlen(wunsch: int = PORT) -> tuple[int, bool]:
    """(Port, laeuft schon). Laeuft schon: nur den Browser oeffnen."""
    if _frei(wunsch):
        return wunsch, False
    if _antwortet_bindung(wunsch):
        return wunsch, True
    return _freier_port(), False


def serve_teilt_die_daten() -> bool:
    """Laeuft `bindung serve` schon, und auf demselben Datenordner?

    Verglichen wird der Fingerabdruck aus `/healthz`, nicht der Pfad. Dann hat dieser
    Prozess keine Tagesaufgabe zu starten: der andere macht sie.
    """
    from bindung.web.routen import anwendung

    port = int(os.environ.get("BINDUNG_PORT") or SERVE_PORT)
    antwort = lebenszeichen(port)
    return bool(antwort) and antwort.get("daten") == anwendung.daten_kennung()


def _browser_wenn_bereit(server, adresse: str) -> None:
    for _ in range(300):
        if server.started:
            break
        time.sleep(0.1)
    if not os.environ.get("BINDUNG_KEIN_BROWSER"):
        webbrowser.open(adresse)


def main() -> None:
    port, laeuft = port_waehlen(int(os.environ.get("BINDUNG_APP_PORT") or PORT))
    adresse = f"http://{HOST}:{port}/"
    if laeuft:
        print(f"Bindung läuft schon: {adresse}")
        if not os.environ.get("BINDUNG_KEIN_BROWSER"):
            webbrowser.open(adresse)
        return

    import uvicorn

    from bindung.web import basis
    from bindung.web.server import app

    if serve_teilt_die_daten():
        os.environ[tagesaufgabe.UMGEBUNG] = "0"
        print(f"Hinweis: bindung serve läuft schon auf Port "
              f"{os.environ.get('BINDUNG_PORT') or SERVE_PORT} mit denselben Daten; "
              "die Tagesmeldung schickt dieser.")

    # `log_config=None`: eine App ohne Terminal hat kein stdout, auf das uvicorns Formatierer
    # sich verlassen duerfte.
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning",
                                           log_config=None))

    def beenden() -> None:
        server.should_exit = True

    basis.BEENDEN = beenden
    threading.Thread(target=_browser_wenn_bereit, args=(server, adresse), daemon=True).start()
    if menueleiste.verfuegbar() and not os.environ.get("BINDUNG_KEINE_MENUELEISTE"):
        print(f"Bindung läuft: {adresse}\nDaten: {pfade.DATEN}\n"
              "Beenden: in der App unten links oder in der Menüleiste.")
        menueleiste.laufen(server, adresse)
    else:
        print(f"Bindung läuft: {adresse}\nDaten: {pfade.DATEN}\n"
              "Beenden: in der App unten links oder mit Strg+C.")
        server.run()


if __name__ == "__main__":
    main()
