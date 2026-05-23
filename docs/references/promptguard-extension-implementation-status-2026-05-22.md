# PromptGuard Extension Implementation Status - 2026-05-23

# 한국어 섹션

## 한 문장 요약

현재 구현되어 실제로 빌드하고 테스트할 수 있는 PromptGuard 앱은 `apps/extension`의 Chrome Extension MVP다. 이 MVP는 ChatGPT 화면에서 프롬프트 전송과 텍스트 파일 첨부를 먼저 멈추고, Analyze 결과를 받은 뒤 Allow/Warn/Mask/Block 중 하나로 처리한다.

현재 상태를 한 줄로 말하면 다음과 같다.

```text
로컬 확장프로그램 MVP 구현 완료
-> mock API와 fixture 테스트로 검증 완료
-> 실제 self-host Analyze API와 live ChatGPT 화면 검증은 남은 일
```

## 이 문서가 답하는 질문

이 문서는 네 가지 질문에 답한다.

1. 지금 무엇이 구현되어 있는가.
2. 사용자가 프롬프트를 보내거나 파일을 첨부할 때 실제로 어떤 순서로 동작하는가.
3. 어떤 데이터가 어디까지 이동하고, 어떤 데이터는 저장하거나 로그로 남기지 않는가.
4. 다음 단계에서 무엇을 연결하거나 검증해야 하는가.

## 현재 구현 상태

| 영역 | 상태 | 의미 |
| --- | --- | --- |
| Chrome Extension 기본 구조 | 구현됨 | Manifest V3, content script, background service worker, options page가 연결되어 있다. |
| 프롬프트 전송 전 검사 | 구현됨 | Send 버튼 클릭과 Enter 전송을 원래 페이지 전송 전에 잡는다. |
| 텍스트 파일 첨부 전 검사 | 구현됨 | file input change와 drag/drop을 원래 페이지 첨부 전에 잡는다. |
| Mock API | 구현됨 | 실제 서버 없이 같은 화면 흐름을 테스트한다. |
| Real API client | 구현됨 | API URL/token이 있으면 `/prompts/analyze`, `/files/analyze`, `/auth/me`, `/config/extension`으로 요청할 수 있다. |
| Options page | 구현됨 | API URL, token, mock mode, config sync를 설정한다. |
| Privacy/security guard | 구현 및 테스트됨 | 원문 저장/로그, 원본 파일명 전송, full URL 저장, network monitoring 사용을 막는 검사가 있다. |
| Product build/test wrapper | 구현됨 | `python apps/extension/tests/run_extension_checks.py all`로 typecheck/test/build/static check를 한 번에 실행한다. |

MVP의 현재 범위는 프롬프트와 텍스트 파일이다. PDF, Office, OCR, 압축파일, 바이너리 파싱, malware scan, 파일 내용 마스킹은 별도 범위다.

## 확장프로그램이 실행되는 위치

Chrome Extension은 한 프로세스처럼 보이지만 실제 코드는 세 위치에서 돈다.

| 위치 | 하는 일 | 대표 코드 |
| --- | --- | --- |
| Content script | ChatGPT 페이지 안에서 사용자의 send/upload 시도를 잡고 overlay를 보여준다. | `src/content/*` |
| Background service worker | content/options에서 온 메시지를 받고 mock API 또는 real API로 보낸다. token과 API URL 경계도 여기서 다룬다. | `src/background/*` |
| Options page | 사용자가 API URL, token, mock mode, config sync를 바꾸는 설정 화면이다. | `src/options/options.ts` |

공통 타입, 메시지 모양, 응답 검증, 파일 정책, privacy-safe audit helper는 `src/shared/*`에 있다. 이 분리는 content script가 DOM만 다루고, background가 API/token/storage를 다루고, shared가 양쪽의 계약을 맞추게 하기 위한 것이다.

## 코드 상세 지도

### Content script 코드

Content script는 사용자가 보고 있는 웹페이지 안에서 돈다. 여기서는 페이지 DOM을 보고, 사용자의 send/upload 이벤트를 먼저 잡고, Analyze 결과에 따라 원래 페이지 동작을 다시 실행할지 결정한다.

