/**
 * /careers  —  RealAICoach Careers Hub (public)
 * Enterprise search & filter + AI-assisted Apply modal.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';

// Native-only keyboard avoidance wrapper for the Apply modal (Fragment on web = zero DOM change).
const KeyboardWrap: any = Platform.OS === 'web' ? React.Fragment : KeyboardAvoidingView;
const keyboardWrapProps: any = Platform.OS === 'web'
  ? {}
  : { behavior: Platform.OS === 'ios' ? 'padding' : undefined, style: { width: '100%', alignItems: 'center', flexShrink: 1 } };
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { trackCareersEvent } from '../src/utils/careersTelemetry';
import { buildAnalyticsSource } from '../src/utils/buildAnalyticsSource';

const API = resolveRuntimeBaseUrl();

type Job = {
  slug: string; title: string; department: string; location: string; type: string; level?: string;
  description: string; requirements: string[]; salary_usd_min?: number; salary_usd_max?: number; hourly_rate_usd?: number;
};
type Facets = { departments: string[]; locations: string[]; types: string[]; total_open: number };
type CareersOverview = {
  total_open: number;
  department_count: number;
  location_count: number;
  featured_roles: Pick<Job, 'slug' | 'title' | 'department' | 'location' | 'type' | 'level'>[];
};

const getRefSource = (): string => {
  if (typeof window === 'undefined') return '';
  try {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get('ref') || params.get('source') || params.get('surface') || '').trim();
  } catch {
    return '';
  }
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

const toTestSlug = (value: string): string => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
const TALENT_ALERT_FREQUENCY_OPTIONS: { value: 'daily' | 'weekly'; label: string; hint: string }[] = [
  { value: 'weekly', label: 'Weekly', hint: 'Recommended: fewer alerts, higher signal.' },
  { value: 'daily', label: 'Daily', hint: 'Get fresh role alerts every day.' },
];

export default function CareersScreen() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const isTablet = width >= 768 && width < 1024;

  const [jobs, setJobs] = useState<Job[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [overview, setOverview] = useState<CareersOverview | null>(null);
  const [q, setQ] = useState('');
  const [department, setDepartment] = useState<string | null>(null);
  const [location, setLocation] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);
  const [applyJob, setApplyJob] = useState<Job | null>(null);
  const [openApp, setOpenApp] = useState(false);
  const refSource = getRefSource();
  const pageIntent = getQueryParam('intent');
  const highlightTalentNetwork = pageIntent === 'talent-network';

  const [talentName, setTalentName] = useState('');
  const [talentEmail, setTalentEmail] = useState('');
  const [talentRoleInterests, setTalentRoleInterests] = useState<string[]>([]);
  const [talentLocations, setTalentLocations] = useState<string[]>([]);
  const [talentWorkTypes, setTalentWorkTypes] = useState<string[]>([]);
  const [talentAlertFrequency, setTalentAlertFrequency] = useState<'daily' | 'weekly'>('weekly');
  const [talentSubmitting, setTalentSubmitting] = useState(false);
  const [talentFeedback, setTalentFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const careersPageSource = useMemo(() => buildAnalyticsSource('careers', 'page'), []);
  const careersTalentNetworkCardSource = useMemo(() => buildAnalyticsSource('careers', 'talent', 'network', 'card'), []);
  const careersHeroSource = useMemo(() => buildAnalyticsSource('careers', 'hero'), []);
  const careersOverviewSource = useMemo(() => buildAnalyticsSource('careers', 'overview'), []);
  const careersToolbarSource = useMemo(() => buildAnalyticsSource('toolbar'), []);
  const careersJobCardSource = useMemo(() => buildAnalyticsSource('job', 'card'), []);
  const careersFooterCtaSource = useMemo(() => buildAnalyticsSource('footer', 'cta'), []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set('q', q.trim());
      if (department) params.set('department', department);
      if (location) params.set('location', location);
      if (type) params.set('type', type);
      const [jobsRes, facetsRes] = await Promise.all([
        fetch(`${API}/api/careers/jobs?${params.toString()}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } }),
        fetch(`${API}/api/careers/facets`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } }),
      ]);
      const overviewPromise = fetch(`${API}/api/careers/overview`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((res) => (res.ok ? res.json() : null))
        .catch(() => null);

      if (!jobsRes.ok || !facetsRes.ok) {
        throw new Error('Unable to load careers data');
      }

      const jr = await jobsRes.json().catch(() => ({} as any));
      const fr = await facetsRes.json().catch(() => ({} as any));
      const ov = await overviewPromise;

      setJobs(Array.isArray(jr?.items) ? jr.items : []);
      setFacets(fr || null);
      setOverview(ov as CareersOverview | null);
      setErr(null);

      await trackCareersEvent({
        event: q || department || location || type ? 'careers_filter_used' : 'careers_job_list_view',
        source: careersPageSource,
        page: '/careers',
        ref: refSource,
        metadata: {
          query: q || '',
          department: department || '',
          location: location || '',
          type: type || '',
          result_count: Array.isArray(jr?.items) ? jr.items.length : 0,
        },
      });
    } catch (error) {
      handleAppRecoverableError({
        scope: 'careers.load',
        error,
        message: t('careers.errors.loadFailed', 'Could not load careers data right now.'),
        setError: (message) => setErr(message),
        onRetry: () => { void load(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setJobs([]);
      setFacets(null);
      setOverview(null);
    } finally { setLoading(false); }
  }, [careersPageSource, q, department, location, type, t, refSource]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    void trackCareersEvent({ event: 'careers_page_view', source: careersPageSource, page: '/careers', ref: refSource });
  }, [careersPageSource, refSource]);

  const kpis = useMemo(() => ({
    total: overview?.total_open || facets?.total_open || 0,
    depts: overview?.department_count || facets?.departments.length || 0,
    locs: overview?.location_count || facets?.locations.length || 0,
  }), [facets, overview]);

  const pad = isMobile ? 16 : isTablet ? 24 : 40;

  const toggleTalentPref = useCallback((value: string, setState: React.Dispatch<React.SetStateAction<string[]>>) => {
    setState((prev) => (prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]));
  }, []);

  const joinTalentNetwork = useCallback(async () => {
    const email = talentEmail.trim().toLowerCase();
    if (!email || !/^\S+@\S+\.\S+$/.test(email)) {
      setTalentFeedback({ type: 'error', text: 'Please enter a valid email address.' });
      return;
    }
    setTalentSubmitting(true);
    setTalentFeedback(null);
    try {
      const res = await fetch(`${API}/api/careers/talent-network/join`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email,
          full_name: talentName.trim(),
          role_interests: talentRoleInterests,
          locations: talentLocations,
          work_types: talentWorkTypes,
          alert_frequency: talentAlertFrequency,
          source: careersTalentNetworkCardSource,
          ref: refSource || pageIntent || '',
        }),
      });
      const payload = await res.json().catch(() => ({} as any));
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || payload?.message || 'Could not join right now');
      }

      setTalentFeedback({
        type: 'success',
        text: payload?.already_joined
          ? 'You are already in our Talent Network. Preferences updated.'
          : 'You’re in! We’ll send matching role alerts to your inbox.',
      });

      await trackCareersEvent({
        event: payload?.already_joined ? 'talent_network_preferences_updated' : 'talent_network_joined',
        source: careersTalentNetworkCardSource,
        page: '/careers',
        ref: refSource || pageIntent || '',
        metadata: {
          has_name: Boolean(talentName.trim()),
          role_interest_count: talentRoleInterests.length,
          location_count: talentLocations.length,
          work_type_count: talentWorkTypes.length,
          alert_frequency: talentAlertFrequency,
        },
      });
    } catch (error: any) {
      setTalentFeedback({ type: 'error', text: String(error?.message || 'Could not join right now. Please try again.') });
    } finally {
      setTalentSubmitting(false);
    }
  }, [careersTalentNetworkCardSource, pageIntent, refSource, talentAlertFrequency, talentEmail, talentLocations, talentName, talentRoleInterests, talentWorkTypes]);

  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try { await load(); } finally { setRefreshing(false); }
  }, [load]);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="careers-page" testID="careers-page" refreshControl={Platform.OS === 'web' ? undefined : <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}>
      {/* Hero */}
      <View style={{ paddingHorizontal: pad, paddingTop: isMobile ? 24 : 56, paddingBottom: isMobile ? 20 : 32, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
        <TouchableOpacity onPress={() => router.push('/')} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }} data-testid="careers-back-home" testID="careers-back-home">
          <Ionicons name="arrow-back" size={16} color={colors.textSec} />
          <Text style={{ color: colors.textSec, marginLeft: 6, fontSize: 13, fontWeight: '600' }}>{t('careers.backHome', 'Back to home')}</Text>
        </TouchableOpacity>
        <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800', letterSpacing: 2, textTransform: 'uppercase' }}>{t('careers.hero.badge', "We're hiring")}</Text>
        <Text style={{ color: colors.text, fontSize: isMobile ? 32 : 48, fontWeight: '800', letterSpacing: -1.2, marginTop: 8, lineHeight: isMobile ? 38 : 54 }}>
          {t('careers.hero.title', 'Build the future of coaching with us.')}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: isMobile ? 15 : 17, lineHeight: isMobile ? 22 : 28, marginTop: 12, maxWidth: 960 }}>
          {t('careers.hero.subtitle', 'Remote-first, outcome-obsessed, and distributed across 48 countries. Help us empower millions of professionals with AI that actually moves careers forward.')}
        </Text>

        <View style={{ marginTop: 16, flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', gap: 10 }}>
          <TouchableOpacity
            onPress={() => {
              void trackCareersEvent({ event: 'careers_track_application_click', source: careersHeroSource, page: '/careers', ref: refSource });
              router.push('/track-application' as any);
            }}
            style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft || colors.card, flexDirection: 'row', alignItems: 'center', gap: 7 }}
            data-testid="careers-track-application-link"
            testID="careers-track-application-link"
          >
            <Ionicons name="locate-outline" size={14} color={colors.textSec} />
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>Track Application</Text>
          </TouchableOpacity>
          {refSource ? (
            <View style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }} data-testid="careers-ref-source-pill" testID="careers-ref-source-pill">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }}>Source: {refSource}</Text>
            </View>
          ) : null}
        </View>

        {err ? (
          <View style={{ marginTop: 14, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '4D'), backgroundColor: (globalThis as any).__alphaColor(colors.error, '14') }} data-testid="careers-load-error-banner" testID="careers-load-error-banner">
            <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{err}</Text>
          </View>
        ) : null}
      </View>

      {overview ? (
        <View style={{ paddingHorizontal: pad, paddingBottom: 8, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: isMobile ? 14 : 18, gap: 12 }} data-testid="careers-overview-panel" testID="careers-overview-panel">
            <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 10 }}>
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>Enterprise Hiring Snapshot</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{overview.total_open} open · {overview.department_count} departments · {overview.location_count} locations</Text>
            </View>
            {Array.isArray(overview.featured_roles) && overview.featured_roles.length > 0 ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {overview.featured_roles.map((role) => (
                  <TouchableOpacity
                    key={role.slug}
                    onPress={() => {
                      setQ(role.title || '');
                      void trackCareersEvent({ event: 'careers_featured_role_click', source: careersOverviewSource, page: '/careers', ref: refSource, job_slug: role.slug });
                    }}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.bgSoft || 'transparent' }}
                    data-testid={`careers-featured-role-${role.slug}`}
                    testID={`careers-featured-role-${role.slug}`}
                  >
                    <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{role.title}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
          </View>
        </View>
      ) : null}

      <View style={{ paddingHorizontal: pad, paddingBottom: 10, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
        <View
          style={{
            borderRadius: 16,
            borderWidth: 1,
            borderColor: highlightTalentNetwork ? colors.primary : colors.border,
            backgroundColor: colors.card,
            padding: isMobile ? 14 : 18,
            gap: 12,
            shadowColor: highlightTalentNetwork ? colors.primary : 'transparent',
            shadowOpacity: highlightTalentNetwork ? 0.14 : 0,
            shadowRadius: 14,
            shadowOffset: { width: 0, height: 6 },
          }}
          data-testid="careers-talent-network-card"
          testID="careers-talent-network-card"
        >
          <View style={{ gap: 6 }}>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>Join Talent Network</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20 }}>
              One-click signup for role alerts. Tell us your preferences and we’ll send matching opportunities.
            </Text>
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <TextInput
              value={talentName}
              onChangeText={setTalentName}
              placeholder="Full name (optional)"
              placeholderTextColor={colors.textMuted}
              style={{
                flex: 1,
                borderWidth: 1,
                borderColor: colors.border,
                borderRadius: 10,
                paddingHorizontal: 12,
                paddingVertical: 10,
                color: colors.text,
                fontSize: 13,
                backgroundColor: colors.bg,
              }}
              data-testid="careers-talent-network-name-input"
              testID="careers-talent-network-name-input"
            />
            <TextInput
              value={talentEmail}
              onChangeText={setTalentEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              placeholder="you@company.com"
              placeholderTextColor={colors.textMuted}
              style={{
                flex: 1,
                borderWidth: 1,
                borderColor: colors.border,
                borderRadius: 10,
                paddingHorizontal: 12,
                paddingVertical: 10,
                color: colors.text,
                fontSize: 13,
                backgroundColor: colors.bg,
              }}
              data-testid="careers-talent-network-email-input"
              testID="careers-talent-network-email-input"
            />
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>Role interests</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(facets?.departments || []).slice(0, 8).map((item) => {
                const active = talentRoleInterests.includes(item);
                const slug = toTestSlug(item);
                return (
                  <TouchableOpacity
                    key={item}
                    onPress={() => toggleTalentPref(item, setTalentRoleInterests)}
                    style={{ borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '1A') : colors.bg, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid={`careers-talent-role-chip-${slug}`}
                    testID={`careers-talent-role-chip-${slug}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>Preferred location</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(facets?.locations || []).slice(0, 6).map((item) => {
                const active = talentLocations.includes(item);
                const slug = toTestSlug(item);
                return (
                  <TouchableOpacity
                    key={item}
                    onPress={() => toggleTalentPref(item, setTalentLocations)}
                    style={{ borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '1A') : colors.bg, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid={`careers-talent-location-chip-${slug}`}
                    testID={`careers-talent-location-chip-${slug}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>Work type</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(facets?.types || []).slice(0, 5).map((item) => {
                const active = talentWorkTypes.includes(item);
                const slug = toTestSlug(item);
                return (
                  <TouchableOpacity
                    key={item}
                    onPress={() => toggleTalentPref(item, setTalentWorkTypes)}
                    style={{ borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '1A') : colors.bg, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid={`careers-talent-worktype-chip-${slug}`}
                    testID={`careers-talent-worktype-chip-${slug}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>Alert frequency</Text>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
              {TALENT_ALERT_FREQUENCY_OPTIONS.map((option) => {
                const active = talentAlertFrequency === option.value;
                return (
                  <TouchableOpacity
                    key={option.value}
                    onPress={() => setTalentAlertFrequency(option.value)}
                    style={{
                      flex: 1,
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: active ? colors.primary : colors.border,
                      backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '14') : colors.bg,
                      paddingHorizontal: 10,
                      paddingVertical: 10,
                    }}
                    data-testid={`careers-talent-alert-frequency-${option.value}`}
                    testID={`careers-talent-alert-frequency-${option.value}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.text, fontSize: 12, fontWeight: '800' }}>{option.label}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>{option.hint}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', gap: 10 }}>
            <TouchableOpacity
              onPress={() => { void joinTalentNetwork(); }}
              disabled={talentSubmitting}
              style={{ backgroundColor: colors.primary, opacity: talentSubmitting ? 0.7 : 1, borderRadius: 10, paddingHorizontal: 18, paddingVertical: 11, flexDirection: 'row', alignItems: 'center', gap: 8 }}
              data-testid="careers-talent-network-submit"
              testID="careers-talent-network-submit"
            >
              {talentSubmitting ? <ActivityIndicator size="small" color={colors.primaryText || colors.text} /> : <Ionicons name="mail-open-outline" size={14} color={colors.primaryText || colors.text} />}
              <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>{talentSubmitting ? 'Joining…' : 'One-click Join Talent Network'}</Text>
            </TouchableOpacity>
            {talentFeedback ? (
              <Text
                style={{ color: talentFeedback.type === 'success' ? colors.success : colors.error, fontSize: 12, fontWeight: '700', flex: 1 }}
                data-testid="careers-talent-network-feedback"
                testID="careers-talent-network-feedback"
              >
                {talentFeedback.text}
              </Text>
            ) : null}
          </View>
        </View>
      </View>

      {/* Toolbar: stats + search + CTA + filters (all visible, nothing hidden) */}
      <View style={{ paddingHorizontal: pad, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
        <View
          style={{
            borderRadius: 18,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.card,
            padding: isMobile ? 16 : 20,
            gap: 16,
          }}
          data-testid="careers-toolbar" testID="careers-toolbar"
        >
          {/* Stat pills */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <StatPill colors={colors} icon="briefcase-outline" label={t('careers.kpi.openRoles', 'Open roles')} value={kpis.total} testId="careers-kpi-total" />
            <StatPill colors={colors} icon="grid-outline" label={t('careers.kpi.departments', 'Departments')} value={kpis.depts} testId="careers-kpi-depts" />
            <StatPill colors={colors} icon="globe-outline" label={t('careers.kpi.countriesServed', 'Countries served')} value={48} testId="careers-kpi-countries" />
          </View>

          {/* Search + primary CTA */}
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, alignItems: isMobile ? 'stretch' : 'center' }}>
            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, backgroundColor: colors.bg }}>
              <Ionicons name="search" size={16} color={colors.textMuted} />
              <TextInput
                value={q} onChangeText={setQ} placeholder={t('careers.search.placeholder', 'Search titles, departments, skills…')}
                placeholderTextColor={colors.textMuted}
                style={{ flex: 1, paddingVertical: 14, paddingHorizontal: 8, color: colors.text, fontSize: 14, outlineStyle: 'none' as any }}
                data-testid="careers-search-input" testID="careers-search-input"
              />
              {q.length > 0 && (
                <TouchableOpacity onPress={() => setQ('')} style={{ padding: 4 }} data-testid="careers-search-clear" testID="careers-search-clear" accessibilityLabel="Clear search">
                  <Ionicons name="close-circle" size={16} color={colors.textMuted} />
                </TouchableOpacity>
              )}
            </View>
            <TouchableOpacity
              onPress={() => {
                void trackCareersEvent({ event: 'careers_open_application_click', source: careersToolbarSource, page: '/careers', ref: refSource });
                setOpenApp(true);
              }}
              style={{
                backgroundColor: colors.primary,
                paddingHorizontal: 18,
                paddingVertical: 13,
                borderRadius: 12,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
                shadowColor: colors.primary,
                shadowOpacity: 0.3,
                shadowRadius: 12,
                shadowOffset: { width: 0, height: 4 },
              }}
              data-testid="careers-send-open-application" testID="careers-send-open-application"
            >
              <Ionicons name="paper-plane-outline" size={16} color={colors.primaryText || colors.text} />
              <Text style={{ color: colors.primaryText || colors.text, fontSize: 14, fontWeight: '800' }}>
                {isMobile ? t('careers.cta.applyNow', 'Apply now') : t('careers.cta.sendOpenApplication', 'Send Open Application')}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Helper line + clear-all shortcut */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '600' }}>
              {department || location || type
                ? t('careers.helper.filtered', 'Narrowing by your filters — clear any pill to broaden.')
                : t('careers.helper.tip', 'Tip: any role open? Just hit “Apply now” above — we review every submission.')}
            </Text>
            {(department || location || type || q) && (
              <TouchableOpacity
                onPress={() => { setQ(''); setDepartment(null); setLocation(null); setType(null); }}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border }}
                data-testid="careers-clear-all-filters" testID="careers-clear-all-filters"
              >
                <Ionicons name="refresh" size={12} color={colors.textSec} />
                <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{t('careers.actions.clearAllFilters', 'Clear all filters')}</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Filter chip rows — wrap, nothing hidden */}
          {facets && (
            <View style={{ gap: 12 }}>
              <FilterRow label={t('careers.filters.department', 'Department')} options={facets.departments} active={department} onPick={setDepartment} colors={colors} testIdPrefix="careers-dept" />
              <FilterRow label={t('careers.filters.location', 'Location')} options={facets.locations} active={location} onPick={setLocation} colors={colors} testIdPrefix="careers-loc" />
              <FilterRow label={t('careers.filters.type', 'Type')} options={facets.types} active={type} onPick={setType} colors={colors} testIdPrefix="careers-type" />
            </View>
          )}
        </View>
      </View>

      {/* Jobs grid */}
      <View style={{ paddingHorizontal: pad, paddingVertical: 24, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
        <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700', marginBottom: 12, letterSpacing: 0.6, textTransform: 'uppercase' }} data-testid="careers-results-count" testID="careers-results-count">
          {loading ? t('careers.results.loading', 'Loading…') : `${jobs.length} ${t('careers.results.role', 'role')}${jobs.length === 1 ? '' : t('careers.results.rolesSuffix', 's')} ${t('careers.results.matchFilters', 'match your filters')}`}
        </Text>
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
        ) : jobs.length === 0 ? (
          <View style={{ padding: 32, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, alignItems: 'center' }} data-testid="careers-empty" testID="careers-empty">
            <Ionicons name="briefcase-outline" size={28} color={colors.textMuted} />
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700', marginTop: 10 }}>{t('careers.empty.noRolesMatch', 'No roles match.')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 4, textAlign: 'center' }}>{t('careers.empty.tryFewerFilters', 'Try fewer filters, or send us an open application.')}</Text>
            <TouchableOpacity onPress={() => { setQ(''); setDepartment(null); setLocation(null); setType(null); }} style={{ marginTop: 12, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border }} data-testid="careers-clear-filters" testID="careers-clear-filters">
              <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{t('careers.actions.clearFilters', 'Clear filters')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }}>
            {jobs.map((job, i) => (
              <JobCard key={job.slug} job={job} colors={colors} isMobile={isMobile} onApply={() => {
                void trackCareersEvent({ event: 'careers_apply_click', source: careersJobCardSource, page: '/careers', ref: refSource, job_slug: job.slug });
                setApplyJob(job);
              }} idx={i} />
            ))}
          </View>
        )}
      </View>

      {/* Footer CTA */}
      <View style={{ paddingHorizontal: pad, paddingVertical: 48, maxWidth: 1240, width: '100%', alignSelf: 'center' }}>
        <View style={{ borderRadius: 20, padding: isMobile ? 24 : 40, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: 16 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: isMobile ? 20 : 24, fontWeight: '800' }}>{t('careers.footer.noFitTitle', "Don't see the right fit?")}</Text>
            <Text style={{ color: colors.textSec, fontSize: 14, marginTop: 6, lineHeight: 22 }}>{t('careers.footer.noFitSubtitle', 'Send us an open application — our talent team reviews every submission personally.')}</Text>
          </View>
          <TouchableOpacity onPress={() => {
            void trackCareersEvent({ event: 'careers_open_application_click', source: careersFooterCtaSource, page: '/careers', ref: refSource });
            setOpenApp(true);
          }} style={{ backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 14, borderRadius: 12, alignItems: 'center', flexDirection: 'row', gap: 8 }} data-testid="careers-footer-open-application" testID="careers-footer-open-application">
            <Ionicons name="paper-plane-outline" size={16} color={colors.primaryText || colors.text} />
            <Text style={{ color: colors.primaryText || colors.text, fontSize: 14, fontWeight: '800' }}>{t('careers.cta.sendOpenApplication', 'Send Open Application')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Apply modal */}
      {(applyJob || openApp) && (
        <ApplyModal
          job={applyJob}
          onClose={() => { setApplyJob(null); setOpenApp(false); }}
          colors={colors}
          isMobile={isMobile}
        />
      )}
    </ScrollView>
  );
}

// ── Pieces ──────────────────────────────────────────────────────────────

function StatPill({ colors, icon, label, value, testId }: { colors: any; icon: string; label: string; value: number; testId: string }) {
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.bg,
      }}
      data-testid={testId} testID={testId}
    >
      <View style={{ width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: `${colors.primary}18` }}>
        <Ionicons name={icon as any} size={16} color={colors.primary} />
      </View>
      <View>
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.3, lineHeight: 22 }}>{value}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase', marginTop: 2 }}>{label}</Text>
      </View>
    </View>
  );
}

