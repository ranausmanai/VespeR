from __future__ import annotations

from agentling.models import ProviderConfig
from agentling.providers.base import BaseProvider
from agentling.providers.cli_provider import CLIProvider
from agentling.providers.ollama_provider import OllamaProvider
from agentling.providers.openai_provider import OpenAIProvider


def build_provider(cfg: ProviderConfig) -> BaseProvider:
    ptype = cfg.type.lower()
    if ptype == "openai":
        return OpenAIProvider(model=cfg.model, endpoint=cfg.endpoint)
    if ptype == "ollama":
        return OllamaProvider(model=cfg.model, endpoint=cfg.endpoint)
    if ptype == "claude_code":
        command = cfg.command or "claude --print {prompt}"
        return CLIProvider(command=command)
    if ptype == "codex_cli":
        command = cfg.command or "codex run {prompt}"
        return CLIProvider(command=command)

    if cfg.command:
        return CLIProvider(command=cfg.command)
    raise ValueError(f"Unsupported provider type: {cfg.type}")
