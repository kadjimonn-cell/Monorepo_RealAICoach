import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';

import api from '../../services/api';

type AdminColors = {
  text: string;
  textMuted: string;
  border: string;
  card: string;
  primary: string;
  successText: string;
  warningText: string;
};

type DashboardPayload = {
  feature_id?: string;
  window_days?: number;
  generated_at?: string;
  kpis?: {
    active_listeners?: number;
    total_plays?: number;
    completed_plays?: number;
    continuation_rate_pct?: number;
    completion_rate_pct?: number;
    avg_session_length_seconds?: number;
  };
  upgrade_funnel?: {
    free_to_paid_rate_pct?: number;
    cta_rate_pct?: number;
    checkout_success_rate_pct?: number;
    subscribe_success?: number;
  };
  cohort_segmentation?: {
    geo_country?: Record<string, number>;
    device_bucket?: Record<string, number>;
    channel?: Record<string, number>;
  };
};

const CARD_TEST_ID = 'podcasts-admin-conversion-card';

export const PodcastsConversionCard = ({ colors }: { colors: AdminColors }) => {
  const [windowDays, setWindowDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<DashboardPayload | null>(null);

  const endpoint = `/podcasts/v2/admin/conversion-dashboard?window_days=${windowDays}`;

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(endpoint, { silentLoading: true, skipDedupe: true });
      setPayload(res?.data || {});
    } catch (err: any) {
      const msg = String(err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Unable to load Podcasts analytics');
      setError(msg);
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const kpis = payload?.kpis || {};
  const funnel = payload?.upgrade_funnel || {};
  const cohorts = payload?.cohort_segmentation || {};

  const compactRows = useMemo(() => ([
    { label: 'Active listeners', value: Number(kpis.active_listeners || 0), color: colors.text },
    { label: 'Completion rate', value: `${Number(kpis.completion_rate_pct || 0).toFixed(2)}%`, color: colors.successText },
    { label: 'Continuation rate', value: `${Number(kpis.continuation_rate_pct || 0).toFixed(2)}%`, color: colors.primary },
    { label: 'Avg session', value: `${Number(kpis.avg_session_length_seconds || 0).toFixed(1)}s`, color: colors.warningText },
    { label: 'Free→Paid', value: `${Number(funnel.free_to_paid_rate_pct || 0).toFixed(2)}%`, color: colors.successText },
  ]), [colors.primary, colors.successText, colors.text, colors.warningText, funnel.free_to_paid_rate_pct, kpis.active_listeners, kpis.avg_session_length_seconds, kpis.completion_rate_pct, kpis.continuation_rate_pct]);

  return (
    <View style={{ marginTop: 12, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid={CARD_TEST_ID} testID={CARD_TEST_ID}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="podcasts-admin-conversion-card-title" testID="podcasts-admin-conversion-card-title">Feature 29 • Podcasts Conversion Analytics</Text>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {[7, 14, 30].map((days) => {
            const active = windowDays === days;
            return (
              <TouchableOpacity
                key={days}
                onPress={() => setWindowDays(days)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? `${colors.primary}1A` : colors.card, paddingHorizontal: 10, paddingVertical: 5 }}
                data-testid={`podcasts-admin-conversion-window-${days}`}
                testID={`podcasts-admin-conversion-window-${days}`}
              >
                <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '800' }}>{days}d</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {loading ? (
        <View style={{ marginTop: 12, alignItems: 'center', justifyContent: 'center', minHeight: 110 }} data-testid="podcasts-admin-conversion-loading" testID="podcasts-admin-conversion-loading">
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ marginTop: 8, color: colors.textMuted, fontSize: 12 }}>Loading podcasts analytics...</Text>
        </View>
      ) : null}

      {!loading && error ? (
        <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}15`, padding: 10 }} data-testid="podcasts-admin-conversion-error" testID="podcasts-admin-conversion-error">
          <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '700' }}>{error}</Text>
          <TouchableOpacity onPress={loadData} style={{ marginTop: 8, borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}16`, paddingHorizontal: 10, paddingVertical: 6, alignSelf: 'flex-start' }} data-testid="podcasts-admin-conversion-retry" testID="podcasts-admin-conversion-retry">
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {!loading && !error ? (
        <>
          <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="podcasts-admin-conversion-kpis" testID="podcasts-admin-conversion-kpis">
            {compactRows.map((row) => (
              <View key={row.label} style={{ minWidth: 160, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`podcasts-admin-conversion-kpi-${row.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`podcasts-admin-conversion-kpi-${row.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                <Text style={{ color: colors.textMuted, fontSize: 10.5, fontWeight: '700' }}>{row.label}</Text>
                <Text style={{ color: row.color, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{String(row.value)}</Text>
              </View>
            ))}
          </View>

          <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="podcasts-admin-conversion-cohorts" testID="podcasts-admin-conversion-cohorts">
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Cohort Segmentation</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 6 }}>Geo: {Object.keys(cohorts.geo_country || {}).slice(0, 3).join(', ') || '—'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }}>Devices: {Object.keys(cohorts.device_bucket || {}).slice(0, 3).join(', ') || '—'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }}>Channels: {Object.keys(cohorts.channel || {}).slice(0, 3).join(', ') || '—'}</Text>
          </View>
        </>
      ) : null}
    </View>
  );
};

export default PodcastsConversionCard;
