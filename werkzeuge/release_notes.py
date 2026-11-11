"""Gibt den Abschnitt einer Version aus `CHANGELOG.md` aus -- fuer `gh release create --notes-file`.

    python werkzeuge/release_notes.py 0.1.0                  # der Text ohne die Ueberschrift
    python werkzeuge/release_notes.py 0.1.0 --erste-zeile    # nur der erste Satz (Tag-Nachricht)

Der Abschnitt beginnt bei `## <Version> (<Datum>)` und endet vor der naechsten `## `-Ueberschrift.
Gibt es ihn nicht oder ist er leer, endet das Skript mit Fehler: ein Release ohne Notizen wird
nicht veroeffentlicht (docs/release.md).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def abschnitt(text: str, version: str) -> str:
    """Der Text unter `## <version> (...)`, ohne die Ueberschrift, ohne Leerzeilen an den Raendern.

    Leer, wenn es keine solche Ueberschrift gibt.
    """
    ueberschrift = re.compile(rf"^## {re.escape(version)}(?: \(.*\))?\s*$", re.M)
    treffer = ueberschrift.search(text)
    if not treffer:
        return ""
    rest = text[treffer.end():]
    naechste = re.search(r"^## ", rest, re.M)
    return (rest[:naechste.start()] if naechste else rest).strip()


def erste_zeile(notizen: str) -> str:
    """Die erste Zeile der Notizen, die Text ist (keine Ueberschrift, keine Aufzaehlung)."""
    for zeile in notizen.splitlines():
        if zeile.strip() and not zeile.lstrip().startswith(("#", "-", "*")):
            return zeile.strip()
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Release-Notizen einer Version aus CHANGELOG.md")
    ap.add_argument("version", help="zum Beispiel 0.1.0 (ohne v)")
    ap.add_argument("--erste-zeile", action="store_true", help="nur der erste Satz")
    ap.add_argument("--datei", type=Path, default=CHANGELOG, help="Vorgabe: CHANGELOG.md")
    args = ap.parse_args()
    notizen = abschnitt(args.datei.read_text(encoding="utf-8"), args.version.removeprefix("v"))
    if not notizen:
        sys.exit(f"Kein Abschnitt für Version {args.version} in {args.datei.name}.")
    print(erste_zeile(notizen) if args.erste_zeile else notizen)


if __name__ == "__main__":
    main()
