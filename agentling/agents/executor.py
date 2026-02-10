"""Agent execution engine for running agent patterns."""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from ..events.types import Event, EventType
from ..events.bus import EventBus
from ..persistence.database import Database
from ..persistence.repositories import Agent, AgentRun, AgentPattern, Run
from ..session.pty_controller import PTYController
from ..session.memory import persist_run_memory


class PatternType(str, Enum):
    SOLO = "solo"
    LOOP = "loop"
    PANEL = "panel"
    DEBATE = "debate"


class HumanInvolvement(str, Enum):
    AUTONOMOUS = "autonomous"
    CHECKPOINTS = "checkpoints"
    ON_DEMAND = "on_demand"


@dataclass
class AgentExecutionResult:
    """Result of an agent execution."""
    agent_run_id: str
    agent_id: str
    output: str
    success: bool
    iteration: int = 0
    role: Optional[str] = None


@dataclass
class PatternExecutionState:
    """State for pattern execution."""
    pattern: AgentPattern
    session_id: str
    run_id: str
    input_text: str
    current_iteration: int = 0
    results: list[AgentExecutionResult] = field(default_factory=list)
    should_stop: bool = False
    awaiting_human: bool = False
    human_decision: Optional[str] = None


class AgentExecutor:
    """Executes agent patterns with full traceability."""
    _MAX_AGENT_RUNTIME_SECONDS = 240
    _MAX_REPEATED_BASH_COMMAND = 8

    def __init__(self, database: Database, event_bus: EventBus):
        self.db = database
        self.event_bus = event_bus
        self._active_executions: dict[str, PatternExecutionState] = {}
        self._human_response_events: dict[str, asyncio.Event] = {}

    @staticmethod
    def _extract_result_usage(event: Event) -> tuple[int, int]:
        """Extract token usage only from finalized result events."""
        if event.type != EventType.STREAM_RESULT:
            return 0, 0
        payload = event.payload or {}
        if payload.get("type") != "result":
            return 0, 0

        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            return 0, 0

        try:
            tokens_in = int(usage.get("input_tokens", 0) or 0)
            tokens_out = int(usage.get("output_tokens", 0) or 0)
        except (TypeError, ValueError):
            return 0, 0

        return tokens_in, tokens_out

    async def execute_pattern(
        self,
        pattern: AgentPattern,
        session_id: str,
        input_text: str,
        working_dir: str,
        on_checkpoint: Optional[Callable[[str, dict], Awaitable[str]]] = None
    ) -> AsyncIterator[Event]:
        """Execute an agent pattern and stream events."""
        # Get session
        session = await self.db.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        start_time = datetime.utcnow()

        # Create a run for this pattern execution
        run = await self.db.runs.create(
            session_id=session_id,
            prompt=f"[Agent Pattern: {pattern.name}] {input_text[:100]}",
            model="sonnet"
        )
        await self.db.runs.update_status(run.id, "running")

        # Initialize state
        state = PatternExecutionState(
            pattern=pattern,
            session_id=session_id,
            run_id=run.id,
            input_text=input_text
        )
        self._active_executions[run.id] = state

        # Emit pattern start event
        start_event = Event(
            type=EventType.RUN_STARTED,
            session_id=session_id,
            run_id=run.id,
            payload={
                "pattern_id": pattern.id,
                "pattern_name": pattern.name,
                "pattern_type": pattern.pattern_type,
                "agents": pattern.config.get("agents", []),
                "human_involvement": pattern.human_involvement,
            }
        )
        await self.event_bus.publish(start_event)
        yield start_event

        try:
            # Execute based on pattern type
            pattern_type = PatternType(pattern.pattern_type)

            if pattern_type == PatternType.SOLO:
                async for event in self._execute_solo(state, working_dir, on_checkpoint):
                    yield event
            elif pattern_type == PatternType.LOOP:
                async for event in self._execute_loop(state, working_dir, on_checkpoint):
                    yield event
            elif pattern_type == PatternType.PANEL:
                async for event in self._execute_panel(state, working_dir, on_checkpoint):
                    yield event
            elif pattern_type == PatternType.DEBATE:
                async for event in self._execute_debate(state, working_dir, on_checkpoint):
                    yield event

            # Pattern completed
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self.db.runs.update_metrics(run.id, duration_ms=duration_ms)
            await self.db.runs.update_status(run.id, "completed")
            await persist_run_memory(self.db, run.id)

            complete_event = Event(
                type=EventType.RUN_COMPLETED,
                session_id=session_id,
                run_id=run.id,
                payload={
                    "pattern_type": pattern.pattern_type,
                    "total_iterations": state.current_iteration,
                    "total_agents_run": len(state.results),
                }
            )
            await self.event_bus.publish(complete_event)
            yield complete_event

        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self.db.runs.update_metrics(run.id, duration_ms=duration_ms)
            await self.db.runs.update_status(run.id, "failed", str(e))
            await persist_run_memory(self.db, run.id)
            error_event = Event(
                type=EventType.RUN_FAILED,
                session_id=session_id,
                run_id=run.id,
                payload={"error": str(e)}
            )
            await self.event_bus.publish(error_event)
            yield error_event
            raise
        finally:
            self._active_executions.pop(run.id, None)

    async def _execute_solo(
        self,
        state: PatternExecutionState,
        working_dir: str,
        on_checkpoint: Optional[Callable[[str, dict], Awaitable[str]]] = None
    ) -> AsyncIterator[Event]:
        """Execute a single agent."""
        config = state.pattern.config
        agent_id = config.get("agent_id") or (config.get("agents", [None])[0])

        if not agent_id:
            raise ValueError("Solo pattern requires an agent_id in config")

        agent = await self.db.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        async for event in self._run_agent(
            agent=agent,
            state=state,
            working_dir=working_dir,
            input_text=state.input_text,
            role_in_pattern="solo",
            sequence=0,
            iteration=0
        ):
            yield event

    async def _execute_loop(
        self,
        state: PatternExecutionState,
        working_dir: str,
        on_checkpoint: Optional[Callable[[str, dict], Awaitable[str]]] = None
    ) -> AsyncIterator[Event]:
        """Execute generator + critic loop."""
        config = state.pattern.config
        generator_id = config.get("generator_id")
        critic_id = config.get("critic_id")
        max_iterations = state.pattern.max_iterations

        if not generator_id or not critic_id:
            raise ValueError("Loop pattern requires generator_id and critic_id in config")

        generator = await self.db.agents.get(generator_id)
        critic = await self.db.agents.get(critic_id)

        if not generator:
            raise ValueError(f"Generator agent {generator_id} not found")
        if not critic:
            raise ValueError(f"Critic agent {critic_id} not found")

        current_input = state.input_text
        current_output = ""

        for iteration in range(max_iterations):
            state.current_iteration = iteration

            # Check for human involvement at checkpoints
            if state.pattern.human_involvement == HumanInvolvement.CHECKPOINTS.value:
                if iteration > 0 and on_checkpoint:
                    checkpoint_event = Event(
                        type=EventType.INTERVENTION_PAUSE,
                        session_id=state.session_id,
                        run_id=state.run_id,
                        payload={
                            "checkpoint": "iteration_start",
                            "iteration": iteration,
                            "previous_output": current_output[:500],
                            "options": ["continue", "modify", "stop"]
                        }
                    )
                    await self.event_bus.publish(checkpoint_event)
                    yield checkpoint_event

                    decision = await on_checkpoint("iteration_start", {
                        "iteration": iteration,
                        "previous_output": current_output
                    })

                    if decision == "stop":
                        state.should_stop = True
                        break
                    elif decision.startswith("modify:"):
                        current_input = decision[7:]

            # Run generator
            generator_prompt = self._build_generator_prompt(
                agent=generator,
                original_input=state.input_text,
                current_input=current_input,
                previous_output=current_output if iteration > 0 else None,
                iteration=iteration
            )

            async for event in self._run_agent(
                agent=generator,
                state=state,
                working_dir=working_dir,
                input_text=generator_prompt,
                role_in_pattern="generator",
                sequence=iteration * 2,
                iteration=iteration
            ):
                yield event
                if event.type == EventType.STREAM_ASSISTANT and hasattr(event, 'content'):
                    current_output = event.content or current_output

            # Get the latest result
            if state.results:
                current_output = state.results[-1].output

            # Run critic
            critic_prompt = self._build_critic_prompt(
                agent=critic,
                original_input=state.input_text,
                generated_output=current_output,
                iteration=iteration
            )

            async for event in self._run_agent(
                agent=critic,
                state=state,
                working_dir=working_dir,
                input_text=critic_prompt,
                role_in_pattern="critic",
                sequence=iteration * 2 + 1,
                iteration=iteration
            ):
                yield event

            # Check critic's verdict
            if state.results:
                critic_output = state.results[-1].output.lower()
                if "approved" in critic_output or "looks good" in critic_output or "acceptable" in critic_output:
                    break

                # Use critic feedback for next iteration
                current_input = f"Previous attempt:\n{current_output}\n\nCritic feedback:\n{state.results[-1].output}"

    async def _execute_panel(
        self,
        state: PatternExecutionState,
        working_dir: str,
        on_checkpoint: Optional[Callable[[str, dict], Awaitable[str]]] = None
    ) -> AsyncIterator[Event]:
        """Execute expert panel - multiple agents contribute perspectives."""
        config = state.pattern.config
        agent_ids = config.get("agents", [])
        synthesizer_id = config.get("synthesizer_id")

        if not agent_ids:
            raise ValueError("Panel pattern requires agents list in config")

        # Run all panel agents (can be parallelized in future)
        panel_outputs = []
        for seq, agent_id in enumerate(agent_ids):
            agent = await self.db.agents.get(agent_id)
            if not agent:
                continue

            panel_prompt = self._build_panel_prompt(
                agent=agent,
                input_text=state.input_text
            )

            async for event in self._run_agent(
                agent=agent,
                state=state,
                working_dir=working_dir,
                input_text=panel_prompt,
                role_in_pattern=f"panelist_{agent.role or seq}",
                sequence=seq,
                iteration=0
            ):
                yield event

            if state.results:
                panel_outputs.append({
                    "agent": agent.name,
                    "role": agent.role,
                    "output": state.results[-1].output
                })

        # Synthesize if synthesizer is specified
        if synthesizer_id:
            synthesizer = await self.db.agents.get(synthesizer_id)
            if synthesizer:
                synthesis_prompt = self._build_synthesis_prompt(
                    agent=synthesizer,
                    original_input=state.input_text,
                    panel_outputs=panel_outputs
                )

                async for event in self._run_agent(
                    agent=synthesizer,
                    state=state,
                    working_dir=working_dir,
                    input_text=synthesis_prompt,
                    role_in_pattern="synthesizer",
                    sequence=len(agent_ids),
                    iteration=0
                ):
                    yield event

    async def _execute_debate(
        self,
        state: PatternExecutionState,
        working_dir: str,
        on_checkpoint: Optional[Callable[[str, dict], Awaitable[str]]] = None
    ) -> AsyncIterator[Event]:
        """Execute debate pattern - agents argue back and forth."""
        config = state.pattern.config
        debater_ids = config.get("debaters", [])
        judge_id = config.get("judge_id")
        max_rounds = config.get("max_rounds", 3)

        if len(debater_ids) < 2:
            raise ValueError("Debate pattern requires at least 2 debaters")

        debaters = []
        for did in debater_ids:
            agent = await self.db.agents.get(did)
            if agent:
                debaters.append(agent)

        if len(debaters) < 2:
            raise ValueError("Could not find enough valid debaters")

        debate_history = []

        for round_num in range(max_rounds):
            state.current_iteration = round_num

            for seq, debater in enumerate(debaters):
                debate_prompt = self._build_debate_prompt(
                    agent=debater,
                    original_topic=state.input_text,
                    debate_history=debate_history,
                    round_num=round_num,
                    position=seq
                )

                async for event in self._run_agent(
                    agent=debater,
                    state=state,
                    working_dir=working_dir,
                    input_text=debate_prompt,
                    role_in_pattern=f"debater_{seq}",
                    sequence=round_num * len(debaters) + seq,
                    iteration=round_num
                ):
                    yield event

                if state.results:
                    debate_history.append({
                        "debater": debater.name,
                        "round": round_num,
                        "argument": state.results[-1].output
                    })

        # Judge renders verdict
        if judge_id:
            judge = await self.db.agents.get(judge_id)
            if judge:
                judge_prompt = self._build_judge_prompt(
                    agent=judge,
                    original_topic=state.input_text,
                    debate_history=debate_history
                )

                async for event in self._run_agent(
                    agent=judge,
                    state=state,
                    working_dir=working_dir,
                    input_text=judge_prompt,
                    role_in_pattern="judge",
                    sequence=max_rounds * len(debaters),
                    iteration=max_rounds
                ):
                    yield event

    async def _run_agent(
        self,
        agent: Agent,
        state: PatternExecutionState,
        working_dir: str,
        input_text: str,
        role_in_pattern: str,
        sequence: int,
        iteration: int
    ) -> AsyncIterator[Event]:
        """Run a single agent and track execution."""
        # Create agent run record
        agent_run = await self.db.agent_runs.create(
            agent_id=agent.id,
            run_id=state.run_id,
            pattern=state.pattern.pattern_type,
            role_in_pattern=role_in_pattern,
            sequence=sequence,
            iteration=iteration,
            input_text=input_text
        )

        # Emit agent start event
        start_event = Event(
            type=EventType.STREAM_SYSTEM,
            session_id=state.session_id,
            run_id=state.run_id,
            payload={
                "agent_run_id": agent_run.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": role_in_pattern,
                "iteration": iteration,
            }
        )
        await self.event_bus.publish(start_event)
        yield start_event

        await self.db.agent_runs.update_status(agent_run.id, "running")

        # Build the full prompt with agent's system prompt
        full_prompt = self._build_full_prompt(agent, input_text)

        # Run Claude with agent's configuration
        controller = PTYController(
            session_id=state.session_id,
            run_id=state.run_id,
            working_dir=working_dir,
            model=agent.model or "sonnet"
        )

        output_text = ""
        saw_agent_failure = False
        agent_failure_reason: Optional[str] = None
        last_bash_command: Optional[str] = None
        repeated_bash_count = 0

        try:
            async with asyncio.timeout(self._MAX_AGENT_RUNTIME_SECONDS):
                async for event in controller.start(full_prompt):
                    # Add agent context to event
                    event.payload = event.payload or {}
                    event.payload["agent_run_id"] = agent_run.id
                    event.payload["agent_name"] = agent.name

                    await self.event_bus.publish(event)
                    yield event

                    if event.type == EventType.STREAM_TOOL_USE:
                        tool_name = getattr(event, "tool_name", None) or str(event.payload.get("tool_name") or "")
                        tool_input = (
                            getattr(event, "tool_input", None)
                            or event.payload.get("tool_input")
                            or event.payload.get("content_block", {}).get("input", {})
                        )
                        command = ""
                        if isinstance(tool_input, dict):
                            command = str(tool_input.get("command") or "").strip()

                        if tool_name == "Bash" and command:
                            if command == last_bash_command:
                                repeated_bash_count += 1
                            else:
                                last_bash_command = command
                                repeated_bash_count = 1

                            if repeated_bash_count >= self._MAX_REPEATED_BASH_COMMAND:
                                await controller.terminate()
                                raise RuntimeError(
                                    f"Runaway loop detected: repeated Bash command `{command}` "
                                    f"{repeated_bash_count} times. Aborted."
                                )
                        elif tool_name == "Bash":
                            last_bash_command = None
                            repeated_bash_count = 0

                    # Track token usage on finalized result events.
                    tokens_in, tokens_out = self._extract_result_usage(event)
                    if tokens_in or tokens_out:
                        await self.db.runs.update_metrics(
                            state.run_id,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out
                        )

                    # Capture output
                    if event.type == EventType.STREAM_ASSISTANT:
                        if hasattr(event, 'content') and event.content:
                            output_text += event.content
                    elif event.type == EventType.STREAM_RESULT:
                        # Prefer finalized result text when available.
                        result_text = str(event.payload.get("result", "") or "")
                        if result_text.strip():
                            output_text = result_text
                    elif event.type == EventType.RUN_FAILED:
                        saw_agent_failure = True
                        stderr_text = str(event.payload.get("stderr", "") or "")
                        return_code = event.payload.get("return_code")
                        if stderr_text:
                            agent_failure_reason = stderr_text
                        else:
                            agent_failure_reason = f"Agent process failed (return_code={return_code})"

            if saw_agent_failure:
                raise RuntimeError(agent_failure_reason or "Agent process failed")

            # Update agent run with output
            await self.db.agent_runs.update_status(agent_run.id, "completed", output_text)

            # Record result
            state.results.append(AgentExecutionResult(
                agent_run_id=agent_run.id,
                agent_id=agent.id,
                output=output_text,
                success=True,
                iteration=iteration,
                role=role_in_pattern
            ))

        except Exception as e:
            if isinstance(e, TimeoutError):
                await controller.terminate()
                e = RuntimeError(
                    f"Agent exceeded {self._MAX_AGENT_RUNTIME_SECONDS}s runtime limit and was aborted."
                )
            await self.db.agent_runs.update_status(agent_run.id, "failed", str(e))
            state.results.append(AgentExecutionResult(
                agent_run_id=agent_run.id,
                agent_id=agent.id,
                output=str(e),
                success=False,
                iteration=iteration,
                role=role_in_pattern
            ))
            raise

    def _build_full_prompt(self, agent: Agent, input_text: str) -> str:
        """Build full prompt including agent's system prompt."""
        parts = []

        if agent.system_prompt:
            parts.append(f"<system>\n{agent.system_prompt}\n</system>\n")

        if agent.personality:
            parts.append(f"<personality>\n{agent.personality}\n</personality>\n")

        if agent.constraints:
            constraints_text = "\n".join(f"- {k}: {v}" for k, v in agent.constraints.items())
            parts.append(f"<constraints>\n{constraints_text}\n</constraints>\n")

        parts.append(input_text)

        return "\n".join(parts)

    def _build_generator_prompt(
        self,
        agent: Agent,
        original_input: str,
        current_input: str,
        previous_output: Optional[str],
        iteration: int
    ) -> str:
        """Build prompt for generator in loop pattern."""
        if iteration == 0:
            return current_input

        return f"""Original request: {original_input}

Your previous output:
{previous_output}

Feedback to incorporate:
{current_input}

Please improve your response based on the feedback."""

    def _build_critic_prompt(
        self,
        agent: Agent,
        original_input: str,
        generated_output: str,
        iteration: int
    ) -> str:
        """Build prompt for critic in loop pattern."""
        return f"""Original request: {original_input}

Generated output to review:
{generated_output}

Iteration: {iteration + 1}

Please review this output. Provide specific, actionable feedback.
If the output is satisfactory, respond with "APPROVED" at the start.
Otherwise, explain what needs improvement."""

    def _build_panel_prompt(self, agent: Agent, input_text: str) -> str:
        """Build prompt for panel member."""
        role_context = f"As a {agent.role}, " if agent.role else ""
        return f"""{role_context}please provide your expert perspective on the following:

{input_text}

Focus on your area of expertise and provide specific, actionable insights."""

    def _build_synthesis_prompt(
        self,
        agent: Agent,
        original_input: str,
        panel_outputs: list[dict]
    ) -> str:
        """Build prompt for panel synthesizer."""
        perspectives = "\n\n".join([
            f"**{p['agent']}** ({p.get('role', 'Expert')}):\n{p['output']}"
            for p in panel_outputs
        ])

        return f"""Original question: {original_input}

Expert panel perspectives:
{perspectives}

Please synthesize these perspectives into a coherent, comprehensive response.
Identify areas of agreement, highlight key insights, and resolve any conflicts."""

    def _build_debate_prompt(
        self,
        agent: Agent,
        original_topic: str,
        debate_history: list[dict],
        round_num: int,
        position: int
    ) -> str:
        """Build prompt for debater."""
        if not debate_history:
            return f"""Topic for debate: {original_topic}

You are arguing position #{position + 1}. Present your opening argument."""

        history_text = "\n\n".join([
            f"**{h['debater']}** (Round {h['round'] + 1}):\n{h['argument']}"
            for h in debate_history
        ])

        return f"""Topic: {original_topic}

Debate history:
{history_text}

This is round {round_num + 1}. Respond to the previous arguments and strengthen your position."""

    def _build_judge_prompt(
        self,
        agent: Agent,
        original_topic: str,
        debate_history: list[dict]
    ) -> str:
        """Build prompt for debate judge."""
        history_text = "\n\n".join([
            f"**{h['debater']}** (Round {h['round'] + 1}):\n{h['argument']}"
            for h in debate_history
        ])

        return f"""Topic: {original_topic}

Full debate:
{history_text}

As the judge, render your verdict. Evaluate the strength of arguments, evidence presented,
and logical reasoning. Declare a winner or draw, and explain your decision."""

    async def provide_human_input(self, run_id: str, decision: str) -> bool:
        """Provide human input for a checkpoint."""
        state = self._active_executions.get(run_id)
        if not state or not state.awaiting_human:
            return False

        state.human_decision = decision
        state.awaiting_human = False

        event = self._human_response_events.get(run_id)
        if event:
            event.set()

        return True

    def get_execution_state(self, run_id: str) -> Optional[dict]:
        """Get current execution state."""
        state = self._active_executions.get(run_id)
        if not state:
            return None

        return {
            "run_id": run_id,
            "pattern_name": state.pattern.name,
            "pattern_type": state.pattern.pattern_type,
            "current_iteration": state.current_iteration,
            "results_count": len(state.results),
            "awaiting_human": state.awaiting_human,
            "should_stop": state.should_stop
        }

    def list_active_executions(self) -> list[dict]:
        """List all currently active pattern executions."""
        items: list[dict] = []
        for run_id, state in self._active_executions.items():
            items.append({
                "run_id": run_id,
                "pattern_name": state.pattern.name,
                "pattern_type": state.pattern.pattern_type,
                "current_iteration": state.current_iteration,
                "results_count": len(state.results),
                "awaiting_human": state.awaiting_human,
                "should_stop": state.should_stop,
            })
        return items
