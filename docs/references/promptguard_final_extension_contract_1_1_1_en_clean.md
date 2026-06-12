# PromptGuard Final Extension Contract 1.1.1 — Clean

## 0. Document Status

This document does not modify `promptguard_dev_docs_1_0_2.md`. The 1.0.2 document remains the baseline contract.

This document defines only the final extension contract layered on top of 1.0.2. Only items explicitly changed or extended here take precedence for 1.1.1. All unspecified authentication, session, permission, dashboard, storage policy, error response, and Filter Rule contracts follow 1.0.2.

---

## 1. Contract Delta from 1.0.2

| Item | 1.0.2 baseline | 1.1.1 contract | Change class |
|---|---|---|---|
| File handling | small text file, attachment metadata, unsupported attachment | server temporary file reference through `file_ref` | API extension |
| `/files/prepare` | absent | stores send-time active attachment raw file temporarily and returns `file_ref` | new API |
| `/prompts/analyze.inputs[].kind` | `text`, `attachment_metadata`, `unsupported_attachment` | adds `file_ref` | existing field value extension |
| `metadata.extension` | attachment metadata | reused for file_ref metadata | reused metadata |
| `metadata.mime` | attachment metadata | reused for file_ref metadata | reused metadata |
| `metadata.size_bytes` | attachment/input size metadata | reused for file_ref metadata | reused metadata |
| `file_ref` | absent | server temporary file reference | new field |
| `scan_status` | absent | parser/OCR status | new field |
| `location_hint` | absent | non-content file location hint for user action | new field |
| `user_notices[]` | top-level `user_message` | structured messages for multiple inputs/findings | new field |
| `reason_code` | detections and dry-run | extended to file parser, ML classifier, and Gemma judge results | extended use |
| File analysis scope | PDF/Office/OCR after MVP | PDF, DOCX, XLSX, PPTX, HWPX, image OCR | file analysis extension |
| Analysis structure | rule detector, keyword, regex, context rule | Stage 0 scan, semantic chunking, Qwen classifier, Gemma judge | internal implementation extension |
| Dashboard | metadata-only | reason_code/template based summary | metadata extension |
| Event storage | event/input/detection metadata | parser_status, ocr_status, location_kind, confidence_bucket | DB metadata extension |

---

## 2. Core Implementation Scope

1.1.1 includes:

- `/files/prepare`
- `kind="file_ref"` input in `/prompts/analyze`
- send-time active attachment manifest upload
- temp file TTL cleanup
- file parser registry
- PDF native text parser
- DOCX parser
- XLSX parser
- PPTX parser
- HWPX parser
- image OCR text parser
- TXT / MD / LOG / ENV / code / CSV / JSON / YAML / XML / HTML parser
- `ParsedDocument`, `ParsedBlock`
- `AnalysisAtom`, `AnalysisSegment`
- Stage 0 full scan
- semantic dynamic chunking
- Qwen embedding classifier
- PII relevance classifier
- Code sensitivity classifier
- Gemma E4B secondary judge
- ReasonCode enum
- UserNotice templates
- AdminSummary templates
- scan_status
- location_hint
- strict / balanced policy
- OCR fixture dataset
- ML dataset build pipeline
- extension WBS and test gates

---

## 3. API Contract

### 3.1 `POST /files/prepare`

Role: register a send-time active attachment raw file in temporary server storage and return a `file_ref`.

`/files/prepare` is a new 1.1.1 API. The file metadata representation reuses `extension`, `mime`, and `size_bytes` from 1.0.2 `attachment_metadata.metadata`.

Request: `multipart/form-data`

| Field | Class | Description |
|---|---|---|
| `file` | new | raw file |
| `client_file_id` | new | extension-local file ID |
| `client_request_id` | reused concept | send attempt ID |
| `capture_method` | new | `file_input`, `drop`, `paste_file`, `unknown` |

Response:

```json
{
  "file_ref": "file_tmp_abc123",
  "client_file_id": "local_file_1",
  "status": "staged",
  "metadata": {
    "extension": "xlsx",
    "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "size_bytes": 834221
  },
  "expires_at": "2026-06-07T12:30:00Z"
}
```

Contract:

