import apiClient from './client';
import type {
  Environment,
  EnvironmentCreate,
  EnvironmentUpdate,
  EnvironmentDeleteResponse,
} from '../types';

export const environmentsApi = {
  list: async (skip = 0, limit = 100): Promise<Environment[]> => {
    const response = await apiClient.get<Environment[]>('/environments', {
      params: { skip, limit },
    });
    return response.data;
  },

  get: async (id: string): Promise<Environment> => {
    const response = await apiClient.get<Environment>(`/environments/${id}`);
    return response.data;
  },

  create: async (data: EnvironmentCreate): Promise<Environment> => {
    const response = await apiClient.post<Environment>('/environments', data);
    return response.data;
  },

  update: async (id: string, data: EnvironmentUpdate): Promise<Environment> => {
    const response = await apiClient.put<Environment>(`/environments/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<EnvironmentDeleteResponse> => {
    const response = await apiClient.delete<EnvironmentDeleteResponse>(`/environments/${id}`);
    return response.data;
  },
};
