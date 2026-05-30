# PromptGuard Development Documentation Set v0.12 - Team Integrated Edition

## 1. Document Use Rules And Current Implementation Status

- The server language is fixed to Python 3.13.
- PostgreSQL remains the database.
- Redis is not required by default for the MVP. PostgreSQL is the persistence boundary for login continuity, refresh tokens, and duplicate request handling.
- Having an extension mock/client does not mean the self-hosted Analyze API server has been implemented.
- Raw prompts, raw file contents, `masked_prompt`, raw detected values, original filenames, secrets/tokens, and stack traces must not be stored or written to logs, dashboard output, error responses, memory logs, or session logs.
- Keep the WBS owner, area, category, item, and original detail, but split them into implementable work units.
- This v0.12 document is the single basis for PromptGuard development contracts, implementation status, API boundaries, data ownership, and work instructions.
- The original WBS XLSX/CSV files remain separate source artifacts only for confirming scope, order, owner, and area.
- v0.12 preserves the v0.11 integrated contract, clarifies that dashboard implementation is reviewed from Vanilla TypeScript source plus build output verification, and fixes the server runtime to the current Docker baseline of Python 3.13.
- This is a product development contract. Do not put agent-session notes, temporary PR sequencing, or context known only to one conversation into the contract body.

### 1.1 Current Implementation Summary

- The extension has implemented the main flows for ChatGPT input detection, submit hold, Allow/Warn/Mask/Block UX, selector fixtures, and double-submit guard.
- The extension currently has parts verified with mock/fake backend and client fixtures. The real self-hosted API end-to-end smoke test is completed only after the server is implemented.
- `apps/api` now contains the FastAPI app, `/auth/me`, `/config/extension`, `/prompts/analyze`, `/livez`, Pydantic request/response schemas, safe `application/problem+json` validation errors, safe redaction helpers, workspace-scoped HMAC `prompt_hash`, contract-context classification helpers, detection overlap merge helpers, and pytest coverage.
- Current auth only provides a bearer-header boundary and dev metadata. Real auth/session verification, default ADMIN seed, PostgreSQL migrations, idempotency/event metadata persistence, dashboard, Docker Compose base runtime, and dashboard statistics APIs are still implementation targets.
- In the WBS work table, `Done`, `Partial`, and `Not Done` reflect the current repository state. `Partial` means there is a client, fixture, document, or partial UI, but real server/API/DB/integration verification remains.
- The English document is an AI-facing translation. It must follow the same section structure and detail level as the Korean contract.

## 2. Fixed Decisions

- Server language: Python 3.13.
  - Reason: Python is favorable for detectors, rule classifiers, masking, privacy regression tests, and future local analysis. OpenAPI lets the extension and dashboard share language-neutral contracts.
- Database: PostgreSQL.
  - Reason: users, filter rules, event metadata, duplicate request handling, token hashes, and rule versions require durable transactions and migrations.
- Initial access flow: login-first with a seeded default ADMIN.
  - Fresh server initialization creates a default administrator account before the first dashboard use.
  - Default account: `admin / 1234`, role `ADMIN`.
  - `1234` is only an initial seed password. It must be stored only as `password_hash`, never in plaintext, logs, errors, audit metadata, dashboards, or test snapshots.
  - Operations documentation must state that the default password is unsafe for real operation and must be changed before production use. The MVP login UI does not need a dedicated password-change warning banner.
  - `/setup` first-admin creation UI and any user-facing first-admin creation API are not part of the v0.10 MVP flow. The first ADMIN is created only by DB seed/migration.
- User management: ADMIN-managed users only.
  - Self signup, invite signup, workspace-code signup, and open signup are not MVP flows.
  - ADMIN creates USER or ADMIN accounts through `/admin/users` and changes roles/status through ADMIN-only routes.
  - USER accounts do not access the dashboard. They use the Chrome Extension and protected analyze/config routes only.
  - Hard delete is excluded from MVP; user removal means `DISABLED` status.
- Chrome extension: Manifest V3 + TypeScript.
- Dashboard: ADMIN-only metadata UI without raw source data.
- Dashboard frontend: Vanilla TypeScript SPA under `apps/dashboard/`.
  - It uses plain HTML, CSS, and TypeScript without React, Vue, Svelte, Next.js, or other frontend frameworks. Node.js is used only for frontend development, build, and test tooling. TypeScript is compiled to browser JavaScript through Vite, `tsc`, or an equivalent build step. The API server remains Python/FastAPI.
  - `apps/dashboard/src/**/*.ts` and dashboard source assets are the source of truth. Generated `dist/` is build output and must not be hand-edited or treated as implementation source during review.
  - Dashboard changes are verified with `cd apps/dashboard && npm run typecheck`, `npm run build`, and a built-output smoke check.
- Filter configuration model: unified Filter Rule model.
  - Built-in detector settings, custom keyword/regex filters, and Business Context rules are managed through one `filter_rules` model and one Filter Rule Management screen.
  - The management model is unified, but execution is type-specific: `detector`, `keyword`, `regex`, and `context_rule` run through different engine branches.
  - Built-in detectors expose only `enabled`, `severity`, and `action` as editable; parser, checksum, entropy, detector regex, and URI/private-key parsing internals are not administrator-editable.
- API contract source: FastAPI/Pydantic/OpenAPI output from `apps/api`.
- Server implementation stack: Python 3.13 + FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic.
- Redis: optional configuration only.


### 2.1 v0.12 Terminology And Scope Rules

Use the following vocabulary consistently in code, API contracts, WBS tickets, PR descriptions, and dashboard copy.

| Use this term | Meaning | Do not replace with |
| --- | --- | --- |
| Filter Rule | One configurable detection rule shown in the admin filter screen | standalone governance module |
| Filter Config | The active runtime configuration assembled from built-in detector settings, custom keyword/regex rules, and context rules | separate rule screen/module |
| Filter Rule Set Version | Optional internal version used for reproducibility and debugging | event-detail UI field |
| Seeded default ADMIN | The initial `admin / 1234` account created by DB seed/migration | user-facing first-admin form/API |
| Dashboard session | ADMIN-only cookie session for the dashboard | extension bearer token |
| Extension token flow | USER/ADMIN bearer-token flow used by the Chrome extension | dashboard session |
| Remote extension config | `/config/extension` response containing selector, timeout, file limits, and optional filter config version | hard-coded-only selector list |
| Analyze Input Bundle | A set of direct text, paste text, large paste, attachment metadata, unsupported attachment, and scanned text-file inputs for one user send attempt | treating all input as one raw `prompt.text` |
| Attachment Metadata | Metadata-only representation of files, images, or service attachment chips such as filename hash or extension, MIME, size, and count | raw file bytes, base64, OCR text |

Implementation rules:

- Do not create a standalone configuration screen separate from Filter Rule Management.
- Do not add a user-facing first-admin creation flow.
- Do not add self signup, invite signup, workspace-code signup, or open signup to MVP.
- Do not expose any version identifier in event detail UI.
- If reproducibility needs a version, store it internally as `filter_rule_set_version` or `filter_config_version`.
- The only version that may be shown in the server status UI is a small application build/version value.

## 3. Server, Runtime, And Infrastructure Contract

Use the following as the implementation standard for server and runtime work. FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, and the 03A/03B split are fixed only under the assumption that they are common, maintainable, and fast to develop with. If implementation evidence breaks that assumption, do not lock it into code; ask the user again.

1. Implement the Python 3.13 web framework with FastAPI.
   - Reason: Python type hints, Pydantic validation, automatic OpenAPI generation, and Swagger/ReDoc documentation match the PromptGuard API contract well.

2. Implement Python request/response validation with Pydantic v2.
   - Reason: it integrates well with FastAPI and makes request/response schema export to OpenAPI straightforward.

3. Implement ORM/migrations with SQLAlchemy 2.x + Alembic.
   - Reason: this is a standard PostgreSQL application combination in Python and produces reviewable migration scripts.

4. Keep Redis out of the default Compose configuration and provide it only as an optional profile.
   - Reason: for a single self-hosted MVP, Redis is not required for login continuity or fast responses. Add Redis only when multi-instance rate limiting, short distributed locks, queues, or caches are actually needed.

5. Split runtime implementation into two subplans.
   - 03A: Docker Compose, `.env.example`, PostgreSQL, API container skeleton.
   - 03B: Python API skeleton, settings loader, raw-data-removing logger, `/livez`, `/readyz`, `/healthz`, migration state.
   - Reason: Docker/infrastructure problems and API framework problems should be separated so AI development agents can diagnose failures more easily and keep maintenance units small.

### 3.1 Infrastructure / Deployment Subscope

- Development runtime:
  - Root scripts must separate extension/dashboard JavaScript workspace commands from Python API commands.
  - The API runs through a Python virtual environment or container.
  - The extension keeps the existing build/test flow.
- Docker:
  - Base configuration: API and PostgreSQL.
  - The API container base image is `python:3.13-slim`, matching the current Dockerfile.
  - Optional configuration: dashboard, reverse proxy, Redis profile.
  - Health checks use `/livez` or `/readyz`.
- Operations documentation:
  - `.env.example`.
  - Installation guide.
  - Reverse proxy/HTTPS guide.
  - Extension sideload/package guide.
  - Privacy design guide.
  - Admin guide.

## 4. Health And Status Contract

This section uses RFC 9110 HTTP status semantics and RFC 9457 HTTP API problem details as the basis.

### 4.1 Endpoints

| Endpoint | Purpose | Auth | HTTP status rule |
| --- | --- | --- | --- |
| `GET /livez` | Check whether the process is alive and the event loop/request handler can respond | public or internal | `200` if the process can respond; otherwise the request itself fails |
| `GET /readyz` | Check whether the service can receive traffic | internal recommended | `200` when config is valid, DB connection works, migrations are current, and default filter config can load; `503` when a required dependency is unavailable |
| `GET /healthz` | Aggregated status for dashboard/operators | internal or ADMIN recommended | `200` if core function works; `200` with `status=degraded` if only optional dependencies are affected; `503` if required dependencies are unavailable |
| `GET /status/server` | Raw-data-free status API used by the dashboard | ADMIN | Returns the same safe metadata as `/healthz` in an authenticated dashboard shape |

Health/status checks are not just UI features. They are part of the self-hosted operations MVP. Docker Compose and fresh-install requirements cannot be verified reliably without readiness checks such as `/healthz`.

### 4.2 Status Response Shape

```json
{
  "status": "healthy",
  "service": "promptguard-api",
  "version": "0.10.0",
  "environment": "self-host",
  "request_id": "req_...",
  "checked_at": "2026-05-24T00:00:00Z",
  "dependencies": [
    {
      "name": "postgres",
      "status": "healthy",
      "required": true,
      "code": "POSTGRES_OK",
      "message": "PostgreSQL connection and migration state are ready"
    },
    {
      "name": "migrations",
      "status": "healthy",
      "required": true,
      "code": "MIGRATIONS_CURRENT",
      "message": "Database migrations are current"
    },
    {
      "name": "filter_config",
      "status": "healthy",
      "required": true,
      "code": "FILTER_CONFIG_READY",
      "message": "Default filter config can be loaded"
    },
    {
      "name": "redis",
      "status": "disabled",
      "required": false,
      "code": "REDIS_DISABLED",
      "message": "Redis is not enabled for this deployment"
    }
  ]
}
```

Allowed top-level statuses:

- `healthy`: required dependencies are usable.
- `degraded`: required dependencies are usable, but optional or non-core functions have a problem.
- `unhealthy`: required dependency, configuration, migration, or filter config state prevents normal service.

Allowed dependency statuses:

- `healthy`
- `degraded`
- `unhealthy`
- `disabled`
- `unknown`

Fields that must not appear in status responses:

- raw prompt, file content, full masked prompt
- auth token, refresh token, password hash, HMAC secret
- database connection string
- stack trace or raw exception message
- original filename or raw detected value

## 5. HTTP Error Contract

### 5.1 Response Shape

Use fields compatible with RFC 9457 `application/problem+json`, plus safe PromptGuard-specific extension fields.

```json
{
  "type": "https://docs.oasecure.local/problems/validation-error",
  "title": "Validation error",
  "status": 400,
  "detail": "The request body did not match the expected schema.",
  "instance": "/requests/req_...",
  "code": "VALIDATION_ERROR",
  "request_id": "req_...",
  "field_errors": [
    {
      "field": "prompt.content_length",
      "code": "INVALID_LENGTH",
      "message": "content_length must match the submitted prompt length"
    }
  ]
}
```

`detail`, `message`, and `field_errors.message` must be fixed safe text or sanitized text. Do not return the user prompt, file text, raw detected value, secret, stack trace, arbitrary exception string, SQL detail, or internal service detail.

### 5.2 Status Code Guidelines

| Status | Use in PromptGuard | Do not use for |
| --- | --- | --- |
| `400 Bad Request` | malformed JSON, missing required top-level structure, schema parsing failure | authenticated user lacking permission |
| `401 Unauthorized` | missing, invalid, expired, or malformed access token | valid token with insufficient role |
| `403 Forbidden` | authenticated user lacks permission, disabled user, USER calls ADMIN route | cases where existence of cross-workspace resource must be hidden |
| `404 Not Found` | route/resource not found, or intentionally hiding forbidden cross-workspace resource existence | ordinary authentication failure |
| `409 Conflict` | duplicate request conflict or stale filter config version conflict that cannot be processed in the current state | ordinary validation error |
| `413 Payload Too Large` | prompt/file/request body exceeds configured size limit | detection result is Block |
| `415 Unsupported Media Type` | unsupported content type or file type | semantic validation error |
| `422 Unprocessable Content` | syntactically valid but semantically invalid business input, such as invalid custom regex, impossible filter configuration transition, unsupported rule expression | malformed JSON |
| `428 Precondition Required` | optional future use when a filter config version precondition is required but missing | ordinary filter config mismatch better represented by `409` |
| `429 Too Many Requests` | rate limit exceeded | auth failure |
| `500 Internal Server Error` | unexpected server failure; response uses only safe generic text | expected dependency failure |
| `503 Service Unavailable` | required dependency unavailable, migration not ready, server not ready | optional Redis disabled |

403 and 404 distinction:

- Use `403` when the client is authenticated and it is safe for it to know the route/resource exists, but its permissions are insufficient.
- Use `404` when revealing the existence of a workspace-scoped resource would leak tenant information. RFC 9110 allows 404 to hide the existence of a forbidden target.

409 and duplicate requests:

