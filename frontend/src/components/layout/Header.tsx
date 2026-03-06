import { useState } from 'react';
import { Link } from 'react-router-dom';
import { EnvironmentSelector } from './EnvironmentSelector';
import { useUser } from '../../contexts/UserContext';

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { userId, isGlobalAdmin, logout } = useUser();

  const navLinks = [
    { to: '/', label: 'Chat' },
    { to: '/documents', label: 'Documents' },
    ...(isGlobalAdmin ? [{ to: '/admin', label: 'Admin' }] : []),
  ];

  return (
    <header className="bg-white border-b border-gray-200 px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <img src="/logo.svg" alt="Fast Chat" className="h-10 w-10" />
          <span className="text-2xl font-extrabold tracking-wide brand-text-gradient">
            FAST CHAT
          </span>
        </Link>

        {/* Environment selector - desktop */}
        <div className="hidden md:flex items-center">
          <EnvironmentSelector />
        </div>

        {/* Desktop nav + user */}
        <div className="hidden md:flex items-center gap-6">
          <nav className="flex items-center gap-6">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="text-gray-600 hover:text-[#00E5FF] transition-colors font-medium"
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3 pl-4 border-l border-gray-200">
            <span className="text-sm text-gray-500">{userId}</span>
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-red-500 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>

        {/* Mobile hamburger button */}
        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileMenuOpen}
          className="md:hidden min-h-[44px] min-w-[44px] p-2 text-gray-600 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-md"
        >
          {mobileMenuOpen ? (
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile nav menu */}
      {mobileMenuOpen && (
        <nav className="md:hidden mt-3 pt-3 border-t border-gray-200 flex flex-col gap-1">
          {/* Environment selector - mobile */}
          <div className="px-3 py-2">
            <EnvironmentSelector />
          </div>
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              onClick={() => setMobileMenuOpen(false)}
              className="min-h-[44px] flex items-center px-3 py-2 text-gray-600 hover:text-[#00E5FF] hover:bg-gray-50 rounded-md transition-colors font-medium"
            >
              {link.label}
            </Link>
          ))}
          <div className="px-3 py-2 border-t border-gray-200 mt-1 flex items-center justify-between">
            <span className="text-sm text-gray-500">{userId}</span>
            <button
              onClick={() => { logout(); setMobileMenuOpen(false); }}
              className="text-sm text-gray-400 hover:text-red-500 transition-colors"
            >
              Logout
            </button>
          </div>
        </nav>
      )}
    </header>
  );
}
