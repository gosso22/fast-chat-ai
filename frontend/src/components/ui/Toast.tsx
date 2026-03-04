import { useEffect, useState, useCallback, type ReactNode } from 'react';

export type ToastType = 'success' | 'error' | 'info';

export interface ToastData {
  id: string;
  type: ToastType;
  message: string;
  duration?: number; // ms, undefined = persistent
}

interface ToastProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
}

const toastStyles: Record<ToastType, { bg: string; icon: ReactNode; iconBg: string }> = {
  success: {
    bg: 'bg-white border-green-200',
    iconBg: 'bg-green-100',
    icon: (
      <svg
        className="h-5 w-5 text-green-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    ),
  },
  error: {
    bg: 'bg-white border-red-200',
    iconBg: 'bg-red-100',
    icon: (
      <svg
        className="h-5 w-5 text-red-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
    ),
  },
  info: {
    bg: 'bg-white border-blue-200',
    iconBg: 'bg-blue-100',
    icon: (
      <svg
        className="h-5 w-5 text-blue-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
  },
};

export function Toast({ toast, onDismiss }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false);
  const styles = toastStyles[toast.type];

  const handleDismiss = useCallback(() => {
    setIsExiting(true);
    // Wait for exit animation before removing
    setTimeout(() => onDismiss(toast.id), 150);
  }, [onDismiss, toast.id]);

  // Auto-dismiss for toasts with duration
  useEffect(() => {
    if (toast.duration) {
      const timer = setTimeout(handleDismiss, toast.duration);
      return () => clearTimeout(timer);
    }
  }, [toast.duration, handleDismiss]);

  return (
    <div
      role="alert"
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
      className={`
        flex items-start gap-3 p-4 rounded-lg shadow-lg border
        transition-all duration-150 ease-out
        ${styles.bg}
        ${isExiting ? 'opacity-0 translate-x-2' : 'opacity-100 translate-x-0'}
      `}
    >
      {/* Icon */}
      <div
        className={`shrink-0 flex items-center justify-center h-8 w-8 rounded-full ${styles.iconBg}`}
      >
        {styles.icon}
      </div>

      {/* Message */}
      <p className="flex-1 text-sm text-gray-700 pt-1">{toast.message}</p>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss notification"
        className="
          shrink-0 min-h-[44px] min-w-[44px] -m-2 p-2
          text-gray-400 hover:text-gray-600
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
          rounded-md transition-colors
        "
      >
        <svg
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}
