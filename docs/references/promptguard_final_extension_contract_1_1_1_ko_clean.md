# PromptGuard Final Extension Contract 1.1.1 — 추가개발 계약문서 Clean

## 0. 문서 지위

이 문서는 `promptguard_dev_docs_1_0_2.md`를 수정하지 않는다. 1.0.2는 기준 계약으로 유지한다.
이 문서는 1.0.2 위에 추가되는 최종발표 추가개발 계약만 정의한다. 이 문서에서 명시적으로 변경하거나 확장한 항목만 1.1.1 범위에서 우선한다. 명시하지 않은 인증, 세션, 권한, 대시보드, 저장 정책, 오류 응답, Filter Rule 기본 계약은 1.0.2를 따른다.

---

## 1. 1.0.2 대비 계약 변경표

| 항목 | 1.0.2 기준 | 1.1.1 계약 | 변경 분류 |
|---|---|---|---|
| 파일 처리 | 작은 text file, attachment metadata, unsupported attachment 중심 | 서버 임시 파일 참조 `file_ref` 추가 | API 확장 |
| `/files/prepare` | 없음 | send 시점 active attachment raw file을 임시 저장하고 `file_ref` 반환 | 신규 API |
| `/prompts/analyze.inputs[].kind` | `text`, `attachment_metadata`, `unsupported_attachment` | `file_ref` 허용값 추가 | 기존 필드 허용값 확장 |
| `metadata.extension` | attachment metadata에서 사용 | file_ref metadata에서도 재사용 | 기존 metadata 재사용 |
| `metadata.mime` | attachment metadata에서 사용 | file_ref metadata에서도 재사용 | 기존 metadata 재사용 |
| `metadata.size_bytes` | attachment metadata/input size에서 사용 | file_ref metadata에서도 재사용 | 기존 metadata 재사용 |
| `file_ref` | 없음 | 서버 임시 파일 참조 | 신규 필드 |
| `scan_status` | 없음 | parser/OCR 상태 | 신규 필드 |
| `location_hint` | 없음 | 사용자 조치를 위한 비식별 파일 위치 힌트 | 신규 필드 |
| `user_notices[]` | top-level `user_message` 중심 | 여러 input/finding을 UI에 전달하는 구조화 메시지 | 신규 필드 |
| `reason_code` | detection/dry-run에서 사용 | file parser, ML classifier, Gemma judge 결과에도 적용 | 기존 개념 적용 범위 확장 |
| 파일 분석 범위 | PDF/Office/OCR은 MVP 이후 | PDF, DOCX, XLSX, PPTX, HWPX, image OCR 포함 | 파일 분석 범위 확장 |
| 분석 구조 | rule detector, keyword, regex, context rule | Stage 0 scan, semantic chunking, Qwen classifier, Gemma judge 추가 | 내부 구현 확장 |
| 대시보드 | metadata-only | reason_code/template 기반 summary 추가 | metadata 확장 |
| 이벤트 저장 | event/input/detection metadata | parser_status, ocr_status, location_kind, confidence_bucket 추가 | DB metadata 확장 |

---

## 2. 핵심 구현 범위

1.1.1은 다음 구현을 포함한다.

- `/files/prepare`
- `/prompts/analyze`의 `kind="file_ref"` 입력
- send 시점 active attachment manifest 기반 파일 업로드
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
- 추가개발 WBS와 테스트 게이트

---

## 3. API 계약

### 3.1 `POST /files/prepare`

역할: send 시점 active attachment raw file을 서버 임시 저장소에 등록하고 `file_ref`를 반환한다.

`/files/prepare`는 1.1.1 신규 API다. 파일 metadata 표현은 1.0.2의 `attachment_metadata.metadata`에서 사용하던 `extension`, `mime`, `size_bytes` 개념을 재사용한다.

Request: `multipart/form-data`

| 필드 | 분류 | 설명 |
|---|---|---|
| `file` | 신규 | raw file |
| `client_file_id` | 신규 | 확장앱 내부 파일 ID |
| `client_request_id` | 기존 개념 재사용 | send attempt ID |
| `capture_method` | 신규 | `file_input`, `drop`, `paste_file`, `unknown` |

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

