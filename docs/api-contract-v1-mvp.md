# PromptGuard v1 MVP API Contract and Privacy Rules

Status: frozen for v1 MVP implementation planning.

This document fixes the v1 MVP API surface before implementation. It is based on the current `origin/main` code shape and the 1.0.0 product document, but it is not a description of the current implementation. Existing routes such as `/admin/users`, `/events`, `/stats/users`, `/stats/events`, and `/status/server` must be aligned to the `/dashboard/*` contract during later implementation work.

## Current Project Shape

Existing reference documents live under `docs/references/`, including:

- `promptguard_dev_docs_1_0_0.md`
- `promptguard_dev_docs_v_0_12_team_integrated.ko.md`
- `promptguard_input_capture_attachment_model_2026-05-30.ko.md`

Current API entry points are under `apps/api/app/routes/`:

- Analyze: `apps/api/app/routes/analyze.py`
- Admin users: `apps/api/app/routes/admin_users.py`
- Events: `apps/api/app/routes/events.py`
- Stats: `apps/api/app/routes/stats.py`
- Status: `apps/api/app/routes/status.py`
- Auth/session-adjacent current implementation: `apps/api/app/routes/auth.py`
- Health: `apps/api/app/routes/health.py`

Current dashboard files are under `apps/dashboard/`:

- Overview/admin scaffold: `apps/dashboard/admin.html`, `apps/dashboard/src/admin.ts`, `apps/dashboard/static/admin.js`
- Events: `apps/dashboard/events.html`, `apps/dashboard/event-detail.html`, `apps/dashboard/src/events.ts`, `apps/dashboard/src/event-detail.ts`
- Users: `apps/dashboard/users.html`, `apps/dashboard/src/users.ts`
- Shared static assets: `apps/dashboard/src/styles/main.css`, `apps/dashboard/static/main.css`

Current extension analyze client and input capture code is under `apps/extension/src/`:

- Analyze client: `apps/extension/src/background/promptAnalyzeClient.ts`
- Authenticated API client: `apps/extension/src/background/authenticatedApiClient.ts`
- Prompt/file capture: `apps/extension/src/content/*`
- Shared request/response types: `apps/extension/src/shared/types.ts`

## API Boundary

All dashboard APIs require ADMIN dashboard authorization when implemented. This MVP contract does not implement or freeze a dashboard session API. Session APIs are explicitly excluded from this MVP contract and must not be added as part of the first API-contract implementation pass.

### Analyze API

Endpoint:

- `POST /prompts/analyze`

Purpose: decide one protected send attempt. The request does not use top-level `prompt`, `file`, or `attachments`. All submitted user material and attachment metadata must be represented through `inputs[]`.

Required top-level request fields:

- `inputs`
- `context`
- `filter_config_revision`
- `client_request_id`

`inputs[]` item fields:

| Field | Required | Description |
| --- | --- | --- |
| `input_id` | yes | Client-generated stable ID unique within the request. |
| `kind` | yes | Input category such as `text`, `attachment_metadata`, or `unsupported_attachment`. |
| `source` | yes | Origin of the input, such as `composer`, `paste`, `file`, `attachment`, or `service_attachment`. |
| `content_included` | yes | Whether `content` is present in this request. |
| `content` | conditional | Text content only when the extension is allowed and able to include it. Omit or set null when unavailable. |
| `size_bytes` | yes | Byte size of the captured content or source object when known. |
| `metadata` | yes | Safe metadata only. Must not contain original file names, raw secrets, tokens, or input body text duplicates. |

The old `type` plus `content_scanned` centered request contract is not used. `content_scanned` is a response or event metadata fact derived by the server, not a client request field.

Example request shape:

```json
{
  "client_request_id": "7d7d6ee8-8d6b-4ab6-ae71-9c78c4ef34fb",
  "filter_config_revision": "cfg_2026_05_31_001",
  "context": {
    "ai_service": "chatgpt",
    "ai_service_domain": "chatgpt.com",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "1.0.0",
    "browser": "chrome",
    "locale": "ko-KR"
  },
  "inputs": [
    {
      "input_id": "composer-1",
      "kind": "text",
      "source": "composer",
      "content_included": true,
      "content": "Text to analyze",
      "size_bytes": 15,
      "metadata": {}
    }
  ]
}
```

