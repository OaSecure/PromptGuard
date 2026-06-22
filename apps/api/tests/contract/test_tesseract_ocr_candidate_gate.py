import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
REPORT = ROOT / "third_party" / "licenses" / "tesseract_ocr_candidate_report.json"
WORKFLOW = ROOT / ".github" / "workflows" / "tesseract-isolated-validation.yml"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_candidate_stays_blocked_until_artifacts_and_native_dependencies_are_reviewed():
    report = _report()
    assert report["schema_version"] == "1"
    assert report["scope"] == "development_contract_pr10_b3_a"
    assert report["validation_phase"] == "pr10_b3_d_isolated_ci_validation_workflow"
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
        assert model["sha256_status"] == "artifact-inspection-required"
        assert model["default_distribution"] is False


def test_traineddata_artifact_gate_requires_pinned_commit_and_checksums():
    report = _report()
    gate = report["traineddata_artifact_gate"]
    assert gate["pinned_repository_commit"] == report["traineddata_repository"]["repository_commit"]
    assert gate["required_artifacts"] == ["kor.traineddata", "eng.traineddata"]
    assert set(gate["required_artifact_reason"]) == set(gate["required_artifacts"])
    assert gate["individual_sha256_recorded"] is False
    assert gate["status"] == "artifact-inspection-required"


def test_native_dependency_and_platform_provenance_remain_blockers():
    report = _report()
    native = report["native_dependency_review"]
    assert native["required"] == ["Leptonica"]
    assert "libpng" in native["optional_or_build_selected"]
    assert "libjpeg" in native["optional_or_build_selected"]
    assert native["classification"]["Leptonica"] == "required-engine-dependency"
    assert set(native["classification"]) == {"Leptonica", *native["optional_or_build_selected"]}
    assert native["exact_platform_versions_recorded"] is False
    assert native["status"] == "blocked-platform-artifact-inventory-required"
    platforms = report["platform_delivery"]
    assert platforms["linux"]["status"] == "distribution-package-pin-required"
    assert platforms["windows"]["status"] == "official-project-binary-unavailable"
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
    assert gate["status"] == "contract-defined-runtime-not-implemented"
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
    assert gate["github_actions_workflow_added_in_this_pr"] is True
    assert gate["workflow_trigger"] == "workflow_dispatch-only"
    assert gate["workflow_path"] == ".github/workflows/tesseract-isolated-validation.yml"
    assert gate["workflow_implementation"] == "manual-ci-validation-workflow-defined-not-yet-evidenced"
    assert gate["artifact_installation_and_validation"] == "ci-runner-only-on-manual-dispatch"
    assert gate["production_approval"] is False
    follow_up = _report()["next_validation"]
    assert follow_up["required_location"] == "ci-runner-or-dedicated-remote-isolated-environment"
    assert "manual workflow dispatch and isolated evidence collection" in follow_up["follow_up_pr_boundary"]
    assert "separate approval decision after validation evidence is reviewed" in follow_up["follow_up_pr_boundary"]


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