- If the same `client_request_id` arrives with the same authenticated workspace/user/request fingerprint, return the previous safe decision when possible and do not create a second event.
- For `Mask`, do not store `masked_prompt` for replay. If the raw prompt is sent again with the duplicate request, deterministically recompute masking and return a new `masked_prompt`, while reusing the original event/idempotency metadata. If recomputation is impossible, return `409 DUPLICATE_REQUEST_RETRY_REQUIRED` with a safe instruction for the extension to preserve local state or retry the original request.

## 6. Auth, Session, And Permission Contract

This section separately defines the extension bearer-token flow and the dashboard ADMIN session-cookie flow. MV3 extension service worker inactivity is not authentication expiry. The dashboard is ADMIN-only and does not need USER access.

### 6.1 Identifiers And Authentication

- `workspace_id` and `user_id` come from authenticated token/session context, not from request body.
- Raw refresh token values must never be stored; PostgreSQL stores only hash and metadata.
- Chrome Extension MV3 service worker inactivity is not authentication expiry. On wake-up, the extension reads auth metadata and attempts `POST /auth/refresh` before asking for login.
- Disabled users are blocked before protected route execution.
- If an authenticated USER account calls an ADMIN-only route, return `403`.
- Default ADMIN seed:
  - Fresh DB seed/migration creates one default ADMIN account: `admin / 1234`.
  - The password is hashed through the same password hashing function used for normal users.
  - Plaintext `1234` must not be stored in DB, logs, audit metadata, error responses, fixtures, or dashboards.
  - Production documentation must state that `1234` is unsafe and must be changed before real operation.
- Dashboard session authentication is separate from extension bearer-token authentication.
  - The dashboard session is a server-managed ADMIN session id delivered through an `HttpOnly` cookie.
  - HTTPS session cookies use `Secure`.
  - The default for same-site admin UI is `SameSite=Lax`; use `Strict` if cross-site embedding is not needed.
  - The dashboard session id is not stored in `localStorage`.
  - Dashboard state-changing requests apply CSRF protection.

### 6.2 Auth, Session, And Permission Detail Contract

| Item | Default | Reason |
| --- | --- | --- |
| access token TTL | 900 seconds | reduce damage from theft while keeping UX through refresh |
| refresh token TTL | 30 days | do not misread MV3 inactivity as logout |
| refresh idle timeout | 14 days | clean long-abandoned sessions |
| refresh rotation | enabled | revoke previous token hash after refresh |
| refresh reuse detection | enabled | revoke token family and require re-login |

Role/permission matrix:

| Surface | Public | USER | ADMIN |
| --- | --- | --- | --- |
| `/auth/login` | allowed | allowed | allowed |
| `/auth/refresh`, `/auth/logout`, `/auth/me` | not allowed without token | own account in extension token flow | own account in extension token flow |
| `/dashboard/session/login`, `/dashboard/session/csrf` | login/csrf allowed | USER cannot enter dashboard | ADMIN dashboard session allowed |
| `/dashboard/session/logout`, `/dashboard/session/me` | not allowed without ADMIN session | USER cannot enter dashboard | ADMIN dashboard session allowed |
| `/config/extension` | not allowed | allowed | allowed |
| `/prompts/analyze`, `/files/analyze` | not allowed | allowed | allowed |
| `/events`, `/stats/*`, `/status/server` | not allowed | not allowed, `403` | allowed |
| `/admin/users`, `/admin/users/{id}/role`, `/admin/users/{id}/status` | not allowed | not allowed, `403` | allowed |
| `/filters`, `/filters/*`, `/filters/dry-run` | not allowed | not allowed, `403` | allowed |
| cross-workspace resource | not allowed | hide existence with `404` | hide existence with `404` |

Removed or non-MVP flows:

- `seed/readiness` and `default-admin-seed` are not required in v0.10 because the default ADMIN is created by DB seed/migration.
- `/auth/register`, invite signup, workspace-code signup, and open signup are not MVP flows.
- `/invites` and registration settings are not required for the login-first MVP. If old WBS rows remain, reinterpret them as ADMIN-managed user creation, user status/role management, or post-MVP work.

Account statuses:

- `ACTIVE`: protected routes are usable.
- `DISABLED`: access and refresh are denied. Protected routes return `403`.
- `DELETED`: hard delete is excluded from MVP. Use `DISABLED` or anonymized metadata.

### 6.3 Extension Token Auth And Dashboard Session Auth Split

| Category | Extension auth | Dashboard auth |
| --- | --- | --- |
| Main client | Chrome Extension service worker/options | Vanilla TypeScript dashboard SPA |
| Login endpoint | `POST /auth/login` | `POST /dashboard/session/login` |
| Current status | `GET /auth/me` | `GET /dashboard/session/me` |
| Renewal | `POST /auth/refresh` | server-managed session renewal or re-login |
| Logout | `POST /auth/logout` | `POST /dashboard/session/logout` |
| Credential storage | access/refresh metadata in extension storage | `HttpOnly` session cookie |
| CSRF | not applied by default to bearer-token APIs | required for state-changing dashboard requests |
| Failure UX | re-login in options/status UI | redirect to `/login` on session expiry |

The dashboard does not store bearer tokens in `localStorage`. USER accounts cannot open dashboard routes or dashboard APIs.

## 7. API Boundary And Detailed Contract

This section keeps API responsibility boundaries and detailed request/response contracts together. FastAPI/Pydantic/OpenAPI output from `apps/api` is the final machine-readable contract source.

### 7.1 Prompt Analyze Boundary

Endpoint: `POST /prompts/analyze`

Server responsibilities:

- request schema validation
- authenticated workspace/user context
- Analyze Input Bundle normalization only in memory
- unified Filter Rule execution
- risk score calculation
- action decision
- `masked_prompt` generation
- raw-data-free event metadata persistence
- HMAC `prompt_hash`
- duplicate request handling
- safe error responses

Extension responsibilities:

- DOM input extraction
- paste event capture
- attachment metadata capture
- hold before submit
- request body creation
- timeout handling
- Allow/Warn/Mask/Block UX
- apply server-returned `masked_prompt`
- protected resend only when allowed

Request values required: `inputs[]`, `context.ai_service`, `context.ai_service_domain`, `context.page_url_origin`, `context.extension_version`, `context.browser`, `context.locale`, `filter_config_version`, `client_request_id`.

`inputs[]` distinguishes these input kinds:

| kind | Content | Raw/content scan state |
| --- | --- | --- |
| `direct_text` | text read from the composer at send time | `contentScanned: true` |
| `clipboard_text` | normal text captured from the paste event | `contentScanned: true` |
| `large_paste` | large pasted content that is not fully sent/scanned because of size policy | `false` or partial scan depending on policy |
| `attachment_metadata` | file/image/service attachment-chip metadata | `contentScanned: false` |
| `unsupported_attachment` | attachment with missing metadata or unsupported MVP handling | `contentScanned: false` |
| `file_text` | transient text input from a small text file allowed by policy | `contentScanned: true` |

Size-limit names are byte-oriented. Examples: `MAX_DIRECT_TEXT_BYTES`, `MAX_CLIPBOARD_CAPTURE_BYTES`, `MAX_ANALYZE_REQUEST_BYTES`, `MAX_FILE_CONTENT_SCAN_BYTES`. Python/JavaScript string length is not the final contract for user-input size limits.

Request values prohibited: `user_id`, `workspace_id`, full page URL path/query, original filename, secrets in IDs.

Response values required: `event_id`, `request_id`, `risk_score`, `risk_level`, `action`, safe `user_message`, `allow_original_send`, `requires_justification`, metadata-only `detections[]`, optional `business_context_matches[]`, machine-facing `filter_config_version`, optional `masked_prompt` only when `action=Mask`, optional `partial_result`, optional `unscanned_input_kinds[]`.

Response values prohibited: raw prompt echo, raw clipboard text echo, raw file content echo, raw detected value, internal stack trace, arbitrary exception text, full masked prompt persisted in event/dashboard APIs.

Requests containing `contentScanned: false` input must not silently allow the send. The server returns Block, or a user-understandable Warn, and records the unscanned state in raw-data-free event metadata.

### 7.2 File Analyze Boundary

MVP final boundary: `inputs[]` inside `POST /prompts/analyze`

The `POST /files/analyze` boundary described in v0.10 is not expanded into an independent final decision endpoint for the v0.12 MVP. It may remain as an extension compatibility or migration path, but the final file/attachment decision contract is absorbed into `/prompts/analyze inputs[]`.

MVP file scope is text-family files only. PDF, Office documents, OCR, archive extraction, malware scanning, binary analysis, ZIP internal-file analysis, image-content analysis, and Gemini repository deep scan are outside MVP. File content is transient input only and must not be stored, logged, or shown on the dashboard.

Image paste and image files do not receive OCR, pixel inspection, or base64 payload scanning. Represent them as `attachment_metadata` when possible; otherwise represent them as `unsupported_attachment`.

### 7.3 Extension Config Boundary

Endpoint: `GET /config/extension`

Returns `api_base_url`, `filter_rule_set_version`, `timeout_ms`, `ai_service_configs[]`, `file_upload` configuration, and selector config for ChatGPT-family pages. The extension uses server selectors first and keeps fallback selectors.

### 7.4 Dashboard API Boundary

Dashboard APIs are ADMIN-only unless explicitly marked public for login/session. They return metadata only.

Required MVP APIs:

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `POST /auth/login` | public | extension token login |
| `POST /auth/refresh` | refresh token | extension token refresh |
| `POST /auth/logout` | user token | extension token logout |
| `GET /auth/me` | user token | extension user/workspace check |
| `GET /dashboard/session/csrf` | public | CSRF token for dashboard session login/mutations |
| `POST /dashboard/session/login` | public + CSRF | ADMIN dashboard session login |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | dashboard logout |
| `GET /dashboard/session/me` | ADMIN session | current ADMIN session |
| `GET /stats/overview` | ADMIN | overview cards and period statistics |
| `GET /stats/users` | ADMIN | user-level aggregate rows |
| `GET /stats/events` | ADMIN | event/action/detection summary for charts |
| `GET /events` | ADMIN | event list table |
| `GET /events/{event_id}` | ADMIN | raw-data-free event detail |
| `GET /admin/users` | ADMIN | user management list |
| `POST /admin/users` | ADMIN | create USER or ADMIN |
| `PATCH /admin/users/{id}` | ADMIN | update display metadata such as display name/department |
| `PATCH /admin/users/{id}/role` | ADMIN | change USER/ADMIN role |
| `PATCH /admin/users/{id}/status` | ADMIN | set ACTIVE/DISABLED |
| `GET /filters` | ADMIN | unified Filter Rule list |
| `GET /filters/{id}` | ADMIN | Filter Rule detail |
| `POST /filters` | ADMIN | create custom keyword/regex/context rule |
| `PATCH /filters/{id}` | ADMIN | update fields permitted by `editable_fields` |
| `PATCH /filters/{id}/enable` | ADMIN | enable rule |
| `PATCH /filters/{id}/disable` | ADMIN | disable rule |
| `DELETE /filters/{id}` | ADMIN | custom-only archive/delete; built-in delete forbidden |
| `POST /filters/dry-run` | ADMIN | request-only filter preview |
| `GET /status/server` | ADMIN | API/PostgreSQL/Migration/last checked status |

`/filters` is the canonical filter management API for v0.10. Do not add separate custom-filter-only API families unless a later scope explicitly requires them.

### 7.5 Event API Contract

`GET /events` list item fields: `event_id`, `created_at`, `user`, `service`, `action`, `risk_score`, `risk_level`, `detection_category`, `detection_type`, `detection_count`, `detail_available`.

`GET /events/{event_id}` detail fields: `event_id`, `created_at`, `user`, `service`, `platform`, `action`, `risk_score`, `risk_level`, `detection_summary`, `detections[]`, `prompt_hash_prefix`, and `business_context_matches[]` only when applicable.

Dashboard event detail does not show any version identifier; the server may still store `filter_rule_set_version` internally. Event detail response must not include raw prompt, full masked prompt, raw detected value, original filename, prompt excerpt, surrounding context, or stack trace.

Business Context match metadata:

```json
{
  "category": "Contract",
  "reason_code": "CONTRACT_KEYWORDS_AND_MONEY_IN_WINDOW",
  "match_count": 4,
  "matched_keywords": [
    { "keyword": "NDA", "count": 1 },
    { "keyword": "위약금", "count": 1 },
    { "keyword": "계약", "count": 1 }
  ],
  "evidence_counts": {
    "contract_terms": 3,
    "money_terms": 1
  }
}
```

`matched_keywords` is limited to system rule-pack keywords or administrator-configured context-rule keywords. Do not return arbitrary raw spans, prompt excerpts, or surrounding sentences.

### 7.6 User Management API Contract

`GET /admin/users` list item fields: `user_id`, `display_name`, `department`, `role`, `status`, `created_at`, `last_event_at`, `event_count`, `blocked_count`, `masked_count`, `warned_count`.

`POST /admin/users` request:

```json
{
  "email": "member@example.com",
  "password": "<submitted password; never log or echo>",
  "display_name": "Member",
  "department": "Security",
  "role": "USER"
}
```

`PATCH /admin/users/{id}/role` request:

```json
{ "role": "ADMIN" }
```

`PATCH /admin/users/{id}/status` request:

```json
{ "status": "DISABLED" }
```

Hard delete is excluded from MVP. USER accounts must not access `/admin/users` routes and must not modify their own role to ADMIN.

### 7.7 Filter Management API Contract

Filter Rule Management uses one unified `Filter Rule` model. Built-in detector settings, custom keyword/regex filters, and Business Context rules all appear in the same filter list and use the same list/detail/update lifecycle. Execution branches by `source` and `kind`.

Filter Rule common fields:

| Field | Description |
| --- | --- |
| `id` | stable filter id |
| `workspace_id` | workspace scope |
| `source` | `built_in` or `custom` |
| `kind` | `detector`, `keyword`, `regex`, `context_rule` |
| `category` | `Secret`, `PII`, `Business Context`, `Custom` |
| `label` | UI label / detection label |
| `description` | safe description |
| `placeholder` | masking placeholder for applicable filters |
| `detector_key` | stable built-in detector key, read-only |
| `keyword` | custom keyword value, if `kind=keyword` |
| `pattern` | custom regex pattern, if `kind=regex` |
| `severity` | `low`, `medium`, `high`, `critical` |
| `action` | `Allow`, `Warn`, `Mask`, `Block` |
| `enabled` | active flag |
| `editable_fields` | per-field editability map |
| `config_json` | context rule and advanced config |
| `version` | rule version |
| `archived_at` | archived timestamp, if archived |
| `created_by`, `updated_by` | safe actor metadata |
| `created_at`, `updated_at` | timestamps |

