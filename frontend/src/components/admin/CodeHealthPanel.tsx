import React, { useEffect, useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

function makeC(AC: any) { return {
  bg: AC.bg, card: AC.surfaceElevated, border: AC.border,
  text: AC.text, muted: AC.textMuted, sec: AC.textSec,
  green: AC.success, red: AC.error, blue: AC.primary,
  yellow: AC.warning, purple: AC.purple, cyan: AC.cyan,
}; }

function Badge({ label, color, count }: { label: string; color: string; count: number }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(color, '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
      <Text style={{ color, fontSize: 13, fontWeight: '700' }}>{count}</Text>
      <Text style={{ color: C.sec, fontSize: 11 }}>{label}</Text>
    </View>
  );
}

function TabButton({ active, label, icon, onPress, testId }: { active: boolean; label: string; icon: string; onPress: () => void; testId: string }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  return (
    <TouchableOpacity
      data-testid={testId} testID={testId}
      onPress={onPress}
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 6,
        paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
        backgroundColor: active ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent',
        borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.blue, '40') : C.border,
      }}
    >
      <Ionicons name={icon as any} size={14} color={active ? C.blue : C.muted} />
      <Text style={{ color: active ? C.blue : C.muted, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </TouchableOpacity>
  );
}

function JsScannerTab() {
  const colors = useAdminTheme();
  const [scanning, setScanning] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [scan, setScan] = useState<any>(null);
  const [fixResult, setFixResult] = useState<any>(null);
  const [filter, setFilter] = useState('all');

  const runScan = async () => {
    setScanning(true); setFixResult(null);
    try { const r = await api.get('/admin/code-health/scan'); setScan(r.data); }
    catch (e) { console.error(e); }
    finally { setScanning(false); }
  };
  const runAutoFix = async () => {
    setFixing(true);
    try { const r = await api.post('/admin/code-health/auto-fix'); setFixResult(r.data); runScan(); }
    catch (e) { console.error(e); }
    finally { setFixing(false); }
  };

  const sevC: any = { critical: 'var(--app-error)', medium: 'var(--app-warning)', low: 'var(--app-primary)' };
  const typeIc: any = { TDZ: 'code-slash', MISSING_ERROR_BOUNDARY: 'shield-half', UNSAFE_API_CALL: 'cloud-offline' };
  const filtered = scan?.issues?.filter((i: any) => filter === 'all' || i.severity === filter) || [];

  return (
    <View style={{ gap: 14 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="shield-checkmark" size={18} color={'var(--app-success)'} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{tx('admin.codeHealthPanel.auto.text.001', 'JavaScript / TDZ Scanner')}</Text>
          <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.codeHealthPanel.auto.text.002', 'Detect &amp; auto-fix "Something Went Wrong" TDZ crashes across 439+ frontend files')}</Text>
        </View>
      </View>

      {/* Action Buttons */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TouchableOpacity onPress={runScan} disabled={scanning}
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary, opacity: scanning ? 0.6 : 1 }}
          data-testid="js-scan-btn" testID="js-scan-btn">
          {scanning ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="scan" size={14} color="var(--app-primary-text)" />}
          <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{scanning ? 'Scanning...' : 'Run Full Scan'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={runAutoFix} disabled={fixing || !scan?.auto_fixable}
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: scan?.auto_fixable ? 'var(--app-success)' : C.border, opacity: (fixing || !scan?.auto_fixable) ? 0.5 : 1 }}
          data-testid="js-autofix-btn" testID="js-autofix-btn">
          {fixing ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="hammer" size={14} color={scan?.auto_fixable ? 'var(--app-primary-text)' : C.muted} />}
          <Text style={{ fontSize: 12, fontWeight: '700', color: scan?.auto_fixable ? 'var(--app-primary-text)' : C.muted }}>Auto-Fix ({scan?.auto_fixable || 0})</Text>
        </TouchableOpacity>
      </View>

      {/* Fix Result */}
      {fixResult && (
        <View style={{ padding: 12, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="checkmark-circle" size={14} color={'var(--app-success)'} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.successText }}>Fixed {fixResult.fixed_count} issues — {fixResult.remaining_critical} critical remaining</Text>
          </View>
        </View>
      )}

      {scan && (
        <>
          {/* KPIs */}
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            {[
              { label: 'Files', value: scan.files_scanned, color: colors.primary, icon: 'document-text' },
              { label: 'Critical', value: scan.critical, color: colors.error, icon: 'alert-circle' },
              { label: 'Medium', value: scan.medium, color: colors.warningText, icon: 'warning' },
              { label: 'Low', value: scan.low, color: colors.primary, icon: 'information-circle' },
            ].map(kpi => (
              <View key={kpi.label} style={{ flex: 1, minWidth: 75, padding: 10, borderRadius: 10, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, marginBottom: 4 }}>
                  <Ionicons name={kpi.icon as any} size={10} color={kpi.color} />
                  <Text style={{ fontSize: 8, fontWeight: '700', color: C.muted, textTransform: 'uppercase' }}>{kpi.label}</Text>
                </View>
                <Text style={{ fontSize: 20, fontWeight: '800', color: kpi.value === 0 && kpi.label === 'Critical' ? 'var(--app-success)' : C.text }}>{kpi.value}</Text>
              </View>
            ))}
          </View>

          {/* Status Badge */}
          <View style={{ padding: 14, borderRadius: 12, backgroundColor: scan.critical === 0 ? 'var(--app-success-soft)' : 'var(--app-error-soft)', borderWidth: 1, borderColor: scan.critical === 0 ? 'var(--app-success-soft)' : 'var(--app-error-soft)' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={scan.critical === 0 ? 'shield-checkmark' : 'warning'} size={18} color={scan.critical === 0 ? 'var(--app-success)' : 'var(--app-error)'} />
              <View>
                <Text style={{ fontSize: 13, fontWeight: '800', color: scan.critical === 0 ? 'var(--app-success)' : 'var(--app-error)' }} data-testid="js-scanner-status" testID="js-scanner-status">
                  {scan.critical === 0 ? 'All Clear — No TDZ Crashes' : `${scan.critical} Critical TDZ Issues`}
                </Text>
                <Text style={{ fontSize: 9, color: C.muted, marginTop: 1 }}>
                  {scan.critical === 0 ? 'No "Something Went Wrong" errors will occur from TDZ bugs.' : 'These cause runtime crashes. Click Auto-Fix to resolve.'}
                </Text>
              </View>
            </View>
          </View>

          {/* Filters */}
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {['all', 'critical', 'medium', 'low'].map(f => {
              const active = filter === f;
              const cnt = f === 'all' ? scan.total_issues : f === 'critical' ? scan.critical : f === 'medium' ? scan.medium : scan.low;
              const fc = f === 'all' ? C.text : sevC[f];
              return (
                <TouchableOpacity key={f} onPress={() => setFilter(f)}
                  style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: active ? (globalThis as any).__alphaColor(fc, '15') : 'transparent', borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(fc, '30') : C.border }}
                  data-testid={`js-filter-${f}`} testID={`js-filter-${f}`}>
                  <Text style={{ fontSize: 9, fontWeight: '700', color: active ? fc : C.muted, textTransform: 'uppercase' }}>{f} ({cnt})</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Issues */}
          {filtered.length === 0 ? (
            <View style={{ padding: 24, borderRadius: 12, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
              <Ionicons name="checkmark-done-circle" size={24} color={'var(--app-success)'} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: colors.successText, marginTop: 6 }}>{tx('admin.codeHealthPanel.auto.text.003', 'No issues in this category')}</Text>
            </View>
          ) : filtered.slice(0, 40).map((issue: any, idx: number) => (
            <View key={idx} style={{ padding: 12, borderRadius: 10, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: sevC[issue.severity] || 'var(--app-primary)' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                <Ionicons name={(typeIc[issue.type] || 'bug') as any} size={11} color={sevC[issue.severity]} />
                <Text style={{ fontSize: 9, fontWeight: '800', color: sevC[issue.severity], textTransform: 'uppercase' }}>{issue.type.replace(/_/g, ' ')}</Text>
                <View style={{ flex: 1 }} />
                <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3, backgroundColor: (globalThis as any).__alphaColor(sevC[issue.severity], '15') }}>
                  <Text style={{ fontSize: 7, fontWeight: '700', color: sevC[issue.severity] }}>{issue.severity.toUpperCase()}</Text>
                </View>
                {issue.auto_fixable && (
                  <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3, backgroundColor: colors.successSoft }}>
                    <Text style={{ fontSize: 7, fontWeight: '700', color: colors.successText }}>{tx('admin.codeHealthPanel.auto.text.004', 'AUTO-FIX')}</Text>
                  </View>
                )}
              </View>
              <Text style={{ fontSize: 10, color: C.text, fontWeight: '500' }} numberOfLines={2}>{issue.message}</Text>
              <Text style={{ fontSize: 9, color: colors.primary, fontFamily: 'monospace', marginTop: 3 }}>{issue.file}{issue.line > 0 ? `:${issue.line}` : ''}</Text>
            </View>
          ))}
          {filtered.length > 40 && <Text style={{ fontSize: 9, color: C.muted, textAlign: 'center' }}>+{filtered.length - 40} more</Text>}
        </>
      )}

      {!scan && !scanning && (
        <View style={{ padding: 28, borderRadius: 14, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
          <Ionicons name="shield-checkmark-outline" size={28} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginTop: 8 }}>{tx('admin.codeHealthPanel.auto.text.005', 'Ready to Scan')}</Text>
          <Text style={{ fontSize: 10, color: C.muted, textAlign: 'center', maxWidth: 300, marginTop: 4 }}>{tx('admin.codeHealthPanel.auto.text.006', 'Scans 439+ JS/TS files for TDZ errors, missing error boundaries, and unsafe API calls.')}</Text>
        </View>
      )}
    </View>
  );
}

export default function CodeHealthPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [checking, setChecking] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [gateChecking, setGateChecking] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [lastFixResult, setLastFixResult] = useState<any>(null);
  const [gateResult, setGateResult] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'autofix' | 'history' | 'gate' | 'js-scanner'>('overview');
  const panelTitle = t('codeHealth.header.title');

  const { data: latestData, loading, refetch: refetchLatest } = useLiveQuery('/admin/code-health/latest', { entity: 'code_health', pollInterval: 60000 });
  const { data: trendsData, refetch: refetchTrends } = useLiveQuery('/admin/code-health/trends?days=30', { entity: 'code_health', pollInterval: 60000 });
  const { data: histData, refetch: refetchHist } = useLiveQuery('/admin/code-health/fix-history?limit=20', { entity: 'code_health', pollInterval: 60000 });
  const { data: gateHistData, refetch: refetchGateHist } = useLiveQuery('/admin/code-health/deploy-gate/history?limit=10', { entity: 'code_health', pollInterval: 60000 });

  const trends = trendsData?.trends || [];
  const fixHistory = histData?.history || [];
  const gateHistory = gateHistData?.history || [];

  useEffect(() => { if (latestData?.has_report) setReport(latestData); }, [latestData]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (gateHistory.length > 0 && !gateResult) setGateResult(gateHistory[0]); }, [gateHistory]);

  const runCheck = useCallback(async () => {
    setChecking(true);
    try {
      const res = await api.get('/admin/code-health/check');
      setReport({ ...res.data, has_report: true });
      await refetchTrends();
    } catch (e) { console.error(e); }
    setChecking(false);
  }, [refetchTrends]);

  const runAutoFix = useCallback(async () => {
    setFixing(true);
    setLastFixResult(null);
    try {
      const res = await api.post('/admin/code-health/auto-fix');
      setLastFixResult(res.data);
      await Promise.all([refetchLatest(), refetchTrends(), refetchHist()]);
    } catch (e) { console.error(e); }
    setFixing(false);
  }, [refetchLatest, refetchTrends, refetchHist]);

  const runGateCheck = useCallback(async () => {
    setGateChecking(true);
    try {
      const res = await api.get('/admin/code-health/deploy-gate');
      setGateResult(res.data);
      await refetchGateHist();
    } catch (e) { console.error(e); }
    setGateChecking(false);
  }, [refetchGateHist]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
      <AutoFixBanner domain="ops" />
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, marginTop: 12 }}>{tx('codeHealth.states.loading', 'Loading code health...')}</Text>
      </View>
    );
  }

  const maxTrend = Math.max(...trends.map(t => t.total_issues || 0), 1);

  return (
    <ScrollView data-testid="code-health-panel" testID="code-health-panel" style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 16 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{panelTitle === 'codeHealth.header.title' ? 'Code Health' : panelTitle}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{tx('codeHealth.header.subtitle', 'Automated linting, auto-fix & alerts — runs daily at 6 AM UTC')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity
            data-testid="run-check-btn" testID="run-check-btn"
            onPress={runCheck}
            disabled={checking || fixing}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: (globalThis as any).__alphaColor(checking ? C.border : C.green, '20'),
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(checking ? C.border : C.green, '40'),
            }}
          >
            {checking ? <ActivityIndicator size="small" color={C.green} /> : <Ionicons name="play" size={14} color={C.green} />}
            <Text style={{ color: checking ? C.muted : C.green, fontSize: 12, fontWeight: '700' }}>
              {checking ? tx('codeHealth.actions.running', 'Running...') : tx('codeHealth.actions.runCheck', 'Run Check')}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            data-testid="auto-fix-btn" testID="auto-fix-btn"
            onPress={runAutoFix}
            disabled={fixing || checking}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: (globalThis as any).__alphaColor(fixing ? C.border : C.purple, '20'),
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(fixing ? C.border : C.purple, '40'),
            }}
          >
            {fixing ? <ActivityIndicator size="small" color={C.purpleText} /> : <Ionicons name="build" size={14} color={C.purpleText} />}
            <Text style={{ color: fixing ? C.muted : C.purple, fontSize: 12, fontWeight: '700' }}>
              {fixing ? tx('codeHealth.actions.fixing', 'Fixing...') : tx('codeHealth.actions.autoFix', 'Auto-Fix')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        <TabButton active={activeTab === 'overview'} label={tx('codeHealth.tabs.overview', 'Overview')} icon="pulse" onPress={() => setActiveTab('overview')} testId="tab-overview" />
        <TabButton active={activeTab === 'autofix'} label={tx('codeHealth.tabs.autoFix', 'Auto-Fix')} icon="build" onPress={() => setActiveTab('autofix')} testId="tab-autofix" />
        <TabButton active={activeTab === 'history'} label={tx('codeHealth.tabs.fixHistory', 'Fix History')} icon="time" onPress={() => setActiveTab('history')} testId="tab-history" />
        <TabButton active={activeTab === 'gate'} label={tx('codeHealth.tabs.deployGate', 'Deploy Gate')} icon="shield-checkmark" onPress={() => setActiveTab('gate')} testId="tab-gate" />
        <TabButton active={activeTab === 'js-scanner'} label={tx('codeHealth.tabs.jsScanner', 'JS/TDZ Scanner')} icon="code-slash" onPress={() => setActiveTab('js-scanner')} testId="tab-js-scanner" />
      </View>

      {/* ── Auto-Fix Result Banner ── */}
      {lastFixResult && (
        <View data-testid="fix-result-banner" testID="fix-result-banner" style={{
          padding: 16, borderRadius: 12,
          backgroundColor: lastFixResult.total_fixed > 0 ? (globalThis as any).__alphaColor(C.purple, '10') : C.blue + '10',
          borderWidth: 1, borderColor: lastFixResult.total_fixed > 0 ? (globalThis as any).__alphaColor(C.purple, '30') : C.blue + '30',
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.purple, '20') }}>
              <Ionicons name="checkmark-done" size={18} color={C.purpleText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>
                Auto-Fix Complete — {lastFixResult.total_fixed} issue{lastFixResult.total_fixed !== 1 ? 's' : ''} fixed
              </Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                {lastFixResult.before_issues} → {lastFixResult.after_issues} issues ({lastFixResult.issues_reduced} reduced)
              </Text>
            </View>
            <TouchableOpacity accessibilityLabel={tx('admin.codeHealthPanel.auto.accessibility.001', 'Safe Fixes')} onPress={() => setLastFixResult(null)}>
              <Ionicons name="close" size={18} color={C.muted} />
            </TouchableOpacity>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.007', 'Safe Fixes')}</Text>
              <Text style={{ color: C.green, fontSize: 18, fontWeight: '800' }}>{lastFixResult.safe_fixed}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.008', 'Unsafe Fixes')}</Text>
              <Text style={{ color: C.yellow, fontSize: 18, fontWeight: '800' }}>{lastFixResult.unsafe_fixed}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.009', 'Bare Except')}</Text>
              <Text style={{ color: C.cyan, fontSize: 18, fontWeight: '800' }}>{lastFixResult.bare_except_fixed}</Text>
            </View>
          </View>
        </View>
      )}

      {/* ════════ OVERVIEW TAB ════════ */}
      {activeTab === 'overview' && (
        <>
          {/* Status Banner */}
          {report && (
            <View data-testid="health-status-banner" testID="health-status-banner" style={{
              flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 12,
              backgroundColor: report.critical_passed ? (globalThis as any).__alphaColor(C.green, '10') : C.red + '10',
              borderWidth: 1, borderColor: report.critical_passed ? (globalThis as any).__alphaColor(C.green, '30') : C.red + '30',
            }}>
              <View style={{
                width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center',
                backgroundColor: report.critical_passed ? (globalThis as any).__alphaColor(C.green, '20') : C.red + '20',
              }}>
                <Ionicons name={report.critical_passed ? 'shield-checkmark' : 'warning'} size={20} color={report.critical_passed ? C.green : C.red} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: report.critical_passed ? C.green : C.red, fontSize: 15, fontWeight: '700' }}>
                  {report.critical_passed ? 'Critical Checks Passed' : 'Critical Issues Found'}
                </Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                  {report.total_issues} total issues | Last checked: {new Date(report.timestamp).toLocaleString()}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <Badge label="errors" color={C.red} count={report.error_count} />
                <Badge label="warnings" color={C.yellow} count={report.warning_count} />
              </View>
            </View>
          )}

          {/* Summary Cards */}
          {report && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {[
                { label: 'Total Issues', value: report.total_issues, icon: 'code-slash', color: C.blue },
                { label: 'Errors (F-rules)', value: report.error_count, icon: 'alert-circle', color: C.red },
                { label: 'Warnings (E-rules)', value: report.warning_count, icon: 'information-circle', color: C.yellow },
                { label: 'Critical', value: report.critical_issues, icon: 'shield', color: report.critical_passed ? C.green : C.red },
              ].map(c => (
                <View key={c.label} data-testid={`stat-${c.label.toLowerCase().replace(/\s+/g, '-')}`} testID={`stat-${c.label.toLowerCase().replace(/\s+/g, '-')}`} style={{ flex: 1, minWidth: 140, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ color: C.sec, fontSize: 11, fontWeight: '600', textTransform: 'uppercase' }}>{c.label}</Text>
                    <Ionicons name={c.icon as any} size={14} color={c.color} />
                  </View>
                  <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{c.value}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Trends Chart */}
          {trends.length > 1 && (
            <View data-testid="health-trends-chart" testID="health-trends-chart" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.codeHealthPanel.auto.text.010', 'Issue Trend (Last 30 Days)')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 100, gap: 4 }}>
                {trends.map((t, i) => {
                  const h = maxTrend > 0 ? ((t.total_issues || 0) / maxTrend) * 100 : 0;
                  const isLatest = i === trends.length - 1;
                  return (
                    <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                      <Text style={{ color: C.muted, fontSize: 9, marginBottom: 2 }}>{t.total_issues}</Text>
                      <View style={{
                        width: '80%', height: `${Math.max(h, 3)}%`, minHeight: 3, borderRadius: 3,
                        backgroundColor: isLatest ? C.blue : (t.critical_passed ? C.green : C.red),
                      }} />
                      <Text style={{ color: C.muted, fontSize: 7, marginTop: 3 }}>
                        {new Date(t.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* Category Breakdown */}
          {report?.categories?.length > 0 && (
            <View data-testid="category-breakdown" testID="category-breakdown" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.011', 'Issue Breakdown')}</Text>
              </View>
              <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.012', 'CODE')}</Text>
                <Text style={{ flex: 3, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.013', 'DESCRIPTION')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.014', 'SEVERITY')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'right' }}>{tx('admin.codeHealthPanel.auto.text.015', 'COUNT')}</Text>
              </View>
              {report.categories.map((cat: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.cyan, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{cat.code}</Text>
                  </View>
                  <View style={{ flex: 3 }}>
                    <Text style={{ color: C.sec, fontSize: 12 }} numberOfLines={1}>{cat.name}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{
                      paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
                      backgroundColor: cat.severity === 'error' ? (globalThis as any).__alphaColor(C.red, '18') : C.yellow + '18',
                    }}>
                      <Text style={{ color: cat.severity === 'error' ? C.red : C.yellow, fontSize: 10, fontWeight: '600' }}>
                        {cat.severity}
                      </Text>
                    </View>
                  </View>
                  <View style={{ flex: 1, alignItems: 'flex-end' }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{cat.count}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </>
      )}

      {/* ════════ AUTO-FIX TAB ════════ */}
      {activeTab === 'autofix' && (
        <>
          {/* Automation Info Card */}
          <View data-testid="automation-info" testID="automation-info" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.purple, '20') }}>
                <Ionicons name="cog" size={18} color={C.purpleText} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.016', 'Automated Code Health Engine')}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{tx('admin.codeHealthPanel.auto.text.017', 'Runs daily at 6:00 AM UTC via APScheduler')}</Text>
              </View>
            </View>

            <View style={{ gap: 10 }}>
              {[
                { icon: 'search', color: C.blue, title: 'Scan', desc: 'Runs ruff lint on entire backend codebase' },
                { icon: 'build', color: C.purpleText, title: 'Auto-Fix', desc: 'Applies safe + unsafe fixes (F541, E401, F841, F401) and bare-except patches' },
                { icon: 'analytics', color: C.green, title: 'Re-scan', desc: 'Measures before/after to track improvement' },
                { icon: 'mail', color: C.cyan, title: 'Email Alert', desc: 'Sends detailed report to platform admins via Resend' },
                { icon: 'server', color: C.yellow, title: 'Store', desc: 'Saves report & fix history to MongoDB for trend tracking' },
              ].map((step, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(step.color, '18') }}>
                    <Ionicons name={step.icon as any} size={14} color={step.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{i + 1}. {step.title}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{step.desc}</Text>
                  </View>
                  {i < 4 && (
                    <Ionicons name="arrow-down" size={12} color={C.border} style={{ position: 'absolute', left: 7, bottom: -12 }} />
                  )}
                </View>
              ))}
            </View>
          </View>

          {/* Fixable Rules Reference */}
          <View data-testid="fixable-rules" testID="fixable-rules" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
            <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.018', 'Auto-Fixable Rules')}</Text>
            </View>
            {[
              { code: 'F541', name: 'f-string without placeholders', type: 'Safe', color: C.green },
              { code: 'E401', name: 'Multiple imports on one line', type: 'Safe', color: C.green },
              { code: 'F841', name: 'Unused variable assignment', type: 'Unsafe', color: C.yellow },
              { code: 'F401', name: 'Unused import', type: 'Unsafe', color: C.yellow },
              { code: 'E722', name: 'Bare except (→ except Exception)', type: 'Regex', color: C.cyan },
            ].map((rule, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 1, color: C.cyan, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{rule.code}</Text>
                <Text style={{ flex: 3, color: C.sec, fontSize: 12 }}>{rule.name}</Text>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(rule.color, '18') }}>
                    <Text style={{ color: rule.color, fontSize: 10, fontWeight: '600' }}>{rule.type}</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>

          {/* Critical (non-fixable) rules */}
          <View data-testid="critical-rules" testID="critical-rules" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
            <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.019', 'Critical Rules (Manual Review Required)')}</Text>
            </View>
            {[
              { code: 'F821', name: 'Undefined name', severity: 'critical' },
              { code: 'F811', name: 'Redefined while unused', severity: 'critical' },
              { code: 'F601', name: 'Duplicate dict key', severity: 'critical' },
              { code: 'E722', name: 'Bare except (if regex fails)', severity: 'high' },
            ].map((rule, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 1, color: C.red, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{rule.code}</Text>
                <Text style={{ flex: 3, color: C.sec, fontSize: 12 }}>{rule.name}</Text>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '18') }}>
                    <Text style={{ color: C.red, fontSize: 10, fontWeight: '600' }}>{rule.severity}</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>
        </>
      )}

      {/* ════════ HISTORY TAB ════════ */}
      {activeTab === 'history' && (
        <>
          {fixHistory.length > 0 ? (
            <View data-testid="fix-history-table" testID="fix-history-table" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.020', 'Fix History')}</Text>
                <Text style={{ color: C.muted, fontSize: 11 }}>{fixHistory.length} runs</Text>
              </View>
              {/* Header */}
              <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.021', 'DATE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.022', 'SOURCE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.023', 'BEFORE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.024', 'AFTER')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.025', 'FIXED')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.026', 'REDUCED')}</Text>
              </View>
              {fixHistory.map((fix: any, i: number) => (
                <View key={i} data-testid={`fix-row-${i}`} testID={`fix-row-${i}`} style={{
                  flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10,
                  borderBottomWidth: 1, borderBottomColor: C.border,
                  backgroundColor: (globalThis as any).__alphaColor(i % 2 === 0 ? 'transparent' : C.bg, '50'),
                }}>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: C.sec, fontSize: 11 }}>{new Date(fix.timestamp).toLocaleString()}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{
                      paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
                      backgroundColor: fix.source === 'scheduled' ? (globalThis as any).__alphaColor(C.cyan, '18') : C.purple + '18',
                    }}>
                      <Text style={{ color: fix.source === 'scheduled' ? C.cyan : C.purple, fontSize: 10, fontWeight: '600' }}>
                        {fix.source}
                      </Text>
                    </View>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: C.sec, fontSize: 12, fontWeight: '600' }}>{fix.before_issues}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{fix.after_issues}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: C.green, fontSize: 12, fontWeight: '800' }}>{fix.total_fixed}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: fix.issues_reduced > 0 ? C.green : C.muted, fontSize: 12, fontWeight: '700' }}>
                      {fix.issues_reduced > 0 ? `-${fix.issues_reduced}` : '0'}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="time-outline" size={40} color={C.muted} />
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', marginTop: 12 }}>{tx('admin.codeHealthPanel.auto.text.027', 'No Fix History Yet')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.028', 'Click "Auto-Fix" or wait for the daily scheduled run to generate fix history.')}</Text>
            </View>
          )}

          {/* Latest Fix Detail (if exists) */}
          {fixHistory.length > 0 && (
            <View data-testid="latest-fix-detail" testID="latest-fix-detail" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.codeHealthPanel.auto.text.029', 'Latest Fix Breakdown')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                {[
                  { label: 'Safe Fixes', value: fixHistory[0]?.safe_fixed ?? 0, color: C.green },
                  { label: 'Unsafe Fixes', value: fixHistory[0]?.unsafe_fixed ?? 0, color: C.yellow },
                  { label: 'Bare Except', value: fixHistory[0]?.bare_except_fixed ?? 0, color: C.cyan },
                  { label: 'Critical Before', value: fixHistory[0]?.critical_before ?? 0, color: C.red },
                  { label: 'Critical After', value: fixHistory[0]?.critical_after ?? 0, color: fixHistory[0]?.critical_after === 0 ? C.green : C.red },
                ].map((s, i) => (
                  <View key={i} style={{ flex: 1, minWidth: 100, backgroundColor: C.bg, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{s.label}</Text>
                    <Text style={{ color: s.color, fontSize: 18, fontWeight: '800', marginTop: 4 }}>{s.value}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </>
      )}

      {/* ════════ DEPLOY GATE TAB ════════ */}
      {activeTab === 'gate' && (
        <>
          {/* Gate Status Banner */}
          <View data-testid="deploy-gate-status" testID="deploy-gate-status" style={{
            flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 12,
            backgroundColor: gateResult?.passed ? (globalThis as any).__alphaColor(C.green, '10') : gateResult ? C.red + '10' : C.card,
            borderWidth: 1, borderColor: gateResult?.passed ? (globalThis as any).__alphaColor(C.green, '30') : gateResult ? C.red + '30' : C.border,
          }}>
            <View style={{
              width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center',
              backgroundColor: gateResult?.passed ? (globalThis as any).__alphaColor(C.green, '20') : gateResult ? C.red + '20' : C.border,
            }}>
              <Ionicons
                name={gateResult?.passed ? 'rocket' : gateResult ? 'close-circle' : 'help-circle'}
                size={24}
                color={gateResult?.passed ? C.green : gateResult ? C.red : C.muted}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{
                color: gateResult?.passed ? C.green : gateResult ? C.red : C.text,
                fontSize: 16, fontWeight: '800',
              }}>
                {gateResult?.passed ? 'Deploy Gate: PASSED' : gateResult ? `Deploy Gate: BLOCKED (${gateResult.blocker_count} issues)` : 'Deploy Gate: Not Checked'}
              </Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                {gateResult?.timestamp
                  ? `Last checked: ${new Date(gateResult.timestamp).toLocaleString()}`
                  : 'Run a gate check to verify deployment readiness'}
              </Text>
            </View>
            <TouchableOpacity
              data-testid="run-gate-check-btn" testID="run-gate-check-btn"
              onPress={runGateCheck}
              disabled={gateChecking}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                backgroundColor: (globalThis as any).__alphaColor(gateChecking ? C.border : C.blue, '20'),
                borderWidth: 1, borderColor: (globalThis as any).__alphaColor(gateChecking ? C.border : C.blue, '40'),
              }}
            >
              {gateChecking ? <ActivityIndicator size="small" color={C.blue} /> : <Ionicons name="shield-checkmark" size={14} color={C.blue} />}
              <Text style={{ color: gateChecking ? C.muted : C.blue, fontSize: 12, fontWeight: '700' }}>
                {gateChecking ? 'Checking...' : 'Run Gate Check'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* What the gate checks */}
          <View data-testid="gate-rules-info" testID="gate-rules-info" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.red, '20') }}>
                <Ionicons name="lock-closed" size={18} color={C.red} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.030', 'Deployment Blockers')}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{tx('admin.codeHealthPanel.auto.text.031', 'These critical issues will block deployment')}</Text>
              </View>
            </View>
            {[
              { code: 'F821', name: 'Undefined name', desc: 'Using a variable/function that doesn\'t exist — guaranteed runtime crash' },
              { code: 'F811', name: 'Redefined while unused', desc: 'A function/variable is redefined before being used — logic error' },
              { code: 'F601', name: 'Duplicate dict key', desc: 'Same key appears twice in a dictionary — data silently lost' },
            ].map((rule, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: i < 2 ? 12 : 0 }}>
                <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.red, '18'), marginTop: 2 }}>
                  <Text style={{ color: C.red, fontSize: 10, fontWeight: '800' }}>{rule.code}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{rule.name}</Text>
                  <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{rule.desc}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Blockers List (when gate failed) */}
          {gateResult && !gateResult.passed && gateResult.blockers?.length > 0 && (
            <View data-testid="gate-blockers-list" testID="gate-blockers-list" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30'), overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: (globalThis as any).__alphaColor(C.red, '08') }}>
                <Text style={{ color: C.red, fontSize: 14, fontWeight: '700' }}>Blocking Issues ({gateResult.blocker_count})</Text>
              </View>
              <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.032', 'CODE')}</Text>
                <Text style={{ flex: 3, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.033', 'FILE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.034', 'LINE')}</Text>
                <Text style={{ flex: 3, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.035', 'MESSAGE')}</Text>
              </View>
              {gateResult.blockers.map((b: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <Text style={{ flex: 1, color: C.red, fontSize: 12, fontWeight: '700', fontFamily: 'monospace' }}>{b.code}</Text>
                  <Text style={{ flex: 3, color: C.cyan, fontSize: 11 }} numberOfLines={1}>{b.file}</Text>
                  <Text style={{ flex: 1, color: C.sec, fontSize: 11, textAlign: 'center' }}>{b.line}</Text>
                  <Text style={{ flex: 3, color: C.sec, fontSize: 11 }} numberOfLines={1}>{b.message}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Gate Check History */}
          {gateHistory.length > 0 && (
            <View data-testid="gate-history" testID="gate-history" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.codeHealthPanel.auto.text.036', 'Gate Check History')}</Text>
              </View>
              {gateHistory.map((g: any, i: number) => (
                <View key={i} data-testid={`gate-row-${i}`} testID={`gate-row-${i}`} style={{
                  flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10,
                  borderBottomWidth: 1, borderBottomColor: C.border,
                }}>
                  <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: g.passed ? (globalThis as any).__alphaColor(C.green, '18') : C.red + '18', marginRight: 12 }}>
                    <Ionicons name={g.passed ? 'checkmark' : 'close'} size={14} color={g.passed ? C.green : C.red} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: g.passed ? C.green : C.red, fontSize: 12, fontWeight: '700' }}>
                      {g.passed ? 'PASSED' : `BLOCKED (${g.blocker_count} issues)`}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{new Date(g.timestamp).toLocaleString()}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </>
      )}

      {/* No report state */}
      {!report && activeTab === 'overview' && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="code-slash-outline" size={40} color={C.muted} />
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', marginTop: 12 }}>{tx('admin.codeHealthPanel.auto.text.037', 'No Reports Yet')}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.codeHealthPanel.auto.text.038', 'Click "Run Check" to generate your first code health report.')}</Text>
        </View>
      )}

      {/* ── JS/TDZ Scanner Tab ── */}
      {activeTab === 'js-scanner' && <JsScannerTab />}
    </ScrollView>
  );
}
