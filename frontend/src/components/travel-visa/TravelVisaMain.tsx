import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import CountryFlag from '../CountryFlag';
import { router, useLocalSearchParams } from 'expo-router';

import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';
import TravelVisaCoach from './TravelVisaCoach';
import TravelVisaInterviewSim from './TravelVisaInterviewSim';
import TravelVisaQuiz from './TravelVisaQuiz';
import TravelVisaEmbassyDir from './TravelVisaEmbassyDir';
import TravelVisaLeaderboard from './TravelVisaLeaderboard';
import TravelVisaChallenge from './TravelVisaChallenge';
import TravelVisaNotifications from './TravelVisaNotifications';
import TravelVisaMedia from './TravelVisaMedia';
import TravelVisaOnboarding from './TravelVisaOnboarding';
import TravelVisaProgressDashboard from './TravelVisaProgressDashboard';
import TravelVisaCertificates from './TravelVisaCertificates';
import TravelVisaUpgradePrompt from './TravelVisaUpgradePrompt';
import TravelVisaCountryTrack from './TravelVisaCountryTrack';

type TabKey = 'explore' | 'progress' | 'certificates' | 'media' | 'coach' | 'interview' | 'quiz' | 'challenge' | 'embassy' | 'leaderboard' | 'notifications';

type BootstrapPayload = {
  countries: any[];
  regions: string[];
  categories: any[];
  category_groups: string[];
  trending: any[];
  user_stats: any;
  subscription: any;
  system_health: any;
};

const WEB_TRANSITION = Platform.OS === 'web'
  ? ({ transitionProperty: 'transform,opacity,background-color,border-color', transitionDuration: '180ms', transitionTimingFunction: 'ease' } as any)
  : {};

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: 'explore', label: 'Explore', icon: 'compass-outline' },
  { key: 'progress', label: 'Progress', icon: 'trophy-outline' },
  { key: 'certificates', label: 'Certificates', icon: 'ribbon-outline' },
  { key: 'media', label: 'Video/Audio', icon: 'play-circle-outline' },
  { key: 'coach', label: 'AI Coach', icon: 'chatbubble-ellipses-outline' },
  { key: 'interview', label: 'Interview Sim', icon: 'videocam-outline' },
  { key: 'quiz', label: 'Quizzes', icon: 'help-circle-outline' },
  { key: 'challenge', label: 'Challenge', icon: 'flash-outline' },
  { key: 'embassy', label: 'Embassies', icon: 'business-outline' },
  { key: 'leaderboard', label: 'Leaderboard', icon: 'podium-outline' },
  { key: 'notifications', label: 'Alerts', icon: 'notifications-outline' },
];

function toText(v: any) {
  if (v === null || v === undefined) return '';
  return String(v);
}

