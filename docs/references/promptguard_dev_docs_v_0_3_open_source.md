# PromptGuard 개발 문서 세트 v0.3

부제: **Self-hosted Open-source Shadow AI 입력 단계 보안/거버넌스 시스템**  
대상 MVP: **ChatGPT 웹 + Chrome Extension + self-hosted API 서버 + 관리자/일반회원 회원가입 + 원문 미저장 이벤트 로그 + 관리자 대시보드**  
작성 목적: AI 개발 에이전트가 구현 이슈로 바로 분해할 수 있는 개발 착수용 산출물  

---

---

# 1. PRD: Product Requirements Document

## 1.1 제품 개요

PromptGuard는 직원 또는 팀원이 ChatGPT 같은 외부 생성형 AI에 업무 데이터를 입력하기 직전, 브라우저 확장에서 prompt를 감지하고 self-hosted 서버로 분석하여 민감정보·영업기밀·소스코드·계약정보·인증정보 유출 가능성을 경고, 마스킹 또는 차단하는 **오픈소스 Shadow AI 입력 단계 보안/거버넌스 도구**이다.

관리자는 직접 서버를 띄우고 첫 관리자 계정을 생성한다. 일반회원은 초대 코드, 워크스페이스 코드 또는 관리자가 허용한 공개 가입 방식으로 회원가입한다. 모든 사용자는 Chrome Extension을 자신의 브라우저에 연결하고, 관리자는 대시보드에서 원문 없는 이벤트 메타데이터를 확인한다.

이 제품은 기존 기업용 DLP/CASB와 정면 경쟁하지 않는다. 목표는 다음이다.

1. 오픈소스로 누구나 검증 가능한 prompt 보호 도구를 제공한다.
2. 기존 오픈소스 PII/secret redaction 확장의 한계인 **관리자 대시보드 부재, 정책 관리 부재, 감사 로그 부재**를 보완한다.
3. 원문 저장 없이도 팀 단위 Shadow AI 사용 위험을 파악하게 한다.
4. 소규모 조직, 개발팀, 학생팀, 오픈소스 커뮤니티가 enterprise 보안 제품 없이 최소한의 AI 입력 거버넌스를 운영하게 한다.

## 1.2 문제 정의

### 1.2.1 기업용 제품의 문제

1. 대형 DLP, CASB, SASE, Enterprise Browser 제품은 기능은 강하지만 도입 비용과 운영 부담이 크다.
2. 기존 기업 보안 스택에 종속되는 경우가 많아 개인 팀, 스타트업, 커뮤니티가 쓰기 어렵다.
3. 일부 제품은 감사와 검색 편의를 위해 prompt/response 원문 또는 샘플을 저장할 수 있어 프라이버시 우려가 생긴다.
4. 한국식 개인정보, 한국어 계약 문맥, 고객 대응 문맥은 별도 튜닝이 필요할 수 있다.

### 1.2.2 오픈소스/소형 확장의 문제

1. PII 또는 secret 탐지에만 집중하고, 조직 단위 정책과 대시보드가 없는 경우가 많다.
2. 로컬 redaction은 유용하지만 관리자가 팀 전체 위험 추이를 보기 어렵다.
3. 일반회원/관리자 역할 분리, 초대, 회원 관리, 감사 로그가 부족하다.
4. 전송 직전 차단·경고·마스킹 UX가 일관되지 않을 수 있다.
5. detector 품질, 테스트셋, 정책 버전, 원문 미저장 검증이 체계화되어 있지 않은 경우가 많다.

PromptGuard v0.3는 이 두 문제 사이에서 **오픈소스이면서도 팀 운영 가능한 self-hosted governance**를 목표로 한다.

## 1.3 목표 사용자

| 사용자 | 목표 |
|---|---|
| Self-host 관리자 | 서버를 직접 띄우고 사용자 가입, 정책, 대시보드, 로그 보존 기간을 관리 |
| 일반회원 | ChatGPT를 계속 사용하되 민감정보를 전송 전에 경고/마스킹/차단받음 |
| 개발자 | API key, token, DB URL, 내부 코드가 외부 AI에 유출되는 것을 방지 |
| CS/운영 담당자 | 고객 문의, 장애 내역, 연락처를 마스킹하고 요약 업무를 지속 |
| 팀 리더/보안 담당자 | 원문 없이 위험 유형·조치·추세를 확인 |
| 오픈소스 기여자 | detector, 한국어 문맥 분류기, extension adapter, 대시보드 기능을 개선 |

## 1.4 페르소나

### Persona P-01: 한민준 Self-host 관리자

- 개발팀 20명 규모 스타트업의 백엔드 리더
- 기업용 DLP를 도입할 예산과 시간이 없음
- Docker Compose로 서버를 띄우고 팀원에게 Extension 사용을 안내하고 싶음
- 팀원이 어떤 민감정보 유형을 자주 입력하려 하는지 원문 없이 보고 싶음

### Persona P-02: 이서연 일반회원/CS 매니저

- 고객 문의 요약과 답변 초안 작성에 ChatGPT 사용
- 고객사명, 담당자명, 이메일, 전화번호, 장애 서버명이 포함된 텍스트를 자주 다룸
- 민감정보를 직접 지우는 부담을 줄이고 싶음

### Persona P-03: 김도윤 개발자

- 로그, 코드, stack trace를 외부 AI에 넣어 디버깅하려 함
- bearer token, GitHub token, AWS access key, DB URL 노출 위험이 큼
- 위험값을 자동 탐지하고 차단받기를 원함

### Persona P-04: 정민아 커뮤니티/교육 운영자

- 여러 명이 공동 프로젝트를 하며 외부 AI를 활용함
- 강력한 enterprise 보안 제품보다 가벼운 오픈소스 도구가 필요함
- 관리자는 볼 수 있되 원문은 저장하지 않는 구조를 원함

## 1.5 핵심 가치

| 가치 | 설명 | 검증 방법 |
|---|---|---|
| 오픈소스 검증 가능성 | prompt 처리·저장 로직을 누구나 코드로 검증 가능 | 공개 repo, 테스트, threat model, privacy CI |
| Self-hosted 데이터 통제 | 서버와 DB를 관리자가 직접 운영 | Docker Compose 설치 테스트 |
| 관리자/일반회원 운영성 | 첫 관리자 가입, 일반회원 가입, 역할 분리, 사용자 관리 | Auth/RBAC E2E 테스트 |
| 입력 직전 통제 | ChatGPT 전송 버튼 또는 Enter 입력 직전에 분석 | Extension E2E 테스트 |
| 생산성 보존 | 차단만 하지 않고 마스킹 후 전송 제공 | Masking 적용률, UX 테스트 |
| Privacy-by-design | raw_prompt, masked_prompt, detection_value 저장 금지 | DB schema, 로그, error tracking 검사 |
| 한국 현지화 | 한국식 개인정보, 전화번호, 주민등록번호, 사업자등록번호, 한국어 고객지원·계약·영업 문맥 탐지 | 한국어 테스트셋 기반 FP/FN 평가 |
| Metadata-only governance | 원문 없이 위험 유형·조치 결과·정책 버전 저장 | 관리자 대시보드 및 audit log 검증 |

## 1.6 MVP 범위

### 반드시 구현할 것

| 항목 | 설명 | 관련 요구사항 |
|---|---|---|
| OSS packaging | GitHub repo 구조, Docker Compose, `.env.example`, 설치/운영 문서 | FR-001~FR-008 |
| Setup wizard | 첫 관리자 회원가입, 서버 초기화, 기본 policy 생성, setup lock | FR-011~FR-018 |
| 일반회원 회원가입 | 초대 코드/워크스페이스 코드 기반 가입, 로그인, 계정 상태 관리 | FR-021~FR-030 |
| Chrome Extension | self-host API 연결, ChatGPT 입력창 탐지, 전송 이벤트 인터셉트 | FR-101~FR-116 |
| Analyze API | prompt 분석 요청/응답, idempotency, max length, policy mismatch 처리 | FR-201~FR-214 |
| Regex detector | 이메일, 전화번호, 주민등록번호, 카드번호, 사업자등록번호 후보 | FR-301~FR-306 |
| Secret detector | GitHub token, AWS key, JWT, private key, DB URL, `.env` secret 후보 | FR-311~FR-317 |
| Rule-based context classifier | 로컬 rule 기반 계약정보, 고객정보, 영업기밀, 내부전략 분류. MVP에서 LLM 사용 금지 | FR-321~FR-325 |
| Risk scoring | 정책 기반 점수 산정, action 결정, 점수 산정 이유 문서화 | FR-401~FR-408 |
| Masking | 민감값 placeholder 치환, overlap 처리, 반복값 전체 치환 | FR-501~FR-508 |
| Event logging | 원문 없는 이벤트 저장, HMAC prompt_hash, 원문 미저장 검증 | FR-601~FR-608, PRV-001~PRV-006 |
| Admin dashboard | 요약, 이벤트 목록, 사용자별 이벤트 유형/횟수 목록·시각화, 사용자 관리 | FR-701~FR-714 |
| Auth/RBAC | ADMIN/USER 권한 분리, token 만료, refresh token hash 저장 | FR-801~FR-810, SEC-001~SEC-010 |

### 구현하면 좋은 것

| 항목 | 설명 | 우선순위 |
|---|---|---|
| 직접 필터 설정 | ADMIN이 regex/keyword 기반 사용자 정의 필터를 만들고 severity/action/placeholder를 설정 | P1 |
| 사용자 정의 필터 테스트 | 필터 저장 전 샘플 문자열로 탐지 결과를 미리 확인. 샘플 원문 저장 금지 | P1 |
| 회원 승인 대기 | 일반회원 가입 후 관리자가 승인해야 ACTIVE 전환 | P1 |
| Extension pairing code | dashboard에서 1회용 pairing code를 생성해 Extension 연결 | P1 |
| 로컬 선탐지 | Extension에서 regex/secret 일부 선탐지 후 서버 호출 최적화 | P1 |
| 정책 시뮬레이션 | 정책 변경 전 최근 이벤트 metadata에 적용했을 때 차단 수 예측 | P1 |
| Slack/Email/Webhook 알림 | 고위험 차단 이벤트 관리자 알림. 원문 포함 금지 | P1 |
| 반복 위험 리포트 | 사용자/부서별 반복 이벤트 자동 요약 | P1 |
| Metadata CSV export | 원문 없는 이벤트·사용자 통계 CSV export | P1 |
| Retention job | 보존 기간 경과 이벤트 삭제 또는 집계화 | P1 |
| Multi-workspace | 하나의 서버에서 여러 워크스페이스 운영 | P2 |
| OIDC/SAML | 기업/학교 계정 연동 | P2 |

### 후속 버전으로 미룰 것

| 항목 | 이유 |
|---|---|
| Claude/Gemini/Perplexity 전체 지원 | 각 서비스 DOM 변화 대응 필요 |
| 파일 업로드 검사 | PDF/Excel/Word 파싱, OCR, malware scanning 범위가 큼 |
| 데스크톱 앱/모바일 통제 | Endpoint agent 또는 MDM 범위 |
| 완전한 CASB/SASE 대체 | 목표가 아님 |
| Local LLM context classifier | MVP는 rule-based classifier로 고정. 로컬 LLM은 GPU/메모리/모델 배포 부담이 있어 후속 |
| Multi-workspace | single-tenant 안정화 이후 |
| OIDC/SAML | self-host MVP 이후 |
| SIEM/SOAR 연동 | 운영 환경 연동은 후속 |
| Managed SaaS | MVP는 오픈소스 self-hosted에 집중 |

## 1.7 제외 범위

- 직원의 모든 브라우징 내용 감시
- ChatGPT 답변 내용 저장 또는 검사
- 원문 prompt 검색 기능
- 관리자 원문 복구 기능
- 보안 사고 조사용 forensic 원문 보관
- 법적 책임 판정 자동화
- 이미지, 음성, 첨부파일 입력 검사
- 외부 LLM API에 raw_prompt를 보내는 기능
- enterprise DLP/CASB 기능 전체 대체
- 서버 운영 대행 또는 클라우드 호스팅

## 1.8 주요 사용자 시나리오

| 시나리오 | 입력/상황 | 결과 |
|---|---|---|
| 관리자가 서버를 직접 띄움 | `docker compose up -d`, `/setup` 접속 | 첫 ADMIN 생성, 기본 policy 생성, dashboard 진입 |
| 일반회원이 가입하고 Extension 연결 | 이메일/비밀번호/초대 코드, API URL | ChatGPT 전송 직전 분석 가능 |
| CS 담당자가 고객 메일을 붙여넣음 | 고객사명, 이메일, 전화번호, 장애 내역 | EMAIL/PHONE/CUSTOMER_INFO 탐지, Mask 권고 |
| 개발자가 API key 포함 로그 입력 | `ghp_`, `AKIA`, DB URL | Secret 탐지, Block |
| 관리자가 대시보드 확인 | 기간, 사용자/부서, 탐지 유형 필터 | 원문 없이 위험 이벤트 수, 차단 수, 마스킹 수 표시 |

## 1.9 성공 KPI

설치 성공률은 핵심 KPI에서 제외한다. Docker, OS, CPU architecture, reverse proxy, 브라우저 배포 방식에 따라 설치 실패 원인이 제품 가치와 무관하게 달라질 수 있기 때문이다. 대신 설치는 release gate와 smoke test로 관리한다.

| KPI | 정의 | MVP 목표 |
|---|---|---|
| 초기 설정 완료 시간 | Docker Compose 실행 후 첫 관리자 생성까지 | 10분 이내 |
| Extension 연결 성공률 | API URL과 계정 설정 후 `/auth/me` 및 `/prompts/analyze` 호출 성공 | 테스트 환경 95% 이상 |
| 위험 프롬프트 탐지율 | 전체 분석 요청 중 risk >= 30 비율 | 측정 가능해야 함 |
| 마스킹 적용률 | Mask 제안 중 사용자가 마스킹 적용한 비율 | 30% 이상 초기 목표 |
| 평균 분석 지연 | Extension 전송 인터셉트 후 결과 표시까지 p95 | regex/secret/rule 기반 1.5초 이하 |
| False Positive 비율 | 사용자가 오탐 피드백한 위험 이벤트 비율 | 20% 이하 초기 목표 |
| raw_prompt 저장 위반 | DB/log/error tracking에 raw_prompt가 남은 건수 | 0건 필수 |
| 사용자별 통계 가시성 | 사용자별 이벤트 유형/횟수 목록과 차트 제공 | 필수 화면 제공 |
| OSS 기여 가능성 | detector rule/test 추가 방법 문서화 | CONTRIBUTING.md 존재 |

## 1.10 리스크와 한계

| 리스크 | 영향 | 대응 |
|---|---|---|
| self-host 운영 부담 | 사용자가 설치/업데이트를 어려워할 수 있음 | Docker Compose, health check, migration 자동화, 명확한 README |
| 서버 공개 노출 | 잘못 노출된 self-host 서버가 공격받을 수 있음 | 기본 admin bootstrap 잠금, rate limit, TLS reverse proxy 문서 |
| 오픈소스 공급망 위험 | dependency 취약점, 악성 PR 가능 | lockfile, Dependabot, CI, 코드 리뷰, release signing |
| 브라우저 우회 | Extension 미설치/비활성화 시 탐지 불가 | 사용자 고지, 관리 브라우저 배포 문서, 한계 명시 |
| DOM 변경 | ChatGPT UI 변경 시 입력창 감지 실패 | selector fallback, MutationObserver, fixture E2E |
| 직접 필터 오설정 | regex 오탐/미탐, catastrophic backtracking, 과도한 차단 | regex validation, timeout, dry-run, audit log, versioning |
| 오탐 | 업무 방해, 우회 사용 유도 | 피드백, policy tuning, confidence threshold |
| 미탐 | 민감정보 유출 가능 | secret scanner 강화, FN 테스트셋 운영 |
| Local LLM 후속 도입 부담 | GPU/메모리/모델 업데이트/로그 통제가 필요 | MVP 제외, 후속에서 local-only runtime과 logging off 검증 |
| 감시 인식 | 사용자 반발 | 원문 미저장 고지, 관리자도 원문 조회 불가 |
| 기업 제품 대비 기능 부족 | 대형 고객에게 경쟁력 낮음 | 목표를 OSS/self-host/투명성/가벼움으로 제한 |

