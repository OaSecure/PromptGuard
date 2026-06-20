import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FORBIDDEN_STORAGE_KEYS = {
    "content", "raw_prompt", "prompt", "original_filename", "file_content",
    "base64", "masked_prompt", "raw_secret", "detected_raw_value", "ocr_text",
    "extracted_text", "normalized_text", "atom_text", "segment_text",
    "embedding", "embedding_vector", "classifier_score",
}


def normalize_dynamic_fields(value: Any) -> Any:
    """Replace only known runtime values while preserving shape and types."""
    if isinstance(value, dict):
        return {
            key: _normalize_named_value(key, normalize_dynamic_fields(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_dynamic_fields(item) for item in value]
    if isinstance(value, UUID):
        return "<UUID>"
    if isinstance(value, datetime):
        return "<TIMESTAMP>"
    return value


def _normalize_named_value(key: str, value: Any) -> Any:
    if key in {"event_id", "id", "user_id"} and isinstance(value, str):
        try:
            UUID(value)
        except ValueError:
            return value
        return "<UUID>"
    if key in {"checked_at", "created_at", "expires_at"} and isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return "<TIMESTAMP>"
    return value


def assert_matches_snapshot(name: str, actual: Any) -> None:
    expected = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert normalize_dynamic_fields(actual) == expected


def assert_storage_privacy(value: Any) -> None:
    def visit(item: Any) -> None:
        if isinstance(item, dict):
            forbidden = FORBIDDEN_STORAGE_KEYS.intersection(key.casefold() for key in item)
            assert not forbidden, f"forbidden storage keys: {sorted(forbidden)}"
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
