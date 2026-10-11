from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_checksums.py"


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    (tmp_path / "payload.txt").write_text("original\n", encoding="utf-8")
    return tmp_path


def invoke(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / SCRIPT.name), *args],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


def generated_receipt(root: Path) -> bytes:
    result = invoke(root)
    assert result.returncode == 0, result.stderr
    return (root / "SHA256SUMS").read_bytes()


def test_check_accepts_current_receipt_without_modification(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    result = invoke(release_tree, "--check")
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
    assert (release_tree / "SHA256SUMS").read_bytes() == original


def test_check_rejects_stale_content_without_repairing_receipt(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    (release_tree / "payload.txt").write_text("changed\n", encoding="utf-8")
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "checksum mismatch: payload.txt" in result.stderr
    assert (release_tree / "SHA256SUMS").read_bytes() == original


def test_check_rejects_new_file_missing_from_receipt(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    (release_tree / "new.txt").write_text("new\n", encoding="utf-8")
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "file missing from SHA256SUMS: new.txt" in result.stderr
    assert (release_tree / "SHA256SUMS").read_bytes() == original


def test_check_rejects_deleted_file(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    (release_tree / "payload.txt").unlink()
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "unexpected checksum entry: payload.txt" in result.stderr
    assert (release_tree / "SHA256SUMS").read_bytes() == original


def test_check_does_not_create_missing_receipt(release_tree: Path) -> None:
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "missing checksum manifest" in result.stderr
    assert not (release_tree / "SHA256SUMS").exists()


def test_check_rejects_invalid_and_duplicate_entries(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    manifest = release_tree / "SHA256SUMS"
    first_line = original.splitlines(keepends=True)[0]
    changed = original + first_line + b"not a checksum\n"
    manifest.write_bytes(changed)
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "duplicate checksum path:" in result.stderr
    assert "invalid SHA256SUMS line" in result.stderr
    assert manifest.read_bytes() == changed


def test_check_rejects_outside_entry_without_following_it(release_tree: Path) -> None:
    original = generated_receipt(release_tree)
    manifest = release_tree / "SHA256SUMS"
    changed = original + b"0" * 64 + b"  ../outside.txt\n"
    manifest.write_bytes(changed)
    result = invoke(release_tree, "--check")
    assert result.returncode == 1
    assert "unexpected checksum entry: ../outside.txt" in result.stderr
    assert manifest.read_bytes() == changed


def test_ci_never_regenerates_checksum_receipt() -> None:
    workflow = SCRIPT.parents[1] / ".github" / "workflows" / "tests.yml"
    text = workflow.read_text(encoding="utf-8")
    commands = [line.strip() for line in text.splitlines() if "python scripts/generate_checksums.py" in line]
    assert commands == ["run: python scripts/generate_checksums.py --check"]
