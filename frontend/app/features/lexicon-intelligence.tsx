import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Alert,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

type WordQuiz = {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
};

type DailyWord = {
  word_id: string;
  domain: string;
  difficulty: string;
  word: string;
  part_of_speech: string;
  definition: string;
  pronunciation: string;
  syllables: string;
  etymology: string;
  memory_hook: string;
  business_value: string;
  synonyms: string[];
  antonyms: string[];
  examples: string[];
  micro_challenge: string;
  quiz: WordQuiz;
  source: string;
  created_at: string;
};

type SavedWord = {
  word_id: string;
  word: string;
  part_of_speech: string;
  definition: string;
  next_review_at?: string;
  review_count: number;
  mastery_score: number;
};

type UsageCoachResult = {
  clarity_score: number;
  accuracy_score: number;
  strengths: string[];
  improvements: string[];
  rewrite_suggestion: string;
  word: string;
};

type BusinessBrief = {
  headline: string;
  email_snippet: string;
  meeting_talking_point: string;
  sales_pitch_line: string;
  leadership_phrase: string;
  confidence_tip: string;
};

type Capability = {
  capability_id: string;
  title: string;
  description: string;
};

type WeeklyChallenge = {
  challenge_id: string;
  week_key: string;
  title: string;
  objective: string;
  reward: string;
  ends_at: string;
  reward_tiers?: RewardTier[];
};

type RewardTier = {
  tier: string;
  min_points: number;
  label: string;
  perk: string;
};

type LeaderboardRow = {
  rank: number;
  user_id: string;
  display_name: string;
  points: number;
  submissions: number;
  tier?: string;
  tier_label?: string;
  perks_unlocked?: string[];
};

type TemplateItem = {
  template_id: string;
  title: string;
  description: string;
  domain: string;
  difficulty: string;
  usage_context: string;
  business_context: string;
  target_outcome?: string;
};

type BatchJob = {
  job_id: string;
  status: string;
  count: number;
  domains?: string[];
  difficulty?: string;
  created_at?: string;
};

type SnapshotItem = {
  snapshot_id: string;
  name: string;
  plan: string;
  saved_words_count: number;
  created_at?: string;
};

type RecommendationItem = {
  recommendation_id: string;
  priority: string;
  title: string;
  reason: string;
  cta: string;
};

type BootstrapPayload = {
  plan: string;
  scope_label: string;
  limits: Record<string, number>;
  daily_word: DailyWord;
  saved_words: SavedWord[];
  review_queue: SavedWord[];
  profile: {
    streak_days: number;
    xp_total: number;
    words_mastered: number;
    last_active_day: string;
  };
  usage_summary: {
    today_usage: Record<string, number>;
    words_generated_30d: number;
    saved_words: number;
  };
  weekly_challenge?: WeeklyChallenge;
  weekly_challenge_entry?: {
    points?: number;
    submissions?: number;
    rank?: number | null;
    tier?: string;
    tier_label?: string;
    perks_unlocked?: string[];
    next_tier?: RewardTier | null;
  };
  leaderboard_preview?: LeaderboardRow[];
  capabilities: Capability[];
  business_contexts: string[];
};

type QuizResult = {
  is_correct: boolean;
  score: number;
  feedback: string;
  explanation: string;
  correct_answer: string;
};

const DIFFICULTY_OPTIONS = ['adaptive', 'beginner', 'intermediate', 'advanced'];
const DOMAIN_OPTIONS = ['business', 'technology', 'legal', 'healthcare', 'leadership'];

