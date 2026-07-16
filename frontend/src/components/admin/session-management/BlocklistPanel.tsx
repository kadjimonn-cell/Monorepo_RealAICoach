import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';

interface BlocklistPanelProps {
  blLoading: boolean;
  blocklist: any;
  blNewIp: string;
  setBlNewIp: (s: string) => void;
  blNewReason: string;
  setBlNewReason: (s: string) => void;
  blockIp: () => void;
  unblockIp: (ip: string) => void;
  whitelistIp: (ip: string) => void;
  removeWhitelist: (ip: string) => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function BlocklistPanel({
  blLoading, blocklist, blNewIp, setBlNewIp, blNewReason, setBlNewReason,
  blockIp, unblockIp, whitelistIp, removeWhitelist,
}: BlocklistPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  if (blLoading) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;
  const st = blocklist.stats || {};

  return (
    <View>
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="ban" size={18} color={T.error} />
          <Text style={s.chartTitle}>{tx('admin.blocklistPanel.auto.text.001', 'IP Blocklist')}</Text>
        </View>
        <View style={s.metricsRow}>
          {[
            { label: 'Total Blocked', value: st.total_blocked, icon: 'ban', color: T.error },
            { label: 'Auto-Blocked', value: st.auto_blocked, icon: 'flash', color: T.warningText },
            { label: 'Manual', value: st.manual_blocked, icon: 'hand-left', color: T.primary },
            { label: 'Whitelisted', value: st.whitelisted, icon: 'checkmark-circle', color: T.successText },
          ].map(m => (
            <View key={m.label} style={s.metricBox}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name={m.icon as any} size={14} color={m.color} />
                <Text style={s.metricLabel}>{m.label}</Text>
              </View>
              <Text style={s.metricValue}>{m.value || 0}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={s.panel}>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>{tx('admin.blocklistPanel.auto.text.002', 'BLOCK AN IP')}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={blNewIp} onChangeText={setBlNewIp} placeholder={tx('admin.blocklistPanel.auto.placeholder.001', 'IP address (e.g. 203.0.113.50)')} placeholderTextColor={T.textMuted}
            style={{ flex: 2, color: T.text, backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: T.border }} />
          <TextInput value={blNewReason} onChangeText={setBlNewReason} placeholder={tx('admin.blocklistPanel.auto.placeholder.002', 'Reason (optional)')} placeholderTextColor={T.textMuted}
            style={{ flex: 1.5, color: T.text, backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: T.border }} />
          <TouchableOpacity onPress={blockIp} disabled={!blNewIp.trim()} accessibilityLabel={tx('admin.blocklistPanel.auto.accessibility.001', 'Block')}
            style={{ backgroundColor: T.error, borderRadius: 8, paddingHorizontal: 16, justifyContent: 'center', opacity: blNewIp.trim() ? 1 : 0.4 }}>
            <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.blocklistPanel.auto.text.003', 'Block')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={s.panel}>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>BLOCKED IPs ({blocklist.blocked?.length || 0})</Text>
        {(!blocklist.blocked || blocklist.blocked.length === 0) ? (
          <View style={{ alignItems: 'center', paddingVertical: 16 }}>
            <Ionicons name="shield-checkmark" size={24} color={T.successText} />
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.blocklistPanel.auto.text.004', 'No blocked IPs')}</Text>
          </View>
        ) : blocklist.blocked.map((b: any, i: number) => (
          <View key={b.block_id || i} style={{
            flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 8,
            borderRadius: 8, marginBottom: 4, backgroundColor: T.bgSoft,
            borderLeftWidth: 3, borderLeftColor: b.reason === 'auto-response' ? T.warning : T.error,
          }}>
            <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(T.error, '18'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="ban" size={14} color={T.error} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{b.ip}</Text>
              <Text style={{ color: T.textMuted, fontSize: 9 }}>
                {b.city || 'Private'}{b.country_code ? `, ${b.country_code}` : ''} | {b.isp || 'Unknown ISP'} | {b.reason}
              </Text>
            </View>
            <Text style={{ color: T.textMuted, fontSize: 9 }}>{new Date(b.blocked_at).toLocaleDateString()}</Text>
            <TouchableOpacity accessibilityLabel={tx('admin.blocklistPanel.auto.accessibility.002', 'Whitelist')} onPress={() => whitelistIp(b.ip)}
              style={{ backgroundColor: (globalThis as any).__alphaColor(T.success, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
              <Text style={{ color: T.successText, fontSize: 9, fontWeight: '700' }}>{tx('admin.blocklistPanel.auto.text.005', 'Whitelist')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel={tx('admin.blocklistPanel.auto.accessibility.003', 'Unblock')} onPress={() => unblockIp(b.ip)}
              style={{ backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
              <Text style={{ color: T.primary, fontSize: 9, fontWeight: '700' }}>{tx('admin.blocklistPanel.auto.text.006', 'Unblock')}</Text>
            </TouchableOpacity>
          </View>
        ))}
      </View>

      {blocklist.whitelisted?.length > 0 && (
        <View style={s.panel}>
          <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>WHITELISTED IPs ({blocklist.whitelisted.length})</Text>
          {blocklist.whitelisted.map((w: any, i: number) => (
            <View key={w.wl_id || i} style={{
              flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 8,
              borderRadius: 8, marginBottom: 4, backgroundColor: (globalThis as any).__alphaColor(T.success, '08'),
              borderLeftWidth: 3, borderLeftColor: T.success,
            }}>
              <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(T.success, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="checkmark-circle" size={14} color={T.successText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{w.ip}</Text>
                <Text style={{ color: T.textMuted, fontSize: 9 }}>
                  {w.city || 'Private'}{w.country_code ? `, ${w.country_code}` : ''} | {w.isp || 'Unknown ISP'}
                </Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 9 }}>{new Date(w.added_at).toLocaleDateString()}</Text>
              <TouchableOpacity accessibilityLabel={tx('admin.blocklistPanel.auto.accessibility.004', 'Remove')} onPress={() => removeWhitelist(w.ip)}
                style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                <Text style={{ color: T.error, fontSize: 9, fontWeight: '700' }}>{tx('admin.blocklistPanel.auto.text.007', 'Remove')}</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
