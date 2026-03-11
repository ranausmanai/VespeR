"""Parsers for Claude and Codex streaming output formats."""

from __future__ import annotations

import json
from typing import Optional

from ..events.types import Event, EventType, StreamEvent


class BaseStreamParser:
    def __init__(self, session_id: str, run_id: str):
        self.session_id = session_id
        self.run_id = run_id

    def parse_line(self, line: str) -> Optional[Event]:
        raise NotImplementedError


class ClaudeStreamParser(BaseStreamParser):
    """Parses Claude Code's stream-json output into typed events."""

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
        super().__init__(session_id, run_id)
        self._current_tool_id: Optional[str] = None
        self._current_tool_name: Optional[str] = None
        self._current_tool_input_json: str = ""

    def parse_line(self, line: str) -> Optional[Event]:
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=line,
                content_type="text",
                payload={"raw": line},
            )

        return self._parse_json_event(data)

    def _parse_json_event(self, data: dict) -> Optional[Event]:
        event_type = data.get("type", "")
        if event_type == "stream_event":
            inner_event = data.get("event", {})
            return self._parse_inner_event(inner_event, data) if inner_event else None
        if event_type in self.STREAM_TYPE_MAP:
            return self._parse_generic(data, self.STREAM_TYPE_MAP[event_type])
        return self._parse_inner_event(data, data)

    def _parse_inner_event(self, event: dict, wrapper: dict) -> Optional[Event]:
        event_type = event.get("type", "")

        if event_type == "message":
            return self._parse_message(event)
        if event_type == "content_block_start":
            return self._parse_content_block_start(event)
        if event_type == "content_block_delta":
            return self._parse_content_block_delta(event)
        if event_type == "content_block_stop":
            if self._current_tool_id and self._current_tool_name:
                tool_input = {}
                if self._current_tool_input_json:
                    try:
                        tool_input = json.loads(self._current_tool_input_json)
                    except json.JSONDecodeError:
                        tool_input = {"raw": self._current_tool_input_json}

                result = StreamEvent(
                    type=EventType.STREAM_TOOL_USE,
                    session_id=self.session_id,
                    run_id=self.run_id,
                    tool_name=self._current_tool_name,
                    tool_id=self._current_tool_id,
                    tool_input=tool_input,
                    payload={"content_block": {"id": self._current_tool_id, "name": self._current_tool_name, "input": tool_input}},
                )
                self._current_tool_id = None
                self._current_tool_name = None
                self._current_tool_input_json = ""
                return result
            return None
        if event_type == "message_start":
            return self._parse_message_start(event)
        if event_type == "message_delta":
            return self._parse_message_delta(event)
        if event_type == "message_stop":
            return self._parse_message_stop(event)
        if event_type == "error":
            return self._parse_error(event)

        return Event(
            type=EventType.STREAM_ASSISTANT,
            session_id=self.session_id,
            run_id=self.run_id,
            payload=wrapper,
        )

    def _parse_message(self, data: dict) -> StreamEvent:
        role = data.get("role", "assistant")
        content = self._extract_content(data.get("content", []))
        return StreamEvent(
            type=EventType.STREAM_ASSISTANT if role == "assistant" else EventType.STREAM_USER,
            session_id=self.session_id,
            run_id=self.run_id,
            role=role,
            content=content,
            content_type="text",
            payload=data,
        )

    def _parse_message_start(self, data: dict) -> StreamEvent:
        message = data.get("message", {})
        role = message.get("role", "assistant")
        return StreamEvent(
            type=EventType.STREAM_INIT,
            session_id=self.session_id,
            run_id=self.run_id,
            role=role,
            content="",
            payload=data,
        )

    def _parse_message_delta(self, data: dict) -> Optional[StreamEvent]:
        delta = data.get("delta", {})
        usage = data.get("usage", {})
        if usage:
            return StreamEvent(
                type=EventType.STREAM_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                content="",
                payload={"type": "result", "stop_reason": delta.get("stop_reason"), "usage": usage},
            )
        return None

    def _parse_message_stop(self, data: dict) -> StreamEvent:
        return StreamEvent(
            type=EventType.STREAM_RESULT,
            session_id=self.session_id,
            run_id=self.run_id,
            content="",
            payload={"type": "result", "completed": True},
        )

    def _parse_content_block_start(self, data: dict) -> Optional[StreamEvent]:
        content_block = data.get("content_block", {})
        block_type = content_block.get("type", "")
        if block_type == "tool_use":
            self._current_tool_id = content_block.get("id")
            self._current_tool_name = content_block.get("name")
            self._current_tool_input_json = ""
            return None
        if block_type == "text":
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                content=content_block.get("text", ""),
                content_type="text",
                payload=data,
            )
        return None

    def _parse_content_block_delta(self, data: dict) -> Optional[StreamEvent]:
        delta = data.get("delta", {})
        delta_type = delta.get("type", "")
        if delta_type == "text_delta":
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                content=delta.get("text", ""),
                content_type="text_delta",
                payload=data,
            )
        if delta_type == "input_json_delta":
            self._current_tool_input_json += delta.get("partial_json", "")
        return None

    def _parse_error(self, data: dict) -> StreamEvent:
        error = data.get("error", {})
        return StreamEvent(
            type=EventType.STREAM_ERROR,
            session_id=self.session_id,
            run_id=self.run_id,
            content=error.get("message", str(error)),
            is_error=True,
            payload=data,
        )

    def _parse_generic(self, data: dict, event_type: EventType) -> StreamEvent:
        return StreamEvent(
            type=event_type,
            session_id=self.session_id,
            run_id=self.run_id,
            content=self._extract_content(data.get("content", [])),
            payload=data,
        )

    def _extract_content(self, content: list | str) -> str:
        if isinstance(content, str):
            return content
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    texts.append(str(item.get("content", "")))
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts)


