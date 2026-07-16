import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useTranslation } from '../../hooks/useTranslation';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const _C = getC(true);

export default function UserInsightsPanel({ colors }: { colors: any }) {
  const { darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = getC(darkMode);
  const { data, loading: dLoading, refetch: refetchDashboard } = useLiveQuery('/admin/insights/dashboard', { entity: 'insights', pollInterval: 60000 });
  const { data: usersData, loading: uLoading, refetch: refetchUsers } = useLiveQuery('/admin/insights/users', { entity: 'insights', pollInterval: 60000 });
  const { data: churnData, loading: cLoading, refetch: refetchChurn } = useLiveQuery('/admin/insights/churn-risk', { entity: 'insights', pollInterval: 60000 });
  const users = usersData?.users || [];
  const churn = churnData?.at_risk_users || [];
  const loading = dLoading || uLoading || cLoading;
  const [tab, setTab] = useState<'overview' | 'users' | 'churn'>('overview');

  const load = () => {
    refetchDashboard?.();
    refetchUsers?.();
    refetchChurn?.();
  };

  if (loading) return <ActivityIndicator style={{ padding: 30 }} color={C.blue} />;

  const o = data?.overview || {};
  const ed = data?.engagement_distribution || {};
  const fa = data?.feature_adoption || {};

  return (
    <View data-testid="user-insights-panel" testID="user-insights-panel">
      <AutoFixBanner domain="user_insights" />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }} data-testid="insights-title" testID="insights-title">{tx('admin.userInsights.title', 'User Insights')}</Text>
        <TouchableOpacity onPress={load} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }} data-testid="refresh-insights-btn" testID="refresh-insights-btn">
          <Ionicons name="refresh" size={12} color={C.muted} />
          <Text style={{ fontSize: 10, fontWeight: '600', color: C.muted }}>{tx('admin.userInsights.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {[{ id: 'overview' as const, label: 'Overview' }, { id: 'users' as const, label: 'Engagement' }, { id: 'churn' as const, label: 'Churn Risk' }].map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTab(t.id)} data-testid={`insights-tab-${t.id}`} testID={`insights-tab-${t.id}`}
            style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: tab === t.id ? C.blue : C.card, borderWidth: 1, borderColor: tab === t.id ? C.blue : C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? 'var(--app-primary-text)' : C.muted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
            {[
              { v: o.total_users, l: 'Total Users', c: C.blue, i: 'people' },
              { v: o.active_7d, l: 'Active 7d', c: C.green, i: 'pulse' },
              { v: o.paid_users, l: 'Paid', c: C.purple, i: 'diamond' },
              { v: `${o.conversion_rate}%`, l: 'Conversion', c: C.orange, i: 'trending-up' },
            ].map(s => (
              <View key={s.l} style={{ flex: 1, minWidth: 100, backgroundColor: C.card, borderRadius: 14, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
                <Ionicons name={s.i as any} size={16} color={s.c} />
                <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, marginTop: 4 }}>{s.v}</Text>
                <Text style={{ fontSize: 9, fontWeight: '600', color: C.muted, textTransform: 'uppercase' }}>{s.l}</Text>
              </View>
            ))}
          </View>

          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted, marginBottom: 10 }}>{tx('admin.userInsights.sections.engagementDistribution', 'Engagement Distribution')}</Text>
              {Object.entries(ed).map(([k, v]) => {
                const colors: Record<string, string> = { high: C.green, medium: C.yellow, low: C.orange, dormant: C.red };
                return (
                  <View key={k} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors[k] || C.muted }} />
                      <Text style={{ fontSize: 12, color: C.text, textTransform: 'capitalize' }}>{k}</Text>
                    </View>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{v as number}</Text>
                  </View>
                );
              })}
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted, marginBottom: 10 }}>{tx('admin.userInsights.sections.featureAdoption', 'Feature Adoption')}</Text>
              {Object.entries(fa).map(([k, v]) => (
                <View key={k} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ fontSize: 12, color: C.text, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</Text>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.blue }}>{v as number}</Text>
                </View>
              ))}
            </View>
          </View>
        </>
      )}

      {tab === 'users' && (
        <View style={{ gap: 6 }}>
          {users.slice(0, 15).map(u => (
            <View key={u.user_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }} data-testid={`insight-user-${u.user_id}`} testID={`insight-user-${u.user_id}`}>
              <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.blue }}>{(u.name || '?')[0]}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{u.name || u.email}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{u.plan} | {u.sessions_7d} sessions</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={{ fontSize: 16, fontWeight: '800', color: u.engagement_score >= 60 ? C.green : u.engagement_score >= 30 ? C.yellow : C.red }}>{u.engagement_score}</Text>
                <Text style={{ fontSize: 8, color: C.muted }}>{tx('admin.userInsights.labels.score', 'SCORE')}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {tab === 'churn' && (
        <View style={{ gap: 6 }}>
          {churn.length === 0 ? (
            <View style={{ alignItems: 'center', padding: 30 }}>
              <Ionicons name="happy-outline" size={36} color={C.green} />
              <Text style={{ fontSize: 13, color: C.green, marginTop: 8, fontWeight: '600' }}>{tx('admin.userInsights.states.noHighRiskUsers', 'No high-risk users detected')}</Text>
            </View>
          ) : churn.map(u => (
            <View key={u.user_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: u.risk_level === 'critical' ? (globalThis as any).__alphaColor(C.red, '40') : C.border }} data-testid={`churn-${u.user_id}`} testID={`churn-${u.user_id}`}>
              <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="warning" size={16} color={C.red} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{u.name || u.email}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{u.factors?.join(', ')}</Text>
              </View>
              <View style={{ backgroundColor: u.risk_level === 'critical' ? (globalThis as any).__alphaColor(C.red, '15') : u.risk_level === 'high' ? C.orange + '15' : C.yellow + '15', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: u.risk_level === 'critical' ? C.red : u.risk_level === 'high' ? C.orange : C.yellow }}>{u.risk_score}%</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