- `file_ref` belongs to the authenticated user.
- `file_ref` is used only for the same `client_request_id` analysis attempt.
- `file_ref` has a TTL.
- `metadata.extension` is extension metadata only, not original filename storage.
- `metadata.mime` may be browser-reported or server-observed and is not a trust boundary.
- The server performs size checks and MIME sniffing instead of trusting extension/mime alone.
- Files exceeding upload size limit are rejected with `413 Payload Too Large`.
- `file_ref` is usable by `/prompts/analyze` only when `state == "staged"`, `expires_at > now`, and `deleted_at IS NULL`.

### 3.2 File Cancellation

Files are uploaded only at send time through `/files/prepare`. Files cancelled before send are not uploaded to the server.

Cancellation is determined by reconciling the extension's `PendingFileStore` with the pre-send `ActiveAttachmentManifest`.

```text
exists in pendingFiles
AND absent from the pre-send active attachment manifest
→ cancelled file
→ no server upload
```

A file prepared but not analyzed is removed by TTL cleanup.

### 3.3 `/prompts/analyze` Extension

The 1.0.2 `inputs[]` structure is retained. 1.1.1 adds `kind="file_ref"`.

```json
{
  "input_id": "file_1",
  "kind": "file_ref",
  "source": "file",
  "file_ref": "file_tmp_abc123",
  "size_bytes": 834221,
  "content_included": false,
  "metadata": {
    "extension": "xlsx",
    "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  }
}
```

### 3.4 Analyze Response Extension

The 1.0.2 top-level action contract is retained. 1.1.1 adds `scan_status`, `location_hint`, and `user_notices`.

```json
{
  "event_id": "evt_123",
  "request_id": "send_123",
  "action": "Block",
  "user_message": "The attachment contains information that cannot be sent.",
  "allow_original_send": false,
  "requires_user_confirmation": false,
  "masked_prompt": null,
  "input_results": [
    {
      "input_id": "file_1",
      "kind": "file_ref",
      "source": "file",
      "content_included": false,
      "content_scanned": true,
      "scan_status": {
        "parser_status": "parsed",
        "ocr_status": "not_applicable"
      },
      "findings": [
        {
          "finding_id": "fd_1",
          "category": "PII",
          "severity": "critical",
          "scope": "file_block",
          "recommended_action": "block",
          "reason_code": "PII_HIGH_RISK_IN_FILE",
          "location_hint": {
            "kind": "spreadsheet",
            "sheet_index": 0,
            "row_start": 2,
            "row_end": 30
          }
        }
      ]
    }
  ],
  "user_notices": [
    {
      "severity": "critical",
      "message_template_id": "file_high_risk_pii_blocked",
      "reason_code": "PII_HIGH_RISK_IN_FILE",
      "input_id": "file_1"
    }
  ]
}
```

---

## 4. Extension File Handling Contract

### 4.1 PendingFile

The extension does not upload the raw File at attachment time. The raw File is kept in the extension memory pending file store.

```ts
type PendingFile = {
  local_file_id: string;
  file: File;
  metadata: {
    extension?: string;
    mime?: string;
    size_bytes: number;
  };
  capture_method: "file_input" | "drop" | "paste_file" | "unknown";
  captured_at: number;
};
```

### 4.2 ActiveAttachmentManifest

Immediately before send, the extension collects attachments that remain in the UI.

```ts
type ActiveAttachmentManifestItem = {
  local_file_id?: string;
  metadata: {
    extension?: string;
    mime?: string;
    size_bytes?: number;
    attachment_kind?: string;
    attachment_index: number;
  };
  raw_file_available: boolean;
};
```

### 4.3 Send-time Reconcile

| Condition | Handling |
|---|---|
| manifest item exists + `raw_file_available=true` | upload through `/files/prepare`, then analyze as `kind="file_ref"` |
| manifest item exists + `raw_file_available=false` | analyze as `attachment_metadata` or `unsupported_attachment` |
| pendingFiles contains item + manifest does not | cancelled file; no server upload |

The extension does not need a separate file state enum. The state is determined by comparing `PendingFileStore` and `ActiveAttachmentManifest`.

---

## 5. Temp File TTL Cleanup Contract

### 5.1 Need

Files are uploaded only at send time. However, a file can remain in temporary storage if the following happens:

```text
/files/prepare succeeds
→ network error
→ user abandons the send flow
→ /prompts/analyze is not called
```

TTL cleanup removes these files.

### 5.2 temp_files State

