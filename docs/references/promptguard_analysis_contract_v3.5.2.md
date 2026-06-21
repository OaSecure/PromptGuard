# PromptGuard 분석 파이프라인 개발 실행 계약서 v3.5.2

문서 버전: `v3.5.2`
계약 스키마 버전: `v3`
계약명: `implementation-boundary-contract`
적용 범위: PromptGuard extension/API/analyze service/file parser/OCR/parser worker/runtime worker/ML pipeline/policy decision/privacy storage/event storage/extension response compatibility

`schema_version="v3"`는 public Analyze API compatibility version이다. 문서 버전 `v3.5.2`와 독립적으로 유지되며, extension compatibility와 legacy adapter compatibility 검토 없이 변경하지 않는다.

---

## 1. 계약 목적

이 문서는 PromptGuard의 extension, API route, AnalyzeService, File Parser, OCR/parser worker, lexical scanner, ML pipeline, Policy Orchestrator, EventStorage가 하나의 구현 가능한 파이프라인으로 연결되도록 고정하는 개발 실행 계약서다.

v3.5는 모듈 경계, 타입 계약, 구현 책임, storage/privacy 규칙, worker runtime, 테스트 게이트, PR 실행 순서를 함께 정의한다. 모든 구현은 이 문서의 pipeline order, public schema, service-local schema, parser schema, ML schema, policy schema, event schema, storage allowlist, response compatibility를 기준으로 한다.

v3.5는 기존 pipeline order, privacy/storage 원칙, SOLID/TDD 원칙, extension response compatibility를 유지하면서 다음 구현 공백을 해소한다.

* extension file handling과 server-side File Parser의 연결
* paste/drop/attach/send interception과 upload/temp file flow의 연결
* `file_ref`와 encrypted temporary processing storage의 lifecycle
* PDF native text extraction과 OCR fallback
* image OCR
* Office document parsing
* spreadsheet parsing
* slide parsing
* code/text file parsing
* `ParsedDocument / ParsedBlock`의 extraction provenance
* 기존 rule/filter detector 결과와 `LexicalSignal`의 연결
* Route, AnalyzeService, Policy Orchestrator, EventStorage의 책임 분리
* extension response compatibility
* SOLID 원칙 기반 의존성 분리
* TDD 기반 test gate와 PR merge gate
* permissive open-source OCR/parser dependency 정책
* ParserAdapter / ParserRegistry / OcrEnginePort / TemporaryFileResolverPort 경계
* PDF native text extraction + page-level OCR fallback
* parser/OCR license artifact, performance budget, static quality gate

Schema 변경은 “Schema 변경 관리 규칙”을 따른다.

---

## 2. 전체 분석 파이프라인

High-level pipeline은 logical stage 이름으로만 표현한다. Runtime component, adapter, registry, resolver, executor, port는 해당 logical stage 내부 구현이며 새로운 최상위 pipeline stage가 아니다.

```text
Raw input / file_ref
→ File Parser
→ ParsedDocument / ParsedBlock
→ RepeatedSpecialCharNormalizer
→ Lexical Signal Scanner
→ AnalysisAtom Builder
→ Qwen3 Atom Embedding Worker
→ Adjacent Semantic Segmenter
→ Signal-to-Segment Mapper
→ SegmentEmbedding Builder
→ Logistic Regression Segment Classifier
→ KLUE RoBERTa Context Verifier, LR candidate segment-label pairs only
→ Policy Orchestrator
→ UserNotice generation
→ EventStorage allowlist metadata write
→ AnalyzeResponse
```

Runtime 실행 순서는 다음과 같다.

```text
Extension paste/drop/attach/send hook
→ upload/temp file endpoint, only for File/Blob handle
→ encrypted temporary processing storage
→ opaque file_ref
→ Analyze API Route
→ AnalyzeService
→ ParserWorkerPool
→ RepeatedSpecialCharNormalizer
→ Lexical Signal Scanner
→ AnalysisAtom Builder
→ Qwen3 Atom Embedding Worker
→ Adjacent Semantic Segmenter
→ Signal-to-Segment Mapper
→ SegmentEmbedding Builder
→ Logistic Regression Segment Classifier
→ RobertaVerifierWorker, LR candidate segment-label pairs only
→ Policy Orchestrator
→ UserNotice generation
→ EventStorage allowlist metadata write
→ AnalyzeResponse
→ Extension response action adapter
```

Stage와 runtime component 관계는 다음 기준으로 고정한다.

| logical stage | runtime component | internal implementation detail |
| --- | --- | --- |
| File Parser | `ParserWorkerPool` | `FileParserRunner`, `TemporaryFileResolverPort`, `ParserPlanResolver`, `ParserPlanExecutor`, `ParserAdapter`, `OcrEnginePort`, renderer port |
| RepeatedSpecialCharNormalizer | normalizer service | `NormalizationPolicy`, offset mapper |
| Lexical Signal Scanner | scanner service | rule snapshot, protected target matcher, regex/keyword/fingerprint matcher |
| Qwen3 Atom Embedding Worker | embedding worker | singleton model loader, `EmbeddingModelPort` |
| KLUE RoBERTa Context Verifier | verifier worker | LR candidate-gated verifier request builder, `VerifierModelPort` |
| Policy Orchestrator | policy service | policy rule set, reason registry, response decision builder |
| UserNotice/EventStorage | serializer/writer | notice template renderer, privacy allowlist serializer, `EventWriterPort` |

실행 순서 계약:

1. Extension은 composer text, converted paste text, attachment metadata, File/Blob handle을 수집한다.
2. Extension은 파일 내부를 읽지 않고, 파일에서 text를 추출하지 않고, OCR을 수행하지 않는다.
3. File/Blob handle을 확보한 파일 입력은 upload/temp file endpoint를 통해 `file_ref`로 전환한다.
4. Analyze JSON body는 raw file bytes, base64 file payload, OCR text, extracted text, original file name을 포함하지 않는다.
5. `Analyze API Route`는 request validation, auth/session context extraction, legacy compatibility adapter 적용, `AnalyzeService` 호출만 수행한다.
6. `AnalyzeService`는 public `AnalyzeInputItem[]`을 service-local `InputEnvelope[]`로 정규화하고, `InputEnvelope`를 다른 module의 공용 타입으로 노출하지 않는다.
7. text input과 file_reference input은 `ParserWorkerPayload`로 변환되어 `ParserWorkerPool`을 거친다. `attachment_metadata`와 `unsupported_attachment`는 raw content가 없으므로 `ParserWorkerPayload`를 만들지 않고 content-not-scanned evidence로 policy에 전달한다.
8. `ParserWorkerPayload`는 coarse `extraction_requirement`만 담는다. 구체 parser 실행 계획은 worker 내부 `ParserPlanResolver`가 `ParserExecutionPlan`으로 만든다.
9. `ParserWorkerPool`은 queue, timeout, backpressure, lifecycle, crash isolation, structured failure boundary만 담당한다. PDF parsing, OCR, adapter selection, plan resolution, policy decision은 직접 수행하지 않는다.
10. `FileParserRunner`는 parser worker runtime 내부에서 `TemporaryFileResolverPort`, `ParserPlanResolver`, `ParserPlanExecutor`를 조율해 `FileParserResult`를 반환한다.
11. `File Parser` logical stage는 text wrapper, PDF, image, Office, spreadsheet, slide, code/text file을 `ParsedDocument`로 표준화한다. OCR은 독립 pipeline stage가 아니라 File Parser 내부 extraction method다.
12. `RepeatedSpecialCharNormalizer`는 keyword/regex scanner 전에 실행한다.
13. normalizer는 original text를 덮어쓰지 않고 normalized text와 offset mapping을 만든다.
14. `Lexical Signal Scanner`는 normalized text를 대상으로 탐지할 수 있으며, scanner signal 위치는 original text 기준으로 복원 가능해야 한다.
15. `AnalysisAtom Builder`는 original text 기준 atom을 만든다.
16. Qwen3 embedding worker는 singleton model loader를 사용하고, Qwen3 embedding model은 runtime fine-tuning, online learning, gradient update 없이 freeze된 inference model로만 사용한다.
17. AnalysisAtom Builder 이후의 atomization, embedding, segmenting, mapping, segment embedding, classification, verification 단계에서는 keyword/regex scanner를 다시 호출하지 않는다.
18. signal은 segment 생성 후 offset overlap 또는 atom membership 기준으로 segment에 매핑한다.
19. LR classifier는 model artifact를 load해 inference만 수행하고, LR candidate segment-label result를 생성한다. final action은 결정하지 않는다.
20. RoBERTa verifier worker는 LR candidate segment-label pair만 처리한다. LR이 만들지 않은 label이나 segment candidate를 새로 추가하거나 복구하지 않는다.
21. verifier timeout/failed result는 allow 근거가 아니다.
22. `Policy Orchestrator`만 final action, reason_code, severity를 결정한다.
23. `UserNotice`는 policy decision을 사용자 표시용 template으로 변환한다. `EventStorage`는 privacy allowlist metadata만 저장한다.
24. temp file은 TTL 만료 또는 analyze completion 이후 cleanup 대상이다.

---

## 3. 절대 불변 원칙

| id | 원칙 |
| --- | --- |
| I-01 | Extension은 파일 내부를 읽지 않는다. |
| I-02 | Extension은 파일에서 text를 추출하지 않는다. |
| I-03 | Extension은 OCR을 수행하지 않는다. |
| I-04 | Extension은 파일 바이트 또는 base64 file payload를 analyze JSON body에 넣지 않는다. |
| I-05 | File/Blob handle을 확보할 수 있는 파일 입력은 upload/temp file flow로 `file_ref`를 만든다. |
| I-06 | `file_ref`는 opaque reference이며 영구 파일 ID, local path, URL, 파일명, 확장자, MIME 문자열을 포함하지 않는다. |
| I-07 | raw file bytes는 encrypted temporary processing storage에만 둘 수 있다. |
| I-08 | EventStorage는 raw file bytes, temp file path, parsed file content, extracted text, OCR text, original file name, document title, author, sheet name, OCR input image dump, parser input dump, exact OCR confidence를 저장하지 않는다. |
| I-09 | keyword/regex scan 전에 `RepeatedSpecialCharNormalizer`를 실행한다. |
| I-10 | normalizer는 original text를 덮어쓰지 않고 offset mapping을 반드시 유지한다. |
| I-11 | scanner는 normalized text를 대상으로 탐지할 수 있고 original text 기준 range 복원이 가능해야 한다. |
| I-12 | AnalysisAtom Builder 이후의 atomization, embedding, segmenting, mapping, segment embedding, classification, verification 단계에서는 keyword/regex scanner를 다시 호출하지 않는다. |
| I-13 | signal은 segment 생성 후 offset overlap 또는 atom membership 기준으로 segment에 매핑한다. |
| I-14 | Qwen3 embedding model은 freeze하며 runtime fine-tuning, online learning, gradient update를 수행하지 않는다. |
| I-15 | 1차 문맥 분류기의 학습 대상은 One-vs-Rest Logistic Regression classifier다. |
| I-16 | KLUE RoBERTa Context Verifier의 학습 대상은 LR candidate segment-label pair에 대한 label-aware binary verifier다. |
| I-17 | Logistic Regression classifier와 RoBERTa verifier는 final action을 직접 결정하지 않는다. |
| I-18 | RoBERTa verifier는 LR이 제안한 segment-label pair만 confirm/reject/timeout/failed 상태로 반환하고, label이나 segment candidate를 새로 추가하지 않는다. |
| I-19 | final action은 오직 `Policy Orchestrator`가 결정한다. |
| I-20 | file-derived content에는 `masked_prompt`를 생성하지 않는다. |
| I-21 | composer text와 converted paste text만 `masked_prompt` 대상이 될 수 있다. |
| I-22 | parser/OCR failure는 allow 근거가 아니다. |
| I-23 | unsupported/content unavailable attachment는 `CONTENT_NOT_SCANNED` evidence로 policy에 전달한다. |
| I-24 | persistent storage, logs, EventStorage에는 raw text, normalized text, OCR text, extracted text, atom text, segment text, secret value, detected raw value, embedding vector, segment vector, exact classifier score, verifier raw logits, raw file bytes, original file name, full masked prompt를 저장하지 않는다. |
| I-25 | `hard_eval`은 train/dev/threshold tuning/model selection에 사용하지 않는다. |
| I-26 | OCR은 독립 pipeline stage가 아니라 File Parser / ParserWorkerPool 내부 extraction method다. |
| I-27 | 기본 OCR/parser dependency는 permissive open-source license와 license scan gate를 통과해야 한다. |
| I-28 | PyMuPDF, MuPDF, Ghostscript, Poppler, pdf2image, cloud OCR API, closed-source OCR SDK는 기본 구현에서 금지한다. |
| I-29 | `schema_version="v3"`는 public Analyze API compatibility version이며 문서 버전 `v3.5`와 독립적으로 유지한다. |
| I-30 | Route, Scanner, Classifier, Verifier, Parser는 final action, reason_code, user notice를 결정하지 않는다. |

---

## 4. Public Analyze Request Contract

Public analyze request는 `inputs[]` 기반 구조를 사용한다. `schema_version="v3"`는 public Analyze API compatibility version이며 문서 버전과 독립적으로 유지된다.

```python
from typing import Literal
from pydantic import BaseModel

FileKind = Literal[
    "plain_text",
    "image",
    "pdf",
    "office_document",
    "spreadsheet",
    "slide",
    "code",
    "unknown",
]

SizeBucket = Literal["empty", "tiny", "small", "medium", "large", "huge", "unknown"]

ContentUnavailableReason = Literal[
    "oversized",
    "unsupported",
    "unsupported_type",
    "metadata_only",
    "unavailable",
    "raw_file_unavailable",
    "parser_disabled",
    "ocr_disabled",
    "encrypted",
]

class AnalyzeInputItem(BaseModel):
    input_id: str
    kind: Literal[
        "text",
        "file_reference",
        "attachment_metadata",
        "unsupported_attachment",
    ]
    source: Literal[
        "composer",
        "converted_paste",
        "pasted_file",
        "pasted_image",
        "screenshot_image",
        "attached_file",
        "attachment_chip",
    ]
    content_included: bool

    content: str | None = None
    file_ref: str | None = None
    file_kind: FileKind | None = None

    mime: str | None = None
    extension: str | None = None
    size_bucket: SizeBucket | None = None

    content_unavailable_reason: ContentUnavailableReason | None = None

class AnalyzeRequest(BaseModel):
    request_id: str
    login_id: str
    schema_version: Literal["v3"] = "v3"
    extension_version: str | None = None
    inputs: list[AnalyzeInputItem]
```

Input invariant:

* `kind="text"`는 `source="composer"` 또는 `source="converted_paste"`만 허용한다.
* `kind="file_reference"`는 `source="pasted_file"`, `source="pasted_image"`, `source="screenshot_image"`, `source="attached_file"`만 허용한다.
* `kind="attachment_metadata"`는 `source="attachment_chip"`, `source="pasted_file"`, `source="pasted_image"`, `source="screenshot_image"`, `source="attached_file"`만 허용한다.
* `kind="unsupported_attachment"`는 `source="attachment_chip"`, `source="pasted_file"`, `source="pasted_image"`, `source="screenshot_image"`, `source="attached_file"`만 허용한다.
* `content_included=true`는 `kind="text"`에서만 허용되며 `content`가 non-null이어야 한다.
* `content_included=false`이면 `content`는 null이어야 한다.
* `kind="text"`에서 `content=""`는 schema level에서 허용할 수 있으나, whitespace-only content는 AnalyzeService input normalization에서 blank input으로 처리한다.
* `kind="file_reference"`이면 `file_ref`는 required이고 `content`는 null이어야 한다.
* `file_ref`는 opaque reference여야 하며 local path, URL, original file name, user-visible file name, file extension, MIME string을 포함하지 않는다.
* `file_ref`는 영구 파일 ID가 아니며 ownership, TTL, request/session scope 검증 전에는 신뢰하지 않는다.
* `file_kind=None`은 파일이 아닌 text input에만 사용한다. 파일이지만 종류를 모르는 경우는 `file_kind="unknown"`을 사용한다.
* `extension`은 `.pdf`, `.png`, `.docx` 같은 suffix hint만 허용하며 original file name, basename, path fragment를 포함하지 않는다.
* `mime`은 client-provided hint이며 신뢰하지 않는다. Parser plan resolution은 server-side validation과 resolved file metadata를 기준으로 한다.
* `size_bucket`은 exact byte size가 아니며 allowlist enum 값만 허용한다.
* `kind="unsupported_attachment"`이면 `content_unavailable_reason`은 required다.
* `kind="attachment_metadata"`에서 content scan이 불가능한 경우 `content_unavailable_reason`을 제공해야 한다.
* `content_unavailable_reason`은 raw file name, raw file content, OCR text, extracted text, parser dump를 포함하지 않는다.
* analyze request는 raw file bytes, base64 file payload, OCR text, extracted text, parsed file content, original file name을 포함하지 않는다.

Legacy compatibility adapter:

* legacy `text` request는 `inputs=[kind="text", source="composer"]`로 변환할 수 있다.
* legacy `file_refs[]` request는 `inputs=[kind="file_reference"]`로 변환할 수 있다.
* adapter는 `kind="text", source="file", content=<file text>`를 생성하지 않는다.
* target request model은 `inputs[]`다.
* `schema_version` 변경은 extension response compatibility와 legacy adapter compatibility 검토 없이는 수행하지 않는다.

---

## 5. AnalyzeService Input Normalization Contract

`InputEnvelope`는 AnalyzeService-local routing type이다. Parser, Scanner, ML, Policy module은 `InputEnvelope`에 직접 의존하지 않는다.

```python
ExtractionRequirement = Literal[
    "wrap_text",
    "native_parse",
    "ocr_required",
    "native_parse_then_ocr_fallback",
    "metadata_only",
    "unsupported",
    "not_applicable",
]

class InputEnvelope(BaseModel):
    input_id: str
    request_id: str
    input_origin: Literal[
        "composer_text",
        "converted_paste_text",
        "pasted_file_ref",
        "pasted_image_ref",
        "screenshot_image_ref",
        "attached_file_ref",
        "attachment_metadata",
        "unsupported_attachment",
    ]
    file_kind: FileKind | None
    extraction_requirement: ExtractionRequirement
    file_ref: str | None
    text: str | None
    metadata: "FileMetadata"
```

Contract:

* `InputEnvelope`는 AnalyzeService-local type이다.
* `InputEnvelope`는 공용 타입 섹션에 두지 않는다.
* `composer_text`와 `converted_paste_text`는 `text` required, `file_ref` forbidden이다.
* `pasted_file_ref`, `pasted_image_ref`, `screenshot_image_ref`, `attached_file_ref`는 `file_ref` required, `text` forbidden이다.
* `attachment_metadata`와 `unsupported_attachment`는 `text` forbidden, `file_ref` optional but unused다.
* `file_kind=None`은 파일이 아닌 text input에만 사용한다.
* 파일이지만 종류를 모르는 경우는 `file_kind="unknown"`을 사용한다.
* text input은 text wrapper를 통해 `ParsedDocument`로 변환할 수 있다.
* file_reference input은 `ParserWorkerPayload`로 변환되어 `ParserWorkerPool`을 거친다.
* `attachment_metadata`와 `unsupported_attachment`는 raw file content가 없으므로 `ParserWorkerPayload`를 만들지 않는다. AnalyzeService는 content-not-scanned evidence를 만들어 `PolicyDecisionRequest`에 포함한다.
* AnalyzeService는 module order를 보장한다.
* AnalyzeService는 module failure를 data로 수집해 `PolicyDecisionRequest`에 전달한다.
* AnalyzeService는 final action을 결정하지 않는다.

### InputEnvelope routing and parser plan mapping

| public `kind/source` | input_origin | file_kind | extraction_requirement | resolved `ParserExecutionPlan.plan_kind` | parser route | note |
| --- | --- | --- | --- | --- | --- | --- |
| `text/composer` | `composer_text` | `None` | `wrap_text` | `wrap_text` | text wrapper through parser worker | 사용자가 직접 입력한 텍스트를 `ParsedDocument`로 감싼다. |
| `text/converted_paste` | `converted_paste_text` | `None` | `wrap_text` | `wrap_text` | text wrapper through parser worker | 붙여넣기에서 변환된 텍스트를 `ParsedDocument`로 감싼다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `plain_text` | `native_parse` | `native_text` | parser worker | 일반 텍스트 파일을 block 단위로 파싱한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `pdf` | `native_parse_then_ocr_fallback` | `pdf_native_then_page_ocr` | parser worker | PDF native text 추출을 먼저 하고, coverage 부족 page만 OCR fallback 대상으로 삼는다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `image` | `ocr_required` | `image_ocr` | parser worker | 붙여넣은 이미지 파일은 OCR로 텍스트를 추출한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `office_document` | `native_parse` | `office_parse` | parser worker | `.docx` 같은 Office 문서를 paragraph/block 단위로 파싱한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `spreadsheet` | `native_parse` | `spreadsheet_parse` | parser worker | `.xlsx`/`.csv`를 sheet/row/cell group 단위로 파싱한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `slide` | `native_parse` | `slide_parse` | parser worker | `.pptx` 슬라이드 텍스트를 slide block으로 파싱한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `code` | `native_parse` | `code_parse` | parser worker | 코드/텍스트 파일을 line range 또는 code block 단위로 파싱한다. |
| `file_reference/pasted_file` | `pasted_file_ref` | `unknown` | `metadata_only` or `unsupported` | `metadata_only` or `unsupported` | metadata-only/unsupported adapter | 파일 종류를 확정할 수 없으면 내용 미스캔 evidence로 policy에 전달한다. |
| `file_reference/pasted_image` | `pasted_image_ref` | `image` | `ocr_required` | `image_ocr` | parser worker | 붙여넣은 이미지는 OCR 필수 대상이다. |
| `file_reference/screenshot_image` | `screenshot_image_ref` | `image` | `ocr_required` | `image_ocr` | parser worker | 스크린샷 이미지는 OCR 필수 대상이다. |
| `file_reference/attached_file` | `attached_file_ref` | `plain_text` | `native_parse` | `native_text` | parser worker | 첨부된 일반 텍스트 파일을 파싱한다. |
| `file_reference/attached_file` | `attached_file_ref` | `pdf` | `native_parse_then_ocr_fallback` | `pdf_native_then_page_ocr` | parser worker | 첨부 PDF는 native text 우선, 부족하면 page-level OCR fallback을 수행한다. |
| `file_reference/attached_file` | `attached_file_ref` | `image` | `ocr_required` | `image_ocr` | parser worker | 첨부 이미지 파일은 OCR 대상이다. |
| `file_reference/attached_file` | `attached_file_ref` | `office_document` | `native_parse` | `office_parse` | parser worker | 첨부 Office 문서를 파싱한다. |
| `file_reference/attached_file` | `attached_file_ref` | `spreadsheet` | `native_parse` | `spreadsheet_parse` | parser worker | 첨부 spreadsheet를 파싱한다. |
| `file_reference/attached_file` | `attached_file_ref` | `slide` | `native_parse` | `slide_parse` | parser worker | 첨부 slide 파일을 파싱한다. |
| `file_reference/attached_file` | `attached_file_ref` | `code` | `native_parse` | `code_parse` | parser worker | 첨부 code/text 파일을 파싱한다. |
| `file_reference/attached_file` | `attached_file_ref` | `unknown` | `metadata_only` or `unsupported` | `metadata_only` or `unsupported` | metadata-only/unsupported adapter | 알 수 없는 첨부는 metadata-only 또는 unsupported로 처리한다. |
| `attachment_metadata/*` | `attachment_metadata` | `unknown` or `None` | `metadata_only` | not applicable | no ParserWorkerPayload | 파일 내용은 읽지 못하고 metadata만 policy evidence로 전달한다. |
| `unsupported_attachment/*` | `unsupported_attachment` | `unknown` or `None` | `unsupported` | not applicable | no ParserWorkerPayload | 지원하지 않는 첨부로 처리하고 content-not-scanned evidence를 만든다. |

