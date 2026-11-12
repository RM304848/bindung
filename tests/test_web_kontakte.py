"""Touchpoint eintragen, Zuletzt besprochen, Karten: die Teile, die HTMX tauscht.

Die Uhr steht auf Mittwoch, 11. November 2026 (Berlin: 13:00).
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from bindung import auth, kontakte, personen

from .conftest import PASSWORT

HEUTE = dt.date(2026, 11, 11)


def hx(aktuell: str = "/") -> dict:
    return {"HX-Request": "true", "HX-Current-URL": f"http://testserver{aktuell}"}


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.UTC))


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


@pytest.fixture
def fremder(con) -> int:
    return auth.nutzer_anlegen(con, "Anderer", PASSWORT)


def vor(tage: int) -> str:
    return (HEUTE - dt.timedelta(days=tage)).isoformat()


def person_mit(con, nid, name, her=None, **felder) -> int:
    """Eine Person; `her` Tage seit dem letzten Kontakt (Anruf), oder keiner."""
    pid = personen.anlegen(con, nid, name, **felder)
    if her is not None:
        con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) "
                    "VALUES (?, ?, ?, 'anruf')", (nid, pid, vor(her)))
        con.commit()
    return pid


@pytest.fixture
def fuenf(con, nid) -> dict[str, int]:
    """Je ein Zustand: ueberfaellig, erkaltet, bald, ok, unbekannt (Intervall 56)."""
    return {"ueber": person_mit(con, nid, "Anna Beispiel", 70),
            "kalt": person_mit(con, nid, "Ben Muster", 150),
            "bald": person_mit(con, nid, "Cem Probe", 50),
            "ok": person_mit(con, nid, "Dora Test", 5),
            "neu": person_mit(con, nid, "Emil Neu")}


def karten(text: str) -> dict[str, int]:
    return {name: int(zahl) for zahl, name in re.findall(
        r'karte-zahl">(\d+)</span>\s*<span class="karte-name">([^<]+)<', text)}


def zeile(text: str, name: str) -> str:
    """Das <li> dieser Person in der Liste, die Leerzeichen zusammengezogen."""
    for li in re.findall(r'<li class="zeilenpunkt">.*?</li>', text, flags=re.S):
        if f">{name}<" in li:
            return re.sub(r"\s+", " ", li)
    raise AssertionError(f"{name} steht nicht in der Liste")


def reihenfolge(text: str) -> list[str]:
    return re.findall(r'<span class="zeile-name">([^<]+)<', text)


# ------------------------------------------------------------ Karten, Zeilen

def test_karten_zaehlen_die_aktiven_personen(angemeldet, fuenf):
    assert karten(angemeldet.get("/").text) == {
        "Braucht Aufmerksamkeit": 2, "Erkaltet": 1, "Diese Woche": 1}


def test_karten_zaehlen_weder_archivierte_noch_unbekannte(angemeldet, con, nid, fuenf):
    personen.archivieren(con, nid, fuenf["kalt"])
    assert karten(angemeldet.get("/").text) == {
        "Braucht Aufmerksamkeit": 1, "Erkaltet": 0, "Diese Woche": 1}


def test_zeile_zeigt_die_plakette_des_zustands(angemeldet, fuenf):
    text = angemeldet.get("/").text
    assert "überfällig seit 14 Tagen" in zeile(text, "Anna Beispiel")
    assert "plakette-ueberfaellig" in zeile(text, "Anna Beispiel")
    assert ">erkaltet<" in zeile(text, "Ben Muster")
    assert "fällig in 6 Tagen" in zeile(text, "Cem Probe")
    assert "vor 5 Tagen" in zeile(text, "Dora Test")
    assert "noch kein Touchpoint" in zeile(text, "Emil Neu")


def test_die_plakette_im_archiv_entfaellt(angemeldet, con, nid, fuenf):
    personen.archivieren(con, nid, fuenf["kalt"])
    text = angemeldet.get("/?filter=archiv").text
    assert "Ben Muster" in text and "plakette" not in zeile(text, "Ben Muster")


def test_zeile_zeigt_die_notiz_des_juengsten_kontakts(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", profilnotiz="Mag Tee.")
    kontakte.eintragen(con, nid, pid, datum="2026-10-01", art="anruf", notiz="Alte Sache.")
    kontakte.eintragen(con, nid, pid, datum="2026-11-02", art="anruf",
                       notiz="\nZieht um.\nZweite Zeile")
    kontakte.eintragen(con, nid, pid, datum="2026-11-05", art="anruf")  # ohne Notiz
    text = zeile(angemeldet.get("/").text, "Anna Beispiel")
    assert ">Zieht um.<" in text and "Zweite Zeile" not in text and "Alte Sache" not in text
    assert "Mag Tee." not in text


def test_profilnotiz_nur_wo_es_keinen_echten_kontakt_gibt(angemeldet, con, nid):
    person_mit(con, nid, "Anna Beispiel", profilnotiz="Mag Tee.")
    ben = person_mit(con, nid, "Ben Muster", profilnotiz="Spielt Cello.")
    kontakte.eintragen(con, nid, ben, datum="2026-11-02", art="anruf")  # echter Kontakt ohne Notiz
    cem = personen.mehrere_hinzufuegen(con, nid, "Cem Probe", grober_kontakt="vor_monaten")[0]
    personen.aendern(con, nid, cem, profilnotiz="Fährt Rad.")
    text = angemeldet.get("/").text
    assert ">Mag Tee.<" in zeile(text, "Anna Beispiel")
    assert "Spielt Cello." not in zeile(text, "Ben Muster")
    assert ">Fährt Rad.<" in zeile(text, "Cem Probe")  # eine Schätzung ist kein Gespräch


def test_der_kreis_ist_der_knopf_kontakt_eintragen(angemeldet, fuenf):
    text = zeile(angemeldet.get("/").text, "Anna Beispiel")
    assert f'hx-get="/personen/{fuenf["ueber"]}/kontakt/neu"' in text
    assert 'aria-label="Touchpoint eintragen: Anna Beispiel"' in text
    assert re.search(r"<button[^>]*kreis-knopf", text)
    assert "<a " in text  # die Zeile selbst bleibt ein Link auf die Person
    assert text.index("kreis-knopf") < text.index('<a class="zeile')  # Knopf neben, nicht im Link


# ----------------------------------------------------------- Blatt oeffnen

def test_blatt_oeffnen(angemeldet, fuenf):
    antwort = angemeldet.get(f"/personen/{fuenf['ueber']}/kontakt/neu", headers=hx())
    assert antwort.status_code == 200
    text = antwort.text
    assert 'id="personenseite"' in text and 'role="dialog"' in text
    assert f'hx-post="/personen/{fuenf["ueber"]}/kontakte"' in text
    for art in ("Anruf", "Nachricht", "E-Mail", "Treffen", "Sonstiges"):
        assert f"<span>{art}</span>" in text
    assert re.search(r'name="art" value="anruf" checked', text)
    assert 'name="datum" value="2026-11-11"' in text and 'max="2026-11-11"' in text
    assert re.search(r'<textarea[^>]*data-diktat', text)
    assert antwort.headers["hx-push-url"] == f"/?person={fuenf['ueber']}"
    assert json.loads(antwort.headers["hx-trigger"]) == {"spalte": "person"}
    assert "zeile-ausgewaehlt" in text  # die Person ist ausgewaehlt


def test_blatt_oeffnen_behaelt_den_filter(angemeldet, fuenf):
    antwort = angemeldet.get(f"/personen/{fuenf['kalt']}/kontakt/neu",
                             headers=hx("/?karte=erkaltet"))
    assert antwort.headers["hx-push-url"] == f"/?karte=erkaltet&person={fuenf['kalt']}"


def test_blatt_ohne_htmx_leitet_auf_die_seite(angemeldet, fuenf):
    antwort = angemeldet.get(f"/personen/{fuenf['ueber']}/kontakt/neu")
    assert antwort.status_code == 303
    assert antwort.headers["location"] == f"/?person={fuenf['ueber']}"


def test_personenseite_hat_den_knopf_kontakt_eintragen(angemeldet, fuenf):
    text = angemeldet.get(f"/?person={fuenf['ueber']}").text
    assert re.search(r'<button[^>]*hx-get="/personen/\d+/kontakt/neu"[^>]*>Touchpoint eintragen<',
                     text)
    assert 'role="dialog"' not in text  # das Blatt ist nur nach Klick da


def test_archivierte_person_hat_keinen_knopf(angemeldet, con, nid, fuenf):
    personen.archivieren(con, nid, fuenf["ok"])
    text = angemeldet.get(f"/?person={fuenf['ok']}").text
    assert ">Touchpoint eintragen<" not in text and "Im Archiv: keine Erinnerung." in text


# -------------------------------------------------------------- Eintragen

def test_eintragen_speichert_und_zieht_alles_nach(angemeldet, con, nid, fuenf):
    antwort = angemeldet.post(
        f"/personen/{fuenf['ueber']}/kontakte", headers=hx(),
        data={"art": "treffen", "datum": "2026-11-11", "notiz": "Kaffee am Markt."})
    assert antwort.status_code == 200
    text = antwort.text
    kontakt = kontakte.liste(con, nid, fuenf["ueber"])[0]
    assert (kontakt["art"], kontakt["datum"], kontakt["notiz"]) == (
        "treffen", "2026-11-11", "Kaffee am Markt.")
    # Personenseite (Hauptziel) ohne Blatt, mit dem neuen Eintrag
    assert text.lstrip().startswith('<section id="personenseite"')
    assert 'role="dialog"' not in text
    assert "Kaffee am Markt." in text and "Treffen" in text
    # Zeile, Karten und Seitenleiste per OOB
    assert 'id="karten"' in text and 'id="listenkoerper"' in text and 'id="seitenleiste"' in text
    assert text.count('hx-swap-oob="true"') >= 3
    assert karten(text) == {"Braucht Aufmerksamkeit": 1, "Erkaltet": 1, "Diese Woche": 1}
    assert "heute" in zeile(text, "Anna Beispiel")
    assert "überfällig" not in zeile(text, "Anna Beispiel")
    assert antwort.headers["hx-replace-url"] == f"/?person={fuenf['ueber']}"


def test_der_erste_kontakt_zaehlt_die_seitenleiste_herunter(angemeldet, fuenf):
    vorher = angemeldet.get("/").text
    assert re.search(r"Noch kein Touchpoint</span><span class=\"zahl\">1<", vorher)
    antwort = angemeldet.post(f"/personen/{fuenf['neu']}/kontakte", headers=hx(),
                              data={"art": "anruf", "datum": "2026-11-10"})
    assert re.search(r"Noch kein Touchpoint</span><span class=\"zahl\">0<", antwort.text)
    assert "vor 1 Tag" not in antwort.text and "gestern" in zeile(antwort.text, "Emil Neu")


def test_eintragen_loescht_den_naechsten_termin(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", 10, naechster_termin="2026-12-24")
    angemeldet.post(f"/personen/{pid}/kontakte", headers=hx(),
                    data={"art": "anruf", "datum": "2026-11-11"})
    assert personen.laden(con, nid, pid)["naechster_termin"] is None


def test_eintragen_behaelt_karte_und_person_in_der_adresse(angemeldet, fuenf):
    antwort = angemeldet.post(
        f"/personen/{fuenf['kalt']}/kontakte",
        headers=hx(f"/?karte=erkaltet&person={fuenf['kalt']}"),
        data={"art": "anruf", "datum": "2026-11-11"})
    assert antwort.headers["hx-replace-url"] == f"/?karte=erkaltet&person={fuenf['kalt']}"
    # Ben ist nicht mehr erkaltet und verschwindet aus der gefilterten Liste
    liste = re.search(r'<div id="listenkoerper".*', antwort.text, flags=re.S).group(0)
    assert "Ben Muster" not in liste and "Keine Bindung ist erkaltet." in liste


def test_zukunft_wird_abgelehnt_und_das_blatt_bleibt_offen(angemeldet, con, nid, fuenf):
    antwort = angemeldet.post(
        f"/personen/{fuenf['ueber']}/kontakte", headers=hx(),
        data={"art": "email", "datum": "2026-11-12", "notiz": "Noch nicht passiert."})
    assert antwort.status_code == 422
    assert "liegt in der Zukunft" in antwort.text
    assert 'role="dialog"' in antwort.text
    assert re.search(r'name="art" value="email" checked', antwort.text)
    assert 'value="2026-11-12"' in antwort.text and "Noch nicht passiert." in antwort.text
    assert kontakte.liste(con, nid, fuenf["ueber"])[0]["datum"] == vor(70)  # nichts neu


@pytest.mark.parametrize("eingabe", [{"art": "", "datum": "2026-11-10"},
                                   {"art": "anruf", "datum": ""},
                                   {"art": "schaetzung", "datum": "2026-11-10"},
                                   {}])
def test_ungueltige_eingaben_geben_422(angemeldet, con, nid, fuenf, eingabe):
    antwort = angemeldet.post(f"/personen/{fuenf['neu']}/kontakte", headers=hx(), data=eingabe)
    assert antwort.status_code == 422
    assert kontakte.liste(con, nid, fuenf["neu"]) == []


# ---------------------------------------------------- Zuletzt besprochen

def test_zuletzt_besprochen_juengster_zuerst_mit_schaetzung(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    kontakte.eintragen(con, nid, pid, datum="2026-09-01", art="anruf", notiz="Erste Notiz.")
    kontakte.eintragen(con, nid, pid, datum="2026-11-01", art="nachricht", notiz="Zweite Notiz.")
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art) "
                "VALUES (?, ?, '2026-07-14', 'schaetzung')", (nid, pid))
    con.commit()
    text = angemeldet.get(f"/?person={pid}").text
    verlauf = re.search(r'<section id="verlauf".*?</section>', text, flags=re.S).group(0)
    assert (verlauf.index("Zweite Notiz.") < verlauf.index("Erste Notiz.")
            < verlauf.index("Schätzung"))
    assert "01.11.2026" in verlauf and "Nachricht" in verlauf and "vor 1 Woche" not in verlauf
    assert "vor 10 Tagen" in verlauf
    # die Schaetzung hat keine Notiz
    schaetzung = re.findall(r"<li class=\"verlauf-eintrag\".*?</li>", verlauf, flags=re.S)[-1]
    assert "verlauf-notiz" not in schaetzung


def test_zuletzt_besprochen_leer(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    assert "Noch nichts eingetragen." in angemeldet.get(f"/?person={pid}").text


def test_eintrag_bearbeiten_formular_und_abbrechen(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    kid = kontakte.eintragen(con, nid, pid, datum="2026-11-01", art="treffen", notiz="Mit Kuchen.")
    form = angemeldet.get(f"/kontakte/{kid}/bearbeiten", headers=hx())
    assert form.status_code == 200
    assert f'id="kontakt-{kid}"' in form.text and f'hx-post="/kontakte/{kid}"' in form.text
    assert re.search(r'<option value="treffen" selected>', form.text) and "Mit Kuchen." in form.text
    assert re.search(r"<textarea[^>]*data-diktat", form.text)
    zurueck = angemeldet.get(f"/kontakte/{kid}", headers=hx())
    assert f'id="kontakt-{kid}"' in zurueck.text and "Mit Kuchen." in zurueck.text
    assert "<form" not in zurueck.text


def test_eintrag_bearbeiten_einer_schaetzung_nur_datum(angemeldet, con, nid):
    pid = personen.mehrere_hinzufuegen(con, nid, "Anna Beispiel", grober_kontakt="vor_monaten")[0]
    kid = kontakte.liste(con, nid, pid)[0]["id"]
    form = angemeldet.get(f"/kontakte/{kid}/bearbeiten", headers=hx()).text
    assert 'name="datum"' in form and 'name="notiz"' not in form and 'name="art"' not in form
    assert "Geschätztes Datum" in form


def test_eintrag_speichern_zieht_zustand_nach(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    kid = kontakte.eintragen(con, nid, pid, datum="2026-11-10", art="anruf", notiz="Alt.")
    antwort = angemeldet.post(f"/kontakte/{kid}", headers=hx(f"/?person={pid}"),
                              data={"datum": "2026-08-01", "art": "treffen", "notiz": "Neu."})
    assert antwort.status_code == 200
    text = antwort.text
    zeilen = kontakte.liste(con, nid, pid)
    assert (zeilen[0]["datum"], zeilen[0]["art"], zeilen[0]["notiz"]) == (
        "2026-08-01", "treffen", "Neu.")
    assert text.lstrip().startswith('<section id="verlauf"')
    assert 'id="faelligkeit"' in text and 'id="listenkoerper"' in text and 'id="karten"' in text
    assert "überfällig seit 46 Tagen" in zeile(text, "Anna Beispiel")  # faellig seit 26.09.
    assert "Neu." in text and "Alt." not in text


def test_eintrag_speichern_kann_die_notiz_leeren(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    kid = kontakte.eintragen(con, nid, pid, datum="2026-11-10", art="anruf", notiz="Weg damit.")
    angemeldet.post(f"/kontakte/{kid}", headers=hx(),
                    data={"datum": "2026-11-10", "art": "anruf", "notiz": ""})
    assert kontakte.laden(con, nid, kid)["notiz"] is None


def test_eintrag_speichern_zukunft_gibt_422_in_der_zeile(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel")
    kid = kontakte.eintragen(con, nid, pid, datum="2026-11-10", art="anruf", notiz="Alt.")
    antwort = angemeldet.post(f"/kontakte/{kid}", headers=hx(),
                              data={"datum": "2027-01-01", "art": "anruf", "notiz": "Neu."})
    assert antwort.status_code == 422
    assert antwort.headers["hx-retarget"] == f"#kontakt-{kid}"
    assert antwort.headers["hx-reswap"] == "outerHTML"
    assert "liegt in der Zukunft" in antwort.text and "Neu." in antwort.text
    assert kontakte.laden(con, nid, kid)["datum"] == "2026-11-10"


def test_eintrag_loeschen_mit_bestaetigung_und_nachzug(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", 5)
    kid = kontakte.liste(con, nid, pid)[0]["id"]
    seite = angemeldet.get(f"/?person={pid}").text
    assert re.search(
        rf'hx-post="/kontakte/{kid}/loeschen"[^>]*hx-confirm="Den Touchpoint vom ', seite)
    antwort = angemeldet.post(f"/kontakte/{kid}/loeschen", headers=hx(f"/?person={pid}"))
    assert antwort.status_code == 200
    assert kontakte.liste(con, nid, pid) == []
    assert "Noch nichts eingetragen." in antwort.text
    assert "Zustand" in antwort.text and "unbekannt" in antwort.text
    assert re.search(r"Noch kein Touchpoint</span><span class=\"zahl\">1<", antwort.text)
    assert "noch kein Touchpoint" in zeile(antwort.text, "Anna Beispiel")


# ------------------------------------------------------------ Faelligkeit

def test_personenseite_zeigt_zustand_und_faellig_am(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", 20)
    text = angemeldet.get(f"/?person={pid}").text
    block = re.search(r'<div id="faelligkeit".*?</div>', text, flags=re.S).group(0)
    assert "Zustand" in block and ">ok<" in block
    assert "22.10.2026" in block and "vor 2 Wochen" in block
    assert "17.12.2026" in block and "Intervall 56 Tage" in block
    assert "nächste Termin ersetzt das Intervall ein Mal" in block


def test_naechster_termin_ersetzt_und_wird_genannt(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", 20)
    antwort = angemeldet.post(f"/personen/{pid}", headers=hx(f"/?person={pid}"),
                              data={"naechster_termin": "2026-11-15"})
    assert antwort.status_code == 200
    block = re.search(r'<div id="faelligkeit".*?</div>', antwort.text, flags=re.S).group(0)
    assert "15.11.2026" in block and "(nächster Termin)" in block and "bald fällig" in block
    assert "fällig in 4 Tagen" in zeile(antwort.text, "Anna Beispiel")


def test_intervall_aendern_zieht_den_zustand_nach(angemeldet, con, nid):
    pid = person_mit(con, nid, "Anna Beispiel", 20)
    antwort = angemeldet.post(f"/personen/{pid}", headers=hx(f"/?person={pid}"),
                              data={"intervall_tage": "14"})
    assert "überfällig" in antwort.text and "Intervall 14 Tage" in antwort.text
    assert karten(antwort.text)["Braucht Aufmerksamkeit"] == 1


def test_noch_kein_kontakt_in_der_seitenleiste_ist_der_zustand_unbekannt(angemeldet, fuenf):
    text = angemeldet.get("/?filter=ohne_kontakt").text
    assert reihenfolge(text) == ["Emil Neu"]


# ---------------------------------------------------------- Karten filtern

def test_karte_filtert_und_sortiert(angemeldet, con, nid, fuenf):
    zwei = person_mit(con, nid, "Zora Probe", 200)  # erkaltet, laenger faellig als Ben
    text = angemeldet.get("/?karte=aufmerksamkeit").text
    # erkaltet zuerst (nach Faelligkeit: Zora vor Ben), dann ueberfaellig (Anna)
    assert reihenfolge(text) == ["Zora Probe", "Ben Muster", "Anna Beispiel"]
    assert reihenfolge(angemeldet.get("/?karte=erkaltet").text) == ["Zora Probe", "Ben Muster"]
    assert reihenfolge(angemeldet.get("/?karte=woche").text) == ["Cem Probe"]
    assert zwei


def test_ohne_karte_bleibt_die_liste_nach_name(angemeldet, fuenf):
    assert reihenfolge(angemeldet.get("/").text) == [
        "Anna Beispiel", "Ben Muster", "Cem Probe", "Dora Test", "Emil Neu"]


def test_karte_im_teil_liste_mit_adresse_und_auswahl(angemeldet, fuenf):
    antwort = angemeldet.get("/liste?karte=erkaltet", headers=hx())
    assert antwort.headers["hx-push-url"] == "/?karte=erkaltet"
    assert json.loads(antwort.headers["hx-trigger"]) == {"spalte": "liste"}
    text = antwort.text
    assert re.search(r'class="karte karte-erkaltet karte-aktiv"', text)
    assert text.count("karte-aktiv") == 1 and 'aria-current="true"' in text
    assert reihenfolge(text) == ["Ben Muster"]


def test_die_aktive_karte_fuehrt_beim_zweiten_klick_zurueck(angemeldet, fuenf):
    text = angemeldet.get("/?karte=erkaltet").text
    aktiv = re.search(r'<a class="karte karte-erkaltet karte-aktiv" href="([^"]*)" '
                      r'hx-get="([^"]*)"', text)
    assert aktiv.groups() == ("/", "/liste")
    andere = re.search(r'<a class="karte karte-woche" href="([^"]*)"', text).group(1)
    assert andere == "/?karte=woche"


def test_karten_sind_links_mit_zielen_fuer_htmx(angemeldet, fuenf):
    text = angemeldet.get("/").text
    for klasse, karte in (("aufmerksamkeit", "aufmerksamkeit"), ("erkaltet", "erkaltet"),
                          ("woche", "woche")):
        assert (f'<a class="karte karte-{klasse}" href="/?karte={karte}" '
                f'hx-get="/liste?karte={karte}" hx-target="#liste" hx-swap="outerHTML">') in text


def test_zahlen_der_karten_gelten_immer_fuer_alle(angemeldet, con, nid, fuenf):
    tag = personen.tag_anlegen(con, nid, "Arbeit")
    personen.tags_setzen(con, nid, fuenf["ueber"], {tag})
    gefiltert = angemeldet.get(f"/?tag={tag}&karte=aufmerksamkeit").text
    assert reihenfolge(gefiltert) == ["Anna Beispiel"]
    assert karten(gefiltert) == {"Braucht Aufmerksamkeit": 2, "Erkaltet": 1, "Diese Woche": 1}
    # der Tag filtert mit: Ben ist erkaltet, aber nicht in dem Tag
    assert reihenfolge(angemeldet.get(f"/?tag={tag}&karte=erkaltet").text) == []


def test_karte_und_suche_gelten_zusammen(angemeldet, fuenf):
    assert reihenfolge(angemeldet.get("/?karte=aufmerksamkeit&suche=ben").text) == ["Ben Muster"]
    text = angemeldet.get("/?karte=aufmerksamkeit&suche=dora").text
    assert "Niemand gefunden für „dora“." in text


def test_karte_leerzustaende(angemeldet):
    assert "Niemand braucht gerade Aufmerksamkeit." in angemeldet.get("/?karte=aufmerksamkeit").text
    assert "Keine Bindung ist erkaltet." in angemeldet.get("/?karte=erkaltet").text
    woche = angemeldet.get("/?karte=woche").text
    assert "In den nächsten sieben Tagen ist niemand fällig." in woche


def test_unbekannte_karte_wird_ignoriert(angemeldet, fuenf):
    assert len(reihenfolge(angemeldet.get("/?karte=blau").text)) == 5


def test_im_archiv_gibt_es_keine_karte(angemeldet, con, nid, fuenf):
    personen.archivieren(con, nid, fuenf["kalt"])
    text = angemeldet.get("/?filter=archiv&karte=erkaltet").text
    assert reihenfolge(text) == ["Ben Muster"]
    assert "karte-aktiv" not in text


def test_karte_auf_dem_telefon_zeigt_die_liste(angemeldet, fuenf):
    assert 'data-ansicht="liste"' in angemeldet.get("/?karte=woche").text


def test_such_suchformular_traegt_die_karte(angemeldet, fuenf):
    text = angemeldet.get("/?karte=erkaltet").text
    assert '<input type="hidden" name="karte" value="erkaltet">' in text


# -------------------------------------------------------------- Suche

def test_suche_behaelt_die_offene_person_in_der_adresse(angemeldet, con, nid, fuenf):
    antwort = angemeldet.get("/liste/suche?suche=ben", headers=hx(f"/?person={fuenf['ueber']}"))
    assert antwort.headers["hx-replace-url"] == f"/?suche=ben&person={fuenf['ueber']}"


def test_suche_behaelt_filter_karte_und_person(angemeldet, fuenf):
    antwort = angemeldet.get("/liste/suche?karte=aufmerksamkeit&suche=ben",
                             headers=hx(f"/?karte=aufmerksamkeit&person={fuenf['kalt']}"))
    assert antwort.headers["hx-replace-url"] == (
        f"/?karte=aufmerksamkeit&suche=ben&person={fuenf['kalt']}")
    assert reihenfolge(antwort.text) == ["Ben Muster"]


def test_suche_laesst_eine_fremde_person_aus_der_adresse_fallen(angemeldet, con, fremder):
    fremd = personen.anlegen(con, fremder, "Fremd Beispiel")
    antwort = angemeldet.get("/liste/suche?suche=x", headers=hx(f"/?person={fremd}"))
    assert antwort.status_code == 200
    assert antwort.headers["hx-replace-url"] == "/?suche=x"


# ------------------------------------------------------ Nutzer und Fremde

def test_fremde_nummern_sind_404(angemeldet, con, fremder):
    fremde_person = personen.anlegen(con, fremder, "Fremd Beispiel")
    fremder_kontakt = kontakte.eintragen(con, fremder, fremde_person, datum="2026-11-10",
                                         art="anruf", notiz="geheim")
    anfragen = [
        ("get", f"/personen/{fremde_person}/kontakt/neu", None),
        ("post", f"/personen/{fremde_person}/kontakte", {"art": "anruf", "datum": "2026-11-10"}),
        ("get", f"/kontakte/{fremder_kontakt}", None),
        ("get", f"/kontakte/{fremder_kontakt}/bearbeiten", None),
        ("post", f"/kontakte/{fremder_kontakt}", {"datum": "2026-11-10", "notiz": "x"}),
        ("post", f"/kontakte/{fremder_kontakt}/loeschen", None),
    ]
    for methode, pfad, daten in anfragen:
        antwort = getattr(angemeldet, methode)(pfad, headers=hx(), **(
            {"data": daten} if daten is not None else {}))
        assert antwort.status_code == 404, (methode, pfad)
    assert [z["notiz"] for z in kontakte.liste(con, fremder, fremde_person)] == ["geheim"]


def test_fremde_kontakte_stehen_nicht_in_karten_und_liste(angemeldet, con, fremder):
    fremd = personen.anlegen(con, fremder, "Fremd Beispiel")
    con.execute("INSERT INTO kontakt (nutzer_id, person_id, datum, art, notiz) "
                "VALUES (?, ?, ?, 'anruf', 'geheim')", (fremder, fremd, vor(300)))
    con.commit()
    text = angemeldet.get("/").text
    assert "Fremd Beispiel" not in text and "geheim" not in text
    assert karten(text) == {"Braucht Aufmerksamkeit": 0, "Erkaltet": 0, "Diese Woche": 0}


def test_ohne_anmeldung_kommt_niemand_an_die_kontakte(client):
    for methode, pfad in (("get", "/personen/1/kontakt/neu"), ("post", "/personen/1/kontakte"),
                          ("get", "/kontakte/1"), ("post", "/kontakte/1/loeschen")):
        antwort = getattr(client, methode)(pfad, headers={"HX-Request": "true"})
        assert antwort.status_code == 401


def test_personenseite_hat_die_profilnotiz_vor_dem_touchpoint_knopf(angemeldet, con, nid):
    """PLAN.md, Abschnitt 7: Kopf, Tags, Telefon und E-Mail, Ort, Herkunft, Profilnotiz,
    dann der Knopf, Zuletzt besprochen, Angehörige, Stichtage, dann Intervall und Archivieren."""
    pid = person_mit(con, nid, "Anna Beispiel", 5)
    text = angemeldet.get(f"/?person={pid}").text
    reihe = ['id="name"', 'id="personentags"', 'id="kontaktlinks"', 'id="telefon"',
             'id="email"', 'id="ort"', 'id="herkunft"', 'id="profilnotiz"',
             '>Touchpoint eintragen<', 'id="verlauf"', 'id="angehoerige"', 'id="stichtage"',
             'id="intervall_tage"', 'id="naechster_termin"', 'id="faelligkeit"',
             '>Archivieren<']
    stellen = [text.index(m) for m in reihe]
    assert stellen == sorted(stellen), reihe
    assert 'for="profilnotiz">Profilnotiz<' in text
    assert "Wer die Person ist. Wird beim Verlassen des Feldes gespeichert." in text