계약:

- `file_ref`는 인증 사용자에게 귀속된다.
- `file_ref`는 같은 `client_request_id`의 분석 요청에서만 사용한다.
- `file_ref`는 TTL을 가진다.
- `metadata.extension`은 원본 파일명이 아니라 확장자 metadata만 의미한다.
- `metadata.mime`은 브라우저 보고값 또는 서버 관측값일 수 있으며 신뢰 경계가 아니다.
- 서버는 `extension`/`mime`만 믿지 않고 size check와 MIME sniffing을 수행한다.
- 파일 크기 제한 초과는 `413 Payload Too Large`로 거부한다.
- `file_ref`는 `state == "staged"`, `expires_at > now`, `deleted_at IS NULL`일 때만 `/prompts/analyze`에서 사용할 수 있다.

### 3.2 파일 취소 처리

파일은 send 시점에만 `/files/prepare`로 업로드한다. send 전에 사용자가 첨부를 취소한 파일은 서버로 업로드하지 않는다.

취소 판단은 확장앱의 `PendingFileStore`와 send 직전 `ActiveAttachmentManifest`를 reconcile하여 수행한다.

```text
pendingFiles에는 있음
AND send 직전 active attachment manifest에는 없음
→ 취소된 파일
→ 서버 전송 없음
```

`/files/prepare` 이후 `/prompts/analyze`가 호출되지 않은 파일은 TTL cleanup으로 제거한다.

### 3.3 `POST /prompts/analyze` 확장

1.0.2의 `inputs[]` 구조를 유지한다. 1.1.1은 `kind="file_ref"`를 추가한다.

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

| 필드 | 1.0.2 기준 | 1.1.1 처리 |
|---|---|---|
| `input_id` | 기존 | 재사용 |
| `kind` | 기존 | 허용값 `file_ref` 추가 |
| `source` | 기존 | 재사용 |
| `size_bytes` | 기존 | 재사용 |
| `content_included` | 기존 | file_ref에서는 `false` |
| `metadata.extension` | 기존 attachment metadata 개념 | 재사용 |
| `metadata.mime` | 기존 attachment metadata 개념 | 재사용 |
| `file_ref` | 없음 | 신규 |

### 3.4 Analyze response 확장

1.0.2의 top-level action 계약을 유지한다. 1.1.1은 `scan_status`, `location_hint`, `user_notices`를 추가한다.