Built-in detector rule example:

```json
{
  "id": "filter_builtin_github_token",
  "source": "built_in",
  "kind": "detector",
  "category": "Secret",
  "label": "GitHub Token",
  "detector_key": "secret.github_token",
  "editable_fields": {
    "label": false,
    "pattern": false,
    "keyword": false,
    "enabled": true,
    "severity": true,
    "action": true
  },
  "enabled": true,
  "severity": "critical",
  "action": "Block"
}
```

Built-in detector editable fields: `enabled`, `severity`, `action` only. Do not allow administrators to edit detector regex, checksum logic, entropy calculation, parser code, `detector_key`, or private-key/URI parsing internals.

Custom keyword rule example:

```json
{
  "id": "filter_custom_project_name",
  "source": "custom",
  "kind": "keyword",
  "category": "Custom",
  "label": "Internal Project Name",
  "keyword": "Project Hermes",
  "placeholder": "[INTERNAL_PROJECT]",
  "editable_fields": {
    "keyword": true,
    "enabled": true,
    "severity": true,
    "action": true,
    "label": true,
    "placeholder": true
  },
  "enabled": true,
  "severity": "high",
  "action": "Mask"
}
```

Custom regex rule example:

```json
{
  "id": "filter_custom_ticket_id",
  "source": "custom",
  "kind": "regex",
  "category": "Custom",
  "label": "Internal Ticket Number",
  "pattern": "INC-[0-9]{6}",
  "placeholder": "[INTERNAL_TICKET]",
  "editable_fields": {
    "pattern": true,
    "enabled": true,
    "severity": true,
    "action": true,
    "label": true,
    "placeholder": true
  },
  "enabled": true,
  "severity": "medium",
  "action": "Warn"
}
```

Regex validation before save: syntax validation, length limit, timeout or safe-regex strategy, catastrophic backtracking/ReDoS defense, and dry-run validation when applicable.

Context rule example:

```json
{
  "id": "filter_context_contract",
  "source": "built_in",
  "kind": "context_rule",
  "category": "Business Context",
  "label": "Contract",
  "config_json": {
    "keyword_groups": [
      {
        "name": "contract_terms",
        "keywords": ["계약", "NDA", "위약금", "갱신", "해지", "견적", "제안서"],
        "min_count": 1
      },
      {
        "name": "money_terms",
        "keywords": ["원", "만원", "억", "%", "할인", "월", "년", "개월"],
        "min_count": 1
      }
    ],
    "exclusion_keywords": ["샘플", "교육용", "공개 약관"],
    "window_size": 500,
    "min_condition_count": 2,
    "sensitivity": "medium",
    "advanced_weights": {
      "keyword_group_weight": 10,
      "money_expression_weight": 15
    }
  },
  "editable_fields": {
    "keyword_groups": true,
    "exclusion_keywords": true,
    "window_size": true,
    "min_condition_count": true,
    "sensitivity": true,
    "advanced_weights": true,
    "severity": true,
    "action": true,
    "enabled": true
  },
  "severity": "high",
  "action": "Mask",
  "enabled": true
}
```

Context rule basic controls: label, keyword groups, exclusion keywords, window size, minimum condition count, sensitivity `low/medium/high`, severity, action, enabled. Advanced controls: scoring weights. MVP does not expose LLM prompt editing.

`POST /filters/dry-run` request and response:

```json
{
  "filter_type": "context_rule",
  "draft_filter": {
    "label": "Contract",
    "keyword_groups": [
      {
        "name": "contract_terms",
        "keywords": ["계약", "NDA", "위약금"],
        "min_count": 1
      }
    ],
    "window_size": 500,
    "min_condition_count": 1,
    "sensitivity": "medium",
    "severity": "high",
    "action": "Mask"
  },
  "sample_text": "<request-only sample text; never store or log>"
}
```

```json
{
  "matched": true,
  "expected_action": "Mask",
  "expected_severity": "high",
  "match_count": 3,
  "reason_code": "CONTRACT_KEYWORDS_IN_WINDOW",
  "matched_keywords": [
    { "keyword": "계약", "count": 1 },
    { "keyword": "NDA", "count": 1 },
    { "keyword": "위약금", "count": 1 }
  ],
  "evidence_counts": {
    "contract_terms": 3
  },
  "sample_persisted": false
}
```

Dry-run sample text, raw detected values, prompt excerpts, surrounding context, file content, and original filenames must not be stored or logged.

Filter API errors:

| Case | Status |
| --- | --- |
| USER calls filter API | `403` |
| filter id not found | `404` |
| built-in detector pattern/checksum/parser edit attempted | `422` |
| invalid role/field/action/severity | `422` |
| risky regex or ReDoS risk | `422` |
| dry-run sample too large | `413` |
| duplicate filter label where uniqueness is required | `409` |

### 7.8 Server Status API

`GET /status/server` returns only UI-needed status metadata: API status, PostgreSQL status, Migration status, last_checked, and optional small version metadata. Dashboard status UI does not show Filter Config or Environment by default. `/readyz` may still include filter/config load internally as a readiness condition.

## 8. Product Scope And Repository Structure

This section defines the product MVP boundary and code locations. Implementation details follow the API, data, detection, extension, and dashboard sections.

### 8.1 Product Scope

- Product purpose:
  - Detect risk before a user sends sensitive business information, personal data, secrets, contract information, or file content to AI services such as ChatGPT.
  - Do not permanently store raw source text on the server; show admins only metadata and statistics.
  - In a self-hosted environment, an admin operates the server and DB, and team members use the protected flow through the Chrome extension.
- MVP includes:
  - self-hosted server runtime, seeded default ADMIN login, ADMIN-managed user creation/status/role management.
  - Chrome extension input detection for ChatGPT, submit hold, Analyze API call, Allow/Warn/Mask/Block handling.
  - Python Analyze API, rule-based detectors, unified Filter Rule model, risk score, server-side masking, duplicate request handling, prompt hash.
  - ADMIN dashboard login, overview, event metadata, user management/stats, filter rule management, and status screens.
  - Privacy/security regression tests, Docker-based runtime, installation docs, final smoke scenario.
- MVP excludes:
  - first-admin setup page and any user-facing first-admin creation flow.
  - self signup, invite signup, workspace-code signup, open signup.
  - user hard delete.
  - dashboard common filters and advanced drill-down filters.
  - external LLM-call-based classification.
  - PDF/Office/OCR/archive/binary file analysis.
  - browser network-request interception.
  - SaaS multi-tenant operation, billing, enterprise organization management.
  - SIEM integration, SSO, advanced filter configuration workflow.

### 8.2 Repository And Code Locations

| Major area | Subarea | Default location | Description |
| --- | --- | --- | --- |
| API server | Python 3.13 self-hosted API | `apps/api/` | `python:3.13-slim` baseline with FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. Includes API schema, auth, detectors, unified filter rules, masking, event service. |
| Dashboard | Vanilla TypeScript SPA admin UI | `apps/dashboard/` | `apps/dashboard/src/**/*.ts` is the implementation source. Use plain HTML, CSS, and TypeScript without React, Vue, Svelte, or Next.js, then smoke-check the Vite/tsc build output. Includes login, overview, events, users, filters, status screens. |
| Extension | Chrome Extension | `apps/extension/` | content script, service worker, options, shared types/tests, and real API alignment. |
| Infrastructure | Docker/env/reverse proxy | `infra/` | Docker Compose, PostgreSQL, optional Redis profile, reverse proxy examples. |
| Tests | Integration/security/regression | each app `tests/` or root tests | app-level unit tests and cross-app privacy/security smoke tests. |

Recommended dashboard file structure:

```text
apps/dashboard/
  index.html
  src/pages/login.ts
  src/pages/overview.ts
  src/pages/events.ts
  src/pages/users.ts
  src/pages/filters.ts
  src/pages/status.ts
  src/api/client.ts
  src/api/events.ts
  src/api/users.ts
  src/api/filters.ts
  src/api/status.ts
  src/components/table.ts
  src/components/modal.ts
  src/components/toast.ts
  src/components/loading.ts
  src/components/error-state.ts
  src/state/session.ts
  src/styles/
```

## 9. Data Model And Raw-Data Prohibition Contract

The data model is based on metadata-only persistence. Raw prompts, raw file contents, full `masked_prompt`, raw detected values, prompt excerpts, surrounding context, and original filenames must not be stored or exposed through DB, logs, dashboard, or error responses.

### 9.1 Data Model Subscope

- Account/organization:
  - `workspaces`: self-hosted workspace unit.
  - `users`: email/username, display name, department, role, status, password hash metadata.
  - `refresh_tokens`: raw token storage prohibited; store only hash and expiry/revocation metadata.
- Filter configuration:
  - `filter_rules`: unified filter rule model for built-in detectors, custom keyword/regex filters, and Business Context context rules.
  - `filter_rule_versions`: immutable change history for filter rules.
  - `ai_service_configs`: ChatGPT-family domains and selector/config.
- Analysis events:
  - `analysis_events`: event id, workspace/user id, action, risk score, risk level, prompt hash, internal filter rule set version, service metadata, created_at.
  - `event_detections`: detection category/type, source, filter_rule_id, reason_code, match_count, matched_keywords, evidence_counts, severity, action, safe_evidence.
  - `event_feedback`: user confirmation/reason metadata. Raw source prohibited.
  - `audit_logs`: auth/admin/filter/user action metadata. Raw request body prohibited.
