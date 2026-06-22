from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy, request_satisfies_policy, safe_environment
from app.infrastructure.ocr.process_port import OcrProcessRequest


def _request(**updates: object) -> OcrProcessRequest:
    values = {
        "image_handle": "opaque-image",
        "argv": ("/opt/tesseract/bin/tesseract", "stdin", "stdout", "tsv"),
        "timeout_ms": 100,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
    }
    values.update(updates)
    return OcrProcessRequest(**values)  # type: ignore[arg-type]


def test_policy_requires_argv_tuple_and_forbids_shell_download_and_network_fallback():
    assert request_satisfies_policy(_request()) is True
    assert request_satisfies_policy(_request(argv=["tesseract"])) is False
    assert request_satisfies_policy(_request(shell=True)) is False
    assert request_satisfies_policy(_request(allow_network_fallback=True)) is False
    assert request_satisfies_policy(_request(allow_automatic_download=True)) is False


def test_policy_requires_positive_bounded_values():
    assert request_satisfies_policy(_request(timeout_ms=0)) is False
    assert request_satisfies_policy(_request(max_input_bytes=0)) is False
    assert request_satisfies_policy(_request(max_output_bytes=0)) is False


def test_safe_environment_only_passes_explicit_allowlist_and_is_sorted():
    policy = ProcessExecutionPolicy(
        allowed_environment_keys=frozenset({"LANG", "OMP_THREAD_LIMIT"}),
        environment={
            "SECRET_TOKEN": "PRIVATE_ENV_SECRET",
            "OMP_THREAD_LIMIT": "1",
            "LANG": "C.UTF-8",
        },
    )
    assert safe_environment(policy) == (("LANG", "C.UTF-8"), ("OMP_THREAD_LIMIT", "1"))


def test_policy_copies_environment_to_prevent_later_mutation():
    environment = {"LANG": "C.UTF-8"}
    policy = ProcessExecutionPolicy(frozenset({"LANG"}), environment)
    environment["LANG"] = "PRIVATE_MUTATION"
    assert safe_environment(policy) == (("LANG", "C.UTF-8"),)
