"""Agentling CLI - Visual control plane for Claude Code."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agentling.config import load_config
from agentling.orchestrator import Orchestrator


def _invoked_name() -> str:
    name = Path(sys.argv[0]).name.strip().lower()
    return "vesper" if name == "vesper" else "agentling"


def _build_parser() -> argparse.ArgumentParser:
    cmd = _invoked_name()
    parser = argparse.ArgumentParser(
        prog=cmd,
        description="VespeR: Visual control plane for Claude Code with multi-agent orchestration.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # UI command
    from agentling.commands import ui
    ui.add_parser(subparsers)

    # Run command (visual tracking)
    from agentling.commands import run
    run.add_parser(subparsers)

    # Replay command
    from agentling.commands import replay
    replay.add_parser(subparsers)

    # Original orchestration command (now as 'orchestrate' subcommand)
    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Run multi-agent orchestration",
        description="Execute instruction through the agent graph"
    )
    orchestrate_parser.add_argument("instruction", help="User instruction for the agent graph.")
    orchestrate_parser.add_argument("--config", default="agentling.config.yaml", help="Path to config YAML file.")
    orchestrate_parser.add_argument("--dry-run", action="store_true", help="Simulate orchestration without provider calls.")
    orchestrate_parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of markdown report.")

    # Legacy: Allow running without subcommand for backwards compatibility
    parser.add_argument("instruction", nargs="?", help="User instruction (legacy mode)")
    parser.add_argument("--config", default="agentling.config.yaml", help="Path to config YAML file.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate orchestration without provider calls.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit structured JSON instead of markdown report.")

    return parser


def _render_markdown(summary) -> str:
    lines = [
        "# Agentling Run",
        "",
        f"- Provider: `{summary.provider}`",
        f"- Duration: `{summary.total_duration_s:.2f}s`",
        f"- Tokens In: `{summary.total_tokens_in}`",
        f"- Tokens Out: `{summary.total_tokens_out}`",
        f"- Agents: `{', '.join(summary.selected_agents)}`",
        "",
        "## Agent Scores",
    ]
    for item in summary.per_agent:
        issue_text = f" issues={len(item.issues)}" if item.issues else ""
        lines.append(
            f"- `{item.node_id}` score={item.score} valid={item.validation_passed} "
            f"tokens=({item.tokens_in}/{item.tokens_out}) time={item.duration_s:.2f}s{issue_text}"
        )
    lines.extend(["", "## Final Output", "", summary.final_output])
    return "\n".join(lines)


async def _run_orchestration(args: argparse.Namespace) -> int:
    cmd = _invoked_name()
    instruction = getattr(args, "instruction", None)
    if not instruction:
        print(f"Instruction is required. Example: {cmd} orchestrate \"build CLI\"", file=sys.stderr)
        return 2

    config = load_config(args.config)
    if args.dry_run:
        config.dry_run = True

    orchestrator = Orchestrator(config)
    summary = await orchestrator.run(instruction)

    json_output = getattr(args, "json", False) or getattr(args, "json_output", False)

    if json_output:
        payload = {
            "instruction": summary.instruction,
            "provider": summary.provider,
            "duration_s": summary.total_duration_s,
            "tokens_in": summary.total_tokens_in,
            "tokens_out": summary.total_tokens_out,
            "selected_agents": summary.selected_agents,
            "final_output": summary.final_output,
            "per_agent": [
                {
                    "node_id": a.node_id,
                    "role": a.role,
                    "score": a.score,
                    "validation_passed": a.validation_passed,
                    "tokens_in": a.tokens_in,
                    "tokens_out": a.tokens_out,
                    "duration_s": a.duration_s,
                    "issues": a.issues,
                    "output": a.output,
                }
                for a in summary.per_agent
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_markdown(summary))

    return 0


def main() -> None:
    cmd = _invoked_name()
    parser = _build_parser()
    args = parser.parse_args()

    # Handle subcommands
    if args.command == "ui":
        from agentling.commands import ui
        code = ui.run_command(args)
    elif args.command == "run":
        from agentling.commands import run
        code = run.run_command(args)
    elif args.command == "replay":
        from agentling.commands import replay
        code = replay.run_command(args)
    elif args.command == "orchestrate":
        code = asyncio.run(_run_orchestration(args))
    elif args.instruction:
        # Legacy mode: run orchestration directly
        code = asyncio.run(_run_orchestration(args))
    else:
        # No command and no instruction - show help
        print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║       🌌 VespeR - Control Plane for Claude Code            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Commands:
  {cmd} ui              Start the visual web UI
  {cmd} run "<prompt>"  Run Claude Code with tracking
  {cmd} replay <id>     Replay a past session
  {cmd} orchestrate     Run multi-agent orchestration

Quick Start:
  {cmd} ui              # Open the visual interface
  {cmd} run "fix bug"   # Run with event tracking

For more help:
  {cmd} <command> --help
        """.format(cmd=cmd))
        code = 0

    raise SystemExit(code)


if __name__ == "__main__":
    main()