- Prohibited columns:
  - Do not create columns such as `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, `raw_detected_value`, `original_filename`, `secret_value`, `token_raw`, `password_plain`.

### 9.2 Data Model Detail Contract

| Table | Core columns | Constraints |
| --- | --- | --- |
| `workspaces` | `id`, `name`, `created_at`, `status` | `id` primary key |
| `users` | `id`, `workspace_id`, `email`, `username`, `display_name`, `department`, `role`, `status`, `password_hash`, `created_at`, `updated_at`, `last_event_at` | unique username/email per workspace; hard delete excluded |
| `refresh_tokens` | `id`, `workspace_id`, `user_id`, `token_hash`, `family_id`, `expires_at`, `idle_expires_at`, `revoked_at`, `reused_at`, `created_at` | raw token storage prohibited |
| `ai_service_configs` | `id`, `workspace_id`, `service`, `domain`, `selector_config`, `enabled`, `version` | extension config source |
| `filter_rules` | `id`, `workspace_id`, `source`, `kind`, `category`, `label`, `description`, `detector_key`, `keyword`, `pattern`, `placeholder`, `severity`, `action`, `enabled`, `editable_fields`, `config_json`, `version`, `archived_at`, `created_by`, `updated_by`, `created_at`, `updated_at` | unified Filter Rule model |
| `filter_rule_versions` | `id`, `filter_rule_id`, `workspace_id`, `version`, `change_type`, `before_json`, `after_json`, `changed_by`, `created_at` | safe change history; no sample text |
| `idempotency_keys` | `id`, `workspace_id`, `user_id`, `client_request_id`, `request_fingerprint`, `event_id`, `created_at`, `expires_at` | duplicate event prevention |
| `analysis_events` | `id`, `workspace_id`, `user_id`, `prompt_hash`, `action`, `risk_score`, `risk_level`, `filter_rule_set_version`, `service`, `service_domain`, `platform`, `created_at` | raw prompt/full mask storage prohibited |
| `event_detections` | `id`, `event_id`, `category`, `type`, `source`, `filter_rule_id`, `severity`, `confidence`, `count`, `reason_code`, `match_count`, `matched_keywords`, `evidence_counts`, `safe_evidence` | raw detected value prohibited |
| `event_feedback` | `id`, `event_id`, `user_id`, `feedback_type`, `reason_code`, `created_at` | free text reason disabled or redacted in MVP |
| `audit_logs` | `id`, `workspace_id`, `actor_user_id`, `action`, `target_type`, `target_id`, `safe_metadata`, `created_at` | raw request body prohibited |

Default ADMIN seed:

- The seed/migration creates a default ADMIN user `admin / 1234` with `role=ADMIN` and `status=ACTIVE`.
- Store only `password_hash`.
- The seed must be idempotent and must not create duplicate `admin` users on restart.
- Later ADMIN users are allowed through `/admin/users`; do not enforce a global unique `role=ADMIN` constraint.

Filter Rule storage rules:

- Built-in detector internals such as regex/checksum/parser/entropy logic are not stored in DB. Store `detector_key` and workspace override values only.
- Custom keyword/regex/context-rule configuration may be stored.
- Custom regex pattern may be stored, but raw match value must not be stored.
- Context rule `keyword_groups`, `exclusion_keywords`, `window_size`, `min_condition_count`, `sensitivity`, and `advanced_weights` are stored in `config_json` or normalized child tables if needed.
- Business Context matched keyword counts are safe metadata and may be stored in `event_detections` because they refer to configured rule keywords, not arbitrary prompt spans.
- Matched keywords can be sensitive internal terms; dashboard access is ADMIN-only.

Migration order:

1. workspace/user base tables and default ADMIN seed
2. refresh token/auth tables
3. ai service config tables
4. unified `filter_rules` and `filter_rule_versions`
5. idempotency/event/detection/feedback/audit tables
6. seed: built-in detector filter rules, built-in context rules, default workspace/config
7. privacy schema scan for prohibited columns

### 9.3 DB Relationships, Indexes, And Delete Filter Config

| Relationship | Standard |
| --- | --- |
| `workspaces 1:N users` | every user belongs to a workspace |
| `users 1:N refresh_tokens` | refresh token family is bound to user and workspace |
| `workspaces 1:N filter_rules` | every filter rule is workspace-scoped |
| `filter_rules 1:N filter_rule_versions` | filter changes remain as version/audit metadata |
| `analysis_events 1:N event_detections` | event has raw-data-free detection summaries |
| `analysis_events 1:N event_feedback` | only user confirmation/reason metadata is stored |

Required indexes:

| Table | Constraint/index | Reason |
| --- | --- | --- |
| `users` | unique `(workspace_id, lower(email))`, unique `(workspace_id, lower(username))` if username is used | prevent duplicate account identifiers |
| `refresh_tokens` | unique `token_hash`, index `(user_id, family_id)` | token rotation/reuse detection |
| `filter_rules` | index `(workspace_id, enabled)`, `(workspace_id, source, kind)`, optional unique `(workspace_id, label, archived_at)` | filter list and pipeline load |
| `filter_rule_versions` | index `(filter_rule_id, version)` | change history |
| `idempotency_keys` | unique `(workspace_id, user_id, client_request_id)` | duplicate event prevention |
| `analysis_events` | index `(workspace_id, created_at)`, `(workspace_id, user_id, created_at)`, `(workspace_id, action, created_at)` | dashboard list/stat query |
| `event_detections` | index `(event_id)`, `(category)`, `(type)`, `(filter_rule_id)` | detail/stat aggregate |
| `audit_logs` | index `(workspace_id, created_at)`, `(actor_user_id, created_at)` | admin audit |

Delete/disable rules:

- MVP does not hard-delete users. Use `DISABLED` status.
- Built-in filter rules cannot be deleted.
- Filter rule rules and context rules may be disabled or archived. Hard delete is optional and should not break historical event metadata.
- Event rows contain privacy-safe metadata and may be deleted by retention rule.
- Audit logs store only action/target/safe_metadata.

## 10. Detection, Masking, Scoring, And Filter Rule Contract

Detection and masking are server responsibilities. The extension holds submit and applies the server-returned action and `masked_prompt`.

### 10.1 Pipeline Order

1. request schema validation
2. workspace/user/config load
3. transient text normalization
4. built-in detector execution through Filter Rules with `source=built_in`, `kind=detector`
5. custom keyword filter execution
6. custom regex filter execution
7. context rule execution
8. overlap merge
9. risk scoring
10. action decision
11. masking generation
12. metadata-only event logging
13. safe response

### 10.2 Detector And Filter Rule Types

- Built-in detector rules:
  - Secret: API Key, GitHub Token, AWS Key, JWT, DB Connection String, `.env` Secret, Private Key, High Entropy Token.
  - PII: Phone Number, ID Number, Email, Card Number, Business Registration Number.
  - Built-in internals are code-backed and not administrator-editable.
- Custom keyword rules:
  - administrator-defined exact/contains/case-insensitive keyword matchers.
- Custom regex rules:
  - administrator-defined pattern filters with safe-regex validation.
- Context rules:
  - Business Context categories such as Contract, Penalty, NDA, Customer Info, Trade Secret, Internal Strategy, Launch Plan, Pricing Strategy.
  - Rule-based evidence scoring only. No free-form LLM prompt editing in MVP.

### 10.3 Context Rule Scoring

Context rules split text into sentence/paragraph/window units. Each window is evaluated using keyword groups, exclusion keywords, structured evidence such as money/period/ratio expressions, and detector outputs.

Context rule controls:

- label
- keyword groups
- exclusion keywords
- window size
- minimum condition count
- sensitivity: `low`, `medium`, `high`
- severity
- action
- enabled
- advanced scoring weights

Default UI exposes sensitivity. Advanced settings expose weights.

Context detection output includes `category`, `reason_code`, `evidence_counts`, `matched_keywords`, `match_count`, `severity`, and `action`. It must not include raw prompt spans, nearby sentences, or prompt excerpts.

### 10.4 Overlap And Priority

- Secret detection has priority over general business context.
- Within the same priority, longer span wins.
- Overlapping detections are not double-counted in response or statistics.
- Context rule evidence does not create stored raw spans; it stores safe evidence counts and configured keyword counts.

### 10.5 Risk And Action Decision

The server orchestrator, not individual detectors, makes the final action decision. The same input, workspace, active Filter Rule set, and scoring configuration must produce the same result.

| Detection | Base score | Base action |
| --- | ---: | --- |
| confirmed secret: API key, private key, DB URI, JWT | 90 | Block or Mask; default rule prioritizes Block for secrets |
| confirmed credential-like `.env` secret | 85 | Mask |
| strong PII such as Korean RRN/card/business id | 80 | Mask |
| email/phone alone | 45 | Warn |
| contract amount/penalty/NDA context | 65 | Warn or Mask |
| customer information/trade secret/internal strategy context | 65 | Warn or Mask |
| ambiguous low confidence | 30 | Allow or Warn |
| filter rule critical | 90 | rule action takes priority |
| filter rule high | 70 | rule action takes priority |

### 10.6 Masking

- Masking uses server-generated `masked_prompt`, not frontend ad-hoc detection.
- Include `masked_prompt` only for Mask action.
- Do not store `masked_prompt` in event rows or dashboard APIs.
- Repeated identical sensitive values use the same placeholder.
- Placeholder examples: `[SECRET_1]`, `[EMAIL_1]`, `[CONTRACT_AMOUNT_1]`, `[INTERNAL_PROJECT_1]`.

### 10.7 Filter Rule Versioning And Dry-run

- Any change to enabled/severity/action/keyword/pattern/context config creates a new filter rule version.
- Dry-run sample text is request-only and is not stored.
- Dry-run output may show safe match counts, reason codes, expected action, expected severity, and configured matched keywords.
- Raw match values, prompt excerpts, surrounding context, file content, and original filenames are never stored or displayed.

## 11. Extension Contract

The extension detects input on ChatGPT-family pages, holds submit, then handles UX and resend according to the real self-hosted API decision.

### 11.1 Extension Subscope

- Content script:
  - Runs only on target domains.
  - Finds textarea and contenteditable candidates and selects the current composer based on visible/focus criteria.
  - Holds send-button click and Enter submit until analysis completes.
  - Does not misread writing-assistance actions such as `@` mention, IME composition, Shift+Enter newline, or GPT picker as submit.
- Service worker:
  - Owns API base URL, token, selector/filter config cache, timeout, and auth error handling.
  - Creates request bodies according to the Analyze API contract and does not inject workspace/user ids manually.
  - Treats MV3 service worker inactivity as normal lifecycle, not as login expiry.
  - On wake-up, reads stored auth/session metadata and attempts automatic refresh first when access token is expired.
  - Requires re-login in options page/status UI only when refresh failure is confirmed.
- Options page:
  - self-host API URL storage.
  - connection test.
  - login/logout/refresh status.
  - server status and filter config sync time.
  - Does not show service worker inactivity itself as an error.
  - Shows user action required only for real auth failures such as refresh token expiry/revocation/reuse, disabled account, or server change.
- Action UX:
  - Allow: replay the original send once.
  - Warn: hold before confirmation, send after confirmation.
  - Mask: replace the composer with the server-provided `masked_prompt` and let the user send again.
  - Block: do not trigger original submit.
  - Passing Allow should not show unnecessary panels.

## 12. Dashboard Contract

The dashboard is an ADMIN-only metadata UI. Overview, events, users, filter rule management, and server status screens show only aggregates and safe metadata, never raw source data. The dashboard frontend is a Vanilla TypeScript SPA under `apps/dashboard/`; it uses plain HTML, CSS, and TypeScript without React, Vue, Svelte, Next.js, or other frontend frameworks. The source of truth is `apps/dashboard/src/**/*.ts` and source assets; `dist/` is generated build output. Review and completion decisions check TypeScript source, `npm run typecheck`, `npm run build`, and a built-output smoke check together.

### 12.1 Dashboard Screens

Login page:

- ID/PW input
- login button
- redirect to login on session expiry
- no current-admin display required for MVP
- no detailed login/server failure UX required for MVP

Overview:

- cards: Total Events, Blocked, Masked, Warned, Active Users
- charts: event statistics, user statistics, period statistics
- buttons: Events, User Management, Filter Rule Management, Server Status, Logout
- dashboard-wide filters are excluded from MVP

Events:

- table columns: time, user, service, action, risk level, detection category, detection type, detail action
- detail panel/modal fields: event ID, time, user, service, platform, action, risk score, risk level, detection summary, detection items, `prompt_hash_prefix`
- internal filter rule set version is not shown in the event detail UI, although the server may store it internally
- detection summary and evidence summary are one UI block named `Detection Summary`
- Business Context details may show configured matched keywords and counts; raw prompt excerpt and surrounding context are prohibited

Users:

- columns: user ID, display name, department, role, status, last event time, created at, event count, Blocked, Masked, Warned, edit button, disable button
- hard delete excluded; disable user instead
- row click opens paginated user event list

Filter Rule Management:

- one filter list containing built-in detector rules, custom keyword rules, custom regex rules, and context rules
- display source/kind/category
- built-in detector edit form allows only enabled/severity/action
- custom keyword form allows keyword/label/placeholder/severity/action/enabled
- custom regex form allows pattern/label/placeholder/severity/action/enabled and shows regex validation errors
- context rule form allows keyword groups, exclusion keywords, window size, minimum condition count, sensitivity low/medium/high, severity/action/enabled, and advanced scoring weights
- dry-run panel shows expected result and does not store sample text
- built-in filters cannot be deleted; filter rules/context rules can be disabled or archived

Server Status:

- show API, PostgreSQL, Migration, Last Checked
- version may be shown as small metadata
- do not show Filter Config or Environment by default
- statuses: healthy, degraded, unhealthy, disabled, unknown
- disabled applies only to optional features, not API/PostgreSQL/Migration



Clarification:

- Event detail UI must never show `filter_config_version`, `filter_rule_set_version`, or any other version identifier.
- The server may store internal version metadata only for reproducibility, audits, and debugging.
- Filter Rule Management is the only admin screen for detection configuration. Do not add a separate configuration screen.

### 12.2 Dashboard Screen Contract

| Screen | Route | APIs used | Required UI | Empty state | Loading state | Error state | Permission | Test/verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Login | `/login` | `POST /dashboard/session/login`, `GET /dashboard/session/me` | ID/PW inputs, login button | already logged in redirects to dashboard | login request pending | session expired redirects to login | public/ADMIN session | no localStorage session, CSRF/session cookie |
| Overview | `/dashboard` | `GET /stats/overview`, `GET /stats/users`, `GET /stats/events` | cards, event/user/period charts, navigation buttons, logout | no events | skeleton/spinner | safe error banner | ADMIN | cards/charts render metadata only |
| Events | `/events` | `GET /events`, `GET /events/{event_id}` | event table and detail panel/modal | no events | table/detail loading | safe API errors | ADMIN | no version identifiers shown in UI, no raw source |
| Users | `/users` | `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}`, `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/status` | user list, add/edit/disable, user event list | no users/events | table/form loading | validation/RBAC errors | ADMIN | hard delete absent, USER 403 |
| Filters | `/filters` | `GET /filters`, `GET /filters/{id}`, `POST /filters`, `PATCH /filters/{id}`, `PATCH /filters/{id}/enable`, `PATCH /filters/{id}/disable`, `DELETE /filters/{id}`, `POST /filters/dry-run` | unified filter list, forms, dry-run panel | no filters | list/form loading | regex/editable_fields/dry-run errors | ADMIN | source/kind rules enforced, sample not stored |
| Status | `/status` | `GET /status/server` | API/PostgreSQL/Migration/Last Checked, optional small version | unknown info | polling/loading | unhealthy/degraded/unknown display | ADMIN | no secrets, DB URL, stack trace, filter config/env default UI |

### 12.3 MVP Dashboard API And Statistics Contract

The MVP dashboard is not a raw-source review tool. Every dashboard API is metadata-only.

Statistic definitions:

- `event_count`: number of `analysis_events` rows matching a fixed MVP range.
- `active_user_count`: distinct `user_id` with at least one event in the selected/default period.
- `blocked_count`, `masked_count`, `warned_count`: action-specific counts.
- `top_detector_category`: aggregate by event_detections category.
- `period bucket`: aggregate by stored UTC values; convert to browser timezone only for display.

MVP does not require dashboard-wide filter controls, but API design should remain compatible with future filters through cursor/range parameters.

## 13. Security And Privacy Contract

### 13.1 Practical Controls

- Request body logging is disabled by default or processed through raw-source removal.
- Access logs record only safe method, path template, status, latency, request id, user/workspace id when safe.
- Error handlers do not serialize raw exception objects.
- All secrets come from environment variables, Docker secrets, or later secret-manager integration; they are not committed.
- PostgreSQL migrations must be reviewable and reproducible.
- Auth tokens, refresh tokens, HMAC keys, password hashes, DB URLs, and API keys are not exposed through health/status/error/dashboard.
- CORS allowlist is explicit. Credentialed wildcard CORS is not allowed.
- Single-instance MVP rate limiting starts without Redis. Add Redis only when a concrete need is confirmed.
- Custom regex filters need length limits, syntax validation, timeout or safe regex engine strategy, and ReDoS tests.
- Dashboard APIs return metadata only.

### 13.2 Required Regression Tests Before MVP Release

- DB schema scan: no `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, or raw detected value columns.
- Log scan: seeded prompt/file/secret values must not appear in application/access/error logs.
- Error scan: validation/server errors must not echo request body or stack trace.
- Dashboard scan: events/details/user stats must not show raw prompt, masked prompt, original filename, or raw detected value.
- Idempotency test: duplicate `client_request_id` creates only one event.
- HMAC test: same workspace+prompt yields the same `prompt_hash`; different workspace yields different hash.
- Auth/RBAC test: USER cannot access ADMIN routes, and disabled user is blocked.
- Health/status test: `/readyz` fails if PostgreSQL or migration is unavailable. Optional Redis disabled is not degraded.

Privacy fixture matrix:

| Fixture id | Seeded value | Use location | Must not appear in | Passing criterion |
| --- | --- | --- | --- | --- |
| `privacy_prompt_contract_amount` | `NDA 위약금은 3억원입니다` | `/prompts/analyze` request | DB event row, app/access/error log, dashboard DOM/API, problem detail | raw sentence absent; only metadata category/count exists |
| `privacy_secret_github_token` | dummy shaped like `ghp_testsecret1234567890abcdef` | analyze/file/filter rule dry-run | DB/log/error/dashboard/API response except safe detection summary | raw token absent; `category=api_key` summary allowed |
| `privacy_file_text` | `고객사 담당자 전화번호 010-0000-0000` | `file_text` in `/prompts/analyze inputs[]` or compatibility `/files/analyze` input | DB/log/dashboard/event detail/original filename fields | raw file text absent; phone detection count allowed |
| `privacy_masked_prompt` | mask response containing `[SECRET_1]` | Mask response only | `analysis_events`, dashboard event/detail/stats, logs | full masked prompt absent from persistence/display |
| `privacy_filter_rule_sample` | dry-run sample sentence | `/filters/dry-run` request | filter rule tables, event tables, logs | sample not persisted; match count only |
| `privacy_error_echo` | invalid request body with seeded secret | validation/error path | `detail`, `message`, `field_errors.message`, logs | fixed safe error only |
| `privacy_status_secret` | dummy DB URL/JWT/HMAC secret env | health/status/error | `/healthz`, `/status/server`, logs | secret value absent; safe dependency code only |

Privacy test implementation requirements:

