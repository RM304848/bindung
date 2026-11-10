"""Gemeinsamer Rahmen fuer alle Tests.

Kein Test darf die echten Daten beruehren -- weder lesen noch schreiben. Zwei
Sicherungen:

1. VOR dem ersten `import bindung` zeigt `BINDUNG_DATEN` (und HOME) in einen
   Wegwerfordner. `pfade.py` liest die Wurzel beim Import; wer sie zu spaet
   umstellt, hat schon den echten Ordner gebunden.
2. Jeder Test bekommt zusaetzlich seinen EIGENEN Datenordner (`daten`,
   autouse): die Konstanten in `pfade` werden umgebogen. Module lesen sie zur
   Laufzeit als `pfade.X` (CLAUDE.md), deshalb genuegt das.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_SITZUNG = Path(tempfile.mkdtemp(prefix="bindung-sitzung-"))
atexit.register(shutil.rmtree, _SITZUNG, ignore_errors=True)
(_SITZUNG / "heim").mkdir()
os.environ["BINDUNG_DATEN"] = str(_SITZUNG / "daten")
os.environ.update(HOME=str(_SITZUNG / "heim"), APPDATA=str(_SITZUNG / "heim" / "appdata"),
                  XDG_DATA_HOME=str(_SITZUNG / "heim" / "share"),
                  USERPROFILE=str(_SITZUNG / "heim"))
for _name in ("BINDUNG_SICHER", "BINDUNG_HOST", "BINDUNG_PORT"):
    os.environ.pop(_name, None)

import pytest  # noqa: E402

from bindung import auth, pfade  # noqa: E402

PASSWORT = "geheimes-passwort"


@pytest.fixture(autouse=True)
def daten(tmp_path, monkeypatch) -> Path:
    """Ein leerer Datenordner nur fuer diesen Test."""
    wurzel = tmp_path / "daten"
    monkeypatch.setattr(pfade, "DATEN", wurzel)
    monkeypatch.setattr(pfade, "DB_PATH", wurzel / "bindung.db")
    monkeypatch.setattr(pfade, "VAPID_PATH", wurzel / "vapid.json")
    monkeypatch.setattr(pfade, "SICHERUNG_DIR", wurzel / "sicherung")
    auth.fehlversuche_vergessen()
    return wurzel


@pytest.fixture
def con(daten):
    """Eine Verbindung zur leeren Datenbank dieses Tests."""
    from bindung import db

    verbindung = db.verbinden()
    yield verbindung
    verbindung.close()


@pytest.fixture
def nutzer(con) -> str:
    """Ein erfundener Nutzer; gibt seinen Namen zurueck."""
    auth.nutzer_anlegen(con, "Beispiel", PASSWORT)
    return "Beispiel"


@pytest.fixture
def client():
    """Ein Testclient ohne Anmeldung."""
    from fastapi.testclient import TestClient

    from bindung.web.server import app

    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def angemeldet(client, nutzer):
    """Ein Testclient mit gueltiger Sitzung."""
    antwort = client.post("/anmeldung", data={"name": nutzer, "passwort": PASSWORT})
    assert antwort.status_code == 303
    return client
