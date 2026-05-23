# PromptGuard MVP WBS 재정리

작성일: 2026-05-23

## 기준

참고한 파일:
- `docs/references/(WBS) OASECURE Project.xlsx`
- `docs/references/(WBS) OASECURE Project.xlsx - 시트1.csv`
- `docs/references/promptguard_dev_docs_v_0_3_open_source.md`
- `docs/references/PromptGuard_Chrome_Extension_Analyze_Integration_Dev_Reference_v0_4.md`
- 현재 repo 코드

판정 기준:
- XLSX 원본 `프로젝트WBS` 시트의 6~107행을 MVP 작업 범위로 본다.
- CSV는 색상 정보가 없으므로 행 내용 확인용으로만 본다.
- 현재 repo에는 `apps/extension` 구현만 있다.
- `apps/api`, `apps/dashboard`, `packages`, `infra`, root workspace build 구조는 아직 없다.

상태 표기:
- `됨`: 현재 repo 코드와 테스트로 확인됨.
- `부분`: 일부 코드/문서/테스트는 있으나 WBS 완료 기준 전체는 아님.
- `안됨`: 현재 repo에 구현 없음.
- `검토`: MVP 포함 여부나 담당 분리가 한 번 더 필요함.

검증:
- `python apps/extension/tests/run_extension_checks.py all` 통과.
- 23개 test file, 70개 test 통과.
- extension build 통과.

## 1. 현재 구현된 범위

현재 실제로 구현되어 실행 가능한 것은 Chrome Extension MVP다.

| 구현 범위 | 상태 | repo 위치 | 확인 방법 |
| --- | --- | --- | --- |
| Manifest V3 확장앱 구조 | 됨 | `apps/extension/manifest.json`, `apps/extension/src/*` | extension checks |
| Options page | 됨 | `apps/extension/src/options/*` | options tests |
| API URL 저장, token 저장, mock mode | 됨 | `apps/extension/src/background/*`, `apps/extension/src/options/*` | storage/options tests |
| `/auth/me`, `/config/extension`, `/prompts/analyze`, `/files/analyze` client 경계 | 부분 | `apps/extension/src/background/*Client.ts` | real server 없음 |
| ChatGPT domain 제한 | 됨 | `apps/extension/manifest.json` | manifest permission test |
| textarea/contenteditable 탐지 | 됨 | `apps/extension/src/content/domDetector.ts` | unit/E2E |
| Send button click 보류 | 됨 | `apps/extension/src/content/sendInterceptor.ts` | unit/E2E |
| Enter 전송 보류 | 됨 | `apps/extension/src/content/sendInterceptor.ts` | unit/E2E |
| Allow/Warn/Mask/Block 처리 | 됨 | `apps/extension/src/content/promptPreflightController.ts` | unit/E2E |
| masked_prompt 입력창 치환 | 됨 | `apps/extension/src/content/maskedTextInjector.ts` | unit |
| Block/fail-closed | 됨 | `apps/extension/src/content/*Controller.ts` | unit |
| raw prompt/file content 저장 방지 테스트 | 부분 | `apps/extension/tests/unit/privacyRegression.test.ts` | 서버 DB/log 검증은 없음 |
| 텍스트 파일 업로드 preflight | 부분/추가 구현됨 | `apps/extension/src/content/fileUpload*`, `textFileReader.ts` | v0.4 추가 범위, 서버 `/files/analyze` 없음 |

## 2. 지금 구현한 것 외에 더 필요한 것

MVP 완성 기준으로 보면 Chrome Extension만으로는 부족하다. 남은 큰 덩어리는 아래와 같다.

