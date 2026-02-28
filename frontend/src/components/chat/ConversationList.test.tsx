import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConversationList } from './ConversationList';
import type { Conversation } from '../../types';

describe('ConversationList', () => {
  const mockConversations: Conversation[] = [
    {
      id: '1',
      title: 'First Conversation',
      user_id: 'user1',
      created_at: '2024-01-01T12:00:00Z',
      updated_at: '2024-01-01T12:30:00Z',
      message_count: 5,
      last_message_preview: 'Last message here',
    },
    {
      id: '2',
      title: 'Second Conversation',
      user_id: 'user1',
      created_at: '2024-01-02T12:00:00Z',
      updated_at: '2024-01-02T12:30:00Z',
      message_count: 3,
    },
  ];

  it('renders new chat button', () => {
    render(
      <ConversationList
        conversations={[]}
        onSelectConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
        onNewConversation={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
  });

  it('shows empty state when no conversations', () => {
    render(
      <ConversationList
        conversations={[]}
        onSelectConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
        onNewConversation={vi.fn()}
      />
    );

    expect(screen.getByText('No conversations yet')).toBeInTheDocument();
  });

  it('renders list of conversations', () => {
    render(
      <ConversationList
        conversations={mockConversations}
        onSelectConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
        onNewConversation={vi.fn()}
      />
    );

    expect(screen.getByText('First Conversation')).toBeInTheDocument();
    expect(screen.getByText('Second Conversation')).toBeInTheDocument();
    expect(screen.getByText('Last message here')).toBeInTheDocument();
  });

  it('calls onNewConversation when new chat button is clicked', async () => {
    const user = userEvent.setup();
    const onNewConversation = vi.fn();

    render(
      <ConversationList
        conversations={[]}
        onSelectConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
        onNewConversation={onNewConversation}
      />
    );

    await user.click(screen.getByRole('button', { name: /new chat/i }));
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });

  it('calls onSelectConversation when conversation is clicked', async () => {
    const user = userEvent.setup();
    const onSelectConversation = vi.fn();

    render(
      <ConversationList
        conversations={mockConversations}
        onSelectConversation={onSelectConversation}
        onDeleteConversation={vi.fn()}
        onNewConversation={vi.fn()}
      />
    );

    await user.click(screen.getByText('First Conversation'));
    expect(onSelectConversation).toHaveBeenCalledWith('1');
  });

  it('calls onDeleteConversation when delete button is clicked', async () => {
    const user = userEvent.setup();
    const onDeleteConversation = vi.fn();

    render(
      <ConversationList
        conversations={mockConversations}
        onSelectConversation={vi.fn()}
        onDeleteConversation={onDeleteConversation}
        onNewConversation={vi.fn()}
      />
    );

    const deleteButtons = screen.getAllByLabelText('Delete conversation');
    await user.click(deleteButtons[0]);

    expect(onDeleteConversation).toHaveBeenCalledWith('1');
  });

  it('highlights active conversation', () => {
    const { container } = render(
      <ConversationList
        conversations={mockConversations}
        activeConversationId="1"
        onSelectConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
        onNewConversation={vi.fn()}
      />
    );

    const activeConversation = container.querySelector('.border-\\[\\#00E5FF\\]\\/30');
    expect(activeConversation).toBeInTheDocument();
  });
});
