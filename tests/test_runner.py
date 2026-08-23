from __future__ import annotations

from pathlib import Path

import pytest

from llm_rtl_eval.runner import build_refined_prompt, load_designs, run_experiment
from llm_rtl_eval.providers import GenerationSettings, FixtureProvider
from llm_rtl_eval.utils import ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def test_refined_prompt_is_failure_directed_without_code_patch() -> None:
    prompt = build_refined_prompt("BASE", [("P", "missing port carry")])
    assert "first failing stage = P" in prompt
    assert "missing port carry" in prompt
    assert "Do not change the target functionality" in prompt
    assert "BASE" in prompt


def test_load_designs_rejects_unsafe_reference_path(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/d.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "designs.json").write_text(
        '{"d":{"prompt":"prompts/d.txt","reference":"../outside","top_module":"d"}}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="escapes repository"):
        load_designs(tmp_path)


def test_run_rejects_duplicate_designs(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "reference/d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts/d.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "reference/d/d.v").write_text("module d; endmodule\n", encoding="utf-8")
    (tmp_path / "designs.json").write_text(
        '{"d":{"prompt":"prompts/d.txt","reference":"reference/d","top_module":"d"}}',
        encoding="utf-8",
    )
    designs = load_designs(tmp_path)
    (tmp_path / "fixtures/llm_outputs").mkdir(parents=True, exist_ok=True)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    with pytest.raises(ConfigurationError, match="Duplicate designs"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=["d", "d"],
            k=3,
            run_id="test",
        )


def test_run_rejects_unknown_design(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "reference/d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts/d.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "reference/d/d.v").write_text("module d; endmodule\n", encoding="utf-8")
    (tmp_path / "designs.json").write_text(
        '{"d":{"prompt":"prompts/d.txt","reference":"reference/d","top_module":"d"}}',
        encoding="utf-8",
    )
    designs = load_designs(tmp_path)
    (tmp_path / "fixtures/llm_outputs").mkdir(parents=True, exist_ok=True)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    with pytest.raises(ConfigurationError, match="Unknown designs"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=["missing"],
            k=3,
            run_id="test",
        )


def test_results_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "results").symlink_to(outside, target_is_directory=True)
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "reference/d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts/d.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "reference/d/d.v").write_text("module d; endmodule\n", encoding="utf-8")
    (tmp_path / "designs.json").write_text(
        '{"d":{"prompt":"prompts/d.txt","reference":"reference/d","top_module":"d"}}',
        encoding="utf-8",
    )
    designs = load_designs(tmp_path)
    (tmp_path / "fixtures/llm_outputs").mkdir(parents=True, exist_ok=True)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    with pytest.raises(ConfigurationError, match="escapes repository"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=["d"],
            k=3,
            run_id="test",
        )


def test_run_checks_tools_before_creating_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_rtl_eval.runner import InfrastructureError

    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "reference/d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "fixtures/llm_outputs/d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts/d.txt").write_text("prompt", encoding="utf-8")
    (tmp_path / "reference/d/d.v").write_text("module d; endmodule\n", encoding="utf-8")
    (tmp_path / "fixtures/llm_outputs/d/default.v").write_text("module d; endmodule\n", encoding="utf-8")
    (tmp_path / "designs.json").write_text(
        '{"d":{"prompt":"prompts/d.txt","reference":"reference/d","top_module":"d"}}',
        encoding="utf-8",
    )
    designs = load_designs(tmp_path)
    (tmp_path / "fixtures/llm_outputs").mkdir(parents=True, exist_ok=True)
    provider = FixtureProvider(tmp_path / "fixtures/llm_outputs", GenerationSettings())
    monkeypatch.setattr("llm_rtl_eval.runner.shutil.which", lambda _: None)
    with pytest.raises(InfrastructureError, match="Required EDA tools"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=["d"],
            k=3,
            run_id="test",
        )
    assert not (tmp_path / "results/test").exists()


def test_provider_preflight_fails_before_creating_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import shutil

    from llm_rtl_eval.providers import GenerationSettings, OpenAICompatibleProvider
    from llm_rtl_eval.utils import ConfigurationError

    shutil.copy2(ROOT / "designs.json", tmp_path / "designs.json")
    for directory in ("prompts", "reference"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    stub_bin = tmp_path / "tool-stubs"
    stub_bin.mkdir()
    for name in ("iverilog", "yosys"):
        path = stub_bin / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_bin}:{os.environ.get('PATH', '')}")
    provider = OpenAICompatibleProvider(
        "model-x",
        GenerationSettings(),
        endpoint="https://example.com/v1/chat/completions",
        api_key=None,
    )
    designs = load_designs(tmp_path)
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        run_experiment(
            root=tmp_path,
            provider=provider,
            designs=designs,
            design_names=["half_adder"],
            k=1,
            run_id="no-key",
        )
    assert not (tmp_path / "results" / "no-key").exists()
