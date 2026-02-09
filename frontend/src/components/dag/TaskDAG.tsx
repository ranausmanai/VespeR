import { useEffect, useMemo } from 'react'
import {
  ReactFlow,
  Node,
  Edge,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { AgentlingEvent } from '../../api/types'
import TaskNode from './TaskNode'

function LaneNode({ data }: { data: Record<string, unknown> }) {
  const title = String(data.title || '')
  const steps = Number(data.steps || 0)
  const actions = Number(data.actions || 0)
  const files = Number(data.files || 0)
  const errors = Number(data.errors || 0)

  return (
    <div className="w-full h-full rounded-lg border border-gray-700 bg-gray-900/90 px-3 py-2">
      <div className="text-sm font-semibold text-gray-100">{title}</div>
      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
        <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">{steps} steps</span>
        <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">{actions} actions</span>
        <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">{files} files</span>
        {errors > 0 ? (
          <span className="px-1.5 py-0.5 rounded bg-red-900/50 text-red-300">{errors} errors</span>
        ) : (
          <span className="px-1.5 py-0.5 rounded bg-green-900/40 text-green-300">0 errors</span>
        )}
      </div>
    </div>
  )
}

const nodeTypes = {
  task: TaskNode,
  lane: LaneNode,
} as const

interface TaskDAGProps {
  events: AgentlingEvent[]
}

export default function TaskDAG({ events }: TaskDAGProps) {
  const { nodes, edges } = useMemo(() => {
    return buildGraph(events)
  }, [events])

  const [displayNodes, setNodes, onNodesChange] = useNodesState(nodes)
  const [displayEdges, setEdges, onEdgesChange] = useEdgesState(edges)

  useEffect(() => {
    setNodes(nodes)
    setEdges(edges)
  }, [nodes, edges, setNodes, setEdges])

  return (
    <div className="h-full w-full bg-gray-950">
      <ReactFlow
        nodes={displayNodes}
        edges={displayEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes as any}
        fitView
        minZoom={0.1}
        maxZoom={2}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        proOptions={{ hideAttribution: true }}
      >
        <Controls className="bg-gray-800 border-gray-700" />
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
      </ReactFlow>
    </div>
  )
}

function buildGraph(events: AgentlingEvent[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []
  const toolIdToNodeId = new Map<string, string>()
  let prevTaskNodeId: string | null = null
  let nodeIndex = 0
  let lastSignature: string | null = null
  const runCompleted = events.some((e) => e.type === 'run.completed')
  const runFailed = events.some((e) => e.type === 'run.failed')
  const phaseOrder = ['Understand', 'Explore', 'Implement', 'Verify', 'Deliver'] as const
  type Phase = typeof phaseOrder[number]
  const phaseCounts = new Map<Phase, number>()
  const phaseStats = new Map<Phase, { steps: number; actions: number; files: Set<string>; errors: number }>()
  const laneWidth = 300
  const laneGap = 24
  const topPadding = 72
  const rowHeight = 110
  const toolIdToPhase = new Map<string, Phase>()

  phaseOrder.forEach((phase) => {
    phaseStats.set(phase, { steps: 0, actions: 0, files: new Set<string>(), errors: 0 })
  })

  const phaseForTool = (toolName: string, input: Record<string, unknown>): Phase => {
    if (toolName === 'Write' || toolName === 'Edit') return 'Implement'
    if (toolName === 'Read' || toolName === 'Glob' || toolName === 'Grep') return 'Explore'
    if (toolName === 'Bash') {
      const command = String(input.command || '').trim().toLowerCase()
      if (/\b(npm|pnpm|yarn)\s+test\b|\bpytest\b|\bvitest\b|\bjest\b|\bgo test\b|\blint\b|\bbuild\b/.test(command)) {
        return 'Verify'
      }
      if (/^(ls|pwd|find)\b/.test(command)) return 'Explore'
      return 'Implement'
    }
    return 'Explore'
  }

  const addTaskNode = (phase: Phase, data: Record<string, unknown>) => {
    const phaseIndex = phaseOrder.indexOf(phase)
    const laneX = phaseIndex * (laneWidth + laneGap)
    const row = phaseCounts.get(phase) || 0
    phaseCounts.set(phase, row + 1)
    const id = `n-${nodeIndex++}`
    const node: Node = {
      id,
      type: 'task',
      position: { x: laneX + 12, y: topPadding + row * rowHeight },
      data: { ...data, phase },
    }
    nodes.push(node)
    const stats = phaseStats.get(phase)
    if (stats) stats.steps += 1
    if (prevTaskNodeId) {
      edges.push({
        id: `edge-${prevTaskNodeId}-${id}`,
        source: prevTaskNodeId,
        target: id,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#6b7280' },
      })
    }
    prevTaskNodeId = id
    return node
  }

  phaseOrder.forEach((phase, idx) => {
    const x = idx * (laneWidth + laneGap)
    nodes.push({
      id: `lane-${phase}`,
      type: 'default',
      position: { x, y: 8 },
      draggable: false,
      selectable: false,
      data: { label: phase },
      style: {
        width: laneWidth,
        height: 44,
        borderRadius: 10,
        border: '1px solid #374151',
        background: '#111827',
        color: '#e5e7eb',
        fontSize: 13,
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        pointerEvents: 'none',
      },
    })
  })

  if (events.length > 0) {
    addTaskNode('Understand', {
      label: 'Run Started',
      subtitle: 'Claude began processing your request',
      toolName: 'default',
      status: 'completed',
    })
  }

  for (const event of events) {
    if (event.type !== 'stream.tool_use') continue

    const toolName = String(event.tool_name || event.payload?.name || 'Unknown Tool')
    const input = (event.tool_input || event.payload?.input || {}) as Record<string, unknown>
    const filePath = String(input.file_path || input.path || '')
    const fileName = filePath ? filePath.split('/').pop() || filePath : ''
    const command = String(input.command || '').trim()

    let label = toolName
    let subtitle = ''
    let signature = toolName
    let phase: Phase = phaseForTool(toolName, input)
    const stats = phaseStats.get(phase)
    if (stats) {
      stats.actions += 1
      if (toolName === 'Read' || toolName === 'Write' || toolName === 'Edit') {
        if (filePath) stats.files.add(filePath)
      }
    }

    if (toolName === 'Read') {
      label = fileName ? `Read ${fileName}` : 'Read file'
      subtitle = filePath || 'Inspecting code context'
      signature = `Read:${filePath || fileName}`
    } else if (toolName === 'Write') {
      label = fileName ? `Create ${fileName}` : 'Create file'
      subtitle = filePath || 'Writing new artifact'
      signature = `Write:${filePath || fileName}`
    } else if (toolName === 'Edit') {
      label = fileName ? `Edit ${fileName}` : 'Edit file'
      subtitle = filePath || 'Updating existing artifact'
      signature = `Edit:${filePath || fileName}`
    } else if (toolName === 'Glob') {
      label = 'Find files'
      subtitle = 'Scanning project structure'
      signature = 'Glob'
    } else if (toolName === 'Grep') {
      label = 'Search code'
      subtitle = 'Finding matching patterns'
      signature = 'Grep'
    } else if (toolName === 'Bash') {
      const short = command.slice(0, 60)
      if (/\b(npm|pnpm|yarn)\s+test\b|\bpytest\b|\bvitest\b|\bjest\b|\bgo test\b/.test(command)) {
        label = 'Run tests'
      } else if (/^(ls|pwd|find)\b/.test(command)) {
        label = 'Inspect workspace'
      } else {
        label = `Run ${short}${command.length > 60 ? '...' : ''}`
      }
      subtitle = command || 'Executing shell command'
      signature = `Bash:${command}`
    }

    const lastNode = nodes[nodes.length - 1]
    if (
      lastNode &&
      lastNode.type === 'task' &&
      lastNode.data &&
      lastNode.data.signature === signature &&
      lastSignature === signature
    ) {
      lastNode.data.count = Number(lastNode.data.count || 1) + 1
      const toolIds: string[] = Array.isArray(lastNode.data.toolIds)
        ? (lastNode.data.toolIds as string[])
        : []
      if (event.tool_id) {
        toolIds.push(event.tool_id)
        toolIdToNodeId.set(event.tool_id, lastNode.id)
        toolIdToPhase.set(event.tool_id, phase)
      }
      lastNode.data.toolIds = toolIds
      lastNode.data.input = input
      continue
    }

    const node = addTaskNode(phase, {
      label,
      subtitle,
      toolName,
      status: 'pending',
      toolId: event.tool_id,
      toolIds: event.tool_id ? [event.tool_id] : [],
      input,
      eventId: event.id,
      signature,
      count: 1,
    })

    if (event.tool_id) {
      toolIdToNodeId.set(event.tool_id, node.id)
      toolIdToPhase.set(event.tool_id, phase)
    }
    lastSignature = signature
  }

  for (const event of events) {
    if (event.type !== 'stream.tool_result') continue
    const toolId = String(event.tool_id || event.payload?.tool_use_id || '')
    if (!toolId) continue
    const nodeId = toolIdToNodeId.get(toolId)
    if (!nodeId) continue
    const node = nodes.find((n) => n.id === nodeId)
    if (!node) continue
    node.data.status = event.is_error ? 'error' : 'completed'
    node.data.output = event.tool_output || event.payload?.output
    if (event.is_error) {
      const phase = toolIdToPhase.get(toolId)
      if (phase) {
        const stats = phaseStats.get(phase)
        if (stats) stats.errors += 1
      }
    }
  }

  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].data.status !== 'pending') continue
    const isLast = i === nodes.length - 1
    nodes[i].data.status = isLast && !runCompleted && !runFailed ? 'running' : 'completed'
  }

  if (runCompleted) {
    addTaskNode('Deliver', {
      label: 'Response Delivered',
      subtitle: 'Claude finished this run',
      toolName: 'default',
      status: 'completed',
    })
  } else if (runFailed) {
    addTaskNode('Deliver', {
      label: 'Run Failed',
      subtitle: 'Execution stopped with an error',
      toolName: 'default',
      status: 'error',
    })
    const deliverStats = phaseStats.get('Deliver')
    if (deliverStats) deliverStats.errors += 1
  }

  phaseOrder.forEach((phase, idx) => {
    const x = idx * (laneWidth + laneGap)
    const stats = phaseStats.get(phase)!
    nodes.push({
      id: `lane-${phase}`,
      type: 'lane',
      position: { x, y: 8 },
      draggable: false,
      selectable: false,
      data: {
        title: phase,
        steps: stats.steps,
        actions: stats.actions,
        files: stats.files.size,
        errors: stats.errors,
      },
      style: {
        width: laneWidth,
        height: 56,
        pointerEvents: 'none',
      },
    })
  })

  return { nodes, edges }
}
