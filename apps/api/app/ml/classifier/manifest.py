from app.ml.classifier.models import ClassifierArtifactRef


def build_classifier_artifact_ref(
    *,
    artifact_id: str,
    manifest_version: str,
    runtime_version: str,
    target_labels: list[str],
    candidate_threshold: float,
    embedding_model_version: str,
) -> ClassifierArtifactRef:
    return ClassifierArtifactRef(
        artifact_id=artifact_id,
        manifest_version=manifest_version,
        runtime_version=runtime_version,
        target_labels=target_labels,
        candidate_threshold=candidate_threshold,
        embedding_model_version=embedding_model_version,
    )
