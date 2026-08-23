from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from llm_rtl_eval.cli import build_provider, resolve_mode_and_provider
from llm_rtl_eval.providers import FixtureProvider, GenerationSettings
from llm_rtl_eval.run_verifier import RunVerificationError, verify_run
from llm_rtl_eval.runner import load_designs, run_experiment
from llm_rtl_eval.utils import ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def test_cli_mode_resolution() -> None:
    assert resolve_mode_and_provider(None, None) == ("fixture", "fixture")
    assert resolve_mode_and_provider(None, "mock") == ("fixture", "fixture")
    assert resolve_mode_and_provider("fixture", None) == ("fixture", "fixture")
    assert resolve_mode_and_provider("replay", None) == ("replay", "replay")
    assert resolve_mode_and_provider(None, "openai") == ("live", "openai")
    assert resolve_mode_and_provider("live", "gemini") == ("live", "gemini")


def test_cli_rejects_incompatible_mode_provider(tmp_path: Path) -> None:
    settings = GenerationSettings()
    with pytest.raises(ConfigurationError, match="incompatible"):
        build_provider(
            root=tmp_path,
            mode="fixture",
            provider_name="openai",
            model=None,
            settings=settings,
            fixture_dir=None,
            replay_source=None,
        )
    with pytest.raises(ConfigurationError, match="requires --provider"):
        build_provider(
            root=tmp_path,
            mode="live",
            provider_name=None,
            model=None,
            settings=settings,
            fixture_dir=None,
            replay_source=None,
        )


def _create_tool_stubs(directory: Path) -> None:
    directory.mkdir()
    for name, version in (
        ("iverilog", "Icarus Verilog test stub 1.0"),
        ("yosys", "Yosys test stub 1.0"),
    ):
        path = directory / name
        path.write_text(
            f"#!/bin/sh\nif [ \"$1\" = \"-V\" ]; then echo '{version}'; fi\nexit 0\n",
            encoding="utf-8",
        )
        path.chmod(0o755)


def test_fixture_run_is_explicitly_not_paper_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference", "fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    designs = load_designs(tmp_path)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    run_dir = run_experiment(
        root=tmp_path,
        provider=provider,
        designs=designs,
        design_names=list(designs),
        k=3,
        run_id="fixture-run",
    )
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_mode"] == "fixture"
    assert manifest["response_origin"] == "synthetic_fixture"
    assert manifest["tool_mode"] == "stub"
    assert manifest["paper_result_eligible"] is False
    lines = verify_run(run_dir)
    assert "paper_result_eligible=false" in lines
    with pytest.raises(RunVerificationError, match="not paper-eligible"):
        verify_run(run_dir, require_paper_eligible=True)


def test_fixture_cannot_be_marked_as_paper_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference", "fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    designs = load_designs(tmp_path)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    with pytest.raises(ConfigurationError, match="Synthetic fixture"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=list(designs),
            k=3,
            run_id="invalid-paper-fixture",
            paper_run=True,
        )
    assert not (tmp_path / "results/invalid-paper-fixture").exists()


def test_describe_modes_text_is_available() -> None:
    from llm_rtl_eval.cli import MODE_HELP

    assert "fixture" in MODE_HELP
    assert "replay" in MODE_HELP
    assert "live" in MODE_HELP
    assert "Never eligible for paper results" in MODE_HELP


def test_cli_fixture_mode_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from llm_rtl_eval.cli import main

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference", "fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    returncode = main(
        [
            "--root",
            str(tmp_path),
            "--mode",
            "fixture",
            "--all",
            "--k",
            "3",
            "--run-id",
            "cli-fixture",
        ]
    )
    assert returncode == 0
    output = capsys.readouterr().out
    assert "Mode: fixture" in output
    metrics = json.loads(
        (tmp_path / "results" / "cli-fixture" / "metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert metrics["e2e_at_1"] == pytest.approx(2 / 3)
    assert metrics["e2e_at_k"] == 1.0


def test_cli_implicit_mode_warns_that_fixture_is_synthetic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from llm_rtl_eval.cli import main

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference", "fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    returncode = main(
        [
            "--root",
            str(tmp_path),
            "--design",
            "priority_encoder",
            "--run-id",
            "implicit-fixture",
        ]
    )
    assert returncode == 0
    captured = capsys.readouterr()
    assert "using fixture mode" in captured.err
    manifest = json.loads(
        (tmp_path / "results" / "implicit-fixture" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["test_fixture"] is True
    assert manifest["paper_result"] is False


def test_cli_requires_explicit_design_selection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from llm_rtl_eval.cli import main

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference", "fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    returncode = main(["--root", str(tmp_path), "--mode", "fixture"])
    assert returncode == 2
    assert "Select at least one --design" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()


def test_cli_replay_mode_uses_archived_response_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from llm_rtl_eval.cli import main

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    prompt = (tmp_path / "prompts" / "priority_encoder.txt").read_text(encoding="utf-8")
    response = (ROOT / "fixtures" / "llm_outputs" / "priority_encoder" / "attempt_1.v").read_text(
        encoding="utf-8"
    )
    bundle = tmp_path / "replay-bundle"
    design_dir = bundle / "priority_encoder"
    design_dir.mkdir(parents=True)
    (bundle / "replay_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "source_run_id": "source-live",
                "paper_eligible": True,
                "designs": ["priority_encoder"],
                "refinement_budget": 1,
            }
        ),
        encoding="utf-8",
    )
    (design_dir / "attempt_1.prompt.txt").write_text(prompt, encoding="utf-8")
    (design_dir / "attempt_1.txt").write_text(response, encoding="utf-8")
    (design_dir / "attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "design": "priority_encoder",
                "attempt": 1,
                "paper_eligible": True,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    returncode = main(
        [
            "--root",
            str(tmp_path),
            "--mode",
            "replay",
            "--replay-source",
            str(bundle),
            "--design",
            "priority_encoder",
            "--k",
            "1",
            "--run-id",
            "replay-run",
        ]
    )
    assert returncode == 0
    manifest = json.loads(
        (tmp_path / "results" / "replay-run" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["execution_mode"] == "replay"
    assert manifest["response_origin"] == "recorded_live"
    assert manifest["tool_mode"] == "stub"
    assert manifest["paper_result"] is False


def test_cli_live_mode_orchestration_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm_rtl_eval import cli
    from llm_rtl_eval.providers import GenerationResponse, Provider

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    response_text = (
        ROOT / "fixtures" / "llm_outputs" / "priority_encoder" / "attempt_1.v"
    ).read_text(encoding="utf-8")

    class TestLiveProvider(Provider):
        name = "test-live"
        execution_mode = "live"
        response_origin = "live"
        paper_eligible = True
        test_fixture = False

        def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
            return GenerationResponse(
                response_text,
                {
                    **self.base_metadata(seed_applied=False),
                    "design": design,
                    "attempt": attempt,
                },
            )

    provider = TestLiveProvider("model-x", GenerationSettings())
    monkeypatch.setattr(cli, "create_provider", lambda *args, **kwargs: provider)
    stub_bin = tmp_path / "tool-stubs"
    _create_tool_stubs(stub_bin)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    returncode = cli.main(
        [
            "--root",
            str(tmp_path),
            "--mode",
            "live",
            "--provider",
            "openai",
            "--model",
            "model-x",
            "--design",
            "priority_encoder",
            "--k",
            "1",
            "--run-id",
            "live-run",
        ]
    )
    assert returncode == 0
    manifest = json.loads(
        (tmp_path / "results" / "live-run" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["execution_mode"] == "live"
    assert manifest["response_origin"] == "live"
    assert manifest["paper_result"] is False
