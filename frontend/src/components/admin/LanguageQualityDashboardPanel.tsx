import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import LanguageSmokeMonitorCard from './LanguageSmokeMonitorCard';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const cardTone = (value, good, warn) => value >= good ? 'var(--app-success)' : value >= warn ? 'var(--app-warning)' : 'var(--app-error)';

export default function LanguageQualityDashboardPanel({ colors: _colors }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningSmoke, setRunningSmoke] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get('/i18n/admin/language-quality-dashboard');
      setData(res.data || null);
    } catch (e) {
      console.error('Language quality dashboard load error:', e);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/language-quality-dashboard/hybrid-refresh',
    onTick: load,
    runOnMount: true,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const runSmokeAudit = useCallback(async () => {
    setRunningSmoke(true);
    try {
      await api.post('/i18n/admin/multilingual-smoke-report/run');
      await load();
    } catch (e) {
      console.error('Language smoke monitor run error:', e);
    } finally {
      setRunningSmoke(false);
    }
  }, [load]);

  if (loading) {
    return <ActivityIndicator color={colors.primary} style={{ marginVertical: 20 }} />;
  }

  if (!data) {
    return <Text style={{ color: colors.textMuted, marginBottom: 16 }}>{tx('admin.languageQualityDashboardPanel.auto.text.001', 'Unable to load language quality dashboard.')}</Text>;
  }

  const summary = data.summary || {};
  const languages = Array.isArray(data.languages) ? data.languages.slice(0, 6) : [];
  const hotspotRoutes = Array.isArray(data.hotspot_routes) ? data.hotspot_routes.slice(0, 5) : [];
  const hotspotKeys = Array.isArray(data.hotspot_keys) ? data.hotspot_keys.slice(0, 5) : [];
  const smokeReport = data.smoke_report || null;

  return (
    <View style={{ marginBottom: 18 }} data-testid="admin-language-quality-dashboard" testID="admin-language-quality-dashboard">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="admin-language-quality-dashboard-title" testID="admin-language-quality-dashboard-title">{tx('admin.languageQualityDashboardPanel.auto.text.002', 'Language Quality Dashboard')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="admin-language-quality-dashboard-subtitle" testID="admin-language-quality-dashboard-subtitle">{tx('admin.languageQualityDashboardPanel.auto.text.003', 'Coverage, AI quality scoring, and runtime fallback pressure in one view.')}</Text>
        </View>
        <TouchableOpacity onPress={load} data-testid="admin-language-quality-dashboard-refresh" testID="admin-language-quality-dashboard-refresh" style={{ padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
          <Ionicons name="refresh" size={16} color={colors.primary} />
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }} data-testid="admin-language-quality-dashboard-summary" testID="admin-language-quality-dashboard-summary">
        {[
          { id: 'avg-coverage', label: 'Avg Coverage', value: `${summary.avg_coverage || 0}%`, color: cardTone(Number(summary.avg_coverage || 0), 95, 80), icon: 'pie-chart' },
          { id: 'avg-quality-score', label: 'Avg Quality', value: `${summary.avg_quality_score || 0}`, color: cardTone(Number(summary.avg_quality_score || 0), 90, 75), icon: 'sparkles' },
          { id: 'fallback-hits', label: 'Fallback Hits (7d)', value: String(summary.total_fallback_hits || 0), color: Number(summary.total_fallback_hits || 0) === 0 ? 'var(--app-success)' : 'var(--app-warning)', icon: 'swap-horizontal' },
          { id: 'attention', label: 'Needs Attention', value: String(summary.languages_needing_attention || 0), color: Number(summary.languages_needing_attention || 0) === 0 ? 'var(--app-success)' : 'var(--app-error)', icon: 'warning' },
        ].map((item) => (
          <View key={item.id} style={{ flex: 1, minWidth: 130, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '20') }} data-testid={`language-quality-summary-${item.id}`} testID={`language-quality-summary-${item.id}`}>
            <Ionicons name={item.icon} size={15} color={item.color} />
            <Text style={{ color: item.color, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{item.label}</Text>
          </View>
        ))}
      </View>

      <LanguageSmokeMonitorCard
        colors={colors}
        report={smokeReport}
        running={runningSmoke}
        onRun={runSmokeAudit}
      />

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="language-quality-top-languages-card" testID="language-quality-top-languages-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('admin.languageQualityDashboardPanel.auto.text.004', 'Priority Languages')}</Text>
          {languages.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.languageQualityDashboardPanel.auto.text.005', 'No language quality data yet.')}</Text>
          ) : languages.map((lang) => (
            <View key={lang.code} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30') }} data-testid={`language-quality-language-${lang.code}`} testID={`language-quality-language-${lang.code}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{lang.name}</Text>
                <Text style={{ color: lang.needs_attention ? 'var(--app-error)' : 'var(--app-success)', fontSize: 10, fontWeight: '700' }}>{lang.needs_attention ? 'ATTENTION' : 'HEALTHY'}</Text>
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>
                Coverage {lang.coverage_pct}% • Quality {lang.quality_score ?? '--'} • Fallback hits {lang.fallback_hits} ({lang.fallback_hits_per_1k_keys}/1k keys)
              </Text>
            </View>
          ))}
        </View>

        <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="language-quality-hotspots-card" testID="language-quality-hotspots-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('admin.languageQualityDashboardPanel.auto.text.006', 'Runtime Fallback Hotspots')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', marginBottom: 6 }}>{tx('admin.languageQualityDashboardPanel.auto.text.007', 'ROUTES')}</Text>
          {hotspotRoutes.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.languageQualityDashboardPanel.auto.text.008', 'No runtime fallback hits recorded yet.')}</Text>
          ) : hotspotRoutes.map((row, idx) => (
            <Text key={`route-${idx}`} style={{ color: colors.text, fontSize: 11, marginBottom: 4 }} data-testid={`language-quality-hotspot-route-${idx}`} testID={`language-quality-hotspot-route-${idx}`}>{row.route} — {row.hits}</Text>
          ))}
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', marginTop: 10, marginBottom: 6 }}>{tx('admin.languageQualityDashboardPanel.auto.text.009', 'KEYS')}</Text>
          {hotspotKeys.map((row, idx) => (
            <Text key={`key-${idx}`} style={{ color: colors.text, fontSize: 11, marginBottom: 4 }} data-testid={`language-quality-hotspot-key-${idx}`} testID={`language-quality-hotspot-key-${idx}`}>{row.key} — {row.hits}</Text>
          ))}
        </View>
      </View>
    </View>
  );
}