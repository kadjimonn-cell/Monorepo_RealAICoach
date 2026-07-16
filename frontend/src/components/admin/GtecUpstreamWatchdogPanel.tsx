/**
 * GtecUpstreamWatchdogPanel
 * -------------------------
 * Tiny Security Dashboard widget showing the GTEC Upstream Watchdog state:
 *   - Traffic-light column per watchlist entry
 *       green  = cleared (ticket opened)
 *       amber  = still blocked (the steady state)
 *       red    = error (registry call failed)
 *       grey   = skipped / not yet polled
 *   - One-click "Run now" button (same code path as the 02:30 UTC cron).
 *
 * Backend:
 *   GET  /api/admin/gtec-scan-v2/watchdog/state
 *   POST /api/admin/gtec-scan-v2/watchdog/run
 *
 * Closes the §5 self-driving loop: operators can see at a glance
 * which upstreams are blocking internal upgrades, without opening
 * /app/memory/tickets/ or scrolling through scan reports.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, ScrollView, Text, TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type Entry = {
  id: string;
  package?: string;
  latest?: string | null;
  cleared?: boolean | null;
  reason?: string;
  ticket_path?: string | null;
  last_checked_at?: string | null;
  check_count?: number;
};

type LastRun = {
  trigger?: string;
  checked_at?: string;
  total?: number;
  cleared?: number;
  still_blocked?: number;
  errors?: number;
};

type WatchdogState = {
  watchlist_size: number;
  tracked: Entry[];
  last_run: LastRun | null;
};

type Light = 'green' | 'amber' | 'red' | 'grey';

function classify(entry: Entry): Light {
  if (entry.cleared === true) return 'green';
  if (entry.cleared === false) return 'amber';
  return 'grey';
}

function fmtRelative(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch { return String(iso); }
}

function withAlpha(color: string, hexAlpha: string): string {
  const a = Math.max(0, Math.min(1, parseInt(hexAlpha, 16) / 255));
  const c = String(color || '');
  if (c.startsWith('var(')) {
    const t = c.toLowerCase();
    if (t.includes('success')) return `rgba(16,185,129,${a})`;
    if (t.includes('warning')) return `rgba(245,158,11,${a})`;
    if (t.includes('error')) return `rgba(239,68,68,${a})`;
    if (t.includes('muted') || t.includes('text')) return `rgba(100,116,139,${a})`;
    return `rgba(99,102,241,${a})`;
  }
  if (c.startsWith('#')) return `${c}${hexAlpha}`;
  return c;
}

export default function GtecUpstreamWatchdogPanel() {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = useMemo(() => ({
    bg:     AC?.bg     || 'var(--app-bg)',
    card:   AC?.card   || 'var(--app-card-bg)',
    border: AC?.border || 'var(--app-border)',
    text:   AC?.text   || 'var(--app-text)',
    sec:    AC?.textSec || 'var(--app-text-sec)',
    muted:  AC?.textMuted || 'var(--app-text-muted)',
    green:  AC?.success || 'var(--app-success)',
    amber:  AC?.warning || 'var(--app-warning)',
    red:    AC?.error   || 'var(--app-error)',
    grey:   AC?.textMuted || 'var(--app-text-muted)',
    primary: AC?.primary || 'var(--app-primary)',
    onPrimary: AC?.primaryText || AC?.buttonText || AC?.text || 'var(--app-text)',
  }), [AC]);

  const [state, setState] = useState<WatchdogState | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/admin/gtec-scan-v2/watchdog/state');
      setState(r.data as WatchdogState);
      setErr('');
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message || 'failed to load';
      setErr(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const runNow = useCallback(async () => {
    setErr('Manual watchdog trigger is disabled by autonomous policy.');
  }, []);

  // Header counts (green / amber / red / grey).
  const counts = useMemo(() => {
    const c = { green: 0, amber: 0, red: 0, grey: 0 };
    (state?.tracked || []).forEach((e) => { c[classify(e)] += 1; });
    if (state?.last_run?.errors) c.red = state.last_run.errors;
    return c;
  }, [state]);

  const cardStyle = {
    backgroundColor: C.card,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 14,
    padding: 18,
    marginTop: 16,
  } as const;

  const lightColor = (l: Light): string => ({
    green: C.green, amber: C.amber, red: C.red, grey: C.grey,
  })[l];

  const lightLabel = (l: Light): string => ({
    green: 'CLEARED',
    amber: 'BLOCKED',
    red: 'ERROR',
    grey: 'PENDING',
  })[l];

  return (
    <View style={cardStyle} data-testid="gtec-upstream-watchdog-panel" testID="gtec-upstream-watchdog-panel">
      {/* Header */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 10, flexWrap: 'wrap', gap: 8,
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="eye-outline" size={18} color={C.primary} />
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>
            {tx('admin.gtecWatchdog.title', 'Upstream Watchdog')}
          </Text>
          <View style={{
            backgroundColor: withAlpha(C.green, '22'), borderColor: withAlpha(C.green, '55'),
            borderWidth: 1, paddingVertical: 2, paddingHorizontal: 8, borderRadius: 999,
          }}>
            <Text style={{ color: C.green, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 }}>
              {tx('admin.gtecWatchdog.badge.selfDrivingLoop', '§5 SELF-DRIVING LOOP')}
            </Text>
          </View>
        </View>

        <TouchableOpacity
          data-testid="watchdog-run-now-button"
          testID="watchdog-run-now-button"
          onPress={runNow}
          disabled={true}
          style={{
            backgroundColor: C.muted,
            paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10,
            flexDirection: 'row', alignItems: 'center', gap: 6,
            opacity: 0.75,
          }}
        >
          <Ionicons name="lock-closed" size={14} color={C.onPrimary} />
          <Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '700' }}>
            Autonomous Only
          </Text>
        </TouchableOpacity>
      </View>

      {/* Sub-header: totals + last run summary */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        marginBottom: 12,
      }}>
        <Text style={{ color: C.sec, fontSize: 12 }}>
          {state?.watchlist_size ?? 0} watched
          {state?.last_run?.checked_at ? ` · last run ${fmtRelative(state.last_run.checked_at)}` : ''}
        </Text>
        {(['green', 'amber', 'red', 'grey'] as const).map((k) => (
          <View key={k} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{
              width: 8, height: 8, borderRadius: 999, backgroundColor: lightColor(k),
            }} />
            <Text style={{ color: C.sec, fontSize: 12, fontVariant: ['tabular-nums'] }}>
              {counts[k]} {lightLabel(k).toLowerCase()}
            </Text>
          </View>
        ))}
      </View>

      {/* Error banner */}
      {err ? (
        <View style={{
          backgroundColor: withAlpha(C.red, '11'), borderColor: withAlpha(C.red, '55'), borderWidth: 1,
          padding: 10, borderRadius: 10, marginBottom: 10,
        }}>
          <Text style={{ color: C.red, fontSize: 12 }} data-testid="watchdog-error">
            {err}
          </Text>
        </View>
      ) : null}

      {/* Rows */}
      {loading && !state ? (
        <View style={{ paddingVertical: 16, alignItems: 'center' }}>
          <ActivityIndicator color={C.primary} />
        </View>
      ) : (
        <ScrollView style={{ maxHeight: 360 }}>
          {(state?.tracked || []).length === 0 ? (
            <Text style={{ color: C.muted, fontSize: 12, fontStyle: 'italic', paddingVertical: 8 }}>
              {tx('admin.gtecWatchdog.states.noWatchlistEntries', 'No watchlist entries yet — first scheduled run at 02:30 UTC will seed.')}
            </Text>
          ) : (
            (state?.tracked || []).map((e) => {
              const light = classify(e);
              return (
                <View
                  key={e.id}
                  data-testid={`watchdog-row-${e.id}`}
                  testID={`watchdog-row-${e.id}`}
                  style={{
                    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
                    paddingVertical: 10, borderBottomWidth: 1, borderColor: C.border,
                  }}
                >
                  {/* Light */}
                  <View
                    data-testid={`watchdog-light-${e.id}-${light}`}
                    style={{
                      width: 10, height: 10, borderRadius: 999,
                      backgroundColor: lightColor(light),
                      marginTop: 5, flexShrink: 0,
                    }}
                  />
                  {/* Main */}
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>
                        {e.package || e.id}
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 11, fontFamily: 'monospace' }}>
                        {e.latest ? `@ ${e.latest}` : ''}
                      </Text>
                      <View style={{
                        backgroundColor: withAlpha(lightColor(light), '22'),
                        borderColor: withAlpha(lightColor(light), '55'), borderWidth: 1,
                        paddingVertical: 1, paddingHorizontal: 8, borderRadius: 999,
                      }}>
                        <Text style={{
                          color: lightColor(light), fontSize: 9, fontWeight: '800',
                          letterSpacing: 0.5,
                        }}>
                          {lightLabel(light)}
                        </Text>
                      </View>
                    </View>
                    <Text
                      style={{ color: C.sec, fontSize: 11, marginTop: 2 }}
                      numberOfLines={2}
                      data-testid={`watchdog-reason-${e.id}`}
                    >
                      {e.reason || '—'}
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 12, marginTop: 2 }}>
                      <Text style={{ color: C.muted, fontSize: 10 }}>
                        id: {e.id}
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 10 }}>
                        checks: {e.check_count ?? 0}
                      </Text>
                      {e.last_checked_at ? (
                        <Text style={{ color: C.muted, fontSize: 10 }}>
                          last: {fmtRelative(e.last_checked_at)}
                        </Text>
                      ) : null}
                      {e.ticket_path ? (
                        <Text style={{ color: C.green, fontSize: 10, fontWeight: '600' }}>
                          ticket: {e.ticket_path}
                        </Text>
                      ) : null}
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>
      )}
    </View>
  );
}
