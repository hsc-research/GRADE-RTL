from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlparse

import requests

from .run_verifier import RunVerificationError, verify_run
from .utils import ConfigurationError, sha256_file

ExecutionMode = Literal["fixture", "replay", "live"]


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Provider:
    name = "provider"
    execution_mode: ExecutionMode = "live"
    response_origin = "live"
    paper_eligible = True
    test_fixture = False

    def __init__(self, model: str, settings: GenerationSettings) -> None:
        settings.validate()
        if not model.strip():
            raise ConfigurationError("model identifier may not be empty")
        self.model = model
        self.settings = settings

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        raise NotImplementedError

    def preflight(self) -> None:
        """Validate local configuration without contacting the model provider."""
        return None

    def provenance_metadata(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "response_origin": self.response_origin,
            "provider_paper_eligible": self.paper_eligible,
            "test_fixture": self.test_fixture,
        }

    def base_metadata(self, *, seed_applied: bool) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "execution_mode": self.execution_mode,
            "response_origin": self.response_origin,
            "paper_eligible": self.paper_eligible,
            "test_fixture": self.test_fixture,
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


class FixtureProvider(Provider):
    """Read synthetic deterministic RTL fixtures used only for tests and CI."""

    name = "fixture"
    execution_mode: ExecutionMode = "fixture"
    response_origin = "synthetic_fixture"
    paper_eligible = False
    test_fixture = True

    def __init__(self, root: Path, settings: GenerationSettings) -> None:
        super().__init__("synthetic-fixture", settings)
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ConfigurationError(f"Fixture directory does not exist: {self.root}")

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
                        "fixture_kind": "synthetic_rtl",
                    },
                )
        raise FileNotFoundError(
            "No synthetic fixture response for "
            f"{design} attempt {attempt}; checked "
            + ", ".join(str(path) for path in candidates)
            + ". Add attempt_N.v or default.v under fixtures/llm_outputs. "
            "If this additional attempt was unexpected, inspect the previous attempt's "
            "first-failure stage and tool log for a validation regression."
        )


# Backwards-compatible import alias. Public documentation uses FixtureProvider.
MockProvider = FixtureProvider


