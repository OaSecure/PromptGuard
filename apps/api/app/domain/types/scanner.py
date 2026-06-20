from typing import Literal

from pydantic import BaseModel, Field

from .common import JsonValue, PipelineFailure, ScannerStatus, TextRange


class LexicalRuleSnapshot(BaseModel):
    snapshot_id: str
    scanner_version: str
    ruleset_version: str
    regex_ruleset_version: str
    keyword_ruleset_version: str
    protected_target_registry_version: str | None = None
    custom_regex_ruleset_version: str | None = None
    config_hash: str
    created_at: str


class ProtectedTargetConfig(BaseModel):
    target_id: str
    target_type: Literal["project", "customer", "system", "repo", "domain", "custom"]
    match_mode: Literal["exact", "substring", "regex", "domain", "repo"]
    encrypted_pattern_ref: str
    severity_hint: Literal["low", "medium", "high", "critical"]
    registry_version: str
    enabled: bool


class LexicalSignal(BaseModel):
    signal_id: str
    input_id: str
    block_id: str
    signal_type: Literal["pii_span", "secret_span", "secret_fingerprint", "token_candidate", "protected_target_hit", "custom_regex_hit", "sensitive_value_pattern_hit", "context_trigger_hit"]
    pattern_id: str
    match_basis: Literal["deterministic_regex", "heuristic_regex", "keyword", "protected_target", "fingerprint", "context_trigger"]
    normalized_range: TextRange
    original_range: TextRange
    severity_hint: Literal["info", "low", "medium", "high", "critical"]
    deterministic: bool
    value_fingerprint: str | None = None
    protected_target_hit: bool = False
    protected_target_id: str | None = None
    protected_target_type: str | None = None
    protected_target_registry_version: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class LexicalScanResult(BaseModel):
    input_id: str
    signals: list[LexicalSignal]
    scanner_status: ScannerStatus
    scanner_version: str
    rule_snapshot: LexicalRuleSnapshot
    failure: PipelineFailure | None = None
