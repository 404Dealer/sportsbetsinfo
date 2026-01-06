"""HTML page routes for sportsbetsinfo web UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": "SportsBetsInfo"},
    )


@router.get("/edges", response_class=HTMLResponse)
async def edges_page(request: Request) -> HTMLResponse:
    """Render the edges scanner page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "edges.html",
        {"request": request, "title": "Edge Scanner"},
    )


@router.get("/report", response_class=HTMLResponse)
async def report_page(request: Request) -> HTMLResponse:
    """Render the performance report page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "report.html",
        {"request": request, "title": "Performance Report"},
    )


@router.get("/charts", response_class=HTMLResponse)
async def charts_page(request: Request) -> HTMLResponse:
    """Render the charts/visualizations page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "charts.html",
        {"request": request, "title": "Charts"},
    )


@router.get("/games", response_class=HTMLResponse)
async def games_page(request: Request) -> HTMLResponse:
    """Render the games list page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "games.html",
        {"request": request, "title": "Games"},
    )


@router.get("/games/{game_id}", response_class=HTMLResponse)
async def game_detail_page(request: Request, game_id: str) -> HTMLResponse:
    """Render the game detail page with belief drift timeline."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "game_detail.html",
        {"request": request, "title": "Game Timeline", "game_id": game_id},
    )