| 파일 | 맡는 일 | 받는 입력 | 다음으로 넘기는 것 | 결과 |
| --- | --- | --- | --- | --- |
| `contentScript.ts` | content script의 시작점이다. 기본 config로 먼저 hook을 설치하고, background에서 저장 config를 받은 뒤 다시 설치한다. | 현재 `document`, Chrome runtime, 저장 config | prompt controller, file controller, DOM watcher | 페이지 로딩 직후부터 send/upload preflight가 켜진다. |
| `domDetector.ts` | ChatGPT 입력창 후보를 selector로 찾고 가장 적합한 입력창을 고른다. | DOM, input selector 목록 | `PromptInputElement` 후보 | controller가 어느 입력창을 검사할지 알 수 있다. |
| `mutationWatcher.ts` | SPA 화면처럼 DOM이 바뀌는 경우 입력창 감지를 다시 실행한다. | DOM root, refresh callback | DOM 변경 알림 | 페이지 구조가 바뀌어도 입력창 감지 상태가 갱신된다. |
| `sendInterceptor.ts` | send 버튼 click과 Enter 전송을 capture phase에서 먼저 잡는다. | click/keydown event, send button selector, 현재 input | `SendAttempt` | 실제 페이지 전송 전에 prompt controller가 검사할 수 있다. |
| `promptExtractor.ts` | textarea 또는 contenteditable 입력창에서 텍스트를 읽는다. | prompt input element | prompt text | Analyze 요청의 `prompt.text`가 된다. |
| `promptPreflightController.ts` | 프롬프트 검사 흐름의 중심이다. 전송을 막고, request를 만들고, response를 검증하고, replay/mask/block UI를 결정한다. | `SendAttempt`, input text, context, config | `PROMPT_ANALYZE_REQUEST` runtime message | Allow/Warn/Mask/Block에 맞게 원래 send replay, overlay, mask 적용, block을 실행한다. |
| `maskedTextInjector.ts` | Mask decision의 `masked_prompt`를 입력창에 넣는다. | input element, `masked_prompt` | 변경된 input value/textContent | 자동 전송 없이 사용자가 바뀐 문장을 확인할 수 있다. |
| `fileUploadInterceptor.ts` | file input change와 drag/drop 파일 이벤트를 capture phase에서 먼저 잡는다. | change/drop event, file input/drop zone selector | `FileUploadAttempt` | 실제 첨부 전에 file controller가 검사할 수 있다. |
| `fileUploadSnapshot.ts` | 이번 첨부 시도의 파일들을 snapshot으로 만든다. | browser `File[]` | `client_file_id`, `File`, policy input | 파일 결과를 원본 파일명 없이 매칭할 수 있다. |
| `textFileReader.ts` | policy를 통과한 텍스트 파일만 메모리에서 읽는다. | file snapshot, policy decision | Analyze request용 file entries | `content_text`가 요청 payload로 준비된다. |
| `fileUploadPreflightController.ts` | 파일 검사 흐름의 중심이다. 정책 검사, 텍스트 읽기, Analyze 요청, response 처리, 첨부 replay/fallback을 담당한다. | `FileUploadAttempt`, config, context | `FILES_ANALYZE_REQUEST` runtime message | Allow/Warn이면 첨부 replay를 시도하고, 실패하면 reattach 안내를 보여준다. |
| `preflightOverlay.ts` | 분석 중, 경고, 차단, 오류, mask action을 화면에 보여준다. | decision, fixed message, button actions | DOM overlay | 사용자가 Continue/Cancel/Retry/Apply mask 같은 결정을 할 수 있다. |

`promptPreflightController.ts`와 `fileUploadPreflightController.ts`가 중요한 이유는 원래 페이지 동작을 다시 실행하는 권한을 여기서만 갖기 때문이다. 이 두 controller는 response가 올 때까지 원래 동작을 막고, response shape가 맞고 decision이 허용할 때만 replay한다.

### Background 코드

Background service worker는 content script와 options page가 직접 서버나 token을 만지지 않게 하는 경계다. content/options는 runtime message를 보내고, background가 storage, auth, mock/real API를 처리한다.

| 파일 | 맡는 일 | 받는 입력 | 다음으로 넘기는 것 | 결과 |
| --- | --- | --- | --- | --- |
| `serviceWorker.ts` | Chrome runtime message 입구다. 메시지 shape를 먼저 확인한다. | unknown runtime message | validated `ExtensionMessage` | 잘못된 메시지는 router에 도달하지 않는다. |
| `messageRouter.ts` | message type별 handler를 고른다. | `PROMPT_ANALYZE_REQUEST`, `FILES_ANALYZE_REQUEST`, auth/config message | prompt/file/auth/config handler 호출 | background 동작이 한 switch에서 추적된다. |
| `promptAnalyzeClient.ts` | 프롬프트 요청을 mock 또는 real API로 보낸다. | `AnalyzeRequest` | `mockPromptAnalyze()` 또는 `postJson("/prompts/analyze")` | prompt decision이 content script로 돌아간다. |
| `fileAnalyzeClient.ts` | 파일 요청을 mock 또는 real API로 보낸다. | `FilesAnalyzeRequest` | `mockFilesAnalyze()` 또는 `postJson("/files/analyze")` | file decision이 content script로 돌아간다. |
| `apiClient.ts` | 실제 HTTP GET/POST를 중앙화한다. bearer header, extension header, timeout, error normalization을 처리한다. | endpoint path, JSON body, API URL, token, timeout | `fetch()` request | 서버 오류나 네트워크 오류가 safe `NormalizedError`로 바뀐다. |
| `mockApi.ts` | 서버 없이 deterministic Analyze 응답을 만든다. Mask일 때는 mock backend 경계에서 `masked_prompt`도 만든다. | prompt text 또는 file text | Allow/Warn/Mask/Block response, Mask의 `masked_prompt` | 개발/테스트에서 real API 없이 같은 control flow를 검증한다. |
| `configStore.ts` | API URL, mock mode, cached config를 읽고 저장한다. | `chrome.storage.local` values | normalized settings | 잘못된 cached config는 `DEFAULT_CONFIG`로 대체된다. |
| `authStore.ts` | bearer token을 저장/조회/삭제한다. | options page token | background-local auth state | content script가 token을 직접 보지 않는다. |

### Shared 코드

Shared 코드는 content, background, options가 같은 계약을 쓰게 한다. 여기서 타입과 validator를 공유하기 때문에 한쪽에서 만든 message나 response가 다른 쪽에서 같은 기준으로 해석된다.

