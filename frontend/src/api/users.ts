import apiClient from './client';

export interface UserMe {
  user_id: string;
  is_global_admin: boolean;
}

export interface UserEnvironment {
  environment: {
    id: string;
    name: string;
    description: string | null;
    system_prompt: string | null;
    settings: Record<string, unknown> | null;
    created_by: string;
    created_at: string;
    updated_at: string;
  };
  role: 'admin' | 'chat_user';
}

export const usersApi = {
  me: async (): Promise<UserMe> => {
    const response = await apiClient.get<UserMe>('/users/me');
    return response.data;
  },

  myEnvironments: async (): Promise<UserEnvironment[]> => {
    const response = await apiClient.get<UserEnvironment[]>('/users/me/environments');
    return response.data;
  },
};
