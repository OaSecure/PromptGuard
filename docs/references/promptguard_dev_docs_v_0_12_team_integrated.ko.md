# PromptGuard 개발 문서 세트 v0.12 - 팀 통합본

## 1. 문서 사용 규칙과 현재 구현 상태
- 서버 언어는 Python 3.13으로 고정한다.
- PostgreSQL은 그대로 쓴다.
- Redis는 MVP 기본 필수가 아니다. 로그인 유지, 갱신 토큰, 중복 요청 처리의 영속 기준은 PostgreSQL이 맡는다.
- 확장앱 mock/client가 있다고 해서 자가 호스팅 Analyze API가 구현된 것이 아니다.
- 원문 프롬프트, 원문 파일 내용, `masked_prompt`, 원문 탐지값, 원본 파일명, 비밀값/토큰, 스택 추적은 저장, 로그, 대시보드, 오류 응답, 메모리/세션 로그에 남기지 않는다.
- WBS의 담당자, 영역, 분류, 항목, 상세 내용은 유지하고 구현 가능한 작업 단위로 풀어쓴다.
- PromptGuard 개발 계약, 구현 상태, API 경계, 데이터 소유권, 작업 지시는 이 v0.12 문서 하나를 기준으로 한다.
- WBS 원본 XLSX/CSV는 범위, 순서, 담당자, 영역을 확인하는 별도 원본으로만 남긴다.
- v0.12는 v0.11 통합본의 기존 계약을 보존하면서, dashboard 구현 기준을 Vanilla TypeScript 소스/빌드 산출물 검증으로 명확히 하고 서버 런타임을 현재 Docker 기준인 Python 3.13으로 고정한다.
- 이 문서는 제품 개발 계약이다. 특정 에이전트 세션, PR 번호, 임시 작업 순서, 대화 참여자만 아는 내부 진행 기록을 계약 본문에 넣지 않는다.

### 1.1 현재 구현 상태 요약

- 확장앱의 ChatGPT 입력 탐지, 전송 보류, Allow/Warn/Mask/Block UX, selector fixture, double-submit guard는 주요 흐름이 구현되어 있다.
- 확장앱은 현재 mock/fake backend와 client fixture로 검증된 부분이 있으며, 실제 self-host API 서버와의 end-to-end smoke는 서버 구현 뒤 완료한다.
- `apps/api`에는 FastAPI app, `/auth/me`, `/config/extension`, `/prompts/analyze`, `/livez`, Pydantic 요청/응답 schema, 안전한 `application/problem+json` validation error, 안전 redaction helper, workspace-scoped HMAC `prompt_hash`, 계약정보 문맥 분류 helper, detection overlap merge helper와 pytest가 들어갔다.
- 현재 auth는 bearer header 경계와 dev metadata만 제공한다. 실제 auth/session 검증, PostgreSQL migration, idempotency/event metadata 저장, dashboard, Docker Compose 기본 실행, 관리자 auth, 대시보드 통계 API는 아직 구현 대상이다.
- WBS 작업표의 `됨`, `부분`, `안됨`은 현재 repo 기준 구현 상태를 뜻한다. `부분`은 client, fixture, 문서, 또는 일부 UI가 있지만 실제 서버/API/DB/통합 검증이 남은 상태다.
- 영어 번역본은 AI 작업 보조 문서이며, 한국어 원본의 구조와 내용이 확정된 뒤 같은 단원 구조로 맞춘다.

## 2. 확정 결정

- 서버 언어: Python 3.13.
  - 이유: 탐지기, 규칙 분류기, 마스킹, 개인정보 회귀 테스트, 향후 로컬 분석 확장에 Python 생태계가 유리하다.
- 데이터베이스: PostgreSQL.
  - 이유: 사용자, 필터 규칙, 이벤트 메타데이터, 중복 요청 처리, 토큰 해시, 규칙 버전은 영속 트랜잭션과 마이그레이션이 필요하다.
- 초기 접근 흐름: 기본 ADMIN seed + login-first.
  - 서버 최초 초기화 시 기본 관리자 계정이 DB seed/migration으로 생성된다.
  - 기본 계정: `admin / 1234`, role `ADMIN`.
  - `1234`는 초기 seed 비밀번호일 뿐이며 반드시 `password_hash`로만 저장한다. 평문 비밀번호는 DB, 로그, 오류 응답, audit metadata, 대시보드, 테스트 snapshot에 남기지 않는다.
  - 운영 문서에는 기본 비밀번호가 실제 운영에 안전하지 않으며 반드시 변경해야 한다고 명시한다. MVP 로그인 UI에는 별도 비밀번호 변경 경고 배너가 필수는 아니다.
  - `/seed` 기본 관리자 로그인 UI와 `default-admin-seed` 기본 관리자 로그인 API는 v0.10 MVP 흐름에서 제외한다.
- 사용자 관리는 ADMIN이 직접 수행한다.
  - self signup, invite signup, workspace-code signup, open signup은 MVP 흐름이 아니다.
  - ADMIN은 `/admin/users`에서 USER 또는 ADMIN을 생성하고 role/status를 변경한다.
  - USER는 대시보드에 접근하지 않는다. Chrome Extension과 보호된 analyze/config route만 사용한다.
  - hard delete는 MVP에서 제외하고, 사용자 제거는 `DISABLED` 상태로 처리한다.
- Chrome 확장앱: Manifest V3 + TypeScript.
- 대시보드: ADMIN 전용 metadata UI이며 원문 데이터는 표시하지 않는다.
- 대시보드 프론트엔드: `apps/dashboard/` 아래 Vanilla TypeScript SPA.
  - React, Vue, Svelte, Next.js 같은 프레임워크를 사용하지 않고 HTML/CSS/TypeScript만 사용한다. Node.js는 개발·빌드·테스트 도구로만 사용한다. TypeScript는 Vite, `tsc`, 또는 동등한 빌드 단계로 브라우저용 JavaScript로 컴파일한다. API 서버는 Python/FastAPI를 유지한다.
  - `apps/dashboard/src/**/*.ts`와 dashboard source asset이 source of truth다. 생성된 `dist/`는 빌드 산출물이며 손으로 수정하거나 구현 원천으로 리뷰하지 않는다.
  - dashboard 변경은 `cd apps/dashboard && npm run typecheck`, `npm run build`, build output smoke로 검증한다.
- 필터 설정 모델: 단일 Filter Rule 모델.
  - 기본 탐지 규칙, 사용자 정의 keyword/regex 필터, Business Context 문맥 규칙은 하나의 `filter_rules` 모델과 하나의 Filter Rule 관리 화면에서 관리한다.
  - 관리 모델은 통합하지만 실행 엔진은 `detector`, `keyword`, `regex`, `context_rule` 종류별로 분기한다.
  - 기본 탐지기는 `enabled`, `severity`, `action`만 수정 가능하고 내부 parser, checksum, entropy, detector regex, URI/private-key parser는 수정할 수 없다.
- API 계약 원천: `apps/api`의 FastAPI/Pydantic/OpenAPI 출력.
- 서버 구현 스택: Python 3.13 + FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic.
- Redis: 선택 구성.


### 2.1 v0.12 용어와 범위 규칙

아래 용어를 코드, API 계약, WBS 티켓, PR 설명, 대시보드 문구에서 일관되게 사용한다.

| 사용할 용어 | 의미 | 대체하면 안 되는 방향 |
| --- | --- | --- |
| Filter Rule | 관리자 필터 화면에 표시되는 하나의 탐지 규칙 | 별도 설정 화면/모듈 |
| Filter Config | 기본 탐지 설정, 사용자 keyword/regex 규칙, context rule을 합친 실제 실행 설정 | 별도 규칙 관리 모듈 |
| Filter Rule Set Version | 재현성·디버깅을 위한 선택적 내부 버전 | 이벤트 상세 UI 표시 필드 |
| 기본 ADMIN seed | DB seed/migration으로 생성되는 초기 `admin / 1234` 계정 | 사용자 입력형 첫 관리자 생성 화면/API |
| Dashboard session | 대시보드 ADMIN 전용 cookie session | 확장앱 bearer token |
| Extension token flow | Chrome 확장앱이 사용하는 USER/ADMIN bearer-token 흐름 | 대시보드 session |
| 원격 확장앱 설정 | `/config/extension`이 반환하는 selector, timeout, file limit, 선택적 filter config version | 코드에만 고정된 selector 목록 |
| Analyze Input Bundle | 사용자가 보내려는 direct text, paste text, large paste, attachment metadata, unsupported attachment, scanned text file 입력의 묶음 | 모든 입력을 하나의 raw `prompt.text`로 취급 |
| Attachment Metadata | 첨부파일/이미지/서비스 attachment chip의 파일명 해시 또는 extension, MIME, size, count 같은 metadata-only 표현 | raw file bytes, base64, OCR text |

구현 규칙:

- Filter Rule Management와 분리된 독립 설정 화면은 만들지 않는다.
- 사용자 호출형 첫 관리자 생성 흐름은 만들지 않는다.
- MVP에 self signup, invite signup, workspace-code signup, open signup을 넣지 않는다.
- 이벤트 상세 UI에는 어떤 버전 식별자도 표시하지 않는다.
- 재현성을 위해 버전이 필요하면 내부 metadata로 `filter_rule_set_version` 또는 `filter_config_version`을 사용한다.
- 서버 상태 UI에 표시할 수 있는 버전은 작은 앱 빌드/version 값뿐이다.

## 3. 서버·실행환경·인프라 계약
아래 기준을 서버·실행환경 구현 기준으로 사용한다. 단, FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, 03A/03B 분리는 "일반적이고 유지보수하기 쉽고 개발이 빠르다"는 전제에서 확정한다. 구현 중 이 전제가 깨지는 근거가 나오면 코드로 고정하지 말고 사용자에게 다시 확인한다.

1. Python 3.13 웹 프레임워크는 FastAPI로 구현한다.
   - 이유: Python 타입 힌트와 Pydantic 기반 검증, OpenAPI 자동 생성, Swagger/ReDoc 문서화 흐름이 PromptGuard API 계약과 잘 맞는다.

2. Python 요청/응답 검증은 Pydantic v2로 구현한다.
   - 이유: FastAPI와 잘 결합되고, 요청/응답 스키마를 OpenAPI로 내보내기 쉽다.

3. ORM/마이그레이션은 SQLAlchemy 2.x + Alembic으로 구현한다.
   - 이유: Python PostgreSQL 앱에서 표준적인 ORM/SQL 도구 + 마이그레이션 조합이고, 검토 가능한 마이그레이션 스크립트를 만들 수 있다.

4. Redis는 기본 Compose에서 제외하고 선택 profile로만 둔다.
   - 이유: 단일 자가 호스팅 MVP에서 로그인 유지와 빠른 응답 자체에는 Redis가 필수는 아니다. Redis는 다중 인스턴스 rate limit, 분산 짧은 잠금, 큐/캐시가 실제로 필요할 때 추가한다.

5. 런타임 구현 작업은 두 하위 계획으로 나눈다.
   - 03A: Docker Compose, `.env.example`, PostgreSQL, 앱 컨테이너 뼈대.
   - 03B: Python API 뼈대, 설정 로더, 원문 제거 로거, `/livez`, `/readyz`, `/healthz`, 마이그레이션 상태.
   - 이유: Docker/인프라 문제와 API 프레임워크 문제를 분리해야 AI 개발 에이전트가 실패 원인을 파악하기 쉽고 유지보수 단위가 작아진다.

### 3.1 인프라/배포 하위 범위
- 개발 실행:
  - 루트 script는 확장앱/대시보드 JS workspace와 Python API 실행을 혼동하지 않게 분리한다.
  - API는 Python 가상환경 또는 container 기준으로 실행한다.
  - 확장앱은 기존 build/test 흐름을 유지한다.
- Docker:
  - 기본 구성: API, PostgreSQL.
  - API 컨테이너 기준 base image는 현재 Dockerfile과 같은 `python:3.13-slim`이다.
  - 선택 구성: dashboard, reverse proxy, Redis profile.
  - 상태 확인은 `/livez` 또는 `/readyz`를 사용한다.
- 운영 문서:
  - `.env.example`.
  - 설치 안내.
  - reverse proxy/HTTPS 안내.
  - 확장앱 sideload/package 안내.
  - privacy design guide.
  - 관리자 안내.

## 4. 상태 확인 계약

이 섹션은 RFC 9110의 HTTP 상태 의미와 RFC 9457의 HTTP API 문제 상세 형식을 기준으로 한다.

### 4.1 엔드포인트

| 엔드포인트 | 목적 | 인증 | HTTP 상태 규칙 |
| --- | --- | --- | --- |
| `GET /livez` | 프로세스가 살아 있고 이벤트 루프/요청 처리기가 응답 가능한지 확인 | 공개 또는 내부 | 프로세스가 응답 가능하면 `200`, 응답 불가하면 응답 자체가 실패 |
| `GET /readyz` | 트래픽을 받아도 되는지 확인 | 내부 권장 | 설정 유효, DB 연결 가능, 마이그레이션 최신, 기본 필터 설정 로드 가능이면 `200`; 핵심 의존성이 불가하면 `503` |
| `GET /healthz` | 대시보드/운영자용 집계 상태 | 내부 또는 ADMIN 권장 | 핵심 기능 가능하면 `200`; 선택 의존성만 문제면 body `status=degraded`와 함께 `200`; 핵심 의존성 불가면 `503` |
| `GET /status/server` | 대시보드가 쓰는 원문 없는 상태 API | ADMIN | `/healthz`와 같은 안전 메타데이터를 인증된 대시보드 형식으로 반환 |

상태 확인은 UI 기능이라기보다 자가 호스팅 운영 MVP의 일부다. Docker Compose와 새 설치 요구사항은 `/healthz` 같은 준비 상태 확인 없이는 검증하기 어렵다.

### 4.2 상태 응답 형식

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

허용되는 최상위 상태:

- `healthy`: 필수 의존성을 사용할 수 있다.
- `degraded`: 필수 의존성은 사용할 수 있지만 선택 기능 또는 비핵심 기능에 문제가 있다.
- `unhealthy`: 필수 의존성, 설정, 마이그레이션, 필터 설정 상태가 정상 서비스를 막는다.

허용되는 의존성 상태:

- `healthy`
- `degraded`
- `unhealthy`
- `disabled`
- `unknown`

상태 응답에 넣으면 안 되는 필드:

- 원문 프롬프트, 파일 내용, 마스킹된 전체 프롬프트
- 인증 토큰, 갱신 토큰, 비밀번호 해시, HMAC 비밀값
- DB 연결 문자열
- 스택 추적 또는 원문 예외 메시지
- 원본 파일명 또는 원문 탐지값

## 5. HTTP 오류 계약

### 5.1 응답 형식

RFC 9457의 `application/problem+json` 호환 필드를 사용하고, PromptGuard 전용 안전 확장 필드를 덧붙인다.

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

