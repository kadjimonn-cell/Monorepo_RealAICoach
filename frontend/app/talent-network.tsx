import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { trackCareersEvent } from '../src/utils/careersTelemetry';
import { buildAnalyticsSource } from '../src/utils/buildAnalyticsSource';
import { useLanguage } from '../src/i18n/LanguageContext';

const API = resolveRuntimeBaseUrl();
const TALENT_NETWORK_PAGE_SOURCE = buildAnalyticsSource('talent', 'network', 'page');
const TALENT_NETWORK_PRO_HUB_SOURCE = buildAnalyticsSource('talent', 'network', 'pro', 'hub');
const TALENT_NETWORK_HUB_SOURCE = buildAnalyticsSource('talent', 'network', 'hub');
const TALENT_NETWORK_TIMELINE_SOURCE = buildAnalyticsSource('talent', 'network', 'timeline');

type Facets = {
  departments: string[];
  locations: string[];
  types: string[];
};

type TalentHubResponse = {
  success: boolean;
  member: {
    email: string;
    full_name?: string;
    role_interests?: string[];
    locations?: string[];
    work_types?: string[];
    alert_frequency?: 'daily' | 'weekly';
    reminder_channels?: string[];
    quiet_hours_start_hour?: number | null;
    quiet_hours_end_hour?: number | null;
    consent_marketing?: boolean;
  };
  state: {
    profile_completeness: number;
    referral_code: string;
    referral_points: number;
    premium_unlocked: boolean;
    recent_referrals: number;
    momentum: {
      current_streak: number;
      longest_streak: number;
      total_checkins: number;
      next_milestone: number;
      remaining_to_milestone: number;
      challenge: {
        target: number;
        progress: number;
        progress_pct: number;
      };
    };
  };
  top_matches: {
    slug: string;
    title: string;
    department: string;
    location: string;
    type: string;
    level?: string;
    match_score: number;
    match_reasons: string[];
  }[];
  premium: {
    is_unlocked: boolean;
  };
};

type ReminderTimelineResponse = {
  success: boolean;
  timeline: {
    email: string;
    alert_frequency: 'daily' | 'weekly';
    reminder_channels: string[];
    quiet_hours_start_hour?: number | null;
    quiet_hours_end_hour?: number | null;
    next_reminder_eta: string;
    snoozed_until?: string | null;
    last_digest_sent_at?: string | null;
    last_action?: string;
    updated_at?: string;
    history: {
      event_id: string;
      event_type: string;
      action?: string;
      channel?: string;
      campaign_id?: string;
      campaign_name?: string;
      meta?: Record<string, any>;
      created_at: string;
    }[];
  };
};

const getQueryParam = (key: string): string => {
  if (typeof window === 'undefined') return '';
  try {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get(key) || '').trim();
  } catch {
    return '';
  }
};

const toSlug = (value: string) => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const parseHourValue = (value: string): number | null => {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n < 0 || n > 23) return null;
  return Math.floor(n);
};

