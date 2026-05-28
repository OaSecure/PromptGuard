# PromptGuard 서버·보안 구현 계획

작성일: 2026-05-23  
대상 문서:

- `docs/references/PromptGuard_Chrome_Extension_Analyze_Integration_Dev_Reference_v0_4.md`
- `promptguard_dev_docs_v_0_3_open_source.md`

## 1. 현재 프로젝트 상태 요약

현재 저장소는 Chrome Extension MVP가 중심이다. `apps/extension`에는 Manifest V3, TypeScript, content script, service worker, options page, mock API, prompt/file preflight, privacy regression test가 구현되어 있다. 2026-05-23 기준 extension wrapper check도 통과했다.

반면 v0.3 제품 문서가 요구하는 self-hosted OSS 제품 구조는 아직 비어 있다. 특히 `apps/api`, `apps/dashboard`, `infra`, `packages`, Docker Compose, PostgreSQL/Redis, migration, auth/RBAC, Analyze API, event logging, dashboard API가 아직 구현되어 있지 않다.

따라서 사용자가 맡은 서버·보안 작업은 extension 이후의 핵심 기반 작업이며, 단순 기능 추가가 아니라 PromptGuard를 실제 self-hosted 제품으로 만드는 1차 백엔드 골격에 해당한다.

## 2. 문서 간 기준 정리

v0.3 문서는 전체 제품 PRD/SRS/WBS다. Docker Compose, setup wizard, auth, RBAC, Analyze API, detector, masking, event logging, dashboard까지 MVP 전체 범위를 정의한다.

v0.4 문서는 현재 구현된 Chrome Extension과 Analyze 연동 계약을 더 구체화한 문서다. DOM preflight, `/prompts/analyze`, `/files/analyze`, `/config/extension`, runtime validation, fail-closed, 원문 미저장 원칙, mock API 흐름을 고정한다.

두 문서를 합치면 서버 구현 기준은 다음으로 정리된다.

- 서버는 extension이 이미 기대하는 API 계약을 제공해야 한다.
- raw prompt, file content, detected raw value, masked prompt, full URL, original filename은 DB/log/diagnostic에 저장하면 안 된다.
- MVP detector는 외부 LLM이 아니라 rule-based evidence scoring으로 구현한다.
- self-host 기본 실행 단위는 API, dashboard, PostgreSQL, Redis, reverse proxy 문서/예시다.
- 관리자/일반회원, 초대/가입 설정, refresh token hash, ADMIN/USER middleware가 P0다.
- Dashboard는 원문 없는 metadata 통계와 사용자별 위험 분포를 제공해야 한다.

## 3. 사용자가 적은 작업의 성격

| 영역 | 작업 | 성격 | 우선순위 |
|---|---|---|---|
| 실행환경 | Docker Compose 실행 구성 | 제품 부팅 기반 | P0 |
| 구성결정 | Self-host 서버 구성 결정안 | 아키텍처 결정 문서 | P0 |
| 상태점검 | `/healthz` endpoint | 운영/compose smoke 기준 | P0 |
| 마이그레이션 | DB migration 실행 골격 | 모든 DB 작업의 선행조건 | P0 |
| 계정DB | users, invites, registration_settings | Auth/RBAC 기반 | P0 |
| 비밀번호 | password hash 저장 | 보안 필수 | P0 |
| 로그인 | login, refresh, auth/me API | extension/dashboard 연결 필수 | P0 |
| 토큰보호 | refresh token hash/expiry/revoke | 세션 보안 필수 | P0 |
| 권한 | ADMIN/USER middleware | dashboard/admin API 보호 | P0 |
| 보안설정 | CORS/rate limit | public self-host 방어 기본값 | P0 |
| 개인정보 | EMAIL/PHONE/RRN/card detector | Analyze 핵심 detector | P0 |
| 직접필터 | custom filter schema/version | P1 또는 P0 후반 |
| 마스킹 | placeholder replacement | Analyze action 구현 핵심 | P0 |
| 분석통합 | detector -> score -> mask -> log -> response | 서버 MVP의 중심 | P0 |
| 사용자통계 | user event stats API | dashboard P0/P1 경계, 사용자 요청상 P0 취급 |

## 4. 현재 부족한 것

### 4.1 저장소/실행 구조