| 구현 범위 | 현재 상태 | 필요한 이유 | 주요 위치 |
| --- | --- | --- | --- |
| Monorepo/root workspace | 부분 | API, dashboard, extension을 한 번에 dev/build/test 해야 함 | `package.json`, `apps/*`, `packages/*` |
| Docker/infra | 안됨 | self-host 제품이므로 fresh clone 실행 경로가 필요함 | `infra/docker-compose.yml`, `.env.example` |
| API 서버 | 안됨 | Extension이 호출할 실제 `/prompts/analyze`, auth, config가 필요함 | `apps/api` |
| Setup wizard | 안됨 | 첫 ADMIN, workspace, default policy, setup lock 필요 | `apps/api`, `apps/dashboard` |
| 일반회원 가입/Auth/RBAC | 안됨 | USER/ADMIN 분리, invite, login, refresh token 필요 | `apps/api` |
| Analyze pipeline | 안됨 | prompt 검증, detector, scoring, masking, event 저장 필요 | `apps/api/src/analyze`, `packages/detectors` |
| Detector/rule pack | 안됨 | PII, secret, 한국어 계약/고객/전략 문맥 탐지 필요 | `apps/api/src/detectors`, `tests/corpus` |
| Custom filter | 안됨 | WBS에 직접 필터 API/dry-run/pipeline/UI가 있음 | `apps/api`, `apps/dashboard` |
| Event logging | 안됨 | dashboard가 볼 metadata-only 이벤트 저장 필요 | `apps/api/src/events`, DB migration |
| Admin dashboard | 안됨 | overview, events, users, invites, policy, stats, status 화면 필요 | `apps/dashboard` |
| Privacy/security gates | 부분 | extension 검증은 있으나 DB/log/dashboard/server 검증이 없음 | `apps/api/tests`, `apps/dashboard/tests`, CI |
| Performance/release/docs | 부분 | fresh install, p95, release artifact, 운영 문서 필요 | `docs`, `scripts`, CI |

## 3. 담당자별 작업표

정렬 기준:
1. 이름 가나다순: 김민지 -> 김영은 -> 김현성 -> 유지수 -> 전체
2. 각 사람 안에서는 구현 범위순: 공통/기획 -> 서버/API -> 분석/탐지 -> Chrome Extension -> Dashboard/UI -> QA/문서/릴리즈

### 김민지

| 구현 범위 | WBS 행 | 상태 | 해야 할 일 | 완료 기준 | 테스트/검증 |
| --- | ---: | --- | --- | --- | --- |
| 서버/API - 일반회원 가입 | 27~30 | 안됨 | invite 가입, invite 생성/폐기, 가입 방식, 사용자 상태/역할 변경 API 구현 | invite, registration mode, user role/status가 API로 동작 | signup/user API tests |
| 서버/API - 이벤트 저장 | 37~38 | 안됨 | analysis event, detection summary DB schema와 저장 서비스 구현 | raw_prompt, masked_prompt, detected value 컬럼 없이 metadata 저장 | migration + privacy DB scan |
| 서버/API - custom filter dry-run | 56 | 안됨 | 샘플 문자열로 필터 결과를 확인하는 dry-run API 구현 | dry-run 샘플 원문이 DB/log에 저장되지 않음 | dry-run privacy test |
| 분석/탐지 - rule pack | 48, 52 | 안됨 | rule_pack_version, label, severity 구조와 애매한 문장 처리 기준 작성 | AMBIGUOUS가 강한 차단으로 잘못 승격되지 않음 | corpus unit tests |
| Dashboard/UI - 사용자 통계 | 86~87 | 안됨 | 사용자별 이벤트 표, action/detection type chart 구현 | 사용자별 유형/횟수/action 분포가 metadata로 표시 | dashboard e2e |
| Dashboard/UI - 사용자/가입 관리 | 88~89 | 안됨 | Users, Invites, Registration 화면 구현 | ADMIN이 사용자 상태/역할, 초대, 가입 방식을 관리 | dashboard e2e + RBAC |
| Dashboard/UI - 정책/통계/직접필터/상태 | 90~93 | 안됨 | policy 조회, detection stats, custom filter 관리, server status 화면 구현 | 원문 없이 policy/filter/status를 볼 수 있음 | dashboard privacy UI tests |
| QA/문서 - auth 검증 | 31 | 안됨 | 가입, 로그인, 권한 통합 테스트 작성 | USER의 admin API 접근 403 등 검증 | auth/RBAC integration tests |