export default function TalentNetworkPage() {
  const { t } = useLanguage();
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const pad = isMobile ? 16 : 28;
  const referralFromQuery = getQueryParam('referral');

  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [roleInterests, setRoleInterests] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [workTypes, setWorkTypes] = useState<string[]>([]);
  const [alertFrequency, setAlertFrequency] = useState<'daily' | 'weekly'>('weekly');
  const [reminderChannels, setReminderChannels] = useState<string[]>(['in_app', 'email']);
  const [quietStart, setQuietStart] = useState('22');
  const [quietEnd, setQuietEnd] = useState('7');
  const [consentMarketing, setConsentMarketing] = useState(false);
  const [referralInput, setReferralInput] = useState(referralFromQuery || '');

  const [facets, setFacets] = useState<Facets>({ departments: [], locations: [], types: [] });
  const [hub, setHub] = useState<TalentHubResponse | null>(null);
  const [notJoined, setNotJoined] = useState(false);
  const [loadingHub, setLoadingHub] = useState(false);
  const [joining, setJoining] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savedMatches, setSavedMatches] = useState<Record<string, boolean>>({});
  const [timeline, setTimeline] = useState<ReminderTimelineResponse['timeline'] | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineActionLoading, setTimelineActionLoading] = useState(false);
  const [campaignInteractionLoadingKey, setCampaignInteractionLoadingKey] = useState('');

  const toggleValue = useCallback((value: string, setState: React.Dispatch<React.SetStateAction<string[]>>) => {
    setState((prev) => (prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]));
  }, []);

  const hydrateFromHub = useCallback((payload: TalentHubResponse) => {
    setHub(payload);
    setNotJoined(false);
    setFullName(String(payload.member?.full_name || ''));
    setEmail(String(payload.member?.email || ''));
    setRoleInterests(Array.isArray(payload.member?.role_interests) ? payload.member.role_interests : []);
    setLocations(Array.isArray(payload.member?.locations) ? payload.member.locations : []);
    setWorkTypes(Array.isArray(payload.member?.work_types) ? payload.member.work_types : []);
    setAlertFrequency(payload.member?.alert_frequency === 'daily' ? 'daily' : 'weekly');
    setReminderChannels(Array.isArray(payload.member?.reminder_channels) && payload.member.reminder_channels.length ? payload.member.reminder_channels : ['in_app', 'email']);
    setQuietStart(payload.member?.quiet_hours_start_hour != null ? String(payload.member.quiet_hours_start_hour) : '22');
    setQuietEnd(payload.member?.quiet_hours_end_hour != null ? String(payload.member.quiet_hours_end_hour) : '7');
    setConsentMarketing(Boolean(payload.member?.consent_marketing));
  }, []);

  const loadReminderTimeline = useCallback(async (targetEmail?: string) => {
    const normalized = String(targetEmail || email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) return;
    setTimelineLoading(true);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/reminder-timeline?email=${encodeURIComponent(normalized)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const payload = await res.json().catch(() => ({} as any));
      if (res.ok && payload?.success && payload?.timeline) {
        setTimeline(payload.timeline);
      }
    } catch {
      // keep non-blocking
    } finally {
      setTimelineLoading(false);
    }
  }, [email]);

  const loadHub = useCallback(async (targetEmail?: string) => {
    const normalized = String(targetEmail || email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) {
      setMessage({ type: 'error', text: tx('talentNetwork.validation.loadHubEmail', 'Please enter a valid email address to load your Talent Network hub.') });
      return;
    }
    setLoadingHub(true);
    setMessage(null);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/hub?email=${encodeURIComponent(normalized)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (res.status === 404) {
        setHub(null);
        setNotJoined(true);
        setMessage({ type: 'error', text: tx('talentNetwork.error.noProfile', 'No Talent Network profile found for this email. Complete the premium join flow below.') });
        return;
      }
      const data = await res.json().catch(() => ({} as any));
      if (!res.ok || !data?.success) {
        throw new Error(data?.detail || tx('talentNetwork.error.loadDashboard', 'Could not load your Talent Network dashboard.'));
      }
      hydrateFromHub(data as TalentHubResponse);
      await loadReminderTimeline(normalized);
      setMessage({ type: 'success', text: tx('talentNetwork.success.dashboardLoaded', 'Talent Network dashboard loaded successfully.') });
      await trackCareersEvent({
        event: 'talent_network_hub_loaded',
        source: TALENT_NETWORK_PAGE_SOURCE,
        page: '/talent-network',
        ref: getQueryParam('ref') || 'direct',
      });
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || tx('talentNetwork.error.loadHub', 'Could not load hub.')) });
    } finally {
      setLoadingHub(false);
    }
  }, [email, hydrateFromHub, loadReminderTimeline, tx]);

  useEffect(() => {
    void trackCareersEvent({
      event: 'talent_network_page_view',
      source: TALENT_NETWORK_PAGE_SOURCE,
      page: '/talent-network',
      ref: getQueryParam('ref') || 'direct',
    });

    const bootstrap = async () => {
      try {
        const facetsRes = await fetch(`${API}/api/careers/facets`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const facetsData = await facetsRes.json().catch(() => ({} as any));
        if (facetsRes.ok) {
          setFacets({
            departments: Array.isArray(facetsData?.departments) ? facetsData.departments : [],
            locations: Array.isArray(facetsData?.locations) ? facetsData.locations : [],
            types: Array.isArray(facetsData?.types) ? facetsData.types : [],
          });
        }
      } catch {
        setFacets({ departments: [], locations: [], types: [] });
      }

      const prefEmail = getQueryParam('email');
      if (prefEmail) {
        setEmail(prefEmail.toLowerCase());
        await loadHub(prefEmail.toLowerCase());
      }
    };
    void bootstrap();
  }, [loadHub]);

  const joinTalentNetwork = useCallback(async () => {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) {
      setMessage({ type: 'error', text: tx('talentNetwork.validation.provideEmail', 'Please provide a valid email address.') });
      return;
    }
    setJoining(true);
    setMessage(null);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/join`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: normalized,
          full_name: fullName.trim(),
          role_interests: roleInterests,
          locations,
          work_types: workTypes,
          alert_frequency: alertFrequency,
          reminder_channels: reminderChannels,
          quiet_hours_start_hour: parseHourValue(quietStart),
          quiet_hours_end_hour: parseHourValue(quietEnd),
          consent_marketing: consentMarketing,
          source: TALENT_NETWORK_PRO_HUB_SOURCE,
          ref: getQueryParam('ref') || 'talent-network-direct',
        }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || payload?.message || tx('talentNetwork.error.join', 'Could not join Talent Network.'));
      }
      setMessage({ type: 'success', text: payload?.already_joined ? tx('talentNetwork.success.profileRefreshed', 'Profile refreshed. Your premium preferences are updated.') : tx('talentNetwork.success.joined', 'Welcome to Talent Network Pro. Your dashboard is ready.') });
      await trackCareersEvent({ event: 'talent_network_joined_pro', source: TALENT_NETWORK_PAGE_SOURCE, page: '/talent-network', ref: 'talent-network-direct' });
      await loadHub(normalized);
      await loadReminderTimeline(normalized);
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || tx('talentNetwork.error.joinNow', 'Could not join right now.')) });
    } finally {
      setJoining(false);
    }
  }, [alertFrequency, consentMarketing, email, fullName, loadHub, loadReminderTimeline, locations, quietEnd, quietStart, reminderChannels, roleInterests, tx, workTypes]);

  const savePreferences = useCallback(async () => {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) {
      setMessage({ type: 'error', text: tx('talentNetwork.validation.validEmailFirst', 'Please use a valid email first.') });
      return;
    }
    setSavingPrefs(true);
    setMessage(null);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/preferences`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: normalized,
          full_name: fullName.trim(),
          role_interests: roleInterests,
          locations,
          work_types: workTypes,
          alert_frequency: alertFrequency,
          reminder_channels: reminderChannels,
          quiet_hours_start_hour: parseHourValue(quietStart),
          quiet_hours_end_hour: parseHourValue(quietEnd),
          consent_marketing: consentMarketing,
        }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || tx('talentNetwork.error.savePreferences', 'Could not save preferences.'));
      }
      setMessage({ type: 'success', text: tx('talentNetwork.success.preferencesUpdated', 'Preferences updated. We will personalize your opportunities and reminders.') });
      await loadHub(normalized);
      await loadReminderTimeline(normalized);
      await trackCareersEvent({ event: 'talent_network_preferences_saved', source: TALENT_NETWORK_PAGE_SOURCE, page: '/talent-network', ref: 'talent-network-direct' });
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || tx('talentNetwork.error.savePreferencesShort', 'Could not save preferences.')) });
    } finally {
      setSavingPrefs(false);
    }
  }, [alertFrequency, consentMarketing, email, fullName, loadHub, loadReminderTimeline, locations, quietEnd, quietStart, reminderChannels, roleInterests, tx, workTypes]);

  const runCheckIn = useCallback(async (action: 'daily_visit' | 'save_match' | 'share' | 'apply' | 'profile_update') => {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) return;
    try {
      const res = await fetch(`${API}/api/careers/talent-network/check-in`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ email: normalized, action, source: TALENT_NETWORK_HUB_SOURCE }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (res.ok && payload?.success && hub) {
        setHub({
          ...hub,
          state: {
            ...hub.state,
            momentum: payload.momentum || hub.state.momentum,
          },
        });
      }
      await loadReminderTimeline(normalized);
    } catch {
      // best effort
    }
  }, [email, hub, loadReminderTimeline]);

  const runTimelineAction = useCallback(async (action: 'snooze' | 'resume', snoozeHours: number = 6) => {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) {
      setMessage({ type: 'error', text: 'Load your hub first using a valid email.' });
      return;
    }
    setTimelineActionLoading(true);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/reminder-action`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: normalized,
          action,
          snooze_hours: snoozeHours,
          note: action === 'snooze' ? `Snoozed by user for ${snoozeHours}h` : 'Resumed by user',
        }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || payload?.message || 'Could not update reminder timeline action.');
      }
      setMessage({ type: 'success', text: action === 'snooze' ? `Reminders snoozed for ${snoozeHours} hours.` : 'Reminder timeline resumed.' });
      await loadReminderTimeline(normalized);
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || 'Could not update reminder timeline.') });
    } finally {
      setTimelineActionLoading(false);
    }
  }, [email, loadReminderTimeline]);

  const openCampaignPath = useCallback((path?: string) => {
    const target = String(path || '').trim();
    if (!target) {
      return;
    }
    if (target.startsWith('http://') || target.startsWith('https://')) {
      try {
        if (typeof window !== 'undefined') {
          window.open(target, '_blank', 'noopener,noreferrer');
        }
      } catch {
        // no-op
      }
      return;
    }
    if (target.startsWith('/')) {
      router.push(target as any);
      return;
    }
    router.push(`/${target}` as any);
  }, []);

  const trackCampaignInteraction = useCallback(async (
    event: ReminderTimelineResponse['timeline']['history'][number],
    interaction: 'open' | 'click',
  ) => {
    const normalized = String(email || '').trim().toLowerCase();
    const campaignId = String(event?.campaign_id || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized) || !campaignId) {
      return;
    }
    const rowKey = `${interaction}-${event.event_id || campaignId}`;
    setCampaignInteractionLoadingKey(rowKey);
    try {
      const ctaPath = String(event?.meta?.cta_path || '').trim();
      const res = await fetch(`${API}/api/careers/talent-network/campaign-interaction`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: normalized,
          campaign_id: campaignId,
          interaction,
          channel: event?.channel === 'email' ? 'email' : 'in_app',
          source: TALENT_NETWORK_TIMELINE_SOURCE,
          cta_path: ctaPath || undefined,
        }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || payload?.message || 'Unable to track reminder interaction.');
      }
      if (interaction === 'click') {
        openCampaignPath(ctaPath || '/talent-network');
      } else {
        setMessage({ type: 'success', text: 'Reminder interaction tracked.' });
      }
      await loadReminderTimeline(normalized);
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || 'Unable to track interaction right now.') });
    } finally {
      setCampaignInteractionLoadingKey('');
    }
  }, [email, loadReminderTimeline, openCampaignPath]);

  const openExternal = (url: string) => {
    try {
      if (typeof window !== 'undefined') {
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    } catch {
      // no-op
    }
  };

  const shareReferral = useCallback(async (channel: 'whatsapp' | 'x' | 'linkedin' | 'copy_link') => {
    const normalized = String(email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(normalized)) {
      setMessage({ type: 'error', text: 'Enter your email and load hub before sharing.' });
      return;
    }
    try {
      const res = await fetch(`${API}/api/careers/talent-network/referral/share`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ email: normalized, channel, source: TALENT_NETWORK_HUB_SOURCE }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.message || payload?.detail || 'Unable to generate share preview now.');
      }

      const preview = payload?.share_preview || {};
      const shareText = `${String(preview?.text || '')} ${String(preview?.link || '')}`.trim();
      if (channel === 'copy_link') {
        const nav = (globalThis as any).navigator;
        if (nav?.clipboard?.writeText) {
          await nav.clipboard.writeText(String(preview?.link || ''));
        }
      } else if (channel === 'whatsapp') {
        openExternal(`https://wa.me/?text=${encodeURIComponent(shareText)}`);
      } else if (channel === 'x') {
        openExternal(`https://x.com/intent/tweet?text=${encodeURIComponent(shareText)}`);
      } else if (channel === 'linkedin') {
        openExternal(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(String(preview?.link || ''))}`);
      }

      setMessage({ type: 'success', text: channel === 'copy_link' ? 'Referral link copied. Ready to share.' : 'Share preview launched successfully.' });
      await runCheckIn('share');
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || 'Unable to share now.') });
    }
  }, [email, runCheckIn]);

  const acceptReferral = useCallback(async () => {
    const code = String(referralInput || '').trim().toLowerCase();
    if (!code) {
      setMessage({ type: 'error', text: 'Enter a referral code to apply.' });
      return;
    }
    try {
      const res = await fetch(`${API}/api/careers/talent-network/referral/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ referral_code: code, candidate_email: email || null, source: TALENT_NETWORK_HUB_SOURCE }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || payload?.message || 'Could not apply referral code.');
      }
      setMessage({ type: 'success', text: payload?.already_counted ? 'Referral already counted for this candidate.' : 'Referral accepted successfully.' });
      if (email) {
        await loadHub(email);
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: String(e?.message || 'Could not apply referral.') });
    }
  }, [email, loadHub, referralInput]);

  const averageTopScore = useMemo(() => {
    const values = (hub?.top_matches || []).slice(0, 3).map((m) => Number(m.match_score || 0));
    if (!values.length) return 0;
    return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  }, [hub]);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="talent-network-page" testID="talent-network-page">
      <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', paddingHorizontal: pad, paddingTop: isMobile ? 20 : 34, paddingBottom: 30, gap: 14 }}>
        <TouchableOpacity onPress={() => router.push('/welcome' as any)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="talent-network-back-welcome" testID="talent-network-back-welcome">
          <Ionicons name="arrow-back" size={16} color={colors.textSec} />
          <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{tx('talentNetwork.backToWelcome', 'Back to Welcome')}</Text>
        </TouchableOpacity>

        <View style={{ borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid="talent-network-hero" testID="talent-network-hero">
          <View style={{ position: 'absolute', right: -35, top: -40, width: 180, height: 180, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '22') }} />
          <View style={{ padding: isMobile ? 16 : 22, gap: 10 }}>
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' }} data-testid="talent-network-hero-badge" testID="talent-network-hero-badge">
              {tx('talentNetwork.hero.badge', 'Talent Network Pro')}
            </Text>
            <Text style={{ color: colors.text, fontSize: isMobile ? 26 : 36, fontWeight: '800', lineHeight: isMobile ? 32 : 42 }} data-testid="talent-network-hero-title" testID="talent-network-hero-title">
              {tx('talentNetwork.hero.title', 'Your career momentum operating system.')}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 14, lineHeight: 22 }} data-testid="talent-network-hero-subtitle" testID="talent-network-hero-subtitle">
              {tx('talentNetwork.hero.subtitle', 'Get personalized role matching, streak-based growth loops, smart reminders, and referral-powered premium unlocks.')}
            </Text>

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
              <View style={{ flex: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="mail-outline" size={14} color={colors.textMuted} />
                <TextInput
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  placeholder="you@company.com"
                  placeholderTextColor={colors.textMuted}
                  style={{ flex: 1, color: colors.text, fontSize: 13, paddingVertical: 4, outlineStyle: 'none' as any }}
                  data-testid="talent-network-email-input"
                  testID="talent-network-email-input"
                />
              </View>
              <TouchableOpacity onPress={() => { void loadHub(); }} disabled={loadingHub} style={{ borderRadius: 12, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8, opacity: loadingHub ? 0.75 : 1 }} data-testid="talent-network-load-hub-button" testID="talent-network-load-hub-button">
                {loadingHub ? <ActivityIndicator size="small" color={colors.primaryText || colors.text} /> : <Ionicons name="flash-outline" size={14} color={colors.primaryText || colors.text} />}
                <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>{t("adopt.load.my.hub")}</Text>
              </TouchableOpacity>
            </View>

            {message ? (
              <View style={{ borderRadius: 10, borderWidth: 1, borderColor: message.type === 'success' ? (globalThis as any).__alphaColor(colors.success, '70') : (globalThis as any).__alphaColor(colors.error, '70'), backgroundColor: message.type === 'success' ? (globalThis as any).__alphaColor(colors.success, '16') : (globalThis as any).__alphaColor(colors.error, '16'), paddingHorizontal: 10, paddingVertical: 8 }} data-testid="talent-network-feedback-banner" testID="talent-network-feedback-banner">
                <Text style={{ color: message.type === 'success' ? colors.success : colors.error, fontSize: 12, fontWeight: '700' }}>{message.text}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {(notJoined || !hub) ? (
          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 18, gap: 12 }} data-testid="talent-network-join-flow-card" testID="talent-network-join-flow-card">
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="talent-network-join-title" testID="talent-network-join-title">{t("adopt.join.talent.network.pro")}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20 }} data-testid="talent-network-join-subtitle" testID="talent-network-join-subtitle">{t("adopt.build.your.profile.once.receive.high.fit.opportunities")}</Text>

            <TextInput value={fullName} onChangeText={setFullName} placeholder="Full name" placeholderTextColor={colors.textMuted} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bg, color: colors.text, fontSize: 13, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="talent-network-fullname-input" testID="talent-network-fullname-input" />

            <PreferenceChips label="Role Interests" values={facets.departments.slice(0, 10)} selected={roleInterests} onToggle={(v) => toggleValue(v, setRoleInterests)} colors={colors} testPrefix="talent-network-role-interest" />
            <PreferenceChips label="Preferred Locations" values={facets.locations.slice(0, 8)} selected={locations} onToggle={(v) => toggleValue(v, setLocations)} colors={colors} testPrefix="talent-network-location" />
            <PreferenceChips label="Work Types" values={facets.types.slice(0, 6)} selected={workTypes} onToggle={(v) => toggleValue(v, setWorkTypes)} colors={colors} testPrefix="talent-network-worktype" />

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
              {['weekly', 'daily'].map((freq) => {
                const active = alertFrequency === freq;
                return (
                  <TouchableOpacity key={freq} onPress={() => setAlertFrequency(freq as 'daily' | 'weekly')} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '16') : colors.bg, paddingHorizontal: 10, paddingVertical: 10 }} data-testid={`talent-network-alert-frequency-${freq}`} testID={`talent-network-alert-frequency-${freq}`}>
                    <Text style={{ color: active ? colors.primary : colors.text, fontSize: 12, fontWeight: '800' }}>{freq === 'weekly' ? 'Weekly digest' : 'Daily alert pulse'}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>{freq === 'weekly' ? 'Lower noise, higher signal' : 'Fastest role visibility'}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
              <QuietHourInput label="Quiet start (0-23)" value={quietStart} onChange={setQuietStart} colors={colors} testId="talent-network-quiet-start-input" />
              <QuietHourInput label="Quiet end (0-23)" value={quietEnd} onChange={setQuietEnd} colors={colors} testId="talent-network-quiet-end-input" />
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { key: 'in_app', label: 'In-app reminders' },
                { key: 'email', label: 'Email reminders' },
              ].map((opt) => {
                const active = reminderChannels.includes(opt.key);
                return (
                  <TouchableOpacity key={opt.key} onPress={() => toggleValue(opt.key, setReminderChannels)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '16') : colors.bg, paddingHorizontal: 11, paddingVertical: 7 }} data-testid={`talent-network-reminder-channel-${opt.key}`} testID={`talent-network-reminder-channel-${opt.key}`}>
                    <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{opt.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <TouchableOpacity onPress={() => setConsentMarketing((prev) => !prev)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="talent-network-consent-toggle" testID="talent-network-consent-toggle">
              <Ionicons name={consentMarketing ? 'checkbox-outline' : 'square-outline'} size={16} color={consentMarketing ? colors.primary : colors.textMuted} />
              <Text style={{ color: colors.textSec, fontSize: 12 }}>{t("adopt.i.agree.to.receive.growth.updates.and.curated")}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { void joinTalentNetwork(); }} disabled={joining} style={{ borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 11, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8, opacity: joining ? 0.7 : 1 }} data-testid="talent-network-join-submit-button" testID="talent-network-join-submit-button">
              {joining ? <ActivityIndicator size="small" color={colors.primaryText || colors.text} /> : <Ionicons name="rocket-outline" size={14} color={colors.primaryText || colors.text} />}
              <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>{joining ? 'Joining…' : 'Activate Talent Network Pro'}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {hub ? (
          <>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
              <MetricCard title="Profile Completeness" value={`${hub.state.profile_completeness}%`} subtitle="Higher profile quality improves matching precision" icon="sparkles-outline" colors={colors} testId="talent-network-metric-profile" />
              <MetricCard title="Opportunity Score" value={`${averageTopScore}`} subtitle="Average fit across your top 3 matches" icon="trending-up-outline" colors={colors} testId="talent-network-metric-opportunity" />
              <MetricCard title="Streak" value={`${hub.state.momentum.current_streak} days`} subtitle={`Next milestone in ${hub.state.momentum.remaining_to_milestone} day(s)`} icon="flame-outline" colors={colors} testId="talent-network-metric-streak" />
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 18, gap: 10 }} data-testid="talent-network-momentum-card" testID="talent-network-momentum-card">
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }} data-testid="talent-network-momentum-title" testID="talent-network-momentum-title">{t("adopt.momentum.loop")}</Text>
              <Text style={{ color: colors.textSec, fontSize: 13 }}>{t("adopt.complete.one.action.daily.to.keep.your.streak")}</Text>
              <View style={{ height: 8, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '1F'), overflow: 'hidden' }} data-testid="talent-network-challenge-progress-track" testID="talent-network-challenge-progress-track">
                <View style={{ width: `${Math.max(0, Math.min(100, Number(hub.state.momentum.challenge.progress_pct || 0)))}%`, height: '100%', backgroundColor: colors.primary }} data-testid="talent-network-challenge-progress-fill" testID="talent-network-challenge-progress-fill" />
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }} data-testid="talent-network-challenge-progress-label" testID="talent-network-challenge-progress-label">{t("adopt.challenge")}{hub.state.momentum.challenge.progress}/{hub.state.momentum.challenge.target}
              </Text>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TouchableOpacity onPress={() => { void runCheckIn('daily_visit'); }} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingVertical: 10, alignItems: 'center' }} data-testid="talent-network-checkin-button" testID="talent-network-checkin-button">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{t("adopt.check.in.today")}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { void runCheckIn('profile_update'); void savePreferences(); }} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingVertical: 10, alignItems: 'center' }} data-testid="talent-network-save-prefs-button" testID="talent-network-save-prefs-button">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{savingPrefs ? 'Saving…' : 'Save preference tuning'}</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 18, gap: 10 }} data-testid="talent-network-matches-card" testID="talent-network-matches-card">
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }} data-testid="talent-network-matches-title" testID="talent-network-matches-title">{t("adopt.top.opportunity.matches")}</Text>
              {(hub.top_matches || []).slice(0, 6).map((match, idx) => (
                <View key={`${match.slug}-${idx}`} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 11, gap: 7 }} data-testid={`talent-network-match-row-${idx}`} testID={`talent-network-match-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid={`talent-network-match-title-${idx}`} testID={`talent-network-match-title-${idx}`}>{match.title}</Text>
                      <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 2 }} data-testid={`talent-network-match-meta-${idx}`} testID={`talent-network-match-meta-${idx}`}>{match.department} · {match.location} · {match.type}</Text>
                    </View>
                    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '66'), backgroundColor: (globalThis as any).__alphaColor(colors.primary, '16'), paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`talent-network-match-score-${idx}`} testID={`talent-network-match-score-${idx}`}>
                      <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{match.match_score}{t("adopt.fit")}</Text>
                    </View>
                  </View>

                  <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`talent-network-match-reasons-${idx}`} testID={`talent-network-match-reasons-${idx}`}>
                    {(match.match_reasons || []).join(' • ')}
                  </Text>

                  <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                    <TouchableOpacity
                      onPress={() => {
                        setSavedMatches((prev) => ({ ...prev, [match.slug]: true }));
                        void runCheckIn('save_match');
                      }}
                      style={{ flex: 1, borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, alignItems: 'center', paddingVertical: 8 }}
                      data-testid={`talent-network-save-match-${idx}`}
                      testID={`talent-network-save-match-${idx}`}
                    >
                      <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{savedMatches[match.slug] ? 'Saved' : 'Save match'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => {
                        void runCheckIn('apply');
                        router.push(`/careers?q=${encodeURIComponent(match.title)}&ref=talent-network-hub` as any);
                      }}
                      style={{ flex: 1, borderRadius: 9, backgroundColor: colors.primary, alignItems: 'center', paddingVertical: 8 }}
                      data-testid={`talent-network-apply-match-${idx}`}
                      testID={`talent-network-apply-match-${idx}`}
                    >
                      <Text style={{ color: colors.primaryText || colors.text, fontSize: 11, fontWeight: '800' }}>{t("adopt.explore.role")}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
              <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 16, gap: 10 }} data-testid="talent-network-reminder-center" testID="talent-network-reminder-center">
                <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="talent-network-reminder-title" testID="talent-network-reminder-title">{t("adopt.smart.reminder.center")}</Text>
                <Text style={{ color: colors.textSec, fontSize: 12 }}>{t("adopt.control.your.cadence.and.quiet.window.to.avoid")}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {[
                    { key: 'in_app', label: 'In-app' },
                    { key: 'email', label: 'Email' },
                  ].map((opt) => {
                    const active = reminderChannels.includes(opt.key);
                    return (
                      <TouchableOpacity key={opt.key} onPress={() => toggleValue(opt.key, setReminderChannels)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '14') : colors.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`talent-network-reminder-pill-${opt.key}`} testID={`talent-network-reminder-pill-${opt.key}`}>
                        <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{opt.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <QuietHourInput label="Start" value={quietStart} onChange={setQuietStart} colors={colors} testId="talent-network-reminder-quiet-start" />
                  <QuietHourInput label="End" value={quietEnd} onChange={setQuietEnd} colors={colors} testId="talent-network-reminder-quiet-end" />
                </View>

              <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 10, gap: 6 }} data-testid="talent-network-reminder-timeline-card" testID="talent-network-reminder-timeline-card">
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="talent-network-reminder-timeline-title" testID="talent-network-reminder-timeline-title">{t("adopt.reminder.timeline")}</Text>
                {timelineLoading ? <Text style={{ color: colors.textMuted, fontSize: 10 }}>{t("adopt.loading.timeline")}</Text> : null}
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="talent-network-reminder-next-eta" testID="talent-network-reminder-next-eta">{t("adopt.next.eta")}{timeline?.next_reminder_eta ? new Date(timeline.next_reminder_eta).toLocaleString() : '—'}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="talent-network-reminder-last-digest" testID="talent-network-reminder-last-digest">{t("adopt.last.digest")}{timeline?.last_digest_sent_at ? new Date(timeline.last_digest_sent_at).toLocaleString() : 'Not sent yet'}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="talent-network-reminder-snoozed-until" testID="talent-network-reminder-snoozed-until">{t("adopt.snoozed.until")}{timeline?.snoozed_until ? new Date(timeline.snoozed_until).toLocaleString() : 'Not snoozed'}
                </Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                  {[1, 6, 24].map((hours) => (
                    <TouchableOpacity
                      key={hours}
                      onPress={() => { void runTimelineAction('snooze', hours); }}
                      disabled={timelineActionLoading}
                      style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 10, paddingVertical: 6, opacity: timelineActionLoading ? 0.7 : 1 }}
                      data-testid={`talent-network-reminder-snooze-${hours}h`}
                      testID={`talent-network-reminder-snooze-${hours}h`}
                    >
                      <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}>{t("admin.escalationPanel.auto.text.005")}{hours}h</Text>
                    </TouchableOpacity>
                  ))}
                  <TouchableOpacity
                    onPress={() => { void runTimelineAction('resume'); }}
                    disabled={timelineActionLoading}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.primary, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '14'), paddingHorizontal: 10, paddingVertical: 6, opacity: timelineActionLoading ? 0.7 : 1 }}
                    data-testid="talent-network-reminder-resume-button"
                    testID="talent-network-reminder-resume-button"
                  >
                    <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{timelineActionLoading ? 'Updating…' : 'Resume now'}</Text>
                  </TouchableOpacity>
                </View>

                <View style={{ gap: 5 }} data-testid="talent-network-reminder-history-list" testID="talent-network-reminder-history-list">
                  {(timeline?.history || []).slice(0, 5).map((event, idx) => (
                    <View key={`${event.event_id}-${idx}`} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 9, paddingVertical: 7 }} data-testid={`talent-network-reminder-history-row-${idx}`} testID={`talent-network-reminder-history-row-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{event.event_type} • {event.action || 'event'}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>
                        {event.channel ? `${event.channel.toUpperCase()} • ` : ''}{event.campaign_name || ''}
                      </Text>
                      {event.event_type === 'campaign_delivery' && event.campaign_id ? (
                        <View style={{ flexDirection: 'row', gap: 7, marginTop: 6, flexWrap: 'wrap' }} data-testid={`talent-network-reminder-history-actions-${idx}`} testID={`talent-network-reminder-history-actions-${idx}`}>
                          <TouchableOpacity
                            onPress={() => { void trackCampaignInteraction(event, 'open'); }}
                            disabled={campaignInteractionLoadingKey === `open-${event.event_id || event.campaign_id}`}
                            style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 10, paddingVertical: 5, opacity: campaignInteractionLoadingKey === `open-${event.event_id || event.campaign_id}` ? 0.7 : 1 }}
                            data-testid={`talent-network-reminder-mark-opened-${idx}`}
                            testID={`talent-network-reminder-mark-opened-${idx}`}
                          >
                            <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}>
                              {campaignInteractionLoadingKey === `open-${event.event_id || event.campaign_id}` ? 'Tracking…' : 'Mark opened'}
                            </Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={() => { void trackCampaignInteraction(event, 'click'); }}
                            disabled={campaignInteractionLoadingKey === `click-${event.event_id || event.campaign_id}`}
                            style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.primary, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '14'), paddingHorizontal: 10, paddingVertical: 5, opacity: campaignInteractionLoadingKey === `click-${event.event_id || event.campaign_id}` ? 0.7 : 1 }}
                            data-testid={`talent-network-reminder-open-cta-${idx}`}
                            testID={`talent-network-reminder-open-cta-${idx}`}
                          >
                            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>
                              {campaignInteractionLoadingKey === `click-${event.event_id || event.campaign_id}` ? 'Opening…' : (String(event.meta?.cta_label || '').trim() || 'Open CTA')}
                            </Text>
                          </TouchableOpacity>
                        </View>
                      ) : null}
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>{event.created_at ? new Date(event.created_at).toLocaleString() : '—'}</Text>
                    </View>
                  ))}
                  {(timeline?.history || []).length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 10 }}>{t("adopt.no.reminder.events.yet")}</Text> : null}
                </View>
              </View>
                <TouchableOpacity onPress={() => { void savePreferences(); }} style={{ borderRadius: 9, backgroundColor: colors.primary, alignItems: 'center', paddingVertical: 9 }} data-testid="talent-network-reminder-save" testID="talent-network-reminder-save">
                  <Text style={{ color: colors.primaryText || colors.text, fontSize: 11, fontWeight: '800' }}>{t("adopt.save.reminder.settings")}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 16, gap: 10 }} data-testid="talent-network-referral-card" testID="talent-network-referral-card">
                <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="talent-network-referral-title" testID="talent-network-referral-title">{t("adopt.referral.growth.loop")}</Text>
                <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="talent-network-referral-code" testID="talent-network-referral-code">{t("adopt.your.code")}{hub.state.referral_code || '—'}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="talent-network-referral-points" testID="talent-network-referral-points">{t("adopt.referral.points")}{hub.state.referral_points}{t("adopt.premium.unlock.at.3.points")}</Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {[
                    { key: 'whatsapp', label: 'WhatsApp' },
                    { key: 'x', label: 'X' },
                    { key: 'linkedin', label: 'LinkedIn' },
                    { key: 'copy_link', label: 'Copy Link' },
                  ].map((item) => (
                    <TouchableOpacity key={item.key} onPress={() => { void shareReferral(item.key as any); }} style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`talent-network-share-${item.key}`} testID={`talent-network-share-${item.key}`}>
                      <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{item.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TextInput
                    value={referralInput}
                    onChangeText={setReferralInput}
                    placeholder="Paste referral code"
                    placeholderTextColor={colors.textMuted}
                    style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 9, backgroundColor: colors.bg, color: colors.text, fontSize: 12, paddingHorizontal: 10, paddingVertical: 9, outlineStyle: 'none' as any }}
                    data-testid="talent-network-referral-input"
                    testID="talent-network-referral-input"
                  />
                  <TouchableOpacity onPress={() => { void acceptReferral(); }} style={{ borderRadius: 9, backgroundColor: colors.primary, paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center' }} data-testid="talent-network-accept-referral" testID="talent-network-accept-referral">
                    <Text style={{ color: colors.primaryText || colors.text, fontSize: 11, fontWeight: '800' }}>{t("admin.paymentsTaxPanel.auto.text.019")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: hub.state.premium_unlocked ? (globalThis as any).__alphaColor(colors.success, '66') : colors.border, backgroundColor: hub.state.premium_unlocked ? (globalThis as any).__alphaColor(colors.success, '12') : colors.card, padding: isMobile ? 14 : 18, gap: 7 }} data-testid="talent-network-premium-card" testID="talent-network-premium-card">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="talent-network-premium-title" testID="talent-network-premium-title">{t("adopt.premium.value.layer")}</Text>
              <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="talent-network-premium-status" testID="talent-network-premium-status">
                {hub.state.premium_unlocked
                  ? 'Premium unlocked: priority visibility, advanced fit reasoning, and shortlist digest enabled.'
                  : `Locked: invite ${Math.max(0, 3 - hub.state.referral_points)} more member(s) to unlock premium insights.`}
              </Text>
            </View>
          </>
        ) : null}
      </View>
    </ScrollView>
  );
}

