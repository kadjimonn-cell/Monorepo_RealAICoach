import React, { useMemo, useState, useEffect } from 'react';
import { ScrollView, Text, View } from 'react-native';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { EmployerPortalContent } from './employer-apply';
import api from '../src/services/api';
import { useTranslation } from '../src/hooks/useTranslation';
import { useAuth } from '../src/context/AuthContext';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';

type ApprovalStage = 'submitted' | 'under_review' | 'approved' | 'rejected';

type ApprovalProgress = {
  stage: ApprovalStage;
  statusRaw: string;
  note: string;
  hasApplication: boolean;
  submittedAt?: string;
  updatedAt?: string;
};

function resolveApprovalProgress(application: any, copy: (key: string, fallback: string) => string): ApprovalProgress {
  const statusRaw = String(application?.status || '').toLowerCase();
  const hasApplication = Boolean(application && (application?.employer_id || application?.application_id || application?.status));

  if (statusRaw === 'approved') {
    return {
      stage: 'approved',
      statusRaw,
      hasApplication,
      note: copy('jobsPortal.employer.approvalNoteApproved', 'Approved by admin. Full Employer Portal access is now active.'),
      submittedAt: application?.submitted_at,
      updatedAt: application?.updated_at,
    };
  }

  if (statusRaw === 'rejected') {
    return {
      stage: 'rejected',
      statusRaw,
      hasApplication,
      note: String(application?.rejection_reason || copy('jobsPortal.employer.approvalNoteRejected', 'Your request was rejected. Please update your documents and submit again.')),
      submittedAt: application?.submitted_at,
      updatedAt: application?.updated_at,
    };
  }

  if (['in_review', 'on_hold', 'escalated'].includes(statusRaw)) {
    return {
      stage: 'under_review',
      statusRaw,
      hasApplication,
      note: copy('jobsPortal.employer.approvalNoteUnderReview', 'Your documents are under review by admin.'),
      submittedAt: application?.submitted_at,
      updatedAt: application?.updated_at,
    };
  }

  if (['pending', 'needs_info'].includes(statusRaw)) {
    return {
      stage: 'submitted',
      statusRaw,
      hasApplication,
      note: statusRaw === 'needs_info'
        ? copy('jobsPortal.employer.approvalNoteNeedsInfo', 'Additional information is required. Please update your submission.')
        : copy('jobsPortal.employer.approvalNoteSubmitted', 'Documents submitted. Your request is queued for review.'),
      submittedAt: application?.submitted_at,
      updatedAt: application?.updated_at,
    };
  }

  return {
    stage: 'submitted',
    statusRaw: statusRaw || 'not_submitted',
    hasApplication,
    note: copy('jobsPortal.employer.approvalNoteNotSubmitted', 'No submission found yet. Submit your documents to start approval.'),
    submittedAt: application?.submitted_at,
    updatedAt: application?.updated_at,
  };
}

