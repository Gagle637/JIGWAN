import { createBrowserRouter, Navigate } from 'react-router-dom';

import { LoginPage } from '@/pages/LoginPage';
import { MapPage } from '@/pages/MapPage';
import { MyPage } from '@/pages/MyPage';
import { SignupPage } from '@/pages/SignupPage';

import { RootLayout } from './RootLayout';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <MapPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'signup', element: <SignupPage /> },
      { path: 'me', element: <MyPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
