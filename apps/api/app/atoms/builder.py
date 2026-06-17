import hashlib
import re
from collections.abc import Iterable

from app.atoms.models import (
    AnalysisAtom,
    AnalysisAtomBuildResult,
    AtomBuildRequest,
    AtomizationPolicy,
    AtomType,
    ParsedBlock,
    ParsedDocument,
    PipelineFailure,
    TextRange,
)
from app.atoms.privacy import location_kind

FENCE_RE = re.compile(r"(```|~~~).*?(?:\1|$)", re.DOTALL)
SENTENCE_BOUNDARIES = {".", "!", "?", "。", "！", "？"}
TABLE_SOURCES = {"csv", "table", "spreadsheet", "xls", "xlsx", "tsv"}


def build_atoms(request: AtomBuildRequest) -> AnalysisAtomBuildResult:
    policy = request.policy
    policy_failure = _validate_policy(policy, len(request.document.blocks))
    if policy_failure is not None:
        return AnalysisAtomBuildResult(
            input_id=request.document.input_id,
            atoms=[],
            atomizer_version=policy.atomizer_version,
            failures=[policy_failure],
        )

    atoms: list[AnalysisAtom] = []
    for block in _iter_blocks_in_source_order(request.document):
        atoms.extend(_atomize_block(block, policy, len(atoms)))

    return AnalysisAtomBuildResult(
        input_id=request.document.input_id,
        atoms=atoms,
        atomizer_version=policy.atomizer_version,
        failures=[],
    )


def _validate_policy(policy: AtomizationPolicy, block_count: int) -> PipelineFailure | None:
    if policy.max_atom_chars <= 0 or policy.min_atom_chars < 0 or policy.atom_id_prefix_length <= 0:
        return _policy_failure(policy, block_count)
    return None


def _policy_failure(policy: AtomizationPolicy, block_count: int) -> PipelineFailure:
    return PipelineFailure(
        code="invalid_atomization_policy",
        message="invalid_atomization_policy",
        metadata={
            "failure_code": "invalid_atomization_policy",
            "atomizer_version": policy.atomizer_version,
            "block_count": block_count,
        },
    )


def _iter_blocks_in_source_order(document: ParsedDocument) -> list[ParsedBlock]:
    return list(document.blocks)


def _atomize_block(block: ParsedBlock, policy: AtomizationPolicy, start_ordinal: int) -> list[AnalysisAtom]:
    content_range = _trim_outer_whitespace_range(block.text)
    if content_range is None:
        return []

    structural_ranges = _structural_ranges(block, content_range, policy)
    atoms: list[AnalysisAtom] = []
    for structural_range, atom_type in structural_ranges:
        for text_range in _split_by_safe_boundary(block.text, structural_range, policy.max_atom_chars):
            if text_range.start < text_range.end:
                atoms.append(_build_atom(block, text_range, atom_type, start_ordinal + len(atoms), policy))
    return atoms


def _structural_ranges(
    block: ParsedBlock,
    content_range: TextRange,
    policy: AtomizationPolicy,
) -> list[tuple[TextRange, AtomType]]:
    if _is_ocr_block(block):
        return [(content_range, "ocr_line")]

    content = block.text[content_range.start : content_range.end]
    if policy.preserve_code_fences and _contains_fence(content):
        return _split_code_fences(block.text, content_range)

    if policy.preserve_table_rows and _is_table_block(block, content):
        return [(row_range, "table_row") for row_range in _split_table_rows(block.text, content_range)]

    paragraph_ranges = _split_paragraphs(block.text, content_range)
    return [(paragraph_range, "paragraph") for paragraph_range in paragraph_ranges]


def _trim_outer_whitespace_range(text: str) -> TextRange | None:
    start = 0
    end = len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start == end:
        return None
    return TextRange(start=start, end=end)


def _contains_fence(text: str) -> bool:
    return "```" in text or "~~~" in text


def _split_code_fences(text: str, content_range: TextRange) -> list[tuple[TextRange, AtomType]]:
    content = text[content_range.start : content_range.end]
    ranges: list[tuple[TextRange, AtomType]] = []
    cursor = content_range.start
    for match in FENCE_RE.finditer(content):
        fence_start = content_range.start + match.start()
        fence_end = content_range.start + match.end()
        prose_before = _range_if_nonblank(text, TextRange(start=cursor, end=fence_start))
        if prose_before is not None:
            ranges.append((prose_before, "paragraph"))
        ranges.append((TextRange(start=fence_start, end=fence_end), "code_block"))
        cursor = fence_end
    prose_after = _range_if_nonblank(text, TextRange(start=cursor, end=content_range.end))
    if prose_after is not None:
        ranges.append((prose_after, "paragraph"))
    return ranges


def _split_table_rows(text: str, content_range: TextRange) -> list[TextRange]:
    return _nonblank_line_groups(text, content_range)