function ApprovalProgressMiniBar({
  progress,
  colors,
  copy,
}: {
  progress: ApprovalProgress;
  colors: any;
  copy: (key: string, fallback: string) => string;
}) {
  const steps = [
    copy('jobsPortal.employer.stepSubmitted', 'Submitted'),
    copy('jobsPortal.employer.stepUnderReview', 'Under Review'),
    copy('jobsPortal.employer.stepApproved', 'Approved'),
  ];

  const isRejected = progress.stage === 'rejected';
  const submittedDone = progress.hasApplication;
  const submittedActive = !progress.hasApplication || progress.stage === 'submitted';
  const reviewDone = progress.stage === 'approved' || isRejected;
  const reviewActive = progress.stage === 'under_review';
  const approvedDone = progress.stage === 'approved';

  const dotColor = (done: boolean, active: boolean) => {
    if (done) return colors.success;
    if (active) return colors.primary;
    return colors.border;
  };

  const statusTone = progress.stage === 'approved'
    ? (colors.success)
    : progress.stage === 'rejected'
      ? (colors.error)
      : (colors.primary);

  const statusLabel = progress.stage === 'approved'
    ? copy('jobsPortal.employer.statusApproved', 'Approved')
    : progress.stage === 'rejected'
      ? copy('jobsPortal.employer.statusRejected', 'Rejected')
      : progress.stage === 'under_review'
        ? copy('jobsPortal.employer.statusUnderReview', 'Under Review')
        : copy('jobsPortal.employer.statusSubmitted', 'Submitted');

  return (
    <View
      style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}
      data-testid="job-platform-employer-approval-progress"
      testID="job-platform-employer-approval-progress"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="job-platform-employer-approval-progress-title" testID="job-platform-employer-approval-progress-title">
          {copy('jobsPortal.employer.approvalProgressTitle', 'Approval Progress')}
        </Text>
        <View
          style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: statusTone }}
          data-testid="job-platform-employer-approval-status-chip"
          testID="job-platform-employer-approval-status-chip"
        >
          <Text style={{ color: statusTone, fontSize: 11, fontWeight: '800' }} data-testid="job-platform-employer-approval-status-text" testID="job-platform-employer-approval-status-text">
            {statusLabel}
          </Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        {[0, 1, 2].map((idx) => {
          const done = idx === 0 ? submittedDone : idx === 1 ? reviewDone : approvedDone;
          const active = idx === 0 ? submittedActive : idx === 1 ? reviewActive : progress.stage === 'approved';
          return (
            <React.Fragment key={`approval-step-${idx}`}>
              {idx > 0 && (
                <View style={{ flex: 1, height: 2, backgroundColor: idx === 1 ? (submittedDone ? colors.success : colors.border) : (reviewDone ? colors.success : colors.border) }} />
              )}
              <View style={{ alignItems: 'center', minWidth: 84 }}>
                <View
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: 12,
                    backgroundColor: done ? (colors.success) : (active ? (colors.primary) : colors.card),
                    borderWidth: done || active ? 0 : 1,
                    borderColor: dotColor(done, active),
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  data-testid={`job-platform-employer-approval-step-dot-${idx}`}
                  testID={`job-platform-employer-approval-step-dot-${idx}`}
                >
                  <Text style={{ color: done || active ? (colors.primaryText) : colors.textMuted, fontSize: 10, fontWeight: '800' }}>{idx + 1}</Text>
                </View>
                <Text
                  style={{ color: done || active ? colors.text : colors.textMuted, fontSize: 11, marginTop: 5, fontWeight: done || active ? '700' : '500' }}
                  data-testid={`job-platform-employer-approval-step-label-${idx}`}
                  testID={`job-platform-employer-approval-step-label-${idx}`}
                >
                  {steps[idx]}
                </Text>
              </View>
            </React.Fragment>
          );
        })}
      </View>

      <Text style={{ color: progress.stage === 'rejected' ? (colors.error) : colors.textMuted, fontSize: 11, marginTop: 10 }} data-testid="job-platform-employer-approval-note" testID="job-platform-employer-approval-note">
        {progress.note}
      </Text>
    </View>
  );
}

