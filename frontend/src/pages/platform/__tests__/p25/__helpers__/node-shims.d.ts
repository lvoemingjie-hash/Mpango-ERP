/**
 * Minimal ambient node-API shims for the P25-B harness.
 *
 * @types/node is intentionally NOT a frontend dependency (the product bundle is
 * browser-only). Two harness files read source text at test time to ground the
 * route inventory in AppRouter.tsx (P25-INV) and to assert the in-app link
 * graph (D1). vitest provides the real node implementations at runtime; these
 * declarations give tsc the shapes without adding a dependency.
 */
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: string): string;
  export function readdirSync(path: string): string[];
}
declare module 'node:path' {
  export function resolve(...paths: string[]): string;
  export function dirname(p: string): string;
}
declare const process: { cwd(): string };
