# v1 MVP Development Plan

## Document Basis

- 기준 문서: `docs/references/promptguard_dev_docs_1_0_2.md`
- 참고 문서: `docs/references/promptguard_dev_docs_1_0_0.md`
- 이 문서는 새 API 계약이나 새 MVP scope를 만드는 문서가 아니다.
- 이 문서는 1.0.2 개발 문서의 23.1 MVP WBS 상태를 기준으로, 남은 구현 작업을 실제 PR 단위로 실행하기 위한 개발 계획 문서다.
- 1.0.2 문서와 이 문서가 충돌하면 1.0.2 문서를 우선한다.

## Current Main Implementation Status Summary

1.0.2 문서는 현재 `main`의 구현 상태를 완료로 과장하지 않고, MVP 계약 대비 남은 작업을 `부분`, `교체 필요`, `미구현`으로 구분한다. 이 문서도 같은 기준을 따른다.

### 완료 또는 기본 구현됨

- Alembic 기반 migration 구조가 존재한다.
- 기본 auth/token 흐름의 일부가 있다.
- `users`, `refresh_tokens`, `analysis_events`, `event_detections`, `filter_rules` 계열의 일부 DB 구조가 있다.
- health/readiness 계열 endpoint 일부가 있다.
- dashboard static/prototype 화면과 일부 TypeScript build 구조가 있다.
- extension DOM hook, preflight, action UX, storage/test 구조의 일부가 있다.

### 부분 구현

- Auth API: bearer token 흐름은 일부 있으나, 1.0.2의 dashboard session cookie + CSRF 계약과 분리 완료가 아니다.
- DB migration/fresh install: Alembic과 일부 schema는 있으나 `dashboard_sessions`, `event_inputs`, idempotency, fresh DB smoke가 완료로 보기 어렵다.
- Dashboard pages: `events.html`, `users.html`, `filters.html` 등 일부 화면은 있으나 1.0.2의 `login.html`, `overview.html`, `status.html` 및 API-backed loading/empty/error flow가 완료되지 않았다.
- Dashboard common API client: 공통 session, CSRF, safe error, loading/empty helper가 완료되지 않았다.
- Extension action UX와 checks: 단독 구현/검증은 일부 있으나 서버 Analyze가 최종 `inputs[]` 계약이 아니어서 real API smoke가 미완성이다.
- Dashboard Status API: health/readiness 구현은 있으나 `/dashboard/status` 계약은 별도 정렬이 필요하다.
- API tests: 일부 테스트가 있으나 dashboard session, Analyze `inputs[]`, event input metadata, overview/status/users aggregate privacy case까지 MVP 계약 기준으로 완료되지 않았다.

### 교체 필요

- Analyze API: 현재 prompt/context 중심 흐름은 1.0.2의 `inputs[]` send attempt decision endpoint로 교체해야 한다.
- Extension Analyze request builder: top-level prompt/input/file/attachments 없이 `inputs[]` 하나로 요청하도록 교체해야 한다.
- Users API: `/admin/users` 또는 기존 통계 분리 흐름은 `/dashboard/users` 및 `login_id/username` 기준 aggregate 응답으로 교체해야 한다.
- Events API: 기존 이벤트 상세의 내부 식별자나 prompt hash 계열 표시 흐름은 `/dashboard/events` metadata-only 계약으로 교체해야 한다.
- Overview API: 기존 stats 성격은 `/dashboard/overview`와 `/dashboard/users` 책임으로 분리해야 한다.
- Filter Rule API: 기존 `/filters` 또는 `source/kind` 기준 흐름은 `/dashboard/filters`와 `origin/kind` 기준으로 교체해야 한다.
- Filter Rule schema: MVP에서 `filter_rule_versions`와 version history가 섞이지 않도록 현재 `filter_rules` 상태와 post-MVP 기능을 분리해야 한다.

### 미구현

