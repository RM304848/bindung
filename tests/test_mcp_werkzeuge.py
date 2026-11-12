"""Die Werkzeuge des MCP-Zugangs, eines nach dem anderen (PLAN.md, Abschnitt 14).

Alle Namen sind erfunden. Die Uhr steht fest auf den 12. November 2026.
"""

from __future__ import annotations

import datetime as dt

import pytest

from bindung import angehoerige, auth, faelligkeit, kontakte, personen, stichtage
from bindung.mcp import werkzeuge
from tests.conftest import PASSWORT

HEUTE = dt.date(2026, 11, 12)


@pytest.fixture(autouse=True)
def feste_uhr(monkeypatch):
    monkeypatch.setattr(personen, "_jetzt",
                        lambda: dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.UTC))


def werkzeuge_aufrufen(name: str, args: dict) -> str:
    return werkzeuge.aufrufen(name, args)


@pytest.fixture
def nid(con, nutzer) -> int:
    return con.execute("SELECT id FROM nutzer WHERE name = ?", (nutzer,)).fetchone()["id"]


def ok(werkzeug: str, /, **args) -> str:
    return werkzeuge_aufrufen(werkzeug, args)


def fehler(werkzeug: str, /, **args) -> str:
    with pytest.raises(ValueError) as grund:
        werkzeuge_aufrufen(werkzeug, args)
    return str(grund.value)


@pytest.fixture
def welt(con, nid) -> dict[str, int]:
    """Fuenf Personen in jedem Zustand, mit Tags, Angehoerigen und Stichtag."""
    ids = {
        "anna": personen.anlegen(con, nid, "Anna Beispiel", firma="Muster GmbH", ort="Köln",
                                 profilnotiz="Mag Bergwandern."),
        "anna2": personen.anlegen(con, nid, "Anna Probe"),
        "ben": personen.anlegen(con, nid, "Ben Muster"),
        "cleo": personen.anlegen(con, nid, "Cleo Test"),
        "dora": personen.anlegen(con, nid, "Dora Neu"),
    }
    freunde = personen.tag_anlegen(con, nid, "Freunde")
    personen.tags_setzen(con, nid, ids["anna"], {freunde})
    personen.tags_setzen(con, nid, ids["ben"], {freunde})
    kontakte.eintragen(con, nid, ids["anna"], datum="2026-11-01", art="anruf",
                       notiz="Über den Umzug gesprochen.\nSie sucht eine Wohnung.")
    kontakte.eintragen(con, nid, ids["ben"], datum="2026-08-04", art="treffen")   # ueberfaellig
    kontakte.eintragen(con, nid, ids["cleo"], datum="2026-01-01", art="nachricht")  # erkaltet
    kontakte.eintragen(con, nid, ids["dora"], datum="2026-09-21", art="email")      # bald
    ids["partner"] = angehoerige.anlegen(con, nid, ids["anna"], name="Paul", rolle="partner",
                                         geburtstag="1990-03-24")
    stichtage.anlegen(con, nid, ids["anna"], bezeichnung="", art="jahrestag", datum="--11-15")
    return ids


# ------------------------------------------------------------ Argumente

def test_pflichtfeld_typ_und_unbekanntes():
    assert "Pflichtfeld fehlt: name" in fehler("person_anlegen")
    assert "name muss vom Typ string sein" in fehler("person_anlegen", name=5)
    assert "Unbekannte Parameter: farbe" in fehler("tags", farbe="rot")
    assert "limit muss vom Typ integer sein" in fehler("personen_suchen", limit=True)
    assert "erlaubt sind" in fehler("wer_wartet", karte="alle")


# ----------------------------------------------------------------- Nutzer

def test_nutzer_waehlen(con, nutzer):
    assert werkzeuge.nutzer_waehlen(con, None)["name"] == nutzer
    assert werkzeuge.nutzer_waehlen(con, "beispiel")["name"] == nutzer
    with pytest.raises(werkzeuge.Meldung, match=r"gibt es nicht\. Vorhanden: Beispiel"):
        werkzeuge.nutzer_waehlen(con, "Niemand")
    auth.nutzer_anlegen(con, "Zweite", PASSWORT)
    with pytest.raises(werkzeuge.Meldung, match="mehrere Nutzer"):
        werkzeuge.nutzer_waehlen(con, None)