`detail`, `message`, `field_errors.message`는 고정된 안전 문구 또는 정제된 문구여야 한다. 사용자 프롬프트, 파일 텍스트, 원문 탐지값, 비밀값, 스택 추적, 임의 예외 문자열, SQL/내부 서비스 상세를 그대로 되돌려주면 안 된다.

### 5.2 상태 코드 기준

| 상태 | PromptGuard에서 쓰는 경우 | 이 경우에는 쓰지 않음 |
| --- | --- | --- |
| `400 Bad Request` | JSON 형식 오류, 필수 최상위 구조 누락, 스키마 파싱 실패 | 인증됐지만 권한이 없는 사용자 |
| `401 Unauthorized` | access token이 없거나, 유효하지 않거나, 만료됐거나, 형식이 잘못됨 | 유효한 토큰이 있지만 역할 권한이 부족한 경우 |
| `403 Forbidden` | 인증된 사용자의 권한 부족, 비활성 사용자, USER가 ADMIN route 호출 | cross-workspace resource 존재 자체를 숨겨야 하는 경우 |
| `404 Not Found` | route/resource 없음, 또는 금지된 cross-workspace resource 존재를 의도적으로 숨김 | 일반 인증 실패 |
| `409 Conflict` | 중복 요청 충돌, 현재 상태 때문에 처리할 수 없는 오래된 filter config version 충돌 | 일반 검증 오류 |
| `413 Payload Too Large` | 프롬프트/파일/request body가 설정된 크기 제한 초과 | 탐지 결과가 Block인 경우 |
| `415 Unsupported Media Type` | 지원하지 않는 content type 또는 파일 형식 | 의미 검증 오류 |
| `422 Unprocessable Content` | 문법적으로는 유효하지만 업무 의미가 잘못됨. 예: 잘못된 custom regex, 불가능한 필터 설정 전환, 지원하지 않는 rule 표현식 | JSON 형식 오류 |
| `428 Precondition Required` | 향후 filter config version precondition이 필수인데 누락된 요청에 선택적으로 사용 | `409`가 더 잘 맞는 일반 필터 설정 불일치 |
| `429 Too Many Requests` | rate limit 초과 | 인증 실패 |
| `500 Internal Server Error` | 예상하지 못한 서버 실패. 응답은 안전한 일반 문구만 사용 | 예상 가능한 의존성 장애 |
| `503 Service Unavailable` | 필수 의존성 불가, migration 미준비, 서버 미준비 | 선택 Redis 비활성화 |

403과 404 구분:

- client가 인증되어 있고 route/resource 존재를 알아도 안전하지만 권한만 부족하면 `403`을 쓴다.
- workspace 범위 resource 존재를 드러내는 것 자체가 tenant 간 정보 유출이면 `404`를 쓴다. RFC 9110은 금지된 대상의 존재를 숨기기 위해 404를 사용할 수 있게 한다.

409와 중복 요청 구분:

- 같은 `client_request_id`와 같은 인증 workspace/user/request fingerprint이면 가능한 경우 기존 안전 판정을 반환하고 두 번째 event를 만들지 않는다.
- `Mask`의 경우 replay를 위해 `masked_prompt`를 저장하지 않는다. 중복 요청에 원문 프롬프트가 다시 들어오면 결정적 마스킹을 다시 계산해 새 `masked_prompt`를 반환하고, 원래 event/idempotency metadata만 재사용한다. 재계산이 불가능하면 `409 DUPLICATE_REQUEST_RETRY_REQUIRED`와 함께 확장앱이 로컬 상태를 유지하거나 원래 요청을 다시 시도하라는 안전 지시를 반환한다.

## 6. 인증·세션·권한 계약

이 단원은 확장앱 bearer token 흐름과 대시보드 ADMIN session cookie 흐름을 분리해서 정의한다. MV3 service worker inactive 상태는 인증 만료가 아니다. 대시보드는 ADMIN 전용이며 USER 접근은 필요 없다.

### 6.1 식별자와 인증

- `workspace_id`와 `user_id`는 request body가 아니라 인증 토큰/세션 context에서 온다.
- refresh token 원문 값은 절대 저장하지 않고 PostgreSQL에는 hash와 metadata만 저장한다.
- Chrome Extension MV3 service worker inactive 상태는 인증 만료가 아니다. worker wake-up 후 access token이 만료됐으면 먼저 `POST /auth/refresh`를 시도한다.
- 비활성 사용자는 보호 route 실행 전에 차단한다.
- 인증된 USER가 ADMIN 전용 route를 호출하면 `403`을 반환한다.
- 기본 ADMIN seed:
  - fresh DB seed/migration은 기본 ADMIN 계정 `admin / 1234`를 생성한다.
  - 비밀번호는 일반 사용자와 동일한 password hashing 함수로 해시한다.
  - 평문 `1234`는 DB, 로그, audit metadata, 오류 응답, fixture, 대시보드에 저장하지 않는다.
  - 운영 문서에는 `1234`가 안전하지 않은 초기값이며 실제 운영 전에 변경해야 한다고 명시한다.
- 대시보드 세션 인증은 확장앱 bearer token 인증과 분리한다.
  - 대시보드 session은 서버가 관리하는 ADMIN session id를 `HttpOnly` cookie로 전달한다.
  - HTTPS 환경의 session cookie는 `Secure`를 사용한다.
  - Same-site 관리자 UI 기본값은 `SameSite=Lax`로 시작한다.
  - 대시보드 session id는 `localStorage`에 저장하지 않는다.
  - 대시보드 상태 변경 요청은 CSRF 방어를 적용한다.

### 6.2 인증·세션·권한 상세 계약

| 항목 | 기본값 | 이유 |
| --- | --- | --- |
| access token TTL | 900초 | 탈취 피해를 줄이되 refresh로 UX 유지 |
| refresh token TTL | 30일 | MV3 inactive를 로그아웃으로 오판하지 않기 위함 |
| refresh idle timeout | 14일 | 오래 방치된 세션 정리 |
| refresh rotation | enabled | refresh 성공 시 이전 token hash 폐기 |
| refresh reuse detection | enabled | 재사용 탐지 시 token family 폐기 |

권한 매트릭스:

| Surface | Public | USER | ADMIN |
| --- | --- | --- | --- |
| `/auth/login` | 가능 | 가능 | 가능 |
| `/auth/refresh`, `/auth/logout`, `/auth/me` | token 없이는 불가 | 자기 계정 가능 | 자기 계정 가능 |
| `/dashboard/session/login`, `/dashboard/session/csrf` | 가능 | 대시보드 진입 불가 | ADMIN session 가능 |
| `/dashboard/session/logout`, `/dashboard/session/me` | ADMIN session 없이는 불가 | 대시보드 진입 불가 | ADMIN session 가능 |
| `/config/extension` | 불가 | 가능 | 가능 |
| `/prompts/analyze`, `/files/analyze` | 불가 | 가능 | 가능 |
| `/events`, `/stats/*`, `/status/server` | 불가 | 불가, `403` | 가능 |
| `/admin/users`, `/admin/users/{id}/role`, `/admin/users/{id}/status` | 불가 | 불가, `403` | 가능 |
| `/filters`, `/filters/*`, `/filters/dry-run` | 불가 | 불가, `403` | 가능 |
| cross-workspace resource | 불가 | 존재 숨김 `404` | 존재 숨김 `404` |

제거 또는 MVP 제외 흐름:

- `seed/readiness`와 `default-admin-seed`은 v0.10에서 기본 ADMIN seed를 사용하므로 필수 endpoint가 아니다.
- `/auth/register`, invite signup, workspace-code signup, open signup은 MVP 흐름이 아니다.
- 기존 WBS의 invite/signup 항목은 ADMIN 기반 사용자 생성, 사용자 상태/역할 관리, 또는 post-MVP 작업으로 재해석한다.

계정 상태:

- `ACTIVE`: 보호 route 사용 가능.
- `DISABLED`: access/refresh 거부. 보호 route는 `403`.
- `DELETED`: MVP에서는 hard delete를 쓰지 않고 `DISABLED` 또는 anonymized metadata를 사용한다.

### 6.3 확장앱 token auth와 대시보드 session auth 분리

| 구분 | 확장앱 인증 | 대시보드 인증 |
| --- | --- | --- |
| 주요 client | Chrome Extension service worker/options | Vanilla TypeScript dashboard SPA |
| 로그인 endpoint | `POST /auth/login` | `POST /dashboard/session/login` |
| 상태 확인 | `GET /auth/me` | `GET /dashboard/session/me` |
| 갱신 | `POST /auth/refresh` | server-managed session renewal 또는 재로그인 |
| 로그아웃 | `POST /auth/logout` | `POST /dashboard/session/logout` |
| credential 저장 | extension storage의 access/refresh metadata | `HttpOnly` session cookie |
| CSRF | bearer token API에는 기본 미적용 | dashboard 상태 변경 요청에 필수 |
| 실패 UX | options/status UI에서 재로그인 | session 만료 시 `/login` 이동 |

대시보드는 bearer token을 `localStorage`에 저장하지 않는다. USER는 대시보드 route/API에 접근할 수 없다.

## 7. API 경계와 상세 계약

이 단원은 API별 책임 경계와 request/response 계약을 함께 둔다. 실제 구현에서는 `apps/api`의 FastAPI/Pydantic/OpenAPI 출력이 최종 기계 판독 계약이다.

### 7.1 프롬프트 분석 경계

엔드포인트: `POST /prompts/analyze`

서버 책임: request schema 검증, 인증된 workspace/user context, 메모리 안에서만 Analyze Input Bundle 정규화, 통합 Filter Rule 실행, risk score 계산, action 결정, 필요한 경우 `masked_prompt` 생성, 원문 없는 event metadata 저장, HMAC `prompt_hash`, 중복 요청 처리, 안전한 오류 응답.

확장앱 책임: DOM 입력 추출, paste event capture, attachment metadata capture, 전송 전 보류, request body 생성, timeout 처리, Allow/Warn/Mask/Block UX, 서버가 준 `masked_prompt` 적용, 허용된 경우에만 보호된 재전송 수행.

요청 필수값: `inputs[]`, `context.ai_service`, `context.ai_service_domain`, `context.page_url_origin`, `context.extension_version`, `context.browser`, `context.locale`, `filter_config_version`, `client_request_id`.

`inputs[]`는 아래 입력 종류를 구분한다.

| kind | 내용 | 원문/내용 스캔 여부 |
| --- | --- | --- |
| `direct_text` | send 시점 composer에서 읽은 직접 입력 텍스트 | `contentScanned: true` |
| `clipboard_text` | paste event capture에서 읽은 일반 텍스트 | `contentScanned: true` |
| `large_paste` | 크기 제한 때문에 전체를 전송/스캔하지 않는 대용량 붙여넣기 | 정책에 따라 `false` 또는 부분 스캔 |
| `attachment_metadata` | 파일/이미지/서비스 attachment chip metadata | `contentScanned: false` |
| `unsupported_attachment` | metadata 부족 또는 MVP 미지원 첨부 | `contentScanned: false` |
| `file_text` | 정책상 허용된 작은 텍스트 파일의 일시 분석 입력 | `contentScanned: true` |

크기 제한 이름은 byte 기준으로 둔다. 예: `MAX_DIRECT_TEXT_BYTES`, `MAX_CLIPBOARD_CAPTURE_BYTES`, `MAX_ANALYZE_REQUEST_BYTES`, `MAX_FILE_CONTENT_SCAN_BYTES`. Python/JavaScript string length 기반 값은 사용자 입력 크기 제한의 최종 계약으로 쓰지 않는다.

요청 금지값: `user_id`, `workspace_id`, 전체 page URL path/query, 원본 파일명, ID 필드 안의 비밀값.

응답 필수값: `event_id`, `request_id`, `risk_score`, `risk_level`, `action`, 안전한 `user_message`, `allow_original_send`, `requires_justification`, metadata-only `detections[]`, 필요한 경우 `business_context_matches[]`, machine client용 `filter_config_version`, `Mask`일 때만 `masked_prompt`, 선택적 `partial_result`, 선택적 `unscanned_input_kinds[]`.

응답 금지값: 원문 prompt echo, 원문 clipboard text echo, 원문 file content echo, 원문 탐지값, 원본 파일명, 내부 stack trace, 임의 exception text, event/dashboard API에 저장된 full masked prompt.

`contentScanned: false` 입력이 포함된 요청은 silent allow로 처리하지 않는다. 정책에 따라 Block하거나, 사용자가 이해할 수 있는 Warn을 반환하고 event metadata에 unscanned 상태를 남긴다.

### 7.2 파일 분석 경계

MVP 최종 경계: `POST /prompts/analyze`의 `inputs[]`

v0.10에서 독립 경계로 적었던 `POST /files/analyze`는 v0.12 MVP 최종 decision endpoint로 확장하지 않는다. 기존 확장앱 호환 또는 migration 중간 단계로 남을 수는 있지만, 파일/첨부 판단의 최종 계약은 `/prompts/analyze inputs[]`에 흡수한다.

MVP 파일 범위는 텍스트 계열 파일로 제한한다. PDF, Office, OCR, 압축 해제, malware scanning, binary analysis, ZIP 내부 파일 분석, 이미지 내용 분석, Gemini repository deep scan은 MVP 밖이다. 파일 내용은 request 처리 중 일시 입력으로만 사용하고 저장, 로그, 대시보드 표시를 금지한다.

이미지 paste나 이미지 파일은 OCR, pixel inspection, base64 payload scan을 하지 않는다. 가능한 경우 `attachment_metadata`로 표현하고, metadata가 부족하거나 미지원이면 `unsupported_attachment`로 표현한다.

### 7.3 확장앱 설정 경계

엔드포인트: `GET /config/extension`

반환값: `api_base_url`, `filter_config_version`, `timeout_ms`, `ai_service_configs[]`, `file_upload` 설정, ChatGPT 계열 selector config.

### 7.4 Dashboard API 경계

대시보드 API는 login/session 관련 public endpoint를 제외하면 ADMIN 전용이고 metadata만 반환한다.

