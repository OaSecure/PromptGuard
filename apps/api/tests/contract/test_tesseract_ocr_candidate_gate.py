import ast
import json
import re
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
REPORT = ROOT / "third_party" / "licenses" / "tesseract_ocr_candidate_report.json"
EVIDENCE = ROOT / "third_party" / "licenses" / "tesseract_isolated_validation_evidence.json"
WORKFLOW = ROOT / ".github" / "workflows" / "tesseract-isolated-validation.yml"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


WINDOWS_LOCAL_EVIDENCE_FIELDS = {
    "scope",
    "status",
    "validation_date",
    "distribution_source",
    "provenance_status",
    "tesseract_version",
    "binary_sha256",
    "eng_traineddata_sha256",
    "input_scope",
    "validation_results",
    "production_artifact",
    "satisfies_linux_production_pin",
    "third_party_binary_provenance_approved",
    "native_dependency_inventory_complete",
    "representative_accuracy_validated",
    "can_satisfy_production_approval",
}
WINDOWS_LOCAL_VALIDATION_RESULT_FIELDS = {
    "synthetic_cli_ocr",
    "pytest_real_ocr",
    "ocr_result_text_surface",
    "parsed_document_text_surface",
    "rendered_image_boundary",
    "selected_page_integrator_boundary",
    "internal_file_ref_runner_boundary",
    "privacy_boundary",
    "cleanup",
}


def _windows_local_evidence_reasons(evidence: dict) -> set[str]:
    reasons: set[str] = set()
    local = evidence.get("windows_local_validation")
    if not isinstance(local, dict) or set(local) != WINDOWS_LOCAL_EVIDENCE_FIELDS:
        return {"WINDOWS_LOCAL_EVIDENCE_SCHEMA_INVALID"}
    sha256 = re.compile(r"^[0-9a-f]{64}$")
    for field in ("binary_sha256", "eng_traineddata_sha256"):
        if not isinstance(local.get(field), str) or sha256.fullmatch(local[field]) is None:
            reasons.add("WINDOWS_LOCAL_EVIDENCE_HASH_INVALID")
    results = local.get("validation_results")
    if not isinstance(results, dict) or set(results) != WINDOWS_LOCAL_VALIDATION_RESULT_FIELDS:
        reasons.add("WINDOWS_LOCAL_EVIDENCE_SCHEMA_INVALID")
    elif set(results.values()) != {"success"}:
        reasons.add("WINDOWS_LOCAL_EVIDENCE_RESULT_INVALID")
    expected = {
        "scope": "local-developer-isolated-validation",
        "status": "additional-validation-required",
        "input_scope": "synthetic-only",
        "production_artifact": False,
        "satisfies_linux_production_pin": False,
        "third_party_binary_provenance_approved": False,
        "native_dependency_inventory_complete": False,
        "representative_accuracy_validated": False,
        "can_satisfy_production_approval": False,
    }
    if any(local.get(field) != value for field, value in expected.items()):
        reasons.add("WINDOWS_LOCAL_EVIDENCE_SCOPE_OVERCLAIMED")
    return reasons


def test_candidate_stays_blocked_until_artifacts_and_native_dependencies_are_reviewed():
    report = _report()
    assert report["schema_version"] == "1"
    assert report["scope"] == "development_contract_pr10_b3_a"
    assert report["validation_phase"] == "pr10_b3_h_runtime_integration_preflight_gate"
    assert report["status"] == "additional-validation-required"
    assert report["approved_for_dependency_addition"] is False
    assert report["approved_for_default_distribution"] is False
    assert report["blockers"]


def test_engine_and_optional_wrapper_are_exact_and_permissively_licensed():
    report = _report()
    engine = report["engine_candidate"]
    assert engine["name"] == "tesseract"
    assert engine["version"] == "5.5.2"
    assert engine["license_id"] == "Apache-2.0"
    assert engine["official_release_url"].startswith("https://github.com/tesseract-ocr/")
    assert engine["candidate_role"] == "source-and-license-review-only"
    assert engine["verified_binary_artifact"] is False
    assert engine["source_archive_sha256_status"] == "artifact-inspection-required"
    wrapper = report["python_wrapper_candidate"]
    assert wrapper["name"] == "pytesseract"
    assert wrapper["version"] == "0.3.13"
    assert wrapper["license_id"] == "Apache-2.0"
    assert wrapper["relationship"] == "optional-subprocess-wrapper"


