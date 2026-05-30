# PromptGuard 개발 문서 세트 v0.11 - 팀 통합본

작성일: 2026-05-30

이 문서는 `promptguard_dev_docs_v_0_10_team_integrated.ko.md`를 기준으로 하는 v0.11 통합 계약이다. v0.10에서 여전히 맞는 서버, 대시보드, 인증, RBAC, privacy, 테스트 원칙은 유지한다. v0.11의 변경 핵심은 브라우저 확장앱 입력을 단일 raw prompt 문자열로 보지 않고, 실제 ChatGPT/Claude/Gemini 입력 제약에 맞는 typed input bundle로 다루는 것이다.

## 1. v0.11 우선순위와 범위

v0.11이 v0.10보다 우선하는 영역은 다음이다.

- 확장앱 입력 모델
- `/prompts/analyze` 요청 계약
- `/files/analyze`의 MVP 내 지위
- 붙여넣기, 대용량 붙여넣기, 파일/첨부파일, 이미지 붙여넣기 처리
- unscanned/unsupported input에 대한 fail-closed 또는 명시적 warning 정책
- 현재 main 구현 상태

v0.11은 코드 구현 PR이 아니다. 이 문서는 다음 PR들의 기준 계약이다.

| PR | 목적 | 주요 산출물 |
| --- | --- | --- |
| PR0 | v0.11 개발문서 계약 | 이 문서 |
| PR1 | 확장앱 typed input model | `AnalyzeInput[]` 타입과 direct text send-read |
| PR2 | paste capture | `ClipboardEvent.clipboardData` 기반 clipboard text/large paste 캡처 |
| PR3 | attachment metadata detector | 서비스 DOM에 렌더된 첨부 chip/card metadata 감지 |
| PR4 | send/replay state guard | typed input snapshot 기반 replay/fail-closed 정합성 |
| PR5 | backend analyze input bundles | `/prompts/analyze`가 `inputs[]`를 받는 provisional schema |
| PR6 | file handling absorption | 기존 file preflight를 unified input bundle로 흡수 |

## 2. 제품 제약 반영

이 문서는 2026-05-30 기준 공식 문서와 현재 코드 확인을 함께 사용한다. 외부 제품 동작은 변할 수 있으므로 service smoke test가 최종 권위다.

| Service | 직접 입력 | 긴 붙여넣기 | 붙여넣기-첨부 전환 threshold | 파일 업로드 제한 | PromptGuard 영향 | Evidence status |
| --- | --- | --- | --- | --- | --- | --- |
| ChatGPT | textarea/contenteditable 계열 composer가 존재할 수 있으나 DOM은 변경 가능 | 긴 텍스트가 composer text가 아니라 attachment 상태가 될 수 있음 | 약 5k chars는 community/observed constraint로 취급. 공식 문서로 확인하지 못하면 UNKNOWN으로 표기 | OpenAI Help: file 512MB, text/document 2M tokens, spreadsheet 약 50MB, image 약 20MB | textarea text만 읽으면 대용량 paste/attachment를 놓칠 수 있음 | file limits OFFICIAL; paste threshold COMMUNITY/UNKNOWN |
| Claude | chat composer와 file upload 지원 | 길이 제한/컨텍스트 제한 오류 가능 | 공식 threshold 확인 못함 | Anthropic Help는 Claude.ai 문서 업로드 20 files/chat 및 계정/문서별 size limit을 설명함. Anthropic Files API는 별도 500MB/file API surface | paste threshold는 UNKNOWN, upload/file은 metadata와 unsupported policy 필요 | upload limits OFFICIAL; auto-convert UNKNOWN |
| Gemini | Gemini Apps prompt에 파일 첨부 가능 | context/window limit 또는 too-large warning 가능 | 공식 threshold 확인 못함 | Google Help: prompt당 최대 10 supported files, video 2GB, 그 외 supported file 100MB | textarea text만으로는 prompt 전체를 모델링할 수 없음 | upload limits OFFICIAL; auto-convert UNKNOWN |

참고 공식 문서:

- OpenAI Help Center, File Uploads FAQ: <https://help.openai.com/en/articles/8555545-file-uploads-faq>
- Anthropic Help Center, Claude.ai document upload: <https://support.anthropic.com/en/articles/8241126-what-kinds-of-documents-can-i-upload-to-claude-ai>
- Anthropic Docs, Files API: <https://docs.anthropic.com/>
- Google Gemini Apps Help, Upload and analyse files: <https://support.google.com/gemini/answer/14903178>

