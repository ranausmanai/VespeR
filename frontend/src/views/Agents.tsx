import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Bot,
  Plus,
  Trash2,
  Edit,
  Play,
  ChevronRight,
  Sparkles,
  Brain,
  Shield,
  X
} from 'lucide-react'
import { getAgents, createAgent, deleteAgent, getSessions, getAgent, updateAgent } from '../api/client'
import { Agent, Session } from '../api/types'

interface AgentFormData {
  name: string
  description: string
  role: string
  personality: string
  system_prompt: string
  model: string
}

const ROLE_OPTIONS = [
  { value: 'generator', label: 'Generator', description: 'Creates content and solutions' },
  { value: 'critic', label: 'Critic', description: 'Reviews and provides feedback' },
  { value: 'expert', label: 'Expert', description: 'Domain specialist' },
  { value: 'reviewer', label: 'Reviewer', description: 'Code/content reviewer' },
  { value: 'planner', label: 'Planner', description: 'Strategy and planning' },
  { value: 'researcher', label: 'Researcher', description: 'Information gathering' },
]

const MODEL_OPTIONS = [
  { value: 'sonnet', label: 'Claude Sonnet', description: 'Balanced performance' },
  { value: 'opus', label: 'Claude Opus', description: 'Maximum capability' },
  { value: 'haiku', label: 'Claude Haiku', description: 'Fast and efficient' },
]