def test_korean_and_english_traineddata_have_separate_license_evidence():
    models = {item["language"]: item for item in _report()["traineddata_candidates"]}
    assert set(models) == {"kor", "eng"}
    for language, model in models.items():
        assert model["filename"] == f"{language}.traineddata"
        assert model["repository"] == "tesseract-ocr/tessdata"
        assert len(model["repository_commit"]) == 40
        assert model["license_id"] == "Apache-2.0"
        assert model["commercial_use_verified"] is True
        assert model["redistribution_verified"] is True
        assert model["sha256_status"].startswith("verified-in-isolated-ci-run-")
        assert len(model["sha256"]) == 64
        assert model["default_distribution"] is False


def test_traineddata_artifact_gate_requires_pinned_commit_and_checksums():
    report = _report()
    gate = report["traineddata_artifact_gate"]
    assert gate["pinned_repository_commit"] == report["traineddata_repository"]["repository_commit"]
    assert gate["required_artifacts"] == ["kor.traineddata", "eng.traineddata"]
    assert set(gate["required_artifact_reason"]) == set(gate["required_artifacts"])
    assert gate["individual_sha256_recorded"] is True
    assert gate["status"] == "ci-evidence-captured-additional-validation-required"


def test_native_dependency_and_platform_provenance_remain_blockers():
    report = _report()
    native = report["native_dependency_review"]
    assert native["required"] == ["Leptonica"]
    assert "libpng" in native["optional_or_build_selected"]
    assert "libjpeg" in native["optional_or_build_selected"]
    assert native["classification"]["Leptonica"] == "required-engine-dependency"
    assert set(native["classification"]) == {"Leptonica", *native["optional_or_build_selected"]}
    assert native["exact_platform_versions_recorded"] is True
    assert native["status"] == "ubuntu-ci-inventory-captured-other-platforms-blocked"
    platforms = report["platform_delivery"]
    assert platforms["linux"]["status"] == "ubuntu-ci-evidence-captured-production-pin-required"
    assert platforms["windows"]["status"] == "blocked/unverified"
    assert platforms["linux"]["candidates"] == ["distribution package", "pinned internally built source package"]


def test_offline_policy_forbids_runtime_download_and_network():
    policy = _report()["offline_runtime_policy"]
    assert policy == {
        "binary_path": "explicit-local-path-only",
        "tessdata_path": "explicit-local-path-only",
        "automatic_download": "forbidden",
        "runtime_network": "forbidden",
        "missing_artifact": "fail-closed",
        "checksum_mismatch": "fail-before-execution",
    }
    gate = _report()["offline_fail_closed_gate"]
    assert gate["status"] == "candidate-runtime-boundary-implemented-production-disabled"
    assert set(gate["required_controls"]) == {
        "explicit-binary-path",
        "explicit-tessdata-path",
        "no-automatic-download",
        "no-runtime-network",
        "missing-binary-fail-closed",
        "missing-tessdata-fail-closed",
        "checksum-mismatch-fail-before-execution",
    }
    assert gate["production_approval"] is False


def test_paddleocr_b2_remains_deferred():
    decision = _report()["paddleocr_b2_decision"]
    assert decision == {
        "status": "deferred/blocked",
        "changed_by_this_gate": False,
        "gate_separation": "must-not-share-tesseract-isolated-validation-gate",
    }


def test_heavy_validation_is_required_only_in_an_isolated_environment():
    gate = _report()["isolated_validation_gate"]
    assert gate["status"] == "additional-validation-required"
    assert set(gate["execution_environment"]) == {
        "ci-runner",
        "dedicated-remote-isolated-environment",
    }
    assert gate["local_developer_machine_execution"] == "forbidden"
    assert set(gate["required_validations"]) == {
        "kor-traineddata-sha256",
        "eng-traineddata-sha256",
        "linux-package-version-and-sha256",
        "windows-binary-provenance",
        "leptonica-and-codec-dependency-inventory",
        "offline-ocr-smoke-test",
        "runtime-network-deny-test",
    }
    assert set(gate["local_prohibited_operations"]) == {
        "apt-install",
        "chocolatey-install",
        "pip-install",
        "tessdata-download",
        "ocr-execution",
        "docker-build",
        "heavy-validation",
    }


