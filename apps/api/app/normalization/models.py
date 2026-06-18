from pydantic import BaseModel, Field

from app.atoms.models import ParsedDocument, TextRange


class NormalizationPolicy(BaseModel):
    minimum_repeat: int = Field(default=2, ge=2)
    normalizer_version: str = "repeated-special-char-v1"


class NormalizerRequest(BaseModel):
    document: ParsedDocument
    policy: NormalizationPolicy = Field(default_factory=NormalizationPolicy)


class OffsetMapEntry(BaseModel):
    normalized_range: TextRange
    original_range: TextRange


class NormalizedBlock(BaseModel):
    block_id: str
    input_id: str
    original_text: str
    normalized_text: str
    offset_map: list[OffsetMapEntry]
    location: object | None = None


class NormalizationFailure(BaseModel):
    code: str
    block_id: str | None = None


class NormalizedDocument(BaseModel):
    input_id: str
    blocks: list[NormalizedBlock]
    normalizer_version: str
    warnings: list[str] = Field(default_factory=list)
    failures: list[NormalizationFailure] = Field(default_factory=list)