## 3. v0.11 입력 모델

MVP Analyze 입력은 하나의 `prompt.text`가 아니라 `inputs[]`다.

```ts
type AnalyzeInput =
  | {
      kind: "direct_text";
      text: string;
      byteLength: number;
      source: "typed" | "send_read";
      contentScanned: true;
    }
  | {
      kind: "clipboard_text";
      text: string;
      byteLength: number;
      source: "paste_event";
      contentScanned: true;
    }
  | {
      kind: "large_paste";
      byteLength: number;
      textHash: string;
      sample?: {
        prefix: string;
        suffix: string;
      };
      contentScanned: boolean;
      handling: "blocked" | "warned" | "metadata_only" | "full_local_scan";
    }
  | {
      kind: "attachment_metadata";
      files: Array<{
        name?: string;
        size: number;
        type?: string;
        extension?: string;
      }>;
      contentScanned: false;
    }
  | {
      kind: "unsupported_attachment";
      reason: string;
      contentScanned: false;
    }
  | {
      kind: "file_text";
      clientFileId: string;
      extension: string;
      mimeType: string;
      sizeBytes: number;
      text: string;
      byteLength: number;
      contentScanned: true;
    };
```

규칙:

- `direct_text`: send 시점 composer에서 읽은 현재 직접 텍스트.
- `clipboard_text`: paste event capture 단계에서 target page가 DOM을 변형하기 전에 읽은 일반 텍스트.
- `large_paste`: capture 가능하지만 full scan하지 않는 대용량 paste. raw 전체를 서버로 보내지 않는 경우 반드시 `contentScanned=false`와 handling을 남긴다.
- `attachment_metadata`: 파일/첨부 chip/card 상태를 metadata로만 표현한다.
- `unsupported_attachment`: DOM에는 첨부가 보이지만 metadata가 부족하거나 지원하지 않는 형식이다.
- `file_text`: MVP에서 정책상 허용된 작은 text file만 해당한다.

이미지 붙여넣기는 이미지 내용을 분석하지 않는다. MVP는 OCR, pixel inspection, base64 payload scan, embedded EXIF scan을 하지 않는다. 이미지 paste는 가능하면 `attachment_metadata` 또는 `unsupported_attachment`로 표현하고, content는 scanned로 표시하지 않는다.

## 4. `/prompts/analyze` v0.11 계약

MVP 최종 Analyze API는 unified input bundle을 받는다.

```json
{
  "inputs": [
    {
      "kind": "direct_text",
      "text": "hello",
      "byteLength": 5,
      "source": "send_read",
      "contentScanned": true
    }
  ],
  "context": {
    "ai_service": "CHATGPT",
    "page_url_origin": "https://chatgpt.com",
    "extension_version": "0.0.0"
  },
  "filter_config_version": "default",
  "client_request_id": "uuid"
}
```

계약:

- `/prompts/analyze`는 text prompt, paste, large paste metadata, attachment metadata, supported text-file content를 하나의 decision으로 판단한다.
- response는 raw prompt, raw clipboard text, raw file content, raw detected values, original filenames를 저장 또는 echo하지 않는다.
- validation error도 raw input을 echo하지 않는다.
- byte-oriented limit 이름을 사용한다. `MAX_PROMPT_LENGTH` 같은 character 기반 이름은 v0.11 최종 계약에서 `MAX_DIRECT_TEXT_BYTES`, `MAX_CLIPBOARD_CAPTURE_BYTES`, `MAX_ANALYZE_REQUEST_BYTES`, `MAX_FILE_CONTENT_SCAN_BYTES`로 대체한다.
- `contentScanned=false` input이 포함된 경우 response/event는 partial 또는 unscanned 상태를 명시해야 한다.

## 5. `/files/analyze` 지위

v0.10의 독립 `/files/analyze` 방향은 v0.11 MVP에서 unified `/prompts/analyze inputs[]`로 흡수한다.

정책:

- `/files/analyze`를 새 최종 decision endpoint로 확장하지 않는다.
- 기존 확장앱 코드가 사용 중이면 migration compatibility path로만 취급한다.
- PR6에서 기존 `FILES_ANALYZE_REQUEST`/`FilesAnalyzeRequest`/`content_text` 경로를 unified input bundle로 흡수한다.
- 이미 문서화된 capability를 실제 제거해야 하는 경우에는 별도 사용자 승인과 compatibility 판단이 필요하다.

