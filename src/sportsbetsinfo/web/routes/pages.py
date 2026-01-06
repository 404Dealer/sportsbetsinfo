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
