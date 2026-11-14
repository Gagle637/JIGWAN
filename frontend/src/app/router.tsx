import { createBrowserRouter, Navigate } from 'react-router-dom';

import { MapPage } from '@/pages/MapPage';

import { RootLayout } from './RootLayout';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <MapPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
