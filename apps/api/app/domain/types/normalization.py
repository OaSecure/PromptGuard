from pydantic import BaseModel, Field

from .common import OffsetMapping, PipelineFailure


class NormalizedBlock(BaseModel):
    block_id: str
    original_text: str
    normalized_text: str
    offset_map: list[OffsetMapping]
    warnings: list[str] = Field(default_factory=list)


class NormalizedDocument(BaseModel):
    input_id: str
    blocks: list[NormalizedBlock]
    normalizer_version: str
    failure: PipelineFailure | None = None
