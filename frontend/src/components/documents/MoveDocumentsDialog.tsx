import { useState, useEffect } from 'react';
import { environmentsApi } from '../../api/environments';
import type { Environment } from '../../types';

interface MoveDocumentsDialogProps {
  open: boolean;
  selectedCount: number;
  currentEnvironmentId?: string;
  onMove: (targetEnvironmentId: string) => void;
  onClose: () => void;
}

export function MoveDocumentsDialog({
  open,
  selectedCount,
  currentEnvironmentId,
  onMove,
  onClose,
}: MoveDocumentsDialogProps) {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [targetEnvId, setTargetEnvId] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setTargetEnvId('');
      environmentsApi.list().then((envs) => {
        setEnvironments(envs.filter((e) => e.id !== currentEnvironmentId));
      });
    }
  }, [open, currentEnvironmentId]);

  if (!open) return null;

  const handleSubmit = () => {
    if (!targetEnvId) return;
    setLoading(true);
    onMove(targetEnvId);
  };

  const targetEnv = environments.find((e) => e.id === targetEnvId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Move {selectedCount} document{selectedCount !== 1 ? 's' : ''}
        </h3>

        <label className="block text-sm font-medium text-gray-700 mb-1">
          Target environment
        </label>
        <select
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={targetEnvId}
          onChange={(e) => setTargetEnvId(e.target.value)}
          disabled={loading}
        >
          <option value="">Select an environment...</option>
          {environments.map((env) => (
            <option key={env.id} value={env.id}>
              {env.name}
            </option>
          ))}
        </select>

        {targetEnv?.description && (
          <p className="mt-2 text-xs text-gray-500">{targetEnv.description}</p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!targetEnvId || loading}
            className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Moving...' : 'Move'}
          </button>
        </div>
      </div>
    </div>
  );
}
