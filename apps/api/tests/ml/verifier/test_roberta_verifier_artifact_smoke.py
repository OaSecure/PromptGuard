import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ml.verifier.loader import load_huggingface_roberta_pair_scorer
from app.ml.verifier import RobertaVerificationCandidate, RobertaVerificationRequest
from app.ml.verifier.factory import build_verifier_service_from_manifest


def test_roberta_pair_scorer_loader_moves_model_and_batches_to_cuda_when_available(tmp_path, monkeypatch):
    verifier_dir = tmp_path / "verifier"
    verifier_dir.mkdir()
    calls: list[tuple[str, str]] = []

    class FakeTensor:
        def __init__(self, name: str) -> None:
            self.name = name

        def to(self, device: str) -> "FakeTensor":
            calls.append((f"{self.name}.to", device))
            return self

        def item(self) -> float:
            return 0.91

    class FakeProbabilityRows:
        def __iter__(self):
            return iter([[FakeTensor("negative"), FakeTensor("positive")]])

    class FakeLogits:
        pass

    class FakeModel:
        def to(self, device: str) -> "FakeModel":
            calls.append(("model.to", device))
            return self

        def eval(self) -> None:
            calls.append(("model.eval", "called"))

        def __call__(self, **encoded):
            calls.append(("model.call.input_ids", encoded["input_ids"].name))
            return SimpleNamespace(logits=FakeLogits())

    class FakeTokenizer:
        def __call__(self, pair_texts, **kwargs):
            calls.append(("tokenizer.batch_size", str(len(pair_texts))))
            return {"input_ids": FakeTensor("input_ids"), "attention_mask": FakeTensor("attention_mask")}

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True),
        no_grad=lambda: _NoopContext(),
        softmax=lambda logits, dim: FakeProbabilityRows(),
    )
    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda path, local_files_only: FakeTokenizer()),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=lambda path, local_files_only: FakeModel()),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    scorer = load_huggingface_roberta_pair_scorer(verifier_dir)
    scores = scorer.score_positive_probabilities(["Label: SECRET\n\nText:\ncontext"], max_length_tokens=384)

    assert scores == [0.91]
    assert ("model.to", "cuda") in calls
    assert ("input_ids.to", "cuda") in calls
    assert ("attention_mask.to", "cuda") in calls


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def test_optional_real_roberta_artifact_smoke_loads_when_configured():
    artifact_dir = os.getenv("PROMPTGUARD_TEST_VERIFIER_ARTIFACT_DIR")
    if not artifact_dir:
        pytest.skip("PROMPTGUARD_TEST_VERIFIER_ARTIFACT_DIR is not configured")

    artifact_root = Path(artifact_dir)
    manifest_path = artifact_root / "models" / "context_lr_roberta_active_best_f1_manifest.json"

    bundle = build_verifier_service_from_manifest(manifest_path, artifact_root=artifact_root)
    result = bundle.service.verify(
        RobertaVerificationRequest(
            input_id="input-1",
            candidates=[
                RobertaVerificationCandidate(
                    segment_id="segment-1",
                    candidate_label="SECRET_CREDENTIAL_CONTEXT",
                    text="api_key = 'pg_live_1234567890abcdef'",
                )
            ],
            artifact=bundle.artifact,
            timeout_ms=3000,
        )
    )

    assert result.failure is None
    assert len(result.verifications) == 1
    assert result.verifications[0].candidate_label == "SECRET_CREDENTIAL_CONTEXT"
    assert result.verifications[0].verifier_status in {"confirmed", "rejected"}