export default function LexiconIntelligenceScreen() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.features.lexicon-intelligence.probe');
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [bootstrap, setBootstrap] = useState<BootstrapPayload | null>(null);
  const [bootstrapError, setBootstrapError] = useState('');
  const [domain, setDomain] = useState('business');
  const [difficulty, setDifficulty] = useState('adaptive');
  const [activeWordId, setActiveWordId] = useState('');
  const [quizAnswer, setQuizAnswer] = useState('');
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [usageSentence, setUsageSentence] = useState('');
  const [usageContext, setUsageContext] = useState('email');
  const [usageCoachResult, setUsageCoachResult] = useState<UsageCoachResult | null>(null);
  const [businessContext, setBusinessContext] = useState('meeting');
  const [businessBrief, setBusinessBrief] = useState<BusinessBrief | null>(null);
  const [challengeSubmission, setChallengeSubmission] = useState('');
  const [challengeResult, setChallengeResult] = useState<{ points_awarded: number; rank?: number | null; tier_label?: string; perks_unlocked?: string[] } | null>(null);
  const [leaderboardRows, setLeaderboardRows] = useState<LeaderboardRow[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [recommendedTemplateIds, setRecommendedTemplateIds] = useState<string[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [batchDomainsInput, setBatchDomainsInput] = useState('business, leadership, technology');
  const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [exportSummary, setExportSummary] = useState('');
  const [showTierConfetti, setShowTierConfetti] = useState(false);
  const tierProgressAnim = useRef(new Animated.Value(0)).current;
  const confettiAnim = useRef(new Animated.Value(0)).current;
  const prevTierRef = useRef<string>('');

  const cardStyle = {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 16,
    marginHorizontal: 16,
    marginBottom: 14,
  } as any;

  const inputStyle = {
    backgroundColor: colors.bgSoft,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.text,
    fontSize: 13,
  } as any;

  const selectedWord = useMemo(() => {
    if (!bootstrap) return null;
    if (bootstrap.daily_word?.word_id === activeWordId) return bootstrap.daily_word;
    const found = bootstrap.saved_words.find((item) => item.word_id === activeWordId);
    if (found) {
      return {
        ...bootstrap.daily_word,
        ...found,
      } as DailyWord;
    }
    return bootstrap.daily_word || null;
  }, [bootstrap, activeWordId]);

  const loadBootstrap = useCallback(async () => {
    try {
      setLoading(true);
      setBootstrapError('');
      const response = await api.get('/word-forge/bootstrap');
      const payload: BootstrapPayload = response.data;
      setBootstrap(payload);
      setActiveWordId(payload?.daily_word?.word_id || '');
      setLeaderboardRows(payload?.leaderboard_preview || []);
      if (Array.isArray(payload?.business_contexts) && payload.business_contexts[0]) {
        setBusinessContext(String(payload.business_contexts[0]));
      }
    } catch (error: any) {
      const message = error?.response?.data?.detail || tx('lexiconHub.alert.bootstrap.body', 'Please retry in a few seconds.');
      setBootstrapError(String(message));
      Alert.alert(
        tx('lexiconHub.alert.bootstrap.title', 'Unable to load Lexicon Intelligence Hub'),
        message,
      );
    } finally {
      setLoading(false);
    }
  }, [tx]);

  const loadTemplates = useCallback(async () => {
    try {
      const response = await api.get('/word-forge/templates');
      const nextTemplates: TemplateItem[] = Array.isArray(response?.data?.templates) ? response.data.templates : [];
      setTemplates(nextTemplates);
      setRecommendedTemplateIds(Array.isArray(response?.data?.recommended_template_ids) ? response.data.recommended_template_ids : []);
      if (!selectedTemplateId && nextTemplates[0]?.template_id) {
        setSelectedTemplateId(nextTemplates[0].template_id);
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/lexicon-intelligence.tsx#loadTemplates',
        error,
        message: tx('lexiconHub.templates.loadFail', 'Could not load templates right now.'),
        notifyMode: 'silent',
      });
    }
  }, [selectedTemplateId, tx]);

  const loadBatchJobs = useCallback(async () => {
    try {
      const response = await api.get('/word-forge/batch/jobs', { params: { limit: 12 } });
      setBatchJobs(Array.isArray(response?.data?.jobs) ? response.data.jobs : []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/lexicon-intelligence.tsx#loadBatchJobs',
        error,
        message: tx('lexiconHub.batch.jobsFail', 'Could not load batch queue.'),
        notifyMode: 'silent',
      });
    }
  }, [tx]);

  const loadSnapshots = useCallback(async () => {
    try {
      const response = await api.get('/word-forge/snapshots', { params: { limit: 12 } });
      setSnapshots(Array.isArray(response?.data?.snapshots) ? response.data.snapshots : []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/lexicon-intelligence.tsx#loadSnapshots',
        error,
        message: tx('lexiconHub.snapshots.loadFail', 'Could not load snapshots.'),
        notifyMode: 'silent',
      });
    }
  }, [tx]);

  const loadRecommendations = useCallback(async () => {
    try {
      const response = await api.get('/word-forge/recommendations');
      setRecommendations(Array.isArray(response?.data?.recommendations) ? response.data.recommendations : []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/lexicon-intelligence.tsx#loadRecommendations',
        error,
        message: tx('lexiconHub.recommendations.loadFail', 'Could not load recommendations.'),
        notifyMode: 'silent',
      });
    }
  }, [tx]);

  useEffect(() => {
    loadBootstrap();
    loadTemplates();
    loadBatchJobs();
    loadSnapshots();
    loadRecommendations();
  }, [loadBootstrap, loadTemplates, loadBatchJobs, loadSnapshots, loadRecommendations]);

  const generateWord = async () => {
    try {
      setWorking(true);
      const response = await api.post('/word-forge/daily-word', {
        domain,
        difficulty,
      });
      const nextWord = response?.data?.word;
      setQuizResult(null);
      setQuizAnswer('');
      if (nextWord?.word_id) {
        setActiveWordId(nextWord.word_id);
      }
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.generate.title', 'Could not generate a new word'),
        error?.response?.data?.detail || tx('lexiconHub.alert.generate.body', 'Please try again.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const submitQuiz = async () => {
    if (!activeWordId || !quizAnswer.trim()) {
      Alert.alert(tx('lexiconHub.alert.quizAnswer', 'Please choose or enter an answer first.'));
      return;
    }
    try {
      setWorking(true);
      const response = await api.post('/word-forge/quiz/submit', {
        word_id: activeWordId,
        mode: 'mcq',
        answer: quizAnswer.trim(),
      });
      setQuizResult(response.data);
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.quiz.title', 'Quiz submission failed'),
        error?.response?.data?.detail || tx('lexiconHub.alert.quiz.body', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const toggleSaveWord = async (wordId: string, save: boolean) => {
    try {
      setWorking(true);
      await api.post('/word-forge/saved/toggle', {
        word_id: wordId,
        save,
      });
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.save.title', 'Unable to update saved words'),
        error?.response?.data?.detail || tx('lexiconHub.alert.save.body', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const runUsageCoach = async () => {
    if (!activeWordId || usageSentence.trim().length < 6) {
      Alert.alert(tx('lexiconHub.alert.usage.required', 'Write a sentence to get coaching feedback.'));
      return;
    }
    try {
      setWorking(true);
      const response = await api.post('/word-forge/usage-coach', {
        word_id: activeWordId,
        sentence: usageSentence.trim(),
        context_type: usageContext,
      });
      setUsageCoachResult(response.data);
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.usage.title', 'Usage coach failed'),
        error?.response?.data?.detail || tx('lexiconHub.alert.usage.body', 'Please retry in a moment.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const generateBusinessBrief = async () => {
    if (!activeWordId) {
      Alert.alert(tx('lexiconHub.alert.word.required', 'Please load a word first.'));
      return;
    }
    try {
      setWorking(true);
      const response = await api.post('/word-forge/business-brief', {
        word_id: activeWordId,
        context_type: businessContext,
      });
      setBusinessBrief(response.data?.brief || null);
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.brief.title', 'Could not generate business brief'),
        error?.response?.data?.detail || tx('lexiconHub.alert.brief.body', 'Please retry shortly.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const refreshLeaderboard = async () => {
    try {
      const response = await api.get('/word-forge/leaderboard');
      setLeaderboardRows(response?.data?.leaderboard || []);
    } catch (error) { handleAppRecoverableError({ scope: 'features/lexicon-intelligence.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const applyTemplate = async () => {
    if (!selectedTemplateId) {
      Alert.alert(tx('lexiconHub.templates.select', 'Please select a template first.'));
      return;
    }
    try {
      setWorking(true);
      const response = await api.post('/word-forge/templates/apply', { template_id: selectedTemplateId });
      const template = response?.data?.template || null;
      if (template?.domain) setDomain(String(template.domain));
      if (template?.difficulty) setDifficulty(String(template.difficulty));
      if (template?.usage_context) setUsageContext(String(template.usage_context));
      if (template?.business_context) setBusinessContext(String(template.business_context));
      Alert.alert(tx('lexiconHub.templates.applied', 'Template applied successfully.'));
      await loadBootstrap();
      await loadRecommendations();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.templates.applyFailTitle', 'Template apply failed'),
        error?.response?.data?.detail || tx('lexiconHub.templates.applyFailBody', 'Please retry in a moment.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const runBatchGenerate = async () => {
    const domains = batchDomainsInput
      .split(',')
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 8);

    if (domains.length === 0) {
      Alert.alert(tx('lexiconHub.batch.required', 'Please enter at least one domain for batch generation.'));
      return;
    }

    try {
      setWorking(true);
      const response = await api.post('/word-forge/batch/generate', {
        template_id: selectedTemplateId || null,
        domains,
        difficulty,
      });
      const count = Number(response?.data?.job?.count || response?.data?.words?.length || 0);
      setExportSummary(tx('lexiconHub.batch.success', `Batch completed: ${count} words generated.`));
      await loadBootstrap();
      await loadBatchJobs();
      await loadRecommendations();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.batch.failTitle', 'Batch generation failed'),
        error?.response?.data?.detail || tx('lexiconHub.batch.failBody', 'Please retry shortly.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const createSnapshot = async () => {
    try {
      setWorking(true);
      const response = await api.post('/word-forge/snapshots', {
        name: '',
        include_saved_words: true,
        include_leaderboard: true,
      });
      const name = response?.data?.snapshot?.name || 'Snapshot created';
      setExportSummary(`${name}`);
      await loadSnapshots();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.snapshots.createFailTitle', 'Snapshot creation failed'),
        error?.response?.data?.detail || tx('lexiconHub.snapshots.createFailBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const restoreSnapshot = async (snapshotId: string) => {
    try {
      setWorking(true);
      await api.post('/word-forge/snapshots/restore', { snapshot_id: snapshotId });
      Alert.alert(tx('lexiconHub.snapshots.restored', 'Snapshot restored to current workspace.'));
      await loadBootstrap();
      await loadSnapshots();
      await loadRecommendations();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.snapshots.restoreFailTitle', 'Snapshot restore failed'),
        error?.response?.data?.detail || tx('lexiconHub.snapshots.restoreFailBody', 'Please retry shortly.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const exportWorkspace = async (format: 'payload' | 'json' | 'csv') => {
    try {
      if (format === 'payload') {
        const response = await api.get('/word-forge/export', { params: { format: 'payload' } });
        const summary = response?.data?.summary || {};
        setExportSummary(
          tx(
            'lexiconHub.export.payloadSummary',
            `Export ready: ${summary.saved_words_count || 0} saved words · ${summary.recent_words_count || 0} recent words · ${summary.challenge_points || 0} challenge points`,
          ),
        );
        return;
      }

      const response = await api.get('/word-forge/export', {
        params: { format },
        responseType: 'blob',
      });

      const contentType = response.headers?.['content-type'] || '';
      const dataBlob = response.data instanceof Blob
        ? response.data
        : new Blob([response.data], { type: contentType || (format === 'json' ? 'application/json' : 'text/csv') });

      const filenameHeader = response.headers?.['content-disposition'] || '';
      const filenameMatch = /filename="?([^";]+)"?/i.exec(filenameHeader);
      const filename = filenameMatch?.[1] || `lexicon-intelligence-export.${format}`;

      const downloadUrl = URL.createObjectURL(dataBlob);
      const anchor = document.createElement('a');
      anchor.href = downloadUrl;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(downloadUrl);
      setExportSummary(tx('lexiconHub.export.downloadReady', `Downloaded ${format.toUpperCase()} export.`));
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.export.failTitle', 'Export failed'),
        error?.response?.data?.detail || tx('lexiconHub.export.failBody', 'Unable to export workspace now. Please retry.'),
      );
    }
  };

  const submitWeeklyChallenge = async () => {
    if (challengeSubmission.trim().length < 8) {
      Alert.alert(tx('lexiconHub.challenge.required', 'Please add a short challenge submission first.'));
      return;
    }
    try {
      setWorking(true);
      const response = await api.post('/word-forge/challenge/submit', {
        word_id: activeWordId || null,
        submission_text: challengeSubmission.trim(),
      });
      setChallengeResult({
        points_awarded: Number(response?.data?.points_awarded || 0),
        rank: response?.data?.entry?.rank ?? null,
        tier_label: response?.data?.entry?.tier_label,
        perks_unlocked: Array.isArray(response?.data?.entry?.perks_unlocked) ? response?.data?.entry?.perks_unlocked : [],
      });
      setChallengeSubmission('');
      await loadBootstrap();
      await refreshLeaderboard();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.challenge.submit.title', 'Challenge submission failed'),
        error?.response?.data?.detail || tx('lexiconHub.challenge.submit.body', 'Please retry shortly.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const completeReview = async (wordId: string, confidence: number) => {
    try {
      setWorking(true);
      await api.post('/word-forge/review/complete', {
        word_id: wordId,
        confidence,
      });
      await loadBootstrap();
    } catch (error: any) {
      Alert.alert(
        tx('lexiconHub.alert.review.title', 'Could not complete review'),
        error?.response?.data?.detail || tx('lexiconHub.alert.review.body', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const isSavedActiveWord = useMemo(() => {
    if (!bootstrap || !activeWordId) return false;
    return bootstrap.saved_words.some((item) => item.word_id === activeWordId);
  }, [bootstrap, activeWordId]);

  const featureColor = colors.accent;
  const challengePointsForAnim = Number(bootstrap?.weekly_challenge_entry?.points || 0);
  const rewardTiersForAnim = bootstrap?.weekly_challenge?.reward_tiers || [];
  const maxTierPointsForAnim = rewardTiersForAnim.length > 0
    ? Math.max(...rewardTiersForAnim.map((tier) => Number(tier.min_points || 0)))
    : 120;
  const tierProgressPercentForAnim = Math.max(0, Math.min(100, Math.round((challengePointsForAnim / Math.max(1, maxTierPointsForAnim)) * 100)));
  const activeTier = String(bootstrap?.weekly_challenge_entry?.tier || 'starter');
  const tierProgressWidth = tierProgressAnim.interpolate({
    inputRange: [0, 100],
    outputRange: ['0%', '100%'],
  });

  useEffect(() => {
    Animated.timing(tierProgressAnim, {
      toValue: tierProgressPercentForAnim,
      duration: 520,
      useNativeDriver: false,
    }).start();
  }, [tierProgressPercentForAnim, tierProgressAnim]);

  useEffect(() => {
    const previousTier = prevTierRef.current;
    if (previousTier && previousTier !== activeTier && activeTier !== 'starter') {
      setShowTierConfetti(true);
      confettiAnim.setValue(1);
      Animated.timing(confettiAnim, {
        toValue: 0,
        duration: 1300,
        useNativeDriver: false,
      }).start(() => setShowTierConfetti(false));
    }
    prevTierRef.current = activeTier;
  }, [activeTier, confettiAnim]);

  if (loading) {
    return (
      <FeatureLayout
        feature="lexicon-intelligence"
        title="Lexicon Intelligence Hub"
        subtitle="Daily communication mastery for business and life"
        icon="book"
        color={featureColor}
      >
        <View style={{ minHeight: 280, justifyContent: 'center', alignItems: 'center' }} data-testid="lexicon-hub-loading" testID="lexicon-hub-loading">
          <ActivityIndicator size="large" color={featureColor} />
          <Text style={{ marginTop: 10, color: colors.textSec }} data-testid="lexicon-hub-loading-text" testID="lexicon-hub-loading-text">
            {tx('lexiconHub.loading', 'Loading Lexicon Intelligence Hub...')}
          </Text>
        </View>
      </FeatureLayout>
    );
  }

  if (!bootstrap) {
    return (
      <FeatureLayout
        feature="lexicon-intelligence"
        title="Lexicon Intelligence Hub"
        subtitle="Daily communication mastery for business and life"
        icon="book"
        color={featureColor}
      >
        <View
          style={{ minHeight: 280, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 24 }}
          data-testid="lexicon-hub-bootstrap-error"
          testID="lexicon-hub-bootstrap-error"
        >
          <Text
            style={{ color: colors.error, fontSize: 14, textAlign: 'center', lineHeight: 22 }}
            data-testid="lexicon-hub-bootstrap-error-text"
            testID="lexicon-hub-bootstrap-error-text"
          >
            {bootstrapError || tx('lexiconHub.alert.bootstrap.body', 'Please retry in a few seconds.')}
          </Text>
          <TouchableOpacity
            style={{ marginTop: 14, borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10 }}
            onPress={loadBootstrap}
            data-testid="lexicon-hub-bootstrap-retry-button"
            testID="lexicon-hub-bootstrap-retry-button"
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>
              {tx('lexiconHub.bootstrap.retry', 'Retry Workspace Load')}
            </Text>
          </TouchableOpacity>
        </View>
      </FeatureLayout>
    );
  }

  const dailyWord = selectedWord || bootstrap.daily_word;
  const capabilityRows = bootstrap.capabilities || [];
  const usageToday = bootstrap.usage_summary?.today_usage || {};
  const weeklyChallenge = bootstrap.weekly_challenge;
  const challengeEntry = bootstrap.weekly_challenge_entry || {};
  const challengePoints = challengePointsForAnim;
  const rewardTiers = rewardTiersForAnim;
  const nextTier = challengeEntry?.next_tier as RewardTier | null | undefined;
  const leaderboardData = leaderboardRows.length > 0 ? leaderboardRows : (bootstrap.leaderboard_preview || []);
  const isWideGrid = isDesktop;

  return (
    <FeatureLayout
      feature="lexicon-intelligence"
      title="Lexicon Intelligence Hub"
      subtitle="Professional Word of the Day workspace with quiz, usage coach, and business communication tools"
      icon="book"
      color={featureColor}
    >
      <ScrollView contentContainerStyle={{ paddingVertical: 8, paddingBottom: 40 }}>
        <View style={[cardStyle, { flexDirection: isWideGrid ? 'row' : 'column', gap: 12 }]} data-testid="lexicon-hub-plan-card" testID="lexicon-hub-plan-card">
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="lexicon-hub-plan-label" testID="lexicon-hub-plan-label">
              {tx('lexiconHub.plan.label', 'Plan Scope')}
            </Text>
            <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }} data-testid="lexicon-hub-plan-value" testID="lexicon-hub-plan-value">
              {String(bootstrap.plan || 'free').toUpperCase()}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 13 }} data-testid="lexicon-hub-scope-label" testID="lexicon-hub-scope-label">
              {bootstrap.scope_label}
            </Text>
          </View>

          <View style={{ flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-kpis" testID="lexicon-hub-kpis">
            {[
              { id: 'streak', label: tx('lexiconHub.kpi.streak', 'Streak'), value: bootstrap.profile?.streak_days || 0 },
              { id: 'xp', label: tx('lexiconHub.kpi.xp', 'XP Total'), value: bootstrap.profile?.xp_total || 0 },
              { id: 'mastered', label: tx('lexiconHub.kpi.mastered', 'Words Mastered'), value: bootstrap.profile?.words_mastered || 0 },
              { id: 'generated30d', label: tx('lexiconHub.kpi.generated', 'Generated (30d)'), value: bootstrap.usage_summary?.words_generated_30d || 0 },
            ].map((item) => (
              <View
                key={item.id}
                style={{
                  minWidth: isWideGrid ? 130 : '48%',
                  flex: 1,
                  backgroundColor: colors.bgSoft,
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: colors.border,
                  padding: 10,
                }}
                data-testid={`lexicon-hub-kpi-${item.id}`}
                testID={`lexicon-hub-kpi-${item.id}`}
              >
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>{item.label}</Text>
                <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700' }}>{item.value}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-recommendations-card" testID="lexicon-hub-recommendations-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-recommendations-title" testID="lexicon-hub-recommendations-title">
            {tx('lexiconHub.recommendations.title', 'Smart Recommendations')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-recommendations-subtitle" testID="lexicon-hub-recommendations-subtitle">
            {tx('lexiconHub.recommendations.subtitle', 'Actionable next steps based on your usage and progress signals.')}
          </Text>
          <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-recommendations-list" testID="lexicon-hub-recommendations-list">
            {recommendations.length === 0 ? (
              <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="lexicon-hub-recommendations-empty" testID="lexicon-hub-recommendations-empty">
                {tx('lexiconHub.recommendations.empty', 'No recommendations yet.')}
              </Text>
            ) : (
              recommendations.map((item, idx) => (
                <View
                  key={`${item.recommendation_id}-${idx}`}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}
                  data-testid={`lexicon-hub-recommendation-row-${idx}`}
                  testID={`lexicon-hub-recommendation-row-${idx}`}
                >
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid={`lexicon-hub-recommendation-title-${idx}`} testID={`lexicon-hub-recommendation-title-${idx}`}>
                    {item.title}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid={`lexicon-hub-recommendation-reason-${idx}`} testID={`lexicon-hub-recommendation-reason-${idx}`}>
                    {item.reason}
                  </Text>
                  <Text style={{ color: colors.successText, fontSize: 11, marginTop: 5, fontWeight: '700' }} data-testid={`lexicon-hub-recommendation-cta-${idx}`} testID={`lexicon-hub-recommendation-cta-${idx}`}>
                    {item.cta}
                  </Text>
                </View>
              ))
            )}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-template-library-card" testID="lexicon-hub-template-library-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-template-library-title" testID="lexicon-hub-template-library-title">
            {tx('lexiconHub.templates.title', 'Template Library')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-template-library-subtitle" testID="lexicon-hub-template-library-subtitle">
            {tx('lexiconHub.templates.subtitle', 'Apply prebuilt communication tracks for faster outcomes.')}
          </Text>
          <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-template-list" testID="lexicon-hub-template-list">
            {templates.map((template, idx) => {
              const selected = selectedTemplateId === template.template_id;
              const recommended = recommendedTemplateIds.includes(template.template_id);
              return (
                <TouchableOpacity
                  key={template.template_id}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: selected ? colors.primary : colors.border,
                    backgroundColor: selected ? `${colors.primary}14` : colors.bgSoft,
                    padding: 10,
                  }}
                  onPress={() => setSelectedTemplateId(template.template_id)}
                  data-testid={`lexicon-hub-template-row-${idx}`}
                  testID={`lexicon-hub-template-row-${idx}`}
                >
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }} data-testid={`lexicon-hub-template-title-${idx}`} testID={`lexicon-hub-template-title-${idx}`}>
                    {template.title}{recommended ? ' · Recommended' : ''}
                  </Text>
                  <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 11 }} data-testid={`lexicon-hub-template-description-${idx}`} testID={`lexicon-hub-template-description-${idx}`}>
                    {template.description}
                  </Text>
                  <Text style={{ color: colors.textMuted, marginTop: 5, fontSize: 11 }} data-testid={`lexicon-hub-template-meta-${idx}`} testID={`lexicon-hub-template-meta-${idx}`}>
                    {template.domain} · {template.difficulty} · {template.target_outcome || ''}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TouchableOpacity
            style={{ marginTop: 10, borderRadius: 10, backgroundColor: colors.primary, paddingVertical: 11, alignItems: 'center' }}
            onPress={applyTemplate}
            disabled={working}
            data-testid="lexicon-hub-template-apply-button"
            testID="lexicon-hub-template-apply-button"
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>
              {tx('lexiconHub.templates.apply', 'Apply Selected Template')}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-batch-studio-card" testID="lexicon-hub-batch-studio-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-batch-studio-title" testID="lexicon-hub-batch-studio-title">
            {tx('lexiconHub.batch.title', 'Batch Generation Studio')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-batch-studio-subtitle" testID="lexicon-hub-batch-studio-subtitle">
            {tx('lexiconHub.batch.subtitle', 'Generate multiple words in one run with queue tracking.')}
          </Text>
          <TextInput
            style={[inputStyle, { marginTop: 10 }]}
            value={batchDomainsInput}
            onChangeText={setBatchDomainsInput}
            placeholder={tx('lexiconHub.batch.placeholder', 'business, leadership, technology')}
            placeholderTextColor={colors.textMuted}
            data-testid="lexicon-hub-batch-domains-input"
            testID="lexicon-hub-batch-domains-input"
          />
          <TouchableOpacity
            style={{ marginTop: 10, borderRadius: 10, backgroundColor: colors.success, paddingVertical: 11, alignItems: 'center' }}
            onPress={runBatchGenerate}
            disabled={working}
            data-testid="lexicon-hub-batch-run-button"
            testID="lexicon-hub-batch-run-button"
          >
            <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }}>
              {tx('lexiconHub.batch.run', 'Run Batch Generate')}
            </Text>
          </TouchableOpacity>

          <View style={{ marginTop: 10, gap: 7 }} data-testid="lexicon-hub-batch-jobs-list" testID="lexicon-hub-batch-jobs-list">
            {batchJobs.length === 0 ? (
              <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="lexicon-hub-batch-jobs-empty" testID="lexicon-hub-batch-jobs-empty">
                {tx('lexiconHub.batch.empty', 'No batch jobs yet.')}
              </Text>
            ) : (
              batchJobs.map((job, idx) => (
                <View
                  key={job.job_id}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }}
                  data-testid={`lexicon-hub-batch-job-row-${idx}`}
                  testID={`lexicon-hub-batch-job-row-${idx}`}
                >
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }} data-testid={`lexicon-hub-batch-job-id-${idx}`} testID={`lexicon-hub-batch-job-id-${idx}`}>
                    {job.job_id}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 3 }} data-testid={`lexicon-hub-batch-job-meta-${idx}`} testID={`lexicon-hub-batch-job-meta-${idx}`}>
                    {job.status} · {job.count} words · {(job.domains || []).join(', ')}
                  </Text>
                </View>
              ))
            )}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-snapshots-card" testID="lexicon-hub-snapshots-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-snapshots-title" testID="lexicon-hub-snapshots-title">
            {tx('lexiconHub.snapshots.title', 'Workspace Snapshots')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-snapshots-subtitle" testID="lexicon-hub-snapshots-subtitle">
            {tx('lexiconHub.snapshots.subtitle', 'Save and restore your workspace state instantly.')}
          </Text>
          <TouchableOpacity
            style={{ marginTop: 10, borderRadius: 10, backgroundColor: colors.primary, paddingVertical: 11, alignItems: 'center' }}
            onPress={createSnapshot}
            disabled={working}
            data-testid="lexicon-hub-snapshot-create-button"
            testID="lexicon-hub-snapshot-create-button"
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>
              {tx('lexiconHub.snapshots.create', 'Create Snapshot')}
            </Text>
          </TouchableOpacity>

          <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-snapshot-list" testID="lexicon-hub-snapshot-list">
            {snapshots.length === 0 ? (
              <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="lexicon-hub-snapshot-empty" testID="lexicon-hub-snapshot-empty">
                {tx('lexiconHub.snapshots.empty', 'No snapshots created yet.')}
              </Text>
            ) : (
              snapshots.map((snapshot, idx) => (
                <View
                  key={snapshot.snapshot_id}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}
                  data-testid={`lexicon-hub-snapshot-row-${idx}`}
                  testID={`lexicon-hub-snapshot-row-${idx}`}
                >
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }} data-testid={`lexicon-hub-snapshot-name-${idx}`} testID={`lexicon-hub-snapshot-name-${idx}`}>
                    {snapshot.name}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid={`lexicon-hub-snapshot-meta-${idx}`} testID={`lexicon-hub-snapshot-meta-${idx}`}>
                    {snapshot.plan.toUpperCase()} · {snapshot.saved_words_count} saved words
                  </Text>
                  <TouchableOpacity
                    style={{ marginTop: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.success, backgroundColor: `${colors.success}16`, paddingVertical: 7, alignItems: 'center' }}
                    onPress={() => restoreSnapshot(snapshot.snapshot_id)}
                    disabled={working}
                    data-testid={`lexicon-hub-snapshot-restore-button-${idx}`}
                    testID={`lexicon-hub-snapshot-restore-button-${idx}`}
                  >
                    <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 11 }}>
                      {tx('lexiconHub.snapshots.restore', 'Restore Snapshot')}
                    </Text>
                  </TouchableOpacity>
                </View>
              ))
            )}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-export-center-card" testID="lexicon-hub-export-center-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-export-center-title" testID="lexicon-hub-export-center-title">
            {tx('lexiconHub.export.title', 'Export Center')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-export-center-subtitle" testID="lexicon-hub-export-center-subtitle">
            {tx('lexiconHub.export.subtitle', 'Download workspace reports for offline analysis.')}
          </Text>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-export-actions" testID="lexicon-hub-export-actions">
            <TouchableOpacity
              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }}
              onPress={() => exportWorkspace('payload')}
              data-testid="lexicon-hub-export-payload-button"
              testID="lexicon-hub-export-payload-button"
            >
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>Payload</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }}
              onPress={() => exportWorkspace('json')}
              data-testid="lexicon-hub-export-json-button"
              testID="lexicon-hub-export-json-button"
            >
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>JSON</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }}
              onPress={() => exportWorkspace('csv')}
              data-testid="lexicon-hub-export-csv-button"
              testID="lexicon-hub-export-csv-button"
            >
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>CSV</Text>
            </TouchableOpacity>
          </View>
          <Text style={{ color: colors.textMuted, marginTop: 10, fontSize: 11 }} data-testid="lexicon-hub-export-summary" testID="lexicon-hub-export-summary">
            {exportSummary || tx('lexiconHub.export.summaryEmpty', 'No export run yet.')}
          </Text>
        </View>

        <View style={[cardStyle, { paddingVertical: 12 }]} data-testid="lexicon-hub-tier-progress-card" testID="lexicon-hub-tier-progress-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }} data-testid="lexicon-hub-tier-progress-title" testID="lexicon-hub-tier-progress-title">
              {tx('lexiconHub.tierProgress.title', 'Tier Progress')}: {challengeEntry?.tier_label || tx('lexiconHub.tierProgress.starter', 'Starter')}
            </Text>
            <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }} data-testid="lexicon-hub-tier-progress-points" testID="lexicon-hub-tier-progress-points">
              {challengePoints} pts
            </Text>
          </View>

          <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid="lexicon-hub-tier-progress-subtitle" testID="lexicon-hub-tier-progress-subtitle">
            {nextTier
              ? `${tx('lexiconHub.tierProgress.next', 'Next')}: ${nextTier.label} (${nextTier.min_points} pts)`
              : tx('lexiconHub.tierProgress.max', 'Maximum tier unlocked this week')}
          </Text>

          {showTierConfetti ? (
            <View
              pointerEvents="none"
              style={{
                position: 'absolute',
                top: 8,
                right: 10,
                left: 10,
                height: 36,
              }}
              data-testid="lexicon-hub-tier-confetti"
              testID="lexicon-hub-tier-confetti"
            >
              {Array.from({ length: 14 }).map((_, idx) => {
                const left = `${(idx * 7) % 96}%`;
                const size = 4 + (idx % 3);
                const tint = idx % 3 === 0 ? colors.primary : idx % 3 === 1 ? colors.success : colors.warning;
                return (
                  <Animated.View
                    key={`tier-confetti-${idx}`}
                    style={{
                      position: 'absolute',
                      left,
                      top: (idx % 4) * 4,
                      width: size,
                      height: size,
                      borderRadius: 2,
                      backgroundColor: tint,
                      opacity: confettiAnim,
                      transform: [
                        {
                          translateY: confettiAnim.interpolate({
                            inputRange: [0, 1],
                            outputRange: [-24, 0],
                          }),
                        },
                        {
                          rotate: `${idx * 18}deg`,
                        },
                      ],
                    }}
                  />
                );
              })}
            </View>
          ) : null}

          <View
            style={{
              marginTop: 10,
              height: 9,
              borderRadius: 999,
              backgroundColor: colors.bgSoft,
              borderWidth: 1,
              borderColor: colors.border,
              overflow: 'hidden',
            }}
            data-testid="lexicon-hub-tier-progress-track"
            testID="lexicon-hub-tier-progress-track"
          >
            <Animated.View
              style={{
                width: tierProgressWidth,
                height: '100%',
                backgroundColor: colors.success,
              }}
              data-testid="lexicon-hub-tier-progress-fill"
              testID="lexicon-hub-tier-progress-fill"
            />
          </View>

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 7 }} data-testid="lexicon-hub-tier-progress-tiers" testID="lexicon-hub-tier-progress-tiers">
            {rewardTiers.map((tier) => {
              const unlocked = challengePoints >= Number(tier.min_points || 0);
              return (
                <View
                  key={tier.tier}
                  style={{
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: unlocked ? colors.success : colors.border,
                    backgroundColor: unlocked ? `${colors.success}20` : colors.bgSoft,
                    paddingHorizontal: 9,
                    paddingVertical: 5,
                  }}
                  data-testid={`lexicon-hub-tier-pill-${tier.tier}`}
                  testID={`lexicon-hub-tier-pill-${tier.tier}`}
                >
                  <Text style={{ color: unlocked ? colors.successText : colors.textSec, fontSize: 10, fontWeight: '700' }}>
                    {tier.label}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-daily-word-card" testID="lexicon-hub-daily-word-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="lexicon-hub-daily-word-label" testID="lexicon-hub-daily-word-label">
                {tx('lexiconHub.daily.label', 'Today\'s Word')}
              </Text>
              <Text style={{ color: colors.text, fontSize: 30, fontWeight: '800' }} data-testid="lexicon-hub-daily-word" testID="lexicon-hub-daily-word">
                {dailyWord?.word || '-'}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="lexicon-hub-daily-word-meta" testID="lexicon-hub-daily-word-meta">
                {(dailyWord?.part_of_speech || '').toUpperCase()} · {dailyWord?.pronunciation || '-'} · {dailyWord?.syllables || '-'}
              </Text>
            </View>
            <TouchableOpacity
              style={{
                backgroundColor: colors.primary,
                borderRadius: 11,
                paddingHorizontal: 12,
                paddingVertical: 10,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
              }}
              onPress={generateWord}
              disabled={working}
              data-testid="lexicon-hub-generate-word-button"
              testID="lexicon-hub-generate-word-button"
            >
              <Ionicons name="sparkles-outline" size={14} color={colors.primaryText} />
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>
                {tx('lexiconHub.daily.generate', 'Generate New')}
              </Text>
            </TouchableOpacity>
          </View>

          <Text style={{ color: colors.text, fontSize: 14, marginTop: 12, lineHeight: 21 }} data-testid="lexicon-hub-definition" testID="lexicon-hub-definition">
            {dailyWord?.definition}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 8 }} data-testid="lexicon-hub-etymology" testID="lexicon-hub-etymology">
            {dailyWord?.etymology}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 8 }} data-testid="lexicon-hub-memory-hook" testID="lexicon-hub-memory-hook">
            {dailyWord?.memory_hook}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 8 }} data-testid="lexicon-hub-business-value" testID="lexicon-hub-business-value">
            {dailyWord?.business_value}
          </Text>

          <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-domain-controls" testID="lexicon-hub-domain-controls">
            {DOMAIN_OPTIONS.map((item) => (
              <TouchableOpacity
                key={item}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: domain === item ? colors.primary : colors.border,
                  backgroundColor: domain === item ? `${colors.primary}20` : colors.bgSoft,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                }}
                onPress={() => setDomain(item)}
                data-testid={`lexicon-hub-domain-${item}`}
                testID={`lexicon-hub-domain-${item}`}
              >
                <Text style={{ color: domain === item ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-difficulty-controls" testID="lexicon-hub-difficulty-controls">
            {DIFFICULTY_OPTIONS.map((item) => (
              <TouchableOpacity
                key={item}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: difficulty === item ? colors.success : colors.border,
                  backgroundColor: difficulty === item ? `${colors.success}20` : colors.bgSoft,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                }}
                onPress={() => setDifficulty(item)}
                data-testid={`lexicon-hub-difficulty-${item}`}
                testID={`lexicon-hub-difficulty-${item}`}
              >
                <Text style={{ color: difficulty === item ? colors.success : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ marginTop: 12, flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              style={{
                flex: 1,
                backgroundColor: isSavedActiveWord ? `${colors.warning}20` : `${colors.success}20`,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: isSavedActiveWord ? colors.warning : colors.success,
                paddingVertical: 10,
                alignItems: 'center',
              }}
              onPress={() => toggleSaveWord(activeWordId, !isSavedActiveWord)}
              data-testid="lexicon-hub-toggle-save-button"
              testID="lexicon-hub-toggle-save-button"
            >
              <Text style={{ color: isSavedActiveWord ? colors.warningText : colors.successText, fontWeight: '700', fontSize: 12 }}>
                {isSavedActiveWord ? tx('lexiconHub.saved.remove', 'Remove from Vault') : tx('lexiconHub.saved.add', 'Save to Vault')}
              </Text>
            </TouchableOpacity>
            <View
              style={{
                flex: 1,
                backgroundColor: colors.bgSoft,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: colors.border,
                paddingVertical: 10,
                alignItems: 'center',
              }}
              data-testid="lexicon-hub-micro-challenge"
              testID="lexicon-hub-micro-challenge"
            >
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '600' }}>{dailyWord?.micro_challenge}</Text>
            </View>
          </View>

          <View style={{ marginTop: 12 }} data-testid="lexicon-hub-synonyms" testID="lexicon-hub-synonyms">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('lexiconHub.synonyms', 'Synonyms')}</Text>
            <View style={{ marginTop: 6, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {(dailyWord?.synonyms || []).map((item, idx) => (
                <View key={`${item}-${idx}`} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: `${colors.primary}18` }}>
                  <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '600' }}>{item}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ marginTop: 12 }} data-testid="lexicon-hub-antonyms" testID="lexicon-hub-antonyms">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('lexiconHub.antonyms', 'Antonyms')}</Text>
            <View style={{ marginTop: 6, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {(dailyWord?.antonyms || []).map((item, idx) => (
                <View key={`${item}-${idx}`} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: `${colors.error}18` }}>
                  <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }}>{item}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ marginTop: 12 }} data-testid="lexicon-hub-examples" testID="lexicon-hub-examples">
            {(dailyWord?.examples || []).map((line, idx) => (
              <Text key={`${idx}-${line}`} style={{ color: colors.textSec, fontSize: 12, lineHeight: 20, marginBottom: 4 }} data-testid={`lexicon-hub-example-${idx}`} testID={`lexicon-hub-example-${idx}`}>
                • {line}
              </Text>
            ))}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-quiz-card" testID="lexicon-hub-quiz-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-quiz-title" testID="lexicon-hub-quiz-title">
            {tx('lexiconHub.quiz.title', 'Adaptive Quiz Loop')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6 }} data-testid="lexicon-hub-quiz-question" testID="lexicon-hub-quiz-question">
            {dailyWord?.quiz?.question}
          </Text>

          <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-quiz-options" testID="lexicon-hub-quiz-options">
            {(dailyWord?.quiz?.options || []).map((option, idx) => {
              const selected = quizAnswer === option;
              return (
                <TouchableOpacity
                  key={`${option}-${idx}`}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: selected ? colors.primary : colors.border,
                    backgroundColor: selected ? `${colors.primary}18` : colors.bgSoft,
                    paddingHorizontal: 12,
                    paddingVertical: 10,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 8,
                  }}
                  onPress={() => setQuizAnswer(option)}
                  data-testid={`lexicon-hub-quiz-option-${idx}`}
                  testID={`lexicon-hub-quiz-option-${idx}`}
                >
                  <Ionicons name={selected ? 'radio-button-on' : 'radio-button-off'} size={14} color={selected ? colors.primary : colors.textMuted} />
                  <Text style={{ color: selected ? colors.primary : colors.textSec, fontSize: 12, flex: 1 }}>{option}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity
            style={{
              marginTop: 12,
              borderRadius: 10,
              backgroundColor: colors.primary,
              paddingVertical: 11,
              alignItems: 'center',
            }}
            onPress={submitQuiz}
            disabled={working}
            data-testid="lexicon-hub-quiz-submit"
            testID="lexicon-hub-quiz-submit"
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>{tx('lexiconHub.quiz.submit', 'Submit Quiz')}</Text>
          </TouchableOpacity>

          {quizResult ? (
            <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: quizResult.is_correct ? colors.success : colors.warning, backgroundColor: quizResult.is_correct ? `${colors.success}14` : `${colors.warning}14`, padding: 12 }} data-testid="lexicon-hub-quiz-result" testID="lexicon-hub-quiz-result">
              <Text style={{ color: quizResult.is_correct ? colors.successText : colors.warningText, fontWeight: '700' }} data-testid="lexicon-hub-quiz-score" testID="lexicon-hub-quiz-score">
                {quizResult.is_correct ? tx('lexiconHub.quiz.correct', 'Correct') : tx('lexiconHub.quiz.retry', 'Needs improvement')} · {quizResult.score}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }} data-testid="lexicon-hub-quiz-feedback" testID="lexicon-hub-quiz-feedback">
                {quizResult.feedback}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="lexicon-hub-quiz-explanation" testID="lexicon-hub-quiz-explanation">
                {quizResult.explanation}
              </Text>
            </View>
          ) : null}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-usage-coach-card" testID="lexicon-hub-usage-coach-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>
            {tx('lexiconHub.usageCoach.title', 'Sentence Usage Coach')}
          </Text>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-usage-contexts" testID="lexicon-hub-usage-contexts">
            {['email', 'meeting', 'sales', 'negotiation', 'presentation'].map((item) => (
              <TouchableOpacity
                key={item}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: usageContext === item ? colors.primary : colors.border,
                  backgroundColor: usageContext === item ? `${colors.primary}20` : colors.bgSoft,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                }}
                onPress={() => setUsageContext(item)}
                data-testid={`lexicon-hub-usage-context-${item}`}
                testID={`lexicon-hub-usage-context-${item}`}
              >
                <Text style={{ color: usageContext === item ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput
            style={[inputStyle, { minHeight: 96, marginTop: 10, textAlignVertical: 'top' }]}
            multiline
            value={usageSentence}
            onChangeText={setUsageSentence}
            placeholder={tx('lexiconHub.usageCoach.placeholder', 'Write one sentence using the selected word...')}
            placeholderTextColor={colors.textMuted}
            data-testid="lexicon-hub-usage-sentence-input"
            testID="lexicon-hub-usage-sentence-input"
          />
          <TouchableOpacity
            style={{
              marginTop: 10,
              borderRadius: 10,
              backgroundColor: colors.primary,
              paddingVertical: 11,
              alignItems: 'center',
            }}
            onPress={runUsageCoach}
            disabled={working}
            data-testid="lexicon-hub-run-usage-coach"
            testID="lexicon-hub-run-usage-coach"
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>{tx('lexiconHub.usageCoach.run', 'Run Usage Coach')}</Text>
          </TouchableOpacity>

          {usageCoachResult ? (
            <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="lexicon-hub-usage-coach-result" testID="lexicon-hub-usage-coach-result">
              <Text style={{ color: colors.text, fontWeight: '700' }} data-testid="lexicon-hub-usage-coach-scores" testID="lexicon-hub-usage-coach-scores">
                {tx('lexiconHub.usageCoach.clarity', 'Clarity')}: {usageCoachResult.clarity_score} · {tx('lexiconHub.usageCoach.accuracy', 'Accuracy')}: {usageCoachResult.accuracy_score}
              </Text>
              {(usageCoachResult.strengths || []).map((item, idx) => (
                <Text key={`str-${idx}`} style={{ color: colors.successText, marginTop: 5, fontSize: 12 }} data-testid={`lexicon-hub-usage-strength-${idx}`} testID={`lexicon-hub-usage-strength-${idx}`}>
                  + {item}
                </Text>
              ))}
              {(usageCoachResult.improvements || []).map((item, idx) => (
                <Text key={`imp-${idx}`} style={{ color: colors.warningText, marginTop: 4, fontSize: 12 }} data-testid={`lexicon-hub-usage-improvement-${idx}`} testID={`lexicon-hub-usage-improvement-${idx}`}>
                  • {item}
                </Text>
              ))}
              <Text style={{ color: colors.textSec, marginTop: 8, fontSize: 12 }} data-testid="lexicon-hub-usage-rewrite" testID="lexicon-hub-usage-rewrite">
                {usageCoachResult.rewrite_suggestion}
              </Text>
            </View>
          ) : null}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-business-brief-card" testID="lexicon-hub-business-brief-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('lexiconHub.brief.title', 'Business Communication Brief')}</Text>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-business-contexts" testID="lexicon-hub-business-contexts">
            {(bootstrap.business_contexts || ['meeting', 'email', 'sales', 'leadership', 'support']).map((item) => (
              <TouchableOpacity
                key={item}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: businessContext === item ? colors.success : colors.border,
                  backgroundColor: businessContext === item ? `${colors.success}20` : colors.bgSoft,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                }}
                onPress={() => setBusinessContext(item)}
                data-testid={`lexicon-hub-business-context-${item}`}
                testID={`lexicon-hub-business-context-${item}`}
              >
                <Text style={{ color: businessContext === item ? colors.success : colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity
            style={{
              marginTop: 10,
              borderRadius: 10,
              backgroundColor: colors.success,
              paddingVertical: 11,
              alignItems: 'center',
            }}
            onPress={generateBusinessBrief}
            disabled={working}
            data-testid="lexicon-hub-generate-brief"
            testID="lexicon-hub-generate-brief"
          >
            <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }}>{tx('lexiconHub.brief.generate', 'Generate Business Brief')}</Text>
          </TouchableOpacity>

          {businessBrief ? (
            <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="lexicon-hub-business-brief-result" testID="lexicon-hub-business-brief-result">
              <Text style={{ color: colors.text, fontWeight: '700' }} data-testid="lexicon-hub-business-brief-headline" testID="lexicon-hub-business-brief-headline">{businessBrief.headline}</Text>
              <Text style={{ color: colors.textSec, marginTop: 7, fontSize: 12 }} data-testid="lexicon-hub-business-email" testID="lexicon-hub-business-email">{businessBrief.email_snippet}</Text>
              <Text style={{ color: colors.textSec, marginTop: 5, fontSize: 12 }} data-testid="lexicon-hub-business-meeting" testID="lexicon-hub-business-meeting">{businessBrief.meeting_talking_point}</Text>
              <Text style={{ color: colors.textSec, marginTop: 5, fontSize: 12 }} data-testid="lexicon-hub-business-sales" testID="lexicon-hub-business-sales">{businessBrief.sales_pitch_line}</Text>
              <Text style={{ color: colors.textSec, marginTop: 5, fontSize: 12 }} data-testid="lexicon-hub-business-leadership" testID="lexicon-hub-business-leadership">{businessBrief.leadership_phrase}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 5, fontSize: 11 }} data-testid="lexicon-hub-business-confidence-tip" testID="lexicon-hub-business-confidence-tip">{businessBrief.confidence_tip}</Text>
            </View>
          ) : null}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-review-queue-card" testID="lexicon-hub-review-queue-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('lexiconHub.review.title', 'Spaced Review Queue')}</Text>
          {(bootstrap.review_queue || []).length === 0 ? (
            <Text style={{ color: colors.textSec, marginTop: 8 }} data-testid="lexicon-hub-review-empty" testID="lexicon-hub-review-empty">
              {tx('lexiconHub.review.empty', 'No due words right now. Great consistency!')}
            </Text>
          ) : (
            <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-review-rows" testID="lexicon-hub-review-rows">
              {(bootstrap.review_queue || []).map((item, idx) => (
                <View
                  key={item.word_id}
                  style={{ borderRadius: 11, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}
                  data-testid={`lexicon-hub-review-row-${idx}`}
                  testID={`lexicon-hub-review-row-${idx}`}
                >
                  <Text style={{ color: colors.text, fontWeight: '700' }}>{item.word}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 3 }}>{item.definition}</Text>
                  <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {[1, 2, 3, 4, 5].map((confidence) => (
                      <TouchableOpacity
                        key={`${item.word_id}-${confidence}`}
                        style={{
                          borderRadius: 999,
                          borderWidth: 1,
                          borderColor: colors.border,
                          backgroundColor: colors.card,
                          paddingHorizontal: 8,
                          paddingVertical: 4,
                        }}
                        onPress={() => completeReview(item.word_id, confidence)}
                        data-testid={`lexicon-hub-review-confidence-${item.word_id}-${confidence}`}
                        testID={`lexicon-hub-review-confidence-${item.word_id}-${confidence}`}
                      >
                        <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}>{tx('lexiconHub.review.confidence', 'Confidence')} {confidence}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-weekly-challenge-card" testID="lexicon-hub-weekly-challenge-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-weekly-challenge-title" testID="lexicon-hub-weekly-challenge-title">
            {tx('lexiconHub.weeklyChallenge.title', 'Weekly Challenge Mode')}
          </Text>
          <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 12 }} data-testid="lexicon-hub-weekly-challenge-objective" testID="lexicon-hub-weekly-challenge-objective">
            {weeklyChallenge?.objective || tx('lexiconHub.weeklyChallenge.fallback', 'Submit one practical sentence application to earn challenge points.')}
          </Text>
          <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 11 }} data-testid="lexicon-hub-weekly-challenge-reward" testID="lexicon-hub-weekly-challenge-reward">
            {weeklyChallenge?.reward || tx('lexiconHub.weeklyChallenge.reward', 'Top participants get weekly spotlight badges.')}
          </Text>

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-weekly-challenge-metrics" testID="lexicon-hub-weekly-challenge-metrics">
            {[
              { id: 'points', label: tx('lexiconHub.challenge.points', 'Your Points'), value: challengeEntry?.points || 0 },
              { id: 'submissions', label: tx('lexiconHub.challenge.submissions', 'Submissions'), value: challengeEntry?.submissions || 0 },
              { id: 'rank', label: tx('lexiconHub.challenge.rank', 'Rank'), value: challengeEntry?.rank || '-' },
              { id: 'tier', label: tx('lexiconHub.challenge.tier', 'Tier'), value: challengeEntry?.tier_label || tx('lexiconHub.challenge.tierStarter', 'Starter') },
            ].map((metric) => (
              <View
                key={metric.id}
                style={{
                  minWidth: isDesktop ? 160 : '48%',
                  flex: 1,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.bgSoft,
                  padding: 10,
                }}
                data-testid={`lexicon-hub-challenge-metric-${metric.id}`}
                testID={`lexicon-hub-challenge-metric-${metric.id}`}
              >
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{metric.label}</Text>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 16 }}>{metric.value}</Text>
              </View>
            ))}
          </View>

          <View style={{ marginTop: 10 }} data-testid="lexicon-hub-reward-tier-progress" testID="lexicon-hub-reward-tier-progress">
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('lexiconHub.challenge.rewards', 'Reward Tiers')}</Text>
            <View style={{ marginTop: 6, gap: 6 }}>
              {(weeklyChallenge?.reward_tiers || []).map((tier) => {
                const isUnlocked = Number(challengeEntry?.points || 0) >= Number(tier.min_points || 0);
                return (
                  <View
                    key={tier.tier}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isUnlocked ? colors.success : colors.border,
                      backgroundColor: isUnlocked ? `${colors.success}16` : colors.bgSoft,
                      padding: 9,
                    }}
                    data-testid={`lexicon-hub-reward-tier-${tier.tier}`}
                    testID={`lexicon-hub-reward-tier-${tier.tier}`}
                  >
                    <Text style={{ color: isUnlocked ? colors.successText : colors.text, fontWeight: '700', fontSize: 12 }}>
                      {tier.label} · {tier.min_points}+ pts
                    </Text>
                    <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 3 }}>{tier.perk}</Text>
                  </View>
                );
              })}
            </View>
          </View>

          {Array.isArray(challengeEntry?.perks_unlocked) && challengeEntry.perks_unlocked.length > 0 ? (
            <View style={{ marginTop: 10 }} data-testid="lexicon-hub-unlocked-perks" testID="lexicon-hub-unlocked-perks">
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('lexiconHub.challenge.unlockedPerks', 'Unlocked Perks')}</Text>
              {(challengeEntry.perks_unlocked || []).map((perk, idx) => (
                <Text key={`${perk}-${idx}`} style={{ color: colors.successText, fontSize: 12, marginTop: 4 }} data-testid={`lexicon-hub-unlocked-perk-${idx}`} testID={`lexicon-hub-unlocked-perk-${idx}`}>
                  • {perk}
                </Text>
              ))}
            </View>
          ) : null}

          <TextInput
            style={[inputStyle, { minHeight: 90, marginTop: 10, textAlignVertical: 'top' }]}
            multiline
            value={challengeSubmission}
            onChangeText={setChallengeSubmission}
            placeholder={tx('lexiconHub.challenge.placeholder', 'Write your best professional sentence using this week\'s vocabulary...')}
            placeholderTextColor={colors.textMuted}
            data-testid="lexicon-hub-weekly-challenge-input"
            testID="lexicon-hub-weekly-challenge-input"
          />
          <TouchableOpacity
            style={{
              marginTop: 10,
              borderRadius: 10,
              backgroundColor: colors.success,
              paddingVertical: 11,
              alignItems: 'center',
            }}
            onPress={submitWeeklyChallenge}
            disabled={working}
            data-testid="lexicon-hub-weekly-challenge-submit"
            testID="lexicon-hub-weekly-challenge-submit"
          >
            <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }}>
              {tx('lexiconHub.challenge.submit', 'Submit Weekly Challenge')}
            </Text>
          </TouchableOpacity>

          {challengeResult ? (
            <View
              style={{
                marginTop: 10,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: colors.success,
                backgroundColor: `${colors.success}16`,
                padding: 10,
              }}
              data-testid="lexicon-hub-weekly-challenge-result"
              testID="lexicon-hub-weekly-challenge-result"
            >
              <Text style={{ color: colors.successText, fontWeight: '700' }} data-testid="lexicon-hub-weekly-challenge-points" testID="lexicon-hub-weekly-challenge-points">
                +{challengeResult.points_awarded} {tx('lexiconHub.challenge.pointsAwarded', 'points earned')}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 4 }} data-testid="lexicon-hub-weekly-challenge-rank" testID="lexicon-hub-weekly-challenge-rank">
                {tx('lexiconHub.challenge.rankNow', 'Current rank')}: {challengeResult.rank || '-'}
              </Text>
              {challengeResult.tier_label ? (
                <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 4 }} data-testid="lexicon-hub-weekly-challenge-tier" testID="lexicon-hub-weekly-challenge-tier">
                  {tx('lexiconHub.challenge.currentTier', 'Current tier')}: {challengeResult.tier_label}
                </Text>
              ) : null}
              {(challengeResult.perks_unlocked || []).slice(0, 3).map((perk, idx) => (
                <Text key={`${perk}-${idx}`} style={{ color: colors.successText, fontSize: 11, marginTop: 3 }} data-testid={`lexicon-hub-weekly-challenge-perk-${idx}`} testID={`lexicon-hub-weekly-challenge-perk-${idx}`}>
                  • {perk}
                </Text>
              ))}
            </View>
          ) : null}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-team-leaderboard-card" testID="lexicon-hub-team-leaderboard-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-team-leaderboard-title" testID="lexicon-hub-team-leaderboard-title">
              {tx('lexiconHub.leaderboard.title', 'Team Vocabulary Leaderboard')}
            </Text>
            <TouchableOpacity
              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
              onPress={refreshLeaderboard}
              disabled={working}
              data-testid="lexicon-hub-refresh-leaderboard"
              testID="lexicon-hub-refresh-leaderboard"
            >
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{tx('lexiconHub.leaderboard.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>

          {leaderboardData.length === 0 ? (
            <Text style={{ color: colors.textSec, marginTop: 8 }} data-testid="lexicon-hub-leaderboard-empty" testID="lexicon-hub-leaderboard-empty">
              {tx('lexiconHub.leaderboard.empty', 'No leaderboard submissions yet this week. Be the first!')}
            </Text>
          ) : (
            <View style={{ marginTop: 10, gap: 6 }} data-testid="lexicon-hub-leaderboard-rows" testID="lexicon-hub-leaderboard-rows">
              {leaderboardData.slice(0, 12).map((row, idx) => {
                const isCurrentUser = Number(challengeEntry?.rank || 0) > 0 && Number(challengeEntry?.rank) === Number(row.rank);
                return (
                  <View
                    key={`${row.user_id}-${idx}`}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isCurrentUser ? colors.primary : colors.border,
                      backgroundColor: isCurrentUser ? `${colors.primary}14` : colors.bgSoft,
                      padding: 10,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 10,
                    }}
                    data-testid={`lexicon-hub-leaderboard-row-${idx}`}
                    testID={`lexicon-hub-leaderboard-row-${idx}`}
                  >
                    <Text style={{ color: colors.text, width: 28, fontWeight: '800' }}>#{row.rank}</Text>
                    <Text style={{ color: colors.textSec, flex: 1, fontSize: 12 }}>{row.display_name}</Text>
                    <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{row.tier_label || row.tier || 'Starter'}</Text>
                    <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }}>{row.points} pts</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{row.submissions}x</Text>
                  </View>
                );
              })}
            </View>
          )}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-saved-vault-card" testID="lexicon-hub-saved-vault-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('lexiconHub.saved.title', 'Lexical Vault')}</Text>
          {(bootstrap.saved_words || []).length === 0 ? (
            <Text style={{ color: colors.textSec, marginTop: 8 }} data-testid="lexicon-hub-saved-empty" testID="lexicon-hub-saved-empty">
              {tx('lexiconHub.saved.empty', 'Save words to build your personal vocabulary vault.')}
            </Text>
          ) : (
            <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-saved-rows" testID="lexicon-hub-saved-rows">
              {(bootstrap.saved_words || []).slice(0, 20).map((item, idx) => (
                <View
                  key={`${item.word_id}-${idx}`}
                  style={{ borderRadius: 11, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}
                  data-testid={`lexicon-hub-saved-row-${idx}`}
                  testID={`lexicon-hub-saved-row-${idx}`}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700' }}>{item.word}</Text>
                      <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 3 }}>
                        {tx('lexiconHub.saved.mastery', 'Mastery')}: {item.mastery_score}% · {tx('lexiconHub.saved.reviews', 'Reviews')}: {item.review_count}
                      </Text>
                    </View>
                    <TouchableOpacity
                      style={{
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: colors.warning,
                        backgroundColor: `${colors.warning}20`,
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                      }}
                      onPress={() => toggleSaveWord(item.word_id, false)}
                      data-testid={`lexicon-hub-unsave-${idx}`}
                      testID={`lexicon-hub-unsave-${idx}`}
                    >
                      <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{tx('lexiconHub.saved.removeCta', 'Remove')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-capabilities-card" testID="lexicon-hub-capabilities-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }} data-testid="lexicon-hub-capabilities-title" testID="lexicon-hub-capabilities-title">
            {tx('lexiconHub.capabilities.title', '15 Enterprise Functionalities')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }} data-testid="lexicon-hub-capabilities-subtitle" testID="lexicon-hub-capabilities-subtitle">
            {tx('lexiconHub.capabilities.subtitle', 'Built to improve daily communication quality, confidence, and business outcomes.')}
          </Text>

          <View style={{ marginTop: 10, gap: 8 }} data-testid="lexicon-hub-capabilities-list" testID="lexicon-hub-capabilities-list">
            {capabilityRows.map((capability, idx) => (
              <View
                key={capability.capability_id}
                style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}
                data-testid={`lexicon-hub-capability-row-${idx}`}
                testID={`lexicon-hub-capability-row-${idx}`}
              >
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{idx + 1}. {capability.title}</Text>
                <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 11 }}>{capability.description}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={cardStyle} data-testid="lexicon-hub-usage-summary-card" testID="lexicon-hub-usage-summary-card">
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('lexiconHub.usage.title', 'Today\'s Entitlement Usage')}</Text>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="lexicon-hub-usage-pills" testID="lexicon-hub-usage-pills">
            {Object.keys(bootstrap.limits || {}).map((key) => (
              <View
                key={key}
                style={{
                  minWidth: isDesktop ? 180 : '48%',
                  flex: 1,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.bgSoft,
                  padding: 10,
                }}
                data-testid={`lexicon-hub-usage-${key}`}
                testID={`lexicon-hub-usage-${key}`}
              >
                <Text style={{ color: colors.textMuted, fontSize: 10, textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</Text>
                <Text style={{ color: colors.text, fontWeight: '700', marginTop: 3 }}>
                  {usageToday[key] || 0} / {bootstrap.limits[key] < 0 ? '∞' : bootstrap.limits[key]}
                </Text>
              </View>
            ))}
          </View>
        </View>

      </ScrollView>
    </FeatureLayout>
  );
}
