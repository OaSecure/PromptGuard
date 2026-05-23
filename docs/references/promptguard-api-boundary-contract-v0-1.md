# PromptGuard API Boundary Contract v0.1

## Purpose

This document fixes the API boundary that the PromptGuard MVP should implement next. It is the handoff contract for API, extension, dashboard, shared contract package, and AI coding agents.

The key decision is simple: the Chrome Extension captures user intent before send, but the self-host API owns policy judgment. The extension may run mock responses for smoke testing. The real product decision comes from the server-side Analyze pipeline.

## Source Authority

This contract reconciles these current sources:

| Source | What It Fixes |
| --- | --- |
| `docs/references/promptguard_dev_docs_v_0_3_open_source.md` | Full product MVP: setup, auth, extension connection, Analyze API, detector pipeline, masking, event logging, dashboard, security tests. |
| `docs/references/PromptGuard_Chrome_Extension_Analyze_Integration_Dev_Reference_v0_4.md` | Extension-to-Analyze integration: runtime messages, `/config/extension`, `/prompts/analyze`, `/files/analyze`, error UX, extension/server ownership split. |
| `docs/references/promptguard-mvp-wbs-ai-workplan-2026-05-23.md` | Team work split and implementation order: root workspace, `packages/contracts`, API foundation, Analyze privacy base, detector/scoring/masking, dashboard. |
| Current repo code | Implemented Chrome Extension client boundary, mock Analyze behavior, local shared types, options page, DOM preflight, prompt/file decision UX, and tests. |

When these sources conflict:

1. Product MVP scope comes from the v0.3 product document.
2. Extension runtime shape comes from the v0.4 integration document.
3. Current repo state decides what is already implemented.
4. WBS decides team ownership and sequencing.
5. This document records the reconciled working contract until `packages/contracts` or OpenAPI supersedes it.

## Ownership Boundary

| Area | Owner | Responsibility |
| --- | --- | --- |
| Prompt capture | Chrome Extension content script | Find supported input, intercept send, extract prompt text transiently, send request to background worker. |
| File capture | Chrome Extension content script | Apply local file policy before reading, read supported text files in memory only, send transient text to background worker. |
| API URL/token/config | Chrome Extension background worker and options page | Store operational settings, call `/auth/me`, call `/config/extension`, cache selector/policy config. |
| Analyze decision | Self-host API | Validate request, run detectors, score risk, choose Allow/Warn/Mask/Block, generate `masked_prompt`, create event metadata. |
| Masking | Self-host API | Produce `masked_prompt` from server-side detections. The extension applies the returned value and does not invent real policy masking. |
| Event logging | Self-host API | Store metadata-only events and detection summaries without raw prompt, file content, masked prompt, or raw detected values. |
| Dashboard | Dashboard/API | Read metadata-only summaries, events, users, filters, health, and policy data. Never display raw prompt or masked full prompt. |
| Shared schema | Future `packages/contracts` | Hold request, response, error, config, and event schemas used by extension, API, and dashboard. |

The extension is not the source of truth for real detection or policy decisions. It owns pre-send control and UX. The API owns judgment and server-side audit boundaries.

## Endpoint Contract

### `GET /auth/me`

Purpose: verify that the configured API URL and token identify an active user in a workspace.

Expected response fields:

| Field | Requirement |
| --- | --- |
| `id` | User id. |
| `workspace_id` | Workspace id from the authenticated token, not from request body. |
| `email` | User email. |
| `role` | `USER` or `ADMIN`. |
| `status` | `ACTIVE` or `DISABLED`. |
| `department` | Optional department object from the v0.3 product spec. |
| `policy_version` | Current policy version for extension request alignment. |

Extension completion for this endpoint means Test connection can call it through the background worker and render a safe status. Server completion means token validation, workspace scoping, disabled-user handling, and safe error responses exist.

### `GET /config/extension`

Purpose: send the extension its supported domains, selector config, timeout, policy version, and file policy.

Required response groups:

| Group | Requirement |
| --- | --- |
| `api_base_url` | Canonical API base URL. |
| `policy_version` | Current policy version. |
| `timeout_ms` | Positive finite timeout. |
| `ai_service_configs` | Service, domains, input selectors, send button selectors, and v0.4 file selectors. |
| `file_upload` | v0.4 text-file policy: enabled flag, max sizes/count, allowed extensions, excluded extensions. |

Remote selector config is preferred over hardcoded fallback selectors. Fallback selectors exist only to keep the extension usable when config is missing or stale.

### `POST /prompts/analyze`

Purpose: analyze the prompt before the original prompt is sent to a supported AI page.

