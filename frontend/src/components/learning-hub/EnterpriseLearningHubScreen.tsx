import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform, useWindowDimensions, Image, ImageBackground, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
import { useRouter, useLocalSearchParams } from 'expo-router';

import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import api, { ensureAuthTokenLoaded } from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { withCertificatePrintLayout } from '../../utils/certificates';
import { CertificatePrintLayoutModal } from '../certificates/CertificatePrintLayoutModal';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../../utils/adminAccess';
import { MomentumStrip, CinemaHero, CinemaRail, CelebrationOverlay, courseCoverUrl } from './LearningCinema';

/* ─────────── TYPES ─────────── */
type TabId = 'discover' | 'journey' | 'lab' | 'admin';

/* ─────────── CONSTANTS ─────────── */
const CACHE_SCHEMA_VERSION = 'ai-learning-hub-ui-v2-enterprise';
const MENTOR_SELECTION_CACHE_KEY = 'ai-learning-hub-selected-mentor-v1';
const MENTOR_FAVORITES_CACHE_KEY = 'ai-learning-hub-favorite-mentors-v1';
const ACTION_TIMEOUT_MS = 15000;
const HF = Platform.OS === 'web' ? 'Outfit, Chivo, system-ui, sans-serif' : undefined;
const BF = Platform.OS === 'web' ? 'Plus Jakarta Sans, Inter, system-ui, sans-serif' : undefined;
const MF = Platform.OS === 'web' ? 'IBM Plex Mono, monospace' : undefined;


const DIFFICULTIES = ['beginner', 'intermediate', 'advanced'];
const CATEGORIES = ['AI', 'Cybersecurity', 'IT', 'Software', 'Data Science', 'Cloud Computing', 'DevOps', 'Business', 'Marketing', 'Entrepreneurship', 'Project Management', 'Product Management', 'Finance', 'Sales', 'Leadership', 'HR & Talent', 'Design', 'Creative Arts', 'Photography', 'Music', 'Writing & Content', 'Lifestyle', 'Health & Wellness', 'Communication', 'Personal Development'];

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'discover', label: 'Discover', icon: 'compass-outline' },
  { id: 'journey', label: 'My Journey', icon: 'trail-sign-outline' },
  { id: 'lab', label: 'AI Lab', icon: 'flask-outline' },
  { id: 'admin', label: 'Executive', icon: 'analytics-outline' },
];

/* ─────────── HELPERS ─────────── */
const getInitialTab = (): TabId => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'discover';
  try {
    const p = new URLSearchParams(window.location.search || '');
    const t = (p.get('tab') || '').trim() as TabId;
    if (['discover', 'journey', 'lab', 'admin'].includes(t)) return t;
  } catch { /* noop */ }
  return 'discover';
};

const num = (v: any, d = 0) => { const n = Number(v); return Number.isFinite(n) ? n.toFixed(d) : '0'; };
const fmtDur = (s: any) => { const t = Math.max(0, Math.floor(Number(s) || 0)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; };
const normUrl = (u: string) => { const r = String(u || '').trim(); if (!r) return ''; if (r.startsWith('http://') || r.startsWith('https://')) return r; if (r.startsWith('/')) return typeof window !== 'undefined' ? `${window.location.origin}${r}` : r; return `https://${r}`; };
const openExt = async (u: string, onErr: (m: string) => void) => {
  const t = normUrl(u); if (!t) { onErr('Invalid link.'); return; }
  if (Platform.OS === 'web' && typeof window !== 'undefined') { window.open(t, '_blank', 'noopener,noreferrer'); return; }
  try { await Linking.openURL(t); } catch { onErr('Unable to open link.'); }
};

/* ─────────── DESIGN TOKENS ─────────── */
const mkColors = (colors: any, dark: boolean) => ({
  bg: colors.bg,
  surface: colors.surface,
  surfaceHover: colors.surfaceHover,
  card: colors.card,
  cardAlt: colors.surfaceElevated || colors.card,
  border: colors.border,
  borderSoft: colors.borderSoft || colors.border,
  text: colors.text,
  textSec: colors.textSec,
  muted: colors.textMuted,
  primary: colors.primary,
  primaryHover: colors.primaryHover || colors.primary,
  cyan: colors.accent,
  emerald: colors.success,
  amber: colors.warning,
  rose: colors.error,
  warning: colors.warning,
  warningText: colors.warningText,
  error: colors.error,
  successText: colors.successText,
  violet: colors.accent,
  overlay: colors.overlay,
  pillBlueBg: `${colors.primary}15`,
  pillBlueBorder: `${colors.primary}28`,
  pillEmeraldBg: `${colors.success}15`,
  pillEmeraldBorder: `${colors.success}28`,
  pillAmberBg: `${colors.warning}15`,
  pillAmberBorder: `${colors.warning}28`,
  pillRedBg: `${colors.error}15`,
  pillRedBorder: `${colors.error}28`,
  paper: dark ? colors.text : colors.bg,
  soft: colors.surfaceHover,
  success: colors.success,
});

/* ─── Reusable styled primitives ─── */
const SectionCard = ({ children, style, testId }: { children: React.ReactNode; style?: any; testId?: string }) => {
  const { colors, darkMode } = useTheme();
  const C = mkColors(colors, darkMode);
  return (
    <View style={[{ backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, darkMode ? 'A8' : 'D8') : C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 20, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }, style]} data-testid={testId} testID={testId}>
      {children}
    </View>
  );
};

const Pill = ({ label, active, onPress, testId }: { label: string; active?: boolean; onPress?: () => void; testId?: string }) => {
  const { colors, darkMode } = useTheme();
  const C = mkColors(colors, darkMode);
  return (
    <TouchableOpacity
      onPress={onPress}
      style={{ backgroundColor: active ? C.primary : C.surfaceHover, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 6, borderWidth: 1, borderColor: active ? C.primary : C.border }}
      data-testid={testId} testID={testId}
    >
      <Text style={{ color: active ? 'var(--app-primary-text)' : C.textSec, fontSize: 12, fontWeight: '700', fontFamily: BF }}>{label}</Text>
    </TouchableOpacity>
  );
};

const PrimaryBtn = ({ label, onPress, busy, icon, testId, small, style }: { label: string; onPress: () => void; busy?: boolean; icon?: string; testId?: string; small?: boolean; style?: any }) => {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const C = mkColors(colors, darkMode);
  const busyLabel = (() => {
    const value = t('learningHub.common.working');
    return value === 'learningHub.common.working' ? 'Working...' : value;
  })();
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={busy}
      style={[{ backgroundColor: C.primary, borderRadius: 6, paddingHorizontal: small ? 12 : 18, paddingVertical: small ? 8 : 11, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: busy ? 0.6 : 1 }, style]}
      data-testid={testId} testID={testId}
    >
      {icon && <Ionicons name={icon as any} size={small ? 14 : 16} color="var(--app-primary-text)" />}
      <Text style={{ color: colors.primaryText, fontSize: small ? 12 : 13, fontWeight: '800', fontFamily: BF }}>{busy ? busyLabel : label}</Text>
    </TouchableOpacity>
  );
};

const SecondaryBtn = ({ label, onPress, busy, icon, testId, small, style }: { label: string; onPress: () => void; busy?: boolean; icon?: string; testId?: string; small?: boolean; style?: any }) => {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const C = mkColors(colors, darkMode);
  const busyLabel = (() => {
    const value = t('learningHub.common.working');
    return value === 'learningHub.common.working' ? 'Working...' : value;
  })();
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={busy}
      style={[{ backgroundColor: 'transparent', borderRadius: 6, borderWidth: 1, borderColor: C.border, paddingHorizontal: small ? 12 : 16, paddingVertical: small ? 7 : 10, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: busy ? 0.6 : 1 }, style]}
      data-testid={testId} testID={testId}
    >
      {icon && <Ionicons name={icon as any} size={small ? 14 : 16} color={C.textSec} />}
      <Text style={{ color: C.text, fontSize: small ? 12 : 13, fontWeight: '700', fontFamily: BF }}>{busy ? busyLabel : label}</Text>
    </TouchableOpacity>
  );
};

const FieldInput = ({ value, onChangeText, placeholder, multiline, mono, testId }: { value: string; onChangeText: (v: string) => void; placeholder?: string; multiline?: boolean; mono?: boolean; testId?: string }) => {
  const { colors, darkMode } = useTheme();
  const C = mkColors(colors, darkMode);
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={C.muted}
      multiline={multiline}
      style={{
        backgroundColor: C.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: C.border,
        paddingHorizontal: 14, paddingVertical: 10, color: C.text, fontSize: 13, fontFamily: mono ? MF : BF,
        minHeight: multiline ? 72 : undefined,
      }}
      data-testid={testId} testID={testId}
    />
  );
};

const ProgressBar = ({ pct, color }: { pct: number; color?: string }) => {
  const { colors, darkMode } = useTheme();
  const C = mkColors(colors, darkMode);
  return (
    <View style={{ height: 6, backgroundColor: C.surfaceHover, borderRadius: 99, overflow: 'hidden' }}>
      <View style={{ height: '100%', width: `${Math.min(100, Math.max(0, pct))}%`, backgroundColor: color || C.primary, borderRadius: 99 }} />
    </View>
  );
};

