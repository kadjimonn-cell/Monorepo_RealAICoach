import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const statusTone = (status) => {
  if (status === 'healthy') return { fg: 'var(--app-success)', bg: 'var(--app-success-soft)', border: 'var(--app-success-soft)', label: 'Healthy' };
  if (status === 'watch') return { fg: 'var(--app-warning)', bg: 'var(--app-warning-soft)', border: 'var(--app-warning-soft)', label: 'Watch' };
  return { fg: 'var(--app-error)', bg: 'var(--app-error-soft)', border: 'var(--app-error-soft)', label: 'Critical' };
};

export default function LanguageSmokeMonitorCard({ colors: _colors, report, running, onRun }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  if (!report) return null;

  const tone = statusTone(report?.overall_status);
  const summary = report?.summary || {};
  const routeResults = Array.isArray(report?.route_results) ? report.route_results : [];
  const languageResults = Array.isArray(report?.language_results) ? report.language_results : [];
  const routeFallbacks = Array.isArray(report?.top_route_fallbacks) ? report.top_route_fallbacks : [];

  return (
    <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 18 }} data-testid="admin-language-smoke-monitor-card" testID="admin-language-smoke-monitor-card">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }} data-testid="admin-language-smoke-monitor-title" testID="admin-language-smoke-monitor-title">{tx('admin.languageSmokeMonitorCard.auto.text.001', 'Nightly Multilingual Smoke Monitor')}</Text>
            <View style={{ backgroundColor: tone.bg, borderColor: tone.border, borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="admin-language-smoke-monitor-status-pill" testID="admin-language-smoke-monitor-status-pill">
              <Text style={{ color: tone.fg, fontSize: 10, fontWeight: '800' }}>{tone.label}</Text>
            </View>
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="admin-language-smoke-monitor-subtitle" testID="admin-language-smoke-monitor-subtitle">{tx('admin.languageSmokeMonitorCard.auto.text.002', 'Latest automated smoke snapshot for language persistence, route availability, API translation health, and fallback pressure.')}</Text>
        </View>

        <TouchableOpacity
          onPress={onRun}
          disabled={running}
          style={{ backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, minWidth: 132, alignItems: 'center' }}
          data-testid="admin-language-smoke-monitor-run-button" testID="admin-language-smoke-monitor-run-button"
        >
          {running ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="scan-outline" size={15} color={'var(--app-primary)'} />
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tx('admin.languageSmokeMonitorCard.auto.text.003', 'Run Smoke Audit')}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }} data-testid="admin-language-smoke-monitor-summary-grid" testID="admin-language-smoke-monitor-summary-grid">
        {[
          { id: 'score', label: 'Smoke Score', value: `${report?.score || 0}/100`, color: tone.fg, icon: 'sparkles' },
          { id: 'routes', label: 'Routes Healthy', value: `${summary.routes_ok || 0}/${summary.routes_total || 0}`, color: (summary.broken_links || 0) === 0 ? 'var(--app-success)' : 'var(--app-warning)', icon: 'link' },
          { id: 'languages', label: 'Languages Probed', value: `${summary.languages_ok || 0}/${summary.languages_total || 0}`, color: (summary.languages_ok || 0) === (summary.languages_total || 0) ? 'var(--app-success)' : 'var(--app-warning)', icon: 'language' },
          { id: 'fallbacks', label: 'Fallback Hits (24h)', value: String(summary.fallback_hits_24h || 0), color: (summary.fallback_hits_24h || 0) === 0 ? 'var(--app-success)' : 'var(--app-error)', icon: 'warning-outline' },
          { id: 'api', label: 'API Coverage', value: `${summary.api_overall_pct || 0}%`, color: (summary.api_overall_pct || 0) >= 95 ? 'var(--app-success)' : 'var(--app-warning)', icon: 'server-outline' },
          { id: 'cache', label: 'Cache Entries', value: String(summary.cache_entries || 0), color: colors.primary, icon: 'albums-outline' },
        ].map((item) => (
          <View key={item.id} style={{ flex: 1, minWidth: 135, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '22') }} data-testid={`admin-language-smoke-monitor-summary-${item.id}`} testID={`admin-language-smoke-monitor-summary-${item.id}`}>
            <Ionicons name={item.icon} size={15} color={item.color} />
            <Text style={{ color: item.color, fontSize: 18, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{item.label}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="admin-language-smoke-monitor-routes-card" testID="admin-language-smoke-monitor-routes-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('admin.languageSmokeMonitorCard.auto.text.004', 'Monitored Routes')}</Text>
          {routeResults.map((row, idx) => (
            <View key={`${row.route}-${idx}`} style={{ paddingVertical: 8, borderBottomWidth: idx === routeResults.length - 1 ? 0 : 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30') }} data-testid={`admin-language-smoke-route-${idx}`} testID={`admin-language-smoke-route-${idx}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{row.route}</Text>
                <Text style={{ color: row.ok ? 'var(--app-success)' : 'var(--app-error)', fontSize: 10, fontWeight: '800' }}>{row.ok ? 'OK' : 'ATTN'}</Text>
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>
                HTTP {row.status_code || 0} • Fallbacks {row.fallback_hits_24h || 0}
              </Text>
            </View>
          ))}
        </View>

        <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="admin-language-smoke-monitor-languages-card" testID="admin-language-smoke-monitor-languages-card">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('admin.languageSmokeMonitorCard.auto.text.005', 'Language Probe Samples')}</Text>
          <ScrollView style={{ maxHeight: 220 }} data-testid="admin-language-smoke-monitor-languages-scroll" testID="admin-language-smoke-monitor-languages-scroll">
            {languageResults.map((row) => (
              <View key={row.code} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '25') }} data-testid={`admin-language-smoke-language-${row.code}`} testID={`admin-language-smoke-language-${row.code}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{row.code.toUpperCase()}</Text>
                  <Text style={{ color: row.ok ? 'var(--app-success)' : 'var(--app-error)', fontSize: 10, fontWeight: '800' }}>{row.changed_count} translated</Text>
                </View>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} numberOfLines={2}>
                  Dashboard → {row.sample?.Dashboard || '--'} • Settings → {row.sample?.Settings || '--'}
                </Text>
              </View>
            ))}
          </ScrollView>
        </View>
      </View>

      <View style={{ marginTop: 14, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="admin-language-smoke-monitor-footer-card" testID="admin-language-smoke-monitor-footer-card">
        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{tx('admin.languageSmokeMonitorCard.auto.text.006', 'Top Runtime Fallback Hotspots')}</Text>
        {routeFallbacks.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.languageSmokeMonitorCard.auto.text.007', 'No fallback hotspots in the last 24 hours.')}</Text>
        ) : routeFallbacks.map((row, idx) => (
          <Text key={`${row.route}-${idx}`} style={{ color: colors.textMuted, fontSize: 11, marginBottom: 4 }} data-testid={`admin-language-smoke-monitor-hotspot-${idx}`} testID={`admin-language-smoke-monitor-hotspot-${idx}`}>
            {row.route} — {row.hits} hits
          </Text>
        ))}
        <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 8 }} data-testid="admin-language-smoke-monitor-generated-at" testID="admin-language-smoke-monitor-generated-at">
          Latest report: {report?.generated_at ? new Date(report.generated_at).toLocaleString() : '—'}
        </Text>
      </View>
    </View>
  );
}