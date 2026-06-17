from app.atoms import AtomBuildRequest, AtomizationPolicy, ParsedBlock, ParsedDocument, build_atoms


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


def _document(blocks: list[ParsedBlock]) -> ParsedDocument:
    return ParsedDocument(input_id="input-1", blocks=blocks)


def _build(text: str, policy: AtomizationPolicy):
    return build_atoms(AtomBuildRequest(document=_document([_block(text)]), policy=policy))


def _joined(result) -> str:
    return "".join(atom.text for atom in result.atoms)


def test_max_atom_chars_boundary_values():
    policy = AtomizationPolicy(max_atom_chars=8, min_atom_chars=2)

    below = _build("x" * 7, policy)
    exact = _build("x" * 8, policy)
    above = _build("x" * 9, policy)

    assert len(below.atoms) == 1
    assert len(exact.atoms) == 1
    assert len(above.atoms) == 2
    assert all(len(atom.text) <= policy.max_atom_chars for atom in above.atoms)


def test_min_atom_chars_boundary_values():
    policy = AtomizationPolicy(max_atom_chars=64, min_atom_chars=4)

    below = _build("abc", policy)
    exact = _build("abcd", policy)
    above = _build("abcde", policy)

    assert _joined(below) == "abc"
    assert _joined(exact) == "abcd"
    assert _joined(above) == "abcde"


def test_two_times_max_atom_chars_plus_one_splits_without_loss():
    policy = AtomizationPolicy(max_atom_chars=8, min_atom_chars=2)
    text = "x" * (2 * policy.max_atom_chars + 1)

    result = _build(text, policy)

    assert len(result.atoms) == 3
    assert _joined(result) == text
    assert all(len(atom.text) <= policy.max_atom_chars for atom in result.atoms)


def test_atom_builder_handles_single_character_block():
    result = _build("한", AtomizationPolicy(max_atom_chars=8, min_atom_chars=4))

    assert len(result.atoms) == 1
    assert result.atoms[0].text == "한"


def test_atom_builder_handles_multiple_paragraphs():
    text = "first paragraph\n\nsecond paragraph"
    result = _build(text, AtomizationPolicy(max_atom_chars=64, min_atom_chars=4))

    assert [atom.text for atom in result.atoms] == ["first paragraph", "second paragraph"]


def test_atom_builder_handles_many_newlines():
    text = "\n\nalpha\n\n\nbeta\n\n"
    result = _build(text, AtomizationPolicy(max_atom_chars=64, min_atom_chars=4))

    assert [atom.text for atom in result.atoms] == ["alpha", "beta"]
    assert all(atom.original_range.start < atom.original_range.end for atom in result.atoms)


def test_atom_builder_handles_very_long_single_paragraph():
    policy = AtomizationPolicy(max_atom_chars=32, min_atom_chars=4)
    text = "word " * 80

    result = _build(text, policy)

    assert _joined(result) == text.strip()
    assert all(len(atom.text) <= policy.max_atom_chars for atom in result.atoms)


def test_invalid_policy_failure_does_not_include_raw_text():
    raw_text = "SECRET-RAW-POLICY-TEXT"
    policy = AtomizationPolicy(max_atom_chars=0, min_atom_chars=10)

    result = _build(raw_text, policy)

    assert result.atoms == []
    assert result.failures
    assert result.failures[0].code == "invalid_atomization_policy"
    assert raw_text not in result.failures[0].message
    assert raw_text not in str(result.failures[0].metadata)


def test_atom_builder_handles_normal_paragraph_text():
    result = _build("일반 문단입니다.", AtomizationPolicy())

    assert result.atoms[0].atom_type == "paragraph"


def test_atom_builder_handles_sentence_heavy_text_as_paragraph_atoms():
    result = _build("First sentence. Second sentence! Third sentence?", AtomizationPolicy(max_atom_chars=20))

    assert {atom.atom_type for atom in result.atoms} == {"paragraph"}


