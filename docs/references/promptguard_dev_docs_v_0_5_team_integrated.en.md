# PromptGuard Development Documentation Set v0.5 - Team Integrated Edition

## 1. Document Use Rules And Current Implementation Status

- The server language is Python.
- PostgreSQL remains the database.
- Redis is not required by default for the MVP. PostgreSQL is the persistence boundary for login continuity, refresh tokens, and duplicate request handling.
- Having an extension mock/client does not mean the self-hosted Analyze API server has been implemented.
- Raw prompts, raw file contents, `masked_prompt`, raw detected values, original filenames, secrets/tokens, and stack traces must not be stored or written to logs, dashboard output, error responses, memory logs, or session logs.
- Keep the WBS owner, area, category, item, and original detail, but split them into implementable work units.
- This v5 document is the single basis for PromptGuard development contracts, implementation status, API boundaries, data ownership, and work instructions.
- The original WBS XLSX/CSV files remain separate source artifacts only for confirming scope, order, owner, and area.

### 1.1 Current Implementation Summary

- The extension has implemented the main flows for ChatGPT input detection, submit hold, Allow/Warn/Mask/Block UX, selector fixtures, and double-submit guard.
- The extension currently has parts verified with mock/fake backend and client fixtures. The real self-hosted API end-to-end smoke test is completed only after the server is implemented.
- Python self-hosted API, PostgreSQL migrations, dashboard, Docker Compose base runtime, admin setup/auth, event metadata persistence, and dashboard statistics APIs are still implementation targets.
- In the WBS work table, `Done`, `Partial`, and `Not Done` reflect the current repository state. `Partial` means there is a client, fixture, document, or partial UI, but real server/API/DB/integration verification remains.
- The English document is an AI-facing translation. It must follow the same section structure and detail level as the Korean contract.

## 2. Fixed Decisions

- Server language: Python.
  - Reason: Python is favorable for detectors, rule classifiers, masking, privacy regression tests, and possible future local NLP/ML expansion. It is easy for team members and AI development agents to read and implement, and OpenAPI lets the extension and dashboard share a language-neutral contract.
- Database: PostgreSQL.
  - Reason: users, workspaces, policies, custom filters, event metadata, duplicate request handling, and token hashes require durable transactions and migrations.
- Chrome extension: Manifest V3 + TypeScript.
  - Reason: the current extension implementation is based on this premise.
- Dashboard: admin UI without raw source data.
  - Reason: if the dashboard becomes a raw-prompt review tool, it conflicts with the privacy-centered product design.
- API contract source: FastAPI/Pydantic/OpenAPI output from `apps/api`.
  - Reason: the Python API owns request/response schemas and generates OpenAPI. The extension/dashboard consume generated clients/types or thin adapters from that OpenAPI.
- Server implementation stack: FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic.
  - Reason: this stack keeps Python API implementation, request/response validation, OpenAPI generation, and PostgreSQL migration in one maintainable flow.
- Redis: optional configuration.
  - Reason: default MVP login continuity, refresh tokens, idempotency, and event persistence are handled by PostgreSQL. Redis is added only as an optional profile when multi-instance rate limiting, distributed locks, queues, or caches are actually needed.

## 3. Server, Runtime, And Infrastructure Contract

Use the following as the implementation standard for server and runtime work. FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, and the 03A/03B split are fixed only under the assumption that they are common, maintainable, and fast to develop with. If implementation evidence breaks that assumption, do not lock it into code; ask the user again.

1. Implement the Python web framework with FastAPI.
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
| `GET /readyz` | Check whether the service can receive traffic | internal recommended | `200` when config is valid, DB connection works, migrations are current, and default policy can load; `503` when a required dependency is unavailable |
| `GET /healthz` | Aggregated status for dashboard/operators | internal or ADMIN recommended | `200` if core function works; `200` with `status=degraded` if only optional dependencies are affected; `503` if required dependencies are unavailable |
| `GET /status/server` | Raw-data-free status API used by the dashboard | ADMIN | Returns the same safe metadata as `/healthz` in an authenticated dashboard shape |

Health/status checks are not just UI features. They are part of the self-hosted operations MVP. Docker Compose and fresh-install requirements cannot be verified reliably without readiness checks such as `/healthz`.

### 4.2 Status Response Shape