Rules:

* `extraction_requirement`는 AnalyzeService-local coarse routing hint다.
* `ParserWorkerPayload`에는 구체 실행 계획을 넣지 않는다.
* `ParserExecutionPlan`은 worker 내부 `ParserPlanResolver`가 생성한다.
* PDF는 `native_parse_then_ocr_fallback`을 `pdf_native_then_page_ocr` plan으로 변환하고, coverage 부족 page만 OCR fallback 대상으로 삼는다.
* `metadata_only`는 content를 열 수 없거나 metadata-only 입력인 경우다.
* `unsupported`는 content 분석 경로에 들어왔지만 지원 가능한 parser plan 또는 adapter가 없는 경우다.

---

## 6. Upload / Temporary Processing Storage Contract

PromptGuard는 파일 보관 서비스가 아니라 전송 전 분석 서비스다. 파일 바이트는 분석을 위한 temporary processing data로만 취급한다.

```text
Extension paste/drop/attach/send hook
→ upload/temp file endpoint
→ encrypted temporary processing storage
→ opaque file_ref
→ analyze request with file_reference input
→ AnalyzeService
→ ParserWorkerPayload
→ ParserWorkerPool
→ FileParserResult
→ ParsedDocument / ParsedBlock
→ v3.5 analysis pipeline
```

Contract:

* raw file bytes는 encrypted temporary processing storage에만 둘 수 있다.
* temporary processing storage는 EventStorage가 아니다.
* `file_ref`는 영구 파일 ID가 아니다.
* `file_ref`는 encrypted temporary processing object를 가리키는 opaque reference다.
* `file_ref`는 ownership, TTL, request/session scope 검증 대상이다.
* temp file은 TTL 만료 또는 analyze completion 이후 cleanup 대상이다.
* cleanup failure는 metric과 failure code로만 표현한다.
* cleanup failure message는 file content, original file name, OCR text, extracted text를 포함하지 않는다.
* upload endpoint는 original file name을 downstream으로 전파하지 않는다.
* EventStorage는 raw file bytes, temp file path, extracted text, OCR text, original file name을 저장하지 않는다.

---

## 7. ParserWorkerPayload / File Parser Shared Types

Parser shared type은 public API schema가 아니다. `ParserWorkerPayload`는 worker handoff용 shared type이고, 구체 실행 계획은 `ParserPlanResolver`가 생성한 `ParserExecutionPlan`에만 존재한다.

```python
class ParserWorkerPayload(BaseModel):
    request_id: str
    input_id: str

    input_origin: Literal[
        "composer_text",
        "converted_paste_text",
        "pasted_file_ref",
        "pasted_image_ref",
        "screenshot_image_ref",
        "attached_file_ref",
    ]

    file_kind: FileKind | None
    extraction_requirement: ExtractionRequirement

    file_ref: str | None
    text: str | None
    metadata: "FileMetadata"
    parser_limits: "ParserLimits"
    access_context: "TempFileAccessContext | None" = None

class TempFileAccessContext(BaseModel):
    authenticated_subject_id: str
    session_id: str
    request_id: str
    temp_scope_id: str | None = None

class FileMetadata(BaseModel):
    extension: str | None
    mime: str | None
    file_kind: FileKind | None = None
    size_bytes: int | None = None  # runtime-only exact size
    size_bucket: SizeBucket | None = None
    content_included: bool = False
    content_unavailable_reason: str | None = None

class ParserLimits(BaseModel):
    max_bytes: int
    timeout_ms: int
    max_blocks: int | None = None
    max_chars_per_block: int | None = None
    max_total_chars: int | None = None
    max_pdf_pages: int | None = None
    max_ocr_pages: int | None = None
    max_spreadsheet_rows: int | None = None
    max_spreadsheet_cells: int | None = None
    max_slide_count: int | None = None
    max_code_lines: int | None = None
    max_image_pixels: int | None = None

ParserPlanKind = Literal[
    "wrap_text",
    "native_text",
    "pdf_native_then_page_ocr",
    "image_ocr",
    "office_parse",
    "spreadsheet_parse",
    "slide_parse",
    "code_parse",
    "metadata_only",
    "unsupported",
]

ParserStepType = Literal[
    "wrap_text",
    "native_text_extract",
    "pdf_native_text_extract",
    "pdf_coverage_evaluate",
    "render_ocr_candidate_pages",
    "ocr_primary",
    "ocr_fallback",
    "office_parse",
    "spreadsheet_parse",
    "slide_parse",
    "code_parse",
    "merge_blocks",
    "metadata_only",
    "unsupported",
]

class ParserPlanStep(BaseModel):
    step_id: str
    ordinal: int
    step_type: ParserStepType
    adapter_id: str | None = None
    condition: str | None = None
    required: bool = True
    on_failure: Literal["fail", "partial", "continue", "apply_fallback"] = "fail"

class ParserFallbackRule(BaseModel):
    rule_id: str
    trigger: str
    fallback_action: Literal["run_step", "mark_partial", "mark_unsupported", "emit_failure"]
    fallback_target: str | None = None
    failure_code: str

class ParserExecutionPlan(BaseModel):
    plan_id: str
    plan_kind: ParserPlanKind
    input_id: str
    steps: list[ParserPlanStep]
    fallback_rules: list[ParserFallbackRule] = []
    unsupported_reason_code: str | None = None

class BlockSource(BaseModel):
    input_id: str
    parser_id: str
    file_type: str | None
    unit_type: Literal[
        "composer_text",
        "converted_paste_text",
        "plain_text_block",
        "pdf_native_page",
        "pdf_ocr_page",
        "pdf_ocr_line",
        "image_ocr_block",
        "image_ocr_line",
        "spreadsheet_sheet",
        "spreadsheet_row",
        "spreadsheet_cell_group",
        "docx_paragraph",
        "ppt_slide_text",
        "code_block",
        "metadata_only",
    ]
    block_index: int

class BlockLocation(BaseModel):
    kind: Literal["page", "spreadsheet", "slide", "ocr", "code", "text"]
    page: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    sheet_index: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    slide_index: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    block_index: int | None = None
    ocr_line_index: int | None = None

class ExtractionStatus(BaseModel):
    method: Literal[
        "composer_text",
        "converted_paste_text",
        "native_text",
        "pdf_native_text",
        "pdf_ocr",
        "image_ocr",
        "xml_text",
        "office_parse",
        "spreadsheet_parse",
        "slide_parse",
        "code_parse",
        "fallback_text",
        "metadata_only",
    ]
    status: "ParserStatus"
    coverage: Literal["complete", "partial", "none"]
    confidence_bucket: Literal["low", "medium", "high"] | None = None
    warnings: tuple[str, ...] = ()
```

Field meaning:

* `input_origin`: 입력이 어디서 왔는가.
* `file_kind`: 어떤 종류의 파일/입력인가. `None`은 파일이 아닌 text input, `unknown`은 파일이지만 종류를 모르는 입력이다.
* `extraction_requirement`: AnalyzeService가 worker에 넘기는 coarse requirement다.
* `ParserExecutionPlan`: `ParserPlanResolver`가 만든 concrete execution plan이다.
* `steps[]`: 정상 실행 순서다. ordered list이며 각 step은 deterministic `ordinal`을 가진다.
* `fallback_rules[]`: 특정 실패나 조건에서 적용할 대체 규칙이며 정상 실행 순서와 분리한다.
* `ocr`: source가 아니라 extraction method다.
* raw file bytes는 payload에 들어가지 않는다.
* `text`는 composer/converted paste wrapper용 runtime-only 값이다.
* file_reference input에서는 `text=None`이고 `file_ref`가 있어야 한다.

Storage rule:

* `size_bytes`는 runtime validation only다.
* EventStorage는 `size_bucket`만 저장한다.
* `BlockLocation`은 response location hint에만 제한적으로 사용한다.
* EventRecord는 `location_kind`만 저장한다.
* `ParsedBlock.text`는 runtime-only다.
* `ParsedDocument.metadata`는 allowlist-only다.
* `ParserExecutionPlan`, `ParserPlanStep`, `ParserFallbackRule`은 runtime-only이며 EventStorage에 원문 serialize하지 않는다. EventStorage에는 plan kind bucket, failure code, parser version 같은 allowlist metadata만 남길 수 있다.

---

## 8. Parser Selection Contract

| file_kind | resolved `ParserExecutionPlan.plan_kind` | parser behavior |
| --- | --- | --- |
| `plain_text` | `text_wrapper` or `plain_text_native` | text block으로 ParsedDocument 생성 |
| `pdf` | `pdf_native_then_page_ocr` | PDF native text extraction 우선, page-level OCR fallback은 coverage policy로 제한 |
| `pdf` | `pdf_page_ocr` | native text coverage 부족 page만 OCR fallback |
| `image` | `image_ocr` | OCR block/line 생성 |
| `office_document` | `office_parse` | paragraph/block 기반 ParsedBlock 생성 |
| `spreadsheet` | `spreadsheet_parse` | sheet/row/cell-group 기반 ParsedBlock 생성 |
| `slide` | `slide_parse` | slide text block 생성 |
| `code` | `code_parse` | code block 또는 line range block 생성 |
| `unknown` | `metadata_only` or `unsupported` | content_not_scanned evidence로 policy에 전달 |

PDF rules:

* PDF는 native text extraction을 먼저 시도한다.
* native text coverage가 충분하면 OCR을 수행하지 않는다.
* native text가 없거나 coverage가 낮으면 OCR fallback을 수행한다.
* encrypted PDF는 `parser_status="encrypted"`로 처리한다.
* PDF timeout은 `parser_status="timeout"`으로 처리한다.

Image OCR rules:

* pasted image, screenshot image, uploaded/attached image는 OCR 대상이다.
* OCR 결과는 `ParsedBlock.text` runtime memory에만 존재한다.
* OCR 실패는 `ocr_status="failed"`로 처리한다.
* OCR no text는 `ocr_status="no_text_detected"`로 처리한다.
* OCR timeout은 `ocr_status="timeout"`으로 처리한다.

Spreadsheet / Office rules:

* spreadsheet sheet name은 EventStorage에 저장하지 않는다.
* document title, author, comments metadata는 저장하지 않는다.
* original file name은 metadata에 복사하지 않는다.
* row/slide/page/line index는 response location hint에만 제한적으로 사용한다.
* EventStorage에는 `location_kind`만 저장한다.

Out of scope:

* archive extraction
* malware scanning
* ZIP 내부 재귀 분석
* binary analysis
* repository deep scan
* image semantic object recognition

* pixel-level visual classification

### 8.1 Open-source license policy

OCR/parser 기본 구현은 permissive open-source component만 사용한다.

허용 default license:

```text
Apache-2.0
MIT
BSD-2-Clause
BSD-3-Clause
ISC
```

기본 dependency로 금지하는 license 또는 조건:

```text
GPL
LGPL
AGPL
SSPL
source-available non-OSI license
commercial-only license
unclear model-weight license
transitive dependency chain에 GPL/LGPL/AGPL/SSPL이 포함된 경우
application source code 공개 의무를 만들 수 있는 license
```

허용 기준:

* PromptGuard application source code 공개를 요구하지 않아야 한다.
* license notice, copyright notice, NOTICE file preservation, attribution 정도만 요구하는 permissive license는 허용한다.
* 직접 dependency와 transitive dependency 모두 license scan 대상이다.
* OCR model weight license도 scan 대상이다.
* dependency license가 불명확하면 기본 구현으로 사용할 수 없다.
* 법무 검토 없이 GPL/LGPL/AGPL/SSPL component를 도입할 수 없다.

### 8.2 Default OCR/parser stack

MVP default OCR/parser stack은 다음과 같이 고정한다.

```text
PDF native text extraction: pypdf
PDF page rendering for OCR fallback: pypdfium2 / PDFium
Primary OCR engine: PaddleOCR local text detection + text recognition engine
Fallback OCR engine: Tesseract OCR
Default OCR language scope: Korean, English, numeric text
Cloud OCR: forbidden by default
Execution mode: local server-side worker only
```

규칙:

* `PaddleOcrEngine`을 default OCR implementation으로 둔다.
* `TesseractOcrEngine`은 fallback implementation으로 둔다.
* OCR engine은 반드시 `OcrEnginePort` 뒤에 숨긴다.
* OCR engine 교체는 public API schema, `ParsedDocument / ParsedBlock` schema, Policy Orchestrator contract를 변경하지 않아야 한다.
* PaddleOCR는 기본 구현에서 local text detection + text recognition 용도로만 사용한다.
* PaddleOCR document parsing, layout understanding, PP-Structure, VLM, Markdown/JSON conversion, cloud/API 기능은 기본 구현에서 사용하지 않는다.
* PaddleOCR package뿐 아니라 실제 로드되는 OCR detection model weight, recognition model weight, orientation/classification model weight, language model, PaddlePaddle runtime, transitive dependency가 모두 license gate를 통과해야 한다.
* PaddleOCR model weight를 수정하지 않더라도 사용, 번들링, 재배포, 배포 artifact 포함 여부가 모두 license scan 대상이다.
* PDF native text extraction은 `pypdf` adapter가 먼저 수행한다.
* native text coverage가 부족한 PDF page만 `pypdfium2 / PDFium`으로 rendering한 뒤 OCR fallback을 수행한다.
* rendered page image는 runtime temporary data이며 EventStorage, log, API response에 남기지 않는다.
* OCR text는 `ParsedBlock.text` runtime-only field에만 들어간다.
* OCR text를 EventStorage에 저장하지 않는다.
* OCR text를 log에 남기지 않는다.
* exact OCR confidence는 저장하지 않고 `confidence_bucket`만 사용한다.
* cloud OCR API는 기본 구현에서 금지한다.

Tesseract fallback trigger:

```text
PaddleOcrEngine unavailable
PaddleOcrEngine disabled by config
PaddleOcrEngine initialization failed
PaddleOcrEngine execution failed before producing valid OcrResult
PaddleOcrEngine returns no_text_detected
  AND page was OCR candidate because native text was very low
  AND image_evidence is present or unknown
  AND OCR budget remains
```

Tesseract fallback trigger가 아닌 것:

```text
PaddleOCR confidence_bucket == low
PaddleOCR returned partial text
PaddleOCR returned some recognized text but layout is imperfect
```

---

### 8.3 Forbidden default dependencies

다음 component는 기본 OCR/parser 구현에서 금지한다.

```text
PyMuPDF
MuPDF
Ghostscript
Poppler
pdf2image
cloud OCR APIs
closed-source OCR SDKs
model weights without explicit commercial-use-compatible open-source license
```

규칙:

* `pdf2image` 자체 license가 permissive여도 Poppler toolchain 의존이 있으면 기본 구현에서 금지한다.
* PyMuPDF/MuPDF는 AGPL/commercial license 구조 때문에 기본 구현에서 금지한다.
* Ghostscript는 AGPL/commercial license 구조 때문에 기본 구현에서 금지한다.
* Poppler는 GPL 계열이므로 기본 구현에서 금지한다.
* 위 component는 별도 legal review, security review, dependency exception record 없이는 사용할 수 없다.

### 8.4 Default non-OCR parser stack

MVP default non-OCR parser stack은 다음과 같이 고정한다.

```text
Office document parser: python-docx for .docx only
Spreadsheet parser: openpyxl for .xlsx, Python csv module for .csv
Slide parser: python-pptx for .pptx only
Plain text parser: Python stdlib text decoding with explicit charset handling
Code text parser: Python stdlib text decoding with line-range preservation
Legacy binary Office formats: .doc, .xls, .ppt unsupported by default
Archive formats: unsupported by default
External office converters: forbidden by default
```

규칙:

* `OfficeDocumentParserAdapter`는 `.docx`만 기본 지원한다.
* `SpreadsheetParserAdapter`는 `.xlsx`와 `.csv`만 기본 지원한다.
* `SlideParserAdapter`는 `.pptx`만 기본 지원한다.
* `.doc`, `.xls`, `.ppt` legacy binary Office formats는 기본 구현에서 `unsupported` 또는 `metadata_only`로 처리한다.
* legacy binary Office formats를 지원하기 위해 LibreOffice, unoconv, antiword, catdoc, xls2csv, external office converter를 기본 dependency로 추가할 수 없다.
* archive, zip, nested attachment extraction은 기본 구현 범위 밖이다.
* parser adapter는 public API schema, `ParsedDocument / ParsedBlock` schema, Policy Orchestrator contract를 변경하지 않아야 한다.
* parser adapter는 original file name, document title, author, comments, spreadsheet sheet name, extracted text를 EventStorage에 저장하지 않는다.
* plain text와 code parser는 line location을 보존하되 text content는 runtime-only로 유지한다.
* charset detection failure는 raw bytes dump 없이 structured `PipelineFailure`로 반환한다.

### 8.5 License scan output artifacts

OCR/parser dependency와 model weight license 검증은 CI 산출물로 남긴다.

Required artifacts:

```text
third_party/licenses/parser_ocr_sbom.json
third_party/licenses/parser_ocr_license_report.json
third_party/licenses/ocr_model_weight_license_report.json
third_party/licenses/NOTICE.parser_ocr.txt
```

규칙:

* direct dependency와 transitive dependency는 모두 license scan 대상이다.
* OCR model weight, OCR language pack, PDF renderer binary, native library binding도 license scan 대상이다.
* license scan artifact가 없으면 OCR/parser dependency 추가 PR은 merge할 수 없다.
* `parser_ocr_sbom.json`은 component name, version, package source, resolved license id, dependency path를 포함한다.
* `parser_ocr_license_report.json`은 allow/deny decision, denial reason, source disclosure risk 여부를 포함한다.
* `ocr_model_weight_license_report.json`은 model id, model version, weight source, license id, commercial-use compatibility, source disclosure requirement 여부를 포함한다.
* `NOTICE.parser_ocr.txt`는 permissive license notice와 required attribution을 포함한다.
* EventStorage에는 license artifact 원문을 저장하지 않는다.
* Runtime metadata에는 component name, version, license id, engine id, model id, model version만 남길 수 있다.

Merge 금지 조건:

* required license artifact 누락
* dependency tree에 GPL, LGPL, AGPL, SSPL, commercial-only, source-available non-OSI license 포함
* model weight license가 불명확함
* source disclosure required component가 default distribution에 포함됨
* PyMuPDF, MuPDF, Ghostscript, Poppler, pdf2image, cloud OCR API, closed-source OCR SDK가 기본 구현에 포함됨

### 8.6 Parser/OCR dependency lock rule

기본 OCR/parser dependency는 lockfile과 license artifact가 함께 변경되어야 한다.

규칙:

* parser/OCR dependency 추가, 제거, version 변경은 lockfile, SBOM, license report, NOTICE file을 함께 갱신해야 한다.
* dependency version range는 reproducible build를 해치지 않도록 lockfile에서 고정한다.
* optional dependency라도 default execution path에 포함되면 license gate와 static quality gate 대상이다.
* dependency exception은 기본 구현 계약에 포함하지 않는다. 별도 legal review, security review, exception record가 있어야 한다.

### 8.7 ParserAdapter Contract

모든 parser adapter는 같은 interface를 따른다.

```python
from typing import Protocol

class ParserAdapter(Protocol):
    parser_id: str
    parser_version: str
    supported_file_kinds: tuple[FileKind, ...]
    supported_mime_types: tuple[str, ...]
    supported_extensions: tuple[str, ...]
    capabilities: tuple[str, ...]
    license_metadata: ComponentLicenseMetadata

    def supports(
        self,
        payload: ParserWorkerPayload,
        metadata: FileMetadata,
    ) -> bool:
        ...

    def parse(
        self,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
        limits: ParserLimits,
    ) -> FileParserResult:
        ...
```

규칙:

* 모든 adapter는 `ParserWorkerPayload -> FileParserResult` 계약을 만족한다.
* adapter는 `FileParserResult` 외의 wrapper result를 반환하지 않는다.
* adapter는 failure도 raw exception escape가 아니라 structured `PipelineFailure`로 반환한다.
* unsupported file도 정상적인 `FileParserResult(document=None, parser_status="unsupported")`로 반환한다.
* partial parse는 available `ParsedBlock[]`과 `parser_status="partial"`로 반환한다.
* adapter는 deterministic block order를 보장한다.
* adapter는 deterministic `block_id`를 생성한다.
* adapter는 `BlockSource`, `BlockLocation`, `ExtractionStatus`를 채운다.
* adapter는 original file name을 metadata에 복사하지 않는다.
* adapter는 raw file bytes, OCR text, extracted text, original file name, temp file path를 log에 남기지 않는다.
* adapter는 scanner, normalizer, embedding, classifier, verifier, policy를 import하지 않는다.
* adapter는 final action, reason_code, user notice를 만들 수 없다.

Required adapters:

```text
TextWrapperParserAdapter
PlainTextParserAdapter
PdfNativeTextParserAdapter
PdfOcrFallbackParserAdapter
ImageOcrParserAdapter
OfficeDocumentParserAdapter
SpreadsheetParserAdapter
SlideParserAdapter
CodeTextParserAdapter
MetadataOnlyParserAdapter
UnsupportedFileParserAdapter
```

### 8.8 ParserPlanResolver / ParserRegistry Contract

`ParserPlanResolver`는 parser 실행 계획을 만드는 component다. `ParserRegistry`라는 이름을 유지할 경우에도 adapter lookup과 `ParserExecutionPlan` 생성 책임으로만 제한한다.

입력:

```text
file_kind
MIME
extension
extraction_requirement
adapter capability
parser config
license policy
resolved file metadata
```

출력:

```text
ParserExecutionPlan
unsupported reason code
```

규칙:

* plan resolution은 deterministic해야 한다.
* 같은 payload, resolved metadata, config, license policy는 같은 `ParserExecutionPlan`을 생성해야 한다.
* `ParserWorkerPayload`에는 구체 plan이 들어가지 않는다.
* ambiguous fallback-order string을 사용하지 않는다.
* 정상 실행 순서는 `ParserExecutionPlan.steps[]`에 둔다.
* 조건부 대체 규칙은 `ParserExecutionPlan.fallback_rules[]`에 둔다.
* adapter가 없으면 `unsupported` 또는 `metadata_only` plan으로 처리한다.
* `metadata_only`는 content를 열 수 없거나 metadata-only 입력인 경우다.
* `unsupported`는 content 분석 경로에 들어왔지만 지원 가능한 parser plan 또는 adapter가 없는 경우다.
* `ParserPlanResolver`는 직접 parsing하지 않는다.
* `ParserPlanResolver`는 OCR을 수행하지 않는다.
* `ParserPlanResolver`는 plan execution을 수행하지 않는다.
* `ParserPlanResolver`는 policy decision을 생성하지 않는다.
* license policy를 통과하지 못한 adapter는 plan step에 포함할 수 없다.
* file type별 concrete parser branching은 AnalyzeService가 아니라 `ParserPlanResolver`에 둔다.

