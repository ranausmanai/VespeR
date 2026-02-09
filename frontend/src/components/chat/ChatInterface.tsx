import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { User, Bot, FileText, Terminal, Edit, FileCode, Check, Zap, Send, Square } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'tool_result' | 'agent';
  content: string;
  timestamp: string;
  toolName?: string;
  toolDescription?: string;
  filePath?: string;
  command?: string;
  fileContent?: string;
  output?: string;
  isError?: boolean;
  agentName?: string;
  agentModel?: string;
  contextSummary?: {
    recentTurns?: number;
    touchedFiles?: string[];
    resolvedTarget?: string | null;
  };
}

interface SessionInfo {
  title?: string;
  tokens_in?: number;
  tokens_out?: number;
  model?: string;
  is_responding?: boolean;
}

interface ChatInterfaceProps {
  runId: string;
  isConnected: boolean;
  onSendMessage: (message: string) => void;
  onStopResponse: () => Promise<void>;
  onEndSession: () => void;
  agents: {
    id: string;
    name: string;
    description?: string;
    role?: string;
    model?: string;
  }[];
  onInvokeAgent: (
    agentId: string,
    instruction: string,
    injectToSession?: boolean
  ) => Promise<{
    output: string;
    agent_name: string;
    model?: string;
    injected?: boolean;
    context?: {
      recent_turns_count?: number;
      touched_files?: string[];
      resolved_target?: string | null;
    };
  }>;
}

function getToolDescription(toolName: string, input: Record<string, unknown> | undefined): { description: string; filePath?: string; command?: string } {
  if (!input) return { description: `Using ${toolName}` };

  const filePath = (input.file_path || input.path) as string | undefined;
  const fileName = filePath ? filePath.split('/').pop() : '';
  const command = input.command as string | undefined;

  switch (toolName) {
    case 'Write':
      return { description: fileName ? `Creating ${fileName}` : 'Creating file', filePath };
    case 'Edit':
      return { description: fileName ? `Editing ${fileName}` : 'Editing file', filePath };
    case 'Read':
      return { description: fileName ? `Reading ${fileName}` : 'Reading file', filePath };
    case 'Bash':
      return { description: command ? `$ ${command.slice(0, 60)}${command.length > 60 ? '...' : ''}` : 'Running command', command };
    case 'Glob':
      return { description: 'Searching for files' };
    case 'Grep':
      return { description: 'Searching in files' };
    default:
      return { description: `Using ${toolName}` };
  }
}

function getToolIcon(toolName: string) {
  switch (toolName) {
    case 'Write':
      return <FileText size={14} className="text-green-400" />;
    case 'Edit':
      return <Edit size={14} className="text-yellow-400" />;
    case 'Read':
      return <FileCode size={14} className="text-blue-400" />;
    case 'Bash':
      return <Terminal size={14} className="text-orange-400" />;
    default:
      return <Terminal size={14} className="text-purple-400" />;
  }
}