class CodexStreamParser(BaseStreamParser):
    """Parses `codex exec --json` output into the app's event model."""

    def __init__(self, session_id: str, run_id: str):
        super().__init__(session_id, run_id)
        self._active_items: dict[str, dict] = {}

    def parse_line(self, line: str) -> Optional[Event]:
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=line,
                content_type="text",
                payload={"raw": line},
            )

        event_type = str(data.get("type") or "")

        if event_type == "thread.started":
            return StreamEvent(
                type=EventType.STREAM_INIT,
                session_id=self.session_id,
                run_id=self.run_id,
                payload=data,
            )
        if event_type in {"turn.started", "turn_summary"}:
            return StreamEvent(
                type=EventType.STREAM_SYSTEM,
                session_id=self.session_id,
                run_id=self.run_id,
                content=str(data.get("summary") or ""),
                payload=data,
            )
        if event_type == "turn.completed":
            usage = data.get("usage") or {}
            result_text = str(data.get("output_text") or data.get("text") or "")
            return StreamEvent(
                type=EventType.STREAM_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                content=result_text,
                payload={"type": "result", "usage": usage, "result": result_text, **data},
            )
        if event_type in {"turn.failed", "error"}:
            message = (
                data.get("message")
                or data.get("error", {}).get("message")
                or data.get("detail")
                or str(data)
            )
            return StreamEvent(
                type=EventType.STREAM_ERROR,
                session_id=self.session_id,
                run_id=self.run_id,
                content=str(message),
                is_error=True,
                payload=data,
            )
        if event_type == "agent_message_delta":
            text = self._extract_text(data)
            if not text:
                return None
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=text,
                content_type="text_delta",
                payload=data,
            )
        if event_type in {"agent_message", "task_complete"}:
            text = self._extract_text(data)
            if not text:
                return None
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=text,
                content_type="text",
                payload=data,
            )
        if event_type.startswith("item."):
            return self._parse_item_event(data)

        return StreamEvent(
            type=EventType.STREAM_SYSTEM,
            session_id=self.session_id,
            run_id=self.run_id,
            payload=data,
        )

    def _parse_item_event(self, data: dict) -> Optional[Event]:
        event_type = str(data.get("type") or "")
        item = data.get("item") or {}
        item_id = str(item.get("id") or data.get("item_id") or "")
        item_type = str(item.get("type") or data.get("item_type") or "")

        if item_id:
            existing = self._active_items.get(item_id, {})
            merged = dict(existing)
            merged.update(item)
            self._active_items[item_id] = merged
            item = merged

        if event_type == "item.started":
            return self._item_started(item_id, item_type, item, data)
        if event_type in {"item.updated", "item.delta"}:
            return self._item_updated(item_id, item_type, item, data)
        if event_type in {"item.completed", "item.finished"}:
            return self._item_completed(item_id, item_type, item, data)
        return None

    def _item_started(self, item_id: str, item_type: str, item: dict, data: dict) -> Optional[Event]:
        if item_type in {"command_execution", "tool_call"}:
            command = str(
                item.get("command")
                or item.get("input", {}).get("command")
                or item.get("raw_command")
                or ""
            )
            return StreamEvent(
                type=EventType.STREAM_TOOL_USE,
                session_id=self.session_id,
                run_id=self.run_id,
                tool_name="Bash",
                tool_id=item_id or None,
                tool_input={"command": command},
                payload=data,
            )
        if item_type in {"mcp_tool_call", "web_search_call"}:
            tool_name = str(item.get("tool_name") or item.get("name") or item_type)
            tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
            return StreamEvent(
                type=EventType.STREAM_TOOL_USE,
                session_id=self.session_id,
                run_id=self.run_id,
                tool_name=tool_name,
                tool_id=item_id or None,
                tool_input=tool_input,
                payload=data,
            )
        return None

    def _item_updated(self, item_id: str, item_type: str, item: dict, data: dict) -> Optional[Event]:
        if item_type == "agent_message":
            text = self._extract_text(data) or self._extract_text(item)
            if not text:
                return None
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=text,
                content_type="text_delta",
                payload=data,
            )
        return None

    def _item_completed(self, item_id: str, item_type: str, item: dict, data: dict) -> Optional[Event]:
        self._active_items.pop(item_id, None)

        if item_type in {"agent_message", "assistant_message"}:
            text = self._extract_text(item) or self._extract_text(data)
            if not text:
                return None
            return StreamEvent(
                type=EventType.STREAM_ASSISTANT,
                session_id=self.session_id,
                run_id=self.run_id,
                role="assistant",
                content=text,
                content_type="text",
                payload=data,
            )

        if item_type in {"command_execution", "tool_call"}:
            command = str(
                item.get("command")
                or item.get("input", {}).get("command")
                or item.get("raw_command")
                or ""
            )
            output = str(
                item.get("output")
                or item.get("stdout")
                or item.get("combined_output")
                or item.get("text")
                or ""
            )
            exit_code = item.get("exit_code")
            is_error = bool(item.get("is_error")) or (exit_code not in (None, 0))
            return StreamEvent(
                type=EventType.STREAM_TOOL_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                tool_name="Bash",
                tool_id=item_id or None,
                tool_input={"command": command},
                tool_output=output,
                is_error=is_error,
                payload={**data, "input": {"command": command}, "output": output, "is_error": is_error, "exit_code": exit_code},
            )

        if item_type in {"mcp_tool_call", "web_search_call"}:
            tool_name = str(item.get("tool_name") or item.get("name") or item_type)
            tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
            output = str(item.get("output") or item.get("result") or item.get("text") or "")
            is_error = bool(item.get("is_error"))
            return StreamEvent(
                type=EventType.STREAM_TOOL_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                tool_name=tool_name,
                tool_id=item_id or None,
                tool_input=tool_input,
                tool_output=output,
                is_error=is_error,
                payload={**data, "input": tool_input, "output": output, "is_error": is_error},
            )

        if item_type == "file_change":
            file_path = str(item.get("path") or item.get("file_path") or "")
            action = str(item.get("action") or "Edit")
            return StreamEvent(
                type=EventType.STREAM_TOOL_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                tool_name=action,
                tool_id=item_id or None,
                tool_input={"path": file_path},
                tool_output=action,
                payload={**data, "input": {"path": file_path}, "output": action},
            )

        if item_type == "reasoning":
            text = self._extract_text(item) or self._extract_text(data)
            if text:
                return StreamEvent(
                    type=EventType.STREAM_SYSTEM,
                    session_id=self.session_id,
                    run_id=self.run_id,
                    content=text,
                    payload=data,
                )
        return None

    def _extract_text(self, data: dict) -> str:
        if not isinstance(data, dict):
            return ""

        candidates = [
            data.get("text"),
            data.get("delta"),
            data.get("content"),
            data.get("output_text"),
            data.get("message"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate

        if isinstance(data.get("content"), list):
            parts: list[str] = []
            for item in data["content"]:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)

        if isinstance(data.get("delta"), dict):
            text = data["delta"].get("text") or data["delta"].get("content")
            if isinstance(text, str):
                return text

        return ""


def build_stream_parser(provider: str, session_id: str, run_id: str) -> BaseStreamParser:
    if provider == "codex":
        return CodexStreamParser(session_id, run_id)
    return ClaudeStreamParser(session_id, run_id)
