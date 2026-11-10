"""Die Kommandozeile, mit Typers Runner."""

from __future__ import annotations

from typer.testing import CliRunner

from bindung import auth, cli, db, pfade

runner = CliRunner()


def _eingabe(passwort: str, zweites: str | None = None) -> str:
    return f"{passwort}\n{zweites or passwort}\n"


def test_ort_nennt_datenordner_und_grund(daten):
    ergebnis = runner.invoke(cli.app, ["ort"])
    assert ergebnis.exit_code == 0
    assert "Datenordner:" in ergebnis.output
    assert "BINDUNG_DATEN" in ergebnis.output


def test_nutzer_anlegen_und_liste(daten):
    ergebnis = runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"],
                             input=_eingabe("ein-gutes-passwort"))
    assert ergebnis.exit_code == 0, ergebnis.output
    assert "angelegt" in ergebnis.output
    assert "ein-gutes-passwort" not in ergebnis.output

    liste = runner.invoke(cli.app, ["nutzer", "liste"])
    assert liste.exit_code == 0
    assert "Anna" in liste.output


def test_leere_liste(daten):
    ergebnis = runner.invoke(cli.app, ["nutzer", "liste"])
    assert "Noch kein Nutzer" in ergebnis.output


def test_passwort_wird_gehasht_gespeichert(daten):
    runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"], input=_eingabe("ein-gutes-passwort"))
    con = db.verbinden()
    try:
        gespeichert = con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0]
        assert auth.passwort_pruefen("ein-gutes-passwort", gespeichert)
    finally:
        con.close()


def test_zwei_verschiedene_passwoerter_legen_nichts_an(daten):
    ergebnis = runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"],
                             input="ein-gutes-passwort\nein-anderes-passwort\n" * 3)
    assert ergebnis.exit_code != 0
    assert "Noch kein Nutzer" in runner.invoke(cli.app, ["nutzer", "liste"]).output


def test_doppelter_name_und_kurzes_passwort(daten):
    runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"], input=_eingabe("ein-gutes-passwort"))
    doppelt = runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"],
                            input=_eingabe("ein-gutes-passwort"))
    assert doppelt.exit_code == 1
    assert "gibt es schon" in doppelt.output
    kurz = runner.invoke(cli.app, ["nutzer", "anlegen", "Ben"], input=_eingabe("kurz"))
    assert kurz.exit_code == 1
    assert "mindestens" in kurz.output


def test_passwort_aendern(daten):
    runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"], input=_eingabe("ein-gutes-passwort"))
    ergebnis = runner.invoke(cli.app, ["nutzer", "passwort", "Anna"],
                             input=_eingabe("ein-neues-passwort"))
    assert ergebnis.exit_code == 0, ergebnis.output
    con = db.verbinden()
    try:
        assert auth.anmelden(con, "Anna", "ein-neues-passwort")
    finally:
        con.close()


def test_passwort_fuer_unbekannten_nutzer(daten):
    ergebnis = runner.invoke(cli.app, ["nutzer", "passwort", "Niemand"],
                             input=_eingabe("ein-neues-passwort"))
    assert ergebnis.exit_code == 1
    assert "gibt es nicht" in ergebnis.output


def test_serve_liest_host_und_port_aus_der_umgebung(daten, monkeypatch):
    aufrufe = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: aufrufe.update(k))
    monkeypatch.setenv("BINDUNG_HOST", "0.0.0.0")
    monkeypatch.setenv("BINDUNG_PORT", "9001")
    assert runner.invoke(cli.app, ["serve"]).exit_code == 0
    assert (aufrufe["host"], aufrufe["port"], aufrufe["reload"]) == ("0.0.0.0", 9001, False)


def test_serve_vorgaben(daten, monkeypatch):
    aufrufe = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: aufrufe.update(k))
    monkeypatch.delenv("BINDUNG_HOST", raising=False)
    monkeypatch.delenv("BINDUNG_PORT", raising=False)
    ergebnis = runner.invoke(cli.app, ["serve", "--reload"])
    assert (aufrufe["host"], aufrufe["port"], aufrufe["reload"]) == ("127.0.0.1", 8785, True)
    assert "bindung nutzer anlegen" in ergebnis.output


def test_cli_schreibt_nur_in_den_testordner(daten):
    runner.invoke(cli.app, ["nutzer", "anlegen", "Anna"], input=_eingabe("ein-gutes-passwort"))
    assert pfade.DB_PATH.exists()
    assert daten in pfade.DB_PATH.parents