김민지 AI에게 줄 지시:

```text
WBS 27~31, 37~38, 48, 52, 56, 86~93을 맡아라.
기존 WBS의 담당자와 범위는 유지한다.
우선 apps/api의 invite/signup/user/event/custom-filter dry-run API와 DB schema를 구현하고,
그 다음 apps/dashboard의 사용자/가입/정책/통계/직접필터/status 화면을 구현한다.
모든 event/custom-filter/dry-run 작업은 raw_prompt, masked_prompt, detected raw value, dry-run sample을 저장하지 않는 테스트를 포함한다.
```

### 김영은

| 구현 범위 | WBS 행 | 상태 | 해야 할 일 | 완료 기준 | 테스트/검증 |
| --- | ---: | --- | --- | --- | --- |
| 기획/UI 흐름 | 8 | 부분 | setup -> 회원가입 -> extension -> dashboard 흐름도를 실제 화면/API 기준으로 갱신 | 팀원이 온보딩 흐름을 한 번에 이해 | 문서 리뷰 |
| 서버/API - setup | 17~21 | 안됨 | `/setup/status`, `/setup/bootstrap`, setup lock, SETUP_COMPLETED audit, default workspace/policy seed 구현 | fresh DB에서 첫 ADMIN 1회 생성 후 bootstrap 잠김 | setup integration tests |
| 분석/탐지 - secret detector | 44~47 | 안됨 | GitHub/AWS key, JWT, private key, DB URI, `.env` secret/high entropy 탐지 구현 | secret fixture가 high/critical severity로 탐지 | detector unit tests |
| 분석/탐지 - 내부전략 문맥 | 51 | 안됨 | 가격정책, 출시계획, 경쟁전략 rule classifier 구현 | 내부전략 positive/negative corpus 통과 | corpus tests |
| Dashboard/UI - shell | 79~80 | 안됨 | dashboard routing, layout, auth guard, setup/login 화면 구현 | setup/login/dashboard shell 접근 가능 | dashboard build/e2e |
| Dashboard/UI - overview/events | 81~84 | 안됨 | overview summary, trend, risk event list/filter/detail 구현 | event detail에 raw_prompt/masked_prompt/value가 없음 | dashboard privacy UI tests |

김영은 AI에게 줄 지시:

```text
WBS 8, 17~21, 44~47, 51, 79~84를 맡아라.
먼저 setup API와 dashboard shell을 연결해 첫 관리자 생성 흐름을 끝낸다.
그 다음 secret detector와 overview/events 화면을 구현한다.
Dashboard는 metadata-only 화면이어야 하며 raw_prompt, masked_prompt, detected value를 표시하지 않는다.
```

### 김현성

