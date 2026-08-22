/**
 * DC-12R1-MVP-L1-J1-H2-A: clipboard copy helper.
 *
 * Returns a boolean instead of throwing so callers can surface a neutral
 * "copy failed" hint without ever embedding the copied credential (e.g. an
 * invitation code) into an error message or console output.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Swallowed deliberately: never log or rethrow clipboard failures that
    // could carry the copied credential in an error payload.
  }
  return false;
}