# 2. SRS: Software Requirements Specification

## 2.1 기능 요구사항

### 2.1.1 OSS Packaging 및 Setup 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-001 | P0 | 프로젝트는 공개 repo 기준으로 `apps/api`, `apps/dashboard`, `apps/extension`, `packages`, `docs`, `infra`를 분리해야 한다. | fresh clone 후 구조가 README와 일치한다. | TC-001 |
| FR-002 | P0 | Docker Compose로 API, dashboard, PostgreSQL, Redis를 실행할 수 있어야 한다. | `docker compose up` 후 `/healthz` 200 | TC-002 |
| FR-003 | P0 | `.env.example`에는 모든 필수 환경변수가 포함되어야 하며 실제 secret은 포함하지 않는다. | env validation 통과, secret scan 통과 | TC-003 |
| FR-004 | P0 | 최초 실행 전 `/setup/status`는 `setup_required=true`를 반환해야 한다. | fresh DB에서 true | TC-004 |
| FR-005 | P0 | 최초 관리자는 `/setup/bootstrap`에서 1회만 생성 가능해야 한다. | setup 완료 후 재호출 409/403 | TC-005 |
| FR-006 | P0 | setup 완료 시 기본 workspace, 기본 policy, 첫 ADMIN user, registration setting이 생성되어야 한다. | DB seed 검증 | TC-006 |
| FR-007 | P0 | DB migration은 fresh install과 재시작 모두에서 안전하게 적용되어야 한다. | migration 재실행 idempotent | TC-007 |
| FR-008 | P0 | setup 완료 후 bootstrap endpoint는 잠기고 audit log에 SETUP_COMPLETED가 남아야 한다. | endpoint 잠금 및 audit 확인 | TC-008 |

### 2.1.2 회원가입/Auth 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-021 | P0 | 시스템은 ADMIN과 USER 역할을 구분해야 한다. | USER는 admin API 접근 시 403 | TC-021 |
| FR-022 | P0 | 일반회원은 초대 코드 또는 워크스페이스 코드로 회원가입할 수 있어야 한다. | 유효 코드로 가입 200, 잘못된 코드 400/403 | TC-022 |
| FR-023 | P0 | ADMIN은 초대 코드를 생성, 만료, 폐기할 수 있어야 한다. | invite CRUD 정상 동작 | TC-023 |
| FR-024 | P0 | 회원가입 방식은 INVITE_ONLY, WORKSPACE_CODE, OPEN_SIGNUP 중 하나로 설정 가능해야 한다. | 설정별 가입 허용/차단 검증 | TC-024 |
| FR-025 | P0 | OPEN_SIGNUP은 기본값으로 비활성화해야 한다. | fresh setup default 확인 | TC-025 |
| FR-026 | P0 | 사용자는 email/password로 로그인하고 access/refresh token을 발급받아야 한다. | login/refresh 정상 | TC-026 |
| FR-027 | P0 | 비밀번호는 Argon2id 또는 bcrypt로 hash 저장해야 한다. | DB에 평문 비밀번호 없음 | TC-027 |
| FR-028 | P0 | refresh token 원문은 저장하지 않고 hash만 저장해야 한다. | refresh_tokens 테이블 원문 없음 | TC-028 |
| FR-029 | P1 | 회원 승인 대기 모드를 지원할 수 있다. | 가입 후 PENDING, admin 승인 시 ACTIVE | TC-029 |
| FR-030 | P1 | Extension pairing code를 1회용·짧은 TTL로 발급할 수 있다. | 사용 후 재사용 불가 | TC-030 |

### 2.1.3 Chrome Extension 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-101 | P0 | Extension은 사용자가 설정한 self-hosted API base URL에 연결해야 한다. | API URL 저장 후 `/auth/me` 호출 성공 | TC-101 |
| FR-102 | P0 | Extension은 관리 대상 AI 서비스 도메인에서만 content script를 활성화해야 한다. | 비대상 도메인에서 DOM 접근/전송 인터셉트 없음 | TC-102 |
| FR-103 | P0 | Extension은 ChatGPT 웹 입력 영역을 textarea 또는 contenteditable 기준으로 탐지해야 한다. | fixture 기준 입력창 탐지 성공 | TC-103 |
| FR-104 | P0 | Extension은 전송 버튼 클릭 이벤트를 서버 분석 완료 전까지 보류해야 한다. | 분석 전 전송되지 않음 | TC-104 |
| FR-105 | P0 | Extension은 Enter 또는 단축키 기반 전송 이벤트를 서버 분석 완료 전까지 보류해야 한다. | Enter 전송 보류 | TC-105 |
| FR-106 | P0 | Extension은 입력 텍스트, AI 서비스명, policy version, extension version을 `/prompts/analyze`로 전송해야 한다. | request body schema 일치 | TC-106 |
| FR-107 | P0 | Extension은 Allow/Warn/Mask/Block action을 처리해야 한다. | 각 action E2E 통과 | TC-107~TC-110 |
| FR-108 | P0 | Extension은 masking 적용 시 입력창 내용을 API가 반환한 masked_prompt로 치환해야 한다. | 원 민감값 미포함 | TC-111 |
| FR-109 | P0 | Extension은 같은 prompt에 대해 승인된 전송이 중복 분석/중복 전송되지 않도록 해야 한다. | double-submit 없음 | TC-112 |
| FR-110 | P0 | Extension은 서버에서 받은 selector/service config를 주기적으로 갱신해야 한다. | config 변경 후 재배포 없이 반영 | TC-113 |
| FR-111 | P0 | Extension은 최초 실행 또는 연결 화면에서 저장/미저장 정보를 고지해야 한다. | notice 표시 | TC-114 |
| FR-112 | P1 | Extension은 서버 timeout 시 정책에 따라 fail-closed 또는 fail-open-with-warning을 적용해야 한다. | 정책별 timeout 동작 검증 | TC-115 |
| FR-113 | P1 | Extension은 사용자가 오탐 피드백을 제출할 수 있게 해야 한다. | feedback API 기록 | TC-116 |
| FR-114 | P1 | Extension은 짧은 TTL의 decision cache를 사용할 수 있다. | TTL 내 중복 호출 감소 | TC-117 |
| FR-115 | P1 | Extension은 서버 연결 상태와 마지막 policy sync 시간을 표시해야 한다. | options/status UI 확인 | TC-118 |
| FR-116 | P1 | Extension은 local pre-scan을 수행하더라도 최종 decision은 서버 정책 기준을 따라야 한다. | 서버 decision 우선 | TC-119 |

### 2.1.4 Analyze API 및 탐지 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-201 | P0 | `/prompts/analyze`는 인증된 Extension 요청만 처리해야 한다. | 인증 없는 요청 401 | TC-201 |
| FR-202 | P0 | Analyze API는 raw_prompt를 요청 body로 받아 분석하되 DB와 일반 로그에 저장하지 않아야 한다. | DB/log scan에서 원문 없음 | TC-202 |
| FR-203 | P0 | Analyze API는 요청마다 event_id와 prompt_hash를 생성해야 한다. | 응답과 이벤트 로그에 존재 | TC-203 |
| FR-204 | P0 | Analyze API는 regex detector, secret detector, custom filter detector, rule-based context classifier를 실행해야 한다. | detector 결과 통합 | TC-204 |
| FR-205 | P0 | Analyze API는 policy version 기준으로 risk score와 action을 결정해야 한다. | policy별 action 차이 | TC-205 |
| FR-206 | P0 | Analyze API는 detection type별 count, confidence, severity, source를 반환해야 한다. | response schema 검증 | TC-206 |
| FR-207 | P0 | Analyze API는 action이 Warn/Mask/Block이면 user_message를 반환해야 한다. | UI 표시 가능 | TC-207 |
| FR-208 | P0 | Analyze API는 masked_prompt를 반환할 때 원문 민감값이 남지 않도록 해야 한다. | 테스트 민감값 미포함 | TC-208 |
| FR-209 | P0 | 요청 길이가 최대치를 초과하면 413과 machine-readable error code를 반환해야 한다. | max length 초과 시 413 | TC-209 |
| FR-210 | P0 | `client_request_id`는 idempotency/debug에 사용하되 원문을 포함하면 안 된다. | 중복 요청 처리 및 원문 미포함 | TC-210 |
| FR-211 | P0 | policy mismatch가 감지되면 응답에 latest_policy_version을 포함해야 한다. | 오래된 policy 요청 시 최신 버전 반환 | TC-211 |
| FR-212 | P0 | MVP는 외부 LLM API를 호출하지 않아야 한다. | 네트워크 mock에서 외부 LLM 호출 0건 | TC-212 |
| FR-213 | P1 | rule-based context classifier 실패 시 structured detector 결과만으로 partial decision을 반환해야 한다. | partial_result=true | TC-213 |
| FR-214 | P2 | Local LLM context classifier를 도입할 수 있으나, raw_prompt는 로컬 프로세스 밖으로 전송하지 않아야 한다. | local-only runtime 검증 | TC-214 |

### 2.1.5 Detector, 직접 필터, Scoring, Masking 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-301 | P0 | 이메일 주소를 탐지해야 한다. | 유효 이메일 EMAIL 탐지 | TC-301 |
| FR-302 | P0 | 한국 휴대폰/유선번호를 탐지해야 한다. | 010, 02 번호 PHONE 탐지 | TC-302 |
| FR-303 | P0 | 주민등록번호 형식 및 checksum 검증을 수행해야 한다. | 유효 dummy RRN만 high confidence | TC-303 |
| FR-304 | P0 | 카드번호 후보는 Luhn algorithm으로 검증해야 한다. | Luhn 유효 번호만 탐지 | TC-304 |
| FR-305 | P1 | 사업자등록번호 후보와 checksum을 탐지해야 한다. | 유효 사업자번호 탐지 | TC-305 |
| FR-306 | P1 | 금액, 할인율, 계약기간 후보를 탐지해야 한다. | “3억 원”, “15% 할인” 탐지 | TC-306 |
| FR-311 | P0 | GitHub classic/fine-grained token prefix를 탐지해야 한다. | `ghp_`, `github_pat_` 탐지 | TC-311 |
| FR-312 | P0 | AWS access key id 패턴을 탐지해야 한다. | `AKIA`, `ASIA` 탐지 | TC-312 |
| FR-313 | P0 | JWT 구조를 탐지해야 한다. | 3-part base64url 구조 탐지 | TC-313 |
| FR-314 | P0 | PEM private key block을 탐지해야 한다. | private key block 탐지 | TC-314 |
| FR-315 | P0 | DB connection string을 탐지해야 한다. | postgres/mysql/mongodb URI 탐지 | TC-315 |
| FR-316 | P1 | entropy 기반 generic secret 후보를 탐지해야 한다. | 고엔트로피 문자열 탐지 | TC-316 |
| FR-317 | P1 | `.env` 형태의 key=value secret 후보를 탐지해야 한다. | `PASSWORD=`, `SECRET=` 후보 탐지 | TC-317 |
| FR-321 | P0 | 계약정보 문맥을 rule 기반 CONTRACT_INFO로 분류해야 한다. | 계약금액/위약금 문장 탐지 | TC-321 |
| FR-322 | P0 | 고객정보 문맥을 rule 기반 CUSTOMER_INFO로 분류해야 한다. | 고객사+담당자+문의 조합 탐지 | TC-322 |
| FR-323 | P0 | 영업기밀/내부전략 문맥을 TRADE_SECRET 또는 INTERNAL_STRATEGY로 분류해야 한다. | 가격정책/출시계획 분류 | TC-323 |
| FR-324 | P0 | 한국 현지화 rule은 별도 rule pack으로 versioning 가능해야 한다. | rule_pack_version 저장 | TC-324 |
| FR-325 | P1 | 낮은 confidence 결과는 AMBIGUOUS로 반환해야 한다. | threshold 미만 강한 차단 근거 제외 | TC-325 |
| FR-331 | P1 | ADMIN은 사용자 정의 regex 필터를 생성할 수 있어야 한다. | 생성 후 analyze에 반영 | TC-331 |
| FR-332 | P1 | ADMIN은 사용자 정의 keyword 필터를 생성할 수 있어야 한다. | keyword 탐지 반영 | TC-332 |
| FR-333 | P1 | 사용자 정의 필터에는 label, severity, action_override, placeholder, enabled가 있어야 한다. | 저장/조회 schema 검증 | TC-333 |
| FR-334 | P1 | regex 필터는 저장 전 syntax, 길이, timeout 안전성을 검증해야 한다. | 위험 regex 거절 | TC-334 |
| FR-335 | P1 | 필터 테스트 API는 샘플 원문을 저장하지 않아야 한다. | DB/log scan 원문 없음 | TC-335 |
| FR-336 | P1 | 사용자 정의 필터 변경은 versioning되고 audit log에 기록되어야 한다. | before/after 기록 | TC-336 |
| FR-337 | P1 | 필터별 탐지 건수는 dashboard에서 metadata로 집계 가능해야 한다. | filter stats 표시 | TC-337 |
| FR-338 | P1 | 사용자 정의 필터가 기본 secret/PII detector보다 낮은 우선순위로 overlap 처리되어야 한다. | overlap 결과 검증 | TC-338 |
| FR-401 | P0 | risk score는 0~100 정수로 반환해야 한다. | 모든 응답 범위 내 | TC-401 |
| FR-402 | P0 | secret 탐지는 기본 high 또는 critical severity를 부여해야 한다. | GITHUB_TOKEN risk >= 80 | TC-402 |
| FR-403 | P0 | 주민등록번호 또는 카드번호 유효 탐지는 risk >= 80으로 산정해야 한다. | valid RRN/CARD Block | TC-403 |
| FR-404 | P0 | EMAIL/PHONE 단독 탐지는 count와 policy에 따라 Warn 또는 Mask를 산정해야 한다. | 기본 policy에서 Warn/Mask | TC-404 |
| FR-405 | P0 | context classifier 결과는 confidence와 severity에 따라 가중해야 한다. | CONTRACT_INFO risk 반영 | TC-405 |
| FR-406 | P0 | service risk weight와 custom filter action_override를 적용해야 한다. | 동일 prompt risk/action 차이 | TC-406 |
| FR-407 | P0 | risk score 구간별 action을 policy 기준으로 결정해야 한다. | threshold mapping 검증 | TC-407 |
| FR-408 | P0 | 위험도 계산 방식과 기본 점수의 이유를 문서화해야 한다. | technical design에 rationale 존재 | TC-408 |
| FR-501 | P0 | EMAIL 값은 `[이메일]`로 치환해야 한다. | 원 이메일 미포함 | TC-501 |
| FR-502 | P0 | PHONE 값은 `[전화번호]`로 치환해야 한다. | 원 전화번호 미포함 | TC-502 |
| FR-503 | P0 | RRN 값은 `[주민등록번호]`로 치환해야 한다. | 원 주민번호 미포함 | TC-503 |
| FR-504 | P0 | API key/token 값은 `[API_KEY]` 또는 구체 placeholder로 치환해야 한다. | 원 token 미포함 | TC-504 |
| FR-505 | P0 | DB URL은 `[DB_CONNECTION_STRING]`으로 치환해야 한다. | username/password/host 미포함 | TC-505 |
| FR-506 | P0 | 동일 민감값이 여러 번 등장하면 모두 치환해야 한다. | 모든 occurrence 치환 | TC-506 |
| FR-507 | P1 | context-only 민감 문장은 정책에 따라 문장 전체 또는 핵심 엔티티를 치환해야 한다. | 계약금액/고객사명 치환 | TC-507 |
| FR-508 | P1 | 사용자 정의 필터는 설정된 placeholder로 치환되어야 한다. | custom placeholder 반영 | TC-508 |

