"""Session management API routes."""

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateSessionRequest(BaseModel):
    working_dir: str
    name: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    name: Optional[str]
    working_dir: str
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


def _pick_directory_native() -> tuple[Optional[str], str]:
    """Open a native folder picker and return (directory, method)."""
    if sys.platform == "darwin":
        script = (
            'try\n'
            'set chosenFolder to POSIX path of (choose folder with prompt "Select Project Directory")\n'
            'return chosenFolder\n'
            'on error number -128\n'
            'return ""\n'
            'end try'
        )
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        selected = (proc.stdout or "").strip()
        if selected:
            return str(Path(selected).expanduser().resolve()), "osascript"
        return None, "osascript"

    # Fallback to tkinter for other platforms and macOS fallback.
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Select Project Directory")
        root.destroy()
        if selected:
            return str(Path(selected).expanduser().resolve()), "tkinter"
        return None, "tkinter"
    except Exception:
        return None, "unavailable"


@router.get("")
async def list_sessions(request: Request, status: Optional[str] = None):
    """List all sessions."""
    db = request.app.state.db
    sessions = await db.sessions.list_all(status)

    return {
        "sessions": [
            {
                "id": s.id,
                "name": s.name,
                "working_dir": s.working_dir,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.post("/pick-directory")
async def pick_directory():
    """Open a native directory picker on the local machine."""
    directory, method = await asyncio.to_thread(_pick_directory_native)
    return {
        "directory": directory,
        "cancelled": directory is None,
        "method": method,
    }


@router.post("")
async def create_session(request: Request, body: CreateSessionRequest):
    """Create a new session."""
    db = request.app.state.db

    session = await db.sessions.create(
        working_dir=body.working_dir,
        name=body.name
    )

    return {
        "id": session.id,
        "name": session.name,
        "working_dir": session.working_dir,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.get("/{session_id}")
async def get_session(request: Request, session_id: str):
    """Get a session by ID."""
    db = request.app.state.db

    session = await db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get runs for this session
    runs = await db.runs.list_for_session(session_id)

    return {
        "id": session.id,
        "name": session.name,
        "working_dir": session.working_dir,
        "status": session.status,
        "config": session.config,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "runs": [
            {
                "id": r.id,
                "prompt": r.prompt[:100] + "..." if len(r.prompt) > 100 else r.prompt,
                "status": r.status,
                "model": r.model,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@router.patch("/{session_id}")
async def update_session(request: Request, session_id: str, body: dict):
    """Update a session."""
    db = request.app.state.db

    session = await db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Only allow updating certain fields
    allowed = {"name", "status", "config"}
    updates = {k: v for k, v in body.items() if k in allowed}

    if updates:
        await db.sessions.update(session_id, **updates)

    # Return updated session
    session = await db.sessions.get(session_id)
    return {
        "id": session.id,
        "name": session.name,
        "working_dir": session.working_dir,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.delete("/{session_id}")
async def archive_session(request: Request, session_id: str):
    """Archive a session (soft delete)."""
    db = request.app.state.db

    session = await db.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.sessions.update(session_id, status="archived")

    return {"status": "archived", "id": session_id}
