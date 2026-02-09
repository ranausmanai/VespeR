from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BudgetConfig:
    max_total_tokens: int = 200_000
    max_total_cost_usd: float = 5.0


@dataclass(slots=True)
class LoggingConfig:
    level: str = "info"
    show_agent_steps: bool = True


@dataclass(slots=True)
class ProviderConfig:
    type: str = "openai"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 120
    max_tokens: int = 1800
    temperature: float = 0.2
    command: str | None = None
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeSpec:
    id: str
    role: str
    prompt_template: str
    depends_on: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(slots=True)
class GraphConfig:
    nodes: list[NodeSpec] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    parallelism: int = 4
    dry_run: bool = False
    cache_enabled: bool = True
    execute_generated_tests: bool = False
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    enabled_agents: list[str] = field(default_factory=list)
    graph: GraphConfig = field(default_factory=GraphConfig)


@dataclass(slots=True)
class AgentResult:
    node_id: str
    role: str
    output: str
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    validation_passed: bool = True
    score: float = 0.0
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunSummary:
    instruction: str
    provider: str
    total_tokens_in: int
    total_tokens_out: int
    total_duration_s: float
    selected_agents: list[str]
    final_output: str
    per_agent: list[AgentResult] = field(default_factory=list)
