## Summary

- Separates the current public Analyze request models from the route into the HTTP interface boundary.
- Adapts supported legacy inputs into an internal v3 request using trusted authenticated identity.
- Isolates legacy `text/file` inputs in a compatibility sidecar instead of promoting them into v3 inputs.
- Keeps the current route on `legacy_view` so response, masking, idempotency, and EventStorage behavior remain unchanged.

## Compatibility and safety

- No native v3 public ingestion or new public required fields.
- No parser, OCR, temp storage, ML, policy, DB, response, or Extension changes.
- Parallel `prompt`, `input`, `file`, and `attachments` fields remain rejected.
- Internal v3 request and legacy sidecar are neither logged nor persisted.
- PR0 snapshots remain unchanged.

## Test evidence

- PR2 adapter/route plus PR0 golden tests: 22 passed
- API: 586 passed, 4 skipped
- Extension: 113 passed
- Extension typecheck and production build passed

## Dependency note

`npm ci` reports four existing dependency audit findings (1 low, 2 high, 1 critical); this PR does not change Extension dependencies.
