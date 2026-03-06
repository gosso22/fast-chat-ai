import { useState } from 'react';
import { useUser } from '../contexts/UserContext';

export function LoginPage() {
  const { login } = useUser();
  const [userIdInput, setUserIdInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = userIdInput.trim();
    if (!trimmed) return;

    setError(null);
    setSubmitting(true);
    try {
      await login(trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <img src="/logo.svg" alt="Fast Chat" className="h-16 w-16 mx-auto mb-4" />
          <h1 className="text-3xl font-extrabold tracking-wide brand-text-gradient">
            FAST CHAT
          </h1>
          <p className="text-gray-500 mt-2">Enter your User ID to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white shadow-md rounded-lg p-6 space-y-4">
          <div>
            <label htmlFor="user-id" className="block text-sm font-medium text-gray-700 mb-1">
              User ID
            </label>
            <input
              id="user-id"
              type="text"
              value={userIdInput}
              onChange={(e) => setUserIdInput(e.target.value)}
              placeholder="e.g. default_admin"
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#00E5FF] focus:border-transparent"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting || !userIdInput.trim()}
            className="w-full py-2 px-4 bg-gradient-to-r from-[#00E5FF] to-[#FF006E] text-white font-semibold rounded-md hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
