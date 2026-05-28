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

- API process scaffold
- PostgreSQL connectivity
- Redis connectivity
- `/healthz` dependency status endpoint
- Alembic migration skeleton
