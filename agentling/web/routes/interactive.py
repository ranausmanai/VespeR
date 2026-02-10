"""Interactive session API routes."""

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from ...events.types import EventType
from ...session.pty_controller import PTYController

router = APIRouter()
_MAX_AGENT_RUNTIME_SECONDS = 240
_MAX_REPEATED_BASH_COMMAND = 8


class StartInteractiveRequest(BaseModel):
    session_id: str
    model: str = "sonnet"


class SendMessageRequest(BaseModel):
    message: str


class InvokeAgentRequest(BaseModel):
    agent_id: str
    instruction: str
    inject_to_session: bool = False


class ContextPackResponse(BaseModel):
    goal: Optional[str] = None
    summary: dict[str, Any] = {}
    resume_prompt: str


def _snapshot_to_dict(snapshot) -> dict:
    return {
        "id": snapshot.id,
        "run_id": snapshot.run_id,
        "session_id": snapshot.session_id,
        "goal": snapshot.goal,
        "summary": snapshot.summary or {},
        "resume_prompt": snapshot.resume_prompt,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def _build_agent_prompt(
    *,
    name: str,
    system_prompt: Optional[str],
    personality: Optional[str],
    constraints: Optional[dict],
    instruction: str,
    recent_context: list[str],
) -> str:
    parts: list[str] = [f"You are agent: {name}."]
    parts.append(
        "You are running inside an active coding session with attached context. "
        "Use the provided context directly. "
        "Do not ask the user to paste code if files/chat context are already present. "
        "Only request more input when context is truly insufficient."
    )

    if system_prompt:
        parts.append(f"<system>\n{system_prompt}\n</system>")
    if personality:
        parts.append(f"<personality>\n{personality}\n</personality>")
    if constraints:
        constraints_text = "\n".join(f"- {k}: {v}" for k, v in constraints.items())
        parts.append(f"<constraints>\n{constraints_text}\n</constraints>")

    if recent_context:
        parts.append("Recent interactive context:\n" + "\n".join(recent_context))

    parts.append(f"Task:\n{instruction}")
    parts.append("Respond with practical, actionable output.")

    return "\n\n".join(parts)


def _build_injected_agent_note(agent_name: str, output: str, max_chars: int = 6000) -> str:
    clipped = (output or "").strip()
    if len(clipped) > max_chars:
        clipped = clipped[:max_chars] + "\n\n[Truncated for context window]"

    return (
        f"[Agent Context: {agent_name}]\n\n"
        "Treat the content below as supporting context from a helper agent, not as a new user request.\n"
        "Do not ask the user to choose among options from this note unless strictly required.\n"
        "Continue executing the latest user task using this context.\n\n"
        f"{clipped}"
    )


def _build_recent_turns(events: list[dict[str, Any]], max_turns: int = 8) -> list[str]:
    turns: list[str] = []
    assistant_buffer: list[str] = []

    def flush_assistant() -> None:
        if assistant_buffer:
            text = "".join(assistant_buffer).strip()
            if text:
                turns.append(f"Assistant: {text[:1200]}")
            assistant_buffer.clear()

    for event in events:
        event_type = event.get("type")
        if event_type == EventType.STREAM_USER.value:
            flush_assistant()
            content = (event.get("content") or event.get("payload", {}).get("content") or "").strip()
            if content:
                turns.append(f"User: {content[:1200]}")
        elif event_type == EventType.STREAM_ASSISTANT.value:
            content = (event.get("content") or event.get("payload", {}).get("content") or "")
            if content:
                assistant_buffer.append(str(content))
        elif event_type == EventType.STREAM_RESULT.value:
            flush_assistant()

    flush_assistant()
    return turns[-max_turns:]


def _extract_touched_files(events: list[dict[str, Any]], max_files: int = 10) -> list[dict[str, str]]:
    touched: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    tool_types = {"Write": "created", "Edit": "edited", "Read": "read"}

    for event in reversed(events):
        if event.get("type") != EventType.STREAM_TOOL_USE.value:
            continue
        tool_name = str(event.get("tool_name") or event.get("payload", {}).get("name") or "")
        if tool_name not in tool_types:
            continue
        tool_input = event.get("tool_input") or event.get("payload", {}).get("input") or {}
        path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
        if not path:
            continue
        key = (path, tool_name)
        if key in seen:
            continue
        seen.add(key)
        touched.append({"path": path, "action": tool_types[tool_name]})
        if len(touched) >= max_files:
            break

    return list(reversed(touched))


def _safe_read_file(working_dir: str, file_path: str, max_chars: int = 2500) -> Optional[str]:
    try:
        work = Path(working_dir).resolve()
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = (work / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if work not in candidate.parents and candidate != work:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        text = candidate.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]
    except Exception:
        return None


def _git_diff_for_file(working_dir: str, file_path: str, max_chars: int = 1800) -> Optional[str]:
    try:
        work = Path(working_dir).resolve()
        candidate = Path(file_path)
        if candidate.is_absolute():
            candidate = candidate.resolve()
        else:
            candidate = (work / candidate).resolve()
        if work not in candidate.parents and candidate != work:
            return None
        rel_path = str(candidate.relative_to(work))
        result = subprocess.run(
            ["git", "-C", str(work), "diff", "--no-ext-diff", "--", rel_path],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if result.returncode != 0:
            return None
        diff = (result.stdout or "").strip()
        if not diff:
            return None
        return diff[:max_chars]
    except Exception:
        return None


def _resolve_instruction_target(instruction: str, touched_files: list[dict[str, str]]) -> Optional[str]:
    if not touched_files:
        return None
    lowered = instruction.lower()
    if not re.search(r"\b(it|this|that|review it|check it|audit it)\b", lowered):
        return None
    return touched_files[-1]["path"]


def _is_review_like_instruction(instruction: str) -> bool:
    lowered = instruction.lower()
    return bool(re.search(r"\b(review|audit|check|inspect|critic|critique|security)\b", lowered))


def _build_smart_context(
    *,
    events: list[dict[str, Any]],
    working_dir: str,
    instruction: str,
) -> tuple[list[str], str, dict[str, Any]]:
    recent_turns = _build_recent_turns(events, max_turns=8)
    touched_files = _extract_touched_files(events, max_files=10)
    resolved_target = _resolve_instruction_target(instruction, touched_files)

    context_parts: list[str] = []
    if recent_turns:
        context_parts.append("Recent chat turns:\n" + "\n".join(recent_turns))

    file_lines: list[str] = []
    for item in touched_files[:6]:
        file_lines.append(f"- {item['action']}: {item['path']}")
    if file_lines:
        context_parts.append("Files touched in this session:\n" + "\n".join(file_lines))

    preview_blocks: list[str] = []
    for item in touched_files[-3:]:
        path = item["path"]
        diff = _git_diff_for_file(working_dir, path)
        if diff:
            preview_blocks.append(f"Diff for {path}:\n```diff\n{diff}\n```")
            continue
        preview = _safe_read_file(working_dir, path)
        if preview:
            preview_blocks.append(f"Current content preview for {path}:\n```text\n{preview}\n```")
    if preview_blocks:
        context_parts.append("\n\n".join(preview_blocks))

    enriched_instruction = instruction.strip()
    if resolved_target:
        enriched_instruction = (
            f"{enriched_instruction}\n\n"
            f"Reference resolution: 'it/this/that' refers to `{resolved_target}`."
        )
    if _is_review_like_instruction(instruction) and touched_files:
        primary_targets = [resolved_target] if resolved_target else []
        primary_targets.extend(
            [item["path"] for item in touched_files if item["path"] not in primary_targets]
        )
        enriched_instruction = (
            f"{enriched_instruction}\n\n"
            "Review guidance: perform a concrete code review against the files in context. "
            "Return findings with severity and actionable fixes. "
            "Do not ask for code snippets unless no file content/diff exists in context.\n"
            "Primary files:\n- " + "\n- ".join(primary_targets[:5])
        )

    metadata = {
        "recent_turns_count": len(recent_turns),
        "touched_files": [item["path"] for item in touched_files],
        "resolved_target": resolved_target,
    }
    return context_parts, enriched_instruction, metadata


@router.post("")
async def start_interactive_session(request: Request, body: StartInteractiveRequest):
    """Start a new interactive Claude session."""
    session_manager = request.app.state.session_manager

    try:
        run = await session_manager.start_interactive_session(
            session_id=body.session_id,
            model=body.model
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Wait a moment for the session to initialize
    await asyncio.sleep(0.5)

    session = session_manager.get_interactive_session(run.id)

    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": "running",
        "model": body.model,
        "interactive": True,
        "is_running": session.is_running if session else False,
        "pid": session.pid if session else None,
        "websocket_url": f"/ws/runs/{run.id}"
    }


@router.get("/{run_id}")
async def get_interactive_session(request: Request, run_id: str):
    """Get status of an interactive session."""
    session_manager = request.app.state.session_manager
    db = request.app.state.db

    session = session_manager.get_interactive_session(run_id)
    run = await db.runs.get(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Session not found")

    event_count = await db.events.count_for_run(run_id)

    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": run.status,
        "model": run.model,
        "interactive": True,
        "is_running": session.is_running if session else False,
        "pid": session.pid if session else None,
        "prompt": run.prompt,
        "title": run.title,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "event_count": event_count,
        "is_responding": session_manager.is_interactive_responding(run_id),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("/{run_id}/snapshot")
async def get_interactive_snapshot(request: Request, run_id: str):
    """Get saved resume snapshot for an ended interactive run."""
    db = request.app.state.db
    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not db.session_snapshots:
        raise HTTPException(status_code=500, detail="Snapshot repository unavailable")
    snapshot = await db.session_snapshots.get_for_run(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return _snapshot_to_dict(snapshot)


@router.get("/session/{session_id}/latest-snapshot")
async def get_latest_snapshot_for_session(request: Request, session_id: str):
    """Get most recent resume snapshot for a project session."""
    db = request.app.state.db
    session = await db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not db.session_snapshots:
        raise HTTPException(status_code=500, detail="Snapshot repository unavailable")
    snapshot = await db.session_snapshots.get_latest_for_session(session_id)
    if not snapshot:
        return {"snapshot": None}
    return {"snapshot": _snapshot_to_dict(snapshot)}


@router.get("/session/{session_id}/context-pack")
async def get_context_pack_for_session(
    request: Request,
    session_id: str,
    source_run_id: Optional[str] = None,
):
    """Get ranked smart context pack assembled from structured run memory."""
    db = request.app.state.db
    session_manager = request.app.state.session_manager
    session = await db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pack = await session_manager.build_session_context_pack(
        session_id=session_id,
        source_run_id=source_run_id,
        max_entries=5,
    )

    return {
        "snapshot": {
            "id": f"context-pack-{session_id}",
            "run_id": source_run_id or "",
            "session_id": session_id,
            "goal": pack.get("goal") or None,
            "summary": pack.get("summary") or {},
            "resume_prompt": pack.get("resume_prompt") or "",
            "created_at": None,
        }
    }


@router.post("/{run_id}/message")
async def send_message(request: Request, run_id: str, body: SendMessageRequest):
    """Send a message to an interactive session."""
    session_manager = request.app.state.session_manager

    session = session_manager.get_interactive_session(run_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interactive session not found")

    if not session.is_running:
        raise HTTPException(status_code=400, detail="Session is not running")

    success = await session_manager.send_interactive_message(run_id, body.message)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send message")

    return {
        "status": "sent",
        "message": body.message
    }


@router.post("/{run_id}/end")
async def end_interactive_session(request: Request, run_id: str):
    """End an interactive session."""
    session_manager = request.app.state.session_manager

    success = await session_manager.end_interactive_session(run_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found or already ended")

    return {
        "status": "ended",
        "run_id": run_id
    }


@router.post("/{run_id}/stop")
async def stop_interactive_response(request: Request, run_id: str):
    """Stop current assistant response while keeping session active."""
    session_manager = request.app.state.session_manager

    success = await session_manager.stop_interactive_response(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="No active response to stop")

    return {
        "status": "stopped",
        "run_id": run_id
    }


@router.post("/{run_id}/agent")
async def invoke_agent(request: Request, run_id: str, body: InvokeAgentRequest):
    """Invoke an agent during an active interactive session."""
    db = request.app.state.db
    session_manager = request.app.state.session_manager

    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    session = await db.sessions.get(run.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    agent = await db.agents.get(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    events: list[dict[str, Any]] = []
    async for event in db.events.get_events_for_run(run_id, from_sequence=0):
        events.append(event)

    smart_context, enriched_instruction, context_meta = _build_smart_context(
        events=events,
        working_dir=session.working_dir,
        instruction=body.instruction,
    )

    full_prompt = _build_agent_prompt(
        name=agent.name,
        system_prompt=agent.system_prompt,
        personality=agent.personality,
        constraints=agent.constraints,
        instruction=enriched_instruction,
        recent_context=smart_context,
    )

    controller = PTYController(
        session_id=run.session_id,
        run_id=f"{run_id}-agent-{agent.id}",
        working_dir=session.working_dir,
        model=agent.model or "sonnet",
    )

    output_chunks: list[str] = []
    last_bash_command: Optional[str] = None
    repeated_bash_count = 0
    try:
        async with asyncio.timeout(_MAX_AGENT_RUNTIME_SECONDS):
            async for event in controller.start(full_prompt):
                if event.type == EventType.STREAM_TOOL_USE:
                    tool_name = getattr(event, "tool_name", None) or str((event.payload or {}).get("tool_name") or "")
                    tool_input = (
                        getattr(event, "tool_input", None)
                        or (event.payload or {}).get("tool_input")
                        or (event.payload or {}).get("content_block", {}).get("input", {})
                    )
                    command = ""
                    if isinstance(tool_input, dict):
                        command = str(tool_input.get("command") or "").strip()

                    if tool_name == "Bash" and command:
                        if command == last_bash_command:
                            repeated_bash_count += 1
                        else:
                            last_bash_command = command
                            repeated_bash_count = 1

                        if repeated_bash_count >= _MAX_REPEATED_BASH_COMMAND:
                            await controller.terminate()
                            raise RuntimeError(
                                f"Runaway loop detected: repeated Bash command `{command}` "
                                f"{repeated_bash_count} times. Aborted."
                            )
                    elif tool_name == "Bash":
                        last_bash_command = None
                        repeated_bash_count = 0

                if event.type != EventType.STREAM_ASSISTANT:
                    continue
                delta = event.payload.get("delta", {}) if event.payload else {}
                text = event.content or delta.get("text") or ""
                if text:
                    output_chunks.append(str(text))
    except TimeoutError as e:
        await controller.terminate()
        raise HTTPException(
            status_code=500,
            detail=f"Agent exceeded {_MAX_AGENT_RUNTIME_SECONDS}s runtime limit and was aborted.",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent invocation failed: {e}") from e

    output = "".join(output_chunks).strip()
    if not output:
        raise HTTPException(status_code=500, detail="Agent produced no output")

    injected = False
    if body.inject_to_session:
        injected_note = _build_injected_agent_note(agent.name, output)
        injected = await session_manager.send_interactive_message(
            run_id,
            injected_note,
        )

    return {
        "status": "ok",
        "run_id": run_id,
        "agent_id": agent.id,
        "agent_name": agent.name,
        "model": agent.model,
        "output": output,
        "injected": injected,
        "context": context_meta,
    }


@router.get("")
async def list_interactive_sessions(request: Request):
    """List all active interactive sessions."""
    session_manager = request.app.state.session_manager
    db = request.app.state.db

    run_ids = session_manager.get_active_interactive_sessions()

    sessions = []
    for run_id in run_ids:
        run = await db.runs.get(run_id)
        session = session_manager.get_interactive_session(run_id)
        if run and session:
            # Get project name for context
            project_session = await db.sessions.get(run.session_id)
            sessions.append({
                "id": run.id,
                "session_id": run.session_id,
                "project_name": project_session.name if project_session else None,
                "title": run.title,
                "status": run.status,
                "model": run.model,
                "is_running": session.is_running,
                "pid": session.pid,
                "tokens_in": run.tokens_in,
                "tokens_out": run.tokens_out,
                "is_responding": session_manager.is_interactive_responding(run_id),
                "created_at": run.created_at.isoformat() if run.created_at else None,
            })

    return {"sessions": sessions}
