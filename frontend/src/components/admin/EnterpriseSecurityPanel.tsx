import React, { useEffect, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAiInsight, AIInsightPanel, FindingItem, TrendItem, PriorityItem } from './AIInsightHelpers';
import DependencyScanPanel from './DependencyScanPanel';
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

// Module-scope fallback for helpers referring bare T/colors outside the main component
const _T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  purple: 'var(--app-info)' as any,
  cyan: 'var(--app-info)' as any,
};
const colors = {
  bg: 'var(--app-bg)' as any,
  surface: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  primarySoft: 'var(--app-primary-soft)' as any,
  success: 'var(--app-success)' as any,
  error: 'var(--app-error)' as any,
  warning: 'var(--app-warning)' as any,
  successText: 'var(--app-success)' as any,
  warningText: 'var(--app-warning)' as any,
  purpleText: 'var(--app-primary)' as any,
  accent: 'var(--app-info)' as any,
  accentSoft: 'var(--app-info-soft)' as any,
};

const tx = (_key: string, fallback: string) => fallback;

const severityColors: Record<string, string> = {
  critical: 'var(--app-error)' as any,
  high: 'var(--app-warning)' as any,
  medium: 'var(--app-primary)' as any,
  low: 'var(--app-text-muted)' as any,
};

export default function EnterpriseSecurityPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [audit, setAudit] = useState<any>(null);
  const [wafStats, setWafStats] = useState<any>(null);
  const [rateLimits, setRateLimits] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [compliance, setCompliance] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [tab, setTab] = useState<'audit' | 'waf' | 'rate-limits' | 'posture' | 'compliance' | 'dependency-scan'>('audit');

  const loadSecurityData = React.useCallback(async () => {
    await Promise.all([
      api.get('/admin/security/audit').then(r => setAudit(r.data)).catch(() => {}),
      api.get('/admin/security/waf/stats').then(r => setWafStats(r.data)).catch(() => {}),
      api.get('/admin/security/rate-limits').then(r => setRateLimits(r.data)).catch(() => {}),
      api.get('/admin/security/posture/timeline').then(r => setTimeline(r.data.timeline || [])).catch(() => {}),
    ]);
  }, []);

  useEffect(() => {
    loadSecurityData().finally(() => setLoading(false));
  }, [loadSecurityData]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/enterprise-security/hybrid-refresh',
    onTick: loadSecurityData,
    runOnMount: false,
    slowIntervalMs: 90000,
    fastIntervalMs: 30000,
  });

  const runAudit = async () => {
    setAuditing(true);
    try {
      const res = await api.get('/admin/security/audit');
      setAudit(res.data);
    } finally { setAuditing(false); }
  };

  const recordSnapshot = async () => {
    setSnapshotting(true);
    try {
      await api.post('/admin/security/posture/snapshot');
      const res = await api.get('/admin/security/posture/timeline');
      setTimeline(res.data.timeline || []);
    } finally { setSnapshotting(false); }
  };

  const generateComplianceReport = async () => {
    setGeneratingReport(true);
    try {
      const res = await api.get('/admin/security/compliance/report');
      setCompliance(res.data);
    } finally { setGeneratingReport(false); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <AutoFixBanner domain="enterprise_security" />
      <ActivityIndicator size="large" color={T.error} />
      <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.enterpriseSecurityPanel.auto.text.001', 'Loading Security Dashboard...')}</Text>
    </View>
  );

  const tabs = [
    { id: 'audit' as const, label: 'Security Audit', icon: 'shield-checkmark' },
    { id: 'waf' as const, label: 'WAF Rules', icon: 'flame' },
    { id: 'rate-limits' as const, label: 'Rate Limits', icon: 'speedometer' },
    { id: 'posture' as const, label: 'Posture Timeline', icon: 'trending-up' },
    { id: 'compliance' as const, label: 'Compliance', icon: 'document-text' },
    { id: 'dependency-scan' as const, label: 'Dep. Scan', icon: 'scan' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${T.error}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield" size={18} color={T.error} />
          </div>
          <div>
            <Text style={{ fontSize: 16, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.002', 'Enterprise Security')}</Text>
            <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.enterpriseSecurityPanel.auto.text.003', 'WAF, Rate Limiting, Security Headers Audit')}</Text>
          </div>
        </div>
        <button data-testid="run-security-audit-btn" onClick={runAudit} disabled={auditing}
          style={{ padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', backgroundColor: auditing ? `${T.error}4D` : T.error, color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>
          {auditing ? 'Auditing...' : 'Run Full Audit'}
        </button>
      </div>

      {/* Score Cards */}
      {audit && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          {[
            { label: 'Overall Score', value: audit.overall_score, color: audit.overall_score >= 80 ? T.success : audit.overall_score >= 60 ? T.warning : T.error },
            { label: 'Headers', value: audit.header_score, color: audit.header_score >= 80 ? T.success : T.warning },
            { label: 'Auth Security', value: audit.auth_score, color: T.successText },
            { label: 'Rate Limiting', value: audit.rate_limit_score, color: T.successText },
            { label: 'WAF Rules', value: audit.waf_summary?.total_rules || 0, color: T.purpleText, suffix: '' },
            { label: 'Blocked 24h', value: audit.waf_summary?.blocked_24h || 0, color: T.warningText, suffix: '' },
          ].map((card, i) => (
            <div key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}`, textAlign: 'center' }} data-testid={`security-card-${i}`}>
              <div style={{ fontSize: 24, fontWeight: '800', color: card.color }}>{card.value}{card.suffix !== '' ? (card.suffix ?? '%') : ''}</div>
              <div style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 4 }}>{card.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, borderBottom: `1px solid ${T.border}`, paddingBottom: 8 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`sec-tab-${t.id}`}
            style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', backgroundColor: tab === t.id ? `${T.error}20` : 'transparent', color: tab === t.id ? T.error : T.textMuted, fontSize: 11, fontWeight: '700' }}>
            <Ionicons name={t.icon as any} size={12} color={tab === t.id ? T.error : T.textMuted} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Security Audit Tab */}
      {tab === 'audit' && audit && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Security Headers */}
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="security-headers">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="code" size={14} color={T.cyan} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.004', 'Security Headers')}</Text>
            </div>
            {audit.security_headers?.map((h: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < audit.security_headers.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                <Ionicons name={h.passed ? 'checkmark-circle' : 'close-circle'} size={14} color={h.passed ? T.success : T.error} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{h.header}</div>
                  <div style={{ fontSize: 10, color: T.textMuted }}>{h.description}</div>
                </div>
                <span style={{ fontSize: 9, color: h.passed ? T.success : T.error, fontWeight: '700' }}>{h.passed ? 'PASS' : 'FAIL'}</span>
              </div>
            ))}
          </div>

          {/* Auth Checks */}
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="auth-checks">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="key" size={14} color={T.purpleText} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.005', 'Authentication Security')}</Text>
            </div>
            {audit.auth_checks?.map((c: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < audit.auth_checks.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                <Ionicons name={c.passed ? 'checkmark-circle' : 'warning'} size={14} color={c.passed ? T.success : T.warning} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{c.check}</div>
                  <div style={{ fontSize: 10, color: T.textMuted }}>{c.detail}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Recommendations */}
          {audit.recommendations?.length > 0 && (
            <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="security-recs">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="bulb" size={14} color={T.warningText} />
                <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.006', 'Security Recommendations')}</Text>
              </div>
              {audit.recommendations.map((r: any, i: number) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < audit.recommendations.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                  <span style={{ fontSize: 9, fontWeight: '700', color: severityColors[r.priority] || T.textMuted, backgroundColor: `${severityColors[r.priority] || T.textMuted}18`, padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{r.priority}</span>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{r.category}</div>
                    <div style={{ fontSize: 10, color: T.textMuted }}>{r.action}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* WAF Tab */}
      {tab === 'waf' && wafStats && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="waf-rules">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="flame" size={14} color={T.error} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>WAF Rules ({wafStats.builtin_rules?.length || 0} built-in)</Text>
            </div>
            {wafStats.builtin_rules?.map((r: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < wafStats.builtin_rules.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                <span style={{ fontSize: 9, fontWeight: '700', color: severityColors[r.severity], backgroundColor: `${severityColors[r.severity]}18`, padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{r.severity}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{r.name}</div>
                  <div style={{ fontSize: 9, color: T.textMuted, fontFamily: 'monospace' }}>{r.pattern?.substring(0, 60)}...</div>
                </div>
                <span style={{ fontSize: 9, color: r.enabled ? T.success : T.textMuted, fontWeight: '700' }}>{r.enabled ? 'ACTIVE' : 'OFF'}</span>
              </div>
            ))}
          </div>
          <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 8 }}>{tx('admin.enterpriseSecurityPanel.auto.text.007', 'Threat Statistics (7 days)')}</Text>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 20, fontWeight: '800', color: T.warningText }}>{wafStats.stats?.blocked_24h || 0}</div>
                <div style={{ fontSize: 10, color: T.textMuted }}>Blocked (24h)</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 20, fontWeight: '800', color: T.error }}>{wafStats.stats?.blocked_7d || 0}</div>
                <div style={{ fontSize: 10, color: T.textMuted }}>Blocked (7d)</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 20, fontWeight: '800', color: T.successText }}>{(wafStats.builtin_rules?.filter((r: any) => r.enabled)?.length || 0) + (wafStats.custom_rules?.length || 0)}</div>
                <div style={{ fontSize: 10, color: T.textMuted }}>Active Rules</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Rate Limits Tab */}
      {tab === 'rate-limits' && rateLimits && (
        <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="rate-limits">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="speedometer" size={14} color={T.primary} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.008', 'Rate Limit Configuration')}</Text>
          </div>
          {Object.entries(rateLimits.config || {}).map(([key, val]: [string, any], i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: i < Object.entries(rateLimits.config).length - 1 ? `1px solid ${T.border}` : 'none' }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: '600', color: T.text, textTransform: 'capitalize' }}>{key}</div>
                <div style={{ fontSize: 10, color: T.textMuted }}>Burst: {val.burst}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 14, fontWeight: '700', color: T.primary }}>{val.requests_per_minute}</div>
                <div style={{ fontSize: 9, color: T.textMuted }}>req/min</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop: 12, padding: 10, backgroundColor: `${T.primary}10`, borderRadius: 8, border: `1px solid ${T.primary}30` }}>
            <div style={{ fontSize: 10, color: T.textMuted }}>Total Violations (24h): {rateLimits.total_violations_24h || 0}</div>
          </div>
        </div>
      )}

      {/* Posture Timeline Tab */}
      {tab === 'posture' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Ionicons name="trending-up" size={14} color={T.cyan} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.009', 'Security Posture Over Time')}</Text>
              <span style={{ fontSize: 9, color: T.textMuted, backgroundColor: T.bgSoft, padding: '2px 6px', borderRadius: 4 }}>{timeline.length} snapshots</span>
            </div>
            <button data-testid="record-snapshot-btn" onClick={recordSnapshot} disabled={snapshotting}
              style={{ padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', backgroundColor: snapshotting ? `${T.cyan}4D` : T.cyan, color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>
              {snapshotting ? 'Recording...' : 'Record Snapshot'}
            </button>
          </div>

          {timeline.length === 0 ? (
            <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 32, border: `1px solid ${T.border}`, textAlign: 'center' }}>
              <Ionicons name="analytics-outline" size={32} color={T.textMuted} />
              <Text style={{ fontSize: 13, fontWeight: '600', color: T.text, marginTop: 12 }}>{tx('admin.enterpriseSecurityPanel.auto.text.010', 'No Snapshots Yet')}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{tx('admin.enterpriseSecurityPanel.auto.text.011', 'Click "Record Snapshot" to start tracking your security posture over time.')}</Text>
            </div>
          ) : (
            <>
              {/* Timeline chart — bar representation */}
              <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="posture-timeline-chart">
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 120, paddingBottom: 24, position: 'relative' }}>
                  {timeline.slice(-30).map((entry: any, i: number) => {
                    const score = entry.overall_score || 0;
                    const barColor = score >= 80 ? T.success : score >= 60 ? T.warning : T.error;
                    return (
                      <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }} title={`${new Date(entry.timestamp).toLocaleDateString()} — Score: ${score}`}>
                        <div style={{ fontSize: 8, color: T.textMuted }}>{score}</div>
                        <div style={{ width: '100%', height: `${score}%`, backgroundColor: barColor, borderRadius: '3px 3px 0 0', minHeight: 4, transition: 'height 0.3s ease' }} />
                      </div>
                    );
                  })}
                </div>
                <div style={{ fontSize: 9, color: T.textMuted, textAlign: 'center', marginTop: 4 }}>Last {Math.min(timeline.length, 30)} snapshots</div>
              </div>

              {/* Timeline entries */}
              <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="posture-timeline-entries">
                <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.enterpriseSecurityPanel.auto.text.012', 'Recent Snapshots')}</Text>
                {timeline.slice(-10).reverse().map((entry: any, i: number) => {
                  const sc = entry.overall_score || 0;
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: i < Math.min(timeline.length, 10) - 1 ? `1px solid ${T.border}` : 'none' }}>
                      <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${sc >= 80 ? T.success : sc >= 60 ? T.warning : T.error}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontSize: 14, fontWeight: '800', color: sc >= 80 ? T.success : sc >= 60 ? T.warning : T.error }}>{sc}</span>
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, color: T.text, fontWeight: '600' }}>{new Date(entry.timestamp).toLocaleString()}</div>
                        <div style={{ fontSize: 10, color: T.textMuted }}>
                          Headers: {entry.header_score}% | WAF: {entry.waf_score}% | Auth: {entry.auth_score}% | Rate: {entry.rate_limit_score}%
                        </div>
                      </div>
                      <div style={{ fontSize: 10, color: T.textMuted }}>{entry.waf_rules_active} rules</div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* Compliance Tab */}
      {tab === 'compliance' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Ionicons name="document-text" size={14} color={T.purpleText} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.013', 'Compliance Reports (SOC2 & GDPR)')}</Text>
            </div>
            <button data-testid="generate-compliance-btn" onClick={generateComplianceReport} disabled={generatingReport}
              style={{ padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', backgroundColor: generatingReport ? `${T.purple}4D` : T.purple, color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>
              {generatingReport ? 'Generating...' : 'Generate Report'}
            </button>
          </div>

          {!compliance ? (
            <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 32, border: `1px solid ${T.border}`, textAlign: 'center' }}>
              <Ionicons name="clipboard-outline" size={32} color={T.textMuted} />
              <Text style={{ fontSize: 13, fontWeight: '600', color: T.text, marginTop: 12 }}>{tx('admin.enterpriseSecurityPanel.auto.text.014', 'No Compliance Report')}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{tx('admin.enterpriseSecurityPanel.auto.text.015', 'Click "Generate Report" to create a SOC2 & GDPR compliance assessment.')}</Text>
            </div>
          ) : (
            <>
              {/* Overall compliance score */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                {[
                  { label: 'Overall Compliance', value: compliance.overall_compliance_score, color: compliance.overall_compliance_score >= 80 ? T.success : T.warning },
                  { label: 'SOC2 Score', value: compliance.soc2?.score, color: compliance.soc2?.score >= 80 ? T.success : T.warning },
                  { label: 'GDPR Score', value: compliance.gdpr?.score, color: compliance.gdpr?.score >= 80 ? T.success : T.warning },
                ].map((card, i) => (
                  <div key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}`, textAlign: 'center' }} data-testid={`compliance-score-${i}`}>
                    <div style={{ fontSize: 28, fontWeight: '800', color: card.color }}>{card.value}%</div>
                    <div style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 4 }}>{card.label}</div>
                  </div>
                ))}
              </div>

              {/* SOC2 Controls */}
              <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="soc2-controls">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Ionicons name="shield-checkmark" size={14} color={T.primary} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>SOC2 Controls ({compliance.soc2?.controls_compliant}/{compliance.soc2?.controls_total} compliant)</Text>
                </div>
                {compliance.soc2?.controls?.map((ctrl: any, i: number) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < (compliance.soc2?.controls?.length || 0) - 1 ? `1px solid ${T.border}` : 'none' }}>
                    <Ionicons name={ctrl.status === 'compliant' ? 'checkmark-circle' : 'warning'} size={14} color={ctrl.status === 'compliant' ? T.success : T.warning} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{ctrl.id}: {ctrl.name}</div>
                      <div style={{ fontSize: 10, color: T.textMuted }}>{ctrl.evidence}</div>
                    </div>
                    <span style={{ fontSize: 12, fontWeight: '700', color: ctrl.score >= 80 ? T.success : T.warning }}>{ctrl.score}%</span>
                  </div>
                ))}
              </div>

              {/* GDPR Articles */}
              <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="gdpr-articles">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Ionicons name="earth" size={14} color={T.cyan} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>GDPR Articles ({compliance.gdpr?.articles_compliant}/{compliance.gdpr?.articles_total} compliant)</Text>
                </div>
                {compliance.gdpr?.articles?.map((art: any, i: number) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < (compliance.gdpr?.articles?.length || 0) - 1 ? `1px solid ${T.border}` : 'none' }}>
                    <Ionicons name={art.status === 'compliant' ? 'checkmark-circle' : 'warning'} size={14} color={art.status === 'compliant' ? T.success : T.warning} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{art.article}: {art.name}</div>
                      <div style={{ fontSize: 10, color: T.textMuted }}>{art.evidence}</div>
                    </div>
                    <span style={{ fontSize: 12, fontWeight: '700', color: art.score >= 80 ? T.success : T.warning }}>{art.score}%</span>
                  </div>
                ))}
              </div>

              {/* Recommendations */}
              {compliance.recommendations?.length > 0 && (
                <div style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }} data-testid="compliance-recs">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="bulb" size={14} color={T.warningText} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.enterpriseSecurityPanel.auto.text.016', 'Compliance Recommendations')}</Text>
                  </div>
                  {compliance.recommendations.map((rec: any, i: number) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < compliance.recommendations.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                      <span style={{ fontSize: 9, fontWeight: '700', color: severityColors[rec.priority] || T.textMuted, backgroundColor: `${severityColors[rec.priority] || T.textMuted}18`, padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{rec.priority}</span>
                      <div>
                        <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{rec.framework}</div>
                        <div style={{ fontSize: 10, color: T.textMuted }}>{rec.action}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ fontSize: 10, color: T.textMuted, textAlign: 'center' }}>
                Report ID: {compliance.report_id} | Generated: {new Date(compliance.generated_at).toLocaleString()}
              </div>
            </>
          )}
        </div>
      )}

      {/* Dependency Scan Tab */}
      {tab === 'dependency-scan' && (
        <View style={{ flex: 1 }} data-testid="dep-scan-tab-content">
          <DependencyScanPanel T={T} />
        </View>
      )}

      {/* AI Security Narrative */}
      <SecurityAISection />

      <View style={{ height: 20 }} />
    </ScrollView>
  );
}

function SecurityAISection() {
  const AC = useAdminTheme();
  const colors = makeT(AC);
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const ai = useAiInsight('security_narrative', 'security-narrative');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="security-ai-toggle" testID="security-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={colors.accent} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.enterpriseSecurityPanel.auto.text.017', 'AI Security Narrative')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={colors.accent} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'security_narrative', postEndpoint: 'security-narrative',
              title: 'AI Security Narrative', subtitle: 'security posture',
              scoreKey: 'security_score', scoreLabel: 'Security Score',
              summaryKey: 'narrative',
              sections: [
                { key: 'key_findings', title: 'Key Findings', icon: 'search', renderItem: (item, idx, total) => <FindingItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'trends', title: 'Security Trends', icon: 'trending-up', renderItem: (item, idx, total) => <TrendItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'recommended_actions', title: 'Recommended Actions', icon: 'shield-checkmark', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}
    </View>
  );
}
