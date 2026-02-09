"""Session manager for coordinating Claude Code runs with event tracking."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncIterator, Callable, Awaitable

from .pty_controller import PTYController
from .interactive import InteractiveSession
from .git_tracker import GitTracker
from ..events.types import Event, EventType
from ..events.bus import EventBus
from ..persistence.database import Database
from ..persistence.repositories import Session, Run


class SessionManager:
    """Manages Claude Code sessions with full observability."""

    def __init__(self, database: Database, event_bus: Optional[EventBus] = None):
        self.db = database
        self.event_bus = event_bus or EventBus(database.events)

        # Active runs (one-shot)
        self._active_runs: dict[str, PTYController] = {}
        self._git_trackers: dict[str, GitTracker] = {}

        # Interactive sessions
        self._interactive_sessions: dict[str, InteractiveSession] = {}
        self._interactive_tasks: dict[str, asyncio.Task] = {}

    async def _create_interactive_snapshot(self, run_id: str) -> None:
        """Create a resumable summary snapshot for an ended interactive run."""
        run = await self.db.runs.get(run_id)
        if not run or not self.db.session_snapshots:
            return

        existing = await self.db.session_snapshots.get_for_run(run_id)
        if existing:
            return

        def _clean_line(text: str, max_len: int = 260) -> str:
            cleaned = " ".join((text or "").split())
            if len(cleaned) <= max_len:
                return cleaned
            return cleaned[: max_len - 3].rstrip() + "..."

        def _bullet(items: list[str], limit: int) -> str:
            if not items:
                return "- None"
            return "\n".join(f"- {item}" for item in items[:limit])

        def _normalize_command(command: str) -> str:
            cmd = (command or "").strip()
            if not cmd:
                return ""
            # Do not leak heredoc/file bodies into resume snapshots.
            if "<<" in cmd:
                first_line = cmd.splitlines()[0].strip()
                return _clean_line(f"{first_line} [heredoc body omitted]", max_len=220)
            first_line = cmd.splitlines()[0].strip()
            return _clean_line(first_line, max_len=220)

        first_goal = ""
        recent_user_goals: list[str] = []
        touched_files: list[str] = []
        touched_seen: set[str] = set()
        commands: list[str] = []
        command_seen: set[str] = set()
        latest_assistant_parts: list[str] = []
        latest_assistant_text = ""
        last_assistant_messages: list[str] = []
        error_count = 0
        test_commands: list[str] = []
        read_count = 0
        edit_count = 0
        write_count = 0

        async for event in self.db.events.get_events_for_run(run_id, from_sequence=0):
            event_type = event.get("type")
            payload = event.get("payload", {}) or {}

            if event_type == EventType.STREAM_USER.value:
                content = str(event.get("content") or payload.get("content") or "").strip()
                if content and not content.startswith("[Agent"):
                    if not first_goal:
                        first_goal = content
                    recent_user_goals.append(_clean_line(content, max_len=180))
                    if len(recent_user_goals) > 5:
                        recent_user_goals = recent_user_goals[-5:]
                    latest_assistant_parts = []

            if event_type == EventType.STREAM_ASSISTANT.value:
                content = str(event.get("content") or payload.get("content") or "")
                if content:
                    latest_assistant_parts.append(content)

            if event_type == EventType.STREAM_RESULT.value and latest_assistant_parts:
                latest_assistant_text = _clean_line("".join(latest_assistant_parts), max_len=420)
                if latest_assistant_text:
                    last_assistant_messages.append(latest_assistant_text)
                    if len(last_assistant_messages) > 3:
                        last_assistant_messages = last_assistant_messages[-3:]

            if event_type == EventType.STREAM_TOOL_USE.value:
                tool_name = str(event.get("tool_name") or payload.get("name") or "")
                tool_input = event.get("tool_input") or payload.get("input") or {}
                if isinstance(tool_input, dict):
                    if tool_name in {"Glob", "Grep", "Read"}:
                        read_count += 1
                    if tool_name == "Edit":
                        edit_count += 1
                    if tool_name == "Write":
                        write_count += 1

                    path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
                    if path and path not in touched_seen:
                        touched_seen.add(path)
                        touched_files.append(path)
                    if tool_name == "Bash":
                        command = str(tool_input.get("command") or "").strip()
                        normalized_command = _normalize_command(command)
                        if normalized_command and normalized_command not in command_seen:
                            command_seen.add(normalized_command)
                            commands.append(normalized_command)
                            if any(x in command for x in ("test", "pytest", "jest", "vitest", "go test")):
                                test_commands.append(normalized_command)

            if event_type in {EventType.STREAM_ERROR.value, EventType.RUN_FAILED.value}:
                error_count += 1

        summary = {
            "goal": _clean_line(first_goal, max_len=300),
            "status": run.status,
            "files_touched": touched_files[:20],
            "commands": commands[:20],
            "test_commands": test_commands[:10],
            "error_count": error_count,
            "last_assistant_summary": _clean_line(latest_assistant_text, max_len=800),
            "recent_user_goals": recent_user_goals[-3:],
            "assistant_outcomes": last_assistant_messages[-2:],
            "phase_counts": {
                "read_ops": read_count,
                "write_ops": write_count,
                "edit_ops": edit_count,
            },
        }

        phases: list[str] = []
        if read_count > 0:
            phases.append("Exploration")
        if write_count > 0 or edit_count > 0:
            phases.append("Implementation")
        if test_commands:
            phases.append("Validation")
        if error_count > 0:
            phases.append("Error handling")

        next_step = "Continue from the latest completed step and run a quick verification."
        if run.status == "failed" or error_count > 0:
            next_step = "Address the most recent error first, then rerun the smallest relevant verification command."
        elif test_commands:
            next_step = "Re-run targeted tests for changed files, then finalize any remaining polish."
        elif touched_files:
            next_step = "Review touched files for correctness and run one lightweight validation command."

        resume_prompt = (
            "Resume this previously ended coding session with smart context.\n\n"
            "Objective:\n"
            f"{summary['goal'] or '(No explicit objective captured)'}\n\n"
            "Session state:\n"
            f"- Status: {run.status}\n"
            f"- Workflow phases observed: {', '.join(phases) if phases else 'Unknown'}\n"
            f"- Errors observed: {error_count}\n\n"
            "Recent user intent:\n"
            f"{_bullet(summary['recent_user_goals'], limit=3)}\n\n"
            "Key artifacts touched:\n"
            f"{_bullet(summary['files_touched'], limit=10)}\n\n"
            "Important commands run:\n"
            f"{_bullet(summary['commands'][:8], limit=8)}\n\n"
            "Latest assistant outcome:\n"
            f"{summary['last_assistant_summary'] or '(No final assistant outcome captured)'}\n\n"
            "Continue from here:\n"
            f"- {next_step}\n"
            "- Reuse existing files/artifacts before creating new ones.\n"
            "- Avoid repeating already completed steps unless verification fails."
        )

        await self.db.session_snapshots.create(
            run_id=run_id,
            session_id=run.session_id,
            goal=summary["goal"] or None,
            summary=summary,
            resume_prompt=resume_prompt,
        )

    @staticmethod
    def _extract_result_usage(event: Event) -> tuple[int, int]:
        """Extract token usage only from finalized result events."""
        if event.type != EventType.STREAM_RESULT:
            return 0, 0
        payload = event.payload or {}
        if payload.get("type") != "result":
            return 0, 0

        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            return 0, 0

        try:
            tokens_in = int(usage.get("input_tokens", 0) or 0)
            tokens_out = int(usage.get("output_tokens", 0) or 0)
        except (TypeError, ValueError):
            return 0, 0

        return tokens_in, tokens_out

    async def get_or_create_session(
        self,
        working_dir: Path,
        name: Optional[str] = None
    ) -> Session:
        """Get existing session for working dir or create new one."""
        working_dir = working_dir.resolve()

        # Try to find existing session
        session = await self.db.sessions.get_by_working_dir(str(working_dir))
        if session:
            return session

        # Create new session
        session = await self.db.sessions.create(
            working_dir=str(working_dir),
            name=name or working_dir.name
        )

        # Note: We don't emit a session event here since it's not part of a run
        # Session lifecycle is tracked in the sessions table directly

        return session

    async def start_run(
        self,
        session_id: str,
        prompt: str,
        model: str = "sonnet",
        parent_run_id: Optional[str] = None,
        branch_point_event_id: Optional[str] = None
    ) -> Run:
        """Start a new Claude Code run."""
        # Get session
        session = await self.db.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Create run record
        run = await self.db.runs.create(
            session_id=session_id,
            prompt=prompt,
            model=model,
            parent_run_id=parent_run_id,
            branch_point_event_id=branch_point_event_id
        )

        # Initialize git tracker
        git_tracker = GitTracker(session.working_dir, session_id, run.id)
        self._git_trackers[run.id] = git_tracker

        # Take initial git snapshot
        snapshot = await git_tracker.snapshot()
        await self.event_bus.publish(snapshot)

        # Create PTY controller
        controller = PTYController(
            session_id=session_id,
            run_id=run.id,
            working_dir=session.working_dir,
            model=model
        )
        self._active_runs[run.id] = controller

        # Update run status
        await self.db.runs.update_status(run.id, "running")

        return run

    async def stream_events(self, run_id: str) -> AsyncIterator[Event]:
        """Stream events from a running Claude session."""
        controller = self._active_runs.get(run_id)
        if not controller:
            raise ValueError(f"No active run {run_id}")

        run = await self.db.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        git_tracker = self._git_trackers.get(run_id)
        start_time = datetime.utcnow()

        try:
            async for event in controller.start(run.prompt):
                # Publish to event bus
                await self.event_bus.publish(event)
                yield event

                # Track token usage on finalized result events.
                tokens_in, tokens_out = self._extract_result_usage(event)
                if tokens_in or tokens_out:
                    await self.db.runs.update_metrics(
                        run_id,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out
                    )

                # Take git snapshot on tool results
                if git_tracker and event.type == EventType.STREAM_TOOL_RESULT:
                    snapshot = await git_tracker.snapshot()
                    await self.event_bus.publish(snapshot)
                    yield snapshot

            # Run completed
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self.db.runs.update_metrics(run_id, duration_ms=duration_ms)
            await self.db.runs.update_status(run_id, "completed")

        except Exception as e:
            await self.db.runs.update_status(run_id, "failed", str(e))
            raise
        finally:
            # Cleanup
            self._active_runs.pop(run_id, None)
            self._git_trackers.pop(run_id, None)

    async def pause_run(self, run_id: str) -> bool:
        """Pause a running Claude session."""
        controller = self._active_runs.get(run_id)
        if not controller:
            return False

        await controller.pause()
        await self.db.runs.update_status(run_id, "paused")

        await self.event_bus.publish(Event(
            type=EventType.RUN_PAUSED,
            session_id=controller.session_id,
            run_id=run_id,
            payload={}
        ))

        return True

    async def resume_run(self, run_id: str) -> bool:
        """Resume a paused Claude session."""
        controller = self._active_runs.get(run_id)
        if not controller:
            return False

        await controller.resume()
        await self.db.runs.update_status(run_id, "running")

        await self.event_bus.publish(Event(
            type=EventType.RUN_RESUMED,
            session_id=controller.session_id,
            run_id=run_id,
            payload={}
        ))

        return True

    async def inject_message(self, run_id: str, message: str) -> bool:
        """Inject a user message into a running session."""
        controller = self._active_runs.get(run_id)
        if not controller:
            return False

        await controller.inject_input(message)

        await self.event_bus.publish(Event(
            type=EventType.INTERVENTION_INJECT,
            session_id=controller.session_id,
            run_id=run_id,
            payload={"message": message}
        ))

        return True

    async def abort_run(self, run_id: str) -> bool:
        """Abort a running Claude session."""
        controller = self._active_runs.get(run_id)
        if not controller:
            return False

        await controller.terminate()
        await self.db.runs.update_status(run_id, "failed", "Aborted by user")

        await self.event_bus.publish(Event(
            type=EventType.INTERVENTION_ABORT,
            session_id=controller.session_id,
            run_id=run_id,
            payload={}
        ))

        self._active_runs.pop(run_id, None)
        self._git_trackers.pop(run_id, None)

        return True

    async def branch_run(
        self,
        run_id: str,
        from_event_id: str,
        modified_prompt: Optional[str] = None
    ) -> Run:
        """Create a new run branching from a specific event."""
        original_run = await self.db.runs.get(run_id)
        if not original_run:
            raise ValueError(f"Run {run_id} not found")

        # Get the event to branch from
        event = await self.db.events.get(from_event_id)
        if not event:
            raise ValueError(f"Event {from_event_id} not found")

        # Use modified prompt or original
        prompt = modified_prompt or original_run.prompt

        # Create branched run
        new_run = await self.start_run(
            session_id=original_run.session_id,
            prompt=prompt,
            model=original_run.model or "sonnet",
            parent_run_id=run_id,
            branch_point_event_id=from_event_id
        )

        await self.event_bus.publish(Event(
            type=EventType.RUN_BRANCHED,
            session_id=original_run.session_id,
            run_id=new_run.id,
            payload={
                "parent_run_id": run_id,
                "branch_point_event_id": from_event_id,
                "modified_prompt": modified_prompt
            }
        ))

        return new_run

    async def get_run_status(self, run_id: str) -> dict:
        """Get current status of a run."""
        run = await self.db.runs.get(run_id)
        if not run:
            return {"error": "Run not found"}

        controller = self._active_runs.get(run_id)

        return {
            "id": run.id,
            "status": run.status,
            "is_active": controller is not None,
            "is_paused": controller.is_paused if controller else False,
            "pid": controller.pid if controller else None,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "cost_usd": run.cost_usd,
            "duration_ms": run.duration_ms
        }

    def get_active_runs(self) -> list[str]:
        """Get list of active run IDs."""
        return list(self._active_runs.keys())

    # ==================== Interactive Session Methods ====================

    async def start_interactive_session(
        self,
        session_id: str,
        model: str = "sonnet"
    ) -> Run:
        """Start a new interactive Claude session."""
        session = await self.db.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Create run record for the interactive session
        run = await self.db.runs.create(
            session_id=session_id,
            prompt="[Interactive Session]",
            model=model
        )

        # Initialize git tracker
        git_tracker = GitTracker(session.working_dir, session_id, run.id)
        self._git_trackers[run.id] = git_tracker

        # Take initial git snapshot
        snapshot = await git_tracker.snapshot()
        await self.event_bus.publish(snapshot)

        # Create interactive session
        interactive = InteractiveSession(
            session_id=session_id,
            run_id=run.id,
            working_dir=session.working_dir,
            model=model
        )

        # Set up event callback to publish to event bus
        async def on_event(event: Event):
            await self.event_bus.publish(event)
            # Take git snapshot on tool results
            if event.type == EventType.STREAM_TOOL_RESULT:
                gt = self._git_trackers.get(run.id)
                if gt:
                    snap = await gt.snapshot()
                    await self.event_bus.publish(snap)

        interactive.set_event_callback(on_event)
        self._interactive_sessions[run.id] = interactive

        # Initialize the session
        await interactive.initialize()

        # Update run status
        await self.db.runs.update_status(run.id, "running")

        return run

    async def send_interactive_message(self, run_id: str, message: str) -> bool:
        """Send a message to an interactive session and stream response."""
        session = self._interactive_sessions.get(run_id)
        if not session:
            return False

        if not session.is_running:
            return False

        try:
            # Update the run's prompt to show current message
            await self.db.runs.update_prompt(run_id, message)

            # Generate title from first message (if not already set)
            run = await self.db.runs.get(run_id)
            if run and not run.title:
                # Create a short title from the first message
                title = message[:50] + "..." if len(message) > 50 else message
                # Clean up the title
                title = title.replace("\n", " ").strip()
                await self.db.runs.update_title(run_id, title)

            # Send message and stream response in background
            async def stream_response():
                try:
                    async for event in session.send_message(message):
                        # Track token usage on finalized result events.
                        tokens_in, tokens_out = self._extract_result_usage(event)
                        if tokens_in or tokens_out:
                            await self.db.runs.update_metrics(
                                run_id,
                                tokens_in=tokens_in,
                                tokens_out=tokens_out
                            )
                except Exception as e:
                    print(f"Error streaming response: {e}")

            # Run in background so API can return immediately
            task = asyncio.create_task(stream_response())
            self._interactive_tasks[run_id] = task

            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    async def end_interactive_session(self, run_id: str) -> bool:
        """End an interactive session."""
        session = self._interactive_sessions.get(run_id)
        if not session:
            return False

        await session.terminate()
        await self.db.runs.update_status(run_id, "completed")

        # Cancel the task
        task = self._interactive_tasks.get(run_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._interactive_sessions.pop(run_id, None)
        self._interactive_tasks.pop(run_id, None)
        self._git_trackers.pop(run_id, None)
        await self._create_interactive_snapshot(run_id)

        return True

    def get_interactive_session(self, run_id: str) -> Optional[InteractiveSession]:
        """Get an interactive session by run ID."""
        return self._interactive_sessions.get(run_id)

    def is_interactive_responding(self, run_id: str) -> bool:
        """Check whether an interactive session is currently generating a response."""
        task = self._interactive_tasks.get(run_id)
        if task is not None and not task.done():
            return True

        session = self._interactive_sessions.get(run_id)
        if not session:
            return False
        return session.pid is not None

    async def stop_interactive_response(self, run_id: str) -> bool:
        """Stop the current assistant response without ending the interactive session."""
        session = self._interactive_sessions.get(run_id)
        if not session:
            return False

        stopped = await session.interrupt_current_response()
        task = self._interactive_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self.event_bus.publish(Event(
            type=EventType.INTERVENTION_ABORT,
            session_id=session.session_id,
            run_id=run_id,
            payload={"scope": "turn"}
        ))

        return stopped

    def get_active_interactive_sessions(self) -> list[str]:
        """Get list of active interactive session run IDs."""
        return [
            run_id for run_id, session in self._interactive_sessions.items()
            if session.is_running
        ]
