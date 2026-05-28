from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes import status as status_route
from app.routes.auth import require_admin


@pytest.mark.anyio
async def test_require_admin_accepts_admin_user() -> None:
    user = SimpleNamespace(role="ADMIN")

    assert await require_admin(user) is user


@pytest.mark.anyio
async def test_require_admin_rejects_user_role() -> None:
    user = SimpleNamespace(role="USER")

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "admin access required"


def test_server_status_route_uses_admin_guard() -> None:
    route = next(route for route in status_route.router.routes if getattr(route, "path", None) == "/status/server")
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}

    assert require_admin in dependency_calls
