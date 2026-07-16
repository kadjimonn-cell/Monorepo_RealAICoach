import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

import { useAdminTheme } from '../../hooks/useAdminTheme';
let C = {
  bg: 'var(--app-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any, muted: 'var(--app-text-muted)' as any, primary: 'var(--app-primary)' as any, emerald: 'var(--app-success)',
  amber: 'var(--app-warning)', rose: 'var(--app-error)', violet: 'var(--app-primary)',
};

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <View style={{ backgroundColor: `${color}20`, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: `${color}40` }}>
      <Text style={{ color, fontSize: 11, fontWeight: '700' }}>{text}</Text>
    </View>
  );
}

export default function EmailCoverageMatrixPanel() {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  C = {
    ...C,
    bg: AC.bg,
    border: AC.border,
    text: AC.text,
    muted: AC.textDim,
    surface: AC.card,
    surfaceHover: AC.surfaceHover,
  };
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'label' | 'total_sent' | 'delivery_rate'>('label');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const res = await api.get('/email-notifications/coverage-matrix');
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator color={C.primary} size="large" /></View>;
  if (error) return <View style={{ padding: 20 }}><Text style={{ color: C.error }}>{error}</Text></View>;
  if (!data) return null;

  const { summary, categories, matrix } = data;

  const filtered = matrix.filter((r: any) => {
    if (filter === 'all') return true;
    if (filter === 'healthy') return r.render_health === 'pass';
    if (filter === 'failed') return r.render_health === 'fail';
    if (filter === 'triggered') return r.total_sent > 0;
    if (filter === 'never') return r.total_sent === 0;
    return r.category === filter;
  });

  const sorted = [...filtered].sort((a: any, b: any) => {
    if (sortBy === 'total_sent') return b.total_sent - a.total_sent;
    if (sortBy === 'delivery_rate') return (b.delivery_rate || 0) - (a.delivery_rate || 0);
    return a.label.localeCompare(b.label);
  });

  const catNames = Object.keys(categories || {}).sort();
  const pills = [
    { id: 'all', label: 'All', count: matrix.length },
    { id: 'healthy', label: 'Healthy', count: summary.render_healthy },
    { id: 'failed', label: 'Failed', count: summary.render_failed },
    { id: 'triggered', label: 'Triggered', count: summary.live_triggered },
    { id: 'never', label: 'Never Sent', count: summary.never_triggered_count },
    ...catNames.map(c => ({ id: c, label: c, count: (categories as any)[c]?.total || 0 })),
  ];

  return (
    <View style={{ flex: 1 }} data-testid="email-coverage-matrix-panel" testID="email-coverage-matrix-panel">
      {/* Summary KPIs */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Templates', value: summary.total_templates, color: C.primary },
          { label: 'Render Health', value: `${summary.health_pct}%`, color: summary.health_pct === 100 ? C.success : C.warning },
          { label: 'Live Coverage', value: `${summary.coverage_pct}%`, color: summary.coverage_pct > 50 ? C.success : C.warning },
          { label: 'Never Triggered', value: summary.never_triggered_count, color: summary.never_triggered_count > 10 ? C.error : C.muted },
        ].map((kpi, i) => (
          <View key={i} style={{ flex: 1, minWidth: 140, backgroundColor: C.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid={`email-coverage-kpi-${i}`} testID={`email-coverage-kpi-${i}`}>
            <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{kpi.label}</Text>
            <Text style={{ color: kpi.color, fontSize: 24, fontWeight: '800' }}>{kpi.value}</Text>
          </View>
        ))}
      </View>

      {/* Filter Pills */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', gap: 6, paddingRight: 16 }}>
          {pills.map(p => (
            <TouchableOpacity key={p.id} onPress={() => setFilter(p.id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: filter === p.id ? C.primary : C.surfaceHover, borderWidth: 1, borderColor: filter === p.id ? C.primary : C.border }} data-testid={`email-coverage-filter-${p.id}`} testID={`email-coverage-filter-${p.id}`}>
              <Text style={{ color: filter === p.id ? 'var(--app-primary-text)' : C.text, fontSize: 12, fontWeight: '600' }}>{p.label}</Text>
              <View style={{ backgroundColor: filter === p.id ? 'rgba(255,255,255,0.2)' : C.surface, borderRadius: 4, paddingHorizontal: 4, paddingVertical: 1 }}>
                <Text style={{ color: filter === p.id ? 'var(--app-primary-text)' : C.muted, fontSize: 10, fontWeight: '700' }}>{p.count}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Sort Row */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600' }}>{tx('admin.emailCoverageMatrix.sortLabel', 'Sort:')}</Text>
        {(['label', 'total_sent', 'delivery_rate'] as const).map(s => (
          <TouchableOpacity key={s} onPress={() => setSortBy(s)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: sortBy === s ? C.primary : 'transparent' }} data-testid={`email-coverage-sort-${s}`} testID={`email-coverage-sort-${s}`}>
            <Text style={{ color: sortBy === s ? 'var(--app-primary-text)' : C.muted, fontSize: 11, fontWeight: '600' }}>{s === 'label' ? 'Name' : s === 'total_sent' ? 'Volume' : 'Delivery %'}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Template Matrix */}
      <View style={{ gap: 8 }}>
        {sorted.map((tpl: any) => (
          <View key={tpl.key} style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: C.border, gap: 12 }} data-testid={`email-coverage-row-${tpl.key}`} testID={`email-coverage-row-${tpl.key}`}>
            {/* Status dot */}
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tpl.render_health === 'pass' ? C.success : C.error }} />

            {/* Info */}
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{tpl.label}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                <Text style={{ color: C.muted, fontSize: 10 }}>{tpl.category}</Text>
                {tpl.total_sent > 0 && <Text style={{ color: C.successText, fontSize: 10, fontWeight: '600' }}>{tpl.total_sent} sent</Text>}
                {tpl.total_sent === 0 && <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '600' }}>{tx('admin.emailCoverageMatrix.states.neverTriggered', 'Never triggered')}</Text>}
              </View>
            </View>

            {/* Stats */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              {tpl.delivery_rate !== null && <Badge text={`${tpl.delivery_rate}% delivered`} color={tpl.delivery_rate >= 95 ? C.success : tpl.delivery_rate >= 80 ? C.warning : C.error} />}
              {tpl.open_rate !== null && <Badge text={`${tpl.open_rate}% opens`} color={C.violet} />}
              <Badge text={tpl.render_health === 'pass' ? 'Healthy' : 'Failed'} color={tpl.render_health === 'pass' ? C.success : C.error} />
            </View>
          </View>
        ))}
      </View>

      {/* Refresh */}
      <TouchableOpacity onPress={load} style={{ marginTop: 16, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: C.surfaceHover, borderWidth: 1, borderColor: C.border }} data-testid="email-coverage-refresh-btn" testID="email-coverage-refresh-btn">
        <Ionicons name="refresh" size={14} color={C.muted} />
        <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600' }}>{tx('admin.emailCoverageMatrix.actions.refresh', 'Refresh')}</Text>
      </TouchableOpacity>
    </View>
  );
}
