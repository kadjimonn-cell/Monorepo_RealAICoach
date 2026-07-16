import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Modal, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { ResponsiveDataGrid } from './ResponsiveDataGrid';

/* ═══════════════════════════════════════
   ANALYTICS TAB
   ═══════════════════════════════════════ */
function FunnelBar({ label, value, total, color, icon }: { label: string; value: number; total: number; color: string; icon: string }) {
  const T = useExecTheme();
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <View style={{ marginBottom: 14 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name={icon as any} size={14} color={color} />
          <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '600' }}>{label}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
          <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{value}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11 }}>({pct.toFixed(0)}%)</Text>
        </View>
      </View>
      <View style={{ height: 8, backgroundColor: T.card, borderRadius: 4, overflow: 'hidden', borderWidth: 1, borderColor: T.border }}>
        <View style={{ height: '100%', width: `${Math.max(pct, 2)}%`, backgroundColor: color, borderRadius: 4 }} />
      </View>
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

function BreakdownRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const T = useExecTheme();
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 }}>
      <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '500', minWidth: 100 }}>{label}</Text>
      <View style={{ flex: 1, height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ height: '100%', width: `${Math.max(pct, 3)}%`, backgroundColor: color, borderRadius: 3 }} />
      </View>
      <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', minWidth: 30, textAlign: 'right' }}>{count}</Text>
      <Text style={{ color: T.textMuted, fontSize: 11, minWidth: 35 }}>{pct.toFixed(0)}%</Text>
    </View>
  );
}