- `apps/api`가 없다.
- `apps/dashboard`가 없다.
- `infra/docker-compose.yml` 또는 루트 `compose.yml`이 없다.
- `.env.example`과 env validation이 없다.
- API, dashboard, Postgres, Redis의 local networking 규약이 없다.
- reverse proxy는 구현보다 먼저 운영 문서와 권장 구성이 필요하다.

### 4.2 서버 API

- `/healthz`가 없다.
- `/setup/status`, `/setup/bootstrap`이 없다.
- `/auth/login`, `/auth/refresh`, `/auth/me`가 없다.
- `/config/extension`이 없다.
- `/prompts/analyze`와 `/files/analyze` real server가 없다.
- admin/user API와 RBAC boundary가 없다.

### 4.3 DB와 마이그레이션

- migration runner가 없다.
- users, invites, registration_settings 테이블이 없다.
- refresh_tokens 테이블이 없다.
- custom_filter_rules, custom_filter_rule_versions 테이블이 없다.
- event/audit/statistics용 metadata-only schema가 없다.
- fresh install과 restart migration idempotency 검증이 없다.

### 4.4 보안/프라이버시

- password hash 정책이 없다.
- refresh token 원문 미저장 검증이 없다.
- CORS allowlist와 rate limit 정책이 없다.
- raw prompt/log redaction guard가 서버에 없다.
- event logging에서 원문 필드가 DB schema에 들어가지 않도록 막는 테스트가 없다.

### 4.5 Analyze pipeline

- PII detector가 없다.
- secret detector가 없다. 사용자가 적은 작업에는 없지만 v0.3 P0라서 반드시 추가되어야 한다.
- DB URL/API key detector가 없다.
- RRN checksum, card Luhn 검증이 없다.
- risk scoring formula와 threshold/action 결정 로직이 없다.
- masking span merge/overlap 처리와 반복값 전체 치환이 없다.
- detector -> scoring -> masking -> event log -> response orchestration이 없다.

### 4.6 Dashboard/API

- 사용자별 이벤트 통계 API가 없다.
- overview/events/users/invites API가 없다.
- dashboard UI가 없다.
- 원문 미표시 UI regression이 없다.

## 5. 구현 순서 제안

### Phase 0. 결정과 골격 고정

목표: 서버 스택과 repo structure를 고정하고 이후 작업 충돌을 줄인다.

1. API 서버 기술 결정
   - 권장: FastAPI 또는 NestJS 중 하나로 고정.
   - detector/문자열 처리와 Python 생태계를 우선하면 FastAPI.
   - extension과 타입 공유, monorepo TS 일관성을 우선하면 NestJS.
   - 결정 문서는 `docs/references`에 남긴다.
2. repo structure 결정
   - `apps/api`
   - `apps/dashboard`
   - `apps/extension`
   - `packages/shared`
   - `infra`
   - `docs`
3. API contract 초안 작성
   - `/healthz`
   - `/auth/login`
   - `/auth/refresh`
   - `/auth/me`
   - `/config/extension`
   - `/prompts/analyze`
   - `/files/analyze`
   - `/dashboard/users/:id/stats`

완료 기준:

- self-host 구성 결정안 문서 존재.
- API scaffold 생성 가능.
- extension이 기대하는 response shape와 서버 contract가 충돌하지 않음.

### Phase 1. 실행환경과 운영 smoke

목표: fresh clone에서 서버가 켜지고 상태를 확인할 수 있게 한다.

1. Docker Compose 작성
   - API
   - Dashboard
   - PostgreSQL
   - Redis
   - 개발용 network/volume
2. `.env.example` 작성
   - DB URL
   - Redis URL
   - JWT secret
   - refresh token secret 또는 pepper
   - CORS origins
   - dashboard URL
   - API public URL
3. `/healthz` 구현
   - API process status
   - DB ping
   - Redis ping
   - migration status 또는 DB schema version
4. Compose smoke test
   - `docker compose up`
   - `/healthz` 200
   - dependency degraded 상태 표현

완료 기준:

- `docker compose up` 후 API가 뜬다.
- `/healthz`가 dependency 상태를 JSON으로 반환한다.
- DB/Redis 장애 시 status가 명확하다.

### Phase 2. DB migration 골격

목표: 모든 DB 기능의 안전한 변경 기반을 만든다.

1. migration 도구 선택
   - FastAPI면 Alembic 권장.
   - NestJS면 Prisma migration 또는 Drizzle migration 권장.
