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
    failures.extend(scan_dist_for_content_script_module_syntax())
    failures.extend(scan_src_for_raw_console_logging())
    failures.extend(scan_src_for_exported_surface_docs())

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


def scan_dist_for_content_script_module_syntax() -> list[str]:
    content_script = EXTENSION_DIR / "dist" / "contentScript.js"
    if not content_script.is_file():
        return ["content script build output missing: apps/extension/dist/contentScript.js"]
    failures: list[str] = []
    lines = content_script.read_text(encoding="utf-8", errors="ignore").splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("import ") or stripped.startswith("export "):
            rel_path = content_script.relative_to(ROOT)
            failures.append(f"content script must be bundled as non-module script: {rel_path}:{index + 1}")
    return failures


def scan_src_for_raw_console_logging() -> list[str]:
    return scan_paths([EXTENSION_DIR / "src"], ["console.log", "console.error", "console.warn"], "console logging in source")


def scan_src_for_exported_surface_docs() -> list[str]:
    export_prefixes = (
        "export function ",
        "export async function ",
        "export interface ",
        "export type ",
        "export const ",
        "export class ",
        "export enum ",
        "export let ",
        "export var ",
    )
    failures: list[str] = []
    for file_path in sorted((EXTENSION_DIR / "src").rglob("*.ts")):
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith(export_prefixes):
                continue
            if has_jsdoc_before(lines, index):
                continue
            rel_path = file_path.relative_to(ROOT)
            surface = describe_exported_surface(stripped)
            failures.append(f"missing JSDoc/TSDoc before exported surface: {rel_path}:{index + 1} {surface}")
    return failures


def has_jsdoc_before(lines: list[str], export_index: int) -> bool:
    index = export_index - 1
    while index >= 0 and lines[index].strip() == "":
        index -= 1
    if index < 0 or not lines[index].strip().endswith("*/"):
        return False
    while index >= 0:
        stripped = lines[index].strip()
        if stripped.startswith("/**"):
            return True
        if stripped.startswith("*") or stripped == "*/" or stripped.endswith("*/"):
            index -= 1
            continue
        return False
    return False


def describe_exported_surface(line: str) -> str:
    for prefix in ("export async function ", "export function ", "export interface ", "export type ", "export const ", "export class ", "export enum ", "export let ", "export var "):
        if line.startswith(prefix):
            return line[len(prefix):].split("(", 1)[0].split("=", 1)[0].strip()
    return line


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