`temp_files.state` uses only four values:

```text
staged
processing
consumed
failed
```

| State | Meaning |
|---|---|
| `staged` | `/files/prepare` completed; usable by analyze |
| `processing` | acquired by `/prompts/analyze` and being processed |
| `consumed` | already used by analyze; not reusable |
| `failed` | save, analysis, or deletion failed |

`expired` is derived by `expires_at < now`. `deleted` is derived by `deleted_at IS NOT NULL`.

Reusable condition:

```text
state == "staged"
AND expires_at > now
AND deleted_at IS NULL
```

### 5.3 temp_files Table

```sql
CREATE TABLE temp_files (
  file_ref TEXT PRIMARY KEY,
  owner_login_id TEXT NOT NULL,
  client_file_id TEXT NOT NULL,
  client_request_id TEXT NOT NULL,

  state TEXT NOT NULL,

  storage_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,

  extension TEXT,
  mime TEXT,
  size_bytes BIGINT NOT NULL,

  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  failed_reason TEXT
);
```

### 5.4 Default Settings

```text
TEMP_FILE_TTL_SECONDS = 1800
TEMP_FILE_CLEANUP_INTERVAL_SECONDS = 60
TEMP_FILE_CLEANUP_BATCH_SIZE = 100
ANALYZE_STALE_SECONDS = 1800
```

### 5.5 Cleanup Candidates

```text
state = staged AND expires_at < now AND deleted_at IS NULL
state = consumed AND deleted_at IS NULL
state = failed AND expires_at < now AND deleted_at IS NULL
state = processing AND updated_at < now - ANALYZE_STALE_SECONDS AND deleted_at IS NULL
```

### 5.6 Cleanup Worker

`TtlCleanupWorker` runs as a server background worker. It periodically selects cleanup candidates from `temp_files` and deletes physical files from `TempFileStore`.

```python
async def temp_file_cleanup_loop(app_state):
    while True:
        try:
            await cleanup_expired_temp_files(app_state)
        except Exception:
            app_state.logger.exception("temp_file_cleanup_failed")
        await asyncio.sleep(app_state.settings.TEMP_FILE_CLEANUP_INTERVAL_SECONDS)
```

Deletion is idempotent.

---

## 6. File Parser Registry

### 6.1 Parser Interface

```python
class FileParser(Protocol):
    parser_id: str
    supported_extensions: set[str]
    supported_mime_prefixes: set[str]

    def parse(self, file_ref: str, path: Path, metadata: FileMetadata) -> ParsedDocument:
        ...
```

### 6.2 Parsers

| Parser | Implementation | ParsedBlock unit |
|---|---|---|
| PlainTextParser | UTF-8 first decode, fallback decode | line/paragraph |
| MarkdownParser | raw markdown retained | paragraph/code fence/table |
| DelimitedTextParser | csv/tsv parser | header + row group |
| JsonYamlXmlHtmlParser | structured text / visible text | key/value block |
| PdfTextParser | PyMuPDF native text | page/block |
| DocxParser | python-docx | paragraph/table row |
| XlsxParser | openpyxl read_only/data_only | sheet index + row group |
| PptxParser | python-pptx | slide/table |
| HwpxParser | zip+xml section text | paragraph |
| ImageOcrParser | OCR text extraction | OCR text block |

### 6.3 ParserStatus

```text
parsed
partial
failed
unsupported
timeout
too_large
encrypted
```

---

## 7. Image OCR Contract

### 7.1 OCR Role

Image OCR parser extracts text from an image and creates `ParsedBlock`s. OCR does not create findings directly. OCR text is passed to the Stage 0 scanner and context classifier.

### 7.2 OCR Engine

Image OCR parser uses Tesseract OCR through the pytesseract wrapper. OCR output is collected through `image_to_data` to obtain word/line information.

### 7.3 OCR Steps

```text
1. Open image file.
2. Check image size/pixel limit.
3. Resize overly large images.
4. Apply EXIF orientation.
5. Convert to grayscale.
6. Run OCR.
7. Collect word/line results.
8. Drop empty text.
9. Create line/block ParsedBlocks.
10. Send OCR text to Stage 0 scan and context classifier.
```

### 7.4 OCR Limits

```text
MAX_IMAGE_PIXELS = 20000000
OCR_MAX_DIMENSION = 3000
OCR_TIMEOUT_SECONDS = 10
OCR_LANG = "kor+eng"
OCR_PSM = 6
```

