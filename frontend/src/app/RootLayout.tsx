import { Outlet } from 'react-router-dom';

export function RootLayout() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center border-b border-border px-4 py-2">
        <span className="font-semibold text-foreground">지관</span>
      </header>
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
