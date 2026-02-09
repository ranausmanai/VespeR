from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from agentling.providers.base import BaseProvider, ProviderError, ProviderResponse


class OllamaProvider(BaseProvider):
    def __init__(self, model: str, endpoint: str | None = None) -> None:
        self.model = model
        self.endpoint = endpoint or "http://127.0.0.1:11434/api/generate"

    async def generate(self, prompt: str, *, max_tokens: int, timeout_s: int, temperature: float) -> ProviderResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        def _request() -> ProviderResponse:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise ProviderError(f"Ollama HTTPError: {exc.code} {details}") from exc
            except urllib.error.URLError as exc:
                raise ProviderError(f"Ollama connection failed: {exc}") from exc

            return ProviderResponse(
                text=body.get("response", ""),
                tokens_in=int(body.get("prompt_eval_count", 0)),
                tokens_out=int(body.get("eval_count", 0)),
            )

        return await asyncio.to_thread(_request)
