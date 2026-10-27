"""Render/Uvicorn entry point.

Run locally with:
    uvicorn web_main:app --reload
"""

from app.main import app

__all__ = ["app"]
