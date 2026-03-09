import { useState, useEffect, useRef, useMemo } from 'react';
import { FileUpload, UploadProgress, DocumentList, MoveDocumentsDialog } from '../components/documents';
import { ConfirmDialog } from '../components/ui';
import { documentsApi } from '../api/documents';
import { useEnvironment } from '../contexts/EnvironmentContext';
import { useUser } from '../contexts/UserContext';
import { useToast } from '../hooks/useToast';
import type { Document } from '../types';

interface UploadState {
  filename: string;
  progress: number;
  status: 'uploading' | 'processing' | 'success' | 'error';
  error?: string;
}

export function DocumentsPage() {
  const { activeEnvironment, activeRole } = useEnvironment();
  const { userId, isGlobalAdmin } = useUser();
  const { addToast } = useToast();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadState, setUploadState] = useState<UploadState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isFirstLoadRef = useRef(true);
  const prevEnvIdRef = useRef<string | null | undefined>(undefined);

  // Selection state for move feature
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showMoveDialog, setShowMoveDialog] = useState(false);

  // Confirm delete state (single or bulk)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; filename: string } | null>(null);
  const [bulkDeleteTarget, setBulkDeleteTarget] = useState<Set<string> | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Search and filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const canManageDocuments = activeRole === 'admin';

  const filteredDocuments = useMemo(() => {
    let result = documents;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(d => d.filename.toLowerCase().includes(q));
    }
    if (statusFilter !== 'all') {
      result = result.filter(d => d.processing_status === statusFilter);
    }
    return result;
  }, [documents, searchQuery, statusFilter]);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const envId = activeEnvironment?.id;
      const docs = envId
        ? await documentsApi.listEnv(envId)
        : await documentsApi.list();
      setDocuments(docs);
      setSelectedIds(new Set());
    } catch (err) {
      setError('Failed to load documents. Please try again.');
      console.error('Error loading documents:', err);
    } finally {
      setLoading(false);
    }
  };

  // Load on mount and reload when environment changes
  useEffect(() => {
    const envId = activeEnvironment?.id ?? null;
    if (isFirstLoadRef.current || prevEnvIdRef.current !== envId) {
      isFirstLoadRef.current = false;
      prevEnvIdRef.current = envId;
      loadDocuments();
    }
  }, [activeEnvironment?.id]);

  const handleUpload = async (file: File) => {
    setUploadState({
      filename: file.name,
      progress: 0,
      status: 'uploading',
    });

    try {
      setUploadState(prev => prev ? { ...prev, progress: 30 } : null);

      const envId = activeEnvironment?.id;
      const uploadedDoc = envId
        ? await documentsApi.uploadToEnv(envId, file, userId!)
        : await documentsApi.upload(file);

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
        if (err?.message?.startsWith('Document processing ended')) {
          throw err;
        }
        console.error('Error polling document status:', err);
      }
    }
  };

  const handleDeleteRequest = (documentId: string) => {
    const doc = documents.find(d => d.id === documentId);
    setDeleteTarget({ id: documentId, filename: doc?.filename || 'this document' });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);

    try {
      const envId = activeEnvironment?.id;
      if (envId) {
        await documentsApi.deleteFromEnv(envId, deleteTarget.id, userId!);
      } else {
        await documentsApi.delete(deleteTarget.id);
      }
      setDocuments(docs => docs.filter(doc => doc.id !== deleteTarget.id));
      setSelectedIds(prev => {
        const next = new Set(prev);
        next.delete(deleteTarget.id);
        return next;
      });
      addToast({ type: 'success', message: `Deleted "${deleteTarget.filename}"` });
    } catch (err) {
      addToast({ type: 'error', message: 'Failed to delete document. Please try again.' });
      console.error('Error deleting document:', err);
    } finally {
      setDeleteLoading(false);
      setDeleteTarget(null);
    }
  };

  const handleBulkDeleteConfirm = async () => {
    if (!bulkDeleteTarget || bulkDeleteTarget.size === 0) return;
    setDeleteLoading(true);

    const ids = Array.from(bulkDeleteTarget);
    const envId = activeEnvironment?.id;
    let successCount = 0;
    let failCount = 0;

    for (const docId of ids) {
      try {
        if (envId) {
          await documentsApi.deleteFromEnv(envId, docId, userId!);
        } else {
          await documentsApi.delete(docId);
        }
        successCount++;
      } catch {
        failCount++;
      }
    }

    if (failCount > 0) {
      addToast({ type: 'error', message: `Failed to delete ${failCount} document${failCount !== 1 ? 's' : ''}` });
      await loadDocuments();
    } else {
      setDocuments(docs => docs.filter(doc => !bulkDeleteTarget.has(doc.id)));
    }
    if (successCount > 0) {
      setSelectedIds(new Set());
      addToast({ type: 'success', message: `Deleted ${successCount} document${successCount !== 1 ? 's' : ''}` });
    }

    setDeleteLoading(false);
    setBulkDeleteTarget(null);
  };

  const handleMoveDocuments = async (targetEnvId: string) => {
    try {
      const result = await documentsApi.moveToEnv(targetEnvId, Array.from(selectedIds), userId!);
      setShowMoveDialog(false);
      setSelectedIds(new Set());
      addToast({ type: 'success', message: result.message });
      await loadDocuments();
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || 'Failed to move documents.';
      addToast({ type: 'error', message: detail });
      console.error('Error moving documents:', err);
    }
  };

  const handleCancelUpload = () => {
    setUploadState(null);
  };

  return (
    <div className="flex-1 p-4 md:p-6 lg:p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Documents</h1>
        {activeEnvironment && (
          <p className="text-sm text-gray-500 mb-6">
            Environment: <span className="font-medium text-gray-700">{activeEnvironment.name}</span>
            {activeRole && (
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full font-medium ${
                activeRole === 'admin'
                  ? 'bg-purple-100 text-purple-700'
                  : 'bg-blue-100 text-blue-700'
              }`}>
                {activeRole === 'admin' ? 'Admin' : 'Read-only'}
              </span>
            )}
          </p>
        )}

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {canManageDocuments && (
          <>
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
          </>
        )}

        {!canManageDocuments && activeEnvironment && (
          <div className="mb-6 p-3 bg-blue-50 border border-blue-200 rounded-md">
            <p className="text-sm text-blue-700">
              You have read-only access to documents in this environment.
            </p>
          </div>
        )}

        {/* Search and filter bar */}
        {documents.length > 0 && (
          <div className="mb-4 flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                type="text"
                placeholder="Search by filename..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="all">All statuses</option>
              <option value="processed">Ready</option>
              <option value="pending">Processing</option>
              <option value="extraction_failed">Failed</option>
            </select>
          </div>
        )}

        {/* Bulk actions toolbar - shown when admin has selected documents */}
        {canManageDocuments && selectedIds.size > 0 && (
          <div className="mb-4 flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-md">
            <span className="text-sm text-blue-800 font-medium">
              {selectedIds.size} document{selectedIds.size !== 1 ? 's' : ''} selected
            </span>
            {isGlobalAdmin && activeEnvironment && (
              <button
                onClick={() => setShowMoveDialog(true)}
                className="px-3 py-1.5 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700"
              >
                Move to environment
              </button>
            )}
            <button
              onClick={() => setBulkDeleteTarget(new Set(selectedIds))}
              className="px-3 py-1.5 text-sm text-white bg-red-600 rounded-md hover:bg-red-700"
            >
              Delete selected
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Clear selection
            </button>
          </div>
        )}

        <DocumentList
          documents={filteredDocuments}
          onDelete={canManageDocuments ? handleDeleteRequest : undefined}
          loading={loading}
          selectable={canManageDocuments}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
        />

        <MoveDocumentsDialog
          open={showMoveDialog}
          selectedCount={selectedIds.size}
          currentEnvironmentId={activeEnvironment?.id}
          onMove={handleMoveDocuments}
          onClose={() => setShowMoveDialog(false)}
        />

        <ConfirmDialog
          isOpen={!!deleteTarget}
          title="Delete document"
          message={`Are you sure you want to delete "${deleteTarget?.filename}"? This will also remove all its chunks and embeddings.`}
          confirmLabel="Delete"
          variant="danger"
          loading={deleteLoading}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />

        <ConfirmDialog
          isOpen={!!bulkDeleteTarget}
          title="Delete documents"
          message={`Are you sure you want to delete ${bulkDeleteTarget?.size ?? 0} selected document${(bulkDeleteTarget?.size ?? 0) !== 1 ? 's' : ''}? This will also remove all their chunks and embeddings.`}
          confirmLabel="Delete all"
          variant="danger"
          loading={deleteLoading}
          onConfirm={handleBulkDeleteConfirm}
          onCancel={() => setBulkDeleteTarget(null)}
        />
      </div>
    </div>
  );
}
