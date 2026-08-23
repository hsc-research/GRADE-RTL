from __future__ import annotations

from pathlib import Path

import pytest

from llm_rtl_eval.providers import (
    GenerationSettings,
    FixtureProvider,
    ReplayProvider,
    OpenAICompatibleProvider,
    validate_endpoint,
)
from llm_rtl_eval.utils import ConfigurationError


def test_endpoint_requires_https_except_localhost() -> None:
    assert validate_endpoint("http://localhost:11434/api/generate").startswith("http://")
    with pytest.raises(ConfigurationError, match="must use HTTPS"):
        validate_endpoint("http://example.com/v1/chat/completions")
    assert validate_endpoint("https://example.com/v1/chat/completions").startswith("https://")


def test_generation_settings_validation() -> None:
    with pytest.raises(ConfigurationError):
        GenerationSettings(top_p=0).validate()
    with pytest.raises(ConfigurationError):
        GenerationSettings(max_tokens=0).validate()


def test_fixture_provider_uses_attempt_specific_response(tmp_path: Path) -> None:
    directory = tmp_path / "d"
    directory.mkdir()
    (directory / "attempt_2.v").write_text("module d; endmodule\n", encoding="utf-8")
    provider = FixtureProvider(tmp_path, GenerationSettings())
    response = provider.generate("prompt", design="d", attempt=2)
    assert "module d" in response.text
    assert response.metadata["seed_applied"] is False
    assert response.metadata["test_fixture"] is True
    assert response.metadata["paper_eligible"] is False
    assert response.metadata["execution_mode"] == "fixture"


def test_openai_compatible_payload_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "id": "response-id",
                "choices": [{"message": {"content": "module x; endmodule"}}],
                "usage": {"total_tokens": 10},
            }

    provider = OpenAICompatibleProvider(
        "model-x",
        GenerationSettings(seed=7),
        endpoint="https://example.com/v1/chat/completions",
        api_key="test-key",
    )
    captured = {}

    def stub_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", stub_post)
    response = provider.generate("hello", design="x", attempt=1)
    assert captured["json"]["seed"] == 7
    assert captured["json"]["messages"][0]["content"] == "hello"
    assert response.metadata["seed_applied"] is True


def test_cloud_provider_requires_explicit_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from llm_rtl_eval.providers import create_provider

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ConfigurationError, match="exact model"):
        create_provider("openai", None, GenerationSettings(), repository_root=tmp_path)


def test_endpoint_rejects_embedded_credentials() -> None:
    with pytest.raises(ConfigurationError, match="embed credentials"):
        validate_endpoint("https://user:dummy@host.invalid/v1")


def test_gemini_seed_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_rtl_eval.providers import GeminiProvider

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "candidates": [{"content": {"parts": [{"text": "module x; endmodule"}]}}],
                "usageMetadata": {},
            }

    provider = GeminiProvider(
        "gemini-test",
        GenerationSettings(seed=11),
        endpoint="https://example.com/models/gemini-test:generateContent",
        api_key="test-key",
    )
    captured = {}

    def stub_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", stub_post)
    response = provider.generate("hello", design="x", attempt=1)
    assert captured["json"]["generationConfig"]["seed"] == 11
    assert response.metadata["seed_applied"] is True


def test_generation_settings_rejects_invalid_seed() -> None:
    with pytest.raises(ConfigurationError, match="seed"):
        GenerationSettings(seed=-1).validate()
    with pytest.raises(ConfigurationError, match="seed"):
        GenerationSettings(seed=True).validate()


def test_fixture_provider_records_relative_source_and_does_not_apply_seed(tmp_path: Path) -> None:
    directory = tmp_path / "d"
    directory.mkdir()
    (directory / "default.v").write_text("module d; endmodule\n", encoding="utf-8")
    provider = FixtureProvider(tmp_path, GenerationSettings(seed=5))
    response = provider.generate("prompt", design="d", attempt=1)
    assert response.metadata["source"] == "d/default.v"
    assert response.metadata["seed_requested"] == 5
    assert response.metadata["seed_applied"] is False


def test_endpoint_rejects_query_string_credentials() -> None:
    with pytest.raises(ConfigurationError, match="query string"):
        validate_endpoint("https://example.com/v1/chat/completions?api_key=secret")


