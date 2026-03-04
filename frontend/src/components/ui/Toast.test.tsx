import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Toast, type ToastData } from './Toast';
import { ToastProvider, ToastContext, type ToastContextValue } from './ToastProvider';
import { useContext } from 'react';

describe('Toast', () => {
  const defaultToast: ToastData = {
    id: 'toast-1',
    type: 'success',
    message: 'Operation successful',
    duration: undefined,
  };

  const onDismiss = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('rendering', () => {
    it('renders success toast with correct styling', () => {
      render(<Toast toast={defaultToast} onDismiss={onDismiss} />);
      
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Operation successful')).toBeInTheDocument();
    });

    it('renders error toast with correct styling', () => {
      const errorToast: ToastData = {
        ...defaultToast,
        type: 'error',
        message: 'Something went wrong',
      };
      
      render(<Toast toast={errorToast} onDismiss={onDismiss} />);
      
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('border-red-200');
    });

    it('renders info toast with correct styling', () => {
      const infoToast: ToastData = {
        ...defaultToast,
        type: 'info',
        message: 'Information message',
      };
      
      render(<Toast toast={infoToast} onDismiss={onDismiss} />);
      
      const alert = screen.getByRole('alert');
      expect(alert).toHaveClass('border-blue-200');
    });

    it('has correct aria-live attribute for error toasts', () => {
      const errorToast: ToastData = {
        ...defaultToast,
        type: 'error',
      };
      
      render(<Toast toast={errorToast} onDismiss={onDismiss} />);
      
      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive');
    });

    it('has correct aria-live attribute for success toasts', () => {
      render(<Toast toast={defaultToast} onDismiss={onDismiss} />);
      
      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'polite');
    });

    it('renders dismiss button with accessible label', () => {
      render(<Toast toast={defaultToast} onDismiss={onDismiss} />);
      
      expect(
        screen.getByRole('button', { name: /dismiss notification/i })
      ).toBeInTheDocument();
    });
  });

  describe('auto-dismiss', () => {
    it('auto-dismisses after specified duration', () => {
      const toastWithDuration: ToastData = {
        ...defaultToast,
        duration: 5000,
      };
      
      render(<Toast toast={toastWithDuration} onDismiss={onDismiss} />);
      
      expect(onDismiss).not.toHaveBeenCalled();
      
      // Advance past the duration
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      
      // Wait for exit animation (150ms)
      act(() => {
        vi.advanceTimersByTime(150);
      });
      
      expect(onDismiss).toHaveBeenCalledWith('toast-1');
    });

    it('does not auto-dismiss when duration is undefined', () => {
      render(<Toast toast={defaultToast} onDismiss={onDismiss} />);
      
      // Advance time significantly
      act(() => {
        vi.advanceTimersByTime(60000);
      });
      
      expect(onDismiss).not.toHaveBeenCalled();
    });

    it('clears timeout on unmount', () => {
      const toastWithDuration: ToastData = {
        ...defaultToast,
        duration: 5000,
      };
      
      const { unmount } = render(
        <Toast toast={toastWithDuration} onDismiss={onDismiss} />
      );
      
      unmount();
      
      // Advance past the duration
      act(() => {
        vi.advanceTimersByTime(5150);
      });
      
      expect(onDismiss).not.toHaveBeenCalled();
    });
  });

  describe('manual dismiss', () => {
    it('calls onDismiss when dismiss button is clicked', async () => {
      vi.useRealTimers();
      const user = userEvent.setup();
      
      render(<Toast toast={defaultToast} onDismiss={onDismiss} />);
      
      await user.click(
        screen.getByRole('button', { name: /dismiss notification/i })
      );
      
      // Wait for exit animation
      await new Promise((resolve) => setTimeout(resolve, 200));
      
      expect(onDismiss).toHaveBeenCalledWith('toast-1');
    });
  });
});

describe('ToastProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // Helper component to access toast context
  function TestConsumer({ onMount }: { onMount: (ctx: ToastContextValue | null) => void }) {
    const context = useContext(ToastContext);
    onMount(context);
    return null;
  }

  it('provides toast context to children', () => {
    let contextValue = null as ToastContextValue | null;
    
    render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue).not.toBeNull();
    expect(contextValue).toHaveProperty('toasts');
    expect(contextValue).toHaveProperty('addToast');
    expect(contextValue).toHaveProperty('removeToast');
  });

  it('adds toast with generated id', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'success', message: 'Test message' });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts).toHaveLength(1);
    expect(contextValue!.toasts[0]).toMatchObject({
      type: 'success',
      message: 'Test message',
    });
    expect(contextValue!.toasts[0].id).toMatch(/^toast-/);
  });

  it('applies default duration for success toasts (5000ms)', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'success', message: 'Success' });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts[0].duration).toBe(5000);
  });

  it('applies default duration for info toasts (5000ms)', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'info', message: 'Info' });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts[0].duration).toBe(5000);
  });

  it('error toasts are persistent (no duration)', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'error', message: 'Error' });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts[0].duration).toBeUndefined();
  });

  it('allows custom duration override', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'success', message: 'Custom', duration: 3000 });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts[0].duration).toBe(3000);
  });

  it('removes toast by id', () => {
    let contextValue = null as ToastContextValue | null;
    
    const { rerender } = render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'success', message: 'Toast 1' });
      contextValue!.addToast({ type: 'error', message: 'Toast 2' });
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    const toastId = contextValue!.toasts[0].id;
    
    act(() => {
      contextValue!.removeToast(toastId!);
    });
    
    rerender(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    expect(contextValue!.toasts).toHaveLength(1);
    expect(contextValue!.toasts[0].message).toBe('Toast 2');
  });

  it('renders toast container with correct positioning classes', () => {
    render(
      <ToastProvider>
        <div>App content</div>
      </ToastProvider>
    );
    
    const container = screen.getByLabelText('Notifications');
    expect(container).toHaveClass('fixed', 'z-50');
    // Mobile: bottom center
    expect(container).toHaveClass('bottom-0');
    // Desktop: top right (md: classes)
    expect(container).toHaveClass('md:top-4', 'md:right-4');
  });

  it('renders multiple toasts', () => {
    let contextValue = null as ToastContextValue | null;
    
    render(
      <ToastProvider>
        <TestConsumer onMount={(ctx) => { contextValue = ctx; }} />
      </ToastProvider>
    );
    
    act(() => {
      contextValue!.addToast({ type: 'success', message: 'First toast' });
      contextValue!.addToast({ type: 'error', message: 'Second toast' });
      contextValue!.addToast({ type: 'info', message: 'Third toast' });
    });
    
    expect(screen.getByText('First toast')).toBeInTheDocument();
    expect(screen.getByText('Second toast')).toBeInTheDocument();
    expect(screen.getByText('Third toast')).toBeInTheDocument();
  });
});
