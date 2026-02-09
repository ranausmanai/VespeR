export interface Session {
  id: string
  name: string | null
  working_dir: string
  status: string
  created_at: string
  updated_at: string
  config?: Record<string, unknown>
  runs?: Run[]
}

export interface Run {
  id: string
  session_id: string
  prompt: string
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed'
  model: string | null
  parent_run_id: string | null
  branch_point_event_id: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  duration_ms: number
  final_output: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  is_active?: boolean
  is_paused?: boolean
  pid?: number | null
  event_count?: number
  git_snapshots?: GitSnapshot[]
}

export interface AgentlingEvent {
  id: string
  type: string
  session_id: string
  run_id: string
  timestamp: string
  sequence: number
  payload: Record<string, unknown>
  parent_event_id: string | null

  // Stream event fields
  role?: string
  content?: string
  content_type?: string
  tool_name?: string
  tool_id?: string
  tool_input?: Record<string, unknown>
  tool_output?: string
  is_error?: boolean
}

export interface GitSnapshot {
  id: string
  event_id: string
  run_id: string
  commit_hash: string
  branch: string
  dirty_files: string[]
  staged_files: string[]
  diff_stat: string
  created_at: string
}

export interface FileChange {
  path: string
  change_type: 'added' | 'modified' | 'deleted' | 'renamed'
  lines_added: number
  lines_removed: number
  old_path?: string
}

export type EventType =
  | 'session.created'
  | 'session.started'
  | 'run.created'
  | 'run.started'
  | 'run.paused'
  | 'run.resumed'
  | 'run.completed'
  | 'run.failed'
  | 'run.branched'
  | 'stream.init'
  | 'stream.system'
  | 'stream.assistant'
  | 'stream.user'
  | 'stream.tool_use'
  | 'stream.tool_result'
  | 'stream.result'
  | 'stream.error'
  | 'intervention.pause'
  | 'intervention.resume'
  | 'intervention.inject'
  | 'intervention.abort'
  | 'git.snapshot'
  | 'git.diff'
  | 'metrics.tokens'
  | 'metrics.cost'

// Agent types
export interface Agent {
  id: string
  name: string
  description: string | null
  role: string | null
  personality: string | null
  system_prompt: string | null
  model: string
  tools: string[]
  constraints: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  run_history?: AgentRunSummary[]
}

export interface AgentRunSummary {
  id: string
  run_id: string
  pattern: string
  role_in_pattern: string | null
  status: string
  started_at: string | null
  completed_at: string | null
}

export interface AgentPattern {
  id: string
  name: string
  description: string | null
  pattern_type: 'solo' | 'loop' | 'panel' | 'debate'
  config: Record<string, unknown>
  human_involvement: 'autonomous' | 'checkpoints' | 'on_demand'
  max_iterations: number
  created_at: string | null
  updated_at: string | null
}

export interface AgentRun {
  id: string
  agent_id: string
  run_id: string
  pattern: string
  role_in_pattern: string | null
  sequence: number
  iteration: number
  status: string
  input_text: string | null
  output_text: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}