def test_openai_compatible_configurable_token_field(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": "module x; endmodule"}}]}

    provider = OpenAICompatibleProvider(
        "model-x",
        GenerationSettings(),
        endpoint="https://example.com/v1/chat/completions",
        api_key="test-key",
        token_field="max_completion_tokens",
    )
    captured = {}

    def stub_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", stub_post)
    response = provider.generate("hello", design="x", attempt=1)
    assert captured["json"]["max_completion_tokens"] == 4096
    assert "max_tokens" not in captured["json"]
    assert response.metadata["token_field"] == "max_completion_tokens"


def test_huggingface_default_uses_current_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from llm_rtl_eval.providers import create_provider

    monkeypatch.setenv("HF_MODEL", "org/model")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    provider = create_provider("huggingface", None, GenerationSettings(), repository_root=tmp_path)
    assert provider.endpoint == "https://router.huggingface.co/v1/chat/completions"
    assert provider.name == "huggingface"



def _write_replay_source(
    root: Path,
    *,
    mode: str = "live",
    paper_result: bool = True,
    prompt: str = "prompt\n",
) -> Path:
    import hashlib
    import json

    source = root / "source-run"
    attempt = source / "d" / "attempt_1"
    attempt.mkdir(parents=True)
    raw = "module d; endmodule\n"
    (attempt / "prompt.txt").write_text(prompt, encoding="utf-8")
    (attempt / "raw_response.txt").write_text(raw, encoding="utf-8")
    source_provider = "openai" if mode == "live" else "fixture"
    metadata = {
        "provider": source_provider,
        "model": "model-x",
        "execution_mode": mode,
        "response_origin": "live" if mode == "live" else "synthetic_fixture",
        "paper_eligible": mode == "live",
        "test_fixture": mode == "fixture",
        "tool_mode": "real",
        "paper_result_eligible": mode == "live",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }
    (attempt / "generation_metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    manifest = {
        "schema_version": 2,
        "execution_mode": mode,
        "response_origin": metadata["response_origin"],
        "provider": source_provider,
        "model": "model-x",
        "tool_mode": "real",
        "provider_paper_eligible": mode == "live",
        "test_fixture": mode == "fixture",
        "paper_result_eligible": mode == "live",
        "paper_result": paper_result and mode == "live",
        "designs": ["d"],
    }
    (source / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "attempts.json").write_text("{}\n", encoding="utf-8")
    (source / "results.csv").write_text("design\nd\n", encoding="utf-8")
    (source / "metrics.json").write_text("{}\n", encoding="utf-8")
    (source / "metrics.txt").write_text("test\n", encoding="utf-8")
    return source


def test_replay_provider_verifies_recorded_live_response(tmp_path: Path) -> None:
    source = _write_replay_source(tmp_path)
    provider = ReplayProvider(source, GenerationSettings())
    response = provider.generate("prompt\n", design="d", attempt=1)
    assert "module d" in response.text
    assert response.metadata["execution_mode"] == "replay"
    assert response.metadata["response_origin"] == "recorded_live"
    assert response.metadata["replay_verified"] is True
    assert provider.paper_eligible is True


def test_replay_provider_rejects_fixture_source(tmp_path: Path) -> None:
    source = _write_replay_source(tmp_path, mode="fixture", paper_result=False)
    with pytest.raises(ConfigurationError, match="Fixture/synthetic"):
        ReplayProvider(source, GenerationSettings())


def test_replay_provider_rejects_prompt_mismatch(tmp_path: Path) -> None:
    source = _write_replay_source(tmp_path)
    provider = ReplayProvider(source, GenerationSettings())
    with pytest.raises(ConfigurationError, match="prompt mismatch"):
        provider.generate("different prompt\n", design="d", attempt=1)


def test_replay_provider_not_paper_eligible_without_certified_source(tmp_path: Path) -> None:
    source = _write_replay_source(tmp_path, paper_result=False)
    provider = ReplayProvider(source, GenerationSettings())
    assert provider.paper_eligible is False


def test_replay_provider_reads_exported_bundle(tmp_path: Path) -> None:
    import hashlib
    import json

    bundle = tmp_path / "bundle"
    design_dir = bundle / "d"
    design_dir.mkdir(parents=True)
    prompt = "prompt\n"
    response = "module d; endmodule\n"
    (bundle / "replay_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "source_run_id": "live-source",
                "paper_eligible": True,
                "designs": ["d"],
                "refinement_budget": 1,
            }
        ),
        encoding="utf-8",
    )
    (design_dir / "attempt_1.txt").write_text(response, encoding="utf-8")
    (design_dir / "attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "design": "d",
                "attempt": 1,
                "paper_eligible": True,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    provider = ReplayProvider(bundle, GenerationSettings(), expected_model="model-x")
    generated = provider.generate(prompt, design="d", attempt=1)
    assert generated.text == response
    assert generated.metadata["replay_source_kind"] == "bundle"
    assert generated.metadata["replay_verified"] is True
    assert provider.paper_eligible is True


def test_replay_provider_reads_exported_bundle(tmp_path: Path) -> None:
    import hashlib
    import json

    bundle = tmp_path / "bundle"
    design_dir = bundle / "d"
    design_dir.mkdir(parents=True)
    prompt = "prompt\n"
    response_text = "module d; endmodule\n"
    (bundle / "replay_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "source_run_id": "live-run",
                "paper_eligible": True,
                "designs": ["d"],
                "refinement_budget": 1,
            }
        ),
        encoding="utf-8",
    )
    (design_dir / "attempt_1.prompt.txt").write_text(prompt, encoding="utf-8")
    (design_dir / "attempt_1.txt").write_text(response_text, encoding="utf-8")
    (design_dir / "attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "recorded_live",
                "provider": "openai",
                "model": "model-x",
                "design": "d",
                "attempt": 1,
                "paper_eligible": True,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "response_sha256": hashlib.sha256(response_text.encode()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    provider = ReplayProvider(bundle, GenerationSettings())
    response = provider.generate(prompt, design="d", attempt=1)
    assert response.text == response_text
    assert response.metadata["replay_source_kind"] == "bundle"
    assert response.metadata["paper_eligible"] is True
