# PromptGuard Dataset Build Guide 1.1.2

## 0. 문서 목적

이 문서는 PromptGuard 1.1.2의 민감값 탐지용 ML 데이터셋을 구축하기 위한 상세 안내서다.

1.1.1 문서는 `context_dataset`, `pii_relevance_dataset`, `code_sensitivity_dataset`, `ocr_fixtures`를 ML dataset type으로 정의하고, `label definition document 작성 → 라벨별 seed sample 20–50개 작성 → synthetic 생성 → hard negative 작성 → train/valid/test split → Qwen embedding 추출 → One-vs-Rest classifier 학습 → threshold 보정 → precision/recall/F1 평가 → error bank 기록 → artifact 저장` 순서의 학습 절차를 요구한다.

1.1.2에서는 그중 비어 있던 `context_dataset` 라벨을 민감값 탐지 목적에 맞게 일반화하고, seed 작성자가 바로 작업할 수 있도록 라벨 정의, JSONL schema, positive/negative/hard negative 작성 기준, 검수 기준, split 기준, 학습 전처리 기준을 고정한다.

---

## 1. 1.1.2에서 고정하는 원칙

### 1.1 목표는 도메인 분류가 아니라 민감값 탐지다

`CONTRACT_INFO`, `CUSTOMER_CONFIDENTIAL`, `INTERNAL_STRATEGY`처럼 특정 업무 도메인을 세분화하는 방식은 발표나 사례 설명에는 직관적이지만, 민감값 탐지 모델의 일반화에는 불리할 수 있다.

1.1.2의 라벨은 다음 질문에 답하도록 설계한다.

```text
이 입력은 어떤 종류의 민감값 또는 민감 문맥을 다루고 있는가?
이 값이 실제 유출 위험에 가까운가?
겉으로는 위험 단어가 있지만 일반 설명/템플릿/더미/마스킹 작업인가?
```

즉 라벨은 특정 업계나 예시 회사에 묶지 않고, 다음처럼 일반화한다.

```text
secret / credential
personal data
financial identifier
confidential business value
proprietary technical value
security / access-control value
internal operational record
bulk sensitive record
```

### 1.2 context classifier는 Stage 0 scanner를 대체하지 않는다

Stage 0 scanner는 regex, fingerprint, token candidate, protected target, custom regex 등 명확한 signal을 탐지한다. `context_dataset` classifier는 그 signal 주변의 문맥 위험도를 보강한다.

예를 들어 `010-0000-0000` 같은 값 자체는 Stage 0이 잡는다. `context_dataset`은 “고객 명단에서 연락처를 추출해달라”처럼 개인정보 처리 의도가 드러나는 문맥을 잡는다.

### 1.3 classifier output과 policy action은 분리한다

Classifier는 `risk_scores`, `suppressor_scores`, `code_scores`, `pii_relevance_scores`를 낸다. 최종 `allow / warn / mask / block`은 Policy Orchestrator가 결정한다.

따라서 라벨은 action이 아니다.

나쁜 해석:

```text
PERSONAL_DATA_CONTEXT = block
SYNTHETIC_DUMMY_CONTEXT = allow
```

정확한 해석:

```text
PERSONAL_DATA_CONTEXT = 개인정보 관련 문맥 risk score 상승
SYNTHETIC_DUMMY_CONTEXT = 더미/테스트 문맥 suppressor score 상승
최종 action = Stage 0 finding + classifier score + threshold + policy mode가 결정
```

---

## 2. Dataset 종류

1.1.2의 dataset은 1.1.1 구조를 유지한다.

```text
datasets/
  raw/
    seeds/
    synthetic/
  processed/
  hard_eval/
  ocr_fixtures/
  reports/
models/
  qwen_context_classifier.joblib
  qwen_pii_relevance_classifier.joblib
  qwen_code_classifier.joblib
  thresholds.json
  label_map.json
  model_card.md
```

Dataset type은 다음 네 개다.

| Dataset | 목적 | 학습 여부 |
|---|---|---|
| `context_dataset` | 입력/segment가 민감값 유출 문맥인지 판단 | 학습 |
| `pii_relevance_dataset` | Stage 0이 찾은 PII-like span이 실제 개인정보인지 판단 | 학습 |
| `code_sensitivity_dataset` | code segment가 일반 예제인지 민감 코드인지 판단 | 학습 |
| `ocr_fixtures` | OCR pipeline과 OCR policy 검증 | ML 학습 아님 |

---

## 3. 공통 JSONL 작성 규칙

### 3.1 실제 민감정보 금지

모든 seed, synthetic, hard_eval에는 실제 민감정보를 넣지 않는다.

금지:

```text
실제 주민등록번호
실제 전화번호
실제 이메일
실제 주소
실제 계좌번호
실제 카드번호
실제 고객사명
실제 계약 조건
실제 API key
실제 access token
실제 password
실제 private key
실제 사내 코드
실제 사내 보안 구조
실제 장애 보고서
실제 고객 지원 기록
```

허용:

```text
가상회사 A
테스트고객 B
샘플프로젝트 C
홍테스트
김샘플
test.user@example.test
010-0000-0000
000-00-00000
1111-2222-3333-4444
sk-test-000000000000
dummy_token_123
fake_private_key_for_test
```

단, placeholder만 반복하면 안 된다. 모델이 `가상회사`, `테스트`, `dummy` 같은 단어만 외우지 않도록 risky sample과 safe sample 양쪽에 같은 placeholder 계열을 섞는다.

### 3.2 label 문자열을 text에 직접 넣지 않는다

금지:

```text
이 문장은 SECRET_CREDENTIAL_CONTEXT입니다.
PERSONAL_DATA_CONTEXT를 탐지해줘.
CONFIDENTIAL_BUSINESS_CONTEXT sample입니다.
```

허용:

```text
첨부된 고객 명단에서 이름과 연락처만 뽑아 표로 정리해줘.
```

### 3.3 같은 template의 파생 sample은 같은 split에 둔다

동일 template에서 target 이름이나 숫자만 바꾼 문장이 train과 test에 동시에 들어가면 평가가 부풀려진다.

따라서 모든 row에는 `template_id`를 넣고, split은 `template_id` 단위로 나눈다.

