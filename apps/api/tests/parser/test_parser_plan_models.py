import pytest
from app.parser.models import ParserExecutionPlan, ParserFallbackRule, ParserPlanStep
from pydantic import ValidationError


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


@pytest.mark.parametrize("second_target", ["fallback-one", "fallback-two"])
def test_duplicate_fallback_trigger_route_is_rejected(second_target):
    with pytest.raises(ValidationError):
        ParserExecutionPlan(
            plan_id="ambiguous-fallback",
            plan_kind="native_text",
            steps=(
                _step("primary", 0),
                _step("fallback-one", 1, mode="fallback"),
                _step("fallback-two", 2, mode="fallback"),
            ),
            fallback_rules=(
                ParserFallbackRule(
                    rule_id="rule-one",
                    source_step_id="primary",
                    trigger="step_failed",
                    target_step_id="fallback-one",
                    ordinal=0,
                ),
                ParserFallbackRule(
                    rule_id="rule-two",
                    source_step_id="primary",
                    trigger="step_failed",
                    target_step_id=second_target,
                    ordinal=1,
                ),
            ),
        )


def test_different_triggers_can_share_one_fallback_target():
    plan = ParserExecutionPlan(
        plan_id="trigger-specific-fallback",
        plan_kind="native_text",
        steps=(_step("primary", 0), _step("fallback", 1, mode="fallback")),
        fallback_rules=(
            ParserFallbackRule(
                rule_id="unavailable",
                source_step_id="primary",
                trigger="adapter_unavailable",
                target_step_id="fallback",
                ordinal=0,
            ),
            ParserFallbackRule(
                rule_id="initialization",
                source_step_id="primary",
                trigger="adapter_initialization_failed",
                target_step_id="fallback",
                ordinal=1,
            ),
        ),
    )

    assert [rule.rule_id for rule in plan.fallback_rules] == ["unavailable", "initialization"]


def test_different_sources_can_share_one_fallback_target():
    plan = ParserExecutionPlan(
        plan_id="shared-fallback",
        plan_kind="native_text",
        steps=(
            _step("primary-one", 0),
            _step("primary-two", 1),
            _step("fallback", 2, mode="fallback"),
        ),
        fallback_rules=(
            ParserFallbackRule(
                rule_id="rule-one",
                source_step_id="primary-one",
                trigger="step_failed",
                target_step_id="fallback",
                ordinal=0,
            ),
            ParserFallbackRule(
                rule_id="rule-two",
                source_step_id="primary-two",
                trigger="step_failed",
                target_step_id="fallback",
                ordinal=1,
            ),
        ),
    )

    assert [rule.source_step_id for rule in plan.fallback_rules] == ["primary-one", "primary-two"]


def test_fallback_mode_step_cannot_be_a_fallback_source():
    with pytest.raises(ValidationError):
        ParserExecutionPlan(
            plan_id="fallback-chain",
            plan_kind="native_text",
            steps=(
                _step("primary", 0),
                _step("fallback-one", 1, mode="fallback"),
                _step("fallback-two", 2, mode="fallback"),
            ),
            fallback_rules=(
                ParserFallbackRule(
                    rule_id="fallback-chain",
                    source_step_id="fallback-one",
                    trigger="step_failed",
                    target_step_id="fallback-two",
                    ordinal=0,
                ),
            ),
        )
