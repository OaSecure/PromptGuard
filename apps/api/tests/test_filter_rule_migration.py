import importlib.util
from pathlib import Path

from app.models.filter_rule import FilterRule, FilterRuleVersion


def load_filter_rule_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260529_0004_filter_rules.py"
    )
    spec = importlib.util.spec_from_file_location("filter_rule_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_filter_rule_model_has_v10_contract_columns() -> None:
    columns = set(FilterRule.__table__.columns.keys())

    assert {
        "id",
        "workspace_id",
        "source",
        "kind",
        "category",
        "label",
        "description",
        "detector_key",
        "keyword",
        "pattern",
        "placeholder",
        "severity",
        "action",
        "enabled",
        "editable_fields",
        "config_json",
        "version",
        "archived_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_filter_rule_version_model_has_v10_contract_columns() -> None:
    columns = set(FilterRuleVersion.__table__.columns.keys())

    assert {
        "id",
        "filter_rule_id",
        "workspace_id",
        "version",
        "change_type",
        "before_json",
        "after_json",
        "changed_by",
        "created_at",
    }.issubset(columns)


def test_built_in_seed_rules_do_not_store_detector_logic() -> None:
    migration = load_filter_rule_migration()

    assert migration.BUILT_IN_DETECTOR_RULES
    for rule in migration.BUILT_IN_DETECTOR_RULES:
        assert rule["source"] == "built_in"
        assert rule["kind"] == "detector"
        assert rule["editable_fields"] == ["enabled", "severity", "action"]
        assert rule["config_json"] == {}
        assert "regex" not in rule
        assert "checksum" not in rule
        assert "parser" not in rule