| 파일 | 맡는 일 | 핵심 포인트 |
| --- | --- | --- |
| `types.ts` | Analyze request/response, file request/response, config, message, error 타입을 정의한다. | `DecisionAction`은 `Allow`, `Warn`, `Mask`, `Block` 네 가지다. |
| `messageTypes.ts` | runtime message가 유효한지 확인한다. | background router 전에 malformed message를 차단한다. |
| `responseValidation.ts` | prompt/file Analyze response가 유효한지 확인한다. | invalid response는 replay를 허용하지 않는다. |
| `configValidation.ts` | remote/cached config shape를 확인한다. | 잘못된 selector, timeout, file policy가 적용되지 않게 한다. |
| `filePolicy.ts` | 파일 개수, 크기, 총 크기, extension, MIME type을 검사한다. | 파일 내용 읽기 전에 reject 여부를 결정한다. |
| `fileTypes.ts` | filename extension과 text-like MIME 여부를 판단한다. | 텍스트 파일 MVP 범위를 정한다. |
| `errors.ts` | fetch/throw error를 safe error message로 바꾼다. | 내부 오류나 raw server text가 UI로 새지 않게 한다. |
| `hashing.ts` | client request/file id를 만든다. | 파일명 hash 대신 per-attempt opaque ID를 만든다. |
| `auditEvents.ts` | metadata-only audit event 객체를 만든다. | raw prompt, file content, original filename, server message를 포함하지 않는다. |
| `constants.ts` | default config, storage key, version, timeout 값을 모은다. | content/background/options가 같은 기본값을 쓴다. |
| `sanitize.ts` | UI나 metadata에 쓰는 문자열을 정리한다. | 표시용 문자열 경계를 한곳에 둔다. |

### Options 코드

Options page는 사용자가 mock mode와 real API 연결을 바꾸는 UI다.

| 파일 | 맡는 일 | 동작 |
| --- | --- | --- |
| `options.ts` | 설정 UI를 hydrate하고 버튼 동작을 runtime message로 보낸다. | Save는 API URL/mock mode/token을 저장하고, Test connection은 `/auth/me`, Sync config는 `/config/extension` 경로를 확인한다. |
| `options.html` | 설정 화면 구조다. | API URL, mock mode, token, status, policy version, file inspection 상태를 보여준다. |
| `options.css` | 설정 화면 스타일이다. | Chrome extension options page 안에서 읽기 쉬운 설정 화면을 만든다. |

### 테스트 코드가 보는 경계

테스트는 단위 함수만 보는 것이 아니라 extension 경계가 깨지지 않는지도 확인한다.

| 테스트 영역 | 확인하는 것 |
| --- | --- |
| prompt controller tests | click/Enter intercept, Allow replay, Warn confirmation, Mask apply, Block/fail-closed 처리 |
| file controller tests | file policy reject, text read, Allow/Warn replay, replay fallback, fail-closed 처리 |
| router/API/storage tests | mock/real routing, auth/config 저장, safe error normalization |
| validator tests | runtime message와 Analyze response shape guard |
| privacy regression tests | prompt/file raw value, original filename, URL path/query 같은 값이 저장/출력 경로로 새지 않는지 |
| wrapper static checks | `webRequest`/DNR, console logging, exported surface docs, privacy seed를 build/test 흐름에서 확인 |

## 프롬프트 전송 흐름

사용자가 Send 버튼을 누르거나 Enter를 누르면 다음 순서로 처리된다.

1. `sendInterceptor.ts`가 click/keydown을 먼저 받는다.
2. Shift+Enter 또는 IME composition 중 Enter이면 글쓰기 동작으로 보고 그대로 둔다.
3. 실제 전송이면 원래 전송을 잠깐 막는다.
4. `promptPreflightController.ts`가 현재 입력창을 찾는다.
5. `promptExtractor.ts`가 입력창의 텍스트를 읽는다.
6. `buildPromptAnalyzeRequest()`가 Analyze 요청을 만든다.
7. content script가 background로 `PROMPT_ANALYZE_REQUEST` 메시지를 보낸다.
8. background는 mock mode이면 `mockApi.ts`, real mode이면 `apiClient.ts`를 통해 검사한다. Mask의 `masked_prompt` 생성 책임은 content script가 아니라 mock/real Analyze 응답 경계에 있다.
9. `responseValidation.ts`가 응답 모양을 확인한다.
10. content script가 decision에 맞는 화면 동작을 실행한다.

프롬프트 요청에 들어가는 핵심 값은 다음이다.

| 값 | 왜 필요한가 | 다음 단계 |
| --- | --- | --- |
| 입력창 텍스트 | Analyze 서버가 위험 여부를 판단한다. | 요청 순간에만 `/prompts/analyze` payload로 들어간다. |
| 입력 방식 | click/Enter 등 사용자가 어떻게 전송했는지 나타낸다. | `prompt.input_method`로 전달된다. |
| origin | 어떤 서비스 화면에서 온 요청인지 알려준다. | path/query/fragment 없이 origin만 전달된다. |
| extension version/browser/locale | 서버가 클라이언트 환경과 정책을 맞춘다. | `context` metadata로 전달된다. |
| client request id | 원문 없이 요청 하나를 구분한다. | metadata identifier로 전달된다. |

Analyze decision 처리 방식은 다음이다.

