import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatPage } from './ChatPage';
import { chatApi } from '../api/chat';
import { UserProvider } from '../contexts/UserContext';
import { EnvironmentProvider } from '../contexts/EnvironmentContext';

vi.mock('../api/chat', () => ({
  chatApi: {
    listConversations: vi.fn(),
    getConversation: vi.fn(),
    startConversation: vi.fn(),
    sendMessage: vi.fn(),
    deleteConversation: vi.fn(),
  },
}));

vi.mock('../api/users', () => ({
  usersApi: {
    me: vi.fn().mockResolvedValue({ user_id: 'test_user', is_global_admin: false }),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

// Seed localStorage so UserProvider restores the session
beforeEach(() => {
  localStorage.setItem('userId', 'test_user');
});

function renderChatPage() {
  return render(
    <UserProvider>
      <EnvironmentProvider>
        <ChatPage />
      </EnvironmentProvider>
    </UserProvider>
  );
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('userId', 'test_user');
    vi.mocked(chatApi.listConversations).mockResolvedValue({
      conversations: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  it('renders welcome message initially', async () => {
    renderChatPage();

    await waitFor(() => {
      expect(screen.getByText('Welcome to Fast Chat')).toBeInTheDocument();
    });
  });

  it('renders conversation list with new chat button', async () => {
    renderChatPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });
  });

  it('loads conversations on mount', async () => {
    renderChatPage();

    await waitFor(() => {
      expect(chatApi.listConversations).toHaveBeenCalledWith('test_user');
    });
  });

  it('displays conversations when loaded', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue({
      conversations: [
        {
          id: '1',
          title: 'Test Conversation',
          user_id: 'demo-user',
          created_at: '2024-01-01T12:00:00Z',
          updated_at: '2024-01-01T12:30:00Z',
          message_count: 2,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByText('Test Conversation')).toBeInTheDocument();
    });
  });

  it('creates new conversation when new chat button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(chatApi.startConversation).mockResolvedValue({
      conversation_id: 'new-conv-id',
      title: 'New Conversation',
      created_at: '2024-01-01T12:00:00Z',
    });

    vi.mocked(chatApi.getConversation).mockResolvedValue({
      id: 'new-conv-id',
      title: 'New Conversation',
      user_id: 'demo-user',
      created_at: '2024-01-01T12:00:00Z',
      updated_at: '2024-01-01T12:00:00Z',
      messages: [],
    });

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new chat/i }));

    await waitFor(() => {
      expect(chatApi.startConversation).toHaveBeenCalledWith({
        user_id: 'test_user',
      });
    });
  });

  it('loads conversation messages when conversation is selected', async () => {
    const user = userEvent.setup();
    vi.mocked(chatApi.listConversations).mockResolvedValue({
      conversations: [
        {
          id: '1',
          title: 'Test Conversation',
          user_id: 'demo-user',
          created_at: '2024-01-01T12:00:00Z',
          updated_at: '2024-01-01T12:30:00Z',
          message_count: 2,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    vi.mocked(chatApi.getConversation).mockResolvedValue({
      id: '1',
      title: 'Test Conversation',
      user_id: 'demo-user',
      created_at: '2024-01-01T12:00:00Z',
      updated_at: '2024-01-01T12:30:00Z',
      messages: [
        { id: 'm1', role: 'user', content: 'Hello', timestamp: '2024-01-01T12:00:00Z' },
        { id: 'm2', role: 'assistant', content: 'Hi there!', timestamp: '2024-01-01T12:00:01Z' },
      ],
    });

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByText('Test Conversation')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Test Conversation'));

    await waitFor(() => {
      expect(chatApi.getConversation).toHaveBeenCalledWith('1', 'test_user');
      expect(screen.getByText('Hello')).toBeInTheDocument();
      expect(screen.getByText('Hi there!')).toBeInTheDocument();
    });
  });

  it('sends message and displays response', async () => {
    const user = userEvent.setup();
    vi.mocked(chatApi.startConversation).mockResolvedValue({
      conversation_id: 'conv-1',
      title: 'New Conversation',
      created_at: '2024-01-01T12:00:00Z',
    });

    vi.mocked(chatApi.getConversation).mockResolvedValue({
      id: 'conv-1',
      title: 'New Conversation',
      user_id: 'demo-user',
      created_at: '2024-01-01T12:00:00Z',
      updated_at: '2024-01-01T12:00:00Z',
      messages: [],
    });

    vi.mocked(chatApi.sendMessage).mockResolvedValue({
      message_id: 'msg-1',
      conversation_id: 'conv-1',
      response: 'This is a response',
      sources: [],
      metadata: {},
      timestamp: '2024-01-01T12:00:01Z',
    });

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new chat/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Test message');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText('Test message')).toBeInTheDocument();
      expect(screen.getByText('This is a response')).toBeInTheDocument();
    });
  });

  it('deletes conversation when delete button is clicked', async () => {
    const user = userEvent.setup();
    vi.mocked(chatApi.listConversations).mockResolvedValue({
      conversations: [
        {
          id: '1',
          title: 'Test Conversation',
          user_id: 'demo-user',
          created_at: '2024-01-01T12:00:00Z',
          updated_at: '2024-01-01T12:30:00Z',
          message_count: 2,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    vi.mocked(chatApi.deleteConversation).mockResolvedValue();

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByText('Test Conversation')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete conversation');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(chatApi.deleteConversation).toHaveBeenCalledWith('1', 'test_user');
    });
  });

  it('shows typing indicator while waiting for response', async () => {
    const user = userEvent.setup();
    vi.mocked(chatApi.startConversation).mockResolvedValue({
      conversation_id: 'conv-1',
      title: 'New Conversation',
      created_at: '2024-01-01T12:00:00Z',
    });

    vi.mocked(chatApi.getConversation).mockResolvedValue({
      id: 'conv-1',
      title: 'New Conversation',
      user_id: 'demo-user',
      created_at: '2024-01-01T12:00:00Z',
      updated_at: '2024-01-01T12:00:00Z',
      messages: [],
    });

    // Delay the response to see typing indicator
    vi.mocked(chatApi.sendMessage).mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                message_id: 'msg-1',
                conversation_id: 'conv-1',
                response: 'Response',
                sources: [],
                metadata: {},
                timestamp: '2024-01-01T12:00:01Z',
              }),
            100
          )
        )
    );

    renderChatPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new chat/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Test');
    await user.click(screen.getByRole('button', { name: /send/i }));

    // Check for typing indicator (Assistant label appears in typing indicator)
    await waitFor(() => {
      const assistantLabels = screen.getAllByText('Assistant');
      expect(assistantLabels.length).toBeGreaterThan(0);
    });
  });
});
