/**
 * Sanitized assertion discipline (task directives #9, #14).
 *
 * Playwright's built-in expect() prints expected/received values on failure.
 * For anything that could carry a secret (URLs with fragments, response
 * bodies, storage values, passwords, tokens), tests MUST use assertSan with a
 * pre-written message that names the field only. expect() is reserved for
 * pure-DOM checks against fixed product strings.
 */
export function assertSan(
  condition: boolean,
  sanitizedMessage: string,
): asserts condition {
  if (!condition) {
    throw new Error(sanitizedMessage);
  }
}
