"""Event API routes for querying event history."""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


@router.get("/{event_id}")
async def get_event(request: Request, event_id: str):
    """Get a single event by ID."""
    db = request.app.state.db

    event = await db.events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event  # Already a dict


@router.get("")
async def search_events(
    request: Request,
    run_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_sequence: int = 0,
    limit: int = 100
):
    """Search events with optional filters."""
    db = request.app.state.db

    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")

    events = []
    count = 0

    async for event in db.events.get_events_for_run(run_id, from_sequence):
        # Filter by type if specified
        if event_type and event["type"] != event_type:
            continue

        events.append(event)  # Already a dict
        count += 1

        if count >= limit:
            break

    return {
        "events": events,
        "count": len(events),
        "filters": {
            "run_id": run_id,
            "event_type": event_type,
            "from_sequence": from_sequence
        }
    }


@router.get("/types/list")
async def list_event_types():
    """List all available event types."""
    from ...events.types import EventType

    return {
        "types": [
            {
                "value": t.value,
                "name": t.name,
                "category": t.value.split(".")[0]
            }
            for t in EventType
        ]
    }
