import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { UserProvider, useUser } from './contexts/UserContext';
import { LoginPage } from './pages/LoginPage';

function AppContent() {
  const { userId, loading } = useUser();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <span className="text-gray-400 animate-pulse">Loading...</span>
      </div>
    );
  }

  if (!userId) {
    return <LoginPage />;
  }

  return <RouterProvider router={router} />;
}

function App() {
  return (
    <UserProvider>
      <AppContent />
    </UserProvider>
  );
}

export default App;