Example plan:

```text
plan_kind: pdf_native_then_page_ocr
steps:
  1. pdf_native_text_extract
  2. pdf_coverage_evaluate
  3. render_ocr_candidate_pages
  4. ocr_primary
  5. merge_blocks
fallback_rules:
  - PaddleOCR unavailable → Tesseract
  - PaddleOCR initialization failed → Tesseract
  - OCR page limit exceeded → OCR_PAGE_LIMIT_EXCEEDED warning/failure
```

---

### 8.9 TemporaryFileResolverPort Contract

`TemporaryFileResolverPort`는 parser worker runtime 내부에서만 사용한다. `ParserWorkerPool`은 `file_ref`를 직접 파일 경로로 해석하지 않는다. `FileParserRunner`가 worker 내부에서 resolver를 호출한다.

```python
class TempFileAccessContext(BaseModel):
    authenticated_subject_id: str
    session_id: str
    request_id: str
    temp_scope_id: str | None = None

class TemporaryFileResolverPort(Protocol):
    def resolve(
        self,
        file_ref: str,
        access_context: TempFileAccessContext,
    ) -> ResolvedTemporaryFile:
        ...
```

규칙:

* resolver는 단일 `owner_id` 인자를 받지 않고 `TempFileAccessContext`만 사용한다.
* `owner_id` 단일 인자는 의미가 불명확하므로 `TempFileAccessContext`로 대체한다.
* resolver는 authenticated subject, session, request, optional temp scope 기준으로 ownership, TTL, request/session scope, metadata integrity를 검증한다.
* `file_ref`는 `TemporaryFileResolverPort`로만 resolve한다.
* resolver failure는 structured `PipelineFailure`로 반환한다.
* temp file path는 API response, EventStorage, log에 노출하지 않는다.
* `ResolvedTemporaryFile.local_runtime_ref`는 parser worker runtime 내부에서만 사용한다.
* analyze completion 또는 TTL 만료 후 cleanup 대상이다.
* resolver는 raw exception message, local path, original file name, extracted text, OCR text를 response/log/storage에 전달하지 않는다.

Failure codes:

```text
TEMP_FILE_NOT_FOUND
TEMP_FILE_EXPIRED
TEMP_FILE_OWNER_MISMATCH
TEMP_FILE_SCOPE_MISMATCH
TEMP_FILE_METADATA_INTEGRITY_FAILED
TEMP_FILE_RESOLVE_FAILED
```

---

### 8.10 OcrEnginePort Contract

OCR provider는 `OcrEnginePort`로 추상화한다.

```python
class OcrEnginePort(Protocol):
    engine_id: str
    engine_version: str
    license_metadata: ComponentLicenseMetadata
    model_id: str | None
    model_version: str | None

    def recognize(
        self,
        image: OcrImageInput,
        options: OcrOptions,
    ) -> OcrResult:
        ...
```

Required implementations:

```text
PaddleOcrEngine implements OcrEnginePort
TesseractOcrEngine implements OcrEnginePort
```

규칙:

* `PaddleOcrEngine` is default.
* `TesseractOcrEngine` is fallback.
* OCR result text는 runtime memory로만 반환한다.
* OCR result text는 `ParsedBlock.text`로만 전달된다.
* exact OCR confidence는 저장하지 않는다.
* OCR confidence는 `confidence_bucket`으로만 변환할 수 있다.
* OCR input image dump는 저장하지 않는다.
* OCR bounding text excerpt는 저장하지 않는다.
* OCR engine은 policy decision을 만들지 않는다.
* OCR engine은 raw image path, raw text, original file name을 log에 남기지 않는다.
* OCR engine failure는 structured `PipelineFailure`로 반환한다.

### 8.11 OCR/parser shared types

```python
class ComponentLicenseMetadata(BaseModel):
    component_name: str
    component_version: str
    license_id: str
    license_url: str | None = None
    source_url: str | None = None
    notice_required: bool
    source_disclosure_required: bool
    allowed_for_default_distribution: bool

class ResolvedTemporaryFile(BaseModel):
    file_ref: str
    mime: str | None
    extension: str | None
    file_kind: FileKind | None
    size_bytes: int
    size_bucket: str
    local_runtime_ref: str

class OcrImageInput(BaseModel):
    input_id: str
    block_candidate_id: str | None = None
    page: int | None = None
    image_runtime_ref: str
    image_kind: Literal["pdf_rendered_page", "pasted_image", "screenshot_image", "attached_image"]
    width_bucket: str | None = None
    height_bucket: str | None = None

class OcrOptions(BaseModel):
    languages: tuple[str, ...]
    timeout_ms: int
    confidence_bucket_policy: str
    page_segmentation_mode: str | None = None
    max_image_pixels: int | None = None

class OcrTextBlock(BaseModel):
    text: str
    line_index: int | None = None
    block_index: int | None = None
    confidence_bucket: Literal["low", "medium", "high"] | None = None

class OcrResult(BaseModel):
    input_id: str
    page: int | None = None
    status: OcrStatus
    blocks: list[OcrTextBlock]
    confidence_bucket: Literal["low", "medium", "high"] | None = None
    engine_id: str
    engine_version: str
    model_id: str | None = None
    model_version: str | None = None
    warnings: tuple[str, ...] = ()
    failure: PipelineFailure | None = None
```

Type rules:

* 모든 ParserAdapter와 OcrEnginePort implementation은 `ComponentLicenseMetadata`를 제공해야 한다.
* `source_disclosure_required=True`인 component는 default implementation으로 사용할 수 없다.
* `allowed_for_default_distribution=False`인 component는 default implementation으로 사용할 수 없다.
* EventStorage에는 component license metadata 전체를 저장하지 않는다.
* Runtime/storage에 남길 수 있는 field는 component name, version, license id, engine id, model id, model version뿐이다.
* `ResolvedTemporaryFile.local_runtime_ref`는 runtime-only이며 EventStorage, API response, log에 남기지 않는다.
* `ResolvedTemporaryFile`은 original file name을 포함하지 않는다.
* exact `size_bytes`는 runtime validation only이며 EventStorage는 `size_bucket`만 저장한다.
* `OcrImageInput.image_runtime_ref`는 runtime-only이다.
* rendered image path, image bytes, OCR input image dump는 EventStorage에 저장하지 않는다.
* `OcrOptions` 기본값은 `languages=("kor", "eng")`, `timeout_ms=ParserLimits.timeout_ms`, `confidence_bucket_policy="low_medium_high"`다.
* `OcrTextBlock.text`는 runtime-only이며 `ParsedBlock.text`로 변환된 뒤 저장되지 않는다.
* exact confidence와 raw bounding box coordinates는 기본 저장 대상이 아니다.
* response location hint에는 page/line/block index만 제한적으로 사용할 수 있다.

### 8.12 Parser/OCR performance budget

Parser/OCR implementation은 synthetic fixture 기준 성능 budget을 만족해야 한다.

```text
text wrapper p95 latency <= 500ms
plain text parser p95 latency <= 800ms
code text parser p95 latency <= 800ms
CSV parser under max_spreadsheet_rows p95 latency <= 1500ms
XLSX parser under max_spreadsheet_rows/max_spreadsheet_cells p95 latency <= 3000ms
DOCX parser under max_total_chars p95 latency <= 3000ms
PPTX parser under max_slide_count p95 latency <= 3000ms
native text PDF under max_pdf_pages p95 latency <= 3000ms
PDF page rendering p95 latency <= 3000ms per page
OCR recognition p95 latency <= 8000ms per page
image OCR p95 latency <= 8000ms per image
total parser worker execution <= ParserLimits.timeout_ms
```

규칙:

* performance budget은 synthetic fixture 기준으로 측정한다.
* fixture에는 실제 PII, real secret, 실제 고객명, 실제 회사명을 넣지 않는다.
* performance regression test는 exact raw text, OCR text, extracted text, file path, original file name을 출력하지 않는다.
* latency는 EventStorage에 exact value로 저장하지 않고 latency bucket 또는 metric으로만 남긴다.
* budget 초과는 silent fallback이 아니라 structured timeout/failure 또는 regression test failure로 처리한다.
* `ParserLimits.timeout_ms`가 개별 budget보다 우선하는 hard limit이다.
* OCR fallback은 `max_ocr_pages`를 초과할 수 없다.
* queue backpressure는 raw payload dump 없이 structured timeout/failure로 반환한다.
* CI performance gate는 deterministic local fixture와 mocked heavy dependency fixture를 분리한다.
* real OCR/model availability에 따라 흔들리는 unit test를 금지하고, real OCR은 integration/performance profile에서만 사용한다.

### 8.13 PDF native text + OCR fallback contract

PDF processing order:

```text
file_ref
→ TemporaryFileResolverPort, called by FileParserRunner
→ ParserPlanResolver creates pdf_native_then_page_ocr plan
→ ParserPlanExecutor runs PdfNativeTextParserAdapter using pypdf
→ page-level PDF coverage evaluation
→ sufficient native page coverage: build native ParsedBlock without OCR
→ insufficient page coverage: render affected pages using pypdfium2 / PDFium
→ OCR rendered candidate pages using PaddleOcrEngine
→ fallback to TesseractOcrEngine only on defined triggers
→ merge native/OCR ParsedBlock results
→ FileParserResult
```

```python
class PdfCoveragePolicy(BaseModel):
    very_low_meaningful_chars_per_page: int = 30
    low_meaningful_chars_per_page: int = 120
    low_native_text_page_ratio_threshold: float = 0.80
    ocr_fallback_scope: Literal["page_level"] = "page_level"
```

Page-level coverage evaluation:

```text
1. pypdf로 page별 native text extraction을 수행한다.
2. meaningful_char_count를 계산한다.
3. image_evidence를 가능한 범위에서 계산한다.
4. OCR fallback candidate 여부를 page 단위로 결정한다.
```

`meaningful_char_count`는 NFKC normalization 이후 Unicode letter 또는 number category에 해당하는 문자만 세어 계산한다. 공백, 개행, punctuation, decorative symbol, separator, control character는 제외한다.

OCR fallback candidate 조건은 다음 중 하나라도 만족하는 경우다.

```text
native_text_extraction_failed
OR meaningful_char_count < very_low_meaningful_chars_per_page
OR meaningful_char_count < low_meaningful_chars_per_page AND image_evidence_present
OR meaningful_char_count < low_meaningful_chars_per_page AND image_evidence_unknown
```

기본값 기준:

```text
native text extraction 실패 → OCR candidate
meaningful_char_count < 30 → OCR candidate
meaningful_char_count < 120 AND image_evidence_present → OCR candidate
meaningful_char_count < 120 AND image_evidence_unknown → OCR candidate
meaningful_char_count >= 120 → OCR skip
meaningful_char_count 30~119 AND image_evidence_absent → OCR skip
```

Image evidence semantics:

* `image_evidence_present`는 page에 이미지 XObject 또는 이에 준하는 image resource가 관측된 경우다. 이는 scanned page 확정 판정이 아니라 보조 신호다.
* `image_evidence_unknown`은 image evidence 판단이 parser limitation, nested resource, unsupported object, parse failure 등으로 신뢰 가능하게 완료되지 않은 경우다. 보수적으로 OCR candidate로 처리한다.
* `image_evidence_absent`는 지원 범위 내에서 page image resource를 확인했으나 image evidence가 발견되지 않은 경우다. 이는 “이미지가 절대 없다”는 보장이 아니라 지원 범위 내 관측 결과다.

기본 구현 범위에서 제외한다.

```text
visual blank page detection
image-only page 확정 판정
scanned-like page 확정 판정
layout coverage 분석
이미지가 page 대부분을 덮는지 판단
OCR 없이 이미지 안에 텍스트가 있는지 판단
```

`low_native_text_page_ratio`는 다음처럼 계산한다.

```text
low_native_text_page_ratio =
    low_native_text_page_count / inspected_page_count
```

여기서 `low_native_text_page`는 page가 OCR fallback candidate로 판정된 경우다. `low_native_text_page_ratio_threshold`는 low-native-coverage PDF warning/status metadata에만 사용한다. OCR fallback 대상 page를 확대하거나 native text가 충분한 page를 OCR하도록 만드는 gate로 사용하지 않는다.

규칙:

* PDF는 native text extraction을 먼저 수행한다.
* PDF OCR fallback은 document-level이 아니라 page-level로만 판단한다.
* 문서 전체의 low coverage ratio 때문에 native text가 충분한 page까지 OCR 대상으로 확대하지 않는다.
* native text coverage가 충분한 page에는 OCR을 수행하지 않는다.
* OCR fallback candidate 수가 `ParserLimits.max_ocr_pages`를 초과하면 deterministic page order로 `max_ocr_pages`까지만 OCR을 수행한다.
* OCR을 수행하지 못한 candidate page는 `OCR_PAGE_LIMIT_EXCEEDED` warning/failure로 Policy Orchestrator에 전달한다.
* scanned-only PDF는 page별 OCR fallback candidate가 된다.
* encrypted PDF는 `parser_status="encrypted"`로 처리한다.
* malformed PDF는 `PDF_PARSE_FAILED`로 처리한다.
* OCR fallback partial success는 available blocks와 `parser_status="partial"`로 반환한다.
* OCR fallback failure는 allow 근거가 아니며 policy에 전달한다.
* rendered page image는 runtime-only이다.
* rendered page image path는 log, EventStorage, API response에 남기지 않는다.
* Tesseract fallback은 section 8.2의 trigger에만 수행한다.

---

### 8.14 Adapter별 output rule

| input/parser | BlockSource.unit_type | ExtractionStatus.method |
| --- | --- | --- |
| composer text wrapper | `composer_text` | `composer_text` |
| converted paste text wrapper | `converted_paste_text` | `converted_paste_text` |
| plain text file | `plain_text_block` | `native_text` |
| PDF native text | `pdf_native_page` | `pdf_native_text` |
| PDF OCR page | `pdf_ocr_page` | `pdf_ocr` |
| PDF OCR line | `pdf_ocr_line` | `pdf_ocr` |
| image OCR block | `image_ocr_block` | `image_ocr` |
| image OCR line | `image_ocr_line` | `image_ocr` |
| Office paragraph | `docx_paragraph` | `office_parse` |
| spreadsheet sheet summary | `spreadsheet_sheet` | `spreadsheet_parse` |
| spreadsheet row | `spreadsheet_row` | `spreadsheet_parse` |
| spreadsheet cell group | `spreadsheet_cell_group` | `spreadsheet_parse` |
| slide text | `ppt_slide_text` | `slide_parse` |
| code block | `code_block` | `code_parse` |
| metadata only | `metadata_only` | `metadata_only` |

규칙:

* 모든 adapter는 deterministic `block_id`를 생성한다.
* 모든 adapter는 stable block ordering을 보장한다.
* 모든 adapter는 가능한 경우 `BlockLocation`을 채운다.
* spreadsheet sheet name은 EventStorage에 저장하지 않는다.
* document title, author, comments metadata는 저장하지 않는다.
* original file name은 metadata에 복사하지 않는다.
* code parser는 line location을 보존하되 code text는 저장하지 않는다.

### 8.15 ParserFailureCode registry

다음 failure code를 공용 registry로 정의한다.

```text
TEMP_FILE_NOT_FOUND
TEMP_FILE_EXPIRED
TEMP_FILE_OWNER_MISMATCH
TEMP_FILE_RESOLVE_FAILED
UNSUPPORTED_FILE_KIND
UNSUPPORTED_MIME
PARSER_DISABLED
OCR_DISABLED
PDF_ENCRYPTED
PDF_NATIVE_TEXT_LOW_COVERAGE
PDF_PARSE_FAILED
PDF_RENDER_FAILED
OCR_ENGINE_UNAVAILABLE
OCR_TIMEOUT
OCR_FAILED
OCR_NO_TEXT_DETECTED
OCR_PAGE_LIMIT_EXCEEDED
OFFICE_PARSE_FAILED
SPREADSHEET_PARSE_FAILED
SLIDE_PARSE_FAILED
CODE_PARSE_FAILED
PARSER_TIMEOUT
PARSER_TOO_LARGE
PARSER_LIMIT_EXCEEDED
PARSED_BLOCK_LIMIT_EXCEEDED
EMPTY_TEXT
PARSER_WORKER_FAILED
LICENSE_POLICY_VIOLATION
DEPENDENCY_LICENSE_UNSUPPORTED
MODEL_LICENSE_UNCLEAR
```

규칙:

* failure code는 storage에 저장할 수 있다.
* failure message는 raw prompt, raw file bytes, OCR text, extracted text, original file name, temp file path, rendered image path, matched value를 포함하면 안 된다.
* raw exception message를 그대로 사용자 response나 EventStorage에 전달하지 않는다.
* parser/OCR failure는 allow 근거가 아니다.

---

## 9. 모듈별 실행 경계 계약

### Module: Extension File Handling

#### Purpose

Extension은 입력 이벤트를 감지하고 서버 분석 요청을 조립하는 client boundary다.

#### Runtime position

Browser runtime에서 Analyze API 호출 전에 실행된다.

#### Upstream dependency

* browser DOM event
* supported site adapter
* composer state
* File/Blob handle
* extension configuration

#### Downstream consumer

* upload/temp file endpoint
* Analyze API Route
* extension response action adapter

#### Responsibility

* composer text capture
* converted paste text capture
* paste/drop/attach/send-time interception
* File/Blob handle 확보
* upload/temp file flow 호출
* `AnalyzeInputItem[]` 조립
* server response action 적용

#### Non-responsibility

* file content parsing
* text file 내부 읽기
* PDF native text extraction
* OCR
* Office/spreadsheet/slide/code parsing
* secret/PII final decision
* final action decision
* raw file content logging
* original file name propagation
* base64 file payload를 analyze request에 포함

#### Input schema

```text
ExtensionInputEvent
```

#### Output schema

```text
AnalyzeRequest or TempUploadRequest
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| composer_text | Extension | Analyze API runtime | no | text input only |
| converted_paste_text | Extension | Analyze API runtime | no | converted paste only |
| file_ref | upload endpoint | Analyze API | temp metadata only | opaque |
| original_file_name | browser | nobody downstream | no | propagation forbidden |
| content for file | forbidden | none | no | extension must not create |

#### Invariants

* Extension never reads file content.
* Extension never performs OCR.
* Extension never sends base64 file payload in analyze body.
* File-derived text is produced only by server-side File Parser.

#### Boundary rules

* File/Blob handle available → upload/temp flow.
* File/Blob handle unavailable → `attachment_metadata` or `unsupported_attachment`.
* Original file name is not propagated to analyze request.
* Server response action is authoritative.

#### Failure handling

| failure case | fallback |
| --- | --- |
| File/Blob handle unavailable | `attachment_metadata` |
| upload failed | `unsupported_attachment` with `raw_file_unavailable` |
| site adapter missing | metadata-only request |
| send interception timeout | fail-closed based on extension policy |

#### Privacy / storage rules

* Extension logs must not include raw file content, OCR text, extracted text, original file name, or base64 payload.
* Extension local storage must not persist raw prompt or file content.

#### Unit tests

* `test_extension_does_not_read_file_content`
* `test_extension_does_not_perform_ocr`
* `test_extension_assembles_file_reference_input`

#### Contract tests

* `test_extension_never_sends_base64_file_payload`
* `test_extension_never_uses_kind_text_source_file`

#### Integration tests

* `test_upload_flow_returns_opaque_file_ref`
* `test_response_boolean_mapping_for_block_mask_warn_allow`

#### Done criteria

* File-derived text path is absent.
* All file inputs become `file_reference`, `attachment_metadata`, or `unsupported_attachment`.
* Existing response fields remain consumed.

---

### Module: Upload / Temporary Processing Storage

#### Purpose

Upload/temp flow는 Extension의 File/Blob handle을 encrypted temporary processing storage에 저장하고 opaque `file_ref`를 발급한다.

#### Runtime position

Extension file event 이후, Analyze API 요청 전에 실행된다.

#### Upstream dependency

* Extension upload request
* authenticated owner/session
* TemporaryFileStore
* Clock
* IdGenerator

#### Downstream consumer

* AnalyzeService
* ParserWorkerPool
* TtlCleanupWorker

#### Responsibility

* raw file bytes temporary 저장
* encryption at rest 적용
* opaque `file_ref` 생성
* owner/session/TTL metadata 생성
* content type/size validation
* cleanup scheduling
* upload response 생성

#### Non-responsibility

* file content parsing
* OCR
* policy decision
* EventStorage write
* original file name propagation
* permanent file storage

#### Input schema

```text
TempUploadRequest(authenticated_subject_id, session_id, temp_scope_id, blob, mime, extension, size_bucket)
```

#### Output schema

```text
TempUploadResponse(file_ref, file_kind, mime, extension, size_bucket, expires_at)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| file_ref | TemporaryFileStore | AnalyzeService/ParserWorker | temp metadata only | opaque |
| raw bytes | Extension upload | TemporaryFileStore | temporary encrypted | EventStorage forbidden |
| expires_at | TemporaryFileStore | cleanup worker | temp metadata only | required |
| authenticated_subject_id | auth/session | TemporaryFileStore | temp metadata only | required for access context |
| session_id | auth/session | TemporaryFileStore | temp metadata only | required for session scope |
| temp_scope_id | upload endpoint | TemporaryFileStore | temp metadata only | request/session-scoped access guard |
| original file name | browser | none | no | rejected/stripped |

#### Invariants

* TemporaryFileStore is not EventStorage.
* `file_ref` is not a permanent file ID.
* cleanup failure never logs content or file name.
* analyze completion triggers cleanup attempt.

#### Boundary rules

* AnalyzeService resolves only through `TemporaryFileStore`.
* ParserWorkerPayload contains `file_ref`, not bytes.
* temp storage may keep exact `size_bytes` for runtime enforcement only.
* event projection stores only `size_bucket`.

#### Failure handling

| failure case | fallback |
| --- | --- |
| upload too large | reject with size bucket only |
| unsupported type | return unsupported metadata |
| temp store unavailable | upload failure, no analyze file_ref |
| cleanup failure | metric + retry, no raw content in message |

#### Privacy / storage rules

* Encrypted temporary bytes are allowed only until TTL or analyze completion cleanup.
* EventStorage must not contain `file_ref`, temp path, raw bytes, extracted text, OCR text, or original file name.
* cleanup metrics may include failure code and count.

#### Unit tests

* `test_temp_store_encrypts_upload_object`
* `test_file_ref_is_opaque`

#### Contract tests

* `test_file_ref_has_ttl_and_owner_scope`
* `test_upload_endpoint_rejects_original_filename_downstream`

#### Integration tests

* `test_temp_file_cleanup_after_analyze`
* `test_temp_file_cleanup_after_ttl`

#### Done criteria

* upload endpoint returns opaque `file_ref`.
* temp object is owner/TTL scoped.
* cleanup is observable without content leakage.

---

### Module: Analyze API Route

#### Purpose

Route는 analyze 요청을 검증하고 `AnalyzeService`로 전달한다. Business logic, ML inference, policy decision은 수행하지 않는다.

#### Runtime position