```json
{
  "event_id": "evt_123",
  "request_id": "send_123",
  "action": "Block",
  "user_message": "첨부파일에서 전송할 수 없는 정보가 감지되었습니다.",
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

## 4. Extension 파일 처리 계약

### 4.1 PendingFile

확장앱은 첨부 시점에 raw File을 서버로 보내지 않는다. raw File은 확장앱 메모리의 pending file store에 보관한다.

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

확장앱은 send 직전에 실제 UI에 남아 있는 첨부 목록을 수집한다.

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

### 4.3 Send-time reconcile

| 조건 | 처리 |
|---|---|
| manifest item 존재 + `raw_file_available=true` | `/files/prepare` 업로드 후 `kind="file_ref"`로 analyze |
| manifest item 존재 + `raw_file_available=false` | `attachment_metadata` 또는 `unsupported_attachment`로 analyze |
| pendingFiles에는 있음 + manifest에는 없음 | 취소된 파일로 보고 서버 전송 없음 |

확장앱 파일 상태 enum은 별도로 두지 않는다. 상태 판단은 `PendingFileStore`와 `ActiveAttachmentManifest`의 비교 결과로 수행한다.

---

## 5. Temp File TTL Cleanup 계약

### 5.1 필요성

파일은 send 시점에만 업로드된다. 그러나 다음 경우 서버 임시 저장소에 파일이 남을 수 있다.

```text
/files/prepare 성공
→ 네트워크 오류
→ 사용자가 전송 흐름 중단
→ /prompts/analyze 미호출
```

이를 제거하기 위해 TTL cleanup을 구현한다.

### 5.2 temp_files 상태

`temp_files.state`는 다음 네 값만 사용한다.

```text
staged
processing
consumed
failed
```

| 상태 | 의미 |
|---|---|
| `staged` | `/files/prepare` 완료, 아직 analyze에서 사용할 수 있음 |
| `processing` | `/prompts/analyze`에서 획득해 처리 중 |
| `consumed` | analyze에 사용 완료, 재사용 불가 |
| `failed` | 저장, 분석, 삭제 중 실패 |

`expired`는 상태가 아니라 `expires_at < now`로 판단한다. `deleted`는 상태가 아니라 `deleted_at IS NOT NULL`로 판단한다.

재사용 가능 조건:

```text
state == "staged"
AND expires_at > now
AND deleted_at IS NULL
```

### 5.3 temp_files 테이블

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

인덱스:

```sql
CREATE INDEX idx_temp_files_owner ON temp_files(owner_login_id);
CREATE INDEX idx_temp_files_state_expires ON temp_files(state, expires_at);
CREATE INDEX idx_temp_files_client_request ON temp_files(owner_login_id, client_request_id);
```

### 5.4 기본 설정값

```text
TEMP_FILE_TTL_SECONDS = 1800
TEMP_FILE_CLEANUP_INTERVAL_SECONDS = 60
TEMP_FILE_CLEANUP_BATCH_SIZE = 100
ANALYZE_STALE_SECONDS = 1800
```

### 5.5 cleanup 대상

cleanup worker는 아래 대상을 조회한다.

```text
state = staged AND expires_at < now AND deleted_at IS NULL
state = consumed AND deleted_at IS NULL
state = failed AND expires_at < now AND deleted_at IS NULL
state = processing AND updated_at < now - ANALYZE_STALE_SECONDS AND deleted_at IS NULL
```

### 5.6 cleanup worker

`TtlCleanupWorker`는 서버 background worker로 동작한다. 주기적으로 `temp_files` 테이블에서 cleanup 후보를 조회하고, `TempFileStore`에서 물리 파일을 삭제한다.

```python
async def temp_file_cleanup_loop(app_state):
    while True:
        try:
            await cleanup_expired_temp_files(app_state)
        except Exception:
            app_state.logger.exception("temp_file_cleanup_failed")
        await asyncio.sleep(app_state.settings.TEMP_FILE_CLEANUP_INTERVAL_SECONDS)
```

cleanup은 idempotent해야 한다.

```python
async def cleanup_expired_temp_files(app_state):
    rows = await app_state.temp_file_repo.list_cleanup_candidates(
        limit=app_state.settings.TEMP_FILE_CLEANUP_BATCH_SIZE
    )

    for row in rows:
        try:
            await app_state.temp_file_store.delete_if_exists(row.storage_path)
            await app_state.temp_file_repo.mark_deleted(row.file_ref)
        except Exception:
            await app_state.temp_file_repo.mark_failed(
                file_ref=row.file_ref,
                failed_reason="cleanup_delete_failed"
            )
```

### 5.7 analyze에서 file_ref 획득

```python
async def acquire_file_ref_for_analyze(file_ref: str, login_id: str):
    row = await repo.get_owned(file_ref, login_id)

    if row.state != "staged":
        raise FileRefNotUsable()

    if row.expires_at < now():
        raise FileRefExpired()

    if row.deleted_at is not None:
        raise FileRefNotUsable()

    await repo.mark_processing(file_ref)
    return row
```

분석 완료 또는 실패 후 파일은 삭제 대상이다.

```python
try:
    parsed = parse_file(row.storage_path)
finally:
    await file_store.delete_if_exists(row.storage_path)
    await repo.mark_consumed_and_deleted(row.file_ref)
```

---

## 6. File Parser Registry

### 6.1 Parser interface

```python
class FileParser(Protocol):
    parser_id: str
    supported_extensions: set[str]
    supported_mime_prefixes: set[str]

    def parse(self, file_ref: str, path: Path, metadata: FileMetadata) -> ParsedDocument:
        ...
