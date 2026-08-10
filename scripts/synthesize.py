#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from llm_rtl_eval.synthesis import run_generic_yosys_synthesis


def main() -> int:
    parser = argparse.ArgumentParser(description="Run generic Yosys synthesis")
    parser.add_argument("rtl", type=Path)
    parser.add_argument("--top", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", choices=["verilog", "systemverilog"], default="verilog")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = run_generic_yosys_synthesis(
        args.rtl,
        top_module=args.top,
        output_dir=args.output,
        language=args.language,
        overwrite=args.overwrite,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
