#!/usr/bin/env python3
"""Verify repository hygiene, tests, aggregate data, and optional HDL smoke runs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "results", "build", "dist"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".yml", ".yaml", ".cff", ".toml", ".tcl", ".v", ".sv", ".example"}

REQUIRED_FILES = [
    "README.md",
    "ARTIFACT_STATUS.md",
    "PUBLIC_RELEASE_CHECKLIST.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "LICENSE",
    "THIRD_PARTY_LICENSES.md",
    ".env.example",
    ".gitignore",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-lock.txt",
    "designs.json",
    "main.py",
    "run_all.py",
    "metrics.py",
    "paper_artifact_manifest.json",
    "VERIFICATION_REPORT.md",
    "paper_results/coverage_within_k.csv",
    "paper_results/aggregate_metrics.json",
    "paper_results/recompute_aggregate_metrics.py",
    "scripts/generate_checksums.py",
    "scripts/synthesize.py",
    "synthesis/genus_template.tcl",
    ".github/workflows/tests.yml",
]

SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("OpenAI-style token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "hardcoded password",
        re.compile(r"(?i)\b(?:password|passwd|ssh_pass)\s*=\s*['\"][^'\"]{3,}['\"]"),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tools", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--public-release", action="store_true")
    return parser.parse_args()


def run(argv: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def text_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore"}:
            yield path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")


def verify_python_syntax(errors: list[str]) -> None:
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"Python syntax error in {path.relative_to(ROOT)}: {exc}")


def verify_design_assets(errors: list[str]) -> None:
    try:
        designs = json.loads((ROOT / "designs.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot parse designs.json: {exc}")
        return
    if not isinstance(designs, dict) or not designs:
        errors.append("designs.json must contain at least one design")
        return
    for name, config in designs.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            errors.append(f"unsafe design name: {name!r}")
            continue
        if not isinstance(config, dict):
            errors.append(f"design {name} must map to an object")
            continue
        prompt = ROOT / str(config.get("prompt", f"prompts/{name}.txt"))
        reference = ROOT / str(config.get("reference", f"reference/{name}"))
        mock = ROOT / "mock_responses" / name
        for label, path in (("prompt", prompt), ("reference", reference), ("mock response", mock)):
            try:
                path.resolve().relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{label} path escapes repository for {name}: {path}")
                continue
            if not path.exists():
                errors.append(f"missing {label} for {name}: {path.relative_to(ROOT)}")
        if prompt.is_file() and not prompt.read_text(encoding="utf-8").strip():
            errors.append(f"empty prompt for {name}")
        if reference.exists():
            files = [reference] if reference.is_file() else [*reference.rglob("*.v"), *reference.rglob("*.sv")]
            if not files:
                errors.append(f"no Verilog reference files for {name}")
        if mock.exists() and not list(mock.glob("*.v")):
            errors.append(f"no Verilog mock responses for {name}")


def verify_secrets(errors: list[str]) -> None:
    verifier = Path(__file__).resolve()
    for path in text_files():
        if path.resolve() == verifier:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"potential {label} in {path.relative_to(ROOT)}")


def verify_unsafe_code(errors: list[str]) -> None:
    patterns = [
        ("shell=True", re.compile(r"\bshell\s*=\s*True\b")),
        ("os.system", re.compile(r"\bos\.system\s*\(")),
        ("sshpass", re.compile(r"\bsshpass\b", re.I)),
        ("disabled SSH host verification", re.compile(r"StrictHostKeyChecking=(?:no|accept-new)", re.I)),
        ("disabled TLS verification", re.compile(r"\bverify\s*=\s*False\b")),
    ]
    verifier = Path(__file__).resolve()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.resolve() == verifier:
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS | {"tests"} for part in relative.parts):
            continue
        if path.suffix.lower() not in {".py", ".yml", ".yaml", ".tcl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in patterns:
            if pattern.search(text):
                errors.append(f"unsafe code pattern ({label}) in {relative}")


def verify_clean_tree(errors: list[str]) -> None:
    for forbidden in (
        "results",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
    ):
        for path in ROOT.rglob(forbidden):
            if path.exists():
                errors.append(
                    f"generated/cache directory should not be released: {path.relative_to(ROOT)}"
                )
    for path in ROOT.rglob("*.egg-info"):
        if path.exists():
            errors.append(
                f"generated package metadata should not be released: {path.relative_to(ROOT)}"
            )
    for path in ROOT.rglob("*.pyc"):
        errors.append(f"compiled Python file should not be released: {path.relative_to(ROOT)}")


def cleanup_caches() -> None:
    for path in sorted(ROOT.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and path.name in {"__pycache__", ".pytest_cache", ".ruff_cache"}:
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix == ".pyc":
            path.unlink(missing_ok=True)


def verify_tests(errors: list[str]) -> None:
    result = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    if result.returncode != 0:
        errors.append("pytest failed:\n" + result.stdout)
    cleanup_caches()


def verify_paper_metrics(errors: list[str]) -> None:
    temp = ROOT / "paper_results" / ".aggregate_metrics.verify.json"
    result = run(
        [
            sys.executable,
            "paper_results/recompute_aggregate_metrics.py",
            "--output",
            str(temp),
        ]
    )
    try:
        if result.returncode != 0:
            errors.append("paper metric recomputation failed:\n" + result.stdout)
            return
        expected = json.loads((ROOT / "paper_results/aggregate_metrics.json").read_text(encoding="utf-8"))
        actual = json.loads(temp.read_text(encoding="utf-8"))
        if expected != actual:
            errors.append("paper_results/aggregate_metrics.json is stale or inconsistent")
    finally:
        temp.unlink(missing_ok=True)


def verify_tools(require: bool, errors: list[str], warnings: list[str]) -> None:
    for name in ("iverilog", "yosys"):
        if shutil.which(name) is None:
            message = f"{name} is not installed; real-tool execution was not verified"
            (errors if require else warnings).append(message)


def verify_smoke(errors: list[str]) -> None:
    run_id = "verification-smoke"
    run_root = ROOT / "results" / run_id
    if run_root.exists():
        shutil.rmtree(run_root)
    result = run(
        [
            sys.executable,
            "run_all.py",
            "--provider",
            "mock",
            "--all",
            "--k",
            "3",
            "--run-id",
            run_id,
            "--overwrite",
        ]
    )
    try:
        if result.returncode != 0:
            errors.append("real-tool smoke run failed:\n" + result.stdout)
            return
        metrics = json.loads((run_root / "metrics.json").read_text(encoding="utf-8"))
        if abs(metrics["e2e_at_1"] - 2 / 3) > 1e-9:
            errors.append("smoke E2E@1 is not 2/3")
        if metrics["e2e_at_k"] != 1.0 or metrics["sey_at_k"] != 1.0:
            errors.append("smoke E2E@3 and SEY@3 must both be 1.0")
    finally:
        shutil.rmtree(ROOT / "results", ignore_errors=True)
        cleanup_caches()


def verify_citation(errors: list[str]) -> None:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8", errors="ignore")
    for field in ("cff-version:", "title:", "type:", "version:", "authors:", "license:"):
        if field not in text:
            errors.append(f"CITATION.cff is missing {field.rstrip(':')}")


def verify_checksums(errors: list[str]) -> None:
    path = ROOT / "SHA256SUMS"
    if not path.is_file():
        errors.append("public release requires SHA256SUMS")
        return
    seen = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            errors.append(f"invalid SHA256SUMS line {number}: {line!r}")
            continue
        digest, relative = match.groups()
        if relative in seen:
            errors.append(f"duplicate checksum path: {relative}")
            continue
        seen.add(relative)
        target = (ROOT / relative).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"checksum path escapes repository: {relative}")
            continue
        if not target.is_file():
            errors.append(f"checksum path is missing: {relative}")
        elif sha256(target) != digest:
            errors.append(f"checksum mismatch: {relative}")
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS"
        and not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    }
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    for relative in missing:
        errors.append(f"file missing from SHA256SUMS: {relative}")
    for relative in extra:
        errors.append(f"unexpected checksum entry: {relative}")


def verify_public_release(errors: list[str]) -> None:
    for relative in ("LICENSE", "THIRD_PARTY_LICENSES.md", "paper_artifact_manifest.json", "ARTIFACT_STATUS.md"):
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size < 100:
            errors.append(f"public release requires a substantive {relative}")
    try:
        manifest = json.loads((ROOT / "paper_artifact_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            errors.append("paper_artifact_manifest.json must use schema_version 1")
        if manifest.get("release_type") != "framework-and-aggregate-results":
            errors.append("unexpected release_type in paper_artifact_manifest.json")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid paper_artifact_manifest.json: {exc}")
    verify_checksums(errors)


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    verify_required_files(errors)
    verify_python_syntax(errors)
    verify_design_assets(errors)
    verify_secrets(errors)
    verify_unsafe_code(errors)
    verify_clean_tree(errors)
    verify_citation(errors)
    verify_tests(errors)
    verify_paper_metrics(errors)
    verify_tools(args.require_tools or args.smoke, errors, warnings)
    if args.smoke and not any("not installed" in item for item in errors):
        verify_smoke(errors)
    if args.public_release:
        verify_public_release(errors)
    print("Repository verification")
    print("=======================")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1
    print(f"PASS ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
