import copy
import json

import pytest
from pydantic import ValidationError

from app.atoms import (
    AtomBuildRequest,
    AtomizationPolicy,
    ParsedBlock,
    ParsedDocument,
    build_atoms,
)


def _block(text: str, block_id: str = "block-1", **overrides) -> ParsedBlock:
    values = {
        "block_id": block_id,
        "input_id": "input-1",
        "text": text,
        "source_type": "text",
        "location": None,
        "metadata": {},
    }
    values.update(overrides)
    return ParsedBlock(**values)


def _document(blocks: list[ParsedBlock], input_id: str = "input-1") -> ParsedDocument:
    return ParsedDocument(
        input_id=input_id,
        blocks=blocks,
        file_ref=None,
        file_type=None,
        parser_id="test-parser",
        parser_status="ok",
        ocr_status="not_applicable",
        metadata={},
    )


def _build(document: ParsedDocument, policy: AtomizationPolicy | None = None):
    return build_atoms(AtomBuildRequest(document=document, policy=policy))


def test_atom_builder_empty_document_returns_empty_atoms():
    document = _document([])

    result = _build(document)

    assert result.atoms == []
    assert result.failures == []


@pytest.mark.parametrize("blank_text", ["", " ", "   ", "\n", "\t", " \n \t "])
def test_atom_builder_skips_empty_and_blank_blocks(blank_text: str):
    document = _document([_block(blank_text)])

    result = _build(document)

    assert result.atoms == []
    assert result.failures == []


def test_atom_builder_preserves_block_order():
    document = _document(
        [
            _block("first block", block_id="block-1"),
            _block("second block", block_id="block-2"),
            _block("third block", block_id="block-3"),
        ]
    )

    result = _build(document)

    assert [atom.block_id for atom in result.atoms] == ["block-1", "block-2", "block-3"]
    assert [atom.text for atom in result.atoms] == ["first block", "second block", "third block"]


def test_atom_builder_preserves_original_range():
    block = _block("normal paragraph block")
    document = _document([block])

    result = _build(document)

    atom = result.atoms[0]
    assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_atom_text_matches_original_slice_after_split():
    policy = AtomizationPolicy(max_atom_chars=12, min_atom_chars=4)
    block = _block("alpha beta gamma delta epsilon")
    document = _document([block])

    result = _build(document, policy)

    assert len(result.atoms) > 1
    for atom in result.atoms:
        assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_atom_builder_does_not_drop_or_duplicate_text_when_splitting():
    policy = AtomizationPolicy(max_atom_chars=12, min_atom_chars=4)
    block = _block("alpha beta gamma delta epsilon")
    document = _document([block])

    result = _build(document, policy)

    assert "".join(atom.text for atom in result.atoms) == block.text.strip()


def test_atom_original_range_is_half_open_and_inside_parent_block():
    policy = AtomizationPolicy(max_atom_chars=8, min_atom_chars=2)
    block = _block("one two three four")
    document = _document([block])

    result = _build(document, policy)

    for atom in result.atoms:
        assert 0 <= atom.original_range.start < atom.original_range.end <= len(block.text)


def test_atom_id_is_deterministic():
    document = _document([_block("same input")])

    first = _build(document)
    second = _build(document)

    assert [atom.atom_id for atom in first.atoms] == [atom.atom_id for atom in second.atoms]


def test_atom_ordinal_is_stable_and_contiguous():
    policy = AtomizationPolicy(max_atom_chars=8, min_atom_chars=2)
    document = _document([_block("one two three", "block-1"), _block("four five six", "block-2")])

    result = _build(document, policy)

    assert [atom.ordinal for atom in result.atoms] == list(range(len(result.atoms)))


def test_atom_output_has_no_action_or_policy_fields():
    document = _document([_block("plain text")])

    result = _build(document)

    forbidden = {
        "action",
        "recommended_action",
        "reason_code",
        "user_notice",
        "label_scores",
        "signals",
        "embedding",
    }
    atom_payload = result.atoms[0].model_dump()
    assert forbidden.isdisjoint(atom_payload)


def test_missing_location_is_allowed():
    document = _document([_block("plain text", location=None)])

    result = _build(document)

    assert result.atoms[0].location is None


def test_parent_block_location_is_preserved():
    location = {"kind": "page", "page": 3, "bbox": [1, 2, 3, 4]}
    document = _document([_block("plain text", location=location)])

    result = _build(document)

    assert result.atoms[0].location == location


def test_atom_builder_has_no_side_effect_on_parsed_document():
    document = _document([_block("  side effect check  ")])
    before = copy.deepcopy(document.model_dump())

    _build(document)

    assert document.model_dump() == before


def test_atom_builder_requires_input_id_without_raw_text_failure():
    raw_text = "SECRET-RAW-TEXT"

    with pytest.raises(ValidationError) as exc_info:
        _document([_block(raw_text)], input_id="")

    assert raw_text not in str(exc_info.value)


def test_atom_builder_requires_block_id_without_raw_text_failure():
    raw_text = "SECRET-RAW-TEXT"

    with pytest.raises(ValidationError) as exc_info:
        _block(raw_text, block_id="")

    assert raw_text not in str(exc_info.value)


def test_atom_builder_trims_outer_whitespace_but_preserves_original_range():
    block = _block("  안녕하세요  ")
    document = _document([block])

    result = _build(document)

    atom = result.atoms[0]
    assert atom.text == "안녕하세요"
    assert atom.original_range.start == 2
    assert atom.original_range.end == 7
    assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_atom_builder_does_not_strip_each_split_atom():
    policy = AtomizationPolicy(max_atom_chars=7, min_atom_chars=2)
    block = _block("aa  bb\ncc\tdd")
    document = _document([block])

    result = _build(document, policy)

    assert "".join(atom.text for atom in result.atoms) == block.text.strip()
    assert any(atom.text.endswith("\n") or atom.text.endswith("\t") or "  " in atom.text for atom in result.atoms)


def test_validation_error_is_not_copied_with_raw_input():
    raw_text = "SECRET-VALIDATION-VALUE"

    with pytest.raises(ValidationError) as exc_info:
        ParsedBlock(block_id="", input_id="input-1", text=raw_text)

    encoded = json.dumps(exc_info.value.errors(include_input=False), ensure_ascii=False)
    assert raw_text not in encoded