| Endpoint | Auth | 목적 |
| --- | --- | --- |
| `POST /auth/login` | public | 확장앱 token login |
| `POST /auth/refresh` | refresh token | 확장앱 token refresh |
| `POST /auth/logout` | user token | 확장앱 token logout |
| `GET /auth/me` | user token | 확장앱 사용자 확인 |
| `GET /dashboard/session/csrf` | public | dashboard CSRF token |
| `POST /dashboard/session/login` | public + CSRF | ADMIN dashboard session login |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | dashboard logout |
| `GET /dashboard/session/me` | ADMIN session | 현재 ADMIN session |
| `GET /stats/overview` | ADMIN | overview card/period 통계 |
| `GET /stats/users` | ADMIN | 사용자별 aggregate |
| `GET /stats/events` | ADMIN | 이벤트/action/detection chart summary |
| `GET /events` | ADMIN | 이벤트 목록 |
| `GET /events/{event_id}` | ADMIN | 원문 없는 이벤트 상세 |
| `GET /admin/users` | ADMIN | 사용자 관리 목록 |
| `POST /admin/users` | ADMIN | USER 또는 ADMIN 생성 |
| `PATCH /admin/users/{id}` | ADMIN | 표시 metadata 수정 |
| `PATCH /admin/users/{id}/role` | ADMIN | role 변경 |
| `PATCH /admin/users/{id}/status` | ADMIN | ACTIVE/DISABLED 변경 |
| `GET /filters` | ADMIN | 통합 Filter Rule 목록 |
| `GET /filters/{id}` | ADMIN | Filter Rule 상세 |
| `POST /filters` | ADMIN | custom keyword/regex/context rule 생성 |
| `PATCH /filters/{id}` | ADMIN | `editable_fields` 허용 필드 수정 |
| `PATCH /filters/{id}/enable` | ADMIN | rule 활성화 |
| `PATCH /filters/{id}/disable` | ADMIN | rule 비활성화 |
| `DELETE /filters/{id}` | ADMIN | custom만 archive/delete, built-in 삭제 금지 |
| `POST /filters/dry-run` | ADMIN | 저장 없는 필터 미리 실행 |
| `GET /status/server` | ADMIN | API/PostgreSQL/Migration/Last Checked 상태 |

기존 `/filters` 명칭은 v0.10에서 deprecated이며 `/filters`와 통합 `filter_rules` 모델을 계약으로 사용한다.

### 7.5 Event API 계약

`GET /events` 목록 필드: `event_id`, `created_at`, `user`, `service`, `action`, `risk_score`, `risk_level`, `detection_category`, `detection_type`, `detection_count`, `detail_available`.

`GET /events/{event_id}` 상세 필드: `event_id`, `created_at`, `user`, `service`, `platform`, `action`, `risk_score`, `risk_level`, `detection_summary`, `detections[]`, `prompt_hash_prefix`, 적용되는 경우 `business_context_matches[]`.

대시보드 이벤트 상세 UI에는 `filter_rule_set_version`을 표시하지 않는다. 서버는 내부 metadata로 저장할 수 있다. raw prompt, full masked prompt, raw detected value, original filename, prompt excerpt, surrounding context, stack trace는 응답하지 않는다.

Business Context match metadata 예시:

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

`matched_keywords`는 시스템 rule pack 또는 관리자 등록 context rule 키워드에 한정한다. 임의 원문 span, prompt excerpt, 주변 문장은 반환하지 않는다.

### 7.6 User Management API 계약

`GET /admin/users` 목록 필드: `user_id`, `display_name`, `department`, `role`, `status`, `created_at`, `last_event_at`, `event_count`, `blocked_count`, `masked_count`, `warned_count`.

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

`PATCH /admin/users/{id}/role` request: `{ "role": "ADMIN" }`

`PATCH /admin/users/{id}/status` request: `{ "status": "DISABLED" }`

hard delete는 MVP에서 제외한다. USER는 `/admin/users` route 접근과 자기 role ADMIN 변경이 불가하다.

### 7.7 Filter Management API 계약

Filter Rule 관리는 단일 `Filter Rule` 모델을 사용한다. 기본 탐지 설정, custom keyword/regex, Business Context rule은 같은 목록/상세/수정 lifecycle을 쓰며, 실행은 `source`와 `kind`에 따라 분기한다.

Filter Rule 공통 필드: `id`, `workspace_id`, `source`, `kind`, `category`, `label`, `description`, `placeholder`, `detector_key`, `keyword`, `pattern`, `severity`, `action`, `enabled`, `editable_fields`, `config_json`, `version`, `archived_at`, `created_by`, `updated_by`, `created_at`, `updated_at`.

Built-in detector는 `enabled`, `severity`, `action`만 수정 가능하다. detector regex, checksum, entropy, parser, `detector_key`는 수정 불가다.

Custom keyword/regex는 keyword/pattern, label, placeholder, severity, action, enabled를 수정할 수 있다. Regex 저장 전에는 syntax, 길이, timeout/safe-regex, ReDoS 방어 검증을 수행한다.

Context rule은 keyword groups, exclusion keywords, window size, min_condition_count, sensitivity `low/medium/high`, severity/action/enabled를 수정할 수 있다. scoring weights는 advanced setting이다. LLM prompt 편집은 MVP에서 제공하지 않는다.

`POST /filters/dry-run`은 sample_text를 request-only로 사용하며 저장하지 않는다. 응답에는 `matched`, `expected_action`, `expected_severity`, `match_count`, `reason_code`, `matched_keywords`, `evidence_counts`, `sample_persisted=false`를 반환할 수 있다. sample text, raw detected value, prompt excerpt, surrounding context, file content, original filename은 저장/로그 금지다.

Filter API 오류: USER 접근 `403`, 없는 filter `404`, built-in 내부 로직 수정 시 `422`, 위험 regex `422`, dry-run sample 과대 `413`, 중복 label 충돌 `409`.

### 7.8 Server Status API

`GET /status/server`는 UI에 필요한 API status, PostgreSQL status, Migration status, last_checked, 선택적 작은 version metadata만 반환한다. dashboard status UI는 Filter Config/Environment를 기본 표시하지 않는다. `/readyz` 내부 readiness 조건에는 filter config load를 포함할 수 있다.

## 8. 제품 범위와 저장소 구조

이 단원은 MVP 제품 범위와 코드 위치를 정의한다. 상세 구현 계약은 API, 데이터, 탐지, 확장앱, 대시보드 단원을 따른다.

### 8.1 제품 범위

- 제품 목적:
  - 사용자가 ChatGPT 같은 AI 서비스에 민감한 업무 정보, 개인정보, 비밀값, 계약 정보, 파일 내용을 보내기 전에 위험을 판별한다.
  - 서버에는 원문을 영구 저장하지 않고, 관리자는 metadata와 통계만 본다.
  - self-hosted 환경에서 관리자가 서버와 DB를 운영하고, 팀원은 Chrome 확장앱으로 보호 흐름을 사용한다.
- MVP 포함:
  - self-hosted 서버 실행, 기본 ADMIN seed login, ADMIN 기반 사용자 생성·상태·권한 관리.
  - Chrome 확장앱의 ChatGPT 입력 탐지, 전송 보류, Analyze API 호출, Allow/Warn/Mask/Block 처리.
  - Python Analyze API, rule-based detector, 통합 Filter Rule 모델, 위험 점수, 서버 측 마스킹, 중복 요청 처리, prompt hash.
  - ADMIN 대시보드 login, overview, event metadata, user management/stats, filter rule management, status 화면.
  - 개인정보/보안 회귀 테스트, Docker 기반 실행, 설치 문서, 최종 smoke scenario.
- MVP 제외:
  - 첫 관리자 seed page와 `default-admin-seed` 사용자 흐름.
  - self-signup, invite signup, workspace-code signup, open signup.
  - 사용자 hard delete.
  - 대시보드 공통 필터와 고급 drill-down 필터.
  - 외부 LLM 호출 기반 분류.
  - PDF/Office/OCR/archive/binary 파일 분석.
  - 브라우저 네트워크 요청 감청 기반 검사.
  - SaaS 멀티테넌트 운영, 결제, 엔터프라이즈 조직 관리.
  - SIEM 연동, SSO, 고급 필터 설정 workflow.

### 8.2 저장소와 코드 위치

| 대분류 | 소분류 | 기본 위치 | 설명 |
| --- | --- | --- | --- |
| API 서버 | Python 3.13 self-hosted API | `apps/api/` | `python:3.13-slim` 기준 FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. API schema, auth, detector, unified filter rules, masking, event service를 포함한다. |
| 대시보드 | Vanilla TypeScript SPA 관리자 UI | `apps/dashboard/` | `apps/dashboard/src/**/*.ts`가 구현 원천이다. React, Vue, Svelte, Next.js 없이 HTML/CSS/TypeScript로 구현하고 Vite/tsc build output을 smoke 검증한다. login, overview, events, users, filters, status 화면을 포함한다. |
| 확장앱 | Chrome Extension | `apps/extension/` | content script, service worker, options, shared types/tests, real API 연동을 유지한다. |
| 인프라 | Docker/env/reverse proxy | `infra/` | Docker Compose, PostgreSQL, 선택 Redis profile, reverse proxy 예시를 포함한다. |
| 테스트 | 통합/보안/회귀 | 각 app의 `tests/` 또는 root tests | 앱별 단위 테스트와 cross-app privacy/security smoke를 둔다. |

권장 대시보드 파일 구조:

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

## 9. 데이터 모델·원문 저장 금지 계약

데이터 모델은 metadata-only 저장을 기준으로 한다. 원문 프롬프트, 원문 파일 내용, full `masked_prompt`, 원문 탐지값, prompt excerpt, 주변 문맥, 원본 파일명은 DB, 로그, 대시보드, 오류 응답에 저장하거나 노출하지 않는다.

### 9.1 데이터 모델 하위 범위

- 계정/조직:
  - `workspaces`: self-hosted workspace 단위.
  - `users`: email/username, display name, department, role, status, password hash metadata.
  - `refresh_tokens`: raw token 저장 금지, hash와 만료/폐기 metadata만 저장.
- 필터 설정:
  - `filter_rules`: built-in detector, custom keyword/regex filter, Business Context context rule을 모두 관리하는 통합 모델.
  - `filter_rule_versions`: filter rule 변경 이력.
  - `ai_service_configs`: ChatGPT 계열 domain과 selector/config.
- 분석 이벤트:
  - `analysis_events`: event id, workspace/user id, action, risk score, risk level, prompt hash, 내부 filter rule set version, service metadata, created_at.
  - `event_detections`: detection category/type, source, filter_rule_id, reason_code, match_count, matched_keywords, evidence_counts, severity, action, safe_evidence.
  - `event_feedback`: 사용자 확인/사유 metadata. 원문 금지.
  - `audit_logs`: auth/admin/filter/user action metadata. request body 원문 금지.
