#!/usr/bin/env python3
"""Compatibility entry point for metric recomputation."""
from __future__ import annotations

from pathlib import Path
import sys

# Allow direct execution from an unpacked source tree before installation.
_SOURCE = Path(__file__).resolve().parent / "src"
if _SOURCE.is_dir() and str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))

from llm_rtl_eval.metrics_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