### 2.1.6 Event Logging, Dashboard, Admin 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| FR-601 | P0 | Analyze API는 raw_prompt 없이 analysis event를 저장해야 한다. | events 테이블 raw_prompt 없음 | TC-601 |
| FR-602 | P0 | event에는 user_id, ai_service, detection_types, risk_score, action, policy_version, timestamp를 저장해야 한다. | 필수 컬럼 저장 | TC-602 |
| FR-603 | P0 | event에는 prompt_hash를 HMAC 기반으로 저장해야 한다. | 같은 workspace+prompt 동일 hash | TC-603 |
| FR-604 | P0 | detection 상세에는 민감값 원문을 저장하지 않아야 한다. | value/raw_value 컬럼 없음 | TC-604 |
| FR-605 | P0 | 대시보드는 기간별 이벤트 수, 차단 수, 마스킹 수를 표시해야 한다. | summary API/UI 일치 | TC-605 |
| FR-606 | P0 | 대시보드는 사용자/부서별 통계를 표시해야 한다. | stats API/UI 일치 | TC-606 |
| FR-607 | P0 | 대시보드는 탐지 유형별 통계를 표시해야 한다. | detection type stats 일치 | TC-607 |
| FR-608 | P0 | 관리자 이벤트 목록에서 원문 prompt는 조회할 수 없어야 한다. | UI/API 원문 필드 없음 | TC-608 |
| FR-609 | P0 | 대시보드는 사용자별 이벤트 유형/횟수를 목록으로 제공해야 한다. | user risk table 정확 | TC-609 |
| FR-610 | P0 | 대시보드는 사용자별 이벤트 유형/횟수를 시각화해야 한다. | chart와 API 값 일치 | TC-610 |
| FR-611 | P0 | 사용자 상세 화면은 해당 사용자의 action 분포, detection type 분포, 추이를 metadata만으로 표시해야 한다. | raw_prompt 없음 | TC-611 |
| FR-612 | P0 | ADMIN은 사용자 목록을 조회하고 상태를 변경할 수 있어야 한다. | active/disabled 변경 가능 | TC-612 |
| FR-613 | P0 | ADMIN은 가입 방식을 설정할 수 있어야 한다. | registration setting 변경 | TC-613 |
| FR-614 | P1 | ADMIN은 metadata CSV export를 수행할 수 있다. | 원문 없는 CSV만 다운로드 | TC-614 |
| FR-701 | P0 | ADMIN은 현재 policy를 조회할 수 있어야 한다. | GET /policies/current 200 | TC-701 |
| FR-702 | P1 | ADMIN은 policy threshold와 detector enable/disable을 변경할 수 있어야 한다. | 새 policy version 생성 | TC-702 |
| FR-703 | P1 | policy, 가입 설정, 사용자 정의 필터 변경은 audit log에 기록해야 한다. | before/after 저장 | TC-703 |
| FR-704 | P1 | Extension은 policy version mismatch 시 최신 policy를 재조회해야 한다. | latest_policy_version 반환 | TC-704 |
| FR-705 | P1 | ADMIN은 서버 health/degraded 상태를 볼 수 있어야 한다. | dashboard status 표시 | TC-705 |
| FR-706 | P1 | ADMIN은 retention_days를 설정할 수 있어야 한다. | 만료 이벤트 삭제/집계 | TC-706 |

## 2.2 비기능·보안·개인정보·운영 요구사항

| ID | 우선순위 | 요구사항 | 검증 기준 | 관련 TC |
|---|---:|---|---|---|
| NFR-001 | P0 | Fresh clone 기준 로컬 개발환경이 문서대로 실행되어야 한다. 이는 KPI가 아니라 release gate이다. | onboarding smoke test 통과 | TC-901 |
| NFR-002 | P0 | Analyze API p95 latency는 regex/secret/custom filter/rule classifier 기준 500ms 이하이어야 한다. | 성능 테스트 p95 <= 500ms | TC-902 |
| NFR-003 | P0 | Dashboard 30일 summary 및 사용자별 통계 API p95 latency는 2초 이하이어야 한다. | 성능 테스트 p95 <= 2s | TC-903 |
| NFR-004 | P0 | Extension UI overlay는 ChatGPT 기본 입력 기능을 영구적으로 깨뜨리지 않아야 한다. | overlay unmount 후 입력 가능 | TC-904 |
| NFR-005 | P0 | 기본 설치 모드는 single-tenant workspace로 동작해야 한다. | workspace isolation 정상 | TC-905 |
| NFR-006 | P0 | 사용자 정의 regex 필터는 개별 실행 timeout과 길이 제한을 가져야 한다. | catastrophic regex 차단 | TC-906 |
| NFR-007 | P1 | detector rule, custom filter, policy는 versioning 가능해야 한다. | event에 version 연결 | TC-907 |
| SEC-001 | P0 | setup bootstrap은 setup 완료 후 비활성화되어야 한다. | 재호출 409/403 | TC-005 |
| SEC-002 | P0 | production 배포용 TLS reverse proxy 문서를 제공해야 한다. | HTTPS deployment guide 존재 | TC-811 |
| SEC-003 | P0 | API 인증 토큰은 만료시간을 가져야 한다. | 만료 토큰 401 | TC-812 |
| SEC-004 | P0 | Admin API는 ADMIN role만 접근 가능해야 한다. | USER token 403 | TC-813 |
| SEC-005 | P0 | raw_prompt는 application log, access log, error log에 기록하지 않아야 한다. | 로그 스캔 테스트 통과 | TC-814 |
| SEC-006 | P0 | prompt_hash HMAC key는 환경변수/secret manager로 주입하고 repo에 저장하지 않는다. | repo secret scan 통과 | TC-815 |
| SEC-007 | P0 | rate limiting을 적용해 Analyze/Auth API 남용을 방지해야 한다. | 초과 요청 429 | TC-816 |
| SEC-008 | P0 | CORS는 설정된 Extension/dashboard origin으로 제한해야 한다. | 미허용 origin 차단 | TC-817 |
| SEC-009 | P0 | 비밀번호와 refresh token은 안전한 hash로 저장해야 한다. | 평문 없음 | TC-027, TC-028 |
| SEC-010 | P0 | MVP는 외부 LLM API 호출을 금지해야 한다. | 외부 LLM endpoint 호출 없음 | TC-212 |
| PRV-001 | P0 | raw_prompt 저장을 금지해야 한다. | DB schema/log scan 원문 없음 | TC-601, TC-814 |
| PRV-002 | P0 | 저장 이벤트는 위험 유형, count, risk, action 중심으로 최소화해야 한다. | detection value 미저장 | TC-604 |
| PRV-003 | P0 | 관리자 UI는 prompt 원문 조회·복구 기능을 제공하지 않아야 한다. | UI/API endpoint 없음 | TC-608 |
| PRV-004 | P0 | 사용자에게 무엇을 검사하고 무엇을 저장하지 않는지 고지해야 한다. | 최초 실행/도움말 표시 | TC-114 |
| PRV-005 | P1 | 로그 보존 기간은 policy로 설정 가능해야 한다. | retention_days 적용 | TC-706 |
| PRV-006 | P1 | user_id는 설정에 따라 pseudonymous ID로 저장 가능해야 한다. | pseudonymization 적용 | TC-821 |
| PRV-007 | P0 | 외부 telemetry는 기본 비활성화해야 한다. | fresh setup에서 outbound telemetry 없음 | TC-822 |
| OPS-001 | P0 | API health check endpoint를 제공해야 한다. | `/healthz` 200 | TC-831 |
| OPS-002 | P0 | DB migration은 컨테이너 시작 시 안전하게 적용 가능해야 한다. | fresh DB/restart 모두 성공 | TC-832 |
| OPS-003 | P0 | detector latency, error rate, action count metric을 수집해야 한다. | monitoring metric 조회 가능 | TC-833 |
| OPS-004 | P0 | Extension selector 변경은 서버 정책 또는 원격 설정으로 배포 가능해야 한다. | Extension 재배포 없이 변경 | TC-834 |
| OPS-005 | P1 | retention job을 주기적으로 실행해야 한다. | 만료 이벤트 삭제/집계 | TC-835 |

# 3. User Stories & Acceptance Criteria

## 3.1 Self-host 관리자

### US-001: 서버 초기 설정

As a self-host admin, I want to run the server and create the first admin account, so that I can operate PromptGuard without a managed SaaS.

| AC ID | Given | When | Then | 관련 요구사항 | 관련 TC |
|---|---|---|---|---|---|
| AC-001-01 | fresh clone 상태다 | README대로 Docker Compose를 실행한다 | API, dashboard, DB, Redis가 실행된다 | FR-002 | TC-002 |
| AC-001-02 | setup_required=true 상태다 | 첫 관리자 정보를 입력한다 | ADMIN user와 기본 policy가 생성된다 | FR-004~FR-006 | TC-004~TC-006 |
| AC-001-03 | setup이 완료됐다 | `/setup/bootstrap`을 다시 호출한다 | 추가 admin 생성이 차단된다 | SEC-001 | TC-005 |

### US-002: 일반회원 가입 관리

As an admin, I want members to sign up with an invite or workspace code, so that my team can use the extension without me creating every account manually.

| AC ID | Given | When | Then | 관련 요구사항 | 관련 TC |
|---|---|---|---|---|---|
| AC-002-01 | ADMIN으로 로그인되어 있다 | 초대 코드를 생성한다 | 만료 시간이 있는 invite가 생성된다 | FR-023 | TC-022 |
| AC-002-02 | 유효 초대 코드가 있다 | 일반회원이 회원가입한다 | USER role로 계정이 생성된다 | FR-022 | TC-021 |
| AC-002-03 | OPEN_SIGNUP이 비활성화되어 있다 | 초대 코드 없이 가입한다 | 가입이 거부된다 | FR-024~FR-025 | TC-023, TC-024 |

### US-003: Shadow AI 위험 현황 확인

As an admin, I want to see weekly AI prompt risk events by user, department, and detection type, so that I can manage Shadow AI risk without reading prompt content.

| AC ID | Given | When | Then | 관련 요구사항 | 관련 TC |
|---|---|---|---|---|---|
| AC-003-01 | ADMIN으로 로그인되어 있다 | Overview 화면을 연다 | 이번 주 이벤트 수, 차단 수, 마스킹 수가 표시된다 | FR-605 | TC-605 |
| AC-003-02 | 이벤트가 여러 사용자/부서에 존재한다 | Stats를 본다 | 사용자/부서별 이벤트 count와 평균 risk가 표시된다 | FR-606 | TC-606 |
| AC-003-03 | 이벤트가 존재한다 | Risk Events 목록을 본다 | raw_prompt 또는 masked_prompt 원문은 표시되지 않는다 | FR-608, PRV-003 | TC-608 |

## 3.2 일반회원/개발자

| Story | Given | When | Then | 관련 요구사항 |
|---|---|---|---|---|
| US-004 Extension 연결 | 사용자가 로그인했다 | Extension에 API URL을 입력한다 | 서버 연결 상태가 표시된다 | FR-101 |
| US-005 개인정보 경고 | ChatGPT 입력창에 이메일과 전화번호가 있다 | Enter를 누른다 | 전송 전 경고 또는 마스킹 패널 표시 | FR-104~FR-108, FR-301~FR-302 |
| US-006 Secret 차단 | 입력 prompt에 GitHub token이 있다 | 전송 버튼을 누른다 | action Block, 전송 차단 | FR-107, FR-311, FR-402 |
| US-007 Detector 기여 | contributor가 rule을 추가한다 | unit/privacy test를 작성한다 | detector corpus와 privacy regression 통과 | NFR-008, PRV-001 |

---
# 4. Technical Design Document

## 4.1 전체 시스템 아키텍처

```text
[User Chrome Browser]
  └─ PromptGuard Chrome Extension
      ├─ content_script.ts
      │   ├─ ChatGPT DOM detector
      │   ├─ input extractor
      │   ├─ send event interceptor
      │   ├─ overlay UI mount
      │   └─ masked text injector
      ├─ service_worker.ts
      │   ├─ self-hosted API URL config
      │   ├─ auth token storage
      │   ├─ policy/config cache
      │   └─ analyze API client
      └─ options/onboarding UI

        HTTPS JSON
          │
          ▼
[Self-hosted PromptGuard Server]
  ├─ Setup module
  │   ├─ first admin bootstrap
  │   ├─ workspace initialization
  │   └─ default policy seed
  ├─ Auth module
  │   ├─ admin/user signup
  │   ├─ invite/workspace code
  │   ├─ login/refresh
  │   └─ RBAC
  ├─ Prompt Analyze controller
  ├─ Detection pipeline
  │   ├─ Regex detector
  │   ├─ Secret detector
  │   ├─ Context classifier adapter
  │   ├─ Risk scoring engine
  │   └─ Masking engine
  ├─ Event logging service
  ├─ Policy service
  ├─ Dashboard query service
  ├─ User management service
  └─ Audit service

          │
          ▼
[Self-hosted Data Stores]
  ├─ PostgreSQL: workspace, users, invites, policies, events, audit logs
  ├─ Redis: short TTL config/cache/rate limit
  ├─ Local secrets/env: HMAC keys, JWT secrets
  └─ Metrics/Logs: no raw_prompt logging

          │
          ▼
[Admin Dashboard]
  ├─ Setup
  ├─ Overview
  ├─ Risk Events
  ├─ User Management
  ├─ Invites & Registration
  ├─ Policies
  ├─ Detection Type Stats
  └─ Server Health
```

## 4.2 Repository 구조

```text
promptguard-k-ai/
  apps/
    api/
    dashboard/
    extension/
  packages/
    detector-core/
    policy-core/
    shared-types/
    privacy-test-utils/
  infra/
    docker/
    compose/
    reverse-proxy-examples/
  docs/
    install.md
    extension-setup.md
    admin-guide.md
    privacy-design.md
    threat-model.md
    contributing.md
  tests/
    e2e/
    corpus/
    privacy-regression/
  .github/
    workflows/
  docker-compose.yml
  .env.example
  README.md
  LICENSE
```

## 4.3 주요 기술 선택지와 trade-off

| 영역 | 권장 선택 | 대안 | Trade-off |
|---|---|---|---|
| API 서버 | FastAPI 또는 NestJS | Go | FastAPI는 detector/ML 후속 확장에 유리. NestJS는 dashboard/extension과 TS 공유에 유리 |
| Dashboard | React + TypeScript | Next.js | self-host SPA로 충분. Next.js는 auth/SSR 운영 복잡도 증가 |
| Extension | TypeScript + Manifest V3 | Plain JS | TS는 안정성 높음. MV3는 Chrome 정책 준수 필요 |
| DB | PostgreSQL | SQLite | PostgreSQL은 운영/통계에 적합. SQLite는 개인용 설치가 쉬움 |
| Cache/Rate limit | Redis | in-memory | Docker Compose 기준 Redis 권장. 단일 프로세스 MVP는 in-memory 가능 |
| Secret scanning | 자체 rule + Gitleaks rule 참고 | TruffleHog 연동 | 검증된 scanner는 정확도 높지만 무거울 수 있음 |
| Context classifier | deterministic local rule engine | Local LLM은 P2 | MVP는 rule-based만 사용한다. 외부 LLM API는 제외한다. Local LLM은 self-host 자원 부담 때문에 후속으로 둔다 |
| Auth | 자체 email/password + invite | OIDC | OSS 설치 용이성 우선. OIDC는 P2 |
| License | AGPL-3.0 또는 Apache-2.0 | MIT | AGPL은 SaaS fork 견제, Apache는 adoption 우수. DEC 필요 |

## 4.4 Setup 및 가입 흐름

### 4.4.1 첫 관리자 bootstrap

1. 관리자가 repo clone
2. `.env` 생성
3. `docker compose up -d`
4. `https://<server>/setup` 접속
5. `/setup/status`가 `setup_required=true`인지 확인
6. 이메일/비밀번호/워크스페이스명을 입력
7. `/setup/bootstrap` 호출
8. default workspace, ADMIN user, default policy, registration settings 생성
9. setup lock 활성화
10. Dashboard로 redirect

### 4.4.2 일반회원 가입 흐름