HTTP request 수신 직후 실행된다.

#### Upstream dependency

* HTTP body
* authentication/session context
* public `AnalyzeRequest`
* legacy compatibility adapter

#### Downstream consumer

* `AnalyzeService`

#### Responsibility

* request schema validation
* auth/session validation 결과를 `login_id`로 전달
* request size limit 적용
* legacy request를 target `inputs[]`로 변환
* `AnalyzeService.analyze()` 호출
* `AnalyzeResponse` 반환
* route-level exception을 API error envelope로 변환

#### Non-responsibility

* parsing 수행 금지
* scanner 호출 금지
* embedding/classifier/verifier 호출 금지
* action/reason/user notice 결정 금지
* raw text logging 금지
* event storage 직접 write 금지

#### Input schema

```text
AnalyzeHttpRequest extends AnalyzeRequest
```

#### Output schema

```text
AnalyzeHttpResponse extends AnalyzeResponse
```

#### Field ownership

| field | produced by | consumed by | persisted | privacy risk |
| --- | --- | --- | ---: | --- |
| request_id | route/client | AnalyzeService/EventStorage | yes | low |
| inputs | client/adapter | AnalyzeService | no raw storage | high |
| login_id | auth/session | AnalyzeService/EventStorage | yes | medium |
| extension_version | client | metrics/compatibility | yes | low |
| action | Policy Orchestrator | extension UI | yes | low |

#### Invariants

* Route는 `action`, `reason_code`, `user_notice`를 결정하지 않는다.
* Route는 raw prompt, file content, OCR text를 log에 남기지 않는다.
* Route는 service call 외 pipeline module을 직접 호출하지 않는다.
* Route는 original file name field를 거부한다.

#### Boundary rules

* validation 실패는 `AnalyzeService`를 호출하지 않는다.
* auth 실패는 pipeline을 실행하지 않는다.
* client가 `request_id`를 보내지 않으면 route가 생성한다.
* `inputs[].content`는 runtime memory로만 전달한다.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| invalid request schema | HTTP 422 |
| auth failure | HTTP 401/403 |
| request too large | HTTP 413 |
| service timeout | HTTP 503 with retry-safe error |
| service internal failure | HTTP 500 with non-sensitive error id |

#### Privacy / storage rules

저장 금지: request body raw text, uploaded file bytes, full masked prompt, full URL path/query, original file name. 저장 허용: request_id, login_id, extension_version, schema_version, request size bucket, non-sensitive failure code.

#### Unit tests

* `test_route_rejects_invalid_schema`
* `test_route_preserves_request_id`

#### Contract tests

* `test_route_only_validates_and_calls_analyze_service`
* `test_route_does_not_evaluate_filter_rules`
* `test_route_does_not_write_event_directly`

#### Integration tests

* `test_api_response_keeps_extension_required_fields`
* `test_analyze_request_rejects_original_filename`

#### Done criteria

* Route calls AnalyzeService exactly once for valid requests.
* Route does not import parser/scanner/model/policy implementation.
* Route rejects raw file content and base64 payload.

---

### Module: AnalyzeService

#### Purpose

`AnalyzeService`는 전체 pipeline orchestration을 담당한다. 각 module을 정해진 순서대로 호출하고, 실패 결과를 `Policy Orchestrator`에 전달한다. Final action은 직접 결정하지 않는다.

#### Runtime position

Route validation 이후 실행된다.

#### Upstream dependency

* `AnalyzeRequest`
* authentication/session context
* WorkerRuntime
* model artifact registry
* policy config
* TemporaryFileStore port

#### Downstream consumer

* ParserWorkerPool
* normalizer
* scanner
* atom builder
* embedding worker
* segmenter
* mapper
* classifier
* verifier worker
* policy orchestrator
* notice/event serializer

#### Responsibility

* request-level `input_id` 검증 또는 생성
* `AnalyzeInputItem[]`을 service-local `InputEnvelope[]`로 정규화
* parser payload 생성
* module execution order 보장
* timeout budget 전달
* partial failure를 `PipelineFailure`로 수집
* `ScanStatus` aggregation
* policy request 조립
* user notice/event serialization 호출
* `AnalyzeResponse` 조립
* analyze completion cleanup 호출

#### Non-responsibility

* raw text 저장 금지
* action/reason_code 결정 금지
* classifier threshold 변경 금지
* verifier scope 확대 금지
* parser/scanner/model 내부 로직 수행 금지

#### Input schema

```text
AnalyzeServiceRequest(request_id, login_id, schema_version='v3', extension_version, inputs: list[AnalyzeInputItem])
```

#### Output schema

```text
AnalyzeResponse
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| input_id | client/service | all modules | yes | no raw content |
| InputEnvelope | AnalyzeService | service only | no | module-local |
| pipeline_failures | modules via service | Policy Orchestrator | code only | no raw message |
| scan_status | AnalyzeService | response/policy/storage | yes | status only |
| policy_decision | Policy Orchestrator | response serializer | allowlist | action source |

#### Invariants

* service는 scanner before normalizer를 허용하지 않는다.
* service는 segmenter after scanner 재호출을 허용하지 않는다.
* service는 verifier request를 LR candidate category 없이 만들지 않는다.
* service는 verifier timeout을 allow로 변환하지 않는다.
* service는 `InputEnvelope`를 공용 모듈 타입으로 노출하지 않는다.

#### Boundary rules

* module failures are data, not route exceptions, unless system unavailable.
* per-input partial failure는 `PolicyDecisionRequest`에 포함한다.
* text input은 parser text wrapper를 통과한다.
* file_ref는 반드시 ParserWorkerPool을 거친다.
* unsupported/metadata-only input도 policy evidence로 전달한다.

#### Failure handling

| failure case | fallback |
| --- | --- |
| parser partial | partial blocks continue, failure passed to policy |
| normalizer failure | original runtime fallback with failure flag |
| scanner timeout | partial signals continue |
| embedding unavailable | lexical-only conservative policy path |
| classifier unavailable | lexical-only conservative policy path |
| verifier timeout | LR + lexical conservative policy path |
| event write failed | response still returned, metric incremented |
| cleanup failed | response still returned, cleanup metric incremented |

#### Privacy / storage rules

저장 금지: raw prompt, parsed text, normalized text, atom text, segment text, embedding vector, raw category_scores, raw suppressor_scores, verifier input dump, full masked prompt. 저장 허용: request_id, input_id, status code, failure code, action/reason metadata after policy.

#### Unit tests

* `test_analyze_service_normalizes_inputs_to_envelopes`
* `test_analyze_service_collects_pipeline_failures`

#### Contract tests

* `test_analyze_service_runs_modules_in_contract_order`
* `test_analyze_service_does_not_decide_action`
* `test_input_envelope_is_service_local_only`

#### Integration tests

* `test_file_ref_must_go_through_parser_worker_pool`
* `test_temp_file_cleanup_after_analyze`

#### Done criteria

* Pipeline order is fixed.
* Final action equals mocked `PolicyDecision.action`.
* All file_reference inputs pass through ParserWorkerPool.
* Failure messages contain no raw content.

---

### Module: ParserWorkerPool

#### Purpose

`ParserWorkerPool`은 File Parser logical stage의 worker execution boundary다. Queue, timeout, backpressure, worker lifecycle, crash isolation, structured failure boundary를 담당한다.

#### Runtime position

`AnalyzeService`가 `ParserWorkerPayload`를 만든 직후, normalizer보다 먼저 실행된다.

#### Upstream dependency

* `ParserWorkerPayload`
* worker runtime config
* queue/backpressure policy
* timeout budget
* `FileParserRunner` port

#### Downstream consumer

* `FileParserResult`
* `AnalyzeService` for `ScanStatus` aggregation
* `Policy Orchestrator` via parser/OCR status

#### Responsibility

* parser worker queue 관리
* timeout budget 적용
* worker lifecycle 관리
* backpressure 처리
* crash isolation
* structured `PipelineFailure` boundary 생성
* `FileParserRunner.parse(payload)` 호출
* `FileParserResult` 반환

#### Non-responsibility

* PDF parsing 직접 수행
* OCR 직접 수행
* Office/spreadsheet/slide/code parsing 직접 수행
* adapter selection 직접 수행
* parser plan resolution 직접 수행
* `ParsedDocument` merge 직접 수행
* keyword/regex scan
* normalization
* embedding/classification/verification
* policy decision
* user notice 생성
* EventStorage write
* raw file bytes persistence
* original file name propagation
* OCR/extracted text logging

#### Input schema

```text
ParserWorkerPayload
```

#### Output schema

```text
FileParserResult(input_id, document: ParsedDocument | None, parser_status, ocr_status, failure)
```

#### Invariants

* ParserWorkerPool does not import concrete parser libraries.
* ParserWorkerPool does not select adapters directly.
* ParserWorkerPool does not resolve `file_ref` to a path directly.
* ParserWorkerPool does not emit action, reason_code, or user notice.

#### Tests

* `test_parser_worker_pool_invokes_file_parser_runner`
* `test_parser_worker_pool_does_not_select_adapter_directly`
* `test_parser_worker_pool_does_not_import_concrete_parser_libraries`
* `test_parser_worker_pool_returns_structured_failure_on_timeout`

#### Done criteria

* All parser jobs cross one worker boundary.
* Worker failure message contains no raw content, temp path, or original file name.
* Queue payload dump is disabled.

---

### Module: FileParserRunner

#### Purpose

`FileParserRunner`는 worker 내부 file parsing use case 조율자다. `ParserWorkerPayload`를 받아 temporary file resolution, plan resolution, plan execution을 순서대로 호출하고 `FileParserResult`를 반환한다.

#### Runtime position

`ParserWorkerPool` 내부에서 실행된다.

#### Upstream dependency

* `ParserWorkerPayload`
* `TemporaryFileResolverPort`
* `ParserPlanResolver`
* `ParserPlanExecutor`
* parser limits
* clock/metrics port

#### Downstream consumer

* `ParserWorkerPool`
* `AnalyzeService`

#### Responsibility

* text wrapper input은 resolved file 없이 plan execution으로 전달
* file_reference input은 `TemporaryFileResolverPort`로 runtime-only file handle resolve
* `ParserPlanResolver` 호출
* `ParserPlanExecutor` 호출
* partial failure를 `FileParserResult`로 집계
* cleanup signal을 AnalyzeService/runtime에 전달

#### Non-responsibility

* concrete parser library 직접 import
* OCR engine 직접 import
* parser step 직접 실행
* plan selection 외부 노출
* policy decision
* EventStorage write

#### Invariants

* FileParserRunner depends on ports/interfaces, not concrete parser implementations.
* Temporary file resolution is called only inside parser worker runtime.
* FileParserRunner returns only `FileParserResult`.

#### Tests

* `test_file_parser_runner_invokes_temp_file_resolver_inside_worker_runtime`
* `test_file_parser_runner_invokes_plan_resolver`
* `test_file_parser_runner_invokes_plan_executor`
* `test_file_parser_runner_does_not_import_concrete_parser_libraries`

#### Done criteria

* Use case orchestration is isolated from worker queue logic.
* Concrete parser dependencies remain behind adapters/ports.

---

### Module: ParserPlanResolver

#### Purpose

`ParserPlanResolver`는 `file_kind`, MIME, extension, `extraction_requirement`, parser config, adapter capability, resolved metadata, license policy를 기준으로 typed `ParserExecutionPlan`을 만든다.

#### Runtime position

`FileParserRunner` 내부에서 plan execution 전에 실행된다.

#### Responsibility

* adapter registry 조회
* license policy를 통과한 adapter capability만 selection에 사용
* `ParserExecutionPlan.steps[]` 생성
* `ParserExecutionPlan.fallback_rules[]` 생성
* unsupported reason code 생성
* deterministic plan 생성

#### Non-responsibility

* parsing/OCR 수행
* plan execution 수행
* policy decision 생성
* user notice 생성
* EventStorage write

#### Invariants

* `ParserWorkerPayload`는 concrete execution plan을 포함하지 않는다.
* `fallback order` 문자열은 사용하지 않는다.
* steps and fallback rules are typed and separated.

#### Tests

* `test_parser_worker_payload_contains_coarse_extraction_requirement_only`
* `test_analyze_service_does_not_create_concrete_extraction_plan`
* `test_parser_plan_resolver_returns_typed_execution_plan`
* `test_parser_execution_plan_steps_are_ordered_and_deterministic`
* `test_parser_execution_plan_separates_steps_and_fallback_rules`
* `test_unsupported_and_metadata_only_are_distinct`

#### Done criteria

* Plan resolution is deterministic and testable without real parser/OCR dependencies.

---

### Module: ParserPlanExecutor

#### Purpose

`ParserPlanExecutor`는 `ParserExecutionPlan.steps[]`를 정해진 순서대로 실행하고, 실행 중 필요한 경우 `fallback_rules[]`를 적용해 `FileParserResult`를 집계한다.

#### Runtime position

`FileParserRunner` 내부에서 plan resolution 이후 실행된다.

#### Upstream dependency

* `ParserExecutionPlan`
* `ParserAdapter` implementations through registry
* `OcrEnginePort`
* PDF renderer port
* parser limits
* resolved runtime file handle

#### Responsibility

* plan step 순서 실행
* fallback rule trigger 평가
* ParserAdapter 호출
* OcrEnginePort 호출
* renderer port 호출
* partial result 집계
* unsupported result 생성
* failure를 `FileParserResult`에 포함
* deterministic block order와 deterministic block_id 보장

#### Non-responsibility

* parser plan 선택
* policy decision
* scanner/normalizer/model 호출
* raw exception 노출
* EventStorage write

#### Invariants

* ParserPlanExecutor does not emit action, reason_code, or user notice.
* ParserPlanExecutor applies fallback rules only on defined triggers.
* ParserPlanExecutor does not call scanner, classifier, verifier, or policy.

#### Tests

* `test_parser_plan_executor_runs_steps_in_order`
* `test_parser_plan_executor_applies_fallback_rules_only_on_defined_triggers`
* `test_parser_plan_executor_does_not_emit_policy_decision`
* `test_all_parser_adapters_return_file_parser_result`
* `test_parser_does_not_call_scanner`

#### Done criteria

* All file parser behaviors are represented by typed execution plans.
* Partial and failure cases are structured and privacy-safe.

---

### Module: ParsedDocument / ParsedBlock

#### Purpose

`ParsedDocument`와 `ParsedBlock`은 parser 결과를 pipeline 전체에서 공유하는 불변 내부 표현으로 고정한다.

#### Runtime position

File Parser output으로 생성되며, normalizer와 atomizer의 공통 upstream type이다.

#### Upstream dependency

* `FileParserResult`

#### Downstream consumer

* RepeatedSpecialCharNormalizer
* AnalysisAtom Builder
* Policy Orchestrator through status metadata

#### Responsibility

* input 단위 document 표현
* block 단위 text와 location 표현
* parser/OCR status 표현
* extraction provenance 표현
* deterministic block ordering 보장

#### Non-responsibility

* text extraction 수행 금지
* normalization 수행 금지
* signal 탐지 금지
* segmentation 수행 금지
* action/reason/user notice 표현 금지

#### Input schema

```text
ParsedBlockBuildInput(input_id, block_id, text, source, location, extraction_status)
```

#### Output schema

```text
ParsedDocument(input_id, file_ref, file_kind, parser_id, parser_version, parser_status, ocr_status, blocks, metadata)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| input_id | AnalyzeService | all modules | yes | id only |
| parser_id | parser | diagnostics/storage | yes | no raw content |
| block_id | parser | normalizer/atomizer/mapper | id only | deterministic |
| text | parser | runtime modules | no | critical runtime-only |
| location | parser | response location hint | limited | EventRecord stores `location_kind` only |
| metadata | parser | policy/storage serializer | allowlist only | no title/author/file name |

#### Invariants

* `ParsedBlock.text` remains original extracted text for that block.
* `block_id` is deterministic within input.
* block order preserves source order.
* metadata is allowlist-only and cannot contain original file name, document title, author, raw content, OCR text, normalized text, or raw values.

#### Boundary rules

* `ParsedBlock.text` is memory-only.
* `location` must be convertible to `LocationHint`.
* `ParsedDocument` does not contain normalized text.
* `ParsedDocument` does not contain action fields.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| parser failed | `ParsedDocument=None` |
| partial parse | available blocks + `parser_status='partial'` |
| empty document | `blocks=[]` |
| missing location | `location=None`, location_hint omitted |

#### Privacy / storage rules

저장 금지: `ParsedBlock.text`, document title, author, original file name, sheet name if user-provided. 저장 허용: block_id, parser_id, parser_version, parser_status, ocr_status, location_kind.

#### Unit tests

* `test_parsed_block_order_is_stable`
* `test_forbidden_metadata_removed`

#### Contract tests

* `test_parsed_document_validates_all_parser_outputs`
* `test_parsed_block_text_not_persisted`

#### Integration tests

* `test_spreadsheet_parse_preserves_row_location`
* `test_event_storage_has_no_original_filename`

#### Done criteria

* Parser adapters return valid `ParsedDocument`.
* Forbidden metadata is stripped or validation fails.
* No raw block text enters EventStorage.

---

### Module: RepeatedSpecialCharNormalizer

#### Purpose

`RepeatedSpecialCharNormalizer`는 keyword/regex 탐지 회피를 줄이기 위해 반복 특수문자를 정규화하고, normalized text와 original text 간 offset mapping을 생성한다.

#### Runtime position

`ParsedDocument` 생성 후, `Lexical Signal Scanner` 실행 전에 반드시 실행된다.

#### Upstream dependency

* `ParsedDocument`
* `NormalizationPolicy`

#### Downstream consumer

* Lexical Signal Scanner
* offset restoration tests

#### Responsibility

* 반복 특수문자 canonicalization
* original text 보존
* normalized text 별도 생성
* normalized range와 original range mapping 생성
* scanner span restoration 지원

#### Non-responsibility

* original text overwrite 금지
* semantic rewrite 금지
* 일반 자연어 반복 문자 축약 금지
* keyword/regex scan 금지
* PolicyDecision 생성 금지
* segment 생성 금지

#### Input schema

```text
NormalizerRequest(document: ParsedDocument, policy: NormalizationPolicy)
```

#### Output schema

