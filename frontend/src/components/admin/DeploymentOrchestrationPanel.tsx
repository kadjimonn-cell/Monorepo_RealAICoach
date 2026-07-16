import React, { useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

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

const statusColors: Record<string, string> = { active: 'var(--app-success)', standby: 'var(--app-warning)', deployed: 'var(--app-primary)', pending: 'var(--app-text)', rolled_back: 'var(--app-error)' };
const strategyLabels: Record<string, string> = { rolling: 'Rolling Update', 'blue-green': 'Blue-Green', canary: 'Canary' };

export default function DeploymentOrchestrationPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [regions, setRegions] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [releaseDashboard, setReleaseDashboard] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [releaseRunning, setReleaseRunning] = useState(false);
  const [selectedRegions, setSelectedRegions] = useState<string[]>([]);
  const [strategy, setStrategy] = useState('rolling');
  const [version, setVersion] = useState('v2.4.0');
  const [canaryPct, setCanaryPct] = useState(10);
  const [tab, setTab] = useState<'regions' | 'deploy' | 'history' | 'release'>('regions');

  const fetchData = () => {
    Promise.all([
      api.get('/admin/security/deployments/regions').then(r => setRegions(r.data.regions || [])),
      api.get('/admin/security/deployments/history').then(r => setHistory(r.data.deployments || [])),
      api.get('/admin/security/deployments/release-intelligence/dashboard').then(r => setReleaseDashboard(r.data || null)),
    ]).catch(e => console.error(e)).finally(() => setLoading(false));
  };

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/deployment-orchestration/hybrid-refresh',
    onTick: fetchData,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });
  const toggleRegion = (id: string) => {
    setSelectedRegions(prev => prev.includes(id) ? prev.filter(r => r !== id) : [...prev, id]);
  };

  const deploy = async () => {
    if (!selectedRegions.length) return;
    setDeploying(true);
    try {
      await api.post('/admin/security/deployments/deploy', {
        region_ids: selectedRegions, version, strategy, canary_percent: canaryPct,
      });
      setSelectedRegions([]);
      fetchData();
    } finally { setDeploying(false); }
  };

  const rollback = async (regionId: string) => {
    try {
      await api.post('/admin/security/deployments/rollback', { region_ids: [regionId], version: 'rollback' });
      fetchData();
    } catch (e) { console.error(e); }
  };

  const runReleaseMonitor = async () => {
    if (releaseRunning) return;
    setReleaseRunning(true);
    try {
      await api.post('/admin/security/deployments/release-intelligence/monitor/run');
      fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setReleaseRunning(false);
    }
  };

  const evaluateRelease = async (releaseId: string) => {
    if (!releaseId || releaseRunning) return;
    setReleaseRunning(true);
    try {
      await api.post(`/admin/security/deployments/release-intelligence/evaluate/${releaseId}`);
      fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setReleaseRunning(false);
    }
  };

  const forceRollbackRelease = async (releaseId: string) => {
    if (!releaseId || releaseRunning) return;
    setReleaseRunning(true);
    try {
      await api.post(`/admin/security/deployments/release-intelligence/rollback/${releaseId}`);
      fetchData();
    } catch (e) {
      console.error(e);
    } finally {
      setReleaseRunning(false);
    }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <AutoFixBanner domain="deployments" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.deploymentOrchestrationPanel.states.loading', 'Loading Deployment Dashboard...')}</Text>
    </View>
  );

  const tabs = [
    { id: 'regions' as const, label: 'Regions', icon: 'earth' },
    { id: 'deploy' as const, label: 'Deploy', icon: 'rocket' },
    { id: 'history' as const, label: 'History', icon: 'time' },
    { id: 'release' as const, label: 'Release IQ', icon: 'shield-checkmark' },
  ];

  const activeRelease = releaseDashboard?.active_release || null;
  const releaseSummary = releaseDashboard?.summary || {};
  const recentReleases = releaseDashboard?.recent_releases || [];

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="globe" size={18} color={T.primary} />
        </div>
        <div>
          <Text style={{ fontSize: 16, fontWeight: '700', color: T.text }}>{tx('admin.deploymentOrchestrationPanel.header.title', 'Multi-Region Deployment')}</Text>
          <Text style={{ fontSize: 11, color: T.textMuted }}>Rolling, Blue-Green & Canary deployments across {regions.length} regions</Text>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, borderBottom: `1px solid ${T.border}`, paddingBottom: 8 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`deploy-tab-${t.id}`}
            style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', backgroundColor: tab === t.id ? 'rgba(59,130,246,0.12)' : 'transparent', color: tab === t.id ? T.primary : T.textMuted, fontSize: 11, fontWeight: '700' }}>
            <Ionicons name={t.icon as any} size={12} color={tab === t.id ? T.primary : T.textMuted} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Regions Tab */}
      {tab === 'regions' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }} data-testid="regions-grid">
          {regions.map((r: any, i: number) => (
            <div key={r.id} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${selectedRegions.includes(r.id) ? T.primary : T.border}`, cursor: 'pointer', transition: 'border-color 0.2s' }}
              onClick={() => toggleRegion(r.id)} data-testid={`region-${r.id}`}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: statusColors[r.status] || T.textMuted }} />
                  <span style={{ fontSize: 12, fontWeight: '700', color: T.text }}>{r.name}</span>
                </div>
                {selectedRegions.includes(r.id) && <Ionicons name="checkmark-circle" size={16} color={T.primary} />}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 10 }}>
                <div><span style={{ color: T.textMuted }}>Provider:</span> <span style={{ color: T.text }}>{r.provider}</span></div>
                <div><span style={{ color: T.textMuted }}>Latency:</span> <span style={{ color: T.text }}>{r.latency_ms}ms</span></div>
                <div><span style={{ color: T.textMuted }}>Version:</span> <span style={{ color: r.current_version === 'not deployed' ? T.warning : T.success }}>{r.current_version}</span></div>
                <div><span style={{ color: T.textMuted }}>Status:</span> <span style={{ color: statusColors[r.deploy_status] || T.textMuted, textTransform: 'uppercase', fontSize: 9, fontWeight: '700' }}>{r.deploy_status}</span></div>
              </div>
              {r.deploy_status === 'deployed' && (
                <button onClick={(e) => { e.stopPropagation(); rollback(r.id); }}
                  style={{ marginTop: 8, fontSize: 9, padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', backgroundColor: 'rgba(239,68,68,0.1)', color: T.error, fontWeight: '700' }}
                  data-testid={`rollback-${r.id}`}>
                  Rollback
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Deploy Tab */}
      {tab === 'deploy' && (
        <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 20, border: `1px solid ${T.border}` }} data-testid="deploy-form">
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 16 }}>{tx('admin.deploymentOrchestrationPanel.deployForm.title', 'New Deployment')}</Text>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Version</label>
              <input data-testid="deploy-version" type="text" value={version} onChange={e => setVersion(e.target.value)}
                style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.card, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Strategy</label>
              <select data-testid="deploy-strategy" value={strategy} onChange={e => setStrategy(e.target.value)}
                style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.card, color: T.text, fontSize: 12, outline: 'none' }}>
                <option value="rolling">Rolling Update</option>
                <option value="blue-green">Blue-Green</option>
                <option value="canary">Canary</option>
              </select>
            </div>
            {strategy === 'canary' && (
              <div>
                <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Canary %</label>
                <input data-testid="deploy-canary-pct" type="number" value={canaryPct} aria-label="Text input" onChange={e => setCanaryPct(parseInt(e.target.value) || 5)}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.card, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
              </div>
            )}
          </div>
          <div style={{ marginBottom: 16 }}>
            <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 8 }}>Selected Regions ({selectedRegions.length}):</Text>
            {selectedRegions.length === 0 ? (
              <Text style={{ fontSize: 11, color: T.warningText }}>{tx('admin.deploymentOrchestrationPanel.deployForm.emptyRegions', 'Go to Regions tab and click to select target regions')}</Text>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {selectedRegions.map(id => {
                  const r = regions.find((reg: any) => reg.id === id);
                  return (
                    <span key={id} style={{ fontSize: 10, padding: '4px 8px', borderRadius: 4, backgroundColor: 'rgba(59,130,246,0.12)', color: T.primary, fontWeight: '600' }}>
                      {r?.name || id}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
          <button data-testid="trigger-deploy-btn" onClick={deploy} disabled={deploying || !selectedRegions.length}
            style={{ width: '100%', padding: '10px', borderRadius: 8, border: 'none', cursor: selectedRegions.length ? 'pointer' : 'not-allowed', backgroundColor: selectedRegions.length ? T.primary : T.textMuted, color: colors.primaryText, fontSize: 13, fontWeight: '700', opacity: deploying ? 0.6 : 1 }}>
            {deploying ? 'Deploying...' : `Deploy to ${selectedRegions.length} Region(s)`}
          </button>
        </div>
      )}

      {/* History Tab */}
      {tab === 'history' && (
        <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="deploy-history">
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.deploymentOrchestrationPanel.history.title', 'Deployment History')}</Text>
          {history.length === 0 ? (
            <Text style={{ fontSize: 11, color: T.textMuted, textAlign: 'center', padding: 20 }}>{tx('admin.deploymentOrchestrationPanel.history.empty', 'No deployments yet')}</Text>
          ) : (
            history.map((d: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: i < history.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${statusColors[d.status] || T.textMuted}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Ionicons name={d.strategy === 'rollback' ? 'arrow-undo' : 'rocket'} size={14} color={statusColors[d.status] || T.textMuted} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{d.region_name}</div>
                  <div style={{ fontSize: 10, color: T.textMuted }}>
                    {d.version} | {strategyLabels[d.strategy] || d.strategy} | {d.deploy_time_seconds}s
                    {d.rollback_from && <span style={{ color: T.error }}> (from {d.rollback_from})</span>}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <span style={{ fontSize: 9, fontWeight: '700', color: statusColors[d.status] || T.textMuted, textTransform: 'uppercase' }}>{d.status}</span>
                  <div style={{ fontSize: 9, color: T.textMuted }}>{new Date(d.deployed_at).toLocaleString()}</div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Release Intelligence Tab */}
      {tab === 'release' && (
        <div style={{ display: 'grid', gap: 12 }} data-testid="release-intelligence-tab">
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="release-intelligence-header">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div>
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }} data-testid="release-intelligence-title" testID="release-intelligence-title">{tx('admin.deploymentOrchestrationPanel.release.title', 'Release Intelligence (Auto-Rollback)')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted }} data-testid="release-intelligence-subtitle" testID="release-intelligence-subtitle">
                  {tx('admin.deploymentOrchestrationPanel.release.subtitle', 'Tracks every deployment, measures post-release impact, auto-rolls back on negative impact.')}
                </Text>
              </div>
              <button
                onClick={runReleaseMonitor}
                disabled={releaseRunning}
                style={{ padding: '8px 12px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: releaseRunning ? `${T.primary}66` : T.primary, color: colors.primaryText, fontSize: 11, fontWeight: '700', cursor: 'pointer' }}
                data-testid="release-intelligence-run-monitor"
              >
                {releaseRunning ? 'Running...' : 'Run Monitor Now'}
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }} data-testid="release-intelligence-summary-grid">
            {[
              { key: 'tracked', label: 'Tracked', value: releaseSummary.tracked_releases || 0, color: T.primary },
              { key: 'stable', label: 'Stable', value: releaseSummary.stable || 0, color: T.successText },
              { key: 'monitoring', label: 'Monitoring', value: releaseSummary.monitoring || 0, color: T.warningText },
              { key: 'rolled_back', label: 'Rolled Back', value: releaseSummary.rolled_back || 0, color: T.error },
            ].map(card => (
              <div key={card.key} style={{ backgroundColor: T.card, borderRadius: 10, border: `1px solid ${T.border}`, padding: 12 }} data-testid={`release-intelligence-card-${card.key}`}>
                <Text style={{ fontSize: 10, color: T.textMuted }}>{card.label}</Text>
                <Text style={{ fontSize: 18, fontWeight: '800', color: card.color }}>{card.value}</Text>
              </div>
            ))}
          </div>

          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, border: `1px solid ${T.border}` }} data-testid="release-intelligence-active-card">
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }} data-testid="release-intelligence-active-title" testID="release-intelligence-active-title">{tx('admin.deploymentOrchestrationPanel.release.activeTitle', 'Active Release')}</Text>
            {!activeRelease ? (
              <Text style={{ fontSize: 11, color: T.textMuted }} data-testid="release-intelligence-no-active" testID="release-intelligence-no-active">{tx('admin.deploymentOrchestrationPanel.release.noActive', 'No active release under monitoring.')}</Text>
            ) : (
              <div style={{ display: 'grid', gap: 8 }} data-testid="release-intelligence-active-content">
                <Text style={{ fontSize: 12, color: T.text }} data-testid="release-intelligence-active-version" testID="release-intelligence-active-version">
                  {activeRelease.version} · {String(activeRelease.status || '').toUpperCase()} · {activeRelease.release_id}
                </Text>
                <Text style={{ fontSize: 10, color: T.textMuted }} data-testid="release-intelligence-active-impact" testID="release-intelligence-active-impact">
                  Error Rate: {activeRelease.latest_metrics?.error_rate_pct ?? 0}% · Latency: {activeRelease.latest_metrics?.avg_latency_ms ?? 0}ms · Auth Failure: {activeRelease.latest_metrics?.auth_failure_rate_pct ?? 0}%
                </Text>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    onClick={() => evaluateRelease(activeRelease.release_id)}
                    disabled={releaseRunning}
                    style={{ fontSize: 10, padding: '6px 10px', borderRadius: 6, border: 'none', backgroundColor: `${T.primary}22`, color: T.primary, fontWeight: '700', cursor: 'pointer' }}
                    data-testid="release-intelligence-evaluate-active"
                  >Evaluate Impact</button>
                  <button
                    onClick={() => forceRollbackRelease(activeRelease.release_id)}
                    disabled={releaseRunning}
                    style={{ fontSize: 10, padding: '6px 10px', borderRadius: 6, border: 'none', backgroundColor: `${T.error}22`, color: T.error, fontWeight: '700', cursor: 'pointer' }}
                    data-testid="release-intelligence-force-rollback-active"
                  >Force Rollback</button>
                </div>
              </div>
            )}
          </div>

          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, border: `1px solid ${T.border}` }} data-testid="release-intelligence-history-card">
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }} data-testid="release-intelligence-history-title" testID="release-intelligence-history-title">{tx('admin.deploymentOrchestrationPanel.release.historyTitle', 'Release Version History')}</Text>
            {recentReleases.length === 0 ? (
              <Text style={{ fontSize: 11, color: T.textMuted }} data-testid="release-intelligence-history-empty" testID="release-intelligence-history-empty">{tx('admin.deploymentOrchestrationPanel.release.historyEmpty', 'No tracked release entries yet.')}</Text>
            ) : recentReleases.slice(0, 8).map((item: any, i: number) => (
              <div key={item.release_id || i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, borderBottom: i < Math.min(7, recentReleases.length - 1) ? `1px solid ${T.border}` : 'none', padding: '8px 0' }} data-testid={`release-intelligence-history-row-${i}`}>
                <div>
                  <Text style={{ fontSize: 12, color: T.text, fontWeight: '700' }} data-testid={`release-intelligence-history-version-${i}`} testID={`release-intelligence-history-version-${i}`}>{item.version} · {item.release_id}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted }} data-testid={`release-intelligence-history-metrics-${i}`} testID={`release-intelligence-history-metrics-${i}`}>
                    err {item.latest_metrics?.error_rate_pct ?? 0}% · lat {item.latest_metrics?.avg_latency_ms ?? 0}ms · auth {item.latest_metrics?.auth_failure_rate_pct ?? 0}%
                  </Text>
                </div>
                <span style={{ fontSize: 10, fontWeight: '700', color: item.status === 'stable' ? T.success : item.status === 'rolled_back' ? T.error : item.status === 'degraded' ? T.warning : T.primary }} data-testid={`release-intelligence-history-status-${i}`}>{String(item.status || 'monitoring').toUpperCase()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </ScrollView>
  );
}
