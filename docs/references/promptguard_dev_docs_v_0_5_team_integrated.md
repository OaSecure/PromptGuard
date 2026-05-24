# PromptGuard 개발 문서 세트 v0.5 - 팀 통합본

## 1. 문서 사용 규칙과 현재 구현 상태
- 서버 언어는 Python으로 간다.
- PostgreSQL은 그대로 쓴다.
- Redis는 MVP 기본 필수가 아니다. 로그인 유지, 갱신 토큰, 중복 요청 처리의 영속 기준은 PostgreSQL이 맡는다.
- 확장앱 mock/client가 있다고 해서 자가 호스팅 Analyze API가 구현된 것이 아니다.
- 원문 프롬프트, 원문 파일 내용, `masked_prompt`, 원문 탐지값, 원본 파일명, 비밀값/토큰, 스택 추적은 저장, 로그, 대시보드, 오류 응답, 메모리/세션 로그에 남기지 않는다.
- WBS의 담당자, 영역, 분류, 항목, 상세 내용은 유지하고 구현 가능한 작업 단위로 풀어쓴다.
- PromptGuard 개발 계약, 구현 상태, API 경계, 데이터 소유권, 작업 지시는 이 v5 문서 하나를 기준으로 한다.
- WBS 원본 XLSX/CSV는 범위, 순서, 담당자, 영역을 확인하는 별도 원본으로만 남긴다.

### 1.1 현재 구현 상태 요약

- 확장앱의 ChatGPT 입력 탐지, 전송 보류, Allow/Warn/Mask/Block UX, selector fixture, double-submit guard는 주요 흐름이 구현되어 있다.
- 확장앱은 현재 mock/fake backend와 client fixture로 검증된 부분이 있으며, 실제 self-host API 서버와의 end-to-end smoke는 서버 구현 뒤 완료한다.
- Python self-host API, PostgreSQL migration, dashboard, Docker Compose 기본 실행, 관리자 setup/auth, event metadata 저장, 대시보드 통계 API는 아직 구현 대상이다.
- WBS 작업표의 `됨`, `부분`, `안됨`은 현재 repo 기준 구현 상태를 뜻한다. `부분`은 client, fixture, 문서, 또는 일부 UI가 있지만 실제 서버/API/DB/통합 검증이 남은 상태다.
- 영어 번역본은 AI 작업 보조 문서이며, 한국어 원본의 구조와 내용이 확정된 뒤 같은 단원 구조로 맞춘다.

## 2. 확정 결정

- 서버 언어: Python.
  - 이유: 탐지기, 규칙 분류기, 마스킹, 개인정보 회귀 테스트, 향후 로컬 자연어 처리/머신러닝 확장에 Python 생태계가 유리하다. 팀원과 AI 개발 에이전트가 읽고 구현하기 쉽고, OpenAPI 기반으로 확장앱과 대시보드가 언어 중립 계약을 공유할 수 있다.
- 데이터베이스: PostgreSQL.
  - 이유: 사용자, 워크스페이스, 정책, 사용자 정의 필터, 이벤트 메타데이터, 중복 요청 처리, 토큰 해시는 영속 트랜잭션과 마이그레이션이 필요한 상태다.
- Chrome 확장앱: Manifest V3 + TypeScript.
  - 이유: 현재 확장앱 구현이 이 전제 위에 있다.
- 대시보드: 원문 없는 관리자 UI.
  - 이유: 대시보드가 원문 검토 도구가 되면 제품의 개인정보 보호 중심 설계 목적과 충돌한다.
- API 계약 원천: `apps/api`의 FastAPI/Pydantic/OpenAPI 출력이 원천이다.
  - 이유: Python API가 요청/응답 스키마를 소유하고 OpenAPI를 생성한다. 확장앱/대시보드는 그 OpenAPI에서 생성한 client/type 또는 얇은 어댑터를 소비한다.
- 서버 구현 스택: FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic.
  - 이유: Python API, 요청/응답 검증, OpenAPI 생성, PostgreSQL migration을 한 흐름으로 구현하기 쉽다.
- Redis: 선택 구성.
  - 이유: 기본 MVP의 로그인 유지, refresh token, idempotency, 이벤트 저장은 PostgreSQL로 처리한다. Redis는 다중 인스턴스 rate limit, 분산 lock, queue/cache가 실제로 필요할 때만 선택 profile로 추가한다.

## 3. 서버·실행환경·인프라 계약
아래 기준을 서버·실행환경 구현 기준으로 사용한다. 단, FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, 03A/03B 분리는 "일반적이고 유지보수하기 쉽고 개발이 빠르다"는 전제에서 확정한다. 구현 중 이 전제가 깨지는 근거가 나오면 코드로 고정하지 말고 사용자에게 다시 확인한다.

1. Python 웹 프레임워크는 FastAPI로 구현한다.
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
| `GET /readyz` | 트래픽을 받아도 되는지 확인 | 내부 권장 | 설정 유효, DB 연결 가능, 마이그레이션 최신, 기본 정책 로드 가능이면 `200`; 핵심 의존성이 불가하면 `503` |
| `GET /healthz` | 대시보드/운영자용 집계 상태 | 내부 또는 ADMIN 권장 | 핵심 기능 가능하면 `200`; 선택 의존성만 문제면 body `status=degraded`와 함께 `200`; 핵심 의존성 불가면 `503` |
| `GET /status/server` | 대시보드가 쓰는 원문 없는 상태 API | ADMIN | `/healthz`와 같은 안전 메타데이터를 인증된 대시보드 형식으로 반환 |

상태 확인은 UI 기능이라기보다 자가 호스팅 운영 MVP의 일부다. Docker Compose와 새 설치 요구사항은 `/healthz` 같은 준비 상태 확인 없이는 검증하기 어렵다.

### 4.2 상태 응답 형식

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

허용되는 최상위 상태:

- `healthy`: 필수 의존성을 사용할 수 있다.
- `degraded`: 필수 의존성은 사용할 수 있지만 선택 기능 또는 비핵심 기능에 문제가 있다.
- `unhealthy`: 필수 의존성, 설정, 마이그레이션, 정책 상태가 정상 서비스를 막는다.

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

### 5.2 상태 코드 정책

| 상태 | PromptGuard에서 쓰는 경우 | 이 경우에는 쓰지 않음 |
| --- | --- | --- |
| `400 Bad Request` | JSON 형식 오류, 필수 최상위 구조 누락, 스키마 파싱 실패 | 인증됐지만 권한이 없는 사용자 |
| `401 Unauthorized` | access token이 없거나, 유효하지 않거나, 만료됐거나, 형식이 잘못됨 | 유효한 토큰이 있지만 역할 권한이 부족한 경우 |
| `403 Forbidden` | 인증된 사용자의 권한 부족, 비활성 사용자, USER가 ADMIN route 호출 | cross-workspace resource 존재 자체를 숨겨야 하는 경우 |
| `404 Not Found` | route/resource 없음, 또는 금지된 cross-workspace resource 존재를 의도적으로 숨김 | 일반 인증 실패 |
| `409 Conflict` | 중복 요청 충돌, setup 완료 후 재시도, 현재 상태 때문에 처리할 수 없는 오래된 policy/version 충돌 | 일반 검증 오류 |
| `413 Payload Too Large` | 프롬프트/파일/request body가 설정된 크기 제한 초과 | 탐지 결과가 Block인 경우 |
| `415 Unsupported Media Type` | 지원하지 않는 content type 또는 파일 형식 | 의미 검증 오류 |
| `422 Unprocessable Content` | 문법적으로는 유효하지만 업무 의미가 잘못됨. 예: 잘못된 custom regex, 불가능한 정책 전환, 지원하지 않는 rule 표현식 | JSON 형식 오류 |
| `428 Precondition Required` | 향후 policy/version precondition이 필수인데 누락된 요청에 선택적으로 사용 | `409`가 더 잘 맞는 일반 정책 불일치 |
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

이 단원은 확장앱 bearer token 흐름과 대시보드 session cookie 흐름을 분리해서 정의한다. 확장앱 service worker inactive 상태는 인증 만료가 아니며, 대시보드는 서버 관리 session과 CSRF 방어를 사용한다.

### 6.1 식별자와 인증
- `workspace_id`와 `user_id`는 request body가 아니라 인증 토큰/세션 context에서 온다.
- access token은 짧은 수명으로 둘 수 있다.
- refresh token 원문 값은 절대 저장하지 않고 PostgreSQL에는 hash와 metadata만 저장한다.
- Chrome Extension의 MV3 service worker inactive 상태는 인증 만료가 아니다.
- 확장앱은 worker wake-up 시 저장된 auth/session metadata를 읽고, access token이 만료됐으면 사용자에게 재로그인을 요구하기 전에 `POST /auth/refresh`를 먼저 시도한다.
- refresh token이 유효하면 서버는 새 access token을 발급한다. refresh token rotation을 쓰는 경우 새 refresh token도 같이 발급하고 이전 refresh token hash는 폐기한다.
- 재로그인을 요구하는 경우는 refresh token 만료, 폐기, 재사용 탐지, 형식 오류, 서버 거부, 명시적 logout, 계정 비활성, 서버 URL 또는 workspace 변경으로 제한한다.
- 비활성 사용자는 보호 route 실행 전에 차단한다.
- ADMIN 전용 route에 인증된 USER 계정이 접근하면 `403`을 반환한다.
- 대시보드 세션 인증은 확장앱 bearer token 인증과 분리한다.
  - Dashboard session은 서버가 관리하는 session id를 `HttpOnly` cookie로 전달한다.
  - HTTPS 환경의 session cookie는 `Secure`를 사용한다.
  - Same-site 관리자 UI 기본값은 `SameSite=Lax`로 시작하고, cross-site embedding이 필요하지 않으면 `Strict`를 검토한다.
  - 대시보드 session id는 `localStorage`에 저장하지 않는다.
  - 대시보드의 상태 변경 요청은 CSRF 방어를 적용한다. 기본 방향은 SameSite cookie와 CSRF token 조합이며, 구현 시 double-submit 또는 synchronizer token 중 하나를 선택한다.
  - session idle timeout, absolute timeout, logout, 계정 비활성, 권한 변경, 위험 이벤트 후 재인증 정책을 서버에서 관리한다.
  - 이 기준은 OWASP Session Management Cheat Sheet와 OWASP Cross-Site Request Forgery Prevention Cheat Sheet의 cookie/session/CSRF 권고를 따른다.

### 6.2 인증·세션·권한 상세 계약
기본 TTL은 운영자가 환경변수로 바꿀 수 있다. 기본값은 MVP의 유지보수와 확장앱 UX를 위해 다음으로 둔다.

| 항목 | 기본값 | 이유 |
| --- | --- | --- |
| access token TTL | 900초 | 탈취 피해를 줄이되 refresh로 UX 유지 |
| refresh token TTL | 30일 | MV3 inactive와 장기 비활성 브라우저 사용을 로그아웃으로 오판하지 않기 위함 |
| refresh idle timeout | 14일 | 오래 방치된 세션을 정리하되 일반 확장앱 사용을 방해하지 않음 |
| refresh rotation | enabled | refresh 성공 시 새 refresh token 발급, 이전 token hash 폐기 |
| refresh reuse detection | enabled | 폐기된 refresh token 재사용 시 해당 token family 폐기 후 재로그인 요구 |

Chrome Extension의 MV3 service worker inactive 상태는 인증 만료가 아니다. 확장앱은 worker wake-up 후 저장된 auth/session metadata를 읽고, access token이 만료됐으면 `POST /auth/refresh`를 먼저 시도한다. 사용자에게 재로그인을 요구하는 경우는 refresh token 만료, 폐기, 재사용 탐지, 형식 오류, 서버 거부, 명시적 logout, 계정 비활성, 서버 URL 변경, workspace 변경으로 제한한다.

role/permission 권한 매트릭스:

| Surface | Public | USER | ADMIN |
| --- | --- | --- | --- |
| `/setup/status` | 가능 | 가능 | 가능 |
| `/setup/bootstrap` | setup_required일 때만 가능 | 불가 | setup 완료 후 불가 |
| `/auth/register`, `/auth/login` | 가능 | 가능 | 가능 |
| `/auth/refresh`, `/auth/logout`, `/auth/me` | 불가 | 확장앱 token 흐름에서 자기 계정 가능 | 확장앱 token 흐름에서 자기 계정 가능 |
| `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me`, `/dashboard/session/csrf` | login/csrf 가능 | USER는 dashboard 진입 불가 | ADMIN dashboard session 가능 |
| `/config/extension` | 불가 | 가능 | 가능 |
| `/prompts/analyze`, `/files/analyze` | 불가 | 가능 | 가능 |
| `/events`, `/stats/*`, `/status/server` | 불가 | 불가, `403` | 가능 |
| `/users`, `/invites`, `/policies`, `/custom-filters` | 불가 | 불가, `403` | 가능 |
| cross-workspace resource | 불가 | 존재 숨김 `404` | 존재 숨김 `404` |

계정 상태:

- `ACTIVE`: 보호 route 사용 가능.
- `DISABLED`: access/refresh 모두 거부. 보호 route는 `403`, 존재 숨김이 필요한 tenant resource는 `404`.
- `PENDING_INVITE`: login 불가.
- `DELETED`: MVP에서는 hard delete 대신 disabled/anonymized metadata로 처리한다.

### 6.3 확장앱 token auth와 대시보드 session auth 분리

두 인증 흐름은 같은 사용자/role/status 모델을 공유하지만 transport와 저장 위치가 다르다. 구현자는 두 흐름을 같은 완료로 보면 안 된다.

| 구분 | 확장앱 인증 | 대시보드 인증 |
| --- | --- | --- |
| 주요 client | Chrome Extension service worker/options | Dashboard web app |
| 로그인 endpoint | `POST /auth/login` | `POST /dashboard/session/login` |
| 상태 확인 | `GET /auth/me` | `GET /dashboard/session/me` |
| 갱신 | `POST /auth/refresh` | server-managed session renewal 또는 재로그인 |
| 로그아웃 | `POST /auth/logout` | `POST /dashboard/session/logout` |
| credential 저장 | extension storage에 access/refresh metadata | browser cookie jar의 `HttpOnly` session cookie |
| CSRF | bearer token API에는 기본적으로 적용하지 않음 | state-changing dashboard request는 CSRF token 필수 |
| 실패 시 UX | options/status UI에서 재로그인 요구 | `/login`으로 이동 또는 session expired banner |

대시보드 session endpoint 계약:

| Endpoint | Auth | 목적 | 응답 핵심 |
| --- | --- | --- | --- |
| `GET /dashboard/session/csrf` | public | login form과 state-changing request에 쓸 CSRF token 발급 | `csrf_token`, `expires_at` |
| `POST /dashboard/session/login` | public + CSRF | ADMIN dashboard session 생성 | `user`, `workspace`, `expires_at`; session id는 cookie로만 전달 |
| `GET /dashboard/session/me` | ADMIN session | 현재 dashboard session 확인 | `user`, `workspace`, `role`, `status`, `expires_at` |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | dashboard session 폐기 | `revoked=true` |

`POST /auth/login`은 확장앱 token login을 위한 endpoint다. 대시보드는 이 endpoint를 직접 사용하지 않는다. 대시보드가 bearer token을 localStorage에 저장하는 구현은 MVP 계약 위반이다.

## 7. API 경계와 상세 계약

이 단원은 API별 책임 경계와 상세 request/response 계약을 함께 둔다. `apps/api`의 FastAPI/Pydantic/OpenAPI 출력이 구현 시 최종 계약 원천이며, 확장앱과 대시보드는 해당 OpenAPI를 소비한다.

### 7.1 프롬프트 분석 경계
엔드포인트: `POST /prompts/analyze`

서버가 맡는 책임:

- request schema 검증
- 인증된 workspace/user context
- 메모리 안에서만 수행하는 prompt 정규화
- detector pipeline
- 위험 점수 계산
- 조치 결정
- `masked_prompt` 생성
- 원문 없는 event metadata 기록
- HMAC `prompt_hash`
- 중복 요청 처리
- 안전한 오류 응답

확장앱이 맡는 책임:

- DOM 입력 추출
- 전송 전 보류
- request body 생성
- timeout 처리
- Allow/Warn/Mask/Block UX
- 서버가 준 `masked_prompt` 적용
- 허용된 경우에만 보호된 재전송 수행

요청에 포함해야 하는 값:

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

요청에 포함하면 안 되는 값:

- `user_id`
- `workspace_id`
- 전체 page URL path/query
- 원본 파일명
- 어떤 ID 필드에도 비밀값을 넣으면 안 됨

응답에 포함해야 하는 값:

- `event_id`
- `request_id`
- `risk_score`
- `risk_level`
- `action`
- 안전 문구인 `user_message`
- `allow_original_send`
- `requires_justification`
- metadata summary만 담은 `detections[]`
- `policy.version`
- `policy.latest_version`
- `action=Mask`일 때만 선택적으로 포함하는 `masked_prompt`
- 선택적 `partial_result`

응답에 포함하면 안 되는 값:

- 원문 프롬프트 echo
- 원문 탐지값
- 내부 detector stack trace
- 임의로 throw된 exception text
- event/dashboard API에 영속 저장된 전체 masked prompt

### 7.2 파일 분석 경계
엔드포인트: `POST /files/analyze`

MVP 파일 범위는 텍스트 계열 파일로 제한한다. PDF, Office 문서, OCR, 압축 해제, malware scanning, binary analysis는 이후 계획에서 추가하지 않는 한 MVP 밖이다.

확장앱은 지원되는 텍스트 파일을 메모리에서 읽어 request를 만들 수 있다. 서버는 파일 내용을 prompt text와 같은 방식으로 취급한다. 즉 요청 처리 중에만 쓰는 일시 입력이며, 저장하지 않고, 로그에 남기지 않고, 대시보드에 표시하지 않는다.

### 7.3 확장앱 설정 경계
엔드포인트: `GET /config/extension`

반환값:

- `api_base_url`
- `policy_version`
- `timeout_ms`
- `ai_service_configs[]`
- `file_upload` policy
- ChatGPT 계열 화면용 selector config

확장앱은 서버 selector를 우선 사용하고, 장애 대응을 위해 fallback selector를 유지한다.

### 7.4 API 서버 구현 범위
- 실행 기반:
  - Docker Compose 기본 구성은 `api + postgres`다.
  - Redis는 기본 구성이 아니며, 다중 인스턴스 rate limit, 분산 lock, queue/cache가 실제로 필요할 때 선택 profile로 추가한다.
  - `.env.example`은 개발용 dummy 값을 제공하되, 실제 secret처럼 보이는 값을 넣지 않는다.
- 설정:
  - 서버 시작 시 필수 환경변수를 검증한다.
  - DB URL, HMAC secret, JWT secret, cookie secret, CORS origin, file size limit, request size limit, rate limit 값을 명시한다.
  - 설정 오류는 안전한 메시지로 실패하고 secret value를 출력하지 않는다.
- Setup/Auth:
  - `GET /setup/status`: workspace/admin bootstrap 필요 여부와 safe metadata 반환.
  - `POST /setup/bootstrap`: 첫 workspace와 첫 ADMIN을 transaction으로 생성하고 1회만 허용.
  - `POST /auth/register`: invite 또는 registration setting 기준으로 USER 생성.
  - `POST /auth/login`: 확장앱용 access token과 refresh token 발급.
  - `POST /auth/refresh`: refresh token raw value를 저장하지 않고 hash 검증으로 재발급.
  - `POST /auth/logout`: refresh token 폐기.
  - `GET /auth/me`: 확장앱이 현재 사용자와 workspace를 확인.
  - `POST /dashboard/session/login`: 대시보드용 server-managed session cookie 생성.
  - `GET /dashboard/session/me`: 대시보드가 현재 ADMIN session을 확인.
  - `GET /dashboard/session/csrf`: 대시보드 상태 변경 요청용 CSRF token 발급.
  - `POST /dashboard/session/logout`: 대시보드 session 폐기.
- 권한:
  - USER는 확장앱 사용과 자기 상태 조회 중심이다.
  - ADMIN은 setup 이후 invite, user, policy, filter, dashboard metadata에 접근한다.
  - disabled user는 보호 route 실행 전에 차단한다.
- Analyze:
  - `POST /prompts/analyze`: request validation, detector, scoring, masking, event metadata 저장, response 생성.
  - `POST /files/analyze`: 텍스트 파일만 일시 입력으로 분석하고 원문 파일 내용은 저장하지 않는다.
  - `client_request_id`는 workspace/user/request fingerprint와 함께 중복 요청 처리 기준이 된다.
- 관리자 API:
  - `/invites`, `/users`, `/policies`, `/custom-filters`, `/events`, `/stats/users`, `/stats/detections`, `/status/server`는 모두 원문 없는 metadata API여야 한다.

### 7.5 API 상세 계약 부록
이 부록은 구현 전 최소 계약이다. 실제 서버는 FastAPI/Pydantic으로 OpenAPI를 생성하고, extension/dashboard는 생성 타입 또는 얇은 adapter로 맞춘다. 모든 오류는 `application/problem+json` 형식을 따른다.

API 계약 작성 형식:

각 endpoint는 문서와 OpenAPI에서 같은 의미를 가져야 한다. Markdown 문서는 사람이 읽는 설명이고, FastAPI/Pydantic/OpenAPI 출력이 기계가 소비하는 최종 schema다. 문서에는 endpoint마다 아래 항목을 둔다.

1. 목적.
2. 인증과 권한.
3. 요청 `Content-Type`.
4. 요청 필드 표.
5. 요청 JSON 예시.
6. 성공 응답 필드 표.
7. 성공 JSON 예시.
8. 오류 JSON 예시.
9. 저장, 로그, 대시보드 노출 금지 필드.
10. 테스트 기준.

MVP payload 형식:

- 일반 API 요청과 응답은 `application/json`을 사용한다.
- 오류 응답은 `application/problem+json`을 사용한다.
- `POST /files/analyze`도 MVP에서는 확장앱이 텍스트 파일을 읽어 JSON body로 보내는 방식을 사용한다.
- `multipart/form-data`는 PDF, Office, 대용량 파일, binary upload를 다루는 후속 범위에서 다시 검토한다.
- JSON 예시는 구현자가 payload 감각을 잡기 위한 샘플이며, 필드의 필수 여부와 저장 가능 여부는 필드 표를 우선한다.

공통 규칙:

- 인증된 route의 `workspace_id`, `user_id`, `role`, `status`는 token/session context에서 온다.
- request body에 `workspace_id`나 `user_id`를 넣지 않는다.
- 모든 list API는 `limit`, `cursor`를 사용한다. 기본 `limit=50`, 최대 `limit=200`.
- 시간은 저장과 API 기준 모두 UTC ISO-8601이다. Dashboard는 표시할 때만 browser timezone으로 변환한다.
- `request_id`는 서버가 만든다. `client_request_id`는 extension/dashboard가 보내는 idempotency key다.

| Endpoint | Auth | Request 핵심 | Response 핵심 | 주요 오류 |
| --- | --- | --- | --- | --- |
| `GET /setup/status` | public/internal | 없음 | `setup_required`, `workspace_exists`, `admin_exists`, `registration_mode` | `503` DB/migration 미준비 |
| `POST /setup/bootstrap` | public when setup_required | admin email/password/display_name, workspace name | workspace metadata, admin metadata, tokens, audit event id | `409` 이미 완료, `422` 약한 입력 |
| `POST /auth/register` | public by registration mode | email/password/display_name/invite_code 또는 workspace_code | user metadata, tokens | `401/403/404/409/422` |
| `POST /auth/login` | public | email/password | extension access token, refresh token, user/workspace metadata | `401`, `403` disabled |
| `POST /auth/refresh` | refresh token | refresh token raw value in request only | new access token, optional rotated refresh token | `401` invalid/expired, `409` reuse detected |
| `POST /auth/logout` | user | refresh token 또는 current session id | `revoked=true` | `401` |
| `GET /auth/me` | user bearer | 없음 | extension user/workspace/role/status metadata | `401`, `403` disabled |
| `GET /dashboard/session/csrf` | public/session | 없음 | CSRF token metadata | `503` |
| `POST /dashboard/session/login` | public + CSRF | email/password | ADMIN session cookie, safe user/workspace metadata | `401/403/422/503` |
| `GET /dashboard/session/me` | ADMIN session | 없음 | dashboard session/user/workspace metadata | `401/403` |
| `POST /dashboard/session/logout` | ADMIN session + CSRF | 없음 | `revoked=true` | `401/403` |
| `GET /config/extension` | user | optional `extension_version` | policy version, timeout, ai service configs, selector configs, file policy | `401`, `403`, `503` |
| `POST /prompts/analyze` | user | transient prompt/context/policy/client_request_id | decision, safe detections, optional `masked_prompt` only for Mask | `400/401/403/409/413/422/503` |
| `POST /files/analyze` | user | transient text file content metadata without original filename | same decision shape as prompt analyze | `400/401/403/413/415/422/503` |
| `GET /events` | ADMIN | filters, cursor, limit | metadata event list | `401/403/404/422` |
| `GET /events/{event_id}` | ADMIN | path id | metadata-only event detail | `401/403/404` |
| `GET /stats/overview` | ADMIN | range, bucket, filters | event/action/risk/user summary | `401/403/422` |
| `GET /stats/users` | ADMIN | range, sort, filters, cursor | 사용자별 집계 rows | `401/403/422` |
| `GET /stats/detections` | ADMIN | range, bucket, filters | detector type/category aggregate | `401/403/422` |
| `GET/POST/PATCH /custom-filters` | ADMIN | keyword/regex/action/severity/enabled | filter metadata and version | `401/403/409/422` |
| `POST /custom-filters/dry-run` | ADMIN | sample text in request only | safe match summary only | `401/403/413/422` |
| `GET/PATCH /users` | ADMIN | filters or role/status update | user metadata | `401/403/404/409/422` |
| `GET/POST/PATCH /invites` | ADMIN | invite policy fields | invite metadata without secret reuse | `401/403/404/409/422` |
| `GET /status/server` | ADMIN | 없음 | safe health/status metadata | `401/403/503` |

