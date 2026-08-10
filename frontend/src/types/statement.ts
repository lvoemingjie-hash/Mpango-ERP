/**
 * DC-12R1-S3-S2B-I2C-I2B — Contract D relationship account statement view model.
 *
 * Mirrors backend/schemas/print.py (StatementPrintView + nested views)
 * FIELD-FOR-FIELD. Money is typed as `string` because the backend serializes
 * Python `Decimal` as a JSON string; the frontend renders these verbatim
 * (string-only grouping; never Number/parseFloat/Intl parsing — see
 * utils/printFormat.ts). No client financial arithmetic ever occurs.
 */

/** A single receivable ledger movement (signed: +charge / -collection). */
export interface StatementMovementView {
  movement_id: string;
  date: string;
  date_eat: string;
  /** Signed amount: +charge / -collection (KES) as a decimal string. */
  signed_amount: string;
  description: string | null;
  reference_type: string;
  reference_id: string;
}

/** A canonical completed settlement (independent list; never cross-associated). */
export interface StatementSettledPaymentView {
  payment_id: string;
  date: string;
  date_eat: string;
  order_id: string;
  amount: string;
  method: string;
  receipt_number: string | null;
}

/** A non-accounting pending/rejected declaration (only when requested). */
export interface StatementPendingDeclarationView {
  declaration_id: string;
  order_id: string;
  declared_amount: string;
  method: string;
  status: string;
  submitted_at: string;
  submitted_at_eat: string;
  transfer_reference: string | null;
}

/** Contract D — printable relationship account statement. */
export interface StatementPrintView {
  document_type: string;
  supplier_name: string;
  retailer_name: string;
  period_from: string;
  period_to: string;
  /** Receivable sum strictly before the period (KES) as a decimal string. */
  opening_balance: string;
  /** opening + net_movement (KES) as a decimal string. */
  closing_balance: string;
  /** Sum of positive movements (KES) as a decimal string. */
  charge_total: string;
  /** Absolute sum of negative movements (KES) as a decimal string. */
  collection_total: string;
  /** charge - collection, signed (KES) as a decimal string. */
  net_movement: string;
  movements: StatementMovementView[];
  settled_payments: StatementSettledPaymentView[];
  pending_declarations: StatementPendingDeclarationView[];
  generated_at: string;
  generated_at_eat: string;
}