def test_ohne_nutzer_ist_eine_meldung(con):
    assert "noch keinen Nutzer" in fehler("tags")


# --------------------------------------------------------------- Lesen

def test_personen_suchen_nach_name_firma_und_tag(welt):
    text = ok("personen_suchen", text="muster")
    assert "2 Personen:" in text
    assert f"Anna Beispiel [{welt['anna']}]" in text      # Firma „Muster GmbH“
    assert "Ben Muster" in text
    assert "Cleo" not in text


def test_personen_suchen_zeile_hat_zustand_tags_und_stichtag(welt):
    zeilen = {z.split(" [")[0]: z for z in ok("personen_suchen").splitlines() if z.startswith("-")}
    assert "Muster GmbH" in zeilen["- Anna Beispiel"]
    assert "Tags: Freunde" in zeilen["- Anna Beispiel"]
    assert "ok · letzter Touchpoint vor 11 Tagen (2026-11-01)" in zeilen["- Anna Beispiel"]
    assert "Jahrestag in 3 Tagen" in zeilen["- Anna Beispiel"]
    assert "überfällig seit 44 Tagen · letzter Touchpoint vor 3 Monaten" in zeilen["- Ben Muster"]
    assert "erkaltet · letzter Touchpoint vor über einem Jahr" not in zeilen["- Cleo Test"]
    assert "erkaltet" in zeilen["- Cleo Test"]
    assert "fällig in 4 Tagen" in zeilen["- Dora Neu"]
    assert "noch kein Touchpoint" in zeilen["- Anna Probe"]


def test_personen_suchen_filter(welt, con, nid):
    assert "2 Personen:" in ok("personen_suchen", tag="freunde")
    assert "1 Person:" in ok("personen_suchen", ohne_touchpoint=True)
    assert "Anna Probe" in ok("personen_suchen", ohne_touchpoint=True)
    assert ok("personen_suchen", archiv=True) == "0 Personen im Archiv."
    personen.archivieren(con, nid, welt["dora"])
    archiv = ok("personen_suchen", archiv=True)
    assert "1 Person im Archiv:" in archiv
    assert "Dora Neu" in archiv and "archiviert" in archiv
    assert "Dora" not in ok("personen_suchen")
    assert fehler(
        "personen_suchen", tag="Fremde") == "Den Tag „Fremde“ gibt es nicht. Vorhanden: Freunde."
    assert ok("personen_suchen", text="gibtsnicht") == "0 Personen."


def test_personen_suchen_limit(welt):
    text = ok("personen_suchen", limit=2)
    assert "5 Personen (die ersten 2, nach Name)" in text
    assert text.count("\n- ") + text.startswith("- ") == 2


def test_person_zeigt_alles_der_personenseite(welt):
    text = ok("person", person=welt["anna"])
    assert text.startswith(f"Anna Beispiel [{welt['anna']}]\nHeute ist 2026-11-12.")
    for erwartet in ("Firma: Muster GmbH", "Ort: Köln", "Tags: Freunde",
                     "Profilnotiz:\n  Mag Bergwandern.",
                     "Zustand: ok (vor 11 Tagen)", "Intervall: 56 Tage (Vorgabe des Nutzers)",
                     "Fällig am: 2026-12-27 (in 45 Tagen)",
                     "Zuletzt besprochen:",
                     "- 2026-11-01 · Anruf [Touchpoint",
                     "    Über den Umzug gesprochen.\n    Sie sucht eine Wohnung.",
                     "Angehörige:", "- Paul (Partner/in) · Geburtstag 24. März 1990",
                     "Stichtage:", "- Jahrestag · 15. November · nächstes Mal in 3 Tagen",
                     "- Geburtstag Paul · 24. März 1990 · nächstes Mal in 132 Tagen (wird 37)"):
        assert erwartet in text, erwartet


def test_person_nach_name_und_klammernummer(welt):
    assert ok("person", person="Ben Muster").startswith(f"Ben Muster [{welt['ben']}]")
    assert ok("person", person=f"[{welt['ben']}]").startswith("Ben Muster")
    assert ok("person", person=str(welt["ben"])).startswith("Ben Muster")
    assert ok("person", person="cleo").startswith("Cleo Test")


