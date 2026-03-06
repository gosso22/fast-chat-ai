// Admin Dashboard Types

// Environment types
export interface Environment {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EnvironmentCreate {
  name: string;
  description?: string;
  system_prompt?: string;
}

export interface EnvironmentUpdate {
  name?: string;
  description?: string;
  system_prompt?: string;
}

export interface EnvironmentDeleteResponse {
  message: string;
  deleted_environment_id: string;
  deleted_documents_count: number;
}

// User Role types
export type RoleType = 'admin' | 'chat_user';

export interface UserRole {
  id: string;
  user_id: string;
  role: RoleType;
  environment_id: string;
  created_at: string;
}

export interface UserRoleCreate {
  user_id: string;
  role: RoleType;
  environment_id: string;
}

export interface UserRoleUpdate {
  role: RoleType;
}

export interface UserRoleDeleteResponse {
  message: string;
  deleted_role_id: string;
}

// Extended type for display (with environment name)
export interface UserRoleWithEnvironment extends UserRole {
  environment_name?: string;
}