export default function Agents() {
  const { agentId } = useParams<{ agentId?: string }>()
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showExecuteModal, setShowExecuteModal] = useState<Agent | null>(null)
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [formData, setFormData] = useState<AgentFormData>({
    name: '',
    description: '',
    role: 'generator',
    personality: '',
    system_prompt: '',
    model: 'sonnet',
  })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    const openEditorFromRoute = async () => {
      if (!agentId) return
      try {
        const agent = await getAgent(agentId)
        setEditingAgentId(agent.id)
        setFormData({
          name: agent.name || '',
          description: agent.description || '',
          role: agent.role || 'generator',
          personality: agent.personality || '',
          system_prompt: agent.system_prompt || '',
          model: agent.model || 'sonnet',
        })
        setShowCreateModal(true)
      } catch (e) {
        console.error('Failed to load agent for editing:', e)
        navigate('/agents')
      }
    }

    openEditorFromRoute()
  }, [agentId, agents, navigate])

  async function loadData() {
    try {
      const [agentsData, sessionsData] = await Promise.all([
        getAgents(),
        getSessions()
      ])
      setAgents(agentsData.agents)
      setSessions(sessionsData.sessions)
    } catch (e) {
      console.error('Failed to load agents:', e)
    } finally {
      setLoading(false)
    }
  }

  function resetForm() {
    setFormData({
      name: '',
      description: '',
      role: 'generator',
      personality: '',
      system_prompt: '',
      model: 'sonnet',
    })
  }

  function closeAgentModal() {
    setShowCreateModal(false)
    setEditingAgentId(null)
    resetForm()
    if (agentId) {
      navigate('/agents')
    }
  }

  async function handleSaveAgent() {
    if (!formData.name.trim()) return

    setCreating(true)
    try {
      if (editingAgentId) {
        const updated = await updateAgent(editingAgentId, {
          name: formData.name,
          description: formData.description || undefined,
          role: formData.role || undefined,
          personality: formData.personality || undefined,
          system_prompt: formData.system_prompt || undefined,
          model: formData.model,
        })
        setAgents(prev => prev.map(a => a.id === editingAgentId ? { ...a, ...updated } : a))
      } else {
        const agent = await createAgent({
          name: formData.name,
          description: formData.description || undefined,
          role: formData.role || undefined,
          personality: formData.personality || undefined,
          system_prompt: formData.system_prompt || undefined,
          model: formData.model,
        })
        setAgents([agent, ...agents])
      }
      closeAgentModal()
    } catch (e) {
      console.error('Failed to save agent:', e)
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteAgent(agentId: string) {
    if (!confirm('Are you sure you want to delete this agent?')) return

    try {
      await deleteAgent(agentId)
      setAgents(agents.filter(a => a.id !== agentId))
    } catch (e) {
      console.error('Failed to delete agent:', e)
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
          <h1 className="text-2xl font-bold text-white mb-2">Agents</h1>
          <p className="text-gray-400">Create and manage reusable AI agents</p>
        </div>
        <button
          onClick={() => {
            setEditingAgentId(null)
            resetForm()
            setShowCreateModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
        >
          <Plus size={18} />
          Create Agent
        </button>
      </div>

      {/* Agents Grid */}
      {agents.length === 0 ? (
        <div className="text-center py-16 bg-gray-900 rounded-xl border border-gray-800">
          <Bot size={48} className="mx-auto mb-4 text-gray-600" />
          <h3 className="text-lg font-medium text-white mb-2">No agents yet</h3>
          <p className="text-gray-400 mb-4">Create your first agent to get started</p>
          <button
            onClick={() => {
              setEditingAgentId(null)
              resetForm()
              setShowCreateModal(true)
            }}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
          >
            Create Agent
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onDelete={() => handleDeleteAgent(agent.id)}
              onExecute={() => setShowExecuteModal(agent)}
            />
          ))}
        </div>
      )}

      {/* Create Agent Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <h2 className="text-xl font-semibold text-white">
                {editingAgentId ? 'Edit Agent' : 'Create New Agent'}
              </h2>
              <button
                onClick={closeAgentModal}
                className="text-gray-400 hover:text-white"
              >
                <X size={20} />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Code Reviewer, Solution Architect"
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description
                </label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={e => setFormData({ ...formData, description: e.target.value })}
                  placeholder="What does this agent do?"
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>

              {/* Role */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Role
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {ROLE_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => setFormData({ ...formData, role: option.value })}
                      className={`
                        p-3 rounded-lg border text-left transition-all
                        ${formData.role === option.value
                          ? 'bg-purple-900/50 border-purple-500 text-white'
                          : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                        }
                      `}
                    >
                      <div className="font-medium">{option.label}</div>
                      <div className="text-xs text-gray-400 mt-1">{option.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Model */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Model
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {MODEL_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => setFormData({ ...formData, model: option.value })}
                      className={`
                        p-3 rounded-lg border text-left transition-all
                        ${formData.model === option.value
                          ? 'bg-blue-900/50 border-blue-500 text-white'
                          : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                        }
                      `}
                    >
                      <div className="font-medium">{option.label}</div>
                      <div className="text-xs text-gray-400 mt-1">{option.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Personality */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Personality
                </label>
                <textarea
                  value={formData.personality}
                  onChange={e => setFormData({ ...formData, personality: e.target.value })}
                  placeholder="Describe the agent's personality traits..."
                  rows={2}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                />
              </div>

              {/* System Prompt */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  System Prompt
                </label>
                <textarea
                  value={formData.system_prompt}
                  onChange={e => setFormData({ ...formData, system_prompt: e.target.value })}
                  placeholder="Custom instructions for the agent..."
                  rows={4}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none font-mono text-sm"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 p-4 border-t border-gray-700">
              <button
                onClick={closeAgentModal}
                className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveAgent}
                disabled={!formData.name.trim() || creating}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {creating ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                ) : (
                  <Sparkles size={18} />
                )}
                {editingAgentId ? 'Save Changes' : 'Create Agent'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execute Agent Modal */}
      {showExecuteModal && (
        <ExecuteAgentModal
          agent={showExecuteModal}
          sessions={sessions}
          onClose={() => setShowExecuteModal(null)}
        />
      )}
    </div>
  )
}

function AgentCard({
  agent,
  onDelete,
  onExecute,
}: {
  agent: Agent
  onDelete: () => void
  onExecute: () => void
}) {
  const roleIcons: Record<string, React.ReactNode> = {
    generator: <Sparkles size={16} className="text-yellow-400" />,
    critic: <Shield size={16} className="text-red-400" />,
    expert: <Brain size={16} className="text-purple-400" />,
    reviewer: <Edit size={16} className="text-blue-400" />,
    planner: <ChevronRight size={16} className="text-green-400" />,
    researcher: <Bot size={16} className="text-cyan-400" />,
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-gray-700 transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-900/30 rounded-lg">
            <Bot size={20} className="text-purple-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-white">{agent.name}</h3>
              {Boolean(agent.constraints?.template) && (
                <span className="px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wide bg-emerald-900/40 text-emerald-300 border border-emerald-700/50">
                  Template
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 text-xs text-gray-400">
              {roleIcons[agent.role || ''] || <Bot size={12} />}
              <span className="capitalize">{agent.role || 'Agent'}</span>
              <span className="mx-1">•</span>
              <span>{agent.model}</span>
            </div>
          </div>
        </div>
      </div>

      {agent.description && (
        <p className="text-sm text-gray-400 mb-3 line-clamp-2">
          {agent.description}
        </p>
      )}

      <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-800">
        <div className="flex items-center gap-2">
          <button
            onClick={onExecute}
            className="flex items-center gap-1 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg text-sm transition-colors"
          >
            <Play size={14} />
            Run
          </button>
          <Link
            to={`/agents/${agent.id}`}
            className="flex items-center gap-1 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
          >
            <Edit size={14} />
            Edit
          </Link>
        </div>
        <button
          onClick={onDelete}
          className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  )
}

function ExecuteAgentModal({
  agent,
  sessions,
  onClose,
}: {
  agent: Agent
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
      const { executeAgent } = await import('../api/client')
      const result = await executeAgent(selectedSession, agent.id, inputText)
      onClose()
      // Navigate to agent execution view
      window.location.href = `/execution/${result.run_id}`
    } catch (e) {
      console.error('Failed to execute agent:', e)
    } finally {
      setExecuting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-lg">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-xl font-semibold text-white">Run Agent: {agent.name}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Session Select */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Session
            </label>
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

          {/* Input */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Input
            </label>
            <textarea
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              placeholder="What would you like this agent to do?"
              rows={4}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 p-4 border-t border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
          >
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
