import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecStyles, useExecTheme } from '../admin/ExecDashboardPanels';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface IDVProps {
  idvData: any;
  idvOverrideLoading: string;
  setIdvOverrideLoading: (id: string) => void;
  loadData: () => void;
  setLightboxAtts: (atts: any[]) => void;
  setLightboxOpen: (open: boolean) => void;
}

const STATUS_FILTERS = ['ALL', 'ADMIN_REVIEW', 'PENDING', 'AI_REVIEW', 'MORE_INFO_REQUIRED', 'APPROVED', 'REJECTED'];
const RISK_FILTERS = ['all', 'high', 'medium', 'low', 'unknown'];

const stateLabel = (state: string) => String(state || 'UNKNOWN').replaceAll('_', ' ');

const riskTone = (theme: any, risk: string) => {
  const key = String(risk || '').toLowerCase();
  if (key === 'high') return { bg: theme.errorSoft, fg: theme.error };
  if (key === 'medium') return { bg: theme.warningSoft, fg: theme.warningText };
  if (key === 'low') return { bg: theme.successSoft, fg: theme.successText };
  return { bg: theme.bgSoft, fg: theme.textMuted };
};

const workflowTone = (theme: any, workflow: string) => {
  const wf = String(workflow || '').toUpperCase();
  if (wf === 'APPROVED') return { bg: theme.successSoft, fg: theme.successText };
  if (wf === 'REJECTED') return { bg: theme.errorSoft, fg: theme.error };
  if (wf === 'MORE_INFO_REQUIRED') return { bg: theme.warningSoft, fg: theme.warningText };
  if (wf === 'ADMIN_REVIEW' || wf === 'AI_REVIEW' || wf === 'PENDING') return { bg: theme.primarySoft, fg: theme.primary };
  return { bg: theme.bgSoft, fg: theme.textMuted };
};

