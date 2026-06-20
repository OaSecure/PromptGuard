from typing import Protocol, runtime_checkable

from app.domain.types.parser import FileParserResult, OcrResult, ParserWorkerPayload
from app.ports.events import EventWriterPort
from app.ports.ml import EmbeddingModelPort, SegmentClassifierPort, VerifierModelPort
from app.ports.ocr import OcrEnginePort
from app.ports.parser import FileParserRunnerPort


def test_ports_are_protocols():
    for port in (FileParserRunnerPort, OcrEnginePort, EmbeddingModelPort, SegmentClassifierPort, VerifierModelPort, EventWriterPort):
        assert port._is_protocol


def test_fake_parser_can_implement_port_signature():
    @runtime_checkable
    class RuntimeParserPort(FileParserRunnerPort, Protocol): pass
    class FakeParser:
        def run(self, payload: ParserWorkerPayload) -> FileParserResult:
            return FileParserResult(input_id=payload.input_id, document=None, parser_status="unsupported", ocr_status="not_applicable")
    assert isinstance(FakeParser(), RuntimeParserPort)
