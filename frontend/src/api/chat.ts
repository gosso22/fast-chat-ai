import apiClient from './client';
import type {
  Conversation,
  ConversationDetail,
  SendMessageRequest,
  SendMessageResponse,
  StartConversationRequest,
  StartConversationResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export interface StreamCallbacks {
  onSources?: (data: { sources: any[]; metadata: Record<string, any> }) => void;
  onChunk?: (content: string) => void;
  onDone?: (data: { message_id: string; timestamp: string }) => void;
  onError?: (detail: string) => void;
}

async function consumeSSE(
  url: string,
  body: Record<string, any>,
  headers: Record<string, string>,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errBody.detail || response.statusText);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      if (!part.trim()) continue;
      let eventType = 'message';
      let data = '';
      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7);
        else if (line.startsWith('data: ')) data = line.slice(6);
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (eventType === 'sources') callbacks.onSources?.(parsed);
      else if (eventType === 'chunk') callbacks.onChunk?.(parsed.content);
      else if (eventType === 'done') callbacks.onDone?.(parsed);
      else if (eventType === 'error') callbacks.onError?.(parsed.detail);
    }
  }
}

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

  updateConversationTitle: async (
    conversationId: string,
    title: string,
    userId: string
  ): Promise<Conversation> => {
    const response = await apiClient.patch<Conversation>(
      `/chat/conversations/${conversationId}`,
      { title, user_id: userId }
    );
    return response.data;
  },

  // Environment-scoped endpoints
  startEnvConversation: async (
    environmentId: string,
    data: { title?: string },
    userId: string
  ): Promise<StartConversationResponse> => {
    const response = await apiClient.post<StartConversationResponse>(
      `/environments/${environmentId}/chat/conversations`,
      data,
      { headers: { 'X-User-ID': userId } }
    );
    return response.data;
  },

  listEnvConversations: async (
    environmentId: string,
    userId: string,
    page = 1,
    pageSize = 20
  ): Promise<{
    conversations: Conversation[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const response = await apiClient.get(
      `/environments/${environmentId}/chat/conversations`,
      {
        params: { page, page_size: pageSize },
        headers: { 'X-User-ID': userId },
      }
    );
    return response.data;
  },

  sendEnvMessage: async (
    environmentId: string,
    conversationId: string,
    data: SendMessageRequest
  ): Promise<SendMessageResponse> => {
    const response = await apiClient.post<SendMessageResponse>(
      `/environments/${environmentId}/chat/conversations/${conversationId}/messages`,
      data,
      { headers: { 'X-User-ID': data.user_id } }
    );
    return response.data;
  },

  // Streaming endpoints
  sendMessageStream: (
    conversationId: string,
    data: SendMessageRequest,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
  ): Promise<void> => {
    const headers: Record<string, string> = {};
    if (apiClient.defaults.headers.common['X-User-ID']) {
      headers['X-User-ID'] = apiClient.defaults.headers.common['X-User-ID'] as string;
    }
    return consumeSSE(
      `${API_BASE_URL}/chat/conversations/${conversationId}/messages/stream`,
      data,
      headers,
      callbacks,
      signal,
    );
  },

  sendEnvMessageStream: (
    environmentId: string,
    conversationId: string,
    data: SendMessageRequest,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
  ): Promise<void> => {
    return consumeSSE(
      `${API_BASE_URL}/environments/${environmentId}/chat/conversations/${conversationId}/messages/stream`,
      data,
      { 'X-User-ID': data.user_id },
      callbacks,
      signal,
    );
  },
};
