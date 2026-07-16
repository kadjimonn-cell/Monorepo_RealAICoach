import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

// Theme adapter — maps the v2 admin theme shape onto the short-name palette
// this panel uses. This mirrors the pattern used in AccessibilityPanel /
// CodeHealthPanel so that theme changes propagate via React state rather
// than relying solely on CSS-variable re-resolution.
function makeC(AC: any) {
  return {
    bg: AC.bg,
    bgSoft: AC.surfaceHover,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    primary: AC.primary,
    primarySoft: AC.primarySoft,
    success: AC.success,
    successSoft: AC.successSoft,
    warning: AC.warning,
    warningSoft: AC.warningSoft,
    error: AC.error,
    errorSoft: AC.errorSoft,
    cyan: AC.primary,
    purple: AC.accent || AC.primary,
  };
}

type LogItem = {
  task_id: string;
  title: string;
  category: string;
  status: string;
  actions_taken?: string[];
  fixes_applied?: string[];
  regressions_prevented?: string[];
  files_touched?: string[];
  notes?: string;
  actor?: string;
  created_at: string;
};

function Pill({ label, color, testId }: { label: string; color: string; testId?: string }) {
  return (
    <View
      style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(color, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '44') }}
      data-testid={testId} testID={testId}
    >
      <Text style={{ color, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
    </View>
  );
}

function Kpi({ label, value, color, testId }: { label: string; value: any; color: string; testId?: string }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  return (
    <View
      style={{ minWidth: 140, flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: color }}
      data-testid={testId} testID={testId}
    >
      <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
      <Text style={{ color: C.text, fontSize: 24, fontWeight: '900', marginTop: 4 }} data-testid={testId ? `${testId}-value` : undefined} testID={testId ? `${testId}-value` : undefined}>
        {value ?? '—'}
      </Text>
    </View>
  );
}

