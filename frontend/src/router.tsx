import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/layout';
import { ChatPage, DocumentsPage } from './pages';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        index: true,
        element: <ChatPage />,
      },
      {
        path: 'chat',
        element: <ChatPage />,
      },
      {
        path: 'documents',
        element: <DocumentsPage />,
      },
    ],
  },
]);
