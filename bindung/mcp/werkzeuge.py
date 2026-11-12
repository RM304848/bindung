"""Was ein Modell ueber MCP lesen und eintragen darf (PLAN.md, Abschnitt 14).

Jedes Werkzeug geht ueber dieselben Funktionen wie die Seiten (`personen`, `kontakte`,
`faelligkeit`, `stichtage`, `angehoerige`, `tagesmeldung`), nie ueber SQL. Damit gelten
dieselben Regeln: kein Touchpoint in der Zukunft, ein Touchpoint loescht den naechsten
Termin, jede Abfrage filtert nach der `nutzer_id` -- ein Modell sieht und schreibt nur fuer
den einen Nutzer, als der `bindung mcp` laeuft.

LESEN: `personen_suchen`, `person`, `wer_wartet`, `diese_woche`, `tags`.
SCHREIBEN: `person_anlegen`, `touchpoint_eintragen`, `profilnotiz_setzen`,
`stichtag_anlegen`. Archivieren, Loeschen, Tags verwalten und Einstellungen gibt es hier
nicht: ein falscher Schreibzug dort faellt nicht auf.

Antworten sind Text, so formatiert wie die App (Zustand, „vor 3 Wochen“), mit der Nummer der
Person in eckigen Klammern. Eine Eingabe, die die Seite ablehnen wuerde, kommt mit demselben
deutschen Satz als `isError`-Antwort zurueck; ein Name, der auf mehrere Personen passt, wird
mit den Kandidaten abgelehnt, nie geraten.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from bindung import (
    angehoerige,
    auth,
    db,
    faelligkeit,
    kontakte,
    personen,
    stichtage,
    tagesmeldung,
)
from bindung.personen import EingabeFehler, NichtGefunden

#: So viele Zeilen zeigt eine Liste hoechstens, wenn nichts anderes verlangt wird.
LISTE_VORGABE = 25
LISTE_HOECHSTENS = 100
#: So viele Touchpoints zeigt `person` vorgabemaessig aus „Zuletzt besprochen“.
VERLAUF_VORGABE = 10
#: So viele Kandidaten nennt eine Ablehnung wegen eines mehrdeutigen Namens.
KANDIDATEN_HOECHSTENS = 8

KARTEN_TITEL = {faelligkeit.KARTE_AUFMERKSAMKEIT: "Braucht Aufmerksamkeit",
                faelligkeit.KARTE_ERKALTET: "Erkaltet",
                faelligkeit.KARTE_WOCHE: "Diese Woche"}


class Meldung(ValueError):
    """Eine Antwort fuer das Modell, die kein Erfolg ist (`isError`); der Text ist deutsch."""


@dataclass(frozen=True)
class Kontext:
    """Woran ein Werkzeug arbeitet: die Verbindung, der Nutzer, sein heutiger Tag."""

    con: sqlite3.Connection
    nutzer_id: int
    nutzer_name: str
    heute: dt.date


@dataclass(frozen=True, slots=True)
class Werkzeug:
    name: str
    beschreibung: str
    funktion: Callable[[Kontext, dict], list[str]]
    #: Name -> (Typ oder Typen, Beschreibung, Pflicht)
    parameter: dict[str, tuple[str | tuple[str, ...], str, bool]] = field(default_factory=dict)
    schema_zusatz: dict = field(default_factory=dict)
    #: Schreibt das Werkzeug? Die Beschreibung sagt es dem Modell, der Client kann danach fragen.
    schreibt: bool = False

    def als_dict(self) -> dict:
        schema = {"type": "object",
                  "properties": {n: {"type": list(t) if isinstance(t, tuple) else t,
                                     "description": b}
                                 for n, (t, b, _p) in self.parameter.items()},
                  "required": [n for n, (_t, _b, pflicht) in self.parameter.items() if pflicht],
                  "additionalProperties": False}
        for name, zusatz in self.schema_zusatz.items():
            schema["properties"][name].update(zusatz)
        return {"name": self.name, "description": self.beschreibung, "inputSchema": schema,
                "annotations": {"readOnlyHint": not self.schreibt, "destructiveHint": False}}


@dataclass(frozen=True, slots=True)
class Ressource:
    uri: str
    name: str
    beschreibung: str
    #: Bekommt den Namen aus `--nutzer` (oder `None`) und gibt den Text.
    lesen: Callable[[str | None], str]

    def als_dict(self) -> dict:
        return {"uri": self.uri, "name": self.name, "description": self.beschreibung,
                "mimeType": "text/markdown"}


# ---------------------------------------------------------------- Nutzer

def nutzer_waehlen(con: sqlite3.Connection, name: str | None) -> sqlite3.Row:
    """Der Nutzer, als der das Modell handelt: der genannte, sonst der einzige.

    Wirft `Meldung` mit dem Satz, der dem Menschen sagt, was zu tun ist.
    """
    alle = auth.nutzer_liste(con)
    if not alle:
        raise Meldung("Es gibt noch keinen Nutzer. Lege einen an: bindung nutzer anlegen <name>")
    namen = ", ".join(z["name"] for z in alle)
    if name is not None and name.strip():
        for zeile in alle:
            if zeile["name"].casefold() == name.strip().casefold():
                return zeile
        raise Meldung(f"Den Nutzer „{name.strip()}“ gibt es nicht. Vorhanden: {namen}.")
    if len(alle) == 1:
        return alle[0]
    raise Meldung(f"Es gibt mehrere Nutzer ({namen}). Starte den Server mit "
                  "bindung mcp --nutzer <name>.")


@contextmanager
def _kontext(nutzer: str | None):
    con = db.verbinden()
    try:
        zeile = nutzer_waehlen(con, nutzer)
        yield Kontext(con, zeile["id"], zeile["name"], personen.heute(con, zeile["id"]))
    finally:
        con.close()


# ---------------------------------------------------------------- Worte

def _tag(tag: dt.date | None) -> str:
    return tag.isoformat() if tag else "—"


def _vor(k: Kontext, tag: dt.date) -> str:
    return faelligkeit.vor_text((k.heute - tag).days)


def _zustand(k: Kontext, b: faelligkeit.Bindung | None) -> str:
    """Der Zustand wie die Plakette der App, dazu der letzte Touchpoint."""
    if b is None:
        return "archiviert"
    if b.zustand == faelligkeit.UNBEKANNT:
        return "noch kein Touchpoint"
    plakette = faelligkeit.plakette(b, k.heute).text
    label = "ok" if b.zustand == faelligkeit.OK else plakette
    return f"{label} · letzter Touchpoint {_vor(k, b.letzter_kontakt)} ({_tag(b.letzter_kontakt)})"


def _tagnamen(k: Kontext) -> dict[int, str]:
    return {z["id"]: z["name"] for z in personen.tags_mit_zaehlern(k.con, k.nutzer_id)}


def _tags_von(k: Kontext, person_id: int, namen: dict[int, str]) -> list[str]:
    ids = personen.tags_der_person(k.con, k.nutzer_id, person_id)
    return sorted((namen[i] for i in ids if i in namen), key=str.casefold)


def _kurz(person: sqlite3.Row) -> str:
    """„Anna Beispiel [12]“: der Name mit der Nummer, mit der man sie wieder aufruft."""
    return f"{person['name']} [{person['id']}]"


def _zeile(k: Kontext, person: sqlite3.Row, b: faelligkeit.Bindung | None,
           namen: dict[int, str], vorkommen: stichtage.Vorkommen | None = None) -> str:
    teile = [_kurz(person)]
    if person["firma"]:
        teile.append(person["firma"])
    tags = _tags_von(k, person["id"], namen)
    if tags:
        teile.append("Tags: " + ", ".join(tags))
    teile.append(_zustand(k, b))
    if vorkommen is not None:
        teile.append(vorkommen.plakette_text)
    return "- " + " · ".join(teile)


def _eingerueckt(text: str, tiefe: str = "  ") -> str:
    return "\n".join(tiefe + zeile if zeile else zeile for zeile in text.splitlines())


# ------------------------------------------------------ Person finden

def _nummer(wert: object) -> int | None:
    if isinstance(wert, int) and not isinstance(wert, bool):
        return wert
    text = str(wert).strip().strip("[]#").strip()
    return int(text) if text.isdigit() else None


def _person(k: Kontext, wert: object) -> sqlite3.Row:
    """Die Person zu einer Nummer oder einem Namen.

    Ein Name gilt, wenn er genau eine aktive Person trifft: erst voller Name (Gross- und
    Kleinschreibung egal), sonst Teil des Namens. Mehrere Treffer werden mit den Kandidaten
    abgelehnt; die Nummer in der Antwort ist der eindeutige Weg.
    """
    nummer = _nummer(wert)
    if nummer is not None:
        zeile = personen.laden(k.con, k.nutzer_id, nummer)
        if zeile is None:
            raise Meldung(f"Es gibt keine Person mit der Nummer {nummer}.")
        return zeile
    text = str(wert or "").strip()
    if not text:
        raise Meldung("Nenne die Person mit ihrer Nummer oder ihrem Namen.")
    aktive = personen.liste(k.con, k.nutzer_id)
    schluessel = text.casefold()
    genau = [p for p in aktive if p["name"].casefold() == schluessel]
    treffer = genau or [p for p in aktive if schluessel in p["name"].casefold()]
    if not treffer:
        raise Meldung(f"Keine Person mit dem Namen „{text}“ gefunden. Suche mit "
                      "personen_suchen oder lege sie mit person_anlegen an.")
    if len(treffer) > 1:
        raise Meldung(_mehrdeutig(text, treffer))
    return treffer[0]


def _mehrdeutig(text: str, treffer: list[sqlite3.Row]) -> str:
    zeilen = [(f"Der Name „{text}“ passt auf {len(treffer)} Personen. Frag nach, welche gemeint "
              "ist, und nimm ihre Nummer:")]
    for p in treffer[:KANDIDATEN_HOECHSTENS]:
        zusatz = " · ".join(t for t in (p["firma"], p["ort"]) if t)
        zeilen.append(f"- {_kurz(p)}" + (f" · {zusatz}" if zusatz else ""))
    if len(treffer) > KANDIDATEN_HOECHSTENS:
        zeilen.append(f"… und {len(treffer) - KANDIDATEN_HOECHSTENS} weitere.")
    return "\n".join(zeilen)


def _grenze(args: dict, vorgabe: int = LISTE_VORGABE, hoechstens: int = LISTE_HOECHSTENS) -> int:
    wert = args.get("limit")
    return vorgabe if wert is None else min(max(wert, 1), hoechstens)


# ---------------------------------------------------------------- Lesen

def _personen_suchen(k: Kontext, args: dict) -> list[str]:
    tag_id = None
    if args.get("tag"):
        gesucht = str(args["tag"]).strip().casefold()
        tags = personen.tags_mit_zaehlern(k.con, k.nutzer_id)
        passend = [t for t in tags if t["name"].casefold() == gesucht]
        if not passend:
            vorhanden = ", ".join(t["name"] for t in tags) or "keine"
            raise Meldung(f"Den Tag „{args['tag']}“ gibt es nicht. Vorhanden: {vorhanden}.")
        tag_id = passend[0]["id"]
    archiv = bool(args.get("archiv"))
    gefunden = personen.liste(
        k.con, k.nutzer_id, tag_id=tag_id, suche=str(args.get("text") or ""),
        ohne_kontakt=bool(args.get("ohne_touchpoint")), archiviert=archiv)
    grenze = _grenze(args)
    bindungen = {} if archiv else faelligkeit.bindungen(k.con, k.nutzer_id, k.heute)
    vorlauf = stichtage.je_person(stichtage.im_vorlauf(k.con, k.nutzer_id, k.heute))
    namen = _tagnamen(k)
    kopf = f"{len(gefunden)} {'Person' if len(gefunden) == 1 else 'Personen'}"
    if archiv:
        kopf += " im Archiv"
    if len(gefunden) > grenze:
        kopf += f" (die ersten {grenze}, nach Name)"
    if not gefunden:
        return [kopf + "."]
    return [kopf + ":", *[_zeile(k, p, bindungen.get(p["id"]), namen, vorlauf.get(p["id"]))
                          for p in gefunden[:grenze]]]


def _person_seite(k: Kontext, args: dict) -> list[str]:
    p = _person(k, args["person"])
    pid = p["id"]
    b = faelligkeit.bindungen(k.con, k.nutzer_id, k.heute, person_id=pid)[pid]
    namen = _tagnamen(k)
    zeilen = [f"{_kurz(p)}" + ("  (archiviert)" if p["archiviert_am"] else ""),
              f"Heute ist {_tag(k.heute)}."]
    for beschriftung, wert in (("Firma", p["firma"]), ("Rolle", p["rolle"]),
                               ("Telefon", p["telefon"]), ("E-Mail", p["email"]),
                               ("Ort", p["ort"]), ("Herkunft", p["herkunft"])):
        if wert:
            zeilen.append(f"{beschriftung}: {wert}")
    tags = _tags_von(k, pid, namen)
    zeilen.append("Tags: " + (", ".join(tags) if tags else "keine"))
    if p["profilnotiz"]:
        zeilen += ["Profilnotiz:", _eingerueckt(p["profilnotiz"])]
    zeilen.append("Zustand: " + _zustand_lang(k, b))
    zeilen.append(f"Intervall: {b.intervall} Tage"
                  + (" (Vorgabe des Nutzers)" if p["intervall_tage"] is None else ""))
    if b.naechster_termin:
        zeilen.append(f"Nächster Termin: {_tag(b.naechster_termin)}")
    if b.faellig_am:
        zeilen.append(f"Fällig am: {_tag(b.faellig_am)} "
                      f"({faelligkeit.in_text((b.faellig_am - k.heute).days)})"
                      if b.faellig_am >= k.heute else
                      f"Fällig war: {_tag(b.faellig_am)}")
    zeilen += _verlauf_zeilen(k, pid, args.get("touchpoints"))
    zeilen += _angehoerige_zeilen(k, pid)
    zeilen += _stichtag_zeilen(k, pid)
    return zeilen


def _zustand_lang(k: Kontext, b: faelligkeit.Bindung) -> str:
    return faelligkeit.zustand_text(b.zustand) + (
        "" if b.zustand == faelligkeit.UNBEKANNT else f" ({faelligkeit.plakette(b, k.heute).text})")


def _verlauf_zeilen(k: Kontext, person_id: int, grenze: int | None) -> list[str]:
    alle = kontakte.liste(k.con, k.nutzer_id, person_id)
    if not alle:
        return ["", "Zuletzt besprochen: noch kein Touchpoint."]
    gezeigt = alle[:VERLAUF_VORGABE if grenze is None else max(grenze, 1)]
    kopf = "Zuletzt besprochen" + (f" (die letzten {len(gezeigt)} von {len(alle)})"
                                   if len(gezeigt) < len(alle) else "") + ":"
    zeilen = ["", kopf]
    for t in gezeigt:
        art = kontakte.ART_NAMEN[t["art"]]
        zeile = f"- {t['datum']} · {art} [Touchpoint {t['id']}]"
        if t["notiz"]:
            zeile += ":\n" + _eingerueckt(t["notiz"], "    ")
        zeilen.append(zeile)
    return zeilen


def _angehoerige_zeilen(k: Kontext, person_id: int) -> list[str]:
    familie = angehoerige.liste(k.con, k.nutzer_id, person_id)
    if not familie:
        return []
    zeilen = ["", "Angehörige:"]
    for a in familie:
        teile = [f"{a['name']} ({angehoerige.rolle_wort(a)})"]
        if a["geburtstag"]:
            teile.append("Geburtstag " + stichtage.text_de(a["geburtstag"]))
        if a["verknuepfte_person_id"]:
            teile.append(f"verknüpft mit {a['verknuepft_name']} [{a['verknuepfte_person_id']}]")
        zeilen.append("- " + " · ".join(teile))
    return zeilen


def _stichtag_label(v: stichtage.Vorkommen) -> str:
    wort = stichtage.ARTEN[v.art]
    if v.art == "sonstiges" or wort.casefold() in v.bezeichnung.casefold():
        return v.bezeichnung
    return f"{v.bezeichnung} ({wort})"


def _stichtag_zeilen(k: Kontext, person_id: int) -> list[str]:
    vorkommen = stichtage.liste(k.con, k.nutzer_id, person_id, k.heute)
    if not vorkommen:
        return []
    zeilen = ["", "Stichtage:"]
    for v in vorkommen:
        zusatz = f" ({v.jahre_text})" if v.jahre_text else ""
        zeilen.append(f"- {_stichtag_label(v)} · {stichtage.text_de(v.datum)} · nächstes Mal "
                      f"{v.tage_text}{zusatz} [Stichtag {v.id}]")
    return zeilen


def _wer_wartet(k: Kontext, args: dict) -> list[str]:
    bindungen = faelligkeit.bindungen(k.con, k.nutzer_id, k.heute)
    vorlauf = stichtage.je_person(stichtage.im_vorlauf(k.con, k.nutzer_id, k.heute))
    karten = faelligkeit.karten_nummern(bindungen, set(vorlauf))
    aktive = {p["id"]: p for p in personen.liste(k.con, k.nutzer_id)}
    namen = _tagnamen(k)
    grenze = _grenze(args, 30)
    gewaehlt = [args["karte"]] if args.get("karte") else list(faelligkeit.KARTEN)
    zeilen = [f"Stand: {_tag(k.heute)}"]
    for karte in gewaehlt:
        ids = sorted(karten[karte], key=lambda i: faelligkeit.sortierschluessel(
            bindungen[i], aktive[i]["name"]))
        zeilen += ["", f"{KARTEN_TITEL[karte]} ({len(ids)}):"]
        if not ids:
            zeilen.append("- niemand")
        zeilen += [_zeile(k, aktive[i], bindungen[i], namen, vorlauf.get(i)) for i in ids[:grenze]]
        if len(ids) > grenze:
            zeilen.append(f"… und {len(ids) - grenze} weitere.")
    return zeilen


def _diese_woche(k: Kontext, args: dict) -> list[str]:
    bindungen = faelligkeit.bindungen(k.con, k.nutzer_id, k.heute)
    aktive = {p["id"]: p for p in personen.liste(k.con, k.nutzer_id)}
    namen = _tagnamen(k)
    bald = sorted((i for i, b in bindungen.items() if b.zustand == faelligkeit.BALD),
                  key=lambda i: faelligkeit.sortierschluessel(bindungen[i], aktive[i]["name"]))
    vorkommen = stichtage.im_vorlauf(k.con, k.nutzer_id, k.heute)
    zeilen = [f"Stand: {_tag(k.heute)}", "",
              f"Bald fällig, in den nächsten {faelligkeit.BALD_TAGE} Tagen ({len(bald)}):"]
    zeilen += [_zeile(k, aktive[i], bindungen[i], namen) for i in bald] or ["- niemand"]
    zeilen += ["", f"Stichtage im Vorlauf ({len(vorkommen)}):"]
    for v in vorkommen:
        zusatz = f" ({v.jahre_text})" if v.jahre_text else ""
        zeilen.append(f"- {v.plakette_text} · {v.person_name} [{v.person_id}] · "
                      f"{stichtage.text_de(v.datum)}{zusatz}")
    if not vorkommen:
        zeilen.append("- keiner")
    return zeilen


def _tags(k: Kontext, args: dict) -> list[str]:
    tags = personen.tags_mit_zaehlern(k.con, k.nutzer_id)
    if not tags:
        return ["Es gibt noch keine Tags."]
    return ["Tags (Zahl der aktiven Personen):",
            *[f"- {t['name']} ({t['anzahl']})" for t in tags]]


# -------------------------------------------------------------- Schreiben

def _text_arg(args: dict, name: str) -> str | None:
    wert = args.get(name)
    return None if wert is None else str(wert)


def _tagnamen_pruefen(args: dict) -> list[str]:
    """Die Tag-Namen der Eingabe, geprueft und ohne Doppelte (Gross-/Kleinschreibung egal)."""
    roh = args.get("tags") or []
    if not all(isinstance(t, str) for t in roh):
        raise Meldung("tags ist eine Liste von Namen.")
    namen: dict[str, str] = {}
    for t in roh:
        sauber = personen.tag_name_pruefen(t)
        namen.setdefault(sauber.casefold(), sauber)
    return list(namen.values())


def _person_anlegen(k: Kontext, args: dict) -> list[str]:
    name = (_text_arg(args, "name") or "").strip()
    tag_namen = _tagnamen_pruefen(args)
    grob = args.get("letzter_touchpoint")
    if grob is not None and grob not in personen.GROBER_KONTAKT:
        raise EingabeFehler("Unbekannte Angabe zum letzten Touchpoint.")
    gleich = [p for p in personen.liste(k.con, k.nutzer_id)
              if name and p["name"].casefold() == name.casefold()]
    if gleich and not args.get("trotzdem"):
        raise Meldung(
            "Es gibt schon eine Person mit diesem Namen: "
            + "; ".join(_kurz(p) + (f" · {p['firma']}" if p["firma"] else "") for p in gleich)
            + ". Ist es dieselbe, nimm ihre Nummer. Soll trotzdem eine zweite angelegt werden, "
              "ruf das Werkzeug mit trotzdem=true auf.")
    felder = {f: _text_arg(args, f) for f in
              ("firma", "rolle", "telefon", "email", "ort", "herkunft", "profilnotiz")}
    person_id = personen.anlegen(k.con, k.nutzer_id, name, **felder)
    vorher = {t["name"].casefold() for t in personen.tags_mit_zaehlern(k.con, k.nutzer_id)}
    neue = [t for t in tag_namen if t.casefold() not in vorher]
    if tag_namen:
        personen.tags_setzen(k.con, k.nutzer_id, person_id,
                             {personen.tag_finden_oder_anlegen(k.con, k.nutzer_id, t)
                              for t in tag_namen})
    if grob is not None:
        kontakte.schaetzung_eintragen(k.con, k.nutzer_id, person_id, grob)
    p = personen.laden(k.con, k.nutzer_id, person_id)
    b = faelligkeit.bindungen(k.con, k.nutzer_id, k.heute, person_id=person_id)[person_id]
    zeilen = [f"Person angelegt: {_kurz(p)}"]
    zeilen += [f"{b_}: {w}" for b_, w in (("Firma", p["firma"]), ("Rolle", p["rolle"]),
                                         ("Telefon", p["telefon"]), ("E-Mail", p["email"]),
                                         ("Ort", p["ort"]), ("Herkunft", p["herkunft"])) if w]
    if p["profilnotiz"]:
        zeilen += ["Profilnotiz:", _eingerueckt(p["profilnotiz"])]
    if tag_namen:
        zeilen.append("Tags: " + ", ".join(tag_namen))
    if neue:
        zeilen.append("Neu angelegte Tags: " + ", ".join(neue)
                      + ". (Gab es noch nicht; prüfe die Schreibweise mit dem Werkzeug tags.)")
    if grob is not None:
        zeilen.append("Letzter Touchpoint geschätzt: " + {
            "diesen_monat": "diesen Monat", "vor_monaten": "vor ein paar Monaten",
            "ueber_ein_jahr": "vor über einem Jahr"}[grob] + ".")
    zeilen.append("Zustand: " + _zustand(k, b))
    return zeilen


def _art_normalisieren(wert: object) -> str:
    """„E-Mail“ wie in der Oberflaeche geschrieben wird `email`; gueltig prueft die Seite."""
    return str(wert or "").strip().casefold().replace("-", "")


def _datum_arg(k: Kontext, wert: object) -> str:
    """„heute“ und „gestern“ sind keine Eingabe der Seite, aber eine, die ein Modell oft meint."""
    text = str(wert or "").strip()
    if not text or text.casefold() == "heute":
        return k.heute.isoformat()
    if text.casefold() == "gestern":
        return (k.heute - dt.timedelta(days=1)).isoformat()
    return text


def _touchpoint_eintragen(k: Kontext, args: dict) -> list[str]:
    p = _person(k, args["person"])
    art = _art_normalisieren(args["art"])
    tag = _datum_arg(k, args.get("datum"))
    notiz = (_text_arg(args, "notiz") or "").strip() or None
    for t in kontakte.liste(k.con, k.nutzer_id, p["id"]):
        if (t["datum"], t["art"], t["notiz"]) == (tag, art, notiz):
            raise Meldung(f"Genau dieser Touchpoint steht schon bei {_kurz(p)} "
                          f"[Touchpoint {t['id']}]. Nichts eingetragen.")
    kontakt_id = kontakte.eintragen(k.con, k.nutzer_id, p["id"], datum=tag, art=art, notiz=notiz)
    b = faelligkeit.bindungen(k.con, k.nutzer_id, k.heute, person_id=p["id"])[p["id"]]
    zeilen = [(f"Touchpoint eingetragen: {kontakte.ARTEN[art]} mit {_kurz(p)} am {tag} "
              f"[Touchpoint {kontakt_id}].")]
    if notiz:
        zeilen += ["Notiz:", _eingerueckt(notiz)]
    if p["naechster_termin"]:
        zeilen.append(f"Der nächste Termin ({p['naechster_termin']}) ist damit gelöscht.")
    zeilen.append("Zustand jetzt: " + _zustand(k, b))
    if b.faellig_am:
        zeilen.append(f"Fällig am: {_tag(b.faellig_am)}")
    return zeilen


def _profilnotiz_setzen(k: Kontext, args: dict) -> list[str]:
    p = _person(k, args["person"])
    text = (_text_arg(args, "text") or "").strip()
    alt = p["profilnotiz"] or ""
    if args.get("anhaengen"):
        if not text:
            raise Meldung("Es gibt nichts anzuhängen: text ist leer.")
        neu = f"{alt}\n{text}" if alt else text
    else:
        neu = text
    personen.aendern(k.con, k.nutzer_id, p["id"], profilnotiz=neu)
    zeilen = [f"Profilnotiz von {_kurz(p)} " + ("ergänzt." if args.get("anhaengen") and alt
                                                else "gesetzt." if neu else "geleert.")]
    if alt and not args.get("anhaengen"):
        zeilen += ["Vorher stand dort:", _eingerueckt(alt)]
    if neu:
        zeilen += ["Jetzt:", _eingerueckt(neu)]
    return zeilen


def _stichtag_anlegen(k: Kontext, args: dict) -> list[str]:
    p = _person(k, args["person"])
    art = str(args["art"]).strip()
    datum = str(args["datum"]).strip()
    bezeichnung = _text_arg(args, "bezeichnung")
    for v in stichtage.liste(k.con, k.nutzer_id, p["id"], k.heute):
        if v.art == art and v.datum == datum and (
                not (bezeichnung or "").strip()
                or v.bezeichnung.casefold() == bezeichnung.strip().casefold()):
            raise Meldung(f"Diesen Stichtag gibt es bei {_kurz(p)} schon "
                          f"[Stichtag {v.id}]. Nichts angelegt.")
    stichtag_id = stichtage.anlegen(k.con, k.nutzer_id, p["id"], bezeichnung=bezeichnung,
                                    art=art, datum=datum, vorlauf_tage=args.get("vorlauf_tage"))
    v = stichtage.vorkommen_von(k.con, k.nutzer_id, stichtag_id, k.heute)
    zusatz = f", {v.jahre_text}" if v.jahre_text else ""
    return [(f"Stichtag angelegt: {_stichtag_label(v)} · {stichtage.text_de(v.datum)} "
            f"bei {_kurz(p)} [Stichtag {stichtag_id}]."),
            f"Nächstes Mal {v.tage_text}{zusatz}; er erscheint {v.vorlauf} Tage vorher."]


# --------------------------------------------------------------- Register

_PERSON = ("integer", "string")
_PERSON_BESCHREIBUNG = ("Die Nummer der Person (die Zahl in eckigen Klammern aus einer Antwort) "
                        "oder ihr Name. Ein Name muss genau eine Person treffen, sonst wird er "
                        "mit den Kandidaten abgelehnt.")

WERKZEUGE: dict[str, Werkzeug] = {w.name: w for w in (
    Werkzeug(
        "personen_suchen",
        "Sucht Personen. Der Text trifft Name, Firma, Ort und Tags (Groß-/Kleinschreibung egal). "
        "Liefert je Person Nummer, Name, Firma, Tags, Zustand (wie die Plakette der App) und "
        "den letzten Touchpoint. Ohne Text: alle, nach Name. Ändert nichts.",
        _personen_suchen,
        {"text": ("string", "Suchtext, Teil von Name, Firma, Ort oder Tag.", False),
         "tag": ("string", "Nur Personen mit genau diesem Tag (Name wie in `tags`).", False),
         "ohne_touchpoint": ("boolean", ("Nur Personen, bei denen noch kein Touchpoint "
                                        "eingetragen ist."), False),
         "archiv": ("boolean", "Im Archiv suchen statt bei den aktiven Personen.", False),
         "limit": ("integer", (f"Wie viele Zeilen, höchstens {LISTE_HOECHSTENS} "
                              f"(Standard {LISTE_VORGABE})."), False)}),
    Werkzeug(
        "person",
        "Alles, was die Personenseite zeigt: Felder, Tags, Profilnotiz, Zustand, Intervall, "
        "Nächster Termin, Fällig am, Zuletzt besprochen (die Touchpoints mit Notizen, jüngster "
        "zuerst), Angehörige und Stichtage. Ändert nichts.",
        _person_seite,
        {"person": (_PERSON, _PERSON_BESCHREIBUNG, True),
         "touchpoints": ("integer", (f"Wie viele Touchpoints aus „Zuletzt besprochen“, "
                                    f"Standard {VERLAUF_VORGABE}."), False)}),
    Werkzeug(
        "wer_wartet",
        "Die drei Karten der App mit Namen, sortiert wie dort (erkaltet zuerst, dann nach "
        "Fälligkeit): Braucht Aufmerksamkeit (überfällig und erkaltet), Erkaltet, Diese Woche "
        "(bald fällig oder Stichtag im Vorlauf). Ändert nichts.",
        _wer_wartet,
        {"karte": ("string", "Nur diese Karte.", False),
         "limit": ("integer", "Wie viele Zeilen je Karte, Standard 30.", False)},
        {"karte": {"enum": list(faelligkeit.KARTEN)}}),
    Werkzeug(
        "diese_woche",
        "Wer in den nächsten sieben Tagen fällig wird und welche Stichtage im Vorlauf liegen "
        "(Geburtstage, Jahrestage). Die Grundlage der wöchentlichen Durchsicht. Ändert nichts.",
        _diese_woche),
    Werkzeug(
        "tags",
        "Die Tags des Nutzers mit der Zahl ihrer aktiven Personen, in der Reihenfolge der "
        "Seitenleiste. Ändert nichts.",
        _tags),
    Werkzeug(
        "person_anlegen",
        "SCHREIBT: legt eine neue Person an (wie „Person hinzufügen“ und „Mehrere hinzufügen“). "
        "Nur der Name ist Pflicht. Tags gibst du mit Namen an; einen Tag, den es noch nicht "
        "gibt, legt das Werkzeug an und sagt es in der Antwort – schau vorher mit `tags` nach, "
        "um die vorhandene Schreibweise zu nehmen. `letzter_touchpoint` setzt eine grobe "
        "Schätzung, wenn der Nutzer nur ungefähr weiß, wann er die Person zuletzt gesprochen hat; "
        "ohne die Angabe ist der Zustand „unbekannt“. Gibt es schon eine Person mit diesem "
        "Namen, wird abgelehnt (außer mit trotzdem=true).",
        _person_anlegen,
        {"name": ("string", "Der Name der Person.", True),
         "firma": ("string", "Firma.", False),
         "rolle": ("string", "Rolle, z. B. Kollegin, Nachbar.", False),
         "telefon": ("string", "Telefonnummer.", False),
         "email": ("string", "E-Mail-Adresse.", False),
         "ort": ("string", "Wohnort.", False),
         "herkunft": ("string", "Wie und wo ihr euch kennengelernt habt.", False),
         "profilnotiz": ("string", "Was man über die Person wissen muss.", False),
         "tags": ("array", "Die Tags der Person, mit Namen.", False),
         "letzter_touchpoint": ("string", ("Grobe Angabe, wann ihr zuletzt gesprochen habt: "
                                          "diesen_monat, vor_monaten oder ueber_ein_jahr."),
                                False),
         "trotzdem": ("boolean", ("Auch anlegen, wenn es schon eine Person mit diesem Namen "
                                 "gibt."), False)},
        {"tags": {"items": {"type": "string"}},
         "letzter_touchpoint": {"enum": list(personen.GROBER_KONTAKT)}},
        schreibt=True),
    Werkzeug(
        "touchpoint_eintragen",
        "SCHREIBT: trägt einen Touchpoint ein (wie „Touchpoint eintragen“ in der App): ein "
        "Austausch mit einer Person an einem Datum, mit Art und Notiz. Er wird nie "
        "überschrieben, nur ergänzt. Ein Datum in der Zukunft wird abgelehnt, und der "
        "Nächste Termin der Person wird gelöscht. Die Notiz ist das, worüber ihr gesprochen "
        "habt – das, was der Nutzer vor dem nächsten Anruf liest; schreib sie in seinen Worten.",
        _touchpoint_eintragen,
        {"person": (_PERSON, _PERSON_BESCHREIBUNG, True),
         "art": ("string", "Wie ihr euch ausgetauscht habt.", True),
         "datum": ("string", ("Der Tag als YYYY-MM-DD, auch „heute“ oder „gestern“. "
                             "Standard heute."), False),
         "notiz": ("string", "Worüber ihr gesprochen habt.", False)},
        {"art": {"enum": list(kontakte.ARTEN)}},
        schreibt=True),
    Werkzeug(
        "profilnotiz_setzen",
        "SCHREIBT: setzt die Profilnotiz einer Person – den Freitext, der bleibt: wer sie ist, "
        "was sie mag, was man wissen muss. Ohne `anhaengen` ersetzt der Text die bisherige "
        "Notiz (die Antwort zeigt, was vorher dort stand); mit anhaengen=true kommt er in einer "
        "neuen Zeile dazu. Was in einem Gespräch besprochen wurde, gehört stattdessen in einen "
        "Touchpoint.",
        _profilnotiz_setzen,
        {"person": (_PERSON, _PERSON_BESCHREIBUNG, True),
         "text": ("string", "Der neue Text der Profilnotiz.", True),
         "anhaengen": ("boolean", "An die bisherige Notiz anhängen statt sie zu ersetzen.",
                       False)},
        schreibt=True),
    Werkzeug(
        "stichtag_anlegen",
        "SCHREIBT: legt einen Stichtag an einer Person an – einen jährlich wiederkehrenden Tag "
        "(Geburtstag, Jahrestag oder ein benannter Tag). Das Datum steht als YYYY-MM-DD mit "
        "Jahr oder als --MM-DD ohne Jahr. Er erscheint im Vorlauf vorher in der App, in der "
        "Tagesmeldung und im Kalender.",
        _stichtag_anlegen,
        {"person": (_PERSON, _PERSON_BESCHREIBUNG, True),
         "art": ("string", "Was für ein Stichtag es ist.", True),
         "datum": ("string", "YYYY-MM-DD, oder --MM-DD, wenn das Jahr nicht bekannt ist.", True),
         "bezeichnung": ("string", "Name des Tages; bei „sonstiges“ Pflicht, sonst die Art.",
                         False),
         "vorlauf_tage": ("integer", ("Wie viele Tage vorher er erscheint (0 bis 365); ohne "
                                     "Angabe gilt die Vorgabe des Nutzers."), False)},
        {"art": {"enum": list(stichtage.ARTEN)}},
        schreibt=True),
)}


# ----------------------------------------------------------------- Aufruf

_TYPEN = {"string": str, "integer": int, "boolean": bool, "array": list}


def _typ_passt(typ: str, wert: object) -> bool:
    if typ == "integer" and isinstance(wert, bool):
        return False
    return isinstance(wert, _TYPEN[typ])


def argumente_pruefen(werkzeug: Werkzeug, args: dict) -> None:
    """Pruefen gegen das angekuendigte Schema: ein Modell halt sich nicht immer daran."""
    unbekannt = sorted(set(args) - set(werkzeug.parameter))
    if unbekannt:
        raise Meldung(f"Unbekannte Parameter: {', '.join(unbekannt)}. "
                      f"Bekannt: {', '.join(werkzeug.parameter) or 'keine'}.")
    for name, (typ, _beschreibung, pflicht) in werkzeug.parameter.items():
        if args.get(name) is None:
            if pflicht:
                raise Meldung(f"Pflichtfeld fehlt: {name}.")
            continue
        typen = (typ,) if isinstance(typ, str) else typ
        if not any(_typ_passt(t, args[name]) for t in typen):
            raise Meldung(f"{name} muss vom Typ {' oder '.join(typen)} sein.")
        # Bei `art` hat die Seite einen eigenen Satz (kontakte, stichtage); der gilt hier auch.
        erlaubt = werkzeug.schema_zusatz.get(name, {}).get("enum")
        if erlaubt and name != "art" and args[name] not in erlaubt:
            raise Meldung(f"{name}: erlaubt sind {', '.join(erlaubt)}.")


def aufrufen(name: str, args: dict, nutzer: str | None = None) -> str:
    """Das Werkzeug ausfuehren und seine Antwort als Text geben.

    `Meldung` und `EingabeFehler` (beide `ValueError`) sind Saetze fuer das Modell -- die
    der Seite, wenn die Seite dieselbe Eingabe ablehnen wuerde. Eine Nummer, die nicht
    existiert oder einem anderen Nutzer gehoert, ist fuer die Funktionen nicht vorhanden.
    """
    werkzeug = WERKZEUGE[name]
    argumente_pruefen(werkzeug, args)
    with _kontext(nutzer) as k:
        try:
            zeilen = werkzeug.funktion(k, args)
        except NichtGefunden as fehler:
            raise Meldung(f"{fehler.args[0]} gibt es nicht.") from None
    return "\n".join(zeilen)


# ------------------------------------------------------------- Ressourcen

#: Das Glossar liegt neben dem Paket (im Quellordner); eine installierte Kopie hat es nicht.
GLOSSAR = Path(__file__).resolve().parents[2] / "CONTEXT.md"


def _glossar(nutzer: str | None) -> str:
    try:
        return GLOSSAR.read_text(encoding="utf-8")
    except OSError:
        raise Meldung("Das Glossar (CONTEXT.md) liegt nicht neben dem installierten Paket.") \
            from None


def _heute(nutzer: str | None) -> str:
    with _kontext(nutzer) as k:
        meldung = tagesmeldung.bauen(k.con, k.nutzer_id, k.heute)
    kopf = f"Tagesmeldung für {_tag(k.heute)}"
    if meldung is None:
        return f"{kopf}: Heute ist nichts zu sagen. Niemand wartet, kein Stichtag im Vorlauf."
    return "\n".join([f"{kopf}:", *meldung.zeilen])


RESSOURCEN: dict[str, Ressource] = {r.uri: r for r in (
    Ressource("bindung://glossar", "Glossar",
              "Die Begriffe der App (CONTEXT.md). Benutze diese Wörter: Touchpoint, nicht "
              "Kontakt.", _glossar),
    Ressource("bindung://heute", "Tagesmeldung heute",
              "Der Text der Tagesmeldung für heute: wer wartet, welche Stichtage nah sind.",
              _heute),
)}


def lesen(uri: str, nutzer: str | None = None) -> str:
    return RESSOURCEN[uri].lesen(nutzer)