```json
{
  "status": "healthy",
  "service": "promptguard-api",
  "version": "0.5.0",
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
      "name": "policy",
      "status": "healthy",
      "required": true,
      "code": "POLICY_READY",
      "message": "Default policy can be loaded"
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
- `unhealthy`: required dependency, configuration, migration, or policy state prevents normal service.

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

### 5.2 Status Code Policy

| Status | Use in PromptGuard | Do not use for |
| --- | --- | --- |
| `400 Bad Request` | malformed JSON, missing required top-level structure, schema parsing failure | authenticated user lacking permission |
| `401 Unauthorized` | missing, invalid, expired, or malformed access token | valid token with insufficient role |
| `403 Forbidden` | authenticated user lacks permission, disabled user, USER calls ADMIN route | cases where existence of cross-workspace resource must be hidden |
| `404 Not Found` | route/resource not found, or intentionally hiding forbidden cross-workspace resource existence | ordinary authentication failure |
| `409 Conflict` | duplicate request conflict, setup retry after completion, stale policy/version conflict that cannot be processed in current state | ordinary validation error |
| `413 Payload Too Large` | prompt/file/request body exceeds configured size limit | detection result is Block |
| `415 Unsupported Media Type` | unsupported content type or file type | semantic validation error |
| `422 Unprocessable Content` | syntactically valid but semantically invalid business input, such as invalid custom regex, impossible policy transition, unsupported rule expression | malformed JSON |
| `428 Precondition Required` | optional future use when a policy/version precondition is required but missing | ordinary policy mismatch better represented by `409` |
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

This section separately defines the extension bearer-token flow and the dashboard session-cookie flow. MV3 extension service worker inactivity is not authentication expiry. The dashboard uses server-managed admin sessions and CSRF protection.

### 6.1 Identifiers And Authentication

- `workspace_id` and `user_id` come from authenticated token/session context, not from request body.
- Access tokens may have a short lifetime.
- Raw refresh token values must never be stored; PostgreSQL stores only hash and metadata.
- Chrome Extension MV3 service worker inactivity is not authentication expiry.
- When the extension worker wakes up, it reads stored auth/session metadata. If the access token is expired, it first tries `POST /auth/refresh` before asking the user to log in again.
- If the refresh token is valid, the server issues a new access token. If refresh token rotation is used, it also issues a new refresh token and revokes the previous refresh token hash.
- Require re-login only for refresh token expiry, revocation, reuse detection, malformed token, server rejection, explicit logout, disabled account, server URL change, or workspace change.
- Disabled users are blocked before protected route execution.
- If an authenticated USER account calls an ADMIN-only route, return `403`.
- Dashboard session authentication is separate from extension bearer-token authentication.
  - The dashboard session is a server-managed session id delivered through an `HttpOnly` cookie.
  - HTTPS session cookies use `Secure`.
  - The default for same-site admin UI is `SameSite=Lax`; use `Strict` if cross-site embedding is not needed.
  - The dashboard session id is not stored in `localStorage`.
  - Dashboard state-changing requests apply CSRF protection. The default direction is SameSite cookie plus CSRF token; choose either double-submit or synchronizer token during implementation.
  - The server manages session idle timeout, absolute timeout, logout, account disablement, permission changes, and re-authentication after risky events.
  - This follows the OWASP Session Management Cheat Sheet and OWASP Cross-Site Request Forgery Prevention Cheat Sheet guidance for cookies, sessions, and CSRF.

### 6.2 Auth, Session, And Permission Detail Contract

Operators can change default TTLs through environment variables. Defaults for MVP maintainability and extension UX are:

| Item | Default | Reason |
| --- | --- | --- |
| access token TTL | 900 seconds | reduce damage from theft while keeping UX through refresh |
| refresh token TTL | 30 days | do not misread MV3 inactivity or long idle browser use as logout |
| refresh idle timeout | 14 days | clean long-abandoned sessions without disrupting normal extension use |
| refresh rotation | enabled | issue a new refresh token on successful refresh and revoke the previous token hash |
| refresh reuse detection | enabled | if a revoked refresh token is reused, revoke that token family and require re-login |

Chrome Extension MV3 service worker inactivity is not authentication expiry. After worker wake-up, the extension reads stored auth/session metadata and first tries `POST /auth/refresh` if the access token is expired. Re-login is required only for refresh token expiry, revocation, reuse detection, malformed token, server rejection, explicit logout, disabled account, server URL change, or workspace change.

Role/permission matrix:

| Surface | Public | USER | ADMIN |
| --- | --- | --- | --- |
| `/setup/status` | allowed | allowed | allowed |
| `/setup/bootstrap` | allowed only when `setup_required` | not allowed | not allowed after setup completion |
| `/auth/register`, `/auth/login` | allowed | allowed | allowed |
| `/auth/refresh`, `/auth/logout`, `/auth/me` | not allowed | own account in extension token flow | own account in extension token flow |
| `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me`, `/dashboard/session/csrf` | login/csrf allowed | USER cannot enter dashboard | ADMIN dashboard session allowed |
| `/config/extension` | not allowed | allowed | allowed |
| `/prompts/analyze`, `/files/analyze` | not allowed | allowed | allowed |
| `/events`, `/stats/*`, `/status/server` | not allowed | not allowed, `403` | allowed |
| `/users`, `/invites`, `/policies`, `/custom-filters` | not allowed | not allowed, `403` | allowed |
| cross-workspace resource | not allowed | hide existence with `404` | hide existence with `404` |

Account statuses:

- `ACTIVE`: protected routes are usable.
- `DISABLED`: access and refresh are both denied. Protected routes return `403`; tenant resources that must hide existence return `404`.
- `PENDING_INVITE`: login is not allowed.
- `DELETED`: for MVP, use disabled/anonymized metadata instead of hard delete.

### 6.3 Extension Token Auth And Dashboard Session Auth Split

The two auth flows share the same user/role/status model, but transport and storage location differ. Implementers must not treat the two flows as one completed task.

| Category | Extension auth | Dashboard auth |
| --- | --- | --- |
| Main client | Chrome Extension service worker/options | Dashboard web app |
| Login endpoint | `POST /auth/login` | `POST /dashboard/session/login` |
| Current status | `GET /auth/me` | `GET /dashboard/session/me` |
| Renewal | `POST /auth/refresh` | server-managed session renewal or re-login |
| Logout | `POST /auth/logout` | `POST /dashboard/session/logout` |
| Credential storage | access/refresh metadata in extension storage | `HttpOnly` session cookie in browser cookie jar |
| CSRF | not applied by default to bearer-token APIs | required for state-changing dashboard requests |
| Failure UX | re-login in options/status UI | redirect to `/login` or show session-expired banner |

Dashboard session endpoint contract:

| Endpoint | Auth | Purpose | Response core |
| --- | --- | --- | --- |
| `GET /dashboard/session/csrf` | public | issue CSRF token for login form and state-changing requests | `csrf_token`, `expires_at` |
| `POST /dashboard/session/login` | public + CSRF | create ADMIN dashboard session | `user`, `workspace`, `expires_at`; session id only via cookie |
| `GET /dashboard/session/me` | ADMIN session | check current dashboard session | `user`, `workspace`, `role`, `status`, `expires_at` |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | revoke dashboard session | `revoked=true` |

`POST /auth/login` is the extension token-login endpoint. The dashboard does not call this endpoint directly. A dashboard implementation that stores bearer tokens in `localStorage` violates the MVP contract.

## 7. API Boundary And Detailed Contract

This section keeps API responsibility boundaries and detailed request/response contracts together. During implementation, FastAPI/Pydantic/OpenAPI output from `apps/api` is the final contract source, and the extension/dashboard consume that OpenAPI.

### 7.1 Prompt Analyze Boundary

Endpoint: `POST /prompts/analyze`

Server responsibilities:

- request schema validation
- authenticated workspace/user context
- prompt normalization only in memory
- detector pipeline
- risk score calculation
- action decision
- `masked_prompt` generation
- raw-data-free event metadata persistence
- HMAC `prompt_hash`
- duplicate request handling
- safe error responses

Extension responsibilities:

- DOM input extraction
- hold before submit
- request body creation
- timeout handling
- Allow/Warn/Mask/Block UX
- apply server-returned `masked_prompt`
- perform protected resend only when allowed

Values required in request:

- `prompt.text`
- `prompt.input_method`
- `prompt.content_length`
- `context.ai_service`
- `context.ai_service_domain`
- `context.page_url_origin`
- `context.extension_version`
- `context.browser`
- `context.locale`
- `policy.version`
- `client_request_id`

Values prohibited in request:

- `user_id`
- `workspace_id`
- full page URL path/query
- original filename
- secrets in any ID field

Values required in response:

- `event_id`
- `request_id`
- `risk_score`
- `risk_level`
- `action`
- safe `user_message`
- `allow_original_send`
- `requires_justification`
- `detections[]` containing metadata summary only
- `policy.version`
- `policy.latest_version`
- optional `masked_prompt` only when `action=Mask`
- optional `partial_result`

Values prohibited in response:

- raw prompt echo
- raw detected value
- internal detector stack trace
- arbitrary thrown exception text
- full masked prompt persisted in event/dashboard APIs

### 7.2 File Analyze Boundary

Endpoint: `POST /files/analyze`

The MVP file scope is limited to text-family files. PDF, Office documents, OCR, archive extraction, malware scanning, and binary analysis are outside MVP unless a later plan adds them.

The extension may read supported text files in memory and create the request. The server treats file content the same way as prompt text: transient input used only during request processing, not stored, not logged, and not shown on the dashboard.

### 7.3 Extension Config Boundary

Endpoint: `GET /config/extension`

Return values:

- `api_base_url`
- `policy_version`
- `timeout_ms`
- `ai_service_configs[]`
- `file_upload` policy
- selector config for ChatGPT-family pages

The extension uses server selectors first and keeps fallback selectors for failure recovery.

### 7.4 API Server Implementation Scope

- Runtime foundation:
  - Default Docker Compose is `api + postgres`.
  - Redis is not part of the default configuration. Add it as an optional profile only when multi-instance rate limiting, distributed locks, queues, or caches are actually needed.
  - `.env.example` provides development dummy values but must not contain values that look like real secrets.
- Settings:
  - Validate required environment variables at server startup.
  - Explicitly define DB URL, HMAC secret, JWT secret, cookie secret, CORS origin, file size limit, request size limit, and rate limit values.
  - Configuration errors fail with safe messages and do not print secret values.
- Setup/Auth:
  - `GET /setup/status`: return whether workspace/admin bootstrap is needed and safe metadata.
  - `POST /setup/bootstrap`: create first workspace and first ADMIN in a transaction and allow it only once.
  - `POST /auth/register`: create USER according to invite or registration setting.
  - `POST /auth/login`: issue access token and refresh token for the extension.
  - `POST /auth/refresh`: reissue through hash verification without storing raw refresh token value.
  - `POST /auth/logout`: revoke refresh token.
  - `GET /auth/me`: let the extension verify current user and workspace.
  - `POST /dashboard/session/login`: create server-managed session cookie for the dashboard.
  - `GET /dashboard/session/me`: let dashboard verify current ADMIN session.
  - `GET /dashboard/session/csrf`: issue CSRF token for dashboard state-changing requests.
  - `POST /dashboard/session/logout`: revoke dashboard session.
- Permissions:
  - USER is centered on extension usage and own status lookup.
  - ADMIN can access invite, user, policy, filter, dashboard metadata after setup.
  - Disabled users are blocked before protected route execution.
- Analyze:
  - `POST /prompts/analyze`: request validation, detector, scoring, masking, event metadata persistence, response creation.
  - `POST /files/analyze`: analyze text files only as transient input and do not store raw file content.
  - `client_request_id` is used with workspace/user/request fingerprint for duplicate request handling.
- Admin APIs:
  - `/invites`, `/users`, `/policies`, `/custom-filters`, `/events`, `/stats/users`, `/stats/detections`, and `/status/server` must all be raw-data-free metadata APIs.

### 7.5 API Detailed Contract Appendix

This appendix is the minimum contract before implementation. The real server generates OpenAPI with FastAPI/Pydantic, and the extension/dashboard align through generated types or thin adapters. All errors follow `application/problem+json`.

API contract writing format:

Each endpoint must have the same meaning in documentation and OpenAPI. Markdown is human-readable explanation; FastAPI/Pydantic/OpenAPI output is the final machine-consumed schema. For each endpoint, include:

1. Purpose.
2. Authentication and permission.
3. Request `Content-Type`.
4. Request field table.
5. Request JSON example.
6. Success response field table.
7. Success JSON example.
8. Error JSON example.
9. Fields prohibited from storage, logs, or dashboard exposure.
10. Test criteria.

MVP payload format:

- Normal API requests and responses use `application/json`.
- Error responses use `application/problem+json`.
- `POST /files/analyze` also uses JSON in MVP: the extension reads the text file and sends it in the JSON body.
- Revisit `multipart/form-data` in later scope for PDF, Office, large files, or binary upload.
- JSON examples are samples to help implementers understand payloads. Field requiredness and persistence rules are governed by the field tables first.

Common rules:

- For authenticated routes, `workspace_id`, `user_id`, `role`, and `status` come from token/session context.
- Do not put `workspace_id` or `user_id` in request body.
- All list APIs use `limit` and `cursor`. Default `limit=50`; maximum `limit=200`.
- All stored and API times are UTC ISO-8601. The dashboard converts to browser timezone only for display.
- The server creates `request_id`. The extension/dashboard send `client_request_id` as an idempotency key.

| Endpoint | Auth | Request core | Response core | Main errors |
| --- | --- | --- | --- | --- |
| `GET /setup/status` | public/internal | none | `setup_required`, `workspace_exists`, `admin_exists`, `registration_mode` | `503` DB/migration not ready |
| `POST /setup/bootstrap` | public when setup_required | admin email/password/display_name, workspace name | workspace metadata, admin metadata, tokens, audit event id | `409` already completed, `422` weak input |
| `POST /auth/register` | public by registration mode | email/password/display_name/invite_code or workspace_code | user metadata, tokens | `401/403/404/409/422` |
| `POST /auth/login` | public | email/password | extension access token, refresh token, user/workspace metadata | `401`, `403` disabled |
| `POST /auth/refresh` | refresh token | refresh token raw value in request only | new access token, optional rotated refresh token | `401` invalid/expired, `409` reuse detected |
| `POST /auth/logout` | user | refresh token or current session id | `revoked=true` | `401` |
| `GET /auth/me` | user bearer | none | extension user/workspace/role/status metadata | `401`, `403` disabled |
| `GET /dashboard/session/csrf` | public/session | none | CSRF token metadata | `503` |
| `POST /dashboard/session/login` | public + CSRF | email/password | ADMIN session cookie, safe user/workspace metadata | `401/403/422/503` |
| `GET /dashboard/session/me` | ADMIN session | none | dashboard session/user/workspace metadata | `401/403` |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | none | `revoked=true` | `401/403` |
| `GET /config/extension` | user | optional `extension_version` | policy version, timeout, AI service configs, selector configs, file policy | `401`, `403`, `503` |
| `POST /prompts/analyze` | user | transient prompt/context/policy/client_request_id | decision, safe detections, optional `masked_prompt` only for Mask | `400/401/403/409/413/422/503` |
| `POST /files/analyze` | user | transient text file content metadata without original filename | same decision shape as prompt analyze | `400/401/403/413/415/422/503` |
| `GET /events` | ADMIN | filters, cursor, limit | metadata event list | `401/403/404/422` |
| `GET /events/{event_id}` | ADMIN | path id | metadata-only event detail | `401/403/404` |
| `GET /stats/overview` | ADMIN | range, bucket, filters | event/action/risk/user summary | `401/403/422` |
| `GET /stats/users` | ADMIN | range, sort, filters, cursor | user aggregate rows | `401/403/422` |
| `GET /stats/detections` | ADMIN | range, bucket, filters | detector type/category aggregate | `401/403/422` |
| `GET/POST/PATCH /custom-filters` | ADMIN | keyword/regex/action/severity/enabled | filter metadata and version | `401/403/409/422` |
| `POST /custom-filters/dry-run` | ADMIN | sample text in request only | safe match summary only | `401/403/413/422` |
| `GET/PATCH /users` | ADMIN | filters or role/status update | user metadata | `401/403/404/409/422` |
| `GET/POST/PATCH /invites` | ADMIN | invite policy fields | invite metadata without secret reuse | `401/403/404/409/422` |
| `GET /status/server` | ADMIN | none | safe health/status metadata | `401/403/503` |

`POST /prompts/analyze` request fields:

| Field | Type | Required | Description | Storage/logging |
| --- | --- | --- | --- | --- |
| `client_request_id` | string | yes | idempotency key generated by the extension | metadata may be stored |
| `prompt.text` | string | yes | raw source to analyze; used only during request processing | storage/logging prohibited |
| `prompt.input_method` | string | yes | input method such as `keyboard`, `paste`, `file_text`, `unknown` | metadata may be stored |
| `prompt.content_length` | integer | yes | prompt length observed by the extension; server validates it | metadata may be stored |
| `context.ai_service` | string | yes | service name such as `chatgpt` | metadata may be stored |
| `context.ai_service_domain` | string | yes | domain such as `chatgpt.com` | metadata may be stored |
| `context.page_url_origin` | string | yes | origin only; path/query prohibited | metadata may be stored |
| `context.extension_version` | string | yes | extension version | metadata may be stored |
| `context.browser` | string | yes | browser name | metadata may be stored |
| `context.locale` | string | yes | browser/page locale | metadata may be stored |
| `policy.version` | string | yes | policy version known by the extension | metadata may be stored |

`POST /prompts/analyze` response fields:

| Field | Type | Required | Description | Storage/logging |
| --- | --- | --- | --- | --- |
| `event_id` | string | yes | raw-data-free event metadata id | may be stored |
| `request_id` | string | yes | server request trace id | may be stored |
| `risk_score` | integer | yes | score from 0 to 100 | may be stored |
| `risk_level` | string | yes | `none`, `low`, `medium`, `high`, `critical` | may be stored |
| `action` | string | yes | `Allow`, `Warn`, `Mask`, `Block` | may be stored |
| `user_message` | string | yes | safe user-facing text | may be stored |
| `allow_original_send` | boolean | yes | whether raw original send is allowed | may be stored |
| `requires_justification` | boolean | yes | whether a reason is required | may be stored |
| `masked_prompt` | string | only for `Mask` | replacement string generated by the server | prohibit event/dashboard storage |
| `detections[]` | array | yes | raw-data-free detection summary | metadata may be stored |
| `policy.version` | string | yes | policy version used for decision | may be stored |
| `policy.latest_version` | string | yes | latest server policy version | may be stored |
| `partial_result` | boolean | no | limited decision due to partial detector failure, etc. | may be stored |

Analyze request shape:

```json
{
  "client_request_id": "crq_01HX...",
  "prompt": {
    "text": "<transient prompt text; never log or store>",
    "input_method": "keyboard",
    "content_length": 42
  },
  "context": {
    "ai_service": "chatgpt",
    "ai_service_domain": "chatgpt.com",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "0.5.0",
    "browser": "chrome",
    "locale": "ko-KR"
  },
  "policy": {
    "version": "polv_001"
  }
}
```

Analyze response shape for `Mask`:

```json
{
  "event_id": "evt_01HX...",
  "request_id": "req_01HX...",
  "risk_score": 72,
  "risk_level": "high",
  "action": "Mask",
  "user_message": "Sensitive content was detected. Review the masked version before sending.",
  "allow_original_send": false,
  "requires_justification": false,
  "masked_prompt": "<masked text returned only for Mask>",
  "detections": [
    {
      "type": "secret",
      "category": "api_key",
      "severity": "critical",
      "confidence": "high",
      "count": 1,
      "safe_evidence": "API key-like token"
    }
  ],
  "policy": {
    "version": "polv_001",
    "latest_version": "polv_001"
  },
  "partial_result": false
}
```

Analyze response shape for `Allow`:

```json
{
  "event_id": "evt_01HX_ALLOW",
  "request_id": "req_01HX_ALLOW",
  "risk_score": 8,
  "risk_level": "low",
  "action": "Allow",
  "user_message": "No blocking risk was detected.",
  "allow_original_send": true,
  "requires_justification": false,
  "detections": [],
  "policy": {
    "version": "polv_001",
    "latest_version": "polv_001"
  },
  "partial_result": false
}
```

Analyze response shape for `Warn`:

```json
{
  "event_id": "evt_01HX_WARN",
  "request_id": "req_01HX_WARN",
  "risk_score": 46,
  "risk_level": "medium",
  "action": "Warn",
  "user_message": "Business-sensitive context may be included. Review before sending.",
  "allow_original_send": true,
  "requires_justification": false,
  "detections": [
    {
      "type": "business_context",
      "category": "contract",
      "severity": "medium",
      "confidence": "medium",
      "count": 1,
      "safe_evidence": "Contract-related context"
    }
  ],
  "policy": {
    "version": "polv_001",
    "latest_version": "polv_001"
  },
  "partial_result": false
}
```

Analyze response shape for `Block`:

```json
{
  "event_id": "evt_01HX_BLOCK",
  "request_id": "req_01HX_BLOCK",
  "risk_score": 95,
  "risk_level": "critical",
  "action": "Block",
  "user_message": "High-risk secret-like content was detected. The original prompt will not be sent.",
  "allow_original_send": false,
  "requires_justification": true,
  "detections": [
    {
      "type": "secret",
      "category": "private_key",
      "severity": "critical",
      "confidence": "high",
      "count": 1,
      "safe_evidence": "Private key-like block"
    }
  ],
  "policy": {
    "version": "polv_001",
    "latest_version": "polv_001"
  },
  "partial_result": false
}
```

Problem response shape:

```json
{
  "type": "https://docs.oasecure.local/problems/validation-error",
  "title": "Validation error",
  "status": 422,
  "detail": "The request body did not match the expected semantic rules.",
  "instance": "/requests/req_01HX_ERROR",
  "code": "VALIDATION_ERROR",
  "request_id": "req_01HX_ERROR",
  "field_errors": [
    {
      "field": "prompt.content_length",
      "code": "INVALID_LENGTH",
      "message": "content_length must match the submitted prompt length"
    }
  ]
}
```

`POST /files/analyze` request shape:

```json
{
  "client_request_id": "crq_01HX_FILE",
  "file": {
    "text": "<transient text file content; never log or store>",
    "content_length": 128,
    "declared_mime_type": "text/plain",
    "extension": ".txt"
  },
  "context": {
    "ai_service": "chatgpt",
    "ai_service_domain": "chatgpt.com",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "0.5.0",
    "browser": "chrome",
    "locale": "ko-KR"
  },
  "policy": {
    "version": "polv_001"
  }
}
```

`GET /config/extension` response shape:

```json
{
  "api_base_url": "https://promptguard.example.internal",
  "policy_version": "polv_001",
  "timeout_ms": 5000,
  "ai_service_configs": [
    {
      "service": "chatgpt",
      "domains": ["chatgpt.com"],
      "enabled": true
    }
  ],
  "file_upload": {
    "enabled": true,
    "max_file_bytes": 262144,
    "allowed_extensions": [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"]
  },
  "selectors": {
    "chatgpt": {
      "composer": "[contenteditable=\"true\"], textarea",
      "send_button": "[data-testid=\"send-button\"], button[aria-label*=\"보내기\"]"
    }
  }
}
```

Setup/auth request and response examples:

| Endpoint | Request fields | Response fields | Prohibited |
| --- | --- | --- | --- |
| `GET /setup/status` | none | `setup_required`, `workspace_exists`, `admin_exists`, `registration_mode` | DB URL, secret, stack trace |
| `POST /setup/bootstrap` | `workspace.name`, `admin.email`, `admin.password`, `admin.display_name` | workspace/admin metadata, extension tokens, audit id | password echo, password hash, raw request body log |
| `POST /auth/register` | `email`, `password`, `display_name`, `invite_code` or `workspace_code` | user/workspace metadata, extension tokens | invite raw code storage, password echo |
| `POST /auth/login` | `email`, `password` | extension access/refresh token, user/workspace metadata | password echo, refresh token storage |
| `POST /auth/refresh` | `refresh_token` request-only | new access token, optional rotated refresh token | raw token persistence |
| `GET /auth/me` | none | user/workspace/role/status metadata | token/secret/password hash |
| `POST /dashboard/session/login` | `email`, `password`, `csrf_token` | safe user/workspace metadata, session expiry; session id cookie only | session id in JSON/localStorage |

`GET /setup/status` response shape:

```json
{
  "setup_required": true,
  "workspace_exists": false,
  "admin_exists": false,
  "registration_mode": "INVITE_ONLY",
  "server_time": "2026-05-24T00:00:00Z"
}
```

`POST /setup/bootstrap` request shape:

```json
{
  "workspace": {
    "name": "OaSecure"
  },
  "admin": {
    "email": "admin@example.com",
    "password": "<submitted password; never log or echo>",
    "display_name": "Admin"
  }
}
```

`POST /setup/bootstrap` response shape:

```json
{
  "workspace": {
    "id": "wsp_01HX...",
    "name": "OaSecure",
    "status": "ACTIVE"
  },
  "admin": {
    "id": "usr_01HX...",
    "email": "admin@example.com",
    "display_name": "Admin",
    "role": "ADMIN",
    "status": "ACTIVE"
  },
  "extension_auth": {
    "access_token": "<jwt returned to extension clients only>",
    "access_token_expires_at": "2026-05-24T00:15:00Z",
    "refresh_token": "<raw refresh token returned once>"
  },
  "audit_event_id": "aud_01HX..."
}
```

`POST /auth/login` response shape for extension:

```json
{
  "access_token": "<jwt>",
  "access_token_expires_at": "2026-05-24T00:15:00Z",
  "refresh_token": "<raw refresh token returned once>",
  "refresh_token_expires_at": "2026-06-23T00:00:00Z",
  "user": {
    "id": "usr_01HX...",
    "email": "member@example.com",
    "display_name": "Member",
    "role": "USER",
    "status": "ACTIVE"
  },
  "workspace": {
    "id": "wsp_01HX...",
    "name": "OaSecure"
  }
}
```

`POST /dashboard/session/login` response shape:

```json
{
  "user": {
    "id": "usr_01HX_ADMIN",
    "email": "admin@example.com",
    "display_name": "Admin",
    "role": "ADMIN",
    "status": "ACTIVE"
  },
  "workspace": {
    "id": "wsp_01HX...",
    "name": "OaSecure"
  },
  "session": {
    "expires_at": "2026-05-24T08:00:00Z",
    "idle_expires_at": "2026-05-24T01:00:00Z"
  }
}
```

The dashboard session id is delivered only through a `Set-Cookie` header. It is not returned in JSON.

Admin metadata API examples:

| Endpoint | Request/filter | Response core | Prohibited |
| --- | --- | --- | --- |
| `GET /events` | `from`, `to`, `user_id`, `action`, `risk_level`, `detector_type`, `cursor`, `limit` | metadata event list | raw prompt, full mask, raw detected value |
| `GET /events/{event_id}` | path `event_id` | metadata-only detail | original filename, raw evidence |
| `GET/PATCH /users` | filters or role/status patch | user metadata | password hash, token metadata |
| `GET/POST/PATCH /invites` | invite lifecycle fields | invite metadata | raw invite code after creation |
| `GET/POST/PATCH /custom-filters` | name/kind/pattern/action/severity/enabled | filter metadata and version | raw match values |
| `POST /custom-filters/dry-run` | sample text request-only | counts and safe evidence | sample persistence |

`GET /events` response shape:

```json
{
  "items": [
    {
      "event_id": "evt_01HX...",
      "created_at": "2026-05-24T00:00:00Z",
      "user": {
        "id": "usr_01HX...",
        "display_name": "Member"
      },
      "service": "chatgpt",
      "service_domain": "chatgpt.com",
      "action": "Mask",
      "risk_score": 72,
      "risk_level": "high",
      "policy_version": "polv_001",
      "detector_summary": [
        {"type": "secret", "category": "api_key", "count": 1}
      ],
      "prompt_hash_prefix": "ph_7d2a"
    }
  ],
  "next_cursor": null
}
```

`GET /events/{event_id}` response shape:

```json
{
  "event_id": "evt_01HX...",
  "created_at": "2026-05-24T00:00:00Z",
  "user": {
    "id": "usr_01HX...",
    "display_name": "Member",
    "status": "ACTIVE"
  },
  "action": "Mask",
  "risk_score": 72,
  "risk_level": "high",
  "policy_version": "polv_001",
  "service": "chatgpt",
  "service_domain": "chatgpt.com",
  "prompt_hash_prefix": "ph_7d2a",
  "detections": [
    {
      "type": "secret",
      "category": "api_key",
      "severity": "critical",
      "confidence": "high",
      "count": 1,
      "safe_evidence": "API key-like token"
    }
  ]
}
```

`POST /custom-filters` request shape:

```json
{
  "name": "Block internal project code names",
  "kind": "keyword",
  "pattern": "<submitted pattern; validate before storage and never expose raw match values>",
  "severity": "high",
  "action": "Mask",
  "enabled": true
}
```

`POST /custom-filters/dry-run` response shape:

```json
{
  "matched": true,
  "match_count": 2,
  "safe_evidence": [
    {
      "category": "custom_filter",
      "label": "Configured keyword matched",
      "count": 2
    }
  ],
  "sample_persisted": false
}
```

Response prohibitions:

- prompt echo
- raw detected value
- original filename
- full masked prompt in event/dashboard APIs
- raw exception message
- token/secret/password/hash/internal stack trace

## 8. Product Scope And Repository Structure

This section defines the product MVP boundary and code locations. Implementation details follow the API, data, detection, extension, and dashboard sections.

### 8.1 Product Scope

- Product purpose:
  - Detect risk before a user sends sensitive business information, personal data, secrets, contract information, or file content to AI services such as ChatGPT.
  - Do not permanently store raw source text on the server; show admins only metadata and statistics.
  - In a self-hosted environment, an admin operates the server and DB, and team members use the protected flow through the Chrome extension.
- MVP includes:
  - self-hosted server runtime, initial admin bootstrap, login/token refresh, user/invite/registration management.
  - Chrome extension input detection for ChatGPT, submit hold, Analyze API call, Allow/Warn/Mask/Block handling.
  - Python Analyze API, rule-based detectors, custom filters, risk score, server-side masking, duplicate request handling, prompt hash.
  - Admin dashboard setup/auth, overview, event metadata, user stats, policy/custom filter/status screens.
  - Privacy/security regression tests, Docker-based runtime, installation docs, final smoke scenario.
- MVP excludes:
  - external LLM-call-based classification.
  - PDF/Office/OCR/archive/binary file analysis.
  - browser network-request interception.
  - SaaS multi-tenant operation, billing, enterprise organization management.
  - SIEM integration, SSO, advanced policy workflow.

### 8.2 Repository And Code Locations

| Major area | Subarea | Default location | Description |
| --- | --- | --- | --- |
| API server | Python self-hosted API | `apps/api/` | Create with FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. Includes API schema, auth, detectors, masking, event service. |
| Dashboard | Admin UI | `apps/dashboard/` | Includes setup, login, overview, events, users, invites, policies, custom filters, status screens. |
| Extension | Chrome Extension | `apps/extension/` | Already exists. Keep content script, service worker, options, shared types/tests, and align with real API. |
| Infrastructure | Docker/env/reverse proxy | `infra/` | Includes Docker Compose, PostgreSQL, optional Redis profile, reverse proxy examples. |
| Tests | Integration/security/regression | each app `tests/` or root tests | Place app-level unit tests and cross-app privacy/security smoke tests. |

## 9. Data Model And Raw-Data Prohibition Contract

The data model is based on metadata-only persistence. Raw prompts, raw file contents, full `masked_prompt`, raw detected values, and original filenames must not be stored or exposed through DB, logs, dashboard, or error responses.

### 9.1 Data Model Subscope

- Account/organization:
  - `workspaces`: self-hosted workspace unit.
  - `users`: email, display name, role, status, password hash metadata.
  - `refresh_tokens`: raw token storage prohibited; store only hash and expiry/revocation metadata.
  - `registration_settings`, `invites`: registration mode and invite lifecycle.
- Policy:
  - `policies`, `policy_versions`: thresholds, detector enablement, action rule, retention metadata.
  - `ai_service_configs`: ChatGPT-family domains and selector/config.
- Custom filters:
  - `custom_filter_rules`: keyword/regex rule, enabled flag, severity/action metadata.
  - `custom_filter_versions`: change history and policy connection.
  - Risky regex must pass length, syntax, timeout/ReDoS strategy before storage.
- Analysis events:
  - `analysis_events`: event id, workspace/user id, action, risk score, risk level, prompt hash, policy version, metadata.
  - `event_detections`: detection type, category, severity, span hash or safe evidence metadata. Raw detected value prohibited.
  - `event_feedback`: user confirmation/reason metadata. Raw source prohibited.
  - `audit_logs`: setup/auth/admin action metadata. Raw request body prohibited.
- Prohibited columns:
  - Do not create columns such as `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, `raw_detected_value`, `original_filename`, `secret_value`, `token_raw`.

### 9.2 Data Model Detail Contract

The data model contract must be fixed before migrations. The following column names are implementation starting points; real migrations are written with Alembic and must be reviewable.

| Table | Core columns | Constraints |
| --- | --- | --- |
| `workspaces` | `id`, `name`, `created_at`, `status` | `id` primary key |
| `users` | `id`, `workspace_id`, `email`, `display_name`, `role`, `status`, `password_hash`, `created_at`, `updated_at` | `unique(workspace_id, email)`, `foreign key workspace_id` |
| `refresh_tokens` | `id`, `workspace_id`, `user_id`, `token_hash`, `family_id`, `expires_at`, `idle_expires_at`, `revoked_at`, `reused_at`, `created_at` | raw token storage prohibited, `unique(token_hash)`, `foreign key user_id` |
| `registration_settings` | `workspace_id`, `mode`, `workspace_code_hash`, `updated_at` | `mode` enum: `INVITE_ONLY`, `WORKSPACE_CODE`, `OPEN_SIGNUP` |
| `invites` | `id`, `workspace_id`, `code_hash`, `email_domain`, `max_uses`, `used_count`, `expires_at`, `revoked_at` | raw invite code storage prohibited |
| `policies` | `id`, `workspace_id`, `active_version_id`, `created_at` | active policy per workspace |
| `policy_versions` | `id`, `policy_id`, `version`, `thresholds`, `detector_config`, `created_at` | immutable version row |
| `ai_service_configs` | `id`, `workspace_id`, `service`, `domain`, `selector_config`, `enabled`, `version` | extension config source |
| `custom_filter_rules` | `id`, `workspace_id`, `name`, `kind`, `pattern_hash`, `pattern_encrypted_optional`, `severity`, `action`, `enabled` | raw pattern exposure prohibited in MVP, safe regex validation |
| `custom_filter_versions` | `id`, `rule_id`, `version`, `change_type`, `created_by`, `created_at` | change history |
| `idempotency_keys` | `id`, `workspace_id`, `user_id`, `client_request_id`, `request_fingerprint`, `event_id`, `created_at`, `expires_at` | `unique(workspace_id, user_id, client_request_id)` |
| `analysis_events` | `id`, `workspace_id`, `user_id`, `prompt_hash`, `action`, `risk_score`, `risk_level`, `policy_version`, `service`, `service_domain`, `created_at` | raw prompt/masked prompt storage prohibited |
| `event_detections` | `id`, `event_id`, `type`, `category`, `severity`, `confidence`, `count`, `span_hash`, `safe_evidence` | raw detected value storage prohibited |
| `event_feedback` | `id`, `event_id`, `user_id`, `feedback_type`, `reason_code`, `created_at` | free-text reason disabled or redacted in MVP |
| `audit_logs` | `id`, `workspace_id`, `actor_user_id`, `action`, `target_type`, `target_id`, `safe_metadata`, `created_at` | raw request body prohibited |

Prohibited columns:

- `raw_prompt`
- `prompt_text`
- `file_content`
- `masked_prompt`
- `raw_detected_value`
- `original_filename`
- `secret_value`
- `token_raw`
- `refresh_token`
- `password_plain`

Migration order:

1. workspace/user base tables
2. registration/invite/auth token tables
3. policy/config tables
4. custom filter tables
5. idempotency/event/detection/feedback/audit tables
6. seed: default workspace policy, registration mode, base detector config
7. privacy schema scan to check prohibited columns

### 9.3 DB Relationships, Indexes, And Delete Policy

Core relationships:

| Relationship | Standard |
| --- | --- |
| `workspaces 1:N users` | every user belongs to a workspace |
| `users 1:N refresh_tokens` | refresh token family is bound to user and workspace |
| `workspaces 1:N policies` | self-host MVP uses one active policy per default workspace |
| `policies 1:N policy_versions` | policy version rows are immutable |
| `custom_filter_rules 1:N custom_filter_versions` | filter changes remain as version/audit metadata |
| `analysis_events 1:N event_detections` | event has raw-data-free detection summaries |
| `analysis_events 1:N event_feedback` | only user confirmation/reason metadata is stored |

Required unique constraints and indexes:

| Table | Constraint/index | Reason |
| --- | --- | --- |
| `users` | `unique(workspace_id, lower(email))` | prevent duplicate email within workspace |
| `refresh_tokens` | `unique(token_hash)`, index `(user_id, family_id)` | token rotation/reuse detection |
| `invites` | `unique(workspace_id, code_hash)` | prevent duplicates without raw invite code |
| `policy_versions` | `unique(policy_id, version)` | prevent policy version conflict |
| `custom_filter_rules` | index `(workspace_id, enabled)` | analyze pipeline filter load |
| `idempotency_keys` | `unique(workspace_id, user_id, client_request_id)` | prevent duplicate event |
| `analysis_events` | index `(workspace_id, created_at)`, `(workspace_id, user_id, created_at)`, `(workspace_id, action, created_at)` | dashboard list/stat query |
| `event_detections` | index `(event_id)`, `(category)`, `(type)` | detail/stat aggregate |
| `audit_logs` | index `(workspace_id, created_at)`, `(actor_user_id, created_at)` | setup/admin audit |

Delete/disable policy:

- MVP does not hard-delete users. Use `DISABLED` or anonymized metadata.
- Workspace hard delete is not an MVP operations feature.
- Event rows contain only privacy-safe metadata and may be deleted by retention policy.
- Do not re-expose custom filter raw patterns through dashboard/API. If operations require pattern display later, handle encrypted-at-rest fields and separate permission policy in a follow-up plan.
- Audit logs store only action/target/safe_metadata, not raw request bodies.

## 10. Detection, Masking, Scoring, And Custom Filter Contract

Detection and masking are server responsibilities. The extension holds submit and applies the server-returned action and `masked_prompt`.

### 10.1 Detection / Masking Subscope

- Pipeline order:
  - request schema validation.
  - workspace/user/policy load.
  - transient text normalization.
  - built-in detector execution.
  - custom filter detector execution.
  - overlap merge.
  - risk score/action decision.
  - server-side masking generation.
  - raw-data-free event metadata persistence.
  - safe response.
- Detector types:
  - personal data: email, phone, Korean RRN dummy checksum, card Luhn, Korean business registration number.
  - secrets: GitHub token, AWS key, JWT, PEM private key, DB connection string, `.env` secret, high-entropy candidate.
  - business context: contract amount, penalty, NDA, customer information, trade secret, internal strategy, launch plan, pricing policy.
  - custom filter: keyword/regex created by workspace ADMIN.
- Merge rules:
  - secret detection has priority over general business context.
  - within the same priority, longer span wins.
  - overlapping detections are not double-counted in response or statistics.
- Masking:
  - Masking is based on server response `masked_prompt`, not frontend ad-hoc detection.
  - Include `masked_prompt` in the response only for `Mask`.
  - The server does not store/expose `masked_prompt` in event rows or dashboard APIs.
  - Repeated appearances of the same sensitive value use the same placeholder consistently.

### 10.2 Detection, Score, And Action Decision Contract

The server orchestrator, not individual detectors, makes the final action decision. The same input, policy version, and custom filter set must produce the same result.

Base risk score:

| Detection | Base score | Base action |
| --- | ---: | --- |
| confirmed secret: API key, private key, DB URI, JWT | 90 | Block or Mask; policy prioritizes Block for secrets |
| confirmed credential-like `.env` secret | 85 | Mask |
| strong PII such as Korean RRN/card/business id | 80 | Mask |
| email/phone alone | 45 | Warn |
| contract amount/penalty/NDA context | 65 | Warn or Mask |
| customer information/trade secret/internal strategy context | 65 | Warn or Mask |
| ambiguous low confidence | 30 | Allow or Warn |
| custom filter critical | 90 | rule action takes priority |
| custom filter high | 70 | rule action takes priority |

Action decision rules:

1. Secret detection has priority over ordinary business context.
2. If a custom filter has an explicit action, it takes priority within policy safety bounds.
3. Overlap is resolved by secret priority first, then longer span.
4. `risk_score >= 85`: default Block or Mask.
5. `65 <= risk_score < 85`: default Mask or Warn.
6. `40 <= risk_score < 65`: default Warn.
7. `risk_score < 40`: default Allow.
8. If the policy version is stale and conflicts with the latest server policy, return `policy.latest_version` and, when needed, `409` or a safe decision.

Masking:

- Include `masked_prompt` only for Mask action.
- Do not store `masked_prompt`.
- Repeated identical sensitive values use the same placeholder.
- Placeholder examples: `[SECRET_1]`, `[EMAIL_1]`, `[CONTRACT_AMOUNT_1]`.

### 10.3 Custom Filter MVP Boundary

Custom filter is included in MVP, but limited to the following scope.

MVP includes:

- ADMIN list/create/update/disable API.
- keyword/regex kind.
- severity/action metadata.
- enabled flag.
- safe regex validation: length, syntax, timeout or safe-regex strategy.
- dry-run API. Dry-run sample text is request-only and is not stored.
- Analyze pipeline connection and dashboard metadata aggregate.

MVP excludes:

- complex rule-expression builder.
- organization/department policy inheritance.
- regex performance tuning UI.
- raw match value display.
- per-custom-filter raw sample storage.

Custom filter MVP is complete only when API CRUD, dry-run, analyze pipeline connection, dashboard list screen, and ReDoS/privacy tests all exist.

### 10.4 Policy, Rule Pack, And Custom Filter Version Contract

`policy.version` exists for Analyze reproducibility. The same input, workspace, policy version, and custom filter version set must produce the same detector/scoring/action result.

Policy version includes:

- detector enable/disable.
- detector severity override.
- risk score threshold.
- action decision rule.
- reference to custom filter version set.
- file upload limit and allowed extension policy.
- retention metadata.
- reference to extension selector/config version.

Changes that alter policy version:

| Change | Change policy version |
| --- | --- |
| detector enable/disable | yes |
| risk threshold | yes |
| action rule | yes |
| custom filter create/update/disable when it affects Analyze result | yes |
| file upload limit | yes |
| dashboard display order only | no |
| help text/copy | no |
| user role/status | no |

Rule pack contract:

| Field | Description |
| --- | --- |
| `rule_pack_version` | built-in detector/rule bundle version |
| `detector_id` | stable detector id |
| `category` | `secret`, `pii`, `business_context`, `custom_filter` |
| `severity` | base severity |
| `default_action` | default action before policy override |
| `locale_scope` | `ko-KR`, `global`, etc. |
| `test_fixture_id` | matching regression fixture id |

Custom filter version contract:

- The current metadata for a custom filter rule lives in `custom_filter_rules`.
- Change history is appended to `custom_filter_versions`.
- Analyze events store the applied policy version and custom filter version summary as safe metadata.
- Dry-run sample text is not stored.
- Raw match values are neither stored nor displayed.

## 11. Extension Contract

The extension detects input on ChatGPT-family pages, holds submit, then handles UX and resend according to the real self-hosted API decision.

### 11.1 Extension Subscope

- Content script:
  - Runs only on target domains.
  - Finds textarea and contenteditable candidates and selects the current composer based on visible/focus criteria.
  - Holds send-button click and Enter submit until analysis completes.
  - Does not misread writing-assistance actions such as `@` mention, IME composition, Shift+Enter newline, or GPT picker as submit.
- Service worker:
  - Owns API base URL, token, policy/config cache, timeout, and auth error handling.
  - Creates request bodies according to the Analyze API contract and does not inject workspace/user ids manually.
  - Treats MV3 service worker inactivity as normal lifecycle, not as login expiry.
  - On wake-up, reads stored auth/session metadata and attempts automatic refresh first when access token is expired.
  - Requires re-login in options page/status UI only when refresh failure is confirmed.
- Options page:
  - self-host API URL storage.
  - connection test.
  - login/logout/refresh status.
  - server status and policy sync time.
  - Does not show service worker inactivity itself as an error.
  - Shows user action required only for real auth failures such as refresh token expiry/revocation/reuse, disabled account, or server change.
- Action UX:
  - Allow: replay the original send once.
  - Warn: hold before confirmation, send after confirmation.
  - Mask: replace the composer with the server-provided `masked_prompt` and let the user send again.
  - Block: do not trigger original submit.
  - Passing Allow should not show unnecessary panels.

## 12. Dashboard Contract

The dashboard is an admin metadata-only UI. Overview, events, users, invites, policy, custom filter, and status screens show only aggregates and safe metadata, never raw source data.

### 12.1 Dashboard Screen Scope

The dashboard is not a raw-prompt review tool. Admins need to see who frequently creates risky flows, when warning/masking/blocking increases, and whether policy and extension connection state are healthy.

- Common principles:
  - Every screen is metadata-only.
  - Raw prompt, full masked prompt, original filename, raw detected value, secret/token, and stack trace must not be shown in any card, table, detail, chart, or export.
  - Statistics use only event metadata, action, risk score/level, detector type/category, policy version, service/domain, user id/display name, and timestamp bucket.
  - User-level aggregates are needed, but there is no drilldown into the user's actual input content.
- Initial setup/login:
  - check whether initial setup is required.
  - first ADMIN bootstrap.
  - login, refresh, logout.
- MVP overview screen:
  - The first overview screen must include event-level statistics, user-level statistics, and period statistics.
  - Event statistics: Allow/Warn/Mask/Block counts, detector category/type distribution, risk level distribution, top policy version or rule pack distribution.
  - User statistics: event count by user, Warn/Mask/Block count, last event time, top detector category. MVP provides only a top-user table and summary cards.
  - Period statistics: event count trend, action trend, detector-category trend for 24h/7d/30d or a user-selected range.
  - Overview cards: total events, Warn count, Mask count, Block count, active users, block rate/mask rate, latest synced policy version.
  - Charts show trends but must not contain values or long sample text that can reconstruct raw source.
- MVP event screen:
  - event list/filter/detail.
  - filters support period, user, action, risk level, detector type/category, service/domain, policy version.
  - detail shows only safe identifiers such as event id, action, risk score/level, detector type/category, policy version, timestamp, user/workspace metadata, prompt hash prefix or event fingerprint.
  - raw prompt, masked prompt, original filename, raw detected value are not displayed.
- MVP users/invites/registration:
  - USER/ADMIN role and status management.
  - invite creation/revocation.
  - registration mode management.
- MVP policy/status screens:
  - policy read screen.
  - display API, PostgreSQL, migration, and policy readiness.
  - Redis disabled is optional disabled, not an outage.
- MVP custom filter management screen:
  - custom filter list/create/update/disable.
  - dry-run is request-only and does not store sample raw text.
- Follow-up admin analytics screens:
  - user-specific event occurrence detail page.
  - period event timeline, action distribution, detector category distribution, risk trend, policy-version occurrence by user.
  - team/department/group comparison, repeated-risk users, CSV export, admin note, remediation status are follow-up scope.
  - Follow-up screens still do not display raw prompt, full masked prompt, or raw detected values.

Dashboard screen contract:

| Screen | Route | APIs used | Required UI | Empty state | Loading state | Error state | Permission | Test/verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Setup | `/setup` | `GET /setup/status`, `POST /setup/bootstrap` | first workspace/ADMIN form, move to login/dashboard after completion | move to login when setup not needed | prevent duplicate submit during bootstrap | show safe text for `409` setup completed, `422` input error, `503` DB not ready | public only while setup_required | block re-bootstrap after setup, no raw request body/log |
| Login | `/login` | dashboard session login endpoint, `GET /auth/me` | email/password login, re-enter after logout, session status check | redirect to dashboard when already logged in | prevent duplicate submit during login | `401` auth failure, `403` disabled, `503` server not ready | public/authenticated redirect | `HttpOnly` session cookie, CSRF, no localStorage session |
| Overview | `/dashboard` | `GET /stats/overview`, `GET /stats/users`, `GET /stats/detections` | event/user/period stats, action/risk/detector cards/charts | no events in range | skeleton or spinner, keep existing filters | safe error banner and retry on API failure | ADMIN | raw prompt/full masked prompt/original filename/raw detected value not exposed in DOM |
| Events | `/events` | `GET /events` | period/user/action/risk/detector/service/policy filters, cursor list | no filter result | list skeleton, minimize filter disabling | handle invalid filter `422`, `403`, `503` | ADMIN | metadata-only list, cursor/limit, seeded sensitive value not exposed |
| Event detail | `/events/:event_id` | `GET /events/{event_id}` | event id, action, risk, detector category/type, policy version, timestamp, safe fingerprint | not found when deleted/hidden | detail skeleton | distinguish cross-workspace hiding `404` and permission `403` | ADMIN | no raw prompt/full mask/raw detected value/original filename |
| Users | `/users` | `GET/PATCH /users`, `GET /stats/users` | user list, role/status change, user aggregate summary | no users | table skeleton | handle `403`, `404`, `409`, `422` | ADMIN | USER access gets 403, disabled user blocked, no raw prompt drilldown |
| Invites/Registration | `/invites` | `GET/POST/PATCH /invites`, registration settings API | create/revoke invite, registration mode settings | no invites | prevent duplicate mutation buttons | safe message for expired/revoked/duplicate/permission errors | ADMIN | invite secret not re-exposed, audit metadata recorded |
| Policy | `/policy` | `/policies` | current policy, threshold, detector enablement, retention metadata | setup required before policy seed | read skeleton | show policy version conflict or server not ready | ADMIN | read-only MVP, no invalid policy transition |
| Custom filters | `/custom-filters` | `GET/POST/PATCH /custom-filters`, `POST /custom-filters/dry-run` | keyword/regex create/update/disable, dry-run safe summary | no filters | dry-run progress, prevent duplicate save | safe messages for regex syntax/ReDoS/size errors | ADMIN | no dry-run sample storage, no raw match value storage/display |
| Status | `/status` | `GET /status/server` | API, PostgreSQL, migration, policy, optional Redis status | unknown when dependency info missing | polling/loading | required dependency failure is outage, Redis disabled is not outage | ADMIN | no secret/DB URL/token/stack trace, reflect `/readyz` failure |

### 12.2 MVP Dashboard API And Statistics Contract

The MVP dashboard is not a raw-source review tool. Every dashboard API is metadata-only.

Statistic definitions:

- `event count`: number of `analysis_events` rows matching filters.
- `active user`: distinct `user_id` with at least one event in selected period.
- `block rate`: `Block` event count / total event count.
- `mask rate`: `Mask` event count / total event count.
- `warn rate`: `Warn` event count / total event count.
- `top detector category`: top category by event_detections aggregate count.
- `period bucket`: aggregate by stored UTC values; convert to browser timezone only for dashboard display.

`GET /stats/overview` response:

```json
{
  "range": {"from": "2026-05-01T00:00:00Z", "to": "2026-05-24T00:00:00Z", "timezone": "UTC"},
  "totals": {
    "event_count": 120,
    "active_user_count": 8,
    "allow_count": 70,
    "warn_count": 20,
    "mask_count": 25,
    "block_count": 5,
    "block_rate": 0.0417,
    "mask_rate": 0.2083
  },
  "trends": [
    {"bucket_start": "2026-05-24T00:00:00Z", "event_count": 12, "warn_count": 2, "mask_count": 3, "block_count": 1}
  ],
  "top_detector_categories": [
    {"category": "secret", "event_count": 18}
  ],
  "policy_version": "polv_001"
}
```

`GET /stats/users` returns user aggregates. Pagination uses `cursor` and `limit`.

```json
{
  "items": [
    {
      "user_id": "usr_01HX...",
      "display_name": "Member",
      "event_count": 12,
      "warn_count": 2,
      "mask_count": 3,
      "block_count": 1,
      "last_event_at": "2026-05-24T00:00:00Z",
      "top_detector_category": "contract"
    }
  ],
  "next_cursor": null
}
```

MVP event list/detail:

- filters: `from`, `to`, `user_id`, `action`, `risk_level`, `detector_type`, `detector_category`, `service`, `service_domain`, `policy_version`, `cursor`, `limit`.
- sort: default `created_at desc`.
- detail fields: event id, action, risk score/level, detector type/category counts, policy version, service/domain, user metadata, prompt hash prefix, timestamp.
- prohibited: raw prompt, full masked prompt, raw detected value, original filename.

Follow-up admin analytics:

- user-specific event occurrence detail, timeline, group comparison, CSV export, admin notes, and remediation status are post-MVP.
- Follow-up screens also must not display raw prompt, full masked prompt, raw detected value, or original filename.

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
| `privacy_secret_github_token` | dummy shaped like `ghp_testsecret1234567890abcdef` | analyze/file/custom filter dry-run | DB/log/error/dashboard/API response except safe detection summary | raw token absent; `category=api_key` summary allowed |
| `privacy_file_text` | `고객사 담당자 전화번호 010-0000-0000` | `/files/analyze` JSON body | DB/log/dashboard/event detail/original filename fields | raw file text absent; phone detection count allowed |
| `privacy_masked_prompt` | mask response containing `[SECRET_1]` | Mask response only | `analysis_events`, dashboard event/detail/stats, logs | full masked prompt absent from persistence/display |
| `privacy_custom_filter_sample` | dry-run sample sentence | `/custom-filters/dry-run` request | custom filter tables, event tables, logs | sample not persisted; match count only |
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
| `MAX_PROMPT_BYTES` | no | `65536` | prompt body limit |
| `MAX_FILE_BYTES` | no | `262144` | file body limit |
| `MAX_REQUEST_BYTES` | no | `524288` | request body limit |
| `REDIS_URL` | no | empty | used only in optional profile |

## 15. Tests, Done Definition, And Release Gates

This section defines completion criteria. Even if partial feature code exists, MVP is not complete unless fresh install, privacy regression, real API/extension/dashboard smoke all pass.

### 15.1 Test / Done Criteria Subscope

- API unit tests:
  - setup/auth/RBAC.
  - schema validation.
  - health/status/error contract.
  - detector/masking/scoring/idempotency.
  - custom filter CRUD/dry-run.
- Privacy regression:
  - DB schema scan.
  - DB row scan with seeded prompt/secret.
  - application/access/error log scan.
  - error response scan.
  - dashboard DOM/API response scan.
- Extension tests:
  - selector fixture.
  - click/Enter hook.
  - `@` mention/GPT picker exception.
  - Allow/Warn/Mask/Block action.
  - timeout/401.
  - real API smoke.
- Dashboard tests:
  - auth guard.
  - setup flow.
  - metadata-only event detail.
  - user/invite/custom filter UI.
  - status screen.
- Release gates:
  - API, dashboard, extension build/test pass.
  - Docker fresh-install smoke.
  - no external LLM call verification.
  - privacy regression pass.
  - final demo scenario pass.

### 15.2 MVP Done Definition

MVP completion means the following flow passes from a fresh install without interruption, not merely that some code exists.

1. Admin starts API and PostgreSQL with the default Docker Compose.
2. `/readyz` confirms PostgreSQL connection, current migrations, and default policy load.
3. Admin creates the first workspace and first ADMIN through `/setup/bootstrap`.
4. ADMIN logs into the dashboard and can access invite/user/policy/custom filter/status screens.
5. A normal user signs up through invite or allowed registration mode and logs into the extension.
6. The extension calls `/auth/me`, `/config/extension`, and `/prompts/analyze` against the real self-host API.
7. On a ChatGPT target composer, click/Enter submit is held before analysis completion.
8. Allow/Warn/Mask/Block results each behave according to the contracted UX.
9. Mask replaces the composer with server-returned `masked_prompt`, and the server does not store the full `masked_prompt`.
10. Dashboard overview shows event statistics, user aggregate, and period trends as metadata-only.
11. Event/detail/user/status/custom filter screens and API responses do not expose raw prompt, raw file content, full masked prompt, original filename, or raw detected value.
12. API, dashboard, extension tests, privacy regression, Docker fresh-install smoke, and final demo scenario all pass.

MVP release gates:

| Gate | Completion criterion | On failure |
| --- | --- | --- |
| Install | from fresh clone or clean export, configure via `.env.example` and start API/PostgreSQL | fix install docs and compose/env first |
| DB | Alembic migration succeeds on fresh DB and restart | do not proceed with feature work before fixing migration |
| Auth | setup/login/refresh/logout/auth/me/RBAC tests pass | do not proceed with extension/dashboard integration |
| Analyze | schema validation, detector, scoring, masking, idempotency, event metadata persistence pass | do not mark dashboard stats or extension smoke complete |
| Dashboard | overview/events/users/invites/policy/custom filter/status work metadata-only | release prohibited if raw-data scan fails |
| Extension | selector, click/Enter, `@` mention exception, Allow/Warn/Mask/Block, 401 refresh, real API smoke pass | re-verify real ChatGPT smoke |
| Privacy | seeded sensitive value absent from DB/log/error/dashboard/API response scan | release prohibited until raw storage/exposure boundary is fixed |
| Release gate | API/dashboard/extension build/test, Docker smoke, no external LLM call, final demo pass | do not mark complete |

### 15.3 Test Command Matrix

| Area | Command | Completion criterion |
| --- | --- | --- |
| API unit/integration | `cd apps/api && pytest` | setup/auth/RBAC/analyze/custom filter/status/error/privacy tests pass |
| API privacy scan | `cd apps/api && pytest tests/privacy` | seeded sensitive values absent from DB/log/error responses |
| Dashboard | `cd apps/dashboard && npm test` | auth guard, setup, overview, metadata-only detail, user/invite/custom filter/status UI pass |
| Extension | `python apps/extension/tests/run_extension_checks.py all` | selector, hook, action UX, auth refresh, API client fixture pass |
| Root build | `npm run build --workspaces` | dashboard/extension JS build pass. Python API is verified separately by pytest/compose |
| Docker smoke | after `docker compose up --build`, run health checks | `/livez`, `/readyz`, `/healthz`, setup/login/analyze/dashboard smoke pass |
| Release gate | each area build/test + privacy regression + no external LLM verification | MVP can be marked complete |

### 15.4 PM Execution Order And PR Bundles

The 102 WBS rows are executed in the following PR bundle order. If the contract/tests of an earlier bundle do not exist, later bundles can proceed only at mock level and must not be marked complete.

| Order | PR bundle | Included WBS | Purpose | Completion condition |
| --- | --- | --- | --- | --- |
| P0-1 | Monorepo/API/Compose scaffold | 6-11 | `apps/api`, `apps/dashboard`, `infra`, PostgreSQL, settings, health skeleton | base compose starts API+PostgreSQL, `/livez`/`/readyz`/`/healthz` skeleton passes |
| P0-2 | Setup/Auth/session/RBAC | 12-27 | bootstrap, registration, extension token auth, dashboard session auth, RBAC | setup/auth/session/RBAC tests pass, auth endpoints are split |
| P0-3 | Metadata-only DB/event/idempotency | 28-33, 90-91 | Analyze schema, prompt hash, idempotency, event metadata, privacy DB/log scan | duplicate event prevented, prohibited column/log scan passes |
| P0-4 | Core detectors/scoring/masking | 34-47, 53-56, 98 | PII/secret/business context, merge, score, server-side mask, corpus | detector/scoring/masking tests and corpus smoke pass |
| P0-5 | Extension real API integration | 57-73, 94-95 | connect existing extension to real API | real `/auth/me`/`/config/extension`/`/prompts/analyze` smoke passes |
| P0-6 | Dashboard MVP metadata UI | 74-89, 97 | setup/login/overview/events/users/invites/policy/custom filter/status | metadata-only API/DOM privacy tests pass |
| P1-1 | Custom filter full MVP | 48-52, 87 | custom filter CRUD/dry-run/pipeline/dashboard | ReDoS/privacy/custom filter integration passes |
| P1-2 | Release/docs/final smoke | 5, 99-102 | README/install/admin/privacy/release/demo | fresh install demo and release gate pass |

Priority rules:

- P0 is required for MVP completion.
- P1 is included in MVP, but cannot be completed before the P0 API/DB/dashboard foundation exists.
- P2/post-MVP includes user-specific detailed analytics, CSV export, admin notes, advanced policy workflow, PDF/Office/OCR, SSO/SIEM.
- Passing extension mock/fake backend does not complete P0-5. Real self-host API smoke is required.

### 15.5 Final Smoke / Demo Scenario

Final smoke runs in the following order from a fresh install.

1. Start API and PostgreSQL with `docker compose up --build`.
2. `GET /livez` returns `200`.
3. `GET /readyz` returns `200` with DB connection, current migration, and default policy load.
4. `GET /setup/status` returns `setup_required=true`.
5. Create the first workspace and ADMIN with `POST /setup/bootstrap`.
6. Create an ADMIN session in the dashboard with `POST /dashboard/session/login`.
7. Dashboard routes `/dashboard`, `/events`, `/users`, `/invites`, `/policy`, `/custom-filters`, `/status` open.
8. Create an invite and register a normal USER.
9. In extension options, save self-host API URL and verify `GET /auth/me`, `GET /config/extension`.
10. Enter `NDA 위약금은 3억원입니다` in ChatGPT composer and verify Warn or Mask appears.
11. Enter a dummy secret fixture and verify Mask or Block appears and raw submit does not occur.
12. Mask action replaces the composer with server-returned `masked_prompt` and does not auto-send.
13. Dashboard overview shows event/action/user/period metadata statistics.
14. Verify seeded raw values do not appear in events/detail/users/custom filters/status screens or API responses.
15. Run DB/log/error/dashboard privacy scans and no external LLM call check.

Smoke fixtures:

| Name | Input | Expected result |
| --- | --- | --- |
| allow_basic | `오늘 회의 안건 정리해줘` | Allow, no panel, raw send allowed |
| warn_contract | `NDA 위약금은 3억원입니다` | Warn or Mask, no raw storage |
| mask_email_phone | `담당자 test@example.com 010-0000-0000` | Mask, placeholders applied |
| block_private_key | dummy PEM private key block | Block, no raw submit |
| custom_filter | sentence containing ADMIN-created keyword | custom filter action applied |

## 16. WBS Document-Order Work Table

`Document order` is renumbered from 1 inside this v5 document for readability. The original WBS owner, area, category, item, and detail are preserved, but because the current CSV mixes owner order, the document uses continuous numbering.

Status criteria:

- `Done`: actual implementation or documentation is confirmed in the current repo.
- `Partial`: partial implementation/documentation exists, but it is insufficient for self-host MVP completion.
- `Not Done`: the implementation is not present in the current repo.
- `Deferred`: the implementation contract cannot be closed without a user decision or external dependency. Do not use this for fixed decisions such as Python/FastAPI/PostgreSQL/Redis optional.

Each WBS row's `v5 implementation instruction` is an implementation ticket containing:

- Remaining implementation: code, tests, or documentation still required in the current repo.
- Prerequisites: API, schema, screen, migration, fixture, or settings needed before starting.
- PR completion criterion: observable output that lets the item be marked complete.
- Test/verification: command, privacy/security scan, smoke, or document verification.

| Document order | Phase | Category | Item | Owner | Area | Original detail | Current status | v5 implementation instruction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Preparation/Planning | Scope confirmation | Confirm open-source MVP scope | 김현성 | Planning·QA·Docs | Self-host, signup, no raw storage, custom filter scope table | Partial | Remaining: align README/install/admin/privacy docs with v5 MVP scope. Prereq: v5 contract fixed. PR criterion: self-host, signup, no raw storage, custom filter, dashboard scope are described consistently in docs and repo structure. Verification: document grep and final demo checklist. |
| 2 | Preparation/Planning | Priority | Reclassify P0/P1/P2 requirements | 김현성 | Planning·QA·Docs | Required/optional/follow-up scope table | Partial | Remaining: sync MVP required, optional, follow-up scope table with this WBS. Prereq: API/dashboard/extension scope fixed. PR criterion: every WBS row has MVP/follow-up/optional status and completion criteria. Verification: review that out-of-scope features are not mixed into MVP done definition. |
| 3 | Preparation/Planning | User flow | Document install, signup, extension, dashboard flow | 김영은 | Dashboard·UI | Setup -> signup -> Extension -> Dashboard flow diagram | Not Done | Remaining: flow diagram and screen skeleton for setup -> login/signup -> extension connection -> analyze -> dashboard metadata view. Prereq: setup/auth/session API contract. PR criterion: dashboard routes and empty/loading/error states connect to the flow. Verification: setup/login/dashboard smoke. |
| 4 | Preparation/Planning | Configuration decision | Write self-host server configuration decision | 유지수 | Server·Security | Docker, DB, Redis, reverse proxy configuration | Partial | Remaining: Python/FastAPI/PostgreSQL base configuration and Redis optional profile docs/compose. Prereq: env schema and health contract. PR criterion: base compose starts API+PostgreSQL without Redis, optional Redis shows disabled. Verification: Docker smoke, `/readyz`, `/healthz`. |
| 5 | Preparation/Planning | Verification plan | List tests and release gates | 전체 | Planning·QA·Docs | Install, E2E, privacy, security tests | Partial | Remaining: connect API/dashboard/extension/privacy/security/release gates to implementation subplans and CI commands. Prereq: each app scaffold and test runner. PR criterion: every MVP slice has completion criteria and test command. Verification: `pytest`, dashboard test, extension checks, Docker smoke, privacy regression. |
| 6 | OSS·Setup·Auth | Repository | Create monorepo base structure | 김현성 | Chrome Extension | apps/api, apps/dashboard, apps/extension, packages, docs, infra | Partial | Only `apps/extension` exists. Python API, dashboard, and infra are next implementation targets. |
| 7 | OSS·Setup·Auth | Runtime | Docker Compose runtime configuration | 김현성 | Chrome Extension | API, dashboard, PostgreSQL, Redis compose file | Not Done | Keep Redis only as optional profile and create Python API/PostgreSQL compose first. |
| 8 | OSS·Setup·Auth | Environment variables | Implement `.env.example` and startup validation | 전체 | Planning·QA·Docs | required env validation and dummy secret file | Not Done | Write Python config validation and safe dummy secret examples. |
| 9 | OSS·Setup·Auth | Build | Organize common build scripts for API, UI, extension | 김현성 | Chrome Extension | dev/build/test scripts and package commands | Partial | Root workspace is needed, but JS-only workspace assumptions must be revisited because the server is Python. |
| 10 | OSS·Setup·Auth | Status check | Implement server health check endpoint | 유지수 | Server·Security | `/healthz` response and dependency status | Not Done | Implement `/livez`, `/readyz`, `/healthz`, dashboard status schema. |
| 11 | OSS·Setup·Auth | Migration | Build DB migration runtime skeleton | 유지수 | Server·Security | fresh install/restart migration verification | Not Done | Write migration runner based on SQLAlchemy 2.x + Alembic. |
| 12 | OSS·Setup·Auth | Initial setup | Implement setup status API | 김영은 | Server·Security | `/setup/status`, setup_required response | Not Done | Write Python API endpoint and tests. |
| 13 | OSS·Setup·Auth | Initial setup | Implement first admin bootstrap API | 김영은 | Server·Security | create workspace, ADMIN, default policy | Not Done | Implement setup lock, transaction, one-time bootstrap. |
| 14 | OSS·Setup·Auth | Initial setup | Implement bootstrap one-time limit and audit record | 김영은 | Server·Security | setup lock, SETUP_COMPLETED audit | Not Done | Implement PostgreSQL constraint and audit metadata. |
| 15 | OSS·Setup·Auth | Initial screen | Implement first admin creation screen | 김영은 | Dashboard·UI | `/setup` input screen and completion navigation | Not Done | Implement dashboard setup screen and API integration. |
| 16 | OSS·Setup·Auth | Config seed | Seed default workspace, policy, registration setting | 김영은 | Server·Security | INVITE_ONLY default, default policy version | Not Done | Implement through fresh DB seed/migration. |
| 17 | OSS·Setup·Auth | Account DB | Create users, invites, registration_settings tables | 유지수 | Server·Security | users, invites, registration_settings migration | Not Done | Write PostgreSQL migration. |
| 18 | OSS·Setup·Auth | Password | Store password hash | 유지수 | Server·Security | Argon2id/bcrypt, plaintext-not-stored test | Not Done | Prefer Argon2id and make cost parameters configurable in operations. |
| 19 | OSS·Setup·Auth | Login | Implement login, refresh, auth/me API | 유지수 | Server·Security | issue access/refresh token and return user info | Not Done | Implement raw refresh-token non-storage and `/auth/me`. |
| 20 | OSS·Setup·Auth | Token protection | Handle refresh token hash, expiry, revocation | 유지수 | Server·Security | verify refresh_tokens raw value not stored | Not Done | Implement token hash, expiry, revoke, rotation tests. |
| 21 | OSS·Setup·Auth | Permission | Implement ADMIN/USER permission middleware | 유지수 | Server·Security | USER access to Admin API returns 403 | Not Done | Apply role guard and 403/404 policy. |
| 22 | OSS·Setup·Auth | Invite | Implement normal member invite signup API | 김민지 | Server·Security | valid invite signup, invalid code rejection | Not Done | Implement invite validation, max uses, expiry. |
| 23 | OSS·Setup·Auth | Invite management | Implement invite code create/revoke API | 김민지 | Server·Security | max_uses, expires_at, revoked handling | Not Done | Implement ADMIN invite CRUD. |
| 24 | OSS·Setup·Auth | Registration mode | Handle INVITE_ONLY, WORKSPACE_CODE, OPEN_SIGNUP | 김민지 | Server·Security | allow/block tests by registration mode | Not Done | Implement registration mode state machine. |
| 25 | OSS·Setup·Auth | User management | Implement user status/role change API | 김민지 | Server·Security | ACTIVE/DISABLED, USER/ADMIN change | Not Done | Implement ADMIN user management API. |
| 26 | OSS·Setup·Auth | Auth verification | Write signup/login/permission tests | 김민지 | Planning·QA·Docs | setup/auth/RBAC integration tests | Not Done | Write pytest/API integration tests. |
| 27 | OSS·Setup·Auth | Security settings | Apply CORS and base rate-limit policy | 유지수 | Server·Security | allowed origins, auth/analyze request limits | Not Done | Implement explicit CORS and start with in-process/Postgres rate limit. |
| 28 | Analysis/Detection | Request validation | Validate Analyze API request schema | 김현성 | Server·Security | validate prompt/context/policy/client_request_id | Not Done | Implement with Pydantic v2 schema and OpenAPI. |
| 29 | Analysis/Detection | Raw-source protection | Implement raw_prompt non-storage boundary | 김현성 | Planning·QA·Docs | block request body logging and redaction hook | Not Done | Build redacted logger and privacy tests first. |
| 30 | Analysis/Detection | Duplicate handling | Handle duplicate `client_request_id` requests | 김현성 | Server·Security | idempotency policy and duplicate event prevention | Not Done | Implement PostgreSQL idempotency metadata and Mask recompute rule. |
| 31 | Analysis/Detection | Hash | Implement HMAC prompt_hash | 김현성 | Server·Security | workspace-separated hash and secret injection | Not Done | Implement workspace-scoped HMAC key id and secret injection. |
| 32 | Analysis/Detection | Event DB | Create analysis event and detection detail tables | 김민지 | Server·Security | migration prohibiting raw_prompt, masked_prompt, value | Not Done | Create metadata-only schema migration. |
| 33 | Analysis/Detection | Event persistence | Implement raw-data-free event persistence service | 김민지 | Server·Security | store user, service, detection_types, risk, action | Not Done | Implement event service and transaction boundary. |
| 34 | Analysis/Detection | Personal data | Implement email/phone detection | 유지수 | Server·Security | EMAIL/PHONE detection functions and unit tests | Not Done | Deterministic detectors plus corpus tests. |
| 35 | Analysis/Detection | Personal data | Implement Korean RRN checksum validation | 유지수 | Server·Security | valid/invalid dummy RRN tests | Not Done | Dummy-only checksum tests. |
| 36 | Analysis/Detection | Personal data | Implement card number Luhn validation | 유지수 | Server·Security | detect only Luhn-valid numbers | Not Done | Luhn test vectors. |
| 37 | Analysis/Detection | Korean localization | Implement business registration number candidate/validation | 유지수 | Planning·QA·Docs | business number candidates and checksum tests | Not Done | Korean business-number test corpus. |
| 38 | Analysis/Detection | Business candidate | Detect amount, discount rate, contract period candidates | 유지수 | Planning·QA·Docs | Korean business sentence candidate test set | Not Done | Context evidence corpus. |
| 39 | Analysis/Detection | Secrets | Implement GitHub/AWS key detection | 김영은 | Server·Security | `ghp_`, `github_pat_`, AKIA/ASIA tests | Not Done | Secret detector tests. |
| 40 | Analysis/Detection | Secrets | Implement JWT/private key block detection | 김영은 | Server·Security | JWT 3-part, PEM block tests | Not Done | JWT/PEM detector tests. |
| 41 | Analysis/Detection | Secrets | Implement DB connection string detection | 김영은 | Server·Security | postgres/mysql/mongodb URI detection | Not Done | URI detector with redaction tests. |
| 42 | Analysis/Detection | Secrets | Detect `.env` secret and high-entropy candidates | 김영은 | Server·Security | PASSWORD/SECRET key=value, entropy tests | Not Done | Env and entropy detector. |
| 43 | Analysis/Detection | Rule pack | Write Korean-localized rule pack structure | 김민지 | Planning·QA·Docs | rule_pack_version, label, severity spec | Not Done | Rule pack schema and fixtures. |
| 44 | Analysis/Detection | Context classification | Implement contract-information rule classifier | 김현성 | Planning·QA·Docs | contract amount, penalty, NDA context tests | Not Done | Rule classifier and corpus tests. |
| 45 | Analysis/Detection | Context classification | Implement customer-information rule classifier | 유지수 | Planning·QA·Docs | customer company, contact person, inquiry combination tests | Not Done | Customer context classifier. |
| 46 | Analysis/Detection | Context classification | Implement trade-secret/internal-strategy classifier | 김영은 | Planning·QA·Docs | pricing policy, launch plan, competitive strategy tests | Not Done | Strategy context classifier. |
| 47 | Analysis/Detection | Context classification | Handle low-confidence/ambiguous sentences | 김민지 | Planning·QA·Docs | AMBIGUOUS handling and exclusion from strong block | Not Done | Ambiguous evidence scoring rule. |
| 48 | Analysis/Detection | Custom filter | Create custom filter tables | 유지수 | Server·Security | custom_filter_rules, versions migration | Not Done | Custom filter migrations. |
| 49 | Analysis/Detection | Custom filter | Implement regex/keyword filter API | 김현성 | Server·Security | create/update/disable/list API | Not Done | ADMIN CRUD with safe regex validation. |
| 50 | Analysis/Detection | Custom filter | Validate risky regex before storage | 전체 | Planning·QA·Docs | length, syntax, execution timeout, ReDoS defense | Not Done | ReDoS tests and safe-regex strategy. |
| 51 | Analysis/Detection | Custom filter | Implement filter dry-run API | 김민지 | Server·Security | sample raw text non-storage test | Not Done | Dry-run request-only, no persistence. |
| 52 | Analysis/Detection | Custom filter | Connect custom filters to analysis pipeline | 김현성 | Server·Security | custom_filter detection and statistics metadata | Not Done | Detector pipeline integration. |
| 53 | Analysis/Detection | Merge | Implement overlap merge rules for detections | 김현성 | Server·Security | secret priority, longer span priority tests | Not Done | Overlap merge priority tests. |
| 54 | Analysis/Detection | Risk | Implement risk score and action decision rules | 전체 | Planning·QA·Docs | 0-100 score, Allow/Warn/Mask/Block | Not Done | Deterministic scoring policy. |
| 55 | Analysis/Detection | Masking | Replace personal data/secrets with placeholders | 유지수 | Server·Security | replace repeated PII/API_KEY/DB URL values | Not Done | Server-side masking with no storage. |
| 56 | Analysis/Detection | Analysis integration | Integrate full Analyze API flow | 유지수 | Server·Security | detector -> score -> mask -> log -> response integration | Not Done | Orchestrator and integration tests. |
| 57 | Extension | Skeleton | Write Manifest V3 extension scaffold | 김현성 | Chrome Extension | content script, service worker, options structure | Done | Only maintenance and real API adapter integration remain. |
| 58 | Extension | Server connection | Implement self-host API URL input screen | 김현성 | Chrome Extension | API base URL storage and connection verification | Partial | Mock/real connection UI exists; real `/auth/me` server is needed. |
| 59 | Extension | Login | Handle extension login/token storage | 김현성 | Chrome Extension | token storage, refresh, logout behavior | Partial | Token storage exists; real refresh/logout server integration remains. MV3 service worker inactivity is not auth expiry; attempt automatic refresh first on access-token expiry. |
| 60 | Extension | Config sync | Sync server selector and policy config | 김현성 | Chrome Extension | `/config/extension` call and cache | Partial | Client/cache exists; real server endpoint is needed. |
| 61 | Extension | Domain | Limit activation to ChatGPT domains | 김현성 | Chrome Extension | separate target/non-target domain behavior | Done | Maintain ChatGPT-like selector regression. |
| 62 | Extension | Input detection | Implement textarea input detection | 김현성 | Chrome Extension | candidate selection by visible/focus | Done | Maintain DOM change smoke. |
| 63 | Extension | Input detection | Implement contenteditable input detection | 김현성 | Chrome Extension | contenteditable fallback detection | Done | Real ChatGPT smoke needed. |
| 64 | Extension | Submit hold | Intercept send-button click | 김현성 | Chrome Extension | hold submit until analysis completes | Done | Maintain selector drift tests. |
| 65 | Extension | Submit hold | Intercept Enter/shortcut submit | 김현성 | Chrome Extension | Enter/Shift+Enter branch | Done | Maintain `@` mention/GPT picker exception regression test. |
| 66 | Extension | API integration | Implement Analyze API client | 김현성 | Chrome Extension | request body creation, 401/timeout handling | Partial | Client exists; real server and shared/generated schema needed. |
| 67 | Extension | Duplicate prevention | Prevent duplicate send of approved prompt | 김현성 | Chrome Extension | allow hash, double-submit guard | Done | Keep separate from server idempotency. |
| 68 | Extension | Action handling | Resume Allow send | 김현성 | Chrome Extension | replay original send once | Done | Verify in real API smoke. |
| 69 | Extension | Action handling | Implement Warn panel | 김현성 | Chrome Extension | hold before confirmation, send after confirmation | Done | Keep UX copy safe. |
| 70 | Extension | Action handling | Implement Mask panel and choice behavior | 김현성 | Chrome Extension | apply mask, cancel, request reason | Done | Needs server-supplied mask and smoke. |
| 71 | Extension | Masking | Replace input with `masked_prompt` | 김현성 | Chrome Extension | textarea/contenteditable replacement | Done | Keep automatic-send prohibition. |
| 72 | Extension | Blocking | Implement Block notice and raw send block | 김현성 | Chrome Extension | verify raw submit does not occur | Done | Maintain fixture and real smoke. |
| 73 | Extension | Notice/status | Storage/non-storage notice and connection status screen | 김현성 | Chrome Extension | notice, policy sync time, server status | Partial | Server status endpoint does not exist yet. |
| 74 | Dashboard/Admin | Screen skeleton | Build dashboard routing and layout | 김영은 | Dashboard·UI | routing, auth guard, shared layout | Not Done | Implement dashboard scaffold. |
| 75 | Dashboard/Admin | Setup screen | Connect setup/login screens | 김영은 | Dashboard·UI | first admin creation, login screen | Not Done | Implement UI after setup/auth API. |
| 76 | Dashboard/Admin | Summary | Connect overview summary API | 김영은 | Dashboard·UI | period totals, risk trend data connection | Not Done | MVP required. Needs metadata summary APIs for event/action/detector/user/period. |
| 77 | Dashboard/Admin | Summary | Implement overview cards and trend charts | 김영은 | Dashboard·UI | event, Warn, Mask, Block cards | Not Done | MVP required. Display event/user/period statistics on the first screen. |
| 78 | Dashboard/Admin | Events | Implement Risk Events list and filters | 김영은 | Dashboard·UI | period, type, action, risk filters | Not Done | MVP required. Implement period, user, action, risk, detector, service/domain filters without raw values. |
| 79 | Dashboard/Admin | Events | Implement raw-data-free event detail | 김영은 | Dashboard·UI | show only event_id, type, score, policy version | Not Done | MVP required. Needs safe metadata detail and privacy UI tests. |
| 80 | Dashboard/Admin | User stats | Implement per-user event stats API | 유지수 | Server·Security | per-user type/count/action distribution API | Not Done | MVP required. Separate user aggregate API from follow-up drilldown API. |
| 81 | Dashboard/Admin | User stats | Implement per-user event table | 김민지 | Dashboard·UI | user, department, top detection, last event | Not Done | MVP required. Top-user/user summary table; detailed user audit page is follow-up. |
| 82 | Dashboard/Admin | User stats | Implement user action/detection-type charts | 김민지 | Dashboard·UI | stacked bar, detection heatmap data | Not Done | MVP required. Metadata-only charts; personal timeline/detail is follow-up. |
| 83 | Dashboard/Admin | User management | Implement Users management screen | 김민지 | Dashboard·UI | list, role/status change | Not Done | Admin UI. |
| 84 | Dashboard/Admin | Registration management | Implement Invites/Registration screen | 김민지 | Dashboard·UI | invite create/revoke, registration mode settings | Not Done | Invite/registration UI. |
| 85 | Dashboard/Admin | Policy | Implement current-policy read screen | 김민지 | Dashboard·UI | show threshold, detector, retention | Not Done | Policy read-only UI first. |
| 86 | Dashboard/Admin | Statistics | Implement detection-type statistics screen | 김민지 | Dashboard·UI | detection type trend and action count | Not Done | Metadata charts. |
| 87 | Dashboard/Admin | Custom filter | Implement custom filter management screen | 김민지 | Dashboard·UI | filter list, create, update, dry-run UI | Not Done | After custom filter APIs. |
| 88 | Dashboard/Admin | Status | Server health/degraded status screen | 김민지 | Dashboard·UI | API/DB/Redis status display | Not Done | Redis only when enabled. |
| 89 | Dashboard/Admin | Raw-source prohibition | Dashboard raw-source non-exposure screen tests | 전체 | Planning·QA·Docs | verify raw_prompt, masked_prompt, detected value hidden | Not Done | MVP required. Scan overview/event/user/status/custom filter DOM/API responses with seeded sensitive values. |
| 90 | Integration·Security·Docs | Privacy | Write DB raw-source non-storage regression tests | 전체 | Planning·QA·Docs | prohibited column and seeded prompt DB scan | Not Done | pytest/schema scan. |
| 91 | Integration·Security·Docs | Privacy | Write log raw-source non-storage regression tests | 전체 | Planning·QA·Docs | application/access/error log seeded scan | Not Done | Log capture tests. |
| 92 | Integration·Security·Docs | Security | Write external LLM call prohibition verification | 전체 | Planning·QA·Docs | network mock, zero outbound LLM calls | Not Done | No external LLM CI check. |
| 93 | Integration·Security·Docs | Security | Write setup/auth/RBAC security tests | 전체 | Planning·QA·Docs | one-time bootstrap, USER 403, token expiry | Not Done | Auth security tests. Include regression that service worker inactivity does not lead to re-login and re-login is requested only after refresh failure conditions. |
| 94 | Integration·Security·Docs | E2E | Write extension core-flow E2E | 전체 | Chrome Extension | Allow/Warn/Mask/Block fixture tests | Done | Current extension tests exist. Real API E2E is needed after server implementation. |
| 95 | Integration·Security·Docs | E2E | Write selector-change regression tests | 전체 | Chrome Extension | remote selector update fixture | Partial | Extension fixture exists. Real config endpoint is needed. |
| 96 | Integration·Security·Docs | Integration | Analyze API integration/performance tests | 전체 | Server·Security | happy/error path, p95 500ms measurement | Not Done | Python API performance tests. |
| 97 | Integration·Security·Docs | Integration | Dashboard integration/performance tests | 전체 | Dashboard·UI | 30-day summary/user stats p95 measurement | Not Done | Write dashboard/API tests. |
| 98 | Integration·Security·Docs | Quality | Korean FP/FN corpus evaluation | 전체 | Planning·QA·Docs | PII/secret/business-context positive/negative report | Not Done | Corpus and report. |
| 99 | Integration·Security·Docs | Docs | Write README, install, reverse proxy docs | 전체 | Planning·QA·Docs | README, install.md, HTTPS guide | Not Done | After compose/API shape. |
| 100 | Integration·Security·Docs | Docs | Write admin, privacy, contribution docs | 전체 | Planning·QA·Docs | admin-guide, privacy-design, contributing | Not Done | After dashboard/API privacy behavior is fixed. |
| 101 | Integration·Security·Docs | Release | Build Docker image and extension package | 전체 | Chrome Extension | release artifact, sideload zip, version check | Not Done | Write release plan after full MVP completion. |
| 102 | Integration·Security·Docs | Closing | Final smoke test and demo scenario | 전체 | Dashboard·UI | setup -> signup -> Extension -> Dashboard demo | Not Done | Write final end-to-end demo. |

## 17. Owner-Sorted AI Work Instructions

This section regroups the WBS document-order work table by person for execution. For detailed original order and status judgment, section 16 is authoritative.

### 김현성

Implementation scope: extension, API boundary, Analyze request validation, raw-source protection, idempotency, HMAC hash, contract-information classification, custom filter API/pipeline, overlap merge.

- Related WBS rows: 28, 29, 30, 31, 44, 49, 52, 53, 57-73.
- Sections to read: `6. Auth, Session, And Permission Contract`, `7. API Boundary And Detailed Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `11. Extension Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Implementation locations: `apps/extension/*`, future `apps/api/*` modules for analyze/custom filter/idempotency/hash, extension API adapter and tests.
- Prerequisites: Python API scaffold, auth context, PostgreSQL idempotency/event tables, OpenAPI output.
- Remaining implementation: real self-host API smoke, request schema validation, raw prompt logging block, duplicate `client_request_id` handling, workspace-scoped HMAC `prompt_hash`, custom filter CRUD/pipeline, overlap merge.
- PR completion criterion: extension DOM hook regression remains passing; real `/auth/me`, `/config/extension`, `/prompts/analyze` calls pass; raw prompt and full masked prompt are absent from DB/log/error/dashboard.
- Test method: `python apps/extension/tests/run_extension_checks.py all`, `cd apps/api && pytest tests/analyze tests/privacy tests/custom_filters`.

### 김영은

Implementation scope: dashboard screens, setup/login screen, overview/events screen, secret detector, trade-secret/internal-strategy context classifier.

- Related WBS rows: 39, 40, 41, 42, 46, 74, 75, 76, 77, 78, 79.
- Sections to read: `8. Product Scope And Repository Structure`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `12. Dashboard Contract`, `13. Security And Privacy Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Implementation locations: future `apps/dashboard/*`, dashboard setup/auth/overview/events API integration, secret detector and classifier tests.
- Prerequisites: dashboard scaffold, setup/auth API, metadata-only summary/events API, session auth guard.
- Remaining implementation: setup/login flow, overview cards/trend charts, events list/filter/detail, GitHub/AWS/JWT/PEM/DB URI/.env/entropy detection, internal-strategy context classifier.
- PR completion criterion: dashboard works metadata-only, overview shows event/user/period statistics, and event detail does not show raw prompt, full masked prompt, raw detected value, or original filename.
- Test method: `cd apps/dashboard && npm test`, `cd apps/api && pytest tests/detectors tests/dashboard tests/privacy`.

### 김민지

Implementation scope: invite/signup/user management API, event metadata DB/service, rule pack, ambiguous scoring, custom filter dry-run, dashboard management UI.

- Related WBS rows: 24, 25, 26, 32, 33, 43, 47, 51, 81, 82, 83, 84, 85, 86, 87, 88.
- Sections to read: `6. Auth, Session, And Permission Contract`, `9. Data Model And Raw-Data Prohibition Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`, `12. Dashboard Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Implementation locations: future `apps/api/*` auth/admin/event/custom-filter/rule-pack modules, `apps/dashboard/*` users/invites/policy/custom filter/status screens.
- Prerequisites: PostgreSQL migration, setup/bootstrap, dashboard session auth, event metadata table.
- Remaining implementation: invite/registration/user role/status API, event metadata persistence service, rule pack structure, ambiguous handling, custom filter dry-run, user stats table/charts, users/invites/policy/custom filter/status UI.
- PR completion criterion: every dashboard/API response is metadata-only, and invite/user/custom-filter/status flows pass permission, CSRF, and privacy regression tests.
- Test method: `cd apps/api && pytest tests/auth tests/events tests/custom_filters tests/privacy`, `cd apps/dashboard && npm test`.

### 유지수

Implementation scope: Python API foundation, Docker/PostgreSQL, migration, auth/RBAC, CORS/rate limit, PII/localized detectors, server-side masking, Analyze orchestrator, user stats API.

- Related WBS rows: 27, 34, 35, 36, 37, 38, 45, 48, 55, 56, 80.
- Sections to read: `3. Server, Runtime, And Infrastructure Contract`, `4. Health And Status Contract`, `5. HTTP Error Contract`, `6. Auth, Session, And Permission Contract`, `7. API Boundary And Detailed Contract`, `9. Data Model And Raw-Data Prohibition Contract`, `10. Detection, Masking, Scoring, And Custom Filter Contract`.
- Implementation locations: future `apps/api/*`, `infra/compose.yaml`, `.env.example`, Alembic migration, detector/masking/orchestrator modules.
- Prerequisites: repository scaffold, API dependency setup, PostgreSQL connection, settings loader, migration baseline.
- Remaining implementation: FastAPI scaffold, `/livez`, `/readyz`, `/healthz`, auth/setup/RBAC, CORS/rate limit, PII/localized detectors, masking, Analyze orchestrator, user stats API.
- PR completion criterion: the default Compose without Redis starts API/PostgreSQL, and health/status/auth/detector/masking/analyze/user stats tests pass.
- Test method: `cd apps/api && pytest`, Docker smoke followed by `/livez`, `/readyz`, `/healthz`, setup/login/analyze/dashboard summary smoke.

### 전체

Implementation scope: custom regex safety, risk scoring, privacy/security tests, E2E, performance, corpus, release/docs, final demo.

- Related WBS rows: 50, 54, 89-102.
- Sections to read: `13. Security And Privacy Contract`, `15. Tests, Done Definition, And Release Gates`, `16. WBS Document-Order Work Table`.
- Remaining implementation: custom regex ReDoS defense, scoring policy, dashboard raw-source non-exposure tests, DB/log/error privacy scan, external LLM call prohibition verification, API/dashboard/extension integration and performance tests, Korean FP/FN corpus, README/install/admin/privacy/contributing docs, release artifact, final smoke/demo.
- PR completion criterion: API, dashboard, extension build/test, privacy regression, no external LLM verification, Docker fresh-install smoke, and setup -> user -> extension -> analyze -> dashboard demo all pass.
- Test method: each area test command, privacy regression, Docker smoke, final demo scenario.
