from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    async def generate(self, prompt: str, *, max_tokens: int, timeout_s: int, temperature: float) -> ProviderResponse:
        raise NotImplementedError
