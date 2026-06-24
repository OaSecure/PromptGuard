# PromptGuard API

FastAPI-based self-host API scaffold for PromptGuard.

## Local Docker

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Then open:

```text
http://localhost:8000/dashboard/
http://localhost:8000/healthz
http://localhost:8000/readyz
```

The same API container serves dashboard static files, API routes, and Analyze runtime. Set `PROMPTGUARD_API_PORT`, `PROMPTGUARD_API_PUBLIC_URL`, and `PROMPTGUARD_DASHBOARD_PUBLIC_URL` together when exposing a different public port. Chrome Extension users should copy the API origin shown on the dashboard status screen, not the PostgreSQL port or a server-local `localhost` value meant only for the administrator machine.

## Current Scope

- API process scaffold
- PostgreSQL connectivity
- Redis connectivity
- `/healthz` dependency status endpoint
- Alembic migration skeleton
