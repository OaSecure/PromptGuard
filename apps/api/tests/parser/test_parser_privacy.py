import logging

from app.parser.fakes import RaisingFileParserRunner
from app.parser.models import ParserWorkerPayload
from app.runtime.parser_worker import ParserWorkerPool


def test_parser_failure_message_has_no_raw_content(caplog):
    sentinels = [
        "PRIVATE_RAW_TEXT",
        "confidential-report.docx",
        "C:\\private\\confidential-report.docx",
        "PRIVATE_OCR_TEXT",
        "PRIVATE_EXTRACTED_TEXT",
    ]
    runner = RaisingFileParserRunner(exception_message=" | ".join(sentinels))
    pool = ParserWorkerPool(runner=runner, max_workers=1, max_queue_size=1)
    payload = ParserWorkerPayload(
        input_id="input-1",
        request_id="request-1",
        input_kind="text_wrapper",
        extraction_requirement="wrap_text",
        text="PRIVATE_RAW_TEXT",
    )

    with caplog.at_level(logging.ERROR):
        result = pool.execute(payload, timeout_ms=100)

    assert result.failure is not None
    combined = result.failure.message + " " + caplog.text
    assert all(sentinel not in combined for sentinel in sentinels)
    pool.shutdown()