- 금지 컬럼:
  - `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, `raw_detected_value`, `original_filename`, `secret_value`, `token_raw`, `password_plain` 같은 컬럼은 만들지 않는다.

### 9.2 데이터 모델 상세 계약

| Table | 핵심 컬럼 | 제약 |
| --- | --- | --- |
| `workspaces` | `id`, `name`, `created_at`, `status` | `id` primary key |
| `users` | `id`, `workspace_id`, `email`, `username`, `display_name`, `department`, `role`, `status`, `password_hash`, `created_at`, `updated_at`, `last_event_at` | workspace 안 email/username unique, hard delete 제외 |
| `refresh_tokens` | `id`, `workspace_id`, `user_id`, `token_hash`, `family_id`, `expires_at`, `idle_expires_at`, `revoked_at`, `reused_at`, `created_at` | raw token 저장 금지 |
| `ai_service_configs` | `id`, `workspace_id`, `service`, `domain`, `selector_config`, `enabled`, `version` | extension config source |
| `filter_rules` | `id`, `workspace_id`, `source`, `kind`, `category`, `label`, `description`, `detector_key`, `keyword`, `pattern`, `placeholder`, `severity`, `action`, `enabled`, `editable_fields`, `config_json`, `version`, `archived_at`, `created_by`, `updated_by`, `created_at`, `updated_at` | 통합 Filter Rule 모델 |
| `filter_rule_versions` | `id`, `filter_rule_id`, `workspace_id`, `version`, `change_type`, `before_json`, `after_json`, `changed_by`, `created_at` | sample text 없는 변경 이력 |
| `idempotency_keys` | `id`, `workspace_id`, `user_id`, `client_request_id`, `request_fingerprint`, `event_id`, `created_at`, `expires_at` | 중복 event 방지 |
| `analysis_events` | `id`, `workspace_id`, `user_id`, `prompt_hash`, `action`, `risk_score`, `risk_level`, `filter_rule_set_version`, `service`, `service_domain`, `platform`, `created_at` | raw prompt/full mask 저장 금지 |
| `event_detections` | `id`, `event_id`, `category`, `type`, `source`, `filter_rule_id`, `severity`, `confidence`, `count`, `reason_code`, `match_count`, `matched_keywords`, `evidence_counts`, `safe_evidence` | raw detected value 저장 금지 |
| `event_feedback` | `id`, `event_id`, `user_id`, `feedback_type`, `reason_code`, `created_at` | free text reason은 MVP에서 비활성 또는 redaction |
| `audit_logs` | `id`, `workspace_id`, `actor_user_id`, `action`, `target_type`, `target_id`, `safe_metadata`, `created_at` | request body 원문 금지 |

기본 ADMIN seed:

- seed/migration은 기본 ADMIN 사용자 `admin / 1234`를 `role=ADMIN`, `status=ACTIVE`로 생성한다.
- `password_hash`만 저장한다.
- seed는 idempotent해야 하며 재시작 시 admin 사용자를 중복 생성하지 않는다.
- 이후 ADMIN은 `/admin/users`로 생성 가능하므로 `role=ADMIN` 전역 unique 제약은 걸지 않는다.

Filter Rule 저장 규칙:

- built-in detector의 내부 regex/checksum/parser/entropy 로직은 DB에 저장하지 않는다. `detector_key`와 workspace override만 저장한다.
- custom keyword/regex/context_rule 설정은 DB에 저장 가능하다.
- custom regex pattern은 저장 가능하지만 raw match value는 저장하지 않는다.
- context rule의 `keyword_groups`, `exclusion_keywords`, `window_size`, `min_condition_count`, `sensitivity`, `advanced_weights`는 `config_json` 또는 필요 시 정규화된 하위 테이블에 저장한다.
- Business Context matched keyword count는 임의 원문 span이 아니라 설정된 rule keyword 기준이므로 `event_detections`에 safe metadata로 저장할 수 있다.
- matched keyword 자체가 내부 프로젝트명일 수 있으므로 dashboard 접근은 ADMIN 전용이다.

마이그레이션 순서:

1. workspace/user 기본 테이블과 기본 ADMIN seed
2. refresh token/auth 테이블
3. ai service config 테이블
4. 통합 `filter_rules`, `filter_rule_versions`
5. idempotency/event/detection/feedback/audit 테이블
6. built-in detector filter rules, built-in context rules, default workspace/config seed
7. 금지 컬럼 privacy schema scan

### 9.3 DB 관계·인덱스·삭제 규칙

| 관계 | 기준 |
| --- | --- |
| `workspaces 1:N users` | 모든 user는 workspace에 속한다. |
| `users 1:N refresh_tokens` | refresh token family는 user와 workspace에 묶인다. |
| `workspaces 1:N filter_rules` | 모든 filter rule은 workspace 단위다. |
| `filter_rules 1:N filter_rule_versions` | filter 변경은 version/audit metadata로 남긴다. |
| `analysis_events 1:N event_detections` | event는 원문 없는 탐지 요약을 가진다. |
| `analysis_events 1:N event_feedback` | 사용자 확인/사유 metadata만 저장한다. |

필수 인덱스:

| Table | 제약/인덱스 | 이유 |
| --- | --- | --- |
| `users` | unique `(workspace_id, lower(email))`, username 사용 시 unique `(workspace_id, lower(username))` | 중복 계정 방지 |
| `refresh_tokens` | unique `token_hash`, index `(user_id, family_id)` | token rotation/reuse 탐지 |
| `filter_rules` | index `(workspace_id, enabled)`, `(workspace_id, source, kind)` | filter 목록과 pipeline load |
| `filter_rule_versions` | index `(filter_rule_id, version)` | 변경 이력 |
| `idempotency_keys` | unique `(workspace_id, user_id, client_request_id)` | 중복 event 방지 |
| `analysis_events` | index `(workspace_id, created_at)`, `(workspace_id, user_id, created_at)`, `(workspace_id, action, created_at)` | dashboard list/stat query |
| `event_detections` | index `(event_id)`, `(category)`, `(type)`, `(filter_rule_id)` | 상세/통계 aggregate |
| `audit_logs` | index `(workspace_id, created_at)`, `(actor_user_id, created_at)` | admin audit |

삭제/비활성 규칙:

- MVP에서 user hard delete는 하지 않는다. `DISABLED` 상태를 사용한다.
- built-in filter rule은 삭제할 수 없다.
- custom filter rule과 context rule은 disabled 또는 archived 처리한다. hard delete는 과거 event metadata를 깨지 않도록 조심한다.
- event row는 privacy-safe metadata만 저장하므로 retention rule로 삭제할 수 있다.
- audit log는 action/target/safe_metadata만 저장한다.

## 10. 탐지·마스킹·점수·Filter Rule 계약

탐지와 마스킹은 서버 책임이다. 확장앱은 전송을 보류하고 서버가 반환한 action과 `masked_prompt`를 적용한다.

### 10.1 파이프라인 순서

1. request schema validation
2. workspace/user/config load
3. transient text normalization
4. `source=built_in`, `kind=detector` Filter Rule을 통한 built-in detector 실행
5. custom keyword filter 실행
6. custom regex filter 실행
7. context rule 실행
8. overlap merge
9. risk scoring
10. action decision
11. masking generation
12. metadata-only event logging
13. safe response

### 10.2 Detector 및 Filter Rule 종류

- Built-in detector rules:
  - Secret: API Key, GitHub Token, AWS Key, JWT, DB Connection String, `.env` Secret, Private Key, High Entropy Token.
  - PII: Phone Number, ID Number, Email, Card Number, Business Registration Number.
  - 내부 로직은 code-backed이며 관리자 수정 불가다.
- Custom keyword rules:
  - 관리자가 정의하는 exact/contains/case-insensitive 키워드 매칭.
- Custom regex rules:
  - 관리자가 정의하는 pattern filter. 저장 전 safe-regex 검증이 필요하다.
- Context rules:
  - Contract, Penalty, NDA, Customer Info, Trade Secret, Internal Strategy, Launch Plan, Pricing Policy 같은 Business Context.
  - rule-based evidence scoring만 사용한다. MVP에서 LLM prompt 직접 편집은 제공하지 않는다.

### 10.3 Context Rule 점수화

Context rule은 텍스트를 문장/문단/window 단위로 나눈다. 각 window에서 keyword group, exclusion keyword, 금액/기간/비율 표현, detector 결과 같은 evidence를 계산한다.

Context rule 제어 항목:

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

기본 UI는 sensitivity를 제공하고, advanced settings에서 weights를 제공한다.

Context detection output은 `category`, `reason_code`, `evidence_counts`, `matched_keywords`, `match_count`, `severity`, `action`을 포함한다. raw prompt span, 주변 문장, prompt excerpt는 포함하지 않는다.

### 10.4 Overlap 및 우선순위

- Secret detection은 일반 business context보다 우선한다.
- 같은 우선순위에서는 긴 span을 우선한다.
- 겹치는 detection은 response와 통계에서 이중 계산하지 않는다.
- context rule evidence는 raw span을 저장하지 않고 safe evidence count와 configured keyword count만 저장한다.

### 10.5 위험도와 Action 결정

최종 action은 detector가 아니라 서버 orchestrator가 결정한다. 같은 입력, workspace, active Filter Rule set, scoring config라면 같은 결과를 내야 한다.

| Detection | 기본 점수 | 기본 action |
| --- | ---: | --- |
| confirmed secret: API key, private key, DB URI, JWT | 90 | Block 또는 Mask, secret은 Block 우선 |
| confirmed credential-like `.env` secret | 85 | Mask |
| 주민번호/card/business id 같은 강한 PII | 80 | Mask |
| email/phone 단독 | 45 | Warn |
| 계약금액/위약금/NDA 문맥 | 65 | Warn 또는 Mask |
| 고객정보/영업기밀/내부전략 문맥 | 65 | Warn 또는 Mask |
| ambiguous low confidence | 30 | Allow 또는 Warn |
| custom filter critical | 90 | rule action 우선 |
| custom filter high | 70 | rule action 우선 |

### 10.6 마스킹

- 마스킹은 서버가 생성한 `masked_prompt`를 기준으로 한다.
- `Mask` action에서만 `masked_prompt`를 응답에 포함한다.
- `masked_prompt`는 event row나 dashboard API에 저장하지 않는다.
- 같은 민감값 반복은 같은 placeholder로 치환한다.
- placeholder 예: `[SECRET_1]`, `[EMAIL_1]`, `[CONTRACT_AMOUNT_1]`, `[INTERNAL_PROJECT_1]`.

### 10.7 Filter Rule Versioning 및 Dry-run

- enabled/severity/action/keyword/pattern/context config가 바뀌면 filter rule version을 남긴다.
- dry-run sample text는 request-only이며 저장하지 않는다.
- dry-run 결과에는 safe match count, reason code, expected action, expected severity, configured matched keywords를 표시할 수 있다.
- raw match value, prompt excerpt, surrounding context, file content, original filename은 저장하거나 표시하지 않는다.

## 11. 확장앱 계약

확장앱은 ChatGPT 계열 화면에서 입력을 탐지하고 전송을 보류한 뒤, 실제 self-host API 판정에 따라 UX와 재전송을 처리한다.

### 11.1 확장앱 하위 범위
- content script:
  - 대상 domain에서만 동작한다.
  - textarea와 contenteditable 후보를 찾고, visible/focus 기준으로 현재 composer를 고른다.
  - send button click과 Enter 전송을 분석 완료 전 보류한다.
  - `@` mention, IME composition, Shift+Enter 줄바꿈, GPT picker 같은 작성 보조 동작은 전송으로 오판하지 않는다.
- service worker:
  - API base URL, token, selector/filter config cache, timeout, auth error 처리를 맡는다.
  - request body는 Analyze API 계약에 맞춰 만들고, workspace/user id를 임의로 넣지 않는다.
  - MV3 service worker inactive는 정상 lifecycle이며 로그인 만료로 취급하지 않는다.
  - wake-up 후 저장된 auth/session metadata를 읽고 access token 만료 시 자동 refresh를 먼저 시도한다.
  - refresh 실패가 확정된 경우에만 options page 또는 상태 UI에서 재로그인을 요구한다.
- options page:
  - self-host API URL 저장.
  - 연결 테스트.
  - login/logout/refresh 상태.
  - server status와 filter config sync time 표시.
  - service worker inactive 자체를 오류로 표시하지 않는다.
  - refresh token 만료/폐기/재사용/계정 비활성/서버 변경 같은 실제 인증 실패만 사용자의 조치가 필요한 상태로 표시한다.
- action UX:
  - Allow: 원래 전송을 1회 재실행.
  - Warn: 확인 전 보류, 확인 후 전송.
  - Mask: 서버가 준 `masked_prompt`를 입력창에 치환하고 사용자가 다시 전송하도록 한다.
  - Block: 원문 전송을 발생시키지 않는다.
  - 통과되는 Allow는 불필요한 panel을 표시하지 않는다.

## 12. 대시보드 계약

대시보드는 ADMIN 전용 metadata UI다. Overview, Events, Users, Filter Rule Management, Server Status 화면은 집계와 안전한 metadata만 보여주며 원문 데이터를 보여주지 않는다. 대시보드 프론트엔드는 `apps/dashboard/` 아래 Vanilla TypeScript SPA이며 React, Vue, Svelte, Next.js 같은 프레임워크를 사용하지 않는다. 구현 원천은 `apps/dashboard/src/**/*.ts`와 source asset이며, `dist/`는 빌드 산출물이다. 리뷰와 완료 판단은 TypeScript source, `npm run typecheck`, `npm run build`, built-output smoke를 함께 본다.

### 12.1 대시보드 화면

로그인 페이지:

- ID/PW input
- 로그인 버튼
- 세션 만료 시 로그인 페이지 이동
- MVP에서는 현재 관리자 표시가 필수 아님
- MVP에서는 상세 로그인 실패/서버 연결 실패 UI가 필수 아님

Overview:

- 카드: Total Events, Blocked, Masked, Warned, Active Users
- 차트: 이벤트별 통계, 사용자별 통계, 기간별 통계
- 버튼: Events, User Management, Filter Rule Management, Server Status, Logout
- 대시보드 전체 공통 필터는 MVP에서 제외

Events:

- 테이블 컬럼: 시간, 사용자, 서비스, action, 위험도, 탐지 카테고리, 탐지 세부유형, 상세보기
- 상세 패널/모달 필드: event ID, time, user, service, platform, action, risk score, risk level, detection summary, detection items, `prompt_hash_prefix`
- 이벤트 상세 UI에서는 어떤 version 식별자도 표시하지 않는다. 서버 내부에는 `filter_rule_set_version`을 저장할 수 있다.
- 탐지 요약과 탐지 근거 요약은 `탐지 요약` 하나로 합친다.
- Business Context는 configured matched keywords와 count를 표시할 수 있다. raw prompt excerpt와 주변 문맥은 금지한다.

Users:

- 컬럼: 사용자 ID, 사용자 이름, 부서, 권한, 상태, 마지막 이벤트 시간, 생성일, 이벤트 수, Blocked, Masked, Warned, 정보 수정, 비활성화
- hard delete 제외. 사용자 비활성화를 사용한다.
- row click은 페이지네이션된 사용자별 이벤트 목록을 연다.

Filter Rule Management:

- built-in detector, custom keyword, custom regex, context rule을 하나의 필터 목록에서 보여준다.
- source/kind/category를 표시한다.
- built-in detector form은 enabled/severity/action만 수정 가능하다.
- custom keyword form은 keyword/label/placeholder/severity/action/enabled를 수정한다.
- custom regex form은 pattern/label/placeholder/severity/action/enabled를 수정하고 regex validation error를 표시한다.
- context rule form은 keyword groups, exclusion keywords, window size, minimum condition count, sensitivity low/medium/high, severity/action/enabled, advanced scoring weights를 제공한다.
- dry-run panel은 예상 결과를 보여주며 sample text를 저장하지 않는다.
- built-in filter는 삭제 불가, custom filter/context rule은 disabled 또는 archived 처리한다.

Server Status:

- API, PostgreSQL, Migration, Last Checked 표시
- Version은 작은 metadata로 표시 가능
- Filter Config/Environment는 기본 표시하지 않음
- 상태: healthy, degraded, unhealthy, disabled, unknown
- disabled는 optional feature에만 적용하고 API/PostgreSQL/Migration에는 적용하지 않는다.



명확화:

- 이벤트 상세 UI에는 `filter_config_version`, `filter_rule_set_version` 또는 그 밖의 어떤 버전 식별자도 표시하지 않는다.
- 서버는 재현성, 감사, 디버깅 목적의 내부 metadata로만 버전을 저장할 수 있다.
- 탐지 설정을 관리하는 관리자 화면은 Filter Rule Management 하나뿐이다. 별도 설정 화면은 만들지 않는다.

### 12.2 대시보드 화면 계약

| Screen | Route | APIs used | Required UI | Empty state | Loading state | Error state | Permission | Test/verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Login | `/login` | `POST /dashboard/session/login`, `GET /dashboard/session/me` | ID/PW, 로그인 버튼 | 이미 로그인 시 dashboard 이동 | login 요청 pending | session 만료 시 login 이동 | public/ADMIN session | localStorage session 금지, CSRF/session cookie |
| Overview | `/dashboard` | `GET /stats/overview`, `GET /stats/users`, `GET /stats/events` | 카드, 이벤트/사용자/기간 차트, 이동 버튼, 로그아웃 | 이벤트 없음 | skeleton/spinner | safe error banner | ADMIN | metadata만 렌더링 |
| Events | `/events` | `GET /events`, `GET /events/{event_id}` | 이벤트 테이블과 상세 패널/모달 | 이벤트 없음 | table/detail loading | safe API errors | ADMIN | version 식별자 UI 없음, raw source 없음 |
| Users | `/users` | `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}`, `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/status` | user list, add/edit/disable, user event list | 사용자/이벤트 없음 | table/form loading | validation/RBAC errors | ADMIN | hard delete 없음, USER 403 |
| Filters | `/filters` | `GET /filters`, `GET /filters/{id}`, `POST /filters`, `PATCH /filters/{id}`, `PATCH /filters/{id}/enable`, `PATCH /filters/{id}/disable`, `DELETE /filters/{id}`, `POST /filters/dry-run` | 통합 filter list, forms, dry-run panel | filter 없음 | list/form loading | regex/editable_fields/dry-run errors | ADMIN | source/kind rules, sample 미저장 |
| Status | `/status` | `GET /status/server` | API/PostgreSQL/Migration/Last Checked, optional version | unknown info | polling/loading | unhealthy/degraded/unknown 표시 | ADMIN | secret, DB URL, stack trace, filter config/env 기본 UI 없음 |

### 12.3 MVP 대시보드 API·통계 계약

MVP 대시보드는 원문 검토 도구가 아니다. 모든 dashboard API는 metadata-only다.

통계 정의:

- `event_count`: 고정 MVP 기간에 해당하는 `analysis_events` row 수.
- `active_user_count`: 선택/기본 기간 내 event가 1개 이상 있는 distinct `user_id`.
- `blocked_count`, `masked_count`, `warned_count`: action별 count.
- `top_detector_category`: event_detections category aggregate.
- `period bucket`: UTC 저장값 기준 집계 후 표시 시 browser timezone 변환.

MVP는 dashboard-wide filter controls를 요구하지 않지만, API 설계는 이후 cursor/range/filter 확장을 막지 않아야 한다.

## 13. 보안·개인정보 계약
### 13.1 실무 통제

- Request body logging은 기본적으로 비활성화하거나 원문 제거 처리를 한다.
- Access log는 안전할 때만 method, path template, status, latency, request id, user/workspace id를 기록한다.
- Error handler는 raw exception object를 직렬화하지 않는다.
- 모든 secret은 환경변수, Docker secret, 또는 이후 secret manager 연동에서 오며, 커밋된 파일에 넣지 않는다.
- PostgreSQL migration은 검토 가능하고 재현 가능해야 한다.
- 인증 토큰, refresh token, HMAC key, password hash, DB URL, API key는 health/status/error/dashboard를 통해 노출하지 않는다.
- CORS allowlist는 명시한다. credential이 붙는 wildcard CORS는 허용하지 않는다.
- 단일 인스턴스 MVP의 rate limiting은 Redis 없이 시작한다. Redis는 구체적인 필요가 확인될 때만 추가한다.
- Custom regex filter에는 길이 제한, syntax 검증, timeout 또는 safe regex engine 전략, ReDoS 테스트가 필요하다.
- Dashboard API는 metadata만 반환한다.

### 13.2 MVP 릴리스 전 필수 회귀 테스트

- DB schema scan: `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, 원문 탐지값 column이 없어야 한다.
- Log scan: seeded prompt/file/secret value가 application/access/error log에 나타나면 안 된다.
- Error scan: validation/server error가 request body나 stack trace를 echo하면 안 된다.
- Dashboard scan: events/details/user stats가 raw prompt, masked prompt, original filename, raw detected value를 보여주면 안 된다.
- Idempotency test: 중복 `client_request_id`가 event를 하나만 만들어야 한다.
- HMAC test: 같은 workspace+prompt는 같은 `prompt_hash`를 만들고, 다른 workspace는 다른 hash를 만들어야 한다.
- Auth/RBAC test: USER는 ADMIN route에 접근할 수 없고, disabled user는 차단되어야 한다.
- Health/status test: PostgreSQL 또는 migration을 사용할 수 없으면 `/readyz`가 실패해야 한다. 선택 Redis disabled는 degraded가 아니다.