- Dashboard Session API: `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me`.
- `dashboard_sessions` hash storage.
- Analyze idempotency: `(login_id, client_request_id)` 기준 중복 event 방지.
- Extension storage/privacy의 장기 저장 금지 검증.
- Basic privacy smoke.
- Final MVP smoke scenario.

### 검증 필요

- Fresh install에서 migration, 기본 ADMIN `admin / 1234`, health/readiness, dashboard login, analyze, dashboard metadata 확인까지 이어지는 smoke.
- API privacy smoke: DB, dashboard API, dashboard DOM, error response에 금지값이 남지 않는지 확인.
- Dashboard typecheck/build smoke.
- Extension real API smoke after server Analyze contract replacement.

## Remaining MVP Core Work

1.0.2 문서 기준 남은 핵심 작업은 다음이다.

- Dashboard Session API: MVP scope다. 임의로 제외하지 않는다.
- `inputs[]` 기반 Analyze API.
- Event input metadata와 event metadata-only persistence.
- `/dashboard/status`.
- `/dashboard/overview`.
- Users aggregate integration in `/dashboard/users`.
- Dashboard page rename and API-backed conversion.
- Basic/final smoke and privacy checks.

## Recommended PR Order

1. `docs: add v1 mvp development plan from 1.0.2 docs`
2. `feat(api): add dashboard session API`
3. `chore(db): align dashboard sessions and event input metadata schema`
4. `feat(api): replace analyze request with inputs bundle`
5. `feat(api): add analyze idempotency and event input metadata persistence`
6. `feat(api): align dashboard events API`
7. `feat(api): align dashboard overview and status APIs`
8. `feat(api): add users aggregate integration`
9. `feat(api): align unified dashboard filter rules API`
10. `feat(dashboard): add shared API client and session helper`
11. `feat(dashboard): convert pages to API-backed dashboard flow`
12. `feat(extension): send inputs bundle and align action UX`
13. `test: add MVP smoke and privacy checks`
14. `docs: sync README/admin/privacy/release notes`

이 순서는 1.0.2의 의존성을 따른다. Dashboard pages는 dashboard session과 API client가 필요하고, extension real smoke는 Analyze `inputs[]` 서버 계약이 먼저 필요하다.

## Work Details

### 1. Development Plan Docs

- 목표: 1.0.2 문서 기준으로 MVP 실행 순서를 고정한다.
- 관련 파일/영역: `docs/v1-mvp-development-plan.md`, `docs/references/promptguard_dev_docs_1_0_2.md`.
- 해야 할 일: 23.1 WBS의 현재 상태, 필요한 조치, 완료 기준을 PR 단위로 정리한다.
- 하지 말아야 할 일: 새 API 계약 작성, 구현 코드 수정, DB migration 작성.
- 완료 기준: 이 문서가 1.0.2 scope와 충돌하지 않고, Dashboard Session API를 MVP scope로 유지한다.
- 테스트/검증 방법: `git diff --check`, 기준 문서의 상태값과 대조.
- privacy 확인 항목: privacy 금지값 원칙을 축약하지 않는다.

### 2. Dashboard Session API

- 목표: 대시보드 ADMIN 전용 session cookie + CSRF 계약을 구현한다.
- 관련 파일/영역: `apps/api/app/routes/*`, auth/session service, `dashboard_sessions` model/migration, auth tests.
- 해야 할 일: `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me` 구현. ADMIN만 session 생성 가능하게 하고 USER는 `403` 처리. session id 원문은 저장하지 않고 hash와 metadata만 저장.
- 하지 말아야 할 일: dashboard bearer token 저장 방식 유지, session id localStorage 저장, extension bearer flow 변경.
- 완료 기준: ADMIN login/session/me/logout이 동작하고 USER credential로 dashboard session이 생성되지 않는다.
- 테스트/검증 방법: session route tests, CSRF tests, disabled user tests, cookie attributes check.
- privacy 확인 항목: session id 원문, token, password, password_hash, DB URL, stack trace를 응답/로그에 노출하지 않는다.

### 3. DB Schema For Sessions And Event Inputs

