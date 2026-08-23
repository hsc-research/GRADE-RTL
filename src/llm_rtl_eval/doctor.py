from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import sys

from .runner import load_designs
from .utils import ConfigurationError, executable_version


@dataclass(slots=True)
class Check:
    status: str
    label: str
    detail: str


def inspect_environment(
    root: Path,
    *,
    require_tools: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[Check], int]:
    root = root.resolve()
    checks: list[Check] = []
    errors = 0

    if sys.version_info >= (3, 10):
        checks.append(Check("PASS", "Python", sys.version.split()[0]))
    else:
        checks.append(Check("FAIL", "Python", "Python 3.10 or newer is required"))
        errors += 1

    try:
        designs = load_designs(root)
    except ConfigurationError as exc:
        checks.append(Check("FAIL", "Repository", str(exc)))
        errors += 1
        designs = {}
    else:
        checks.append(Check("PASS", "Repository", f"loaded {len(designs)} design(s)"))

    fixture_root = root / "fixtures" / "llm_outputs"
    if fixture_root.is_dir():
        missing = [name for name in designs if not (fixture_root / name).is_dir()]
        if missing:
            checks.append(Check("FAIL", "Fixture data", "missing: " + ", ".join(missing)))
            errors += 1
        else:
            checks.append(Check("PASS", "Fixture data", str(fixture_root.relative_to(root))))
    else:
        checks.append(Check("FAIL", "Fixture data", f"missing {fixture_root}"))
        errors += 1

    if provider is not None:
        provider_requirements: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
            "ollama": ((), ()),
            "openai": (("OPENAI_API_KEY",), ("OPENAI_MODEL",)),
            "deepseek": (("DEEPSEEK_API_KEY",), ("DEEPSEEK_MODEL",)),
            "anthropic": (("ANTHROPIC_API_KEY",), ("ANTHROPIC_MODEL",)),
            "gemini": (("GEMINI_API_KEY",), ("GEMINI_MODEL",)),
            "huggingface": (("HF_TOKEN", "HF_API_KEY"), ("HF_MODEL",)),
        }
        credentials, models = provider_requirements[provider]
        if credentials and not any(os.environ.get(name, "").strip() for name in credentials):
            checks.append(
                Check("FAIL", f"{provider} credential", "set " + " or ".join(credentials))
            )
            errors += 1
        elif credentials:
            checks.append(Check("PASS", f"{provider} credential", "configured"))
        selected_model = (model or "").strip()
        if not selected_model:
            selected_model = next(
                (
                    os.environ.get(name, "").strip()
                    for name in models
                    if os.environ.get(name, "").strip()
                ),
                "",
            )
        if provider == "ollama" and not selected_model:
            selected_model = os.environ.get("OLLAMA_MODEL", "deepseek-coder:6.7b").strip()
        if not selected_model:
            checks.append(
                Check("FAIL", f"{provider} model", "set " + " or ".join(models))
            )
            errors += 1
        else:
            checks.append(Check("PASS", f"{provider} model", selected_model))

    for tool, version_args in (("iverilog", ["-V"]), ("yosys", ["-V"])):
        path = shutil.which(tool)
        if path is None:
            status = "FAIL" if require_tools else "WARN"
            checks.append(Check(status, tool, "not found on PATH"))
            if require_tools:
                errors += 1
            continue
        version = executable_version(tool, version_args) or "version unavailable"
        lowered = f"{path} {version}".lower()
        if any(marker in lowered for marker in ("stub", "mock", "fake")):
            checks.append(Check("FAIL", tool, f"test stub detected: {path}"))
            errors += 1
        else:
            first_line = version.splitlines()[0] if version else "version unavailable"
            checks.append(Check("PASS", tool, f"{path} ({first_line})"))

    return checks, errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether a GRADE-RTL checkout is ready to run."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--require-tools",
        action="store_true",
        help="Fail if real Icarus Verilog or Yosys is unavailable.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "deepseek", "anthropic", "gemini", "huggingface"],
        help="Also check the selected live provider's model and credential variables.",
    )
    parser.add_argument(
        "--model",
        help="Exact live model identifier; overrides the provider's model environment variable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks, errors = inspect_environment(
        args.root,
        require_tools=args.require_tools,
        provider=args.provider,
        model=args.model,
    )
    print("GRADE-RTL environment check")
    for check in checks:
        print(f"  [{check.status}] {check.label}: {check.detail}")
    print()
    if errors:
        print(f"Environment is not ready ({errors} blocking issue(s)).")
        print("See README.md#installation and MODES.md.")
        return 1
    print("Environment is ready.")
    print("Fixture smoke: llm-rtl-eval --mode fixture --all --k 3 --run-id fixture-smoke")
    print("Mode guide:    llm-rtl-eval --describe-modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
