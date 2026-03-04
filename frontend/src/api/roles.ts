import apiClient from './client';
import type {
  UserRole,
  UserRoleCreate,
  UserRoleUpdate,
  UserRoleDeleteResponse,
} from '../types';

export const rolesApi = {
  list: async (filters?: { environmentId?: string; userId?: string }): Promise<UserRole[]> => {
    const params: Record<string, string> = {};
    if (filters?.environmentId) params.environment_id = filters.environmentId;
    if (filters?.userId) params.user_id = filters.userId;

    const response = await apiClient.get<UserRole[]>('/roles', { params });
    return response.data;
  },

  get: async (id: string): Promise<UserRole> => {
    const response = await apiClient.get<UserRole>(`/roles/${id}`);
    return response.data;
  },

  create: async (data: UserRoleCreate): Promise<UserRole> => {
    const response = await apiClient.post<UserRole>('/roles', data);
    return response.data;
  },

  update: async (id: string, data: UserRoleUpdate): Promise<UserRole> => {
    const response = await apiClient.put<UserRole>(`/roles/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<UserRoleDeleteResponse> => {
    const response = await apiClient.delete<UserRoleDeleteResponse>(`/roles/${id}`);
    return response.data;
  },
};
