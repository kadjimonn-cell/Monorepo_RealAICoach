import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { ActivityIndicator, Alert, Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

function makeT(AC: any) { return {
  card: AC.card,
  bgSoft: AC.surfaceHover,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  warning: AC.warning,
  error: AC.error,
}; }

// Module-scope fallback for ConfigBadge/MetricPill/Row helpers (they're defined at module
// scope and reference T directly; without this they crash with `T is not defined`).
const T = {
  card: 'var(--app-card-bg)', bgSoft: 'var(--app-card-muted)', border: 'var(--app-border)',
  text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)',
};

interface IapProviderSummary {
  provider: string;
  total_transactions: number;
  completed: number;
  pending: number;
  refunded: number;
  reconciliation_rate: number;
  total_revenue: number;
  tax_compliance_rate: number;
  ledger_coverage: number;
  status: string;
}

interface IapTransaction {
  transaction_id: string;
  provider: string;
  amount: number;
  currency: string;
  status: string;
  tax_amount: number;
  created_at: string;
  user_id: string;
}

interface IapDashboardData {
  window_hours: number;
  generated_at: string;
  apple: IapProviderSummary;
  google: IapProviderSummary;
  combined: {
    total_transactions: number;
    total_revenue: number;
    overall_reconciliation_rate: number;
  };
  recent_transactions: IapTransaction[];
  config: {
    apple_configured: boolean;
    google_configured: boolean;
  };
}

interface TaxExplainabilityData {
  transaction_id: string;
  explainability: {
    subtotal: number;
    tax: {
      amount: number;
      rate: number;
      rate_display: string;
      rule: string;
      rule_detail: string;
      breakdown: Record<string, number | string>;
      jurisdiction: { country: string; state: string };
    };
    processing_fee: {
      amount: number;
      provider: string;
      policy: string;
    };
    gross_amount: number;
    gross_formula: string;
    net_amount: number;
    net_formula: string;
    currency: string;
    product_type: string;
  };
  ledger: {
    recorded: boolean;
    sequence: number | null;
    entry_hash: string | null;
  };
  metadata: {
    provider: string;
    plan: string;
    billing_period: string;
    created_at: string;
  };
}

const tx = (_key: string, fallback: string) => fallback;

const WINDOWS = [24, 168, 720];

const statusColor = (status: string) => {
  if (status === 'healthy') return T.success;
  if (status === 'warning') return T.warning;
  return T.error;
};

const normalizeId = (value: string) => value.replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();

const formatAmount = (amount: number, currency: string) => {
  const amountNum = Number.isFinite(amount) ? amount : 0;
  return `${currency || 'USD'} ${amountNum.toFixed(2)}`;
};

const parseErrorMessage = (error: unknown, fallback: string) => {
  const errorAny = error as { response?: { data?: { detail?: string } } };
  return errorAny?.response?.data?.detail || fallback;
};

const csvCell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;

const rowsToCsv = (rows: (string | number)[][]) => rows.map((row) => row.map(csvCell).join(',')).join('\n');

