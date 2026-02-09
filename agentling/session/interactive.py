"""Interactive session controller using Claude's --resume for conversation continuity."""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, Callable, Awaitable

from .stream_parser import ClaudeStreamParser
from ..events.types import Event, EventType, StreamEvent


class InteractiveSession:
    """Manages an interactive Claude Code session using --resume for multi-turn."""

    def __init__(
        self,
        session_id: str,
        run_id: str,
        working_dir: str,
        model: str = "sonnet",
    ):
        self.session_id = session_id
        self.run_id = run_id
        self.working_dir = Path(working_dir).resolve()
        self.model = model

        # Generate a unique Claude session ID for conversation continuity
        self._claude_session_id = str(uuid.uuid4())

        self._parser = ClaudeStreamParser(session_id, run_id)
        self._is_running = False
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._turn_count = 0

        # Callbacks
        self._on_event: Optional[Callable[[Event], Awaitable[None]]] = None

    def set_event_callback(self, callback: Callable[[Event], Awaitable[None]]) -> None:
        """Set callback for events."""
        self._on_event = callback

    async def initialize(self) -> Event:
        """Initialize the interactive session (emits start event)."""
        self._is_running = True

        start_event = Event(
            type=EventType.RUN_STARTED,
            session_id=self.session_id,
            run_id=self.run_id,
            payload={
                "model": self.model,
                "interactive": True,
                "claude_session_id": self._claude_session_id
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

        # Build command - use --resume for subsequent messages
        cmd = self._build_command(message)

        # Start process
        self._current_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.working_dir),
            env=self._get_env(),
        )

        # Stream response
        try:
            async for event in self._stream_response():
                yield event
                if self._on_event:
                    await self._on_event(event)
        finally:
            if self._current_process:
                await self._current_process.wait()
                self._current_process = None

    async def _stream_response(self) -> AsyncIterator[Event]:
        """Stream and parse response from Claude."""
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
        """Build the Claude CLI command."""
        cmd = [
            "claude",
            "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--model", self.model,
            "--dangerously-skip-permissions",
        ]

        # First message: use --session-id to establish the session
        # Subsequent messages: use --resume to continue the conversation
        if self._turn_count == 1:
            cmd.extend(["--session-id", self._claude_session_id])
        else:
            cmd.extend(["--resume", self._claude_session_id])

        cmd.append(message)
        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for subprocess."""
        env = os.environ.copy()
        env["CLAUDE_CODE_NONINTERACTIVE"] = "1"
        return env

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
        """Interrupt the currently running Claude turn, keeping session alive."""
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
    def claude_session_id(self) -> str:
        """Get the Claude session ID for conversation continuity."""
        return self._claude_session_id
