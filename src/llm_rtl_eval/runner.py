from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
from typing import Any

from .metrics import DesignSummary, aggregate_metrics, summarize_design
from .models import AttemptResult, DesignConfig, StageResult, STAGE_ORDER
from .parsing import extract_modules
from .providers import GenerationResponse, Provider
from .stages import (
    classify_root_cause,
    run_compile_stage,
    run_completeness_stage,
    run_elaboration_stage,
    run_equivalence_stage,
    run_port_stage,
    skipped_stage,
)
from .utils import (
    ConfigurationError,
    atomic_write_json,
    atomic_write_text,
    ensure_clean_directory,
    executable_version,
    resolve_inside,
    sha256_file,
    validate_design_slug,
    validate_module_name,
)


class InfrastructureError(RuntimeError):
    """Raised when the evaluation infrastructure, rather than RTL, fails."""


def load_designs(root: Path, path: Path | None = None) -> dict[str, DesignConfig]:
    config_path = path or root / "designs.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"Could not read design configuration: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {config_path}: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise ConfigurationError("designs.json must contain at least one design")
    result: dict[str, DesignConfig] = {}
    for name, value in raw.items():
        validate_design_slug(name)
        config = DesignConfig.from_mapping(name, value)
        if config.language not in {"verilog", "systemverilog"}:
            raise ConfigurationError(f"Unsupported language for {name}: {config.language}")
        validate_module_name(config.top_module)
        if config.reference_top is not None:
            validate_module_name(config.reference_top)
        for candidate_name, reference_name in config.port_aliases.items():
            validate_module_name(str(candidate_name))
            validate_module_name(str(reference_name))
        resolve_inside(root, config.prompt, must_exist=True)
        resolve_inside(root, config.reference, must_exist=True)
        result[name] = config
    return result


def _failure_message(stage: StageResult) -> str:
    message = stage.message.strip().replace("\x00", "")
    return message[:1200] if message else f"{stage.stage}-stage failed"


def build_refined_prompt(
    base_prompt: str,
    feedback_history: list[tuple[str, str]],
) -> str:
    if not feedback_history:
        return base_prompt.rstrip() + "\n"
    blocks = [base_prompt.rstrip(), "", "[TOOL-GUIDED SPECIFICATION CLARIFICATIONS]"]
    for index, (stage, message) in enumerate(feedback_history, start=1):
        blocks.extend(
            [
                f"Round {index}: first failing stage = {stage}",
                f"Diagnostic: {message}",
            ]
        )
    stage = feedback_history[-1][0]
    hints = {
        "P": "Match the required top-module name, port names, directions, widths, and signedness exactly.",
        "C": "Return legal synthesizable RTL with declared signals and no implicit nets.",
        "E": "Resolve every instantiated module, parameter, generate block, and hierarchy binding.",
        "M": "Complete every required logic branch and drive every top-level output; do not use stubs or placeholders.",
        "F": "Preserve the specified cycle-visible behavior, reset convention, and latency at the module boundary.",
    }
    blocks.extend(
        [
            "",
            hints.get(stage, "Correct the earliest reported failure without changing the requested interface."),
            "Do not change the target functionality. Output only the complete RTL implementation.",
        ]
    )
    return "\n".join(blocks).rstrip() + "\n"


def _attempt_metadata(
    response: GenerationResponse,
    *,
    prompt_path: Path,
    raw_path: Path,
    rtl_path: Path | None,
    tool_versions: dict[str, str | None],
) -> dict[str, Any]:
    data = dict(response.metadata)
    data.update(
        {
            "prompt_sha256": sha256_file(prompt_path),
            "raw_response_sha256": sha256_file(raw_path),
            "rtl_sha256": sha256_file(rtl_path) if rtl_path and rtl_path.is_file() else None,
            "tool_versions": tool_versions,
        }
    )
    return data


def _first_failure(stages: dict[str, StageResult]) -> tuple[str | None, str | None]:
    for stage in STAGE_ORDER:
        result = stages.get(stage)
        if result is None or result.status != "PASS":
            return stage, classify_root_cause(stage)
    return None, None