function FilterRow({ label, options, active, onPick, colors, testIdPrefix }: { label: string; options: string[]; active: string | null; onPick: (v: string | null) => void; colors: any; testIdPrefix: string }) {
  if (!options || options.length === 0) return null;
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 }} data-testid={`${testIdPrefix}-row`} testID={`${testIdPrefix}-row`}>
      <View style={{ minWidth: 92, marginRight: 4 }}>
        <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{label}</Text>
      </View>
      <Chip label="All" active={active === null} onPress={() => onPick(null)} colors={colors} testId={`${testIdPrefix}-all`} />
      {options.map((opt) => (
        <Chip key={opt} label={opt} active={active === opt} onPress={() => onPick(opt)} colors={colors} testId={`${testIdPrefix}-${opt.replace(/\W+/g, '-').toLowerCase()}`} />
      ))}
    </View>
  );
}

function Chip({ label, active, onPress, colors, testId }: { label: string; active: boolean; onPress: () => void; colors: any; testId: string }) {
  return (
    <TouchableOpacity onPress={onPress} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? `${colors.primary}18` : 'transparent' }} data-testid={testId} testID={testId}>
      <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 12, fontWeight: '700' }}>{label}</Text>
    </TouchableOpacity>
  );
}

function JobCard({ job, colors, isMobile, onApply, idx }: { job: Job; colors: any; isMobile: boolean; onApply: () => void; idx: number }) {
  const salary = job.salary_usd_min && job.salary_usd_max && job.salary_usd_max > 0
    ? `$${(job.salary_usd_min / 1000).toFixed(0)}k – $${(job.salary_usd_max / 1000).toFixed(0)}k`
    : job.hourly_rate_usd ? `$${job.hourly_rate_usd}/hr` : 'Competitive';
  const cardWidth = isMobile ? '100%' : 'calc(33.333% - 10px)';
  return (
    <View
      style={{ width: cardWidth as any, minHeight: 190, padding: 18, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, gap: 10 }}
      data-testid={`careers-job-card-${job.slug}`} testID={`careers-job-card-${job.slug}`}
    >
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        <Pill label={job.department} colors={colors} />
        <Pill label={job.type} colors={colors} />
        {job.level && <Pill label={job.level} colors={colors} />}
      </View>
      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', letterSpacing: -0.2 }} numberOfLines={2}>{job.title}</Text>
      <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 18 }} numberOfLines={3}>{job.description}</Text>
      <View style={{ flex: 1 }} />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 6 }}>
        <View>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{job.location}</Text>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 2 }}>{salary}</Text>
        </View>
        <TouchableOpacity onPress={onApply} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: colors.primary }} data-testid={`careers-apply-${job.slug}`} testID={`careers-apply-${job.slug}`}>
          <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>Apply</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Pill({ label, colors }: { label: string; colors: any }) {
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.bgSoft || `${colors.primary}10` }}>
      <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</Text>
    </View>
  );
}

