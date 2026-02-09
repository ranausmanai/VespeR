"""Control API routes for managing running Claude sessions."""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class InjectMessageRequest(BaseModel):
    message: str


class RetryRequest(BaseModel):
    from_event_id: str
    modified_prompt: Optional[str] = None


@router.post("/runs/{run_id}/pause")
async def pause_run(request: Request, run_id: str):
    """Pause a running Claude session."""
    session_manager = request.app.state.session_manager

    success = await session_manager.pause_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or not running")

    return {"status": "paused", "run_id": run_id}


@router.post("/runs/{run_id}/resume")
async def resume_run(request: Request, run_id: str):
    """Resume a paused Claude session."""
    session_manager = request.app.state.session_manager

    success = await session_manager.resume_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or not paused")

    return {"status": "resumed", "run_id": run_id}


@router.post("/runs/{run_id}/abort")
async def abort_run(request: Request, run_id: str):
    """Abort a running Claude session."""
    session_manager = request.app.state.session_manager

    success = await session_manager.abort_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or not running")

    return {"status": "aborted", "run_id": run_id}


@router.post("/runs/{run_id}/inject")
async def inject_message(request: Request, run_id: str, body: InjectMessageRequest):
    """Inject a user message into the running session."""
    session_manager = request.app.state.session_manager

    success = await session_manager.inject_message(run_id, body.message)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or not running")

    return {"status": "injected", "run_id": run_id, "message": body.message}


@router.get("/active")
async def list_active_runs(request: Request):
    """List all currently active runs."""
    session_manager = request.app.state.session_manager
    db = request.app.state.db

    active_run_ids = session_manager.get_active_runs()

    runs = []
    for run_id in active_run_ids:
        status = await session_manager.get_run_status(run_id)
        run = await db.runs.get(run_id)
        if run:
            runs.append({
                "id": run.id,
                "session_id": run.session_id,
                "prompt": run.prompt[:100] + "..." if len(run.prompt) > 100 else run.prompt,
                "status": run.status,
                "model": run.model,
                "is_paused": status.get("is_paused", False),
                "pid": status.get("pid"),
                "tokens_in": status.get("tokens_in", 0),
                "tokens_out": status.get("tokens_out", 0),
            })

    return {"active_runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}/status")
async def get_run_status(request: Request, run_id: str):
    """Get detailed status of a run."""
    session_manager = request.app.state.session_manager

    status = await session_manager.get_run_status(run_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return status
