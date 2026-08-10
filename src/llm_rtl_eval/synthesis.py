from __future__ import annotations

import json
from pathlib import Path
import shutil

from .utils import atomic_write_text, ensure_clean_directory, run_command, validate_module_name


def run_generic_yosys_synthesis(
    rtl: Path,
    *,
    top_module: str,
    output_dir: Path,
    language: str = "verilog",
    timeout: float = 300.0,
    overwrite: bool = False,
) -> dict[str, object]:
    """Run technology-independent Yosys synthesis.

    This helper is intentionally separate from the P/C/E/M/F front-end
    scorecard. It produces a generic netlist and Yosys statistics, not a
    foundry-quality ASIC report.
    """
    if shutil.which("yosys") is None:
        raise RuntimeError("Yosys is required for generic synthesis")
    validate_module_name(top_module)
    rtl = rtl.resolve()
    if not rtl.is_file() or rtl.suffix.lower() not in {".v", ".sv"}:
        raise ValueError(f"RTL input must be an existing .v or .sv file: {rtl}")
    output_dir = output_dir.resolve()
    if rtl == output_dir or output_dir in rtl.parents:
        raise ValueError("Output directory may not contain the RTL input")
    ensure_clean_directory(output_dir, overwrite=overwrite)
    script = output_dir / "synth.ys"
    log = output_dir / "synth.log"
    netlist = output_dir / "netlist.v"
    stat_json = output_dir / "stat.json"
    read = f'read_verilog {"-sv " if language == "systemverilog" else ""}{json.dumps(str(rtl.resolve()))}'
    script_text = "\n".join(
        [
            read,
            f"hierarchy -check -top {top_module}",
            f"synth -top {top_module}",
            f"tee -q -o {json.dumps(str(stat_json.resolve()))} stat -json",
            f"write_verilog -noattr {json.dumps(str(netlist.resolve()))}",
        ]
    ) + "\n"
    atomic_write_text(script, script_text)
    returncode, output = run_command(
        ["yosys", "-Q", "-s", str(script)], cwd=output_dir, timeout=timeout
    )
    atomic_write_text(log, output)
    if returncode != 0:
        raise RuntimeError(f"Yosys synthesis failed; see {log}")
    if not netlist.is_file() or not stat_json.is_file():
        raise RuntimeError(f"Yosys synthesis did not produce all expected outputs; see {log}")
    try:
        json.loads(stat_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Yosys statistics are not valid JSON; see {stat_json}") from exc
    return {
        "status": "PASS",
        "netlist": netlist.name,
        "statistics": stat_json.name,
        "log": log.name,
    }
