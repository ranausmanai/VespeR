"""WebSocket connection manager for real-time event streaming."""

import asyncio
import json
from typing import Set, Optional

from fastapi import WebSocket, WebSocketDisconnect

from ...events.types import Event


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        # Global connections (receive all events)
        self._global_connections: Set[WebSocket] = set()
        # Run-specific connections
        self._run_connections: dict[str, Set[WebSocket]] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: Optional[str] = None) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()

        async with self._lock:
            if run_id:
                if run_id not in self._run_connections:
                    self._run_connections[run_id] = set()
                self._run_connections[run_id].add(websocket)
            else:
                self._global_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket, run_id: Optional[str] = None) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if run_id and run_id in self._run_connections:
                self._run_connections[run_id].discard(websocket)
                if not self._run_connections[run_id]:
                    del self._run_connections[run_id]
            else:
                self._global_connections.discard(websocket)

    async def broadcast_event(self, event: Event) -> None:
        """Broadcast an event to all relevant connections."""
        message = {
            "type": "event",
            "data": event.to_dict()
        }
        json_message = json.dumps(message, default=str)

        # Collect connections to send to
        async with self._lock:
            connections = set(self._global_connections)

            # Add run-specific connections
            if event.run_id in self._run_connections:
                connections.update(self._run_connections[event.run_id])

        # Send to all connections
        await self._send_to_all(connections, json_message)

    async def send_to_run(self, run_id: str, message: dict) -> None:
        """Send a message to all connections watching a specific run."""
        json_message = json.dumps(message, default=str)

        async with self._lock:
            connections = set(self._global_connections)
            if run_id in self._run_connections:
                connections.update(self._run_connections[run_id])

        await self._send_to_all(connections, json_message)

    async def _send_to_all(self, connections: Set[WebSocket], message: str) -> None:
        """Send a message to all specified connections."""
        dead_connections = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._global_connections.discard(ws)
                    for run_conns in self._run_connections.values():
                        run_conns.discard(ws)

    def get_connection_count(self, run_id: Optional[str] = None) -> int:
        """Get the number of active connections."""
        if run_id:
            return len(self._run_connections.get(run_id, set()))
        return len(self._global_connections)


# Global WebSocket manager instance (set by app lifespan)
_ws_manager: Optional[WebSocketManager] = None


async def websocket_endpoint(websocket: WebSocket, run_id: Optional[str] = None):
    """WebSocket endpoint for real-time event streaming."""
    # Get manager from app state
    ws_manager: WebSocketManager = websocket.app.state.ws_manager

    await ws_manager.connect(websocket, run_id)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "data": {"run_id": run_id}
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()

                # Handle ping/pong for keepalive
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                # Handle subscription changes
                elif data.get("type") == "subscribe":
                    new_run_id = data.get("run_id")
                    if new_run_id:
                        await ws_manager.disconnect(websocket, run_id)
                        await ws_manager.connect(websocket, new_run_id)
                        run_id = new_run_id

            except Exception:
                # Connection closed or error
                break

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket, run_id)
