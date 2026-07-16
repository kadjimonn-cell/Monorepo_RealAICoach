import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type RouteCard = {
  route: string;
  files: number;
  uses_t_files: number;
  estimated_hardcoded_user_copy: number;
  uses_t_coverage_pct: number;
  score: number;
  grade: string;
  status: 'healthy' | 'watch' | 'action_required';
};

type ReportCardPayload = {
  summary: {
    files_scanned: number;
    files_using_t: number;
    adoption_pct: number;
    hardcoded_copy_pct: number;
    routes_scored: number;
  };
  status_summary?: {
    healthy?: number;
    watch?: number;
    action_required?: number;
  };
  route_report_card: RouteCard[];
};

const tx = (_key: string, fallback: string) => fallback;

const statusTone = (status: string, colors: any) => {
  if (status === 'healthy') return { label: 'Healthy', color: colors.successText || colors.success };
  if (status === 'watch') return { label: 'Watch', color: colors.warningText || colors.warning };
  return { label: 'Action Required', color: colors.error };
};

export default function RouteI18nReportCardWidget() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'all' | 'healthy' | 'watch' | 'action_required'>('all');
  const [query, setQuery] = useState('');
  const [payload, setPayload] = useState<ReportCardPayload | null>(null);

  const fetchData = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.get('/admin/i18n/adoption/routes', { silentLoading: true });
      setPayload({
        summary: res.data?.summary || {
          files_scanned: 0,
          files_using_t: 0,
          adoption_pct: 0,
          hardcoded_copy_pct: 0,
          routes_scored: 0,
        },
        status_summary: res.data?.status_summary || {
          healthy: 0,
          watch: 0,
          action_required: 0,
        },
        route_report_card: Array.isArray(res.data?.route_report_card) ? res.data.route_report_card : [],
      });
    } catch {
      setPayload((prev) => prev || {
        summary: { files_scanned: 0, files_using_t: 0, adoption_pct: 0, hardcoded_copy_pct: 0, routes_scored: 0 },
        status_summary: { healthy: 0, watch: 0, action_required: 0 },
        route_report_card: [],
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData('initial');
  }, [fetchData]);

  const summary = payload?.summary;
  const cards = payload?.route_report_card || [];

  const counts = useMemo(() => {
    if (payload?.status_summary) {
      return {
        healthy: Number(payload.status_summary.healthy || 0),
        watch: Number(payload.status_summary.watch || 0),
        action_required: Number(payload.status_summary.action_required || 0),
      };
    }
    return {
      healthy: cards.filter((c) => c.status === 'healthy').length,
      watch: cards.filter((c) => c.status === 'watch').length,
      action_required: cards.filter((c) => c.status === 'action_required').length,
    };
  }, [cards, payload?.status_summary]);

  const filteredCards = useMemo(() => {
    return cards.filter((card) => {
      const passStatus = statusFilter === 'all' ? true : card.status === statusFilter;
      const q = query.trim().toLowerCase();
      const passQuery = !q || `${card.route} ${card.grade}`.toLowerCase().includes(q);
      return passStatus && passQuery;
    });
  }, [cards, statusFilter, query]);

  if (loading) {
    return (
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 16, alignItems: 'center' }} data-testid="i18n-route-report-card-loading" testID="i18n-route-report-card-loading">
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14, gap: 12 }} data-testid="i18n-route-report-card-widget" testID="i18n-route-report-card-widget">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="i18n-route-report-card-title" testID="i18n-route-report-card-title">{tx('admin.routeI18nReportCardWidget.auto.text.001', 'Route-level i18n Report Card')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="i18n-route-report-card-subtitle" testID="i18n-route-report-card-subtitle">{tx('admin.routeI18nReportCardWidget.auto.text.002', 'Health signal by route based on translation adoption and hardcoded copy risk')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => fetchData('refresh')}
          disabled={refreshing}
          style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, flexDirection: 'row', alignItems: 'center', gap: 6 }}
          data-testid="i18n-route-report-card-refresh-button"
          testID="i18n-route-report-card-refresh-button"
        >
          {refreshing ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="refresh" size={13} color={colors.textSec} />}
          <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.routeI18nReportCardWidget.auto.text.003', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {[
          { key: 'Routes Scored', value: summary?.routes_scored || 0, tone: colors.primary },
          { key: 'Adoption', value: `${summary?.adoption_pct || 0}%`, tone: colors.successText || colors.success },
          { key: 'Hardcoded Risk', value: `${summary?.hardcoded_copy_pct || 0}%`, tone: colors.error },
          { key: 'Files with t()', value: `${summary?.files_using_t || 0}/${summary?.files_scanned || 0}`, tone: colors.accent || colors.primary },
        ].map((metric) => (
          <View key={metric.key} style={{ flex: 1, minWidth: 120, borderRadius: 10, borderWidth: 1, borderColor: `${metric.tone}25`, backgroundColor: `${metric.tone}12`, padding: 10 }} data-testid={`i18n-route-report-card-metric-${metric.key.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`i18n-route-report-card-metric-${metric.key.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
            <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{metric.key}</Text>
            <Text style={{ color: metric.tone, fontSize: 16, fontWeight: '900', marginTop: 4 }}>{metric.value}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {([
          { id: 'all', label: `All (${cards.length})` },
          { id: 'healthy', label: `Healthy (${counts.healthy})` },
          { id: 'watch', label: `Watch (${counts.watch})` },
          { id: 'action_required', label: `Action (${counts.action_required})` },
        ] as const).map((item) => {
          const active = statusFilter === item.id;
          return (
            <TouchableOpacity
              key={item.id}
              onPress={() => setStatusFilter(item.id)}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: active ? `${colors.primary}50` : colors.border, backgroundColor: active ? colors.primarySoft : colors.surfaceHover }}
              data-testid={`i18n-route-report-card-filter-${item.id}`}
              testID={`i18n-route-report-card-filter-${item.id}`}
            >
              <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
            </TouchableOpacity>
          );
        })}

        <View style={{ flex: 1, minWidth: 200 }}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={tx('admin.routeI18nReportCardWidget.auto.placeholder.001', 'Search route')}
            placeholderTextColor={colors.textMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.surfaceHover, color: colors.text, paddingHorizontal: 12, paddingVertical: 8, fontSize: 11 }}
            data-testid="i18n-route-report-card-search-input"
            testID="i18n-route-report-card-search-input"
          />
        </View>
      </View>

      <View style={{ gap: 8 }} data-testid="i18n-route-report-card-list" testID="i18n-route-report-card-list">
        {filteredCards.slice(0, 12).map((card, index) => {
          const tone = statusTone(card.status, colors);
          return (
            <View key={`${card.route}-${index}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 11, backgroundColor: colors.surfaceHover, padding: 10, gap: 6 }} data-testid={`i18n-route-report-card-row-${index + 1}`} testID={`i18n-route-report-card-row-${index + 1}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', flex: 1 }} numberOfLines={1} data-testid={`i18n-route-report-card-row-${index + 1}-route`} testID={`i18n-route-report-card-row-${index + 1}-route`}>{card.route}</Text>
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, borderWidth: 1, borderColor: `${tone.color}40`, backgroundColor: `${tone.color}15` }} data-testid={`i18n-route-report-card-row-${index + 1}-status`} testID={`i18n-route-report-card-row-${index + 1}-status`}>
                  <Text style={{ color: tone.color, fontSize: 9, fontWeight: '800' }}>{tone.label}</Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>Grade {card.grade}</Text>
                <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }} data-testid={`i18n-route-report-card-row-${index + 1}-score`} testID={`i18n-route-report-card-row-${index + 1}-score`}>{card.score}/100</Text>
                <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: colors.border }}>
                  <View style={{ width: `${Math.max(0, Math.min(100, card.score))}%`, height: 6, borderRadius: 3, backgroundColor: tone.color }} />
                </View>
              </View>

              <Text style={{ color: colors.textSec, fontSize: 10 }} data-testid={`i18n-route-report-card-row-${index + 1}-details`} testID={`i18n-route-report-card-row-${index + 1}-details`}>
                Files {card.files} • Using t() {card.uses_t_files} ({card.uses_t_coverage_pct}%) • Hardcoded copy {card.estimated_hardcoded_user_copy}
              </Text>
            </View>
          );
        })}

        {filteredCards.length === 0 ? (
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 12 }} data-testid="i18n-route-report-card-empty-state" testID="i18n-route-report-card-empty-state">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.routeI18nReportCardWidget.auto.text.004', 'No routes match the selected filters.')}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}
