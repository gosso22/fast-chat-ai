interface UploadProgressProps {
  filename: string;
  progress: number;
  status: 'uploading' | 'processing' | 'success' | 'error';
  error?: string;
  onCancel?: () => void;
}

export function UploadProgress({ filename, progress, status, error, onCancel }: UploadProgressProps) {
  const getStatusColor = () => {
    switch (status) {
      case 'uploading':
      case 'processing':
        return 'brand-gradient';
      case 'success':
        return 'bg-green-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'uploading':
        return 'Uploading...';
      case 'processing':
        return 'Processing...';
      case 'success':
        return 'Upload complete';
      case 'error':
        return 'Upload failed';
      default:
        return '';
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4" data-testid="upload-progress">
      <div className="flex items-center justify-between mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate" data-testid="upload-filename">
            {filename}
          </p>
          <p className="text-xs text-gray-500" data-testid="upload-status">
            {getStatusText()}
          </p>
        </div>
        
        {status === 'uploading' && onCancel && (
          <button
            onClick={onCancel}
            className="ml-4 text-gray-400 hover:text-gray-600"
            data-testid="cancel-upload"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full transition-all duration-300 ${getStatusColor()}`}
          style={{ width: `${progress}%` }}
          data-testid="progress-bar"
        />
      </div>

      {error && (
        <p className="mt-2 text-sm text-red-600" data-testid="upload-error-message">
          {error}
        </p>
      )}
    </div>
  );
}
