/**
 * GtecCrawlerPanel
 * ----------------
 * Self-serve GTEC compliance panel shown inside Route Health Report.
 *
 * Features:
 *   - "Run GTEC Scan" one-click audit (desktop/mobile viewport toggle)
 *   - Live job polling (queued → running → complete/failed)
 *   - Latest report summary (pass/fail counts, pass-rate, top failures)
 *   - "Safe Auto Runs" toggle (scheduler runs every 6 hours server-side)
 *   - Scan history feed (last 20 runs)
 *
 * Backend: `/api/admin/gtec-crawler/*` (see routes/gtec_crawler_api.py).
 */
import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Totals = { scans: number; passing: number; failing: number; routes_scanned: number } | null;

type Job = {
  job_id: string;
  status: 'queued' | 'running' | 'complete' | 'failed';
  viewports: string;
  limit?: number | null;
  triggered_by?: string;
  actor?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  totals?: Totals;
};

type Failure = { url: string; viewport: string; category?: string; reasons: string[] };
type FailedApi = { url: string; status: number; count: number };

type ReportSummary = {
  generated_at?: string;
  frontend_base?: string;
  totals?: Totals;
  failures_by_category?: Record<string, number>;
  top_failures?: Failure[];
  top_failed_apis?: FailedApi[];
};

type Colors = {
  bg: string; card: string; cardAlt: string; border: string; text: string;
  muted: string; success: string; warn: string; danger: string;
};

type Props = {
  C: Colors;
  accent: string;
};

const tx = (_key: string, fallback: string) => fallback;

function fmtRelative(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch {
    return iso;
  }
}

