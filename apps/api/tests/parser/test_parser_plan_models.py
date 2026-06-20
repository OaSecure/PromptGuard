import pytest
from pydantic import ValidationError

from app.parser.models import ParserExecutionPlan, ParserFallbackRule, ParserPlanStep


def _step(step_id="one", ordinal=0, step_kind="native_text_extract", mode="always"):
    return ParserPlanStep(
        step_id=step_id,
        ordinal=ordinal,
        step_kind=step_kind,
        capability_id=f"cap-{step_kind}",
        execution_mode=mode,
    )


def test_empty_steps_allowed_only_for_metadata_only_and_unsupported():
    for kind in ("metadata_only", "unsupported"):
        assert ParserExecutionPlan(plan_id=kind, plan_kind=kind, steps=()).steps == ()
    with pytest.raises(ValidationError):
        ParserExecutionPlan(plan_id="bad", plan_kind="native_text", steps=())


def test_duplicate_ordinal_is_rejected():
    with pytest.raises(ValidationError):
        ParserExecutionPlan(
            plan_id="bad",
            plan_kind="native_text",
            steps=(_step("one", 0), _step("two", 0)),
        )


def test_unordered_steps_are_rejected_not_sorted():
    with pytest.raises(ValidationError):
        ParserExecutionPlan(
            plan_id="bad",
            plan_kind="native_text",
            steps=(_step("two", 1), _step("one", 0)),
        )


def test_fallback_rule_requires_trigger():
    with pytest.raises(ValidationError):
        ParserFallbackRule(
            rule_id="rule", source_step_id="one", trigger=None, target_step_id="fallback", ordinal=0
        )


def test_fallback_target_must_exist_and_be_fallback_step():
    with pytest.raises(ValidationError):
        ParserExecutionPlan(
            plan_id="bad",
            plan_kind="native_text",
            steps=(_step(),),
            fallback_rules=(ParserFallbackRule(
                rule_id="rule", source_step_id="one", trigger="step_failed",
                target_step_id="missing", ordinal=0
            ),),
        )
