import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';
import { RISK_COLORS, FLAG_ICONS, ConfirmAction, fmtDate } from './types';

interface SuspiciousPanelProps {
  suspicious: any;
  suspLoading: boolean;
  loadSuspicious: () => void;
  setSuspicious: (s: any) => void;
  expandedUser: string | null;
  setExpandedUser: (u: string | null) => void;
  setConfirmModal: (a: ConfirmAction) => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function SuspiciousPanel({
  suspicious, suspLoading, loadSuspicious, setSuspicious,
  expandedUser, setExpandedUser, setConfirmModal,
}: SuspiciousPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  if (suspLoading) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;
  if (!suspicious) return <Text style={{ color: T.textMuted, textAlign: 'center', padding: 20 }}>{tx('admin.suspiciousPanel.auto.text.001', 'No data')}</Text>;
  const { risk_summary: rs, flagged_users: fu, scanned_sessions, scanned_users } = suspicious;

  return (
    <View data-testid="suspicious-activity-panel" testID="suspicious-activity-panel">
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="shield" size={18} color={T.error} />
            <Text style={s.chartTitle}>{tx('admin.suspiciousPanel.auto.text.002', 'Threat Detection')}</Text>
          </View>
          <TouchableOpacity onPress={() => { setSuspicious(null); loadSuspicious(); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="suspicious-refresh-btn" testID="suspicious-refresh-btn">
            <Ionicons name="refresh" size={14} color={T.primary} />
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.suspiciousPanel.auto.text.003', 'Rescan')}</Text>
          </TouchableOpacity>
        </View>
        <View style={s.metricsRow}>
          {(['critical', 'high', 'medium', 'low'] as const).map((level) => {
            const rc = RISK_COLORS[level];
            return (
              <View key={level} style={[s.metricBox, { borderLeftWidth: 3, borderLeftColor: rc.text }]} data-testid={`risk-${level}-count`} testID={`risk-${level}-count`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Ionicons name={rc.icon as any} size={14} color={rc.text} />
                  <Text style={[s.metricLabel, { textTransform: 'capitalize' }]}>{level}</Text>
                </View>
                <Text style={[s.metricValue, { color: rc.text }]}>{rs[level] || 0}</Text>
              </View>
            );
          })}
          <View style={s.metricBox} data-testid="scanned-stat" testID="scanned-stat">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name="scan" size={14} color={T.textMuted} />
              <Text style={s.metricLabel}>{tx('admin.suspiciousPanel.auto.text.004', 'Scanned')}</Text>
            </View>
            <Text style={s.metricValue}>{scanned_sessions}</Text>
            <Text style={{ color: T.textMuted, fontSize: 9 }}>{scanned_users} users</Text>
          </View>
        </View>
      </View>
      <View style={s.panel}>
        <Text style={[s.chartTitle, { marginBottom: 12 }]}>Flagged Users ({fu?.length || 0})</Text>
        {(!fu || fu.length === 0) ? (
          <View style={{ alignItems: 'center', paddingVertical: 30 }}>
            <Ionicons name="checkmark-circle" size={40} color={T.successText} />
            <Text style={{ color: T.successText, fontSize: 14, fontWeight: '700', marginTop: 8 }}>{tx('admin.suspiciousPanel.auto.text.005', 'All Clear')}</Text>
          </View>
        ) : fu.map((user: any, i: number) => {
          const rc = RISK_COLORS[user.risk_level] || RISK_COLORS.low;
          const expanded = expandedUser === user.user_id;
          return (
            <View key={user.user_id} style={{ marginBottom: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(rc.text, '30'), borderRadius: 12, overflow: 'hidden', backgroundColor: rc.bg }} data-testid={`flagged-user-${i}`} testID={`flagged-user-${i}`}>
              <TouchableOpacity onPress={() => setExpandedUser(expanded ? null : user.user_id)}
                style={{ flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 }} data-testid={`flagged-user-toggle-${i}`} testID={`flagged-user-toggle-${i}`}
              >
                <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(rc.text, '20'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: rc.text, fontSize: 14, fontWeight: '900' }}>{user.risk_score}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{user.email}</Text>
                    {user.is_admin && <View style={{ backgroundColor: T.purpleSoft, borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}><Text style={{ color: T.purpleText, fontSize: 8, fontWeight: '700' }}>{tx('admin.suspiciousPanel.auto.text.006', 'ADMIN')}</Text></View>}
                  </View>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 3 }}>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{user.session_count} sessions</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{user.distinct_ips?.length || 0} IPs</Text>
                    <Text style={{ color: rc.text, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{user.risk_level}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
                  <TouchableOpacity onPress={() => setConfirmModal({ type: 'user', target: user.user_id, label: user.email })}
                    style={{ backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 }} data-testid={`flagged-revoke-all-${i}`} testID={`flagged-revoke-all-${i}`}
                  >
                    <Text style={{ color: T.error, fontSize: 9, fontWeight: '700' }}>{tx('admin.suspiciousPanel.auto.text.007', 'Revoke All')}</Text>
                  </TouchableOpacity>
                  <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
                </View>
              </TouchableOpacity>
              {expanded && (
                <View style={{ padding: 12, paddingTop: 0, gap: 8 }}>
                  <View style={{ gap: 4 }}>
                    <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 2 }}>{tx('admin.suspiciousPanel.auto.text.008', 'DETECTED FLAGS')}</Text>
                    {user.flags?.map((f: any, fi: number) => {
                      const frc = RISK_COLORS[f.severity] || RISK_COLORS.low;
                      return (
                        <View key={fi} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: T.card, borderRadius: 8, padding: 8 }} data-testid={`flag-${i}-${fi}`} testID={`flag-${i}-${fi}`}>
                          <View style={{ width: 26, height: 26, borderRadius: 7, backgroundColor: frc.bg, alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name={(FLAG_ICONS[f.type] || 'warning') as any} size={13} color={frc.text} />
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{f.detail}</Text>
                            <Text style={{ color: T.textMuted, fontSize: 9, textTransform: 'capitalize' }}>{f.type.replace(/_/g, ' ')} - {f.severity}</Text>
                          </View>
                        </View>
                      );
                    })}
                  </View>
                  {user.locations?.length > 0 && (
                    <View>
                      <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 4 }}>{tx('admin.suspiciousPanel.auto.text.009', 'GEOLOCATIONS')}</Text>
                      <View style={{ gap: 4 }}>
                        {user.locations.map((loc: any, li: number) => (
                          <View key={li} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: T.card, borderRadius: 6, padding: 6 }}>
                            <Ionicons name="location" size={12} color={T.cyan} />
                            <Text style={{ color: T.text, fontSize: 10, fontFamily: 'monospace' }}>{loc.ip}</Text>
                            <Text style={{ color: T.textSec, fontSize: 10 }}>{loc.city}, {loc.country_code}</Text>
                            <Text style={{ color: T.textMuted, fontSize: 9 }}>{loc.isp}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  )}
                  {user.distinct_ips?.length > 0 && !user.locations?.length && (
                    <View>
                      <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 4 }}>{tx('admin.suspiciousPanel.auto.text.010', 'IP ADDRESSES')}</Text>
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                        {user.distinct_ips.map((ip: string, ipi: number) => (
                          <View key={ipi} style={{ backgroundColor: T.card, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                            <Text style={{ color: T.textSec, fontSize: 10, fontFamily: 'monospace' }}>{ip}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  )}
                  {user.latest_session && <Text style={{ color: T.textMuted, fontSize: 9 }}>Last active: {fmtDate(user.latest_session)}</Text>}
                </View>
              )}
            </View>
          );
        })}
      </View>
    </View>
  );
}
