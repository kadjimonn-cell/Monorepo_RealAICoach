import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Platform, TextInput, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTheme } from '../src/context/ThemeContext';
import AppShell from '../src/components/AppShell';
import api from '@/src/services/api';
import { ProfileFormSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { withAlpha } from '../src/utils/colorAlpha';

const ID_TYPES = [
  { value: 'national_id', labelKey: 'idVerification.idType.nationalId', fallback: 'National ID Card' },
  { value: 'passport', labelKey: 'idVerification.idType.passport', fallback: 'Passport' },
  { value: 'drivers_license', labelKey: 'idVerification.idType.driversLicense', fallback: "Driver's License" },
];

type Step = 'form' | 'id_front' | 'id_back' | 'selfie' | 'review' | 'processing';
const stateLabel = (state: string) => String(state || '').replaceAll('_', ' ');

type PageVariant = 'id-verification' | 'id-checker';

type IDVerificationPageProps = {
  routeVariant?: PageVariant;
};

export default function IDVerificationPage({ routeVariant = 'id-verification' }: IDVerificationPageProps) {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const [contentWidth, setContentWidth] = useState(0);
  const idvAccessToken = useMemo(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
    try {
      return new URLSearchParams(window.location.search).get('idv_token') || '';
    } catch {
      return '';
    }
  }, []);

  const withIdvAccess = useCallback((config: any = {}) => {
    const nextConfig = { ...config, params: { ...(config.params || {}) }, headers: { ...(config.headers || {}) } };
    if (idvAccessToken) {
      nextConfig.params.idv_token = idvAccessToken;
      nextConfig.headers['X-IDV-Access-Token'] = idvAccessToken;
    }
    return nextConfig;
  }, [idvAccessToken]);

  const isRiskPlaceholderKyc = useCallback((record: any) => {
    if (!record) return false;
    const hasEngineFlag = Boolean(record.verification_required_by_engine);
    const noDocs = !Array.isArray(record.documents) || record.documents.length === 0;
    const pending = String(record.status || '').toLowerCase() === 'pending_review';
    return hasEngineFlag && pending && noDocs;
  }, []);

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, card: colors.card, cardAlt: colors.bgSoft, text: colors.text,
    muted: colors.textSec, dim: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success, error: colors.error, warn: colors.warning,
    surface: (colors as any).surface || colors.card,
    surfaceElevated: (colors as any).surfaceElevated || colors.card,
    borderStrong: (colors as any).borderStrong || colors.border,
    primaryText: colors.primaryText,
    infoBg: (colors as any).infoBg || colors.bgSoft,
    infoBorder: (colors as any).infoBorder || colors.border,
    infoText: (colors as any).infoText || colors.text,
  }), [colors]);

  const pageHorizontalPadding = width >= 1280 ? 28 : width >= 760 ? 22 : 16;
  const responsiveWidth = contentWidth > 0 ? contentWidth : Math.max(320, width - (pageHorizontalPadding * 2));
  const isMobile = responsiveWidth < 768;
  const isDesktop = responsiveWidth >= 1180;
  const heroRowWrap = responsiveWidth < 720;
  const heroTagWrap = responsiveWidth < 860;
  const heroTitle = routeVariant === 'id-checker'
    ? tx('idChecker.hero.title', 'ID Checker')
    : tx('idVerification.title', 'ID Verification');
  const heroSubtitle = routeVariant === 'id-checker'
    ? tx('idChecker.hero.subtitle', 'Security-grade identity checks with AI triage, human review, and platform-safe audit handling.')
    : tx('idVerification.form.enterpriseSubtitle', 'Security-grade identity verification powered by AI + manual review safeguards.');
  const heroBody = routeVariant === 'id-checker'
    ? tx('idChecker.hero.body', 'Verify your identity to unlock secure platform access. Capture clear identity documents and a selfie so our verification workflow can review your submission safely.')
    : tx('idVerification.form.subtitle', 'Verify your identity to unlock full access to the platform. Our security system uses AI and manual review to analyze your documents safely.');
  const heroIconName = routeVariant === 'id-checker' ? 'shield-checkmark-outline' : 'finger-print';
  const heroBadgeSurface = useMemo(() => withAlpha(C.primary, darkMode ? '22' : '14'), [C.primary, darkMode]);
  const heroBadgeBorder = useMemo(() => withAlpha(C.primary, darkMode ? '4A' : '2A'), [C.primary, darkMode]);
  const sectionSurface = C.surfaceElevated;
  const sectionAltSurface = C.cardAlt;

  const screenContentProps = {
    style: { flex: 1, backgroundColor: C.bg },
    contentContainerStyle: { padding: pageHorizontalPadding, maxWidth: isDesktop ? 1120 : 960, alignSelf: 'center' as const, width: '100%' },
    onLayout: (event: any) => {
      const nextWidth = Math.max(320, Math.round(event?.nativeEvent?.layout?.width || 0));
      setContentWidth((prev) => (prev === nextWidth ? prev : nextWidth));
    },
  };

  const [loading, setLoading] = useState(true);
  const [kyc, setKyc] = useState<any>(null);
  const [statusMeta, setStatusMeta] = useState<any>({ entitlements: null, sla: null, id_checker: null });
  const [step, setStep] = useState<Step>('form');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Form fields
  const [fullName, setFullName] = useState('');
  const [dob, setDob] = useState('');
  const [nationality, setNationality] = useState('');
  const [idType, setIdType] = useState('national_id');
  const [idNumber, setIdNumber] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');

  // Document captures
  const [idFrontFile, setIdFrontFile] = useState<File | null>(null);
  const [idFrontPreview, setIdFrontPreview] = useState<string | null>(null);
  const [idBackFile, setIdBackFile] = useState<File | null>(null);
  const [idBackPreview, setIdBackPreview] = useState<string | null>(null);
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);

  // QR session (desktop)
  const [qrSession, setQrSession] = useState<any>(null);
  const [qrPolling, setQrPolling] = useState(false);
  const [useQR, setUseQR] = useState(false);

  const idTypeLabelMap: Record<string, string> = {
    national_id: tx('idVerification.idType.nationalId', 'National ID Card'),
    passport: tx('idVerification.idType.passport', 'Passport'),
    drivers_license: tx('idVerification.idType.driversLicense', "Driver's License"),
  };

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get('/id-checker/kyc/status', withIdvAccess());
      const data = res.data;
      setKyc(data.kyc);
      setStatusMeta({
        entitlements: data?.entitlements || null,
        sla: data?.sla || null,
        id_checker: data?.id_checker || null,
        experience_summary: data?.experience_summary || null,
      });
      if (data.kyc && isRiskPlaceholderKyc(data.kyc)) {
        // Critical-risk placeholder records should not block the form.
        setStep('form');
      } else if (data.kyc?.full_name) {
        setFullName(data.kyc.full_name);
        setDob(data.kyc.date_of_birth || '');
        setNationality(data.kyc.nationality || '');
        setIdType(data.kyc.id_type || 'national_id');
        setAddress(data.kyc.address || '');
        setPhone(data.kyc.phone || '');
      }
    } catch {
      // User may not have a KYC record yet
    } finally {
      setLoading(false);
    }
  }, [isRiskPlaceholderKyc, withIdvAccess]);

  useEffect(() => { void fetchStatus(); }, [fetchStatus]);

  const submitForm = async () => {
    setError('');
    if (!fullName || !dob || !nationality || !idNumber || !address || !phone) {
      setError(tx('idVerification.errors.allFieldsRequired', 'Please complete every required field before continuing.'));
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post('/id-checker/kyc/submit', {
        full_name: fullName, date_of_birth: dob, nationality,
        id_type: idType, id_number: idNumber, address, phone, level: 1,
      }, withIdvAccess());
      setKyc(res.data.kyc);
      setStep('id_front');
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (detail === 'Authentication required' && !idvAccessToken) {
        setError(tx('idVerification.errors.authRequired', 'Authentication required. Please use the ID Checker link from your security prompt.'));
      } else {
        setError(detail || e.message || tx('idVerification.errors.submissionFailed', 'Unable to submit your verification details right now.'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const capturePhoto = useCallback((type: 'id_front' | 'id_back' | 'selfie') => {
    if (Platform.OS !== 'web') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    if (isMobile) input.setAttribute('capture', type === 'selfie' ? 'user' : 'environment');
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { setError(tx('idVerification.errors.fileTooLarge', 'File too large. Please choose an image smaller than 5 MB.')); return; }
      setError('');
      const url = URL.createObjectURL(file);
      if (type === 'id_front') { setIdFrontFile(file); setIdFrontPreview(url); }
      else if (type === 'id_back') { setIdBackFile(file); setIdBackPreview(url); }
      else { setSelfieFile(file); setSelfiePreview(url); }
    };
    input.click();
  }, [isMobile, tx]);

  const uploadDocument = async (file: File, docType: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', docType);
    const res = await api.post('/id-checker/kyc/upload-file', formData, withIdvAccess({
      headers: { 'Content-Type': 'multipart/form-data' },
    }));
    return res.data;
  };

  const submitDocuments = async () => {
    setError('');
    if (!idFrontFile || !idBackFile || !selfieFile) {
      setError(tx('idVerification.errors.allDocumentsRequired', 'Please capture all required documents: ID front, ID back, and selfie.'));
      setStep('review');
      return;
    }
    setSubmitting(true);
    setStep('processing');
    try {
      if (idFrontFile) await uploadDocument(idFrontFile, 'id_front');
      if (idBackFile) await uploadDocument(idBackFile, 'id_back');
      if (selfieFile) await uploadDocument(selfieFile, 'selfie');

      // Trigger vision analysis
      try {
        await api.post('/id-checker/kyc/vision-analyze', {}, withIdvAccess());
      } catch (ve) {
        console.warn('Vision analysis:', ve);
      }

      await fetchStatus();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || tx('idVerification.errors.uploadFailed', 'Unable to upload your documents right now.'));
      setStep('review');
    } finally {
      setSubmitting(false);
    }
  };

  const createQRSession = async () => {
    try {
      const res = await api.post('/id-checker/qr/create', {}, withIdvAccess());
      setQrSession(res.data);
      setUseQR(true);
      pollQRSession(res.data.session_id);
    } catch {
      setError(tx('idVerification.errors.qrSessionFailed', 'Unable to create a secure QR session right now.'));
    }
  };

  const pollQRSession = (sid: string) => {
    setQrPolling(true);
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/id-checker/qr/status/${sid}`, withIdvAccess());
        if (res.data.status === 'complete') {
          clearInterval(interval);
          setQrPolling(false);
          setUseQR(false);
          await fetchStatus();
        } else if (res.data.status === 'expired') {
          clearInterval(interval);
          setQrPolling(false);
          setQrSession(null);
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'id-verification.qr-poll',
          error,
          message: tx('idVerification.errors.qrPollingFailed', 'Unable to refresh QR session status right now.'),
          setError,
          onRetry: () => { void fetchStatus(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      }
    }, 3000);
    setTimeout(() => { clearInterval(interval); setQrPolling(false); }, 300000);
  };

  const renderStatusBadge = (status: string) => {
    const map: Record<string, { bg: string; fg: string; label: string }> = {
      verified: { bg: withAlpha(C.success, '20'), fg: C.success, label: tx('idVerification.status.verified', 'Verified') },
      rejected: { bg: withAlpha(C.error, '20'), fg: C.error, label: tx('idVerification.status.rejected', 'Rejected') },
      pending_review: { bg: withAlpha(C.warn, '20'), fg: C.warn, label: tx('idVerification.status.underReview', 'Under Review') },
      banned: { bg: withAlpha(C.error, '20'), fg: C.error, label: tx('idVerification.status.banned', 'Banned') },
      APPROVED: { bg: withAlpha(C.success, '20'), fg: C.success, label: tx('idVerification.status.approved', 'Approved') },
      REJECTED: { bg: withAlpha(C.error, '20'), fg: C.error, label: tx('idVerification.status.rejected', 'Rejected') },
      MORE_INFO_REQUIRED: { bg: withAlpha(C.warn, '20'), fg: C.warn, label: tx('idVerification.status.moreInfoRequired', 'More Info Required') },
      ADMIN_REVIEW: { bg: withAlpha(C.warn, '20'), fg: C.warn, label: tx('idVerification.status.underAdminReview', 'Under Admin Review') },
      AI_REVIEW: { bg: withAlpha(C.primary, '20'), fg: C.primary, label: tx('idVerification.status.underAiReview', 'Under AI Review') },
      PENDING: { bg: withAlpha(C.dim, '20'), fg: C.dim, label: tx('idVerification.status.pendingReview', 'Pending Review') },
      NOT_SUBMITTED: { bg: withAlpha(C.dim, '20'), fg: C.dim, label: tx('idVerification.status.notSubmitted', 'Not Submitted') },
    };
    const s = map[status] || { bg: withAlpha(C.dim, '20'), fg: C.dim, label: status };
    return (
      <View style={{ backgroundColor: s.bg, paddingHorizontal: 12, paddingVertical: 4, borderRadius: 20 }}>
        <Text style={{ color: s.fg, fontSize: 12, fontWeight: '700' }}>{s.label}</Text>
      </View>
    );
  };

  if (loading) {
    return (
      <AppShell>
        <ProfileFormSkeleton />
      </AppShell>
    );
  }

  // STATUS DASHBOARD - show when KYC exists with definitive status, excluding risk-triggered placeholders.
  const workflowState = String(
    kyc?.workflow_state
      || (kyc?.status === 'verified' ? 'APPROVED'
        : kyc?.status === 'rejected' || kyc?.status === 'banned' ? 'REJECTED'
          : kyc?.status === 'pending_review' ? 'ADMIN_REVIEW'
            : 'NOT_SUBMITTED')
  ).toUpperCase();

  const hasStatus = !!(
    kyc
    && (
      workflowState !== 'NOT_SUBMITTED'
      && !(workflowState === 'PENDING' && isRiskPlaceholderKyc(kyc))
    )
  );
  const isSystemTriggeredFlow = Boolean(idvAccessToken || kyc?.verification_required_by_engine || kyc?.risk_trigger);
  const naLabel = tx('idChecker.value.notAvailable', 'N/A');
  const workflowStateLabels: Record<string, string> = {
    NOT_SUBMITTED: tx('idVerification.status.notSubmitted', 'Not Submitted'),
    PENDING: tx('idVerification.status.pendingReview', 'Pending Review'),
    AI_REVIEW: tx('idVerification.status.underAiReview', 'Under AI Review'),
    ADMIN_REVIEW: tx('idVerification.status.underAdminReview', 'Under Admin Review'),
    APPROVED: tx('idVerification.status.approved', 'Approved'),
    REJECTED: tx('idVerification.status.rejected', 'Rejected'),
    MORE_INFO_REQUIRED: tx('idVerification.status.moreInfoRequired', 'More Info Required'),
  };
  const workflowStateLabel = (s: string) => workflowStateLabels[String(s || '').toUpperCase()] || stateLabel(s);
  const milestoneStatusLabels: Record<string, string> = {
    completed: tx('idChecker.milestoneStatus.completed', 'Completed'),
    current: tx('idChecker.milestoneStatus.current', 'Current'),
    blocked: tx('idChecker.milestoneStatus.blocked', 'Blocked'),
    skipped: tx('idChecker.milestoneStatus.skipped', 'Skipped'),
    upcoming: tx('idChecker.milestoneStatus.upcoming', 'Upcoming'),
  };
  const milestoneStatusLabel = (s: string) => milestoneStatusLabels[String(s || 'upcoming').toLowerCase()] || milestoneStatusLabels.upcoming;
  const laneLabels: Record<string, string> = {
    fast_lane: tx('idChecker.lane.fast', 'Fast Lane'),
    priority_lane: tx('idChecker.lane.priority', 'Priority Lane'),
    standard_lane: tx('idChecker.lane.standard', 'Standard Lane'),
  };
  const milestoneEtaLabels: Record<string, string> = {
    NOT_SUBMITTED: tx('idChecker.milestoneEta.notSubmitted', 'Awaiting secure submission'),
    PENDING: tx('idChecker.milestoneEta.pending', 'Queued for intake validation'),
    AI_REVIEW: tx('idChecker.milestoneEta.aiReview', 'AI document triage in progress'),
    ADMIN_REVIEW: tx('idChecker.milestoneEta.adminReview', 'Manual reviewer handoff in progress'),
    MORE_INFO_REQUIRED: tx('idChecker.milestoneEta.moreInfoRequired', 'Waiting for customer follow-up'),
    APPROVED: tx('idChecker.milestoneEta.approved', 'Verification completed'),
    REJECTED: tx('idChecker.milestoneEta.rejected', 'Decision completed'),
  };
  const milestoneOwnerLabels: Record<string, string> = {
    NOT_SUBMITTED: tx('idChecker.owner.notSubmitted', 'You'),
    PENDING: tx('idChecker.owner.pending', 'Intake queue'),
    AI_REVIEW: tx('idChecker.owner.aiReview', 'AI review engine'),
    ADMIN_REVIEW: tx('idChecker.owner.adminReview', 'Trust & Safety reviewer'),
    MORE_INFO_REQUIRED: tx('idChecker.owner.moreInfoRequired', 'Customer action required'),
    APPROVED: tx('idChecker.owner.approved', 'Trust & Safety reviewer'),
    REJECTED: tx('idChecker.owner.rejected', 'Trust & Safety reviewer'),
  };
  const milestoneTitle = (m: any) => workflowStateLabels[String(m?.state || '').toUpperCase()] || String(m?.label || '');
  const milestoneEta = (m: any) => milestoneEtaLabels[String(m?.state || '').toUpperCase()] || String(m?.eta_label || '');
  const milestoneOwner = (m: any) => milestoneOwnerLabels[String(m?.state || '').toUpperCase()] || String(m?.owner || '');
  const statusDocCount = Array.isArray(kyc?.documents) ? kyc.documents.length : 0;
  const statusAiConfidence = kyc?.ai_verification?.confidence_score != null
    ? `${Math.round(kyc.ai_verification.confidence_score * 100)}%`
    : naLabel;
  const statusPlan = String(statusMeta?.entitlements?.plan || 'free').toUpperCase();
  const statusLane = laneLabels[String(statusMeta?.entitlements?.service_lane || 'standard_lane')] || String(statusMeta?.entitlements?.service_lane || 'standard_lane').replaceAll('_', ' ');
  const statusSlaDueAt = statusMeta?.sla?.sla_due_at ? String(statusMeta.sla.sla_due_at).substring(0, 19).replace('T', ' ') : naLabel;
  const statusSlaRemaining = statusMeta?.sla?.sla_hours_remaining;
  const experienceSummary = statusMeta?.experience_summary || null;
  const timelineSummary = statusMeta?.id_checker?.timeline || null;
  const timelineMilestones = Array.isArray(timelineSummary?.milestones) ? timelineSummary.milestones : [];
  const timelineEvents = Array.isArray(timelineSummary?.recent_events) ? timelineSummary.recent_events : [];
  const trustReadiness = typeof experienceSummary?.trust_readiness_score === 'number' ? experienceSummary.trust_readiness_score : null;
  const currentEtaMessage = milestoneEtaLabels[workflowState] || String(timelineSummary?.eta_message || tx('idChecker.timeline.etaFallback', 'Verification workflow in progress.'));
  const currentOwnerLabel = milestoneOwnerLabels[workflowState] || String(timelineSummary?.owner_label || tx('idChecker.timeline.ownerFallback', 'Trust workflow'));
  const timelineHandoffLabel = String(timelineSummary?.current_handoff || 'submission-intake').replaceAll('-', ' ').replaceAll('_', ' ').toUpperCase();
  const milestoneTone = (status: string) => {
    if (status === 'completed') return { border: withAlpha(C.success, '36'), bg: withAlpha(C.success, '12'), fg: C.success };
    if (status === 'current') return { border: withAlpha(C.primary, '48'), bg: withAlpha(C.primary, '16'), fg: C.primary };
    if (status === 'blocked') return { border: withAlpha(C.warn, '40'), bg: withAlpha(C.warn, '12'), fg: C.warn };
    if (status === 'skipped') return { border: withAlpha(C.dim, '28'), bg: withAlpha(C.dim, '10'), fg: C.dim };
    return { border: withAlpha(C.borderStrong, '80'), bg: sectionAltSurface, fg: C.muted };
  };
  if (hasStatus && step === 'form') {
    return (
      <AppShell>
        <ScrollView {...screenContentProps}>
          <View data-testid="idv-status-dashboard" testID="idv-status-dashboard" style={{ backgroundColor: sectionSurface, borderRadius: 20, padding: isMobile ? 18 : 24, borderWidth: 1, borderColor: C.borderStrong, marginBottom: 20 }}>
            <View style={{ flexDirection: heroRowWrap ? 'column' : 'row', justifyContent: 'space-between', alignItems: heroRowWrap ? 'flex-start' : 'center', marginBottom: 16, gap: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: isDesktop ? 26 : 22, fontWeight: '800' }}>{heroTitle}</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, lineHeight: 18 }}>{tx('idChecker.status.subtitle', 'Track your verification state, audit signals, and next required actions from one secure workspace.')}</Text>
              </View>
              {renderStatusBadge(workflowState)}
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 }} data-testid="idv-status-kpi-strip" testID="idv-status-kpi-strip">
              {[
                { key: 'workflow', label: tx('idVerification.kpi.workflow', 'Workflow State'), value: workflowStateLabel(workflowState), icon: 'git-network' },
                { key: 'docs', label: tx('idVerification.kpi.documents', 'Documents'), value: String(statusDocCount), icon: 'document-text' },
                { key: 'ai', label: tx('idVerification.kpi.aiConfidence', 'AI Confidence'), value: statusAiConfidence, icon: 'sparkles' },
                { key: 'lane', label: tx('idVerification.kpi.serviceLane', 'Service Lane'), value: statusLane, icon: 'flash' },
              ].map((item) => (
                <View key={item.key} style={{ flex: 1, minWidth: isMobile ? '100%' : 170, backgroundColor: sectionAltSurface, borderRadius: 12, borderWidth: 1, borderColor: C.borderStrong, padding: 10 }} data-testid={`idv-status-kpi-${item.key}`} testID={`idv-status-kpi-${item.key}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={item.icon as any} size={12} color={C.primary} />
                    <Text style={{ color: C.dim, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
                  </View>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
                </View>
              ))}
            </View>

            <View style={{ backgroundColor: sectionAltSurface, borderRadius: 10, borderWidth: 1, borderColor: C.borderStrong, padding: 10, marginBottom: 14 }} data-testid="idv-sla-strip" testID="idv-sla-strip">
              <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>
                {tx('idVerification.kpi.planTier', 'Plan Tier')}: {statusPlan} · {tx('idVerification.kpi.slaDue', 'SLA Due')}: {statusSlaDueAt}
              </Text>
              <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }}>
                {tx('idVerification.kpi.slaRemaining', 'SLA Hours Remaining')}: {statusSlaRemaining == null ? naLabel : statusSlaRemaining}
              </Text>
            </View>

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 16 }}>
              <View style={{ flex: 1.2, backgroundColor: sectionAltSurface, borderRadius: 14, borderWidth: 1, borderColor: C.borderStrong, padding: 14 }} data-testid="id-checker-enterprise-timeline-summary" testID="id-checker-enterprise-timeline-summary">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{tx('idChecker.timeline.title', 'Enterprise Timeline')}</Text>
                <Text style={{ color: C.muted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('idChecker.timeline.subtitle', 'Follow the active review lane, reviewer handoffs, and the most likely next milestone.')}</Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                  <View style={{ backgroundColor: withAlpha(C.primary, '12'), borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: withAlpha(C.primary, '26') }} data-testid="id-checker-current-handoff-chip" testID="id-checker-current-handoff-chip">
                    <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>{tx('idChecker.timeline.currentHandoff', 'Current Handoff')}: {timelineHandoffLabel}</Text>
                  </View>
                  <View style={{ backgroundColor: withAlpha(C.success, '12'), borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: withAlpha(C.success, '26') }} data-testid="id-checker-trust-readiness-chip" testID="id-checker-trust-readiness-chip">
                    <Text style={{ color: C.success, fontSize: 10, fontWeight: '800' }}>{tx('idChecker.timeline.trustReadiness', 'Trust Readiness')}: {trustReadiness == null ? naLabel : `${trustReadiness}%`}</Text>
                  </View>
                </View>

                <View style={{ marginTop: 14, borderRadius: 12, padding: 12, backgroundColor: withAlpha(C.primary, '10'), borderWidth: 1, borderColor: withAlpha(C.primary, '20') }} data-testid="id-checker-eta-card" testID="id-checker-eta-card">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('idChecker.timeline.etaTitle', 'ETA & Review Ownership')}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{currentEtaMessage}</Text>
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', marginTop: 8 }}>{tx('idChecker.timeline.owner', 'Current Owner')}: {currentOwnerLabel}</Text>
                </View>

                {Array.isArray(experienceSummary?.nudges) && experienceSummary.nudges.length > 0 ? (
                  <View style={{ marginTop: 14, gap: 8 }} data-testid="id-checker-next-actions" testID="id-checker-next-actions">
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('idChecker.timeline.nextActions', 'Next Actions')}</Text>
                    {experienceSummary.nudges.slice(0, 3).map((nudge: string, idx: number) => (
                      <View key={`${nudge}-${idx}`} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }}>
                        <Ionicons name="arrow-forward-circle" size={14} color={C.primary} style={{ marginTop: 2 }} />
                        <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, flex: 1 }}>{nudge}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>

              <View style={{ flex: 1, backgroundColor: sectionAltSurface, borderRadius: 14, borderWidth: 1, borderColor: C.borderStrong, padding: 14 }} data-testid="id-checker-recent-review-events" testID="id-checker-recent-review-events">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{tx('idChecker.timeline.recentEvents', 'Recent Review Events')}</Text>
                <Text style={{ color: C.muted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('idChecker.timeline.recentEventsSubtitle', 'Most recent status changes and reviewer handoffs in your verification trail.')}</Text>
                <View style={{ marginTop: 12, gap: 10 }}>
                  {timelineEvents.length > 0 ? timelineEvents.map((event: any, idx: number) => (
                    <View key={event.event_id || `${event.to_state}-${idx}`} style={{ flexDirection: 'row', gap: 10 }} data-testid={`id-checker-timeline-event-${idx}`} testID={`id-checker-timeline-event-${idx}`}>
                      <View style={{ width: 28, alignItems: 'center' }}>
                        <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: idx === 0 ? C.primary : withAlpha(C.primary, '45'), marginTop: 4 }} />
                        {idx !== timelineEvents.length - 1 ? <View style={{ width: 2, flex: 1, backgroundColor: withAlpha(C.borderStrong, '66'), marginTop: 4 }} /> : null}
                      </View>
                      <View style={{ flex: 1, paddingBottom: idx !== timelineEvents.length - 1 ? 6 : 0 }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{workflowStateLabels[String(event.to_state || '').toUpperCase()] || event.label}</Text>
                        <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', marginTop: 2 }}>{event.actor}</Text>
                        <Text style={{ color: C.textSec, fontSize: 11, lineHeight: 17, marginTop: 3 }}>{event.reason}</Text>
                        <Text style={{ color: C.dim, fontSize: 10, marginTop: 4 }}>{event.created_at ? String(event.created_at).substring(0, 19).replace('T', ' ') : tx('idChecker.timeline.justNow', 'Just now')}</Text>
                      </View>
                    </View>
                  )) : (
                    <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.borderStrong, backgroundColor: withAlpha(C.primary, '08'), padding: 12 }}>
                      <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18 }}>{tx('idChecker.timeline.noRecentEvents', 'No transition events yet. Your first secure submission will start the review timeline.')}</Text>
                    </View>
                  )}
                </View>
              </View>
            </View>

            <View style={{ marginBottom: 14 }} data-testid="id-checker-milestone-timeline" testID="id-checker-milestone-timeline">
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('idChecker.timeline.milestones', 'Milestones')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                {timelineMilestones.map((milestone: any, idx: number) => {
                  const tone = milestoneTone(String(milestone.status || 'upcoming'));
                  return (
                    <View key={milestone.state || idx} style={{ flex: 1, minWidth: isMobile ? '100%' : 220, borderRadius: 14, borderWidth: 1, borderColor: tone.border, backgroundColor: tone.bg, padding: 12 }} data-testid={`id-checker-milestone-${String(milestone.state || idx).toLowerCase()}`} testID={`id-checker-milestone-${String(milestone.state || idx).toLowerCase()}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <Text style={{ color: tone.fg, fontSize: 11, fontWeight: '800' }}>{milestoneStatusLabel(String(milestone.status || 'upcoming'))}</Text>
                        <Text style={{ color: C.dim, fontSize: 10, fontWeight: '700' }}>#{idx + 1}</Text>
                      </View>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginTop: 8 }}>{milestoneTitle(milestone)}</Text>
                      <Text style={{ color: C.textSec, fontSize: 11, lineHeight: 17, marginTop: 6 }}>{milestoneEta(milestone)}</Text>
                      <Text style={{ color: tone.fg, fontSize: 10, fontWeight: '700', marginTop: 8 }}>{tx('idChecker.timeline.owner', 'Current Owner')}: {milestoneOwner(milestone)}</Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }} data-testid="id-checker-workflow-stages" testID="id-checker-workflow-stages">
              {[
                'NOT_SUBMITTED',
                'PENDING',
                'AI_REVIEW',
                'ADMIN_REVIEW',
                'APPROVED',
                'REJECTED',
                'MORE_INFO_REQUIRED',
              ].map((s) => {
                const active = workflowState === s;
                return (
                  <View key={s} style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: active ? C.primary : C.borderStrong, backgroundColor: active ? withAlpha(C.primary, '18') : sectionAltSurface }}>
                    <Text style={{ color: active ? C.primary : C.muted, fontSize: 10, fontWeight: '700' }}>{workflowStateLabel(s)}</Text>
                  </View>
                );
              })}
            </View>

            {(kyc.status === 'verified' || workflowState === 'APPROVED') && (
              <View style={{ backgroundColor: withAlpha(C.success, '10'), borderRadius: 12, padding: 16, gap: 8, borderWidth: 1, borderColor: withAlpha(C.success, '24') }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons name="shield-checkmark" size={28} color={C.successText} />
                  <View>
                    <Text style={{ color: C.successText, fontSize: 16, fontWeight: '700' }}>{tx('idVerification.verified.title', 'Verification completed')}</Text>
                    <Text style={{ color: C.muted, fontSize: 12 }}>{tx('idVerification.verified.on', 'Verified on')} {kyc.verified_at?.substring(0, 10)}</Text>
                  </View>
                </View>
                {kyc.tier && <Text style={{ color: C.muted, fontSize: 12 }}>{tx('idVerification.status.tier', 'Tier')}: {kyc.tier}</Text>}
                {kyc.verification_method && <Text style={{ color: C.dim, fontSize: 11 }}>{tx('idVerification.status.method', 'Method')}: {kyc.verification_method}</Text>}
              </View>
            )}

            {(kyc.status === 'rejected' || kyc.status === 'banned' || workflowState === 'REJECTED') && (
              <View style={{ backgroundColor: withAlpha(C.error, '10'), borderRadius: 12, padding: 16, gap: 8, borderWidth: 1, borderColor: withAlpha(C.error, '24') }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons name="close-circle" size={28} color={C.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.error, fontSize: 16, fontWeight: '700' }}>{tx('idVerification.rejected.title', 'Verification requires attention')}</Text>
                    {kyc.rejection_reason && <Text style={{ color: C.muted, fontSize: 12 }}>{kyc.rejection_reason}</Text>}
                  </View>
                </View>
                {kyc.retry_available_date && (
                  <Text style={{ color: C.warn, fontSize: 12 }}>{tx('idVerification.status.retryAvailable', 'Retry available')}: {kyc.retry_available_date.substring(0, 10)}</Text>
                )}
                <TouchableOpacity data-testid="idv-retry-btn" testID="idv-retry-btn" onPress={() => { setKyc(null); setStep('form'); }}
                  style={{ backgroundColor: C.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center', marginTop: 8 }}>
                  <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{tx('idVerification.actions.startNewVerification', 'Start New Verification')}</Text>
                </TouchableOpacity>
              </View>
            )}

            {(kyc.status === 'pending_review' || ['PENDING', 'AI_REVIEW', 'ADMIN_REVIEW', 'MORE_INFO_REQUIRED'].includes(workflowState)) && (
              <View style={{ backgroundColor: withAlpha(C.warn, '10'), borderRadius: 12, padding: 16, gap: 8, borderWidth: 1, borderColor: withAlpha(C.warn, '24') }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons name="time" size={28} color={C.warn} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.warn, fontSize: 16, fontWeight: '700' }}>{workflowStateLabel(workflowState)}</Text>
                    <Text style={{ color: C.muted, fontSize: 12 }}>{tx('idVerification.underReview.subtitle', 'Your submission is in the secure verification workflow. We will notify you when review is complete.')}</Text>
                  </View>
                </View>
                {kyc.combined_score != null && (
                  <Text style={{ color: C.dim, fontSize: 11 }}>{tx('idVerification.status.aiConfidence', 'AI confidence')}: {Math.round(kyc.combined_score * 100)}%</Text>
                )}
              </View>
            )}
          </View>

          {/* Submission Details */}
          <View style={{ backgroundColor: sectionSurface, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: C.borderStrong, marginBottom: 20 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 14 }}>{tx('idVerification.sections.submissionDetails', 'Submission Details')}</Text>
            {[
              [tx('idVerification.review.fullName', 'Full Name'), kyc.full_name],
              [tx('idVerification.review.dateOfBirth', 'Date of Birth'), kyc.date_of_birth],
              [tx('idVerification.review.nationality', 'Nationality'), kyc.nationality],
              [tx('idVerification.review.idType', 'ID Type'), (idTypeLabelMap[kyc.id_type] || kyc.id_type)],
              [tx('idVerification.review.phone', 'Phone'), kyc.phone],
              [tx('idVerification.review.address', 'Address'), kyc.address],
              [tx('idVerification.review.submitted', 'Submitted'), kyc.submitted_at?.substring(0, 19)?.replace('T', ' ')],
            ].map(([label, val]) => (
              <View key={label} style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 4, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: withAlpha(C.borderStrong, '40') }}>
                <Text style={{ color: C.muted, fontSize: 13 }}>{label}</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', maxWidth: isMobile ? '100%' : '60%', textAlign: isMobile ? 'left' : 'right' }}>{val || '-'}</Text>
              </View>
            ))}
          </View>

          {/* Documents */}
          <View style={{ backgroundColor: sectionSurface, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: C.borderStrong, marginBottom: 20 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 14 }}>{tx('idVerification.sections.documents', 'Documents')}</Text>
            {(kyc.documents || []).length === 0 ? (
              <Text style={{ color: C.dim, fontSize: 13 }}>{tx('idVerification.documents.empty', 'No documents uploaded yet.')}</Text>
            ) : (
              (kyc.documents || []).map((doc: any) => (
                <View key={doc.doc_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: withAlpha(C.borderStrong, '40') }}>
                  <Ionicons name={doc.type === 'selfie' ? 'person-circle' : 'document'} size={20} color={C.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{doc.type === 'id_front' ? tx('idVerification.documents.idFront', 'ID Front') : doc.type === 'id_back' ? tx('idVerification.documents.idBack', 'ID Back') : tx('idVerification.documents.selfie', 'Selfie')}</Text>
                    <Text style={{ color: C.dim, fontSize: 11 }}>{doc.uploaded_at?.substring(0, 19)?.replace('T', ' ')}</Text>
                  </View>
                  {doc.file_size && <Text style={{ color: C.dim, fontSize: 11 }}>{Math.round(doc.file_size / 1024)}KB</Text>}
                </View>
              ))
            )}
          </View>

          {/* AI Analysis Results */}
          {(kyc.ai_verification || kyc.vision_analysis) && (
            <View style={{ backgroundColor: sectionSurface, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: C.borderStrong, marginBottom: 20 }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 14 }}>{tx('idVerification.sections.aiAnalysis', 'AI Analysis')}</Text>
              {kyc.ai_verification?.confidence_score != null && (
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 }}>
                  <Text style={{ color: C.muted, fontSize: 13 }}>{tx('idVerification.ai.confidenceScore', 'Confidence Score')}</Text>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{Math.round(kyc.ai_verification.confidence_score * 100)}%</Text>
                </View>
              )}
              {kyc.ai_verification?.risk_level && (
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 }}>
                  <Text style={{ color: C.muted, fontSize: 13 }}>{tx('idVerification.ai.riskLevel', 'Risk Level')}</Text>
                  <Text style={{ color: kyc.ai_verification.risk_level === 'low' ? C.success : kyc.ai_verification.risk_level === 'high' ? C.error : C.warn, fontSize: 13, fontWeight: '700' }}>
                    {kyc.ai_verification.risk_level.toUpperCase()}
                  </Text>
                </View>
              )}
              {kyc.ai_verification?.checks?.length > 0 && (
                <View style={{ marginTop: 10, gap: 4 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.ai.checks', 'Checks')}</Text>
                  {kyc.ai_verification.checks.map((check: any, i: number) => (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 3 }}>
                      <Ionicons name={check.passed ? 'checkmark-circle' : 'close-circle'} size={14} color={check.passed ? C.success : C.error} />
                      <Text style={{ color: C.muted, fontSize: 12, flex: 1 }}>{check.detail || check.check}</Text>
                    </View>
                  ))}
                </View>
              )}
              {kyc.vision_analysis?.document_results && (
                <View style={{ marginTop: 12, gap: 6 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{tx('idVerification.ai.documentVision', 'Document Vision Analysis')}</Text>
                  {Object.entries(kyc.vision_analysis.document_results).map(([dtype, res]: [string, any]) => (
                    <View key={dtype} style={{ backgroundColor: sectionAltSurface, borderRadius: 8, padding: 10, marginTop: 4, borderWidth: 1, borderColor: C.borderStrong }}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{dtype === 'id_front' ? tx('idVerification.review.idFront', 'ID Front') : dtype === 'id_back' ? tx('idVerification.review.idBack', 'ID Back') : tx('idVerification.review.selfie', 'Selfie')}</Text>
                      <Text style={{ color: C.dim, fontSize: 11 }}>{res.summary || tx('idVerification.review.analyzed', 'Analyzed')}</Text>
                      {res.confidence != null && <Text style={{ color: C.muted, fontSize: 11 }}>{tx('idVerification.ai.confidence', 'Confidence')}: {Math.round(res.confidence * 100)}%</Text>}
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}
        </ScrollView>
      </AppShell>
    );
  }

  // PROCESSING state
  if (step === 'processing') {
    return (
      <AppShell>
        <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
          <View style={{ width: 80, height: 80, borderRadius: 40, backgroundColor: withAlpha(C.primary, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
            <ActivityIndicator size="large" color={C.primary} />
          </View>
          <Text data-testid="idv-processing-title" testID="idv-processing-title" style={{ color: C.text, fontSize: 20, fontWeight: '800', marginBottom: 8 }}>{tx('idVerification.processing.title', 'Processing your verification')}</Text>
          <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', maxWidth: 320 }}>
            {tx('idVerification.processing.subtitle', 'Please wait while we review your uploaded identity evidence and generate verification signals.')}
          </Text>
        </View>
      </AppShell>
    );
  }

  // MULTI-STEP CAPTURE FLOW
  const stepConfig: Record<string, { title: string; desc: string; icon: string; capture: 'id_front' | 'id_back' | 'selfie'; preview: string | null; next: Step }> = {
    id_front: { title: tx('idVerification.steps.idFront.title', 'Capture ID Front'), desc: tx('idVerification.steps.idFront.desc', 'Upload or capture the front of your identity document in a clear frame.'), icon: 'card', capture: 'id_front', preview: idFrontPreview, next: 'id_back' },
    id_back: { title: tx('idVerification.steps.idBack.title', 'Capture ID Back'), desc: tx('idVerification.steps.idBack.desc', 'Upload or capture the reverse side of the same identity document.'), icon: 'card-outline', capture: 'id_back', preview: idBackPreview, next: 'selfie' },
    selfie: { title: tx('idVerification.steps.selfie.title', 'Capture Selfie'), desc: tx('idVerification.steps.selfie.desc', 'Capture a clear selfie so the review engine can compare your face against the submitted ID.'), icon: 'person-circle', capture: 'selfie', preview: selfiePreview, next: 'review' },
  };

  if (step === 'id_front' || step === 'id_back' || step === 'selfie') {
    const cfg = stepConfig[step];
    const stepNum = step === 'id_front' ? 1 : step === 'id_back' ? 2 : 3;
    return (
      <AppShell>
        <ScrollView {...screenContentProps} contentContainerStyle={{ ...screenContentProps.contentContainerStyle, maxWidth: 720 }}>
          {/* Progress bar */}
          <View style={{ flexDirection: 'row', gap: 6, marginBottom: 24, justifyContent: 'center' }}>
            {[1, 2, 3].map(n => (
              <View key={n} style={{ height: 4, flex: 1, borderRadius: 2, backgroundColor: n <= stepNum ? C.primary : C.border, maxWidth: 80 }} />
            ))}
          </View>

          <View style={{ alignItems: 'center', marginBottom: 24 }}>
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: withAlpha(C.primary, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
              <Ionicons name={cfg.icon as any} size={28} color={C.primary} />
            </View>
            <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }} data-testid={`idv-step-title-${step}`} testID={`idv-step-title-${step}`}>
              {tx('idVerification.steps.stepPrefix', 'Step {num}').replace('{num}', String(stepNum))}: {cfg.title}
            </Text>
            <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', marginTop: 4 }}>{cfg.desc}</Text>
          </View>

          {/* Capture zone */}
          <TouchableOpacity data-testid={`idv-capture-${step}`} testID={`idv-capture-${step}`} onPress={() => capturePhoto(cfg.capture)}
            style={{
              width: '100%', aspectRatio: 1.6, borderRadius: 16, borderWidth: 2,
              borderColor: withAlpha(cfg.preview ? C.success : C.primary, '50'), borderStyle: cfg.preview ? 'solid' : 'dashed',
              backgroundColor: cfg.preview ? sectionSurface : sectionAltSurface,
              alignItems: 'center', justifyContent: 'center', overflow: 'hidden', marginBottom: 20,
            }}>
            {cfg.preview ? (
              Platform.OS === 'web' ? <img src={cfg.preview} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null
            ) : (
              <View style={{ alignItems: 'center', gap: 8 }}>
                <Ionicons name="camera" size={40} color={C.primary} />
                <Text style={{ color: C.primary, fontSize: 14, fontWeight: '600' }}>{tx('idVerification.capture.tapTo', 'Tap to {action}').replace('{action}', isMobile ? tx('idVerification.capture.capture', 'capture') : tx('idVerification.capture.selectFile', 'select a file'))}</Text>
              </View>
            )}
          </TouchableOpacity>

          {cfg.preview && (
            <TouchableOpacity data-testid={`idv-retake-${step}`} testID={`idv-retake-${step}`} onPress={() => capturePhoto(cfg.capture)} style={{ alignSelf: 'center', marginBottom: 16 }}>
              <Text style={{ color: C.primary, fontSize: 13, fontWeight: '600' }}>{tx('idVerification.capture.retake', 'Retake')}</Text>
            </TouchableOpacity>
          )}

          {/* Desktop QR option */}
          {!isMobile && step === 'id_front' && !useQR && (
            <TouchableOpacity data-testid="idv-use-qr-btn" testID="idv-use-qr-btn" onPress={createQRSession}
              style={{ backgroundColor: sectionAltSurface, borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: C.borderStrong, marginBottom: 16 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="qr-code" size={18} color={C.primary} />
                <Text style={{ color: C.primary, fontSize: 13, fontWeight: '600' }}>{tx('idVerification.qr.usePhone', 'Use your phone instead')}</Text>
              </View>
            </TouchableOpacity>
          )}

          {/* QR Code */}
          {useQR && qrSession && (
            <View style={{ backgroundColor: sectionSurface, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.borderStrong, alignItems: 'center', marginBottom: 16 }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('idVerification.qr.scanTitle', 'Scan with your mobile camera')}</Text>
              <View data-testid="idv-qr-code" testID="idv-qr-code" style={{ width: 200, height: 200, backgroundColor: colors.primaryText, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                {Platform.OS === 'web' && (
                  <img
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(
                      `${(`https://${window.location.host}`)}/id-verify-mobile?sid=${qrSession.session_id}&token=${qrSession.token}`
                    )}`}
                    style={{ width: 180, height: 180 }}
                    alt="QR Code"
                  />
                )}
              </View>
              {qrPolling && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <ActivityIndicator size="small" color={C.primary} />
                  <Text style={{ color: C.muted, fontSize: 12 }}>{tx('idVerification.qr.waiting', 'Waiting for secure mobile upload')}</Text>
                </View>
              )}
              <TouchableOpacity data-testid="idv-qr-cancel-btn" testID="idv-qr-cancel-btn" onPress={() => { setUseQR(false); setQrSession(null); }} style={{ marginTop: 10 }}>
                <Text style={{ color: C.dim, fontSize: 12 }}>{tx('idVerification.qr.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
            </View>
          )}

          {error ? <Text style={{ color: C.error, fontSize: 12, textAlign: 'center', marginBottom: 10 }}>{error}</Text> : null}

          <View style={{ flexDirection: 'row', gap: 12, marginTop: 8 }}>
            <TouchableOpacity data-testid="idv-step-back" testID="idv-step-back" onPress={() => setStep(step === 'id_front' ? 'form' : step === 'id_back' ? 'id_front' : 'id_back')}
              style={{ flex: 1, backgroundColor: C.cardAlt, borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontWeight: '600', fontSize: 14 }}>{tx('common.back', 'Back')}</Text>
            </TouchableOpacity>
            <TouchableOpacity data-testid="idv-step-next" testID="idv-step-next" onPress={() => cfg.preview ? setStep(cfg.next) : capturePhoto(cfg.capture)}
              style={{ flex: 2, backgroundColor: withAlpha(C.primary, 'D9'), borderRadius: 12, paddingVertical: 14, alignItems: 'center' }}>
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{cfg.preview ? tx('common.continue', 'Continue') : tx('idVerification.capture.capturePhoto', 'Capture photo')}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </AppShell>
    );
  }

  // REVIEW step
  if (step === 'review') {
    const docs = [
      { type: 'ID Front', preview: idFrontPreview, file: idFrontFile },
      { type: 'ID Back', preview: idBackPreview, file: idBackFile },
      { type: 'Selfie', preview: selfiePreview, file: selfieFile },
    ];
    return (
      <AppShell>
        <ScrollView {...screenContentProps} contentContainerStyle={{ ...screenContentProps.contentContainerStyle, maxWidth: 720 }}>
          <Text data-testid="idv-review-title" testID="idv-review-title" style={{ color: C.text, fontSize: 22, fontWeight: '800', marginBottom: 4 }}>{tx('idVerification.review.title', 'Review your identity package')}</Text>
          <Text style={{ color: C.muted, fontSize: 13, marginBottom: 20 }}>{tx('idVerification.review.subtitle', 'Confirm that each required image is present and readable before secure submission.')}</Text>

          {docs.map((doc) => (
            <View key={doc.type} style={{ backgroundColor: sectionSurface, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.borderStrong, marginBottom: 12, flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: 14 }}>
              {doc.preview ? (
                <View style={{ width: 64, height: 48, borderRadius: 8, overflow: 'hidden' }}>
                  {Platform.OS === 'web' && <img src={doc.preview} style={{ width: 64, height: 48, objectFit: 'cover', borderRadius: 8 }} />}
                </View>
              ) : (
                <View style={{ width: 64, height: 48, borderRadius: 8, backgroundColor: sectionAltSurface, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="alert-circle" size={20} color={C.warn} />
                </View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>{doc.type === 'ID Front' ? tx('idVerification.review.idFront', 'ID Front') : doc.type === 'ID Back' ? tx('idVerification.review.idBack', 'ID Back') : tx('idVerification.review.selfie', 'Selfie')}</Text>
                <Text style={{ color: doc.preview ? C.success : C.warn, fontSize: 11 }}>
                  {doc.preview ? `${tx('idVerification.review.ready', 'Ready')} (${doc.file ? Math.round(doc.file.size / 1024) + 'KB' : ''})` : tx('idVerification.review.notCaptured', 'Not captured yet')}
                </Text>
              </View>
              <Ionicons name={doc.preview ? 'checkmark-circle' : 'alert-circle'} size={22} color={doc.preview ? C.success : C.warn} />
            </View>
          ))}

          {error ? <Text style={{ color: C.error, fontSize: 12, textAlign: 'center', marginVertical: 10 }}>{error}</Text> : null}

          <View style={{ flexDirection: 'row', gap: 12, marginTop: 16 }}>
            <TouchableOpacity data-testid="idv-review-back" testID="idv-review-back" onPress={() => setStep('selfie')}
              style={{ flex: 1, backgroundColor: C.cardAlt, borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontWeight: '600', fontSize: 14 }}>{tx('common.back', 'Back')}</Text>
            </TouchableOpacity>
            <TouchableOpacity data-testid="idv-submit-docs" testID="idv-submit-docs" onPress={submitDocuments} disabled={submitting || (!idFrontFile || !idBackFile || !selfieFile)}
              style={{ flex: 2, backgroundColor: C.primary, borderRadius: 12, paddingVertical: 14, alignItems: 'center', opacity: submitting ? 0.6 : 1 }}>
              {submitting ? <ActivityIndicator color={colors.primaryText} /> : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="shield-checkmark" size={18} color={colors.primaryText} />
                  <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{tx('idVerification.actions.submitForAi', 'Submit for secure review')}</Text>
                </View>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </AppShell>
    );
  }

  // FORM step (default)
  return (
    <AppShell>
      <View style={{ flex: 1 }} data-testid="id-verification-screen" testID="id-verification-screen">
        <ScrollView {...screenContentProps}>
        {!isSystemTriggeredFlow && (
          <View
            style={{
              backgroundColor: C.infoBg,
              borderWidth: 1,
              borderColor: C.infoBorder,
              borderRadius: 12,
              padding: 14,
              marginBottom: 16,
            }}
            data-testid="idv-normal-user-notice"
            testID="idv-normal-user-notice"
          >
            <Text style={{ color: C.infoText, fontSize: 13, lineHeight: 20, fontWeight: '700', marginBottom: 4 }}>
              {tx('idVerification.notice.title', 'Security-triggered verification notice')}
            </Text>
            <Text style={{ color: C.infoText, fontSize: 12, lineHeight: 18 }}>
              {tx('idVerification.notice.body', 'This ID verification page is primarily used when our security system auto-detects elevated risk and requests additional verification. If you were not directed here by a security prompt, no action is required and you may safely return to your dashboard.')}
            </Text>
            <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <TouchableOpacity
                onPress={() => router.push('/dashboard')}
                style={{
                  alignSelf: 'flex-start',
                  backgroundColor: C.primary,
                  borderRadius: 999,
                  paddingHorizontal: 14,
                  paddingVertical: 8,
                }}
                data-testid="idv-notice-back-dashboard"
                testID="idv-notice-back-dashboard"
              >
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>
                  {tx('idVerification.notice.backToDashboard', 'Back to Dashboard')}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => router.push('/auth/login?source=security-prompt' as any)}
                style={{
                  alignSelf: 'flex-start',
                  backgroundColor: 'transparent',
                  borderRadius: 999,
                  paddingHorizontal: 14,
                  paddingVertical: 8,
                  borderWidth: 1.5,
                  borderColor: C.primary,
                }}
                data-testid="idv-notice-return-security-prompt"
                testID="idv-notice-return-security-prompt"
              >
                <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>
                  {tx('idVerification.notice.returnToSecurityPrompt', 'Return to Security Prompt')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
        <View style={{ alignItems: 'center', marginBottom: 24 }} data-testid="idv-form-hero" testID="idv-form-hero">
          <View style={{ width: '100%', backgroundColor: sectionSurface, borderRadius: 20, borderWidth: 1, borderColor: C.borderStrong, padding: isMobile ? 16 : 20, marginBottom: 16 }}>
            <View style={{ flexDirection: heroRowWrap ? 'column' : 'row', alignItems: heroRowWrap ? 'flex-start' : 'center', gap: 12, marginBottom: 8 }}>
              <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: heroBadgeSurface, borderWidth: 1, borderColor: heroBadgeBorder, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={heroIconName as any} size={24} color={C.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: isDesktop ? 24 : 20, fontWeight: '800' }} data-testid="idv-form-title" testID="idv-form-title">{heroTitle}</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>
                  {heroSubtitle}
                </Text>
              </View>
            </View>

            <View style={{ flexDirection: heroTagWrap ? 'row' : 'row', flexWrap: 'wrap', gap: 8 }} data-testid="idv-form-hero-tags" testID="idv-form-hero-tags">
              {[
                tx('idChecker.heroTag.dataOnly', 'Platform Data Only'),
                tx('idChecker.heroTag.endToEnd', 'End-to-End Reviewable'),
                tx('idChecker.heroTag.secure', 'Enterprise Security Controls'),
              ].map((tag, idx) => (
                <View key={`${tag}_${idx}`} style={{ backgroundColor: sectionAltSurface, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.borderStrong }} data-testid={`idv-form-hero-tag-${idx}`} testID={`idv-form-hero-tag-${idx}`}>
                  <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tag}</Text>
                </View>
              ))}
            </View>
          </View>
          <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', marginTop: 4, maxWidth: 520 }}>
            {heroBody}
          </Text>
        </View>

        {timelineMilestones.length > 0 && (
          <View style={{ backgroundColor: sectionSurface, borderRadius: 18, borderWidth: 1, borderColor: C.borderStrong, padding: isMobile ? 16 : 20, marginBottom: 20 }} data-testid="id-checker-preview-timeline" testID="id-checker-preview-timeline">
            <View style={{ flexDirection: heroRowWrap ? 'column' : 'row', alignItems: heroRowWrap ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{tx('idChecker.timeline.title', 'Enterprise Timeline')}</Text>
                <Text style={{ color: C.muted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('idChecker.preview.subtitle', "Here's how your verification will progress once you submit — every stage is reviewable end to end.")}</Text>
              </View>
              {renderStatusBadge(workflowState)}
            </View>

            <View style={{ marginTop: 14, borderRadius: 12, padding: 12, backgroundColor: withAlpha(C.primary, '10'), borderWidth: 1, borderColor: withAlpha(C.primary, '20') }} data-testid="id-checker-preview-eta-card" testID="id-checker-preview-eta-card">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('idChecker.timeline.etaTitle', 'ETA & Review Ownership')}</Text>
              <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{currentEtaMessage}</Text>
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', marginTop: 8 }}>{tx('idChecker.timeline.owner', 'Current Owner')}: {currentOwnerLabel}</Text>
            </View>

            <View style={{ marginTop: 14 }} data-testid="id-checker-preview-milestones" testID="id-checker-preview-milestones">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('idChecker.timeline.milestones', 'Milestones')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                {timelineMilestones.map((milestone: any, idx: number) => {
                  const tone = milestoneTone(String(milestone.status || 'upcoming'));
                  return (
                    <View key={milestone.state || idx} style={{ flex: 1, minWidth: isMobile ? '100%' : 200, borderRadius: 14, borderWidth: 1, borderColor: tone.border, backgroundColor: tone.bg, padding: 12 }} data-testid={`id-checker-preview-milestone-${String(milestone.state || idx).toLowerCase()}`} testID={`id-checker-preview-milestone-${String(milestone.state || idx).toLowerCase()}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <Text style={{ color: tone.fg, fontSize: 11, fontWeight: '800' }}>{milestoneStatusLabel(String(milestone.status || 'upcoming'))}</Text>
                        <Text style={{ color: C.dim, fontSize: 10, fontWeight: '700' }}>#{idx + 1}</Text>
                      </View>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginTop: 8 }}>{milestoneTitle(milestone)}</Text>
                      <Text style={{ color: C.textSec, fontSize: 11, lineHeight: 17, marginTop: 6 }}>{milestoneEta(milestone)}</Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={{ marginTop: 14 }} data-testid="id-checker-preview-stages" testID="id-checker-preview-stages">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('idChecker.preview.stagesTitle', 'Workflow Stages')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {['NOT_SUBMITTED', 'PENDING', 'AI_REVIEW', 'ADMIN_REVIEW', 'APPROVED'].map((s) => {
                  const active = workflowState === s;
                  return (
                    <View key={s} style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: active ? C.primary : C.borderStrong, backgroundColor: active ? withAlpha(C.primary, '18') : sectionAltSurface }}>
                      <Text style={{ color: active ? C.primary : C.muted, fontSize: 10, fontWeight: '700' }}>{workflowStateLabel(s)}</Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={{ marginTop: 14, borderRadius: 14, borderWidth: 1, borderColor: withAlpha(C.success, '2E'), backgroundColor: withAlpha(C.success, '0E'), padding: 14 }} data-testid="id-checker-perks-teaser" testID="id-checker-perks-teaser">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="ribbon" size={16} color={C.success} />
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', flex: 1 }}>{tx('idChecker.perks.title', 'Verified Member Perks')}</Text>
              </View>
              <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('idChecker.perks.subtitle', 'Finish verification to unlock trust signals across your workspace.')}</Text>
              <View style={{ marginTop: 10, gap: 8 }}>
                {[
                  { key: 'badge', icon: 'shield-checkmark', label: tx('idChecker.perks.badge', 'Verified trust badge on your workspace profile') },
                  { key: 'lanes', icon: 'flash', label: tx('idChecker.perks.lanes', 'Faster review lanes with upgraded plans') },
                  { key: 'support', icon: 'headset', label: tx('idChecker.perks.support', 'Priority support handling for verified members') },
                ].map((perk) => (
                  <View key={perk.key} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }} data-testid={`id-checker-perk-${perk.key}`} testID={`id-checker-perk-${perk.key}`}>
                    <Ionicons name={perk.icon as any} size={13} color={C.success} style={{ marginTop: 2 }} />
                    <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, flex: 1 }}>{perk.label}</Text>
                  </View>
                ))}
              </View>
              <TouchableOpacity
                onPress={() => router.push('/subscription/plans' as any)}
                style={{ alignSelf: 'flex-start', marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primary, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 }}
                data-testid="id-checker-perks-view-plans-btn" testID="id-checker-perks-view-plans-btn"
              >
                <Ionicons name="rocket-outline" size={13} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('idChecker.perks.viewPlans', 'View plans')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {isRiskPlaceholderKyc(kyc) && (
          <View style={{ backgroundColor: C.infoBg, borderRadius: 10, borderWidth: 1, borderColor: C.infoBorder, padding: 12, marginBottom: 14 }} data-testid="idv-risk-placeholder-info" testID="idv-risk-placeholder-info">
            <Text style={{ color: C.infoText, fontSize: 12, lineHeight: 18, fontWeight: '600' }}>
              {tx('idVerification.placeholder.info', 'We created a temporary security verification placeholder. Please complete this form to continue document capture.')}
            </Text>
          </View>
        )}

        <View style={{ backgroundColor: sectionSurface, borderRadius: 18, padding: 20, borderWidth: 1, borderColor: C.borderStrong, gap: 14 }} data-testid="idv-form-section" testID="idv-form-section">
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('idVerification.form.personalInfo', 'Personal Information')}</Text>

          <View>
            <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('auth.name', 'Full Name')}</Text>
            <TextInput data-testid="idv-full-name" testID="idv-full-name" value={fullName} onChangeText={setFullName} placeholder={tx('idVerification.placeholder.fullName', 'Enter your full name')}
              placeholderTextColor={C.dim} style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong }} />
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.dob', 'Date of Birth')}</Text>
              <TextInput data-testid="idv-dob" testID="idv-dob" value={dob} onChangeText={setDob} placeholder={tx('idVerification.placeholder.dob', 'YYYY-MM-DD')}
                placeholderTextColor={C.dim} style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong }} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.nationality', 'Nationality (Country Code)')}</Text>
              <TextInput data-testid="idv-nationality" testID="idv-nationality" value={nationality} onChangeText={(v) => setNationality(v.toUpperCase())} placeholder={tx('idVerification.placeholder.nationality', 'e.g. CM, NG, US')}
                placeholderTextColor={C.dim} maxLength={3} style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong }} />
            </View>
          </View>

          <View>
            <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.idType', 'ID Type')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {ID_TYPES.map(t => (
                <TouchableOpacity key={t.value} data-testid={`idv-type-${t.value}`} testID={`idv-type-${t.value}`} onPress={() => setIdType(t.value)}
                  style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, borderWidth: 1.5,
                    borderColor: idType === t.value ? C.primary : C.borderStrong,
                    backgroundColor: idType === t.value ? withAlpha(C.primary, '15') : 'transparent' }}>
                  <Text style={{ color: idType === t.value ? C.primary : C.muted, fontSize: 12, fontWeight: '600' }}>{tx(t.labelKey, t.fallback)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View>
            <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.idNumber', 'ID Number')}</Text>
            <TextInput data-testid="idv-id-number" testID="idv-id-number" value={idNumber} onChangeText={setIdNumber} placeholder={tx('idVerification.placeholder.idNumber', 'Enter your ID number')}
              placeholderTextColor={C.dim} style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong }} />
          </View>

          <View>
            <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.phone', 'Phone Number')}</Text>
            <TextInput data-testid="idv-phone" testID="idv-phone" value={phone} onChangeText={setPhone} placeholder={tx('idVerification.placeholder.phone', '+237612345678')}
              placeholderTextColor={C.dim} style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong }} />
          </View>

          <View>
            <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>{tx('idVerification.form.address', 'Address')}</Text>
            <TextInput data-testid="idv-address" testID="idv-address" value={address} onChangeText={setAddress} placeholder={tx('idVerification.placeholder.address', 'Enter your address')}
              placeholderTextColor={C.dim} multiline style={{ backgroundColor: sectionAltSurface, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.borderStrong, minHeight: 60 }} />
          </View>
        </View>

        {error ? <Text style={{ color: C.error, fontSize: 12, textAlign: 'center', marginTop: 10 }}>{error}</Text> : null}

        <View style={{ backgroundColor: sectionAltSurface, borderRadius: 12, padding: 14, marginTop: 16, flexDirection: isMobile ? 'column' : 'row', gap: 10, borderWidth: 1, borderColor: C.borderStrong }}>
          <Ionicons name="information-circle" size={20} color={C.primary} />
          <Text style={{ color: C.dim, fontSize: 11, flex: 1, lineHeight: 16 }}>
            {tx('idVerification.form.captureHint', "After submitting, you'll capture three required images: ID front, ID back, and a clear selfie.")}
          </Text>
        </View>

        <View data-testid="idv-submit-form" testID="idv-submit-form">
          <TouchableOpacity data-testid="idv-start-btn" testID="idv-start-btn" onPress={submitForm} disabled={submitting}
            style={{ backgroundColor: C.primary, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: 16, opacity: submitting ? 0.6 : 1 }}>
            {submitting ? <ActivityIndicator color={colors.primaryText} /> : (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="arrow-forward" size={18} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 15 }}>{tx('idVerification.actions.continueToCapture', 'Continue to Capture')}</Text>
              </View>
            )}
          </TouchableOpacity>
        </View>
      </ScrollView>
      </View>
    </AppShell>
  );
}
