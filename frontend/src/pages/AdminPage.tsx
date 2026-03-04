import { useState, useCallback } from 'react';
import type { Environment, EnvironmentCreate, EnvironmentUpdate, UserRoleCreate, UserRoleUpdate, UserRoleWithEnvironment } from '../types';
import { environmentsApi } from '../api/environments';
import { rolesApi } from '../api/roles';
import { EnvironmentList } from '../components/admin/EnvironmentList';
import { EnvironmentForm } from '../components/admin/EnvironmentForm';
import { RoleList } from '../components/admin/RoleList';
import { RoleForm } from '../components/admin/RoleForm';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { useToast } from '../hooks/useToast';

type Tab = 'environments' | 'roles';

export function AdminPage() {
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState<Tab>('environments');

  // Environment state
  const [envFormOpen, setEnvFormOpen] = useState(false);
  const [envFormMode, setEnvFormMode] = useState<'create' | 'edit'>('create');
  const [editingEnv, setEditingEnv] = useState<Environment | undefined>();
  const [deletingEnv, setDeletingEnv] = useState<Environment | null>(null);
  const [deleteEnvLoading, setDeleteEnvLoading] = useState(false);
  const [envRefreshKey, setEnvRefreshKey] = useState(0);

  // Role state
  const [roleFormOpen, setRoleFormOpen] = useState(false);
  const [roleFormMode, setRoleFormMode] = useState<'create' | 'edit'>('create');
  const [editingRole, setEditingRole] = useState<UserRoleWithEnvironment | undefined>();
  const [deletingRole, setDeletingRole] = useState<UserRoleWithEnvironment | null>(null);
  const [deleteRoleLoading, setDeleteRoleLoading] = useState(false);
  const [roleRefreshKey, setRoleRefreshKey] = useState(0);

  // Environments for role form dropdown
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const loadEnvironments = useCallback(async () => {
    try {
      const data = await environmentsApi.list();
      setEnvironments(data);
    } catch {
      // silently fail, form will show empty dropdown
    }
  }, []);

  // --- Environment handlers ---
  const handleCreateEnv = () => {
    setEnvFormMode('create');
    setEditingEnv(undefined);
    setEnvFormOpen(true);
  };

  const handleEditEnv = (env: Environment) => {
    setEnvFormMode('edit');
    setEditingEnv(env);
    setEnvFormOpen(true);
  };

  const handleEnvFormSubmit = async (data: EnvironmentCreate | EnvironmentUpdate) => {
    if (envFormMode === 'create') {
      await environmentsApi.create(data as EnvironmentCreate);
      addToast({ type: 'success', message: 'Environment created successfully' });
    } else if (editingEnv) {
      await environmentsApi.update(editingEnv.id, data as EnvironmentUpdate);
      addToast({ type: 'success', message: 'Environment updated successfully' });
    }
    setEnvFormOpen(false);
    setEnvRefreshKey((k) => k + 1);
  };

  const handleDeleteEnv = (env: Environment) => {
    setDeletingEnv(env);
  };

  const confirmDeleteEnv = async () => {
    if (!deletingEnv) return;
    setDeleteEnvLoading(true);
    try {
      const result = await environmentsApi.delete(deletingEnv.id);
      addToast({
        type: 'success',
        message: `Environment deleted. ${result.deleted_documents_count} document(s) removed.`,
      });
      setDeletingEnv(null);
      setEnvRefreshKey((k) => k + 1);
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to delete environment',
      });
      setDeletingEnv(null);
    } finally {
      setDeleteEnvLoading(false);
    }
  };

  // --- Role handlers ---
  const handleCreateRole = async () => {
    await loadEnvironments();
    setRoleFormMode('create');
    setEditingRole(undefined);
    setRoleFormOpen(true);
  };

  const handleEditRole = async (role: UserRoleWithEnvironment) => {
    await loadEnvironments();
    setRoleFormMode('edit');
    setEditingRole(role);
    setRoleFormOpen(true);
  };

  const handleRoleFormSubmit = async (data: UserRoleCreate | UserRoleUpdate) => {
    if (roleFormMode === 'create') {
      await rolesApi.create(data as UserRoleCreate);
      addToast({ type: 'success', message: 'Role assigned successfully' });
    } else if (editingRole) {
      await rolesApi.update(editingRole.id, data as UserRoleUpdate);
      addToast({ type: 'success', message: 'Role updated successfully' });
    }
    setRoleFormOpen(false);
    setRoleRefreshKey((k) => k + 1);
  };

  const handleDeleteRole = (role: UserRoleWithEnvironment) => {
    setDeletingRole(role);
  };

  const confirmDeleteRole = async () => {
    if (!deletingRole) return;
    setDeleteRoleLoading(true);
    try {
      await rolesApi.delete(deletingRole.id);
      addToast({ type: 'success', message: 'Role removed successfully' });
      setDeletingRole(null);
      setRoleRefreshKey((k) => k + 1);
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to remove role',
      });
      setDeletingRole(null);
    } finally {
      setDeleteRoleLoading(false);
    }
  };

  return (
    <section className="flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin Dashboard</h1>

      {/* Tab navigation */}
      <nav aria-label="Admin sections" className="border-b border-gray-200 mb-6">
        <div className="flex gap-0 -mb-px">
          <button
            type="button"
            onClick={() => setActiveTab('environments')}
            className={`min-h-[44px] px-4 py-2 text-sm font-medium border-b-2 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset ${
              activeTab === 'environments'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            aria-selected={activeTab === 'environments'}
            role="tab"
          >
            Environments
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('roles')}
            className={`min-h-[44px] px-4 py-2 text-sm font-medium border-b-2 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset ${
              activeTab === 'roles'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            aria-selected={activeTab === 'roles'}
            role="tab"
          >
            Roles
          </button>
        </div>
      </nav>

      {/* Tab content */}
      <div role="tabpanel">
        {activeTab === 'environments' ? (
          <EnvironmentList
            onEdit={handleEditEnv}
            onDelete={handleDeleteEnv}
            onCreate={handleCreateEnv}
            refreshKey={envRefreshKey}
          />
        ) : (
          <RoleList
            onEdit={handleEditRole}
            onDelete={handleDeleteRole}
            onCreate={handleCreateRole}
            refreshKey={roleRefreshKey}
          />
        )}
      </div>

      {/* Environment form modal */}
      <EnvironmentForm
        isOpen={envFormOpen}
        mode={envFormMode}
        environment={editingEnv}
        onSubmit={handleEnvFormSubmit}
        onClose={() => setEnvFormOpen(false)}
      />

      {/* Role form modal */}
      <RoleForm
        isOpen={roleFormOpen}
        mode={roleFormMode}
        role={editingRole}
        environments={environments}
        onSubmit={handleRoleFormSubmit}
        onClose={() => setRoleFormOpen(false)}
      />

      {/* Delete environment confirmation */}
      <ConfirmDialog
        isOpen={!!deletingEnv}
        title="Delete Environment"
        message="This will permanently delete this environment and all associated documents. This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        loading={deleteEnvLoading}
        onConfirm={confirmDeleteEnv}
        onCancel={() => setDeletingEnv(null)}
        details={
          deletingEnv
            ? [{ label: 'Environment', value: deletingEnv.name }]
            : undefined
        }
      />

      {/* Delete role confirmation */}
      <ConfirmDialog
        isOpen={!!deletingRole}
        title="Remove Role"
        message="This will remove the user's access to this environment."
        confirmLabel="Remove"
        variant="danger"
        loading={deleteRoleLoading}
        onConfirm={confirmDeleteRole}
        onCancel={() => setDeletingRole(null)}
        details={
          deletingRole
            ? [
                { label: 'User', value: deletingRole.user_id },
                { label: 'Role', value: deletingRole.role === 'admin' ? 'Admin' : 'Chat User' },
                { label: 'Environment', value: deletingRole.environment_name || deletingRole.environment_id },
              ]
            : undefined
        }
      />
    </section>
  );
}
