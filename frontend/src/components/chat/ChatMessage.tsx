import type { ChatMessage as ChatMessageType } from '../../types';

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[70%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-gradient-to-r from-[#00E5FF] to-[#FF00E5] text-white'
            : 'bg-gray-100 text-gray-900'
        }`}
      >
        <div className="text-xs font-semibold mb-1 opacity-75">
          {isUser ? 'You' : 'Assistant'}
        </div>
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        {message.timestamp && (
          <div className="text-xs mt-1 opacity-60">
            {new Date(message.timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}
