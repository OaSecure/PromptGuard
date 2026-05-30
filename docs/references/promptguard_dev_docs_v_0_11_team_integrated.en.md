# PromptGuard Development Document Set v0.11 - Team Integrated

Date: 2026-05-30

This document is the v0.11 integrated contract based on `promptguard_dev_docs_v_0_10_team_integrated.en.md` and the Korean v0.11 source document. v0.10 remains valid for server, dashboard, auth, RBAC, privacy, and test principles unless this document explicitly overrides it. The v0.11 change is that browser-extension input must not be modeled as one raw prompt string. It must be modeled as typed input bundles that reflect real ChatGPT, Claude, and Gemini chat constraints.

## 1. v0.11 Priority And Scope

v0.11 takes precedence over v0.10 for these areas:

- extension input model
- `/prompts/analyze` request contract
- MVP status of `/files/analyze`
- paste, large paste, files/attachments, and image paste handling
- fail-closed or explicit warning policy for unscanned/unsupported input
- current main implementation status

v0.11 is not an implementation PR. It is the contract for the next implementation PRs.

| PR | Purpose | Main output |
| --- | --- | --- |
| PR0 | v0.11 development-document contract | this document |
| PR1 | extension typed input model | `AnalyzeInput[]` type and direct text send-read |
| PR2 | paste capture | `ClipboardEvent.clipboardData` capture for clipboard text and large paste |
| PR3 | attachment metadata detector | service DOM attachment chip/card metadata detection |
| PR4 | send/replay state guard | replay/fail-closed consistency based on typed input snapshots |
| PR5 | backend analyze input bundles | provisional schema where `/prompts/analyze` accepts `inputs[]` |
| PR6 | file handling absorption | absorb existing file preflight into the unified input bundle |

## 2. Product Constraints

This document uses official product documentation where available and marks unverified product behavior as UNKNOWN. External product behavior can change, so service smoke tests are the final authority for runtime behavior.

| Service | Direct text input | Long paste behavior | Paste-to-attachment threshold | File upload limit | PromptGuard implication | Evidence status |
| --- | --- | --- | --- | --- | --- | --- |
| ChatGPT | A textarea/contenteditable-like composer may exist, but DOM can change | Long text can become attachment state instead of composer text | Around 5k chars is treated as community/observed unless official docs confirm it | OpenAI Help: 512MB/file, 2M tokens for text/document, about 50MB for spreadsheets, about 20MB for images | Reading only textarea text can miss large paste/attachments | file limits OFFICIAL; paste threshold COMMUNITY/UNKNOWN |
| Claude | Chat composer and file uploads are supported | Length/context errors may occur | No official threshold confirmed | Anthropic Help describes Claude.ai document uploads and Files API limits separately | paste threshold is UNKNOWN; uploads need metadata and unsupported policy | upload limits OFFICIAL; auto-convert UNKNOWN |
| Gemini | Gemini Apps support files in prompts | context/window or too-large warnings may occur | No official threshold confirmed | Google Help: up to 10 supported files per prompt, video up to 2GB, other supported file types up to 100MB | textarea text cannot represent the full prompt state | upload limits OFFICIAL; auto-convert UNKNOWN |

References:

- OpenAI Help Center, File Uploads FAQ: <https://help.openai.com/en/articles/8555545-file-uploads-faq>
- Anthropic Help Center, Claude.ai document upload: <https://support.anthropic.com/en/articles/8241126-what-kinds-of-documents-can-i-upload-to-claude-ai>
- Anthropic Docs, Files API: <https://docs.anthropic.com/>
- Google Gemini Apps Help, Upload and analyse files: <https://support.google.com/gemini/answer/14903178>

## 3. v0.11 Input Model

MVP Analyze input is not one `prompt.text`. It is `inputs[]`.

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

Rules:

- `direct_text`: current text read from the composer at send time.
- `clipboard_text`: ordinary text read from paste-event capture before the target page mutates the DOM.
- `large_paste`: a large paste that is captured but not fully scanned. If the full raw text is not sent to the backend, the input must record `contentScanned=false` and a handling mode.
- `attachment_metadata`: file/attachment chip/card state represented as metadata only.
- `unsupported_attachment`: an attachment is visible but metadata is insufficient or the format is unsupported.
- `file_text`: only small policy-allowed text files in MVP.

Image paste does not mean image-content analysis. MVP does not perform OCR, pixel inspection, base64 payload scanning, or embedded EXIF scanning. Image paste is represented as `attachment_metadata` or `unsupported_attachment` when possible, and content is not marked as scanned.