`POST /prompts/analyze` request fields:

| 필드 | 타입 | 필수 | 설명 | 저장/로그 |
| --- | --- | --- | --- | --- |
| `client_request_id` | string | yes | 확장앱이 생성하는 idempotency key | metadata 저장 가능 |
| `prompt.text` | string | yes | 분석 대상 원문. request 처리 중에만 사용 | 저장/로그 금지 |
| `prompt.input_method` | string | yes | `keyboard`, `paste`, `file_text`, `unknown` 등 입력 방식 | metadata 저장 가능 |
| `prompt.content_length` | integer | yes | 확장앱이 본 prompt 길이. 서버 검증에 사용 | metadata 저장 가능 |
| `context.ai_service` | string | yes | `chatgpt` 등 서비스 이름 | metadata 저장 가능 |
| `context.ai_service_domain` | string | yes | `chatgpt.com` 등 도메인 | metadata 저장 가능 |
| `context.page_url_origin` | string | yes | origin까지만 포함. path/query 금지 | metadata 저장 가능 |
| `context.extension_version` | string | yes | 확장앱 버전 | metadata 저장 가능 |
| `context.browser` | string | yes | 브라우저 이름 | metadata 저장 가능 |
| `context.locale` | string | yes | 브라우저/페이지 locale | metadata 저장 가능 |
| `policy.version` | string | yes | 확장앱이 알고 있는 policy version | metadata 저장 가능 |

`POST /prompts/analyze` response fields:

| 필드 | 타입 | 필수 | 설명 | 저장/로그 |
| --- | --- | --- | --- | --- |
| `event_id` | string | yes | 원문 없는 event metadata id | 저장 가능 |
| `request_id` | string | yes | 서버 요청 추적 id | 저장 가능 |
| `risk_score` | integer | yes | 0-100 점수 | 저장 가능 |
| `risk_level` | string | yes | `none`, `low`, `medium`, `high`, `critical` | 저장 가능 |
| `action` | string | yes | `Allow`, `Warn`, `Mask`, `Block` | 저장 가능 |
| `user_message` | string | yes | 안전한 사용자 표시 문구 | 저장 가능 |
| `allow_original_send` | boolean | yes | 원문 전송 허용 여부 | 저장 가능 |
| `requires_justification` | boolean | yes | 사유 입력 필요 여부 | 저장 가능 |
| `masked_prompt` | string | `Mask`일 때만 | 서버가 생성한 치환 문자열 | event/dashboard 저장 금지 |
| `detections[]` | array | yes | 원문 없는 탐지 요약 | metadata 저장 가능 |
| `policy.version` | string | yes | 판정에 사용된 policy version | 저장 가능 |
| `policy.latest_version` | string | yes | 서버 최신 policy version | 저장 가능 |
| `partial_result` | boolean | no | 일부 detector 실패 등 제한 판정 여부 | 저장 가능 |

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

| Endpoint | 요청 필드 | 응답 필드 | 금지 |
| --- | --- | --- | --- |
| `GET /setup/status` | 없음 | `setup_required`, `workspace_exists`, `admin_exists`, `registration_mode` | DB URL, secret, stack trace |
| `POST /setup/bootstrap` | `workspace.name`, `admin.email`, `admin.password`, `admin.display_name` | workspace/admin metadata, extension tokens, audit id | password echo, password hash, raw request body log |
| `POST /auth/register` | `email`, `password`, `display_name`, `invite_code` 또는 `workspace_code` | user/workspace metadata, extension tokens | invite raw code storage, password echo |
| `POST /auth/login` | `email`, `password` | extension access/refresh token, user/workspace metadata | password echo, refresh token storage |
| `POST /auth/refresh` | `refresh_token` request-only | new access token, optional rotated refresh token | raw token persistence |
| `GET /auth/me` | 없음 | user/workspace/role/status metadata | token/secret/password hash |
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

The dashboard session id is delivered only as a `Set-Cookie` header. It is not returned in JSON.

Admin metadata API examples:

| Endpoint | 요청/필터 | 응답 핵심 | 금지 |
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

응답 금지:

- prompt echo
- raw detected value
- original filename
- full masked prompt in event/dashboard APIs
- raw exception message
- token/secret/password/hash/internal stack trace

## 8. 제품 범위와 저장소 구조

이 단원은 제품이 어디까지를 MVP로 포함하는지와 코드가 어느 위치에 놓이는지를 정의한다. 구현 세부 계약은 뒤의 API, 데이터, 탐지, 확장앱, 대시보드 단원을 따른다.

### 8.1 제품 범위
- 제품 목적:
  - 사용자가 ChatGPT 같은 AI 서비스에 민감한 업무 정보, 개인정보, 비밀값, 계약 정보, 파일 내용을 보내기 전에 위험을 판별한다.
  - 원문을 서버에 영구 저장하지 않고, 관리자에게는 메타데이터와 통계만 보여준다.
  - 자가 호스팅 환경에서 관리자가 서버와 DB를 직접 운영하고, 팀원이 Chrome 확장앱으로 보호 흐름을 사용한다.
- MVP 포함:
  - 자가 호스팅 서버 실행, 초기 관리자 bootstrap, 로그인/토큰 갱신, 사용자/초대/가입 관리.
  - Chrome 확장앱의 ChatGPT 대상 입력 탐지, 전송 보류, Analyze API 호출, Allow/Warn/Mask/Block 처리.
  - Python Analyze API, 규칙 기반 detector, 직접 필터, 위험 점수, 서버 측 마스킹, 중복 요청 처리, prompt hash.
  - 관리자 대시보드의 setup/auth, overview, event metadata, 사용자 통계, policy/custom filter/status 화면.
  - 개인정보/보안 회귀 테스트, Docker 기반 실행, 설치 문서, 최종 smoke scenario.
- MVP 제외:
  - 외부 LLM 호출 기반 분류.
  - PDF/Office/OCR/archive/binary 파일 분석.
  - 브라우저 네트워크 요청 감청 기반 검사.
  - SaaS 멀티테넌트 운영, 결제, 조직 단위 엔터프라이즈 관리.
  - SIEM 연동, SSO, 고급 정책 운영 workflow.

### 8.2 저장소와 코드 위치
| 대분류 | 소분류 | 기본 위치 | 설명 |
| --- | --- | --- | --- |
| API 서버 | Python 자가 호스팅 API | `apps/api/` | FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic 기준으로 생성한다. API schema, auth, detector, masking, event service를 포함한다. |
| 대시보드 | 관리자 UI | `apps/dashboard/` | setup, login, overview, events, users, invites, policies, custom filters, status 화면을 포함한다. |
| 확장앱 | Chrome Extension | `apps/extension/` | 이미 존재한다. content script, service worker, options, shared type/test를 유지하고 실제 API와 맞춘다. |
| 인프라 | Docker/env/reverse proxy | `infra/` | Docker Compose, PostgreSQL, 선택 Redis profile, reverse proxy 예시를 포함한다. |
| 테스트 | 통합/보안/회귀 | 각 앱의 `tests/` 또는 루트 테스트 | 앱별 단위 테스트와 cross-app privacy/security smoke를 둔다. |

## 9. 데이터 모델·원문 저장 금지 계약

데이터 모델은 metadata-only 저장을 기준으로 한다. 원문 프롬프트, 원문 파일 내용, full `masked_prompt`, 원문 탐지값, 원본 파일명은 DB, 로그, 대시보드, 오류 응답에 저장하거나 노출하지 않는다.

### 9.1 데이터 모델 하위 범위
- 계정/조직:
  - `workspaces`: 자가 호스팅 단위 workspace.
  - `users`: email, display name, role, status, password hash metadata.
  - `refresh_tokens`: raw token 저장 금지, hash와 만료/폐기 metadata만 저장.
  - `registration_settings`, `invites`: 가입 방식과 초대 lifecycle.
- 정책:
  - `policies`, `policy_versions`: threshold, detector enablement, action rule, retention metadata.
  - `ai_service_configs`: ChatGPT 계열 domain과 selector/config.
- 직접 필터:
  - `custom_filter_rules`: keyword/regex rule, enabled flag, severity/action metadata.
  - `custom_filter_versions`: 변경 이력과 policy 연결.
  - 위험 regex는 저장 전에 길이, syntax, timeout/ReDoS 전략을 통과해야 한다.
- 분석 이벤트:
  - `analysis_events`: event id, workspace/user id, action, risk score, risk level, prompt hash, policy version, metadata.
  - `event_detections`: detection type, category, severity, span hash 또는 safe evidence metadata. raw detected value 금지.
  - `event_feedback`: 사용자 확인/사유 metadata. 원문 금지.
  - `audit_logs`: setup/auth/admin action metadata. request body 원문 금지.
- 금지 컬럼:
  - `raw_prompt`, `prompt_text`, `file_content`, `masked_prompt`, `raw_detected_value`, `original_filename`, `secret_value`, `token_raw` 같은 컬럼은 만들지 않는다.

### 9.2 데이터 모델 상세 계약
데이터 모델 계약은 migration 전에 확정해야 한다. 아래 컬럼명은 구현 시작점이며 실제 migration은 Alembic으로 검토 가능하게 만든다.

| Table | 핵심 컬럼 | 제약 |
| --- | --- | --- |
| `workspaces` | `id`, `name`, `created_at`, `status` | `id` primary key |
| `users` | `id`, `workspace_id`, `email`, `display_name`, `role`, `status`, `password_hash`, `created_at`, `updated_at` | `unique(workspace_id, email)`, `foreign key workspace_id` |
| `refresh_tokens` | `id`, `workspace_id`, `user_id`, `token_hash`, `family_id`, `expires_at`, `idle_expires_at`, `revoked_at`, `reused_at`, `created_at` | raw token 저장 금지, `unique(token_hash)`, `foreign key user_id` |
| `registration_settings` | `workspace_id`, `mode`, `workspace_code_hash`, `updated_at` | `mode` enum: `INVITE_ONLY`, `WORKSPACE_CODE`, `OPEN_SIGNUP` |
| `invites` | `id`, `workspace_id`, `code_hash`, `email_domain`, `max_uses`, `used_count`, `expires_at`, `revoked_at` | raw invite code 저장 금지 |
| `policies` | `id`, `workspace_id`, `active_version_id`, `created_at` | workspace별 active policy |
| `policy_versions` | `id`, `policy_id`, `version`, `thresholds`, `detector_config`, `created_at` | immutable version row |
| `ai_service_configs` | `id`, `workspace_id`, `service`, `domain`, `selector_config`, `enabled`, `version` | extension config source |
| `custom_filter_rules` | `id`, `workspace_id`, `name`, `kind`, `pattern_hash`, `pattern_encrypted_optional`, `severity`, `action`, `enabled` | MVP에서 raw pattern 노출 금지, safe regex validation |
| `custom_filter_versions` | `id`, `rule_id`, `version`, `change_type`, `created_by`, `created_at` | 변경 이력 |
| `idempotency_keys` | `id`, `workspace_id`, `user_id`, `client_request_id`, `request_fingerprint`, `event_id`, `created_at`, `expires_at` | `unique(workspace_id, user_id, client_request_id)` |
| `analysis_events` | `id`, `workspace_id`, `user_id`, `prompt_hash`, `action`, `risk_score`, `risk_level`, `policy_version`, `service`, `service_domain`, `created_at` | raw prompt/masked prompt 저장 금지 |
| `event_detections` | `id`, `event_id`, `type`, `category`, `severity`, `confidence`, `count`, `span_hash`, `safe_evidence` | raw detected value 저장 금지 |
| `event_feedback` | `id`, `event_id`, `user_id`, `feedback_type`, `reason_code`, `created_at` | free text reason은 MVP에서 비활성 또는 redaction |
| `audit_logs` | `id`, `workspace_id`, `actor_user_id`, `action`, `target_type`, `target_id`, `safe_metadata`, `created_at` | request body 원문 금지 |

금지 컬럼:

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

마이그레이션 순서 / migration order:

1. workspace/user 기본 테이블
2. registration/invite/auth token 테이블
3. policy/config 테이블
4. custom filter 테이블
5. idempotency/event/detection/feedback/audit 테이블
6. seed: default workspace policy, registration mode, base detector config
7. privacy schema scan으로 금지 컬럼 확인

### 9.3 DB 관계·인덱스·삭제 정책

핵심 관계:

| 관계 | 기준 |
| --- | --- |
| `workspaces 1:N users` | 모든 user는 workspace에 속한다. |
| `users 1:N refresh_tokens` | refresh token family는 user와 workspace에 묶인다. |
| `workspaces 1:N policies` | self-host MVP에서는 기본 workspace당 active policy 1개를 사용한다. |
| `policies 1:N policy_versions` | policy version row는 immutable이다. |
| `custom_filter_rules 1:N custom_filter_versions` | filter 변경은 version/audit metadata로 남긴다. |
| `analysis_events 1:N event_detections` | event는 원문 없는 탐지 요약을 가진다. |
| `analysis_events 1:N event_feedback` | 사용자 확인/사유 metadata만 저장한다. |

필수 unique/index:

