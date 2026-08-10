from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable

DESIGN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
MODULE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*\Z")


class ConfigurationError(ValueError):
    """Raised for invalid user configuration."""


class ToolUnavailableError(RuntimeError):
    """Raised when a required external EDA tool is unavailable."""


def validate_design_slug(value: str) -> str:
    if not DESIGN_RE.fullmatch(value):
        raise ConfigurationError(
            f"Unsafe design name {value!r}; use letters, digits, '.', '_' or '-'"
        )
    return value


def validate_module_name(value: str) -> str:
    if not MODULE_RE.fullmatch(value):
        raise ConfigurationError(f"Invalid Verilog module name: {value!r}")
    return value


def resolve_inside(root: Path, value: str | Path, *, must_exist: bool = False) -> Path:
    root = root.resolve()
    candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(f"Path escapes repository root: {value}") from exc
    if must_exist and not candidate.exists():
        raise ConfigurationError(f"Required path does not exist: {candidate}")
    return candidate


def ensure_clean_directory(path: Path, *, overwrite: bool = False) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise ConfigurationError(f"Refusing to use symlink as output directory: {path}")
        if not path.is_dir():
            raise ConfigurationError(f"Output path exists and is not a directory: {path}")
        if any(path.iterdir()):
            if not overwrite:
                raise FileExistsError(
                    f"Output directory is not empty: {path}. Use --overwrite explicitly."
                )
            shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable_version(name: str, args: Iterable[str]) -> str | None:
    executable = shutil.which(name)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return f"{name} (version unavailable)"
    first_line = result.stdout.strip().splitlines()
    return first_line[0] if first_line else f"{name} (version unavailable)"


def run_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    if not argv or not isinstance(argv[0], str):
        raise ValueError("Command must be a non-empty argument list")
    effective_env = dict(os.environ)
    if env:
        effective_env.update(env)
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=effective_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout
