import type { UserRoleWithEnvironment } from '../../types';

interface RoleCardProps {
  role: UserRoleWithEnvironment;
  onEdit: (role: UserRoleWithEnvironment) => void;
  onDelete: (role: UserRoleWithEnvironment) => void;
}

export function RoleCard({ role, onEdit, onDelete }: RoleCardProps) {
  const formattedDate = new Date(role.created_at).toLocaleDateString();
  const roleLabel = role.role === 'admin' ? 'Admin' : 'Chat User';

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900 truncate">{role.user_id}</p>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              role.role === 'admin'
                ? 'bg-purple-100 text-purple-800'
                : 'bg-green-100 text-green-800'
            }`}>
              {roleLabel}
            </span>
            {role.environment_name && (
              <span className="text-xs text-gray-500">{role.environment_name}</span>
            )}
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            type="button"
            onClick={() => onEdit(role)}
            aria-label={`Edit role for ${role.user_id}`}
            className="min-h-[44px] min-w-[44px] p-3 text-gray-400 hover:text-blue-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => onDelete(role)}
            aria-label={`Delete role for ${role.user_id}`}
            className="min-h-[44px] min-w-[44px] p-3 text-gray-400 hover:text-red-600 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>
      <div className="mt-2 text-xs text-gray-400">
        <span>Created: {formattedDate}</span>
      </div>
    </div>
  );
}
