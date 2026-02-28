import apiClient from './client';
import type {
  Conversation,
  ConversationDetail,
  SendMessageRequest,
  SendMessageResponse,
  StartConversationRequest,
  StartConversationResponse,
} from '../types';

export const chatApi = {
  startConversation: async (data: StartConversationRequest): Promise<StartConversationResponse> => {
    const response = await apiClient.post<StartConversationResponse>('/chat/conversations', data);
    return response.data;
  },

  listConversations: async (userId: string, page = 1, pageSize = 20): Promise<{
    conversations: Conversation[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const response = await apiClient.get('/chat/conversations', {
      params: { user_id: userId, page, page_size: pageSize },
    });
    return response.data;
  },

  getConversation: async (conversationId: string, userId: string): Promise<ConversationDetail> => {
    const response = await apiClient.get<ConversationDetail>(
      `/chat/conversations/${conversationId}`,
      { params: { user_id: userId } }
    );
    return response.data;
  },

  sendMessage: async (conversationId: string, data: SendMessageRequest): Promise<SendMessageResponse> => {
    const response = await apiClient.post<SendMessageResponse>(
      `/chat/conversations/${conversationId}/messages`,
      data
    );
    return response.data;
  },

  deleteConversation: async (conversationId: string, userId: string): Promise<void> => {
    await apiClient.delete(`/chat/conversations/${conversationId}`, {
      params: { user_id: userId },
    });
  },
};
