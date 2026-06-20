## What this PR freezes

- Current `/prompts/analyze` Allow, Warn, Mask, and Block response shapes
- Current masking placeholder and `masked_prompt` behavior
- Current event, input, detection, commit, and idempotency write projection
- Current extension response validation and preflight behavior
- Current legacy `kind=text, source=file` payload behavior

## What this PR intentionally does not change

- No product, policy/action, schema, parser/OCR, upload/file_ref, route, service, or extension behavior changes
- No new architecture packages or validation rules

## Discovered but not fixed in PR0

- Metadata-only attachment input forces a Block even when the only detection requests Warn.
- Legacy file content is still transported as `kind=text, source=file`; v3.5 migration is deferred.

## Snapshot update rule

- Snapshots change only through explicit JSON fixture edits.
- Only documented UUID and timestamp fields are normalized.
- The normalizer never deletes fields, sorts arrays, or coerces business values or types.

## Test evidence

- API: `347 passed, 2 skipped`
- Extension: `113 passed`; typecheck and production build passed