def evaluate_attempt(
    *,
    root: Path,
    run_dir: Path,
    design: DesignConfig,
    provider: Provider,
    attempt: int,
    prompt_text: str,
    tool_versions: dict[str, str | None],
    timeout_compile: float = 120.0,
    timeout_equivalence: float = 300.0,
    induction_depth: int = 10,
) -> AttemptResult:
    attempt_dir = run_dir / design.name / f"attempt_{attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    prompt_path = attempt_dir / "prompt.txt"
    raw_path = attempt_dir / "raw_response.txt"
    candidate_path = attempt_dir / "candidate.v"
    metadata_path = attempt_dir / "generation_metadata.json"
    atomic_write_text(prompt_path, prompt_text)

    start = time.monotonic()
    response = provider.generate(prompt_text, design=design.name, attempt=attempt)
    atomic_write_text(raw_path, response.text)
    rtl = extract_modules(response.text)
    stages: dict[str, StageResult] = {}
    reference_path = resolve_inside(root, design.reference, must_exist=True)

    if rtl is None:
        stages["P"] = StageResult("P", "FAIL", "No complete Verilog module was found")
        for stage in STAGE_ORDER[1:]:
            stages[stage] = skipped_stage(stage, "Skipped after P-stage failure")
        candidate: Path | None = None
    else:
        atomic_write_text(candidate_path, rtl)
        candidate = candidate_path
        stages["P"] = run_port_stage(candidate_path, reference_path, design, attempt_dir)
        if stages["P"].status == "ERROR":
            raise InfrastructureError(stages["P"].message)
        if stages["P"].passed:
            stages["C"] = run_compile_stage(
                candidate_path, design, attempt_dir, timeout=timeout_compile
            )
            if stages["C"].status == "ERROR":
                raise InfrastructureError(stages["C"].message)
        else:
            stages["C"] = skipped_stage("C", "Skipped after P-stage failure")
        if stages["C"].passed:
            stages["E"] = run_elaboration_stage(
                candidate_path, design, attempt_dir, timeout=timeout_compile
            )
            if stages["E"].status == "ERROR":
                raise InfrastructureError(stages["E"].message)
        else:
            stages["E"] = skipped_stage("E", "Skipped after earlier failure")
        if stages["E"].passed:
            stages["M"] = run_completeness_stage(
                candidate_path, design, attempt_dir, timeout=timeout_compile
            )
            if stages["M"].status == "ERROR":
                raise InfrastructureError(stages["M"].message)
        else:
            stages["M"] = skipped_stage("M", "Skipped after earlier failure")
        if stages["M"].passed:
            stages["F"] = run_equivalence_stage(
                candidate_path,
                reference_path,
                design,
                attempt_dir,
                timeout=timeout_equivalence,
                induction_depth=induction_depth,
            )
            if stages["F"].status == "ERROR":
                raise InfrastructureError(stages["F"].message)
        else:
            stages["F"] = skipped_stage("F", "Skipped after earlier failure")

    elapsed = time.monotonic() - start
    first_failure, root_cause = _first_failure(stages)
    metadata = _attempt_metadata(
        response,
        prompt_path=prompt_path,
        raw_path=raw_path,
        rtl_path=candidate,
        tool_versions=tool_versions,
    )
    atomic_write_json(metadata_path, metadata)
    result = AttemptResult(
        design=design.name,
        attempt=attempt,
        provider=provider.name,
        model=provider.model,
        elapsed_seconds=elapsed,
        stages=stages,
        first_failure=first_failure,
        root_cause=root_cause,
        prompt_path=prompt_path.relative_to(run_dir).as_posix(),
        raw_response_path=raw_path.relative_to(run_dir).as_posix(),
        rtl_path=candidate.relative_to(run_dir).as_posix() if candidate else None,
        metadata_path=metadata_path.relative_to(run_dir).as_posix(),
    )
    atomic_write_json(attempt_dir / "attempt_result.json", result.to_dict())
    return result


def _run_manifest(
    *,
    provider: Provider,
    k: int,
    design_names: list[str],
    tool_versions: dict[str, str | None],
    command_line: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider.name,
        "model": provider.model,
        "refinement_budget": k,
        "designs": design_names,
        "python": sys.version,
        "platform": platform.platform(),
        "tool_versions": tool_versions,
        "command_line": command_line,
        "environment_recorded_without_secrets": True,
    }


