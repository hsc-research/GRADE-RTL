#!/usr/bin/env python3
"""Compatibility entry point for a single design."""
from __future__ import annotations

import sys

from llm_rtl_eval.cli import main


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if "--design" not in arguments and "--all" not in arguments and "--list-designs" not in arguments:
        print("Usage: python main.py --design DESIGN [other options]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(arguments))