function MetricCard({ label, value, sub, icon, color }: { label: string; value: string; sub?: string; icon: string; color: string }) {
  const T = useExecTheme();
  return (
    <View style={{ flex: 1, minWidth: 160, backgroundColor: T.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid={`analytics-metric-${label.replace(/\s+/g, '-').toLowerCase()}`} testID={`analytics-metric-${label.replace(/\s+/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3, flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 26, fontWeight: '800', letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

function AnalyticsView({ stats, applications }: { stats: any; applications: any[] }) {
  const _s = useExecStyles();
  const T = useExecTheme();
  const total = stats?.total ?? 0;
  const reviewed = (stats?.approved ?? 0) + (stats?.rejected ?? 0);
  const approved = stats?.approved ?? 0;
  const pending = (stats?.pending ?? 0) + (stats?.in_review ?? 0);
  const rejected = stats?.rejected ?? 0;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _onHold = (stats?.on_hold ?? 0) + (stats?.needs_info ?? 0) + (stats?.escalated ?? 0);
  const approvalRate = stats?.approval_rate ?? 0;
  const avgHours = stats?.avg_approval_hours ?? 0;

  // Compute avg days from application data
  const reviewedApps = applications.filter(a => a.status === 'approved' || a.status === 'rejected');
  let avgDays = 0;
  if (reviewedApps.length > 0) {
    const totalMs = reviewedApps.reduce((sum, a) => {
      const sub = new Date(a.submitted_at || a.created_at).getTime();
      const upd = new Date(a.updated_at || a.submitted_at).getTime();
      return sum + (upd - sub);
    }, 0);
    avgDays = totalMs / reviewedApps.length / (1000 * 60 * 60 * 24);
  }

  // Status distribution for chart
  const statusDist = [
    { label: 'Approved', count: approved, color: T.successText },
    { label: 'Pending', count: stats?.pending ?? 0, color: T.warningText },
    { label: 'In Review', count: stats?.in_review ?? 0, color: T.primary },
    { label: 'Rejected', count: rejected, color: T.error },
    { label: 'On Hold', count: stats?.on_hold ?? 0, color: T.textMuted },
    { label: 'Needs Info', count: stats?.needs_info ?? 0, color: T.orangeText },
  ].filter(s => s.count > 0);

  const industryData = stats?.industry_breakdown || [];
  const countryData = stats?.country_breakdown || [];
  const indColors = [T.primary, T.cyan, T.purple, T.pink, T.orange, T.teal];
  const countryColors = [T.success, T.warning, T.primary, T.purple, T.cyan];

  return (
    <View data-testid="employer-analytics-view" testID="employer-analytics-view">
      {/* Metric Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
        <MetricCard label="Total Applications" value={String(total)} sub={`${pending} awaiting review`} icon="documents" color={T.primary} />
        <MetricCard label="Approval Rate" value={`${approvalRate.toFixed(1)}%`} sub={`${approved} of ${total} approved`} icon="checkmark-done" color={T.successText} />
        <MetricCard label="Avg Review Time" value={avgHours > 0 ? `${avgHours.toFixed(1)}h` : avgDays > 0 ? `${avgDays.toFixed(1)}d` : '< 1h'} sub="From submission to decision" icon="timer" color={T.cyan} />
        <MetricCard label="Rejection Rate" value={total > 0 ? `${((rejected / total) * 100).toFixed(1)}%` : '0%'} sub={`${rejected} applications rejected`} icon="close-circle" color={T.error} />
      </View>

      {/* Conversion Funnel */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, marginBottom: 20 }} data-testid="analytics-funnel" testID="analytics-funnel">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 18 }}>
          <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="funnel" size={14} color={T.primary} />
          </View>
          <Text style={{ color: T.text, fontSize: 16, fontWeight: '800', letterSpacing: -0.3 }}>{tx('admin.employerPortalPanel.auto.text.001', 'Application Funnel')}</Text>
        </View>
        <FunnelBar label="Total Applications" value={total} total={total} color={T.primary} icon="documents" />
        <FunnelBar label="Reviewed" value={reviewed} total={total} color={T.purpleText} icon="eye" />
        <FunnelBar label="Approved" value={approved} total={total} color={T.successText} icon="checkmark-circle" />
      </View>

      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Status Distribution */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="analytics-status-dist" testID="analytics-status-dist">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: T.cyanSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="pie-chart" size={14} color={T.cyan} />
            </View>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.002', 'Status Distribution')}</Text>
          </View>
          {/* Visual donut representation */}
          <View style={{ flexDirection: 'row', height: 12, borderRadius: 6, overflow: 'hidden', marginBottom: 16 }}>
            {statusDist.map((s, i) => (
              <View key={i} style={{ flex: s.count, backgroundColor: s.color, marginRight: i < statusDist.length - 1 ? 2 : 0 }} />
            ))}
          </View>
          {statusDist.map((s, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: s.color }} />
              <Text style={{ color: T.textSec, fontSize: 13, flex: 1 }}>{s.label}</Text>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{s.count}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, minWidth: 35 }}>{total > 0 ? ((s.count / total) * 100).toFixed(0) : 0}%</Text>
            </View>
          ))}
        </View>

        {/* Industry Breakdown */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="analytics-industry" testID="analytics-industry">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: T.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="grid" size={14} color={T.purpleText} />
            </View>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.003', 'By Industry')}</Text>
          </View>
          {industryData.length > 0 ? industryData.map((ind: any, i: number) => (
            <BreakdownRow key={i} label={ind.industry || ind._id || 'Other'} count={ind.count} total={total} color={indColors[i % indColors.length]} />
          )) : (
            <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.employerPortalPanel.auto.text.004', 'No industry data available')}</Text>
          )}
        </View>
      </View>

      {/* Country Breakdown */}
      {countryData.length > 0 && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="analytics-country" testID="analytics-country">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: T.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="earth" size={14} color={T.successText} />
            </View>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.005', 'By Country')}</Text>
          </View>
          {countryData.map((c: any, i: number) => (
            <BreakdownRow key={i} label={c.country || c._id || 'Unknown'} count={c.count} total={total} color={countryColors[i % countryColors.length]} />
          ))}
        </View>
      )}
    </View>
  );
}

/* ═══════════════════════════════════════
   MAIN PANEL
   ═══════════════════════════════════════ */
export default function EmployerPortalPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const [filter, setFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');
  const [page, setPage] = useState(1);
  const { data: stats, loading: stLoading, refetch: loadData } = useLiveQuery('/employers/admin/stats', { entity: 'employers', pollInterval: 30000 });
  const { data: appsData, loading: apLoading } = useLiveQuery(`/employers/admin/applications?status=${filter}&risk_level=${riskFilter}&page=${page}&limit=20`, { entity: 'employers', pollInterval: 30000 });
  const { data: commandData, refetch: refetchCommand } = useLiveQuery('/employers/admin/command-center?status=all&limit=20', { entity: 'employers', pollInterval: 30000 });
  const applications = appsData?.applications || [];
  const loading = stLoading || apLoading;
  const [search, setSearch] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedApp, setSelectedApp] = useState<any>(null);
  const [comms, setComms] = useState<any>({ messages: [], email_timeline: [], audit_trail: [] });
  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [previewLoadingDocId, setPreviewLoadingDocId] = useState<string | null>(null);
  const [docPreviewUrls, setDocPreviewUrls] = useState<Record<string, string>>({});
  const [docPreviewModalOpen, setDocPreviewModalOpen] = useState(false);
  const [docPreviewDocs, setDocPreviewDocs] = useState<any[]>([]);
  const [docPreviewEmployerId, setDocPreviewEmployerId] = useState('');
  const [docPreviewIndex, setDocPreviewIndex] = useState(0);
  const [docPreviewZoom, setDocPreviewZoom] = useState(1);
  const [checklistModalOpen, setChecklistModalOpen] = useState(false);
  const [checklistTarget, setChecklistTarget] = useState<any>(null);
  const [checkDocCompleteness, setCheckDocCompleteness] = useState(false);
  const [checkIdentityMatch, setCheckIdentityMatch] = useState(false);
  const [checkFraudReviewed, setCheckFraudReviewed] = useState(false);
  const [checklistNote, setChecklistNote] = useState('');
  const [submittingChecklist, setSubmittingChecklist] = useState(false);
  const [viewMode, setViewMode] = useState<'applications' | 'analytics'>('applications');

  const currentPreviewDoc = useMemo(() => docPreviewDocs[docPreviewIndex] || null, [docPreviewDocs, docPreviewIndex]);

  const handleReview = async (employerId: string, decision: string, extras: Record<string, any> = {}) => {
    setActionLoading(employerId + decision);
    try {
      await api.post(`/hiring/v2/admin/employers/review/${employerId}`, {
        action: decision,
        internal_note: extras.internal_note ?? `${decision} by admin`,
        reason: extras.reason,
        checklist_doc_completeness: extras.checklist_doc_completeness,
        checklist_identity_match: extras.checklist_identity_match,
        checklist_fraud_risk_reviewed: extras.checklist_fraud_risk_reviewed,
      });
      loadData();
      refetchCommand();
      if (selectedApp?.employer_id === employerId) {
        try {
          const res = await api.get(`/employers/admin/application/${employerId}`);
          const appDoc = res.data?.application || {};
          setSelectedApp({ ...appDoc, audit_trail: res.data?.audit_trail || [], email_timeline: res.data?.email_timeline || [] });
        } catch { setSelectedApp(null); }
      }
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  const openApproveChecklist = (app: any) => {
    setChecklistTarget(app);
    setChecklistModalOpen(true);
    setCheckDocCompleteness(false);
    setCheckIdentityMatch(false);
    setCheckFraudReviewed(false);
    setChecklistNote('');
  };

  const submitApproveChecklist = async () => {
    if (!checklistTarget?.employer_id) return;
    if (!checkDocCompleteness || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim()) return;
    setSubmittingChecklist(true);
    try {
      await handleReview(checklistTarget.employer_id, 'approve', {
        reason: checklistNote.trim(),
        internal_note: `Checklist approved: ${checklistNote.trim()}`,
        checklist_doc_completeness: true,
        checklist_identity_match: true,
        checklist_fraud_risk_reviewed: true,
      });
      setChecklistModalOpen(false);
      setChecklistTarget(null);
    } finally {
      setSubmittingChecklist(false);
    }
  };

  const handleAccessControl = async (employerId: string, action: 'suspend' | 'revoke' | 'restore') => {
    setActionLoading(employerId + action);
    try {
      await api.post(`/hiring/v2/admin/employers/access-control/${employerId}`, { action });
      loadData();
      refetchCommand();
      if (selectedApp?.employer_id === employerId) {
        await openDetail(employerId);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  };

  const handleAiRiskAssessment = async (employerId: string) => {
    setActionLoading(employerId + 'risk');
    try {
      await api.post(`/hiring/v2/admin/employers/risk-assess/${employerId}`, {});
      await openDetail(employerId);
      loadData();
      refetchCommand();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  };

  const sendAdminMessage = async (employerId: string) => {
    if (!newMessage.trim()) return;
    setSendingMessage(true);
    try {
      await api.post(`/hiring/v2/admin/employers/messages/${employerId}`, { message: newMessage.trim() });
      setNewMessage('');
      const commRes = await api.get(`/employers/admin/communications/${employerId}`).catch(() => null);
      if (commRes?.data) setComms(commRes.data);
    } catch (e) {
      console.error(e);
    } finally {
      setSendingMessage(false);
    }
  };

  const ensureDocPreviewUrl = useCallback(async (employerId: string, doc: any) => {
    if (!doc?.doc_id) return '';
    if (docPreviewUrls[doc.doc_id]) return docPreviewUrls[doc.doc_id];
    setPreviewLoadingDocId(String(doc.doc_id));
    try {
      const res = await api.get(`/employers/documents/${employerId}/${doc.doc_id}/download`, { responseType: 'blob' as any });
      const originalType = (res.headers?.['x-original-content-type'] || doc.content_type || 'application/octet-stream') as string;
      const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: originalType });
      if (typeof window === 'undefined') return '';
      const url = window.URL.createObjectURL(blob);
      setDocPreviewUrls(prev => ({ ...prev, [doc.doc_id]: url }));
      return url;
    } catch (e) {
      console.error(e);
      return '';
    } finally {
      setPreviewLoadingDocId(null);
    }
  }, [docPreviewUrls]);

  const openDocPreviewModal = async (employerId: string, docs: any[], index: number) => {
    if (!docs?.length) return;
    setDocPreviewDocs(docs);
    setDocPreviewEmployerId(String(employerId || ''));
    setDocPreviewIndex(index);
    setDocPreviewZoom(1);
    setDocPreviewModalOpen(true);
    await ensureDocPreviewUrl(employerId, docs[index]);
  };

  useEffect(() => {
    if (!docPreviewModalOpen || !currentPreviewDoc || !docPreviewEmployerId) return;
    if (docPreviewUrls[currentPreviewDoc.doc_id]) return;
    void ensureDocPreviewUrl(docPreviewEmployerId, currentPreviewDoc);
  }, [currentPreviewDoc, docPreviewEmployerId, docPreviewModalOpen, docPreviewUrls, ensureDocPreviewUrl]);

  const handleAddNote = async () => {
    if (!selectedApp || !noteText.trim()) return;
    try {
      await api.post(`/hiring/v2/admin/employers/add-note/${selectedApp.employer_id}`, { note: noteText });
      setNoteText('');
      const res = await api.get(`/employers/admin/application/${selectedApp.employer_id}`).catch(() => null);
      if (res?.data) {
        const appDoc = res.data?.application || {};
        setSelectedApp({ ...appDoc, audit_trail: res.data?.audit_trail || [], email_timeline: res.data?.email_timeline || [] });
      }
    } catch (e) { console.error(e); }
  };

  const openDetail = async (employerId: string) => {
    try {
      const [res, commRes] = await Promise.all([
        api.get(`/employers/admin/application/${employerId}`),
        api.get(`/employers/admin/communications/${employerId}`).catch(() => ({ data: { messages: [], email_timeline: [], audit_trail: [] } })),
      ]);
      const appDoc = res.data?.application || {};
      setSelectedApp({ ...appDoc, audit_trail: res.data?.audit_trail || [], email_timeline: res.data?.email_timeline || [] });
      setComms(commRes.data || { messages: [], email_timeline: [], audit_trail: [] });
      const docs = Array.isArray(appDoc?.documents) ? appDoc.documents : [];
      docs
        .filter((d: any) => String(d?.content_type || '').startsWith('image/'))
        .slice(0, 6)
        .forEach((d: any) => {
          void ensureDocPreviewUrl(employerId, d);
        });
    } catch (e) { console.error(e); }
  };

  const statusColor = (st: string) => {
    switch (st) { case 'approved': return T.success; case 'rejected': return T.error; case 'pending': return T.warning; case 'in_review': return T.primary; case 'on_hold': return T.cyan; case 'needs_info': return T.orange; default: return T.textMuted; }
  };

  const riskColor = (risk: string) => {
    if (risk === 'high_risk') return T.error;
    if (risk === 'suspicious') return T.warning;
    return T.successText;
  };

  const kpis = [
    { label: 'Total Employers', value: stats?.total ?? 0, icon: 'business', color: T.primary },
    { label: 'Approved', value: stats?.approved ?? 0, icon: 'checkmark-circle', color: T.successText },
    { label: 'Pending Review', value: (stats?.pending ?? 0) + (stats?.in_review ?? 0), icon: 'time', color: T.warningText },
    { label: 'Rejected', value: stats?.rejected ?? 0, icon: 'close-circle', color: T.error },
    { label: 'Approval Rate', value: `${stats?.approval_rate?.toFixed(1) ?? 0}%`, icon: 'analytics', color: T.cyan },
  ];

  const filteredApplications = applications.filter(a => !search || (a.business_name || '').toLowerCase().includes(search.toLowerCase()) || (a.email || a.business_email || '').toLowerCase().includes(search.toLowerCase()));

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="employer-portal-panel" testID="employer-portal-panel">
      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {kpis.map((k, i) => (
          <View key={i} style={[s.kpiCard, { flex: 1, minWidth: 160, borderLeftColor: k.color, borderLeftWidth: 3 }]} data-testid={`employer-kpi-${i}`} testID={`employer-kpi-${i}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase' }}>{k.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: '700', marginTop: 6 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* View Toggle */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 16, backgroundColor: T.card, borderRadius: 10, padding: 4, alignSelf: 'flex-start', borderWidth: 1, borderColor: T.border }}>
        {([
          { key: 'applications', label: 'Applications', icon: 'list' },
          { key: 'analytics', label: 'Analytics', icon: 'bar-chart' },
        ] as const).map(tab => (
          <TouchableOpacity key={tab.key} onPress={() => setViewMode(tab.key)} data-testid={`employer-tab-${tab.key}`} testID={`employer-tab-${tab.key}`}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8,
              backgroundColor: viewMode === tab.key ? T.primary : 'transparent',
            }}>
            <Ionicons name={tab.icon as any} size={14} color={viewMode === tab.key ? 'var(--app-primary-text)' : T.textMuted} />
            <Text style={{ color: viewMode === tab.key ? 'var(--app-primary-text)' : T.textMuted, fontSize: 13, fontWeight: '600' }}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Analytics View */}
      {viewMode === 'analytics' && <AnalyticsView stats={stats} applications={applications} />}

      {/* Applications View */}
      {viewMode === 'applications' && (
        <>
          <View style={{ backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 14, marginBottom: 14 }} data-testid="employer-command-center-summary" testID="employer-command-center-summary">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.employerPortalPanel.auto.text.006', 'Verification Command Center')}</Text>
              <TouchableOpacity onPress={refetchCommand} data-testid="employer-command-center-refresh" testID="employer-command-center-refresh">
                <Ionicons name="refresh" size={16} color={T.primary} />
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.employerPortalPanel.auto.text.007', 'Pending Reviews')}</Text>
                <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{commandData?.metrics?.pending_reviews ?? 0}</Text>
              </View>
              <View style={{ backgroundColor: T.errorSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '44'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: T.error, fontSize: 10 }}>{tx('admin.employerPortalPanel.auto.text.008', 'High-Risk Pending')}</Text>
                <Text style={{ color: T.error, fontSize: 16, fontWeight: '800' }}>{commandData?.metrics?.high_risk_pending ?? 0}</Text>
              </View>
              <View style={{ backgroundColor: T.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '33'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: T.successText, fontSize: 10 }}>{tx('admin.employerPortalPanel.auto.text.009', 'Avg Trust Score')}</Text>
                <Text style={{ color: T.successText, fontSize: 16, fontWeight: '800' }}>{stats?.avg_trust_score ?? 0}</Text>
              </View>
            </View>
          </View>

          {/* Filters */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {['all', 'pending', 'in_review', 'approved', 'rejected', 'on_hold'].map(f => (
                  <TouchableOpacity key={f} onPress={() => { setFilter(f); setPage(1); }}
                    style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: filter === f ? T.primary : T.card, borderWidth: 1, borderColor: filter === f ? T.primary : T.border }}
                    data-testid={`employer-filter-${f}`} testID={`employer-filter-${f}`}>
                    <Text style={{ color: filter === f ? 'var(--app-primary-text)' : T.textSec, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{f.replace('_', ' ')}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxWidth: 320 }}>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {['all', 'safe', 'suspicious', 'high_risk'].map(r => (
                  <TouchableOpacity key={r} onPress={() => { setRiskFilter(r); setPage(1); }}
                    style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 20, backgroundColor: riskFilter === r ? T.cyanSoft : T.card, borderWidth: 1, borderColor: riskFilter === r ? T.cyan : T.border }}
                    data-testid={`employer-risk-filter-${r}`} testID={`employer-risk-filter-${r}`}>
                    <Text style={{ color: riskFilter === r ? T.cyan : T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{r.replace('_', ' ')}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
            <TextInput placeholder={tx('admin.employerPortalPanel.auto.placeholder.001', 'Search employers...')} placeholderTextColor={T.textMuted} value={search} onChangeText={setSearch}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: T.text, fontSize: 13, minWidth: 200 } as any}
              data-testid="employer-search-input" testID="employer-search-input" />
            <TouchableOpacity onPress={loadData} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, alignItems: 'center', justifyContent: 'center' }}
              data-testid="employer-refresh-btn" testID="employer-refresh-btn">
              <Ionicons name="refresh" size={16} color={T.primary} />
            </TouchableOpacity>
          </View>

          {/* Applications Table / Cards */}
          <ResponsiveDataGrid
            compactBreakpoint={980}
            desktopTestId="employer-applications-desktop-table"
            compactTestId="employer-applications-compact-list"
            renderDesktop={() => (
              <View style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
                <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: T.bgSoft, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Text style={{ flex: 2, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.employerPortalPanel.auto.text.010', 'Company')}</Text>
                  <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.employerPortalPanel.auto.text.011', 'Contact')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.employerPortalPanel.auto.text.012', 'Location')}</Text>
                  <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.employerPortalPanel.auto.text.013', 'Status')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.employerPortalPanel.auto.text.014', 'Date')}</Text>
                  <Text style={{ flex: 1.2, color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.employerPortalPanel.auto.text.015', 'Actions')}</Text>
                </View>
                {filteredApplications.map((app, i) => (
                  <View key={app.employer_id || i} style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: T.border, alignItems: 'center' }} data-testid={`employer-row-${i}`} testID={`employer-row-${i}`}>
                    <TouchableOpacity style={{ flex: 2 }} accessibilityLabel={tx('admin.employerPortalPanel.auto.accessibility.001', 'Open employer candidate details')} onPress={() => openDetail(app.employer_id)}>
                      <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{app.business_name || app.company_name || 'N/A'}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>{app.industry || app.sector || 'N/A'}</Text>
                    </TouchableOpacity>
                    <View style={{ flex: 1.5 }}>
                      <Text style={{ color: T.text, fontSize: 13 }}>{app.contact_person_name || app.contact_name || 'N/A'}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>{app.email || app.business_email || app.contact_email || 'N/A'}</Text>
                    </View>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 13 }}>{app.country || app.city || 'N/A'}</Text>
                    <View style={{ flex: 0.8 }}>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor(app.status), '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, alignSelf: 'flex-start' }}>
                        <Text style={{ color: statusColor(app.status), fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{app.status?.replace('_', ' ')}</Text>
                      </View>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(riskColor(app.risk_level), '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, alignSelf: 'flex-start', marginTop: 4 }} data-testid={`employer-risk-pill-${app.employer_id}`}>
                        <Text style={{ color: riskColor(app.risk_level), fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{(app.risk_level || 'safe').replace('_', ' ')}</Text>
                      </View>
                    </View>
                    <Text style={{ flex: 1, color: T.textMuted, fontSize: 11 }}>{app.created_at || app.submitted_at ? new Date(app.created_at || app.submitted_at).toLocaleDateString() : 'N/A'}</Text>
                    <View style={{ flex: 1.2, flexDirection: 'row', justifyContent: 'flex-end', gap: 6, flexWrap: 'wrap' }}>
                      <TouchableOpacity onPress={() => openDetail(app.employer_id)} style={{ backgroundColor: T.cyanSoft, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 }} data-testid={`view-${app.employer_id}`} testID={`view-${app.employer_id}`}>
                        <Text style={{ color: T.cyan, fontSize: 10, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.016', 'View')}</Text>
                      </TouchableOpacity>
                      {(app.status === 'pending' || app.status === 'in_review') && (
                        <>
                          <TouchableOpacity onPress={() => openApproveChecklist(app)} disabled={actionLoading === app.employer_id + 'approve'} style={{ backgroundColor: T.successSoft, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 }} data-testid={`approve-${app.employer_id}`} testID={`approve-${app.employer_id}`}>
                            <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }}>{actionLoading === app.employer_id + 'approve' ? '...' : 'Approve'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => handleReview(app.employer_id, 'reject')} disabled={actionLoading === app.employer_id + 'reject'} style={{ backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6 }} data-testid={`reject-${app.employer_id}`} testID={`reject-${app.employer_id}`}>
                            <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{actionLoading === app.employer_id + 'reject' ? '...' : 'Reject'}</Text>
                          </TouchableOpacity>
                        </>
                      )}
                    </View>
                  </View>
                ))}
                {filteredApplications.length === 0 && (
                  <View style={{ padding: 30, alignItems: 'center' }}>
                    <Ionicons name="business-outline" size={36} color={T.textMuted} />
                    <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.employerPortalPanel.auto.text.017', 'No employer applications found')}</Text>
                  </View>
                )}
              </View>
            )}
            renderCompact={() => (
              <View style={{ gap: 8 }}>
                {filteredApplications.map((app, i) => (
                  <View key={app.employer_id || i} style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 12, gap: 8 }} data-testid={`employer-row-${i}`} testID={`employer-row-${i}`}>
                    <TouchableOpacity accessibilityLabel={tx('admin.employerPortalPanel.auto.accessibility.001', 'Open employer candidate details')} onPress={() => openDetail(app.employer_id)}>
                      <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{app.business_name || app.company_name || 'N/A'}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>{app.industry || app.sector || 'N/A'}</Text>
                    </TouchableOpacity>
                    <Text style={{ color: T.textSec, fontSize: 12 }}>{app.contact_person_name || app.contact_name || 'N/A'} • {app.email || app.business_email || app.contact_email || 'N/A'}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.employerPortalPanel.auto.text.012', 'Location')}: {app.country || app.city || 'N/A'} • {tx('admin.employerPortalPanel.auto.text.014', 'Date')}: {app.created_at || app.submitted_at ? new Date(app.created_at || app.submitted_at).toLocaleDateString() : 'N/A'}</Text>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor(app.status), '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 }}>
                        <Text style={{ color: statusColor(app.status), fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{app.status?.replace('_', ' ')}</Text>
                      </View>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(riskColor(app.risk_level), '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 }} data-testid={`employer-risk-pill-${app.employer_id}`} testID={`employer-risk-pill-${app.employer_id}`}>
                        <Text style={{ color: riskColor(app.risk_level), fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{(app.risk_level || 'safe').replace('_', ' ')}</Text>
                      </View>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                      <TouchableOpacity onPress={() => openDetail(app.employer_id)} style={{ backgroundColor: T.cyanSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6 }} data-testid={`view-${app.employer_id}`} testID={`view-${app.employer_id}`}>
                        <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.016', 'View')}</Text>
                      </TouchableOpacity>
                      {(app.status === 'pending' || app.status === 'in_review') && (
                        <>
                          <TouchableOpacity onPress={() => openApproveChecklist(app)} disabled={actionLoading === app.employer_id + 'approve'} style={{ backgroundColor: T.successSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6 }} data-testid={`approve-${app.employer_id}`} testID={`approve-${app.employer_id}`}>
                            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{actionLoading === app.employer_id + 'approve' ? '...' : 'Approve'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => handleReview(app.employer_id, 'reject')} disabled={actionLoading === app.employer_id + 'reject'} style={{ backgroundColor: T.errorSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6 }} data-testid={`reject-${app.employer_id}`} testID={`reject-${app.employer_id}`}>
                            <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }}>{actionLoading === app.employer_id + 'reject' ? '...' : 'Reject'}</Text>
                          </TouchableOpacity>
                        </>
                      )}
                    </View>
                  </View>
                ))}
                {filteredApplications.length === 0 && (
                  <View style={{ padding: 30, alignItems: 'center', backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border }}>
                    <Ionicons name="business-outline" size={36} color={T.textMuted} />
                    <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.employerPortalPanel.auto.text.017', 'No employer applications found')}</Text>
                  </View>
                )}
              </View>
            )}
          />
        </>
      )}

      {/* Detail Modal */}
      {selectedApp && (
        <Modal visible={!!selectedApp} transparent animationType="fade" onRequestClose={() => setSelectedApp(null)}>
          <View style={{ flex: 1, backgroundColor: T.overlay, justifyContent: 'center', alignItems: 'center', padding: 20 }}>
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 16, width: '100%', maxWidth: 960, maxHeight: '85%', borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottomWidth: 1, borderBottomColor: T.border }}>
                <View>
                  <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{selectedApp.business_name || 'Employer Application'}</Text>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 4, alignItems: 'center' }}>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor(selectedApp.status), '20'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 }}>
                      <Text style={{ color: statusColor(selectedApp.status), fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{selectedApp.status?.replace('_', ' ')}</Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>{selectedApp.employer_id}</Text>
                  </View>
                </View>
                <TouchableOpacity onPress={() => setSelectedApp(null)} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: T.card, alignItems: 'center', justifyContent: 'center' }}
                  data-testid="close-employer-detail" testID="close-employer-detail">
                  <Ionicons name="close" size={18} color={T.textMuted} />
                </TouchableOpacity>
              </View>

              <ScrollView style={{ padding: 20, maxHeight: 450 }}>
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(riskColor(selectedApp.risk_level), '18'), borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(riskColor(selectedApp.risk_level), '44'), paddingHorizontal: 10, paddingVertical: 6 }} data-testid="selected-employer-risk-level">
                    <Text style={{ color: riskColor(selectedApp.risk_level), fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>
                      {(selectedApp.risk_level || 'safe').replace('_', ' ')}
                    </Text>
                  </View>
                  <View style={{ backgroundColor: T.card, borderRadius: 999, borderWidth: 1, borderColor: T.border, paddingHorizontal: 10, paddingVertical: 6 }}>
                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>Risk Score: {selectedApp.risk_score ?? 0}</Text>
                  </View>
                  <View style={{ backgroundColor: T.successSoft, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '33'), paddingHorizontal: 10, paddingVertical: 6 }}>
                    <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>Trust Score: {selectedApp.trust_score ?? 100}</Text>
                  </View>
                </View>

                {/* Info Grid */}
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                  {[
                    { l: 'Contact', v: selectedApp.contact_person_name || selectedApp.contact_name },
                    { l: 'Email', v: selectedApp.email || selectedApp.business_email },
                    { l: 'Phone', v: selectedApp.phone_number || selectedApp.phone },
                    { l: 'Industry', v: selectedApp.industry || selectedApp.sector },
                    { l: 'Country', v: selectedApp.country },
                    { l: 'Company Size', v: selectedApp.company_size || selectedApp.employee_count },
                    { l: 'Website', v: selectedApp.website },
                    { l: 'Registration', v: selectedApp.registration_number },
                  ].filter(f => f.v).map((field, i) => (
                    <View key={i} style={{ flex: 1, minWidth: 200, backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: T.border }}>
                      <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', marginBottom: 4 }}>{field.l}</Text>
                      <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{field.v}</Text>
                    </View>
                  ))}
                </View>

                {/* Description */}
                {selectedApp.description && (
                  <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 16, borderLeftWidth: 3, borderLeftColor: T.primary }}>
                    <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', marginBottom: 6 }}>{tx('admin.employerPortalPanel.auto.text.018', 'Description')}</Text>
                    <Text style={{ color: T.text, fontSize: 13, lineHeight: 20 }}>{selectedApp.description}</Text>
                  </View>
                )}

                {/* Uploaded verification documents */}
                <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="selected-employer-documents" testID="selected-employer-documents">
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', marginBottom: 8 }}>{tx('admin.employerPortalPanel.auto.text.019', 'Verification Documents')}</Text>
                  {(selectedApp.documents || []).length === 0 ? (
                    <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.employerPortalPanel.auto.text.020', 'No documents uploaded.')}</Text>
                  ) : (
                    (selectedApp.documents || []).map((doc: any, i: number) => (
                      <View key={doc.doc_id || i} style={{ backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: T.border, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                        {String(doc.content_type || '').startsWith('image/') && docPreviewUrls[doc.doc_id] && Platform.OS === 'web' ? (
                          React.createElement('img', {
                            src: docPreviewUrls[doc.doc_id],
                            alt: doc.original_filename || doc.filename,
                            style: {
                              width: 42,
                              height: 42,
                              borderRadius: 8,
                              objectFit: 'cover',
                              border: `1px solid ${T.border}`,
                            },
                            'data-testid': `selected-employer-doc-thumb-${doc.doc_id}`,
                          })
                        ) : (
                          <Ionicons name={String(doc.content_type || '').includes('pdf') ? 'document-text' : 'image'} size={16} color={T.cyan} />
                        )}
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{String(doc.type || 'document').replace(/_/g, ' ')}</Text>
                          <Text style={{ color: T.textSec, fontSize: 11 }}>{doc.original_filename || doc.filename}</Text>
                          {!!doc.purpose && <Text style={{ color: T.textMuted, fontSize: 10 }}>Purpose: {String(doc.purpose).replace(/_/g, ' ')}</Text>}
                          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid={`selected-employer-doc-checksum-${doc.doc_id}`} testID={`selected-employer-doc-checksum-${doc.doc_id}`}>
                            SHA-256: {doc.checksum_sha256 ? String(doc.checksum_sha256).slice(0, 18) + '…' : 'N/A'}
                          </Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => openDocPreviewModal(selectedApp.employer_id, selectedApp.documents || [], i)}
                          disabled={previewLoadingDocId === String(doc.doc_id)}
                          style={{ backgroundColor: T.cyanSoft, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '33'), paddingHorizontal: 10, paddingVertical: 8 }}
                          data-testid={`selected-employer-doc-preview-${doc.doc_id}`}
                          testID={`selected-employer-doc-preview-${doc.doc_id}`}
                        >
                          {previewLoadingDocId === String(doc.doc_id) ? (
                            <ActivityIndicator size="small" color={T.cyan} />
                          ) : (
                            <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.021', 'Preview')}</Text>
                          )}
                        </TouchableOpacity>
                      </View>
                    ))
                  )}
                </View>

                {/* Actions */}
                {(selectedApp.status === 'pending' || selectedApp.status === 'in_review') && (
                  <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
                    <TouchableOpacity onPress={() => openApproveChecklist(selectedApp)} disabled={actionLoading !== null}
                      style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, backgroundColor: T.success, borderRadius: 8 }}
                      data-testid="modal-approve-btn" testID="modal-approve-btn">
                      <Ionicons name="checkmark-circle" size={16} color="var(--app-primary-text)" />
                      <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.022', 'Approve')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleReview(selectedApp.employer_id, 'reject')} disabled={actionLoading !== null}
                      style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, backgroundColor: T.error, borderRadius: 8 }}
                      data-testid="modal-reject-btn" testID="modal-reject-btn">
                      <Ionicons name="close-circle" size={16} color="var(--app-primary-text)" />
                      <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.023', 'Reject')}</Text>
                    </TouchableOpacity>
                  </View>
                )}

                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                  <TouchableOpacity onPress={() => handleAiRiskAssessment(selectedApp.employer_id)}
                    style={{ backgroundColor: T.cyanSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}
                    data-testid="modal-risk-refresh-btn" testID="modal-risk-refresh-btn">
                    <Text style={{ color: T.cyan, fontSize: 12, fontWeight: '700' }}>{actionLoading === selectedApp.employer_id + 'risk' ? 'Refreshing...' : 'AI Risk Refresh'}</Text>
                  </TouchableOpacity>

                  <TouchableOpacity onPress={() => handleAccessControl(selectedApp.employer_id, 'suspend')}
                    style={{ backgroundColor: T.warningSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}
                    data-testid="modal-suspend-btn" testID="modal-suspend-btn">
                    <Text style={{ color: T.warningText, fontSize: 12, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.024', 'Suspend Access')}</Text>
                  </TouchableOpacity>

                  <TouchableOpacity onPress={() => handleAccessControl(selectedApp.employer_id, 'revoke')}
                    style={{ backgroundColor: T.errorSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}
                    data-testid="modal-revoke-btn" testID="modal-revoke-btn">
                    <Text style={{ color: T.error, fontSize: 12, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.025', 'Revoke Access')}</Text>
                  </TouchableOpacity>

                  <TouchableOpacity onPress={() => handleAccessControl(selectedApp.employer_id, 'restore')}
                    style={{ backgroundColor: T.successSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}
                    data-testid="modal-restore-btn" testID="modal-restore-btn">
                    <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.026', 'Restore Access')}</Text>
                  </TouchableOpacity>
                </View>

                <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="employer-communications-hub">
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', marginBottom: 8 }}>{tx('admin.employerPortalPanel.auto.text.027', 'Communication Hub')}</Text>

                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employerPortalPanel.auto.text.028', 'In-App Messages')}</Text>
                  {(comms.messages || []).slice(0, 5).map((msg: any, i: number) => (
                    <View key={msg.message_id || i} style={{ backgroundColor: T.bgSoft, borderRadius: 8, padding: 9, marginBottom: 6, borderWidth: 1, borderColor: T.border }} data-testid={`comm-msg-${i}`}>
                      <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700' }}>{msg.sender_role?.toUpperCase()} • {new Date(msg.created_at).toLocaleString()}</Text>
                      <Text style={{ color: T.text, fontSize: 12, marginTop: 3 }}>{msg.message}</Text>
                    </View>
                  ))}
                  {(comms.messages || []).length === 0 && <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 8 }}>{tx('admin.employerPortalPanel.auto.text.029', 'No in-app messages yet.')}</Text>}

                  <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
                    <TextInput
                      value={newMessage}
                      onChangeText={setNewMessage}
                      placeholder={tx('admin.employerPortalPanel.auto.placeholder.002', 'Send message to employer...')}
                      placeholderTextColor={T.textMuted}
                      style={{ flex: 1, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: T.text, fontSize: 12 } as any}
                      data-testid="admin-employer-message-input"
                      testID="admin-employer-message-input"
                    />
                    <TouchableOpacity onPress={() => sendAdminMessage(selectedApp.employer_id)} disabled={!newMessage.trim() || sendingMessage}
                      style={{ backgroundColor: T.primary, borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center', opacity: !newMessage.trim() || sendingMessage ? 0.5 : 1 }}
                      data-testid="admin-employer-send-message-btn" testID="admin-employer-send-message-btn">
                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{sendingMessage ? '...' : 'Send'}</Text>
                    </TouchableOpacity>
                  </View>

                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employerPortalPanel.auto.text.030', 'Email Timeline')}</Text>
                  {(selectedApp.email_timeline || comms.email_timeline || []).slice(0, 6).map((emailEvent: any, i: number) => (
                    <View key={emailEvent.email_log_id || i} style={{ backgroundColor: T.bgSoft, borderRadius: 8, padding: 9, marginBottom: 6, borderWidth: 1, borderColor: T.border }} data-testid={`comm-email-${i}`}>
                      <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700' }}>{String(emailEvent.status || 'unknown').toUpperCase()} • {emailEvent.recipient_email}</Text>
                      <Text style={{ color: T.text, fontSize: 11, marginTop: 3 }}>{emailEvent.subject}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{new Date(emailEvent.created_at).toLocaleString()}</Text>
                    </View>
                  ))}
                  {((selectedApp.email_timeline || comms.email_timeline || []).length === 0) && <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.employerPortalPanel.auto.text.031', 'No email events logged yet.')}</Text>}
                </View>

                {/* Admin Notes */}
                <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', marginBottom: 8 }}>{tx('admin.employerPortalPanel.auto.text.032', 'Admin Notes')}</Text>
                  {(selectedApp.admin_notes || selectedApp.internal_notes || []).map((note: any, i: number) => (
                    <View key={i} style={{ backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, marginBottom: 6, borderLeftWidth: 2, borderLeftColor: T.primary }}>
                      <Text style={{ color: T.text, fontSize: 12 }}>{note.note || note.text || note}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{note.created_at ? new Date(note.created_at).toLocaleString() : ''}</Text>
                    </View>
                  ))}
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                    <TextInput placeholder={tx('admin.employerPortalPanel.auto.placeholder.003', 'Add a note...')} placeholderTextColor={T.textMuted} value={noteText} onChangeText={setNoteText}
                      style={{ flex: 1, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: T.text, fontSize: 13 } as any}
                      data-testid="employer-note-input" testID="employer-note-input" />
                    <TouchableOpacity onPress={handleAddNote} disabled={!noteText.trim()}
                      style={{ backgroundColor: T.primary, paddingHorizontal: 16, borderRadius: 8, alignItems: 'center', justifyContent: 'center', opacity: !noteText.trim() ? 0.5 : 1 }}
                      data-testid="employer-add-note-btn" testID="employer-add-note-btn">
                      <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.033', 'Add')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </ScrollView>
            </View>
          </View>
        </Modal>
      )}

      {/* Document preview modal */}
      {docPreviewModalOpen && (
        <Modal visible={docPreviewModalOpen} transparent animationType="fade" onRequestClose={() => { setDocPreviewModalOpen(false); setDocPreviewEmployerId(''); }}>
          <View style={{ flex: 1, backgroundColor: T.overlay, justifyContent: 'center', alignItems: 'center', padding: 20 }}>
            <View style={{ width: '100%', maxWidth: 960, maxHeight: '90%', backgroundColor: T.bgSoft, borderRadius: 14, borderWidth: 1, borderColor: T.border }} data-testid="employer-doc-preview-modal" testID="employer-doc-preview-modal">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: T.border }}>
                <View>
                  <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.employerPortalPanel.auto.text.034', 'Document Preview')}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{docPreviewIndex + 1} / {docPreviewDocs.length} · {currentPreviewDoc?.original_filename || currentPreviewDoc?.filename || 'document'}</Text>
                </View>
                <TouchableOpacity onPress={() => { setDocPreviewModalOpen(false); setDocPreviewEmployerId(''); }} data-testid="close-employer-doc-preview" testID="close-employer-doc-preview">
                  <Ionicons name="close" size={20} color={T.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  onPress={() => setDocPreviewIndex((p) => Math.max(0, p - 1))}
                  disabled={docPreviewIndex <= 0}
                  style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, opacity: docPreviewIndex <= 0 ? 0.5 : 1 }}
                  data-testid="employer-doc-preview-prev"
                  testID="employer-doc-preview-prev"
                ><Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.035', 'Prev')}</Text></TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setDocPreviewIndex((p) => Math.min(docPreviewDocs.length - 1, p + 1))}
                  disabled={docPreviewIndex >= docPreviewDocs.length - 1}
                  style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, opacity: docPreviewIndex >= docPreviewDocs.length - 1 ? 0.5 : 1 }}
                  data-testid="employer-doc-preview-next"
                  testID="employer-doc-preview-next"
                ><Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.036', 'Next')}</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setDocPreviewZoom((z) => Math.max(0.5, z - 0.25))} style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="employer-doc-preview-zoom-out" testID="employer-doc-preview-zoom-out"><Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>-</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setDocPreviewZoom(1)} style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="employer-doc-preview-zoom-reset" testID="employer-doc-preview-zoom-reset"><Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>100%</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setDocPreviewZoom((z) => Math.min(3, z + 0.25))} style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="employer-doc-preview-zoom-in" testID="employer-doc-preview-zoom-in"><Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>+</Text></TouchableOpacity>
              </View>

              <View style={{ flex: 1, minHeight: 460, backgroundColor: T.bg }}>
                {currentPreviewDoc ? (
                  (() => {
                    const previewUrl = docPreviewUrls[currentPreviewDoc.doc_id];
                    if (!previewUrl) {
                      return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
                    }
                    if (String(currentPreviewDoc.content_type || '').includes('pdf') && Platform.OS === 'web') {
                      return React.createElement('iframe', {
                        src: previewUrl,
                        style: { width: '100%', height: '100%', border: 'none' },
                        'data-testid': 'employer-doc-preview-pdf',
                      });
                    }
                    if (Platform.OS === 'web') {
                      return React.createElement('div', {
                        style: { width: '100%', height: '100%', overflow: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'center' },
                        children: React.createElement('img', {
                          src: previewUrl,
                          alt: currentPreviewDoc.original_filename || currentPreviewDoc.filename,
                          style: { transform: `scale(${docPreviewZoom})`, transformOrigin: 'center center', maxWidth: '88%', maxHeight: '88%', transition: 'transform 120ms ease' },
                          'data-testid': 'employer-doc-preview-image',
                        }),
                      });
                    }
                    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: T.textMuted }}>{tx('admin.employerPortalPanel.auto.text.037', 'Preview supported on web dashboard.')}</Text></View>;
                  })()
                ) : (
                  <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: T.textMuted }}>{tx('admin.employerPortalPanel.auto.text.038', 'No document selected.')}</Text></View>
                )}
              </View>
            </View>
          </View>
        </Modal>
      )}

      {/* Approve with checklist modal */}
      {checklistModalOpen && (
        <Modal visible={checklistModalOpen} transparent animationType="fade" onRequestClose={() => setChecklistModalOpen(false)}>
          <View style={{ flex: 1, backgroundColor: T.overlay, alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <View style={{ width: '100%', maxWidth: 560, backgroundColor: T.bgSoft, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid="approve-checklist-modal" testID="approve-checklist-modal">
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800', marginBottom: 6 }}>{tx('admin.employerPortalPanel.auto.text.039', 'Approve with Checklist')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 12 }}>{tx('admin.employerPortalPanel.auto.text.040', 'Complete all verification checks before approving this employer.')}</Text>

              {[
                { key: 'doc', label: 'Document completeness verified', value: checkDocCompleteness, set: setCheckDocCompleteness, id: 'approve-check-doc-completeness' },
                { key: 'identity', label: 'Identity match verified', value: checkIdentityMatch, set: setCheckIdentityMatch, id: 'approve-check-identity-match' },
                { key: 'fraud', label: 'Fraud risk reviewed', value: checkFraudReviewed, set: setCheckFraudReviewed, id: 'approve-check-fraud-risk' },
              ].map((item) => (
                <TouchableOpacity key={item.key} onPress={() => item.set(!item.value)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }} data-testid={item.id} testID={item.id}>
                  <View style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1, borderColor: item.value ? T.success : T.border, backgroundColor: item.value ? T.successSoft : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                    {item.value && <Ionicons name="checkmark" size={12} color={T.successText} />}
                  </View>
                  <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600' }}>{item.label}</Text>
                </TouchableOpacity>
              ))}

              <TextInput
                value={checklistNote}
                onChangeText={setChecklistNote}
                placeholder={tx('admin.employerPortalPanel.auto.placeholder.004', 'Reviewer note (required)')}
                placeholderTextColor={T.textMuted}
                multiline
                style={{ minHeight: 90, backgroundColor: T.bg, borderWidth: 1, borderColor: T.border, borderRadius: 10, color: T.text, padding: 10, fontSize: 12, marginTop: 4 }}
                data-testid="approve-checklist-note"
                testID="approve-checklist-note"
              />

              <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
                <TouchableOpacity onPress={() => setChecklistModalOpen(false)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="approve-checklist-cancel" testID="approve-checklist-cancel">
                  <Text style={{ color: T.textMuted, fontSize: 12, fontWeight: '700' }}>{tx('admin.employerPortalPanel.auto.text.041', 'Cancel')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={submitApproveChecklist}
                  disabled={submittingChecklist || !checkDocCompleteness || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim()}
                  style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: T.success, opacity: submittingChecklist || !checkDocCompleteness || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim() ? 0.55 : 1 }}
                  data-testid="approve-checklist-confirm"
                  testID="approve-checklist-confirm"
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{submittingChecklist ? 'Approving…' : 'Approve'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}
