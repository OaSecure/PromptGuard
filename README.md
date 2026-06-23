# PromptGuard

## 한국어

PromptGuard는 AI 서비스로 프롬프트와 파일이 전송되기 전에 민감정보, 정책 위반 가능성, 마스킹 필요 여부를 검사하기 위한 프로젝트다.

이 저장소는 PromptGuard 제품 전체의 프로젝트 저장소다. 현재 구현된 첫 번째 클라이언트는 `apps/extension`의 Chrome Extension MVP이며, 이후 Analyze API, 정책 설정, 배포/운영 문서, 추가 클라이언트가 이 프로젝트 경계 안에서 확장될 수 있다.

### 현재 포함된 구성

- `apps/extension`: Manifest V3 기반 Chrome Extension MVP.
- `apps/api`: Analyze API와 민감정보 감지 파이프라인.
- `models`: 실제 모델 파일을 두는 로컬 mount 위치와 샘플 manifest 문서.
- `docs/references`: 구현 상태, 개발 기준, Analyze 연동 참고 문서.
- 루트 문서: 프로젝트 범위, 보안 경계, 라이선스, 실행 방법을 빠르게 확인하기 위한 문서.

### 현재 구현된 MVP

현재 동작하는 앱은 Chrome Extension이다. 이 확장프로그램은 ChatGPT와 유사한 페이지에서 사용자가 prompt 전송이나 텍스트 파일 첨부를 시도할 때 DOM preflight 방식으로 잠깐 멈추고 Analyze 흐름을 실행한다.

- Prompt send는 버튼 클릭과 Enter 전송을 가로채 검사 전 실제 전송이 나가지 않게 한다.
- Shift+Enter와 IME composition Enter는 일반 텍스트 입력으로 유지한다.
- 텍스트 파일 업로드는 file input 변경과 drag/drop을 가로채 검사 전 실제 첨부가 진행되지 않게 한다.
- 지원 파일은 텍스트 기반 파일이며, 파일 내용은 메모리에서만 읽는다.
- Mask 결과는 입력창을 `masked_prompt`로 바꾸고 사용자가 다시 직접 전송하게 한다.
- Block, timeout, malformed response, API error는 fail-closed로 처리한다.
- MVP는 `webRequest`나 Declarative Net Request 기반 네트워크 감시를 사용하지 않는다.
- PDF, Office, OCR, archive, binary parsing, malware scanning, file content masking은 현재 범위 밖이다.

### Privacy Boundary

PromptGuard는 다음 값을 저장하거나 로그로 남기지 않아야 한다.

- raw prompt text
- file content
- extracted text
- detected raw values
- original filenames
- full masked prompts
- full URL path/query

### Extension 실행과 검증

확장프로그램 작업은 `apps/extension`에서 실행한다.

```bash
cd apps/extension
npm install
npm run typecheck
npm test
npm run build
```

저장소 루트에서는 wrapper 검사를 실행할 수 있다.

```bash
python apps/extension/tests/run_extension_checks.py prompt-preflight
python apps/extension/tests/run_extension_checks.py file-upload-preflight
python apps/extension/tests/run_extension_checks.py all
```

빌드 후 Chrome에서 `apps/extension/dist`를 unpacked extension으로 로드한다.

### 모델 artifact 다운로드

PromptGuard 코드는 GitHub에서 배포하고, 학습된 모델 artifact는 Hugging Face Hub에서 배포한다. 실제 `.joblib`, `.safetensors`, tokenizer 파일은 GitHub 저장소에 커밋하지 않는다.

저장소 루트에서 다음 명령을 실행하면 `models/` 아래에 현재 v287 context classifier artifact가 내려받아진다.

```bash
pip install "huggingface_hub[hf_xet]"
huggingface-cli download OASecure/promptguard-context-classifier \
  --revision v287-20260623 \
  --include "models/*" \
  --local-dir .
```