def write_results(
    run_dir: Path,
    attempts_by_design: dict[str, list[AttemptResult]],
    *,
    k: int,
) -> tuple[list[DesignSummary], dict[str, Any]]:
    summaries = [
        summarize_design(attempts_by_design[name], k=k)
        for name in sorted(attempts_by_design)
    ]
    fieldnames = [
        "design",
        "attempts",
        "selected_attempt",
        "selected_depth",
        *STAGE_ORDER,
        "E2E@1",
        f"E2E@{k}",
        f"SEY@{k}",
        "A_i",
        "ETS",
        "TTFP_seconds",
        "First_Failure",
        "Root_Cause",
    ]
    with (run_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(summary.to_row(k))
    metrics = aggregate_metrics(summaries)
    metrics_dict = metrics.to_dict()
    metrics_dict["k"] = k
    atomic_write_json(run_dir / "metrics.json", metrics_dict)
    lines = [
        f"Designs: {metrics.designs}",
        f"E2E@1: {metrics.e2e_at_1:.4f}",
        f"E2E@{k}: {metrics.e2e_at_k:.4f}",
        f"SEY@{k}: {metrics.sey_at_k:.4f}",
        f"ETS: {metrics.ets if metrics.ets is not None else 'N/A'}",
        f"TTFP seconds: {metrics.ttfp_seconds if metrics.ttfp_seconds is not None else 'N/A'}",
        "Stage rates: " + ", ".join(f"{key}={value:.4f}" for key, value in metrics.stage_rates.items()),
        "Conditional yields: "
        + ", ".join(f"{key}={value:.4f}" for key, value in metrics.conditional_yields.items()),
        "First-failure shares: "
        + ", ".join(f"{key}={value:.4f}" for key, value in metrics.first_failure_shares.items()),
        "Root-cause shares: "
        + ", ".join(f"{key}={value:.4f}" for key, value in metrics.root_cause_shares.items()),
    ]
    atomic_write_text(run_dir / "metrics.txt", "\n".join(lines) + "\n")
    atomic_write_json(
        run_dir / "attempts.json",
        {
            name: [attempt.to_dict() for attempt in attempts]
            for name, attempts in attempts_by_design.items()
        },
    )
    return summaries, metrics_dict


def run_experiment(
    *,
    root: Path,
    provider: Provider,
    designs: dict[str, DesignConfig],
    design_names: list[str],
    k: int,
    run_id: str,
    overwrite: bool = False,
    timeout_compile: float = 120.0,
    timeout_equivalence: float = 300.0,
    induction_depth: int = 10,
    command_line: list[str] | None = None,
) -> Path:
    if k < 1 or k > 100:
        raise ConfigurationError("K must be between 1 and 100")
    validate_design_slug(run_id)
    if not design_names:
        raise ConfigurationError("At least one design must be selected")
    if len(design_names) != len(set(design_names)):
        raise ConfigurationError("Duplicate designs are not permitted in one run")
    unknown = [name for name in design_names if name not in designs]
    if unknown:
        raise ConfigurationError("Unknown designs: " + ", ".join(unknown))
    results_root = resolve_inside(root, "results")
    run_dir = resolve_inside(root, Path("results") / run_id)
    # Validate prompts and tool availability before creating any run output or
    # making a potentially billable provider request.
    for design_name in design_names:
        prompt_path = resolve_inside(root, designs[design_name].prompt, must_exist=True)
        if not prompt_path.is_file() or not prompt_path.read_text(encoding="utf-8").strip():
            raise ConfigurationError(f"Prompt is missing or empty: {prompt_path}")
    missing_tools = [name for name in ("iverilog", "yosys") if shutil.which(name) is None]
    if missing_tools:
        raise InfrastructureError(
            "Required EDA tools are unavailable: " + ", ".join(missing_tools)
        )
    results_root.mkdir(parents=True, exist_ok=True)
    ensure_clean_directory(run_dir, overwrite=overwrite)
    tool_versions = {
        "iverilog": executable_version("iverilog", ["-V"]),
        "yosys": executable_version("yosys", ["-V"]),
    }
    atomic_write_json(
        run_dir / "run_manifest.json",
        _run_manifest(
            provider=provider,
            k=k,
            design_names=design_names,
            tool_versions=tool_versions,
            command_line=command_line or sys.argv,
        ),
    )
    attempts_by_design: dict[str, list[AttemptResult]] = {}
    for design_name in design_names:
        design = designs[design_name]
        prompt_path = resolve_inside(root, design.prompt, must_exist=True)
        base_prompt = prompt_path.read_text(encoding="utf-8")
        if not base_prompt.strip():
            raise ConfigurationError(f"Prompt is empty: {prompt_path}")
        feedback: list[tuple[str, str]] = []
        attempts: list[AttemptResult] = []
        for attempt_number in range(1, k + 1):
            prompt = build_refined_prompt(base_prompt, feedback)
            result = evaluate_attempt(
                root=root,
                run_dir=run_dir,
                design=design,
                provider=provider,
                attempt=attempt_number,
                prompt_text=prompt,
                tool_versions=tool_versions,
                timeout_compile=timeout_compile,
                timeout_equivalence=timeout_equivalence,
                induction_depth=induction_depth,
            )
            attempts.append(result)
            if result.full_success:
                break
            if result.first_failure is None:
                raise RuntimeError(f"Attempt for {design_name} failed without a failure stage")
            failed_stage = result.stages[result.first_failure]
            feedback.append((result.first_failure, _failure_message(failed_stage)))
        attempts_by_design[design_name] = attempts
    write_results(run_dir, attempts_by_design, k=k)
    return run_dir
