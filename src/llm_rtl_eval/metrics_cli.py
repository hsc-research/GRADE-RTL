from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import attempt_from_dict
from .runner import write_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recompute metrics from a completed run")
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--k", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = args.run_directory.resolve()
    attempts_path = run_dir / "attempts.json"
    data = json.loads(attempts_path.read_text(encoding="utf-8"))
    attempts = {
        design: [attempt_from_dict(item) for item in items]
        for design, items in data.items()
    }
    write_results(run_dir, attempts, k=args.k)
    print(f"Recomputed metrics in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
