/**
 * GtecDirectiveBanner
 * -------------------
 * Persistent top-of-page banner for every admin screen.
 * Shows, at a glance:
 *   • Directive load state (ALWAYS ACTIVE + version hash)
 *   • Last v2 scan §12 status (task_id + PASS/FAIL + 6-pillar pills)
 *
 * Reads:
 *   GET /api/gtec/directive/state          (public, no-auth; for version hash)
 *   GET /api/admin/gtec-scan-v2/latest     (admin-only; for last §12 output)
 *
 * Lives at the top of admin surfaces. Collapses to a single status pill on
 * mobile to stay out of the user's way.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Platform, Text, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type DirectiveState = {
  loaded: boolean;
  version?: string;
  byte_size?: number;
  always_active?: boolean;
};

type LatestReport = {
  task_id?: string;
  execution_hash?: string;
  status?: 'PASS' | 'FAIL';
  critical_vulns?: number;
  high_vulns?: number;
  medium_vulns?: number;
  low_vulns?: number;
  severity_counts?: { medium?: number; low?: number };
  regressions?: 'YES' | 'NO';
  security_scan?: 'PASS' | 'FAIL';
  e2e_tests?: 'PASS' | 'FAIL';
  responsiveness?: 'PASS' | 'FAIL';
  performance?: 'PASS' | 'FAIL';
  rbac_status?: 'PASS' | 'FAIL';
  subscription_enforcement?: 'PASS' | 'FAIL';
  generated_at?: string;
  triggered_by?: string;
};

function relTime(iso?: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch { return iso; }
}

function withAlpha(color: string, hexAlpha: string): string {
  const a = Math.max(0, Math.min(1, parseInt(hexAlpha, 16) / 255));
  const c = String(color || '');
  if (c.startsWith('var(')) {
    const t = c.toLowerCase();
    if (t.includes('success')) return `rgba(16,185,129,${a})`;
    if (t.includes('warning')) return `rgba(245,158,11,${a})`;
    if (t.includes('error')) return `rgba(239,68,68,${a})`;
    if (t.includes('info')) return `rgba(14,165,233,${a})`;
    if (t.includes('muted') || t.includes('text')) return `rgba(100,116,139,${a})`;
    return `rgba(99,102,241,${a})`;
  }
  if (c.startsWith('#')) return `${c}${hexAlpha}`;
  return c;
}

export default function GtecDirectiveBanner() {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const compact = width < 900;

  const C = React.useMemo(() => ({
    border: AC?.border || 'var(--app-border)',
    card: AC?.card || 'var(--app-card-bg)',
    cardAlt: AC?.bgAlt || AC?.cardSoft || 'var(--app-surface)',
    text: AC?.text || 'var(--app-text)',
    textSec: AC?.textSec || 'var(--app-text-sec)',
    muted: AC?.textMuted || 'var(--app-text-muted)',
    success: AC?.success || 'var(--app-success)',
    danger: AC?.error || 'var(--app-error)',
    warning: AC?.warning || 'var(--app-warning)',
    accent: AC?.info || 'var(--app-primary)',
  }), [AC]);

  const [directive, setDirective] = useState<DirectiveState | null>(null);
  const [latest, setLatest] = useState<LatestReport | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.get('/gtec/directive/state');
      setDirective({
        loaded: Boolean(d.data?.loaded),
        version: d.data?.version,
        byte_size: d.data?.byte_size,
        always_active: Boolean(d.data?.always_active),
      });
    } catch { /* public endpoint — ignore */ }
    try {
      const r = await api.get('/admin/gtec-scan-v2/latest');
      setLatest(r.data?.report || null);
    } catch { /* non-admin or no report yet */ }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/gtec-directive-banner/hybrid-refresh',
    onTick: load,
    runOnMount: false,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  // If directive endpoint hasn't responded yet, render nothing
  if (!directive) return null;

  const statusTone = latest?.status === 'PASS' ? C.success
                    : latest?.status === 'FAIL' ? C.danger
                    : C.muted;
  const directiveTone = directive.loaded ? C.success : C.danger;
  const mediumCount = latest?.medium_vulns ?? latest?.severity_counts?.medium ?? 0;
  const lowCount = latest?.low_vulns ?? latest?.severity_counts?.low ?? 0;

  return (
    <View
      data-testid="gtec-directive-banner"
      testID="gtec-directive-banner"
      style={{
        marginTop: 0, marginBottom: 10,
        borderRadius: 12,
        borderWidth: 1, borderColor: withAlpha(statusTone, '44'),
        backgroundColor: C.card,
        paddingHorizontal: 12, paddingVertical: 10,
        ...(Platform.OS === 'web'
          ? { boxShadow: '0 2px 6px rgba(15,23,42,0.04)' } as any
          : {}),
      }}
    >
      {/* Header row: directive state + status pill + expand toggle */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <View
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6,
            paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999,
            backgroundColor: withAlpha(directiveTone, '18'), borderWidth: 1, borderColor: withAlpha(directiveTone, '3A'),
          }}
          data-testid="gtec-banner-directive-pill"
          testID="gtec-banner-directive-pill"
        >
          <Ionicons name="shield-checkmark" size={11} color={directiveTone} />
          <Text style={{ color: directiveTone, fontSize: 9, fontWeight: '900', letterSpacing: 0.5 }}>
            DIRECTIVE · {directive.loaded ? 'ALWAYS ACTIVE' : 'NOT LOADED'}
          </Text>
        </View>
        {directive.version ? (
          <Text
            style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
            data-testid="gtec-banner-directive-version"
            testID="gtec-banner-directive-version"
          >
            v{directive.version}
          </Text>
        ) : null}

        <View style={{ width: 1, height: 14, backgroundColor: C.border, marginHorizontal: 4 }} />

        {/* Last scan status */}
        <View
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6,
            paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999,
            backgroundColor: withAlpha(statusTone, '18'), borderWidth: 1, borderColor: withAlpha(statusTone, '3A'),
          }}
          data-testid="gtec-banner-scan-status"
          testID="gtec-banner-scan-status"
        >
          <View style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: statusTone }} />
          <Text style={{ color: statusTone, fontSize: 9, fontWeight: '900', letterSpacing: 0.5 }}>
            LAST SCAN · {latest?.status || 'NONE'}
          </Text>
        </View>

        {latest?.task_id ? (
          <Text
            style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
            data-testid="gtec-banner-task-id"
            testID="gtec-banner-task-id"
            numberOfLines={1}
          >
            {latest.task_id}
          </Text>
        ) : null}
        {latest?.generated_at ? (
          <Text style={{ color: C.muted, fontSize: 10 }}>
            · {relTime(latest.generated_at)}
          </Text>
        ) : null}

        <View style={{ flex: 1 }} />

        {latest ? (
          <TouchableOpacity
            onPress={() => setExpanded((v) => !v)}
            data-testid="gtec-banner-expand"
            testID="gtec-banner-expand"
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 4,
              paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8,
              borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt,
            }}
          >
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>
              {expanded ? 'Hide' : 'Details'}
            </Text>
            <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={11} color={C.textSec} />
          </TouchableOpacity>
        ) : null}

        <TouchableOpacity
          onPress={() => router.push('/executive-dashboard?section=security' as any)}
          data-testid="gtec-banner-open-security"
          testID="gtec-banner-open-security"
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 4,
            paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8,
            backgroundColor: withAlpha(C.accent, '18'), borderWidth: 1, borderColor: withAlpha(C.accent, '3A'),
          }}
        >
          <Ionicons name="shield-half" size={11} color={C.accent} />
          <Text style={{ color: C.accent, fontSize: 10, fontWeight: '800', letterSpacing: 0.3 }}>
            {tx('admin.gtecDirectiveBanner.actions.securityDashboard', 'Security Dashboard')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Expanded §12 detail */}
      {expanded && latest ? (
        <View
          data-testid="gtec-banner-details"
          testID="gtec-banner-details"
          style={{
            marginTop: 10, paddingTop: 10,
            borderTopWidth: 1, borderTopColor: C.border,
          }}
        >
          {/* Severity counters */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            <Counter label="CRIT" value={latest.critical_vulns ?? 0}
              tone={(latest.critical_vulns ?? 0) > 0 ? C.danger : C.success} C={C} />
            <Counter label="HIGH" value={latest.high_vulns ?? 0}
              tone={(latest.high_vulns ?? 0) > 0 ? C.warning : C.success} C={C} />
            <Counter label="MED" value={mediumCount}
              tone={mediumCount > 0 ? C.warning : C.success} C={C} />
            <Counter label="LOW" value={lowCount}
              tone={lowCount > 0 ? C.warning : C.success} C={C} />
            <Counter label="REGRESSION" value={latest.regressions === 'YES' ? 'YES' : 'NO'}
              tone={latest.regressions === 'YES' ? C.danger : C.success} C={C} />
            <Counter label="TRIGGER" value={latest.triggered_by || '—'} tone={C.muted} C={C} />
          </View>

          {/* Pillar row */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            <Pillar label="SECURITY"       value={latest.security_scan} C={C} />
            <Pillar label="E2E"            value={latest.e2e_tests} C={C} />
            <Pillar label="RESPONSIVENESS" value={latest.responsiveness} C={C} />
            <Pillar label="PERFORMANCE"    value={latest.performance} C={C} />
            <Pillar label="RBAC"           value={latest.rbac_status} C={C} />
            <Pillar label="SUBSCRIPTION"   value={latest.subscription_enforcement} C={C} />
          </View>

          {!compact && latest.execution_hash ? (
            <Text
              style={{ color: C.muted, fontSize: 10, marginTop: 8, fontFamily: 'monospace' }}
              data-testid="gtec-banner-execution-hash"
              testID="gtec-banner-execution-hash"
            >
              EXECUTION_HASH · {latest.execution_hash}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function Counter({ label, value, tone, C }: {
  label: string; value: number | string; tone: string; C: any;
}) {
  return (
    <View style={{
      paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8,
      borderWidth: 1, borderColor: withAlpha(tone, '3A'), backgroundColor: withAlpha(tone, '10'),
    }}>
      <Text style={{ color: tone, fontSize: 8, fontWeight: '900', letterSpacing: 0.5 }}>{label}</Text>
      <Text style={{ color: tone, fontSize: 12, fontWeight: '900', marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function Pillar({ label, value, C }: {
  label: string; value?: 'PASS' | 'FAIL'; C: any;
}) {
  const tone = value === 'PASS' ? C.success : value === 'FAIL' ? C.danger : C.muted;
  return (
    <View
      data-testid={`gtec-banner-pillar-${label.toLowerCase()}`}
      testID={`gtec-banner-pillar-${label.toLowerCase()}`}
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 4,
        paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999,
        borderWidth: 1, borderColor: withAlpha(tone, '3A'), backgroundColor: withAlpha(tone, '10'),
      }}>
      <View style={{ width: 5, height: 5, borderRadius: 999, backgroundColor: tone }} />
      <Text style={{ color: tone, fontSize: 8, fontWeight: '800', letterSpacing: 0.4 }}>
        {label} · {value || '—'}
      </Text>
    </View>
  );
}