| Table | 제약/인덱스 | 이유 |
| --- | --- | --- |
| `users` | `unique(workspace_id, lower(email))` | 같은 workspace 안 email 중복 방지 |
| `refresh_tokens` | `unique(token_hash)`, index `(user_id, family_id)` | token rotation/reuse 탐지 |
| `invites` | `unique(workspace_id, code_hash)` | raw invite code 없이 중복 방지 |
| `policy_versions` | `unique(policy_id, version)` | policy version 충돌 방지 |
| `custom_filter_rules` | index `(workspace_id, enabled)` | analyze pipeline filter load |
| `idempotency_keys` | `unique(workspace_id, user_id, client_request_id)` | 중복 event 방지 |
| `analysis_events` | index `(workspace_id, created_at)`, `(workspace_id, user_id, created_at)`, `(workspace_id, action, created_at)` | dashboard list/stat query |
| `event_detections` | index `(event_id)`, `(category)`, `(type)` | detail/stat aggregate |
| `audit_logs` | index `(workspace_id, created_at)`, `(actor_user_id, created_at)` | setup/admin 감사 |

삭제/비활성 정책:

- MVP에서 user hard delete는 하지 않는다. `DISABLED` 또는 anonymized metadata로 처리한다.
- workspace hard delete는 MVP 운영 기능이 아니다.
- event row는 privacy-safe metadata만 저장하므로 retention policy로 기간 삭제할 수 있다.
- custom filter raw pattern은 dashboard/API에 재노출하지 않는다. 운영상 pattern 재표시가 필요하면 encrypted-at-rest 필드와 별도 권한 정책을 후속 계획으로 다룬다.
- audit log는 request body 원문을 저장하지 않고 action/target/safe_metadata만 저장한다.

## 10. 탐지·마스킹·점수·custom filter 계약

탐지와 마스킹은 서버 책임이다. 확장앱은 전송을 보류하고 서버가 반환한 action과 `masked_prompt`를 적용한다.

### 10.1 탐지/마스킹 하위 범위
- 파이프라인 순서:
  - request schema validation.
  - workspace/user/policy load.
  - 일시 텍스트 정규화.
  - 내장 detector 실행.
  - custom filter detector 실행.
  - overlap merge.
  - risk score/action 결정.
  - 서버 측 masking 생성.
  - 원문 없는 event metadata 저장.
  - safe response 반환.
- detector 종류:
  - 개인정보: email, phone, 주민등록번호 dummy checksum, card Luhn, 사업자등록번호.
  - 비밀값: GitHub token, AWS key, JWT, PEM private key, DB connection string, `.env` secret, 고엔트로피 후보.
  - 업무 문맥: 계약금액, 위약금, NDA, 고객정보, 영업기밀, 내부 전략, 출시계획, 가격정책.
  - custom filter: workspace ADMIN이 만든 keyword/regex.
- 병합 규칙:
  - secret detection이 일반 업무 문맥보다 우선한다.
  - 같은 우선순위에서는 긴 span을 우선한다.
  - overlap이 있으면 중복 detection을 response와 통계에서 이중 계산하지 않는다.
- 마스킹:
  - 마스킹은 프론트엔드 임의 탐지가 아니라 서버 response의 `masked_prompt`를 기준으로 한다.
  - `Mask` action일 때만 `masked_prompt`를 response에 포함한다.
  - 서버는 `masked_prompt`를 event row나 dashboard API에 저장/노출하지 않는다.
  - 같은 민감값이 여러 번 나오면 같은 placeholder로 일관 치환한다.

### 10.2 탐지·점수·Action 결정 계약
Action 결정은 detector가 아니라 server orchestrator가 최종 판단한다. 같은 입력, 같은 policy version, 같은 custom filter set이면 같은 결과를 내야 한다.

기본 위험 점수:

| Detection | 기본 점수 | 기본 action |
| --- | ---: | --- |
| confirmed secret: API key, private key, DB URI, JWT | 90 | Block 또는 Mask, policy에 따라 secret은 Block 우선 |
| confirmed credential-like `.env` secret | 85 | Mask |
| 주민등록번호/card/business id 같은 강한 PII | 80 | Mask |
| email/phone 단독 | 45 | Warn |
| 계약금액/위약금/NDA 문맥 | 65 | Warn 또는 Mask |
| 고객정보/영업기밀/내부전략 문맥 | 65 | Warn 또는 Mask |
| ambiguous low confidence | 30 | Allow 또는 Warn |
| custom filter critical | 90 | rule action 우선 |
| custom filter high | 70 | rule action 우선 |

Action 결정 규칙:

1. secret detection은 일반 업무 문맥보다 우선한다.
2. custom filter에 명시 action이 있으면 policy safety bound 안에서 우선한다.
3. overlap은 secret 우선, 그 다음 긴 span 우선이다.
4. `risk_score >= 85`: 기본 Block 또는 Mask.
5. `65 <= risk_score < 85`: 기본 Mask 또는 Warn.
6. `40 <= risk_score < 65`: 기본 Warn.
7. `risk_score < 40`: 기본 Allow.
8. policy version이 오래되어 서버 최신 정책과 충돌하면 `policy.latest_version`을 응답하고 필요 시 `409` 또는 safe decision을 반환한다.

마스킹:

- Mask action에서만 response에 `masked_prompt`를 포함한다.
- 서버는 `masked_prompt`를 저장하지 않는다.
- 같은 민감값 반복은 같은 placeholder로 치환한다.
- placeholder 예: `[SECRET_1]`, `[EMAIL_1]`, `[CONTRACT_AMOUNT_1]`.

### 10.3 custom filter MVP 경계
custom filter MVP는 포함한다. 단, 범위는 아래로 제한한다.

MVP 포함:

- ADMIN list/create/update/disable API.
- keyword/regex kind.
- severity/action metadata.
- enabled flag.
- safe regex validation: length, syntax, timeout 또는 safe-regex strategy.
- dry-run API. dry-run sample text는 request-only이고 저장하지 않는다.
- Analyze pipeline 연결과 dashboard metadata aggregate.

MVP 제외:

- 복잡한 rule expression builder.
- 조직/부서별 policy inheritance.
- regex 성능 튜닝 UI.
- raw match value 표시.
- custom filter별 원문 sample 저장.

custom filter MVP 구현이 끝났다고 보려면 API CRUD, dry-run, analyze pipeline 연결, dashboard list 화면, ReDoS/privacy tests가 모두 있어야 한다.

### 10.4 policy, rule pack, custom filter version 계약

`policy.version`은 Analyze 판정의 재현성을 위한 계약이다. 같은 입력, 같은 workspace, 같은 policy version, 같은 custom filter version set이면 같은 detector/scoring/action 결과가 나와야 한다.

Policy version에 포함되는 것:

- detector enable/disable.
- detector severity override.
- risk score threshold.
- action decision rule.
- custom filter version set 참조.
- file upload limit과 허용 확장자 policy.
- retention metadata.
- extension selector/config version 참조.

Policy version을 바꾸는 변경:

| 변경 | policy version 변경 |
| --- | --- |
| detector enable/disable 변경 | yes |
| risk threshold 변경 | yes |
| action rule 변경 | yes |
| custom filter 생성/수정/비활성화가 Analyze 결과에 영향을 주는 경우 | yes |
| file upload limit 변경 | yes |
| dashboard 표시 순서만 변경 | no |
| help text/copy 변경 | no |
| user role/status 변경 | no |

Rule pack 계약:

| 필드 | 설명 |
| --- | --- |
| `rule_pack_version` | 내장 detector/rule bundle version |
| `detector_id` | detector의 stable id |
| `category` | `secret`, `pii`, `business_context`, `custom_filter` |
| `severity` | 기본 severity |
| `default_action` | policy override 전 기본 action |
| `locale_scope` | `ko-KR`, `global` 등 |
| `test_fixture_id` | 대응하는 regression fixture id |

Custom filter version 계약:

- custom filter rule 자체는 `custom_filter_rules`에 현재 metadata를 둔다.
- 변경 이력은 `custom_filter_versions`에 append한다.
- Analyze event에는 적용된 policy version과 custom filter version summary를 safe metadata로 저장한다.
- dry-run sample text는 저장하지 않는다.
- raw match value는 저장/표시하지 않는다.

## 11. 확장앱 계약

확장앱은 ChatGPT 계열 화면에서 입력을 탐지하고 전송을 보류한 뒤, 실제 self-host API 판정에 따라 UX와 재전송을 처리한다.

### 11.1 확장앱 하위 범위
- content script:
  - 대상 domain에서만 동작한다.
  - textarea와 contenteditable 후보를 찾고, visible/focus 기준으로 현재 composer를 고른다.
  - send button click과 Enter 전송을 분석 완료 전 보류한다.
  - `@` mention, IME composition, Shift+Enter 줄바꿈, GPT picker 같은 작성 보조 동작은 전송으로 오판하지 않는다.
- service worker:
  - API base URL, token, policy/config cache, timeout, auth error 처리를 맡는다.
  - request body는 Analyze API 계약에 맞춰 만들고, workspace/user id를 임의로 넣지 않는다.
  - MV3 service worker inactive는 정상 lifecycle이며 로그인 만료로 취급하지 않는다.
  - wake-up 후 저장된 auth/session metadata를 읽고 access token 만료 시 자동 refresh를 먼저 시도한다.
  - refresh 실패가 확정된 경우에만 options page 또는 상태 UI에서 재로그인을 요구한다.
- options page:
  - self-host API URL 저장.
  - 연결 테스트.
  - login/logout/refresh 상태.
  - server status와 policy sync time 표시.
  - service worker inactive 자체를 오류로 표시하지 않는다.
  - refresh token 만료/폐기/재사용/계정 비활성/서버 변경 같은 실제 인증 실패만 사용자의 조치가 필요한 상태로 표시한다.
- action UX:
  - Allow: 원래 전송을 1회 재실행.
  - Warn: 확인 전 보류, 확인 후 전송.
  - Mask: 서버가 준 `masked_prompt`를 입력창에 치환하고 사용자가 다시 전송하도록 한다.
  - Block: 원문 전송을 발생시키지 않는다.
  - 통과되는 Allow는 불필요한 panel을 표시하지 않는다.

## 12. 대시보드 계약

대시보드는 관리자용 metadata-only UI다. overview, events, users, invites, policy, custom filter, status 화면은 원문을 표시하지 않고 집계와 안전 메타데이터만 보여준다.

### 12.1 대시보드 화면 범위
대시보드는 원문 검토 도구가 아니라 운영·관리 메타데이터 화면이다. 관리자에게 필요한 것은 누가 어떤 위험 흐름을 자주 만들고 있는지, 어느 기간에 경고/마스킹/차단이 늘어나는지, 정책과 확장앱 연결 상태가 정상인지 확인하는 것이다.

- 공통 원칙:
  - 모든 화면은 metadata-only다.
  - raw prompt, full masked prompt, original filename, raw detected value, secret/token, stack trace는 어떤 카드/표/상세/차트/export에도 표시하지 않는다.
  - 통계는 event metadata, action, risk score/level, detector type/category, policy version, service/domain, user id/display name, timestamp bucket만 사용한다.
  - 사용자별 집계는 필요하지만 사용자의 실제 입력 내용으로 드릴다운하지 않는다.
- 초기 설정/로그인:
  - 초기 설정 필요 여부 확인.
  - 첫 ADMIN bootstrap.
  - login, refresh, logout.
- MVP 요약 화면:
  - 전체 오버뷰 첫 화면에는 이벤트별 통계, 사용자별 통계, 기간별 통계가 모두 있어야 한다.
  - 이벤트별 통계: Allow/Warn/Mask/Block 수, detector category/type 분포, risk level 분포, top policy version 또는 rule pack 분포.
  - 사용자별 통계: 사용자별 event count, Warn/Mask/Block count, 마지막 이벤트 시각, top detector category. MVP에서는 상위 사용자 표와 요약 카드까지만 제공한다.
  - 기간별 통계: 24시간/7일/30일 또는 사용자가 선택한 기간의 event count 추이, action별 추이, detector category별 추이.
  - 오버뷰 카드: 총 이벤트 수, Warn 수, Mask 수, Block 수, 활성 사용자 수, 차단률/마스킹률, 최근 동기화된 policy version.
  - 차트는 추세를 보여주되 원문을 복원할 수 있는 값이나 긴 sample text를 포함하지 않는다.
- MVP 이벤트 화면:
  - 이벤트 목록/필터/상세.
  - 필터는 기간, 사용자, action, risk level, detector type/category, service/domain, policy version을 지원한다.
  - 상세에는 event id, action, risk score/level, detector type/category, policy version, timestamp, user/workspace metadata, prompt hash prefix 또는 event fingerprint 같은 안전 식별자만 표시한다.
  - raw prompt, masked prompt, original filename, raw detected value는 표시하지 않는다.
- MVP 사용자/초대/가입:
  - USER/ADMIN role과 status 관리.
  - invite 생성/폐기.
  - registration mode 관리.
- MVP 정책/상태 화면:
  - policy read 화면.
  - API, PostgreSQL, migration, policy readiness 표시.
  - Redis가 disabled이면 장애가 아니라 optional disabled로 표시한다.