def _split_paragraphs(text: str, content_range: TextRange) -> list[TextRange]:
    segment = text[content_range.start : content_range.end]
    ranges: list[TextRange] = []
    cursor = content_range.start
    for match in re.finditer(r"\n[ \t\r\f\v]*\n+", segment):
        boundary_start = content_range.start + match.start()
        range_before = _trim_range(text, TextRange(start=cursor, end=boundary_start))
        if range_before is not None:
            ranges.append(range_before)
        cursor = content_range.start + match.end()
    tail = _trim_range(text, TextRange(start=cursor, end=content_range.end))
    if tail is not None:
        ranges.append(tail)
    if ranges:
        return ranges
    return [content_range]


def _nonblank_line_groups(text: str, text_range: TextRange) -> list[TextRange]:
    ranges: list[TextRange] = []
    cursor = text_range.start
    while cursor < text_range.end:
        line_end = text.find("\n", cursor, text_range.end)
        if line_end == -1:
            line_end = text_range.end
            next_cursor = text_range.end
        else:
            next_cursor = line_end + 1
        row_range = _trim_range(text, TextRange(start=cursor, end=line_end))
        if row_range is not None:
            ranges.append(row_range)
        cursor = next_cursor
    return ranges


def _trim_range(text: str, text_range: TextRange) -> TextRange | None:
    start = text_range.start
    end = text_range.end
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start == end:
        return None
    return TextRange(start=start, end=end)


def _range_if_nonblank(text: str, text_range: TextRange) -> TextRange | None:
    if text_range.start >= text_range.end:
        return None
    if not text[text_range.start : text_range.end].strip():
        return None
    return text_range


def _split_by_safe_boundary(text: str, text_range: TextRange, max_chars: int) -> list[TextRange]:
    ranges: list[TextRange] = []
    start = text_range.start
    while text_range.end - start > max_chars:
        split_at = _find_split_boundary(text, start, start + max_chars)
        if split_at <= start:
            split_at = start + max_chars
        ranges.append(TextRange(start=start, end=split_at))
        start = split_at
    if start < text_range.end:
        ranges.append(TextRange(start=start, end=text_range.end))
    return ranges


def _find_split_boundary(text: str, start: int, limit: int) -> int:
    newline_at = text.rfind("\n", start + 1, limit)
    if newline_at > start:
        return newline_at + 1

    for index in range(limit - 1, start, -1):
        if text[index] in SENTENCE_BOUNDARIES:
            return index + 1

    for index in range(limit - 1, start, -1):
        if text[index].isspace():
            return index + 1

    return limit


def _is_ocr_block(block: ParsedBlock) -> bool:
    return (
        block.source_type == "ocr"
        or location_kind(block.location, block.source_type, block.metadata) == "ocr"
        or block.metadata.get("source") == "ocr"
    )


def _is_table_block(block: ParsedBlock, text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    if _looks_malformed_table(lines):
        return False
    if any("\t" in line or "|" in line for line in lines):
        return _consistent_rows(lines, "\t") or _consistent_rows(lines, "|")
    if any("," in line for line in lines):
        source = block.source_type.lower()
        metadata_source = str(block.metadata.get("source", "")).lower()
        source_is_table = source in TABLE_SOURCES or metadata_source in TABLE_SOURCES
        return source_is_table and _consistent_rows(lines, ",")
    return False


def _looks_malformed_table(lines: Iterable[str]) -> bool:
    for line in lines:
        if "|||" in line or ",,," in line:
            return True
        stripped_columns = [part.strip() for part in re.split(r"[|,\t]", line)]
        if len(stripped_columns) > 1 and any(column == "" for column in stripped_columns):
            return True
    return False


def _consistent_rows(lines: list[str], delimiter: str) -> bool:
    rows = [[column.strip() for column in line.split(delimiter)] for line in lines if delimiter in line]
    if not rows:
        return False
    if len(lines) > 1 and len(rows) != len(lines):
        return False
    counts = {len(row) for row in rows}
    if len(counts) != 1 or next(iter(counts)) < 2:
        return False
    return all(all(column for column in row) for row in rows)


def _build_atom(
    block: ParsedBlock,
    text_range: TextRange,
    atom_type: AtomType,
    ordinal: int,
    policy: AtomizationPolicy,
) -> AnalysisAtom:
    text = block.text[text_range.start : text_range.end]
    return AnalysisAtom(
        atom_id=_make_atom_id(block.input_id, block.block_id, ordinal, policy.atom_id_prefix_length),
        input_id=block.input_id,
        block_id=block.block_id,
        text=text,
        original_range=text_range,
        location=block.location,
        atom_type=atom_type,
        ordinal=ordinal,
    )


def _make_atom_id(input_id: str, block_id: str, ordinal: int, prefix_length: int) -> str:
    digest = hashlib.sha256(f"{input_id}:{block_id}:{ordinal}".encode("utf-8")).hexdigest()
    return f"atom_{digest[:prefix_length]}"
