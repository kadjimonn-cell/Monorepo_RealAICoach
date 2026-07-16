import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import api from '../../services/api';
import { useExecTheme, MiniSparkline, useExecStyles } from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type OverviewPayload = {
  summary?: {
    total_users: number;
    language_mismatch_count: number;
    currency_mismatch_count: number;
    combined_mismatch_count: number;
  };
  countries?: { country: string; mismatch_count: number }[];
  mismatches?: any[];
};

type EffectivenessPayload = {
  metrics?: {
    dismiss_rate: number;
    switch_conversion_rate: number;
    remediation_success_rate: number;
    avg_time_to_align_minutes: number;
    open_count: number;
  };
  trend?: {
    labels: string[];
    dismiss_rate: number[];
    switch_conversion_rate: number[];
    remediation_success_rate: number[];
    avg_time_to_align_minutes: number[];
  };
  daily_trend?: {
    date: string;
    dismiss_rate: number;
    switch_conversion_rate: number;
    remediation_success_rate: number;
    avg_time_to_align_minutes: number;
  }[];
  country_breakdown?: {
    country: string;
    open: number;
    dismiss_rate: number;
    switch_conversion_rate: number;
  }[];
};

type TrendPayload = {
  labels: string[];
  dismiss_rate: number[];
  switch_conversion_rate: number[];
  remediation_success_rate: number[];
  avg_time_to_align_minutes: number[];
};

const tx = (_key: string, fallback: string) => fallback;

function MetricTrendCard({
  title,
  value,
  trendData,
  testId,
}: {
  title: string;
  value: string | number;
  trendData: number[];
  testId: string;
}) {
  const s = useExecStyles();
  const T = useExecTheme();
  return (
    <View
      style={[s.kpiCard, { minWidth: 150 }]}
      data-testid={`${testId}-card`} testID={`${testId}-card`}
    >
      <Text style={s.kpiValue} data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {value}
      </Text>
      <Text style={s.kpiLabel} data-testid={`${testId}-label`} testID={`${testId}-label`}>
        {title}
      </Text>
      <View style={{ marginTop: 8 }} data-testid={`${testId}-trend`} testID={`${testId}-trend`}>
        {trendData.length > 1 ? (
          <MiniSparkline data={trendData} color={T.cyan} width={92} height={30} />
        ) : (
          <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.001', 'Trend unavailable')}</Text>
        )}
      </View>
    </View>
  );
}

export default function GlobalAdaptationControlCenterPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const [loading, setLoading] = useState(true);
  const [remediating, setRemediating] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [data, setData] = useState<OverviewPayload>({});
  const [effectiveness, setEffectiveness] = useState<EffectivenessPayload>({});

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [overviewRes, effectivenessRes] = await Promise.all([
        api.get('/i18n/admin/global-adaptation/overview'),
        api.get('/i18n/admin/global-adaptation/effectiveness', { params: { days: 7, include_country_breakdown: true } }),
      ]);
      setData(overviewRes.data || {});
      setEffectiveness(effectivenessRes.data || {});
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load adaptation overview');
    } finally {
      setLoading(false);
    }
  };

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/global-adaptation-control-center/hybrid-refresh',
    onTick: load,
    runOnMount: true,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const remediate = async () => {
    setRemediating(true);
    setNotice('');
    try {
      const res = await api.post('/i18n/admin/global-adaptation/remediate', { auto_align_currency: false });
      setNotice(`Remediation batch ${res.data?.batch_id || ''}: ${res.data?.notifications_created || 0} guidance notifications created.`);
      await load();
    } catch (e: any) {
      setNotice(e?.response?.data?.detail || 'Remediation failed');
    } finally {
      setRemediating(false);
    }
  };

  if (loading) {
    return <View style={[s.panel, { alignItems: 'center', paddingVertical: 40 }]} data-testid="global-adaptation-loading" testID="global-adaptation-loading"><ActivityIndicator color={T.cyan} /><Text style={{ color: T.textSec, marginTop: 10 }}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.002', 'Loading adaptation health...')}</Text></View>;
  }

  const summary = data.summary || { total_users: 0, language_mismatch_count: 0, currency_mismatch_count: 0, combined_mismatch_count: 0 };
  const countries = data.countries || [];
  const mismatches = data.mismatches || [];
  const metrics = effectiveness.metrics || { dismiss_rate: 0, switch_conversion_rate: 0, remediation_success_rate: 0, avg_time_to_align_minutes: 0, open_count: 0 };
  const effectivenessCountries = effectiveness.country_breakdown || [];
  const trend: TrendPayload = effectiveness.trend || {
    labels: [],
    dismiss_rate: (effectiveness.daily_trend || []).map((d) => d.dismiss_rate),
    switch_conversion_rate: (effectiveness.daily_trend || []).map((d) => d.switch_conversion_rate),
    remediation_success_rate: (effectiveness.daily_trend || []).map((d) => d.remediation_success_rate),
    avg_time_to_align_minutes: (effectiveness.daily_trend || []).map((d) => d.avg_time_to_align_minutes),
  };

  return (
    <View style={s.panel} data-testid="global-adaptation-control-center-panel" testID="global-adaptation-control-center-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <Text style={s.panelTitle}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.003', 'Global Adaptation Control Center')}</Text>
        <TouchableOpacity onPress={() => { void remediate(); }} disabled={remediating} style={{ backgroundColor: T.cyan, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="global-adaptation-remediate-btn" testID="global-adaptation-remediate-btn">
          <Text style={{ color: T.text, fontWeight: '800', fontSize: 12 }}>{remediating ? 'Remediating...' : 'Run One-Click Remediation'}</Text>
        </TouchableOpacity>
      </View>

      {notice ? <Text style={{ color: T.textSec, fontSize: 12, marginBottom: 10 }} data-testid="global-adaptation-notice" testID="global-adaptation-notice">{notice}</Text> : null}
      {error ? <Text style={{ color: colors.errorText, fontSize: 12, marginBottom: 10 }} data-testid="global-adaptation-error" testID="global-adaptation-error">{error}</Text> : null}

      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <View style={[s.kpiCard, { minWidth: 150 }]} data-testid="global-adaptation-kpi-total-users" testID="global-adaptation-kpi-total-users"><Text style={s.kpiValue}>{summary.total_users}</Text><Text style={s.kpiLabel}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.004', 'Users Audited')}</Text></View>
        <View style={[s.kpiCard, { minWidth: 150 }]} data-testid="global-adaptation-kpi-lang" testID="global-adaptation-kpi-lang"><Text style={s.kpiValue}>{summary.language_mismatch_count}</Text><Text style={s.kpiLabel}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.005', 'Language Mismatch')}</Text></View>
        <View style={[s.kpiCard, { minWidth: 150 }]} data-testid="global-adaptation-kpi-currency" testID="global-adaptation-kpi-currency"><Text style={s.kpiValue}>{summary.currency_mismatch_count}</Text><Text style={s.kpiLabel}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.006', 'Currency Mismatch')}</Text></View>
        <View style={[s.kpiCard, { minWidth: 150 }]} data-testid="global-adaptation-kpi-combined" testID="global-adaptation-kpi-combined"><Text style={s.kpiValue}>{summary.combined_mismatch_count}</Text><Text style={s.kpiLabel}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.007', 'Combined Mismatch')}</Text></View>
      </View>

      <Text style={[s.panelTitle, { marginBottom: 6 }]}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.008', 'Top Countries by Mismatch')}</Text>
      <View style={{ marginBottom: 12 }} data-testid="global-adaptation-countries-list" testID="global-adaptation-countries-list">
        {countries.slice(0, 6).map((c) => (
          <Text key={c.country} style={{ color: T.textSec, fontSize: 12, marginBottom: 3 }}>{c.country}: {c.mismatch_count}</Text>
        ))}
      </View>

      <Text style={[s.panelTitle, { marginBottom: 6 }]}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.009', 'Guidance Effectiveness (Last 7 Days)')}</Text>
      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 10 }} data-testid="global-adaptation-effectiveness-metrics" testID="global-adaptation-effectiveness-metrics">
        <MetricTrendCard
          title="Dismiss Rate"
          value={`${metrics.dismiss_rate}%`}
          trendData={trend.dismiss_rate || []}
          testId="global-adaptation-metric-dismiss-rate"
        />
        <MetricTrendCard
          title="Switch Conversion"
          value={`${metrics.switch_conversion_rate}%`}
          trendData={trend.switch_conversion_rate || []}
          testId="global-adaptation-metric-switch-conversion"
        />
        <MetricTrendCard
          title="Remediation Success"
          value={`${metrics.remediation_success_rate}%`}
          trendData={trend.remediation_success_rate || []}
          testId="global-adaptation-metric-remediation-success"
        />
        <MetricTrendCard
          title="Time-to-Align (min)"
          value={metrics.avg_time_to_align_minutes}
          trendData={trend.avg_time_to_align_minutes || []}
          testId="global-adaptation-metric-time-to-align"
        />
      </View>

      <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }} data-testid="global-adaptation-trend-window" testID="global-adaptation-trend-window">
        Trend window: {(trend.labels || []).slice(-7).map((d) => d.slice(5)).join(' · ') || 'No daily trend data yet'}
      </Text>

      <View style={{ marginBottom: 12 }} data-testid="global-adaptation-effectiveness-countries" testID="global-adaptation-effectiveness-countries">
        {effectivenessCountries.slice(0, 6).map((c) => (
          <Text key={`eff-${c.country}`} style={{ color: T.textSec, fontSize: 12, marginBottom: 3 }}>
            {c.country}: open {c.open} · dismiss {c.dismiss_rate}% · switch {c.switch_conversion_rate}%
          </Text>
        ))}
      </View>

      <Text style={[s.panelTitle, { marginBottom: 6 }]}>{tx('admin.globalAdaptationControlCenterPanel.auto.text.010', 'Sample Mismatch Records')}</Text>
      <ScrollView style={{ maxHeight: 260 }} data-testid="global-adaptation-records-scroll" testID="global-adaptation-records-scroll">
        {mismatches.slice(0, 20).map((m, idx) => (
          <View key={`${m.user_id}-${idx}`} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 8, padding: 10, marginBottom: 8 }} data-testid="global-adaptation-record-row" testID="global-adaptation-record-row">
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{m.email || m.user_id}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>
              {m.country} · Lang {m.preferred_language} → {m.expected_language} · Currency {m.preferred_currency} → {m.expected_currency}
            </Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}
