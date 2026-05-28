# PromptGuard June 2 MVP Reallocated Plan

Date: 2026-05-28

Source:

- `C:/Users/dbdlw/OneDrive/바탕 화면/promptguard_dev_docs_v_0_9_team_integrated.reallocated.ko.md`
- `C:/Users/dbdlw/OneDrive/바탕 화면/promptguard_dev_docs_v_0_9_team_integrated.en.reallocated.md`
- Current working branch: `codex/server-auth-bootstrap`

Goal:

- 2026-06-02까지 유지수 담당 서버/Auth, 탐지/마스킹/분석통합, 필터 DB, 최소 대시보드 관리 기능을 실제로 시연 가능한 MVP로 만든다.
- 이미 구현한 foundation은 최대한 살리되, v0.9 문서에서 확정된 흐름과 맞지 않는 부분은 조정한다.

## 1. v0.9에서 바뀐 핵심 결정

이전 계획과 비교해서 반드시 반영해야 하는 변경점이다.

1. 기본 관리자 생성 방식 변경
   - 이전 구현: `/setup/status`, `/setup/bootstrap`로 첫 ADMIN 생성.
   - 프로젝트 적용 기준: fresh DB seed/migration이 기본 계정 `admin`을 만들고, 초기 비밀번호는 `PROMPTGUARD_INITIAL_ADMIN_PASSWORD` 설정값을 사용한다.
   - `/setup/status`, `/setup/bootstrap`은 v0.9 MVP 필수 흐름이 아니다.

2. 로그인 식별자 변경
   - 이전 구현: `login_id=ADMIN`.
   - v0.9/WBS 기준: 사용자 계정은 `email`, `username`, `department`, `role`, `status`, `password_hash`, `last_event_at` 중심.
   - MVP 로그인은 `username` 기반으로 맞추고, 기본 계정은 `username=admin`으로 둔다.

3. Redis 기본 필수 제외
   - 이전 구현: compose 기본 서비스에 Redis 포함, API가 Redis에 의존.
   - v0.9 기준: Redis는 optional profile이다.
   - 로그인 유지, refresh token, 중복 요청의 영속 기준은 PostgreSQL이다.

4. Health endpoint 확장
   - 이전 구현: `/healthz`만 있음.
   - v0.9 기준: `/livez`, `/readyz`, `/healthz`, `/status/server`가 필요하다.
   - readiness에는 DB, migration, config, 기본 policy 상태가 포함되어야 한다.

5. 대시보드 요구 추가
   - `apps/dashboard` 아래 Vanilla TypeScript SPA가 필요하다.
   - ADMIN 전용 metadata UI여야 하며 원문 prompt, 원문 탐지값, full `masked_prompt`는 표시하지 않는다.

## 2. 현재까지 이미 한 것

다음 항목은 foundation으로 이미 구현되어 있으므로 처음부터 다시 만들 필요가 없다.

| 영역 | 현재 상태 | 남은 조정 |
| --- | --- | --- |
| FastAPI API scaffold | `apps/api` 생성, FastAPI 실행 가능 | v0.9 endpoint/response 계약 보강 |
| PostgreSQL compose | PostgreSQL service 구성 완료 | Redis를 optional profile로 내리고 dashboard service 추가 |
| Alembic skeleton | Alembic env와 migration 2개 작성 | v0.9 스키마 기준 migration 추가 |
| password hash | Argon2id hash/verify 유틸과 테스트 있음 | 기본 admin seed password도 hash-only로 검증 |
| users table | `users` 존재, role/status/password_hash 있음 | `username`, `department`, `last_event_at` 반영, `login_id` 정리 |
| refresh_tokens table | token hash, expiry, revocation, rotation 일부 있음 | reuse detection과 token family 폐기 강화 |
| login/refresh/me/logout | bearer auth 기본 흐름 구현 | username 기반, disabled 처리 테스트, raw token 미저장 테스트 추가 |
| change password | `/auth/change-password` 구현 | 기본 admin 비밀번호 변경 운영 흐름으로 유지 |
| health | `/healthz` DB/Redis check 구현 | `/livez`, `/readyz`, migration/config readiness 추가 |
| CI | backend migration/test job 추가 | detector/analyze/dashboard smoke까지 확장 |

## 3. 했지만 수정해야 하는 것

이 항목들은 "완료"가 아니라 "재사용 가능한 초안"으로 본다.

1. `/setup/status`, `/setup/bootstrap`
   - v0.9 MVP에서는 제외된다.
   - 지금 코드는 남겨도 되지만 MVP 경로에서는 쓰지 않는다.
   - 최종적으로는 제거하거나 dev-only로 낮추는 것이 좋다.

