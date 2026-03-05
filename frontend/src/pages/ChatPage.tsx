import { useState, useEffect, useRef } from 'react';
import { chatApi } from '../api/chat';
import { ConversationList, MessageList, MessageInput } from '../components/chat';
import type { Conversation, ChatMessage, ConversationDetail } from '../types';

const USER_ID = 'default_user'; // TODO: Replace with actual user authentication

export function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const titleRefreshTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (titleRefreshTimerRef.current) clearTimeout(titleRefreshTimerRef.current);
    };
  }, []);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

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
      const response = await chatApi.listConversations(USER_ID);
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
      const response = await chatApi.startConversation({
        user_id: USER_ID,
      });
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
    if (!activeConversationId) {
      // Create new conversation if none exists
      await handleNewConversation();
      return;
    }

    try {
      // Add user message immediately
      const userMessage: ChatMessage = {
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setIsTyping(true);

      // Send message to API
      const response = await chatApi.sendMessage(activeConversationId, {
        message,
        user_id: USER_ID,
      });

      // Add assistant response
      const assistantMessage: ChatMessage = {
        id: response.message_id,
        role: 'assistant',
        content: response.response,
        timestamp: response.timestamp,
        metadata: {
          sources: response.sources,
          ...response.metadata,
        },
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Refresh conversations to update last message preview
      await loadConversations();

      // On first message, schedule a delayed re-fetch to pick up the
      // background-generated title (takes ~1-2s on the backend)
      if (messages.length === 0) {
        titleRefreshTimerRef.current = setTimeout(() => {
          loadConversations();
        }, 2000);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      // TODO: Show error message to user
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