### 3.4 모든 seed에는 notes를 쓴다

`notes`는 사람이 다시 검수할 때 “왜 이 라벨을 붙였는지” 확인하기 위한 필드다.

좋은 notes:

```text
requests extraction of direct personal identifiers from a customer list
mentions API key but asks only for general explanation
specific business terms tied to a non-public document
```

나쁜 notes:

```text
위험함
계약임
개인정보 같음
```

### 3.5 학습 입력과 관리 필드를 분리한다

데이터셋 row에는 학습에 직접 쓰이는 필드와 관리용 필드가 함께 있을 수 있다. 둘을 명확히 구분한다.

```text
학습 입력:
text, labels 또는 label

관리 필드:
id, language, source_type, case_type, template_id, parent_seed_id, target_risk_label, notes
```

Qwen embedding model에는 `text` 또는 `code_text`/`segment_text`에서 만든 텍스트만 들어간다. Classifier의 정답값으로는 `labels` 또는 `label`만 사용한다. 나머지 필드는 split, 검수, 통계, error bank 연결, 재현성 관리를 위한 정보다.

Stage 0 signal 여부, PII span count, token candidate count, risk score 같은 값은 raw seed 작성자가 수동으로 쓰지 않는다. 이런 값은 scanner/evaluation을 실행한 뒤 별도 report나 cache로 자동 산출한다.

---

## 4. context_dataset

## 4.1 역할

`context_dataset`은 prompt, 첨부파일 segment, OCR text block, 문서 paragraph, spreadsheet row group 등이 민감값 유출 문맥인지 분류한다.

입력 단위:

```text
composer prompt
ParsedBlock
AnalysisSegment
PDF page/block
DOCX paragraph/table row
XLSX sheet row group
PPT slide text
OCR text block
log/config/code 주변 설명문
```

출력:

```text
risk_scores
suppressor_scores
```

`context_dataset`은 multi-label이다. 하나의 입력에 여러 라벨이 동시에 붙을 수 있다.

---

## 4.2 context_dataset schema

`context_dataset`은 **학습 입력**과 **데이터셋 관리용 원천 row**를 구분한다.

학습에 실제로 사용되는 핵심 정보는 다음 두 필드다.

```json
{
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"]
}
```

Qwen embedding model에는 `text`만 들어간다. Classifier head의 정답값으로는 `labels`만 사용한다.

학습 코드는 개념적으로 다음과 같다.

```python
x = qwen_embed(row["text"])
y = encode_multilabel(row["labels"])
```

`id`, `language`, `source_type`, `case_type`, `template_id`, `target_risk_label`, `notes`는 classifier 입력 feature가 아니다. 이 필드들은 seed 추적, 검수, split leakage 방지, error analysis를 위한 관리 필드다.

### 4.2.1 최소 학습 row

학습용 processed dataset은 다음처럼 단순하게 유지할 수 있다.

```json
{
  "id": "ctx_secret_001",
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "split": "train"
}
```

multi-label sample은 `labels` 배열에 여러 라벨을 넣는다.

```json
{
  "id": "ctx_multi_001",
  "text": "고객사 A와 맺은 계약서의 API 인증 조건과 결제 조건을 정리해줘.",
  "labels": [
    "CONFIDENTIAL_BUSINESS_CONTEXT",
    "SECRET_CREDENTIAL_CONTEXT",
    "SECURITY_CONTROL_CONTEXT"
  ],
  "split": "train"
}
```

### 4.2.2 권장 raw seed row

사람이 작성하고 검수하는 원천 seed는 다음 필드를 권장한다.

```json
{
  "id": "ctx_secret_001",
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "secret_api_call_v1",
  "notes": "credential-like token is used to construct an API call"
}
```

Hard negative는 어떤 risk label의 오탐을 줄이기 위한 sample인지 추적하기 위해 `target_risk_label`을 추가한다.

```json
{
  "id": "ctx_secret_hn_001",
  "text": "API key와 OAuth access token의 차이를 일반적으로 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "SECRET_CREDENTIAL_CONTEXT",
  "template_id": "secret_general_explanation_v1",
  "notes": "mentions API key and token but asks for general explanation only"
}
```

### 4.2.3 필드 설명

| Field | 필수 | 학습 입력 여부 | 설명 |
|---|---:|---:|---|
| `id` | 예 | 아니요 | 고유 ID. 추적, 중복 제거, error bank 연결에 사용 |
| `text` | 예 | 예 | Qwen embedding 입력 텍스트 |
| `labels` | 예 | 예 | multi-label list. multi-hot target으로 변환됨 |
| `split` | processed에서 예 | 아니요 | `train`, `valid`, `test` |
| `language` | raw에서 권장 | 아니요 | `ko`, `en`, `ko_en`, `code_mixed`. 언어별 성능 분석용 |
| `source_type` | raw에서 권장 | 아니요 | `seed`, `synthetic`, `hard_eval`, `error_bank` |
| `case_type` | raw에서 권장 | 아니요 | `positive`, `negative`, `hard_negative`, `mixed`, `boundary` |
| `template_id` | raw에서 강력 권장 | 아니요 | split grouping 기준. 같은 template은 같은 split에 둠 |
| `parent_seed_id` | synthetic에서 권장 | 아니요 | synthetic sample의 원본 seed 추적 |
| `target_risk_label` | hard_negative일 때 예 | 아니요 | 어떤 risk label의 오탐을 줄이기 위한 negative인지 |
| `notes` | raw에서 권장 | 아니요 | 라벨링 근거 |

`metadata.has_stage0_signal`, `contains_real_sensitive_value`, `risk_score` 같은 값은 raw seed에 수동으로 넣지 않는다. 이런 값은 Stage 0 scanner, preprocessing, evaluation을 돌린 뒤 report나 cache로 자동 산출한다.

---

## 4.3 context risk labels

1.1.2에서 확정하는 `context_dataset` risk label은 다음 8개다.

```text
SECRET_CREDENTIAL_CONTEXT
PERSONAL_DATA_CONTEXT
FINANCIAL_IDENTIFIER_CONTEXT
CONFIDENTIAL_BUSINESS_CONTEXT
PROPRIETARY_TECHNICAL_CONTEXT
SECURITY_CONTROL_CONTEXT
INTERNAL_OPERATION_CONTEXT
BULK_SENSITIVE_RECORD_CONTEXT
```

