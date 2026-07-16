import { PaymentHistoryRecord, PaymentHistorySummary, PaymentSortKey } from './types';

const PLAN_LABELS: Record<string, string> = {
  basic: 'Basic',
  premium: 'Premium',
  free: 'Free',
};

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CAD: 'CA$',
  AUD: 'A$',
  INR: '₹',
  BRL: 'R$',
  NGN: '₦',
  KES: 'KSh',
  GHS: 'GH₵',
  ZAR: 'R',
  XOF: 'CFA ',
  XAF: 'CFA ',
  CHF: 'CHF ',
  SEK: 'kr',
  PLN: 'zł',
  TRY: '₺',
  THB: '฿',
  RUB: '₽',
  MXN: 'MX$',
  KRW: '₩',
};

const NO_DECIMAL_CURRENCIES = new Set(['JPY', 'KRW', 'XOF', 'XAF']);

const safeNumber = (value: any): number => {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
};

export const resolvePlanLabel = (planId: string) => PLAN_LABELS[String(planId || '').toLowerCase()] || (planId ? String(planId) : 'Unknown');

export const normalizeGatewayKey = (rawValue: string) => {
  const value = String(rawValue || '').trim().toLowerCase();
  if (value.includes('paypal')) return 'paypal';
  if (value.includes('feda') || value.includes('mobile') || value.includes('kkiapay')) return 'fedapay';
  if (value.includes('stripe') || value.includes('card')) return 'stripe';
  return value || 'unknown';
};

export const providerLabelFromGateway = (gatewayKey: string, fallback = '') => {
  if (gatewayKey === 'paypal') return 'PayPal';
  if (gatewayKey === 'fedapay') return 'FedaPay';
  if (gatewayKey === 'stripe') return 'Stripe';
  return fallback || 'Payment Gateway';
};

export const formatAmount = (amount: number, currency = 'USD') => {
  const code = String(currency || 'USD').toUpperCase();
  const symbol = CURRENCY_SYMBOLS[code] || `${code} `;
  if (NO_DECIMAL_CURRENCIES.has(code)) {
    return `${symbol}${Math.round(amount).toLocaleString()}`;
  }
  return `${symbol}${safeNumber(amount).toFixed(2)}`;
};

export const formatLongDate = (value: string) => {
  try {
    return new Date(value).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return String(value || '—');
  }
};

export const formatShortDate = (value: string) => {
  try {
    return new Date(value).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return String(value || '—');
  }
};

export const formatDateInputValue = (date: Date) => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const normalizeStatus = (rawValue: string) => {
  const value = String(rawValue || '').trim().toLowerCase();
  if (['completed', 'paid', 'succeeded', 'success'].includes(value)) {
    return { status: 'paid', label: 'Paid', rank: 0 };
  }
  if (['initiated', 'pending', 'processing', 'awaiting'].includes(value)) {
    return { status: 'pending', label: 'Pending', rank: 1 };
  }
  if (['failed', 'cancelled', 'canceled', 'expired', 'reversed'].includes(value)) {
    return { status: 'failed', label: 'Failed', rank: 2 };
  }
  return {
    status: value || 'unknown',
    label: value ? value.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase()) : 'Unknown',
    rank: 3,
  };
};

const buildJurisdictionLabel = (row: Record<string, any>) => {
  const jurisdiction = row?.jurisdiction;
  if (!jurisdiction || typeof jurisdiction !== 'object') return '—';
  const country = String(jurisdiction.country || '').trim();
  const state = String(jurisdiction.state || '').trim();
  const postal = String(jurisdiction.postal_code || '').trim();
  return [country, state, postal].filter(Boolean).join(' · ') || '—';
};

const buildSignature = (record: PaymentHistoryRecord) => {
  const createdMinute = String(record.createdAt || '').slice(0, 16);
  return [record.planId, record.gatewayKey, record.currency, record.totalAmount.toFixed(2), createdMinute].join('|');
};