def test_isolated_gate_keeps_fail_closed_controls_and_follow_up_boundary():
    gate = _report()["isolated_validation_gate"]
    assert set(gate["fail_closed_acceptance_criteria"]) == {
        "missing-explicit-binary-path-fails",
        "missing-explicit-tessdata-path-fails",
        "missing-checksum-blocks-production-approval",
        "checksum-mismatch-fails-before-execution",
        "automatic-download-is-forbidden",
        "runtime-network-is-forbidden",
    }
    assert gate["github_actions_workflow_added_in_this_pr"] is False
    assert gate["workflow_trigger"] == "workflow_dispatch-only"
    assert gate["workflow_path"] == ".github/workflows/tesseract-isolated-validation.yml"
    assert gate["workflow_implementation"] == "manual-ci-validation-workflow-evidenced-in-run-27927632968"
    assert gate["artifact_installation_and_validation"] == "successful-in-manual-ci-run-27927632968"
    assert gate["evidence_file"] == "third_party/licenses/tesseract_isolated_validation_evidence.json"
    assert gate["production_approval"] is False
    follow_up = _report()["next_validation"]
    assert follow_up["required_location"] == "ci-runner-or-dedicated-remote-isolated-environment"


def test_isolated_validation_workflow_is_manual_only_and_preserves_evidence():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    trigger_section = workflow.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_section
    assert "pull_request:" not in trigger_section
    assert "push:" not in trigger_section
    assert "runs-on: ubuntu-24.04" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if: always()" in workflow


def test_isolated_validation_workflow_covers_required_gate_operations():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    required_fragments = {
        "kor.traineddata",
        "eng.traineddata",
        "sha256sum",
        "tesseract --version",
        "dpkg-query",
        "liblept5",
        "windows-binary-provenance.txt",
        "Run offline OCR smoke test",
        "unshare --net",
    }
    assert all(fragment in workflow for fragment in required_fragments)


def test_isolated_ci_evidence_is_scoped_and_does_not_approve_production():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["status"] == "additional-validation-required"
    assert evidence["production_approval"] is False
    run = evidence["workflow_run"]
    assert run["id"] == 27927632968
    assert run["event"] == "workflow_dispatch"
    assert run["conclusion"] == "success"
    assert run["runner_label"] == "ubuntu-24.04"
    assert evidence["artifact"]["created"] is True
    assert evidence["artifact"]["downloaded_to_local_developer_machine"] is False


def test_isolated_ci_evidence_records_hashes_runtime_and_remaining_mismatch():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    artifacts = evidence["traineddata"]["artifacts"]
    models = {item["filename"]: item for item in _report()["traineddata_candidates"]}
    assert set(artifacts) == {"kor.traineddata", "eng.traineddata"}
    for filename, artifact in artifacts.items():
        assert artifact["verified"] is True
        assert len(artifact["sha256"]) == 64
        assert models[filename]["sha256"] == artifact["sha256"]
    linux = evidence["linux_runtime"]
    assert linux["binary_path"] == "/usr/bin/tesseract"
    assert linux["tesseract_version"] == "5.3.4"
    assert linux["candidate_version_match"] is False
    assert evidence["runtime_tests"]["offline_ocr_smoke"]["conclusion"] == "success"
    assert evidence["runtime_tests"]["runtime_network_deny"]["conclusion"] == "success"
    assert evidence["windows_provenance"]["third_party_or_internal_binary_verified"] is False
    assert evidence["unverified_or_blocked"]


def test_verified_linux_artifact_is_separate_from_552_source_candidate():
    report = _report()
    candidate = report["verified_linux_candidate"]
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    linux = evidence["linux_runtime"]
    assert report["engine_candidate"]["version"] == "5.5.2"
    assert candidate["package"] == "tesseract-ocr 5.3.4-1build5 amd64"
    assert candidate["binary_path"] == "/usr/bin/tesseract"
    assert candidate["binary_sha256"] == linux["binary_sha256"]
    assert candidate["leptonica_package"] == "liblept5 1.82.0-3build4 amd64"
    assert candidate["native_dependency_inventory_verified"] is True
    assert candidate["offline_ocr_smoke_verified"] is True
    assert candidate["runtime_network_deny_verified"] is True
    separation = evidence["artifact_separation_gate"]
    assert separation["same_artifact"] is False
    assert separation["source_license_candidate_is_verified_binary"] is False
    assert separation["production_approval"] is False


