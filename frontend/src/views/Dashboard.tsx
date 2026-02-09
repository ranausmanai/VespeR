import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Clock, Cpu, DollarSign, Folder, Zap, MessageSquare, MessageCircle, Workflow } from 'lucide-react'
import { getSessions, getRuns, getActiveRuns } from '../api/client'
import { Session, Run } from '../api/types'

interface ActiveInteractiveSession {
  id: string;
  session_id: string;
  is_running: boolean;
}

interface ActivePatternExecution {
  run_id: string;
  pattern_name: string;
  pattern_type: string;
  awaiting_human: boolean;
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [recentRuns, setRecentRuns] = useState<Run[]>([])
  const [activeChatSessions, setActiveChatSessions] = useState<ActiveInteractiveSession[]>([])
  const [activePatternExecutions, setActivePatternExecutions] = useState<ActivePatternExecution[]>([])
  const [activeControlRuns, setActiveControlRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const [sessionsData, runsData] = await Promise.all([
          getSessions(),
          getRuns(),
        ])
        setSessions(sessionsData.sessions)
        setRecentRuns(runsData.runs.slice(0, 10))
      } catch (e) {
        console.error('Failed to load dashboard data:', e)
      } finally {
        setLoading(false)
      }
    }

    async function loadActiveData() {
      try {
        const [interactiveResp, patternResp, controlResp] = await Promise.all([
          fetch('/api/interactive'),
          fetch('/api/execute/active'),
          getActiveRuns(),
        ])
        const interactiveData = await interactiveResp.json()
        setActiveChatSessions(interactiveData.sessions || [])

        if (patternResp.ok) {
          const patternData = await patternResp.json()
          setActivePatternExecutions(patternData.active_executions || [])
        } else {
          setActivePatternExecutions([])
        }

        setActiveControlRuns(controlResp.active_runs || [])
      } catch (e) {
        console.error('Failed to load active run data:', e)
      }
    }

    loadData()
    loadActiveData()

    // Poll for active sessions
    const interval = setInterval(loadActiveData, 5000)
    return () => clearInterval(interval)
  }, [])

  const totalTokens = recentRuns.reduce((sum, r) => sum + r.tokens_in + r.tokens_out, 0)
  const totalCost = recentRuns.reduce((sum, r) => sum + r.cost_usd, 0)
  const totalActiveWork = activeControlRuns.length + activeChatSessions.length + activePatternExecutions.length
  const activeInteractiveRunIds = useMemo(
    () => new Set(activeChatSessions.map(s => s.id)),
    [activeChatSessions]
  )
  const activeControlRunIds = useMemo(
    () => new Set(activeControlRuns.map(r => r.id)),
    [activeControlRuns]
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-claude-500" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-gray-400">Visual control plane for Claude Code</p>
        </div>
        <Link
          to="/interactive?new=1"
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          <MessageSquare size={18} />
          Start Interactive Session
        </Link>
      </div>

      {/* Active Interactive Sessions Banner */}
      {activeChatSessions.length > 0 && (
        <div className="mb-6 p-4 bg-green-950/30 border border-green-800 rounded-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <MessageCircle size={20} className="text-green-400" />
              <div>
                <h3 className="font-medium text-white">
                  {activeChatSessions.length} Active Interactive Session{activeChatSessions.length > 1 ? 's' : ''}
                </h3>
                <p className="text-sm text-gray-400">Click to rejoin your conversation with Claude</p>
              </div>
            </div>
            <Link
              to="/interactive"
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg transition-colors"
            >
              <MessageCircle size={16} />
              Rejoin Session
            </Link>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
            {activeChatSessions.map((s) => (
              <Link
                key={s.id}
                to={`/interactive?runId=${encodeURIComponent(s.id)}`}
                className="px-3 py-2 rounded-lg bg-gray-900/60 border border-green-900 hover:border-green-600 text-sm text-gray-200 truncate"
              >
                {s.id}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={<Activity className="text-green-400" />}
          label="Active Work"
          value={totalActiveWork.toString()}
          highlight={totalActiveWork > 0}
        />
        <StatCard
          icon={<Folder className="text-blue-400" />}
          label="Sessions"
          value={sessions.length.toString()}
        />
        <StatCard
          icon={<Zap className="text-yellow-400" />}
          label="Total Tokens"
          value={formatNumber(totalTokens)}
        />
        <StatCard
          icon={<DollarSign className="text-green-400" />}
          label="Total Cost"
          value={`$${totalCost.toFixed(4)}`}
        />
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Active Runs */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Activity size={18} className="text-green-400" />
            Active Runs
          </h2>

          {totalActiveWork === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Cpu size={32} className="mx-auto mb-2 opacity-50" />
              <p>No active work</p>
              <p className="text-sm mt-1">
                Start Interactive, run a Pattern, or use <code className="bg-gray-800 px-1 rounded">agentling run</code>
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {activePatternExecutions.map((exec) => (
                <Link
                  key={exec.run_id}
                  to={`/execution/${exec.run_id}`}
                  className="block p-3 rounded-lg border bg-purple-950/20 border-purple-800 hover:border-purple-600 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <Workflow size={14} className="text-purple-400" />
                      <p className="text-white font-medium truncate">{exec.pattern_name}</p>
                    </div>
                    <span className="text-xs text-purple-300">{exec.awaiting_human ? 'checkpoint' : 'running'}</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">{exec.pattern_type}</p>
                </Link>
              ))}

              {activeChatSessions.map((session) => (
                <Link
                  key={session.id}
                  to={`/interactive?runId=${encodeURIComponent(session.id)}`}
                  className="block p-3 rounded-lg border bg-green-950/20 border-green-800 hover:border-green-600 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <MessageCircle size={14} className="text-green-400" />
                      <p className="text-white font-medium truncate">Interactive Session</p>
                    </div>
                    <span className="text-xs text-green-300">running</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1 truncate">{session.id}</p>
                </Link>
              ))}

              {recentRuns
                .filter(r => activeControlRunIds.has(r.id))
                .map(run => (
                  <RunCard key={run.id} run={run} active activeInteractiveRunIds={activeInteractiveRunIds} />
                ))}
            </div>
          )}
        </div>

        {/* Recent Runs */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Clock size={18} className="text-gray-400" />
            Recent Runs
          </h2>

          {recentRuns.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Clock size={32} className="mx-auto mb-2 opacity-50" />
              <p>No runs yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {recentRuns.slice(0, 5).map(run => (
                <RunCard key={run.id} run={run} activeInteractiveRunIds={activeInteractiveRunIds} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sessions */}
      <div className="mt-6 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Folder size={18} className="text-blue-400" />
          Sessions
        </h2>

        {sessions.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Folder size={32} className="mx-auto mb-2 opacity-50" />
            <p>No sessions yet</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {sessions.slice(0, 6).map(session => (
              <SessionCard key={session.id} session={session} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
  highlight = false,
}: {
  icon: React.ReactNode
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div
      className={`
        p-4 rounded-xl border
        ${highlight
          ? 'bg-green-950/30 border-green-800'
          : 'bg-gray-900 border-gray-800'
        }
      `}
    >
      <div className="flex items-center gap-3">
        {icon}
        <div>
          <p className="text-sm text-gray-400">{label}</p>
          <p className="text-xl font-semibold text-white">{value}</p>
        </div>
      </div>
    </div>
  )
}

function RunCard({
  run,
  active = false,
  activeInteractiveRunIds
}: {
  run: Run
  active?: boolean
  activeInteractiveRunIds: Set<string>
}) {
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-500',
    running: 'bg-green-500 animate-pulse',
    paused: 'bg-yellow-500',
    completed: 'bg-blue-500',
    failed: 'bg-red-500',
  }

  return (
    <Link
      to={getRunRoute(run, activeInteractiveRunIds)}
      className={`
        block p-3 rounded-lg border transition-all
        ${active
          ? 'bg-green-950/20 border-green-800 hover:border-green-600'
          : 'bg-gray-800/50 border-gray-700 hover:border-gray-600'
        }
      `}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${statusColors[run.status] || 'bg-gray-500'}`} />
          <span className="text-sm font-medium text-white truncate max-w-[200px]">
            {run.prompt.slice(0, 50)}...
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>{run.model}</span>
          <span>{formatDuration(run.duration_ms)}</span>
        </div>
      </div>
    </Link>
  )
}

function getRunRoute(run: Run, activeInteractiveRunIds: Set<string>): string {
  if (activeInteractiveRunIds.has(run.id)) {
    return `/interactive?runId=${encodeURIComponent(run.id)}`
  }
  const prompt = run.prompt || ''
  if (prompt.startsWith('[Interactive Session]')) {
    return `/interactive?new=1&sessionId=${encodeURIComponent(run.session_id)}`
  }
  if (prompt.startsWith('[Agent Pattern:') || prompt.startsWith('[Agent:')) {
    return `/execution/${run.id}`
  }
  return `/runs/${run.id}`
}

function SessionCard({ session }: { session: Session }) {
  return (
    <Link
      to={`/sessions?id=${session.id}`}
      className="block p-3 rounded-lg bg-gray-800/50 border border-gray-700 hover:border-gray-600 transition-all"
    >
      <div className="flex items-center gap-2 mb-2">
        <Folder size={16} className="text-blue-400" />
        <span className="font-medium text-white truncate">
          {session.name || 'Unnamed'}
        </span>
      </div>
      <p className="text-xs text-gray-400 truncate font-mono">
        {session.working_dir}
      </p>
    </Link>
  )
}

function formatNumber(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}