export default function GTECPanel() {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = React.useMemo(() => makeC(AC), [AC]);

  // Category / status color maps must live INSIDE the component so they
  // re-evaluate when the theme flips. (Previously these were module-scope
  // and captured stale CSS-var strings at import time.)
  const CATEGORY_COLOR: Record<string, string> = React.useMemo(() => ({
    feature: C.primary,
    bug_fix: C.warning,
    enhancement: C.cyan,
    regression: C.error,
    ops: C.textSec,
    integration: C.purple,
    guardrail: C.success,
    cleanup: C.textMuted,
  }), [C]);

  const STATUS_COLOR: Record<string, string> = React.useMemo(() => ({
    completed: C.success,
    in_progress: C.warning,
    rolled_back: C.error,
    blocked: C.error,
  }), [C]);

  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const [ov, h, l] = await Promise.all([
        api.get('/gtec/overview'),
        api.get('/gtec/health'),
        api.get('/gtec/logs?limit=50'),
      ]);
      setOverview(ov.data || null);
      setHealth(h.data || null);
      setLogs((l.data?.items as LogItem[]) || []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load GTEC');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <View style={{ paddingVertical: 60, alignItems: 'center' }} data-testid="gtec-loading" testID="gtec-loading">
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }

  const k = overview?.kpis || {};
  const overall = String(health?.overall || 'unknown').toLowerCase();
  const overallColor = overall === 'pass' ? C.success : overall === 'warning' ? C.warning : C.error;

  return (
    <View data-testid="gtec-panel" testID="gtec-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}>
            <Ionicons name="analytics" size={24} color={C.primary} />
          </View>
          <View>
            <Text style={{ color: C.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 }} data-testid="gtec-title" testID="gtec-title">
              {tx('admin.gtecPanel.header.title', 'GTEC — Global Task Enforcement Center')}
            </Text>
            <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 2 }}>
              {tx('admin.gtecPanel.header.subtitle', 'Central brain · task log · regression memory · live diagnostics')}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pill label={overall || 'unknown'} color={overallColor} testId="gtec-overall-pill" />
          <TouchableOpacity
            onPress={load}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}
            data-testid="gtec-refresh-btn" testID="gtec-refresh-btn"
          >
            <Ionicons name="refresh" size={14} color={C.textSec} />
            <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '600' }}>{tx('admin.gtecPanel.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {err ? (
        <View style={{ marginBottom: 12, padding: 10, borderRadius: 10, backgroundColor: C.errorSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '44') }} data-testid="gtec-error" testID="gtec-error">
          <Text style={{ color: C.error, fontSize: 12, fontWeight: '700' }}>{err}</Text>
        </View>
      ) : null}

      {/* KPI row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 }} data-testid="gtec-kpis" testID="gtec-kpis">
        <Kpi label="Total tasks" value={k.total_tasks ?? 0} color={C.primary} testId="gtec-kpi-total" />
        <Kpi label="Completed" value={k.completed ?? 0} color={C.success} testId="gtec-kpi-completed" />
        <Kpi label="In progress" value={k.in_progress ?? 0} color={C.warning} testId="gtec-kpi-inprogress" />
        <Kpi label="Rolled back" value={k.rolled_back ?? 0} color={C.error} testId="gtec-kpi-rolledback" />
        <Kpi label="Last 24h" value={k.last_24h ?? 0} color={C.cyan} testId="gtec-kpi-last24h" />
        <Kpi label="Regressions prevented" value={k.regressions_prevented ?? 0} color={C.purple} testId="gtec-kpi-regressions" />
        <Kpi label="Fixes applied" value={k.fixes_applied ?? 0} color={C.success} testId="gtec-kpi-fixes" />
      </View>

      {/* Two column: Health + Latest task */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12, marginBottom: 14 }}>
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="gtec-health-card" testID="gtec-health-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ionicons name="pulse" size={16} color={overallColor} />
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.gtecPanel.health.title', 'System health checks')}</Text>
          </View>
          {(health?.checks || []).map((chk: any, idx: number) => {
            const ok = !!chk.ok;
            return (
              <View
                key={chk.id || idx}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 7, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border }}
                data-testid={`gtec-health-row-${chk.id}`} testID={`gtec-health-row-${chk.id}`}
              >
                <Ionicons name={ok ? 'checkmark-circle' : 'close-circle'} size={14} color={ok ? C.success : C.error} />
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', minWidth: 140 }}>{chk.id}</Text>
                <Text style={{ color: C.textMuted, fontSize: 11, flex: 1 }} numberOfLines={2}>{chk.detail}</Text>
              </View>
            );
          })}
          <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 8 }}>
            Last task: {health?.last_task_at ? String(health.last_task_at).slice(0, 19).replace('T', ' ') : '—'}
          </Text>
        </View>

        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="gtec-latest-card" testID="gtec-latest-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ionicons name="flash" size={16} color={C.cyan} />
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.gtecPanel.latest.title', 'Latest task')}</Text>
          </View>
          {overview?.latest ? (
            <View>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }} data-testid="gtec-latest-title" testID="gtec-latest-title">
                {overview.latest.title}
              </Text>
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                <Pill label={overview.latest.category} color={CATEGORY_COLOR[overview.latest.category] || C.textSec} />
                <Pill label={overview.latest.status} color={STATUS_COLOR[overview.latest.status] || C.textSec} />
              </View>
              <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 8 }}>
                {String(overview.latest.created_at || '').slice(0, 19).replace('T', ' ')} · by {overview.latest.actor || 'system'}
              </Text>
              {overview.latest.notes ? (
                <Text style={{ color: C.textSec, fontSize: 11, marginTop: 6 }} numberOfLines={3}>{overview.latest.notes}</Text>
              ) : null}
            </View>
          ) : (
            <Text style={{ color: C.textMuted, fontSize: 12 }} data-testid="gtec-latest-empty" testID="gtec-latest-empty">
              {tx('admin.gtecPanel.latest.empty', 'No tasks logged yet. POST /api/gtec/log to record the first task.')}
            </Text>
          )}
        </View>
      </View>

      {/* Log feed */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid="gtec-log-feed" testID="gtec-log-feed">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="list" size={16} color={C.textSec} />
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.gtecPanel.logFeed.title', 'Task log feed')}</Text>
          </View>
          <Text style={{ color: C.textMuted, fontSize: 11 }}>{logs.length} rows</Text>
        </View>
        <ScrollView style={{ maxHeight: 520 }}>
          {logs.length === 0 ? (
            <View style={{ padding: 16, alignItems: 'center' }} data-testid="gtec-log-empty" testID="gtec-log-empty">
              <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('admin.gtecPanel.logFeed.empty', 'No tasks logged yet.')}</Text>
            </View>
          ) : (
            logs.map((row, idx) => {
              const catC = CATEGORY_COLOR[row.category] || C.textSec;
              const stC = STATUS_COLOR[row.status] || C.textSec;
              return (
                <View
                  key={row.task_id || idx}
                  style={{ paddingVertical: 10, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border }}
                  data-testid={`gtec-log-row-${idx}`} testID={`gtec-log-row-${idx}`}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', flex: 1 }} numberOfLines={1}>
                      {row.title}
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 6 }}>
                      <Pill label={row.category} color={catC} />
                      <Pill label={row.status} color={stC} />
                    </View>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 10, marginTop: 4, flexWrap: 'wrap' }}>
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>
                      {String(row.created_at || '').slice(0, 19).replace('T', ' ')}
                    </Text>
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>actor: {row.actor || 'system'}</Text>
                    {(row.fixes_applied?.length || 0) > 0 && (
                      <Text style={{ color: C.success, fontSize: 10, fontWeight: '700' }}>
                        {row.fixes_applied!.length} fix(es)
                      </Text>
                    )}
                    {(row.regressions_prevented?.length || 0) > 0 && (
                      <Text style={{ color: C.purple, fontSize: 10, fontWeight: '700' }}>
                        {row.regressions_prevented!.length} guardrail(s)
                      </Text>
                    )}
                    {(row.files_touched?.length || 0) > 0 && (
                      <Text style={{ color: C.cyan, fontSize: 10, fontWeight: '700' }}>
                        {row.files_touched!.length} file(s)
                      </Text>
                    )}
                  </View>
                  {row.notes ? (
                    <Text style={{ color: C.textSec, fontSize: 11, marginTop: 4 }} numberOfLines={2}>
                      {row.notes}
                    </Text>
                  ) : null}
                </View>
              );
            })
          )}
        </ScrollView>
      </View>

      <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 10, textAlign: 'center' }}>
        {tx('admin.gtecPanel.footer.copy', 'GTEC enforces the Global Execution Pipeline · Memory · Regression prevention · Real-time diagnostics')}
      </Text>
    </View>
  );
}
