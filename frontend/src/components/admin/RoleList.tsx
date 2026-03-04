import { useState, useEffect, useCallback, useMemo } from 'react';
import type { Environment, UserRole, UserRoleWithEnvironment } from '../../types';
import { rolesApi } from '../../api/roles';
import { environmentsApi } from '../../api/environments';
import { RoleCard } from './RoleCard';
import { RoleFilters } from './RoleFilters';
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { EmptyState } from '../ui/EmptyState';

interface RoleListProps {
  onEdit: (role: UserRoleWithEnvironment) => void;
  onDelete: (role: UserRoleWithEnvironment) => void;
  onCreate: () => void;
  refreshKey?: number;
}

export function RoleList({ onEdit, onDelete, onCreate, refreshKey }: RoleListProps) {
  const [roles, setRoles] = useState<UserRole[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [envFilter, setEnvFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rolesData, envsData] = await Promise.all([
        rolesApi.list(),
        environmentsApi.list(),
      ]);
      setRoles(rolesData);
      setEnvironments(envsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load roles');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshKey]);

  const envMap = useMemo(() => {
    const map = new Map<string, string>();
    environments.forEach((env) => map.set(env.id, env.name));
    return map;
  }, [environments]);

  const filteredRoles: UserRoleWithEnvironment[] = useMemo(() => {
    return roles
      .map((role) => ({
        ...role,
        environment_name: envMap.get(role.environment_id),
      }))
      .filter((role) => {
        if (envFilter && role.environment_id !== envFilter) return false;
        if (userFilter && !role.user_id.toLowerCase().includes(userFilter.toLowerCase())) return false;
        return true;
      });
  }, [roles, envMap, envFilter, userFilter]);

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
          onClick={fetchData}
          className="min-h-[44px] px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Roles ({filteredRoles.length})
        </h2>
        <button
          type="button"
          onClick={onCreate}
          className="min-h-[44px] px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
        >
          Assign Role
        </button>
      </div>

      <div className="mb-4">
        <RoleFilters
          environments={environments}
          selectedEnvironmentId={envFilter}
          userIdFilter={userFilter}
          onEnvironmentChange={setEnvFilter}
          onUserIdChange={setUserFilter}
        />
      </div>

      {filteredRoles.length === 0 ? (
        <EmptyState
          title={roles.length === 0 ? 'No roles assigned' : 'No matching roles'}
          description={
            roles.length === 0
              ? 'Assign roles to users to control access to environments.'
              : 'Try adjusting your filters.'
          }
          action={roles.length === 0 ? { label: 'Assign Role', onClick: onCreate } : undefined}
        />
      ) : (
        <>
          {/* Mobile: cards */}
          <div className="lg:hidden flex flex-col gap-3">
            {filteredRoles.map((role) => (
              <RoleCard key={role.id} role={role} onEdit={onEdit} onDelete={onDelete} />
            ))}
          </div>

          {/* Desktop: table */}
          <div className="hidden lg:block">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 uppercase bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3">User ID</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Environment</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredRoles.map((role) => (
                  <tr key={role.id} className="bg-white hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{role.user_id}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        role.role === 'admin'
                          ? 'bg-purple-100 text-purple-800'
                          : 'bg-green-100 text-green-800'
                      }`}>
                        {role.role === 'admin' ? 'Admin' : 'Chat User'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{role.environment_name || role.environment_id}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(role.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => onEdit(role)}
                          aria-label={`Edit role for ${role.user_id}`}
                          className="min-h-[44px] min-w-[44px] p-3 text-gray-400 hover:text-blue-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(role)}
                          aria-label={`Delete role for ${role.user_id}`}
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
        </>
      )}
    </div>
  );
}
