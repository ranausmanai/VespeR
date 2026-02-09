"""CLI command to replay a past Claude Code session."""

import argparse
import asyncio
import sys
from datetime import datetime


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Add the 'replay' subcommand parser."""
    parser = subparsers.add_parser(
        "replay",
        help="Replay a past Claude Code session",
        description="Replay events from a previous run with timing simulation"
    )
    parser.add_argument(
        "run_id",
        help="Run ID to replay"
    )
    parser.add_argument(
        "--speed",
        "-s",
        type=float,
        default=1.0,
        help="Playback speed multiplier (default: 1.0)"
    )
    parser.add_argument(
        "--from-event",
        help="Start from specific event ID"
    )
    parser.add_argument(
        "--from-sequence",
        type=int,
        default=0,
        help="Start from sequence number"
    )
    parser.add_argument(
        "--no-timing",
        action="store_true",
        help="Disable timing simulation (instant replay)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output events as JSON lines"
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Open UI to view the run"
    )
    return parser


async def execute_replay(args: argparse.Namespace) -> int:
    """Execute the replay command."""
    from ..persistence.database import Database
    from ..events.bus import EventBus
    from ..events.types import EventType

    # Connect to database
    db = Database()
    await db.connect()

    try:
        # Get run info
        run = await db.runs.get(args.run_id)
        if not run:
            print(f"Error: Run {args.run_id} not found")
            return 1

        session = await db.sessions.get(run.session_id)

        if args.ui:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:8420/runs/{args.run_id}")
            return 0

        # Get starting sequence
        from_sequence = args.from_sequence

        if args.from_event:
            event = await db.events.get(args.from_event)
            if event:
                from_sequence = event.sequence
            else:
                print(f"Warning: Event {args.from_event} not found, starting from beginning")

        # Print header
        if not args.json:
            print(f"\n{'='*60}")
            print(f"  Replaying Run: {run.id}")
            print(f"  Session: {session.name if session else 'Unknown'}")
            print(f"  Prompt: {run.prompt[:50]}...")
            print(f"  Status: {run.status}")
            print(f"  Speed: {args.speed}x")
            print(f"{'='*60}\n")

        # Create event bus for replay
        event_bus = EventBus(db.events)

        # Replay events
        last_timestamp = None
        event_count = 0

        async for event in event_bus.replay(args.run_id, from_sequence):
            event_count += 1

            # Simulate timing
            if not args.no_timing and last_timestamp and args.speed > 0:
                delay = (event.timestamp - last_timestamp).total_seconds() / args.speed
                delay = min(delay, 2.0)  # Cap at 2 seconds
                if delay > 0:
                    await asyncio.sleep(delay)

            last_timestamp = event.timestamp

            # Output based on format
            if args.json:
                import json
                print(json.dumps(event.to_dict(), default=str))
                continue

            # Pretty print
            timestamp = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
            event_type = event.type.value

            if event.type == EventType.STREAM_ASSISTANT:
                content = event.payload.get("content", "")[:80]
                if content:
                    print(f"[{timestamp}] {content}")

            elif event.type == EventType.STREAM_TOOL_USE:
                tool_name = event.payload.get("name", "unknown")
                print(f"[{timestamp}] 🔧 Tool: {tool_name}")

            elif event.type == EventType.STREAM_TOOL_RESULT:
                output = event.payload.get("output", "")[:60]
                is_error = event.payload.get("is_error", False)
                icon = "❌" if is_error else "✅"
                print(f"[{timestamp}] {icon} Result: {output}...")

            elif event.type == EventType.GIT_SNAPSHOT:
                dirty = event.payload.get("dirty_files", [])
                print(f"[{timestamp}] 📁 Git: {len(dirty)} files changed")

            elif event.type in (EventType.RUN_STARTED, EventType.RUN_COMPLETED, EventType.RUN_FAILED):
                status_icons = {
                    EventType.RUN_STARTED: "▶️",
                    EventType.RUN_COMPLETED: "✅",
                    EventType.RUN_FAILED: "❌"
                }
                print(f"[{timestamp}] {status_icons.get(event.type, '•')} {event_type}")

            elif event.type in (EventType.RUN_PAUSED, EventType.RUN_RESUMED):
                print(f"[{timestamp}] ⏸️ {event_type}")

            elif event.type.value.startswith("intervention."):
                print(f"[{timestamp}] 👤 {event_type}")

        # Print summary
        if not args.json:
            print(f"\n{'='*60}")
            print(f"  Replay complete: {event_count} events")
            print(f"{'='*60}\n")

        return 0

    finally:
        await db.disconnect()


def run_command(args: argparse.Namespace) -> int:
    """Execute the replay command."""
    return asyncio.run(execute_replay(args))