// ── Apply Modal with AI Suggest ────────────────────────────────────────

type ServerAttachment = {
  attachment_id: string;
  filename: string;
  size: number;
  content_type: string;
  kind: string;
  url: string;
  created_at?: string;
};

const ATTACH_ACCEPT = '.pdf,.doc,.docx,.txt,.rtf,.png,.jpg,.jpeg,.webp,.gif,.zip,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,application/rtf,image/*,application/zip';
const ATTACH_MAX_FILES = 5;
const ATTACH_MAX_PER_FILE = 10 * 1024 * 1024; // 10 MB
const ATTACH_MAX_TOTAL = 25 * 1024 * 1024;    // 25 MB
const ATTACH_KINDS: { id: string; label: string }[] = [
  { id: 'resume', label: 'Resume' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'cover_letter', label: 'Cover Letter' },
  { id: 'certification', label: 'Certification' },
  { id: 'transcript', label: 'Transcript' },
  { id: 'other', label: 'Other' },
];

const formatBytes = (n: number): string => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
};

const randomDraftToken = (): string => {
  // 16 hex chars matches the server regex /^[a-zA-Z0-9_-]{8,64}$/.
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const buf = new Uint8Array(16);
    crypto.getRandomValues(buf);
    return 'draft_' + Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');
  }
  return 'draft_' + Math.random().toString(36).slice(2, 18) + Date.now().toString(36);
};

