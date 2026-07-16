import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useLiveQuery } from '../../hooks/useLiveQuery';

type AdminColors = {
  text: string;
  textMuted: string;
  textSec: string;
  primary: string;
  border: string;
  card: string;
  bg: string;
  successText: string;
  warningText: string;
};

export const AudioStudioConversionCard = ({ colors }: { colors: AdminColors }) => {
  const [windowDays, setWindowDays] = useState(7);
  const endpoint = `/audio-studio/v2/admin/conversion-dashboard?window_days=${windowDays}`;
  const { data, loading, error, refetch } = useLiveQuery(endpoint, {
    entity: 'audio-studio-conversion-dashboard',
    pollInterval: 60_000,
  });

  const kpis = useMemo(() => data?.kpis || {}, [data]);
  const funnel = useMemo(() => data?.upgrade_funnel || {}, [data]);
  const deltas = useMemo(() => data?.benchmark_deltas || {}, [data]);
  const cohorts = useMemo(() => data?.cohort_segmentation || {}, [data]);

  const topGeo = useMemo(
    () => Object.entries(cohorts?.geo_country || {}).slice(0, 3),
    [cohorts?.geo_country],
  );
  const topDevice = useMemo(
    () => Object.entries(cohorts?.device_bucket || {}).slice(0, 3),
    [cohorts?.device_bucket],
  );
  const topChannel = useMemo(
    () => Object.entries(cohorts?.channel || {}).slice(0, 3),
    [cohorts?.channel],
  );

  return (
    <View
      style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}
      data-testid="audio-studio-conversion-card"
      testID="audio-studio-conversion-card"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="stats-chart" size={15} color={colors.primary} />
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="audio-studio-conversion-card-title" testID="audio-studio-conversion-card-title">
            Feature 28 Conversion Dashboard
          </Text>
        </View>
        <TouchableOpacity onPress={() => refetch()} data-testid="audio-studio-conversion-card-refresh" testID="audio-studio-conversion-card-refresh">
          <Ionicons name="refresh" size={15} color={colors.textMuted} />
        </TouchableOpacity>
      </View>

      <View style={{ marginTop: 8, flexDirection: 'row', gap: 8 }}>
        {[1, 7, 30].map((d) => {
          const active = windowDays === d;
          return (
            <TouchableOpacity
              key={`audio-studio-conversion-window-${d}`}
              onPress={() => setWindowDays(d)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? `${colors.primary}18` : colors.bg, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid={`audio-studio-conversion-window-${d}`}
              testID={`audio-studio-conversion-window-${d}`}
            >
              <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 10.5, fontWeight: '700' }}>{`${d}d`}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading ? (
        <View style={{ paddingVertical: 24, alignItems: 'center' }} data-testid="audio-studio-conversion-card-loading" testID="audio-studio-conversion-card-loading">
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }}>Loading conversion metrics...</Text>
        </View>
      ) : error ? (
        <View style={{ marginTop: 10, borderRadius: 8, borderWidth: 1, borderColor: `${colors.warningText}55`, backgroundColor: `${colors.warningText}12`, padding: 9 }} data-testid="audio-studio-conversion-card-error" testID="audio-studio-conversion-card-error">
          <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{String(error)}</Text>
        </View>
      ) : (
        <>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <View style={{ minWidth: 140, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 8 }} data-testid="audio-studio-conversion-kpi-session-length" testID="audio-studio-conversion-kpi-session-length">
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Avg Session Length</Text>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 3 }}>{`${Number(kpis?.avg_session_length_seconds || 0).toFixed(1)}s`}</Text>
            </View>
            <View style={{ minWidth: 140, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 8 }} data-testid="audio-studio-conversion-kpi-completion-rate" testID="audio-studio-conversion-kpi-completion-rate">
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Completion Rate</Text>
              <Text style={{ color: colors.successText, fontSize: 13, fontWeight: '800', marginTop: 3 }}>{`${Number(kpis?.completion_rate_pct || 0).toFixed(2)}%`}</Text>
            </View>
            <View style={{ minWidth: 160, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 8 }} data-testid="audio-studio-conversion-kpi-free-to-basic" testID="audio-studio-conversion-kpi-free-to-basic">
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Free → Paid Rate</Text>
              <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '800', marginTop: 3 }}>{`${Number(funnel?.free_to_paid_rate_pct || 0).toFixed(2)}%`}</Text>
            </View>
          </View>

          <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10 }} data-testid="audio-studio-conversion-funnel" testID="audio-studio-conversion-funnel">
            <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700', marginBottom: 6 }}>Upgrade Funnel</Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5 }} data-testid="audio-studio-conversion-funnel-values" testID="audio-studio-conversion-funnel-values">
              {`Free engaged ${Number(funnel?.free_engaged || 0)} → Prompt views ${Number(funnel?.prompt_views || 0)} → CTA ${Number(funnel?.plan_cta_clicks || 0)} → Success ${Number(funnel?.subscribe_success || 0)}`}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 5 }} data-testid="audio-studio-conversion-funnel-rates" testID="audio-studio-conversion-funnel-rates">
              {`Prompt ${Number(funnel?.prompt_view_rate_pct || 0).toFixed(2)}% · CTA ${Number(funnel?.cta_rate_pct || 0).toFixed(2)}% · Checkout ${Number(funnel?.checkout_success_rate_pct || 0).toFixed(2)}%`}
            </Text>
          </View>

          <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10 }} data-testid="audio-studio-conversion-benchmark-deltas" testID="audio-studio-conversion-benchmark-deltas">
            <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700', marginBottom: 6 }}>Benchmark Delta vs Previous Window</Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5 }} data-testid="audio-studio-conversion-delta-session" testID="audio-studio-conversion-delta-session">
              {`Avg Session Δ ${Number(deltas?.kpis?.avg_session_length_seconds?.delta_abs || 0).toFixed(2)}s (${Number(deltas?.kpis?.avg_session_length_seconds?.delta_pct || 0).toFixed(2)}%)`}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} data-testid="audio-studio-conversion-delta-completion" testID="audio-studio-conversion-delta-completion">
              {`Completion Δ ${Number(deltas?.kpis?.completion_rate_pct?.delta_abs || 0).toFixed(2)}pp (${Number(deltas?.kpis?.completion_rate_pct?.delta_pct || 0).toFixed(2)}%)`}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} data-testid="audio-studio-conversion-delta-free-to-paid" testID="audio-studio-conversion-delta-free-to-paid">
              {`Free→Paid Δ ${Number(deltas?.upgrade_funnel?.free_to_paid_rate_pct?.delta_abs || 0).toFixed(2)}pp (${Number(deltas?.upgrade_funnel?.free_to_paid_rate_pct?.delta_pct || 0).toFixed(2)}%)`}
            </Text>
          </View>

          <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10 }} data-testid="audio-studio-conversion-cohort-segmentation" testID="audio-studio-conversion-cohort-segmentation">
            <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700', marginBottom: 6 }}>Cohort Segmentation</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginBottom: 4 }}>Top Geo Countries</Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5 }} data-testid="audio-studio-cohort-geo" testID="audio-studio-cohort-geo">
              {topGeo.length ? topGeo.map(([k, v]) => `${k}:${v}`).join(' · ') : 'No geo data'}
            </Text>

            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6, marginBottom: 4 }}>Top Devices</Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5 }} data-testid="audio-studio-cohort-device" testID="audio-studio-cohort-device">
              {topDevice.length ? topDevice.map(([k, v]) => `${k}:${v}`).join(' · ') : 'No device data'}
            </Text>

            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6, marginBottom: 4 }}>Top Channels</Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5 }} data-testid="audio-studio-cohort-channel" testID="audio-studio-cohort-channel">
              {topChannel.length ? topChannel.map(([k, v]) => `${k}:${v}`).join(' · ') : 'No channel data'}
            </Text>
          </View>
        </>
      )}
    </View>
  );
};

export default AudioStudioConversionCard;
