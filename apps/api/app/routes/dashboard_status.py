from datetime import UTC, datetime
import ipaddress
from pathlib import Path
import socket
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.core.config import get_settings
from app.models.auth import User
from app.models.filters import FilterRule
from app.routes.dashboard_session import require_dashboard_admin_session
from app.routes.health import build_health

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

StatusValue = Literal["healthy", "degraded", "unhealthy", "unknown"]


class ExtensionConnectionInfo(BaseModel):
    internal_api_origins: list[str]
    excluded_internal_api_origins: list[str]
    admin_local_api_origin: str
    external_api_origin: str | None
    api_port: str


class DashboardStatusResponse(BaseModel):
    status: StatusValue
    last_checked: str
    api_status: StatusValue
    postgres_status: StatusValue
    migration_status: StatusValue
    filter_rules_status: StatusValue
    extension_connection: ExtensionConnectionInfo


def sanitize_status(value: object) -> StatusValue:
    if value in {"healthy", "degraded", "unhealthy"}:
        return value  # type: ignore[return-value]
    return "unknown"


def dependency_status(health: dict[str, object], name: str) -> StatusValue:
    dependencies = health.get("dependencies", [])
    if not isinstance(dependencies, list):
        return "unknown"

    for item in dependencies:
        if isinstance(item, dict) and item.get("name") == name:
            return sanitize_status(item.get("status"))
    return "unknown"


async def filter_rules_status(session: AsyncSession) -> StatusValue:
    try:
        await session.execute(select(FilterRule.id).limit(1))
        return "healthy"
    except Exception:
        return "unhealthy"


def safe_last_checked(value: object) -> str:
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            pass
    try:
        return datetime.now(UTC).isoformat()
    except Exception:
        return "unknown"


def collect_server_ipv4_addresses() -> list[str]:
    candidates: set[str] = set()
    hostnames = {socket.gethostname(), socket.getfqdn(), ""}
    for hostname in hostnames:
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            continue
        for info in infos:
            address = info[4][0]
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
                continue
            candidates.add(address)
    return sorted(candidates)


def is_running_in_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "docker" in cgroup or "kubepods" in cgroup or "containerd" in cgroup


def is_container_bridge_address(address: str) -> bool:
    if not is_running_in_container():
        return False
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed in ipaddress.ip_network("172.16.0.0/12")


def request_origin(request: Request) -> str:
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def request_port(request: Request) -> str:
    if request.url.port is not None:
        return str(request.url.port)
    host = request.headers.get("host", "")
    if ":" in host and not host.startswith("["):
        return host.rsplit(":", 1)[1]
    return "443" if request.url.scheme == "https" else "80"


def forwarded_origin(request: Request) -> str | None:
    forwarded_host = request.headers.get("x-forwarded-host")
    if not forwarded_host:
        return None
    forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = forwarded_host.split(",", 1)[0].strip()
    proto = forwarded_proto.split(",", 1)[0].strip()
    if not host or not proto:
        return None
    return f"{proto}://{host}"


def configured_public_api_origin() -> str | None:
    configured = get_settings().api_public_url.strip()
    if not configured:
        return None
    parsed = urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return None

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is None:
        return f"{parsed.scheme}://{host}"
    return f"{parsed.scheme}://{host}:{parsed.port}"


def build_extension_connection_info(request: Request) -> ExtensionConnectionInfo:
    port = request_port(request)
    scheme = request.url.scheme
    internal_origins: list[str] = []
    excluded_origins: list[str] = []
    for address in collect_server_ipv4_addresses():
        origin = f"{scheme}://{address}:{port}"
        if is_container_bridge_address(address):
            excluded_origins.append(origin)
        else:
            internal_origins.append(origin)
    return ExtensionConnectionInfo(
        internal_api_origins=internal_origins,
        excluded_internal_api_origins=excluded_origins,
        admin_local_api_origin=request_origin(request),
        external_api_origin=configured_public_api_origin() or forwarded_origin(request),
        api_port=port,
    )


def sanitize_dashboard_status(
    health: dict[str, object],
    filter_status: StatusValue,
    extension_connection: ExtensionConnectionInfo,
) -> DashboardStatusResponse:
    overall = sanitize_status(health.get("status"))
    return DashboardStatusResponse(
        status=overall,
        last_checked=safe_last_checked(health.get("checked_at")),
        api_status=overall,
        postgres_status=dependency_status(health, "postgres"),
        migration_status=dependency_status(health, "migrations"),
        filter_rules_status=filter_status,
        extension_connection=extension_connection,
    )


def should_return_unavailable(payload: DashboardStatusResponse) -> bool:
    return "unhealthy" in {
        payload.postgres_status,
        payload.migration_status,
        payload.filter_rules_status,
    }


@router.get("/status", response_model=DashboardStatusResponse)
async def dashboard_status(
    request: Request,
    response: Response,
    _admin_user: User = Depends(require_dashboard_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardStatusResponse:
    health = await build_health(include_optional=False)
    payload = sanitize_dashboard_status(
        health,
        await filter_rules_status(session),
        build_extension_connection_info(request),
    )
    if should_return_unavailable(payload):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
