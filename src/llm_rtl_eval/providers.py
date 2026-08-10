from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import requests

from .utils import ConfigurationError


@dataclass(slots=True)
class GenerationSettings:
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096
    seed: int | None = None
    timeout_seconds: float = 300.0

    def validate(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigurationError("temperature must be between 0 and 2")
        if not 0.0 < self.top_p <= 1.0:
            raise ConfigurationError("top_p must be in (0, 1]")
        if not 1 <= self.max_tokens <= 131072:
            raise ConfigurationError("max_tokens must be between 1 and 131072")
        if self.seed is not None:
            if isinstance(self.seed, bool) or not isinstance(self.seed, int):
                raise ConfigurationError("seed must be an integer")
            if not 0 <= self.seed <= 2**31 - 1:
                raise ConfigurationError("seed must be between 0 and 2^31-1")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("timeout_seconds must be positive")


@dataclass(slots=True)
class GenerationResponse:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a provider request or response cannot be completed safely."""


class Provider:
    name = "provider"

    def __init__(self, model: str, settings: GenerationSettings) -> None:
        settings.validate()
        if not model.strip():
            raise ConfigurationError("model identifier may not be empty")
        self.model = model
        self.settings = settings

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        raise NotImplementedError

    def base_metadata(self, *, seed_applied: bool) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": self.settings.max_tokens,
            "seed_requested": self.settings.seed,
            "seed_applied": seed_applied,
            "timeout_seconds": self.settings.timeout_seconds,
        }


class HttpProvider(Provider):
    def __init__(
        self,
        model: str,
        settings: GenerationSettings,
        *,
        endpoint: str,
        api_key: str | None,
        allow_http_localhost: bool = True,
    ) -> None:
        super().__init__(model, settings)
        self.endpoint = validate_endpoint(endpoint, allow_http_localhost=allow_http_localhost)
        self.api_key = api_key
        self.session = requests.Session()

    def require_key(self, variable: str) -> str:
        if not self.api_key or self.api_key.startswith("YOUR_"):
            raise ConfigurationError(f"Missing required environment variable: {variable}")
        return self.api_key

    def post(self, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.post(
                self.endpoint,
                timeout=self.settings.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            suffix = f" (HTTP {status})" if status is not None else ""
            raise ProviderError(f"{self.name} request failed{suffix}") from exc

    def response_json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except (ValueError, requests.RequestException) as exc:
            raise ProviderError(f"{self.name} returned a non-JSON response") from exc


class MockProvider(Provider):
    name = "mock"

    def __init__(self, root: Path, settings: GenerationSettings) -> None:
        super().__init__("deterministic-mock", settings)
        self.root = root.resolve()

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        directory = self.root / design
        candidates = [directory / f"attempt_{attempt}.v", directory / "default.v"]
        for path in candidates:
            if path.is_file():
                return GenerationResponse(
                    path.read_text(encoding="utf-8"),
                    {
                        **self.base_metadata(seed_applied=False),
                        "source": path.relative_to(self.root).as_posix(),
                        "prompt_length": len(prompt),
                        "deterministic_mock": True,
                    },
                )
        raise FileNotFoundError(
            f"No mock response for {design} attempt {attempt}; checked {candidates}"
        )


class OpenAICompatibleProvider(HttpProvider):
    name = "openai"

    def __init__(
        self,
        model: str,
        settings: GenerationSettings,
        *,
        endpoint: str,
        api_key: str | None,
        provider_name: str = "openai",
        api_key_env: str = "OPENAI_API_KEY",
        token_field: str = "max_tokens",
    ) -> None:
        super().__init__(model, settings, endpoint=endpoint, api_key=api_key)
        self.name = provider_name
        self.api_key_env = api_key_env
        if token_field not in {"max_tokens", "max_completion_tokens"}:
            raise ConfigurationError(f"Unsupported token field: {token_field}")
        self.token_field = token_field

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        key = self.require_key(self.api_key_env)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            self.token_field: self.settings.max_tokens,
        }
        seed_applied = self.settings.seed is not None
        if seed_applied:
            payload["seed"] = self.settings.seed
        response = self.post(
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        data = self.response_json(response)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Unexpected {self.name} response schema") from exc
        return GenerationResponse(
            str(text),
            {
                **self.base_metadata(seed_applied=seed_applied),
                "endpoint": self.endpoint,
                "token_field": self.token_field,
                "design": design,
                "attempt": attempt,
                "response_id": data.get("id"),
                "response_model": data.get("model"),
                "system_fingerprint": data.get("system_fingerprint"),
                "usage": data.get("usage"),
            },
        )


class AnthropicProvider(HttpProvider):
    name = "anthropic"

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        key = self.require_key("ANTHROPIC_API_KEY")
        payload = {
            "model": self.model,
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self.post(
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        data = self.response_json(response)
        blocks = data.get("content", [])
        text = "".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
        if not text:
            raise ProviderError("Anthropic response contained no text blocks")
        return GenerationResponse(
            text,
            {
                **self.base_metadata(seed_applied=False),
                "endpoint": self.endpoint,
                "design": design,
                "attempt": attempt,
                "response_id": data.get("id"),
                "response_model": data.get("model"),
                "usage": data.get("usage"),
            },
        )


class GeminiProvider(HttpProvider):
    name = "gemini"

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        key = self.require_key("GEMINI_API_KEY")
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.settings.temperature,
                "topP": self.settings.top_p,
                "maxOutputTokens": self.settings.max_tokens,
            },
        }
        seed_applied = self.settings.seed is not None
        if seed_applied:
            payload["generationConfig"]["seed"] = self.settings.seed
        response = self.post(
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=payload,
        )
        data = self.response_json(response)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected Gemini response schema") from exc
        return GenerationResponse(
            text,
            {
                **self.base_metadata(seed_applied=seed_applied),
                "endpoint": self.endpoint,
                "design": design,
                "attempt": attempt,
                "usage": data.get("usageMetadata"),
            },
        )


class HuggingFaceProvider(OpenAICompatibleProvider):
    """Hugging Face Inference Providers via the OpenAI-compatible router."""

    name = "huggingface"

    def __init__(
        self,
        model: str,
        settings: GenerationSettings,
        *,
        endpoint: str,
        api_key: str | None,
    ) -> None:
        super().__init__(
            model,
            settings,
            endpoint=endpoint,
            api_key=api_key,
            provider_name="huggingface",
            api_key_env="HF_TOKEN (or HF_API_KEY)",
            token_field="max_tokens",
        )


class OllamaProvider(HttpProvider):
    name = "ollama"

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        options: dict[str, Any] = {
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "num_predict": self.settings.max_tokens,
        }
        if self.settings.seed is not None:
            options["seed"] = self.settings.seed
        response = self.post(
            json={"model": self.model, "prompt": prompt, "stream": False, "options": options}
        )
        data = self.response_json(response)
        text = data.get("response", "")
        if not text:
            raise ProviderError("Ollama response contained no response text")
        return GenerationResponse(
            str(text),
            {
                **self.base_metadata(seed_applied=self.settings.seed is not None),
                "endpoint": self.endpoint,
                "design": design,
                "attempt": attempt,
                "done_reason": data.get("done_reason"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            },
        )


def validate_endpoint(endpoint: str, *, allow_http_localhost: bool = True) -> str:
    endpoint = endpoint.strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"Invalid provider endpoint: {endpoint!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("Provider endpoint must not embed credentials")
    if parsed.fragment:
        raise ConfigurationError("Provider endpoint must not contain a URL fragment")
    sensitive_query_names = {"key", "api_key", "apikey", "access_token", "token"}
    for name, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if name.lower() in sensitive_query_names:
            raise ConfigurationError("Provider endpoint must not place credentials in the query string")
    hostname = (parsed.hostname or "").lower()
    local = hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (allow_http_localhost and local):
        raise ConfigurationError(
            "Provider endpoints carrying prompts or API keys must use HTTPS; "
            "plain HTTP is permitted only for localhost"
        )
    return endpoint.rstrip("/")


def _required_model(value: str | None, environment_variable: str) -> str:
    selected = value or os.environ.get(environment_variable, "")
    if not selected.strip():
        raise ConfigurationError(
            f"Specify an exact model with --model or {environment_variable}"
        )
    return selected.strip()


def create_provider(
    name: str,
    model: str | None,
    settings: GenerationSettings,
    *,
    repository_root: Path,
) -> Provider:
    normalized = name.lower()
    if normalized == "mock":
        return MockProvider(repository_root / "mock_responses", settings)
    if normalized == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OllamaProvider(
            model or os.environ.get("OLLAMA_MODEL", "deepseek-coder:6.7b"),
            settings,
            endpoint=host.rstrip("/") + "/api/generate",
            api_key=None,
        )
    if normalized == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleProvider(
            _required_model(model, "OPENAI_MODEL"),
            settings,
            endpoint=base.rstrip("/") + "/chat/completions",
            api_key=os.environ.get("OPENAI_API_KEY"),
            token_field=os.environ.get("OPENAI_TOKEN_FIELD", "max_completion_tokens"),
        )
    if normalized == "deepseek":
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        return OpenAICompatibleProvider(
            _required_model(model, "DEEPSEEK_MODEL"),
            settings,
            endpoint=base.rstrip("/") + "/chat/completions",
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            provider_name="deepseek",
            api_key_env="DEEPSEEK_API_KEY",
            token_field="max_tokens",
        )
    if normalized == "anthropic":
        return AnthropicProvider(
            _required_model(model, "ANTHROPIC_MODEL"),
            settings,
            endpoint=os.environ.get("ANTHROPIC_ENDPOINT", "https://api.anthropic.com/v1/messages"),
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    if normalized == "gemini":
        selected = _required_model(model, "GEMINI_MODEL")
        endpoint = os.environ.get(
            "GEMINI_ENDPOINT",
            f"https://generativelanguage.googleapis.com/v1beta/models/{selected}:generateContent",
        )
        return GeminiProvider(
            selected,
            settings,
            endpoint=endpoint,
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
    if normalized == "huggingface":
        selected = _required_model(model, "HF_MODEL")
        endpoint = os.environ.get(
            "HF_ENDPOINT",
            "https://router.huggingface.co/v1/chat/completions",
        )
        return HuggingFaceProvider(
            selected,
            settings,
            endpoint=endpoint,
            api_key=os.environ.get("HF_TOKEN") or os.environ.get("HF_API_KEY"),
        )
    raise ConfigurationError(
        f"Unknown provider {name!r}; choose mock, ollama, openai, deepseek, anthropic, gemini, or huggingface"
    )
