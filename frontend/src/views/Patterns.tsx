import { useEffect, useState } from 'react'
import {
  Workflow,
  Plus,
  Trash2,
  Play,
  X,
  ArrowRight,
  RefreshCw,
  Users,
  MessageSquare,
  User
} from 'lucide-react'
import { getPatterns, createPattern, deletePattern, getAgents, getSessions } from '../api/client'
import { AgentPattern, Agent, Session } from '../api/types'

const PATTERN_TYPES = [
  {
    value: 'solo',
    label: 'Solo',
    icon: <User size={20} />,
    description: 'Single agent executes the task',
    color: 'blue'
  },
  {
    value: 'loop',
    label: 'Generator + Critic Loop',
    icon: <RefreshCw size={20} />,
    description: 'Generator creates, critic reviews, iterate until approved',
    color: 'purple'
  },
  {
    value: 'panel',
    label: 'Expert Panel',
    icon: <Users size={20} />,
    description: 'Multiple experts contribute perspectives, synthesizer combines',
    color: 'green'
  },
  {
    value: 'debate',
    label: 'Debate',
    icon: <MessageSquare size={20} />,
    description: 'Agents argue different positions, judge decides',
    color: 'orange'
  },
]

const INVOLVEMENT_OPTIONS = [
  { value: 'autonomous', label: 'Autonomous', description: 'Runs without interruption' },
  { value: 'checkpoints', label: 'Checkpoints', description: 'Pauses for approval at key points' },
  { value: 'on_demand', label: 'On Demand', description: 'Human can intervene anytime' },
]