### 7.5 OcrStatus

```text
not_applicable
text_found
no_text_detected
timeout
failed
```

### 7.6 OCR Policy

| OCR status | Sensitive finding | balanced | strict |
|---|---:|---|---|
| `text_found` | yes | finding-based action | finding-based action |
| `text_found` | no | allow | allow |
| `no_text_detected` | no | allow | allow |
| `timeout` | no | allow | warn |
| `failed` | no | allow | warn |

No sensitive finding in OCR output does not guarantee that the image contains no sensitive information. 1.1.1 detects sensitive information only from extracted OCR text.

---

## 8. OCR Fixture Dataset

### 8.1 Purpose

The OCR fixture dataset is not for OCR model training. It validates the PromptGuard OCR pipeline.

Goals:

- OCR parser creates text blocks
- OCR text reaches Stage 0 scanner
- PII/secret in OCR text is detected
- OCR failure/no text/finding policies work

### 8.2 Directory Layout

```text
datasets/ocr_fixtures/
  source_text/
    pii_phone_ko.txt
    pii_rrn_ko.txt
    pii_email.txt
    secret_token.txt
    benign_public_text.txt

  generated_images/
    clean/
    blurred/
    low_contrast/
    rotated/
    screenshot_like/
    no_text/

  labels/
    ocr_fixture_labels.jsonl

  reports/
    ocr_fixture_report.md
```

### 8.3 Label Format

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

Use expected findings rather than exact OCR text as the primary assertion.

---

## 9. Internal Data Models

### 9.1 ParsedDocument

```python
@dataclass(frozen=True)
class ParsedDocument:
    file_ref: str
    file_type: str
    parser_id: str
    parser_status: ParserStatus
    blocks: list["ParsedBlock"]
    metadata: dict
```

### 9.2 LocationHint

`LocationHint` is used only in the user runtime response. Admin events store only `location_kind`.

```ts
type LocationHint =
  | { kind: "page"; page: number }
  | { kind: "spreadsheet"; sheet_index?: number; row_start?: number; row_end?: number }
  | { kind: "slide"; slide_index: number }
  | { kind: "ocr"; block_index?: number }
  | { kind: "code"; line_start?: number; line_end?: number };
```

### 9.3 ScanStatus

```ts
type ParserStatus =
  | "parsed"
  | "partial"
  | "failed"
  | "unsupported"
  | "timeout"
  | "too_large"
  | "encrypted";

type OcrStatus =
  | "not_applicable"
  | "text_found"
  | "no_text_detected"
  | "timeout"
  | "failed";

type ScanStatus = {
  parser_status: ParserStatus;
  ocr_status?: OcrStatus;
};
```

---

## 10. Analysis Pipeline

```text
Raw input / file_ref
→ File Parser
→ ParsedDocument / ParsedBlock
→ Stage 0 Full Scan
→ AnalysisAtom Builder
→ Atom Embedding
→ Semantic Dynamic Chunker
→ Signal-to-Segment Mapping
→ Qwen Segment Classifier
→ Policy Orchestrator
→ Gemma E4B Judge, if needed
→ Final Action
```

Stage 0 signal detection runs once using raw offsets. Chunking does not re-scan text. Signals are attached to segments by range overlap after `AnalysisSegment` creation.

---

## 11. Stage 0 Full Scan

Stage 0 is a deterministic scan over the full input before chunking. Its purpose is to avoid missing sensitive spans and high-risk candidates before segmentation.

Signal types:

```text
pii_span
secret_span
secret_fingerprint
token_candidate
protected_target_hit
custom_regex_hit
sensitive_value_pattern_hit
context_trigger_hit
parser_status
```

---

## 12. Semantic Dynamic Chunking

Text is not chunked by fixed length only. First, the system creates `AnalysisAtom`s and computes cosine similarity between adjacent atom embeddings. Low-similarity boundaries are used as semantic transition candidates. When file structure is clear, structural boundaries such as page, slide, sheet row group, or code block take precedence.

Default values:

```text
min_chunk_chars = 500
target_chunk_chars = 1800
max_chunk_chars = 3500
overlap_atoms = 1
```

---

## 13. PII Relevance Classifier