| Decision | 현재 동작 |
| --- | --- |
| `Allow` | 응답이 원본 전송을 허용하면 원래 send를 한 번만 다시 실행한다. |
| `Warn` | Continue/Cancel overlay를 보여주고, Continue를 누르면 원래 send를 한 번만 다시 실행한다. |
| `Mask` | 입력창을 `masked_prompt`로 바꾸고 자동 전송하지 않는다. 사용자가 확인 후 직접 다시 보낸다. |
| `Block` | 원래 send를 다시 실행하지 않는다. |
| timeout/error/invalid response | 확실히 허용된 상태가 아니므로 원래 send를 다시 실행하지 않는다. |

## 텍스트 파일 첨부 흐름

사용자가 파일을 선택하거나 드롭하면 다음 순서로 처리된다.

1. `fileUploadInterceptor.ts`가 file input change 또는 drop event를 먼저 받는다.
2. 원래 페이지 첨부를 잠깐 막는다.
3. `fileUploadSnapshot.ts`가 이번 첨부 시도의 파일 목록을 snapshot으로 만든다.
4. `filePolicy.ts`가 파일 개수, 파일 크기, 총 크기, 확장자, MIME type을 확인한다.
5. 지원하지 않는 파일이면 내용을 읽지 않고 막는다.
6. 지원하는 텍스트 파일이면 `textFileReader.ts`가 메모리에서만 내용을 읽는다.
7. 바이너리처럼 보이면 막는다.
8. `buildFilesAnalyzeRequest()`가 `/files/analyze` 요청을 만든다.
9. background가 mock API 또는 real API로 검사한다.
10. content script가 decision에 맞는 첨부 동작을 실행한다.

파일 요청에 들어가는 핵심 값은 다음이다.

| 값 | 왜 필요한가 | 다음 단계 |
| --- | --- | --- |
| 텍스트 파일 내용 | 파일 내용의 위험 여부를 판단한다. | 요청 순간에만 `/files/analyze` payload로 들어간다. |
| size/MIME/extension 판단 결과 | MVP에서 읽을 수 있는 텍스트 파일인지 결정한다. | 로컬 정책 판단과 요청 metadata에 쓰인다. |
| `client_file_id` | 원본 파일명 없이 결과를 파일 시도에 매칭한다. | 첨부 시도마다 새로 만든 opaque ID로 전달된다. |
| origin/context | 어떤 페이지에서 온 첨부인지 알려준다. | origin 중심 metadata로 전달된다. |

파일 Analyze decision 처리 방식은 다음이다.

| Decision | 현재 동작 |
| --- | --- |
| `Allow` | 원래 첨부를 한 번 재실행한다. 페이지가 자동 재첨부를 거부하면 사용자가 다시 첨부해야 한다는 안내를 보여준다. |
| `Warn` | Continue/Cancel overlay를 보여주고, Continue를 누르면 첨부 재실행을 시도한다. |
| `Mask` | 파일 내용 마스킹은 현재 MVP 범위 밖이므로 첨부하지 않는다. |
| `Block` | 첨부하지 않는다. |
| timeout/error/invalid response | 확실히 허용된 상태가 아니므로 첨부하지 않는다. |

## 데이터 경계

프롬프트 텍스트와 텍스트 파일 내용은 Analyze 판단에 필요하므로 요청 순간에는 사용된다. 하지만 extension 쪽에서 저장하거나 로그로 남기지 않는다.

| 데이터 | Analyze 요청에 사용 | 저장/로그 | 설명 |
| --- | --- | --- | --- |
| 프롬프트 원문 | 예 | 아니오 | `/prompts/analyze` 요청 순간에만 사용한다. |
| 텍스트 파일 내용 | 예 | 아니오 | 지원되는 텍스트 파일만 메모리에서 읽어 요청한다. |
| 원본 파일명 | 로컬 정책 판단에만 사용 | 아니오 | Analyze payload에는 원본 파일명을 넣지 않는다. |
| filename hash | 아니오 | 아니오 | 파일명 기반 hash를 만들지 않는다. |
| `client_file_id` | 예 | metadata | 원본 파일명과 연결되지 않는 per-attempt opaque ID다. |
| URL origin | 예 | metadata | path/query/fragment는 제외한다. |
| masked prompt 전체 | 화면 치환에만 사용 | 아니오 | 자동 전송하지 않고 사용자가 직접 확인한다. |
| detected raw value | 아니오 | 아니오 | 서버 응답에 있어도 UI에 그대로 보여주지 않는다. |
| server `user_message` | schema compatibility로만 확인 | 아니오 | overlay에는 extension이 가진 fixed safe message를 보여준다. |

## 주요 안전장치

| 안전장치 | 필요한 이유 | 현재 구현 |
| --- | --- | --- |
| `document_start` 로딩 | 저장된 설정을 읽기 전에 사용자가 전송할 수 있다. | 기본 config로 먼저 hook을 설치하고, 저장된 config를 읽은 뒤 다시 설치한다. |
| hook cleanup | 같은 send/upload가 두 번 처리될 수 있다. | 재설치 전에 이전 watcher/controller를 끊는다. |
| runtime message guard | 잘못된 메시지가 background 동작을 시작하면 안 된다. | 메시지 shape를 확인한 뒤 라우팅한다. |
| Analyze response validation | 잘못된 서버 응답이 replay를 허용하면 안 된다. | 응답 shape가 맞을 때만 decision을 처리한다. |
| timeout fail-closed | 검사가 늦을 때 원래 동작이 계속되면 보호가 깨진다. | timeout/error는 send/upload를 진행하지 않는다. |
| contradictory Allow 차단 | `Allow`라도 원본 replay 금지가 함께 오면 위험하다. | fail-closed로 처리한다. |
| fixed safe message | 서버 메시지에 민감값이 섞일 수 있다. | 서버 `user_message`를 overlay에 그대로 렌더하지 않는다. |
| original filename exclusion | 파일명에 민감정보가 들어갈 수 있다. | Analyze 파일 요청에는 원본 파일명을 넣지 않는다. |
| metadata-only audit event | telemetry가 원문 저장 경로가 되면 안 된다. | `auditEvents.ts`는 action/risk/policy/count 같은 metadata만 만든다. |
| network monitoring exclusion | 현재 통제 방식은 DOM preflight다. | `webRequest`와 DNR 사용을 정적 검사로 막는다. |

