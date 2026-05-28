# PromptGuard Self-host 서버 구성 결정안

작성일: 2026-05-23

## 결정

PromptGuard self-host MVP 서버는 다음 구성을 기본값으로 한다.

- API: FastAPI
- DB: PostgreSQL
- Cache/Rate limit: Redis
- Migration: Alembic
- Local runtime: Docker Compose
- 초기 dashboard: 별도 `apps/dashboard`로 분리 예정

## 이유

FastAPI는 detector, masking, checksum, Luhn 검증처럼 문자열 처리와 테스트가 많은 서버 로직을 빠르게 구현하기 좋다. PostgreSQL은 사용자, 초대, refresh token, event metadata, custom filter versioning을 안정적으로 저장하기에 적합하다. Redis는 auth/analyze rate limit과 짧은 TTL 상태 저장에 사용한다. Alembic은 PostgreSQL schema migration을 명시적으로 관리할 수 있어 fresh install과 restart migration 검증에 맞다.

## 기본 실행 단위

Docker Compose는 다음 서비스를 제공한다.

- `api`: FastAPI app
- `postgres`: PromptGuard metadata database
- `redis`: rate limit/session helper

Dashboard는 API/Auth/Stats가 준비된 뒤 `apps/dashboard`로 추가한다.

## 우선 API

1. `GET /healthz`
2. `GET /setup/status`
3. `POST /setup/bootstrap`
4. `POST /auth/login`
5. `POST /auth/refresh`
6. `GET /auth/me`
7. `GET /config/extension`
8. `POST /prompts/analyze`
9. `POST /files/analyze`

## Privacy Guardrails

- raw prompt는 DB, log, diagnostic에 저장하지 않는다.
- file content는 DB, log, diagnostic에 저장하지 않는다.
- detected raw value는 event table에 저장하지 않는다.
- masked prompt는 기본 저장하지 않는다.
- URL은 origin만 저장한다.
- refresh token 원문은 저장하지 않고 hash만 저장한다.

## 다음 작업

1. Docker Desktop 설치 및 실행 확인
2. `.env.example`을 `.env`로 복사
3. `docker compose up --build`
4. `http://localhost:8000/healthz` 확인
5. users/invites/registration_settings/refresh_tokens migration 작성
