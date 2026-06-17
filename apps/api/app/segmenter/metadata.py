from typing import Any

from app.atoms.privacy import length_bucket, location_kind
from app.segmenter.models import AnalysisSegment, SegmentBuildResult


def project_segment_metadata(segment: AnalysisSegment, segmenter_version: str) -> dict[str, Any]:
    first_location = segment.locations[0] if segment.locations else None
    return {
        "segment_id": segment.segment_id,
        "atom_count": len(segment.atom_ids),
        "segment_type": segment.segment_type,
        "length_bucket": length_bucket(len(segment.text)),
        "location_kind": location_kind(first_location),
        "segmenter_version": segmenter_version,
    }


def project_segment_result_metadata(result: SegmentBuildResult) -> dict[str, Any]:
    failure = None if result.failure is None else {"failure_code": result.failure.code, "segmenter_version": result.segmenter_version}
    return {
        "segments": [project_segment_metadata(segment, result.segmenter_version) for segment in result.segments],
        "boundary_score_count": len(result.boundary_scores),
        "failure": failure,
    }
