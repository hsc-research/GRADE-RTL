from __future__ import annotations

from pathlib import Path

import pytest

from llm_rtl_eval.providers import (
    GenerationSettings,
    MockProvider,
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


def test_mock_provider_uses_attempt_specific_response(tmp_path: Path) -> None:
    directory = tmp_path / "d"
    directory.mkdir()
    (directory / "attempt_2.v").write_text("module d; endmodule\n", encoding="utf-8")
    provider = MockProvider(tmp_path, GenerationSettings())
    response = provider.generate("prompt", design="d", attempt=2)
    assert "module d" in response.text
    assert response.metadata["seed_applied"] is False
    assert response.metadata["deterministic_mock"] is True


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

    def fake_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", fake_post)
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

    def fake_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", fake_post)
    response = provider.generate("hello", design="x", attempt=1)
    assert captured["json"]["generationConfig"]["seed"] == 11
    assert response.metadata["seed_applied"] is True


def test_generation_settings_rejects_invalid_seed() -> None:
    with pytest.raises(ConfigurationError, match="seed"):
        GenerationSettings(seed=-1).validate()
    with pytest.raises(ConfigurationError, match="seed"):
        GenerationSettings(seed=True).validate()


def test_mock_provider_records_relative_source_and_does_not_apply_seed(tmp_path: Path) -> None:
    directory = tmp_path / "d"
    directory.mkdir()
    (directory / "default.v").write_text("module d; endmodule\n", encoding="utf-8")
    provider = MockProvider(tmp_path, GenerationSettings(seed=5))
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

    def fake_post(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(provider, "post", fake_post)
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
