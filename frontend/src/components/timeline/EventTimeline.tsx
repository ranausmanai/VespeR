import { useRef, useEffect } from 'react'
import {
  MessageSquare, Terminal, FileCode, Check, X, AlertCircle,
  GitBranch, User, Settings, Bot, FileText, Edit
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { AgentlingEvent } from '../../api/types'

interface EventTimelineProps {
  events: AgentlingEvent[]
  highlight?: number
  mode?: 'full' | 'assistant_focus'
}

export default function EventTimeline({ events, highlight, mode = 'full' }: EventTimelineProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (bottomRef.current && highlight === undefined) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events.length, highlight])

  // Scroll to highlighted event
  useEffect(() => {
    if (highlight !== undefined && containerRef.current) {
      const element = containerRef.current.querySelector(`[data-index="${highlight}"]`)
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlight])

  // Filter and process events for display
  const displayEvents = processEvents(events, mode)

  if (displayEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <MessageSquare size={32} className="mx-auto mb-2 opacity-50" />
          <p>No events yet</p>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="p-4 space-y-3">
      {displayEvents.map((item, index) => (
        <EventCard
          key={item.id}
          item={item}
          index={index}
          isHighlighted={highlight === index}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

interface DisplayItem {
  id: string
  type: 'user' | 'assistant' | 'tool' | 'tool_result' | 'system' | 'git' | 'status'
  content: string
  timestamp: string
  toolName?: string
  toolInput?: string
  filePath?: string
  command?: string
  isError?: boolean
}

function processEvents(events: AgentlingEvent[], mode: 'full' | 'assistant_focus'): DisplayItem[] {
  const items: DisplayItem[] = []
  let currentAssistantText = ''
  let lastAssistantTimestamp = ''

  for (const event of events) {
    const type = event.type

    // Skip internal/debug events
    if (['stream.init', 'stream.system', 'stream.start', 'metrics.tokens'].includes(type)) {
      continue
    }

    // User message
    if (type === 'stream.user') {
      // Flush any pending assistant text
      if (currentAssistantText) {
        items.push({
          id: `assistant-${event.id}`,
          type: 'assistant',
          content: currentAssistantText.trim(),
          timestamp: lastAssistantTimestamp,
        })
        currentAssistantText = ''
      }

      const content = extractUserDisplayText(event)
      if (content) {
        items.push({
          id: event.id,
          type: 'user',
          content: content,
          timestamp: event.timestamp,
        })
      }
      continue
    }

    // Assistant text (accumulate)
    if (type === 'stream.assistant') {
      const delta = event.payload?.delta as Record<string, unknown> | undefined
      const text = event.content || (delta?.text as string) || ''
      currentAssistantText += text
      lastAssistantTimestamp = event.timestamp
      continue
    }

    // Tool use - flush assistant text first
    if (type === 'stream.tool_use') {
      if (currentAssistantText) {
        items.push({
          id: `assistant-before-${event.id}`,
          type: 'assistant',
          content: currentAssistantText.trim(),
          timestamp: lastAssistantTimestamp,
        })
        currentAssistantText = ''
      }

      const toolName = event.tool_name || (event.payload?.name as string) || 'Unknown tool'
      const input = event.tool_input || event.payload?.input

      // Extract file path for Write/Edit/Read tools
      let filePath = ''
      let toolInput = ''
      if (input && typeof input === 'object') {
        const inputObj = input as Record<string, unknown>
        filePath = (inputObj.file_path as string) || (inputObj.path as string) || ''
        // For Write tool, show content preview
        if (toolName === 'Write' && inputObj.content) {
          const content = String(inputObj.content)
          toolInput = content.length > 200 ? content.slice(0, 200) + '...' : content
        }
      }

      const inputObj = (input && typeof input === 'object') ? input as Record<string, unknown> : undefined
      const command = toolName === 'Bash' && inputObj?.command ? String(inputObj.command) : undefined

      if (mode === 'full') {
        items.push({
          id: event.id,
          type: 'tool',
          content: getToolDescription(toolName, filePath, inputObj),
          timestamp: event.timestamp,
          toolName,
          toolInput,
          filePath,
          command,
        })
      }
      continue
    }

    // Tool result
    if (type === 'stream.tool_result') {
      const isError = event.is_error || (event.payload?.is_error as boolean)
      const output = event.tool_output || (event.payload?.output as string) || ''
      const toolName = event.tool_name || ''

      // Only show result if there's meaningful output or it's an error
      if ((output || isError) && mode === 'full') {
        items.push({
          id: event.id,
          type: 'tool_result',
          content: isError ? `Error: ${output}` : (output.length > 300 ? output.slice(0, 300) + '...' : output),
          timestamp: event.timestamp,
          toolName,
          isError,
        })
      }
      continue
    }

    // Stream result - flush remaining assistant text
    if (type === 'stream.result') {
      if (currentAssistantText) {
        items.push({
          id: `assistant-${event.id}`,
          type: 'assistant',
          content: currentAssistantText.trim(),
          timestamp: lastAssistantTimestamp,
        })
        currentAssistantText = ''
      }
      continue
    }

    // Git snapshot
    if (type === 'git.snapshot') {
      const dirtyFiles = (event.payload?.dirty_files || []) as string[]
      if (dirtyFiles.length > 0) {
        items.push({
          id: event.id,
          type: 'git',
          content: `${dirtyFiles.length} file${dirtyFiles.length > 1 ? 's' : ''} changed`,
          timestamp: event.timestamp,
        })
      }
      continue
    }

    // Run status events
    if (type === 'run.started') {
      items.push({
        id: event.id,
        type: 'status',
        content: 'Session started',
        timestamp: event.timestamp,
      })
      continue
    }

    if (type === 'run.completed') {
      items.push({
        id: event.id,
        type: 'status',
        content: 'Completed',
        timestamp: event.timestamp,
      })
      continue
    }

    if (type === 'run.failed') {
      items.push({
        id: event.id,
        type: 'status',
        content: (event.payload?.error as string) || 'Failed',
        timestamp: event.timestamp,
        isError: true,
      })
      continue
    }

    if (type === 'run.paused') {
      items.push({
        id: event.id,
        type: 'status',
        content: 'Paused',
        timestamp: event.timestamp,
      })
      continue
    }

    if (type === 'stream.error') {
      items.push({
        id: event.id,
        type: 'status',
        content: event.content || (event.payload?.message as string) || 'Error occurred',
        timestamp: event.timestamp,
        isError: true,
      })
      continue
    }
  }

  // Flush any remaining assistant text
  if (currentAssistantText) {
    items.push({
      id: 'assistant-final',
      type: 'assistant',
      content: currentAssistantText.trim(),
      timestamp: lastAssistantTimestamp,
    })
  }

  return items
}

function extractUserDisplayText(event: AgentlingEvent): string {
  const payload = (event.payload || {}) as Record<string, unknown>
  const message = payload.message as Record<string, unknown> | undefined
  const content = message?.content

  if (Array.isArray(content)) {
    const textParts: string[] = []
    for (const item of content) {
      if (!item || typeof item !== 'object') continue
      const typedItem = item as Record<string, unknown>
      const itemType = String(typedItem.type || '')
      if (itemType === 'tool_result') {
        // Tool results are rendered via tool cards; avoid flooding the user lane.
        continue
      }
      if (itemType === 'text') {
        const text = String(typedItem.text || '').trim()
        if (text) textParts.push(text)
      }
    }
    return textParts.join('\n').trim()
  }

  return String(event.content || payload.content || '').trim()
}

function getToolDescription(toolName: string, filePath: string, input?: Record<string, unknown>): string {
  const fileName = filePath ? filePath.split('/').pop() : ''

  switch (toolName) {
    case 'Write':
      return fileName ? `Creating ${fileName}` : 'Creating file'
    case 'Edit':
      return fileName ? `Editing ${fileName}` : 'Editing file'
    case 'Read':
      return fileName ? `Reading ${fileName}` : 'Reading file'
    case 'Bash': {
      const cmd = input?.command as string
      if (cmd) {
        const shortCmd = cmd.length > 50 ? cmd.slice(0, 50) + '...' : cmd
        return `$ ${shortCmd}`
      }
      return 'Running command'
    }
    case 'Glob':
      return 'Searching for files'
    case 'Grep':
      return 'Searching in files'
    case 'WebFetch':
      return 'Fetching from web'
    case 'WebSearch':
      return 'Searching the web'
    default:
      return `Using ${toolName}`
  }
}

function EventCard({
  item,
  index,
  isHighlighted,
}: {
  item: DisplayItem
  index: number
  isHighlighted: boolean
}) {
  return (
    <div
      data-index={index}
      className={`
        rounded-lg border transition-all
        ${isHighlighted
          ? 'border-claude-500 bg-claude-950/30'
          : 'border-gray-800'
        }
        ${item.type === 'user' ? 'bg-blue-950/30 border-blue-800/50' : ''}
        ${item.type === 'assistant' ? 'bg-gray-900/50' : ''}
        ${item.type === 'tool' ? 'bg-purple-950/20 border-purple-800/30' : ''}
        ${item.type === 'tool_result' && item.isError ? 'bg-red-950/20 border-red-800/30' : ''}
        ${item.type === 'status' && item.isError ? 'bg-red-950/20 border-red-800/30' : ''}
      `}
    >
      {item.type === 'user' && (
        <div className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <User size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-blue-400">You</span>
            <span className="text-xs text-gray-500">{formatTimestamp(item.timestamp)}</span>
          </div>
          <p className="text-gray-200 whitespace-pre-wrap">{item.content}</p>
        </div>
      )}

      {item.type === 'assistant' && (
        <div className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Bot size={16} className="text-purple-400" />
            <span className="text-sm font-medium text-purple-400">Claude</span>
            <span className="text-xs text-gray-500">{formatTimestamp(item.timestamp)}</span>
          </div>
          <div className="text-gray-200 prose prose-invert prose-sm max-w-none prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700 prose-code:text-purple-300 prose-code:before:content-none prose-code:after:content-none">
            <ReactMarkdown>{item.content}</ReactMarkdown>
          </div>
        </div>
      )}

      {item.type === 'tool' && (
        <div className="p-3">
          <div className="flex items-center gap-2">
            {getToolIcon(item.toolName || '')}
            <span className="text-sm text-purple-300 font-medium">{item.content}</span>
            <span className="text-xs text-gray-500">{formatTimestamp(item.timestamp)}</span>
          </div>
          {item.filePath && (
            <p className="text-xs text-gray-500 mt-1 ml-6 font-mono">{item.filePath}</p>
          )}
          {item.command && (
            <pre className="text-xs text-green-400 mt-2 ml-6 bg-gray-800/50 rounded p-2 overflow-x-auto font-mono">
              $ {item.command}
            </pre>
          )}
          {item.toolInput && !item.command && (
            <pre className="text-xs text-gray-400 mt-2 ml-6 bg-gray-800/50 rounded p-2 overflow-auto max-h-32">
              {item.toolInput}
            </pre>
          )}
        </div>
      )}

      {item.type === 'tool_result' && (
        <div className="p-3">
          <div className="flex items-center gap-2">
            {item.isError
              ? <X size={14} className="text-red-400" />
              : <Check size={14} className="text-green-400" />
            }
            <span className={`text-sm ${item.isError ? 'text-red-400' : 'text-green-400'}`}>
              {item.isError ? 'Error' : 'Done'}
            </span>
          </div>
          {item.content && (
            <pre className="text-xs text-gray-400 mt-2 ml-6 overflow-auto max-h-24 whitespace-pre-wrap">
              {item.content}
            </pre>
          )}
        </div>
      )}

      {item.type === 'git' && (
        <div className="p-3 flex items-center gap-2">
          <GitBranch size={14} className="text-orange-400" />
          <span className="text-sm text-orange-400">{item.content}</span>
          <span className="text-xs text-gray-500">{formatTimestamp(item.timestamp)}</span>
        </div>
      )}

      {item.type === 'status' && (
        <div className="p-3 flex items-center gap-2">
          {item.isError
            ? <AlertCircle size={14} className="text-red-400" />
            : <Settings size={14} className="text-gray-400" />
          }
          <span className={`text-sm ${item.isError ? 'text-red-400' : 'text-gray-400'}`}>
            {item.content}
          </span>
          <span className="text-xs text-gray-500">{formatTimestamp(item.timestamp)}</span>
        </div>
      )}
    </div>
  )
}

function getToolIcon(toolName: string) {
  switch (toolName) {
    case 'Write':
      return <FileText size={14} className="text-green-400" />
    case 'Edit':
      return <Edit size={14} className="text-yellow-400" />
    case 'Read':
      return <FileCode size={14} className="text-blue-400" />
    case 'Bash':
      return <Terminal size={14} className="text-orange-400" />
    default:
      return <Terminal size={14} className="text-purple-400" />
  }
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
