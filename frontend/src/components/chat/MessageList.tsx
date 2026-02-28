import { useEffect, useRef } from 'react';
import type { ChatMessage as ChatMessageType } from '../../types';
import { ChatMessage } from './ChatMessage';
import { TypingIndicator } from './TypingIndicator';

interface MessageListProps {
  messages: ChatMessageType[];
  isTyping?: boolean;
}

export function MessageList({ messages, isTyping = false }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  if (messages.length === 0 && !isTyping) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-gray-500 py-12">
          <img src="/logo.svg" alt="Fast Chat" className="h-24 w-24 mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2 brand-text-gradient">Welcome to Fast Chat</h2>
          <p className="text-sm">Upload documents and start asking questions about them.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 chat-scrollbar">
      <div className="max-w-3xl mx-auto">
        {messages.map((message) => (
          <ChatMessage key={message.id || Math.random()} message={message} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
