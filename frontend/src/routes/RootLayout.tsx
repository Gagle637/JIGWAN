import { NavLink, Outlet } from 'react-router-dom';

import { cn } from '@/lib/cn';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-3 py-1.5 text-sm',
    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100',
  );

export function RootLayout() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
        <span className="font-semibold text-slate-900">지관</span>
        <nav className="flex gap-1">
          <NavLink to="/" className={navLinkClass} end>
            지도
          </NavLink>
          <NavLink to="/login" className={navLinkClass}>
            로그인
          </NavLink>
          <NavLink to="/signup" className={navLinkClass}>
            회원가입
          </NavLink>
          <NavLink to="/me" className={navLinkClass}>
            마이페이지
          </NavLink>
        </nav>
      </header>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
