import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { ToastProvider } from '../ui/ToastProvider';

export function Layout() {
  return (
    <ToastProvider>
      <div className="min-h-screen flex flex-col bg-gray-50">
        <Header />
        <main className="flex-1 flex overflow-hidden">
          <Outlet />
        </main>
      </div>
    </ToastProvider>
  );
}
