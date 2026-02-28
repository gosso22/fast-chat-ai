import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UploadProgress } from './UploadProgress';

describe('UploadProgress', () => {
  it('renders filename and progress', () => {
    render(
      <UploadProgress
        filename="test.pdf"
        progress={50}
        status="uploading"
      />
    );
    
    expect(screen.getByTestId('upload-filename')).toHaveTextContent('test.pdf');
    expect(screen.getByTestId('upload-status')).toHaveTextContent('Uploading...');
    
    const progressBar = screen.getByTestId('progress-bar');
    expect(progressBar).toHaveStyle({ width: '50%' });
  });

  it('shows correct status text for each status', () => {
    const statuses: Array<{ status: 'uploading' | 'processing' | 'success' | 'error', text: string }> = [
      { status: 'uploading', text: 'Uploading...' },
      { status: 'processing', text: 'Processing...' },
      { status: 'success', text: 'Upload complete' },
      { status: 'error', text: 'Upload failed' },
    ];
    
    statuses.forEach(({ status, text }) => {
      const { rerender } = render(
        <UploadProgress
          filename="test.pdf"
          progress={50}
          status={status}
        />
      );
      
      expect(screen.getByTestId('upload-status')).toHaveTextContent(text);
      
      rerender(<div />);
    });
  });

  it('displays error message when provided', () => {
    render(
      <UploadProgress
        filename="test.pdf"
        progress={0}
        status="error"
        error="Upload failed due to network error"
      />
    );
    
    expect(screen.getByTestId('upload-error-message')).toHaveTextContent('Upload failed due to network error');
  });

  it('shows cancel button only during upload', () => {
    const onCancel = vi.fn();
    
    const { rerender } = render(
      <UploadProgress
        filename="test.pdf"
        progress={30}
        status="uploading"
        onCancel={onCancel}
      />
    );
    
    expect(screen.getByTestId('cancel-upload')).toBeInTheDocument();
    
    rerender(
      <UploadProgress
        filename="test.pdf"
        progress={100}
        status="success"
        onCancel={onCancel}
      />
    );
    
    expect(screen.queryByTestId('cancel-upload')).not.toBeInTheDocument();
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(
      <UploadProgress
        filename="test.pdf"
        progress={30}
        status="uploading"
        onCancel={onCancel}
      />
    );
    
    fireEvent.click(screen.getByTestId('cancel-upload'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('applies correct color for each status', () => {
    const statuses: Array<{ status: 'uploading' | 'processing' | 'success' | 'error', color: string }> = [
      { status: 'uploading', color: 'bg-blue-500' },
      { status: 'processing', color: 'bg-blue-500' },
      { status: 'success', color: 'bg-green-500' },
      { status: 'error', color: 'bg-red-500' },
    ];
    
    statuses.forEach(({ status, color }) => {
      const { rerender } = render(
        <UploadProgress
          filename="test.pdf"
          progress={50}
          status={status}
        />
      );
      
      const progressBar = screen.getByTestId('progress-bar');
      expect(progressBar).toHaveClass(color);
      
      rerender(<div />);
    });
  });
});
