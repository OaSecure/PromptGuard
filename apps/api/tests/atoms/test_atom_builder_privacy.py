import logging

from app.atoms import AtomBuildRequest, AtomizationPolicy, ParsedBlock, ParsedDocument, build_atoms
from app.atoms.privacy import serialize_atom_metadata, serialize_result_metadata


def _block(text: str, **overrides) -> ParsedBlock:
    values = {
        "block_id": "block-1",
        "input_id": "input-1",
        "text": text,
        "source_type": "text",
        "location": None,
        "metadata": {},
    }
    values.update(overrides)
    return ParsedBlock(**values)


def _document(blocks: list[ParsedBlock]) -> ParsedDocument:
    return ParsedDocument(input_id="input-1", blocks=blocks)


def _result_for(text: str, **block_overrides):
    block = _block(text, **block_overrides)
    return build_atoms(AtomBuildRequest(document=_document([block]), policy=AtomizationPolicy()))


def test_atom_text_not_persisted():
    raw_text = "SECRET-ATOM-TEXT"
    result = _result_for(raw_text)

    payload = serialize_result_metadata(result)

    assert raw_text not in str(payload)


def test_persistent_atom_metadata_uses_allowlist_only():
    result = _result_for("safe metadata shape")

    payload = serialize_atom_metadata(result.atoms[0], result.atomizer_version)

    assert set(payload) == {"atom_id", "block_id", "atom_type", "length_bucket", "location_kind", "atomizer_version"}


def test_persistent_atom_metadata_does_not_include_ordinal():
    result = _result_for("runtime ordinal exists")

    atom = result.atoms[0]
    payload = serialize_atom_metadata(atom, result.atomizer_version)

    assert atom.ordinal == 0
    assert "ordinal" not in payload


def test_failure_message_does_not_include_raw_text():
    raw_text = "SECRET-FAILURE-TEXT"
    result = build_atoms(
        AtomBuildRequest(
            document=_document([_block(raw_text)]),
            policy=AtomizationPolicy(max_atom_chars=0, min_atom_chars=10),
        )
    )

    assert raw_text not in result.failures[0].message
    assert raw_text not in str(result.failures[0].metadata)


def test_logging_does_not_include_raw_text(caplog):
    raw_text = "SECRET-LOG-TEXT"

    with caplog.at_level(logging.INFO):
        build_atoms(AtomBuildRequest(document=_document([_block(raw_text)]), policy=AtomizationPolicy()))

    assert raw_text not in caplog.text


def test_length_bucket_does_not_store_exact_raw_length():
    result = _result_for("x" * 40)

    payload = serialize_atom_metadata(result.atoms[0], result.atomizer_version)

    assert payload["length_bucket"] == "short"
    assert "40" not in str(payload)


def test_location_kind_does_not_store_raw_location():
    location = {"kind": "page", "page": 7, "bbox": [1, 2, 3, 4]}
    result = _result_for("located text", location=location)

    payload = serialize_atom_metadata(result.atoms[0], result.atomizer_version)

    assert payload["location_kind"] == "page"
    assert "bbox" not in str(payload)
    assert "page': 7" not in str(payload)
