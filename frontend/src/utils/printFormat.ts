/**
 * DC-12R1-S3-S2B-I2C-I2 — String-only money & date formatting for print views.
 *
 * BINDING CORRECTION #1: Money values from the server are exact decimal
 * strings (Python `Decimal` serialized as JSON string). They must NEVER be
 * parsed through Number, parseFloat, or Intl.NumberFormat — those would round
 * large amounts (>2^53) and silently alter high-precision values. Instead we
 * insert thousands separators by pure string manipulation, preserving every
 * digit the server returned (including arbitrary decimal places).
 *
 * All functions here are total and defensive: a malformed/empty input is
 * returned essentially unchanged (only safe trimming of stray whitespace) so a
 * bad payload can never produce a NaN or a rounded value.
 */

/**
 * Group the integer part of a decimal string into thousands using commas,
 * leaving the fractional part (and a leading sign) untouched.
 *
 * Example:
 *   "1234567.8900" -> "1,234,567.8900"
 *   "9007199254740993.125" -> "9,007,199,254,740,993.125"  (exact, no rounding)
 *   "0.000001" -> "0.000001"
 *   "-1250.5" -> "-1,250.5"
 */
export function formatDecimalMoney(value: string | null | undefined): string {
  if (value === null || value === undefined) return '';
  // Trim surrounding whitespace only; never alter the numeric content.
  const trimmed = String(value).trim();
  if (trimmed === '') return '';

  // Split sign / integer / fraction without numeric coercion.
  let sign = '';
  let body = trimmed;
  if (body.startsWith('-') || body.startsWith('+')) {
    sign = body.charAt(0);
    body = body.slice(1);
  }

  let integerPart = body;
  let fractionPart = '';
  const dot = body.indexOf('.');
  if (dot !== -1) {
    integerPart = body.slice(0, dot);
    fractionPart = body.slice(dot); // keeps the leading "."
  }

  // Guard: if the integer part isn't decimal digits, return the value as-is
  // (we never want to mangle an unexpected shape into something misleading).
  if (integerPart.length > 0 && !/^\d+$/.test(integerPart)) {
    return trimmed;
  }

  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${sign}${grouped}${fractionPart}`;
}

/**
 * Render a server decimal string as a KES money label, preserving exact
 * precision. "KES " prefix + grouped amount. No rounding, no parsing.
 */
export function formatKes(value: string | null | undefined): string {
  const grouped = formatDecimalMoney(value);
  if (grouped === '') return '';
  return `KES ${grouped}`;
}

/**
 * Format an ISO timestamp for display using only the Date's locale string
 * (display layer only — never used on money). Returns '' for falsy input.
 */
export function formatPrintDate(value: string | null | undefined): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleString('en-KE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}
