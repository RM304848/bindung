"""Erzeugt die Symbole der App aus dem Entwurf in `symbol.svg`.

    python werkzeuge/symbole/erzeugen.py                 # PNGs nach bindung/web/statisch/
    python werkzeuge/symbole/erzeugen.py --iconset DIR   # Bilder fuer `iconutil -c icns`

WARUM VON HAND GERECHNET. Das Symbol sind zwei Ringe und ein abgerundetes
Quadrat; das zeichnet man in zwanzig Zeilen. `cairosvg` braucht die native
Bibliothek cairo (auf diesem Mac nicht da), `rsvg-convert` fehlt, und
`qlmanage -t` liefert immer einen deckend weissen Hintergrund und rendert je
nach hellem oder dunklem System in anderen Farben. Hier gibt es dafuer keine
Abhaengigkeit, die Pixel sind jedes Mal dieselben, und die Ecken sind wirklich
durchsichtig.

Die Zahlen der Ringe stehen im SVG und werden hier daraus gelesen; die Farben
kommen aus der Palette in `stil.css` (`--akzent`, `--akzent-text`), nicht aus
einer eigenen Liste. `tests/test_web_manifest.py` prueft, dass die Dateien
vorhanden sind und das SVG und das Stylesheet dieselbe Farbe nennen.

Erzeugt werden:

* `symbol-180.png`           apple-touch-icon: deckend, bis zum Rand (iOS rundet selbst)
* `symbol-192.png`, `symbol-512.png`
                             abgerundetes Quadrat in Akzentfarbe, weisse Ringe
* `symbol-maskable-512.png`  deckend bis zum Rand, Ringe in der sicheren Mitte
                             (Android schneidet beliebig zu)
* `symbol-menue.png`         schwarze Ringe auf durchsichtig, als Vorlage fuer die
                             Menueleiste des Mac (macOS faerbt sie selbst ein)
"""

from __future__ import annotations

import argparse
import math
import re
import struct
import sys
import zlib
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
STATISCH = WURZEL / "bindung" / "web" / "statisch"
SVG = STATISCH / "symbol.svg"
CSS = STATISCH / "stil.css"


