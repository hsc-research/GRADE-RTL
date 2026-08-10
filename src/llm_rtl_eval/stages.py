from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Iterable

from .models import DesignConfig, StageResult
from .parsing import (
    VerilogParseError,
    compare_interfaces,
    completeness_issues,
    detect_top_module,
    parse_interface,
)
from .utils import atomic_write_text, run_command


def reference_files(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() in {".v", ".sv"}:
        return [path]
    if path.is_dir():
        return sorted(
            [*path.rglob("*.v"), *path.rglob("*.sv")],
            key=lambda item: item.as_posix(),
        )
    return []


def _read_reference(files: Iterable[Path]) -> str:
    return "\n\n".join(path.read_text(encoding="utf-8") for path in files)


def _read_verilog_command(path: Path, language: str) -> str:
    quoted = json.dumps(str(path.resolve()))
    return f"read_verilog {'-sv ' if language == 'systemverilog' else ''}{quoted}"


def run_port_stage(
    candidate_path: Path,
    reference_path: Path,
    design: DesignConfig,
    attempt_dir: Path,
) -> StageResult:
    log_path = attempt_dir / "P_port_signature.json"
    try:
        candidate_text = candidate_path.read_text(encoding="utf-8")
        ref_files = reference_files(reference_path)
        if not ref_files:
            raise VerilogParseError(f"No reference RTL found under {reference_path}")
        reference_text = _read_reference(ref_files)
        candidate_top = detect_top_module(candidate_text, design.top_module)
        if candidate_top is None:
            raise VerilogParseError(
                f"Expected top module {design.top_module!r} was not generated"
            )
        reference_top = design.reference_top or design.top_module
        candidate_ports = parse_interface(candidate_text, candidate_top)
        reference_ports = parse_interface(reference_text, reference_top)
        issues = compare_interfaces(candidate_ports, reference_ports, design.port_aliases)
        payload = {
            "candidate_top": candidate_top,
            "reference_top": reference_top,
            "candidate_ports": {
                name: {
                    "direction": port.direction,
                    "width": port.width,
                    "signed": port.signed,
                }
                for name, port in candidate_ports.items()
            },
            "reference_ports": {
                name: {
                    "direction": port.direction,
                    "width": port.width,
                    "signed": port.signed,
                }
                for name, port in reference_ports.items()
            },
            "issues": issues,
        }
        atomic_write_text(log_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        if issues:
            return StageResult("P", "FAIL", "; ".join(issues), log_path.name, payload)
        return StageResult("P", "PASS", "Interface matches trusted reference", log_path.name, payload)
    except (OSError, VerilogParseError, ValueError) as exc:
        payload = {"issues": [str(exc)]}
        atomic_write_text(log_path, json.dumps(payload, indent=2) + "\n")
        return StageResult("P", "FAIL", str(exc), log_path.name, payload)


def run_compile_stage(
    candidate_path: Path,
    design: DesignConfig,
    attempt_dir: Path,
    *,
    timeout: float = 120.0,
) -> StageResult:
    log_path = attempt_dir / "C_iverilog.log"
    if shutil.which("iverilog") is None:
        message = "Icarus Verilog is not installed"
        atomic_write_text(log_path, message + "\n")
        return StageResult("C", "ERROR", message, log_path.name)
    wrapped = attempt_dir / "candidate_strict.v"
    text = candidate_path.read_text(encoding="utf-8")
    atomic_write_text(wrapped, "`default_nettype none\n" + text + "\n`default_nettype wire\n")
    generation = "-g2012" if design.language == "systemverilog" else "-g2005"
    argv = [
        "iverilog",
        generation,
        "-tnull",
        "-Wall",
        "-Wimplicit",
        "-s",
        design.top_module,
        str(wrapped),
    ]
    try:
        returncode, output = run_command(argv, cwd=attempt_dir, timeout=timeout)
    except Exception as exc:  # subprocess timeout or OS-level failure
        output = f"{type(exc).__name__}: {exc}\n"
        returncode = 1
    atomic_write_text(log_path, "$ " + " ".join(argv) + "\n\n" + output)
    if returncode != 0:
        return StageResult("C", "FAIL", "Icarus Verilog compilation failed", log_path.name)
    return StageResult("C", "PASS", "Verilog compilation succeeded", log_path.name)


def run_elaboration_stage(
    candidate_path: Path,
    design: DesignConfig,
    attempt_dir: Path,
    *,
    timeout: float = 120.0,
) -> StageResult:
    script_path = attempt_dir / "E_elaboration.ys"
    log_path = attempt_dir / "E_yosys.log"
    if shutil.which("yosys") is None:
        message = "Yosys is not installed"
        atomic_write_text(log_path, message + "\n")
        return StageResult("E", "ERROR", message, log_path.name)
    script = "\n".join(
        [
            _read_verilog_command(candidate_path, design.language),
            f"hierarchy -check -top {design.top_module}",
            "stat",
        ]
    ) + "\n"
    atomic_write_text(script_path, script)
    try:
        returncode, output = run_command(
            ["yosys", "-Q", "-s", str(script_path)], cwd=attempt_dir, timeout=timeout
        )
    except Exception as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        returncode = 1
    atomic_write_text(log_path, output)
    if returncode != 0 or re.search(r"\bERROR:\b", output):
        return StageResult("E", "FAIL", "Yosys elaboration failed", log_path.name)
    return StageResult("E", "PASS", "Hierarchy and parameters resolved", log_path.name)


def run_completeness_stage(
    candidate_path: Path,
    design: DesignConfig,
    attempt_dir: Path,
    *,
    timeout: float = 120.0,
) -> StageResult:
    static_log = attempt_dir / "M_static.json"
    yosys_script = attempt_dir / "M_completeness.ys"
    yosys_log = attempt_dir / "M_yosys.log"
    text = candidate_path.read_text(encoding="utf-8")
    issues = completeness_issues(
        text,
        design.top_module,
        require_case_default=design.require_case_default,
    )
    atomic_write_text(static_log, json.dumps({"issues": issues}, indent=2) + "\n")
    if issues:
        return StageResult(
            "M",
            "FAIL",
            "; ".join(issues),
            static_log.name,
            {"static_issues": issues},
        )
    if shutil.which("yosys") is None:
        message = "Yosys is not installed"
        atomic_write_text(yosys_log, message + "\n")
        return StageResult("M", "ERROR", message, yosys_log.name)
    script = "\n".join(
        [
            _read_verilog_command(candidate_path, design.language),
            f"hierarchy -check -top {design.top_module}",
            "proc",
            "opt",
            "check -assert",
        ]
    ) + "\n"
    atomic_write_text(yosys_script, script)
    try:
        returncode, output = run_command(
            ["yosys", "-Q", "-s", str(yosys_script)], cwd=attempt_dir, timeout=timeout
        )
    except Exception as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        returncode = 1
    atomic_write_text(yosys_log, output)
    detected: list[str] = []
    lowered = output.lower()
    if "latch inferred" in lowered:
        detected.append("Yosys inferred a latch")
    if "multiple conflicting drivers" in lowered:
        detected.append("multiple conflicting drivers")
    if "has no driver" in lowered:
        detected.append("undriven signal")
    if returncode != 0 and not detected:
        detected.append("Yosys structural check failed")
    if detected:
        return StageResult(
            "M",
            "FAIL",
            "; ".join(detected),
            yosys_log.name,
            {"static_issues": [], "yosys_issues": detected},
        )
    return StageResult(
        "M",
        "PASS",
        "Static and Yosys completeness checks passed",
        yosys_log.name,
    )


def build_equivalence_script(
    candidate_path: Path,
    reference_paths: list[Path],
    design: DesignConfig,
    *,
    induction_depth: int = 10,
) -> str:
    ref_top = design.reference_top or design.top_module
    lines: list[str] = ["# Trusted reference (gold)"]
    lines.extend(_read_verilog_command(path, design.language) for path in reference_paths)
    lines.extend(
        [
            f"hierarchy -check -top {ref_top}",
            "proc",
            "memory",
            "flatten",
            "opt",
            f"rename {ref_top} gold",
            "design -stash gold_design",
            "design -reset-vlog",
            "# Candidate implementation (gate)",
            _read_verilog_command(candidate_path, design.language),
            f"hierarchy -check -top {design.top_module}",
            "proc",
            "memory",
            "flatten",
            "opt",
            f"rename {design.top_module} gate",
            "design -stash gate_design",
            "design -copy-from gold_design -as gold gold",
            "design -copy-from gate_design -as gate gate",
            "equiv_make gold gate equiv",
            "hierarchy -top equiv",
            f"equiv_simple -seq {int(induction_depth)}",
            f"equiv_induct -seq {int(induction_depth)}",
            "equiv_status -assert",
        ]
    )
    return "\n".join(lines) + "\n"


def run_equivalence_stage(
    candidate_path: Path,
    reference_path: Path,
    design: DesignConfig,
    attempt_dir: Path,
    *,
    timeout: float = 300.0,
    induction_depth: int = 10,
) -> StageResult:
    script_path = attempt_dir / "F_equivalence.ys"
    log_path = attempt_dir / "F_yosys.log"
    if shutil.which("yosys") is None:
        message = "Yosys is not installed"
        atomic_write_text(log_path, message + "\n")
        return StageResult("F", "ERROR", message, log_path.name)
    refs = reference_files(reference_path)
    if not refs:
        message = f"No trusted reference RTL found under {reference_path}"
        atomic_write_text(log_path, message + "\n")
        return StageResult("F", "FAIL", message, log_path.name)
    script = build_equivalence_script(
        candidate_path,
        refs,
        design,
        induction_depth=induction_depth,
    )
    atomic_write_text(script_path, script)
    try:
        returncode, output = run_command(
            ["yosys", "-Q", "-s", str(script_path)], cwd=attempt_dir, timeout=timeout
        )
    except Exception as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        returncode = 1
    atomic_write_text(log_path, output)
    if returncode != 0:
        return StageResult(
            "F",
            "FAIL",
            "Reference equivalence was not proven",
            log_path.name,
            {"induction_depth": induction_depth, "inconclusive_counts_as_failure": True},
        )
    return StageResult(
        "F",
        "PASS",
        "Reference equivalence proven",
        log_path.name,
        {"induction_depth": induction_depth, "inconclusive_counts_as_failure": True},
    )


def skipped_stage(stage: str, reason: str) -> StageResult:
    return StageResult(stage, "SKIP", reason)  # type: ignore[arg-type]


def classify_root_cause(stage: str | None) -> str | None:
    return {
        "P": "compiler",
        "C": "compiler",
        "E": "not-elaborated",
        "M": "partial_module",
        "F": "functional_mismatch",
    }.get(stage)
