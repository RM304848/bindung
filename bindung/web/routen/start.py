"""Die Startseite: Seitenleiste, Liste und Personenseite (PLAN.md, Abschnitt 7).

In diesem Stand ist das Geruest leer: alle Zahlen sind 0, es gibt keine Tags
und keine Personen. WP1 fuellt es.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from bindung.web import basis

router = APIRouter()


@router.get("/")
def start(request: Request):
    return basis.seite(request, "start.html")
