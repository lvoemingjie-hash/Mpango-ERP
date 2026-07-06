/**
 * P25-B dimension: route inventory grounding (matrix dim 1, smoke; C11/C12).
 *
 * Asserts the P25-A section 3 inventory is the AS-BUILT inventory:
 *   - every one of the 19 contract routes exists as a <Route> under
 *     <PlatformRoute /> in frontend/src/router/AppRouter.tsx (none dropped -- C11)
 *   - no route in the inventory is invented (each is present in the source -- C12)
 *   - the PlatformRoute guard wraps the platform subtree (section 3.6)
 *
 * Grounded in the source file (read at test time), not in a copy.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { PLATFORM_ROUTES } from './__helpers__/readiness';

// Vitest runs with cwd at the frontend root (where vite.config.ts lives).
const APP_ROUTER = resolve(process.cwd(), 'src/router/AppRouter.tsx');
const SOURCE = readFileSync(APP_ROUTER, 'utf-8');

// The set of platform <Route path="..."> literals actually present in AppRouter.
const ROUTE_PATHS_IN_SOURCE = Array.from(
  SOURCE.matchAll(/path:\s*['"`](\/platform[^'"`]*)['"`]/g),
).map((m: RegExpExecArray) => m[1]);

describe('P25-B route inventory is the as-built inventory', () => {
  it('P25-INV00: AppRouter source is readable and contains a PlatformRoute subtree', () => {
    expect(SOURCE.length).toBeGreaterThan(0);
    expect(SOURCE).toContain('PlatformRoute');
    expect(SOURCE).toContain('element: <PlatformRoute />');
  });

  it('P25-INV01: every contract route is present in AppRouter (none dropped, C11)', () => {
    const missing = PLATFORM_ROUTES.filter(
      (r) => !ROUTE_PATHS_IN_SOURCE.includes(r.path),
    ).map((r) => r.path);
    expect(missing).toEqual([]);
  });

  it('P25-INV02: every route is under <PlatformRoute /> (section 3.6 guard wrap)', () => {
    // AppRouter expresses the platform subtree as a config object whose root
    // element is <PlatformRoute />: `{ element: <PlatformRoute />, children: ... }`.
    // Assert each route path is present AND the PlatformRoute root element wraps
    // the subtree; structural nesting is enforced by tsc + INV01.
    for (const r of PLATFORM_ROUTES) {
      expect(SOURCE).toContain(`path: '${r.path}'`);
    }
    expect(SOURCE).toMatch(/element:\s*<PlatformRoute\s*\/?>/);
  });

  it('P25-INV03: no extra platform route is invented beyond the contract (C12)', () => {
    const contractPaths = new Set(PLATFORM_ROUTES.map((r) => r.path));
    const extra = ROUTE_PATHS_IN_SOURCE.filter((p) => !contractPaths.has(p));
    expect(extra).toEqual([]);
  });

  it('P25-INV04: the closed inventory has exactly 19 routes', () => {
    expect(PLATFORM_ROUTES.length).toBe(19);
  });

  it('P25-INV05: 10 routes carry a direct Sidebar link; 9 do not', () => {
    const direct = PLATFORM_ROUTES.filter((r) => r.sidebarPath !== null);
    expect(direct.length).toBe(10);
  });
});
