from app.atoms.models import ParsedBlock, ParsedDocument, TextRange
from app.normalization import NormalizerRequest, normalize_document, restore_original_range


def _document(text: str) -> ParsedDocument:
    return ParsedDocument(input_id="input-1", blocks=[ParsedBlock(block_id="block-1", input_id="input-1", text=text)])


def test_normalizer_preserves_original_text_and_collapses_repeated_special_characters():
    document = _document("Project---Hermes!!! aaa")

    result = normalize_document(NormalizerRequest(document=document))

    assert document.blocks[0].text == "Project---Hermes!!! aaa"
    assert result.blocks[0].original_text == document.blocks[0].text
    assert result.blocks[0].normalized_text == "Project-Hermes! aaa"


def test_normalizer_does_not_collapse_natural_language_repetition_or_alternating_symbols():
    result = normalize_document(NormalizerRequest(document=_document("coooool!?!?")))

    assert result.blocks[0].normalized_text == "coooool!?!?"


def test_mapping_uses_half_open_ranges_and_restores_collapsed_span():
    block = normalize_document(NormalizerRequest(document=_document("a---b"))).blocks[0]

    dash = block.offset_map[1]
    assert dash.normalized_range == TextRange(start=1, end=2)
    assert dash.original_range == TextRange(start=1, end=4)
    assert restore_original_range(TextRange(start=1, end=2), block.offset_map) == TextRange(start=1, end=4)
    assert restore_original_range(TextRange(start=0, end=3), block.offset_map) == TextRange(start=0, end=5)


def test_empty_block_has_empty_mapping():
    block = normalize_document(NormalizerRequest(document=_document(""))).blocks[0]

    assert block.normalized_text == ""
    assert block.offset_map == []


def test_invalid_or_unmapped_range_fails_closed():
    block = normalize_document(NormalizerRequest(document=_document("abc"))).blocks[0]

    assert restore_original_range(TextRange(start=1, end=1), block.offset_map) is None
    assert restore_original_range(TextRange(start=2, end=4), block.offset_map) is None