Response fields:

| Field | Description |
| --- | --- |
| `risk_score` | Integer risk score for the whole send attempt. |
| `risk_level` | `low`, `medium`, `high`, or `critical`. |
| `action` | Final send decision: `ALLOW`, `WARN`, `MASK`, or `BLOCK`. |
| `allow_original_send` | Whether the original unmodified composer content may be sent. |
| `requires_user_confirmation` | Whether the extension must show confirmation before sending. |
| `detections[]` | Safe grouped detection metadata. Must not include detected raw values. |
| `input_results[]` | Per-input processing result in the same order as request `inputs[]`. |
| `content_unavailable_inputs[]` | Inputs that could not be content-scanned and were handled as metadata-only or unavailable. |

`input_results[]` items include `input_id`, `input_index`, `kind`, `source`, `content_included`, `content_scanned`, `decision_basis`, and optional `content_unavailable_reason` or `limit_exceeded`.

`content_unavailable_inputs[]` items include `input_id`, `input_index`, `kind`, `source`, `reason`, and optional `limit_exceeded`.

`masked_prompt` may be returned only when `action` requires replacing composer text. It must not be persisted and must not be returned by dashboard APIs.

### Dashboard Users API

Endpoint:

- `GET /dashboard/users`

The v1 MVP dashboard user API is `/dashboard/users`, not `/admin/users`.

User fields:

- `login_id`
- `username`
- `department`
- `role`
- `status`

Per-user event aggregate fields:

- `event_count`
- `blocked_count`
- `masked_count`
- `warned_count`
- `last_event_at`

Allowed response fields:

- The user fields and aggregate fields listed above.
- Optional pagination metadata if needed.

Forbidden response fields:

- Internal DB IDs.
- Password hashes or password metadata.
- Email if not explicitly needed by the MVP UI.
- Raw prompt, raw file text, detected raw values, original file names, or full masked prompts.

### Dashboard Events API

Endpoints:

- `GET /dashboard/events`
- `GET /dashboard/events/{event_id}`

List response may return:

- `event_id`: public event identifier, not the internal DB primary key if those differ.
- `created_at`
- Safe user summary: `login_id`, `username`, `department`
- `service`
- `action`
- `risk_score`
- `risk_level`
- `detection_category`
- `detection_type`
- `detection_count`
- `detail_available`

Detail response may return:

- All list-safe fields.
- `platform`
- `service_domain`
- `detection_summary[]`
- `detections[]` with `category`, `type`, `source`, `severity`, `confidence`, `count`, `reason_code`, `match_count`, and safe evidence such as value lengths or counts only.
- `input_results[]` metadata without input body text.
- `content_unavailable_inputs[]`.
- Safe request context metadata such as browser, locale, extension version, and page origin.

Events responses must not return:

- Internal DB identifiers.
- Input body original text.
- File content original text.
- Detected raw values.
- Full `masked_prompt`.
- Original file names.
- Secrets, tokens, stack traces, DB URLs, or detailed env values.
- Prompt hashes or fingerprints that allow correlation outside the product unless explicitly approved for the final v1 privacy design.

### Dashboard Overview API

Endpoint:

- `GET /dashboard/overview`

Purpose: provide dashboard summary cards and trend metadata.

The older `/stats/users` and `/stats/events` responsibilities are absorbed as follows:

- User list plus per-user aggregates move to `GET /dashboard/users`.
- Event totals, action distributions, risk distributions, detector summaries, active user counts, and daily buckets move to `GET /dashboard/overview`.

Overview response may return:

- `event_count`
- `active_user_count`
- `blocked_count`
- `masked_count`
- `warned_count`
- `allowed_count`
- `action_distribution`
- `risk_level_distribution`
- `detection_type_distribution`
- `detection_category_distribution`
- `daily_buckets[]`
- `last_event_at`

