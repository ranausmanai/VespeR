"""Provider-specific command building and availability checks."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .model_registry import ModelSpec, parse_model_spec


EXECUTABLE_ENV_VARS = {
    "claude": ("AGENTLING_CLAUDE_BIN", "CLAUDE_BIN"),
    "codex": ("AGENTLING_CODEX_BIN", "CODEX_BIN"),
}


def _resolve_provider_executable(provider: str) -> str | None:
    for env_name in EXECUTABLE_ENV_VARS.get(provider, ()):
        candidate = os.environ.get(env_name)
        if candidate:
            resolved = shutil.which(candidate) or candidate
            if Path(resolved).exists():
                return resolved

    executable = "codex" if provider == "codex" else "claude"
    resolved = shutil.which(executable)
    if provider == "codex":
        resolved = _resolve_real_codex_path(resolved)
    return resolved


def _resolve_real_codex_path(path: str | None) -> str | None:
    if not path:
        return None

    if not _looks_like_opticode_wrapper(path):
        return path

    wrapper_path = str(Path(path).resolve())
    npm_prefix = _run_capture(["npm", "config", "get", "prefix"])
    candidates: list[str] = []

    if npm_prefix:
        candidates.append(str(Path(npm_prefix) / "bin" / "codex"))

    candidates.extend([
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        "/usr/bin/codex",
    ])

    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            continue
        try:
            resolved = str(candidate_path.resolve())
        except OSError:
            continue
        if resolved == wrapper_path:
            continue
        if _looks_like_opticode_wrapper(resolved):
            continue
        if os.access(resolved, os.X_OK):
            return resolved

    return path


def _looks_like_opticode_wrapper(path: str) -> bool:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "opticode run --tool codex" in text


def _run_capture(cmd: list[str]) -> str | None:
    try:
        result = shutil.which(cmd[0])
        if not result:
            return None
        import subprocess

        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    output = (completed.stdout or "").strip()
    return output or None


@dataclass(frozen=True, slots=True)
class ProviderAdapter:
    provider: str
    executable: str

    def build_run_command(self, prompt: str, spec: ModelSpec) -> list[str]:
        if self.provider == "claude":
            return [
                self.executable,
                "-p",
                "--verbose",
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--model", spec.model,
                "--dangerously-skip-permissions",
                prompt,
            ]

        if self.provider == "codex":
            return [
                self.executable,
                "exec",
                "--json",
                "-s", "danger-full-access",
                "--skip-git-repo-check",
                "--model", spec.model,
                prompt,
            ]

        raise ValueError(f"Unsupported provider: {self.provider}")

    def build_interactive_command(
        self,
        message: str,
        spec: ModelSpec,
        *,
        turn_count: int,
        conversation_id: str | None,
    ) -> list[str]:
        if self.provider == "claude":
            cmd = [
                self.executable,
                "-p",
                "--verbose",
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--model", spec.model,
                "--dangerously-skip-permissions",
            ]
            if conversation_id:
                if turn_count == 1:
                    cmd.extend(["--session-id", conversation_id])
                else:
                    cmd.extend(["--resume", conversation_id])
            cmd.append(message)
            return cmd

        if self.provider == "codex":
            return [
                self.executable,
                "exec",
                "--json",
                "-s", "danger-full-access",
                "--skip-git-repo-check",
                "--model", spec.model,
                message,
            ]

        raise ValueError(f"Unsupported provider: {self.provider}")

    def build_env_overrides(self) -> dict[str, str]:
        if self.provider == "claude":
            return {"CLAUDE_CODE_NONINTERACTIVE": "1"}
        return {}


def get_provider_adapter(model_spec: str | None) -> tuple[ModelSpec, ProviderAdapter]:
    spec = parse_model_spec(model_spec)
    executable = _resolve_provider_executable(spec.provider) or ("codex" if spec.provider == "codex" else "claude")
    return spec, ProviderAdapter(provider=spec.provider, executable=executable)


def ensure_provider_available(model_spec: str | None) -> None:
    spec, adapter = get_provider_adapter(model_spec)
    if Path(adapter.executable).exists() or shutil.which(adapter.executable):
        return

    if spec.provider == "codex":
        raise RuntimeError("Codex CLI is not installed or not on PATH.")
    raise RuntimeError("Claude CLI is not installed or not on PATH.")
