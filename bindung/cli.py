"""Die Kommandozeile `bindung` (PLAN.md, Abschnitte 4 und 11)."""

from __future__ import annotations

from pathlib import Path

import typer

from bindung import auth, db, pfade

app = typer.Typer(help="Bindung: den Kontakt zu den Menschen halten, die einem wichtig sind.",
                  no_args_is_help=True)
nutzer_app = typer.Typer(help="Nutzer anlegen, Passwort setzen, auflisten.",
                         no_args_is_help=True)
app.add_typer(nutzer_app, name="nutzer")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", envvar="BINDUNG_HOST",
                             help="Adresse; Vorgabe: nur dieser Rechner"),
    port: int = typer.Option(8785, envvar="BINDUNG_PORT", help="Port"),
    reload: bool = typer.Option(False, "--reload",
                                help="Bei jeder Codeaenderung von selbst neu starten"),
) -> None:
    """Startet den Server (Vorgabe http://127.0.0.1:8785)."""
    import uvicorn

    con = db.verbinden()
    if not auth.nutzer_liste(con):
        typer.echo("Noch kein Nutzer. Anlegen mit: bindung nutzer anlegen <name>")
    con.close()
    paket = str(Path(__file__).resolve().parent)
    uvicorn.run("bindung.web.server:app", host=host, port=port, reload=reload,
                reload_dirs=[paket] if reload else None)


@app.command("app")
def app_starten() -> None:
    """Startet Bindung wie die Mac-App: Server auf Port 8788, Menüleiste, Browser.

    Dasselbe tut der Doppelklick auf die App aus der .dmg.
    """
    from bindung import starter

    starter.main()


@app.command("mcp")
def mcp_starten(
    nutzer: str = typer.Option(None, "--nutzer", help="Als dieser Nutzer handeln; ohne Angabe "
                                                     "der einzige Nutzer"),
) -> None:
    """Spricht MCP über stdin/stdout: ein Bot fragt ab und trägt ein, als dieser Nutzer.

    Für Claude Desktop und andere MCP-Clients (docs/mcp.md). stdout gehört dem Protokoll;
    Meldungen stehen auf stderr.
    """
    from bindung import mcp
    from bindung.mcp import werkzeuge

    con = db.verbinden()
    try:
        werkzeuge.nutzer_waehlen(con, nutzer)
    except werkzeuge.Meldung as fehler:
        typer.echo(str(fehler), err=True)
        raise typer.Exit(1) from None
    finally:
        con.close()
    mcp.laufen(nutzer=nutzer)


@app.command()
def ort() -> None:
    """Zeigt den Datenordner und warum es dieser ist."""
    wurzel, grund = pfade.wurzel_mit_grund()
    typer.echo(f"Datenordner: {wurzel}")
    typer.echo(f"Grund:       {grund}")


@nutzer_app.command("anlegen")
def nutzer_anlegen(name: str = typer.Argument(..., help="Name des neuen Nutzers")) -> None:
    """Legt einen Nutzer an; das Passwort wird zweimal verdeckt abgefragt."""
    passwort = typer.prompt("Passwort", hide_input=True, confirmation_prompt=True)
    con = db.verbinden()
    try:
        auth.nutzer_anlegen(con, name, passwort)
    except auth.AuthFehler as fehler:
        typer.echo(str(fehler), err=True)
        raise typer.Exit(1) from None
    finally:
        con.close()
    typer.echo(f"Nutzer „{name.strip()}“ angelegt.")


@nutzer_app.command("passwort")
def nutzer_passwort(name: str = typer.Argument(..., help="Name des Nutzers")) -> None:
    """Setzt ein neues Passwort; alle Sitzungen des Nutzers enden."""
    passwort = typer.prompt("Neues Passwort", hide_input=True, confirmation_prompt=True)
    con = db.verbinden()
    try:
        auth.passwort_setzen(con, name, passwort)
    except auth.AuthFehler as fehler:
        typer.echo(str(fehler), err=True)
        raise typer.Exit(1) from None
    finally:
        con.close()
    typer.echo(f"Passwort von „{name.strip()}“ geändert.")


@nutzer_app.command("liste")
def nutzer_liste() -> None:
    """Zeigt alle Nutzer."""
    con = db.verbinden()
    try:
        nutzer = auth.nutzer_liste(con)
    finally:
        con.close()
    if not nutzer:
        typer.echo("Noch kein Nutzer.")
    for zeile in nutzer:
        typer.echo(f"{zeile['name']}  (seit {zeile['erstellt_am'][:10]})")
