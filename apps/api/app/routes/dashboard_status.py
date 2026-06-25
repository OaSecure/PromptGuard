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
ExtensionApiUrlStatus = Literal["configured", "missing", "invalid"]


class ExtensionConnectionInfo(BaseModel):
    internal_api_origins: list[str]
    excluded_internal_api_origins: list[str]
    admin_local_api_origin: str
    external_api_origin: str | None
    api_port: str
    extension_api_url: str | None
    extension_api_url_status: ExtensionApiUrlStatus
    extension_api_url_error: str | None
    dashboard_public_url: str | None


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


def configured_dashboard_public_url() -> str | None:
    configured = get_settings().dashboard_public_url.strip()
    if not configured:
        return None
    parsed = urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return configured


def _normal_host(hostname: str) -> str:
    return f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname


def _parse_extension_api_url(configured: str):
    parsed = urlparse(configured)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return parsed, "PROMPTGUARD_EXTENSION_API_URL must be an http or https URL."
    return parsed, None


def _extension_api_url_component_error(parsed) -> str | None:
    if parsed.username or parsed.password:
        return "PROMPTGUARD_EXTENSION_API_URL must not include credentials."
    if parsed.query or parsed.fragment:
        return "PROMPTGUARD_EXTENSION_API_URL must not include query strings or fragments."
    if parsed.path not in {"", "/"}:
        return "PROMPTGUARD_EXTENSION_API_URL must be the API origin only, without /dashboard/ or another path."
    return None


def _extension_api_url_host_error(hostname: str) -> str | None:
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return "localhost only points to the user's own computer and cannot be used as the Extension API URL."
    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if parsed_ip.is_loopback or parsed_ip.is_unspecified or parsed_ip.is_link_local:
        return "PROMPTGUARD_EXTENSION_API_URL must be reachable from extension user computers."
    if parsed_ip in ipaddress.ip_network("172.16.0.0/12"):
        return "Docker bridge addresses cannot be used as the Extension API URL."
    return None


def _invalid_extension_api_url_reason(configured: str) -> str | None:
    parsed, parse_error = _parse_extension_api_url(configured)
    if parse_error is not None:
        return parse_error
    component_error = _extension_api_url_component_error(parsed)
    if component_error is not None:
        return component_error
    host_error = _extension_api_url_host_error(parsed.hostname or "")
    if host_error is not None:
        return host_error
    if parsed.port == 5432:
        return "PostgreSQL port 5432 is not an HTTP API port."
    return None


def configured_extension_api_url_status() -> tuple[str | None, ExtensionApiUrlStatus, str | None]:
    configured = get_settings().extension_api_url.strip()
    if not configured:
        return None, "missing", "PROMPTGUARD_EXTENSION_API_URL is not configured."
    reason = _invalid_extension_api_url_reason(configured)
    if reason is not None:
        return None, "invalid", reason
    parsed = urlparse(configured)
    host = _normal_host(parsed.hostname or "")
    if parsed.port is None:
        return f"{parsed.scheme}://{host}", "configured", None
    return f"{parsed.scheme}://{host}:{parsed.port}", "configured", None


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
    extension_api_url, extension_api_url_status, extension_api_url_error = configured_extension_api_url_status()
    return ExtensionConnectionInfo(
        internal_api_origins=internal_origins,
        excluded_internal_api_origins=excluded_origins,
        admin_local_api_origin=request_origin(request),
        external_api_origin=configured_public_api_origin() or forwarded_origin(request),
        api_port=port,
        extension_api_url=extension_api_url,
        extension_api_url_status=extension_api_url_status,
        extension_api_url_error=extension_api_url_error,
        dashboard_public_url=configured_dashboard_public_url(),
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