function ApplyModal({ job, onClose, colors, isMobile }: { job: Job | null; onClose: () => void; colors: any; isMobile: boolean }) {
  const isOpen = job === null;
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [years, setYears] = useState('');
  const [skills, setSkills] = useState('');
  const [linkedin, setLinkedin] = useState('');
  const [strengths, setStrengths] = useState('');
  const [coverLetter, setCoverLetter] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [variants, setVariants] = useState<{tone: string; text: string}[] | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<{ id: string; role: string; attachment_count?: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Attachment state
  const [draftToken] = useState<string>(() => randomDraftToken());
  const [attachments, setAttachments] = useState<ServerAttachment[]>([]);
  const [attachBusy, setAttachBusy] = useState(false);
  const [attachErr, setAttachErr] = useState<string | null>(null);

  const totalBytes = attachments.reduce((n, a) => n + (a.size || 0), 0);

  const uploadOne = async (file: File, kind: string = 'other'): Promise<ServerAttachment | null> => {
    // Client-side gates (defence-in-depth — server re-validates)
    if (file.size === 0) { setAttachErr(`${file.name}: file is empty.`); return null; }
    if (file.size > ATTACH_MAX_PER_FILE) {
      setAttachErr(`${file.name}: file is too large (${formatBytes(file.size)}). Max 10 MB per file.`);
      return null;
    }
    const form = new FormData();
    form.append('file', file);
    form.append('draft_token', draftToken);
    form.append('kind', kind);
    try {
      const r = await fetch(`${API}/api/careers/apply/attachment`, {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }, body: form,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setAttachErr(d?.detail || `Upload failed (HTTP ${r.status}).`);
        return null;
      }
      return d as ServerAttachment;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'careers.attachment-upload',
        error,
        message: t('careers.errors.uploadFailed', 'Network error while uploading — try again.'),
        setError: (message) => setAttachErr(message),
        onRetry: () => { void uploadOne(file, kind); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return null;
    }
  };

  const addFiles = (files: File[]) => {
    (async () => {
      setAttachErr(null);
      const remaining = ATTACH_MAX_FILES - attachments.length;
      if (remaining <= 0) { setAttachErr(`You can attach up to ${ATTACH_MAX_FILES} files.`); return; }
      const batch = files.slice(0, remaining);
      let runningTotal = totalBytes;
      setAttachBusy(true);
      for (const f of batch) {
        runningTotal += f.size;
        if (runningTotal > ATTACH_MAX_TOTAL) {
          setAttachErr(`Total attachments would exceed ${formatBytes(ATTACH_MAX_TOTAL)}. Remove or compress some files.`);
          break;
        }
        // First upload → assume resume, subsequent → portfolio, rest → other. User can change via the kind selector.
        const defaultKind = attachments.length === 0 ? 'resume' : attachments.length === 1 ? 'portfolio' : 'other';
        const uploaded = await uploadOne(f, defaultKind);
        if (uploaded) {
          setAttachments(prev => [...prev, uploaded]);
        }
      }
      setAttachBusy(false);
    })();
  };

  const pickFiles = () => {
    // Web-only DOM file picker — avoids RN dependency on expo-document-picker.
    if (typeof document === 'undefined') {
      setAttachErr('File picker is only available on web.');
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = ATTACH_ACCEPT;
    input.multiple = true;
    input.onchange = (e: any) => {
      const files: File[] = Array.from(e?.target?.files || []);
      if (files.length > 0) addFiles(files);
    };
    input.click();
  };

  const changeKind = async (attachment_id: string, newKind: string) => {
    // The server stores kind but doesn't expose a PATCH today; we just
    // update the local view so the submit payload reflects user intent.
    // Server-side canonical value remains whatever was uploaded.
    setAttachments(prev => prev.map(a => a.attachment_id === attachment_id ? { ...a, kind: newKind } : a));
  };

  const removeAttachment = async (attachment_id: string) => {
    try {
      await fetch(`${API}/api/careers/apply/attachment/${attachment_id}?draft_token=${encodeURIComponent(draftToken)}`, {
        method: 'DELETE',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
    } catch (error) { handleAppRecoverableError({ scope: 'careers.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAttachments(prev => prev.filter(a => a.attachment_id !== attachment_id));
  };

  const suggest = async () => {
    setAiBusy(true); setErr(null);
    try {
      const r = await fetch(`${API}/api/careers/ai-suggest-cover-letter`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({
          name: name.trim() || undefined,
          role_slug: job?.slug || undefined,
          years_experience: years.trim() || undefined,
          skills: skills.split(',').map(s => s.trim()).filter(Boolean),
          strengths: strengths.trim() || undefined,
        }),
      });
      const d = await r.json();
      setVariants(d.variants || []);
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'careers.suggest',
        error,
        message: 'AI suggest failed — write freely and submit below.',
        setError: (message) => setErr(message),
        onRetry: () => { void suggest(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr('AI suggest failed — write freely and submit below.');
    }
    finally { setAiBusy(false); }
  };

  const submit = async () => {
    if (!name.trim() || !email.trim() || coverLetter.trim().length < 10) {
      setErr('Name, email, and a cover letter (min 10 chars) are required.'); return;
    }
    setSubmitting(true); setErr(null);
    try {
      const r = await fetch(`${API}/api/careers/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({
          name: name.trim(), email: email.trim(),
          role_slug: job?.slug,
          years_experience: years.trim() || undefined,
          linkedin: linkedin.trim() || undefined,
          skills: skills.split(',').map(s => s.trim()).filter(Boolean),
          cover_letter: coverLetter.trim(),
          draft_token: attachments.length > 0 ? draftToken : undefined,
        }),
      });
      if (!r.ok) throw new Error('submit failed');
      const d = await r.json();
      setSubmitted({ id: d.application_id, role: d.role_title, attachment_count: d.attachment_count });
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'careers.submit',
        error,
        message: 'Submit failed. Please try again.',
        setError: (message) => setErr(message),
        onRetry: () => { void submit(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr('Submit failed. Please try again.');
    }
    finally { setSubmitting(false); }
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable onPress={onClose} style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(colors.text, '8C'), alignItems: 'center', justifyContent: isMobile ? 'flex-end' : 'center', padding: isMobile ? 0 : 24 }}>
        <KeyboardWrap {...keyboardWrapProps}>
        <Pressable onPress={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 960, maxHeight: '92%', backgroundColor: colors.card, borderRadius: isMobile ? 20 : 18, borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: 'hidden' }} data-testid="careers-apply-modal" testID="careers-apply-modal">
          <ScrollView contentContainerStyle={{ padding: 22 }} keyboardShouldPersistTaps="handled">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' }}>{isOpen ? 'Open Application' : job?.department}</Text>
                <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800', marginTop: 4 }}>{isOpen ? 'Tell us about yourself' : `Apply — ${job?.title}`}</Text>
              </View>
              <TouchableOpacity onPress={onClose} style={{ padding: 8 }} data-testid="careers-apply-close" testID="careers-apply-close">
                <Ionicons name="close" size={22} color={colors.textSec} />
              </TouchableOpacity>
            </View>

            {submitted ? (
              <View style={{ padding: 20, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '33'), backgroundColor: (globalThis as any).__alphaColor((colors.successSoft || colors.success), '14') }} data-testid="careers-apply-success" testID="careers-apply-success">
                <Ionicons name="checkmark-circle" size={32} color={colors.success} />
                <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginTop: 10 }}>Application received!</Text>
                <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, lineHeight: 20 }}>
                  Thanks, {name}. Your application for <Text style={{ fontWeight: '800', color: colors.text }}>{submitted.role}</Text> was received (ID: <Text style={{ fontFamily: 'monospace', color: colors.text }}>{submitted.id}</Text>).{submitted.attachment_count && submitted.attachment_count > 0 ? ` ${submitted.attachment_count} attachment${submitted.attachment_count === 1 ? '' : 's'} included.` : ''} Our talent team will respond within 5 business days.
                </Text>
                <TouchableOpacity onPress={onClose} style={{ marginTop: 16, alignSelf: 'flex-start', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primary }} data-testid="careers-apply-done" testID="careers-apply-done">
                  <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '800' }}>Done</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <>
                <TwoCol isMobile={isMobile}>
                  <Field label="Full name *" value={name} onChange={setName} placeholder="Alex Rivera" colors={colors} testId="careers-apply-name" />
                  <Field label="Email *" value={email} onChange={setEmail} placeholder="alex@example.com" colors={colors} testId="careers-apply-email" />
                </TwoCol>
                <TwoCol isMobile={isMobile}>
                  <Field label="Years of experience" value={years} onChange={setYears} placeholder="e.g. 5" colors={colors} testId="careers-apply-years" />
                  <Field label="LinkedIn URL" value={linkedin} onChange={setLinkedin} placeholder="https://linkedin.com/in/…" colors={colors} testId="careers-apply-linkedin" />
                </TwoCol>
                <Field label="Top skills (comma-separated)" value={skills} onChange={setSkills} placeholder="React, Python, MongoDB, LLMs" colors={colors} testId="careers-apply-skills" />
                <Field label="Unique strengths (optional — helps the AI)" value={strengths} onChange={setStrengths} placeholder="Shipped 3 products from 0→1; built a 100k community; etc." colors={colors} testId="careers-apply-strengths" multiline />

                {/* ── Attachments (resume / portfolio / cover / etc.) ── */}
                <View style={{ marginTop: 6 }} data-testid="careers-apply-attachments" testID="careers-apply-attachments">
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>Attachments (optional)</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{attachments.length}/{ATTACH_MAX_FILES} · {formatBytes(totalBytes)} / {formatBytes(ATTACH_MAX_TOTAL)}</Text>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 8, lineHeight: 16 }}>
                    Add your resume, portfolio, certifications, or transcripts. PDF, DOC(X), TXT, PNG, JPG, or ZIP · up to {formatBytes(ATTACH_MAX_PER_FILE)} each.
                  </Text>

                  {attachments.map((a) => (
                    <View key={a.attachment_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft || 'transparent', marginBottom: 8 }} data-testid={`careers-apply-attachment-${a.attachment_id}`} testID={`careers-apply-attachment-${a.attachment_id}`}>
                      <Ionicons name={a.content_type.startsWith('image/') ? 'image-outline' : a.filename.endsWith('.zip') ? 'archive-outline' : 'document-text-outline'} size={18} color={colors.primary} />
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{a.filename}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>{formatBytes(a.size)} · {a.content_type || 'file'}</Text>
                      </View>
                      {/* Kind picker */}
                      <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' as any, maxWidth: isMobile ? 150 : 220, justifyContent: 'flex-end' }}>
                        {ATTACH_KINDS.slice(0, isMobile ? 3 : 6).map((k) => (
                          <TouchableOpacity
                            key={k.id}
                            onPress={() => changeKind(a.attachment_id, k.id)}
                            style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: a.kind === k.id ? colors.primary : 'transparent', borderWidth: 1, borderColor: a.kind === k.id ? colors.primary : colors.border }}
                            data-testid={`careers-apply-attachment-kind-${a.attachment_id}-${k.id}`} testID={`careers-apply-attachment-kind-${a.attachment_id}-${k.id}`}
                          >
                            <Text style={{ color: a.kind === k.id ? colors.primaryText : colors.textSec, fontSize: 9, fontWeight: '700' }}>{k.label}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                      <TouchableOpacity onPress={() => removeAttachment(a.attachment_id)} style={{ padding: 6 }} data-testid={`careers-apply-attachment-remove-${a.attachment_id}`} testID={`careers-apply-attachment-remove-${a.attachment_id}`}>
                        <Ionicons name="close-circle-outline" size={18} color={colors.error || colors.textMuted} />
                      </TouchableOpacity>
                    </View>
                  ))}

                  <TouchableOpacity
                    onPress={pickFiles}
                    disabled={attachBusy || attachments.length >= ATTACH_MAX_FILES}
                    style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderStyle: 'dashed', borderColor: (globalThis as any).__alphaColor(colors.primary, '66'), backgroundColor: (globalThis as any).__alphaColor(colors.primary, '0A'), opacity: attachBusy || attachments.length >= ATTACH_MAX_FILES ? 0.5 : 1 }}
                    data-testid="careers-apply-attachment-add" testID="careers-apply-attachment-add"
                  >
                    {attachBusy ? <ActivityIndicator size="small" color={colors.primary} /> : <Ionicons name="cloud-upload-outline" size={16} color={colors.primary} />}
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>
                      {attachBusy ? 'Uploading…' : attachments.length >= ATTACH_MAX_FILES ? `${ATTACH_MAX_FILES} files attached` : attachments.length === 0 ? 'Attach files (resume, portfolio…)' : 'Add another file'}
                    </Text>
                  </TouchableOpacity>

                  {attachErr && (
                    <View style={{ marginTop: 8, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '33'), backgroundColor: (globalThis as any).__alphaColor(colors.error, '10') }} data-testid="careers-apply-attachment-error" testID="careers-apply-attachment-error">
                      <Text style={{ color: colors.error, fontSize: 11 }}>{attachErr}</Text>
                    </View>
                  )}
                </View>

                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14, marginBottom: 6 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>Cover letter *</Text>
                  <TouchableOpacity onPress={suggest} disabled={aiBusy} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '66'), backgroundColor: (globalThis as any).__alphaColor(colors.primary, '14'), opacity: aiBusy ? 0.6 : 1 }} data-testid="careers-apply-ai-suggest" testID="careers-apply-ai-suggest">
                    {aiBusy ? <ActivityIndicator size="small" color={colors.primary} /> : <Ionicons name="sparkles" size={13} color={colors.primary} />}
                    <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{aiBusy ? 'Thinking…' : 'Suggest with AI'}</Text>
                  </TouchableOpacity>
                </View>
                {variants && variants.length > 0 && (
                  <View style={{ gap: 8, marginBottom: 10 }} data-testid="careers-apply-ai-variants" testID="careers-apply-ai-variants">
                    {variants.map((v, i) => (
                      <TouchableOpacity key={i} onPress={() => setCoverLetter(v.text)} style={{ padding: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft || 'transparent' }} data-testid={`careers-apply-ai-variant-${i}`} testID={`careers-apply-ai-variant-${i}`}>
                        <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 4 }}>{v.tone} · Tap to use</Text>
                        <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }} numberOfLines={4}>{v.text}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
                <TextInput
                  value={coverLetter} onChangeText={setCoverLetter} multiline
                  placeholder="Why you, why this role, why RealAICoach…"
                  placeholderTextColor={colors.textMuted}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 12, minHeight: 140, color: colors.text, backgroundColor: colors.bgSoft || colors.bg, fontSize: 13, lineHeight: 20, textAlignVertical: 'top' as any }}
                  data-testid="careers-apply-cover-letter" testID="careers-apply-cover-letter"
                />

                {err && (
                  <View style={{ marginTop: 10, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '33'), backgroundColor: (globalThis as any).__alphaColor(colors.error, '14') }} data-testid="careers-apply-error" testID="careers-apply-error">
                    <Text style={{ color: colors.error, fontSize: 12 }}>{err}</Text>
                  </View>
                )}

                <TouchableOpacity onPress={submit} disabled={submitting} style={{ marginTop: 16, paddingVertical: 14, borderRadius: 12, backgroundColor: colors.primary, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8, opacity: submitting ? 0.6 : 1 }} data-testid="careers-apply-submit" testID="careers-apply-submit">
                  {submitting ? <ActivityIndicator color={colors.primaryText} /> : <Ionicons name="paper-plane-outline" size={15} color={colors.primaryText} />}
                  <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '800' }}>{submitting ? 'Submitting…' : 'Submit application'}</Text>
                </TouchableOpacity>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 10, textAlign: 'center' }}>By submitting you agree to our privacy policy. We respond within 5 business days.</Text>
              </>
            )}
          </ScrollView>
        </Pressable>
        </KeyboardWrap>
      </Pressable>
    </Modal>
  );
}

function TwoCol({ children, isMobile }: { children: React.ReactNode; isMobile: boolean }) {
  return <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>{children}</View>;
}

function Field({ label, value, onChange, placeholder, colors, testId, multiline }: { label: string; value: string; onChange: (v: string) => void; placeholder: string; colors: any; testId: string; multiline?: boolean }) {
  return (
    <View style={{ flex: 1, marginBottom: 10 }}>
      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{label}</Text>
      <TextInput
        value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted}
        multiline={multiline}
        style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: multiline ? 10 : 11, color: colors.text, backgroundColor: colors.bgSoft || colors.bg, fontSize: 13, minHeight: multiline ? 70 : undefined, textAlignVertical: (multiline ? 'top' : 'center') as any }}
        autoCapitalize="none" autoCorrect={false}
        data-testid={testId} testID={testId}
      />
    </View>
  );
}
