#!/bin/zsh
# Baut die Mac-App und die .dmg: Symbol -> App -> Rauchtest -> .dmg.
#
#     werkzeuge/paket/bauen.sh
#
# Voraussetzung: .venv mit  pip install -e '.[dev,paket]'
# Ergebnis: dist/Bindung-<Version>-mac.dmg. Nicht signiert: eine .dmg, die auf diesem
# Rechner gebaut wurde, oeffnet sich ohne Warnung; eine heruntergeladene braucht beim
# ersten Mal Rechtsklick -> Oeffnen.
set -euo pipefail
cd "${0:A:h}/../.."
PY=.venv/bin/python
BAU=build/paket
mkdir -p "$BAU"

# 1. Symbol: aus symbol.svg alle Groessen, die macOS will (werkzeuge/symbole/erzeugen.py).
rm -rf "$BAU/Bindung.iconset"
$PY werkzeuge/symbole/erzeugen.py --iconset "$BAU/Bindung.iconset"
iconutil -c icns "$BAU/Bindung.iconset" -o "$BAU/Bindung.icns"

# 2. App
$PY -m PyInstaller --noconfirm --distpath dist --workpath "$BAU/work" werkzeuge/paket/bindung.spec

# 3. Rauchtest: startet sie in einem leeren Datenordner und klickt sich durch.
$PY werkzeuge/paket/rauchtest.py "dist/Bindung.app/Contents/MacOS/Bindung"

# 4. .dmg: die App und ein Verweis auf Programme zum Hineinziehen.
VERSION=$($PY -c 'from bindung import __version__; print(__version__)')
rm -rf "$BAU/dmg" && mkdir -p "$BAU/dmg"
cp -R "dist/Bindung.app" "$BAU/dmg/"
ln -s /Applications "$BAU/dmg/Programme"
rm -f "dist/Bindung-$VERSION-mac.dmg"
hdiutil create -volname "Bindung" -srcfolder "$BAU/dmg" -ov -format UDZO \
  "dist/Bindung-$VERSION-mac.dmg" >/dev/null
echo "Fertig: dist/Bindung-$VERSION-mac.dmg"
