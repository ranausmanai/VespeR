"""CLI command to execute Claude Code with visual tracking."""

import argparse
import asyncio
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Add the 'run' subcommand parser."""
    parser = subparsers.add_parser(
        "run",
        help="Execute Claude Code with visual tracking",
        description="Run Claude Code and track all events for visualization"
    )
    parser.add_argument(
        "prompt",
        help="The prompt to execute"
    )
    parser.add_argument(
        "--session",
        "-s",
        help="Session name or ID"
    )
    parser.add_argument(
        "--model",
        "-m",
        default="sonnet",
        help="Claude model to use (default: sonnet)"
    )
    parser.add_argument(
        "--workdir",
        "-w",
        default=".",
        help="Working directory (default: current)"
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Open UI in browser after starting"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress output streaming to console"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output events as JSON lines"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="UI server port (default: 8420)"
    )
    return parser


def check_server(port: int) -> bool:
    """Check if the UI server is running."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except:
        return False


def create_session_via_api(port: int, working_dir: str, name: str = None) -> dict:
    """Create a session via the web API."""
    data = json.dumps({"working_dir": working_dir, "name": name}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/sessions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_sessions_via_api(port: int) -> list:
    """Get sessions via the web API."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/sessions")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return data.get("sessions", [])


async def execute_run(args: argparse.Namespace) -> int:
    """Execute the run command by calling the web API."""
    port = args.port

    # Check if UI server is running
    if not check_server(port):
        print(f"Error: Agentling UI server is not running on port {port}")
        print(f"Start it first with: agentling ui")
        return 1

    working_dir = str(Path(args.workdir).resolve())

    # Find or create session
    sessions = get_sessions_via_api(port)
    session = next((s for s in sessions if s["working_dir"] == working_dir), None)

    if not session:
        session = create_session_via_api(port, working_dir, args.session or Path(working_dir).name)

    session_id = session["id"]

    # Start run via API
    run_data = json.dumps({
        "session_id": session_id,
        "prompt": args.prompt,
        "model": args.model
    }).encode()

    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/runs",
        data=run_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            run = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error starting run: {e.read().decode()}")
        return 1

    run_id = run["id"]

    print(f"\n{'='*60}")
    print(f"  Run ID: {run_id}")
    print(f"  Session: {session.get('name', 'unknown')} ({session_id[:8]}...)")
    print(f"  Model: {args.model}")
    print(f"  Working Dir: {working_dir}")
    print(f"  View in UI: http://127.0.0.1:{port}/runs/{run_id}")
    print(f"{'='*60}\n")

    if args.ui:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}/runs/{run_id}")

    # Poll for run completion and stream events
    last_sequence = 0
    start_time = datetime.utcnow()

    while True:
        await asyncio.sleep(0.5)

        # Get run status
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/runs/{run_id}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                run_status = json.loads(resp.read().decode())
        except:
            continue

        # Get new events
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/runs/{run_id}/events?from_sequence={last_sequence}"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                events_data = json.loads(resp.read().decode())
                events = events_data.get("events", [])
        except:
            events = []

        # Display events
        for event in events:
            seq = event.get("sequence", 0)
            if seq >= last_sequence:
                last_sequence = seq + 1

                if args.json:
                    print(json.dumps(event))
                elif not args.quiet:
                    display_event(event)

        # Check if run is complete
        status = run_status.get("status", "")
        if status in ("completed", "failed"):
            duration = (datetime.utcnow() - start_time).total_seconds()
            tokens = run_status.get("tokens_in", 0) + run_status.get("tokens_out", 0)
            cost = run_status.get("cost_usd", 0)

            print(f"\n{'='*60}")
            print(f"  Status: {status}")
            print(f"  Duration: {duration:.1f}s")
            print(f"  Tokens: {tokens}")
            print(f"  Cost: ${cost:.4f}")
            print(f"  View in UI: http://127.0.0.1:{port}/runs/{run_id}")
            print(f"{'='*60}\n")
            break

    return 0 if status == "completed" else 1


def display_event(event: dict):
    """Display an event in a readable format."""
    event_type = event.get("type", "")
    payload = event.get("payload", {})

    if event_type == "stream.assistant":
        content = event.get("content") or payload.get("content", "")
        if content:
            sys.stdout.write(content)
            sys.stdout.flush()

    elif event_type == "stream.tool_use":
        tool_name = event.get("tool_name") or payload.get("name", "unknown")
        print(f"\n[Tool: {tool_name}]")

    elif event_type == "stream.tool_result":
        is_error = event.get("is_error") or payload.get("is_error", False)
        output = event.get("tool_output") or payload.get("output", "")
        if output:
            preview = str(output)[:100]
            status = "Error" if is_error else "Result"
            print(f"[{status}: {preview}{'...' if len(str(output)) > 100 else ''}]")

    elif event_type == "git.snapshot":
        dirty = payload.get("dirty_files", [])
        if dirty:
            print(f"\n[Git: {len(dirty)} files changed]")

    elif event_type == "run.started":
        print("[Run started]")

    elif event_type in ("run.completed", "run.failed"):
        pass  # Handled in main loop


def run_command(args: argparse.Namespace) -> int:
    """Execute the run command."""
    return asyncio.run(execute_run(args))
