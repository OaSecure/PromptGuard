import pytest

from app.parser.fakes import FakeParserStepAdapter
from app.parser.models import ParserAdapterCapability, ParserBoundaryError
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration


def _capability(
    capability_id="cap-wrap", step_kinds=("wrap_text",), enabled=True, license_allowed=True
):
    return ParserAdapterCapability(
        capability_id=capability_id,
        step_kinds=step_kinds,
        enabled=enabled,
        license_allowed=license_allowed,
    )


def test_registry_resolves_adapter_by_capability_and_step_kind():
    adapter = FakeParserStepAdapter()
    registry = InMemoryParserAdapterRegistry((ParserAdapterRegistration(_capability(), adapter),))
    assert registry.resolve_adapter("cap-wrap", "wrap_text") is adapter


def test_registry_rejects_duplicate_capability_id():
    registration = ParserAdapterRegistration(_capability(), FakeParserStepAdapter())
    with pytest.raises(ValueError, match="duplicate capability id"):
        InMemoryParserAdapterRegistry((registration, registration))


def test_registry_returns_structured_failure_for_missing_adapter():
    registry = InMemoryParserAdapterRegistry(())
    with pytest.raises(ParserBoundaryError) as error:
        registry.resolve_adapter("missing", "wrap_text")
    assert error.value.failure.code == "UNSUPPORTED_FILE_KIND"


def test_registry_rejects_step_kind_outside_capability():
    registry = InMemoryParserAdapterRegistry((
        ParserAdapterRegistration(_capability(step_kinds=("native_text_extract",)), FakeParserStepAdapter()),
    ))
    with pytest.raises(ParserBoundaryError) as error:
        registry.resolve_adapter("cap-wrap", "wrap_text")
    assert error.value.failure.code == "UNSUPPORTED_FILE_KIND"


def test_registry_rejects_disabled_adapter():
    registry = InMemoryParserAdapterRegistry((
        ParserAdapterRegistration(_capability(enabled=False), FakeParserStepAdapter()),
    ))
    with pytest.raises(ParserBoundaryError) as error:
        registry.resolve_adapter("cap-wrap", "wrap_text")
    assert error.value.failure.code == "PARSER_DISABLED"


def test_registry_rejects_license_blocked_adapter_as_selection_contract_only():
    registry = InMemoryParserAdapterRegistry((
        ParserAdapterRegistration(_capability(license_allowed=False), FakeParserStepAdapter()),
    ))
    with pytest.raises(ParserBoundaryError) as error:
        registry.resolve_adapter("cap-wrap", "wrap_text")
    assert error.value.failure.code == "LICENSE_POLICY_VIOLATION"
