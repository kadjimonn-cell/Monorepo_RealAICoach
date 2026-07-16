import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { useLanguage } from '../../i18n/LanguageContext';

type TalentNetworkOverview = {
  window_days: number;
  generated_at: string;
  summary: {
    total_signups: number;
    active_signups: number;
    signups_in_window: number;
    dispatch_totals: {
      attempted: number;
      sent: number;
      failed: number;
    };
    frequency_breakdown?: {
      daily: number;
      weekly: number;
    };
    confidence?: {
      avg_score: number;
      distribution: {
        high: number;
        medium: number;
        low: number;
      };
      sample_size: number;
    };
    reminder_channel_breakdown?: {
      in_app: number;
      email: number;
    };
    premium_unlocked_count?: number;
    referral_accept_in_window?: number;
  };
  top_role_interests: { label: string; count: number }[];
  source_conversion: {
    source: string;
    signups: number;
    click_events: number;
    conversion_rate_pct: number;
  }[];
  latest_dispatch_run: {
    run_id?: string;
    status?: string;
    started_at?: string;
    completed_at?: string;
    attempted?: number;
    sent?: number;
    failed?: number;
  };
  recent_dispatches: {
    event_id: string;
    email: string;
    status: string;
    top_job_title: string;
    source: string;
    created_at: string;
    matched_count: number;
    alert_frequency?: 'daily' | 'weekly';
    confidence_score?: number;
    confidence_label?: 'high' | 'medium' | 'low';
  }[];
};

type TalentNetworkSegment = {
  segment_id: string;
  name: string;
  description?: string;
  alert_frequency: 'any' | 'daily' | 'weekly';
  reminder_channel: 'any' | 'in_app' | 'email';
  profile_min: number;
  profile_max: number;
  premium_state: 'any' | 'locked' | 'unlocked';
  marketing_consent_required: boolean;
  active: boolean;
  estimated_members?: number;
};

type TalentNetworkCampaign = {
  campaign_id: string;
  campaign_name: string;
  segment_id: string;
  segment_name: string;
  channel: 'in_app' | 'email';
  schedule_type: 'run_now' | 'scheduled';
  scheduled_at: string;
  message_title: string;
  message_body: string;
  cta_label?: string;
  cta_path?: string;
  status: string;
  last_run_summary?: {
    attempted: number;
    sent: number;
    skipped: number;
    failed: number;
  };
};

type TalentNetworkCampaignRun = {
  run_id: string;
  campaign_id: string;
  campaign_name: string;
  segment_id?: string;
  segment_name?: string;
  channel: 'in_app' | 'email';
  attempted: number;
  sent: number;
  skipped: number;
  failed: number;
  created_at: string;
};

type TalentNetworkDeliverabilitySummary = {
  segments_count: number;
  campaigns_count: number;
  sent: number;
  opened: number;
  clicked: number;
  open_rate_pct: number;
  click_rate_pct: number;
  click_to_open_rate_pct: number;
  quiet_hours_sent: number;
  quiet_hours_opened: number;
  quiet_hours_clicked: number;
  quiet_hours_open_rate_pct: number;
  non_quiet_open_rate_pct: number;
  quiet_hours_impact_pct: number;
};

type TalentNetworkDeliverabilitySegment = {
  segment_id: string;
  segment_name: string;
  campaign_count: number;
  sent: number;
  opened: number;
  clicked: number;
  unique_sent_recipients: number;
  unique_open_recipients: number;
  unique_click_recipients: number;
  open_rate_pct: number;
  click_rate_pct: number;
  click_to_open_rate_pct: number;
  quiet_hours_sent: number;
  quiet_hours_opened: number;
  quiet_hours_clicked: number;
  quiet_hours_open_rate_pct: number;
  non_quiet_open_rate_pct: number;
  quiet_hours_click_rate_pct: number;
  non_quiet_click_rate_pct: number;
  quiet_hours_impact_pct: number;
};

type TalentNetworkDeliverabilityPayload = {
  window_days: number;
  generated_at: string;
  summary: TalentNetworkDeliverabilitySummary;
  segments: TalentNetworkDeliverabilitySegment[];
};

const WINDOW_OPTIONS = [7, 30, 90] as const;

function KpiCard({
  title,
  value,
  subtitle,
  icon,
  tone,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: string;
  tone: string;
}) {
  const AC = useAdminTheme();
  return (
    <View
      style={{
        flex: 1,
        minWidth: 180,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: AC.border,
        backgroundColor: AC.bgAlt,
        padding: 14,
      }}
      data-testid={`talent-network-kpi-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
      testID={`talent-network-kpi-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ color: AC.textMuted, fontSize: 11, fontWeight: '700' }}>{title}</Text>
        <View style={{ width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: `${tone}1A` }}>
          <Ionicons name={icon as any} size={14} color={tone} />
        </View>
      </View>
      <Text style={{ color: AC.text, fontSize: 24, fontWeight: '800', marginTop: 8 }}>{value}</Text>
      <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{subtitle}</Text>
    </View>
  );
}

