# VespeR

Visual control plane for Claude Code workflows.

VespeR is for teams/solo builders who want more than a single chat window:
- reusable agents
- reusable multi-agent patterns
- execution DAG + timeline visibility
- resumable interactive sessions with compact context

CLI commands:
- `vesper` (preferred)
- `agentling` (backward-compatible alias)

## What It Is

VespeR gives you:
1. Interactive coding sessions you can rejoin.
2. Agent Dock to run specialist agents (reviewer, security, strategist, etc.).
3. Pattern execution (Solo, Build+Review loop, Expert panel, Debate).
4. Execution observability: DAG, timeline, activity stream, per-agent flow.
5. Session snapshots for smart resume of ended interactive work.

## Core Use Cases

1. Build + review loop
- Use the `Build + Review Loop` pattern to generate code and auto-review before merge.

2. Release go/no-go checks
- Use `Release Readiness Panel` for security/performance/product sign-off in one run.

3. Long-running coding continuity
- End session, then `Resume this run` to restart with compressed context.

4. Debugging agent behavior
- Inspect `Agent Execution` with DAG/Timeline/Split to see exactly what happened.

## Requirements

- Python 3.10+
- Node.js 18+
- Claude Code CLI available in PATH

## Quick Start

```bash
# 1) install backend package
pip install -e .

# 2) install frontend deps + build
npm -C frontend install
npm -C frontend run build

# 3) run VespeR UI
vesper ui --port 8420 --no-browser
```

Open `http://127.0.0.1:8420`.

## Main Commands

```bash
# UI
vesper ui

# One-shot tracked run
vesper run "add JWT auth with tests"

# Replay run
vesper replay <run-id>
```

## Pattern Test Prompts

Build + Review Loop:
```text
Add src/utils/slugify.js with slugify(text) and tests in tests/slugify.test.js. Run npm test.
```

Release Readiness Panel:
```text
Assess this repo for v0.1 alpha release readiness. Return go/no-go, top 5 risks, and this-week fixes.
```

## UI Notes

- `Sessions > Resume this run` starts a new interactive run seeded with snapshot context.
- `Dashboard > Active Work` includes interactive sessions, active patterns, and one-shot runs.
- Sidebar badges:
  - `Interactive`: active interactive sessions
  - `Patterns`: active pattern executions

## Development

```bash
# backend + API server + built frontend
vesper ui --port 8420

# frontend dev (optional)
npm -C frontend run dev
```

## Screenshots / GIFs

Recommended to add before broader launch:
- Dashboard with Active Work
- Agent Execution (split view)
- Pattern run result
- Interactive resume flow

Place assets under `docs/screenshots/` and reference them here.

## License

MIT
