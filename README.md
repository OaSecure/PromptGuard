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
hf download OASecure/promptguard-context-classifier \
  --revision v287-20260623 \
  --include "models/*" \
  --local-dir .
```

Qwen embedding model도 런타임 시작 전에 반드시 로컬 artifact로 내려받아야 한다. Torch worker는 요청 처리 중 Hugging Face에서 모델을 내려받지 않으며, 아래 경로에 모델이 없으면 context ML runtime을 사용할 수 없다.

```bash
hf download Qwen/Qwen3-Embedding-0.6B \
  --local-dir models/qwen3-embedding-0.6b
```

Docker Compose 실행 시 `compose.yml`은 `./models`를 API 컨테이너의 `/opt/promptguard/models`에 read-only로 mount한다. 런타임을 켜려면 `.env`에서 다음 값을 사용한다.

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
PROMPTGUARD_QWEN_EMBEDDING_MODEL_PATH=/opt/promptguard/models/qwen3-embedding-0.6b
PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
```

### Docker 단일 서버 실행

Docker Compose 기본 배포는 API 컨테이너 하나가 API, Analyze runtime, dashboard 정적 파일을 함께 제공한다.

```bash
cp .env.example .env
docker compose up --build
```

기본 접속 주소는 다음과 같다.

```text
Dashboard: http://localhost:8000/dashboard/
API health: http://localhost:8000/healthz
API ready: http://localhost:8000/readyz
```

Chrome Extension에서 사용할 주소는 자동 추측하지 않는다. 서버를 띄우기 전에 `.env`에 Extension 사용자가 실제로 접속할 수 있는 API origin을 명시한다. Dashboard URL은 `/dashboard/`가 들어가지만, Extension API URL은 `/dashboard/` 같은 경로 없이 origin만 적는다.

```env
PROMPTGUARD_API_PORT=8000
PROMPTGUARD_EXTENSION_API_URL=http://192.168.0.25:8000
PROMPTGUARD_DASHBOARD_PUBLIC_URL=http://192.168.0.25:8000/dashboard/
```

외부 도메인이나 포트포워딩을 사용할 때는 같은 방식으로 공개 주소를 적는다.

```env
PROMPTGUARD_API_PORT=8000
PROMPTGUARD_EXTENSION_API_URL=https://promptguard.example.com
PROMPTGUARD_DASHBOARD_PUBLIC_URL=https://promptguard.example.com/dashboard/
```

Dashboard의 서버 상태 화면은 `PROMPTGUARD_EXTENSION_API_URL`이 유효할 때만 복사 버튼을 보여준다. 값이 비어 있거나 `localhost`, `127.0.0.1`, Docker 내부 `172.16.0.0/12` 주소, PostgreSQL 포트 `5432`, `/dashboard/` 경로가 들어간 URL이면 설정 오류로 표시된다.

### API 로컬 CUDA 런타임 확인

Docker 배포는 API 이미지 하나를 사용한다. 이미지 내부에서는 Python 환경을 세 개로 나눈다.

- `/opt/venvs/api`: FastAPI 서버, DB, queue, 공통 parser runtime.
- `/opt/venvs/paddle`: PaddleOCR GPU worker runtime.
- `/opt/venvs/torch`: Torch GPU model worker runtime.

PaddleOCR와 Torch는 서로 다른 NVIDIA Python wheel 버전을 요구할 수 있으므로 같은 Python 환경에 함께 설치하지 않는다. API 프로세스는 외부 공개 API를 유지하고, 내부 worker process가 각 전용 venv에서 OCR 또는 model inference를 실행한다.

로컬에서 실제 모델 런타임을 검증할 때도 같은 분리 구조를 사용한다.

```bash
python -m venv .venv-api
.venv-api\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-api\Scripts\python -m pip install -r apps/api/requirements.txt

python -m venv .venv-paddle
.venv-paddle\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-paddle\Scripts\python -m pip install -r apps/api/requirements-paddle-gpu.txt

python -m venv .venv-torch
.venv-torch\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-torch\Scripts\python -m pip install -r apps/api/requirements-torch-gpu.txt
```

Torch worker Python 런타임이 CUDA를 쓰는지 확인한다.

```bash
cd apps/api
..\..\.venv-torch\Scripts\python scripts/runtime_readiness.py --target torch
```

PaddleOCR worker 런타임을 확인하려면 다음 명령을 사용한다. 이 출력은 설치 여부, CUDA 사용 가능 여부, blocker 코드만 포함하고 OCR 원문이나 파일명을 출력하지 않는다.

