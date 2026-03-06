import type { Document } from '../../types';

interface DocumentListProps {
  documents: Document[];
  onDelete?: (documentId: string) => void;
  loading?: boolean;
}

export function DocumentList({ documents, onDelete, loading = false }: DocumentListProps) {
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: Document['processing_status']) => {
    const statusConfig: Record<string, { color: string; text: string }> = {
      pending: { color: 'bg-yellow-100 text-yellow-800', text: 'Processing' },
      processed: { color: 'bg-green-100 text-green-800', text: 'Ready' },
      extraction_failed: { color: 'bg-red-100 text-red-800', text: 'Failed' },
    };

    const config = statusConfig[status] || { color: 'bg-gray-100 text-gray-800', text: status };
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
        {config.text}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
        <p className="mt-2 text-gray-500">Loading documents...</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center" data-testid="empty-state">
        <svg
          className="mx-auto h-12 w-12 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <p className="mt-2 text-gray-500">No documents uploaded yet</p>
        <p className="text-sm text-gray-400">Upload your first document to get started</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden" data-testid="document-list">
      <div className="divide-y divide-gray-200">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="p-4 hover:bg-gray-50 transition-colors"
            data-testid={`document-item-${doc.id}`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <svg
                    className="h-5 w-5 text-gray-400 flex-shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <h3 className="text-sm font-medium text-gray-900 truncate" data-testid="document-filename">
                    {doc.filename}
                  </h3>
                  {getStatusBadge(doc.processing_status)}
                </div>
                
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span data-testid="document-size">{formatFileSize(doc.file_size)}</span>
                  <span data-testid="document-date">{formatDate(doc.upload_date)}</span>
                  {doc.chunk_count !== undefined && (
                    <span data-testid="document-chunks">{doc.chunk_count} chunks</span>
                  )}
                </div>
              </div>

              {onDelete && (
                <button
                  onClick={() => onDelete(doc.id)}
                  className="ml-4 text-gray-400 hover:text-red-600 transition-colors"
                  data-testid={`delete-document-${doc.id}`}
                  aria-label={`Delete ${doc.filename}`}
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
