import { useEffect, useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Play, Pause, RotateCcw, FastForward } from 'lucide-react'
import { getRun, getRunEvents } from '../api/client'
import { Run, AgentlingEvent } from '../api/types'
import TaskDAG from '../components/dag/TaskDAG'
import EventTimeline from '../components/timeline/EventTimeline'

export default function Replay() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const [allEvents, setAllEvents] = useState<AgentlingEvent[]>([])
  const [visibleEvents, setVisibleEvents] = useState<AgentlingEvent[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    if (!runId) return

    async function loadRun() {
      try {
        const [runData, eventsData] = await Promise.all([
          getRun(runId!),
          getRunEvents(runId!),
        ])
        setRun(runData)
        setAllEvents(eventsData.events)
      } catch (e) {
        console.error('Failed to load run:', e)
      } finally {
        setLoading(false)
      }
    }

    loadRun()
  }, [runId])

  useEffect(() => {
    setVisibleEvents(allEvents.slice(0, currentIndex + 1))
  }, [currentIndex, allEvents])

  useEffect(() => {
    if (playing && currentIndex < allEvents.length - 1) {
      const delay = calculateDelay()
      intervalRef.current = window.setTimeout(() => {
        setCurrentIndex(prev => Math.min(prev + 1, allEvents.length - 1))
      }, delay)
    } else if (currentIndex >= allEvents.length - 1) {
      setPlaying(false)
    }

    return () => {
      if (intervalRef.current) {
        clearTimeout(intervalRef.current)
      }
    }
  }, [playing, currentIndex, allEvents.length, speed])

  const calculateDelay = () => {
    if (currentIndex >= allEvents.length - 1) return 100
    const current = new Date(allEvents[currentIndex].timestamp)
    const next = new Date(allEvents[currentIndex + 1].timestamp)
    const diff = (next.getTime() - current.getTime()) / speed
    return Math.min(Math.max(diff, 50), 2000)
  }

  const handlePlayPause = () => {
    setPlaying(prev => !prev)
  }

  const handleReset = () => {
    setPlaying(false)
    setCurrentIndex(0)
  }

  const handleSpeedChange = () => {
    const speeds = [0.5, 1, 2, 4, 8]
    const currentIdx = speeds.indexOf(speed)
    setSpeed(speeds[(currentIdx + 1) % speeds.length])
  }

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCurrentIndex(parseInt(e.target.value))
  }

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

  const progress = allEvents.length > 0 ? (currentIndex / (allEvents.length - 1)) * 100 : 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900/50">
        <div>
          <h1 className="text-lg font-semibold text-white">
            Replay: {run.prompt.slice(0, 50)}...
          </h1>
          <p className="text-sm text-gray-400">
            {allEvents.length} events • {formatDuration(run.duration_ms)}
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300"
            title="Reset"
          >
            <RotateCcw size={18} />
          </button>
          <button
            onClick={handlePlayPause}
            className={`p-2 rounded-lg ${
              playing
                ? 'bg-yellow-600 hover:bg-yellow-500'
                : 'bg-green-600 hover:bg-green-500'
            } text-white`}
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button
            onClick={handleSpeedChange}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300"
          >
            <FastForward size={16} />
            {speed}x
          </button>
        </div>
      </header>

      {/* Timeline scrubber */}
      <div className="px-4 py-3 bg-gray-900/30 border-b border-gray-800">
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400 w-20">
            {currentIndex + 1} / {allEvents.length}
          </span>
          <input
            type="range"
            min="0"
            max={Math.max(0, allEvents.length - 1)}
            value={currentIndex}
            onChange={handleSliderChange}
            className="flex-1 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-claude-500"
          />
          <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-claude-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        <div className="w-1/2 border-r border-gray-800">
          <TaskDAG events={visibleEvents} />
        </div>
        <div className="w-1/2 overflow-auto">
          <EventTimeline events={visibleEvents} highlight={currentIndex} />
        </div>
      </div>
    </div>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}
