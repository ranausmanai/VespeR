"""PTY controller for spawning and managing provider CLI processes."""

import asyncio
import json
import os
import signal
import sys
from typing import AsyncIterator, Optional, Callable, Awaitable
from pathlib import Path

from .provider_adapter import ensure_provider_available, get_provider_adapter
from .stream_parser import build_stream_parser
from ..events.types import Event, EventType, StreamEvent


class PTYController:
    """Spawns and controls Claude/Codex CLI processes for real-time streaming."""

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

        self._process: Optional[asyncio.subprocess.Process] = None
        self._parser = build_stream_parser(self._model_spec.provider, session_id, run_id)
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._terminated = False

        # Callbacks
        self._on_event: Optional[Callable[[Event], Awaitable[None]]] = None

    def set_event_callback(self, callback: Callable[[Event], Awaitable[None]]) -> None:
        """Set callback for events."""
        self._on_event = callback

    async def start(self, prompt: str) -> AsyncIterator[Event]:
        """Start the configured provider CLI with streaming output."""
        ensure_provider_available(self.model)
        cmd = self._build_command(prompt)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=self._get_env(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{self._adapter.executable} is not installed or not on PATH") from exc

        # Emit run started event
        start_event = Event(
            type=EventType.RUN_STARTED,
            session_id=self.session_id,
            run_id=self.run_id,
            payload={
                "prompt": prompt,
                "model": self.model,
                "provider": self._model_spec.provider,
                "pid": self._process.pid,
            }
        )
        yield start_event
        if self._on_event:
            await self._on_event(start_event)

        # Stream stdout
        try:
            async for event in self._stream_output():
                yield event
                if self._on_event:
                    await self._on_event(event)
        except asyncio.CancelledError:
            await self.terminate()
            raise

        # Wait for process to complete
        return_code = await self._process.wait()

        # Emit completion event
        if return_code == 0:
            end_event = Event(
                type=EventType.RUN_COMPLETED,
                session_id=self.session_id,
                run_id=self.run_id,
                payload={"return_code": return_code}
            )
        else:
            stderr = ""
            if self._process.stderr:
                stderr_bytes = await self._process.stderr.read()
                stderr = stderr_bytes.decode("utf-8", errors="replace")

            end_event = Event(
                type=EventType.RUN_FAILED,
                session_id=self.session_id,
                run_id=self.run_id,
                payload={"return_code": return_code, "stderr": stderr}
            )

        yield end_event
        if self._on_event:
            await self._on_event(end_event)

    def _build_command(self, prompt: str) -> list[str]:
        """Build the provider CLI command."""
        return self._adapter.build_run_command(prompt, self._model_spec)

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for subprocess."""
        env = os.environ.copy()
        env.update(self._adapter.build_env_overrides())
        return env

    async def _stream_output(self) -> AsyncIterator[Event]:
        """Stream and parse output from the configured provider."""
        if not self._process or not self._process.stdout:
            return

        while True:
            # Check if paused
            await self._pause_event.wait()

            if self._terminated:
                break

            # Read line by line; both Claude and Codex emit JSON lines here.
            try:
                line_bytes = await self._process.stdout.readline()
            except Exception:
                break

            if not line_bytes:
                # EOF reached
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if line:
                event = self._parser.parse_line(line)
                if event:
                    yield event

    async def pause(self) -> None:
        """Pause the provider process."""
        if self._process and self._process.returncode is None and not self._paused:
            self._paused = True
            self._pause_event.clear()

            # Send SIGSTOP on Unix
            if sys.platform != "win32":
                try:
                    os.kill(self._process.pid, signal.SIGSTOP)
                except ProcessLookupError:
                    pass

    async def resume(self) -> None:
        """Resume the provider process."""
        if self._process and self._paused:
            # Send SIGCONT on Unix
            if sys.platform != "win32":
                try:
                    os.kill(self._process.pid, signal.SIGCONT)
                except ProcessLookupError:
                    pass

            self._paused = False
            self._pause_event.set()

    async def inject_input(self, message: str) -> None:
        """Inject input into the provider's stdin.

        Note: Currently not supported since we use DEVNULL for stdin to prevent
        CLI blocking. Future versions may implement this via PTY.
        """
        # TODO: Implement input injection via PTY or named pipe
        pass

    async def terminate(self) -> None:
        """Terminate the provider process."""
        self._terminated = True
        self._pause_event.set()  # Unblock if paused

        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                # Give it a moment to terminate gracefully
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass

    @property
    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self._process is not None and self._process.returncode is None

    @property
    def is_paused(self) -> bool:
        """Check if the process is paused."""
        return self._paused

    @property
    def pid(self) -> Optional[int]:
        """Get the process ID."""
        return self._process.pid if self._process else None