A detected PII span does not automatically receive the same action. The classifier evaluates the PII type and surrounding context to estimate actual leakage risk.

Inputs:

- PII span type
- surrounding `AnalysisSegment`
- input source: composer, file, OCR
- surrounding risk signals

Output labels:

```text
example_or_format
real_personal_data
needed_for_task
bulk_sensitive_data
uncertain
```

| Label | Meaning |
|---|---|
| `example_or_format` | format explanation, example, or dummy value |
| `real_personal_data` | likely real personal data |
| `needed_for_task` | likely necessary for the requested task |
| `bulk_sensitive_data` | bulk/list-style personal data |
| `uncertain` | classifier alone cannot decide |

Default implementation is a Qwen embedding classifier. Gemma judge is applied only to uncertain or policy-conflict segments.

---

## 14. Code Sensitivity Classifier

The presence of code alone does not block transmission. The classifier determines whether a code segment is generic example code, public library usage, proprietary logic, security-critical logic, data-access logic, or infra configuration.

Labels:

```text
CODE_GENERIC_EXAMPLE
CODE_PUBLIC_OR_LIBRARY_USAGE
CODE_PROPRIETARY_LOGIC
CODE_SECURITY_CRITICAL_LOGIC
CODE_DATA_ACCESS_LOGIC
CODE_INFRA_CONFIG
```

Large code files are evaluated by max/top-k segment risk, not average risk.

---

## 15. Qwen Classifier

The Qwen embedding model is frozen. Only classifier heads are trained.

Classifier outputs:

```text
risk_scores
suppressor_scores
code_scores
pii_relevance_scores
```

---

## 16. Gemma E4B Judge

Gemma is not applied to all segments. It is applied only to high-risk, uncertain, or classifier-conflict segments.

Output schema:

```json
{
  "risk_present": true,
  "risk_categories": ["CONTRACT_INFO"],
  "recommended_reason_codes": ["CONTRACT_TERMS_CONTEXT"],
  "recommended_action": "warn",
  "confidence": 0.77
}
```

Contract:

- JSON validation is required.
- One repair attempt is allowed.
- If repair fails, mark Gemma unavailable.
- Gemma unavailable is not evidence for allow.
- Final action is decided by the Policy Orchestrator.
- Gemma free-form text is not stored in admin events.

---

## 17. Policy Orchestrator

Action priority:

```text
block > mask > warn > allow
```

Decision rules:

- confirmed secret in file → block
- confirmed secret in composer → mask or block by rule action
- high-risk PII in composer → mask
- high-risk PII in file → block
- high context risk → warn
- high context risk + protected target → stronger warn or strict block
- high suppressor score and no confirmed span → lower severity
- OCR no text only → allow in balanced mode
- parser failed/timeout → policy-mode dependent

---

## 18. ReasonCode, UserNotice, AdminSummary

ReasonCode is enum-based.

UserNotice is a structured message for the extension runtime UI.

```ts
type UserNotice = {
  severity: "info" | "warning" | "critical";
  message_template_id: string;
  reason_code: ReasonCode;
  input_id?: string;
  location_hint?: LocationHint;
};
```

Admin summary is generated from server templates. Admin events store only allowlisted metadata.

Allowed admin event fields:

```text
action
reason_code
category
severity
input_kind
source
file_type
parser_status
ocr_status
location_kind
protected_target_hit
confidence_bucket
created_at
```

---

## 19. Event Storage Contract

Event store persists only allowlisted metadata.

Allowed:

- event_id
- login_id
- action
- risk_level
- reason_code
- category
- severity
- input_kind
- source
- file_type
- parser_status
- ocr_status
- location_kind
- protected_target_hit
- confidence_bucket

Not stored:

- source text
- extracted text
- OCR text
- raw file bytes
- raw secret
- original file name
- full masked_prompt

---

## 20. Worker Contract

FastAPI route handlers remain thin.

Workers:

```text
ParserWorkerPool
EmbeddingWorker
GemmaJudgeWorker
TtlCleanupWorker
```

Rules:

- Qwen/Gemma models are not loaded per request.
- Qwen embedding uses queue + micro-batching.
- Gemma judge uses bounded queue + timeout.
- Parser execution must not block the event loop.
- TtlCleanupWorker deletes expired temp files.
- file_ref ownership is checked before analysis.

---

## 21. ML Dataset Build Contract

