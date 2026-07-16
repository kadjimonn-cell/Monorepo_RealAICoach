/* residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
/**
 * AdminHealthDigestWidget — 7-day digest history surface.
 *
 * Reads ``GET /api/admin/health-digest/history?days=7`` (backed by
 * ``db.admin_health_digest_log``) so the in-console view shows the same
 * thing that landed in the admin inbox this morning. Each row renders
 * severity, title, crash count, healthy/total route ratio, and the top
 * 3 offending panels. A "Run digest now" button triggers an on-demand
 * run for immediate re-preview.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { humanizeAdminToken, normalizeAdminRuntimeCopy, normalizeAdminStatusTone } from '../../i18n/adminCopyGuard';

type DigestRow = {
  generated_at: string;
  severity: 'warning' | 'critical' | 'info';
  title: string;
  summary: string;
  total_errors_24h: number;
  healthy_routes: number;
  total_routes: number;
  unhealthy_routes: string[];
  top_panels: {
    panel_id: string;
    panel_name?: string;
    count: number;
    unique_clients: number;
  }[];
  dispatched: boolean;
  email_sent: boolean;
  theme_audit?: {
    files_scanned?: number;
    files_with_violations?: number;
    files_theme_compliant?: number;
    p0_violations?: number;
    status?: 'pass' | 'fail' | 'unknown';
  };
};

type ThemeAuditSnapshot = {
  files_scanned: number;
  files_with_violations: number;
  files_theme_compliant: number;
  p0_violations: number;
  status: 'pass' | 'fail' | 'unknown';
  violations_by_category?: Record<string, number>;
  files_by_priority?: Record<string, number>;
  error?: string;
};

const severityColor = (s: string, c: any) =>
  s === 'critical' ? (c?.errorText || 'var(--app-error)')
  : s === 'warning' ? (c?.warningText || 'var(--app-warning)')
  : (c?.successText || 'var(--app-success)');

interface Props { colors: any; }

export default function AdminHealthDigestWidget({ colors }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [rows, setRows] = useState<DigestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [themeAudit, setThemeAudit] = useState<ThemeAuditSnapshot | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/health-digest/history?days=7');
      setRows(((res.data as any)?.history) || []);
    } catch (e: any) {
      setStatus(`Failed to load: ${e?.message || 'unknown'}`);
    } finally {
      setLoading(false);
    }
    try {
      const audit = await api.get('/admin/code-health/theme-audit');
      setThemeAudit(audit.data as ThemeAuditSnapshot);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AdminHealthDigestWidget.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const runNow = useCallback(async () => {
    setBusy(true);
    setStatus(null);
    try {
      await api.post('/admin/health-digest/trigger');
      await load();
      setStatus('Digest fired — email sent and history refreshed.');
    } catch (e: any) {
      setStatus(`Trigger failed: ${e?.response?.data?.detail || e?.message || 'unknown'}`);
    } finally {
      setBusy(false);
    }
  }, [load]);

  useEffect(() => { void load(); }, [load]);

  const border = colors?.border || 'var(--app-text)';
  const cardBg = colors?.card || 'var(--app-text)';
  const text = colors?.text || 'var(--app-primary)';
  const muted = colors?.textMuted || 'var(--app-text-muted)';
  const accent = colors?.primary || 'var(--app-primary)';

  return (
    <View
      style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 16, gap: 10 }}
      data-testid="admin-health-digest-widget"
      testID="admin-health-digest-widget"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="calendar" size={16} color={accent} />
        <Text style={{ color: text, fontSize: 14, fontWeight: '700', flex: 1 }}>
          {tx('admin.adminHealthDigest.header.title', 'Admin Health Digest — last 7 days')}
        </Text>
        {themeAudit ? (() => {
          const ok = themeAudit.status === 'pass';
          const pillColor = ok ? (colors?.successText || 'var(--app-success)') : (colors?.errorText || 'var(--app-error)');
          const compliantPct = Math.round((themeAudit.files_theme_compliant / Math.max(1, themeAudit.files_scanned)) * 100);
          const filesViol = themeAudit.files_with_violations || 0;
          const label = ok
            ? `V2 theme ${compliantPct}% ✓ · 0 files`
            : `V2 theme · ${themeAudit.p0_violations} P0 · ${filesViol} files`;

          // Build 7-day sparkline from oldest→newest row `theme_audit.files_with_violations`.
          // De-duplicate by calendar day (keep the latest snapshot per day).
          const byDay = new Map<string, number>();
          rows.forEach((r) => {
            const v = r.theme_audit?.files_with_violations;
            if (typeof v !== 'number' || !r.generated_at) return;
            const day = r.generated_at.slice(0, 10);
            // Rows are newest-first; first write wins = latest snapshot of that day
            if (!byDay.has(day)) byDay.set(day, v);
          });
          const series = Array.from(byDay.entries())
            .sort(([a], [b]) => (a < b ? -1 : 1))
            .map(([, v]) => v);
          // Append the live current value as the rightmost point so the trend ends at "now".
          series.push(filesViol);

          const hasTrend = series.length >= 2;
          const trendColor = ok ? (colors?.successText || 'var(--app-success)') : (colors?.errorText || 'var(--app-error)');
          const sparkW = 70;
          const sparkH = 18;
          let polyPoints = '';
          let areaPoints = '';
          let deltaLabel = '';
          if (hasTrend) {
            const mn = Math.min(...series);
            const mx = Math.max(...series);
            const rng = Math.max(1, mx - mn);
            const step = sparkW / Math.max(1, series.length - 1);
            polyPoints = series
              .map((v, i) => `${(i * step).toFixed(1)},${(sparkH - ((v - mn) / rng) * (sparkH - 2) - 1).toFixed(1)}`)
              .join(' ');
            areaPoints = `0,${sparkH} ${polyPoints} ${sparkW},${sparkH}`;
            const delta = series[series.length - 1] - series[0];
            deltaLabel = delta === 0 ? '→ 0' : delta > 0 ? `▲ +${delta}` : `▼ ${delta}`;
          }

          return (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              {hasTrend ? (
                <View
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}
                  data-testid="admin-health-digest-theme-sparkline"
                  testID="admin-health-digest-theme-sparkline"
                >
                  <svg width={sparkW} height={sparkH} viewBox={`0 0 ${sparkW} ${sparkH}`}>
                    <polyline fill={`${trendColor}1A`} stroke="none" points={areaPoints} />
                    <polyline fill="none" stroke={trendColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" points={polyPoints} />
                  </svg>
                  <Text
                    style={{ color: trendColor, fontSize: 9, fontWeight: '700' }}
                    data-testid="admin-health-digest-theme-trend-delta"
                    testID="admin-health-digest-theme-trend-delta"
                  >
                    {deltaLabel}
                  </Text>
                </View>
              ) : null}
              <View
                style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: `${pillColor}1A`, borderWidth: 1, borderColor: pillColor }}
                data-testid="admin-health-digest-theme-pill"
                testID="admin-health-digest-theme-pill"
              >
                <Text style={{ color: pillColor, fontSize: 10, fontWeight: '800' }}>
                  {label}
                </Text>
              </View>
            </View>
          );
        })() : null}
        <TouchableOpacity
          disabled={busy}
          onPress={runNow}
          data-testid="admin-health-digest-run-now"
          testID="admin-health-digest-run-now"
          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${accent}22`, borderWidth: 1, borderColor: accent }}
        >
          <Text style={{ color: accent, fontSize: 11, fontWeight: '700' }}>
            {busy ? 'Running…' : 'Run now'}
          </Text>
        </TouchableOpacity>
      </View>
      {themeAudit && themeAudit.violations_by_category ? (() => {
        const cats = themeAudit.violations_by_category || {};
        const counts: [string, number][] = [
          ['ternary', cats.darkmode_ternary || 0],
          ['inline_bg', (cats.inline_solid_bg || 0) + (cats.inline_dark_bg || 0) + (cats.inline_light_bg || 0)],
          ['overlay', cats.inline_raw_overlay || 0],
          ['border', cats.inline_solid_border || 0],
          ['text', (cats.inline_solid_text || 0) + (cats.inline_light_text || 0)],
        ];
        return (
          <View
            style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 2 }}
            data-testid="admin-health-digest-theme-breakdown"
            testID="admin-health-digest-theme-breakdown"
          >
            {counts.map(([k, n]) => {
              const dotColor = n === 0 ? (colors?.successText || 'var(--app-success)') : (colors?.errorText || 'var(--app-error)');
              return (
                <View key={k} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid={`theme-breakdown-${k}`} testID={`theme-breakdown-${k}`}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: dotColor }} />
                  <Text style={{ color: muted, fontSize: 9, fontWeight: '600' }}>{k}: {n}</Text>
                </View>
              );
            })}
          </View>
        );
      })() : null}
      {status ? (
        <Text
          style={{ color: muted, fontSize: 11, fontStyle: 'italic' }}
          data-testid="admin-health-digest-status"
          testID="admin-health-digest-status"
        >
          {status}
        </Text>
      ) : null}
      {loading ? (
        <ActivityIndicator size="small" color={accent} />
      ) : rows.length === 0 ? (
        <Text style={{ color: muted, fontSize: 12 }} data-testid="admin-health-digest-empty" testID="admin-health-digest-empty">
          {tx('admin.adminHealthDigest.states.empty', 'No digests in the last 7 days yet — the first run fires at 08:00 UTC or hit "Run now".')}
        </Text>
      ) : (
        rows.map((row, i) => {
          const sc = severityColor(row.severity, colors);
          const dateStr = new Date(row.generated_at).toLocaleString();
          const severityLabel = normalizeAdminStatusTone(row.severity, 'INFO');
          return (
            <View
              key={i}
              style={{ borderTopWidth: i === 0 ? 0 : 1, borderTopColor: border, paddingTop: i === 0 ? 0 : 10, gap: 4 }}
              data-testid={`admin-health-digest-row-${i}`}
              testID={`admin-health-digest-row-${i}`}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: `${sc}22` }}>
                  <Text style={{ color: sc, fontSize: 9, fontWeight: '800' }}>
                    {severityLabel}
                  </Text>
                </View>
                <Text style={{ color: muted, fontSize: 10 }}>{dateStr}</Text>
              </View>
              <Text style={{ color: text, fontSize: 12, fontWeight: '600' }} numberOfLines={2}>
                {normalizeAdminRuntimeCopy(row.title, tx('admin.adminHealthDigest.row.titleFallback', 'Admin health digest item'))}
              </Text>
              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                <Text style={{ color: muted, fontSize: 11 }}>
                  routes: {row.healthy_routes}/{row.total_routes}
                </Text>
                <Text style={{ color: muted, fontSize: 11 }}>
                  crashes: {row.total_errors_24h}
                </Text>
                <Text style={{ color: muted, fontSize: 11 }}>
                  {row.email_sent ? 'email ✓' : 'email ✗'}
                </Text>
                <Text style={{ color: muted, fontSize: 11 }}>
                  {row.dispatched ? 'slack ✓' : 'slack ✗'}
                </Text>
              </View>
              {(row.top_panels || []).slice(0, 3).map((p, j) => (
                <Text key={j} style={{ color: muted, fontSize: 10 }} numberOfLines={1}>
                  · {humanizeAdminToken(p.panel_name || p.panel_id, tx('admin.adminHealthDigest.row.panelFallback', 'Panel'))}: {p.count} crash(es)
                </Text>
              ))}
            </View>
          );
        })
      )}
    </View>
  );
}
