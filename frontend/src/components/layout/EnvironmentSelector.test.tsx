import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { EnvironmentSelector } from './EnvironmentSelector';
import { UserProvider } from '../../contexts/UserContext';
import { EnvironmentProvider } from '../../contexts/EnvironmentContext';
import { usersApi } from '../../api/users';

vi.mock('../../api/users', () => ({
  usersApi: {
    me: vi.fn().mockResolvedValue({ user_id: 'test_user', is_global_admin: false }),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem('userId', 'test_user');
  vi.mocked(usersApi.me).mockResolvedValue({ user_id: 'test_user', is_global_admin: false });
  vi.mocked(usersApi.myEnvironments).mockResolvedValue([]);
});

function renderSelector() {
  return render(
    <UserProvider>
      <EnvironmentProvider>
        <EnvironmentSelector />
      </EnvironmentProvider>
    </UserProvider>
  );
}

describe('EnvironmentSelector', () => {
  it('shows "No environments assigned" when user has no environments', async () => {
    renderSelector();

    await waitFor(() => {
      expect(screen.getByText('No environments assigned')).toBeInTheDocument();
    });
  });

  it('shows environments with role badges', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Production', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
      {
        environment: { id: 'env-2', name: 'Staging', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'chat_user',
      },
    ]);

    renderSelector();

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
    });

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('Production [Admin]');
    expect(options[1]).toHaveTextContent('Staging [User]');
  });

  it('shows role badge for active environment', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test Env', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    renderSelector();

    await waitFor(() => {
      expect(screen.getByText('Admin')).toBeInTheDocument();
    });
  });
});
