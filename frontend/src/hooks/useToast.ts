import { useContext } from 'react';
import { ToastContext, type ToastContextValue } from '../components/ui/ToastProvider';

/**
 * Hook to access toast notification functionality.
 * Must be used within a ToastProvider.
 * 
 * @example
 * const { addToast, removeToast } = useToast();
 * 
 * // Success toast (auto-dismisses after 5s)
 * addToast({ type: 'success', message: 'Environment created successfully' });
 * 
 * // Error toast (persistent until dismissed)
 * addToast({ type: 'error', message: 'Failed to delete environment' });
 * 
 * // Custom duration
 * addToast({ type: 'info', message: 'Processing...', duration: 3000 });
 */
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  
  return context;
}
