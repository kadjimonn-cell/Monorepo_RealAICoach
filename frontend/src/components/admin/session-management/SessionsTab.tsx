import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';
import { ConfirmAction, parseUA, fmtDate } from './types';

interface SessionsTabProps {
  stats: any;
  sessions: any[];
  loading: boolean;
  search: string;
  setSearch: (s: string) => void;
  page: number;
  setPage: (fn: number | ((p: number) => number)) => void;
  pages: number;
  total: number;
  revoking: string;
  setConfirmModal: (a: ConfirmAction) => void;
  loadSessions: () => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function SessionsTab({
  stats, sessions, loading, search, setSearch, page, setPage,
  pages, total, revoking, setConfirmModal, loadSessions,
}: SessionsTabProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const isCompact = width < 900;
  return (
    <>
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="key" size={18} color={T.primary} />
          <Text style={s.chartTitle}>{tx('admin.sessionsTab.auto.text.001', 'Session Overview')}</Text>
        </View>
        <View style={[s.metricsRow, { flexWrap: 'wrap' }]}>
          {[
            { label: 'Active Sessions', value: stats?.total_sessions ?? '...', color: T.primary, icon: 'key' },
            { label: 'Unique Users', value: stats?.unique_users ?? '...', color: T.successText, icon: 'people' },
            { label: 'Avg/User', value: stats ? (stats.total_sessions / Math.max(1, stats.unique_users)).toFixed(1) : '...', color: T.warningText, icon: 'analytics' },
          ].map((m, i) => (
            <View key={i} style={s.metricBox} data-testid={`session-stat-${i}`} testID={`session-stat-${i}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name={m.icon as any} size={14} color={m.color} />
                <Text style={s.metricLabel}>{m.label}</Text>
              </View>
              <Text style={s.metricValue}>{m.value}</Text>
            </View>
          ))}
        </View>
      </View>
      {stats?.top_users?.length > 0 && (
        <View style={s.panel}>
          <Text style={[s.chartTitle, { marginBottom: 12 }]}>{tx('admin.sessionsTab.auto.text.002', 'Top Session Users')}</Text>
          <View style={{ gap: 6 }}>
            {stats.top_users.map((u: any, i: number) => {
              const maxC = stats.top_users[0]?.session_count || 1;
              const pct = Math.round((u.session_count / maxC) * 100);
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`top-session-user-${i}`} testID={`top-session-user-${i}`}>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', width: 120 }} numberOfLines={1}>{u.email}</Text>
                  <View style={{ flex: 1, height: 22, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                    <View style={{ width: `${pct}%`, height: '100%', backgroundColor: (globalThis as any).__alphaColor(T.primary, '50'), borderRadius: 4, justifyContent: 'center', paddingLeft: 6 }}>
                      <Text style={{ color: T.text, fontSize: 9, fontWeight: '700' }}>{u.session_count}</Text>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => setConfirmModal({ type: 'user', target: u.user_id, label: u.email })}
                    style={{ backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }} data-testid={`revoke-all-${i}`} testID={`revoke-all-${i}`}>
                    <Text style={{ color: T.error, fontSize: 9, fontWeight: '700' }}>{tx('admin.sessionsTab.auto.text.003', 'Revoke All')}</Text>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        </View>
      )}
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <Text style={s.chartTitle}>{tx('admin.sessionsTab.header.activeSessions', 'Active Sessions')} ({total})</Text>
          <TouchableOpacity onPress={loadSessions} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="session-refresh-btn" testID="session-refresh-btn">
            <Ionicons name="refresh" size={14} color={T.primary} />
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.sessionsTab.auto.text.004', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
        <View style={{ marginBottom: 12 }}>
          <TextInput value={search} onChangeText={t => { setSearch(t); setPage(1); }} placeholder={tx('admin.sessionsTab.auto.placeholder.001', 'Search by email, name, or user ID...')}
            placeholderTextColor={T.textMuted}
            style={{ backgroundColor: T.bgSoft, color: T.text, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, fontSize: 12, borderWidth: 1, borderColor: T.border }}
            data-testid="session-search-input" testID="session-search-input"
          />
        </View>
        {loading ? <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} /> : (
          <>
            {!isCompact && (
              <View style={{ flexDirection: 'row', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
                <Text style={[s.th, { flex: 1.5 }]}>{tx('admin.sessionsTab.auto.text.005', 'User')}</Text>
                <Text style={[s.th, { flex: 1 }]}>{tx('admin.sessionsTab.auto.text.006', 'IP')}</Text>
                <Text style={[s.th, { flex: 1 }]}>{tx('admin.sessionsTab.auto.text.007', 'Device')}</Text>
                <Text style={[s.th, { flex: 1 }]}>{tx('admin.sessionsTab.auto.text.008', 'Created')}</Text>
                <Text style={[s.th, { flex: 0.5 }]}>{tx('admin.sessionsTab.auto.text.009', 'Plan')}</Text>
                <Text style={[s.th, { flex: 0.6 }]}>{tx('admin.sessionsTab.auto.text.010', 'Actions')}</Text>
              </View>
            )}
            {sessions.length === 0 ? <Text style={{ color: T.textMuted, textAlign: 'center', paddingVertical: 20, fontSize: 12 }}>{tx('admin.sessionsTab.auto.text.011', 'No sessions found')}</Text>
              : sessions.map((sess: any, i: number) => (
                isCompact ? (
                  <View key={i} style={{ padding: 10, borderWidth: 1, borderColor: T.border, borderRadius: 10, marginBottom: 8, backgroundColor: T.bgSoft }} data-testid={`session-row-${i}`} testID={`session-row-${i}`}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{sess.name}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 6 }} numberOfLines={1}>{sess.email}</Text>
                    <Text style={{ color: T.textSec, fontSize: 10 }}>{tx('admin.sessionsTab.fields.ip', 'IP')}: {sess.ip_address}</Text>
                    <Text style={{ color: T.textSec, fontSize: 10 }} numberOfLines={1}>{tx('admin.sessionsTab.fields.device', 'Device')}: {parseUA(sess.user_agent)}</Text>
                    <Text style={{ color: T.textSec, fontSize: 10 }}>{tx('admin.sessionsTab.fields.created', 'Created')}: {fmtDate(sess.created_at)}</Text>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                      <View style={[s.planBadge, { backgroundColor: sess.plan === 'premium' ? T.purpleSoft : sess.plan === 'basic' ? T.primarySoft : T.bgSoft }]}> 
                        <Text style={[s.planText, { color: sess.plan === 'premium' ? T.purple : sess.plan === 'basic' ? T.primary : T.textMuted }]}>{sess.plan || 'free'}</Text>
                      </View>
                      <TouchableOpacity onPress={() => setConfirmModal({ type: 'single', target: sess.session_token_full, label: sess.email })}
                        disabled={revoking === sess.session_token_full}
                        style={{ backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 }}
                        data-testid={`revoke-session-${i}`} testID={`revoke-session-${i}`}>
                        <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{revoking === sess.session_token_full ? '...' : tx('admin.sessionsTab.actions.revoke', 'Revoke')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border, backgroundColor: i % 2 === 0 ? T.bgSoft : 'transparent' }} data-testid={`session-row-${i}`} testID={`session-row-${i}`}>
                    <View style={{ flex: 1.5 }}>
                      <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{sess.name}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }} numberOfLines={1}>{sess.email}</Text>
                    </View>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 10 }}>{sess.ip_address}</Text>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 10 }} numberOfLines={1}>{parseUA(sess.user_agent)}</Text>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 10 }}>{fmtDate(sess.created_at)}</Text>
                    <View style={{ flex: 0.5 }}>
                      <View style={[s.planBadge, { backgroundColor: sess.plan === 'premium' ? T.purpleSoft : sess.plan === 'basic' ? T.primarySoft : T.bgSoft }]}> 
                        <Text style={[s.planText, { color: sess.plan === 'premium' ? T.purple : sess.plan === 'basic' ? T.primary : T.textMuted }]}>{sess.plan || 'free'}</Text>
                      </View>
                    </View>
                    <View style={{ flex: 0.6 }}>
                      <TouchableOpacity onPress={() => setConfirmModal({ type: 'single', target: sess.session_token_full, label: sess.email })}
                        disabled={revoking === sess.session_token_full}
                        style={{ backgroundColor: T.errorSoft, paddingHorizontal: 6, paddingVertical: 4, borderRadius: 4 }}
                        data-testid={`revoke-session-${i}`} testID={`revoke-session-${i}`}
                      >
                        <Text style={{ color: T.error, fontSize: 9, fontWeight: '700' }}>{revoking === sess.session_token_full ? '...' : tx('admin.sessionsTab.actions.revoke', 'Revoke')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )
              ))}
            {pages > 1 && (
              <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 12 }}>
                <TouchableOpacity onPress={() => setPage((p: number) => Math.max(1, p - 1))} disabled={page <= 1}
                  style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: page <= 1 ? T.bgSoft : T.primarySoft }} data-testid="session-prev-page" testID="session-prev-page">
                  <Text style={{ color: page <= 1 ? T.textMuted : T.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.sessionsTab.auto.text.012', 'Prev')}</Text>
                </TouchableOpacity>
                <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.sessionsTab.auto.text.014', 'Page {page} of {pages}').replace('{page}', String(page)).replace('{pages}', String(pages))}</Text>
                <TouchableOpacity onPress={() => setPage((p: number) => Math.min(pages, p + 1))} disabled={page >= pages}
                  style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: page >= pages ? T.bgSoft : T.primarySoft }} data-testid="session-next-page" testID="session-next-page">
                  <Text style={{ color: page >= pages ? T.textMuted : T.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.sessionsTab.auto.text.013', 'Next')}</Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}
      </View>
    </>
  );
}
