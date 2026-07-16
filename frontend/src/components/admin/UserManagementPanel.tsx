import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const _C = getC(true);
const ROLES = ['user', 'admin', 'moderator', 'employer', 'support'];

const tx = (_key: string, fallback: string) => fallback;

export default function UserManagementPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const { data: usersData, loading, refetch: loadUsers } = useLiveQuery(`/admin/manage/users?page=${page}&limit=15&search=${search}&status=${filter}`, { entity: 'users', pollInterval: 30000 });
  const users = usersData?.users || [];
  const total = usersData?.total || 0;
  const [selected, setSelected] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [actionLoading, setActionLoading] = useState('');

  const loadLogs = async (uid: string) => {
    try {
      const res = await api.get(`/admin/manage/users/${uid}/login-logs`);
      setLogs(res.data.events || []);
    } catch { setLogs([]); }
  };

  const selectUser = (u: any) => {
    setSelected(u);
    loadLogs(u.user_id);
  };

  const doAction = async (action: string, body?: any) => {
    if (!selected) return;
    setActionLoading(action);
    try {
      if (action === 'freeze') {
        await api.post(`/admin/manage/users/${selected.user_id}/freeze`, { reason: 'Frozen by admin' });
      } else if (action === 'unfreeze') {
        await api.post(`/admin/manage/users/${selected.user_id}/unfreeze`, {});
      } else if (action === 'reset') {
        const res = await api.post(`/admin/manage/users/${selected.user_id}/reset-password`, {});
        Alert.alert(
          tx('admin.userManagementPanel.auto.alert.passwordReset', 'Password Reset'),
          tx('admin.userManagementPanel.auto.alert.tempPassword', 'Temp password: {value}').replace('{value}', String(res.data.temp_password || ''))
        );
      } else if (action === 'role') {
        await api.post(`/admin/manage/users/${selected.user_id}/role`, body);
      }
      await loadUsers();
      if (selected) loadLogs(selected.user_id);
    } catch (e: any) {
      Alert.alert(
        tx('admin.userManagementPanel.auto.alert.error', 'Error'),
        e?.response?.data?.detail || tx('admin.userManagementPanel.auto.alert.actionFailed', 'Action failed')
      );
    }
    setActionLoading('');
  };

  return (
    <View data-testid="user-management-panel" testID="user-management-panel">
      {/* Search + Filter */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
        <TextInput
          value={search}
          onChangeText={(t) => { setSearch(t); setPage(1); }}
          placeholder={tx('admin.userManagementPanel.auto.placeholder.001', 'Search users by name, email, or ID...')}
          placeholderTextColor={C.muted}
          style={{ flex: 1, backgroundColor: C.card, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.border }}
          data-testid="user-search-input" testID="user-search-input"
        />
        {['all', 'active', 'frozen'].map(f => (
          <TouchableOpacity key={f} onPress={() => { setFilter(f); setPage(1); }} style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: filter === f ? (globalThis as any).__alphaColor(C.blue, '20') : C.card, borderWidth: 1, borderColor: filter === f ? (globalThis as any).__alphaColor(C.blue, '40') : C.border }} data-testid={`user-filter-${f}`} testID={`user-filter-${f}`}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: filter === f ? C.blue : C.sec }}>{f.charAt(0).toUpperCase() + f.slice(1)}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        {/* User List */}
        <View style={{ width: isWide ? 360 : '100%' }}>
          {loading ? <ActivityIndicator color={C.blue} style={{ padding: 20 }} /> : users.map(u => (
            <TouchableOpacity key={u.user_id} onPress={() => selectUser(u)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 10, marginBottom: 4, backgroundColor: selected?.user_id === u.user_id ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent', borderWidth: 1, borderColor: selected?.user_id === u.user_id ? (globalThis as any).__alphaColor(C.blue, '30') : 'transparent' }} data-testid={`user-row-${u.user_id}`} testID={`user-row-${u.user_id}`}>
              <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: u.access_locked ? (globalThis as any).__alphaColor(C.red, '20') : C.green + '20', alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={u.access_locked ? 'lock-closed' : 'person'} size={16} color={u.access_locked ? C.red : C.green} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }} numberOfLines={1}>{u.name || 'No name'}</Text>
                <Text style={{ fontSize: 11, color: C.muted }} numberOfLines={1}>{u.email}</Text>
              </View>
              <View style={{ backgroundColor: u.is_admin ? (globalThis as any).__alphaColor(C.purple, '20') : u.role === 'employer' ? C.yellow + '20' : C.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: u.is_admin ? C.purple : u.role === 'employer' ? C.yellow : C.sec }}>{u.role || 'user'}</Text>
              </View>
            </TouchableOpacity>
          ))}
          {/* Pagination */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, padding: 8 }}>
            <TouchableOpacity disabled={page <= 1} accessibilityLabel={tx('admin.userManagementPanel.auto.accessibility.001', 'Previous')} onPress={() => setPage(p => p - 1)} style={{ opacity: page <= 1 ? 0.3 : 1 }}>
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '600' }}>{tx('admin.userManagementPanel.auto.text.001', 'Previous')}</Text>
            </TouchableOpacity>
            <Text style={{ fontSize: 11, color: C.muted }}>Page {page} of {Math.max(1, Math.ceil(total / 15))} ({total} users)</Text>
            <TouchableOpacity disabled={page * 15 >= total} accessibilityLabel={tx('admin.userManagementPanel.auto.accessibility.002', 'Next')} onPress={() => setPage(p => p + 1)} style={{ opacity: page * 15 >= total ? 0.3 : 1 }}>
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '600' }}>{tx('admin.userManagementPanel.auto.text.002', 'Next')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* User Detail */}
        <View style={{ flex: 1 }}>
          {!selected ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: C.border, minHeight: 200 }}>
              <Ionicons name="people-outline" size={40} color={C.border} />
              <Text style={{ color: C.muted, marginTop: 10 }}>{tx('admin.userManagementPanel.auto.text.003', 'Select a user to manage')}</Text>
            </View>
          ) : (
            <View>
              {/* Profile Card */}
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="user-detail-card" testID="user-detail-card">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: selected.access_locked ? (globalThis as any).__alphaColor(C.red, '20') : C.blue + '20', alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ fontSize: 18, fontWeight: '700', color: selected.access_locked ? C.red : C.blue }}>{(selected.name || '?')[0].toUpperCase()}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 16, fontWeight: '700', color: C.text }}>{selected.name || 'No name'}</Text>
                    <Text style={{ fontSize: 12, color: C.muted }}>{selected.email}</Text>
                    <Text style={{ fontSize: 11, color: C.sec }}>ID: {selected.user_id} | Plan: {selected.subscription_plan || 'free'}</Text>
                  </View>
                  {selected.access_locked && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '20'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 }}>
                      <Text style={{ fontSize: 11, fontWeight: '700', color: C.red }}>{tx('admin.userManagementPanel.auto.text.004', 'FROZEN')}</Text>
                    </View>
                  )}
                </View>

                {/* Actions */}
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {selected.access_locked ? (
                    <TouchableOpacity onPress={() => doAction('unfreeze')} disabled={actionLoading === 'unfreeze'} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '30') }} data-testid="user-unfreeze-btn" testID="user-unfreeze-btn">
                      {actionLoading === 'unfreeze' ? <ActivityIndicator size="small" color={C.green} /> : <><Ionicons name="lock-open" size={14} color={C.green} /><Text style={{ fontSize: 12, fontWeight: '600', color: C.green }}>{tx('admin.userManagementPanel.auto.text.005', 'Unfreeze')}</Text></>}
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity onPress={() => doAction('freeze')} disabled={actionLoading === 'freeze'} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30') }} data-testid="user-freeze-btn" testID="user-freeze-btn">
                      {actionLoading === 'freeze' ? <ActivityIndicator size="small" color={C.red} /> : <><Ionicons name="snow" size={14} color={C.red} /><Text style={{ fontSize: 12, fontWeight: '600', color: C.red }}>{tx('admin.userManagementPanel.auto.text.006', 'Freeze')}</Text></>}
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity onPress={() => doAction('reset')} disabled={actionLoading === 'reset'} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.yellow, '15'), borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.yellow, '30') }} data-testid="user-reset-pwd-btn" testID="user-reset-pwd-btn">
                    {actionLoading === 'reset' ? <ActivityIndicator size="small" color={C.yellow} /> : <><Ionicons name="key" size={14} color={C.yellow} /><Text style={{ fontSize: 12, fontWeight: '600', color: C.yellow }}>{tx('admin.userManagementPanel.auto.text.007', 'Reset Password')}</Text></>}
                  </TouchableOpacity>
                </View>

                {/* Role */}
                <View style={{ marginTop: 16 }}>
                  <Text style={{ fontSize: 12, fontWeight: '600', color: C.sec, marginBottom: 8 }}>{tx('admin.userManagementPanel.auto.text.008', 'Role Management')}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {ROLES.map(r => (
                      <TouchableOpacity key={r} onPress={() => doAction('role', { role: r, is_admin: r === 'admin', full_access: r === 'admin' })} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: selected.role === r ? (globalThis as any).__alphaColor(C.blue, '20') : C.bg, borderWidth: 1, borderColor: selected.role === r ? (globalThis as any).__alphaColor(C.blue, '40') : C.border }} data-testid={`user-role-${r}`} testID={`user-role-${r}`}>
                        <Text style={{ fontSize: 11, fontWeight: '600', color: selected.role === r ? C.blue : C.sec }}>{r}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>

              {/* Login Logs */}
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="user-login-logs" testID="user-login-logs">
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.userManagementPanel.auto.text.009', 'Login History')}</Text>
                {logs.length === 0 ? <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.userManagementPanel.auto.text.010', 'No recent activity')}</Text> : logs.slice(0, 15).map((e, i) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: C.border }}>
                    <Ionicons name={e.event_type?.includes('success') ? 'checkmark-circle' : 'close-circle'} size={14} color={e.event_type?.includes('success') ? C.green : C.red} />
                    <Text style={{ flex: 1, fontSize: 11, color: C.text }}>{e.event_type?.replace(/_/g, ' ')}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }}>{e.timestamp ? new Date(e.timestamp).toLocaleString() : ''}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}