2. migration runner 설정
3. schema version 확인 방식 추가
4. fresh install migration 테스트
5. restart/re-run migration 테스트

완료 기준:

- 빈 DB에서 migration 성공.
- 같은 migration을 재실행해도 안전.
- compose restart 후 API가 같은 schema를 인식.

### Phase 3. 계정, 가입, Auth/RBAC

목표: extension/dashboard가 real auth를 사용할 수 있게 한다.

1. 계정 DB migration
   - `users`
   - `invites`
   - `registration_settings`
   - `refresh_tokens`
2. password hash 저장
   - Argon2id 권장.
   - bcrypt는 호환 fallback으로 가능.
   - DB에는 hash, algorithm, params/version만 저장.
3. auth API
   - `POST /auth/login`
   - `POST /auth/refresh`
   - `GET /auth/me`
   - logout/revoke endpoint는 refresh token 폐기 검증에 필요.
4. refresh token 보호
   - 원문 저장 금지.
   - hash 저장.
   - 만료, rotation, revoke, reuse detection 정책 작성.
5. ADMIN/USER middleware
   - ADMIN API에 USER 접근 시 403.
   - 인증 없음은 401.
6. 가입 설정
   - `INVITE_ONLY` 기본.
   - `WORKSPACE_CODE`, `OPEN_SIGNUP`은 명시 설정.
   - OPEN_SIGNUP은 기본 비활성.

완료 기준:

- 평문 비밀번호 DB 미저장 테스트 통과.
- refresh token 원문 DB 미저장 테스트 통과.
- login/refresh/me API 통과.
- USER가 admin API 접근 시 403.

### Phase 4. 서버 보안 기본값

목표: public self-host 노출을 전제로 기본 방어선을 둔다.

1. CORS 정책
   - dashboard origin allowlist.
   - extension request origin/headers 정책 정리.
   - 개발/운영 분리.
2. rate limit
   - `/auth/*`는 강하게 제한.
   - `/prompts/analyze`, `/files/analyze`는 사용자/IP/workspace 기준 제한.
   - Redis 기반 sliding window 또는 token bucket.
3. request size limit
   - prompt max length.
   - file text max size.
4. logging redaction
   - request body logging 금지.
   - 민감 key redaction.
   - raw prompt seeded test.

완료 기준:

- 허용되지 않은 origin 차단.
- auth brute force rate limit 테스트 통과.
- analyze flood rate limit 테스트 통과.
- log에 raw_prompt seed가 남지 않음.

### Phase 5. Detector와 masking TDD

목표: Analyze API를 만들기 전에 detector 단위를 신뢰 가능하게 만든다.

1. EMAIL detector
   - 일반 이메일.
   - false positive 회피.
2. PHONE detector
   - 한국 휴대폰/지역번호/하이픈/공백 변형.
   - 숫자열 오탐 방지.
3. RRN detector
   - 주민등록번호 후보 추출.
   - checksum 유효한 dummy만 탐지.
   - 실제 개인정보 테스트 데이터 금지.
4. Card detector
   - 카드번호 후보 추출.
   - Luhn 유효 번호만 탐지.
5. Secret detector 추가 필요
   - GitHub token.
   - AWS access key.
   - JWT.
   - private key block.
   - DB URL.
6. masking engine
   - span merge.
   - overlap 처리.
   - 반복값 전체 치환.
   - placeholder 예: `[EMAIL_1]`, `[PHONE_1]`, `[RRN_1]`, `[CARD_1]`, `[API_KEY_1]`, `[DB_URL_1]`.

완료 기준:

- detector별 unit test 통과.
- RRN checksum 유효/무효 dummy 테스트 통과.
- card Luhn 유효/무효 테스트 통과.
- PII/API_KEY/DB URL 반복값이 전체 치환됨.
- detection raw value는 result 외부 저장 경로에 남지 않음.

### Phase 6. Analyze API 전체 흐름

목표: extension mock API를 real self-host API로 대체한다.

1. `/config/extension`
   - selector config.
   - policy version.
   - timeout.
   - file policy.
2. `/prompts/analyze`
   - auth required.
   - schema validation.
   - idempotency/client request id 처리.
   - detector 실행.
   - risk scoring.
   - action 결정.
   - masking.
   - metadata-only event logging.
   - response 반환.
