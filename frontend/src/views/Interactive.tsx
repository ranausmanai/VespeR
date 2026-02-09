import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { MessageCircle, Plus } from 'lucide-react';
import { ChatInterface } from '../components/chat/ChatInterface';

interface ActiveSession {
  id: string;
  session_id: string;
  project_name?: string;
  title?: string;
  is_running: boolean;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  created_at?: string;
}

interface SessionSnapshot {
  id: string;
  run_id: string;
  session_id: string;
  goal?: string;
  summary?: Record<string, unknown>;
  resume_prompt: string;
  created_at?: string;
}

interface Session {
  id: string;
  name: string;
  working_dir: string;
}

interface Agent {
  id: string;
  name: string;
  description?: string;
  role?: string;
  model?: string;
}

export const Interactive: React.FC = () => {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const requestedRunId = searchParams.get('runId');
  const forceNewSession = searchParams.get('new') === '1';
  const preselectedSessionId = searchParams.get('sessionId');
  const disableSnapshot = searchParams.get('snapshot') === '0';
  const snapshotRunId = searchParams.get('snapshotRunId');

  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<string>(sessionId || preselectedSessionId || '');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [model, setModel] = useState('sonnet');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showStartAnother, setShowStartAnother] = useState(false);
  const [showStartPicker, setShowStartPicker] = useState(forceNewSession);
  const [pendingRequestedRunId, setPendingRequestedRunId] = useState<string | null>(requestedRunId);
  const [latestSnapshot, setLatestSnapshot] = useState<SessionSnapshot | null>(null);
  const [useSnapshotOnStart, setUseSnapshotOnStart] = useState(!disableSnapshot);

  useEffect(() => {
    setPendingRequestedRunId(requestedRunId);
  }, [requestedRunId]);

  useEffect(() => {
    setShowStartPicker(forceNewSession);
  }, [forceNewSession]);

  useEffect(() => {
    if (preselectedSessionId) {
      setSelectedSession(preselectedSessionId);
    }
  }, [preselectedSessionId]);

  // Fetch available sessions
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/sessions');
        const data = await response.json();
        setSessions(data.sessions || []);

        // If we have a sessionId from URL, use it
        if (sessionId && !selectedSession) {
          setSelectedSession(sessionId);
        }
      } catch (error) {
        console.error('Error fetching sessions:', error);
      }
    };

    fetchSessions();
  }, [sessionId]);

  // Check for active interactive sessions
  useEffect(() => {
    const checkActive = async () => {
      try {
        const response = await fetch('/api/interactive');
        const data = await response.json();
        if (data.sessions && data.sessions.length > 0) {
          const sessionsList = data.sessions as ActiveSession[];
          setActiveSessions(sessionsList);
          const requested = pendingRequestedRunId
            ? sessionsList.find((s: ActiveSession) => s.id === pendingRequestedRunId)
            : null;

          if (requested) {
            setActiveRunId(requested.id);
            setIsConnected(requested.is_running);
            setPendingRequestedRunId(null);
            setShowStartPicker(false);
          } else if (showStartPicker && !pendingRequestedRunId) {
            setActiveRunId(null);
            setIsConnected(false);
          } else if (!activeRunId) {
            const active = sessionsList[0];
            setActiveRunId(active.id);
            setIsConnected(active.is_running);
          } else {
            const current = sessionsList.find((s: ActiveSession) => s.id === activeRunId);
            if (current) {
              setIsConnected(current.is_running);
            } else {
              const fallback = sessionsList[0];
              setActiveRunId(fallback.id);
              setIsConnected(fallback.is_running);
            }
          }
        } else {
          setActiveSessions([]);
          setActiveRunId(null);
          setIsConnected(false);
        }
      } catch (error) {
        console.error('Error checking active sessions:', error);
      }
    };

    checkActive();
    const interval = setInterval(checkActive, 5000);
    return () => clearInterval(interval);
  }, [activeRunId, pendingRequestedRunId, showStartPicker]);

  // Load agents for in-chat invocation
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const response = await fetch('/api/agents');
        if (!response.ok) return;
        const data = await response.json();
        setAgents(data.agents || []);
      } catch (error) {
        console.error('Error fetching agents:', error);
      }
    };

    fetchAgents();
  }, []);

  useEffect(() => {
    const fetchLatestSnapshot = async () => {
      if (!selectedSession) {
        setLatestSnapshot(null);
        return;
      }
      try {
        if (snapshotRunId) {
          const specific = await fetch(`/api/interactive/${snapshotRunId}/snapshot`);
          if (specific.ok) {
            const data = await specific.json();
            setLatestSnapshot(data || null);
            return;
          }
        }

        const response = await fetch(`/api/interactive/session/${selectedSession}/latest-snapshot`);
        if (!response.ok) {
          setLatestSnapshot(null);
          return;
        }
        const data = await response.json();
        setLatestSnapshot(data.snapshot || null);
      } catch (error) {
        console.error('Error fetching latest snapshot:', error);
        setLatestSnapshot(null);
      }
    };

    fetchLatestSnapshot();
  }, [selectedSession, snapshotRunId]);

  const handleStartSession = async () => {
    if (!selectedSession) return;

    setIsStarting(true);
    try {
      const response = await fetch('/api/interactive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: selectedSession,
          model: model,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start session');
      }

      const data = await response.json();
      setActiveRunId(data.id);
      setIsConnected(data.is_running);
      setShowStartAnother(false);
      setShowStartPicker(false);
      setPendingRequestedRunId(null);
      if (useSnapshotOnStart && latestSnapshot?.resume_prompt) {
        await fetch(`/api/interactive/${data.id}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: latestSnapshot.resume_prompt }),
        });
      }
      navigate(`/interactive?runId=${encodeURIComponent(data.id)}`, { replace: true });
    } catch (error) {
      console.error('Error starting session:', error);
      alert(`Failed to start session: ${error}`);
    } finally {
      setIsStarting(false);
    }
  };

  const handleSendMessage = async (message: string) => {
    if (!activeRunId) return;

    try {
      await fetch(`/api/interactive/${activeRunId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
    } catch (error) {
      console.error('Error sending message:', error);
    }
  };

  const handleEndSession = async () => {
    if (!activeRunId) return;

    try {
      await fetch(`/api/interactive/${activeRunId}/end`, {
        method: 'POST',
      });
      const endingRunId = activeRunId;
      const remaining = activeSessions.filter((s) => s.id !== endingRunId);
      setActiveSessions(remaining);
      if (remaining.length > 0) {
        setActiveRunId(remaining[0].id);
        setIsConnected(remaining[0].is_running);
        navigate(`/interactive?runId=${encodeURIComponent(remaining[0].id)}`, { replace: true });
      } else {
        setActiveRunId(null);
        setIsConnected(false);
        navigate('/interactive', { replace: true });
      }
    } catch (error) {
      console.error('Error ending session:', error);
    }
  };

  const handleStopResponse = async () => {
    if (!activeRunId) return;
    try {
      await fetch(`/api/interactive/${activeRunId}/stop`, {
        method: 'POST',
      });
    } catch (error) {
      console.error('Error stopping response:', error);
    }
  };

  const handleInvokeAgent = async (
    agentId: string,
    instruction: string,
    injectToSession = false
  ) => {
    if (!activeRunId) {
      throw new Error('No active run');
    }

    const response = await fetch(`/api/interactive/${activeRunId}/agent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: agentId,
        instruction,
        inject_to_session: injectToSession,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to invoke agent' }));
      throw new Error(error.detail || 'Failed to invoke agent');
    }

    return response.json();
  };

  // Rejoin an active session
  const handleRejoinSession = (runId: string) => {
    const session = activeSessions.find(s => s.id === runId);
    if (session) {
      setActiveRunId(runId);
      setIsConnected(session.is_running);
      setPendingRequestedRunId(null);
      setShowStartPicker(false);
      navigate(`/interactive?runId=${encodeURIComponent(runId)}`, { replace: true });
    }
  };

  const currentActiveSession = activeSessions.find((s) => s.id === activeRunId);

  // If we have an active session, show the chat with sidebar
  if (activeRunId && !showStartPicker) {
    return (
      <div className="h-full">
        <div className="px-4 py-2 border-b border-gray-800 bg-gray-900/80 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xs text-gray-400 whitespace-nowrap">Active Session</span>
            <select
              value={activeRunId}
              onChange={(e) => handleRejoinSession(e.target.value)}
              className="bg-gray-800 text-white rounded px-2 py-1 text-sm border border-gray-700 min-w-[320px] max-w-[560px]"
            >
              {activeSessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.title || session.project_name || session.id}
                </option>
              ))}
            </select>
            {currentActiveSession?.model && (
              <span className="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded border border-gray-700">
                {currentActiveSession.model}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowStartAnother(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded transition-colors"
          >
            <Plus size={14} />
            Start Another Session
          </button>
        </div>
        <ChatInterface
          runId={activeRunId}
          isConnected={isConnected}
          onSendMessage={handleSendMessage}
          onStopResponse={handleStopResponse}
          onEndSession={handleEndSession}
          agents={agents}
          onInvokeAgent={handleInvokeAgent}
        />
        {showStartAnother && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full shadow-xl border border-gray-700">
              <h2 className="text-lg font-semibold text-white mb-4">Start Another Interactive Session</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-gray-300 text-sm font-medium mb-2">Select Project</label>
                  <select
                    value={selectedSession}
                    onChange={(e) => setSelectedSession(e.target.value)}
                    className="w-full bg-gray-700 text-white rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Choose a session...</option>
                    {sessions.map((session) => (
                      <option key={session.id} value={session.id}>
                        {session.name} - {session.working_dir}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 text-sm font-medium mb-2">Model</label>
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full bg-gray-700 text-white rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="sonnet">Claude Sonnet</option>
                    <option value="opus">Claude Opus</option>
                    <option value="haiku">Claude Haiku</option>
                  </select>
                </div>
                {latestSnapshot && (
                  <div className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
                    <label className="flex items-start gap-2 text-sm text-gray-200 min-w-0">
                      <input
                        type="checkbox"
                        checked={useSnapshotOnStart}
                        onChange={(e) => setUseSnapshotOnStart(e.target.checked)}
                        className="mt-0.5"
                      />
                      <span className="min-w-0 flex-1">
                        Start with latest session snapshot context
                        {snapshotRunId ? (
                          <span className="block text-xs text-blue-300 mt-1 break-all">
                            Source run: {snapshotRunId}
                          </span>
                        ) : null}
                        {latestSnapshot.goal ? (
                          <span className="block text-xs text-gray-400 mt-1 whitespace-pre-wrap break-words max-h-24 overflow-y-auto pr-1">
                            Goal: {latestSnapshot.goal}
                          </span>
                        ) : null}
                      </span>
                    </label>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2 mt-6">
                <button
                  type="button"
                  onClick={() => setShowStartAnother(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleStartSession}
                  disabled={!selectedSession || isStarting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded"
                >
                  {isStarting ? 'Starting...' : 'Start Session'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Otherwise show the session selector
  return (
    <div className="h-full bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-lg p-8 max-w-md w-full shadow-xl">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">
          Interactive Session
        </h1>

        <div className="space-y-6">
          {/* Active sessions to rejoin */}
          {activeSessions.length > 0 && (
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-2">
                <MessageCircle size={16} className="inline mr-2 text-green-400" />
                Active Sessions
              </label>
              <div className="space-y-2">
                {activeSessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleRejoinSession(session.id)}
                    className="w-full text-left bg-gray-700 hover:bg-gray-600 text-white rounded-lg px-4 py-3 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${session.is_running ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                        <span className="font-medium truncate max-w-[200px]">
                          {session.title || session.project_name || 'Untitled Session'}
                        </span>
                      </span>
                      <span className="text-sm text-green-400">Rejoin</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-400 ml-4">
                      {session.project_name && (
                        <span>{session.project_name}</span>
                      )}
                      {session.model && (
                        <span className="bg-gray-600 px-1.5 py-0.5 rounded">{session.model}</span>
                      )}
                      {(session.tokens_in || session.tokens_out) ? (
                        <span>{((session.tokens_in || 0) + (session.tokens_out || 0)).toLocaleString()} tokens</span>
                      ) : null}
                    </div>
                  </button>
                ))}
              </div>
              <div className="border-t border-gray-700 mt-4 pt-4">
                <p className="text-gray-400 text-sm text-center">Or start a new session</p>
              </div>
            </div>
          )}

          {/* Session selector */}
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">
              Select Project
            </label>
            <select
              value={selectedSession}
              onChange={(e) => setSelectedSession(e.target.value)}
              className="w-full bg-gray-700 text-white rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Choose a session...</option>
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.name} - {session.working_dir}
                </option>
              ))}
            </select>
          </div>

          {/* Model selector */}
          <div>
            <label className="block text-gray-300 text-sm font-medium mb-2">
              Model
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-gray-700 text-white rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="sonnet">Claude Sonnet</option>
              <option value="opus">Claude Opus</option>
              <option value="haiku">Claude Haiku</option>
            </select>
          </div>

          {latestSnapshot && (
            <div className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
              <label className="flex items-start gap-2 text-sm text-gray-200 min-w-0">
                <input
                  type="checkbox"
                  checked={useSnapshotOnStart}
                  onChange={(e) => setUseSnapshotOnStart(e.target.checked)}
                  className="mt-0.5"
                />
                <span className="min-w-0 flex-1">
                  Start with latest session snapshot context
                  {snapshotRunId ? (
                    <span className="block text-xs text-blue-300 mt-1 break-all">
                      Source run: {snapshotRunId}
                    </span>
                  ) : null}
                  {latestSnapshot.goal ? (
                    <span className="block text-xs text-gray-400 mt-1 whitespace-pre-wrap break-words max-h-24 overflow-y-auto pr-1">
                      Goal: {latestSnapshot.goal}
                    </span>
                  ) : null}
                </span>
              </label>
            </div>
          )}

          {/* Start button */}
          <button
            onClick={handleStartSession}
            disabled={!selectedSession || isStarting}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
          >
            {isStarting ? 'Starting...' : 'Start Session'}
          </button>

          {/* Or create new session */}
          <div className="text-center">
            <p className="text-gray-400 text-sm mb-2">Or create a new project session first</p>
            <button
              onClick={() => navigate('/sessions')}
              className="text-blue-400 hover:text-blue-300 text-sm"
            >
              Go to Sessions
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
