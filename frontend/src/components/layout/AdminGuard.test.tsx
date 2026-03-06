import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AdminGuard } from './AdminGuard';
import { UserProvider } from '../../contexts/UserContext';
import { usersApi } from '../../api/users';

vi.mock('../../api/users', () => ({
  usersApi: {
    me: vi.fn(),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWithRouter(isAdmin: boolean) {
  vi.mocked(usersApi.me).mockResolvedValue({
    user_id: 'test_user',
    is_global_admin: isAdmin,
  });
  localStorage.setItem('userId', 'test_user');

  return render(
    <UserProvider>
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/" element={<div>Home Page</div>} />
          <Route
            path="/admin"
            element={
              <AdminGuard>
                <div>Admin Page</div>
              </AdminGuard>
            }
          />
        </Routes>
      </MemoryRouter>
    </UserProvider>
  );
}

describe('AdminGuard', () => {
  it('renders children for global admin users', async () => {
    renderWithRouter(true);

    await waitFor(() => {
      expect(screen.getByText('Admin Page')).toBeInTheDocument();
    });
    expect(screen.queryByText('Home Page')).not.toBeInTheDocument();
  });

  it('redirects non-admin users to home', async () => {
    renderWithRouter(false);

    await waitFor(() => {
      expect(screen.getByText('Home Page')).toBeInTheDocument();
    });
    expect(screen.queryByText('Admin Page')).not.toBeInTheDocument();
  });
});
