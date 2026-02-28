// API Types matching backend schemas

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
}

export interface Conversation {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string;
}

export interface ConversationDetail extends Omit<Conversation, 'message_count' | 'last_message_preview'> {
  messages: ChatMessage[];
}

export interface Document {
  id: string;
  filename: string;
  file_size: number;
  content_type: string;
  upload_date: string;
  processing_status: 'pending' | 'processed' | 'extraction_failed';
  chunk_count?: number;
}

export interface SendMessageRequest {
  message: string;
  user_id: string;
  max_context_chunks?: number;
  similarity_threshold?: number;
  temperature?: number;
  include_citations?: boolean;
}

export interface SendMessageResponse {
  message_id: string;
  conversation_id: string;
  response: string;
  sources: Array<{
    document_id: string;
    filename: string;
    chunk_index: number;
    similarity: number;
    content_preview: string;
  }>;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface StartConversationRequest {
  title?: string;
  user_id: string;
}

export interface StartConversationResponse {
  conversation_id: string;
  title: string;
  created_at: string;
}

export interface ApiError {
  detail: string;
}
