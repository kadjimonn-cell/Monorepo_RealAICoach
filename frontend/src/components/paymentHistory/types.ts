export type PaymentSourceType = 'payment' | 'transaction';

export type PaymentHistoryRecord = {
  id: string;
  type: PaymentSourceType;
  sourceLabel: string;
  referenceId: string;
  documentId: string;
  createdAt: string;
  planId: string;
  planLabel: string;
  billingPeriod: string;
  gatewayKey: string;
  providerDisplayName: string;
  paymentMethod: string;
  status: string;
  statusLabel: string;
  currency: string;
  amount: number;
  amountGross: number;
  totalAmount: number;
  amountNet: number;
  taxAmount: number;
  processingFee: number;
  taxRate: number;
  jurisdictionLabel: string;
  isSuccessful: boolean;
  raw: Record<string, any>;
};

export type PaymentHistorySummary = {
  totalPaid: number;
  successfulPayments: number;
  visibleRecords: number;
  providerCount: number;
  currentPlanLabel: string;
  lastSuccessfulPayment: PaymentHistoryRecord | null;
};

export type PaymentReportPreferences = {
  weekly_enabled: boolean;
  monthly_enabled: boolean;
  renewal_reminders: boolean;
};

export type PaymentSortKey = 'date' | 'amount' | 'status' | 'gateway';
