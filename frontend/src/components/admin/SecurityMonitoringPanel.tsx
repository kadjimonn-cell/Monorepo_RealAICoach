import React from 'react';
import { View, Text, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

function MiniBarChart({ data, color, height = 50 }: { data: { day: string; count: number }[]; color: string; height?: number }) {
  const max = Math.max(...data.map(d => d.count), 1);
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 4 }}>
        {data.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <View style={{ width: '80%', height: Math.max(3, (d.count / max) * height), backgroundColor: (globalThis as any).__alphaColor(color, '60'), borderRadius: 3 }} />
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', marginTop: 4 }}>
        {data.map((d, i) => <Text key={i} style={{ flex: 1, textAlign: 'center', fontSize: 9, color: C.muted }}>{d.day}</Text>)}
      </View>
    </View>
  );
}

export default function SecurityMonitoringPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { data, loading } = useLiveQuery('/admin/manage/security/overview', { entity: 'security', pollInterval: 30000 });

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>;

  return (
    <View data-testid="security-monitoring-panel" testID="security-monitoring-panel">
      {/* KPI */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {[
          { l: 'Successful Logins (24h)', v: data?.successful_logins_24h || 0, i: 'checkmark-circle', c: C.green },
          { l: 'Failed Logins (24h)', v: data?.failed_logins_24h || 0, i: 'close-circle', c: C.red },
          { l: 'Frozen Accounts', v: data?.frozen_accounts || 0, i: 'snow', c: C.cyan },
          { l: 'Suspicious Events (7d)', v: data?.suspicious_events_7d || 0, i: 'warning', c: C.yellow },
        ].map(s => (
          <View key={s.l} style={{ flex: 1, minWidth: 150, backgroundColor: (globalThis as any).__alphaColor(s.c, '10'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.c, '20') }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', textTransform: 'uppercase' }}>{s.l}</Text>
              <Ionicons name={s.i as any} size={14} color={s.c} />
            </View>
            <Text style={{ fontSize: 26, fontWeight: '800', color: s.c }}>{s.v}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Events Chart */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.securityMonitoringPanel.auto.text.001', 'Security Events (7 Days)')}</Text>
          <MiniBarChart data={data?.daily_events || []} color={C.blue} height={60} />
        </View>

        {/* Quick Stats */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.securityMonitoringPanel.auto.text.002', 'Login Success Rate')}</Text>
          {(() => {
            const total = (data?.successful_logins_24h || 0) + (data?.failed_logins_24h || 0);
            const rate = total > 0 ? Math.round(((data?.successful_logins_24h || 0) / total) * 100) : 100;
            return (
              <View>
                <Text style={{ fontSize: 40, fontWeight: '800', color: rate > 95 ? C.green : rate > 80 ? C.yellow : C.red }}>{rate}%</Text>
                <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, marginTop: 8, overflow: 'hidden' }}>
                  <View style={{ height: '100%', width: `${rate}%`, backgroundColor: rate > 95 ? C.green : rate > 80 ? C.yellow : C.red, borderRadius: 4 }} />
                </View>
                <Text style={{ fontSize: 11, color: C.muted, marginTop: 6 }}>{data?.successful_logins_24h || 0} successful / {total} total (24h)</Text>
              </View>
            );
          })()}
        </View>
      </View>

      {/* Audit Log */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.securityMonitoringPanel.auto.text.003', 'Audit Log (24h)')}</Text>
        {(data?.recent_audit || []).length === 0 ? <Text style={{ color: C.muted, fontSize: 13 }}>{tx('admin.securityMonitoringPanel.auto.text.004', 'No events in the last 24 hours')}</Text> : (data.recent_audit || []).slice(0, 30).map((e: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 7, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: C.border }}>
            <Ionicons name={e.event_type?.includes('success') ? 'checkmark-circle' : e.event_type?.includes('fail') ? 'close-circle' : e.event_type?.includes('frozen') ? 'snow' : 'information-circle'} size={14} color={e.severity === 'high' ? C.red : e.severity === 'medium' ? C.yellow : C.green} />
            <Text style={{ flex: 1, fontSize: 11, color: C.text }}>{e.event_type?.replace(/_/g, ' ')}</Text>
            <Text style={{ fontSize: 10, color: C.sec }}>{e.user_id?.substring(0, 12)}</Text>
            <View style={{ backgroundColor: e.severity === 'high' ? (globalThis as any).__alphaColor(C.red, '20') : e.severity === 'medium' ? C.yellow + '20' : C.green + '20', borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}>
              <Text style={{ fontSize: 8, fontWeight: '700', color: e.severity === 'high' ? C.red : e.severity === 'medium' ? C.yellow : C.green }}>{e.severity}</Text>
            </View>
            <Text style={{ fontSize: 9, color: C.muted, width: 55 }}>{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
