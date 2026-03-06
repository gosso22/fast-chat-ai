import { useState, useEffect, type FormEvent } from 'react';
import type { Environment, EnvironmentCreate, EnvironmentUpdate } from '../../types';
import { Modal } from '../ui/Modal';

interface EnvironmentFormProps {
  mode: 'create' | 'edit';
  environment?: Environment;
  onSubmit: (data: EnvironmentCreate | EnvironmentUpdate) => Promise<void>;
  onClose: () => void;
  isOpen: boolean;
}

export function EnvironmentForm({ mode, environment, onSubmit, onClose, isOpen }: EnvironmentFormProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [errors, setErrors] = useState<{ name?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (mode === 'edit' && environment) {
        setName(environment.name);
        setDescription(environment.description || '');
        setSystemPrompt(environment.system_prompt || '');
      } else {
        setName('');
        setDescription('');
        setSystemPrompt('');
      }
      setErrors({});
      setServerError(null);
      setSubmitting(false);
    }
  }, [isOpen, mode, environment]);

  const validate = (): boolean => {
    const newErrors: { name?: string } = {};
    const trimmed = name.trim();
    if (!trimmed) {
      newErrors.name = 'Name is required';
    } else if (trimmed.length > 255) {
      newErrors.name = 'Name must be 1-255 characters';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setServerError(null);
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || undefined,
        system_prompt: systemPrompt.trim() || undefined,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      if (message.toLowerCase().includes('already exists') || message.includes('409')) {
        setErrors({ name: 'Environment name already exists' });
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
      title={mode === 'create' ? 'Create Environment' : 'Edit Environment'}
    >
      <form onSubmit={handleSubmit} noValidate>
        <div className="space-y-4">
          <div>
            <label htmlFor="env-name" className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              id="env-name"
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (errors.name) setErrors({});
              }}
              maxLength={255}
              required
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? 'env-name-error' : undefined}
              className={`h-11 w-full px-3 rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.name ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.name && (
              <p id="env-name-error" className="mt-1 text-sm text-red-600" role="alert">
                {errors.name}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="env-description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="env-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-md border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label htmlFor="env-system-prompt" className="block text-sm font-medium text-gray-700 mb-1">
              System Prompt
            </label>
            <p className="text-xs text-gray-500 mb-1">
              Instructions that define the chatbot's behavior, tone, and personality for this environment.
            </p>
            <textarea
              id="env-system-prompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={5}
              placeholder="e.g., You are a friendly support agent for Acme Corp. Always be concise and reference documentation when possible."
              className="w-full px-3 py-2 rounded-md border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
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
            {mode === 'create' ? 'Create' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
