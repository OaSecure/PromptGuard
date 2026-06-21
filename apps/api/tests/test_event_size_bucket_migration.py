import importlib.util
from pathlib import Path

import pytest

from app.privacy.size_bucket import persistence_size_bucket

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260621_0012_event_input_size_bucket.py"
SPEC = importlib.util.spec_from_file_location("event_size_bucket_migration", MIGRATION_PATH)
assert SPEC and SPEC.loader
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "empty"), (1, "small"), (1_048_575, "small"), (1_048_576, "small"),
     (1_048_577, "medium"), (10_485_759, "medium"), (10_485_760, "medium"), (10_485_761, "large")],
)
def test_canonical_persistence_bucket_boundaries(value, expected):
    assert persistence_size_bucket(value) == expected


def test_frozen_migration_mapping_matches_runtime_contract():
    sql = MIGRATION.BUCKET_CASE_SQL.replace(" ", "").replace("\n", "")
    assert "size_bytes=0then'empty'" in sql
    assert "size_bytes<=1048576then'small'" in sql
    assert "size_bytes<=10485760then'medium'" in sql
    assert "else'large'" in sql
    assert "file_reference" in MIGRATION.NEW_KIND_CONSTRAINT
