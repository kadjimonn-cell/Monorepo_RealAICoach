import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface WafRule { id: string; name: string; pattern: string; severity: string; enabled: boolean; }
interface GeoRule { country_code: string; country_name: string; action: string; added_at: string; }
interface BlockedIP { ip: string; reason: string; blocked_at: string; city: string; country: string; isp: string; }

const SEV_COLORS: Record<string, string> = { critical: 'var(--app-error)', high: 'var(--app-warning)', medium: 'var(--app-primary)', low: 'var(--app-success)' };

export default function WAFFirewallPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [tab, setTab] = useState<'rules' | 'blocklist' | 'geo' | 'bots'>('rules');
  const [wafData, setWafData] = useState<any>(null);
  const [blocklist, setBlocklist] = useState<any>(null);
  const [geoRules, setGeoRules] = useState<GeoRule[]>([]);
  const [botData, setBotData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [blockIp, setBlockIp] = useState('');
  const [blockReason, setBlockReason] = useState('');
  const [geoCode, setGeoCode] = useState('');
  const [geoAction, setGeoAction] = useState('block');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [waf, ips, geo, bots] = await Promise.all([
        api.get('/api/admin/security/waf/stats').then(r => r.data).catch(() => null),
        api.get('/api/admin/sessions/blocked-ips').then(r => r.data).catch(() => null),
        api.get('/api/admin/security/waf/geo-rules').then(r => r.data).catch(() => ({ rules: [] })),
        api.get('/api/admin/security/waf/bot-detections').then(r => r.data).catch(() => null),
      ]);
      setWafData(waf);
      setBlocklist(ips);
      setGeoRules(geo?.rules || []);
      setBotData(bots);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/waf-firewall/hybrid-refresh',
    onTick: load,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const handleBlockIP = async () => {
    if (!blockIp.trim()) return;
    try {
      await api.post('/api/admin/sessions/blocked-ips', { ip: blockIp.trim(), reason: blockReason || 'Manual block' });
      setBlockIp(''); setBlockReason('');
      load();
    } catch (e) { console.error(e); }
  };

  const handleUnblockIP = async (ip: string) => {
    try { await api.delete(`/api/admin/sessions/blocked-ips/${encodeURIComponent(ip)}`); load(); } catch (e) { console.error(e); }
  };

  const handleAddGeoRule = async () => {
    if (!geoCode.trim()) return;
    try {
      await api.post('/api/admin/security/waf/geo-rules', { country_code: geoCode.toUpperCase().trim(), action: geoAction });
      setGeoCode('');
      load();
    } catch (e) { console.error(e); }
  };

  const handleRemoveGeoRule = async (cc: string) => {
    try { await api.delete(`/api/admin/security/waf/geo-rules/${cc}`); load(); } catch (e) { console.error(e); }
  };

  if (loading && !wafData) return <View style={{ padding: 24, alignItems: 'center' }}><Text style={{ color: colors.textMuted }}>{tx('admin.wafFirewallPanel.states.loading', 'Loading WAF data...')}</Text></View>;

  const tabs = [
    { id: 'rules' as const, label: 'WAF Rules', icon: 'shield-checkmark' },
    { id: 'blocklist' as const, label: 'IP Blocklist', icon: 'ban' },
    { id: 'geo' as const, label: 'Geo-Blocking', icon: 'earth' },
    { id: 'bots' as const, label: 'Bot Detection', icon: 'bug' },
  ];

  return (
    <ScrollView style={{ flex: 1, padding: 16 }} data-testid="waf-firewall-panel" testID="waf-firewall-panel">
      <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text, marginBottom: 4 }}>{tx('admin.wafFirewallPanel.header.title', 'WAF & Firewall Management')}</Text>
      <Text style={{ fontSize: 13, color: colors.textMuted, marginBottom: 16 }}>{tx('admin.wafFirewallPanel.header.subtitle', 'Real-time firewall rules, IP blocklist, geo-blocking, and bot detection')}</Text>

      {/* Stats row */}
      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        {[
          { label: 'Active Rules', value: wafData?.builtin_rules?.filter((r: WafRule) => r.enabled).length || 0, color: colors.primary, icon: 'shield' },
          { label: 'Blocked IPs', value: blocklist?.stats?.total_blocked || 0, color: colors.error, icon: 'ban' },
          { label: 'Geo Rules', value: geoRules.length, color: colors.warningText, icon: 'earth' },
          { label: 'Bots Detected', value: botData?.total_detected || 0, color: colors.successText, icon: 'bug' },
        ].map((s, i) => (
          <View key={i} style={{ flex: 1, minWidth: 140, backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid={`waf-stat-${s.label.toLowerCase().replace(/\s/g, '-')}`} testID={`waf-stat-${s.label.toLowerCase().replace(/\s/g, '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <Ionicons name={s.icon as any} size={14} color={s.color} />
              <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</Text>
            </View>
            <Text style={{ fontSize: 28, fontWeight: '800', color: s.color }}>{s.value}</Text>
          </View>
        ))}
      </View>

      {/* Tab bar */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8, backgroundColor: tab === t.id ? 'var(--app-primary)' : colors.surface, borderWidth: 1, borderColor: tab === t.id ? 'var(--app-primary)' : colors.border }}
            data-testid={`waf-tab-${t.id}`} testID={`waf-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? colors.primaryText : colors.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: tab === t.id ? colors.primaryText : colors.text }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* WAF Rules Tab */}
      {tab === 'rules' && wafData?.builtin_rules && (
        <View data-testid="waf-rules-list" testID="waf-rules-list">
          {wafData.builtin_rules.map((rule: WafRule) => (
            <View key={rule.id} style={{ backgroundColor: colors.surface, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{rule.name}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: `${SEV_COLORS[rule.severity] || colors.textMuted}20` }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: SEV_COLORS[rule.severity] || colors.textMuted, textTransform: 'uppercase' }}>{rule.severity}</Text>
                  </View>
                </View>
                <Text style={{ fontSize: 11, color: colors.textMuted, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} numberOfLines={1}>{rule.pattern.substring(0, 60)}...</Text>
              </View>
              <View style={{ backgroundColor: rule.enabled ? 'var(--app-success-soft)' : 'var(--app-error-soft)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: rule.enabled ? 'var(--app-success)' : 'var(--app-error)' }}>{rule.enabled ? 'ACTIVE' : 'OFF'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* IP Blocklist Tab */}
      {tab === 'blocklist' && (
        <View data-testid="waf-blocklist-panel" testID="waf-blocklist-panel">
          {/* Add IP form */}
          <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, marginBottom: 8 }}>{tx('admin.wafFirewallPanel.blocklist.blockIpTitle', 'Block IP Address')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <TextInput placeholder={tx('admin.wafFirewallPanel.blocklist.ipPlaceholder', 'IP Address (e.g. 192.168.1.1)')} placeholderTextColor={colors.textMuted} value={blockIp} onChangeText={setBlockIp}
                style={{ flex: 2, minWidth: 160, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, color: colors.text, fontSize: 13, backgroundColor: colors.background }} data-testid="block-ip-input" testID="block-ip-input" />
              <TextInput placeholder={tx('admin.wafFirewallPanel.blocklist.reasonPlaceholder', 'Reason')} placeholderTextColor={colors.textMuted} value={blockReason} onChangeText={setBlockReason}
                style={{ flex: 2, minWidth: 120, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, color: colors.text, fontSize: 13, backgroundColor: colors.background }} data-testid="block-reason-input" testID="block-reason-input" />
              <TouchableOpacity onPress={handleBlockIP}
                style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 16, paddingVertical: 10, justifyContent: 'center' }} data-testid="block-ip-btn" testID="block-ip-btn">
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.wafFirewallPanel.blocklist.blockButton', 'Block')}</Text>
              </TouchableOpacity>
            </View>
          </View>
          {/* Blocked list */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, marginBottom: 8 }}>{blocklist?.stats?.total_blocked || 0} Blocked IPs</Text>
          {(blocklist?.blocked || []).slice(0, 20).map((b: BlockedIP, i: number) => (
            <View key={i} style={{ backgroundColor: colors.surface, borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>{b.ip}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted }}>{b.reason} | {b.country || 'Unknown'} {b.city ? `/ ${b.city}` : ''}</Text>
              </View>
              <TouchableOpacity onPress={() => handleUnblockIP(b.ip)} style={{ padding: 6 }} data-testid={`unblock-${b.ip}`} testID={`unblock-${b.ip}`}>
                <Ionicons name="close-circle" size={20} color={'var(--app-error)'} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {/* Geo-Blocking Tab */}
      {tab === 'geo' && (
        <View data-testid="waf-geo-panel" testID="waf-geo-panel">
          <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, marginBottom: 8 }}>{tx('admin.wafFirewallPanel.geo.title', 'Add Geo-Blocking Rule')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <TextInput placeholder={tx('admin.wafFirewallPanel.geo.countryPlaceholder', 'Country code (e.g. CN, RU)')} placeholderTextColor={colors.textMuted} value={geoCode} onChangeText={setGeoCode}
                style={{ flex: 1, minWidth: 120, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, color: colors.text, fontSize: 13, backgroundColor: colors.background }} data-testid="geo-code-input" testID="geo-code-input" />
              <TouchableOpacity onPress={() => setGeoAction(geoAction === 'block' ? 'challenge' : 'block')}
                style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: geoAction === 'block' ? 'var(--app-error-soft)' : 'var(--app-warning-soft)' }} data-testid="geo-action-toggle" testID="geo-action-toggle">
                <Text style={{ fontSize: 13, fontWeight: '600', color: geoAction === 'block' ? 'var(--app-error)' : 'var(--app-warning)' }}>{geoAction === 'block' ? 'Block' : 'Challenge'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleAddGeoRule}
                style={{ backgroundColor: colors.primary, borderRadius: 8, paddingHorizontal: 16, paddingVertical: 10 }} data-testid="add-geo-rule-btn" testID="add-geo-rule-btn">
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.wafFirewallPanel.geo.addRuleButton', 'Add Rule')}</Text>
              </TouchableOpacity>
            </View>
          </View>
          {geoRules.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <Ionicons name="earth" size={32} color={colors.textMuted} />
              <Text style={{ color: colors.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.wafFirewallPanel.geo.empty', 'No geo-blocking rules configured')}</Text>
            </View>
          ) : geoRules.map((g, i) => (
            <View key={i} style={{ backgroundColor: colors.surface, borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Text style={{ fontSize: 18 }}>{String.fromCodePoint(...(g.country_code || '').split('').map((c: string) => 0x1F1E6 + c.charCodeAt(0) - 65))}</Text>
                <View>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{g.country_code}</Text>
                  <Text style={{ fontSize: 11, color: colors.textMuted }}>{g.action}</Text>
                </View>
              </View>
              <TouchableOpacity onPress={() => handleRemoveGeoRule(g.country_code)} style={{ padding: 6 }} data-testid={`remove-geo-${g.country_code}`} testID={`remove-geo-${g.country_code}`}>
                <Ionicons name="trash" size={18} color={'var(--app-error)'} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {/* Bot Detection Tab */}
      {tab === 'bots' && (
        <View data-testid="waf-bots-panel" testID="waf-bots-panel">
          {botData ? (
            <>
              <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
                {[
                  { label: 'Total Detected', value: botData.total_detected, color: colors.error },
                  { label: 'Blocked', value: botData.blocked, color: colors.warningText },
                  { label: 'Allowed Bots', value: botData.allowed, color: colors.successText },
                ].map((s, i) => (
                  <View key={i} style={{ flex: 1, minWidth: 120, backgroundColor: colors.surface, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: colors.border }}>
                    <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600', textTransform: 'uppercase' }}>{s.label}</Text>
                    <Text style={{ fontSize: 24, fontWeight: '800', color: s.color, marginTop: 4 }}>{s.value}</Text>
                  </View>
                ))}
              </View>
              {(botData.recent || []).slice(0, 10).map((b: any, i: number) => (
                <View key={i} style={{ backgroundColor: colors.surface, borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: colors.border }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{b.bot_name || b.user_agent?.substring(0, 40) || 'Unknown Bot'}</Text>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: b.action === 'blocked' ? 'var(--app-error-soft)' : 'var(--app-success-soft)' }}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: b.action === 'blocked' ? 'var(--app-error)' : 'var(--app-success)' }}>{(b.action || 'detected').toUpperCase()}</Text>
                    </View>
                  </View>
                  <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }}>{b.ip || ''} | {b.path || '/'} | {new Date(b.timestamp || Date.now()).toLocaleString()}</Text>
                </View>
              ))}
            </>
          ) : (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <Text style={{ color: colors.textMuted }}>{tx('admin.wafFirewallPanel.bots.empty', 'No bot detection data')}</Text>
            </View>
          )}
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}
