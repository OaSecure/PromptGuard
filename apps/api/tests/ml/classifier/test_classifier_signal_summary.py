from app.atoms.models import PipelineFailure
from app.ml.classifier import (
    SegmentClassificationCandidate,
    SegmentClassificationResult,
    project_classification_signal_summary,
)


def candidate(label: str, score: float, segment_id: str = "segment-1") -> SegmentClassificationCandidate:
    return SegmentClassificationCandidate(
        segment_id=segment_id,
        label=label,
        score=score,
        threshold=0.575,
        artifact_id="lr-v205",
        runtime_version="lr-runtime-v1",
    )


def test_signal_summary_groups_candidates_without_policy_action_or_raw_scores():
    result = SegmentClassificationResult(
        input_id="input-SECRET-RAW-PROMPT",
        candidates=[
            candidate("secret", 0.99),
            candidate("credential", 0.8),
            candidate("safe_example", 0.6),
            candidate("unknown_label", 0.7),
        ],
    )

    summary = project_classification_signal_summary(result)

    assert summary == {
        "candidate_count": 4,
        "has_candidates": True,
        "highest_score_bucket": "very_high",
        "label_groups": {"risk": 2, "suppressor": 1, "code": 0, "pii_relevance": 0, "other": 1},
        "failure": None,
    }

    summary_text = str(summary)
    assert "action" not in summary_text
    assert "0.99" not in summary_text
    assert "0.8" not in summary_text
    assert "0.6" not in summary_text
    assert "lr-v205" not in summary_text
    assert "lr-runtime-v1" not in summary_text
    assert "SECRET-RAW-PROMPT" not in summary_text


def test_signal_summary_returns_empty_groups_for_no_candidates():
    summary = project_classification_signal_summary(SegmentClassificationResult(input_id="input-1"))

    assert summary == {
        "candidate_count": 0,
        "has_candidates": False,
        "highest_score_bucket": None,
        "label_groups": {"risk": 0, "suppressor": 0, "code": 0, "pii_relevance": 0, "other": 0},
        "failure": None,
    }


def test_signal_summary_projects_failures_without_raw_details():
    result = SegmentClassificationResult(
        input_id="input-FILE-NAME-SECRET.txt",
        failure=PipelineFailure(
            code="classifier_unavailable",
            message="raw prompt leaked in exception",
            metadata={
                "file_content": "FILE-CONTENT-SENTINEL",
                "extracted_text": "EXTRACTED-TEXT-SENTINEL",
                "detected_raw_value": "DETECTED-RAW-VALUE-SENTINEL",
                "vector": [0.12345, 0.98765],
            },
        ),
    )

    summary = project_classification_signal_summary(result)
    summary_text = str(summary)

    assert summary == {
        "candidate_count": 0,
        "has_candidates": False,
        "highest_score_bucket": None,
        "label_groups": {"risk": 0, "suppressor": 0, "code": 0, "pii_relevance": 0, "other": 0},
        "failure": {"code": "classifier_unavailable"},
    }
    assert "raw prompt" not in summary_text
    assert "FILE-CONTENT-SENTINEL" not in summary_text
    assert "EXTRACTED-TEXT-SENTINEL" not in summary_text
    assert "DETECTED-RAW-VALUE-SENTINEL" not in summary_text
    assert "SECRET.txt" not in summary_text
    assert "0.12345" not in summary_text
    assert "vector" not in summary_text
