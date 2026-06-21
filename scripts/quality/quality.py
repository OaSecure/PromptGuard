from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "scripts" / "quality" / "baselines"
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yml", ".yaml", ".toml", ".ini"}
EXCLUDED_PARTS = {"node_modules", "dist", "build", "third_party", "vendor", "__pycache__", ".pytest_cache"}
PERSISTENCE_FILES = (
    "apps/api/app/models/events.py",
    "apps/api/app/privacy/event_serializer.py",
    "apps/api/app/events/writer.py",
)
FORBIDDEN_FIELDS = {
    "raw_text",
    "raw_prompt",
    "full_prompt",
    "masked_prompt",
    "full_masked_prompt",
    "file_ref",
    "filename",
    "original_filename",
    "file_content",
    "parsed_text",
    "ocr_text",
    "normalized_text",
    "atom_text",
    "segment_text",
    "embedding",
    "embedding_vector",
    "vector",
    "logit",
    "logits",
    "exact_score",
    "size_bytes",
}
BIDI = {"RLE", "LRE", "RLO", "LRO", "PDF", "RLI", "LRI", "FSI", "PDI"}
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}


class QualityFailure(RuntimeError):
    pass


def normalize_path(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    root = str(ROOT).replace("\\", "/").rstrip("/") + "/"
    if text.lower().startswith(root.lower()):
        text = text[len(root) :]
    marker = "/apps/"
    if marker in text and not text.startswith("apps/"):
        text = "apps/" + text.split(marker, 1)[1]
    return text.lstrip("./")


def normalized_message(value: str) -> str:
    value = re.sub(r"[A-Za-z]:[/\\][^\s:]+|(?<![\w\"'])/(?:[^\s:]+/)+[^\s:]+", "<path>", value)
    value = re.sub(r"\bline \d+\b|:\d+(?::\d+)?", "", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def fingerprint(tool: str, path: str, code: str, message: str, snippet: str = "") -> str:
    parts = [tool, normalize_path(path), code, normalized_message(message), " ".join(snippet.split())]
    return "|".join(parts)


def compare_baseline(current: Counter[str], baseline: Counter[str], tool: str) -> None:
    added = current - baseline
    stale = baseline - current
    if added or stale:
        details = []
        if added:
            details.append(f"new/increased={dict(sorted(added.items()))}")
        if stale:
            details.append(f"stale/decreased={dict(sorted(stale.items()))}")
        raise QualityFailure(f"{tool} baseline mismatch: {'; '.join(details)}")


def load_baseline(tool: str) -> Counter[str]:
    path = BASELINES / f"{tool}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Counter({item["fingerprint"]: item["count"] for item in data["findings"]})


def baseline_payload(tool: str, findings: Counter[str]) -> str:
    data = {
        "schema_version": 1,
        "tool": tool,
        "findings": [{"fingerprint": key, "count": findings[key]} for key in sorted(findings)],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "apps" / "api") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if check and result.returncode:
        raise QualityFailure(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result


def ruff_findings() -> Counter[str]:
    result = run([sys.executable, "-m", "ruff", "check", "apps/api/app", "apps/api/tests", "--output-format", "json"])
    if result.returncode not in {0, 1}:
        raise QualityFailure(result.stderr or result.stdout)
    findings = Counter()
    for item in json.loads(result.stdout or "[]"):
        location = item.get("location", {})
        snippet = ""
        path = ROOT / item["filename"] if not Path(item["filename"]).is_absolute() else Path(item["filename"])
        try:
            snippet = path.read_text(encoding="utf-8").splitlines()[location.get("row", 1) - 1]
        except (OSError, IndexError):
            pass
        findings[fingerprint("ruff", item["filename"], item["code"], item["message"], snippet)] += 1
    return findings


MYPY_PATTERN = re.compile(r"^(.*?):\d+(?::\d+)?: error: (.*?)\s+\[([^]]+)]$")


def mypy_findings() -> Counter[str]:
    result = run([sys.executable, "-m", "mypy", "--config-file", "mypy.ini", "apps/api/app"])
    if result.returncode not in {0, 1}:
        raise QualityFailure(result.stderr or result.stdout)
    findings = Counter()
    for line in result.stdout.splitlines():
        match = MYPY_PATTERN.match(line)
        if match:
            findings[fingerprint("mypy", match.group(1), match.group(3), match.group(2))] += 1
    return findings


def radon_findings() -> Counter[str]:
    result = run([sys.executable, "-m", "radon", "cc", "apps/api/app", "-j"], check=True)
    findings = Counter()
    for path, blocks in json.loads(result.stdout).items():
        for block in blocks:
            if block["complexity"] > 10:
                key = fingerprint("radon", path, block["type"], block["name"])
                findings[f"{key}|complexity={block['complexity']}"] += 1
    return findings


def tracked_files() -> list[Path]:
    result = run(["git", "ls-files"], check=True)
    paths = []
    for item in result.stdout.splitlines():
        path = Path(item)
        if path.suffix.lower() not in SOURCE_EXTENSIONS or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        paths.append(ROOT / path)
    return paths


def unicode_violations(paths: Iterable[Path]) -> list[str]:
    violations = []
    for path in paths:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            violations.append(f"{normalize_path(path)}|INVALID_UTF8")
            continue
        for index, character in enumerate(text):
            code = ord(character)
            category = unicodedata.category(character)
            if code == 0xFEFF and index == 0:
                continue
            if (
                code in ZERO_WIDTH
                or unicodedata.bidirectional(character) in BIDI
                or (category == "Cc" and character not in "\n\r\t")
            ):
                violations.append(f"{normalize_path(path)}|U+{code:04X}")
    return sorted(violations)


def _assigned_names(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = []
        for item in targets:
            if isinstance(item, ast.Name):
                names.append(item.id)
    return names


def privacy_violations(root: Path = ROOT) -> list[str]:
    violations = []
    for relative in PERSISTENCE_FILES:
        path = root / relative
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _assigned_names(tree):
            if name.lower() in FORBIDDEN_FIELDS:
                violations.append(f"{relative}|forbidden-field|{name}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "dict"
                and relative != "apps/api/app/privacy/event_serializer.py"
            ):
                violations.append(f"{relative}|broad-dict")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "model_dump":
                owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                if relative.endswith("writer.py") and owner in {"item", "detection"}:
                    continue
                if relative.endswith("writer.py") and isinstance(node.func.value, ast.Attribute):
                    if node.func.value.attr in {"event", "idempotency"}:
                        continue
                if relative.endswith("event_serializer.py"):
                    violations.append(f"{relative}|unrestricted-model-dump")
    return sorted(set(violations))


def architecture_violations(root: Path = ROOT) -> list[str]:
    app = root / "apps" / "api" / "app"
    violations = []
    for path in app.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        relative = normalize_path(path)
        if any(name == "tests" or name.startswith("tests.") for name in imports):
            violations.append(f"{relative}|app-imports-tests")
        if "/domain/" in f"/{relative}" or "/ports/" in f"/{relative}":
            forbidden = (
                "fastapi",
                "sqlalchemy",
                "app.routes",
                "app.db",
                "app.models",
                "app.infrastructure",
                "app.runtime",
                "app.services",
            )
            for name in imports:
                if name.startswith(forbidden):
                    violations.append(f"{relative}|forbidden-import|{name}")
    return sorted(violations)


def validate_baseline_change(old_counts: Counter[str] | None, new_counts: Counter[str], name: str) -> None:
    if old_counts is None:
        return
    increase = new_counts - old_counts
    if increase:
        raise QualityFailure(f"baseline increase is forbidden for {name}: {dict(increase)}")


def verify_baseline_diff(base_ref: str) -> None:
    for path in sorted(BASELINES.glob("*.json")):
        relative = normalize_path(path)
        result = run(["git", "show", f"{base_ref}:{relative}"])
        if result.returncode != 0:
            validate_baseline_change(None, new_counts=Counter(), name=path.name)
            continue
        old = json.loads(result.stdout)
        new = json.loads(path.read_text(encoding="utf-8"))
        old_counts = Counter({item["fingerprint"]: item["count"] for item in old["findings"]})
        new_counts = Counter({item["fingerprint"]: item["count"] for item in new["findings"]})
        validate_baseline_change(old_counts, new_counts, path.name)
