## Summary

Adds deterministic, fake-heavy integration coverage for the currently implemented PromptGuard boundaries. This is not a production full-pipeline implementation PR.

## Coverage

- Real `/prompts/analyze` HTTP behavior for Allow, Warn, Mask, Block, converted paste, and file-reference fail-closed behavior.
- Response-only masking and EventStorage privacy projection.
- Test-only encrypted temp-file, resolver, parser runner, Policy Orchestrator composition.
- Structured parser failure projection and candidate-only verifier behavior.
- Deterministic replay with fixed inputs and stable projections.

## Known limitation

Production `file_reference -> parser` wiring does not currently exist. PR19 does not add or simulate that production route wiring; the parser composition is tests-only and remains a future production integration target.

## PR18 runtime-only baseline waiver

Additional PR18 implementation is intentionally skipped. PR19 uses the runtime gates already present in `main`: Qwen frozen validation, classifier/verifier artifact manifest validation, and the candidate-only verifier contract. Dataset training, `hard_eval`, threshold tuning, model selection, online learning, and artifact generation are out of scope. Real OCR and real model profiles are not part of default CI.

## Verification

- `pytest apps/api/tests/integration`
- Existing API regression suites and full API pytest
- Existing Extension test, typecheck, build, and contract checks
