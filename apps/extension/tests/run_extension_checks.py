from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXTENSION_DIR = ROOT / "apps" / "extension"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target not in {"all", "prompt-preflight", "file-upload-preflight"}:
        print(f"Unsupported check target: {target}", file=sys.stderr)
        return 2

    commands = [
        ["run", "typecheck"],
        ["test"],
        ["run", "build"],
    ]

    for args in commands:
        code = run_npm(args)
        if code != 0:
            return code

    failures = []
    failures.extend(scan_for_network_monitoring())
    failures.extend(scan_dist_for_forbidden_seeds())
    failures.extend(scan_src_for_raw_console_logging())

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("PromptGuard extension checks passed.")
    return 0


def run_npm(args: list[str]) -> int:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        print("npm is not available.", file=sys.stderr)
        return 127

    command = [npm, *args]
    print(f"Running: {' '.join(['npm', *args])}")
    completed = subprocess.run(
        command,
        cwd=EXTENSION_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        shell=False,
    )
    print(completed.stdout)
    return completed.returncode


def scan_for_network_monitoring() -> list[str]:
    patterns = ["chrome.webRequest", "chrome.declarativeNetRequest", "declarativeNetRequest", '"webRequest"']
    paths = [EXTENSION_DIR / "manifest.json", EXTENSION_DIR / "src", EXTENSION_DIR / "tests"]
    return scan_paths(paths, patterns, "network monitoring token")


def scan_dist_for_forbidden_seeds() -> list[str]:
    patterns = [
        "SEEDED_PROMPT_SHOULD_NOT_SURVIVE",
        "SEEDED_FILE_SHOULD_NOT_SURVIVE",
        "SEEDED_CONTENT_TEXT_SHOULD_NOT_SURVIVE",
        "SEEDED_TEXT_SHOULD_NOT_SURVIVE",
        "SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE",
        "customer-project.env",
        "quarterly-plan.txt",
        "secret-value",
        "copied sensitive phrase",
    ]
    return scan_paths([EXTENSION_DIR / "dist"], patterns, "forbidden seed in build output")


def scan_src_for_raw_console_logging() -> list[str]:
    return scan_paths([EXTENSION_DIR / "src"], ["console.log", "console.error", "console.warn"], "console logging in source")


def scan_paths(paths: list[Path], patterns: list[str], label: str) -> list[str]:
    failures: list[str] = []
    for path in paths:
        files = [path] if path.is_file() else list(path.rglob("*"))
        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".ts", ".js", ".json", ".html", ".css"}:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in patterns:
                if pattern in text:
                    rel_path = file_path.relative_to(ROOT)
                    failures.append(f"{label}: {rel_path} contains {pattern}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