3. `/files/analyze`
   - v0.4 extension이 이미 호출하므로 contract는 맞춰야 한다.
   - MVP 서버 범위에서 텍스트 파일만 처리.
   - 파일명 원문 저장 금지.
4. scoring
   - secret/DB URL은 기본 Block 또는 high risk.
   - EMAIL/PHONE 단독은 Mask 우선.
   - RRN/card는 Block 또는 Mask+high warning 정책 결정 필요.
5. event logging
   - user_id, workspace_id, event_id.
   - action, risk_score, detection types/counts.
   - policy_version, origin only.
   - prompt_hash는 HMAC이면 가능하나 raw prompt 저장 금지.

완료 기준:

- extension real mode에서 `/prompts/analyze` 호출 성공.
- Allow/Warn/Mask/Block response shape가 extension validator를 통과.
- raw prompt, masked prompt, detection raw value가 event DB에 저장되지 않음.
- API error/timeout은 extension fail-closed 정책과 충돌하지 않음.

### Phase 7. Custom filter

목표: 조직별 rule을 versioning 가능한 형태로 저장한다.

권장 위치: P1 또는 P0 후반. 이유는 기본 detector, scoring, masking, event logging이 먼저 있어야 custom rule이 붙어도 흔들리지 않는다.

1. `custom_filter_rules`
   - id, workspace_id, name, type, pattern, severity, action, placeholder, enabled.
2. `custom_filter_rule_versions`
   - rule_id, version, previous snapshot, changed_by, changed_at.
3. regex validation
   - syntax.
   - max length.
   - timeout/ReDoS 방어.
4. dry-run API
   - 샘플 원문 저장 금지.
5. analyze pipeline 통합
   - custom detector evidence 생성.
   - event에는 rule id/version/type만 저장.

완료 기준:

- migration 통과.
- custom filter CRUD와 versioning 기본 테스트 통과.
- dry-run 샘플 원문 미저장 테스트 통과.

### Phase 8. 사용자 통계 API

목표: dashboard가 원문 없이 사용자별 위험 분포를 보여줄 수 있게 한다.

1. event schema 확정
2. aggregation query 작성
   - 사용자별 이벤트 수.
   - detection type 분포.
   - action 분포.
   - risk bucket 분포.
   - 기간별 trend.
3. ADMIN-only stats API
4. USER 본인 통계 API는 후속 선택 가능.

완료 기준:

- ADMIN이 사용자별 유형/횟수/action 분포 조회 가능.
- USER가 다른 사용자 통계 접근 시 403.
- response에 raw prompt나 detection raw value가 없음.

## 6. 추천 구현 순서 한 줄 버전

1. Self-host 구성 결정안
2. `apps/api` scaffold
3. Docker Compose + `.env.example`
4. `/healthz`
5. migration runner
6. users/invites/registration_settings/refresh_tokens migration
7. password hash
8. login/refresh/me
9. refresh token hash/expiry/revoke
10. ADMIN/USER middleware
11. CORS/rate limit/log redaction
12. detector TDD: EMAIL/PHONE/RRN/card
13. secret/DB URL detector 추가
14. masking engine
15. event schema/logging
16. `/config/extension`
17. `/prompts/analyze` orchestration
18. `/files/analyze` contract alignment
19. custom filter schema/versioning
20. user stats API
21. dashboard API/UI
22. install/admin/privacy docs

## 7. 사용자가 적은 작업별 선행관계

| 작업 | 반드시 먼저 필요한 것 | 뒤에 이어질 것 |
|---|---|---|
| Docker Compose 실행 구성 | 서버 기술 결정, repo structure | healthz, migration, install guide |
| Self-host 서버 구성 결정안 | v0.3/v0.4 기준 정리 | compose/API scaffold |
| `/healthz` | API scaffold, DB/Redis config | compose smoke, ops docs |
| DB migration 골격 | DB 선택, migration tool | 계정/이벤트/custom filter schema |
| users/invites/registration_settings | migration 골격 | signup/auth/RBAC |
| password hash | users table | login/register |
| login/refresh/me | users, refresh_tokens, hash | extension real auth, dashboard guard |
| refresh token 보호 | refresh_tokens table | logout/revoke, session security |
| ADMIN/USER middleware | auth/me, role field | admin APIs, stats API |
| CORS/rate limit | API scaffold, Redis | public self-host hardening |
| EMAIL/PHONE detector | detector interface | masking/scoring |
| RRN checksum | detector interface | high-risk scoring |
| Card Luhn | detector interface | high-risk scoring |
| custom filter tables | migration, auth/RBAC | custom filter CRUD/dry-run |
| placeholder masking | detector spans | Analyze response |
| Analyze 통합 | detector, scoring, masking, event logging | extension real integration |
| user stats API | event schema/logging, RBAC | dashboard charts |

