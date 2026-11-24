import { createBrowserRouter, RouterProvider } from 'react-router';
import { Shell } from './components/Shell';
import { PortfolioPage } from './pages/PortfolioPage';
import { LaunchPage } from './pages/LaunchPage';
import { ActionsPage } from './pages/ActionsPage';
import { AdvisorPage } from './pages/AdvisorPage';
import { AskPage } from './pages/AskPage';

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: '/', element: <PortfolioPage /> },
      { path: '/launch/:npiId', element: <LaunchPage /> },
      { path: '/actions', element: <ActionsPage /> },
      { path: '/advisor', element: <AdvisorPage /> },
      { path: '/ask', element: <AskPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
