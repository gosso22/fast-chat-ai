import { useState, useEffect, useCallback } from 'react';
import type { Environment } from '../../types';
import { environmentsApi } from '../../api/environments';
import { EnvironmentCard } from './EnvironmentCard';
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { EmptyState } from '../ui/EmptyState';

interface EnvironmentListProps {
  onEdit: (environment: Environment) => void;
  onDelete: (environment: Environment) => void;
  onCreate: () => void;
  refreshKey?: number;
}

export function EnvironmentList({ onEdit, onDelete, onCreate, refreshKey }: EnvironmentListProps) {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEnvironments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await environmentsApi.list();
      setEnvironments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load environments');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEnvironments();
  }, [fetchEnvironments, refreshKey]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 mb-4">{error}</p>
        <button
          type="button"
          onClick={fetchEnvironments}
          className="min-h-[44px] px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (environments.length === 0) {
    return (
      <EmptyState
        icon={
          <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
          </svg>
        }
        title="No environments yet"
        description="Create your first environment to start building a knowledge base."
        action={{ label: 'Create Environment', onClick: onCreate }}
      />
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Environments ({environments.length})
        </h2>
        <button
          type="button"
          onClick={onCreate}
          className="min-h-[44px] px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
        >
          Create Environment
        </button>
      </div>

      {/* Mobile: cards, Desktop: table */}
      <div className="lg:hidden flex flex-col gap-3">
        {environments.map((env) => (
          <EnvironmentCard key={env.id} environment={env} onEdit={onEdit} onDelete={onDelete} />
        ))}
      </div>

      <div className="hidden lg:block">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-500 uppercase bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Created By</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {environments.map((env) => (
              <tr key={env.id} className="bg-white hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{env.name}</td>
                <td className="px-4 py-3 text-gray-500">{env.description || '—'}</td>
                <td className="px-4 py-3 text-gray-500">{env.created_by}</td>
                <td className="px-4 py-3 text-gray-500">
                  {new Date(env.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => onEdit(env)}
                      aria-label={`Edit ${env.name}`}
                      className="min-h-[44px] min-w-[44px] p-3 text-gray-400 hover:text-blue-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(env)}
                      aria-label={`Delete ${env.name}`}
                      className="min-h-[44px] min-w-[44px] p-3 text-gray-400 hover:text-red-600 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
