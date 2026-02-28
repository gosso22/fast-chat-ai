import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DocumentList } from './DocumentList';
import type { Document } from '../../types';

const mockDocuments: Document[] = [
  {
    id: '1',
    filename: 'test1.pdf',
    file_size: 1024 * 1024, // 1MB
    content_type: 'application/pdf',
    upload_date: '2024-01-15T10:00:00Z',
    processing_status: 'processed',
    chunk_count: 5,
  },
  {
    id: '2',
    filename: 'test2.txt',
    file_size: 2048,
    content_type: 'text/plain',
    upload_date: '2024-01-16T12:00:00Z',
    processing_status: 'pending',
  },
  {
    id: '3',
    filename: 'test3.docx',
    file_size: 5 * 1024 * 1024, // 5MB
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    upload_date: '2024-01-17T14:00:00Z',
    processing_status: 'extraction_failed',
  },
];

describe('DocumentList', () => {
  it('renders empty state when no documents', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[]} onDelete={onDelete} />);
    
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText(/no documents uploaded yet/i)).toBeInTheDocument();
  });

  it('renders loading state', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[]} onDelete={onDelete} loading={true} />);
    
    expect(screen.getByText(/loading documents/i)).toBeInTheDocument();
  });

  it('renders list of documents', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={mockDocuments} onDelete={onDelete} />);
    
    expect(screen.getByTestId('document-list')).toBeInTheDocument();
    expect(screen.getByTestId('document-item-1')).toBeInTheDocument();
    expect(screen.getByTestId('document-item-2')).toBeInTheDocument();
    expect(screen.getByTestId('document-item-3')).toBeInTheDocument();
  });

  it('displays document information correctly', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[mockDocuments[0]]} onDelete={onDelete} />);
    
    expect(screen.getByText('test1.pdf')).toBeInTheDocument();
    expect(screen.getByText('1 MB')).toBeInTheDocument();
    expect(screen.getByText('5 chunks')).toBeInTheDocument();
  });

  it('formats file sizes correctly', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={mockDocuments} onDelete={onDelete} />);
    
    expect(screen.getByText('1 MB')).toBeInTheDocument();
    expect(screen.getByText('2 KB')).toBeInTheDocument();
    expect(screen.getByText('5 MB')).toBeInTheDocument();
  });

  it('displays correct status badges', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={mockDocuments} onDelete={onDelete} />);
    
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('calls onDelete when delete button is clicked', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[mockDocuments[0]]} onDelete={onDelete} />);
    
    const deleteButton = screen.getByTestId('delete-document-1');
    fireEvent.click(deleteButton);
    
    expect(onDelete).toHaveBeenCalledWith('1');
  });

  it('renders delete button for each document', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={mockDocuments} onDelete={onDelete} />);
    
    expect(screen.getByTestId('delete-document-1')).toBeInTheDocument();
    expect(screen.getByTestId('delete-document-2')).toBeInTheDocument();
    expect(screen.getByTestId('delete-document-3')).toBeInTheDocument();
  });

  it('displays chunk count when available', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[mockDocuments[0]]} onDelete={onDelete} />);
    
    expect(screen.getByText('5 chunks')).toBeInTheDocument();
  });

  it('does not display chunk count when not available', () => {
    const onDelete = vi.fn();
    render(<DocumentList documents={[mockDocuments[1]]} onDelete={onDelete} />);
    
    expect(screen.queryByText(/chunks/i)).not.toBeInTheDocument();
  });
});
