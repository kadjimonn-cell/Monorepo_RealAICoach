import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { getShadow } from '../../utils/themeShadows';
import { ThemeHealthCenterPanel } from './ThemeHealthCenterPanel';
import { ThemeDriftTicketsPanel } from './ThemeDriftTicketsPanel';
import { ThemeTokenRemediationPanel } from './ThemeTokenRemediationPanel';
import { V2ComplianceGuardrailPanel } from './V2ComplianceGuardrailPanel';
import { V1_DARK, V1_LIGHT } from '../../theme/v1';
import { useTranslation } from '../../hooks/useTranslation';

function buildPreviewColors(mode: 'light' | 'dark', liveColors: any) {
  return mode === 'light' ? { ...liveColors, ...V1_LIGHT } : { ...liveColors, ...V1_DARK };
}

function ComponentPreviewCard({ title, colors, isDark }: { title: string; colors: any; isDark: boolean }) {
  const chartBars = [42, 68, 55, 84, 73, 91];
  return (
    <View
      style={{
        flex: 1, minWidth: 340,
        backgroundColor: colors.card,
        borderRadius: 22, borderWidth: 1, borderColor: colors.border,
        padding: 18, gap: 16,
        ...getShadow('md', isDark),
      }}
      data-testid={`theme-validation-preview-${title.toLowerCase().replace(/\s/g, '-')}`} testID={`theme-validation-preview-${title.toLowerCase().replace(/\s/g, '-')}`}
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{title}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.themeValidationDashboard.auto.text.001', 'Side-by-side component parity')}</Text>
        </View>
        <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: colors.primarySoft }}>
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', letterSpacing: 0.6 }}>{isDark ? 'DARK' : 'LIGHT'}</Text>
        </View>
      </View>

      {/* Buttons */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 12 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.002', 'Buttons')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <TouchableOpacity style={{ backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 }} accessibilityLabel={tx('admin.themeValidationDashboard.auto.accessibility.001', 'Primary')}>
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.003', 'Primary')}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{ backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.borderStrong || colors.border, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 }} accessibilityLabel={tx('admin.themeValidationDashboard.auto.accessibility.002', 'Secondary')}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.004', 'Secondary')}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{ backgroundColor: isDark ? 'rgba(239,68,68,0.12)' : 'rgba(220,38,38,0.08)', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: isDark ? 'rgba(239,68,68,0.30)' : 'rgba(220,38,38,0.20)' }} accessibilityLabel={tx('admin.themeValidationDashboard.auto.accessibility.003', 'Danger')}>
            <Text style={{ color: colors.errorText || colors.error, fontSize: 12, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.005', 'Danger')}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{ backgroundColor: 'transparent', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 }} accessibilityLabel={tx('admin.themeValidationDashboard.auto.accessibility.004', 'Link')}>
            <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700', textDecorationLine: 'underline' }}>{tx('admin.themeValidationDashboard.auto.text.006', 'Link')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Badges */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.007', 'Badges & Status')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {[
            { label: 'Active', color: colors.successText },
            { label: 'Pending', color: colors.warningText },
            { label: 'Error', color: colors.error || 'var(--app-error)' },
            { label: 'Info', color: colors.primary },
          ].map(b => (
            <View key={b.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(b.color, '18') }}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: b.color }} />
              <Text style={{ color: b.color, fontSize: 11, fontWeight: '700' }}>{b.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Form */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.008', 'Form Elements')}</Text>
        <TextInput accessibilityLabel={tx('admin.themeValidationDashboard.auto.accessibility.005', 'Text input')}
          editable={false}
          value="Standard text input"
          style={{ backgroundColor: colors.input, color: colors.inputText, borderWidth: 1, borderColor: colors.inputBorder, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, fontSize: 12 }}
        />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 22, borderRadius: 11, backgroundColor: colors.primary, justifyContent: 'center', padding: 2 }}>
            <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: colors.primaryText, alignSelf: 'flex-end' }} />
          </View>
          <Text style={{ color: colors.text, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.009', 'Toggle on')}</Text>
          <View style={{ width: 40, height: 22, borderRadius: 11, backgroundColor: colors.bgAlt, borderWidth: 1, borderColor: colors.border, justifyContent: 'center', padding: 2 }}>
            <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: colors.textMuted, alignSelf: 'flex-start' }} />
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.010', 'Toggle off')}</Text>
        </View>
      </View>

      {/* KPI Cards */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.011', 'KPI Cards')}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[
            { label: 'Revenue', value: '$12.4k', icon: 'wallet', color: colors.successText },
            { label: 'Users', value: '2,481', icon: 'people', color: colors.primary },
            { label: 'Issues', value: '3', icon: 'warning', color: colors.warningText },
          ].map(kpi => (
            <View key={kpi.label} style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(kpi.color, '0C'), borderRadius: 14, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(kpi.color, '20') }}>
              <Ionicons name={kpi.icon as any} size={16} color={kpi.color} />
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', marginTop: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>{kpi.label}</Text>
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginTop: 2 }}>{kpi.value}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Table */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.012', 'Data Table')}</Text>
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', backgroundColor: colors.bgAlt, paddingVertical: 8, paddingHorizontal: 12 }}>
            {['User', 'Plan', 'Status', 'Amount'].map(h => (
              <Text key={h} style={{ flex: 1, color: colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }}>{h}</Text>
            ))}
          </View>
          {[
            { name: 'Alex M.', plan: 'Premium', status: 'Active', statusColor: 'var(--app-success)', amount: '$29.99' },
            { name: 'Sarah K.', plan: 'Basic', status: 'Pending', statusColor: 'var(--app-warning)', amount: '$9.99' },
          ].map((row, i) => (
            <View key={i} style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: i % 2 === 0 ? colors.surface : colors.surfaceHover, borderTopWidth: 1, borderTopColor: colors.border }}>
              <Text style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: '600' }}>{row.name}</Text>
              <Text style={{ flex: 1, color: colors.textSec, fontSize: 12 }}>{row.plan}</Text>
              <View style={{ flex: 1 }}>
                <Text style={{ color: row.statusColor, fontSize: 11, fontWeight: '700' }}>{row.status}</Text>
              </View>
              <Text style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: '600' }}>{row.amount}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Alert / Notification */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.013', 'Alerts & Notifications')}</Text>
        {[
          { type: 'Success', icon: 'checkmark-circle', color: colors.successText, msg: 'Payment processed successfully' },
          { type: 'Warning', icon: 'alert-circle', color: colors.warningText, msg: 'Subscription expiring in 3 days' },
          { type: 'Error', icon: 'close-circle', color: colors.error || 'var(--app-error)', msg: 'Connection timeout — please retry' },
        ].map(a => (
          <View key={a.type} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(a.color, '0C'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(a.color, '20') }}>
            <Ionicons name={a.icon as any} size={16} color={a.color} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: a.color, fontSize: 11, fontWeight: '700' }}>{a.type}</Text>
              <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 1 }}>{a.msg}</Text>
            </View>
          </View>
        ))}
      </View>

      {/* Chart */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.014', 'Chart Preview')}</Text>
        <View style={{ backgroundColor: colors.chartSurface || colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 5, height: 72 }}>
            {chartBars.map((bar, idx) => (
              <View key={idx} style={{ flex: 1, justifyContent: 'flex-end', height: '100%' as any }}>
                <View style={{ height: `${bar}%` as any, borderRadius: 5, backgroundColor: idx % 3 === 0 ? colors.chartLinePrimary : idx % 3 === 1 ? colors.chartLineSecondary : colors.chartLineTertiary }} />
              </View>
            ))}
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, alignItems: 'center' }}>
            <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeValidationDashboard.auto.text.015', 'Jan — Jun')}</Text>
            <View style={{ backgroundColor: colors.chartTooltipBg, borderWidth: 1, borderColor: colors.chartTooltipBorder, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>$1,240</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Nav / Sidebar items */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('admin.themeValidationDashboard.auto.text.016', 'Navigation Items')}</Text>
        {[
          { label: 'Dashboard', icon: 'grid', active: true },
          { label: 'Analytics', icon: 'bar-chart', active: false },
          { label: 'Settings', icon: 'settings', active: false },
        ].map(nav => (
          <View key={nav.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10, backgroundColor: nav.active ? (colors.primarySoft) : 'transparent' }}>
            <Ionicons name={nav.icon as any} size={16} color={nav.active ? colors.primary : colors.textMuted} />
            <Text style={{ color: nav.active ? colors.primary : colors.textSec, fontSize: 13, fontWeight: nav.active ? '700' : '500' }}>{nav.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

const cardTitleStyle = (colors: any) => ({
  color: colors.text,
  fontSize: 15,
  fontWeight: '800',
});

const cardCopyStyle = (colors: any) => ({
  color: colors.textMuted,
  fontSize: 12,
  marginTop: 4,
  lineHeight: 18,
});

const inlineMetricLabelStyle = (colors: any) => ({
  color: colors.textMuted,
  fontSize: 10,
  fontWeight: '700',
  textTransform: 'uppercase' as const,
});

const inlineMetricValueStyle = (colors: any) => ({
  color: colors.text,
  fontSize: 14,
  fontWeight: '800',
  marginTop: 6,
});

export default function ThemeValidationDashboard() {
  const { darkMode, themeMode, setThemeMode , colors} = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const lightPreview = useMemo(() => buildPreviewColors('light', colors), [colors]);
  const darkPreview = useMemo(() => buildPreviewColors('dark', colors), [colors]);
  const [viewMode, setViewMode] = useState<'side-by-side' | 'light' | 'dark'>('side-by-side');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningValidation, setRunningValidation] = useState(false);
  const [runningSafeAutofix, setRunningSafeAutofix] = useState(false);
  const [savingSuggestionId, setSavingSuggestionId] = useState('');
  const [status, setStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any>(null);
  const [safeAutofixResult, setSafeAutofixResult] = useState<any>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [healthOverview, setHealthOverview] = useState<any>(null);
  const centerTitle = t('themeValidation.header.title');

  const loadDashboard = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setLoading(true);
    else setRefreshing(true);
    try {
      const [statusRes, historyRes, suggestionsRes, healthRes] = await Promise.all([
        api.get('/admin/autonomous-engine/theme-guardrail/status', { silentLoading: true }),
        api.get('/admin/autonomous-engine/theme-guardrail/history?limit=8', { silentLoading: true }),
        api.get('/admin/autonomous-engine/theme-guardrail/low-severity/suggestions?limit=10', { silentLoading: true }),
        api.get('/admin/autonomous-engine/theme-health-center/overview?matrix_limit=60&run_limit=10&ticket_limit=12', { silentLoading: true }),
      ]);
      setStatus(statusRes.data || null);
      setHistory(historyRes.data?.runs || []);
      setSuggestions(suggestionsRes.data || null);
      setHealthOverview(healthRes.data || null);
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || e?.message || 'Failed to load Theme Health Center.' });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard('initial');
  }, [loadDashboard]);

  const runValidation = useCallback(async () => {
    setRunningValidation(true);
    setMessage(null);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-guardrail/run');
      setStatus(res.data || null);
      await loadDashboard('refresh');
      setMessage({ type: 'success', text: `Theme validation run complete (${res.data?.run_id || 'run created'}).` });
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || e?.message || 'Theme validation run failed.' });
    } finally {
      setRunningValidation(false);
    }
  }, [loadDashboard]);

  const runSafeAutofix = useCallback(async () => {
    setRunningSafeAutofix(true);
    setMessage(null);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-guardrail/safe-autofix/run');
      setSafeAutofixResult(res.data || null);
      await loadDashboard('refresh');
      setMessage({ type: 'success', text: `Safe auto-fix run complete (${res.data?.run_id || 'run created'}).` });
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || e?.message || 'Safe auto-fix failed.' });
    } finally {
      setRunningSafeAutofix(false);
    }
  }, [loadDashboard]);

  const updateSuggestionStatus = useCallback(async (suggestionId: string, nextAction: 'mark-done' | 'reopen') => {
    setSavingSuggestionId(suggestionId);
    setMessage(null);
    try {
      await api.post(`/admin/autonomous-engine/theme-guardrail/low-severity/suggestions/${suggestionId}/${nextAction}`);
      await loadDashboard('refresh');
      setMessage({ type: 'success', text: nextAction === 'mark-done' ? 'Suggestion marked as completed.' : 'Suggestion reopened.' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || e?.message || 'Failed to update suggestion.' });
    } finally {
      setSavingSuggestionId('');
    }
  }, [loadDashboard]);

  const summaryCards = useMemo(() => {
    const severity = status?.issues_by_severity || {};
    return [
      { id: 'status', label: 'Theme Guardrail Status', value: status?.status || 'NOT_RUN', tone: status?.status === 'PASS' ? colors.success : colors.warning || colors.primary, icon: 'shield-checkmark' },
      { id: 'score', label: 'Score', value: status?.theme_guardrail_score ?? 0, tone: colors.primary, icon: 'speedometer' },
      { id: 'files', label: 'Files Scanned', value: status?.files_scanned ?? 0, tone: colors.cyan || colors.primary, icon: 'document-text' },
      { id: 'issues', label: 'Issues Total', value: status?.issues_total ?? 0, tone: (status?.issues_total || 0) > 0 ? colors.warning || colors.primary : colors.success, icon: 'warning' },
      { id: 'high', label: 'High Severity', value: severity.high ?? 0, tone: colors.error || colors.error, icon: 'alert-circle' },
      { id: 'medium', label: 'Medium Severity', value: severity.medium ?? 0, tone: colors.warning || colors.warning, icon: 'alert' },
      { id: 'safe-ready', label: 'Safe Ready', value: suggestions?.safe_ready ?? 0, tone: colors.success, icon: 'construct' },
      { id: 'completed', label: 'Completed', value: suggestions?.completed ?? 0, tone: colors.primary, icon: 'checkmark-done-circle' },
    ];
  }, [colors.cyan, colors.error, colors.primary, colors.success, colors.warning, status, suggestions?.completed, suggestions?.safe_ready]);

  const topFindings = useMemo(() => (status?.findings || []).slice(0, 8), [status?.findings]);
  const previousRun = useMemo(() => {
    return history.find((run) => run?.run_id && run.run_id !== status?.run_id) || null;
  }, [history, status?.run_id]);

  const runDiff = useMemo(() => {
    if (!status || !previousRun) return null;
    const currentSeverity = status?.issues_by_severity || {};
    const previousSeverity = previousRun?.issues_by_severity || {};
    return {
      scoreDelta: Number(((status?.theme_guardrail_score || 0) - (previousRun?.theme_guardrail_score || 0)).toFixed(1)),
      issuesDelta: (status?.issues_total || 0) - (previousRun?.issues_total || 0),
      filesDelta: (status?.files_scanned || 0) - (previousRun?.files_scanned || 0),
      highDelta: (currentSeverity.high || 0) - (previousSeverity.high || 0),
      mediumDelta: (currentSeverity.medium || 0) - (previousSeverity.medium || 0),
      lowDelta: (currentSeverity.low || 0) - (previousSeverity.low || 0),
    };
  }, [previousRun, status]);

  const diffVerdict = useMemo(() => {
    if (!runDiff) return null;
    const improved = runDiff.scoreDelta > 0 || runDiff.issuesDelta < 0 || runDiff.highDelta < 0 || runDiff.mediumDelta < 0 || runDiff.lowDelta < 0;
    const regressed = runDiff.scoreDelta < 0 || runDiff.issuesDelta > 0 || runDiff.highDelta > 0 || runDiff.mediumDelta > 0 || runDiff.lowDelta > 0;
    if (regressed) {
      return {
        label: 'Regressed',
        description: 'Latest run shows at least one weaker signal compared with the previous baseline.',
        icon: 'warning',
        tone: colors.error || colors.error,
        bg: `${colors.error || colors.error}18`,
      };
    }
    if (improved) {
      return {
        label: 'Improved',
        description: 'Latest run improved on at least one tracked theme validation metric.',
        icon: 'trending-up',
        tone: colors.success || colors.success,
        bg: `${colors.success || colors.success}18`,
      };
    }
    return {
      label: 'Unchanged',
      description: 'Latest run is materially unchanged from the previous baseline.',
      icon: 'remove-circle',
      tone: colors.textMuted || colors.textMuted,
      bg: colors.bgSoft,
    };
  }, [colors.bgSoft, colors.error, colors.success, colors.textMuted, runDiff]);

  if (loading) {
    return (
      <View style={styles.loadingWrap} data-testid="theme-validation-loading" testID="theme-validation-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 10 }}>{tx('themeValidation.states.loading', 'Loading Theme Health Center…')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 16, paddingBottom: 40 }} data-testid="theme-validation-dashboard" testID="theme-validation-dashboard">
      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="theme-validation-hero-card" testID="theme-validation-hero-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{centerTitle === 'themeValidation.header.title' ? 'Theme Health Center' : centerTitle}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{tx('themeValidation.header.subtitle', 'Visual governance center for route parity, drift history, nightlies, and safe theme remediation workflows.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={() => loadDashboard('refresh')}
              disabled={refreshing}
              style={[styles.actionButton, { backgroundColor: colors.bgSoft, borderColor: colors.border }, refreshing && { opacity: 0.65 }]}
              data-testid="theme-validation-refresh-button"
              testID="theme-validation-refresh-button"
            >
              <Ionicons name="refresh" size={14} color={colors.text} />
              <Text style={[styles.actionButtonText, { color: colors.text }]}>{refreshing ? tx('themeValidation.actions.refreshing', 'Refreshing…') : tx('themeValidation.actions.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runValidation}
              disabled={runningValidation}
              style={[styles.actionButton, { backgroundColor: colors.primary, borderColor: colors.primary }, runningValidation && { opacity: 0.65 }]}
              data-testid="theme-validation-run-button"
              testID="theme-validation-run-button"
            >
              <Ionicons name="play" size={14} color="var(--app-primary-text)" />
              <Text style={[styles.actionButtonText, { color: colors.primaryText }]}>{runningValidation ? tx('themeValidation.actions.running', 'Running…') : tx('themeValidation.actions.runValidation', 'Run Validation')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runSafeAutofix}
              disabled={runningSafeAutofix}
              style={[styles.actionButton, { backgroundColor: colors.success || colors.success, borderColor: colors.success || colors.success }, runningSafeAutofix && { opacity: 0.65 }]}
              data-testid="theme-validation-safe-autofix-button"
              testID="theme-validation-safe-autofix-button"
            >
              <Ionicons name="construct" size={14} color="var(--app-primary-text)" />
              <Text style={[styles.actionButtonText, { color: colors.primaryText }]}>{runningSafeAutofix ? tx('themeValidation.actions.fixing', 'Fixing…') : tx('themeValidation.actions.runSafeAutofix', 'Run Safe Auto-Fix')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.summaryGrid} data-testid="theme-validation-summary-grid" testID="theme-validation-summary-grid">
          {summaryCards.map((card) => (
            <View key={card.id} style={[styles.summaryCard, { borderLeftColor: card.tone, backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid={`theme-validation-summary-${card.id}`} testID={`theme-validation-summary-${card.id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name={card.icon as any} size={15} color={card.tone} />
                <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{card.label}</Text>
              </View>
              <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', marginTop: 8 }}>{card.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-latest-run-pill" testID="theme-validation-latest-run-pill">
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.017', 'Latest Run:')}</Text>
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{status?.run_id || 'Not run yet'}</Text>
          </View>
          <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-checked-at-pill" testID="theme-validation-checked-at-pill">
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.018', 'Checked:')}</Text>
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{status?.checked_at ? new Date(status.checked_at).toLocaleString() : 'Never'}</Text>
          </View>
        </View>

        {message ? (
          <View style={[styles.messageCard, { backgroundColor: message.type === 'success' ? `${colors.success || colors.success}18` : `${colors.error || colors.error}18`, borderColor: message.type === 'success' ? `${colors.success || colors.success}40` : `${colors.error || colors.error}40` }]} data-testid="theme-validation-message" testID="theme-validation-message">
            <Ionicons name={message.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={message.type === 'success' ? colors.success || colors.success : colors.error || colors.error} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600', flex: 1 }}>{message.text}</Text>
          </View>
        ) : null}

        {/* Global theme controls */}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginRight: 4 }}>{tx('admin.themeValidationDashboard.auto.text.019', 'Live Theme:')}</Text>
          {(['light', 'system', 'dark'] as const).map(mode => {
            const active = themeMode === mode;
            return (
              <TouchableOpacity
                key={mode}
                onPress={() => setThemeMode(mode)}
                style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '14') : colors.surface }}
                data-testid={`theme-validation-global-${mode}`} testID={`theme-validation-global-${mode}`}
              >
                <Text style={{ color: active ? colors.primary : colors.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{mode}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* View mode controls */}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginRight: 4 }}>{tx('admin.themeValidationDashboard.auto.text.020', 'Preview:')}</Text>
          {(['side-by-side', 'light', 'dark'] as const).map(mode => {
            const active = viewMode === mode;
            const label = mode === 'side-by-side' ? 'Side-by-Side' : mode.charAt(0).toUpperCase() + mode.slice(1) + ' Only';
            return (
              <TouchableOpacity
                key={mode}
                onPress={() => setViewMode(mode)}
                style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: active ? colors.primary : colors.bgSoft }}
                data-testid={`theme-validation-view-${mode}`} testID={`theme-validation-view-${mode}`}
              >
                <Text style={{ color: active ? colors.text : colors.text, fontSize: 12, fontWeight: '700' }}>{label}</Text>
              </TouchableOpacity>
            );
          })}
          <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.bgSoft, marginLeft: 'auto' as any }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>
              Current: {darkMode ? 'Dark' : 'Light'}
            </Text>
          </View>
        </View>
      </View>

      <ThemeHealthCenterPanel overview={healthOverview} />

      <ThemeDriftTicketsPanel />

      <ThemeTokenRemediationPanel />

      <V2ComplianceGuardrailPanel />

      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="theme-validation-diff-card" testID="theme-validation-diff-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.themeValidationDashboard.auto.text.021', 'Latest Run Diff')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.themeValidationDashboard.auto.text.022', 'Compares the current Theme Guardrail run against the previous recorded run.')}</Text>
          </View>
          {previousRun ? (
            <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-diff-baseline-pill" testID="theme-validation-diff-baseline-pill">
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.023', 'Baseline:')}</Text>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{previousRun.run_id}</Text>
            </View>
          ) : null}
        </View>

        {runDiff ? (
          <>
            <View style={[styles.verdictBanner, { backgroundColor: diffVerdict?.bg, borderColor: `${diffVerdict?.tone}35` }]} data-testid="theme-validation-diff-verdict-banner" testID="theme-validation-diff-verdict-banner">
              <Ionicons name={(diffVerdict?.icon || 'remove-circle') as any} size={18} color={diffVerdict?.tone} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: diffVerdict?.tone, fontSize: 13, fontWeight: '800' }} data-testid="theme-validation-diff-verdict-label" testID="theme-validation-diff-verdict-label">{diffVerdict?.label}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} data-testid="theme-validation-diff-verdict-description" testID="theme-validation-diff-verdict-description">{diffVerdict?.description}</Text>
              </View>
            </View>

            <View style={styles.summaryGrid}>
            {[
              { id: 'score', label: 'Score Δ', value: `${runDiff.scoreDelta > 0 ? '+' : ''}${runDiff.scoreDelta}`, tone: runDiff.scoreDelta > 0 ? (colors.success || colors.success) : runDiff.scoreDelta < 0 ? (colors.error || colors.error) : (colors.textMuted || colors.textMuted), icon: 'speedometer', trend: runDiff.scoreDelta > 0 ? 'arrow-up' : runDiff.scoreDelta < 0 ? 'arrow-down' : 'remove' },
              { id: 'issues', label: 'Issues Δ', value: `${runDiff.issuesDelta > 0 ? '+' : ''}${runDiff.issuesDelta}`, tone: runDiff.issuesDelta < 0 ? (colors.success || colors.success) : runDiff.issuesDelta > 0 ? (colors.error || colors.error) : (colors.textMuted || colors.textMuted), icon: 'list', trend: runDiff.issuesDelta < 0 ? 'arrow-down' : runDiff.issuesDelta > 0 ? 'arrow-up' : 'remove' },
              { id: 'high', label: 'High Δ', value: `${runDiff.highDelta > 0 ? '+' : ''}${runDiff.highDelta}`, tone: runDiff.highDelta < 0 ? (colors.success || colors.success) : runDiff.highDelta > 0 ? (colors.error || colors.error) : (colors.textMuted || colors.textMuted), icon: 'alert-circle', trend: runDiff.highDelta < 0 ? 'arrow-down' : runDiff.highDelta > 0 ? 'arrow-up' : 'remove' },
              { id: 'medium', label: 'Medium Δ', value: `${runDiff.mediumDelta > 0 ? '+' : ''}${runDiff.mediumDelta}`, tone: runDiff.mediumDelta < 0 ? (colors.success || colors.success) : runDiff.mediumDelta > 0 ? (colors.warning || colors.warning) : (colors.textMuted || colors.textMuted), icon: 'alert', trend: runDiff.mediumDelta < 0 ? 'arrow-down' : runDiff.mediumDelta > 0 ? 'arrow-up' : 'remove' },
              { id: 'low', label: 'Low Δ', value: `${runDiff.lowDelta > 0 ? '+' : ''}${runDiff.lowDelta}`, tone: runDiff.lowDelta < 0 ? (colors.success || colors.success) : runDiff.lowDelta > 0 ? (colors.warning || colors.warning) : (colors.textMuted || colors.textMuted), icon: 'layers', trend: runDiff.lowDelta < 0 ? 'arrow-down' : runDiff.lowDelta > 0 ? 'arrow-up' : 'remove' },
              { id: 'files', label: 'Files Δ', value: `${runDiff.filesDelta > 0 ? '+' : ''}${runDiff.filesDelta}`, tone: colors.cyan || colors.primary, icon: 'documents', trend: runDiff.filesDelta > 0 ? 'arrow-up' : runDiff.filesDelta < 0 ? 'arrow-down' : 'remove' },
            ].map((metric) => (
              <View key={metric.id} style={[styles.summaryCard, { borderLeftColor: metric.tone, backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid={`theme-validation-diff-${metric.id}`} testID={`theme-validation-diff-${metric.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={metric.icon as any} size={15} color={metric.tone} />
                  <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{metric.label}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <Text style={{ color: metric.tone, fontSize: 18, fontWeight: '800', minWidth: 16, textAlign: 'center' }} data-testid={`theme-validation-diff-${metric.id}-arrow`} testID={`theme-validation-diff-${metric.id}-arrow`}>
                    {metric.trend === 'arrow-up' ? '↑' : metric.trend === 'arrow-down' ? '↓' : '→'}
                  </Text>
                  <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800' }}>{metric.value}</Text>
                </View>
              </View>
            ))}
            </View>
          </>
        ) : (
          <View style={[styles.findingRow, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-diff-empty" testID="theme-validation-diff-empty">
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.024', 'A second historical run is needed before a diff can be shown.')}</Text>
          </View>
        )}
      </View>

      {safeAutofixResult ? (
        <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 12 }} data-testid="theme-validation-safe-autofix-result" testID="theme-validation-safe-autofix-result">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Ionicons name="sparkles" size={18} color={colors.success || colors.success} />
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.themeValidationDashboard.auto.text.025', 'Latest Safe Auto-Fix Result')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <View style={[styles.inlineMetric, { backgroundColor: colors.bgSoft, borderColor: colors.border }]}>
              <Text style={inlineMetricLabelStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.026', 'Run ID')}</Text>
              <Text style={inlineMetricValueStyle(colors)}>{safeAutofixResult.run_id}</Text>
            </View>
            <View style={[styles.inlineMetric, { backgroundColor: colors.bgSoft, borderColor: colors.border }]}>
              <Text style={inlineMetricLabelStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.027', 'AI Applied')}</Text>
              <Text style={inlineMetricValueStyle(colors)}>{safeAutofixResult.ai_autofix?.total_applied ?? 0}</Text>
            </View>
            <View style={[styles.inlineMetric, { backgroundColor: colors.bgSoft, borderColor: colors.border }]}>
              <Text style={inlineMetricLabelStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.028', 'Theme Score')}</Text>
              <Text style={inlineMetricValueStyle(colors)}>{safeAutofixResult.theme_guardrail?.score ?? '--'}</Text>
            </View>
            <View style={[styles.inlineMetric, { backgroundColor: colors.bgSoft, borderColor: colors.border }]}>
              <Text style={inlineMetricLabelStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.029', 'Safe Ready')}</Text>
              <Text style={inlineMetricValueStyle(colors)}>{safeAutofixResult.suggestion_summary?.safe_ready ?? 0}</Text>
            </View>
          </View>
        </View>
      ) : null}

      <View style={styles.dualColumnWrap}>
        <View style={[styles.dataCard, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="theme-validation-findings-card" testID="theme-validation-findings-card">
          <Text style={cardTitleStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.030', 'Priority Findings')}</Text>
          <Text style={cardCopyStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.031', 'Top live findings from the most recent theme guardrail scan.')}</Text>
          <View style={{ gap: 10, marginTop: 14 }}>
            {topFindings.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.032', 'No findings in the latest run.')}</Text>
            ) : topFindings.map((finding: any, index: number) => {
              const severity = String(finding?.severity || 'low').toLowerCase();
              const tone = severity === 'high' ? (colors.error || colors.error) : severity === 'medium' ? (colors.warning || colors.warning) : (colors.success || colors.success);
              return (
                <View key={`${finding.file}-${finding.line}-${index}`} style={[styles.findingRow, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid={`theme-validation-finding-${index}`} testID={`theme-validation-finding-${index}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{finding.file}</Text>
                    <View style={[styles.severityBadge, { backgroundColor: `${tone}18` }]}>
                      <Text style={{ color: tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{severity}</Text>
                    </View>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{finding.message}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6 }}>Rule: {finding.rule || 'n/a'} · Line: {finding.line || '—'}</Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={[styles.dataCard, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="theme-validation-history-card" testID="theme-validation-history-card">
          <Text style={cardTitleStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.033', 'Recent Validation History')}</Text>
          <Text style={cardCopyStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.034', 'Latest theme guardrail runs with score and operator attribution.')}</Text>
          <View style={{ gap: 10, marginTop: 14 }}>
            {history.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.035', 'No validation history yet.')}</Text>
            ) : history.map((run: any, index: number) => {
              const pass = String(run?.status || '').toUpperCase() === 'PASS';
              return (
                <View key={run.run_id || index} style={[styles.findingRow, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid={`theme-validation-history-${index}`} testID={`theme-validation-history-${index}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{run.run_id}</Text>
                    <View style={[styles.severityBadge, { backgroundColor: pass ? `${colors.success || colors.success}18` : `${colors.warning || colors.warning}18` }]}>
                      <Text style={{ color: pass ? (colors.success || colors.success) : (colors.warning || colors.warning), fontSize: 10, fontWeight: '800' }}>{run.status}</Text>
                    </View>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>Score: {run.theme_guardrail_score ?? 0} · Issues: {run.issues_total ?? 0}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6 }}>{run.checked_at ? new Date(run.checked_at).toLocaleString() : 'Unknown time'} · {run.triggered_by || 'system'}</Text>
                </View>
              );
            })}
          </View>
        </View>
      </View>

      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="theme-validation-suggestions-card" testID="theme-validation-suggestions-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View>
            <Text style={cardTitleStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.036', 'Low-Severity Safe Auto-Fix Queue')}</Text>
            <Text style={cardCopyStyle(colors)}>{tx('admin.themeValidationDashboard.auto.text.037', 'Operator workflow for suggestions that are safe to auto-fix or mark complete.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-suggestions-total-pill" testID="theme-validation-suggestions-total-pill">
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.038', 'Total:')}</Text>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{suggestions?.total ?? 0}</Text>
            </View>
            <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-suggestions-safe-ready-pill" testID="theme-validation-suggestions-safe-ready-pill">
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.039', 'Safe Ready:')}</Text>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{suggestions?.safe_ready ?? 0}</Text>
            </View>
            <View style={[styles.pill, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid="theme-validation-suggestions-pending-pill" testID="theme-validation-suggestions-pending-pill">
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeValidationDashboard.auto.text.040', 'Pending:')}</Text>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{suggestions?.pending ?? 0}</Text>
            </View>
          </View>
        </View>

        <View style={{ gap: 10 }} data-testid="theme-validation-suggestions-list" testID="theme-validation-suggestions-list">
          {(suggestions?.suggestions || []).length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.themeValidationDashboard.auto.text.041', 'No low-severity suggestions available.')}</Text>
          ) : (suggestions?.suggestions || []).map((item: any, index: number) => (
            <View key={item.suggestion_id || index} style={[styles.findingRow, { backgroundColor: colors.bgSoft, borderColor: colors.border }]} data-testid={`theme-validation-suggestion-${index}`} testID={`theme-validation-suggestion-${index}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 220 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{item.title || item.rule}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{item.file}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{item.suggested_fix || item.message}</Text>
                </View>
                <View style={{ alignItems: 'flex-end', gap: 8 }}>
                  <View style={[styles.severityBadge, { backgroundColor: item.status === 'completed' ? `${colors.success || colors.success}18` : `${colors.warning || colors.warning}18` }]}>
                    <Text style={{ color: item.status === 'completed' ? (colors.success || colors.success) : (colors.warning || colors.warning), fontSize: 10, fontWeight: '800' }}>{String(item.status || 'pending').toUpperCase()}</Text>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>Occurrences: {item.occurrence_count ?? 0}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                {item.status === 'completed' ? (
                  <TouchableOpacity
                    onPress={() => updateSuggestionStatus(item.suggestion_id, 'reopen')}
                    disabled={savingSuggestionId === item.suggestion_id}
                    style={[styles.secondaryActionButton, { backgroundColor: colors.card, borderColor: colors.border }, savingSuggestionId === item.suggestion_id && { opacity: 0.65 }]}
                    data-testid={`theme-validation-suggestion-reopen-${index}`}
                    testID={`theme-validation-suggestion-reopen-${index}`}
                  >
                    <Text style={[styles.actionButtonText, { color: colors.text }]}>{savingSuggestionId === item.suggestion_id ? 'Updating…' : 'Reopen'}</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    onPress={() => updateSuggestionStatus(item.suggestion_id, 'mark-done')}
                    disabled={savingSuggestionId === item.suggestion_id}
                    style={[styles.secondaryActionButton, { backgroundColor: colors.card, borderColor: colors.border }, savingSuggestionId === item.suggestion_id && { opacity: 0.65 }]}
                    data-testid={`theme-validation-suggestion-done-${index}`}
                    testID={`theme-validation-suggestion-done-${index}`}
                  >
                    <Text style={[styles.actionButtonText, { color: colors.text }]}>{savingSuggestionId === item.suggestion_id ? 'Updating…' : 'Mark Done'}</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          ))}
        </View>
      </View>

      {/* Preview panels */}
      <View style={{ flexDirection: viewMode === 'side-by-side' ? 'row' : 'column', gap: 16, flexWrap: 'wrap' }}>
        {(viewMode === 'side-by-side' || viewMode === 'light') && (
          <ComponentPreviewCard title="Light Theme" colors={lightPreview} isDark={false} />
        )}
        {(viewMode === 'side-by-side' || viewMode === 'dark') && (
          <ComponentPreviewCard title="Dark Theme" colors={darkPreview} isDark />
        )}
      </View>

      {/* Color Palette Reference */}
      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 12 }}>
        <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.themeValidationDashboard.auto.text.042', 'Color Palette Reference (Live)')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {[
            { label: 'Primary', value: colors.primary },
            { label: 'BG', value: colors.bg },
            { label: 'Card', value: colors.card },
            { label: 'Text', value: colors.text },
            { label: 'Muted', value: colors.textMuted },
            { label: 'Border', value: colors.border },
            { label: 'Success', value: colors.success || colors.success },
            { label: 'Warning', value: colors.warning || colors.warning },
            { label: 'Error', value: colors.error || colors.error },
          ].map(c => (
            <View key={c.label} style={{ alignItems: 'center', gap: 4 }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: c.value, borderWidth: 1, borderColor: colors.border }} />
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700' }}>{c.label}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 8 }}>{c.value}</Text>
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  loadingWrap: {
    padding: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryActionButton: {
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  actionButtonText: {
    fontSize: 12,
    fontWeight: '800',
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  summaryCard: {
    flex: 1,
    minWidth: 180,
    borderRadius: 14,
    borderWidth: 1,
    borderLeftWidth: 3,
    padding: 14,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  messageCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  verdictBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  dualColumnWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  dataCard: {
    flex: 1,
    minWidth: 320,
    borderRadius: 18,
    borderWidth: 1,
    padding: 18,
  },
  findingRow: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 12,
  },
  severityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  inlineMetric: {
    minWidth: 130,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
});
