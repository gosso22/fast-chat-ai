import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from './LoginPage';
import { UserProvider } from '../contexts/UserContext';
import { usersApi } from '../api/users';

vi.mock('../api/users', () => ({
  usersApi: {
    me: vi.fn(),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

function renderLoginPage() {
  return render(
    <UserProvider>
      <LoginPage />
    </UserProvider>
  );
}

describe('LoginPage', () => {
  it('renders login form with user ID input', () => {
    renderLoginPage();

    expect(screen.getByText('FAST CHAT')).toBeInTheDocument();
    expect(screen.getByLabelText('User ID')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('disables submit button when input is empty', () => {
    renderLoginPage();

    expect(screen.getByRole('button', { name: /sign in/i })).toBeDisabled();
  });

  it('enables submit button when input has text', async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText('User ID'), 'test_user');
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled();
  });

  it('calls login on form submit', async () => {
    const user = userEvent.setup();
    vi.mocked(usersApi.me).mockResolvedValue({
      user_id: 'test_user',
      is_global_admin: false,
    });

    renderLoginPage();

    await user.type(screen.getByLabelText('User ID'), 'test_user');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(usersApi.me).toHaveBeenCalled();
    });
  });

  it('shows error message on login failure', async () => {
    const user = userEvent.setup();
    vi.mocked(usersApi.me).mockRejectedValue(new Error('Network error'));

    renderLoginPage();

    await user.type(screen.getByLabelText('User ID'), 'bad_user');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });
});
