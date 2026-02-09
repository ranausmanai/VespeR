import { Component, ErrorInfo, ReactNode, useEffect, useMemo, useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import {
  Bot,
  Play,
  Pause,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  ArrowRight,
  User,
  MessageSquare,
  Send,
  Zap,
  DollarSign,
  FileCode,
  Terminal
} from 'lucide-react'
import { getRun, getExecutionState, provideHumanInput } from '../api/client'
import { Run, AgentlingEvent } from '../api/types'
import { wsClient } from '../api/websocket'
import TaskDAG from '../components/dag/TaskDAG'
import EventTimeline from '../components/timeline/EventTimeline'

interface ExecutionState {
  run_id: string
  pattern_name: string
  pattern_type: string
  current_iteration: number
  results_count: number
  awaiting_human: boolean
}

function safeString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

function getPayloadValue(event: AgentlingEvent, key: string): unknown {
  const payload = event.payload
  if (!payload || typeof payload !== 'object') return undefined
  return (payload as Record<string, unknown>)[key]
}

function getAgentRunId(event: AgentlingEvent): string {
  return safeString(getPayloadValue(event, 'agent_run_id'), 'unknown')
}

function formatEventTime(timestamp: unknown): string {
  const raw = safeString(timestamp)
  if (!raw) return ''
  try {
    const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T')
    const date = new Date(normalized)
    if (Number.isNaN(date.getTime())) return raw
    return date.toLocaleTimeString()
  } catch {
    return raw
  }
}

function appendUniqueEvent(prev: AgentlingEvent[], next: AgentlingEvent): AgentlingEvent[] {
  if (prev.some(e => e.id === next.id)) return prev
  return [...prev, next]
}

class EventStreamErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; message: string }
> {
  state = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: safeString(error?.message, 'Unknown render error') }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Event stream render crashed:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 rounded-lg border border-red-800 bg-red-900/20 text-red-300">
          Failed to render one or more events: {this.state.message}
        </div>
      )
    }
    return this.props.children
  }
}