export function ExecIDCheckerPanel({
  idvData,
  idvOverrideLoading,
  setIdvOverrideLoading,
  loadData,
  setLightboxAtts,
  setLightboxOpen,
}: IDVProps) {
  const s = useExecStyles();
  const THEME = useExecTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const isNarrow = width < 980;
  const isMobile = width < 740;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const sseRef = useRef<EventSource | null>(null);
  const [streamSummary, setStreamSummary] = useState<any>(null);
  const [opsKpis, setOpsKpis] = useState<any>(null);
  const [conversionFunnel, setConversionFunnel] = useState<any>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueStatus, setQueueStatus] = useState('ALL');
  const [queueRisk, setQueueRisk] = useState('all');
  const [queueCountry, setQueueCountry] = useState('all');
  const [queueRows, setQueueRows] = useState<any[]>([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedCase, setSelectedCase] = useState<any>(null);
  const [selectedCaseLoading, setSelectedCaseLoading] = useState(false);
  const [reviewModeEnabled, setReviewModeEnabled] = useState(false);
  const [activeCaseIndex, setActiveCaseIndex] = useState(0);
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiModalLoading, setAiModalLoading] = useState(false);
  const [aiModalData, setAiModalData] = useState<any>(null);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [actionModalType, setActionModalType] = useState<'request_more_info' | 'force_approve' | 'force_reject' | 'ban' | ''>('');
  const [actionModalTargetUser, setActionModalTargetUser] = useState('');
  const [actionReason, setActionReason] = useState('');

  const countryOptions = useMemo(() => {
    const base = Array.isArray(idvData?.country_breakdown)
      ? idvData.country_breakdown.map((row: any) => String(row?._id || '').toUpperCase()).filter(Boolean)
      : [];
    return ['all', ...Array.from(new Set(base)).sort()];
  }, [idvData?.country_breakdown]);

  const fallbackQueue = useMemo(() => {
    const rows = Array.isArray(idvData?.recent_submissions) ? idvData.recent_submissions : [];
    return rows.map((sub: any) => ({
      user_id: sub.user_id,
      full_name: sub.full_name,
      country: sub.nationality,
      status: sub.status,
      workflow_state: sub.workflow_state,
      submitted_at: sub.submitted_at,
      risk_level: sub.ai_risk_level || 'unknown',
      ai_confidence: sub.ai_confidence,
      documents_count: sub.documents_count || 0,
      suggested_action: sub?.ai_verification?.recommendation || 'manual_review',
      document_front_url: sub.document_front_url,
      document_back_url: sub.document_back_url,
      selfie_url: sub.selfie_url,
    }));
  }, [idvData?.recent_submissions]);

  const effectiveRows = queueRows.length ? queueRows : fallbackQueue;
  const activeCase = reviewModeEnabled && effectiveRows.length
    ? effectiveRows[Math.min(activeCaseIndex, effectiveRows.length - 1)]
    : null;

  const queueStats = useMemo(() => {
    const source = effectiveRows;
    const total = source.length;
    const approved = source.filter((row) => String(row.workflow_state || row.status || '').toUpperCase() === 'APPROVED').length;
    const rejected = source.filter((row) => String(row.workflow_state || row.status || '').toUpperCase() === 'REJECTED').length;
    const pending = source.filter((row) => {
      const wf = String(row.workflow_state || row.status || '').toUpperCase();
      return ['PENDING', 'AI_REVIEW', 'ADMIN_REVIEW', 'MORE_INFO_REQUIRED'].includes(wf);
    }).length;
    return { total, approved, rejected, pending };
  }, [effectiveRows]);

  const openDocuments = useCallback((row: any, caseDetail?: any) => {
    const assets = caseDetail?.document_assets || {};
    const atts: any[] = [];
    const push = (url: string | undefined, name: string) => {
      if (!url) return;
      atts.push({ url, original_name: name, mime_type: 'image/jpeg' });
    };
    push(assets?.id_front || row?.document_front_url, tx('executive.idChecker.docs.idFront', 'ID Front'));
    push(assets?.id_back || row?.document_back_url, tx('executive.idChecker.docs.idBack', 'ID Back'));
    push(assets?.selfie || row?.selfie_url, tx('executive.idChecker.docs.selfie', 'Selfie'));
    if (!atts.length) return;
    setLightboxAtts(atts);
    setLightboxOpen(true);
  }, [setLightboxAtts, setLightboxOpen, tx]);

  const loadQueue = useCallback(async () => {
    setQueueLoading(true);
    try {
      const res = await api.get('/id-checker/admin/queue', {
        params: {
          status: queueStatus,
          risk_level: queueRisk,
          country: queueCountry,
          limit: 140,
        },
      });
      const rows = Array.isArray(res?.data?.queue) ? res.data.queue : [];
      setQueueRows(rows);
      if (!selectedUserId && rows.length) {
        setSelectedUserId(rows[0].user_id);
      }
      if (selectedUserId && rows.length && !rows.some((row: any) => row.user_id === selectedUserId)) {
        setSelectedUserId(rows[0].user_id);
      }
    } catch {
      setQueueRows([]);
    } finally {
      setQueueLoading(false);
    }
  }, [queueCountry, queueRisk, queueStatus, selectedUserId]);

  const loadCommercialMetrics = useCallback(async () => {
    try {
      const [opsRes, funnelRes] = await Promise.all([
        api.get('/id-checker/admin/operations-kpis', { params: { lookback_days: 30 } }),
        api.get('/id-checker/admin/conversion-funnel', { params: { lookback_days: 30 } }),
      ]);
      setOpsKpis(opsRes?.data || null);
      setConversionFunnel(funnelRes?.data || null);
    } catch {
      setOpsKpis(null);
      setConversionFunnel(null);
    }
  }, []);

  const loadCaseDetail = useCallback(async (userId: string) => {
    if (!userId) {
      setSelectedCase(null);
      return;
    }
    setSelectedCaseLoading(true);
    try {
      const res = await api.get(`/id-checker/admin/case/${userId}`);
      setSelectedCase(res.data);
    } catch {
      setSelectedCase(null);
    } finally {
      setSelectedCaseLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  useEffect(() => {
    loadCommercialMetrics();
  }, [loadCommercialMetrics]);

  useEffect(() => {
    if (activeCaseIndex <= Math.max(effectiveRows.length - 1, 0)) return;
    setActiveCaseIndex(0);
  }, [activeCaseIndex, effectiveRows.length]);

  useEffect(() => {
    if (reviewModeEnabled && activeCase?.user_id) {
      setSelectedUserId(activeCase.user_id);
    }
  }, [activeCase?.user_id, reviewModeEnabled]);

  useEffect(() => {
    if (!selectedUserId) return;
    loadCaseDetail(selectedUserId);
  }, [loadCaseDetail, selectedUserId]);

  useEffect(() => {
    if (!reviewModeEnabled || typeof window === 'undefined' || !effectiveRows.length) return;
    const onKeyDown = (ev: any) => {
      const target = ev?.target as any;
      const tag = String(target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return;
      const key = String(ev?.key || '').toLowerCase();
      if (['j', 'n', 'arrowdown'].includes(key)) {
        ev.preventDefault();
        setActiveCaseIndex((prev) => Math.min(prev + 1, effectiveRows.length - 1));
      } else if (['k', 'p', 'arrowup'].includes(key)) {
        ev.preventDefault();
        setActiveCaseIndex((prev) => Math.max(prev - 1, 0));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [effectiveRows.length, reviewModeEnabled]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof (window as any).EventSource !== 'function') return;
    const token = localStorage.getItem('session_token') || localStorage.getItem('auth_token') || '';
    if (!token) return;
    const base = (window.location?.origin || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
    if (!base) return;
    let fallbackTimer: any = null;
    const url = `${base}/api/id-checker/admin/queue/stream?token=${encodeURIComponent(token)}&interval_seconds=6`;
    try {
      const stream = new EventSource(url);
      sseRef.current = stream;
      stream.addEventListener('queue_tick', (event: Event) => {
        const messageEvent = event as MessageEvent;
        try {
          const payload = JSON.parse(String(messageEvent.data || '{}'));
          setStreamSummary(payload);
          loadQueue();
          loadData();
        } catch {
          loadQueue();
        }
      });
      stream.onerror = () => {
        try { stream.close(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/ExecIDCheckerPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        sseRef.current = null;
        if (!fallbackTimer) {
          fallbackTimer = setInterval(() => {
            loadQueue();
            loadData();
          }, 12000);
        }
      };
    } catch {
      fallbackTimer = setInterval(() => {
        loadQueue();
      }, 12000);
    }
    return () => {
      if (sseRef.current) {
        try { sseRef.current.close(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/ExecIDCheckerPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        sseRef.current = null;
      }
      if (fallbackTimer) clearInterval(fallbackTimer);
    };
  }, [loadData, loadQueue]);

  const openAiModal = async (userId: string) => {
    if (!userId) return;
    setAiModalOpen(true);
    setAiModalLoading(true);
    try {
      const res = await api.get(`/id-checker/admin/ai-analysis/${userId}`);
      setAiModalData(res.data || null);
    } catch {
      setAiModalData(null);
    } finally {
      setAiModalLoading(false);
    }
  };

  const runOverrideAction = async (
    userId: string,
    action: 'request_more_info' | 'force_approve' | 'force_reject' | 'ban',
    reason: string,
  ) => {
    const loadKey = `${userId}_${action}`;
    setIdvOverrideLoading(loadKey);
    try {
      const payload: any = { user_id: userId, action };
      if (reason.trim()) payload.reason = reason.trim();
      await api.post('/id-checker/admin/override', payload);
      await Promise.all([loadQueue(), loadData()]);
      await loadCaseDetail(userId);
    } finally {
      setIdvOverrideLoading('');
    }
  };

  const openActionModal = (
    userId: string,
    action: 'request_more_info' | 'force_approve' | 'force_reject' | 'ban',
    defaultReason = '',
  ) => {
    if (!userId) return;
    setActionModalTargetUser(userId);
    setActionModalType(action);
    setActionReason(defaultReason);
    setActionModalOpen(true);
  };

  const actionText = (action: string) => {
    if (action === 'request_more_info') return tx('executive.idChecker.actions.moreInfo', 'More Info');
    if (action === 'force_approve') return tx('executive.idChecker.actions.approve', 'Approve');
    if (action === 'force_reject') return tx('executive.idChecker.actions.reject', 'Reject');
    if (action === 'ban') return tx('executive.idChecker.actions.ban', 'Ban');
    return action;
  };

  return (
    <View data-testid="id-checker-enterprise-panel" testID="id-checker-enterprise-panel">
      <View style={[s.panel, { marginBottom: 14 }]} data-testid="id-checker-enterprise-header" testID="id-checker-enterprise-header">
        <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Text style={[s.chartTitle, { marginBottom: 6 }]} data-testid="id-checker-enterprise-title" testID="id-checker-enterprise-title">
              {tx('executive.idChecker.title', 'ID Checker Command Center')}
            </Text>
            <Text style={{ color: THEME.textMuted, fontSize: 12 }} data-testid="id-checker-enterprise-subtitle" testID="id-checker-enterprise-subtitle">
              {tx('executive.idChecker.subtitle', 'Enterprise reviewer workspace with live queue intelligence and AI-assisted case actions.')}
            </Text>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: THEME.successSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="id-checker-live-chip" testID="id-checker-live-chip">
              <View style={{ width: 8, height: 8, borderRadius: 99, backgroundColor: THEME.success }} />
              <Text style={{ color: THEME.successText, fontSize: 10, fontWeight: '800' }}>{tx('executive.idChecker.live', 'LIVE')}</Text>
            </View>
            <TouchableOpacity
              onPress={() => { loadQueue(); loadData(); loadCommercialMetrics(); }}
              style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center' }}
              data-testid="id-checker-refresh-button"
              testID="id-checker-refresh-button"
            >
              <Ionicons name="refresh" size={13} color={THEME.textSec} />
              <Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>{tx('executive.idChecker.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Id checker export csv button"
              onPress={() => {
                const apiBase = (typeof window !== 'undefined' && window.location?.origin
                  ? window.location.origin
                  : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')).replace(/\/+$/, '');
                const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') || localStorage.getItem('auth_token') : '';
                if (typeof window !== 'undefined' && apiBase) window.open(`${apiBase}/api/id-checker/admin/export/csv?token=${token}`, '_blank');
              }}
              style={{ backgroundColor: THEME.successSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center' }}
              data-testid="id-checker-export-csv-button"
              testID="id-checker-export-csv-button"
            >
              <Ionicons name="download-outline" size={13} color={THEME.successText} />
              <Text style={{ color: THEME.successText, fontSize: 11, fontWeight: '800' }}>{tx('executive.idChecker.exportCsv', 'Export CSV')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Id checker export pdf button"
              onPress={() => {
                const apiBase = (typeof window !== 'undefined' && window.location?.origin
                  ? window.location.origin
                  : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')).replace(/\/+$/, '');
                const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') || localStorage.getItem('auth_token') : '';
                if (typeof window !== 'undefined' && apiBase) window.open(`${apiBase}/api/id-checker/admin/export/pdf?token=${token}`, '_blank');
              }}
              style={{ backgroundColor: THEME.primarySoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center' }}
              data-testid="id-checker-export-pdf-button"
              testID="id-checker-export-pdf-button"
            >
              <Ionicons name="document-outline" size={13} color={THEME.primary} />
              <Text style={{ color: THEME.primary, fontSize: 11, fontWeight: '800' }}>{tx('executive.idChecker.exportPdf', 'Export PDF')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {streamSummary && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }} data-testid="id-checker-stream-summary" testID="id-checker-stream-summary">
            <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="id-checker-stream-pending-chip" testID="id-checker-stream-pending-chip">
              <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.pendingWorkload', 'Pending Workload')}: {streamSummary?.pending_workload ?? 0}</Text>
            </View>
            <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="id-checker-stream-risk-chip" testID="id-checker-stream-risk-chip">
              <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>
                {tx('executive.idChecker.riskMix', 'Risk Mix H/M/L')}: {streamSummary?.risk_counts?.high ?? 0}/{streamSummary?.risk_counts?.medium ?? 0}/{streamSummary?.risk_counts?.low ?? 0}
              </Text>
            </View>
            <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="id-checker-stream-admin-review-chip" testID="id-checker-stream-admin-review-chip">
              <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>
                {tx('executive.idChecker.adminReview', 'Admin Review')}: {streamSummary?.state_counts?.ADMIN_REVIEW ?? 0}
              </Text>
            </View>
          </View>
        )}

        <View style={s.metricsRow}>
          {[
            { key: 'total', label: tx('executive.idChecker.metrics.total', 'Total Submissions'), value: idvData?.overview?.total_submissions ?? queueStats.total, icon: 'document-text', color: THEME.primary },
            { key: 'pending', label: tx('executive.idChecker.metrics.pending', 'Pending Review'), value: idvData?.overview?.pending_review ?? queueStats.pending, icon: 'time', color: THEME.warningText },
            { key: 'approved', label: tx('executive.idChecker.metrics.approved', 'Approved'), value: idvData?.overview?.approved ?? queueStats.approved, icon: 'checkmark-circle', color: THEME.successText },
            { key: 'rejected', label: tx('executive.idChecker.metrics.rejected', 'Rejected'), value: idvData?.overview?.rejected ?? queueStats.rejected, icon: 'close-circle', color: THEME.error },
          ].map((metric) => (
            <View key={metric.key} style={s.metricBox} data-testid={`id-checker-metric-${metric.key}`} testID={`id-checker-metric-${metric.key}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name={metric.icon as any} size={14} color={metric.color} />
                <Text style={s.metricLabel}>{metric.label}</Text>
              </View>
              <Text style={s.metricValue}>{metric.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 }} data-testid="id-checker-commercial-kpis" testID="id-checker-commercial-kpis">
          {[
            {
              key: 'approval-rate',
              label: tx('executive.idChecker.metrics.approvalRate', 'Approval Rate'),
              value: `${opsKpis?.approval_rate_pct ?? 0}%`,
              tone: THEME.successText,
            },
            {
              key: 'doc-completion',
              label: tx('executive.idChecker.metrics.docCompletion', 'Doc Completion'),
              value: `${opsKpis?.document_completion_rate_pct ?? 0}%`,
              tone: THEME.primary,
            },
            {
              key: 'sla-breach',
              label: tx('executive.idChecker.metrics.slaBreach', 'SLA Breaches'),
              value: `${opsKpis?.sla_breach_cases ?? 0}`,
              tone: THEME.error,
            },
            {
              key: 'submitted-to-approved',
              label: tx('executive.idChecker.metrics.submittedToApproved', 'Submitted → Approved'),
              value: `${conversionFunnel?.conversion_rates_pct?.submitted_to_approved ?? 0}%`,
              tone: THEME.warningText,
            },
          ].map((item) => (
            <View key={item.key} style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 8, minWidth: 160 }} data-testid={`id-checker-commercial-kpi-${item.key}`} testID={`id-checker-commercial-kpi-${item.key}`}>
              <Text style={{ color: THEME.textMuted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
              <Text style={{ color: item.tone, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{item.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ marginTop: 8, backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-funnel-insights" testID="id-checker-funnel-insights">
          <Text style={{ color: THEME.text, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{tx('executive.idChecker.funnel.insights', 'Funnel Insights')}</Text>
          {Array.isArray(conversionFunnel?.insights) && conversionFunnel.insights.length > 0 ? (
            conversionFunnel.insights.slice(0, 2).map((insight: string, idx: number) => (
              <Text key={`${insight}_${idx}`} style={{ color: THEME.textMuted, fontSize: 10, lineHeight: 15 }} data-testid={`id-checker-funnel-insight-${idx}`} testID={`id-checker-funnel-insight-${idx}`}>
                • {insight}
              </Text>
            ))
          ) : (
            <Text style={{ color: THEME.textMuted, fontSize: 10, lineHeight: 15 }} data-testid="id-checker-funnel-insight-empty" testID="id-checker-funnel-insight-empty">
              • Funnel data not available yet. Drive new submissions to generate conversion intelligence.
            </Text>
          )}
        </View>
      </View>

      <View style={[s.panel, { marginBottom: 12 }]} data-testid="id-checker-filters-panel" testID="id-checker-filters-panel">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '700' }}>{tx('executive.idChecker.filters.workflow', 'Workflow')}</Text>
          {STATUS_FILTERS.map((status) => (
            <TouchableOpacity accessibilityLabel="Set queue status in exec idchecker panel"
              key={status}
              onPress={() => setQueueStatus(status)}
              style={{
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: queueStatus === status ? THEME.primary : THEME.border,
                backgroundColor: queueStatus === status ? THEME.primarySoft : THEME.bgSoft,
              }}
              data-testid={`id-checker-filter-status-${String(status).toLowerCase()}`}
              testID={`id-checker-filter-status-${String(status).toLowerCase()}`}
            >
              <Text style={{ color: queueStatus === status ? THEME.primary : THEME.textSec, fontSize: 10, fontWeight: '700' }}>{stateLabel(status)}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '700' }}>{tx('executive.idChecker.filters.risk', 'Risk')}</Text>
          {RISK_FILTERS.map((risk) => {
            const tone = riskTone(THEME, risk);
            return (
              <TouchableOpacity accessibilityLabel="Set queue risk in exec idchecker panel"
                key={risk}
                onPress={() => setQueueRisk(risk)}
                style={{
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: queueRisk === risk ? tone.fg : THEME.border,
                  backgroundColor: queueRisk === risk ? tone.bg : THEME.bgSoft,
                }}
                data-testid={`id-checker-filter-risk-${risk}`}
                testID={`id-checker-filter-risk-${risk}`}
              >
                <Text style={{ color: queueRisk === risk ? tone.fg : THEME.textSec, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{risk}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '700' }}>{tx('executive.idChecker.filters.country', 'Country')}</Text>
          {countryOptions.slice(0, 12).map((country) => (
            <TouchableOpacity accessibilityLabel="Set queue country in exec idchecker panel"
              key={country}
              onPress={() => setQueueCountry(country)}
              style={{
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: queueCountry === country ? THEME.primary : THEME.border,
                backgroundColor: queueCountry === country ? THEME.primarySoft : THEME.bgSoft,
              }}
              data-testid={`id-checker-filter-country-${String(country).toLowerCase()}`}
              testID={`id-checker-filter-country-${String(country).toLowerCase()}`}
            >
              <Text style={{ color: queueCountry === country ? THEME.primary : THEME.textSec, fontSize: 10, fontWeight: '700' }}>{String(country).toUpperCase()}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: isNarrow ? 'column' : 'row', gap: 12 }}>
        <View style={[s.panel, { flex: isNarrow ? 0 : 1.25 }]} data-testid="id-checker-queue-panel" testID="id-checker-queue-panel">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <Text style={s.chartTitle}>{tx('executive.idChecker.queue.title', 'Verification Queue')}</Text>
            <TouchableOpacity accessibilityLabel="Id checker rapid review toggle button"
              onPress={() => setReviewModeEnabled((value) => !value)}
              style={{
                backgroundColor: reviewModeEnabled ? THEME.primarySoft : THEME.bgSoft,
                borderColor: reviewModeEnabled ? THEME.primary : THEME.border,
                borderWidth: 1,
                borderRadius: 999,
                paddingHorizontal: 10,
                paddingVertical: 6,
              }}
              data-testid="id-checker-rapid-review-toggle"
              testID="id-checker-rapid-review-toggle"
            >
              <Text style={{ color: reviewModeEnabled ? THEME.primary : THEME.textSec, fontSize: 10, fontWeight: '800' }}>
                {reviewModeEnabled ? tx('executive.idChecker.rapidReview.on', 'Rapid Review ON') : tx('executive.idChecker.rapidReview.off', 'Rapid Review OFF')}
              </Text>
            </TouchableOpacity>
          </View>

          {reviewModeEnabled && effectiveRows.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <TouchableOpacity onPress={() => setActiveCaseIndex((prev) => Math.max(prev - 1, 0))} style={{ backgroundColor: THEME.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="id-checker-rapid-review-prev" testID="id-checker-rapid-review-prev">
                <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>{tx('common.prev', 'Prev')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setActiveCaseIndex((prev) => Math.min(prev + 1, effectiveRows.length - 1))} style={{ backgroundColor: THEME.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="id-checker-rapid-review-next" testID="id-checker-rapid-review-next">
                <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>{tx('common.next', 'Next')}</Text>
              </TouchableOpacity>
              <Text style={{ color: THEME.textMuted, fontSize: 10 }} data-testid="id-checker-rapid-review-active" testID="id-checker-rapid-review-active">
                {tx('executive.idChecker.rapidReview.active', 'Active')} {activeCase ? `${activeCaseIndex + 1}/${effectiveRows.length}` : '-'}
              </Text>
            </View>
          )}

          {queueLoading ? (
            <View style={{ paddingVertical: 30, alignItems: 'center' }} data-testid="id-checker-queue-loading" testID="id-checker-queue-loading">
              <ActivityIndicator size="small" color={THEME.primary} />
            </View>
          ) : effectiveRows.length === 0 ? (
            <Text style={{ color: THEME.textMuted, fontSize: 12, textAlign: 'center', paddingVertical: 24 }} data-testid="id-checker-queue-empty" testID="id-checker-queue-empty">
              {tx('executive.idChecker.queue.empty', 'No cases match current filters.')}
            </Text>
          ) : (
            <View style={{ gap: 8 }}>
              {effectiveRows.map((row: any, index: number) => {
                const risk = riskTone(THEME, row.risk_level);
                const workflow = workflowTone(THEME, row.workflow_state || row.status);
                const isActive = selectedUserId === row.user_id || (reviewModeEnabled && activeCaseIndex === index);
                const loadPrefix = `${row.user_id}_`;
                return (
                  <TouchableOpacity accessibilityLabel="Set selected user id in exec idchecker panel"
                    key={row.user_id || `row_${index}`}
                    onPress={() => setSelectedUserId(row.user_id)}
                    style={{
                      borderWidth: 1,
                      borderColor: isActive ? THEME.primary : THEME.border,
                      backgroundColor: isActive ? THEME.primarySoft : THEME.bgSoft,
                      borderRadius: 12,
                      padding: 10,
                    }}
                    data-testid={`id-checker-queue-row-${row.user_id || index}`}
                    testID={`id-checker-queue-row-${row.user_id || index}`}
                  >
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: THEME.text, fontSize: 13, fontWeight: '800' }} numberOfLines={1}>{row.full_name || row.user_id || '-'}</Text>
                        <Text style={{ color: THEME.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`id-checker-row-meta-${row.user_id || index}`} testID={`id-checker-row-meta-${row.user_id || index}`}>
                          {(row.user_id || '').slice(-8)} • {String(row.country || 'N/A').toUpperCase()} • {tx('executive.idChecker.docsCount', 'Docs')} {row.documents_count ?? 0}
                        </Text>
                        <Text style={{ color: THEME.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`id-checker-row-commercial-${row.user_id || index}`} testID={`id-checker-row-commercial-${row.user_id || index}`}>
                          {String(row.service_lane || 'standard_lane').replaceAll('_', ' ')} · SLA {row.sla_hours_remaining ?? 'N/A'}h
                        </Text>
                      </View>
                      <View style={{ alignItems: 'flex-end', gap: 4 }}>
                        <View style={{ backgroundColor: workflow.bg, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }}>
                          <Text style={{ color: workflow.fg, fontSize: 9, fontWeight: '800' }}>{stateLabel(row.workflow_state || row.status)}</Text>
                        </View>
                        <View style={{ backgroundColor: risk.bg, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }}>
                          <Text style={{ color: risk.fg, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{row.risk_level || 'unknown'}</Text>
                        </View>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                      <TouchableOpacity
                        onPress={() => openAiModal(row.user_id)}
                        style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 8, paddingVertical: 6 }}
                        data-testid={`id-checker-row-ai-${row.user_id || index}`}
                        testID={`id-checker-row-ai-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.ai', 'AI')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => openDocuments(row, selectedCase?.case?.user_id === row.user_id ? selectedCase : null)}
                        style={{ backgroundColor: THEME.primarySoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }}
                        data-testid={`id-checker-row-docs-${row.user_id || index}`}
                        testID={`id-checker-row-docs-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.primary, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.docs', 'Docs')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => openActionModal(row.user_id, 'request_more_info', tx('executive.idChecker.defaults.moreInfo', 'Please provide clearer document captures.'))}
                        disabled={idvOverrideLoading === `${loadPrefix}request_more_info`}
                        style={{ backgroundColor: THEME.warningSoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, opacity: idvOverrideLoading === `${loadPrefix}request_more_info` ? 0.5 : 1 }}
                        data-testid={`id-checker-row-more-info-${row.user_id || index}`}
                        testID={`id-checker-row-more-info-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.warningText, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.moreInfo', 'More Info')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => runOverrideAction(row.user_id, 'force_approve', '')}
                        disabled={idvOverrideLoading === `${loadPrefix}force_approve`}
                        style={{ backgroundColor: THEME.successSoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, opacity: idvOverrideLoading === `${loadPrefix}force_approve` ? 0.5 : 1 }}
                        data-testid={`id-checker-row-approve-${row.user_id || index}`}
                        testID={`id-checker-row-approve-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.successText, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.approve', 'Approve')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => openActionModal(row.user_id, 'force_reject', tx('executive.idChecker.defaults.rejectReason', 'Rejected by admin reviewer.'))}
                        disabled={idvOverrideLoading === `${loadPrefix}force_reject`}
                        style={{ backgroundColor: THEME.errorSoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, opacity: idvOverrideLoading === `${loadPrefix}force_reject` ? 0.5 : 1 }}
                        data-testid={`id-checker-row-reject-${row.user_id || index}`}
                        testID={`id-checker-row-reject-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.error, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.reject', 'Reject')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => openActionModal(row.user_id, 'ban', tx('executive.idChecker.defaults.banReason', 'Fraudulent pattern detected.'))}
                        disabled={idvOverrideLoading === `${loadPrefix}ban`}
                        style={{ backgroundColor: THEME.errorSoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, opacity: idvOverrideLoading === `${loadPrefix}ban` ? 0.5 : 1 }}
                        data-testid={`id-checker-row-ban-${row.user_id || index}`}
                        testID={`id-checker-row-ban-${row.user_id || index}`}
                      >
                        <Text style={{ color: THEME.error, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.ban', 'Ban')}</Text>
                      </TouchableOpacity>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}
        </View>

        <View style={[s.panel, { flex: 1 }]} data-testid="id-checker-case-panel" testID="id-checker-case-panel">
          <Text style={s.chartTitle}>{tx('executive.idChecker.case.title', 'Case Review Drawer')}</Text>
          {!selectedUserId ? (
            <Text style={{ color: THEME.textMuted, fontSize: 12, paddingVertical: 20 }} data-testid="id-checker-case-empty" testID="id-checker-case-empty">
              {tx('executive.idChecker.case.selectPrompt', 'Select a queue item to inspect detailed AI and document evidence.')}
            </Text>
          ) : selectedCaseLoading ? (
            <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 24 }} data-testid="id-checker-case-loading" testID="id-checker-case-loading">
              <ActivityIndicator size="small" color={THEME.primary} />
            </View>
          ) : selectedCase?.case ? (
            <ScrollView style={{ maxHeight: isNarrow ? 540 : 760 }} contentContainerStyle={{ gap: 10 }} data-testid="id-checker-case-scroll" testID="id-checker-case-scroll">
              <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-case-identity" testID="id-checker-case-identity">
                <Text style={{ color: THEME.text, fontSize: 13, fontWeight: '800' }}>{selectedCase.case.full_name || '-'}</Text>
                <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 2 }}>
                  {selectedCase.case.user_id} • {selectedCase.case.nationality || 'N/A'} • {stateLabel(selectedCase.case.workflow_state || selectedCase.case.status)}
                </Text>
              </View>

              <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-case-ai" testID="id-checker-case-ai">
                <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{tx('executive.idChecker.case.aiScore', 'AI Scoring')}</Text>
                <Text style={{ color: THEME.textSec, fontSize: 11 }}>{tx('executive.idChecker.case.confidence', 'Confidence')}: {Math.round((selectedCase.ai?.confidence_score || 0) * 100)}%</Text>
                <Text style={{ color: THEME.textSec, fontSize: 11 }}>{tx('executive.idChecker.case.risk', 'Risk')}: {String(selectedCase.ai?.risk_level || 'unknown').toUpperCase()}</Text>
                <Text style={{ color: THEME.textSec, fontSize: 11 }}>{tx('executive.idChecker.case.fraudRiskScore', 'Fraud Risk Score')}: {selectedCase.ai?.fraud_risk_score ?? 'N/A'}</Text>
                <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 4 }}>{tx('executive.idChecker.case.suggestedAction', 'Suggested Action')}: {stateLabel(selectedCase.ai?.suggested_action || 'manual_review')}</Text>
                {(selectedCase.ai?.tampering_flags || []).length > 0 && (
                  <View style={{ marginTop: 6, gap: 4 }}>
                    {(selectedCase.ai?.tampering_flags || []).slice(0, 4).map((flag: string, idx: number) => (
                      <Text key={`${flag}_${idx}`} style={{ color: THEME.warningText, fontSize: 10 }} data-testid={`id-checker-case-flag-${idx}`} testID={`id-checker-case-flag-${idx}`}>• {flag}</Text>
                    ))}
                  </View>
                )}
              </View>

              <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-case-doc-actions" testID="id-checker-case-doc-actions">
                <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{tx('executive.idChecker.case.documents', 'Documents')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => openDocuments(selectedCase.case, selectedCase)}
                    style={{ backgroundColor: THEME.primarySoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="id-checker-case-open-docs"
                    testID="id-checker-case-open-docs"
                  >
                    <Text style={{ color: THEME.primary, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.case.openDrawer', 'Open Document Drawer')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => openAiModal(selectedCase.case.user_id)}
                    style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="id-checker-case-open-ai"
                    testID="id-checker-case-open-ai"
                  >
                    <Text style={{ color: THEME.textSec, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.case.openAi', 'Open AI Breakdown')}</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-case-ocr" testID="id-checker-case-ocr">
                <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{tx('executive.idChecker.case.ocr', 'OCR / Vision Signals')}</Text>
                {Object.keys(selectedCase.ocr_extracted || {}).length === 0 ? (
                  <Text style={{ color: THEME.textMuted, fontSize: 11 }}>{tx('executive.idChecker.case.ocrEmpty', 'No structured OCR fields found in this submission.')}</Text>
                ) : (
                  Object.entries(selectedCase.ocr_extracted || {}).slice(0, 6).map(([dtype, value]: [string, any]) => (
                    <View key={dtype} style={{ marginBottom: 6 }}>
                      <Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>{dtype.toUpperCase()}</Text>
                      <Text style={{ color: THEME.textMuted, fontSize: 10 }} numberOfLines={2}>{value?.summary || JSON.stringify(value).slice(0, 120)}</Text>
                    </View>
                  ))
                )}
              </View>

              <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: THEME.border, padding: 10 }} data-testid="id-checker-case-actions" testID="id-checker-case-actions">
                <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{tx('executive.idChecker.case.reviewActions', 'Review Actions')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity onPress={() => openActionModal(selectedCase.case.user_id, 'request_more_info', tx('executive.idChecker.defaults.moreInfo', 'Please provide clearer document captures.'))} style={{ backgroundColor: THEME.warningSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="id-checker-case-more-info" testID="id-checker-case-more-info">
                    <Text style={{ color: THEME.warningText, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.moreInfo', 'More Info')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => runOverrideAction(selectedCase.case.user_id, 'force_approve', '')} style={{ backgroundColor: THEME.successSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="id-checker-case-approve" testID="id-checker-case-approve">
                    <Text style={{ color: THEME.successText, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.approve', 'Approve')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => openActionModal(selectedCase.case.user_id, 'force_reject', tx('executive.idChecker.defaults.rejectReason', 'Rejected by admin reviewer.'))} style={{ backgroundColor: THEME.errorSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="id-checker-case-reject" testID="id-checker-case-reject">
                    <Text style={{ color: THEME.error, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.reject', 'Reject')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => openActionModal(selectedCase.case.user_id, 'ban', tx('executive.idChecker.defaults.banReason', 'Fraudulent pattern detected.'))} style={{ backgroundColor: THEME.errorSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="id-checker-case-ban" testID="id-checker-case-ban">
                    <Text style={{ color: THEME.error, fontSize: 10, fontWeight: '700' }}>{tx('executive.idChecker.actions.ban', 'Ban')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </ScrollView>
          ) : (
            <Text style={{ color: THEME.textMuted, fontSize: 12 }}>{tx('executive.idChecker.case.notFound', 'Case details unavailable for selected user.')}</Text>
          )}
        </View>
      </View>

      <Modal visible={actionModalOpen} transparent animationType="fade" onRequestClose={() => setActionModalOpen(false)}>
        <View style={{ flex: 1, backgroundColor: THEME.overlay, justifyContent: 'center', padding: 20 }}>
          <View style={{ width: '100%', maxWidth: 560, alignSelf: 'center', backgroundColor: THEME.card, borderRadius: 12, borderWidth: 1, borderColor: THEME.border, padding: 16 }} data-testid="id-checker-action-modal" testID="id-checker-action-modal">
            <Text style={{ color: THEME.text, fontSize: 14, fontWeight: '800', marginBottom: 4 }} data-testid="id-checker-action-modal-title" testID="id-checker-action-modal-title">
              {tx('executive.idChecker.actionModal.title', 'Confirm Reviewer Action')} · {actionText(actionModalType)}
            </Text>
            <Text style={{ color: THEME.textMuted, fontSize: 11, marginBottom: 10 }} data-testid="id-checker-action-modal-target" testID="id-checker-action-modal-target">
              {tx('executive.idChecker.actionModal.target', 'Target User')}: {actionModalTargetUser || '-'}
            </Text>
            <TextInput
              value={actionReason}
              onChangeText={setActionReason}
              multiline
              placeholder={tx('executive.idChecker.actionModal.reasonPlaceholder', 'Add reviewer reason for audit trail')}
              placeholderTextColor={THEME.textMuted}
              style={{ minHeight: 94, borderWidth: 1, borderColor: THEME.border, borderRadius: 10, backgroundColor: THEME.bgSoft, color: THEME.text, padding: 10, fontSize: 12 }}
              data-testid="id-checker-action-modal-reason-input"
              testID="id-checker-action-modal-reason-input"
            />
            <View style={{ marginTop: 12, flexDirection: 'row', justifyContent: 'flex-end', gap: 8 }}>
              <TouchableOpacity
                onPress={() => setActionModalOpen(false)}
                style={{ backgroundColor: THEME.bgSoft, borderWidth: 1, borderColor: THEME.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="id-checker-action-modal-cancel"
                testID="id-checker-action-modal-cancel"
              >
                <Text style={{ color: THEME.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('common.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityLabel="Id checker action modal confirm button"
                onPress={async () => {
                  if (!actionModalType || !actionModalTargetUser) return;
                  await runOverrideAction(actionModalTargetUser, actionModalType, actionReason);
                  setActionModalOpen(false);
                }}
                disabled={actionModalType !== 'force_approve' && actionReason.trim().length < 4}
                style={{
                  backgroundColor: THEME.primary,
                  borderRadius: 8,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  opacity: actionModalType !== 'force_approve' && actionReason.trim().length < 4 ? 0.5 : 1,
                }}
                data-testid="id-checker-action-modal-confirm"
                testID="id-checker-action-modal-confirm"
              >
                <Text style={{ color: THEME.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('common.confirm', 'Confirm')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <Modal visible={aiModalOpen} transparent animationType="fade" onRequestClose={() => setAiModalOpen(false)}>
        <View style={{ flex: 1, backgroundColor: THEME.overlay, justifyContent: 'center', padding: 20 }}>
          <View style={{ width: '100%', maxWidth: 960, alignSelf: 'center', backgroundColor: THEME.card, borderRadius: 12, borderWidth: 1, borderColor: THEME.border, padding: 16 }} data-testid="id-checker-ai-modal" testID="id-checker-ai-modal">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={{ color: THEME.text, fontSize: 14, fontWeight: '800' }} data-testid="id-checker-ai-modal-title" testID="id-checker-ai-modal-title">
                {tx('executive.idChecker.aiModal.title', 'AI Verification Analysis')}
              </Text>
              <TouchableOpacity onPress={() => setAiModalOpen(false)} data-testid="id-checker-ai-modal-close" testID="id-checker-ai-modal-close">
                <Ionicons name="close" size={18} color={THEME.textMuted} />
              </TouchableOpacity>
            </View>
            {aiModalLoading ? (
              <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 20 }}>
                <ActivityIndicator size="small" color={THEME.primary} />
              </View>
            ) : !aiModalData ? (
              <Text style={{ color: THEME.textMuted, fontSize: 12 }} data-testid="id-checker-ai-modal-empty" testID="id-checker-ai-modal-empty">
                {tx('executive.idChecker.aiModal.empty', 'AI analysis unavailable for this case.')}
              </Text>
            ) : (
              <ScrollView style={{ maxHeight: 460 }} contentContainerStyle={{ gap: 8 }}>
                <Text style={{ color: THEME.textSec, fontSize: 12 }}>{tx('executive.idChecker.aiModal.status', 'Status')}: {stateLabel(aiModalData?.workflow_state || aiModalData?.status || 'UNKNOWN')}</Text>
                <Text style={{ color: THEME.textSec, fontSize: 12 }}>{tx('executive.idChecker.aiModal.confidence', 'Confidence')}: {Math.round(((aiModalData?.ai_verification?.confidence_score || 0) as number) * 100)}%</Text>
                <Text style={{ color: THEME.textSec, fontSize: 12 }}>{tx('executive.idChecker.aiModal.risk', 'Risk Level')}: {String(aiModalData?.ai_verification?.risk_level || 'unknown').toUpperCase()}</Text>
                <Text style={{ color: THEME.textSec, fontSize: 12 }}>{tx('executive.idChecker.aiModal.combined', 'Combined Score')}: {aiModalData?.combined_score ?? 'N/A'}</Text>
                <Text style={{ color: THEME.textMuted, fontSize: 12 }}>{tx('executive.idChecker.aiModal.method', 'Verification Method')}: {aiModalData?.verification_method || 'N/A'}</Text>
                {Array.isArray(aiModalData?.ai_verification?.checks) && aiModalData.ai_verification.checks.length > 0 && (
                  <View style={{ marginTop: 6 }}>
                    <Text style={{ color: THEME.text, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('executive.idChecker.aiModal.checks', 'Checks')}</Text>
                    {aiModalData.ai_verification.checks.slice(0, 10).map((check: any, idx: number) => (
                      <View key={`check_${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }} data-testid={`id-checker-ai-modal-check-${idx}`} testID={`id-checker-ai-modal-check-${idx}`}>
                        <Ionicons name={check?.passed ? 'checkmark-circle' : 'close-circle'} size={12} color={check?.passed ? THEME.success : THEME.error} />
                        <Text style={{ color: THEME.textMuted, fontSize: 11, flex: 1 }}>{check?.detail || check?.check || 'signal'}</Text>
                      </View>
                    ))}
                  </View>
                )}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}