def test_platform_evidence_cannot_implicitly_approve_production():
    report = _report()
    gate = report["production_approval_gate"]
    assert report["verified_linux_candidate"]["production_artifact_pin"] is False
    assert report["verified_linux_candidate"]["production_approval"] is False
    assert gate["status"] == "blocked-policy-requirements-not-satisfied"
    assert gate["production_approval"] is False
    assert gate["linux_verified_candidate_is_production_approved"] is False
    assert gate["linux_and_windows_approval_must_not_be_combined"] is True
    assert gate["required_before_approval"] == {
        "exact_linux_package_pin": "required-not-satisfied",
        "native_dependency_version_pins": "required-not-satisfied",
        "runtime_integration_validation": "required-not-satisfied",
        "ocr_recognition_accuracy_validation": "required-not-satisfied",
    }
    assert gate["independent_blockers"] == {
        "windows_binary_provenance_hash_runtime_smoke": "blocked/unverified",
        "tesseract_5_5_2_binary_or_source_archive_sha256": "artifact-inspection-required",
    }
    windows = report["platform_delivery"]["windows"]
    assert windows["status"] == "blocked/unverified"
    assert windows["binary_provenance_verified"] is False
    assert windows["artifact_sha256_recorded"] is False
    assert windows["runtime_smoke_verified"] is False


def test_evidence_cannot_satisfy_production_pin_policy_by_itself():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    policy = evidence["production_pin_policy"]
    assert policy["status"] == "requirements-not-satisfied"
    assert policy["linux_candidate_verified"] is True
    assert policy["linux_candidate_production_approved"] is False
    for requirement in (
        "exact_linux_package_pin_satisfied",
        "native_dependency_version_pins_satisfied",
        "runtime_integration_validation_satisfied",
        "ocr_recognition_accuracy_validation_satisfied",
    ):
        assert policy[requirement] is False
    assert policy["windows_blocker_is_independent"] is True
    assert policy["tesseract_5_5_2_artifact_inspection_is_independent"] is True
    assert policy["production_approval"] is False


def test_windows_local_validation_evidence_is_privacy_safe_and_not_production_approval():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    local = evidence["windows_local_validation"]

    assert _windows_local_evidence_reasons(evidence) == set()
    assert set(local) == WINDOWS_LOCAL_EVIDENCE_FIELDS
    assert set(local["validation_results"]) == WINDOWS_LOCAL_VALIDATION_RESULT_FIELDS
    serialized = json.dumps(local, sort_keys=True)
    for forbidden in (
        "C:\\Users\\",
        "Program Files",
        "AppData",
        "TEMP",
        "stdout",
        "stderr",
        "argv",
        "original_filename",
        "raw_exception",
        "HELLO OCR",
    ):
        assert forbidden not in serialized


def test_windows_local_validation_hashes_fail_closed_when_missing_or_malformed():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for field in ("binary_sha256", "eng_traineddata_sha256"):
        missing = deepcopy(evidence)
        del missing["windows_local_validation"][field]
        assert _windows_local_evidence_reasons(missing)

        malformed = deepcopy(evidence)
        malformed["windows_local_validation"][field] = "NOT-A-SHA256"
        assert "WINDOWS_LOCAL_EVIDENCE_HASH_INVALID" in _windows_local_evidence_reasons(
            malformed
        )


def test_windows_local_validation_scope_overclaim_fails_closed():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for field in (
        "production_artifact",
        "satisfies_linux_production_pin",
        "third_party_binary_provenance_approved",
        "native_dependency_inventory_complete",
        "representative_accuracy_validated",
        "can_satisfy_production_approval",
    ):
        overclaimed = deepcopy(evidence)
        overclaimed["windows_local_validation"][field] = True
        assert "WINDOWS_LOCAL_EVIDENCE_SCOPE_OVERCLAIMED" in _windows_local_evidence_reasons(
            overclaimed
        )


