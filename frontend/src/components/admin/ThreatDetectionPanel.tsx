import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
}; }
export default function ThreatDetectionPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [blockingIp, setBlockingIp] = useState('');

  const fetchThreats = useCallback(async () => {
    try {
      const response = await api.get('/admin/security/threats/live');
      setData(response.data);
    } catch (error) {
      console.error('Threat fetch error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/threat-detection/hybrid-refresh',
    onTick: fetchThreats,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const blockIp = async (ip: string) => {
    setBlockingIp(ip);
    try {
      await api.post('/admin/security/threats/block-ip', { ip, reason: 'Blocked from threat dashboard', duration_hours: 24 });
      fetchThreats();
    } finally { setBlockingIp(''); }
  };

  const unblockIp = async (ip: string) => {
    try {
      await api.post('/admin/security/threats/unblock-ip', { ip });
      fetchThreats();
    } catch (e) { console.error(e); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <AutoFixBanner domain="threat_detection" />
      <ActivityIndicator size="large" color={T.error} />
      <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.threatDetectionPanel.auto.text.001', 'Loading Threat Dashboard...')}</Text>
    </View>
  );

  const stats = data?.stats || {};
  const threats = data?.recent_threats || [];
  const blockedIps = data?.blocked_ips || [];
  const sevColors: Record<string, string> = {
    critical: T.error,
    high: T.warning,
    medium: T.primary,
    low: T.textDim,
  };

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${T.error}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="eye" size={18} color={T.error} />
          </div>
          <div>
            <Text style={{ fontSize: 16, fontWeight: '700', color: T.text }}>{tx('admin.threatDetectionPanel.auto.text.002', 'Real-Time Threat Detection')}</Text>
            <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.threatDetectionPanel.auto.text.003', 'Live WAF monitoring with auto-refresh every 15s')}</Text>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success, animation: 'pulse 2s infinite' }} />
          <span style={{ fontSize: 10, color: T.successText, fontWeight: '700' }}>LIVE</span>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
        {[
          { label: 'Threats (24h)', value: stats.total_24h || 0, color: T.error, icon: 'alert-circle' },
          { label: 'Critical', value: stats.by_severity?.critical || 0, color: colors.error, icon: 'warning' },
          { label: 'High', value: stats.by_severity?.high || 0, color: colors.warningText, icon: 'shield' },
          { label: 'Medium', value: stats.by_severity?.medium || 0, color: colors.primary, icon: 'information-circle' },
          { label: 'Blocked IPs', value: blockedIps.length, color: T.purpleText, icon: 'ban' },
        ].map((card, i) => (
          <div key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}`, textAlign: 'center' }} data-testid={`threat-stat-${i}`}>
            <Ionicons name={card.icon as any} size={16} color={card.color} />
            <div style={{ fontSize: 24, fontWeight: '800', color: card.color, marginTop: 4 }}>{card.value}</div>
            <div style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 2 }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* Two-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        {/* Recent Threats */}
        <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="recent-threats">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="list" size={14} color={T.error} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.threatDetectionPanel.auto.text.004', 'Recent Threats')}</Text>
            <span style={{ fontSize: 9, color: T.textMuted }}>(last 1h)</span>
          </div>
          {threats.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Ionicons name="shield-checkmark" size={24} color={T.successText} />
              <Text style={{ fontSize: 12, color: T.successText, fontWeight: '600', marginTop: 8 }}>{tx('admin.threatDetectionPanel.auto.text.005', 'No threats detected')}</Text>
            </div>
          ) : (
            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
              {threats.map((t: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < threats.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                  <span style={{ fontSize: 8, fontWeight: '700', color: sevColors[t.severity] || T.textMuted, backgroundColor: `${sevColors[t.severity] || T.textMuted}18`, padding: '2px 5px', borderRadius: 3, textTransform: 'uppercase', flexShrink: 0 }}>{t.severity}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{t.rule_name}</div>
                    <div style={{ fontSize: 10, color: T.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.path}</div>
                    <div style={{ fontSize: 9, color: T.textMuted }}>{t.client_ip} | {new Date(t.timestamp).toLocaleTimeString()}</div>
                  </div>
                  <button onClick={() => blockIp(t.client_ip)} disabled={blockingIp === t.client_ip}
                    style={{ fontSize: 9, padding: '3px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', backgroundColor: `${T.error}20`, color: T.error, fontWeight: '700', flexShrink: 0 }}
                    data-testid={`block-ip-${i}`}>
                    {blockingIp === t.client_ip ? '...' : 'Block'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column: Top Rules & Blocked IPs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Top Attack Types */}
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="top-rules">
            <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.threatDetectionPanel.auto.text.006', 'Top Attack Types')}</Text>
            {(stats.top_rules || []).map((r: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: i < (stats.top_rules?.length || 0) - 1 ? `1px solid ${T.border}` : 'none' }}>
                <span style={{ fontSize: 11, color: T.text, fontWeight: '500' }}>{r.rule}</span>
                <span style={{ fontSize: 12, fontWeight: '700', color: T.error }}>{r.count}</span>
              </div>
            ))}
            {(!stats.top_rules || stats.top_rules.length === 0) && (
              <Text style={{ fontSize: 11, color: T.textMuted, textAlign: 'center' }}>{tx('admin.threatDetectionPanel.auto.text.007', 'No attacks recorded')}</Text>
            )}
          </div>

          {/* Blocked IPs */}
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="blocked-ips">
            <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.threatDetectionPanel.auto.text.008', 'Blocked IPs')}</Text>
            {blockedIps.length === 0 ? (
              <Text style={{ fontSize: 11, color: T.textMuted, textAlign: 'center' }}>{tx('admin.threatDetectionPanel.auto.text.009', 'No blocked IPs')}</Text>
            ) : (
              blockedIps.map((b: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: i < blockedIps.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                  <div>
                    <div style={{ fontSize: 11, color: T.text, fontFamily: 'monospace' }}>{b.ip}</div>
                    <div style={{ fontSize: 9, color: T.textMuted }}>{b.reason}</div>
                  </div>
                  <button onClick={() => unblockIp(b.ip)}
                    style={{ fontSize: 9, padding: '3px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', backgroundColor: `${T.success}20`, color: T.successText, fontWeight: '700' }}
                    data-testid={`unblock-${i}`}>
                    Unblock
                  </button>
                </div>
              ))
            )}
          </div>

          {/* Top Offending IPs */}
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="top-ips">
            <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.threatDetectionPanel.auto.text.010', 'Top Offending IPs')}</Text>
            {(stats.top_ips || []).map((ip: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0' }}>
                <span style={{ fontSize: 10, color: T.text, fontFamily: 'monospace' }}>{ip.ip}</span>
                <span style={{ fontSize: 11, fontWeight: '700', color: T.warningText }}>{ip.count}</span>
              </div>
            ))}
            {(!stats.top_ips || stats.top_ips.length === 0) && (
              <Text style={{ fontSize: 11, color: T.textMuted, textAlign: 'center' }}>{tx('admin.threatDetectionPanel.auto.text.011', 'No data')}</Text>
            )}
          </div>
        </div>
      </div>
    </ScrollView>
  );
}
