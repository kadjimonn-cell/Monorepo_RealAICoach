import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import api from '../../services/api';
import { HeartbeatPulse } from '../common/HeartbeatPulse';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { ResponsiveDataGrid } from './ResponsiveDataGrid';

type PaymentBillingPanelProps = {
  prefillParams?: Record<string, string>;
};

const tx = (_key: string, fallback: string) => fallback;

export default function PaymentBillingPanel({ prefillParams = {} }: PaymentBillingPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  // V2 Teal Enterprise chart palette — reused by pie / bar / donut breakdowns.
  // Before this palette was defined, the iteration site treated the theme
  // object itself as an array and produced undefined hex values at runtime.
  const chartPalette = [colors.primary, colors.info || colors.primary, colors.purple, colors.warning, colors.success, colors.error];
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [period, setPeriod] = useState('7d');
  const { data: financial, loading: fLoading, refetch: refetchFinancial } = useLiveQuery(`/admin/executive/financial-intelligence?period=${period}`, { entity: 'payments', pollInterval: 60000, deps: [period] });
  const { data: txnData, loading: tLoading, refetch: refetchTxn } = useLiveQuery('/admin/payment-analytics/recent-transactions?limit=20', { entity: 'payments', pollInterval: 30000 });
  const [exportSettings, setExportSettings] = useState({
    theme_profile: 'enterprise',
    signature_enabled: true,
    signature_label: 'RealAICoach Integrity Signature',
  });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [packLoading, setPackLoading] = useState(false);
  const [packMonth, setPackMonth] = useState(currentMonth);
  const [prefillApplied, setPrefillApplied] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [trustSettings, setTrustSettings] = useState({
    trust_signals_enabled: true,
    guarantee_message: 'Refunds handled per provider policy and platform terms.',
    fraud_notice: 'Protected transactions with fraud monitoring.',
    compliance_labels: ['PCI-DSS'],
    display_level: 'detailed' as 'minimal' | 'detailed',
    allow_nova_security_answers: true,
  });
  const [trustSettingsLoading, setTrustSettingsLoading] = useState(false);
  const [trustSettingsSaving, setTrustSettingsSaving] = useState(false);
  const [trustSettingsMessage, setTrustSettingsMessage] = useState<string | null>(null);
  const [trustFunnelWindow, setTrustFunnelWindow] = useState<1440 | 10080>(10080);
  const [trustFunnelLoading, setTrustFunnelLoading] = useState(false);
  const [trustFunnelRows, setTrustFunnelRows] = useState<Array<{ provider: string; open_count: number; conversion_click_count: number; conversion_rate_pct: number }>>([]);
  const [trustFunnelTotals, setTrustFunnelTotals] = useState<{ open_count: number; conversion_click_count: number; conversion_rate_pct: number }>({ open_count: 0, conversion_click_count: 0, conversion_rate_pct: 0 });
  const [packMessage, setPackMessage] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [verifyForm, setVerifyForm] = useState({
    report_id: '',
    generated_at: '',
    row_count: '0',
    total_spent: '0',
    data_hash: '',
    signature: '',
  });
  const recentTxns = txnData?.transactions || txnData?.payments || [];
  const loading = fLoading || tLoading;
  const [methodsStatusCheckedAt, setMethodsStatusCheckedAt] = useState(Date.now());
  const [methodsStatusHeartbeatSec, setMethodsStatusHeartbeatSec] = useState(0);
  const methodsSnapshotRef = useRef('');

  const loadExportSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      const res = await api.get('/admin/payment-history-export-settings');
      const stg = res.data?.settings || {};
      setExportSettings({
        theme_profile: stg.theme_profile || 'enterprise',
        signature_enabled: stg.signature_enabled !== false,
        signature_label: stg.signature_label || 'RealAICoach Integrity Signature',
      });
      setSettingsMessage(null);
    } catch {
      setSettingsMessage('Failed to load export settings');
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  const loadTrustSettings = useCallback(async () => {
    setTrustSettingsLoading(true);
    try {
      const res = await api.get('/admin/payment-trust/settings');
      const stg = res.data?.settings || {};
      setTrustSettings({
        trust_signals_enabled: stg.trust_signals_enabled !== false,
        guarantee_message: stg.guarantee_message || 'Refunds handled per provider policy and platform terms.',
        fraud_notice: stg.fraud_notice || 'Protected transactions with fraud monitoring.',
        compliance_labels: Array.isArray(stg.compliance_labels) && stg.compliance_labels.length > 0 ? stg.compliance_labels : ['PCI-DSS'],
        display_level: stg.display_level === 'minimal' ? 'minimal' : 'detailed',
        allow_nova_security_answers: stg.allow_nova_security_answers !== false,
      });
      setTrustSettingsMessage(null);
    } catch {
      setTrustSettingsMessage('Failed to load Trust & Security settings');
    } finally {
      setTrustSettingsLoading(false);
    }
  }, []);

  const loadTrustFunnel = useCallback(async (windowMinutes: 1440 | 10080 = trustFunnelWindow) => {
    setTrustFunnelLoading(true);
    try {
      const res = await api.get('/admin/subscriptions/trust-funnel-analytics', { params: { minutes: windowMinutes }, silentLoading: true });
      setTrustFunnelRows(Array.isArray(res.data?.providers) ? res.data.providers : []);
      setTrustFunnelTotals({
        open_count: Number(res.data?.totals?.open_count || 0),
        conversion_click_count: Number(res.data?.totals?.conversion_click_count || 0),
        conversion_rate_pct: Number(res.data?.totals?.conversion_rate_pct || 0),
      });
    } catch {
      setTrustFunnelRows([]);
      setTrustFunnelTotals({ open_count: 0, conversion_click_count: 0, conversion_rate_pct: 0 });
    } finally {
      setTrustFunnelLoading(false);
    }
  }, [trustFunnelWindow]);

  useEffect(() => {
    loadExportSettings();
    loadTrustSettings();
    loadTrustFunnel();
  }, [loadExportSettings, loadTrustFunnel, loadTrustSettings]);

  useEffect(() => {
    if (prefillApplied) return;

    const queryParams = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search)
      : null;

    const readParam = (key: string) => {
      const fromProp = prefillParams?.[key];
      if (fromProp) return String(fromProp);
      return queryParams?.get(key) || '';
    };

    const reportId = readParam('verify_report_id');
    const generatedAt = readParam('verify_generated_at');
    const rowCount = readParam('verify_row_count');
    const totalSpent = readParam('verify_total_spent');
    const dataHash = readParam('verify_data_hash');
    const signature = readParam('verify_signature');

    if (!reportId && !generatedAt && !dataHash && !signature) return;

    setVerifyForm((prev) => ({
      ...prev,
      report_id: reportId || prev.report_id,
      generated_at: generatedAt || prev.generated_at,
      row_count: rowCount || prev.row_count,
      total_spent: totalSpent || prev.total_spent,
      data_hash: dataHash || prev.data_hash,
      signature: signature || prev.signature,
    }));
    setSettingsMessage('Verifier form prefilled from QR scan. Review values, then click Verify Integrity.');
    setPrefillApplied(true);
  }, [prefillParams, prefillApplied]);

  const saveExportSettings = async () => {
    setSettingsSaving(true);
    try {
      await api.put('/admin/payment-history-export-settings', exportSettings);
      setSettingsMessage('Export settings saved');
    } catch {
      setSettingsMessage('Failed to save export settings');
    } finally {
      setSettingsSaving(false);
    }
  };

  const resetExportSettings = async () => {
    setSettingsSaving(true);
    try {
      const res = await api.post('/admin/payment-history-export-settings/reset');
      const stg = res.data?.settings || {};
      setExportSettings({
        theme_profile: stg.theme_profile || 'enterprise',
        signature_enabled: stg.signature_enabled !== false,
        signature_label: stg.signature_label || 'RealAICoach Integrity Signature',
      });
      setSettingsMessage('Export settings reset to defaults');
    } catch {
      setSettingsMessage('Failed to reset export settings');
    } finally {
      setSettingsSaving(false);
    }
  };

  const saveTrustSettings = async () => {
    setTrustSettingsSaving(true);
    try {
      await api.put('/admin/payment-trust/settings', trustSettings);
      setTrustSettingsMessage('Trust & Security settings saved');
    } catch {
      setTrustSettingsMessage('Failed to save Trust & Security settings');
    } finally {
      setTrustSettingsSaving(false);
    }
  };

  const verifyIntegrity = async () => {
    setVerifyLoading(true);
    setVerifyResult(null);
    try {
      const payload = {
        report_id: verifyForm.report_id.trim(),
        generated_at: verifyForm.generated_at.trim(),
        row_count: Number(verifyForm.row_count || 0),
        total_spent: Number(verifyForm.total_spent || 0),
        data_hash: verifyForm.data_hash.trim(),
        signature: verifyForm.signature.trim(),
      };
      const res = await api.post('/admin/payment-history-export/verify-integrity', payload);
      setVerifyResult(res.data || null);
    } catch (e: any) {
      setVerifyResult({ valid: false, reason: e?.response?.data?.detail || 'Verification failed' });
    } finally {
      setVerifyLoading(false);
    }
  };

  const downloadExecutivePack = async () => {
    setPackLoading(true);
    setPackMessage(null);
    try {
      const month = /^\d{4}-\d{2}$/.test(packMonth.trim()) ? packMonth.trim() : currentMonth;
      const res = await api.get('/admin/payments/executive-billing-pack', {
        params: { month },
        responseType: 'blob',
        timeout: 180000,
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = res.data as Blob;
        const href = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href;
        link.download = `monthly-executive-billing-pack-${month}.zip`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(href);
      }

      setPackMessage(`Billing pack generated for ${month}.`);
    } catch (e: any) {
      setPackMessage(e?.response?.data?.detail || 'Failed to generate monthly executive pack');
    } finally {
      setPackLoading(false);
    }
  };

  const loadData = async () => {
    await Promise.all([refetchFinancial(), refetchTxn(), loadExportSettings(), loadTrustSettings(), loadTrustFunnel()]);
  };

  const summary = financial?.summary || {};
  const formatCurrency = (value: any) => `$${Number(value || 0).toLocaleString()}`;
  const formatCount = (value: any) => Number(value || 0).toLocaleString();

  const paymentMethodsFromRecent = React.useMemo(() => {
    const agg: Record<string, { method: string; count: number; total: number }> = {};
    (recentTxns || []).forEach((txn: any) => {
      const methodRaw = String(txn?.payment_method || txn?.provider || txn?.gateway || txn?.source || 'unknown').trim();
      const methodKey = methodRaw.toLowerCase();
      const total = Number(txn?.amount_usd ?? txn?.amount ?? 0);
      if (!agg[methodKey]) {
        agg[methodKey] = { method: methodRaw || 'unknown', count: 0, total: 0 };
      }
      agg[methodKey].count += 1;
      agg[methodKey].total += Number.isFinite(total) ? total : 0;
    });
    return Object.values(agg)
      .map((row) => ({ ...row, total: Number(row.total.toFixed(2)) }))
      .sort((a, b) => b.total - a.total);
  }, [recentTxns]);

  const kpis = [
    { label: 'Total Revenue', value: formatCurrency(summary.total_revenue), icon: 'cash', color: T.successText },
    { label: 'Net After Fees', value: formatCurrency(summary.net_revenue_after_fees), icon: 'wallet', color: T.primary },
    { label: 'Active Subscriptions', value: formatCount(summary.active_subscriptions), icon: 'card', color: T.cyan },
    { label: 'Transactions Today', value: formatCount(summary.transactions_today), icon: 'swap-horizontal', color: T.warningText },
    { label: 'MRR', value: formatCurrency(summary.mrr || summary.monthly_recurring_revenue), icon: 'trending-up', color: T.purpleText },
  ];

  const revenueBreakdown = financial?.revenue_breakdown || [];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const paymentMethods = (financial?.payment_methods?.length ? financial.payment_methods : paymentMethodsFromRecent) || [];

  useEffect(() => {
    const signature = JSON.stringify((paymentMethods || []).map((pm: any) => ({ method: pm.method || pm.name, count: pm.count || 0, total: pm.total || 0 })));
    if (signature !== methodsSnapshotRef.current) {
      methodsSnapshotRef.current = signature;
      setMethodsStatusCheckedAt(Date.now());
    }
  }, [paymentMethods]);

  useEffect(() => {
    setMethodsStatusCheckedAt(Date.now());
  }, [period]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setMethodsStatusHeartbeatSec(Math.max(0, Math.floor((Date.now() - methodsStatusCheckedAt) / 1000)));
    }, 1000);
    return () => clearInterval(intervalId);
  }, [methodsStatusCheckedAt]);

  const methodIcon = (m: string) => {
    if (m?.toLowerCase().includes('paypal')) return 'wallet';
    if (m?.toLowerCase().includes('stripe') || m?.toLowerCase().includes('card')) return 'card';
    if (m?.toLowerCase().includes('mobile') || m?.toLowerCase().includes('momo') || m?.toLowerCase().includes('fedapay')) return 'phone-portrait';
    return 'cash';
  };

  const methodColor = (m: string) => {
    if (m?.toLowerCase().includes('paypal')) return T.primary;
    if (m?.toLowerCase().includes('stripe')) return T.purple;
    if (m?.toLowerCase().includes('mobile') || m?.toLowerCase().includes('fedapay')) return T.success;
    return T.cyan;
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="payment-billing-panel" testID="payment-billing-panel">
      <View style={[s.panel, { marginBottom: 20 }]} data-testid="monthly-executive-billing-pack-panel" testID="monthly-executive-billing-pack-panel">
        <Text style={[s.panelTitle, { marginBottom: 10 }]}>{tx('admin.paymentBillingPanel.auto.text.001', 'Monthly Executive Billing Pack')}</Text>
        <Text style={{ color: T.textSec, fontSize: 12, marginBottom: 8 }}>{tx('admin.paymentBillingPanel.auto.text.002', 'Bundle includes redesigned PDF, enterprise CSV, and tax CSV in one ZIP.')}</Text>
        <TextInput
          value={packMonth}
          onChangeText={setPackMonth}
          placeholder={tx('admin.paymentBillingPanel.auto.placeholder.001', 'YYYY-MM')}
          placeholderTextColor={T.textDim}
          style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 10 }}
          data-testid="monthly-executive-pack-month-input" testID="monthly-executive-pack-month-input"
        />
        <TouchableOpacity
          onPress={() => { void downloadExecutivePack(); }}
          disabled={packLoading}
          style={{ backgroundColor: T.success, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9, alignSelf: 'flex-start' }}
          data-testid="monthly-executive-pack-download-btn" testID="monthly-executive-pack-download-btn"
        >
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{packLoading ? 'Building Pack...' : 'Download Billing Pack'}</Text>
        </TouchableOpacity>
        {packMessage && <Text style={{ color: T.textSec, fontSize: 11, marginTop: 8 }} data-testid="monthly-executive-pack-message" testID="monthly-executive-pack-message">{packMessage}</Text>}
      </View>

      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {kpis.map((k, i) => (
          <LinearGradient
            key={i}
            colors={[`${k.color}20`, `${k.color}08`]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[s.kpiCard, { flex: 1, minWidth: 160, borderColor: `${k.color}40`, borderWidth: 1, borderRadius: 16 }]}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase' }}>{k.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: '700', marginTop: 6 }}>{k.value}</Text>
          </LinearGradient>
        ))}
      </View>

      <View style={[s.panel, { marginBottom: 20 }]} data-testid="payment-export-governance-panel" testID="payment-export-governance-panel">
        <Text style={[s.panelTitle, { marginBottom: 10 }]}>{tx('admin.paymentBillingPanel.auto.text.003', 'Payment Export Governance')}</Text>

        {settingsLoading ? (
          <ActivityIndicator size="small" color={T.brand} />
        ) : (
          <>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              {['enterprise', 'finance', 'minimal'].map((theme) => (
                <TouchableOpacity
                  key={theme}
                  onPress={() => setExportSettings((prev) => ({ ...prev, theme_profile: theme }))}
                  style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: exportSettings.theme_profile === theme ? T.brand : T.border, backgroundColor: exportSettings.theme_profile === theme ? `${T.brand}20` : T.card }}
                  data-testid={`payment-export-theme-${theme}`} testID={`payment-export-theme-${theme}`}
                >
                  <Text style={{ color: exportSettings.theme_profile === theme ? T.brand : T.textSec, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{theme}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              onPress={() => setExportSettings((prev) => ({ ...prev, signature_enabled: !prev.signature_enabled }))}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}
              data-testid="payment-export-signature-toggle" testID="payment-export-signature-toggle"
            >
              <Ionicons name={exportSettings.signature_enabled ? 'checkbox' : 'square-outline'} size={18} color={exportSettings.signature_enabled ? T.green : T.textSec} />
              <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.paymentBillingPanel.auto.text.004', 'Enable digital signature + hash footer')}</Text>
            </TouchableOpacity>

            <TextInput
              value={exportSettings.signature_label}
              onChangeText={(text) => setExportSettings((prev) => ({ ...prev, signature_label: text }))}
              placeholder={tx('admin.paymentBillingPanel.auto.placeholder.002', 'Signature label')}
              placeholderTextColor={T.textDim}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 10 }}
              data-testid="payment-export-signature-label-input" testID="payment-export-signature-label-input"
            />

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={() => { void saveExportSettings(); }}
                disabled={settingsSaving}
                style={{ backgroundColor: T.brand, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="payment-export-settings-save-btn" testID="payment-export-settings-save-btn"
              >
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{settingsSaving ? 'Saving...' : 'Save Settings'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { void resetExportSettings(); }}
                disabled={settingsSaving}
                style={{ backgroundColor: T.card, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="payment-export-settings-reset-btn" testID="payment-export-settings-reset-btn"
              >
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.005', 'Reset')}</Text>
              </TouchableOpacity>
            </View>

            {settingsMessage && <Text style={{ color: T.textSec, fontSize: 11, marginTop: 8 }} data-testid="payment-export-settings-message" testID="payment-export-settings-message">{settingsMessage}</Text>}
          </>
        )}
      </View>

      <View style={[s.panel, { marginBottom: 20 }]} data-testid="payment-trust-security-settings-panel" testID="payment-trust-security-settings-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Ionicons name="shield-checkmark" size={16} color={T.successText} />
          <Text style={[s.panelTitle, { marginBottom: 0 }]}>{tx('admin.paymentBillingPanel.auto.text.013', 'Trust & Security Settings')}</Text>
        </View>

        {trustSettingsLoading ? (
          <ActivityIndicator size="small" color={T.primary} />
        ) : (
          <>
            <TouchableOpacity
              onPress={() => setTrustSettings((prev) => ({ ...prev, trust_signals_enabled: !prev.trust_signals_enabled }))}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}
              data-testid="trust-settings-enable-toggle" testID="trust-settings-enable-toggle"
            >
              <Ionicons name={trustSettings.trust_signals_enabled ? 'checkbox' : 'square-outline'} size={18} color={trustSettings.trust_signals_enabled ? T.green : T.textSec} />
              <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.paymentBillingPanel.auto.text.014', 'Enable global trust signals')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setTrustSettings((prev) => ({ ...prev, allow_nova_security_answers: !prev.allow_nova_security_answers }))}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}
              data-testid="trust-settings-nova-toggle" testID="trust-settings-nova-toggle"
            >
              <Ionicons name={trustSettings.allow_nova_security_answers ? 'checkbox' : 'square-outline'} size={18} color={trustSettings.allow_nova_security_answers ? T.green : T.textSec} />
              <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.paymentBillingPanel.auto.text.015', 'Allow Nova payment-security explanations')}</Text>
            </TouchableOpacity>

            <TextInput
              value={trustSettings.guarantee_message}
              onChangeText={(text) => setTrustSettings((prev) => ({ ...prev, guarantee_message: text }))}
              placeholder={tx('admin.paymentBillingPanel.auto.placeholder.003', 'Guarantee message')}
              placeholderTextColor={T.textDim}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 8 }}
              data-testid="trust-settings-guarantee-input" testID="trust-settings-guarantee-input"
            />

            <TextInput
              value={trustSettings.fraud_notice}
              onChangeText={(text) => setTrustSettings((prev) => ({ ...prev, fraud_notice: text }))}
              placeholder={tx('admin.paymentBillingPanel.auto.placeholder.004', 'Fraud protection notice')}
              placeholderTextColor={T.textDim}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 8 }}
              data-testid="trust-settings-fraud-input" testID="trust-settings-fraud-input"
            />

            <TextInput
              value={trustSettings.compliance_labels.join(', ')}
              onChangeText={(text) => setTrustSettings((prev) => ({ ...prev, compliance_labels: text.split(',').map((item) => item.trim()).filter(Boolean) }))}
              placeholder={tx('admin.paymentBillingPanel.auto.placeholder.005', 'Compliance labels, comma-separated')}
              placeholderTextColor={T.textDim}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 10 }}
              data-testid="trust-settings-compliance-input" testID="trust-settings-compliance-input"
            />

            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
              {(['minimal', 'detailed'] as const).map((lvl) => (
                <TouchableOpacity
                  key={lvl}
                  onPress={() => setTrustSettings((prev) => ({ ...prev, display_level: lvl }))}
                  style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: trustSettings.display_level === lvl ? T.primary : T.border, backgroundColor: trustSettings.display_level === lvl ? `${T.primary}20` : T.card }}
                  data-testid={`trust-settings-display-${lvl}`} testID={`trust-settings-display-${lvl}`}
                >
                  <Text style={{ color: trustSettings.display_level === lvl ? T.primary : T.textSec, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{lvl}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={() => { void saveTrustSettings(); }}
                disabled={trustSettingsSaving}
                style={{ backgroundColor: T.success, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="trust-settings-save-btn" testID="trust-settings-save-btn"
              >
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{trustSettingsSaving ? 'Saving...' : 'Save Trust Settings'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { void loadTrustSettings(); }}
                disabled={trustSettingsSaving}
                style={{ backgroundColor: T.card, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="trust-settings-reload-btn" testID="trust-settings-reload-btn"
              >
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>Reload</Text>
              </TouchableOpacity>
            </View>

            {trustSettingsMessage ? (
              <Text style={{ color: T.textSec, fontSize: 11, marginTop: 8 }} data-testid="trust-settings-message" testID="trust-settings-message">{trustSettingsMessage}</Text>
            ) : null}

            <View style={{ marginTop: 12, borderTopWidth: 1, borderTopColor: T.border, paddingTop: 10 }} data-testid="trust-funnel-mini-chart" testID="trust-funnel-mini-chart">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>Trust Funnel (Open → Conversion)</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  {[{ label: '24h', value: 1440 as const }, { label: '7d', value: 10080 as const }].map((opt) => (
                    <TouchableOpacity
                      key={opt.label}
                      onPress={() => { setTrustFunnelWindow(opt.value); void loadTrustFunnel(opt.value); }}
                      style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: trustFunnelWindow === opt.value ? T.primary : T.border, backgroundColor: trustFunnelWindow === opt.value ? `${T.primary}20` : T.card }}
                      data-testid={`trust-funnel-window-${opt.label.toLowerCase()}`}
                      testID={`trust-funnel-window-${opt.label.toLowerCase()}`}
                    >
                      <Text style={{ color: trustFunnelWindow === opt.value ? T.primary : T.textSec, fontSize: 11, fontWeight: '700' }}>{opt.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              {trustFunnelLoading ? (
                <ActivityIndicator size="small" color={T.primary} />
              ) : trustFunnelRows.length === 0 ? (
                <Text style={{ color: T.textSec, fontSize: 11 }}>No trust funnel events recorded for this window yet.</Text>
              ) : (
                <View style={{ gap: 8 }}>
                  {trustFunnelRows.map((row) => {
                    const maxBase = Math.max(1, trustFunnelTotals.open_count || 1);
                    const openPct = Math.min(100, (row.open_count / maxBase) * 100);
                    const conversionPct = Math.min(100, (row.conversion_click_count / maxBase) * 100);
                    return (
                      <View key={row.provider} style={{ gap: 4 }} data-testid={`trust-funnel-row-${row.provider}`} testID={`trust-funnel-row-${row.provider}`}>
                        <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>
                          {row.provider} • {row.conversion_rate_pct}% conversion rate
                        </Text>
                        <View style={{ height: 8, borderRadius: 999, backgroundColor: T.card, overflow: 'hidden' }}>
                          <View style={{ width: `${openPct}%`, height: '100%', backgroundColor: T.primary }} />
                        </View>
                        <View style={{ height: 8, borderRadius: 999, backgroundColor: T.card, overflow: 'hidden' }}>
                          <View style={{ width: `${conversionPct}%`, height: '100%', backgroundColor: T.success }} />
                        </View>
                        <Text style={{ color: T.textSec, fontSize: 10 }}>
                          Opens: {row.open_count} • Conversion clicks: {row.conversion_click_count}
                        </Text>
                      </View>
                    );
                  })}
                  <Text style={{ color: T.textSec, fontSize: 10 }} data-testid="trust-funnel-totals" testID="trust-funnel-totals">
                    Total opens: {trustFunnelTotals.open_count} • Total conversion clicks: {trustFunnelTotals.conversion_click_count} • Total conversion rate: {trustFunnelTotals.conversion_rate_pct}%
                  </Text>
                </View>
              )}
            </View>
          </>
        )}
      </View>

      <View style={[s.panel, { marginBottom: 20 }]} data-testid="payment-export-integrity-verifier-panel" testID="payment-export-integrity-verifier-panel">
        <Text style={[s.panelTitle, { marginBottom: 10 }]}>{tx('admin.paymentBillingPanel.auto.text.006', 'Verify Report Integrity')}</Text>
        {prefillApplied && (
          <View style={{ marginBottom: 10, borderWidth: 1, borderColor: `${T.cyan}66`, backgroundColor: `${T.cyan}14`, borderRadius: 8, padding: 10 }} data-testid="payment-export-qr-prefill-banner" testID="payment-export-qr-prefill-banner">
            <Text style={{ color: T.cyan, fontSize: 12, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.007', 'Prefilled from QR')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 3 }}>{tx('admin.paymentBillingPanel.auto.text.008', 'Fields were auto-filled from the PDF tamper-evident QR block.')}</Text>
          </View>
        )}
        {[
          ['report_id', 'Report ID'],
          ['generated_at', 'Generated ISO Datetime'],
          ['row_count', 'Row Count'],
          ['total_spent', 'Total Spent'],
          ['data_hash', 'Report Hash'],
          ['signature', 'Signature'],
        ].map(([key, label]) => (
          <TextInput
            key={key}
            value={(verifyForm as any)[key]}
            onChangeText={(text) => setVerifyForm((prev) => ({ ...prev, [key]: text }))}
            placeholder={label}
            placeholderTextColor={T.textDim}
            style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, color: T.text, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 8 }}
            data-testid={`payment-export-verify-${key}-input`} testID={`payment-export-verify-${key}-input`}
          />
        ))}
        <TouchableOpacity
          onPress={() => { void verifyIntegrity(); }}
          disabled={verifyLoading}
          style={{ backgroundColor: T.indigo, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9, alignSelf: 'flex-start' }}
          data-testid="payment-export-verify-btn" testID="payment-export-verify-btn"
        >
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{verifyLoading ? 'Verifying...' : 'Verify Integrity'}</Text>
        </TouchableOpacity>

        {verifyResult && (
          <View style={{ marginTop: 10, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: verifyResult.valid ? `${T.green}66` : `${T.red}66`, backgroundColor: verifyResult.valid ? `${T.green}15` : `${T.red}15` }} data-testid="payment-export-verify-result" testID="payment-export-verify-result">
            <Text style={{ color: verifyResult.valid ? T.green : T.red, fontSize: 12, fontWeight: '700' }}>{verifyResult.valid ? 'Valid signature' : 'Invalid signature'}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{verifyResult.reason || 'No message'}</Text>
          </View>
        )}
      </View>

      {/* Period Filter */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {[{ k: '7d', l: '7 Days' }, { k: '30d', l: '30 Days' }, { k: '90d', l: '90 Days' }].map(p => (
          <TouchableOpacity key={p.k} onPress={() => setPeriod(p.k)}
            style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: period === p.k ? T.primary : T.card, borderWidth: 1, borderColor: period === p.k ? T.primary : T.border }}
            data-testid={`billing-period-${p.k}`} testID={`billing-period-${p.k}`}>
            <Text style={{ color: period === p.k ? 'var(--app-primary-text)' : T.textSec, fontSize: 13, fontWeight: '600' }}>{p.l}</Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity onPress={() => { void loadData(); }} style={{ marginLeft: 'auto', width: 36, height: 36, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, alignItems: 'center', justifyContent: 'center' }}
          data-testid="billing-refresh" testID="billing-refresh">
          <Ionicons name="refresh" size={16} color={T.primary} />
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
        {/* Revenue Breakdown */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="pie-chart" size={16} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.009', 'Revenue Breakdown')}</Text>
          </View>
          {revenueBreakdown.length > 0 ? revenueBreakdown.map((item: any, i: number) => {
            const color = chartPalette[i % chartPalette.length];
            const totalRev = revenueBreakdown.reduce((s: number, r: any) => s + (r.amount || r.value || 0), 0);
            const pct = totalRev > 0 ? ((item.amount || item.value || 0) / totalRev * 100).toFixed(1) : '0';
            return (
              <View key={i} style={{ marginBottom: 12 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: color }} />
                    <Text style={{ color: T.text, fontSize: 14 }}>{item.label || item.source || `Source ${i + 1}`}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>{pct}%</Text>
                    <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>${(item.amount || item.value || 0).toLocaleString()}</Text>
                  </View>
                </View>
                <View style={{ height: 4, backgroundColor: T.border, borderRadius: 2, overflow: 'hidden' }}>
                  <View style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: 2 }} />
                </View>
              </View>
            );
          }) : (
            <Text style={{ color: T.textMuted, fontSize: 13, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.paymentBillingPanel.auto.text.010', 'No revenue data available')}</Text>
          )}
        </View>

        {/* Payment Methods */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="card" size={16} color={T.successText} />
            <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.011', 'Payment Methods')}</Text>
            </View>
            <HeartbeatPulse
              tick={methodsStatusHeartbeatSec}
              warningAfterSeconds={60}
              criticalAfterSeconds={120}
              dataTestId="admin-payment-methods-status-heartbeat"
              testID="admin-payment-methods-status-heartbeat"
            >
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>
                {methodsStatusHeartbeatSec >= 120 ? 'Critical stale' : methodsStatusHeartbeatSec >= 60 ? 'Stale' : 'Last checked'} {methodsStatusHeartbeatSec}s ago
              </Text>
            </HeartbeatPulse>
          </View>
          {paymentMethods.length > 0 ? paymentMethods.map((pm: any, i: number) => (
            <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: i < paymentMethods.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(methodColor(pm.method || pm.name), '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={methodIcon(pm.method || pm.name) as any} size={18} color={methodColor(pm.method || pm.name)} />
                </View>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600', textTransform: 'capitalize' }}>{pm.method || pm.name || `Method ${i + 1}`}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{pm.count || 0} txns</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>${(pm.total || 0).toLocaleString()}</Text>
              </View>
            </View>
          )) : (
            <View
              style={{ paddingVertical: 16, borderWidth: 1, borderColor: T.border, borderRadius: 10, backgroundColor: T.bgSoft }}
              data-testid="payment-methods-live-empty-state"
              testID="payment-methods-live-empty-state"
            >
              <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center' }}>
                {tx('admin.paymentBillingPanel.auto.text.012', 'No live payment-method data for this window')}
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* Recent Transactions */}
      {recentTxns.length > 0 && (
        <View style={{ marginTop: 20, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 16, borderBottomWidth: 1, borderBottomColor: T.border, backgroundColor: T.bgSoft }}>
            <Ionicons name="receipt" size={16} color={T.cyan} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.013', 'Recent Transactions')}</Text>
            <View style={{ backgroundColor: T.cyanSoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1, marginLeft: 4 }}>
              <Text style={{ color: T.cyan, fontSize: 10, fontWeight: '700' }}>{recentTxns.length}</Text>
            </View>
          </View>

          <ResponsiveDataGrid
            compactBreakpoint={980}
            desktopTestId="payment-billing-transactions-desktop-table"
            compactTestId="payment-billing-transactions-compact-list"
            renderDesktop={() => (
              <>
                <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.014', 'USER')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.015', 'METHOD')}</Text>
                  <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.016', 'AMOUNT')}</Text>
                  <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.paymentBillingPanel.auto.text.017', 'STATUS')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{tx('admin.paymentBillingPanel.auto.text.018', 'DATE')}</Text>
                </View>
                {recentTxns.slice(0, 10).map((txn: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border, alignItems: 'center' }} data-testid={`txn-row-${i}`} testID={`txn-row-${i}`}>
                    <Text style={{ flex: 1.5, color: T.text, fontSize: 12 }} numberOfLines={1}>{txn.user_email || txn.user_name || 'N/A'}</Text>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 12, textTransform: 'capitalize' }}>{txn.payment_method || txn.method || 'N/A'}</Text>
                    <Text style={{ flex: 0.8, color: T.successText, fontSize: 12, fontWeight: '700' }}>${(txn.amount || 0).toFixed(2)}</Text>
                    <View style={{ flex: 0.8 }}>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor((txn.status === 'completed' || txn.status === 'succeeded' ? T.success : txn.status === 'pending' ? T.warning : T.error), '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, alignSelf: 'flex-start' }}>
                        <Text style={{ color: txn.status === 'completed' || txn.status === 'succeeded' ? T.success : txn.status === 'pending' ? T.warning : T.error, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{txn.status || 'N/A'}</Text>
                      </View>
                    </View>
                    <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, textAlign: 'right' }}>{txn.created_at ? new Date(txn.created_at).toLocaleDateString() : 'N/A'}</Text>
                  </View>
                ))}
              </>
            )}
            renderCompact={() => (
              <View style={{ gap: 8, padding: 12 }}>
                {recentTxns.slice(0, 10).map((txn: any, i: number) => (
                  <View key={i} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, backgroundColor: T.bgSoft, gap: 6 }} data-testid={`txn-row-${i}`} testID={`txn-row-${i}`}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{txn.user_email || txn.user_name || 'N/A'}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11, textTransform: 'capitalize' }}>{txn.payment_method || txn.method || 'N/A'}</Text>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>${(txn.amount || 0).toFixed(2)}</Text>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor((txn.status === 'completed' || txn.status === 'succeeded' ? T.success : txn.status === 'pending' ? T.warning : T.error), '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 }}>
                        <Text style={{ color: txn.status === 'completed' || txn.status === 'succeeded' ? T.success : txn.status === 'pending' ? T.warning : T.error, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{txn.status || 'N/A'}</Text>
                      </View>
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>{txn.created_at ? new Date(txn.created_at).toLocaleDateString() : 'N/A'}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          />
        </View>
      )}
    </View>
  );
}
