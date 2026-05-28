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
http://localhost:8000/healthz
```

## Current Scope

This branch is an auth foundation draft, not the final v0.10 MVP implementation.
It adds the first runnable FastAPI/PostgreSQL/Alembic/auth skeleton so later
stacked PRs can tighten the contract in smaller reviewable steps.

- API process scaffold
- PostgreSQL connectivity
- Redis connectivity
- `/healthz` dependency status endpoint
- Alembic migration skeleton

## Follow-up Scope

The following v0.10 requirements are intentionally handled by follow-up PRs:

- Default `admin` seed through DB migration instead of `/setup/bootstrap`
- `username`-based account schema alignment
- Redis as an optional profile instead of a default dependency
- Separate `/livez`, `/readyz`, `/healthz`, and ADMIN-only `/status/server`
- Refresh token reuse detection and token family revocation
- Explicit FastAPI CORS middleware and auth/analyze rate limits
- ADMIN/USER RBAC and ADMIN-managed `/admin/users` APIs
