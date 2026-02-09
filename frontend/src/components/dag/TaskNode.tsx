import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { Check, X, Loader2, FileCode, Terminal, Edit, Search, GitBranch } from 'lucide-react'

interface TaskNodeData {
  label: string
  subtitle?: string
  count?: number
  toolName?: string
  status: 'pending' | 'running' | 'completed' | 'error'
  toolId?: string
  input?: Record<string, unknown>
  output?: string
  eventId?: string
}

interface TaskNodeProps {
  data: TaskNodeData
}

const toolIcons: Record<string, React.ReactNode> = {
  Read: <FileCode size={16} />,
  Write: <Edit size={16} />,
  Edit: <Edit size={16} />,
  Bash: <Terminal size={16} />,
  Grep: <Search size={16} />,
  Glob: <Search size={16} />,
  default: <GitBranch size={16} />,
}

function TaskNode({ data }: TaskNodeProps) {
  const { label, subtitle, count, toolName, status, input, output } = data

  const statusStyles: Record<string, string> = {
    pending: 'border-gray-600 bg-gray-800/80',
    running: 'border-claude-500 bg-claude-950/50 glow-orange',
    completed: 'border-green-600 bg-green-950/30',
    error: 'border-red-600 bg-red-950/30',
  }

  const statusIcons: Record<string, React.ReactNode> = {
    pending: null,
    running: <Loader2 size={14} className="animate-spin text-claude-400" />,
    completed: <Check size={14} className="text-green-400" />,
    error: <X size={14} className="text-red-400" />,
  }

  // Use toolName for icon, fall back to label
  const iconKey = toolName || label
  const icon = toolIcons[iconKey] || toolIcons.default

  // Extract file path from input if present
  const filePath = input?.file_path || input?.path
  const fullPath = typeof filePath === 'string' ? filePath : null

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-lg min-w-[180px] max-w-[240px]
        transition-all duration-200
        ${statusStyles[status] || statusStyles.pending}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-gray-600 border-2 border-gray-500"
      />

      <div className="flex items-center gap-2">
        <span className="text-gray-400">{icon}</span>
        <span className="font-medium text-white text-sm flex-1 truncate">{label}</span>
        {count && count > 1 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-200">
            x{count}
          </span>
        )}
        {statusIcons[status]}
      </div>

      {subtitle && (
        <p className="text-xs text-gray-400 mt-1 truncate" title={subtitle}>
          {subtitle}
        </p>
      )}

      {fullPath && (
        <p className="text-xs text-gray-500 font-mono truncate mt-1" title={fullPath}>
          {fullPath}
        </p>
      )}

      {status === 'error' && output && (
        <p className="text-xs text-red-400 mt-1 truncate" title={output}>
          {output.slice(0, 50)}...
        </p>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-gray-600 border-2 border-gray-500"
      />
    </div>
  )
}

export default memo(TaskNode)
