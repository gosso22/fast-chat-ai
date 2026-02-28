import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Header } from './Header';

describe('Header', () => {
  it('renders the app title', () => {
    render(
      <BrowserRouter>
        <Header />
      </BrowserRouter>
    );
    expect(screen.getByText('FAST CHAT')).toBeInTheDocument();
  });

  it('renders navigation links', () => {
    render(
      <BrowserRouter>
        <Header />
      </BrowserRouter>
    );
    expect(screen.getByRole('link', { name: /^chat$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /documents/i })).toBeInTheDocument();
  });
});
