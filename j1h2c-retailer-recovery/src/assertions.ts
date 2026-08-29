/**
 * Field-only failure message helper.
 *
 * Every assertion in this harness reports surfaces/fields/categories ONLY.
 * Values (emails, tokens, passwords, codes, URLs with fragments) are never
 * interpolated into failure messages or any artifact.
 */

export function fieldOnly(
  surface: 'ui' | 'http' | 'mail' | 'storage' | 'console' | 'network' | 'artifact' | 'precondition',
  field: string,
  category: string,
): Error {
  return new Error(`assertion:${surface}:${field}:${category}`);
}
