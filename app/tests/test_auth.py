import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app.auth import require_current_user


def credentials(username: str, password: str) -> HTTPBasicCredentials:
    return HTTPBasicCredentials(username=username, password=password)


def test_demo_credentials_are_admin_for_demo_tenant() -> None:
    user = require_current_user(credentials("demo", "demo"), "demo")

    assert user.username == "demo"
    assert user.tenant_id == "demo"
    assert user.role == "demo_admin"
    assert user.is_admin is True


def test_demo_credentials_cannot_cross_tenants() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_current_user(credentials("demo", "demo"), "default")

    assert exc_info.value.status_code == 401


def test_admin_credentials_keep_cross_tenant_bootstrap_access() -> None:
    user = require_current_user(credentials("admin", "admin"), "demo")

    assert user.role == "admin"
    assert user.tenant_id == "demo"