- Tests collect seed values in one fixture module, and DB/log/API/dashboard scans use the same seed list.
- Scans check exact strings and URL/base64/JSON-escaped variants.
- Dashboard privacy tests check both API response and rendered DOM.
- If a privacy scan fails, that slice cannot pass the release gate regardless of functional behavior.

### 13.3 Security / Privacy Subscope

- Raw-source prohibition:
  - raw prompt/file content may enter the request, but must not remain in storage, logs, dashboard, error responses, or memory/session logs.
  - request body logging is blocked or redacted by default.
- Authentication/authorization:
  - the extension uses bearer token + refresh token flow.
  - the dashboard uses server-managed session-cookie flow.
  - Dashboard session cookie uses `HttpOnly`, and `Secure` under HTTPS.
  - Dashboard session starts with `SameSite=Lax`; consider `Strict` if cross-site is not needed.
  - Dashboard state-changing requests must pass CSRF token validation.
  - Dashboard session id is not stored in `localStorage`.
  - access token is short-lived; only refresh token hash is stored.
  - ADMIN/USER routes are separated, and cross-workspace access may use 404 hiding.
- Errors:
  - error responses return safe problem details only.
  - stack trace, SQL detail, raw exception message, and request body echo are prohibited.
- Network:
  - MVP detectors do not call external LLMs.
  - CORS uses explicit allowlist; credentialed wildcard is prohibited.
- Rule execution:
  - regex length/syntax/time limit/ReDoS tests are required.
  - file size and request size limits are required.

## 14. File Analysis Limits And Environment Contract

File analysis limits and environment variables are separate from test commands. File content is raw input just like prompt text: use it only during server processing and do not store it.

### 14.1 File Analysis Limits

- MVP supports text files only.
- Default allowed extensions: `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.log`.
- Default allowed MIME: `text/*`, `application/json`, `application/x-yaml`.
- Default maximum file size: 256 KiB.
- Default maximum request body: 512 KiB.
- Encoding: UTF-8 first; return `415` or `422` on failure.
- If binary sniffing finds null bytes or high binary ratio, return `415`.
- Original filename is not stored. If needed, the extension uses it only for local-only display.

### 14.2 Environment Variable Contract

| Variable | Required | Example | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql+psycopg://promptguard:promptguard@postgres:5432/promptguard` | PostgreSQL connection |
| `PROMPTGUARD_ENV` | yes | `self-host-dev` | environment name |
| `PROMPTGUARD_HMAC_SECRET` | yes | `dev-only-change-me` | prompt_hash HMAC secret; do not commit production value |
| `PROMPTGUARD_JWT_SECRET` | yes | `dev-only-change-me` | access token signing secret |
| `PROMPTGUARD_REFRESH_SECRET` | yes | `dev-only-change-me` | refresh token hash pepper |
| `ACCESS_TOKEN_TTL_SECONDS` | no | `900` | access token TTL |
| `REFRESH_TOKEN_TTL_DAYS` | no | `30` | refresh token TTL |
| `REFRESH_IDLE_TIMEOUT_DAYS` | no | `14` | refresh idle timeout |
| `CORS_ALLOWED_ORIGINS` | yes | `chrome-extension://...,http://localhost:5173` | explicit allowlist |
| `MAX_DIRECT_TEXT_BYTES` | no | `65536` | direct composer text byte limit |
| `MAX_CLIPBOARD_CAPTURE_BYTES` | no | `65536` | paste-event clipboard text capture byte limit |
| `MAX_ANALYZE_REQUEST_BYTES` | no | `524288` | full analyze request body byte limit |
| `MAX_FILE_CONTENT_SCAN_BYTES` | no | `262144` | small text-file transient scan byte limit |
| `MAX_FILE_BYTES` | no | `262144` | file body limit |
| `REDIS_URL` | no | empty | used only in optional profile |

## 15. Tests, Done Definition, And Release Gates

This section defines completion criteria. Even if partial feature code exists, MVP is not complete unless fresh install, privacy regression, real API/extension/dashboard smoke all pass.

### 15.1 Test / Done Criteria Subscope

API tests:

- default ADMIN seed creates exactly one `admin` account on fresh DB.
- default ADMIN password is stored only as hash.
- `admin / 1234` can log in in local/fresh install flow.
- USER dashboard access returns `403` or redirects to login according to session state.
- ADMIN dashboard access works.
- `/admin/users` can create USER/ADMIN accounts.
- `/admin/users/{id}/role` can promote USER to ADMIN.
- `/admin/users/{id}/status` can disable a user.
- USER cannot change own role to ADMIN.
- schema validation, health/status/error contract, detector/masking/scoring/idempotency, and unified Filter Rule APIs pass.

Dashboard tests:

- login ID/PW succeeds.
- session expiry redirects to login.
- overview shows total events, blocked, masked, warned, active users.
- overview renders event/user/period charts and logout button.
- events table renders detection category/type.
- event detail panel/modal opens.
- event detail does not show any version identifier.
- Business Context detail shows matched configured keyword count.
- raw prompt/full masked prompt/raw detected value/original filename are absent.
- users page shows last event time and disables users instead of hard delete.
- user row opens paginated user event list.
- filters page shows source/kind/category.
- built-in detector allows only enabled/severity/action edits.
- custom keyword/regex/context_rule CRUD works.
- context rule sensitivity low/medium/high works; scoring weights are advanced settings.
- dangerous regex is rejected.
- dry-run sample is not stored and dry-run output shows safe result metadata.
- status page shows API/PostgreSQL/Migration/Last Checked and optional small version. Filter Config/Environment are not default UI fields.

Privacy regression:

- DB schema scan: no `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, raw detected value, original filename columns.
- Log scan: seeded prompt/file/secret values absent.
- Error scan: validation/server errors do not echo request body or stack trace.
- Dashboard scan: events/users/filters/status pages do not show raw prompt, file content, full masked prompt, raw detected value, original filename, or prompt excerpts.
- Business Context configured matched keyword and count may appear in ADMIN event detail.

### 15.2 MVP Done Definition

MVP completion means this fresh-install flow passes:

1. Admin starts API and PostgreSQL with default Docker Compose.
2. `/readyz` confirms PostgreSQL connection, current migrations, default config/filter seed readiness.
3. DB seed/migration creates default ADMIN `admin / 1234`; only password hash is stored.
4. The default route opens the login page.
5. ADMIN logs into the dashboard.
6. ADMIN can access overview, events, users, filters, and status screens.
7. ADMIN creates USER or ADMIN through `/admin/users`.
8. USER logs into the extension but cannot access dashboard routes.
9. Extension calls `/auth/me`, `/config/extension`, `/prompts/analyze` against real self-host API.
10. ChatGPT composer click/Enter submit is held before analysis completion.
11. Allow/Warn/Mask/Block results behave according to contract.
12. Mask replaces the composer with server-returned `masked_prompt`; server does not store full `masked_prompt`.
13. Dashboard overview shows event/action/user/period metadata.
14. Event detail shows detection summary and Business Context configured matched keyword counts when applicable, but no raw source text.
15. Filter Rule Management uses unified Filter Rule model and enforces editable_fields.
16. API, dashboard, extension tests, privacy regression, Docker fresh-install smoke, and final demo scenario all pass.

MVP release gates:

| Gate | Completion criterion | On failure |
| --- | --- | --- |
| Install | fresh clone/export starts API/PostgreSQL via `.env.example` | fix install docs and compose/env first |
| DB | Alembic migration/seed succeeds on fresh DB and restart | fix migration before feature work |
| Auth | login/refresh/logout/auth/me/RBAC and default ADMIN seed tests pass | block dashboard/extension integration |
| Analyze | schema validation, detector, scoring, masking, idempotency, event metadata pass | do not mark dashboard stats/extension smoke complete |
| Filters | unified `filter_rules`, `filter_rule_versions`, dry-run, editable_fields, regex safety tests pass | block filter UI completion |
| Dashboard | overview/events/users/filters/status work metadata-only | release prohibited if raw-data scan fails |
| Extension | selector, click/Enter, `@` mention exception, Allow/Warn/Mask/Block, 401 refresh, real API smoke pass | re-verify real ChatGPT smoke |
| Privacy | seeded sensitive value absent from DB/log/error/dashboard/API response scan | release prohibited |
| Release gate | API/dashboard/extension build/test, Docker smoke, no external LLM call, final demo pass | do not mark MVP complete |

### 15.3 Test Command Matrix

| Area | Command | Completion criterion |
| --- | --- | --- |
| API unit/integration | `cd apps/api && pytest` | auth/RBAC/analyze/filter/status/error/privacy tests pass |
| API privacy scan | `cd apps/api && pytest tests/privacy` | seeded sensitive values absent from DB/log/error responses |
| Dashboard | `cd apps/dashboard && npm run typecheck`, `npm run build`, `npm test`, built-output smoke | TypeScript source typechecks/builds, and generated output renders login, overview, events, users, filters, and status as metadata-only UI |
| Extension | `python apps/extension/tests/run_extension_checks.py all` | selector, hook, action UX, auth refresh, API client fixture pass |
| Root build | `npm run build --workspaces` | dashboard/extension JS build pass; Python API verified by pytest/compose |
| Docker smoke | after `docker compose up --build`, run health checks | `/livez`, `/readyz`, `/healthz`, login/analyze/dashboard smoke pass |
| Release gate | each area build/test + privacy regression + no external LLM verification | MVP can be marked complete |

### 15.4 PM Execution Order And PR Bundles

| Order | PR bundle | Included WBS | Purpose | Completion condition |
| --- | --- | --- | --- | --- |
| P0-1 | Monorepo/API/Compose scaffold | 6-11 | `apps/api`, `apps/dashboard`, `infra`, PostgreSQL, settings, health skeleton | base compose starts API+PostgreSQL, health skeleton passes |
| P0-2 | Auth/default admin/RBAC | 12-27 | default ADMIN seed, login/session auth, admin user management, RBAC | auth/RBAC/default admin tests pass |
| P0-3 | Metadata-only DB/event/idempotency | 28-33, 90-91 | Analyze schema, prompt hash, idempotency, event metadata, privacy DB/log scan | duplicate event prevented and prohibited column/log scan passes |
| P0-4 | Core detectors/scoring/masking/filter rules | 34-56, 98 | PII/secret/business context, unified filter rules, merge, score, mask, corpus | detector/filter/scoring/masking tests pass |
| P0-5 | Extension real API integration | 57-73, 94-95 | connect extension to real API | real auth/config/analyze smoke passes |
| P0-6 | Dashboard MVP metadata UI | 74-89, 97 | login/overview/events/users/filters/status | metadata-only API/DOM privacy tests pass |
| P1-1 | Filter management hardening | 48-52, 87 | regex safety, dry-run, versions, context rule UX | ReDoS/privacy/filter integration passes |
| P1-2 | Release/docs/final smoke | 5, 99-102 | README/install/admin/privacy/release/demo | fresh install demo and release gate pass |

### 15.5 Final Smoke / Demo Scenario

1. Start API and PostgreSQL with `docker compose up --build`.
2. `GET /livez` returns `200`.
3. `GET /readyz` returns `200` with DB connection, current migration, default filter/config readiness.
4. Verify default ADMIN `admin / 1234` exists and password is hash-only.
5. Open dashboard login page and log in as ADMIN.
6. Dashboard routes `/dashboard`, `/events`, `/users`, `/filters`, `/status` open.
7. ADMIN creates a normal USER through `/admin/users`.
8. USER can use extension auth/config/analyze but cannot access dashboard.
9. Extension options save self-host API URL and verify `/auth/me`, `/config/extension`.
10. Enter `NDA 위약금은 3억원입니다` in ChatGPT composer and verify Warn or Mask.
11. Event detail shows Business Context matched keyword counts and no raw prompt.
12. Enter a dummy secret fixture and verify Mask or Block with no raw submit.
13. Filter dry-run works and does not persist sample text.
14. Status page shows API/PostgreSQL/Migration/Last Checked.
15. Run DB/log/error/dashboard privacy scans and no external LLM call check.

## 16. WBS Document-Order Work Table

### 16.0 v0.12 Current Implementation Status Audit Sources

v0.12 does not rewrite v0.11. Instead, it directly reflects the current implementation status in this document. Status judgments are based on the current `promptguard_publish/main` code, tests, and merged PRs.

Status audit sources:

- WBS 10-15: health/status/setup/admin seed/dashboard login scaffold status was reclassified from PR #10, #12, #13, #15, #23, #32, #33 and `apps/api/app/routes/*`, `apps/api/tests/*`, `apps/dashboard/src/main.ts`.
- WBS 17-27: auth DB, password hash, login/refresh/logout/auth/me, RBAC, admin user API, and CORS/rate-limit status was reclassified from PR #10, #12, #15, #18, #22 and `apps/api/app/routes/auth.py`, `apps/api/app/routes/admin_users.py`, and related pytest coverage.
- WBS 34-36 and 55: PII/RRN/card detectors and placeholder masking status was reclassified from PR #20, #29, #35 and `apps/api/app/detectors/pii.py`, `apps/api/app/masking/placeholder.py`, and related pytest coverage.
- WBS 74-79, 83, 87, and 88: dashboard scaffold/events/filter/status status was reclassified from PR #16, #23, #26, #30, #32, #33 and `apps/dashboard/src/main.ts`, `apps/api/app/routes/status.py`.
- WBS 48 remains `Not Done` because the current `main` code does not contain a `filter_rules` migration/model despite earlier PR history. WBS 49-52 also remain incomplete because backend CRUD/dry-run/pipeline implementation is not present in current `main`.

`Document order` is renumbered from 1 inside this v0.12 document for readability. The Owner and Planned date columns reflect the revised WBS allocation after one team member was removed. Area, category, item, original detail, status, and implementation instructions are kept intact unless needed for allocation consistency.

Status criteria:

- `Done`: actual implementation or documentation is confirmed in the current repo.
- `Partial`: partial implementation/documentation exists, but it is insufficient for self-host MVP completion.
- `Not Done`: the implementation is not present in the current repo.
- `Deferred`: the implementation contract cannot be closed without a user decision or external dependency. Do not use this for fixed decisions such as Python/FastAPI/PostgreSQL/Redis optional.

Each WBS row's `v0.12 implementation instruction` is an implementation ticket containing:

- Completed slice: the code, test, or document portion already confirmed in the current repo when status is `Partial`.
- Remaining implementation: code, tests, or documentation still required in the current repo.
- Prerequisites: API, schema, screen, migration, fixture, or settings needed before starting.
- PR completion criterion: observable output that lets the item be marked complete.
- Test/verification: command, privacy/security scan, smoke, or document verification.

Partial means the row is not ready to execute as one vague task. Before a partial row is assigned or implemented, split it into completed slice and remaining work, then implement only the remaining work as a concrete MVP slice.

| Document order | Phase | Category | Item | Owner | Planned date | Area | Original detail | Current status | v0.12 implementation instruction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Preparation/Planning | Scope confirmation | Confirm open-source MVP scope | 전체 | 2026-05-19 | Planning·QA·Docs | Self-host, admin-managed user creation, no raw storage, filter rule scope table | Partial | Completed slice: self-host, admin-managed user creation, raw-storage prohibition, and unified Filter Rule scope are reflected in the v0.12 contract. Remaining work: align README/install/admin/privacy docs with v0.12 MVP scope. Prereq: v0.12 contract fixed. PR criterion: self-host, admin-managed user creation, no raw storage, filter rule, dashboard scope are described consistently in docs and repo structure. Verification: document grep and final demo checklist. |
| 2 | Preparation/Planning | Priority | Reclassify P0/P1/P2 requirements | 전체 | 5-20(Wed) | Planning·QA·Docs | Required/optional/follow-up scope table | Partial | Completed slice: the v0.12 document now acts as the MVP/follow-up classification source and contains current status per WBS row. Remaining work: sync MVP required, optional, follow-up scope table with this WBS. Prereq: API/dashboard/extension scope fixed. PR criterion: every WBS row has MVP/follow-up/optional status and completion criteria. Verification: review that out-of-scope features are not mixed into MVP done definition. |
| 3 | Preparation/Planning | User flow | Document install, admin-managed user creation, extension, dashboard flow | 김영은 | 5-20(Wed) | Dashboard·UI | Login -> admin user management -> Extension -> Dashboard flow diagram | Not Done | Remaining: flow diagram and screen skeleton for setup -> login/admin-managed user creation -> extension connection -> analyze -> dashboard metadata view. Prereq: auth/session API contract. PR criterion: dashboard routes and empty/loading/error states connect to the flow. Verification: login/dashboard smoke. |
| 4 | Preparation/Planning | Configuration decision | Write self-host server configuration decision | 유지수 | 5-24(Sun) | Server·Security | Docker, DB, Redis, reverse proxy configuration | Partial | Completed slice: Python/FastAPI/PostgreSQL and Redis-optional decisions are reflected in the contract. Remaining work: Python/FastAPI/PostgreSQL base configuration and Redis optional profile docs/compose. Prereq: env schema and health contract. PR criterion: base compose starts API+PostgreSQL without Redis, optional Redis shows disabled. Verification: Docker smoke, `/readyz`, `/healthz`. |
| 5 | Preparation/Planning | Verification plan | List tests and release gates | 전체 | 5-22(Fri) | Planning·QA·Docs | Install, E2E, privacy, security tests | Partial | Completed slice: the v0.12 document contains privacy/security/E2E/release gate categories and a demo checklist. Remaining work: connect API/dashboard/extension/privacy/security/release gates to implementation subplans and CI commands. Prereq: each app scaffold and test runner. PR criterion: every MVP slice has completion criteria and test command. Verification: `pytest`, dashboard test, extension checks, Docker smoke, privacy regression. |
| 6 | OSS·Seed·Auth | Repository | Create monorepo base structure | 김현성 | 5-22(Fri) | Chrome Extension | apps/api, apps/dashboard, apps/extension, packages, docs, infra | Partial | Completed slice: `apps/extension` and `apps/api` for the API core exist. Remaining work: confirm dashboard/infra package boundaries, root runtime scripts, and docs wiring so the monorepo can run API/dashboard/extension without JS-only server assumptions. |
| 7 | OSS·Seed·Auth | Runtime | Docker Compose runtime configuration | 유지수 | 5-24(Sun) | Chrome Extension | API, dashboard, PostgreSQL, Redis compose file | Partial | Completed slice: `infra/docker-compose.yml` contains the API+PostgreSQL default runtime and optional Redis profile. Remaining work: dashboard service, PostgreSQL-backed `/readyz`, migration smoke, and documented Redis-disabled status. |
| 8 | OSS·Seed·Auth | Environment variables | Implement `.env.example` and startup validation | 전체 | 5-22(Fri) | Planning·QA·Docs | required env validation and dummy secret file | Not Done | Write Python config validation and safe dummy secret examples. |
| 9 | OSS·Seed·Auth | Build | Organize common build scripts for API, UI, extension | 김현성 | 5-23(Sat) | Chrome Extension | dev/build/test scripts and package commands | Partial | Completed slice: extension/dashboard JS commands exist in their app contexts. Remaining work: root scripts must separate Python API commands from JS workspace commands and provide predictable dev/build/test entry points. |
| 10 | OSS·Seed·Auth | Health | Implement server health check endpoint | 유지수 | 5-24(Sun) | Server·Security | /healthz response and dependency status | Done | Completed slice: `/livez`, `/readyz`, `/healthz`, DB/migration/config/filter_config dependency checks, optional Redis disabled/degraded handling, ADMIN-only `/status/server`, and route/RBAC/status tests are implemented. Status audit source: PR #13, PR #15, `apps/api/app/routes/health.py`, `apps/api/app/routes/status.py`, `apps/api/tests/test_health.py`, `apps/api/tests/test_rbac.py`. Remaining work: keep verifying real PostgreSQL/migration state in operational compose smoke. |
| 11 | OSS·Seed·Auth | DB | Build DB migration runtime skeleton | 유지수 | 5-24(Sun) | Server·Security | alembic migration runner | Partial | Completed slice: Alembic config, auth/user migrations, default ADMIN seed migration, and migration-head lookup are implemented. Status audit source: PR #10, PR #12, `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/*`, `apps/api/app/routes/health.py`. Remaining work: fresh DB upgrade/downgrade smoke, filter/event/idempotency migrations, and standardized CI/compose migration runner. |
| 12 | OSS·Seed·Auth | Seed/Auth | Implement default ADMIN seed readiness check | 김영은 | 5-24(Sun) | Server·Security | `seed/readiness`, needs_setup response | Partial | Completed slice: `/setup/status` returns `needs_setup`, and default ADMIN seed migration tests exist. Status audit source: PR #10, PR #12, `apps/api/app/routes/setup.py`, `apps/api/tests/test_admin_seed.py`. Remaining work: reconcile user-facing bootstrap route with the v0.12 login-first contract, and connect seed readiness to dashboard session flow. |
| 13 | OSS·Seed·Auth | Seed/Auth | Implement default ADMIN DB seed | 김영은 | 5-24(Sun) | Server·Security | `admin / 1234` hash seed | Done | Completed slice: default ADMIN login id seed, environment-based initial password, Argon2id hash-only storage, and seed password verification tests are implemented. Status audit source: PR #12, `apps/api/alembic/versions/20260528_0003_v09_username_admin_seed.py`, `apps/api/tests/test_admin_seed.py`. Remaining work: keep operations docs warning that the initial password must be changed. |
| 14 | OSS·Seed·Auth | Seed/Auth | Implement seed idempotency and audit record | 김영은 | 5-24(Sun) | Server·Security | duplicate seed prevention and audit log | Partial | Completed slice: ADMIN seed avoids duplicate creation by checking existing ADMIN/login_id state. Status audit source: PR #12, `apps/api/alembic/versions/20260528_0003_v09_username_admin_seed.py`. Remaining work: seed execution audit metadata, restart/fresh DB idempotency smoke, and audit-table integration. |
| 15 | OSS·Seed·Auth | Initial screen | Implement login page | 김영은 | 5-25(Mon) | Dashboard·UI | login page and ADMIN session navigation | Partial | Completed slice: Vanilla TypeScript dashboard login screen, restored visual baseline, separated temporary mock login helper, and logout/navigation scaffold are implemented. Status audit source: PR #23, PR #32, PR #33, `apps/dashboard/src/main.ts`, `apps/dashboard/src/styles/main.css`. Remaining work: API-backed dashboard session login/me/logout, CSRF, and session-expired redirect. |
| 16 | OSS·Seed·Auth | Config seed | Seed default workspace, filter config, admin defaults | 김영은 | 5-25(Mon) | Server·Security | INVITE_ONLY default, default filter config version | Not Done | Implement through fresh DB seed/migration. |
| 17 | OSS·Seed·Auth | DB | Create users, invites, registration_settings tables | 유지수 | 5-24(Sun) | Server·Security | users, invites, registration_settings | Partial | Completed slice: users and refresh_tokens auth migrations/models are implemented. Status audit source: PR #10, PR #12, `apps/api/app/models/auth.py`, `apps/api/alembic/versions/20260523_0001_auth_tables.py`, `apps/api/alembic/versions/20260526_0002_login_id_accounts.py`. Remaining work: keep invites/registration_settings excluded from MVP or implement separate post-MVP migrations if needed. |
| 18 | OSS·Seed·Auth | Security | Store password hash | 유지수 | 5-24(Sun) | Server·Security | argon2/bcrypt hash | Done | Completed slice: Argon2id hash/verify helper, hash-only password storage for login/admin user/default seed, and password/security tests are implemented. Status audit source: PR #10, PR #12, PR #22, `apps/api/app/core/password.py`, `apps/api/tests/test_password.py`, `apps/api/tests/test_auth_security.py`, `apps/api/tests/test_admin_users.py`. Remaining work: document operational cost parameters. |
| 19 | OSS·Seed·Auth | Login | Implement login, refresh, auth/me API | 유지수 | 5-24(Sun) | Server·Security | access/refresh token issue and user info response | Partial | Completed slice: `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/change-password`, bearer token verification, refresh rotation/revocation boundary, and route tests are implemented. Status audit source: PR #10, PR #12, PR #18, `apps/api/app/routes/auth.py`, `apps/api/tests/test_auth_routes.py`, `apps/api/tests/test_auth_security.py`. Remaining work: separate dashboard session-cookie/CSRF auth and connect it to dashboard. |
| 20 | OSS·Seed·Auth | Token | Handle refresh token hash, expiry, revocation | 유지수 | 5-24(Sun) | Server·Security | raw refresh token not stored | Done | Completed slice: refresh token hash storage, expiry, revoked_at, replaced_by_token_id rotation, logout revocation, and raw token non-storage tests are implemented. Status audit source: PR #10, `apps/api/app/core/tokens.py`, `apps/api/app/routes/auth.py`, `apps/api/app/models/auth.py`, `apps/api/tests/test_auth_security.py`, `apps/api/tests/test_auth_routes.py`. Remaining work: recheck rotation in DB integration smoke. |
| 21 | OSS·Seed·Auth | Authorization | Implement ADMIN/USER permission middleware | 유지수 | 5-24(Sun) | Server·Security | require_admin, role guard | Done | Completed slice: `require_active_user`, `require_admin`, disabled-user blocking, USER 403, ADMIN-only `/status/server`, and RBAC route tests are implemented. Status audit source: PR #15, `apps/api/app/routes/auth.py`, `apps/api/tests/test_rbac.py`. Remaining work: reuse the same permission rule when dashboard session guard lands. |
| 22 | OSS·Seed·Auth | User management | Implement ADMIN user creation API | 김현성 | 5-27(Wed) | Server·Security | POST /admin/users, password hashing | Done | Completed slice: ADMIN-only `POST /admin/users`, password hashing, role validation, duplicate 409, safe response, and email validation tests are implemented. Status audit source: PR #22, `apps/api/app/routes/admin_users.py`, `apps/api/tests/test_admin_users.py`. Remaining work: connect response stats to real event aggregates when event tables land. |
| 23 | OSS·Seed·Auth | Invite management | Implement admin user list/detail API | 김현성 | 5-27(Wed) | Server·Security | GET /admin/users list, user aggregate fields, safe metadata only | Partial | Completed slice: ADMIN-only `GET /admin/users`, `GET /admin/users/{user_id}`, `user_id` alias, safe metadata response, USER-forbidden, and OpenAPI tests are implemented. Status audit source: PR #22, `apps/api/app/routes/admin_users.py`, `apps/api/tests/test_admin_users.py`. Remaining work: populate `last_event_at`, `event_count`, `blocked_count`, `masked_count`, and `warned_count` from event tables. |
| 24 | OSS·Seed·Auth | Registration mode | Remove self-signup routes from MVP scope | 김현성 | 5-28(Thu) | Server·Security | self signup/invite signup/workspace-code/open signup are absent or disabled | Not Done | Ensure unsupported registration routes are not exposed in MVP; document as post-MVP if kept. |
| 25 | OSS·Seed·Auth | User management | Implement user status/role change API | 김현성 | 5-27(Wed) | Server·Security | role/status patch | Done | Completed slice: ADMIN-only role/status patch, enum validation, self-demotion/self-disable prevention, and safe response tests are implemented. Status audit source: PR #22, `apps/api/app/routes/admin_users.py`, `apps/api/tests/test_admin_users.py`. Remaining work: connect to the dashboard Users screen. |
| 26 | OSS·Seed·Auth | Tests | Write admin-managed user creation/login/permission tests | 유지수 | 5-24(Sun) | Server·Security | auth/RBAC pytest | Done | Completed slice: default admin seed, login/refresh rate limit, disabled user, refresh token hash, RBAC, and admin-users route tests are implemented. Status audit source: PR #10, PR #12, PR #15, PR #18, PR #22, `apps/api/tests/test_admin_seed.py`, `test_auth_routes.py`, `test_auth_security.py`, `test_rbac.py`, `test_admin_users.py`. Remaining work: add dashboard session auth tests when dashboard session lands. |
| 27 | OSS·Seed·Auth | Security | Apply CORS and base rate-limit rule | 유지수 | 5-24(Sun) | Server·Security | origin allowlist, login limit | Done | Completed slice: settings-based CORS origin allowlist, credential wildcard rejection, login/refresh in-memory rate limiting, and X-Forwarded-For non-trust tests are implemented. Status audit source: PR #18, `apps/api/app/main.py`, `apps/api/app/core/config.py`, `apps/api/app/core/rate_limit.py`, `apps/api/tests/test_cors.py`, `apps/api/tests/test_auth_routes.py`. Remaining work: distributed Redis/Postgres-backed limiter for multi-instance deployments. |
| 28 | Analysis/Detection | Request validation | Validate Analyze API request schema | 김현성 | 5-29(Fri) | Server·Security | validate prompt/context/filter_config_version/client_request_id | Partial | Completed slice: Pydantic schema, FastAPI route, OpenAPI exposure, and route tests exist for the current narrow boundary. Remaining work: migrate final MVP contract to typed `inputs[]`, wire real auth/workspace context, require DB-backed filter config context, and keep validation errors raw-free. |
| 29 | Analysis/Detection | Raw-source protection | Implement raw_prompt non-storage boundary | 김현성 | 5-30(Sat) | Planning·QA·Docs | block request body logging and redaction hook | Partial | Completed slice: safe redaction helpers, safe problem responses, and raw-prompt non-echo tests exist. Remaining work: access/request/error logging blocks, privacy scans, DB/log integration tests, clipboard/file raw-content leakage checks, and oversized/unsupported input error privacy. |
| 30 | Analysis/Detection | Duplicate handling | Handle duplicate `client_request_id` requests | 김현성 | 5-31(Sun) | Server·Security | idempotency rule and duplicate event prevention | Not Done | Implement PostgreSQL idempotency metadata and Mask recompute rule. |
| 31 | Analysis/Detection | Hash | Implement HMAC prompt_hash | 김현성 | 5-31(Sun) | Server·Security | workspace-separated hash and secret injection | Partial | Completed slice: HMAC helpers that separate workspace id as input, env-based secret settings, and route-boundary generation exist. Remaining work: real auth workspace id, key id metadata, rotation policy, event persistence integration, and tests that raw prompt is not used as a stored identifier. |
| 32 | Analysis/Detection | Event DB | Create analysis event and detection detail tables | 김영은 | 5-31(Sun) | Server·Security | migration prohibiting raw_prompt, masked_prompt, value | Not Done | Create metadata-only schema migration. |
| 33 | Analysis/Detection | Event persistence | Implement raw-data-free event persistence service | 김영은 | 5-31(Sun) | Server·Security | store user, service, detection_types, risk, action | Not Done | Implement event service and transaction boundary. |
| 34 | Analysis/Detection | PII | Implement email/phone detection | 유지수 | 5-29(Fri) | Server·Security | EMAIL/PHONE detector and corpus test | Done | Completed slice: EMAIL/PHONE deterministic detectors, punctuation edge case, raw-free detection object, and corpus tests are implemented. Status audit source: PR #20, `apps/api/app/detectors/pii.py`, `apps/api/tests/test_pii_detectors.py`. Remaining work: connect filter rule enabled/severity/action to analyze pipeline. |
| 35 | Analysis/Detection | PII | Implement Korean RRN checksum validation | 유지수 | 5-30(Sat) | Server·Security | RRN checksum | Done | Completed slice: RRN candidate detection, checksum validation, and raw-free detection tests are implemented. Status audit source: PR #29, `apps/api/app/detectors/pii.py`, `apps/api/tests/test_pii_detectors.py`. Remaining work: expand operational corpus and connect filter/action. |
| 36 | Analysis/Detection | Payment info | Implement card number Luhn validation | 유지수 | 5-30(Sat) | Server·Security | CARD Luhn | Done | Completed slice: card candidate detection, Luhn validation, and raw-free detection tests are implemented. Status audit source: PR #29, `apps/api/app/detectors/pii.py`, `apps/api/tests/test_pii_detectors.py`. Remaining work: expand operational corpus and connect filter/action. |
| 37 | Analysis/Detection | Korean localization | Implement business registration number candidate/validation | 전체 | 6-1(Mon) | Planning·QA·Docs | business number candidates and checksum tests | Not Done | Korean business-number test corpus. |
| 38 | Analysis/Detection | Business candidate | Detect amount, discount rate, contract period candidates | 전체 | 6-1(Mon) | Planning·QA·Docs | Korean business sentence candidate test set | Not Done | Context evidence corpus. |
| 39 | Analysis/Detection | Secrets | Implement GitHub/AWS key detection | 김영은 | 6-2(Tue) | Server·Security | `ghp_`, `github_pat_`, AKIA/ASIA tests | Not Done | Secret detector tests. |
| 40 | Analysis/Detection | Secrets | Implement JWT/private key block detection | 김영은 | 6-3(Wed) | Server·Security | JWT 3-part, PEM block tests | Not Done | JWT/PEM detector tests. |
| 41 | Analysis/Detection | Secrets | Implement DB connection string detection | 김영은 | 6-3(Wed) | Server·Security | postgres/mysql/mongodb URI detection | Not Done | URI detector with redaction tests. |
| 42 | Analysis/Detection | Secrets | Detect `.env` secret and high-entropy candidates | 김영은 | 6-3(Wed) | Server·Security | PASSWORD/SECRET key=value, entropy tests | Not Done | Env and entropy detector. |
| 43 | Analysis/Detection | Rule pack | Write Korean-localized rule pack structure | 김현성 | 6-3(Wed) | Planning·QA·Docs | rule_pack_version, label, severity spec | Not Done | Rule pack schema and fixtures. |
| 44 | Analysis/Detection | Context classification | Implement contract-information rule classifier | 김현성 | 6-4(Thu) | Planning·QA·Docs | contract amount, penalty, NDA context tests | Partial | Completed slice: contract amount, penalty, and NDA helpers plus unit tests exist. Remaining work: corpus expansion, false-positive/false-negative evaluation, detector pipeline integration, scoring/action linkage, and raw-free evidence metadata. |
| 45 | Analysis/Detection | Context classification | Implement customer-information rule classifier | 전체 | 6-5(Fri) | Planning·QA·Docs | customer company, contact person, inquiry combination tests | Not Done | Customer context classifier. |
| 46 | Analysis/Detection | Context classification | Implement trade-secret/internal-strategy classifier | 김영은 | 6-5(Fri) | Planning·QA·Docs | pricing strategy, launch plan, competitive strategy tests | Not Done | Strategy context classifier. |
| 47 | Analysis/Detection | Context classification | Handle low-confidence/ambiguous sentences | 김현성 | 6-5(Fri) | Planning·QA·Docs | AMBIGUOUS handling and exclusion from strong block | Not Done | Ambiguous evidence scoring rule. |
| 48 | Analysis/Detection | Filter rule | Create filter rule tables | 유지수 | 6-5(Fri) | Server·Security | filter_rules, versions migration | Not Done | Filter rule migrations. |
| 49 | Analysis/Detection | Filter rule | Implement regex/keyword filter API | 김현성 | 6-6(Sat) | Server·Security | create/update/disable/list API | Not Done | ADMIN CRUD with safe regex validation. |
| 50 | Analysis/Detection | Filter rule | Validate risky regex before storage | 전체 | 6-6(Sat) | Planning·QA·Docs | length, syntax, execution timeout, ReDoS defense | Not Done | ReDoS tests and safe-regex strategy. |
| 51 | Analysis/Detection | Filter rule | Implement filter dry-run API | 김영은 | 6-6(Sat) | Server·Security | sample raw text non-storage test | Not Done | Dry-run request-only, no persistence. |
| 52 | Analysis/Detection | Filter rule | Connect filter rules to analysis pipeline | 김현성 | 6-6(Sat) | Server·Security | filter_rule detection and statistics metadata | Not Done | Detector pipeline integration. |
| 53 | Analysis/Detection | Merge | Implement overlap merge rules for detections | 김현성 | 6-6(Sat) | Server·Security | secret priority, longer span priority tests | Partial | Completed slice: helper and tests cover secret priority and longer span priority within the same priority level. Remaining work: integrate into the full detector pipeline, verify duplicate statistics are removed, and add regression cases for mixed PII/secret/filter-rule overlaps. |
| 54 | Analysis/Detection | Risk | Implement risk score and action decision rules | 전체 | 6-6(Sat) | Planning·QA·Docs | 0-100 score, Allow/Warn/Mask/Block | Not Done | Deterministic scoring rules. |
| 55 | Analysis/Detection | Masking | Replace personal data/secrets with placeholders | 유지수 | 6-6(Sat) | Server·Security | EMAIL_1, PHONE_1 placeholders | Done | Completed slice: deterministic placeholder masking, repeated value reuse, overlap handling, and raw-free masking tests are implemented. Status audit source: PR #35, `apps/api/app/masking/placeholder.py`, `apps/api/tests/test_masking.py`. Remaining work: generate server response `masked_prompt` in the Analyze orchestrator and verify persistence remains raw-free. |
| 56 | Analysis/Detection | Analysis integration | Integrate full Analyze API flow | 유지수 | 6-7(Sun) | Server·Security | detector -> score -> mask -> log -> response integration | Not Done | Orchestrator and integration tests. |
| 57 | Extension | Skeleton | Write Manifest V3 extension scaffold | 김현성 | 6-7(Sun) | Chrome Extension | content script, service worker, options structure | Done | Only maintenance and real API adapter integration remain. |
| 58 | Extension | Server connection | Implement self-host API URL input screen | 김현성 | 6-7(Sun) | Chrome Extension | API base URL storage and connection verification | Partial | Completed slice: mock/real connection UI and `/auth/me` skeleton exist. Remaining work: real token verification, safe connection error states, end-to-end options smoke, and persistence migration for any changed config shape. |
| 59 | Extension | Login | Handle extension login/token storage | 김현성 | 6-7(Sun) | Chrome Extension | token storage, refresh, logout behavior | Partial | Completed slice: token storage exists. Remaining work: real refresh/logout server integration, refresh-before-relogin behavior, token expiry tests, and confirmation that MV3 service worker inactivity is not treated as auth expiry. |
| 60 | Extension | Config sync | Sync server selector and filter config | 김현성 | 6-8(Mon) | Chrome Extension | `/config/extension` call and cache | Partial | Completed slice: client/cache and `/config/extension` skeleton exist. Remaining work: DB-backed filter config/selector source, cache invalidation/version handling, real smoke, and safe fallback when selector config is missing. |
| 61 | Extension | Domain | Limit activation to ChatGPT domains | 김현성 | 6-8(Mon) | Chrome Extension | separate target/non-target domain behavior | Done | Maintain ChatGPT-like selector regression. |
| 62 | Extension | Input detection | Implement textarea input detection | 김현성 | 6-8(Mon) | Chrome Extension | candidate selection by visible/focus | Done | Maintain DOM change smoke. |
| 63 | Extension | Input detection | Implement contenteditable input detection | 김현성 | 6-8(Mon) | Chrome Extension | contenteditable fallback detection | Done | Real ChatGPT smoke needed. |
| 64 | Extension | Submit hold | Intercept send-button click | 김현성 | 6-9(Tue) | Chrome Extension | hold submit until analysis completes | Done | Maintain selector drift tests. |
| 65 | Extension | Submit hold | Intercept Enter/shortcut submit | 김현성 | 6-10(Wed) | Chrome Extension | Enter/Shift+Enter branch | Done | Maintain `@` mention/GPT picker exception regression test. |
| 66 | Extension | API integration | Implement Analyze API client | 김현성 | 6-10(Wed) | Chrome Extension | request body creation, 401/timeout handling | Partial | Completed slice: extension client and `/auth/me`, `/config/extension`, `/prompts/analyze` route skeletons exist. Remaining work: real token verification, DB-backed filter config, typed `inputs[]` request body, timeout/error privacy handling, and end-to-end smoke. |
| 67 | Extension | Duplicate prevention | Prevent duplicate send of approved prompt | 김현성 | 6-10(Wed) | Chrome Extension | allow hash, double-submit guard | Done | Keep separate from server idempotency. |
| 68 | Extension | Action handling | Resume Allow send | 김현성 | 6-10(Wed) | Chrome Extension | replay original send once | Done | Verify in real API smoke. |
| 69 | Extension | Action handling | Implement Warn panel | 김현성 | 6-11(Thu) | Chrome Extension | hold before confirmation, send after confirmation | Done | Keep UX copy safe. |
| 70 | Extension | Action handling | Implement Mask panel and choice behavior | 김현성 | 6-12(Fri) | Chrome Extension | apply mask, cancel, request reason | Done | Needs server-supplied mask and smoke. |
| 71 | Extension | Masking | Replace input with `masked_prompt` | 김현성 | 6-12(Fri) | Chrome Extension | textarea/contenteditable replacement | Done | Keep automatic-send prohibition. |
| 72 | Extension | Blocking | Implement Block notice and raw send block | 김현성 | 6-12(Fri) | Chrome Extension | verify raw submit does not occur | Done | Maintain fixture and real smoke. |
| 73 | Extension | Notice/status | Storage/non-storage notice and connection status screen | 김현성 | 6-12(Fri) | Chrome Extension | notice, filter config sync time, server status | Partial | Completed slice: extension-side status/notice surface exists only as partial UI scaffolding. Remaining work: server status endpoint integration, last sync time, raw-storage notice accuracy, disconnected/degraded states, and options UI smoke. |
| 74 | Dashboard/Admin | Screen scaffold | Build dashboard routing and layout | 김영은 | 6-13(Sat) | Dashboard·UI | routing, auth guard, common layout | Partial | Completed slice: Vanilla TypeScript dashboard scaffold, login/admin/events/users/filters route rendering, visual baseline, and CSS layout are implemented. Status audit source: PR #23, PR #26, PR #32, `apps/dashboard/src/main.ts`, `apps/dashboard/src/styles/main.css`. Remaining work: API-backed auth guard, loading/error/permission states, and dashboard session integration. |
| 75 | Dashboard/Admin | Login | Connect login screens | 김영은 | 6-13(Sat) | Dashboard·UI | default ADMIN login | Partial | Completed slice: dashboard login screen and mock `admin/1234` boundary are separated into a helper. Status audit source: PR #32, PR #33, `apps/dashboard/src/main.ts`. Remaining work: `/dashboard/session/login`, `/dashboard/session/me`, CSRF, cookie session, and real seed/admin auth connection. |
| 76 | Dashboard/Admin | Summary | Connect overview summary API | 김영은 | 6-14(Sun) | Dashboard·UI | period totals, risk trend data connection | Not Done | MVP required. Needs metadata summary APIs for event/action/detector/user/period. |
| 77 | Dashboard/Admin | Overview | Implement overview cards and trend charts | 김영은 | 6-14(Sun) | Dashboard·UI | Total/Blocked/Masked/Warned/Active cards | Partial | Completed slice: overview cards and CSS-based action/user/period statistics visual scaffold are implemented. Status audit source: PR #23, PR #26, `apps/dashboard/src/main.ts`, `apps/dashboard/src/styles/main.css`. Remaining work: connect `/stats/overview`, `/stats/users`, and `/stats/events` APIs plus metadata privacy DOM tests. |
| 78 | Dashboard/Admin | Events | Implement Risk Events list and filters | 김영은 | 6-14(Sun) | Dashboard·UI | event table, filters | Partial | Completed slice: metadata-only risk event list scaffold and event navigation are implemented. Status audit source: PR #16, PR #23, `apps/dashboard/src/main.ts`. Remaining work: period/user/action/risk/detector/service filter API, pagination, loading/error state, and real event table connection. |
| 79 | Dashboard/Admin | Events | Implement raw-data-free event detail | 김영은 | 6-14(Sun) | Dashboard·UI | event detail safe metadata | Partial | Completed slice: event detail scaffold renders safe metadata and `promptHash` without raw prompt, file content, or original filename. Status audit source: PR #16, `apps/dashboard/src/main.ts`. Remaining work: real event detail API, matched keyword count, and privacy API/DOM regression tests. |
| 80 | Dashboard/Admin | User stats | Implement per-user event stats API | 김현성 | 6-15(Mon) | Server·Security | per-user type/count/action distribution API | Not Done | 김현성 MVP. This aggregate API is required before the per-user event table can work without mock data. Separate it from follow-up drilldown API. |
| 81 | Dashboard/Admin | User stats | Implement per-user event table | 김현성 | 6-15(Mon) | Dashboard·UI | user, department, top detection, last event | Not Done | 김현성 MVP. Top-user/user summary table connected to WBS 80 user statistics API; detailed user audit page is follow-up. |
| 82 | Dashboard/Admin | User stats | Implement user action/detection-type charts | 유지수 | 6-15(Mon) | Dashboard·UI | stacked bar, detection heatmap data | Not Done | MVP required. Metadata-only charts; personal timeline/detail is follow-up. |
| 83 | Dashboard/Admin | Users | Implement Users management screen | 김현성 | 6-16(Tue) | Dashboard·UI | admin UI | Partial | 김현성 MVP. Completed slice: dashboard Users placeholder/navigation scaffold and backend `/admin/users` API exist. Status audit source: PR #22, PR #23, `apps/api/app/routes/admin_users.py`, `apps/dashboard/src/main.ts`. Remaining work: remove mock data and connect real `/admin/users` list/create/role/status API client plus empty/loading/error/RBAC states. |
| 84 | Dashboard/Admin | Registration management | Implement User creation/role management screen | 유지수 | 6-16(Tue) | Dashboard·UI | admin user creation, role/status management | Not Done | Invite/registration UI. |
| 85 | Dashboard/Admin | Filter config | Merge filter config summary into Filter Rule Management | 유지수 | 6-17(Wed) | Dashboard·UI | show filter rule summary, detector overrides, retention metadata | Not Done | Do not implement a standalone configuration screen; surface any needed filter configuration summary inside Filter Rule Management. |
| 86 | Dashboard/Admin | Statistics | Implement detection-type statistics screen | 유지수 | 6-17(Wed) | Dashboard·UI | detection type trend and action count | Not Done | Metadata charts. |
| 87 | Dashboard/Admin | Filters | Implement filter rule management screen | 유지수 | 6-17(Wed) | Dashboard·UI | filter rule CRUD UI | Partial | Completed slice: Vanilla TypeScript Filter Rule management mock UI, built-in/custom/context rule list, pagination, and action/severity metadata scaffold are implemented. Status audit source: PR #30, `apps/dashboard/src/main.ts`, `apps/dashboard/src/styles/main.css`. Remaining work: backend Filter Rule CRUD API, validation/dry-run integration, real API client, and privacy/error states. |
| 88 | Dashboard/Admin | Status | Server health/degraded status screen | 김현성 | 6-17(Wed) | Dashboard·UI | API/DB/migration status | Partial | 김현성 MVP. Completed slice: backend `/status/server` and health/degraded metadata payload are implemented. Status audit source: PR #15, `apps/api/app/routes/status.py`, `apps/api/tests/test_rbac.py`, `apps/api/tests/test_health.py`. Remaining work: dashboard Status screen UI/API client, degraded/disabled visual states, session guard, and verification that raw prompt/full masked prompt/DB URL/stack trace are not displayed. |
| 89 | Dashboard/Admin | Raw-source prohibition | Dashboard raw-source non-exposure screen tests | 전체 | — | Planning·QA·Docs | verify raw_prompt, masked_prompt, detected value hidden | Not Done | MVP required. Scan overview/event/user/status/filter rule DOM/API responses with seeded sensitive values. |
| 90 | Integration·Security·Docs | Privacy | Write DB raw-source non-storage regression tests | 전체 | — | Planning·QA·Docs | prohibited column and seeded prompt DB scan | Not Done | pytest/schema scan. |
| 91 | Integration·Security·Docs | Privacy | Write log raw-source non-storage regression tests | 전체 | — | Planning·QA·Docs | application/access/error log seeded scan | Not Done | Log capture tests. |
| 92 | Integration·Security·Docs | Security | Write external LLM call prohibition verification | 전체 | — | Planning·QA·Docs | network mock, zero outbound LLM calls | Not Done | No external LLM CI check. |
| 93 | Integration·Security·Docs | Security | Write auth/RBAC security tests | 전체 | 6-20(Sat) | Planning·QA·Docs | default ADMIN seed, USER 403, token expiry | Not Done | Auth security tests. Include regression that service worker inactivity does not lead to re-login and re-login is requested only after refresh failure conditions. |
| 94 | Integration·Security·Docs | E2E | Write extension core-flow E2E | 전체 | 6-21(Sun) | Chrome Extension | Allow/Warn/Mask/Block fixture tests | Done | Current extension tests exist. Real API E2E is needed after server implementation. |
| 95 | Integration·Security·Docs | E2E | Write selector-change regression tests | 전체 | 6-21(Sun) | Chrome Extension | remote selector update fixture | Partial | Completed slice: extension fixture exists. Remaining work: real config endpoint, remote selector update fixture, rerender regression tied to marker refresh, and end-to-end test against updated selector config. |
| 96 | Integration·Security·Docs | Integration | Analyze API integration/performance tests | 전체 | 6-21(Sun) | Server·Security | happy/error path, p95 500ms measurement | Not Done | Python API performance tests. |
| 97 | Integration·Security·Docs | Integration | Dashboard integration/performance tests | 전체 | 6-21(Sun) | Dashboard·UI | 30-day summary/user stats p95 measurement | Not Done | Write dashboard/API tests. |
| 98 | Integration·Security·Docs | Quality | Korean FP/FN corpus evaluation | 전체 | 6-21(Sun) | Planning·QA·Docs | PII/secret/business-context positive/negative report | Not Done | Corpus and report. |
| 99 | Integration·Security·Docs | Docs | Write README, install, reverse proxy docs | 전체 | 6-22(Mon) | Planning·QA·Docs | README, install.md, HTTPS guide | Not Done | After compose/API shape. |
| 100 | Integration·Security·Docs | Docs | Write admin, privacy, contribution docs | 전체 | 6-22(Mon) | Planning·QA·Docs | admin-guide, privacy-design, contributing | Not Done | After dashboard/API privacy behavior is fixed. |
| 101 | Integration·Security·Docs | Release | Build Docker image and extension package | 전체 | 6-22(Mon) | Chrome Extension | release artifact, sideload zip, version check | Not Done | Write release plan after full MVP completion. |
| 102 | Integration·Security·Docs | Closing | Final smoke test and demo scenario | 전체 | 6-23(Tue) | Dashboard·UI | login -> admin user management -> Extension -> Dashboard demo | Not Done | Write final end-to-end demo. |
## 17. Owner-Sorted AI Work Instructions

This section regroups the WBS document-order work table by the revised owner allocation after one team member was removed. For detailed original order, status judgment, and planned dates, section 16 is authoritative.

### 김현성

Implementation scope: monorepo/build coordination, extension, extension-to-API boundary, ADMIN-managed user creation and user-management API work reassigned from the removed member, Analyze request validation, raw-source protection, idempotency, HMAC hash, rule-pack and contract-context work, ambiguous handling, filter rule API/pipeline, overlap merge, user statistics API/per-user event table, API-backed Users management screen, and dashboard status screen.

- Related WBS rows: 6, 9, 22-25, 28-31, 43, 44, 47, 49, 52, 53, 57-73, 80, 81, 83, 88.
- Planned concentration: 5-22 to 6-12, with the extension implementation concentrated on 6-7 to 6-12.
- Sections to read: `6. Auth, Session, And Permission Contract`, `7. API Boundary And Detailed Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `11. Extension Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Implementation locations: `apps/extension/*`, `apps/api/*` modules for invites, user management, analyze/filter rule/idempotency/hash/user statistics, extension API adapter, tests, and `apps/dashboard/*` users/status/user summary screens.
- Prerequisites: Python API scaffold, auth context, PostgreSQL idempotency/event tables, user tables, OpenAPI output.
- Completed slices to preserve: extension DOM hook/hold/action handling, extension token storage, partial extension API client/config cache, narrow Analyze route/schema tests, safe redaction/problem response helpers, HMAC helper, contract-context helper, overlap merge helper, and ADMIN user create/list/detail/role/status APIs.
- Remaining implementation: typed `inputs[]` request body, real self-host API smoke, DB-backed filter/config, raw prompt/clipboard/file logging block, duplicate `client_request_id` handling, HMAC persistence integration, real event aggregates for user responses, per-user event table API integration, Users management mock removal and `/admin/users` list/create/role/status connection, dashboard status API integration plus raw prompt/full masked prompt/DB URL/stack trace non-display verification, rule-pack/ambiguous handling, filter rule CRUD/pipeline, and overlap merge pipeline integration.
- PR completion criterion: extension DOM hook regression remains passing; real `/auth/me`, `/config/extension`, `/prompts/analyze` calls pass; assigned invite/user APIs plus user statistics/dashboard users/status screens pass auth/RBAC tests; raw prompt and full masked prompt are absent from DB/log/error/dashboard.
- Test method: `python apps/extension/tests/run_extension_checks.py all`, `cd apps/api && pytest tests/analyze tests/privacy tests/filter_rules tests/auth`.

### 김영은

Implementation scope: user-flow documentation, default ADMIN seed/readiness work, event metadata DB/service work reassigned from the removed member, secret detectors, trade-secret/internal-strategy classifier, filter rule dry-run, and dashboard setup/overview/events screens.

- Related WBS rows: 3, 12-16, 32, 33, 39-42, 46, 51, 74-79.
- Planned concentration: 5-20 to 6-14, with dashboard MVP screens concentrated on 6-13 and 6-14.
- Sections to read: `8. Product Scope And Repository Structure`, `9. Data Model And Raw-Data Prohibition Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `12. Dashboard Contract`, `13. Security And Privacy Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Implementation locations: `apps/api/*` seed/event/detector modules and future `apps/dashboard/*` auth/overview/events screens.
- Prerequisites: dashboard scaffold and PostgreSQL/auth baseline are partially implemented. Metadata-only event table, metadata-only summary/events API, and session auth guard are still required.
- Completed slices to preserve: default ADMIN DB seed, partial `/setup/status` readiness, dashboard login/scaffold/overview/events/detail visual scaffold.
- Remaining implementation: user-flow diagram, seed audit and v0.12 login-first consistency cleanup, event metadata tables and service, GitHub/AWS/JWT/PEM/DB URI/.env/entropy detection, internal-strategy context classifier, filter rule dry-run, API-backed login flow, overview/events real API integration, and privacy DOM tests.
- PR completion criterion: login-first flow and event metadata persistence work without raw storage; dashboard works metadata-only; overview shows event/user/period statistics; event detail does not show raw prompt, full masked prompt, raw detected value, or original filename.
- Test method: `cd apps/api && pytest tests/seed tests/events tests/detectors tests/filter_rules tests/privacy`, `cd apps/dashboard && npm test`.

### 유지수

Implementation scope: Python API foundation, Docker/PostgreSQL, migration, auth/RBAC, CORS/rate limit, PII/localized detectors, server-side masking, Analyze orchestrator, filter rule backend, and part of dashboard filter management.

- Related WBS rows: 4, 7, 10, 11, 17-21, 26, 27, 34-36, 48, 55, 56, 82, 84-87.
- Planned concentration: 5-24 to 6-17, with dashboard management/status work concentrated on 6-15 to 6-17.
- Sections to read: `3. Server, Runtime, And Infrastructure Contract`, `4. Health And Status Contract`, `5. HTTP Error Contract`, `6. Auth, Session, And Permission Contract`, `7. API Boundary And Detailed Contract`, `9. Data Model And Raw-Data Prohibition Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `12. Dashboard Contract`.
- Implementation locations: `apps/api/*`, `infra/compose.yaml`, `.env.example`, Alembic migration, detector/masking/orchestrator modules, and future `apps/dashboard/*` filter-rule-related screens.
- Prerequisites: repository scaffold, API dependency setup, PostgreSQL connection, settings loader, migration/auth baseline are partially implemented. Dashboard session and event aggregate APIs are still required.
- Completed slices to preserve: health/status endpoints, Alembic baseline, auth/RBAC/token/CORS/rate-limit, EMAIL/PHONE/RRN/CARD detectors, placeholder masking, backend `/status/server`, and partial dashboard filter/status-related scaffold.
- Remaining implementation: compose runtime smoke, filter rule table/API, Analyze orchestrator, and real API-backed filter-rule screen.
- PR completion criterion: default Compose without Redis starts API/PostgreSQL; remaining filter/analyze/filter-management tests pass; assigned dashboard filter screen is metadata-only and RBAC-protected.
- Test method: `cd apps/api && pytest`, Docker smoke followed by `/livez`, `/readyz`, `/healthz`, login/analyze/dashboard summary smoke, and `cd apps/dashboard && npm test`.

### 전체

Implementation scope: shared planning, environment validation, Korean business-number and business-context corpus work, custom regex safety, risk scoring, raw-source non-exposure tests, privacy/security/E2E/performance tests, release documentation, packaging, and final demo.

- Related WBS rows: 1, 2, 5, 8, 37, 38, 45, 50, 54, 89-102.
- Planned concentration: 5-19 to 6-23, with integration, documentation, release, and final demo concentrated on 6-20 to 6-23.
- Sections to read: `13. Security And Privacy Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Remaining implementation: scope/priority alignment, `.env.example`, business registration and business-term detectors/corpus, customer context rule, custom regex ReDoS defense, scoring rules, dashboard raw-source non-exposure tests, DB/log/error privacy scan, external LLM call prohibition verification, API/dashboard/extension integration and performance tests, Korean FP/FN corpus, README/install/admin/privacy/contributing docs, release artifact, final smoke/demo.
- PR completion criterion: API, dashboard, extension build/test, privacy regression, no external LLM verification, Docker fresh-install smoke, and login -> admin user creation -> extension -> analyze -> dashboard demo all pass.
- Test method: each area test command, privacy regression, Docker smoke, final demo scenario.
