import { Navigate } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isGlobalAdmin, loading } = useUser();

  if (loading) {
    return null;
  }

  if (!isGlobalAdmin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