export const TalentNetworkAdminPanel = ({ colors }: { colors: any }) => {
  const { t } = useLanguage();
  const AC = useAdminTheme();
  const [windowDays, setWindowDays] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningDispatch, setRunningDispatch] = useState<boolean>(false);
  const [segmentLoading, setSegmentLoading] = useState<boolean>(false);
  const [campaignLoading, setCampaignLoading] = useState<boolean>(false);
  const [deliverabilityLoading, setDeliverabilityLoading] = useState<boolean>(false);
  const [submittingSegment, setSubmittingSegment] = useState<boolean>(false);
  const [submittingCampaign, setSubmittingCampaign] = useState<boolean>(false);
  const [runningCampaignId, setRunningCampaignId] = useState<string>('');
  const [overview, setOverview] = useState<TalentNetworkOverview | null>(null);
  const [segments, setSegments] = useState<TalentNetworkSegment[]>([]);
  const [campaigns, setCampaigns] = useState<TalentNetworkCampaign[]>([]);
  const [campaignRuns, setCampaignRuns] = useState<TalentNetworkCampaignRun[]>([]);
  const [deliverability, setDeliverability] = useState<TalentNetworkDeliverabilityPayload | null>(null);
  const [error, setError] = useState<string>('');

  const [segmentName, setSegmentName] = useState('High Momentum Members');
  const [segmentDescription, setSegmentDescription] = useState('Members with stronger profile completeness and reminder readiness.');
  const [segmentAlertFrequency, setSegmentAlertFrequency] = useState<'any' | 'daily' | 'weekly'>('any');
  const [segmentReminderChannel, setSegmentReminderChannel] = useState<'any' | 'in_app' | 'email'>('any');
  const [segmentPremiumState, setSegmentPremiumState] = useState<'any' | 'locked' | 'unlocked'>('any');
  const [segmentProfileMin, setSegmentProfileMin] = useState('40');
  const [segmentProfileMax, setSegmentProfileMax] = useState('100');
  const [segmentConsentRequired, setSegmentConsentRequired] = useState(false);

  const [campaignName, setCampaignName] = useState('Weekly Talent Momentum Nudge');
  const [campaignSegmentId, setCampaignSegmentId] = useState('');
  const [campaignChannel, setCampaignChannel] = useState<'in_app' | 'email'>('in_app');
  const [campaignScheduleType, setCampaignScheduleType] = useState<'run_now' | 'scheduled'>('run_now');
  const [campaignScheduledAt, setCampaignScheduledAt] = useState('');
  const [campaignMessageTitle, setCampaignMessageTitle] = useState('Your top role matches are getting stronger');
  const [campaignMessageBody, setCampaignMessageBody] = useState('Keep your streak active today. We found fresh opportunities that align with your profile and reminder cadence.');
  const [campaignCtaLabel, setCampaignCtaLabel] = useState('Open Talent Network');
  const [campaignCtaPath, setCampaignCtaPath] = useState('/talent-network');

  const parseNumberWithBounds = (value: string, fallback: number, min: number, max: number): number => {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, Math.floor(n)));
  };

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get(`/admin/careers/talent-network/overview?days=${windowDays}`, { silentLoading: true });
      setOverview(response?.data || null);
      setError('');
    } catch (e: any) {
      setError(String(e?.message || 'Unable to load Talent Network analytics.'));
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, [windowDays]);

  const loadSegments = useCallback(async () => {
    setSegmentLoading(true);
    try {
      const response = await api.get('/admin/careers/talent-network/segments', { silentLoading: true });
      const rows = Array.isArray(response?.data?.segments) ? response.data.segments : [];
      setSegments(rows);
      if (!campaignSegmentId && rows[0]?.segment_id) {
        setCampaignSegmentId(String(rows[0].segment_id));
      }
    } catch {
      setSegments([]);
    } finally {
      setSegmentLoading(false);
    }
  }, [campaignSegmentId]);

  const loadCampaigns = useCallback(async () => {
    setCampaignLoading(true);
    try {
      const response = await api.get('/admin/careers/talent-network/campaigns', { silentLoading: true });
      setCampaigns(Array.isArray(response?.data?.campaigns) ? response.data.campaigns : []);
      setCampaignRuns(Array.isArray(response?.data?.runs) ? response.data.runs : []);
    } catch {
      setCampaigns([]);
      setCampaignRuns([]);
    } finally {
      setCampaignLoading(false);
    }
  }, []);

  const loadDeliverability = useCallback(async () => {
    setDeliverabilityLoading(true);
    try {
      const response = await api.get(`/admin/careers/talent-network/deliverability-analytics?days=${windowDays}`, { silentLoading: true });
      const payload = response?.data || null;
      setDeliverability(payload);
    } catch {
      setDeliverability(null);
    } finally {
      setDeliverabilityLoading(false);
    }
  }, [windowDays]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    void loadSegments();
    void loadCampaigns();
  }, [loadSegments, loadCampaigns]);

  useEffect(() => {
    void loadDeliverability();
  }, [loadDeliverability]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/talent-network/overview-hybrid-refresh',
    onTick: loadOverview,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const runDispatchNow = useCallback(async () => {
    if (runningDispatch) return;
    setRunningDispatch(true);
    try {
      await api.post('/admin/careers/talent-network/dispatch/run-now?force=true', {}, { silentLoading: true });
      await loadOverview();
    } catch {
      // keep panel non-blocking
    } finally {
      setRunningDispatch(false);
    }
  }, [runningDispatch, loadOverview]);

  const submitSegment = useCallback(async () => {
    if (submittingSegment) return;
    setSubmittingSegment(true);
    try {
      const profileMin = parseNumberWithBounds(segmentProfileMin, 0, 0, 100);
      const profileMax = parseNumberWithBounds(segmentProfileMax, 100, 0, 100);
      await api.post(
        '/admin/careers/talent-network/segments',
        {
          name: segmentName.trim(),
          description: segmentDescription.trim(),
          alert_frequency: segmentAlertFrequency,
          reminder_channel: segmentReminderChannel,
          profile_min: Math.min(profileMin, profileMax),
          profile_max: Math.max(profileMin, profileMax),
          premium_state: segmentPremiumState,
          marketing_consent_required: segmentConsentRequired,
          active: true,
        },
        { silentLoading: true },
      );
      await loadSegments();
      setError('');
    } catch (e: any) {
      setError(String(e?.message || 'Unable to save segment.'));
    } finally {
      setSubmittingSegment(false);
    }
  }, [
    submittingSegment,
    segmentName,
    segmentDescription,
    segmentAlertFrequency,
    segmentReminderChannel,
    segmentProfileMin,
    segmentProfileMax,
    segmentPremiumState,
    segmentConsentRequired,
    loadSegments,
  ]);

  const submitCampaign = useCallback(async () => {
    if (submittingCampaign) return;
    setSubmittingCampaign(true);
    try {
      await api.post(
        '/admin/careers/talent-network/campaigns',
        {
          campaign_name: campaignName.trim(),
          segment_id: campaignSegmentId,
          channel: campaignChannel,
          schedule_type: campaignScheduleType,
          scheduled_at: campaignScheduleType === 'scheduled' ? campaignScheduledAt.trim() : undefined,
          message_title: campaignMessageTitle.trim(),
          message_body: campaignMessageBody.trim(),
          cta_label: campaignCtaLabel.trim(),
          cta_path: campaignCtaPath.trim() || '/talent-network',
        },
        { silentLoading: true },
      );
      await loadCampaigns();
      setError('');
    } catch (e: any) {
      setError(String(e?.message || 'Unable to create campaign.'));
    } finally {
      setSubmittingCampaign(false);
    }
  }, [
    submittingCampaign,
    campaignName,
    campaignSegmentId,
    campaignChannel,
    campaignScheduleType,
    campaignScheduledAt,
    campaignMessageTitle,
    campaignMessageBody,
    campaignCtaLabel,
    campaignCtaPath,
    loadCampaigns,
  ]);

  const runCampaignNow = useCallback(async (campaignId: string) => {
    if (!campaignId || runningCampaignId) return;
    setRunningCampaignId(campaignId);
    try {
      await api.post(`/admin/careers/talent-network/campaigns/${campaignId}/run-now`, {}, { silentLoading: true });
      await loadCampaigns();
      await loadOverview();
      await loadDeliverability();
      setError('');
    } catch (e: any) {
      setError(String(e?.message || 'Unable to run campaign now.'));
    } finally {
      setRunningCampaignId('');
    }
  }, [runningCampaignId, loadCampaigns, loadOverview, loadDeliverability]);

  const successRate = useMemo(() => {
    const attempted = Number(overview?.summary?.dispatch_totals?.attempted || 0);
    const sent = Number(overview?.summary?.dispatch_totals?.sent || 0);
    if (attempted <= 0) return 0;
    return Math.round((sent / attempted) * 100);
  }, [overview]);

  const avgConfidence = Number(overview?.summary?.confidence?.avg_score || 0);
  const freqDaily = Number(overview?.summary?.frequency_breakdown?.daily || 0);
  const freqWeekly = Number(overview?.summary?.frequency_breakdown?.weekly || 0);
  const reminderInApp = Number(overview?.summary?.reminder_channel_breakdown?.in_app || 0);
  const reminderEmail = Number(overview?.summary?.reminder_channel_breakdown?.email || 0);
  const premiumUnlocked = Number(overview?.summary?.premium_unlocked_count || 0);
  const referralWindow = Number(overview?.summary?.referral_accept_in_window || 0);
  const deliverabilitySummary = deliverability?.summary;
  const deliverabilitySegments = Array.isArray(deliverability?.segments) ? deliverability?.segments : [];

  if (loading && !overview) {
    return (
      <View
        style={{ minHeight: 220, alignItems: 'center', justifyContent: 'center' }}
        data-testid="talent-network-admin-panel-loading"
        testID="talent-network-admin-panel-loading"
      >
        <ActivityIndicator size="small" color={colors.primary} />
        <Text style={{ color: AC.textMuted, fontSize: 12, marginTop: 10 }}>{t("adopt.loading.talent.network.panel")}</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ gap: 14, padding: 14 }}
      data-testid="talent-network-admin-panel"
      testID="talent-network-admin-panel"
    >
      <View
        style={{
          borderRadius: 14,
          borderWidth: 1,
          borderColor: AC.border,
          backgroundColor: AC.bgAlt,
          padding: 14,
          gap: 12,
        }}
        data-testid="talent-network-admin-header"
        testID="talent-network-admin-header"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: AC.text, fontSize: 18, fontWeight: '800' }} data-testid="talent-network-admin-title" testID="talent-network-admin-title">{t("adopt.talent.network.control.center")}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 11, marginTop: 4 }} data-testid="talent-network-admin-subtitle" testID="talent-network-admin-subtitle">{t("adopt.signup.trends.role.interests.source.conversion.and.role")}</Text>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {WINDOW_OPTIONS.map((opt) => {
              const active = windowDays === opt;
              return (
                <TouchableOpacity
                  key={opt}
                  onPress={() => setWindowDays(opt)}
                  style={{
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? colors.primary : AC.border,
                    backgroundColor: active ? `${colors.primary}1A` : AC.bg,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                  }}
                  data-testid={`talent-network-window-option-${opt}`}
                  testID={`talent-network-window-option-${opt}`}
                >
                  <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '800' }}>{t("admin.csat.ai.lastRun")}{opt}d</Text>
                </TouchableOpacity>
              );
            })}

            <TouchableOpacity
              onPress={() => void loadOverview()}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="talent-network-refresh-button"
              testID="talent-network-refresh-button"
            >
              <Ionicons name="refresh" size={13} color={AC.textMuted} />
              <Text style={{ color: AC.textMuted, fontSize: 11, fontWeight: '700' }}>{t("abTesting.actions.refresh")}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => void runDispatchNow()}
              disabled={runningDispatch}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary, opacity: runningDispatch ? 0.7 : 1, paddingHorizontal: 11, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="talent-network-dispatch-now-button"
              testID="talent-network-dispatch-now-button"
            >
              {runningDispatch ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="paper-plane" size={13} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{runningDispatch ? 'Dispatching…' : 'Dispatch now'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {error ? (
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.error}66`, backgroundColor: `${colors.error}14`, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="talent-network-error-banner" testID="talent-network-error-banner">
            <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <KpiCard title="Total signups" value={overview?.summary?.total_signups || 0} subtitle="All-time Talent Network members" icon="people" tone={colors.primary} />
        <KpiCard title="Active" value={overview?.summary?.active_signups || 0} subtitle="Currently active members" icon="checkmark-circle" tone={colors.successText} />
        <KpiCard title={`Signups (${windowDays}d)`} value={overview?.summary?.signups_in_window || 0} subtitle="Recent conversion into Talent Network" icon="trending-up" tone={colors.warning} />
        <KpiCard title="Dispatch success" value={`${successRate}%`} subtitle={`${overview?.summary?.dispatch_totals?.sent || 0} sent / ${overview?.summary?.dispatch_totals?.attempted || 0} attempted`} icon="mail" tone={colors.accent || colors.primary} />
        <KpiCard title="Avg confidence" value={avgConfidence} subtitle={`${overview?.summary?.confidence?.sample_size || 0} matched dispatch samples`} icon="sparkles" tone={colors.successText} />
        <KpiCard title="Premium unlocked" value={premiumUnlocked} subtitle="Members with unlocked premium layer" icon="diamond" tone={colors.warning} />
        <KpiCard title={`Referrals (${windowDays}d)`} value={referralWindow} subtitle="Accepted referrals in selected window" icon="git-network" tone={colors.accent || colors.primary} />
      </View>

      <View
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: AC.border,
          backgroundColor: AC.bgAlt,
          padding: 12,
          gap: 10,
        }}
        data-testid="talent-network-deliverability-card"
        testID="talent-network-deliverability-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }} data-testid="talent-network-deliverability-title" testID="talent-network-deliverability-title">{t("adopt.deliverability.analytics.by.segment")}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 11, marginTop: 4 }} data-testid="talent-network-deliverability-subtitle" testID="talent-network-deliverability-subtitle">{t("adopt.open.click.performance.and.quiet.hours.impact.for")}</Text>
          </View>
          <TouchableOpacity
            onPress={() => void loadDeliverability()}
            style={{ borderRadius: 9, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
            data-testid="talent-network-deliverability-refresh-button"
            testID="talent-network-deliverability-refresh-button"
          >
            <Ionicons name="refresh" size={12} color={AC.textMuted} />
            <Text style={{ color: AC.textMuted, fontSize: 11, fontWeight: '700' }}>{deliverabilityLoading ? 'Refreshing…' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ flex: 1, minWidth: 190, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-deliverability-open-rate" testID="talent-network-deliverability-open-rate">
            <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.open.rate")}</Text>
            <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800', marginTop: 5 }}>{Number(deliverabilitySummary?.open_rate_pct || 0)}%</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{Number(deliverabilitySummary?.opened || 0)}{t("adopt.opens")}{Number(deliverabilitySummary?.sent || 0)}{t("admin.gdpr.common.sent")}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 190, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-deliverability-click-rate" testID="talent-network-deliverability-click-rate">
            <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.click.rate")}</Text>
            <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800', marginTop: 5 }}>{Number(deliverabilitySummary?.click_rate_pct || 0)}%</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{Number(deliverabilitySummary?.clicked || 0)}{t("adopt.clicks")}{Number(deliverabilitySummary?.sent || 0)}{t("admin.gdpr.common.sent")}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 220, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-deliverability-quiet-impact" testID="talent-network-deliverability-quiet-impact">
            <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.quiet.hours.impact")}</Text>
            <Text style={{ color: Number(deliverabilitySummary?.quiet_hours_impact_pct || 0) <= 0 ? colors.successText : colors.warning, fontSize: 20, fontWeight: '800', marginTop: 5 }}>
              {Number(deliverabilitySummary?.quiet_hours_impact_pct || 0)}%
            </Text>
            <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{t("adopt.quiet.open")}{Number(deliverabilitySummary?.quiet_hours_open_rate_pct || 0)}{t("adopt.non.quiet.open")}{Number(deliverabilitySummary?.non_quiet_open_rate_pct || 0)}%
            </Text>
          </View>
        </View>

        <View style={{ gap: 7 }} data-testid="talent-network-deliverability-segment-list" testID="talent-network-deliverability-segment-list">
          {deliverabilityLoading ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.loading.deliverability.analytics")}</Text> : null}
          {!deliverabilityLoading && deliverabilitySegments.length === 0 ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.campaign.deliverability.data.yet.run.campaigns.and")}</Text> : null}
          {deliverabilitySegments.map((row, idx) => (
            <View key={`${row.segment_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-deliverability-segment-row-${idx}`} testID={`talent-network-deliverability-segment-row-${idx}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }}>{row.segment_name}</Text>
                <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{row.campaign_count}{t("adopt.campaign.s")}</Text>
              </View>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{t("admin.abTestsView.metrics.sent")}{row.sent}{t("adopt.open")}{row.opened} ({row.open_rate_pct}{t("adopt.click")}{row.clicked} ({row.click_rate_pct}%)
              </Text>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 3 }}>{t("adopt.quiet.sent")}{row.quiet_hours_sent}{t("adopt.quiet.open.2")}{row.quiet_hours_open_rate_pct}{t("adopt.quiet.impact")}{row.quiet_hours_impact_pct}%
              </Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View
          style={{
            flex: 1,
            minWidth: 320,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: AC.border,
            backgroundColor: AC.bgAlt,
            padding: 12,
            gap: 10,
          }}
          data-testid="talent-network-role-interests-card"
          testID="talent-network-role-interests-card"
        >
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.top.role.interests")}</Text>
          {(overview?.top_role_interests || []).length === 0 ? (
            <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.role.interest.data.yet")}</Text>
          ) : (
            <View style={{ gap: 8 }}>
              {(overview?.top_role_interests || []).map((row, idx) => (
                <View key={`${row.label}-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`talent-network-role-interest-row-${idx}`} testID={`talent-network-role-interest-row-${idx}`}>
                  <View style={{ width: 24, alignItems: 'center' }}>
                    <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>#{idx + 1}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }}>{row.label}</Text>
                  </View>
                  <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{row.count}</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        <View
          style={{
            flex: 1,
            minWidth: 320,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: AC.border,
            backgroundColor: AC.bgAlt,
            padding: 12,
            gap: 10,
          }}
          data-testid="talent-network-source-conversion-card"
          testID="talent-network-source-conversion-card"
        >
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.source.conversion")}</Text>
          {(overview?.source_conversion || []).length === 0 ? (
            <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.source.conversion.data.yet")}</Text>
          ) : (
            <View style={{ gap: 8 }}>
              {(overview?.source_conversion || []).map((row, idx) => (
                <View key={`${row.source}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-source-conversion-row-${idx}`} testID={`talent-network-source-conversion-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }}>{row.source || 'unknown'}</Text>
                    <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>{row.conversion_rate_pct}%</Text>
                  </View>
                  <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>
                    {row.signups}{t("adopt.signups")}{row.click_events}{t("adopt.tracked.events")}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View
          style={{
            flex: 1,
            minWidth: 320,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: AC.border,
            backgroundColor: AC.bgAlt,
            padding: 12,
            gap: 10,
          }}
          data-testid="talent-network-frequency-breakdown-card"
          testID="talent-network-frequency-breakdown-card"
        >
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.alert.frequency.breakdown")}</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-frequency-daily" testID="talent-network-frequency-daily">
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.daily")}</Text>
              <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{freqDaily}</Text>
            </View>
            <View style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-frequency-weekly" testID="talent-network-frequency-weekly">
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.weekly")}</Text>
              <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{freqWeekly}</Text>
            </View>
          </View>
        </View>

        <View
          style={{
            flex: 1,
            minWidth: 320,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: AC.border,
            backgroundColor: AC.bgAlt,
            padding: 12,
            gap: 10,
          }}
          data-testid="talent-network-confidence-distribution-card"
          testID="talent-network-confidence-distribution-card"
        >
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.confidence.distribution")}</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {[
              { key: 'high', label: 'High', tone: colors.successText },
              { key: 'medium', label: 'Medium', tone: colors.warning },
              { key: 'low', label: 'Low', tone: colors.error },
            ].map((band) => (
              <View key={band.key} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid={`talent-network-confidence-${band.key}`} testID={`talent-network-confidence-${band.key}`}>
                <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{band.label}</Text>
                <Text style={{ color: band.tone, fontSize: 20, fontWeight: '800', marginTop: 6 }}>
                  {Number((overview?.summary?.confidence?.distribution as any)?.[band.key] || 0)}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View
          style={{
            flex: 1,
            minWidth: 320,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: AC.border,
            backgroundColor: AC.bgAlt,
            padding: 12,
            gap: 10,
          }}
          data-testid="talent-network-reminder-channels-card"
          testID="talent-network-reminder-channels-card"
        >
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.reminder.channel.mix")}</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-reminder-channel-in-app" testID="talent-network-reminder-channel-in-app">
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("adopt.in.app")}</Text>
              <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{reminderInApp}</Text>
            </View>
            <View style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, padding: 10 }} data-testid="talent-network-reminder-channel-email" testID="talent-network-reminder-channel-email">
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{t("admin.escalationPanel.auto.text.011")}</Text>
              <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{reminderEmail}</Text>
            </View>
          </View>
        </View>
      </View>

      <View
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: AC.border,
          backgroundColor: AC.bgAlt,
          padding: 12,
          gap: 10,
        }}
        data-testid="talent-network-segment-ops-card"
        testID="talent-network-segment-ops-card"
      >
        <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.segment.operations")}</Text>
        <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.create.target.cohorts.for.campaign.scheduling.from.profile")}</Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TextInput
            value={segmentName}
            onChangeText={setSegmentName}
            placeholder="Segment name"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-segment-name-input"
            testID="talent-network-segment-name-input"
          />
          <TextInput
            value={segmentDescription}
            onChangeText={setSegmentDescription}
            placeholder="Description"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-segment-description-input"
            testID="talent-network-segment-description-input"
          />
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[{ key: 'any', label: 'Any cadence' }, { key: 'daily', label: 'Daily only' }, { key: 'weekly', label: 'Weekly only' }].map((opt) => {
            const active = segmentAlertFrequency === opt.key;
            return (
              <TouchableOpacity key={opt.key} onPress={() => setSegmentAlertFrequency(opt.key as any)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : AC.border, backgroundColor: active ? `${colors.primary}14` : AC.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-segment-alert-frequency-${opt.key}`} testID={`talent-network-segment-alert-frequency-${opt.key}`}>
                <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
          {[{ key: 'any', label: 'Any channel' }, { key: 'in_app', label: 'In-app' }, { key: 'email', label: 'Email' }].map((opt) => {
            const active = segmentReminderChannel === opt.key;
            return (
              <TouchableOpacity key={opt.key} onPress={() => setSegmentReminderChannel(opt.key as any)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : AC.border, backgroundColor: active ? `${colors.primary}14` : AC.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-segment-reminder-channel-${opt.key}`} testID={`talent-network-segment-reminder-channel-${opt.key}`}>
                <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
          {[{ key: 'any', label: 'Any premium state' }, { key: 'locked', label: 'Premium locked' }, { key: 'unlocked', label: 'Premium unlocked' }].map((opt) => {
            const active = segmentPremiumState === opt.key;
            return (
              <TouchableOpacity key={opt.key} onPress={() => setSegmentPremiumState(opt.key as any)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : AC.border, backgroundColor: active ? `${colors.primary}14` : AC.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-segment-premium-state-${opt.key}`} testID={`talent-network-segment-premium-state-${opt.key}`}>
                <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextInput
            value={segmentProfileMin}
            onChangeText={setSegmentProfileMin}
            keyboardType="numeric"
            placeholder="Profile min"
            placeholderTextColor={AC.textMuted}
            style={{ minWidth: 130, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-segment-profile-min"
            testID="talent-network-segment-profile-min"
          />
          <TextInput
            value={segmentProfileMax}
            onChangeText={setSegmentProfileMax}
            keyboardType="numeric"
            placeholder="Profile max"
            placeholderTextColor={AC.textMuted}
            style={{ minWidth: 130, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-segment-profile-max"
            testID="talent-network-segment-profile-max"
          />
          <TouchableOpacity onPress={() => setSegmentConsentRequired((prev) => !prev)} style={{ borderRadius: 999, borderWidth: 1, borderColor: segmentConsentRequired ? colors.primary : AC.border, backgroundColor: segmentConsentRequired ? `${colors.primary}14` : AC.bg, paddingHorizontal: 11, paddingVertical: 7 }} data-testid="talent-network-segment-consent-toggle" testID="talent-network-segment-consent-toggle">
            <Text style={{ color: segmentConsentRequired ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{t("adopt.marketing.consent")}{segmentConsentRequired ? 'required' : 'optional'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => void submitSegment()} disabled={submittingSegment} style={{ borderRadius: 9, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, opacity: submittingSegment ? 0.7 : 1 }} data-testid="talent-network-segment-save-button" testID="talent-network-segment-save-button">
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{submittingSegment ? 'Saving…' : 'Save segment'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ gap: 7 }} data-testid="talent-network-segment-list" testID="talent-network-segment-list">
          {segmentLoading ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.loading.segments")}</Text> : null}
          {!segmentLoading && segments.length === 0 ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.segments.yet.create.your.first.segment.above")}</Text> : null}
          {segments.slice(0, 8).map((segment, idx) => (
            <View key={`${segment.segment_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-segment-row-${idx}`} testID={`talent-network-segment-row-${idx}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }}>{segment.name}</Text>
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{Number(segment.estimated_members || 0)}{t("adopt.members")}</Text>
              </View>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>
                {segment.alert_frequency.toUpperCase()}{t("adopt.cadence")}{segment.reminder_channel.toUpperCase()}{t("adopt.channel.profile")}{segment.profile_min}-{segment.profile_max}
              </Text>
            </View>
          ))}
        </View>
      </View>

      <View
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: AC.border,
          backgroundColor: AC.bgAlt,
          padding: 12,
          gap: 10,
        }}
        data-testid="talent-network-campaign-scheduler-card"
        testID="talent-network-campaign-scheduler-card"
      >
        <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.campaign.scheduler")}</Text>
        <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.build.in.app.email.campaigns.from.your.segments")}</Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TextInput
            value={campaignName}
            onChangeText={setCampaignName}
            placeholder="Campaign name"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-campaign-name-input"
            testID="talent-network-campaign-name-input"
          />
          <TextInput
            value={campaignSegmentId}
            onChangeText={setCampaignSegmentId}
            placeholder="Segment ID"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-campaign-segment-id-input"
            testID="talent-network-campaign-segment-id-input"
          />
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[{ key: 'in_app', label: 'In-app campaign' }, { key: 'email', label: 'Email campaign' }].map((opt) => {
            const active = campaignChannel === opt.key;
            return (
              <TouchableOpacity key={opt.key} onPress={() => setCampaignChannel(opt.key as any)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : AC.border, backgroundColor: active ? `${colors.primary}14` : AC.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-campaign-channel-${opt.key}`} testID={`talent-network-campaign-channel-${opt.key}`}>
                <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
          {[{ key: 'run_now', label: 'Run now' }, { key: 'scheduled', label: 'Schedule' }].map((opt) => {
            const active = campaignScheduleType === opt.key;
            return (
              <TouchableOpacity key={opt.key} onPress={() => setCampaignScheduleType(opt.key as any)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : AC.border, backgroundColor: active ? `${colors.primary}14` : AC.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-campaign-schedule-type-${opt.key}`} testID={`talent-network-campaign-schedule-type-${opt.key}`}>
                <Text style={{ color: active ? colors.primary : AC.textMuted, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {campaignScheduleType === 'scheduled' ? (
          <TextInput
            value={campaignScheduledAt}
            onChangeText={setCampaignScheduledAt}
            placeholder="Scheduled at ISO (e.g., 2026-07-01T10:00:00+00:00)"
            placeholderTextColor={AC.textMuted}
            style={{ borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-campaign-scheduled-at-input"
            testID="talent-network-campaign-scheduled-at-input"
          />
        ) : null}

        <TextInput
          value={campaignMessageTitle}
          onChangeText={setCampaignMessageTitle}
          placeholder="Message title"
          placeholderTextColor={AC.textMuted}
          style={{ borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
          data-testid="talent-network-campaign-message-title-input"
          testID="talent-network-campaign-message-title-input"
        />
        <TextInput accessibilityLabel="Message body"
          value={campaignMessageBody}
          onChangeText={setCampaignMessageBody}
          multiline
          numberOfLines={3}
          placeholder="Message body"
          placeholderTextColor={AC.textMuted}
          style={{ borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, minHeight: 80, outlineStyle: 'none' as any }}
          data-testid="talent-network-campaign-message-body-input"
          testID="talent-network-campaign-message-body-input"
        />

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TextInput
            value={campaignCtaLabel}
            onChangeText={setCampaignCtaLabel}
            placeholder="CTA label"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-campaign-cta-label-input"
            testID="talent-network-campaign-cta-label-input"
          />
          <TextInput
            value={campaignCtaPath}
            onChangeText={setCampaignCtaPath}
            placeholder="CTA path"
            placeholderTextColor={AC.textMuted}
            style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: AC.border, borderRadius: 9, color: AC.text, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
            data-testid="talent-network-campaign-cta-path-input"
            testID="talent-network-campaign-cta-path-input"
          />
        </View>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={() => void submitCampaign()} disabled={submittingCampaign} style={{ borderRadius: 9, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 9, opacity: submittingCampaign ? 0.7 : 1 }} data-testid="talent-network-campaign-create-button" testID="talent-network-campaign-create-button">
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{submittingCampaign ? 'Creating…' : 'Create campaign'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => void loadCampaigns()} style={{ borderRadius: 9, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="talent-network-campaign-refresh-button" testID="talent-network-campaign-refresh-button">
            <Text style={{ color: AC.textMuted, fontSize: 11, fontWeight: '700' }}>{t("adopt.refresh.campaigns")}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ gap: 8 }} data-testid="talent-network-campaign-list" testID="talent-network-campaign-list">
          {campaignLoading ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.loading.campaigns")}</Text> : null}
          {!campaignLoading && campaigns.length === 0 ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.campaigns.yet")}</Text> : null}
          {campaigns.slice(0, 8).map((campaign, idx) => (
            <View key={`${campaign.campaign_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-campaign-row-${idx}`} testID={`talent-network-campaign-row-${idx}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }}>{campaign.campaign_name}</Text>
                <View style={{ borderRadius: 999, backgroundColor: `${colors.primary}14`, paddingHorizontal: 8, paddingVertical: 4 }}>
                  <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '800' }}>{(campaign.status || 'scheduled').toUpperCase()}</Text>
                </View>
              </View>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>
                {campaign.channel.toUpperCase()}{t("adopt.segment")}{campaign.segment_name || campaign.segment_id}{t("adopt.scheduled")}{campaign.scheduled_at ? new Date(campaign.scheduled_at).toLocaleString() : '—'}
              </Text>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{t("autofix.last.run")}{campaign.last_run_summary ? `${campaign.last_run_summary.sent}/${campaign.last_run_summary.attempted} sent` : 'not run yet'}
              </Text>
              <TouchableOpacity
                onPress={() => void runCampaignNow(campaign.campaign_id)}
                disabled={runningCampaignId === campaign.campaign_id}
                style={{ alignSelf: 'flex-start', marginTop: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.primary, backgroundColor: `${colors.primary}14`, paddingHorizontal: 10, paddingVertical: 6, opacity: runningCampaignId === campaign.campaign_id ? 0.7 : 1 }}
                data-testid={`talent-network-campaign-run-now-${idx}`}
                testID={`talent-network-campaign-run-now-${idx}`}
              >
                <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{runningCampaignId === campaign.campaign_id ? 'Running…' : 'Run now'}</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>

        <View style={{ gap: 7 }} data-testid="talent-network-campaign-runs-list" testID="talent-network-campaign-runs-list">
          <Text style={{ color: AC.text, fontSize: 12, fontWeight: '800' }}>{t("adopt.recent.campaign.runs")}</Text>
          {campaignRuns.length === 0 ? <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.run.history.yet")}</Text> : null}
          {campaignRuns.slice(0, 8).map((run, idx) => (
            <View key={`${run.run_id}-${idx}`} style={{ borderRadius: 9, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-campaign-run-row-${idx}`} testID={`talent-network-campaign-run-row-${idx}`}>
              <Text style={{ color: AC.text, fontSize: 11, fontWeight: '700' }}>{run.campaign_name} • {run.channel.toUpperCase()}</Text>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{t("admin.gdpr.common.sent")}{run.sent}/{run.attempted}{t("adopt.skipped")}{run.skipped}{t("adopt.failed")}{run.failed}
              </Text>
              <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 4 }}>{run.created_at ? new Date(run.created_at).toLocaleString() : '—'}</Text>
            </View>
          ))}
        </View>
      </View>

      <View
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: AC.border,
          backgroundColor: AC.bgAlt,
          padding: 12,
          gap: 10,
        }}
        data-testid="talent-network-dispatch-activity-card"
        testID="talent-network-dispatch-activity-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{t("adopt.recent.dispatch.activity")}</Text>
          <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid="talent-network-latest-dispatch-status" testID="talent-network-latest-dispatch-status">{t("autofix.last.run")}{overview?.latest_dispatch_run?.status || '—'}
            {overview?.latest_dispatch_run?.completed_at ? ` · ${new Date(overview.latest_dispatch_run.completed_at).toLocaleString()}` : ''}
          </Text>
        </View>

        {(overview?.recent_dispatches || []).length === 0 ? (
          <Text style={{ color: AC.textMuted, fontSize: 11 }}>{t("adopt.no.recent.dispatch.records.in.this.window")}</Text>
        ) : (
          <View style={{ gap: 8 }} data-testid="talent-network-recent-dispatch-list" testID="talent-network-recent-dispatch-list">
            {(overview?.recent_dispatches || []).map((row, idx) => (
              <View
                key={`${row.event_id}-${idx}`}
                style={{ borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bg, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid={`talent-network-dispatch-row-${idx}`}
                testID={`talent-network-dispatch-row-${idx}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ color: AC.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{row.email}</Text>
                  <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: row.status === 'sent' ? `${colors.successText}1A` : `${colors.error}1A` }}>
                    <Text style={{ color: row.status === 'sent' ? colors.successText : colors.error, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>
                      {row.status}
                    </Text>
                  </View>
                </View>
                <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 5 }}>
                  {row.top_job_title || 'Role alert'}{t("adopt.source")}{row.source || 'unknown'}{t("adopt.matched")}{row.matched_count || 0}
                </Text>
                <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 3 }}>{t("adopt.frequency")}{(row.alert_frequency || 'weekly').toUpperCase()}{t("adopt.confidence")}{typeof row.confidence_score === 'number' ? row.confidence_score : 0} ({(row.confidence_label || 'low').toUpperCase()})
                </Text>
                <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 3 }}>
                  {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </ScrollView>
  );
};

export default TalentNetworkAdminPanel;
