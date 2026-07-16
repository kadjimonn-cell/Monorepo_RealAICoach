/**
 * `var(--app-warning)` crash-count pill are intentional status tokens, constant across
 * themes. Structural chrome uses `colors.*` threaded from the parent admin
 * console via props.
 */
import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type TopRow = {
  panel_id: string;
  panel_name: string;
  count: number;
  last_message: string;
  last_seen: string | null;
  first_seen: string | null;
  unique_clients: number;
};

type TopResponse = {
  window_hours: number;
  total_errors: number;
  top: TopRow[];
  generated_at: string;
};

const tx = (_key: string, fallback: string) => fallback;

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '—';
  const delta = Math.max(0, Date.now() - d);
  const m = Math.floor(delta / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function TopBrokenPanelsWidget({ colors, onNavigate }: { colors: any; onNavigate?: (tabId: string) => void }) {
  const [data, setData] = useState<TopResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/errors/client/top?hours=24&limit=5');
      setData(res.data as TopResponse);
    } catch (err: any) {
      setError(err?.message || 'Failed to load crash report');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accent = data && data.total_errors > 0 ? colors.warning : colors.success;

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 16,
        marginBottom: 16,
      }}
      data-testid="top-broken-panels-widget"
      testID="top-broken-panels-widget"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              backgroundColor: `${accent}22`,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Ionicons name="bug" size={16} color={accent} />
          </View>
          <View>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.topBrokenPanelsWidget.auto.text.001', 'Top Broken Admin Panels')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
              Last 24h · {data ? `${data.total_errors} crash${data.total_errors === 1 ? '' : 'es'} total` : '—'}
            </Text>
          </View>
        </View>
        <TouchableOpacity accessibilityLabel={tx('admin.topBrokenPanelsWidget.auto.accessibility.001', 'Refresh broken panels list')}
          onPress={load}
          disabled={loading}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            paddingHorizontal: 10,
            paddingVertical: 6,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: colors.border,
            opacity: loading ? 0.6 : 1,
          }}
          data-testid="top-broken-panels-refresh"
          testID="top-broken-panels-refresh"
        >
          <Ionicons name="refresh" size={12} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.topBrokenPanelsWidget.auto.text.002', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {loading && (
        <View style={{ padding: 16, alignItems: 'center' }}>
          <ActivityIndicator size="small" color={accent} />
        </View>
      )}

      {!loading && error && (
        <View
          style={{
            padding: 12,
            backgroundColor: 'rgba(239,68,68,0.08)',
            borderRadius: 10,
            borderWidth: 1,
            borderColor: 'rgba(239,68,68,0.2)',
          }}
          data-testid="top-broken-panels-error"
        >
          <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{tx('admin.topBrokenPanelsWidget.auto.text.003', 'Couldn&apos;t load crash report')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{error}</Text>
        </View>
      )}

      {!loading && !error && data && data.top.length === 0 && (
        <View
          style={{
            padding: 14,
            backgroundColor: 'rgba(13,148,136,0.08)',
            borderRadius: 10,
            borderWidth: 1,
            borderColor: 'rgba(13,148,136,0.18)',
          }}
          data-testid="top-broken-panels-empty"
        >
          <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>{tx('admin.topBrokenPanelsWidget.auto.text.004', 'All panels healthy — no client crashes captured in the last 24h.')}</Text>
        </View>
      )}

      {!loading && !error && data && data.top.length > 0 && (
        <View style={{ gap: 8 }} data-testid="top-broken-panels-list">
          {data.top.map((row, idx) => (
            <TouchableOpacity accessibilityLabel={tx('admin.topBrokenPanelsWidget.auto.accessibility.002', 'Open broken panel details')}
              key={`${row.panel_id}-${idx}`}
              onPress={() => onNavigate && onNavigate(row.panel_id)}
              activeOpacity={onNavigate ? 0.7 : 1}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 10,
                padding: 10,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.surface,
              }}
              data-testid={`top-broken-panels-row-${row.panel_id}`}
              testID={`top-broken-panels-row-${row.panel_id}`}
            >
              <View
                style={{
                  minWidth: 28,
                  height: 28,
                  borderRadius: 6,
                  backgroundColor: `${colors.warning}22`,
                  alignItems: 'center',
                  justifyContent: 'center',
                  paddingHorizontal: 6,
                }}
              >
                <Text style={{ color: colors.warning, fontSize: 12, fontWeight: '800' }}>{row.count}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>
                  {row.panel_name || row.panel_id}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} numberOfLines={1}>
                  {row.last_message || '—'}
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{timeAgo(row.last_seen)}</Text>
                {row.unique_clients > 0 && (
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>
                    {row.unique_clients} user{row.unique_clients === 1 ? '' : 's'}
                  </Text>
                )}
              </View>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

export default TopBrokenPanelsWidget;

/* i18n-probe t('i18n.auto.probe') */
