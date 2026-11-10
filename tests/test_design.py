"""Die Design-Konventionen, geprueft aus docs/design_conventions.yaml.

Die Regeln stehen in der YAML-Datei, mit Grund; hier steht nur, WIE eine Art
von Pruefung ausgefuehrt wird. Eine neue Konvention ist damit ein Eintrag in
der Datei und kein neuer Test, der irgendwo in test_web.py verschwindet.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

WURZEL = Path(__file__).resolve().parent.parent
KONVENTIONEN = WURZEL / "docs" / "design_conventions.yaml"
VORLAGEN = WURZEL / "bindung" / "web" / "vorlagen"
CSS = WURZEL / "bindung" / "web" / "statisch" / "stil.css"
REGELN = yaml.safe_load(KONVENTIONEN.read_text(encoding="utf-8"))["regeln"]

BEKANNT = {"css_farben_nur_in_wurzel", "paletten_gleich", "vorlagen_verbieten",
           "felder_mit_beschriftung", "nur_deutsch", "datei_enthaelt", "beruehrziele"}


def _mit(art: str) -> list[dict]:
    return [r for r in REGELN if (r.get("pruefung") or {}).get("art") == art]


def _ids(regel: dict) -> str:
    return regel["id"]


def _ohne_kommentare(text: str) -> str:
    """Jinja-Kommentare erklaeren oft, warum es etwas NICHT gibt -- sie sind keine Verwendung."""
    return re.sub(r"\{#.*?#\}", " ", text, flags=re.S)


def _css_ohne_kommentare() -> str:
    return re.sub(r"/\*.*?\*/", " ", CSS.read_text(encoding="utf-8"), flags=re.S)


def _vorlagen() -> list[Path]:
    return sorted(VORLAGEN.glob("*.html"))


# ------------------------------------------------------------------- Datei

def test_every_rule_says_what_and_why():
    ids = [r["id"] for r in REGELN]
    assert len(ids) == len(set(ids)), "doppelte Kennung"
    for r in REGELN:
        assert r.get("regel") and r.get("warum"), r["id"]


def test_every_check_has_an_implementation():
    for r in REGELN:
        art = (r.get("pruefung") or {}).get("art")
        assert art is None or art in BEKANNT, f"{r['id']}: unbekannte Pruefung {art}"


def test_every_exception_is_listed_as_open():
    """Eine Ausnahme ohne `offen` wird zur stillen Erlaubnis."""
    for r in REGELN:
        if (r.get("pruefung") or {}).get("ausnahmen"):
            assert r.get("offen"), r["id"]


def test_there_are_templates_and_a_stylesheet_to_check():
    assert {v.name for v in _vorlagen()} >= {"basis.html", "anmeldung.html", "start.html"}
    assert CSS.exists()


# ------------------------------------------------------------------ Farben

_FARBE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")


def _wurzelbloecke(css: str) -> list[tuple[str, str]]:
    """Alle `:root { ... }`-Bloecke als ("hell" | "dunkel", Inhalt)."""
    bloecke = []
    for treffer in re.finditer(r":root\s*\{([^{}]*)\}", css):
        davor = css[:treffer.start()]
        im_dunkel = davor.rfind("prefers-color-scheme: dark") > davor.rfind("}\n}")
        bloecke.append(("dunkel" if im_dunkel else "hell", treffer.group(1)))
    return bloecke


@pytest.mark.parametrize("regel", _mit("css_farben_nur_in_wurzel"), ids=_ids)
def test_colours_only_live_in_root_variables(regel):
    css = _css_ohne_kommentare()
    ohne_wurzel = re.sub(r":root\s*\{[^{}]*\}", " ", css)
    funde = _FARBE.findall(ohne_wurzel)
    assert not funde, f"{regel['id']}: Farben ausserhalb von :root: {funde}"
    assert _wurzelbloecke(css), "kein :root-Block gefunden"


def _variablen(inhalt: str) -> set[str]:
    return set(re.findall(r"(--[\w-]+)\s*:", inhalt))


@pytest.mark.parametrize("regel", _mit("paletten_gleich"), ids=_ids)
def test_light_and_dark_define_the_same_colours(regel):
    css = _css_ohne_kommentare()
    bloecke = _wurzelbloecke(css)
    hell = set().union(*(_variablen(i) for k, i in bloecke if k == "hell"))
    dunkel = set().union(*(_variablen(i) for k, i in bloecke if k == "dunkel"))
    assert dunkel, "kein dunkler :root-Block"
    farben_hell = {v for v in hell if any(
        _FARBE.search(w) for k, i in bloecke if k == "hell"
        for w in re.findall(rf"{re.escape(v)}\s*:\s*([^;]+);", i))}
    assert farben_hell == dunkel, (
        f"{regel['id']}: nur hell: {sorted(farben_hell - dunkel)}, "
        f"nur dunkel: {sorted(dunkel - farben_hell)}")
    benutzt = set(re.findall(r"var\((--[\w-]+)", css))
    assert benutzt <= hell, f"{regel['id']}: nie definiert: {sorted(benutzt - hell)}"


# ------------------------------------------------------- Vorlagen verbieten

@pytest.mark.parametrize("regel", _mit("vorlagen_verbieten"), ids=_ids)
def test_templates_avoid_what_the_convention_forbids(regel):
    p = regel["pruefung"]
    dateien = [v for v in _vorlagen() if v.name not in (p.get("ausnahmen") or [])]
    texte = {v.name: _ohne_kommentare(v.read_text(encoding="utf-8")) for v in dateien}
    if p.get("auch_css"):
        texte["stil.css"] = _css_ohne_kommentare()
    funde = [f"{name}: {muster}" for name, text in texte.items()
             for muster in p["muster"] if re.search(muster, text)]
    assert not funde, f"{regel['id']}: {funde}"


@pytest.mark.parametrize("regel", _mit("vorlagen_verbieten"), ids=_ids)
def test_an_exception_that_is_fixed_is_removed_from_the_list(regel):
    """Sonst bleibt eine behobene Altlast als Erlaubnis stehen."""
    p = regel["pruefung"]
    for name in p.get("ausnahmen") or []:
        text = _ohne_kommentare((VORLAGEN / name).read_text(encoding="utf-8"))
        assert any(re.search(m, text) for m in p["muster"]), (
            f"{regel['id']}: {name} ist behoben -- aus `ausnahmen` und `offen` streichen")


# --------------------------------------------------------- Felder und Sprache

class _Seite(HTMLParser):
    """Sammelt Felder, Beschriftungen und sichtbaren Text einer Vorlage."""

    def __init__(self) -> None:
        super().__init__()
        self.felder: list[dict] = []
        self.label_fuer: set[str] = set()
        self.texte: list[str] = []
        self._im_label = 0
        self._ueberspringen = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._ueberspringen += 1
        if tag == "label":
            self._im_label += 1
            if a.get("for"):
                self.label_fuer.add(a["for"])
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden":
            if a.get("type") in ("submit", "button"):
                return
            self.felder.append({**a, "_tag": tag, "_im_label": self._im_label > 0})
        for attribut in ("placeholder", "aria-label", "title", "alt"):
            if a.get(attribut):
                self.texte.append(a[attribut])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ueberspringen -= 1
        if tag == "label":
            self._im_label -= 1

    def handle_data(self, data):
        if not self._ueberspringen and data.strip():
            self.texte.append(data.strip())


def _lesen(vorlage: Path) -> _Seite:
    text = _ohne_kommentare(vorlage.read_text(encoding="utf-8"))
    text = re.sub(r"\{%.*?%\}", " ", text, flags=re.S)
    text = re.sub(r"\{\{.*?\}\}", "x", text, flags=re.S)
    seite = _Seite()
    seite.feed(text)
    return seite


@pytest.mark.parametrize("regel", _mit("felder_mit_beschriftung"), ids=_ids)
@pytest.mark.parametrize("vorlage", _vorlagen(), ids=lambda v: v.name)
def test_every_form_field_has_a_label(regel, vorlage):
    seite = _lesen(vorlage)
    ohne = [f"<{f['_tag']} name={f.get('name')}>" for f in seite.felder
            if not (f.get("aria-label") or f["_im_label"]
                    or (f.get("id") and f["id"] in seite.label_fuer))]
    assert not ohne, f"{regel['id']}: {vorlage.name}: ohne Beschriftung: {ohne}"


@pytest.mark.parametrize("regel", _mit("nur_deutsch"), ids=_ids)
@pytest.mark.parametrize("vorlage", _vorlagen(), ids=lambda v: v.name)
def test_visible_text_is_german(regel, vorlage):
    p = regel["pruefung"]
    verboten = [w for w in p["verboten"] if w not in (p.get("ausnahmen") or [])]
    muster = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in verboten) + r")\b")
    funde = [t for t in _lesen(vorlage).texte if muster.search(t)]
    assert not funde, f"{regel['id']}: {vorlage.name}: {funde}"


# ------------------------------------------------------------- Dateien, Ziele

@pytest.mark.parametrize("regel", _mit("datei_enthaelt"), ids=_ids)
def test_file_contains_what_the_convention_requires(regel):
    p = regel["pruefung"]
    text = (WURZEL / p["datei"]).read_text(encoding="utf-8")
    fehlt = [m for m in p["muster"] if not re.search(m, text)]
    assert not fehlt, f"{regel['id']}: {p['datei']} fehlt: {fehlt}"


def _regeln_des_stylesheets() -> list[tuple[list[str], str]]:
    css = re.sub(r"@media[^{]*\{", " ", _css_ohne_kommentare())
    return [([s.strip() for s in kopf.split(",")], inhalt)
            for kopf, inhalt in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


@pytest.mark.parametrize("regel", _mit("beruehrziele"), ids=_ids)
def test_touch_targets_are_at_least_44px(regel):
    css = _css_ohne_kommentare()
    ziel = re.search(r"--ziel:\s*(\d+)px", css)
    assert ziel and int(ziel.group(1)) >= 44, "--ziel ist nicht mindestens 44px"
    regeln = _regeln_des_stylesheets()
    fehlt = [s for s in regel["pruefung"]["selektoren"]
             if not any(s in koepfe and "min-height: var(--ziel)" in inhalt
                        for koepfe, inhalt in regeln)]
    assert not fehlt, f"{regel['id']}: ohne min-height: var(--ziel): {fehlt}"