- MVP custom filter 관리 화면:
  - custom filter list/create/update/disable.
  - dry-run은 request-only이고 sample 원문을 저장하지 않는다.
- 후속 관리자 분석 화면:
  - 사용자별 이벤트 발생 현황 상세 페이지.
  - 특정 사용자의 기간별 event timeline, action 분포, detector category 분포, risk 추이, 정책 version별 발생 현황을 보여준다.
  - 팀/부서/그룹별 비교, 반복 발생 사용자 확인, CSV export, 관리자 메모, 조치 상태 같은 기능은 후속 범위다.
  - 후속 화면도 원문·마스킹 전문·탐지 원값은 표시하지 않는다.

Dashboard 화면 계약:

| 화면 | route | 사용하는 API | 필수 UI | empty state | loading state | error state | 권한 | 테스트/검증 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Setup | `/setup` | `GET /setup/status`, `POST /setup/bootstrap` | 첫 workspace/ADMIN 생성 form, 완료 후 login/dashboard 이동 | setup 불필요 시 login으로 이동 | bootstrap 진행 중 submit 중복 방지 | `409` setup 완료, `422` 입력 오류, `503` DB 미준비를 안전 문구로 표시 | public only while setup_required | setup 완료 후 재bootstrap 차단, request body/log 원문 없음 |
| Login | `/login` | dashboard session login endpoint, `GET /auth/me` | email/password login, logout 후 재진입, session 상태 확인 | 이미 로그인됨이면 dashboard로 이동 | 로그인 진행 중 submit 중복 방지 | `401` 인증 실패, `403` disabled, `503` 서버 미준비 | public/authenticated redirect | session cookie `HttpOnly`, CSRF 적용, localStorage session 저장 없음 |
| Overview | `/dashboard` | `GET /stats/overview`, `GET /stats/users`, `GET /stats/detections` | 이벤트별 통계, 사용자별 통계, 기간별 통계, action/risk/detector cards/charts | 기간 내 이벤트 없음 표시 | skeleton 또는 spinner, 기존 필터 유지 | API 실패 시 safe error banner와 재시도 | ADMIN | raw prompt/full masked prompt/original filename/raw detected value DOM 미노출 |
| Events | `/events` | `GET /events` | 기간/사용자/action/risk/detector/service/policy filter, cursor list | 필터 결과 없음 표시 | list skeleton, filter disabled 최소화 | `422` 잘못된 filter, `403`, `503` 처리 | ADMIN | metadata-only list, cursor/limit, seeded sensitive value 미노출 |
| Event detail | `/events/:event_id` | `GET /events/{event_id}` | event id, action, risk, detector category/type, policy version, timestamp, safe fingerprint | 삭제/숨김 대상이면 not found | detail skeleton | cross-workspace hiding `404`, 권한 부족 `403` 구분 | ADMIN | 원문/마스킹 전문/탐지 원값/원본 파일명 미표시 |
| Users | `/users` | `GET/PATCH /users`, `GET /stats/users` | 사용자 목록, role/status 변경, 사용자별 aggregate summary | 사용자 없음 표시 | table skeleton | `403`, `404`, `409`, `422` 처리 | ADMIN | USER가 접근 시 403, disabled user 차단, raw prompt drilldown 없음 |
| Invites/Registration | `/invites` | `GET/POST/PATCH /invites`, registration settings API | invite 생성/폐기, 가입 방식 설정 | invite 없음 표시 | mutation 중 버튼 중복 방지 | 만료/폐기/중복/권한 오류 safe message | ADMIN | invite secret 재노출 금지, audit metadata 기록 |
| Policy | `/policy` | `/policies` | 현재 policy, threshold, detector enablement, retention metadata 표시 | policy seed 전이면 setup 필요 표시 | read skeleton | policy version conflict 또는 서버 미준비 표시 | ADMIN | read-only MVP, 잘못된 policy 전환 없음 |
| Custom filters | `/custom-filters` | `GET/POST/PATCH /custom-filters`, `POST /custom-filters/dry-run` | keyword/regex 생성·수정·비활성화, dry-run 결과 safe summary | filter 없음 표시 | dry-run 진행 상태, 저장 중 중복 방지 | regex syntax/ReDoS/size 오류 safe message | ADMIN | dry-run sample 저장 금지, raw match value 저장/표시 금지 |
| Status | `/status` | `GET /status/server` | API, PostgreSQL, migration, policy, optional Redis 상태 | 의존성 정보 없음이면 unknown 표시 | polling/loading 표시 | required dependency 실패는 outage, Redis disabled는 outage 아님 | ADMIN | secret/DB URL/token/stack trace 미노출, `/readyz` 실패 반영 |

### 12.2 MVP 대시보드 API·통계 계약
MVP 대시보드는 원문 검토 도구가 아니다. 모든 dashboard API는 metadata-only다.

통계 정의:

- `event count`: filter 조건에 맞는 `analysis_events` row 수.
- `active user`: 선택 기간 안에 event가 1개 이상 있는 distinct `user_id`.
- `block rate`: `Block` event count / 전체 event count.
- `mask rate`: `Mask` event count / 전체 event count.
- `warn rate`: `Warn` event count / 전체 event count.
- `top detector category`: event_detections aggregate count 기준 상위 category.
- `period bucket`: UTC 저장값을 기준으로 집계하고 dashboard 표시에서만 browser timezone을 적용한다.

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

`GET /stats/users`는 사용자별 집계를 반환한다. pagination은 `cursor`, `limit`을 사용한다.

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

MVP 이벤트 list/detail:

- filters: `from`, `to`, `user_id`, `action`, `risk_level`, `detector_type`, `detector_category`, `service`, `service_domain`, `policy_version`, `cursor`, `limit`.
- sort: 기본 `created_at desc`.
- detail fields: event id, action, risk score/level, detector type/category counts, policy version, service/domain, user metadata, prompt hash prefix, timestamp.
- 금지: raw prompt, full masked prompt, raw detected value, original filename.

후속 관리자 분석:

- 사용자별 이벤트 발생 현황 상세, timeline, group comparison, CSV export, admin notes, remediation status는 post-MVP다.
- 후속 화면도 raw prompt, full masked prompt, raw detected value, original filename은 표시하지 않는다.

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
| `privacy_secret_github_token` | `ghp_testsecret1234567890abcdef` 형태 dummy | analyze/file/custom filter dry-run | DB/log/error/dashboard/API response except safe detection summary | raw token absent; `category=api_key` summary 가능 |
| `privacy_file_text` | `고객사 담당자 전화번호 010-0000-0000` | `/files/analyze` JSON body | DB/log/dashboard/event detail/original filename fields | raw file text absent; phone detection count 가능 |
| `privacy_masked_prompt` | `[SECRET_1]`가 포함된 mask response | Mask response only | `analysis_events`, dashboard event/detail/stats, logs | full masked prompt absent from persistence/display |
| `privacy_custom_filter_sample` | dry-run sample sentence | `/custom-filters/dry-run` request | custom filter tables, event tables, logs | sample not persisted; match count only |
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
| `MAX_PROMPT_BYTES` | no | `65536` | prompt body limit |
| `MAX_FILE_BYTES` | no | `262144` | file body limit |
| `MAX_REQUEST_BYTES` | no | `524288` | request body limit |
| `REDIS_URL` | no | empty | optional profile에서만 사용 |

## 15. 테스트·완료·릴리즈 게이트

이 단원은 완료 판단 기준을 모은다. 기능 코드가 일부 존재해도 fresh install, privacy regression, 실제 API/extension/dashboard smoke가 통과하지 않으면 MVP 완료로 보지 않는다.

### 15.1 테스트/완료 기준 하위 범위
- API 단위 테스트:
  - setup/auth/RBAC.
  - schema validation.
  - health/status/error contract.
  - detector/masking/scoring/idempotency.
  - custom filter CRUD/dry-run.
- 개인정보 회귀:
  - DB schema scan.
  - seeded prompt/secret을 넣은 DB row scan.
  - application/access/error log scan.
  - error response scan.
  - dashboard DOM/API response scan.
- 확장앱 테스트:
  - selector fixture.
  - click/Enter hook.
  - `@` mention/GPT picker 예외.
  - Allow/Warn/Mask/Block action.
  - timeout/401.
  - 실제 API smoke.
- 대시보드 테스트:
  - auth guard.
  - setup flow.
  - metadata-only event detail.
  - user/invite/custom filter UI.
  - status 화면.
- 릴리즈 게이트:
  - API, dashboard, extension build/test 통과.
  - Docker fresh install smoke.
  - 외부 LLM 호출 없음 검증.
  - privacy regression 통과.
  - 최종 demo scenario 통과.

### 15.2 MVP 완료 정의
MVP 완료 정의는 "코드가 일부 있다"가 아니라 아래 흐름이 fresh install에서 끊기지 않고 통과하는 것이다.

1. 관리자가 Docker Compose 기본 구성으로 API와 PostgreSQL을 실행한다.
2. `/readyz`가 PostgreSQL 연결, migration 최신 상태, 기본 policy load 가능 상태를 확인한다.
3. 관리자가 `/setup/bootstrap`으로 첫 workspace와 첫 ADMIN을 만든다.
4. ADMIN이 dashboard에 로그인하고 invite/user/policy/custom filter/status 화면에 접근한다.
5. 일반 사용자가 invite 또는 허용된 registration mode로 가입하고 extension에 로그인한다.
6. extension이 `/auth/me`, `/config/extension`, `/prompts/analyze`를 실제 self-host API로 호출한다.
7. ChatGPT 대상 composer에서 click/Enter 전송이 분석 완료 전 보류된다.
8. Allow/Warn/Mask/Block 결과가 각각 계약된 UX로 동작한다.
9. Mask는 서버가 응답한 `masked_prompt`를 입력창에 치환하며 서버는 `masked_prompt` 전체를 저장하지 않는다.
10. Dashboard overview는 이벤트별 통계, 사용자별 집계, 기간별 추세를 metadata-only로 보여준다.
11. Event/detail/user/status/custom filter 화면과 API response는 raw prompt, raw file content, full masked prompt, original filename, raw detected value를 노출하지 않는다.
12. API, dashboard, extension test와 privacy regression, Docker fresh-install smoke, 최종 demo scenario가 통과한다.

MVP 릴리즈 게이트:

| 게이트 | 완료 기준 | 실패 시 처리 |
| --- | --- | --- |
| 설치 | fresh clone 또는 clean export에서 `.env.example` 기반 설정 후 API/PostgreSQL 시작 | 설치 문서와 compose/env를 먼저 수정 |
| DB | Alembic migration이 fresh DB와 restart 모두에서 성공 | migration 수정 전 기능 구현 진행 금지 |
| Auth | setup/login/refresh/logout/auth/me/RBAC test 통과 | extension/dashboard 연동 진행 금지 |
| Analyze | schema validation, detector, scoring, masking, idempotency, event metadata 저장 통과 | dashboard 통계와 extension smoke를 완료로 보지 않음 |
| Dashboard | overview/events/users/invites/policy/custom filter/status가 metadata-only로 동작 | raw-data scan 실패 시 릴리즈 금지 |
| Extension | selector, click/Enter, `@` mention 예외, Allow/Warn/Mask/Block, 401 refresh, real API smoke 통과 | 실제 ChatGPT smoke 재검증 |
| Privacy | DB/log/error/dashboard/API response scan에서 seeded sensitive value가 나오지 않음 | 원문 저장/노출 경계 수정 전 릴리즈 금지 |
| Release gate | API/dashboard/extension build/test, Docker smoke, no external LLM call, final demo 통과 | 완료 상태로 표시하지 않음 |

### 15.3 테스트 명령 매트릭스

| 영역 | 명령 | 완료 기준 |
| --- | --- | --- |
| API unit/integration | `cd apps/api && pytest` | setup/auth/RBAC/analyze/custom filter/status/error/privacy tests 통과 |
| API privacy scan | `cd apps/api && pytest tests/privacy` | seeded sensitive value가 DB/log/error response에 없음 |
| Dashboard | `cd apps/dashboard && npm test` | auth guard, setup, overview, metadata-only detail, user/invite/custom filter/status UI 통과 |
| Extension | `python apps/extension/tests/run_extension_checks.py all` | selector, hook, action UX, auth refresh, API client fixture 통과 |
| Root build | `npm run build --workspaces` | dashboard/extension JS build 통과. Python API는 별도 pytest/compose로 검증 |
| Docker smoke | `docker compose up --build` 후 health check | `/livez`, `/readyz`, `/healthz`, setup/login/analyze/dashboard smoke 통과 |
| Release gate | 각 영역 build/test + privacy regression + no external LLM verification | MVP 완료 가능 |

### 15.4 PM 실행 순서와 PR 묶음

102개 WBS 행은 아래 PR 묶음 순서로 진행한다. 앞 묶음의 계약/테스트가 없으면 뒤 묶음은 mock 수준에서만 진행하고 완료로 표시하지 않는다.