```

### 6.2 Parser별 구현

| Parser | 구현 방식 | ParsedBlock 단위 |
|---|---|---|
| PlainTextParser | UTF-8 우선 decode, fallback decode | line/paragraph |
| MarkdownParser | raw markdown 유지 | paragraph/code fence/table |
| DelimitedTextParser | csv/tsv parser | header + row group |
| JsonYamlXmlHtmlParser | 구조 text / visible text | key/value block |
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

| 상태 | 의미 |
|---|---|
| `parsed` | 분석 가능한 text block을 정상 생성 |
| `partial` | 일부 text block만 생성 |
| `failed` | parser 실행 실패 |
| `unsupported` | 지원하지 않는 파일 형식 |
| `timeout` | parser 제한 시간 초과 |
| `too_large` | parser 처리 한도 초과 |
| `encrypted` | 암호화 또는 비밀번호 보호로 내용 접근 불가 |

---

## 7. Image OCR 계약

### 7.1 OCR 역할

Image OCR parser는 이미지에서 텍스트를 추출해 `ParsedBlock`을 생성한다. OCR은 finding을 직접 생성하지 않는다. OCR text는 Stage 0 scanner와 context classifier에 입력된다.

### 7.2 OCR 엔진

Image OCR parser는 Tesseract OCR을 사용한다. Python 서버에서는 pytesseract wrapper를 사용한다. OCR 결과는 `image_to_data` 기반 TSV/dict 구조로 받아 word/line 정보를 얻는다.

### 7.3 OCR 처리 순서

```text
1. 이미지 파일 열기
2. 이미지 크기/픽셀 수 제한 확인
3. 너무 큰 이미지는 resize
4. EXIF orientation 보정
5. grayscale 변환
6. OCR 실행
7. word/line 결과 수집
8. 빈 text 제거
9. line/block 단위 ParsedBlock 생성
10. OCR text를 Stage 0 scan과 context classifier에 전달
```

### 7.4 OCR 제한값

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

| 상태 | 의미 |
|---|---|
| `not_applicable` | OCR 대상이 아님 |
| `text_found` | OCR text block을 하나 이상 생성 |
| `no_text_detected` | OCR은 실행됐지만 text block 없음 |
| `timeout` | OCR 제한 시간 초과 |
| `failed` | OCR 실행 실패 |

### 7.6 OCR policy

| OCR 상태 | 민감 finding | balanced | strict |
|---|---:|---|---|
| `text_found` | 있음 | finding 기준 action | finding 기준 action |
| `text_found` | 없음 | allow | allow |
| `no_text_detected` | 없음 | allow | allow |
| `timeout` | 없음 | allow | warn |
| `failed` | 없음 | allow | warn |

OCR 결과에서 민감정보가 발견되지 않았다는 것은 이미지에 민감정보가 없다는 보장이 아니다. 1.1.1은 OCR text에 대해서만 민감정보 탐지를 수행한다.

---

## 8. OCR Fixture Dataset 계약

### 8.1 목적

OCR fixture dataset은 OCR 모델 학습용이 아니다. PromptGuard OCR pipeline 검증용 테스트 데이터셋이다.

검증 목표:

- OCR parser가 text block을 생성하는지 확인
- OCR text가 Stage 0 scanner에 들어가는지 확인
- OCR text 안의 PII/secret이 탐지되는지 확인
- OCR 실패/텍스트 없음/민감정보 발견이 policy에 올바르게 반영되는지 확인

### 8.2 폴더 구조

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

### 8.3 Label 형식

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

OCR은 문자 단위로 항상 동일하게 나오지 않을 수 있으므로 exact text match를 기본 기준으로 삼지 않는다. 테스트는 `expected_findings` 중심으로 작성한다.

### 8.4 Fixture 생성 스크립트

```python
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def make_text_image(text: str, out_path: str, font_path: str, font_size: int = 36):
    img = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)
    draw.text((50, 150), text, fill="black", font=font)
    img.save(out_path)

def make_blurred(src: str, out_path: str):
    img = Image.open(src)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    img.save(out_path)

def make_low_contrast(text: str, out_path: str, font_path: str):
    img = Image.new("RGB", (1200, 400), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, 36)
    draw.text((50, 150), text, fill=(150, 150, 150), font=font)
    img.save(out_path)

