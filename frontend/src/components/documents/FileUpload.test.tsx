import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FileUpload } from './FileUpload';

describe('FileUpload', () => {
  it('renders upload zone with correct text', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    expect(screen.getByText(/drag and drop files here/i)).toBeInTheDocument();
    expect(screen.getByText(/supports pdf, txt, docx, and markdown files/i)).toBeInTheDocument();
  });

  it('calls onUpload when valid file is selected', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    
    fireEvent.change(input, { target: { files: [file] } });
    
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it('shows error for oversized file', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    // Create a file larger than 50MB
    const largeFile = new File(['x'.repeat(51 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    
    fireEvent.change(input, { target: { files: [largeFile] } });
    
    expect(screen.getByTestId('upload-error')).toBeInTheDocument();
    expect(screen.getByText(/file size exceeds 50mb limit/i)).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('shows error for invalid file format', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    const invalidFile = new File(['test'], 'test.exe', { type: 'application/x-msdownload' });
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    
    fireEvent.change(input, { target: { files: [invalidFile] } });
    
    expect(screen.getByTestId('upload-error')).toBeInTheDocument();
    expect(screen.getByText(/invalid file format/i)).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('handles drag and drop', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    const dropZone = screen.getByTestId('file-upload-zone');
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });
    
    fireEvent.dragEnter(dropZone, {
      dataTransfer: { files: [file] }
    });
    
    expect(screen.getByText(/drop file here/i)).toBeInTheDocument();
    
    fireEvent.drop(dropZone, {
      dataTransfer: { files: [file] }
    });
    
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it('disables upload when disabled prop is true', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} disabled={true} />);
    
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input).toBeDisabled();
    
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('accepts all supported file formats', () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    
    const formats = [
      { name: 'test.pdf', type: 'application/pdf' },
      { name: 'test.txt', type: 'text/plain' },
      { name: 'test.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
      { name: 'test.md', type: 'text/markdown' },
    ];
    
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    
    formats.forEach(format => {
      const file = new File(['test'], format.name, { type: format.type });
      fireEvent.change(input, { target: { files: [file] } });
      expect(onUpload).toHaveBeenCalledWith(file);
    });
    
    expect(onUpload).toHaveBeenCalledTimes(formats.length);
  });
});