이 라벨들은 특정 업종이 아니라 민감값 유형과 유출 문맥을 기준으로 한다.

---

## 4.4 SECRET_CREDENTIAL_CONTEXT

### 의미

API key, access token, refresh token, password, credential, private key, session cookie, signing key, connection string, webhook secret 등 인증/접근 권한을 제공할 수 있는 값이나 그 사용 문맥.

### Positive 기준

다음 중 하나에 해당하면 붙인다.

```text
secret 값을 사용해서 API 호출, curl, 코드, config를 만들려는 요청
파일/log/env에서 secret 값을 추출하려는 요청
token, password, key를 재사용하거나 변환하려는 요청
private key, session cookie, connection string 분석 요청
실제 또는 실제처럼 보이는 secret candidate가 있고 사용 의도가 있음
```

### Negative 기준

다음 경우에는 붙이지 않는다.

```text
API key 개념 설명
OAuth token과 refresh token의 차이 설명
secret 관리 best practice 설명
더미 token 형식 예시 생성
환경변수 사용법 일반 설명
```

### Positive seed

```json
{
  "id": "ctx_secret_001",
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "secret_api_call_v1",
  "notes": "credential-like token is used to construct an API call"
}
```

### Hard negative

```json
{
  "id": "ctx_secret_hn_001",
  "text": "API key와 OAuth access token의 차이를 일반적으로 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "SECRET_CREDENTIAL_CONTEXT",
  "template_id": "secret_general_explanation_v1",
  "notes": "mentions API key and token but asks for general explanation only"
}
```

---

## 4.5 PERSONAL_DATA_CONTEXT

### 의미

개인 식별정보나 연락처를 추출, 정리, 변환, 요약, 전송하려는 문맥. 이름, 이메일, 전화번호, 주소, 생년월일, 주민등록번호, 여권번호, 사번, 고객번호, 계정 ID 등이 포함된다.

### Positive 기준

```text
명단에서 이름/연락처/이메일을 추출하려는 요청
고객/지원자/직원/학생 개인정보를 표, CSV, JSON으로 변환하려는 요청
이력서, 신청서, 상담 기록에서 개인 식별정보를 정리하려는 요청
여러 개인의 정보를 요약하거나 재구성하려는 요청
```

### Negative 기준

```text
개인정보보호법 일반 설명
개인정보 처리방침 템플릿 요청
이력서 빈 양식 생성
더미 개인정보 생성 요청
개인정보 마스킹 방법 설명
```

### Positive seed

```json
{
  "id": "ctx_personal_001",
  "text": "첨부한 고객 명단에서 이름, 이메일, 전화번호만 뽑아서 CSV로 정리해줘.",
  "labels": ["PERSONAL_DATA_CONTEXT", "BULK_SENSITIVE_RECORD_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "personal_bulk_extract_v1",
  "notes": "extracts direct personal identifiers from a customer list"
}
```

### Hard negative

```json
{
  "id": "ctx_personal_hn_001",
  "text": "회원가입 양식에 들어갈 이름, 이메일, 전화번호 입력칸 예시를 만들어줘.",
  "labels": ["TEMPLATE_OR_EMPTY_FORM_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "PERSONAL_DATA_CONTEXT",
  "template_id": "personal_form_template_v1",
  "notes": "asks for empty form fields, not actual personal data"
}
```

---

## 4.6 FINANCIAL_IDENTIFIER_CONTEXT

### 의미

계좌번호, 카드번호, 결제수단, 청구 정보, 세금계산서 식별값, 거래 식별자, 급여/정산 정보 등 금전 거래나 금융 식별값과 연결된 문맥.

### Positive 기준

```text
계좌번호/카드번호/결제정보 추출
정산 목록, 청구 목록, 결제 실패 목록 처리
고객별 결제수단이나 청구 정보를 표로 정리
거래 ID와 개인/고객 정보를 연결해서 재구성
급여/환급/정산 파일에서 식별값 추출
```

### Negative 기준

```text
카드번호 형식 설명
더미 결제 데이터 생성
회계 개념 설명
결제 플로우 일반 설명
금융정보 마스킹 가이드 작성
```

### Positive seed

```json
{
  "id": "ctx_financial_001",
  "text": "첨부된 정산 파일에서 고객명, 계좌번호, 환급 금액을 추출해서 표로 정리해줘.",
  "labels": ["FINANCIAL_IDENTIFIER_CONTEXT", "PERSONAL_DATA_CONTEXT", "BULK_SENSITIVE_RECORD_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "financial_refund_extract_v1",
  "notes": "bulk financial identifiers linked to personal names"
}
```

### Hard negative

```json
{
  "id": "ctx_financial_hn_001",
  "text": "신용카드 번호가 16자리로 구성되는 일반적인 이유를 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "FINANCIAL_IDENTIFIER_CONTEXT",
  "template_id": "financial_general_explanation_v1",
  "notes": "general explanation, no actual financial identifier"
}
```

---

## 4.7 CONFIDENTIAL_BUSINESS_CONTEXT

### 의미

비공개 업무 정보, 고객/거래처 관련 비밀, 계약 조건, 가격 조건, 협상 조건, 매출, 견적, 내부 보고서, 사업 계획 등 외부 공개 대상이 아닌 비즈니스 값을 다루는 문맥.

### Positive 기준

```text
특정 고객/거래처/프로젝트와 연결된 계약 조건이나 단가 추출
비공개 매출, 견적, 영업 조건, 협상 조건 분석
대외비 업무 문서 요약
비공개 파트너/고객별 조건 비교
공개되지 않은 사업 계획이나 내부 보고서 변환
```

### Negative 기준

```text
계약서 일반 구성 설명
표준 계약서 템플릿 작성
공개 보도자료 요약
가상 사업계획 예시 생성
일반 영업 전략 설명
```

### Positive seed

```json
{
  "id": "ctx_business_001",
  "text": "가상회사 A와 체결한 공급 계약서에서 단가, 위약금, 결제 조건만 요약해줘.",
  "labels": ["CONFIDENTIAL_BUSINESS_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "business_contract_terms_v1",
  "notes": "specific non-public business terms tied to a named counterparty"
}
```