| 방식 | 기본값 | 설명 |
|---|---:|---|
| INVITE_ONLY | 기본 활성 | ADMIN이 생성한 invite code로만 가입 |
| WORKSPACE_CODE | 선택 | 팀 공통 가입 코드를 알고 있으면 가입 |
| OPEN_SIGNUP | 기본 비활성 | 서버 URL을 아는 누구나 가입. public internet 배포에서는 비권장 |

회원가입 결과:

- 기본 role: USER
- 기본 status: ACTIVE 또는 PENDING. 설정에 따라 결정
- department/team 필드는 선택
- 사용자 email은 login 식별자로 사용
- 관리자는 사용자 disabled, role 변경, invite 폐기 가능

### 4.4.3 Extension 연결 흐름

1. 사용자가 Extension options를 연다.
2. API base URL 입력
3. 이메일/비밀번호 로그인 또는 dashboard에서 복사한 pairing code 입력
4. access/refresh token 저장
5. `/auth/me`, `/policies/current`, `/config/extension` 호출
6. ChatGPT 페이지에서 전송 직전 검사 활성화

권장 보안:

- token은 `chrome.storage.local`에 저장
- refresh token rotation 적용
- Extension origin 제한
- pairing code는 P1로 구현 가능

## 4.5 Chrome Extension 구조

### 4.5.1 Content Script 책임

- 관리 대상 도메인에서만 실행
- ChatGPT 입력창 탐지
- 전송 버튼 click, Enter keydown, form submit 이벤트 인터셉트
- prompt text 추출
- service worker에 analyze 요청 위임
- 응답 action에 따라 UI overlay 표시
- masked_prompt 입력창 치환
- 원래 전송 이벤트 재실행

### 4.5.2 Service Worker 책임

- self-hosted API base URL 관리
- 인증 token 저장 및 refresh
- `/prompts/analyze` 호출
- timeout 및 retry 제어
- policy/config 캐싱
- Extension runtime message broker

### 4.5.3 DOM 탐지 전략

1. 서버에서 내려받은 selector config 우선 사용
2. fallback selector 사용
   - `textarea`
   - `[contenteditable="true"]`
   - submit button 후보
3. MutationObserver로 입력창 재렌더링 감지
4. 입력창 후보가 여러 개면 visible, focus, bounding box, text length 기준으로 scoring
5. selector 실패 시 사용자에게 불필요한 경고를 반복하지 않고 telemetry metadata만 기록한다.

## 4.6 API 서버 구조

```text
src/
  setup/
  auth/
  users/
  invites/
  prompts/
    analyze.controller
    analyze.service
  detectors/
    regex.detector
    secret.detector
    custom-filter.detector
    rule-context-classifier
  scoring/
    risk-scoring.service
  masking/
    masking.service
  events/
    event-logging.service
    event-query.service
  policies/
    policy.service
  custom-filters/
    custom-filter.controller
    custom-filter.service
  dashboard/
    dashboard.service
  audit/
  common/
    redaction.logger
    errors
    schemas
```

## 4.7 탐지 파이프라인

| 단계 | 입력 | 처리 | 출력 |
|---|---|---|---|
| 1. Validate | request body | schema, max length, auth 검증 | normalized request |
| 2. Normalize | raw_prompt | Unicode normalization, line ending normalize | normalized_prompt |
| 3. Regex scan | normalized_prompt | PII 정규식, checksum | regex detections |
| 4. Secret scan | normalized_prompt | token pattern, entropy, URI scan | secret detections |
| 5. Custom filter scan | normalized_prompt | ADMIN이 설정한 regex/keyword filter 실행. timeout 적용 | custom filter detections |
| 6. Rule context classify | normalized_prompt | 한국 현지화 rule pack, keyword/window/context score | context detections |
| 7. Merge | all detections | overlap resolve, severity merge, rule priority 적용 | merged detections |
| 8. Score | detections + policy | risk score/action 산정 | decision |
| 9. Mask | prompt + detections | placeholder 치환 | masked_prompt |
| 10. Log | metadata only | raw_prompt 제외 저장 | event_id |
| 11. Respond | decision | UI message 포함 응답 | AnalyzeResponse |

MVP에서는 외부 LLM API를 호출하지 않는다. Context 분류는 deterministic local rule로 구현하고, Local LLM은 P2에서 별도 runtime/logging 통제를 설계한 뒤 추가한다.

## 4.8 위험도 계산 방식

```text
risk_score = min(100,
  max_detection_score
  + count_bonus
  + context_bonus
  + custom_filter_bonus
  + service_risk_weight
  + policy_override_bonus
  - confidence_penalty
)
```

| Detection Type | Base Score | Severity | 기본 이유 |
|---|---:|---|---|
| PRIVATE_KEY | 98 | critical | 노출 즉시 시스템 접근권 탈취 가능성이 큼 |
| AWS_ACCESS_KEY | 95 | critical | 클라우드 자원·데이터 접근으로 이어질 수 있음 |
| GITHUB_TOKEN | 90 | critical | 소스코드·CI/CD·secret 접근으로 이어질 수 있음 |
| RRN_VALID | 90 | critical | 한국 고유식별정보로 유출 영향이 큼 |
| DB_CONNECTION_STRING | 85 | critical | DB 접근정보가 포함될 가능성이 큼 |
| CARD_NUMBER_VALID | 85 | critical | 결제정보 유출 위험이 큼 |
| JWT | 80 | high | 세션/권한 위임 정보일 가능성이 큼 |
| TRADE_SECRET | 80 | critical | 비공개 전략·영업기밀 유출 위험 |
| INTERNAL_STRATEGY | 75 | high | 출시계획·가격정책 등 비공개 정보 가능성 |
| CONTRACT_INFO | 70 | high | 계약금액·위약금·NDA 등 민감 업무정보 가능성 |
| CUSTOMER_INFO | 55 | medium | 고객 식별정보와 업무맥락 결합 시 위험 상승 |
| PHONE | 30 | medium | 단독으로는 중간 위험, count/context 결합 시 상승 |
| EMAIL | 25 | low | 단독으로는 낮은 위험, 대량·고객문맥 결합 시 상승 |
| MONEY_AMOUNT | 25 | low | 공개 정보일 수도 있으므로 context와 결합 필요 |
| SOURCE_CODE | 30 | medium | 공개 코드와 내부 코드 구분 필요 |
| BUSINESS_NUMBER | 25 | low | 공개 가능성이 있어 단독 차단 근거로 약함 |
| CUSTOM_FILTER | filter 설정값 | 설정값 | 관리자가 조직/팀 맥락에 맞게 지정 |

### 4.8.1 점수 설정 이유

1. **즉시 악용 가능한 인증정보는 80점 이상**으로 둔다. API key, private key, DB URL은 실제 침해로 직결될 수 있어 사용자 확인만으로 허용하기 어렵다.
2. **한국 고유식별정보와 결제정보는 critical**로 둔다. 주민등록번호와 카드번호는 형식 검증이 통과하면 오탐 가능성이 낮고 유출 영향이 크다.
3. **이메일·전화번호는 단독 차단하지 않는다.** 업무에서 흔히 등장하므로 단독으로 Block하면 오탐이 많다. 대신 count, 고객문맥, custom filter와 결합하면 Warn/Mask로 올라간다.
4. **context-only 결과는 보수적으로 처리한다.** rule 기반 문맥 분류는 오탐 가능성이 있으므로 기본은 Mask 중심이며, secret/PII와 결합하거나 confidence가 높을 때만 Block에 가까워진다.
5. **count_bonus는 상한을 둔다.** 긴 문서에서 반복된 낮은 위험 항목이 과도하게 100점으로 치솟지 않게 최대 +15로 제한한다.
6. **custom filter는 관리자 의도를 반영한다.** 단, 사용자 정의 regex는 오탐과 DoS 위험이 있으므로 저장 전 검증, 실행 timeout, audit log가 필요하다.
7. **정책 변경 가능성을 전제로 한다.** 기본 점수는 안전한 출발점이며, 실제 FP/FN 평가 결과에 따라 policy version으로 조정한다.

| 요소 | 계산 기준 |
|---|---|
| max_detection_score | detection base score 중 최대값 |
| count_bonus | 동일/다른 detection count에 따라 최대 +15 |
| context_bonus | rule context confidence >= 0.8이면 +10 |
| custom_filter_bonus | 필터 severity/action_override에 따라 +0~30 |
| service_risk_weight | AI 서비스별 0~10. MVP ChatGPT 기본 0 |
| policy_override_bonus | 특정 부서/서비스/유형 강화 시 +0~20 |
| confidence_penalty | confidence < 0.6인 context-only 결과는 -20 |

기본 action mapping:

| Risk Score | Action | UI |
|---:|---|---|
| 0~29 | Allow | 조용히 전송 |
| 30~59 | Warn | 경고 후 사용자 확인 시 전송 |
| 60~79 | Mask | 마스킹 적용 권고. 원문 전송은 정책에 따라 제한 |
| 80~100 | Block | 원문 전송 차단 |

## 4.9 관리자 대시보드 구조

| 화면 | 기능 | MVP |
|---|---|---|
| Setup | 첫 관리자 생성, 서버 초기화 | 필수 |
| Overview | 기간별 이벤트 수, 차단 수, 마스킹 수, risk trend | 필수 |
| Risk Events | 이벤트 목록, 필터, 상세 metadata | 필수 |
| User Risk Stats | 사용자별 이벤트 유형/횟수 목록, action 분포, detection type heatmap/bar chart | 필수 |
| User Detail | 특정 사용자의 기간별 이벤트 추이, 탐지 유형, action 분포. 원문 없음 | 필수 |
| Users | 사용자 목록, role/status 변경 | 필수 |
| Invites & Registration | invite 생성/폐기, 가입 방식 설정 | 필수 |
| Detection Type Stats | 유형별 추이 | 필수 |
| Custom Filters | 사용자 정의 필터 생성/수정/비활성화, dry-run 테스트 | P1 |
| Policies | threshold, detector enable, retention 설정 | P1 |
| Server Health | API/DB/Redis/classifier 상태 | P1 |
| Audit Logs | 관리자 행위 조회 | P1 |

사용자별 이벤트 목록과 시각화는 다음 조건을 따른다.

- 기본 컬럼: 사용자, 부서, 전체 이벤트 수, Warn/Mask/Block 수, top detection types, 마지막 이벤트 시각
- 차트: 사용자별 stacked action bar, detection type heatmap, 기간별 trend
- drill-down: 사용자 상세는 metadata만 표시하며 raw_prompt, masked_prompt, detected value를 표시하지 않는다.
- 필터: 기간, 사용자, 부서, AI 서비스, detection type, action, risk score

원문 조회 금지 UX:

- 이벤트 상세에는 “원문 프롬프트는 저장되지 않습니다” 문구 표시
- 원문 보기 버튼 없음
- 검색어로 prompt 내용 검색 불가
- 필터는 metadata 기준만 제공
- CSV export도 metadata만 포함
- 관리자 원문 복구 기능은 제공하지 않음

## 4.10 배포 구조

```text
Admin machine or VPS
  ├─ nginx/caddy/traefik reverse proxy
  ├─ promptguard-api container
  ├─ promptguard-dashboard container
  ├─ postgres container or managed postgres
  └─ redis container
```

최소 운영 체크리스트:

- `APP_URL`, `API_BASE_URL` 설정
- `JWT_SECRET`, `PROMPT_HASH_SECRET` 생성
- HTTPS reverse proxy 설정
- DB volume backup 설정
- admin bootstrap 완료 후 `/setup/bootstrap` 잠금 확인
- OPEN_SIGNUP 비활성화 확인
- outbound telemetry 비활성화 확인

---

# 5. API Specification

## 5.1 공통 규칙

### Base URL

```text
https://<self-hosted-domain>/api/v1
```

### Authentication

```http
Authorization: Bearer <access_token>
X-PromptGuard-Client: chrome-extension | dashboard
X-PromptGuard-Extension-Version: 0.3.0
```

### 공통 Error Response

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

## 5.2 GET /setup/status

```json
{
  "setup_required": true,
  "setup_completed_at": null,
  "version": "0.3.0"
}
```

## 5.3 POST /setup/bootstrap

최초 관리자 생성 전용. setup 완료 후에는 비활성화된다.

```json
{
  "workspace_name": "My Team",
  "admin_email": "admin@example.com",
  "admin_password": "strong-password",
  "admin_display_name": "Admin"
}
```

Response:

```json
{
  "workspace": { "id": "wks_001", "name": "My Team" },
  "admin": { "id": "user_001", "email": "admin@example.com", "role": "ADMIN" },
  "policy": { "version": "v0.3.0-default" },
  "setup_completed": true
}
```

## 5.4 POST /auth/register

일반회원 가입.

```json
{
  "email": "member@example.com",
  "password": "strong-password",
  "display_name": "Member",
  "invite_code": "pg_invite_xxx",
  "workspace_code": null
}
```

Response:

```json
{
  "user": {
    "id": "user_123",
    "email": "member@example.com",
    "role": "USER",
    "status": "ACTIVE"
  }
}
```

## 5.5 POST /auth/login

```json
{
  "email": "admin@example.com",
  "password": "string"
}
```

Response:

```json
{
  "access_token": "jwt_access_token",
  "refresh_token": "opaque_refresh_token",
  "expires_in": 3600,
  "token_type": "Bearer",
  "user": {
    "id": "user_123",
    "workspace_id": "wks_001",
    "email": "admin@example.com",
    "role": "ADMIN",
    "department_id": "dept_security"
  }
}
```

## 5.6 POST /auth/refresh

```json
{ "refresh_token": "opaque_refresh_token" }
```

## 5.7 GET /auth/me

```json
{
  "id": "user_123",
  "workspace_id": "wks_001",
  "email": "employee@example.com",
  "role": "USER",
  "status": "ACTIVE",
  "department": {
    "id": "dept_cs",
    "name": "Customer Success"
  },
  "policy_version": "v0.3.0-default"
}
```

## 5.8 POST /invites

Admin 전용.

```json
{
  "role": "USER",
  "expires_in_hours": 168,
  "max_uses": 10
}
```

Response:

```json
{
  "invite_id": "inv_001",
  "invite_code": "pg_invite_xxx",
  "role": "USER",
  "expires_at": "2026-05-26T12:00:00+09:00",
  "max_uses": 10,
  "used_count": 0
}
```

## 5.9 GET /config/extension

Extension이 selector와 policy cache를 가져온다.

```json
{
  "api_base_url": "https://promptguard.example.com/api/v1",
  "policy_version": "v0.3.0-default",
  "ai_service_configs": [
    {
      "service": "CHATGPT",
      "domains": ["chatgpt.com", "chat.openai.com"],
      "selectors": {
        "input": ["textarea", "[contenteditable='true']"],
        "send_button": ["button[data-testid='send-button']"]
      }
    }
  ],
  "timeout_ms": 3000
}
```

## 5.10 POST /prompts/analyze

Request:

```json
{
  "prompt": {
    "text": "홍길동 고객님, 010-1234-5678, gildong@example.com 문의 요약해줘",
    "input_method": "ENTER",
    "content_length": 57
  },
  "context": {
    "ai_service": "CHATGPT",
    "ai_service_domain": "chatgpt.com",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "0.3.0",
    "browser": "Chrome",
    "locale": "ko-KR"
  },
  "policy": { "version": "v0.3.0-default" },
  "client_request_id": "crq_01H..."
}
```

Response:

```json
{
  "event_id": "evt_20260519_000123",
  "request_id": "req_abc123",
  "decision": {
    "risk_score": 72,
    "risk_level": "HIGH",
    "action": "Mask",
    "user_message": "고객 개인정보로 보이는 항목이 포함되어 있습니다. 이메일 1건, 전화번호 1건이 탐지되었습니다. 마스킹 후 전송하시겠습니까?",
    "requires_justification": true,
    "allow_original_send": false
  },
  "detections": [
    { "type": "PHONE", "label": "전화번호", "count": 1, "severity": "medium", "confidence": 0.99, "source": "regex" },
    { "type": "EMAIL", "label": "이메일", "count": 1, "severity": "low", "confidence": 0.99, "source": "regex" }
  ],
  "masked_prompt": "홍길동 고객님, [전화번호], [이메일] 문의 요약해줘",
  "policy": {
    "version": "v0.3.0-default",
    "latest_version": "v0.3.0-default"
  },
  "partial_result": false
}
```

