import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { usersApi } from '../api/users';
import apiClient from '../api/client';

interface UserContextValue {
  userId: string | null;
  isGlobalAdmin: boolean;
  loading: boolean;
  login: (userId: string) => Promise<void>;
  logout: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(
    () => localStorage.getItem('userId'),
  );
  const [isGlobalAdmin, setIsGlobalAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  const syncHeader = useCallback((id: string | null) => {
    if (id) {
      apiClient.defaults.headers.common['X-User-ID'] = id;
    } else {
      delete apiClient.defaults.headers.common['X-User-ID'];
    }
  }, []);

  // On mount, restore session if saved userId exists
  useEffect(() => {
    const savedId = localStorage.getItem('userId');
    if (savedId) {
      syncHeader(savedId);
      usersApi.me()
        .then((data) => {
          setUserId(data.user_id);
          setIsGlobalAdmin(data.is_global_admin);
        })
        .catch(() => {
          // If validation fails, clear saved state
          localStorage.removeItem('userId');
          setUserId(null);
          syncHeader(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [syncHeader]);

  const login = useCallback(async (id: string) => {
    syncHeader(id);
    const data = await usersApi.me();
    setUserId(data.user_id);
    setIsGlobalAdmin(data.is_global_admin);
    localStorage.setItem('userId', data.user_id);
  }, [syncHeader]);

  const logout = useCallback(() => {
    setUserId(null);
    setIsGlobalAdmin(false);
    localStorage.removeItem('userId');
    localStorage.removeItem('activeEnvironmentId');
    syncHeader(null);
  }, [syncHeader]);

  return (
    <UserContext.Provider value={{ userId, isGlobalAdmin, loading, login, logout }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const ctx = useContext(UserContext);
  if (!ctx) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return ctx;
}