### 21.1 Dataset Types

```text
context_dataset
pii_relevance_dataset
code_sensitivity_dataset
ocr_fixtures
```

### 21.2 Directory Layout

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

### 21.3 Step-by-step Process

1. Write the label definition document.
2. Manually write 20–50 seed samples per label.
3. Generate synthetic samples from the seed samples.
4. Apply automatic filters to synthetic samples.
5. Human-review label mismatch and shortcut patterns.
6. Create hard negative samples.
7. Split train/valid/test into 70/15/15.
8. Keep samples from the same template in the same split.
9. Never put hard_eval samples into train.
10. Extract Qwen embeddings.
11. Train One-vs-Rest classifiers.
12. Calibrate per-label thresholds on the validation set.
13. Evaluate precision/recall/F1.
14. Record false positives and false negatives in an error bank.
15. Save model artifacts and thresholds.
16. Allow model replacement only after fixed hard_eval passes.
17. Generate OCR fixtures and run OCR parser/policy tests.

---

## 22. WBS

### A. Contract and Schema

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| A1 | 1.0.2 delta table | Document | Change table | reused/expanded/new fields classified |
| A2 | file_ref input schema | API schema | Pydantic model | `kind=file_ref` validates |
| A3 | AnalyzeResult extension | API schema | scan_status/findings/user_notices | Response schema validates |
| A4 | ReasonCode enum | Shared type | Python/TS enum | Server and client share values |
| A5 | LocationHint schema | API schema | union type | page/sheet/slide/ocr/code hints validate |

### B. FileRef / TTL Cleanup

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| B1 | temp_files table | DB | migration | file_ref state/TTL stored |
| B2 | TempFileStore | Service | save/read/delete | file roundtrip tested |
| B3 | `/files/prepare` | API | route | file_ref returned |
| B4 | ownership check | Service | repository method | cross-user access denied |
| B5 | TTL settings | Config | env/config | TTL and interval loaded |
| B6 | cleanup query | Repository | method | cleanup candidates selected |
| B7 | cleanup worker | Worker | background task | expired files deleted |
| B8 | stale processing handler | Worker | state transition | stale files marked failed |
| B9 | idempotent delete | Storage | delete_if_exists | missing file does not fail cleanup |
| B10 | cleanup tests | Tests | pytest | DB + storage cleanup verified |

### C. Extension File Handling

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| C1 | PendingFileStore | Extension module | local store | raw File refs retained until send |
| C2 | ActiveAttachmentManifest | Extension module | manifest builder | send-time active attachments collected |
| C3 | Manifest reconcile | Extension module | decision function | cancelled files excluded |
| C4 | prepare client | Extension API client | upload function | file_ref received |
| C5 | analyze input builder | Extension module | `kind=file_ref` input | request schema valid |
| C6 | metadata-only fallback | Extension module | attachment_metadata/unsupported input | raw-file-missing case handled |

### D. Parser Registry / OCR

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| D1 | parser protocol | Interface | FileParser | all parsers implement |
| D2 | parsed models | Internal type | ParsedDocument/ParsedBlock | tests pass |
| D3 | text/markdown parser | Parser | blocks | fixtures pass |
| D4 | csv/tsv parser | Parser | header+row groups | fixtures pass |
| D5 | structured text parser | Parser | key/value blocks | fixtures pass |
| D6 | PDF parser | Parser | page blocks | fixtures pass |
| D7 | DOCX parser | Parser | paragraph/table blocks | fixtures pass |
| D8 | XLSX parser | Parser | sheet/row groups | fixtures pass |
| D9 | PPTX parser | Parser | slide blocks | fixtures pass |
| D10 | HWPX parser | Parser | paragraph blocks | fixtures pass |
| D11 | image OCR parser | Parser | OCR blocks | fixtures pass |
| D12 | parser timeout guard | Runtime | wrapper | timeout mapped to status |
| D13 | OCR fixture generator | Dataset script | generated images | clean/degraded/no-text fixtures generated |
| D14 | OCR fixture labels | Dataset | labels jsonl | expected findings/actions defined |
| D15 | OCR parser tests | Tests | pytest | text_found/no_text/timeout/failure pass |
| D16 | OCR policy tests | Tests | pytest | balanced/strict policy verified |
| D17 | OCR report | Report | markdown report | OCR fixture result documented |
