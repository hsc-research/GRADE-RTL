from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from llm_rtl_eval.doctor import inspect_environment

ROOT = Path(__file__).resolve().parents[1]


def test_doctor_accepts_repository_without_requiring_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = shutil.which

    def which(name: str):
        if name in {"iverilog", "yosys"}:
            return None
        return original(name)

    monkeypatch.setattr(shutil, "which", which)
    checks, errors = inspect_environment(ROOT, require_tools=False)
    assert errors == 0
    assert any(check.status == "WARN" and check.label == "iverilog" for check in checks)


def test_doctor_requires_real_tools_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = shutil.which

    def which(name: str):
        if name in {"iverilog", "yosys"}:
            return None
        return original(name)

    monkeypatch.setattr(shutil, "which", which)
    _, errors = inspect_environment(ROOT, require_tools=True)
    assert errors == 2


def test_doctor_checks_live_provider_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    _, errors = inspect_environment(ROOT, provider="openai")
    assert errors == 2
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "model-x")
    checks, errors = inspect_environment(ROOT, provider="openai")
    assert errors == 0
    assert any(check.label == "openai model" and check.status == "PASS" for check in checks)


def test_doctor_accepts_model_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    checks, errors = inspect_environment(ROOT, provider="openai", model="model-x")
    assert errors == 0
    assert any(check.label == "openai model" and check.detail == "model-x" for check in checks)
