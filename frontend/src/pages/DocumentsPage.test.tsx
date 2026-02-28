import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DocumentsPage } from './DocumentsPage';
import { documentsApi } from '../api/documents';
import type { Document } from '../types';

vi.mock('../api/documents', () => ({
  documentsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
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

describe('DocumentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page title', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    render(<DocumentsPage />);
    
    expect(screen.getByText('Documents')).toBeInTheDocument();
  });

  it('loads and displays documents on mount', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(mockDocuments);
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });
    
    expect(documentsApi.list).toHaveBeenCalledTimes(1);
  });

  it('shows empty state when no documents', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('handles document upload successfully', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    vi.mocked(documentsApi.upload).mockResolvedValue(mockDocuments[0]);
    vi.mocked(documentsApi.get).mockResolvedValue({ ...mockDocuments[0], processing_status: 'processed' });
    
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByTestId('file-upload-zone')).toBeInTheDocument();
    });
    
    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    
    fireEvent.change(input, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(screen.getByTestId('upload-progress')).toBeInTheDocument();
    });
    
    expect(documentsApi.upload).toHaveBeenCalledWith(file);
  });

  it('shows upload progress during upload', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    vi.mocked(documentsApi.upload).mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve(mockDocuments[0]), 100))
    );
    vi.mocked(documentsApi.get).mockResolvedValue({ ...mockDocuments[0], processing_status: 'processed' });
    
    render(<DocumentsPage />);
    
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
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    vi.mocked(documentsApi.upload).mockRejectedValue({
      response: { data: { detail: 'Upload failed' } }
    });
    
    render(<DocumentsPage />);
    
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

  it('handles document deletion', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(mockDocuments);
    vi.mocked(documentsApi.delete).mockResolvedValue();
    
    // Mock window.confirm
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });
    
    const deleteButton = screen.getByTestId('delete-document-1');
    fireEvent.click(deleteButton);
    
    expect(confirmSpy).toHaveBeenCalled();
    
    await waitFor(() => {
      expect(documentsApi.delete).toHaveBeenCalledWith('1');
    });
    
    confirmSpy.mockRestore();
  });

  it('cancels deletion when user declines confirmation', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue(mockDocuments);
    
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });
    
    const deleteButton = screen.getByTestId('delete-document-1');
    fireEvent.click(deleteButton);
    
    expect(confirmSpy).toHaveBeenCalled();
    expect(documentsApi.delete).not.toHaveBeenCalled();
    
    confirmSpy.mockRestore();
  });

  it('shows error message when loading documents fails', async () => {
    vi.mocked(documentsApi.list).mockRejectedValue(new Error('Network error'));
    
    render(<DocumentsPage />);
    
    await waitFor(() => {
      expect(screen.getByText(/failed to load documents/i)).toBeInTheDocument();
    });
  });

  it('disables upload during active upload', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue([]);
    vi.mocked(documentsApi.upload).mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve(mockDocuments[0]), 1000))
    );
    
    render(<DocumentsPage />);
    
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
