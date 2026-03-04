import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    isOpen: true,
    title: 'Confirm Action',
    message: 'Are you sure you want to proceed?',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders when isOpen is true', () => {
      render(<ConfirmDialog {...defaultProps} />);
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Confirm Action')).toBeInTheDocument();
      expect(screen.getByText('Are you sure you want to proceed?')).toBeInTheDocument();
    });

    it('does not render when isOpen is false', () => {
      render(<ConfirmDialog {...defaultProps} isOpen={false} />);
      
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('renders with default button labels', () => {
      render(<ConfirmDialog {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });

    it('renders with custom button labels', () => {
      render(
        <ConfirmDialog
          {...defaultProps}
          confirmLabel="Delete"
          cancelLabel="Keep"
        />
      );
      
      expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Keep' })).toBeInTheDocument();
    });

    it('renders details when provided', () => {
      const details = [
        { label: 'Environment', value: 'Production' },
        { label: 'Documents', value: '15' },
      ];
      
      render(<ConfirmDialog {...defaultProps} details={details} />);
      
      expect(screen.getByText('Environment:')).toBeInTheDocument();
      expect(screen.getByText('Production')).toBeInTheDocument();
      expect(screen.getByText('Documents:')).toBeInTheDocument();
      expect(screen.getByText('15')).toBeInTheDocument();
    });

    it('renders with aria-describedby for accessibility', () => {
      render(<ConfirmDialog {...defaultProps} />);
      
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-describedby', 'confirm-dialog-description');
      expect(screen.getByText(defaultProps.message)).toHaveAttribute(
        'id',
        'confirm-dialog-description'
      );
    });
  });

  describe('variants', () => {
    it('renders danger variant by default', () => {
      render(<ConfirmDialog {...defaultProps} />);
      
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton).toHaveClass('bg-red-600');
    });

    it('renders warning variant when specified', () => {
      render(<ConfirmDialog {...defaultProps} variant="warning" />);
      
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton).toHaveClass('bg-amber-600');
    });
  });

  describe('confirm action', () => {
    it('calls onConfirm when confirm button is clicked', async () => {
      const user = userEvent.setup();
      render(<ConfirmDialog {...defaultProps} />);
      
      await user.click(screen.getByRole('button', { name: 'Confirm' }));
      
      expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
    });

    it('does not call onCancel when confirm button is clicked', async () => {
      const user = userEvent.setup();
      render(<ConfirmDialog {...defaultProps} />);
      
      await user.click(screen.getByRole('button', { name: 'Confirm' }));
      
      expect(defaultProps.onCancel).not.toHaveBeenCalled();
    });
  });

  describe('cancel action', () => {
    it('calls onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup();
      render(<ConfirmDialog {...defaultProps} />);
      
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      
      expect(defaultProps.onCancel).toHaveBeenCalledTimes(1);
    });

    it('does not call onConfirm when cancel button is clicked', async () => {
      const user = userEvent.setup();
      render(<ConfirmDialog {...defaultProps} />);
      
      await user.click(screen.getByRole('button', { name: 'Cancel' }));
      
      expect(defaultProps.onConfirm).not.toHaveBeenCalled();
    });

    it('calls onCancel when modal close button is clicked', async () => {
      const user = userEvent.setup();
      render(<ConfirmDialog {...defaultProps} />);
      
      await user.click(screen.getByRole('button', { name: /close modal/i }));
      
      expect(defaultProps.onCancel).toHaveBeenCalledTimes(1);
    });

    it('calls onCancel when Escape key is pressed', () => {
      render(<ConfirmDialog {...defaultProps} />);
      
      // Modal handles Escape key and calls onClose (which is onCancel)
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      
      expect(defaultProps.onCancel).toHaveBeenCalledTimes(1);
    });
  });

  describe('loading state', () => {
    it('disables confirm button when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={true} />);
      
      expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    });

    it('disables cancel button when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={true} />);
      
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    });

    it('shows loading spinner in confirm button when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={true} />);
      
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('does not show loading spinner when not loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={false} />);
      
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      expect(confirmButton.querySelector('.animate-spin')).not.toBeInTheDocument();
    });
  });
});