export default function GtecCrawlerPanel({ C, accent }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [viewport, setViewport] = useState<'desktop' | 'mobile' | 'desktop,mobile'>('desktop');
  const [latest, setLatest] = useState<ReportSummary | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [autoRunHours, setAutoRunHours] = useState<number>(6);
  const [err, setErr] = useState<string>('');

  const loadLatest = useCallback(async () => {
    try {
      const res = await api.get('/admin/gtec-crawler/latest');
      setLatest(res.data?.report || null);
    } catch (_e: any) {
      /* silent — handled by parent forbidden/error flow */
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.get('/admin/gtec-crawler/history');
      setHistory(res.data?.items || []);
    } catch {
      /* silent */
    }
  }, []);

  const loadAutoRun = useCallback(async () => {
    try {
      const res = await api.get('/admin/gtec-crawler/auto-run');
      setAutoRunHours(Number(res.data?.interval_hours || 6));
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    void loadLatest();
    void loadHistory();
    void loadAutoRun();
  }, [loadLatest, loadHistory, loadAutoRun]);

  const runScan = async () => {
    setErr('Manual scan is disabled by autonomous policy.');
  };

  const toggleAutoRun = async (next: boolean) => {
    setErr('Runtime auto-run mutation is disabled by autonomous policy.');
  };

  const totals = latest?.totals;
  const passRate = useMemo(() => {
    if (!totals || !totals.scans) return null;
    return (totals.passing / totals.scans) * 100;
  }, [totals]);
  const passTone = passRate === null ? C.muted : passRate >= 80 ? C.success : passRate >= 60 ? C.warn : C.danger;

  const isRunning = false;

  return (
    <View
      data-testid="gtec-crawler-panel"
      testID="gtec-crawler-panel"
      style={{
        marginTop: 14,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: C.card,
        padding: 14,
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 10, flexWrap: 'wrap' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="shield-checkmark" size={18} color={accent} />
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.gtecCrawlerPanel.auto.text.001', 'GTEC Compliance Auditor')}</Text>
        </View>
        <Text style={{ color: C.muted, fontSize: 10 }} numberOfLines={1}>{tx('admin.gtecCrawlerPanel.auto.text.002', 'Live browser audit • headless Chromium')}</Text>
      </View>

      {/* Controls row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        {(['desktop', 'mobile', 'desktop,mobile'] as const).map((vp) => (
          <TouchableOpacity
            key={vp}
            onPress={() => setErr('Viewport override is disabled in autonomous mode.')}
            disabled={true}
            data-testid={`gtec-viewport-${vp.replace(',', '-')}`}
            testID={`gtec-viewport-${vp.replace(',', '-')}`}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 7,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: viewport === vp ? accent : C.border,
              backgroundColor: viewport === vp ? (globalThis as any).__alphaColor(accent, '18') : C.cardAlt,
              opacity: 0.5,
            }}
          >
            <Text style={{ color: viewport === vp ? accent : C.text, fontSize: 11, fontWeight: '700' }}>
              {vp === 'desktop,mobile' ? 'desktop + mobile' : vp}
            </Text>
          </TouchableOpacity>
        ))}

        <TouchableOpacity
          onPress={runScan}
          disabled={true}
          data-testid="gtec-run-scan-button"
          testID="gtec-run-scan-button"
          style={{
            marginLeft: 'auto' as any,
            paddingHorizontal: 14,
            paddingVertical: 9,
            borderRadius: 10,
            backgroundColor: C.cardAlt,
            borderWidth: 1,
            borderColor: C.border,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Ionicons name="lock-closed" size={13} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 12, fontWeight: '800' }}>
            Autonomous Only
          </Text>
        </TouchableOpacity>
      </View>

      {/* Auto-run */}
      <View
        data-testid="gtec-auto-run-row"
        testID="gtec-auto-run-row"
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          paddingHorizontal: 12,
          paddingVertical: 10,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.cardAlt,
          marginBottom: 12,
        }}
      >
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.gtecCrawlerPanel.auto.text.003', 'Safe Auto Runs')}</Text>
          <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
            Runs a desktop-only scan every {autoRunHours}h in autonomous mode.
          </Text>
        </View>
        <View data-testid="gtec-auto-run-toggle" testID="gtec-auto-run-toggle" style={{ borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '44'), backgroundColor: (globalThis as any).__alphaColor(C.success, '22'), paddingHorizontal: 10, paddingVertical: 4 }}>
          <Text style={{ color: C.success, fontSize: 10, fontWeight: '800' }}>LOCKED ON</Text>
        </View>
      </View>

      {err ? (
        <Text style={{ color: C.danger, fontSize: 11, marginBottom: 10 }} data-testid="gtec-error" testID="gtec-error">
          {err}
        </Text>
      ) : null}

      {/* Summary */}
      {totals ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <SmallStat C={C} label="Pass rate" value={passRate === null ? '—' : `${passRate.toFixed(1)}%`} tone={passTone} testId="gtec-pass-rate" />
          <SmallStat C={C} label="Passing" value={String(totals.passing)} tone={C.success} testId="gtec-pass-count" />
          <SmallStat C={C} label="Failing" value={String(totals.failing)} tone={totals.failing ? C.warn : C.success} testId="gtec-fail-count" />
          <SmallStat C={C} label="Unique routes" value={String(totals.routes_scanned)} tone={C.text} testId="gtec-routes-scanned" />
        </View>
      ) : (
        <Text style={{ color: C.muted, fontSize: 11, marginBottom: 12 }} data-testid="gtec-no-report-yet" testID="gtec-no-report-yet">{tx('admin.gtecCrawlerPanel.auto.text.004', 'No scan has been run yet. Click "Run GTEC Scan" to capture your first compliance snapshot.')}</Text>
      )}

      {/* Last run meta */}
      {latest ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Ionicons name="time-outline" size={12} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 10 }} data-testid="gtec-latest-generated-at" testID="gtec-latest-generated-at">
            Last scan {fmtRelative(latest.generated_at)}
          </Text>
        </View>
      ) : null}

      {/* Top failures */}
      {Array.isArray(latest?.top_failures) && latest!.top_failures!.length > 0 ? (
        <View data-testid="gtec-top-failures" testID="gtec-top-failures" style={{ marginBottom: 12 }}>
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>
            Top failures ({latest!.top_failures!.length})
          </Text>
          {latest!.top_failures!.slice(0, 6).map((f, idx) => (
            <View
              key={`${f.url}-${f.viewport}-${idx}`}
              data-testid={`gtec-top-failure-${idx}`}
              testID={`gtec-top-failure-${idx}`}
              style={{
                borderWidth: 1,
                borderColor: C.border,
                borderRadius: 10,
                backgroundColor: C.cardAlt,
                paddingHorizontal: 10,
                paddingVertical: 7,
                marginTop: idx ? 6 : 0,
              }}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }} numberOfLines={1}>{f.url}</Text>
                <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{f.viewport}</Text>
              </View>
              <Text style={{ color: C.warn, fontSize: 10, marginTop: 3 }}>{(f.reasons || []).join(' • ') || '—'}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Top failed APIs */}
      {Array.isArray(latest?.top_failed_apis) && latest!.top_failed_apis!.length > 0 ? (
        <View data-testid="gtec-top-apis" testID="gtec-top-apis" style={{ marginBottom: 12 }}>
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.gtecCrawlerPanel.auto.text.005', 'Top failed API calls')}</Text>
          {latest!.top_failed_apis!.slice(0, 5).map((a, idx) => (
            <View
              key={`${a.url}-${a.status}-${idx}`}
              data-testid={`gtec-top-api-${idx}`}
              testID={`gtec-top-api-${idx}`}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 8,
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderWidth: 1,
                borderColor: C.border,
                borderRadius: 10,
                backgroundColor: C.cardAlt,
                marginTop: idx ? 6 : 0,
              }}
            >
              <Text style={{ color: a.status >= 500 ? C.danger : C.warn, fontSize: 10, fontWeight: '900', minWidth: 30 }}>
                {a.status}
              </Text>
              <Text style={{ color: C.text, fontSize: 10, flex: 1 }} numberOfLines={1}>
                {(a.url || '').replace(latest?.frontend_base || '', '')}
              </Text>
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>×{a.count}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* History */}
      {history.length > 0 ? (
        <View data-testid="gtec-history" testID="gtec-history">
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.gtecCrawlerPanel.auto.text.006', 'Recent scans')}</Text>
          {history.slice(0, 5).map((h, idx) => {
            const t: any = h.totals;
            const label = t ? `${t.passing}/${t.scans} pass` : '—';
            const tone = h.status === 'complete' ? C.success : h.status === 'failed' ? C.danger : C.muted;
            return (
              <View
                key={h.job_id}
                data-testid={`gtec-history-${idx}`}
                testID={`gtec-history-${idx}`}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 8,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  borderWidth: 1,
                  borderColor: C.border,
                  borderRadius: 10,
                  backgroundColor: C.cardAlt,
                  marginTop: idx ? 5 : 0,
                }}
              >
                <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: tone }} />
                <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{h.triggered_by || 'manual'}</Text>
                <Text style={{ color: C.muted, fontSize: 10 }}>{h.viewports}</Text>
                <Text style={{ color: C.text, fontSize: 10, fontWeight: '700', marginLeft: 'auto' as any }}>{label}</Text>
                <Text style={{ color: C.muted, fontSize: 10 }}>{fmtRelative(h.started_at || (h as any).created_at)}</Text>
              </View>
            );
          })}
        </View>
      ) : null}

      <GtecAlertsSection C={C} accent={accent} />
    </View>
  );
}

