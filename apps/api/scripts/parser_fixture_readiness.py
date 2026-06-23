import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.runtime.parser_fixture_readiness import ParserFixtureReadinessProbe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    report = ParserFixtureReadinessProbe().check()
    print(json.dumps(report.model_dump(), sort_keys=True))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