def make_no_text(out_path: str):
    img = Image.new("RGB", (800, 500), (220, 230, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((100, 100, 700, 400), outline=(100, 100, 100), width=5)
    img.save(out_path)
```

### 8.5 Fixture 카테고리

| 카테고리 | 예 |
|---|---|
| clean sensitive text | 전화번호, 주민등록번호, 이메일, API key-like token |
| clean benign text | 기술 설명, 공개자료, 일반 OCR 테스트 문장 |
| degraded sensitive text | blur, low contrast, small font, rotated |
| no text image | 도형, 아이콘, 사진 느낌 배경 |
| OCR failure simulation | timeout monkeypatch, invalid image, corrupted file |

### 8.6 OCR test 기준

| 케이스 | 기대 결과 |
|---|---|
| 이미지에 `010-1111-1111` 포함 | OCR block 생성, PII_PHONE finding |
| 도형 이미지 | OCR block 없음, finding 없음, balanced allow |
| corrupted image | scan_status.ocr_status=`failed`, finding 없음, balanced allow, strict warn |
| timeout mock | scan_status.ocr_status=`timeout`, finding 없음, balanced allow, strict warn |
| OCR 일부 불완전 + 민감 finding 있음 | finding 기준 action, scan_status 함께 반환 |

---

## 9. 내부 데이터 모델

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

### 9.2 ParsedBlock

```python
@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    text: str
    source: "BlockSource"
    location: "BlockLocation | None"
    extraction_status: "ExtractionStatus"
```

### 9.3 BlockSource

```python
@dataclass(frozen=True)
class BlockSource:
    file_ref: str
    parser_id: str
    file_type: str
    unit_type: str
    block_index: int
```

### 9.4 LocationHint

`LocationHint`는 사용자 runtime 응답에만 사용한다. 관리자 이벤트에는 `location_kind`만 저장한다.

```ts
type LocationHint =
  | { kind: "page"; page: number }
  | { kind: "spreadsheet"; sheet_index?: number; row_start?: number; row_end?: number }
  | { kind: "slide"; slide_index: number }
  | { kind: "ocr"; block_index?: number }
  | { kind: "code"; line_start?: number; line_end?: number };
```

### 9.5 ExtractionStatus

```python
@dataclass(frozen=True)
class ExtractionStatus:
    method: Literal[
        "native_text",
        "xml_text",
        "spreadsheet_parse",
        "ocr",
        "fallback_text"
    ]
    status: ParserStatus
    coverage: Literal["complete", "partial", "none"]
    ocr_text_found: bool | None
    ocr_observed_confidence: float | None
    warnings: tuple[str, ...]
```

### 9.6 ScanStatus

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

## 10. 분석 파이프라인

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
→ Gemma E4B Judge, 필요한 경우
→ Final Action
```

Stage 0 signal detection은 raw offset 기준으로 한 번만 수행한다. chunk 단계에서는 재탐지하지 않는다. AnalysisSegment 생성 후 signal range overlap으로 segment에 한 번만 매핑한다.

---

## 11. Stage 0 Full Scan

Stage 0은 전체 입력에 대해 먼저 수행되는 deterministic scan이다. 목적은 민감 span과 고위험 후보를 chunking 전에 놓치지 않는 것이다.

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

대표 구현:

- 하이픈 없는 전화번호 포함
- 이메일
- 주민등록번호
- 카드번호
- 계좌번호 후보
- JWT
- private key
- known API key pattern
- unknown token-like candidate
- HMAC secret fingerprint
- custom regex
- protected target exact/canonical match

---

## 12. Semantic Dynamic Chunking

고정 길이로만 텍스트를 자르지 않는다. 먼저 `AnalysisAtom`을 만들고, 인접 atom embedding의 cosine similarity를 계산한다. 유사도가 낮아지는 지점을 의미 전환점으로 보고 chunk boundary 후보로 사용한다. 파일 구조가 명확한 경우에는 page, slide, sheet row group, code block 같은 구조 boundary를 우선한다.

기본값:

```text
min_chunk_chars = 500
target_chunk_chars = 1800
max_chunk_chars = 3500
overlap_atoms = 1
```

구현 순서:

1. ParsedBlock에서 AnalysisAtom 생성
2. atom embedding 계산
3. 인접 atom cosine similarity 계산
4. 구조 boundary와 semantic boundary 결합
5. min/target/max size로 AnalysisSegment 생성

---

## 13. PII Relevance Classifier

PII span이 발견되었다고 무조건 같은 action을 적용하지 않는다. PII span의 유형과 주변 문맥을 함께 보고 실제 개인정보 유출 가능성을 분류한다.

입력:

- PII span type
- PII span text의 원문값은 저장하지 않음
- PII span 주변 AnalysisSegment
- input source: composer, file, OCR 등
- surrounding risk signals

출력 label:

```text
example_or_format
real_personal_data
needed_for_task
bulk_sensitive_data
uncertain
```

| label | 의미 |
|---|---|
| `example_or_format` | 형식 설명, 예시, 더미값에 가까움 |
| `real_personal_data` | 실제 개인정보일 가능성이 높음 |
| `needed_for_task` | 사용자가 요청한 작업 수행에 필요한 값일 가능성이 높음 |
| `bulk_sensitive_data` | 다량 개인정보 또는 목록형 개인정보 |
| `uncertain` | classifier만으로 판단 불가 |

기본 구현은 Qwen embedding classifier다. Gemma judge는 `uncertain` 또는 policy 충돌이 있는 segment에만 적용한다.

---

## 14. Code Sensitivity Classifier

코드가 있다는 사실만으로 차단하지 않는다. 코드 segment가 일반 예시인지, 공개 라이브러리 사용인지, 사내 로직/보안 로직/인프라 설정인지 분류한다.

Label:

```text
CODE_GENERIC_EXAMPLE
CODE_PUBLIC_OR_LIBRARY_USAGE
CODE_PROPRIETARY_LOGIC
CODE_SECURITY_CRITICAL_LOGIC
CODE_DATA_ACCESS_LOGIC
CODE_INFRA_CONFIG
```

| label | 의미 |
|---|---|
| `CODE_GENERIC_EXAMPLE` | 일반 예제 코드 |
| `CODE_PUBLIC_OR_LIBRARY_USAGE` | 공개 라이브러리 사용 예 |
| `CODE_PROPRIETARY_LOGIC` | 사내 비즈니스 로직 가능성 |
| `CODE_SECURITY_CRITICAL_LOGIC` | 인증, 권한, 암호화, 보안 정책 관련 로직 |
| `CODE_DATA_ACCESS_LOGIC` | DB query, 고객 데이터 접근, 내부 API 접근 로직 |
| `CODE_INFRA_CONFIG` | 배포, secret, network, infra 설정 |

대량 코드 파일은 평균 점수로 판단하지 않는다. 고위험 segment의 max/top-k risk를 사용한다.

---

## 15. Qwen Classifier

Qwen embedding model은 freeze한다. 학습 대상은 classifier head다.

Classifier outputs:

```text
risk_scores
suppressor_scores
code_scores
pii_relevance_scores
```

Risk labels:

```text
AUTH_SECRET_OPERATION
CONTRACT_INFO
CUSTOMER_CONFIDENTIAL
INTERNAL_DECISION_STRATEGY
SOURCE_SECURITY_LOGIC
SECURITY_ARCHITECTURE_DECISION
CONTACT_OR_PERSONAL_IDENTIFIER_CONTEXT
```

Suppressor labels:

```text
TECHNICAL_EXPLANATION
GENERAL_CONCEPT_EXPLANATION
PUBLIC_OR_GENERAL_INFO_REQUEST
TEMPLATE_OR_CHECKLIST_REQUEST
TEST_LOG_OR_DUMMY_DATA_CONTEXT
```

---

## 16. Gemma E4B Judge

Gemma는 전체 segment에 적용하지 않는다. 고위험, 불확실, classifier 간 충돌이 있는 segment에만 적용한다.

대상:

- high-risk
- uncertain
- risk/suppressor conflict
- PII relevance uncertain
- code criticality uncertain
- protected target + medium risk
- strict mode

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

계약:

- JSON validation 필수
- 실패 시 repair 1회
- 재실패 시 Gemma unavailable
- Gemma unavailable은 allow 근거가 아님
- 최종 action은 Policy Orchestrator가 결정
- Gemma 자유서술은 관리자 이벤트에 저장하지 않음

---

## 17. Policy Orchestrator

Action priority:

```text
block > mask > warn > allow
```

Policy inputs:

- confirmed secret
- PII span
- PII relevance
- context risk score
- suppressor score
- code sensitivity score
- protected target hit
- context trigger hit
- file source
- scan_status
- Gemma judge result

Decision rules:

- confirmed secret in file → block
- confirmed secret in composer → mask or block by rule action
- high-risk PII in composer → mask
- high-risk PII in file → block
- context risk high → warn
- context risk high + protected target → stronger warn or strict block
- suppressor high and no confirmed span → lower severity
- OCR no text only → allow in balanced
- parser failed/timeout → policy mode dependent

---

## 18. ReasonCode, UserNotice, AdminSummary

### 18.1 ReasonCode

ReasonCode는 enum이다.

Examples:

```text
PII_PHONE_IN_COMPOSER
PII_HIGH_RISK_IN_FILE
AUTH_SECRET_CONFIRMED
AUTH_SECRET_CANDIDATE_WITH_USAGE_CONTEXT
CONTRACT_TERMS_CONTEXT
CUSTOMER_CONFIDENTIAL_CONTEXT
INTERNAL_DECISION_CONTEXT
SECURITY_ARCHITECTURE_CONTEXT
CODE_PROPRIETARY_LOGIC
CODE_SECURITY_CRITICAL_LOGIC
PROTECTED_TARGET_WITH_RISK_CONTEXT
PARSER_TIMEOUT
CONTENT_NOT_SCANNED
GEMMA_JUDGE_UNAVAILABLE
UNCERTAIN_NEAR_THRESHOLD
```

### 18.2 UserNotice

UserNotice는 extension runtime UI용 구조화 메시지다. 새로운 UI 레이아웃 계약이 아니라 기존 warn/mask/block UI가 소비할 수 있는 메시지 데이터다.

```ts
type UserNotice = {
  severity: "info" | "warning" | "critical";
  message_template_id: string;
  reason_code: ReasonCode;
  input_id?: string;
  location_hint?: LocationHint;
};
```

### 18.3 AdminSummary

관리자 summary는 서버 template에서 생성한다. 관리자 이벤트에는 허용된 metadata만 저장한다.

저장 허용 필드:

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

Event store는 allowlisted metadata만 저장한다.

허용:

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

저장하지 않는 값:

- source text
- extracted text
- OCR text
- raw file bytes
- raw secret
- original file name
- full masked_prompt

---

## 20. Worker Contract

FastAPI route handler는 얇게 유지한다.

Workers:

```text
ParserWorkerPool
EmbeddingWorker
GemmaJudgeWorker
TtlCleanupWorker
```

Rules:

- Qwen/Gemma model은 request마다 load하지 않는다.
- Qwen embedding은 queue + micro-batching을 사용한다.
- Gemma judge는 bounded queue + timeout을 사용한다.
- Parser는 event loop를 막지 않는 실행 경계에서 실행한다.
- TtlCleanupWorker는 만료된 temp file을 삭제한다.
- file_ref ownership은 분석 전 확인한다.

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

1. label 정의서를 작성한다.
2. label마다 20–50개 seed sample을 사람이 직접 작성한다.
3. seed sample을 기반으로 synthetic sample을 생성한다.
4. synthetic sample을 자동 필터링한다.
5. 사람이 label mismatch와 shortcut pattern을 검수한다.
6. hard negative sample을 만든다.
7. train/valid/test를 70/15/15로 나눈다.
8. 같은 template에서 나온 sample은 같은 split에만 넣는다.
9. hard_eval은 train에 절대 넣지 않는다.
10. Qwen embedding을 추출한다.
11. One-vs-Rest classifier를 학습한다.
12. validation set으로 label별 threshold를 보정한다.
13. precision/recall/F1을 평가한다.
14. false positive/false negative를 error bank에 기록한다.
15. model artifact와 threshold를 저장한다.
16. 고정 hard_eval을 통과해야 model replacement를 허용한다.
17. OCR fixture dataset을 생성하고 OCR parser/policy test를 실행한다.

### 21.4 Dataset Constraints

- real PII 사용 금지
- real secret 사용 금지
- 실제 회사명/고객명 대신 가상 protected target 사용
- 같은 protected target은 normal/risky 예시에 모두 등장해야 함
- Korean/English/mixed 예시를 모두 포함
- placeholder만 반복하는 sample 제거
- label 이름이 text에 직접 드러나는 shortcut sample 제거
- hard_eval sample은 train에 들어갈 수 없음

### 21.5 Dataset Row Format

Context dataset row:

```json
{
  "id": "ctx_contract_001",
  "text": "가상회사 A와 체결한 공급 단가 조건을 요약해줘.",
  "labels": ["CONTRACT_INFO"],
  "language": "ko",
  "source_type": "synthetic",
  "notes": "contract terms request with protected target"
}
```

PII relevance row:

```json
{
  "id": "pii_phone_example_001",
  "segment_text": "전화번호 형식은 010-1234-5678처럼 작성합니다.",
  "pii_type": "phone",
  "label": "example_or_format",
  "language": "ko"
}
```

Code sensitivity row:

```json
{
  "id": "code_auth_001",
  "code_text": "def verify_token(token): ...",
  "labels": ["CODE_SECURITY_CRITICAL_LOGIC"],
  "language": "python",
  "source_type": "synthetic"
}
```

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

### E. Analysis Pipeline

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| E1 | signal scanner interface | Interface | SignalScanner | signal list returned |
| E2 | PII scanner | Detector | PII signals | no-hyphen phone detected |
| E3 | secret scanner | Detector | secret signals | known formats detected |
| E4 | fingerprint scanner | Detector | HMAC matcher | exact registered secret detected |
| E5 | token candidate extractor | Detector | candidates | unknown tokens extracted |
| E6 | protected target matcher | Detector | target signals | canonical match works |
| E7 | custom regex scanner | Detector | regex signals | custom rule works |
| E8 | atom builder | Segment prep | atoms | fixture atoms stable |
| E9 | atom embedding worker | ML infra | embeddings | batch works |
| E10 | semantic dynamic chunker | Chunker | segments | boundary tests pass |
| E11 | signal mapper | Mapper | segment signals | no re-scan occurs |
| E12 | pipeline integration | Test | full fixture | end-to-end pass |

### F. ML Runtime and Dataset

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| F1 | Qwen embedding service | ML runtime | singleton loader | no per-request load |
| F2 | micro-batching queue | ML runtime | queue | batch latency measured |
| F3 | context classifier | Model | joblib/model | eval report exists |
| F4 | PII relevance classifier | Model | joblib/model | eval report exists |
| F5 | code classifier | Model | joblib/model | eval report exists |
| F6 | dataset seeds | Dataset | seed csv/jsonl | per-label minimum met |
| F7 | synthetic generation | Dataset | synthetic jsonl | auto filter applied |
| F8 | hard eval | Dataset | hard_eval jsonl | excluded from train |
| F9 | calibration | Model | thresholds.json | per-label threshold set |
| F10 | regression eval | Test | report | release gate pass |

### G. Gemma Judge

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| G1 | judge runner | ML runtime | runner | E4B judge callable |
| G2 | judge prompt | Prompt contract | template | JSON-only prompt fixed |
| G3 | judge schema | Schema | Pydantic model | validation works |
| G4 | parse/repair | Service | parser | malformed JSON fallback |
| G5 | judge queue | Runtime | bounded queue | timeout handled |
| G6 | reason mapping | Policy | enum mapping | invalid reason ignored |

### H. Policy and Events

| ID | Task | Boundary | Output | Done |
|---|---|---|---|---|
| H1 | policy engine | Service | PolicyOrchestrator | action priority tested |
| H2 | user notice templates | UX contract | templates | notices generated |
| H3 | admin summary templates | Dashboard contract | templates | deterministic summaries |
| H4 | OCR policy | Policy | status rules | no-text allow in balanced |
| H5 | file policy | Policy | file action rules | file mask not produced |
| H6 | protected target modifier | Policy | modifier | target alone no action |
| H7 | strict/balanced config | Config | table | mode tests pass |
| H8 | event writer | Service | serializer | no raw text stored |
| H9 | event API extension | API | response | parser/ocr status included |
| H10 | privacy tests | Test | smoke | raw text not returned |
