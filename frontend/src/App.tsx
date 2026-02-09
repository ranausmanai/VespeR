import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './views/Dashboard'
import LiveSession from './views/LiveSession'
import Replay from './views/Replay'
import Sessions from './views/Sessions'
import { Interactive } from './views/Interactive'
import Agents from './views/Agents'
import Patterns from './views/Patterns'
import AgentExecution from './views/AgentExecution'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="sessions" element={<Sessions />} />
        <Route path="runs/:runId" element={<LiveSession />} />
        <Route path="replay/:runId" element={<Replay />} />
        <Route path="agents" element={<Agents />} />
        <Route path="agents/:agentId" element={<Agents />} />
        <Route path="patterns" element={<Patterns />} />
        <Route path="execution/:runId" element={<AgentExecution />} />
        <Route path="interactive" element={<Interactive />} />
        <Route path="interactive/:sessionId" element={<Interactive />} />
      </Route>
    </Routes>
  )
}

export default App
