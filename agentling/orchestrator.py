from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Iterable

from agentling.cache import ResultCache
from agentling.graph import AgentGraph
from agentling.models import AgentResult, AppConfig, NodeSpec, RunSummary
from agentling.providers import ProviderError, ProviderResponse, build_provider
from agentling.providers.openai_provider import OpenAIProvider
from agentling.scoring import total_score
from agentling.validators import combine_validations, validate_json_schema, validate_python_syntax

OPTIONAL_ROLES = {"test_writer", "refactor_agent", "security_reviewer", "performance_reviewer"}


class Orchestrator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.provider = build_provider(config.provider)
        self.cache = ResultCache() if config.cache_enabled else None

    async def run(self, instruction: str) -> RunSummary:
        start = time.perf_counter()
        graph = AgentGraph(self.config.graph)
        selected_ids = self._select_nodes(graph, instruction)

        results: dict[str, AgentResult] = {}
        completed: set[str] = set()
        scheduled: set[str] = set()
        running: dict[asyncio.Task[AgentResult], str] = {}

        total_tokens_in = 0
        total_tokens_out = 0

        async def schedule(node: NodeSpec) -> None:
            scheduled.add(node.id)
            task = asyncio.create_task(self._run_node(node, instruction, results))
            running[task] = node.id

        while len(completed) < len(selected_ids):
            ready_nodes = [
                n
                for n in graph.ready_nodes(completed=completed, scheduled=scheduled)
                if n.id in selected_ids
            ]

            for node in ready_nodes:
                if len(running) >= max(1, self.config.parallelism):
                    break
                if self._would_exceed_budget(total_tokens_in, total_tokens_out, node):
                    if node.id in OPTIONAL_ROLES:
                        results[node.id] = AgentResult(
                            node_id=node.id,
                            role=node.role,
                            output="Skipped due to token budget constraints.",
                            validation_passed=True,
                            score=5.0,
                            issues=["Budget constraint skip"],
                        )
                        completed.add(node.id)
                        scheduled.add(node.id)
                        continue
                await schedule(node)

            if not running:
                for node_id in selected_ids:
                    if node_id not in completed:
                        completed.add(node_id)
                        results[node_id] = AgentResult(
                            node_id=node_id,
                            role=node_id,
                            output="Execution skipped because no runnable dependency path remained.",
                            score=1.0,
                            validation_passed=False,
                            issues=["Unrunnable graph path"],
                        )
                break

            done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                node_id = running.pop(task)
                completed.add(node_id)
                result = task.result()
                results[node_id] = result
                total_tokens_in += result.tokens_in
                total_tokens_out += result.tokens_out

        per_agent = [results[node_id] for node_id in graph.topological_order() if node_id in results]
        final_output = self._final_output(per_agent)
        duration = time.perf_counter() - start
        return RunSummary(
            instruction=instruction,
            provider=self.config.provider.type,
            total_tokens_in=total_tokens_in,
            total_tokens_out=total_tokens_out,
            total_duration_s=duration,
            selected_agents=selected_ids,
            final_output=final_output,
            per_agent=per_agent,
        )

    async def _run_node(
        self,
        node: NodeSpec,
        instruction: str,
        prior_results: dict[str, AgentResult],
    ) -> AgentResult:
        started = time.perf_counter()
        prompt = self._build_prompt(node, instruction, prior_results)

        if self.config.dry_run:
            text = (
                f"[dry-run] {node.role} executed.\n"
                f"Summary: simulated output for node '{node.id}'.\n"
                "Self-critique score: 7.5"
            )
            out = ProviderResponse(text=text, tokens_in=0, tokens_out=0)
        else:
            cached = self.cache.get(prompt) if self.cache else None
            if cached:
                out = ProviderResponse(text=cached, tokens_in=0, tokens_out=0)
            else:
                out = await self._safe_generate(prompt)
                if self.cache:
                    self.cache.set(prompt, out.text)

        validations = combine_validations(
            validate_python_syntax(out.text),
            validate_json_schema(out.text),
        )

        test_issue = ""
        if self.config.execute_generated_tests and node.id == "test_writer":
            test_issue = await self._run_generated_tests(out.text)
            if test_issue:
                validations.passed = False
                validations.issues.append(test_issue)

        score = total_score(instruction=instruction, output=out.text, validation_passed=validations.passed)
        duration = time.perf_counter() - started
        return AgentResult(
            node_id=node.id,
            role=node.role,
            output=out.text,
            tokens_in=out.tokens_in,
            tokens_out=out.tokens_out,
            duration_s=duration,
            validation_passed=validations.passed,
            score=score,
            issues=validations.issues,
        )

    async def _safe_generate(self, prompt: str) -> ProviderResponse:
        try:
            return await self.provider.generate(
                prompt,
                max_tokens=self.config.provider.max_tokens,
                timeout_s=self.config.provider.timeout_seconds,
                temperature=self.config.provider.temperature,
            )
        except ProviderError as primary_error:
            if self.config.provider.type != "openai":
                fallback = OpenAIProvider(model="gpt-4o-mini")
                try:
                    return await fallback.generate(
                        prompt,
                        max_tokens=self.config.provider.max_tokens,
                        timeout_s=self.config.provider.timeout_seconds,
                        temperature=self.config.provider.temperature,
                    )
                except ProviderError:
                    pass
            raise ProviderError(str(primary_error))

    def _build_prompt(self, node: NodeSpec, instruction: str, prior_results: dict[str, AgentResult]) -> str:
        deps = []
        for dep in node.depends_on:
            if dep in prior_results:
                trimmed = prior_results[dep].output[:3000]
                deps.append(f"[{dep}]\n{trimmed}")

        dep_text = "\n\n".join(deps) if deps else "None"
        return (
            f"Role: {node.role}\n"
            f"Node ID: {node.id}\n"
            f"Task instruction:\n{instruction}\n\n"
            f"Role-specific objective:\n{node.prompt_template}\n\n"
            f"Dependency outputs:\n{dep_text}\n\n"
            "Return concise, actionable output in markdown. Include a line `Self-critique score: <0-10>`."
        )

    def _select_nodes(self, graph: AgentGraph, instruction: str) -> list[str]:
        order = graph.topological_order()
        if self.config.enabled_agents:
            enabled = [n for n in order if n in set(self.config.enabled_agents)]
            if enabled:
                return self._dependency_closed(enabled, graph)

        complexity = self._complexity_score(instruction)
        default = order
        if complexity < 0.35:
            keep = {"planner", "requirement_structurer", "implementation_generator", "final_synthesizer"}
        elif complexity < 0.65:
            keep = {
                "planner",
                "requirement_structurer",
                "edge_case_analyzer",
                "implementation_generator",
                "test_writer",
                "final_synthesizer",
            }
        else:
            keep = set(default)

        chosen = [node_id for node_id in default if node_id in keep]
        if not chosen:
            return default
        return self._dependency_closed(chosen, graph)

    def _dependency_closed(self, selected: list[str], graph: AgentGraph) -> list[str]:
        needed = set(selected)
        queue = list(selected)
        while queue:
            node_id = queue.pop()
            node = graph.nodes[node_id]
            for dep in node.depends_on:
                if dep not in needed:
                    needed.add(dep)
                    queue.append(dep)
        return [n for n in graph.topological_order() if n in needed]

    def _complexity_score(self, instruction: str) -> float:
        words = len(instruction.split())
        weighted_terms = [
            "security",
            "performance",
            "benchmark",
            "architecture",
            "concurrency",
            "distributed",
            "validation",
            "integration",
            "cross-platform",
        ]
        hits = sum(1 for t in weighted_terms if t in instruction.lower())
        score = min(1.0, (words / 250.0) + (hits * 0.08))
        return score

    def _would_exceed_budget(self, used_in: int, used_out: int, node: NodeSpec) -> bool:
        projected = used_in + used_out + self.config.provider.max_tokens
        return projected > self.config.budget.max_total_tokens

    def _final_output(self, per_agent: Iterable[AgentResult]) -> str:
        results = list(per_agent)
        if not results:
            return "No output generated."

        for result in results:
            if result.node_id == "final_synthesizer" and result.output.strip():
                return result.output

        ranked = sorted(results, key=lambda r: r.score, reverse=True)[:3]
        blocks = ["# Final Synthesized Output", ""]
        for idx, result in enumerate(ranked, start=1):
            blocks.append(f"## Candidate {idx}: {result.role} (score={result.score})")
            blocks.append(result.output)
            blocks.append("")
        return "\n".join(blocks).strip()

    async def _run_generated_tests(self, text: str) -> str:
        marker = "```python"
        if marker not in text:
            return ""
        blocks = []
        remaining = text
        while marker in remaining:
            _, after = remaining.split(marker, 1)
            code, _, tail = after.partition("```")
            blocks.append(code.strip())
            remaining = tail

        if not blocks:
            return ""

        with tempfile.TemporaryDirectory(prefix="agentling-tests-") as tmp:
            test_file = Path(tmp) / "test_generated.py"
            test_file.write_text("\n\n".join(blocks), encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-m",
                "pytest",
                str(test_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            except TimeoutError:
                proc.kill()
                return "Generated tests timed out"
            if proc.returncode != 0:
                out = stdout.decode("utf-8", errors="replace").strip()
                err = stderr.decode("utf-8", errors="replace").strip()
                return f"Generated tests failed: {(out or err)[:240]}"
        return ""
