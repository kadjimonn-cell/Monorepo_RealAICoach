import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

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

export default function TrustedDevicesPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const AC = useAdminTheme();
  const C = {
    bg: AC.bg, surface: colors.card, surfaceHover: colors.border, border: AC.border,
    text: AC.text, muted: AC.textDim, primary: colors.primary, emerald: colors.success,
    amber: colors.warning, rose: colors.error, violet: colors.purple,
  };
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await api.get('/auth/devices');
      setDevices(res.data?.devices || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load devices');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleTrust = useCallback(async (deviceId: string, trusted: boolean) => {
    setBusyId(`trust-${deviceId}`);
    try {
      await api.post('/auth/devices/trust', { device_id: deviceId, trusted });
      setDevices(prev => prev.map(d => d.device_id === deviceId ? { ...d, trusted } : d));
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed'); }
    finally { setBusyId(''); }
  }, []);

  const revoke = useCallback(async (deviceId: string, name: string) => {
    const confirmed = typeof window !== 'undefined'
      ? window.confirm(`Revoke "${name}"? This will end all sessions from this device.`)
      : true;
    if (!confirmed) return;
    setBusyId(`revoke-${deviceId}`);
    try {
      await api.delete('/auth/devices/revoke', { data: { device_id: deviceId } });
      setDevices(prev => prev.filter(d => d.device_id !== deviceId));
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed'); }
    finally { setBusyId(''); }
  }, []);

  if (loading) return <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator color={C.primary} size="large" /></View>;

  const trusted = devices.filter(d => d.trusted);
  const untrusted = devices.filter(d => !d.trusted);

  return (
    <View data-testid="trusted-devices-panel" testID="trusted-devices-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${C.primary}18`, justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name="shield-checkmark-outline" size={20} color={C.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.trustedDevicesPanel.auto.text.001', 'Trusted Devices')}</Text>
          <Text style={{ color: C.muted, fontSize: 12 }}>{trusted.length} trusted, {untrusted.length} unrecognized</Text>
        </View>
        <TouchableOpacity onPress={load} style={{ padding: 8 }} data-testid="devices-refresh-btn" testID="devices-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.muted} />
        </TouchableOpacity>
      </View>

      {error ? <Text style={{ color: C.error, fontSize: 12, marginBottom: 12 }}>{error}</Text> : null}

      {/* Trusted devices section */}
      {trusted.length > 0 && (
        <View style={{ marginBottom: 20 }}>
          <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>{tx('admin.trustedDevicesPanel.auto.text.002', 'Trusted Devices')}</Text>
          <View style={{ gap: 6 }}>
            {trusted.map(d => (
              <DeviceRow key={d.device_id} device={d} onTrust={toggleTrust} onRevoke={revoke} busyId={busyId} />
            ))}
          </View>
        </View>
      )}

      {/* Untrusted devices section */}
      {untrusted.length > 0 && (
        <View>
          <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>{tx('admin.trustedDevicesPanel.auto.text.003', 'Unrecognized Devices')}</Text>
          <View style={{ gap: 6 }}>
            {untrusted.map(d => (
              <DeviceRow key={d.device_id} device={d} onTrust={toggleTrust} onRevoke={revoke} busyId={busyId} />
            ))}
          </View>
        </View>
      )}

      {devices.length === 0 && (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="shield-outline" size={36} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('admin.trustedDevicesPanel.auto.text.004', 'No devices found')}</Text>
        </View>
      )}
    </View>
  );
}

function DeviceRow({ device: d, onTrust, onRevoke, busyId }: any) {
  const C = useAdminTheme();
  const isBusyTrust = busyId === `trust-${d.device_id}`;
  const isBusyRevoke = busyId === `revoke-${d.device_id}`;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: d.trusted ? `${C.success}30` : C.border, gap: 10 }} data-testid={`device-row-${d.device_id}`} testID={`device-row-${d.device_id}`}>
      <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: d.trusted ? `${C.success}18` : C.surfaceHover, justifyContent: 'center', alignItems: 'center' }}>
        <Ionicons name={deviceIcon(d.device_type) as any} size={18} color={d.trusted ? C.success : C.muted} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{d.device_name}</Text>
        <View style={{ flexDirection: 'row', gap: 10, marginTop: 2 }}>
          <Text style={{ color: C.muted, fontSize: 10 }}>{d.ip_address}</Text>
          <Text style={{ color: C.muted, fontSize: 10 }}>{d.location}</Text>
          <Text style={{ color: C.muted, fontSize: 10 }}>Last: {timeAgo(d.last_seen)}</Text>
          <Text style={{ color: C.muted, fontSize: 10 }}>{d.login_count} logins</Text>
        </View>
      </View>
      <View style={{ flexDirection: 'row', gap: 4 }}>
        <TouchableOpacity
          onPress={() => onTrust(d.device_id, !d.trusted)}
          disabled={isBusyTrust}
          style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: d.trusted ? `${C.warning}18` : `${C.success}18`, borderWidth: 1, borderColor: d.trusted ? `${C.warning}40` : `${C.success}40` }}
          data-testid={`device-trust-${d.device_id}`} testID={`device-trust-${d.device_id}`}
        >
          {isBusyTrust ? <ActivityIndicator size="small" color={C.primary} /> :
            <Text style={{ color: d.trusted ? C.warning : C.success, fontSize: 10, fontWeight: '700' }}>{d.trusted ? 'Untrust' : 'Trust'}</Text>}
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => onRevoke(d.device_id, d.device_name)}
          disabled={isBusyRevoke}
          style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: `${C.error}18`, borderWidth: 1, borderColor: `${C.error}40` }}
          data-testid={`device-revoke-${d.device_id}`} testID={`device-revoke-${d.device_id}`}
        >
          {isBusyRevoke ? <ActivityIndicator size="small" color={C.error} /> :
            <Text style={{ color: C.error, fontSize: 10, fontWeight: '700' }}>{tx('admin.trustedDevicesPanel.auto.text.005', 'Revoke')}</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}
