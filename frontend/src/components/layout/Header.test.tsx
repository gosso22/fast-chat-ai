import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Header } from './Header';
import { UserProvider } from '../../contexts/UserContext';
import { EnvironmentProvider } from '../../contexts/EnvironmentContext';

vi.mock('../../api/users', () => ({
  usersApi: {
    me: vi.fn().mockResolvedValue({ user_id: 'test_user', is_global_admin: false }),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

beforeEach(() => {
  localStorage.setItem('userId', 'test_user');
});

function renderHeader() {
  return render(
    <UserProvider>
      <EnvironmentProvider>
        <BrowserRouter>
          <Header />
        </BrowserRouter>
      </EnvironmentProvider>
    </UserProvider>
  );
}

describe('Header', () => {
  it('renders the app title', async () => {
    renderHeader();
    expect(screen.getByText('FAST CHAT')).toBeInTheDocument();
  });

  it('renders navigation links', async () => {
    renderHeader();
    expect(screen.getByRole('link', { name: /^chat$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /documents/i })).toBeInTheDocument();
  });

  it('hides admin link for non-admin users', async () => {
    renderHeader();
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument();
  });
});
