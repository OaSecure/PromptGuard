## Summary

- Adds internal v3.5 handoff schemas organized by responsibility.
- Adds implementation-free parser, OCR, ML, policy, event, clock, ID, and storage Protocol ports.
- Keeps `InputEnvelope` local to `application/analyze` and enforces that boundary with AST tests.
- Adds deterministic runtime/event contract fixtures with distinct privacy rules.

## Safety boundaries

- No public `/prompts/analyze` request or response behavior changes.
- No route, DB schema, Extension, policy decision, EventStorage, parser/OCR, or ML runtime wiring changes.
- No existing production type migration or removal.
- No real parser, OCR, model, or temporary storage implementation.
- Existing PR0 snapshots remain unchanged and passing.

## Test evidence

- PR1 contract tests: 11 passed
- API: 526 passed, 4 skipped
- Extension: 113 passed
- Extension typecheck and production build passed

## Review ownership

- 담당자 2: parser/OCR/temp-file schemas and ports
- 담당자 3: normalization/scanner/analysis/ML schemas and ports
