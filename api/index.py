"""Vercel serverless function entry point.

This file exposes the FastAPI app for Vercel's Python runtime.
"""

from sportsbetsinfo.web.app import app

# Vercel expects an `app` or `handler` at module level
# FastAPI is ASGI-compatible and works directly