| 구현 범위 | WBS 행 | 상태 | 해야 할 일 | 완료 기준 | 테스트/검증 |
| --- | ---: | --- | --- | --- | --- |
| 공통/기획 | 6~7 | 됨/부분 | MVP 범위와 P0/P1/P2를 WBS 상태표와 연결 | 각 작업이 MVP/P1/후속으로 구분됨 | 문서 리뷰 |
| 공통/저장소 | 11, 14 | 부분 | root workspace, `apps/api`, `apps/dashboard`, `packages`, `infra`, 공통 dev/build/test 명령 정리 | 루트에서 전체 typecheck/test/build 가능 | root build/test |
| Infra | 12 | 안됨 | Docker Compose 골격 작성 | API, dashboard, PostgreSQL, Redis 기동 | `docker compose up` + `/healthz` |
| 서버/API - Analyze contract | 33 | 부분 | `/prompts/analyze` request schema와 extension/shared contract 정리 | prompt/context/policy/client_request_id 검증 | API schema tests |
| 서버/API - privacy/idempotency/hash | 34~36 | 안됨/부분 | request body logging 차단, redaction hook, client_request_id idempotency, HMAC prompt_hash 구현 | DB/log 중복 이벤트/원문 저장 없음 | privacy + idempotency + hash tests |
| 분석/탐지 - 계약 문맥 | 49 | 안됨 | 계약금액, 위약금, NDA rule classifier 구현 | 계약 문맥 corpus 통과 | corpus tests |
| 분석/탐지 - custom filter API/pipeline | 54, 57 | 안됨 | regex/keyword filter CRUD와 Analyze pipeline 연결 | custom_filter detection과 통계 metadata 생성 | CRUD + pipeline tests |
| 분석/탐지 - overlap merge | 58 | 안됨 | secret 우선, 긴 span 우선 merge 규칙 구현 | overlap fixture가 deterministic하게 병합 | merge unit tests |
| Chrome Extension | 62~63, 66~70, 73~74, 76~77 | 됨 | 기존 구현 유지 | fixture 기준 동작 유지 | extension checks |
| Chrome Extension | 64~65, 71~72, 75, 78 | 부분 | refresh/logout, real API contract smoke, approved hash, Mask 사유/피드백, degraded server status 보강 | WBS의 누락 세부 동작까지 완료 | extension + real API smoke |

김현성 AI에게 줄 지시:

```text
WBS 6~7, 11~14, 33~36, 49, 54, 57~58, 62~78을 맡아라.
현재 extension MVP는 유지하고, 부족한 부분만 보강한다.
root workspace와 server/extension contract를 먼저 고정한 뒤,
Analyze schema, raw prompt logging redaction, idempotency, HMAC prompt_hash, custom filter API/pipeline, overlap merge를 구현한다.
Extension 쪽은 refresh/logout, approved hash, real API smoke, server status 표시를 보강한다.
```

### 유지수

| 구현 범위 | WBS 행 | 상태 | 해야 할 일 | 완료 기준 | 테스트/검증 |
| --- | ---: | --- | --- | --- | --- |
| 서버/Infra 결정 | 9 | 부분 | Docker, DB, Redis, reverse proxy 구성안을 실제 infra 파일과 맞춤 | 구성안과 compose가 일치 | doc + compose review |
| 서버/API - health/migration/env | 15~16, 13 | 안됨 | `/healthz`, dependency status, migration skeleton, env validation 구현 | fresh install/restart가 안전하게 동작 | health/migration/env tests |
| 서버/API - auth 기반 | 22~26, 32 | 안됨 | users/invites/settings DB, password hash, login/refresh/auth/me, refresh token hash, RBAC, CORS/rate limit 구현 | USER/ADMIN 분리와 token lifecycle 동작 | auth/RBAC/security tests |
| 분석/탐지 - 개인정보/한국 현지화 | 39~43, 50 | 안됨 | EMAIL/PHONE, RRN checksum, card Luhn, business number, amount/discount/period, customer info classifier 구현 | positive/negative corpus 통과 | detector unit tests |
| 분석/탐지 - custom filter table | 53 | 안됨 | custom_filter_rules, versions migration 구현 | workspace별 rule/version 저장 | migration/repository tests |
| 분석/탐지 - masking/analyze integration | 60~61 | 안됨 | placeholder masking, repeated value masking, detector -> score -> mask -> log -> response 통합 | Analyze API가 실제 decision/masked_prompt/event를 반환 | `/prompts/analyze` integration tests |
| Dashboard/API | 85 | 안됨 | 사용자별 이벤트 통계 API 구현 | dashboard user stats가 metadata로 조회됨 | admin stats API tests |

유지수 AI에게 줄 지시:

```text
WBS 9, 13, 15~16, 22~26, 32, 39~43, 50, 53, 60~61, 85를 맡아라.
서버 실행 기반과 auth/RBAC를 먼저 만든 뒤 detector와 Analyze 통합을 구현한다.
비밀번호와 refresh token은 원문 저장 금지, prompt/detection value도 DB/log 저장 금지다.
Detector는 positive/negative fixture와 privacy regression을 같이 추가한다.
```

