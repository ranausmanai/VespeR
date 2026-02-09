"""Agent pattern management API routes."""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


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


@router.get("")
async def list_patterns(request: Request):
    """List all agent patterns."""
    db = request.app.state.db
    patterns = await db.agent_patterns.list_all()

    return {
        "patterns": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "pattern_type": p.pattern_type,
                "config": p.config,
                "human_involvement": p.human_involvement,
                "max_iterations": p.max_iterations,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in patterns
        ]
    }


@router.post("")
async def create_pattern(request: Request, body: CreatePatternRequest):
    """Create a new agent pattern."""
    db = request.app.state.db

    # Validate pattern_type
    valid_types = {"solo", "loop", "panel", "debate"}
    if body.pattern_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pattern_type. Must be one of: {', '.join(valid_types)}"
        )

    # Validate human_involvement
    valid_involvement = {"autonomous", "checkpoints", "on_demand"}
    if body.human_involvement not in valid_involvement:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid human_involvement. Must be one of: {', '.join(valid_involvement)}"
        )

    pattern = await db.agent_patterns.create(
        name=body.name,
        pattern_type=body.pattern_type,
        config=body.config,
        description=body.description,
        human_involvement=body.human_involvement,
        max_iterations=body.max_iterations
    )

    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern_type": pattern.pattern_type,
        "config": pattern.config,
        "human_involvement": pattern.human_involvement,
        "max_iterations": pattern.max_iterations,
        "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
        "updated_at": pattern.updated_at.isoformat() if pattern.updated_at else None,
    }


@router.get("/{pattern_id}")
async def get_pattern(request: Request, pattern_id: str):
    """Get a pattern by ID with full details."""
    db = request.app.state.db

    pattern = await db.agent_patterns.get(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern_type": pattern.pattern_type,
        "config": pattern.config,
        "human_involvement": pattern.human_involvement,
        "max_iterations": pattern.max_iterations,
        "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
        "updated_at": pattern.updated_at.isoformat() if pattern.updated_at else None,
    }


@router.put("/{pattern_id}")
async def update_pattern(request: Request, pattern_id: str, body: UpdatePatternRequest):
    """Update a pattern."""
    db = request.app.state.db

    pattern = await db.agent_patterns.get(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # Validate pattern_type if provided
    if body.pattern_type:
        valid_types = {"solo", "loop", "panel", "debate"}
        if body.pattern_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pattern_type. Must be one of: {', '.join(valid_types)}"
            )

    # Validate human_involvement if provided
    if body.human_involvement:
        valid_involvement = {"autonomous", "checkpoints", "on_demand"}
        if body.human_involvement not in valid_involvement:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid human_involvement. Must be one of: {', '.join(valid_involvement)}"
            )

    # Build update dict from non-None fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    if updates:
        pattern = await db.agent_patterns.update(pattern_id, **updates)

    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern_type": pattern.pattern_type,
        "config": pattern.config,
        "human_involvement": pattern.human_involvement,
        "max_iterations": pattern.max_iterations,
        "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
        "updated_at": pattern.updated_at.isoformat() if pattern.updated_at else None,
    }


@router.delete("/{pattern_id}")
async def delete_pattern(request: Request, pattern_id: str):
    """Delete a pattern."""
    db = request.app.state.db

    pattern = await db.agent_patterns.get(pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    deleted = await db.agent_patterns.delete(pattern_id)

    return {"deleted": deleted, "id": pattern_id}