### Hard negative

```json
{
  "id": "ctx_business_hn_001",
  "text": "일반적인 공급계약서에 포함되는 주요 조항 목록을 알려줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "CONFIDENTIAL_BUSINESS_CONTEXT",
  "template_id": "business_contract_general_v1",
  "notes": "general contract knowledge, no non-public business data"
}
```

---

## 4.8 PROPRIETARY_TECHNICAL_CONTEXT

### 의미

사내 소스코드, 비공개 알고리즘, 업무 규칙, 가격 산정 로직, 추천/랭킹 로직, 필터링 로직, 내부 데이터 처리 로직 등 공개되지 않은 기술 자산을 다루는 문맥.

### Positive 기준

```text
첨부한 사내 코드의 핵심 로직 요약
비공개 알고리즘/정책/필터링 로직 분석
내부 계산식, 추천식, 스코어링 로직 설명 요청
사내 모듈이나 비공개 SDK 동작 방식 추출
```

### Negative 기준

```text
공개 라이브러리 사용법 설명
학습용 예제 코드 작성
오픈소스 코드 설명
일반 알고리즘 개념 설명
더미 데이터 기반 예제 코드
```

### Positive seed

```json
{
  "id": "ctx_proprietary_001",
  "text": "첨부한 가격 산정 모듈의 할인율 계산 로직을 설명하고 예외 케이스를 정리해줘.",
  "labels": ["PROPRIETARY_TECHNICAL_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "proprietary_logic_summary_v1",
  "notes": "asks to analyze non-public pricing logic from attached code"
}
```

### Hard negative

```json
{
  "id": "ctx_proprietary_hn_001",
  "text": "Python으로 할인율 계산 예제 함수를 만들어줘. 더미 데이터만 사용해.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT", "SYNTHETIC_DUMMY_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "PROPRIETARY_TECHNICAL_CONTEXT",
  "template_id": "generic_discount_code_example_v1",
  "notes": "generic educational code request with dummy data"
}
```

---

## 4.9 SECURITY_CONTROL_CONTEXT

### 의미

인증, 인가, 접근제어, 권한 정책, 보안 필터, allowlist, secret rotation, 탐지 규칙, 관리자 접근 구조, 보안 아키텍처 등 보안 통제나 접근 통제와 연결된 비공개 문맥.

### Positive 기준

```text
사내 인증/권한 구조 설명 요청
관리자 콘솔 접근제어 구조 분석
보안 필터링/탐지/차단 로직 분석
IP allowlist, IAM 정책, secret rotation 정책 요약
보안 우회 방지 로직 검토
```

### Negative 기준

```text
OAuth/OIDC 개념 설명
일반적인 접근제어 설계 방법 설명
공개 클라우드 보안 best practice 요약
학습용 보안 미들웨어 예제 작성
```

### Positive seed

```json
{
  "id": "ctx_security_001",
  "text": "사내 관리자 콘솔의 접근제어 구조와 IP allowlist 설계 결정을 요약해줘.",
  "labels": ["SECURITY_CONTROL_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "security_control_internal_v1",
  "notes": "internal access-control and allowlist design"
}
```

### Hard negative

```json
{
  "id": "ctx_security_hn_001",
  "text": "일반적인 웹서비스에서 관리자 페이지 접근제어를 설계하는 방법을 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "SECURITY_CONTROL_CONTEXT",
  "template_id": "security_control_general_v1",
  "notes": "general educational security architecture explanation"
}
```

---

## 4.10 INTERNAL_OPERATION_CONTEXT

### 의미

외부 공개 대상이 아닌 내부 운영 기록, 장애 보고서, incident report, 운영 로그, 내부 티켓, 배포 기록, 점검 결과, 내부 감사 기록, 시스템 상태 보고 등을 다루는 문맥.

### Positive 기준

```text
내부 장애 보고서 요약
운영 로그에서 장애 원인 추출
내부 티켓/업무 기록 정리
배포 실패 기록 분석
내부 점검 결과 보고서 요약
```

### Negative 기준

```text
장애 대응 절차 일반 설명
incident report 템플릿 작성
공개 postmortem 사례 요약
더미 로그 생성
```

### Positive seed

```json
{
  "id": "ctx_ops_001",
  "text": "첨부한 내부 장애 보고서에서 원인, 영향 범위, 재발 방지 대책을 요약해줘.",
  "labels": ["INTERNAL_OPERATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "internal_incident_report_v1",
  "notes": "non-public internal incident report"
}
```

### Hard negative

```json
{
  "id": "ctx_ops_hn_001",
  "text": "서비스 장애 보고서 템플릿을 만들어줘. 예시는 모두 더미 값으로 작성해줘.",
  "labels": ["TEMPLATE_OR_EMPTY_FORM_CONTEXT", "SYNTHETIC_DUMMY_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "INTERNAL_OPERATION_CONTEXT",
  "template_id": "incident_template_dummy_v1",
  "notes": "template request with dummy values only"
}
```

---

## 4.11 BULK_SENSITIVE_RECORD_CONTEXT

### 의미

여러 row, 여러 사람, 여러 고객, 여러 token, 여러 거래 기록처럼 민감값이 목록/표/CSV/XLSX/JSON 형태로 대량 처리되는 문맥.

이 라벨은 보통 다른 risk label과 함께 붙는다. 예를 들어 개인정보 목록이면 `PERSONAL_DATA_CONTEXT`와 함께 붙인다.

### Positive 기준

```text
고객 명단, 직원 명단, 지원자 명단, 계정 목록 처리
여러 secret/token/credential 후보 목록 추출
여러 거래/정산/환급 record 처리
XLSX/CSV/JSON table에서 민감 column 추출
row group 단위로 민감값이 반복됨
```

### Negative 기준

```text
단일 값의 형식 설명
빈 템플릿 표 생성
더미 데이터 생성
공개 통계표 요약
```

### Positive seed