export default function AgentExecution() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const [executionState, setExecutionState] = useState<ExecutionState | null>(null)
  const [events, setEvents] = useState<AgentlingEvent[]>([])
  const [agentRunStatuses, setAgentRunStatuses] = useState<Record<string, string>>({})
  const [humanInput, setHumanInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<'timeline' | 'dag' | 'split'>('split')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!runId) return

    loadRun()
    loadEvents()
    loadAgentRuns()
    pollState()

    // Subscribe to WebSocket events
    const unsub = wsClient.onEvent((event) => {
      if (event.run_id === runId) {
        setEvents(prev => appendUniqueEvent(prev, event))

        // Auto-scroll
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
      }
    })

    const interval = setInterval(pollState, 2000)

    return () => {
      unsub()
      clearInterval(interval)
    }
  }, [runId])

  async function loadRun() {
    if (!runId) return
    try {
      const data = await getRun(runId)
      setRun(data)
    } catch (e) {
      console.error('Failed to load run:', e)
    } finally {
      setLoading(false)
    }
  }

  async function loadEvents() {
    if (!runId) return
    try {
      const response = await fetch(`/api/runs/${runId}/events?limit=2000`)
      if (!response.ok) return
      const data = await response.json()
      const unique: AgentlingEvent[] = []
      const seen = new Set<string>()
      for (const event of (data.events || []) as AgentlingEvent[]) {
        if (!event.id || seen.has(event.id)) continue
        seen.add(event.id)
        unique.push(event)
      }
      setEvents(unique)
    } catch (e) {
      console.error('Failed to load execution events:', e)
    }
  }

  async function loadAgentRuns() {
    if (!runId) return
    try {
      const response = await fetch(`/api/execute/run/${runId}/agents`)
      if (!response.ok) return
      const data = await response.json()
      const statuses: Record<string, string> = {}
      for (const ar of data.agent_runs || []) {
        if (ar?.id) statuses[String(ar.id)] = String(ar.status || '')
      }
      setAgentRunStatuses(statuses)
    } catch (e) {
      console.error('Failed to load agent run statuses:', e)
    }
  }

  async function pollState() {
    if (!runId) return
    let latestRun: Run | null = null
    try {
      latestRun = await getRun(runId)
      setRun(latestRun)
    } catch (e) {
      console.error('Failed to refresh run:', e)
    }

    // Refresh agent-level statuses periodically to avoid stale "running" chips.
    await loadAgentRuns()

    // Only request active execution state while run is still running.
    if (!latestRun || latestRun.status !== 'running') {
      setExecutionState(null)
      return
    }

    try {
      const state = await getExecutionState(runId)
      setExecutionState(state)
    } catch {
      // Execution state not present when not actively orchestrating.
      setExecutionState(null)
    }
  }

  async function handleHumanInput(decision: string) {
    if (!runId) return
    try {
      await provideHumanInput(runId, decision)
      setHumanInput('')
    } catch (e) {
      console.error('Failed to send input:', e)
    }
  }

  // Collapse noisy stream chunks and duplicate lifecycle events for readability.
  const displayEvents = useMemo(() => {
    const collapsed: AgentlingEvent[] = []
    const seenResultByAgent = new Set<string>()
    const seenRunCompleted = new Set<string>()

    for (const event of events) {
      const agentRunId = getAgentRunId(event)

      if (event.type === 'stream.assistant') {
        const rawChunk = safeString(event.content)
        if (!rawChunk.trim() || rawChunk.trim() === '...') continue

        const prev = collapsed[collapsed.length - 1]
        if (prev && prev.type === 'stream.assistant' && getAgentRunId(prev) === agentRunId) {
          prev.content = `${safeString(prev.content)}${rawChunk}`
          prev.timestamp = event.timestamp
          continue
        }

        collapsed.push({ ...event, content: rawChunk })
        continue
      }

      if (event.type === 'stream.user') {
        if (!safeString(event.content).trim()) continue
        continue
      }

      if (event.type === 'stream.result') {
        if (seenResultByAgent.has(agentRunId)) continue
        seenResultByAgent.add(agentRunId)
      }

      if (event.type === 'run.completed') {
        const key = `${event.run_id}:${event.type}`
        if (seenRunCompleted.has(key)) continue
        seenRunCompleted.add(key)
      }

      const prev = collapsed[collapsed.length - 1]
      if (
        prev &&
        prev.type === event.type &&
        prev.run_id === event.run_id &&
        getAgentRunId(prev) === getAgentRunId(event) &&
        safeString(prev.content) === safeString(event.content)
      ) {
        continue
      }

      collapsed.push(event)
    }

    return collapsed
  }, [events])
  const activityItems = useMemo(() => buildActivityItems(events), [events])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        Run not found
      </div>
    )
  }

  // Group events by agent_run_id
  const eventsByAgent = events.reduce((acc, event) => {
    const agentRunId = getAgentRunId(event)
    if (!acc[agentRunId]) acc[agentRunId] = []
    acc[agentRunId].push(event)
    return acc
  }, {} as Record<string, AgentlingEvent[]>)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <Bot size={24} className="text-purple-400" />
              {executionState?.pattern_name || 'Agent Execution'}
            </h1>
            <p className="text-sm text-gray-400 mt-1">
              {executionState?.pattern_type || run.status}
              {executionState && ` • Iteration ${executionState.current_iteration + 1}`}
            </p>
            <div className="flex items-center gap-4 text-xs text-gray-500 mt-1">
              <span className="flex items-center gap-1">
                <Zap size={12} />
                {(run.tokens_in + run.tokens_out).toLocaleString()} tokens
              </span>
              <span className="flex items-center gap-1">
                <DollarSign size={12} />
                ${run.cost_usd.toFixed(4)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex rounded-lg overflow-hidden border border-gray-700">
              {(['dag', 'timeline', 'split'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-3 py-1.5 text-sm ${
                    viewMode === mode
                      ? 'bg-claude-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  }`}
                >
                  {mode.charAt(0).toUpperCase() + mode.slice(1)}
                </button>
              ))}
            </div>
            <StatusBadge status={run.status} />
            {executionState?.awaiting_human && (
              <span className="px-3 py-1 bg-yellow-900/50 text-yellow-400 rounded-full text-sm animate-pulse">
                Awaiting Input
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Agent Flow Sidebar */}
        <div className="w-64 border-r border-gray-800 bg-gray-900/50 p-4 overflow-auto">
          <h2 className="text-sm font-medium text-gray-400 mb-4">Agent Flow</h2>

          <div className="space-y-2">
            {Object.entries(eventsByAgent).map(([agentRunId, agentEvents]) => {
              const startEvent = agentEvents.find(e => e.type === 'stream.system')
              const agentName = startEvent?.payload?.agent_name as string || 'Agent'
              const role = startEvent?.payload?.role as string || ''
              const iteration = startEvent?.payload?.iteration as number || 0

              const hasCompleted = agentEvents.some(e =>
                e.type === 'stream.result' || e.type === 'run.completed'
              )
              const hasFailed = agentEvents.some(e =>
                e.type === 'stream.error' || e.type === 'run.failed'
              )
              const explicitStatus = agentRunStatuses[agentRunId]
              const resolvedStatus: 'pending' | 'running' | 'completed' | 'failed' =
                explicitStatus === 'completed'
                  ? 'completed'
                  : explicitStatus === 'failed'
                    ? 'failed'
                    : explicitStatus === 'running'
                      ? 'running'
                      : explicitStatus === 'pending'
                        ? 'pending'
                        : hasFailed
                          ? 'failed'
                          : hasCompleted || run.status === 'completed'
                            ? 'completed'
                            : 'running'

              return (
                <AgentFlowItem
                  key={agentRunId}
                  name={agentName}
                  role={role}
                  iteration={iteration}
                  status={resolvedStatus}
                  eventCount={agentEvents.length}
                />
              )
            })}
          </div>
        </div>

        {/* Events Stream */}
        <div className="flex-1 flex flex-col min-w-0">
          {viewMode === 'dag' && (
            <div className="flex-1">
              <TaskDAG events={events} />
            </div>
          )}

          {viewMode === 'split' && (
            <div className="flex-1 flex min-h-0">
              <div className="w-[45%] border-r border-gray-800 min-w-0">
                <TaskDAG events={events} />
              </div>
              <div className="w-[37%] overflow-auto border-r border-gray-800 min-w-0">
                <EventTimeline events={events} mode="assistant_focus" />
              </div>
              <div className="w-[18%] overflow-auto bg-gray-900/30 min-w-0">
                <ActivityPane items={activityItems} />
              </div>
            </div>
          )}

          {viewMode === 'timeline' && (
            <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-2">
              <EventStreamErrorBoundary>
                {displayEvents.map((event, i) => (
                  <EventCard key={i} event={event} />
                ))}
              </EventStreamErrorBoundary>

              {displayEvents.length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  <RefreshCw size={32} className="mx-auto mb-2 animate-spin" />
                  <p>Waiting for events...</p>
                </div>
              )}
            </div>
          )}

          {/* Human Input */}
          {executionState?.awaiting_human && viewMode === 'timeline' && (
            <div className="p-4 border-t border-gray-800 bg-gray-900">
              <div className="flex items-center gap-2 mb-2">
                <User size={16} className="text-yellow-400" />
                <span className="text-sm text-yellow-400">Human checkpoint reached</span>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => handleHumanInput('continue')}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
                >
                  Continue
                </button>
                <button
                  onClick={() => handleHumanInput('stop')}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                >
                  Stop
                </button>
                <div className="flex-1 flex gap-2">
                  <input
                    type="text"
                    value={humanInput}
                    onChange={e => setHumanInput(e.target.value)}
                    placeholder="Or provide custom input..."
                    className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-yellow-500"
                  />
                  <button
                    onClick={() => handleHumanInput(`modify:${humanInput}`)}
                    disabled={!humanInput.trim()}
                    className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors disabled:opacity-50"
                  >
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface ActivityItem {
  id: string
  type: 'file' | 'command'
  title: string
  detail: string
  timestamp: string
}

function buildActivityItems(events: AgentlingEvent[]): ActivityItem[] {
  const items: ActivityItem[] = []
  const seen = new Set<string>()

  for (const event of events) {
    if (event.type !== 'stream.tool_use') continue
    const toolName = String(event.tool_name || '')
    const input = (event.tool_input || event.payload?.tool_input || event.payload?.input || {}) as Record<string, unknown>
    const timestamp = event.timestamp

    if (toolName === 'Read' || toolName === 'Write' || toolName === 'Edit') {
      const filePath = String(input.file_path || input.path || '')
      if (!filePath) continue
      const key = `file:${toolName}:${filePath}:${timestamp}`
      if (seen.has(key)) continue
      seen.add(key)
      items.push({
        id: `${event.id}-file`,
        type: 'file',
        title: `${toolName} ${filePath.split('/').pop() || filePath}`,
        detail: filePath,
        timestamp,
      })
      continue
    }

    if (toolName === 'Bash') {
      const command = String(input.command || '').trim()
      if (!command) continue
      const key = `cmd:${command}:${timestamp}`
      if (seen.has(key)) continue
      seen.add(key)
      items.push({
        id: `${event.id}-cmd`,
        type: 'command',
        title: command,
        detail: 'Bash',
        timestamp,
      })
    }
  }

  return items.slice(-200).reverse()
}

function ActivityPane({ items }: { items: ActivityItem[] }) {
  return (
    <div className="h-full p-3">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Activity</h3>
      {items.length === 0 ? (
        <div className="text-xs text-gray-500">No file or command activity yet.</div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="rounded-lg border border-gray-800 bg-gray-900/60 p-2">
              <div className="flex items-center gap-2 mb-1">
                {item.type === 'file' ? (
                  <FileCode size={13} className="text-blue-400" />
                ) : (
                  <Terminal size={13} className="text-yellow-400" />
                )}
                <span className="text-xs text-gray-200 truncate">{item.title}</span>
              </div>
              <div className="text-[11px] text-gray-500 truncate">{item.detail}</div>
              <div className="text-[10px] text-gray-600 mt-1">
                {formatEventTime(item.timestamp)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AgentFlowItem({
  name,
  role,
  iteration,
  status,
  eventCount
}: {
  name: string
  role: string
  iteration: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  eventCount: number
}) {
  const statusIcons = {
    pending: <Clock size={14} className="text-gray-400" />,
    running: <RefreshCw size={14} className="text-blue-400 animate-spin" />,
    completed: <CheckCircle size={14} className="text-green-400" />,
    failed: <XCircle size={14} className="text-red-400" />,
  }

  return (
    <div className={`
      p-3 rounded-lg border transition-all
      ${status === 'running'
        ? 'bg-blue-900/20 border-blue-800'
        : status === 'completed'
          ? 'bg-green-900/20 border-green-800/50'
          : status === 'failed'
            ? 'bg-red-900/20 border-red-800/50'
            : 'bg-gray-800/50 border-gray-700'
      }
    `}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-medium text-white text-sm">{name}</span>
        {statusIcons[status]}
      </div>
      <div className="text-xs text-gray-400">
        {role && <span className="capitalize">{role}</span>}
        {iteration > 0 && <span> • Iteration {iteration + 1}</span>}
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {eventCount} events
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const statusConfig: Record<string, { icon: React.ReactNode; class: string }> = {
    pending: { icon: <Clock size={14} />, class: 'bg-gray-700 text-gray-300' },
    running: { icon: <Play size={14} />, class: 'bg-blue-900/50 text-blue-400' },
    paused: { icon: <Pause size={14} />, class: 'bg-yellow-900/50 text-yellow-400' },
    completed: { icon: <CheckCircle size={14} />, class: 'bg-green-900/50 text-green-400' },
    failed: { icon: <XCircle size={14} />, class: 'bg-red-900/50 text-red-400' },
  }

  const config = statusConfig[status] || statusConfig.pending

  return (
    <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-sm ${config.class}`}>
      {config.icon}
      <span className="capitalize">{status}</span>
    </span>
  )
}

function EventCard({ event }: { event: AgentlingEvent }) {
  const agentName = safeString(getPayloadValue(event, 'agent_name'))

  // Skip non-essential events
  if (event.type === 'stream.init') {
    return null
  }

  const getEventIcon = () => {
    switch (event.type) {
      case 'stream.system':
        return <Play size={14} className="text-blue-400" />
      case 'stream.assistant':
        return <MessageSquare size={14} className="text-purple-400" />
      case 'stream.user':
        return <User size={14} className="text-cyan-400" />
      case 'stream.tool_use':
        return <Bot size={14} className="text-yellow-400" />
      case 'stream.tool_result':
        return <CheckCircle size={14} className="text-green-400" />
      case 'stream.result':
        return <CheckCircle size={14} className="text-green-400" />
      case 'stream.error':
        return <XCircle size={14} className="text-red-400" />
      case 'run.completed':
        return <CheckCircle size={14} className="text-green-400" />
      case 'run.failed':
        return <XCircle size={14} className="text-red-400" />
      case 'intervention.pause':
        return <User size={14} className="text-yellow-400" />
      default:
        return <ArrowRight size={14} className="text-gray-400" />
    }
  }

  const getEventContent = () => {
    switch (event.type) {
      case 'stream.system': {
        const role = safeString(getPayloadValue(event, 'role'))
        return (
          <span className="text-blue-400">
            {agentName || 'Agent'} started
            {role && <span className="text-gray-400"> as {role}</span>}
          </span>
        )
      }
      case 'stream.assistant':
        return (
          <div className="text-gray-300 whitespace-pre-wrap">
            {safeString(event.content, '...').trim() || '...'}
          </div>
        )
      case 'stream.user':
        return (
          <div className="text-cyan-300 whitespace-pre-wrap">
            {safeString(event.content).trim()}
          </div>
        )
      case 'stream.tool_use':
        return (
          <span className="text-yellow-400">
            Using tool: {event.tool_name}
          </span>
        )
      case 'stream.tool_result':
        return (
          <div>
            <span className="text-green-400">Tool result: {event.tool_name}</span>
            {event.tool_output && (
              <pre className="mt-1 text-xs text-gray-400 bg-gray-800 p-2 rounded overflow-auto max-h-32">
                {safeString(event.tool_output).slice(0, 500)}
              </pre>
            )}
          </div>
        )
      case 'stream.result':
        return (
          <span className="text-green-400">
            {agentName || 'Agent'} completed
          </span>
        )
      case 'stream.error':
        return (
          <span className="text-red-400">
            Error: {event.content || 'Unknown error'}
          </span>
        )
      case 'run.completed':
        return <span className="text-green-400">Pattern execution completed</span>
      case 'run.failed':
        return <span className="text-red-400">Pattern execution failed</span>
      case 'run.started':
        return <span className="text-gray-300">Run started</span>
      case 'intervention.pause':
        return (
          <span className="text-yellow-400">
            Checkpoint: {safeString(getPayloadValue(event, 'checkpoint'))}
          </span>
        )
      default:
        return <span className="text-gray-400">{safeString(event.type)}</span>
    }
  }

  return (
    <div className="flex items-start gap-3 p-3 bg-gray-900/50 rounded-lg border border-gray-800">
      <div className="mt-0.5">{getEventIcon()}</div>
      <div className="flex-1 min-w-0">
        {getEventContent()}
        <div className="text-xs text-gray-500 mt-1">
          {formatEventTime(event.timestamp)}
        </div>
      </div>
    </div>
  )
}
