import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.runtime.local_readiness import LocalRuntimeReadinessProbe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit metadata-only local runtime readiness JSON.")
    parser.add_argument("--include-ocr", action="store_true", help="Include local OCR dependency readiness checks.")
    args = parser.parse_args(argv)

    report = LocalRuntimeReadinessProbe(expected_cuda=True, include_ocr=args.include_ocr).check()
    print(json.dumps(report.model_dump(), sort_keys=True))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
