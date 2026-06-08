# PromptGuard 개발 문서 세트 1.0.2 - 팀 통합본

## 목차

1. 문서 기준과 범위 원칙
2. MVP 확정 결정과 용어
   - 2.1 MVP 용어와 범위 규칙
3. MVP 제품 범위와 저장소 구조
   - 3.1 제품 범위
   - 3.2 저장소와 코드 위치
4. MVP 서버·실행환경·인프라 계약
   - 4.1 인프라/배포 하위 범위
5. MVP 상태 확인 계약
   - 5.1 엔드포인트
   - 5.2 상태 응답 형식
6. MVP HTTP 오류 계약
   - 6.1 응답 형식
   - 6.2 상태 코드와 오류 출처 구분 기준
7. MVP 인증·세션·권한 계약
   - 7.1 식별자와 인증
   - 7.2 인증·세션·권한 상세 계약
   - 7.3 확장앱 token auth와 대시보드 session auth 분리
8. MVP API 경계와 상세 계약
   - 8.1 전송 시도 분석 경계
   - 8.2 파일/첨부 입력 경계
   - 8.3 확장앱 설정 경계
   - 8.4 MVP API 목록과 권한 경계
   - 8.5 대시보드 이벤트 조회 계약
   - 8.6 ADMIN 사용자 관리 API 계약
   - 8.7 Filter Rule 관리 API 계약
   - 8.8 대시보드 서버 상태 조회 계약
9. MVP PostgreSQL 데이터 모델 계약
   - 9.1 주요 테이블
   - 9.2 테이블별 핵심 컬럼
   - 9.3 인덱스와 삭제 규칙
10. MVP 탐지·마스킹·점수·Filter Rule 실행 계약
    - 10.1 분석 파이프라인 순서
    - 10.2 Detector 및 Filter Rule 종류
    - 10.3 Context Rule 점수화
    - 10.4 Overlap 및 우선순위
    - 10.5 위험도와 Action 결정
    - 10.6 마스킹
    - 10.7 실행 설정과 Dry-run
11. MVP 확장앱 계약
    - 11.1 확장앱 하위 범위
    - 11.2 Action UX
    - 11.3 재전송과 중복 방지
    - 11.4 설정과 selector
    - 11.5 확장앱 저장소와 금지사항
12. MVP 대시보드 계약
    - 12.1 대시보드 화면
    - 12.2 대시보드 화면 계약
    - 12.3 화면별 조회·통계 API 계약
    - 12.4 대시보드 보안·표시 규칙
13. MVP Analyze 요청 처리 한도와 환경변수 계약
    - 13.1 Analyze 요청 크기 한도
    - 13.2 파일 text 처리 한도
    - 13.3 환경변수 계약
    - 13.4 확장앱 설정 응답과 환경변수 매핑
    - 13.5 테스트 기준
14. MVP 보안·개인정보 계약
    - 14.1 MVP 보안 기준
15. MVP 수용 기준·테스트 게이트
    - 15.1 MVP 수용 기준
    - 15.2 영역별 완료 기준
    - 15.3 MVP 기능 시연 게이트
    - 15.4 테스트 명령 매트릭스
    - 15.5 최종 smoke 시나리오
16. MVP 이후 제품 기능 범위
17. MVP 이후 서버·인프라·운영 범위
18. MVP 이후 API·데이터·Analyze 범위
19. MVP 이후 탐지·Filter Rule·파일 분석 범위
20. MVP 이후 확장앱·대시보드 범위
21. MVP 이후 보안·개인정보·재현성 보강 범위
22. MVP 이후 범위 검증 기준
23. MVP/WBS 작업 정리

## 1. 문서 기준과 범위 원칙

- 이 문서는 PromptGuard의 제품 개발 계약, MVP 범위, 구현범위, API 경계, 데이터 소유권, WBS 작업 지시를 함께 다루는 통합 개발 문서다.
- 서버 언어는 Python 3.13으로 고정한다.
- PostgreSQL은 그대로 쓴다.
- Redis는 MVP 기본 필수가 아니다. 로그인 유지, 갱신 토큰, 중복 요청 처리의 영속 기준은 PostgreSQL이 맡는다.
- mock, client fixture, schema, stub, UI shell이 있다고 해서 실제 API, 인증, DB 저장, end-to-end 통합 흐름이 구현된 것으로 보지 않는다.
- 특정 에이전트 세션, 임시 작업 순서, 대화 참여자만 아는 내부 진행 기록은 제품 요구사항 본문에 섞지 않는다.
- PR 번호, 구현 근거, 현재 repo 상태, 올라온 PR 상태는 필요한 경우 구현 상태 또는 WBS 상태 판단 근거로 기록할 수 있다.
- 2\~14장은 기능 시연 MVP 구현 계약을 정의한다.
- 15장은 MVP 수용 기준과 테스트 게이트를 정의한다.
- 16\~21장은 MVP 범위 밖의 제품 기능, 운영, API, 데이터, 탐지, 확장앱, 대시보드, 보안·재현성 보강 범위를 정의한다.
- 22장은 MVP 이후 범위를 구현할 때의 검증 기준을 정의한다.
- 23장은 실제 WBS/MVP 작업표를 정의한다.

### 1.1 문서 목적

- 이 문서는 PromptGuard MVP의 product/API/DB/UI/WBS 기준과 현재 구현 상태별 필요한 조치를 정리한 최신 작업 기준 문서다.
- 미완성 코드, static/mock page, stub route, schema 일부, fixture, build artifact가 있다는 이유로 MVP 요구사항을 낮추지 않는다.
- Dashboard Session API는 MVP scope에 남아 있다. 현재 bearer 기반 ADMIN 보호가 일부 있더라도, dashboard session cookie + CSRF 계약을 대체하지 않는다.

### 1.2 판정 기준

- 23.1의 `부분`, `교체 필요`, `미구현` 행은 현재 구현된 것, 아직 MVP 완료가 아닌 이유, 다음 작업을 plain language로 설명한다.
- static/mock page, placeholder UI, schema 일부, route stub, fixture, build artifact는 단독으로 MVP 완료 근거가 아니다.
- 현재 구현 상태가 MVP 계약과 다르면 요구사항을 낮추지 않고, 필요한 교체·보강 작업을 WBS에 명확히 남긴다.

## 2. MVP 확정 결정과 용어

- 서버 언어: Python 3.13.
  - 이유: 탐지기, 규칙 분류기, 마스킹, 개인정보 회귀 테스트, 향후 로컬 분석 확장에 Python 생태계가 유리하다.
- 데이터베이스: PostgreSQL.
  - 이유: 사용자, 필터 규칙, 이벤트 metadata, 중복 요청 처리, 토큰 해시는 영속 트랜잭션과 마이그레이션이 필요하다.
- 초기 접근 흐름: 기본 ADMIN 계정 포함 + login-first.
  - fresh install 후 DB migration/초기 데이터 생성 단계가 완료되면 기본 ADMIN 계정이 이미 존재해야 한다.
  - 사용자는 처음 접속하면 로그인 화면을 본다.
  - 기본 계정은 `admin / 1234`, role `ADMIN`이다.
  - `1234`는 초기 비밀번호일 뿐이며 반드시 `password_hash`로만 저장한다. 평문 비밀번호는 DB, 로그, 오류 응답, audit metadata, 대시보드, 테스트 snapshot에 남기지 않는다.
  - 운영 문서에는 기본 비밀번호가 실제 운영에 안전하지 않으며 반드시 변경해야 한다고 명시한다. MVP 로그인 UI에는 별도 비밀번호 변경 경고 배너가 필수는 아니다.
  - 사용자가 첫 관리자 계정을 직접 생성하거나 활성화하는 초기 설정 화면, 초기 설정 API, 가입 흐름은 MVP 범위에 포함하지 않는다.
- 사용자 관리는 ADMIN이 직접 수행한다.
  - ADMIN은 `/dashboard/users`에서 USER 또는 ADMIN을 생성하고 role/status를 변경한다.
  - USER는 대시보드에 접근하지 않는다. Chrome Extension을 통해 extension config와 `POST /prompts/analyze` 기반 send attempt 분석 같은 허용된 보호 API만 사용한다.
  - hard delete는 MVP에서 제외하고, 사용자 제거는 `DISABLED` 상태로 처리한다.
- Chrome 확장앱: Manifest V3 + TypeScript.
- 대시보드: ADMIN 전용 metadata UI이며 원문 데이터는 표시하지 않는다.
- 대시보드 프론트엔드: `apps/dashboard/` 아래 HTML/CSS/TypeScript 기반 multi-page static dashboard.
  - 대시보드는 React, Vue, Svelte, Next.js 같은 프론트엔드 프레임워크를 사용하지 않는다.
  - 대시보드 페이지는 `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`처럼 화면별 HTML 파일로 구성한다.
  - 각 HTML 파일은 화면 entry 역할을 한다. 사용자 목록, 이벤트 목록, 이벤트 상세, 필터 규칙, 상태 정보 같은 실제 데이터는 해당 화면의 TypeScript 코드가 FastAPI API를 호출해 조회하고 화면에 렌더링한다.
  - API 계약은 대시보드에서도 그대로 핵심이다. 정적 HTML 구조는 프론트엔드 서버와 프레임워크를 쓰지 않는다는 뜻이지, API 없이 고정 데이터를 표시한다는 뜻이 아니다.
  - TypeScript source는 `apps/dashboard/src/**/*.ts`에 두고, `npm run build`로 브라우저용 JavaScript인 `apps/dashboard/static/*.js`로 컴파일한다.
  - 각 HTML 파일은 컴파일된 `static/*.js`와 공통 CSS를 직접 로드한다.
  - 대시보드 변경은 `cd apps/dashboard && npm run typecheck`, `npm run build`로 검증한다.
  - 운영 배포에서 Vite dev server, Flask/Jinja template server, React/Vue/Next.js runtime, 별도 dashboard 전용 서버를 필수 구성으로 두지 않는다.
  - CSRF, XSS, session cookie 같은 대시보드 보안 규칙은 인증/보안 섹션의 계약을 따른다.
- 필터 관리 모델: 단일 Filter Rule 모델.
  - 기본 탐지 규칙, 사용자 정의 keyword 필터, 사용자 정의 regex 필터, Business Context 문맥 규칙은 하나의 `filter_rules` 모델과 하나의 Filter Rule 관리 화면에서 관리한다.
  - 처음부터 들어 있는 기본 탐지 규칙과 나중에 사용자가 추가하는 필터 규칙은 같은 Filter Rule 기반 코드, 같은 목록 화면, 같은 dry-run 흐름, 같은 실행 파이프라인을 사용한다.
  - 규칙 종류는 `detector`, `keyword`, `regex`, `context_rule`로 구분한다.
  - 공통 필드는 `label`, `severity`, `action`, `enabled`, `description`, `placeholder`, `config_json`을 기본으로 한다.
  - `keyword` 규칙은 keyword 목록과 제외 keyword를 가진다.
  - `regex` 규칙은 regex pattern을 가진다.
  - `context_rule`은 Business Context 탐지를 위한 keyword 그룹, 제외 keyword, window 크기, 최소 조건 수, sensitivity 같은 설정을 가진다.
  - 기본 탐지 규칙은 삭제할 수 없고 `enabled`, `severity`, `action`만 수정할 수 있다.
  - 기본 탐지 규칙의 내부 parser, checksum, entropy, detector regex, URI/private-key parser는 수정할 수 없다.
  - 사용자가 추가한 `keyword`, `regex`, `context_rule` 규칙은 추가, 수정, 삭제, 켜기/끄기가 가능해야 한다.
  - dry-run은 입력 샘플에 대해 탐지 여부, 예상 action, 예상 severity, 탐지 유형, match count, reason code를 보여준다.
  - dry-run sample은 저장하지 않는다.
- API 계약은 이 문서의 API 경계와 각 endpoint 계약을 기준으로 한다.
- `apps/api`의 실제 구현, Pydantic schema, 생성된 OpenAPI 산출물은 이 문서의 API 계약과 대조해야 하는 구현 산출물로 본다.
- 서버 구현 스택: Python 3.13 + FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic.
- Redis: 선택 구성.

### 2.1 MVP 용어와 범위 규칙

아래 용어를 코드, API 계약, WBS 티켓, PR 설명, 대시보드 문구에서 일관되게 사용한다.

| 사용할 용어                 | 의미                                                                                                                             | 혼동하면 안 되는 것                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| Filter Rule            | 관리자 필터 화면에 표시되는 하나의 탐지 규칙                                                                                                      | 별도 설정 화면/모듈                              |
| Filter Config          | 기본 탐지 설정, 사용자 keyword/regex 규칙, context rule을 합친 실제 실행 설정                                                                      | 별도 규칙 관리 모듈                              |
| Filter Config Revision | 확장앱 설정 동기화를 위한 단순 설정 revision metadata                                                                                         | Filter Rule 변경 이력 또는 이벤트 상세 UI 표시 필드     |
| 기본 ADMIN 계정            | fresh install 후 DB migration/초기 데이터 생성 단계가 끝나면 이미 존재하는 초기 `admin / 1234` 계정                                                    | 사용자가 별도 절차로 만드는 계정                       |
| Dashboard session      | 대시보드 ADMIN 전용 cookie session                                                                                                   | 확장앱 bearer token                         |
| Extension token flow   | Chrome 확장앱이 사용하는 USER/ADMIN bearer-token 흐름                                                                                    | 대시보드 session                             |
| 원격 확장앱 설정              | `/config/extension`이 반환하는 selector, timeout, file limit, 선택적 filter config revision                                            | 코드에만 고정된 selector 목록                     |
| Analyze Input Bundle   | 사용자가 보내려는 text 입력, 파일 text 입력, attachment metadata, unsupported attachment를 `kind`, `source`, `content_included`로 구분해 담는 입력 묶음 | 모든 입력을 단일 prompt text로 취급                |
| Attachment Metadata    | 첨부파일/이미지/서비스 attachment chip의 extension, MIME, size, count, attachment kind, attachment index 같은 metadata-only 표현              | raw file bytes, base64, OCR text, 원본 파일명 |

구현 규칙:

- Filter Rule Management와 분리된 독립 설정 화면은 만들지 않는다.
- fresh install 후 기본 ADMIN 계정이 이미 존재한다.
- 사용자는 로그인 화면에서 기본 ADMIN 계정으로 로그인한다.
- ADMIN은 대시보드의 사용자 관리 화면에서 USER 또는 ADMIN 계정을 생성하고 상태를 관리한다.
- 이벤트 상세 UI에는 내부 버전 식별자를 표시하지 않는다.
- `filter_config_revision`은 확장앱 설정 동기화용 revision metadata로만 사용한다. Filter Rule 변경 이력과 과거 rule set 재현성은 운영 전 보강 항목으로 둔다.
- 서버 상태 UI는 8.8의 필수/선택 상태 metadata만 표시한다.

## 3. MVP 제품 범위와 저장소 구조

이 단원은 MVP 제품 범위와 코드 위치를 정의한다. 상세 구현 계약은 API, 데이터, 탐지, 확장앱, 대시보드 단원을 따른다.

### 3.1 제품 범위

제품 목적:

- 사용자가 ChatGPT 같은 AI 서비스에 민감한 업무 정보, 개인정보, 비밀값, 계약 정보, 파일 내용을 보내기 전에 위험을 판별한다.
- 서버는 한 번의 전송 시도(send attempt)를 분석하고, 관리자는 대시보드에서 metadata와 통계를 본다.
- self-hosted 환경에서 관리자가 서버와 DB를 운영하고, 팀원은 Chrome Extension으로 보호 흐름을 사용한다.

MVP 포함:

- self-hosted API 서버 실행.
- fresh install 후 기본 ADMIN 계정으로 login-first 흐름 제공.
- ADMIN 기반 사용자 생성, role 변경, status 변경.
- Chrome Extension의 AI 서비스 입력 탐지, 전송 보류, `POST /prompts/analyze` 호출, Allow/Warn/Mask/Block 처리.
- `POST /prompts/analyze` 기반 send attempt 분석.
- `inputs[]` 기반 composer text, converted paste, file text, attachment metadata, unsupported attachment 표현.
- 허용된 작은 text file scan.
- rule-based detector, 통합 Filter Rule 모델, 위험 점수 계산, 서버 측 composer text 마스킹, 중복 요청 처리.
- `client_request_id` 기반 중복 event 방지와 metadata-only event 저장.
- ADMIN 대시보드 login, overview, events, event detail, users, Filter Rule management, server status 화면.
- Docker 기반 실행, 설치 문서, 기본 privacy smoke, 최종 smoke 시나리오.

MVP에서는 여러 입력과 여러 탐지 결과가 동시에 존재하더라도 서버가 단순 우선순위 `Block > Mask > Warn > Allow`로 전송 시도 전체의 최종 `action` 하나를 반환한다. 프론트엔드는 그 top-level action만 따른다.

### 3.2 저장소와 코드 위치

| 대분류    | 소분류                                                | 기본 위치                               | 설명                                                                                                                                                                                                                                         |
| ------ | -------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| API 서버 | Python 3.13 self-hosted API                        | `apps/api/`                         | `python:3.13-slim` 기준 FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic. API schema, auth, detector, unified Filter Rule, masking, event metadata, dashboard API를 포함한다.                                                                        |
| 대시보드   | HTML/CSS/TypeScript 기반 multi-page static dashboard | `apps/dashboard/`                   | `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html` 같은 화면별 HTML 파일과 `apps/dashboard/src/**/*.ts`를 구현 원천으로 한다. TypeScript는 `npm run build`로 `apps/dashboard/static/*.js`에 컴파일한다. |
| 확장앱    | Chrome Extension                                   | `apps/extension/`                   | content script, service worker, options, shared types/tests, real API 연동을 유지한다.                                                                                                                                                            |
| 인프라    | Docker/env                                         | 루트 `compose.yml`, 루트 `.env.example` | Docker Compose, PostgreSQL, 선택 Redis profile, 환경변수 예시는 루트 파일에서 관리한다.                                                                                                                                                                       |
| 운영 문서  | 설치/운영 안내                                           | `docs/` 또는 `docs/references/`       | 설치 안내, HTTPS/도메인 배포 안내, 선택 reverse proxy 예시, 확장앱 sideload/package 안내, privacy/security guide, 관리자 안내를 둔다.                                                                                                                                  |
| 테스트    | 단위/통합/보안/회귀                                        | 각 app의 `tests/` 또는 root tests       | 앱별 단위 테스트와 cross-app privacy/security smoke를 둔다.                                                                                                                                                                                           |

대시보드 파일 기준:

- 각 HTML 파일은 하나의 상위 화면 entry다.
- 실제 데이터 조회와 상태 변경은 TypeScript 코드가 FastAPI API를 호출해 처리한다.
- `static/*.js`는 TypeScript build 산출물이다.
- MVP 배포 기준에서는 FastAPI 서버가 API와 dashboard 정적 파일을 함께 제공한다.
- 운영 환경에서 HTTPS, 도메인 연결, TLS 인증서 종료, 경로 라우팅이 필요한 경우 reverse proxy 예시 구성을 제공한다.

## 4. MVP 서버·실행환경·인프라 계약

아래 기준을 서버·실행환경 구현 기준으로 사용한다.

1. Python 3.13 웹 프레임워크는 FastAPI로 구현한다.
   - 이유: Python 타입 힌트와 Pydantic 기반 검증, OpenAPI 자동 생성, Swagger/ReDoc 문서화 흐름이 PromptGuard API 계약과 잘 맞는다.
2. Python 요청/응답 검증은 Pydantic v2로 구현한다.
   - 이유: FastAPI와 잘 결합되고, 요청/응답 schema를 OpenAPI로 내보내기 쉽다.
3. ORM/마이그레이션은 SQLAlchemy 2.x + Alembic으로 구현한다.
   - 이유: Python PostgreSQL 앱에서 표준적인 ORM/SQL 도구 + 마이그레이션 조합이고, 검토 가능한 마이그레이션 스크립트를 만들 수 있다.
4. Redis는 기본 Compose에서 제외하고 선택 profile로만 둔다.
   - 이유: 기본 MVP 실행에서는 로그인 유지와 빠른 응답 자체에 Redis가 필수는 아니다. Redis는 다중 서버 요청 한도 상태 저장소, 분산 잠금, 큐, 캐시가 필요해지는 경우 선택 구성으로 사용한다.
5. 구현 중 위 기준을 유지하기 어렵다는 근거가 나오면 대체안을 기록하고 범위를 재확정한다.

### 4.1 인프라/배포 하위 범위

- 개발 실행:

  - 루트 script는 확장앱, 대시보드 JS workspace, Python API 실행을 혼동하지 않게 분리한다.
  - API는 Python 가상환경 또는 Docker 기준으로 실행한다.
  - 확장앱은 기존 build/test 흐름을 유지한다.
  - 대시보드는 `apps/dashboard` 기준으로 typecheck, build, 로컬 실행 smoke를 수행한다.

- Docker:

  - MVP 기본 구성은 API와 PostgreSQL이다.
  - API base image는 `python:3.13-slim`을 사용한다.
  - 대시보드는 HTML/CSS/TypeScript 기반 정적 파일 산출물로 배포한다.
  - MVP 배포 기준에서는 FastAPI 서버가 API와 dashboard 정적 파일을 함께 제공한다.
  - Redis는 필요할 때 켤 수 있는 선택 profile로 제공한다.
  - 운영 환경에서 HTTPS, 도메인 연결, TLS 인증서 종료, 경로 라우팅이 필요한 경우 reverse proxy 예시 구성을 제공한다.
  - 상태 확인은 `/livez`, `/readyz`, `/healthz`를 사용한다.

- 운영 문서:

  - `.env.example`
  - 설치 안내
  - HTTPS/도메인 배포 안내
  - 선택 reverse proxy 예시
  - 확장앱 sideload/package 안내
  - privacy/security guide
  - 관리자 안내

## 5. MVP 상태 확인 계약

이 섹션은 HTTP 상태 코드의 일반 의미를 기준으로 PromptGuard의 상태 확인 endpoint를 정의한다.

### 5.1 엔드포인트

| 엔드포인트                   | 목적                             | 인증             | HTTP 상태 규칙                                                                       |
| ----------------------- | ------------------------------ | -------------- | -------------------------------------------------------------------------------- |
| `GET /livez`            | 프로세스가 살아 있고 요청 처리기가 응답 가능한지 확인 | 공개 또는 내부       | 프로세스가 응답 가능하면 `200`, 응답 불가하면 응답 자체가 실패                                           |
| `GET /readyz`           | 서버가 트래픽을 받아도 되는지 확인            | 내부 권장          | 설정 유효, DB 연결 가능, 마이그레이션 최신, 기본 필터 설정 로드 가능이면 `200`; 핵심 의존성이 불가하면 `503`           |
| `GET /healthz`          | 운영자용 집계 상태                     | 내부 또는 ADMIN 권장 | 핵심 기능 가능하면 `200`; 선택 의존성만 문제면 body `status=degraded`와 함께 `200`; 핵심 의존성 불가면 `503` |
| `GET /dashboard/status` | 대시보드가 쓰는 서버 상태 API             | ADMIN          | `/healthz`와 같은 상태 metadata를 인증된 대시보드 형식으로 반환                                     |

상태 확인 endpoint는 Docker Compose 실행과 fresh install 검증에 사용한다. 준비 상태 확인이 실패하면 MVP smoke를 통과한 것으로 보지 않는다.

### 5.2 상태 응답 형식