금지 필드:

- user_id request body
- workspace_id request body
- raw prompt response echo
- detected raw values

## 5.11 기타 API

| Method/Path | 권한 | 목적 | 원문 반환 여부 |
|---|---|---|---|
| POST /events/{event_id}/feedback | USER | 오탐/업무상 필요 피드백 | 없음 |
| GET /events | ADMIN | 이벤트 목록 | 없음 |
| GET /events/{event_id} | ADMIN | 이벤트 상세 metadata | 없음 |
| GET /dashboard/summary | ADMIN | 대시보드 전체 집계 | 없음 |
| GET /dashboard/users | ADMIN | 사용자별 이벤트 유형/횟수 목록 | 없음 |
| GET /dashboard/users/{user_id}/stats | ADMIN | 사용자 상세 통계와 시각화 데이터 | 없음 |
| GET /dashboard/detection-types | ADMIN | 탐지 유형별 통계 | 없음 |
| GET /admin/users | ADMIN | 사용자 목록 | 없음 |
| PATCH /admin/users/{user_id} | ADMIN | role/status/department 변경 | 없음 |
| POST /invites | ADMIN | 초대 코드 생성 | 없음 |
| DELETE /invites/{invite_id} | ADMIN | 초대 코드 폐기 | 없음 |
| GET /policies/current | ADMIN/USER | 현재 policy 조회 | 없음 |
| PUT /policies/current | ADMIN | 새 policy version 생성 | 없음 |
| GET /custom-filters | ADMIN | 사용자 정의 필터 목록 | 없음 |
| POST /custom-filters | ADMIN | 사용자 정의 필터 생성 | 없음 |
| PATCH /custom-filters/{filter_id} | ADMIN | 사용자 정의 필터 수정/비활성화 | 없음 |
| POST /custom-filters/test | ADMIN | 필터 dry-run. 샘플 원문 저장 금지 | 없음 |
| GET /audit-logs | ADMIN | 관리자 행위 로그 조회 | 없음 |
| GET /healthz | Public or internal | 서버 상태 | 없음 |

# 6. Data Model / ERD

## 6.1 ERD 개요

```text
server_instances 1 ── 1 workspaces               # MVP single-tenant
workspaces 1 ── N departments
workspaces 1 ── N users
workspaces 1 ── N invites
workspaces 1 ── N registration_settings
workspaces 1 ── N policies
policies 1 ── N policy_versions
workspaces 1 ── N custom_filter_rules
custom_filter_rules 1 ── N custom_filter_versions
users 1 ── N refresh_tokens
users 1 ── N analysis_events
analysis_events 1 ── N event_detections
analysis_events 1 ── N event_feedback
users 1 ── N audit_logs
workspaces 1 ── N ai_service_configs
```

## 6.2 핵심 테이블

### server_instances

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | ins_ prefix |
| instance_id | varchar(64) | N | unique | 설치 인스턴스 식별자. 외부 전송 금지 |
| setup_completed | boolean | N | idx | bootstrap 완료 여부 |
| setup_completed_at | timestamptz | Y |  | 완료 시각 |
| version | varchar(50) | N |  | 현재 app version |
| created_at | timestamptz | N |  | 생성일 |
| updated_at | timestamptz | N |  | 수정일 |

### workspaces

MVP는 single workspace를 기본으로 한다. P2에서 multi-workspace 가능.

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | wks_ prefix |
| name | varchar(255) | N |  | 워크스페이스명 |
| slug | varchar(100) | N | unique | workspace slug |
| status | varchar(30) | N | idx | ACTIVE, SUSPENDED |
| prompt_hash_key_id | varchar(255) | Y |  | secret reference. 실제 key 저장 금지 |
| workspace_code_hash | varchar(255) | Y |  | 가입 코드 hash |
| created_at | timestamptz | N |  | 생성일 |
| updated_at | timestamptz | N |  | 수정일 |

### departments

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | dept_ prefix |
| workspace_id | varchar(36) | N | FK, idx | workspace 격리 |
| name | varchar(255) | N | idx | 부서/팀명 |
| created_at | timestamptz | N |  | 생성일 |
| updated_at | timestamptz | N |  | 수정일 |

### users

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | user_ prefix |
| workspace_id | varchar(36) | N | FK, idx | workspace 격리 |
| department_id | varchar(36) | Y | FK, idx | 부서 |
| email | varchar(320) | N | unique(workspace,email) | login 식별자 |
| password_hash | varchar(255) | N |  | Argon2id/bcrypt |
| display_name | varchar(255) | Y |  | UI 표시명 |
| role | varchar(30) | N | idx | USER, ADMIN |
| status | varchar(30) | N | idx | ACTIVE, PENDING, DISABLED |
| created_at | timestamptz | N |  |  |
| updated_at | timestamptz | N |  |  |

### refresh_tokens

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | rt_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| user_id | varchar(36) | N | FK, idx |  |
| token_hash | varchar(255) | N | unique | refresh token 원문 저장 금지 |
| expires_at | timestamptz | N | idx | 만료 |
| revoked_at | timestamptz | Y |  | 폐기 |
| created_at | timestamptz | N |  |  |

### registration_settings

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | reg_ prefix |
| workspace_id | varchar(36) | N | FK, unique |  |
| mode | varchar(50) | N |  | INVITE_ONLY, WORKSPACE_CODE, OPEN_SIGNUP |
| require_admin_approval | boolean | N |  | 기본 false |
| default_role | varchar(30) | N |  | USER |
| updated_by | varchar(36) | Y | FK | admin user |
| updated_at | timestamptz | N |  |  |

### invites

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | inv_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| code_hash | varchar(255) | N | unique | invite 원문 저장 금지 |
| role | varchar(30) | N |  | USER/ADMIN. MVP는 USER만 허용 권장 |
| max_uses | integer | N |  | 사용 가능 횟수 |
| used_count | integer | N |  | 사용 횟수 |
| expires_at | timestamptz | Y | idx | 만료 |
| revoked_at | timestamptz | Y |  | 폐기 |
| created_by | varchar(36) | N | FK | ADMIN |
| created_at | timestamptz | N |  |  |

### policies

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | pol_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| active_version_id | varchar(36) | Y | FK | 현재 활성 version |
| created_at | timestamptz | N |  |  |
| updated_at | timestamptz | N |  |  |

### policy_versions

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | polv_ prefix |
| policy_id | varchar(36) | N | FK, idx |  |
| workspace_id | varchar(36) | N | FK, idx | query 단순화 |
| version | varchar(50) | N | unique(policy,version) | v0.3.0-default |
| thresholds | jsonb | N |  | allow/warn/mask/block |
| detector_config | jsonb | N |  | regex/secret/custom/rule context on/off |
| scoring_config | jsonb | N |  | base score, weights |
| retention_days | integer | N |  | 기본 180 |
| timeout_behavior | varchar(50) | N |  | FAIL_CLOSED_FOR_HIGH_RISK 등 |
| created_by | varchar(36) | Y | FK | users.id |
| created_at | timestamptz | N |  |  |

### custom_filter_rules

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | cfr_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| name | varchar(255) | N | idx | 관리자 표시명 |
| type | varchar(30) | N | idx | REGEX, KEYWORD |
| enabled | boolean | N | idx | 활성 여부 |
| active_version_id | varchar(36) | Y | FK | 현재 버전 |
| created_by | varchar(36) | N | FK | ADMIN |
| created_at | timestamptz | N |  |  |
| updated_at | timestamptz | N |  |  |

### custom_filter_versions

필터 pattern 자체는 정책 정보이므로 저장 가능하지만, 테스트 입력 샘플이나 탐지된 원문값은 저장하지 않는다.

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | cfv_ prefix |
| filter_id | varchar(36) | N | FK, idx |  |
| workspace_id | varchar(36) | N | FK, idx |  |
| version | integer | N | unique(filter,version) | 1부터 증가 |
| pattern | text | N |  | regex pattern 또는 keyword. 탐지 대상 원문 아님 |
| label | varchar(100) | N |  | 예: 내부프로젝트명 |
| severity | varchar(30) | N |  | low~critical |
| action_override | varchar(50) | Y |  | null, Warn, Mask, Block |
| placeholder | varchar(100) | Y |  | 예: [내부프로젝트] |
| flags | jsonb | Y |  | case_sensitive 등 |
| created_by | varchar(36) | N | FK | ADMIN |
| created_at | timestamptz | N |  |  |

### ai_service_configs

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | aisvc_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| service_name | varchar(100) | N | idx | CHATGPT |
| domains | jsonb | N |  | 허용 도메인 배열 |
| selectors | jsonb | N |  | input/send button selector |
| service_risk_weight | integer | N |  | 0~10 |
| enabled | boolean | N | idx | 활성 여부 |
| updated_at | timestamptz | N |  |  |

### analysis_events

raw_prompt 저장 금지. 이 테이블에는 원문 또는 마스킹된 전체 prompt 컬럼을 만들지 않는다.

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | evt_ prefix |
| workspace_id | varchar(36) | N | FK, idx | tenant/workspace 격리 |
| user_id | varchar(36) | N | FK, idx | 사용자 |
| department_id | varchar(36) | Y | FK, idx | 부서 |
| ai_service | varchar(100) | N | idx | CHATGPT |
| ai_service_domain | varchar(255) | N | idx | hostname만 저장 |
| input_method | varchar(50) | N |  | ENTER, BUTTON_CLICK |
| prompt_hash | varchar(128) | N | idx | HMAC-SHA256 |
| prompt_length | integer | N |  | 길이만 저장 |
| detection_types | jsonb | N | gin | label 배열. 값 원문 금지 |
| max_severity | varchar(30) | N | idx | low/medium/high/critical |
| risk_score | integer | N | idx | 0~100 |
| risk_level | varchar(30) | N | idx | LOW~CRITICAL |
| action | varchar(50) | N | idx | Allow/Warn/Mask/Block |
| policy_version | varchar(50) | N | idx | 분석 시점 정책 |
| detector_rule_versions | jsonb | Y |  | rule pack/custom filter version metadata |
| partial_result | boolean | N |  | fallback 여부 |
| client_request_id | varchar(100) | Y | idx | idempotency/debug용. 원문 없음 |
| created_at | timestamptz | N | idx | timestamp |

금지 컬럼:

- raw_prompt
- prompt_text
- masked_prompt
- detected_values
- span_text

### event_detections

민감 원문값 저장 금지.

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | det_ prefix |
| event_id | varchar(36) | N | FK, idx |  |
| workspace_id | varchar(36) | N | FK, idx |  |
| detection_type | varchar(100) | N | idx | EMAIL, API_KEY 등 |
| label | varchar(100) | N |  | 한국어 표시명 또는 custom label |
| source | varchar(50) | N | idx | regex, secret, custom_filter, rule_context |
| custom_filter_id | varchar(36) | Y | FK, idx | custom filter 결과일 때만 |
| count | integer | N |  | 원문값 없이 count만 |
| severity | varchar(30) | N | idx | low~critical |
| confidence | numeric(4,3) | N |  | 0~1 |
| created_at | timestamptz | N |  |  |

### event_feedback

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | fb_ prefix |
| event_id | varchar(36) | N | FK, idx |  |
| workspace_id | varchar(36) | N | FK, idx |  |
| user_id | varchar(36) | N | FK, idx |  |
| feedback_type | varchar(50) | N | idx | FALSE_POSITIVE, BUSINESS_JUSTIFICATION |
| comment | text | Y |  | UI/서버 redaction 적용. 원문 입력 금지 고지 |
| user_selected_action | varchar(50) | Y |  | SEND_MASKED 등 |
| created_at | timestamptz | N | idx |  |

### audit_logs

| Column | Type | Nullable | Index | 설명 |
|---|---|---:|---|---|
| id | varchar(36) | N | PK | aud_ prefix |
| workspace_id | varchar(36) | N | FK, idx |  |
| actor_user_id | varchar(36) | Y | FK, idx | setup 전에는 null 가능 |
| action | varchar(100) | N | idx | SETUP_COMPLETED, USER_REGISTERED, POLICY_UPDATED, CUSTOM_FILTER_UPDATED 등 |
| resource_type | varchar(100) | N |  | USER, POLICY, INVITE, EVENT, CUSTOM_FILTER |
| resource_id | varchar(36) | Y | idx | 대상 |
| before_json | jsonb | Y |  | 민감정보 금지 |
| after_json | jsonb | Y |  | 민감정보 금지 |
| ip_address | inet | Y |  | 관리자 접속 IP |
| user_agent | text | Y |  |  |
| created_at | timestamptz | N | idx |  |

# 7. Security & Privacy Design

## 7.1 핵심 원칙

1. raw_prompt는 저장하지 않는다.
2. raw_prompt는 API request 처리 메모리에서만 존재한다.
3. detector 결과에는 원문값이 아닌 type/count/confidence/severity만 저장한다.
4. prompt_hash는 HMAC-SHA256으로 생성해 원문 복원이 불가능해야 한다.
5. 관리자도 사용자 prompt 원문을 조회할 수 없다.
6. self-hosted라도 기본 outbound telemetry는 비활성화한다.
7. setup bootstrap endpoint는 최초 설정 후 잠근다.
8. MVP는 외부 LLM API를 호출하지 않는다. Local LLM은 P2 후속 기능으로만 검토한다.

## 7.2 Raw prompt 미저장 통제

| 위치 | 통제 |
|---|---|
| DB | raw_prompt/prompt_text/masked_prompt 컬럼 금지 |
| Application log | request body logging 비활성화 |
| Access log | body 미기록. path, status, latency만 기록 |
| Error tracking | exception context에서 prompt 제거 |
| Metrics | prompt 관련 label 금지 |
| Audit log | metadata만 저장 |
| Local LLM trace | P2에서만 해당. local runtime의 prompt trace 저장 금지 또는 비활성화 |

구현 방법:

- `RedactedLogger`만 사용하도록 lint rule 설정
- controller 진입 직후 raw request body logging middleware 비활성화
- exception handler에서 `prompt`, `text`, `raw_prompt` key 자동 redaction
- CI에서 seeded secret/PII 문자열이 로그와 DB dump에 남는지 검사
- migration lint에서 금지 컬럼명 검사

## 7.3 Self-host 보안

| 영역 | 요구 |
|---|---|
| Bootstrap | setup 완료 후 bootstrap API 비활성화 |
| Secret | `.env.example`에는 dummy만 제공. 실제 secret은 설치 시 생성 |
| Password | Argon2id 또는 bcrypt hash 저장 |
| HTTPS | production deployment guide에서 reverse proxy/TLS 권장 |
| CORS | dashboard origin, extension origin만 허용 |
| Rate limit | login/register/analyze API에 적용 |
| Registration | OPEN_SIGNUP 기본 비활성화 |
| Backup | DB backup에 raw_prompt는 없어야 하나, metadata도 개인정보이므로 보호 필요 |
| Release | checksum/signature 제공 권장 |

## 7.4 인증/인가

| Role | 권한 |
|---|---|
| USER | Extension analyze 요청, 본인 feedback 제출 |
| ADMIN | dashboard 조회, 사용자 관리, invite 관리, policy 조회/수정, audit log 조회 |

인가 규칙:

- JWT claim의 `workspace_id`, `user_id`, `role`을 신뢰한다.
- 클라이언트 request body의 user_id/workspace_id는 받지 않는다.
- 모든 query는 `workspace_id`로 scoping한다.
- 원문 조회 권한은 어떤 role에도 없음.

## 7.5 사용자 고지 정책

Extension 첫 실행 또는 dashboard help에서 다음을 명확히 고지한다.

- 외부 AI 입력 직전 보안 검사가 수행된다.
- 원문 prompt는 저장되지 않는다.
- 저장되는 정보는 위험 유형, 위험도, 조치 결과, 시각, AI 서비스명, 사용자/팀 식별자이다.
- 관리자는 원문을 볼 수 없다.
- 오탐 피드백 또는 업무상 필요 사유를 제출할 수 있다.
- 서버 운영자는 메타데이터 DB와 계정 정보를 보호해야 한다.

