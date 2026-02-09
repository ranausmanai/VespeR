"""Agent management API routes."""

from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateAgentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    personality: Optional[str] = None
    system_prompt: Optional[str] = None
    model: str = "sonnet"
    tools: Optional[List[str]] = None
    constraints: Optional[dict] = None


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    personality: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[List[str]] = None
    constraints: Optional[dict] = None


class CreatePatternRequest(BaseModel):
    name: str
    pattern_type: str  # 'solo', 'loop', 'panel', 'debate'
    config: dict
    description: Optional[str] = None
    human_involvement: str = "checkpoints"  # 'autonomous', 'checkpoints', 'on_demand'
    max_iterations: int = 3


class UpdatePatternRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pattern_type: Optional[str] = None
    config: Optional[dict] = None
    human_involvement: Optional[str] = None
    max_iterations: Optional[int] = None


# Agent endpoints

@router.get("")
async def list_agents(request: Request):
    """List all agents."""
    db = request.app.state.db
    agents = await db.agents.list_all()

    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "role": a.role,
                "model": a.model,
                "tools": a.tools,
                "constraints": a.constraints,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in agents
        ]
    }


@router.post("")
async def create_agent(request: Request, body: CreateAgentRequest):
    """Create a new agent."""
    db = request.app.state.db

    agent = await db.agents.create(
        name=body.name,
        description=body.description,
        role=body.role,
        personality=body.personality,
        system_prompt=body.system_prompt,
        model=body.model,
        tools=body.tools,
        constraints=body.constraints
    )

    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "role": agent.role,
        "personality": agent.personality,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "tools": agent.tools,
        "constraints": agent.constraints,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


@router.get("/{agent_id}")
async def get_agent(request: Request, agent_id: str):
    """Get an agent by ID with full details."""
    db = request.app.state.db

    agent = await db.agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get run history for this agent
    agent_runs = await db.agent_runs.list_for_agent(agent_id)

    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "role": agent.role,
        "personality": agent.personality,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "tools": agent.tools,
        "constraints": agent.constraints,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        "run_history": [
            {
                "id": ar.id,
                "run_id": ar.run_id,
                "pattern": ar.pattern,
                "role_in_pattern": ar.role_in_pattern,
                "status": ar.status,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
            }
            for ar in agent_runs[:20]  # Limit to recent 20
        ]
    }


@router.put("/{agent_id}")
async def update_agent(request: Request, agent_id: str, body: UpdateAgentRequest):
    """Update an agent."""
    db = request.app.state.db

    agent = await db.agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Build update dict from non-None fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    if updates:
        agent = await db.agents.update(agent_id, **updates)

    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "role": agent.role,
        "personality": agent.personality,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "tools": agent.tools,
        "constraints": agent.constraints,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


@router.delete("/{agent_id}")
async def delete_agent(request: Request, agent_id: str):
    """Delete an agent."""
    db = request.app.state.db

    agent = await db.agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    deleted = await db.agents.delete(agent_id)

    return {"deleted": deleted, "id": agent_id}


@router.get("/{agent_id}/runs")
async def get_agent_runs(request: Request, agent_id: str, limit: int = 50):
    """Get run history for an agent."""
    db = request.app.state.db

    agent = await db.agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_runs = await db.agent_runs.list_for_agent(agent_id)

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "runs": [
            {
                "id": ar.id,
                "run_id": ar.run_id,
                "pattern": ar.pattern,
                "role_in_pattern": ar.role_in_pattern,
                "sequence": ar.sequence,
                "iteration": ar.iteration,
                "status": ar.status,
                "input_text": ar.input_text[:200] + "..." if ar.input_text and len(ar.input_text) > 200 else ar.input_text,
                "output_text": ar.output_text[:200] + "..." if ar.output_text and len(ar.output_text) > 200 else ar.output_text,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
                "created_at": ar.created_at.isoformat() if ar.created_at else None,
            }
            for ar in agent_runs[:limit]
        ]
    }