```json
{
  "status": "healthy",
  "service": "promptguard-api",
  "version": "app-build-version",
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
      "name": "filter_rules",
      "status": "healthy",
      "required": true,
      "code": "FILTER_RULES_READY",
      "message": "Default filter rules can be loaded"
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
- `unhealthy`: 필수 의존성, 설정, 마이그레이션, 필터 규칙 상태가 정상 서비스를 막는다.

허용되는 의존성 상태:

- `healthy`
- `degraded`
- `unhealthy`
- `disabled`
- `unknown`

상태 응답에 넣으면 안 되는 필드:

- 입력 본문, 파일 내용, 전체 `masked_prompt`
- access token, refresh token, dashboard session id, password\_hash, JWT secret, refresh secret, DB 연결 문자열, 서버 secret 값
- 스택 추적 또는 원문 예외 메시지
- 원본 파일명 또는 원문 탐지값

## 6. MVP HTTP 오류 계약

### 6.1 응답 형식

PromptGuard가 직접 발생시키는 업무/API 오류는 RFC 9457의 `application/problem+json` 호환 필드를 사용하고, PromptGuard 전용 `code` 필드로 세부 원인을 구분한다.

FastAPI/Pydantic request validation error는 FastAPI 기본 `422` 응답 형식을 따른다. 이 오류는 별도 구현 없이 FastAPI가 요청 schema/type/required field 오류를 처리하는 기본 흐름으로 둔다.

Dashboard TypeScript API client는 다음 두 응답을 모두 처리할 수 있어야 한다.

- PromptGuard 업무/API 오류: `application/problem+json` + `code`
- FastAPI/Pydantic validation 오류: 기본 `422` JSON 응답의 `detail[]`

### 6.2 상태 코드와 오류 출처 구분 기준

PromptGuard는 HTTP status code를 표준 의미에 맞게 사용하고, 프론트엔드 정적 파일 오류와 API 오류는 요청 경로, 응답 형식, `code` 값으로 구분한다.

대시보드는 FastAPI 서버가 정적 HTML/CSS/JavaScript 파일을 서빙하지만, 정적 파일 요청 실패를 API business error로 취급하지 않는다.

| 상태                           | API에서 쓰는 경우                                                                                                                                 | Dashboard 정적 파일 요청에서 쓰는 경우                                                | 이 경우에는 쓰지 않음                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------- |
| `400 Bad Request`            | FastAPI validation 흐름 밖에서 명시적으로 잘못된 요청으로 처리해야 하는 경우                                                                                         | 사용하지 않음                                                                   | FastAPI/Pydantic request validation error |
| `401 Unauthorized`           | access token, refresh token, dashboard session이 없거나, 유효하지 않거나, 만료됐거나, 형식이 잘못됨                                                               | 보호된 dashboard page 접근에 유효한 session이 없을 때 login page로 redirect하거나 `401` 처리 | 유효한 인증 context는 있지만 역할 권한이 부족한 경우         |
| `403 Forbidden`              | 인증된 사용자의 권한 부족, 비활성 사용자, USER가 ADMIN route 호출                                                                                               | dashboard session은 있지만 ADMIN 권한이 부족한 경우                                   | 권한상 resource 존재 자체를 숨겨야 하는 경우             |
| `404 Not Found`              | API route 없음, resource 없음, 또는 권한상 숨겨야 하는 resource 존재를 의도적으로 숨김                                                                              | 요청한 dashboard HTML page, CSS, JavaScript, image/static asset이 없음          | 일반 인증 실패                                  |
| `409 Conflict`               | 중복 요청 충돌 또는 현재 상태 때문에 처리할 수 없는 요청 충돌                                                                                                        | 사용하지 않음                                                                   | 일반 validation 오류                          |
| `413 Payload Too Large`      | inputs, attachment metadata, request body가 설정된 크기 제한을 초과                                                                                    | 사용하지 않음                                                                   | 탐지 결과가 Block인 경우                          |
| `415 Unsupported Media Type` | 지원하지 않는 content type, attachment kind, 파일 형식 metadata                                                                                       | 사용하지 않음                                                                   | schema/type/required field 오류             |
| `422 Unprocessable Content`  | FastAPI/Pydantic request validation error, schema/type/required field 오류, 업무 의미 검증 오류. 예: 잘못된 custom regex, 불가능한 필터 설정 전환, 지원하지 않는 rule 표현식 | 사용하지 않음                                                                   | 인증 실패, 권한 부족                              |
| `429 Too Many Requests`      | 요청 한도 초과                                                                                                                                    | 정적 파일 요청에는 기본 적용하지 않음. 필요한 경우 reverse proxy나 서버 공통 rate limit에서 처리        | 인증 실패                                     |
| `500 Internal Server Error`  | 예상하지 못한 서버 실패                                                                                                                               | 정적 파일 서빙 중 예상하지 못한 서버 실패                                                  | 예상 가능한 의존성 장애                             |
| `503 Service Unavailable`    | 필수 의존성 불가, migration 미준비, 서버 미준비                                                                                                            | 서버가 dashboard 파일을 서빙할 준비가 안 된 경우                                          | 선택 Redis 비활성화                             |

API 오류와 dashboard 정적 파일 오류 구분:

- API endpoint의 PromptGuard 업무 오류는 `application/problem+json` 형식을 사용한다.
- FastAPI/Pydantic request validation error는 FastAPI 기본 `422` JSON 응답 형식을 따른다.
- Dashboard HTML/CSS/JavaScript/static asset 요청 실패는 API business error가 아니다.
- Dashboard 정적 파일 요청 실패는 브라우저의 일반 page/static asset 로딩 실패로 처리한다.
- Dashboard TypeScript API client는 API 응답의 HTTP status, content type, `code`, 또는 FastAPI validation `detail[]`을 기준으로 오류 처리를 분기한다.

`404 Not Found` 세부 구분:

| `code`                       | 쓰는 경우                                                  | 응답 형식                       |
| ---------------------------- | ------------------------------------------------------ | --------------------------- |
| `DASHBOARD_PAGE_NOT_FOUND`   | 요청한 dashboard HTML page가 없음                            | HTML 또는 plain text 오류 응답    |
| `DASHBOARD_STATIC_NOT_FOUND` | 요청한 dashboard CSS/JavaScript/static asset이 없음          | plain text 또는 기본 static 404 |
| `API_ROUTE_NOT_FOUND`        | 요청한 API route가 없음                                      | `application/problem+json`  |
| `RESOURCE_NOT_FOUND`         | API route는 맞지만 요청한 resource가 없거나, 존재를 숨겨야 하는 resource임 | `application/problem+json`  |

`403`과 `404` 구분:

- client가 인증되어 있고 route/resource 존재를 알아도 안전하지만 권한만 부족하면 `403`을 쓴다.
- resource 존재를 드러내는 것 자체가 정보 유출이면 `404`를 쓴다.
- 이 경우 `RESOURCE_NOT_FOUND`를 사용하고, 응답 메시지는 resource 존재 여부를 확정하지 않는 문구로 둔다.

`409`와 중복 요청 구분:

- 같은 `login_id`와 같은 `client_request_id` 조합이 이미 처리된 경우 가능한 한 기존 event/idempotency metadata를 재사용하고 두 번째 event를 만들지 않는다.
- `Mask`의 경우 replay를 위해 전체 `masked_prompt`를 저장하지 않는다.
- 기존 응답 재사용이 불가능하면 `409 DUPLICATE_REQUEST_RETRY_REQUIRED`를 반환하고, 확장앱은 원래 전송 시도를 다시 분석해야 한다.
- 같은 `client_request_id`에 서로 다른 요청 내용이 들어오는 충돌 감지는 MVP 필수 범위에 포함하지 않는다. 이 충돌 감지를 위한 HMAC 기반 request fingerprint는 운영 전 보강 항목으로 둔다.

## 7. MVP 인증·세션·권한 계약

이 단원은 확장앱 bearer token 흐름과 대시보드 ADMIN session cookie 흐름을 분리해서 정의한다. Chrome Extension MV3 service worker inactive 상태는 인증 만료가 아니다. 대시보드는 ADMIN 전용이며 USER는 대시보드 화면과 대시보드 API에 접근할 수 없다.

### 7.1 식별자와 인증

- `login_id`는 request body가 아니라 인증 토큰 또는 session context에서 온다.
- refresh token 원문 값은 저장하지 않고 PostgreSQL에는 hash와 metadata만 저장한다.
- Chrome Extension MV3 service worker inactive 상태는 인증 만료가 아니다. worker wake-up 후 access token이 만료됐으면 먼저 `POST /auth/refresh`를 시도한다.
- access token, refresh token, dashboard session이 형식상 유효하더라도, DB의 사용자 상태가 `DISABLED`이면 API 처리나 대시보드 접근을 허용하지 않고 `403`을 반환한다.
- 인증된 USER가 ADMIN 전용 route를 호출하면 `403`을 반환한다.
- 기본 ADMIN 계정:
  - fresh install 후 DB migration/초기 데이터 생성 단계가 완료되면 기본 ADMIN 계정 `admin / 1234`가 이미 존재해야 한다.
  - 비밀번호는 일반 사용자와 동일한 password hashing 함수로 해시한다.
  - 평문 `1234`는 DB, 로그, audit metadata, 오류 응답, fixture, 대시보드에 저장하지 않는다.
  - 운영 문서에는 `1234`가 안전하지 않은 초기값이며 실제 운영 전에 변경해야 한다고 명시한다.
- 대시보드 세션 인증은 확장앱 bearer token 인증과 분리한다.
- 대시보드 session은 서버가 관리하는 ADMIN session id를 `HttpOnly` cookie로 전달한다.
- HTTPS 환경의 session cookie는 `Secure`를 사용한다.
- same-site 관리자 UI 기본값은 `SameSite=Lax`로 시작한다.
- 대시보드 session id는 `localStorage`에 저장하지 않는다.
- 대시보드 상태 변경 요청은 CSRF 방어를 적용한다.

### 7.2 인증·세션·권한 상세 계약

| 항목                    | 기본값     | 이유                                                               |
| --------------------- | ------- | ---------------------------------------------------------------- |
| access token TTL      | 900초    | 탈취 피해를 줄이되 refresh로 UX 유지                                        |
| refresh token TTL     | 30일     | MV3 inactive를 로그아웃으로 오판하지 않기 위함                                  |
| refresh idle timeout  | 14일     | 오래 방치된 refresh token 정리                                          |
| refresh rotation      | enabled | refresh 성공 시 이전 token hash 폐기                                    |
| dashboard session TTL | 12시간    | ADMIN cookie session이 무기한 유지되지 않게 하되, 일반적인 작업 시간 동안 재로그인을 줄이기 위함 |

권한 매트릭스:

| Surface                                                       | Public               | USER                                             | ADMIN                                   |
| ------------------------------------------------------------- | -------------------- | ------------------------------------------------ | --------------------------------------- |
| `POST /auth/login`                                            | 가능                   | 가능                                               | 가능                                      |
| `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`     | token 없이는 불가         | 자기 계정 가능                                         | 자기 계정 가능                                |
| `GET /dashboard/session/csrf`                                 | 가능                   | 가능하지만 대시보드 session 생성은 아님                        | 가능하지만 대시보드 session 생성은 아님               |
| `POST /dashboard/session/login`                               | 가능                   | USER credential로는 dashboard session 생성 불가, `403` | ACTIVE ADMIN credential이면 session 생성 가능 |
| `POST /dashboard/session/logout`, `GET /dashboard/session/me` | ADMIN session 없이는 불가 | 대시보드 접근 불가, `403`                                | 가능                                      |
| `GET /config/extension`                                       | 불가                   | 가능                                               | 가능                                      |
| `POST /prompts/analyze`                                       | 불가                   | 가능                                               | 가능                                      |
| Dashboard event/stat/status 조회 API                            | 불가                   | 불가, `403`                                        | 가능                                      |
| ADMIN 사용자 관리 API                                              | 불가                   | 불가, `403`                                        | 가능                                      |
| Filter Rule 관리 API                                            | 불가                   | 불가, `403`                                        | 가능                                      |

계정 상태:

| 상태         | 의미      | 처리                                                                                           |
| ---------- | ------- | -------------------------------------------------------------------------------------------- |
| `ACTIVE`   | 정상 사용자  | 역할 권한 범위 안에서 허용된 API 사용 가능                                                                   |
| `DISABLED` | 비활성 사용자 | access token, refresh token, dashboard session이 형식상 유효하더라도 API 처리나 대시보드 접근을 허용하지 않고 `403` 반환 |

사용자 삭제는 hard delete로 처리하지 않고, MVP에서는 사용자 상태를 `DISABLED`로 바꾸는 방식으로 처리한다.

### 7.3 확장앱 token auth와 대시보드 session auth 분리

| 구분                      | 확장앱 인증                                                     | 대시보드 인증                                               |
| ----------------------- | ---------------------------------------------------------- | ----------------------------------------------------- |
| 주요 client               | Chrome Extension service worker/options                    | HTML/CSS/TypeScript 기반 multi-page static dashboard    |
| 인증 방식                   | bearer token                                               | ADMIN session cookie                                  |
| 로그인 endpoint            | `POST /auth/login`                                         | `POST /dashboard/session/login`                       |
| 상태 확인                   | `GET /auth/me`                                             | `GET /dashboard/session/me`                           |
| 갱신                      | `POST /auth/refresh`                                       | 12시간 session 만료 시 재로그인                                |
| 로그아웃                    | `POST /auth/logout`                                        | `POST /dashboard/session/logout`                      |
| client 측 credential 저장  | extension storage에 access token, refresh token, 만료 시각 등 저장 | `HttpOnly` session cookie                             |
| 서버 측 refresh/session 저장 | refresh token 원문은 저장하지 않고 hash와 metadata만 PostgreSQL에 저장   | session id 원문은 저장하지 않고 hash와 metadata만 PostgreSQL에 저장 |
| CSRF                    | bearer token API에는 기본 미적용                                  | dashboard 상태 변경 요청에 필수                                |
| 실패 UX                   | options/status UI에서 재로그인                                   | session 만료 시 login page로 이동                           |

대시보드는 bearer token을 `localStorage`에 저장하지 않는다. 대시보드 session id도 `localStorage`에 저장하지 않는다. USER는 대시보드 화면과 대시보드 API에 접근할 수 없다.

## 8. MVP API 경계와 상세 계약

이 단원은 API별 책임 경계와 request/response 계약을 함께 둔다. 이 문서의 API 경계와 request/response 계약을 기준으로 구현한다. `apps/api`의 FastAPI route, Pydantic schema, 생성된 OpenAPI 산출물은 이 문서의 API 계약과 대조해야 하는 구현 결과물이다.

### 8.1 전송 시도 분석 경계

엔드포인트: `POST /prompts/analyze`

`POST /prompts/analyze`는 단일 prompt 문자열만 검사하는 API가 아니라, 사용자의 한 번의 전송 시도(send attempt)를 판단하는 decision endpoint다.

하나의 전송 시도에는 최종 composer text, 허용된 text file 내용, paste가 attachment/file로 변환되기 전에 확장앱이 캡처한 text, attachment metadata, unsupported attachment, 크기 제한을 초과한 입력의 metadata-only 정보가 함께 포함될 수 있다. 서버는 이 입력들을 함께 판단해 전송 시도 전체에 대한 하나의 최종 `action`을 반환한다.

일반 paste는 독립 input으로 보내지 않는다. 붙여넣은 내용이 최종 composer text에 포함되므로, send 시점 composer 전체를 `kind: "text"`, `source: "composer"`로 보낸다. `converted_paste`는 paste된 텍스트가 AI 서비스에 의해 attachment/file처럼 변환되어 composer에 남지 않고, 확장앱이 paste event에서 원문 text를 캡처한 경우에만 사용한다.

구현 일관성을 위해 analyze request의 입력 표현은 `inputs[]` 하나로 통일한다. 단일 composer text, 복합 입력, 파일 text, attachment metadata, unsupported attachment는 모두 같은 `inputs[]` 배열로 표현한다. 서버와 확장앱은 top-level `prompt`, `input`, `file`, `attachments` 같은 별도 병렬 입력 필드를 만들지 않는다.

서버 책임: request schema 검증, bearer token 검증, token에 대응하는 `login_id` 확인, 사용자 `status` 확인, Analyze Input Bundle 정규화, 통합 Filter Rule 실행, risk score 계산, action 결정, 필요한 경우 composer text에 적용할 `masked_prompt` 생성, event metadata 저장, `client_request_id` 기반 중복 요청 처리, 6장의 HTTP 오류 계약에 맞는 오류 응답.

확장앱 책임: DOM 입력 추출, paste event capture, 가능한 경우 file input/drop/paste에서 raw `File` 객체 확보, attachment metadata capture, 크기 제한 preflight, 전송 전 보류, request body 생성, timeout 처리, Allow/Warn/Mask/Block UX, 서버가 준 `masked_prompt` 적용, 허용된 경우에만 보호된 재전송 수행.

확장앱은 제한을 초과한 텍스트나 파일 내용을 analyze request body에 포함하지 않는다. 대신 해당 입력의 `kind`, `source`, `size_bytes`, `content_included: false`, `content_unavailable_reason`, `limit_exceeded` 같은 metadata-only 정보를 포함해 서버가 중앙 정책에 따라 최종 action을 결정하게 한다.

요청 필수값: `inputs[]`, `context.ai_service`, `context.ai_service_domain`, `context.page_url_origin`, `context.extension_version`, `context.browser`, `context.locale`, `filter_config_revision`, `client_request_id`.

`filter_config_revision`은 확장앱이 마지막으로 받은 실행 설정의 revision 값이다. 이벤트 상세 UI에는 표시하지 않는다.

MVP에서는 `client_request_id`를 사용해 동일 전송 시도의 중복 event 생성을 방지한다.

- idempotency 처리는 `(login_id, client_request_id)` 조합을 기준으로 한다.
- 같은 `(login_id, client_request_id)`가 이미 처리된 경우 가능한 한 기존 event/idempotency metadata를 재사용한다.
- 같은 `client_request_id`에 서로 다른 요청 내용이 들어오는 충돌 감지는 MVP 필수 범위에 포함하지 않는다.

`inputs[]`는 한 번의 전송 시도에 포함된 입력 조각들의 배열이다. 각 item은 최소한 `input_id`, `kind`, `source`, `size_bytes`, `content_included`를 가진다.

- `input_id`: 요청 안에서 입력 조각을 식별하기 위한 client-generated id다.
- `kind`: 입력 데이터의 형태다. 예: `text`, `attachment_metadata`, `unsupported_attachment`.
- `source`: 입력이 어디서 왔는지 나타낸다. 예: `composer`, `converted_paste`, `file`, `attachment_chip`.
- `content_included`: 확장앱이 실제 내용을 analyze request에 포함했는지 여부다.
- `content_scanned`: 서버가 실제로 내용을 분석했는지 여부다. request 필드가 아니라 response 또는 event metadata에 기록한다.

| kind                     | source                                | 내용                                                                         | 요청에서의 처리                                                             |
| ------------------------ | ------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `text`                   | `composer`                            | send 시점 composer에 들어 있는 최종 텍스트. typed text와 일반 paste가 여기에 포함된다.            | 제한 안이면 `content_included: true`                                      |
| `text`                   | `converted_paste`                     | paste event에서 확장앱이 캡처했지만, AI 서비스가 attachment/file로 변환해 composer에 남지 않은 텍스트 | 제한 안이면 `content_included: true`                                      |
| `text`                   | `file`                                | 확장앱이 raw `File` 객체를 확보했고, MVP에서 허용된 작은 텍스트 계열 파일                           | 제한 안이면 `content_included: true`                                      |
| `text`                   | `composer`, `converted_paste`, `file` | 크기 제한을 초과해 전체 내용을 분석 요청에 포함할 수 없는 텍스트 입력                                   | `content_included: false`, `content_unavailable_reason: "oversized"` |
| `attachment_metadata`    | `attachment_chip`                     | 파일/이미지/서비스 attachment chip metadata                                        | `content_included: false`                                            |
| `unsupported_attachment` | `attachment_chip`                     | metadata 부족, raw File 접근 불가, 또는 MVP 미지원 첨부                                 | `content_included: false`                                            |

요청 예시:

```json
{
  "client_request_id": "req_123",
  "filter_config_revision": "cfg_2026_05_31_001",
  "context": {
    "ai_service": "chatgpt",
    "ai_service_domain": "chatgpt.com",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "extension-build-version",
    "browser": "chrome",
    "locale": "ko-KR"
  },
  "inputs": [
    {
      "input_id": "in_1",
      "kind": "text",
      "source": "composer",
      "content": "이 파일 요약해줘",
      "size_bytes": 24,
      "content_included": true
    },
    {
      "input_id": "in_2",
      "kind": "text",
      "source": "file",
      "content": "파일에서 읽은 텍스트 내용...",
      "size_bytes": 50000,
      "content_included": true
    },
    {
      "input_id": "in_3",
      "kind": "attachment_metadata",
      "source": "attachment_chip",
      "metadata": {
        "extension": "png",
        "mime": "image/png",
        "size_bytes": 300000,
        "attachment_kind": "image",
        "attachment_index": 0
      },
      "size_bytes": 300000,
      "content_included": false
    },
    {
      "input_id": "in_4",
      "kind": "text",
      "source": "converted_paste",
      "size_bytes": 2500000,
      "content_included": false,
      "content_unavailable_reason": "oversized",
      "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES"
    }
  ]
}
```

크기 제한 이름은 byte 기준으로 둔다.

기본값:

- `MAX_COMPOSER_TEXT_BYTES=262144`
- `MAX_CONVERTED_PASTE_TEXT_BYTES=1048576`
- `MAX_FILE_TEXT_SCAN_BYTES=1048576`
- `MAX_ANALYZE_REQUEST_BYTES=2097152`

Python/JavaScript string length 기반 값은 요청 처리 한도의 최종 기준으로 쓰지 않는다.

제한 안에 들어오는 text input은 크더라도 전체를 분석 요청에 포함하고 서버에서 스캔한다. 제한을 초과해 내용을 요청에 포함할 수 없는 입력은 `content_included: false`로 표시하고, 내용 없이 metadata-only로 서버에 보낸다.

서버는 `content_included: false` 입력을 content unavailable 입력으로 본다. 이런 입력이 포함된 전송 시도는 silent allow로 처리하지 않는다. 기본 action은 `Block`으로 두며, 정책에서 허용하는 경우에만 사용자가 이해할 수 있는 `Warn`과 사용자 확인 요구로 낮출 수 있다.

서버는 `MAX_ANALYZE_REQUEST_BYTES`를 request parsing 전에 적용해야 한다. 확장앱의 client-side 제한만으로 request 크기 제한을 보장하지 않는다.

요청 금지값: 전체 page URL path/query, 원본 파일명, ID 필드 안의 비밀값.

응답 필수값: `event_id`, `request_id`, `risk_score`, `risk_level`, `action`, `user_message`, `allow_original_send`, `requires_user_confirmation`, `detections[]`, `input_results[]`, `content_unavailable_inputs[]`, 필요한 경우 `business_context_matches[]`, machine client용 `filter_config_revision`, `Mask`일 때만 `masked_prompt`.

서버는 여러 입력과 여러 탐지 결과를 종합해 전송 시도 전체에 대한 최종 `action`을 하나만 반환한다. 프론트엔드는 top-level `action`, `allow_original_send`, `requires_user_confirmation`, `masked_prompt`만 전송 제어에 사용한다. `detections[]`, `input_results[]`, `content_unavailable_inputs[]`는 사용자가 결과를 이해하도록 표시하는 근거 metadata이며 action을 다시 계산하는 입력이 아니다.

최종 action 우선순위는 `Block > Mask > Warn > Allow`로 둔다.

- `Block`: 전송을 차단한다. `allow_original_send`는 `false`다.
- `Mask`: composer text를 `masked_prompt`로 교체한다. 원본 전송은 허용하지 않으므로 `allow_original_send`는 `false`다.
- `Warn`: 사용자에게 경고 또는 confirmation UI를 보여준 뒤 전송을 허용할 수 있다. `requires_user_confirmation`이 `true`일 수 있다.
- `Allow`: 별도 개입 없이 원래 전송을 허용한다.

`Mask`와 `Warn`이 동시에 필요한 경우 서버는 `action: "Mask"`와 `requires_user_confirmation: true`를 함께 반환한다. 프론트엔드는 composer text를 `masked_prompt`로 교체한 뒤 warning/confirmation UI를 표시하고, 사용자가 확인한 경우에만 마스킹된 텍스트를 전송한다.

`Block`이 필요한 입력이 하나라도 있으면 서버는 최종 `action: "Block"`을 반환한다. 이 경우 프론트엔드는 다른 `Mask` 또는 `Warn` 후보가 있어도 전송하지 않는다.

`detections[]`의 각 항목은 원문 탐지값을 포함하지 않고, 어느 입력에서 탐지됐는지 알 수 있도록 `input_id`, `input_index`, `kind`, `source`, `rule_id`, `detector_id`, `severity`, `action`, `placeholder`, `match_count`, `reason_code`를 포함한다.

`input_results[]`는 요청의 `inputs[]`와 같은 순서로 반환한다. 각 항목은 `input_id`, `input_index`, `kind`, `source`, `content_included`, `content_scanned`, `decision_basis`, 필요한 경우 `content_unavailable_reason`, `limit_exceeded`를 포함한다.

`content_unavailable_inputs[]`는 서버가 실제 내용을 검사하지 못하고 metadata-only로 판단한 입력만 별도로 요약한다. 없으면 빈 배열을 반환한다. 각 항목은 `input_id`, `input_index`, `kind`, `source`, `reason`, `limit_exceeded`를 포함한다.

응답 예시:

```json
{
  "event_id": "evt_123",
  "request_id": "req_123",
  "risk_score": 0.92,
  "risk_level": "high",
  "action": "Block",
  "user_message": "첨부 또는 입력 중 확인할 수 없는 항목이 있어 전송을 차단했습니다.",
  "allow_original_send": false,
  "requires_user_confirmation": false,
  "filter_config_revision": "cfg_2026_05_31_001",
  "detections": [
    {
      "input_id": "in_2",
      "input_index": 1,
      "kind": "text",
      "source": "file",
      "rule_id": "rule_secret",
      "detector_id": "private_key",
      "severity": "high",
      "action": "Block",
      "placeholder": "[SECRET]",
      "match_count": 1,
      "reason_code": "SECRET_PATTERN"
    }
  ],
  "input_results": [
    {
      "input_id": "in_1",
      "input_index": 0,
      "kind": "text",
      "source": "composer",
      "content_included": true,
      "content_scanned": true,
      "decision_basis": "no_detection"
    },
    {
      "input_id": "in_2",
      "input_index": 1,
      "kind": "text",
      "source": "file",
      "content_included": true,
      "content_scanned": true,
      "decision_basis": "detection"
    },
    {
      "input_id": "in_3",
      "input_index": 2,
      "kind": "attachment_metadata",
      "source": "attachment_chip",
      "content_included": false,
      "content_scanned": false,
      "decision_basis": "metadata_only"
    },
    {
      "input_id": "in_4",
      "input_index": 3,
      "kind": "text",
      "source": "converted_paste",
      "content_included": false,
      "content_scanned": false,
      "decision_basis": "content_unavailable",
      "content_unavailable_reason": "oversized",
      "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES"
    }
  ],
  "content_unavailable_inputs": [
    {
      "input_id": "in_4",
      "input_index": 3,
      "kind": "text",
      "source": "converted_paste",
      "reason": "oversized",
      "limit_exceeded": "MAX_ANALYZE_REQUEST_BYTES"
    }
  ]
}
```

응답은 metadata와 필요한 action 결과만 반환한다. 입력 본문, 파일 내용, 탐지값 원문, 원본 파일명, 내부 stack trace, 임의 exception text, 저장되지 않은 전체 `masked_prompt`는 반환하지 않는다.

`masked_prompt`는 MVP에서 composer text에만 적용한다. file text 또는 attachment metadata에서 탐지된 위험은 자동으로 파일 내용을 수정하지 않고, 정책에 따라 `Block` 또는 `Warn`으로 처리한다.

### 8.2 파일/첨부 입력 경계

파일 내용, 파일 metadata, 이미지/서비스 attachment chip 정보는 모두 `POST /prompts/analyze`의 `inputs[]` item으로 표현한다.

MVP에서 파일 내용 스캔은 확장앱이 raw `File` 객체를 확보할 수 있고, 파일이 허용된 작은 텍스트 계열이며, 크기 제한 안에 있을 때만 적용한다. 이 경우 확장앱은 `inputs[]`에서 `kind: "text"`, `source: "file"`, `content_included: true`로 요청에 포함한다. 서버가 해당 내용을 분석한 뒤 response와 event metadata에는 `content_scanned: true`로 기록한다.

확장앱이 raw `File` 객체를 확보하지 못하거나, 이미 서비스 attachment chip으로만 표시되는 경우에는 파일 내용을 읽으려 하지 않는다. 이 경우 가능한 metadata만 `attachment_metadata`로 보내고, metadata도 부족하거나 MVP 미지원이면 `unsupported_attachment`로 보낸다.

PDF, Office, OCR, 압축 해제, malware scanning, binary analysis, ZIP 내부 파일 분석, 이미지 내용 분석, repository deep scan은 MVP 범위에 포함하지 않는다.

파일 내용은 request 처리 중 일시 입력으로만 사용한다.

이미지 paste, 이미지 파일, 서비스 attachment chip은 OCR, pixel inspection, base64 payload scan을 하지 않는다. 가능한 경우 `attachment_metadata`로 표현하고, metadata가 부족하거나 미지원이면 `unsupported_attachment`로 표현한다.

`attachment_metadata`에는 extension, MIME, size, count, attachment kind, attachment index 같은 metadata-only 정보를 담는다. 원본 파일명, raw file bytes, base64 payload, OCR text는 `attachment_metadata`에 포함하지 않는다.

서버와 확장앱은 같은 분석 요청 안에서 composer text, converted paste, 파일 text, attachment metadata를 함께 판단한다.

### 8.3 확장앱 설정 경계

엔드포인트: `GET /config/extension`

`GET /config/extension`은 Chrome Extension이 서버 정책, 입력 제한, AI 서비스별 입력 감지 설정을 받아오기 위한 보호 API다. USER와 ADMIN 모두 사용할 수 있지만 public endpoint는 아니다.

반환값은 최소한 다음 항목을 포함한다.

| 필드                       | 의미                                      |
| ------------------------ | --------------------------------------- |
| `filter_config_revision` | 확장앱이 analyze 요청에 함께 보낼 설정 revision 값    |
| `request_timeouts`       | 확장앱 API 요청 timeout 설정                   |
| `ai_service_configs[]`   | AI 서비스별 domain, selector, capability 설정 |
| `input_limits`           | byte 기준 입력 크기 제한                        |
| `attachment_policy`      | 파일/첨부 입력 처리 정책                          |

`filter_config_revision`은 확장앱이 마지막으로 받은 실행 설정의 revision 값이다. 이벤트 상세 UI에는 표시하지 않는다.

`request_timeouts`는 확장앱이 서버 응답을 무한정 기다리지 않도록 API 요청별 timeout을 제공한다.

| 필드                   | 기본값    | 의미                                                                           |
| -------------------- | ------ | ---------------------------------------------------------------------------- |
| `config_request_ms`  | `5000` | 확장앱 설정 요청 timeout. 최초 설정 요청에는 확장앱 내장 기본값을 쓰고, 이후에는 서버 설정 또는 캐시된 설정을 적용한다.    |
| `analyze_request_ms` | `8000` | `/prompts/analyze` 요청 timeout. 이 시간을 넘으면 확장앱은 서버 응답 실패로 보고 timeout UX를 적용한다. |

`input_limits`는 byte 기준 크기 제한을 고정 key-value map으로 표현한다. 서버 내부 환경변수나 설정 이름은 `MAX_COMPOSER_TEXT_BYTES`처럼 대문자 상수명을 쓸 수 있지만, API 응답 JSON은 snake\_case field로 내려준다.

| API 응답 필드                    | 서버 설정 이름                         | 기본값       | 의미                                                                                         |
| ---------------------------- | -------------------------------- | --------- | ------------------------------------------------------------------------------------------ |
| `composer_text_bytes`        | `MAX_COMPOSER_TEXT_BYTES`        | `262144`  | send 시점 composer text 최대 크기                                                                |
| `converted_paste_text_bytes` | `MAX_CONVERTED_PASTE_TEXT_BYTES` | `1048576` | paste가 attachment/file로 변환되어 composer에 남지 않은 경우, 확장앱이 캡처한 text를 analyze 요청에 포함할 수 있는 최대 크기 |
| `file_text_scan_bytes`       | `MAX_FILE_TEXT_SCAN_BYTES`       | `1048576` | 허용된 작은 텍스트 계열 파일을 읽어 analyze 요청에 포함할 수 있는 최대 크기                                            |
| `analyze_request_bytes`      | `MAX_ANALYZE_REQUEST_BYTES`      | `2097152` | `/prompts/analyze` 전체 request body 최대 크기                                                   |

`attachment_policy`는 확장앱이 파일/첨부 입력을 어떻게 표현할지 판단하는 데 필요한 metadata-only 정책을 포함한다.

| 항목                           | 의미                                                                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 허용된 텍스트 파일 MIME/extension 목록 | `source: "file"` text input으로 읽을 수 있는 작은 텍스트 계열 파일 기준                                                                    |
| 파일 text scan 최대 크기           | `input_limits.file_text_scan_bytes`와 일치해야 한다                                                                             |
| attachment metadata 허용 필드    | extension, MIME, size, count, attachment kind, attachment index                                                          |
| unsupported attachment 처리 기준 | metadata 부족, raw File 접근 불가, MVP 미지원 첨부 처리 기준                                                                            |
| MVP 미지원 첨부 처리 기준             | OCR, image content scan, PDF/Office parsing, archive extraction 대상은 `unsupported_attachment` 또는 metadata-only 입력으로 표현한다. |

`ai_service_configs[]`는 AI 서비스별 설정을 포함한다.

| 필드                    | 의미                                                                   |
| --------------------- | -------------------------------------------------------------------- |
| `service_id`          | `chatgpt`, `claude`, `gemini` 같은 내부 서비스 식별자                          |
| `domains[]`           | 해당 AI 서비스로 인식할 origin/domain 목록                                      |
| `enabled`             | 해당 서비스 감지 활성화 여부                                                     |
| `selectors`           | composer, send button, attachment chip 등을 찾기 위한 selector 설정          |
| `capabilities`        | composer text, converted paste, attachment chip, file input 감지 가능 여부 |
| `timeout_override_ms` | 필요한 경우 서비스별 analyze timeout override                                 |

AI 서비스별 selector는 기본값을 확장앱에 내장하되, 서버 설정으로 override할 수 있게 한다. 확장앱은 설정 요청 실패에 대비해 built-in fallback selector를 사용한다.

### 8.4 MVP API 목록과 권한 경계

이 섹션은 MVP에서 사용하는 주요 API endpoint, 인증 방식, 목적을 요약한다. 각 endpoint의 request/response 상세 계약은 해당 하위 섹션을 따른다.

대시보드 API는 login/session 관련 public endpoint를 제외하면 ADMIN 전용이고 metadata만 반환한다. 확장앱 보호 API는 USER와 ADMIN이 사용할 수 있다.

| Endpoint                                   | Auth                 | 목적                                                    |
| ------------------------------------------ | -------------------- | ----------------------------------------------------- |
| `POST /auth/login`                         | public               | 확장앱 bearer token login                                |
| `POST /auth/refresh`                       | refresh token        | 확장앱 access token refresh                              |
| `POST /auth/logout`                        | user token           | 확장앱 token logout                                      |
| `GET /auth/me`                             | user token           | 확장앱 사용자 확인                                            |
| `GET /config/extension`                    | user token           | 확장앱 원격 설정 조회                                          |
| `POST /prompts/analyze`                    | user token           | send attempt 분석과 최종 action 결정                         |
| `GET /dashboard/session/csrf`              | public               | dashboard CSRF token 발급                               |
| `POST /dashboard/session/login`            | public + CSRF        | ADMIN dashboard session login                         |
| `POST /dashboard/session/logout`           | ADMIN session + CSRF | dashboard logout                                      |
| `GET /dashboard/session/me`                | ADMIN session        | 현재 ADMIN session 확인                                   |
| `GET /dashboard/overview`                  | ADMIN session        | Overview 카드와 기본 차트용 metadata aggregate                |
| `GET /dashboard/events`                    | ADMIN session        | 이벤트 목록                                                |
| `GET /dashboard/events/{event_id}`         | ADMIN session        | 이벤트 상세 metadata                                       |
| `GET /dashboard/users`                     | ADMIN session        | 사용자 목록과 사용자별 기본 이벤트 통계                                |
| `POST /dashboard/users`                    | ADMIN session + CSRF | USER 또는 ADMIN 생성                                      |
| `PATCH /dashboard/users/{login_id}/role`   | ADMIN session + CSRF | role 변경                                               |
| `PATCH /dashboard/users/{login_id}/status` | ADMIN session + CSRF | ACTIVE/DISABLED 변경                                    |
| `GET /dashboard/filters`                   | ADMIN session        | 통합 Filter Rule 목록                                     |
| `GET /dashboard/filters/{id}`              | ADMIN session        | Filter Rule 상세                                        |
| `POST /dashboard/filters`                  | ADMIN session + CSRF | custom keyword/regex/context rule 생성                  |
| `PATCH /dashboard/filters/{id}`            | ADMIN session + CSRF | `editable_fields` 허용 필드 수정                            |
| `PATCH /dashboard/filters/{id}/enable`     | ADMIN session + CSRF | rule 활성화                                              |
| `PATCH /dashboard/filters/{id}/disable`    | ADMIN session + CSRF | rule 비활성화                                             |
| `DELETE /dashboard/filters/{id}`           | ADMIN session + CSRF | custom rule만 archive/delete, built-in 삭제 금지           |
| `POST /dashboard/filters/dry-run`          | ADMIN session + CSRF | 저장 없는 필터 미리 실행                                        |
| `GET /dashboard/status`                    | ADMIN session        | API/PostgreSQL/Migration/Filter Rules/Last Checked 상태 |

MVP에서는 여러 종류의 탐지/제약이 동시에 걸린 경우의 고급 정책 조합, 사용자별 conflict resolution, 복합 remediation UX를 구현하지 않는다. 서버는 단순 우선순위 `Block > Mask > Warn > Allow`로 전송 시도 전체의 최종 `action` 하나를 반환하고, 프론트엔드는 그 top-level action만 따른다.

`detections[]`, `input_results[]`, `content_unavailable_inputs[]`는 top-level `action`의 근거 metadata로만 사용한다.

### 8.5 대시보드 이벤트 조회 계약

대시보드 이벤트 조회 API는 ADMIN이 분석 이벤트 목록과 상세를 확인하기 위한 read-only metadata API다. 이벤트는 `POST /prompts/analyze`가 생성한 한 번의 전송 시도(send attempt) 분석 결과를 뜻한다. 이 API는 탐지, 차단, 마스킹을 수행하지 않고, 이미 저장된 event metadata를 조회한다.

`GET /dashboard/events` 목록 필드:

| 필드                           | 의미                           |
| ---------------------------- | ---------------------------- |
| `event_id`                   | 이벤트 식별자                      |
| `created_at`                 | 분석 시각                        |
| `login_id`                   | 사용자 식별자                      |
| `username`                   | 사용자 표시 이름                    |
| `service`                    | AI 서비스 식별자                   |
| `platform`                   | 브라우저/확장앱 platform metadata   |
| `action`                     | 서버가 결정한 최종 action            |
| `risk_score`                 | 최종 위험 점수                     |
| `risk_level`                 | 최종 위험 등급                     |
| `primary_detection_category` | 대표 탐지 category               |
| `primary_detection_type`     | 대표 탐지 type                   |
| `detection_count`            | 탐지 개수                        |
| `input_count`                | 분석 요청에 포함된 입력 item 수         |
| `content_unavailable_count`  | metadata-only로 판단한 입력 item 수 |
| `detail_available`           | 상세 조회 가능 여부                  |

`GET /dashboard/events/{event_id}` 상세 필드:

| 필드                             | 의미                                           |
| ------------------------------ | -------------------------------------------- |
| `event_id`                     | 이벤트 식별자                                      |
| `created_at`                   | 분석 시각                                        |
| `login_id`                     | 사용자 식별자                                      |
| `username`                     | 사용자 표시 이름                                    |
| `service`                      | AI 서비스 식별자                                   |
| `platform`                     | 브라우저/확장앱 platform metadata                   |
| `action`                       | 서버가 결정한 최종 action                            |
| `risk_score`                   | 최종 위험 점수                                     |
| `risk_level`                   | 최종 위험 등급                                     |
| `detection_summary`            | 탐지 요약                                        |
| `detections[]`                 | 원문 탐지값 없는 탐지 metadata                        |
| `input_results[]`              | `inputs[]` item별 처리 결과 요약                    |
| `content_unavailable_inputs[]` | 서버가 실제 내용을 검사하지 못하고 metadata-only로 판단한 입력 요약 |
| `business_context_matches[]`   | 적용되는 경우 Business Context match metadata      |

대시보드 이벤트 상세 화면과 `GET /dashboard/events/{event_id}` 응답은 다음 내부 식별자를 표시하거나 반환하지 않는다.

- `filter_config_revision`
- `filter_rule_version`
- `prompt_hash_prefix`
- `input_bundle_hash_prefix`
- `request_fingerprint`

위 값들은 사용자에게 보여주는 이벤트 설명용 metadata가 아니다.

`detections[]`의 각 항목은 8.1의 응답 계약과 같은 기준을 따른다. 원문 탐지값을 포함하지 않고, 어느 입력에서 탐지됐는지 알 수 있도록 `input_id`, `input_index`, `kind`, `source`, `rule_id`, `detector_id`, `severity`, `action`, `placeholder`, `match_count`, `reason_code`를 포함한다.

`input_results[]`는 요청 당시 `inputs[]`와 같은 순서로 저장된 처리 결과 요약을 반환한다. 각 항목은 `input_id`, `input_index`, `kind`, `source`, `content_included`, `content_scanned`, `decision_basis`, 필요한 경우 `content_unavailable_reason`, `limit_exceeded`를 포함한다.

`content_unavailable_inputs[]`는 서버가 실제 내용을 검사하지 못하고 metadata-only로 판단한 입력만 별도로 요약한다. 없으면 빈 배열을 반환한다.

Business Context match metadata는 `input_id`, `input_index`, `kind`, `source`, `category`, `reason_code`, `match_count`, `matched_keywords`, `evidence_counts`를 포함할 수 있다. `matched_keywords`는 시스템 rule pack 또는 관리자 등록 context rule 키워드에 한정한다. 임의 원문 span, 입력 일부, 주변 문장은 반환하지 않는다.

### 8.6 ADMIN 사용자 관리 API 계약

ADMIN 사용자 관리 API는 대시보드에서 ADMIN이 USER 또는 ADMIN 계정을 생성하고, role/status를 관리하기 위한 API다. 사용자 생성은 ADMIN이 직접 수행하며, 별도 가입, 초대, 사용자 셀프 등록 흐름을 전제로 하지 않는다.

MVP에서는 `login_id`를 로그인 ID이자 사용자 식별자로 사용한다. `login_id` 변경 기능은 제공하지 않는다.

`GET /dashboard/users` 목록 필드:

| 필드              | 의미                                       |
| --------------- | ---------------------------------------- |
| `login_id`      | 로그인에 사용하는 고유 계정 ID. MVP에서는 사용자 식별에도 사용한다 |
| `username`      | 대시보드에 표시하는 사용자 이름. 동명이인이 있을 수 있다         |
| `department`    | 부서 metadata                              |
| `role`          | `USER` 또는 `ADMIN`                        |
| `status`        | `ACTIVE` 또는 `DISABLED`                   |
| `created_at`    | 생성 시각                                    |
| `last_login_at` | 마지막 로그인 시각                               |
| `last_event_at` | 마지막 분석 이벤트 시각                            |
| `event_count`   | 기본 통계 기간 내 이벤트 수                         |
| `blocked_count` | 기본 통계 기간 내 Block 처리 이벤트 수                |
| `masked_count`  | 기본 통계 기간 내 Mask 처리 이벤트 수                 |
| `warned_count`  | 기본 통계 기간 내 Warn 처리 이벤트 수                 |

`POST /dashboard/users` request:

```json
{
  "login_id": "member01",
  "username": "김현성",
  "password": "temporary-password-12+",
  "department": "Security",
  "role": "USER"
}
```

요청 필드 기준:

| 필드           | 필수 | 의미                           |
| ------------ | -- | ---------------------------- |
| `login_id`   | 필수 | 로그인에 사용하는 고유 계정 ID. 중복될 수 없다 |
| `username`   | 필수 | 대시보드 표시 이름. 동명이인이 있을 수 있다    |
| `password`   | 필수 | ADMIN이 설정하는 초기 비밀번호          |
| `role`       | 필수 | `USER` 또는 `ADMIN`            |
| `department` | 선택 | 부서 metadata                  |

`POST /dashboard/users` 응답은 생성된 사용자 metadata를 반환하되, `password`, `password_hash`, token, session 정보는 반환하지 않는다.

`PATCH /dashboard/users/{login_id}/role` request:

```json
{
  "role": "ADMIN"
}
```

`PATCH /dashboard/users/{login_id}/status` request:

```json
{
  "status": "DISABLED"
}
```

권한과 제약:

- USER는 `/dashboard/users` 계열 API에 접근할 수 없다.
- USER가 ADMIN role을 직접 얻는 API는 만들지 않는다.
- ADMIN은 USER 또는 ADMIN을 생성할 수 있다.
- ADMIN은 다른 사용자의 role을 `USER` 또는 `ADMIN`으로 변경할 수 있다.
- ADMIN은 다른 사용자의 status를 `ACTIVE` 또는 `DISABLED`로 변경할 수 있다.
- 현재 로그인한 ADMIN이 자기 자신의 role을 `USER`로 낮추는 요청은 거부한다.
- 현재 로그인한 ADMIN이 자기 자신의 status를 `DISABLED`로 바꾸는 요청은 거부한다.
- 마지막 `ACTIVE` ADMIN을 없애는 role/status 변경은 거부한다.
- MVP에서는 사용자 삭제를 hard delete로 처리하지 않고 `DISABLED` 상태로 비활성화한다.
- hard delete 또는 사용자 데이터 익명화는 운영 retention 정책이 필요해지는 단계에서 별도 기능으로 다룬다.

MVP에서는 사용자 생성, 목록 조회, role 변경, status 변경을 기본 범위로 둔다. 표시정보 수정 전용 API는 MVP 필수 범위에 포함하지 않는다.

### 8.7 Filter Rule 관리 API 계약

Filter Rule 관리는 단일 `Filter Rule` 모델을 사용한다. 기본 탐지 규칙, custom keyword rule, custom regex rule, Business Context rule은 같은 목록, 상세, 생성/수정, 활성화/비활성화, dry-run 흐름을 사용한다.

Filter Rule은 `origin`과 `kind`로 구분한다.

`severity`는 `low`, `medium`, `high`, `critical` 중 하나를 사용한다.

| 필드       | 의미                                                    |
| -------- | ----------------------------------------------------- |
| `origin` | 규칙 출처. `built_in` 또는 `custom`                         |
| `kind`   | 규칙 종류. `detector`, `keyword`, `regex`, `context_rule` |

`source`라는 필드명은 Filter Rule에서는 사용하지 않는다. `source`는 Analyze Input Bundle의 입력 출처(`composer`, `file`, `attachment_chip` 등)에 사용한다.

Filter Rule 공통 필드:

| 필드                | 의미                                             |
| ----------------- | ---------------------------------------------- |
| `id`              | Filter Rule 식별자                                |
| `origin`          | `built_in` 또는 `custom`                         |
| `kind`            | `detector`, `keyword`, `regex`, `context_rule` |
| `category`        | 규칙 category                                    |
| `label`           | 관리자 화면 표시 이름                                   |
| `description`     | 설명                                             |
| `placeholder`     | 마스킹 또는 표시용 placeholder                         |
| `severity`        | 위험도                                            |
| `action`          | 기본 action                                      |
| `enabled`         | 활성화 여부                                         |
| `editable_fields` | 이 규칙에서 수정 가능한 필드 목록                            |
| `config_json`     | kind별 상세 설정                                    |
| `archived_at`     | custom rule archive 시각                         |
| `created_by`      | 생성자                                            |
| `updated_by`      | 마지막 수정자                                        |
| `created_at`      | 생성 시각                                          |
| `updated_at`      | 수정 시각                                          |

Built-in detector rule:

- `origin: "built_in"`, `kind: "detector"`로 표현한다.
- 삭제할 수 없다.
- `enabled`, `severity`, `action`만 수정할 수 있다.
- 내부 parser, checksum, entropy, detector regex, URI/private-key parser, `detector_key`는 수정할 수 없다.

Custom keyword rule:

- `origin: "custom"`, `kind: "keyword"`로 표현한다.
- 추가, 수정, 삭제 또는 archive, 활성화/비활성화가 가능하다.
- keyword 목록, 제외 keyword, `label`, `description`, `placeholder`, `severity`, `action`, `enabled`를 수정할 수 있다.
- keyword 목록과 제외 keyword는 `config_json`에 저장한다.

Custom regex rule:

- `origin: "custom"`, `kind: "regex"`로 표현한다.
- 추가, 수정, 삭제 또는 archive, 활성화/비활성화가 가능하다.
- regex pattern, `label`, `description`, `placeholder`, `severity`, `action`, `enabled`를 수정할 수 있다.
- regex pattern은 저장 전에 syntax와 길이 검증을 통과해야 한다.
- syntax 오류 또는 처리 불가능한 regex는 `422`로 거부한다.

Business Context rule:

- `origin: "custom"` 또는 시스템 기본 context rule의 경우 `origin: "built_in"`으로 표현할 수 있다.
- `kind: "context_rule"`로 표현한다.
- keyword groups, exclusion keywords, window size, min\_condition\_count, sensitivity `low/medium/high`, `severity`, `action`, `enabled`를 수정할 수 있다.
- 점수 민감도는 `sensitivity`로 조정한다.

API 목록:

| Endpoint                                | Auth                 | 목적                                                  |
| --------------------------------------- | -------------------- | --------------------------------------------------- |
| `GET /dashboard/filters`                | ADMIN session        | 통합 Filter Rule 목록                                   |
| `GET /dashboard/filters/{id}`           | ADMIN session        | Filter Rule 상세                                      |
| `POST /dashboard/filters`               | ADMIN session + CSRF | custom keyword/regex/context rule 생성                |
| `PATCH /dashboard/filters/{id}`         | ADMIN session + CSRF | `editable_fields`에 허용된 필드 수정                        |
| `PATCH /dashboard/filters/{id}/enable`  | ADMIN session + CSRF | rule 활성화                                            |
| `PATCH /dashboard/filters/{id}/disable` | ADMIN session + CSRF | rule 비활성화                                           |
| `DELETE /dashboard/filters/{id}`        | ADMIN session + CSRF | custom rule만 archive 또는 delete. built-in rule 삭제 금지 |
| `POST /dashboard/filters/dry-run`       | ADMIN session + CSRF | 저장 없는 필터 미리 실행                                      |

`POST /dashboard/filters/dry-run`:

- `sample_text`를 request-only로 사용한다.
- dry-run은 event를 만들지 않는다.
- dry-run은 sample text를 저장하지 않는다.
- dry-run은 rule 저장 없이 현재 입력한 설정이 어떻게 동작할지 확인하기 위한 기능이다.

dry-run 응답에는 다음 필드를 반환할 수 있다.

| 필드                  | 의미                          |
| ------------------- | --------------------------- |
| `matched`           | sample에 rule이 매칭됐는지         |
| `expected_action`   | 예상 action                   |
| `expected_severity` | 예상 severity                 |
| `match_count`       | 매칭 개수                       |
| `reason_code`       | 매칭 이유 코드                    |
| `matched_keywords`  | 설정된 keyword 기준 매칭 요약        |
| `evidence_counts`   | context rule evidence count |
| `sample_persisted`  | 항상 `false`                  |

Filter Rule API 오류:

| 상황                         | 상태    |
| -------------------------- | ----- |
| USER 접근                    | `403` |
| 없는 filter                  | `404` |
| built-in 내부 로직 수정 시도       | `422` |
| syntax 오류 또는 처리 불가능한 regex | `422` |
| dry-run sample 크기 초과       | `413` |
| 중복 label 충돌                | `409` |

MVP에서는 여러 rule이 동시에 복잡하게 충돌하는 고급 conflict resolution을 구현하지 않는다. Filter Rule 실행 결과는 8.1의 단순 action 우선순위 `Block > Mask > Warn > Allow`에 따라 서버 orchestrator가 최종 action 하나로 합친다.

### 8.8 대시보드 서버 상태 조회 계약

`GET /dashboard/status`는 대시보드 상태 화면이 필요한 서버 상태 metadata를 반환하는 ADMIN 전용 read-only API다.

필수 반환값:

| 필드                    | 의미                      |
| --------------------- | ----------------------- |
| `api_status`          | API 서버 상태               |
| `postgres_status`     | PostgreSQL 연결 상태        |
| `migration_status`    | DB migration 상태         |
| `filter_rules_status` | 기본 Filter Rule 로드 가능 여부 |
| `last_checked`        | 상태 확인 시각                |

선택 반환값:

| 필드                 | 의미                                  |
| ------------------ | ----------------------------------- |
| `app_version`      | 앱 버전                                |
| `build_sha`        | build 식별자                           |
| `python_version`   | Python runtime version              |
| `postgres_version` | PostgreSQL version 또는 major version |

`GET /dashboard/status`는 `/healthz`와 같은 상태 정보를 대시보드 표시용으로 정리해 반환한다. 단, DB 연결 문자열, secret, token, 상세 env 값, stack trace, 내부 exception text는 반환하지 않는다.

대시보드 status UI는 필수 반환값을 기본 표시한다. 선택 반환값이 있으면 별도 runtime metadata 영역에 표시할 수 있다. Filter Rule 상세 설정이나 환경변수 상세값은 표시하지 않는다.

`/readyz` 내부 readiness 조건에는 DB 연결, migration 상태, 기본 Filter Rule 로드 가능 여부를 포함한다.

## 9. MVP PostgreSQL 데이터 모델 계약

이 단원은 PromptGuard API 서버가 PostgreSQL에 둘 주요 테이블과 컬럼을 정의한다. 데이터 모델은 계정, 인증, Filter Rule, 분석 이벤트, 대시보드 조회 metadata를 기준으로 한다.

각 테이블은 구현상 내부 primary key를 둘 수 있다. 사용자 계정은 MVP에서 `login_id`를 기준으로 참조한다.

### 9.1 주요 테이블

계정/인증:

- `users`: 로그인 계정, 표시 이름, 부서, role, status, password hash metadata를 저장한다.
- `refresh_tokens`: 확장앱 bearer token 흐름의 refresh token hash와 만료/폐기 metadata를 저장한다.
- `dashboard_sessions`: 대시보드 ADMIN session hash와 만료 metadata를 저장한다.

Filter Rule:

- `filter_rules`: built-in detector, custom keyword rule, custom regex rule, Business Context rule을 모두 관리하는 통합 Filter Rule 테이블이다.

분석 이벤트:

- `idempotency_keys`: `client_request_id` 기반 중복 event 방지 metadata를 저장한다.
- `analysis_events`: 한 번의 전송 시도(send attempt)에 대한 최종 action, risk score, risk level, service metadata, created\_at을 저장한다.
- `event_inputs`: 분석 요청의 `inputs[]` item별 metadata와 처리 결과 요약을 저장한다.
- `event_detections`: 탐지 category/type, input 참조, filter\_rule\_id, reason\_code, match\_count, severity, action, evidence metadata를 저장한다.
- `audit_logs`: auth, admin, filter, user 관리 action metadata를 저장한다.

### 9.2 테이블별 핵심 컬럼

| Table                | 핵심 컬럼                                                                                                                                                                                                                         | 제약                                                  |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `users`              | `login_id`, `username`, `department`, `role`, `status`, `password_hash`, `created_at`, `updated_at`, `last_login_at`, `last_event_at`                                                                                         | `login_id` unique, 사용자 hard delete 없음               |
| `refresh_tokens`     | `login_id`, `token_hash`, `expires_at`, `idle_expires_at`, `revoked_at`, `created_at`                                                                                                                                         | raw token 저장 금지                                     |
| `dashboard_sessions` | `login_id`, `session_hash`, `expires_at`, `revoked_at`, `created_at`, `last_seen_at`                                                                                                                                          | raw session id 저장 금지                                |
| `filter_rules`       | `origin`, `kind`, `category`, `label`, `description`, `detector_key`, `placeholder`, `severity`, `action`, `enabled`, `editable_fields`, `config_json`, `archived_at`, `created_by`, `updated_by`, `created_at`, `updated_at` | 통합 Filter Rule 모델. `origin`은 `built_in` 또는 `custom` |
| `idempotency_keys`   | `login_id`, `client_request_id`, `event_id`, `created_at`, `expires_at`                                                                                                                                                       | 중복 event 방지                                         |
| `analysis_events`    | `login_id`, `client_request_id`, `action`, `risk_score`, `risk_level`, `filter_config_revision`, `service`, `service_domain`, `platform`, `created_at`                                                                        | send attempt 단위 event metadata                      |
| `event_inputs`       | `event_id`, `input_id`, `input_index`, `kind`, `source`, `size_bytes`, `content_included`, `content_scanned`, `decision_basis`, `content_unavailable_reason`, `limit_exceeded`                                                | `inputs[]` item별 처리 결과 metadata                     |
| `event_detections`   | `event_id`, `input_id`, `input_index`, `kind`, `input_source`, `category`, `type`, `filter_rule_id`, `severity`, `confidence`, `action`, `reason_code`, `match_count`, `matched_keywords`, `evidence_counts`                  | 탐지값 원문 저장 금지                                        |
| `audit_logs`         | `actor_login_id`, `action`, `target_type`, `target_id`, `safe_metadata`, `created_at`                                                                                                                                         | request body 원문 저장 금지                               |

기본 ADMIN 계정:

- DB migration/초기 데이터 생성 단계가 완료되면 기본 ADMIN 계정 `admin / 1234`가 존재해야 한다.
- 기본 ADMIN의 `login_id`는 `admin`, role은 `ADMIN`, status는 `ACTIVE`다.
- 비밀번호는 일반 사용자와 동일한 password hashing 함수로 해시한다.

### 9.3 인덱스와 삭제 규칙

각 테이블은 구현상 내부 primary key를 둘 수 있다. API 계약과 대시보드 표시에서는 사용자를 `login_id`로 식별한다. DB 내부 primary key, foreign key 컬럼 이름, 실제 join 방식은 구현 세부로 둔다.

이벤트 상세 조회를 위해 `analysis_events`, `event_inputs`, `event_detections`는 같은 이벤트를 기준으로 함께 조회할 수 있어야 한다. `event_inputs`와 `event_detections`는 `input_id` 또는 `input_index`로 어느 입력에서 탐지 결과가 나왔는지 연결할 수 있어야 한다.

필수 인덱스:

| Table                | 제약/인덱스                                                                 | 이유                         |
| -------------------- | ---------------------------------------------------------------------- | -------------------------- |
| `users`              | unique `lower(login_id)`                                               | 중복 계정 방지                   |
| `refresh_tokens`     | unique `token_hash`, index `(login_id, expires_at)`                    | token refresh 조회와 만료 처리    |
| `dashboard_sessions` | unique `session_hash`, index `(login_id, expires_at)`                  | dashboard session 조회/만료 처리 |
| `filter_rules`       | index `(enabled)`, `(origin, kind)`                                    | filter 목록과 pipeline load   |
| `idempotency_keys`   | unique `(login_id, client_request_id)`                                 | 중복 event 방지                |
| `analysis_events`    | index `(created_at)`, `(login_id, created_at)`, `(action, created_at)` | dashboard list/stat query  |
| `event_inputs`       | index `(event_id)`, `(event_id, input_index)`                          | event 상세 조회                |
| `event_detections`   | index `(event_id)`, `(category)`, `(type)`, `(filter_rule_id)`         | 상세/통계 aggregate            |
| `audit_logs`         | index `(created_at)`, `(actor_login_id, created_at)`                   | admin audit                |

삭제/비활성 규칙:

- 사용자는 `DISABLED` 상태로 처리한다. hard delete 또는 사용자 데이터 익명화는 운영 retention 정책이 필요해지는 단계에서 별도 기능으로 다룬다.
- built-in Filter Rule은 삭제할 수 없다.
- custom Filter Rule과 context rule은 disabled 또는 archived 처리한다.
- event row는 metadata만 저장하므로 retention rule로 삭제할 수 있다.
- audit log는 action, target, safe\_metadata만 저장한다.

데이터 저장 기준:

- `event_inputs`는 입력별 metadata와 처리 결과를 저장하되, `content` 본문은 저장하지 않는다.
- `event_detections`는 탐지값 원문이 아니라 rule name, configured keyword count, evidence count 같은 안전한 요약 metadata만 담는다.
- 입력 본문, 파일 내용, full `masked_prompt`, 탐지값 원문, 원본 파일명, 입력 일부, 주변 문맥, stack trace는 저장하거나 대시보드 API로 반환하지 않는다.

## 10. MVP 탐지·마스킹·점수·Filter Rule 실행 계약

탐지, 점수 계산, 최종 action 결정, 마스킹 생성은 서버 책임이다. 확장앱은 전송을 보류하고, 서버가 반환한 top-level `action`과 필요한 경우 `masked_prompt`를 적용한다.

`POST /prompts/analyze`는 단일 prompt 문자열이 아니라 한 번의 전송 시도(send attempt)를 분석한다. 서버는 `inputs[]`에 포함된 composer text, converted paste, file text, attachment metadata, content unavailable 입력을 함께 판단해 전송 시도 전체의 최종 `action` 하나를 반환한다.

### 10.1 분석 파이프라인 순서

1. request schema validation
2. bearer token 검증
3. token에 대응하는 `login_id` 확인
4. 사용자 `status`가 `ACTIVE`인지 확인
5. 확장앱이 보낸 `filter_config_revision` 확인
6. `inputs[]` 정규화
7. `content_included: true`인 text 입력의 transient text normalization
8. `origin: "built_in"`, `kind: "detector"` Filter Rule을 통한 built-in detector 실행
9. custom keyword rule 실행
10. custom regex rule 실행
11. Business Context `context_rule` 실행
12. 입력별 detection overlap merge
13. send attempt 전체 risk scoring
14. send attempt 전체 final action decision
15. 필요한 경우 composer text용 `masked_prompt` 생성
16. metadata-only event logging
17. safe response 생성

`content_included: false`인 입력은 내용 기반 detector를 실행하지 않는다. 서버는 해당 입력을 content unavailable 입력으로 보고, metadata-only 정책에 따라 최종 action 결정에 반영한다.

### 10.2 Detector 및 Filter Rule 종류

Built-in detector rule:

- `origin: "built_in"`, `kind: "detector"`로 표현한다.
- Secret:
  - API Key
  - GitHub Token
  - AWS Key
  - JWT
  - DB Connection String
  - `.env` Secret
  - Private Key
  - High Entropy Token
- PII:
  - Phone Number
  - Email
  - 주민등록번호
  - Card Number
  - Business Registration Number
- 내부 parser, checksum, entropy, detector regex, URI/private-key parser, `detector_key`는 code-backed이며 관리자 수정 대상이 아니다.
- 관리자는 built-in detector rule의 `enabled`, `severity`, `action`만 수정할 수 있다.

Custom keyword rule:

- `origin: "custom"`, `kind: "keyword"`로 표현한다.
- 관리자가 정의하는 exact/contains/case-insensitive keyword matching을 수행한다.
- keyword 목록과 제외 keyword는 `config_json`에 저장한다.
- keyword rule은 추가, 수정, 삭제 또는 archive, 활성화/비활성화가 가능하다.

Custom regex rule:

- `origin: "custom"`, `kind: "regex"`로 표현한다.
- 관리자가 정의하는 regex pattern filter다.
- 저장 전 syntax와 길이 검증을 수행한다.
- syntax 오류 또는 처리 불가능한 regex는 `422`로 거부한다.

Business Context rule:

- `kind: "context_rule"`로 표현한다.
- Contract, Penalty, NDA, Customer Info, Trade Secret, Internal Strategy, Launch Plan, Pricing Policy 같은 업무 문맥 탐지에 사용한다.
- rule-based evidence scoring만 사용한다.
- Business Context rule은 keyword/evidence 기반 규칙으로 처리한다.

### 10.3 Context Rule 점수화

Context Rule은 text 입력을 문장, 문단, window 단위로 나누고 각 window에서 evidence를 계산한다.

Context Rule 제어 항목:

- `label`
- `keyword_groups`
- `exclusion_keywords`
- `window_size`
- `min_condition_count`
- `sensitivity`: `low`, `medium`, `high`
- `severity`
- `action`
- `enabled`

Context Rule의 점수 민감도는 `sensitivity`로 조정한다.

Context detection output은 다음 metadata를 포함한다.

- `input_id`
- `input_index`
- `kind`
- `source`
- `category`
- `reason_code`
- `evidence_counts`
- `matched_keywords`
- `match_count`
- `severity`
- `action`

Context detection output은 입력 본문 span, 주변 문장, 입력 일부를 포함하지 않는다.

### 10.4 Overlap 및 우선순위

Overlap merge는 같은 입력 안의 detection을 기준으로 수행한다.

- Secret detection은 일반 PII나 Business Context보다 우선한다.
- 같은 우선순위에서는 긴 span을 우선한다.
- 겹치는 detection은 response와 통계에서 이중 계산하지 않는다.
- Context Rule evidence는 입력 본문 span을 저장하지 않고 evidence count와 configured keyword count만 저장한다.
- Detection 결과는 `input_id`, `input_index`, `kind`, `source`와 함께 반환해 어느 입력에서 발생했는지 알 수 있게 한다.

MVP에서는 여러 rule이 동시에 복잡하게 충돌하는 고급 conflict resolution을 구현하지 않는다. 서버 orchestrator는 단순 우선순위 `Block > Mask > Warn > Allow`에 따라 send attempt 전체의 최종 `action` 하나를 결정한다.

### 10.5 위험도와 Action 결정

최종 action은 개별 detector가 아니라 서버 orchestrator가 결정한다.

같은 `inputs[]`, 같은 active Filter Rule set, 같은 scoring config, 같은 content availability 상태라면 같은 결과를 내야 한다.

Severity 값:

| severity   | 기본 의미                                                  | 기본 action 경향  |
| ---------- | ------------------------------------------------------ | ------------- |
| `critical` | confirmed secret, private key, DB URI, JWT, API key 계열 | Block         |
| `high`     | 강한 PII, `.env` secret, high entropy token              | Mask 또는 Block |
| `medium`   | email/phone 단독, 계약/NDA/고객정보/내부전략 문맥                    | Warn 또는 Mask  |
| `low`      | 낮은 신뢰도 또는 모호한 후보                                       | Allow 또는 Warn |

| Detection                                           | 기본 점수 | 기본 action               |
| --------------------------------------------------- | ----- | ----------------------- |
| confirmed secret: API key, private key, DB URI, JWT | 90    | Block 우선                |
| confirmed credential-like `.env` secret             | 85    | Mask 또는 Block           |
| 주민등록번호, card, business id 같은 강한 PII                 | 80    | Mask                    |
| email/phone 단독                                      | 45    | Warn                    |
| 계약금액/위약금/NDA 문맥                                     | 65    | Warn 또는 Mask            |
| 고객정보/영업기밀/내부전략 문맥                                   | 65    | Warn 또는 Mask            |
| ambiguous low confidence                            | 30    | Allow 또는 Warn           |
| custom Filter Rule with `severity: "critical"`      | 90    | rule action 우선          |
| custom Filter Rule with `severity: "high"`          | 70    | rule action 우선          |
| content unavailable input                           | 정책값   | 기본 Block, 정책상 허용 시 Warn |

최종 action 우선순위:

1. `Block`
2. `Mask`
3. `Warn`
4. `Allow`

`Block`이 필요한 입력이 하나라도 있으면 최종 action은 `Block`이다. 이 경우 프론트엔드는 다른 `Mask` 또는 `Warn` 후보가 있어도 전송하지 않는다.

`Mask`와 `Warn`이 동시에 필요한 경우 서버는 `action: "Mask"`와 `requires_user_confirmation: true`를 함께 반환할 수 있다. 프론트엔드는 composer text를 `masked_prompt`로 교체한 뒤 warning/confirmation UI를 표시하고, 사용자가 확인한 경우에만 마스킹된 텍스트를 전송한다.

MVP에서는 Warn 사유 입력 또는 justification 저장 기능을 제공하지 않는다.

### 10.6 마스킹

마스킹은 서버가 생성한 `masked_prompt`를 기준으로 한다.

- `Mask` action에서만 `masked_prompt`를 응답에 포함한다.
- `masked_prompt`는 MVP에서 composer text에만 적용한다.
- `masked_prompt`는 event row나 dashboard API에 저장하지 않는다.
- 같은 민감값 반복은 같은 placeholder로 치환한다.
- placeholder 예:
  - `[SECRET_1]`
  - `[EMAIL_1]`
  - `[PHONE_1]`
  - `[CARD_1]`
  - `[CONTRACT_AMOUNT_1]`
  - `[INTERNAL_PROJECT_1]`

file text, attachment metadata, unsupported attachment, content unavailable 입력에서 탐지된 위험은 자동으로 파일 내용이나 attachment를 수정하지 않는다. 이 경우 서버는 정책에 따라 `Block` 또는 `Warn`을 반환한다.

composer text와 다른 입력에서 동시에 위험이 발견된 경우에도 프론트엔드는 top-level `action`만 따른다. 예를 들어 composer text는 Mask 가능하지만 file text에서 Block 위험이 발견되면 최종 action은 `Block`이다.

### 10.7 실행 설정과 Dry-run

`filter_config_revision`은 확장앱이 받은 실행 설정의 revision 값이며, analyze request에 함께 보낼 수 있다. MVP에서는 이 값을 복잡한 Filter Rule 변경 이력으로 관리하지 않고, 확장앱 설정 동기화와 디버깅을 위한 단순 revision metadata로 사용한다.

대시보드 이벤트 상세 UI에는 `filter_config_revision`, 내부 rule version, hash/fingerprint 식별자를 표시하지 않는다.

`POST /dashboard/filters/dry-run`은 sample text를 request-only로 사용한다.

- dry-run은 event를 만들지 않는다.
- dry-run sample text는 저장하지 않는다.
- dry-run 결과에는 safe match count, reason code, expected action, expected severity, configured matched keywords를 표시할 수 있다.
- match 원문, 입력 일부, 주변 문맥, 파일 내용, 원본 파일명은 저장하거나 표시하지 않는다.

## 11. MVP 확장앱 계약

확장앱은 지원 대상 AI 서비스 화면에서 사용자의 전송 시도(send attempt)를 감지하고, 실제 전송 전에 서버의 `POST /prompts/analyze` 판정을 받아 Allow/Warn/Mask/Block UX를 적용한다.

확장앱은 최종 정책 판단을 직접 계산하지 않는다. 확장앱은 입력 수집, 전송 보류, analyze request 생성, 서버 응답 적용, 재전송 제어를 담당한다. 최종 `action`은 서버가 결정한다.

### 11.1 확장앱 하위 범위

content script:

- 지원 대상 domain에서만 동작한다.
- 현재 AI 서비스 화면의 composer, send button, attachment chip 후보를 찾는다.
- textarea와 contenteditable 후보를 찾고, visible/focus 기준으로 현재 composer를 고른다.
- send button click과 Enter 전송을 분석 완료 전 보류한다.
- `@` mention, IME composition, Shift+Enter 줄바꿈, GPT picker 같은 작성 보조 동작은 전송으로 오판하지 않는다.
- send 시점 composer에 들어 있는 최종 텍스트를 `kind: "text"`, `source: "composer"` 입력으로 만든다.
- 일반 paste는 독립 input으로 보내지 않는다. 일반 paste는 최종 composer text에 포함된 것으로 본다.
- paste된 텍스트가 AI 서비스에 의해 attachment/file처럼 변환되어 composer에 남지 않고, 확장앱이 paste event에서 원문 text를 캡처한 경우에만 `source: "converted_paste"` 입력으로 만들 수 있다.
- file input, drag-and-drop, paste event 등에서 raw `File` 객체를 확보할 수 있고, 허용된 작은 텍스트 계열 파일이며 크기 제한 안에 있으면 `kind: "text"`, `source: "file"`, `content_included: true`로 요청에 포함한다.
- raw `File` 객체를 확보하지 못하거나, 이미 서비스 attachment chip으로만 표시되는 경우에는 파일 내용을 읽으려 하지 않는다.
- attachment chip은 가능한 metadata만 `attachment_metadata`로 표현하고, metadata가 부족하거나 MVP 미지원이면 `unsupported_attachment`로 표현한다.
- 이미지 paste, 이미지 파일, 서비스 attachment chip에 대해 OCR, pixel inspection, base64 payload scan을 하지 않는다.

service worker:

- PromptGuard API URL, bearer token, extension config cache, selector override, input limit, timeout, auth error 처리를 맡는다.
- `GET /config/extension`으로 `request_timeouts`, `input_limits`, `attachment_policy`, `ai_service_configs[]`를 받아 캐시한다.
- 설정 요청 실패 시 built-in fallback selector와 마지막으로 캐시한 안전 설정을 사용할 수 있다.
- request body는 8.1의 Analyze Input Bundle 계약에 맞춰 `inputs[]` 하나로 만든다.
- request body에 `login_id`를 임의로 넣지 않는다. 사용자 식별은 bearer token을 통해 서버가 판단한다.
- 제한을 초과한 텍스트나 파일 내용은 request body에 포함하지 않는다. 대신 `content_included: false`, `size_bytes`, `content_unavailable_reason`, `limit_exceeded` 같은 metadata-only 정보를 포함한다.
- MV3 service worker inactive 상태는 정상 lifecycle이며 로그인 만료로 취급하지 않는다.
- worker wake-up 후 저장된 auth metadata를 읽고, access token이 만료됐으면 먼저 `POST /auth/refresh`를 시도한다.
- refresh 실패가 확정된 경우에만 options page 또는 상태 UI에서 재로그인을 요구한다.
- `/prompts/analyze` 요청은 `request_timeouts.analyze_request_ms` 기준으로 timeout 처리한다.
- analyze timeout, 네트워크 실패, 서버 미응답은 silent allow로 처리하지 않는다. 확장앱은 전송을 보류하고 사용자에게 재시도 또는 취소 UX를 보여준다.

options page:

- PromptGuard API URL을 저장한다.
- login/logout 상태를 보여준다.
- 연결 테스트를 수행한다.
- `GET /auth/me`로 현재 인증 상태를 확인한다.
- `GET /config/extension`으로 원격 확장앱 설정을 확인하고 마지막 sync time을 표시한다.
- server status 확인이 필요한 경우 `GET /dashboard/status` 또는 health endpoint 결과를 사용자에게 안전한 문구로 표시한다.
- service worker inactive 자체를 오류로 표시하지 않는다.
- refresh token 만료, refresh 실패, 계정 비활성, 서버 변경, 인증 실패처럼 사용자의 조치가 필요한 상태만 오류로 표시한다.

### 11.2 Action UX

확장앱은 서버 응답의 top-level `action`, `allow_original_send`, `requires_user_confirmation`, `masked_prompt`만 기준으로 전송 동작을 결정한다. `detections[]`, `input_results[]`, `content_unavailable_inputs[]`를 보고 최종 action을 다시 계산하지 않는다.

Allow:

- `allow_original_send: true`이면 원래 전송을 1회 재실행한다.
- Allow는 불필요한 panel을 표시하지 않는다.
- double-submit guard를 유지해 동일 전송이 중복 실행되지 않게 한다.

Warn:

- 전송을 보류하고 경고 UI를 표시한다.
- MVP에서는 Warn 사유 입력 또는 justification 저장 기능을 제공하지 않는다.
- 사용자가 확인하면 원래 입력을 1회 전송한다.
- 사용자가 취소하면 전송하지 않는다.

Mask:

- 서버가 응답한 `masked_prompt`를 composer text에 적용한다.
- 원본 composer text는 전송하지 않는다.
- `masked_prompt`는 composer text에만 적용한다.
- file text, attachment metadata, unsupported attachment, content unavailable 입력은 확장앱이 자동 수정하지 않는다.
- Mask 적용 후 사용자가 확인하면 마스킹된 composer text를 1회 전송한다.
- 서버가 `requires_user_confirmation: true`를 함께 반환하면 warning/confirmation UI를 표시한 뒤 사용자가 확인한 경우에만 마스킹된 텍스트를 전송한다.

Block:

- 원문 전송을 발생시키지 않는다.
- 사용자가 이해할 수 있는 차단 사유를 표시한다.
- content unavailable 입력 때문에 Block된 경우, 확장앱은 “내용을 확인할 수 없는 첨부 또는 입력이 있어 전송을 차단했다”는 식의 안전한 설명을 표시한다.

### 11.3 재전송과 중복 방지

- 확장앱은 서버 분석이 끝나기 전 원래 전송을 발생시키지 않는다.
- 서버 응답 적용 후 허용된 경우에만 보호된 재전송을 1회 수행한다.
- 보호된 재전송 중 발생한 click/Enter는 다시 분석 요청을 만들지 않도록 replay guard를 둔다.
- 각 analyze request에는 `client_request_id`를 포함한다.
- 같은 전송 시도에 대해 중복 analyze 요청이 발생해도 서버의 idempotency 계약을 따른다.
- Mask 적용 후 재전송할 때 원본 텍스트를 되살려 전송하지 않는다.

### 11.4 설정과 selector

- 확장앱은 built-in fallback selector를 가진다.
- 서버가 내려주는 AI 서비스별 selector config는 built-in selector를 override할 수 있다.
- selector override는 composer, send button, attachment chip, file input 감지에 사용할 수 있다.
- selector 설정이 없거나 실패하면 built-in fallback selector로 동작한다.
- AI 서비스별 capability에 따라 composer text, converted paste, attachment chip, file input 감지 가능 여부를 다르게 처리한다.
- selector 실패, composer 미탐지, send button 미탐지는 오류 UI 또는 상태 표시로 남기되, 원본 전송을 조용히 허용하지 않는다.

### 11.5 확장앱 저장소와 금지사항

확장앱은 다음 정보를 저장할 수 있다.

- PromptGuard API URL
- access token
- refresh token
- token 만료 시각
- 마지막 extension config
- 마지막 config sync time
- built-in fallback selector version
- 최근 연결 상태 metadata

확장앱은 다음 정보를 장기 저장하지 않는다.

- composer 원문
- paste 원문
- file text 원문
- `masked_prompt`
- 탐지값 원문
- 원본 파일명
- full request body
- full response body

일시적으로 메모리에 보관한 입력 내용은 analyze 요청 생성과 UX 적용이 끝나면 폐기한다.

## 12. MVP 대시보드 계약

대시보드는 ADMIN 전용 metadata UI다. Overview, Events, Event Detail, Users, Filter Rule Management, Server Status 화면은 집계와 안전한 metadata만 보여준다.

대시보드는 HTML/CSS/TypeScript로 구현하는 multi-page dashboard다. 각 화면은 개별 HTML 파일을 진입점으로 사용하며, 화면 렌더링과 사용자 상호작용은 해당 페이지에 연결된 TypeScript 코드에서 컴파일된 JavaScript가 담당한다. 데이터 조회와 상태 변경은 브라우저에서 실행되는 JavaScript가 FastAPI API를 호출해 수행한다.

대시보드는 USER 접근을 허용하지 않는다. USER가 대시보드 화면이나 대시보드 API에 접근하면 session 상태에 따라 login page로 이동하거나 `403`으로 처리한다.

운영 단계 전 로컬 개발, 화면 검수, 데모 편의를 위해 대시보드는 실제 로그인 없이 화면 shell에 진입 가능한 dev-only bypass를 둘 수 있다. dev-only bypass는 운영 배포에서 기본 비활성화되어야 하며, ADMIN session 계약이나 보호 API 인증을 대체하지 않는다. dev-only bypass 상태에서도 실제 보호 API 호출은 인증/권한 계약을 따른다.

### 12.1 대시보드 화면

Login:

- HTML entry: `login.html`
- `login_id` input
- password input
- 로그인 버튼
- CSRF token 요청 후 dashboard session login 수행
- 세션 만료 시 login page 이동
- 이미 유효한 ADMIN session이 있으면 `overview.html`로 이동
- MVP에서는 상세 로그인 실패 원인별 고급 UI를 필수로 두지 않는다

Overview:

- HTML entry: `overview.html`
- 카드: Total Events, Blocked, Masked, Warned, Active Users
- 차트: action별 통계, 기간별 통계
- 이동 버튼: Events, Users, Filter Rule Management, Server Status, Logout
- `GET /dashboard/overview` API를 호출해 카드와 기본 차트 데이터를 렌더링한다

Events:

- HTML entry: `events.html`
- `GET /dashboard/events` API를 호출해 이벤트 목록을 렌더링한다
- 테이블 컬럼: 시간, 사용자, 서비스, action, 위험도, 대표 탐지 category, 대표 탐지 type, 탐지 수, 입력 수, content unavailable 수, 상세보기
- 상세보기 클릭 시 `event-detail.html?event_id=...`로 이동한다

Event Detail:

- HTML entry: `event-detail.html`
- URL query parameter `event_id`를 읽어 `GET /dashboard/events/{event_id}` API를 호출한다
- 필드: event ID, time, user, service, platform, action, risk score, risk level, detection summary, detections, input results, content unavailable inputs, Business Context metadata
- 이벤트 상세 UI 표시 금지 내부 식별자: `filter_config_revision`, `filter_rule_version`, `prompt_hash_prefix`, `input_bundle_hash_prefix`, `request_fingerprint`
- Business Context는 configured matched keywords와 count를 표시할 수 있다
- 입력 본문이나 원문 주변 문맥은 표시하지 않는다

Users:

- HTML entry: `users.html`
- `GET /dashboard/users` API를 호출해 사용자 목록과 사용자별 기본 이벤트 통계를 렌더링한다
- 컬럼: login ID, 사용자 이름, 부서, 권한, 상태, 마지막 이벤트 시간, 생성일, 이벤트 수, Blocked, Masked, Warned
- ADMIN은 사용자 생성, role 변경, status 변경을 수행할 수 있다
- MVP에서는 사용자 삭제를 hard delete로 처리하지 않고 `DISABLED` 상태로 비활성화한다
- hard delete 또는 사용자 데이터 익명화는 운영 retention 정책이 필요해지는 단계에서 별도 기능으로 다룬다
- 표시정보 수정 전용 API와 UI는 MVP 기본 범위에 포함하지 않는다

Filter Rule Management:

- HTML entry: `filters.html`
- built-in detector, custom keyword, custom regex, Business Context rule을 하나의 Filter Rule 목록에서 보여준다
- Filter Rule은 `origin`, `kind`, `category`를 표시한다
- built-in detector form은 `enabled`, `severity`, `action`만 수정할 수 있다
- custom keyword form은 keyword 목록, 제외 keyword, label, description, placeholder, severity, action, enabled를 수정한다
- custom regex form은 pattern, label, description, placeholder, severity, action, enabled를 수정하고 regex validation error를 표시한다
- context rule form은 keyword groups, exclusion keywords, window size, minimum condition count, sensitivity `low/medium/high`, severity, action, enabled를 제공한다
- built-in filter는 삭제할 수 없고, custom filter/context rule은 disabled 또는 archived 처리한다

Dry-run panel:

- Filter Rule Management 화면 안에 둔다
- 관리자는 Filter Rule 작성/수정 form에서 sample text를 입력하고 dry-run을 실행할 수 있다
- dry-run은 `POST /dashboard/filters/dry-run`을 호출한다
- 저장된 rule은 `rule_id`로 테스트할 수 있고, 저장 전 작성 중인 rule은 draft rule payload로 테스트할 수 있다
- dry-run은 sample text를 저장하지 않고 event도 만들지 않는다
- dry-run은 단일 Filter Rule이 sample text에 match되는지 확인하는 기능이다
- MVP dry-run은 여러 rule이 동시에 실행됐을 때의 최종 action 조합이나 전체 send attempt orchestration을 시뮬레이션하지 않는다
- dry-run 결과는 `matched`, `expected_action`, `expected_severity`, `match_count`, `reason_code`, `matched_keywords`, `evidence_counts`, `sample_persisted=false`를 표시한다
- regex rule의 경우 syntax error와 처리 불가능한 regex는 저장 전과 같은 기준으로 검증하고 오류를 표시한다

Server Status:

- HTML entry: `status.html`
- `GET /dashboard/status` API를 호출한다
- 8.8의 필수 상태 항목인 API, PostgreSQL, Migration, Filter Rules, Last Checked를 표시한다
- 선택 상태 항목은 8.8의 선택 반환값을 따른다
- 상태: `healthy`, `degraded`, `unhealthy`, `disabled`, `unknown`
- `disabled`는 optional feature에만 적용하고 API/PostgreSQL/Migration에는 적용하지 않는다
- Filter Rule 상세 설정, 환경변수 상세값, DB URL, secret, token, stack trace는 표시하지 않는다
- OS 배포판, kernel version, container image digest 같은 세부 runtime 정보는 MVP 기본 표시 범위에 포함하지 않는다

명확화:

- 탐지 설정을 관리하는 관리자 화면은 Filter Rule Management 하나뿐이다. 별도 설정 화면은 만들지 않는다
- 대시보드 API와 DOM은 metadata-only를 유지한다
- 대시보드는 서버가 반환하거나 저장한 top-level `action`을 그대로 표시한다. `detections[]`, `input_results[]`, `content_unavailable_inputs[]`는 해당 action의 근거 metadata로만 렌더링하며, 대시보드 TypeScript는 이 배열들을 조합해 action을 새로 계산하지 않는다

### 12.2 대시보드 화면 계약

| Screen       | HTML entry                       | APIs used                                                                                                                                                                                                                                                                 | Required UI                                                                       | Empty state               | Loading state      | Error state                              | Permission           | Test/verification                                   |
| ------------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------- | ------------------ | ---------------------------------------- | -------------------- | --------------------------------------------------- |
| Login        | `login.html`                     | `GET /dashboard/session/csrf`, `POST /dashboard/session/login`, `GET /dashboard/session/me`                                                                                                                                                                               | login ID, password, 로그인 버튼                                                        | 이미 로그인 시 Overview 이동      | login 요청 pending   | session 만료 시 login 이동, safe error banner | public/ADMIN session | localStorage session 금지, CSRF/session cookie        |
| Overview     | `overview.html`                  | `GET /dashboard/overview`                                                                                                                                                                                                                                                 | 카드, action/period 차트, 이동 버튼, 로그아웃                                                 | 이벤트 없음                    | skeleton/spinner   | safe error banner                        | ADMIN                | metadata만 렌더링                                       |
| Events       | `events.html`                    | `GET /dashboard/events`                                                                                                                                                                                                                                                   | 이벤트 테이블, 상세보기 링크                                                                  | 이벤트 없음                    | table loading      | safe API errors                          | ADMIN                | version 식별자 UI 없음, metadata-only 렌더링                |
| Event Detail | `event-detail.html?event_id=...` | `GET /dashboard/events/{event_id}`                                                                                                                                                                                                                                        | 이벤트 상세 metadata                                                                   | 이벤트 없음 또는 event not found | detail loading     | safe API errors                          | ADMIN                | 입력 본문/파일 내용/전체 `masked_prompt`/원본 파일명 없음            |
| Users        | `users.html`                     | `GET /dashboard/users`, `POST /dashboard/users`, `PATCH /dashboard/users/{login_id}/role`, `PATCH /dashboard/users/{login_id}/status`                                                                                                                                     | user list, add user, role/status change                                           | 사용자 없음                    | table/form loading | validation/RBAC errors                   | ADMIN                | MVP hard delete 없음, USER 403                        |
| Filters      | `filters.html`                   | `GET /dashboard/filters`, `GET /dashboard/filters/{id}`, `POST /dashboard/filters`, `PATCH /dashboard/filters/{id}`, `PATCH /dashboard/filters/{id}/enable`, `PATCH /dashboard/filters/{id}/disable`, `DELETE /dashboard/filters/{id}`, `POST /dashboard/filters/dry-run` | 통합 Filter Rule list, forms, dry-run panel                                         | filter 없음                 | list/form loading  | regex/editable\_fields/dry-run errors    | ADMIN                | origin/kind rules, sample 미저장                       |
| Status       | `status.html`                    | `GET /dashboard/status`                                                                                                                                                                                                                                                   | API/PostgreSQL/Migration/Filter Rules/Last Checked, optional app/runtime metadata | unknown info              | polling/loading    | unhealthy/degraded/unknown 표시            | ADMIN                | secret, DB URL, stack trace, 필터 설정 상세값, 환경변수 상세값 없음 |

### 12.3 화면별 조회·통계 API 계약

모든 dashboard API는 metadata-only다.

이 섹션은 Overview, Users, Events 화면이 어떤 API 응답을 사용해 화면을 렌더링하는지 정의한다. 여기서 `GET /dashboard/events`, `GET /dashboard/events/{event_id}`, `GET /dashboard/overview`, `GET /dashboard/users`는 FastAPI API endpoint이며, 대시보드 HTML entry가 아니다.

#### Overview 화면 조회·통계

Overview 화면은 전체 현황 카드와 기본 차트를 보여준다.

사용 API:

| API                       | 화면 사용 위치        | 응답 사용 목적                                                                                                 |
| ------------------------- | --------------- | -------------------------------------------------------------------------------------------------------- |
| `GET /dashboard/overview` | Overview 카드와 차트 | Total Events, Blocked, Masked, Warned, Active Users, content unavailable event 수, action별 통계, 기간별 이벤트 통계 |

`GET /dashboard/overview` response:

| 필드                                | 의미                                       |
| --------------------------------- | ---------------------------------------- |
| `period_start`                    | 집계 시작 시각                                 |
| `period_end`                      | 집계 종료 시각                                 |
| `event_count`                     | 기간 내 분석 이벤트 수                            |
| `blocked_count`                   | `action=Block` 이벤트 수                     |
| `masked_count`                    | `action=Mask` 이벤트 수                      |
| `warned_count`                    | `action=Warn` 이벤트 수                      |
| `allowed_count`                   | `action=Allow` 이벤트 수                     |
| `active_user_count`               | 기간 내 이벤트가 1개 이상 있는 distinct `login_id` 수 |
| `content_unavailable_event_count` | content unavailable 입력이 포함된 이벤트 수        |
| `last_event_at`                   | 마지막 이벤트 시각                               |
| `action_counts[]`                 | action별 count                            |
| `risk_level_counts[]`             | risk level별 count                        |
| `detector_category_counts[]`      | 탐지 category별 count                       |
| `period_buckets[]`                | 기간별 이벤트 count                            |

`period_buckets[]`는 차트용 시간 구간별 집계 배열이다. 예를 들어 기본 기간이 최근 30일이면 1일 단위 bucket 30개를 반환해 일자별 이벤트 추이를 그릴 수 있게 한다.

`period_buckets[]` item:

| 필드              | 의미           |
| --------------- | ------------ |
| `bucket_start`  | bucket 시작 시각 |
| `bucket_end`    | bucket 종료 시각 |
| `event_count`   | 이벤트 수        |
| `blocked_count` | Block 수      |
| `masked_count`  | Mask 수       |
| `warned_count`  | Warn 수       |

#### Users 화면 조회·통계

Users 화면은 사용자 목록과 사용자별 기본 이벤트 통계를 보여준다.

| API                    | 화면 사용 위치        | 응답 사용 목적                                                                         |
| ---------------------- | --------------- | -------------------------------------------------------------------------------- |
| `GET /dashboard/users` | Users 목록과 통계 컬럼 | login ID, 사용자 이름, 부서, role, status, 생성일, 마지막 이벤트 시간, 사용자별 event/action aggregate |

`GET /dashboard/users` response row:

| 필드              | 의미                     |
| --------------- | ---------------------- |
| `login_id`      | 사용자 식별자                |
| `username`      | 표시 이름                  |
| `department`    | 부서                     |
| `role`          | `USER` 또는 `ADMIN`      |
| `status`        | `ACTIVE` 또는 `DISABLED` |
| `created_at`    | 생성 시각                  |
| `last_login_at` | 마지막 로그인 시각             |
| `last_event_at` | 마지막 이벤트 시각             |
| `event_count`   | 기간 내 이벤트 수             |
| `blocked_count` | Block 수                |
| `masked_count`  | Mask 수                 |
| `warned_count`  | Warn 수                 |

#### Events 화면 조회·상세

Events 화면은 이벤트 목록과 이벤트 상세 metadata를 보여준다.

| API                                | 화면 사용 위치        | 응답 사용 목적                                                                                            |
| ---------------------------------- | --------------- | --------------------------------------------------------------------------------------------------- |
| `GET /dashboard/events`            | Events 목록       | 시간, 사용자, 서비스, action, 위험도, 대표 탐지 category/type, 탐지 수, 입력 수, content unavailable 수                   |
| `GET /dashboard/events/{event_id}` | Event Detail 화면 | detection summary, detections, input results, content unavailable inputs, Business Context metadata |

Events 화면에서 이벤트 상세를 표시하는 MVP 기본 방식은 `event-detail.html?event_id=...`로 이동하는 것이다. `event-detail.html`의 TypeScript는 query parameter의 `event_id`를 읽고 `GET /dashboard/events/{event_id}`를 호출해 상세 metadata를 렌더링한다.

`GET /dashboard/events/{event_id}`는 대시보드 HTML entry가 아니라 FastAPI API endpoint다.

Events 화면은 최종 action을 다시 계산하지 않는다. 서버가 저장한 event metadata를 조회해 표시한다.

시간 기준:

- 기본 통계 기간은 최근 30일이다
- 서버 저장 시각은 UTC 기준으로 저장한다
- 대시보드는 표시 시 browser timezone으로 변환한다

### 12.4 대시보드 보안·표시 규칙

- 대시보드는 bearer token을 사용하지 않고 ADMIN session cookie를 사용한다
- 대시보드 session id는 `localStorage`에 저장하지 않는다
- 상태 변경 요청은 CSRF token을 사용한다
- API 응답값을 DOM에 표시할 때 원칙적으로 `textContent` 또는 안전한 DOM API를 사용한다
- 대시보드 API와 DOM은 저장된 metadata만 사용한다. 입력 본문, 파일 내용, 전체 `masked_prompt`를 조회하거나 표시하는 흐름은 포함하지 않는다
- 내부 version 식별자, DB 연결 문자열, 환경변수 상세값, secret, token은 표시하지 않는다

## 13. MVP Analyze 요청 처리 한도와 환경변수 계약

이 단원은 `POST /prompts/analyze` 요청에 포함할 수 있는 text 본문 크기, 파일 text 처리 한도, 전체 request body 한도, 서버 환경변수 기준을 정의한다.

요청 크기와 파일 text 처리 한도는 byte 기준으로 둔다. Python/JavaScript string length는 요청 처리 한도의 최종 기준으로 쓰지 않는다.

### 13.1 Analyze 요청 크기 한도

`POST /prompts/analyze`는 `inputs[]` 하나로 입력을 표현한다. 각 입력은 `kind`, `source`, `size_bytes`, `content_included`를 가진다.

기본 한도값:

| 한도                               | 기본값       | 의미                                                                                 |
| -------------------------------- | --------- | ---------------------------------------------------------------------------------- |
| `MAX_COMPOSER_TEXT_BYTES`        | `262144`  | send 시점 composer text 최대 크기                                                        |
| `MAX_CONVERTED_PASTE_TEXT_BYTES` | `1048576` | paste가 attachment/file로 변환되어 composer에 남지 않은 경우, 확장앱이 캡처한 text를 요청에 포함할 수 있는 최대 크기 |
| `MAX_FILE_TEXT_SCAN_BYTES`       | `1048576` | 허용된 작은 텍스트 계열 파일을 읽어 요청에 포함할 수 있는 최대 크기                                            |
| `MAX_ANALYZE_REQUEST_BYTES`      | `2097152` | `/prompts/analyze` 전체 request body 최대 크기                                           |

처리 한도 안에 들어오는 text input은 요청에 포함하고 서버에서 분석한다.

처리 한도를 초과한 text input은 request body에 본문을 포함하지 않는다. 이 경우 확장앱은 해당 input을 `content_included: false`, `content_unavailable_reason: "oversized"`, `limit_exceeded` metadata와 함께 보낸다.

서버는 `content_included: false` 입력을 content unavailable 입력으로 보고, silent allow로 처리하지 않는다. 기본 action은 `Block`이며, 정책에서 허용하는 경우 `Warn`으로 낮출 수 있다.

서버는 `MAX_ANALYZE_REQUEST_BYTES`를 request parsing 전에 적용해야 한다. 확장앱의 client-side 한도만으로 request 크기 한도를 보장하지 않는다.

### 13.2 파일 text 처리 한도

MVP에서 파일 내용 스캔은 확장앱이 raw `File` 객체를 확보할 수 있고, 파일이 허용된 작은 텍스트 계열이며, 크기 한도 안에 있을 때만 적용한다.

허용 확장자 기본값:

| 확장자     |
| ------- |
| `.txt`  |
| `.md`   |
| `.csv`  |
| `.json` |
| `.yaml` |
| `.yml`  |
| `.log`  |

허용 MIME 기본값:

| MIME                 |
| -------------------- |
| `text/*`             |
| `application/json`   |
| `application/x-yaml` |
| `application/yaml`   |

encoding은 UTF-8을 우선한다. UTF-8로 읽을 수 없거나 text로 안전하게 처리할 수 없으면 `415` 또는 `422`로 처리한다.

binary sniffing에서 null byte 또는 높은 binary ratio가 나오면 text input으로 처리하지 않는다.

MVP에서 다음 처리는 제공하지 않는다.

- PDF parsing
- Office document parsing
- OCR
- archive extraction
- binary analysis
- malware scanning
- image content scan
- base64 payload scan

파일 내용을 읽을 수 없거나 MVP 미지원 파일이면 가능한 metadata만 `attachment_metadata`로 표현한다. metadata도 부족하면 `unsupported_attachment`로 표현한다.

`attachment_metadata`에는 extension, MIME, size, count, attachment kind, attachment index 같은 metadata-only 정보를 담는다. 원본 파일명, raw file bytes, base64 payload, OCR text는 포함하지 않는다.

### 13.3 환경변수 계약

| 변수                               | 범위         | 예시                                                                       | 설명                                     |
| -------------------------------- | ---------- | ------------------------------------------------------------------------ | -------------------------------------- |
| `DATABASE_URL`                   | MVP 필수     | `postgresql+psycopg://promptguard:promptguard@postgres:5432/promptguard` | PostgreSQL 연결                          |
| `PROMPTGUARD_JWT_SECRET`         | MVP 필수     | `dev-only-change-me`                                                     | access token signing secret. 운영값 커밋 금지 |
| `PROMPTGUARD_REFRESH_SECRET`     | MVP 필수     | `dev-only-change-me`                                                     | refresh token hash pepper. 운영값 커밋 금지   |
| `CORS_ALLOWED_ORIGINS`           | MVP 필수     | `chrome-extension://...,http://localhost:3000`                           | 명시 allowlist. credential wildcard 금지   |
| `ACCESS_TOKEN_TTL_SECONDS`       | MVP 선택 기본값 | `900`                                                                    | access token TTL                       |
| `REFRESH_TOKEN_TTL_DAYS`         | MVP 선택 기본값 | `30`                                                                     | refresh token TTL                      |
| `REFRESH_IDLE_TIMEOUT_DAYS`      | MVP 선택 기본값 | `14`                                                                     | refresh idle timeout                   |
| `DASHBOARD_SESSION_TTL_HOURS`    | MVP 선택 기본값 | `12`                                                                     | dashboard ADMIN session TTL            |
| `MAX_COMPOSER_TEXT_BYTES`        | MVP 선택 기본값 | `262144`                                                                 | composer text byte limit               |
| `MAX_CONVERTED_PASTE_TEXT_BYTES` | MVP 선택 기본값 | `1048576`                                                                | converted paste text byte limit        |
| `MAX_FILE_TEXT_SCAN_BYTES`       | MVP 선택 기본값 | `1048576`                                                                | text file transient scan byte limit    |
| `MAX_ANALYZE_REQUEST_BYTES`      | MVP 선택 기본값 | `2097152`                                                                | full analyze request body byte limit   |
| `REDIS_URL`                      | 선택 구성      | empty                                                                    | Redis 선택 profile에서만 사용                 |

`.env.example`에는 실제 secret처럼 보이는 값을 넣지 않는다. secret 값은 dummy placeholder로 둔다.

`/dashboard/status` 반환값은 8.8의 필수/선택 필드 계약을 따른다. 환경변수 상세값과 secret 값은 반환하지 않는다.

### 13.4 확장앱 설정 응답과 환경변수 매핑

`GET /config/extension`은 서버 환경변수 또는 서버 설정값을 확장앱이 쓰기 쉬운 JSON field로 내려준다.

| 환경변수                             | `/config/extension` 응답 field              |
| -------------------------------- | ----------------------------------------- |
| `MAX_COMPOSER_TEXT_BYTES`        | `input_limits.composer_text_bytes`        |
| `MAX_CONVERTED_PASTE_TEXT_BYTES` | `input_limits.converted_paste_text_bytes` |
| `MAX_FILE_TEXT_SCAN_BYTES`       | `input_limits.file_text_scan_bytes`       |
| `MAX_ANALYZE_REQUEST_BYTES`      | `input_limits.analyze_request_bytes`      |

`request_timeouts` 기본값:

```json
{
  "request_timeouts": {
    "config_request_ms": 5000,
    "analyze_request_ms": 8000
  }
}
```

`input_limits` 기본값:

```json
{
  "input_limits": {
    "composer_text_bytes": 262144,
    "converted_paste_text_bytes": 1048576,
    "file_text_scan_bytes": 1048576,
    "analyze_request_bytes": 2097152
  }
}
```

`input_limits`는 고정 key-value map으로 표현한다.

### 13.5 테스트 기준

Analyze 요청 크기 한도 테스트:

- `MAX_COMPOSER_TEXT_BYTES` 이하 composer text는 요청에 포함된다.
- `MAX_COMPOSER_TEXT_BYTES` 초과 composer text는 본문을 포함하지 않고 content unavailable metadata로 처리된다.
- `MAX_CONVERTED_PASTE_TEXT_BYTES` 이하 converted paste text는 요청에 포함된다.
- `MAX_CONVERTED_PASTE_TEXT_BYTES` 초과 converted paste text는 본문을 포함하지 않는다.
- `MAX_FILE_TEXT_SCAN_BYTES` 이하 허용 text file은 `kind: "text"`, `source: "file"`, `content_included: true`로 처리된다.
- 허용되지 않는 파일 형식은 `attachment_metadata` 또는 `unsupported_attachment`로 처리된다.
- `MAX_ANALYZE_REQUEST_BYTES` 초과 요청은 서버에서 차단된다.

환경변수 테스트:

- `.env.example`은 필요한 변수 목록을 포함한다.
- `.env.example`은 실제 secret처럼 보이는 값을 포함하지 않는다.
- 서버는 환경변수 기본값과 override 값을 모두 로드할 수 있다.
- `/config/extension`은 환경변수 기반 input limit을 snake\_case JSON field로 반환한다.
- `/dashboard/status`는 환경변수 상세값이나 secret 값을 반환하지 않는다.

## 14. MVP 보안·개인정보 계약

이 단원은 기능 시연용 MVP에서 지켜야 하는 보안·개인정보 기준을 정의한다.

이 문서에서 `입력 본문`은 `POST /prompts/analyze` 요청의 `inputs[]` 중 `content_included: true`로 포함된 실제 텍스트 값을 뜻한다. 예를 들어 composer text, converted paste text, file text가 이에 해당한다. `content_included: false`인 입력은 내용 없이 metadata-only로 처리한다.

### 14.1 MVP 보안 기준

MVP 기능 시연에서도 아래 보안 기준은 지킨다.

계정/권한:

- 기본 ADMIN 비밀번호는 `password_hash`로만 저장한다.
- USER와 ADMIN 권한을 분리한다.
- USER는 대시보드 화면과 대시보드 API에 접근할 수 없다.
- `DISABLED` 사용자는 token/session이 형식상 유효해도 API 처리나 대시보드 접근이 차단된다.

Token/session:

- refresh token 원문은 저장하지 않고 hash와 metadata만 저장한다.
- dashboard session id 원문은 저장하지 않고 hash와 metadata만 저장한다.
- dashboard session id는 `localStorage`에 저장하지 않는다.
- 대시보드 상태 변경 요청은 CSRF token을 사용한다.

데이터 저장/표시:

- 입력 본문, 파일 내용, 전체 `masked_prompt`, 탐지값 원문, 원본 파일명은 DB와 대시보드 API/DOM에 저장하거나 표시하지 않는다.
- `masked_prompt`는 Mask 응답에서만 일시적으로 반환한다.
- dry-run sample text는 저장하지 않고 event도 만들지 않는다.
- 대시보드 API와 DOM은 저장된 metadata와 aggregate를 기준으로 동작한다.

기본 로그/오류:

- request body 전체 logging은 기본 비활성화한다.
- error handler는 exception object를 그대로 직렬화하지 않는다.
- DB 연결 문자열, secret, token, session id 원문은 health/status/error/dashboard 응답에 포함하지 않는다.

Custom regex:

- Custom regex rule은 저장 전에 syntax와 길이를 검증한다.
- syntax 오류 또는 처리 불가능한 regex는 `422`로 거부한다.

## 15. MVP 수용 기준·테스트 게이트

이 단원은 기능 시연용 MVP 수용 기준, 필수 테스트, 최종 smoke 시나리오를 정의한다.

MVP는 fresh install, API, dashboard, extension, 기본 privacy smoke가 통과할 때 수용한다.

### 15.1 MVP 수용 기준

MVP는 아래 흐름이 fresh install 기준으로 끊기지 않고 통과할 때 수용한다.

1. 관리자가 루트 `.env.example`을 기준으로 환경변수를 구성한다.
2. `docker compose up --build` 또는 문서화된 로컬 실행 절차로 API 서버와 PostgreSQL을 시작한다.
3. DB migration과 초기 데이터 생성이 완료된다.
4. 기본 ADMIN 계정 `admin / 1234`가 존재하고, password는 hash로만 저장된다.
5. `GET /livez`, `GET /readyz`, `GET /healthz`가 계약된 상태 규칙대로 동작한다.
6. `login.html`에서 기본 ADMIN으로 dashboard session login이 가능하다.
7. ADMIN은 `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`에 접근할 수 있다.
8. ADMIN은 `POST /dashboard/users`로 USER 또는 ADMIN을 생성할 수 있다.
9. ADMIN은 `PATCH /dashboard/users/{login_id}/role`, `PATCH /dashboard/users/{login_id}/status`로 role/status를 변경할 수 있다.
10. USER는 확장앱 보호 API를 사용할 수 있지만 대시보드 화면과 대시보드 API에는 접근할 수 없다.
11. Chrome Extension options에서 PromptGuard API URL을 저장하고, `GET /auth/me`, `GET /config/extension`을 확인할 수 있다.
12. Chrome Extension은 지원 대상 AI 서비스 화면에서 composer, send button, attachment chip 후보를 감지한다.
13. 사용자가 전송을 시도하면 확장앱은 원래 전송을 보류하고 `POST /prompts/analyze`를 호출한다.
14. 서버는 `inputs[]` 기반 send attempt를 분석하고 top-level `action` 하나를 반환한다.
15. 확장앱은 Allow/Warn/Mask/Block UX를 계약대로 적용한다.
16. 작은 텍스트 파일은 한도 안에서 `kind: "text"`, `source: "file"`, `content_included: true`로 분석 요청에 포함할 수 있다.
17. Mask는 서버가 응답한 `masked_prompt`를 composer text에 적용하고, 원본 composer text를 전송하지 않는다.
18. 대시보드는 Overview, Events, Users, Filters, Status 화면에서 저장된 metadata와 aggregate만 표시한다.
19. Filter Rule Management는 built-in detector, custom keyword, custom regex, Business Context rule을 하나의 Filter Rule 모델로 관리한다.
20. `POST /dashboard/filters/dry-run`은 sample text를 저장하지 않고 event도 만들지 않는다.
21. Docker fresh-install smoke, 핵심 기능 smoke, 기본 privacy smoke가 통과한다.

### 15.2 영역별 완료 기준

API/Auth:

- 기본 ADMIN 계정이 fresh DB에서 1회 생성된다.
- 기본 ADMIN password는 hash로만 저장된다.
- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`가 동작한다.
- refresh token은 원문 저장 없이 hash와 metadata로 관리된다.
- `DISABLED` 사용자는 token/session이 형식상 유효해도 API 처리나 대시보드 접근이 차단된다.
- USER는 대시보드 API에 접근할 수 없다.
- 현재 로그인한 ADMIN이 자기 자신의 role을 `USER`로 낮추거나 status를 `DISABLED`로 바꾸는 요청은 거부된다.
- 마지막 `ACTIVE` ADMIN을 없애는 role/status 변경은 거부된다.

Analyze:

- `POST /prompts/analyze`는 top-level `prompt`, `input`, `file`, `attachments` 필드 없이 `inputs[]` 하나로 입력을 받는다.
- `content_included: true`인 text input은 서버에서 분석된다.
- `content_included: false`인 입력은 content unavailable 입력으로 처리된다.
- 처리 한도 초과 본문은 request body에 포함하지 않는다.
- 작은 텍스트 파일은 한도 안에서 text input으로 분석된다.
- built-in detector, custom keyword, custom regex, Business Context rule이 pipeline에서 실행된다.
- 서버는 최종 action 하나를 `Block > Mask > Warn > Allow` 우선순위로 결정한다.
- `Mask` 응답은 composer text용 `masked_prompt`를 포함한다.
- file text, attachment metadata, unsupported attachment, content unavailable 입력은 자동 수정하지 않는다.
- `client_request_id` 기반 중복 요청 처리로 duplicate event를 만들지 않는다.

Filter Rule:

- Filter Rule은 `origin`, `kind`, `category`, `editable_fields` 기준으로 동작한다.
- built-in detector는 삭제할 수 없고 `enabled`, `severity`, `action`만 수정할 수 있다.
- custom keyword, custom regex, context rule은 생성, 수정, 비활성화 또는 archive 처리할 수 있다.
- regex rule은 syntax와 길이 검증을 통과해야 저장된다.
- `POST /dashboard/filters/dry-run`은 저장 전 draft rule payload 또는 저장된 `rule_id` 기준으로 sample text를 테스트할 수 있다.
- dry-run은 sample text를 저장하지 않고 event를 만들지 않는다.
- dry-run 결과는 safe metadata만 반환한다.

Dashboard:

- 대시보드는 `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`을 기준으로 동작한다.
- 대시보드 화면은 HTML entry와 TypeScript-compiled JavaScript로 구성된다.
- 대시보드 API는 `/dashboard/*` namespace를 사용한다.
- Overview는 `GET /dashboard/overview`로 카드와 기본 차트를 렌더링한다.
- Events는 `GET /dashboard/events`로 목록을 렌더링한다.
- Event Detail은 `event-detail.html?event_id=...`에서 `GET /dashboard/events/{event_id}`를 호출해 상세 metadata를 렌더링한다.
- Users는 `GET /dashboard/users`로 사용자 목록과 기본 이벤트 통계를 렌더링한다.
- Filters는 `/dashboard/filters*` API로 Filter Rule 목록, 상세, 생성/수정, enable/disable, dry-run을 처리한다.
- Status는 `GET /dashboard/status`로 API, PostgreSQL, Migration, Filter Rules, Last Checked를 표시한다.
- 대시보드는 서버가 저장한 top-level `action`을 그대로 표시한다. `detections[]`, `input_results[]`, `content_unavailable_inputs[]`는 근거 metadata로만 렌더링한다.

Extension:

- content script는 지원 대상 domain에서만 동작한다.
- composer, send button, attachment chip 후보를 감지한다.
- click/Enter 전송을 서버 분석 완료 전 보류한다.
- `@` mention, IME composition, Shift+Enter, picker 동작을 전송으로 오판하지 않는다.
- 일반 paste는 최종 composer text로 처리한다.
- converted paste는 AI 서비스가 attachment/file처럼 변환해 composer에 남지 않은 경우에만 별도 입력으로 처리한다.
- raw `File` 객체를 확보하고 허용된 작은 텍스트 계열 파일이면 `kind: "text"`, `source: "file"`로 요청에 포함한다.
- analyze timeout, 네트워크 실패, 서버 미응답은 silent allow로 처리하지 않는다.
- Allow/Warn/Mask/Block UX가 실제 API 응답 기준으로 동작한다.
- protected replay는 1회만 수행하고 double-submit을 방지한다.

기본 privacy smoke:

- 입력 본문, 파일 내용, 전체 `masked_prompt`, 탐지값 원문, 원본 파일명이 DB, dashboard API/DOM, error response에 남지 않는다.
- refresh token 원문과 dashboard session id 원문은 저장하지 않는다.
- dashboard session id는 `localStorage`에 저장하지 않는다.
- dry-run sample text는 저장되지 않고 event도 만들지 않는다.
- `/dashboard/status`는 DB URL, secret, token, stack trace를 반환하지 않는다.

### 15.3 MVP 기능 시연 게이트

| 게이트                 | 완료 기준                                                                                    | 실패 시 처리                                |
| ------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------- |
| 설치                  | fresh clone/export에서 `.env.example` 기반 API와 PostgreSQL 시작                                | 설치 문서, compose, env 수정                 |
| DB                  | Alembic migration과 초기 데이터 생성이 fresh DB와 restart에서 성공                                     | feature 작업 전 migration 수정              |
| Auth                | login, refresh, logout, auth/me, dashboard session, RBAC, default ADMIN 테스트 통과           | dashboard/extension 통합 보류              |
| Analyze             | `inputs[]` schema, detector, scoring, masking, basic idempotency, event metadata 테스트 통과  | dashboard events/extension smoke 완료 불가 |
| Filter Rule         | unified `filter_rules`, dry-run, editable\_fields, regex validation 테스트 통과               | filter UI 완료 불가                        |
| Dashboard           | overview/events/event-detail/users/filters/status가 API-backed metadata UI로 동작            | dashboard 완료 표시 금지                     |
| Extension           | selector, click/Enter hook, 예외 처리, Allow/Warn/Mask/Block, 401 refresh, real API smoke 통과 | 실제 AI 서비스 smoke 재검증                    |
| Basic privacy smoke | 입력 본문/파일 내용/전체 `masked_prompt`/dry-run sample이 저장·표시되지 않음                                | MVP 수용 보류                              |
| Build/Smoke         | API/dashboard/extension build/test, Docker smoke, 최종 smoke 시나리오 통과                       | MVP 완료 표시 금지                           |
| Docs                | README/install/admin/privacy/release 문서가 이 문서의 계약과 일치                                    | 문서 수정                                  |

### 15.4 테스트 명령 매트릭스

| 영역                        | 명령                                                        | 완료 기준                                                                       |
| ------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------- |
| API unit/integration      | `cd apps/api && pytest`                                   | auth/RBAC/analyze/filter/status/error tests 통과                              |
| API privacy smoke         | `cd apps/api && pytest tests/privacy` 또는 대응 smoke         | 입력 본문/파일 내용/전체 `masked_prompt`/dry-run sample 기본 미저장 확인                     |
| Dashboard typecheck/build | `cd apps/dashboard && npm run typecheck`, `npm run build` | TypeScript source typecheck/build 통과                                        |
| Dashboard smoke           | build output 또는 로컬 정적 파일 실행 smoke                         | login/overview/events/event-detail/users/filters/status가 metadata-only로 렌더링 |
| Extension checks          | `python apps/extension/tests/run_extension_checks.py all` | selector, hook, action UX, auth refresh, API client fixture 통과              |
| Docker smoke              | `docker compose up --build` 후 health check                | `/livez`, `/readyz`, `/healthz`, login/analyze/dashboard smoke 통과           |
| MVP 수용 게이트                | 각 영역 build/test + basic privacy smoke + 최종 smoke          | MVP 수용 가능                                                                   |

테스트 명령은 repo의 실제 script와 CI 구조에 맞게 고정한다. 명령이 아직 없으면 해당 테스트 runner를 만들거나, MVP 수용 게이트에서 수동 smoke로 명시한다.

### 15.5 최종 smoke 시나리오

1. `docker compose up --build`로 API와 PostgreSQL을 시작한다.
2. `GET /livez`가 `200`을 반환한다.
3. `GET /readyz`가 DB 연결, migration 최신, 기본 Filter Rule 준비 상태로 `200`을 반환한다.
4. 기본 ADMIN `admin / 1234`가 존재하고 password가 hash-only인지 확인한다.
5. `login.html`에서 ADMIN으로 로그인한다.
6. `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html` 화면이 ADMIN session으로 열린다.
7. ADMIN이 `POST /dashboard/users`로 일반 USER를 만든다.
8. USER는 extension auth/config/analyze를 사용할 수 있지만 dashboard에는 접근할 수 없다.
9. Extension options에서 PromptGuard API URL을 저장하고 `GET /auth/me`, `GET /config/extension`을 확인한다.
10. 지원 대상 AI 서비스 composer에 `NDA 위약금은 3억원입니다` 같은 Business Context fixture를 입력하고 Warn 또는 Mask를 확인한다.
11. 작은 text file fixture를 첨부하고 분석 결과가 event metadata로 남는지 확인한다.
12. Event Detail에서 Business Context configured matched keyword count가 표시되고 입력 본문이 표시되지 않는지 확인한다.
13. dummy secret fixture를 입력하고 Mask 또는 Block, 원본 submit 미발생을 확인한다.
14. Filter Rule Management에서 dry-run이 동작하고 sample text가 저장되지 않는지 확인한다.
15. Status 화면이 API/PostgreSQL/Migration/Filter Rules/Last Checked를 표시한다.
16. basic privacy smoke를 실행한다.

## 16. MVP 이후 제품 기능 범위

이 단원은 MVP 구현 계약에서 제외한 제품 기능을 정의한다. 운영 전 보안·운영 보강 항목은 21장을 따른다.

제품 기능 후속 범위:

- 사용자 hard delete 또는 사용자 데이터 익명화.
- 표시정보 수정 전용 사용자 관리 UI/API.
- 여러 종류의 탐지/제약이 동시에 걸린 경우의 고급 정책 조합.
- 사용자별 conflict resolution.
- 복합 remediation UX.
- SaaS 멀티테넌트 운영.
- 결제 기능.
- 엔터프라이즈 조직 관리.
- SSO 연동.
- SIEM 연동.
- 고급 필터 설정 workflow.

## 17. MVP 이후 서버·인프라·운영 범위

이 단원은 MVP 이후 서버 실행, 배포, 운영 편의 기능의 확장 범위를 정의한다.

서버·인프라 후속 범위:

- Redis 기반 다중 서버 요청 한도 상태 저장소, 분산 잠금, 큐, 캐시 사용.
- 운영 배포 profile 분리.
- reverse proxy 운영 예시 고도화.
- HTTPS, 도메인, TLS 인증서 종료 배포 문서 고도화.
- 운영 로그 보존 정책과 로그 수집 파이프라인.
- runtime metadata 표시 확장.
- 배포 artifact와 확장앱 package release 자동화.

## 18. MVP 이후 API·데이터·Analyze 범위

이 단원은 MVP 이후 API 계약, 데이터 모델, Analyze 처리의 확장 범위를 정의한다.

API·데이터·Analyze 후속 범위:

- HMAC 기반 `input_bundle_hash` 또는 request fingerprint.
- Filter Rule 변경 이력과 과거 rule set 재현성.
- `filter_rule_versions` 테이블.
- `login_id` 변경 기능을 추가하는 경우 stable `user_id` 도입.
- 사용자 관련 FK, event 참조, 사용자 관리 API path parameter의 `user_id` 전환.
- Analyze schema의 고급 확장.
- HMAC 기반 중복 요청 충돌 감지.

HMAC fingerprint 세부 기준:

- 입력 본문을 저장하지 않고도 중복 요청 충돌을 감지하기 위해 HMAC-SHA-256 기반 `input_bundle_hash` 또는 request fingerprint를 도입한다.
- HMAC secret은 `PROMPTGUARD_HMAC_SECRET`에서 읽는다. 운영 환경에서는 충분히 긴 무작위 값을 사용하고, `.env.example`에는 dummy placeholder만 둔다.
- canonical payload는 UTF-8 JSON bytes로 만든다. JSON 직렬화는 key 정렬, 공백 없는 separators, 고정 schema version을 사용한다.
- `input_bundle_hash`는 `inputs[]`의 순서, `kind`, `source`, `size_bytes`, `content_included`, 포함된 text 본문, attachment metadata, `content_unavailable_reason`, `limit_exceeded`를 canonical JSON으로 정규화해 HMAC-SHA-256으로 계산한 값이다.
- `request_fingerprint`는 `input_bundle_hash`, `filter_config_revision`, `context.ai_service`, `context.ai_service_domain`, `context.page_url_origin`, `context.extension_version`, `context.browser`, `context.locale`을 canonical JSON으로 정규화해 HMAC-SHA-256으로 계산한 값이다.
- `client_request_id`는 fingerprint 계산 payload에는 넣지 않고 idempotency key로만 사용한다.
- canonical payload와 입력 본문은 저장하지 않는다. 저장 대상은 HMAC 결과값과 필요한 metadata뿐이다.

## 19. MVP 이후 탐지·Filter Rule·파일 분석 범위

이 단원은 MVP 이후 탐지, Filter Rule, 파일 분석 기능의 확장 범위를 정의한다.

탐지·Filter Rule 후속 범위:

- advanced scoring weights 편집.
- Business Context rule 고도화.
- 한국 현지화 rule pack 고도화.
- 낮은 confidence와 ambiguous 후보의 고급 처리.
- 여러 rule이 동시에 충돌하는 경우의 고급 conflict resolution.
- Custom regex ReDoS regression.
- PDF parsing.
- Office document parsing.
- OCR.
- archive extraction.
- binary analysis.
- malware scanning.
- image content scan.
- pixel inspection.
- base64 payload scan.
- 브라우저 네트워크 요청 감청 기반 검사.

## 20. MVP 이후 확장앱·대시보드 범위

이 단원은 MVP 이후 Chrome Extension과 dashboard UI의 확장 범위를 정의한다.

확장앱 후속 범위:

- selector update E2E 강화.
- AI 서비스별 attachment 처리 고도화.
- 복합 remediation UX.
- 고급 extension status UI.

대시보드 후속 범위:

- dashboard-wide 공통 필터.
- date range picker.
- 고급 drill-down filter.
- 사용자별 이벤트 상세 drill-down.
- 고급 차트. 예: stacked bar, detection heatmap, 30일 summary p95.
- Filter Rule 변경 이력 UI.
- 과거 rule set 재현성 UI.

## 21. MVP 이후 보안·개인정보·재현성 보강 범위

이 단원은 MVP 이후 운영 전에 보강할 보안, 개인정보, 재현성 항목을 정의한다.

보안·개인정보·재현성 보강 범위:

- refresh reuse detection.
- `refresh_token_families` 테이블과 `refresh_tokens.family_id` 참조 추가.
- refresh token 재사용 탐지 시 token family 폐기와 재로그인 요구.
- full privacy/security regression.
- DB schema scan.
- log scan.
- error scan.
- dashboard DOM/API scan.
- exact string, JSON-escaped string, URL-encoded string, base64-like 변형 검사.
- fixture matrix 기반 regression.
- endpoint별 요청 한도 정책 정의와 적용.
- dashboard security headers 적용.
- `Content-Security-Policy`.
- `X-Content-Type-Options: nosniff`.
- `Referrer-Policy`.
- `frame-ancestors` 또는 동등한 frame 제한.

운영 전 보강 환경변수:

| 변수                              | 사용 시점                                                   | 설명                                                          |
| ------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------- |
| `PROMPTGUARD_HMAC_SECRET`       | HMAC 기반 `input_bundle_hash` 또는 request fingerprint 도입 시 | 충분히 긴 무작위 서버 secret. `.env.example`에는 dummy placeholder만 둔다 |
| `RATE_LIMIT_LOGIN_PER_MINUTE`   | endpoint별 요청 한도 정책 도입 시                                 | login endpoint의 분당 요청 한도                                    |
| `RATE_LIMIT_ANALYZE_PER_MINUTE` | endpoint별 요청 한도 정책 도입 시                                 | analyze endpoint의 분당 요청 한도                                  |

## 22. MVP 이후 범위 검증 기준

이 단원은 16\~21장의 MVP 이후 범위를 구현할 때 적용할 검증 기준을 정의한다. 이 기준은 기능 시연 MVP 수용 기준이 아니라, 해당 후속 범위를 실제로 구현하는 시점의 완료 기준이다.

### 22.1 제품 기능 검증 기준

사용자 hard delete 또는 익명화:

- 사용자 비활성화와 hard delete/익명화 동작이 명확히 구분되어야 한다.
- 이벤트 metadata, audit log, 사용자 통계에서 삭제 또는 익명화된 사용자가 어떻게 표시되는지 정의되어야 한다.
- 마지막 `ACTIVE` ADMIN 보호 규칙이 hard delete/익명화에서도 유지되어야 한다.

사용자 표시정보 수정:

- 표시정보 수정 API는 role/status 변경 API와 분리되어야 한다.
- `login_id` 변경 기능이 포함되는 경우 stable `user_id` 도입 기준을 따라야 한다.
- 수정 전후 audit metadata가 남아야 한다.

고급 dashboard 기능:

- date range picker, 공통 필터, drill-down, 고급 차트는 API pagination과 집계 성능 기준을 함께 검증한다.
- 필터 조건이 이벤트 목록, 이벤트 상세, overview aggregate에서 서로 다르게 적용되지 않아야 한다.
- 사용자별 이벤트 상세 drill-down은 USER에게 노출되지 않아야 한다.

### 22.2 서버·인프라·운영 검증 기준

Redis 기반 기능:

- Redis가 꺼진 기본 실행과 Redis profile 실행이 모두 검증되어야 한다.
- Redis를 사용하는 요청 한도 상태 저장소, 분산 잠금, 큐, 캐시는 PostgreSQL 기준 영속 데이터와 충돌하지 않아야 한다.
- Redis 장애 시 필수 API가 어떤 상태 코드와 오류를 반환하는지 정의되어야 한다.

운영 배포:

- reverse proxy 예시는 HTTPS, domain, TLS 종료, 업로드 크기 제한, 보안 header 전달 기준을 포함해야 한다.
- Docker Compose와 운영 profile의 환경변수 이름이 문서와 일치해야 한다.
- release artifact와 확장앱 package는 버전과 build 식별자를 확인할 수 있어야 한다.

운영 로그:

- 로그 보존 정책은 입력 본문, 파일 내용, 전체 `masked_prompt`, secret 값을 저장하지 않는 기준을 유지해야 한다.
- access log와 application log의 field set을 문서화한다.

### 22.3 API·데이터·Analyze 검증 기준

HMAC 기반 fingerprint:

- `input_bundle_hash`는 같은 canonical input bundle에서 같은 값을 내야 한다.
- `request_fingerprint`는 같은 input bundle과 같은 request metadata에서 같은 값을 내야 한다.
- `client_request_id`가 달라도 input bundle과 request metadata가 같으면 fingerprint는 같아야 한다.
- `client_request_id`는 fingerprint payload에 포함되지 않아야 한다.
- canonical payload와 입력 본문은 DB, logs, dashboard API에 저장되지 않아야 한다.
- `PROMPTGUARD_HMAC_SECRET`이 바뀌면 같은 입력의 HMAC 결과가 달라지는 것을 문서화해야 한다.

Filter Rule 변경 이력과 재현성:

- `filter_rule_versions` 또는 동등한 변경 이력 저장소가 있어야 한다.
- Filter Rule 생성, 수정, 비활성화, archive가 변경 이력에 기록되어야 한다.
- 과거 event가 어떤 rule 상태에서 생성됐는지 재현 가능한 metadata가 남아야 한다.
- 이벤트 상세 UI는 내부 version/hash 식별자를 사용자에게 표시하지 않아야 한다.

`login_id` 변경 기능:

- stable `user_id`가 도입되어야 한다.
- 사용자 관련 FK, event 참조, 사용자 관리 API path parameter가 `user_id` 기준으로 전환되어야 한다.
- `login_id`는 변경 가능한 로그인 credential로만 사용되어야 한다.
- 기존 이벤트와 통계가 변경 전후 사용자를 잘못 합치거나 분리하지 않아야 한다.

### 22.4 탐지·Filter Rule·파일 분석 검증 기준

Advanced scoring weights:

- 기본 sensitivity `low/medium/high`와 advanced weight 편집 결과가 충돌하지 않아야 한다.
- scoring config 변경 전후의 dry-run 결과가 설명 가능해야 한다.
- 잘못된 scoring config는 저장 전에 거부되어야 한다.

Business Context 고도화:

- positive/negative corpus를 기준으로 FP/FN을 측정한다.
- 낮은 confidence와 ambiguous 후보는 강한 차단으로 바로 이어지지 않아야 한다.
- context rule evidence는 입력 본문 span 대신 configured keyword count와 evidence count로 저장되어야 한다.

Custom regex ReDoS regression:

- 위험 regex fixture가 저장 단계에서 거부되어야 한다.
- regex 실행 timeout 또는 safe-regex 전략이 적용되어야 한다.
- ReDoS fixture가 API latency와 worker 안정성을 깨뜨리지 않아야 한다.

파일 분석 확장:

- PDF, Office, OCR, archive, binary, image content scan은 각각 별도 parser와 크기 제한을 가져야 한다.
- parser 실패 시 입력 본문이나 파일 내용이 error detail/log에 남지 않아야 한다.
- archive extraction은 압축 폭탄, 중첩 archive, 총 해제 크기 제한을 검증해야 한다.
- 이미지/OCR 처리는 원본 이미지 bytes와 OCR text 저장 기준을 별도로 정의해야 한다.

### 22.5 확장앱·대시보드 검증 기준

확장앱 확장 기능:

- selector update E2E는 remote selector override, fallback selector, DOM 변경 smoke를 포함해야 한다.
- AI 서비스별 attachment 처리 고도화는 raw `File` 접근 가능 여부와 attachment chip metadata 처리 기준을 검증해야 한다.
- 복합 remediation UX는 top-level `action`을 임의로 재계산하지 않아야 한다.

대시보드 확장 기능:

- dashboard-wide filter와 date range picker는 모든 관련 API의 query parameter와 집계 기준을 일치시켜야 한다.
- 고급 차트는 대량 이벤트 데이터에서 응답 시간과 렌더링 성능을 검증해야 한다.
- Filter Rule 변경 이력 UI는 변경 이력을 보여주되 입력 본문, 탐지값 원문, 내부 secret을 노출하지 않아야 한다.
- 과거 rule set 재현성 UI를 만들더라도 event detail 기본 화면에는 내부 식별자를 표시하지 않아야 한다.

### 22.6 보안·개인정보·재현성 보강 검증 기준

Refresh reuse detection:

- refresh token 재사용이 감지되면 해당 token family가 폐기되어야 한다.
- 폐기된 token family로 refresh를 재시도하면 실패해야 한다.
- 사용자에게는 재로그인이 필요한 안전한 오류만 표시해야 한다.
- refresh token 원문은 DB와 logs에 저장되지 않아야 한다.

Full privacy/security regression:

- DB schema scan, log scan, error scan, dashboard DOM/API scan을 자동화한다.
- exact string, JSON-escaped string, URL-encoded string, base64-like 변형을 함께 검사한다.
- fixture matrix 기반 regression은 release gate로 실행한다.
- 실패 시 해당 후속 범위는 완료로 보지 않는다.

Endpoint별 요청 한도 정책:

- login, refresh, analyze, dashboard 상태 변경 endpoint별 한도를 따로 정의한다.
- 제한 기준 식별자는 endpoint 성격에 맞게 정한다. 예: IP, `login_id`, token subject.
- 연속 실패 횟수와 제한 해제 조건을 정의한다.
- 요청 한도 초과 응답은 입력 본문이나 secret 값을 포함하지 않아야 한다.

Dashboard security headers:

- dashboard 정적 파일 응답에 `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `frame-ancestors` 또는 동등한 frame 제한을 적용한다.
- header 적용 후 login, overview, events, users, filters, status 화면이 정상 동작해야 한다.

## 23. MVP/WBS 작업 정리

### 23.1 MVP WBS + 산출물 + 배분

| 기존 WBS | 담당 | 분류 | 영역 | 구현 단위 | 산출물 | 현재 상태 | 필요한 조치 | 완료 기준 | 근거/비고 |
|---|---|---|---|---|---|---|---|---|---|
| 59 Users 관리 화면 구현 | 김현성 | MVP 대시보드 | Users 화면 | mock 데이터를 제거하고 `/dashboard/users` 목록·생성·role/status API를 연결한다. | `users.html`, Users TypeScript, `/dashboard/users` API client 연동 | 부분 | 수정 | 사용자 목록, 사용자 생성, role 변경, status 변경, 비활성화가 실제 API로 동작한다. `/admin/users` 기준 연동은 남기지 않는다. | 현재 main에는 `users.html` 파일이 있지만, 실제 사용자 목록 table, 사용자 생성 form, role/status 변경 UI는 아직 붙어 있지 않다. 화면에는 "사용자 관리 상세 기능은 다음 단계에서 연결합니다" 수준의 안내만 있다. 서버에는 `/dashboard/users` API가 일부 구현되어 있으므로 화면을 완전히 새로 만드는 단계는 아니지만, 아직 그 API를 화면에서 호출해 렌더링하지 않는다. 다음 작업은 `users.html`/Users TypeScript를 `/dashboard/users` 목록·생성·role/status API에 연결하고, dashboard session+CSRF가 붙은 뒤 동작을 검증하는 것이다. |
| 80 사용자별 이벤트 통계 API 구현 | 김현성 | MVP API·데이터·Analyze | Users 통계 API | 기본 통계 기간 내 사용자별 event/action aggregate를 `/dashboard/users` 응답에 포함한다. | `/dashboard/users` response row의 `event_count`, `blocked_count`, `masked_count`, `warned_count`, `last_event_at` | 완료 | 완료 | Users 화면의 사용자별 이벤트 표가 별도 mock 없이 `/dashboard/users` 응답만으로 렌더링된다. 기존 `/stats/users`, `user_id/display_name` 기준은 `/dashboard/users`, `login_id/username` 기준으로 교체한다. | `/dashboard/users` route가 최근 30일 `analysis_events` 기준으로 사용자별 `event_count`, `blocked_count`, `masked_count`, `warned_count`, `last_event_at`를 계산해 반환한다. 테스트는 mixed action aggregate, 기간 밖 이벤트 제외, zero-event safe metadata, password/hash/token/session-free 응답을 검증한다. Users 화면 API 연동은 WBS 59/PR10 범위로 남아 있다. |
| 61 서버 상태 대시보드 구현 | 유지수 | MVP 대시보드 | Status 화면 | `status.html`을 `/dashboard/status`와 연결하고 typecheck/build를 통과시킨 뒤 변경분을 커밋·푸시·PR 생성한다. | `status.html`, Status TypeScript, `/dashboard/status` API client 연동, PR | 교체 필요 | 교체 | API/PostgreSQL/Migration/Filter Rules/Last Checked가 표시된다. DB URL, secret, token, stack trace, 필터 설정 상세값, 환경변수 상세값은 표시하지 않는다. | 현재 dashboard 폴더에는 `status.html`이 없다. 서버에는 `/status/server`가 있지만, 이것은 MVP 계약의 dashboard status API가 아니다. MVP는 ADMIN dashboard에서 `GET /dashboard/status`를 호출해 `api_status`, `postgres_status`, `migration_status`, `filter_rules_status`, `last_checked`를 표시해야 한다. 다음 작업은 `status.html`을 추가하고 `/status/server`가 아니라 `/dashboard/status` flat response를 사용하는 화면과 API를 구현하는 것이다. |
| 74, 76, 77 Dashboard prototype/static pages | 김현성 | MVP 대시보드 | Login 화면 | `login.html`을 dashboard session API와 연결한다. | `login.html`, Login TypeScript, `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/me` API client 연동 | 교체 필요 | 교체 | ADMIN credential로 로그인하면 `overview.html`로 이동한다. USER credential은 dashboard session을 만들지 못한다. session 만료 시 login 화면으로 이동한다. | 현재 로그인 화면 역할은 `index.html`이 하고 있고, `src/login.ts`는 실제 API 호출 없이 `admin / 1234` 값을 직접 비교하는 mock login이다. 성공하면 계약상 `overview.html`이 아니라 `admin.html`로 이동한다. 즉 로그인 UI shell은 있지만 MVP의 dashboard session login은 구현되지 않았다. 다음 작업은 `index.html`을 계약 entry인 `login.html`로 교체하거나 이동하고, mock 검증을 `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/me` 호출로 바꾸는 것이다. |
| 74, 76, 77 Dashboard prototype/static pages | 김영은 | MVP 대시보드 | Overview 화면 | `overview.html`을 `/dashboard/overview`와 연결한다. | `overview.html`, Overview TypeScript, `/dashboard/overview` API client 연동 | 교체 필요 | 교체 | Total Events, Blocked, Masked, Warned, Active Users 카드와 action/period 차트가 실제 API 값으로 렌더링된다. | 현재 Overview 역할은 `admin.html`이 하고 있다. 카드, 통계, 차트처럼 보이는 UI는 있지만 값이 정적 mock이고 `src/admin.ts`가 비어 있어 `/dashboard/overview` API 값을 렌더링하지 않는다. 즉 화면 모양만 있고 MVP 데이터 연동은 없다. 다음 작업은 `admin.html`을 계약 entry인 `overview.html`로 교체하거나 이동하고, Total Events, Blocked, Masked, Warned, Active Users, action/period chart를 `/dashboard/overview` API 응답으로 렌더링하는 것이다. |
| 78, 79 Dashboard Events metadata MVP | 김영은 | MVP 대시보드 | Events 목록 화면 | `events.html`을 `/dashboard/events`와 연결한다. | `events.html`, Events TypeScript, `/dashboard/events` API client 연동 | 교체 필요 | 교체 | 이벤트 목록에 시간, 사용자, 서비스, action, risk, 대표 탐지 category/type, 탐지 수, 입력 수, content unavailable 수, 상세보기 링크가 표시된다. | 현재 `events.html` 파일은 있지만 정적 mock 이벤트를 보여준다. `src/events.ts`가 비어 있어 API 호출 기반 목록 렌더링이 아니다. 서버에도 event route는 있으나 path가 `/events`이고, MVP 계약은 `/dashboard/events`다. 다음 작업은 화면의 mock 데이터를 제거하고 `/dashboard/events` API를 호출해 시간, 사용자, 서비스, action, 위험도, 대표 탐지 category/type, 탐지 수, 입력 수, content unavailable 수, 상세보기 링크를 렌더링하는 것이다. |
| 78, 79 Dashboard Events metadata MVP | 김영은 | MVP 대시보드 | Event Detail 화면 | `event-detail.html?event_id=...`에서 `GET /dashboard/events/{event_id}`를 호출해 상세 metadata를 렌더링한다. | `event-detail.html`, Event Detail TypeScript, `/dashboard/events/{event_id}` API client 연동 | 교체 필요 | 교체 | detection summary, detections, input results, content unavailable inputs, Business Context metadata가 표시된다. 입력 본문, 파일 내용, 전체 `masked_prompt`, 원본 파일명, 내부 식별자는 표시하지 않는다. | 현재 `event-detail.html`은 `risk` query로 정적 row를 접고 펼치는 게시판형 mock 화면이다. `event_id`를 읽어 `GET /dashboard/events/{event_id}`를 호출하지 않는다. 화면과 현재 event API에는 `prompt_hash_prefix` 또는 "프롬프트 해시"가 보이는데, 개발문서상 이벤트 상세 UI/API에서는 이런 내부 식별자를 표시하거나 반환하면 안 된다. 다음 작업은 정적 상세 데이터를 제거하고, `event-detail.html?event_id=...`에서 `/dashboard/events/{event_id}`를 호출해 detection summary, detections, input results, content unavailable inputs, Business Context metadata만 metadata-only로 표시하는 것이다. |
| 87 Filter Rule 관리 화면 구현 | 유지수 | MVP 대시보드 | Filter Rule Management 화면 | `filters.html`을 `/dashboard/filters*` API와 연결한다. | `filters.html`, Filters TypeScript, Filter Rule list/form/dry-run UI | 완료 | 없음 | built-in/custom/context rule 목록, 생성·수정, enable/disable, dry-run이 동작한다. built-in detector는 허용 필드만 수정된다. | `filters.html`과 `src/filters.ts`는 `/dashboard/filters`, 상세 조회, 생성, 수정, enable/disable, delete, dry-run API를 사용한다. 대시보드 경로는 ADMIN session cookie + CSRF mutation 경계로 동작하고, built-in detector는 허용 필드만 수정 가능하다. Filter Rule 변경 이력은 MVP 이후 범위로 두고 현재 화면 경로에서는 생성·수정·enable/disable·archive side effect를 만들지 않는다. |
| 74, 76, 77 Dashboard prototype/static pages | 김현성 | MVP 대시보드 | Dashboard 공통 API client | dashboard 화면들이 ADMIN session, CSRF, safe error banner, loading/empty state를 공통 방식으로 처리한다. | dashboard shared API client, session helper, CSRF helper, error rendering helper | 부분 | 수정 | `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`에서 공통 client가 재사용된다. session id는 `localStorage`에 저장하지 않는다. | 현재 dashboard TypeScript 파일은 화면별로 존재하지만 공통 dashboard API client가 완성됐다고 보기는 어렵다. `filters.ts`는 자체 `apiRequest()`로 API를 호출하지만, login은 mock이고 admin/events/users TypeScript는 비어 있다. MVP에서는 모든 dashboard 화면이 ADMIN session cookie, CSRF, 공통 오류 처리, loading/empty 상태 처리를 같은 방식으로 써야 한다. 다음 작업은 session helper, CSRF helper, safe error renderer, loading/empty state 처리를 공통 모듈로 만들고 각 화면에서 재사용하는 것이다. |
|  | 김현성 | MVP 확장앱 | Options auth/config | Extension options에서 PromptGuard API URL 저장, login/logout, `/auth/me`, `/config/extension` 확인을 구현한다. | options UI, service worker auth client, config cache, auth status UI | 부분 | 수정 | PromptGuard API URL 저장 후 인증 상태와 원격 확장앱 설정을 확인할 수 있다. MV3 service worker inactive 상태를 인증 만료로 표시하지 않는다. | README와 extension 구조상 PromptGuard API URL 저장, auth/config 확인 흐름은 어느 정도 구현된 것으로 보인다. 하지만 서버의 최종 `/config/extension` 계약과 `/prompts/analyze`의 `inputs[]` 계약이 아직 완성되지 않았기 때문에 options/config 흐름도 최종 계약 기준으로 완료됐다고 볼 수 없다. 다음 작업은 options page가 실제 `/auth/me`, `/config/extension` 응답을 사용하고, token 만료·refresh 실패·MV3 inactive 상태를 계약대로 구분하는지 end-to-end로 확인하는 것이다. |
| 95 DOM selector rerender regression | 김현성 | MVP 확장앱 | Content script selector/hook | 지원 대상 AI 서비스 화면에서 composer, send button, attachment chip 후보를 감지하고 click/Enter 전송을 분석 완료 전 보류한다. | content script selector, send interceptor, replay guard, selector tests | 부분 | 수정 | `@` mention, IME composition, Shift+Enter, picker 동작을 전송으로 오판하지 않는다. protected replay는 1회만 수행한다. | extension README 기준으로 send button click, Enter 전송, Shift+Enter, IME composition, text file input/drop preflight 같은 DOM hook은 구현된 상태로 보인다. 즉 브라우저에서 전송을 가로채는 기본 동작은 어느 정도 있다. 아직 완료가 아닌 이유는 서버 Analyze API가 아직 `inputs[]` 계약이 아니어서, content script가 수집한 입력을 최종 Analyze Input Bundle로 보내는 전체 흐름이 검증되지 않았기 때문이다. 다음 작업은 실제 서버 `/prompts/analyze` `inputs[]` 계약과 연결해 real API smoke를 수행하는 것이다. |
|  | 김현성 | MVP 확장앱 | Analyze request builder | composer text, converted paste, 작은 text file, attachment metadata, unsupported attachment를 8.1의 `inputs[]` 계약으로 request body에 담는다. | request builder, input normalization, input limit preflight, API client tests | 교체 필요 | 교체 | top-level `prompt`, `input`, `file`, `attachments` 없이 `inputs[]` 하나로 `/prompts/analyze`를 호출한다. 한도 초과 본문은 포함하지 않고 content unavailable metadata로 보낸다. | 현재 서버 `/prompts/analyze`가 `inputs[]`가 아니라 단일 `prompt` 중심 request를 받는다. 따라서 extension request builder도 MVP의 최종 입력 묶음 계약과 end-to-end로 맞을 수 없다. 다음 작업은 서버와 extension을 함께 바꿔 composer text, converted paste, file text, attachment metadata, unsupported attachment를 모두 `inputs[]` 하나에 담도록 하는 것이다. |
|  | 김현성 | MVP 확장앱 | File/attachment capture | raw `File` 객체를 확보한 작은 text file은 읽어서 분석 요청에 포함하고, 그 외 첨부는 metadata-only 또는 `unsupported_attachment`로 표현한다. | file input/drop/paste handler, MIME/extension check, attachment chip metadata capture | 부분 | 수정 | 허용 text file은 `kind: "text"`, `source: "file"`, `content_included: true`로 전송된다. PDF/Office/OCR/archive/binary/image scan은 수행하지 않는다. | extension 쪽에서는 text file input/drop preflight와 메모리 기반 파일 읽기 흐름이 있는 것으로 보인다. 하지만 서버가 아직 `source: "file"` text input, attachment metadata, unsupported attachment, content unavailable metadata를 `inputs[]`로 받지 않는다. 즉 클라이언트 쪽 수집 일부는 됐지만 서버 계약과 연결되지 않았다. 다음 작업은 파일/첨부 입력을 `inputs[]` item으로 보내고, 서버가 `content_scanned`, `content_unavailable_reason`, `limit_exceeded`를 기록하도록 연결하는 것이다. |
|  | 김현성 | MVP 확장앱 | Action UX | 서버 응답의 top-level `action`, `allow_original_send`, `requires_user_confirmation`, `masked_prompt`를 기준으로 Allow/Warn/Mask/Block UX를 적용한다. | action panel, warning/confirmation UI, mask apply logic, block UI, UX tests | 부분 | 수정 | Allow는 원래 전송을 1회 재실행하고, Warn은 사용자 확인 후 전송하며, Mask는 composer text를 `masked_prompt`로 교체한 뒤 전송하고, Block은 원문 전송을 발생시키지 않는다. | extension README 기준으로 Mask replace, Block, timeout, malformed response, API error fail-closed 같은 UX는 구현되어 있다. 다만 서버 response가 아직 MVP 계약의 `allow_original_send`, `requires_user_confirmation`, `input_results[]`, `content_unavailable_inputs[]` 구조가 아니라 구형 Analyze 응답이다. 다음 작업은 최종 서버 응답 계약에 맞춰 Allow/Warn/Mask/Block UX를 다시 검증하고, extension이 detection 배열로 action을 재계산하지 않는지 확인하는 것이다. |
|  | 김현성 | MVP 확장앱 | Extension storage/privacy | 확장앱 저장소에는 API URL, token, config cache, sync time, selector metadata만 장기 저장하고 입력 본문 계열 값은 저장하지 않는다. | extension storage adapter, cleanup path, privacy tests | 부분 | 수정 | composer 원문, paste 원문, file text 원문, 전체 `masked_prompt`, 탐지값 원문, 원본 파일명, full request/response body가 장기 저장되지 않는다. | README에는 raw prompt, file content, extracted text, detected raw values, original filenames, full masked prompts를 저장하거나 로그로 남기지 않는다고 되어 있다. 이 방향은 MVP 개인정보 기준과 맞다. 아직 완료가 아닌 이유는 실제 extension storage, DB, dashboard API/DOM, error response를 대상으로 금지값이 남지 않는지 자동 smoke가 확인되지 않았기 때문이다. 다음 작업은 basic privacy smoke를 만들어 저장소와 화면, 오류 응답을 검사하는 것이다. |
| 47 로그인·refresh·auth/me API 구현 | 유지수 | MVP 인증·세션·권한 | Auth API | 확장앱 bearer token 흐름을 `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me` 기준으로 구현한다. | FastAPI auth routes, token hash 저장, refresh rotation, auth tests | 부분 | 수정 | access token/refresh token 흐름이 동작하고, refresh token 원문은 저장하지 않는다. `DISABLED` 사용자는 차단된다. | 현재 `/auth/login`, `/auth/me`, `/auth/refresh`, `/auth/logout`, `/auth/change-password`와 bearer token 기반 사용자 확인은 구현되어 있다. `DISABLED` 사용자 차단과 refresh token rotation도 일부 구현되어 있다. 즉 extension bearer-token 인증은 부분적으로 동작한다. 아직 MVP 인증 전체가 완료가 아닌 이유는 dashboard session이 없고, refresh idle timeout과 dashboard session hash 저장이 빠져 있으며, logout이 refresh token 소유자를 명확히 검증하는지 추가 확인이 필요하기 때문이다. 다음 작업은 extension token flow를 보강하고, 별도 Dashboard Session API를 구현하는 것이다. |
|  | 김현성 | MVP 인증·세션·권한 | Dashboard Session API | ADMIN dashboard session을 `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me` 기준으로 구현한다. | dashboard session routes, CSRF, HttpOnly cookie, session hash 저장 | 미구현 | 신규 | ADMIN만 session 생성 가능하고 USER는 403이다. session id는 `localStorage`에 저장하지 않는다. | 현재 main에는 dashboard session route나 `DashboardSession` model이 보이지 않는다. 대시보드 API도 extension bearer token의 ADMIN 확인 방식에 기대고 있다. MVP에서는 대시보드가 extension token을 쓰지 않고, `/dashboard/session/csrf`, `/dashboard/session/login`, `/dashboard/session/logout`, `/dashboard/session/me`, HttpOnly cookie, CSRF를 사용해야 한다. 다음 작업은 dashboard session 모델, session hash 저장, CSRF 발급/검증, login/logout/me route를 새로 구현하는 것이다. |
| 22 관리자 기반 사용자 생성 API 구현 / 23 사용자 role/status 변경 API 구현 | 김현성 | MVP API·데이터·Analyze | Users API | ADMIN 사용자 관리 API를 `/dashboard/users`, `POST /dashboard/users`, `PATCH /dashboard/users/{login_id}/role`, `PATCH /dashboard/users/{login_id}/status` 기준으로 구현한다. | users API routes, schemas, service, tests | 완료 | 완료 | `login_id` 기준 목록/생성/role/status 변경이 동작한다. email 필수 요구와 `/admin/users` path는 남기지 않는다. | `/dashboard/users` 목록/생성/role/status API는 dashboard session/CSRF boundary를 사용하고, 응답에서 password/hash/token/session을 반환하지 않는다. 사용자별 aggregate query와 마지막 ACTIVE ADMIN 보호 테스트가 추가되어 Users API completion 기준을 만족한다. Users 화면 연동은 WBS 59/PR10 범위로 남아 있다. |
| 25 Analyze API 요청 schema 검증 / 57 Analyze API 전체 흐름 통합 | 김현성 | MVP API·데이터·Analyze | Analyze API | `POST /prompts/analyze`를 `inputs[]` 기반 send attempt decision endpoint로 교체한다. | analyze request/response schemas, route, pipeline orchestration, tests | 교체 필요 | 교체 | top-level `prompt`, `input`, `file`, `attachments` 없이 `inputs[]`만 수용하고 top-level `action` 하나를 반환한다. | 현재 `/prompts/analyze`는 단일 `prompt` 문자열을 검사하는 구조다. MVP 계약은 사용자의 한 번의 전송 시도 전체를 `inputs[]`로 보내고, composer text, file text, converted paste, attachment metadata, unsupported attachment를 함께 판단하는 구조다. 다음 작업은 top-level `prompt` 중심 schema를 `inputs[]` schema로 교체하고, `input_results[]`, `content_unavailable_inputs[]`, `requires_user_confirmation`, 최종 action 근거 metadata를 반환하는 것이다. |
| 27 client_request_id 중복 요청 처리 | 김현성 | MVP API·데이터·Analyze | Analyze Idempotency | `(login_id, client_request_id)` 기준 중복 event 방지를 구현한다. | `idempotency_keys` 저장, idempotency service, duplicate request tests | 미구현 | 수정 | 같은 전송 시도의 중복 요청이 두 번째 event를 만들지 않는다. HMAC fingerprint는 구현하지 않는다. | 현재 `client_request_id`는 Analyze request field로만 존재하고, 같은 사용자의 같은 `client_request_id`가 중복 event를 만들지 않도록 막는 저장소나 service가 확인되지 않는다. MVP에서는 HMAC fingerprint가 아니라 `(login_id, client_request_id)` 기준 중복 event 방지가 필요하다. 다음 작업은 `idempotency_keys` 또는 동등한 테이블/service를 추가하고 duplicate request 테스트를 작성하는 것이다. |
|  | 김현성 | MVP API·데이터·Analyze | File/Text Input | 작은 text file scan과 attachment metadata/unsupported attachment 표현을 구현한다. | file text read path, MIME/extension allowlist, input limit handling, tests | 교체 필요 | 교체 | 허용 text file은 `kind: "text"`, `source: "file"`, `content_included: true`로 분석된다. 미지원 첨부는 metadata-only 또는 `unsupported_attachment`로 처리된다. | 서버 Analyze API가 아직 `inputs[]`를 받지 않기 때문에 작은 text file, converted paste, attachment metadata, unsupported attachment, oversized/content unavailable 입력을 서버에 표현할 수 없다. 다음 작업은 request schema, byte limit 처리, content unavailable 처리, input별 `content_scanned` 기록을 추가하는 것이다. |
| 6 analysis_events·event_detections 테이블 작성 / 7 원문 없는 이벤트 저장 서비스 구현 | 김현성 | MVP API·데이터·Analyze | Events API | 대시보드 이벤트 조회 API를 `/dashboard/events`, `/dashboard/events/{event_id}` 기준으로 구현한다. | events routes, list/detail schemas, event metadata queries, tests | 완료 | 없음 | 목록/상세는 metadata만 반환하고 내부 식별자와 입력 본문을 반환하지 않는다. | `/dashboard/events`와 `/dashboard/events/{event_id}`는 ADMIN dashboard session 기준으로 동작한다. 목록은 action/risk/대표 탐지/input count/content unavailable count를 반환하고, 상세는 detection summary, detections, input results, content unavailable inputs, Business Context metadata를 metadata-only로 반환한다. 응답은 입력 본문, 파일 내용, 전체 `masked_prompt`, 원본 파일명, prompt hash 계열, filter rule set version 같은 내부 식별자를 반환하지 않는다. |
| 10 Overview summary API 연결 | 김영은 | MVP API·데이터·Analyze | Overview API | Overview aggregate를 `/dashboard/overview` 기준으로 구현한다. | overview route, 30일 기본 aggregate, action/period counts, tests | 교체 필요 | 교체 | 카드와 action/period 차트에 필요한 metadata가 반환된다. 사용자별 aggregate는 `/dashboard/users`가 담당한다. | 현재 `/stats/users`, `/stats/events` 같은 통계 API는 있지만, MVP 계약의 Overview API는 `/dashboard/overview`다. 화면도 `admin.html` 정적 mock이라 실제 API 값을 쓰지 않는다. 다음 작업은 현재 stats 쪽에서 유효한 aggregate 로직만 가져와 `/dashboard/overview` 응답으로 정리하고, `overview.html`에서 그 값을 렌더링하는 것이다. |
| 8 Filter Rule dry-run API 구현 / 29 custom keyword·regex·context_rule 생성·수정 API 구현 / 30 통합 Filter Rule 목록·상세 API 구현 | 김현성 | MVP API·데이터·Analyze | Filter Rule API | 통합 Filter Rule API를 `/dashboard/filters*` 기준으로 구현한다. | filter routes, schemas, `origin/kind`, `editable_fields`, dry-run | 완료 | 없음 | built-in detector는 `enabled`, `severity`, `action`만 수정 가능하고, custom keyword/regex/context rule과 dry-run이 동작한다. | `/dashboard/filters` API는 목록, 상세, 생성, 수정, enable/disable, delete, dry-run을 제공한다. read는 ADMIN session 기준으로, mutation과 dry-run은 ADMIN session + CSRF 기준으로 동작한다. built-in rule은 허용된 필드만 수정 가능하고 regex/context rule 검증도 있다. Filter Rule 변경 이력은 MVP 이후 범위로 두며, 현재 `/dashboard/filters*` mutation 경로는 `FilterRuleVersion` side effect를 만들지 않는다. |
| 51 서버 health/readiness endpoint 구현 | 유지수 | MVP API·데이터·Analyze | Dashboard Status API | 서버 상태 조회 API를 `/dashboard/status` 기준으로 구현한다. | status route, required/optional status metadata, tests | 교체 필요 | 교체 | API/PostgreSQL/Migration/Filter Rules/Last Checked를 반환한다. secret, DB 연결 문자열, stack trace는 반환하지 않는다. | 현재 서버에는 `/status/server`가 있지만, MVP 대시보드 API인 `/dashboard/status`는 아니다. 응답도 nested 구조이고, MVP 계약의 flat `api_status`, `postgres_status`, `migration_status`, `filter_rules_status`, `last_checked`가 아니다. 다음 작업은 `/dashboard/status` route를 만들고, dashboard status 화면이 필요한 안전한 metadata만 flat response로 반환하는 것이다. |
| 6 analysis_events·event_detections 테이블 작성 | 유지수 | MVP PostgreSQL | Event schema | `analysis_events`, `event_inputs`, `event_detections` 중심의 event metadata schema를 MVP 계약에 맞게 정리한다. | SQLAlchemy models, Alembic migration, event metadata tests | 교체 필요 | 교체 | 이벤트 metadata가 저장되고 입력 본문, 파일 내용, 전체 `masked_prompt`, 탐지값 원문은 저장되지 않는다. | 현재 `analysis_events`와 `event_detections`는 있으나 `event_inputs`가 없다. 그래서 어느 입력 조각에서 어떤 탐지가 발생했는지 `input_id`, `input_index`, `kind`, `source`로 연결할 수 없다. 또한 `analysis_events`에는 `prompt_hash`, `prompt_hash_key_id`, `filter_rule_set_version` 같은 내부 식별자 중심 필드가 남아 있다. 다음 작업은 `event_inputs`를 추가하고, event/detection schema를 `inputs[]` 기반 metadata-only 구조로 바꾸는 것이다. |
| 45 users·refresh_tokens 테이블 작성 | 유지수 | MVP PostgreSQL | Auth/User schema | `users`, `refresh_tokens`, `dashboard_sessions` schema를 MVP 인증 계약에 맞게 정리한다. | SQLAlchemy models, Alembic migration, default ADMIN seed | 부분 | 수정 | `login_id`, `username`, `department`, role/status, password_hash, refresh token hash, dashboard session hash가 저장된다. | 현재 `users`에는 `login_id`, `username`, `department`, role/status, password hash metadata가 있고 `refresh_tokens`도 있다. 그래서 로컬 계정과 extension token 기반 인증의 기본 DB 구조는 일부 있다. 아직 MVP 완료가 아닌 이유는 user status에 `PENDING` 같은 MVP 외 상태가 남아 있고, invite/registration 모델 같은 가입 흐름이 남아 있으며, dashboard session table/model이 없기 때문이다. 다음 작업은 MVP 기준 `ACTIVE/DISABLED` 계정 모델, refresh token hash metadata, dashboard session hash 저장 구조를 정리하는 것이다. |
| 48 DB migration 실행 골격 작성 | 유지수 | MVP PostgreSQL | Migration 실행 | fresh DB와 restart에서 Alembic migration과 초기 데이터 생성이 안정적으로 실행되게 한다. | Alembic env, migration runner, seed path, Docker smoke | 부분 | 수정 | fresh DB에서 migration 후 기본 ADMIN과 MVP tables가 준비된다. | Alembic migration은 존재하고 users, refresh_tokens, analysis_events, filter_rules 같은 일부 MVP 테이블을 만든다. 하지만 dashboard_sessions, event_inputs, idempotency_keys 등 핵심 MVP 테이블이 아직 없고, fresh DB에서 기본 ADMIN seed와 restart idempotency가 자동 smoke로 검증됐다고 보기 어렵다. 다음 작업은 누락 테이블 migration과 fresh DB/restart smoke를 추가하는 것이다. |
| 58 filter_rules·filter_rule_versions 테이블 작성 | 유지수 | MVP PostgreSQL | Filter Rule schema | `filter_rules` schema를 MVP 통합 Filter Rule 계약에 맞게 정리한다. | `filter_rules` model/migration, origin/kind/editable_fields/config_json columns | 부분 | 수정 | built-in detector, custom keyword, custom regex, context rule이 하나의 `filter_rules` 모델로 저장된다. | 현재 `filter_rules`는 `origin`, `kind`, `label`, `editable_fields`, `config_json` 등 MVP 계약의 핵심 필드에 가깝고, built-in/custom과 detector/keyword/regex/context_rule 구분도 있다. `/dashboard/filters*` mutation 경로는 더 이상 Filter Rule 변경 이력을 기록하지 않는다. 다만 `version` 필드와 `filter_rule_versions` table 자체는 compatibility residue로 남아 있어 schema 차원의 post-MVP history 분리 작업은 아직 남아 있다. |
|  | 김현성 | MVP 수용·검증 | Docker fresh-install smoke | fresh clone/export 기준으로 `.env.example`, Docker Compose, DB migration, 기본 ADMIN seed를 검증한다. | Docker smoke script 또는 수동 smoke checklist, install docs update | 미구현 | 신규 | `docker compose up --build`, `/livez`, `/readyz`, `/healthz`, 기본 ADMIN login이 통과한다. | Docker/compose와 health endpoint는 일부 존재하지만, fresh DB에서 migration, 기본 ADMIN seed, health check, dashboard login, analyze, dashboard metadata 확인까지 이어지는 자동 smoke 결과가 확인되지 않는다. 다음 작업은 fresh-install smoke script나 체크리스트를 만들고 실제 실행 결과를 문서에 남기는 것이다. |
|  | 전체 | MVP 수용·검증 | API unit/integration test | Auth, dashboard session, users, analyze, filters, events, overview, status API의 MVP 계약을 테스트한다. | API test suite, fixtures, CI command | 부분 | 수정 | `cd apps/api && pytest` 또는 대응 명령이 MVP API 계약 기준으로 통과한다. | 일부 API 테스트는 있을 수 있지만, 현재 main 자체가 dashboard session, `/dashboard/status`, `/dashboard/overview`, Analyze `inputs[]`, event input metadata, idempotency가 미완성이다. 따라서 전체 MVP API 계약을 검증하는 테스트 세트는 아직 완료가 아니다. 다음 작업은 각 계약 endpoint별 unit/integration test와 privacy/error case test를 보강하는 것이다. |
|  | 김현성 | MVP 수용·검증 | Dashboard typecheck/build smoke | dashboard TypeScript typecheck/build와 주요 화면 loading/empty/error state smoke를 검증한다. | `npm run typecheck`, `npm run build`, dashboard smoke checklist | 부분 | 수정 | `login.html`, `overview.html`, `events.html`, `event-detail.html`, `users.html`, `filters.html`, `status.html`가 API-backed 화면으로 렌더링된다. | dashboard package에는 typecheck/build script가 있다. 하지만 현재 entry 이름과 계약 entry 이름이 다르고, `status.html`이 없으며, admin/events/users 화면은 정적 mock 또는 placeholder다. 다음 작업은 `login.html`, `overview.html`, `status.html`을 계약대로 갖추고, 각 화면이 API-backed loading/empty/error 상태까지 렌더링되는 smoke를 추가하는 것이다. |
|  | 김현성 | MVP 수용·검증 | Extension checks | selector, send hook, action UX, auth refresh, API client fixture를 검증한다. | extension checks script, fixture, manual real-service smoke | 부분 | 수정 | `python apps/extension/tests/run_extension_checks.py all` 또는 대응 명령이 통과하고 silent allow가 발생하지 않는다. | extension README에는 typecheck, test, build, prompt/file preflight checks가 정리되어 있고 DOM preflight 구현 설명도 있다. 즉 extension 단독 검증은 일부 있다. 아직 완료가 아닌 이유는 서버 Analyze가 최종 `inputs[]` 계약이 아니어서 extension과 real API 사이의 end-to-end Allow/Warn/Mask/Block smoke가 불가능하거나 불완전하기 때문이다. 다음 작업은 서버 계약 교체 후 real API smoke를 실행하는 것이다. |
|  | 전체 | MVP 수용·검증 | Basic privacy smoke | 입력 본문, 파일 내용, 전체 `masked_prompt`, 탐지값 원문, 원본 파일명, dry-run sample이 저장·표시되지 않는지 확인한다. | privacy smoke test 또는 checklist | 부분 | 수정 | DB, dashboard API/DOM, error response에서 금지값이 확인되지 않는다. full privacy regression은 MVP 이후 범위다. | 설계와 README에는 raw prompt, file content, detected raw value, original filename, full masked prompt를 저장하지 않는다는 기준이 있다. 하지만 현재 event detail에는 prompt hash 계열 식별자가 남아 있고, DB/API/DOM/error response에 금지값이 남지 않는지 자동 검사하는 smoke가 확인되지 않는다. 다음 작업은 금지값 fixture를 넣고 DB, dashboard API, dashboard DOM, error response를 검사하는 basic privacy smoke를 추가하는 것이다. |
|  | 전체 | MVP 수용·검증 | 최종 smoke 시나리오 | 15.5의 최종 smoke 시나리오를 실행한다. | final smoke checklist, 결과 기록 | 미구현 | 신규 | fresh install부터 extension analyze, Allow/Warn/Mask/Block, dashboard metadata 확인까지 끊기지 않고 통과한다. | fresh install부터 기본 admin login, dashboard session, 사용자 생성, extension real analyze, Allow/Warn/Mask/Block, event metadata 확인까지 이어지는 MVP 전체 흐름은 아직 연결되지 않았다. 특히 dashboard session, `inputs[]` Analyze, event input metadata, `/dashboard/status`, `/dashboard/overview`가 빠져 있다. 다음 작업은 각 핵심 계약을 구현한 뒤 15.5 최종 smoke 시나리오를 실제 실행하는 것이다. |
|  | 전체 | MVP 수용·검증 | 문서 정합성 확인 | README/install/admin/privacy/release 문서를 이 문서의 MVP 계약과 맞춘다. | README/install/admin/privacy/release docs | 부분 | 수정 | 주요 문서가 `/dashboard/*`, `inputs[]`, `login_id`, Filter Rule `origin/kind`, MVP 범위 기준과 충돌하지 않는다. | README는 현재 extension MVP 중심으로 작성되어 있고, 현재 main 구현과 이 문서의 MVP 계약 사이에는 차이가 크다. 계약을 바꾸지 말고 WBS `현재 상태`와 `근거/비고`에 현재 구현 수준과 남은 작업을 분리해서 적어야 한다. 다음 작업은 이 문서가 current main 상태를 보수적으로 반영하는지 diff review하는 것이다. |


### 23.2 Non-MVP WBS + 산출물 + 배분

| 기존 WBS | 담당 | 분류 | 영역 | 구현 단위 | 산출물 | 현재 상태 | 필요한 조치 | 완료 기준 | 근거/비고 |
|---|---|---|---|---|---|---|---|---|---|
|  |  | MVP 이후 제품 기능 | 사용자 관리 | 사용자 hard delete 또는 사용자 데이터 익명화 | user deletion/anonymization API, retention policy, audit 처리 | 미구현 | 신규 | 사용자 비활성화와 hard delete/익명화 동작이 구분되고, 마지막 ACTIVE ADMIN 보호 규칙이 유지된다. | MVP에서는 `DISABLED` 처리만 사용한다. |
|  |  | MVP 이후 제품 기능 | 사용자 관리 | 표시정보 수정 전용 사용자 관리 UI/API | profile metadata patch API, users UI edit form, audit metadata | 미구현 | 신규 | role/status 변경 API와 분리되어 표시 이름/부서 등 표시 metadata만 수정된다. | MVP에서는 생성, role 변경, status 변경만 포함한다. |
|  |  | MVP 이후 제품 기능 | 정책/UX | 여러 탐지·제약이 동시에 걸린 경우의 고급 정책 조합 | policy combination engine, conflict resolution rules, UX copy | 미구현 | 신규 | 단순 `Block > Mask > Warn > Allow`를 넘어 복합 상황별 action 조합이 정의되고 테스트된다. | MVP는 top-level action 하나만 따른다. |
|  |  | MVP 이후 제품 기능 | 정책/UX | 사용자별 conflict resolution | user/group-aware conflict policy, tests | 미구현 | 신규 | 사용자 또는 그룹별 예외/우선순위가 일관되게 적용된다. | MVP에는 사용자별 conflict resolution을 넣지 않는다. |
|  |  | MVP 이후 제품 기능 | 정책/UX | 복합 remediation UX | multi-step warning/masking/remediation UI, extension/dashboard UX tests | 미구현 | 신규 | 여러 remediation이 동시에 필요한 경우 사용자가 이해할 수 있는 순서와 UI가 제공된다. | MVP는 Allow/Warn/Mask/Block 기본 UX만 포함한다. |
|  |  | MVP 이후 제품 기능 | Enterprise | SaaS 멀티테넌트 운영 | tenant model, tenant isolation, tenant admin UI, billing-ready deployment docs | 미구현 | 신규 | tenant 간 데이터/설정/사용자 접근이 분리된다. | MVP는 self-hosted 단일 운영 기준이다. |
|  |  | MVP 이후 제품 기능 | Enterprise | 결제·엔터프라이즈 조직 관리 | billing integration, org admin model, plan limits | 미구현 | 신규 | 조직/요금제/권한 모델이 API와 UI에 반영된다. | MVP 범위 밖이다. |
|  |  | MVP 이후 제품 기능 | Enterprise | SSO/SIEM 연동 | SSO provider integration, SIEM export, admin docs | 미구현 | 신규 | SSO 로그인과 SIEM event export가 보안 기준을 만족한다. | MVP는 로컬 계정과 dashboard session 기준이다. |
|  |  | MVP 이후 서버·인프라·운영 | Redis/운영 | Redis 기반 다중 서버 요청 한도 상태 저장소, 분산 잠금, 큐, 캐시 사용 | Redis profile, service adapter, failover behavior tests | 미구현 | 신규 | Redis off/on profile이 모두 검증되고 PostgreSQL 영속 데이터와 충돌하지 않는다. | MVP에서 Redis는 선택 구성이다. |
|  |  | MVP 이후 서버·인프라·운영 | 배포 | 운영 배포 profile 분리와 reverse proxy 예시 고도화 | compose profile, reverse proxy sample, HTTPS/domain/TLS docs | 미구현 | 신규 | HTTPS, domain, TLS 종료, 업로드 크기 제한, header 전달 기준이 문서화된다. | MVP는 API+PostgreSQL 기본 Compose 실행 기준이다. |
|  |  | MVP 이후 서버·인프라·운영 | 로그/릴리즈 | 운영 로그 보존 정책과 로그 수집 파이프라인 | log field set, retention policy, collector config | 미구현 | 신규 | 입력 본문, 파일 내용, 전체 `masked_prompt`, secret 값이 로그에 저장되지 않는다. | MVP는 기본 request body logging 비활성만 요구한다. |
|  |  | MVP 이후 서버·인프라·운영 | 릴리즈 | 배포 artifact와 확장앱 package release 자동화 | release workflow, extension package artifact, build metadata | 미구현 | 신규 | release artifact와 extension package의 version/build 식별자를 확인할 수 있다. | MVP는 수동 smoke와 기본 build 기준이다. |
|  |  | MVP 이후 API·데이터·Analyze | HMAC fingerprint | HMAC 기반 `input_bundle_hash` 또는 request fingerprint | HMAC-SHA-256 helper, canonical JSON, `PROMPTGUARD_HMAC_SECRET`, tests | 미구현 | 신규 | 같은 canonical input bundle/request metadata에서 같은 HMAC 결과가 나오고, 입력 본문은 저장되지 않는다. | MVP는 `(login_id, client_request_id)` 중복 event 방지만 구현한다. |
|  |  | MVP 이후 API·데이터·Analyze | Filter Rule history | Filter Rule 변경 이력과 과거 rule set 재현성 | `filter_rule_versions`, change history service, reproducibility metadata | 미구현 | 신규 | 과거 event가 어떤 rule 상태에서 생성됐는지 재현 가능한 metadata가 남는다. | MVP에서는 현재 `filter_rules` 상태만 사용한다. |
|  |  | MVP 이후 API·데이터·Analyze | 사용자 식별자 | `login_id` 변경 기능과 stable `user_id` 도입 | stable `user_id`, FK migration, user path parameter 변경 | 미구현 | 신규 | `login_id`는 변경 가능한 credential로만 사용되고 event/user 통계 연결이 깨지지 않는다. | MVP는 `login_id`를 식별자로 사용하고 변경 기능을 제공하지 않는다. |
|  |  | MVP 이후 API·데이터·Analyze | Analyze 확장 | Analyze schema의 고급 확장 | extended input kinds, backward-compatible schema, tests | 미구현 | 신규 | 새 input kind가 기존 `inputs[]` 계약을 깨지 않고 추가된다. | MVP input kind는 text/attachment_metadata/unsupported_attachment 기준이다. |
|  |  | MVP 이후 탐지·Filter Rule·파일 분석 | Scoring | advanced scoring weights 편집 | scoring config UI/API, validation, dry-run explanation | 미구현 | 신규 | `sensitivity`와 advanced weight 편집 결과가 충돌하지 않고 dry-run으로 설명 가능하다. | MVP는 `sensitivity`만 사용한다. |
|  |  | MVP 이후 탐지·Filter Rule·파일 분석 | Business Context | Business Context rule 고도화와 한국 현지화 rule pack | corpus, context rule pack, FP/FN measurement, regression tests | 미구현 | 신규 | positive/negative corpus 기준 FP/FN이 측정되고 low confidence 후보가 강한 차단으로 바로 이어지지 않는다. | MVP는 keyword/evidence 기반 기본 context rule만 사용한다. |
|  |  | MVP 이후 탐지·Filter Rule·파일 분석 | Regex safety | Custom regex ReDoS regression | ReDoS fixtures, safe-regex/timeout strategy, API latency tests | 미구현 | 신규 | 위험 regex fixture가 저장 단계에서 거부되고 API latency와 worker 안정성을 깨뜨리지 않는다. | MVP는 syntax와 길이 검증만 필수다. |
|  |  | MVP 이후 탐지·Filter Rule·파일 분석 | File analysis | PDF/Office/OCR/archive/binary/image content scan | parser adapters, size limits, error/privacy tests | 미구현 | 신규 | parser 실패 시 입력 본문/파일 내용이 error detail/log에 남지 않고 각 parser별 크기 제한이 적용된다. | MVP는 작은 text file scan만 포함한다. |
|  |  | MVP 이후 탐지·Filter Rule·파일 분석 | Network inspection | 브라우저 네트워크 요청 감청 기반 검사 | network interception design, extension permission review, tests | 미구현 | 신규 | 브라우저 permission과 개인정보 기준을 만족하면서 전송 요청을 검사한다. | MVP는 DOM 기반 send attempt hook 기준이다. |
|  |  | MVP 이후 확장앱·대시보드 | Extension | selector update E2E 강화 | remote selector override tests, fallback selector tests, DOM change smoke | 미구현 | 신규 | remote selector, fallback selector, DOM 변경 smoke가 모두 검증된다. | MVP는 built-in fallback과 기본 selector/hook만 요구한다. |
|  |  | MVP 이후 확장앱·대시보드 | Extension | AI 서비스별 attachment 처리 고도화 | service-specific attachment adapters, metadata tests | 미구현 | 신규 | raw `File` 접근 가능 여부와 attachment chip metadata 처리 기준이 서비스별로 검증된다. | MVP는 공통 metadata-only/unsupported 처리 기준이다. |
|  |  | MVP 이후 확장앱·대시보드 | Dashboard | dashboard-wide 공통 필터와 date range picker | dashboard query controls, API query params, aggregate tests | 미구현 | 신규 | 이벤트 목록, 상세, overview aggregate가 동일한 필터 기준을 사용한다. | MVP 기본 통계 기간은 최근 30일이다. |
|  |  | MVP 이후 확장앱·대시보드 | Dashboard | 고급 drill-down과 사용자별 이벤트 상세 drill-down | drill-down UI, API pagination, RBAC tests | 미구현 | 신규 | USER에게 노출되지 않고 ADMIN만 drill-down metadata를 조회한다. | MVP는 기본 Events/Users metadata 화면만 제공한다. |
|  |  | MVP 이후 확장앱·대시보드 | Dashboard | 고급 차트 | stacked bar, detection heatmap, summary p95, performance tests | 미구현 | 신규 | 대량 이벤트 데이터에서 응답 시간과 렌더링 성능이 검증된다. | MVP는 action/period 기본 차트만 포함한다. |
|  |  | MVP 이후 확장앱·대시보드 | Dashboard | Filter Rule 변경 이력 UI와 과거 rule set 재현성 UI | change history screen, reproducibility UI, privacy checks | 미구현 | 신규 | 변경 이력을 보여주되 입력 본문, 탐지값 원문, 내부 secret을 노출하지 않는다. | MVP 이벤트 상세 기본 화면에는 내부 식별자를 표시하지 않는다. |
|  |  | MVP 이후 보안·개인정보·재현성 보강 | Refresh hardening | refresh reuse detection과 token family 관리 | `refresh_token_families`, `refresh_tokens.family_id`, reuse detection tests | 미구현 | 신규 | token 재사용 감지 시 해당 token family가 폐기되고 재로그인이 요구된다. | MVP는 refresh token hash 저장과 rotation만 포함한다. |
|  |  | MVP 이후 보안·개인정보·재현성 보강 | Privacy regression | full privacy/security regression | DB schema scan, log scan, error scan, dashboard DOM/API scan, fixture matrix | 미구현 | 신규 | exact/escaped/url-encoded/base64-like 변형까지 검사하고 실패 시 완료로 보지 않는다. | MVP는 basic privacy smoke만 포함한다. |
|  |  | MVP 이후 보안·개인정보·재현성 보강 | Request limits | endpoint별 요청 한도 정책 정의와 적용 | login/refresh/analyze/dashboard mutation limits, 429 tests | 미구현 | 신규 | endpoint별 분당 요청 수, 연속 실패 횟수, 제한 기준 식별자와 해제 조건이 정의된다. | MVP는 세부 요청 한도 정책을 필수로 하지 않는다. |
|  |  | MVP 이후 보안·개인정보·재현성 보강 | Security headers | dashboard security headers 적용 | CSP, nosniff, Referrer-Policy, frame-ancestors, smoke tests | 미구현 | 신규 | header 적용 후 login/overview/events/users/filters/status 화면이 정상 동작한다. | MVP 보안 기준에는 CSRF/session/XSS-safe rendering만 포함한다. |