export default function Patterns() {
  const [patterns, setPatterns] = useState<AgentPattern[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showExecuteModal, setShowExecuteModal] = useState<AgentPattern | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [patternsData, agentsData, sessionsData] = await Promise.all([
        getPatterns(),
        getAgents(),
        getSessions()
      ])
      setPatterns(patternsData.patterns)
      setAgents(agentsData.agents)
      setSessions(sessionsData.sessions)
    } catch (e) {
      console.error('Failed to load data:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleDeletePattern(patternId: string) {
    if (!confirm('Are you sure you want to delete this pattern?')) return

    try {
      await deletePattern(patternId)
      setPatterns(patterns.filter(p => p.id !== patternId))
    } catch (e) {
      console.error('Failed to delete pattern:', e)
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
    <div className="h-full overflow-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Agent Patterns</h1>
          <p className="text-gray-400">Create multi-agent workflows</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          <Plus size={18} />
          Create Pattern
        </button>
      </div>

      {/* Pattern Types Overview */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {PATTERN_TYPES.map(type => (
          <div
            key={type.value}
            className={`p-4 rounded-xl border bg-${type.color}-900/20 border-${type.color}-800/50`}
          >
            <div className={`text-${type.color}-400 mb-2`}>{type.icon}</div>
            <h3 className="font-medium text-white">{type.label}</h3>
            <p className="text-xs text-gray-400 mt-1">{type.description}</p>
          </div>
        ))}
      </div>

      {/* Patterns List */}
      {patterns.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <Workflow size={48} className="mx-auto mb-4 text-gray-600" />
          <h3 className="text-lg font-medium text-white mb-2">No patterns yet</h3>
          <p className="text-gray-400 mb-4">Create your first agent pattern</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
          >
            Create Pattern
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {patterns.map(pattern => (
            <PatternCard
              key={pattern.id}
              pattern={pattern}
              agents={agents}
              onDelete={() => handleDeletePattern(pattern.id)}
              onExecute={() => setShowExecuteModal(pattern)}
            />
          ))}
        </div>
      )}

      {/* Create Pattern Modal */}
      {showCreateModal && (
        <CreatePatternModal
          agents={agents}
          onClose={() => setShowCreateModal(false)}
          onCreate={async (pattern) => {
            setPatterns([pattern, ...patterns])
            setShowCreateModal(false)
          }}
        />
      )}

      {/* Execute Pattern Modal */}
      {showExecuteModal && (
        <ExecutePatternModal
          pattern={showExecuteModal}
          sessions={sessions}
          onClose={() => setShowExecuteModal(null)}
        />
      )}
    </div>
  )
}

function PatternCard({
  pattern,
  agents,
  onDelete,
  onExecute,
}: {
  pattern: AgentPattern
  agents: Agent[]
  onDelete: () => void
  onExecute: () => void
}) {
  const typeInfo = PATTERN_TYPES.find(t => t.value === pattern.pattern_type)
  const config = pattern.config || {}

  // Get agent names from config
  const agentIds = (config.agents as string[] | undefined) ||
    [config.agent_id, config.generator_id, config.critic_id]
      .filter(Boolean) as string[]

  const patternAgents = agentIds
    .map(id => agents.find(a => a.id === id))
    .filter(Boolean) as Agent[]

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-gray-700 transition-all">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-${typeInfo?.color || 'gray'}-900/30`}>
            {typeInfo?.icon || <Workflow size={20} />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-white">{pattern.name}</h3>
              {Boolean(config.template) && (
                <span className="px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wide bg-emerald-900/40 text-emerald-300 border border-emerald-700/50">
                  Template
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400">
              {typeInfo?.label} • {pattern.human_involvement}
              {pattern.pattern_type === 'loop' && ` • Max ${pattern.max_iterations} iterations`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onExecute}
            className="flex items-center gap-1 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg text-sm transition-colors"
          >
            <Play size={14} />
            Run
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {pattern.description && (
        <p className="text-sm text-gray-400 mt-3">{pattern.description}</p>
      )}

      {/* Agent Flow */}
      {patternAgents.length > 0 && (
        <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-800">
          {patternAgents.map((agent, i) => (
            <div key={agent.id} className="flex items-center gap-2">
              {i > 0 && <ArrowRight size={16} className="text-gray-600" />}
              <div className="px-3 py-1 bg-gray-800 rounded-full text-sm text-gray-300">
                {agent.name}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function CreatePatternModal({
  agents,
  onClose,
  onCreate,
}: {
  agents: Agent[]
  onClose: () => void
  onCreate: (pattern: AgentPattern) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [patternType, setPatternType] = useState('solo')
  const [humanInvolvement, setHumanInvolvement] = useState('checkpoints')
  const [maxIterations, setMaxIterations] = useState(3)
  const [selectedAgents, setSelectedAgents] = useState<Record<string, string>>({})
  const [creating, setCreating] = useState(false)

  async function handleCreate() {
    if (!name.trim()) return

    setCreating(true)
    try {
      // Build config based on pattern type
      let config: Record<string, unknown> = {}

      if (patternType === 'solo') {
        config = { agent_id: selectedAgents.solo }
      } else if (patternType === 'loop') {
        config = {
          generator_id: selectedAgents.generator,
          critic_id: selectedAgents.critic
        }
      } else if (patternType === 'panel') {
        config = {
          agents: [selectedAgents.expert1, selectedAgents.expert2, selectedAgents.expert3].filter(Boolean),
          synthesizer_id: selectedAgents.synthesizer
        }
      } else if (patternType === 'debate') {
        config = {
          debaters: [selectedAgents.debater1, selectedAgents.debater2].filter(Boolean),
          judge_id: selectedAgents.judge
        }
      }

      const pattern = await createPattern({
        name,
        description: description || undefined,
        pattern_type: patternType,
        config,
        human_involvement: humanInvolvement,
        max_iterations: maxIterations
      })

      onCreate(pattern)
    } catch (e) {
      console.error('Failed to create pattern:', e)
    } finally {
      setCreating(false)
    }
  }

  const renderAgentSelectors = () => {
    if (patternType === 'solo') {
      return (
        <AgentSelect
          label="Agent"
          value={selectedAgents.solo}
          onChange={v => setSelectedAgents({ ...selectedAgents, solo: v })}
          agents={agents}
        />
      )
    }

    if (patternType === 'loop') {
      return (
        <>
          <AgentSelect
            label="Generator"
            value={selectedAgents.generator}
            onChange={v => setSelectedAgents({ ...selectedAgents, generator: v })}
            agents={agents}
            hint="Creates content/solutions"
          />
          <AgentSelect
            label="Critic"
            value={selectedAgents.critic}
            onChange={v => setSelectedAgents({ ...selectedAgents, critic: v })}
            agents={agents}
            hint="Reviews and provides feedback"
          />
        </>
      )
    }

    if (patternType === 'panel') {
      return (
        <>
          <AgentSelect
            label="Expert 1"
            value={selectedAgents.expert1}
            onChange={v => setSelectedAgents({ ...selectedAgents, expert1: v })}
            agents={agents}
          />
          <AgentSelect
            label="Expert 2"
            value={selectedAgents.expert2}
            onChange={v => setSelectedAgents({ ...selectedAgents, expert2: v })}
            agents={agents}
          />
          <AgentSelect
            label="Expert 3 (optional)"
            value={selectedAgents.expert3}
            onChange={v => setSelectedAgents({ ...selectedAgents, expert3: v })}
            agents={agents}
            optional
          />
          <AgentSelect
            label="Synthesizer"
            value={selectedAgents.synthesizer}
            onChange={v => setSelectedAgents({ ...selectedAgents, synthesizer: v })}
            agents={agents}
            hint="Combines perspectives"
          />
        </>
      )
    }

    if (patternType === 'debate') {
      return (
        <>
          <AgentSelect
            label="Debater 1"
            value={selectedAgents.debater1}
            onChange={v => setSelectedAgents({ ...selectedAgents, debater1: v })}
            agents={agents}
          />
          <AgentSelect
            label="Debater 2"
            value={selectedAgents.debater2}
            onChange={v => setSelectedAgents({ ...selectedAgents, debater2: v })}
            agents={agents}
          />
          <AgentSelect
            label="Judge"
            value={selectedAgents.judge}
            onChange={v => setSelectedAgents({ ...selectedAgents, judge: v })}
            agents={agents}
            hint="Renders final verdict"
          />
        </>
      )
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-auto">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-xl font-semibold text-white">Create Pattern</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Name *</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g., Code Review Loop, Architecture Panel"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
            <input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What does this pattern do?"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            />
          </div>

          {/* Pattern Type */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Pattern Type</label>
            <div className="grid grid-cols-2 gap-2">
              {PATTERN_TYPES.map(type => (
                <button
                  key={type.value}
                  onClick={() => {
                    setPatternType(type.value)
                    setSelectedAgents({})
                  }}
                  className={`
                    p-3 rounded-lg border text-left transition-all flex items-center gap-3
                    ${patternType === type.value
                      ? 'bg-purple-900/50 border-purple-500 text-white'
                      : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                    }
                  `}
                >
                  <div className={patternType === type.value ? 'text-purple-400' : 'text-gray-500'}>
                    {type.icon}
                  </div>
                  <div>
                    <div className="font-medium">{type.label}</div>
                    <div className="text-xs text-gray-400">{type.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Agent Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Agents</label>
            <div className="space-y-3">
              {renderAgentSelectors()}
            </div>
          </div>

          {/* Human Involvement */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Human Involvement</label>
            <div className="grid grid-cols-3 gap-2">
              {INVOLVEMENT_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setHumanInvolvement(opt.value)}
                  className={`
                    p-3 rounded-lg border text-left transition-all
                    ${humanInvolvement === opt.value
                      ? 'bg-blue-900/50 border-blue-500 text-white'
                      : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                    }
                  `}
                >
                  <div className="font-medium">{opt.label}</div>
                  <div className="text-xs text-gray-400">{opt.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Max Iterations (for loop) */}
          {patternType === 'loop' && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Max Iterations
              </label>
              <input
                type="number"
                min={1}
                max={10}
                value={maxIterations}
                onChange={e => setMaxIterations(parseInt(e.target.value) || 3)}
                className="w-24 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
              />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 p-4 border-t border-gray-700">
          <button onClick={onClose} className="px-4 py-2 text-gray-300 hover:text-white transition-colors">
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || creating}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {creating ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <Workflow size={18} />
            )}
            Create Pattern
          </button>
        </div>
      </div>
    </div>
  )
}

function AgentSelect({
  label,
  value,
  onChange,
  agents,
  hint,
  optional
}: {
  label: string
  value?: string
  onChange: (value: string) => void
  agents: Agent[]
  hint?: string
  optional?: boolean
}) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-1">
        {label} {optional && <span className="text-gray-600">(optional)</span>}
      </label>
      <select
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
      >
        <option value="">Select an agent...</option>
        {agents.map(agent => (
          <option key={agent.id} value={agent.id}>
            {agent.name} ({agent.role || 'agent'})
          </option>
        ))}
      </select>
      {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  )
}

function ExecutePatternModal({
  pattern,
  sessions,
  onClose,
}: {
  pattern: AgentPattern
  sessions: Session[]
  onClose: () => void
}) {
  const [selectedSession, setSelectedSession] = useState<string>(sessions[0]?.id || '')
  const [inputText, setInputText] = useState('')
  const [executing, setExecuting] = useState(false)

  async function handleExecute() {
    if (!selectedSession || !inputText.trim()) return

    setExecuting(true)
    try {
      const { executePattern } = await import('../api/client')
      const result = await executePattern(pattern.id, selectedSession, inputText)
      onClose()
      window.location.href = `/execution/${result.run_id}`
    } catch (e) {
      console.error('Failed to execute pattern:', e)
    } finally {
      setExecuting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-lg">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-xl font-semibold text-white">Run Pattern: {pattern.name}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Session</label>
            <select
              value={selectedSession}
              onChange={e => setSelectedSession(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
            >
              {sessions.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name || s.working_dir}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Input</label>
            <textarea
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              placeholder="What would you like the agents to work on?"
              rows={4}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 p-4 border-t border-gray-700">
          <button onClick={onClose} className="px-4 py-2 text-gray-300 hover:text-white transition-colors">
            Cancel
          </button>
          <button
            onClick={handleExecute}
            disabled={!selectedSession || !inputText.trim() || executing}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {executing ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
            ) : (
              <Play size={18} />
            )}
            Execute
          </button>
        </div>
      </div>
    </div>
  )
}