```bash
cd apps/api
..\..\.venv-paddle\Scripts\python scripts/runtime_readiness.py --target ocr
```

Windows에서 Tesseract가 PATH에 없으면 `PROMPTGUARD_TESSERACT_BINARY_PATH`에 `tesseract.exe` 절대경로를 지정한다. 한국어 OCR은 `tesseract --list-langs` 결과에 `kor`가 있어야 준비 완료로 판단한다.

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
hf download OASecure/promptguard-context-classifier \
  --revision v287-20260623 \
  --include "models/*" \
  --local-dir .
```

Download the Qwen embedding model before starting the runtime. The Torch worker does not download this model from Hugging Face while handling requests; if this local artifact is missing, the context ML runtime is unavailable.

```bash
hf download Qwen/Qwen3-Embedding-0.6B \
  --local-dir models/qwen3-embedding-0.6b
```

`compose.yml` mounts `./models` into the API container at `/opt/promptguard/models` as read-only. Enable the runtime with:

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
PROMPTGUARD_QWEN_EMBEDDING_MODEL_PATH=/opt/promptguard/models/qwen3-embedding-0.6b
PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
```

### Docker Single-Server Runtime

The default Docker Compose deployment uses one API container to serve API routes, the Analyze runtime, and dashboard static files together.

```bash
cp .env.example .env
docker compose up --build
```

Default URLs:

```text
Dashboard: http://localhost:8000/dashboard/
API health: http://localhost:8000/healthz
API ready: http://localhost:8000/readyz
```

The Chrome Extension address is not guessed automatically. Before starting the server, set the API origin that extension user computers can actually reach. The Dashboard URL includes `/dashboard/`, but the Extension API URL is the origin only and must not include `/dashboard/` or another path.

```env
PROMPTGUARD_API_PORT=8000
PROMPTGUARD_EXTENSION_API_URL=http://192.168.0.25:8000
PROMPTGUARD_DASHBOARD_PUBLIC_URL=http://192.168.0.25:8000/dashboard/
```

For an external domain or port-forwarded deployment, set the public address instead:

```env
PROMPTGUARD_API_PORT=8000
PROMPTGUARD_EXTENSION_API_URL=https://promptguard.example.com
PROMPTGUARD_DASHBOARD_PUBLIC_URL=https://promptguard.example.com/dashboard/
```

The dashboard Server Status screen shows a copy button only when `PROMPTGUARD_EXTENSION_API_URL` is valid. Empty values, `localhost`, `127.0.0.1`, Docker-internal `172.16.0.0/12` addresses, PostgreSQL port `5432`, and URLs with `/dashboard/` paths are shown as configuration errors.

### API Local CUDA Runtime Check

The Docker deployment still uses one API image. Inside that image, Python is split into three runtime environments:

- `/opt/venvs/api`: FastAPI server, DB, queue, and common parser runtime.
- `/opt/venvs/paddle`: PaddleOCR GPU worker runtime.
- `/opt/venvs/torch`: Torch GPU model worker runtime.

PaddleOCR and Torch may require incompatible NVIDIA Python wheels, so they are not installed into the same Python environment. The API process keeps the public API stable, and internal worker processes run OCR or model inference from their dedicated venvs.

For local real-model runtime verification, use the same split-runtime layout.

```bash
python -m venv .venv-api
.venv-api\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-api\Scripts\python -m pip install -r apps/api/requirements.txt

python -m venv .venv-paddle
.venv-paddle\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-paddle\Scripts\python -m pip install -r apps/api/requirements-paddle-gpu.txt

python -m venv .venv-torch
.venv-torch\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv-torch\Scripts\python -m pip install -r apps/api/requirements-torch-gpu.txt
```

Check whether the Torch worker Python runtime can use CUDA.

```bash
cd apps/api
..\..\.venv-torch\Scripts\python scripts/runtime_readiness.py --target torch
```

Use this command to check the PaddleOCR worker runtime. The output contains dependency state, CUDA availability, and blocker codes only; it does not print OCR text or filenames.

```bash
cd apps/api
..\..\.venv-paddle\Scripts\python scripts/runtime_readiness.py --target ocr
```

On Windows, set `PROMPTGUARD_TESSERACT_BINARY_PATH` to the absolute `tesseract.exe` path when Tesseract is not on PATH. Korean OCR is considered ready only when `tesseract --list-langs` includes `kor`.