def test_runtime_integration_preflight_requires_bounded_fail_closed_controls():
    gate = _report()["runtime_integration_preflight_gate"]
    assert gate["status"] == "candidate-runtime-boundary-implemented-production-disabled"
    assert set(gate["required_controls"]) == {
        "explicit-binary-path",
        "explicit-tessdata-directory",
        "allowed-language-allowlist",
        "required-traineddata-exists",
        "binary-checksum-verified",
        "traineddata-checksum-verified",
        "production-package-pin-verified",
        "native-dependency-pins-verified",
        "bounded-timeout-required",
        "bounded-input-size-required",
        "bounded-output-size-required",
        "no-runtime-network",
        "no-automatic-download",
        "argv-invocation-only-no-shell-string",
        "temporary-file-policy-and-cleanup-required",
        "all-failures-fail-closed",
    }
    assert gate["bounded_values_defined_in_this_gate"] is False
    assert gate["platform_evaluation"] == "linux-and-windows-independent"
    assert set(gate["preflight_success_means"].values()) == {False}
    assert gate["production_approval"] is False


def test_runtime_preflight_defines_required_failure_cases():
    failures = set(_report()["runtime_integration_preflight_gate"]["failure_cases"])
    assert failures == {
        "binary-missing",
        "traineddata-missing",
        "timeout",
        "unsupported-language",
        "ocr-failed",
        "network-access-attempted",
        "binary-checksum-mismatch",
        "traineddata-checksum-mismatch",
        "invalid-or-untrusted-path",
        "native-dependency-pin-mismatch",
        "malformed-ocr-output",
        "output-size-limit-exceeded",
        "temporary-file-create-or-delete-failure",
        "process-spawn-failure",
        "unexpected-exit-code",
        "unverified-windows-binary-selected",
    }


def test_runtime_preflight_protects_ocr_content_and_paths():
    controls = set(_report()["runtime_integration_preflight_gate"]["security_and_privacy_controls"])
    assert controls == {
        "no-ocr-source-text-logging",
        "no-original-filename-logging",
        "no-full-extracted-text-in-error-response",
        "no-full-extracted-text-persistent-storage",
        "no-raw-subprocess-stdout-or-stderr-logging",
        "no-unnecessary-temporary-or-user-path-exposure",
        "limited-error-codes-and-deidentified-metadata-only",
        "no-shell-string-composition",
        "no-ocr-input-to-external-service-or-network",
        "no-partial-failure-result-in-log-response-or-storage",
    }


def test_existing_evidence_does_not_claim_runtime_or_accuracy_validation():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    scope = evidence["runtime_integration_preflight_scope"]
    assert scope["status"] == "requirements-not-satisfied"
    assert scope["existing_linux_evidence_preserved"] is True
    for claim in (
        "runtime_integration_validated",
        "ocr_recognition_accuracy_validated",
        "preflight_contract_implemented_in_runtime",
        "preflight_success_would_prove_ocr_success",
        "preflight_success_would_prove_accuracy",
        "preflight_success_would_approve_production",
        "production_approval",
    ):
        assert scope[claim] is False


def test_follow_up_work_excludes_completed_candidate_runtime_boundaries():
    follow_up = _report()["next_validation"]["follow_up_pr_boundary"]
    assert follow_up == [
        "B3-K: OCR accuracy corpus/acceptance policy",
        "B3-L: production artifact/native dependency pin decision",
        "separate: Windows artifact validation or Windows support exclusion decision",
    ]


def test_blocked_candidate_is_absent_from_requirements_active_artifacts_and_app_imports():
    requirement_text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in (API / "requirements.txt", API / "requirements-ocr.lock")
    )
    assert "pytesseract" not in requirement_text
    active = "\n".join(
        (ROOT / "third_party" / "licenses" / name).read_text(encoding="utf-8").lower()
        for name in (
            "parser_ocr_sbom.json",
            "parser_ocr_license_report.json",
            "ocr_model_weight_license_report.json",
            "NOTICE.parser_ocr.txt",
        )
    )
    assert "tesseract" not in active
    offenders = []
    for path in (API / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        imports.update(
            node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        )
        if imports & {"pytesseract", "tesserocr"}:
            offenders.append(str(path.relative_to(API)))
    assert offenders == []