export default function JobPlatformEmployerRoute() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const copy = useMemo(() => (key: string, fallback: string) => {
    const value = tx(key, fallback);
    return value === key ? fallback : value;
  }, [tx]);
  const [explainability, setExplainability] = useState<any[]>([]);
  const [premiumEvents, setPremiumEvents] = useState<any[]>([]);
  const [statusText, setStatusText] = useState('');
  const [permissionGate, setPermissionGate] = useState<{ employerStatus?: string; canViewCandidates?: boolean } | null>(null);
  const [approvalProgress, setApprovalProgress] = useState<ApprovalProgress>(() => ({
    stage: 'submitted',
    statusRaw: 'not_submitted',
    hasApplication: false,
    note: 'No submission found yet. Submit your documents to start approval.',
  }));
  const [pipelineHealth, setPipelineHealth] = useState<any | null>(null);
  const isAdmin = hasAdminConsoleVisibility(user as any);
  const roleBasedEmployer = Boolean(
    (user as any)?.is_employer
    || String(user?.role || '').toLowerCase() === 'employer'
    || String(user?.platform_role || '').toLowerCase() === 'employer'
    || (Array.isArray(user?.roles) && user.roles.some((role) => String(role).toLowerCase() === 'employer'))
  );
  const isApprovedEmployer = Boolean(
    roleBasedEmployer
    || String(permissionGate?.employerStatus || '').toLowerCase() === 'approved'
    || permissionGate?.canViewCandidates
  );

  useEffect(() => {
    if (!user?.user_id) {
      setPermissionGate(null);
      return;
    }
    let cancelled = false;
    const hydratePermissions = async () => {
      try {
        const permRes = await api.get('/employers/my-permissions', { skipDedupe: true });
        if (cancelled) return;
        const permissions = permRes?.data?.permissions || {};
        setPermissionGate({
          employerStatus: String(permissions?.employer_status || '').toLowerCase(),
          canViewCandidates: Boolean(permissions?.can_view_candidates),
        });
      } catch {
        if (!cancelled) setPermissionGate(null);
      }
    };
    void hydratePermissions();
    return () => {
      cancelled = true;
    };
  }, [user?.user_id]);

  useEffect(() => {
    if (!isAdmin && !isApprovedEmployer) {
      setStatusText(copy('jobsPortal.employer.submitDocumentsFirst', 'Submit your documents to request employer approval. Once approved by admin, full employer portal access is unlocked automatically.'));
      setExplainability([]);
      setPremiumEvents([]);
      const loadApproval = async () => {
        try {
          const appRes = await api.get('/employers/my-application', { skipDedupe: true });
          setApprovalProgress(resolveApprovalProgress(appRes?.data?.application, copy));
        } catch {
          setApprovalProgress(resolveApprovalProgress(null, copy));
        }
      };
      void loadApproval();
      return;
    }
    const run = async () => {
      try {
        const [expRes, eventsRes] = await Promise.all([
          api.get('/hiring/v2/employer/shortlist/explainability?limit=8', { skipDedupe: true }),
          api.get('/hiring/v2/employer/premium-analytics/events?lookback_days=30&limit=20', { skipDedupe: true }),
        ]);
        setExplainability(expRes?.data?.items || []);
        setPremiumEvents(eventsRes?.data?.events || []);
        setStatusText(copy('jobsPortal.employer.loadedStatus', `Loaded ${expRes?.data?.total ?? 0} explainability rows and ${eventsRes?.data?.total ?? 0} premium events`));
      } catch (error: any) {
        setStatusText(error?.response?.data?.detail || copy('jobsPortal.employer.premiumRequired', 'Premium explainability and analytics require Premium employer access.'));
      }
    };
    void run();
  }, [copy, isAdmin, isApprovedEmployer]);

  useEffect(() => {
    if (!isAdmin && !isApprovedEmployer) {
      setPipelineHealth(null);
      return;
    }
    let cancelled = false;
    const loadHealth = async () => {
      try {
        const response = await api.get('/hiring/v2/employer/pipeline-health', { skipDedupe: true });
        if (!cancelled) {
          setPipelineHealth(response?.data || null);
        }
      } catch {
        if (!cancelled) {
          setPipelineHealth(null);
        }
      }
    };
    void loadHealth();
    return () => {
      cancelled = true;
    };
  }, [isAdmin, isApprovedEmployer]);

  if (!isAdmin && !isApprovedEmployer) {
    return (
      <AppShell>
        <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="job-platform-employer-onboarding-route" testID="job-platform-employer-onboarding-route">
          <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 36 }}>
            <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', gap: 12 }}>
              <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14 }} data-testid="job-platform-employer-onboarding-banner" testID="job-platform-employer-onboarding-banner">
                <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900' }} data-testid="job-platform-employer-onboarding-title" testID="job-platform-employer-onboarding-title">{copy('jobsPortal.employer.submitDocumentsTitle', 'Submit Documents')}</Text>
                <Text style={{ color: colors.textMuted, marginTop: 6, fontSize: 12 }} data-testid="job-platform-employer-onboarding-subtitle" testID="job-platform-employer-onboarding-subtitle">
                  {copy('jobsPortal.employer.submitDocumentsSubtitle', 'Start your employer approval request. After admin approval, this portal unlocks full hiring management automatically.')}
                </Text>
              </View>

              {!!statusText && (
                <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-employer-onboarding-status" testID="job-platform-employer-onboarding-status">
                  <Text style={{ color: colors.primary, fontSize: 12 }}>{statusText}</Text>
                </View>
              )}

              <ApprovalProgressMiniBar progress={approvalProgress} colors={colors} copy={copy} />

              <EmployerPortalContent routeSource="job-platform-employer" />
            </View>
          </ScrollView>
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="job-platform-employer-route" testID="job-platform-employer-route">
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 36 }}>
          <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', gap: 12 }}>
            <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14 }}>
              <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900' }} data-testid="job-platform-employer-title" testID="job-platform-employer-title">{copy('jobsPortal.employer.workspaceTitle', 'Employer Workspace')}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 6, fontSize: 12 }}>{copy('jobsPortal.employer.workspaceSubtitle', 'Dedicated Feature 26 module for employer pipeline, offers, and hiring operations.')}</Text>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-employer-commercial-panel" testID="job-platform-employer-commercial-panel">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{copy('jobsPortal.employer.premiumTitle', 'Premium recruiter intelligence')}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.employer.premiumSubtitle', 'Explainability + premium analytics help recruiters prioritize high-conversion candidates faster.')}
              </Text>
              {!!statusText && <Text style={{ color: colors.primary, fontSize: 12, marginTop: 8 }} data-testid="job-platform-employer-commercial-status" testID="job-platform-employer-commercial-status">{statusText}</Text>}

              <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="job-platform-employer-pipeline-health" testID="job-platform-employer-pipeline-health">
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{copy('jobsPortal.employer.pipelineHealthTitle', 'Pipeline Health')}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
                  {copy('jobsPortal.employer.pipelineHealthSubtitle', 'Monitor role velocity, bottlenecks, and conversion readiness in one view.')}
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  <View style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, paddingVertical: 6 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.employer.healthScore', 'Health Score')}</Text>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }} data-testid="job-platform-employer-health-score" testID="job-platform-employer-health-score">{pipelineHealth?.pipeline_health_score ?? 0}/100</Text>
                  </View>
                  <View style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, paddingVertical: 6 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.employer.activePipeline', 'Active Pipeline')}</Text>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }} data-testid="job-platform-employer-active-pipeline" testID="job-platform-employer-active-pipeline">{pipelineHealth?.active_pipeline ?? 0}</Text>
                  </View>
                  <View style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, paddingVertical: 6 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.employer.bottlenecks', 'Bottlenecks')}</Text>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }} data-testid="job-platform-employer-bottlenecks" testID="job-platform-employer-bottlenecks">{pipelineHealth?.bottlenecks ?? 0}</Text>
                  </View>
                </View>
              </View>

              <View style={{ marginTop: 10, gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{copy('jobsPortal.employer.shortlistTitle', 'Shortlist Explainability')}</Text>
                {explainability.slice(0, 4).map((row, idx) => (
                  <View key={`${row?.application_id || 'row'}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid={`job-platform-employer-explainability-${idx}`} testID={`job-platform-employer-explainability-${idx}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{row?.candidate_name || copy('jobsPortal.employer.candidateFallback', 'Candidate')}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>Match {row?.match_score ?? 0}% • {(row?.recommendation || 'lean_hire').toUpperCase()}</Text>
                  </View>
                ))}
                {explainability.length === 0 && <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="job-platform-employer-explainability-empty" testID="job-platform-employer-explainability-empty">{copy('jobsPortal.employer.explainabilityEmpty', 'No explainability rows returned.')}</Text>}
              </View>

              <View style={{ marginTop: 10, gap: 6 }}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{copy('jobsPortal.employer.premiumEventsTitle', 'Premium Analytics Events')}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="job-platform-employer-premium-events-count" testID="job-platform-employer-premium-events-count">{copy('jobsPortal.employer.eventsCapturedPrefix', 'Events captured:')} {premiumEvents.length}</Text>
              </View>
            </View>

            <EmployerPortalContent routeSource="job-platform-employer" />
          </View>
        </ScrollView>
      </View>
    </AppShell>
  );
}