// ─── Alerts section ─────────────────────────────────────────────────────

type AlertSettings = {
  email_enabled: boolean;
  email_recipients: string[];
  slack_webhook_url: string;
  pass_rate_drop_pct: number;
  absolute_fail_delta: number;
  cooldown_hours: number;
};

type AlertHistoryItem = {
  fingerprint: string;
  job_id?: string;
  reasons: string[];
  channels_sent: string[];
  sent_at?: string;
};

function GtecAlertsSection({ C, accent }: { C: Colors; accent: string }) {
  const [settings, setSettings] = React.useState<AlertSettings | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [history, setHistory] = React.useState<AlertHistoryItem[]>([]);
  const [err, setErr] = React.useState('');
  const [okMsg, setOkMsg] = React.useState('');
  const [expanded, setExpanded] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        api.get('/admin/gtec-crawler/alerts/settings'),
        api.get('/admin/gtec-crawler/alerts/history'),
      ]);
      setSettings(s.data || null);
      setHistory(Array.isArray(h.data?.items) ? h.data.items : []);
    } catch { /* silent */ }
  }, []);

  React.useEffect(() => { void load(); }, [load]);

  const save = async (patch: Partial<AlertSettings>) => {
    setErr('Alert settings are policy-managed and immutable at runtime.');
  };

  const testAlert = async () => {
    setErr('Manual alert testing is disabled by autonomous policy.');
  };

  if (!settings) return null;

  return (
    <View data-testid="gtec-alerts-section" testID="gtec-alerts-section" style={{ marginTop: 14, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardAlt, padding: 12 }}>
      <TouchableOpacity
        onPress={() => setExpanded((v) => !v)}
        data-testid="gtec-alerts-toggle-expand"
        testID="gtec-alerts-toggle-expand"
        style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="notifications-outline" size={14} color={accent} />
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('admin.gtecCrawlerPanel.auto.text.007', 'Regression alerts')}</Text>
          {settings.email_enabled || settings.slack_webhook_url ? (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '22'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
              <Text style={{ color: C.success, fontSize: 9, fontWeight: '800' }}>{tx('admin.gtecCrawlerPanel.auto.text.008', 'ARMED')}</Text>
            </View>
          ) : (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.muted, '22'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
              <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800' }}>{tx('admin.gtecCrawlerPanel.auto.text.009', 'OFF')}</Text>
            </View>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={C.muted} />
      </TouchableOpacity>

      {expanded ? (
        <View style={{ marginTop: 12, gap: 10 }}>
          <Text data-testid="gtec-alerts-policy-lock-note" testID="gtec-alerts-policy-lock-note" style={{ color: C.muted, fontSize: 10 }}>
            Alert channels and thresholds are managed by platform policy (read-only here).
          </Text>
          {/* Email toggle + recipients */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{tx('admin.gtecCrawlerPanel.auto.text.010', 'Email alerts')}</Text>
            <Switch
              value={settings.email_enabled}
              onValueChange={() => save({})}
              disabled={true}
              data-testid="gtec-alerts-email-toggle"
              testID="gtec-alerts-email-toggle"
            />
          </View>
          <TextInput accessibilityLabel={tx('admin.gtecCrawlerPanel.auto.accessibility.001', 'ops@example.com, alerts@example.com')}
            value={(settings.email_recipients || []).join(', ')}
            editable={false}
            onChangeText={() => undefined}
            onBlur={() => undefined}
            placeholder={tx('admin.gtecCrawlerPanel.auto.placeholder.001', 'ops@example.com, alerts@example.com')}
            placeholderTextColor={C.muted}
            data-testid="gtec-alerts-email-recipients"
            testID="gtec-alerts-email-recipients"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, color: C.text, fontSize: 11 }}
          />

          {/* Slack webhook */}
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{tx('admin.gtecCrawlerPanel.auto.text.011', 'Slack webhook')}</Text>
          <TextInput accessibilityLabel="Text input"
            value={settings.slack_webhook_url}
            editable={false}
            onChangeText={() => undefined}
            onBlur={() => undefined}
            placeholder={tx('admin.gtecCrawlerPanel.auto.placeholder.002', 'https://hooks.slack.com/services/…')}
            placeholderTextColor={C.muted}
            data-testid="gtec-alerts-slack-webhook"
            testID="gtec-alerts-slack-webhook"
            autoCapitalize="none"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, color: C.text, fontSize: 11 }}
          />

          {/* Thresholds */}
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <ThresholdInput C={C} label="Pass-rate drop ≥" suffix="pts" value={settings.pass_rate_drop_pct} onChange={() => undefined} testId="gtec-alerts-threshold-rate" readOnly={true} />
            <ThresholdInput C={C} label="Fail count +" suffix="" value={settings.absolute_fail_delta} onChange={() => undefined} testId="gtec-alerts-threshold-fail" readOnly={true} />
            <ThresholdInput C={C} label="Cool-down" suffix="h" value={settings.cooldown_hours} onChange={() => undefined} testId="gtec-alerts-threshold-cooldown" readOnly={true} />
          </View>

          {/* Test button */}
          <TouchableOpacity
            onPress={testAlert}
            disabled={true}
            data-testid="gtec-alerts-test-btn"
            testID="gtec-alerts-test-btn"
            style={{ backgroundColor: C.card, borderWidth: 1, borderColor: accent, borderRadius: 10, paddingVertical: 9, alignItems: 'center', opacity: 0.6 }}
          >
            <Text style={{ color: accent, fontSize: 11, fontWeight: '800' }}>{tx('admin.gtecCrawlerPanel.auto.text.012', 'Send test alert')}</Text>
          </TouchableOpacity>

          {okMsg ? <Text style={{ color: C.success, fontSize: 10 }} data-testid="gtec-alerts-ok" testID="gtec-alerts-ok">{okMsg}</Text> : null}
          {err ? <Text style={{ color: C.danger, fontSize: 10 }} data-testid="gtec-alerts-err" testID="gtec-alerts-err">{err}</Text> : null}

          {/* Recent alerts */}
          {history.length > 0 ? (
            <View data-testid="gtec-alerts-history" testID="gtec-alerts-history" style={{ marginTop: 6 }}>
              <Text style={{ color: C.text, fontSize: 10, fontWeight: '700', marginBottom: 4 }}>{tx('admin.gtecCrawlerPanel.auto.text.013', 'Recent alerts')}</Text>
              {history.slice(0, 3).map((h, idx) => (
                <View key={h.fingerprint + idx} data-testid={`gtec-alerts-history-${idx}`} testID={`gtec-alerts-history-${idx}`} style={{ paddingVertical: 5, borderTopWidth: idx ? 1 : 0, borderColor: C.border }}>
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>
                    {(h.reasons || []).join(' • ') || h.fingerprint}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 9 }}>
                    via {(h.channels_sent || []).join(', ') || '—'} · {fmtRelative(h.sent_at)}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function SmallStat({ C, label, value, tone, testId }: { C: Colors; label: string; value: string; tone: string; testId: string }) {  return (
    <View
      data-testid={testId}
      testID={testId}
      style={{
        flexBasis: '23%',
        minWidth: 110,
        flexGrow: 1,
        borderWidth: 1,
        borderColor: C.border,
        borderRadius: 10,
        backgroundColor: C.cardAlt,
        paddingHorizontal: 10,
        paddingVertical: 9,
      }}
    >
      <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '800', letterSpacing: 0.5 }}>{label}</Text>
      <Text style={{ color: tone, fontSize: 17, fontWeight: '900', marginTop: 4 }}>{value}</Text>
    </View>
  );
}

function ThresholdInput({ C, label, suffix, value, onChange, testId, readOnly = false }: { C: Colors; label: string; suffix: string; value: number; onChange: (n: number) => void; testId: string; readOnly?: boolean }) {
  const [txt, setTxt] = useState<string>(String(value ?? ''));
  useEffect(() => { setTxt(String(value ?? '')); }, [value]);
  return (
    <View style={{ flex: 1, minWidth: 100 }}>
      <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase', marginBottom: 3 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 8 }}>
        <TextInput accessibilityLabel={tx('admin.gtecCrawlerPanel.auto.accessibility.002', 'Text input')}
          value={txt}
          editable={!readOnly}
          onChangeText={setTxt}
          onBlur={() => {
            if (readOnly) {
              setTxt(String(value));
              return;
            }
            const n = parseInt(txt, 10);
            if (Number.isFinite(n) && n > 0) onChange(n);
            else setTxt(String(value));
          }}
          keyboardType="numeric"
          data-testid={testId}
          testID={testId}
          style={{ flex: 1, paddingHorizontal: 8, paddingVertical: 6, color: C.text, fontSize: 11 }}
        />
        {suffix ? <Text style={{ color: C.muted, fontSize: 10, paddingRight: 8 }}>{suffix}</Text> : null}
      </View>
    </View>
  );
}