| 순서 | PR 묶음 | 포함 WBS | 목적 | 완료 조건 |
| --- | --- | --- | --- | --- |
| P0-1 | Monorepo/API/Compose scaffold | 6-11 | `apps/api`, `apps/dashboard`, `infra`, PostgreSQL, settings, health skeleton | 기본 compose가 API+PostgreSQL 실행, `/livez`/`/readyz`/`/healthz` skeleton 통과 |
| P0-2 | Setup/Auth/session/RBAC | 12-27 | bootstrap, registration, extension token auth, dashboard session auth, RBAC | setup/auth/session/RBAC tests 통과, auth endpoint 분리 완료 |
| P0-3 | Metadata-only DB/event/idempotency | 28-33, 90-91 | Analyze schema, prompt hash, idempotency, event metadata, privacy DB/log scan | duplicate event 방지, 금지 컬럼/로그 scan 통과 |
| P0-4 | Core detectors/scoring/masking | 34-47, 53-56, 98 | PII/secret/business context, merge, score, server-side mask, corpus | detector/scoring/masking tests와 corpus smoke 통과 |
| P0-5 | Extension real API integration | 57-73, 94-95 | existing extension을 실제 API와 연결 | real `/auth/me`/`/config/extension`/`/prompts/analyze` smoke 통과 |
| P0-6 | Dashboard MVP metadata UI | 74-89, 97 | setup/login/overview/events/users/invites/policy/custom filter/status | metadata-only API/DOM privacy tests 통과 |
| P1-1 | Custom filter full MVP | 48-52, 87 | custom filter CRUD/dry-run/pipeline/dashboard | ReDoS/privacy/custom filter integration 통과 |
| P1-2 | Release/docs/final smoke | 5, 99-102 | README/install/admin/privacy/release/demo | fresh install demo와 release gate 통과 |

우선순위 규칙:

- P0는 MVP 완료에 필수다.
- P1은 MVP 안에 포함되지만 P0 API/DB/dashboard 기반이 먼저 있어야 완료할 수 있다.
- P2/post-MVP는 사용자별 상세 분석, CSV export, 관리자 메모, 고급 policy workflow, PDF/Office/OCR, SSO/SIEM이다.
- extension mock/fake backend 통과는 P0-5 완료가 아니다. 실제 self-host API smoke가 필요하다.

### 15.5 최종 smoke/demo 시나리오

최종 smoke는 한 번의 fresh install에서 아래 순서로 수행한다.

1. `docker compose up --build`로 API와 PostgreSQL을 시작한다.
2. `GET /livez`가 `200`을 반환한다.
3. `GET /readyz`가 DB 연결, migration 최신, 기본 policy load 가능 상태로 `200`을 반환한다.
4. `GET /setup/status`가 `setup_required=true`를 반환한다.
5. `POST /setup/bootstrap`으로 첫 workspace와 ADMIN을 만든다.
6. dashboard에서 `POST /dashboard/session/login`으로 ADMIN session을 만든다.
7. dashboard `/dashboard`, `/events`, `/users`, `/invites`, `/policy`, `/custom-filters`, `/status` route가 열린다.
8. invite를 만들고 일반 USER를 등록한다.
9. extension options에서 self-host API URL을 저장하고 `GET /auth/me`, `GET /config/extension` 연결을 확인한다.
10. ChatGPT composer에 `NDA 위약금은 3억원입니다`를 입력하고 Warn 또는 Mask가 표시되는지 확인한다.
11. dummy secret fixture를 입력하고 Mask 또는 Block이 표시되며 원문 submit이 발생하지 않는지 확인한다.
12. Mask action은 서버가 반환한 `masked_prompt`를 composer에 치환하고 자동 전송하지 않는다.
13. dashboard overview에 event/action/user/period metadata 통계가 표시된다.
14. events/detail/users/custom filters/status 화면과 API response에서 seeded raw value가 나오지 않는지 확인한다.
15. DB/log/error/dashboard privacy scan과 no external LLM call check를 실행한다.

Smoke fixture:

| 이름 | 입력 | 기대 결과 |
| --- | --- | --- |
| allow_basic | `오늘 회의 안건 정리해줘` | Allow, panel 없음, 원문 전송 가능 |
| warn_contract | `NDA 위약금은 3억원입니다` | Warn 또는 Mask, 원문 저장 없음 |
| mask_email_phone | `담당자 test@example.com 010-0000-0000` | Mask, placeholders 적용 |
| block_private_key | dummy PEM private key block | Block, 원문 submit 없음 |
| custom_filter | ADMIN이 만든 keyword 포함 문장 | custom filter action 적용 |

## 16. WBS 문서 순서 기준 작업표
아래 `문서 순서`는 이 v5 문서 안에서 읽기 쉽게 1부터 다시 매긴 번호다. 원본 WBS의 담당자, 영역, 분류, 항목, 상세 내용은 보존하되, 현재 CSV가 담당자별로 섞여 있어 표시는 문서용 연속 번호로 정리한다.

상태 기준:

- `됨`: 현재 repo에서 실제 구현 또는 문서화가 확인됨.
- `부분`: 일부 구현/문서가 있으나 self-host MVP 완료 기준에는 부족함.
- `안됨`: 현재 repo에 해당 구현이 없음.
- `보류`: 현재 사용자 결정 또는 외부 의존성 없이는 구현 계약을 닫을 수 없음. 이미 확정된 Python/FastAPI/PostgreSQL/Redis optional 결정에는 쓰지 않는다.

각 WBS 행의 `v5 구현 지시`는 다음 네 가지를 포함하는 구현 티켓으로 읽는다.

- 남은 구현: 현재 repo 기준으로 아직 만들어야 하는 코드, 테스트, 문서.
- 선행 작업: 시작 전에 필요한 API, schema, 화면, migration, fixture, 설정.
- 완료 PR 기준: 해당 항목을 완료로 바꿀 수 있는 observable output.
- 테스트/검증: 실행 명령, privacy/security scan, smoke, 또는 문서 검증.

