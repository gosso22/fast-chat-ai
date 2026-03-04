import { createContext, useCallback, useState, type ReactNode } from 'react';
import { Toast, type ToastData, type ToastType } from './Toast';

// Default durations
const DEFAULT_SUCCESS_DURATION = 5000; // 5 seconds
const DEFAULT_INFO_DURATION = 5000; // 5 seconds
// Error toasts are persistent (no duration)

export interface ToastContextValue {
  toasts: ToastData[];
  addToast: (toast: Omit<ToastData, 'id'>) => void;
  removeToast: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

interface ToastProviderProps {
  children: ReactNode;
}

let toastIdCounter = 0;

function generateToastId(): string {
  return `toast-${++toastIdCounter}-${Date.now()}`;
}

function getDefaultDuration(type: ToastType): number | undefined {
  switch (type) {
    case 'success':
      return DEFAULT_SUCCESS_DURATION;
    case 'info':
      return DEFAULT_INFO_DURATION;
    case 'error':
      return undefined; // Persistent
    default:
      return DEFAULT_SUCCESS_DURATION;
  }
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const addToast = useCallback((toast: Omit<ToastData, 'id'>) => {
    const id = generateToastId();
    const duration = toast.duration ?? getDefaultDuration(toast.type);
    
    setToasts((prev) => [...prev, { ...toast, id, duration }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      
      {/* Toast container - responsive positioning */}
      {/* Mobile: bottom center, Desktop: top right */}
      <div
        aria-label="Notifications"
        className="
          fixed z-50 pointer-events-none
          inset-x-0 bottom-0 p-4
          md:inset-auto md:top-4 md:right-4 md:bottom-auto md:left-auto
          flex flex-col gap-2
          items-center md:items-end
        "
      >
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto w-full max-w-sm">
            <Toast toast={toast} onDismiss={removeToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
