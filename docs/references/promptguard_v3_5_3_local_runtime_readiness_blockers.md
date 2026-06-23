# PromptGuard v3.5.3 Local Runtime Readiness Blockers

## Current Local Runtime Evidence

- Python runtime: `promptguard_publish/.venv`
- Torch CUDA: available, `torch 2.9.1+cu128`, device `NVIDIA GeForce RTX 2080`
- PaddleOCR: installed and CUDA-capable through `apps/api/requirements-ocr-gpu.txt`
- Runtime probe command:
  - `python apps/api/scripts/runtime_readiness.py --include-ocr`
- Runtime probe result:
  - `torch.cuda_available=true`
  - `paddleocr.cuda_available=true`
  - remaining blocker: `tesseract_kor_unavailable`

The runtime readiness probe must emit metadata-only JSON. It must not emit raw prompt, file content, OCR/extracted text, original filenames, raw detected values, vectors, logits, exact classifier scores, or full masked prompts.

## Tesseract Korean OCR Blocker

Current local blocker:

- `tesseract.exe` is not available on `PATH`.
- No existing `tesseract.exe` was found under:
  - `C:\Program Files`
  - `C:\Program Files (x86)`
  - `C:\Users\yhntg\AppData\Local\Programs`
  - `C:\Users\yhntg`
- `scoop`, `conda`, `mamba`, and `micromamba` are not installed.
- `winget install --id tesseract-ocr.tesseract --exact --accept-package-agreements --accept-source-agreements --silent` failed with `0x800704c7 : The operation was canceled by the user.`
- `winget install --id UB-Mannheim.TesseractOCR --exact --accept-package-agreements --accept-source-agreements --silent` failed with `0x800704c7 : The operation was canceled by the user.`

This means Tesseract Korean OCR is not ready in the current local runtime. The exact blocker is Windows installer completion, not CUDA, Python package installation, or PaddleOCR.

## Required Resolution

One of these must become true before Tesseract OCR can be claimed ready:

- Install Tesseract OCR manually or through an installer path that completes without user cancellation.
- Ensure `kor.traineddata` is present in the installed `tessdata` directory.
- Make `tesseract.exe` discoverable through `PATH`, or set `PROMPTGUARD_TESSERACT_BINARY_PATH` to the absolute executable path.
- Re-run `python apps/api/scripts/runtime_readiness.py --include-ocr`.

Completion evidence:

- `tesseract --list-langs` or the configured binary path lists `kor`.
- Runtime readiness no longer reports `tesseract_kor_unavailable`.
- OCR tests use metadata-only assertions and do not store or expose OCR text.
