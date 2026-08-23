#!/usr/bin/env python3
"""Compatibility entry point for a single design."""
from __future__ import annotations

from pathlib import Path
import sys

# Allow direct execution from an unpacked source tree before installation.
_SOURCE = Path(__file__).resolve().parent / "src"
if _SOURCE.is_dir() and str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))

from llm_rtl_eval.cli import main


if __name__ == "__main__":
    arguments = sys.argv[1:]
    informational = {"--describe-modes", "--list-designs", "--help", "-h"}
    if (
        "--design" not in arguments
        and "--all" not in arguments
        and not informational.intersection(arguments)
    ):
        print(
            "Usage: python main.py --design DESIGN [other options]\n"
            "       python main.py --describe-modes",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main(arguments))
