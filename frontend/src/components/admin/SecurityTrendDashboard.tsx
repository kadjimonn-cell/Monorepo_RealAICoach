import React, { useMemo, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

export function SecurityTrendDashboard() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [days, setDays] = useState(30);

  const { data: trend, loading } = useLiveQuery(`/admin/autonomous-engine/zero-trust/active-defense/trend?days=${days}`, {
    entity: `security-trend-${days}`,
    pollInterval: 120000,
  });

  const T = useMemo(() => ({
    card: colors?.card || 'var(--app-primary)',
    bgSoft: colors?.bgSoft,
    border: colors?.border || colors.border,
    text: colors?.text || colors.textSec,
    textSec: colors?.textSec,
    textMuted: colors?.textMuted || colors.textDim,
    primary: colors?.primary || colors.success,
    success: colors?.success || colors.success,
    warning: colors?.warning || colors.warning,
    error: colors?.error || colors.error,
    successText: (colors as any)?.successText || colors?.success || 'var(--app-primary)',
    primaryText: (colors as any)?.primaryText || 'rgb(255,255,255)',
  }), [colors]);

  const dataPoints = (trend?.data_points || []) as any[];
  const sectionRates = (trend?.section_pass_rates || {}) as Record<string, { pass: number; fail: number; rate: number }>;
  const _maxChecks = 8;

  if (loading && !trend) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }} data-testid="security-trend-loading" testID="security-trend-loading">
        <ActivityIndicator size="large" color={T.primary} />
      </View>
    );
  }

  return (
    <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: T.border, padding: 16, gap: 14 }} data-testid="security-trend-panel" testID="security-trend-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="trending-up" size={16} color={T.primary} />
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }} data-testid="security-trend-title" testID="security-trend-title">{tx('admin.securityTrendDashboard.auto.text.001', 'Security Posture Trend')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {[7, 14, 30].map(d => (
            <TouchableOpacity key={d} onPress={() => setDays(d)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: days === d ? `${T.primary}20` : T.bgSoft, borderWidth: 1, borderColor: days === d ? `${T.primary}50` : T.border }} data-testid={`security-trend-${d}d`} testID={`security-trend-${d}d`}>
              <Text style={{ color: days === d ? T.primary : T.textSec, fontSize: 10, fontWeight: '700' }}>{d}d</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Summary stats */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="security-trend-summary" testID="security-trend-summary">
        <View style={{ flex: 1, minWidth: 100, backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.002', 'Scans')}</Text>
          <Text style={{ color: T.text, fontSize: 18, fontWeight: '900', marginTop: 3 }} data-testid="security-trend-total-scans" testID="security-trend-total-scans">{trend?.total_scans || 0}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.003', 'Pass Rate')}</Text>
          <Text style={{ color: (trend?.pass_rate || 0) >= 80 ? T.success : (trend?.pass_rate || 0) >= 50 ? T.warning : T.error, fontSize: 18, fontWeight: '900', marginTop: 3 }} data-testid="security-trend-pass-rate" testID="security-trend-pass-rate">{trend?.pass_rate || 0}%</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.004', 'Passed')}</Text>
          <Text style={{ color: T.successText, fontSize: 18, fontWeight: '900', marginTop: 3 }}>{trend?.pass_count || 0}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.005', 'Failed')}</Text>
          <Text style={{ color: T.error, fontSize: 18, fontWeight: '900', marginTop: 3 }}>{trend?.fail_count || 0}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.006', 'IPs Blocked')}</Text>
          <Text style={{ color: (trend?.total_blocked_ips || 0) > 0 ? T.warning : T.text, fontSize: 18, fontWeight: '900', marginTop: 3 }}>{trend?.total_blocked_ips || 0}</Text>
        </View>
      </View>

      {/* Visual trend bar chart */}
      {dataPoints.length > 0 && (
        <View style={{ gap: 6 }}>
          <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.007', 'Daily Checks')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 60 }} data-testid="security-trend-chart" testID="security-trend-chart">
            {dataPoints.map((p: any, idx: number) => {
              const pct = (p.pass_count || 0) / (p.total_checks || 8);
              const barColor = p.status === 'PASS' ? T.success : T.error;
              return (
                <View key={idx} style={{ flex: 1, height: '100%', justifyContent: 'flex-end' }}>
                  <View style={{ height: `${Math.max(pct * 100, 8)}%` as any, backgroundColor: barColor, borderRadius: 3, minHeight: 4 }} />
                  <Text style={{ color: T.textMuted, fontSize: 7, textAlign: 'center', marginTop: 2 }}>{String(p.date || '').slice(5)}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Section pass rates */}
      {Object.keys(sectionRates).length > 0 && (
        <View style={{ gap: 6 }}>
          <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.securityTrendDashboard.auto.text.008', 'Section Pass Rates')}</Text>
          {Object.entries(sectionRates).sort(([, a], [, b]) => a.rate - b.rate).map(([sec, data]) => (
            <View key={sec} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={{ color: T.textSec, fontSize: 10, width: 100 }} numberOfLines={1}>{sec.replace(/_/g, ' ')}</Text>
              <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: T.border }}>
                <View style={{ width: `${data.rate}%` as any, height: 6, borderRadius: 3, backgroundColor: data.rate >= 80 ? T.success : data.rate >= 50 ? T.warning : T.error }} />
              </View>
              <Text style={{ color: data.rate >= 80 ? T.success : data.rate >= 50 ? T.warning : T.error, fontSize: 10, fontWeight: '700', width: 35, textAlign: 'right' }}>{data.rate}%</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

export function DriftAlertConfigPanel() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState('');
  const [testing, setTesting] = useState(false);

  const { data: config, refetch } = useLiveQuery('/admin/autonomous-engine/drift-alerts/config', {
    entity: 'drift-alert-config',
    pollInterval: 60000,
  });

  const [localConfig, setLocalConfig] = useState<any>(null);
  const cfg = localConfig || config || { enabled: false, slack_webhook_url: '', teams_webhook_url: '', alert_min_severity: 'high' };

  const save = useCallback(async (updates: any) => {
    setSaving(true);
    setNote('');
    try {
      await api.put('/admin/autonomous-engine/drift-alerts/config', updates);
      setLocalConfig(null);
      await refetch();
      setNote('Configuration saved');
    } catch (e: any) {
      setNote(e?.response?.data?.detail || 'Save failed');
    }
    setSaving(false);
  }, [refetch]);

  const testAlert = useCallback(async () => {
    setTesting(true);
    setNote('');
    try {
      const res = await api.post('/admin/autonomous-engine/drift-alerts/test');
      const results = res.data?.results || [];
      const ok = results.filter((r: any) => r.ok).length;
      setNote(`Test sent: ${ok}/${results.length} delivered`);
    } catch (e: any) {
      setNote(e?.response?.data?.detail || 'Test failed');
    }
    setTesting(false);
  }, []);

  const T = useMemo(() => ({
    card: colors?.card || 'var(--app-primary)',
    bgSoft: colors?.bgSoft,
    border: colors?.border || colors.border,
    text: colors?.text || colors.textSec,
    textSec: colors?.textSec,
    textMuted: colors?.textMuted || colors.textDim,
    primary: colors?.primary || colors.success,
    success: colors?.success || colors.success,
    warning: colors?.warning || colors.warning,
    error: colors?.error || colors.error,
  }), [colors]);

  return (
    <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: T.border, padding: 16, gap: 12 }} data-testid="drift-alert-config-panel" testID="drift-alert-config-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="notifications" size={14} color={T.primary} />
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="drift-alert-title" testID="drift-alert-title">{tx('admin.securityTrendDashboard.auto.text.009', 'Slack / Teams Drift Alerts')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => save({ enabled: !cfg.enabled })}
          style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: cfg.enabled ? `${T.success}20` : `${T.error}20`, borderWidth: 1, borderColor: cfg.enabled ? `${T.success}50` : `${T.error}50` }}
          data-testid="drift-alert-toggle" testID="drift-alert-toggle"
        >
          <Text style={{ color: cfg.enabled ? T.success : T.error, fontSize: 10, fontWeight: '800' }}>{cfg.enabled ? 'ENABLED' : 'DISABLED'}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ gap: 8 }}>
        <View style={{ gap: 4 }}>
          <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.securityTrendDashboard.auto.text.010', 'Slack Webhook URL')}</Text>
          <TextInput
            value={localConfig?.slack_webhook_url ?? cfg.slack_webhook_url ?? ''}
            onChangeText={v => setLocalConfig({ ...cfg, ...localConfig, slack_webhook_url: v })}
            placeholder={tx('admin.securityTrendDashboard.auto.placeholder.001', 'https://hooks.slack.com/services/...')}
            placeholderTextColor={T.textMuted}
            style={{ borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: T.text, backgroundColor: T.bgSoft, fontSize: 11 }}
            data-testid="drift-alert-slack-url" testID="drift-alert-slack-url"
          />
        </View>
        <View style={{ gap: 4 }}>
          <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.securityTrendDashboard.auto.text.011', 'Teams Webhook URL')}</Text>
          <TextInput
            value={localConfig?.teams_webhook_url ?? cfg.teams_webhook_url ?? ''}
            onChangeText={v => setLocalConfig({ ...cfg, ...localConfig, teams_webhook_url: v })}
            placeholder={tx('admin.securityTrendDashboard.auto.placeholder.002', 'https://outlook.office.com/webhook/...')}
            placeholderTextColor={T.textMuted}
            style={{ borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: T.text, backgroundColor: T.bgSoft, fontSize: 11 }}
            data-testid="drift-alert-teams-url" testID="drift-alert-teams-url"
          />
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TouchableOpacity onPress={() => save(localConfig || cfg)} disabled={saving} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.primary, opacity: saving ? 0.6 : 1 }} data-testid="drift-alert-save-btn" testID="drift-alert-save-btn">
          <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={testAlert} disabled={testing} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, opacity: testing ? 0.6 : 1 }} data-testid="drift-alert-test-btn" testID="drift-alert-test-btn">
          <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{testing ? 'Sending...' : 'Send Test'}</Text>
        </TouchableOpacity>
      </View>

      {note ? <Text style={{ color: note.includes('fail') ? T.error : T.success, fontSize: 11, fontWeight: '600' }} data-testid="drift-alert-note" testID="drift-alert-note">{note}</Text> : null}
    </View>
  );
}
