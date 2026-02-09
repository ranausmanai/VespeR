"""Agent and pattern execution API routes."""

import asyncio
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ExecuteAgentRequest(BaseModel):
    session_id: str
    agent_id: str
    input_text: str


class ExecutePatternRequest(BaseModel):
    session_id: str
    input_text: str


class HumanInputRequest(BaseModel):
    decision: str


@router.post("/agent")
async def execute_agent(request: Request, body: ExecuteAgentRequest):
    """Execute a single agent (solo pattern)."""
    db = request.app.state.db
    agent_executor = request.app.state.agent_executor

    # Get session
    session = await db.sessions.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get agent
    agent = await db.agents.get(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Create a temporary solo pattern
    pattern = await db.agent_patterns.create(
        name=f"Solo: {agent.name}",
        pattern_type="solo",
        config={"agent_id": agent.id},
        human_involvement="autonomous"
    )

    execution_stream = agent_executor.execute_pattern(
        pattern=pattern,
        session_id=body.session_id,
        input_text=body.input_text,
        working_dir=session.working_dir
    )

    # Prime the stream to obtain run_id from the first emitted event.
    try:
        first_event = await execution_stream.__anext__()
    except StopAsyncIteration:
        await db.agent_patterns.delete(pattern.id)
        raise HTTPException(status_code=500, detail="Agent execution failed to start")
    run_id = first_event.run_id

    # Continue execution in background
    async def run_execution():
        try:
            async for event in execution_stream:
                pass  # Events broadcast via EventBus
        except Exception as e:
            print(f"Agent execution error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up temporary pattern
            await db.agent_patterns.delete(pattern.id)

    # Store task reference
    if not hasattr(request.app.state, '_execution_tasks'):
        request.app.state._execution_tasks = {}

    task = asyncio.create_task(run_execution())
    request.app.state._execution_tasks[run_id] = task

    return {
        "status": "started",
        "run_id": run_id,
        "pattern_id": pattern.id,
        "agent_id": agent.id,
        "agent_name": agent.name,
        "message": "Execution started. Watch WebSocket for events."
    }


@router.post("/pattern/{pattern_id}")
async def execute_pattern(request: Request, pattern_id: str, body: ExecutePatternRequest):
    """Execute a saved agent pattern."""
    db = request.app.state.db
    agent_executor = request.app.state.agent_executor

    # Get session
    session = await db.sessions.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get pattern
    pattern = await db.agent_patterns.get(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    execution_stream = agent_executor.execute_pattern(
        pattern=pattern,
        session_id=body.session_id,
        input_text=body.input_text,
        working_dir=session.working_dir
    )

    # Prime the stream to obtain run_id from the first emitted event.
    try:
        first_event = await execution_stream.__anext__()
    except StopAsyncIteration:
        raise HTTPException(status_code=500, detail="Pattern execution failed to start")
    run_id = first_event.run_id

    # Continue execution in background
    async def run_execution():
        try:
            async for event in execution_stream:
                pass  # Events broadcast via EventBus
        except Exception as e:
            print(f"Pattern execution error: {e}")
            import traceback
            traceback.print_exc()

    # Store task reference
    if not hasattr(request.app.state, '_execution_tasks'):
        request.app.state._execution_tasks = {}

    task = asyncio.create_task(run_execution())
    request.app.state._execution_tasks[run_id] = task

    return {
        "status": "started",
        "run_id": run_id,
        "pattern_id": pattern.id,
        "pattern_name": pattern.name,
        "pattern_type": pattern.pattern_type,
        "message": "Pattern execution started. Watch WebSocket for events."
    }


@router.post("/run/{run_id}/input")
async def provide_human_input(request: Request, run_id: str, body: HumanInputRequest):
    """Provide human input for a checkpoint."""
    agent_executor = request.app.state.agent_executor

    success = await agent_executor.provide_human_input(run_id, body.decision)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="No active execution awaiting input for this run"
        )

    return {"status": "input_accepted", "run_id": run_id}


@router.get("/run/{run_id}/state")
async def get_execution_state(request: Request, run_id: str):
    """Get current execution state."""
    agent_executor = request.app.state.agent_executor

    state = agent_executor.get_execution_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="No active execution for this run")

    return state


@router.get("/run/{run_id}/agents")
async def get_run_agent_runs(request: Request, run_id: str):
    """Get all agent runs for a pattern execution."""
    db = request.app.state.db

    run = await db.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    agent_runs = await db.agent_runs.list_for_run(run_id)

    return {
        "run_id": run_id,
        "agent_runs": [
            {
                "id": ar.id,
                "agent_id": ar.agent_id,
                "pattern": ar.pattern,
                "role_in_pattern": ar.role_in_pattern,
                "sequence": ar.sequence,
                "iteration": ar.iteration,
                "status": ar.status,
                "input_text": ar.input_text[:200] + "..." if ar.input_text and len(ar.input_text) > 200 else ar.input_text,
                "output_text": ar.output_text[:500] + "..." if ar.output_text and len(ar.output_text) > 500 else ar.output_text,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
            }
            for ar in agent_runs
        ]
    }


@router.get("/active")
async def list_active_pattern_executions(request: Request):
    """List currently active pattern executions."""
    agent_executor = request.app.state.agent_executor
    active = agent_executor.list_active_executions()
    return {"active_executions": active, "count": len(active)}