---

# 8. Threat Model

## 8.1 주요 자산

| Asset ID | 자산 | 설명 |
|---|---|---|
| A-001 | raw_prompt | 사용자가 AI에 보내려는 원문. 가장 민감. 저장 금지 |
| A-002 | masked_prompt | 마스킹된 텍스트. 응답에서만 사용 |
| A-003 | event metadata | 위험 유형, risk, action, user/department |
| A-004 | prompt_hash HMAC key | prompt_hash 생성용 비밀키 |
| A-005 | auth token | Extension/Admin 인증 토큰 |
| A-006 | policy config | 차단 기준, selector, detector 설정 |
| A-007 | dashboard data | workspace별 위험 통계 |
| A-008 | setup bootstrap state | 첫 admin 생성 권한 |
| A-009 | invite/workspace code | 회원가입 권한 |
| A-010 | source code/release artifact | 오픈소스 공급망 자산 |

## 8.2 STRIDE 분석

| TM ID | STRIDE | 위협 | 대상 자산 | 완화책 | MVP 여부 | 관련 TC |
|---|---|---|---|---|---|---|
| TM-001 | Spoofing | 공격자가 다른 사용자 ID로 analyze 요청 | A-003, A-005 | JWT에서 user_id 획득, body user_id 불허 | 반드시 | TC-803 |
| TM-002 | Spoofing | 악성 origin이 API 호출 | A-003 | CORS, token 검증 | 반드시 | TC-817 |
| TM-003 | Tampering | setup 완료 후 bootstrap 재호출 | A-008 | setup lock, unique admin bootstrap guard | 반드시 | TC-005 |
| TM-004 | Tampering | 가입 코드 brute force | A-009 | code hash 저장, rate limit, expiry | 반드시 | TC-816 |
| TM-005 | Information Disclosure | raw_prompt가 로그에 남음 | A-001 | RedactedLogger, log scan CI | 반드시 | TC-814 |
| TM-006 | Information Disclosure | DB에 원문 컬럼 추가 | A-001 | schema review, migration lint | 반드시 | TC-601 |
| TM-007 | Information Disclosure | 관리자 원문 조회 | A-001 | 원문 미저장, UI/API 미제공 | 반드시 | TC-608 |
| TM-008 | Information Disclosure | prompt_hash brute force | A-004 | HMAC + workspace key | 반드시 | TC-603 |
| TM-009 | Denial of Service | Analyze/Auth API 대량 호출 | API | rate limit, max length | 반드시 | TC-816 |
| TM-010 | Elevation of Privilege | USER가 admin API 접근 | A-007 | role check | 반드시 | TC-813 |
| TM-011 | Tampering | ChatGPT DOM 변경으로 감지 실패 | Extension | selector fallback, remote config, E2E | 반드시 | TC-103 |
| TM-012 | Information Disclosure | 후속 Local LLM runtime이 prompt trace를 저장 | A-001 | MVP 제외, P2 도입 시 local-only 및 trace off 검증 | 후속 | TC-214 |
| TM-017 | Denial of Service | 사용자 정의 regex가 catastrophic backtracking 유발 | API | regex validation, timeout, length limit | 일부 우회 가능 | P1 | TC-334, TC-906 |
| TM-013 | Tampering | 악성 PR이 로그에 prompt 출력 추가 | A-010, A-001 | privacy regression CI, code review | 반드시 | TC-814 |
| TM-014 | Misconfiguration | OPEN_SIGNUP으로 공개 서버 가입 남용 | A-009 | 기본 비활성, warning UI | 반드시 | TC-024 |

## 8.3 MVP에서 반드시 막아야 할 위협

- raw_prompt 저장 또는 로그 노출
- setup bootstrap 재호출
- 인증 없는 Analyze API 호출
- USER의 관리자 API 접근
- Secret/API key 포함 prompt 원문 전송
- 주민등록번호/카드번호 등 고위험 개인정보 원문 전송
- prompt_hash key 노출
- 잘못된 가입 코드로 회원가입
- 악성/부주의한 코드 변경으로 privacy 원칙 훼손

---

# 9. Test Strategy

## 9.1 테스트 목표

- self-host fresh install이 문서대로 성공하는지 검증한다.
- 첫 관리자 가입과 일반회원 가입 흐름을 자동 검증한다.
- 핵심 보안 원칙인 raw_prompt 미저장을 자동 검증한다.
- regex/secret/context detector의 정확도와 회귀를 관리한다.
- Extension이 ChatGPT 전송 직전 개입하는지 E2E로 검증한다.
- API schema, auth, RBAC, workspace isolation, dashboard aggregation을 검증한다.
- 오픈소스 기여자가 rule을 추가해도 privacy CI가 깨지지 않는지 검증한다.

## 9.2 테스트 레벨

| 레벨 | 목적 | 범위 | 도구 예시 | 성공 기준 |
|---|---|---|---|---|
| Install Test | fresh install 검증 | Docker Compose, setup wizard | shell script, Playwright | README 그대로 성공 |
| Unit Test | 함수 단위 정확성 | detector, scoring, masking | Jest/Vitest, Pytest | P0 detector 100% |
| Integration Test | 모듈 연동 | API + DB + policy + auth | Testcontainers | 주요 API happy/error path 통과 |
| E2E Test | 사용자 흐름 검증 | Extension + fixture page + API | Playwright + Chrome Extension | Allow/Warn/Mask/Block 검증 |
| Security Test | 인증/인가/정보노출 검증 | API, logs, DB | custom scripts, ZAP | P0 보안 테스트 100% |
| Privacy Regression | 원문 미저장 검증 | DB/log/error dump | seeded scan | 원문 0건 |
| Performance Test | 지연/처리량 검증 | Analyze API, dashboard | k6, Locust | NFR 기준 충족 |
| OSS Contribution Test | PR 품질 검증 | lint, test, dependency scan | GitHub Actions | main branch 보호 |

## 9.3 FP/FN 테스트 데이터셋

| Dataset | 최소 개수 | 구성 |
|---|---:|---|
| PII positive | 100 | 이메일, 전화번호, 주민번호, 카드번호 |
| PII negative | 100 | 숫자, 주문번호, 일반 날짜, 이메일 유사 문자열 |
| Secret positive | 100 | GitHub/AWS/JWT/private key/DB URL dummy |
| Secret negative | 100 | UUID, hash, 일반 base64 |
| Korean business context positive | 100 | 계약, 영업기밀, 내부전략, 고객문의 |
| Korean business context negative | 100 | 공개 보도자료, 일반 교육자료, 샘플 데이터 |

---

# 10. TDD Test Case Specification

TDD는 요구사항 누락을 막기 위한 핵심 산출물이다. 아래 테스트는 세 번의 관점으로 재검토했다.

1. **제품 흐름 관점:** setup → 가입 → Extension 연결 → analyze → dashboard까지 끊기지 않는가.
2. **보안·프라이버시 관점:** raw_prompt, masked_prompt, detection value가 저장·노출되지 않는가.
3. **오픈소스 운영 관점:** self-host 설치, 직접 필터, migration, 문서, 기여 흐름이 검증되는가.

## 10.1 Setup/Auth 테스트

| TC ID | 제목 | Given | When | Then | 관련 요구사항 |
|---|---|---|---|---|---|
| TC-001 | repo 구조 검증 | fresh clone | inspect | apps/packages/docs/infra 존재 | FR-001 |
| TC-002 | Docker Compose 실행 | fresh clone/env | compose up | healthz 200 | FR-002 |
| TC-003 | env example 검증 | .env.example | validation | 필수 env 포함, secret 없음 | FR-003 |
| TC-004 | setup status | fresh DB | GET /setup/status | setup_required=true | FR-004 |
| TC-005 | bootstrap 1회 제한 | setup 완료 상태 | POST /setup/bootstrap | 409/403 | FR-005, SEC-001 |
| TC-006 | bootstrap seed | fresh DB | POST /setup/bootstrap | workspace/admin/policy/settings 생성 | FR-006 |
| TC-007 | migration idempotent | migration 완료 DB | restart/migrate | 중복 오류 없음 | FR-007 |
| TC-008 | setup audit | bootstrap 성공 | audit 조회 | SETUP_COMPLETED 기록 | FR-008 |
| TC-021 | role 분리 | USER token | admin API | 403 | FR-021 |
| TC-022 | invite 가입 | 유효 invite | POST /auth/register | USER 생성 | FR-022 |
| TC-023 | invite 생성/폐기 | ADMIN token | POST/DELETE /invites | 정상 처리 | FR-023 |
| TC-024 | 가입 방식별 제어 | mode별 설정 | register | 정책대로 허용/거부 | FR-024 |
| TC-025 | OPEN_SIGNUP 기본 비활성 | fresh setup | settings 조회 | OPEN_SIGNUP=false | FR-025 |
| TC-026 | login/refresh | 유효 계정 | login/refresh | token 발급 | FR-026 |
| TC-027 | password hash | 회원가입 | DB inspect | 평문 비밀번호 없음 | FR-027, SEC-009 |
| TC-028 | refresh token hash | 로그인 | DB inspect | refresh token 원문 없음 | FR-028, SEC-009 |
| TC-029 | 승인 대기 | approval mode on | register | status=PENDING | FR-029 |
| TC-030 | pairing code 1회성 | code 발급 | 2회 사용 | 1회 성공, 2회 실패 | FR-030 |

## 10.2 Extension 테스트

| TC ID | 제목 | Given | When | Then | 관련 요구사항 |
|---|---|---|---|---|---|
| TC-101 | self-host API 연결 | API URL/token | options 저장 | /auth/me 성공 | FR-101 |
| TC-102 | 대상 도메인 활성화 | URL chatgpt.com | page load | detector 시작 | FR-102 |
| TC-103 | 입력창 탐지 | textarea/contenteditable | detector 실행 | element 반환 | FR-103 |
| TC-104 | 버튼 클릭 전송 보류 | prompt 존재 | click | analyze 전 submit 없음 | FR-104 |
| TC-105 | Enter 전송 보류 | prompt focus | Enter | analyze 전 전송 없음 | FR-105 |
| TC-106 | analyze request 생성 | prompt/context | analyze 호출 | schema 일치, user_id body 없음 | FR-106 |
| TC-107 | Allow 처리 | action=Allow | 응답 수신 | 전송 재개 | FR-107 |
| TC-108 | Warn 처리 | action=Warn | 응답 수신 | 경고 후 확인 전송 | FR-107 |
| TC-109 | Mask 처리 | action=Mask | 마스킹 클릭 | masked_prompt 치환 | FR-107~FR-108 |
| TC-110 | Block 처리 | action=Block | 응답 수신 | 전송 차단 | FR-107 |
| TC-111 | 민감값 치환 | masked_prompt 있음 | 적용 | 원값 미포함 | FR-108 |
| TC-112 | double-submit 방지 | 전송 버튼 연타 | click 반복 | submit 1회 이하 | FR-109 |
| TC-113 | remote selector sync | selector 변경 | config refresh | 새 selector 적용 | FR-110 |
| TC-114 | 사용자 고지 | 최초 실행 | notice 열기 | 저장/미저장 정보 표시 | FR-111, PRV-004 |
| TC-115 | timeout fallback | API timeout | analyze | 정책별 동작 | FR-112 |
| TC-116 | 오탐 피드백 | overlay 표시 | feedback submit | feedback API 호출 | FR-113 |
| TC-117 | decision cache | 같은 prompt TTL 내 재시도 | analyze | 중복 호출 감소 | FR-114 |
| TC-118 | 연결 상태 UI | token 만료/정상 | options 표시 | 상태와 sync 시각 표시 | FR-115 |
| TC-119 | 서버 decision 우선 | local pre-scan allow, server block | 전송 시도 | Block 적용 | FR-116 |

## 10.3 Analyze/Detector/직접 필터/Masking 테스트

| TC ID | 제목 | Given | When | Then | 관련 요구사항 |
|---|---|---|---|---|---|
| TC-201 | Analyze 인증 없음 | Authorization 없음 | POST /prompts/analyze | 401 | FR-201 |
| TC-202 | raw_prompt 미저장 | unique seeded prompt | analyze 후 scan | DB/log 원문 없음 | FR-202 |
| TC-203 | event_id/hash 생성 | 유효 request | analyze | response와 DB에 존재 | FR-203 |
| TC-204 | detector 통합 | email+token+custom keyword prompt | analyze | EMAIL, GITHUB_TOKEN, CUSTOM_FILTER 반환 | FR-204 |
| TC-205 | policy별 action | 같은 prompt 다른 policy | analyze | action 다름 | FR-205 |
| TC-206 | detection 필드 | detection 발생 | analyze | type/count/severity/confidence/source 존재 | FR-206 |
| TC-207 | user_message | action=Block | analyze | user_message 존재 | FR-207 |
| TC-208 | masked_prompt 안전성 | 민감값 포함 | analyze | masked_prompt 원값 미포함 | FR-208 |
| TC-209 | payload too large | max length 초과 | analyze | 413 | FR-209 |
| TC-210 | client_request_id idempotency | 동일 id 재요청 | analyze | 중복 event 정책대로 처리 | FR-210 |
| TC-211 | policy mismatch | old version | analyze | latest_policy_version 반환 | FR-211 |
| TC-212 | 외부 LLM 호출 금지 | fresh config/network mock | analyze | 외부 LLM 호출 0건 | FR-212, SEC-010 |
| TC-213 | rule classifier fallback | classifier module error | analyze | partial_result=true | FR-213 |
| TC-214 | Local LLM local-only | P2 local LLM enabled | analyze | 외부 전송 없음, trace off | FR-214 |
| TC-301 | 이메일 탐지 | test@example.com | scan | EMAIL count=1 | FR-301 |
| TC-302 | 한국 전화번호 탐지 | 010-1234-5678 | scan | PHONE count=1 | FR-302 |
| TC-303 | 주민번호 checksum | valid/invalid dummy | scan | valid만 high confidence | FR-303 |
| TC-304 | 카드 Luhn | valid/invalid | scan | valid만 탐지 | FR-304 |
| TC-305 | 사업자번호 checksum | valid/invalid dummy | scan | valid만 탐지 | FR-305 |
| TC-306 | 금액/할인율 후보 | 3억 원, 15% 할인 | scan | BUSINESS_TERM_CANDIDATE | FR-306 |
| TC-311 | GitHub token | ghp_ dummy | scan | GITHUB_TOKEN | FR-311 |
| TC-312 | AWS key | AKIA dummy | scan | AWS_ACCESS_KEY | FR-312 |
| TC-313 | JWT | 3-part token | scan | JWT | FR-313 |
| TC-314 | Private key | PEM block | scan | PRIVATE_KEY | FR-314 |
| TC-315 | DB URL | postgres URI | scan | DB_CONNECTION_STRING | FR-315 |
| TC-316 | Generic secret 후보 | high entropy dummy | scan | GENERIC_SECRET_CANDIDATE | FR-316 |
| TC-317 | .env secret 후보 | PASSWORD=abc | scan | ENV_SECRET_CANDIDATE | FR-317 |
| TC-321 | 계약정보 rule | 계약금액/위약금 문장 | classify | CONTRACT_INFO | FR-321 |
| TC-322 | 고객정보 rule | 고객사+담당자+문의 | classify | CUSTOMER_INFO | FR-322 |
| TC-323 | 내부전략 rule | 출시계획/가격정책 | classify | INTERNAL_STRATEGY | FR-323 |
| TC-324 | 한국 현지화 rule version | rule pack v 변경 | analyze | event에 version 저장 | FR-324 |
| TC-325 | 애매한 문장 | 일반 계약법 설명 | classify | AMBIGUOUS/low confidence | FR-325 |
| TC-331 | custom regex 생성 | ADMIN token | POST /custom-filters | 생성 후 탐지 반영 | FR-331 |
| TC-332 | custom keyword 생성 | ADMIN token | POST /custom-filters | keyword 탐지 반영 | FR-332 |
| TC-333 | custom filter schema | 필터 생성 | GET filter | label/severity/action/placeholder 존재 | FR-333 |
| TC-334 | 위험 regex 차단 | catastrophic regex | 저장 시도 | validation error | FR-334 |
| TC-335 | filter dry-run 원문 미저장 | 샘플 입력 | POST /custom-filters/test | DB/log 샘플 없음 | FR-335 |
| TC-336 | custom filter audit/version | 필터 수정 | audit 조회 | before/after/version 기록 | FR-336 |
| TC-337 | custom filter stats | filter detection seed | dashboard | 필터별 count 표시 | FR-337 |
| TC-338 | overlap 우선순위 | secret과 custom span 중복 | analyze | secret 우선 | FR-338 |
| TC-401 | 점수 범위 | 임의 detection set | score | 0<=risk<=100 | FR-401 |
| TC-402 | Secret critical | GITHUB_TOKEN | score | risk>=80 Block | FR-402 |
| TC-403 | RRN/Card critical | valid RRN/CARD | score | risk>=80 Block | FR-403 |
| TC-404 | Email/phone 단독 | EMAIL/PHONE only | score | Warn 또는 Mask | FR-404 |
| TC-405 | context confidence 반영 | CONTRACT_INFO conf high | score | risk 상승 | FR-405 |
| TC-406 | custom override 반영 | custom filter action=Block | score | Block | FR-406 |
| TC-407 | threshold mapping | score=85 | decision | Block | FR-407 |
| TC-408 | scoring rationale 존재 | 문서 inspect | read | 점수 이유 명시 | FR-408 |
| TC-501 | 이메일 마스킹 | 이메일 포함 | mask | [이메일] 치환 | FR-501 |
| TC-502 | 전화번호 마스킹 | 전화번호 포함 | mask | [전화번호] 치환 | FR-502 |
| TC-503 | 주민번호 마스킹 | RRN 포함 | mask | [주민등록번호] 치환 | FR-503 |
| TC-504 | API key 마스킹 | token 포함 | mask | [API_KEY] 치환 | FR-504 |
| TC-505 | DB URL 마스킹 | DB URL 포함 | mask | [DB_CONNECTION_STRING] 치환 | FR-505 |
| TC-506 | 반복값 치환 | 같은 이메일 2회 | mask | 모두 치환 | FR-506 |
| TC-507 | context entity 치환 | 고객사/계약금액 span | mask | placeholder 치환 | FR-507 |
| TC-508 | custom placeholder | custom filter match | mask | 설정 placeholder 치환 | FR-508 |

