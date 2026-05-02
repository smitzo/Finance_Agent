"""Compatibility entry point.

The maintained FastAPI application lives in app.main. Keep this tiny wrapper so
older commands such as `uvicorn main:app` still work without duplicating routes,
startup logic, or persistence code.
"""

from app.main import app

__all__ = ["app"]