Request:

| Field | Owner | Requirement |
| --- | --- | --- |
| `prompt.text` | Extension | Raw prompt text, transient request input only. |
| `prompt.input_method` | Extension | `CLICK`, `ENTER`, or `UNKNOWN`. |
| `prompt.content_length` | Extension/API | Must match or safely bound `prompt.text.length`. |
| `context.ai_service` | Extension | `CHATGPT` for MVP. |
| `context.ai_service_domain` | Extension | Domain host such as `chatgpt.com`. |
| `context.page_url_origin` | Extension | Origin only; no full path/query. |
| `context.extension_version` | Extension | Extension version. |
| `context.browser` | Extension | `Chrome`. |
| `context.locale` | Extension | Browser/user locale. |
| `policy.version` | Extension/API | Extension's known policy version. |
| `client_request_id` | Extension | Random/idempotency id that contains no raw prompt, file content, or filename. |

Forbidden request fields:

- `user_id`
- `workspace_id`
- raw prompt embedded in ids, logs, filenames, headers, or error objects

Response:

| Field | Owner | Requirement |
| --- | --- | --- |
| `event_id` | API | Metadata-only event id. |
| `request_id` | API | Request correlation id. |
| `decision.risk_score` | API | 0-100 risk score. |
| `decision.risk_level` | API | `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`. |
| `decision.action` | API | `Allow`, `Warn`, `Mask`, or `Block`. |
| `decision.user_message` | API/Extension | Schema-compatible safe message. Extension UI should render fixed safe copy rather than arbitrary server text. |
| `decision.requires_justification` | API | Optional v0.3 field for feedback/justification flows. |
| `decision.allow_original_send` | API | Explicitly authorizes original send for Allow/Warn. |
| `detections[]` | API | Summary only: type, label, count, severity, confidence, source. No raw values. |
| `masked_prompt` | API | Present when action is `Mask`; must not contain original sensitive values. |
| `policy.version` | API | Policy evaluated. |
| `policy.latest_version` | API | Latest known server policy. |
| `partial_result` | API | True when analysis is degraded or incomplete. |

Forbidden response fields:

- raw prompt echo
- raw detected values
- full masked prompt in persisted event APIs
- server internals, stack traces, or raw thrown messages

### `POST /files/analyze`

Purpose: v0.4 text-file preflight path. This is a supported extension boundary, but prompt Analyze remains the first server MVP priority.

Request:

| Field | Requirement |
| --- | --- |
| `files[].client_file_id` | Opaque per-attempt id. |
| `files[].name_hash` | Optional. Current extension does not require stable file fingerprinting. |
| `files[].extension` | Extension suffix, not full original filename. |
| `files[].mime_type` | Browser file MIME. |
| `files[].size_bytes` | File size. |
| `files[].content_text` | Supported text file content, transient request input only. |
| `context`, `policy`, `client_request_id` | Same principles as prompt Analyze. |

Response:

| Field | Requirement |
| --- | --- |
| `event_id`, `request_id`, `decision`, `policy`, `partial_result` | Same principles as prompt Analyze. |
| `file_results[]` | Per-file metadata keyed by `client_file_id`; no original filename or raw content. |
| `file_results[].detections[]` | Summary only; no raw values. |

File Analyze is not a reason to delay prompt Analyze foundation. It should share the same privacy, error, idempotency, and event logging rules when implemented.

## Privacy Contract

Raw prompt and raw file content may exist only in these transient places:

1. Page DOM before capture.
2. Content script memory while building a request.
3. Runtime message payload to background worker.
4. Background worker memory while calling mock or real API.
5. API request handler memory while analyzing.

Raw prompt and raw file content must not be written to:

- `chrome.storage`
- console logs
- thrown error text
- test snapshots
- request ids
- event tables
- detection tables
- dashboard APIs
- dashboard UI
- memory/session logs
- third-party telemetry

`masked_prompt` is also sensitive. It can be returned to the extension for immediate user action, but should not be stored or displayed later as a dashboard artifact.

Event storage is metadata-only:

| Store | Allowed |
| --- | --- |
| analysis events | event id, user/workspace ids from auth context, AI service, origin, risk score, risk level, action, policy version, prompt hash, timestamps. |
| detection summaries | detection type, label, count, severity, confidence, source, rule/filter ids, reason codes. |
| feedback | event id, safe reason category, justification metadata where required. |

## Error Contract

