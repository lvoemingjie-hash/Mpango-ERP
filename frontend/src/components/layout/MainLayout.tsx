import { useCallback, useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';

/**
 * App shell — Sidebar + Header + scrollable content area.
 * Used by ProtectedRoute children only. Login stays full-screen.
 *
 * PW1-R4-C1 responsive contract:
 *  - MainLayout owns the mobile drawer open/close state.
 *  - Content uses mobile margin-free layout with lg:ml-64 + min-w-0
 *    (no overflow-x-hidden / clip / negative-margin overflow masking).
 *  - Drawer closes on route change, Escape, backdrop and hamburger;
 *    focus returns to the hamburger after close.
 */
export function MainLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  // Route navigation auto-closes the mobile drawer.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location]);

  // Escape closes the drawer and restores focus to the hamburger.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDrawerOpen(false);
        hamburgerRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [drawerOpen]);

  // Shared close path for backdrop/hamburger: focus returns to the hamburger.
  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    hamburgerRef.current?.focus();
  }, []);

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* R4-C1-R1 (F1): the in-flow content column renders BEFORE the fixed
          Sidebar so every always-visible landmark (breadcrumb nav, main)
          precedes the lg-gated desktop <aside> in DOM order. The frozen
          browser harness resolves 'main, nav, aside' with .first(), which
          must land on a visible element at mobile width. The desktop aside,
          mobile backdrop and mobile drawer are position:fixed, so this order
          has zero visual effect at every viewport. */}
      <div className="flex min-w-0 flex-1 flex-col lg:ml-64">
        <Header
          drawerOpen={drawerOpen}
          hamburgerRef={hamburgerRef}
          onToggleDrawer={() => setDrawerOpen((open) => !open)}
        />
        <main className="min-w-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <Sidebar mobileOpen={drawerOpen} onClose={closeDrawer} />
    </div>
  );
}
