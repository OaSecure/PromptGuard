import unicodedata

from app.atoms.models import TextRange
from app.normalization.models import NormalizedBlock, NormalizedDocument, NormalizerRequest, OffsetMapEntry

def _is_special(character: str) -> bool:
    return unicodedata.category(character)[:1] in {"P", "S"}


def _normalize_block(text: str, minimum_repeat: int) -> tuple[str, list[OffsetMapEntry]]:
    normalized: list[str] = []
    mapping: list[OffsetMapEntry] = []
    original_index = 0
    while original_index < len(text):
        character = text[original_index]
        original_end = original_index + 1
        if _is_special(character):
            while original_end < len(text) and text[original_end] == character:
                original_end += 1
        if original_end - original_index < minimum_repeat:
            original_end = original_index + 1

        normalized_index = len(normalized)
        normalized.append(character)
        mapping.append(
            OffsetMapEntry(
                normalized_range=TextRange(start=normalized_index, end=normalized_index + 1),
                original_range=TextRange(start=original_index, end=original_end),
            )
        )
        original_index = original_end
    return "".join(normalized), mapping


def normalize_document(request: NormalizerRequest) -> NormalizedDocument:
    blocks: list[NormalizedBlock] = []
    for block in request.document.blocks:
        normalized_text, offset_map = _normalize_block(block.text, request.policy.minimum_repeat)
        blocks.append(
            NormalizedBlock(
                block_id=block.block_id,
                input_id=block.input_id,
                original_text=block.text,
                normalized_text=normalized_text,
                offset_map=offset_map,
                location=block.location,
            )
        )
    return NormalizedDocument(
        input_id=request.document.input_id,
        blocks=blocks,
        normalizer_version=request.policy.normalizer_version,
    )


def restore_original_range(normalized_range: TextRange, offset_map: list[OffsetMapEntry]) -> TextRange | None:
    if normalized_range.start >= normalized_range.end:
        return None
    selected = [
        entry
        for entry in offset_map
        if entry.normalized_range.start >= normalized_range.start and entry.normalized_range.end <= normalized_range.end
    ]
    if not selected:
        return None
    if selected[0].normalized_range.start != normalized_range.start or selected[-1].normalized_range.end != normalized_range.end:
        return None
    for left, right in zip(selected, selected[1:]):
        if left.normalized_range.end != right.normalized_range.start:
            return None
        if left.original_range.end != right.original_range.start:
            return None
    return TextRange(start=selected[0].original_range.start, end=selected[-1].original_range.end)