function MetricCard({ title, value, subtitle, icon, colors, testId }: { title: string; value: string; subtitle: string; icon: string; colors: any; testId: string }) {
  return (
    <View style={{ flex: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, gap: 5 }} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{title}</Text>
        <Ionicons name={icon as any} size={13} color={colors.textMuted} />
      </View>
      <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{subtitle}</Text>
    </View>
  );
}

function PreferenceChips({ label, values, selected, onToggle, colors, testPrefix }: { label: string; values: string[]; selected: string[]; onToggle: (value: string) => void; colors: any; testPrefix: string }) {
  return (
    <View style={{ gap: 7 }}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
        {values.map((item) => {
          const active = selected.includes(item);
          return (
            <Pressable key={item} onPress={() => onToggle(item)} style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '16') : colors.bg, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`${testPrefix}-${toSlug(item)}`} testID={`${testPrefix}-${toSlug(item)}`}>
              <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function QuietHourInput({ label, value, onChange, colors, testId }: { label: string; value: string; onChange: (value: string) => void; colors: any; testId: string }) {
  return (
    <View style={{ flex: 1, gap: 5 }}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        keyboardType="numeric"
        placeholder="0-23"
        placeholderTextColor={colors.textMuted}
        style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 9, backgroundColor: colors.bg, color: colors.text, fontSize: 12, paddingHorizontal: 10, paddingVertical: 8, outlineStyle: 'none' as any }}
        data-testid={testId}
        testID={testId}
      />
    </View>
  );
}
