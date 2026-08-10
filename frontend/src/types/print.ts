/**
 * DC-12R1-S3-S2B-I2C-I2 — Printable record view models (Contracts A–C).
 *
 * Mirrors backend/schemas/print.py (I2C-I1) FIELD-FOR-FIELD. These are
 * read-only views; the browser never recomputes, sums, or rounds any value.
 *
 * Money is typed as `string` because the backend serializes Python `Decimal`
 * as a JSON string. The frontend renders these verbatim (string-only grouping
 * for thousands; never Number/parseFloat/Intl parsing — see
 * utils/printFormat.ts). This preserves exact server-authoritative precision
 * for large and high-precision amounts.
 *
 * Timestamps are typed as `string` (ISO-8601 from the server). Each authoritative
 * UTC timestamp has a paired `*_eat` server-derived Africa/Nairobi display value.
 *
 * Truth contract (I2C-D/R2 + I2C-I2 binding corrections):
 *   - No money is parsed, rounded, or recomputed in the browser.
 *   - A pending/rejected declaration is NEVER a receipt. Only the dedicated
 *     /receipt endpoints (Contract C) expose receipt content.
 *   - No internal identifiers (payment row UUID, cashier user id,
 *     tenant_user_id) are present in these views.
 */

/** Contract A — single line item on a printable order document. */
export interface PrintOrderItemView {
  product_name: string;
  sku_code: string;
  quantity: number;
  /** Server-authoritative unit price (KES) as a decimal string. */
  unit_price: string;
  /** Server-authoritative line subtotal (KES) as a decimal string. */
  subtotal: string;
}

/** Contract A — printable order document (server-authoritative). */
export interface OrderPrintView {
  /** Document discriminator; server sends "order". */
  document_type: string;
  order_id: string;
  /** Client-mapped order status. */
  status: string;
  supplier_name: string;
  retailer_name: string;
  items: PrintOrderItemView[];
  /** Server-authoritative order total (KES) as a decimal string. */
  total_amount: string;
  item_count: number;
  notes: string | null;
  /** Authoritative UTC creation timestamp. */
  created_at: string;
  /** Fixed Africa/Nairobi (EAT) display timestamp. */
  created_at_eat: string;
}

/** Contract B — printable payment declaration document. */
export interface DeclarationPrintView {
  /** Document discriminator; server sends "payment_declaration". */
  document_type: string;
  declaration_id: string;
  order_id: string;
  supplier_name: string;
  retailer_name: string;
  /** Declaration status: pending | confirmed | rejected. */
  status: string;
  /** Declared amount (KES) as a decimal string. */
  declared_amount: string;
  /** Declared method: cash | transfer. */
  method: string;
  transfer_reference: string | null;
  /** True ONLY when receipt eligibility passes. Pending/rejected → false. */
  is_receipt: boolean;
  /** Prominent notice for pending/rejected (verbatim; contains "NOT A RECEIPT"). */
  non_receipt_notice: string | null;
  /** Sanitized rejection reason (rejected only). */
  rejection_reason: string | null;
  /** Authoritative UTC submission timestamp. */
  submitted_at: string;
  /** Fixed Africa/Nairobi (EAT) display timestamp. */
  submitted_at_eat: string;
  confirmed_at: string | null;
  confirmed_at_eat: string | null;
  rejected_at: string | null;
  rejected_at_eat: string | null;
  /** Client-mapped order status. */
  order_status: string | null;
}

/** Contract C — confirmed receipt (receipt-eligible only). */
export interface ReceiptPrintView {
  /** Document discriminator; server sends "receipt". */
  document_type: string;
  declaration_id: string;
  order_id: string;
  supplier_name: string;
  retailer_name: string;
  /** Canonical receipt number RCT-YYYYMMDD-NNNNNN. */
  receipt_number: string;
  /** Confirmed/settled amount (KES) as a decimal string. */
  confirmed_amount: string;
  /** Payment method: cash | transfer. */
  method: string;
  /** Authoritative UTC confirmation timestamp. */
  confirmed_at: string;
  /** Fixed Africa/Nairobi (EAT) display timestamp. */
  confirmed_at_eat: string;
  /** Originally declared amount (KES) as a decimal string. */
  declared_amount: string;
  /** Client-mapped order status. */
  order_status: string | null;
  /** Server-authoritative order total (KES) as a decimal string. */
  order_total_amount: string | null;
}
