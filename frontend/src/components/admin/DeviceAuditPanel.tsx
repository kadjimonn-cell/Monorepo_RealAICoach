import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
let C = {
  bg: 'var(--app-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any, muted: 'var(--app-text-muted)' as any, primary: 'var(--app-primary)' as any, emerald: 'var(--app-success)',
  amber: 'var(--app-warning)', rose: 'var(--app-error)', violet: 'var(--app-primary)',
};

const tx = (_key: string, fallback: string) => fallback;

const deviceIcon = (type: string): string => {
  if (type === 'mobile') return 'phone-portrait-outline';
  if (type === 'tablet') return 'tablet-portrait-outline';
  return 'desktop-outline';
};

function timeAgo(dateStr: string): string {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function DeviceAuditPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
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
  const [search, setSearch] = useState('');
  const [trustedFilter, setTrustedFilter] = useState('');
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const params = new URLSearchParams({ page: String(page), limit: '20' });
      if (search) params.set('search', search);
      if (trustedFilter) params.set('trusted', trustedFilter);
      const res = await api.get(`/auth/admin/devices/audit?${params}`);
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load');
    } finally { setLoading(false); }
  }, [page, search, trustedFilter]);

  useEffect(() => { load(); }, [load]);

  const forceRevoke = useCallback(async (userId: string, deviceId: string, name: string) => {
    const confirmed = typeof window !== 'undefined'
      ? window.confirm(`Force-revoke "${name}"? This will terminate all sessions from this device.`)
      : true;
    if (!confirmed) return;
    setBusyId(deviceId);
    try {
      await api.post('/auth/admin/devices/force-revoke', { user_id: userId, device_id: deviceId });
      load();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed'); }
    finally { setBusyId(''); }
  }, [load]);

  const summary = data?.summary || {};
  const devices = data?.devices || [];
  const pages = data?.pages || 1;

  return (
    <View style={{ flex: 1 }} data-testid="device-audit-panel" testID="device-audit-panel">
      {/* Summary KPIs */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Devices', value: summary.total_devices || 0, color: C.primary },
          { label: 'Trusted', value: summary.trusted_devices || 0, color: C.successText },
          { label: 'Untrusted', value: summary.untrusted_devices || 0, color: summary.untrusted_devices > 10 ? C.warning : C.muted },
          { label: 'Unique Users', value: summary.unique_users || 0, color: C.violet },
        ].map((kpi, i) => (
          <View key={i} style={{ flex: 1, minWidth: 130, backgroundColor: C.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid={`audit-kpi-${i}`} testID={`audit-kpi-${i}`}>
            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{kpi.label}</Text>
            <Text style={{ color: kpi.color, fontSize: 22, fontWeight: '800' }}>{kpi.value}</Text>
          </View>
        ))}
      </View>

      {/* Search + Filters */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <View style={{ flex: 1, minWidth: 200, flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, paddingVertical: 8 }}>
          <Ionicons name="search" size={14} color={C.muted} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={load}
            placeholder={tx('admin.deviceAuditPanel.auto.placeholder.001', 'Search by IP, device, user...')}
            placeholderTextColor={C.muted}
            style={{ flex: 1, marginLeft: 8, color: C.text, fontSize: 13, outlineStyle: 'none' } as any}
            data-testid="audit-search-input" testID="audit-search-input"
          />
        </View>
        {['', 'true', 'false'].map(f => (
          <TouchableOpacity key={f} onPress={() => { setTrustedFilter(f); setPage(1); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: trustedFilter === f ? C.primary : C.surfaceHover, borderWidth: 1, borderColor: trustedFilter === f ? C.primary : C.border }} data-testid={`audit-filter-${f || 'all'}`} testID={`audit-filter-${f || 'all'}`}>
            <Text style={{ color: trustedFilter === f ? 'var(--app-primary-text)' : C.text, fontSize: 11, fontWeight: '600' }}>{f === '' ? 'All' : f === 'true' ? 'Trusted' : 'Untrusted'}</Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity onPress={load} style={{ padding: 8 }} data-testid="audit-refresh-btn" testID="audit-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.muted} />
        </TouchableOpacity>
      </View>

      {error ? <Text style={{ color: C.error, fontSize: 12, marginBottom: 8 }}>{error}</Text> : null}
      {loading ? <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator color={C.primary} size="large" /></View> : null}

      {/* Device Table */}
      {!loading && (
        <View style={{ gap: 6 }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 6, gap: 6 }}>
            <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.deviceAuditPanel.auto.text.001', 'User')}</Text>
            <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.deviceAuditPanel.auto.text.002', 'Device')}</Text>
            <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.deviceAuditPanel.auto.text.003', 'IP')}</Text>
            <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.deviceAuditPanel.auto.text.004', 'Location')}</Text>
            <Text style={{ width: 60, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.deviceAuditPanel.auto.text.005', 'Status')}</Text>
            <Text style={{ width: 60, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.deviceAuditPanel.auto.text.006', 'Last Seen')}</Text>
            <Text style={{ width: 70, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.deviceAuditPanel.auto.text.007', 'Action')}</Text>
          </View>

          {devices.map((d: any, i: number) => (
            <View key={`${d.user_id}-${d.device_id}`} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8, backgroundColor: i % 2 === 0 ? C.surface : 'transparent', gap: 6 }} data-testid={`audit-row-${i}`} testID={`audit-row-${i}`}>
              <View style={{ flex: 2, minWidth: 0 }}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{d.user_email || d.user_id}</Text>
                {d.user_name ? <Text style={{ color: C.muted, fontSize: 9 }} numberOfLines={1}>{d.user_name}</Text> : null}
              </View>
              <View style={{ flex: 2, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name={deviceIcon(d.device_type) as any} size={14} color={d.trusted ? C.success : C.muted} />
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '600', flex: 1 }} numberOfLines={1}>{d.device_name}</Text>
              </View>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10 }} numberOfLines={1}>{d.ip_address}</Text>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10 }} numberOfLines={1}>{d.location}</Text>
              <View style={{ width: 60, alignItems: 'center' }}>
                <View style={{ backgroundColor: d.trusted ? `${C.success}20` : `${C.warning}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                  <Text style={{ color: d.trusted ? C.success : C.warning, fontSize: 9, fontWeight: '700' }}>{d.trusted ? 'Trusted' : 'Untrusted'}</Text>
                </View>
              </View>
              <Text style={{ width: 60, color: C.muted, fontSize: 10, textAlign: 'center' }}>{timeAgo(d.last_seen)}</Text>
              <View style={{ width: 70, alignItems: 'center' }}>
                <TouchableOpacity
                  onPress={() => forceRevoke(d.user_id, d.device_id, d.device_name)}
                  disabled={busyId === d.device_id}
                  style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: `${C.error}18`, borderWidth: 1, borderColor: `${C.error}40` }}
                  data-testid={`audit-revoke-${i}`} testID={`audit-revoke-${i}`}
                >
                  {busyId === d.device_id ? <ActivityIndicator size="small" color={C.error} /> :
                    <Text style={{ color: C.error, fontSize: 9, fontWeight: '700' }}>{tx('admin.deviceAuditPanel.auto.text.008', 'Force Revoke')}</Text>}
                </TouchableOpacity>
              </View>
            </View>
          ))}

          {devices.length === 0 && !loading && (
            <View style={{ padding: 30, alignItems: 'center' }}>
              <Ionicons name="hardware-chip-outline" size={36} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('admin.deviceAuditPanel.auto.text.009', 'No devices found')}</Text>
            </View>
          )}
        </View>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 16 }}>
          <TouchableOpacity onPress={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} style={{ padding: 8, opacity: page <= 1 ? 0.3 : 1 }} data-testid="audit-prev-page" testID="audit-prev-page">
            <Ionicons name="chevron-back" size={16} color={C.text} />
          </TouchableOpacity>
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>Page {page} of {pages}</Text>
          <TouchableOpacity onPress={() => setPage(Math.min(pages, page + 1))} disabled={page >= pages} style={{ padding: 8, opacity: page >= pages ? 0.3 : 1 }} data-testid="audit-next-page" testID="audit-next-page">
            <Ionicons name="chevron-forward" size={16} color={C.text} />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}
