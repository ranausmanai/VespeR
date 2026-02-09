"""Async event bus with persistence and replay support."""

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable, AsyncIterator, Optional, TYPE_CHECKING

from .types import Event, EventType

if TYPE_CHECKING:
    from ..persistence.repositories import EventRepository

EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Async pub/sub event bus with SQLite persistence."""

    def __init__(self, repository: Optional["EventRepository"] = None):
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._repository = repository
        self._sequence_counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to a specific event type. Returns unsubscribe function."""
        self._handlers[event_type].append(handler)
        return lambda: self._handlers[event_type].remove(handler)

    def subscribe_all(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to all event types. Returns unsubscribe function."""
        self._global_handlers.append(handler)
        return lambda: self._global_handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event - persists first, then notifies handlers."""
        async with self._lock:
            # Assign sequence number
            run_id = event.run_id
            seq = self._sequence_counters.get(run_id, 0)
            event.sequence = seq
            self._sequence_counters[run_id] = seq + 1

        # Persist first (event sourcing guarantee)
        if self._repository:
            await self._repository.save(event)

        # Notify type-specific handlers
        type_handlers = self._handlers.get(event.type, [])

        # Notify global handlers
        all_handlers = type_handlers + self._global_handlers

        if all_handlers:
            await asyncio.gather(
                *[self._safe_call(h, event) for h in all_handlers],
                return_exceptions=True
            )

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call handler with exception handling."""
        try:
            await handler(event)
        except Exception as e:
            # Log but don't crash
            print(f"Event handler error: {e}")

    async def replay(
        self,
        run_id: str,
        from_sequence: int = 0,
        to_sequence: Optional[int] = None
    ) -> AsyncIterator[Event]:
        """Replay events for a run from a given sequence."""
        if not self._repository:
            return

        async for event in self._repository.get_events_for_run(
            run_id, from_sequence, to_sequence
        ):
            yield event

    async def get_last_sequence(self, run_id: str) -> int:
        """Get the last sequence number for a run."""
        return self._sequence_counters.get(run_id, 0)

    def reset_sequence(self, run_id: str) -> None:
        """Reset sequence counter for a run (used when starting fresh)."""
        self._sequence_counters[run_id] = 0