Privacy fixture matrix:

| Fixture id | Seeded value | 사용 위치 | 나오면 안 되는 위치 | 통과 기준 |
| --- | --- | --- | --- | --- |
| `privacy_prompt_contract_amount` | `NDA 위약금은 3억원입니다` | `/prompts/analyze` request | DB event row, app/access/error log, dashboard DOM/API, problem detail | raw sentence absent; metadata category/count만 존재 |
| `privacy_secret_github_token` | `ghp_testsecret1234567890abcdef` 형태 dummy | analyze/file/filter rule dry-run | DB/log/error/dashboard/API response except safe detection summary | raw token absent; `category=api_key` summary 가능 |
| `privacy_file_text` | `고객사 담당자 전화번호 010-0000-0000` | `/prompts/analyze inputs[]`의 `file_text` 또는 호환 `/files/analyze` 입력 | DB/log/dashboard/event detail/original filename fields | raw file text absent; phone detection count 가능 |
| `privacy_masked_prompt` | `[SECRET_1]`가 포함된 mask response | Mask response only | `analysis_events`, dashboard event/detail/stats, logs | full masked prompt absent from persistence/display |
| `privacy_filter_rule_sample` | dry-run sample sentence | `/filters/dry-run` request | filter rule tables, event tables, logs | sample not persisted; match count only |
| `privacy_error_echo` | invalid request body with seeded secret | validation/error path | `detail`, `message`, `field_errors.message`, logs | fixed safe error only |
| `privacy_status_secret` | dummy DB URL/JWT/HMAC secret env | health/status/error | `/healthz`, `/status/server`, logs | secret value absent; safe dependency code only |

Privacy test implementation requirements:

- 테스트는 seed 값을 하나의 fixture module에 모으고 DB/log/API/dashboard scan이 같은 seed 목록을 사용한다.
- scan은 exact string과 URL/base64/JSON-escaped 변형을 모두 확인한다.
- dashboard privacy test는 API response와 rendered DOM을 모두 확인한다.
- 실패 시 해당 slice는 기능 동작 여부와 관계없이 release gate를 통과할 수 없다.

### 13.3 보안/개인정보 하위 범위
- 원문 금지:
  - request에는 raw prompt/file content가 들어올 수 있지만 저장, 로그, 대시보드, error response, memory/session log에는 남기지 않는다.
  - request body logging은 기본 차단 또는 redaction한다.
- 인증/인가:
  - 확장앱은 bearer token + refresh token 흐름을 사용한다.
  - 대시보드는 server-managed session cookie 흐름을 사용한다.
  - Dashboard session cookie는 `HttpOnly`를 사용하고 HTTPS에서는 `Secure`를 사용한다.
  - Dashboard session은 `SameSite=Lax`를 기본으로 시작하며, cross-site 필요가 없으면 `Strict`를 검토한다.
  - 대시보드 상태 변경 요청은 CSRF token 검증을 통과해야 한다.
  - 대시보드 session id는 `localStorage`에 저장하지 않는다.
  - access token은 짧게, refresh token은 hash만 저장한다.
  - ADMIN/USER route를 분리하고, cross-workspace 접근은 404 hiding을 고려한다.
- 오류:
  - 오류 응답은 safe problem detail만 반환한다.
  - stack trace, SQL detail, exception raw message, request body echo 금지.
- 네트워크:
  - MVP detector는 외부 LLM 호출을 하지 않는다.
  - CORS는 명시 allowlist이고 credentialed wildcard 금지다.
- 규칙 실행:
  - regex length/syntax/time limit/ReDoS 테스트를 둔다.
  - file size/request size limit을 둔다.

## 14. 파일 분석 제한과 환경변수 계약

파일 분석 제한과 환경변수는 테스트 명령과 분리한다. 파일 내용은 prompt text와 같은 원문 입력으로 취급하며, 서버 처리 중에만 사용하고 저장하지 않는다.

### 14.1 파일 분석 제한

- MVP는 text file만 지원한다.
- 허용 확장자 기본값: `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.log`.
- 허용 MIME 기본값: `text/*`, `application/json`, `application/x-yaml`.
- 최대 파일 크기 기본값: 256 KiB.
- 최대 request body 기본값: 512 KiB.
- encoding: UTF-8 우선, 실패 시 `415` 또는 `422`.
- binary sniffing에서 null byte 또는 높은 binary ratio가 나오면 `415`.
- original filename은 저장하지 않는다. 필요하면 extension이 local-only 표시로만 사용한다.

### 14.2 환경변수 계약

| 변수 | 필수 | 예시 | 설명 |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql+psycopg://promptguard:promptguard@postgres:5432/promptguard` | PostgreSQL 연결 |
| `PROMPTGUARD_ENV` | yes | `self-host-dev` | 환경 이름 |
| `PROMPTGUARD_HMAC_SECRET` | yes | `dev-only-change-me` | prompt_hash HMAC secret, 운영값 커밋 금지 |
| `PROMPTGUARD_JWT_SECRET` | yes | `dev-only-change-me` | access token signing secret |
| `PROMPTGUARD_REFRESH_SECRET` | yes | `dev-only-change-me` | refresh token hash pepper |
| `ACCESS_TOKEN_TTL_SECONDS` | no | `900` | access token TTL |
| `REFRESH_TOKEN_TTL_DAYS` | no | `30` | refresh token TTL |
| `REFRESH_IDLE_TIMEOUT_DAYS` | no | `14` | refresh idle timeout |
| `CORS_ALLOWED_ORIGINS` | yes | `chrome-extension://...,http://localhost:5173` | 명시 allowlist |
| `MAX_DIRECT_TEXT_BYTES` | no | `65536` | direct composer text byte limit |
| `MAX_CLIPBOARD_CAPTURE_BYTES` | no | `65536` | paste-event clipboard text capture byte limit |
| `MAX_ANALYZE_REQUEST_BYTES` | no | `524288` | full analyze request body byte limit |
| `MAX_FILE_CONTENT_SCAN_BYTES` | no | `262144` | small text-file transient scan byte limit |
| `MAX_FILE_BYTES` | no | `262144` | file body limit |
| `REDIS_URL` | no | empty | optional profile에서만 사용 |

## 15. 테스트·완료·릴리즈 게이트

이 단원은 완료 판단 기준을 정의한다. 일부 코드가 있더라도 fresh install, privacy regression, 실제 API/extension/dashboard smoke가 통과하지 않으면 MVP 완료로 보지 않는다.

### 15.1 테스트/완료 기준 하위 범위

API 테스트:

- fresh DB에서 기본 ADMIN seed가 `admin` 계정을 정확히 1개 생성한다.
- 기본 ADMIN password는 hash로만 저장한다.
- 로컬/fresh install 흐름에서 `admin / 1234`로 로그인 가능하다.
- USER dashboard 접근은 `403` 또는 session 상태에 따른 login redirect로 처리된다.
- ADMIN dashboard 접근 가능.
- `/admin/users`로 USER/ADMIN 생성 가능.
- `/admin/users/{id}/role`로 USER를 ADMIN으로 승격 가능.
- `/admin/users/{id}/status`로 사용자를 비활성화 가능.
- USER는 자기 role을 ADMIN으로 변경 불가.
- schema validation, health/status/error contract, detector/masking/scoring/idempotency, unified Filter Rule API 테스트 통과.

Dashboard 테스트:

- ID/PW 로그인 성공.
- 세션 만료 시 login page 이동.
- overview에 total events, blocked, masked, warned, active users 표시.
- overview의 이벤트/사용자/기간 차트와 로그아웃 버튼 동작.
- events table이 detection category/type 표시.
- event detail panel/modal 표시.
- event detail에 version 식별자 UI 미표시.
- Business Context detail에서 matched configured keyword count 표시.
- raw prompt/full masked prompt/raw detected value/original filename 미표시.
- users page에 last event time 표시, hard delete 대신 disable 사용.
- user row에서 페이지네이션된 사용자별 이벤트 목록 표시.
- filters page에 source/kind/category 표시.
- built-in detector는 enabled/severity/action만 수정 가능.
- custom keyword/regex/context_rule CRUD 동작.
- context rule sensitivity low/medium/high 동작, scoring weights는 advanced setting.
- 위험 regex 저장 차단.
- dry-run sample 미저장, dry-run 결과는 safe metadata만 표시.
- status page에 API/PostgreSQL/Migration/Last Checked 표시, Version은 작게 표시 가능, Filter Config/Environment 기본 UI 미표시.

Privacy regression:

- DB schema scan: `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, raw detected value, original filename 컬럼 없음.
- Log scan: seeded prompt/file/secret 값이 로그에 없음.
- Error scan: validation/server error가 request body나 stack trace를 echo하지 않음.
- Dashboard scan: events/users/filters/status 화면이 raw prompt, file content, full masked prompt, raw detected value, original filename, prompt excerpt를 표시하지 않음.
- Business Context configured matched keyword와 count는 ADMIN event detail에 표시 가능.

### 15.2 MVP 완료 정의

MVP 완료는 아래 fresh-install 흐름이 끊기지 않고 통과하는 것이다.

1. 관리자가 Docker Compose 기본 구성으로 API와 PostgreSQL을 실행한다.
2. `/readyz`가 PostgreSQL 연결, migration 최신 상태, 기본 config/filter seed 준비 상태를 확인한다.
3. DB seed/migration이 기본 ADMIN `admin / 1234`를 생성하며 password는 hash로만 저장한다.
4. 기본 route는 login page를 연다.
5. ADMIN이 dashboard에 로그인한다.
6. ADMIN이 overview, events, users, filters, status 화면에 접근한다.
7. ADMIN이 `/admin/users`로 USER 또는 ADMIN을 생성한다.
8. USER는 extension에는 로그인할 수 있지만 dashboard route에는 접근할 수 없다.
9. Extension이 실제 self-host API의 `/auth/me`, `/config/extension`, `/prompts/analyze`를 호출한다.
10. ChatGPT composer에서 click/Enter 전송이 분석 완료 전 보류된다.
11. Allow/Warn/Mask/Block 결과가 계약된 UX로 동작한다.
12. Mask는 서버가 응답한 `masked_prompt`를 composer에 치환하고, 서버는 full `masked_prompt`를 저장하지 않는다.
13. Dashboard overview는 event/action/user/period metadata를 보여준다.
14. Event detail은 탐지 요약과 Business Context configured matched keyword count를 보여주되 raw source text를 표시하지 않는다.
15. Filter Rule Management는 unified Filter Rule 모델과 editable_fields를 지킨다.
16. API, dashboard, extension test, privacy regression, Docker fresh-install smoke, final demo scenario가 통과한다.

MVP 릴리즈 게이트:

| 게이트 | 완료 기준 | 실패 시 처리 |
| --- | --- | --- |
| 설치 | fresh clone/export에서 `.env.example` 기반 API/PostgreSQL 시작 | 설치 문서와 compose/env 수정 |
| DB | Alembic migration/seed가 fresh DB와 restart에서 성공 | feature 작업 전 migration 수정 |
| Auth | login/refresh/logout/auth/me/RBAC/default ADMIN seed 테스트 통과 | dashboard/extension 통합 보류 |
| Analyze | schema validation, detector, scoring, masking, idempotency, event metadata 통과 | dashboard stats/extension smoke 완료 불가 |
| Filters | unified `filter_rules`, `filter_rule_versions`, dry-run, editable_fields, regex safety 테스트 통과 | filter UI 완료 불가 |
| Dashboard | overview/events/users/filters/status가 metadata-only로 동작 | raw-data scan 실패 시 릴리즈 금지 |
| Extension | selector, click/Enter, 예외 처리, Allow/Warn/Mask/Block, 401 refresh, real API smoke 통과 | 실제 ChatGPT smoke 재검증 |
| Privacy | seeded sensitive value가 DB/log/error/dashboard/API response에 없음 | 릴리즈 금지 |
| Release gate | API/dashboard/extension build/test, Docker smoke, 외부 LLM 호출 없음, final demo 통과 | MVP 완료 표시 금지 |

### 15.3 테스트 명령 매트릭스

| 영역 | 명령 | 완료 기준 |
| --- | --- | --- |
| API unit/integration | `cd apps/api && pytest` | auth/RBAC/analyze/filter/status/error/privacy tests 통과 |
| API privacy scan | `cd apps/api && pytest tests/privacy` | seeded sensitive value가 DB/log/error response에 없음 |
| Dashboard | `cd apps/dashboard && npm run typecheck`, `npm run build`, `npm test`, built-output smoke | TypeScript source typecheck/build 통과, 생성 output이 login/overview/events/users/filters/status를 metadata-only로 렌더링 |
| Extension | `python apps/extension/tests/run_extension_checks.py all` | selector, hook, action UX, auth refresh, API client fixture 통과 |
| Root build | `npm run build --workspaces` | dashboard/extension JS build 통과, Python API는 pytest/compose로 검증 |
| Docker smoke | `docker compose up --build` 후 health check | `/livez`, `/readyz`, `/healthz`, login/analyze/dashboard smoke 통과 |
| Release gate | 각 영역 build/test + privacy regression + no external LLM verification | MVP 완료 가능 |

### 15.4 PM 실행 순서와 PR 묶음

| 순서 | PR 묶음 | 포함 WBS | 목적 | 완료 조건 |
| --- | --- | --- | --- | --- |
| P0-1 | Monorepo/API/Compose scaffold | 6-11 | `apps/api`, `apps/dashboard`, `infra`, PostgreSQL, settings, health skeleton | 기본 compose가 API+PostgreSQL 실행, health skeleton 통과 |
| P0-2 | Auth/default admin/RBAC | 12-27 | 기본 ADMIN seed, login/session auth, admin user management, RBAC | auth/RBAC/default admin tests 통과 |
| P0-3 | Metadata-only DB/event/idempotency | 28-33, 90-91 | Analyze schema, prompt hash, idempotency, event metadata, privacy DB/log scan | duplicate event 방지, 금지 컬럼/log scan 통과 |
| P0-4 | Core detectors/scoring/masking/filter rules | 34-56, 98 | PII/secret/business context, unified filter rules, merge, score, mask, corpus | detector/filter/scoring/masking tests 통과 |
| P0-5 | Extension real API integration | 57-73, 94-95 | extension 실제 API 연결 | real auth/config/analyze smoke 통과 |
| P0-6 | Dashboard MVP metadata UI | 74-89, 97 | login/overview/events/users/filters/status | metadata-only API/DOM privacy tests 통과 |
| P1-1 | Filter management hardening | 48-52, 87 | regex safety, dry-run, versions, context rule UX | ReDoS/privacy/filter integration 통과 |
| P1-2 | Release/docs/final smoke | 5, 99-102 | README/install/admin/privacy/release/demo | fresh install demo와 release gate 통과 |

### 15.5 최종 smoke/demo 시나리오

1. `docker compose up --build`로 API와 PostgreSQL을 시작한다.
2. `GET /livez`가 `200`을 반환한다.
3. `GET /readyz`가 DB 연결, migration 최신, 기본 filter/config 준비 상태로 `200`을 반환한다.
4. 기본 ADMIN `admin / 1234`가 존재하고 password가 hash-only인지 확인한다.
5. dashboard login page에서 ADMIN으로 로그인한다.
6. dashboard `/dashboard`, `/events`, `/users`, `/filters`, `/status` route가 열린다.
7. ADMIN이 `/admin/users`로 일반 USER를 만든다.
8. USER는 extension auth/config/analyze를 사용할 수 있지만 dashboard에는 접근할 수 없다.
9. Extension options에서 self-host API URL을 저장하고 `/auth/me`, `/config/extension`을 확인한다.
10. ChatGPT composer에 `NDA 위약금은 3억원입니다`를 입력하고 Warn 또는 Mask를 확인한다.
11. Event detail에서 Business Context matched keyword count가 표시되고 raw prompt가 표시되지 않는지 확인한다.
12. dummy secret fixture를 입력하고 Mask 또는 Block, raw submit 미발생을 확인한다.
13. Filter dry-run이 동작하고 sample text가 저장되지 않는지 확인한다.
14. Status page가 API/PostgreSQL/Migration/Last Checked를 표시한다.
15. DB/log/error/dashboard privacy scan과 외부 LLM 호출 없음 검증을 실행한다.

## 16. WBS 문서 순서 기준 작업표
아래 `문서 순서`는 이 v0.12 문서 안에서 읽기 쉽게 1부터 다시 매긴 번호다. 담당자와 예정일은 팀원 1명 제외 후 제공된 수정 WBS 배분표를 기준으로 반영한다. 영역, 분류, 항목, 기존 상세, 상태, 구현 지시는 기존 기술 내용을 해치지 않도록 유지한다.

상태 기준:

- `됨`: 현재 repo에서 실제 구현 또는 문서화가 확인됨.
- `부분`: 일부 구현/문서가 있으나 self-host MVP 완료 기준에는 부족함.
- `안됨`: 현재 repo에 해당 구현이 없음.
- `보류`: 현재 사용자 결정 또는 외부 의존성 없이는 구현 계약을 닫을 수 없음. 이미 확정된 Python/FastAPI/PostgreSQL/Redis optional 결정에는 쓰지 않는다.

각 WBS 행의 `v0.12 구현 지시`는 다음 다섯 가지를 포함하는 구현 티켓으로 읽는다.

- 구현된 조각: `부분` 상태인 행에서 현재 repo 기준으로 이미 확인된 코드, 테스트, 문서.
- 남은 구현: 현재 repo 기준으로 아직 만들어야 하는 코드, 테스트, 문서.
- 선행 작업: 시작 전에 필요한 API, schema, 화면, migration, fixture, 설정.
- 완료 PR 기준: 해당 항목을 완료로 바꿀 수 있는 observable output.
- 테스트/검증: 실행 명령, privacy/security scan, smoke, 또는 문서 검증.

`부분`은 하나의 모호한 작업으로 실행하지 않는다. 담당자 또는 AI agent가 해당 행을 구현하기 전에는 구현된 조각과 남은 구현을 먼저 분리하고, 남은 구현만 MVP slice로 계획한다.

| 문서 순서 | 단계 | 분류 | 항목 | 담당자 | 예정일 | 영역 | 기존 상세 | 현재 상태 | v0.12 구현 지시 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 준비/기획 | 범위확정 | 오픈소스 MVP 범위 확인 | 전체 | 2026-05-19 | 기획·QA·문서 | Self-host, 가입, 원문 미저장, 직접 필터 범위표 | 부분 | 구현된 조각: self-host, 관리자 기반 사용자 생성, 원문 미저장, 통합 Filter Rule 범위가 v0.12 계약에 반영됨. 남은 구현: README/install/admin/privacy 문서가 v0.12 MVP 범위와 일치하도록 정리. 선행 작업: v0.12 계약 확정. 완료 PR 기준: self-host, 가입, 원문 미저장, 직접 필터, 대시보드 범위가 문서와 repo 구조에서 같은 말로 설명됨. 테스트/검증: 문서 grep과 최종 demo scenario 체크리스트. |
| 2 | 준비/기획 | 우선순위 | P0/P1/P2 요구사항 재분류 | 전체 | 5-20(수) | 기획·QA·문서 | 필수·선택·후속 범위 정리표 | 부분 | 구현된 조각: v0.12 문서가 MVP/후속 구분의 기준 문서로 정리되고 WBS 행별 현재 상태를 보유한다. 남은 구현: MVP 필수, 선택, 후속 범위표를 이 WBS와 동기화. 선행 작업: API/dashboard/extension 범위 확정. 완료 PR 기준: 각 WBS 행이 MVP 포함/후속/선택 여부와 완료 기준을 가진다. 테스트/검증: 범위밖 기능이 MVP Done Definition에 섞이지 않는지 리뷰. |
| 3 | 준비/기획 | 사용자흐름 | 설치·가입·확장앱·대시보드 흐름 정리 | 김영은 | 5-20(수) | 대시보드·UI | Login→관리자 사용자 생성→Extension→Dashboard 흐름도 | 안됨 | 남은 구현: seed -> login/signup -> extension connection -> analyze -> dashboard metadata view 흐름도와 화면 skeleton. 선행 작업: auth/session API 계약. 완료 PR 기준: 대시보드 route와 빈/로딩/오류 상태가 흐름과 연결됨. 테스트/검증: login/dashboard smoke. |
| 4 | 준비/기획 | 구성결정 | Self-host 서버 구성 결정안 작성 | 유지수 | 5-24(일) | 서버·보안 | Docker, DB, Redis, reverse proxy 구성안 | 부분 | 구현된 조각: Python/FastAPI/PostgreSQL과 Redis optional 결정이 계약에 반영됐다. 남은 구현: Python/FastAPI/PostgreSQL 기본 구성과 Redis optional profile 문서/compose. 선행 작업: env schema와 health contract. 완료 PR 기준: 기본 compose가 Redis 없이 API+PostgreSQL을 시작하고 optional Redis는 disabled로 표시됨. 테스트/검증: Docker smoke, `/readyz`, `/healthz`. |
| 5 | 준비/기획 | 검증계획 | 테스트·릴리즈 게이트 목록 정리 | 전체 | 5-22(금) | 기획·QA·문서 | Install, E2E, privacy, security 테스트 목록 | 부분 | 구현된 조각: v0.12 문서가 privacy/security/E2E/release gate 범주와 demo checklist를 보유한다. 남은 구현: API/dashboard/extension/privacy/security/release gate를 구현 subplan과 CI 명령으로 연결. 선행 작업: 각 앱 scaffold와 테스트 runner. 완료 PR 기준: 모든 MVP slice가 완료 PR 기준과 테스트 명령을 가진다. 테스트/검증: `pytest`, dashboard test, extension checks, Docker smoke, privacy regression. |
| 6 | OSS·Seed·Auth | 저장소 | 모노레포 기본 구조 생성 | 김현성 | 5-22(금) | Chrome 확장 | apps/api, apps/dashboard, apps/extension, packages, docs, infra | 부분 | 구현된 조각: `apps/extension`과 API core용 `apps/api`가 존재한다. 남은 구현: dashboard/infra package 경계, root 실행 script, Python API와 JS workspace가 섞이지 않는 dev/build/test 진입점 정리. |
| 7 | OSS·Seed·Auth | 실행환경 | Docker Compose 실행 구성 | 유지수 | 5-24(일) | Chrome 확장 | API, dashboard, PostgreSQL, Redis compose 파일 | 부분 | 구현된 조각: `infra/docker-compose.yml`에 API+PostgreSQL 기본 구성과 선택 Redis profile이 추가됐다. 남은 구현: Dashboard service, PostgreSQL 연결 `/readyz`, migration smoke, Redis disabled 상태 문서화. |
| 8 | OSS·Seed·Auth | 환경변수 | .env.example 및 시작 검증 구현 | 전체 | 5-22(금) | 기획·QA·문서 | 필수 환경변수 검증과 dummy secret 파일 | 안됨 | Python config validation과 safe dummy secret 예시를 작성한다. |
| 9 | OSS·Seed·Auth | 빌드 | API·화면·확장앱 공통 빌드 스크립트 정리 | 김현성 | 5-23(토) | Chrome 확장 | dev/build/test script와 package 명령 | 부분 | 구현된 조각: extension/dashboard JS 명령은 각 앱 맥락에 존재한다. 남은 구현: Python API 명령과 JS workspace 명령을 분리한 root dev/build/test 진입점, CI에서 호출할 표준 명령, JS-only 서버 전제 제거. |
| 10 | OSS·Seed·Auth | 상태점검 | 서버 health check endpoint 구현 | 유지수 | 5-24(일) | 서버·보안 | /healthz 응답과 dependency 상태 | 부분 | 구현된 조각: `/livez`는 구현됐다. 남은 구현: `/readyz`, `/healthz`, DB/migration dependency status, dashboard-safe `/status/server`, 필수/선택 의존성 테스트. |
| 11 | OSS·Seed·Auth | 마이그레이션 | DB migration 실행 골격 작성 | 유지수 | 5-24(일) | 서버·보안 | fresh install·restart migration 검증 | 안됨 | SQLAlchemy 2.x + Alembic 기준으로 migration runner를 작성한다. |
| 12 | OSS·Seed·Auth | Seed/Auth | 기본 ADMIN seed readiness 확인 구현 | 김영은 | 5-24(일) | 서버·보안 | seed/readiness, needs_seed 응답 | 안됨 | Python API endpoint와 tests 작성. |
| 13 | OSS·Seed·Auth | Seed/Auth | 기본 ADMIN DB seed 구현 | 김영은 | 5-24(일) | 서버·보안 | workspace, 기본 ADMIN, default filter config 생성 | 안됨 | idempotent DB seed/migration과 안전한 audit metadata를 구현. 사용자 호출형 첫 관리자 API는 만들지 않는다. |
| 14 | OSS·Seed·Auth | Seed/Auth | seed idempotency와 audit 기록 구현 | 김영은 | 5-24(일) | 서버·보안 | seed lock, SETUP_COMPLETED audit | 안됨 | seed 실행 idempotency 제약과 audit metadata 구현. |
| 15 | OSS·Seed·Auth | 초기화면 | 로그인 화면 구현 | 김영은 | 5-25(월) | 대시보드·UI | login page와 ADMIN session 이동 | 안됨 | dashboard login page, session check, logout path, session-expired redirect 구현. |
| 16 | OSS·Seed·Auth | 설정seed | 기본 workspace·filter config·관리자 seed | 김영은 | 5-25(월) | 서버·보안 | INVITE_ONLY 기본값, default filter config version | 안됨 | fresh DB seed/migration으로 구현. |
| 17 | OSS·Seed·Auth | 계정DB | 사용자·초대·가입설정 테이블 작성 | 유지수 | 5-24(일) | 서버·보안 | users와 refresh token 테이블. MVP invite/registration 테이블은 후속 필요 시만 | 안됨 | PostgreSQL migration 작성. |
| 18 | OSS·Seed·Auth | 비밀번호 | 비밀번호 hash 저장 처리 | 유지수 | 5-24(일) | 서버·보안 | Argon2id/bcrypt 적용, 평문 미저장 테스트 | 안됨 | Argon2id 우선으로 구현하고, 운영 환경에서 비용 파라미터를 설정 가능하게 둔다. |
| 19 | OSS·Seed·Auth | 로그인 | 로그인·refresh·auth/me API 구현 | 유지수 | 5-24(일) | 서버·보안 | access/refresh token 발급과 사용자 정보 응답 | 부분 | 구현된 조각: `/auth/me` skeleton은 구현됐다. 남은 구현: 실제 login/refresh/logout, token 검증, refresh token raw 미저장, revocation/rotation tests, dashboard session 분리. |
| 20 | OSS·Seed·Auth | 토큰보호 | refresh token hash·만료·폐기 처리 | 유지수 | 5-27(수) | 서버·보안 | refresh_tokens 원문 미저장 검증 | 안됨 | token hash, expiry, revoke, rotation tests. |
| 21 | OSS·Seed·Auth | 권한 | ADMIN/USER 권한 middleware 구현 | 유지수 | 5-27(수) | 서버·보안 | Admin API USER 접근 403 테스트 | 안됨 | role guard와 403/404 규칙 적용. |
| 22 | OSS·Seed·Auth | 초대 | ADMIN 사용자 생성 API 구현 | 김현성 | 5-27(수) | 서버·보안 | POST /admin/users로 USER 또는 ADMIN 생성, 잘못된 role/input 거부 | 안됨 | POST /admin/users, password hashing, role validation, 안전 audit metadata 구현. |
| 23 | OSS·Seed·Auth | 초대관리 | 관리자 사용자 목록·상세 API 구현 | 김현성 | 5-27(수) | 서버·보안 | GET /admin/users 목록, 사용자 aggregate 필드, 안전 metadata만 반환 | 안됨 | ADMIN 전용 사용자 목록/상세 API와 안전 오류 처리 구현. |
| 24 | OSS·Seed·Auth | 가입방식 | self-signup route MVP 제외 처리 | 김현성 | 5-28(목) | 서버·보안 | self signup/invite signup/workspace-code/open signup route 부재 또는 비활성 확인 | 안됨 | MVP에서 지원하지 않는 registration route를 노출하지 않고, 필요 시 post-MVP로 문서화. |
| 25 | OSS·Seed·Auth | 사용자관리 | 사용자 상태·역할 변경 API 구현 | 김현성 | 5-29(금) | 서버·보안 | ACTIVE/DISABLED, USER/ADMIN 변경 | 안됨 | ADMIN user management API. |
| 26 | OSS·Seed·Auth | 인증검증 | 가입·로그인·권한 테스트 작성 | 유지수 | 5-29(금) | 기획·QA·문서 | auth/RBAC 통합 테스트 | 안됨 | pytest/API integration tests. |
| 27 | OSS·Seed·Auth | 보안설정 | CORS·rate limit 기본 규칙 적용 | 유지수 | 5-29(금) | 서버·보안 | 허용 origin, auth/analyze 요청 제한 | 안됨 | explicit CORS, in-process/Postgres rate limit first. |
| 28 | 분석/탐지 | 요청검증 | Analyze API 요청 schema 검증 | 김현성 | 5-29(금) | 서버·보안 | prompt/context/filter_config_version/client_request_id 검증 | 부분 | 구현된 조각: 현재 좁은 경계의 Pydantic schema, FastAPI route, OpenAPI 노출, route 테스트는 구현됐다. 남은 구현: 최종 MVP 계약을 typed `inputs[]`로 전환, 실제 auth/workspace context, DB-backed filter config context, validation error raw-free 회귀. |
| 29 | 분석/탐지 | 원문보호 | raw_prompt 저장 금지 처리 경계 구현 | 김현성 | 5-30(토) | 기획·QA·문서 | request body logging 차단과 redaction hook | 부분 | 구현된 조각: 안전 redaction helper, safe problem response, raw prompt 미반향 테스트는 구현됐다. 남은 구현: 실제 access/request/error logging 차단, privacy scan, DB/log 연동 테스트, clipboard/file raw-content leakage 검사, oversized/unsupported input error privacy. |
| 30 | 분석/탐지 | 중복처리 | client_request_id 중복 요청 처리 | 김현성 | 5-31(일) | 서버·보안 | idempotency 규칙과 중복 이벤트 방지 | 안됨 | PostgreSQL idempotency metadata, Mask recompute rule 구현. |
| 31 | 분석/탐지 | 해시 | HMAC prompt_hash 생성 구현 | 김현성 | 5-31(일) | 서버·보안 | workspace별 hash 분리와 secret 주입 | 부분 | 구현된 조각: workspace id를 입력으로 분리하는 HMAC helper, env 기반 secret 설정, route boundary 생성은 구현됐다. 남은 구현: 실제 auth workspace id, key id metadata, rotation policy, event persistence 연결, raw prompt를 저장 식별자로 쓰지 않는 회귀 테스트. |
| 32 | 분석/탐지 | 이벤트DB | 분석 이벤트·탐지 상세 테이블 작성 | 김영은 | 5-31(일) | 서버·보안 | raw_prompt, masked_prompt, value 금지 migration | 안됨 | metadata-only schema migration. |
| 33 | 분석/탐지 | 이벤트저장 | 원문 없는 이벤트 저장 서비스 구현 | 김영은 | 5-31(일) | 서버·보안 | user, service, detection_types, risk, action 저장 | 안됨 | event service and transaction boundary. |
| 34 | 분석/탐지 | 개인정보 | 이메일·전화번호 탐지 구현 | 유지수 | 5-31(일) | 서버·보안 | EMAIL/PHONE 탐지 함수와 단위 테스트 | 안됨 | deterministic detectors + corpus tests. |
| 35 | 분석/탐지 | 개인정보 | 주민등록번호 checksum 검증 구현 | 유지수 | 6-1(월) | 서버·보안 | 유효/무효 dummy RRN 테스트 | 안됨 | dummy-only checksum tests. |
| 36 | 분석/탐지 | 개인정보 | 카드번호 Luhn 검증 구현 | 유지수 | 6-1(월) | 서버·보안 | Luhn 유효 번호만 탐지 | 안됨 | Luhn test vectors. |
| 37 | 분석/탐지 | 한국현지화 | 사업자등록번호 후보·검증 구현 | 전체 | 6-1(월) | 기획·QA·문서 | 사업자번호 후보와 checksum 테스트 | 안됨 | Korean business number test corpus. |
| 38 | 분석/탐지 | 업무후보 | 금액·할인율·계약기간 후보 탐지 | 전체 | 6-1(월) | 기획·QA·문서 | 한국어 업무 문장 후보 테스트셋 | 안됨 | context evidence corpus. |
| 39 | 분석/탐지 | 비밀값 | GitHub·AWS key 탐지 구현 | 김영은 | 6-2(화) | 서버·보안 | ghp_, github_pat_, AKIA/ASIA 테스트 | 안됨 | secret detector tests. |
| 40 | 분석/탐지 | 비밀값 | JWT·개인키 block 탐지 구현 | 김영은 | 6-3(수) | 서버·보안 | JWT 3-part, PEM block 테스트 | 안됨 | JWT/PEM detector tests. |
| 41 | 분석/탐지 | 비밀값 | DB 접속 문자열 탐지 구현 | 김영은 | 6-3(수) | 서버·보안 | postgres/mysql/mongodb URI 탐지 | 안됨 | URI detector with redaction tests. |
| 42 | 분석/탐지 | 비밀값 | .env secret·고엔트로피 후보 탐지 | 김영은 | 6-3(수) | 서버·보안 | PASSWORD/SECRET key=value, entropy 테스트 | 안됨 | env and entropy detector. |
| 43 | 분석/탐지 | 규칙팩 | 한국 현지화 rule pack 구조 작성 | 김현성 | 6-3(수) | 기획·QA·문서 | rule_pack_version, label, severity 규격 | 안됨 | rule pack schema and fixtures. |
| 44 | 분석/탐지 | 문맥분류 | 계약정보 규칙 분류 구현 | 김현성 | 6-4(목) | 기획·QA·문서 | 계약금액, 위약금, NDA 문맥 테스트 | 부분 | 구현된 조각: 계약금액, 위약금, NDA helper와 단위 테스트는 구현됐다. 남은 구현: corpus 확장, false-positive/false-negative 평가, detector pipeline/scoring/action 연결, raw-free evidence metadata. |
| 45 | 분석/탐지 | 문맥분류 | 고객정보 규칙 분류 구현 | 전체 | 6-5(금) | 기획·QA·문서 | 고객사, 담당자, 문의 조합 테스트 | 안됨 | customer context classifier. |
| 46 | 분석/탐지 | 문맥분류 | 영업기밀·내부전략 규칙 분류 구현 | 김영은 | 6-5(금) | 기획·QA·문서 | 가격전략, 출시계획, 경쟁전략 테스트 | 안됨 | strategy context classifier. |
| 47 | 분석/탐지 | 문맥분류 | 낮은 신뢰도·애매한 문장 처리 | 김현성 | 6-5(금) | 기획·QA·문서 | AMBIGUOUS 처리와 강한 차단 제외 | 안됨 | ambiguous evidence scoring rule. |
| 48 | 분석/탐지 | 직접필터 | Filter Rule 테이블 작성 | 유지수 | 6-5(금) | 서버·보안 | filter_rules, versions migration | 안됨 | filter rule migrations. |
| 49 | 분석/탐지 | 직접필터 | 정규식·키워드 필터 API 구현 | 김현성 | 6-6(토) | 서버·보안 | 생성·수정·비활성화·조회 API | 안됨 | ADMIN CRUD with safe regex validation. |
| 50 | 분석/탐지 | 직접필터 | 위험 정규식 저장 전 검증 | 전체 | 6-6(토) | 기획·QA·문서 | 길이, syntax, 실행 timeout, ReDoS 방어 | 안됨 | ReDoS tests and safe-regex strategy. |
| 51 | 분석/탐지 | 직접필터 | 필터 dry-run API 구현 | 김영은 | 6-6(토) | 서버·보안 | 샘플 원문 미저장 테스트 | 안됨 | dry-run request-only, no persistence. |
| 52 | 분석/탐지 | 직접필터 | Filter Rule 분석 pipeline 연결 | 김현성 | 6-6(토) | 서버·보안 | filter_rule detection과 통계 metadata | 안됨 | detector pipeline integration. |
| 53 | 분석/탐지 | 병합 | 탐지 결과 overlap 병합 규칙 구현 | 김현성 | 6-6(토) | 서버·보안 | secret 우선, 긴 span 우선 테스트 | 부분 | 구현된 조각: secret 우선, 같은 우선순위에서 긴 span 우선 helper와 테스트는 구현됐다. 남은 구현: 전체 detector pipeline 연결, 중복 통계 제거 검증, PII/secret/filter-rule 혼합 overlap 회귀. |
| 54 | 분석/탐지 | 위험도 | 위험 점수·조치 결정 규칙 구현 | 전체 | 6-6(토) | 기획·QA·문서 | 0~100 점수, Allow/Warn/Mask/Block | 안됨 | deterministic scoring rules. |
| 55 | 분석/탐지 | 마스킹 | 개인정보·비밀값 placeholder 치환 | 유지수 | 6-7(일) | 서버·보안 | PII/API_KEY/DB URL 반복값 전체 치환 | 안됨 | server-side masking with no storage. |
| 56 | 분석/탐지 | 분석통합 | Analyze API 전체 흐름 통합 | 유지수 | 6-7(일) | 서버·보안 | detector→score→mask→log→response 통합 | 안됨 | orchestrator + integration tests. |
| 57 | 확장앱 | 뼈대 | Manifest V3 확장앱 scaffold 작성 | 김현성 | 6-7(일) | Chrome 확장 | content script, service worker, options 구조 | 됨 | 유지보수 및 real API adapter 연동만 남음. |
| 58 | 확장앱 | 서버연결 | Self-host API URL 입력 화면 구현 | 김현성 | 6-7(일) | Chrome 확장 | API base URL 저장과 연결 검증 | 부분 | 구현된 조각: mock/real 연결 UI와 `/auth/me` skeleton이 있다. 남은 구현: 실제 token 검증, 안전한 연결 오류 상태, end-to-end options smoke, config shape 변경 시 storage migration. |
| 59 | 확장앱 | 로그인 | 확장앱 로그인·토큰 저장 처리 | 김현성 | 6-7(일) | Chrome 확장 | token 저장, refresh, 로그아웃 동작 | 부분 | 구현된 조각: token 저장은 있다. 남은 구현: real refresh/logout 서버 연동, refresh-before-relogin 동작, token expiry 테스트, MV3 service worker inactive를 인증 만료로 취급하지 않는 회귀. |
| 60 | 확장앱 | 설정동기화 | 서버 selector·filter config 동기화 | 김현성 | 6-8(월) | Chrome 확장 | /config/extension 호출과 cache | 부분 | 구현된 조각: client/cache와 `/config/extension` skeleton이 있다. 남은 구현: DB-backed filter config/selector source, cache invalidation/version handling, real smoke, selector config 누락 시 safe fallback. |
| 61 | 확장앱 | 도메인 | ChatGPT 도메인 활성화 제한 | 김현성 | 6-8(월) | Chrome 확장 | 대상/비대상 도메인 동작 분리 | 됨 | ChatGPT-like selector regression 유지. |
| 62 | 확장앱 | 입력탐지 | textarea 입력창 탐지 구현 | 김현성 | 6-8(월) | Chrome 확장 | visible/focus 기준 후보 선택 | 됨 | DOM 변경 smoke 유지. |
| 63 | 확장앱 | 입력탐지 | contenteditable 입력창 탐지 구현 | 김현성 | 6-8(월) | Chrome 확장 | contenteditable fallback 탐지 | 됨 | real ChatGPT smoke 필요. |
| 64 | 확장앱 | 전송보류 | 전송 버튼 클릭 가로채기 | 김현성 | 6-9(화) | Chrome 확장 | 분석 완료 전 submit 보류 | 됨 | selector drift tests 유지. |
| 65 | 확장앱 | 전송보류 | Enter·단축키 전송 가로채기 | 김현성 | 6-10(수) | Chrome 확장 | Enter/Shift+Enter 분기 | 됨 | @ mention/GPT picker 예외 회귀 테스트 유지. |
| 66 | 확장앱 | API연동 | 분석 API client 구현 | 김현성 | 6-10(수) | Chrome 확장 | request body 생성, 401/timeout 처리 | 부분 | 구현된 조각: extension client와 `/auth/me`, `/config/extension`, `/prompts/analyze` route skeleton은 있다. 남은 구현: 실제 token 검증, DB-backed filter config, typed `inputs[]` request body, timeout/error privacy handling, end-to-end smoke. |
| 67 | 확장앱 | 중복방지 | 전송 허용 prompt 중복 전송 방지 | 김현성 | 6-10(수) | Chrome 확장 | allow hash, double-submit guard | 됨 | server idempotency와 별도 유지. |
| 68 | 확장앱 | 조치처리 | Allow 전송 재개 처리 | 김현성 | 6-10(수) | Chrome 확장 | 원래 전송 1회 재실행 | 됨 | real API smoke에서 확인. |
| 69 | 확장앱 | 조치처리 | Warn 경고 panel 구현 | 김현성 | 6-11(목) | Chrome 확장 | 확인 전 보류, 확인 후 전송 | 됨 | UX copy safe. |
| 70 | 확장앱 | 조치처리 | Mask panel과 선택 동작 구현 | 김현성 | 6-12(금) | Chrome 확장 | 마스킹 적용, 취소, 사유 요청 | 됨 | server-supplied mask와 smoke 필요. |
| 71 | 확장앱 | 마스킹 | 입력창 masked_prompt 치환 구현 | 김현성 | 6-12(금) | Chrome 확장 | textarea/contenteditable 치환 | 됨 | 자동 전송 금지 유지. |
| 72 | 확장앱 | 차단 | Block 안내와 원문 전송 차단 구현 | 김현성 | 6-12(금) | Chrome 확장 | 원문 submit 미발생 검증 | 됨 | fixture + real smoke 유지. |
| 73 | 확장앱 | 고지상태 | 저장/미저장 고지와 연결 상태 화면 | 김현성 | 6-12(금) | Chrome 확장 | notice, filter config sync time, server status | 부분 | 구현된 조각: extension-side status/notice surface는 부분 UI scaffold 수준이다. 남은 구현: server status endpoint 연동, last sync time, raw-storage notice 정확성, disconnected/degraded 상태, options UI smoke. |
| 74 | 대시보드/관리 | 화면뼈대 | Dashboard routing·layout 구성 | 김영은 | 6-13(토) | 대시보드·UI | 라우팅, auth guard, 공통 레이아웃 | 안됨 | dashboard scaffold 구현. |
| 75 | 대시보드/관리 | 로그인화면 | Seed·login 화면 연결 | 김영은 | 6-14(일) | 대시보드·UI | 기본 관리자 로그인, 로그인 화면 | 안됨 | auth API 이후 UI 구현. |
| 76 | 대시보드/관리 | 요약 | Overview summary API 연결 | 김영은 | 6-14(일) | 대시보드·UI | 기간별 totals, risk trend 데이터 연결 | 안됨 | MVP 필수. event/action/detector/user/period metadata summary API 필요. |
| 77 | 대시보드/관리 | 요약 | Overview 카드·추이 차트 구현 | 김영은 | 6-14(일) | 대시보드·UI | 이벤트, Warn, Mask, Block 카드 | 안됨 | MVP 필수. 이벤트별·사용자별·기간별 통계를 첫 화면에 표시한다. |
| 78 | 대시보드/관리 | 이벤트 | Risk Events 목록·필터 구현 | 김영은 | 6-14(일) | 대시보드·UI | 기간, 유형, action, risk 필터 | 안됨 | MVP 필수. 기간, 사용자, action, risk, detector, service/domain filter를 raw value 없이 구현. |
| 79 | 대시보드/관리 | 이벤트 | 원문 없는 이벤트 상세 구현 | 김영은 | 6-14(일) | 대시보드·UI | event_id, 유형, 점수, 탐지 요약을 표시하고 version 식별자는 표시하지 않음 | 안됨 | MVP 필수. safe metadata detail, matched keyword count, privacy UI tests 필요. |
| 80 | 대시보드/관리 | 사용자통계 | 사용자별 이벤트 통계 API 구현 | 유지수 | 6-15(월) | 서버·보안 | 사용자별 유형/횟수/action 분포 API | 안됨 | MVP 필수. 사용자별 aggregate API, 후속 drilldown API와 분리. |
| 81 | 대시보드/관리 | 사용자통계 | 사용자별 이벤트 표 구현 | 유지수 | 6-15(월) | 대시보드·UI | 사용자, 부서, top detection, 마지막 이벤트 | 안됨 | MVP 필수. 상위 사용자/사용자별 summary table. 상세 점검 페이지는 후속. |
| 82 | 대시보드/관리 | 사용자통계 | 사용자 action·탐지유형 차트 구현 | 유지수 | 6-15(월) | 대시보드·UI | stacked bar, detection heatmap 데이터 | 안됨 | MVP 필수. metadata-only chart; 개인 timeline/detail은 후속. |
| 83 | 대시보드/관리 | 사용자관리 | Users 관리 화면 구현 | 유지수 | 6-15(월) | 대시보드·UI | 목록, role/status 변경 | 안됨 | admin UI. |
| 84 | 대시보드/관리 | 가입관리 | Invites·Registration 화면 구현 | 유지수 | 6-16(화) | 대시보드·UI | 초대 생성/폐기, 관리자 기반 사용자 생성/role 지정 설정 | 안됨 | invite/registration UI. |
| 85 | 대시보드/관리 | 규칙 | Filter Rule 설정 요약을 Filter Rule 관리 화면에 통합 | 유지수 | 6-17(수) | 대시보드·UI | filter rule summary, detector override, retention metadata 표시 | 안됨 | 독립 설정 화면은 구현하지 않고 필요한 필터 설정 요약은 Filter Rule 관리 화면에 포함한다. |
| 86 | 대시보드/관리 | 통계 | 탐지 유형별 통계 화면 구현 | 유지수 | 6-17(수) | 대시보드·UI | detection type trend와 action count | 안됨 | metadata charts. |
| 87 | 대시보드/관리 | 직접필터 | Filter Rule 관리 화면 구현 | 유지수 | 6-17(수) | 대시보드·UI | 필터 목록, 생성, 수정, dry-run UI | 안됨 | filter rule APIs after server. |
| 88 | 대시보드/관리 | 상태 | 서버 health·degraded 상태 화면 | 유지수 | 6-17(수) | 대시보드·UI | API/DB/Redis 상태 표시 | 안됨 | Redis only when enabled. |
| 89 | 대시보드/관리 | 원문금지 | Dashboard 원문 미노출 화면 테스트 | 전체 | — | 기획·QA·문서 | raw_prompt, masked_prompt, detected value 미표시 검증 | 안됨 | MVP 필수. overview/event/user/status/filter rule 화면의 DOM/API response를 seeded sensitive value로 검사. |
| 90 | 통합·보안·문서 | Privacy | DB 원문 미저장 회귀 테스트 작성 | 전체 | — | 기획·QA·문서 | 금지 컬럼·seeded prompt DB scan | 안됨 | pytest/schema scan. |
| 91 | 통합·보안·문서 | Privacy | 로그 원문 미저장 회귀 테스트 작성 | 전체 | — | 기획·QA·문서 | application/access/error log seeded scan | 안됨 | log capture tests. |
| 92 | 통합·보안·문서 | Security | 외부 LLM 호출 금지 검증 작성 | 전체 | — | 기획·QA·문서 | network mock, outbound LLM 호출 0건 | 안됨 | no external LLM CI check. |
| 93 | 통합·보안·문서 | Security | seed·auth·RBAC 보안 테스트 작성 | 전체 | 6-20(토) | 기획·QA·문서 | 기본 ADMIN seed, USER 403, token 만료 | 안됨 | auth security tests. service worker inactive가 재로그인으로 이어지지 않고 refresh 실패 조건에서만 재로그인을 요구하는 회귀 테스트 포함. |
| 94 | 통합·보안·문서 | E2E | 확장앱 핵심 흐름 E2E 작성 | 전체 | 6-21(일) | Chrome 확장 | Allow/Warn/Mask/Block fixture 테스트 | 됨 | 현재 확장앱 테스트는 있음. 실제 API E2E는 서버 구현 뒤 필요. |
| 95 | 통합·보안·문서 | E2E | 선택자 변경 회귀 테스트 작성 | 전체 | 6-21(일) | Chrome 확장 | remote selector update fixture | 부분 | 구현된 조각: 확장앱 fixture는 있다. 남은 구현: 실제 config endpoint, remote selector update fixture, marker refresh와 연결된 rerender regression, 업데이트된 selector config 기반 end-to-end test. |
| 96 | 통합·보안·문서 | 통합 | Analyze API 통합·성능 테스트 | 전체 | 6-21(일) | 서버·보안 | happy/error path, p95 500ms 측정 | 안됨 | Python API performance tests. |
| 97 | 통합·보안·문서 | 통합 | Dashboard 통합·성능 테스트 | 전체 | 6-21(일) | 대시보드·UI | 30일 summary/user stats p95 측정 | 안됨 | dashboard/API 테스트 작성. |
| 98 | 통합·보안·문서 | 품질 | 한국어 FP/FN corpus 평가 | 전체 | 6-21(일) | 기획·QA·문서 | PII/secret/업무문맥 positive·negative 리포트 | 안됨 | corpus and report. |
| 99 | 통합·보안·문서 | 문서 | README·설치·reverse proxy 문서 작성 | 전체 | 6-22(월) | 기획·QA·문서 | README, install.md, HTTPS guide | 안됨 | after compose/API shape. |
| 100 | 통합·보안·문서 | 문서 | 관리자·privacy·기여 문서 작성 | 전체 | 6-22(월) | 기획·QA·문서 | admin-guide, privacy-design, contributing | 안됨 | 대시보드/API privacy 동작 확정 후 작성. |
| 101 | 통합·보안·문서 | 릴리즈 | Docker image·확장앱 패키지 빌드 | 전체 | 6-22(월) | Chrome 확장 | release artifact, sideload zip, version 확인 | 안됨 | 전체 MVP 완료 뒤 release plan 작성. |
| 102 | 통합·보안·문서 | 마감 | 최종 smoke test와 데모 시나리오 정리 | 전체 | 6-23(화) | 대시보드·UI | seed→관리자 기반 사용자 생성→Extension→Dashboard 데모 | 안됨 | 최종 end-to-end demo 작성. |
## 17. 담당자별 AI 작업 지시

이 섹션은 팀원 1명 제외 후 수정된 담당자 배분 기준으로 WBS 문서 순서 작업표를 다시 묶은 실행용 요약이다. 세부 항목의 원본 순서, 상태 판단, 예정일은 `16. WBS 문서 순서 기준 작업표`를 우선한다.

### 김현성

구현 범위: 모노레포/빌드 조정, 확장앱, 확장앱-API 경계, 제외된 팀원에게서 재배분된 ADMIN 기반 사용자 생성·사용자 관리 API, Analyze 요청 검증, 원문 보호, idempotency, HMAC hash, rule pack 및 계약정보 문맥 작업, 애매한 문장 처리, filter rule API/pipeline, overlap merge.

- 관련 WBS 행: 6, 9, 22-25, 28-31, 43, 44, 47, 49, 52, 53, 57-73.
- 예정 집중 구간: 5-22~6-12. 확장앱 구현은 6-7~6-12에 집중한다.
- 읽을 단원: `6. 인증·세션·권한 계약`, `7. API 경계와 상세 계약`, `10. 탐지·마스킹·점수·filter rule 계약`, `11. 확장앱 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 구현 위치: `apps/extension/*`, `apps/api/*`의 invites, user management, analyze/filter rule/idempotency/hash 관련 모듈, extension API adapter와 테스트.
- 선행 작업: Python API scaffold, auth context, PostgreSQL idempotency/event table, user table, OpenAPI 출력.
- 구현된 조각: extension DOM hook/hold/action handling, extension token storage, 부분 extension API client/config cache, 좁은 Analyze route/schema test, safe redaction/problem response helper, HMAC helper, contract-context helper, overlap merge helper.
- 남은 구현: typed `inputs[]` request body, 실제 self-host API smoke, real token 검증, DB-backed filter config, raw prompt/clipboard/file logging 차단, `client_request_id` 중복 처리, HMAC persistence 연결, 재배분된 invite/user management API, rule pack/AMBIGUOUS 처리, filter rule CRUD/pipeline, overlap merge pipeline 연결.
- 완료 PR 기준: 확장앱 DOM hook 회귀가 유지되고, 실제 `/auth/me`, `/config/extension`, `/prompts/analyze` 호출이 통과하며, 맡은 invite/user API가 auth/RBAC 테스트를 통과하고, raw prompt와 full masked prompt가 DB/log/error/dashboard에 남지 않는다.
- 테스트 방법: `python apps/extension/tests/run_extension_checks.py all`, `cd apps/api && pytest tests/analyze tests/privacy tests/filter_rules tests/auth`.

