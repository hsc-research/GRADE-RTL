from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from llm_rtl_eval.providers import GenerationSettings, MockProvider
from llm_rtl_eval.runner import load_designs, run_experiment

ROOT = Path(__file__).resolve().parents[1]


def copy_smoke_assets(destination: Path) -> None:
    for name in ("designs.json",):
        shutil.copy2(ROOT / name, destination / name)
    for directory in ("prompts", "reference", "mock_responses"):
        shutil.copytree(ROOT / directory, destination / directory)


def create_fake_tools(directory: Path) -> None:
    directory.mkdir()
    iverilog = directory / "iverilog"
    iverilog.write_text(
        "#!/bin/sh\nif [ \"$1\" = \"-V\" ]; then echo 'Icarus Verilog fake 1.0'; fi\nexit 0\n",
        encoding="utf-8",
    )
    yosys = directory / "yosys"
    yosys.write_text(
        "#!/bin/sh\nif [ \"$1\" = \"-V\" ]; then echo 'Yosys fake 1.0'; fi\nexit 0\n",
        encoding="utf-8",
    )
    iverilog.chmod(0o755)
    yosys.chmod(0o755)


def test_mock_smoke_run_with_fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    copy_smoke_assets(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    create_fake_tools(fake_bin)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")
    designs = load_designs(tmp_path)
    provider = MockProvider(tmp_path / "mock_responses", GenerationSettings())
    run_dir = run_experiment(
        root=tmp_path,
        provider=provider,
        designs=designs,
        design_names=list(designs),
        k=3,
        run_id="smoke",
    )
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["e2e_at_1"] == pytest.approx(2 / 3)
    assert metrics["e2e_at_k"] == 1.0
    assert metrics["sey_at_k"] == 1.0
    rows = (run_dir / "results.csv").read_text(encoding="utf-8")
    assert "half_adder,2,2" in rows


@pytest.mark.integration
def test_smoke_with_real_iverilog_and_yosys(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("yosys") is None:
        pytest.skip("Icarus Verilog and Yosys are required")
    copy_smoke_assets(tmp_path)
    designs = load_designs(tmp_path)
    provider = MockProvider(tmp_path / "mock_responses", GenerationSettings())
    run_dir = run_experiment(
        root=tmp_path,
        provider=provider,
        designs=designs,
        design_names=list(designs),
        k=3,
        run_id="real-tools",
    )
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["e2e_at_k"] == 1.0
