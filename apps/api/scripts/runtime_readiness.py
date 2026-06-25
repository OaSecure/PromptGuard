import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.runtime.local_readiness import LocalRuntimeReadinessProbe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit metadata-only local runtime readiness JSON.")
    parser.add_argument("--include-ocr", action="store_true", help="Include local OCR dependency readiness checks.")
    parser.add_argument(
        "--target",
        choices=("torch", "ocr", "all"),
        default=None,
        help="Check one split worker runtime instead of the legacy combined runtime.",
    )
    args = parser.parse_args(argv)
    include_torch = args.target in (None, "torch", "all")
    include_ocr = args.include_ocr or args.target in ("ocr", "all")
    if args.target == "ocr":
        include_torch = False

    with _suppress_probe_output():
        report = LocalRuntimeReadinessProbe(
            expected_cuda=True,
            include_torch=include_torch,
            include_ocr=include_ocr,
        ).check()
    print(json.dumps(report.model_dump(), sort_keys=True))
    return 0 if report.ready else 1


@contextlib.contextmanager
def _suppress_probe_output() -> Iterator[None]:
    try:
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError, io.UnsupportedOperation):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield
        return

    saved_stdout = os.dup(stdout_fd)
    saved_stderr = os.dup(stderr_fd)
    try:
        with tempfile.TemporaryFile(mode="w+b") as sink:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), stdout_fd)
            os.dup2(sink.fileno(), stderr_fd)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, stdout_fd)
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stdout)
        os.close(saved_stderr)


if __name__ == "__main__":
    raise SystemExit(main())
