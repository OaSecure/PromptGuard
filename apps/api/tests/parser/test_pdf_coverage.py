import pytest
from pydantic import ValidationError

from app.parser.pdf_coverage import (
    PdfCoverageEvaluator,
    PdfPageCoverageInput,
    count_meaningful_characters,
)


def _page(
    page_index: int,
    count: int,
    image_evidence: str = "absent",
    native_extraction_status: str = "success",
) -> PdfPageCoverageInput:
    return PdfPageCoverageInput(
        page_index=page_index,
        native_extraction_status=native_extraction_status,
        meaningful_character_count=count,
        image_evidence=image_evidence,
    )


def test_native_extraction_failure_page_becomes_ocr_candidate():
    result = PdfCoverageEvaluator().evaluate([_page(1, 500, native_extraction_status="failed")], 1)
    assert result.pages[0].is_ocr_candidate is True
    assert result.pages[0].candidate_reason == "native_extraction_failed"


def test_page_below_very_low_meaningful_chars_becomes_ocr_candidate():
    result = PdfCoverageEvaluator().evaluate([_page(1, 29)], 1)
    assert result.pages[0].is_ocr_candidate is True
    assert result.pages[0].count_bucket == "very_low"
    assert result.pages[0].candidate_reason == "very_low_native_text"


@pytest.mark.parametrize(
    ("image_evidence", "expected_candidate", "expected_reason"),
    [
        ("present", True, "low_native_text_image_present"),
        ("unknown", True, "low_native_text_image_unknown"),
        ("absent", False, "low_native_text_image_absent"),
    ],
)
def test_low_native_text_uses_image_evidence(image_evidence, expected_candidate, expected_reason):
    page = PdfCoverageEvaluator().evaluate([_page(1, 30, image_evidence)], 1).pages[0]
    assert page.is_ocr_candidate is expected_candidate
    assert page.candidate_reason == expected_reason


def test_sufficient_native_text_page_skips_ocr():
    page = PdfCoverageEvaluator().evaluate([_page(1, 120, "present")], 1).pages[0]
    assert page.is_ocr_candidate is False
    assert page.count_bucket == "sufficient"
    assert page.candidate_reason == "sufficient_native_text"


def test_max_ocr_pages_uses_document_contract_deterministic_page_order():
    pages = [
        _page(4, 10),
        _page(1, 100, "unknown"),
        _page(3, 500, native_extraction_status="failed"),
        _page(2, 100, "present"),
    ]
    result = PdfCoverageEvaluator().evaluate(pages, max_ocr_pages=2)
    assert result.aggregate.selected_candidate_pages == (1, 2)
    assert result.aggregate.candidate_page_count == 4
    assert result.aggregate.skipped_candidate_count == 2
    assert [page.page_index for page in result.pages] == [1, 2, 3, 4]
    assert [page.selected_for_ocr for page in result.pages] == [True, True, False, False]


def test_low_native_text_ratio_is_metadata_only_and_does_not_expand_candidates():
    result = PdfCoverageEvaluator().evaluate(
        [_page(1, 0), _page(2, 0), _page(3, 0), _page(4, 120)], max_ocr_pages=4
    )
    assert result.aggregate.low_native_text_page_ratio == 0.75
    assert result.aggregate.low_native_text_ratio_warning is False
    assert result.aggregate.selected_candidate_pages == (1, 2, 3)
    assert result.pages[3].is_ocr_candidate is False


def test_ratio_warning_does_not_expand_sufficient_page_into_ocr_candidate():
    result = PdfCoverageEvaluator().evaluate(
        [_page(1, 0), _page(2, 0), _page(3, 0), _page(4, 0), _page(5, 120)], 5
    )
    assert result.aggregate.low_native_text_page_ratio == 0.8
    assert result.aggregate.low_native_text_ratio_warning is True
    assert result.aggregate.selected_candidate_pages == (1, 2, 3, 4)
    assert result.pages[4].is_ocr_candidate is False


def test_downstream_output_contains_only_safe_page_metadata():
    result = PdfCoverageEvaluator().evaluate([_page(7, 10, "unknown")], 1)
    dumped = result.model_dump()
    assert dumped["aggregate"]["selected_candidate_pages"] == (7,)
    exposed = repr(dumped)
    for forbidden in (
        "raw_text", "extracted_text", "filename", "path", "file_ref", "runtime_ref",
        "PRIVATE PAGE TEXT", "C:\\private\\document.pdf",
    ):
        assert forbidden not in exposed


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_index": 0, "meaningful_character_count": 1, "image_evidence": "absent", "native_extraction_status": "success"},
        {"page_index": 1, "meaningful_character_count": -1, "image_evidence": "absent", "native_extraction_status": "success"},
        {"page_index": 1, "meaningful_character_count": 1, "image_evidence": "invalid", "native_extraction_status": "success"},
        {"page_index": 1, "meaningful_character_count": 1, "image_evidence": "absent", "native_extraction_status": "invalid"},
    ],
)
def test_invalid_page_coverage_input_is_rejected_without_private_details(kwargs):
    with pytest.raises(ValidationError):
        PdfPageCoverageInput(**kwargs)


def test_duplicate_page_index_and_negative_budget_are_rejected():
    evaluator = PdfCoverageEvaluator()
    with pytest.raises(ValueError, match="PDF_COVERAGE_DUPLICATE_PAGE"):
        evaluator.evaluate([_page(1, 0), _page(1, 0)], 1)
    with pytest.raises(ValueError, match="PDF_COVERAGE_INVALID_LIMIT"):
        evaluator.evaluate([_page(1, 0)], -1)


def test_meaningful_character_count_uses_nfkc_letters_and_numbers_only():
    assert count_meaningful_characters("ＡＢＣ 123 한글\n\t!@#\u200b") == 8
    assert count_meaningful_characters(" \n\t!@#\u200b") == 0
