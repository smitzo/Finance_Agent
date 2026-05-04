"""Basic authentication and authorization dependencies."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

security = HTTPBasic()
settings = get_settings()


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str
    is_admin: bool


def require_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
) -> AuthenticatedUser:
    username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if username_ok and password_ok:
        return AuthenticatedUser(username=credentials.username, role="admin", is_admin=True)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def require_admin(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
    if user.is_admin:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
