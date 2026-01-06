"""FastAPI application factory for sportsbetsinfo web UI."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sportsbetsinfo.web.routes import api, pages

# Path to templates and static files
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="SportsBetsInfo",
        description="Event-sourced sports betting research platform",
        version="0.1.0",
    )

    # Add CORS middleware for API access from different origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files (skip on Vercel where they're served by CDN)
    if STATIC_DIR.exists() and not os.environ.get("VERCEL"):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Set up templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Store templates in app state for access in routes
    app.state.templates = templates

    # Include routers
    app.include_router(api.router, prefix="/api", tags=["api"])
    app.include_router(pages.router, tags=["pages"])

    return app


# Create default app instance for uvicorn
app = create_app()
