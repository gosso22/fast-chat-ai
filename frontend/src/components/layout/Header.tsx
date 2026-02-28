import { Link } from 'react-router-dom';

export function Header() {
  return (
    <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
      <Link to="/" className="flex items-center gap-3 group">
        <img src="/logo.svg" alt="Fast Chat" className="h-10 w-10" />
        <span className="text-2xl font-extrabold tracking-wide brand-text-gradient">
          FAST CHAT
        </span>
      </Link>
      <nav className="flex items-center gap-6">
        <Link
          to="/"
          className="text-gray-600 hover:text-[#00E5FF] transition-colors font-medium"
        >
          Chat
        </Link>
        <Link
          to="/documents"
          className="text-gray-600 hover:text-[#00E5FF] transition-colors font-medium"
        >
          Documents
        </Link>
      </nav>
    </header>
  );
}