## Mock API와 Real API 연결

Mock mode와 real mode는 content/background/message 흐름을 공유한다. 마지막 responder만 다르다.

```text
content script가 Analyze request 생성
-> background messageRouter
-> mock mode: mockApi
-> real mode: apiClient로 서버 호출
-> 같은 response shape
-> content script가 같은 decision 처리
```

이 구조 덕분에 서버가 준비되기 전에는 mock mode로 UI와 control flow를 검증하고, 서버가 준비되면 options page에서 API URL/token/mock mode만 바꿔 real API를 확인할 수 있다.

## 실행과 검증 방법

확장프로그램을 직접 빌드하려면 저장소 루트에서 다음을 실행한다.

```powershell
cd apps/extension
npm install
npm run typecheck
npm test
npm run build
```

전체 검증은 저장소 루트에서 다음 wrapper를 실행한다.

```powershell
python apps/extension/tests/run_extension_checks.py all
```

현재 wrapper 기준은 다음이다.

| 검사 | 확인하는 것 |
| --- | --- |
| TypeScript typecheck | 타입 계약이 맞는지 확인한다. |
| Vitest unit tests | 주요 모듈 동작이 맞는지 확인한다. |
| E2E fixture tests | ChatGPT 비슷한 fixture page에서 prompt/file 흐름이 동작하는지 확인한다. |
| production build | Chrome이 로드할 수 있는 `dist`가 만들어지는지 확인한다. |
| no network monitoring static check | `webRequest`와 DNR이 들어오지 않았는지 확인한다. |
| no console static check | source에 console logging이 남지 않았는지 확인한다. |
| privacy seed check | 금지 seed가 build output에 남지 않았는지 확인한다. |
| exported surface documentation check | exported TypeScript surface에 JSDoc/TSDoc이 있는지 확인한다. |
| audit event unit test | audit event가 원문, 파일명, 서버 메시지를 포함하지 않는지 확인한다. |

마지막 전체 검증 스냅샷은 23개 test file, 70개 test 통과다.

Chrome에 로드하는 순서는 다음이다.

1. Chrome에서 `chrome://extensions`를 연다.
2. `Developer mode`를 켠다.
3. `Load unpacked`를 누른다.
4. `apps/extension/dist` 폴더를 선택한다.
5. `https://chatgpt.com/*` 또는 `https://chat.openai.com/*`에서 동작을 확인한다.

## 남은 일

| 남은 일 | 필요한 조건 |
| --- | --- |
| 실제 Analyze API schema 통합 검증 | self-host 서버 endpoint와 최종 request/response schema가 필요하다. |
| live ChatGPT DOM smoke test | 실제 ChatGPT 페이지에서 수동 검증 환경이 필요하다. |
| file replay 안정성 live 검증 | 실제 uploader가 fixture와 다르게 동작하는지 확인해야 한다. |
| persistent event logging / dashboard ingestion | 서버 저장 정책, 보존 기간, dashboard 요구사항이 필요하다. |
| file content masking | 별도 UX와 정책 결정이 필요하다. |
| PDF/Office/OCR/archive/binary/malware scan | 텍스트 파일 MVP보다 큰 별도 처리 범위가 필요하다. |

# English Section

## One-Sentence Summary

The currently implemented and runnable PromptGuard app is the Chrome Extension MVP under `apps/extension`. It pauses prompt sends and text-file attaches on a ChatGPT page, sends the content through Analyze, then applies one of Allow/Warn/Mask/Block.

Current status in one line:

```text
Local extension MVP implemented
-> verified with mock API and fixture tests
-> real self-host Analyze API and live ChatGPT verification remain
```

## What This Document Answers

This document answers four questions.

1. What is implemented now.
2. What happens when a user sends a prompt or attaches a file.
3. Which data moves where, and which data is not persisted or logged.
4. What still needs integration or verification.

## Current Implementation State

| Area | Status | Meaning |
| --- | --- | --- |
| Chrome Extension foundation | Implemented | Manifest V3, content script, background service worker, and options page are connected. |
| Prompt preflight | Implemented | Send button clicks and Enter sends are intercepted before the page sends. |
| Text-file upload preflight | Implemented | File input change and drag/drop are intercepted before the page attaches files. |
| Mock API | Implemented | The same UI flow can be tested without a real server. |
| Real API client | Implemented | With API URL/token, the extension can call `/prompts/analyze`, `/files/analyze`, `/auth/me`, and `/config/extension`. |
| Options page | Implemented | API URL, token, mock mode, and config sync are configurable. |
| Privacy/security guard | Implemented and tested | Checks cover raw persistence/logging, original filename payloads, full URL storage, and network monitoring usage. |
| Product build/test wrapper | Implemented | `python apps/extension/tests/run_extension_checks.py all` runs typecheck, tests, build, and static checks. |

