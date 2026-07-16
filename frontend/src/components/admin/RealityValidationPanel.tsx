import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const statusColor = (status: string) => {
  const s = String(status || '').toUpperCase();
  if (s === 'PASS' || s === 'HIGH') return 'var(--app-success)';
  if (s === 'MEDIUM') return 'var(--app-warning)';
  return 'var(--app-error)';
};

export default function RealityValidationPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [windowHours, setWindowHours] = useState<number>(24);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async (forceRun = false) => {
    try {
      if (!forceRun) setLoading(true);
      setError(null);
      const res = await api.get('/admin/autonomous-engine/reality-validation/dashboard', {
        params: { hours: windowHours, force_run: forceRun },
        silentLoading: true,
      });
      setData(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load reality validation dashboard');
    } finally {
      setLoading(false);
      setRunning(false);
    }
  }, [windowHours]);

  const runNow = async () => {
    if (running) return;
    setRunning(true);
    try {
      await api.post('/admin/autonomous-engine/reality-validation/run', null, {
        params: { hours: windowHours },
      });
      await loadDashboard(true);
    } catch (e: any) {
      setRunning(false);
      setError(e?.response?.data?.detail || e?.message || 'Failed to run reality validation');
    }
  };

  useEffect(() => {
    loadDashboard(false);
  }, [loadDashboard]);

  const refreshSeconds = Number(data?.policy?.auto_refresh_seconds || 30);
  const refreshMs = Math.max(10, refreshSeconds) * 1000;

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/reality-validation/hybrid-refresh',
    onTick: () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      return loadDashboard(false);
    },
    runOnMount: false,
    slowIntervalMs: refreshMs,
    fastIntervalMs: Math.max(10000, Math.floor(refreshMs / 2)),
  });

  const latest = data?.latest || {};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const categories = latest?.categories || {};
  const evidence = latest?.evidence || {};
  const mandatoryScenarios = latest?.mandatory_scenarios || {};
  const skippedScenarios = latest?.skipped_scenarios || [];
  const failedScenarios = latest?.failed_scenarios || [];
  const history = data?.recent_history || [];

  const orderedCategories = useMemo(() => {
    const keys = [
      'real_world_scenarios',
      'negative_testing',
      'ux_quality',
      'regression',
      'independent_validation',
    ];
    return keys.map((key) => ({
      key,
      label: key.replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase()),
      status: categories?.[key]?.status || 'FAIL',
      checks: categories?.[key]?.checks || [],
    }));
  }, [categories]);

  const primaryTintSoft = (globalThis as any).__alphaColor(colors.primary, '22');
  const primaryTintStrong = (globalThis as any).__alphaColor(colors.primary, '66');

  return (
    <ScrollView style={{ flex: 1, padding: 16 }} contentContainerStyle={{ paddingBottom: 40 }} data-testid="reality-validation-panel" testID="reality-validation-panel">
      <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="reality-validation-header" testID="reality-validation-header">
        <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }} data-testid="reality-validation-title" testID="reality-validation-title">{tx('admin.realityValidationPanel.header.title', 'Reality Validation Panel')}</Text>
        <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 4 }} data-testid="reality-validation-subtitle" testID="reality-validation-subtitle">
          {tx('admin.realityValidationPanel.header.subtitle', 'PASS only when all categories pass, mandatory evidence exists, and confidence is HIGH.')}
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, minWidth: 130 }} data-testid="reality-status-card" testID="reality-status-card">
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.realityValidationPanel.cards.status', 'Reality Status')}</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: statusColor(data?.reality_status) }} data-testid="reality-status-value" testID="reality-status-value">{data?.reality_status || 'FAIL'}</Text>
          </View>
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, minWidth: 130 }} data-testid="reality-confidence-card" testID="reality-confidence-card">
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.realityValidationPanel.cards.confidence', 'Confidence')}</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: statusColor(data?.confidence) }} data-testid="reality-confidence-value" testID="reality-confidence-value">{data?.confidence || 'LOW'}</Text>
          </View>
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, minWidth: 130 }} data-testid="reality-evidence-card" testID="reality-evidence-card">
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.realityValidationPanel.cards.evidence', 'Evidence')}</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: latest?.evidence_complete ? 'var(--app-success)' : 'var(--app-error)' }} data-testid="reality-evidence-value" testID="reality-evidence-value">{latest?.evidence_complete ? 'COMPLETE' : 'MISSING'}</Text>
          </View>
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, minWidth: 150 }} data-testid="reality-scenarios-card" testID="reality-scenarios-card">
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.realityValidationPanel.cards.scenarios', 'Scenarios')}</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: latest?.mandatory_scenarios_pass ? 'var(--app-success)' : 'var(--app-error)' }} data-testid="reality-scenarios-value" testID="reality-scenarios-value">{latest?.mandatory_scenarios_pass ? 'ALL PASSED' : 'FAILED/SKIPPED'}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          {[24, 168].map((hrs) => (
            <button
              key={hrs}
              onClick={() => setWindowHours(hrs)}
              style={{
                borderRadius: 8,
                border: `1px solid ${windowHours === hrs ? 'var(--app-primary)' : colors.border}`,
                backgroundColor: windowHours === hrs ? 'var(--app-primary)' : colors.surface,
                color: windowHours === hrs ? colors.primaryText : colors.text,
                padding: '8px 12px',
                fontSize: 11,
                fontWeight: 700,
                cursor: 'pointer',
              }}
              data-testid={`reality-window-${hrs}`}
            >
              {hrs === 24 ? '24h' : '7d'}
            </button>
          ))}
          <button onClick={() => loadDashboard(false)} style={{ borderRadius: 8, border: `1px solid ${colors.border}`, backgroundColor: primaryTintSoft, color: colors.primary, padding: '8px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }} data-testid="reality-refresh-button">Refresh</button>
          <button onClick={runNow} disabled={running} style={{ borderRadius: 8, border: `1px solid ${colors.border}`, backgroundColor: running ? primaryTintStrong : colors.primary, color: colors.primaryText, padding: '8px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }} data-testid="reality-run-now-button">{running ? 'Running…' : 'Run Validation Now'}</button>
        </View>
      </View>

      {error && <Text style={{ marginTop: 10, color: 'var(--app-error)', fontSize: 12 }} data-testid="reality-error-text" testID="reality-error-text">{error}</Text>} {/* @theme-ok residual semantic hex (reviewed) */}
      {loading && <Text style={{ marginTop: 10, color: colors.textMuted, fontSize: 12 }} data-testid="reality-loading-text" testID="reality-loading-text">{tx('admin.realityValidationPanel.states.loadingEvidence', 'Loading reality validation evidence…')}</Text>}

      <View style={{ marginTop: 12, backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="reality-categories-section" testID="reality-categories-section">
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 10 }} data-testid="reality-categories-title" testID="reality-categories-title">{tx('admin.realityValidationPanel.categories.title', 'Validation Categories')}</Text>
        {orderedCategories.map((cat, idx) => (
          <View key={cat.key} style={{ borderBottomWidth: idx < orderedCategories.length - 1 ? 1 : 0, borderBottomColor: colors.border, paddingVertical: 8 }} data-testid={`reality-category-${cat.key}`} testID={`reality-category-${cat.key}`}>
            <Text style={{ fontSize: 12, color: colors.text, fontWeight: '700' }} data-testid={`reality-category-label-${cat.key}`} testID={`reality-category-label-${cat.key}`}>{cat.label}</Text>
            <Text style={{ fontSize: 11, fontWeight: '800', color: statusColor(cat.status) }} data-testid={`reality-category-status-${cat.key}`} testID={`reality-category-status-${cat.key}`}>{cat.status}</Text>
            <Text style={{ fontSize: 10, color: colors.textMuted }} data-testid={`reality-category-checks-${cat.key}`} testID={`reality-category-checks-${cat.key}`}>{cat.checks.filter((c: any) => c?.pass).length}/{cat.checks.length} checks passed</Text>
          </View>
        ))}
      </View>

      <View style={{ marginTop: 12, backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="reality-scenarios-section" testID="reality-scenarios-section">
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 6 }} data-testid="reality-scenarios-title" testID="reality-scenarios-title">{tx('admin.realityValidationPanel.scenarios.title', 'Mandatory Real-World Scenario Execution')}</Text>
        <Text style={{ fontSize: 11, color: colors.textMuted, marginBottom: 8 }} data-testid="reality-scenarios-subtitle" testID="reality-scenarios-subtitle">{tx('admin.realityValidationPanel.scenarios.subtitle', 'If any scenario fails or is skipped, status must remain FAIL.')}</Text>
        {Object.entries(mandatoryScenarios).map(([key, item], idx, arr) => (
          <View key={key} style={{ borderBottomWidth: idx < arr.length - 1 ? 1 : 0, borderBottomColor: colors.border, paddingVertical: 8 }} data-testid={`reality-scenario-${key}`} testID={`reality-scenario-${key}`}>
            <Text style={{ fontSize: 12, color: colors.text, fontWeight: '700' }} data-testid={`reality-scenario-label-${key}`} testID={`reality-scenario-label-${key}`}>{item?.label || key}</Text>
            <Text style={{ fontSize: 11, color: item?.executed ? 'var(--app-success)' : 'var(--app-error)', fontWeight: '700' }} data-testid={`reality-scenario-executed-${key}`} testID={`reality-scenario-executed-${key}`}>{item?.executed ? 'EXECUTED' : 'SKIPPED'}</Text>
            <Text style={{ fontSize: 11, color: item?.pass ? 'var(--app-success)' : 'var(--app-error)', fontWeight: '700' }} data-testid={`reality-scenario-pass-${key}`} testID={`reality-scenario-pass-${key}`}>{item?.pass ? 'PASS' : 'FAIL'}</Text>
          </View>
        ))}
        <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 8 }} data-testid="reality-scenarios-summary" testID="reality-scenarios-summary">Skipped: {skippedScenarios.length} · Failed: {failedScenarios.length}</Text>
      </View>

      <View style={{ marginTop: 12, backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="reality-evidence-section" testID="reality-evidence-section">
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 10 }} data-testid="reality-evidence-title" testID="reality-evidence-title">{tx('admin.realityValidationPanel.evidence.title', 'Mandatory Evidence')}</Text>
        {[
          { key: 'api_logs', label: 'API logs' },
          { key: 'latency_metrics', label: 'Latency metrics' },
          { key: 'screenshots', label: 'Screenshots' },
          { key: 'error_logs', label: 'Error logs' },
        ].map((item, idx, arr) => {
          const ev = evidence?.[item.key] || {};
          return (
            <View key={item.key} style={{ borderBottomWidth: idx < arr.length - 1 ? 1 : 0, borderBottomColor: colors.border, paddingVertical: 8 }} data-testid={`reality-evidence-${item.key}`} testID={`reality-evidence-${item.key}`}>
              <Text style={{ fontSize: 12, color: colors.text, fontWeight: '700' }}>{item.label}</Text>
              <Text style={{ fontSize: 11, fontWeight: '800', color: ev.present ? 'var(--app-success)' : 'var(--app-error)' }} data-testid={`reality-evidence-status-${item.key}`} testID={`reality-evidence-status-${item.key}`}>{ev.present ? 'PRESENT' : 'MISSING'}</Text>
              <Text style={{ fontSize: 10, color: colors.textMuted }} data-testid={`reality-evidence-meta-${item.key}`} testID={`reality-evidence-meta-${item.key}`}>samples: {Number(ev.sample_count || ev.error_line_count || 0)}</Text>
            </View>
          );
        })}
      </View>

      <View style={{ marginTop: 12, backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="reality-history-section" testID="reality-history-section">
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 10 }} data-testid="reality-history-title" testID="reality-history-title">{tx('admin.realityValidationPanel.history.title', 'Recent Validation History')}</Text>
        {history.slice(0, 8).map((row: any, idx: number) => (
          <View key={row.run_id || idx} style={{ borderBottomWidth: idx < Math.min(7, history.length - 1) ? 1 : 0, borderBottomColor: colors.border, paddingVertical: 8 }} data-testid={`reality-history-row-${idx}`} testID={`reality-history-row-${idx}`}>
            <Text style={{ fontSize: 11, color: colors.text, fontWeight: '700' }} data-testid={`reality-history-status-${idx}`} testID={`reality-history-status-${idx}`}>{row.reality_status} · {row.confidence}</Text>
            <Text style={{ fontSize: 10, color: colors.textMuted }} data-testid={`reality-history-time-${idx}`} testID={`reality-history-time-${idx}`}>{row.evaluated_at || row.created_at}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