```json
{
  "id": "ctx_bulk_001",
  "text": "첨부한 CSV에서 고객별 이름, 이메일, 결제 상태, 환급 계좌를 추출해서 새 표로 정리해줘.",
  "labels": ["PERSONAL_DATA_CONTEXT", "FINANCIAL_IDENTIFIER_CONTEXT", "BULK_SENSITIVE_RECORD_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "bulk_customer_financial_extract_v1",
  "notes": "bulk records containing personal and financial identifiers"
}
```

### Hard negative

```json
{
  "id": "ctx_bulk_hn_001",
  "text": "테스트용 더미 고객 데이터 20개를 JSON 배열로 만들어줘. 실제 개인정보는 사용하지 마.",
  "labels": ["SYNTHETIC_DUMMY_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "BULK_SENSITIVE_RECORD_CONTEXT",
  "template_id": "bulk_dummy_generation_v1",
  "notes": "bulk-shaped data but explicitly synthetic dummy values"
}
```

---

## 4.12 context suppressor labels

1.1.2에서 확정하는 suppressor label은 다음 6개다.

```text
GENERAL_EXPLANATION_CONTEXT
PUBLIC_SOURCE_CONTEXT
TEMPLATE_OR_EMPTY_FORM_CONTEXT
SYNTHETIC_DUMMY_CONTEXT
REDACTED_SANITIZED_CONTEXT
DEFENSIVE_TRANSFORMATION_CONTEXT
```

Suppressor는 allow 보장 신호가 아니다. Confirmed secret, high-risk PII, protected target, parser failure 등은 suppressor보다 우선할 수 있다.

---

## 4.13 GENERAL_EXPLANATION_CONTEXT

### 의미

민감값 자체를 처리하지 않고 일반 개념, 원리, 제도, 기술, 절차를 설명하는 문맥.

### 예시

```json
{
  "id": "ctx_general_001",
  "text": "OAuth access token과 refresh token의 차이를 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "general_auth_explanation_v1",
  "notes": "general technical explanation only"
}
```

---

## 4.14 PUBLIC_SOURCE_CONTEXT

### 의미

공개 법령, 공개 문서, 공개 GitHub repository, 공개 보도자료, 공식 문서 등 외부 공개 정보에 기반한 문맥.

### 예시

```json
{
  "id": "ctx_public_001",
  "text": "공개된 개인정보보호법의 주요 원칙을 요약해줘.",
  "labels": ["PUBLIC_SOURCE_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "public_legal_summary_v1",
  "notes": "request based on public legal information"
}
```

---

## 4.15 TEMPLATE_OR_EMPTY_FORM_CONTEXT

### 의미

빈 양식, 템플릿, 체크리스트, 예시 구조, placeholder가 포함된 문서 생성/검토 문맥.

### 예시

```json
{
  "id": "ctx_template_001",
  "text": "개인정보 처리방침 검토 체크리스트를 만들어줘.",
  "labels": ["TEMPLATE_OR_EMPTY_FORM_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "privacy_checklist_template_v1",
  "notes": "checklist request without actual personal data"
}
```

---

## 4.16 SYNTHETIC_DUMMY_CONTEXT

### 의미

명확하게 더미, 테스트, 합성, 예시, 가상 데이터임을 밝힌 문맥.

### 예시

```json
{
  "id": "ctx_dummy_001",
  "text": "테스트용 더미 고객 데이터 5개를 JSON 형식으로 만들어줘. 실제 개인정보는 사용하지 마.",
  "labels": ["SYNTHETIC_DUMMY_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "dummy_data_generation_v1",
  "notes": "explicit request for dummy data and no real personal information"
}
```

---

## 4.17 REDACTED_SANITIZED_CONTEXT

### 의미

본문 값이 명확히 마스킹, 익명화, 비식별화, `[REDACTED]`, `<MASKED>`, `***` 등으로 처리된 문맥.

### 예시

```json
{
  "id": "ctx_redacted_001",
  "text": "이름과 이메일이 모두 [REDACTED] 처리된 고객 문의 요약문의 문장을 다듬어줘.",
  "labels": ["REDACTED_SANITIZED_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "redacted_text_review_v1",
  "notes": "explicitly redacted content with no visible sensitive values"
}
```

---

## 4.18 DEFENSIVE_TRANSFORMATION_CONTEXT

### 의미

민감값을 유출하려는 것이 아니라 탐지, 마스킹, 익명화, 비식별화, 검증, 정책 적용을 요청하는 방어적 처리 문맥.

이 라벨은 조심해서 사용한다. 실제 민감값이 포함되어 있으면 policy가 mask/block할 수 있다. 이 라벨은 “의도가 방어적임”을 나타낼 뿐이다.

### 예시

```json
{
  "id": "ctx_defensive_001",
  "text": "아래 문장에서 개인정보로 보이는 값을 찾아서 모두 [MASKED]로 바꿔줘.",
  "labels": ["DEFENSIVE_TRANSFORMATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "defensive_masking_v1",
  "notes": "asks for masking rather than disclosure or reuse"
}
```

---

## 5. pii_relevance_dataset

## 5.1 역할

`pii_relevance_dataset`은 Stage 0에서 PII-like span이 탐지된 뒤, 그 span이 실제 개인정보인지, 예시값인지, 작업상 필요한 값인지 판단한다.

이 dataset은 single-label로 관리한다.

확정 label:

```text
example_or_format
real_personal_data
needed_for_task
bulk_sensitive_data
uncertain
```

권장 row schema:

```json
{
  "id": "pii_phone_example_001",
  "segment_text": "전화번호 형식은 010-0000-0000처럼 작성합니다.",
  "pii_type": "phone",
  "span_text_policy": "dummy_or_synthetic_only",
  "label": "example_or_format",
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "phone_format_example_v1",
  "notes": "phone-like value is a format example"
}
```

### 5.2 label 기준

| Label | 붙이는 경우 | 붙이지 않는 경우 |
|---|---|---|
| `example_or_format` | 형식 설명, placeholder, 명확한 더미값 | 실제 사람/고객 record |
| `real_personal_data` | 실제 개인 record처럼 쓰이는 값 | 더미/템플릿/형식 설명 |
| `needed_for_task` | 마스킹/검증/비식별화 등 작업 수행에 필요한 값 | 단순 추출/전송/재정리 |
| `bulk_sensitive_data` | 여러 명/여러 row의 개인정보 | 단일 값 설명 |
| `uncertain` | 문맥 부족으로 판단 불가 | 충분히 명확한 예시/실제/더미 |