The current MVP scope is prompts and text files. PDF, Office, OCR, archives, binary parsing, malware scan, and file content masking are separate scopes.

## Where The Extension Runs

A Chrome Extension looks like one app, but the code runs in three places.

| Place | Responsibility | Representative code |
| --- | --- | --- |
| Content script | Runs inside the ChatGPT page, catches send/upload attempts, and shows overlay UI. | `src/content/*` |
| Background service worker | Receives messages from content/options and sends them to mock or real API. It also owns token and API URL boundaries. | `src/background/*` |
| Options page | Lets the user set API URL, token, mock mode, and config sync. | `src/options/options.ts` |

Shared types, message shapes, response validation, file policy, and privacy-safe audit helpers live in `src/shared/*`. This keeps DOM work in content, API/token/storage work in background, and shared contracts in one place.

## Detailed Code Map

### Content Script Code

The content script runs inside the web page. It reads the page DOM, intercepts user send/upload events first, and decides whether to replay the original page action after Analyze returns.

| File | Responsibility | Receives | Passes forward | Result |
| --- | --- | --- | --- | --- |
| `contentScript.ts` | Content entry point. Installs hooks once with default config, then reinstalls after stored config loads from background. | Current `document`, Chrome runtime, stored config | Prompt controller, file controller, DOM watcher | Send/upload preflight starts immediately after page load. |
| `domDetector.ts` | Finds the best ChatGPT input candidate from selectors. | DOM and input selectors | `PromptInputElement` candidate | Controllers know which input to inspect. |
| `mutationWatcher.ts` | Re-runs input detection when the SPA DOM changes. | DOM root and refresh callback | DOM change notification | Input detection stays current after page changes. |
| `sendInterceptor.ts` | Catches send button clicks and Enter sends in capture phase. | click/keydown event, send button selectors, current input | `SendAttempt` | The prompt controller can inspect before native send. |
| `promptExtractor.ts` | Reads text from textarea or contenteditable inputs. | Prompt input element | Prompt text | Becomes `prompt.text` in the Analyze request. |
| `promptPreflightController.ts` | Owns prompt inspection. Blocks native send, builds request, validates response, and decides replay/mask/block UI. | `SendAttempt`, input text, context, config | `PROMPT_ANALYZE_REQUEST` runtime message | Applies Allow/Warn/Mask/Block behavior. |
| `maskedTextInjector.ts` | Writes `masked_prompt` back into the input. | Input element and `masked_prompt` | Updated input value/textContent | The user can review the masked text before sending. |
| `fileUploadInterceptor.ts` | Catches file input changes and drag/drop file events in capture phase. | change/drop event, file input/drop zone selectors | `FileUploadAttempt` | The file controller can inspect before native attach. |
| `fileUploadSnapshot.ts` | Creates snapshots for the current attach attempt. | Browser `File[]` | `client_file_id`, `File`, policy input | File results can be matched without original filenames. |
| `textFileReader.ts` | Reads only policy-approved text files in memory. | File snapshot and policy decision | Request file entries | `content_text` is prepared for the transient request payload. |
| `fileUploadPreflightController.ts` | Owns file inspection. Runs policy, reads text, sends Analyze, handles replay/fallback. | `FileUploadAttempt`, config, context | `FILES_ANALYZE_REQUEST` runtime message | Replays approved attaches or shows reattach fallback. |
| `preflightOverlay.ts` | Shows analyzing, warn, block, error, and mask actions. | decision, fixed message, button actions | DOM overlay | The user can continue, cancel, retry, or apply mask. |

`promptPreflightController.ts` and `fileUploadPreflightController.ts` are the key safety boundaries because they are the only content-side modules that decide whether the original page action is replayed. They block first, wait for Analyze, validate the response shape, and replay only when the decision authorizes it.

### Background Code

The background service worker keeps content scripts and the options page away from direct server/token handling. Content/options send runtime messages; background owns storage, auth, mock mode, and real API calls.

| File | Responsibility | Receives | Passes forward | Result |
| --- | --- | --- | --- | --- |
| `serviceWorker.ts` | Chrome runtime message entry point. Validates message shape first. | unknown runtime message | validated `ExtensionMessage` | Malformed messages do not reach the router. |
| `messageRouter.ts` | Chooses a handler by message type. | prompt, file, auth, config messages | prompt/file/auth/config handler call | Background behavior stays traceable in one switch. |
| `promptAnalyzeClient.ts` | Sends prompt requests through mock or real API. | `AnalyzeRequest` | `mockPromptAnalyze()` or `postJson("/prompts/analyze")` | Prompt decision returns to content. |
| `fileAnalyzeClient.ts` | Sends file requests through mock or real API. | `FilesAnalyzeRequest` | `mockFilesAnalyze()` or `postJson("/files/analyze")` | File decision returns to content. |
| `apiClient.ts` | Centralizes real HTTP GET/POST. Handles bearer headers, extension headers, timeout, and error normalization. | endpoint path, JSON body, API URL, token, timeout | `fetch()` request | Server/network errors become safe `NormalizedError` objects. |
| `mockApi.ts` | Creates deterministic Analyze responses without a server. For Mask, it also creates `masked_prompt` at the mock backend boundary. | prompt text or file text | Allow/Warn/Mask/Block response, plus Mask `masked_prompt` | Development/tests exercise the same control flow without real API. |
| `configStore.ts` | Reads and saves API URL, mock mode, and cached config. | `chrome.storage.local` values | normalized settings | Invalid cached config falls back to `DEFAULT_CONFIG`. |
| `authStore.ts` | Stores, reads, and clears bearer tokens. | options page token | background-local auth state | Content scripts do not handle tokens directly. |

