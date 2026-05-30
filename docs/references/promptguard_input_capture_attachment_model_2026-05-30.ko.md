# PromptGuard 입력 캡처와 Attachment 처리 모델

작성일: 2026-05-30

## 목적

이 문서는 PromptGuard 확장앱이 ChatGPT, Claude, Gemini 같은 실제 채팅 서비스에서 사용자 입력을 안전하게 분석하기 위한 입력 캡처 모델을 정의한다.

핵심 전제는 다음과 같다.

- 사용자가 보내려는 입력은 항상 하나의 `prompt.text` 문자열이 아니다.
- 붙여넣기 입력은 target 페이지가 처리하기 전에 clipboard payload를 먼저 확인해야 한다.
- 붙여넣기 이후에는 target 페이지가 만든 composer DOM, attachment chip/card, file input 상태를 다시 확인해야 한다.
- 이미지 paste나 binary attachment의 내용 분석은 MVP 범위가 아니다. 내용 스캔을 시도하지 말고 metadata-only로 감지한 뒤 `contentScanned: false`로 표현한다.

## 현재 위험

현재 extension MVP는 textarea/contenteditable의 현재 텍스트를 읽고 send를 preflight하는 구조다. 이 구조는 일반 typed text에는 동작할 수 있지만, 다음 입력을 안전하게 표현하지 못한다.

- large paste가 target 서비스에 의해 attachment로 변환되는 경우
- 이미지가 clipboard paste로 들어오는 경우
- 이미 composer에 렌더된 attachment chip/card가 있는 경우
- file input 또는 drag/drop 이벤트를 extension이 놓친 뒤 attachment만 남아 있는 경우
- Claude/Gemini처럼 서비스별 upload/card DOM이 다른 경우

따라서 "send 직전에 composer text만 읽는 방식"은 full input scanned 상태를 보장하지 못한다.

## 입력 캡처 원칙

### 1. Paste 이벤트 선점

확장앱은 capture phase에서 `paste` 이벤트를 관찰해야 한다.

이 단계에서 확인할 정보:

- `event.clipboardData.getData("text/plain")`의 존재 여부
- UTF-8 byte length
- configured clipboard capture limit 초과 여부
- `event.clipboardData.items` 또는 `files`에 포함된 file/image item metadata
- text hash 또는 request-local id

주의:

- clipboard에 있는 raw text는 request 처리 중 transient input으로만 사용한다.
- raw clipboard text는 console, log, DB, dashboard, error response, memory/session log에 남기지 않는다.
- large paste는 무조건 textarea에 들어간다고 가정하지 않는다.

### 2. Paste 이후 DOM 재확인

target 서비스가 paste를 처리한 뒤 extension은 짧은 지연 또는 `MutationObserver`로 composer 상태를 다시 읽어야 한다.

확인할 정보:

- textarea/contenteditable에 실제 텍스트가 남았는지
- 입력창이 비었는데 attachment chip/card가 생겼는지
- paste 전 clipboard text size와 paste 후 composer text size가 일치하는지
- file/image attachment metadata가 DOM에 표시되는지
- "Show in text field" 같은 전환 UI가 있는지

이 재확인은 clipboard capture를 대체하지 않는다. clipboard capture는 "붙여넣어진 원본 payload", DOM 재확인은 "실제로 전송될 현재 페이지 상태"를 보기 위한 별도 단계다.

### 3. Send 시점 통합 판정

send click 또는 Enter를 막은 뒤에는 다음 상태를 합쳐 판단한다.

- 마지막 paste capture 기록
- 현재 composer text
- 현재 attachment metadata
- file input/drop preflight 결과
- 분석 완료 여부
- 분석하지 못한 입력의 존재 여부

분석하지 못한 attachment 또는 large paste가 남아 있으면 `Allow`로 replay하면 안 된다.

## 이미지 Paste 처리

이미지 내용 확인은 MVP 범위가 아니다.

브라우저 extension이 clipboard image의 실제 픽셀 내용이나 OCR 결과를 안정적으로 분석하는 것은 비용, 성능, 권한, privacy 측면에서 MVP에 맞지 않는다. 따라서 이미지 paste는 다음처럼 처리한다.

