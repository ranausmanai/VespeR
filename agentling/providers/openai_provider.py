from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from agentling.providers.base import BaseProvider, ProviderError, ProviderResponse


class OpenAIProvider(BaseProvider):
    def __init__(self, model: str, endpoint: str | None = None) -> None:
        self.model = model
        self.endpoint = endpoint or "https://api.openai.com/v1/responses"

    async def generate(self, prompt: str, *, max_tokens: int, timeout_s: int, temperature: float) -> ProviderResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set")

        payload = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }

        def _request() -> ProviderResponse:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise ProviderError(f"OpenAI HTTPError: {exc.code} {details}") from exc
            except urllib.error.URLError as exc:
                raise ProviderError(f"OpenAI connection failed: {exc}") from exc

            text = body.get("output_text", "")
            usage = body.get("usage", {})
            return ProviderResponse(
                text=text,
                tokens_in=int(usage.get("input_tokens", 0)),
                tokens_out=int(usage.get("output_tokens", 0)),
            )

        return await asyncio.to_thread(_request)
