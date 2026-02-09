import { Session, Run, AgentlingEvent, Agent, AgentPattern, AgentRun } from './types'

const API_BASE = '/api'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Sessions
export async function getSessions(): Promise<{ sessions: Session[] }> {
  return fetchJson('/sessions')
}

export async function getSession(id: string): Promise<Session> {
  return fetchJson(`/sessions/${id}`)
}

export async function createSession(workingDir: string, name?: string): Promise<Session> {
  return fetchJson('/sessions', {
    method: 'POST',
    body: JSON.stringify({ working_dir: workingDir, name }),
  })
}

export async function pickSessionDirectory(): Promise<{
  directory: string | null
  cancelled: boolean
  method: string
}> {
  return fetchJson('/sessions/pick-directory', {
    method: 'POST',
  })
}

// Runs
export async function getRuns(sessionId?: string): Promise<{ runs: Run[] }> {
  const query = sessionId ? `?session_id=${sessionId}` : ''
  return fetchJson(`/runs${query}`)
}

export async function getRun(id: string): Promise<Run> {
  return fetchJson(`/runs/${id}`)
}

export async function startRun(
  sessionId: string,
  prompt: string,
  model: string = 'sonnet'
): Promise<Run> {
  return fetchJson('/runs', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, prompt, model }),
  })
}

export async function getRunEvents(
  runId: string,
  fromSequence: number = 0
): Promise<{ events: AgentlingEvent[] }> {
  return fetchJson(`/runs/${runId}/events?from_sequence=${fromSequence}`)
}

export async function branchRun(
  runId: string,
  fromEventId: string,
  modifiedPrompt?: string
): Promise<Run> {
  return fetchJson(`/runs/${runId}/branch`, {
    method: 'POST',
    body: JSON.stringify({ from_event_id: fromEventId, modified_prompt: modifiedPrompt }),
  })
}

// Control
export async function pauseRun(runId: string): Promise<{ status: string }> {
  return fetchJson(`/control/runs/${runId}/pause`, { method: 'POST' })
}

export async function resumeRun(runId: string): Promise<{ status: string }> {
  return fetchJson(`/control/runs/${runId}/resume`, { method: 'POST' })
}

export async function abortRun(runId: string): Promise<{ status: string }> {
  return fetchJson(`/control/runs/${runId}/abort`, { method: 'POST' })
}

export async function injectMessage(
  runId: string,
  message: string
): Promise<{ status: string }> {
  return fetchJson(`/control/runs/${runId}/inject`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}

export async function getActiveRuns(): Promise<{ active_runs: Run[]; count: number }> {
  return fetchJson('/control/active')
}

export async function getRunStatus(runId: string): Promise<Run> {
  return fetchJson(`/control/runs/${runId}/status`)
}

// Health
export async function checkHealth(): Promise<{ status: string }> {
  return fetchJson('/health')
}

// Agents
export async function getAgents(): Promise<{ agents: Agent[] }> {
  return fetchJson('/agents')
}

export async function getAgent(id: string): Promise<Agent> {
  return fetchJson(`/agents/${id}`)
}

export async function createAgent(agent: {
  name: string
  description?: string
  role?: string
  personality?: string
  system_prompt?: string
  model?: string
  tools?: string[]
  constraints?: Record<string, unknown>
}): Promise<Agent> {
  return fetchJson('/agents', {
    method: 'POST',
    body: JSON.stringify(agent),
  })
}

export async function updateAgent(
  id: string,
  updates: Partial<Agent>
): Promise<Agent> {
  return fetchJson(`/agents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  })
}

export async function deleteAgent(id: string): Promise<{ deleted: boolean }> {
  return fetchJson(`/agents/${id}`, { method: 'DELETE' })
}

export async function getAgentRuns(agentId: string): Promise<{ runs: AgentRun[] }> {
  return fetchJson(`/agents/${agentId}/runs`)
}

// Patterns
export async function getPatterns(): Promise<{ patterns: AgentPattern[] }> {
  return fetchJson('/patterns')
}

export async function getPattern(id: string): Promise<AgentPattern> {
  return fetchJson(`/patterns/${id}`)
}

export async function createPattern(pattern: {
  name: string
  pattern_type: string
  config: Record<string, unknown>
  description?: string
  human_involvement?: string
  max_iterations?: number
}): Promise<AgentPattern> {
  return fetchJson('/patterns', {
    method: 'POST',
    body: JSON.stringify(pattern),
  })
}

export async function updatePattern(
  id: string,
  updates: Partial<AgentPattern>
): Promise<AgentPattern> {
  return fetchJson(`/patterns/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  })
}

export async function deletePattern(id: string): Promise<{ deleted: boolean }> {
  return fetchJson(`/patterns/${id}`, { method: 'DELETE' })
}

// Execution
export async function executeAgent(
  sessionId: string,
  agentId: string,
  inputText: string
): Promise<{ status: string; run_id: string; pattern_id: string }> {
  return fetchJson('/execute/agent', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      agent_id: agentId,
      input_text: inputText,
    }),
  })
}

export async function executePattern(
  patternId: string,
  sessionId: string,
  inputText: string
): Promise<{ status: string; run_id: string; pattern_id: string }> {
  return fetchJson(`/execute/pattern/${patternId}`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      input_text: inputText,
    }),
  })
}

export async function getExecutionState(runId: string): Promise<{
  run_id: string
  pattern_name: string
  pattern_type: string
  current_iteration: number
  results_count: number
  awaiting_human: boolean
}> {
  return fetchJson(`/execute/run/${runId}/state`)
}

export async function provideHumanInput(
  runId: string,
  decision: string
): Promise<{ status: string }> {
  return fetchJson(`/execute/run/${runId}/input`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  })
}
