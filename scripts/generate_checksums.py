#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "results",
    "build",
    "dist",
}
EXCLUDED_NAMES = {"SHA256SUMS"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def repository_files(root: Path) -> list[Path]:
    """Return the release files covered by the checksum receipt."""
    paths = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in EXCLUDED_NAMES:
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        paths.append(path)
    return sorted(paths)


def current_checksums(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in repository_files(root)
    }


def check_checksums(root: Path) -> list[str]:
    """Check the existing receipt without creating or changing any file.

    Compute the expected file set from the repository, rather than opening paths
    supplied by a receipt. This also makes extra/path-traversal entries harmless.
    """
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        return ["missing checksum manifest: SHA256SUMS"]
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"cannot read SHA256SUMS: {type(exc).__name__}"]
    errors: list[str] = []
    recorded: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            errors.append(f"invalid SHA256SUMS line {number}")
            continue
        value, relative = match.groups()
        if relative in recorded:
            errors.append(f"duplicate checksum path: {relative}")
        recorded[relative] = value
    expected = current_checksums(root)
    for relative in sorted(expected.keys() - recorded.keys()):
        errors.append(f"file missing from SHA256SUMS: {relative}")
    for relative in sorted(recorded.keys() - expected.keys()):
        errors.append(f"unexpected checksum entry: {relative}")
    for relative in sorted(expected.keys() & recorded.keys()):
        if expected[relative] != recorded[relative]:
            errors.append(f"checksum mismatch: {relative}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check release checksums")
    parser.add_argument(
        "--check", action="store_true",
        help="Verify the existing SHA256SUMS without rewriting it",
    )
    args = parser.parse_args(argv)
    if args.check:
        errors = check_checksums(ROOT)
        if errors:
            for error in errors:
                print(f"FAIL: {error}", file=sys.stderr)
            return 1
        print("Committed checksums: PASS")
        return 0
    values = current_checksums(ROOT)
    lines = [f"{value}  {relative}" for relative, value in values.items()]
    (ROOT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} checksums to {ROOT / 'SHA256SUMS'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