## 4. `/prompts/analyze` v0.11 Contract

The MVP final Analyze API accepts a unified input bundle.

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

Contract:

- `/prompts/analyze` makes one decision across prompt text, paste, large-paste metadata, attachment metadata, and supported text-file content.
- The response must not store or echo raw prompt, raw clipboard text, raw file content, raw detected values, or original filenames.
- Validation errors must not echo raw input.
- Byte-oriented limit names are required. Character-oriented names such as `MAX_PROMPT_LENGTH` must be replaced in the final v0.11 contract by `MAX_DIRECT_TEXT_BYTES`, `MAX_CLIPBOARD_CAPTURE_BYTES`, `MAX_ANALYZE_REQUEST_BYTES`, and `MAX_FILE_CONTENT_SCAN_BYTES`.
- If an input with `contentScanned=false` is present, the response/event must explicitly record partial or unscanned state.

## 5. Status Of `/files/analyze`

The independent `/files/analyze` direction from v0.10 is absorbed into unified `/prompts/analyze inputs[]` for v0.11 MVP.

Policy:

- Do not expand `/files/analyze` as a new final decision endpoint.
- If existing extension code still uses it, treat it as a migration compatibility path only.
- PR6 absorbs existing `FILES_ANALYZE_REQUEST` / `FilesAnalyzeRequest` / `content_text` paths into unified input bundles.
- Removing an already documented capability requires separate user approval and compatibility review.

## 6. Extension Input Capture Contract

The extension collects input in this order:

1. On paste-event capture, inspect `ClipboardEvent.clipboardData` first.
2. After the target page handles paste, inspect whether the page converted it into composer text, attachment, image, or error state.
3. On send click/Enter, read current composer direct text and attachment metadata again.
4. Send `inputs[]` and an input-state snapshot instead of one raw prompt string.
5. After a decision, replay is allowed only when original state can be preserved.

Large paste handling:

- ChatGPT-style large paste can become an attachment, so reading only the textarea at send time is insufficient.
- Even if clipboard raw text is captured, full backend send is forbidden when it exceeds byte limits.
- If full scan is not possible, represent it as `large_paste` or `unsupported_attachment`.
- Block policy prevents native send. Warn policy must explicitly tell the user that the input is unscanned or partial.

File/attachment handling:

- File input `change`, drag/drop, and rendered attachment chip/card state are separate input kinds.
- MVP file content scanning is limited to small text files.
- PDF, Office, image, binary, ZIP, and Gemini repository deep scan are outside MVP.
- Unsupported/unscanned attachments must not silently allow. They must go through fail-closed or explicit Warn policy.

## 7. Replay Contract

Replay is a risky section because it re-executes a page action.

Allowed only when:

- Analyze decision is Allow, or the user explicitly confirms Warn.
- The replay target is prompt-text-only and the original composer state is equivalent to the send-time state.
- The replay bypass flag is scoped only to the replay call.

Forbidden or fail-closed when:

- Original input included an attachment but replay can only reinsert text.
- A large paste was converted to an attachment and only a text snapshot remains.
- The composer DOM node was replaced and current state does not match the snapshot.
- Replay would need to recreate a trusted file drop.

## 8. Current Main Status

Verification basis:

- repository: `promptguard_publish`
- branch: `main`
- commit: `4f9d099382b47e99604e2cdc6d906b1fab05c124`
- scan date: 2026-05-30
- note: the Korean input-capture reference was untracked at scan time before PR0 commit.

### 8.1 Completed

