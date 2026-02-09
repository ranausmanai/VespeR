from __future__ import annotations

import asyncio
import shlex

from agentling.providers.base import BaseProvider, ProviderError, ProviderResponse


class CLIProvider(BaseProvider):
    def __init__(self, command: str) -> None:
        self.command = command

    async def generate(self, prompt: str, *, max_tokens: int, timeout_s: int, temperature: float) -> ProviderResponse:
        cmd_text = self.command.replace("{prompt}", shlex.quote(prompt))
        if "{prompt}" not in self.command:
            cmd_text = f"{cmd_text} {shlex.quote(prompt)}"

        proc = await asyncio.create_subprocess_shell(
            cmd_text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as exc:
            proc.kill()
            raise ProviderError(f"Provider command timed out after {timeout_s}s") from exc

        if proc.returncode != 0:
            raise ProviderError(stderr.decode("utf-8", errors="replace") or "Provider command failed")

        text = stdout.decode("utf-8", errors="replace").strip()
        tokens_in = _rough_tokens(prompt)
        tokens_out = _rough_tokens(text)
        return ProviderResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out)


def _rough_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.33))