- 목표: 1.0.2 MVP 데이터 모델을 fresh DB 기준으로 정리한다.
- 관련 파일/영역: SQLAlchemy models, Alembic migrations, seed path, readiness/fresh DB smoke.
- 해야 할 일: `dashboard_sessions`, `event_inputs`, idempotency 저장 구조를 추가하고, `users`, `refresh_tokens`, `analysis_events`, `event_detections`, `filter_rules`를 1.0.2 기준으로 점검한다.
- 하지 말아야 할 일: 기존 closed PR #55를 그대로 되살려 최신 main과 충돌시키기, 원문 저장 컬럼 추가, Filter Rule history/version을 MVP 완료 범위에 섞기.
- 완료 기준: fresh DB에서 기본 ADMIN, users, refresh_tokens, dashboard_sessions, analysis_events, event_inputs, event_detections, filter_rules가 준비된다.
- 테스트/검증 방법: Alembic upgrade on fresh PostgreSQL, restart idempotency smoke, model import tests.
- privacy 확인 항목: raw prompt, file content, detected raw value, original filename, full masked prompt 저장 컬럼이 없다.

### 4. Analyze Inputs Bundle API

- 목표: `POST /prompts/analyze`를 `inputs[]` 기반 send attempt decision endpoint로 교체한다.
- 관련 파일/영역: `apps/api/app/routes/analyze.py`, detectors, masking, scoring, analyze tests.
- 해야 할 일: top-level `prompt`, `input`, `file`, `attachments` 없이 `inputs[]`만 받는다. `input_results[]`, `content_unavailable_inputs[]`, top-level `action` 하나를 반환한다.
- 하지 말아야 할 일: Extension request builder를 같은 PR에서 수정, HMAC input fingerprint 구현, PDF/Office/OCR/archive/image scan 구현.
- 완료 기준: `inputs[]` request schema, detector, scoring, masking, basic response contract tests가 통과한다.
- 테스트/검증 방법: `pytest apps/api/tests/test_analyze.py`, validation error privacy tests.
- privacy 확인 항목: raw prompt, raw file text, detected raw value, full masked prompt가 event/dashboard/error 응답에 남지 않는다. `masked_prompt`는 Mask 응답에서만 일시 반환한다.

### 5. Analyze Idempotency And Event Input Metadata

- 목표: `(login_id, client_request_id)` 기준 중복 event 생성을 방지하고, `inputs[]` item별 metadata를 저장한다.
- 관련 파일/영역: analyze service, event service, `event_inputs`, `analysis_events`, tests.
- 해야 할 일: duplicate request가 두 번째 event를 만들지 않게 하고, `input_results[]`, `content_unavailable_inputs[]`에 필요한 metadata를 저장한다.
- 하지 말아야 할 일: HMAC fingerprint 구현, 입력 본문 저장, full request/response body 저장.
- 완료 기준: 동일 `(login_id, client_request_id)` 재요청이 안전하게 처리되고, event detail이 metadata-only로 재구성된다.
- 테스트/검증 방법: duplicate request tests, DB row assertions, privacy fixture tests.
- privacy 확인 항목: 입력 본문, 파일 내용, 탐지값 원문, 원본 파일명, full masked prompt 저장 금지.

### 6. Dashboard Events API

- 목표: `/dashboard/events`, `/dashboard/events/{event_id}`를 metadata-only 계약으로 정렬한다.
- 관련 파일/영역: event routes, event schemas, event queries, tests.
- 해야 할 일: 목록/상세에서 detection summary, detections, input results, content unavailable inputs, safe context metadata를 반환한다.
- 하지 말아야 할 일: 입력 본문, 파일 내용, 전체 masked prompt, 원본 파일명, 내부 식별자 표시.
- 완료 기준: dashboard event list/detail이 1.0.2 metadata 계약을 따른다.
- 테스트/검증 방법: events API tests, RBAC/session tests, privacy response tests.
- privacy 확인 항목: prompt hash 계열 내부 식별자를 dashboard 표시/API 완료 기준에 섞지 않는다.

