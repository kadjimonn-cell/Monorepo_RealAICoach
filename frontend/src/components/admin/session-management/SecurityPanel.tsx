import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';
import { Tab } from './types';
import { useTranslation } from '../../../hooks/useTranslation';

interface SecurityPanelProps {
  secLoading: boolean;
  secOverview: any;
  loadSecOverview: () => void;
  setTab: (t: Tab) => void;
}

export default function SecurityPanel({ secLoading, secOverview, loadSecOverview, setTab }: SecurityPanelProps) {
  const s = useExecStyles();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  if (secLoading || !secOverview) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;
  const d = secOverview;
  const threatColors: any = { low: T.success, medium: T.warning, high: 'var(--app-warning)', critical: T.error };
  const threatIcons: any = { low: 'shield-checkmark', medium: 'shield', high: 'shield', critical: 'alert-circle' };
  const tc = threatColors[d.threat_level] || T.textMuted;

  return (
    <View data-testid="security-overview-panel" testID="security-overview-panel">
      {/* Threat Level */}
      <View style={[s.panel, { borderWidth: 1, borderColor: (globalThis as any).__alphaColor(tc, '30') }]} data-testid="threat-level-card" testID="threat-level-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(tc, '18'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={threatIcons[d.threat_level] || 'shield'} size={26} color={tc} />
            </View>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.sessionSecurity.threatLevel', 'THREAT LEVEL')}</Text>
              <Text style={{ color: tc, fontSize: 22, fontWeight: '800', textTransform: 'uppercase' }}>{d.threat_level}</Text>
            </View>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.sessionSecurity.threatScore', 'Threat Score')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 2 }}>
              <Text style={{ color: tc, fontSize: 28, fontWeight: '800' }}>{d.threat_score}</Text>
              <Text style={{ color: T.textMuted, fontSize: 12 }}>/100</Text>
            </View>
          </View>
        </View>
        <View style={{ height: 6, backgroundColor: T.bgSoft, borderRadius: 3, marginTop: 12, overflow: 'hidden' }}>
          <View style={{ width: `${d.threat_score}%`, height: '100%', backgroundColor: tc, borderRadius: 3 }} />
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: d.auto_response.scheduler_enabled ? T.success : T.textMuted }} />
            <Text style={{ color: T.textMuted, fontSize: 10 }}>
              Auto-Response: {d.auto_response.scheduler_enabled ? 'Active' : 'Manual'} | {d.auto_response.active_rules}/{d.auto_response.total_rules} rules
            </Text>
          </View>
          {d.auto_response.last_scan && (
            <Text style={{ color: T.textMuted, fontSize: 9 }}>Last scan: {new Date(d.auto_response.last_scan).toLocaleTimeString()}</Text>
          )}
        </View>
      </View>

      {/* Metric Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 0 }}>
        {[
          { label: 'Active Anomalies', value: d.anomalies.total, sub: `${d.anomalies.critical} critical, ${d.anomalies.warning} warning`, icon: 'warning', color: d.anomalies.critical > 0 ? T.error : T.warning, onTap: () => setTab('map') },
          { label: 'Blocked IPs', value: d.blocked_ips.total, sub: `${d.blocked_ips.auto} auto, ${d.blocked_ips.manual} manual`, icon: 'ban', color: T.error, onTap: () => setTab('blocklist') },
          { label: 'Actions Fired', value: d.auto_response.total_fired, sub: `${d.auto_response.active_rules} active rules`, icon: 'flash', color: T.purpleText, onTap: () => setTab('map') },
          { label: 'Sessions (1h)', value: d.sessions.last_hour, sub: `${d.sessions.total} total, ${d.sessions.unique_users_30m} users`, icon: 'key', color: T.primary, onTap: () => setTab('sessions') },
        ].map((card, i) => (
          <TouchableOpacity key={i} onPress={card.onTap} style={[s.panel, { flex: 1, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(card.color, '15') }]} accessibilityLabel="card.label">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(card.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={card.icon as any} size={12} color={card.color} />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{card.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{card.value}</Text>
            <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 2 }}>{card.sub}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Activity Timeline */}
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="time" size={16} color={T.primary} />
            <Text style={s.chartTitle}>{tx('admin.sessionSecurity.activityTimeline', 'Activity Timeline')}</Text>
          </View>
          <TouchableOpacity onPress={loadSecOverview} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} accessibilityLabel="Refresh">
            <Ionicons name="refresh" size={12} color={T.primary} />
            <Text style={{ color: T.primary, fontSize: 10, fontWeight: '600' }}>{tx('admin.sessionSecurity.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
        {d.timeline.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 16 }}>
            <Ionicons name="checkmark-circle" size={24} color={T.successText} />
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.sessionSecurity.states.allClear', 'All clear — no recent security events')}</Text>
          </View>
        ) : d.timeline.map((ev: any, i: number) => {
          const sevC: any = { critical: T.error, warning: T.warning, info: T.primary };
          const typeIcons: any = { auto_response: 'flash', block: 'ban', anomaly: 'warning' };
          const c = sevC[ev.severity] || T.textMuted;
          return (
            <View key={i} style={{
              flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8,
              borderBottomWidth: i < d.timeline.length - 1 ? 1 : 0, borderBottomColor: T.border,
            }}>
              <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(c, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={typeIcons[ev.type] || 'alert-circle'} size={14} color={c} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{ev.title}</Text>
                <Text style={{ color: T.textMuted, fontSize: 9 }}>{ev.detail}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(c, '15'), borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}>
                  <Text style={{ color: c, fontSize: 8, fontWeight: '800', textTransform: 'uppercase' }}>{ev.severity}</Text>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 8, marginTop: 2 }}>
                  {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                </Text>
              </View>
            </View>
          );
        })}
      </View>

      {/* Quick Actions */}
      <View style={s.panel}>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>{tx('admin.sessionSecurity.quickActions', 'QUICK ACTIONS')}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[
            { label: 'View Anomalies', icon: 'warning', color: T.warningText, tab: 'map' as Tab },
            { label: 'View Blocklist', icon: 'ban', color: T.error, tab: 'blocklist' as Tab },
            { label: 'View Threats', icon: 'shield', color: T.purpleText, tab: 'suspicious' as Tab },
            { label: 'View Sessions', icon: 'key', color: T.primary, tab: 'sessions' as Tab },
          ].map(a => (
            <TouchableOpacity key={a.label} accessibilityLabel="a.label" onPress={() => setTab(a.tab)}
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(a.color, '10'), borderRadius: 8, paddingVertical: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(a.color, '20') }}>
              <Ionicons name={a.icon as any} size={14} color={a.color} />
              <Text style={{ color: a.color, fontSize: 10, fontWeight: '700' }}>{a.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    </View>
  );
}