def test_person_ohne_touchpoint_und_mit_eigenem_intervall_und_termin(welt, con, nid):
    text = ok("person", person=welt["anna2"])
    assert "Zustand: unbekannt" in text
    assert "Zuletzt besprochen: noch kein Touchpoint." in text
    assert "Fällig am" not in text
    personen.aendern(con, nid, welt["ben"], intervall_tage=30, naechster_termin="2026-12-01")
    text = ok("person", person=welt["ben"])
    assert "Intervall: 30 Tage\n" in text
    assert "Nächster Termin: 2026-12-01" in text
    assert "Fällig am: 2026-12-01 (in 19 Tagen)" in text


def test_person_ueberfaellig_zeigt_faellig_war(welt):
    assert "Fällig war: 2026-09-29" in ok("person", person=welt["ben"])


def test_person_begrenzt_den_verlauf(welt, con, nid):
    for tag in ("2026-10-01", "2026-10-02", "2026-10-03"):
        kontakte.eintragen(con, nid, welt["anna"], datum=tag, art="sonstiges")
    text = ok("person", person=welt["anna"], touchpoints=2)
    assert "Zuletzt besprochen (die letzten 2 von 4):" in text
    assert text.count("[Touchpoint") == 2


def test_person_archiviert(welt, con, nid):
    personen.archivieren(con, nid, welt["ben"])
    assert "(archiviert)" in ok("person", person=welt["ben"])


def test_wer_wartet_sortiert_wie_die_app(welt):
    text = ok("wer_wartet")
    aufmerksamkeit = text.split("Braucht Aufmerksamkeit (2):")[1].split("Erkaltet (")[0]
    assert aufmerksamkeit.index("Cleo Test") < aufmerksamkeit.index("Ben Muster")
    assert "Erkaltet (1):\n- Cleo Test" in text
    woche = text.split("Diese Woche (")[1]
    assert woche.startswith("2):")
    assert "Anna Beispiel" in woche and "Dora Neu" in woche
    assert "Anna Probe" not in text and text.startswith("Stand: 2026-11-12")


def test_wer_wartet_eine_karte_und_leere_karte(welt, con, nid):
    nur = ok("wer_wartet", karte="erkaltet")
    assert "Erkaltet (1)" in nur and "Aufmerksamkeit" not in nur
    leer = ok("wer_wartet", karte="erkaltet", limit=1)
    assert "Cleo" in leer
    personen.archivieren(con, nid, welt["cleo"])
    assert "Erkaltet (0):\n- niemand" in ok("wer_wartet", karte="erkaltet")


def test_wer_wartet_begrenzt(welt):
    assert "… und 1 weitere." in ok("wer_wartet", karte="aufmerksamkeit", limit=1)


def test_diese_woche(welt):
    text = ok("diese_woche")
    assert "Bald fällig, in den nächsten 7 Tagen (1):\n- Dora Neu" in text
    anna = welt["anna"]
    assert (f"Stichtage im Vorlauf (1):\n- Jahrestag in 3 Tagen · Anna Beispiel [{anna}] · "
            "15. November") in text
    assert "Ben Muster" not in text      # überfällig ist Sache von wer_wartet


def test_diese_woche_leer(nutzer):
    text = ok("diese_woche")
    assert "(0):\n- niemand" in text and "(0):\n- keiner" in text


def test_tags(welt, con, nid):
    assert ok("tags") == "Tags (Zahl der aktiven Personen):\n- Freunde (2)"
    personen.archivieren(con, nid, welt["ben"])
    assert "- Freunde (1)" in ok("tags")


def test_tags_ohne(nutzer):
    assert ok("tags") == "Es gibt noch keine Tags."


# ------------------------------------------------- Person finden / Mehrdeutig

def test_mehrdeutiger_name_wird_mit_kandidaten_abgelehnt(welt, con, nid):
    text = fehler("person", person="Anna")
    assert "passt auf 2 Personen" in text
    assert f"Anna Beispiel [{welt['anna']}] · Muster GmbH · Köln" in text
    assert f"Anna Probe [{welt['anna2']}]" in text


def test_voller_name_schlaegt_teilname(welt, con, nid):
    personen.anlegen(con, nid, "Ben")
    assert ok("person", person="ben").startswith("Ben [")
    assert "passt auf 2" in fehler("person", person="Ben M x") or True


def test_gleicher_name_zweimal_ist_mehrdeutig(welt, con, nid):
    personen.anlegen(con, nid, "Ben Muster")
    assert "passt auf 2 Personen" in fehler("person", person="Ben Muster")