Overview response must be aggregate-only and must not include raw event input, detected raw values, original file names, full masked prompts, internal DB IDs, secrets, tokens, stack traces, DB URLs, or detailed env values.

### Dashboard Filters API

Endpoints:

- `GET /dashboard/filters`
- `GET /dashboard/filters/{filter_id}`
- `POST /dashboard/filters`
- `PATCH /dashboard/filters/{filter_id}`
- `POST /dashboard/filters/{filter_id}/enable`
- `POST /dashboard/filters/{filter_id}/disable`
- `DELETE /dashboard/filters/{filter_id}`
- `POST /dashboard/filters/dry-run`

MVP uses a single `filter_rules` model. `filter_rule_versions` is excluded from MVP.

Core `filter_rules` fields:

- `filter_id`: public rule identifier.
- `origin`: `built_in`, `custom`, or `business_context`.
- `kind`: detector/rule kind, such as `pii`, `secret`, `keyword`, `regex`, or `context`.
- `editable_fields`: list of fields the current rule allows admins to change.
- `config_json`: safe rule config. Must not include raw detected values or secrets.
- `enabled`
- `severity`
- `action`
- `created_at`
- `updated_at`

Built-in detectors are editable only for:

- `enabled`
- `severity`
- `action`

Custom keyword, regex, and business-context rules may edit only the fields declared in `editable_fields`. Server-side validation must reject changes outside that list.

`POST /dashboard/filters/dry-run` returns match counts and safe metadata only. It must not echo raw test input, detected raw values, full masked prompts, secrets, tokens, or stack traces.

### Dashboard Status API

Endpoint:

- `GET /dashboard/status`

Displayed status items:

- API status
- PostgreSQL status
- Migration status
- Filter Rules status
- Last Checked

Allowed response fields:

- Overall status: `healthy`, `degraded`, or `unhealthy`.
- Component status for `api`, `postgres`, `migrations`, and `filter_rules`.
- Short safe component messages.
- `last_checked` timestamp.

Forbidden response fields:

- DB URL.
- Secret or token values.
- Stack traces.
- Detailed env values.
- Raw exception text that may expose infrastructure details.

## Privacy Rules

### Must Not Return

No API response, dashboard payload, validation error, or status payload may return:

- Internal DB identifiers.
- Input body original text.
- File content original text.
- Detected raw value.
- Full `masked_prompt`.
- Original file name.
- DB URL.
- Secret.
- Token.
- Stack trace.
- Detailed env value.

### Must Not Store

The API, database, logs, and event metadata must not store:

- Raw prompt.
- Raw file text.
- Detected raw value.
- Full masked prompt.
- Original file name.

Allowed storage is metadata-only: counts, categories, detector type, severity, action, safe context labels, safe domains, byte sizes, unavailable reasons, timestamps, and non-reversible aggregate statistics.

## MVP Exclusions

The following are excluded from v1 MVP:

- Session API.
- HMAC input fingerprint.
- PDF, Office, OCR, archive, and image content scan.
- Filter Rule history/version.
- `filter_rule_versions`.
- Redis-based distributed processing.
- SSO/SIEM.
- Full privacy regression automation.

## MVP Implementation Order

1. chore: start v1 mvp branch from origin/main
2. docs: freeze v1 mvp api contract and privacy rules
3. chore(db): align v1 mvp schema and migrations
4. feat(api): replace analyze contract with v1 inputs bundle
5. feat(api): add analyze idempotency and safe event metadata
6. feat(extension): send unified analyze inputs bundle
7. feat(api): add dashboard users API with aggregates
8. feat(api): align dashboard events and overview APIs
9. feat(api): add unified filter rules API
10. feat(api): align dashboard status API
11. feat(dashboard): add shared API client and auth helper
12. feat(dashboard): wire login, overview, events, event-detail, users pages
13. feat(dashboard): wire filters and status pages
14. test: add fresh install, integration, privacy smoke checks
15. docs: sync install, admin, privacy, release docs