| Area | Status | Source trace |
| --- | --- | --- |
| MV3 extension shared Analyze types | `AnalyzeRequest`, `AnalyzeResponse`, `FilesAnalyzeRequest`, and `FilesAnalyzeResponse` exist | `apps/extension/src/shared/types.ts:31`, `apps/extension/src/shared/types.ts:54` |
| ChatGPT default domain/config | only CHATGPT service enum and default selectors exist | `apps/extension/src/shared/types.ts:6`, `apps/extension/src/shared/constants.ts:22`, `apps/extension/src/shared/constants.ts:23` |
| textarea/contenteditable prompt detection | textarea and `[contenteditable='true']` candidates are detected | `apps/extension/src/content/domDetector.ts:27`, `apps/extension/src/content/promptExtractor.ts:10`, `apps/extension/src/content/promptExtractor.ts:26` |
| click/Enter native send preflight | capture-phase click/keydown listeners block native send first | `apps/extension/src/content/sendInterceptor.ts:67`, `apps/extension/src/content/sendInterceptor.ts:103`, `apps/extension/src/content/promptPreflightController.ts:75` |
| Allow/Warn/Mask/Block UX | overlay/replay/mask/block paths exist per prompt decision | `apps/extension/src/content/promptPreflightController.ts:105`, `apps/extension/src/content/promptPreflightController.ts:130`, `apps/extension/src/content/promptPreflightController.ts:142`, `apps/extension/src/content/promptPreflightController.ts:160` |
| replay loop guard | `replaying` bypass flag is scoped to replay | `apps/extension/src/content/promptPreflightController.ts:53`, `apps/extension/src/content/promptPreflightController.ts:180` |
| file input/drop interception | file input change and drop capture listeners exist | `apps/extension/src/content/fileUploadInterceptor.ts:29`, `apps/extension/src/content/fileUploadInterceptor.ts:69`, `apps/extension/src/content/fileUploadInterceptor.ts:70` |
| file policy before read | file count/size/extension/MIME policy runs before `File.text()` | `apps/extension/src/shared/filePolicy.ts:24`, `apps/extension/src/shared/filePolicy.ts:30`, `apps/extension/src/shared/filePolicy.ts:43` |
| safe validation handler | FastAPI `RequestValidationError` handler exists | `apps/api/app/main.py:23` |
| authenticated `/prompts/analyze` route | FastAPI route registration and OpenAPI test exist | `apps/api/app/routes/analyze.py:19`, `apps/api/app/routes/analyze.py:68`, `apps/api/app/main.py:47`, `apps/api/tests/test_analyze.py:134` |
| response/error raw-free regression tests | success and validation responses do not echo raw prompt/context values | `apps/api/tests/test_analyze.py:114`, `apps/api/tests/test_analyze.py:141` |
| deterministic PII detectors | EMAIL/PHONE/RRN/CARD detectors and raw-free tests exist | `apps/api/app/detectors/pii.py:36`, `apps/api/tests/test_pii_detectors.py:132` |
| masking helper | placeholder masking helper and raw-free metadata tests exist | `apps/api/app/masking/placeholder.py:65`, `apps/api/tests/test_masking.py:44` |
| prompt hash helper | prompt hash helper and raw-free test exist | `apps/api/app/core/prompt_hash.py:22`, `apps/api/tests/test_prompt_hash.py:72` |
| admin users API | `/admin/users` route and self-lockout regression exist | `apps/api/app/routes/admin_users.py:17`, `apps/api/tests/test_admin_users.py:245` |

### 8.2 Partial

| Area | Status | Source trace |
| --- | --- | --- |
| extension real API integration | background clients call real API paths, but not the v0.11 `inputs[]` contract | `apps/extension/src/background/promptAnalyzeClient.ts:12`, `apps/extension/src/background/fileAnalyzeClient.ts:12` |
| backend `/prompts/analyze` | route exists, but it is a provisional `prompt: str` boundary and always returns `ALLOW` | `apps/api/app/routes/analyze.py:16`, `apps/api/app/routes/analyze.py:68` |
| size limits | backend prompt/context limits are character/json-string length based, not byte based | `apps/api/app/routes/analyze.py:12`, `apps/api/app/routes/analyze.py:13`, `apps/api/app/routes/analyze.py:16`, `apps/api/app/routes/analyze.py:33` |
| file upload preflight | small text-file read and `/files/analyze` path exist, but are not absorbed into unified input bundles | `apps/extension/src/content/textFileReader.ts:12`, `apps/extension/src/background/fileAnalyzeClient.ts:17` |
| raw file handling | original filename is omitted, but text `content_text` is sent through a separate file path | `apps/extension/src/content/fileUploadPreflightController.ts:179`, `apps/extension/src/content/textFileReader.ts:29` |
| service adapters | only CHATGPT config exists; Claude/Gemini typed adapters do not exist | `apps/extension/src/shared/types.ts:6`, `apps/extension/src/shared/configValidation.ts:30` |

### 8.3 Not Done