2. 기본 관리자 계정
   - 현재 테스트 계정: `ADMIN / Admin1234!ChangeMe`.
   - 프로젝트 적용 기준 계정: `admin / PROMPTGUARD_INITIAL_ADMIN_PASSWORD`.
   - 초기 비밀번호 평문은 DB, 로그, 오류 응답, audit metadata, 대시보드, 테스트 snapshot에 저장하지 않고 migration 실행 중 hash로만 저장한다.

3. 계정 식별자
   - 현재 모델은 `login_id`, `login_id_normalized`를 사용한다.
   - v0.9 WBS는 `username`을 요구한다.
   - 다음 migration에서 `username`, `username_normalized`, `department`, `last_event_at`를 추가하고 auth API 응답도 맞춘다.

4. Redis 의존성
   - 현재 `/healthz`와 compose가 Redis를 기본 필수처럼 다룬다.
   - Redis disabled 상태를 정상으로 표현할 수 있어야 한다.

5. refresh token 보호
   - raw token은 저장하지 않는다.
   - rotation은 구현되어 있다.
   - reuse detection은 아직 약하다. 폐기된 refresh token이 다시 들어오면 같은 token family를 모두 폐기하는 처리가 필요하다.

## 4. 2026-06-02 MVP에서 제외하거나 후순위로 미룰 것

6월 2일 MVP를 끝내기 위해 아래는 후순위로 둔다.

- open signup, invite signup, workspace-code signup.
- hard delete. 사용자는 `DISABLED` 처리만 한다.
- Redis 필수 구성.
- React/Vue/Next dashboard.
- 외부 LLM 호출.
- 원문 prompt, 원문 파일 내용, 원문 탐지값, full `masked_prompt` 저장/표시.
- 고급 차트 p95, 30일 heatmap 등은 최소 API/화면이 된 뒤 확장한다.

## 5. 남은 구현 범위

### 5.1 서버/Auth

필수 구현:

- `users` table v0.9 정렬
  - `email`
  - `username`
  - `department`
  - `role`
  - `status`
  - `password_hash`
  - `last_event_at`
- `refresh_tokens` table 보강
  - `token_hash`
  - `expires_at`
  - `revoked_at`
  - `replaced_by_token_id`
  - `family_id` 또는 동등한 reuse detection 기준
- 기본 ADMIN seed
  - username: `admin`
  - password: `PROMPTGUARD_INITIAL_ADMIN_PASSWORD` 설정값
  - role: `ADMIN`
  - password는 Argon2id hash-only
- auth API
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `GET /auth/me`
  - `POST /auth/logout`
  - `POST /auth/change-password`
- RBAC dependency/middleware
  - `require_active_user`
  - `require_admin`
  - USER가 ADMIN route 호출 시 `403`
  - cross-workspace resource는 존재 숨김 `404`
- CORS/rate limit
  - 명시 origin만 허용
  - credential wildcard 금지
  - `/auth/login`, `/auth/refresh`, `/prompts/analyze` 기본 rate limit

### 5.2 실행환경과 상태점검

필수 구현:

- Compose 기본: API + PostgreSQL.
- Redis는 profile로 선택 실행.
- Dashboard service 추가.
- `.env.example` 정리.
- endpoint:
  - `GET /livez`
  - `GET /readyz`
  - `GET /healthz`
  - `GET /status/server`
- readiness check:
  - DB 연결
  - migration 최신 여부
  - 필수 config 유효성
  - 기본 policy/filter load 가능 여부
  - Redis disabled 상태 표현

### 5.3 분석/탐지/마스킹

필수 구현:

- EMAIL detector.
- PHONE detector.
- RRN detector with dummy checksum validation.
- Card detector with Luhn validation.
- API key / DB URL secret detector 최소 버전.
- 반복값 일관 placeholder masking.
- raw value 미저장 테스트.
- full `masked_prompt` 미저장 테스트.

### 5.4 Filter Rule DB

필수 구현:

- `filter_rules`
  - `source`
  - `kind`
  - `category`
  - `enabled`
  - `severity`
  - `action`
  - `editable_fields`
  - `config_json`
  - `version`
  - `archived_at`
- `filter_rule_versions`
  - rule 변경 이력 metadata.
- built-in detector 내부 parser/checksum/regex는 DB에 저장하지 않는다.
- custom keyword/regex/context_rule만 config에 저장한다.

### 5.5 Analyze API 통합

필수 구현:

- `POST /prompts/analyze`
- 흐름:
  - request validation
  - auth context
  - detector 실행
  - filter_rule 실행
  - score/action 결정
  - masking
  - event metadata 저장
  - safe response 반환