## 6. 확장앱 입력 캡처 계약

확장앱은 다음 순서로 입력을 수집한다.

1. paste event capture에서 `ClipboardEvent.clipboardData`를 먼저 확인한다.
2. target page가 paste를 composer text, attachment, image, error state 중 무엇으로 바꾸는지 mutation/DOM snapshot으로 확인한다.
3. send click/Enter 시점에는 현재 composer direct text와 attachment metadata를 다시 읽는다.
4. Analyze request에는 raw text만 있는 단일 prompt 대신 `inputs[]`와 input 상태 snapshot을 보낸다.
5. decision 후 replay는 original state가 보존되는 경우에만 허용한다.

대용량 paste 처리:

- ChatGPT식 large paste가 attachment로 전환될 수 있으므로, send 시점 textarea만 읽는 방식은 불충분하다.
- clipboard raw text를 읽었더라도 byte limit을 넘으면 full backend send를 금지한다.
- full scan하지 못한 경우 `large_paste` 또는 `unsupported_attachment`로 표현한다.
- 정책이 Block이면 native send를 막는다. Warn이면 사용자에게 unscanned/partial 상태를 명시한다.

파일/첨부 처리:

- file input `change`, drag/drop, rendered attachment chip/card를 별도 input kind로 모델링한다.
- MVP에서 file content scan은 작은 text file만 허용한다.
- PDF, Office, image, binary, ZIP, Gemini repository deep scan은 MVP 밖이다.
- unsupported/unscanned attachment는 silent allow가 아니라 fail-closed 또는 explicit Warn 정책을 탄다.

## 7. Replay 계약

Replay는 page action을 자동으로 다시 실행하는 위험한 구간이다.

허용 조건:

- Analyze decision이 Allow이거나 사용자가 Warn을 명시적으로 계속하기로 했다.
- replay 대상이 prompt text only이고, original composer state가 send 시점과 동등함을 확인했다.
- replay bypass flag는 replay 호출 동안만 켜진다.

금지 또는 fail-closed 조건:

- original input에 attachment가 있었는데 replay가 text만 재주입할 수 있는 경우.
- large paste가 page에서 attachment로 전환된 뒤 text snapshot만 남은 경우.
- DOM composer node가 교체되어 snapshot과 현재 state가 불일치하는 경우.
- replay가 trusted file drop을 재현해야 하는 경우.

## 8. 현재 main 구현 상태

검증 기준:

- repository: `promptguard_publish`
- branch: `main`
- commit: `4f9d099382b47e99604e2cdc6d906b1fab05c124`
- scan date: 2026-05-30
- working tree note: `docs/references/promptguard_input_capture_attachment_model_2026-05-30.ko.md` is untracked at scan time.

### 8.1 Completed