## 10.4 Dashboard/Admin/Security 테스트

| TC ID | 제목 | Given | When | Then | 관련 요구사항 |
|---|---|---|---|---|---|
| TC-601 | events table raw_prompt 없음 | schema introspection | inspect | 금지 컬럼 없음 | FR-601 |
| TC-602 | event metadata 저장 | analyze 성공 | DB 조회 | 필수 metadata 저장 | FR-602 |
| TC-603 | HMAC prompt_hash | 같은/different workspace | analyze | workspace별 hash 분리 | FR-603 |
| TC-604 | detection value 미저장 | detection 발생 | DB 조회 | value/raw_value 없음 | FR-604 |
| TC-605 | dashboard summary | event seed | summary | totals 일치 | FR-605 |
| TC-606 | 사용자/부서 통계 | 여러 seed | summary | stats 정확 | FR-606 |
| TC-607 | detection stats | detection seed | summary | type stats 정확 | FR-607 |
| TC-608 | 원문 미표시/복구 불가 | event detail/UI/routes | inspect/render | raw_prompt·복구 endpoint 없음 | FR-608, PRV-003 |
| TC-609 | 사용자별 이벤트 목록 | user event seed | GET /dashboard/users | 유형/횟수 정확 | FR-609 |
| TC-610 | 사용자별 차트 데이터 | user event seed | chart render | API와 차트 값 일치 | FR-610 |
| TC-611 | 사용자 상세 metadata | user detail | render | action/type/trend만 표시 | FR-611 |
| TC-612 | user 상태 변경 | ADMIN token | PATCH user | ACTIVE/DISABLED 변경 | FR-612 |
| TC-613 | 가입 설정 변경 | ADMIN token | PUT registration | 설정 반영 | FR-613 |
| TC-614 | metadata CSV export | event seed | export | 원문 없는 CSV | FR-614 |
| TC-701 | policy 조회 | ADMIN token | GET policy | 200 | FR-701 |
| TC-702 | policy update | ADMIN token | PUT policy | new_version 생성 | FR-702 |
| TC-703 | audit log | policy/filter/update | audit 조회 | 기록 존재 | FR-703 |
| TC-704 | policy mismatch refresh | old version | analyze | latest_policy_version 반환 | FR-704 |
| TC-705 | health/degraded | DB/Redis down mock | dashboard | degraded 표시 | FR-705 |
| TC-706 | retention 적용 | expired event seed | job 실행 | 삭제/집계 | FR-706 |
| TC-811 | HTTPS guide | production docs | inspect | reverse proxy TLS 문서 존재 | SEC-002 |
| TC-812 | expired token | 만료 JWT | API 요청 | 401 | SEC-003 |
| TC-813 | Admin API role check | USER token | admin API | 403 | SEC-004 |
| TC-814 | log redaction | seeded PII/secret | log scan | seeded 값 없음 | SEC-005 |
| TC-815 | repo secret scan | repo 전체 | secret scan | secret 원문 없음 | SEC-006 |
| TC-816 | rate limit | 초과 요청 | analyze/auth | 429 | SEC-007 |
| TC-817 | CORS 제한 | unauthorized origin | preflight/API | 차단 | SEC-008 |
| TC-821 | pseudonym mode | pseudonym on | event 저장 | 직접 email 미저장 | PRV-006 |
| TC-822 | telemetry 기본 비활성 | fresh setup | network mock | outbound telemetry 없음 | PRV-007 |
| TC-831 | health check | API running | GET /healthz | 200 ok | OPS-001 |
| TC-832 | migration on startup | fresh/restart | container start | 성공 | OPS-002 |
| TC-833 | metrics 수집 | analyze requests | metrics scrape | latency/error/action metric 존재 | OPS-003 |
| TC-834 | 원격 selector update | selector config 변경 | Extension refresh | 새 selector 적용 | OPS-004 |
| TC-835 | retention job | old event seed | job | policy 기준 처리 | OPS-005 |
| TC-901 | onboarding smoke test | fresh clone | documented setup | healthz와 setup 완료 | NFR-001 |
| TC-902 | analyze latency | rule-based detectors | load test | p95 <= 500ms | NFR-002 |
| TC-903 | dashboard latency | 30일 seed | summary/user stats | p95 <= 2s | NFR-003 |
| TC-904 | overlay unmount 안정성 | overlay 표시 후 닫힘 | 다시 입력 | 기본 입력 정상 | NFR-004 |
| TC-905 | single workspace isolation | workspace seed | query | scope 적용 | NFR-005 |
| TC-906 | regex timeout | 악성 regex | analyze | timeout/차단 | NFR-006 |
| TC-907 | rule versioning | policy/filter 변경 | analyze | event에 version 연결 | NFR-007 |

# 11. Development Backlog

## 11.1 Epic 목록

| Epic ID | Epic | 목표 | 우선순위 |
|---|---|---|---:|
| EP-000 | OSS Packaging & Setup | 공개 repo, Docker Compose, setup wizard | P0 |
| EP-001 | Auth, Signup & RBAC | 관리자/일반회원 가입, 초대, 권한 분리 | P0 |
| EP-002 | Chrome Extension MVP | ChatGPT 전송 직전 검사 UX 구현 | P0 |
| EP-003 | Analyze API & Detection Pipeline | prompt 분석, 탐지, scoring, masking 구현 | P0 |
| EP-003A | Custom Filters | 관리자 직접 필터 설정, dry-run, versioning, audit | P1 |
| EP-004 | Event Logging & Privacy Controls | 원문 미저장 이벤트 저장과 검증 | P0 |
| EP-005 | Admin Dashboard | 위험 현황, 사용자, 가입 설정 UI/API | P0 |
| EP-006 | Security Hardening | setup lock, 로그 redaction, rate limit, CORS | P0 |
| EP-007 | Test & QA Automation | TDD, E2E, 설치, 성능, privacy regression | P0 |
| EP-008 | Docs & Contributor Experience | README, install/admin/privacy/contributing 문서 | P0 |
| EP-009 | Operations | health, metrics, migration, retention, backup | P1 |

## 11.2 Feature/Task 상세

### EP-000 OSS Packaging & Setup

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-000 | Repo scaffold | apps/packages/docs/infra 구조 생성 | 없음 | TC-001 통과 | P0 | S |
| TASK-001 | Docker Compose | API/Dashboard/Postgres/Redis compose | TASK-000 | TC-002 통과 | P0 | M |
| TASK-002 | env validation | `.env.example`, startup validation | TASK-001 | TC-003 통과 | P0 | S |
| TASK-003 | setup status API | `/setup/status` | API scaffold | TC-004 통과 | P0 | S |
| TASK-004 | bootstrap API | 첫 admin/workspace/policy 생성 | DB schema | TC-005, TC-006 통과 | P0 | M |
| TASK-005 | setup UI | 첫 관리자 생성 화면 | dashboard scaffold | AC-001 통과 | P0 | M |

### EP-001 Auth, Signup & RBAC

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-011 | user schema | users/invites/registration_settings | DB scaffold | migration 통과 | P0 | M |
| TASK-012 | password auth | register/login/refresh/me | TASK-011 | TC-021, TC-025, TC-026 통과 | P0 | M |
| TASK-013 | invite system | invite 생성/폐기/사용 | TASK-012 | TC-022 통과 | P0 | M |
| TASK-014 | registration modes | INVITE_ONLY/WORKSPACE_CODE/OPEN_SIGNUP | TASK-013 | TC-023, TC-024 통과 | P0 | M |
| TASK-015 | RBAC middleware | ADMIN/USER 권한 | TASK-012 | TC-801, TC-813 통과 | P0 | S |
| TASK-016 | user management API | list/update status/role | TASK-015 | TC-702 통과 | P0 | M |

### EP-002 Chrome Extension MVP

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-101 | Extension scaffold | Manifest V3, TS build, content script, service worker | 없음 | Chrome sideload 가능 | P0 | M |
| TASK-102 | API URL onboarding | self-host URL/token 저장 | TASK-101, Auth API | TC-101 통과 | P0 | M |
| TASK-103 | domain activation | ChatGPT 도메인에서만 활성화 | TASK-101 | TC-102 통과 | P0 | S |
| TASK-104 | input detector | textarea/contenteditable 탐지 | TASK-103 | TC-103 통과 | P0 | M |
| TASK-105 | send event interceptor | click/Enter 전송 보류 | TASK-104 | TC-104, TC-105 통과 | P0 | L |
| TASK-106 | API client | analyze 호출 | TASK-105 | TC-106 통과 | P0 | M |
| TASK-107 | decision handler | Allow/Warn/Mask/Block 처리 | TASK-106 | TC-107~TC-110 통과 | P0 | L |
| TASK-108 | masking injector | masked_prompt 치환 | TASK-107 | TC-111 통과 | P0 | M |
| TASK-109 | employee notice UI | 검사/저장 범위 고지 | TASK-101 | TC-121 통과 | P0 | S |

### EP-003 Analyze API & Detection Pipeline

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-201 | API scaffold | FastAPI/NestJS, OpenAPI, error handler | 없음 | healthz, schema CI 가능 | P0 | M |
| TASK-202 | /prompts/analyze | schema validation, auth | TASK-201 | TC-201 통과 | P0 | M |
| TASK-203 | regex detector | email/phone/RRN/card | TASK-201 | TC-301~TC-304 통과 | P0 | M |
| TASK-204 | secret detector | GitHub/AWS/JWT/private key/DB URL | TASK-201 | TC-311~TC-315 통과 | P0 | L |
| TASK-205 | rule context classifier | 한국 현지화 rule pack 기반 classifier | TASK-201 | TC-321~TC-325 통과 | P0 | M |
| TASK-206 | risk scoring engine | formula, threshold action | detectors | TC-401~TC-407 통과 | P0 | M |
| TASK-207 | masking engine | span merge, placeholder 치환 | detectors | TC-501~TC-506 통과 | P0 | L |
| TASK-208 | analyze orchestration | detector/scoring/masking 통합 | TASK-202~207 | TC-204~TC-208 통과 | P0 | L |
| TASK-209 | local LLM P2 spike | Local LLM runtime/logging/local-only 검증 | TASK-205 | TC-214 통과 | P2 | L |

### EP-003A Custom Filters

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-231 | custom filter schema | custom_filter_rules/versions migration | DB scaffold | TC-331~TC-333 통과 | P1 | M |
| TASK-232 | custom filter CRUD API | 생성/수정/비활성화/조회 | TASK-231 | TC-331~TC-333 통과 | P1 | M |
| TASK-233 | regex validation | syntax/length/timeout/reDoS 방어 | TASK-232 | TC-334, TC-906 통과 | P1 | M |
| TASK-234 | dry-run API | 샘플 테스트, 원문 미저장 | TASK-232 | TC-335 통과 | P1 | M |
| TASK-235 | custom filter detector | analyze pipeline 통합 | TASK-232 | TC-204, TC-337, TC-338 통과 | P1 | L |
| TASK-236 | custom filter UI | 목록/생성/수정/dry-run | dashboard scaffold | TC-331~TC-337 통과 | P1 | M |
| TASK-237 | audit/versioning | 변경 이력 저장 | TASK-232 | TC-336 통과 | P1 | S |

### EP-004 Event Logging & Privacy Controls

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-301 | event schema migration | events/detections/feedback/audit | DB scaffold | TC-601, TC-604 통과 | P0 | M |
| TASK-302 | event logging service | metadata-only 저장 | TASK-301 | TC-602 통과 | P0 | M |
| TASK-303 | HMAC prompt_hash | workspace별 secret | TASK-302 | TC-603, TC-815 통과 | P0 | M |
| TASK-304 | RedactedLogger | prompt key 자동 redaction | API scaffold | TC-814 통과 | P0 | M |
| TASK-305 | privacy regression CI | seeded 원문 DB/log scan | TASK-304 | TC-202, TC-814 자동화 | P0 | L |
| TASK-306 | telemetry off by default | 외부 telemetry 비활성 | API scaffold | TC-823 통과 | P0 | S |

### EP-005 Admin Dashboard

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-401 | dashboard scaffold | React routing, auth guard | Auth API | 기본 화면 표시 | P0 | M |
| TASK-402 | summary API | totals/by_user/by_detection/trend | event schema | TC-605~TC-607 통과 | P0 | M |
| TASK-402A | user risk stats API | 사용자별 이벤트 유형/횟수 목록과 차트 데이터 | event schema | TC-609~TC-611 통과 | P0 | M |
| TASK-403 | Overview UI | summary 카드/차트 | TASK-402 | API와 숫자 일치 | P0 | M |
| TASK-404 | events API | filter/page/detail | event schema | TC-608 통과 | P0 | M |
| TASK-405 | Risk Events UI | 목록/필터/상세 | TASK-404 | raw prompt 미표시 | P0 | M |
| TASK-406 | Users UI | 사용자 목록/status/role 변경 | user API | TC-702 통과 | P0 | M |
| TASK-407 | Registration UI | invite/mode 설정 | invite API | TC-022~TC-024 통과 | P0 | M |
| TASK-408 | no raw prompt UI check | 원문 필드 미표시 테스트 | TASK-405 | TC-608 통과 | P0 | S |
| TASK-409 | Custom Filters UI | 직접 필터 관리와 dry-run 화면 | custom filter API | TC-331~TC-337 통과 | P1 | M |

### EP-006 Security, Docs, Operations

