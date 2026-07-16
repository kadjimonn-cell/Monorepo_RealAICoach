import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

export default function CDNManagementPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const _colors = useAdminTheme();
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const d = width >= 1024;
  const [config, setConfig] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [edges, setEdges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [purging, setPurging] = useState(false);
  const [tab, setTab] = useState<'overview' | 'edges' | 'analytics'>('overview');

  const load = useCallback(async () => {
    try {
      const [cfgRes, edgeRes, analyticsRes] = await Promise.all([
        api.get('/admin/cdn/config'),
        api.get('/admin/cdn/edge-locations'),
        api.get('/admin/cdn/analytics'),
      ]);
      setConfig(cfgRes.data);
      setEdges(edgeRes.data.locations || []);
      setAnalytics(analyticsRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const purgeCache = async () => {
    setPurging(true);
    try {
      await api.post('/admin/cdn/purge-cache', { purge_type: 'all' });
    } catch (e) { console.error(e); }
    finally { setPurging(false); }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  const summary = analytics?.summary || {};
  const hourlyData = analytics?.hourly_data || [];
  const edgeTraffic = analytics?.edge_traffic || [];
  const topAssets = analytics?.top_assets || [];
  const maxReqs = Math.max(...hourlyData.map((h: any) => h.total_requests), 1);

  return (
    <View style={s.panel} data-testid="cdn-management-panel" testID="cdn-management-panel">
      {/* Header */}
      <View style={[s.panelHeader, { marginBottom: 16 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.cyan, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="globe" size={18} color={T.cyan} />
          </View>
          <View>
            <Text style={s.panelTitle}>{tx('admin.cDNManagementPanel.auto.text.001', 'CDN Management')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{config?.provider || 'Cloudflare'} — {config?.status || 'active'}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity onPress={purgeCache} disabled={purging}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.warning, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.warning, '30') }}
            data-testid="cdn-purge-btn" testID="cdn-purge-btn">
            {purging ? <ActivityIndicator size="small" color={T.warningText} /> : <Ionicons name="trash" size={14} color={T.warningText} />}
            <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '600' }}>{tx('admin.cDNManagementPanel.auto.text.002', 'Purge Cache')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setLoading(true); load(); }} style={s.refreshBtn} data-testid="cdn-refresh-btn" testID="cdn-refresh-btn">
            <Ionicons name="refresh" size={16} color={T.textSec} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 16 }}>
        {(['overview', 'edges', 'analytics'] as const).map(t => (
          <TouchableOpacity key={t} onPress={() => setTab(t)}
            style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: tab === t ? (globalThis as any).__alphaColor(T.primary, '18') : 'transparent', borderWidth: 1, borderColor: tab === t ? (globalThis as any).__alphaColor(T.primary, '30') : 'transparent' }}
            data-testid={`cdn-tab-${t}`} testID={`cdn-tab-${t}`}>
            <Text style={{ color: tab === t ? T.primary : T.textMuted, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <View style={{ gap: 12 }}>
          {/* KPIs */}
          <View style={{ flexDirection: d ? 'row' : 'column', gap: 10 }}>
            {[
              { label: 'Cache Hit Rate', value: `${summary.avg_cache_hit_rate || config?.cache_hit_rate || 0}%`, icon: 'checkmark-circle', color: T.successText },
              { label: 'Requests (24h)', value: `${((summary.total_requests_24h || config?.total_requests_24h || 0) / 1000).toFixed(0)}K`, icon: 'pulse', color: T.primary },
              { label: 'Bandwidth Saved', value: `${config?.bandwidth_saved_percent || 0}%`, icon: 'cloud-download', color: T.cyan },
              { label: 'Edge Locations', value: `${config?.edge_count || 0}/${config?.total_edge_locations || 0}`, icon: 'globe', color: T.purpleText },
              { label: 'P95 Latency', value: `${summary.p95_latency_ms || 0}ms`, icon: 'speedometer', color: T.warningText },
            ].map((kpi, i) => (
              <View key={i} style={{ flex: d ? 1 : undefined, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: kpi.color }}
                data-testid={`cdn-kpi-${kpi.label.toLowerCase().replace(/[\s()]/g, '-')}`} testID={`cdn-kpi-${kpi.label.toLowerCase().replace(/[\s()]/g, '-')}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Ionicons name={kpi.icon as any} size={14} color={kpi.color} />
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{kpi.label}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }}>{kpi.value}</Text>
              </View>
            ))}
          </View>

          {/* Config Summary */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.cDNManagementPanel.auto.text.003', 'Configuration')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { label: 'Provider', value: config?.provider, active: true },
                { label: 'Strategy', value: config?.caching_strategy },
                { label: 'Compression', value: config?.compression },
                { label: 'HTTP/2 Push', value: config?.http2_push ? 'On' : 'Off', active: config?.http2_push },
                { label: 'HTTP/3', value: config?.http3_enabled ? 'On' : 'Off', active: config?.http3_enabled },
                { label: 'Minify JS', value: config?.minify_js ? 'On' : 'Off', active: config?.minify_js },
                { label: 'Minify CSS', value: config?.minify_css ? 'On' : 'Off', active: config?.minify_css },
                { label: 'Image Opt', value: config?.image_optimization ? 'On' : 'Off', active: config?.image_optimization },
                { label: 'WebP', value: config?.webp_conversion ? 'On' : 'Off', active: config?.webp_conversion },
              ].map((item, i) => (
                <View key={i} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: item.active !== false ? (globalThis as any).__alphaColor(T.success, '10') : T.border, borderWidth: 1, borderColor: item.active !== false ? (globalThis as any).__alphaColor(T.success, '20') : T.border }}>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{item.label}</Text>
                  <Text style={{ color: item.active !== false ? T.success : T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Top Cached Assets */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.cDNManagementPanel.auto.text.004', 'Top Cached Assets')}</Text>
            {topAssets.map((asset: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: i < topAssets.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
                <Text style={{ flex: 3, color: T.textSec, fontSize: 11, fontFamily: 'monospace' }}>{asset.path}</Text>
                <Text style={{ flex: 1, color: T.text, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{(asset.hits / 1000).toFixed(0)}K hits</Text>
                <View style={{ flex: 1, alignItems: 'flex-end' }}>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: asset.cache_status === 'HIT' ? (globalThis as any).__alphaColor(T.success, '20') : T.warning + '20' }}>
                    <Text style={{ color: asset.cache_status === 'HIT' ? T.success : T.warning, fontSize: 9, fontWeight: '700' }}>{asset.cache_status}</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Edges Tab */}
      {tab === 'edges' && (
        <View style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {edges.map((edge: any, i: number) => (
              <View key={i} style={{ width: d ? '48%' : '100%', backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: edge.enabled ? (globalThis as any).__alphaColor(T.success, '30') : T.border, borderLeftWidth: 3, borderLeftColor: edge.enabled ? T.success : T.textMuted }}
                data-testid={`cdn-edge-${edge.id}`} testID={`cdn-edge-${edge.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{edge.name}</Text>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: edge.enabled ? (globalThis as any).__alphaColor(T.success, '20') : T.textMuted + '20' }}>
                    <Text style={{ color: edge.enabled ? T.success : T.textMuted, fontSize: 9, fontWeight: '700' }}>{edge.status?.toUpperCase()}</Text>
                  </View>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{edge.region} — {edge.latency_ms}ms latency</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Analytics Tab */}
      {tab === 'analytics' && (
        <View style={{ gap: 12 }}>
          {/* Hourly Traffic Chart */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="cdn-hourly-chart" testID="cdn-hourly-chart">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.cDNManagementPanel.auto.text.005', '24h Traffic')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 16 }}>{tx('admin.cDNManagementPanel.auto.text.006', 'Hourly requests distribution')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 100 }}>
              {hourlyData.map((h: any, i: number) => {
                const barH = (h.total_requests / maxReqs) * 90;
                const cachedH = (h.cached_requests / maxReqs) * 90;
                return (
                  <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ width: '80%', height: barH, borderRadius: 2 }}>
                      <View style={{ flex: 1, backgroundColor: T.border, borderRadius: 2 }}>
                        <View style={{ height: cachedH, backgroundColor: (globalThis as any).__alphaColor(T.cyan, '60'), borderRadius: 2 }} />
                      </View>
                    </View>
                    {i % 4 === 0 && <Text style={{ color: T.textMuted, fontSize: 7, marginTop: 2 }}>{h.hour}</Text>}
                  </View>
                );
              })}
            </View>
          </View>

          {/* Edge Traffic Table */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.cDNManagementPanel.auto.text.007', 'Edge Location Traffic')}</Text>
            {edgeTraffic.map((et: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: i < edgeTraffic.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
                <Text style={{ flex: 2, color: T.textSec, fontSize: 11, fontWeight: '600' }}>{et.name}</Text>
                <Text style={{ flex: 1, color: T.text, fontSize: 11, textAlign: 'right' }}>{(et.requests_24h / 1000).toFixed(1)}K</Text>
                <Text style={{ flex: 1, color: T.text, fontSize: 11, textAlign: 'right' }}>{et.bandwidth_gb}GB</Text>
                <Text style={{ flex: 1, color: et.cache_hit_rate > 95 ? T.success : T.warning, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{et.cache_hit_rate}%</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}
