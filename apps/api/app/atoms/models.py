from typing import Any, Literal

from pydantic_core import PydanticCustomError
from pydantic import BaseModel, Field, field_validator, model_validator

AtomType = Literal["paragraph", "code_block", "table_row", "ocr_line"]


class TextRange(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def range_must_be_half_open(self) -> "TextRange":
        if self.start < 0:
            raise ValueError("range start must be non-negative")
        if self.end < self.start:
            raise ValueError("range end must be greater than or equal to start")
        return self


class ParsedBlock(BaseModel):
    block_id: str
    input_id: str
    text: str
    source_type: str = "text"
    location: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("block_id", "input_id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_required_id", "required id must not be blank")
        return value


class ParsedDocument(BaseModel):
    input_id: str
    blocks: list[ParsedBlock] = Field(default_factory=list)
    file_ref: str | None = None
    file_type: str | None = None
    parser_id: str = "unknown"
    parser_status: str = "ok"
    ocr_status: str = "not_applicable"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_id")
    @classmethod
    def input_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise PydanticCustomError("missing_input_id", "input_id must not be blank")
        return value


class AtomizationPolicy(BaseModel):
    min_atom_chars: int = 16
    max_atom_chars: int = 512
    atomizer_version: str = "analysis-atom-builder-v1"
    atom_id_prefix_length: int = 16
    preserve_table_rows: bool = True
    preserve_code_fences: bool = True


class AtomBuildRequest(BaseModel):
    document: ParsedDocument
    policy: AtomizationPolicy | None = None

    @model_validator(mode="after")
    def default_policy_when_missing(self) -> "AtomBuildRequest":
        if self.policy is None:
            self.policy = AtomizationPolicy()
        return self


class PipelineFailure(BaseModel):
    code: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisAtom(BaseModel):
    atom_id: str
    input_id: str
    block_id: str
    text: str
    original_range: TextRange
    location: Any | None
    atom_type: AtomType
    ordinal: int


class AnalysisAtomBuildResult(BaseModel):
    input_id: str
    atoms: list[AnalysisAtom]
    atomizer_version: str
    failures: list[PipelineFailure] = Field(default_factory=list)
