import json

from app.runtime.parser_fixture_readiness import ParserFixtureReadinessProbe

from scripts import parser_fixture_readiness

FORBIDDEN = (
    "fixture native text",
    "fixture ocr text",
    "raw_prompt",
    "file_content",
    "extracted_text",
    "ocr_text",
    "original_filename",
    "embedding_vector",
    "logits",
    "exact_score",
)


def test_parser_fixture_readiness_runs_pdf_render_and_ocr_boundaries_without_public_text():
    report = ParserFixtureReadinessProbe().check()

    assert report.ready is True
    assert report.pdf_native_status == "success"
    assert report.pdf_native_block_count == 1
    assert report.pdf_render_status == "success"
    assert report.rendered_image_count == 1
    assert report.pdf_ocr_status == "parsed"
    assert report.pdf_ocr_block_count == 1
    encoded = report.model_dump_json()
    assert all(value not in encoded for value in FORBIDDEN)


def test_parser_fixture_readiness_cli_emits_metadata_only_json(capsys):
    exit_code = parser_fixture_readiness.main([])
    output = capsys.readouterr().out
    parsed = json.loads(output)

    assert exit_code == 0
    assert parsed["ready"] is True
    assert parsed["pdf_render_status"] == "success"
    assert all(value not in output for value in FORBIDDEN)
