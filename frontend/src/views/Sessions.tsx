import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Folder, Play, ChevronRight } from 'lucide-react'
import { getSessions, getSession, createSession, pickSessionDirectory } from '../api/client'
import { Session, Run } from '../api/types'

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedSession, setSelectedSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [newSessionName, setNewSessionName] = useState('')
  const [newSessionDir, setNewSessionDir] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [isPickingDir, setIsPickingDir] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [activeInteractiveRunIds, setActiveInteractiveRunIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    async function loadSessions() {
      try {
        const data = await getSessions()
        setSessions(data.sessions)
        if (data.sessions.length > 0) {
          const full = await getSession(data.sessions[0].id)
          setSelectedSession(full)
        }
      } catch (e) {
        console.error('Failed to load sessions:', e)
      } finally {
        setLoading(false)
      }
    }

    async function loadActiveInteractiveRuns() {
      try {
        const response = await fetch('/api/interactive')
        const data = await response.json()
        const ids = new Set<string>((data.sessions || []).map((s: { id: string }) => s.id))
        setActiveInteractiveRunIds(ids)
      } catch (e) {
        console.error('Failed to load active interactive runs:', e)
      }
    }

    loadSessions()
    loadActiveInteractiveRuns()
    const interval = setInterval(loadActiveInteractiveRuns, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleSelectSession = async (session: Session) => {
    try {
      const full = await getSession(session.id)
      setSelectedSession(full)
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  const handleCreateSession = async (e: FormEvent) => {
    e.preventDefault()

    const workingDir = newSessionDir.trim()
    if (!workingDir) {
      setCreateError('Working directory is required.')
      return
    }

    setCreateError(null)
    setIsCreating(true)
    try {
      const created = await createSession(workingDir, newSessionName.trim() || undefined)
      const data = await getSessions()
      setSessions(data.sessions)
      const full = await getSession(created.id)
      setSelectedSession(full)
      setNewSessionName('')
      setNewSessionDir('')
    } catch (e) {
      console.error('Failed to create session:', e)
      setCreateError(e instanceof Error ? e.message : 'Failed to create session.')
    } finally {
      setIsCreating(false)
    }
  }

  const handleBrowseDirectory = async () => {
    setCreateError(null)
    setIsPickingDir(true)
    try {
      const result = await pickSessionDirectory()
      if (result.directory) {
        setNewSessionDir(result.directory)
      } else if (!result.cancelled) {
        setCreateError('Directory picker is unavailable. Please enter the path manually.')
      }
    } catch (e) {
      console.error('Failed to pick directory:', e)
      setCreateError('Directory picker is unavailable. Please enter the path manually.')
    } finally {
      setIsPickingDir(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-claude-500" />
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* Session list */}
      <div className="w-80 border-r border-gray-800 overflow-auto">
        <div className="p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">Sessions</h2>
          <p className="text-sm text-gray-400 mt-1">{sessions.length} sessions</p>
        </div>

        <form onSubmit={handleCreateSession} className="p-3 border-b border-gray-800 space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              value={newSessionDir}
              onChange={(e) => setNewSessionDir(e.target.value)}
              placeholder="/absolute/path/to/project"
              className="flex-1 px-3 py-2 rounded bg-gray-900 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-claude-500"
            />
            <button
              type="button"
              onClick={handleBrowseDirectory}
              disabled={isPickingDir}
              className="px-3 py-2 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-60 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors"
            >
              {isPickingDir ? 'Opening...' : 'Browse...'}
            </button>
          </div>
          <input
            type="text"
            value={newSessionName}
            onChange={(e) => setNewSessionName(e.target.value)}
            placeholder="Session name (optional)"
            className="w-full px-3 py-2 rounded bg-gray-900 border border-gray-700 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-claude-500"
          />
          <button
            type="submit"
            disabled={isCreating}
            className="w-full px-3 py-2 rounded bg-claude-600 hover:bg-claude-500 disabled:opacity-60 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors"
          >
            {isCreating ? 'Creating...' : 'New Session'}
          </button>
          {createError && (
            <p className="text-xs text-red-400">{createError}</p>
          )}
        </form>

        <div className="p-2">
          {sessions.map(session => (
            <button
              key={session.id}
              onClick={() => handleSelectSession(session)}
              className={`
                w-full text-left p-3 rounded-lg mb-1 transition-all
                ${selectedSession?.id === session.id
                  ? 'bg-claude-600/20 border border-claude-600'
                  : 'hover:bg-gray-800 border border-transparent'
                }
              `}
            >
              <div className="flex items-center gap-2 mb-1">
                <Folder size={16} className="text-blue-400" />
                <span className="font-medium text-white truncate">
                  {session.name || 'Unnamed'}
                </span>
              </div>
              <p className="text-xs text-gray-400 truncate font-mono">
                {session.working_dir}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {new Date(session.updated_at).toLocaleDateString()}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Session detail */}
      <div className="flex-1 overflow-auto p-6">
        {selectedSession ? (
          <>
            <div className="mb-6">
              <h1 className="text-2xl font-bold text-white mb-2">
                {selectedSession.name || 'Unnamed Session'}
              </h1>
              <p className="text-gray-400 font-mono text-sm">
                {selectedSession.working_dir}
              </p>
              <div className="mt-4 flex items-center gap-2">
                <Link
                  to={`/interactive?new=1&sessionId=${encodeURIComponent(selectedSession.id)}`}
                  className="px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 text-sm font-medium text-white transition-colors"
                >
                  Resume Latest
                </Link>
                <Link
                  to={`/interactive?new=1&sessionId=${encodeURIComponent(selectedSession.id)}&snapshot=0`}
                  className="px-3 py-2 rounded bg-gray-700 hover:bg-gray-600 text-sm font-medium text-white transition-colors"
                >
                  Start Fresh
                </Link>
              </div>
            </div>

            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-400 mb-3">Runs</h3>
              {selectedSession.runs && selectedSession.runs.length > 0 ? (
                <div className="space-y-2">
                  {selectedSession.runs.map((run: Run) => (
                    <div
                      key={run.id}
                      className="p-4 rounded-lg bg-gray-800/50 border border-gray-700"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <Link
                          to={getRunRoute(run, activeInteractiveRunIds)}
                          className="min-w-0 flex-1"
                        >
                          <div className="flex items-center gap-3">
                            <StatusBadge status={run.status} />
                            <div className="min-w-0">
                              <p className="text-white font-medium truncate">
                                {run.prompt.slice(0, 80)}...
                              </p>
                              <p className="text-sm text-gray-400">
                                {run.model} • {formatRunDuration(run)} • {run.tokens_in + run.tokens_out} tokens
                              </p>
                            </div>
                          </div>
                        </Link>
                        <ChevronRight size={16} className="text-gray-500 mt-1 shrink-0" />
                      </div>
                      {canResumeFromRun(run) && (
                        <div className="mt-3 flex items-center gap-2">
                          <Link
                            to={`/interactive?new=1&sessionId=${encodeURIComponent(selectedSession.id)}&snapshotRunId=${encodeURIComponent(run.id)}`}
                            className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-xs font-medium text-white transition-colors"
                          >
                            Resume this run
                          </Link>
                          <span className="text-xs text-gray-400">
                            Starts a new interactive run with this run&apos;s snapshot context (if available).
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Play size={32} className="mx-auto mb-2 opacity-50" />
                  <p>No runs yet</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <p>Select a session to view details</p>
          </div>
        )}
      </div>
    </div>
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

function canResumeFromRun(run: Run): boolean {
  // Allow resuming from any finished run type (interactive, agent, or pattern).
  // For active runs, users should rejoin directly via the active session picker.
  return run.status !== 'running' && run.status !== 'pending'
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400',
    running: 'bg-green-500/20 text-green-400',
    paused: 'bg-yellow-500/20 text-yellow-400',
    completed: 'bg-blue-500/20 text-blue-400',
    failed: 'bg-red-500/20 text-red-400',
  }

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${styles[status] || 'bg-gray-500/20 text-gray-400'}`}>
      {status}
    </span>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function formatRunDuration(run: Run): string {
  const duration = Number(run.duration_ms)
  if (Number.isFinite(duration) && duration >= 0) {
    return formatDuration(duration)
  }

  const started = run.started_at ? Date.parse(run.started_at) : NaN
  const created = run.created_at ? Date.parse(run.created_at) : NaN
  const anchor = Number.isFinite(started) ? started : created
  const completed = run.completed_at ? Date.parse(run.completed_at) : NaN

  if (Number.isFinite(anchor) && Number.isFinite(completed) && completed >= anchor) {
    return formatDuration(completed - anchor)
  }

  if (run.status === 'running' && Number.isFinite(anchor)) {
    return formatDuration(Math.max(0, Date.now() - anchor))
  }

  return '—'
}