### 전체

| 구현 범위 | WBS 행 | 상태 | 해야 할 일 | 완료 기준 | 테스트/검증 |
| --- | ---: | --- | --- | --- | --- |
| 검증 계획 | 10 | 부분 | install, E2E, privacy, security, release gate를 전체 repo 기준으로 정리 | release 전에 어떤 테스트를 돌릴지 명확함 | gate checklist |
| 직접필터 보안 | 55 | 안됨 | regex length/syntax/timeout/ReDoS 방어 기준 구현/검증 | 위험 regex 저장 전 차단 | ReDoS tests |
| 위험도/scoring | 59 | 안됨 | 0~100 risk score, Allow/Warn/Mask/Block threshold 기준 구현/문서화 | 정책별 action 결정이 일관됨 | scoring tests |
| Privacy/security | 94~98 | 부분/안됨 | dashboard 원문 미노출, DB/log 원문 미저장, 외부 LLM 호출 금지, setup/auth/RBAC security tests | privacy/security gate 통과 | CI gate |
| E2E/integration/performance | 99~103 | 부분/안됨 | extension fixture E2E 유지, remote selector E2E, Analyze/Dashboard 성능, 한국어 FP/FN corpus 평가 | 통합 품질을 수치로 확인 | E2E/perf/corpus |
| 문서/릴리즈 | 104~107 | 부분 | README, install, reverse proxy, admin guide, privacy design, contributing, Docker image, sideload zip, demo scenario 작성 | fresh clone에서 설치->setup->signup->extension->dashboard demo 가능 | release smoke |

전체 AI에게 줄 지시:

```text
WBS 10, 55, 59, 94~107을 맡아라.
각 담당자가 만든 기능을 release gate로 묶고, privacy/security/performance/doc/release 기준을 닫는다.
최종 smoke는 setup -> 일반회원 가입 -> extension 연결 -> prompt analyze -> dashboard metadata 확인 순서로 작성한다.
```

## 4. 구현 순서 제안

| 순서 | 먼저 할 일 | 이유 |
| ---: | --- | --- |
| 1 | root workspace와 `packages/contracts` | API/extension/dashboard가 같은 schema를 써야 함 |
| 2 | Docker/env/healthz/migration | self-host 실행 경로가 먼저 필요함 |
| 3 | setup/auth/RBAC | 모든 API와 dashboard 권한의 기반 |
| 4 | Analyze request schema, privacy redaction, idempotency, HMAC hash | 원문 미저장과 중복 방지가 먼저 닫혀야 함 |
| 5 | detector/rule pack/custom filter/merge/scoring/masking | Analyze API 실제 판단 로직 |
| 6 | event logging | dashboard가 볼 metadata 저장 |
| 7 | extension real API integration 보강 | mock에서 self-host API로 연결 |
| 8 | dashboard 화면/API 연결 | 관리자 운영 화면 완성 |
| 9 | integration/privacy/security/performance/release gate | MVP 배포 가능 여부 확인 |

## 5. WBS에서 빠졌거나 더 세분화해야 하는 작업

| 추가/세분화 필요 항목 | 이유 | 넣을 위치 |
| --- | --- | --- |
| `packages/contracts` | extension 타입과 server schema를 따로 관리하면 drift가 생김 | 저장소/빌드 또는 Analyze contract |
| API error contract | timeout, 401, 413, policy mismatch, invalid response를 machine-readable하게 맞춰야 함 | Analyze API |
| server-side request logging redaction | extension 원문 미저장만으로는 부족함 | 원문보호 |
| DB/log/dashboard privacy scan | raw_prompt 저장 금지의 실제 완료 기준 | Privacy/security |
| approved prompt hash 정책 | extension double-submit과 server idempotency는 다름 | Extension 중복방지 |
| live self-host smoke | mock 통과와 실제 API 통과는 다름 | Extension/API integration |
| remote selector update E2E | `/config/extension` 구현만으로 selector 동기화 완료가 아님 | Extension 설정동기화 |
| dashboard API contract | dashboard UI와 admin API 응답 schema가 먼저 맞아야 함 | Dashboard/API |
| release artifact script | Docker image와 extension sideload zip 생성 경로가 필요함 | 릴리즈 |