### 5.3 seed 예시

```json
{"id":"pii_example_001","segment_text":"전화번호 형식은 010-0000-0000처럼 작성합니다.","pii_type":"phone","label":"example_or_format","language":"ko","source_type":"seed","case_type":"positive","template_id":"phone_format_example_v1","notes":"format example"}
{"id":"pii_real_001","segment_text":"홍테스트 고객의 연락처는 010-0000-1234이고 배송지는 서울시 테스트구 샘플로 1입니다.","pii_type":"name,phone,address","label":"real_personal_data","language":"ko","source_type":"seed","case_type":"positive","template_id":"personal_record_v1","notes":"PII-like values appear in a personal customer record context"}
{"id":"pii_needed_001","segment_text":"이 전화번호 010-0000-1234를 010-****-1234 형식으로 마스킹해줘.","pii_type":"phone","label":"needed_for_task","language":"ko","source_type":"seed","case_type":"positive","template_id":"pii_masking_task_v1","notes":"value is needed for masking task"}
{"id":"pii_bulk_001","segment_text":"아래 고객 명단에서 이름, 이메일, 전화번호를 추출해서 CSV로 정리해줘.","pii_type":"name,email,phone","label":"bulk_sensitive_data","language":"ko","source_type":"seed","case_type":"positive","template_id":"bulk_pii_extract_v1","notes":"bulk personal data extraction request"}
{"id":"pii_uncertain_001","segment_text":"김테스트 / 010-0000-1234 / sample@example.test","pii_type":"name,phone,email","label":"uncertain","language":"ko","source_type":"seed","case_type":"positive","template_id":"bare_pii_values_v1","notes":"bare PII-like values with insufficient context"}
```

---

## 6. code_sensitivity_dataset

## 6.1 역할

`code_sensitivity_dataset`은 code segment가 일반 예제인지, 공개 라이브러리 사용인지, 비공개 로직인지, 보안 중요 로직인지, 데이터 접근 로직인지, 인프라 설정인지 분류한다.

이 dataset은 multi-label로 관리한다.

확정 label:

```text
CODE_GENERIC_EXAMPLE
CODE_PUBLIC_OR_LIBRARY_USAGE
CODE_PROPRIETARY_LOGIC
CODE_SECURITY_CRITICAL_LOGIC
CODE_DATA_ACCESS_LOGIC
CODE_INFRA_CONFIG
```

권장 row schema:

```json
{
  "id": "code_security_001",
  "code_text": "def verify_token(token):\n    payload = decode_jwt(token)\n    if payload.get('role') != 'admin':\n        raise PermissionError('forbidden')\n    return payload",
  "labels": ["CODE_SECURITY_CRITICAL_LOGIC"],
  "language": "python",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "token_verification_logic_v1",
  "notes": "authentication and authorization logic"
}
```

### 6.2 label 기준

| Label | 붙이는 경우 |
|---|---|
| `CODE_GENERIC_EXAMPLE` | hello world, 단순 반복문, 학습용 더미 예제 |
| `CODE_PUBLIC_OR_LIBRARY_USAGE` | pandas, requests, React, FastAPI 등 공개 라이브러리 일반 사용 |
| `CODE_PROPRIETARY_LOGIC` | 비공개 업무 규칙, 가격 계산, 추천/랭킹, 승인 조건 |
| `CODE_SECURITY_CRITICAL_LOGIC` | 인증, 인가, 암호화, token 검증, secret 검증, 보안 필터 |
| `CODE_DATA_ACCESS_LOGIC` | DB query, 고객 데이터 조회, 내부 API 호출, export |
| `CODE_INFRA_CONFIG` | env, Docker, Kubernetes, CI/CD, Terraform, Nginx, secret config |

### 6.3 seed 예시

```json
{"id":"code_generic_001","code_text":"for i in range(5):\n    print(i)","labels":["CODE_GENERIC_EXAMPLE"],"language":"python","source_type":"seed","case_type":"positive","template_id":"generic_loop_example_v1","notes":"simple educational loop example"}
{"id":"code_lib_001","code_text":"import pandas as pd\n\ndf = pd.read_csv('sample.csv')\nprint(df.head())","labels":["CODE_PUBLIC_OR_LIBRARY_USAGE"],"language":"python","source_type":"seed","case_type":"positive","template_id":"public_library_usage_v1","notes":"public pandas library usage with sample file"}
{"id":"code_prop_001","code_text":"def calculate_discount(customer_tier, renewal_months):\n    if customer_tier == 'enterprise' and renewal_months >= 12:\n        return 0.18\n    return 0.05","labels":["CODE_PROPRIETARY_LOGIC"],"language":"python","source_type":"seed","case_type":"positive","template_id":"proprietary_discount_logic_v1","notes":"business pricing policy encoded as code"}
{"id":"code_security_001","code_text":"def verify_token(token):\n    payload = decode_jwt(token)\n    if payload.get('role') != 'admin':\n        raise PermissionError('forbidden')\n    return payload","labels":["CODE_SECURITY_CRITICAL_LOGIC"],"language":"python","source_type":"seed","case_type":"positive","template_id":"token_verification_logic_v1","notes":"authentication and authorization logic"}
{"id":"code_data_001","code_text":"query = \"SELECT name, email, phone FROM customers WHERE status = 'active'\"","labels":["CODE_DATA_ACCESS_LOGIC"],"language":"sql","source_type":"seed","case_type":"positive","template_id":"customer_query_logic_v1","notes":"query accesses customer personal fields"}
{"id":"code_infra_001","code_text":"DATABASE_URL=${DB_URL}\nJWT_SECRET=${JWT_SECRET}\nALLOWED_ORIGINS=https://admin.example.test","labels":["CODE_INFRA_CONFIG","CODE_SECURITY_CRITICAL_LOGIC"],"language":"env","source_type":"seed","case_type":"positive","template_id":"infra_secret_config_v1","notes":"infra config with security-sensitive environment variables"}
```

---

## 7. OCR fixture dataset

OCR fixture는 classifier 학습용이 아니다.

