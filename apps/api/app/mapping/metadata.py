from typing import Any

from app.mapping.models import SignalMappingResult


def project_signal_mapping_metadata(result: SignalMappingResult) -> dict[str, Any]:
    return {
        "input_id": result.input_id,
        "mapper_version": result.mapper_version,
        "segment_signal_sets": [
            {
                "segment_id": signal_set.segment_id,
                "signal_ids": signal_set.signal_ids,
                "signal_count": signal_set.signal_count,
                "max_severity": signal_set.max_severity,
            }
            for signal_set in result.segment_signal_sets
        ],
        "failure": None if result.failure is None else {"failure_code": result.failure.code},
    }