- 저장 금지:
  - raw prompt
  - raw file content
  - original detected value
  - full `masked_prompt`
  - secret/token
  - stack trace

### 5.6 대시보드/Admin UI

필수 구현:

- `apps/dashboard` Vanilla TypeScript SPA scaffold.
- ADMIN login/session 또는 임시 bearer 기반 admin guard.
- Users 관리 화면
  - 목록
  - 추가
  - role/status 변경
  - 비활성화
  - hard delete 제외
- 서버 상태 화면
  - API
  - PostgreSQL
  - migration
  - last checked
  - version metadata
- Filter Rule 관리 화면
  - 목록
  - built-in 수정 제한
  - custom keyword/regex/context_rule form
  - dry-run panel
- 사용자 통계 API/화면
  - user_id
  - display_name 또는 username
  - department
  - last_event
  - event_count
  - blocked/masked/warned aggregate

## 6. 구현 순서

### Phase 0. 기준 맞추기

목표: 지금 코드와 v0.9 문서의 차이를 먼저 정리한다.

작업:

1. 현재 branch/PR 상태 확인.
2. 이 문서를 기준으로 issue/PR 단위를 나눈다.
3. 기존 `server-auth-bootstrap` PR에는 "auth foundation"까지만 담고, v0.9 정렬은 후속 PR로 분리한다.

완료 기준:

- 기존 foundation PR과 새 MVP 보정 PR의 역할이 분리되어 있다.

### Phase 1. Auth schema 보정

목표: 6월 2일 작업의 기반 DB를 먼저 고정한다.

작업:

1. Alembic migration 추가.
2. `users`에 `username`, `username_normalized`, `department`, `last_event_at` 추가.
3. 기본 admin seed를 `admin / PROMPTGUARD_INITIAL_ADMIN_PASSWORD` hash-only로 생성.
4. `refresh_tokens`에 reuse detection 기준 추가.
5. 모델과 auth route를 username 중심으로 변경.
6. password/plaintext 미저장 테스트 추가.

완료 기준:

- fresh DB에서 `alembic upgrade head` 후 `admin`과 설정한 초기 비밀번호로 로그인 가능.
- DB에 초기 비밀번호 plaintext가 저장되지 않음.
- disabled user 로그인 실패.
- refresh token raw가 저장되지 않음.

### Phase 2. Runtime/Health 정리

목표: Docker와 상태점검이 v0.9 계약을 만족하게 만든다.

작업:

1. Compose 기본을 API + PostgreSQL로 조정.
2. Redis를 optional profile로 이동.
3. dashboard service skeleton 추가.
4. `/livez`, `/readyz`, `/healthz`, `/status/server` 구현.
5. migration current check 추가.

완료 기준:

- Redis 없이 `docker compose up --build` 성공.
- `/readyz`가 DB/migration/config 상태를 반영.
- `/healthz`가 Redis disabled를 정상적으로 표현.

### Phase 3. RBAC와 보안 기본값

목표: ADMIN/USER 경계와 API 보호를 만든다.

작업:

1. `require_active_user`, `require_admin` dependency 구현.
2. admin route skeleton 생성.
3. USER가 admin route 호출하면 `403`.
4. cross-workspace 숨김 helper는 interface부터 만든다.
5. CORS 설정 검증.
6. auth/analyze rate limit 기본 구현.

완료 기준:

- ADMIN-only route에 USER 접근 시 `403`.
- credential wildcard CORS가 불가능.
- login/analyze rate limit 테스트가 있다.

### Phase 4. Filter Rule DB와 Detector

목표: Analyze pipeline이 쓸 규칙과 탐지기를 준비한다.

작업:

1. `filter_rules`, `filter_rule_versions` migration.
2. built-in rule seed.
3. EMAIL/PHONE detector.
4. RRN/card detector.
5. API key/DB URL detector 최소 구현.
6. detector unit/corpus test.

완료 기준:

- 유효한 값만 탐지하고 무효 checksum/Luhn 값은 제외.
- raw detected value를 DB/log에 저장하지 않음.

### Phase 5. Masking과 Analyze 통합

목표: extension이 실제 self-host API를 호출할 수 있는 최소 분석 서버를 만든다.

작업:

1. placeholder masking 구현.
2. repeated value는 같은 placeholder로 치환.
3. score/action 결정 최소 정책 구현.
4. event metadata table/service 구현.
5. `POST /prompts/analyze` 통합.
6. raw prompt/full masked_prompt 미저장 테스트.

완료 기준:

- detector -> filter_rule -> score -> mask -> metadata event -> safe response 흐름 통과.
- DB/log/error/dashboard에 원문이 남지 않는다.

### Phase 6. Dashboard MVP

