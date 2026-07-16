import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';

import api from '../../services/api';

type SportsConversionCardProps = {
  colors: any;
};

type SportsConversionPayload = {
  window_days?: number;
  generated_at?: string;
  kpis?: {
    active_viewers?: number;
    total_plays?: number;
    completed_plays?: number;
    live_ratio_pct?: number;
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
    league?: Record<string, number>;
  };
};

const formatPct = (value?: number) => `${Number(value || 0).toFixed(1)}%`;

export const SportsConversionCard: React.FC<SportsConversionCardProps> = ({ colors }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<SportsConversionPayload | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/sports/v2/admin/conversion-dashboard?window_days=7', {
        silentLoading: true,
        skipDedupe: true,
      });
      setPayload(response?.data || {});
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || 'Unable to load sports conversion dashboard'));
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const topGeo = useMemo(() => {
    const rows = Object.entries(payload?.cohort_segmentation?.geo_country || {});
    return rows.slice(0, 3);
  }, [payload?.cohort_segmentation?.geo_country]);

  const topLeagues = useMemo(() => {
    const rows = Object.entries(payload?.cohort_segmentation?.league || {});
    return rows.slice(0, 4);
  }, [payload?.cohort_segmentation?.league]);

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 12,
        gap: 8,
      }}
      data-testid="sports-conversion-card"
      testID="sports-conversion-card"
    >
      <Text style={{ color: colors.text, fontWeight: '800', fontSize: 15 }} data-testid="sports-conversion-title">
        Sports Conversion Intelligence
      </Text>
      <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="sports-conversion-subtitle">
        Feature 30 v2 growth funnel, watch completion, and cohort quality signals.
      </Text>

      {loading ? (
        <View style={{ paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="sports-conversion-loading">
          <ActivityIndicator size="small" color={colors.warningText} />
          <Text style={{ color: colors.textSec, fontSize: 12 }}>Loading conversion metrics…</Text>
        </View>
      ) : null}

      {!loading && error ? (
        <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '700' }} data-testid="sports-conversion-error">
          {error}
        </Text>
      ) : null}

      {!loading && !error && payload ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }} data-testid="sports-conversion-kpi-strip">
          <View style={{ minWidth: 130, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }} data-testid="sports-kpi-active-viewers">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Active Viewers</Text>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{Number(payload?.kpis?.active_viewers || 0)}</Text>
          </View>
          <View style={{ minWidth: 130, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }} data-testid="sports-kpi-completion-rate">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Completion Rate</Text>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{formatPct(payload?.kpis?.completion_rate_pct)}</Text>
          </View>
          <View style={{ minWidth: 130, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }} data-testid="sports-kpi-live-ratio">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Live Ratio</Text>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{formatPct(payload?.kpis?.live_ratio_pct)}</Text>
          </View>
          <View style={{ minWidth: 130, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }} data-testid="sports-kpi-upgrade-rate">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Free → Paid</Text>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{formatPct(payload?.upgrade_funnel?.free_to_paid_rate_pct)}</Text>
          </View>
        </ScrollView>
      ) : null}

      {!loading && !error && payload ? (
        <View style={{ gap: 6 }} data-testid="sports-conversion-cohort-section">
          <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12.5 }}>Top Cohorts</Text>
          <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="sports-conversion-top-geo">
            Geo: {topGeo.map(([k, v]) => `${k} (${v})`).join(' • ') || 'No data'}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="sports-conversion-top-leagues">
            Leagues: {topLeagues.map(([k, v]) => `${k} (${v})`).join(' • ') || 'No data'}
          </Text>
        </View>
      ) : null}
    </View>
  );
};

export default SportsConversionCard;
