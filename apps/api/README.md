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

The same API container serves dashboard static files, API routes, and Analyze runtime. Set `PROMPTGUARD_EXTENSION_API_URL` to the API origin that Chrome Extension user computers can reach, for example `http://192.168.0.25:8000` or `https://promptguard.example.com`. Set `PROMPTGUARD_DASHBOARD_PUBLIC_URL` separately with the `/dashboard/` path. The dashboard status screen only makes a URL copyable when `PROMPTGUARD_EXTENSION_API_URL` is valid; `localhost`, Docker bridge addresses, PostgreSQL port `5432`, and `/dashboard/` paths are configuration errors for the Extension API URL.

## Current Scope

- API process scaffold
- PostgreSQL connectivity
- Redis connectivity
- `/healthz` dependency status endpoint
- Alembic migration skeleton