Error responses use the v0.3/v0.4 common shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request body is invalid.",
    "details": [
      { "field": "prompt.text", "reason": "required" }
    ],
    "request_id": "req_abc123"
  }
}
```

Minimum error codes for MVP alignment:

| Situation | HTTP/code | Boundary Rule |
| --- | --- | --- |
| Missing/expired token | `401` / `UNAUTHORIZED` | Extension asks user to reconnect. |
| Invalid request body | `400` / `VALIDATION_ERROR` | No raw prompt in details. |
| Oversized prompt/file | `413` / `PAYLOAD_TOO_LARGE` | Fail closed with safe message. |
| Policy mismatch | `409` or `428` / `POLICY_MISMATCH` | Include latest policy version; extension should resync config. |
| Duplicate client request | `200` replay or `409` / `DUPLICATE_REQUEST` | No duplicate event creation. |
| Too many requests | `429` / `RATE_LIMITED` | Fail closed or retry only within explicit policy. |
| Timeout | client-side `TIMEOUT` | Extension holds send and shows safe timeout copy. |
| Server error | `500` / `SERVER_ERROR` | No stack trace or raw input. |
| Network failure | client-side `NETWORK_ERROR` | Extension holds send and shows connection failure copy. |

The current extension-local `NormalizedError` shape should be aligned with this table when the real API server work starts.

## Analyze Pipeline Contract

The real server-owned prompt pipeline is:

```text
request validation
  -> normalize
  -> regex detector
  -> secret detector
  -> custom filter detector
  -> rule context classifier
  -> overlap merge
  -> risk scoring
  -> masking
  -> metadata-only event logging
  -> response
```

MVP context classification is deterministic rule logic. External LLM API calls are outside the MVP. A future local LLM classifier must have a separate runtime, logging, and privacy design before adoption.

## Implementation Order

The next implementation should proceed in this order:

1. Root workspace and `packages/contracts`
   - Create one schema/type source for extension, API, and dashboard.
   - Start by matching the current extension types and the v0.3/v0.4 API examples.
   - Include request, response, config, auth, error, detection summary, event metadata, and file Analyze schemas.

2. API scaffold
   - Add `/healthz`, common error handler, request id, auth header parsing, body size limits, redaction logger, and OpenAPI/schema CI path.

3. Minimum extension connection endpoints
   - Implement `GET /auth/me`.
   - Implement `GET /config/extension`.
   - Implement enough of `POST /prompts/analyze` to validate schema and return safe contract-shaped responses.

4. Analyze privacy base
   - Block raw request body logging.
   - Add redaction hook.
   - Add `client_request_id` idempotency.
   - Add workspace-separated HMAC `prompt_hash`.
   - Add privacy regression tests for DB/log/API/dashboard boundaries.

5. Real detector/scoring/masking
   - Add regex, secret, context, custom filter, overlap merge, risk scoring, and masking.
   - Server must generate `masked_prompt`; extension must only apply it.

6. Metadata event logging and dashboard APIs
   - Store and query metadata-only events.
   - Build dashboard summary/events/users/status from metadata only.

7. Extension real API smoke
   - Validate extension against real self-host API.
   - Keep mock mode for local smoke tests but label it as mock-only.

## Done / Not Done

| Claim | Status Meaning |
| --- | --- |
| Extension API client exists | Extension can call the shape; real server is not implemented. |
| Mock Analyze returns Mask | Smoke testing can prove UX wiring; real detection/masking is not implemented. |
| `/prompts/analyze` contract skeleton exists | Request/response schema and safe error shape exist; full pipeline is not done. |
| Analyze API is done | Auth, validation, idempotency, HMAC hash, detectors, scoring, masking, metadata event logging, and privacy tests all pass. |
| Mask panel is done | Extension can show and apply server-supplied `masked_prompt`; server masking engine may still be missing. |
| Dashboard event detail is done | Admin can inspect metadata-only event details without raw prompt, masked prompt, or raw detection values. |
| Custom filter is done | CRUD, validation, dry-run, pipeline integration, event metadata, stats, and UI all work. |

## AI Implementation Instructions

When giving this document to an AI coding agent, use this instruction:

```text
Read `docs/references/promptguard-api-boundary-contract-v0-1.md` first.
Do not infer API ownership from extension mock code.
The extension owns pre-send capture and UX. The API owns real decision, masking, event metadata, idempotency, hash, and privacy controls.
Implement the smallest next WBS slice without expanding MVP scope.
If you change request/response shape, update the shared contract document and all affected extension/API/dashboard tests in the same change.
Never store or log raw prompt, raw file content, masked_prompt, original filename, or raw detected values.
```

## Open Follow-Up

The next code-bearing plan should create root workspace plus `packages/contracts`, then migrate extension-local shared types toward that package without breaking current extension tests.
