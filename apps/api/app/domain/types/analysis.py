from typing import Literal

from pydantic import BaseModel

from .common import TextRange
from .parser import BlockLocation


class AnalysisAtom(BaseModel):
    atom_id: str
    input_id: str
    block_id: str
    text: str
    original_range: TextRange
    location: BlockLocation | None
    atom_type: Literal["sentence", "paragraph", "row_group", "code_block", "table_row", "ocr_line"]
    ordinal: int


class AnalysisSegment(BaseModel):
    segment_id: str
    input_id: str
    atom_ids: list[str]
    text: str
    original_range: TextRange
    locations: list[BlockLocation]
    segment_type: Literal["semantic", "structure", "size_fallback", "single_atom"]
    ordinal: int
