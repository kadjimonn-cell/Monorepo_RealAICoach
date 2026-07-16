import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity, TextInput } from 'react-native';
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

// Module-scope theme-aware palette (CSS-var-backed) so module-scope helpers
// (sevColor, etc.) resolve correctly in both light and dark modes.
const T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)',
  purple: 'var(--app-primary)', cyan: 'var(--app-primary)' as any,
};

type Tab = 'dashboard' | 'new-incident' | 'history';

export default function AIRemediationPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<Tab>('dashboard');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [form, setForm] = useState({ title: '', description: '', severity: 'medium', affected_services: '', error_logs: '' });

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, hRes] = await Promise.all([
        api.get('/admin/ai-remediation/dashboard'),
        api.get('/admin/ai-remediation/history?limit=10'),
      ]);
      setDashboard(dRes.data);
      setHistory(hRes.data.remediations || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/ai-remediation/hybrid-refresh',
    onTick: fetchDashboard,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const analyzeIncident = async () => {
    if (!form.title || !form.description) return;
    setAnalyzing(true);
    try {
      const res = await api.post('/admin/ai-remediation/analyze', {
        title: form.title, description: form.description, severity: form.severity,
        affected_services: form.affected_services.split(',').map((s: string) => s.trim()).filter(Boolean),
        error_logs: form.error_logs || null,
      });
      setCurrentPlan(res.data);
      setTab('dashboard');
      fetchDashboard();
    } catch (e) { console.error(e); }
    finally { setAnalyzing(false); }
  };

  const executePlan = async (remediationId: string) => {
    setExecuting(true);
    try {
      const res = await api.post('/admin/ai-remediation/execute', { remediation_id: remediationId, steps_to_execute: [] });
      setCurrentPlan((prev: any) => prev?.remediation_id === remediationId ? { ...prev, ...res.data } : prev);
      fetchDashboard();
    } catch (e) { console.error(e); }
    finally { setExecuting(false); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="ai-remediation-loading" testID="ai-remediation-loading">
      <AutoFixBanner domain="ai_resolution" />
      <ActivityIndicator size="large" color={T.purpleText} />
      <Text style={{ color: T.textSec, marginTop: 12 }}>{tx('admin.aiRemediationPanel.states.loading', 'Loading remediation dashboard...')}</Text>
    </View>
  );

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: 'pulse' },
    { id: 'new-incident', label: 'Report Incident', icon: 'add-circle' },
    { id: 'history', label: `History (${history.length})`, icon: 'time' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} data-testid="ai-remediation-panel" testID="ai-remediation-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${T.purple}22`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="medkit" size={22} color={T.purpleText} />
        </View>
        <View>
          <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.aiRemediationPanel.header.title', 'AI Auto-Remediation')}</Text>
          <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.aiRemediationPanel.header.subtitle', 'Multi-Step Incident Analysis & Fix (GPT-4o)')}</Text>
        </View>
      </View>

      {/* Stats */}
      {dashboard && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
          <StatCard label="Total" value={dashboard.total_remediations} color={T.primary} />
          <StatCard label="Completed" value={dashboard.completed} color={T.successText} />
          <StatCard label="Partial" value={dashboard.partial} color={T.warningText} />
          <StatCard label="Success Rate" value={`${dashboard.success_rate}%`} color={dashboard.success_rate >= 80 ? T.success : T.warning} />
        </View>
      )}

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity key={t.id} data-testid={`remediation-tab-${t.id}`} testID={`remediation-tab-${t.id}`} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(T.purple, '20') : T.card, borderWidth: 1, borderColor: tab === t.id ? (globalThis as any).__alphaColor(T.purple, '40') : T.border }}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? T.purple : T.textMuted} />
            <Text style={{ color: tab === t.id ? T.purple : T.textSec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'dashboard' && currentPlan && (
        <View data-testid="remediation-current-plan" testID="remediation-current-plan" style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '40') }}>
          <Text style={{ color: T.purpleText, fontWeight: '700', fontSize: 14, marginBottom: 8 }}>{tx('admin.aiRemediationPanel.dashboard.latestPlan', 'Latest Remediation Plan')}</Text>
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{currentPlan.incident?.title}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>Root Cause: {currentPlan.plan?.root_cause}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 2 }}>Impact: {currentPlan.plan?.impact_assessment}</Text>

          <View style={{ marginTop: 12, gap: 6 }}>
            {currentPlan.plan?.steps?.map((step: any, i: number) => {
              const exec = currentPlan.executed_steps?.find((e: any) => e.step_order === step.order);
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: T.bg, borderRadius: 8, padding: 10 }}>
                  <View style={{ width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: exec?.status === 'success' || exec?.status === 'verified' ? (globalThis as any).__alphaColor(T.success, '20') : exec?.status === 'failed' ? T.error + '20' : T.textMuted + '20' }}>
                    <Text style={{ color: exec?.status === 'success' || exec?.status === 'verified' ? T.success : exec?.status === 'failed' ? T.error : T.textMuted, fontSize: 11, fontWeight: '700' }}>{step.order}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{step.action}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>{step.description}</Text>
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{step.type}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{step.estimated_duration_min}min</Text>
                    </View>
                    {exec?.output && <Text style={{ color: T.cyan, fontSize: 10, marginTop: 4, fontFamily: 'monospace' }}>{exec.output.substring(0, 200)}</Text>}
                  </View>
                </View>
              );
            })}
          </View>

          {currentPlan.status === 'pending' && (
            <TouchableOpacity data-testid="remediation-execute-btn" testID="remediation-execute-btn" onPress={() => executePlan(currentPlan.remediation_id)} disabled={executing}
              style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.purple, borderRadius: 8, paddingVertical: 10, marginTop: 12, opacity: executing ? 0.6 : 1 }}>
              {executing ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="play" size={16} color="var(--app-primary-text)" />}
              <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 13 }}>{executing ? 'Executing...' : 'Execute All Steps'}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {tab === 'new-incident' && (
        <View data-testid="remediation-form" testID="remediation-form" style={{ gap: 12 }}>
          <InputField label="Incident Title" value={form.title} onChange={(v: string) => setForm({ ...form, title: v })} placeholder={tx('admin.aiRemediationPanel.form.incidentTitlePlaceholder', 'e.g. API response times > 5s')} testId="incident-title-input" />
          <InputField label="Description" value={form.description} onChange={(v: string) => setForm({ ...form, description: v })} placeholder={tx('admin.aiRemediationPanel.form.descriptionPlaceholder', 'Describe the issue in detail...')} multiline testId="incident-desc-input" />
          <InputField label="Affected Services (comma-separated)" value={form.affected_services} onChange={(v: string) => setForm({ ...form, affected_services: v })} placeholder={tx('admin.aiRemediationPanel.form.affectedServicesPlaceholder', 'backend, database, auth')} testId="incident-services-input" />
          <InputField label="Error Logs (optional)" value={form.error_logs} onChange={(v: string) => setForm({ ...form, error_logs: v })} placeholder={tx('admin.aiRemediationPanel.form.errorLogsPlaceholder', 'Paste error logs...')} multiline testId="incident-logs-input" />

          <View style={{ flexDirection: 'row', gap: 8 }}>
            {['low', 'medium', 'high', 'critical'].map(s => (
              <TouchableOpacity key={s} data-testid={`severity-${s}`} testID={`severity-${s}`} onPress={() => setForm({ ...form, severity: s })}
                style={{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                  backgroundColor: form.severity === s ? (globalThis as any).__alphaColor(sevColor(s), '20') : T.card, borderWidth: 1, borderColor: form.severity === s ? sevColor(s) : T.border }}>
                <Text style={{ color: form.severity === s ? sevColor(s) : T.textMuted, fontSize: 11, fontWeight: '600' }}>{s.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity data-testid="analyze-incident-btn" testID="analyze-incident-btn" onPress={analyzeIncident} disabled={analyzing || !form.title || !form.description}
            style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.purple, borderRadius: 8, paddingVertical: 12, opacity: analyzing ? 0.6 : 1 }}>
            {analyzing ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="flash" size={18} color="var(--app-primary-text)" />}
            <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 14 }}>{analyzing ? 'AI Analyzing...' : 'Analyze with AI'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {tab === 'history' && (
        <View data-testid="remediation-history" testID="remediation-history" style={{ gap: 10 }}>
          {history.length === 0 ? (
            <View style={{ padding: 30, alignItems: 'center' }}>
              <Ionicons name="document-text-outline" size={40} color={T.textMuted} />
              <Text style={{ color: T.textSec, marginTop: 10, fontWeight: '600' }}>{tx('admin.aiRemediationPanel.history.empty', 'No Remediation History')}</Text>
            </View>
          ) : history.map((r: any, i: number) => (
            <TouchableOpacity key={i} accessibilityLabel="r.incident?.title" onPress={() => { setCurrentPlan(r); setTab('dashboard'); }}
              style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{r.incident?.title}</Text>
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                  backgroundColor: r.status === 'completed' ? (globalThis as any).__alphaColor(T.success, '20') : r.status === 'partial' ? T.warning + '20' : T.textMuted + '20' }}>
                  <Text style={{ color: r.status === 'completed' ? T.success : r.status === 'partial' ? T.warning : T.textMuted, fontSize: 10, fontWeight: '600' }}>{r.status}</Text>
                </View>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{r.incident?.severity} | {r.plan?.steps?.length || 0} steps | {r.created_at ? new Date(r.created_at).toLocaleString() : ''}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function StatCard({ label, value, color }: any) {
  return (
    <View style={{ flex: 1, minWidth: 80, backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
      <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10 }}>{label}</Text>
    </View>
  );
}

function InputField({ label, value, onChange, placeholder, multiline, testId }: any) {
  return (
    <View>
      <Text style={{ color: T.text, fontWeight: '600', fontSize: 12, marginBottom: 4 }}>{label}</Text>
      <TextInput data-testid={testId} testID={testId} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={T.textMuted}
        multiline={multiline} numberOfLines={multiline ? 3 : 1}
        style={{ backgroundColor: T.bg, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: T.text, fontSize: 13, borderWidth: 1, borderColor: T.border, minHeight: multiline ? 70 : 40 }} />
    </View>
  );
}

function sevColor(s: string) { return s === 'critical' ? T.error : s === 'high' ? T.warning : s === 'medium' ? T.primary : T.textMuted; }