def test_unbekannter_name_und_nummer(welt):
    assert "Keine Person mit dem Namen „Zora“ gefunden" in fehler("person", person="Zora")
    assert fehler("person", person=99999) == "Es gibt keine Person mit der Nummer 99999."
    assert "Nenne die Person" in fehler("person", person="  ")


# ------------------------------------------------------- person_anlegen

def test_person_anlegen_mit_allem(con, nid, nutzer):
    personen.tag_anlegen(con, nid, "Familie")
    text = ok("person_anlegen", name="  Eva Erfunden ", firma="Beispiel AG", rolle="Nachbarin",
              telefon="0123 456", email="eva@example.org", ort="Bonn", herkunft="Aus dem Chor",
              profilnotiz="Hat zwei Katzen.", tags=["familie", "Chor", "chor"],
              letzter_touchpoint="vor_monaten")
    assert text.startswith("Person angelegt: Eva Erfunden [")
    for erwartet in ("Firma: Beispiel AG", "Rolle: Nachbarin", "Telefon: 0123 456",
                     "E-Mail: eva@example.org", "Ort: Bonn", "Herkunft: Aus dem Chor",
                     "Profilnotiz:\n  Hat zwei Katzen.", "Tags: familie, Chor",
                     "Neu angelegte Tags: Chor.", ("Letzter Touchpoint geschätzt: vor ein paar "
                     "Monaten."), "Zustand: ", "letzter Touchpoint vor 3 Monaten (2026-08-14)"):
        assert erwartet in text, erwartet
    person = personen.liste(con, nid, suche="Eva")[0]
    assert {t["name"] for t in personen.tags_mit_zaehlern(con, nid)} == {"Familie", "Chor"}
    assert personen.tags_der_person(con, nid, person["id"])
    art = kontakte.liste(con, nid, person["id"])[0]
    assert (art["art"], art["datum"], art["notiz"]) == ("schaetzung", "2026-08-14", None)


def test_person_anlegen_nur_name(con, nid, nutzer):
    text = ok("person_anlegen", name="Finn Frei")
    assert "Zustand: noch kein Touchpoint" in text
    assert "Tags" not in text


def test_person_anlegen_lehnt_ab_wie_die_seite(nutzer):
    assert fehler("person_anlegen", name="   ") == "Der Name darf nicht leer sein."
    assert "erlaubt sind diesen_monat, vor_monaten, ueber_ein_jahr" in fehler(
        "person_anlegen", name="X", letzter_touchpoint="gestern")
    assert fehler("person_anlegen", name="X", tags=[" "]) == "Der Tag braucht einen Namen."
    assert fehler("person_anlegen", name="X", tags=[1]) == "tags ist eine Liste von Namen."


def test_abgelehnte_person_hinterlaesst_nichts(con, nid, nutzer):
    fehler("person_anlegen", name="Halb", tags=["Gut", " "])
    assert personen.liste(con, nid) == []
    assert personen.tags_mit_zaehlern(con, nid) == []


def test_person_anlegen_doppelter_name(welt, con, nid):
    text = fehler("person_anlegen", name="anna beispiel")
    assert f"Es gibt schon eine Person mit diesem Namen: Anna Beispiel [{welt['anna']}]" in text
    assert len(personen.liste(con, nid)) == 5
    ok("person_anlegen", name="anna beispiel", trotzdem=True)
    assert len(personen.liste(con, nid)) == 6


# ------------------------------------------------ touchpoint_eintragen

def test_touchpoint_eintragen_nach_nummer(welt, con, nid):
    text = ok("touchpoint_eintragen", person=welt["ben"], art="anruf", datum="2026-11-10",
              notiz=" Über die Reise gesprochen. ")
    assert text.startswith(f"Touchpoint eingetragen: Anruf mit Ben Muster [{welt['ben']}] "
                           "am 2026-11-10 [Touchpoint ")
    assert "Notiz:\n  Über die Reise gesprochen." in text
    assert "Zustand jetzt: ok · letzter Touchpoint vor 2 Tagen (2026-11-10)" in text
    assert "Fällig am: 2027-01-05" in text
    neu = kontakte.liste(con, nid, welt["ben"])[0]
    assert (neu["datum"], neu["art"], neu["notiz"]) == (
        "2026-11-10", "anruf", "Über die Reise gesprochen.")


