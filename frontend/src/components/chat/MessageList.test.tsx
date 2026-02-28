import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageList } from './MessageList';
import type { ChatMessage } from '../../types';

describe('MessageList', () => {
  it('renders welcome message when no messages', () => {
    render(<MessageList messages={[]} />);

    expect(screen.getByText('Welcome to Fast Chat')).toBeInTheDocument();
    expect(screen.getByText(/Upload documents and start asking questions/i)).toBeInTheDocument();
  });

  it('renders list of messages', () => {
    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'Hello' },
      { id: '2', role: 'assistant', content: 'Hi there!' },
    ];

    render(<MessageList messages={messages} />);

    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });

  it('shows typing indicator when isTyping is true', () => {
    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'Hello' },
    ];

    render(<MessageList messages={messages} isTyping={true} />);

    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Assistant')).toBeInTheDocument();
  });

  it('does not show welcome message when messages exist', () => {
    const messages: ChatMessage[] = [
      { id: '1', role: 'user', content: 'Hello' },
    ];

    render(<MessageList messages={messages} />);

    expect(screen.queryByText('Welcome to Fast Chat')).not.toBeInTheDocument();
  });

  it('shows typing indicator without messages', () => {
    render(<MessageList messages={[]} isTyping={true} />);

    expect(screen.getByText('Assistant')).toBeInTheDocument();
    expect(screen.queryByText('Welcome to Fast Chat')).not.toBeInTheDocument();
  });
});