| Task ID | Feature/Task | 설명 | 선행조건 | 완료 기준 | 우선순위 | 난이도 |
|---|---|---|---|---|---:|---:|
| TASK-501 | setup lock hardening | setup 완료 후 bootstrap 차단 | setup API | TC-005 통과 | P0 | S |
| TASK-502 | CORS restriction | Extension/dashboard origin 제한 | API scaffold | TC-817 통과 | P0 | S |
| TASK-503 | rate limiting | auth/analyze 기준 | Redis | TC-816 통과 | P0 | M |
| TASK-504 | workspace scoping guard | workspace query helper | Auth | isolation test 통과 | P0 | M |
| TASK-505 | repo secret scanning | CI secret scan | repo scaffold | TC-815 통과 | P0 | S |
| TASK-801 | README | 설치/개요/스크린샷/한계 | MVP scaffold | README 완성 | P0 | M |
| TASK-802 | install guide | Docker Compose, HTTPS, backup | compose | docs/install.md | P0 | M |
| TASK-803 | admin guide | 가입/정책/대시보드 운영 | dashboard | docs/admin-guide.md | P0 | M |
| TASK-804 | privacy design doc | raw_prompt 미저장 설명 | privacy controls | docs/privacy-design.md | P0 | M |
| TASK-805 | contributing guide | detector rule/test 기여 방법 | test harness | CONTRIBUTING.md | P0 | M |
| TASK-806 | license decision | AGPL/Apache 결정 | DEC-002 | LICENSE 추가 | P0 | S |

## 11.3 MVP 개발 순서 제안

1. Repo scaffold, Docker Compose, `.env.example`, health check를 만든다.
2. setup status/bootstrap과 첫 관리자 생성 flow를 만든다.
3. 사용자/초대/가입 방식/Auth/RBAC를 구현한다.
4. raw_prompt 미저장 테스트와 RedactedLogger를 먼저 CI에 넣는다.
5. regex/secret detector와 masking engine을 TDD로 구현한다.
6. risk scoring engine과 `/prompts/analyze` orchestration을 구현한다.
7. Chrome Extension scaffold와 self-host API 연결 UI를 만든다.
8. ChatGPT fixture 기반 전송 인터셉트 E2E를 만든다.
9. Allow/Warn/Mask/Block UI와 masking injector를 구현한다.
10. event logging과 dashboard summary/events API를 구현한다.
11. dashboard Overview/Risk Events/Users/Invites UI를 구현한다.
12. security tests, workspace scoping, rate limit, CORS를 구현한다.
13. context classifier를 붙이고 fallback/timeout을 검증한다.
14. install/admin/privacy/contributing 문서를 완성한다.
15. release package와 sample deployment guide를 만든다.

---

# 12. Definition of Done

## 12.1 기능 완료 기준

- P0 FR이 모두 구현되어야 한다.
- fresh clone 후 README만 보고 local self-host 설치가 가능해야 한다.
- 첫 관리자 회원가입과 일반회원 회원가입이 동작해야 한다.
- Extension은 self-hosted API URL에 연결할 수 있어야 한다.
- Extension은 ChatGPT fixture page에서 Allow/Warn/Mask/Block 흐름을 모두 재현해야 한다.
- `/setup/*`, `/auth/*`, `/invites`, `/prompts/analyze`, `/events`, `/dashboard/summary`, `/admin/users`, `/policies/current` API가 OpenAPI spec과 일치해야 한다.
- Dashboard는 Overview, Risk Events, Users, Invites/Registration 화면을 제공해야 한다.
- 원문 prompt 조회 기능은 없어야 한다.

## 12.2 테스트 완료 기준

- Install test: fresh clone + compose + setup flow 통과
- Unit test: P0 detector/scoring/masking branch coverage 80% 이상
- Integration test: P0 API 테스트 100% 통과
- E2E test: Extension P0 flow 100% 통과
- Security test: SEC P0 테스트 100% 통과
- Privacy regression: seeded raw_prompt가 DB/log/error tracking에 0건
- Performance: NFR-002, NFR-003, NFR-006 기준 충족
- OSS CI: lint, typecheck, test, secret scan, dependency scan 통과

## 12.3 보안 완료 기준

- setup bootstrap 1회 제한 검증
- ADMIN/USER 권한 분리 검증
- workspace scoping 검증
- rate limit 적용
- CORS 제한 적용
- 비밀번호 hash 저장
- prompt_hash HMAC key가 repo/log에 노출되지 않음
- application/access/error log에 raw_prompt 미기록 검증
- 외부 LLM API 호출 없음
- 관리자 policy/registration 변경 audit log 기록

## 12.4 개인정보 완료 기준

- raw_prompt 저장 컬럼 없음
- detection 원문값 저장 컬럼 없음
- masked_prompt 기본 저장 없음
- page URL은 origin만 저장
- 직원/회원 고지 UI 또는 문서 제공
- retention_days 정책 존재
- outbound telemetry 기본 비활성
- pseudonymous mode 설계 또는 후속 이슈 등록

## 12.5 문서 완료 기준

- README, install guide, admin guide, extension setup, privacy design, threat model, contributing guide가 최신 상태여야 한다.
- 모든 P0 요구사항에는 관련 TC가 연결되어야 한다.
- API 변경 시 OpenAPI spec과 본 문서가 함께 수정되어야 한다.
- DB migration 변경 시 Data Model 문서가 함께 수정되어야 한다.
- policy 변경 시 Threat Model과 Test Case 영향 여부를 확인해야 한다.

## 12.6 배포 가능 기준

- GitHub release artifact 생성
- Docker image build 성공
- Extension build 생성 및 sideload 테스트 완료
- test workspace, admin user, normal user seed script 제공
- health check와 metrics 정상
- backup/restore 기본 문서화
- 개인정보/보안 체크리스트 승인
- known issue 목록 작성

---

# 13. MVP 범위 분리표

## 13.1 반드시 구현할 것

| 항목 | 관련 ID |
|---|---|
| OSS repo/Docker Compose/setup wizard | FR-001~FR-006 |
| 관리자 회원가입 | FR-004~FR-006 |
| 일반회원 회원가입 | FR-021~FR-028 |
| Auth/RBAC | FR-021, FR-026~FR-027, SEC-003~SEC-009 |
| ChatGPT 웹 입력창 감지 | FR-102~FR-105 |
| self-host API 연결 | FR-101 |
| 전송 직전 Analyze API 호출 | FR-106, FR-201~FR-208 |
| Allow/Warn/Mask/Block UI | FR-107~FR-108 |
| Regex PII 탐지 | FR-301~FR-304 |
| Secret 탐지 | FR-311~FR-315 |
| Rule-based context classifier 최소 구현 | FR-321~FR-325 |
| Risk scoring | FR-401~FR-407 |
| Masking | FR-501~FR-506 |
| 원문 미저장 event logging | FR-601~FR-608, PRV-001~PRV-003 |
| Dashboard Overview/Risk Events/User Risk Stats/Users/Invites | FR-605~FR-614, FR-701~FR-706 |
| Privacy/security regression tests | TC-601~TC-608, TC-814~TC-817 |
| 설치/운영/기여 문서 | TASK-801~TASK-805 |

## 13.2 구현하면 좋은 것

| 항목 | 관련 ID |
|---|---|
| 회원 승인 대기 | FR-028 |
| Extension pairing code | P1 |
| 사용자 사유 입력 후 허용 | FR-110 |
| 오탐 피드백 | FR-110 |
| 로컬/TTL 캐싱 | P1 |
| 직접 필터 설정 | FR-331~FR-338, FR-508 |
| Repeat Risk | P1 |
| Policy update UI/API | FR-704~FR-706 |
| Retention job | OPS-005 |
| Release signing | SEC-010 |

## 13.3 후속 버전으로 미룰 것

| 항목 | 이유 |
|---|---|
| Claude/Gemini/Perplexity 전체 지원 | DOM/UX별 adapter 필요 |
| 첨부파일 검사 | 파일 파싱, OCR, malware, 대용량 처리 필요 |
| 모바일/데스크톱 앱 | endpoint/MDM 영역 |
| OIDC/SAML | self-host MVP 이후 |
| Multi-workspace | single-tenant 안정화 이후 |
| SIEM/SOAR 연동 | 운영 환경 연동은 후속 |
| Local LLM context classifier | P2. 로컬 실행만 허용하고 외부 LLM API는 제외 |
| Managed SaaS | MVP 목표가 아님 |

---

# 14. 요구사항-테스트 추적 매트릭스 요약

| Requirement | Test Cases |
|---|---|
| FR-001~FR-006 | TC-001~TC-006 |
| FR-021~FR-028 | TC-021~TC-027, TC-801 |
| FR-101~FR-110 | TC-101~TC-113, TC-121 |
| FR-201~FR-210 | TC-201~TC-210 |
| FR-301~FR-305 | TC-301~TC-305 |
| FR-311~FR-316 | TC-311~TC-316 |
| FR-321~FR-324 | TC-321~TC-324 |
| FR-401~FR-407 | TC-401~TC-407 |
| FR-501~FR-507 | TC-501~TC-507 |
| FR-601~FR-608 | TC-601~TC-608 |
| FR-701~FR-708 | TC-701~TC-708 |
| NFR-001~NFR-008 | TC-901~TC-908 |
| SEC-001 | TC-005 |
| SEC-002 | TC-811 |
| SEC-003 | TC-812 |
| SEC-004 | TC-813 |
| SEC-005 | TC-814 |
| SEC-006 | TC-815 |
| SEC-007 | TC-816 |
| SEC-008 | TC-817 |
| SEC-009 | TC-026 |
| SEC-010 | TC-818 |
| SEC-011 | TC-819 |
| PRV-001 | TC-601, TC-814 |
| PRV-002 | TC-604 |
| PRV-003 | TC-608 |
| PRV-004 | TC-121 |
| PRV-005 | TC-821 |
| PRV-006 | TC-822 |
| PRV-007 | TC-823 |
| OPS-001 | TC-831 |
| OPS-002 | TC-832 |
| OPS-003 | TC-833 |
| OPS-004 | TC-834 |
| OPS-005 | TC-835 |

---

# 15. 충돌/불확실성/결정 필요 사항

## 15.1 결정 필요 사항

| ID | 항목 | 선택지 | 권장안 | 영향 |
|---|---|---|---|---|
| DEC-001 | API 서버 기술 | FastAPI vs NestJS vs Go | detector/ML 연동 우선이면 FastAPI, monorepo TS 우선이면 NestJS | 팀 역량과 기여자 풀에 영향 |
| DEC-002 | License | AGPL-3.0 vs Apache-2.0 vs MIT | SaaS fork 견제면 AGPL-3.0, 확산 우선이면 Apache-2.0 | 오픈소스 생태계와 상업화 전략 영향 |
| DEC-003 | DB 기본값 | PostgreSQL only vs SQLite option | MVP는 PostgreSQL. 개인용 SQLite는 P2 | 설치 난이도와 운영 안정성 trade-off |
| DEC-004 | 가입 방식 기본값 | INVITE_ONLY vs WORKSPACE_CODE | public internet 노출 고려해 INVITE_ONLY | 보안성과 사용 편의성 trade-off |
| DEC-005 | Context classifier 방식 | rule-based MVP vs Local LLM P2 | MVP는 rule-based, Local LLM은 P2 | 정확도와 self-host 운영 부담 trade-off |
| DEC-006 | timeout 정책 | fail-closed vs fail-open-with-warning | secret/critical은 fail-closed, low/medium은 warning | 보안성과 업무 연속성 trade-off |
| DEC-007 | user identity 저장 | 실명/이메일 vs pseudonymous ID | MVP는 이메일, privacy 민감 환경은 pseudonymous P1 | 감사성과 프라이버시 trade-off |
| DEC-008 | context-only Block 기준 | confidence 0.8 이상 block vs mask only | 초기에는 Mask 우선, secret/PII와 결합 시 Block | 오탐 업무 방해 영향 |
| DEC-009 | masked_prompt 저장 여부 | 저장 금지 vs 옵션 저장 | MVP는 저장 금지 | 디버깅 편의보다 privacy 우선 |
| DEC-010 | Extension 배포 | Chrome Web Store vs sideload/packed release | MVP는 sideload/packed release + 빌드 문서 | 심사 부담과 사용 편의성 영향 |
| DEC-011 | Telemetry | 완전 비활성 vs opt-in anonymous telemetry | 기본 비활성, opt-in만 허용 | OSS 신뢰와 품질 개선 trade-off |

## 15.2 잠재 충돌

| 충돌 | 설명 | 해결 방향 |
|---|---|---|
| 오픈소스 투명성 vs 보안 악용 | detector 우회 방법도 공개될 수 있음 | rule 다양화, secret detector 강화, 보안 한계 명시 |
| 설치 편의성 vs 운영 보안 | OPEN_SIGNUP/HTTP가 쉬우나 위험 | 안전한 기본값, 경고 UI, reverse proxy 문서 |
| 감사 증빙 vs 개인정보 최소화 | 감사에는 상세 근거가 필요하지만 원문 저장은 위험 | detection type/count/confidence/action/policy version으로 증빙 |
| Local LLM 정확도 vs 운영 부담 | 문맥 분류 정확도를 높일 수 있지만 GPU/메모리/trace 통제가 필요 | MVP 제외, P2에서 local-only로 검토 |
| 전송 직전 검사 vs UX 지연 | API 지연이 업무 흐름을 방해 | regex/secret/custom/rule 빠른 경로, timeout fallback |
| 고위험 차단 vs 생산성 | 차단이 많으면 우회 사용 증가 | Mask 우선 UX, 사유 입력, 정책 튜닝, FP feedback |
| DOM 기반 구현 vs ChatGPT UI 변경 | selector 깨질 수 있음 | remote selector config, MutationObserver, fixture E2E |

## 15.3 명시적 한계

- Extension이 설치되지 않은 브라우저, 개인 기기, 모바일 앱, 데스크톱 앱 입력은 탐지하지 못한다.
- self-host 서버를 public internet에 잘못 노출하면 계정/메타데이터가 위험해질 수 있다.
- 사용자가 민감정보를 이미지로 캡처해 업로드하는 경우 MVP는 탐지하지 못한다.
- rule-based context classifier는 법적 위반 여부를 확정하지 않는다. 위험 가능성만 분류한다.
- 원문을 저장하지 않으므로 사후 forensic에서 실제 prompt 원문 복구는 불가능하다. 이는 의도된 privacy 설계이다.
- ChatGPT 웹의 DOM 변경은 지속적 유지보수가 필요하다.
- 대형 enterprise DLP/CASB의 네트워크·엔드포인트 통제 범위를 대체하지 않는다.

---

# 16. AI 개발 에이전트용 구현 지시 요약

1. 먼저 self-host 설치 flow부터 만든다. `docker compose up` → `/setup` → 첫 admin 생성 → dashboard 진입이 최우선이다.
2. 관리자 회원가입과 일반회원 회원가입을 명확히 분리한다. 첫 admin bootstrap은 1회만 허용한다.
3. 기본 가입 모드는 INVITE_ONLY다. OPEN_SIGNUP은 기본 비활성화한다.
4. raw_prompt 저장 금지 원칙을 깨는 schema, log, error tracking 구현은 거부한다.
5. TC-601, TC-603, TC-814는 초기부터 CI에 포함한다.
6. Extension은 self-host API URL을 사용자가 설정할 수 있어야 한다.
7. Extension은 fixture 기반 E2E를 먼저 만들고 실제 ChatGPT DOM은 remote selector config로 대응한다.
8. secret detector와 masking engine은 P0 중 최우선으로 구현한다.
9. context classifier는 adapter interface부터 만들고, 초기에는 mock/local rule로 테스트 가능하게 한다.
10. dashboard는 원문 없는 metadata만 보여준다.
11. 관리자도 원문을 볼 수 있는 endpoint/UI를 만들지 않는다.
12. 모든 API response와 DB event에는 `policy_version`과 `event_id`를 포함한다.
13. 모든 P0 요구사항은 연결된 TC가 통과하기 전 완료로 보지 않는다.
14. README, install guide, privacy design, contributing guide는 코드와 동시에 업데이트한다.
15. 오픈소스 기여자가 detector를 추가해도 privacy regression이 반드시 실행되게 한다.