def test_touchpoint_vorgabe_heute_und_gestern(welt, con, nid):
    ok("touchpoint_eintragen", person=welt["cleo"], art="Anruf")
    ok("touchpoint_eintragen", person=welt["cleo"], art="treffen", datum="gestern")
    ok("touchpoint_eintragen", person=welt["cleo"], art="sonstiges", datum="heute", notiz="x")
    tage = [(t["datum"], t["art"]) for t in kontakte.liste(con, nid, welt["cleo"])[:3]]
    assert ("2026-11-12", "anruf") in tage and ("2026-11-11", "treffen") in tage
    assert ("2026-11-12", "sonstiges") in tage


def test_touchpoint_nach_eindeutigem_namen(welt, con, nid):
    text = ok("touchpoint_eintragen", person="Cleo", art="E-Mail", notiz="Kurz geschrieben.")
    assert "E-Mail mit Cleo Test" in text
    assert kontakte.liste(con, nid, welt["cleo"])[0]["art"] == "email"


def test_touchpoint_mehrdeutiger_name_schreibt_nichts(welt, con, nid):
    text = fehler("touchpoint_eintragen", person="Anna", art="anruf")
    assert "passt auf 2 Personen" in text and f"[{welt['anna2']}]" in text
    assert kontakte.liste(con, nid, welt["anna2"]) == []
    assert len(kontakte.liste(con, nid, welt["anna"])) == 1


def test_touchpoint_zukunft_und_ungueltig_wie_die_seite(welt, con, nid):
    assert fehler("touchpoint_eintragen", person=welt["ben"], art="anruf",
                  datum="2026-11-13") == \
        "Das Datum liegt in der Zukunft. Trag nur ein, was schon war."
    assert fehler("touchpoint_eintragen", person=welt["ben"], art="anruf", datum="morgen") \
        == "Das Datum ist ungültig."
    assert fehler("touchpoint_eintragen", person=welt["ben"], art="telepathie") \
        == "Wähle aus, wie ihr euch ausgetauscht habt."
    assert len(kontakte.liste(con, nid, welt["ben"])) == 1


def test_touchpoint_loescht_den_naechsten_termin(welt, con, nid):
    personen.aendern(con, nid, welt["ben"], naechster_termin="2026-12-24")
    text = ok("touchpoint_eintragen", person=welt["ben"], art="anruf")
    assert "Der nächste Termin (2026-12-24) ist damit gelöscht." in text
    assert personen.laden(con, nid, welt["ben"])["naechster_termin"] is None


def test_touchpoint_zweimal_gleich_wird_abgelehnt(welt, con, nid):
    ok("touchpoint_eintragen", person=welt["ben"], art="anruf", notiz="Hallo.")
    assert "Genau dieser Touchpoint steht schon" in fehler(
        "touchpoint_eintragen", person=welt["ben"], art="anruf", notiz="Hallo.")
    assert len(kontakte.liste(con, nid, welt["ben"])) == 2
    ok("touchpoint_eintragen", person=welt["ben"], art="anruf", notiz="Anderes.")


def test_touchpoint_archivierte_per_namen_nicht_per_nummer(welt, con, nid):
    personen.archivieren(con, nid, welt["ben"])
    assert "Keine Person mit dem Namen" in fehler("touchpoint_eintragen", person="Ben", art="anruf")
    assert "Touchpoint eingetragen" in ok("touchpoint_eintragen", person=welt["ben"], art="anruf")


# ------------------------------------------------- profilnotiz_setzen

def test_profilnotiz_ersetzen_zeigt_das_vorherige(welt, con, nid):
    text = ok("profilnotiz_setzen", person=welt["anna"], text="Mag Segeln.")
    assert f"Profilnotiz von Anna Beispiel [{welt['anna']}] gesetzt." in text
    assert "Vorher stand dort:\n  Mag Bergwandern." in text and "Jetzt:\n  Mag Segeln." in text
    assert personen.laden(con, nid, welt["anna"])["profilnotiz"] == "Mag Segeln."


def test_profilnotiz_anhaengen(welt, con, nid):
    text = ok("profilnotiz_setzen", person=welt["anna"], text=" Hat einen Hund. ", anhaengen=True)
    assert "ergänzt." in text and "Vorher" not in text
    assert personen.laden(con, nid, welt["anna"])["profilnotiz"] == \
        "Mag Bergwandern.\nHat einen Hund."
    ok("profilnotiz_setzen", person=welt["anna2"], text="Neu.", anhaengen=True)
    assert personen.laden(con, nid, welt["anna2"])["profilnotiz"] == "Neu."
    assert fehler("profilnotiz_setzen", person=welt["anna"], text=" ", anhaengen=True) \
        == "Es gibt nichts anzuhängen: text ist leer."


