from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

from .providers import GenerationSettings, ProviderError, create_provider
from .runner import InfrastructureError, load_designs, run_experiment
from .utils import ConfigurationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-rtl-eval",
        description="Evaluate LLM-generated RTL through P/C/E/M/F stages.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--config", type=Path, default=None, help="Alternative designs.json")
    parser.add_argument(
        "--provider",
        default="mock",
        choices=["mock", "ollama", "openai", "deepseek", "anthropic", "gemini", "huggingface"],
    )
    parser.add_argument("--model", default=None, help="Exact model identifier")
    parser.add_argument("--design", action="append", dest="designs", help="Design name; repeat as needed")
    parser.add_argument("--all", action="store_true", help="Run all configured designs")
    parser.add_argument("--list-designs", action="store_true")
    parser.add_argument("--k", type=int, default=3, help="Maximum attempts per design")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        designs = load_designs(root, args.config)
        if args.list_designs:
            for name, config in designs.items():
                print(f"{name}: {config.description or config.top_module}")
            return 0
        if args.all:
            selected = list(designs)
        elif args.designs:
            selected = args.designs
        else:
            selected = list(designs)
        settings = GenerationSettings(
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
            seed=args.seed,
            timeout_seconds=args.provider_timeout,
        )
        provider = create_provider(args.provider, args.model, settings, repository_root=root)
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
        )
        print(f"Run complete: {run_dir}")
        print(f"Metrics: {run_dir / 'metrics.txt'}")
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
