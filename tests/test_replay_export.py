from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from llm_rtl_eval.providers import GenerationSettings, ReplayProvider

ROOT = Path(__file__).resolve().parents[1]


def test_exported_live_run_can_be_replayed(tmp_path: Path) -> None:
    source = tmp_path / "live-source"
    attempt_dir = source / "half_adder" / "attempt_1"
    attempt_dir.mkdir(parents=True)
    prompt = "Generate half_adder.\n"
    response = "module half_adder; endmodule\n"
    (attempt_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (attempt_dir / "raw_response.txt").write_text(response, encoding="utf-8")
    (attempt_dir / "generation_metadata.json").write_text(
        json.dumps(
            {
                "provider": "openai",
                "model": "model-x",
                "execution_mode": "live",
                "response_origin": "live",
                "test_fixture": False,
                "paper_eligible": True,
                "tool_mode": "real",
                "paper_result_eligible": True,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "raw_response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                "seed_requested": 7,
                "seed_applied": True,
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 1024,
            }
        ),
        encoding="utf-8",
    )
    (source / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "created_utc": "2026-08-23T00:00:00+00:00",
                "execution_mode": "live",
                "response_origin": "live",
                "provider": "openai",
                "model": "model-x",
                "tool_mode": "real",
                "provider_paper_eligible": True,
                "test_fixture": False,
                "paper_result_eligible": True,
                "paper_result": True,
                "designs": ["half_adder"],
                "refinement_budget": 1,
                "tool_versions": {"iverilog": "real", "yosys": "real"},
            }
        ),
        encoding="utf-8",
    )
    (source / "attempts.json").write_text("{}\n", encoding="utf-8")
    (source / "results.csv").write_text("design\nhalf_adder\n", encoding="utf-8")
    (source / "metrics.json").write_text("{}\n", encoding="utf-8")
    (source / "metrics.txt").write_text("test\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_replay.py"),
            str(source),
            str(bundle),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert result.returncode == 0, result.stdout
    assert (bundle / "half_adder" / "attempt_1.prompt.txt").read_text(
        encoding="utf-8"
    ) == prompt
    provider = ReplayProvider(bundle, GenerationSettings())
    replayed = provider.generate(prompt, design="half_adder", attempt=1)
    assert replayed.text == response
    assert replayed.metadata["response_origin"] == "recorded_live"


def test_export_rejects_output_inside_source_run(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "run_manifest.json").write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_replay.py"),
            str(source),
            str(source / "bundle"),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert result.returncode == 2
    assert "may not be created inside" in result.stdout
