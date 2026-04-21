"""Routes for the built-in ops dashboard pages."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse


router = APIRouter()
_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


@router.get("/dashboard", include_in_schema=False)
async def dashboard_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/metrics")


@router.get("/dashboard/metrics", include_in_schema=False)
async def dashboard_metrics() -> FileResponse:
    return FileResponse(_DASHBOARD_DIR / "metrics.html")


@router.get("/dashboard/reviews", include_in_schema=False)
async def dashboard_reviews() -> FileResponse:
    return FileResponse(_DASHBOARD_DIR / "reviews.html")
