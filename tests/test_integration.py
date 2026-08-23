from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from llm_rtl_eval.providers import FixtureProvider, GenerationSettings
from llm_rtl_eval.runner import load_designs, run_experiment

ROOT = Path(__file__).resolve().parents[1]


def copy_smoke_assets(destination: Path) -> None:
    shutil.copy2(ROOT / "designs.json", destination / "designs.json")
    for directory in ("prompts", "reference"):
        shutil.copytree(ROOT / directory, destination / directory)
    target = destination / "fixtures" / "llm_outputs"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "fixtures" / "llm_outputs", target)


def create_tool_stubs(directory: Path) -> None:
    directory.mkdir()
    iverilog = directory / "iverilog"
    iverilog.write_text(
        "#!/bin/sh\nif [ \"$1\" = \"-V\" ]; then echo 'Icarus Verilog test stub 1.0'; fi\nexit 0\n",
        encoding="utf-8",
    )
    yosys = directory / "yosys"
    yosys.write_text(
        "#!/bin/sh\nif [ \"$1\" = \"-V\" ]; then echo 'Yosys test stub 1.0'; fi\nexit 0\n",
        encoding="utf-8",
    )
    iverilog.chmod(0o755)
    yosys.chmod(0o755)


def test_runner_orchestration_with_tool_stubs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy_smoke_assets(tmp_path)
    stub_bin = tmp_path / "tool-stubs"
    create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    designs = load_designs(tmp_path)
    provider = FixtureProvider(
        tmp_path / "fixtures" / "llm_outputs", GenerationSettings()
    )
    run_dir = run_experiment(
        root=tmp_path,
        provider=provider,
        designs=designs,
        design_names=list(designs),
        k=3,
        run_id="smoke",
    )
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    attempts = json.loads((run_dir / "attempts.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert metrics["e2e_at_1"] == pytest.approx(2 / 3)
    assert metrics["e2e_at_k"] == 1.0
    assert metrics["sey_at_k"] == 1.0
    assert len(attempts["priority_encoder"]) == 1
    assert len(attempts["ripple_carry_adder"]) == 1
    assert len(attempts["half_adder"]) == 2
    assert manifest["execution_mode"] == "fixture"
    assert manifest["response_origin"] == "synthetic_fixture"
    assert manifest["tool_mode"] == "stub"
    assert manifest["paper_result"] is False


@pytest.mark.integration
def test_fixture_smoke_with_real_iverilog_and_yosys(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("yosys") is None:
        pytest.skip("Icarus Verilog and Yosys are required")
    copy_smoke_assets(tmp_path)
    designs = load_designs(tmp_path)
    provider = FixtureProvider(
        tmp_path / "fixtures" / "llm_outputs", GenerationSettings()
    )
    run_dir = run_experiment(
        root=tmp_path,
        provider=provider,
        designs=designs,
        design_names=list(designs),
        k=3,
        run_id="real-tools",
    )
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    attempts = json.loads((run_dir / "attempts.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert metrics["e2e_at_1"] == pytest.approx(2 / 3)
    assert metrics["e2e_at_k"] == 1.0
    assert metrics["sey_at_k"] == 1.0
    assert len(attempts["priority_encoder"]) == 1
    assert len(attempts["ripple_carry_adder"]) == 1
    assert len(attempts["half_adder"]) == 2
    assert manifest["tool_mode"] == "real"
    assert manifest["paper_result_eligible"] is False
