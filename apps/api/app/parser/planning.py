from collections.abc import Mapping
from typing import cast

from app.parser.models import (
    ParserAdapterCapability,
    ParserExecutionPlan,
    ParserFallbackRule,
    ParserLicensePolicy,
    ParserPlanConfig,
    ParserPlanRequest,
    ParserPlanResolution,
    ParserPlanStep,
    PlanKind,
    StepKind,
    sanitized_failure,
)

PLAN_STEPS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "wrap_text": (("wrap-text", "wrap_text", "always"),),
    "native_text": (("native-text", "native_text_extract", "always"),),
    "pdf_native_ocr": (("pdf-native-ocr", "pdf_native_ocr", "always"),),
    "pdf_native_then_page_ocr": (
        ("pdf-native", "pdf_native_text_extract", "always"),
        ("pdf-coverage", "pdf_coverage_evaluate", "always"),
        ("pdf-render", "render_ocr_candidate_pages", "always"),
        ("ocr-primary", "ocr_primary", "always"),
        ("ocr-fallback", "ocr_fallback", "fallback"),
        ("merge-blocks", "merge_blocks", "always"),
    ),
    "pdf_native": (("pdf-native", "pdf_native_text_extract", "always"),),
    "image_ocr": (
        ("image-ocr-primary", "image_ocr", "always"),
        ("image-ocr-fallback", "ocr_fallback", "fallback"),
    ),
    "office_parse": (("office-parse", "office_parse", "always"),),
    "spreadsheet_parse": (("spreadsheet-parse", "spreadsheet_parse", "always"),),
    "slide_parse": (("slide-parse", "slide_parse", "always"),),
    "code_parse": (("code-parse", "code_parse", "always"),),
}

PLAN_RULES = {
    "pdf_native_then_page_ocr": (
        ("ocr-unavailable", "ocr-primary", "adapter_unavailable", "ocr-fallback"),
        ("ocr-init-failed", "ocr-primary", "adapter_initialization_failed", "ocr-fallback"),
    ),
    "image_ocr": (
        ("image-ocr-unavailable", "image-ocr-primary", "adapter_unavailable", "image-ocr-fallback"),
        ("image-ocr-init-failed", "image-ocr-primary", "adapter_initialization_failed", "image-ocr-fallback"),
    ),
}


class ParserPlanResolver:
    def __init__(
        self,
        config: ParserPlanConfig | None = None,
        capabilities: tuple[ParserAdapterCapability, ...] = (),
        license_policy: ParserLicensePolicy | None = None,
    ) -> None:
        self._config = config or ParserPlanConfig()
        self._capabilities = tuple(capabilities)
        self._license_policy = license_policy or ParserLicensePolicy()

    def resolve(self, request) -> ParserPlanResolution:
        return self.resolve_plan(ParserPlanRequest(
            payload=request.payload,
            resolved_file=request.resolved_file,
            config=self._config,
            capabilities=self._capabilities,
            license_policy=self._license_policy,
        ))

    def resolve_plan(self, request: ParserPlanRequest) -> ParserPlanResolution:
        plan_kind = self._plan_kind(request)
        if plan_kind in {"metadata_only", "unsupported"}:
            return ParserPlanResolution(plan=ParserExecutionPlan(
                plan_id=f"plan-{plan_kind}", plan_kind=plan_kind, steps=()
            ))
        capability_by_kind: dict[str, ParserAdapterCapability] = {
            kind: capability
            for capability in request.capabilities
            if capability.enabled
            for kind in capability.step_kinds
        }
        plan_kind = self._select_available_plan_kind(request, plan_kind, capability_by_kind)
        if not request.config.enable_native_parsing and plan_kind not in {"image_ocr"}:
            return ParserPlanResolution(failure=sanitized_failure("PARSER_DISABLED"))
        if not request.config.enable_ocr and plan_kind in {"image_ocr", "pdf_native_then_page_ocr"}:
            return ParserPlanResolution(failure=sanitized_failure("OCR_DISABLED"))

        definitions = PLAN_STEPS[plan_kind]
        for _, step_kind, _ in definitions:
            capability = capability_by_kind.get(step_kind)
            if capability is None:
                return ParserPlanResolution(failure=sanitized_failure("UNSUPPORTED_FILE_KIND"))
            if capability.capability_id in request.license_policy.denied_capability_ids:
                return ParserPlanResolution(failure=sanitized_failure("LICENSE_POLICY_VIOLATION"))

        steps = tuple(
            ParserPlanStep(
                step_id=step_id,
                ordinal=ordinal,
                step_kind=cast(StepKind, step_kind),
                capability_id=capability_by_kind[step_kind].capability_id,
                execution_mode=mode,
            )
            for ordinal, (step_id, step_kind, mode) in enumerate(definitions)
        )
        rules = tuple(
            ParserFallbackRule(
                rule_id=rule_id,
                source_step_id=source,
                trigger=trigger,
                target_step_id=target,
                ordinal=ordinal,
            )
            for ordinal, (rule_id, source, trigger, target) in enumerate(PLAN_RULES.get(plan_kind, ()))
        )
        return ParserPlanResolution(plan=ParserExecutionPlan(
            plan_id=f"plan-{plan_kind}", plan_kind=plan_kind, steps=steps, fallback_rules=rules
        ))

    @staticmethod
    def _select_available_plan_kind(
        request: ParserPlanRequest,
        plan_kind: PlanKind,
        capability_by_kind: Mapping[str, ParserAdapterCapability],
    ) -> PlanKind:
        if plan_kind == "pdf_native_then_page_ocr" and "pdf_native_ocr" in capability_by_kind:
            return "pdf_native_ocr"
        if plan_kind == "pdf_native_then_page_ocr" and ParserPlanResolver._should_use_pdf_native_only(
            request, capability_by_kind
        ):
            return "pdf_native"
        return plan_kind

    @staticmethod
    def _should_use_pdf_native_only(
        request: ParserPlanRequest,
        capability_by_kind: Mapping[str, ParserAdapterCapability],
    ) -> bool:
        if request.payload.file_kind != "pdf" or "pdf_native_text_extract" not in capability_by_kind:
            return False
        if not request.config.enable_ocr:
            return True
        return any(step_kind not in capability_by_kind for _, step_kind, _ in PLAN_STEPS["pdf_native_then_page_ocr"])

    @staticmethod
    def _plan_kind(request: ParserPlanRequest) -> PlanKind:
        requirement = request.payload.extraction_requirement
        kind = request.payload.file_kind
        if requirement == "metadata_only":
            return "metadata_only"
        if requirement in {"unsupported", "not_applicable"}:
            return "unsupported"
        if requirement == "wrap_text":
            return "wrap_text"
        if kind == "unknown" or kind is None:
            return "unsupported"
        mapping: dict[str, PlanKind] = {
            "plain_text": "native_text",
            "pdf": "pdf_native_then_page_ocr",
            "image": "image_ocr",
            "office_document": "office_parse",
            "spreadsheet": "spreadsheet_parse",
            "slide": "slide_parse",
            "code": "code_parse",
        }
        return mapping.get(kind, "unsupported")
