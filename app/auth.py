"""Basic authentication and authorization dependencies."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings
from app.tenancy import tenant_from_header

security = HTTPBasic()
settings = get_settings()


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str
    is_admin: bool
    tenant_id: str


def require_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    tenant_id: str = Depends(tenant_from_header),
) -> AuthenticatedUser:
    username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if username_ok and password_ok:
        return AuthenticatedUser(
            username=credentials.username,
            role="admin",
            is_admin=True,
            tenant_id=tenant_id,
        )

    demo_tenant_ok = secrets.compare_digest(tenant_id, settings.demo_tenant_id)
    demo_username_ok = secrets.compare_digest(credentials.username, settings.demo_username)
    demo_password_ok = secrets.compare_digest(credentials.password, settings.demo_password)
    if demo_tenant_ok and demo_username_ok and demo_password_ok:
        return AuthenticatedUser(
            username=credentials.username,
            role="demo_admin",
            is_admin=True,
            tenant_id=tenant_id,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def require_admin(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
    if user.is_admin:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