- clipboard item 또는 file metadata만 읽는다.
- 가능한 metadata:
  - MIME type: 예 `image/png`
  - size: 가능하면 `File.size`
  - source: `clipboard`
  - attachment count
- raw image bytes, OCR text, preview bitmap, base64 payload는 Analyze request에 넣지 않는다.
- `contentScanned: false`로 표현한다.
- 정책 기본값은 fail-closed 또는 explicit warning이어야 한다. 조용한 Allow는 금지한다.

즉 "이미지 내용을 확인한다"가 아니라 "이미지가 포함됐고 내용은 스캔하지 않았음을 안전하게 표현한다"가 맞다.

## 권장 입력 모델

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
      contentScanned: boolean;
      handling: "blocked" | "warned" | "metadata_only" | "full_local_scan";
    }
  | {
      kind: "attachment_metadata";
      files: Array<{
        nameHash?: string;
        size?: number;
        type?: string;
        extension?: string;
        source: "file_input" | "drop" | "clipboard" | "rendered_attachment";
      }>;
      contentScanned: false;
    }
  | {
      kind: "unsupported_attachment";
      reason: string;
      contentScanned: false;
    };
```

이 모델은 extension 내부 request model과 backend Analyze API contract 양쪽에 반영되어야 한다.

## Decision 규칙

### Allow

다음 조건을 모두 만족할 때만 원본 send replay를 허용한다.

- 모든 direct/clipboard text가 configured limit 안에서 분석됨
- 현재 composer DOM과 분석된 입력 snapshot이 의미상 일치함
- attachment가 없거나, attachment policy가 명시적으로 allow함
- `unsupported_attachment`가 없음
- `contentScanned: false` 항목이 정책상 Allow 가능한 것으로 명시됨

### Warn

사용자 확인이 필요한 경우:

- content는 스캔하지 못했지만 metadata상 낮은 위험으로 취급하는 정책이 있는 경우
- large paste가 full scan 대신 metadata-only 처리된 경우
- 이미지 paste처럼 내용 분석 밖의 입력이 포함된 경우

Warn도 조용한 replay가 아니다. 사용자가 명시적으로 Continue를 눌러야 한다.

### Block

기본 Block 조건:

- large paste capture limit 초과
- attachment content를 스캔하지 못했고 정책상 허용 근거가 없음
- paste 후 DOM에 unscanned attachment가 생겼지만 clipboard/file preflight 기록과 연결할 수 없음
- 현재 composer state가 분석된 snapshot과 다름
- file/image/binary attachment가 MVP 지원 범위 밖이고 warning-only 정책이 아님

### Mask

Mask는 text input에만 적용한다.

- direct text 또는 clipboard text에만 masked replacement를 적용한다.
- attachment, image, binary content에는 masked replacement를 적용하지 않는다.
- attachment가 함께 있으면 masked text 적용 후 자동 send하지 않는다.

## Replay 규칙

원본 send replay는 page state가 보존된 경우에만 허용한다.

권장 snapshot:

- composer text hash
- composer byte length
- attachment count
- attachment metadata hash
- last paste capture id
- file preflight attempt id

다음 경우에는 자동 replay를 금지한다.

- paste 후 attachment로 변환됐으나 content scan 또는 metadata decision이 없음
- attachment count가 분석 시점과 send replay 시점 사이에 바뀜
- image paste가 있었으나 policy decision이 없음
- drag/drop 파일은 browser 보안 정책상 trusted replay가 불가능함

## API Contract 방향

기존 `prompt.text` 단일 필드는 장기적으로 충분하지 않다.

권장 request shape:

```ts
interface AnalyzeRequest {
  inputs: AnalyzeInput[];
  context: {
    ai_service: "CHATGPT" | "CLAUDE" | "GEMINI";
    ai_service_domain: string;
    page_url_origin: string;
    extension_version: string;
    browser: "Chrome";
    locale: string;
  };
  filter_config_version: string;
  client_request_id: string;
}
```

backend response는 다음을 명확히 포함해야 한다.

```ts
interface AnalyzeDecision {
  action: "Allow" | "Warn" | "Mask" | "Block";
  allow_original_send: boolean;
  unscanned_input_kinds: Array<AnalyzeInput["kind"]>;
  user_message: string;
}
```

## 테스트 계획

### Unit tests

1. `paste` 이벤트에서 plain text를 캡처하고 UTF-8 byte length를 계산한다.
2. `paste` 이벤트에서 clipboard image item을 `attachment_metadata`로 변환하고 raw image bytes를 request에 넣지 않는다.
3. large paste가 configured limit를 넘으면 `large_paste`와 `handling: "blocked"` 또는 정책상 warning 상태로 표현된다.
4. paste capture 후 composer DOM text가 동일하면 scanned text로 연결된다.
5. paste capture 후 composer text가 비고 attachment chip이 생기면 unscanned attachment로 표시된다.
6. `contentScanned: false` 입력이 있는데 policy decision이 없으면 Allow가 불가능하다.
7. Mask는 text input에만 적용되고 attachment metadata에는 적용되지 않는다.
8. replay guard는 attachment count/hash가 바뀐 경우 자동 replay를 거부한다.

### DOM fixture tests

1. ChatGPT-like textarea에 normal paste가 들어가고 send 시 분석 request에 반영된다.
2. ChatGPT-like large paste fixture가 textarea 대신 attachment card를 만들면 send가 fail-closed 된다.
3. contenteditable composer에서도 paste capture와 DOM 재확인이 작동한다.
4. rendered attachment card만 있고 textarea가 비어 있으면 empty prompt Allow가 아니라 unscanned attachment Block/Warn으로 처리된다.
5. image paste fixture는 MIME/size metadata만 남기고 raw content를 request/log/debug state에 남기지 않는다.

### Integration/e2e tests

1. send click은 native send를 먼저 막고 Analyze decision 전에는 원본 전송을 발생시키지 않는다.
2. Allow replay는 분석 snapshot과 현재 DOM state가 일치할 때 한 번만 발생한다.
3. Warn은 사용자 Continue 없이는 replay하지 않는다.
4. Mask는 composer text만 바꾸고 자동 send하지 않는다.
5. file input text file은 size/extension/MIME policy를 통과한 뒤에만 `File.text()`를 호출한다.
6. unsupported/binary/image file은 내용 읽기 없이 metadata-only decision으로 간다.
7. drag/drop은 분석 후 trusted replay가 불가능하면 재첨부 안내로 끝난다.

### Privacy regression tests

다음 값이 console/debug/log/API error/event/dashboard/test snapshot에 남지 않아야 한다.

- raw clipboard text
- raw prompt text
- raw file content
- raw image bytes 또는 base64
- OCR-like extracted text
- original filename
- full masked prompt
- raw detected value

### Manual browser smoke

공식 DOM과 threshold는 제품 변경에 취약하므로 수동 smoke가 필요하다.

1. ChatGPT에서 5k+ character paste가 실제로 attachment로 변환되는지 확인한다.
2. ChatGPT attachment card selector와 "Show in text field" UI를 확인한다.
3. Claude에서 paste/file/drop/image paste가 어떤 DOM으로 표현되는지 확인한다.
4. Gemini에서 multi-file, ZIP, code folder/GitHub repo attachment DOM을 확인한다.
5. 각 서비스에서 extension이 unsupported attachment를 조용히 Allow하지 않는지 확인한다.

## 구현 순서 제안

1. 내부 `AnalyzeInput` union type 추가
2. paste capture module 추가
3. attachment DOM detector 추가
4. send 시점 input aggregator 추가
5. replay snapshot guard 추가
6. API request contract alignment
7. privacy regression tests 추가
8. ChatGPT manual smoke 후 Claude/Gemini adapter 분리

## 비목표

- 이미지 OCR
- PDF/Office/binary full content extraction
- ZIP 내부 파일 분석
- Gemini code folder/GitHub repository deep scan
- target 서비스 private API 의존

이 기능들은 별도 MVP 이후 범위로 다룬다.
