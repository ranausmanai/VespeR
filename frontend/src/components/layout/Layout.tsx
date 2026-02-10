import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { Activity, Home, Layers, Wifi, WifiOff, Bot, Workflow, MessageCircle, Github, Mail, Globe } from 'lucide-react'
import { useStore } from '../../store'
import { wsClient } from '../../api/websocket'
import { getActiveRuns } from '../../api/client'

export default function Layout() {
  const location = useLocation()
  const { connected, setConnected, activeRuns, setActiveRuns, addEvent } = useStore()
  const [activeInteractiveSessions, setActiveInteractiveSessions] = useState(0)
  const [activePatternExecutions, setActivePatternExecutions] = useState(0)

  useEffect(() => {
    // Connect WebSocket
    wsClient.connect()

    // Subscribe to connection status
    const unsubConnection = wsClient.onConnection(setConnected)

    // Subscribe to events
    const unsubEvents = wsClient.onEvent(addEvent)

    // Poll for active runs
    const pollActive = async () => {
      try {
        const data = await getActiveRuns()
        setActiveRuns(data.active_runs.map(r => r.id))
      } catch (e) {
        console.error('Failed to fetch active runs:', e)
      }
    }

    // Poll for active interactive sessions
    const pollInteractive = async () => {
      try {
        const response = await fetch('/api/interactive')
        const data = await response.json()
        setActiveInteractiveSessions(data.sessions?.length || 0)
      } catch (e) {
        console.error('Failed to fetch interactive sessions:', e)
      }
    }

    const pollPatternExecutions = async () => {
      try {
        const response = await fetch('/api/execute/active')
        if (!response.ok) return
        const data = await response.json()
        setActivePatternExecutions(data.count || 0)
      } catch (e) {
        console.error('Failed to fetch active pattern executions:', e)
      }
    }

    pollActive()
    pollInteractive()
    pollPatternExecutions()
    const interval = setInterval(() => {
      pollActive()
      pollInteractive()
      pollPatternExecutions()
    }, 5000)

    return () => {
      unsubConnection()
      unsubEvents()
      clearInterval(interval)
    }
  }, [setConnected, setActiveRuns, addEvent])

  const navItems = [
    { path: '/', icon: Home, label: 'Dashboard' },
    { path: '/sessions', icon: Layers, label: 'Sessions' },
    { path: '/interactive', icon: MessageCircle, label: 'Interactive', badge: activeInteractiveSessions },
    { path: '/agents', icon: Bot, label: 'Agents' },
    { path: '/patterns', icon: Workflow, label: 'Patterns', badge: activePatternExecutions },
  ]

  return (
    <div className="flex h-screen bg-gray-950">
      {/* Sidebar */}
      <aside className="w-56 flex flex-col py-4 px-3 bg-gray-900 border-r border-gray-800">
        {/* Originally Agentling, now rebranded as VespeR. */}
        {/* Logo */}
        <a
          href="https://vesper.run"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 px-2 mb-6 rounded-lg hover:bg-gray-800/60 transition-colors"
          title="Open VespeR website"
        >
          <img src="/favicon.svg" alt="VespeR logo" className="w-10 h-10 rounded-xl" />
          <div>
            <p className="text-white font-semibold leading-tight">VespeR</p>
            <p className="text-xs text-gray-400 leading-tight hover:text-blue-300 transition-colors">VespeR.run</p>
          </div>
        </a>

        {/* Nav */}
        <nav className="flex-1 flex flex-col gap-2">
          {navItems.map(({ path, icon: Icon, label, badge }) => (
            <Link
              key={path}
              to={path}
              className={`
                relative rounded-lg flex items-center gap-3 px-3 py-2
                transition-all duration-200
                ${location.pathname === path
                  ? 'bg-claude-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }
                ${badge ? 'text-green-400' : ''}
              `}
              title={badge ? `${label} (${badge} active)` : label}
            >
              <Icon size={20} />
              <span className="text-sm font-medium">{label}</span>
              {badge ? (
                <span className="ml-auto min-w-5 h-5 px-1 bg-green-500 rounded-full text-xs text-white flex items-center justify-center animate-pulse">
                  {badge}
                </span>
              ) : null}
            </Link>
          ))}
        </nav>

        {/* Status indicators */}
        <div className="flex flex-col gap-3 mt-auto px-2">
          <div className="flex items-center gap-2">
            <a
              href="https://vesper.run"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center w-8 h-8 rounded-md text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
              title="Website"
            >
              <Globe size={16} />
            </a>

            <a
              href="https://github.com/ranausmanai/VespeR"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center w-8 h-8 rounded-md text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
              title="GitHub"
            >
              <Github size={16} />
            </a>

            <a
              href="mailto:usmanashrafrana@gmail.com"
              className="inline-flex items-center justify-center w-8 h-8 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
              title="Email"
            >
              <Mail size={16} />
            </a>

            <a
              href="https://x.com/UsmanReads"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center w-8 h-8 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
              title="X"
            >
              <span className="inline-flex items-center justify-center w-4 h-4 text-xs font-semibold">X</span>
            </a>
          </div>

          {activeRuns.length > 0 && (
            <div className="flex items-center justify-between text-sm" title={`${activeRuns.length} active runs`}>
              <div className="flex items-center gap-2 text-green-400">
                <Activity size={16} className="animate-pulse" />
                <span>Active Runs</span>
              </div>
              <span className="w-5 h-5 bg-green-500 rounded-full text-xs text-white flex items-center justify-center">
                {activeRuns.length}
              </span>
            </div>
          )}

          <div className="flex items-center gap-2 text-sm" title={connected ? 'Connected' : 'Disconnected'}>
            {connected ? (
              <>
                <Wifi size={16} className="text-green-400" />
                <span className="text-green-400">Connected</span>
              </>
            ) : (
              <>
                <WifiOff size={16} className="text-red-400" />
                <span className="text-red-400">Disconnected</span>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