| 영역 | 상태 | Source trace |
| --- | --- | --- |
| MV3 extension shared Analyze types | `AnalyzeRequest`, `AnalyzeResponse`, `FilesAnalyzeRequest`, `FilesAnalyzeResponse` 존재 | `apps/extension/src/shared/types.ts:31`, `apps/extension/src/shared/types.ts:54` |
| ChatGPT default domain/config | CHATGPT만 service enum 및 default selectors 존재 | `apps/extension/src/shared/types.ts:6`, `apps/extension/src/shared/constants.ts:22`, `apps/extension/src/shared/constants.ts:23` |
| textarea/contenteditable prompt detection | textarea와 `[contenteditable='true']` 후보 탐지 | `apps/extension/src/content/domDetector.ts:27`, `apps/extension/src/content/promptExtractor.ts:10`, `apps/extension/src/content/promptExtractor.ts:26` |
| click/Enter native send preflight | capture-phase click/keydown listener로 native send를 먼저 막음 | `apps/extension/src/content/sendInterceptor.ts:67`, `apps/extension/src/content/sendInterceptor.ts:103`, `apps/extension/src/content/promptPreflightController.ts:75` |
| Allow/Warn/Mask/Block UX | prompt decision별 overlay/replay/mask/block 흐름 존재 | `apps/extension/src/content/promptPreflightController.ts:105`, `apps/extension/src/content/promptPreflightController.ts:130`, `apps/extension/src/content/promptPreflightController.ts:142`, `apps/extension/src/content/promptPreflightController.ts:160` |
| replay loop guard | `replaying` bypass flag가 replay 호출 동안만 켜짐 | `apps/extension/src/content/promptPreflightController.ts:53`, `apps/extension/src/content/promptPreflightController.ts:180` |
| file input/drop interception | file input change와 drop capture listener 존재 | `apps/extension/src/content/fileUploadInterceptor.ts:29`, `apps/extension/src/content/fileUploadInterceptor.ts:69`, `apps/extension/src/content/fileUploadInterceptor.ts:70` |
| file policy before read | file count/size/extension/MIME policy를 `File.text()` 전에 검사 | `apps/extension/src/shared/filePolicy.ts:24`, `apps/extension/src/shared/filePolicy.ts:30`, `apps/extension/src/shared/filePolicy.ts:43` |
| safe validation handler | FastAPI `RequestValidationError` handler 존재 | `apps/api/app/main.py:23` |
| authenticated `/prompts/analyze` route | FastAPI route 등록 및 OpenAPI 테스트 존재 | `apps/api/app/routes/analyze.py:19`, `apps/api/app/routes/analyze.py:68`, `apps/api/app/main.py:47`, `apps/api/tests/test_analyze.py:134` |
| response/error raw-free regression tests | success/validation response가 raw prompt/context를 echo하지 않는 테스트 존재 | `apps/api/tests/test_analyze.py:114`, `apps/api/tests/test_analyze.py:141` |
| deterministic PII detectors | EMAIL/PHONE/RRN/CARD detector와 raw-free test 존재 | `apps/api/app/detectors/pii.py:36`, `apps/api/tests/test_pii_detectors.py:132` |
| masking helper | placeholder masking helper와 raw-free metadata test 존재 | `apps/api/app/masking/placeholder.py:65`, `apps/api/tests/test_masking.py:44` |
| prompt hash helper | prompt hash helper와 raw-free test 존재 | `apps/api/app/core/prompt_hash.py:22`, `apps/api/tests/test_prompt_hash.py:72` |
| admin users API | `/admin/users` route와 self-lockout regression 존재 | `apps/api/app/routes/admin_users.py:17`, `apps/api/tests/test_admin_users.py:245` |

### 8.2 Partial

| 영역 | 상태 | Source trace |
| --- | --- | --- |
| extension real API integration | background client는 real API path를 호출하지만 contract가 v0.11 `inputs[]`가 아님 | `apps/extension/src/background/promptAnalyzeClient.ts:12`, `apps/extension/src/background/fileAnalyzeClient.ts:12` |
| backend `/prompts/analyze` | route는 존재하지만 `prompt: str` provisional boundary이고 항상 `ALLOW` | `apps/api/app/routes/analyze.py:16`, `apps/api/app/routes/analyze.py:68` |
| size limits | backend prompt/context limit은 character/json-string length 기반. v0.11 byte contract 아님 | `apps/api/app/routes/analyze.py:12`, `apps/api/app/routes/analyze.py:13`, `apps/api/app/routes/analyze.py:16`, `apps/api/app/routes/analyze.py:33` |
| file upload preflight | small text file read and `/files/analyze` path는 있으나 unified input bundle로 흡수 전 | `apps/extension/src/content/textFileReader.ts:12`, `apps/extension/src/background/fileAnalyzeClient.ts:17` |
| raw file handling | original filename을 request에서 제외하려는 구조는 있으나 text `content_text`를 separate files path로 보냄 | `apps/extension/src/content/fileUploadPreflightController.ts:179`, `apps/extension/src/content/textFileReader.ts:29` |
| service adapters | CHATGPT config만 존재. Claude/Gemini typed adapter 없음 | `apps/extension/src/shared/types.ts:6`, `apps/extension/src/shared/configValidation.ts:30` |

### 8.3 Not Done

