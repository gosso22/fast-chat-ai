import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { usersApi, type UserEnvironment } from '../api/users';
import { useUser } from './UserContext';
import type { Environment } from '../types';

interface EnvironmentContextValue {
  environments: Environment[];
  activeEnvironment: Environment | null;
  activeRole: 'admin' | 'chat_user' | null;
  setActiveEnvironment: (env: Environment | null) => void;
  refreshEnvironments: () => Promise<void>;
  loading: boolean;
  getRoleForEnvironment: (envId: string) => 'admin' | 'chat_user' | null;
}

const EnvironmentContext = createContext<EnvironmentContextValue | null>(null);

export function EnvironmentProvider({ children }: { children: ReactNode }) {
  const { userId } = useUser();
  const [userEnvs, setUserEnvs] = useState<UserEnvironment[]>([]);
  const [activeEnvironment, setActiveEnvironment] = useState<Environment | null>(null);
  const [loading, setLoading] = useState(true);

  const environments = userEnvs.map((ue) => ue.environment as Environment);

  const getRoleForEnvironment = (envId: string): 'admin' | 'chat_user' | null => {
    const found = userEnvs.find((ue) => ue.environment.id === envId);
    return found ? found.role : null;
  };

  const activeRole = activeEnvironment
    ? getRoleForEnvironment(activeEnvironment.id)
    : null;

  const refreshEnvironments = async () => {
    if (!userId) {
      setUserEnvs([]);
      setActiveEnvironment(null);
      setLoading(false);
      return;
    }

    try {
      const envs = await usersApi.myEnvironments();
      setUserEnvs(envs);

      const envList = envs.map((ue) => ue.environment as Environment);

      // Auto-select saved environment or first available
      if (!activeEnvironment && envList.length > 0) {
        const savedId = localStorage.getItem('activeEnvironmentId');
        const saved = savedId ? envList.find((e) => e.id === savedId) : null;
        setActiveEnvironment(saved || envList[0]);
      }

      // If active env was deleted or user lost access, reset
      if (activeEnvironment && !envList.find((e) => e.id === activeEnvironment.id)) {
        setActiveEnvironment(envList[0] || null);
      }
    } catch (err) {
      console.error('Failed to load environments:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshEnvironments();
  }, [userId]);

  // Persist selection
  useEffect(() => {
    if (activeEnvironment) {
      localStorage.setItem('activeEnvironmentId', activeEnvironment.id);
    } else {
      localStorage.removeItem('activeEnvironmentId');
    }
  }, [activeEnvironment]);

  return (
    <EnvironmentContext.Provider
      value={{
        environments,
        activeEnvironment,
        activeRole,
        setActiveEnvironment,
        refreshEnvironments,
        loading,
        getRoleForEnvironment,
      }}
    >
      {children}
    </EnvironmentContext.Provider>
  );
}

export function useEnvironment() {
  const ctx = useContext(EnvironmentContext);
  if (!ctx) {
    throw new Error('useEnvironment must be used within an EnvironmentProvider');
  }
  return ctx;
}
