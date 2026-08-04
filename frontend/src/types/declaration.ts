/** DC-12R1-S3-S2B-I2B: Payment declaration types (retailer + cashier views). */

export type DeclarationStatus = 'pending' | 'confirmed' | 'rejected';
export type DeclarationMethod = 'cash' | 'transfer';

export interface PaymentDeclaration {
  id: string;
  order_id: string;
  declared_amount: string;
  method: DeclarationMethod;
  transfer_reference?: string | null;
  status: DeclarationStatus;
  submitted_at: string;
  confirmed_at?: string | null;
  rejected_at?: string | null;
  reason?: string | null;
  receipt_number?: string | null;
  order_status?: string | null;
}

export interface StatementLine {
  date: string;
  order_id: string;
  amount: string;
  method: string;
  receipt_number?: string | null;
  description: string;
}

export interface DeclarationConfirmResponse {
  id: string;
  order_id: string;
  status: 'confirmed';
  confirmation_payment_id: string;
  receipt_number: string;
  order_status: string;
  confirmed_at: string;
}
