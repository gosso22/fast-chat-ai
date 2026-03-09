import apiClient from './client';
import type { Document, DocumentMoveResponse } from '../types';

export const documentsApi = {
  upload: async (file: File, userId = 'default_user'): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<Document>('/documents/upload', formData, {
      headers: { 'Content-Type': undefined },
      params: { user_id: userId },
    });
    return response.data;
  },

  list: async (userId = 'default_user', skip = 0, limit = 100): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>('/documents/', {
      params: { user_id: userId, skip, limit },
    });
    return response.data;
  },

  get: async (documentId: string, userId = 'default_user'): Promise<Document> => {
    const response = await apiClient.get<Document>(`/documents/${documentId}`, {
      params: { user_id: userId },
    });
    return response.data;
  },

  delete: async (documentId: string, userId = 'default_user'): Promise<void> => {
    await apiClient.delete(`/documents/${documentId}`, {
      params: { user_id: userId },
    });
  },

  // Environment-scoped endpoints
  uploadToEnv: async (
    environmentId: string,
    file: File,
    userId: string
  ): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<Document>(
      `/environments/${environmentId}/documents/upload`,
      formData,
      {
        headers: { 'Content-Type': undefined, 'X-User-ID': userId },
      }
    );
    return response.data;
  },

  listEnv: async (
    environmentId: string,
    skip = 0,
    limit = 100
  ): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>(
      `/environments/${environmentId}/documents`,
      { params: { skip, limit } }
    );
    return response.data;
  },

  deleteFromEnv: async (
    environmentId: string,
    documentId: string,
    userId: string
  ): Promise<void> => {
    await apiClient.delete(
      `/environments/${environmentId}/documents/${documentId}`,
      { headers: { 'X-User-ID': userId } }
    );
  },

  moveToEnv: async (
    targetEnvironmentId: string,
    documentIds: string[],
    userId: string
  ): Promise<DocumentMoveResponse> => {
    const response = await apiClient.put<DocumentMoveResponse>(
      `/environments/${targetEnvironmentId}/documents/move`,
      { document_ids: documentIds },
      { headers: { 'X-User-ID': userId } }
    );
    return response.data;
  },
};