const buildRecord = (row: Record<string, any>, type: 'payment' | 'transaction'): PaymentHistoryRecord => {
  const gatewayKey = normalizeGatewayKey(String(row.gateway_key || row.provider || row.gateway || row.payment_method || ''));
  const statusMeta = normalizeStatus(String(row.status || row.payment_status || 'unknown'));
  const amount = safeNumber(row.amount ?? row.amount_gross ?? row.total_amount ?? 0);
  const totalAmount = safeNumber(row.total_amount ?? row.amount_gross ?? row.amount ?? 0);
  const amountGross = safeNumber((row.amount_gross ?? totalAmount) || amount);
  const taxAmount = safeNumber(row.tax_amount ?? 0);
  const processingFee = safeNumber(row.processing_fee ?? row.fee ?? 0);
  const amountNet = safeNumber(row.amount_net ?? Math.max(totalAmount - processingFee, 0));
  const referenceId = String(row.payment_id || row.transaction_id || row.id || row.session_id || '').trim();
  const documentId = String(row.receipt_document_id || referenceId || row.id || row.session_id || '').trim();
  const planId = String(row.plan_id || '').trim();
  return {
    id: `${type}-${documentId || referenceId || Math.random().toString(36).slice(2)}`,
    type,
    sourceLabel: type === 'payment' ? 'Payments' : 'Transactions',
    referenceId: referenceId || '—',
    documentId: documentId || referenceId,
    createdAt: String(row.created_at || ''),
    planId,
    planLabel: resolvePlanLabel(planId),
    billingPeriod: String(row.billing_period || '').trim(),
    gatewayKey,
    providerDisplayName: String(row.provider_display_name || providerLabelFromGateway(gatewayKey, String(row.provider || row.gateway || ''))),
    paymentMethod: String(row.payment_method || row.provider || row.gateway || 'card'),
    status: statusMeta.status,
    statusLabel: statusMeta.label,
    currency: String(row.currency || 'USD').toUpperCase(),
    amount,
    amountGross,
    totalAmount,
    amountNet,
    taxAmount,
    processingFee,
    taxRate: safeNumber(row.tax_rate ?? 0),
    jurisdictionLabel: buildJurisdictionLabel(row),
    isSuccessful: statusMeta.status === 'paid',
    raw: row,
  };
};

export const buildPaymentHistoryRecords = (payments: Record<string, any>[], transactions: Record<string, any>[]) => {
  const paymentRecords = (payments || []).map((row) => buildRecord(row, 'payment'));
  const paymentSignatures = new Set(paymentRecords.map(buildSignature));
  const transactionRecords = (transactions || [])
    .map((row) => buildRecord(row, 'transaction'))
    .filter((record) => !paymentSignatures.has(buildSignature(record)));

  return [...paymentRecords, ...transactionRecords].sort((left, right) => {
    const leftTime = new Date(left.createdAt).getTime();
    const rightTime = new Date(right.createdAt).getTime();
    return rightTime - leftTime;
  });
};

export const summarizePaymentHistory = (records: PaymentHistoryRecord[], user: Record<string, any> | null | undefined): PaymentHistorySummary => {
  const successful = records.filter((record) => record.isSuccessful);
  const providers = new Set(records.map((record) => record.gatewayKey).filter((value) => value && value !== 'unknown'));
  return {
    totalPaid: successful.reduce((sum, record) => sum + record.totalAmount, 0),
    successfulPayments: successful.length,
    visibleRecords: records.length,
    providerCount: providers.size,
    currentPlanLabel: resolvePlanLabel(String(user?.subscription_plan || 'free')),
    lastSuccessfulPayment: successful[0] || null,
  };
};

export const filterPaymentHistoryRecords = (records: PaymentHistoryRecord[], searchText: string, statusFilter: string) => {
  const normalizedSearch = String(searchText || '').trim().toLowerCase();
  return records.filter((record) => {
    const matchesStatus = statusFilter === 'all' || record.status === statusFilter;
    if (!matchesStatus) return false;
    if (!normalizedSearch) return true;
    const haystack = [
      record.referenceId,
      record.planLabel,
      record.providerDisplayName,
      record.sourceLabel,
      record.billingPeriod,
      record.statusLabel,
      record.currency,
      record.jurisdictionLabel,
      formatAmount(record.totalAmount, record.currency),
    ].join(' ').toLowerCase();
    return haystack.includes(normalizedSearch);
  });
};

export const sortPaymentHistoryRecords = (records: PaymentHistoryRecord[], sortKey: PaymentSortKey, sortDirection: 'asc' | 'desc') => {
  const sorted = [...records].sort((left, right) => {
    if (sortKey === 'amount') return left.totalAmount - right.totalAmount;
    if (sortKey === 'status') return normalizeStatus(left.status).rank - normalizeStatus(right.status).rank;
    if (sortKey === 'gateway') return left.providerDisplayName.localeCompare(right.providerDisplayName);
    return new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime();
  });
  return sortDirection === 'desc' ? sorted.reverse() : sorted;
};
