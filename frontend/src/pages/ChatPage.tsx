import { useState, useEffect, useRef } from 'react';
import { chatApi } from '../api/chat';
import { ConversationList, MessageList, MessageInput } from '../components/chat';
import { useEnvironment } from '../contexts/EnvironmentContext';
import { useUser } from '../contexts/UserContext';
import type { Conversation, ChatMessage, ConversationDetail } from '../types';

export function ChatPage() {
  const { activeEnvironment } = useEnvironment();
  const { userId } = useUser();
  const USER_ID = userId!;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const titleRefreshTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const abortControllerRef = useRef<AbortController>();
  const isFirstLoadRef = useRef(true);
  const prevEnvIdRef = useRef<string | null | undefined>(undefined);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (titleRefreshTimerRef.current) clearTimeout(titleRefreshTimerRef.current);
      abortControllerRef.current?.abort();
    };
  }, []);

  // Load conversations on mount and when environment changes
  useEffect(() => {
    const envId = activeEnvironment?.id ?? null;
    if (isFirstLoadRef.current || prevEnvIdRef.current !== envId) {
      isFirstLoadRef.current = false;
      prevEnvIdRef.current = envId;
      setActiveConversationId(undefined);
      setMessages([]);
      loadConversations();
    }
  }, [activeEnvironment?.id]);

  // Load messages when active conversation changes
  useEffect(() => {
    if (activeConversationId) {
      loadConversation(activeConversationId);
    } else {
      setMessages([]);
    }
  }, [activeConversationId]);

  const loadConversations = async () => {
    try {
      const envId = activeEnvironment?.id;
      const response = envId
        ? await chatApi.listEnvConversations(envId, USER_ID)
        : await chatApi.listConversations(USER_ID);
      setConversations(response.conversations);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (conversationId: string) => {
    try {
      setIsLoading(true);
      const conversation: ConversationDetail = await chatApi.getConversation(conversationId, USER_ID);
      setMessages(conversation.messages);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const envId = activeEnvironment?.id;
      const response = envId
        ? await chatApi.startEnvConversation(envId, {}, USER_ID)
        : await chatApi.startConversation({ user_id: USER_ID });
      setActiveConversationId(response.conversation_id);
      await loadConversations();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
  };

  const handleDeleteConversation = async (conversationId: string) => {
    try {
      await chatApi.deleteConversation(conversationId, USER_ID);
      if (activeConversationId === conversationId) {
        setActiveConversationId(undefined);
      }
      await loadConversations();
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleSendMessage = async (message: string) => {
    let conversationId = activeConversationId;

    if (!conversationId) {
      try {
        const envId = activeEnvironment?.id;
        const response = envId
          ? await chatApi.startEnvConversation(envId, {}, USER_ID)
          : await chatApi.startConversation({ user_id: USER_ID });
        conversationId = response.conversation_id;
        setActiveConversationId(conversationId);
        await loadConversations();
      } catch (error) {
        console.error('Failed to create conversation:', error);
        return;
      }
    }

    // Add user message immediately
    const userMessage: ChatMessage = {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    // Abort any previous stream
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const isFirstMessage = messages.length === 0;
    const envId = activeEnvironment?.id;
    const messageData = { message, user_id: USER_ID };

    // Create a placeholder assistant message that we'll update incrementally
    const placeholderMessage: ChatMessage = {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      metadata: {},
    };
    setMessages((prev) => [...prev, placeholderMessage]);

    try {
      const streamFn = envId
        ? (cb: typeof import('../api/chat').StreamCallbacks, signal?: AbortSignal) =>
            chatApi.sendEnvMessageStream(envId, conversationId!, messageData, cb, signal)
        : (cb: typeof import('../api/chat').StreamCallbacks, signal?: AbortSignal) =>
            chatApi.sendMessageStream(conversationId!, messageData, cb, signal);

      await streamFn(
        {
          onSources: (data) => {
            // Attach sources metadata to the assistant message
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  metadata: { ...last.metadata, sources: data.sources, ...data.metadata },
                };
              }
              return updated;
            });
          },
          onChunk: (content) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + content,
                };
              }
              return updated;
            });
          },
          onDone: (data) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  id: data.message_id,
                  timestamp: data.timestamp,
                };
              }
              return updated;
            });
          },
          onError: (detail) => {
            console.error('Stream error:', detail);
            // Update the placeholder message with error info
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === 'assistant' && !last.content) {
                updated[updated.length - 1] = {
                  ...last,
                  content: 'An error occurred while generating the response. Please try again.',
                };
              }
              return updated;
            });
          },
        },
        abortController.signal,
      );

      // Refresh conversations to update last message preview
      await loadConversations();

      // On first message, schedule a delayed re-fetch for background title
      if (isFirstMessage) {
        titleRefreshTimerRef.current = setTimeout(() => {
          loadConversations();
        }, 2000);
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        console.error('Failed to send message:', error);
      }
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col md:flex-row">
      <ConversationList
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onNewConversation={handleNewConversation}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <MessageList messages={messages} isTyping={isTyping} />
        <MessageInput onSendMessage={handleSendMessage} disabled={isLoading || isTyping} />
      </div>
    </div>
  );
}