### Shared Code

Shared code keeps content, background, and options on the same contract. Types and validators are shared so a message or response built on one side is interpreted with the same rules on the other side.

| File | Responsibility | Key point |
| --- | --- | --- |
| `types.ts` | Defines Analyze requests/responses, file requests/responses, config, messages, and errors. | `DecisionAction` is `Allow`, `Warn`, `Mask`, or `Block`. |
| `messageTypes.ts` | Validates runtime messages. | Malformed messages are rejected before background routing. |
| `responseValidation.ts` | Validates prompt/file Analyze responses. | Invalid responses cannot authorize replay. |
| `configValidation.ts` | Validates remote/cached config shape. | Bad selectors, timeout, or file policy are not applied. |
| `filePolicy.ts` | Checks file count, size, total size, extension, and MIME type. | Rejects files before content is read. |
| `fileTypes.ts` | Interprets filename extension and text-like MIME type. | Defines the text-file MVP boundary. |
| `errors.ts` | Converts fetch/thrown errors into safe messages. | Internal errors and raw server text do not leak to UI. |
| `hashing.ts` | Creates client request/file IDs. | Uses per-attempt opaque IDs instead of filename hashes. |
| `auditEvents.ts` | Builds metadata-only audit events. | Excludes raw prompt, file content, original filename, and server message text. |
| `constants.ts` | Holds default config, storage keys, version, and timeout values. | Content/background/options use the same defaults. |
| `sanitize.ts` | Normalizes strings used in UI or metadata. | Keeps display string handling in one boundary. |

### Options Code

The options page is the UI for switching mock mode and real API integration.

| File | Responsibility | Behavior |
| --- | --- | --- |
| `options.ts` | Hydrates the settings UI and sends button actions as runtime messages. | Save stores API URL/mock mode/token, Test connection checks `/auth/me`, Sync config checks `/config/extension`. |
| `options.html` | Settings page structure. | Shows API URL, mock mode, token, status, policy version, and file inspection state. |
| `options.css` | Settings page styling. | Keeps the Chrome options page readable. |

### Test Boundaries

Tests check module behavior and extension boundary safety.

| Test area | What it checks |
| --- | --- |
| prompt controller tests | click/Enter intercept, Allow replay, Warn confirmation, Mask apply, Block/fail-closed behavior |
| file controller tests | file policy reject, text read, Allow/Warn replay, replay fallback, fail-closed behavior |
| router/API/storage tests | mock/real routing, auth/config storage, safe error normalization |
| validator tests | runtime message and Analyze response shape guards |
| privacy regression tests | raw prompt/file values, original filename, URL path/query do not leak into storage/output paths |
| wrapper static checks | `webRequest`/DNR, console logging, exported surface docs, and privacy seeds are checked in the build/test flow |

## Prompt Send Flow

When the user clicks Send or presses Enter, the extension handles it in this order.

1. `sendInterceptor.ts` receives the click/keydown first.
2. Shift+Enter and IME composition Enter remain normal typing actions.
3. A real send is paused.
4. `promptPreflightController.ts` finds the current input.
5. `promptExtractor.ts` reads the input text.
6. `buildPromptAnalyzeRequest()` creates the Analyze request.
7. The content script sends `PROMPT_ANALYZE_REQUEST` to the background worker.
8. The background worker uses `mockApi.ts` in mock mode or `apiClient.ts` in real mode. Mask `masked_prompt` generation belongs to the mock/real Analyze response boundary, not the content script.
9. `responseValidation.ts` checks the response shape.
10. The content script applies the decision to the page.

Core prompt request values:

| Value | Why it is needed | Next step |
| --- | --- | --- |
| Input text | The Analyze server needs it to judge risk. | Used only in the transient `/prompts/analyze` payload. |
| Input method | Records whether the user sent by click, Enter, or another route. | Passed as `prompt.input_method`. |
| Origin | Identifies the service surface. | Passed without path/query/fragment. |
| Extension version/browser/locale | Helps server policy and compatibility decisions. | Passed as `context` metadata. |
| Client request id | Identifies one request without storing raw text. | Passed as a metadata identifier. |

Decision behavior:

| Decision | Current behavior |
| --- | --- |
| `Allow` | Replays the original send once when the response permits original send. |
| `Warn` | Shows Continue/Cancel; Continue replays the original send once. |
| `Mask` | Replaces the input with `masked_prompt` and does not auto-send. The user reviews and sends manually. |
| `Block` | Does not replay the original send. |
| timeout/error/invalid response | Does not replay the original send because the action was not explicitly allowed. |

## Text-File Upload Flow

When the user selects or drops files, the extension handles it in this order.

1. `fileUploadInterceptor.ts` receives the file input change or drop event first.
2. The native page attach is paused.
3. `fileUploadSnapshot.ts` snapshots the current attach attempt.
4. `filePolicy.ts` checks file count, file size, total size, extension, and MIME type.
5. Unsupported files are blocked before reading.
6. Supported text files are read in memory by `textFileReader.ts`.
7. Binary-looking content is blocked.
8. `buildFilesAnalyzeRequest()` creates the `/files/analyze` request.
9. The background worker sends the request through mock or real API.
10. The content script applies the decision to the attach action.

