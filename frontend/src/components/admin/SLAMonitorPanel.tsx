import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import api from '../../services/api';

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
  primaryText: AC.primaryText || 'var(--app-primary-text)',
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

interface Props { colors: any; }

export default function SLAMonitorPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data, loading } = useLiveQuery('/admin/sla/dashboard', { entity: 'sla', pollInterval: 30000 });
  const [view, setView] = useState<'overview' | 'at-risk' | 'escalated' | 'ai-insights'>('overview');
  const [aiData, setAiData] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);

  const runAiAnalysis = useCallback(async () => {
    setAiLoading(true);
    try {
      const cached = await api.get('/admin/ai-insights/latest/sla_predictor');
      if (cached.data && cached.data.risk_score !== undefined) { setAiData(cached.data); setAiLoading(false); return; }
      const res = await api.post('/admin/ai-insights/sla-predictor');
      setAiData(res.data);
    } catch { setAiData(null); }
    setAiLoading(false);
  }, []);

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.sLAMonitorPanel.auto.text.001', 'Failed to load SLA data')}</Text>;

  const { overview, sla_config, at_risk_tickets, escalated_tickets } = data;

  const complianceColor = overview.sla_compliance_pct >= 90 ? T.success : overview.sla_compliance_pct >= 70 ? T.warning : T.error;

  return (
    <View data-testid="sla-monitor-panel" testID="sla-monitor-panel">
      <View style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="sla-monitor-title" testID="sla-monitor-title">{tx('admin.sLAMonitorPanel.auto.text.002', 'SLA Monitor')}</Text>
        <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>Automated ticket escalation engine | SLA: {sla_config.escalation_hours}h response target</Text>
      </View>

      {/* View Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16, flexWrap: 'wrap' }} data-testid="sla-view-tabs" testID="sla-view-tabs">
        {([
          { id: 'overview', label: 'Dashboard', icon: 'grid' },
          { id: 'at-risk', label: `At Risk (${at_risk_tickets?.length || 0})`, icon: 'alert-circle' },
          { id: 'escalated', label: `Escalated (${escalated_tickets?.length || 0})`, icon: 'flame' },
          { id: 'ai-insights', label: 'AI Predictor', icon: 'sparkles' },
        ] as const).map(t => (
          <TouchableOpacity key={t.id} onPress={() => setView(t.id as any)} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
            borderRadius: 10, backgroundColor: view === t.id ? T.primary : T.bgSoft,
          }} data-testid={`sla-tab-${t.id}`} testID={`sla-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={view === t.id ? T.primaryText : T.textSec} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: view === t.id ? T.primaryText : T.textSec }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {view === 'overview' && (
        <View style={{ gap: 16 }}>
          {/* SLA Compliance Gauge */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center' }} data-testid="sla-compliance-card" testID="sla-compliance-card">
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', marginBottom: 8 }}>{tx('admin.sLAMonitorPanel.auto.text.003', 'SLA COMPLIANCE RATE')}</Text>
            <View style={{ width: 120, height: 120, borderRadius: 60, borderWidth: 6, borderColor: (globalThis as any).__alphaColor(complianceColor, '30'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
              <Text style={{ color: complianceColor, fontSize: 32, fontWeight: '900' }}>{overview.sla_compliance_pct}%</Text>
            </View>
            <Text style={{ color: T.textSec, fontSize: 11 }}>Target: Respond within {sla_config.escalation_hours}h</Text>
          </View>

          {/* KPI Grid */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }} data-testid="sla-kpis" testID="sla-kpis">
            <SLAKPI icon="document-text" color={T.primary} label="Open Tickets" value={overview.total_open} />
            <SLAKPI icon="flame" color={T.error} label="Escalated" value={overview.total_escalated} />
            <SLAKPI icon="flame" color={T.warningText} label="Escalated (7d)" value={overview.escalated_7d} />
            <SLAKPI icon="alert-circle" color={T.warningText} label="At Risk" value={overview.at_risk} />
            <SLAKPI icon="checkmark-circle" color={T.successText} label="Resolved" value={overview.total_resolved} />
            <SLAKPI icon="time" color={T.cyan} label="Avg Response (h)" value={overview.avg_response_hours} />
          </View>

          {/* Automation Status */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="sla-automation-card" testID="sla-automation-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.sLAMonitorPanel.auto.text.004', 'Automation Rules')}</Text>
            <View style={{ gap: 8 }}>
              <AutoRule icon="time" color={T.warningText} label={`Warning at ${sla_config.warning_hours}h`} desc="Tickets flagged as at-risk when approaching SLA deadline" active />
              <AutoRule icon="flame" color={T.error} label={`Auto-escalate at ${sla_config.escalation_hours}h`} desc="Tickets automatically escalated to senior admins" active />
              <AutoRule icon="mail" color={T.primary} label="Senior admin email alerts" desc="Automated email notifications on every escalation" active />
              <AutoRule icon="refresh" color={T.teal} label="Scheduler runs every 6h" desc="Background job checks all open tickets against SLA" active />
            </View>
          </View>
        </View>
      )}

      {view === 'at-risk' && (
        <View style={{ gap: 12 }}>
          {(!at_risk_tickets || at_risk_tickets.length === 0) ? (
            <View style={{ paddingVertical: 32, alignItems: 'center' }}>
              <Ionicons name="shield-checkmark" size={40} color={T.successText} />
              <Text style={{ color: T.textSec, fontSize: 14, marginTop: 8, fontWeight: '600' }}>{tx('admin.sLAMonitorPanel.auto.text.005', 'All tickets within SLA')}</Text>
            </View>
          ) : (
            <>
              <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 10, backgroundColor: T.bgSoft, borderRadius: 8 }}>
                <Text style={{ flex: 2, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.sLAMonitorPanel.auto.text.006', 'TICKET')}</Text>
                <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.sLAMonitorPanel.auto.text.007', 'STATUS')}</Text>
                <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.sLAMonitorPanel.auto.text.008', 'WAITING')}</Text>
                <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.sLAMonitorPanel.auto.text.009', 'SLA %')}</Text>
              </View>
              {at_risk_tickets.map((t: any, i: number) => {
                const urgency = t.sla_pct >= 100 ? T.error : t.sla_pct >= 75 ? T.warning : T.textSec;
                return (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 10, borderBottomWidth: 1, borderBottomColor: T.border, backgroundColor: t.sla_pct >= 100 ? T.errorSoft : 'transparent', borderRadius: 8 }} data-testid={`at-risk-ticket-${i}`} testID={`at-risk-ticket-${i}`}>
                    <View style={{ flex: 2 }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{t.ticket_number || t.ticket_id}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={1}>{t.subject}</Text>
                    </View>
                    <View style={{ flex: 1, alignItems: 'center' }}>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: T.bgSoft }}>
                        <Text style={{ color: T.textSec, fontSize: 9, fontWeight: '700' }}>{t.status?.toUpperCase()}</Text>
                      </View>
                    </View>
                    <Text style={{ flex: 1, color: urgency, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>{Math.round(t.hours_waiting)}h</Text>
                    <View style={{ flex: 1.5, alignItems: 'center' }}>
                      <View style={{ width: '80%', height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                        <View style={{ width: `${Math.min(100, t.sla_pct)}%` as any, height: '100%', backgroundColor: urgency, borderRadius: 4 }} />
                      </View>
                      <Text style={{ color: urgency, fontSize: 9, fontWeight: '700', marginTop: 2 }}>{t.sla_pct}%</Text>
                    </View>
                  </View>
                );
              })}
            </>
          )}
        </View>
      )}

      {view === 'escalated' && (
        <View style={{ gap: 12 }}>
          {(!escalated_tickets || escalated_tickets.length === 0) ? (
            <View style={{ paddingVertical: 32, alignItems: 'center' }}>
              <Ionicons name="checkmark-done" size={40} color={T.successText} />
              <Text style={{ color: T.textSec, fontSize: 14, marginTop: 8, fontWeight: '600' }}>{tx('admin.sLAMonitorPanel.auto.text.010', 'No escalated tickets')}</Text>
            </View>
          ) : (
            escalated_tickets.map((t: any, i: number) => (
              <View key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '30'), borderLeftWidth: 3, borderLeftColor: T.error }} data-testid={`escalated-ticket-${i}`} testID={`escalated-ticket-${i}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Ionicons name="flame" size={14} color={T.error} />
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', flex: 1 }}>{t.ticket_number || t.ticket_id}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: T.errorSoft }}>
                    <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{tx('admin.sLAMonitorPanel.auto.text.011', 'ESCALATED')}</Text>
                  </View>
                </View>
                <Text style={{ color: T.textSec, fontSize: 12 }} numberOfLines={1}>{t.subject}</Text>
                <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>Waited: {t.sla_hours_waited || '?'}h</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>Escalated: {t.sla_escalated_at?.slice(0, 10) || '-'}</Text>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {view === 'ai-insights' && (
        <AIInsightsTab data={aiData} loading={aiLoading} onRun={runAiAnalysis} />
      )}
    </View>
  );
}

function AIInsightsTab({ data, loading, onRun }: { data: any; loading: boolean; onRun: () => void }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => { if (!data && !loading) onRun(); }, []);

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.ai} /><Text style={{ color: T.textSec, marginTop: 8, fontSize: 12 }}>{tx('admin.sLAMonitorPanel.auto.text.012', 'GPT-4o analyzing SLA patterns...')}</Text></View>;

  if (!data || data.status === 'no_data') return (
    <View style={{ alignItems: 'center', paddingVertical: 32 }}>
      <TouchableOpacity onPress={onRun} style={{ backgroundColor: T.ai, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 }} data-testid="sla-ai-run-btn" testID="sla-ai-run-btn">
        <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 14 }}>{tx('admin.sLAMonitorPanel.auto.text.013', 'Run AI SLA Analysis')}</Text>
      </TouchableOpacity>
    </View>
  );

  const riskColor = data.risk_score >= 70 ? T.error : data.risk_score >= 40 ? T.warning : T.success;

  return (
    <View style={{ gap: 14 }} data-testid="sla-ai-insights" testID="sla-ai-insights">
      <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '30') }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.ai, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="sparkles" size={16} color={T.ai} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.sLAMonitorPanel.auto.text.014', 'SLA Risk Score')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.sLAMonitorPanel.auto.text.015', 'Powered by GPT-4o')}</Text>
            </View>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: riskColor, fontSize: 28, fontWeight: '900' }}>{data.risk_score}</Text>
            <Text style={{ color: riskColor, fontSize: 9, fontWeight: '700' }}>/100</Text>
          </View>
        </View>
        <Text style={{ color: T.textSec, fontSize: 12, lineHeight: 18 }}>{data.risk_summary}</Text>
        {data.predicted_breaches > 0 && (
          <View style={{ backgroundColor: T.errorSoft, borderRadius: 8, padding: 10, marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="warning" size={16} color={T.error} />
            <Text style={{ color: T.error, fontSize: 12, fontWeight: '700' }}>{data.predicted_breaches} tickets predicted to breach SLA</Text>
          </View>
        )}
      </View>

      {data.at_risk_tickets?.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.sLAMonitorPanel.auto.text.016', 'AI-Predicted At-Risk Tickets')}</Text>
          {data.at_risk_tickets.slice(0, 5).map((t: any, i: number) => (
            <View key={i} style={{ paddingVertical: 10, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: T.border }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '600', flex: 1 }} numberOfLines={1}>{t.ticket_id}</Text>
                <View style={{ backgroundColor: t.breach_probability >= 80 ? T.errorSoft : T.warningSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
                  <Text style={{ color: t.breach_probability >= 80 ? T.error : T.warning, fontSize: 10, fontWeight: '700' }}>{t.breach_probability}% breach risk</Text>
                </View>
              </View>
              <Text style={{ color: T.textSec, fontSize: 11 }}>{t.recommended_action}</Text>
            </View>
          ))}
        </View>
      )}

      {data.optimization_tips?.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.sLAMonitorPanel.auto.text.017', 'Optimization Tips')}</Text>
          {data.optimization_tips.map((tip: any, i: number) => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 8, borderBottomWidth: i < data.optimization_tips.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
              <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: tip.impact === 'high' ? T.errorSoft : tip.impact === 'medium' ? T.warningSoft : T.successSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="bulb" size={12} color={tip.impact === 'high' ? T.error : tip.impact === 'medium' ? T.warning : T.success} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{tip.tip}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{tip.category} | Impact: {tip.impact}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <TouchableOpacity onPress={onRun} style={{ backgroundColor: (globalThis as any).__alphaColor(T.ai, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '40'), paddingVertical: 10, borderRadius: 10, alignItems: 'center' }} data-testid="sla-ai-refresh-btn" testID="sla-ai-refresh-btn">
        <Text style={{ color: T.ai, fontSize: 12, fontWeight: '700' }}>{tx('admin.sLAMonitorPanel.auto.text.018', 'Refresh AI Analysis')}</Text>
      </TouchableOpacity>

      {data.created_at && <Text style={{ color: T.textMuted, fontSize: 9, textAlign: 'center' }}>Last analyzed: {new Date(data.created_at).toLocaleString()}</Text>}
    </View>
  );
}

function SLAKPI({ icon, color, label, value }: { icon: string; color: string; label: string; value: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color, minWidth: 140, flex: 1 }} data-testid={`sla-kpi-${label.replace(/\s/g, '-').toLowerCase()}`} testID={`sla-kpi-${label.replace(/\s/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={12} color={color} />
        </View>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
    </View>
  );
}

function AutoRule({ icon, color, label, desc, active }: { icon: string; color: string; label: string; desc: string; active: boolean }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
      <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon as any} size={14} color={color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{label}</Text>
        <Text style={{ color: T.textMuted, fontSize: 10 }}>{desc}</Text>
      </View>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: active ? T.success : T.textMuted }} />
    </View>
  );
}
