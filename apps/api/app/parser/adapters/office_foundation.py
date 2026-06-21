import csv
import io
import re
import zipfile
from collections.abc import Iterable
from xml.etree import ElementTree

from app.atoms.models import ParsedBlock, ParsedDocument
from app.parser.models import (
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort


OFFICE_STEPS = {
    "office_document": "office_parse",
    "spreadsheet": "spreadsheet_parse",
    "slide": "slide_parse",
}
_SHEET_PART = re.compile(r"^xl/worksheets/sheet(\d+)\.xml$")
_SLIDE_PART = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


class _EncryptedContainer(Exception):
    pass


class _PartialExtraction(Exception):
    def __init__(self, blocks: list[ParsedBlock]) -> None:
        self.blocks = blocks


class OfficeParserFoundationAdapter:
    def __init__(self, content_source: ResolvedFileContentSourcePort) -> None:
        self._content_source = content_source

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        expected_step = OFFICE_STEPS.get(payload.file_kind or "")
        if expected_step is None or step.step_kind != expected_step:
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")
        if resolved_file is None or resolved_file.file_kind != payload.file_kind:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        try:
            content = self._content_source.read(resolved_file)
        except Exception:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")

        if not content:
            return self._result(step.step_id, payload, "success", "parsed", [])

        try:
            blocks = self._extract(content, payload)
        except _EncryptedContainer:
            return self._failure(step.step_id, "PARSER_ENCRYPTED")
        except UnicodeDecodeError:
            return self._failure(step.step_id, "TEXT_DECODE_FAILED")
        except _PartialExtraction as partial:
            return self._result(
                step.step_id, payload, "partial", "partial", partial.blocks, "PARSER_PARTIAL"
            )
        except (csv.Error, ElementTree.ParseError, KeyError, ValueError, zipfile.BadZipFile):
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")
        except Exception:
            return self._failure(step.step_id, "PARSER_WORKER_FAILED")
        return self._result(step.step_id, payload, "success", "parsed", blocks)

    def _extract(self, content: bytes, payload: ParserWorkerPayload) -> list[ParsedBlock]:
        if payload.file_kind == "spreadsheet" and not content.startswith(b"PK"):
            return self._extract_csv(content, payload.input_id)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if any(info.flag_bits & 1 for info in archive.infolist()):
                raise _EncryptedContainer
            if payload.file_kind == "office_document":
                return self._extract_docx(archive, payload.input_id)
            if payload.file_kind == "spreadsheet":
                return self._extract_xlsx(archive, payload.input_id)
            return self._extract_pptx(archive, payload.input_id)

    @staticmethod
    def _extract_docx(archive: zipfile.ZipFile, input_id: str) -> list[ParsedBlock]:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        blocks = []
        for paragraph in _elements(root, "p"):
            text = "".join(node.text or "" for node in _elements(paragraph, "t"))
            if text:
                index = len(blocks)
                blocks.append(ParsedBlock(
                    block_id=f"office-block-{index}", input_id=input_id, text=text,
                    source_type="office_paragraph",
                    location={"kind": "office", "block_index": index},
                ))
        return blocks

    @staticmethod
    def _extract_xlsx(archive: zipfile.ZipFile, input_id: str) -> list[ParsedBlock]:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(node.text or "" for node in _elements(item, "t"))
                              for item in _elements(shared_root, "si")]
        sheet_parts = _numbered_parts(archive.namelist(), _SHEET_PART)
        if not sheet_parts:
            raise KeyError("required worksheet missing")
        blocks: list[ParsedBlock] = []
        failed = False
        for sheet_index, part in enumerate(sheet_parts):
            try:
                root = ElementTree.fromstring(archive.read(part))
                for fallback_row, row in enumerate(_elements(root, "row"), start=1):
                    values = [_xlsx_cell_text(cell, shared_strings) for cell in _children(row, "c")]
                    text = "\t".join(values)
                    if text:
                        row_index = _positive_int(row.get("r"), fallback_row)
                        blocks.append(ParsedBlock(
                            block_id=f"spreadsheet-block-{len(blocks)}", input_id=input_id,
                            text=text, source_type="spreadsheet_row",
                            location={"kind": "spreadsheet", "sheet_index": sheet_index,
                                      "row_index": row_index},
                        ))
            except (ElementTree.ParseError, KeyError, ValueError):
                failed = True
        if failed:
            if blocks:
                raise _PartialExtraction(blocks)
            raise ElementTree.ParseError("worksheet parse failed")
        return blocks

    @staticmethod
    def _extract_pptx(archive: zipfile.ZipFile, input_id: str) -> list[ParsedBlock]:
        slide_parts = _numbered_parts(archive.namelist(), _SLIDE_PART)
        if not slide_parts:
            raise KeyError("required slide missing")
        blocks: list[ParsedBlock] = []
        failed = False
        for slide_number, part in enumerate(slide_parts, start=1):
            try:
                root = ElementTree.fromstring(archive.read(part))
                text = "\n".join(node.text or "" for node in _elements(root, "t") if node.text)
                if text:
                    blocks.append(ParsedBlock(
                        block_id=f"slide-block-{len(blocks)}", input_id=input_id, text=text,
                        source_type="slide_text",
                        location={"kind": "slide", "slide": slide_number},
                    ))
            except (ElementTree.ParseError, KeyError):
                failed = True
        if failed:
            if blocks:
                raise _PartialExtraction(blocks)
            raise ElementTree.ParseError("slide parse failed")
        return blocks

    @staticmethod
    def _extract_csv(content: bytes, input_id: str) -> list[ParsedBlock]:
        text = content.decode("utf-8-sig")
        blocks = []
        for row_index, row in enumerate(csv.reader(io.StringIO(text)), start=1):
            row_text = "\t".join(row)
            if row_text:
                blocks.append(ParsedBlock(
                    block_id=f"spreadsheet-block-{len(blocks)}", input_id=input_id,
                    text=row_text, source_type="spreadsheet_row",
                    location={"kind": "spreadsheet", "row_index": row_index},
                ))
        return blocks

    @staticmethod
    def _result(
        step_id: str,
        payload: ParserWorkerPayload,
        status: str,
        parser_status: str,
        blocks: list[ParsedBlock],
        failure_code: str | None = None,
    ) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status=status,
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=blocks,
                file_ref=payload.file_ref,
                file_type=payload.file_kind,
                parser_id="office-native-contract",
                parser_status=parser_status,
                ocr_status="not_applicable",
            ),
            failure=sanitized_failure(failure_code) if failure_code else None,
        )

    @staticmethod
    def _failure(step_id: str, code: str) -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status="failed",
            trigger="step_failed",
            failure=sanitized_failure(code),
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _elements(root: ElementTree.Element, local_name: str) -> Iterable[ElementTree.Element]:
    return (element for element in root.iter() if _local_name(element.tag) == local_name)


def _children(root: ElementTree.Element, local_name: str) -> Iterable[ElementTree.Element]:
    return (element for element in root if _local_name(element.tag) == local_name)


def _numbered_parts(names: Iterable[str], pattern: re.Pattern[str]) -> list[str]:
    matches = [(int(match.group(1)), name) for name in names if (match := pattern.match(name))]
    return [name for _, name in sorted(matches)]


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in _elements(cell, "t"))
    value_node = next(_elements(cell, "v"), None)
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    return value


def _positive_int(value: str | None, fallback: int) -> int:
    parsed = int(value) if value else fallback
    return parsed if parsed > 0 else fallback