Core file request values:

| Value | Why it is needed | Next step |
| --- | --- | --- |
| Text-file content | Analyze needs it to judge file risk. | Used only in the transient `/files/analyze` payload. |
| Size/MIME/extension decision | Determines whether the MVP may read the file. | Used for local policy and request metadata. |
| `client_file_id` | Matches the result to the file attempt without sending the original filename. | Passed as a new opaque per-attempt ID. |
| Origin/context | Identifies the page where the attach came from. | Passed as origin-centered metadata. |

File decision behavior:

| Decision | Current behavior |
| --- | --- |
| `Allow` | Attempts one attach replay. If the page rejects automatic reattach, the UI asks the user to attach again. |
| `Warn` | Shows Continue/Cancel; Continue attempts attach replay. |
| `Mask` | Does not attach because file content masking is outside the current MVP scope. |
| `Block` | Does not attach. |
| timeout/error/invalid response | Does not attach because the action was not explicitly allowed. |

## Data Boundary

Prompt text and text-file content are needed for Analyze, so they are used in the request. The extension does not persist or log them.

| Data | Used in Analyze request | Persisted/logged | Notes |
| --- | --- | --- | --- |
| Raw prompt text | Yes | No | Used only in the transient `/prompts/analyze` request. |
| Text-file content | Yes | No | Only supported text files are read in memory for the request. |
| Original filename | Local policy only | No | File Analyze payloads omit the original filename. |
| Filename hash | No | No | The extension does not create filename-derived hashes. |
| `client_file_id` | Yes | Metadata | Opaque per-attempt ID, not tied to the original filename. |
| URL origin | Yes | Metadata | Path/query/fragment are omitted. |
| Full masked prompt | Page replacement only | No | The user reviews it manually before sending. |
| Detected raw value | No | No | Not rendered directly in the UI. |
| Server `user_message` | Schema compatibility only | No | The overlay uses extension-owned fixed safe messages. |

## Key Safety Controls

| Control | Why it exists | Current implementation |
| --- | --- | --- |
| `document_start` loading | The user may send before stored config finishes loading. | Hooks install with default config first, then reinstall after stored config loads. |
| Hook cleanup | One send/upload can otherwise be processed twice. | Old watchers/controllers disconnect before reinstall. |
| Runtime message guard | Bad messages must not drive background behavior. | Message shape is checked before routing. |
| Analyze response validation | Bad server responses must not authorize replay. | Only valid response shapes reach decision handling. |
| Timeout fail-closed | Protection fails if a slow inspection allows the original action. | Timeout/error does not continue send/upload. |
| Contradictory Allow rejection | `Allow` plus replay denial is unsafe. | Treated as fail-closed. |
| Fixed safe message | Server messages may contain sensitive values. | Raw `user_message` is not rendered in overlays. |
| Original filename exclusion | Filenames can contain sensitive data. | File Analyze requests omit original filenames. |
| Metadata-only audit event | Telemetry must not become raw-data storage. | `auditEvents.ts` emits action/risk/policy/count metadata only. |
| Network monitoring exclusion | The current control path is DOM preflight. | Static checks reject `webRequest` and DNR usage. |

## Mock And Real API

Mock mode and real mode share the same content/background/message flow. Only the final responder changes.

```text
content script builds Analyze request
-> background messageRouter
-> mock mode: mockApi
-> real mode: apiClient calls server
-> same response shape
-> content script applies the same decision behavior
```

This lets the team verify UI and control flow in mock mode before the server is ready. Once the server is ready, the options page can switch API URL/token/mock mode to verify real API behavior.

## Run And Verify

To build the extension directly from the repository root:

```powershell
cd apps/extension
npm install
npm run typecheck
npm test
npm run build
```

To run the full wrapper from the repository root:

```powershell
python apps/extension/tests/run_extension_checks.py all
```

The wrapper checks:

| Check | What it verifies |
| --- | --- |
| TypeScript typecheck | Type contracts line up. |
| Vitest unit tests | Core module behavior is correct. |
| E2E fixture tests | Prompt/file flows work on a ChatGPT-like fixture page. |
| production build | Chrome-loadable `dist` is created. |
| no network monitoring static check | `webRequest` and DNR are absent. |
| no console static check | Source console logging is absent. |
| privacy seed check | Forbidden seeds are absent from build output. |
| exported surface documentation check | Exported TypeScript surfaces have JSDoc/TSDoc. |
| audit event unit test | Audit events exclude raw text, filenames, and server message text. |

The latest full verification snapshot passed 23 test files and 70 tests.

To load the built extension in Chrome:

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select `apps/extension/dist`.
5. Test on `https://chatgpt.com/*` or `https://chat.openai.com/*`.

## Remaining Work

| Remaining work | Required condition |
| --- | --- |
| Real Analyze API schema integration | Needs the self-host server endpoint and final request/response schema. |
| Live ChatGPT DOM smoke test | Needs a real ChatGPT page verification environment. |
| File replay stability on live DOM | Needs confirmation that the real uploader behaves like or differently from the fixture. |
| Persistent event logging / dashboard ingestion | Needs server storage policy, retention rules, and dashboard requirements. |
| File content masking | Needs separate UX and policy decisions. |
| PDF/Office/OCR/archive/binary/malware scan | Needs a larger processing scope beyond the text-file MVP. |