## 8. 빠진 일감으로 추가해야 할 것

사용자 목록에는 없지만 MVP 문서 기준으로 반드시 추가해야 하는 작업이다.

| 추가 작업 | 이유 | 권장 우선순위 |
|---|---|---|
| `apps/api` scaffold | 모든 서버 작업의 시작점 | P0 |
| `.env.example`과 env validation | Docker Compose와 운영 안정성 | P0 |
| setup status/bootstrap | 첫 관리자와 setup lock이 MVP P0 | P0 |
| `/config/extension` | extension real mode 연결 필수 | P0 |
| secret detector | v0.3 P0, 개발자 유출 방지 핵심 | P0 |
| DB URL detector | 사용자의 masking 요구에도 포함 | P0 |
| risk scoring engine | action 결정의 중심 | P0 |
| event schema/logging | 사용자 통계 API의 선행조건 | P0 |
| RedactedLogger/privacy regression | 원문 미저장 신뢰성 확보 | P0 |
| dashboard scaffold | 사용자 통계 API 소비 화면 | P0/P1 |
| install/admin/privacy docs | OSS self-host 제품 완성 기준 | P0 |

## 9. 주요 결정 필요 사항

| 결정 | 권장안 | 이유 |
|---|---|---|
| API stack | FastAPI 또는 NestJS 중 즉시 결정 | migration/auth/detector 구조가 달라짐 |
| DB | PostgreSQL only | v0.3 기준과 Docker Compose 운영성 |
| Redis | rate limit/session auxiliary 사용 | auth/analyze abuse 방어 |
| 기본 가입 방식 | INVITE_ONLY | public self-host 안전 기본값 |
| password hash | Argon2id 우선 | password storage modern default |
| refresh token | opaque token + server-side hash 저장 | JWT refresh 원문 저장 위험 감소 |
| timeout 정책 | critical fail-closed | extension v0.4 기본과 일치 |
| masked_prompt 저장 | 저장 금지 | privacy-by-design |
| custom filter | P1 또는 P0 후반 | 기본 detector와 event schema 이후 안정적 |

## 10. 1차 마일스톤 제안

### M1. 서버가 켜진다

- `apps/api` scaffold
- compose로 API/Postgres/Redis 실행
- `/healthz`
- `.env.example`

### M2. 로그인할 수 있다

- migration runner
- users/invites/registration_settings/refresh_tokens
- password hash
- login/refresh/me
- ADMIN/USER middleware

### M3. 안전하게 호출할 수 있다

- CORS
- rate limit
- request size limit
- logging redaction
- privacy regression seed test

### M4. 분석할 수 있다

- EMAIL/PHONE/RRN/card detector
- secret/DB URL detector
- masking engine
- scoring
- `/prompts/analyze`
- `/config/extension`

### M5. 기록하고 볼 수 있다

- metadata-only event logging
- user stats API
- dashboard summary/events/users API
- 원문 미표시 검증

### M6. 조직별 정책을 붙인다

- custom filter schema/versioning
- CRUD/dry-run
- analyze pipeline integration

## 11. 권장 첫 작업 5개

1. `docs/references`에 self-host 서버 구성 결정안을 작성한다.
2. `apps/api` scaffold와 `/healthz`만 먼저 만든다.
3. `compose.yml`과 `.env.example`로 API/Postgres/Redis를 띄운다.
4. migration runner를 붙이고 users/invites/registration_settings/refresh_tokens 첫 migration을 만든다.
5. password hash, login/refresh/me, ADMIN/USER middleware를 TDD로 구현한다.

이 순서가 좋은 이유는 이후 detector, analyze, dashboard가 모두 인증 사용자와 DB, 운영 smoke 위에 올라가기 때문이다. detector부터 만들면 재미는 있지만, extension real mode와 dashboard까지 이어지는 제품 골격이 늦어진다.