### 7. Dashboard Overview And Status APIs

- 목표: `/dashboard/overview`와 `/dashboard/status`를 1.0.2 dashboard session 기준으로 정렬한다.
- 관련 파일/영역: overview/status routes, health/readiness helpers, tests.
- 해야 할 일: overview는 30일 기본 aggregate와 action/period counts를 반환한다. status는 API/PostgreSQL/Migration/Filter Rules/Last Checked를 반환한다.
- 하지 말아야 할 일: DB URL, secret, stack trace, detailed env values 노출.
- 완료 기준: ADMIN session으로만 조회 가능하고, dashboard 화면이 필요한 metadata를 받을 수 있다.
- 테스트/검증 방법: status/overview route tests, degraded state tests, privacy tests.
- privacy 확인 항목: status/error 응답에 secret, token, DB URL, stack trace가 없다.

### 8. Users Aggregate Integration

- 목표: `/dashboard/users` 응답에 사용자별 event/action aggregate를 포함한다.
- 관련 파일/영역: users routes, user aggregate query, tests.
- 해야 할 일: `login_id`, `username`, `department`, `role`, `status`와 `event_count`, `blocked_count`, `masked_count`, `warned_count`, `last_event_at`를 반환한다.
- 하지 말아야 할 일: `/stats/users`를 dashboard UI 계약으로 유지, email 필수 path 유지, password/password_hash/token/session 정보 반환.
- 완료 기준: Users 화면은 별도 mock 없이 `/dashboard/users`만으로 렌더링 가능하다.
- 테스트/검증 방법: dashboard users API tests, aggregate tests, RBAC/session tests.
- privacy 확인 항목: password, password_hash, token, session, raw event data 반환 금지.

### 9. Unified Dashboard Filter Rules API

- 목표: `/dashboard/filters*` API를 `origin/kind/editable_fields/config_json` 기준으로 정렬한다.
- 관련 파일/영역: filter routes, filter schemas, filter service, dry-run, tests.
- 해야 할 일: built-in detector는 `enabled`, `severity`, `action`만 수정 가능하게 하고 custom keyword/regex/context rule과 dry-run을 구현한다.
- 하지 말아야 할 일: `filter_rule_versions` history를 MVP 필수 완료 범위로 구현, dry-run sample text 저장.
- 완료 기준: built-in/custom/context rule CRUD와 dry-run이 1.0.2 계약대로 동작한다.
- 테스트/검증 방법: filter API tests, dry-run validation tests, regex syntax/length tests.
- privacy 확인 항목: dry-run sample, detected raw value, secret, stack trace 저장/응답 금지.

### 10. Dashboard Shared Client And API-Backed Pages

- 목표: static dashboard pages를 ADMIN session 기반 API-backed flow로 전환한다.
- 관련 파일/영역: `apps/dashboard/`, shared API client, session helper, page TypeScript.
- 해야 할 일: `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`를 공통 API client, CSRF, loading/empty/error state로 연결한다.
- 하지 말아야 할 일: bearer token localStorage 저장, session id localStorage 저장, mock 데이터를 완료 기준으로 유지.
- 완료 기준: 주요 dashboard pages가 ADMIN session으로 열리고, API-backed metadata를 렌더링한다.
- 테스트/검증 방법: dashboard typecheck/build, local smoke, API error state smoke.
- privacy 확인 항목: dashboard DOM에 입력 본문, 파일 내용, full masked prompt, detected raw value, original filename을 표시하지 않는다.

### 11. Extension Inputs Bundle And Real API Smoke

