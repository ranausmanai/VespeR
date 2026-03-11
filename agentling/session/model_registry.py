"""Shared model/provider helpers for Claude and Codex support."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_PROVIDER = "claude"
DEFAULT_MODEL = "sonnet"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    provider: str
    model: str
    raw: str


def parse_model_spec(raw: str | None) -> ModelSpec:
    """Parse a stored model string into provider + concrete model name."""
    normalized = (raw or "").strip()
    if not normalized:
        normalized = f"{DEFAULT_PROVIDER}:{DEFAULT_MODEL}"

    if ":" in normalized:
        provider, model = normalized.split(":", 1)
        provider = provider.strip().lower() or DEFAULT_PROVIDER
        model = model.strip() or DEFAULT_MODEL
        return ModelSpec(provider=provider, model=model, raw=f"{provider}:{model}")

    provider = infer_provider_from_model(normalized)
    return ModelSpec(provider=provider, model=normalized, raw=f"{provider}:{normalized}")


def infer_provider_from_model(model: str | None) -> str:
    normalized = (model or "").strip().lower()
    if not normalized:
        return DEFAULT_PROVIDER
    if "codex" in normalized or normalized.startswith(("gpt-5", "gpt-4.1")):
        return "codex"
    return "claude"


def format_model_spec(provider: str, model: str) -> str:
    normalized_provider = (provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    normalized_model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return f"{normalized_provider}:{normalized_model}"


def supports_native_resume(provider: str) -> bool:
    return provider in {"claude", "codex"}