| 영역 | 상태 | Negative/source trace |
| --- | --- | --- |
| unified `AnalyzeInput[]` | 현재 shared/API request에 `inputs[]` 없음 | `apps/extension/src/shared/types.ts:31`; `apps/api/app/routes/analyze.py:16` |
| paste event capture | `paste`/`clipboardData` capture path 없음 | `rg -n "paste|clipboardData" apps/extension/src` returned no implementation match in PR0 source scan |
| large paste model | `large_paste` kind 없음 | `rg -n "large_paste|MAX_CLIPBOARD_CAPTURE_BYTES" apps/extension/src apps/api` expected no match |
| attachment chip/card detector | rendered attachment DOM detector 없음 | only file input/drop traces found: `apps/extension/src/content/fileUploadInterceptor.ts:29` |
| image paste metadata | image paste를 metadata-only input으로 표현하는 path 없음 | no paste/clipboard implementation in source scan |
| unsupported attachment fail-closed | attachment chip/card unsupported state 모델 없음 | no `unsupported_attachment` kind in source scan |
| replay state preservation | replay는 current send button click/keyboard dispatch 중심이고 typed input snapshot equality 없음 | `apps/extension/src/content/sendInterceptor.ts:120`, `apps/extension/src/content/promptPreflightController.ts:180` |
| byte-based Analyze request limit | backend uses Python `len()` and JSON string length, not UTF-8 byte limit | `apps/api/app/routes/analyze.py:12`, `apps/api/app/routes/analyze.py:33`, `apps/api/app/routes/analyze.py:88` |
| idempotency persistence | `client_request_id` echo only, durable idempotency store 없음 | `apps/api/app/routes/analyze.py:23`, `apps/api/app/routes/analyze.py:90` |
| event persistence | analyze route does not persist event records | `apps/api/app/routes/analyze.py:68` |
| real service smoke for ChatGPT/Claude/Gemini | repository tests are unit/e2e fixtures, not live service smoke | `apps/extension/tests/e2e/extension.spec.ts:61` fixture-based message handling |

## 9. 보안·개인정보 계약

금지:

- raw prompt 저장
- raw clipboard text 저장
- raw file content 저장
- raw detected value 저장
- original filename 저장
- validation error에 raw input echo
- browser console/debug log에 raw input 출력
- event persistence에 raw text 저장

허용:

- transient Analyze request body에 direct/clipboard/file text를 포함하는 것. 단, v0.11 byte limit과 policy를 통과한 경우에 한한다.
- metadata-only attachment state.
- HMAC/hash 기반 correlation id.
- masked output은 사용자에게 적용/표시될 수 있으나 event/log에는 raw substitute로 저장하지 않는다.

## 10. MVP 제외

다음은 v0.11 MVP 밖이다.

- OCR
- 이미지 내용 분석
- PDF parsing
- Office document parsing
- binary parsing
- ZIP unpacking
- malware scanning
- Gemini GitHub repository deep scan
- Claude/Gemini long-paste auto-attachment threshold 확정
- service private API 사용

UNKNOWN으로 남는 항목은 공식 문서 또는 수동 브라우저 smoke로 확인되기 전까지 문서에서 확정 사실로 쓰지 않는다.

## 11. 테스트 요구

PR1~PR6는 아래 테스트를 나눠 구현해야 한다.

- typed prompt direct text: textarea/contenteditable text가 `direct_text`로 변환된다.
- normal paste: paste event에서 `clipboard_text`를 캡처하고 DOM mutation 이후 state와 reconcile한다.
- ChatGPT-style large paste: 5k+ text가 attachment-like DOM으로 바뀌는 fixture에서 raw textarea만으로 allow하지 않는다.
- paste-before-DOM-mutation: `ClipboardEvent.clipboardData`를 target page handler보다 먼저 읽는 capture-phase test.
- file input metadata: original filename 없이 extension/MIME/size/count만 유지한다.
- drag/drop metadata: trusted drop replay 불가 시 fail-closed 또는 manual reattach path를 탄다.
- image paste: raw image/base64/OCR 없이 metadata-only 또는 unsupported input으로 표현한다.
- unsupported attachment fail-closed: unscanned attachment가 silent allow되지 않는다.
- large input over limit: full backend send가 차단되고 metadata/partial state가 남는다.
- replay loop prevention: replay bypass는 one-shot이고 사용자 재시도는 다시 inspection된다.
- replay state preservation: attachment 포함 state는 text-only replay로 손실되지 않는다.
- privacy regression: logs/errors/events/tests/snapshots에 raw prompt, clipboard text, file content, filename, detected raw value가 없다.

## 12. PR0 완료 기준

PR0은 다음 grep이 통과해야 완료로 본다.

```bash
rg -n "v0.11|/prompts/analyze|/files/analyze|inputs\\[\\]|AnalyzeInput" promptguard_publish/docs/references
rg -n "direct_text|clipboard_text|large_paste|attachment_metadata|unsupported_attachment|file_text" promptguard_publish/docs/references
rg -n "OCR|PDF|Office|binary|ZIP|GitHub repository deep scan|MVP 밖|MVP 제외" promptguard_publish/docs/references
rg -n "Current main status|현재 main|Completed|Partial|Not done|완료|부분|안됨|Verification trace|Source trace" promptguard_publish/docs/references
```
