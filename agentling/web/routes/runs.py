"""Run management API routes."""

import asyncio
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()


class StartRunRequest(BaseModel):
    session_id: str
    prompt: str
    model: str = "sonnet"


class BranchRunRequest(BaseModel):
    from_event_id: str
    modified_prompt: Optional[str] = None


@router.get("")
async def list_runs(
    request: Request,
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List runs, optionally filtered by session or status."""
    db = request.app.state.db

    if session_id:
        runs = await db.runs.list_for_session(session_id)
    else:
        # Get all runs (would need to add this method)
        runs = []
        sessions = await db.sessions.list_all()
        for session in sessions[:10]:  # Limit sessions checked
            session_runs = await db.runs.list_for_session(session.id)
            runs.extend(session_runs)

    # Filter by status if specified
    if status:
        runs = [r for r in runs if r.status == status]

    # Limit results
    runs = runs[:limit]

    return {
        "runs": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "prompt": r.prompt[:100] + "..." if len(r.prompt) > 100 else r.prompt,
                "status": r.status,
                "model": r.model,
                "parent_run_id": r.parent_run_id,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": r.cost_usd,
                "duration_ms": r.duration_ms,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@router.post("")
async def start_run(request: Request, body: StartRunRequest, background_tasks: BackgroundTasks):
    """Start a new Claude Code run."""
    session_manager = request.app.state.session_manager

    # Start the run
    run = await session_manager.start_run(
        session_id=body.session_id,
        prompt=body.prompt,
        model=body.model
    )

    # Run the stream in background using asyncio.create_task
    async def run_stream():
        try:
            async for event in session_manager.stream_events(run.id):
                # Events are automatically broadcast via WebSocket through the EventBus
                pass
        except Exception as e:
            print(f"Run error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up task reference
            if hasattr(request.app.state, '_run_tasks'):
                request.app.state._run_tasks.pop(run.id, None)

    # Store task reference to prevent garbage collection
    if not hasattr(request.app.state, '_run_tasks'):
        request.app.state._run_tasks = {}
    task = asyncio.create_task(run_stream())
    request.app.state._run_tasks[run.id] = task

    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": "running",
        "prompt": body.prompt,
        "model": body.model,
        "websocket_url": f"/ws/runs/{run.id}"
    }


@router.get("/{run_id}")
async def get_run(request: Request, run_id: str):
    """Get a run by ID with full details."""
    db = request.app.state.db
    session_manager = request.app.state.session_manager

    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get live status if running
    status = await session_manager.get_run_status(run_id)

    # Get event count
    event_count = await db.events.count_for_run(run_id)

    # Get git snapshots
    git_snapshots = await db.git_snapshots.get_for_run(run_id)

    return {
        "id": run.id,
        "session_id": run.session_id,
        "prompt": run.prompt,
        "status": run.status,
        "model": run.model,
        "parent_run_id": run.parent_run_id,
        "branch_point_event_id": run.branch_point_event_id,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_usd": run.cost_usd,
        "duration_ms": run.duration_ms,
        "final_output": run.final_output,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "is_active": status.get("is_active", False),
        "is_paused": status.get("is_paused", False),
        "pid": status.get("pid"),
        "event_count": event_count,
        "git_snapshots": git_snapshots,
    }


@router.post("/{run_id}/branch")
async def branch_run(
    request: Request,
    run_id: str,
    body: BranchRunRequest,
    background_tasks: BackgroundTasks
):
    """Create a new run branching from a specific event."""
    session_manager = request.app.state.session_manager

    try:
        new_run = await session_manager.branch_run(
            run_id=run_id,
            from_event_id=body.from_event_id,
            modified_prompt=body.modified_prompt
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Run the stream in background
    async def run_stream():
        try:
            async for _ in session_manager.stream_events(new_run.id):
                pass
        except Exception as e:
            print(f"Branch run error: {e}")

    background_tasks.add_task(asyncio.create_task, run_stream())

    return {
        "id": new_run.id,
        "parent_run_id": run_id,
        "branch_point_event_id": body.from_event_id,
        "status": "running",
        "websocket_url": f"/ws/runs/{new_run.id}"
    }


@router.get("/{run_id}/events")
async def get_run_events(
    request: Request,
    run_id: str,
    from_sequence: int = 0,
    limit: int = 1000
):
    """Get events for a run."""
    db = request.app.state.db

    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    events = []
    count = 0
    async for event in db.events.get_events_for_run(run_id, from_sequence):
        events.append(event)  # Already a dict
        count += 1
        if count >= limit:
            break

    return {
        "run_id": run_id,
        "events": events,
        "count": len(events),
        "from_sequence": from_sequence
    }


@router.get("/{run_id}/git")
async def get_run_git_history(request: Request, run_id: str):
    """Get git snapshot history for a run."""
    db = request.app.state.db

    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    snapshots = await db.git_snapshots.get_for_run(run_id)

    return {
        "run_id": run_id,
        "snapshots": snapshots
    }
