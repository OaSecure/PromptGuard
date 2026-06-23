import json
import re
from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "fixtures" / "contracts"
EVENT_DENIED = {"raw_text", "raw_prompt", "parsed_text", "extracted_text", "ocr_text", "normalized_text", "atom_text", "segment_text", "raw_value", "matched_value", "secret_value", "original_file_name", "filename", "file_name", "file_ref", "temp_scope_id", "temp_file_path", "local_path", "rendered_image_path", "embedding", "embedding_vector", "segment_vector", "raw_logits", "category_scores", "suppressor_scores", "exact_score", "size_bytes", "masked_prompt", "full_masked_prompt"}
RUNTIME_RAW_DENIED = {"raw_value", "matched_value", "secret_value", "original_file_name", "filename", "file_name", "temp_file_path", "local_path", "rendered_image_path", "embedding_vector", "raw_logits"}


def walk(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key, nested
            yield from walk(nested)
    elif isinstance(value, list):
        for nested in value: yield from walk(nested)


def test_event_fixtures_use_strict_storage_denylist():
    for path in (FIXTURES / "event").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        denied = {key for key, _ in walk(value)} & EVENT_DENIED
        assert not denied, f"{path.name}: {sorted(denied)}"


def test_runtime_fixtures_forbid_raw_values_and_require_opaque_file_refs():
    for path in (FIXTURES / "runtime").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        denied = {key for key, _ in walk(value)} & RUNTIME_RAW_DENIED
        assert not denied, f"{path.name}: {sorted(denied)}"
        for key, nested in walk(value):
            if key == "file_ref" and nested is not None:
                assert re.fullmatch(r"fr_[a-z0-9_]+", nested)
                assert not any(token in nested for token in ("/", "\\", "://", ".pdf", ".docx", "image/"))


def test_contract_fixture_order_and_ids_are_deterministic():
    for path in FIXTURES.rglob("*.json"):
        first = json.loads(path.read_text(encoding="utf-8"))
        second = json.loads(path.read_text(encoding="utf-8"))
        assert first == second
