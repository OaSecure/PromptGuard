# PromptGuard Chrome Extension

Manifest V3 + TypeScript extension scaffold for the PromptGuard DOM preflight MVP.

## Commands

```bash
npm install
npm run typecheck
npm test
npm run build
python tests/run_extension_checks.py prompt-preflight
python tests/run_extension_checks.py file-upload-preflight
```

## Scope

- Primary control: DOM preflight hook.
- No `webRequest` or DNR monitoring in MVP.
- Mock API mode is available before the self-host API is ready.
- Config, runtime messages, and Analyze responses are runtime-validated before cache/use/action.
- Do not persist prompt text, file content, extracted text, detected raw values, original filenames, full URL path/query, or full masked prompt.
- Prompt send attempts are intercepted through DOM click/Enter preflight. Shift+Enter and IME composition Enter stay available for text entry.
- Allow decisions replay the send once. Warn decisions require user confirmation. Mask decisions replace the input and require the user to send again manually. Block, timeout, and error paths fail closed.
- Text-file upload attempts are intercepted through DOM file input/drop preflight. Supported text files are read only in memory, original filenames are not sent, Allow/Warn attempt guarded replay, and replay failure shows reattach fallback.
- PDF, Office, OCR, archives, binary parsing, malware scanning, and file content masking are outside this MVP.

## Load

After `npm run build`, load `apps/extension/dist` as an unpacked extension in Chrome.
