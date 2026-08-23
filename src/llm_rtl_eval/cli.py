from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

from .providers import (
    FixtureProvider,
    GenerationSettings,
    Provider,
    ProviderError,
    ReplayProvider,
    create_provider,
)
from .runner import InfrastructureError, load_designs, run_experiment
from .utils import ConfigurationError, resolve_inside

LIVE_PROVIDERS = (
    "ollama",
    "openai",
    "deepseek",
    "anthropic",
    "gemini",
    "huggingface",
)

MODE_HELP = """\
GRADE-RTL execution modes

  fixture  Synthetic deterministic RTL used only for tests and CI.
           Never eligible for paper results.

  replay   Re-evaluates archived responses from a provenance-checked
           earlier live run. No LLM/API call is made.

  live     Calls an actual local or API-based LLM provider.

The response mode (fixture/replay/live) is independent of the EDA tools.
All CLI experiments require real Icarus Verilog and Yosys. Tests may use
short-lived tool stubs only for Python orchestration checks.

Examples:
  llm-rtl-eval --mode fixture --all --k 3 --run-id smoke

  llm-rtl-eval --mode live --provider openai --model MODEL \\
      --design half_adder --k 3 --run-id live-openai --paper-run

  llm-rtl-eval --mode replay --replay-source results/live-openai \\
      --design half_adder --k 3 --run-id replay-openai --paper-run
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-rtl-eval",
        description="Evaluate LLM-generated RTL through P/C/E/M/F stages.",
        epilog=(
            "Use --describe-modes for fixture, replay, and live examples. "
            "Legacy '--provider mock' is accepted as fixture mode."
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--config", type=Path, default=None, help="Alternative designs.json")
    parser.add_argument(
        "--mode",
        choices=["fixture", "replay", "live"],
        default=None,
        help="Response source. If omitted, inferred from --provider for compatibility.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["fixture", "mock", *LIVE_PROVIDERS],
        help="Provider used with --mode live; fixture/mock are legacy compatibility values.",
    )
    parser.add_argument("--model", default=None, help="Exact model identifier")
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=None,
        help="Synthetic fixture root; default: fixtures/llm_outputs",
    )
    parser.add_argument(
        "--replay-source",
        "--replay-run",
        "--responses-root",
        dest="replay_source",
        type=Path,
        default=None,
        help="Prior live/replay run or exported replay bundle",
    )
    parser.add_argument(
        "--paper-run",
        action="store_true",
        help="Mark a live/replay run as intended for paper data; rejected for fixtures/stubs.",
    )
    parser.add_argument("--describe-modes", action="store_true", help="Print mode guide and exit")
    parser.add_argument("--design", action="append", dest="designs", help="Design name; repeat as needed")
    parser.add_argument("--all", action="store_true", help="Run all configured designs")
    parser.add_argument("--list-designs", action="store_true")
    parser.add_argument("--k", type=int, default=3, help="Maximum total attempts per design")
    parser.add_argument("--run-id", default=None, help="Output subdirectory under results/")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--provider-timeout", type=float, default=300.0)
    parser.add_argument("--tool-timeout", type=float, default=120.0)
    parser.add_argument("--equivalence-timeout", type=float, default=300.0)
    parser.add_argument("--equiv-induction-depth", type=int, default=10)
    return parser


def resolve_mode_and_provider(
    mode: str | None, provider: str | None
) -> tuple[str, str]:
    """Resolve explicit mode/provider while preserving legacy commands."""
    if mode is None:
        if provider in {None, "fixture", "mock"}:
            return "fixture", "fixture"
        return "live", provider
    if mode == "fixture":
        if provider not in {None, "fixture", "mock"}:
            raise ConfigurationError("fixture mode does not call a live provider")
        return "fixture", "fixture"
    if mode == "replay":
        if provider not in {None, "fixture", "mock"}:
            raise ConfigurationError("replay mode does not use --provider")
        return "replay", "replay"
    if mode == "live":
        if provider not in LIVE_PROVIDERS:
            raise ConfigurationError(
                "live mode requires --provider " + ", ".join(LIVE_PROVIDERS)
            )
        return "live", provider
    raise ConfigurationError(f"Unsupported mode: {mode}")


def build_provider(
    *,
    root: Path,
    mode: str,
    provider_name: str | None,
    model: str | None,
    settings: GenerationSettings,
    fixture_dir: Path | None,
    replay_source: Path | None,
) -> Provider:
    if mode == "fixture":
        if provider_name not in {None, "fixture", "mock"}:
            raise ConfigurationError(
                f"--provider {provider_name!r} is incompatible with --mode fixture"
            )
        selected = fixture_dir or Path("fixtures/llm_outputs")
        fixture_root = resolve_inside(root, selected, must_exist=True)
        return FixtureProvider(fixture_root, settings)

    if mode == "replay":
        if provider_name not in {None, "replay"}:
            raise ConfigurationError("--provider is not used with --mode replay")
        if replay_source is None:
            raise ConfigurationError("--mode replay requires --replay-source PATH")
        source = replay_source if replay_source.is_absolute() else root / replay_source
        return ReplayProvider(source, settings, expected_model=model)

    if mode == "live":
        if provider_name in {None, "fixture", "mock"}:
            raise ConfigurationError(
                "--mode live requires --provider " + ", ".join(LIVE_PROVIDERS)
            )
        if replay_source is not None:
            raise ConfigurationError("--replay-source is valid only with --mode replay")
        if fixture_dir is not None:
            raise ConfigurationError("--fixture-dir is valid only with --mode fixture")
        return create_provider(provider_name, model, settings, repository_root=root)

    raise ConfigurationError(f"Unsupported mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.describe_modes:
        print(MODE_HELP)
        return 0
    root = args.root.resolve()
    try:
        designs = load_designs(root, args.config)
        if args.list_designs:
            for name, config in designs.items():
                print(f"{name}: {config.description or config.top_module}")
            return 0
        settings = GenerationSettings(
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
            seed=args.seed,
            timeout_seconds=args.provider_timeout,
        )
        implicit_fixture = args.mode is None and args.provider is None
        mode, resolved_provider = resolve_mode_and_provider(args.mode, args.provider)
        if implicit_fixture:
            print(
                "NOTE: no --mode was specified; using fixture mode "
                "(synthetic test RTL, never paper data).",
                file=sys.stderr,
            )
        provider = build_provider(
            root=root,
            mode=mode,
            provider_name=resolved_provider,
            model=args.model,
            settings=settings,
            fixture_dir=args.fixture_dir,
            replay_source=args.replay_source,
        )
        if mode == "replay" and isinstance(provider, ReplayProvider):
            source_budget = provider.source_manifest.get("refinement_budget")
            if isinstance(source_budget, int) and args.k > source_budget:
                raise ConfigurationError(
                    f"Requested K={args.k} exceeds replay source budget K={source_budget}. "
                    "Use the same or a smaller budget, or create a new live run."
                )
        if args.all:
            selected = list(designs)
        elif args.designs:
            selected = args.designs
        elif mode == "replay" and isinstance(provider, ReplayProvider):
            selected = [str(name) for name in provider.source_manifest.get("designs", [])]
            if not selected:
                raise ConfigurationError(
                    "Replay source manifest lists no designs; specify --design explicitly"
                )
        else:
            raise ConfigurationError(
                "Select at least one --design DESIGN or use --all. "
                "GRADE-RTL never starts live/provider calls implicitly."
            )
        run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        run_dir = run_experiment(
            root=root,
            provider=provider,
            designs=designs,
            design_names=selected,
            k=args.k,
            run_id=run_id,
            overwrite=args.overwrite,
            timeout_compile=args.tool_timeout,
            timeout_equivalence=args.equivalence_timeout,
            induction_depth=args.equiv_induction_depth,
            command_line=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            paper_run=args.paper_run,
        )
        print(f"Run complete: {run_dir}")
        print(f"Mode: {mode}")
        print(f"Metrics: {run_dir / 'metrics.txt'}")
        print(f"Provenance: {run_dir / 'run_manifest.json'}")
        print(f"Verify: llm-rtl-verify-run {run_dir}")
        if args.paper_run:
            print(f"Paper gate: llm-rtl-verify-run --require-paper-result {run_dir}")
        return 0
    except (
        ConfigurationError,
        InfrastructureError,
        ProviderError,
        FileNotFoundError,
        FileExistsError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, InfrastructureError):
            missing = [name for name in ("iverilog", "yosys") if shutil.which(name) is None]
            if missing:
                print(
                    "Install the missing EDA tools before evaluating RTL: " + ", ".join(missing),
                    file=sys.stderr,
                )
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