| 문서 순서 | 단계 | 분류 | 항목 | 담당자 | 영역 | 기존 상세 | 현재 상태 | v5 구현 지시 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 준비/기획 | 범위확정 | 오픈소스 MVP 범위 확인 | 김현성 | 기획·QA·문서 | Self-host, 가입, 원문 미저장, 직접 필터 범위표 | 부분 | 남은 구현: README/install/admin/privacy 문서가 v5 MVP 범위와 일치하도록 정리. 선행 작업: v5 계약 확정. 완료 PR 기준: self-host, 가입, 원문 미저장, 직접 필터, 대시보드 범위가 문서와 repo 구조에서 같은 말로 설명됨. 테스트/검증: 문서 grep과 최종 demo scenario 체크리스트. |
| 2 | 준비/기획 | 우선순위 | P0/P1/P2 요구사항 재분류 | 김현성 | 기획·QA·문서 | 필수·선택·후속 범위 정리표 | 부분 | 남은 구현: MVP 필수, 선택, 후속 범위표를 이 WBS와 동기화. 선행 작업: API/dashboard/extension 범위 확정. 완료 PR 기준: 각 WBS 행이 MVP 포함/후속/선택 여부와 완료 기준을 가진다. 테스트/검증: 범위밖 기능이 MVP Done Definition에 섞이지 않는지 리뷰. |
| 3 | 준비/기획 | 사용자흐름 | 설치·가입·확장앱·대시보드 흐름 정리 | 김영은 | 대시보드·UI | Setup→회원가입→Extension→Dashboard 흐름도 | 안됨 | 남은 구현: setup -> login/signup -> extension connection -> analyze -> dashboard metadata view 흐름도와 화면 skeleton. 선행 작업: setup/auth/session API 계약. 완료 PR 기준: 대시보드 route와 빈/로딩/오류 상태가 흐름과 연결됨. 테스트/검증: setup/login/dashboard smoke. |
| 4 | 준비/기획 | 구성결정 | Self-host 서버 구성 결정안 작성 | 유지수 | 서버·보안 | Docker, DB, Redis, reverse proxy 구성안 | 부분 | 남은 구현: Python/FastAPI/PostgreSQL 기본 구성과 Redis optional profile 문서/compose. 선행 작업: env schema와 health contract. 완료 PR 기준: 기본 compose가 Redis 없이 API+PostgreSQL을 시작하고 optional Redis는 disabled로 표시됨. 테스트/검증: Docker smoke, `/readyz`, `/healthz`. |
| 5 | 준비/기획 | 검증계획 | 테스트·릴리즈 게이트 목록 정리 | 전체 | 기획·QA·문서 | Install, E2E, privacy, security 테스트 목록 | 부분 | 남은 구현: API/dashboard/extension/privacy/security/release gate를 구현 subplan과 CI 명령으로 연결. 선행 작업: 각 앱 scaffold와 테스트 runner. 완료 PR 기준: 모든 MVP slice가 완료 PR 기준과 테스트 명령을 가진다. 테스트/검증: `pytest`, dashboard test, extension checks, Docker smoke, privacy regression. |
| 6 | OSS·Setup·Auth | 저장소 | 모노레포 기본 구조 생성 | 김현성 | Chrome 확장 | apps/api, apps/dashboard, apps/extension, packages, docs, infra | 부분 | `apps/extension`만 있음. Python API, dashboard, infra는 다음 구현. |
| 7 | OSS·Setup·Auth | 실행환경 | Docker Compose 실행 구성 | 김현성 | Chrome 확장 | API, dashboard, PostgreSQL, Redis compose 파일 | 안됨 | Redis는 선택 profile로만 두고 Python API/PostgreSQL compose부터 만든다. |
| 8 | OSS·Setup·Auth | 환경변수 | .env.example 및 시작 검증 구현 | 전체 | 기획·QA·문서 | 필수 환경변수 검증과 dummy secret 파일 | 안됨 | Python config validation과 safe dummy secret 예시를 작성한다. |
| 9 | OSS·Setup·Auth | 빌드 | API·화면·확장앱 공통 빌드 스크립트 정리 | 김현성 | Chrome 확장 | dev/build/test script와 package 명령 | 부분 | root workspace는 필요하되 서버가 Python이므로 JS-only workspace 전제를 재검토한다. |
| 10 | OSS·Setup·Auth | 상태점검 | 서버 health check endpoint 구현 | 유지수 | 서버·보안 | /healthz 응답과 dependency 상태 | 안됨 | `/livez`, `/readyz`, `/healthz`, dashboard status schema를 구현한다. |
| 11 | OSS·Setup·Auth | 마이그레이션 | DB migration 실행 골격 작성 | 유지수 | 서버·보안 | fresh install·restart migration 검증 | 안됨 | SQLAlchemy 2.x + Alembic 기준으로 migration runner를 작성한다. |
| 12 | OSS·Setup·Auth | 초기설정 | setup 상태 조회 API 구현 | 김영은 | 서버·보안 | /setup/status, setup_required 응답 | 안됨 | Python API endpoint와 tests 작성. |
| 13 | OSS·Setup·Auth | 초기설정 | 첫 관리자 bootstrap API 구현 | 김영은 | 서버·보안 | workspace, ADMIN, default policy 생성 | 안됨 | setup lock, transaction, one-time bootstrap 구현. |
| 14 | OSS·Setup·Auth | 초기설정 | bootstrap 1회 제한과 audit 기록 구현 | 김영은 | 서버·보안 | setup lock, SETUP_COMPLETED audit | 안됨 | PostgreSQL constraint와 audit metadata 구현. |
| 15 | OSS·Setup·Auth | 초기화면 | 첫 관리자 생성 화면 구현 | 김영은 | 대시보드·UI | /setup 입력 화면과 완료 이동 | 안됨 | dashboard setup screen과 API 연동. |
| 16 | OSS·Setup·Auth | 설정seed | 기본 workspace·policy·가입 설정 seed | 김영은 | 서버·보안 | INVITE_ONLY 기본값, default policy version | 안됨 | fresh DB seed/migration으로 구현. |
| 17 | OSS·Setup·Auth | 계정DB | 사용자·초대·가입설정 테이블 작성 | 유지수 | 서버·보안 | users, invites, registration_settings migration | 안됨 | PostgreSQL migration 작성. |
| 18 | OSS·Setup·Auth | 비밀번호 | 비밀번호 hash 저장 처리 | 유지수 | 서버·보안 | Argon2id/bcrypt 적용, 평문 미저장 테스트 | 안됨 | Argon2id 우선으로 구현하고, 운영 환경에서 비용 파라미터를 설정 가능하게 둔다. |
| 19 | OSS·Setup·Auth | 로그인 | 로그인·refresh·auth/me API 구현 | 유지수 | 서버·보안 | access/refresh token 발급과 사용자 정보 응답 | 안됨 | refresh token raw 미저장, `/auth/me` 구현. |
| 20 | OSS·Setup·Auth | 토큰보호 | refresh token hash·만료·폐기 처리 | 유지수 | 서버·보안 | refresh_tokens 원문 미저장 검증 | 안됨 | token hash, expiry, revoke, rotation tests. |
| 21 | OSS·Setup·Auth | 권한 | ADMIN/USER 권한 middleware 구현 | 유지수 | 서버·보안 | Admin API USER 접근 403 테스트 | 안됨 | role guard와 403/404 정책 적용. |
| 22 | OSS·Setup·Auth | 초대 | 일반회원 초대 가입 API 구현 | 김민지 | 서버·보안 | 유효 invite 가입, 잘못된 코드 거부 | 안됨 | invite validation, max uses, expiry. |
| 23 | OSS·Setup·Auth | 초대관리 | 초대 코드 생성·폐기 API 구현 | 김민지 | 서버·보안 | invite max_uses, expires_at, revoked 처리 | 안됨 | ADMIN invite CRUD. |
| 24 | OSS·Setup·Auth | 가입방식 | INVITE_ONLY·WORKSPACE_CODE·OPEN_SIGNUP 처리 | 김민지 | 서버·보안 | 가입 모드별 허용·차단 테스트 | 안됨 | registration mode state machine. |
| 25 | OSS·Setup·Auth | 사용자관리 | 사용자 상태·역할 변경 API 구현 | 김민지 | 서버·보안 | ACTIVE/DISABLED, USER/ADMIN 변경 | 안됨 | ADMIN user management API. |
| 26 | OSS·Setup·Auth | 인증검증 | 가입·로그인·권한 테스트 작성 | 김민지 | 기획·QA·문서 | setup/auth/RBAC 통합 테스트 | 안됨 | pytest/API integration tests. |
| 27 | OSS·Setup·Auth | 보안설정 | CORS·rate limit 기본 정책 적용 | 유지수 | 서버·보안 | 허용 origin, auth/analyze 요청 제한 | 안됨 | explicit CORS, in-process/Postgres rate limit first. |
| 28 | 분석/탐지 | 요청검증 | Analyze API 요청 schema 검증 | 김현성 | 서버·보안 | prompt/context/policy/client_request_id 검증 | 안됨 | Pydantic v2 schema와 OpenAPI 기준으로 구현한다. |
| 29 | 분석/탐지 | 원문보호 | raw_prompt 저장 금지 처리 경계 구현 | 김현성 | 기획·QA·문서 | request body logging 차단과 redaction hook | 안됨 | redacted logger와 privacy tests부터 작성. |
| 30 | 분석/탐지 | 중복처리 | client_request_id 중복 요청 처리 | 김현성 | 서버·보안 | idempotency 정책과 중복 이벤트 방지 | 안됨 | PostgreSQL idempotency metadata, Mask recompute rule 구현. |
| 31 | 분석/탐지 | 해시 | HMAC prompt_hash 생성 구현 | 김현성 | 서버·보안 | workspace별 hash 분리와 secret 주입 | 안됨 | workspace-scoped HMAC key id와 secret injection. |
| 32 | 분석/탐지 | 이벤트DB | 분석 이벤트·탐지 상세 테이블 작성 | 김민지 | 서버·보안 | raw_prompt, masked_prompt, value 금지 migration | 안됨 | metadata-only schema migration. |
| 33 | 분석/탐지 | 이벤트저장 | 원문 없는 이벤트 저장 서비스 구현 | 김민지 | 서버·보안 | user, service, detection_types, risk, action 저장 | 안됨 | event service and transaction boundary. |
| 34 | 분석/탐지 | 개인정보 | 이메일·전화번호 탐지 구현 | 유지수 | 서버·보안 | EMAIL/PHONE 탐지 함수와 단위 테스트 | 안됨 | deterministic detectors + corpus tests. |
| 35 | 분석/탐지 | 개인정보 | 주민등록번호 checksum 검증 구현 | 유지수 | 서버·보안 | 유효/무효 dummy RRN 테스트 | 안됨 | dummy-only checksum tests. |
| 36 | 분석/탐지 | 개인정보 | 카드번호 Luhn 검증 구현 | 유지수 | 서버·보안 | Luhn 유효 번호만 탐지 | 안됨 | Luhn test vectors. |
| 37 | 분석/탐지 | 한국현지화 | 사업자등록번호 후보·검증 구현 | 유지수 | 기획·QA·문서 | 사업자번호 후보와 checksum 테스트 | 안됨 | Korean business number test corpus. |
| 38 | 분석/탐지 | 업무후보 | 금액·할인율·계약기간 후보 탐지 | 유지수 | 기획·QA·문서 | 한국어 업무 문장 후보 테스트셋 | 안됨 | context evidence corpus. |
| 39 | 분석/탐지 | 비밀값 | GitHub·AWS key 탐지 구현 | 김영은 | 서버·보안 | ghp_, github_pat_, AKIA/ASIA 테스트 | 안됨 | secret detector tests. |
| 40 | 분석/탐지 | 비밀값 | JWT·개인키 block 탐지 구현 | 김영은 | 서버·보안 | JWT 3-part, PEM block 테스트 | 안됨 | JWT/PEM detector tests. |
| 41 | 분석/탐지 | 비밀값 | DB 접속 문자열 탐지 구현 | 김영은 | 서버·보안 | postgres/mysql/mongodb URI 탐지 | 안됨 | URI detector with redaction tests. |
| 42 | 분석/탐지 | 비밀값 | .env secret·고엔트로피 후보 탐지 | 김영은 | 서버·보안 | PASSWORD/SECRET key=value, entropy 테스트 | 안됨 | env and entropy detector. |
| 43 | 분석/탐지 | 규칙팩 | 한국 현지화 rule pack 구조 작성 | 김민지 | 기획·QA·문서 | rule_pack_version, label, severity 규격 | 안됨 | rule pack schema and fixtures. |
| 44 | 분석/탐지 | 문맥분류 | 계약정보 규칙 분류 구현 | 김현성 | 기획·QA·문서 | 계약금액, 위약금, NDA 문맥 테스트 | 안됨 | rule classifier and corpus tests. |
| 45 | 분석/탐지 | 문맥분류 | 고객정보 규칙 분류 구현 | 유지수 | 기획·QA·문서 | 고객사, 담당자, 문의 조합 테스트 | 안됨 | customer context classifier. |
| 46 | 분석/탐지 | 문맥분류 | 영업기밀·내부전략 규칙 분류 구현 | 김영은 | 기획·QA·문서 | 가격정책, 출시계획, 경쟁전략 테스트 | 안됨 | strategy context classifier. |
| 47 | 분석/탐지 | 문맥분류 | 낮은 신뢰도·애매한 문장 처리 | 김민지 | 기획·QA·문서 | AMBIGUOUS 처리와 강한 차단 제외 | 안됨 | ambiguous evidence scoring rule. |
| 48 | 분석/탐지 | 직접필터 | 사용자 정의 필터 테이블 작성 | 유지수 | 서버·보안 | custom_filter_rules, versions migration | 안됨 | custom filter migrations. |
| 49 | 분석/탐지 | 직접필터 | 정규식·키워드 필터 API 구현 | 김현성 | 서버·보안 | 생성·수정·비활성화·조회 API | 안됨 | ADMIN CRUD with safe regex validation. |
| 50 | 분석/탐지 | 직접필터 | 위험 정규식 저장 전 검증 | 전체 | 기획·QA·문서 | 길이, syntax, 실행 timeout, ReDoS 방어 | 안됨 | ReDoS tests and safe-regex strategy. |
| 51 | 분석/탐지 | 직접필터 | 필터 dry-run API 구현 | 김민지 | 서버·보안 | 샘플 원문 미저장 테스트 | 안됨 | dry-run request-only, no persistence. |
| 52 | 분석/탐지 | 직접필터 | 사용자 정의 필터 분석 pipeline 연결 | 김현성 | 서버·보안 | custom_filter detection과 통계 metadata | 안됨 | detector pipeline integration. |
| 53 | 분석/탐지 | 병합 | 탐지 결과 overlap 병합 규칙 구현 | 김현성 | 서버·보안 | secret 우선, 긴 span 우선 테스트 | 안됨 | overlap merge priority tests. |
| 54 | 분석/탐지 | 위험도 | 위험 점수·조치 결정 규칙 구현 | 전체 | 기획·QA·문서 | 0~100 점수, Allow/Warn/Mask/Block | 안됨 | deterministic scoring policy. |
| 55 | 분석/탐지 | 마스킹 | 개인정보·비밀값 placeholder 치환 | 유지수 | 서버·보안 | PII/API_KEY/DB URL 반복값 전체 치환 | 안됨 | server-side masking with no storage. |
| 56 | 분석/탐지 | 분석통합 | Analyze API 전체 흐름 통합 | 유지수 | 서버·보안 | detector→score→mask→log→response 통합 | 안됨 | orchestrator + integration tests. |
| 57 | 확장앱 | 뼈대 | Manifest V3 확장앱 scaffold 작성 | 김현성 | Chrome 확장 | content script, service worker, options 구조 | 됨 | 유지보수 및 real API adapter 연동만 남음. |
| 58 | 확장앱 | 서버연결 | Self-host API URL 입력 화면 구현 | 김현성 | Chrome 확장 | API base URL 저장과 연결 검증 | 부분 | mock/real 연결 UI 있음. real `/auth/me` 서버 필요. |
| 59 | 확장앱 | 로그인 | 확장앱 로그인·토큰 저장 처리 | 김현성 | Chrome 확장 | token 저장, refresh, 로그아웃 동작 | 부분 | token 저장은 있음. real refresh/logout 서버 연동 필요. MV3 service worker inactive는 인증 만료가 아니며 access token 만료 시 자동 refresh를 먼저 시도한다. |
| 60 | 확장앱 | 설정동기화 | 서버 selector·policy config 동기화 | 김현성 | Chrome 확장 | /config/extension 호출과 cache | 부분 | client/cache 있음. real server endpoint 필요. |
| 61 | 확장앱 | 도메인 | ChatGPT 도메인 활성화 제한 | 김현성 | Chrome 확장 | 대상/비대상 도메인 동작 분리 | 됨 | ChatGPT-like selector regression 유지. |
| 62 | 확장앱 | 입력탐지 | textarea 입력창 탐지 구현 | 김현성 | Chrome 확장 | visible/focus 기준 후보 선택 | 됨 | DOM 변경 smoke 유지. |
| 63 | 확장앱 | 입력탐지 | contenteditable 입력창 탐지 구현 | 김현성 | Chrome 확장 | contenteditable fallback 탐지 | 됨 | real ChatGPT smoke 필요. |
| 64 | 확장앱 | 전송보류 | 전송 버튼 클릭 가로채기 | 김현성 | Chrome 확장 | 분석 완료 전 submit 보류 | 됨 | selector drift tests 유지. |
| 65 | 확장앱 | 전송보류 | Enter·단축키 전송 가로채기 | 김현성 | Chrome 확장 | Enter/Shift+Enter 분기 | 됨 | @ mention/GPT picker 예외 회귀 테스트 유지. |
| 66 | 확장앱 | API연동 | 분석 API client 구현 | 김현성 | Chrome 확장 | request body 생성, 401/timeout 처리 | 부분 | client exists; real server and shared/generated schema needed. |
| 67 | 확장앱 | 중복방지 | 전송 허용 prompt 중복 전송 방지 | 김현성 | Chrome 확장 | allow hash, double-submit guard | 됨 | server idempotency와 별도 유지. |
| 68 | 확장앱 | 조치처리 | Allow 전송 재개 처리 | 김현성 | Chrome 확장 | 원래 전송 1회 재실행 | 됨 | real API smoke에서 확인. |
| 69 | 확장앱 | 조치처리 | Warn 경고 panel 구현 | 김현성 | Chrome 확장 | 확인 전 보류, 확인 후 전송 | 됨 | UX copy safe. |
| 70 | 확장앱 | 조치처리 | Mask panel과 선택 동작 구현 | 김현성 | Chrome 확장 | 마스킹 적용, 취소, 사유 요청 | 됨 | server-supplied mask와 smoke 필요. |
| 71 | 확장앱 | 마스킹 | 입력창 masked_prompt 치환 구현 | 김현성 | Chrome 확장 | textarea/contenteditable 치환 | 됨 | 자동 전송 금지 유지. |
| 72 | 확장앱 | 차단 | Block 안내와 원문 전송 차단 구현 | 김현성 | Chrome 확장 | 원문 submit 미발생 검증 | 됨 | fixture + real smoke 유지. |
| 73 | 확장앱 | 고지상태 | 저장/미저장 고지와 연결 상태 화면 | 김현성 | Chrome 확장 | notice, policy sync time, server status | 부분 | server status endpoint가 아직 없음. |
| 74 | 대시보드/관리 | 화면뼈대 | Dashboard routing·layout 구성 | 김영은 | 대시보드·UI | 라우팅, auth guard, 공통 레이아웃 | 안됨 | dashboard scaffold 구현. |
| 75 | 대시보드/관리 | Setup화면 | Setup·login 화면 연결 | 김영은 | 대시보드·UI | 첫 관리자 생성, 로그인 화면 | 안됨 | setup/auth API 이후 UI 구현. |
| 76 | 대시보드/관리 | 요약 | Overview summary API 연결 | 김영은 | 대시보드·UI | 기간별 totals, risk trend 데이터 연결 | 안됨 | MVP 필수. event/action/detector/user/period metadata summary API 필요. |
| 77 | 대시보드/관리 | 요약 | Overview 카드·추이 차트 구현 | 김영은 | 대시보드·UI | 이벤트, Warn, Mask, Block 카드 | 안됨 | MVP 필수. 이벤트별·사용자별·기간별 통계를 첫 화면에 표시한다. |
| 78 | 대시보드/관리 | 이벤트 | Risk Events 목록·필터 구현 | 김영은 | 대시보드·UI | 기간, 유형, action, risk 필터 | 안됨 | MVP 필수. 기간, 사용자, action, risk, detector, service/domain filter를 raw value 없이 구현. |
| 79 | 대시보드/관리 | 이벤트 | 원문 없는 이벤트 상세 구현 | 김영은 | 대시보드·UI | event_id, 유형, 점수, 정책 version만 표시 | 안됨 | MVP 필수. safe metadata detail과 privacy UI tests 필요. |
| 80 | 대시보드/관리 | 사용자통계 | 사용자별 이벤트 통계 API 구현 | 유지수 | 서버·보안 | 사용자별 유형/횟수/action 분포 API | 안됨 | MVP 필수. 사용자별 aggregate API, 후속 drilldown API와 분리. |
| 81 | 대시보드/관리 | 사용자통계 | 사용자별 이벤트 표 구현 | 김민지 | 대시보드·UI | 사용자, 부서, top detection, 마지막 이벤트 | 안됨 | MVP 필수. 상위 사용자/사용자별 summary table. 상세 점검 페이지는 후속. |
| 82 | 대시보드/관리 | 사용자통계 | 사용자 action·탐지유형 차트 구현 | 김민지 | 대시보드·UI | stacked bar, detection heatmap 데이터 | 안됨 | MVP 필수. metadata-only chart; 개인 timeline/detail은 후속. |
| 83 | 대시보드/관리 | 사용자관리 | Users 관리 화면 구현 | 김민지 | 대시보드·UI | 목록, role/status 변경 | 안됨 | admin UI. |
| 84 | 대시보드/관리 | 가입관리 | Invites·Registration 화면 구현 | 김민지 | 대시보드·UI | 초대 생성/폐기, 가입 방식 설정 | 안됨 | invite/registration UI. |
| 85 | 대시보드/관리 | 정책 | 현재 policy 조회 화면 구현 | 김민지 | 대시보드·UI | threshold, detector, retention 표시 | 안됨 | policy read-only UI first. |
| 86 | 대시보드/관리 | 통계 | 탐지 유형별 통계 화면 구현 | 김민지 | 대시보드·UI | detection type trend와 action count | 안됨 | metadata charts. |
| 87 | 대시보드/관리 | 직접필터 | 사용자 정의 필터 관리 화면 구현 | 김민지 | 대시보드·UI | 필터 목록, 생성, 수정, dry-run UI | 안됨 | custom filter APIs after server. |
| 88 | 대시보드/관리 | 상태 | 서버 health·degraded 상태 화면 | 김민지 | 대시보드·UI | API/DB/Redis 상태 표시 | 안됨 | Redis only when enabled. |
| 89 | 대시보드/관리 | 원문금지 | Dashboard 원문 미노출 화면 테스트 | 전체 | 기획·QA·문서 | raw_prompt, masked_prompt, detected value 미표시 검증 | 안됨 | MVP 필수. overview/event/user/status/custom filter 화면의 DOM/API response를 seeded sensitive value로 검사. |
| 90 | 통합·보안·문서 | Privacy | DB 원문 미저장 회귀 테스트 작성 | 전체 | 기획·QA·문서 | 금지 컬럼·seeded prompt DB scan | 안됨 | pytest/schema scan. |
| 91 | 통합·보안·문서 | Privacy | 로그 원문 미저장 회귀 테스트 작성 | 전체 | 기획·QA·문서 | application/access/error log seeded scan | 안됨 | log capture tests. |
| 92 | 통합·보안·문서 | Security | 외부 LLM 호출 금지 검증 작성 | 전체 | 기획·QA·문서 | network mock, outbound LLM 호출 0건 | 안됨 | no external LLM CI check. |
| 93 | 통합·보안·문서 | Security | setup·auth·RBAC 보안 테스트 작성 | 전체 | 기획·QA·문서 | bootstrap 1회 제한, USER 403, token 만료 | 안됨 | auth security tests. service worker inactive가 재로그인으로 이어지지 않고 refresh 실패 조건에서만 재로그인을 요구하는 회귀 테스트 포함. |
| 94 | 통합·보안·문서 | E2E | 확장앱 핵심 흐름 E2E 작성 | 전체 | Chrome 확장 | Allow/Warn/Mask/Block fixture 테스트 | 됨 | 현재 확장앱 테스트는 있음. 실제 API E2E는 서버 구현 뒤 필요. |
| 95 | 통합·보안·문서 | E2E | 선택자 변경 회귀 테스트 작성 | 전체 | Chrome 확장 | remote selector update fixture | 부분 | 확장앱 fixture는 있음. 실제 config endpoint가 필요. |
| 96 | 통합·보안·문서 | 통합 | Analyze API 통합·성능 테스트 | 전체 | 서버·보안 | happy/error path, p95 500ms 측정 | 안됨 | Python API performance tests. |
| 97 | 통합·보안·문서 | 통합 | Dashboard 통합·성능 테스트 | 전체 | 대시보드·UI | 30일 summary/user stats p95 측정 | 안됨 | dashboard/API 테스트 작성. |
| 98 | 통합·보안·문서 | 품질 | 한국어 FP/FN corpus 평가 | 전체 | 기획·QA·문서 | PII/secret/업무문맥 positive·negative 리포트 | 안됨 | corpus and report. |
| 99 | 통합·보안·문서 | 문서 | README·설치·reverse proxy 문서 작성 | 전체 | 기획·QA·문서 | README, install.md, HTTPS guide | 안됨 | after compose/API shape. |
| 100 | 통합·보안·문서 | 문서 | 관리자·privacy·기여 문서 작성 | 전체 | 기획·QA·문서 | admin-guide, privacy-design, contributing | 안됨 | 대시보드/API privacy 동작 확정 후 작성. |
| 101 | 통합·보안·문서 | 릴리즈 | Docker image·확장앱 패키지 빌드 | 전체 | Chrome 확장 | release artifact, sideload zip, version 확인 | 안됨 | 전체 MVP 완료 뒤 release plan 작성. |
| 102 | 통합·보안·문서 | 마감 | 최종 smoke test와 데모 시나리오 정리 | 전체 | 대시보드·UI | setup→회원가입→Extension→Dashboard 데모 | 안됨 | 최종 end-to-end demo 작성. |

## 17. 담당자별 AI 작업 지시

이 섹션은 WBS 문서 순서 작업표를 이름별로 다시 묶은 실행용 요약이다. 세부 항목의 원본 순서와 상태 판단은 `16. WBS 문서 순서 기준 작업표`를 우선한다.

### 김현성

구현 범위: 확장앱, API 경계, Analyze 요청 검증, 원문보호, idempotency, HMAC hash, 계약정보 분류, custom filter API/pipeline, overlap merge.

- 관련 WBS 행: 28, 29, 30, 31, 44, 49, 52, 53, 57-73.
- 읽을 단원: `6. 인증·세션·권한 계약`, `7. API 경계와 상세 계약`, `10. 탐지·마스킹·점수·custom filter 계약`, `11. 확장앱 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 구현 위치: `apps/extension/*`, 향후 `apps/api/*`의 analyze/custom filter/idempotency/hash 관련 모듈, extension API adapter와 테스트.
- 선행 작업: Python API scaffold, auth context, PostgreSQL idempotency/event table, OpenAPI 출력.
- 남은 구현: 실제 self-host API smoke, request schema 검증, raw prompt logging 차단, `client_request_id` 중복 처리, workspace-scoped HMAC `prompt_hash`, custom filter CRUD/pipeline, overlap merge.
- 완료 PR 기준: 확장앱 DOM hook 회귀가 유지되고, 실제 `/auth/me`, `/config/extension`, `/prompts/analyze` 호출이 통과하며, raw prompt와 full masked prompt가 DB/log/error/dashboard에 남지 않는다.
- 테스트 방법: `python apps/extension/tests/run_extension_checks.py all`, `cd apps/api && pytest tests/analyze tests/privacy tests/custom_filters`.

### 김영은

구현 범위: 대시보드 화면, setup/login 화면, overview/events 화면, secret detector, 영업기밀·내부전략 context classifier.

- 관련 WBS 행: 39, 40, 41, 42, 46, 74, 75, 76, 77, 78, 79.
- 읽을 단원: `8. 제품 범위와 저장소 구조`, `10. 탐지·마스킹·점수·custom filter 계약`, `12. 대시보드 계약`, `13. 보안·개인정보 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 구현 위치: 향후 `apps/dashboard/*`, 대시보드 setup/auth/overview/events API 연동부, secret detector와 classifier 테스트.
- 선행 작업: dashboard scaffold, setup/auth API, metadata-only summary/events API, session auth guard.
- 남은 구현: setup/login flow, overview 카드·추이 차트, events 목록·필터·상세, GitHub/AWS/JWT/PEM/DB URI/.env/entropy 탐지, 내부전략 context classifier.
- 완료 PR 기준: 대시보드는 metadata-only로 동작하고, overview는 이벤트별·사용자별·기간별 통계를 보여주며, events 상세는 원문·full masked prompt·원문 탐지값·원본 파일명을 표시하지 않는다.
- 테스트 방법: `cd apps/dashboard && npm test`, `cd apps/api && pytest tests/detectors tests/dashboard tests/privacy`.

### 김민지

구현 범위: invite/signup/user management API, event metadata DB/service, rule pack, ambiguous scoring, custom filter dry-run, dashboard management UI.

- 관련 WBS 행: 24, 25, 26, 32, 33, 43, 47, 51, 81, 82, 83, 84, 85, 86, 87, 88.
- 읽을 단원: `6. 인증·세션·권한 계약`, `9. 데이터 모델·원문 저장 금지 계약`, `10. 탐지·마스킹·점수·custom filter 계약`, `12. 대시보드 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 구현 위치: 향후 `apps/api/*`의 auth/admin/event/custom-filter/rule-pack 모듈, `apps/dashboard/*`의 users/invites/policy/custom filter/status 화면.
- 선행 작업: PostgreSQL migration, setup/bootstrap, dashboard session auth, event metadata table.
- 남은 구현: invite/registration/user role/status API, event metadata 저장 서비스, rule pack 구조, ambiguous 처리, custom filter dry-run, user stats 표·차트, users/invites/policy/custom filter/status UI.
- 완료 PR 기준: 모든 dashboard/API 응답은 metadata-only이고, invite/user/custom-filter/status flow가 권한·CSRF·privacy 회귀 테스트를 통과한다.
- 테스트 방법: `cd apps/api && pytest tests/auth tests/events tests/custom_filters tests/privacy`, `cd apps/dashboard && npm test`.

### 유지수

구현 범위: Python API 기반 구조, Docker/PostgreSQL, migration, auth/RBAC, CORS/rate limit, PII/localized detectors, server-side masking, Analyze orchestrator, user stats API.

- 관련 WBS 행: 27, 34, 35, 36, 37, 38, 45, 48, 55, 56, 80.
- 읽을 단원: `3. 서버·실행환경·인프라 계약`, `4. 상태 확인 계약`, `5. HTTP 오류 계약`, `6. 인증·세션·권한 계약`, `7. API 경계와 상세 계약`, `9. 데이터 모델·원문 저장 금지 계약`, `10. 탐지·마스킹·점수·custom filter 계약`.
- 구현 위치: 향후 `apps/api/*`, `infra/compose.yaml`, `.env.example`, Alembic migration, detector/masking/orchestrator modules.
- 선행 작업: repository scaffold, API dependency setup, PostgreSQL connection, settings loader, migration baseline.
- 남은 구현: FastAPI scaffold, `/livez`, `/readyz`, `/healthz`, auth/setup/RBAC, CORS/rate limit, PII/localized detectors, masking, Analyze orchestrator, user stats API.
- 완료 PR 기준: Redis 없는 기본 Compose에서 API/PostgreSQL이 올라가고, health/status/auth/detector/masking/analyze/user stats 테스트가 통과한다.
- 테스트 방법: `cd apps/api && pytest`, Docker smoke 후 `/livez`, `/readyz`, `/healthz`, setup/login/analyze/dashboard summary smoke.

### 전체

구현 범위: custom regex safety, 위험 점수, privacy/security tests, E2E, performance, corpus, release/docs, final demo.

- 관련 WBS 행: 50, 54, 89-102.
- 읽을 단원: `13. 보안·개인정보 계약`, `15. 테스트·완료·릴리즈 게이트`, `16. WBS 문서 순서 기준 작업표`.
- 남은 구현: custom regex ReDoS 방어, scoring policy, dashboard 원문 미노출 테스트, DB/log/error privacy scan, 외부 LLM 호출 금지 검증, API/dashboard/extension 통합·성능 테스트, 한국어 FP/FN corpus, README/install/admin/privacy/contributing 문서, release artifact, final smoke/demo.
- 완료 PR 기준: API, dashboard, extension build/test와 privacy regression, no external LLM verification, Docker fresh-install smoke, setup -> user -> extension -> analyze -> dashboard demo가 모두 통과한다.
- 테스트 방법: 각 영역 테스트 명령, privacy regression, Docker smoke, final demo scenario.