/* ═══════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════ */
export const EnterpriseLearningHubScreen = () => {
  const router = useRouter();
  const routeParams = useLocalSearchParams<{ tab?: string; filter?: string; kpi?: string; kpiId?: string }>();
  const { colors, darkMode } = useTheme();
  const { width } = useWindowDimensions();
  const { user, loading: authLoading } = useAuth();
  const { t } = useTranslation();
  const C = useMemo(() => mkColors(colors, darkMode), [colors, darkMode]);
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const isAdmin = hasAdminConsoleVisibility(user as any);
  const isMobile = width < 700;
  const isTablet = width >= 700 && width < 1100;

  /* ─── State ─── */
  const [activeTab, setActiveTab] = useState<TabId>(getInitialTab);
  const [journeyFilter, setJourneyFilter] = useState<'all' | 'active' | 'completed'>('all');
  const [selectedKpiId, setSelectedKpiId] = useState<'streak' | 'active' | 'complete' | 'minutes' | null>(null);
  const [roadmapTimelineMonths, setRoadmapTimelineMonths] = useState(6);
  const [roadmapWeekProgress, setRoadmapWeekProgress] = useState<Record<string, boolean>>({});
  const [assessmentTargetEnrollment, setAssessmentTargetEnrollment] = useState<any | null>(null);
  const [assessmentAnswers, setAssessmentAnswers] = useState<Record<string, number>>({});
  const [assessmentResult, setAssessmentResult] = useState<any | null>(null);
  const [lessonPlayer, setLessonPlayer] = useState<any | null>(null);
  const [celebration, setCelebration] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshingHub, setIsRefreshingHub] = useState(false);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [_lastFreshAt, setLastFreshAt] = useState('');
  const [_cacheSweepDone, setCacheSweepDone] = useState(false);
  const [certificatePrintTarget, setCertificatePrintTarget] = useState<any | null>(null);

  const [dashboard, setDashboard] = useState<any>(null);
  const [courses, setCourses] = useState<any[]>([]);
  const [courseAccessControl, setCourseAccessControl] = useState<any>(null);
  const [center, setCenter] = useState<any>({ enrollments: [], certificates: [], latest_roadmap: null });
  const [papers, setPapers] = useState<any[]>([]);
  const [adminInsights, setAdminInsights] = useState<any>(null);
  const [engagementKpis, setEngagementKpis] = useState<any>(null);
  const [_enterpriseStandard, setEnterpriseStandard] = useState<any>(null);
  const [_sessionTimeoutConfig, setSessionTimeoutConfig] = useState<any>(null);
  const [_sessionTimeoutHistory, setSessionTimeoutHistory] = useState<any[]>([]);
  const [adminSessionHoursInput, setAdminSessionHoursInput] = useState('5');
  const [userSessionHoursInput, setUserSessionHoursInput] = useState('5');
  const [opportunityRadar, setOpportunityRadar] = useState<any>(null);
  const [incomeExperiments, setIncomeExperiments] = useState<any[]>([]);
  const [recoveryCopilot, setRecoveryCopilot] = useState<any>(null);

  const [search, setSearch] = useState('');
  const [courseTopic, setCourseTopic] = useState('');
  const [courseCategory, setCourseCategory] = useState('');
  const [courseDifficulty, setCourseDifficulty] = useState('intermediate');
  const [roadmapRole, setRoadmapRole] = useState('AI Product Manager');
  const [roadmapSkills, setRoadmapSkills] = useState('prompting, analytics, python basics');
  const [sandboxPrompt, setSandboxPrompt] = useState('Build a Python function to detect anomalous transaction spikes.');
  const [sandboxOutput, setSandboxOutput] = useState<any>(null);
  const [mentorObjective, setMentorObjective] = useState('I want to transition into AI Security Architect in 9 months');
  const [mentorMatches, setMentorMatches] = useState<any[]>([]);
  const [selectedMentorId, setSelectedMentorId] = useState('');
  const [favoriteMentorIds, setFavoriteMentorIds] = useState<string[]>([]);
  const [compareMentorIds, setCompareMentorIds] = useState<string[]>([]);
  const [mentorFlowMessage, setMentorFlowMessage] = useState('');
  const [habitLoop, setHabitLoop] = useState<any>(null);
  const [careerSprint, setCareerSprint] = useState<any>(null);
  const [checkInMood, setCheckInMood] = useState(3);
  const [checkInFocus, setCheckInFocus] = useState(3);
  const [checkInBlocker, setCheckInBlocker] = useState('');
  const [checkInCoach, setCheckInCoach] = useState<any>(null);
  const [careerChallengeTitle, setCareerChallengeTitle] = useState('Launch a portfolio project that attracts paid opportunities');
  const [careerObjective, setCareerObjective] = useState('Build a 7-day execution sprint for career growth and income opportunities');
  const [careerContext, setCareerContext] = useState('I can commit 6 focused hours this week and need practical actions.');
  const [careerIncomeGoal, setCareerIncomeGoal] = useState('Secure first paid consulting lead this month');
  const [careerWeeklyHours, setCareerWeeklyHours] = useState('6');
  const [experimentTitle, setExperimentTitle] = useState('AI workflow teardown mini-offer');
  const [experimentHypothesis, setExperimentHypothesis] = useState('Publishing one teardown case study weekly can generate inbound leads');
  const [experimentPlan, setExperimentPlan] = useState('Publish on LinkedIn + send to 10 target founders');
  const [experimentRevenue, _setExperimentRevenue] = useState('0');
  const [experimentInsight, setExperimentInsight] = useState('');
  const playerTickRef = useRef<any>(null);
  const scrollViewRef = useRef<ScrollView>(null);
  const [careerSprintSectionY, setCareerSprintSectionY] = useState(0);

  /* ─── Derived ─── */
  const _plan = dashboard?.entitlements?.plan || dashboard?.access_control?.plan || user?.subscription_plan || 'free';
  const allEnrollments = center?.enrollments || [];
  const completedEnrollments = allEnrollments.filter((r: any) => Boolean(r?.completed));
  const activeEnrollments = allEnrollments.filter((r: any) => !r?.completed);
  const visibleEnrollments = journeyFilter === 'active' ? activeEnrollments : journeyFilter === 'completed' ? completedEnrollments : allEnrollments;
  const displayedActive = allEnrollments.length > 0 ? activeEnrollments.length : Number(dashboard?.engagement?.active_courses || 0);
  const displayedCompleted = allEnrollments.length > 0 ? completedEnrollments.length : Number(dashboard?.engagement?.completed_courses || 0);
  const momentumSummary = habitLoop?.summary || dashboard?.daily_momentum?.habit_loop || center?.habit_loop?.summary || null;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const dailyMissions = momentumSummary?.missions || [];
  const streakMultiplier = Number(momentumSummary?.streak_multiplier || 1).toFixed(2);
  const habitRisk = momentumSummary?.risk?.risk_score ?? '--';
  const habitNudge = momentumSummary?.risk?.nudge || tx('learningHub.momentum.defaultNudge', 'Complete one mission now to protect your momentum.');
  const recoveryRiskLevel = String(recoveryCopilot?.risk?.level || 'low').toLowerCase();
  const activeSprint = careerSprint || dashboard?.daily_momentum?.latest_career_sprint || center?.latest_career_sprint || null;
  const insuranceTokens = Number(momentumSummary?.streak_insurance?.tokens || 0);
  const radarOpportunities = opportunityRadar?.radar?.opportunities || [];
  const activeSprintTitle = String(activeSprint?.plan?.title || activeSprint?.challenge_title || '');
  const activeSprintActions = Array.isArray(activeSprint?.plan?.daily_actions) ? activeSprint.plan.daily_actions : Array.isArray(activeSprint?.plan?.daily_plan) ? activeSprint.plan.daily_plan : [];
  const selectedMentor = useMemo(() => mentorMatches.find((r: any) => r.mentor_id === selectedMentorId) || null, [mentorMatches, selectedMentorId]);
  const sortedMentorMatches = useMemo(() => {
    if (!Array.isArray(mentorMatches)) return [];
    return [...mentorMatches].sort((a: any, b: any) => {
      const aFav = favoriteMentorIds.includes(String(a?.mentor_id || '')) ? 1 : 0;
      const bFav = favoriteMentorIds.includes(String(b?.mentor_id || '')) ? 1 : 0;
      if (aFav !== bFav) return bFav - aFav;
      return Number(b?.score || 0) - Number(a?.score || 0);
    });
  }, [favoriteMentorIds, mentorMatches]);
  const compareMentors = useMemo(
    () => mentorMatches.filter((m: any) => compareMentorIds.includes(String(m?.mentor_id || ''))).slice(0, 3),
    [compareMentorIds, mentorMatches],
  );
  const certificatesByCourse = useMemo(() => { const m: Record<string, any> = {}; (center?.certificates || []).forEach((c: any) => { m[c.course_id] = c; }); return m; }, [center]);
  const coursesById = useMemo(() => { const m: Record<string, any> = {}; courses.forEach((c: any) => { if (c?.course_id) m[c.course_id] = c; }); return m; }, [courses]);
  const hubActionCards = Array.isArray(dashboard?.daily_action_cards) ? dashboard.daily_action_cards : [];
  const onboarding = dashboard?.onboarding || null;
  const onboardingSteps = Array.isArray(onboarding?.steps) ? onboarding.steps : [];
  const onboardingCompleted = Number(onboarding?.completed_steps || 0);
  const onboardingTotal = Number(onboarding?.total_steps || onboardingSteps.length || 0);
  const onboardingPct = Number(onboarding?.completion_pct || 0);
  const nextOnboardingStep = onboardingSteps.find((step: any) => !step?.completed) || null;
  const onboardingRouteFor = (step: any) => {
    const route = String(step?.action?.route || '').trim();
    if (route) return route;
    const tab = String(step?.action?.tab || '').trim();
    return tab ? `/ai-learning-hub?tab=${encodeURIComponent(tab)}` : '/ai-learning-hub';
  };

  const weeklyLoop = dashboard?.weekly_achievement_loop || null;
  const weeklyMissionCards = Array.isArray(weeklyLoop?.mission_cards) ? weeklyLoop.mission_cards : [];
  const weeklyCompletionRewards = Array.isArray(weeklyLoop?.completion_rewards) ? weeklyLoop.completion_rewards : [];
  const weeklyLeaderboardEntries = Array.isArray(weeklyLoop?.leaderboard_teaser?.entries) ? weeklyLoop.leaderboard_teaser.entries : [];
  const weeklyXpEarned = Number(weeklyLoop?.xp?.earned || 0);
  const weeklyXpGoal = Number(weeklyLoop?.xp?.goal || 0);
  const weeklyMinutesEarned = Number(weeklyLoop?.minutes?.earned || 0);
  const weeklyMinutesGoal = Number(weeklyLoop?.minutes?.goal || 0);
  const weeklyMissionsCompleted = Number(weeklyLoop?.missions?.completed || 0);
  const weeklyMissionsGoal = Number(weeklyLoop?.missions?.goal || 0);
  const weeklyBadge = weeklyLoop?.streak_badge || null;
  const weeklyYourRank = weeklyLoop?.leaderboard_teaser?.you?.rank;
  const weeklyNudges = weeklyLoop?.retention_nudges || null;
  const weeklyActivePrompt = weeklyNudges?.active_prompt || null;
  const weeklyUpcomingPrompt = weeklyNudges?.upcoming_prompt || null;
  const weeklyCadence = weeklyNudges?.cadence || null;
  const weeklyMondayPrompt = weeklyNudges?.monday_reset || null;
  const weeklyFridayPrompt = weeklyNudges?.friday_momentum || null;
  const videoQuality = dashboard?.video_quality || null;
  const accessControl = dashboard?.access_control || courseAccessControl || null;
  const entitlements = dashboard?.entitlements || {};
  const planScopeLabel = accessControl?.scope_label || dashboard?.entitlements?.learning_access?.label || (_plan === 'premium' ? 'Full unlimited access' : _plan === 'basic' ? 'Almost unlimited access' : 'Limited access');
  const entitlementCaps = {
    course: entitlements?.course_generation?.daily_limit,
    roadmap: entitlements?.roadmap_generation?.daily_limit,
    sandbox: entitlements?.sandbox?.daily_limit,
    mentor: entitlements?.mentor_matching?.daily_limit,
  };
  const certificatesEnabled = Boolean(entitlements?.certificates?.enabled);
  const showUpgradeNudge = _plan !== 'premium';
  const formatCap = useCallback((v: any) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    return n < 0 ? '∞' : String(n);
  }, []);

  /* ─── Data Loading ─── */
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') { setCacheSweepDone(true); return; }
    try { const prev = window.localStorage.getItem('ai-learning-hub-cache-schema'); if (prev !== CACHE_SCHEMA_VERSION) { Object.keys(window.localStorage).filter(k => k.startsWith('ai-learning-hub-legacy-') || k.startsWith('ai-learning-hub-cache-')).forEach(k => window.localStorage.removeItem(k)); window.localStorage.setItem('ai-learning-hub-cache-schema', CACHE_SCHEMA_VERSION); } } catch { /* noop */ } finally { setCacheSweepDone(true); }
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(MENTOR_FAVORITES_CACHE_KEY);
      const ids = raw ? JSON.parse(raw) : [];
      setFavoriteMentorIds(Array.isArray(ids) ? ids.map((id: any) => String(id)) : []);
    } catch {
      setFavoriteMentorIds([]);
    }
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(MENTOR_FAVORITES_CACHE_KEY, JSON.stringify(favoriteMentorIds.slice(0, 20)));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/learning-hub/EnterpriseLearningHubScreen.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [favoriteMentorIds]);

  const loadDashboard = useCallback(async () => { const r = await api.get('/ai-learn/hub-dashboard'); setDashboard(r.data || null); }, []);
  const loadCourses = useCallback(async () => {
    const r = await api.get('/ai-learn/courses', { params: { search: search.trim() || undefined } });
    setCourses(r.data?.courses || []);
    setCourseAccessControl(r.data?.access_control || null);
  }, [search]);
  const loadCenter = useCallback(async () => { const r = await api.get('/ai-learn/my-learning-center'); setCenter(r.data || { enrollments: [], certificates: [], latest_roadmap: null }); }, []);
  const loadPapers = useCallback(async () => { const r = await api.get('/ai-learn/papers/latest'); setPapers(r.data?.papers || []); }, []);
  const loadAdmin = useCallback(async () => {
    if (!isAdmin) return;
    const [a, b, c, d, e] = await Promise.all([api.get('/ai-learn/admin/executive-insights'), api.get('/ai-learn/admin/engagement-kpis'), api.get('/admin/platform-health/enterprise-standard/status'), api.get('/auth/admin/session-timeout-config'), api.get('/auth/admin/session-timeout-config/history', { params: { limit: 12 } })]);
    setAdminInsights(a.data || null); setEngagementKpis(b.data || null); setEnterpriseStandard(c.data || null); setSessionTimeoutConfig(d.data || null);
    setAdminSessionHoursInput(String(d.data?.admin_hours ?? '5')); setUserSessionHoursInput(String(d.data?.user_hours ?? '5'));
    setSessionTimeoutHistory(e.data?.history || []);
  }, [isAdmin]);
  const loadHabitLoop = useCallback(async () => { const r = await api.get('/ai-learn/habit-loop/summary'); setHabitLoop(r.data || null); }, []);
  const loadCareerSprint = useCallback(async () => { const r = await api.get('/ai-learn/career-sprints/latest'); setCareerSprint(r.data?.sprint || null); }, []);
  const loadOpportunityRadar = useCallback(async () => { const r = await api.get('/ai-learn/opportunity-radar'); setOpportunityRadar(r.data || null); }, []);
  const loadIncomeExperiments = useCallback(async () => { const r = await api.get('/ai-learn/income-experiments'); setIncomeExperiments(r.data?.experiments || []); }, []);
  const loadRecoveryCopilot = useCallback(async () => { const r = await api.get('/ai-learn/recovery-copilot/plan'); setRecoveryCopilot(r.data || null); }, []);
  const stampFreshness = useCallback(() => { setLastFreshAt(new Date().toISOString()); }, []);

  const runWithTimeout = useCallback(async <T,>(f: () => Promise<T>, msg: string, ms = ACTION_TIMEOUT_MS): Promise<T> => {
    let h: any = null;
    try { return await Promise.race([f(), new Promise<never>((_, rej) => { h = setTimeout(() => rej(new Error(msg)), ms); })]); } finally { if (h) clearTimeout(h); }
  }, []);

  const bgRefresh = useCallback((tasks: Promise<any>[]) => { void Promise.allSettled(tasks).then(() => stampFreshness()); }, [stampFreshness]);

  const focusSprint = useCallback(() => {
    const y = Math.max(careerSprintSectionY - 20, 0);
    setTimeout(() => scrollViewRef.current?.scrollTo?.({ y, animated: true }), 140);
  }, [careerSprintSectionY]);

  const isRefreshingRef = useRef(false);
  const loadEverything = useCallback(async (opts?: { background?: boolean }) => {
    if (authLoading || isRefreshingRef.current) return;
    const preserve = Boolean(opts?.background);
    try {
      setError('');
      isRefreshingRef.current = true;
      if (!preserve) setLoading(true); else setIsRefreshingHub(true);
      if (!user?.user_id) { setError(tx('learningHub.auth.signInRequired', 'Please sign in to access AI Learning Hub.')); setLoading(false); return; }
      const crit = await Promise.allSettled([loadDashboard(), loadCenter(), loadHabitLoop(), loadCareerSprint(), loadRecoveryCopilot()]);
      const fails = crit.filter(r => r.status === 'rejected').length;
      if (fails === crit.length) throw new Error(tx('learningHub.errors.criticalModules', 'Unable to load critical modules.'));
      if (fails > 0) setError(tx('learningHub.errors.partialModules', 'Some modules are delayed. Core actions remain available.'));
      stampFreshness(); setLoading(false);
      bgRefresh([loadCourses(), loadPapers(), loadOpportunityRadar(), loadIncomeExperiments(), ...(activeTab === 'admin' && isAdmin ? [loadAdmin()] : [])]);
    } catch (e: any) { setError(e?.response?.data?.detail || tx('learningHub.errors.loadHubData', 'Unable to load AI Learning Hub data.')); } finally { setLoading(false); setIsRefreshingHub(false); isRefreshingRef.current = false; }
  }, [activeTab, authLoading, isAdmin, loadDashboard, loadCourses, loadCenter, loadPapers, loadAdmin, loadHabitLoop, loadCareerSprint, loadOpportunityRadar, loadIncomeExperiments, loadRecoveryCopilot, bgRefresh, stampFreshness, user?.user_id]);

  const loadRef = useRef(false);
  useEffect(() => {
    if (loadRef.current) return;
    if (authLoading) return; // Wait for auth to complete before loading
    loadRef.current = true;
    loadEverything();
  }, [authLoading, loadEverything]);

  useEffect(() => {
    if (activeTab === 'discover') { bgRefresh([loadCourses(), loadPapers()]); return; }
    if (activeTab === 'lab') { bgRefresh([loadPapers(), loadOpportunityRadar(), loadIncomeExperiments(), loadCareerSprint(), loadRecoveryCopilot()]); return; }
    if (activeTab === 'admin' && isAdmin) bgRefresh([loadAdmin()]);
  }, [activeTab, isAdmin, loadAdmin, loadCareerSprint, loadCourses, loadIncomeExperiments, loadOpportunityRadar, loadPapers, loadRecoveryCopilot, bgRefresh]);

  useEffect(() => {
    const t = typeof routeParams.tab === 'string' ? routeParams.tab : '';
    const f = typeof routeParams.filter === 'string' ? routeParams.filter : '';
    const k = ((typeof routeParams.kpi === 'string' ? routeParams.kpi : '') || (typeof routeParams.kpiId === 'string' ? routeParams.kpiId : '')).toLowerCase();
    if (['discover', 'journey', 'lab', 'admin'].includes(t)) setActiveTab(t as TabId);
    if (['all', 'active', 'completed'].includes(f)) setJourneyFilter(f as any);
    if (['streak', 'active', 'complete', 'minutes'].includes(k)) { setSelectedKpiId(k as any); setActiveTab('journey'); if (!f) setJourneyFilter(k === 'active' ? 'active' : k === 'complete' ? 'completed' : 'all'); }
  }, [routeParams.tab, routeParams.filter, routeParams.kpi, routeParams.kpiId]);

  useEffect(() => { if (selectedKpiId) api.post('/ai-learn/kpi-route-view', { kpi_id: selectedKpiId, route_path: typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '/ai-learning-hub', source: 'route' }).catch(() => {}); }, [selectedKpiId]);

  useEffect(() => {
    if (!lessonPlayer?.playing) { if (playerTickRef.current) { clearInterval(playerTickRef.current); playerTickRef.current = null; } return; }
    playerTickRef.current = setInterval(() => { setLessonPlayer((p: any) => { if (!p?.playing) return p; const d = Number(p.durationSeconds || 0); return { ...p, positionSeconds: d > 0 ? Math.min(d, Number(p.positionSeconds || 0) + 1) : Number(p.positionSeconds || 0) + 1 }; }); }, 1000);
    return () => { if (playerTickRef.current) { clearInterval(playerTickRef.current); playerTickRef.current = null; } };
  }, [lessonPlayer?.playing]);

  useEffect(() => { const t = Number(center?.latest_roadmap?.timeline_months); if (Number.isFinite(t) && t >= 1 && t <= 12) setRoadmapTimelineMonths(Math.round(t)); }, [center?.latest_roadmap?.roadmap_id, center?.latest_roadmap?.timeline_months]);

  useEffect(() => {
    const rid = center?.latest_roadmap?.roadmap_id;
    if (!rid || Platform.OS !== 'web' || typeof window === 'undefined') { setRoadmapWeekProgress({}); return; }
    try { const raw = window.localStorage.getItem(`ai-learning-hub-roadmap-progress-${rid}`); const p = raw ? JSON.parse(raw) : {}; setRoadmapWeekProgress(p && typeof p === 'object' ? p : {}); } catch { setRoadmapWeekProgress({}); }
  }, [center?.latest_roadmap?.roadmap_id]);

  useAutoRefresh(() => {
    loadEverything({ background: true });
  }, { intervalMs: 300000 });

  /* ─── Action Handlers ─── */
  const generateCourse = async () => {
    if (!courseTopic.trim()) return; setBusyId('generate-course');
    try { await api.post('/ai-learn/courses/auto-generate', { topic: courseTopic.trim(), category: courseCategory || 'AI', difficulty: courseDifficulty, objective: 'Career acceleration and practical execution' }); setCourseTopic(''); await Promise.all([loadCourses(), loadDashboard()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Course generation failed'); } finally { setBusyId(''); }
  };

  const enrollCourse = async (courseId: string) => {
    setBusyId(`enroll-${courseId}`);
    try { await api.post(`/ai-learn/courses/${courseId}/enroll`); await Promise.all([loadCourses(), loadCenter(), loadDashboard()]); setActiveTab('journey'); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Enrollment failed'); } finally { setBusyId(''); }
  };

  const completeModule = async (courseId: string, moduleId: string) => {
    setBusyId(`progress-${courseId}-${moduleId}`);
    try { await api.post(`/ai-learn/courses/${courseId}/progress`, { module_id: moduleId, completed: true, minutes_spent: 20 }); await Promise.all([loadCenter(), loadDashboard(), loadHabitLoop()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Progress update failed'); } finally { setBusyId(''); }
  };

  const generateRoadmap = async () => {
    setBusyId('generate-roadmap');
    try { await api.post('/ai-learn/roadmap/generate', { target_role: roadmapRole, current_skills: roadmapSkills.split(',').map(s => s.trim()).filter(Boolean), timeline_months: roadmapTimelineMonths }); await Promise.all([loadCenter(), loadDashboard()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Roadmap generation failed'); } finally { setBusyId(''); }
  };

  const executeSandbox = async () => {
    setBusyId('sandbox-run');
    try { const r = await runWithTimeout(() => api.post('/ai-learn/sandbox/execute', { prompt: sandboxPrompt, language: 'python' }), 'Sandbox execution timed out.'); setSandboxOutput(r.data?.sandbox || null); bgRefresh([loadDashboard()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Sandbox execution failed'); } finally { setBusyId(''); }
  };

  const summarizePaper = async (paperId: string) => {
    setBusyId(`paper-${paperId}`);
    try { await api.post(`/ai-learn/papers/${paperId}/summarize`); await loadPapers(); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Paper summary failed'); } finally { setBusyId(''); }
  };

  const runMentorMatch = async () => {
    if (busyId === 'mentor-match') return; setBusyId('mentor-match'); setSelectedMentorId(''); setMentorMatches([]); setMentorFlowMessage('Refreshing mentor shortlist...');
    try { if (Platform.OS === 'web' && typeof window !== 'undefined') window.localStorage.removeItem(MENTOR_SELECTION_CACHE_KEY);
      const r = await api.post('/ai-learn/mentor-match', { objective: mentorObjective, preferred_focus: 'AI' });
      const m = Array.isArray(r.data?.matches) ? r.data.matches : []; setMentorMatches(m);
      const pid = Platform.OS === 'web' && typeof window !== 'undefined' ? String(window.localStorage.getItem(MENTOR_SELECTION_CACHE_KEY) || '') : '';
      setSelectedMentorId(m.find((r: any) => r.mentor_id === pid)?.mentor_id || m[0]?.mentor_id || '');
      await Promise.all([loadDashboard(), loadHabitLoop()]); stampFreshness();
      setMentorFlowMessage(m.length > 0 ? 'Mentor shortlist ready.' : 'No suggestions yet. Try a clearer objective.');
    } catch (e: any) { setError(e?.response?.data?.detail || 'Mentor match failed'); setMentorFlowMessage('Matching failed. Retry after updating your objective.'); } finally { setBusyId(''); }
  };

  const continueWithMentor = async (mentorOverride?: any, source: 'selection' | 'manual' = 'manual') => {
    const mentor = mentorOverride || selectedMentor; if (!mentor?.mentor_id) { setError('Please select a mentor.'); return false; }
    setBusyId('mentor-next-step'); setMentorFlowMessage(`Preparing ${mentor.name}'s mentor-guided sprint...`);
    try {
      const title = `Mentor-guided sprint with ${mentor.name}`; const obj = mentorObjective.trim() || `Build execution momentum with ${mentor.specialty}`; const ctx = `${mentor.reason} Region: ${mentor.region}. Experience: ${num(mentor.experience_years)} years.`;
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.localStorage.setItem(MENTOR_SELECTION_CACHE_KEY, String(mentor.mentor_id));
      const r = await runWithTimeout(() => api.post('/ai-learn/career-sprints/solve', { challenge_title: title, objective: obj, context: ctx, income_goal: careerIncomeGoal.trim() || undefined, weekly_hours: Number(careerWeeklyHours) || 6 }), 'Mentor sprint setup timed out.');
      setCareerChallengeTitle(title); setCareerObjective(obj); setCareerContext(ctx); setCareerSprint(r.data?.sprint || null); setSelectedMentorId(String(mentor.mentor_id)); setActiveTab('lab');
      router.push({ pathname: '/ai-learning-hub', params: { tab: 'lab' } }); focusSprint();
      bgRefresh([loadDashboard(), loadHabitLoop(), loadCareerSprint(), loadCenter()]); stampFreshness();
      setMentorFlowMessage(`${mentor.name} selected. Sprint is ready.`); return true;
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Mentor step failed.'); setMentorFlowMessage('Sprint init failed. Retry.'); return false; } finally { setBusyId(''); }
  };

  const handleMentorSelect = async (mentor: any) => { if (!mentor?.mentor_id) { setError('Invalid mentor.'); return; } setSelectedMentorId(String(mentor.mentor_id)); await continueWithMentor(mentor, 'selection'); };

  const toggleFavoriteMentor = useCallback((mentorId: string) => {
    const id = String(mentorId || '');
    if (!id) return;
    setFavoriteMentorIds((prev) => (prev.includes(id) ? prev.filter((m) => m !== id) : [id, ...prev].slice(0, 20)));
  }, []);

  const toggleCompareMentor = useCallback((mentorId: string) => {
    const id = String(mentorId || '');
    if (!id) return;
    setCompareMentorIds((prev) => {
      if (prev.includes(id)) return prev.filter((m) => m !== id);
      if (prev.length >= 3) return [...prev.slice(1), id];
      return [...prev, id];
    });
  }, []);

  const clearMentorCompare = useCallback(() => setCompareMentorIds([]), []);

  const bookIntroSession = useCallback(() => {
    router.push('/book-meeting' as any);
  }, [router]);

  const generateCareerSprint = async () => {
    if (!careerChallengeTitle.trim() || !careerObjective.trim()) return; setBusyId('career-sprint-generate');
    try { const r = await runWithTimeout(() => api.post('/ai-learn/career-sprints/solve', { challenge_title: careerChallengeTitle.trim(), objective: careerObjective.trim(), context: careerContext.trim() || undefined, income_goal: careerIncomeGoal.trim() || undefined, weekly_hours: Number(careerWeeklyHours) || 6 }), 'Sprint generation timed out.');
      setCareerSprint(r.data?.sprint || null); focusSprint(); bgRefresh([loadDashboard(), loadHabitLoop(), loadCareerSprint()]); stampFreshness();
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Sprint generation failed.'); } finally { setBusyId(''); }
  };

  const createIncomeExperiment = async () => {
    if (!experimentTitle.trim() || !experimentHypothesis.trim()) return; setBusyId('income-experiment-create');
    try { await runWithTimeout(() => api.post('/ai-learn/income-experiments', { title: experimentTitle.trim(), hypothesis: experimentHypothesis.trim(), execution_plan: experimentPlan.trim() || undefined, effort_hours: 3 }), 'Experiment creation timed out.');
      bgRefresh([loadIncomeExperiments()]); setExperimentTitle(''); setExperimentHypothesis(''); setExperimentPlan(''); stampFreshness();
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Experiment creation failed.'); } finally { setBusyId(''); }
  };

  const logIncomeExperiment = async (eid: string) => {
    setBusyId(`income-experiment-log-${eid}`);
    try { await api.post(`/ai-learn/income-experiments/${eid}/log`, { status: 'validated', revenue_delta: Number(experimentRevenue) || 0, insight: experimentInsight.trim() || 'Validation checkpoint logged.' }); await loadIncomeExperiments(); setExperimentInsight(''); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Log experiment failed.'); } finally { setBusyId(''); }
  };

  const completeDailyMission = async (key: string) => {
    setBusyId(`habit-mission-${key}`);
    try { const r = await api.post(`/ai-learn/habit-loop/missions/${key}/complete`); setHabitLoop((p: any) => ({ ...(p || {}), summary: r.data?.summary || p?.summary })); await loadDashboard(); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Mission failed.'); } finally { setBusyId(''); }
  };

  const submitHabitCheckIn = async () => {
    setBusyId('habit-check-in');
    try { const r = await api.post('/ai-learn/habit-loop/check-in', { mood_score: checkInMood, focus_score: checkInFocus, blocker: checkInBlocker.trim() || undefined, available_minutes: 30 }); setCheckInCoach(r.data?.coach || null); setHabitLoop((p: any) => ({ ...(p || {}), summary: r.data?.summary || p?.summary })); setCheckInBlocker(''); await loadDashboard(); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Check-in failed.'); } finally { setBusyId(''); }
  };

  const redeemStreakInsurance = async () => { setBusyId('streak-insurance-redeem'); try { await api.post('/ai-learn/habit-loop/streak-insurance/redeem', {}); await Promise.all([loadHabitLoop(), loadDashboard()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Redeem failed.'); } finally { setBusyId(''); } };
  const activateOpportunity = async (oid: string) => { setBusyId(`activate-opportunity-${oid}`); try { await api.post(`/ai-learn/opportunity-radar/${oid}/activate`); await loadOpportunityRadar(); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Activate failed.'); } finally { setBusyId(''); } };

  const issueCertificate = async (cid: string) => { setBusyId(`issue-cert-${cid}`); try { await api.post(`/ai-learn/certificates/${cid}/issue`); await Promise.all([loadCenter(), loadDashboard()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Certificate failed.'); } finally { setBusyId(''); } };

  const downloadCertificatePdf = async (vid: string, layout: 'portrait' | 'landscape' = 'portrait') => {
    setBusyId(`download-cert-${vid}-${layout}`);
    try {
      const base = (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
      const canUseCookieSession = Platform.OS === 'web';
      const token = canUseCookieSession ? null : await ensureAuthTokenLoaded();
      if (!canUseCookieSession && !token) throw new Error('Session missing');
      const tokenQuery = token ? `token=${encodeURIComponent(token)}&` : '';
      const url = withCertificatePrintLayout(`${base || ''}/api/ai-learn/certificates/${encodeURIComponent(vid)}/pdf/file?${tokenQuery}variant=print`, layout);
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(url, '_blank', 'noopener,noreferrer');
      else await Linking.openURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'PDF download failed.');
    } finally {
      setBusyId('');
      setCertificatePrintTarget(null);
    }
  };

  const downloadAllCertificatesBundle = async () => {
    setBusyId('download-certificates-bundle');
    try {
      const canUseCookieSession = Platform.OS === 'web';
      const token = canUseCookieSession ? null : await ensureAuthTokenLoaded();
      if (!canUseCookieSession && !token) throw new Error('Session missing');
      const base = (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
      const tokenQuery = token ? `token=${encodeURIComponent(token)}&` : '';
      const url = `${base || ''}/api/ai-learn/certificates/download-all/bundle?${tokenQuery}layout=portrait`;
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(url, '_blank', 'noopener,noreferrer');
      else await Linking.openURL(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Bundle download failed.');
    } finally {
      setBusyId('');
    }
  };

  const applyRecoveryCopilotAction = async (actionId: string) => {
    setBusyId(`recovery-copilot-${actionId}`);
    try {
      const r = await api.post('/ai-learn/recovery-copilot/apply', { action_id: actionId, objective: careerObjective });
      setRecoveryCopilot(r.data?.summary || recoveryCopilot);
      if (r.data?.sprint) setCareerSprint(r.data.sprint);
      if (r.data?.action_url) router.push(r.data.action_url as any);
      await Promise.all([loadDashboard(), loadHabitLoop(), loadCareerSprint(), loadRecoveryCopilot()]);
      stampFreshness();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Recovery action failed.');
    } finally {
      setBusyId('');
    }
  };

  const openCertificatePrintOptions = (c: any) => { const vid = typeof c === 'string' ? c : c?.verification_id; if (!vid) return; setCertificatePrintTarget(typeof c === 'string' ? { verification_id: vid } : c || { verification_id: vid }); };
  const openCertificatePage = (vid?: string, fallbackUrl?: string) => { if (vid) { router.push(`/certificate-verify/${encodeURIComponent(vid)}` as any); return; } if (fallbackUrl) openExt(fallbackUrl, setError); };

  const openResolvedVideo = async (cid: string, lesson: any) => {
    const lid = String(lesson?.lesson_id || ''); if (!lid) return; setBusyId(`video-external-${cid}-${lid}`);
    try { const r = await api.get(`/ai-learn/videos/${cid}/${lid}/resolve`); const url = r.data?.playback_url || r.data?.fallback_url; if (!url) throw new Error('Video URL missing'); await openExt(url, setError); } catch (e: any) { setError(e?.response?.data?.detail || 'Unable to open lesson.'); } finally { setBusyId(''); }
  };

  const handleKpiCardPress = (kpiId: string) => {
    const filter = kpiId === 'active' ? 'active' : kpiId === 'complete' ? 'completed' : 'all';
    setActiveTab('journey'); setJourneyFilter(filter);
    if (['streak', 'active', 'complete', 'minutes'].includes(kpiId)) { setSelectedKpiId(kpiId as any); router.push(`/ai-learning-hub-kpi/${kpiId}` as any); }
  };

  const closeKpiModal = () => { setSelectedKpiId(null); router.push({ pathname: '/ai-learning-hub', params: { tab: activeTab, filter: journeyFilter } }); };

  const openAssessmentModal = (enrollment: any) => {
    const qs = enrollment?.final_assessment?.questions || [];
    const init: Record<string, number> = {}; qs.forEach((q: any) => { init[String(q.question_id)] = -1; });
    setAssessmentAnswers(init); setAssessmentResult(null); setAssessmentTargetEnrollment(enrollment);
  };

  const submitAssessment = async () => {
    const e = assessmentTargetEnrollment; if (!e?.course_id) return; setBusyId(`assessment-${e.course_id}`);
    try { const ans: Record<string, number> = {}; Object.entries(assessmentAnswers).forEach(([qid, ai]) => { if (typeof ai === 'number' && ai >= 0) ans[qid] = ai; });
      const r = await api.post(`/ai-learn/courses/${e.course_id}/assessment/submit`, { answers: ans }); setAssessmentResult(r.data || null);
      await Promise.all([loadCenter(), loadDashboard()]); stampFreshness(); if (r.data?.completed) setAssessmentTargetEnrollment(null);
    } catch (ex: any) { setError(ex?.response?.data?.detail || 'Assessment failed.'); } finally { setBusyId(''); }
  };

  const trackRemediationAction = async (cid: string, payload: any) => { if (!cid) return; try { await api.post(`/ai-learn/courses/${cid}/remediation/action`, payload); await loadCenter(); stampFreshness(); } catch { /* noop */ } };

  const applyLocalLessonWatch = (cid: string, lid: string, ws: any) => {
    setCenter((prev: any) => { if (!prev?.enrollments) return prev; return { ...prev, enrollments: (prev.enrollments || []).map((en: any) => { if (en?.course_id !== cid) return en; const nls = (en.video_lessons || []).map((l: any) => { if (l?.lesson_id !== lid) return l; return { ...l, watch_state: ws, watched_pct: Number(ws?.watched_pct || 0), resume_label: ws?.resume_label || fmtDur(ws?.last_position_seconds || ws?.watch_seconds || 0) }; }); return { ...en, video_lessons: nls, lesson_watch_state: { ...(en.lesson_watch_state || {}), [lid]: ws } }; }) }; });
  };

  const saveLessonWatchState = async (cid: string, lid: string, payload: any, tag: string) => {
    setBusyId(`watch-${cid}-${lid}-${tag}`);
    try { const r = await api.post(`/ai-learn/courses/${cid}/lessons/${lid}/watch-state`, payload); if (r.data?.watch_state) applyLocalLessonWatch(cid, lid, r.data.watch_state); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || 'Watch state save failed.'); } finally { setBusyId(''); }
  };

  const emitLessonTelemetry = async (cid: string, lid: string, payload: any, tag: string) => {
    setBusyId(`telemetry-${cid}-${lid}-${tag}`);
    try { const r = await api.post(`/ai-learn/courses/${cid}/lessons/${lid}/telemetry`, payload); if (r.data?.watch_state) applyLocalLessonWatch(cid, lid, r.data.watch_state); return r.data?.watch_state; } catch (e: any) { setError(e?.response?.data?.detail || 'Telemetry failed.'); return null; } finally { setBusyId(''); }
  };

  const closeLessonPlayer = async () => { if (lessonPlayer?.playing) await emitLessonTelemetry(lessonPlayer.courseId, lessonPlayer.lessonId, { session_id: lessonPlayer.sessionId, event_type: 'pause', position_seconds: Number(lessonPlayer.positionSeconds || 0), duration_seconds: Number(lessonPlayer.durationSeconds || 0) }, 'pause_on_close'); setLessonPlayer(null); };
  const togglePlay = async () => { if (!lessonPlayer) return; const np = !lessonPlayer.playing; await emitLessonTelemetry(lessonPlayer.courseId, lessonPlayer.lessonId, { session_id: lessonPlayer.sessionId, event_type: np ? 'play' : 'pause', position_seconds: Number(lessonPlayer.positionSeconds || 0), duration_seconds: Number(lessonPlayer.durationSeconds || 0) }, np ? 'play' : 'pause'); setLessonPlayer((p: any) => p ? { ...p, playing: np } : p); };
  const seekPlayer = async (d: number) => { if (!lessonPlayer) return; const dur = Number(lessonPlayer.durationSeconds || 0); const cur = Number(lessonPlayer.positionSeconds || 0); const np = Math.max(0, dur > 0 ? Math.min(dur, cur + d) : cur + d); await emitLessonTelemetry(lessonPlayer.courseId, lessonPlayer.lessonId, { session_id: lessonPlayer.sessionId, event_type: 'seek', position_seconds: np, duration_seconds: dur || undefined, seek_delta_seconds: d }, d > 0 ? 'seek_plus' : 'seek_minus'); setLessonPlayer((p: any) => p ? { ...p, positionSeconds: np } : p); };
  const markComplete = async () => { if (!lessonPlayer) return; const d = Number(lessonPlayer.durationSeconds || 0) || Number(lessonPlayer.positionSeconds || 0); const ws = await emitLessonTelemetry(lessonPlayer.courseId, lessonPlayer.lessonId, { session_id: lessonPlayer.sessionId, event_type: 'complete', position_seconds: d, duration_seconds: d || undefined }, 'complete'); if (ws) { setLessonPlayer((p: any) => p ? { ...p, positionSeconds: Number(ws.last_position_seconds || d), playing: false } : p);
    const enr = allEnrollments.find((e: any) => String(e.course_id) === String(lessonPlayer.courseId));
    const vls = Array.isArray(enr?.video_lessons) ? enr.video_lessons : [];
    const li = vls.findIndex((l: any) => String(l.lesson_id) === String(lessonPlayer.lessonId));
    const nextLesson = li >= 0 && li < vls.length - 1 ? vls[li + 1] : null;
    setCelebration({ courseId: lessonPlayer.courseId, lessonTitle: lessonPlayer.title, nextLesson });
  } };

  const openCourseVideo = async (cid: string, lesson: any) => {
    const lid = String(lesson?.lesson_id || ''); if (!lid) return; setBusyId(`video-${cid}-${lid}`);
    try { const r = await api.get(`/ai-learn/videos/${cid}/${lid}/resolve`); const url = r.data?.playback_url; if (!url) throw new Error('Video URL missing');
      const ts = Number(lesson?.duration_min || 0) * 60; const ws = lesson?.watch_state || {}; const sp = Number(ws?.last_position_seconds || ws?.watch_seconds || 0); const sid = `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      await emitLessonTelemetry(cid, lid, { session_id: sid, event_type: 'open', position_seconds: sp, duration_seconds: ts || undefined }, 'open');
      setLessonPlayer({ courseId: cid, lessonId: lid, title: lesson?.title || 'Lesson Playback', playbackUrl: url, positionSeconds: sp, durationSeconds: ts, sessionId: sid, playing: false }); stampFreshness();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Unable to open video.'); } finally { setBusyId(''); }
  };

  const runWeeklyAutopublishNow = async () => { if (!isAdmin) return; setBusyId('weekly-autopublish-run-now'); try { await runWithTimeout(() => api.post('/ai-learn/admin/weekly-course-publish/run-now'), 'Autopublish timed out.'); bgRefresh([loadDashboard(), loadCourses(), loadAdmin()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Autopublish failed.'); } finally { setBusyId(''); } };
  const runAssuranceNow = async () => { if (!isAdmin) return; setBusyId('assurance-run-now'); try { await runWithTimeout(() => api.post('/ai-learn/admin/assurance/run-now'), 'Assurance timed out.'); bgRefresh([loadDashboard(), loadAdmin()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Assurance failed.'); } finally { setBusyId(''); } };
  const saveSessionTimeoutPolicy = async (ov?: { userHours?: number; adminHours?: number }) => {
    if (!isAdmin) return; const ah = Number(ov?.adminHours ?? adminSessionHoursInput); const uh = Number(ov?.userHours ?? userSessionHoursInput);
    if (!Number.isFinite(ah) || !Number.isFinite(uh) || ah < 1 || ah > 24 || uh < 1 || uh > 24) { setError('Timeout hours must be 1-24.'); return; }
    setBusyId('session-timeout-save');
    try { const r = await runWithTimeout(() => api.post('/auth/admin/session-timeout-config', { admin_hours: Math.round(ah), user_hours: Math.round(uh) }), 'Timeout policy save timed out.'); setSessionTimeoutConfig(r.data?.config || null); setAdminSessionHoursInput(String(Math.round(ah))); setUserSessionHoursInput(String(Math.round(uh))); bgRefresh([loadAdmin()]); stampFreshness(); } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Policy save failed.'); } finally { setBusyId(''); }
  };

  const toggleRoadmapWeek = (wn: number) => {
    const rid = center?.latest_roadmap?.roadmap_id; const k = String(wn);
    setRoadmapWeekProgress(p => { const n = { ...p, [k]: !p[k] }; if (rid && Platform.OS === 'web' && typeof window !== 'undefined') try { window.localStorage.setItem(`ai-learning-hub-roadmap-progress-${rid}`, JSON.stringify(n)); } catch { /* noop */ } return n; });
  };

  const kpiDetails = useMemo(() => ({
    streak: { title: 'Streak Days', value: num(dashboard?.engagement?.streak_days), subtitle: `Multiplier x${streakMultiplier} | ${insuranceTokens} insurance tokens`, bullets: [`Missions: ${dailyMissions.filter((m: any) => m.completed).length}/${dailyMissions.length}`, `Risk: ${habitRisk}`, habitNudge], filter: 'all' as const },
    active: { title: 'Active Courses', value: String(displayedActive), subtitle: 'Courses in progress', bullets: activeEnrollments.length > 0 ? activeEnrollments.slice(0, 4).map((r: any) => `${r.course_title} - ${num(r.progress_pct)}%`) : ['No active courses yet.'], filter: 'active' as const },
    complete: { title: 'Completed Courses', value: String(displayedCompleted), subtitle: 'Completed with certificate readiness', bullets: completedEnrollments.length > 0 ? completedEnrollments.slice(0, 4).map((r: any) => `${r.course_title} - completed`) : ['No completed courses yet.'], filter: 'completed' as const },
    minutes: { title: 'Weekly Minutes', value: num(dashboard?.engagement?.weekly_minutes), subtitle: 'Learning time this week', bullets: [`Minutes: ${num(dashboard?.engagement?.weekly_minutes)}`, `Autopublished: ${Number(dashboard?.weekly_release?.published_count || 0)}/5`], filter: 'all' as const },
  }), [dashboard, streakMultiplier, insuranceTokens, dailyMissions, habitRisk, habitNudge, displayedActive, displayedCompleted, activeEnrollments, completedEnrollments]);

  /* ═══════════════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════════════ */

  if (loading) return (
    <View style={{ flex: 1, backgroundColor: 'transparent', justifyContent: 'center', alignItems: 'center' }} data-testid="ai-learning-hub-page-root" testID="ai-learning-hub-page-root">
      <ActivityIndicator size="large" color={C.primary} />
      <Text style={{ color: C.muted, marginTop: 16, fontSize: 14, fontFamily: BF }}>{tx('learningHub.states.loading', 'Loading Learning Hub...')}</Text>
    </View>
  );

  if (error && !dashboard && !center?.enrollments?.length) return (
    <View style={{ flex: 1, backgroundColor: 'transparent', justifyContent: 'center', alignItems: 'center', padding: 24 }} data-testid="ai-learning-hub-page-root" testID="ai-learning-hub-page-root">
      <Ionicons name="alert-circle-outline" size={40} color={C.error} />
      <Text style={{ color: C.text, marginTop: 12, fontSize: 16, fontWeight: '700', fontFamily: HF, textAlign: 'center' }}>{error}</Text>
      <PrimaryBtn label={tx('learningHub.common.retry', 'Retry')} onPress={() => loadEverything()} icon="refresh-outline" testId="ai-learning-hub-retry-btn" style={{ marginTop: 16 }} />
    </View>
  );

  const pad = isMobile ? 16 : 32;
  const maxW = 1440;

  const kpiCards = [
    { id: 'streak', label: tx('learningHub.kpis.streak', 'Streak'), value: num(dashboard?.engagement?.streak_days), unit: tx('learningHub.kpis.days', 'days'), icon: 'flame-outline', color: C.warningText },
    { id: 'active', label: tx('learningHub.kpis.active', 'Active'), value: String(displayedActive), unit: tx('learningHub.kpis.courses', 'courses'), icon: 'book-outline', color: C.primary },
    { id: 'complete', label: tx('learningHub.kpis.completed', 'Completed'), value: String(displayedCompleted), unit: tx('learningHub.kpis.courses', 'courses'), icon: 'checkmark-circle-outline', color: C.successText },
    { id: 'minutes', label: tx('learningHub.kpis.minutes', 'Minutes'), value: num(dashboard?.engagement?.weekly_minutes), unit: tx('learningHub.kpis.thisWeek', 'this week'), icon: 'time-outline', color: C.cyan },
  ];

  const filteredCourses = courses.filter((c: any) => {
    if (courseCategory && String(c.category || 'General') !== courseCategory) return false;
    if (search.trim()) { const s = search.toLowerCase(); return (c.title || '').toLowerCase().includes(s) || (c.category || '').toLowerCase().includes(s); }
    return true;
  });

  return (
    <View style={{ flex: 1, backgroundColor: 'transparent' }} data-testid="ai-learning-hub-page-root" testID="ai-learning-hub-page-root">
      <ScrollView ref={scrollViewRef} contentContainerStyle={{ paddingBottom: 80 }} data-testid="ai-learning-hub-page-scroll" testID="ai-learning-hub-page-scroll">
        <View style={{ width: '100%', maxWidth: maxW, alignSelf: 'center', paddingHorizontal: pad }}>

          {/* ─── CONTROL ROOM HEADER ─── */}
          <View style={{ paddingTop: isMobile ? 16 : 28, paddingBottom: 10 }} data-testid="ai-learning-hub-heading" testID="ai-learning-hub-heading">
            <SectionCard testId="ai-learning-hub-autopilot-ribbon" style={{ marginBottom: 14, backgroundColor: C.surface, borderRadius: 8 }}>
              <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'flex-start', gap: 14 }}>
                <View style={{ flex: 1, minWidth: 240 }}>
                  <Text style={{ color: C.cyan, fontSize: 11, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BF }} data-testid="ai-learning-hub-overline" testID="ai-learning-hub-overline">
                    {tx('learningHub.header.overline', 'AI Learning Hub')}
                  </Text>
                  <Text style={{ color: C.text, fontSize: isMobile ? 30 : 42, fontWeight: '900', letterSpacing: -1.8, fontFamily: HF, marginTop: 6 }} data-testid="ai-learning-hub-title" testID="ai-learning-hub-title">
                    {tx('learningHub.header.title', 'Learning Control Room')}
                  </Text>
                  <Text style={{ color: C.textSec, fontSize: 13, fontFamily: BF, marginTop: 8, lineHeight: 20 }} data-testid="ai-learning-hub-header-subtitle" testID="ai-learning-hub-header-subtitle">
                    {tx('learningHub.header.subtitle', 'Enterprise-grade orchestration for courses, roadmaps, labs, mentorship, and verified outcomes.')}
                  </Text>
                </View>

                <View style={{ alignItems: isMobile ? 'flex-start' : 'flex-end', gap: 8, minWidth: isMobile ? '100%' : 290 }}>
                  <View style={{ backgroundColor: C.pillBlueBg, borderRadius: 8, borderWidth: 1, borderColor: C.pillBlueBorder, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="ai-learning-hub-plan-label" testID="ai-learning-hub-plan-label">
                    <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', fontFamily: BF }}>
                      {tx('learningHub.plan.scope', 'Subscription Scope')}: {planScopeLabel}
                    </Text>
                  </View>
                  <View style={{ backgroundColor: C.pillEmeraldBg, borderRadius: 8, borderWidth: 1, borderColor: C.pillEmeraldBorder, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="ai-learning-hub-plan-caption" testID="ai-learning-hub-plan-caption">
                    <Text style={{ color: C.success, fontSize: 11, fontWeight: '800', fontFamily: BF }}>
                      {tx('learningHub.plan.autoEnforced', 'AI-entitlements auto-enforced')}
                    </Text>
                  </View>
                  {showUpgradeNudge ? (
                    <PrimaryBtn
                      label={_plan === 'free' ? tx('learningHub.plan.upgradeBasic', 'Upgrade to Basic') : tx('learningHub.plan.upgradePremium', 'Upgrade to Premium')}
                      onPress={() => router.push('/subscription/plans' as any)}
                      icon="rocket-outline"
                      testId="ai-learning-hub-upgrade-cta"
                      small
                    />
                  ) : null}
                </View>
              </View>

              <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="ai-learning-hub-access-banner" testID="ai-learning-hub-access-banner">
                <View style={{ minWidth: isMobile ? '46%' : 150, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-cap-course" testID="ai-learning-hub-cap-course">
                  <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('learningHub.cap.courseGen', 'Course Gen')}</Text>
                  <Text style={{ color: C.text, fontWeight: '900', fontFamily: HF, marginTop: 4 }}>{formatCap(entitlementCaps.course)}</Text>
                </View>
                <View style={{ minWidth: isMobile ? '46%' : 150, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-cap-roadmap" testID="ai-learning-hub-cap-roadmap">
                  <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('learningHub.cap.roadmaps', 'Roadmaps')}</Text>
                  <Text style={{ color: C.text, fontWeight: '900', fontFamily: HF, marginTop: 4 }}>{formatCap(entitlementCaps.roadmap)}</Text>
                </View>
                <View style={{ minWidth: isMobile ? '46%' : 150, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-cap-sandbox" testID="ai-learning-hub-cap-sandbox">
                  <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('learningHub.cap.sandbox', 'Sandbox')}</Text>
                  <Text style={{ color: C.text, fontWeight: '900', fontFamily: HF, marginTop: 4 }}>{formatCap(entitlementCaps.sandbox)}</Text>
                </View>
                <View style={{ minWidth: isMobile ? '46%' : 150, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-cap-mentor" testID="ai-learning-hub-cap-mentor">
                  <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('learningHub.cap.mentors', 'Mentors')}</Text>
                  <Text style={{ color: C.text, fontWeight: '900', fontFamily: HF, marginTop: 4 }}>{formatCap(entitlementCaps.mentor)}</Text>
                </View>
                <View style={{ minWidth: isMobile ? '46%' : 150, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-cap-certificate" testID="ai-learning-hub-cap-certificate">
                  <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('learningHub.cap.certificates', 'Certificates')}</Text>
                  <Text style={{ color: certificatesEnabled ? C.success : C.warningText, fontWeight: '900', fontFamily: HF, marginTop: 4 }}>
                    {certificatesEnabled ? tx('learningHub.cap.enabled', 'Enabled') : tx('learningHub.cap.locked', 'Locked')}
                  </Text>
                </View>
              </View>

              <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="ai-learning-hub-quick-actions" testID="ai-learning-hub-quick-actions">
                <PrimaryBtn label={tx('learningHub.quick.generateCourse', 'Generate Course')} onPress={generateCourse} busy={busyId === 'generate-course'} icon="sparkles-outline" testId="ai-learning-hub-quick-generate-course" small />
                <SecondaryBtn label={tx('learningHub.quick.openJourney', 'Open Journey')} onPress={() => setActiveTab('journey')} icon="map-outline" testId="ai-learning-hub-quick-open-journey" small />
                <SecondaryBtn label={tx('learningHub.quick.runRoadmap', 'Run Roadmap')} onPress={generateRoadmap} busy={busyId === 'generate-roadmap'} icon="git-network-outline" testId="ai-learning-hub-quick-run-roadmap" small />
                <SecondaryBtn label={tx('learningHub.quick.sandbox', 'Sandbox')} onPress={executeSandbox} busy={busyId === 'sandbox-run'} icon="code-working-outline" testId="ai-learning-hub-quick-sandbox" small />
              </View>

              {hubActionCards.length > 0 ? (
                <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="ai-learning-hub-daily-action-cards" testID="ai-learning-hub-daily-action-cards">
                  {hubActionCards.slice(0, 3).map((card: any, idx: number) => (
                    <TouchableOpacity
                      key={card.action_id || idx}
                      onPress={() => router.push((card.action_url || '/ai-learning-hub') as any)}
                      style={{ flex: 1, minWidth: isMobile ? '100%' : 220, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 12 }}
                      data-testid={`ai-learning-hub-daily-action-card-${idx}`}
                      testID={`ai-learning-hub-daily-action-card-${idx}`}
                    >
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', fontFamily: BF }} data-testid={`ai-learning-hub-daily-action-card-title-${idx}`} testID={`ai-learning-hub-daily-action-card-title-${idx}`}>
                        {String(card.title || tx('learningHub.dailyAction.defaultTitle', 'Daily action'))}
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 4 }} numberOfLines={2}>
                        {String(card.detail || '')}
                      </Text>
                      <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', fontFamily: BF, marginTop: 8 }}>
                        {tx('learningHub.dailyAction.open', 'Open action')} →
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              ) : null}

              {onboardingTotal > 0 ? (
                <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: C.pillBlueBorder, backgroundColor: C.pillBlueBg, padding: 12 }} data-testid="ai-learning-hub-onboarding-checklist-card" testID="ai-learning-hub-onboarding-checklist-card">
                  <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 10 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-onboarding-title" testID="ai-learning-hub-onboarding-title">Onboarding Checklist</Text>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-onboarding-progress" testID="ai-learning-hub-onboarding-progress">{onboardingCompleted}/{onboardingTotal} steps complete • {num(onboardingPct)}%</Text>
                    </View>
                    {nextOnboardingStep ? (
                      <PrimaryBtn
                        label={String(nextOnboardingStep?.action?.cta_label || 'Continue setup')}
                        onPress={() => router.push(onboardingRouteFor(nextOnboardingStep) as any)}
                        icon="arrow-forward-outline"
                        testId="ai-learning-hub-onboarding-next-step-button"
                        small
                      />
                    ) : (
                      <View style={{ backgroundColor: C.pillEmeraldBg, borderWidth: 1, borderColor: C.pillEmeraldBorder, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="ai-learning-hub-onboarding-complete-chip" testID="ai-learning-hub-onboarding-complete-chip">
                        <Text style={{ color: C.success, fontSize: 10, fontWeight: '800', fontFamily: BF }}>All steps completed</Text>
                      </View>
                    )}
                  </View>

                  <View style={{ marginTop: 10, gap: 8 }} data-testid="ai-learning-hub-onboarding-step-list" testID="ai-learning-hub-onboarding-step-list">
                    {onboardingSteps.slice(0, 5).map((step: any, idx: number) => {
                      const done = Boolean(step?.completed);
                      return (
                        <TouchableOpacity
                          key={String(step?.step_id || idx)}
                          onPress={() => !done && router.push(onboardingRouteFor(step) as any)}
                          disabled={done}
                          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderRadius: 8, borderWidth: 1, borderColor: done ? C.pillEmeraldBorder : C.border, backgroundColor: done ? C.pillEmeraldBg : C.surface, padding: 10 }}
                          data-testid={`ai-learning-hub-onboarding-step-${step?.step_id || idx}`}
                          testID={`ai-learning-hub-onboarding-step-${step?.step_id || idx}`}
                        >
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                            <Ionicons name={done ? 'checkmark-circle' : 'ellipse-outline'} size={17} color={done ? C.success : C.muted} />
                            <View style={{ flex: 1 }}>
                              <Text style={{ color: done ? C.success : C.text, fontSize: 12, fontWeight: '700', fontFamily: BF }}>{String(step?.title || `Step ${idx + 1}`)}</Text>
                              <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, marginTop: 2 }} numberOfLines={1}>{String(step?.description || '')}</Text>
                            </View>
                          </View>
                          {!done ? <Ionicons name="arrow-forward-outline" size={15} color={C.primary} /> : null}
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              ) : null}
            </SectionCard>
          </View>

          {/* ─── ERROR BANNER ─── */}
          {error ? (
            <View style={{ backgroundColor: C.pillAmberBg, borderWidth: 1, borderColor: C.pillAmberBorder, borderRadius: 10, padding: 12, marginBottom: 16, flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid="ai-learning-hub-error-banner" testID="ai-learning-hub-error-banner">
              <Ionicons name="warning-outline" size={16} color={C.warningText} />
              <Text style={{ color: C.warningText, fontSize: 12, fontFamily: BF, flex: 1 }}>{error}</Text>
              <TouchableOpacity onPress={() => setError('')} data-testid="ai-learning-hub-dismiss-error" testID="ai-learning-hub-dismiss-error"><Ionicons name="close" size={16} color={C.muted} /></TouchableOpacity>
            </View>
          ) : null}

          {/* ─── KPI CARDS ─── */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }} data-testid="ai-learning-hub-kpi-grid" testID="ai-learning-hub-kpi-grid">
            {kpiCards.map(kpi => (
              <TouchableOpacity
                key={kpi.id}
                onPress={() => handleKpiCardPress(kpi.id)}
                style={{ flex: 1, minWidth: isMobile ? '45%' : 200, backgroundColor: C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: isMobile ? 16 : 20 }}
                data-testid={`ai-learning-hub-kpi-card-${kpi.id}`} testID={`ai-learning-hub-kpi-card-${kpi.id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${kpi.color}18`, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name={kpi.icon as any} size={16} color={kpi.color} />
                  </View>
                  <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, fontFamily: BF }}>{kpi.label}</Text>
                </View>
                <Text style={{ color: C.text, fontSize: 32, fontWeight: '900', fontFamily: HF, letterSpacing: -1 }}>{kpi.value}</Text>
                <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 2 }}>{kpi.unit}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* ─── TAB BAR ─── */}
          <MomentumStrip
            streakDays={Number(dashboard?.engagement?.streak_days || 0)}
            weeklyMinutes={Number(dashboard?.engagement?.weekly_minutes || 0)}
            missions={dailyMissions}
            multiplier={streakMultiplier}
            insuranceTokens={insuranceTokens}
            onOpenJourney={() => setActiveTab('journey')}
          />

          <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, flexDirection: 'row', gap: 0, marginBottom: 24, overflow: 'hidden', backgroundColor: C.surface }} data-testid="ai-learning-hub-tab-bar" testID="ai-learning-hub-tab-bar">
            {TABS.filter(t => t.id !== 'admin' || isAdmin).map(tab => {
              const active = activeTab === tab.id;
              return (
                <TouchableOpacity
                  key={tab.id}
                  onPress={() => setActiveTab(tab.id)}
                  style={{ flex: 1, paddingVertical: 12, paddingHorizontal: isMobile ? 12 : 20, borderBottomWidth: 2, borderColor: active ? C.primary : 'transparent', backgroundColor: active ? C.surfaceHover : C.surface, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6 }}
                  data-testid={`ai-learning-hub-tab-${tab.id}`} testID={`ai-learning-hub-tab-${tab.id}`}
                >
                  <Ionicons name={tab.icon as any} size={16} color={active ? C.primary : C.muted} />
                  <Text
                    style={{ color: active ? C.text : C.muted, fontSize: isMobile ? 10 : 13, fontWeight: active ? '800' : '600', fontFamily: BF }}
                    numberOfLines={1}
                  >
                    {tx(`learningHub.tabs.${tab.id}`, tab.label)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ═══ DISCOVER TAB ═══ */}
          {activeTab === 'discover' && (
            <View data-testid="ai-learning-hub-discover-tab" testID="ai-learning-hub-discover-tab">
              {/* Search */}
              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 20 }}>
                <View style={{ flex: 1 }}>
                  <FieldInput value={search} onChangeText={setSearch} placeholder={tx('learningHub.discover.searchPlaceholder', 'Search courses by title or category...')} testId="ai-learning-hub-search-input" />
                </View>
                <PrimaryBtn label={tx('learningHub.common.search', 'Search')} onPress={() => loadCourses()} icon="search-outline" testId="ai-learning-hub-search-btn" />
              </View>

              {accessControl ? (
                <View style={{ marginBottom: 16, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 12 }} data-testid="ai-learning-hub-access-control-banner" testID="ai-learning-hub-access-control-banner">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-access-control-title" testID="ai-learning-hub-access-control-title">
                    {String(accessControl.scope_label || planScopeLabel)}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-access-control-message" testID="ai-learning-hub-access-control-message">
                    {String(accessControl.message || 'Entitlements are automatically applied from your active plan.')}
                  </Text>
                </View>
              ) : null}

              {/* Generate Course */}
              <SectionCard testId="ai-learning-hub-generate-course-card" style={{ marginBottom: 20 }}>
                <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF, marginBottom: 4 }}>{tx('learningHub.discover.generateCourseTitle', 'Generate Custom Course')}</Text>
                <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginBottom: 16 }}>{tx('learningHub.discover.generateCourseSubtitle', 'AI-powered course creation on any topic')}</Text>
                <View style={{ gap: 12 }}>
                  <FieldInput value={courseTopic} onChangeText={setCourseTopic} placeholder={tx('learningHub.discover.courseTopicPlaceholder', 'Enter a topic (e.g., LLM Fine-tuning)')} testId="ai-learning-hub-course-topic-input" />
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {CATEGORIES.map(cat => <Pill key={cat} label={cat} active={courseCategory === cat} onPress={() => setCourseCategory(prev => prev === cat ? '' : cat)} testId={`ai-learning-hub-category-${cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} />)}
                  </View>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {DIFFICULTIES.map(d => <Pill key={d} label={tx(`learningHub.difficulty.${d}`, d.charAt(0).toUpperCase() + d.slice(1))} active={courseDifficulty === d} onPress={() => setCourseDifficulty(d)} testId={`ai-learning-hub-difficulty-${d}`} />)}
                  </View>
                  <PrimaryBtn label={tx('learningHub.discover.generateCourseButton', 'Generate Course')} onPress={generateCourse} busy={busyId === 'generate-course'} icon="sparkles-outline" testId="ai-learning-hub-generate-course-btn" />
                </View>
              </SectionCard>

              {/* Research Papers */}
              {papers.length > 0 && (
                <SectionCard testId="ai-learning-hub-papers-section" style={{ marginBottom: 20 }}>
                  <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF, marginBottom: 4 }}>{tx('learningHub.discover.researchPapersTitle', 'Research Papers')}</Text>
                  <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginBottom: 16 }}>{tx('learningHub.discover.researchPapersSubtitle', 'Latest AI research with one-click summaries')}</Text>
                  <View style={{ gap: 10 }}>
                    {papers.slice(0, 6).map((paper: any, pi: number) => (
                      <View key={paper.paper_id || pi} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.surfaceHover, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-paper-${paper.paper_id}`} testID={`ai-learning-hub-paper-${paper.paper_id}`}>
                        <View style={{ flex: 1, marginRight: 12 }}>
                          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }} numberOfLines={2}>{paper.title}</Text>
                          {paper.summary && <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 4 }} numberOfLines={2}>{paper.summary}</Text>}
                        </View>
                        <View style={{ flexDirection: 'row', gap: 6 }}>
                          {!paper.summary && <PrimaryBtn label={tx('learningHub.discover.summarize', 'Summarize')} onPress={() => summarizePaper(paper.paper_id)} busy={busyId === `paper-${paper.paper_id}`} icon="document-text-outline" testId={`ai-learning-hub-summarize-paper-${paper.paper_id}`} small />}
                          {paper.url && <SecondaryBtn label={tx('learningHub.common.open', 'Open')} onPress={() => openExt(paper.url, setError)} icon="open-outline" testId={`ai-learning-hub-open-paper-${paper.paper_id}`} small />}
                        </View>
                      </View>
                    ))}
                  </View>
                </SectionCard>
              )}

              {/* Cinematic Storefront */}
              <View style={{ gap: 26 }} data-testid="ai-learning-hub-course-grid" testID="ai-learning-hub-course-grid">
                {(() => {
                  const heroCourse = filteredCourses.find((c: any) => c.featured) || filteredCourses[0] || null;
                  const enrolledIds = new Set(allEnrollments.map((e: any) => String(e.course_id)));
                  const continueCourses = activeEnrollments.map((e: any) => ({ ...(coursesById[e.course_id] || {}), course_id: e.course_id, title: e.course_title || coursesById[e.course_id]?.title || 'Course', category: e.category || coursesById[e.course_id]?.category, progress_pct: e.progress_pct }));
                  const railCategories: string[] = Array.from(new Set(filteredCourses.map((c: any) => String(c.category || 'General'))));
                  return (
                    <>
                      {heroCourse && (
                        <CinemaHero
                          course={heroCourse}
                          enrolled={enrolledIds.has(String(heroCourse.course_id))}
                          busy={busyId === `enroll-${heroCourse.course_id}`}
                          onEnroll={() => enrollCourse(heroCourse.course_id)}
                          onResume={() => setActiveTab('journey')}
                          isMobile={isMobile}
                        />
                      )}
                      {continueCourses.length > 0 && (
                        <CinemaRail
                          railId="continue"
                          title={tx('learningHub.cinema.continue', 'Continue learning')}
                          icon="play-circle-outline"
                          courses={continueCourses}
                          enrolledIds={enrolledIds}
                          busyId={busyId}
                          onEnroll={enrollCourse}
                          onOpen={() => setActiveTab('journey')}
                          isMobile={isMobile}
                        />
                      )}
                      {railCategories.map((cat) => (
                        <CinemaRail
                          key={cat}
                          railId={cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}
                          title={cat}
                          icon="film-outline"
                          courses={filteredCourses.filter((c: any) => String(c.category || 'General') === cat)}
                          enrolledIds={enrolledIds}
                          busyId={busyId}
                          onEnroll={enrollCourse}
                          onOpen={() => setActiveTab('journey')}
                          isMobile={isMobile}
                        />
                      ))}
                      {filteredCourses.length === 0 && <Text style={{ color: C.muted, fontSize: 14, fontFamily: BF, textAlign: 'center', padding: 32 }}>{tx('learningHub.discover.noCoursesFound', 'No courses found. Try a different search or generate one above.')}</Text>}
                    </>
                  );
                })()}
              </View>
            </View>
          )}

          {/* ═══ JOURNEY TAB ═══ */}
          {activeTab === 'journey' && (
            <View data-testid="ai-learning-hub-journey-tab" testID="ai-learning-hub-journey-tab">
              {weeklyLoop ? (
                <SectionCard testId="ai-learning-hub-weekly-achievement-loop-section" style={{ marginBottom: 18 }}>
                  <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 10, marginBottom: 10 }}>
                    <View>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF }} data-testid="ai-learning-hub-weekly-achievement-loop-title" testID="ai-learning-hub-weekly-achievement-loop-title">Weekly Achievement Loop</Text>
                      <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF }} data-testid="ai-learning-hub-weekly-achievement-loop-subtitle" testID="ai-learning-hub-weekly-achievement-loop-subtitle">Points, missions, rewards, and leaderboard momentum.</Text>
                    </View>
                    <View style={{ backgroundColor: C.pillBlueBg, borderWidth: 1, borderColor: C.pillBlueBorder, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }} data-testid="ai-learning-hub-weekly-rank-chip" testID="ai-learning-hub-weekly-rank-chip">
                      <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', fontFamily: BF }}>Rank: {weeklyYourRank ? `#${weeklyYourRank}` : '--'}</Text>
                    </View>
                  </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 12 }} data-testid="ai-learning-hub-weekly-score-strip" testID="ai-learning-hub-weekly-score-strip">
                    <View style={{ flex: 1, minWidth: isMobile ? '46%' : 160, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-xp-meter" testID="ai-learning-hub-weekly-xp-meter">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Points</Text>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF, marginTop: 2 }}>{num(weeklyXpEarned)}/{num(weeklyXpGoal || 0)}</Text>
                    </View>
                    <View style={{ flex: 1, minWidth: isMobile ? '46%' : 160, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-minutes-meter" testID="ai-learning-hub-weekly-minutes-meter">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Minutes</Text>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF, marginTop: 2 }}>{num(weeklyMinutesEarned)}/{num(weeklyMinutesGoal || 0)}</Text>
                    </View>
                    <View style={{ flex: 1, minWidth: isMobile ? '46%' : 160, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-missions-meter" testID="ai-learning-hub-weekly-missions-meter">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Missions</Text>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF, marginTop: 2 }}>{num(weeklyMissionsCompleted)}/{num(weeklyMissionsGoal || 0)}</Text>
                    </View>
                  </View>

                  {weeklyBadge ? (
                    <View style={{ marginBottom: 12, borderRadius: 8, borderWidth: 1, borderColor: C.pillAmberBorder, backgroundColor: C.pillAmberBg, padding: 10 }} data-testid="ai-learning-hub-weekly-streak-badge-card" testID="ai-learning-hub-weekly-streak-badge-card">
                      <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-weekly-streak-badge-label" testID="ai-learning-hub-weekly-streak-badge-label">{String(weeklyBadge?.label || 'Streak badge')}</Text>
                      <Text style={{ color: C.textSec, fontSize: 11, fontFamily: BF, marginTop: 3 }}>{String(weeklyBadge?.description || '')}</Text>
                    </View>
                  ) : null}

                  {weeklyNudges ? (
                    <View style={{ marginBottom: 12, gap: 8 }} data-testid="ai-learning-hub-weekly-retention-nudges" testID="ai-learning-hub-weekly-retention-nudges">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-nudges-title" testID="ai-learning-hub-weekly-retention-nudges-title">
                        Weekly Retention Nudges ({String(weeklyCadence?.weekday_label || 'day')})
                      </Text>

                      {weeklyActivePrompt ? (
                        <View style={{ borderRadius: 8, borderWidth: 1, borderColor: C.pillBlueBorder, backgroundColor: C.pillBlueBg, padding: 10 }} data-testid="ai-learning-hub-weekly-retention-active-card" testID="ai-learning-hub-weekly-retention-active-card">
                          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-active-headline" testID="ai-learning-hub-weekly-retention-active-headline">{String(weeklyActivePrompt?.headline || 'This week nudge')}</Text>
                          <Text style={{ color: C.textSec, fontSize: 11, fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-weekly-retention-active-message" testID="ai-learning-hub-weekly-retention-active-message">{String(weeklyActivePrompt?.message || '')}</Text>
                          <View style={{ marginTop: 8, flexDirection: 'row', justifyContent: 'flex-end' }}>
                            <SecondaryBtn
                              label={String(weeklyActivePrompt?.cta?.label || 'Open nudge')}
                              onPress={() => router.push(String(weeklyActivePrompt?.cta?.action_url || '/ai-learning-hub') as any)}
                              icon="arrow-forward-outline"
                              testId="ai-learning-hub-weekly-retention-active-cta"
                              small
                            />
                          </View>
                        </View>
                      ) : null}

                      {weeklyUpcomingPrompt ? (
                        <View style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-retention-upcoming-card" testID="ai-learning-hub-weekly-retention-upcoming-card">
                          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-upcoming-headline" testID="ai-learning-hub-weekly-retention-upcoming-headline">Upcoming: {String(weeklyUpcomingPrompt?.headline || 'Weekly nudge')}</Text>
                          <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-weekly-retention-upcoming-message" testID="ai-learning-hub-weekly-retention-upcoming-message">{String(weeklyUpcomingPrompt?.message || '')}</Text>
                        </View>
                      ) : null}

                      {weeklyMondayPrompt ? (
                        <View style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-retention-monday-card" testID="ai-learning-hub-weekly-retention-monday-card">
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-monday-headline" testID="ai-learning-hub-weekly-retention-monday-headline">Monday Reset</Text>
                            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-monday-state" testID="ai-learning-hub-weekly-retention-monday-state">{String(weeklyMondayPrompt?.state || 'pending')}</Text>
                          </View>
                          <Text style={{ color: C.textSec, fontSize: 11, fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-weekly-retention-monday-message" testID="ai-learning-hub-weekly-retention-monday-message">{String(weeklyMondayPrompt?.message || '')}</Text>
                          <View style={{ marginTop: 8, flexDirection: 'row', justifyContent: 'flex-end' }}>
                            <SecondaryBtn
                              label={String(weeklyMondayPrompt?.cta?.label || 'Open Monday reset')}
                              onPress={() => router.push(String(weeklyMondayPrompt?.cta?.action_url || '/ai-learning-hub?tab=lab') as any)}
                              icon="arrow-forward-outline"
                              testId="ai-learning-hub-weekly-retention-monday-cta"
                              small
                            />
                          </View>
                        </View>
                      ) : null}

                      {weeklyFridayPrompt ? (
                        <View style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover, padding: 10 }} data-testid="ai-learning-hub-weekly-retention-friday-card" testID="ai-learning-hub-weekly-retention-friday-card">
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-friday-headline" testID="ai-learning-hub-weekly-retention-friday-headline">Friday Momentum Push</Text>
                            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', fontFamily: BF }} data-testid="ai-learning-hub-weekly-retention-friday-state" testID="ai-learning-hub-weekly-retention-friday-state">{String(weeklyFridayPrompt?.state || 'pending')}</Text>
                          </View>
                          <Text style={{ color: C.textSec, fontSize: 11, fontFamily: BF, marginTop: 4 }} data-testid="ai-learning-hub-weekly-retention-friday-message" testID="ai-learning-hub-weekly-retention-friday-message">{String(weeklyFridayPrompt?.message || '')}</Text>
                          <View style={{ marginTop: 8, flexDirection: 'row', justifyContent: 'flex-end' }}>
                            <SecondaryBtn
                              label={String(weeklyFridayPrompt?.cta?.label || 'Open Friday push')}
                              onPress={() => router.push(String(weeklyFridayPrompt?.cta?.action_url || '/ai-learning-hub?tab=journey&filter=active') as any)}
                              icon="arrow-forward-outline"
                              testId="ai-learning-hub-weekly-retention-friday-cta"
                              small
                            />
                          </View>
                        </View>
                      ) : null}
                    </View>
                  ) : null}

                  <View style={{ gap: 8, marginBottom: 12 }} data-testid="ai-learning-hub-weekly-mission-card-list" testID="ai-learning-hub-weekly-mission-card-list">
                    {weeklyMissionCards.map((card: any, idx: number) => (
                      <View key={String(card?.card_id || idx)} style={{ borderRadius: 8, borderWidth: 1, borderColor: card?.completed ? C.pillEmeraldBorder : C.border, backgroundColor: card?.completed ? C.pillEmeraldBg : C.surfaceHover, padding: 10 }} data-testid={`ai-learning-hub-weekly-mission-card-${card?.card_id || idx}`} testID={`ai-learning-hub-weekly-mission-card-${card?.card_id || idx}`}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', fontFamily: BF }}>{String(card?.title || 'Weekly mission')}</Text>
                          <Text style={{ color: card?.completed ? C.success : C.primary, fontSize: 11, fontWeight: '800', fontFamily: BF }}>{num(card?.current || 0)}/{num(card?.target || 0)} {String(card?.unit || '')}</Text>
                        </View>
                        <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 3 }}>{String(card?.description || '')}</Text>
                        <Text style={{ color: C.textSec, fontSize: 10, fontFamily: BF, marginTop: 6 }}>Reward: {String(card?.reward || '')}</Text>
                      </View>
                    ))}
                  </View>

                  {weeklyCompletionRewards.length > 0 ? (
                    <View style={{ marginBottom: 10 }} data-testid="ai-learning-hub-weekly-reward-badges" testID="ai-learning-hub-weekly-reward-badges">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8, fontFamily: BF }}>Reward Badges</Text>
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                        {weeklyCompletionRewards.map((reward: any, idx: number) => {
                          const unlocked = String(reward?.status || '').toLowerCase() === 'unlocked';
                          return (
                            <View key={String(reward?.reward_id || idx)} style={{ borderRadius: 999, borderWidth: 1, borderColor: unlocked ? C.pillEmeraldBorder : C.border, backgroundColor: unlocked ? C.pillEmeraldBg : C.surfaceHover, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`ai-learning-hub-weekly-reward-badge-${reward?.reward_id || idx}`} testID={`ai-learning-hub-weekly-reward-badge-${reward?.reward_id || idx}`}>
                              <Text style={{ color: unlocked ? C.success : C.muted, fontSize: 10, fontWeight: '800', fontFamily: BF }}>{String(reward?.title || 'Reward')}</Text>
                            </View>
                          );
                        })}
                      </View>
                    </View>
                  ) : null}

                  {weeklyLeaderboardEntries.length > 0 ? (
                    <View data-testid="ai-learning-hub-weekly-leaderboard-teaser" testID="ai-learning-hub-weekly-leaderboard-teaser">
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8, fontFamily: BF }}>Leaderboard Teaser</Text>
                      <View style={{ gap: 6 }}>
                        {weeklyLeaderboardEntries.slice(0, 5).map((entry: any, idx: number) => (
                          <View key={String(entry?.user_id || idx)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderRadius: 8, borderWidth: 1, borderColor: entry?.is_current_user ? C.pillBlueBorder : C.border, backgroundColor: entry?.is_current_user ? C.pillBlueBg : C.surfaceHover, padding: 10 }} data-testid={`ai-learning-hub-weekly-leaderboard-row-${idx + 1}`} testID={`ai-learning-hub-weekly-leaderboard-row-${idx + 1}`}>
                            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', fontFamily: BF }}>#{num(entry?.rank || idx + 1)} {String(entry?.display_name || 'Learner')}</Text>
                            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', fontFamily: BF }}>{num(entry?.weekly_xp || 0)} XP</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  ) : null}
                </SectionCard>
              ) : null}

              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
                {(['all', 'active', 'completed'] as const).map(f => <Pill key={f} label={f === 'all' ? tx('learningHub.journey.filters.all', 'All') : f === 'active' ? tx('learningHub.journey.filters.active', 'Active') : tx('learningHub.journey.filters.completed', 'Completed')} active={journeyFilter === f} onPress={() => setJourneyFilter(f)} testId={`ai-learning-hub-journey-filter-${f}`} />)}
              </View>
              {(center?.certificates || []).length > 0 && (
                <View style={{ marginTop: -10, marginBottom: 14 }}>
                  <SecondaryBtn
                    label="Download All Certificates (ZIP)"
                    onPress={downloadAllCertificatesBundle}
                    busy={busyId === 'download-certificates-bundle'}
                    icon="archive-outline"
                    testId="ai-learning-hub-download-all-certificates-btn"
                    small
                  />
                </View>
              )}

              {visibleEnrollments.length === 0 ? (
                <SectionCard testId="ai-learning-hub-journey-empty">
                  <View style={{ alignItems: 'center', padding: 32 }}>
                    <Ionicons name="school-outline" size={40} color={C.muted} />
                    <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', fontFamily: HF, marginTop: 12 }}>{tx('learningHub.journey.empty.title', 'No courses here yet')}</Text>
                    <Text style={{ color: C.muted, fontSize: 13, fontFamily: BF, marginTop: 4, textAlign: 'center' }}>{tx('learningHub.journey.empty.subtitle', 'Enroll in a course from the Discover tab to start your journey.')}</Text>
                    <PrimaryBtn label={tx('learningHub.journey.empty.button', 'Discover Courses')} onPress={() => setActiveTab('discover')} icon="compass-outline" testId="ai-learning-hub-go-discover" style={{ marginTop: 16 }} />
                  </View>
                </SectionCard>
              ) : (
                <View style={{ gap: 16 }}>
                  {visibleEnrollments.map((enrollment: any, idx: number) => {
                    const pct = Number(enrollment.progress_pct || 0);
                    const completed = Boolean(enrollment.completed);
                    const cert = certificatesByCourse[enrollment.course_id];
                    const modules = enrollment.modules || [];
                    const awaitingAssessment = Boolean(enrollment.awaiting_assessment);

                    return (
                      <SectionCard key={enrollment.enrollment_id || enrollment.course_id || idx} testId={`ai-learning-hub-enrollment-${enrollment.course_id}`}>
                        <ImageBackground
                          source={{ uri: courseCoverUrl(String(enrollment.course_id || '')) }}
                          style={{ width: '100%', height: 96, justifyContent: 'flex-end', marginBottom: 14 }}
                          imageStyle={{ borderRadius: 10 }}
                          resizeMode="cover"
                          data-testid={`ai-learning-hub-enrollment-cover-${enrollment.course_id}`} testID={`ai-learning-hub-enrollment-cover-${enrollment.course_id}`}
                        >
                          <View style={{ backgroundColor: 'rgba(4,8,16,0.45)', paddingHorizontal: 12, paddingVertical: 7, borderBottomLeftRadius: 10, borderBottomRightRadius: 10 }}>
                            <Text style={{ color: '#f8fafc' /* @theme-ok fixed-dark-canvas */, fontSize: 11, fontWeight: '900', letterSpacing: 0.8, textTransform: 'uppercase', fontFamily: BF }} numberOfLines={1}>{enrollment.category || 'General'}</Text>
                          </View>
                        </ImageBackground>
                        <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 12, marginBottom: 16 }}>
                          <View style={{ flex: 1 }}>
                            <Text style={{ color: C.text, fontSize: 17, fontWeight: '800', fontFamily: HF }}>{enrollment.course_title || 'Course'}</Text>
                            <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginTop: 2 }}>{enrollment.category || 'General'} | {enrollment.difficulty || 'intermediate'}</Text>
                          </View>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <View style={{ backgroundColor: completed ? C.pillEmeraldBg : C.pillBlueBg, borderWidth: 1, borderColor: completed ? C.pillEmeraldBorder : C.pillBlueBorder, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                              <Text style={{ color: completed ? C.success : C.primary, fontSize: 11, fontWeight: '700', fontFamily: BF }}>{completed ? 'Completed' : `${num(pct)}% progress`}</Text>
                            </View>
                          </View>
                        </View>

                        <ProgressBar pct={pct} color={completed ? C.success : C.primary} />

                        {/* Modules */}
                        {modules.length > 0 && (
                          <View style={{ marginTop: 16, gap: 8 }}>
                            {modules.map((mod: any, mi: number) => {
                              const done = Boolean(mod.completed);
                              return (
                                <View key={mod.module_id || mi} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.surfaceHover, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: C.borderSoft }} data-testid={`ai-learning-hub-module-${enrollment.course_id}-${mod.module_id}`} testID={`ai-learning-hub-module-${enrollment.course_id}-${mod.module_id}`}>
                                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                                    <Ionicons name={done ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={done ? C.success : C.muted} />
                                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', fontFamily: BF, flex: 1 }} numberOfLines={1}>{mod.title || `Module ${mi + 1}`}</Text>
                                  </View>
                                  {!done && !completed && (
                                    <TouchableOpacity onPress={() => completeModule(enrollment.course_id, mod.module_id)} disabled={busyId === `progress-${enrollment.course_id}-${mod.module_id}`} style={{ backgroundColor: C.primary, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`ai-learning-hub-complete-module-${enrollment.course_id}-${mod.module_id}`} testID={`ai-learning-hub-complete-module-${enrollment.course_id}-${mod.module_id}`}>
                                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700', fontFamily: BF }}>{busyId === `progress-${enrollment.course_id}-${mod.module_id}` ? '...' : 'Complete'}</Text>
                                    </TouchableOpacity>
                                  )}
                                </View>
                              );
                            })}
                          </View>
                        )}

                        {/* Video Lessons */}
                        {(enrollment.video_lessons || []).length > 0 && (
                          <View style={{ marginTop: 16, gap: 8 }}>
                            <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, fontFamily: BF }}>Video Lessons</Text>
                            {(enrollment.video_lessons || []).map((lesson: any, li: number) => {
                              const wp = Number(lesson.watched_pct || lesson.watch_state?.watched_pct || 0);
                              const lessonMatchPct = Number(lesson.topic_alignment_score || 0) * 100;
                              return (
                                <View key={lesson.lesson_id || li} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.surfaceHover, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: C.borderSoft }} data-testid={`ai-learning-hub-lesson-${enrollment.course_id}-${lesson.lesson_id}`} testID={`ai-learning-hub-lesson-${enrollment.course_id}-${lesson.lesson_id}`}>
                                  <View style={{ flex: 1, marginRight: 8 }}>
                                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600', fontFamily: BF }} numberOfLines={1}>{lesson.title || `Lesson ${li + 1}`}</Text>
                                    <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, marginTop: 2 }} data-testid={`ai-learning-hub-lesson-topic-match-${enrollment.course_id}-${lesson.lesson_id}`} testID={`ai-learning-hub-lesson-topic-match-${enrollment.course_id}-${lesson.lesson_id}`}>
                                      Topic match {lessonMatchPct.toFixed(0)}%
                                    </Text>
                                    {wp > 0 && <View style={{ marginTop: 4 }}><ProgressBar pct={wp} color={wp >= 95 ? C.success : C.primary} /></View>}
                                  </View>
                                  <View style={{ flexDirection: 'row', gap: 4 }}>
                                    <TouchableOpacity onPress={() => openCourseVideo(enrollment.course_id, lesson)} style={{ backgroundColor: C.primary, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`ai-learning-hub-play-lesson-${enrollment.course_id}-${lesson.lesson_id}`} testID={`ai-learning-hub-play-lesson-${enrollment.course_id}-${lesson.lesson_id}`}>
                                      <Ionicons name="play" size={12} color="var(--app-primary-text)" />
                                    </TouchableOpacity>
                                    {lesson.external_url && <TouchableOpacity onPress={() => openResolvedVideo(enrollment.course_id, lesson)} accessibilityLabel="open outline button" style={{ backgroundColor: C.surfaceHover, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-open-lesson-${enrollment.course_id}-${lesson.lesson_id}`} testID={`ai-learning-hub-open-lesson-${enrollment.course_id}-${lesson.lesson_id}`}><Ionicons name="open-outline" size={12} color={C.muted} /></TouchableOpacity>}
                                  </View>
                                </View>
                              );
                            })}
                          </View>
                        )}

                        {/* Assessment / Certificate */}
                        <View style={{ marginTop: 16, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                          {awaitingAssessment && !completed && (
                            <PrimaryBtn label="Take Assessment" onPress={() => openAssessmentModal(enrollment)} icon="document-text-outline" testId={`ai-learning-hub-take-assessment-${enrollment.course_id}`} small />
                          )}
                          {completed && !cert && (
                            <PrimaryBtn label="Generate Certificate" onPress={() => issueCertificate(enrollment.course_id)} busy={busyId === `issue-cert-${enrollment.course_id}`} icon="ribbon-outline" testId={`ai-learning-hub-issue-cert-${enrollment.course_id}`} small />
                          )}
                          {cert && (
                            <>
                              <SecondaryBtn label="View Certificate" onPress={() => openCertificatePage(cert.verification_id)} icon="eye-outline" testId={`ai-learning-hub-view-cert-${enrollment.course_id}`} small />
                              <SecondaryBtn label="Download PDF" onPress={() => openCertificatePrintOptions(cert)} icon="download-outline" testId={`ai-learning-hub-download-cert-${enrollment.course_id}`} small />
                            </>
                          )}
                        </View>
                      </SectionCard>
                    );
                  })}
                </View>
              )}

              {/* Roadmap Section */}
              {center?.latest_roadmap && (
                <SectionCard testId="ai-learning-hub-roadmap-section" style={{ marginTop: 20 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.violet}18`, justifyContent: 'center', alignItems: 'center' }}>
                      <Ionicons name="map-outline" size={18} color={C.violet} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Career Roadmap</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Target: {center.latest_roadmap.target_role || 'AI Professional'} | {roadmapTimelineMonths} months</Text>
                    </View>
                  </View>
                  {(center.latest_roadmap.weeks || center.latest_roadmap.milestones || []).slice(0, 12).map((week: any, wi: number) => {
                    const done = Boolean(roadmapWeekProgress[String(wi + 1)]);
                    return (
                      <TouchableOpacity key={wi} onPress={() => toggleRoadmapWeek(wi + 1)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: done ? C.pillEmeraldBg : C.surfaceHover, borderRadius: 8, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: done ? C.pillEmeraldBorder : C.border }} data-testid={`ai-learning-hub-roadmap-week-${wi}`} testID={`ai-learning-hub-roadmap-week-${wi}`}>
                        <Ionicons name={done ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={done ? C.success : C.muted} />
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{week.title || week.milestone || `Week ${wi + 1}`}</Text>
                          {week.description && <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 2 }} numberOfLines={2}>{week.description}</Text>}
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </SectionCard>
              )}

              {/* Roadmap Generator */}
              {!center?.latest_roadmap && (
                <SectionCard testId="ai-learning-hub-roadmap-generator" style={{ marginTop: 20 }}>
                  <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF, marginBottom: 4 }}>Generate Career Roadmap</Text>
                  <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginBottom: 16 }}>AI-powered personalized learning path</Text>
                  <View style={{ gap: 12 }}>
                    <FieldInput value={roadmapRole} onChangeText={setRoadmapRole} placeholder="Target role..." testId="ai-learning-hub-roadmap-role-input" />
                    <FieldInput value={roadmapSkills} onChangeText={setRoadmapSkills} placeholder="Current skills (comma-separated)..." testId="ai-learning-hub-roadmap-skills-input" />
                    <PrimaryBtn label="Generate Roadmap" onPress={generateRoadmap} busy={busyId === 'generate-roadmap'} icon="map-outline" testId="ai-learning-hub-generate-roadmap-btn" />
                  </View>
                </SectionCard>
              )}
            </View>
          )}

          {/* ═══ AI LAB TAB ═══ */}
          {activeTab === 'lab' && (
            <View data-testid="ai-learning-hub-lab-tab" testID="ai-learning-hub-lab-tab">

              <SectionCard testId="ai-learning-hub-recovery-copilot-section" style={{ marginBottom: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.warning}18`, justifyContent: 'center', alignItems: 'center' }}>
                      <Ionicons name="pulse-outline" size={18} color={C.warningText} />
                    </View>
                    <View>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }} data-testid="ai-learning-hub-recovery-copilot-title" testID="ai-learning-hub-recovery-copilot-title">AI Learning Recovery Copilot</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Drift detection + one-click momentum recovery</Text>
                    </View>
                  </View>
                  <View style={{ backgroundColor: recoveryRiskLevel === 'high' ? C.pillRedBg : recoveryRiskLevel === 'medium' ? C.pillAmberBg : C.pillEmeraldBg, borderWidth: 1, borderColor: recoveryRiskLevel === 'high' ? C.pillRedBorder : recoveryRiskLevel === 'medium' ? C.pillAmberBorder : C.pillEmeraldBorder, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }} data-testid="ai-learning-hub-recovery-risk-chip" testID="ai-learning-hub-recovery-risk-chip">
                    <Text style={{ color: recoveryRiskLevel === 'high' ? C.error : recoveryRiskLevel === 'medium' ? C.warningText : C.success, fontSize: 10, fontWeight: '800', fontFamily: BF }}>
                      {String(recoveryCopilot?.risk?.score ?? '--')} • {String(recoveryCopilot?.risk?.level || 'low').toUpperCase()}
                    </Text>
                  </View>
                </View>

                {(recoveryCopilot?.drift_signals || []).length > 0 && (
                  <View style={{ gap: 8, marginBottom: 12 }}>
                    {(recoveryCopilot?.drift_signals || []).slice(0, 3).map((signal: any, si: number) => (
                      <View key={`drift-${si}`} style={{ backgroundColor: C.surfaceHover, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-recovery-signal-${si}`} testID={`ai-learning-hub-recovery-signal-${si}`}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', fontFamily: BF }}>{signal?.signal || 'signal'}</Text>
                        <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 2 }}>{signal?.detail || ''}</Text>
                      </View>
                    ))}
                  </View>
                )}

                <View style={{ gap: 6 }}>
                  {(recoveryCopilot?.plan_steps || []).slice(0, 3).map((step: any, si: number) => (
                    <View key={`recovery-step-${si}`} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }} data-testid={`ai-learning-hub-recovery-step-${si}`} testID={`ai-learning-hub-recovery-step-${si}`}>
                      <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800', width: 22 }}>{si + 1}.</Text>
                      <Text style={{ color: C.textSec, fontSize: 12, fontFamily: BF, flex: 1 }}>{String(step)}</Text>
                    </View>
                  ))}
                </View>

                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 12 }} data-testid="ai-learning-hub-recovery-actions" testID="ai-learning-hub-recovery-actions">
                  <PrimaryBtn label="Generate Recovery Sprint" onPress={() => applyRecoveryCopilotAction('generate_recovery_sprint')} busy={busyId === 'recovery-copilot-generate_recovery_sprint'} icon="flash-outline" testId="ai-learning-hub-recovery-action-sprint" small />
                  <SecondaryBtn label="Complete Next Mission" onPress={() => applyRecoveryCopilotAction('complete_next_mission')} busy={busyId === 'recovery-copilot-complete_next_mission'} icon="checkmark-done-outline" testId="ai-learning-hub-recovery-action-mission" small />
                  <SecondaryBtn label="Book Intro" onPress={() => applyRecoveryCopilotAction('book_intro_session')} busy={busyId === 'recovery-copilot-book_intro_session'} icon="calendar-outline" testId="ai-learning-hub-recovery-action-book" small />
                </View>
              </SectionCard>

              {/* Career Sprint Generator */}
              <SectionCard testId="ai-learning-hub-career-sprint-section" style={{ marginBottom: 20 }}>
                <View onLayout={(e) => setCareerSprintSectionY(e.nativeEvent.layout.y)}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.primary}18`, justifyContent: 'center', alignItems: 'center' }}>
                      <Ionicons name="rocket-outline" size={18} color={C.primary} />
                    </View>
                    <View>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Career & Income Sprint</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>AI-generated 7-day execution plan</Text>
                    </View>
                  </View>
                  <View style={{ gap: 12 }}>
                    <FieldInput value={careerChallengeTitle} onChangeText={setCareerChallengeTitle} placeholder="Challenge title..." testId="ai-learning-hub-sprint-title-input" />
                    <FieldInput value={careerObjective} onChangeText={setCareerObjective} placeholder="Objective..." testId="ai-learning-hub-sprint-objective-input" />
                    <FieldInput value={careerContext} onChangeText={setCareerContext} placeholder="Context..." testId="ai-learning-hub-sprint-context-input" />
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <View style={{ flex: 1 }}><FieldInput value={careerIncomeGoal} onChangeText={setCareerIncomeGoal} placeholder="Income goal..." testId="ai-learning-hub-sprint-income-input" /></View>
                      <View style={{ width: 100 }}><FieldInput value={careerWeeklyHours} onChangeText={setCareerWeeklyHours} placeholder="Hours/wk" testId="ai-learning-hub-sprint-hours-input" /></View>
                    </View>
                    <PrimaryBtn label="Generate Sprint" onPress={generateCareerSprint} busy={busyId === 'career-sprint-generate'} icon="flash-outline" testId="ai-learning-hub-generate-sprint-btn" />
                  </View>

                  {/* Active Sprint Display */}
                  {activeSprint?.plan && (
                    <View style={{ marginTop: 20, backgroundColor: C.surfaceHover, borderRadius: 10, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="ai-learning-hub-active-sprint-card" testID="ai-learning-hub-active-sprint-card">
                      <Text style={{ color: C.primary, fontSize: 15, fontWeight: '800', fontFamily: HF }}>{activeSprintTitle}</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginTop: 4 }}>North Star: {String(activeSprint.plan?.north_star_metric || 'Execution momentum')}</Text>
                      {activeSprintActions.length > 0 && (
                        <View style={{ marginTop: 12, gap: 6 }}>
                          {activeSprintActions.slice(0, 7).map((action: any, ai: number) => (
                            <View key={ai} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }}>
                              <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800', fontFamily: BF, width: 24 }}>{ai + 1}.</Text>
                              <Text style={{ color: C.textSec, fontSize: 12, fontFamily: BF, flex: 1 }}>{typeof action === 'string' ? action : action?.action || action?.task || JSON.stringify(action)}</Text>
                            </View>
                          ))}
                        </View>
                      )}
                      <View style={{ marginTop: 12, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="ai-learning-hub-sprint-cta-row" testID="ai-learning-hub-sprint-cta-row">
                        <PrimaryBtn label="Book Intro Session" onPress={bookIntroSession} icon="calendar-outline" testId="ai-learning-hub-book-intro-session-btn" small />
                        <SecondaryBtn label="Open Agenda" onPress={() => router.push('/book-meeting' as any)} icon="open-outline" testId="ai-learning-hub-open-agenda-btn" small />
                      </View>
                    </View>
                  )}
                </View>
              </SectionCard>

              {/* Code Sandbox */}
              <SectionCard testId="ai-learning-hub-sandbox-section" style={{ marginBottom: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.violet}18`, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name="code-slash-outline" size={18} color={C.violet} />
                  </View>
                  <View>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Code Sandbox</Text>
                    <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>AI-powered code generation and execution</Text>
                  </View>
                </View>
                <FieldInput value={sandboxPrompt} onChangeText={setSandboxPrompt} placeholder="Describe what to build..." multiline mono testId="ai-learning-hub-sandbox-prompt-input" />
                <View style={{ marginTop: 12 }}>
                  <PrimaryBtn label="Run Simulation" onPress={executeSandbox} busy={busyId === 'sandbox-run'} icon="play-outline" testId="ai-learning-hub-sandbox-run-btn" />
                </View>
                {sandboxOutput && (
                  <View style={{ marginTop: 16, backgroundColor: C.surfaceHover, borderRadius: 8, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid="ai-learning-hub-sandbox-output" testID="ai-learning-hub-sandbox-output">
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, fontFamily: BF, marginBottom: 6 }}>Output</Text>
                    <Text style={{ color: C.text, fontSize: 12, fontFamily: MF, lineHeight: 20 }}>{typeof sandboxOutput === 'string' ? sandboxOutput : sandboxOutput?.result || sandboxOutput?.code || JSON.stringify(sandboxOutput, null, 2)}</Text>
                  </View>
                )}
              </SectionCard>

              {/* Income Experiments */}
              <SectionCard testId="ai-learning-hub-experiments-section" style={{ marginBottom: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.success}18`, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name="flask-outline" size={18} color={C.successText} />
                  </View>
                  <View>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Income Experiments</Text>
                    <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Track and validate revenue hypotheses</Text>
                  </View>
                </View>
                <View style={{ gap: 12 }}>
                  <FieldInput value={experimentTitle} onChangeText={setExperimentTitle} placeholder="Experiment title..." testId="ai-learning-hub-experiment-title-input" />
                  <FieldInput value={experimentHypothesis} onChangeText={setExperimentHypothesis} placeholder="Hypothesis..." testId="ai-learning-hub-experiment-hypothesis-input" />
                  <FieldInput value={experimentPlan} onChangeText={setExperimentPlan} placeholder="Execution plan..." testId="ai-learning-hub-experiment-plan-input" />
                  <PrimaryBtn label="Create Experiment" onPress={createIncomeExperiment} busy={busyId === 'income-experiment-create'} icon="add-outline" testId="ai-learning-hub-create-experiment-btn" />
                </View>

                {incomeExperiments.length > 0 && (
                  <View style={{ marginTop: 16, gap: 10 }}>
                    {incomeExperiments.slice(0, 5).map((exp: any, ei: number) => (
                      <View key={exp.experiment_id || ei} style={{ backgroundColor: C.surfaceHover, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-experiment-${exp.experiment_id}`} testID={`ai-learning-hub-experiment-${exp.experiment_id}`}>
                        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{exp.title}</Text>
                        <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 2 }}>{exp.hypothesis}</Text>
                        <View style={{ marginTop: 8 }}>
                          <SecondaryBtn label="Log Outcome" onPress={() => logIncomeExperiment(exp.experiment_id)} busy={busyId === `income-experiment-log-${exp.experiment_id}`} icon="create-outline" testId={`ai-learning-hub-log-experiment-${exp.experiment_id}`} small />
                        </View>
                      </View>
                    ))}
                  </View>
                )}
              </SectionCard>

              {/* Mentor Match */}
              <SectionCard testId="ai-learning-hub-mentor-section" style={{ marginBottom: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.cyan}18`, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name="people-outline" size={18} color={C.cyan} />
                  </View>
                  <View>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>AI Mentor Matching</Text>
                    <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Find curated mentors for your career goals</Text>
                  </View>
                </View>
                <FieldInput value={mentorObjective} onChangeText={setMentorObjective} placeholder="Your career objective..." testId="ai-learning-hub-mentor-objective-input" />
                <View style={{ marginTop: 12 }}><PrimaryBtn label="Find Mentors" accessibilityRole="button" tabIndex={0} onPress={runMentorMatch} busy={busyId === 'mentor-match'} icon="search-outline" testId="ai-learning-hub-find-mentors-btn" /></View>
                {mentorFlowMessage ? <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginTop: 8 }}>{mentorFlowMessage}</Text> : null}

                {compareMentors.length >= 2 && (
                  <View style={{ marginTop: 14, backgroundColor: C.pillBlueBg, borderRadius: 10, borderWidth: 1, borderColor: C.pillBlueBorder, padding: 12 }} data-testid="ai-learning-hub-mentor-compare-card" testID="ai-learning-hub-mentor-compare-card">
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-mentor-compare-title" testID="ai-learning-hub-mentor-compare-title">Mentor Compare ({compareMentors.length}/3)</Text>
                      <TouchableOpacity onPress={clearMentorCompare} data-testid="ai-learning-hub-clear-mentor-compare-btn" testID="ai-learning-hub-clear-mentor-compare-btn">
                        <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', fontFamily: BF }}>Clear</Text>
                      </TouchableOpacity>
                    </View>
                    <View style={{ gap: 8 }}>
                      {compareMentors.map((mentor: any) => (
                        <View key={`cmp-${mentor.mentor_id}`} style={{ backgroundColor: C.surface, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid={`ai-learning-hub-mentor-compare-${mentor.mentor_id}`} testID={`ai-learning-hub-mentor-compare-${mentor.mentor_id}`}>
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', fontFamily: BF }}>{mentor.name}</Text>
                          <Text style={{ color: C.textSec, fontSize: 11, fontFamily: BF, marginTop: 2 }}>{mentor.specialty} • {mentor.region} • {num(mentor.experience_years)} yrs</Text>
                          <Text style={{ color: C.muted, fontSize: 10, fontFamily: BF, marginTop: 4 }}>Match score: {num(mentor.score || 0, 1)}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                {mentorMatches.length > 0 && (
                  <View style={{ marginTop: 16, gap: 10 }}>
                    {sortedMentorMatches.map((mentor: any, mi: number) => {
                      const mentorId = String(mentor.mentor_id || mi);
                      const isFavorite = favoriteMentorIds.includes(mentorId);
                      const inCompare = compareMentorIds.includes(mentorId);
                      return (
                      <TouchableOpacity key={mentor.mentor_id || mi} onPress={() => handleMentorSelect(mentor)} style={{ backgroundColor: selectedMentorId === mentor.mentor_id ? C.pillBlueBg : C.surfaceHover, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: selectedMentorId === mentor.mentor_id ? C.pillBlueBorder : C.border }} data-testid={`ai-learning-hub-mentor-${mentor.mentor_id}`} testID={`ai-learning-hub-mentor-${mentor.mentor_id}`}>
                        <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', fontFamily: BF }}>{mentor.name}</Text>
                        <Text style={{ color: C.textSec, fontSize: 12, fontFamily: BF, marginTop: 2 }}>{mentor.specialty} | {mentor.region} | {num(mentor.experience_years)} yrs</Text>
                        <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 4 }}>{mentor.reason}</Text>
                        <View style={{ marginTop: 10, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                          <SecondaryBtn
                            label={isFavorite ? 'Favorited' : 'Favorite'}
                            onPress={() => toggleFavoriteMentor(mentorId)}
                            icon={isFavorite ? 'star' : 'star-outline'}
                            testId={`ai-learning-hub-mentor-favorite-${mentorId}`}
                            small
                            style={{ borderColor: isFavorite ? C.warning : C.border }}
                          />
                          <SecondaryBtn
                            label={inCompare ? 'Compared' : 'Compare'}
                            onPress={() => toggleCompareMentor(mentorId)}
                            icon="git-compare-outline"
                            testId={`ai-learning-hub-mentor-compare-toggle-${mentorId}`}
                            small
                            style={{ borderColor: inCompare ? C.primary : C.border }}
                          />
                        </View>
                      </TouchableOpacity>
                    )})}
                  </View>
                )}
              </SectionCard>

              {/* Daily Missions */}
              {dailyMissions.length > 0 && (
                <SectionCard testId="ai-learning-hub-missions-section" style={{ marginBottom: 20 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.warning}18`, justifyContent: 'center', alignItems: 'center' }}>
                      <Ionicons name="trophy-outline" size={18} color={C.warningText} />
                    </View>
                    <View>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Daily Missions</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Streak x{streakMultiplier} | Risk: {habitRisk}</Text>
                    </View>
                  </View>
                  <View style={{ gap: 8 }}>
                    {dailyMissions.map((m: any, mi: number) => (
                      <View key={m.key || mi} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.surfaceHover, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: m.completed ? C.pillEmeraldBorder : C.border }} data-testid={`ai-learning-hub-mission-${m.key || mi}`} testID={`ai-learning-hub-mission-${m.key || mi}`}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                          <Ionicons name={m.completed ? 'checkmark-circle' : 'radio-button-off-outline'} size={18} color={m.completed ? C.success : C.muted} />
                          <Text style={{ color: m.completed ? C.success : C.text, fontSize: 13, fontWeight: '600', fontFamily: BF, flex: 1, textDecorationLine: m.completed ? 'line-through' : 'none' }}>{m.label || m.description || `Mission ${mi + 1}`}</Text>
                        </View>
                        {!m.completed && (
                          <TouchableOpacity onPress={() => completeDailyMission(m.key)} style={{ backgroundColor: C.primary, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`ai-learning-hub-complete-mission-${m.key}`} testID={`ai-learning-hub-complete-mission-${m.key}`}>
                            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700', fontFamily: BF }}>Done</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    ))}
                  </View>

                  {/* Streak Insurance */}
                  {insuranceTokens > 0 && (
                    <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.pillAmberBg, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: C.pillAmberBorder }} data-testid="ai-learning-hub-streak-insurance" testID="ai-learning-hub-streak-insurance">
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: C.warningText, fontSize: 12, fontWeight: '700', fontFamily: BF }}>Streak Insurance: {insuranceTokens} tokens</Text>
                        <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF }}>Protect your streak if you miss a day</Text>
                      </View>
                      <PrimaryBtn label="Redeem" onPress={redeemStreakInsurance} busy={busyId === 'streak-insurance-redeem'} icon="shield-outline" testId="ai-learning-hub-redeem-insurance-btn" small style={{ backgroundColor: C.warning }} />
                    </View>
                  )}
                </SectionCard>
              )}

              {/* Habit Check-In */}
              <SectionCard testId="ai-learning-hub-checkin-section" style={{ marginBottom: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.success}18`, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name="heart-outline" size={18} color={C.successText} />
                  </View>
                  <View>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Daily Check-In</Text>
                    <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>Log your mood and focus to get AI coaching</Text>
                  </View>
                </View>
                <View style={{ gap: 12 }}>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginBottom: 4 }}>Mood (1-5)</Text>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        {[1, 2, 3, 4, 5].map(v => <TouchableOpacity key={v} onPress={() => setCheckInMood(v)} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: checkInMood === v ? C.primary : C.surfaceHover, borderWidth: 1, borderColor: checkInMood === v ? C.primary : C.border, justifyContent: 'center', alignItems: 'center' }} data-testid={`ai-learning-hub-checkin-mood-${v}`} testID={`ai-learning-hub-checkin-mood-${v}`}><Text style={{ color: checkInMood === v ? 'var(--app-primary-text)' : C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{v}</Text></TouchableOpacity>)}
                      </View>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginBottom: 4 }}>Focus (1-5)</Text>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        {[1, 2, 3, 4, 5].map(v => <TouchableOpacity key={v} onPress={() => setCheckInFocus(v)} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: checkInFocus === v ? C.primary : C.surfaceHover, borderWidth: 1, borderColor: checkInFocus === v ? C.primary : C.border, justifyContent: 'center', alignItems: 'center' }} data-testid={`ai-learning-hub-checkin-focus-${v}`} testID={`ai-learning-hub-checkin-focus-${v}`}><Text style={{ color: checkInFocus === v ? 'var(--app-primary-text)' : C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{v}</Text></TouchableOpacity>)}
                      </View>
                    </View>
                  </View>
                  <FieldInput value={checkInBlocker} onChangeText={setCheckInBlocker} placeholder="Any blockers? (optional)" testId="ai-learning-hub-checkin-blocker-input" />
                  <PrimaryBtn label="Submit Check-In" onPress={submitHabitCheckIn} busy={busyId === 'habit-check-in'} icon="checkmark-circle-outline" testId="ai-learning-hub-submit-checkin-btn" />
                </View>
                {checkInCoach && (
                  <View style={{ marginTop: 12, backgroundColor: C.pillBlueBg, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: C.pillBlueBorder }} data-testid="ai-learning-hub-checkin-coach" testID="ai-learning-hub-checkin-coach">
                    <Text style={{ color: C.primary, fontSize: 12, fontWeight: '700', fontFamily: BF, marginBottom: 4 }}>AI Coach</Text>
                    <Text style={{ color: C.textSec, fontSize: 12, fontFamily: BF }}>{typeof checkInCoach === 'string' ? checkInCoach : checkInCoach?.message || checkInCoach?.suggestion || JSON.stringify(checkInCoach)}</Text>
                  </View>
                )}
              </SectionCard>

              {/* Opportunity Radar */}
              {radarOpportunities.length > 0 && (
                <SectionCard testId="ai-learning-hub-opportunity-radar" style={{ marginBottom: 20 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${C.error}18`, justifyContent: 'center', alignItems: 'center' }}>
                      <Ionicons name="radar-outline" size={18} color={C.error} />
                    </View>
                    <View>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', fontFamily: HF }}>Opportunity Radar</Text>
                      <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF }}>{radarOpportunities.length} opportunities detected</Text>
                    </View>
                  </View>
                  <View style={{ gap: 8 }}>
                    {radarOpportunities.slice(0, 6).map((opp: any, oi: number) => (
                      <View key={opp.opportunity_id || oi} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.surfaceHover, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-opportunity-${opp.opportunity_id}`} testID={`ai-learning-hub-opportunity-${opp.opportunity_id}`}>
                        <View style={{ flex: 1, marginRight: 8 }}>
                          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{opp.title || opp.name}</Text>
                          <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginTop: 2 }} numberOfLines={2}>{opp.description || opp.reason}</Text>
                        </View>
                        {!opp.activated && <PrimaryBtn label="Activate" onPress={() => activateOpportunity(opp.opportunity_id)} busy={busyId === `activate-opportunity-${opp.opportunity_id}`} icon="flash-outline" testId={`ai-learning-hub-activate-${opp.opportunity_id}`} small />}
                      </View>
                    ))}
                  </View>
                </SectionCard>
              )}
            </View>
          )}

          {/* ═══ EXECUTIVE TAB ═══ */}
          {activeTab === 'admin' && isAdmin && (
            <View data-testid="ai-learning-hub-admin-tab" testID="ai-learning-hub-admin-tab">
              <SectionCard testId="ai-learning-hub-admin-insights" style={{ marginBottom: 20 }}>
                <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', fontFamily: HF, marginBottom: 16 }}>Executive Insights</Text>
                {adminInsights ? (
                  <View style={{ gap: 10 }}>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                      {[
                        { label: 'Total Users', value: num(adminInsights.total_users || engagementKpis?.total_users), icon: 'people-outline' },
                        { label: 'Active Enrollments', value: num(adminInsights.total_enrollments || engagementKpis?.total_enrollments), icon: 'book-outline' },
                        { label: 'Certificates Issued', value: num(adminInsights.total_certificates || engagementKpis?.total_certificates), icon: 'ribbon-outline' },
                        { label: 'Avg Completion', value: `${num(adminInsights.avg_completion_pct || engagementKpis?.avg_completion_pct)}%`, icon: 'stats-chart-outline' },
                      ].map((s, si) => (
                        <View key={si} style={{ flex: 1, minWidth: isMobile ? '45%' : 160, backgroundColor: C.surfaceHover, borderRadius: 10, padding: 16, borderWidth: 1, borderColor: C.border }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}><Ionicons name={s.icon as any} size={14} color={C.muted} /><Text style={{ color: C.muted, fontSize: 11, fontWeight: '700', fontFamily: BF }}>{s.label}</Text></View>
                          <Text style={{ color: C.text, fontSize: 24, fontWeight: '900', fontFamily: HF }}>{s.value}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : <Text style={{ color: C.muted, fontSize: 13, fontFamily: BF }}>Loading executive data...</Text>}
              </SectionCard>

              <SectionCard testId="ai-learning-hub-admin-recovery-copilot-snapshot" style={{ marginBottom: 20 }}>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', fontFamily: HF, marginBottom: 8 }}>Recovery Copilot Snapshot</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>
                  <View style={{ minWidth: 140, backgroundColor: C.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid="ai-learning-hub-admin-recovery-risk-metric" testID="ai-learning-hub-admin-recovery-risk-metric">
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Risk Score</Text>
                    <Text style={{ color: C.text, fontSize: 20, fontWeight: '900', fontFamily: HF }}>{String(recoveryCopilot?.risk?.score ?? '--')}</Text>
                  </View>
                  <View style={{ minWidth: 140, backgroundColor: C.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid="ai-learning-hub-admin-recovery-signals-metric" testID="ai-learning-hub-admin-recovery-signals-metric">
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Drift Signals</Text>
                    <Text style={{ color: C.text, fontSize: 20, fontWeight: '900', fontFamily: HF }}>{num((recoveryCopilot?.drift_signals || []).length)}</Text>
                  </View>
                  <View style={{ minWidth: 180, backgroundColor: C.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid="ai-learning-hub-admin-recovery-level-metric" testID="ai-learning-hub-admin-recovery-level-metric">
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', fontFamily: BF }}>Risk Level</Text>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF }}>{String(recoveryCopilot?.risk?.level || 'low').toUpperCase()}</Text>
                  </View>
                </View>
                <Text style={{ color: C.muted, fontSize: 11, fontFamily: BF }} data-testid="ai-learning-hub-admin-recovery-note" testID="ai-learning-hub-admin-recovery-note">
                  Snapshot mirrors AI Learning Recovery Copilot and refreshes with hub data.
                </Text>
              </SectionCard>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 16, marginBottom: 20 }}>
                <SectionCard testId="ai-learning-hub-admin-autopublish" style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', fontFamily: HF, marginBottom: 8 }}>Weekly Autopublish</Text>
                  <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginBottom: 12 }}>Published: {Number(dashboard?.weekly_release?.published_count || 0)}/5</Text>
                  <PrimaryBtn label="Run Now" onPress={runWeeklyAutopublishNow} busy={busyId === 'weekly-autopublish-run-now'} icon="rocket-outline" testId="ai-learning-hub-autopublish-btn" small />
                </SectionCard>
                <SectionCard testId="ai-learning-hub-admin-assurance" style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', fontFamily: HF, marginBottom: 8 }}>Platform Assurance</Text>
                  <Text style={{ color: C.muted, fontSize: 12, fontFamily: BF, marginBottom: 12 }}>Status: {String(dashboard?.assurance?.status || 'unknown')}</Text>
                  <PrimaryBtn label="Run Assurance" onPress={runAssuranceNow} busy={busyId === 'assurance-run-now'} icon="shield-checkmark-outline" testId="ai-learning-hub-assurance-btn" small />
                </SectionCard>
              </View>

              <SectionCard testId="ai-learning-hub-admin-session-timeout" style={{ marginBottom: 20 }}>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', fontFamily: HF, marginBottom: 12 }}>Session Timeout Policy</Text>
                <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
                  <View style={{ flex: 1 }}><Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginBottom: 4 }}>Admin Hours</Text><FieldInput value={adminSessionHoursInput} onChangeText={setAdminSessionHoursInput} placeholder="1-24" testId="ai-learning-hub-admin-timeout-input" /></View>
                  <View style={{ flex: 1 }}><Text style={{ color: C.muted, fontSize: 11, fontFamily: BF, marginBottom: 4 }}>User Hours</Text><FieldInput value={userSessionHoursInput} onChangeText={setUserSessionHoursInput} placeholder="1-24" testId="ai-learning-hub-user-timeout-input" /></View>
                </View>
                <View style={{ marginTop: 12 }}><PrimaryBtn label="Save Policy" accessibilityRole="button" tabIndex={0} onPress={() => saveSessionTimeoutPolicy()} busy={busyId === 'session-timeout-save'} icon="save-outline" testId="ai-learning-hub-save-timeout-btn" small /></View>
              </SectionCard>
            </View>
          )}
        </View>
      </ScrollView>

      {/* ═══ KPI DETAIL MODAL ═══ */}
      <Modal visible={Boolean(selectedKpiId)} transparent animationType="fade" onRequestClose={closeKpiModal}>
        <View style={{ flex: 1, backgroundColor: C.overlay, justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="ai-learning-hub-kpi-detail-modal" testID="ai-learning-hub-kpi-detail-modal">
          <View style={{ width: '100%', maxWidth: 500, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 24 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF }} data-testid="ai-learning-hub-kpi-detail-title" testID="ai-learning-hub-kpi-detail-title">{selectedKpiId ? kpiDetails[selectedKpiId]?.title : 'KPI Detail'}</Text>
              <TouchableOpacity onPress={closeKpiModal} style={{ padding: 4 }} data-testid="ai-learning-hub-kpi-detail-close-button" testID="ai-learning-hub-kpi-detail-close-button"><Ionicons name="close" size={20} color={C.muted} /></TouchableOpacity>
            </View>
            <Text style={{ color: C.primary, marginTop: 8, fontSize: 36, fontWeight: '900', fontFamily: HF }} data-testid="ai-learning-hub-kpi-detail-value" testID="ai-learning-hub-kpi-detail-value">{selectedKpiId ? kpiDetails[selectedKpiId]?.value : '--'}</Text>
            <Text style={{ color: C.muted, marginTop: 4, fontSize: 13, fontFamily: BF }} data-testid="ai-learning-hub-kpi-detail-subtitle" testID="ai-learning-hub-kpi-detail-subtitle">{selectedKpiId ? kpiDetails[selectedKpiId]?.subtitle : ''}</Text>
            <View style={{ marginTop: 16, gap: 8 }} data-testid="ai-learning-hub-kpi-detail-bullets" testID="ai-learning-hub-kpi-detail-bullets">
              {(selectedKpiId ? (kpiDetails[selectedKpiId]?.bullets || []) : []).map((b: string, i: number) => (
                <View key={i} style={{ backgroundColor: C.surfaceHover, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-kpi-detail-bullet-${i}`} testID={`ai-learning-hub-kpi-detail-bullet-${i}`}>
                  <Text style={{ color: C.textSec, fontSize: 12, fontFamily: BF }}>{b}</Text>
                </View>
              ))}
            </View>
            <View style={{ marginTop: 16, flexDirection: 'row', gap: 8 }}>
              <PrimaryBtn label="Open Route" onPress={() => { if (!selectedKpiId) return; setActiveTab('journey'); setJourneyFilter(kpiDetails[selectedKpiId].filter); closeKpiModal(); }} testId="ai-learning-hub-kpi-detail-go-to-route-button" small />
              <SecondaryBtn label="Close" onPress={closeKpiModal} testId="ai-learning-hub-kpi-detail-switch-tab-button" small />
            </View>
          </View>
        </View>
      </Modal>

      {/* ═══ ASSESSMENT MODAL ═══ */}
      <Modal visible={Boolean(assessmentTargetEnrollment)} transparent animationType="slide" onRequestClose={() => setAssessmentTargetEnrollment(null)}>
        <View style={{ flex: 1, backgroundColor: C.overlay, justifyContent: 'center', padding: 16 }} data-testid="ai-learning-hub-assessment-modal" testID="ai-learning-hub-assessment-modal">
          <View style={{ width: '100%', maxHeight: '88%', alignSelf: 'center', maxWidth: 960, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 24 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', fontFamily: HF }} data-testid="ai-learning-hub-assessment-modal-title" testID="ai-learning-hub-assessment-modal-title">Final Assessment</Text>
              <TouchableOpacity onPress={() => setAssessmentTargetEnrollment(null)} data-testid="ai-learning-hub-assessment-modal-close-button" testID="ai-learning-hub-assessment-modal-close-button"><Ionicons name="close" size={20} color={C.muted} /></TouchableOpacity>
            </View>
            <Text style={{ color: C.muted, marginTop: 4, fontSize: 12, fontFamily: BF }} data-testid="ai-learning-hub-assessment-modal-subtitle" testID="ai-learning-hub-assessment-modal-subtitle">Complete to unlock certification for {assessmentTargetEnrollment?.course_title || 'your course'}.</Text>

            <ScrollView style={{ marginTop: 16 }} contentContainerStyle={{ gap: 12 }} data-testid="ai-learning-hub-assessment-modal-questions" testID="ai-learning-hub-assessment-modal-questions">
              {(assessmentTargetEnrollment?.final_assessment?.questions || []).map((q: any, qi: number) => (
                <View key={q.question_id || qi} style={{ backgroundColor: C.surfaceHover, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid={`ai-learning-hub-assessment-question-${qi}`} testID={`ai-learning-hub-assessment-question-${qi}`}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', fontFamily: BF }}>{qi + 1}. {q.question}</Text>
                  <View style={{ marginTop: 8, gap: 6 }}>
                    {(q.options || []).map((opt: string, oi: number) => {
                      const sel = assessmentAnswers[String(q.question_id)] === oi;
                      return (
                        <TouchableOpacity key={oi} onPress={() => setAssessmentAnswers(p => ({ ...p, [String(q.question_id)]: oi }))} style={{ borderWidth: 1, borderColor: sel ? C.primary : C.border, backgroundColor: sel ? C.pillBlueBg : C.card, borderRadius: 8, padding: 10 }} data-testid={`ai-learning-hub-assessment-question-${qi}-option-${oi}`} testID={`ai-learning-hub-assessment-question-${qi}-option-${oi}`}>
                          <Text style={{ color: sel ? C.primary : C.textSec, fontSize: 12, fontWeight: sel ? '700' : '500', fontFamily: BF }}>{opt}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              ))}
            </ScrollView>

            {assessmentResult && (
              <View style={{ marginTop: 12, backgroundColor: assessmentResult.passed ? C.pillEmeraldBg : C.pillAmberBg, borderWidth: 1, borderColor: assessmentResult.passed ? C.pillEmeraldBorder : C.pillAmberBorder, borderRadius: 10, padding: 12 }} data-testid="ai-learning-hub-assessment-result-card" testID="ai-learning-hub-assessment-result-card">
                <Text style={{ color: assessmentResult.passed ? C.success : C.warning, fontSize: 13, fontWeight: '800', fontFamily: BF }} data-testid="ai-learning-hub-assessment-result-message" testID="ai-learning-hub-assessment-result-message">{assessmentResult.passed ? 'Passed! Certificate can be generated.' : 'Not passed yet. Review and retry.'}</Text>
                <Text style={{ color: C.textSec, marginTop: 4, fontSize: 11, fontFamily: BF }} data-testid="ai-learning-hub-assessment-result-score" testID="ai-learning-hub-assessment-result-score">Score {num(assessmentResult.score_pct)}% | Pass mark {num(assessmentResult.passing_score_pct || 70)}%</Text>
              </View>
            )}

            <View style={{ marginTop: 16, flexDirection: 'row', gap: 8 }}>
              <PrimaryBtn label="Submit Assessment" onPress={submitAssessment} busy={busyId === `assessment-${assessmentTargetEnrollment?.course_id}`} testId="ai-learning-hub-assessment-submit-button" />
              <SecondaryBtn label="Close" onPress={() => setAssessmentTargetEnrollment(null)} testId="ai-learning-hub-assessment-cancel-button" />
            </View>
          </View>
        </View>
      </Modal>

      {/* ═══ LESSON PLAYER MODAL ═══ */}
      <Modal visible={Boolean(lessonPlayer)} transparent animationType="slide" onRequestClose={closeLessonPlayer}>
        <View style={{ flex: 1, backgroundColor: C.overlay, justifyContent: 'center', padding: 16 }} data-testid="ai-learning-hub-lesson-player-modal" testID="ai-learning-hub-lesson-player-modal">
          <View style={{ width: '100%', maxWidth: 960, alignSelf: 'center', backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 24 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '900', fontFamily: HF }} data-testid="ai-learning-hub-lesson-player-title" testID="ai-learning-hub-lesson-player-title">Lesson Playback</Text>
              <TouchableOpacity onPress={closeLessonPlayer} data-testid="ai-learning-hub-lesson-player-close-button" testID="ai-learning-hub-lesson-player-close-button"><Ionicons name="close" size={20} color={C.muted} /></TouchableOpacity>
            </View>
            <Text style={{ color: C.text, marginTop: 8, fontSize: 14, fontWeight: '700', fontFamily: BF }} data-testid="ai-learning-hub-lesson-player-lesson-title" testID="ai-learning-hub-lesson-player-lesson-title">{lessonPlayer?.title || 'Lesson'}</Text>
            <Text style={{ color: C.muted, marginTop: 4, fontSize: 12, fontFamily: MF }} data-testid="ai-learning-hub-lesson-player-position" testID="ai-learning-hub-lesson-player-position">{fmtDur(lessonPlayer?.positionSeconds || 0)} / {fmtDur(lessonPlayer?.durationSeconds || 0)}</Text>

            <ProgressBar pct={lessonPlayer?.durationSeconds ? ((lessonPlayer.positionSeconds || 0) / lessonPlayer.durationSeconds) * 100 : 0} />

            <View style={{ marginTop: 16, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <PrimaryBtn label={lessonPlayer?.playing ? 'Pause' : 'Play'} onPress={togglePlay} icon={lessonPlayer?.playing ? 'pause-outline' : 'play-outline'} testId="ai-learning-hub-lesson-player-play-pause-button" small />
              <SecondaryBtn label="-15s" onPress={() => seekPlayer(-15)} icon="play-back-outline" testId="ai-learning-hub-lesson-player-seek-back-button" small />
              <SecondaryBtn label="+15s" onPress={() => seekPlayer(15)} icon="play-forward-outline" testId="ai-learning-hub-lesson-player-seek-forward-button" small />
              <PrimaryBtn label="Complete" onPress={markComplete} icon="checkmark-outline" testId="ai-learning-hub-lesson-player-complete-button" small style={{ backgroundColor: C.success }} />
              <SecondaryBtn label="Open Video" onPress={() => openExt(lessonPlayer?.playbackUrl || '', setError)} icon="open-outline" testId="ai-learning-hub-lesson-player-open-external-button" small />
            </View>
          </View>
        </View>
      </Modal>

      <CelebrationOverlay
        payload={celebration}
        onNext={() => { const c = celebration; setCelebration(null); if (c?.nextLesson) { void openCourseVideo(String(c.courseId), c.nextLesson); } }}
        onClose={() => setCelebration(null)}
      />

      <CertificatePrintLayoutModal
        visible={Boolean(certificatePrintTarget)}
        onClose={() => setCertificatePrintTarget(null)}
        onSelect={(layout) => { void downloadCertificatePdf(String(certificatePrintTarget?.verification_id || ''), layout); }}
        colors={{ ...C, paper: C.paper, muted: C.muted, borderSoft: C.borderSoft, soft: C.soft }}
        busy={busyId.startsWith(`download-cert-${String(certificatePrintTarget?.verification_id || '')}`)}
        prefix="ai-learning-hub"
        previewUrl={certificatePrintTarget?.public_png_url || certificatePrintTarget?.preview_image_url || certificatePrintTarget?.thumbnail_image_url || ''}
      />
    </View>
  );
};
