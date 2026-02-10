"""Data access repositories for SQLite persistence."""

import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, AsyncIterator, Any

import aiosqlite

from ..events.types import Event, EventType


@dataclass
class Session:
    """Session model."""
    id: str
    name: Optional[str]
    working_dir: str
    created_at: datetime
    updated_at: datetime
    config: dict[str, Any]
    status: str = "active"


@dataclass
class Run:
    """Run model."""
    id: str
    session_id: str
    prompt: str
    status: str = "pending"
    model: Optional[str] = None
    parent_run_id: Optional[str] = None
    branch_point_event_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    final_output: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    title: Optional[str] = None


@dataclass
class Agent:
    """Agent template model."""
    id: str
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    personality: Optional[str] = None
    system_prompt: Optional[str] = None
    model: str = "sonnet"
    tools: list[str] = None
    constraints: dict[str, Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = []
        if self.constraints is None:
            self.constraints = {}


@dataclass
class AgentRun:
    """Agent run instance - links an agent to a run execution."""
    id: str
    agent_id: str
    run_id: str
    parent_agent_run_id: Optional[str] = None
    pattern: str = "solo"
    role_in_pattern: Optional[str] = None
    sequence: int = 0
    iteration: int = 0
    status: str = "pending"
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    metadata: dict[str, Any] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AgentPattern:
    """Saved multi-agent workflow pattern."""
    id: str
    name: str
    description: Optional[str] = None
    pattern_type: str = "solo"
    config: dict[str, Any] = None
    human_involvement: str = "checkpoints"
    max_iterations: int = 3
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}


@dataclass
class SessionSnapshot:
    """Snapshot summary for an ended interactive run."""
    id: str
    run_id: str
    session_id: str
    goal: Optional[str] = None
    summary: dict[str, Any] = None
    resume_prompt: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.summary is None:
            self.summary = {}