목적:

```text
OCR parser가 text block을 생성하는지 확인
OCR text가 Stage 0 scanner로 전달되는지 확인
OCR text 안의 PII/secret이 탐지되는지 확인
OCR 실패/무텍스트/민감정보 발견 정책이 작동하는지 확인
```

권장 label format:

```json
{
  "id": "ocr_phone_clean_001",
  "image_path": "generated_images/clean/ocr_phone_clean_001.png",
  "expected_text_contains": ["010-1111-1111"],
  "expected_findings": ["PII_PHONE"],
  "expected_policy_balanced": "finding_based",
  "expected_policy_strict": "finding_based",
  "notes": "clean Korean phone text image"
}
```

OCR fixture는 exact OCR text보다 `expected_findings`를 primary assertion으로 사용한다.

---

## 8. Seed 작성 수량

### 8.1 1차 최소 수량

```text
context risk labels: 8 labels × 20 = 160
context suppressor labels: 6 labels × 20 = 120
context mixed/boundary cases: 60
pii_relevance labels: 5 labels × 20 = 100
code_sensitivity labels: 6 labels × 20 = 120
code mixed cases: 30
```

1차 총량:

```text
약 590 samples
```

### 8.2 권장 수량

```text
각 context risk label: 50 positive + 15 hard negative
각 suppressor label: 50 positive
PII relevance 각 label: 50
Code sensitivity 각 label: 50
hard_eval: label별 20개 이상
```

---

## 9. Hard negative 작성법

Hard negative는 특정 risk label을 과탐하지 않도록 만드는 샘플이다.

필수 필드:

```json
{
  "case_type": "hard_negative",
  "target_risk_label": "SECRET_CREDENTIAL_CONTEXT"
}
```

좋은 hard negative는 다음 조건을 만족한다.

```text
위험 라벨의 핵심 단어를 포함한다.
하지만 실제 위험 의도는 없다.
일반 설명, 공개 정보, 템플릿, 더미, 마스킹 요청 중 하나다.
왜 negative인지 notes에 설명되어 있다.
```

예:

```json
{
  "id": "ctx_secret_hn_002",
  "text": "환경변수에 API key를 저장하는 보안상 이유를 설명해줘.",
  "labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "hard_negative",
  "target_risk_label": "SECRET_CREDENTIAL_CONTEXT",
  "template_id": "secret_best_practice_explanation_v1",
  "notes": "mentions API key but asks for best-practice explanation only"
}
```

---

## 10. Synthetic sample 생성 규칙

Synthetic은 seed를 확장하는 용도다. 라벨 체계를 새로 만들거나 애매한 sample을 양산하는 용도로 쓰지 않는다.

### 10.1 허용 변형

```text
한국어 ↔ 영어 ↔ 한영혼합
명령형 ↔ 질문형
요약 요청 ↔ 추출 요청 ↔ 표 변환 요청
composer prompt ↔ file segment 느낌
짧은 요청 ↔ 긴 문서 단락
단일 record ↔ 여러 record
첨부파일 기반 표현 추가
```

### 10.2 금지 변형

```text
실제 회사명/개인정보/secret 삽입
label 이름을 text에 삽입
target 이름만 바꾼 반복문 대량 생성
positive를 negative로 바꿔야 하는데 label을 그대로 유지
source seed와 template_id 연결을 끊음
```

### 10.3 synthetic row 필드

```json
{
  "id": "ctx_secret_syn_001",
  "text": "Use this test access token to build a curl request for the internal billing API.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "language": "en",
  "source_type": "synthetic",
  "case_type": "positive",
  "template_id": "secret_api_call_v1",
  "parent_seed_id": "ctx_secret_001",
  "generation_method": "paraphrase_v1",
  "notes": "English paraphrase of credential-use request"
}
```

---

## 11. 검수 기준

### 11.1 자동 필터

Synthetic 생성 후 자동으로 다음을 검사한다.

```text
실제 secret pattern 의심값 제거
실제 주민등록번호/카드번호/전화번호 의심값 제거
label 이름 직접 노출 제거
placeholder만 반복하는 sample 제거
text 길이 너무 짧은 sample 제거
중복/near-duplicate 제거
template_id 누락 제거
notes 누락 제거
case_type 누락 제거
hard_negative의 target_risk_label 누락 제거
```

### 11.2 사람 검수

사람은 다음을 확인한다.

```text
라벨 정의와 sample이 일치하는가?
positive와 hard negative의 경계가 명확한가?
risk label이 너무 많이 붙지 않았는가?
suppressor label이 allow 보장처럼 오해되지 않는가?
같은 target이 risky/normal 양쪽에 존재하는가?
source_type과 case_type이 맞는가?
notes가 라벨링 근거를 설명하는가?
```

---

## 12. Split 규칙

비율:

```text
train: 70%
valid: 15%
test: 15%
```

규칙:

```text
같은 template_id에서 나온 sample은 같은 split에만 둔다.
같은 parent_seed_id에서 나온 seed/synthetic은 같은 split에 둔다.
hard_eval sample은 train/valid/test에 넣지 않는다.
error_bank에서 가져온 회귀 테스트 sample은 별도 hard_eval 후보로 관리한다.
label별 분포가 split마다 크게 무너지지 않게 한다.
```

---

## 13. 학습 전 처리

학습 전 pipeline:

```text
1. raw JSONL schema validation
2. raw 관리 필드와 학습 필드 분리
3. label_map 생성
4. text normalization
5. Qwen embedding 추출
6. X matrix와 Y matrix 생성
7. One-vs-Rest 학습용 label별 binary target 생성
8. train/valid/test split 적용
```

### 13.1 학습에 들어가는 필드

Context classifier 학습에 실제로 들어가는 값은 다음 두 개다.

```text
text   → Qwen embedding 입력
labels → multi-hot target 생성
```

다음 필드는 학습 feature로 사용하지 않는다.

```text
id
language
source_type
case_type
template_id
parent_seed_id
target_risk_label
notes
```

이 필드들은 split, 검수, 통계, error analysis, 재현성 관리에만 사용한다.

### 13.2 context_dataset multi-label 변환

`context_dataset`은 multi-label이다. 하나의 row가 여러 risk/suppressor label을 동시에 가질 수 있다.