Docker Compose 실행 시 `compose.yml`은 `./models`를 API 컨테이너의 `/opt/promptguard/models`에 read-only로 mount한다. 런타임을 켜려면 `.env`에서 다음 값을 사용한다.

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
```

### API 로컬 CUDA 런타임 확인

로컬에서 실제 모델 런타임을 검증할 때는 저장소 루트에 전용 venv를 만들고 CUDA용 PyTorch wheel을 설치한다.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python -m pip install -r apps/api/requirements.txt -r apps/api/requirements-ml.txt
.venv\Scripts\python -m pip install --force-reinstall -r apps/api/requirements-ml-cu128.txt
```

현재 Python 런타임이 CUDA를 쓰는지 확인한다.

```bash
cd apps/api
..\..\.venv\Scripts\python scripts/runtime_readiness.py
```

## English

PromptGuard is a project for inspecting prompts and files before they leave a user workflow for an AI service. Its goal is to detect sensitive data, policy issues, and masking requirements before submission.

This repository represents the PromptGuard product project. The first implemented client is the Chrome Extension MVP under `apps/extension`; future Analyze API work, policy configuration, deployment documentation, and additional clients can grow inside the same project boundary.

### Current Contents

- `apps/extension`: Manifest V3 Chrome Extension MVP.
- `apps/api`: Analyze API and sensitive-data detection pipeline.
- `models`: local mount location and sample manifests for model artifacts.
- `docs/references`: implementation status, development references, and Analyze integration notes.
- Root documents: project overview, security boundary, license, and quick operating commands.

### Current MVP

The currently implemented app is a Chrome Extension. It uses DOM preflight hooks on supported ChatGPT-like pages before prompt sends and text-file upload attempts proceed.

- Prompt sends are intercepted through click and Enter preflight.
- Shift+Enter and IME composition Enter remain available for text entry.
- Text-file uploads are intercepted through file input and drag/drop preflight.
- Supported files are text-based and read in memory only.
- Mask decisions replace the input with `masked_prompt` and require the user to send again manually.
- Block, timeout, malformed response, and API error paths fail closed.
- The MVP does not use `webRequest` or Declarative Net Request network monitoring.
- PDF, Office, OCR, archives, binary parsing, malware scanning, and file content masking are out of scope.

### Privacy Boundary

PromptGuard must not persist or log raw prompt text, file content, extracted text, detected raw values, original filenames, full masked prompts, or full URL path/query.

### Extension Commands

Run from `apps/extension`:

```bash
npm install
npm run typecheck
npm test
npm run build
```

Run wrapper checks from the repository root:

```bash
python apps/extension/tests/run_extension_checks.py prompt-preflight
python apps/extension/tests/run_extension_checks.py file-upload-preflight
python apps/extension/tests/run_extension_checks.py all
```

After `npm run build`, load `apps/extension/dist` as an unpacked extension in Chrome.

### Model Artifacts

PromptGuard distributes application code through GitHub and trained model artifacts through Hugging Face Hub. Real `.joblib`, `.safetensors`, and tokenizer files are not committed to this GitHub repository.

Run this from the repository root to download the current v287 context classifier into `models/`:

```bash
pip install "huggingface_hub[hf_xet]"
huggingface-cli download OASecure/promptguard-context-classifier \
  --revision v287-20260623 \
  --include "models/*" \
  --local-dir .
```

`compose.yml` mounts `./models` into the API container at `/opt/promptguard/models` as read-only. Enable the runtime with:

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
```

### API Local CUDA Runtime Check

For local real-model runtime verification, create a repository-local venv and install the CUDA PyTorch wheel.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python -m pip install -r apps/api/requirements.txt -r apps/api/requirements-ml.txt
.venv\Scripts\python -m pip install --force-reinstall -r apps/api/requirements-ml-cu128.txt
```

Check whether the active Python runtime can use CUDA.

```bash
cd apps/api
..\..\.venv\Scripts\python scripts/runtime_readiness.py
```
