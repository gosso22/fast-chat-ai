import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage } from './ChatMessage';
import type { ChatMessage as ChatMessageType } from '../../types';

describe('ChatMessage', () => {
  it('renders user message with correct styling', () => {
    const message: ChatMessageType = {
      id: '1',
      role: 'user',
      content: 'Hello, how are you?',
      timestamp: '2024-01-01T12:00:00Z',
    };

    render(<ChatMessage message={message} />);

    expect(screen.getByText('You')).toBeInTheDocument();
    expect(screen.getByText('Hello, how are you?')).toBeInTheDocument();
  });

  it('renders assistant message with correct styling', () => {
    const message: ChatMessageType = {
      id: '2',
      role: 'assistant',
      content: 'I am doing well, thank you!',
      timestamp: '2024-01-01T12:00:01Z',
    };

    render(<ChatMessage message={message} />);

    expect(screen.getByText('Assistant')).toBeInTheDocument();
    expect(screen.getByText('I am doing well, thank you!')).toBeInTheDocument();
  });

  it('displays timestamp when provided', () => {
    const message: ChatMessageType = {
      id: '3',
      role: 'user',
      content: 'Test message',
      timestamp: '2024-01-01T12:00:00Z',
    };

    render(<ChatMessage message={message} />);

    const timestamp = new Date(message.timestamp!).toLocaleTimeString();
    expect(screen.getByText(timestamp)).toBeInTheDocument();
  });

  it('renders without timestamp', () => {
    const message: ChatMessageType = {
      role: 'user',
      content: 'Test message',
    };

    const { container } = render(<ChatMessage message={message} />);
    expect(container.querySelector('.text-xs.mt-1')).not.toBeInTheDocument();
  });
});
