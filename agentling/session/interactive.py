"""Interactive session controller for Claude/Codex conversation continuity."""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, Callable, Awaitable

from .provider_adapter import ensure_provider_available, get_provider_adapter
from .stream_parser import build_stream_parser
from ..events.types import Event, EventType, StreamEvent


class InteractiveSession:
    """Manages an interactive provider session using provider-native resume support."""

    def __init__(
        self,
        session_id: str,
        run_id: str,
        working_dir: str,
        model: str = "claude:sonnet",
    ):
        self.session_id = session_id
        self.run_id = run_id
        self.working_dir = Path(working_dir).resolve()
        self.model = model
        self._model_spec, self._adapter = get_provider_adapter(model)
        self._conversation_id = str(uuid.uuid4()) if self._model_spec.provider == "claude" else None
        self._parser = build_stream_parser(self._model_spec.provider, session_id, run_id)
        self._is_running = False
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._turn_count = 0
        self._history: list[tuple[str, str]] = []

        # Callbacks
        self._on_event: Optional[Callable[[Event], Awaitable[None]]] = None

    def set_event_callback(self, callback: Callable[[Event], Awaitable[None]]) -> None:
        """Set callback for events."""
        self._on_event = callback

    async def initialize(self) -> Event:
        """Initialize the interactive session (emits start event)."""
        ensure_provider_available(self.model)
        self._is_running = True

        start_event = Event(
            type=EventType.RUN_STARTED,
            session_id=self.session_id,
            run_id=self.run_id,
            payload={
                "model": self.model,
                "interactive": True,
                "provider": self._model_spec.provider,
                "conversation_id": self._conversation_id,
            }
        )

        if self._on_event:
            await self._on_event(start_event)

        return start_event

    async def send_message(self, message: str) -> AsyncIterator[Event]:
        """Send a message and stream the response."""
        if not self._is_running:
            raise RuntimeError("Session not running")

        self._turn_count += 1

        # Emit user message event
        user_event = StreamEvent(
            type=EventType.STREAM_USER,
            session_id=self.session_id,
            run_id=self.run_id,
            role="user",
            content=message,
            payload={"turn": self._turn_count}
        )
        yield user_event
        if self._on_event:
            await self._on_event(user_event)

        effective_message = self._prepare_message(message)
        cmd = self._build_command(effective_message)
        assistant_parts: list[str] = []

        # Start process
        try:
            self._current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=self._get_env(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{self._adapter.executable} is not installed or not on PATH") from exc

        # Stream response
        try:
            async for event in self._stream_response():
                self._ingest_conversation_event(event)
                if event.type == EventType.STREAM_ASSISTANT and getattr(event, "content", ""):
                    assistant_parts.append(event.content)
                yield event
                if self._on_event:
                    await self._on_event(event)
        finally:
            if self._current_process:
                return_code = await self._current_process.wait()
                stderr_text = ""
                if self._current_process.stderr:
                    stderr_bytes = await self._current_process.stderr.read()
                    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                self._current_process = None
                if return_code != 0:
                    raise RuntimeError(stderr_text or f"{self._adapter.executable} exited with code {return_code}")

        assistant_text = "".join(assistant_parts).strip()
        self._record_turn(message, assistant_text)

    async def _stream_response(self) -> AsyncIterator[Event]:
        """Stream and parse response from the configured provider."""
        if not self._current_process or not self._current_process.stdout:
            return

        while True:
            try:
                line_bytes = await self._current_process.stdout.readline()
            except Exception:
                break

            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if line:
                event = self._parser.parse_line(line)
                if event:
                    yield event

    def _build_command(self, message: str) -> list[str]:
        """Build the provider-specific interactive command."""
        return self._adapter.build_interactive_command(
            message,
            self._model_spec,
            turn_count=self._turn_count,
            conversation_id=self._conversation_id,
        )

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for subprocess."""
        env = os.environ.copy()
        env.update(self._adapter.build_env_overrides())
        return env

    def _prepare_message(self, message: str) -> str:
        if self._model_spec.provider != "codex" or not self._history:
            return message

        recent_turns = self._history[-8:]
        transcript = "\n\n".join(
            f"{role.title()}:\n{text}" for role, text in recent_turns if text.strip()
        )
        return (
            "Continue this coding conversation. Treat the transcript as prior context.\n\n"
            f"{transcript}\n\n"
            f"User:\n{message}"
        )

    def _record_turn(self, user_message: str, assistant_message: str) -> None:
        if self._model_spec.provider != "codex":
            return
        self._history.append(("user", user_message))
        if assistant_message:
            self._history.append(("assistant", assistant_message))
        self._history = self._history[-16:]

    def _ingest_conversation_event(self, event: Event) -> None:
        payload = event.payload or {}
        if self._model_spec.provider == "codex":
            thread_id = (
                payload.get("thread_id")
                or payload.get("id")
                or payload.get("thread", {}).get("id")
            )
            if isinstance(thread_id, str) and thread_id:
                self._conversation_id = thread_id

    async def terminate(self) -> None:
        """Terminate the session."""
        self._is_running = False

        if self._current_process and self._current_process.returncode is None:
            try:
                self._current_process.terminate()
                try:
                    await asyncio.wait_for(self._current_process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._current_process.kill()
                    await self._current_process.wait()
            except ProcessLookupError:
                pass

    async def interrupt_current_response(self) -> bool:
        """Interrupt the currently running turn while keeping the session alive."""
        if not self._current_process or self._current_process.returncode is not None:
            return False

        try:
            self._current_process.terminate()
            try:
                await asyncio.wait_for(self._current_process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._current_process.kill()
                await self._current_process.wait()
            finally:
                self._current_process = None
        except ProcessLookupError:
            self._current_process = None

        return True

    @property
    def is_running(self) -> bool:
        """Check if the session is active."""
        return self._is_running

    @property
    def pid(self) -> Optional[int]:
        """Get current process ID if running."""
        return self._current_process.pid if self._current_process else None

    @property
    def conversation_id(self) -> Optional[str]:
        """Get the provider-native conversation/thread identifier."""
        return self._conversation_id