@dataclass
class RunMemoryEntry:
    """Structured memory extracted from a completed run."""
    id: str
    run_id: str
    session_id: str
    objective: Optional[str] = None
    short_summary: str = ""
    memory: dict[str, Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.memory is None:
            self.memory = {}


class SessionRepository:
    """Repository for session CRUD operations."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        working_dir: str,
        name: Optional[str] = None,
        config: Optional[dict] = None
    ) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        config = config or {}

        await self._conn.execute(
            """INSERT INTO sessions (id, name, working_dir, created_at, updated_at, config_json, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, name, working_dir, now, now, json.dumps(config), "active")
        )
        await self._conn.commit()

        return Session(
            id=session_id,
            name=name,
            working_dir=working_dir,
            created_at=now,
            updated_at=now,
            config=config,
            status="active"
        )

    async def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return Session(
            id=row["id"],
            name=row["name"],
            working_dir=row["working_dir"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            config=json.loads(row["config_json"] or "{}"),
            status=row["status"]
        )

    async def get_by_working_dir(self, working_dir: str) -> Optional[Session]:
        """Get session by working directory."""
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE working_dir = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (working_dir,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return Session(
            id=row["id"],
            name=row["name"],
            working_dir=row["working_dir"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            config=json.loads(row["config_json"] or "{}"),
            status=row["status"]
        )

    async def list_all(self, status: Optional[str] = None) -> list[Session]:
        """List all sessions, optionally filtered by status."""
        if status:
            cursor = await self._conn.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY updated_at DESC",
                (status,)
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            )

        sessions = []
        async for row in cursor:
            sessions.append(Session(
                id=row["id"],
                name=row["name"],
                working_dir=row["working_dir"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                config=json.loads(row["config_json"] or "{}"),
                status=row["status"]
            ))

        return sessions

    async def update(self, session_id: str, **kwargs) -> None:
        """Update session fields."""
        allowed = {"name", "config", "status"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if "config" in updates:
            updates["config_json"] = json.dumps(updates.pop("config"))

        if not updates:
            return

        updates["updated_at"] = datetime.utcnow()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [session_id]

        await self._conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?", values
        )
        await self._conn.commit()


class RunRepository:
    """Repository for run CRUD operations."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        session_id: str,
        prompt: str,
        model: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        branch_point_event_id: Optional[str] = None
    ) -> Run:
        """Create a new run."""
        run_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._conn.execute(
            """INSERT INTO runs (id, session_id, prompt, model, parent_run_id, branch_point_event_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, session_id, prompt, model, parent_run_id, branch_point_event_id, "pending", now)
        )
        await self._conn.commit()

        return Run(
            id=run_id,
            session_id=session_id,
            prompt=prompt,
            model=model,
            parent_run_id=parent_run_id,
            branch_point_event_id=branch_point_event_id,
            status="pending",
            created_at=now
        )

    async def get(self, run_id: str) -> Optional[Run]:
        """Get a run by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_run(row)

    async def list_for_session(self, session_id: str) -> list[Run]:
        """List all runs for a session."""
        cursor = await self._conn.execute(
            "SELECT * FROM runs WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,)
        )

        runs = []
        async for row in cursor:
            runs.append(self._row_to_run(row))

        return runs

    async def update_status(
        self,
        run_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Update run status."""
        now = datetime.utcnow()

        if status == "running":
            await self._conn.execute(
                "UPDATE runs SET status = ?, started_at = ? WHERE id = ?",
                (status, now, run_id)
            )
        elif status in ("completed", "failed"):
            await self._conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, error_message = ? WHERE id = ?",
                (status, now, error_message, run_id)
            )
        else:
            await self._conn.execute(
                "UPDATE runs SET status = ? WHERE id = ?",
                (status, run_id)
            )

        await self._conn.commit()

    async def update_metrics(
        self,
        run_id: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        duration_ms: int = 0
    ) -> None:
        """Update run metrics."""
        await self._conn.execute(
            """UPDATE runs SET
               tokens_in = tokens_in + ?,
               tokens_out = tokens_out + ?,
               cost_usd = cost_usd + ?,
               duration_ms = ?
               WHERE id = ?""",
            (tokens_in, tokens_out, cost_usd, duration_ms, run_id)
        )
        await self._conn.commit()

    async def update_title(self, run_id: str, title: str) -> None:
        """Update run title."""
        await self._conn.execute(
            "UPDATE runs SET title = ? WHERE id = ?",
            (title, run_id)
        )
        await self._conn.commit()

    async def set_output(self, run_id: str, output: str) -> None:
        """Set final output for a run."""
        await self._conn.execute(
            "UPDATE runs SET final_output = ? WHERE id = ?",
            (output, run_id)
        )
        await self._conn.commit()

    async def update_prompt(self, run_id: str, prompt: str) -> None:
        """Update the prompt for a run (used for interactive sessions)."""
        await self._conn.execute(
            "UPDATE runs SET prompt = ? WHERE id = ?",
            (prompt, run_id)
        )
        await self._conn.commit()

    def _row_to_run(self, row) -> Run:
        """Convert database row to Run model."""
        return Run(
            id=row["id"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            status=row["status"],
            model=row["model"],
            parent_run_id=row["parent_run_id"],
            branch_point_event_id=row["branch_point_event_id"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            tokens_in=row["tokens_in"] or 0,
            tokens_out=row["tokens_out"] or 0,
            cost_usd=row["cost_usd"] or 0.0,
            duration_ms=row["duration_ms"] or 0,
            final_output=row["final_output"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            title=row["title"] if "title" in row.keys() else None
        )


class EventRepository:
    """Repository for event persistence."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def save(self, event: Event) -> None:
        """Save an event to the database."""
        # Get all event data including StreamEvent-specific fields
        event_dict = event.to_dict()

        # Store everything in payload for full data preservation
        # Keep the base payload but merge in any StreamEvent fields
        full_payload = dict(event.payload) if event.payload else {}

        # Add StreamEvent-specific fields if present
        for key in ['content', 'content_type', 'role', 'tool_name', 'tool_id',
                    'tool_input', 'tool_output', 'is_error']:
            if key in event_dict and event_dict[key] is not None:
                full_payload[key] = event_dict[key]

        await self._conn.execute(
            """INSERT INTO events (id, run_id, session_id, type, sequence, timestamp, payload_json, parent_event_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.run_id,
                event.session_id,
                event.type.value,
                event.sequence,
                event.timestamp,
                json.dumps(full_payload),
                event.parent_event_id
            )
        )
        await self._conn.commit()

    async def get(self, event_id: str) -> Optional[dict]:
        """Get an event by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_event(row)

    async def get_events_for_run(
        self,
        run_id: str,
        from_sequence: int = 0,
        to_sequence: Optional[int] = None
    ) -> AsyncIterator[dict]:
        """Get events for a run within a sequence range."""
        if to_sequence is not None:
            cursor = await self._conn.execute(
                """SELECT * FROM events
                   WHERE run_id = ? AND sequence >= ? AND sequence <= ?
                   ORDER BY sequence""",
                (run_id, from_sequence, to_sequence)
            )
        else:
            cursor = await self._conn.execute(
                """SELECT * FROM events
                   WHERE run_id = ? AND sequence >= ?
                   ORDER BY sequence""",
                (run_id, from_sequence)
            )

        async for row in cursor:
            yield self._row_to_event(row)

    async def count_for_run(self, run_id: str) -> int:
        """Count events for a run."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    def _row_to_event(self, row) -> dict:
        """Convert database row to event dict with all fields."""
        payload = json.loads(row["payload_json"] or "{}")

        # Build base event dict
        event_dict = {
            "id": row["id"],
            "type": row["type"],
            "session_id": row["session_id"],
            "run_id": row["run_id"],
            "timestamp": row["timestamp"],
            "sequence": row["sequence"],
            "payload": payload,
            "parent_event_id": row["parent_event_id"],
        }

        # Merge StreamEvent fields to top level for API convenience
        for key in ['content', 'content_type', 'role', 'tool_name', 'tool_id',
                    'tool_input', 'tool_output', 'is_error']:
            if key in payload:
                event_dict[key] = payload[key]

        return event_dict


class GitSnapshotRepository:
    """Repository for git snapshot persistence."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def save(
        self,
        event_id: str,
        run_id: str,
        commit_hash: str,
        branch: str,
        dirty_files: list[str],
        staged_files: list[str],
        diff_stat: str
    ) -> str:
        """Save a git snapshot."""
        snapshot_id = str(uuid.uuid4())

        await self._conn.execute(
            """INSERT INTO git_snapshots
               (id, event_id, run_id, commit_hash, branch, dirty_files_json, staged_files_json, diff_stat)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                event_id,
                run_id,
                commit_hash,
                branch,
                json.dumps(dirty_files),
                json.dumps(staged_files),
                diff_stat
            )
        )
        await self._conn.commit()

        return snapshot_id

    async def get_for_run(self, run_id: str) -> list[dict]:
        """Get all git snapshots for a run."""
        cursor = await self._conn.execute(
            "SELECT * FROM git_snapshots WHERE run_id = ? ORDER BY created_at",
            (run_id,)
        )

        snapshots = []
        async for row in cursor:
            snapshots.append({
                "id": row["id"],
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "commit_hash": row["commit_hash"],
                "branch": row["branch"],
                "dirty_files": json.loads(row["dirty_files_json"] or "[]"),
                "staged_files": json.loads(row["staged_files_json"] or "[]"),
                "diff_stat": row["diff_stat"],
                "created_at": row["created_at"]
            })

        return snapshots


class AgentRepository:
    """Repository for agent CRUD operations."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        role: Optional[str] = None,
        personality: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        constraints: Optional[dict] = None
    ) -> Agent:
        """Create a new agent."""
        agent_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._conn.execute(
            """INSERT INTO agents
               (id, name, description, role, personality, system_prompt, model, tools_json, constraints_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id, name, description, role, personality, system_prompt, model,
                json.dumps(tools or []), json.dumps(constraints or {}), now, now
            )
        )
        await self._conn.commit()

        return Agent(
            id=agent_id,
            name=name,
            description=description,
            role=role,
            personality=personality,
            system_prompt=system_prompt,
            model=model,
            tools=tools or [],
            constraints=constraints or {},
            created_at=now,
            updated_at=now
        )

    async def get(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_agent(row)

    async def list_all(self) -> list[Agent]:
        """List all agents."""
        cursor = await self._conn.execute(
            "SELECT * FROM agents ORDER BY updated_at DESC"
        )

        agents = []
        async for row in cursor:
            agents.append(self._row_to_agent(row))

        return agents

    async def update(self, agent_id: str, **kwargs) -> Optional[Agent]:
        """Update agent fields."""
        allowed = {"name", "description", "role", "personality", "system_prompt", "model", "tools", "constraints"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if "tools" in updates:
            updates["tools_json"] = json.dumps(updates.pop("tools"))
        if "constraints" in updates:
            updates["constraints_json"] = json.dumps(updates.pop("constraints"))

        if not updates:
            return await self.get(agent_id)

        updates["updated_at"] = datetime.utcnow()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [agent_id]

        await self._conn.execute(
            f"UPDATE agents SET {set_clause} WHERE id = ?", values
        )
        await self._conn.commit()

        return await self.get(agent_id)

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent."""
        cursor = await self._conn.execute(
            "DELETE FROM agents WHERE id = ?", (agent_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_agent(self, row) -> Agent:
        """Convert database row to Agent model."""
        return Agent(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            role=row["role"],
            personality=row["personality"],
            system_prompt=row["system_prompt"],
            model=row["model"],
            tools=json.loads(row["tools_json"] or "[]"),
            constraints=json.loads(row["constraints_json"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
        )


class AgentRunRepository:
    """Repository for agent run tracking."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        agent_id: str,
        run_id: str,
        pattern: str = "solo",
        role_in_pattern: Optional[str] = None,
        sequence: int = 0,
        iteration: int = 0,
        parent_agent_run_id: Optional[str] = None,
        input_text: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> AgentRun:
        """Create a new agent run."""
        agent_run_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._conn.execute(
            """INSERT INTO agent_runs
               (id, agent_id, run_id, parent_agent_run_id, pattern, role_in_pattern,
                sequence, iteration, status, input_text, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_run_id, agent_id, run_id, parent_agent_run_id, pattern,
                role_in_pattern, sequence, iteration, "pending", input_text,
                json.dumps(metadata or {}), now
            )
        )
        await self._conn.commit()

        return AgentRun(
            id=agent_run_id,
            agent_id=agent_id,
            run_id=run_id,
            parent_agent_run_id=parent_agent_run_id,
            pattern=pattern,
            role_in_pattern=role_in_pattern,
            sequence=sequence,
            iteration=iteration,
            status="pending",
            input_text=input_text,
            metadata=metadata or {},
            created_at=now
        )

    async def get(self, agent_run_id: str) -> Optional[AgentRun]:
        """Get an agent run by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM agent_runs WHERE id = ?", (agent_run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_agent_run(row)

    async def list_for_run(self, run_id: str) -> list[AgentRun]:
        """List all agent runs for a run."""
        cursor = await self._conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ? ORDER BY sequence, iteration",
            (run_id,)
        )

        agent_runs = []
        async for row in cursor:
            agent_runs.append(self._row_to_agent_run(row))

        return agent_runs

    async def list_for_agent(self, agent_id: str) -> list[AgentRun]:
        """List all runs for an agent."""
        cursor = await self._conn.execute(
            "SELECT * FROM agent_runs WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,)
        )

        agent_runs = []
        async for row in cursor:
            agent_runs.append(self._row_to_agent_run(row))

        return agent_runs

    async def update_status(
        self,
        agent_run_id: str,
        status: str,
        output_text: Optional[str] = None
    ) -> None:
        """Update agent run status."""
        now = datetime.utcnow()

        if status == "running":
            await self._conn.execute(
                "UPDATE agent_runs SET status = ?, started_at = ? WHERE id = ?",
                (status, now, agent_run_id)
            )
        elif status in ("completed", "failed"):
            await self._conn.execute(
                "UPDATE agent_runs SET status = ?, output_text = ?, completed_at = ? WHERE id = ?",
                (status, output_text, now, agent_run_id)
            )
        else:
            await self._conn.execute(
                "UPDATE agent_runs SET status = ? WHERE id = ?",
                (status, agent_run_id)
            )

        await self._conn.commit()

    def _row_to_agent_run(self, row) -> AgentRun:
        """Convert database row to AgentRun model."""
        return AgentRun(
            id=row["id"],
            agent_id=row["agent_id"],
            run_id=row["run_id"],
            parent_agent_run_id=row["parent_agent_run_id"],
            pattern=row["pattern"],
            role_in_pattern=row["role_in_pattern"],
            sequence=row["sequence"] or 0,
            iteration=row["iteration"] or 0,
            status=row["status"],
            input_text=row["input_text"],
            output_text=row["output_text"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
        )


class AgentPatternRepository:
    """Repository for saved agent patterns."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        name: str,
        pattern_type: str,
        config: dict,
        description: Optional[str] = None,
        human_involvement: str = "checkpoints",
        max_iterations: int = 3
    ) -> AgentPattern:
        """Create a new agent pattern."""
        pattern_id = str(uuid.uuid4())
        now = datetime.utcnow()

        await self._conn.execute(
            """INSERT INTO agent_patterns
               (id, name, description, pattern_type, config_json, human_involvement, max_iterations, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pattern_id, name, description, pattern_type, json.dumps(config), human_involvement, max_iterations, now, now)
        )
        await self._conn.commit()

        return AgentPattern(
            id=pattern_id,
            name=name,
            description=description,
            pattern_type=pattern_type,
            config=config,
            human_involvement=human_involvement,
            max_iterations=max_iterations,
            created_at=now,
            updated_at=now
        )

    async def get(self, pattern_id: str) -> Optional[AgentPattern]:
        """Get a pattern by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM agent_patterns WHERE id = ?", (pattern_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_pattern(row)

    async def list_all(self) -> list[AgentPattern]:
        """List all patterns."""
        cursor = await self._conn.execute(
            "SELECT * FROM agent_patterns ORDER BY updated_at DESC"
        )

        patterns = []
        async for row in cursor:
            patterns.append(self._row_to_pattern(row))

        return patterns

    async def update(self, pattern_id: str, **kwargs) -> Optional[AgentPattern]:
        """Update pattern fields."""
        allowed = {"name", "description", "pattern_type", "config", "human_involvement", "max_iterations"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if "config" in updates:
            updates["config_json"] = json.dumps(updates.pop("config"))

        if not updates:
            return await self.get(pattern_id)

        updates["updated_at"] = datetime.utcnow()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [pattern_id]

        await self._conn.execute(
            f"UPDATE agent_patterns SET {set_clause} WHERE id = ?", values
        )
        await self._conn.commit()

        return await self.get(pattern_id)

    async def delete(self, pattern_id: str) -> bool:
        """Delete a pattern."""
        cursor = await self._conn.execute(
            "DELETE FROM agent_patterns WHERE id = ?", (pattern_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_pattern(self, row) -> AgentPattern:
        """Convert database row to AgentPattern model."""
        return AgentPattern(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            pattern_type=row["pattern_type"],
            config=json.loads(row["config_json"] or "{}"),
            human_involvement=row["human_involvement"],
            max_iterations=row["max_iterations"] or 3,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
        )


class SessionSnapshotRepository:
    """Repository for persisted session resume snapshots."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def create(
        self,
        run_id: str,
        session_id: str,
        goal: Optional[str],
        summary: dict[str, Any],
        resume_prompt: str,
    ) -> SessionSnapshot:
        snapshot_id = str(uuid.uuid4())
        now = datetime.utcnow()
        await self._conn.execute(
            """INSERT INTO session_snapshots
               (id, run_id, session_id, goal, summary_json, resume_prompt, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                run_id,
                session_id,
                goal,
                json.dumps(summary or {}),
                resume_prompt,
                now,
            )
        )
        await self._conn.commit()
        return SessionSnapshot(
            id=snapshot_id,
            run_id=run_id,
            session_id=session_id,
            goal=goal,
            summary=summary or {},
            resume_prompt=resume_prompt,
            created_at=now,
        )

    async def get_for_run(self, run_id: str) -> Optional[SessionSnapshot]:
        cursor = await self._conn.execute(
            "SELECT * FROM session_snapshots WHERE run_id = ? LIMIT 1",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_snapshot(row)

    async def get_latest_for_session(self, session_id: str) -> Optional[SessionSnapshot]:
        cursor = await self._conn.execute(
            """SELECT * FROM session_snapshots
               WHERE session_id = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_snapshot(row)

    def _row_to_snapshot(self, row) -> SessionSnapshot:
        return SessionSnapshot(
            id=row["id"],
            run_id=row["run_id"],
            session_id=row["session_id"],
            goal=row["goal"],
            summary=json.loads(row["summary_json"] or "{}"),
            resume_prompt=row["resume_prompt"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


class RunMemoryRepository:
    """Repository for persisted structured run memory entries."""

    def __init__(self, connection: aiosqlite.Connection):
        self._conn = connection

    async def upsert(
        self,
        run_id: str,
        session_id: str,
        objective: Optional[str],
        short_summary: str,
        memory: dict[str, Any],
    ) -> RunMemoryEntry:
        existing = await self.get_for_run(run_id)
        now = datetime.utcnow()

        if existing:
            await self._conn.execute(
                """UPDATE run_memory_entries
                   SET objective = ?, short_summary = ?, memory_json = ?, updated_at = ?
                   WHERE run_id = ?""",
                (
                    objective,
                    short_summary,
                    json.dumps(memory or {}),
                    now,
                    run_id,
                ),
            )
            await self._conn.commit()
            refreshed = await self.get_for_run(run_id)
            if refreshed:
                return refreshed

        entry_id = str(uuid.uuid4())
        await self._conn.execute(
            """INSERT INTO run_memory_entries
               (id, run_id, session_id, objective, short_summary, memory_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                run_id,
                session_id,
                objective,
                short_summary,
                json.dumps(memory or {}),
                now,
                now,
            ),
        )
        await self._conn.commit()
        return RunMemoryEntry(
            id=entry_id,
            run_id=run_id,
            session_id=session_id,
            objective=objective,
            short_summary=short_summary,
            memory=memory or {},
            created_at=now,
            updated_at=now,
        )

    async def get_for_run(self, run_id: str) -> Optional[RunMemoryEntry]:
        cursor = await self._conn.execute(
            "SELECT * FROM run_memory_entries WHERE run_id = ? LIMIT 1",
            (run_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_memory(row)

    async def list_for_session(self, session_id: str, limit: int = 50) -> list[RunMemoryEntry]:
        cursor = await self._conn.execute(
            """SELECT * FROM run_memory_entries
               WHERE session_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (session_id, limit),
        )
        items: list[RunMemoryEntry] = []
        async for row in cursor:
            items.append(self._row_to_memory(row))
        return items

    def _row_to_memory(self, row) -> RunMemoryEntry:
        return RunMemoryEntry(
            id=row["id"],
            run_id=row["run_id"],
            session_id=row["session_id"],
            objective=row["objective"],
            short_summary=row["short_summary"] or "",
            memory=json.loads(row["memory_json"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
