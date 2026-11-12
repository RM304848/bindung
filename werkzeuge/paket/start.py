"""Einstieg der App aus der .dmg: der Starter, oder mit `mcp` der Zugang fuer einen Bot.

    /Applications/Bindung.app/Contents/MacOS/Bindung                 # die App
    /Applications/Bindung.app/Contents/MacOS/Bindung mcp --nutzer X  # MCP ueber stdin/stdout

Wer Bindung aus der .dmg hat, hat kein `bindung` im Terminal; ein MCP-Client startet
deshalb das Programm in der App mit `mcp` (docs/mcp.md).
"""

import sys

if __name__ == "__main__":
    if sys.argv[1:2] == ["mcp"]:
        from bindung.cli import app

        app(prog_name="bindung")
    else:
        from bindung.starter import main

        main()
