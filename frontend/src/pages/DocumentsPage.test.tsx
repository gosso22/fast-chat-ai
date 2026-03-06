import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentsPage } from './DocumentsPage';
import { documentsApi } from '../api/documents';
import { UserProvider } from '../contexts/UserContext';
import { EnvironmentProvider } from '../contexts/EnvironmentContext';
import type { Document } from '../types';

vi.mock('../api/documents', () => ({
  documentsApi: {
    list: vi.fn(),
    listEnv: vi.fn(),
    upload: vi.fn(),
    uploadToEnv: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    deleteFromEnv: vi.fn(),
  },
}));

import { usersApi } from '../api/users';

vi.mock('../api/users', () => ({
  usersApi: {
    me: vi.fn().mockResolvedValue({ user_id: 'test_user', is_global_admin: false }),
    myEnvironments: vi.fn().mockResolvedValue([]),
  },
}));

const mockDocuments: Document[] = [
  {
    id: '1',
    filename: 'test.pdf',
    file_size: 1024 * 1024,
    content_type: 'application/pdf',
    upload_date: '2024-01-15T10:00:00Z',
    processing_status: 'processed',
    chunk_count: 5,
  },
];

function renderDocumentsPage() {
  return render(
    <UserProvider>
      <EnvironmentProvider>
        <DocumentsPage />
      </EnvironmentProvider>
    </UserProvider>
  );
}

describe('DocumentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('userId', 'test_user');
    // Reset to default: no environments (non-admin user)
    vi.mocked(usersApi.me).mockResolvedValue({ user_id: 'test_user', is_global_admin: false });
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([]);
  });

  it('renders page title', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    renderDocumentsPage();

    expect(screen.getByText('Documents')).toBeInTheDocument();
  });

  it('loads and displays documents on mount', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(mockDocuments);
    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });

    expect(documentsApi.list).toHaveBeenCalledTimes(1);
  });

  it('shows empty state when no documents', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('handles document upload successfully', async () => {
    // Simulate admin role so upload is visible
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    vi.mocked(documentsApi.listEnv).mockResolvedValue([]);
    vi.mocked(documentsApi.uploadToEnv).mockResolvedValue(mockDocuments[0]);
    vi.mocked(documentsApi.get).mockResolvedValue({ ...mockDocuments[0], processing_status: 'processed' });

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByTestId('file-upload-zone')).toBeInTheDocument();
    });

    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('upload-progress')).toBeInTheDocument();
    });
  });

  it('shows upload progress during upload', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    vi.mocked(documentsApi.listEnv).mockResolvedValue([]);
    vi.mocked(documentsApi.uploadToEnv).mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockDocuments[0]), 100))
    );
    vi.mocked(documentsApi.get).mockResolvedValue({ ...mockDocuments[0], processing_status: 'processed' });

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByTestId('file-upload-zone')).toBeInTheDocument();
    });

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('upload-progress')).toBeInTheDocument();
      expect(screen.getByTestId('upload-filename')).toHaveTextContent('test.pdf');
    });
  });

  it('handles upload error', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    vi.mocked(documentsApi.listEnv).mockResolvedValue([]);
    vi.mocked(documentsApi.uploadToEnv).mockRejectedValue({
      response: { data: { detail: 'Upload failed' } }
    });

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByTestId('file-upload-zone')).toBeInTheDocument();
    });

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('upload-error-message')).toBeInTheDocument();
    });
  });

  it('handles document deletion for admin users', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    vi.mocked(documentsApi.listEnv).mockResolvedValue(mockDocuments);
    vi.mocked(documentsApi.deleteFromEnv).mockResolvedValue();

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });

    const deleteButton = screen.getByTestId('delete-document-1');
    fireEvent.click(deleteButton);

    expect(confirmSpy).toHaveBeenCalled();

    await waitFor(() => {
      expect(documentsApi.deleteFromEnv).toHaveBeenCalledWith('env-1', '1', 'test_user');
    });

    confirmSpy.mockRestore();
  });

  it('hides delete button for non-admin users', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(mockDocuments);

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });

    // Without admin role, delete button should not be present
    expect(screen.queryByTestId('delete-document-1')).not.toBeInTheDocument();
    expect(documentsApi.delete).not.toHaveBeenCalled();
  });

  it('shows error message when loading documents fails', async () => {
    vi.mocked(documentsApi.list).mockRejectedValue(new Error('Network error'));

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByText(/failed to load documents/i)).toBeInTheDocument();
    });
  });

  it('disables upload during active upload', async () => {
    vi.mocked(usersApi.myEnvironments).mockResolvedValue([
      {
        environment: { id: 'env-1', name: 'Test', description: null, system_prompt: null, settings: null, created_by: 'admin', created_at: '', updated_at: '' },
        role: 'admin',
      },
    ]);

    vi.mocked(documentsApi.listEnv).mockResolvedValue([]);
    vi.mocked(documentsApi.uploadToEnv).mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockDocuments[0]), 1000))
    );

    renderDocumentsPage();

    await waitFor(() => {
      expect(screen.getByTestId('file-upload-zone')).toBeInTheDocument();
    });

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('upload-progress')).toBeInTheDocument();
    });

    expect(input).toBeDisabled();
  });
});
