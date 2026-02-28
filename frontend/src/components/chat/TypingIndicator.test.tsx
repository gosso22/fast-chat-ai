import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TypingIndicator } from './TypingIndicator';

describe('TypingIndicator', () => {
  it('renders typing indicator with assistant label', () => {
    render(<TypingIndicator />);
    expect(screen.getByText('Assistant')).toBeInTheDocument();
  });

  it('renders three animated dots', () => {
    const { container } = render(<TypingIndicator />);
    const dots = container.querySelectorAll('.animate-bounce');
    expect(dots).toHaveLength(3);
  });
});
