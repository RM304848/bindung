# PyInstaller-Bauplan fuer die Mac-App (wie health_os.spec in Health OS).
#
#     werkzeuge/paket/bauen.sh        # Symbol, App, Rauchtest, .dmg
#
# Mitgenommen wird, was die App zur Laufzeit von der Platte liest und kein Import verraet:
# Vorlagen, Stylesheet, Skripte, Symbole, Schema -- dieselbe Liste wie package-data in
# pyproject.toml -- und die Module, die erst per Name geladen werden (uvicorn, die Router).
#
# Zeitzonen: `zoneinfo` liest die Zeitzonendatenbank des Systems (/usr/share/zoneinfo);
# die hat jeder Mac. Gibt es das Paket `tzdata` im Build, kommt es zusaetzlich mit.

from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

from bindung import __version__

WURZEL = Path(SPECPATH).parent.parent  # noqa: F821 -- von PyInstaller gesetzt
BAU = WURZEL / "build" / "paket"

daten = (collect_data_files("bindung", includes=["**/*.html", "**/*.css", "**/*.js", "**/*.svg",
                                                 "**/*.png", "**/*.sql"])
         + collect_data_files("pywebpush") + copy_metadata("bindung"))
versteckt = (collect_submodules("bindung") + collect_submodules("uvicorn")
             + collect_submodules("pywebpush") + ["py_vapid", "http_ece", "multipart",
                                                  "python_multipart", "AppKit", "Foundation",
                                                  "PyObjCTools.AppHelper",
                                                  "PyObjCTools.MachSignals"])
if find_spec("tzdata"):
    daten += collect_data_files("tzdata")
    versteckt += collect_submodules("tzdata")

a = Analysis(  # noqa: F821
    [str(WURZEL / "werkzeuge" / "paket" / "start.py")],
    pathex=[str(WURZEL)],
    datas=daten,
    hiddenimports=versteckt,
    excludes=["tkinter", "pytest", "ruff", "PyInstaller"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Bindung",  # noqa: F821
          console=False)
sammlung = COLLECT(exe, a.binaries, a.datas, name="Bindung")  # noqa: F821
app = BUNDLE(  # noqa: F821
    sammlung,
    name="Bindung.app",
    icon=str(BAU / "Bindung.icns"),
    bundle_identifier="de.bindung.app",
    info_plist={
        # Kein Symbol im Dock: das Fenster der App ist der Browser. Ein Dock-Symbol liesse
        # sich "beenden", ohne dass der Server davon erfuehre. Beendet wird ueber "Beenden"
        # in der App oder in der Menueleiste.
        "LSUIElement": True,
        "CFBundleName": "Bindung",
        "CFBundleDisplayName": "Bindung",
        "CFBundleShortVersionString": __version__,
    },
)