예:

```json
{
  "text": "첨부한 CSV에서 고객별 이름, 이메일, 결제 상태, 환급 계좌를 추출해서 새 표로 정리해줘.",
  "labels": [
    "PERSONAL_DATA_CONTEXT",
    "FINANCIAL_IDENTIFIER_CONTEXT",
    "BULK_SENSITIVE_RECORD_CONTEXT"
  ]
}
```

내부에서는 label list를 multi-hot vector로 바꾼다.

```text
SECRET_CREDENTIAL_CONTEXT       = 0
PERSONAL_DATA_CONTEXT           = 1
FINANCIAL_IDENTIFIER_CONTEXT    = 1
CONFIDENTIAL_BUSINESS_CONTEXT   = 0
PROPRIETARY_TECHNICAL_CONTEXT   = 0
SECURITY_CONTROL_CONTEXT        = 0
INTERNAL_OPERATION_CONTEXT      = 0
BULK_SENSITIVE_RECORD_CONTEXT   = 1
GENERAL_EXPLANATION_CONTEXT     = 0
PUBLIC_SOURCE_CONTEXT           = 0
TEMPLATE_OR_EMPTY_FORM_CONTEXT  = 0
SYNTHETIC_DUMMY_CONTEXT         = 0
REDACTED_SANITIZED_CONTEXT      = 0
DEFENSIVE_TRANSFORMATION_CONTEXT = 0
```

One-vs-Rest 학습에서는 각 label마다 별도의 binary target을 만든다.

```text
PERSONAL_DATA_CONTEXT classifier:
  해당 row의 target = 1

FINANCIAL_IDENTIFIER_CONTEXT classifier:
  해당 row의 target = 1

SECRET_CREDENTIAL_CONTEXT classifier:
  해당 row의 target = 0
```

### 13.3 dataset별 label 방식

| Dataset | Label 방식 | 학습 target 형태 |
|---|---|---|
| `context_dataset` | multi-label | `labels[]` → multi-hot vector |
| `pii_relevance_dataset` | single-label | `label` → class index 또는 one-hot vector |
| `code_sensitivity_dataset` | multi-label | `labels[]` → multi-hot vector |

`pii_relevance_dataset`은 하나의 PII span을 `example_or_format`, `real_personal_data`, `needed_for_task`, `bulk_sensitive_data`, `uncertain` 중 하나로 판단한다. 따라서 기본은 single-label이다.

`code_sensitivity_dataset`은 하나의 code segment가 `CODE_INFRA_CONFIG`이면서 동시에 `CODE_SECURITY_CRITICAL_LOGIC`일 수 있으므로 multi-label이다.

### 13.4 processed training row 생성

Raw seed row에서 학습에 필요한 필드만 뽑아 processed row를 만든다.

Raw row:

```json
{
  "id": "ctx_secret_001",
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "language": "ko",
  "source_type": "seed",
  "case_type": "positive",
  "template_id": "secret_api_call_v1",
  "notes": "credential-like token is used to construct an API call"
}
```

Processed training row:

```json
{
  "id": "ctx_secret_001",
  "text": "이 테스트 API 토큰을 사용해서 내부 결제 API 호출 curl 명령어를 만들어줘.",
  "labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "split": "train"
}
```

Embedding cache나 Stage 0 scan 결과는 processed training row에 직접 섞지 않는다. 필요하면 별도 cache/report 파일로 관리한다.

---

## 14. Threshold 보정

학습 후 classifier는 label별 score를 낸다. 이 score를 실제 hit로 볼 기준은 `thresholds.json`에 저장한다.

Threshold는 valid set에서 label별로 따로 고른다.

예:

```json
{
  "context": {
    "SECRET_CREDENTIAL_CONTEXT": 0.55,
    "PERSONAL_DATA_CONTEXT": 0.65,
    "FINANCIAL_IDENTIFIER_CONTEXT": 0.65,
    "CONFIDENTIAL_BUSINESS_CONTEXT": 0.70,
    "PROPRIETARY_TECHNICAL_CONTEXT": 0.70,
    "SECURITY_CONTROL_CONTEXT": 0.70,
    "INTERNAL_OPERATION_CONTEXT": 0.72,
    "BULK_SENSITIVE_RECORD_CONTEXT": 0.60
  }
}
```

Threshold 방향성:

```text
secret/credential은 recall 우선
bulk sensitive record는 recall 우선
business/proprietary/internal은 precision과 recall 균형
suppressor는 risk 무효화가 아니라 severity 보정에만 사용
```

---

## 15. Error bank

평가 중 틀린 sample은 error bank에 기록한다.

필드:

```json
{
  "id": "err_ctx_001",
  "source_dataset": "context_dataset",
  "text": "API key를 환경변수로 관리하는 이유를 설명해줘.",
  "true_labels": ["GENERAL_EXPLANATION_CONTEXT"],
  "predicted_labels": ["SECRET_CREDENTIAL_CONTEXT"],
  "error_type": "false_positive",
  "target_label": "SECRET_CREDENTIAL_CONTEXT",
  "model_version": "qwen_context_classifier_2026_06_09",
  "notes": "general explanation misclassified as secret use"
}
```

Error bank 사용법:

```text
false positive → hard negative 후보
false negative → positive seed 보강 후보
near threshold → threshold calibration 검토 후보
risk/suppressor conflict → Gemma judge trigger test 후보
```

---

## 16. 완료 기준

1차 dataset 구축 완료 기준:

```text
모든 label의 seed 최소 수량 충족
hard negative가 risk label별 최소 10개 이상 존재
JSONL schema validation 통과
label 이름 직접 노출 sample 0개
실제 민감정보 sample 0개
template_id 누락 0개
notes 누락 0개
train/valid/test split 완료
hard_eval이 train에 포함되지 않음
model_card 초안 작성
```

모델 교체 가능 기준:

```text
fixed hard_eval 통과
label별 precision/recall/F1 report 존재
false positive/false negative error bank 기록
thresholds.json 저장
label_map.json 저장
qwen_context_classifier.joblib 저장
qwen_pii_relevance_classifier.joblib 저장
qwen_code_classifier.joblib 저장
```
