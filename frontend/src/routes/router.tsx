import { createBrowserRouter, Navigate } from 'react-router-dom'
import RootLayout from './RootLayout'
import MapPage from '../pages/MapPage'
import LoginPage from '../pages/LoginPage'
import SignupPage from '../pages/SignupPage'
import MyPage from '../pages/MyPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <MapPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'signup', element: <SignupPage /> },
      { path: 'me', element: <MyPage /> },
      // 없는 경로는 지도 화면으로 보낸다. /me 보호 처리는 인증 단계에서 한다.
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
