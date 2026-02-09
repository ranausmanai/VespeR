import { useState } from 'react'
import { Send, MessageSquare } from 'lucide-react'

interface ControlPanelProps {
  onInject: (message: string) => void
  isPaused: boolean
  canInject?: boolean
  disabledReason?: string
}

export default function ControlPanel({
  onInject,
  isPaused,
  canInject = true,
  disabledReason,
}: ControlPanelProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const injectDisabled = isPaused || sending || !canInject

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim() || injectDisabled) return

    setSending(true)
    try {
      await onInject(message.trim())
      setMessage('')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="border-t border-gray-800 bg-gray-900/50 p-4">
      <form onSubmit={handleSubmit} className="flex gap-3">
        <div className="flex-1 relative">
          <MessageSquare
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
          />
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={
              !canInject
                ? (disabledReason || "Injection is unavailable for this run type")
                : isPaused
                  ? "Run is paused - resume to inject messages"
                  : "Inject a message into the conversation..."
            }
            disabled={injectDisabled}
            className={`
              w-full pl-10 pr-4 py-2.5 rounded-lg
              bg-gray-800 border border-gray-700
              text-white placeholder-gray-500
              focus:outline-none focus:border-claude-500
              disabled:opacity-50 disabled:cursor-not-allowed
            `}
          />
        </div>

        <button
          type="submit"
          disabled={!message.trim() || injectDisabled}
          className={`
            flex items-center gap-2 px-4 py-2.5 rounded-lg
            font-medium transition-all
            ${message.trim() && !injectDisabled
              ? 'bg-claude-600 hover:bg-claude-500 text-white'
              : 'bg-gray-800 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          <Send size={16} />
          Inject
        </button>
      </form>

      <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
        <span>Press Enter to send</span>
        {!canInject && (
          <span className="text-yellow-500">{disabledReason || 'Injection unavailable for this run'}</span>
        )}
        {canInject && isPaused && (
          <span className="text-yellow-500">Resume the run to inject messages</span>
        )}
      </div>
    </div>
  )
}
