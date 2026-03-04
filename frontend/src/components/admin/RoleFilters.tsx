import type { Environment } from '../../types';

interface RoleFiltersProps {
  environments: Environment[];
  selectedEnvironmentId: string;
  userIdFilter: string;
  onEnvironmentChange: (environmentId: string) => void;
  onUserIdChange: (userId: string) => void;
}

export function RoleFilters({
  environments,
  selectedEnvironmentId,
  userIdFilter,
  onEnvironmentChange,
  onUserIdChange,
}: RoleFiltersProps) {
  return (
    <div className="flex flex-col sm:flex-row gap-3">
      <div className="flex-1">
        <label htmlFor="role-env-filter" className="block text-xs font-medium text-gray-500 mb-1">
          Environment
        </label>
        <select
          id="role-env-filter"
          value={selectedEnvironmentId}
          onChange={(e) => onEnvironmentChange(e.target.value)}
          className="h-11 w-full px-3 rounded-md border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All Environments</option>
          {environments.map((env) => (
            <option key={env.id} value={env.id}>{env.name}</option>
          ))}
        </select>
      </div>
      <div className="flex-1">
        <label htmlFor="role-user-filter" className="block text-xs font-medium text-gray-500 mb-1">
          User ID
        </label>
        <input
          id="role-user-filter"
          type="text"
          value={userIdFilter}
          onChange={(e) => onUserIdChange(e.target.value)}
          placeholder="Search by user ID..."
          className="h-11 w-full px-3 rounded-md border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
  );
}
