import { create } from 'zustand'
import { AgentlingEvent, Run, Session } from '../api/types'

interface AppState {
  // Connection
  connected: boolean
  setConnected: (connected: boolean) => void

  // Sessions
  sessions: Session[]
  setSessions: (sessions: Session[]) => void
  currentSession: Session | null
  setCurrentSession: (session: Session | null) => void

  // Runs
  runs: Run[]
  setRuns: (runs: Run[]) => void
  currentRun: Run | null
  setCurrentRun: (run: Run | null) => void
  activeRuns: string[]
  setActiveRuns: (runIds: string[]) => void

  // Events
  events: AgentlingEvent[]
  addEvent: (event: AgentlingEvent) => void
  setEvents: (events: AgentlingEvent[]) => void
  clearEvents: () => void

  // UI State
  selectedEventId: string | null
  setSelectedEventId: (id: string | null) => void
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  viewMode: 'dag' | 'timeline' | 'split'
  setViewMode: (mode: 'dag' | 'timeline' | 'split') => void
}

export const useStore = create<AppState>((set) => ({
  // Connection
  connected: false,
  setConnected: (connected) => set({ connected }),

  // Sessions
  sessions: [],
  setSessions: (sessions) => set({ sessions }),
  currentSession: null,
  setCurrentSession: (session) => set({ currentSession: session }),

  // Runs
  runs: [],
  setRuns: (runs) => set({ runs }),
  currentRun: null,
  setCurrentRun: (run) => set({ currentRun: run }),
  activeRuns: [],
  setActiveRuns: (runIds) => set({ activeRuns: runIds }),

  // Events
  events: [],
  addEvent: (event) => set((state) => ({
    events: [...state.events, event].slice(-1000) // Keep last 1000 events
  })),
  setEvents: (events) => set({ events }),
  clearEvents: () => set({ events: [] }),

  // UI State
  selectedEventId: null,
  setSelectedEventId: (id) => set({ selectedEventId: id }),
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  viewMode: 'split',
  setViewMode: (mode) => set({ viewMode: mode }),
}))
