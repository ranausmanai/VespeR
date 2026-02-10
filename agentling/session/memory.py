"""Structured run memory extraction and context-pack assembly."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ..events.types import EventType


def _clean_line(text: str, max_len: int = 260) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _normalize_command(command: str) -> str:
    cmd = (command or "").strip()
    if not cmd:
        return ""
    if "<<" in cmd:
        first_line = cmd.splitlines()[0].strip()
        return _clean_line(f"{first_line} [heredoc body omitted]", max_len=220)
    first_line = cmd.splitlines()[0].strip()
    return _clean_line(first_line, max_len=220)


async def extract_run_memory(db, run_id: str) -> Optional[dict[str, Any]]:
    """Extract deterministic structured memory for a run."""
    run = await db.runs.get(run_id)
    if not run:
        return None

    first_goal = ""
    recent_user_goals: list[str] = []
    touched_files: list[str] = []
    touched_seen: set[str] = set()
    commands: list[str] = []
    command_seen: set[str] = set()
    latest_assistant_parts: list[str] = []
    assistant_outcomes: list[str] = []
    latest_assistant_summary = ""
    error_count = 0
    test_commands: list[str] = []
    read_count = 0
    edit_count = 0
    write_count = 0
    open_loops: list[str] = []
    seen_open_loops: set[str] = set()

    async for event in db.events.get_events_for_run(run_id, from_sequence=0):
        event_type = event.get("type")
        payload = event.get("payload", {}) or {}

        if event_type == EventType.STREAM_USER.value:
            content = str(event.get("content") or payload.get("content") or "").strip()
            if content and not content.startswith("[Agent"):
                if not first_goal:
                    first_goal = content
                recent_user_goals.append(_clean_line(content, max_len=180))
                if len(recent_user_goals) > 6:
                    recent_user_goals = recent_user_goals[-6:]
                latest_assistant_parts = []

        if event_type == EventType.STREAM_ASSISTANT.value:
            content = str(event.get("content") or payload.get("content") or "")
            if content:
                latest_assistant_parts.append(content)

        if event_type == EventType.STREAM_RESULT.value and latest_assistant_parts:
            latest_assistant_summary = _clean_line("".join(latest_assistant_parts), max_len=900)
            if latest_assistant_summary:
                assistant_outcomes.append(latest_assistant_summary)
                if len(assistant_outcomes) > 3:
                    assistant_outcomes = assistant_outcomes[-3:]
                lowered = latest_assistant_summary.lower()
                if any(
                    cue in lowered
                    for cue in (
                        "let me know",
                        "would you like",
                        "what would you like",
                        "i can also",
                        "next step",
                    )
                ):
                    loop = _clean_line(latest_assistant_summary, max_len=220)
                    if loop not in seen_open_loops:
                        seen_open_loops.add(loop)
                        open_loops.append(loop)

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
                        lowered_cmd = command.lower()
                        if any(x in lowered_cmd for x in ("test", "pytest", "jest", "vitest", "go test", "cargo test")):
                            test_commands.append(normalized_command)

        if event_type in {EventType.STREAM_ERROR.value, EventType.RUN_FAILED.value}:
            error_count += 1

    phases: list[str] = []
    if read_count > 0:
        phases.append("exploration")
    if write_count > 0 or edit_count > 0:
        phases.append("implementation")
    if test_commands:
        phases.append("validation")
    if error_count > 0:
        phases.append("error_handling")

    if run.status == "failed":
        next_action = "Fix the latest failure first, then rerun the smallest relevant validation command."
    elif test_commands:
        next_action = "Re-run targeted tests for changed files, then finalize remaining polish."
    elif touched_files:
        next_action = "Review touched files for completeness and run one lightweight validation command."
    else:
        next_action = "Clarify the next concrete implementation step and proceed."

    objective = _clean_line(first_goal, max_len=300)
    short_summary = latest_assistant_summary or (
        f"Run {run.status} with {len(touched_files)} files touched and {len(commands)} key commands."
    )

    return {
        "objective": objective,
        "short_summary": _clean_line(short_summary, max_len=320),
        "status": run.status,
        "recent_user_goals": recent_user_goals[-4:],
        "assistant_outcomes": assistant_outcomes[-2:],
        "files_touched": touched_files[:24],
        "commands": commands[:24],
        "test_commands": test_commands[:12],
        "error_count": error_count,
        "phases": phases,
        "open_loops": open_loops[:6],
        "next_action": next_action,
        "phase_counts": {
            "read_ops": read_count,
            "write_ops": write_count,
            "edit_ops": edit_count,
        },
    }


async def persist_run_memory(db, run_id: str) -> None:
    """Extract and upsert run memory if repository is available."""
    if not db.run_memory:
        return
    run = await db.runs.get(run_id)
    if not run:
        return
    memory = await extract_run_memory(db, run_id)
    if not memory:
        return
    await db.run_memory.upsert(
        run_id=run_id,
        session_id=run.session_id,
        objective=memory.get("objective") or None,
        short_summary=memory.get("short_summary") or "Run memory",
        memory=memory,
    )


def _memory_score(entry, now: datetime, source_run_id: Optional[str]) -> float:
    score = 0.0
    if source_run_id and entry.run_id == source_run_id:
        score += 1000.0
    age_hours = 0.0
    if entry.created_at:
        age_hours = max(0.0, (now - entry.created_at).total_seconds() / 3600.0)
    score += max(0.0, 240.0 - age_hours) / 8.0

    memory = entry.memory or {}
    if memory.get("status") == "failed":
        score += 8.0
    if memory.get("open_loops"):
        score += min(6.0, float(len(memory.get("open_loops", []))))
    if memory.get("test_commands"):
        score += 3.0
    if memory.get("files_touched"):
        score += min(5.0, len(memory.get("files_touched", [])) / 2.0)
    return score


def build_context_pack(memories: list, source_run_id: Optional[str] = None, max_entries: int = 5) -> dict[str, Any]:
    """Rank memories and build a compact resume prompt."""
    if not memories:
        return {
            "goal": "",
            "summary": {"source": "memory_pack", "entries_used": 0},
            "resume_prompt": (
                "Resume this coding session.\n"
                "No prior structured memory was found. Start by confirming current objective and state."
            ),
        }

    now = datetime.utcnow()
    ranked = sorted(memories, key=lambda m: _memory_score(m, now, source_run_id), reverse=True)
    selected = ranked[:max_entries]

    primary = selected[0]
    primary_memory = primary.memory or {}
    selected_entries: list[dict[str, Any]] = []

    files: list[str] = []
    seen_files: set[str] = set()
    open_loops: list[str] = []
    seen_loops: set[str] = set()
    validations: list[str] = []
    seen_validations: set[str] = set()
    commands: list[str] = []
    seen_commands: set[str] = set()
    recent_work: list[str] = []

    for entry in selected:
        mem = entry.memory or {}
        summary = str(mem.get("short_summary") or entry.short_summary or "").strip()
        selected_entries.append(
            {
                "run_id": entry.run_id,
                "objective": str(mem.get("objective") or entry.objective or "").strip(),
                "short_summary": _clean_line(summary, max_len=180),
                "status": str(mem.get("status") or ""),
                "files_touched_count": len(mem.get("files_touched", []) or []),
                "open_loops_count": len(mem.get("open_loops", []) or []),
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
        )
        if summary:
            recent_work.append(_clean_line(summary, max_len=180))
            if len(recent_work) > 5:
                recent_work = recent_work[:5]

        for path in mem.get("files_touched", [])[:8]:
            if path not in seen_files:
                seen_files.add(path)
                files.append(path)
            if len(files) >= 12:
                break

        for loop in mem.get("open_loops", [])[:3]:
            cleaned = _clean_line(str(loop), max_len=160)
            if cleaned and cleaned not in seen_loops:
                seen_loops.add(cleaned)
                open_loops.append(cleaned)
            if len(open_loops) >= 6:
                break

        for test_cmd in mem.get("test_commands", [])[:3]:
            cmd = _clean_line(str(test_cmd), max_len=120)
            if cmd and cmd not in seen_validations:
                seen_validations.add(cmd)
                validations.append(cmd)
            if len(validations) >= 5:
                break

        for cmd in mem.get("commands", [])[:2]:
            cleaned = _clean_line(str(cmd), max_len=120)
            if cleaned and cleaned not in seen_commands:
                seen_commands.add(cleaned)
                commands.append(cleaned)
            if len(commands) >= 6:
                break

    objective = str(primary_memory.get("objective") or primary.objective or "").strip()
    next_action = _clean_line(
        str(primary_memory.get("next_action") or "Continue from the latest completed step and verify."),
        max_len=220,
    )

    def _bullet(items: list[str], max_items: int) -> str:
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items[:max_items])

    resume_prompt = (
        "Resume this previously ended coding session with smart memory context.\n\n"
        "Objective:\n"
        f"{objective or '(No explicit objective captured)'}\n\n"
        "Recent completed work:\n"
        f"{_bullet(recent_work, 5)}\n\n"
        "Open loops needing attention:\n"
        f"{_bullet(open_loops, 6)}\n\n"
        "Key artifacts touched:\n"
        f"{_bullet(files, 12)}\n\n"
        "Relevant validation commands seen:\n"
        f"{_bullet(validations, 5)}\n\n"
        "Important commands run:\n"
        f"{_bullet(commands, 6)}\n\n"
        "Continue from here:\n"
        f"- {next_action}\n"
        "- Reuse existing files/artifacts before creating new ones.\n"
        "- Avoid repeating already completed steps unless verification fails.\n"
        "- If uncertain, run one small validation command before broad changes."
    )

    return {
        "goal": objective,
        "summary": {
            "source": "memory_pack",
            "entries_used": len(selected),
            "source_run_id": source_run_id,
            "run_ids": [entry.run_id for entry in selected],
            "selected_entries": selected_entries,
        },
        "resume_prompt": resume_prompt,
    }