export default function TravelVisaMain() {
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 960;
  const shell = { width: '100%' as const, maxWidth: 1240, alignSelf: 'center' as const };
  const kpiCard = { flexGrow: 1, flexBasis: (isMobile ? '45%' : '22%') as any, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 };
  const countryCardWidth = width < 560 ? '100%' : width < 960 ? '47.8%' : '31.5%';

  const [activeTab, setActiveTab] = useState<TabKey>('explore');
  const [authChecked, setAuthChecked] = useState(false);
  const [authUserId, setAuthUserId] = useState('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pageError, setPageError] = useState('');
  const [sectionWarning, setSectionWarning] = useState('');

  // Onboarding & Upgrade state
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingComplete, setOnboardingComplete] = useState(false);
  const [upgradePromptVisible, setUpgradePromptVisible] = useState(false);
  const [upgradePromptTrigger, setUpgradePromptTrigger] = useState<'daily_limit' | 'locked_content' | 'feature_teaser' | 'quiz_limit'>('feature_teaser');

  const [countries, setCountries] = useState<any[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [dailyLessons, setDailyLessons] = useState<any[]>([]);
  const [userStats, setUserStats] = useState<any>(null);
  const [subInfo, setSubInfo] = useState<any>(null);
  const [systemHealth, setSystemHealth] = useState<any>(null);

  const [selectedRegion, setSelectedRegion] = useState<string>('');
  const [selectedCategoryGroup, setSelectedCategoryGroup] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const params = useLocalSearchParams<{ country?: string | string[] }>();
  const [selectedCountryCode, setSelectedCountryCode] = useState('');

  useEffect(() => {
    const raw = Array.isArray(params.country) ? params.country[0] : params.country;
    setSelectedCountryCode(toText(raw).trim().toUpperCase());
  }, [params.country]);

  const openCountryTrack = useCallback((code: string) => {
    const normalized = toText(code).trim().toUpperCase();
    if (!normalized) return;
    setSelectedCountryCode(normalized);
    try { router.setParams({ country: normalized }); } catch { /* param sync best-effort */ }
  }, []);

  const closeCountryTrack = useCallback(() => {
    setSelectedCountryCode('');
    try { router.setParams({ country: '' }); } catch { /* param sync best-effort */ }
  }, []);

  const onboardingStateKey = useMemo(() => {
    if (!authUserId) return '';
    return `travel-visa-onboarding-complete:${authUserId}`;
  }, [authUserId]);

  const plan = toText(subInfo?.plan || 'free').toLowerCase();
  const readinessScore = Number(userStats?.readiness_score || 0);

  const groupedCategories = useMemo(() => {
    const grouped: Record<string, any[]> = {};
    categories.forEach((cat: any) => {
      const key = toText(cat.group || 'Other');
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(cat);
    });
    return grouped;
  }, [categories]);

  const regionFilteredCountries = useMemo(() => {
    const list = !selectedRegion ? countries : countries.filter((c: any) => toText(c.region) === selectedRegion);
    return [...list].sort((a: any, b: any) => Number(!!b.popular) - Number(!!a.popular));
  }, [countries, selectedRegion]);

  const filteredCategoryGroups = useMemo(() => {
    if (!selectedCategoryGroup) return Object.entries(groupedCategories);
    return Object.entries(groupedCategories).filter(([group]) => group === selectedCategoryGroup);
  }, [groupedCategories, selectedCategoryGroup]);

  const checkAuth = useCallback(async () => {
    setAuthChecked(false);
    if (user?.user_id) {
      setAuthUserId(user.user_id);
      setAuthChecked(true);
      return;
    }

    try {
      const me = await api.get('/auth/me', { silentLoading: true });
      const uid = toText(me?.data?.user_id || me?.data?.id);
      if (uid) {
        setAuthUserId(uid);
      } else {
        setAuthUserId('');
      }
    } catch {
      setAuthUserId('');
    }
    setAuthChecked(true);
  }, [user?.user_id]);

  const loadBootstrap = useCallback(async (uid: string, isManual = false) => {
    if (!uid) return;
    if (isManual) setRefreshing(true);
    else setLoading(true);
    setPageError('');
    setSectionWarning('');

    try {
      const [bootstrapRes, dailyRes] = await Promise.allSettled([
        api.get(`/travel-visa/bootstrap/${uid}`, { silentLoading: true }),
        api.get('/travel-visa/daily-lessons', { silentLoading: true }),
      ]);

      if (bootstrapRes.status === 'fulfilled' && bootstrapRes.value?.data) {
        const payload = bootstrapRes.value.data as BootstrapPayload;
        setCountries(payload.countries || []);
        setRegions(payload.regions || []);
        setCategories(payload.categories || []);
        setTrending(payload.trending || []);
        setUserStats(payload.user_stats || null);
        setSubInfo(payload.subscription || null);
        setSystemHealth(payload.system_health || null);
      } else {
        const fallback = await Promise.all([
          api.get('/travel-visa/countries', { silentLoading: true }),
          api.get('/travel-visa/categories', { silentLoading: true }),
          api.get('/travel-visa/trending', { silentLoading: true }),
          api.get(`/travel-visa/progress/${uid}`, { silentLoading: true }),
          api.get(`/travel-visa/subscription/info/${uid}`, { silentLoading: true }),
        ]);

        setCountries(fallback[0].data?.countries || []);
        setRegions(fallback[0].data?.regions || []);
        setCategories(fallback[1].data?.categories || []);
        setTrending(fallback[2].data?.trending || []);
        setUserStats(fallback[3].data?.stats || null);
        setSubInfo(fallback[4].data || null);
        setSystemHealth({});
        setSectionWarning(tx('travelVisa.errors.compatibilityMode', 'Travel Visa is running in compatibility mode; enhanced bootstrap data is temporarily unavailable.'));
      }

      if (dailyRes.status === 'fulfilled') {
        setDailyLessons(dailyRes.value?.data?.lessons || []);
      } else {
        setDailyLessons([]);
      }
    } catch (e: any) {
      setPageError(e?.response?.data?.detail || tx('travelVisa.errors.bootstrapFailed', 'Travel Visa failed to load. Please retry.'));
    }

    if (isManual) setRefreshing(false);
    else setLoading(false);
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (!authChecked) return;
    if (!authUserId) {
      setLoading(false);
      return;
    }
    void loadBootstrap(authUserId, false);
  }, [authChecked, authUserId, loadBootstrap]);

  useEffect(() => {
    if (!authUserId || !onboardingStateKey) {
      setOnboardingComplete(false);
      setShowOnboarding(false);
      return;
    }

    let completed = false;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        completed = window.localStorage.getItem(onboardingStateKey) === '1';
      } catch {
        completed = false;
      }
    }

    setOnboardingComplete(completed);
    setShowOnboarding(!completed);
  }, [authUserId, onboardingStateKey]);

  const persistOnboardingComplete = useCallback(() => {
    if (!onboardingStateKey) return;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(onboardingStateKey, '1');
      } catch {
        // no-op; onboarding still closes for this session
      }
    }
  }, [onboardingStateKey]);

  const runSearch = useCallback(async () => {
    if (!authUserId) return;
    if (searchQuery.trim().length < 2) {
      setSearchResults(null);
      return;
    }
    setSearchLoading(true);
    try {
      const res = await api.get(`/travel-visa/search?q=${encodeURIComponent(searchQuery.trim())}`, { silentLoading: true });
      setSearchResults(res.data || null);
    } catch {
      setSectionWarning(tx('travelVisa.errors.searchUnavailable', 'Search is temporarily unavailable. Please retry shortly.'));
      setSearchResults({ countries: [], categories: [], lessons: [], embassies: [] });
    }
    setSearchLoading(false);
  }, [authUserId, searchQuery]);

  useEffect(() => {
    const timer = setTimeout(() => { void runSearch(); }, 360);
    return () => clearTimeout(timer);
  }, [runSearch]);

  const renderExplore = () => (
    <View data-testid="tv-v2-explore-panel" testID="tv-v2-explore-panel" style={{ padding: isMobile ? 14 : 20, gap: 14, ...shell }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View data-testid="tv-v2-kpi-countries" testID="tv-v2-kpi-countries" style={kpiCard}>
          <Text style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', fontWeight: '700' }}>{tx('travelVisa.kpi.countries', 'Countries')}</Text>
          <Text style={{ fontSize: 22, color: colors.text, fontWeight: '800', marginTop: 6 }}>{countries.length}</Text>
        </View>
        <View data-testid="tv-v2-kpi-categories" testID="tv-v2-kpi-categories" style={kpiCard}>
          <Text style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', fontWeight: '700' }}>{tx('travelVisa.kpi.categories', 'Categories')}</Text>
          <Text style={{ fontSize: 22, color: colors.text, fontWeight: '800', marginTop: 6 }}>{categories.length}</Text>
        </View>
        <View data-testid="tv-v2-kpi-readiness" testID="tv-v2-kpi-readiness" style={kpiCard}>
          <Text style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', fontWeight: '700' }}>{tx('travelVisa.kpi.readiness', 'Readiness')}</Text>
          <Text style={{ fontSize: 22, color: colors.text, fontWeight: '800', marginTop: 6 }}>{`${readinessScore}%`}</Text>
        </View>
        <View data-testid="tv-v2-kpi-plan" testID="tv-v2-kpi-plan" style={kpiCard}>
          <Text style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', fontWeight: '700' }}>{tx('travelVisa.kpi.plan', 'Plan')}</Text>
          <Text style={{ fontSize: 18, color: colors.primary, fontWeight: '800', marginTop: 8, textTransform: 'uppercase' }}>{plan}</Text>
        </View>
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.filters.region', 'Region Filter')}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={{ flexDirection: 'row', gap: 7 }}>
            <TouchableOpacity
              data-testid="tv-v2-region-all"
              onPress={() => setSelectedRegion('')}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: !selectedRegion ? colors.primary : colors.border, backgroundColor: !selectedRegion ? colors.primarySoft : colors.surfaceHover }}
            >
              <Text style={{ fontSize: 11, color: !selectedRegion ? colors.primary : colors.textSec, fontWeight: '700' }}>{tx('travelVisa.filters.allRegions', 'All Regions')}</Text>
            </TouchableOpacity>
            {regions.map((region) => (
              <TouchableOpacity
                data-testid={`tv-v2-region-${region.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                key={region}
                onPress={() => setSelectedRegion(region)}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: selectedRegion === region ? colors.primary : colors.border, backgroundColor: selectedRegion === region ? colors.primarySoft : colors.surfaceHover, ...WEB_TRANSITION }}
              >
                <Text style={{ fontSize: 11, color: selectedRegion === region ? colors.primary : colors.textSec, fontWeight: '700' }}>{region}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.explore.topCountries', 'Top Countries')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {regionFilteredCountries.slice(0, 16).map((country: any) => (
            <TouchableOpacity
              key={country.code}
              data-testid={`tv-v2-country-${String(country.code || '').toLowerCase()}`}
              testID={`tv-v2-country-${String(country.code || '').toLowerCase()}`}
              onPress={() => openCountryTrack(country.code)}
              style={{ width: countryCardWidth, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10, ...WEB_TRANSITION }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <CountryFlag code={country.code} emoji={country.flag} size={13} />
                <Text style={{ fontSize: 12, color: colors.text, fontWeight: '700', flexShrink: 1, flex: 1 }}>{toText(country.name)}</Text>
                <Ionicons name="chevron-forward" size={13} color={colors.textMuted} />
              </View>
              <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }}>{`${country.region || '-'} • ${country.difficulty || 'medium'} difficulty`}</Text>
              <Text style={{ fontSize: 10, color: colors.textSec, marginTop: 5 }} numberOfLines={2}>{toText((country.visa_types || []).slice(0, 2).join(' · '))}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.explore.trendingDestinations', 'Trending Destinations')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {trending.slice(0, 9).map((item: any, idx: number) => (
            <TouchableOpacity
              key={`trend-${idx}`}
              data-testid={`tv-v2-trending-${String(item.code || idx).toLowerCase()}`}
              onPress={() => openCountryTrack(item.code)}
              disabled={!item.code}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '44'), backgroundColor: colors.successSoft, ...WEB_TRANSITION }}
            >
              <CountryFlag code={item.code} emoji={item.flag} size={11} />
              <Text style={{ fontSize: 11, color: colors.successText, fontWeight: '700' }}>{toText(item.name || item.country || 'Destination')}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
          <Text style={{ flex: 1, fontSize: 13, color: colors.text, fontWeight: '700' }}>{tx('travelVisa.explore.categoryTracks', 'Category Tracks')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity data-testid="tv-v2-group-all" onPress={() => setSelectedCategoryGroup('')} style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: !selectedCategoryGroup ? colors.primary : colors.border, backgroundColor: !selectedCategoryGroup ? colors.primarySoft : colors.surfaceHover }}>
                <Text style={{ fontSize: 10, color: !selectedCategoryGroup ? colors.primary : colors.textSec, fontWeight: '700' }}>{tx('travelVisa.common.all', 'All')}</Text>
              </TouchableOpacity>
              {Object.keys(groupedCategories).slice(0, 8).map((group) => (
                <TouchableOpacity key={group} data-testid={`tv-v2-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} onPress={() => setSelectedCategoryGroup(group)} style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: selectedCategoryGroup === group ? colors.primary : colors.border, backgroundColor: selectedCategoryGroup === group ? colors.primarySoft : colors.surfaceHover }}>
                  <Text style={{ fontSize: 10, color: selectedCategoryGroup === group ? colors.primary : colors.textSec, fontWeight: '700' }}>{group}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        </View>

        <View style={{ gap: 7 }}>
          {filteredCategoryGroups.slice(0, 6).map(([group, list]) => (
            <View key={group} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10 }}>
              <Text style={{ fontSize: 11, color: colors.text, fontWeight: '800', marginBottom: 6 }}>{group}</Text>
              <Text style={{ fontSize: 10, color: colors.textSec }}>{(list as any[]).slice(0, 5).map((c: any) => c.name).join(' • ')}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.explore.dailyLessons', 'Daily Lessons')}</Text>
        {dailyLessons.length === 0 ? (
          <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('travelVisa.explore.dailyLessonsEmpty', 'No daily lessons are currently available. Refresh to regenerate today’s set.')}</Text>
        ) : (
          <View style={{ gap: 8 }}>
            {dailyLessons.slice(0, 5).map((lesson: any, idx: number) => (
              <View key={`${lesson.lesson_id || lesson.title}-${idx}`} data-testid={`tv-v2-daily-lesson-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10 }}>
                <Text style={{ fontSize: 11, color: colors.text, fontWeight: '800' }}>{lesson.title || 'Travel Visa Lesson'}</Text>
                <Text style={{ fontSize: 10, color: colors.textSec, marginTop: 4 }}>{`${lesson.type || 'reading'} • ${lesson.duration_min || 0} min • ${lesson.difficulty || 'medium'}`}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="tv-v2-system-health">
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.systemIntegrity.title', 'System Integrity Snapshot')}</Text>
        <Text style={{ fontSize: 11, color: colors.textSec }}>{`Countries: ${systemHealth?.countries ?? countries.length} | Categories: ${systemHealth?.categories ?? categories.length} | Lessons: ${systemHealth?.lessons ?? '-'} | Quizzes: ${systemHealth?.quizzes ?? '-'}`}</Text>
        <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }}>{tx('travelVisa.systemIntegrity.note', 'Global Travel Visa bootstrap is validated for authenticated sessions only.')}</Text>
      </View>

      {!!searchQuery.trim() && (
        <View data-testid="tv-v2-search-results" style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
          <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.search.results', 'Search Results')}</Text>
          {searchLoading ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Text style={{ fontSize: 11, color: colors.textSec }}>
              {`Countries: ${(searchResults?.countries || []).length} · Categories: ${(searchResults?.categories || []).length} · Lessons: ${(searchResults?.lessons || []).length} · Embassies: ${(searchResults?.embassies || []).length}`}
            </Text>
          )}
        </View>
      )}
    </View>
  );

  if (!authChecked) {
    return (
      <View data-testid="tv-v2-auth-check-loading" style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, marginTop: 10, fontSize: 13 }}>{tx('travelVisa.auth.validating', 'Validating your Travel Visa access...')}</Text>
      </View>
    );
  }

  if (!authUserId) {
    return (
      <View data-testid="tv-v2-auth-required" style={{ padding: 28, margin: 18, borderRadius: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft }}>
        <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.auth.signInRequired', 'Sign in required')}</Text>
        <Text style={{ fontSize: 13, color: colors.textSec, lineHeight: 20, marginBottom: 14 }}>
          {tx('travelVisa.auth.protectedMessage', 'Travel Visa is a protected system feature. Please sign in to load country intelligence, lessons, coaching, and compliance-safe user progress.')}
        </Text>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TouchableOpacity
            data-testid="tv-v2-login-button"
            onPress={() => router.push('/login')}
            style={{ borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10 }}
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('travelVisa.auth.goToLogin', 'Go to Login')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            data-testid="tv-v2-auth-retry-button"
            onPress={() => void checkAuth()}
            style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 14, paddingVertical: 10 }}
          >
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '800' }}>{tx('travelVisa.auth.retryCheck', 'Retry Auth Check')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (loading) {
    return (
      <View data-testid="tv-v2-bootstrap-loading" style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, marginTop: 10, fontSize: 13 }}>{tx('travelVisa.loading.bootstrap', 'Loading Travel Visa system bootstrap...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView data-testid="tv-v2-root" testID="tv-v2-root" style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ paddingBottom: 36 }}>
      <View data-testid="tv-v2-hero" style={{
        padding: isMobile ? 18 : 24,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: darkMode ? colors.surface : colors.primarySoft,
      }}>
        <View style={shell}>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }}>
              <Ionicons name="airplane" size={20} color={colors.primaryText} />
            </View>
            <View>
              <Text style={{ fontSize: isMobile ? 22 : 28, fontWeight: '900', color: colors.text }}>{tx('travelVisa.hero.title', 'Travel Visa')}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{tx('travelVisa.hero.subtitle', 'Global Visa Learning & Interview Readiness Platform')}</Text>
            </View>
          </View>

          <View data-testid="tv-v2-readiness-badge" style={{ borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '66'), backgroundColor: colors.primarySoft, paddingHorizontal: 12, paddingVertical: 7 }}>
            <Text style={{ fontSize: 11, color: colors.primary, fontWeight: '800' }}>{`Readiness ${readinessScore}%`}</Text>
          </View>
        </View>

        <Text style={{ fontSize: 12, color: colors.textSec, marginTop: 12, lineHeight: 18 }}>
          {tx('travelVisa.hero.disclaimer', 'Educational & coaching use only. Always validate country-specific legal requirements from official government sources.')}
        </Text>

        {!!sectionWarning && (
          <View data-testid="tv-v2-section-warning" style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10 }}>
            <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }}>{sectionWarning}</Text>
          </View>
        )}
        {!!pageError && (
          <View data-testid="tv-v2-error" style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10 }}>
            <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
            <TouchableOpacity data-testid="tv-v2-retry-button" onPress={() => void loadBootstrap(authUserId, true)} style={{ borderRadius: 8, backgroundColor: colors.error, paddingHorizontal: 10, paddingVertical: 6, alignSelf: 'flex-start' }}>
              <Text style={{ fontSize: 11, color: colors.buttonText, fontWeight: '800' }}>{tx('travelVisa.actions.retryLoad', 'Retry Load')}</Text>
            </TouchableOpacity>
          </View>
        )}

        <View style={{ marginTop: 12, flexDirection: 'row', gap: 8 }}>
          <View data-testid="tv-v2-search-bar" testID="tv-v2-search-bar" style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 11, borderWidth: 1, borderColor: colors.inputBorder, backgroundColor: colors.input, paddingHorizontal: 12, height: 42 }}>
            <Ionicons name="search" size={16} color={colors.textMuted} />
            <TextInput
              data-testid="tv-v2-search-input"
              testID="tv-v2-search-input"
              placeholder={tx('travelVisa.search.placeholder', 'Search countries, lessons, embassies')}
              placeholderTextColor={colors.placeholder}
              value={searchQuery}
              onChangeText={setSearchQuery}
              style={{ flex: 1, fontSize: 13, color: colors.inputText, ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}) }}
            />
          </View>
          <TouchableOpacity
            data-testid="tv-v2-refresh-button"
            onPress={() => void loadBootstrap(authUserId, true)}
            style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 11, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 12, height: 42, opacity: refreshing ? 0.7 : 1 }}
          >
            {refreshing ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="refresh-outline" size={15} color={colors.textSec} />}
            {!isMobile && <Text style={{ fontSize: 11, color: colors.textSec, fontWeight: '800' }}>{refreshing ? tx('travelVisa.actions.refreshing', 'Refreshing...') : tx('travelVisa.actions.refresh', 'Refresh')}</Text>}
          </TouchableOpacity>
        </View>
        </View>
      </View>

      <View style={shell}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: isMobile ? 14 : 20, paddingTop: 14, gap: 8 }}>
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <TouchableOpacity
              key={tab.key}
              data-testid={`tv-v2-tab-${tab.key}`}
              testID={`tv-v2-tab-${tab.key}`}
              onPress={() => setActiveTab(tab.key)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? colors.primarySoft : colors.surfaceHover, paddingHorizontal: 12, paddingVertical: 8, ...WEB_TRANSITION }}
            >
              <Ionicons name={tab.icon as any} size={14} color={active ? colors.primary : colors.textSec} />
              <Text style={{ fontSize: 11, color: active ? colors.primary : colors.textSec, fontWeight: '800' }}>{tx(`travelVisa.tabs.${tab.key}`, tab.label)}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      </View>

      {activeTab === 'explore' && (selectedCountryCode ? (
        <View style={shell}>
          <TravelVisaCountryTrack
            countryCode={selectedCountryCode}
            userId={authUserId}
            onBack={closeCountryTrack}
            onUpgradePress={(trigger) => {
              setUpgradePromptTrigger(trigger);
              setUpgradePromptVisible(true);
            }}
          />
        </View>
      ) : renderExplore())}
      {activeTab === 'progress' && (
        <View style={shell}>
        <TravelVisaProgressDashboard 
          userStats={userStats} 
          plan={plan}
          onUpgradeClick={() => {
            setUpgradePromptTrigger('feature_teaser');
            setUpgradePromptVisible(true);
          }}
        />
        </View>
      )}
      {activeTab === 'certificates' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaCertificates userId={authUserId} /></View>}
      {activeTab === 'media' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaMedia userId={authUserId} /></View>}
      {activeTab === 'coach' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaCoach userId={authUserId} plan={plan} /></View>}
      {activeTab === 'interview' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaInterviewSim userId={authUserId} plan={plan} countries={countries} /></View>}
      {activeTab === 'quiz' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaQuiz userId={authUserId} plan={plan} /></View>}
      {activeTab === 'challenge' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaChallenge userId={authUserId} plan={plan} /></View>}
      {activeTab === 'embassy' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaEmbassyDir countries={countries} /></View>}
      {activeTab === 'leaderboard' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaLeaderboard userId={authUserId} /></View>}
      {activeTab === 'notifications' && <View style={{ padding: isMobile ? 14 : 20, ...shell }}><TravelVisaNotifications userId={authUserId} /></View>}

      {/* Upgrade Prompt Modal */}
      {upgradePromptVisible && (
        <TravelVisaUpgradePrompt
          visible={upgradePromptVisible}
          onClose={() => setUpgradePromptVisible(false)}
          trigger={upgradePromptTrigger}
          currentPlan={plan}
        />
      )}

      {/* Onboarding Wizard */}
      {showOnboarding && !onboardingComplete && (() => {
        const overlay = (
          <View
            data-testid="tv-v2-onboarding-overlay"
            testID="tv-v2-onboarding-overlay"
            style={{ position: (Platform.OS === 'web' ? 'fixed' : 'absolute') as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 1200 }}
          >
            <TravelVisaOnboarding
              onComplete={(data) => {
                setOnboardingComplete(true);
                setShowOnboarding(false);
                persistOnboardingComplete();
                // Optionally save preferences to backend or localStorage
              }}
              onSkip={() => {
                setOnboardingComplete(true);
                setShowOnboarding(false);
                persistOnboardingComplete();
              }}
            />
          </View>
        );
        if (Platform.OS === 'web' && typeof document !== 'undefined') {
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { createPortal } = require('react-dom');
          return createPortal(overlay, document.body);
        }
        return overlay;
      })()}
    </ScrollView>
  );
}