| Area | Status | Negative/source trace |
| --- | --- | --- |
| unified `AnalyzeInput[]` | current shared/API request has no `inputs[]` | `apps/extension/src/shared/types.ts:31`; `apps/api/app/routes/analyze.py:16` |
| paste event capture | no `paste`/`clipboardData` capture path exists | `rg -n "paste|clipboardData" apps/extension/src` found no implementation match in PR0 source scan |
| large paste model | no `large_paste` kind exists | `rg -n "large_paste|MAX_CLIPBOARD_CAPTURE_BYTES" apps/extension/src apps/api` expected no match |
| attachment chip/card detector | no rendered attachment DOM detector exists | only file input/drop traces found: `apps/extension/src/content/fileUploadInterceptor.ts:29` |
| image paste metadata | no path represents image paste as metadata-only input | no paste/clipboard implementation in source scan |
| unsupported attachment fail-closed | no attachment chip/card unsupported-state model exists | no `unsupported_attachment` kind in source scan |
| replay state preservation | replay is current send-button click/keyboard dispatch; no typed input snapshot equality | `apps/extension/src/content/sendInterceptor.ts:120`, `apps/extension/src/content/promptPreflightController.ts:180` |
| byte-based Analyze request limit | backend uses Python `len()` and JSON string length, not UTF-8 byte limit | `apps/api/app/routes/analyze.py:12`, `apps/api/app/routes/analyze.py:33`, `apps/api/app/routes/analyze.py:88` |
| idempotency persistence | `client_request_id` is only echoed; no durable idempotency store exists | `apps/api/app/routes/analyze.py:23`, `apps/api/app/routes/analyze.py:90` |
| event persistence | analyze route does not persist event records | `apps/api/app/routes/analyze.py:68` |
| real service smoke for ChatGPT/Claude/Gemini | repository tests use unit/e2e fixtures, not live service smoke | `apps/extension/tests/e2e/extension.spec.ts:61` fixture-based message handling |

## 9. Security And Privacy Contract

Forbidden:

- storing raw prompt
- storing raw clipboard text
- storing raw file content
- storing raw detected value
- storing original filename
- echoing raw input in validation errors
- printing raw input in browser console or debug logs
- persisting raw text in event records

Allowed:

- transient direct/clipboard/file text in the Analyze request body only after v0.11 byte limits and policy pass.
- metadata-only attachment state.
- HMAC/hash-based correlation ids.
- masked output may be shown/applied to the user, but must not be stored in events/logs as raw substitute text.

## 10. MVP Exclusions

These are outside v0.11 MVP:

- OCR
- image content analysis
- PDF parsing
- Office document parsing
- binary parsing
- ZIP unpacking
- malware scanning
- Gemini GitHub repository deep scan
- confirmed Claude/Gemini long-paste auto-attachment thresholds
- service private API usage

UNKNOWN behavior must not be documented as confirmed until official docs or manual browser smoke tests verify it.

## 11. Required Tests

PR1 through PR6 must add these tests across the relevant implementation slices:

- typed prompt direct text: textarea/contenteditable text becomes `direct_text`.
- normal paste: paste event captures `clipboard_text` and reconciles after DOM mutation.
- ChatGPT-style large paste: a fixture where 5k+ text becomes attachment-like DOM must not allow based only on raw textarea state.
- paste-before-DOM-mutation: capture-phase test reads `ClipboardEvent.clipboardData` before the target page handler.
- file input metadata: preserve extension/MIME/size/count without original filename.
- drag/drop metadata: if trusted drop replay is impossible, fail closed or use manual reattach path.
- image paste: represent raw image/base64/OCR-free metadata-only or unsupported input.
- unsupported attachment fail-closed: unscanned attachment must not silently allow.
- large input over limit: full backend send is blocked and metadata/partial state remains.
- replay loop prevention: replay bypass is one-shot and a user retry is inspected again.
- replay state preservation: attachment state is not lost by text-only replay.
- privacy regression: logs/errors/events/tests/snapshots do not include raw prompt, clipboard text, file content, filename, or detected raw value.

## 12. PR0 Completion Criteria

PR0 is complete when these grep checks pass:

```bash
rg -n "v0.11|/prompts/analyze|/files/analyze|inputs\\[\\]|AnalyzeInput" docs/references/promptguard_dev_docs_v_0_11_team_integrated.en.md
rg -n "direct_text|clipboard_text|large_paste|attachment_metadata|unsupported_attachment|file_text" docs/references/promptguard_dev_docs_v_0_11_team_integrated.en.md
rg -n "OCR|PDF|Office|binary|ZIP|GitHub repository deep scan|outside v0.11 MVP|MVP Exclusions" docs/references/promptguard_dev_docs_v_0_11_team_integrated.en.md
rg -n "Current Main Status|Completed|Partial|Not Done|Source trace" docs/references/promptguard_dev_docs_v_0_11_team_integrated.en.md
```
