import { useState, useEffect, type FormEvent } from 'react';
import type { Environment, UserRole, UserRoleCreate, UserRoleUpdate, RoleType } from '../../types';
import { Modal } from '../ui/Modal';

interface RoleFormProps {
  mode: 'create' | 'edit';
  role?: UserRole;
  environments: Environment[];
  onSubmit: (data: UserRoleCreate | UserRoleUpdate) => Promise<void>;
  onClose: () => void;
  isOpen: boolean;
}

export function RoleForm({ mode, role, environments, onSubmit, onClose, isOpen }: RoleFormProps) {
  const [userId, setUserId] = useState('');
  const [roleType, setRoleType] = useState<RoleType>('chat_user');
  const [environmentId, setEnvironmentId] = useState('');
  const [errors, setErrors] = useState<{ userId?: string; role?: string; environmentId?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (mode === 'edit' && role) {
        setUserId(role.user_id);
        setRoleType(role.role);
        setEnvironmentId(role.environment_id);
      } else {
        setUserId('');
        setRoleType('chat_user');
        setEnvironmentId('');
      }
      setErrors({});
      setServerError(null);
      setSubmitting(false);
    }
  }, [isOpen, mode, role]);

  const validate = (): boolean => {
    const newErrors: typeof errors = {};
    if (mode === 'create') {
      if (!userId.trim()) newErrors.userId = 'User ID is required';
      if (!environmentId) newErrors.environmentId = 'Environment is required';
    }
    if (!roleType) newErrors.role = 'Role is required';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setServerError(null);
    try {
      if (mode === 'create') {
        await onSubmit({
          user_id: userId.trim(),
          role: roleType,
          environment_id: environmentId,
        } as UserRoleCreate);
      } else {
        await onSubmit({ role: roleType } as UserRoleUpdate);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      if (message.includes('409') || message.toLowerCase().includes('already')) {
        setErrors({ userId: 'User already has a role in this environment' });
      } else if (message.includes('404') || message.toLowerCase().includes('not found')) {
        setErrors({ environmentId: 'Environment not found' });
      } else {
        setServerError(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={mode === 'create' ? 'Assign Role' : 'Edit Role'}
    >
      <form onSubmit={handleSubmit} noValidate>
        <div className="space-y-4">
          <div>
            <label htmlFor="role-user-id" className="block text-sm font-medium text-gray-700 mb-1">
              User ID <span className="text-red-500">*</span>
            </label>
            <input
              id="role-user-id"
              type="text"
              value={userId}
              onChange={(e) => {
                setUserId(e.target.value);
                if (errors.userId) setErrors((prev) => ({ ...prev, userId: undefined }));
              }}
              disabled={mode === 'edit'}
              required
              aria-invalid={!!errors.userId}
              aria-describedby={errors.userId ? 'role-user-id-error' : undefined}
              className={`h-11 w-full px-3 rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.userId ? 'border-red-500' : 'border-gray-300'
              } ${mode === 'edit' ? 'bg-gray-100 text-gray-500' : ''}`}
            />
            {errors.userId && (
              <p id="role-user-id-error" className="mt-1 text-sm text-red-600" role="alert">
                {errors.userId}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="role-type" className="block text-sm font-medium text-gray-700 mb-1">
              Role <span className="text-red-500">*</span>
            </label>
            <select
              id="role-type"
              value={roleType}
              onChange={(e) => {
                setRoleType(e.target.value as RoleType);
                if (errors.role) setErrors((prev) => ({ ...prev, role: undefined }));
              }}
              aria-invalid={!!errors.role}
              className="h-11 w-full px-3 rounded-md border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="chat_user">Chat User</option>
              <option value="admin">Admin</option>
            </select>
            {errors.role && (
              <p className="mt-1 text-sm text-red-600" role="alert">{errors.role}</p>
            )}
          </div>

          <div>
            <label htmlFor="role-environment" className="block text-sm font-medium text-gray-700 mb-1">
              Environment <span className="text-red-500">*</span>
            </label>
            <select
              id="role-environment"
              value={environmentId}
              onChange={(e) => {
                setEnvironmentId(e.target.value);
                if (errors.environmentId) setErrors((prev) => ({ ...prev, environmentId: undefined }));
              }}
              disabled={mode === 'edit'}
              required
              aria-invalid={!!errors.environmentId}
              aria-describedby={errors.environmentId ? 'role-env-error' : undefined}
              className={`h-11 w-full px-3 rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white ${
                errors.environmentId ? 'border-red-500' : 'border-gray-300'
              } ${mode === 'edit' ? 'bg-gray-100 text-gray-500' : ''}`}
            >
              <option value="">Select environment...</option>
              {environments.map((env) => (
                <option key={env.id} value={env.id}>{env.name}</option>
              ))}
            </select>
            {errors.environmentId && (
              <p id="role-env-error" className="mt-1 text-sm text-red-600" role="alert">
                {errors.environmentId}
              </p>
            )}
          </div>

          {serverError && (
            <p className="text-sm text-red-600" role="alert">{serverError}</p>
          )}
        </div>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end mt-6">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="min-h-[44px] px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-md font-medium text-sm transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="min-h-[44px] px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 rounded-md font-medium text-sm transition-colors disabled:bg-blue-400 disabled:cursor-not-allowed flex items-center justify-center gap-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            {submitting && (
              <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            )}
            {mode === 'create' ? 'Assign' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
