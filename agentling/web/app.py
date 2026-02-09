"""FastAPI application factory for VespeR web UI.

Originally launched as Agentling and later rebranded to VespeR.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import sessions, runs, events, control, interactive, agents, patterns, execute
from .websocket.handler import WebSocketManager
from ..persistence.database import Database
from ..events.bus import EventBus
from ..session.manager import SessionManager
from ..agents.executor import AgentExecutor


DEFAULT_AGENT_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "feature_builder",
        "name": "Feature Builder",
        "description": "Builds production-ready code for requested features with clear file-level changes.",
        "role": "generator",
        "personality": "Pragmatic senior engineer focused on shippable outcomes.",
        "system_prompt": (
            "You are a coding agent. Build complete, working implementations with minimal churn. "
            "Prefer small, safe changes; include tests when appropriate; explain decisions briefly."
        ),
        "model": "sonnet",
    },
    {
        "template_id": "code_reviewer",
        "name": "Code Reviewer",
        "description": "Reviews code for correctness, regressions, and missing tests before merge.",
        "role": "critic",
        "personality": "Detail-oriented reviewer who prioritizes risk and concrete fixes.",
        "system_prompt": (
            "Review code changes with a bug-first mindset. Identify correctness issues, edge cases, "
            "security risks, and missing tests. Be concise and specific."
        ),
        "model": "haiku",
    },
    {
        "template_id": "security_auditor",
        "name": "Security Auditor",
        "description": "Finds security issues in app/backend code and recommends concrete remediations.",
        "role": "expert",
        "personality": "Cautious and threat-model driven.",
        "system_prompt": (
            "Audit code for authz/authn flaws, injection risks, secrets exposure, unsafe deserialization, "
            "and dependency risk. Provide severity and exact mitigation steps."
        ),
        "model": "sonnet",
    },
    {
        "template_id": "performance_optimizer",
        "name": "Performance Optimizer",
        "description": "Improves runtime performance, database efficiency, and frontend responsiveness.",
        "role": "expert",
        "personality": "Measurement-focused optimizer.",
        "system_prompt": (
            "Identify hotspots, unnecessary allocations, blocking operations, N+1 queries, and render inefficiencies. "
            "Recommend measurable, low-risk optimizations."
        ),
        "model": "sonnet",
    },
    {
        "template_id": "product_strategist",
        "name": "Product Strategist",
        "description": "Turns feature requests into clear delivery plans, scope cuts, and launch milestones.",
        "role": "planner",
        "personality": "Outcome-focused PM mindset.",
        "system_prompt": (
            "Convert requests into phased delivery plans with MVP scope, risks, and validation strategy. "
            "Optimize for user impact and execution speed."
        ),
        "model": "haiku",
    },
]


def _build_default_pattern_templates(agent_ids: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "template_id": "quick_build_solo",
            "name": "Quick Build (Solo)",
            "description": "One coding agent builds the requested feature end-to-end.",
            "pattern_type": "solo",
            "config": {
                "template_id": "quick_build_solo",
                "template": True,
                "agent_id": agent_ids["feature_builder"],
            },
            "human_involvement": "autonomous",
            "max_iterations": 1,
        },
        {
            "template_id": "build_review_loop",
            "name": "Build + Review Loop",
            "description": "Feature builder iterates with a code reviewer until quality bar is met.",
            "pattern_type": "loop",
            "config": {
                "template_id": "build_review_loop",
                "template": True,
                "generator_id": agent_ids["feature_builder"],
                "critic_id": agent_ids["code_reviewer"],
            },
            "human_involvement": "checkpoints",
            "max_iterations": 3,
        },
        {
            "template_id": "release_readiness_panel",
            "name": "Release Readiness Panel",
            "description": "Security, performance, and product experts review implementation and synthesize a release decision.",
            "pattern_type": "panel",
            "config": {
                "template_id": "release_readiness_panel",
                "template": True,
                "agents": [
                    agent_ids["security_auditor"],
                    agent_ids["performance_optimizer"],
                    agent_ids["product_strategist"],
                ],
                "synthesizer_id": agent_ids["code_reviewer"],
            },
            "human_involvement": "checkpoints",
            "max_iterations": 2,
        },
    ]


async def _ensure_default_templates(db: Database) -> None:
    """Seed default coding-focused agents and patterns (idempotent)."""
    agents = await db.agents.list_all()
    agents_by_template_id: dict[str, str] = {}
    for agent in agents:
        template_id = (agent.constraints or {}).get("template_id")
        if isinstance(template_id, str):
            agents_by_template_id[template_id] = agent.id

    for template in DEFAULT_AGENT_TEMPLATES:
        template_id = template["template_id"]
        if template_id in agents_by_template_id:
            continue

        created = await db.agents.create(
            name=template["name"],
            description=template["description"],
            role=template["role"],
            personality=template["personality"],
            system_prompt=template["system_prompt"],
            model=template["model"],
            constraints={
                "template": True,
                "template_id": template_id,
                "template_version": 1,
            },
        )
        agents_by_template_id[template_id] = created.id

    patterns = await db.agent_patterns.list_all()
    existing_pattern_template_ids = {
        p.config.get("template_id")
        for p in patterns
        if isinstance(p.config, dict) and isinstance(p.config.get("template_id"), str)
    }

    for template in _build_default_pattern_templates(agents_by_template_id):
        if template["template_id"] in existing_pattern_template_ids:
            continue

        await db.agent_patterns.create(
            name=template["name"],
            pattern_type=template["pattern_type"],
            config=template["config"],
            description=template["description"],
            human_involvement=template["human_involvement"],
            max_iterations=template["max_iterations"],
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    db = Database()
    await db.connect()
    await _ensure_default_templates(db)

    # Initialize components
    ws_manager = WebSocketManager()
    event_bus = EventBus(db.events)
    session_manager = SessionManager(db, event_bus)
    agent_executor = AgentExecutor(db, event_bus)

    # Subscribe WebSocket manager to all events for real-time updates
    event_bus.subscribe_all(ws_manager.broadcast_event)

    # Store in app state
    app.state.db = db
    app.state.ws_manager = ws_manager
    app.state.event_bus = event_bus
    app.state.session_manager = session_manager
    app.state.agent_executor = agent_executor

    yield

    # Shutdown
    await db.disconnect()


def create_app(serve_frontend: bool = True) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="VespeR",
        description="Visual control plane for Claude Code",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])
    app.include_router(interactive.router, prefix="/api/interactive", tags=["interactive"])
    app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
    app.include_router(execute.router, prefix="/api/execute", tags=["execute"])

    # WebSocket endpoint
    from .websocket.handler import websocket_endpoint
    app.add_api_websocket_route("/ws", websocket_endpoint)
    app.add_api_websocket_route("/ws/runs/{run_id}", websocket_endpoint)

    # Health check
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "vesper"}

    # Serve frontend in production
    if serve_frontend:
        frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        if frontend_dist.exists():
            app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

            @app.get("/favicon.svg")
            async def serve_favicon_svg():
                favicon_path = frontend_dist / "favicon.svg"
                if favicon_path.exists():
                    return FileResponse(favicon_path)
                return {"error": "Favicon not found"}

            @app.get("/favicon.ico")
            async def serve_favicon_ico():
                # Some browsers still request .ico; serve SVG as a fallback.
                favicon_path = frontend_dist / "favicon.svg"
                if favicon_path.exists():
                    return FileResponse(favicon_path)
                return {"error": "Favicon not found"}

            @app.get("/{full_path:path}")
            async def serve_spa(full_path: str):
                """Serve the SPA for all non-API routes."""
                index_path = frontend_dist / "index.html"
                if index_path.exists():
                    return FileResponse(index_path)
                return {"error": "Frontend not built"}

    return app