def test_atom_builder_handles_code_block():
    result = _build("```python\nprint('hello')\n```", AtomizationPolicy())

    assert result.atoms[0].atom_type == "code_block"


def test_mixed_prose_and_fenced_code_preserves_ranges():
    text = "before\n```python\nprint('hello')\n```\nafter"
    block = _block(text)
    result = build_atoms(AtomBuildRequest(document=_document([block]), policy=AtomizationPolicy(max_atom_chars=128)))

    assert "".join(atom.text for atom in result.atoms) == text.strip()
    assert any(atom.atom_type == "code_block" for atom in result.atoms)
    for atom in result.atoms:
        assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_long_code_block_splits_as_code_block_without_loss():
    policy = AtomizationPolicy(max_atom_chars=20, min_atom_chars=4)
    text = "```\n" + ("x" * 60) + "\n```"

    result = _build(text, policy)

    assert {atom.atom_type for atom in result.atoms} == {"code_block"}
    assert _joined(result) == text
    assert all(len(atom.text) <= policy.max_atom_chars for atom in result.atoms)


def test_atom_builder_handles_table_rows():
    result = _build("name | email | role", AtomizationPolicy())

    assert result.atoms[0].atom_type == "table_row"


def test_comma_sentence_is_not_misclassified_as_table_row():
    result = _build("안녕하세요, 오늘 회의 내용 정리해주세요", AtomizationPolicy())

    assert result.atoms[0].atom_type == "paragraph"


def test_multiline_table_block_creates_row_atoms_with_parent_ranges():
    text = "name,email,role\n유지수,test@example.com,admin"
    block = _block(text, source_type="csv", metadata={"source": "csv"})
    result = build_atoms(AtomBuildRequest(document=_document([block]), policy=AtomizationPolicy()))

    assert [atom.atom_type for atom in result.atoms] == ["table_row", "table_row"]
    assert [atom.text for atom in result.atoms] == ["name,email,role", "유지수,test@example.com,admin"]
    for atom in result.atoms:
        assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_multiline_table_recomposition_uses_structural_delimiter_rule():
    text = "name,email,role\n유지수,test@example.com,admin"
    result = build_atoms(
        AtomBuildRequest(
            document=_document([_block(text, source_type="csv", metadata={"source": "csv"})]),
            policy=AtomizationPolicy(),
        )
    )

    assert "\n".join(atom.text for atom in result.atoms) == text


def test_atom_builder_handles_ocr_lines():
    result = build_atoms(
        AtomBuildRequest(document=_document([_block("ocr text", source_type="ocr")]), policy=AtomizationPolicy())
    )

    assert result.atoms[0].atom_type == "ocr_line"


def test_atom_builder_falls_back_malformed_table_to_paragraph():
    result = _build("name ||| \n| | |\nemail,,,", AtomizationPolicy())

    assert {atom.atom_type for atom in result.atoms} == {"paragraph"}


def test_atom_builder_handles_unicode_korean_and_emoji_ranges():
    text = "안녕하세요 😊. 보안 검토입니다."
    block = _block(text)
    result = build_atoms(AtomBuildRequest(document=_document([block]), policy=AtomizationPolicy(max_atom_chars=10)))

    assert _joined(result) == text
    for atom in result.atoms:
        assert atom.text == block.text[atom.original_range.start : atom.original_range.end]


def test_atom_builder_handles_huge_text():
    policy = AtomizationPolicy(max_atom_chars=128, min_atom_chars=8)
    text = "secure " * 500

    result = _build(text, policy)

    assert _joined(result) == text.strip()
    assert all(len(atom.text) <= policy.max_atom_chars for atom in result.atoms)


def test_atom_builder_handles_unicode_mixed_text():
    text = "한국어 English 123 😊 token"
    block = _block(text)

    result = build_atoms(AtomBuildRequest(document=_document([block]), policy=AtomizationPolicy(max_atom_chars=12)))

    assert _joined(result) == text
    for atom in result.atoms:
        assert atom.text == block.text[atom.original_range.start : atom.original_range.end]
