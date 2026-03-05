import { useState, useEffect } from 'react';
import { FileUpload, UploadProgress, DocumentList } from '../components/documents';
import { documentsApi } from '../api/documents';
import type { Document } from '../types';

interface UploadState {
  filename: string;
  progress: number;
  status: 'uploading' | 'processing' | 'success' | 'error';
  error?: string;
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadState, setUploadState] = useState<UploadState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const docs = await documentsApi.list();
      setDocuments(docs);
    } catch (err) {
      setError('Failed to load documents. Please try again.');
      console.error('Error loading documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleUpload = async (file: File) => {
    setUploadState({
      filename: file.name,
      progress: 0,
      status: 'uploading',
    });

    try {
      // Simulate upload progress
      setUploadState(prev => prev ? { ...prev, progress: 30 } : null);
      
      const uploadedDoc = await documentsApi.upload(file);
      
      setUploadState(prev => prev ? { ...prev, progress: 60, status: 'processing' } : null);
      
      // Poll for processing completion
      await pollDocumentStatus(uploadedDoc.id);
      
      setUploadState(prev => prev ? { ...prev, progress: 100, status: 'success' } : null);
      
      // Reload documents list
      await loadDocuments();
      
      // Clear upload state after a delay
      setTimeout(() => setUploadState(null), 2000);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Upload failed. Please try again.';
      setUploadState(prev => prev ? {
        ...prev,
        progress: 0,
        status: 'error',
        error: errorMessage,
      } : null);
      
      // Clear error state after delay
      setTimeout(() => setUploadState(null), 5000);
    }
  };

  const TERMINAL_STATUSES = new Set([
    'processed',
    'partially_processed',
    'extraction_failed',
    'embedding_failed',
  ]);

  const pollDocumentStatus = async (documentId: string, maxAttempts = 60): Promise<void> => {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(resolve => setTimeout(resolve, 2000));

      try {
        const doc = await documentsApi.get(documentId);
        if (doc.processing_status && TERMINAL_STATUSES.has(doc.processing_status)) {
          if (doc.processing_status !== 'processed') {
            throw new Error(
              `Document processing ended with status: ${doc.processing_status}`
            );
          }
          return;
        }
      } catch (err: any) {
        // Re-throw terminal-status errors so handleUpload shows them
        if (err?.message?.startsWith('Document processing ended')) {
          throw err;
        }
        console.error('Error polling document status:', err);
      }
    }
  };

  const handleDelete = async (documentId: string) => {
    if (!confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      await documentsApi.delete(documentId);
      setDocuments(docs => docs.filter(doc => doc.id !== documentId));
    } catch (err) {
      alert('Failed to delete document. Please try again.');
      console.error('Error deleting document:', err);
    }
  };

  const handleCancelUpload = () => {
    setUploadState(null);
  };

  return (
    <div className="flex-1 p-4 md:p-6 lg:p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">Documents</h1>
        
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        <div className="mb-6">
          <FileUpload onUpload={handleUpload} disabled={uploadState !== null} />
        </div>

        {uploadState && (
          <UploadProgress
            filename={uploadState.filename}
            progress={uploadState.progress}
            status={uploadState.status}
            error={uploadState.error}
            onCancel={uploadState.status === 'uploading' ? handleCancelUpload : undefined}
          />
        )}

        <DocumentList
          documents={documents}
          onDelete={handleDelete}
          loading={loading}
        />
      </div>
    </div>
  );
}
