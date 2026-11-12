"""Der MCP-Zugang: ein Modell fragt Bindung ab und schreibt, was der Nutzer ihm aufgetragen hat.

`bindung mcp` spricht das Model Context Protocol ueber stdin/stdout (PLAN.md, Abschnitt 14).
Es oeffnet keinen Port und braucht keine Bibliothek: das Protokoll ist JSON-RPC, Zeile fuer
Zeile.

* `protokoll.py`: Handshake, Liste, Aufruf. Kennt keine Menschen.
* `werkzeuge.py`: die Werkzeuge und Ressourcen. Sie gehen ueber dieselben Funktionen wie die
  Seiten (`personen`, `kontakte`, `faelligkeit`, `stichtage`, `angehoerige`), nie ueber SQL.
"""

from bindung.mcp.protokoll import laufen

__all__ = ["laufen"]