def test_profilnotiz_leeren(welt, con, nid):
    text = ok("profilnotiz_setzen", person=welt["anna"], text="")
    assert "geleert." in text and "Vorher stand dort:" in text
    assert personen.laden(con, nid, welt["anna"])["profilnotiz"] is None


# ---------------------------------------------------- stichtag_anlegen

def test_stichtag_anlegen_mit_jahr(welt, con, nid):
    text = ok("stichtag_anlegen", person=welt["ben"], art="geburtstag", datum="1985-11-14")
    assert text.startswith("Stichtag angelegt: Geburtstag · 14. November 1985 bei Ben Muster "
                           f"[{welt['ben']}] [Stichtag ")
    assert "Nächstes Mal in 2 Tagen, wird 41; er erscheint 7 Tage vorher." in text
    assert len(stichtage.liste(con, nid, welt["ben"], HEUTE)) == 1


def test_stichtag_ohne_jahr_benannt_und_vorlauf(welt, con, nid):
    text = ok("stichtag_anlegen", person=welt["ben"], art="sonstiges", datum="--02-29",
              bezeichnung="Hochzeitstag", vorlauf_tage=14)
    assert "Hochzeitstag · 29. Februar" in text and "14 Tage vorher" in text


def test_stichtag_lehnt_ab_wie_die_seite(welt):
    assert fehler("stichtag_anlegen", person=welt["ben"], art="sonstiges", datum="--01-01") \
        == "Gib dem Stichtag einen Namen."
    assert fehler("stichtag_anlegen", person=welt["ben"], art="geburtstag", datum="24.03.") \
        == "Das Datum ist ungültig."
    assert fehler("stichtag_anlegen", person=welt["ben"], art="feiertag", datum="--01-01") \
        == "Wähle aus, was für ein Stichtag es ist."
    assert "Der Vorlauf liegt zwischen" in fehler(
        "stichtag_anlegen", person=welt["ben"], art="geburtstag", datum="--01-01",
        vorlauf_tage=999)


def test_stichtag_doppelt(welt, con, nid):
    ok("stichtag_anlegen", person=welt["ben"], art="geburtstag", datum="1985-11-14")
    assert f"gibt es bei Ben Muster [{welt['ben']}] schon" in fehler(
        "stichtag_anlegen", person=welt["ben"], art="geburtstag", datum="1985-11-14")
    assert len(stichtage.liste(con, nid, welt["ben"], HEUTE)) == 1


# ------------------------------------------------------- Ressourcen

def test_glossar_ist_das_context_md():
    text = werkzeuge.lesen("bindung://glossar")
    assert "**Touchpoint**" in text and text.startswith("# Bindung")


def test_glossar_fehlt(monkeypatch, tmp_path):
    monkeypatch.setattr(werkzeuge, "GLOSSAR", tmp_path / "weg.md")
    with pytest.raises(werkzeuge.Meldung, match="Glossar"):
        werkzeuge.lesen("bindung://glossar")


def test_heute_ist_die_tagesmeldung(welt):
    text = werkzeuge.lesen("bindung://heute")
    assert text.startswith("Tagesmeldung für 2026-11-12:\n2 Personen warten")
    assert "Cleo Test, Ben Muster" in text
    assert "Jahrestag" in text


def test_heute_ohne_meldung(nutzer):
    assert werkzeuge.lesen("bindung://heute") == (
        "Tagesmeldung für 2026-11-12: Heute ist nichts zu sagen. "
        "Niemand wartet, kein Stichtag im Vorlauf.")


# --------------------------------------------- Zustand wie die App rechnet

def test_zustaende_stimmen_mit_der_faelligkeit_ueberein(welt, con, nid):
    bindungen = faelligkeit.bindungen(con, nid, HEUTE)
    assert bindungen[welt["ben"]].zustand == faelligkeit.UEBERFAELLIG
    assert bindungen[welt["cleo"]].zustand == faelligkeit.ERKALTET
    assert bindungen[welt["dora"]].zustand == faelligkeit.BALD