class ReplayProvider(Provider):
    """Replay provenance-checked responses from an earlier genuine live run.

    The source may be either a complete GRADE-RTL run directory containing
    ``run_manifest.json`` or a compact bundle created by
    ``scripts/export_replay.py`` containing ``replay_manifest.json``.
    """

    name = "replay"
    execution_mode: ExecutionMode = "replay"
    response_origin = "recorded_live"
    test_fixture = False

    def __init__(
        self,
        source: Path,
        settings: GenerationSettings,
        *,
        expected_model: str | None = None,
    ) -> None:
        self.source = source.resolve()
        run_manifest = self.source / "run_manifest.json"
        bundle_manifest = self.source / "replay_manifest.json"
        if run_manifest.is_file():
            self.source_kind = "run"
            manifest_path = run_manifest
        elif bundle_manifest.is_file():
            self.source_kind = "bundle"
            manifest_path = bundle_manifest
        else:
            raise ConfigurationError(
                "Replay source must contain run_manifest.json or replay_manifest.json: "
                f"{self.source}"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid replay manifest: {manifest_path}") from exc
        if self.source_kind == "run":
            try:
                verify_run(self.source)
            except RunVerificationError as exc:
                raise ConfigurationError(
                    f"Replay source run failed provenance/hash verification: {exc}"
                ) from exc
            if manifest.get("schema_version") != 2:
                raise ConfigurationError(
                    "Replay run manifest must use schema_version 2; "
                    "rerun with GRADE-RTL v1.1.0 or later"
                )
            source_mode = str(manifest.get("execution_mode", ""))
            if source_mode not in {"live", "replay"}:
                raise ConfigurationError(
                    "Replay requires a provenance-enabled live or replay run. "
                    "Fixture/synthetic runs cannot be replayed as genuine LLM outputs."
                )
            if manifest.get("test_fixture") is True:
                raise ConfigurationError("Synthetic fixture runs cannot be used in replay mode")
            source_provider = str(manifest.get("provider", "")).strip()
            source_model = str(manifest.get("model", "")).strip()
            self.paper_eligible = bool(
                manifest.get("paper_result") is True
                and manifest.get("tool_mode") == "real"
                and manifest.get("provider_paper_eligible") is True
            )
            self.source_run_id = self.source.name
        else:
            if manifest.get("schema_version") != 1:
                raise ConfigurationError("Replay bundle must use schema_version 1")
            if manifest.get("origin") != "recorded_live":
                raise ConfigurationError(
                    "Replay bundle origin must be 'recorded_live'; synthetic fixtures are rejected"
                )
            source_provider = str(manifest.get("provider", "")).strip()
            source_model = str(manifest.get("model", "")).strip()
            self.paper_eligible = manifest.get("paper_eligible") is True
            self.source_run_id = str(manifest.get("source_run_id", self.source.name))
        if not source_provider or not source_model:
            raise ConfigurationError("Replay manifest is missing provider/model provenance")
        if expected_model and expected_model != source_model:
            raise ConfigurationError(
                f"Replay source model is {source_model!r}, not requested model {expected_model!r}"
            )
        self.source_manifest = manifest
        self.source_provider = source_provider
        super().__init__(source_model, settings)

    def provenance_metadata(self) -> dict[str, Any]:
        return {
            **super().provenance_metadata(),
            "replay_source_kind": self.source_kind,
            "replay_source_run": self.source_run_id,
            "replay_source_provider": self.source_provider,
            "replay_source_model": self.model,
            "replay_source_paper_result": self.paper_eligible,
        }

    def _generate_from_run(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        attempt_dir = self.source / design / f"attempt_{attempt}"
        prompt_path = attempt_dir / "prompt.txt"
        raw_path = attempt_dir / "raw_response.txt"
        metadata_path = attempt_dir / "generation_metadata.json"
        missing = [path.name for path in (prompt_path, raw_path, metadata_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"Replay source lacks {', '.join(missing)} for {design} attempt {attempt}: "
                f"{attempt_dir}"
            )
        try:
            source_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid replay metadata: {metadata_path}") from exc
        if source_metadata.get("test_fixture") is True:
            raise ConfigurationError("Synthetic fixture metadata cannot be replayed")
        if source_metadata.get("response_origin") not in {"live", "recorded_live"}:
            raise ConfigurationError(
                "Replay source lacks genuine live-response provenance. "
                "Create a new live run with GRADE-RTL v1.1.0 or later."
            )
        if source_metadata.get("provider") != self.source_provider:
            raise ConfigurationError(f"Replay provider mismatch in {metadata_path}")
        if source_metadata.get("model") != self.model:
            raise ConfigurationError(f"Replay model mismatch in {metadata_path}")
        if source_metadata.get("paper_eligible") is not True and self.paper_eligible:
            raise ConfigurationError(
                f"Replay source claims paper eligibility but attempt does not: {metadata_path}"
            )
        source_prompt = prompt_path.read_text(encoding="utf-8")
        source_prompt_hash = _sha256_text(source_prompt)
        recorded_prompt_hash = source_metadata.get("prompt_sha256")
        if recorded_prompt_hash and recorded_prompt_hash != source_prompt_hash:
            raise ConfigurationError(f"Replay prompt checksum mismatch in {metadata_path}")
        if _sha256_text(prompt) != source_prompt_hash:
            raise ConfigurationError(
                f"Replay prompt mismatch for {design} attempt {attempt}. "
                "Use the same prompts/configuration as the source run."
            )
        actual_response_hash = sha256_file(raw_path)
        recorded_response_hash = source_metadata.get("raw_response_sha256")
        if recorded_response_hash and recorded_response_hash != actual_response_hash:
            raise ConfigurationError(f"Replay response checksum mismatch in {metadata_path}")
        return self._response(
            raw_path.read_text(encoding="utf-8"),
            source_metadata=source_metadata,
            design=design,
            attempt=attempt,
            prompt_hash=source_prompt_hash,
            response_hash=actual_response_hash,
        )

    def _generate_from_bundle(
        self, prompt: str, *, design: str, attempt: int
    ) -> GenerationResponse:
        prompt_path = self.source / design / f"attempt_{attempt}.prompt.txt"
        response_path = self.source / design / f"attempt_{attempt}.txt"
        metadata_path = self.source / design / f"attempt_{attempt}.json"
        if not response_path.is_file() or not metadata_path.is_file():
            raise FileNotFoundError(
                f"Replay bundle lacks response/metadata for {design} attempt {attempt}: "
                f"{response_path.parent}"
            )
        try:
            source_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid replay metadata: {metadata_path}") from exc
        if source_metadata.get("schema_version") != 1:
            raise ConfigurationError(f"Replay attempt must use schema_version 1: {metadata_path}")
        if source_metadata.get("origin") != "recorded_live":
            raise ConfigurationError(f"Replay attempt origin is not recorded_live: {metadata_path}")
        if source_metadata.get("provider") != self.source_provider:
            raise ConfigurationError(f"Replay provider mismatch: {metadata_path}")
        if source_metadata.get("model") != self.model:
            raise ConfigurationError(f"Replay model mismatch: {metadata_path}")
        if source_metadata.get("design") != design or source_metadata.get("attempt") != attempt:
            raise ConfigurationError(f"Replay design/attempt mismatch: {metadata_path}")
        if source_metadata.get("paper_eligible") is not True and self.paper_eligible:
            raise ConfigurationError(
                f"Replay bundle is paper-eligible but attempt is not: {metadata_path}"
            )
        prompt_hash = _sha256_text(prompt)
        if prompt_path.is_file():
            archived_prompt = prompt_path.read_text(encoding="utf-8")
            archived_prompt_hash = _sha256_text(archived_prompt)
            if archived_prompt_hash != source_metadata.get("prompt_sha256"):
                raise ConfigurationError(f"Replay archived prompt hash mismatch: {prompt_path}")
            if archived_prompt != prompt:
                raise ConfigurationError(
                    f"Replay prompt mismatch for {design} attempt {attempt}"
                )
        if source_metadata.get("prompt_sha256") != prompt_hash:
            raise ConfigurationError(
                f"Replay prompt hash mismatch for {design} attempt {attempt}"
            )
        response_hash = sha256_file(response_path)
        if source_metadata.get("response_sha256") != response_hash:
            raise ConfigurationError(f"Replay response hash mismatch: {response_path}")
        return self._response(
            response_path.read_text(encoding="utf-8"),
            source_metadata=source_metadata,
            design=design,
            attempt=attempt,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
        )

    def _response(
        self,
        text: str,
        *,
        source_metadata: dict[str, Any],
        design: str,
        attempt: int,
        prompt_hash: str,
        response_hash: str,
    ) -> GenerationResponse:
        return GenerationResponse(
            text,
            {
                **source_metadata,
                "provider": "replay",
                "model": self.model,
                "execution_mode": "replay",
                "response_origin": "recorded_live",
                "paper_eligible": self.paper_eligible,
                "test_fixture": False,
                "replay_verified": True,
                "replay_source_kind": self.source_kind,
                "replay_source_run": self.source_run_id,
                "replay_source_provider": self.source_provider,
                "replay_source_model": self.model,
                "replay_source_attempt": attempt,
                "replay_design": design,
                "replay_prompt_sha256": prompt_hash,
                "replay_response_sha256": response_hash,
            },
        )

    def generate(self, prompt: str, *, design: str, attempt: int) -> GenerationResponse:
        if self.source_kind == "run":
            return self._generate_from_run(prompt, design=design, attempt=attempt)
        return self._generate_from_bundle(prompt, design=design, attempt=attempt)


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

    def preflight(self) -> None:
        self.require_key(self.api_key_env)

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

    def preflight(self) -> None:
        self.require_key("ANTHROPIC_API_KEY")

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
        text = "".join(
            str(block.get("text", "")) for block in blocks if block.get("type") == "text"
        )
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

    def preflight(self) -> None:
        self.require_key("GEMINI_API_KEY")

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
    fixture_root: Path | None = None,
) -> Provider:
    """Create a fixture or live provider.

    Replay mode is created explicitly with ReplayProvider because it requires a
    source run path rather than a provider endpoint.
    """
    normalized = name.lower()
    if normalized in {"fixture", "mock"}:
        root = fixture_root or repository_root / "fixtures" / "llm_outputs"
        return FixtureProvider(root, settings)
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
            endpoint=os.environ.get(
                "ANTHROPIC_ENDPOINT", "https://api.anthropic.com/v1/messages"
            ),
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
        f"Unknown provider {name!r}; choose fixture, ollama, openai, deepseek, "
        "anthropic, gemini, or huggingface"
    )
