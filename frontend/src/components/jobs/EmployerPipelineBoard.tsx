import React, { useCallback, useEffect, useMemo, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { resolveRuntimeBaseUrl } from '../../utils/runtimeBaseUrl';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

const STAGES = ['applied', 'viewed', 'interview', 'offer', 'hired', 'rejected'] as const;
type StageKey = (typeof STAGES)[number];

type PipelineApplication = {
  application_id: string;
  job_id: string;
  job_title: string;
  company_name: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  status: StageKey | string;
  resume_score?: number;
  match_score?: number;
  match_tier?: string;
  match_reasons?: string[];
  sla_age_days?: number;
  sla_target_days?: number;
  sla_breached?: boolean;
  copilot_actions?: Array<{ action_key: string; label: string; type: string; priority: string }>;
  applied_at?: string;
  updated_at?: string;
  latest_interview?: {
    interview_id?: string;
    status?: string;
    scheduled_start?: string;
    timezone?: string;
  };
};

type PipelineSlaAlerts = {
  overdue_total?: number;
  overdue_by_stage?: Record<string, number>;
  items?: Array<{
    application_id: string;
    candidate_name: string;
    status: string;
    age_days: number;
    target_days: number;
    job_title: string;
  }>;
};

type InterviewKitPayload = {
  kit_id?: string;
  panel_brief?: string;
  focus_areas?: string[];
  technical_questions?: string[];
  behavioral_questions?: string[];
};

type OfferRecord = {
  offer_id: string;
  application_id: string;
  status: string;
  approval_status?: string;
  base_salary_usd?: number;
  start_date?: string;
  expires_at?: string;
  sent_at?: string;
  signed_at?: string;
  decision?: string;
};

type TimelineEvent = {
  event_id?: string;
  event_type?: string;
  title?: string;
  description?: string;
  created_at?: string;
};

type ScorecardSummary = {
  count?: number;
  average_overall_score?: number;
  latest_recommendation?: string;
};

type ScorecardPayload = {
  scorecards?: Array<{
    scorecard_id: string;
    overall_score?: number;
    recommendation?: string;
    reviewer_name?: string;
    created_at?: string;
  }>;
  summary?: ScorecardSummary;
  panel_debrief?: {
    summary?: string;
    majority_recommendation?: string;
    average_overall_score?: number;
  };
};

type AutoSchedulerSlot = {
  start: string;
  end: string;
  date: string;
  time: string;
  day_name?: string;
  duration_minutes?: number;
  rank?: number;
  ai_recommended?: boolean;
};

type CommunicationSequencePayload = {
  sequence_id?: string;
  status?: string;
  current_step_index?: number;
  steps?: Array<{ key?: string; title?: string; message?: string }>;
  history?: Array<{ sent_at?: string; title?: string }>;
};

type HiringForecastPayload = {
  forecast?: {
    predicted_days_to_fill?: number;
    predicted_hires_next_30_days?: number;
    risk_level?: string;
    confidence?: number;
  };
  counts?: {
    active_applications?: number;
    bottleneck_items?: number;
  };
  recommendations?: string[];
};

type RediscoveryCandidate = {
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  match_score?: number;
  previous_stage?: string;
  match_reasons?: string[];
};

type UndoInterviewAction = {
  kind: 'cancel' | 'reschedule';
  interviewId: string;
  applicationId: string;
  candidateName: string;
  previousDate: string;
  previousTime: string;
  previousTimezone: string;
  expiresAt: number;
};

type SlaAutoTriggerItem = {
  trigger_id: string;
  application_id: string;
  candidate_name: string;
  job_title: string;
  stage: string;
  overdue_by_days?: number;
  trigger_action: string;
  trigger_label: string;
  reason?: string;
  status?: string;
  suggested_slots?: AutoSchedulerSlot[];
};

type SlaAutoTriggerPayload = {
  summary?: {
    pending_total?: number;
    cooldown_total?: number;
    by_action?: Record<string, number>;
  };
  items?: SlaAutoTriggerItem[];
};

type SharedUndoNotice = {
  kind: 'cancel' | 'reschedule';
  actorName: string;
  candidateName: string;
  applicationId: string;
  expiresAt: number;
  message: string;
};

type AuditDownloadHistoryEntry = {
  export_id: string;
  format: 'csv' | 'pdf';
  range_label?: string;
  row_count?: number;
  signature_id?: string;
  signature?: string;
  exported_by_name?: string;
  created_at?: string;
};

type AuditRangeKey = '30d' | '90d' | 'all';

const UNDO_WINDOW_SECONDS = 30;

type DrilldownFilterKey = 'all' | 'time-to-hire' | 'stage-conversion' | 'offer-acceptance' | 'active-bottlenecks';

type EmployerPipelineBoardProps = {
  drilldownFilter?: DrilldownFilterKey;
  onClearDrilldown?: () => void;
};

const STAGE_LABEL: Record<string, string> = {
  applied: 'Applied',
  viewed: 'Viewed',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
};

function extractDateTimeFromIso(iso?: string): { date: string; time: string } {
  if (iso && iso.includes('T')) {
    const [date, timePart] = iso.split('T');
    const time = (timePart || '10:00').replace('Z', '').slice(0, 5);
    if (date && time) {
      return { date, time };
    }
  }
  const fallback = new Date();
  fallback.setDate(fallback.getDate() + 1);
  return { date: fallback.toISOString().slice(0, 10), time: '10:00' };
}

export function EmployerPipelineBoard({ drilldownFilter = 'all', onClearDrilldown }: EmployerPipelineBoardProps) {
  const { width } = useWindowDimensions();
  const isCompactBreadcrumb = width < 768;
  const { user } = useAuth();
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [applications, setApplications] = useState<PipelineApplication[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [slaAlerts, setSlaAlerts] = useState<PipelineSlaAlerts>({});
  const [selectedAppId, setSelectedAppId] = useState('');
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [draggingAppId, setDraggingAppId] = useState('');
  const [interviewKit, setInterviewKit] = useState<InterviewKitPayload | null>(null);
  const [offers, setOffers] = useState<OfferRecord[]>([]);
  const [copilotInsight, setCopilotInsight] = useState<any | null>(null);
  const [undoAction, setUndoAction] = useState<UndoInterviewAction | null>(null);
  const [undoSecondsRemaining, setUndoSecondsRemaining] = useState(0);
  const [activeFilter, setActiveFilter] = useState<DrilldownFilterKey>('all');
  const [bulkSelection, setBulkSelection] = useState<string[]>([]);
  const [scorecards, setScorecards] = useState<ScorecardPayload | null>(null);
  const [autoSlots, setAutoSlots] = useState<AutoSchedulerSlot[]>([]);
  const [sequence, setSequence] = useState<CommunicationSequencePayload | null>(null);
  const [forecast, setForecast] = useState<HiringForecastPayload | null>(null);
  const [rediscoveryCandidates, setRediscoveryCandidates] = useState<RediscoveryCandidate[]>([]);
  const [slaAutoTriggers, setSlaAutoTriggers] = useState<SlaAutoTriggerPayload | null>(null);
  const [auditRange, setAuditRange] = useState<AuditRangeKey>('30d');
  const [auditDownloadHistory, setAuditDownloadHistory] = useState<AuditDownloadHistoryEntry[]>([]);
  const [liveSyncStatus, setLiveSyncStatus] = useState<'idle' | 'connecting' | 'connected' | 'reconnecting'>('idle');
  const [liveSyncMembers, setLiveSyncMembers] = useState(0);
  const [liveSyncMessage, setLiveSyncMessage] = useState('');
  const [sharedUndoNotice, setSharedUndoNotice] = useState<SharedUndoNotice | null>(null);
  const [sharedUndoSecondsRemaining, setSharedUndoSecondsRemaining] = useState(0);

  const cardBg = colors.card || colors.surface;
  const cardBorder = colors.border;
  const laneBg = colors.bgSoft || colors.cardMuted || colors.bgAlt;
  const muted = colors.textMuted;
  const titleColor = colors.text;

  const filteredApplications = useMemo(() => {
    return applications.filter((app) => {
      const status = String(app.status || 'applied').toLowerCase();
      if (activeFilter === 'time-to-hire') return status === 'hired';
      if (activeFilter === 'stage-conversion') return status !== 'applied';
      if (activeFilter === 'offer-acceptance') return status === 'offer' || status === 'hired';
      if (activeFilter === 'active-bottlenecks') return Boolean(app.sla_breached);
      return true;
    });
  }, [applications, activeFilter]);

  const selectedApplication = useMemo(
    () => filteredApplications.find((app) => app.application_id === selectedAppId) || filteredApplications[0] || null,
    [filteredApplications, selectedAppId]
  );

  const filterLabel = useMemo(() => {
    if (activeFilter === 'all') return 'all candidates';
    return activeFilter.replace(/-/g, ' ');
  }, [activeFilter]);

  useEffect(() => {
    setActiveFilter(drilldownFilter || 'all');
  }, [drilldownFilter]);

  const loadBoard = useCallback(async (silent = false) => {
    setError('');
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await api.get('/hiring/v2/employer/pipeline-board', { params: { limit: 320 } });
      const rows = (res.data?.applications || []) as PipelineApplication[];
      setApplications(rows);
      setCounts(res.data?.counts || {});
      setSlaAlerts(res.data?.sla_alerts || {});
      if (rows.length > 0 && (!selectedAppId || !rows.some((x) => x.application_id === selectedAppId))) {
        setSelectedAppId(rows[0].application_id);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load employer pipeline board.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedAppId]);

  const loadTimeline = useCallback(async (applicationId: string) => {
    if (!applicationId) return;
    setTimelineLoading(true);
    try {
      const res = await api.get(`/jobs/employer/pipeline-board/${applicationId}/timeline`, { params: { limit: 80 } });
      setTimeline(res.data?.events || []);
    } catch {
      setTimeline([]);
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  const loadOffers = useCallback(async (applicationId: string) => {
    if (!applicationId) {
      setOffers([]);
      return;
    }
    try {
      const res = await api.get('/hiring/v2/employer/offers', { params: { application_id: applicationId, limit: 20 } });
      setOffers((res.data?.offers || []) as OfferRecord[]);
    } catch {
      setOffers([]);
    }
  }, []);

  const loadCopilotSuggestions = useCallback(async (applicationId: string) => {
    if (!applicationId) {
      setCopilotInsight(null);
      return;
    }
    try {
      const res = await api.get(`/jobs/employer/copilot/${applicationId}/suggestions`);
      setCopilotInsight(res.data || null);
    } catch {
      setCopilotInsight(null);
    }
  }, []);

  const loadScorecards = useCallback(async (applicationId: string) => {
    if (!applicationId) {
      setScorecards(null);
      return;
    }
    try {
      const res = await api.get(`/jobs/employer/scorecards/${applicationId}`);
      setScorecards((res.data || null) as ScorecardPayload | null);
    } catch {
      setScorecards(null);
    }
  }, []);

  const loadSequence = useCallback(async (applicationId: string) => {
    if (!applicationId) {
      setSequence(null);
      return;
    }
    try {
      const res = await api.get(`/jobs/employer/communication-sequences/${applicationId}`);
      setSequence((res.data?.sequence || null) as CommunicationSequencePayload | null);
    } catch {
      setSequence(null);
    }
  }, []);

  const loadForecast = useCallback(async () => {
    try {
      const res = await api.get('/jobs/employer/hiring-forecast', { params: { window_days: 45 } });
      setForecast((res.data || null) as HiringForecastPayload | null);
    } catch {
      setForecast(null);
    }
  }, []);

  const loadRediscovery = useCallback(async (jobId?: string) => {
    try {
      const res = await api.get('/jobs/employer/talent-rediscovery', { params: { job_id: jobId || undefined, limit: 8 } });
      setRediscoveryCandidates((res.data?.candidates || []) as RediscoveryCandidate[]);
    } catch {
      setRediscoveryCandidates([]);
    }
  }, []);

  const loadAuditDownloadHistory = useCallback(async (applicationId?: string) => {
    if (!applicationId) {
      setAuditDownloadHistory([]);
      return;
    }
    try {
      const res = await api.get(`/jobs/employer/pipeline-board/${applicationId}/audit-download-history`, { params: { limit: 8 } });
      setAuditDownloadHistory((res.data?.entries || []) as AuditDownloadHistoryEntry[]);
    } catch {
      setAuditDownloadHistory([]);
    }
  }, []);

  const loadSlaAutoTriggers = useCallback(async () => {
    try {
      const res = await api.get('/hiring/v2/employer/sla-alerts', { params: { limit: 8 } });
      setSlaAutoTriggers((res.data || null) as SlaAutoTriggerPayload | null);
    } catch {
      setSlaAutoTriggers(null);
    }
  }, []);

  useEffect(() => {
    void loadBoard(false);
  }, [loadBoard]);

  useEffect(() => {
    const interval = setInterval(() => {
      void loadBoard(true);
    }, 30000);
    return () => clearInterval(interval);
  }, [loadBoard]);

  useEffect(() => {
    if (selectedAppId) {
      void loadTimeline(selectedAppId);
      void loadAuditDownloadHistory(selectedAppId);
    } else {
      setAuditDownloadHistory([]);
    }
  }, [selectedAppId, loadAuditDownloadHistory, loadTimeline]);

  useEffect(() => {
    if (selectedAppId) {
      void loadOffers(selectedAppId);
      void loadCopilotSuggestions(selectedAppId);
      void loadScorecards(selectedAppId);
      void loadSequence(selectedAppId);
      const selected = applications.find((row) => row.application_id === selectedAppId);
      void loadRediscovery(selected?.job_id);
      setInterviewKit(null);
      setAutoSlots([]);
    }
  }, [selectedAppId, applications, loadOffers, loadCopilotSuggestions, loadScorecards, loadSequence, loadRediscovery]);

  useEffect(() => {
    void loadForecast();
  }, [loadForecast]);

  useEffect(() => {
    void loadSlaAutoTriggers();
  }, [loadSlaAutoTriggers]);

  useEffect(() => {
    if (!undoAction) {
      setUndoSecondsRemaining(0);
      return;
    }

    const tick = () => {
      const remaining = Math.max(0, Math.ceil((undoAction.expiresAt - Date.now()) / 1000));
      setUndoSecondsRemaining(remaining);
      if (remaining <= 0) {
        setUndoAction(null);
      }
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [undoAction]);

  useEffect(() => {
    if (!sharedUndoNotice) {
      setSharedUndoSecondsRemaining(0);
      return;
    }

    const tick = () => {
      const remaining = Math.max(0, Math.ceil((sharedUndoNotice.expiresAt - Date.now()) / 1000));
      setSharedUndoSecondsRemaining(remaining);
      if (remaining <= 0) {
        setSharedUndoNotice(null);
      }
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [sharedUndoNotice]);

  const pipelineWsEnabled = Platform.OS === 'web' && typeof window !== 'undefined' && Boolean(user?.user_id);

  const buildPipelineWsUrl = useCallback(async () => {
    const baseUrl = resolveRuntimeBaseUrl();
    if (!baseUrl) return '';

    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'jobs_employer_pipeline' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for employer pipeline');
    }
    return `${baseUrl.replace(/^http/i, 'ws')}/api/ws/jobs/employer/pipeline?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError: pipelineWsError } = useManagedWebSocket({
    enabled: pipelineWsEnabled,
    buildUrl: buildPipelineWsUrl,
    errorScope: 'jobs/employer-pipeline/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1600,
    onOpen: () => {
      setLiveSyncStatus('connected');
      setLiveSyncMessage('Interview actions and shared undo windows update across recruiter tabs in real time.');
    },
    onClose: () => {
      if (!pipelineWsEnabled) return;
      setLiveSyncStatus('reconnecting');
    },
    onError: () => {
      setLiveSyncStatus('reconnecting');
      setLiveSyncMessage('Live sync disconnected. Reconnecting...');
    },
    onReconnectAttempt: () => {
      setLiveSyncStatus('reconnecting');
      setLiveSyncMessage('Live sync reconnecting...');
    },
    onMessage: (event) => {
      try {
        const payload = JSON.parse(event.data || '{}');
        if (payload?.type === 'pipeline_presence') {
          setLiveSyncMembers(Number(payload?.members || 0));
          return;
        }
        if (payload?.type !== 'pipeline_event') return;

        if (payload?.message) {
          setLiveSyncMessage(String(payload.message));
        }
        if (payload?.event_type === 'interview_action_undone') {
          setSharedUndoNotice(null);
        } else if (payload?.undo_window_expires_at && payload?.actor_user_id !== user?.user_id) {
          setSharedUndoNotice({
            kind: payload?.undo_kind === 'cancel' ? 'cancel' : 'reschedule',
            actorName: String(payload?.actor_name || 'Recruiter'),
            candidateName: String(payload?.candidate_name || 'Candidate'),
            applicationId: String(payload?.application_id || ''),
            expiresAt: new Date(String(payload.undo_window_expires_at)).getTime(),
            message: String(payload?.message || 'Interview action updated.'),
          });
        }

        void loadBoard(true);
        void loadSlaAutoTriggers();
        if (selectedAppId) {
          void loadTimeline(selectedAppId);
        }
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'jobs/employer-pipeline/ws-parse',
          fallbackMessage: 'A live pipeline event could not be processed.',
          setMessage: setLiveSyncMessage,
        });
      }
    },
  });

  useEffect(() => {
    if (pipelineWsEnabled) return;
    setLiveSyncStatus('idle');
    setLiveSyncMembers(0);
  }, [pipelineWsEnabled]);

  useEffect(() => {
    if (!pipelineWsError) return;
    setLiveSyncStatus('reconnecting');
    setLiveSyncMessage(pipelineWsError);
  }, [pipelineWsError]);

  const updateStage = useCallback(
    async (app: PipelineApplication, status: StageKey) => {
      const actionId = `status-${app.application_id}-${status}`;
      setActionLoading(actionId);
      setError('');
      try {
      await api.post(`/hiring/v2/employer/applications/${app.job_id}/${app.application_id}/status`, { status });
        await loadBoard(true);
        await loadTimeline(app.application_id);
      } catch (e: any) {
        setError(e?.response?.data?.detail || `Failed to move candidate to ${status}.`);
      } finally {
        setActionLoading('');
      }
    },
    [loadBoard, loadTimeline]
  );

  const scheduleInterview = useCallback(
    async (app: PipelineApplication) => {
      const actionId = `schedule-${app.application_id}`;
      setActionLoading(actionId);
      setError('');
      try {
        let date = '';
        let time = '';
        let timezone = 'UTC';
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          date = window.prompt('Interview date (YYYY-MM-DD)', '') || '';
          time = window.prompt('Interview time (HH:MM)', '10:00') || '10:00';
          timezone = window.prompt('Timezone', 'UTC') || 'UTC';
        }
        if (!date) {
          const dt = new Date();
          dt.setDate(dt.getDate() + 1);
          date = dt.toISOString().slice(0, 10);
          time = '10:00';
        }

        await api.post('/interviews/schedule', {
          application_id: app.application_id,
          candidate_id: app.candidate_id,
          job_id: app.job_id,
          interview_type: 'video',
          scheduled_date: date,
          scheduled_time: time,
          timezone,
          duration_minutes: 30,
          notes: 'Scheduled from Employer Pipeline Board',
        });

      await api.post(`/hiring/v2/employer/applications/${app.job_id}/${app.application_id}/status`, { status: 'interview' });
        await loadBoard(true);
        await loadTimeline(app.application_id);
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to schedule interview.');
      } finally {
        setActionLoading('');
      }
    },
    [loadBoard, loadTimeline]
  );

  const rescheduleInterview = useCallback(
    async (app: PipelineApplication) => {
      const interviewId = app.latest_interview?.interview_id;
      if (!interviewId) {
        setError('No scheduled interview found for this candidate.');
        return;
      }
      const actionId = `reschedule-${app.application_id}`;
      setActionLoading(actionId);
      setError('');
      try {
        const previousSlot = extractDateTimeFromIso(app.latest_interview?.scheduled_start);
        let date = '';
        let time = '';
        let timezone = 'UTC';
        let reason = 'Rescheduled from Employer Pipeline Board';
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          date = window.prompt('New interview date (YYYY-MM-DD)', '') || '';
          time = window.prompt('New interview time (HH:MM)', '10:00') || '10:00';
          timezone = window.prompt('Timezone', app.latest_interview?.scheduled_start ? 'UTC' : 'UTC') || 'UTC';
          reason = window.prompt('Reason for reschedule', reason) || reason;
        }
        if (!date) {
          const dt = new Date();
          dt.setDate(dt.getDate() + 2);
          date = dt.toISOString().slice(0, 10);
          time = '10:00';
        }

        await api.post(`/interviews/${interviewId}/reschedule`, {
          new_date: date,
          new_time: time,
          timezone,
          reason,
        });

        setUndoAction({
          kind: 'reschedule',
          interviewId,
          applicationId: app.application_id,
          candidateName: app.candidate_name || 'Candidate',
          previousDate: previousSlot.date,
          previousTime: previousSlot.time,
          previousTimezone: app.latest_interview?.timezone || 'UTC',
          expiresAt: Date.now() + UNDO_WINDOW_SECONDS * 1000,
        });

        await loadBoard(true);
        await loadTimeline(app.application_id);
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to reschedule interview.');
      } finally {
        setActionLoading('');
      }
    },
    [loadBoard, loadTimeline]
  );

  const cancelInterview = useCallback(
    async (app: PipelineApplication) => {
      const interviewId = app.latest_interview?.interview_id;
      if (!interviewId) {
        setError('No scheduled interview found for this candidate.');
        return;
      }

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const confirmed = window.confirm('Cancel this interview?');
        if (!confirmed) return;
      }

      const actionId = `cancel-${app.application_id}`;
      setActionLoading(actionId);
      setError('');
      try {
        const previousSlot = extractDateTimeFromIso(app.latest_interview?.scheduled_start);
        await api.post(`/interviews/${interviewId}/cancel`, {
          reason: 'Cancelled from Employer Pipeline Board',
        });

        setUndoAction({
          kind: 'cancel',
          interviewId,
          applicationId: app.application_id,
          candidateName: app.candidate_name || 'Candidate',
          previousDate: previousSlot.date,
          previousTime: previousSlot.time,
          previousTimezone: app.latest_interview?.timezone || 'UTC',
          expiresAt: Date.now() + UNDO_WINDOW_SECONDS * 1000,
        });

        await loadBoard(true);
        await loadTimeline(app.application_id);
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to cancel interview.');
      } finally {
        setActionLoading('');
      }
    },
    [loadBoard, loadTimeline]
  );

  const undoLastInterviewAction = useCallback(async () => {
    if (!undoAction) return;
    if (Date.now() > undoAction.expiresAt) {
      setUndoAction(null);
      setUndoSecondsRemaining(0);
      return;
    }

    setActionLoading('undo-interview-action');
    setError('');
    try {
      await api.post(`/interviews/${undoAction.interviewId}/reschedule`, {
        new_date: undoAction.previousDate,
        new_time: undoAction.previousTime,
        timezone: undoAction.previousTimezone || 'UTC',
        reason: `Undo ${undoAction.kind} from 30-second safety window`,
      });

      const applicationId = undoAction.applicationId;
      setUndoAction(null);
      setUndoSecondsRemaining(0);
      await loadBoard(true);
      await loadTimeline(applicationId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to undo interview action.');
    } finally {
      setActionLoading('');
    }
  }, [undoAction, loadBoard, loadTimeline]);

  const generateInterviewKit = useCallback(async () => {
    if (!selectedAppId) return;
    setActionLoading('generate-interview-kit');
    setError('');
    try {
      const res = await api.post(`/hiring/v2/employer/interview-kit/${selectedAppId}/generate`);
      setInterviewKit(res.data?.interview_kit || null);
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to generate interview kit.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadTimeline]);

  const shareInterviewKit = useCallback(async () => {
    if (!selectedAppId) return;
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setError('Interview kit sharing prompt is available on web mode only.');
      return;
    }
    const raw = window.prompt('Enter panel emails (comma separated)', '');
    if (!raw) return;
    const note = window.prompt('Optional note for panelists', 'Please review this kit before interview.') || '';
    const panelEmails = raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (panelEmails.length === 0) return;

    setActionLoading('share-interview-kit');
    setError('');
    try {
      await api.post(`/hiring/v2/employer/interview-kit/${selectedAppId}/share`, { panel_emails: panelEmails, note });
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to share interview kit.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadTimeline]);

  const buildOfferDraft = useCallback(async () => {
    if (!selectedAppId || Platform.OS !== 'web' || typeof window === 'undefined') return;
    const salary = Number(window.prompt('Base salary (USD)', '120000') || '120000');
    const startDate = window.prompt('Start date (YYYY-MM-DD)', '') || '';
    const expiresAt = window.prompt('Offer expiry (YYYY-MM-DD)', '') || '';
    const personalMessage = window.prompt('Personal message (optional)', '') || '';
    if (!startDate || !expiresAt) {
      setError('Start date and expiry date are required to build offer draft.');
      return;
    }

    setActionLoading('build-offer-draft');
    setError('');
    try {
      await api.post('/hiring/v2/employer/offers/build', {
        application_id: selectedAppId,
        base_salary_usd: salary,
        start_date: startDate,
        expires_at: expiresAt,
        personal_message: personalMessage,
      });
      await loadOffers(selectedAppId);
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to build offer draft.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadOffers, loadTimeline]);

  const submitOfferForApproval = useCallback(async (offerId: string) => {
    setActionLoading(`submit-offer-${offerId}`);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/offers/${offerId}/submit-approval`, { note: 'Submitted from Employer Console' });
      if (selectedAppId) {
        await loadOffers(selectedAppId);
        await loadTimeline(selectedAppId);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to submit offer for approval.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadOffers, loadTimeline]);

  const approveOffer = useCallback(async (offerId: string) => {
    setActionLoading(`approve-offer-${offerId}`);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/offers/${offerId}/approve`, { approver_name: 'Employer Console Approver' });
      if (selectedAppId) {
        await loadOffers(selectedAppId);
        await loadTimeline(selectedAppId);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to approve offer.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadOffers, loadTimeline]);

  const sendOffer = useCallback(async (offerId: string) => {
    setActionLoading(`send-offer-${offerId}`);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/offers/${offerId}/send`, {});
      if (selectedAppId) {
        await loadOffers(selectedAppId);
        await loadTimeline(selectedAppId);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to send offer.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadOffers, loadTimeline]);

  const executeCopilotAction = useCallback(async (actionKey: string) => {
    if (!selectedAppId) return;
    setActionLoading(`copilot-${actionKey}`);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/pipeline/${selectedAppId}/copilot-execute`, {
        action_key: actionKey,
        reason: 'Triggered from Recruiter Copilot panel',
      });
      await loadBoard(true);
      await loadTimeline(selectedAppId);
      await loadCopilotSuggestions(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to execute copilot action.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadBoard, loadTimeline, loadCopilotSuggestions]);

  const toggleBulkSelection = useCallback((applicationId: string) => {
    setBulkSelection((prev) => (prev.includes(applicationId) ? prev.filter((id) => id !== applicationId) : [...prev, applicationId]));
  }, []);

  const selectAllVisible = useCallback(() => {
    const ids = filteredApplications.map((app) => app.application_id);
    setBulkSelection(ids);
  }, [filteredApplications]);

  const clearBulkSelection = useCallback(() => {
    setBulkSelection([]);
  }, []);

  const executeBulkAction = useCallback(async (action: 'move_stage' | 'reject' | 'send_followup', targetStatus?: StageKey) => {
    if (bulkSelection.length === 0) {
      setError('Select at least one candidate for bulk action.');
      return;
    }
    const actionKey = `bulk-${action}-${targetStatus || 'none'}`;
    setActionLoading(actionKey);
    setError('');
    try {
      await api.post('/hiring/v2/employer/pipeline/bulk-action', {
        application_ids: bulkSelection,
        action,
        target_status: targetStatus,
        note: 'Bulk action triggered from Employer Console',
      });
      setBulkSelection([]);
      await loadBoard(true);
      if (selectedAppId) {
        await loadTimeline(selectedAppId);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Bulk action failed.');
    } finally {
      setActionLoading('');
    }
  }, [bulkSelection, selectedAppId, loadBoard, loadTimeline]);

  const submitScorecard = useCallback(async () => {
    if (!selectedAppId) return;
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setError('Scorecard submission prompt is available on web mode only.');
      return;
    }

    const technical = Number(window.prompt('Technical score (1-5)', '4') || '4');
    const communication = Number(window.prompt('Communication score (1-5)', '4') || '4');
    const problemSolving = Number(window.prompt('Problem-solving score (1-5)', '4') || '4');
    const cultureFit = Number(window.prompt('Culture fit score (1-5)', '4') || '4');
    const recommendation = window.prompt('Recommendation (strong_hire|hire|lean_hire|no_hire)', 'lean_hire') || 'lean_hire';
    const debriefSummary = window.prompt('Panel debrief summary', 'Candidate shows good momentum for next round.') || '';

    setActionLoading('submit-scorecard');
    setError('');
    try {
      await api.post(`/hiring/v2/employer/scorecards/${selectedAppId}`, {
        technical_score: technical,
        communication_score: communication,
        problem_solving_score: problemSolving,
        culture_fit_score: cultureFit,
        recommendation,
        debrief_summary: debriefSummary,
      });
      await loadScorecards(selectedAppId);
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to submit scorecard.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadScorecards, loadTimeline]);

  const loadAutoSchedulerSlots = useCallback(async () => {
    if (!selectedAppId) return;
    setActionLoading('load-auto-scheduler-slots');
    setError('');
    try {
      const res = await api.get(`/jobs/employer/auto-scheduler/${selectedAppId}/suggest`, {
        params: { days_ahead: 10, duration_minutes: 45 },
      });
      setAutoSlots((res.data?.slots || []) as AutoSchedulerSlot[]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to fetch auto-scheduler slots.');
      setAutoSlots([]);
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId]);

  const bookAutoSchedulerSlot = useCallback(async (slot: AutoSchedulerSlot) => {
    if (!selectedAppId) return;
    setActionLoading(`book-slot-${slot.start}`);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/auto-scheduler/${selectedAppId}/book`, {
        start: slot.start,
        end: slot.end,
        timezone: 'UTC',
        duration_minutes: slot.duration_minutes || 45,
        interview_type: 'video',
      });
      await loadBoard(true);
      await loadTimeline(selectedAppId);
      setAutoSlots([]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to book slot.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadBoard, loadTimeline]);

  const startCommunicationSequence = useCallback(async () => {
    if (!selectedAppId) return;
    setActionLoading('start-communication-sequence');
    setError('');
    try {
      await api.post(`/hiring/v2/employer/communication-sequences/${selectedAppId}/start`, {
        channel: 'email_inapp',
        track: 'stage_progression',
      });
      await loadSequence(selectedAppId);
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to start communication sequence.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadSequence, loadTimeline]);

  const advanceCommunicationSequence = useCallback(async () => {
    if (!selectedAppId) return;
    setActionLoading('advance-communication-sequence');
    setError('');
    try {
      await api.post(`/hiring/v2/employer/communication-sequences/${selectedAppId}/advance`, {
        note: 'Advancing sequence from Employer Console',
      });
      await loadSequence(selectedAppId);
      await loadTimeline(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to advance communication sequence.');
    } finally {
      setActionLoading('');
    }
  }, [selectedAppId, loadSequence, loadTimeline]);

  const reengageRediscoveryCandidate = useCallback(async (candidate: RediscoveryCandidate) => {
    if (!selectedApplication?.job_id) {
      setError('Select a candidate with a valid job context to re-engage talent.');
      return;
    }
    const actionKey = `reengage-${candidate.candidate_id}`;
    setActionLoading(actionKey);
    setError('');
    try {
      await api.post(`/hiring/v2/employer/talent-rediscovery/${candidate.candidate_id}/reengage`, {
        job_id: selectedApplication.job_id,
      });
      await loadRediscovery(selectedApplication.job_id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to re-engage candidate.');
    } finally {
      setActionLoading('');
    }
  }, [selectedApplication, loadRediscovery]);

  const runSlaAutoTrigger = useCallback(async (applicationId?: string) => {
    const actionKey = applicationId ? `run-sla-auto-trigger-${applicationId}` : 'run-sla-auto-trigger-all';
    setActionLoading(actionKey);
    setError('');
    try {
      await api.post('/hiring/v2/employer/sla-auto-triggers/run', {
        application_id: applicationId,
        max_items: applicationId ? 1 : 8,
      });
      await loadSlaAutoTriggers();
      await loadBoard(true);
      if (selectedAppId) {
        await loadTimeline(selectedAppId);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to run SLA auto-trigger.');
    } finally {
      setActionLoading('');
    }
  }, [loadBoard, loadSlaAutoTriggers, loadTimeline, selectedAppId]);

  const exportTimelineAudit = useCallback(async (format: 'csv' | 'pdf') => {
    if (!selectedAppId) {
      setError('Select a candidate first to export audit history.');
      return;
    }
    if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') {
      setError('Audit export is available on web mode only.');
      return;
    }

    const actionKey = `audit-export-${format}`;
    setActionLoading(actionKey);
    setError('');
    try {
      const res = await api.get(`/jobs/employer/pipeline-board/${selectedAppId}/audit-export.${format}`, {
        params: { range_key: auditRange },
        responseType: 'blob' as any,
      });
      const mime = format === 'pdf' ? 'application/pdf' : 'text/csv;charset=utf-8;';
      const blob = new Blob([res.data], { type: mime });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `hiring-audit-${selectedAppId}-${auditRange}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      await loadAuditDownloadHistory(selectedAppId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || `Failed to export ${format.toUpperCase()} audit.`);
    } finally {
      setActionLoading('');
    }
  }, [auditRange, loadAuditDownloadHistory, selectedAppId]);

  const grouped = useMemo(() => {
    const map: Record<string, PipelineApplication[]> = {};
    STAGES.forEach((s) => {
      map[s] = [];
    });
    filteredApplications.forEach((app) => {
      const status = String(app.status || 'applied').toLowerCase();
      const key = STAGES.includes(status as StageKey) ? (status as StageKey) : 'applied';
      map[key].push(app);
    });
    return map;
  }, [filteredApplications]);

  const filteredCount = useMemo(() => STAGES.reduce((acc, stage) => acc + grouped[stage].length, 0), [grouped]);

  useEffect(() => {
    const visibleIds = new Set(filteredApplications.map((app) => app.application_id));
    setBulkSelection((prev) => prev.filter((id) => visibleIds.has(id)));
  }, [filteredApplications]);

  useEffect(() => {
    const hasSelected = STAGES.some((stage) => grouped[stage].some((app) => app.application_id === selectedAppId));
    if (!hasSelected) {
      const fallback = STAGES.flatMap((stage) => grouped[stage])[0];
      if (fallback?.application_id) {
        setSelectedAppId(fallback.application_id);
      }
    }
  }, [grouped, selectedAppId]);

  const dropToStage = useCallback(
    async (stage: StageKey) => {
      if (!draggingAppId) return;
      const app = applications.find((row) => row.application_id === draggingAppId);
      setDraggingAppId('');
      if (!app) return;
      if (String(app.status).toLowerCase() === stage) return;
      await updateStage(app, stage);
    },
    [applications, draggingAppId, updateStage]
  );

  if (loading) {
    return (
      <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: cardBorder, borderRadius: 14, padding: 18 }} data-testid="employer-pipeline-board-loading" testID="employer-pipeline-board-loading">
        <ActivityIndicator color={colors.primary} />
        <Text style={{ color: muted, fontSize: 12, marginTop: 8 }}>Loading employer hiring pipeline...</Text>
      </View>
    );
  }

  return (
    <View style={{ marginTop: 16, marginBottom: 24, backgroundColor: cardBg, borderWidth: 1, borderColor: cardBorder, borderRadius: 16, padding: 14 }} data-testid="employer-pipeline-board" testID="employer-pipeline-board">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <View>
          <Text style={{ color: titleColor, fontSize: 18, fontWeight: '800' }} data-testid="employer-pipeline-board-title" testID="employer-pipeline-board-title">Hiring Pipeline Board</Text>
          <Text style={{ color: muted, fontSize: 11, marginTop: 2 }} data-testid="employer-pipeline-board-subtitle" testID="employer-pipeline-board-subtitle">
            Drag candidates between stages or use quick actions directly.
          </Text>
        </View>
        <Pressable
          onPress={() => void loadBoard(true)}
          disabled={refreshing || !!actionLoading}
          style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: laneBg }}
          data-testid="employer-pipeline-refresh-button"
          testID="employer-pipeline-refresh-button"
        >
          <Text style={{ color: titleColor, fontSize: 11, fontWeight: '700' }}>{refreshing ? 'Refreshing...' : 'Refresh Board'}</Text>
        </Pressable>
      </View>

      <View
        style={{
          borderWidth: 1,
          borderColor: cardBorder,
          borderRadius: 10,
          backgroundColor: cardBg,
          paddingHorizontal: 10,
          paddingVertical: 8,
          marginBottom: 10,
          ...(Platform.OS === 'web' ? ({ position: 'sticky', top: 8, zIndex: 30 } as any) : {}),
        }}
        data-testid="employer-pipeline-breadcrumb"
        testID="employer-pipeline-breadcrumb"
      >
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingRight: 6 }}
          data-testid="employer-pipeline-breadcrumb-scroll"
          testID="employer-pipeline-breadcrumb-scroll"
        >
          <Pressable accessibilityLabel="Employer pipeline breadcrumb kpi button"
            onPress={() => {
              setActiveFilter('all');
              onClearDrilldown?.();
            }}
            style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 999, backgroundColor: laneBg, paddingHorizontal: 8, paddingVertical: 4 }}
            data-testid="employer-pipeline-breadcrumb-kpi"
            testID="employer-pipeline-breadcrumb-kpi"
          >
            <Text style={{ color: titleColor, fontSize: 10, fontWeight: '800' }}>{isCompactBreadcrumb ? 'KPI' : 'KPI Metrics'}</Text>
          </Pressable>

          <Text style={{ color: muted, fontSize: 10 }}>{'>'}</Text>

          <Pressable accessibilityLabel="Employer pipeline breadcrumb filter button"
            onPress={() => {
              setActiveFilter('all');
              onClearDrilldown?.();
            }}
            style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(activeFilter === 'all' ? cardBorder : colors.primary, '55'), borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(activeFilter === 'all' ? laneBg : colors.primary, '12'), paddingHorizontal: 8, paddingVertical: 4 }}
            data-testid="employer-pipeline-breadcrumb-filter"
            testID="employer-pipeline-breadcrumb-filter"
          >
            <Text style={{ color: activeFilter === 'all' ? muted : colors.primary, fontSize: 10, fontWeight: '800', textTransform: 'capitalize' }}>
              {isCompactBreadcrumb ? filterLabel.replace(' candidates', '') : filterLabel}
            </Text>
          </Pressable>

          <Text style={{ color: muted, fontSize: 10 }}>{'>'}</Text>

          <Pressable accessibilityLabel="Employer pipeline breadcrumb candidate button"
            onPress={() => {
              if (selectedApplication?.application_id) setSelectedAppId(selectedApplication.application_id);
            }}
            style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 999, backgroundColor: laneBg, paddingHorizontal: 8, paddingVertical: 4, maxWidth: isCompactBreadcrumb ? 150 : 260 }}
            data-testid="employer-pipeline-breadcrumb-candidate"
            testID="employer-pipeline-breadcrumb-candidate"
            {...(Platform.OS === 'web' ? ({ title: selectedApplication?.candidate_name || '' } as any) : {})}
          >
            <Text style={{ color: titleColor, fontSize: 10, fontWeight: '800' }} numberOfLines={1}>
              {selectedApplication?.candidate_name || 'No candidate selected'}
            </Text>
          </Pressable>
        </ScrollView>
      </View>

      {error ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.error}55`, backgroundColor: colors.errorSoft, padding: 10, marginBottom: 10 }} data-testid="employer-pipeline-error" testID="employer-pipeline-error">
          <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '700' }}>{error}</Text>
        </View>
      ) : null}

      <View style={{ borderRadius: 10, borderWidth: 1, borderColor: cardBorder, backgroundColor: laneBg, padding: 10, marginBottom: 10 }} data-testid="employer-pipeline-live-sync-banner" testID="employer-pipeline-live-sync-banner">
        <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }} data-testid="employer-pipeline-live-sync-status" testID="employer-pipeline-live-sync-status">
          Live Sync: {liveSyncStatus === 'connected' ? 'Connected' : liveSyncStatus === 'connecting' ? 'Connecting' : liveSyncStatus === 'reconnecting' ? 'Reconnecting' : 'Idle'}
        </Text>
        <Text style={{ color: muted, fontSize: 10, marginTop: 4 }} data-testid="employer-pipeline-live-sync-summary" testID="employer-pipeline-live-sync-summary">
          {liveSyncMessage || 'Interview actions and shared undo windows update across recruiter tabs in real time.'} {liveSyncMembers > 0 ? `· Active recruiter tabs: ${liveSyncMembers}` : ''}
        </Text>
      </View>

      {sharedUndoNotice && sharedUndoSecondsRemaining > 0 ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), backgroundColor: colors.infoSoft, padding: 10, marginBottom: 10 }} data-testid="employer-pipeline-shared-undo-banner" testID="employer-pipeline-shared-undo-banner">
          <Text style={{ color: colors.infoText, fontSize: 11, fontWeight: '700' }} data-testid="employer-pipeline-shared-undo-text" testID="employer-pipeline-shared-undo-text">
            {sharedUndoNotice.actorName} has a {sharedUndoNotice.kind} undo window open for {sharedUndoNotice.candidateName}. {sharedUndoSecondsRemaining}s left.
          </Text>
          <Text style={{ color: muted, fontSize: 10, marginTop: 4 }}>{sharedUndoNotice.message}</Text>
        </View>
      ) : null}

      {undoAction && undoSecondsRemaining > 0 ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }} data-testid="employer-pipeline-undo-banner" testID="employer-pipeline-undo-banner">
          <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700', flex: 1 }}>
            {undoAction.kind === 'cancel' ? 'Interview cancelled' : 'Interview rescheduled'} for {undoAction.candidateName}. Undo available for {undoSecondsRemaining}s.
          </Text>
          <Pressable
            onPress={() => void undoLastInterviewAction()}
            disabled={actionLoading === 'undo-interview-action'}
            style={{ borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: (globalThis as any).__alphaColor(colors.warning, '18'), paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-pipeline-undo-interview-action-button"
            testID="employer-pipeline-undo-interview-action-button"
          >
            <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '800' }}>
              {actionLoading === 'undo-interview-action' ? 'Undoing...' : 'Undo'}
            </Text>
          </Pressable>
        </View>
      ) : null}

      <View style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 10, backgroundColor: laneBg, padding: 10, marginBottom: 12 }} data-testid="employer-pipeline-bulk-panel" testID="employer-pipeline-bulk-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }} data-testid="employer-pipeline-bulk-selected-count" testID="employer-pipeline-bulk-selected-count">
            Bulk Actions · {bulkSelection.length} selected
          </Text>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <Pressable
              onPress={selectAllVisible}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: cardBg, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid="employer-pipeline-bulk-select-all-button"
              testID="employer-pipeline-bulk-select-all-button"
            >
              <Text style={{ color: muted, fontSize: 9, fontWeight: '800' }}>Select visible</Text>
            </Pressable>
            <Pressable
              onPress={clearBulkSelection}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: cardBg, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid="employer-pipeline-bulk-clear-button"
              testID="employer-pipeline-bulk-clear-button"
            >
              <Text style={{ color: muted, fontSize: 9, fontWeight: '800' }}>Clear</Text>
            </Pressable>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
          {(['viewed', 'interview', 'offer', 'hired', 'rejected'] as StageKey[]).map((stage) => (
            <Pressable accessibilityLabel="Execute bulk action in employer pipeline board button"
              key={`bulk-${stage}`}
              onPress={() => void executeBulkAction(stage === 'rejected' ? 'reject' : 'move_stage', stage)}
              disabled={bulkSelection.length === 0 || !!actionLoading}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: cardBg, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid={`employer-pipeline-bulk-move-${stage}-button`}
              testID={`employer-pipeline-bulk-move-${stage}-button`}
            >
              <Text style={{ color: titleColor, fontSize: 9, fontWeight: '800' }}>{stage === 'rejected' ? 'Bulk Reject' : `Move ${STAGE_LABEL[stage]}`}</Text>
            </Pressable>
          ))}
          <Pressable
            onPress={() => void executeBulkAction('send_followup')}
            disabled={bulkSelection.length === 0 || !!actionLoading}
            style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 9, paddingVertical: 5 }}
            data-testid="employer-pipeline-bulk-send-followup-button"
            testID="employer-pipeline-bulk-send-followup-button"
          >
            <Text style={{ color: colors.infoText, fontSize: 9, fontWeight: '800' }}>Send Follow-up</Text>
          </Pressable>
        </View>
      </View>

      <View style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 10, backgroundColor: laneBg, padding: 10, marginBottom: 12 }} data-testid="employer-pipeline-drilldown-bar" testID="employer-pipeline-drilldown-bar">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }} data-testid="employer-pipeline-drilldown-title" testID="employer-pipeline-drilldown-title">
            KPI Drill-down: {activeFilter === 'all' ? 'All candidates' : activeFilter.replace(/-/g, ' ')} · {filteredCount} visible
          </Text>
          <Pressable accessibilityLabel="Employer pipeline clear drilldown button"
            onPress={() => {
              setActiveFilter('all');
              onClearDrilldown?.();
            }}
            style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: cardBg, paddingHorizontal: 9, paddingVertical: 5 }}
            data-testid="employer-pipeline-clear-drilldown-button"
            testID="employer-pipeline-clear-drilldown-button"
          >
            <Text style={{ color: muted, fontSize: 10, fontWeight: '800' }}>Clear filter</Text>
          </Pressable>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
          {(['all', 'time-to-hire', 'stage-conversion', 'offer-acceptance', 'active-bottlenecks'] as DrilldownFilterKey[]).map((filterKey) => (
            <Pressable
              key={filterKey}
              onPress={() => setActiveFilter(filterKey)}
              style={{ borderWidth: 1, borderColor: activeFilter === filterKey ? (globalThis as any).__alphaColor(colors.primary, '66') : cardBorder, borderRadius: 999, backgroundColor: activeFilter === filterKey ? (globalThis as any).__alphaColor(colors.primary, '12') : cardBg, paddingHorizontal: 10, paddingVertical: 5 }}
              data-testid={`employer-pipeline-drilldown-chip-${filterKey}`}
              testID={`employer-pipeline-drilldown-chip-${filterKey}`}
            >
              <Text style={{ color: activeFilter === filterKey ? colors.primary : muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>
                {filterKey === 'all' ? 'All' : filterKey.replace(/-/g, ' ')}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }} data-testid="employer-pipeline-counts" testID="employer-pipeline-counts">
        {STAGES.map((stage) => (
          <View key={stage} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 10, backgroundColor: laneBg, paddingVertical: 8, paddingHorizontal: 10 }} data-testid={`employer-pipeline-count-${stage}`} testID={`employer-pipeline-count-${stage}`}>
            <Text style={{ color: muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{STAGE_LABEL[stage]}</Text>
            <Text style={{ color: titleColor, fontSize: 17, fontWeight: '800' }} data-testid={`employer-pipeline-count-value-${stage}`} testID={`employer-pipeline-count-value-${stage}`}>{Number(counts[stage] || 0)}</Text>
          </View>
        ))}
      </View>

      {Number(slaAlerts.overdue_total || 0) > 0 ? (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 12 }} data-testid="employer-pipeline-sla-alert-banner" testID="employer-pipeline-sla-alert-banner">
          <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }} data-testid="employer-pipeline-sla-alert-title" testID="employer-pipeline-sla-alert-title">
            Bottleneck Alert: {Number(slaAlerts.overdue_total || 0)} candidates are beyond SLA thresholds.
          </Text>
          <Text style={{ color: muted, fontSize: 10, marginTop: 4 }} data-testid="employer-pipeline-sla-alert-subtitle" testID="employer-pipeline-sla-alert-subtitle">
            Prioritize stalled stages to keep hiring velocity on track.
          </Text>
        </View>
      ) : null}

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: cardBorder, backgroundColor: laneBg, padding: 12, marginBottom: 12 }} data-testid="employer-sla-auto-trigger-panel" testID="employer-sla-auto-trigger-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-sla-auto-trigger-title" testID="employer-sla-auto-trigger-title">SLA Auto-Triggers</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }} data-testid="employer-sla-auto-trigger-subtitle" testID="employer-sla-auto-trigger-subtitle">
              Recover stalled candidates automatically with follow-ups, slot suggestions, and rediscovery nudges.
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Pressable
              onPress={() => void loadSlaAutoTriggers()}
              disabled={!!actionLoading}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: cardBg, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-sla-auto-trigger-refresh-button"
              testID="employer-sla-auto-trigger-refresh-button"
            >
              <Text style={{ color: muted, fontSize: 10, fontWeight: '800' }}>Refresh</Text>
            </Pressable>
            <Pressable
              onPress={() => void runSlaAutoTrigger()}
              disabled={!!actionLoading || Number(slaAutoTriggers?.summary?.pending_total || 0) === 0}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-sla-auto-trigger-run-all-button"
              testID="employer-sla-auto-trigger-run-all-button"
            >
              <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '800' }}>
                {actionLoading === 'run-sla-auto-trigger-all' ? 'Running...' : 'Run Due Triggers'}
              </Text>
            </Pressable>
          </View>
        </View>

        <Text style={{ color: titleColor, fontSize: 11, fontWeight: '700', marginTop: 8 }} data-testid="employer-sla-auto-trigger-summary" testID="employer-sla-auto-trigger-summary">
          Pending: {Number(slaAutoTriggers?.summary?.pending_total || 0)} · Cooling down: {Number(slaAutoTriggers?.summary?.cooldown_total || 0)}
        </Text>

        <View style={{ marginTop: 10, gap: 8 }}>
          {(slaAutoTriggers?.items || []).slice(0, 4).map((item, idx) => (
            <View key={item.trigger_id || `${item.application_id}-${idx}`} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 9, backgroundColor: cardBg, padding: 8 }} data-testid={`employer-sla-auto-trigger-item-${idx}`} testID={`employer-sla-auto-trigger-item-${idx}`}>
              <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }}>
                {item.candidate_name} · {item.trigger_label}
              </Text>
              <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>
                {item.job_title} · Stage {String(item.stage || '').toUpperCase()} · Overdue by {Number(item.overdue_by_days || 0)} day(s)
              </Text>
              <Text style={{ color: muted, fontSize: 10, marginTop: 4 }}>
                {item.reason || 'No recommendation reason available.'}
              </Text>
              {item.trigger_action === 'open_slot_suggestion' && Array.isArray(item.suggested_slots) && item.suggested_slots.length > 0 ? (
                <Text style={{ color: colors.infoText, fontSize: 10, marginTop: 4 }} data-testid={`employer-sla-auto-trigger-slot-preview-${idx}`} testID={`employer-sla-auto-trigger-slot-preview-${idx}`}>
                  Slot preview: {item.suggested_slots.slice(0, 2).map((slot) => `${slot.date} ${slot.time}`).join(' • ')}
                </Text>
              ) : null}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, gap: 8 }}>
                <Text style={{ color: item.status === 'cooldown_active' ? colors.warningText : colors.successText, fontSize: 10, fontWeight: '800' }}>
                  {item.status === 'cooldown_active' ? 'Cooldown active' : 'Ready to run'}
                </Text>
                <Pressable
                  onPress={() => void runSlaAutoTrigger(item.application_id)}
                  disabled={!!actionLoading || item.status === 'cooldown_active'}
                  style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: laneBg, paddingHorizontal: 9, paddingVertical: 5 }}
                  data-testid={`employer-sla-auto-trigger-run-${item.application_id}`}
                  testID={`employer-sla-auto-trigger-run-${item.application_id}`}
                >
                  <Text style={{ color: titleColor, fontSize: 9, fontWeight: '800' }}>
                    {actionLoading === `run-sla-auto-trigger-${item.application_id}` ? 'Running...' : 'Run Trigger'}
                  </Text>
                </Pressable>
              </View>
            </View>
          ))}
          {(!slaAutoTriggers?.items || slaAutoTriggers.items.length === 0) ? (
            <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-sla-auto-trigger-empty" testID="employer-sla-auto-trigger-empty">
              No stalled candidates need automatic recovery right now.
            </Text>
          ) : null}
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ gap: 10, paddingBottom: 10 }} data-testid="employer-pipeline-stage-scroll" testID="employer-pipeline-stage-scroll">
        {STAGES.map((stage) => (
          <View
            key={stage}
            style={{ width: 300, borderRadius: 12, borderWidth: 1, borderColor: cardBorder, backgroundColor: laneBg, padding: 10, minHeight: 420 }}
            data-testid={`employer-pipeline-stage-${stage}-column`}
            testID={`employer-pipeline-stage-${stage}-column`}
            {...(Platform.OS === 'web'
              ? ({
                  onDragOver: (e: any) => e.preventDefault(),
                  onDrop: (e: any) => {
                    e.preventDefault();
                    void dropToStage(stage);
                  },
                } as any)
              : {})}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ color: titleColor, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' }}>{STAGE_LABEL[stage]}</Text>
              <Text style={{ color: muted, fontSize: 11, fontWeight: '700' }} data-testid={`employer-pipeline-stage-${stage}-count`} testID={`employer-pipeline-stage-${stage}-count`}>{grouped[stage].length}</Text>
            </View>

            <View style={{ gap: 8 }}>
              {grouped[stage].map((app) => (
                <Pressable
                  key={app.application_id}
                  onPress={() => setSelectedAppId(app.application_id)}
                  style={{ borderWidth: 1, borderColor: selectedAppId === app.application_id ? (globalThis as any).__alphaColor(colors.primary, '70') : cardBorder, borderRadius: 10, backgroundColor: cardBg, padding: 10 }}
                  data-testid={`employer-pipeline-card-${app.application_id}`}
                  testID={`employer-pipeline-card-${app.application_id}`}
                  {...(Platform.OS === 'web'
                    ? ({
                        draggable: true,
                        onDragStart: () => setDraggingAppId(app.application_id),
                        onDragEnd: () => setDraggingAppId(''),
                      } as any)
                    : {})}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <Pressable
                      onPress={() => toggleBulkSelection(app.application_id)}
                      style={{ borderWidth: 1, borderColor: bulkSelection.includes(app.application_id) ? colors.primary : cardBorder, borderRadius: 999, backgroundColor: bulkSelection.includes(app.application_id) ? (globalThis as any).__alphaColor(colors.primary, '14') : laneBg, paddingHorizontal: 8, paddingVertical: 3 }}
                      data-testid={`employer-pipeline-card-bulk-select-${app.application_id}`}
                      testID={`employer-pipeline-card-bulk-select-${app.application_id}`}
                    >
                      <Text style={{ color: bulkSelection.includes(app.application_id) ? colors.primary : muted, fontSize: 9, fontWeight: '800' }}>
                        {bulkSelection.includes(app.application_id) ? 'Selected' : 'Select'}
                      </Text>
                    </Pressable>
                    <Text style={{ color: muted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }} data-testid={`employer-pipeline-card-stage-${app.application_id}`} testID={`employer-pipeline-card-stage-${app.application_id}`}>
                      {String(app.status || 'applied')}
                    </Text>
                  </View>

                  <Text style={{ color: titleColor, fontSize: 13, fontWeight: '800' }} numberOfLines={1} data-testid={`employer-pipeline-card-candidate-${app.application_id}`} testID={`employer-pipeline-card-candidate-${app.application_id}`}>
                    {app.candidate_name || 'Candidate'}
                  </Text>
                  <Text style={{ color: muted, fontSize: 10, marginTop: 2 }} numberOfLines={1}>{app.candidate_email || 'No email'}</Text>
                  <Text style={{ color: muted, fontSize: 10, marginTop: 4 }} numberOfLines={1} data-testid={`employer-pipeline-card-job-${app.application_id}`} testID={`employer-pipeline-card-job-${app.application_id}`}>
                    {app.job_title}
                  </Text>

                  <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '700' }} data-testid={`employer-pipeline-card-score-${app.application_id}`} testID={`employer-pipeline-card-score-${app.application_id}`}>
                      Resume: {Number(app.resume_score || 0)}
                    </Text>
                    <Text style={{ color: app.match_score && app.match_score >= 75 ? colors.successText : colors.infoText, fontSize: 10, fontWeight: '700' }} data-testid={`employer-pipeline-card-match-score-${app.application_id}`} testID={`employer-pipeline-card-match-score-${app.application_id}`}>
                      Match: {Number(app.match_score || 0)}
                    </Text>
                    {app.latest_interview?.status ? (
                      <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '700' }} data-testid={`employer-pipeline-card-interview-status-${app.application_id}`} testID={`employer-pipeline-card-interview-status-${app.application_id}`}>
                        {String(app.latest_interview.status).toUpperCase()}
                      </Text>
                    ) : null}
                  </View>

                  {Array.isArray(app.match_reasons) && app.match_reasons.length > 0 ? (
                    <Text style={{ color: muted, fontSize: 9, marginTop: 4 }} numberOfLines={2} data-testid={`employer-pipeline-card-match-reasons-${app.application_id}`} testID={`employer-pipeline-card-match-reasons-${app.application_id}`}>
                      {app.match_reasons[0]}
                    </Text>
                  ) : null}

                  {app.sla_breached ? (
                    <Text style={{ color: colors.warningText, fontSize: 9, marginTop: 4, fontWeight: '700' }} data-testid={`employer-pipeline-card-sla-breach-${app.application_id}`} testID={`employer-pipeline-card-sla-breach-${app.application_id}`}>
                      SLA breach: {Number(app.sla_age_days || 0)}d in stage (target {Number(app.sla_target_days || 0)}d)
                    </Text>
                  ) : null}

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {(['viewed', 'interview', 'offer', 'hired', 'rejected'] as StageKey[]).map((statusAction) => (
                      <Pressable accessibilityLabel="Update stage in employer pipeline board button"
                        key={`${app.application_id}-${statusAction}`}
                        onPress={() => void updateStage(app, statusAction)}
                        disabled={!!actionLoading}
                        style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: laneBg, paddingVertical: 4, paddingHorizontal: 6 }}
                        data-testid={`employer-pipeline-card-action-${statusAction}-${app.application_id}`}
                        testID={`employer-pipeline-card-action-${statusAction}-${app.application_id}`}
                      >
                        <Text style={{ color: titleColor, fontSize: 9, fontWeight: '800' }}>
                          {actionLoading === `status-${app.application_id}-${statusAction}` ? '...' : STAGE_LABEL[statusAction]}
                        </Text>
                      </Pressable>
                    ))}

                    <Pressable
                      onPress={() => void scheduleInterview(app)}
                      disabled={!!actionLoading}
                      style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), paddingVertical: 4, paddingHorizontal: 6 }}
                      data-testid={`employer-pipeline-card-schedule-interview-${app.application_id}`}
                      testID={`employer-pipeline-card-schedule-interview-${app.application_id}`}
                    >
                      <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '800' }}>
                        {actionLoading === `schedule-${app.application_id}` ? 'Scheduling...' : 'Schedule Interview'}
                      </Text>
                    </Pressable>

                    {app.latest_interview?.interview_id ? (
                      <>
                        <Pressable
                          onPress={() => void rescheduleInterview(app)}
                          disabled={!!actionLoading}
                          style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '12'), paddingVertical: 4, paddingHorizontal: 6 }}
                          data-testid={`employer-pipeline-card-reschedule-interview-${app.application_id}`}
                          testID={`employer-pipeline-card-reschedule-interview-${app.application_id}`}
                        >
                          <Text style={{ color: colors.warningText, fontSize: 9, fontWeight: '800' }}>
                            {actionLoading === `reschedule-${app.application_id}` ? 'Rescheduling...' : 'Reschedule'}
                          </Text>
                        </Pressable>

                        <Pressable
                          onPress={() => void cancelInterview(app)}
                          disabled={!!actionLoading}
                          style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), paddingVertical: 4, paddingHorizontal: 6 }}
                          data-testid={`employer-pipeline-card-cancel-interview-${app.application_id}`}
                          testID={`employer-pipeline-card-cancel-interview-${app.application_id}`}
                        >
                          <Text style={{ color: colors.error, fontSize: 9, fontWeight: '800' }}>
                            {actionLoading === `cancel-${app.application_id}` ? 'Cancelling...' : 'Cancel Interview'}
                          </Text>
                        </Pressable>
                      </>
                    ) : null}

                    {Array.isArray(app.copilot_actions) && app.copilot_actions.length > 0 ? (
                      <Pressable accessibilityLabel="Set selected app id in employer pipeline board button"
                        onPress={() => {
                          setSelectedAppId(app.application_id);
                          void executeCopilotAction(app.copilot_actions?.[0]?.action_key || '');
                        }}
                        disabled={!!actionLoading}
                        style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingVertical: 4, paddingHorizontal: 6 }}
                        data-testid={`employer-pipeline-card-copilot-primary-${app.application_id}`}
                        testID={`employer-pipeline-card-copilot-primary-${app.application_id}`}
                      >
                        <Text style={{ color: colors.infoText, fontSize: 9, fontWeight: '800' }}>
                          {actionLoading.startsWith('copilot-') ? 'Copilot...' : `Copilot: ${app.copilot_actions?.[0]?.label || 'Next action'}`}
                        </Text>
                      </Pressable>
                    ) : null}
                  </View>
                </Pressable>
              ))}
              {grouped[stage].length === 0 ? (
                <View style={{ borderRadius: 10, borderWidth: 1, borderColor: cardBorder, borderStyle: 'dashed', backgroundColor: cardBg, padding: 12 }} data-testid={`employer-pipeline-empty-${stage}`} testID={`employer-pipeline-empty-${stage}`}>
                  <Text style={{ color: muted, fontSize: 11 }}>No candidates in this stage</Text>
                </View>
              ) : null}
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={{ marginTop: 8, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-pipeline-timeline-panel" testID="employer-pipeline-timeline-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-pipeline-timeline-title" testID="employer-pipeline-timeline-title">
            Candidate Timeline {selectedApplication ? `• ${selectedApplication.candidate_name}` : ''}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Pressable
              onPress={() => void exportTimelineAudit('csv')}
              disabled={!selectedAppId || !!actionLoading}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: cardBg, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid="employer-pipeline-timeline-export-csv-button"
              testID="employer-pipeline-timeline-export-csv-button"
            >
              <Text style={{ color: titleColor, fontSize: 9, fontWeight: '800' }}>{actionLoading === 'audit-export-csv' ? 'Exporting...' : 'Export CSV'}</Text>
            </Pressable>
            <Pressable
              onPress={() => void exportTimelineAudit('pdf')}
              disabled={!selectedAppId || !!actionLoading}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid="employer-pipeline-timeline-export-pdf-button"
              testID="employer-pipeline-timeline-export-pdf-button"
            >
              <Text style={{ color: colors.infoText, fontSize: 9, fontWeight: '800' }}>{actionLoading === 'audit-export-pdf' ? 'Exporting...' : 'Export PDF'}</Text>
            </Pressable>
            {timelineLoading ? <ActivityIndicator size="small" color={colors.primary} /> : null}
          </View>
        </View>

        <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="employer-pipeline-audit-range-group" testID="employer-pipeline-audit-range-group">
            {([
              { key: '30d', label: 'Last 30 days' },
              { key: '90d', label: 'Last 90 days' },
              { key: 'all', label: 'All time' },
            ] as { key: AuditRangeKey; label: string }[]).map((option) => (
              <Pressable accessibilityLabel="Set audit range in employer pipeline board button"
                key={option.key}
                onPress={() => setAuditRange(option.key)}
                style={{
                  borderWidth: 1,
                  borderColor: auditRange === option.key ? (globalThis as any).__alphaColor(colors.primary, '55') : cardBorder,
                  borderRadius: 999,
                  backgroundColor: auditRange === option.key ? (globalThis as any).__alphaColor(colors.primary, '12') : cardBg,
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                }}
                data-testid={`employer-pipeline-audit-range-${option.key}`}
                testID={`employer-pipeline-audit-range-${option.key}`}
              >
                <Text style={{ color: auditRange === option.key ? colors.primary : muted, fontSize: 9, fontWeight: '800' }}>{option.label}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-pipeline-audit-range-summary" testID="employer-pipeline-audit-range-summary">
            Export filter: {auditRange === '30d' ? 'Last 30 days' : auditRange === '90d' ? 'Last 90 days' : 'All time'}
          </Text>
        </View>

        <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 10, backgroundColor: cardBg, padding: 10 }} data-testid="employer-pipeline-audit-history-panel" testID="employer-pipeline-audit-history-panel">
          <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }} data-testid="employer-pipeline-audit-history-title" testID="employer-pipeline-audit-history-title">
            Signed Download History
          </Text>
          <Text style={{ color: muted, fontSize: 10, marginTop: 3 }} data-testid="employer-pipeline-audit-history-subtitle" testID="employer-pipeline-audit-history-subtitle">
            Recent export receipts for this candidate timeline. Each download is logged with a signature ID and range.
          </Text>
          <View style={{ marginTop: 8, gap: 6 }}>
            {auditDownloadHistory.slice(0, 4).map((entry, idx) => (
              <View key={entry.export_id || `${entry.signature_id || 'sig'}-${idx}`} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: laneBg, padding: 8 }} data-testid={`employer-pipeline-audit-history-item-${idx}`} testID={`employer-pipeline-audit-history-item-${idx}`}>
                <Text style={{ color: titleColor, fontSize: 10, fontWeight: '800' }}>
                  {String(entry.format || 'csv').toUpperCase()} · {entry.range_label || 'Custom Range'}
                </Text>
                <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>
                  Rows: {Number(entry.row_count || 0)} · Signed ID: {entry.signature_id || 'pending'}
                </Text>
                <Text style={{ color: muted, fontSize: 9, marginTop: 2 }}>
                  {entry.created_at ? new Date(entry.created_at).toLocaleString() : 'Unknown time'} · {entry.exported_by_name || 'Recruiter'}
                </Text>
              </View>
            ))}
            {selectedAppId && auditDownloadHistory.length === 0 ? (
              <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-pipeline-audit-history-empty" testID="employer-pipeline-audit-history-empty">
                No signed downloads yet for this candidate.
              </Text>
            ) : null}
            {!selectedAppId ? (
              <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-pipeline-audit-history-select-hint" testID="employer-pipeline-audit-history-select-hint">
                Select a candidate card to view signed export history.
              </Text>
            ) : null}
          </View>
        </View>

        <View style={{ marginTop: 10, gap: 8 }}>
          {timeline.slice(0, 12).map((event, idx) => (
            <View key={`${event.event_id || 'evt'}-${idx}`} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 9, backgroundColor: cardBg, padding: 9 }} data-testid={`employer-pipeline-timeline-item-${idx}`} testID={`employer-pipeline-timeline-item-${idx}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800', flex: 1 }} numberOfLines={1}>{event.title || event.event_type || 'Timeline Event'}</Text>
                <Text style={{ color: muted, fontSize: 10 }}>{event.created_at ? new Date(event.created_at).toLocaleString() : 'n/a'}</Text>
              </View>
              <Text style={{ color: muted, fontSize: 10, marginTop: 4 }}>
                {event.description || 'No description'}
              </Text>
            </View>
          ))}
          {!timelineLoading && timeline.length === 0 ? (
            <Text style={{ color: muted, fontSize: 11 }} data-testid="employer-pipeline-timeline-empty" testID="employer-pipeline-timeline-empty">
              Select a candidate card to view timeline history.
            </Text>
          ) : null}
        </View>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-copilot-panel" testID="employer-copilot-panel">
        <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-copilot-title" testID="employer-copilot-title">
          Recruiter Copilot Actions
        </Text>
        <Text style={{ color: muted, fontSize: 10, marginTop: 3 }}>
          AI-assisted next-best actions with one-click execution and audit logs.
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }} data-testid="employer-copilot-actions-row" testID="employer-copilot-actions-row">
          {(copilotInsight?.actions || []).slice(0, 6).map((action: any, idx: number) => (
            <Pressable accessibilityLabel="Execute copilot action in employer pipeline board button"
              key={`${action?.action_key || 'copilot'}-${idx}`}
              onPress={() => void executeCopilotAction(action?.action_key || '')}
              disabled={!!actionLoading}
              style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: cardBg, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid={`employer-copilot-action-${idx}`}
              testID={`employer-copilot-action-${idx}`}
            >
              <Text style={{ color: titleColor, fontSize: 10, fontWeight: '800' }}>
                {actionLoading === `copilot-${action?.action_key}` ? 'Running...' : action?.label || 'Copilot Action'}
              </Text>
            </Pressable>
          ))}
          {(!copilotInsight?.actions || copilotInsight.actions.length === 0) ? (
            <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-copilot-empty" testID="employer-copilot-empty">
              Select a candidate to view copilot recommendations.
            </Text>
          ) : null}
        </View>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-interview-kit-panel" testID="employer-interview-kit-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-interview-kit-title" testID="employer-interview-kit-title">One-Click Interview Kit</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Generate role-focused questions and share with panelists instantly.</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Pressable
              onPress={() => void generateInterviewKit()}
              disabled={!!actionLoading || !selectedAppId}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-interview-kit-generate-button"
              testID="employer-interview-kit-generate-button"
            >
              <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{actionLoading === 'generate-interview-kit' ? 'Generating...' : 'Generate Kit'}</Text>
            </Pressable>
            <Pressable
              onPress={() => void shareInterviewKit()}
              disabled={!!actionLoading || !selectedAppId}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-interview-kit-share-button"
              testID="employer-interview-kit-share-button"
            >
              <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '800' }}>{actionLoading === 'share-interview-kit' ? 'Sharing...' : 'Share to Panel'}</Text>
            </Pressable>
          </View>
        </View>

        {interviewKit ? (
          <View style={{ marginTop: 10, gap: 6 }} data-testid="employer-interview-kit-content" testID="employer-interview-kit-content">
            <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }} numberOfLines={2}>{interviewKit.panel_brief || 'No panel brief available.'}</Text>
            <Text style={{ color: muted, fontSize: 10 }}>
              Focus: {(interviewKit.focus_areas || []).slice(0, 4).join(', ') || 'N/A'}
            </Text>
            <Text style={{ color: muted, fontSize: 10 }}>
              Technical Qs: {(interviewKit.technical_questions || []).slice(0, 2).join(' • ') || 'N/A'}
            </Text>
          </View>
        ) : (
          <Text style={{ color: muted, fontSize: 10, marginTop: 8 }} data-testid="employer-interview-kit-empty" testID="employer-interview-kit-empty">
            Generate an interview kit for the selected candidate.
          </Text>
        )}
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-offer-studio-panel" testID="employer-offer-studio-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-offer-studio-title" testID="employer-offer-studio-title">Offer Builder + Approval Flow</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Build, approve, send offers and track e-sign decisions.</Text>
          </View>
          <Pressable
            onPress={() => void buildOfferDraft()}
            disabled={!!actionLoading || !selectedAppId}
            style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.success, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-offer-build-draft-button"
            testID="employer-offer-build-draft-button"
          >
            <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>{actionLoading === 'build-offer-draft' ? 'Building...' : 'Build Offer Draft'}</Text>
          </Pressable>
        </View>

        <View style={{ marginTop: 10, gap: 8 }}>
          {offers.slice(0, 4).map((offer) => (
            <View key={offer.offer_id} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 9, backgroundColor: cardBg, padding: 8 }} data-testid={`employer-offer-item-${offer.offer_id}`} testID={`employer-offer-item-${offer.offer_id}`}>
              <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }}>
                Offer #{offer.offer_id.slice(-6)} · {String(offer.status || '').toUpperCase()}
              </Text>
              <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>
                ${Number(offer.base_salary_usd || 0).toLocaleString()} · starts {offer.start_date || 'TBD'} · expires {offer.expires_at || 'TBD'}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                <Pressable
                  onPress={() => void submitOfferForApproval(offer.offer_id)}
                  disabled={!!actionLoading}
                  style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 7, backgroundColor: laneBg, paddingHorizontal: 8, paddingVertical: 5 }}
                  data-testid={`employer-offer-submit-approval-${offer.offer_id}`}
                  testID={`employer-offer-submit-approval-${offer.offer_id}`}
                >
                  <Text style={{ color: titleColor, fontSize: 9, fontWeight: '800' }}>{actionLoading === `submit-offer-${offer.offer_id}` ? '...' : 'Submit Approval'}</Text>
                </Pressable>
                <Pressable
                  onPress={() => void approveOffer(offer.offer_id)}
                  disabled={!!actionLoading}
                  style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 8, paddingVertical: 5 }}
                  data-testid={`employer-offer-approve-${offer.offer_id}`}
                  testID={`employer-offer-approve-${offer.offer_id}`}
                >
                  <Text style={{ color: colors.infoText, fontSize: 9, fontWeight: '800' }}>{actionLoading === `approve-offer-${offer.offer_id}` ? '...' : 'Approve'}</Text>
                </Pressable>
                <Pressable
                  onPress={() => void sendOffer(offer.offer_id)}
                  disabled={!!actionLoading}
                  style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55'), borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), paddingHorizontal: 8, paddingVertical: 5 }}
                  data-testid={`employer-offer-send-${offer.offer_id}`}
                  testID={`employer-offer-send-${offer.offer_id}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '800' }}>{actionLoading === `send-offer-${offer.offer_id}` ? '...' : 'Send Offer'}</Text>
                </Pressable>
              </View>
            </View>
          ))}
          {offers.length === 0 ? (
            <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-offer-empty" testID="employer-offer-empty">
              No offers yet for selected candidate. Build a draft to begin approval workflow.
            </Text>
          ) : null}
        </View>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-auto-scheduler-panel" testID="employer-auto-scheduler-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-auto-scheduler-title" testID="employer-auto-scheduler-title">Auto-Scheduling Orchestrator</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Find conflict-free interview slots and book instantly.</Text>
          </View>
          <Pressable
            onPress={() => void loadAutoSchedulerSlots()}
            disabled={!!actionLoading || !selectedAppId}
            style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-auto-scheduler-load-slots-button"
            testID="employer-auto-scheduler-load-slots-button"
          >
            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>
              {actionLoading === 'load-auto-scheduler-slots' ? 'Finding...' : 'Suggest Slots'}
            </Text>
          </Pressable>
        </View>
        <View style={{ marginTop: 10, gap: 8 }}>
          {autoSlots.slice(0, 4).map((slot, idx) => (
            <View key={`${slot.start}-${idx}`} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 9, backgroundColor: cardBg, padding: 8 }} data-testid={`employer-auto-scheduler-slot-${idx}`} testID={`employer-auto-scheduler-slot-${idx}`}>
              <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }}>
                {slot.day_name || 'Day'} · {slot.date} {slot.time} {slot.ai_recommended ? '• AI Top Pick' : ''}
              </Text>
              <Pressable
                onPress={() => void bookAutoSchedulerSlot(slot)}
                disabled={!!actionLoading}
                style={{ marginTop: 6, alignSelf: 'flex-start', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '55'), borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.success, '12'), paddingHorizontal: 9, paddingVertical: 5 }}
                data-testid={`employer-auto-scheduler-book-slot-${idx}`}
                testID={`employer-auto-scheduler-book-slot-${idx}`}
              >
                <Text style={{ color: colors.successText, fontSize: 9, fontWeight: '800' }}>
                  {actionLoading === `book-slot-${slot.start}` ? 'Booking...' : 'Book this slot'}
                </Text>
              </Pressable>
            </View>
          ))}
          {autoSlots.length === 0 ? (
            <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-auto-scheduler-empty" testID="employer-auto-scheduler-empty">
              Load slot suggestions for the selected candidate.
            </Text>
          ) : null}
        </View>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-scorecard-panel" testID="employer-scorecard-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-scorecard-title" testID="employer-scorecard-title">Structured Interview Scorecards</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Capture interviewer ratings and build panel debrief consensus.</Text>
          </View>
          <Pressable
            onPress={() => void submitScorecard()}
            disabled={!!actionLoading || !selectedAppId}
            style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-scorecard-submit-button"
            testID="employer-scorecard-submit-button"
          >
            <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '800' }}>
              {actionLoading === 'submit-scorecard' ? 'Submitting...' : 'Submit Scorecard'}
            </Text>
          </Pressable>
        </View>

        <View style={{ marginTop: 8 }}>
          <Text style={{ color: titleColor, fontSize: 11, fontWeight: '700' }} data-testid="employer-scorecard-summary" testID="employer-scorecard-summary">
            Scorecards: {Number(scorecards?.summary?.count || 0)} · Avg: {Number(scorecards?.summary?.average_overall_score || 0).toFixed(1)} · Latest: {String(scorecards?.summary?.latest_recommendation || 'n/a')}
          </Text>
          <Text style={{ color: muted, fontSize: 10, marginTop: 4 }} data-testid="employer-scorecard-debrief-summary" testID="employer-scorecard-debrief-summary">
            {scorecards?.panel_debrief?.summary || 'No panel debrief yet. Submit first scorecard to start debriefing.'}
          </Text>
        </View>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-communication-sequence-panel" testID="employer-communication-sequence-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-communication-sequence-title" testID="employer-communication-sequence-title">Smart Candidate Communication Sequences</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Automated stage-based check-ins via in-app + email.</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Pressable
              onPress={() => void startCommunicationSequence()}
              disabled={!!actionLoading || !selectedAppId}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-communication-sequence-start-button"
              testID="employer-communication-sequence-start-button"
            >
              <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{actionLoading === 'start-communication-sequence' ? 'Starting...' : 'Start Sequence'}</Text>
            </Pressable>
            <Pressable
              onPress={() => void advanceCommunicationSequence()}
              disabled={!!actionLoading || !selectedAppId || !sequence}
              style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.info, '12'), paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="employer-communication-sequence-advance-button"
              testID="employer-communication-sequence-advance-button"
            >
              <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '800' }}>{actionLoading === 'advance-communication-sequence' ? 'Advancing...' : 'Send Next Step'}</Text>
            </Pressable>
          </View>
        </View>
        <Text style={{ color: muted, fontSize: 10, marginTop: 8 }} data-testid="employer-communication-sequence-status" testID="employer-communication-sequence-status">
          Sequence status: {sequence?.status || 'not started'} · Current step: {typeof sequence?.current_step_index === 'number' ? sequence.current_step_index + 1 : 0}
        </Text>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-hiring-forecast-panel" testID="employer-hiring-forecast-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-hiring-forecast-title" testID="employer-hiring-forecast-title">Hiring Forecast & Bottleneck Prediction</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Predict fill speed and spot risk before SLA breaches escalate.</Text>
          </View>
          <Pressable
            onPress={() => void loadForecast()}
            disabled={!!actionLoading}
            style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: cardBg, paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-hiring-forecast-refresh-button"
            testID="employer-hiring-forecast-refresh-button"
          >
            <Text style={{ color: muted, fontSize: 10, fontWeight: '800' }}>Refresh Forecast</Text>
          </Pressable>
        </View>
        <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800', marginTop: 8 }} data-testid="employer-hiring-forecast-summary" testID="employer-hiring-forecast-summary">
          Fill ETA: {Number(forecast?.forecast?.predicted_days_to_fill || 0).toFixed(1)}d · Next 30d hires: {Number(forecast?.forecast?.predicted_hires_next_30_days || 0)} · Risk: {String(forecast?.forecast?.risk_level || 'n/a').toUpperCase()}
        </Text>
        <Text style={{ color: muted, fontSize: 10, marginTop: 4 }} data-testid="employer-hiring-forecast-recommendation" testID="employer-hiring-forecast-recommendation">
          {(forecast?.recommendations || [])[0] || 'Forecast unavailable. Refresh to compute latest projection.'}
        </Text>
      </View>

      <View style={{ marginTop: 10, borderWidth: 1, borderColor: cardBorder, borderRadius: 12, backgroundColor: laneBg, padding: 12 }} data-testid="employer-rediscovery-panel" testID="employer-rediscovery-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: titleColor, fontSize: 14, fontWeight: '800' }} data-testid="employer-rediscovery-title" testID="employer-rediscovery-title">Talent Rediscovery CRM</Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>Re-activate silver medalists with one-click outreach.</Text>
          </View>
          <Pressable
            onPress={() => void loadRediscovery(selectedApplication?.job_id)}
            disabled={!!actionLoading}
            style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 8, backgroundColor: cardBg, paddingHorizontal: 10, paddingVertical: 6 }}
            data-testid="employer-rediscovery-refresh-button"
            testID="employer-rediscovery-refresh-button"
          >
            <Text style={{ color: muted, fontSize: 10, fontWeight: '800' }}>Refresh Talent Pool</Text>
          </Pressable>
        </View>

        <View style={{ marginTop: 10, gap: 8 }}>
          {rediscoveryCandidates.slice(0, 4).map((candidate) => (
            <View key={candidate.candidate_id} style={{ borderWidth: 1, borderColor: cardBorder, borderRadius: 9, backgroundColor: cardBg, padding: 8 }} data-testid={`employer-rediscovery-item-${candidate.candidate_id}`} testID={`employer-rediscovery-item-${candidate.candidate_id}`}>
              <Text style={{ color: titleColor, fontSize: 11, fontWeight: '800' }}>{candidate.candidate_name} · Match {Number(candidate.match_score || 0)}</Text>
              <Text style={{ color: muted, fontSize: 10, marginTop: 2 }} numberOfLines={2}>{(candidate.match_reasons || [])[0] || 'Strong previous pipeline signal.'}</Text>
              <Pressable
                onPress={() => void reengageRediscoveryCandidate(candidate)}
                disabled={!!actionLoading}
                style={{ marginTop: 6, alignSelf: 'flex-start', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '55'), borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.success, '12'), paddingHorizontal: 9, paddingVertical: 5 }}
                data-testid={`employer-rediscovery-reengage-${candidate.candidate_id}`}
                testID={`employer-rediscovery-reengage-${candidate.candidate_id}`}
              >
                <Text style={{ color: colors.successText, fontSize: 9, fontWeight: '800' }}>
                  {actionLoading === `reengage-${candidate.candidate_id}` ? 'Sending...' : 'Re-engage'}
                </Text>
              </Pressable>
            </View>
          ))}
          {rediscoveryCandidates.length === 0 ? (
            <Text style={{ color: muted, fontSize: 10 }} data-testid="employer-rediscovery-empty" testID="employer-rediscovery-empty">
              No rediscovery candidates found yet. Refresh after more pipeline activity.
            </Text>
          ) : null}
        </View>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
