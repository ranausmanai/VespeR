"""Parser for Claude Code's stream-json output format."""

import json
from typing import Optional
from ..events.types import Event, EventType, StreamEvent


class ClaudeStreamParser:
    """Parses Claude Code's stream-json output into typed events."""

    # Map Claude stream types to our event types
    STREAM_TYPE_MAP = {
        "system": EventType.STREAM_SYSTEM,
        "assistant": EventType.STREAM_ASSISTANT,
        "user": EventType.STREAM_USER,
        "tool_use": EventType.STREAM_TOOL_USE,
        "tool_result": EventType.STREAM_TOOL_RESULT,
        "result": EventType.STREAM_RESULT,
        "error": EventType.STREAM_ERROR,
    }

    def __init__(self, session_id: str, run_id: str):
        self.session_id = session_id
        self.run_id = run_id
        self._buffer = ""
        self._current_tool_id: Optional[str] = None
        self._current_tool_name: Optional[str] = None
        self._current_tool_input_json: str = ""  # Accumulates JSON fragments

    def parse_line(self, line: str) -> Optional[Event]:
        """Parse a single line from Claude's stream output."""
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON, might be raw output - wrap it
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=line,
                content_type="text",
                payload={"raw": line}
            )

        return self._parse_json_event(data)

    def _parse_json_event(self, data: dict) -> Optional[Event]:
        """Parse a JSON event from Claude's stream."""
        event_type = data.get("type", "")

        # Handle stream_event wrapper - unwrap and process the inner event
        if event_type == "stream_event":
            inner_event = data.get("event", {})
            if inner_event:
                return self._parse_inner_event(inner_event, data)
            return None

        # Handle top-level event types (assistant, result, system, etc.)
        if event_type in self.STREAM_TYPE_MAP:
            return self._parse_generic(data, self.STREAM_TYPE_MAP[event_type])

        # Handle direct event types (for backwards compatibility)
        return self._parse_inner_event(data, data)

    def _parse_inner_event(self, event: dict, wrapper: dict) -> Optional[Event]:
        """Parse the inner event from a stream_event wrapper."""
        event_type = event.get("type", "")

        if event_type == "message":
            return self._parse_message(event)
        elif event_type == "content_block_start":
            return self._parse_content_block_start(event)
        elif event_type == "content_block_delta":
            return self._parse_content_block_delta(event)
        elif event_type == "content_block_stop":
            # If we have accumulated tool input, emit the tool_use event now
            if self._current_tool_id and self._current_tool_name:
                tool_input = {}
                if self._current_tool_input_json:
                    try:
                        tool_input = json.loads(self._current_tool_input_json)
                    except json.JSONDecodeError:
                        tool_input = {"raw": self._current_tool_input_json}

                event = StreamEvent(
                    type=EventType.STREAM_TOOL_USE,
                    session_id=self.session_id,
                    run_id=self.run_id,
                    tool_name=self._current_tool_name,
                    tool_id=self._current_tool_id,
                    tool_input=tool_input,
                    payload={"content_block": {"id": self._current_tool_id, "name": self._current_tool_name, "input": tool_input}}
                )
                # Reset state
                self._current_tool_id = None
                self._current_tool_name = None
                self._current_tool_input_json = ""
                return event
            return None
        elif event_type == "message_start":
            return self._parse_message_start(event)
        elif event_type == "message_delta":
            return self._parse_message_delta(event)
        elif event_type == "message_stop":
            return self._parse_message_stop(event)
        elif event_type == "error":
            return self._parse_error(event)

        # Unknown type - log it
        return Event(
            type=EventType.STREAM_ASSISTANT,
            session_id=self.session_id,
            run_id=self.run_id,
            payload=wrapper
        )

    def _parse_message(self, data: dict) -> StreamEvent:
        """Parse a complete message event."""
        role = data.get("role", "assistant")
        content = self._extract_content(data.get("content", []))

        return StreamEvent(
            type=EventType.STREAM_ASSISTANT if role == "assistant" else EventType.STREAM_USER,
            session_id=self.session_id,
            run_id=self.run_id,
            role=role,
            content=content,
            content_type="text",
            payload=data
        )

    def _parse_message_start(self, data: dict) -> StreamEvent:
        """Parse message_start event."""
        message = data.get("message", {})
        role = message.get("role", "assistant")

        return StreamEvent(
            type=EventType.STREAM_INIT,
            session_id=self.session_id,
            run_id=self.run_id,
            role=role,
            content="",
            payload=data
        )

    def _parse_message_delta(self, data: dict) -> Optional[StreamEvent]:
        """Parse message_delta event (contains usage stats)."""
        delta = data.get("delta", {})
        usage = data.get("usage", {})

        if usage:
            return StreamEvent(
                type=EventType.STREAM_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                content="",
                payload={
                    "stop_reason": delta.get("stop_reason"),
                    "usage": usage
                }
            )

        return None

    def _parse_message_stop(self, data: dict) -> StreamEvent:
        """Parse message_stop event."""
        return StreamEvent(
            type=EventType.STREAM_RESULT,
            session_id=self.session_id,
            run_id=self.run_id,
            content="",
            payload={"completed": True}
        )

    def _parse_content_block_start(self, data: dict) -> Optional[StreamEvent]:
        """Parse content_block_start event."""
        content_block = data.get("content_block", {})
        block_type = content_block.get("type", "")

        if block_type == "tool_use":
            self._current_tool_id = content_block.get("id")
            self._current_tool_name = content_block.get("name")
            self._current_tool_input_json = ""  # Reset JSON buffer for new tool
            # Don't emit event yet - wait until we have the full input
            return None
        elif block_type == "text":
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                content=content_block.get("text", ""),
                content_type="text",
                payload=data
            )

        return None

    def _parse_content_block_delta(self, data: dict) -> Optional[StreamEvent]:
        """Parse content_block_delta event (streaming content)."""
        delta = data.get("delta", {})
        delta_type = delta.get("type", "")

        if delta_type == "text_delta":
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                content=delta.get("text", ""),
                content_type="text_delta",
                payload=data
            )
        elif delta_type == "input_json_delta":
            # Accumulate JSON fragments for tool input
            self._current_tool_input_json += delta.get("partial_json", "")
            return None

        return None

    def _parse_error(self, data: dict) -> StreamEvent:
        """Parse error event."""
        error = data.get("error", {})
        return StreamEvent(
            type=EventType.STREAM_ERROR,
            session_id=self.session_id,
            run_id=self.run_id,
            content=error.get("message", str(error)),
            is_error=True,
            payload=data
        )

    def _parse_generic(self, data: dict, event_type: EventType) -> StreamEvent:
        """Parse a generic stream event."""
        return StreamEvent(
            type=event_type,
            session_id=self.session_id,
            run_id=self.run_id,
            content=self._extract_content(data.get("content", [])),
            payload=data
        )

    def _extract_content(self, content: list) -> str:
        """Extract text content from a content array."""
        if isinstance(content, str):
            return content

        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    texts.append(str(item.get("content", "")))
            elif isinstance(item, str):
                texts.append(item)

        return "\n".join(texts)

    def parse_tool_result(self, tool_id: str, output: str, is_error: bool = False) -> StreamEvent:
        """Create a tool result event."""
        return StreamEvent(
            type=EventType.STREAM_TOOL_RESULT,
            session_id=self.session_id,
            run_id=self.run_id,
            tool_id=tool_id,
            tool_output=output,
            is_error=is_error,
            payload={"tool_use_id": tool_id, "output": output, "is_error": is_error}
        )
