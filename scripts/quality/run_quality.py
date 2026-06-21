from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.quality import (  # noqa: E402
    QualityFailure,
    architecture_violations,
    baseline_payload,
    compare_baseline,
    load_baseline,
    mypy_findings,
    privacy_violations,
    radon_findings,
    ruff_findings,
    run,
    tracked_files,
    unicode_violations,
    verify_baseline_diff,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-current", action="store_true")
    parser.add_argument("--base-ref", default=os.environ.get("QUALITY_BASE_REF", "origin/main"))
    args = parser.parse_args()
    try:
        findings = {"ruff": ruff_findings(), "mypy": mypy_findings(), "radon": radon_findings()}
        if args.print_current:
            for tool, values in findings.items():
                print(f"--- {tool}.json ---")
                print(baseline_payload(tool, values), end="")
            return 0
        for tool, values in findings.items():
            compare_baseline(values, load_baseline(tool), tool)
        run([sys.executable, "-m", "ruff", "check", "scripts/quality"], check=True)
        run([sys.executable, "-m", "ruff", "format", "--check", "scripts/quality"], check=True)
        run([sys.executable, "-m", "importlinter.cli", "--config", ".importlinter"], check=True)
        problems = {
            "unicode": unicode_violations(tracked_files()),
            "privacy": privacy_violations(),
            "architecture": architecture_violations(),
        }
        for name, values in problems.items():
            if values:
                raise QualityFailure(f"{name} violations: {values}")
        verify_baseline_diff(args.base_ref)
    except QualityFailure as error:
        print(error, file=sys.stderr)
        return 1
    print("Static quality gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
