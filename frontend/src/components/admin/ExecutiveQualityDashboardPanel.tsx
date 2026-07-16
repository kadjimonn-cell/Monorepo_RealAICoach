import React, { useCallback, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const SEMANTIC = {
  success: 'var(--app-success)',
  warning: 'var(--app-warning)',
  error: 'var(--app-error)',
  info: 'var(--app-primary)',
};

const statusColor = (value: string) => {
  const normalized = String(value || '').toLowerCase();
  if (['healthy', 'ok', 'completed', 'low'].includes(normalized)) return SEMANTIC.success;
  if (['warning', 'elevated', 'partial', 'medium'].includes(normalized)) return SEMANTIC.warning;
  return SEMANTIC.error;
};

export default function ExecutiveQualityDashboardPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      const safeGet = async (url: string, pauseMs = 0) => {
        if (pauseMs > 0) {
          await new Promise((resolve) => setTimeout(resolve, pauseMs));
        }
        try {
          const res = await api.get(url);
          return { ok: true, data: res.data || {} };
        } catch (e: any) {
          return { ok: false, data: {}, status: e?.response?.status || 0 };
        }
      };

      const themeRes = await safeGet('/admin/platform-perf/theme-visibility-audit');
      const languageRes = await safeGet('/i18n/admin/language-quality-dashboard');
      const pagePerfRes = await safeGet('/admin/page-performance/dashboard?period=1h');
      const routeRes = await safeGet('/admin/platform-perf/route-health', 200);
      const shellRes = await safeGet('/admin/platform-perf/shell-health?hours=24', 400);

      const hadRateLimit = [themeRes, languageRes, pagePerfRes, routeRes, shellRes].some((row) => row.status === 429);
      setNotice(hadRateLimit ? 'Some quality signals are temporarily cooling down; showing the latest available data.' : '');

      setData({
        theme: themeRes.data || {},
        route: routeRes.data || {},
        shell: shellRes.data || {},
        pagePerf: pagePerfRes.data || {},
        language: languageRes.data || {},
      });
    } catch (e) {
      console.error('Executive quality dashboard load error:', e);
      setData(null);
      setNotice('');
    } finally {
      setLoading(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/executive-quality-dashboard/hybrid-refresh',
    onTick: load,
    runOnMount: true,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const summaryCards = useMemo(() => {
    const themeSummary = data?.theme?.summary || {};
    const routeSummary = data?.route?.summary || {};
    const shellAlert = data?.shell?.alert || {};
    const languageSummary = data?.language?.summary || {};
    const pagePerf = data?.pagePerf?.kpis || {};
    return [
      { id: 'theme', label: 'Theme Drift', value: `${themeSummary.critical || 0} critical`, color: Number(themeSummary.critical || 0) === 0 ? SEMANTIC.success : SEMANTIC.error, icon: 'color-palette' },
      { id: 'language', label: 'Fallback Hits (7d)', value: String(languageSummary.total_fallback_hits || 0), color: Number(languageSummary.total_fallback_hits || 0) === 0 ? SEMANTIC.success : SEMANTIC.warning, icon: 'swap-horizontal' },
      { id: 'route', label: 'Route Integrity', value: `${routeSummary.direct_integrity_pct || 0}%`, color: Number(routeSummary.direct_integrity_pct || 0) >= 99 ? SEMANTIC.success : SEMANTIC.warning, icon: 'git-network' },
      { id: 'startup', label: 'Startup Alert Band', value: String(shellAlert.status || 'unknown').toUpperCase(), color: statusColor(shellAlert.status || 'warning'), icon: 'flash' },
      { id: 'lcp', label: 'App Ready P95', value: `${Math.round(Number(pagePerf.p95_ms || 0)) || 0}ms`, color: Number(pagePerf.p95_ms || 0) <= 2000 ? SEMANTIC.success : Number(pagePerf.p95_ms || 0) <= 4000 ? SEMANTIC.warning : SEMANTIC.error, icon: 'speedometer' },
    ];
  }, [data]);

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} style={{ marginVertical: 20 }} />;
  if (!data) return <Text style={{ color: colors.textMuted }}>{tx('admin.executiveQualityDashboardPanel.auto.text.001', 'Unable to load executive quality dashboard.')}</Text>;

  const themeSummary = data.theme?.summary || {};
  const routeSummary = data.route?.summary || {};
  const shellTotals = data.shell?.totals || {};
  const languageSummary = data.language?.summary || {};
  const topLanguages = Array.isArray(data.language?.languages) ? data.language.languages.slice(0, 5) : [];

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }} data-testid="executive-quality-dashboard-panel" testID="executive-quality-dashboard-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="executive-quality-dashboard-title" testID="executive-quality-dashboard-title">{tx('admin.executiveQualityDashboardPanel.auto.text.002', 'Executive Quality Dashboard')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="executive-quality-dashboard-subtitle" testID="executive-quality-dashboard-subtitle">{tx('admin.executiveQualityDashboardPanel.auto.text.003', 'One place for startup stability, theme drift, route integrity, and language quality.')}</Text>
        </View>
        <TouchableOpacity onPress={load} data-testid="executive-quality-dashboard-refresh" testID="executive-quality-dashboard-refresh" style={{ padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
          <Ionicons name="refresh" size={16} color={'var(--app-primary)'} />
        </TouchableOpacity>
      </View>

      {notice ? (
        <View style={{ backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft, borderRadius: 10, padding: 10 }} data-testid="executive-quality-dashboard-notice" testID="executive-quality-dashboard-notice">
          <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{notice}</Text>
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="executive-quality-dashboard-summary" testID="executive-quality-dashboard-summary">
        {summaryCards.map((card) => (
          <View key={card.id} style={{ flex: 1, minWidth: 135, backgroundColor: (globalThis as any).__alphaColor(card.color, '10'), borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(card.color, '20'), padding: 12 }} data-testid={`executive-quality-summary-${card.id}`} testID={`executive-quality-summary-${card.id}`}>
            <Ionicons name={card.icon as any} size={14} color={card.color} />
            <Text style={{ color: card.color, fontSize: 18, fontWeight: '900', marginTop: 6 }}>{card.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 260, backgroundColor: colors.surfaceHover, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="executive-quality-theme-card" testID="executive-quality-theme-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('admin.executiveQualityDashboardPanel.auto.text.004', 'Theme Visibility')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Status {String(data.theme?.status || 'unknown')} • critical {themeSummary.critical || 0} • high {themeSummary.high || 0} • medium {themeSummary.medium || 0}</Text>
        </View>

        <View style={{ flex: 1, minWidth: 260, backgroundColor: colors.surfaceHover, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="executive-quality-route-card" testID="executive-quality-route-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('admin.executiveQualityDashboardPanel.auto.text.005', 'Route Health')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Direct integrity {routeSummary.direct_integrity_pct || 0}% • Protected integrity {routeSummary.protected_integrity_pct || 0}% • Nav lock {routeSummary.navigation_lock_status || 'unknown'}</Text>
        </View>

        <View style={{ flex: 1, minWidth: 260, backgroundColor: colors.surfaceHover, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="executive-quality-startup-card" testID="executive-quality-startup-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('admin.executiveQualityDashboardPanel.auto.text.006', 'Startup Stability')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Fallback activations {shellTotals.fallback_activations || 0} • Route recoveries {shellTotals.route_recoveries || 0} • 429s {shellTotals.rate_limit_429s || 0}</Text>
        </View>
      </View>

      <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="executive-quality-language-card" testID="executive-quality-language-card">
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('admin.executiveQualityDashboardPanel.auto.text.007', 'Language Quality Watchlist')}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 10 }}>Avg coverage {languageSummary.avg_coverage || 0}% • Avg quality {languageSummary.avg_quality_score || 0} • Missing keys {languageSummary.total_missing_keys || 0}</Text>
        {topLanguages.map((lang: any) => (
          <View key={lang.code} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30') }} data-testid={`executive-quality-language-${lang.code}`} testID={`executive-quality-language-${lang.code}`}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{lang.name}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>Coverage {lang.coverage_pct}% • Quality {lang.quality_score ?? '--'} • Fallback hits {lang.fallback_hits}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
