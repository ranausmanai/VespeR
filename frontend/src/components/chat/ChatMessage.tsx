import React from 'react';

interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  toolName?: string;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  timestamp,
  toolName,
}) => {
  const isUser = role === 'user';
  const isSystem = role === 'system';

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
    >
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-blue-600 text-white'
            : isSystem
            ? 'bg-gray-700 text-gray-300 text-sm italic'
            : 'bg-gray-800 text-gray-100'
        }`}
      >
        {toolName && (
          <div className="text-xs text-yellow-400 mb-1 font-mono">
            Tool: {toolName}
          </div>
        )}
        <div className="whitespace-pre-wrap break-words">{content}</div>
        {timestamp && (
          <div className="text-xs opacity-50 mt-1 text-right">
            {new Date(timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
};
