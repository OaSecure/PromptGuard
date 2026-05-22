# PromptGuard

PromptGuard is a Chrome Extension MVP that performs DOM preflight inspection before prompt submissions and text-file uploads leave supported ChatGPT-like pages.

## Scope

- Primary control: DOM preflight hooks for prompt send and text-file upload attempts.
- Prompt sends are intercepted through click and Enter preflight. Shift+Enter and IME composition Enter remain available for text entry.
- File uploads are intercepted through file input and drop preflight.
- Supported file handling is text-only and in-memory for this MVP.
- Mask decisions replace the prompt input and require the user to send again manually.
- Block, timeout, malformed response, and error paths fail closed.
- No network monitoring through browser request hooks is used in this MVP.
- PDF, Office files, OCR, archives, binary parsing, malware scanning, and file content masking are out of scope.

## Privacy Boundary

PromptGuard must not persist or log raw prompt text, file content, extracted text, detected raw values, original filenames, full masked prompts, or full URL path/query.

## Extension Commands

Run from `apps/extension`:

```bash
npm install
npm run typecheck
npm test
npm run build
```

Run the extension wrapper checks from the repository root:

```bash
python apps/extension/tests/run_extension_checks.py prompt-preflight
python apps/extension/tests/run_extension_checks.py file-upload-preflight
```

## Load In Chrome

After `npm run build`, load `apps/extension/dist` as an unpacked extension in Chrome.