function parseInjectedAgentMessage(content: string): { agentName: string; body: string } | null {
  const match = content.match(/^\[(Agent|Agent Context):\s*([^\]]+)\]\s*([\s\S]*)$/);
  if (!match) return null;
  return {
    agentName: match[2].trim(),
    body: (match[3] || '').trim(),
  };
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  runId,
  isConnected,
  onSendMessage,
  onStopResponse,
  onEndSession,
  agents,
  onInvokeAgent,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionInfo, setSessionInfo] = useState<SessionInfo>({});
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [agentPrompt, setAgentPrompt] = useState('');
  const [isInvokingAgent, setIsInvokingAgent] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [lastInjectContext, setLastInjectContext] = useState<{
    recentTurns: number;
    touchedFiles: string[];
    resolvedTarget: string | null;
  } | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
    }
  }, [messages, isAtBottom]);

  // Fetch session info periodically
  useEffect(() => {
    const fetchSessionInfo = async () => {
      try {
        const response = await fetch(`/api/interactive/${runId}`);
        if (response.ok) {
          const data = await response.json();
          setSessionInfo({
            title: data.title,
            tokens_in: data.tokens_in,
            tokens_out: data.tokens_out,
            model: data.model,
            is_responding: Boolean(data.is_responding),
          });
          setIsStreaming(Boolean(data.is_responding));
        }
      } catch (error) {
        console.error('Error fetching session info:', error);
      }
    };

    fetchSessionInfo();
    const interval = setInterval(fetchSessionInfo, 5000);
    return () => clearInterval(interval);
  }, [runId]);

  // Fetch events and build message history
  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const response = await fetch(`/api/runs/${runId}/events`);
        const data = await response.json();

        const newMessages: Message[] = [];
        let currentAssistantContent = '';
        let lastTimestamp = '';

        for (const event of data.events) {
          // Skip internal events
          if (['stream.init', 'stream.system', 'stream.start'].includes(event.type)) {
            continue;
          }

          if (event.type === 'stream.user') {
            // Flush assistant content
            if (currentAssistantContent) {
              newMessages.push({
                id: `assistant-${event.id}`,
                role: 'assistant',
                content: currentAssistantContent.trim(),
                timestamp: lastTimestamp,
              });
              currentAssistantContent = '';
            }

            const content = event.content || event.payload?.content || '';
            if (content) {
              const textContent = String(content);
              const injectedAgent = parseInjectedAgentMessage(textContent);
              if (injectedAgent) {
                newMessages.push({
                  id: event.id,
                  role: 'agent',
                  content: injectedAgent.body || '(No agent output)',
                  timestamp: event.timestamp,
                  agentName: injectedAgent.agentName,
                });
              } else {
                newMessages.push({
                  id: event.id,
                  role: 'user',
                  content: textContent,
                  timestamp: event.timestamp,
                });
              }
            }
          } else if (event.type === 'stream.assistant') {
            const delta = event.payload?.delta as Record<string, unknown> | undefined;
            const text = event.content || (delta?.text as string) || '';
            currentAssistantContent += text;
            lastTimestamp = event.timestamp;
          } else if (event.type === 'stream.tool_use') {
            // Flush assistant content first
            if (currentAssistantContent) {
              newMessages.push({
                id: `assistant-before-${event.id}`,
                role: 'assistant',
                content: currentAssistantContent.trim(),
                timestamp: lastTimestamp,
              });
              currentAssistantContent = '';
            }

            const toolName = (event.tool_name || event.payload?.name || 'Tool') as string;
            const toolInput = (event.tool_input || event.payload?.input) as Record<string, unknown> | undefined;
            const { description, filePath, command } = getToolDescription(toolName, toolInput);

            // Get file content for Write tool
            let fileContent: string | undefined;
            if (toolName === 'Write' && toolInput?.content) {
              fileContent = String(toolInput.content);
            }

            newMessages.push({
              id: event.id,
              role: 'tool',
              content: description,
              timestamp: event.timestamp,
              toolName,
              toolDescription: description,
              filePath,
              command,
              fileContent,
            });
          } else if (event.type === 'stream.tool_result') {
            // Show command output or errors
            const output = (event.tool_output || event.payload?.output) as string | undefined;
            const isError = event.is_error || (event.payload?.is_error as boolean);

            if (output && output.trim()) {
              newMessages.push({
                id: event.id,
                role: 'tool_result',
                content: output,
                timestamp: event.timestamp,
                isError,
              });
            }
          } else if (event.type === 'stream.result') {
            // Flush remaining assistant content
            if (currentAssistantContent) {
              newMessages.push({
                id: `assistant-${event.id}`,
                role: 'assistant',
                content: currentAssistantContent.trim(),
                timestamp: lastTimestamp,
              });
              currentAssistantContent = '';
            }
          }
        }

        // Add any remaining content
        if (currentAssistantContent) {
          newMessages.push({
            id: `assistant-final`,
            role: 'assistant',
            content: currentAssistantContent.trim(),
            timestamp: lastTimestamp || new Date().toISOString(),
          });
        }

        const dedupedEventMessages: Message[] = [];
        const seen = new Set<string>();
        for (const message of newMessages) {
          const key = `${message.id}:${message.role}`;
          if (seen.has(key)) continue;
          seen.add(key);
          dedupedEventMessages.push(message);
        }

        setMessages((prev) => {
          const localAgentMessages = prev.filter(
            (m) => m.role === 'agent' && m.id.startsWith('agent-')
          );
          return [...dedupedEventMessages, ...localAgentMessages];
        });

      } catch (error) {
        console.error('Error fetching events:', error);
      }
    };

    fetchEvents();
    const interval = setInterval(fetchEvents, 2000);
    return () => clearInterval(interval);
  }, [runId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !isConnected) return;

    const message = input.trim();
    setInput('');

    // Add user message immediately
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    }]);

    const agentMatch = message.match(/^@([a-zA-Z0-9_-]+)\s+([\s\S]+)/);
    if (agentMatch) {
      const handle = agentMatch[1];
      const instruction = agentMatch[2];
      const agent = findAgentByHandle(handle);
      if (!agent) {
        setAgentError(`Agent "@${handle}" not found`);
      } else {
        await invokeAgent(agent.id, instruction, false);
      }
      setIsStreaming(false);
      return;
    }

    setIsStreaming(true);
    onSendMessage(message);
  };

  const handleMessagesScroll = () => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsAtBottom(distanceFromBottom < 80);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && isStreaming) {
      e.preventDefault();
      void onStopResponse();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  };

  const findAgentByHandle = (handle: string) => {
    const normalized = handle.toLowerCase().replace(/[^a-z0-9]/g, '');
    return agents.find((agent) => {
      const nameKey = agent.name.toLowerCase().replace(/[^a-z0-9]/g, '');
      return nameKey === normalized;
    });
  };

  const invokeAgent = async (
    agentId: string,
    instruction: string,
    injectToSession = false
  ) => {
    if (!instruction.trim()) return;

    setAgentError(null);
    setIsInvokingAgent(true);
    try {
      const result = await onInvokeAgent(agentId, instruction, injectToSession);
      const contextSummary = {
        recentTurns: result.context?.recent_turns_count || 0,
        touchedFiles: result.context?.touched_files || [],
        resolvedTarget: result.context?.resolved_target || null,
      };
      if (!injectToSession) {
        setMessages(prev => [...prev, {
          id: `agent-${Date.now()}`,
          role: 'agent',
          content: result.output,
          timestamp: new Date().toISOString(),
          agentName: result.agent_name,
          agentModel: result.model,
          contextSummary,
        }]);
      } else {
        setLastInjectContext(contextSummary);
      }
      setAgentPrompt('');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to invoke agent';
      setAgentError(message);
    } finally {
      setIsInvokingAgent(false);
    }
  };

  return (
    <div className="flex h-full bg-gray-900">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-gray-200 font-medium truncate max-w-[300px]">
                {sessionInfo.title || 'Interactive Session'}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-400">
              {sessionInfo.model && (
                <span className="bg-gray-700 px-2 py-0.5 rounded">{sessionInfo.model}</span>
              )}
              {(sessionInfo.tokens_in || sessionInfo.tokens_out) ? (
                <span className="flex items-center gap-1">
                  <Zap size={12} />
                  {((sessionInfo.tokens_in || 0) + (sessionInfo.tokens_out || 0)).toLocaleString()} tokens
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void onStopResponse()}
              disabled={!isStreaming}
              className="px-3 py-1 text-sm bg-amber-600 hover:bg-amber-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded inline-flex items-center gap-1"
              title="Stop current response (Esc)"
            >
              <Square size={12} />
              Stop
            </button>
            <button
              onClick={onEndSession}
              className="px-3 py-1 text-sm bg-red-600 hover:bg-red-700 text-white rounded"
            >
              End Session
            </button>
          </div>
        </div>

        {/* Messages */}
        <div
          ref={messagesContainerRef}
          onScroll={handleMessagesScroll}
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 mt-8">
            <p className="text-lg mb-2">Start a conversation</p>
            <p className="text-sm">Type a message below to begin interacting with Claude</p>
          </div>
        ) : (
          messages.map((message) => (
            <div key={message.id}>
              {message.role === 'user' && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                    <User size={16} className="text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-blue-400">You</span>
                      <span className="text-xs text-gray-500">{formatTime(message.timestamp)}</span>
                    </div>
                    <p className="text-gray-200">{message.content}</p>
                  </div>
                </div>
              )}

              {message.role === 'assistant' && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0">
                    <Bot size={16} className="text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-purple-400">Claude</span>
                      <span className="text-xs text-gray-500">{formatTime(message.timestamp)}</span>
                    </div>
                    <div className="text-gray-200 prose prose-invert prose-sm max-w-none prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700 prose-code:text-purple-300">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {message.role === 'agent' && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center flex-shrink-0">
                    <Bot size={16} className="text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-emerald-400">
                        {message.agentName || 'Agent'}
                      </span>
                      {message.agentModel && (
                        <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                          {message.agentModel}
                        </span>
                      )}
                      <span className="text-xs text-gray-500">{formatTime(message.timestamp)}</span>
                    </div>
                    <div className="text-gray-200 prose prose-invert prose-sm max-w-none prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700 prose-code:text-emerald-300">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                    {message.contextSummary && (
                      <div className="mt-2 text-xs text-gray-400 flex flex-wrap gap-2">
                        <span className="bg-gray-800 border border-gray-700 rounded px-2 py-0.5">
                          {message.contextSummary.recentTurns || 0} turns
                        </span>
                        <span className="bg-gray-800 border border-gray-700 rounded px-2 py-0.5">
                          {(message.contextSummary.touchedFiles || []).length} files
                        </span>
                        {message.contextSummary.resolvedTarget && (
                          <span className="bg-gray-800 border border-gray-700 rounded px-2 py-0.5 truncate max-w-[360px]">
                            target: {message.contextSummary.resolvedTarget}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {message.role === 'tool' && (
                <div className="ml-11 space-y-2">
                  <div className="flex items-center gap-2 px-3 py-2 bg-gray-800/50 rounded-lg border border-gray-700 inline-flex">
                    {getToolIcon(message.toolName || '')}
                    <span className="text-sm text-gray-300">{message.content}</span>
                    <Check size={14} className="text-green-400" />
                  </div>
                  {message.filePath && (
                    <div className="text-xs text-gray-500 font-mono ml-1">{message.filePath}</div>
                  )}
                  {message.fileContent && (
                    <pre className="text-xs text-gray-300 bg-gray-800 border border-gray-700 rounded-lg p-3 overflow-auto max-h-48">
                      {message.fileContent.length > 500 ? message.fileContent.slice(0, 500) + '\n...' : message.fileContent}
                    </pre>
                  )}
                  {message.command && (
                    <pre className="text-xs text-green-400 bg-gray-800 border border-gray-700 rounded-lg p-2 font-mono">
                      $ {message.command}
                    </pre>
                  )}
                </div>
              )}

              {message.role === 'tool_result' && (
                <div className="ml-11">
                  <pre className={`text-xs ${message.isError ? 'text-red-400' : 'text-gray-300'} bg-gray-800 border ${message.isError ? 'border-red-800' : 'border-gray-700'} rounded-lg p-3 overflow-auto max-h-64 whitespace-pre-wrap`}>
                    {message.content.length > 1000 ? message.content.slice(0, 1000) + '\n...' : message.content}
                  </pre>
                </div>
              )}
            </div>
          ))
        )}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0">
              <Bot size={16} className="text-white" />
            </div>
            <div className="bg-gray-800 rounded-lg px-4 py-2">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-gray-400 text-sm">Claude is working on your request...</span>
              </div>
            </div>
          </div>
        )}

        {isInvokingAgent && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center flex-shrink-0">
              <Bot size={16} className="text-white" />
            </div>
            <div className="bg-gray-800 rounded-lg px-4 py-2">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-gray-400 text-sm">Agent is analyzing context...</span>
              </div>
            </div>
          </div>
        )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="border-t border-gray-700 p-4">
          <div className="flex gap-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isConnected ? "Type a message or @AgentName <task>" : "Session not connected"}
              disabled={!isConnected}
              className="flex-1 bg-gray-800 text-gray-100 rounded-lg px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
              rows={2}
            />
            <button
              type="submit"
              disabled={!isConnected || !input.trim()}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
            >
              Send
            </button>
          </div>
          {agentError && (
            <p className="text-xs text-red-400 mt-2">{agentError}</p>
          )}
        </form>
      </div>

      {/* Agent Dock */}
      <aside className="w-80 border-l border-gray-800 bg-gray-900/70 p-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-white mb-3">Agent Dock</h3>
        {agents.length === 0 ? (
          <p className="text-sm text-gray-500">No agents available. Create one in Agents page.</p>
        ) : (
          <div className="space-y-3">
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="">Select an agent...</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} {agent.role ? `(${agent.role})` : ''}
                </option>
              ))}
            </select>

            <textarea
              value={agentPrompt}
              onChange={(e) => setAgentPrompt(e.target.value)}
              placeholder="Ask selected agent to analyze, plan, or review..."
              rows={5}
              className="w-full bg-gray-800 text-gray-100 rounded-lg px-3 py-2 resize-none border border-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                disabled={!selectedAgentId || !agentPrompt.trim() || isInvokingAgent}
                onClick={() => invokeAgent(selectedAgentId, agentPrompt, false)}
                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm rounded-lg transition-colors"
              >
                {isInvokingAgent ? 'Running...' : 'Ask Agent'}
              </button>
              <button
                type="button"
                disabled={!selectedAgentId || !agentPrompt.trim() || isInvokingAgent}
                onClick={() => invokeAgent(selectedAgentId, agentPrompt, true)}
                className="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm rounded-lg transition-colors"
              >
                <span className="inline-flex items-center gap-1">
                  <Send size={12} />
                  Inject
                </span>
              </button>
            </div>

            <div className="text-xs text-gray-500 border-t border-gray-800 pt-3">
              <p>Shortcut: use <span className="text-emerald-400">@AgentName your task</span> in chat.</p>
              {lastInjectContext && (
                <div className="mt-2 text-[11px] text-gray-400 space-y-1">
                  <p className="text-blue-300">Last inject context sent:</p>
                  <p>{lastInjectContext.recentTurns} recent turns, {lastInjectContext.touchedFiles.length} touched files</p>
                  {lastInjectContext.resolvedTarget && (
                    <p className="truncate">Resolved target: {lastInjectContext.resolvedTarget}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
};