const buildFinanceAuditCsv = (dashboard: IapDashboardData, explainability: TaxExplainabilityData | null) => {
  const summaryRows: (string | number)[][] = [
    ['section', 'provider', 'total_transactions', 'completed', 'pending', 'refunded', 'reconciliation_rate', 'total_revenue', 'tax_compliance_rate', 'ledger_coverage', 'status'],
    ['summary', dashboard.apple.provider, dashboard.apple.total_transactions, dashboard.apple.completed, dashboard.apple.pending, dashboard.apple.refunded, dashboard.apple.reconciliation_rate, dashboard.apple.total_revenue, dashboard.apple.tax_compliance_rate, dashboard.apple.ledger_coverage, dashboard.apple.status],
    ['summary', dashboard.google.provider, dashboard.google.total_transactions, dashboard.google.completed, dashboard.google.pending, dashboard.google.refunded, dashboard.google.reconciliation_rate, dashboard.google.total_revenue, dashboard.google.tax_compliance_rate, dashboard.google.ledger_coverage, dashboard.google.status],
    ['summary', 'Combined', dashboard.combined.total_transactions, dashboard.apple.completed + dashboard.google.completed, dashboard.apple.pending + dashboard.google.pending, dashboard.apple.refunded + dashboard.google.refunded, dashboard.combined.overall_reconciliation_rate, dashboard.combined.total_revenue, '', '', ''],
  ];

  const transactionRows: (string | number)[][] = [
    ['section', 'transaction_id', 'provider', 'status', 'amount', 'currency', 'tax_amount', 'user_id', 'created_at'],
    ...dashboard.recent_transactions.map((tx) => [
      'recent_transaction',
      tx.transaction_id,
      tx.provider,
      tx.status,
      Number(tx.amount || 0),
      tx.currency,
      Number(tx.tax_amount || 0),
      tx.user_id,
      tx.created_at,
    ]),
  ];

  const explainRows: (string | number)[][] = [
    ['section', 'transaction_id', 'tax_rule', 'tax_rate', 'tax_amount', 'subtotal', 'gross_amount', 'net_amount', 'jurisdiction', 'ledger_recorded', 'ledger_sequence', 'entry_hash'],
  ];

  if (explainability) {
    explainRows.push([
      'tax_explainability',
      explainability.transaction_id,
      explainability.explainability.tax.rule,
      explainability.explainability.tax.rate_display,
      explainability.explainability.tax.amount,
      explainability.explainability.subtotal,
      explainability.explainability.gross_amount,
      explainability.explainability.net_amount,
      `${explainability.explainability.tax.jurisdiction.country || '--'}-${explainability.explainability.tax.jurisdiction.state || '--'}`,
      explainability.ledger.recorded ? 'yes' : 'no',
      explainability.ledger.sequence ?? '',
      explainability.ledger.entry_hash ?? '',
    ]);
  } else {
    explainRows.push(['tax_explainability', 'N/A', 'No explainability transaction selected in this snapshot', '', '', '', '', '', '', '', '', '']);
  }

  return [
    rowsToCsv([
      ['report_name', 'Finance Integrity Audit Export'],
      ['generated_at', dashboard.generated_at],
      ['window_hours', dashboard.window_hours],
    ]),
    rowsToCsv(summaryRows),
    rowsToCsv(transactionRows),
    rowsToCsv(explainRows),
  ].join('\n\n');
};

const buildShareContent = (dashboard: IapDashboardData, explainability: TaxExplainabilityData | null) => {
  const breakdown = explainability?.explainability?.tax?.breakdown || {};
  return JSON.stringify(
    {
      report: 'Platform Finance Integrity Snapshot',
      generated_at: dashboard.generated_at,
      window_hours: dashboard.window_hours,
      combined_metrics: dashboard.combined,
      provider_metrics: {
        apple: dashboard.apple,
        google: dashboard.google,
      },
      recent_transactions: dashboard.recent_transactions,
      tax_explainability: explainability || null,
      tax_breakdown_keys: Object.keys(breakdown),
    },
    null,
    2,
  );
};

export default function PlatformFinanceIntegrityPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { user } = useAuth();
  const [windowHours, setWindowHours] = useState(168);
  const [dashboard, setDashboard] = useState<IapDashboardData | null>(null);
  const [emailServiceAvailable, setEmailServiceAvailable] = useState<boolean | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState('');
  const [exportingCsv, setExportingCsv] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [auditActionError, setAuditActionError] = useState('');
  const [auditShareLink, setAuditShareLink] = useState('');
  const [auditShareExpiresAt, setAuditShareExpiresAt] = useState('');

  const [transactionInput, setTransactionInput] = useState('');
  const [explainability, setExplainability] = useState<TaxExplainabilityData | null>(null);
  const [explainabilityLoading, setExplainabilityLoading] = useState(false);
  const [explainabilityError, setExplainabilityError] = useState('');

  const loadIapDashboard = useCallback(async (hours: number) => {
    setDashboardLoading(true);
    setDashboardError('');
    try {
      const { data } = await api.get('/admin/platform-health/iap-reconciliation', { params: { window_hours: hours } });
      setDashboard(data as IapDashboardData);
    } catch (error) {
      setDashboardError(parseErrorMessage(error, 'Unable to load IAP reconciliation data.'));
    }
    setDashboardLoading(false);
  }, []);

  useEffect(() => {
    loadIapDashboard(windowHours);
  }, [windowHours, loadIapDashboard]);

  useEffect(() => {
    let mounted = true;
    const loadGatewayConfig = async () => {
      try {
        const { data } = await api.get('/subscriptions/gateway-config');
        if (!mounted) return;
        const available = typeof data?.email_service_available === 'boolean' ? Boolean(data?.email_service_available) : null;
        setEmailServiceAvailable(available);
      } catch {
        if (mounted) setEmailServiceAvailable(null);
      }
    };
    loadGatewayConfig();
    return () => { mounted = false; };
  }, []);

  const loadExplainability = useCallback(async (transactionId: string) => {
    const cleanId = transactionId.trim();
    if (!cleanId || cleanId === 'N/A') {
      setExplainabilityError('Please provide a valid transaction ID.');
      setExplainability(null);
      return;
    }

    setExplainabilityLoading(true);
    setExplainabilityError('');
    try {
      const { data } = await api.get(`/admin/platform-health/tax-explainability/${encodeURIComponent(cleanId)}`);
      setExplainability(data as TaxExplainabilityData);
      setTransactionInput(cleanId);
    } catch (error) {
      setExplainability(null);
      setExplainabilityError(parseErrorMessage(error, `No explainability data found for ${cleanId}.`));
    }
    setExplainabilityLoading(false);
  }, []);

  const summaryCards = useMemo(() => {
    const combined = dashboard?.combined;
    const generatedAt = dashboard?.generated_at
      ? new Date(dashboard.generated_at).toLocaleString()
      : 'N/A';
    return [
      {
        key: 'total-transactions',
        label: 'IAP Transactions',
        value: String(combined?.total_transactions ?? 0),
        color: T.primary,
        icon: 'swap-horizontal',
      },
      {
        key: 'total-revenue',
        label: 'IAP Revenue',
        value: formatAmount(combined?.total_revenue ?? 0, 'USD'),
        color: T.successText,
        icon: 'cash',
      },
      {
        key: 'overall-reconciliation-rate',
        label: 'Reconciliation Rate',
        value: `${Number(combined?.overall_reconciliation_rate ?? 0).toFixed(1)}%`,
        color: Number(combined?.overall_reconciliation_rate ?? 0) >= 90 ? T.success : T.warning,
        icon: 'shield-checkmark',
      },
      {
        key: 'generated-at',
        label: 'Generated At',
        value: generatedAt,
        color: T.textSec,
        icon: 'time',
      },
    ];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard]);

  const providerCards = useMemo(() => [dashboard?.apple, dashboard?.google].filter(Boolean) as IapProviderSummary[], [dashboard]);

  const resolveExplainabilityForAudit = useCallback(async (): Promise<TaxExplainabilityData | null> => {
    if (explainability) return explainability;

    const candidates = [
      transactionInput.trim(),
      ...(dashboard?.recent_transactions || []).map((tx) => String(tx.transaction_id || '').trim()),
    ].filter((id) => id && id !== 'N/A' && id !== 'unknown');

    for (const txId of candidates) {
      try {
        const { data } = await api.get(`/admin/platform-health/tax-explainability/${encodeURIComponent(txId)}`);
        const resolved = data as TaxExplainabilityData;
        setExplainability(resolved);
        setTransactionInput(txId);
        return resolved;
      } catch {
        continue;
      }
    }
    return null;
  }, [explainability, transactionInput, dashboard?.recent_transactions]);

  const handleExportCsv = useCallback(async () => {
    if (!dashboard) {
      setAuditActionError('Load the IAP dashboard first before exporting CSV.');
      return;
    }

    setExportingCsv(true);
    setAuditActionError('');
    try {
      const explainData = await resolveExplainabilityForAudit();
      const csv = buildFinanceAuditCsv(dashboard, explainData);
      const filename = `finance-integrity-audit-${windowHours}h-${Date.now()}.csv`;

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      } else {
        Alert.alert(
          tx('admin.platformFinanceIntegrityPanel.auto.alert.csvReady', 'CSV Ready'),
          tx('admin.platformFinanceIntegrityPanel.auto.alert.csvReadyMessage', 'CSV export is available in the web admin console.')
        );
      }
    } catch (error) {
      setAuditActionError(parseErrorMessage(error, 'Failed to export finance audit CSV.'));
    }
    setExportingCsv(false);
  }, [dashboard, resolveExplainabilityForAudit, windowHours]);

  const handleCreateShareLink = useCallback(async () => {
    if (!dashboard) {
      setAuditActionError('Load the IAP dashboard first before generating a share link.');
      return;
    }

    setShareLoading(true);
    setAuditActionError('');
    try {
      const explainData = await resolveExplainabilityForAudit();
      const { data } = await api.post('/share/create', {
        user_id: user?.user_id || 'admin-audit-system',
        feature_key: 'platform_finance_integrity_audit',
        title: `Finance Audit Snapshot (${windowHours}h)` ,
        content: buildShareContent(dashboard, explainData),
        expires_in_hours: 168,
      });

      const token = data?.token;
      if (!token) throw new Error('Missing share token response');

      const origin = (Platform.OS === 'web' && typeof window !== 'undefined')
        ? window.location.origin
        : String(process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
      const link = `${origin.replace(/\/$/, '')}/shared/${token}`;

      setAuditShareLink(link);
      setAuditShareExpiresAt(data?.expires_at || '');

      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(link);
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformFinanceIntegrityPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
    } catch (error) {
      setAuditActionError(parseErrorMessage(error, 'Failed to create finance audit share link.'));
    }
    setShareLoading(false);
  }, [dashboard, resolveExplainabilityForAudit, user?.user_id, windowHours]);

  return (
    <View style={{ marginTop: 18 }} data-testid="platform-finance-integrity-panel" testID="platform-finance-integrity-panel">
      <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 14 }} data-testid="platform-finance-integrity-header" testID="platform-finance-integrity-header">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 32, height: 32, borderRadius: 9, backgroundColor: `${T.primary}20`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="card" size={14} color={T.primary} />
            </View>
            <View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: T.text }} data-testid="platform-finance-integrity-title" testID="platform-finance-integrity-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.001', 'IAP Reconciliation + Tax Explainability')}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted }} data-testid="platform-finance-integrity-subtitle" testID="platform-finance-integrity-subtitle">{tx('admin.platformFinanceIntegrityPanel.auto.text.002', 'Single-pane audit trail for Apple/Google IAP and tax formula transparency.')}</Text>
            </View>
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={handleExportCsv}
              disabled={!dashboard || exportingCsv}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primary, borderRadius: 9, paddingHorizontal: 11, paddingVertical: 7, opacity: !dashboard || exportingCsv ? 0.6 : 1 }}
              data-testid="iap-export-csv-button" testID="iap-export-csv-button"
            >
              {exportingCsv ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="download-outline" size={13} color={T.primary} />}
              <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{exportingCsv ? 'Exporting...' : 'Export CSV'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={handleCreateShareLink}
              disabled={!dashboard || shareLoading}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.indigoSoft, borderWidth: 1, borderColor: colors.purpleText, borderRadius: 9, paddingHorizontal: 11, paddingVertical: 7, opacity: !dashboard || shareLoading ? 0.6 : 1 }}
              data-testid="iap-create-share-link-button" testID="iap-create-share-link-button"
            >
              {shareLoading ? <ActivityIndicator size="small" color={colors.purpleText} /> : <Ionicons name="share-social-outline" size={13} color={colors.purpleText} />}
              <Text style={{ color: colors.purpleText, fontSize: 11, fontWeight: '700' }}>{shareLoading ? 'Creating...' : 'Create Share Link'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => loadIapDashboard(windowHours)}
              disabled={dashboardLoading}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 7 }}
              data-testid="iap-reconciliation-refresh-button" testID="iap-reconciliation-refresh-button"
            >
              <Ionicons name="refresh" size={13} color={T.textSec} />
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{dashboardLoading ? 'Refreshing...' : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 6, marginTop: 12, flexWrap: 'wrap' }} data-testid="iap-window-hours-selector" testID="iap-window-hours-selector">
          {WINDOWS.map((hours) => {
            const active = windowHours === hours;
            return (
              <TouchableOpacity
                key={hours}
                onPress={() => setWindowHours(hours)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? `${T.primary}70` : T.border, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: active ? `${T.primary}22` : T.bgSoft }}
                data-testid={`iap-window-hours-${hours}-button`} testID={`iap-window-hours-${hours}-button`}
              >
                <Text style={{ color: active ? T.primary : T.textMuted, fontSize: 10, fontWeight: '800' }}>{hours}h window</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' }} data-testid="iap-provider-config-status-row" testID="iap-provider-config-status-row">
          <ConfigBadge label="Apple IAP" configured={Boolean(dashboard?.config?.apple_configured)} testId="iap-provider-apple-config-status" />
          <ConfigBadge label="Google Play" configured={Boolean(dashboard?.config?.google_configured)} testId="iap-provider-google-config-status" />
        </View>

        {emailServiceAvailable === false ? (
          <View
            style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: `${T.warning}66`, backgroundColor: colors.warningSoft, padding: 10 }}
            data-testid="admin-email-service-warning-banner" testID="admin-email-service-warning-banner"
          >
            <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }} data-testid="admin-email-service-warning-title" testID="admin-email-service-warning-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.003', 'Email delivery service is not configured')}</Text>
            <Text style={{ color: T.textSec, fontSize: 10, marginTop: 4 }} data-testid="admin-email-service-warning-message" testID="admin-email-service-warning-message">{tx('admin.platformFinanceIntegrityPanel.auto.text.004', 'Receipt and alert emails are paused. In-app payment confirmations and admin in-app alerts continue to run.')}</Text>
          </View>
        ) : null}

        {auditShareLink ? (
          <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.indigoSoft, backgroundColor: colors.indigoSoft, padding: 10 }} data-testid="iap-audit-share-link-card" testID="iap-audit-share-link-card">
            <Text style={{ color: colors.indigoText, fontSize: 11, fontWeight: '800' }} data-testid="iap-audit-share-link-title" testID="iap-audit-share-link-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.005', 'Audit link generated (public, read-only · expires in 7 days)')}</Text>
            <Text style={{ color: colors.indigoText, fontSize: 10, marginTop: 6 }} selectable data-testid="iap-audit-share-link-url" testID="iap-audit-share-link-url">{auditShareLink}</Text>
            <Text style={{ color: colors.indigoText, fontSize: 10, marginTop: 4 }} data-testid="iap-audit-share-link-expiry" testID="iap-audit-share-link-expiry">Expires: {auditShareExpiresAt ? new Date(auditShareExpiresAt).toLocaleString() : 'N/A'}</Text>

            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity accessibilityLabel={tx('admin.platformFinanceIntegrityPanel.auto.accessibility.001', 'Copy audit share link')}
                onPress={async () => {
                  if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(auditShareLink);
                  }
                }}
                style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.indigoSoft, backgroundColor: colors.indigoSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                data-testid="iap-audit-share-link-copy-button" testID="iap-audit-share-link-copy-button"
              >
                <Text style={{ color: colors.indigoText, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformFinanceIntegrityPanel.auto.text.006', 'Copy Link')}</Text>
              </TouchableOpacity>

              <TouchableOpacity accessibilityLabel={tx('admin.platformFinanceIntegrityPanel.auto.accessibility.002', 'Open audit share link')}
                onPress={() => {
                  if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(auditShareLink, '_blank');
                }}
                style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.indigoSoft, backgroundColor: colors.indigoSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                data-testid="iap-audit-share-link-open-button" testID="iap-audit-share-link-open-button"
              >
                <Text style={{ color: colors.indigoText, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformFinanceIntegrityPanel.auto.text.007', 'Open Link')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        {dashboardError ? (
          <View style={{ marginTop: 10, borderRadius: 10, backgroundColor: `${T.error}15`, borderWidth: 1, borderColor: `${T.error}55`, padding: 10 }} data-testid="iap-reconciliation-error-banner" testID="iap-reconciliation-error-banner">
            <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }} data-testid="iap-reconciliation-error-message" testID="iap-reconciliation-error-message">{dashboardError}</Text>
          </View>
        ) : null}

        {auditActionError ? (
          <View style={{ marginTop: 10, borderRadius: 10, backgroundColor: `${T.error}15`, borderWidth: 1, borderColor: `${T.error}55`, padding: 10 }} data-testid="iap-audit-actions-error-banner" testID="iap-audit-actions-error-banner">
            <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }} data-testid="iap-audit-actions-error-message" testID="iap-audit-actions-error-message">{auditActionError}</Text>
          </View>
        ) : null}
      </View>

      {dashboardLoading && !dashboard ? (
        <View style={{ paddingVertical: 22, alignItems: 'center' }} data-testid="iap-reconciliation-loading" testID="iap-reconciliation-loading">
          <ActivityIndicator size="small" color={T.primary} />
          <Text style={{ color: T.textSec, marginTop: 8, fontSize: 11 }} data-testid="iap-reconciliation-loading-text" testID="iap-reconciliation-loading-text">{tx('admin.platformFinanceIntegrityPanel.auto.text.008', 'Loading reconciliation metrics...')}</Text>
        </View>
      ) : null}

      {dashboard ? (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }} data-testid="iap-reconciliation-summary-cards" testID="iap-reconciliation-summary-cards">
            {summaryCards.map((card) => (
              <View key={card.key} style={{ flex: 1, minWidth: 180, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid={`iap-reconciliation-summary-${card.key}`} testID={`iap-reconciliation-summary-${card.key}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={card.icon as any} size={12} color={card.color} />
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
                </View>
                <Text style={{ color: card.color, fontSize: 16, fontWeight: '900', marginTop: 6 }} data-testid={`iap-reconciliation-summary-${card.key}-value`} testID={`iap-reconciliation-summary-${card.key}-value`}>{card.value}</Text>
              </View>
            ))}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }} data-testid="iap-provider-summary-cards" testID="iap-provider-summary-cards">
            {providerCards.map((provider) => {
              const providerSlug = normalizeId(provider.provider || 'provider');
              const indicatorColor = statusColor(provider.status);
              return (
                <View key={providerSlug} style={{ flex: 1, minWidth: 250, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`iap-provider-${providerSlug}-card`} testID={`iap-provider-${providerSlug}-card`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }} data-testid={`iap-provider-${providerSlug}-name`} testID={`iap-provider-${providerSlug}-name`}>{provider.provider}</Text>
                    <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: `${indicatorColor}22` }} data-testid={`iap-provider-${providerSlug}-status`} testID={`iap-provider-${providerSlug}-status`}>
                      <Text style={{ color: indicatorColor, fontSize: 9, fontWeight: '800' }}>{provider.status}</Text>
                    </View>
                  </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                    <MetricPill label="Completed" value={String(provider.completed)} valueColor={T.success} testId={`iap-provider-${providerSlug}-completed`} />
                    <MetricPill label="Pending" value={String(provider.pending)} valueColor={T.warning} testId={`iap-provider-${providerSlug}-pending`} />
                    <MetricPill label="Refunded" value={String(provider.refunded)} valueColor={T.error} testId={`iap-provider-${providerSlug}-refunded`} />
                    <MetricPill label="Tax Compliance" value={`${provider.tax_compliance_rate}%`} valueColor={provider.tax_compliance_rate >= 95 ? T.success : T.warning} testId={`iap-provider-${providerSlug}-tax-compliance`} />
                    <MetricPill label="Ledger Coverage" value={`${provider.ledger_coverage}%`} valueColor={provider.ledger_coverage >= 95 ? T.success : T.warning} testId={`iap-provider-${providerSlug}-ledger-coverage`} />
                    <MetricPill label="Revenue" value={formatAmount(provider.total_revenue, 'USD')} valueColor={T.textSec} testId={`iap-provider-${providerSlug}-revenue`} />
                  </View>
                </View>
              );
            })}
          </View>

          <View style={{ marginTop: 12, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid="iap-recent-transactions-panel" testID="iap-recent-transactions-panel">
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }} data-testid="iap-recent-transactions-title" testID="iap-recent-transactions-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.009', 'Recent IAP Transactions')}</Text>

            {dashboard.recent_transactions.length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="iap-recent-transactions-empty" testID="iap-recent-transactions-empty">{tx('admin.platformFinanceIntegrityPanel.auto.text.010', 'No IAP transactions found in this window.')}</Text>
            ) : (
              <View style={{ gap: 8 }} data-testid="iap-recent-transactions-list" testID="iap-recent-transactions-list">
                {dashboard.recent_transactions.map((tx, index) => {
                  const txId = tx.transaction_id || 'unknown';
                  const txSlug = normalizeId(txId || `row-${index}`);
                  const canExplain = txId !== 'N/A' && txId !== 'unknown';
                  return (
                    <View key={`${txId}-${index}`} style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid={`iap-transaction-${txSlug}-row`} testID={`iap-transaction-${txSlug}-row`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: T.text, fontSize: 11, fontWeight: '800' }} data-testid={`iap-transaction-${txSlug}-id`} testID={`iap-transaction-${txSlug}-id`}>{txId}</Text>
                          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid={`iap-transaction-${txSlug}-meta`} testID={`iap-transaction-${txSlug}-meta`}>
                            {tx.provider} · {formatAmount(Number(tx.amount || 0), tx.currency)} · Tax {formatAmount(Number(tx.tax_amount || 0), tx.currency)}
                          </Text>
                          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid={`iap-transaction-${txSlug}-created-at`} testID={`iap-transaction-${txSlug}-created-at`}>
                            {tx.created_at ? new Date(tx.created_at).toLocaleString() : 'Unknown timestamp'}
                          </Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => loadExplainability(txId)}
                          disabled={!canExplain || explainabilityLoading}
                          style={{ borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: canExplain ? `${T.primary}55` : T.border, backgroundColor: canExplain ? `${T.primary}20` : `${T.textMuted}18` }}
                          data-testid={`iap-transaction-${txSlug}-explain-button`} testID={`iap-transaction-${txSlug}-explain-button`}
                        >
                          <Text style={{ color: canExplain ? T.primary : T.textMuted, fontSize: 10, fontWeight: '800' }}>{tx('admin.platformFinanceIntegrityPanel.auto.text.011', 'Explain Tax')}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        </>
      ) : null}

      <View style={{ marginTop: 12, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid="tax-explainability-panel" testID="tax-explainability-panel">
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }} data-testid="tax-explainability-title" testID="tax-explainability-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.012', 'Tax Explainability Inspector')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }} data-testid="tax-explainability-subtitle" testID="tax-explainability-subtitle">{tx('admin.platformFinanceIntegrityPanel.auto.text.013', 'Inspect the exact tax rule, formula, and ledger evidence for a transaction.')}</Text>

        <View style={{ marginTop: 10, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <TextInput
            value={transactionInput}
            onChangeText={setTransactionInput}
            placeholder={tx('admin.platformFinanceIntegrityPanel.auto.placeholder.001', 'Enter transaction ID')}
            placeholderTextColor={T.textMuted}
            style={{
              flex: 1,
              minWidth: 220,
              borderWidth: 1,
              borderColor: T.border,
              borderRadius: 9,
              backgroundColor: T.bgSoft,
              color: T.text,
              paddingHorizontal: 10,
              paddingVertical: 8,
              fontSize: 11,
              outlineStyle: 'none',
            } as any}
            autoCapitalize="none"
            data-testid="tax-explainability-transaction-input" testID="tax-explainability-transaction-input"
          />
          <TouchableOpacity
            onPress={() => loadExplainability(transactionInput)}
            disabled={explainabilityLoading}
            style={{ borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: explainabilityLoading ? `${T.primary}55` : T.primary }}
            data-testid="tax-explainability-run-button" testID="tax-explainability-run-button"
          >
            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{explainabilityLoading ? 'Loading...' : 'Analyze'}</Text>
          </TouchableOpacity>
        </View>

        {explainabilityError ? (
          <View style={{ marginTop: 10, borderRadius: 10, backgroundColor: `${T.error}15`, borderWidth: 1, borderColor: `${T.error}55`, padding: 10 }} data-testid="tax-explainability-error-banner" testID="tax-explainability-error-banner">
            <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }} data-testid="tax-explainability-error-message" testID="tax-explainability-error-message">{explainabilityError}</Text>
          </View>
        ) : null}

        {explainabilityLoading ? (
          <View style={{ marginTop: 12, alignItems: 'center' }} data-testid="tax-explainability-loading" testID="tax-explainability-loading">
            <ActivityIndicator size="small" color={T.primary} />
            <Text style={{ color: T.textSec, marginTop: 6, fontSize: 11 }} data-testid="tax-explainability-loading-text" testID="tax-explainability-loading-text">{tx('admin.platformFinanceIntegrityPanel.auto.text.014', 'Building tax formula overlay...')}</Text>
          </View>
        ) : null}

        {explainability ? (
          <View style={{ marginTop: 12, gap: 8 }} data-testid="tax-explainability-result-card" testID="tax-explainability-result-card">
            <Row label="Transaction" value={explainability.transaction_id} testId="tax-explainability-transaction-id" />
            <Row label="Tax Rule" value={explainability.explainability.tax.rule} testId="tax-explainability-tax-rule" />
            <Row label="Rate" value={explainability.explainability.tax.rate_display} testId="tax-explainability-tax-rate" />
            <Row label="Jurisdiction" value={`${explainability.explainability.tax.jurisdiction.country || '--'}-${explainability.explainability.tax.jurisdiction.state || '--'}`} testId="tax-explainability-jurisdiction" />
            <Row label="Gross Formula" value={explainability.explainability.gross_formula} testId="tax-explainability-gross-formula" />
            <Row label="Net Formula" value={explainability.explainability.net_formula} testId="tax-explainability-net-formula" />
            <Row label="Ledger Recorded" value={explainability.ledger.recorded ? 'Yes' : 'No'} testId="tax-explainability-ledger-recorded" />
            <Row label="Ledger Sequence" value={explainability.ledger.sequence ? String(explainability.ledger.sequence) : 'N/A'} testId="tax-explainability-ledger-sequence" />
            <Row label="Entry Hash" value={explainability.ledger.entry_hash || 'N/A'} testId="tax-explainability-ledger-entry-hash" />

            <View style={{ marginTop: 6, borderWidth: 1, borderColor: T.border, borderRadius: 10, backgroundColor: T.bgSoft, padding: 10 }} data-testid="tax-explainability-breakdown-block" testID="tax-explainability-breakdown-block">
              <Text style={{ color: T.text, fontSize: 10, fontWeight: '800' }} data-testid="tax-explainability-breakdown-title" testID="tax-explainability-breakdown-title">{tx('admin.platformFinanceIntegrityPanel.auto.text.015', 'Tax Breakdown')}</Text>
              {Object.keys(explainability.explainability.tax.breakdown || {}).length === 0 ? (
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 6 }} data-testid="tax-explainability-breakdown-empty" testID="tax-explainability-breakdown-empty">{tx('admin.platformFinanceIntegrityPanel.auto.text.016', 'No detailed breakdown for this transaction.')}</Text>
              ) : (
                Object.entries(explainability.explainability.tax.breakdown).map(([key, value]) => (
                  <Row key={key} label={key} value={String(value)} testId={`tax-explainability-breakdown-${normalizeId(key)}`} />
                ))
              )}
            </View>

            <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }} data-testid="tax-explainability-rule-detail" testID="tax-explainability-rule-detail">
              {explainability.explainability.tax.rule_detail}
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function ConfigBadge({ label, configured, testId }: { label: string; configured: boolean; testId: string }) {    const { colors } = useTheme();
  const color = configured ? colors.success : colors.warning;
  return (
    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${color}55`, backgroundColor: `${color}15`, paddingHorizontal: 10, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid={testId} testID={testId}>
      <View style={{ width: 7, height: 7, borderRadius: 5, backgroundColor: color }} />
      <Text style={{ color, fontSize: 10, fontWeight: '800' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label} {configured ? 'configured' : 'missing'}</Text>
    </View>
  );
}

function MetricPill({ label, value, valueColor, testId }: { label: string; value: string; valueColor: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color: valueColor, fontSize: 11, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
    </View>
  );
}

function Row({ label, value, testId }: { label: string; value: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, paddingVertical: 4 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 10, flex: 1 }}>{label}</Text>
      <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700', flex: 2, textAlign: 'right' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
    </View>
  );
}
