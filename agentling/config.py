from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentling.models import AppConfig, BudgetConfig, GraphConfig, LoggingConfig, NodeSpec, ProviderConfig


DEFAULT_ROLES = [
    "planner",
    "requirement_structurer",
    "edge_case_analyzer",
    "implementation_generator",
    "test_writer",
    "refactor_agent",
    "security_reviewer",
    "performance_reviewer",
    "final_synthesizer",
]


def default_graph() -> GraphConfig:
    return GraphConfig(
        nodes=[
            NodeSpec("planner", "Planner Agent", "Decompose the task into an execution plan."),
            NodeSpec(
                "requirement_structurer",
                "Requirement Structurer",
                "Convert requirements into clear acceptance criteria.",
                ["planner"],
            ),
            NodeSpec(
                "edge_case_analyzer",
                "Edge Case Analyzer",
                "Identify edge cases, failure paths, and hidden assumptions.",
                ["planner"],
            ),
            NodeSpec(
                "implementation_generator",
                "Implementation Generator",
                "Produce implementation strategy and concrete code.",
                ["requirement_structurer", "edge_case_analyzer"],
            ),
            NodeSpec(
                "test_writer",
                "Test Writer",
                "Write tests that verify core behavior and edge cases.",
                ["implementation_generator", "edge_case_analyzer"],
            ),
            NodeSpec(
                "refactor_agent",
                "Refactor Agent",
                "Improve clarity, maintainability, and modularity.",
                ["implementation_generator"],
            ),
            NodeSpec(
                "security_reviewer",
                "Security Reviewer",
                "Review generated solution for security risks and mitigations.",
                ["implementation_generator", "edge_case_analyzer"],
            ),
            NodeSpec(
                "performance_reviewer",
                "Performance Reviewer",
                "Review performance implications and optimize hotspots.",
                ["implementation_generator"],
            ),
            NodeSpec(
                "final_synthesizer",
                "Final Synthesizer",
                "Merge strongest ideas into one final response with rationale.",
                ["test_writer", "refactor_agent", "security_reviewer", "performance_reviewer"],
            ),
        ]
    )


def _merge_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _graph_from_dict(raw: dict[str, Any]) -> GraphConfig:
    nodes: list[NodeSpec] = []
    for node in raw.get("nodes", []):
        nodes.append(
            NodeSpec(
                id=node["id"],
                role=node.get("role", node["id"]),
                prompt_template=node.get("prompt_template", ""),
                depends_on=node.get("depends_on", []) or [],
                enabled=bool(node.get("enabled", True)),
            )
        )
    return GraphConfig(nodes=nodes)


def load_config(path: str | Path | None = None) -> AppConfig:
    defaults: dict[str, Any] = {
        "provider": {
            "type": "openai",
            "model": "gpt-4o-mini",
            "timeout_seconds": 120,
            "max_tokens": 1800,
            "temperature": 0.2,
        },
        "parallelism": 4,
        "dry_run": False,
        "cache_enabled": True,
        "execute_generated_tests": False,
        "budget": {"max_total_tokens": 200000, "max_total_cost_usd": 5.0},
        "logging": {"level": "info", "show_agent_steps": True},
        "enabled_agents": [],
        "graph": {"nodes": []},
    }

    target = Path(path or "agentling.config.yaml")
    incoming: dict[str, Any] = {}
    if target.exists():
        incoming = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    merged = _merge_dict(defaults, incoming)
    graph = _graph_from_dict(merged.get("graph", {}))
    if not graph.nodes:
        graph = default_graph()

    provider = ProviderConfig(**merged["provider"])
    budget = BudgetConfig(**merged["budget"])
    logging = LoggingConfig(**merged["logging"])

    return AppConfig(
        provider=provider,
        parallelism=int(merged["parallelism"]),
        dry_run=bool(merged["dry_run"]),
        cache_enabled=bool(merged["cache_enabled"]),
        execute_generated_tests=bool(merged["execute_generated_tests"]),
        budget=budget,
        logging=logging,
        enabled_agents=merged.get("enabled_agents", []),
        graph=graph,
    )