## 6. WBS 밖에서 이미 구현된 추가 범위

| 추가 구현 | 현재 상태 | 계속 가져갈지 |
| --- | --- | --- |
| 텍스트 파일 업로드 preflight | extension 쪽 구현됨, 서버 `/files/analyze` 없음 | v0.4 실험 기능으로 유지 가능 |
| original filename 제외 | 구현됨 | privacy 기준에 맞으므로 유지 |
| per-attempt `client_file_id` | 구현됨 | 파일명/파일 hash 없이 매칭하려면 유지 |
| fixed safe overlay message | 구현됨 | 서버 메시지에 원문이 섞일 위험을 줄이므로 유지 |
| no webRequest/DNR static check | 구현됨 | MVP 통제 방식이 DOM preflight이므로 유지 |

## 7. 오해하면 안 되는 점

| 오해 | 정확한 구분 |
| --- | --- |
| Extension API client가 있으니 Analyze API가 된 것이다 | 아니다. client만 있고 self-host API 서버는 없다. |
| raw prompt를 request에 넣으면 privacy 위반이다 | 아니다. 분석 요청에는 필요하다. 저장/log/dashboard 노출이 금지다. |
| extension double-submit guard가 있으면 server idempotency가 필요 없다 | 아니다. 클라이언트 replay 방지와 서버 중복 이벤트 방지는 별도다. |
| Mask panel 구현이면 Masking이 끝났다 | 아니다. extension 치환은 됐지만 server masking engine은 없다. |
| Dashboard event detail에서 masked_prompt는 보여줘도 된다 | 아니다. 원문과 masked_prompt 모두 저장/노출 금지로 본다. |
| 직접 필터 API만 만들면 custom filter 완료다 | 아니다. CRUD, validation, dry-run, pipeline, event metadata, dashboard UI까지 필요하다. |
| 파일 업로드 검사는 v0.3 WBS 완료 항목이다 | 아니다. v0.4 레퍼런스의 추가 실험 기능으로 분리해서 관리한다. |

## 8. 바로 나눠 줄 작업 단위

| 우선순위 | 담당자 | 작업 단위 | 입력 | 출력 | 완료 기준 |
| ---: | --- | --- | --- | --- | --- |
| 1 | 김현성 | root workspace + contracts | WBS 11,14,33 | root scripts, `packages/contracts` | API/extension schema 공유 |
| 2 | 유지수 | infra + API foundation | WBS 9,13,15~16 | compose/env/healthz/migration | fresh API 기동 |
| 3 | 김영은 | setup bootstrap | WBS 17~21,80 | setup API + setup UI | 첫 ADMIN 1회 생성 |
| 4 | 유지수/김민지 | auth/signup/RBAC | WBS 22~32 | auth/register/invite/user APIs | USER/ADMIN 권한 검증 |
| 5 | 김현성/유지수 | Analyze privacy base | WBS 33~36,60~61 | schema/redaction/idempotency/hash/analyze route | raw 미저장 + 응답 계약 |
| 6 | 유지수/김영은/김민지 | detectors/rule pack | WBS 39~52 | detector modules + corpus | PII/secret/context 탐지 |
| 7 | 김현성/김민지/전체 | custom filter | WBS 53~57,92 | CRUD/validation/dry-run/pipeline/UI | 사용자 정의 필터 end-to-end |
| 8 | 김영은/김민지/유지수 | dashboard | WBS 79~93 | dashboard screens + admin APIs | metadata-only 운영 화면 |
| 9 | 전체 | integration/release gate | WBS 94~107 | tests/docs/release scripts | fresh demo 가능 |