```text
NormalizedDocument(input_id, blocks: list[NormalizedBlock], normalizer_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| original_text | parser | normalizer/scanner mapping runtime | no | critical |
| normalized_text | normalizer | scanner runtime | no | critical |
| offset_map | normalizer | scanner | no event | runtime |
| normalizer_version | normalizer | diagnostics/tests | yes | version only |
| warnings | normalizer | policy/metrics | code only | no raw content |

#### Invariants

* original text is never overwritten.
* normalized text must not replace `ParsedBlock.text`.
* Every normalized char range must restore to original range or fail closed for that signal.
* Mapping uses half-open ranges `[start, end)`.

#### Boundary rules

* downstream scanner may scan normalized text.
* scanner output must include both normalized and original ranges.
* offset mapping is runtime-only unless exported as sanitized test artifact.
* natural-language repeated letters are not collapsed by this normalizer.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| empty block | `normalized_text=''`, `offset_map=[]` |
| offset mapping failure | `failure.code='OFFSET_MAPPING_FAILED'` |
| unsupported unicode sequence | original sequence preserved, warning code |
| too large block | block-level safe split, warning code |
| normalization timeout | normalized block equals original, failure passed |

#### Privacy / storage rules

저장 금지: original text, normalized text, normalized excerpt, raw matched values. 저장 허용: normalizer_version, warning code, failure code, mapping count bucket.

#### Unit tests

* `test_normalizer_preserves_original_text`
* `test_normalizer_mapping_uses_half_open_range`

#### Contract tests

* `test_normalized_span_restores_original_range`
* `test_normalizer_does_not_emit_signal`

#### Integration tests

* `test_scanner_uses_normalized_text`
* `test_event_storage_has_no_raw_text`

#### Done criteria

* Original/normalized offset restoration works.
* Normalizer emits no signal/action fields.
* No normalized text is persisted.

---

### Module: Lexical Signal Scanner

#### Purpose

`Lexical Signal Scanner`는 normalized text에서 keyword/regex 기반 signal 후보를 탐지한다. Scanner는 signal metadata만 생성한다.

#### Runtime position

RepeatedSpecialCharNormalizer 직후, AnalysisAtom/segment 생성과 독립적으로 한 번 실행된다.

#### Upstream dependency

* `NormalizedDocument`
* `LexicalRuleSnapshot`
* `ProtectedTargetConfig[]` from secure ProtectedTarget Registry

#### Downstream consumer

* Signal-to-Segment Mapper
* Policy Orchestrator
* Event metadata serializer

#### Responsibility

* PII-like span 후보 탐지
* secret-like span 후보 탐지
* token candidate 탐지
* protected target hit 탐지
* custom regex hit 탐지
* sensitive value pattern hit 탐지
* context trigger hit 탐지
* normalized range와 original range 동시 반환
* raw value 대신 fingerprint 또는 pattern metadata 반환
* `scanner_status` 생성

#### Non-responsibility

* final action 결정 금지
* PolicyDecision 생성 금지
* reason_code 확정 금지
* segment 생성 금지
* embedding/classification 금지
* RoBERTa verifier 호출 금지
* user notice 생성 금지

#### Input schema

```text
LexicalScanRequest(normalized_document, rule_snapshot, protected_targets)
```

#### Output schema

```text
LexicalScanResult(input_id, signals, scanner_status, scanner_version, rule_snapshot, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| signal_id | scanner | mapper/policy/storage | yes | id only |
| signal_type | scanner | mapper/policy/storage | yes | metadata |
| pattern_id | scanner | policy/storage | yes | no raw regex body |
| match_basis | scanner | mapper/policy/storage | yes | deterministic semantics |
| normalized_range | scanner | tests/debug runtime | no event | runtime |
| original_range | scanner | mapper/location hint | limited | no value reconstruction |
| value_fingerprint | scanner | policy/storage | yes | irreversible |
| metadata | scanner | policy | allowlist only | no raw value |

#### Invariants

* scanner never returns raw matched value.
* scanner returns original and normalized range for each signal.
* scanner is not called again inside chunking/segmenting.
* regex, keyword, protected target, and fingerprint results are match results, not probabilistic confidence scores.
* scanner does not emit `confidence_hint` for regex/keyword/protected-target matches.
* mapping restoration failure must not leak raw value.

#### Boundary rules

* scanner operates over normalized text.
* scanner output range must be restored to original range before mapping.
* deterministic regex/keyword/protected-target/fingerprint matches use `deterministic=True`.
* heuristic token-like candidates use `deterministic=False` and `match_basis='heuristic_regex'` unless stronger deterministic rule applies.
* custom regex timeout disables that rule only.
* protected target hit returns opaque target_id, not raw protected target text.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| regex timeout | rule skipped, warning |
| invalid custom regex | rule disabled, warning |
| empty document | `signals=[]` |
| mapping restore failure | signal discarded, failure code |
| scanner timeout | partial signals + `LEXICAL_SCAN_TIMEOUT` |
| protected target registry unavailable | continue without protected targets, failure code |

#### Privacy / storage rules

저장 금지: matched raw value, normalized text, original text, OCR text, secret value, raw file bytes, original file name, raw protected target text, raw rule body. 저장 허용: signal_type, pattern_id, match_basis, deterministic, severity_hint, value_fingerprint, protected_target_id, protected_target_type, protected_target_registry_version, location_kind.

#### Unit tests

* `test_scanner_uses_normalized_text`
* `test_scanner_restores_original_range`

#### Contract tests

* `test_scanner_never_returns_raw_value`
* `test_scanner_returns_original_and_normalized_range`
* `test_scanner_emits_match_basis_and_deterministic_flag`
* `test_scanner_does_not_emit_confidence_hint`

#### Integration tests

* `test_segmenter_does_not_rescan_keywords`
* `test_protected_target_registry_does_not_store_raw_target_in_event`

#### Done criteria

* All signals contain original/normalized ranges.
* No raw matched value is present in scanner output.
* Protected target event projection is opaque.

---

### Module: AnalysisAtom Builder

#### Purpose

`AnalysisAtom Builder`는 `ParsedBlock`을 embedding과 semantic segmentation에 적합한 atom 단위로 분해한다.

#### Runtime position

Parser output 이후 실행된다. Normalizer/scanner와 병렬 실행될 수 있으나 atom은 original text 기준으로 생성한다.

#### Upstream dependency

* `ParsedDocument`
* `AtomizationPolicy`

#### Downstream consumer

* Qwen3 Atom Embedding Worker
* Adjacent Semantic Segmenter
* Signal-to-Segment Mapper
* SegmentEmbedding Builder

#### Responsibility

* paragraph, sentence, row group, code block, OCR line atom 생성
* block structure 보존
* original range 유지
* atom membership 유지
* deterministic atom id 생성

#### Non-responsibility

* keyword/regex 탐지 금지
* normalization 금지
* embedding 계산 금지
* segment classification 금지
* signal mapping 금지
* action 결정 금지

#### Input schema

```text
AtomBuildRequest(document: ParsedDocument, atom_policy: AtomizationPolicy)
```

#### Output schema

```text
AnalysisAtomBuildResult(input_id, atoms, atomizer_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| atom_id | atom builder | embedding/segmenter/mapper | id only | deterministic |
| text | atom builder | embedding runtime | no | critical |
| original_range | atom builder | segmenter/mapper | no event | runtime |
| atom_type | atom builder | segmenter/metrics | yes | metadata |
| ordinal | atom builder | segmenter | yes | no raw content |

#### Invariants

* atom text is derived from original parsed block text.
* atom id is deterministic.
* atom original range is within parent block range.
* atom output contains no classification/action fields.

#### Boundary rules

* normalizer output must not overwrite atom text.
* atom membership is the authoritative structural link for mapping.
* max atom size fallback must preserve range continuity.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| empty blocks | `atoms=[]` |
| huge block | split by max chars |
| invalid unicode | warning, range preserved |
| atomization timeout | block-level fallback atom |
| malformed table | paragraph fallback |

#### Privacy / storage rules

저장 금지: atom text, original text excerpt, atom-level raw content. 저장 허용: atom_id, block_id, atom_type, length bucket, location_kind.

#### Unit tests

* `test_atom_builder_preserves_original_range`
* `test_atom_id_is_deterministic`

#### Contract tests

* `test_atom_text_not_persisted`
* `test_atom_builder_does_not_scan_keywords`

#### Integration tests

* `test_atom_builder_handles_table_rows`
* `test_signal_mapper_uses_atom_membership`

#### Done criteria

* Atom ids are stable.
* Atom ranges are valid.
* Atom builder has no scanner dependency.

---

### Module: Qwen3 Atom Embedding Worker

#### Purpose

`Qwen3 Atom Embedding Worker`는 `AnalysisAtom.text`를 `Qwen/Qwen3-Embedding-0.6B` embedding vector로 변환한다.

#### Runtime position

AnalysisAtom Builder 이후, Adjacent Semantic Segmenter 이전에 실행된다.

#### Upstream dependency

* `AnalysisAtom[]`
* embedding worker queue
* Qwen3 singleton model loader

#### Downstream consumer

* Adjacent Semantic Segmenter
* SegmentEmbedding Builder

#### Responsibility

* Qwen3 embedding model singleton load
* request마다 model reload 금지
* atom text batch embedding
* micro-batching
* embedding dimension, model version 반환
* timeout/failure를 structured result로 반환

#### Non-responsibility

* Qwen3 fine-tuning 금지
* LR classifier 학습 금지
* classifier prediction 금지
* segment boundary 결정 금지
* final action 결정 금지

#### Input schema

```text
AtomEmbeddingRequest(input_id, atoms, model_name='Qwen/Qwen3-Embedding-0.6B', normalize_vectors, timeout_ms)
```

#### Output schema

```text
AtomEmbeddingResult(input_id, embeddings: list[AtomEmbedding], embedding_model_version, dimension, normalized, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| model_name | config | worker | yes | version metadata |
| atom_id | atom builder | embedding/segmenter | id only | no raw |
| vector | embedding worker | segmenter/segment embedding | no | high privacy |
| embedding_model_version | worker | classifier/audit | yes | version only |
| dimension | worker | validation | yes | metadata |
| normalized | worker | segmenter/classifier | yes | metadata |

#### Invariants

* Qwen3 model is frozen.
* model loader is singleton per process or worker lifecycle.
* embedding result order matches request atom order.
* embedding vector is never persisted in EventStorage.

#### Boundary rules

* worker queue payload is memory-only.
* model errors must not include raw input text.
* partial batch failure returns failed atom ids, not raw text.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| model not loaded | `EMBEDDING_MODEL_UNAVAILABLE` |
| timeout | `EMBEDDING_TIMEOUT` |
| OOM | retry smaller batch once, then failure |
| empty atoms | `embeddings=[]` |
| partial batch failure | partial result + failed atom ids |
| queue full | backpressure then timeout |

#### Privacy / storage rules

저장 금지: atom text, embedding vector, worker queue dump, model input dump. 저장 허용: model_version, dimension, batch size bucket, latency bucket, failure code.

#### Unit tests

* `test_atom_embedding_order_preserved`
* `test_qwen_model_frozen`

#### Contract tests

* `test_qwen_model_loaded_once`
* `test_embedding_vector_not_persisted`

#### Integration tests

* `test_embedding_worker_timeout_returns_failure`
* `test_worker_queue_dump_disabled`

#### Done criteria

* Qwen3 loads once per worker lifecycle.
* Vectors are runtime-only.
* Timeout and OOM return structured failures.

---

### Module: Adjacent Semantic Segmenter

#### Purpose

`Adjacent Semantic Segmenter`는 인접 atom embedding의 cosine similarity와 source structure를 사용해 semantic segment를 생성한다.

#### Runtime position

Atom embedding 이후, signal mapping 이전에 실행된다.

#### Upstream dependency

* `AnalysisAtom[]`
* `AtomEmbedding[]`
* `SegmentPolicy`

#### Downstream consumer

* Signal-to-Segment Mapper
* SegmentEmbedding Builder
* LR classifier
* RoBERTa verifier

#### Responsibility

* adjacent cosine similarity 계산
* semantic boundary 후보 생성
* structure boundary usage
* min/target/max segment size 적용
* segment atom membership 생성
* segment original range 생성

#### Non-responsibility

* keyword/regex 재탐지 금지
* signal 생성 금지
* classifier label 예측 금지
* action 결정 금지
* verifier 호출 금지

#### Input schema

```text
SegmentBuildRequest(input_id, atoms, atom_embeddings, segment_policy)
```

#### Output schema

```text
SegmentBuildResult(input_id, segments, boundary_scores, segmenter_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| segment_id | segmenter | mapper/classifier/verifier/policy | id only | no raw |
| atom_ids | segmenter | mapper/segment embedding | ids only | no raw |
| text | segmenter | classifier/verifier runtime | no | critical |
| original_range | segmenter | mapper/location | no event | runtime |
| locations | segmenter | response hint | limited | EventRecord `location_kind` only |
| boundary_scores | segmenter | diagnostics | summary only | no raw text |

#### Invariants

* segmenter never invokes scanner.
* segment must include atom membership.
* segment text remains runtime-only.
* original range must cover member atoms.

#### Boundary rules

* missing embedding triggers structure/size fallback.
* overlapping segments require explicit atom ids.
* signal mapping happens only after segments are created.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| no atoms | `segments=[]` |
| missing embedding | structure/size fallback |
| similarity failure | structure fallback |
| too large segment | max chars split |
| all atoms too short | single segment |
| timeout | block-level fallback segments |

#### Privacy / storage rules

저장 금지: segment text, atom text, original content excerpt, embedding vector. 저장 허용: segment_id, atom count, segment_type, confidence bucket, location_kind, boundary score summary without text.

#### Unit tests

* `test_adjacent_similarity_creates_boundary`
* `test_segment_contains_atom_membership`

#### Contract tests

* `test_segmenter_does_not_rescan_keywords`
* `test_segment_text_not_persisted`

#### Integration tests

* `test_signal_mapper_uses_original_offset_overlap`
* `test_segmenter_structure_fallback`

#### Done criteria

* Segmenter has no scanner dependency.
* Segments contain atom membership and original ranges.
* No segment text is persisted.

---

### Module: Signal-to-Segment Mapper

#### Purpose

`Signal-to-Segment Mapper`는 scanner가 생성한 `LexicalSignal`을 segment에 연결한다.

#### Runtime position

Segments 생성 후, segment embedding/classification 전에 실행된다.

#### Upstream dependency

* `LexicalSignal[]`
* `AnalysisSegment[]`
* `AnalysisAtom[]`
* `SignalMappingPolicy`

#### Downstream consumer

* Logistic Regression Segment Classifier
* Policy Orchestrator
* Event metadata serializer

#### Responsibility

* original offset overlap 기준 매핑
* atom membership 기준 매핑
* segment별 signal summary 생성
* duplicate signal 제거
* severity summary 생성
* protected target / secret / high-risk PII flag 생성

#### Non-responsibility

* keyword/regex 재탐지 금지
* signal risk final 판단 금지
* classifier score 생성 금지
* action/reason/user notice 생성 금지

#### Input schema

```text
SignalMappingRequest(input_id, segments, atoms, lexical_signals, mapping_policy)
```

#### Output schema

```text
SignalMappingResult(input_id, segment_signal_sets, mapper_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| segment_id | segmenter | mapper/classifier/policy | id only | no raw |
| signal_ids | mapper | classifier/policy/storage | yes | id only |
| signals | mapper | policy runtime | metadata projection only | no raw value |
| max_severity_hint | mapper | policy/storage | yes | metadata |
| has_protected_target | mapper | classifier/policy/storage | yes | metadata |
| has_deterministic_secret_signal | mapper | policy | yes | not final confirmation |
| has_high_risk_pii_signal | mapper | policy | yes | not final confirmation |

#### Invariants

* mapper uses existing signals only.
* offset overlap uses original range.
* mapper never includes raw matched value.
* mapper never emits action.

#### Boundary rules

* atom membership may resolve ambiguous offset overlap.
* invalid range signal is skipped with warning.
* signal may map to multiple segments only when overlap policy allows.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| no signals | empty sets for each segment |
| no segments | empty result |
| invalid range | skip signal + warning |
| ambiguous overlap | map to candidates with ambiguous flag |
| missing atom | offset-only fallback |

#### Privacy / storage rules

저장 금지: raw signal value, original text, segment text, normalized text. 저장 허용: signal_id, signal_type, pattern_id, severity_hint, fingerprint, flags.

#### Unit tests

* `test_signal_mapper_uses_original_offset_overlap`
* `test_signal_mapper_uses_atom_membership`

#### Contract tests

* `test_signal_mapper_does_not_rescan`
* `test_signal_mapper_never_returns_raw_value`

#### Integration tests

* `test_signal_mapper_drops_invalid_range`
* `test_policy_orchestrator_only_module_emits_action`

#### Done criteria

* Signal mapping is deterministic.
* Mapper emits no raw value/action.
* Mapper flags are treated as evidence inputs, not final policy confirmation.

---

### Module: SegmentEmbedding Builder

#### Purpose

`SegmentEmbedding Builder`는 segment membership과 atom embeddings를 사용해 classifier 입력용 `SegmentEmbedding`을 생성한다.

#### Runtime position

Signal mapping 이후 또는 병렬로 실행될 수 있으며, LR classifier 전에 완료되어야 한다.

#### Upstream dependency

* `AnalysisSegment[]`
* `AnalysisAtom[]`
* `AtomEmbedding[]`
* `SegmentEmbeddingPolicy`

#### Downstream consumer

* Logistic Regression Segment Classifier

#### Responsibility

* segment에 속한 atom embeddings 수집
* pooling strategy 적용
* segment vector 생성
* model version/dimension 유지
* vector normalization 여부 유지

#### Non-responsibility

* Qwen3 model loading 금지
* atom text embedding 직접 계산 금지
* label scoring 금지
* action 결정 금지
* vector persistence 금지

#### Input schema

```text
SegmentEmbeddingBuildRequest(input_id, segments, atom_embeddings, policy)
```

#### Output schema

```text
SegmentEmbeddingBuildResult(input_id, segment_embeddings, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| segment_id | segmenter | segment embedding/classifier | id only | no raw |
| vector | SegmentEmbedding Builder | classifier | no | high privacy |
| pooling | builder | classifier/audit | yes | metadata |
| dimension | builder | classifier validation | yes | metadata |
| normalized | builder | classifier | yes | metadata |

#### Invariants

* segment vector dimension equals atom vector dimension.
* vector ordering is stable by segment order.
* missing atom embedding must not silently create zero vector unless policy explicitly allows.

#### Boundary rules

* segment embedding does not include raw text.
* pooling strategy is part of artifact compatibility.
* classifier rejects embedding dimension mismatch.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| missing atom embedding | `SEGMENT_EMBEDDING_MISSING_ATOM` |
| dimension mismatch | failure, classifier skip |
| empty segment atom ids | failure or zero-vector disabled |
| timeout | failure passed to policy |
| vector normalization failure | unnormalized vector only if artifact permits |

#### Privacy / storage rules

저장 금지: segment vector, atom vector, segment text, atom text. 저장 허용: dimension, pooling, normalized flag, failure code, model version.

#### Unit tests

* `test_segment_embedding_mean_pooling`
* `test_segment_embedding_dimension_mismatch_fails`

#### Contract tests

* `test_segment_embedding_not_persisted`
* `test_segment_embedding_preserves_segment_order`

#### Integration tests

* `test_lr_classifier_does_not_emit_action`
* `test_event_storage_has_no_raw_text`

#### Done criteria

* Segment embeddings are stable and dimension-valid.
* Missing data fails explicitly.
* Vectors are runtime-only.

---

### Module: Logistic Regression Segment Classifier

#### Purpose

이 모듈은 `SegmentEmbedding`을 입력받아 One-vs-Rest Logistic Regression으로 risk/context candidate category를 산출하는 빠른 1차 문맥 분류기다.

#### Runtime position

SegmentEmbedding Builder 이후, RoBERTa verifier 이전에 실행된다.

#### Upstream dependency

* `AnalysisSegment`
* `SegmentEmbedding`
* `SegmentSignalSet`
* classifier artifact files

#### Downstream consumer

* KLUE RoBERTa Context Verifier
* Policy Orchestrator
* model evaluation reports

#### Responsibility

* Qwen3 embedding 기반 segment vector 사용
* Logistic Regression artifact load
* One-vs-Rest multi-label inference
* label별 score 출력
* threshold 비교
* LR candidate category 생성
* confidence bucket 생성

#### Non-responsibility

* Qwen3 model fine-tuning 금지
* final action 결정 금지
* user-facing message 생성 금지
* reason_code 확정 금지
* RoBERTa verification 수행 금지
* hard_eval 기준 threshold tuning 금지

#### Input schema

```text
SegmentClassificationRequest(segment, segment_embedding, segment_signals, classifier_artifact)
```

#### Output schema

```text
SegmentClassificationResult(segment_id, category_scores, predicted_categories, thresholded_categories, suppressor_scores, confidence_bucket, classifier_model_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| category_scores | LR classifier | verifier/policy | bucket only | raw score runtime-only |
| predicted_categories | LR classifier | verifier/policy | yes | labels only |
| thresholded_categories | LR classifier | verifier | yes | verifier candidates |
| suppressor_scores | classifier | policy | bucket only | raw score runtime-only |
| confidence_bucket | classifier | policy/storage | yes | bucket |
| classifier_model_version | classifier | policy/storage/report | yes | version |

#### Invariants

* Qwen3 embedding model is frozen.
* LR is the trainable first-stage classifier.
* classifier does not emit action, reason_code, user_notice.
* `thresholded_categories` are the only default verifier candidates.
* `hard_eval` is never used for threshold tuning or model selection.

#### Boundary rules

* thresholds are read from `context_with_<prefix>_thresholds.json`.
* default threshold may be `0.50` only when no explicit practical-dev-selected threshold artifact exists.
* threshold suggestion reports are diagnostic, not auto-applied.
* suppressor labels are not final risk targets unless a separate scorer contract is added.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| missing embedding | `SEGMENT_EMBEDDING_MISSING` |
| artifact missing | `CLASSIFIER_ARTIFACT_MISSING` |
| threshold missing | label disabled + warning |
| empty segment | scores empty, low confidence |
| classifier timeout | policy uses lexical signals conservatively |
| dimension mismatch | classifier failure |

#### Privacy / storage rules

저장 금지: segment text, embedding vector, raw classifier input, raw example text in model card. 저장 허용: model_version, category names, confidence_bucket, score buckets, threshold artifact version.

#### Unit tests

* `test_one_vs_rest_multilabel_output`
* `test_lr_classifier_uses_thresholds_from_practical_validation`

#### Contract tests

* `test_lr_classifier_does_not_emit_action`
* `test_lr_candidate_categories_feed_verifier_only`

#### Integration tests

* `test_roberta_verifier_skips_without_lr_candidate`
* `test_policy_timeout_is_not_allow_reason`

#### Done criteria

* LR emits candidate categories, not actions.
* Artifact dimension and label map are validated.
* hard_eval contamination is rejected.

---

### Module: KLUE RoBERTa Context Verifier

#### Purpose

`KLUE RoBERTa Context Verifier`는 LR classifier가 제안한 `(segment, candidate_category)` pair를 label-aware binary verification으로 confirm/reject한다.

#### Runtime position

LR classifier 이후, Policy Orchestrator 이전에 실행된다.

#### Upstream dependency

* `AnalysisSegment`
* `SegmentMetadata`
* `SegmentClassificationResult`
* `LexicalSignal[]`
* LR candidate categories
* verifier model artifact

#### Downstream consumer

* Policy Orchestrator

#### Responsibility

* LR candidate category별 verification request 생성
* candidate category confirm/reject/uncertain/timeout/failed 반환
* confidence 반환
* reason code candidate 반환 가능
* timeout/failure를 structured result로 반환

#### Non-responsibility

* LR miss label 추가 금지
* all-label classification 금지
* final action 결정 금지
* recommended_action 확정 금지
* reason_code 최종 확정 금지
* user-facing message 생성 금지
* raw text 저장 금지

#### Input schema

```text
RobertaVerificationRequest(request_id, segment, segment_metadata, candidate_category, lexical_signals, classifier_result, verification_context, verifier_model_version, timeout_ms)
```

#### Output schema

```text
RobertaVerificationResult(segment_id, candidate_category, verifier_status, accepted, confidence, reason_code_candidates, verifier_model_version, failure)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| candidate_category | LR classifier/service | verifier/policy | yes | candidate only |
| verifier_status | verifier | policy/storage | yes | status |
| accepted | verifier | policy | yes | not action |
| confidence | verifier | policy | bucket only | raw runtime |
| reason_code_candidates | verifier | Policy Orchestrator | no final | candidates only |
| verifier_model_version | verifier | policy/storage | yes | version |

#### Invariants

* verifier receives only LR candidate categories.
* verifier does not add new labels.
* verifier output is not action.
* timeout/failed is not allow reason.
* segment text is runtime-only.

#### Boundary rules

* no candidate category means verifier request is not created.
* each candidate category creates one request.
* `verification_context` is metadata, not additional label discovery.
* `confirmed` increases evidence confidence, but Policy Orchestrator still decides final action.
* `rejected` does not suppress confirmed lexical secret or high-risk PII span.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| no LR candidate | request skipped |
| timeout | `verifier_status='timeout'` |
| model failure | `verifier_status='failed'` |
| low confidence | `verifier_status='uncertain'` |
| queue full | timeout/failed result |
| invalid label | skipped + failure code |

#### Privacy / storage rules

저장 금지: segment text, verifier input dump, raw signal value, worker queue dump, raw protected target text, raw protected target pattern, exact size_bytes. 저장 허용: segment_id, candidate_category, verifier_status, confidence_bucket, verifier_model_version, failure code.

#### Unit tests

* `test_roberta_verifier_skips_without_lr_candidate`
* `test_roberta_verifier_does_not_add_new_label`

#### Contract tests

* `test_roberta_verifier_result_is_not_action`
* `test_verifier_timeout_is_not_allow_reason`

#### Integration tests

* `test_roberta_model_loaded_once`
* `test_verifier_queue_is_bounded`

#### Done criteria

* Verifier is candidate-gated.
* Verifier never adds labels or actions.
* Timeout/failure is structured and conservative.

---

### Module: Policy Orchestrator

#### Purpose

`Policy Orchestrator`는 parser status, lexical signals, classifier result, verifier result, source metadata를 조합해 final action, recommended_action, reason_code, severity를 확정한다.

#### Runtime position

Verifier 결과 수집 후, UserNotice/EventStorage 이전에 실행된다.

#### Upstream dependency

* `ScanStatus`
* `LexicalSignal[]`
* `SegmentSignalSet[]`
* `SegmentClassificationResult[]`
* `RobertaVerificationResult[]`
* `SourceMetadata`
* policy config

#### Downstream consumer

* UserNotice builder
* EventStorage serializer
* AnalyzeResponse builder

#### Responsibility

* final action 결정
* recommended_action 결정
* reason_code 확정
* severity 확정
* finding summary 생성
* event metadata 생성 요청
* user notice request 생성
* fallback policy 적용
* file-derived masking 금지 적용

#### Non-responsibility

* raw text 저장 금지
* parser 직접 실행 금지
* embedding/classifier/verifier 실행 금지
* classifier/verifier 학습 금지
* UI message string 직접 하드코딩 금지

#### Input schema

```text
PolicyDecisionRequest(request_id, input_id, source_metadata, scan_status, lexical_signals, segment_signal_sets, classification_results, verification_results, pipeline_failures)
```

#### Output schema

```text
PolicyDecision(request_id, input_id, action, recommended_action, reason_code, category, severity, user_notice_requests, finding_summaries, event_metadata)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| action | Policy Orchestrator | API/extension/storage | yes | final only here |
| recommended_action | Policy Orchestrator | API/extension/storage | yes | final only here |
| reason_code | Policy Orchestrator | notice/storage | yes | registry |
| severity | Policy Orchestrator | notice/storage | yes | metadata |
| finding_summaries | Policy Orchestrator | response/storage sanitized | metadata only | no raw text |
| event_metadata | Policy Orchestrator | EventStorage | allowlist | no raw content |

#### Invariants

* Only Policy Orchestrator emits final action.
* Priority is `block > mask > warn > allow`.
* verifier timeout/failed cannot justify allow.
* classifier/verifier rejected result cannot erase deterministic lexical secret evidence considered by Policy Orchestrator.
* suppressor score can reduce severity only when no Policy-confirmed lexical span evidence exists.

#### Boundary rules

* Policy-confirmed secret evidence and high-risk PII evidence are internal evidence states derived only by `Policy Orchestrator`.
* Upstream modules must not emit `confirmed_secret` or final risk confirmation fields.
* `has_deterministic_secret_signal` and `has_high_risk_pii_signal` are evidence flags, not final confirmation.
* Decision priority is `block > mask > warn > allow`.
* file-derived content must not create `masked_prompt`.

#### Failure handling

| failure case | fallback |
| --- | --- |
| classifier failed | lexical + parser status conservative decision |
| verifier timeout | LR + lexical conservative decision |
| verifier failed | LR + lexical conservative decision |
| parser timeout | warn |
| unsupported file | content_not_scanned notice |
| empty input | allow with info notice |
| policy conflict | higher priority action wins |
| reason code missing | internal unmapped fallback |

#### Privacy / storage rules

저장 금지: raw text, OCR text, normalized text, segment text, raw secret, original file name, full masked prompt. 저장 허용: action/recommended_action/reason_code/severity/category and EventMetadata allowlist.

#### Unit tests

* `test_policy_action_priority`
* `test_policy_timeout_is_not_allow_reason`

#### Contract tests

* `test_policy_orchestrator_only_module_emits_action`
* `test_policy_confirmed_secret_evidence_overrides_roberta_reject`

#### Integration tests

* `test_file_risk_does_not_generate_masked_prompt`
* `test_response_boolean_mapping_for_block_mask_warn_allow`

#### Done criteria

* Only policy emits final action.
* File-derived content never produces `masked_prompt`.
* Timeouts/failures never become allow evidence.

---

### Module: UserNotice / EventStorage

#### Purpose

이 모듈은 `PolicyDecision`을 extension/API response와 event storage가 소비할 수 있는 형태로 변환한다. Event storage는 allowlist metadata만 저장한다.

#### Runtime position

Policy Orchestrator 이후, `AnalyzeResponse` 반환 전후에 실행된다.

#### Upstream dependency

* `PolicyDecision`
* `SourceMetadata`
* `ScanStatus`
* reason code registry
* message template registry
* EventWriterPort

#### Downstream consumer

* AnalyzeResponse builder
* event database
* extension UI
* admin dashboard

#### Responsibility

* reason_code enum validation
* `UserNotice` 생성
* `EventRecord` 생성
* storage allowlist serialization
* location_hint response-only 처리
* user message template resolution
* rendered `user_message` response generation without storage
* storage failure isolation

#### Non-responsibility

* action 결정 금지
* classifier score 해석 금지
* verifier result 변경 금지
* raw text 저장 금지
* original file name 저장 금지
* rendered `user_message` 저장 금지

#### Input schema

```text
NoticeAndEventRequest(policy_decision, source_metadata, scan_status, login_id)
```

#### Output schema

```text
UserNotice, EventRecord
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| user_notice | notice builder | API/extension | template id only | rendered text not stored |
| location_hint | notice builder | API only | no | response-only |
| event_id | event serializer | response/storage | yes | generated |
| EventRecord | event serializer | storage | yes | allowlist only |
| message_template_id | notice builder | UI/storage | yes | no rendered content |

#### Invariants

* EventRecord contains no raw content.
* location_hint is runtime response only.
* reason_code must be from registry or mapped fallback.
* storage failure must not prevent analyze response.
* EventStorage stores `size_bucket`, not exact `size_bytes`.
* EventStorage stores opaque `protected_target_id`, not raw protected target text or pattern.

#### Boundary rules

* `FindingSummary` includes only `category`, `severity`, `reason_code`, response-only `location_hint`, `signal_type`, and `confidence_bucket`.
* `user_message` is derived from template, not arbitrary model text.
* Rendered `user_message` is response-only and must not be stored.
* `masked_prompt` may be returned in runtime response but must not be stored.
* Event storage cannot include full path/query.
* Event storage stores `message_template_id` and `reason_code`, not rendered `user_message`.

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| unknown reason_code | `INTERNAL_POLICY_REASON_UNMAPPED` |
| missing message template | generic template |
| event write failed | response returned, metric incremented |
| invalid location | location_hint omitted |
| storage unavailable | non-blocking storage failure metric |

#### Privacy / storage rules

저장 금지: source text, extracted text, OCR text, normalized text, segment text, raw file bytes, raw secret, original file name, full masked prompt, matched lexical value, worker queue dump, raw protected target text, raw protected target pattern, human-readable protected target canonical name, exact size_bytes. 저장 허용: EventRecord allowlist only.

#### Unit tests

* `test_reason_code_enum_validation`
* `test_event_record_message_template_id_allowlisted`

#### Contract tests

* `test_event_storage_has_no_raw_text`
* `test_event_storage_has_no_original_filename`
* `test_event_storage_has_no_full_masked_prompt`

#### Integration tests

* `test_event_write_failure_does_not_fail_analyze`
* `test_event_storage_uses_size_bucket_not_exact_size_bytes`

#### Done criteria

* Event serializer deny-by-default allowlist is enforced.
* Storage failure is isolated.
* No rendered message or masked prompt is persisted.

---

### Module: ML Dataset Build Pipeline

#### Purpose

`ML Dataset Build Pipeline`은 제품 runtime에 포함되지 않는 offline training workspace 계약이다. 이 파이프라인은 Qwen3 embedding + LR classifier와 KLUE RoBERTa verifier 학습/평가 dataset을 생성하고 model artifact replacement gate를 검증한다.

PromptGuard 제품 repository의 책임은 dataset 생성이나 학습 실행이 아니라, 외부에서 전달된 model artifact와 manifest를 intake gate로 검증한 뒤 runtime classifier/verifier가 사용할 수 있는 artifact만 load하는 것이다.

#### Runtime position

Offline build pipeline에서 실행된다. Runtime request path와 배포 server 기본 실행 경로에 포함되지 않는다.

#### Upstream dependency

Offline training workspace:

* context dataset JSONL
* verifier dataset JSONL
* label spec
* split policy
* audit rules

Product runtime / publish repository:

* model artifact files
* artifact manifest
* expected runtime contract version

#### Downstream consumer

Offline training workspace:

* LR trainer
* RoBERTa verifier trainer
* artifact registry
* model replacement gate

Product runtime / publish repository:

* LR classifier loader
* verifier loader
* analyze runtime factory

#### Responsibility

Offline training workspace responsibility:

* context_dataset build
* verifier_dataset build
* practical_dev/practical_final split 관리
* hard_eval isolation
* same template_id split lock
* shortcut/meta leakage 제거
* privacy audit
* artifact manifest 생성
* replacement gate 판단

Product runtime / publish repository responsibility:

* artifact manifest 존재 여부 검증
* artifact manifest version 검증
* artifact file 존재 여부와 load 가능성 검증
* artifact가 요구 runtime contract version과 맞는지 검증
* manifest와 artifact metadata만 사용하고 dataset 원문, hard_eval 원문, training source file을 요구하지 않는다.

#### Non-responsibility

* production action 결정 금지
* real PII 사용 금지
* real secret 사용 금지
* 실제 회사명/고객명 사용 금지
* hard_eval tuning 금지
* Product runtime에서 dataset build, train, hard_eval execution을 직접 수행하지 않는다.
* Product runtime에서 raw dataset, hard_eval source, train/dev/test 원문을 요구하거나 저장하지 않는다.

#### Input schema

```text
DatasetBuildRequest(context_dataset_paths, verifier_dataset_paths, practical_dev_paths, practical_final_paths, hard_eval_paths, label_spec_path, split_policy, output_dir)
```

Product runtime / publish repository intake input:

```text
ArtifactIntakeRequest(artifact_root, artifact_manifest_path, expected_runtime_contract_version)
```

#### Output schema

```text
DatasetBuildResult(context_train_path, context_valid_path, context_test_path, verifier_train_path, verifier_valid_path, verifier_test_path, reports, artifact_manifest_path, passed_replacement_gate, failures)
```

Product runtime / publish repository intake output:

```text
ArtifactIntakeResult(accepted, artifact_refs, manifest_version, runtime_contract_version, failures)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| template_id | dataset author | splitter/audit | yes | split lock |
| labels | dataset author | trainers/audit | yes | label spec |
| text | dataset author | offline training | dataset only | synthetic/sanitized |
| split | splitter | trainers/audit | yes | no leakage |
| passed_replacement_gate | builder | release process | yes | required |
| artifact_manifest_path | model provider | runtime loader | yes | required for runtime load |
| runtime_contract_version | model provider | runtime loader | yes | must match runtime |

#### Invariants

* same `template_id` must not cross train/valid/test.
* hard_eval must not enter train/valid/test.
* hard_eval must not tune threshold, model, policy, or architecture.
* real PII, real secret, actual customer/company names are rejected.
* category names appearing directly in text are rejected.
* Product runtime MUST NOT require raw dataset or hard_eval source files.
* Product runtime MUST reject missing or incompatible artifact manifest before model load.

#### Boundary rules

| dataset | use | tuning allowed | forbidden use |
| --- | --- | ---: | --- |
| context_dataset | Qwen3 embedding + LR training | yes | real PII, real secret, actual customer/company |
| verifier_dataset | RoBERTa verifier fine-tuning | yes | real PII, real secret, actual customer/company |
| practical_dev | threshold/model selection | yes | hard_eval contamination |
| practical_final | final held-out report | no tuning | train/dev leakage |
| hard_eval | frozen reference report | no tuning | train/dev/threshold/model selection |

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| hard_eval contamination | build fail |
| same template split leak | build fail |
| label shortcut detected | sample rejected |
| real PII suspected | sample quarantined |
| missing practical_dev report | replacement denied |
| missing practical_final report | replacement denied |
| hard_eval used for tuning | build fail |
| missing artifact manifest in product runtime | runtime load fail |
| incompatible artifact manifest version | runtime load fail |
| runtime requires raw dataset/hard_eval source | contract fail |

#### Privacy / storage rules

금지: real PII, real secret, actual company/customer names, production raw logs, production file bytes, sensitive values in model card. 허용: synthetic values, reserved IP ranges, placeholders for contracts, audit-safe generated samples, sanitized field names.

#### Unit tests

* `test_same_template_id_not_split_across_train_valid_test`
* `test_label_name_in_text_rejected`

#### Contract tests

* `test_hard_eval_not_used_for_threshold_tuning`
* `test_real_pii_secret_quarantined`

#### Integration tests

* `test_practical_reports_required_for_replacement`
* `test_artifact_manifest_required_for_runtime_load`
* `test_runtime_does_not_require_dataset_or_hard_eval_sources`
* `test_incompatible_artifact_manifest_version_rejected`

#### Done criteria

* Build rejects leakage and hard_eval tuning.
* Artifact manifest is generated.
* Replacement gate requires practical_dev and practical_final reports.
* Product runtime accepts only manifest-backed model artifacts.
* Product runtime can load classifier/verifier artifacts without dataset, training script, or hard_eval source files.

---

### Module: Worker Runtime

#### Purpose

`Worker Runtime`은 ParserWorkerPool, EmbeddingWorker, RobertaVerifierWorker, cleanup worker의 lifecycle, queue, timeout, readiness를 관리한다.

#### Runtime position

Application startup부터 shutdown까지 유지된다.

#### Upstream dependency

* runtime config
* model artifact registry
* temp file manager
* service lifecycle hooks

#### Downstream consumer

* AnalyzeService
* readiness endpoint
* observability metrics

#### Responsibility

* parser pool 관리
* Qwen3 singleton embedding worker 관리
* RoBERTa verifier worker 관리
* bounded queue 관리
* timeout/retry/backpressure 적용
* model readiness check
* graceful shutdown
* temp file cleanup

#### Non-responsibility

* classifier 학습 금지
* policy decision 직접 생성 금지
* user notice 직접 생성 금지
* raw text 저장 금지
* queue dump 생성 금지

#### Input schema

```text
WorkerRuntimeConfig(parser_pool_size, embedding_batch_size, embedding_timeout_ms, verifier_queue_size, verifier_timeout_ms, temp_file_cleanup_interval_seconds, model_preload)
```

#### Output schema

```text
WorkerRuntimeState(parser_pool_ready, embedding_worker_ready, roberta_verifier_ready, ttl_cleanup_ready, qwen_model_loaded_once, roberta_model_loaded_once, queue_backpressure_active)
```

#### Field ownership

| field | produced by | consumed by | persisted | rule |
| --- | --- | --- | ---: | --- |
| verifier_queue_size | config | runtime | yes | numeric metadata |
| timeout_ms | config | workers | yes | config metadata |
| qwen_model_loaded_once | runtime | readiness/tests | yes | lifecycle |
| roberta_model_loaded_once | runtime | readiness/tests | yes | lifecycle |
| queue payload | service | worker memory | no | critical |

#### Invariants

* Qwen3 model is not loaded per request.
* RoBERTa model is not loaded per request.
* verifier queue is bounded.
* worker queue payload is memory-only.
* queue timeout is represented as structured failure/result.

#### Boundary rules

| worker | input queue payload | output result type | timeout | retry | model lifecycle | logging forbidden | readiness | degradation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ParserWorkerPool | `ParserWorkerPayload` | `FileParserResult` | parser timeout | worker crash only | no ML model | file bytes, raw text, file name | parser workers alive | parser failure to policy |
| EmbeddingWorker | `AtomEmbeddingRequest` | `AtomEmbeddingResult` | embedding timeout | smaller batch once | Qwen3 singleton | atom text, vectors | model loaded | lexical-only fallback |
| RobertaVerifierWorker | `RobertaVerificationRequest` | `RobertaVerificationResult` | verifier timeout | no default request retry | RoBERTa singleton | segment text, queue dump | model loaded + queue accepts | LR+lexical fallback |
| TtlCleanupWorker | temp file refs | cleanup status | cleanup interval | next interval | no model | file name if raw | cleanup loop alive | next cycle retry |

#### Failure handling

| failure case | output / fallback |
| --- | --- |
| embedding queue full | backpressure, timeout if not accepted |
| verifier queue full | timeout/failed verifier result |
| parser worker crash | restart, request failure status |
| model load failure | readiness false, degraded/fail-closed by policy |
| cleanup failure | retry next interval |
| shutdown | drain or cancel with structured failure |

#### Privacy / storage rules

저장 금지: worker queue dump, raw protected target text, raw protected target pattern, human-readable protected target canonical name, exact size_bytes, raw text log, segment text log, atom text log, verifier input dump, model input dump. 저장 허용: worker readiness state, queue depth, latency bucket, failure code, model version.

#### Unit tests

* `test_qwen_model_loaded_once`
* `test_roberta_model_loaded_once`

#### Contract tests

* `test_verifier_queue_is_bounded`
* `test_worker_queue_dump_disabled`

#### Integration tests

* `test_worker_graceful_shutdown`
* `test_temp_file_cleanup_after_ttl`

#### Done criteria

* Workers expose readiness.
* Queues are bounded.
* Queue payloads are never dumped.
* Shutdown drains or cancels with structured failure.

---


## 10. 공용 타입 정의

이 섹션에는 downstream handoff 또는 cross-module response/storage에 필요한 공용 타입만 둔다. Module-local request/config 타입은 각 모듈 섹션의 Input schema 또는 config schema에만 둔다.

```python
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]

ReasonCode = Literal[
    "NO_RISK_DETECTED",
    "LEXICAL_DETERMINISTIC_SECRET_SIGNAL",
    "LEXICAL_HIGH_RISK_PII_SIGNAL",
    "PROTECTED_TARGET_STRONG_SIGNAL",
    "RISK_CONTEXT_VERIFIER_CONFIRMED",
    "RISK_CONTEXT_LR_ONLY",
    "RISK_CONTEXT_LR_ONLY_VERIFIER_TIMEOUT",
    "RISK_CONTEXT_LR_ONLY_VERIFIER_FAILED",
    "RISK_CONTEXT_VERIFIER_UNCERTAIN",
    "CONTENT_NOT_SCANNED",
    "PARSER_OR_OCR_FAILED",
    "UNSUPPORTED_FILE",
    "EMPTY_INPUT",
    "INTERNAL_POLICY_REASON_UNMAPPED",
]

ParserStatus = Literal["parsed", "partial", "failed", "unsupported", "timeout", "too_large", "encrypted"]
OcrStatus = Literal["not_applicable", "text_found", "no_text_detected", "timeout", "failed"]
ScannerStatus = Literal["not_started", "completed", "partial", "timeout", "failed"]
SizeBucket = Literal["empty", "tiny", "small", "medium", "large", "huge", "unknown"]
ExtractionRequirement = Literal[
    "wrap_text",
    "native_parse",
    "ocr_required",
    "native_parse_then_ocr_fallback",
    "metadata_only",
    "unsupported",
    "not_applicable",
]

class TextRange(BaseModel):
    start: int
    end: int

class OffsetMapping(BaseModel):
    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int

class PipelineFailure(BaseModel):
    code: str
    message: str
    retryable: bool
    module: str | None = None

class ScanStatus(BaseModel):
    parser_status: ParserStatus
    ocr_status: OcrStatus
    scanner_status: ScannerStatus = "not_started"

class FileParserResult(BaseModel):
    input_id: str
    document: ParsedDocument | None
    parser_status: ParserStatus
    ocr_status: OcrStatus
    failure: PipelineFailure | None = None

class ParsedBlock(BaseModel):
    block_id: str
    input_id: str
    text: str
    source: BlockSource
    location: BlockLocation | None
    extraction_status: ExtractionStatus

class ParsedDocument(BaseModel):
    input_id: str
    file_ref: str | None
    file_kind: FileKind | None
    parser_id: str
    parser_version: str
    parser_status: ParserStatus
    ocr_status: OcrStatus
    blocks: list[ParsedBlock]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

class NormalizedBlock(BaseModel):
    block_id: str
    original_text: str
    normalized_text: str
    offset_map: list[OffsetMapping]
    warnings: list[str] = Field(default_factory=list)

class NormalizedDocument(BaseModel):
    input_id: str
    blocks: list[NormalizedBlock]
    normalizer_version: str
    failure: PipelineFailure | None = None

class LexicalRuleSnapshot(BaseModel):
    snapshot_id: str
    scanner_version: str
    ruleset_version: str
    regex_ruleset_version: str
    keyword_ruleset_version: str
    protected_target_registry_version: str | None
    custom_regex_ruleset_version: str | None
    config_hash: str
    created_at: str

class ProtectedTargetConfig(BaseModel):
    target_id: str
    target_type: Literal["project", "customer", "system", "repo", "domain", "custom"]
    match_mode: Literal["exact", "substring", "regex", "domain", "repo"]
    encrypted_pattern_ref: str
    severity_hint: Literal["low", "medium", "high", "critical"]
    registry_version: str
    enabled: bool

class LexicalSignal(BaseModel):
    signal_id: str
    input_id: str
    block_id: str
    signal_type: Literal[
        "pii_span",
        "secret_span",
        "secret_fingerprint",
        "token_candidate",
        "protected_target_hit",
        "custom_regex_hit",
        "sensitive_value_pattern_hit",
        "context_trigger_hit",
    ]
    pattern_id: str
    match_basis: Literal[
        "deterministic_regex",
        "heuristic_regex",
        "keyword",
        "protected_target",
        "fingerprint",
        "context_trigger",
    ]
    normalized_range: TextRange
    original_range: TextRange
    severity_hint: Literal["info", "low", "medium", "high", "critical"]
    deterministic: bool
    value_fingerprint: str | None
    protected_target_hit: bool = False
    protected_target_id: str | None = None
    protected_target_type: str | None = None
    protected_target_registry_version: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

class LexicalScanResult(BaseModel):
    input_id: str
    signals: list[LexicalSignal]
    scanner_status: ScannerStatus
    scanner_version: str
    rule_snapshot: LexicalRuleSnapshot
    failure: PipelineFailure | None = None

class AnalysisAtom(BaseModel):
    atom_id: str
    input_id: str
    block_id: str
    text: str
    original_range: TextRange
    location: BlockLocation | None
    atom_type: Literal["sentence", "paragraph", "row_group", "code_block", "table_row", "ocr_line"]
    ordinal: int

class AnalysisSegment(BaseModel):
    segment_id: str
    input_id: str
    atom_ids: list[str]
    text: str
    original_range: TextRange
    locations: list[BlockLocation]
    segment_type: Literal["semantic", "structure", "size_fallback", "single_atom"]
    ordinal: int
```

Parser-specific shared types such as `ParserWorkerPayload`, `ParserExecutionPlan`, `TempFileAccessContext`, `OcrResult`, `OcrImageInput`, and `ComponentLicenseMetadata` are defined in section 7 and section 8.11. They are shared across parser worker internals but are not public API schema.

공용 타입 섹션에 두지 않는 module-local 타입:

* `AnalyzeHttpRequest`, `AnalyzeHttpResponse`
* `InputEnvelope`
* `TempUploadRequest`, `TempUploadResponse`
* `ParsedBlockBuildInput`
* `NormalizerRequest`, `NormalizationPolicy`
* `LexicalScanRequest`
* `AtomBuildRequest`, `AtomizationPolicy`
* `AtomEmbeddingRequest`
* `SegmentBuildRequest`, `SegmentPolicy`
* `SignalMappingRequest`, `SignalMappingPolicy`
* `SegmentEmbeddingBuildRequest`, `SegmentEmbeddingPolicy`
* `SegmentClassificationRequest`
* `DatasetBuildRequest`, `SplitPolicy`
* `WorkerRuntimeConfig`
* `PdfCoveragePolicy`
* adapter-local runtime configs

Boundary rules:

* public API schema, service-local schema, parser schema, ML schema, policy schema, event storage schema, response compatibility schema를 섞지 않는다.
* wrapper result type과 inner payload type을 혼용하지 않는다.
* module boundary를 넘는 dict는 typed schema 또는 allowlist serializer를 거친다.
* runtime-only text/vector/value field는 EventStorage serializer 입력으로 전달하지 않는다.

---

## 11. ProtectedTarget Registry Contract

ProtectedTarget Registry는 보호 대상 원문 또는 match pattern을 보관하는 보안 설정 저장소다.

* raw protected target pattern은 scanner 운영을 위해 registry에 저장될 수 있다.
* raw protected target pattern은 secure registry에 암호화 저장되어야 한다.
* raw protected target pattern은 일반 EventStorage에 저장하면 안 된다.
* scanner runtime은 ProtectedTarget Registry에서 target config를 읽어 matcher를 구성한다.
* raw protected target pattern은 runtime memory에서 matching을 위해 사용될 수 있다.
* raw protected target pattern은 log, worker queue dump, event storage, API response에 남기지 않는다.
* scanner 결과와 event에는 raw protected target text를 남기지 않는다.
* event에는 opaque target_id, target_type, registry_version 같은 안전한 metadata만 남긴다.
* `encrypted_pattern_ref`는 raw pattern 자체가 아니다.
* raw pattern은 secure registry/KMS/secret manager를 통해 runtime에서만 복호화되어 matcher에 사용된다.
* `canonical_id` 또는 canonical name이 사람이 읽을 수 있는 민감 이름이 될 수 있으면 EventStorage에 저장하지 않는다.

Event/storage projection에는 다음 필드만 허용한다.

```python
protected_target_hit: bool
protected_target_id: str | None
protected_target_type: str | None
protected_target_registry_version: str | None
```

## 12. Runtime / Worker 계약

| layer | allowed responsibility | forbidden responsibility |
| --- | --- | --- |
| FastAPI Route | request validation, auth context extraction, service call | pipeline execution, policy decision, raw logging |
| AnalyzeService | module orchestration, failure aggregation, response assembly | final action decision, storage raw content, concrete parser branching |
| ParserWorkerPool | queue, timeout, backpressure, worker lifecycle, crash isolation | parser plan selection, concrete parser library call, policy decision |
| FileParserRunner | parser use case orchestration inside worker runtime | queue management, concrete parser implementation, policy decision |
| ParserPlanResolver | typed execution plan creation | parsing/OCR execution, policy decision |
| ParserPlanExecutor | typed plan execution and FileParserResult aggregation | plan selection, policy decision, scanner/model calls |
| Worker Runtime | queues, timeout, readiness, singleton lifecycle | policy decision, user notice generation |
| Policy Orchestrator | final action, reason_code, severity | raw content storage, model inference |

| worker | startup | per-request | shutdown |
| --- | --- | --- | --- |
| ParserWorkerPool | pool initialized, runner wired through ports | execute parser job and return `FileParserResult` | drain/cancel active parse |
| EmbeddingWorker | Qwen3 singleton loaded | batch atom embedding | release model resources |
| RobertaVerifierWorker | RoBERTa singleton loaded | batch LR candidate pairs only | drain/cancel verifier tasks |
| TtlCleanupWorker | cleanup loop started | not request-bound | final cleanup attempt |

| queue | bounded | payload | timeout result | retry |
| --- | ---: | --- | --- | --- |
| parser queue | yes | `ParserWorkerPayload` without raw bytes | `PARSER_TIMEOUT` | worker crash only |
| embedding queue | yes | `AtomEmbeddingRequest` without persisted text dump | `EMBEDDING_TIMEOUT` | smaller batch once |
| verifier queue | yes | `RobertaVerificationRequest` for LR candidate pairs only | `verifier_status="timeout"` | no default retry |
| cleanup queue | yes | file_ref cleanup item | cleanup metric | next interval |

Composition root must wire concrete implementations. Runtime workers and services receive ports/interfaces through constructor or dependency injection. Concrete OCR/parser/model/storage implementations must not be instantiated inside Route, AnalyzeService, Policy Orchestrator, or test fixtures except composition root and integration profiles.

---

## 13. Policy / Masking Contract

* file-derived content에는 `masked_prompt`를 생성하지 않는다.
* OCR/PDF/parsed file content를 reconstructed masked prompt로 만들지 않는다.
* composer text와 converted paste text만 `masked_prompt` 대상이 될 수 있다.
* file_reference input에서 발견된 risk는 policy에 따라 block 또는 warn으로 처리한다.
* composer risk와 file risk가 함께 있으면 top-level action은 `block > mask > warn > allow` 우선순위를 따른다.
* parser/OCR failure는 allow 근거가 아니다.
* unsupported/content unavailable attachment는 `CONTENT_NOT_SCANNED` evidence로 policy에 전달한다.
* Policy Orchestrator만 final action을 결정한다.
* Policy Orchestrator는 parser/OCR status, lexical signals, classifier result, verifier result, source metadata, pipeline failures를 조합해 decision을 만든다.

### 13.1 Action priority

```text
block > mask > warn > allow
```

### 13.2 Decision rules

| rule | decision |
| --- | --- |
| Policy-confirmed secret evidence in file | block |
| Policy-confirmed secret evidence in composer | mask |
| Policy-confirmed high-risk PII evidence in file | block |
| Policy-confirmed high-risk PII evidence in composer | mask |
| Parser/OCR failure | warn |
| Unsupported file | warn with content_not_scanned notice |
| Empty input | allow with info notice |
| RoBERTa confirmed high-risk context | higher confidence than LR-only |
| RoBERTa rejected + Policy-confirmed secret evidence | secret evidence remains |
| RoBERTa rejected + Policy-confirmed high-risk PII evidence | PII evidence remains |
| RoBERTa rejected + protected target + strong signal | strong evidence remains |
| verifier timeout/failed | LR + lexical conservative decision |
| all segments no-risk and no strong lexical signal | allow |
| suppressor score with no Policy-confirmed lexical span evidence | may lower severity |

### 13.3 Action별 response boolean 규칙

| action | allow_original_send | requires_user_confirmation | behavior |
| --- | ---: | ---: | --- |
| block | false | false | 원본 전송 불가, 사용자 확인으로도 우회 불가 |
| mask | false | true | 사용자는 마스킹 결과를 확인하고, 마스킹된 프롬프트만 전송 |
| warn | true | true | 경고 후 사용자가 원본 전송 가능 |
| allow | true | false | 바로 원본 전송 가능 |

추가 규칙:

* `action="mask"`인 composer input은 `masked_prompt`가 있어야 한다.
* extension은 `action="mask"`일 때 원본 text가 아니라 `masked_prompt`를 전송해야 한다.
* file-only input에서는 `masked_prompt`를 생성하지 않는다.
* `action="block"`은 원본 전송과 마스킹본 전송 모두 기본적으로 차단한다.

## 14. Privacy / Storage Contract

### 14.1 Storage denied

* raw prompt text
* raw file bytes
* base64 file payload
* temporary file content
* `file_ref` in EventStorage
* temporary file path
* rendered image path
* extension-side extracted file text
* parsed file content
* extracted text
* OCR text
* OCR input image dump
* parser input dump
* normalized text
* normalized excerpt
* atom text
* segment text
* raw matched value
* detected raw value
* secret value
* original file name
* original filename-derived display name
* document title
* document author
* spreadsheet sheet name if user-provided
* exact OCR confidence
* OCR bounding text excerpt
* full masked prompt
* reconstructed file-derived masked prompt
* embedding vector
* segment vector
* exact classifier score
* raw category_scores
* raw suppressor_scores
* verifier raw logits
* verifier input dump
* exact size_bytes
* worker queue dump
* raw protected target text
* raw protected target pattern
* human-readable protected target canonical name
* full URL path/query
* raw exception message that may contain any denied value

### 14.2 Storage allowed

* event_id
* request_id
* input_id
* login_id
* action
* recommended_action
* reason_code
* category
* severity
* input_kind
* source
* file_kind
* file_type
* extension suffix hint
* MIME hint
* size_bucket
* parser_id
* parser_version
* parser_plan_kind bucket
* extraction_method
* parser_status
* ocr_status
* location_kind
* warning code
* failure code
* cleanup status metric
* signal_type
* pattern_id
* severity_hint
* confidence_bucket
* score_bucket
* model_version
* message_template_id
* created_at
* component_name
* component_version
* license_id
* engine_id
* model_id
* latency_bucket

### 14.3 Serialization rule

Any field not present in the allowlist is denied by default. Adding a persisted field requires schema migration, privacy review, integration fixture, and storage allowlist update. `metadata: dict[str, JsonValue]` is allowlist-only in every schema. Rendered `user_message` is never stored; storage keeps `message_template_id` and `reason_code` only. Raw classifier scores, raw logits, embedding vectors, and segment vectors are runtime-only; storage may keep buckets and version metadata only. `LocationHint` is response-only; EventRecord stores `location_kind` only. EventStorage does not store exact `size_bytes`; file size is stored as `size_bucket` only. `PrivacyAllowlistSerializer` is the only path into EventStorage, and contract tests must fail if a non-allowlisted field is serialized.

---

## 15. SOLID / TDD / Clean Code Implementation Contract

### 15.1 SRP

각 module은 하나의 변경 이유만 가져야 한다.

* Route는 request validation, auth context extraction, AnalyzeService 호출만 담당한다.
* AnalyzeService는 pipeline orchestration과 failure aggregation만 담당한다.
* ParserWorkerPool은 worker dispatch, timeout, backpressure, lifecycle, structured failure boundary만 담당한다.
* FileParserRunner는 parser use case orchestration만 담당한다.
* ParserPlanResolver는 typed parser execution plan creation만 담당한다.
* ParserPlanExecutor는 typed plan execution과 `FileParserResult` aggregation만 담당한다.
* ParserAdapter는 특정 file type 또는 extraction method의 parsing/extraction만 담당한다.
* OcrEnginePort 구현체는 OCR recognition만 담당한다.
* Policy Orchestrator만 final action, reason_code, severity를 결정한다.
* Event serializer는 allowlist projection만 담당한다.

금지한다.

* Route에서 parser/scanner/model/policy 직접 호출
* AnalyzeService에서 final action 결정
* AnalyzeService에서 file type별 concrete parser branching 수행
* ParserWorkerPool에서 adapter selection 또는 parser library 호출
* FileParserRunner에서 concrete parser library 또는 OCR engine 직접 import
* ParserPlanResolver에서 parsing/OCR 수행
* ParserPlanExecutor에서 policy decision 생성
* ParserAdapter에서 scanner, normalizer, classifier, verifier, policy 호출
* OCR engine에서 policy decision 생성
* Event serializer에서 action 결정

### 15.2 OCP

새 file type, 새 parser, 새 OCR provider는 기존 orchestration 코드를 수정하지 않고 adapter/port 등록과 plan resolver config로 확장되어야 한다.

금지한다.

* AnalyzeService에 `if file_kind == "pdf"` 같은 concrete parser logic 추가
* ParserWorkerPool에 특정 parser library 호출을 직접 하드코딩
* FileParserRunner에 concrete OCR provider import 추가
* 새 parser 추가를 위해 public API schema를 변경하는 구조
* OCR provider 교체를 위해 PDF parser core logic을 수정해야 하는 구조

### 15.3 LSP

모든 ParserAdapter는 같은 input/output contract를 만족해야 한다.

* 입력: `ParserWorkerPayload`, `ResolvedTemporaryFile | None`, `ParserLimits`
* 출력: `FileParserResult`
* 실패: structured `PipelineFailure`
* unsupported: `FileParserResult(document=None, parser_status="unsupported")`
* partial: available `ParsedBlock[]` + `parser_status="partial"`

### 15.4 ISP

module이 필요하지 않은 schema나 port에 의존하지 않도록 interface를 분리한다.

반드시 분리한다.

* public API schema
* service-local `InputEnvelope`
* parser schema
* OCR schema
* ML schema
* policy schema
* event storage schema
* response compatibility schema

금지한다.

* Parser module이 HTTP request schema import
* ML module이 API response schema import
* Event serializer가 `ParsedBlock.text`에 접근
* Policy Orchestrator가 concrete parser class에 의존
* Extension이 parser/OCR schema에 의존

### 15.5 DIP

상위 orchestration module은 concrete implementation이 아니라 port/interface에 의존해야 한다.

Required ports:

```text
TemporaryFileStorePort
TemporaryFileResolverPort
FileParserRunnerPort
ParserPlanResolverPort
ParserPlanExecutorPort
ParserAdapter
OcrEnginePort
PdfRendererPort
EmbeddingModelPort
VerifierModelPort
ClassifierArtifactRegistry
EventWriterPort
Clock
IdGenerator
PolicyConfigProvider
PrivacyAllowlistSerializer
LicensePolicyProvider
```

금지한다.

* AnalyzeService가 concrete parser class를 직접 생성
* ParserAdapter가 concrete storage implementation에 직접 의존
* Policy Orchestrator가 concrete DB writer를 직접 호출
* 테스트가 real OCR engine, real model, real storage에만 의존

### 15.6 TDD rule

각 구현 PR은 다음 순서를 따른다.

```text
Red: 실패하는 unit/contract/privacy/license/compatibility test를 먼저 추가한다.
Green: 테스트를 통과하는 최소 구현만 작성한다.
Refactor: public behavior를 바꾸지 않고 SOLID 경계를 정리한다.
Regression: privacy denylist, license policy, response compatibility, storage allowlist, pipeline order test를 재실행한다.
```

각 PR은 다음 evidence를 남긴다.

* Red 단계에서 실패한 테스트 이름
* Green 단계에서 통과한 최소 구현 범위
* Refactor 단계에서 변경한 dependency direction
* Regression 단계에서 통과한 privacy/API/storage/license test 목록
* 새로 추가한 public schema field 여부
* persisted field 추가 여부
* raw content persistence risk check result
* OCR/parser dependency license scan result
* model weight license scan result
* required license scan artifact path
* parser/OCR performance budget test result
* static quality gate result

Merge 금지 조건:

* contract test 실패
* privacy denylist test 실패
* license policy test 실패
* response compatibility snapshot 실패
* parser/OCR failure message에 raw content, file path, original file name 포함
* worker queue dump 또는 raw content log 발견
* ParserAdapter가 scanner/policy/model을 import
* Route가 parser/scanner/model/policy를 import
* AnalyzeService가 final action 결정
* Policy Orchestrator 외 module이 action/reason_code 확정
* EventStorage allowlist 밖 field serialization
* default OCR/parser dependency tree에 GPL/LGPL/AGPL/SSPL/commercial-only/unclear model license 포함
* required license scan artifact 누락
* PyMuPDF, MuPDF, Ghostscript, Poppler, pdf2image import 또는 subprocess invocation 발견
* parser/OCR performance regression test 실패
* static quality gate 실패
* public required field 추가인데 schema version bump 없음

### 15.7 Static quality gates

OCR/parser 구현 PR은 다음 static quality gate를 통과해야 한다.

```text
ruff lint
mypy or pyright type check
import-linter dependency boundary check
radon complexity check for parser/OCR modules
pytest contract/privacy/license/performance suite
```

규칙:

* `parser -> api route` import는 금지한다.
* `parser -> scanner` import는 금지한다.
* `parser -> policy` import는 금지한다.
* `ml -> api response` import는 금지한다.
* `event storage -> ParsedBlock.text` 접근은 금지한다.
* `extension -> parser/OCR schema` 의존은 금지한다.
* parser/OCR module의 function complexity가 threshold를 초과하면 refactor 없이는 merge할 수 없다.
* public behavior 변경 없이 helper extraction, strategy object, adapter decomposition으로 complexity를 낮춘다.
* static quality gate 실패는 merge 금지 조건이다.
* import-linter rule은 dependency direction contract와 동일한 single source of truth를 사용한다.
* radon threshold는 parser/OCR module에 대해 CI에서 강제한다.

### 15.8 Clean Code naming

* type 이름은 역할을 드러내야 한다.
* 같은 개념에 여러 이름을 만들지 않는다.
* `file_ref`, `input_id`, `block_id`, `segment_id`, `signal_id`의 의미를 혼용하지 않는다.
* `content`, `text`, `raw_text`, `parsed_text`, `ocr_text`, `normalized_text`를 섞어 쓰지 않는다.
* storage에 남길 수 없는 runtime-only field는 이름과 주석에 명시한다.

금지 예시:

```text
data
payload2
result_obj
final_result가 여러 단계에서 다른 의미로 쓰이는 것
content가 file bytes와 text를 동시에 의미하는 것
fallback order처럼 서로 다른 fallback 의미를 섞는 표현
```

### 15.9 Clean Code function responsibility

* 한 함수는 하나의 판단 또는 하나의 변환만 수행한다.
* parsing, normalization, scanning, policy decision을 한 함수에 섞지 않는다.
* 50 lines를 초과하는 function은 helper extraction 또는 object decomposition을 검토한다.
* 중첩 조건이 3단계 이상이면 guard clause 또는 strategy로 분리한다.
* file type별 branching은 ParserPlanResolver 또는 ParserAdapter로 이동한다.

### 15.10 Clean Code data model discipline

* dict soup를 금지한다.
* module boundary를 넘는 값은 typed schema를 사용한다.
* `metadata: dict`는 allowlist serializer를 거친 값만 허용한다.
* runtime-only text/vector/value field는 EventStorage serializer 입력으로 전달하지 않는다.
* wrapper result type과 inner payload type을 혼용하지 않는다.
* `ParserWorkerPayload`와 `ParserExecutionPlan`을 혼용하지 않는다.

### 15.11 Clean Code error handling

* parser/OCR/model failure는 raw exception message를 그대로 노출하지 않는다.
* failure는 `PipelineFailure(code, message, retryable, module)` 형태로 구조화한다.
* `message`에는 raw prompt, extracted text, OCR text, original file name, file path, matched value를 넣지 않는다.
* timeout/failure는 allow 근거가 아니다.
* partial success는 available output과 failure code를 함께 반환한다.

### 15.12 Dependency direction

허용 방향:

```text
api route
→ AnalyzeService
→ ports/interfaces
→ worker/parser/model/policy implementations
```

금지 방향:

```text
parser → api route
ml → api response
event storage → parser text
scanner → policy decision
parser → scanner
parser → policy
extension → parser/OCR
```

Concrete binding은 composition root에서만 수행한다. Composition root는 app startup 또는 dependency provider module에 둔다. Route, AnalyzeService, Policy Orchestrator, ParserWorkerPool, FileParserRunner는 concrete implementation을 직접 생성하지 않는다.

### 15.13 Testability

* 모든 외부 dependency는 port 또는 interface로 mock 가능해야 한다.
* OCR engine, temp storage, parser plan resolver, parser plan executor, model worker, event writer는 test double을 사용할 수 있어야 한다.
* unit test는 real file system, real OCR, real model, real storage에 의존하지 않는다.
* contract test는 fake/test double로 boundary behavior를 검증한다.
* integration/performance test만 fixture file과 real dependency를 사용할 수 있다.
* fixture file에도 실제 PII, real secret, 실제 고객명/회사명을 넣지 않는다.

### 15.14 Duplication control

* parser failure code는 중앙 registry를 사용한다.
* reason_code는 policy reason registry를 사용한다.
* storage allowlist는 단일 source of truth를 사용한다.
* response compatibility field는 단일 adapter에서 관리한다.
* file_kind/extraction_requirement to plan_kind mapping은 ParserPlanResolver config table에만 둔다.
* license policy는 단일 `LicensePolicyProvider`에서 관리한다.

### 15.15 Static quality tool ownership

Clean Code 규칙은 CI에서 실행 가능한 static quality gate로 연결되어야 한다.

규칙:

* formatting/lint는 `ruff`가 담당한다.
* type boundary 검사는 `mypy` 또는 `pyright`가 담당한다.
* dependency direction 검사는 `import-linter`가 담당한다.
* parser/OCR module complexity 검사는 `radon`이 담당한다.
* static quality config는 repository에 versioned file로 저장한다.
* static quality rule 우회는 merge gate에서 허용하지 않는다.

### 15.16 Repository Architecture / Composition Root

목표 구조:

```text
apps/api/app/
  interfaces/http/          # FastAPI routes, request/response adapter only
  application/analyze/      # AnalyzeService, use case orchestration, service-local InputEnvelope
  domain/                   # policy, scanner contracts, parser/ML shared domain types without FastAPI/DB imports
  infrastructure/           # DB, temp storage, parser adapters, OCR engines, model runtime adapters
  runtime/                  # worker pools, queue/lifecycle/readiness wiring
  composition_root/         # concrete dependency binding and app startup wiring
  privacy/                  # allowlist serializer, denylist tests
  tests/
    unit/
    contract/
    integration/
    privacy/
    performance/
```

현재 `apps/api/app/routes`, `services`, `detectors`, `atoms`, `segmenter`, `models` 중심 구조는 route, service, DB model, detector, ML-ish component가 기술 축과 도메인 축으로 혼재될 수 있다. 기존 public API와 pipeline order를 유지하면서 다음 원칙으로 이관한다.

* 기능 변경 PR과 구조 이관 PR을 섞지 않는다.
* 먼저 import boundary tests와 composition root skeleton을 추가한다.
* 기존 module은 compatibility shim으로 남기고 새 package로 내부 이동한다.
* public route path, response schema, DB migration behavior는 migration PR에서 변경하지 않는다.
* rollback은 shim import를 기존 module로 되돌리는 방식으로 가능해야 한다.
* 구조 이관 중 privacy/storage allowlist와 response compatibility snapshot을 매 PR 실행한다.

---

## 16. API Response Compatibility Contract

### 16.1 Compatibility fields

```text
event_id
request_id
action
user_message
allow_original_send
requires_user_confirmation
masked_prompt
input_results
scan_status
findings
recommended_action
reason_code
location_hint
user_notices
```

### 16.2 Field compatibility table

| field | owner | produced by | consumed by | backward compatibility rule | privacy note |
| --- | --- | --- | --- | --- | --- |
| event_id | Backend A | Event serializer | extension/admin logs | required stable string | no raw content |
| request_id | Route | route/client | extension/logs | required stable string | no raw content |
| action | Runtime/Policy C | Policy Orchestrator | extension | enum cannot remove existing values | metadata only |
| user_message | Backend A | notice template renderer | extension UI | string remains present | response-only; never stored; must not include raw sensitive value |
| allow_original_send | Runtime/Policy C | Policy Orchestrator | extension | boolean required | no raw content |
| requires_user_confirmation | Runtime/Policy C | Policy Orchestrator | extension | boolean required | no raw content |
| masked_prompt | Runtime/Policy C | Policy runtime response | extension composer | nullable; storage forbidden | runtime response only, never EventStorage |
| input_results | AnalyzeService | service aggregation | extension UI | list required | no raw text |
| scan_status | Backend A | parser/scanner/service | extension UI | object required | status only |
| findings | Runtime/Policy C | Policy Orchestrator | extension UI | list required | sanitized summaries only |
| recommended_action | Runtime/Policy C | Policy Orchestrator | extension | enum stable | metadata only |
| reason_code | Runtime/Policy C | Policy Orchestrator | extension/storage | enum add-only unless version bump | no raw content |
| location_hint | Backend A | notice builder | extension UI | nullable | response-only; EventRecord stores location_kind only |
| user_notices | Backend A | notice builder | extension UI | list required | template-derived text only |

### 16.3 `masked_prompt` rule

* `masked_prompt` may be returned in runtime response when composer masking is required.
* `masked_prompt` must not be stored in EventStorage.
* `masked_prompt` must not be logged.
* file-derived content must not be reconstructed into `masked_prompt`.
* response serializer must drop `masked_prompt` for file-only input unless composer replacement is explicitly required.
* `action="mask"`인 composer input은 `masked_prompt`가 있어야 한다.
* extension은 `action="mask"`일 때 원본 text가 아니라 `masked_prompt`를 전송해야 한다.


## 17. Dataset / Model Artifact Contract

이 장의 dataset/training 항목은 offline training workspace 계약이다. Product runtime과 publish repository는 dataset 생성, training 실행, hard_eval 실행을 맡지 않는다. Product runtime과 publish repository의 필수 책임은 외부 model provider가 전달한 artifact manifest와 model artifact를 검증하고, runtime contract version에 맞는 artifact만 load하는 것이다.

### 17.1 Dataset 종류

| dataset | 사용처 | tuning 사용 여부 | 금지 사항 |
| --- | --- | ---: | --- |
| context_dataset | Qwen3 embedding + LR 학습 | yes | real PII, real secret, actual customer/company |
| verifier_dataset | RoBERTa verifier fine-tuning | yes | real PII, real secret, actual customer/company |
| practical_dev | threshold/model selection | yes | hard_eval contamination |
| practical_final | final held-out report | no tuning | train/dev leakage |
| hard_eval | frozen reference report | no tuning | train/dev/threshold/model selection 사용 금지 |

### 17.2 Split 규칙

1. 같은 `template_id`는 같은 split에만 들어간다.
2. `hard_eval`은 train/valid/test에 들어가지 않는다.
3. label 이름이 text에 직접 드러나는 sample은 제거한다.
4. placeholder만 반복되는 sample은 제거한다.
5. real PII, real secret, 실제 회사명, 실제 고객명은 사용하지 않는다.
6. eval set을 보고 train set을 직접 맞추는 방식은 금지한다.
7. suppressor label은 risk label false positive 감소와 slice audit에 사용한다.
8. risk label과 suppressor label이 함께 필요한 row는 실제 의미가 동시에 성립할 때만 허용한다.

### 17.3 ML 학습 계약

| item | contract |
| --- | --- |
| embedding model | `Qwen/Qwen3-Embedding-0.6B`, frozen |
| first-stage classifier | One-vs-Rest Logistic Regression |
| trainable target | LR classifier only for first stage |
| threshold source | practical validation set |
| hard_eval | threshold/model/policy selection 금지 |
| verifier model | KLUE RoBERTa label-aware binary verifier |
| verifier trainable target | LR candidate segment-label pair에 대한 label-aware binary verifier |
| verifier scope | LR candidate segment-label pairs only |
| verifier miss recovery | 금지 |
| verifier output | confirm/reject/uncertain/timeout/failed |
| final action | Policy Orchestrator only |

### 17.4 Verifier dataset 필수 slice

| slice | purpose |
| --- | --- |
| clear risk positive | confirm true risk candidate |
| clear benign | reject benign candidate |
| false positive correction | LR overfire correction |
| false negative correction | candidate distribution calibration |
| hard negative | suppressor/risk-looking safe cases |
| near-threshold | borderline LR score cases |
| suppressor conflict | risk/suppressor conflict cases |
| protected target benign | protected target mention without risk |
| protected target risky | protected target with risk context |
| PII format benign | format/example no person-level data |
| PII risky context | person-level data handling |
| public code benign | open technical explanation |
| proprietary/security-sensitive code | internal implementation/control context |

### 17.5 Artifact 경로

```text
models/
  context_with_<prefix>_classifier.joblib
  context_with_<prefix>_thresholds.json
  context_with_<prefix>_label_map.json
  context_verifier_klue_roberta_<prefix>/
  practical_dev_report.json
  practical_final_report.json
  hard_eval_reference_report.json
```

### 17.6 Product runtime artifact intake 계약

Product runtime은 `models/manifest` 또는 동등한 runtime artifact manifest를 기준으로 model artifact를 검증한다.

| item | product runtime contract |
| --- | --- |
| dataset source files | runtime에서 요구하지 않음 |
| training scripts | runtime에서 요구하지 않음 |
| hard_eval source files | runtime에서 요구하지 않음 |
| artifact manifest | runtime load 전 필수 |
| manifest version | 호환 version만 허용 |
| runtime contract version | classifier/verifier runtime 계약과 일치해야 함 |
| model files | manifest에 선언된 파일만 load |
| replacement decision | manifest와 offline report provenance를 기준으로 판단 |
| raw dataset/example content | runtime 저장/로그/응답 금지 |

Product runtime 테스트는 dataset build의 내부 품질을 재검증하지 않는다. 대신 다음 경계를 검증한다.

* manifest가 없으면 model load가 실패한다.
* manifest version이 runtime과 맞지 않으면 model load가 실패한다.
* manifest에 없는 artifact file은 load하지 않는다.
* dataset, train script, hard_eval source file이 없어도 manifest와 model artifact만 있으면 runtime classifier/verifier 조립 경로가 동작한다.
* runtime load와 analyze response는 raw dataset/example content를 저장하거나 노출하지 않는다.

## 18. Integration Test Gate

### 18.1 Extension / upload tests

* `test_extension_does_not_read_file_content`
* `test_extension_does_not_perform_ocr`
* `test_extension_never_sends_base64_file_payload`
* `test_extension_never_uses_kind_text_source_file`
* `test_upload_flow_returns_opaque_file_ref`
* `test_file_ref_has_ttl_and_access_scope`
* `test_upload_endpoint_rejects_original_filename_downstream`

### 18.2 Analyze request validation tests

* `test_analyze_input_rejects_text_source_file`
* `test_analyze_input_rejects_file_reference_with_content`
* `test_analyze_input_rejects_content_included_true_for_file_reference`
* `test_analyze_input_requires_content_unavailable_reason_for_unsupported_attachment`
* `test_file_kind_none_only_for_text_input`
* `test_file_kind_unknown_for_unknown_file`
* `test_file_ref_must_be_opaque`
* `test_schema_version_v3_is_public_api_compatibility_version`

### 18.3 License tests

* `test_parser_ocr_dependency_license_artifacts_exist`
* `test_dependency_tree_has_no_gpl_lgpl_agpl_sspl_default_path`
* `test_ocr_model_weights_require_license_artifact`
* `test_paddleocr_model_weight_license_is_allowed`
* `test_forbidden_pdf_stack_not_imported`
* `test_cloud_ocr_default_path_forbidden`

### 18.4 SOLID boundary tests

* `test_route_only_validates_and_calls_analyze_service`
* `test_route_does_not_import_parser_scanner_model_policy`
* `test_analyze_service_does_not_decide_action`
* `test_analyze_service_does_not_create_concrete_extraction_plan`
* `test_input_envelope_is_service_local_only`
* `test_policy_orchestrator_only_module_emits_action`
* `test_composition_root_is_only_concrete_binding_owner`

### 18.5 Parser/OCR contract tests

* `test_parser_worker_payload_contains_coarse_extraction_requirement_only`
* `test_file_parser_runner_invokes_plan_resolver`
* `test_parser_plan_resolver_returns_typed_execution_plan`
* `test_parser_execution_plan_steps_are_ordered_and_deterministic`
* `test_parser_execution_plan_separates_steps_and_fallback_rules`
* `test_parser_plan_executor_runs_steps_in_order`
* `test_parser_plan_executor_applies_fallback_rules_only_on_defined_triggers`
* `test_parser_worker_pool_does_not_select_adapter_directly`
* `test_parser_worker_pool_does_not_import_concrete_parser_libraries`
* `test_unsupported_and_metadata_only_are_distinct`
* `test_parser_plan_executor_does_not_emit_policy_decision`
* `test_temp_file_resolver_uses_access_context_not_owner_id`
* `test_temp_file_resolver_used_only_inside_parser_worker_runtime`
* `test_all_parser_adapters_return_file_parser_result`
* `test_parser_failure_message_has_no_raw_content`

### 18.6 PDF/OCR fallback tests

* `test_pdf_page_with_native_extraction_failure_becomes_ocr_candidate`
* `test_pdf_page_below_very_low_meaningful_chars_becomes_ocr_candidate`
* `test_pdf_page_below_low_threshold_with_image_evidence_becomes_ocr_candidate`
* `test_pdf_page_below_low_threshold_with_unknown_image_evidence_becomes_ocr_candidate`
* `test_pdf_page_below_low_threshold_without_image_evidence_skips_ocr`
* `test_pdf_page_above_low_threshold_skips_ocr`
* `test_low_native_text_page_ratio_is_metadata_not_ocr_expansion_gate`
* `test_pdf_ocr_candidates_respect_max_ocr_pages`
* `test_paddleocr_is_used_only_for_text_detection_and_recognition`
* `test_paddleocr_document_parser_features_are_forbidden`
* `test_tesseract_fallback_only_on_defined_triggers`

### 18.7 Privacy tests

* `test_event_storage_has_no_raw_text`
* `test_event_storage_has_no_normalized_text`
* `test_event_storage_has_no_atom_or_segment_text`
* `test_event_storage_has_no_embedding_or_segment_vector`
* `test_event_storage_has_no_exact_classifier_score_or_verifier_logits`
* `test_event_storage_has_no_original_filename`
* `test_event_storage_has_no_file_ref`
* `test_logs_do_not_include_raw_exception_message`
* `test_privacy_allowlist_serializer_denies_unknown_field`

### 18.8 Policy / response tests

* `test_parser_ocr_failure_is_not_allow_reason`
* `test_roberta_verifier_does_not_add_new_label`
* `test_roberta_timeout_keeps_conservative_policy_path`
* `test_lr_classifier_does_not_emit_action`
* `test_extension_required_fields_remain_present`
* `test_file_derived_content_has_no_masked_prompt`
* `test_masked_prompt_only_for_composer_or_converted_paste`

### 18.9 Dataset/model tests

* `test_hard_eval_not_used_for_threshold_tuning`
* `test_qwen3_embedding_model_is_frozen_runtime`
* `test_lr_candidate_segment_label_pairs_only_feed_verifier`
* `test_model_artifact_manifest_version_required`

### 18.10 Performance regression tests

* `test_parser_ocr_performance_budget_fixture_passes`
* `test_performance_output_has_no_raw_text_or_path`
* `test_real_ocr_only_runs_in_integration_or_performance_profile`

### 18.11 Static quality gate tests

* `test_import_linter_dependency_direction_rules`
* `test_radon_parser_ocr_complexity_threshold`
* `test_ruff_and_typecheck_pass`
* `test_static_quality_config_is_versioned`

---

## 19. PR Implementation Plan

각 PR은 독립적으로 reviewable, testable, rollbackable해야 한다. 기능 변경과 구조 이관은 같은 PR에 섞지 않는다.

### 19.1 Architecture migration PR sequence

| PR | title | goal | expected modules | forbidden changes | merge gate |
| ---: | --- | --- | --- | --- | --- |
| A1 | API architecture boundary skeleton | composition root, ports/interfaces, import-linter config를 추가한다. | `interfaces/http`, `application/analyze`, `domain`, `infrastructure`, `runtime`, `composition_root`, `tests/contract/architecture` | public route/response/DB behavior 변경 | import-linter rule pass, existing tests pass |
| A2 | Analyze route thin adapter | route에서 pipeline/business logic을 제거하고 AnalyzeService port 호출로 이동할 준비를 한다. | `routes/analyze.py`, `interfaces/http/analyze.py`, compatibility adapter | action semantics 변경, response field 제거 | response snapshot pass |
| A3 | AnalyzeService orchestration shell | service-local `InputEnvelope`, pipeline order contract test, fake module ports를 추가한다. | `application/analyze/service.py`, `application/analyze/input_normalizer.py` | real parser/model 도입, final action 결정 | `test_analyze_service_runs_modules_in_contract_order` |
| A4 | Privacy serializer single owner | EventStorage allowlist serializer와 deny-by-default test를 고정한다. | `privacy/`, `events/`, DB event writer adapter | raw field 저장, schema incompatible removal | privacy denylist suite pass |

### 19.2 Full implementation PR plan

| PR | title | goal | contract sections covered | expected files/modules | forbidden changes | tests to add/update | merge gate | dependency |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Shared schemas, ports, fixtures | 공용 schema, service-local schema, parser/ML/policy ports, synthetic fixtures, architecture tests를 먼저 고정한다. | 4, 5, 7, 10, 15, 18 | `domain/types`, `application/analyze`, `ports`, `tests/contract`, `tests/fixtures` | real OCR/model/storage 의존, public required field 추가 | schema invariant tests, import boundary tests | all schema/contract tests pass | none |
| 2 | Analyze request compatibility adapter | `inputs[]` target schema와 legacy adapter를 정합화한다. | 4, 16, 20 | `interfaces/http/analyze_request.py`, `routes/analyze.py` | `schema_version` 변경, text source file 생성 | request validation tests, response snapshot | extension compatibility pass | PR1 |
| 3 | Upload/temp file boundary | opaque `file_ref`, encrypted temp storage port, access context, cleanup hooks를 추가한다. | 6, 8.9, 12, 14 | `infrastructure/temp_storage`, `application/upload`, `runtime/cleanup` | original filename propagation, EventStorage file_ref 저장 | temp scope/TTL/privacy tests | temp privacy + cleanup tests pass | PR1 |
| 4 | Parser worker payload and runner skeleton | ParserWorkerPayload coarse requirement, ParserWorkerPool, FileParserRunner fake implementation을 추가한다. | 5, 7, 9 ParserWorkerPool/FileParserRunner, 12 | `runtime/parser_worker.py`, `application/parser/runner.py` | concrete parser libs, adapter selection in pool | parser worker boundary tests | no concrete parser imports in pool | PR1, PR3 |
| 5 | Parser plan resolver/executor | typed `ParserExecutionPlan`, `steps[]`, `fallback_rules[]`, resolver/executor fake adapters를 구현한다. | 7, 8.8, 9 ParserPlanResolver/Executor, 15 | `application/parser/planning.py`, `application/parser/executor.py` | fallback order string, policy decision | plan determinism/fallback tests | plan contract tests pass | PR4 |
| 6 | Parser adapter base and text/plain/code | base adapter contract, text wrapper, plain text, code parser를 구현한다. | 8.4, 8.7, 8.14 | `infrastructure/parser/adapters/text.py`, `code.py` | scanner/model/policy import | adapter result/privacy tests | adapter contract pass | PR5 |
| 7 | Office/spreadsheet/slide parsers | `.docx`, `.xlsx`, `.csv`, `.pptx` 기본 parser를 추가한다. | 8.4, 8.14, 14 | `infrastructure/parser/adapters/office.py`, `spreadsheet.py`, `slide.py` | legacy binary Office converter, original filename metadata | fixture parser tests | license + privacy tests pass | PR6 |
| 8 | PDF native parser and page coverage | pypdf native extraction과 page-level coverage evaluator를 구현한다. | 8.2, 8.13 | `infrastructure/parser/adapters/pdf_native.py`, `domain/parser/pdf_coverage.py` | document-level OCR expansion | PDF coverage tests | page-level tests pass | PR5 |
| 9 | OCR ports and fake OCR integration | OcrEnginePort, renderer port, fake OCR result integration을 추가한다. | 8.10, 8.11, 8.13 | `ports/ocr.py`, `ports/pdf_renderer.py`, fake adapters | real Paddle/Tesseract dependency | fake OCR contract tests | no real dependency required | PR8 |
| 10 | Real OCR dependency gate | PaddleOCR/Tesseract/pypdfium2 default integration을 license artifacts와 함께 추가한다. | 8.1-8.6, 8.10-8.13 | `infrastructure/ocr`, `third_party/licenses`, lockfile | artifact 없는 dependency, forbidden PDF stack, cloud OCR | license/SBOM/model weight tests | license artifacts + lockfile updated | PR9 |
| 11 | Parser/OCR performance profile | parser/OCR performance budget profile과 sanitized output을 추가한다. | 8.12, 18.10 | `tests/performance/parser_ocr` | real OCR in unit tests | performance budget tests | performance profile pass | PR10 |
| 12 | Normalizer and lexical scanner | offset mapping, normalized scan, no raw matched value scanner를 구현한다. | 2, 9 normalizer/scanner, 11, 14 | `domain/normalization`, `domain/scanner` | scanner action/reason decision | offset/scanner privacy tests | scanner called once | PR1 |
| 13 | Atom/embedding/segment/mapping | atom, embedding port, segmenter, mapper를 scanner 재호출 없이 연결한다. | 9 atom/embedding/segment/mapper, 17 | `domain/atoms`, `ml/embedding`, `domain/segmenter`, `domain/mapping` | vector persistence, keyword rescan | no rescan/vector storage tests | call order tests pass | PR12 |
| 14 | LR classifier runtime | LR artifact registry와 candidate segment-label result만 반환하는 classifier를 구현한다. | 9 classifier, 17 | `ml/classifier`, `models/manifest` | final action 결정, exact score storage | LR no-action/no-score-storage tests | artifact validation pass | PR13 |
| 15 | RoBERTa verifier worker | LR candidate pair만 검증하는 verifier worker를 구현한다. | 9 verifier, 12, 17 | `ml/verifier`, `runtime/verifier_worker.py` | missing label 복구, action 결정 | candidate-gated verifier tests | verifier boundary pass | PR14 |
| 16 | Policy Orchestrator | final action/reason_code/severity를 policy 단일 경계로 이동한다. | 13, 14, 16 | `domain/policy`, `application/analyze/policy_adapter.py` | parser/scanner/classifier action 결정 | policy-only action tests | final action source pass | PR15 |
| 17 | Response and event serialization | response adapter, masked_prompt rule, EventStorage allowlist write를 고정한다. | 14, 16 | `interfaces/http/response_adapter.py`, `privacy`, `events` | full masked prompt 저장, file-derived masked_prompt | response/privacy snapshot | compatibility pass | PR16 |
| 18 | External model artifact intake gates | Product runtime에서 dataset/train/hard_eval source 없이 manifest-backed model artifact만 load하도록 gate를 추가한다. Offline training workspace는 hard_eval exclusion, Qwen freeze, replacement report를 산출한다. | 17, 18.9 | `models/manifest`, `ml/classifier`, `ml/verifier`, runtime factory | runtime의 dataset/train/hard_eval source 의존, online learning, manifest 없는 model load | artifact intake/runtime load tests | manifest-backed runtime load pass | PR14 |
| 19 | End-to-end pipeline integration | fake-heavy dependency E2E와 real-profile opt-in E2E를 묶는다. | 2, 18 | `tests/integration` | flaky real OCR in default CI | full pipeline tests | deterministic CI pass | PR17, PR18 |
| 20 | Static quality and cleanup | import-linter/radon/ruff/typecheck를 CI merge gate로 묶고 shims를 정리한다. | 15, 18.11, 21 | `.github/workflows`, quality configs | behavior change, public API change | static quality tests | all gates pass | PR19 |

---

## 20. Schema 변경 관리 규칙

### 20.1 변경 원칙

1. public API field 제거 금지.
2. required field 추가 시 schema version bump 필수.
3. persisted field 추가 시 privacy review 필수.
4. raw content 저장 가능성을 만드는 field 추가 금지.
5. field alias는 만들지 않는다.
6. 같은 의미의 field name은 하나로 통일한다.
7. response compatibility snapshot을 갱신하지 않은 API schema 변경은 merge 금지.
8. model artifact schema 변경은 artifact manifest version bump가 필요하다.
9. dataset schema 변경은 offline training workspace의 split/audit pipeline fixture 갱신이 필요하다. Product runtime은 dataset schema가 아니라 artifact manifest compatibility를 검증한다.
10. service-local type은 공용 schema로 승격하지 않는다.
11. parser schema는 HTTP schema를 import하지 않는다.
12. ML module은 API response schema를 import하지 않는다.

### 20.2 Migration required fields

| field category | migration needed when changed |
| --- | --- |
| API request fields | always |
| API response fields | always |
| EventRecord fields | always |
| ParsedDocument/ParsedBlock fields | if required or persisted |
| Offset fields | always |
| ML output fields | always |
| PolicyDecision fields | always |
| Artifact paths | always |
| Dataset split fields | always |
| TemporaryFileStore metadata | if persisted or security relevant |

### 20.3 Extension compatibility rule

* Existing extension-required fields must remain present.
* New nullable fields may be added with schema version update.
* Existing enum values must not be removed.
* UI message semantics must remain template-based.
* `masked_prompt` storage prohibition is not relaxed by response compatibility.
* Legacy request adapter may exist, but target request schema remains `inputs[]`.

## 21. Implementation Readiness Checklist

| checklist item | required status |
| --- | --- |
| Pipeline order fixed | required |
| Logical stage and runtime component vocabulary separated | required |
| Extension no file content read | required |
| Extension no OCR/parser dependency | required |
| Upload/temp file flow implemented | required |
| `file_ref` opaque owner/session/request/temp-scope checked | required |
| `file_ref` contains no path, URL, filename, extension, MIME string | required |
| Analyze request `inputs[]` schema | required |
| `schema_version="v3"` public compatibility preserved | required |
| Text vs file_reference separated | required |
| `kind/source/content_included/content/file_ref/file_kind` invariants enforced | required |
| `file_kind=None` only for non-file text input | required |
| `file_kind="unknown"` for unknown file type | required |
| Original file name rejected downstream | required |
| `AnalyzeRequest` has no raw file bytes/base64/OCR text/extracted text | required |
| OCR is File Parser extraction method, not independent pipeline stage | required |
| ParserWorkerPayload contains coarse extraction_requirement only | required |
| AnalyzeService does not create concrete parser execution plan | required |
| ParserWorkerPool only manages worker boundary | required |
| FileParserRunner orchestrates resolver/resolver/executor inside worker runtime | required |
| ParserPlanResolver creates typed ParserExecutionPlan | required |
| ParserExecutionPlan separates steps and fallback_rules | required |
| ParserPlanExecutor executes steps and aggregates FileParserResult | required |
| ParserAdapter uniform interface | required |
| TemporaryFileResolverPort uses TempFileAccessContext | required |
| TemporaryFileResolverPort used only inside parser worker runtime | required |
| OcrEnginePort swappable provider boundary | required |
| Default OCR engine PaddleOcrEngine behind port | required |
| PaddleOCR only local text detection + recognition | required |
| PaddleOCR document parser/layout/VLM/Markdown conversion forbidden | required |
| Fallback OCR engine TesseractOcrEngine behind port | required |
| Tesseract fallback triggers typed and tested | required |
| Default PDF native extraction uses pypdf | required |
| Default PDF rendering uses pypdfium2/PDFium | required |
| PDF OCR fallback page-level only | required |
| Native text sufficient page skips OCR | required |
| `low_native_text_page_ratio` metadata only, not OCR expansion gate | required |
| PyMuPDF/MuPDF/Ghostscript/Poppler/pdf2image forbidden by default | required |
| Cloud OCR forbidden by default | required |
| Default non-OCR parser stack fixed | required |
| Legacy binary Office formats unsupported by default | required |
| External office converters forbidden by default | required |
| OCR/parser dependency lockfile and license artifact updated together | required |
| Parser/OCR SBOM artifact generated | required |
| Parser/OCR license report generated | required |
| OCR model weight license report generated | required |
| NOTICE.parser_ocr.txt generated | required |
| Normalizer before scanner | required |
| Original/normalized offset mapping | required |
| Scanner no raw value output | required |
| Scanner called once before atom/embedding/segment/classifier/verifier | required |
| Signal mapping by original offset or atom membership | required |
| Qwen3 singleton load | required |
| Qwen3 freeze with no runtime fine-tuning/online learning/gradient update | required |
| LR only first-stage trainable classifier | required |
| One-vs-Rest multi-label LR | required |
| LR emits candidate segment-label result only | required |
| LR no action output | required |
| Verifier LR-candidate segment-label pair only | required |
| Verifier no label/segment addition | required |
| Verifier no action output | required |
| Policy-only final action | required |
| Timeout/failure not allow reason | required |
| File-derived content has no masked_prompt | required |
| hard_eval excluded from tuning/selection | required |
| same template_id split lock | required |
| EventStorage no raw content | required |
| EventStorage stores size_bucket, not exact size_bytes | required |
| EventStorage stores no file_ref | required |
| EventStorage stores no original file name, document title, author, sheet name | required |
| EventStorage stores no OCR input image dump or parser input dump | required |
| EventStorage stores no exact classifier score/verifier raw logits/vector | required |
| API response required fields preserved | required |
| Composition root owns concrete binding | required |
| SOLID boundary tests pass | required |
| Clean Code static quality gates pass | required |
| TDD Red-Green-Refactor evidence per PR | required |
| PR sequence documented and independently rollbackable | required |
