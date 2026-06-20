from pathlib import Path
from typing import Any


class RobertaVerifierLoadError(Exception):
    def __init__(self, code: str, message: str, metadata: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class HuggingFaceRobertaPairScorer:
    def __init__(self, tokenizer: Any, model: Any, torch_module: Any) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch_module

    def score_positive_probabilities(self, pair_texts: list[str], *, max_length_tokens: int) -> list[float]:
        encoded = self._tokenizer(
            pair_texts,
            padding=True,
            truncation=True,
            max_length=max_length_tokens,
            return_tensors="pt",
        )
        self._model.eval()
        with self._torch.no_grad():
            output = self._model(**encoded)
            probabilities = self._torch.softmax(output.logits, dim=-1)
        return [float(row[1].item()) for row in probabilities]


def load_huggingface_roberta_pair_scorer(verifier_dir: str | Path) -> HuggingFaceRobertaPairScorer:
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RobertaVerifierLoadError(
            code="VERIFIER_ARTIFACT_DEPENDENCY_MISSING",
            message="verifier artifact dependency is unavailable",
        ) from exc

    path = Path(verifier_dir)
    if not path.is_dir():
        raise RobertaVerifierLoadError(code="VERIFIER_ARTIFACT_NOT_FOUND", message="verifier artifact directory was not found")

    try:
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True)
    except Exception as exc:
        raise RobertaVerifierLoadError(code="VERIFIER_ARTIFACT_LOAD_FAILED", message="verifier artifact could not be loaded") from exc

    return HuggingFaceRobertaPairScorer(tokenizer=tokenizer, model=model, torch_module=torch)
