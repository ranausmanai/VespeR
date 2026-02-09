"""Event type definitions for the Agentling event-sourcing system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid


class EventType(str, Enum):
    """All event types in the system."""

    # Session lifecycle
    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"
    SESSION_COMPLETED = "session.completed"
    SESSION_FAILED = "session.failed"

    # Run lifecycle
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_BRANCHED = "run.branched"

    # Claude stream events (from stream-json)
    STREAM_INIT = "stream.init"
    STREAM_SYSTEM = "stream.system"
    STREAM_ASSISTANT = "stream.assistant"
    STREAM_USER = "stream.user"
    STREAM_TOOL_USE = "stream.tool_use"
    STREAM_TOOL_RESULT = "stream.tool_result"
    STREAM_RESULT = "stream.result"
    STREAM_ERROR = "stream.error"

    # Human intervention
    INTERVENTION_PAUSE = "intervention.pause"
    INTERVENTION_RESUME = "intervention.resume"
    INTERVENTION_PROMPT_EDIT = "intervention.prompt_edit"
    INTERVENTION_RETRY = "intervention.retry"
    INTERVENTION_BRANCH = "intervention.branch"
    INTERVENTION_INJECT = "intervention.inject"
    INTERVENTION_ABORT = "intervention.abort"

    # Git tracking
    GIT_SNAPSHOT = "git.snapshot"
    GIT_DIFF = "git.diff"
    GIT_FILE_CHANGE = "git.file_change"

    # Metrics
    METRICS_TOKENS = "metrics.tokens"
    METRICS_COST = "metrics.cost"
    METRICS_DURATION = "metrics.duration"


@dataclass
class Event:
    """Base event class for all system events."""

    type: EventType
    session_id: str
    run_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence: int = 0
    parent_event_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
            "payload": self.payload,
            "parent_event_id": self.parent_event_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize event from dictionary."""
        return cls(
            id=data["id"],
            type=EventType(data["type"]),
            session_id=data["session_id"],
            run_id=data["run_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            sequence=data["sequence"],
            payload=data.get("payload", {}),
            parent_event_id=data.get("parent_event_id"),
        )


@dataclass
class StreamEvent(Event):
    """Event from Claude's stream-json output."""

    role: str = "assistant"
    content: str = ""
    content_type: str = "text"
    tool_name: Optional[str] = None
    tool_id: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_output: Optional[str] = None
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "role": self.role,
            "content": self.content,
            "content_type": self.content_type,
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "is_error": self.is_error,
        })
        return d


@dataclass
class GitSnapshotEvent(Event):
    """Captures git state at a point in time."""

    commit_hash: str = ""
    branch: str = ""
    dirty_files: list[str] = field(default_factory=list)
    staged_files: list[str] = field(default_factory=list)
    diff_stat: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "commit_hash": self.commit_hash,
            "branch": self.branch,
            "dirty_files": self.dirty_files,
            "staged_files": self.staged_files,
            "diff_stat": self.diff_stat,
        })
        return d


@dataclass
class InterventionEvent(Event):
    """Human intervention during a run."""

    intervention_type: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "intervention_type": self.intervention_type,
            "input_data": self.input_data,
            "result": self.result,
        })
        return d


@dataclass
class MetricsEvent(Event):
    """Token and cost metrics."""

    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
        })
        return d