- 목표: extension request builder와 action UX를 최종 server Analyze 계약에 맞춘다.
- 관련 파일/영역: `apps/extension/src/`, extension tests, real API smoke.
- 해야 할 일: composer text, converted paste, 작은 text file, attachment metadata, unsupported attachment를 `inputs[]`로 보낸다. server top-level `action`, `allow_original_send`, `requires_user_confirmation`, `masked_prompt`만 전송 제어에 사용한다.
- 하지 말아야 할 일: 서버 Analyze 계약 구현과 같은 PR에 섞기, 입력 본문 장기 저장.
- 완료 기준: Allow/Warn/Mask/Block real API smoke가 silent allow 없이 동작한다.
- 테스트/검증 방법: extension unit checks, `python apps/extension/tests/run_extension_checks.py all`, manual real-service smoke.
- privacy 확인 항목: extension storage에 composer 원문, paste 원문, file text, full masked prompt, detected raw value, original filename, full request/response body를 장기 저장하지 않는다.

### 12. MVP Smoke And Privacy Checks

- 목표: MVP 수용 기준과 최종 smoke를 실제 실행 가능한 체크로 만든다.
- 관련 파일/영역: API tests, dashboard smoke, extension checks, docs/checklists.
- 해야 할 일: fresh install, API, dashboard, extension, basic privacy smoke를 연결한다.
- 하지 말아야 할 일: full privacy regression을 MVP 완료 조건으로 과도하게 확장.
- 완료 기준: 1.0.2의 15.1과 15.5 smoke 흐름이 통과하거나, 수동 smoke 결과가 문서에 남는다.
- 테스트/검증 방법: Docker fresh-install smoke, API pytest, dashboard build, extension checks.
- privacy 확인 항목: DB, API response, dashboard DOM, error response에서 금지값 fixture가 보이지 않는다.

### 13. Docs Sync

- 목표: README, install, admin, privacy, release docs를 1.0.2 MVP 계약과 맞춘다.
- 관련 파일/영역: `README.md`, `docs/`, admin/privacy/release notes.
- 해야 할 일: `/dashboard/*`, `inputs[]`, `login_id`, Filter Rule `origin/kind`, Dashboard Session API, privacy 기준을 반영한다.
- 하지 말아야 할 일: 구현 전 완료로 단정, 1.0.2와 다른 MVP scope 작성.
- 완료 기준: 주요 문서가 1.0.2와 충돌하지 않는다.
- 테스트/검증 방법: docs diff review, link/path check.
- privacy 확인 항목: 운영 문서에 초기 `1234` 변경 안내와 원문 저장 금지 원칙을 명확히 둔다.

## Privacy / Security Basis

1.0.2 기준으로 모든 MVP 구현 PR은 아래 원칙을 지켜야 한다.

- `raw_prompt` 저장, 로그, 응답 금지.
- 파일 내용 또는 추출 텍스트 저장, 로그, 응답 금지.
- 탐지 원문값 저장, 로그, 응답 금지.
- 원본 파일명 저장, 로그, 응답 금지.
- full masked prompt 저장, 로그, 대시보드 노출 금지.
- token, secret, API key, DB URL, stack trace, detailed env value 노출 금지.
- refresh token 원문과 dashboard session id 원문 저장 금지.
- dashboard session id와 bearer token을 `localStorage`에 저장 금지.
- `masked_prompt`는 Mask 응답에서 composer text 적용을 위해 일시 반환할 수 있지만, event row나 dashboard API에 저장/노출하지 않는다.

## Pre-Development Checklist

다음 작업을 시작하기 전에 매번 확인한다.

- 최신 `origin/main` 기준으로 새 브랜치를 만든다.
- `docs/references/promptguard_dev_docs_1_0_2.md`가 존재하고 기준 문서로 사용되는지 확인한다.
- PR 하나에 docs/API/DB/dashboard/extension을 과도하게 섞지 않는다.
- 기존 main 구현 상태와 중복/충돌을 먼저 확인한다.
- generated/build/cache 파일을 커밋하지 않는다.
- Dashboard Session API를 MVP 제외로 취급하지 않는다.
- 1.0.2 문서의 `부분`, `교체 필요`, `미구현` 항목을 임의로 완료 처리하지 않는다.
- 새 API 계약을 별도 문서로 만들지 않고, 1.0.2 계약의 구현 계획만 작성한다.
