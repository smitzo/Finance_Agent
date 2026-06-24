"""Tenant context helpers used by API, service, and agent layers."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Header, HTTPException

from app.config import get_settings

settings = get_settings()
TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def normalize_tenant_id(value: str | None) -> str:
    tenant_id = (value or settings.default_tenant_id).strip()
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise ValueError(
            "tenant_id must be 1-64 characters and contain only letters, numbers, '_' or '-'"
        )
    return tenant_id


async def tenant_from_header(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> str:
    try:
        return normalize_tenant_id(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
