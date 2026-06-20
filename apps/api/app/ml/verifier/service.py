from app.atoms.models import PipelineFailure
from app.ml.verifier.models import RobertaVerificationRequest, RobertaVerificationResult, VerifierModelPort


class RobertaVerifierService:
    def __init__(self, model: VerifierModelPort) -> None:
        self._model = model

    def verify(self, request: RobertaVerificationRequest) -> RobertaVerificationResult:
        if not request.candidates:
            return RobertaVerificationResult(input_id=request.input_id)

        try:
            result = self._model.verify(request)
        except Exception:
            return _failed(request.input_id, "VERIFIER_MODEL_FAILED", "verifier model failed closed")

        if result.input_id != request.input_id:
            return _failed(request.input_id, "VERIFIER_INPUT_MISMATCH", "verifier returned a different input_id")

        allowed_pairs = {(candidate.segment_id, candidate.candidate_label) for candidate in request.candidates}
        returned_pairs = {(evidence.segment_id, evidence.candidate_label) for evidence in result.verifications}
        if not returned_pairs.issubset(allowed_pairs):
            return _failed(request.input_id, "VERIFIER_SCOPE_VIOLATION", "verifier returned a non-candidate segment-label pair")

        return result


def _failed(input_id: str, code: str, message: str) -> RobertaVerificationResult:
    return RobertaVerificationResult(input_id=input_id, failure=PipelineFailure(code=code, message=message))

