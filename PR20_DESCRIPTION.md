## Summary

Adds PR20 Static Quality Gate using baseline ratchet.

This PR introduces CI-enforced static quality checks for Ruff, mypy, import-linter, privacy/static source scanning, hidden Unicode/Bidi/control character detection, and Radon complexity.

Existing violations from current main are captured in explicit baselines. New findings, finding count increases, stale baselines, new architecture boundary violations, privacy persistence violations, hidden Unicode/control characters, and complexity regressions fail CI.

No public behavior, policy behavior, database schema, response shape, masking behavior, parser behavior, scanner behavior, ML behavior, or EventStorage projection is changed.

## Changes

- Added pinned quality dependencies
- Added Static Quality CI job
- Added Ruff and mypy ratchet gates
- Added import-linter architecture boundary gate
- Added privacy/static source and Unicode scans
- Added Radon complexity ratchet gate
- Added deterministic baseline comparison and self-tests
- Preserved existing backend/frontend/Docker CI jobs

## Baseline Policy

PR20 bootstraps explicit baselines from current main because no prior baseline exists. After PR20 is merged, baseline entry additions and count increases fail by default. Stale baseline entries fail and require baseline reduction. Baseline deletion/reduction is allowed and encouraged.

## Non-goals

- No public API or production behavior changes
- No DB schema or policy changes
- No parser/OCR/model behavior changes
- No large refactoring