목표: ADMIN이 최소 운영을 할 수 있는 화면을 만든다.

작업:

1. `apps/dashboard` scaffold.
2. login/session 연결.
3. Users 관리 화면.
4. Server status 화면.
5. Filter Rule 관리 화면.
6. User stats API와 table/chart 최소 구현.

완료 기준:

- ADMIN만 dashboard API 접근 가능.
- USER는 dashboard/users/filters/events/status 접근 시 `403`.
- 화면에는 원문 prompt, 원문 탐지값, full masked_prompt가 표시되지 않는다.

### Phase 7. 통합 검증

목표: 6월 2일 시연 가능한 상태를 만든다.

작업:

1. fresh install smoke.
2. restart smoke.
3. migration smoke.
4. auth smoke.
5. analyze smoke.
6. dashboard smoke.
7. privacy regression.

완료 기준:

- Docker fresh install에서 API/PostgreSQL/dashboard 실행.
- admin 로그인 후 비밀번호 변경 가능.
- USER 생성 후 analyze 호출 가능.
- dashboard에서 users/status/filter/stats 확인 가능.
- 민감 원문 저장/표시 금지 테스트 통과.

## 7. 추천 PR 분리

한 번에 크게 올리지 말고 아래 순서로 쪼갠다.

1. `docs: add June 2 MVP reallocation plan`
   - 이 문서만 포함.

2. `feat(api): align auth schema with v0.9`
   - users/refresh_tokens migration.
   - default admin seed.
   - username login.
   - password/token tests.

3. `feat(api): add health readiness and compose profiles`
   - Redis optional profile.
   - `/livez`, `/readyz`, `/healthz`, `/status/server`.
   - compose smoke.

4. `feat(api): add rbac and security defaults`
   - ADMIN/USER dependencies.
   - CORS/rate limit.
   - admin route skeleton/tests.

5. `feat(api): add filter rule schema and pii detectors`
   - filter_rules migrations.
   - EMAIL/PHONE/RRN/card detectors.
   - tests.

6. `feat(api): integrate analyze masking pipeline`
   - masking.
   - event metadata.
   - analyze response.
   - privacy regression.

7. `feat(dashboard): add admin MVP screens`
   - users.
   - status.
   - filter rules.
   - user stats.

## 8. 가장 먼저 할 일

지금 바로 다음 작업은 Phase 1이다.

우선순위:

1. 새 migration으로 계정 DB를 v0.9에 맞춘다.
2. 기본 ADMIN seed를 `admin / PROMPTGUARD_INITIAL_ADMIN_PASSWORD`로 바꾼다.
3. 로그인 API를 `username` 기준으로 맞춘다.
4. 기존 테스트에 admin seed, plaintext 미저장, disabled user, refresh raw 미저장 테스트를 추가한다.

이유:

- 모든 admin API, dashboard, analyze auth가 사용자 context에 의존한다.
- DB 스키마가 흔들리면 뒤의 detector/event/dashboard 구현이 계속 다시 바뀐다.
- 6월 2일 MVP의 가장 큰 위험은 기능 수가 아니라 auth/schema 기준이 늦게 바뀌는 것이다.

## 9. 체크리스트

### Auth/DB

- [ ] `users.username` 추가.
- [ ] `users.department` 추가.
- [ ] `users.last_event_at` 추가.
- [ ] default admin seed `admin / PROMPTGUARD_INITIAL_ADMIN_PASSWORD` hash-only.
- [ ] `/auth/login` username 기반.
- [ ] disabled user 차단.
- [ ] refresh token raw 미저장 테스트.
- [ ] refresh reuse detection.

### Runtime/Health

- [ ] Redis optional profile.
- [ ] dashboard service skeleton.
- [ ] `/livez`.
- [ ] `/readyz`.
- [ ] `/healthz` v0.9 response shape.
- [ ] `/status/server` ADMIN-only.

### Security

- [ ] `require_admin`.
- [ ] USER admin route `403`.
- [ ] cross-workspace `404` helper.
- [ ] explicit CORS origins.
- [ ] credential wildcard 금지.
- [ ] auth/analyze rate limit.

### Detection/Analyze

- [ ] EMAIL detector.
- [ ] PHONE detector.
- [ ] RRN checksum detector.
- [ ] Card Luhn detector.
- [ ] API key/DB URL detector.
- [ ] masking placeholders.
- [ ] Analyze orchestrator.
- [ ] raw/full masked prompt 미저장.

### Filter/Dashboard

- [ ] `filter_rules`.
- [ ] `filter_rule_versions`.
- [ ] Users management UI.
- [ ] User stats API.
- [ ] Server status dashboard.
- [ ] Filter Rule management UI.