### 김영은

구현 범위: 사용자 흐름 문서, seed/seed/server seed, 제외된 팀원에게서 재배분된 event metadata DB/service, secret detector, 영업기밀·내부전략 classifier, filter rule dry-run, dashboard seed/overview/events 화면.

- 관련 WBS 행: 3, 12-16, 32, 33, 39-42, 46, 51, 74-79.
- 예정 집중 구간: 5-20~6-14. 대시보드 MVP 화면은 6-13~6-14에 집중한다.
- 읽을 단원: `8. 제품 범위와 저장소 구조`, `9. 데이터 모델·원문 저장 금지 계약`, `10. 탐지·마스킹·점수·filter rule 계약`, `12. 대시보드 계약`, `13. 보안·개인정보 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 구현 위치: `apps/api/*`의 seed/event/detector 모듈과 향후 `apps/dashboard/*`의 auth/overview/events 화면.
- 선행 작업: dashboard scaffold, PostgreSQL migration baseline, auth API, metadata-only event table, metadata-only summary/events API, session auth guard.
- 남은 구현: 사용자 흐름도, 기본 admin seed/readiness/audit, event metadata table/service, GitHub/AWS/JWT/PEM/DB URI/.env/entropy 탐지, 내부전략 context classifier, filter rule dry-run, login flow, overview 카드·추이 차트, events 목록·필터·상세.
- 완료 PR 기준: login-first flow와 event metadata 저장이 raw storage 없이 동작하고, 대시보드는 metadata-only로 동작하며, overview는 이벤트별·사용자별·기간별 통계를 보여주고, events 상세는 원문·full masked prompt·원문 탐지값·원본 파일명·version 식별자를 표시하지 않는다.
- 테스트 방법: `cd apps/api && pytest tests/seed tests/events tests/detectors tests/filter_rules tests/privacy`, `cd apps/dashboard && npm test`.

### 유지수

구현 범위: Python API foundation, Docker/PostgreSQL, migration, auth/RBAC, CORS/rate limit, PII/localized detector, server-side masking, Analyze orchestrator, user statistics API, 제외된 팀원에게서 재배분된 dashboard management/status 화면.

- 관련 WBS 행: 4, 7, 10, 11, 17-21, 26, 27, 34-36, 48, 55, 56, 80-88.
- 예정 집중 구간: 5-24~6-17. 대시보드 관리/status 작업은 6-15~6-17에 집중한다.
- 읽을 단원: `3. 서버·실행환경·인프라 계약`, `4. 상태 확인 계약`, `5. HTTP 오류 계약`, `6. 인증·세션·권한 계약`, `7. API 경계와 상세 계약`, `9. 데이터 모델·원문 저장 금지 계약`, `10. 탐지·마스킹·점수·filter rule 계약`, `12. 대시보드 계약`.
- 구현 위치: `apps/api/*`, `infra/compose.yaml`, `.env.example`, Alembic migration, detector/masking/orchestrator modules, 향후 `apps/dashboard/*`의 users/filter rule/status 화면.
- 선행 작업: repository scaffold, API dependency seed, PostgreSQL connection, settings loader, migration baseline, auth/session API.
- 남은 구현: compose/runtime 결정 작업, `/livez`, `/readyz`, `/healthz`, migration skeleton, account/auth/RBAC/token protection, CORS/rate limit, PII/localized detectors, filter rule table, masking, Analyze orchestrator, user stats API, user stats UI, users/filter rule/status 화면.
- 완료 PR 기준: Redis 없이 default Compose가 API/PostgreSQL을 시작하고, health/status/auth/detector/masking/analyze/user stats 테스트가 통과하며, 재배분된 dashboard management/status 화면이 metadata-only와 RBAC 기준을 지킨다.
- 테스트 방법: `cd apps/api && pytest`, Docker smoke 이후 `/livez`, `/readyz`, `/healthz`, login/analyze/dashboard summary smoke, `cd apps/dashboard && npm test`.

### 전체

구현 범위: 공통 기획, 환경변수 검증, 한국 사업자번호·업무문맥 corpus 작업, custom regex safety, risk scoring, raw-source non-exposure test, privacy/security/E2E/performance test, release 문서, packaging, final demo.

- 관련 WBS 행: 1, 2, 5, 8, 37, 38, 45, 50, 54, 89-102.
- 예정 집중 구간: 5-19~6-23. 통합·문서·릴리즈·최종 데모는 6-20~6-23에 집중한다.
- 읽을 단원: `13. 보안·개인정보 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 남은 구현: 범위/우선순위 정렬, `.env.example`, 사업자등록번호 및 업무조건 detector/corpus, 고객정보 rule, custom regex ReDoS 방어, scoring rules, dashboard raw-source non-exposure test, DB/log/error privacy scan, external LLM call prohibition verification, API/dashboard/extension integration/performance tests, Korean FP/FN corpus, README/install/admin/privacy/contributing docs, release artifact, final smoke/demo.
- 완료 PR 기준: API, dashboard, extension build/test, privacy regression, no external LLM verification, Docker fresh-install smoke, seed -> user -> extension -> analyze -> dashboard demo가 모두 통과한다.
- 테스트 방법: 각 영역 test command, privacy regression, Docker smoke, final demo scenario.
