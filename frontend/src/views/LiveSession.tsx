import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Pause, Play, Square,
  Clock, Zap, DollarSign, FileCode, Terminal
} from 'lucide-react'
import { getRun, getRunEvents, pauseRun, resumeRun, abortRun, injectMessage } from '../api/client'
import { Run, AgentlingEvent } from '../api/types'
import { useStore } from '../store'
import { wsClient } from '../api/websocket'
import TaskDAG from '../components/dag/TaskDAG'
import EventTimeline from '../components/timeline/EventTimeline'
import ControlPanel from '../components/control/ControlPanel'

export default function LiveSession() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const [run, setRun] = useState<Run | null>(null)
  const [loading, setLoading] = useState(true)
  const { events, setEvents, addEvent, clearEvents, viewMode, setViewMode } = useStore()

  useEffect(() => {
    if (!runId) return

    async function loadRun() {
      try {
        clearEvents()
        const [runData, eventsData] = await Promise.all([
          getRun(runId!),
          getRunEvents(runId!),
        ])
        setRun(runData)
        setEvents(eventsData.events)

        // Subscribe to run-specific events
        wsClient.connect(runId)
      } catch (e) {
        console.error('Failed to load run:', e)
      } finally {
        setLoading(false)
      }
    }

    loadRun()

    // Poll for run updates if active
    const pollInterval = setInterval(async () => {
      try {
        const updated = await getRun(runId!)
        setRun(updated)
      } catch (e) {
        console.error('Poll error:', e)
      }
    }, 2000)

    return () => {
      clearInterval(pollInterval)
    }
  }, [runId, setEvents, clearEvents])

  // Subscribe to new events from WebSocket
  useEffect(() => {
    const unsub = wsClient.onEvent((event) => {
      if (event.run_id === runId) {
        addEvent(event)
      }
    })

    return unsub
  }, [runId, addEvent])

  useEffect(() => {
    if (!run) return
    const prompt = run.prompt || ''
    const isAgentPatternRun = prompt.startsWith('[Agent Pattern:') || prompt.startsWith('[Agent:')
    if (isAgentPatternRun) {
      navigate(`/execution/${run.id}`, { replace: true })
    }
  }, [run, navigate])

  useEffect(() => {
    if (!run) return
    const prompt = run.prompt || ''
    if (prompt.startsWith('[Interactive Session]')) {
      navigate('/interactive', { replace: true })
      return
    }

    if (run.status !== 'running') return

    const detectActiveInteractiveRun = async () => {
      try {
        const response = await fetch('/api/interactive')
        const data = await response.json()
        const activeIds = new Set<string>((data.sessions || []).map((s: { id: string }) => s.id))
        if (activeIds.has(run.id)) {
          navigate('/interactive', { replace: true })
        }
      } catch (e) {
        console.error('Failed to detect interactive run:', e)
      }
    }

    detectActiveInteractiveRun()
  }, [run, navigate])

  const handlePause = async () => {
    if (!runId) return
    await pauseRun(runId)
    setRun(prev => prev ? { ...prev, status: 'paused' } : null)
  }

  const handleResume = async () => {
    if (!runId) return
    await resumeRun(runId)
    setRun(prev => prev ? { ...prev, status: 'running' } : null)
  }

  const handleAbort = async () => {
    if (!runId) return
    await abortRun(runId)
    setRun(prev => prev ? { ...prev, status: 'failed' } : null)
  }

  const handleInject = async (message: string) => {
    if (!runId) return
    await injectMessage(runId, message)
  }

  const activityItems = useMemo(() => buildActivityItems(events), [events])
  const canInject = false

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-claude-500" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        Run not found
      </div>
    )
  }

  const isActive = run.status === 'running' || run.status === 'paused'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900/50">
        <div className="flex items-center gap-4">
          <StatusIndicator status={run.status} />
          <div>
            <h1 className="text-lg font-semibold text-white truncate max-w-md">
              {run.prompt.slice(0, 60)}...
            </h1>
            <div className="flex items-center gap-4 text-sm text-gray-400">
              <span className="flex items-center gap-1">
                <Clock size={14} />
                {formatDuration(run.duration_ms)}
              </span>
              <span className="flex items-center gap-1">
                <Zap size={14} />
                {(run.tokens_in + run.tokens_out).toLocaleString()} tokens
              </span>
              <span className="flex items-center gap-1">
                <DollarSign size={14} />
                ${run.cost_usd.toFixed(4)}
              </span>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
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

          {/* Run controls */}
          {isActive && (
            <>
              {run.status === 'running' ? (
                <button
                  onClick={handlePause}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-600 hover:bg-yellow-500 text-white text-sm"
                >
                  <Pause size={16} />
                  Pause
                </button>
              ) : (
                <button
                  onClick={handleResume}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm"
                >
                  <Play size={16} />
                  Resume
                </button>
              )}
              <button
                onClick={handleAbort}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm"
              >
                <Square size={16} />
                Abort
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {viewMode === 'dag' && (
          <div className="flex-1">
            <TaskDAG events={events} />
          </div>
        )}

        {viewMode === 'timeline' && (
          <div className="flex-1 overflow-auto">
            <EventTimeline events={events} mode="full" />
          </div>
        )}

        {viewMode === 'split' && (
          <>
            <div className="w-[42%] border-r border-gray-800">
              <TaskDAG events={events} />
            </div>
            <div className="w-[38%] overflow-auto border-r border-gray-800">
              <EventTimeline events={events} mode="assistant_focus" />
            </div>
            <div className="w-[20%] overflow-auto bg-gray-900/30">
              <ActivityPane items={activityItems} />
            </div>
          </>
        )}
      </div>

      {/* Control panel (for active runs) */}
      {isActive && (
        <ControlPanel
          onInject={handleInject}
          isPaused={run.status === 'paused'}
          canInject={canInject}
          disabledReason="Injection is only supported in Interactive mode right now."
        />
      )}
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
              <div className="text-[10px] text-gray-600 mt-1">{formatTime(item.timestamp)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    if (Number.isNaN(date.getTime())) return timestamp
    return date.toLocaleTimeString()
  } catch {
    return timestamp
  }
}

function StatusIndicator({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-500',
    running: 'bg-green-500 animate-pulse',
    paused: 'bg-yellow-500',
    completed: 'bg-blue-500',
    failed: 'bg-red-500',
  }

  return (
    <div className="flex items-center gap-2">
      <span className={`w-3 h-3 rounded-full ${styles[status] || 'bg-gray-500'}`} />
      <span className="text-sm font-medium text-gray-300 capitalize">{status}</span>
    </div>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}
