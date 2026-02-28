import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageInput } from './MessageInput';

describe('MessageInput', () => {
  it('renders input field and send button', () => {
    render(<MessageInput onSendMessage={vi.fn()} />);

    expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  it('disables send button when input is empty', () => {
    render(<MessageInput onSendMessage={vi.fn()} />);

    const sendButton = screen.getByRole('button', { name: /send/i });
    expect(sendButton).toBeDisabled();
  });

  it('enables send button when input has text', async () => {
    const user = userEvent.setup();
    render(<MessageInput onSendMessage={vi.fn()} />);

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Hello');

    const sendButton = screen.getByRole('button', { name: /send/i });
    expect(sendButton).not.toBeDisabled();
  });

  it('calls onSendMessage with trimmed message on submit', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn();
    render(<MessageInput onSendMessage={onSendMessage} />);

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, '  Hello World  ');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSendMessage).toHaveBeenCalledWith('Hello World');
  });

  it('clears input after sending message', async () => {
    const user = userEvent.setup();
    render(<MessageInput onSendMessage={vi.fn()} />);

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Hello');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(input).toHaveValue('');
  });

  it('does not send empty or whitespace-only messages', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn();
    render(<MessageInput onSendMessage={onSendMessage} />);

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, '   ');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('disables input and button when disabled prop is true', () => {
    render(<MessageInput onSendMessage={vi.fn()} disabled={true} />);

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    expect(input).toBeDisabled();
    expect(sendButton).toBeDisabled();
  });
});
