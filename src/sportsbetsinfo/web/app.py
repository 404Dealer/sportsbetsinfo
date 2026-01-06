"""FastAPI application factory for sportsbetsinfo web UI."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sportsbetsinfo.web.routes import api, pages

# Path to templates and static files
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def _ensure_database() -> None:
    """Ensure database exists and is initialized."""
    from sportsbetsinfo.config.settings import get_settings
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.schema import initialize_database

    settings = get_settings()
    db_path = settings.db_path

    # Create parent directory
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize if database doesn't exist or is empty
    if not db_path.exists() or db_path.stat().st_size == 0:
        with get_connection(db_path) as conn:
            initialize_database(conn)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup/shutdown."""
    # Startup: ensure database is ready
    try:
        _ensure_database()
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}")
    yield
    # Shutdown: nothing to clean up


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="SportsBetsInfo",
        description="Event-sourced sports betting research platform",
        version="0.1.0",
        lifespan=lifespan,
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

    # Global exception handler for API routes to ensure JSON responses
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions with JSON response."""
        # Only return JSON for API routes
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": str(exc),
                    "error": str(exc),
                    "detail": "Internal server error",
                    "path": request.url.path,
                },
            )
        # Re-raise for page routes to show error page
        raise exc

    return app


# Create default app instance for uvicorn
app = create_app()
