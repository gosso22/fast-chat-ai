import { Modal } from './Modal';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning';
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  /** Additional details to display (e.g., environment name, document count) */
  details?: { label: string; value: string }[];
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
  loading = false,
  details,
}: ConfirmDialogProps) {
  const variantStyles = {
    danger: {
      icon: (
        <svg
          className="h-6 w-6 text-red-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      ),
      iconBg: 'bg-red-100',
      confirmButton:
        'bg-red-600 hover:bg-red-700 focus:ring-red-500 text-white disabled:bg-red-400',
    },
    warning: {
      icon: (
        <svg
          className="h-6 w-6 text-amber-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      ),
      iconBg: 'bg-amber-100',
      confirmButton:
        'bg-amber-600 hover:bg-amber-700 focus:ring-amber-500 text-white disabled:bg-amber-400',
    },
  };

  const styles = variantStyles[variant];

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title={title} ariaDescribedBy="confirm-dialog-description">
      <div className="flex flex-col gap-4">
        {/* Icon and message */}
        <div className="flex items-start gap-4">
          <div
            className={`shrink-0 flex items-center justify-center h-10 w-10 rounded-full ${styles.iconBg}`}
          >
            {styles.icon}
          </div>
          <div className="flex-1">
            <p id="confirm-dialog-description" className="text-sm text-gray-600">
              {message}
            </p>
          </div>
        </div>

        {/* Details list (e.g., environment name, document count) */}
        {details && details.length > 0 && (
          <div className="bg-gray-50 rounded-md p-3 space-y-1">
            {details.map((detail, index) => (
              <div key={index} className="flex justify-between text-sm">
                <span className="text-gray-500">{detail.label}:</span>
                <span className="font-medium text-gray-900">{detail.value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="
              min-h-[44px] px-4 py-2
              text-gray-700 bg-white border border-gray-300
              hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
              rounded-md font-medium text-sm transition-colors
              disabled:opacity-50 disabled:cursor-not-allowed
            "
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`
              min-h-[44px] px-4 py-2
              focus:outline-none focus:ring-2 focus:ring-offset-2
              rounded-md font-medium text-sm transition-colors
              disabled:cursor-not-allowed
              flex items-center justify-center gap-2
              ${styles.confirmButton}
            `}
          >
            {loading && (
              <svg
                className="animate-spin h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            )}
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