def palette() -> dict[str, tuple[int, int, int]]:
    """Die hellen Farben aus dem ersten `:root`-Block des Stylesheets."""
    block = re.search(r":root\s*\{([^{}]*)\}", CSS.read_text(encoding="utf-8")).group(1)
    return {name: _hex(wert)
            for name, wert in re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", block)}


def _hex(text: str) -> tuple[int, int, int]:
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def ringe() -> tuple[list[tuple[float, float, float]], float]:
    """([(mx, my, radius)], Strichbreite) aus dem SVG, im Koordinatenraum 0..512."""
    svg = SVG.read_text(encoding="utf-8")
    kreise = [(float(x), float(y), float(r)) for x, y, r in re.findall(
        r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"[^>]*r="([\d.]+)"', svg)]
    breite = float(re.search(r"stroke-width:\s*([\d.]+)", svg).group(1))
    if len(kreise) != 2:
        raise SystemExit("symbol.svg: erwartet werden genau zwei Kreise")
    return kreise, breite


# ------------------------------------------------------------ Zeichnen

def _abdeckung(abstand: float) -> float:
    """Wie viel eines Pixels liegt innen, wenn die Kante `abstand` Pixel entfernt ist."""
    return min(1.0, max(0.0, 0.5 - abstand))


def _rundquadrat(x: float, y: float, mitte: float, halb: float, radius: float) -> float:
    """Abstand zum abgerundeten Quadrat (negativ innen)."""
    qx, qy = abs(x - mitte) - (halb - radius), abs(y - mitte) - (halb - radius)
    aussen = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return aussen + min(max(qx, qy), 0.0) - radius


def zeichnen(groesse: int, *, grund: str, ring_faktor: float, vordergrund: tuple[int, int, int],
             hintergrund: tuple[int, int, int] | None, rand: float = 0.0,
             rundung: float = 0.0) -> bytes:
    """Ein Bild als RGBA-Bytes.

    grund        "voll" (bis zum Rand), "rund" (abgerundetes Quadrat) oder "keiner"
    ring_faktor  Groesse des Zeichens im Verhaeltnis zum Entwurf (1.0 = wie im SVG)
    rand         Abstand des Quadrats vom Bildrand als Bruchteil (nur "rund")
    rundung      Eckenradius als Bruchteil der Bildkante (nur "rund")
    """
    kreise, breite = ringe()
    mass = groesse / 512
    s = ring_faktor * mass
    mitte = groesse / 2
    # Die Ringe um die Bildmitte legen (Entwurf: Mitte bei 256, 256).
    ringe_px = [((mitte + (x - 256) * s), (mitte + (y - 256) * s), r * s) for x, y, r in kreise]
    halbe_breite = breite * s / 2
    halb = groesse / 2 * (1 - rand)
    radius = groesse * rundung
    zeilen = bytearray()
    for j in range(groesse):
        zeilen.append(0)   # PNG-Filter "keiner"
        y = j + 0.5
        for i in range(groesse):
            x = i + 0.5
            d_ring = min(abs(math.hypot(x - mx, y - my) - r) - halbe_breite
                         for mx, my, r in ringe_px)
            a_ring = _abdeckung(d_ring)
            if grund == "keiner":
                a_grund = 0.0
            elif grund == "voll":
                a_grund = 1.0
            else:
                a_grund = _abdeckung(_rundquadrat(x, y, mitte, halb, radius))
            if hintergrund is None:
                farbe, alpha = vordergrund, a_ring
            else:
                alpha = a_grund
                farbe = tuple(round(h * (1 - a_ring) + v * a_ring)
                              for h, v in zip(hintergrund, vordergrund, strict=True))
            zeilen += bytes((*farbe, round(alpha * 255)))
    return bytes(zeilen)


def png(groesse: int, rohdaten: bytes) -> bytes:
    """RGBA-Rohdaten (mit Filterbyte je Zeile) als PNG-Datei."""
    def stueck(art: bytes, inhalt: bytes) -> bytes:
        rumpf = art + inhalt
        return struct.pack(">I", len(inhalt)) + rumpf + struct.pack(">I", zlib.crc32(rumpf))

    kopf = struct.pack(">IIBBBBB", groesse, groesse, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + stueck(b"IHDR", kopf)
            + stueck(b"IDAT", zlib.compress(rohdaten, 9)) + stueck(b"IEND", b""))


# ------------------------------------------------------------ Satz

def app_symbol(groesse: int, art: str) -> bytes:
    farben = palette()
    akzent, weiss = farben["--akzent"], farben["--akzent-text"]
    if art == "voll":
        roh = zeichnen(groesse, grund="voll", ring_faktor=1.0, vordergrund=weiss,
                       hintergrund=akzent)
    elif art == "maskable":
        roh = zeichnen(groesse, grund="voll", ring_faktor=0.8, vordergrund=weiss,
                       hintergrund=akzent)
    elif art == "icns":   # wie die Vorlage von Apple: Quadrat mit Luft ringsum
        roh = zeichnen(groesse, grund="rund", ring_faktor=0.92, vordergrund=weiss,
                       hintergrund=akzent, rand=0.098, rundung=0.18)
    elif art == "menue":
        roh = zeichnen(groesse, grund="keiner", ring_faktor=0.94, vordergrund=(0, 0, 0),
                       hintergrund=None)
    else:   # "rund": 192 und 512 fuer das Manifest
        roh = zeichnen(groesse, grund="rund", ring_faktor=0.9, vordergrund=weiss,
                       hintergrund=akzent, rand=0.0, rundung=0.22)
    return png(groesse, roh)


PNGS = (("symbol-180.png", 180, "voll"), ("symbol-192.png", 192, "rund"),
        ("symbol-512.png", 512, "rund"), ("symbol-maskable-512.png", 512, "maskable"),
        ("symbol-menue.png", 44, "menue"))

#: Dateiname im .iconset -> Kantenlaenge (iconutil erwartet genau diese Namen).
ICONSET = {"icon_16x16.png": 16, "icon_16x16@2x.png": 32, "icon_32x32.png": 32,
           "icon_32x32@2x.png": 64, "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
           "icon_256x256.png": 256, "icon_256x256@2x.png": 512, "icon_512x512.png": 512,
           "icon_512x512@2x.png": 1024}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--iconset", type=Path, help="Ordner fuer die Bilder eines .iconset")
    args = ap.parse_args()
    if args.iconset:
        args.iconset.mkdir(parents=True, exist_ok=True)
        gebaut: dict[int, bytes] = {}
        for name, kante in ICONSET.items():
            if kante not in gebaut:
                gebaut[kante] = app_symbol(kante, "icns")
            (args.iconset / name).write_bytes(gebaut[kante])
        print(f"{len(ICONSET)} Bilder in {args.iconset}")
        return
    for name, kante, art in PNGS:
        (STATISCH / name).write_bytes(app_symbol(kante, art))
        print(f"{name} ({kante} x {kante})")


if __name__ == "__main__":
    sys.exit(main())
