import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Modal, Platform, View, Text, TouchableOpacity, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY, MONO_FONT_FAMILY } from '../../constants/appTypography';

interface HomeEnterpriseCommandDeckProps {
  responsiveWidth?: number;
  payload: any;
  loading?: boolean;
  onNavigate: (route: string) => void;
}

const getTodayIso = () => new Date().toISOString().slice(0, 10);

const getYesterdayIso = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
};

const readLocalJson = (key: string) => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const writeLocalJson = (key: string, value: any) => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/home/HomeEnterpriseCommandDeck.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
};

export default function HomeEnterpriseCommandDeck({ responsiveWidth, payload, loading = false, onNavigate }: HomeEnterpriseCommandDeckProps) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const isDesktop = width >= 1080;
  const deckBg = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'AA' : 'F0')
    : colors.card;
  const viewerUserId = String(payload?.viewer_user_id || 'anon-user');
  const subscriptionPlan = String(payload?.subscription_plan || 'free');
  const focusTemplate = payload?.focus_mode_template || {};
  const today = getTodayIso();
  const progressStorageKey = `home_focus_mode_progress:${viewerUserId}:${today}`;
  const streakStorageKey = `home_focus_mode_streak:${viewerUserId}`;

  const [focusModeOpen, setFocusModeOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const [resumeIndex, setResumeIndex] = useState(0);
  const [focusStreakDays, setFocusStreakDays] = useState(0);
  const [celebrationVisible, setCelebrationVisible] = useState(false);
  const celebrationScale = useRef(new Animated.Value(0.82)).current;

  const kpis = payload?.command_kpis || {};
  const actions = Array.isArray(payload?.priority_actions) ? payload.priority_actions : [];
  const focusSteps = actions.slice(0, 3);
  const currentFocusStep = focusSteps[focusIndex] || null;
  const focusProgress = focusSteps.length > 0 ? Math.min(100, Math.round((resumeIndex / focusSteps.length) * 100)) : 0;

  useEffect(() => {
    const savedProgress = readLocalJson(progressStorageKey);
    const validResumeIndex = Number(savedProgress?.index || 0);
    if (!savedProgress?.completed && Number.isFinite(validResumeIndex) && validResumeIndex > 0 && validResumeIndex < focusSteps.length) {
      setResumeIndex(validResumeIndex);
      setFocusIndex(validResumeIndex);
    } else {
      setResumeIndex(0);
      setFocusIndex(0);
    }

    const savedStreak = readLocalJson(streakStorageKey);
    setFocusStreakDays(Number(savedStreak?.streak_days || 0));
  }, [focusSteps.length, progressStorageKey, streakStorageKey]);

  const kpiCards = useMemo(() => ([
    { id: 'notifications', label: tx('home.commandDeck.unreadAlerts', 'Unread alerts'), value: Number(kpis.unread_notifications || 0), icon: 'notifications-outline', tone: colors.warningText },
    { id: 'goals', label: tx('home.commandDeck.activeGoals', 'Active goals'), value: Number(kpis.active_goals || 0), icon: 'flag-outline', tone: colors.primary },
    { id: 'events', label: tx('home.commandDeck.next7Days', 'Events next 7d'), value: Number(kpis.upcoming_events_7d || 0), icon: 'calendar-outline', tone: colors.successText },
    { id: 'learning', label: tx('home.commandDeck.learningTracks', 'Learning tracks'), value: Number(kpis.active_learning_tracks || 0), icon: 'school-outline', tone: colors.accent },
  ]), [colors.accent, colors.primary, colors.successText, colors.warningText, kpis.active_goals, kpis.active_learning_tracks, kpis.unread_notifications, kpis.upcoming_events_7d, tx]);

  const persistFocusProgress = (nextIndex: number, completed = false) => {
    writeLocalJson(progressStorageKey, {
      index: nextIndex,
      completed,
      updated_at: new Date().toISOString(),
    });
  };

  const startFocusMode = () => {
    if (focusSteps.length <= 0) return;
    const initialIndex = resumeIndex > 0 && resumeIndex < focusSteps.length ? resumeIndex : 0;
    setFocusIndex(initialIndex);
    setFocusModeOpen(true);
    persistFocusProgress(initialIndex, false);
  };

  const triggerCelebration = (streakDays: number) => {
    setCelebrationVisible(true);
    celebrationScale.setValue(0.84);
    Animated.sequence([
      Animated.spring(celebrationScale, { toValue: 1, useNativeDriver: true, friction: 6, tension: 95 }),
      Animated.delay(1200),
      Animated.timing(celebrationScale, { toValue: 0.84, duration: 240, useNativeDriver: true }),
    ]).start(() => setCelebrationVisible(false));
  };

  const finalizeFocusMode = () => {
    const todayIso = getTodayIso();
    const yesterdayIso = getYesterdayIso();
    const prev = readLocalJson(streakStorageKey) || {};
    const prevDate = String(prev.last_completed_date || '');
    const prevStreak = Number(prev.streak_days || 0);
    let nextStreak = 1;

    if (prevDate === todayIso) {
      nextStreak = Math.max(1, prevStreak);
    } else if (prevDate === yesterdayIso) {
      nextStreak = Math.max(1, prevStreak + 1);
    }

    writeLocalJson(streakStorageKey, {
      streak_days: nextStreak,
      last_completed_date: todayIso,
      updated_at: new Date().toISOString(),
    });

    persistFocusProgress(0, true);
    setFocusStreakDays(nextStreak);
    setResumeIndex(0);
    setFocusModeOpen(false);
    setFocusIndex(0);
    triggerCelebration(nextStreak);
  };

  const advanceFocusStep = () => {
    if (focusIndex >= focusSteps.length - 1) {
      finalizeFocusMode();
      return;
    }
    const nextIndex = focusIndex + 1;
    setFocusIndex(nextIndex);
    setResumeIndex(nextIndex);
    persistFocusProgress(nextIndex, false);
  };

  const focusButtonLabel = resumeIndex > 0 && resumeIndex < focusSteps.length
    ? `${tx('home.commandDeck.resumeFocusMode', 'Resume Daily Focus Mode')} (${resumeIndex + 1}/${focusSteps.length})`
    : String(focusTemplate?.button_label || tx('home.commandDeck.focusMode', 'Start Daily Focus Mode'));

  const modalFocusTitle = String(focusTemplate?.title || tx('home.commandDeck.focusModeTitle', 'Daily Focus Mode'));
  const modalFocusSubtitle = String(focusTemplate?.subtitle || tx('home.commandDeck.focusModeSubtitle', 'Follow the top 3 actions in sequence and maintain daily momentum.'));
  const currentActionSummary = String(currentFocusStep?.description || tx('home.commandDeck.currentActionSummary', 'Use this space to convert the highest-value recommendation into immediate action.'));

  return (
    <View
      style={{
        marginHorizontal: 20,
        marginTop: 14,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: deckBg,
        padding: isDesktop ? 20 : 14,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', boxShadow: darkMode ? '0 16px 42px rgba(2,6,23,0.24)' : '0 14px 34px rgba(15,23,42,0.08)' } as any : {}),
      }}
      data-testid="home-command-deck"
      testID="home-command-deck"
    >
      <View style={{ flexDirection: isDesktop ? 'row' : 'column', justifyContent: 'space-between', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>
            {tx('home.commandDeck.kicker', 'Priority actions')}
          </Text>
          <Text style={{ color: colors.text, fontSize: isDesktop ? 22 : 18, fontWeight: '900', letterSpacing: -1, marginTop: 8, fontFamily: DISPLAY_FONT_FAMILY }} data-testid="home-command-deck-title" testID="home-command-deck-title">
            {tx('home.commandDeck.title', 'Enterprise Command Deck')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4, lineHeight: 20, maxWidth: 680, fontFamily: BODY_FONT_FAMILY }} data-testid="home-command-deck-subtitle" testID="home-command-deck-subtitle">
            {tx('home.commandDeck.subtitle', 'Live priorities and growth-critical workflows from platform signals.')}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <TouchableOpacity accessibilityLabel="Home daily focus mode button"
            onPress={startFocusMode}
            disabled={focusSteps.length <= 0}
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: `${colors.primary}66`,
              backgroundColor: focusSteps.length <= 0 ? colors.surfaceHover : `${colors.primary}18`,
              paddingHorizontal: 12,
              paddingVertical: 6,
              opacity: focusSteps.length <= 0 ? 0.65 : 1,
            }}
            data-testid="home-daily-focus-mode-button"
            testID="home-daily-focus-mode-button"
          >
            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>
              {focusButtonLabel}
            </Text>
          </TouchableOpacity>

          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.warning}66`, backgroundColor: `${colors.warning}16`, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="home-focus-streak-chip" testID="home-focus-streak-chip">
            <Text style={{ color: colors.warningText || colors.warning, fontSize: 10, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>
              {tx('home.commandDeck.streak', 'Streak')} {focusStreakDays}d
            </Text>
          </View>

          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.success}50`, backgroundColor: `${colors.success}1A`, alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5 }} data-testid="home-command-deck-status-chip" testID="home-command-deck-status-chip">
            <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>{loading ? tx('home.commandDeck.syncing', 'SYNCING') : tx('home.commandDeck.live', 'LIVE')}</Text>
          </View>
        </View>
      </View>

      <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="home-command-deck-kpis" testID="home-command-deck-kpis">
        {kpiCards.map((card) => (
          <View key={card.id} style={{ flex: 1, minWidth: isDesktop ? 170 : 145, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surfaceHover, padding: 12 }} data-testid={`home-command-deck-kpi-${card.id}`} testID={`home-command-deck-kpi-${card.id}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name={card.icon as any} size={13} color={card.tone} />
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>{card.label}</Text>
            </View>
            <Text style={{ color: colors.text, fontSize: 26, fontWeight: '900', marginTop: 8, letterSpacing: -1, fontFamily: DISPLAY_FONT_FAMILY }} data-testid={`home-command-deck-kpi-value-${card.id}`} testID={`home-command-deck-kpi-value-${card.id}`}>
              {card.value}
            </Text>
          </View>
        ))}
      </View>

      <View style={{ marginTop: 16, flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
        <View style={{ flex: 1, borderRadius: 22, borderWidth: 1, borderColor: `${colors.primary}26`, backgroundColor: `${colors.primary}10`, padding: 16 }} data-testid="home-command-deck-focus-card" testID="home-command-deck-focus-card">
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>
            {tx('home.commandDeck.focusCard.kicker', 'Daily focus mode')}
          </Text>
          <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900', letterSpacing: -1, marginTop: 10, fontFamily: DISPLAY_FONT_FAMILY }} data-testid="home-command-deck-focus-title" testID="home-command-deck-focus-title">
            {String(currentFocusStep?.title || tx('home.commandDeck.focusCard.emptyTitle', 'Turn the next action into momentum.'))}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginTop: 8, fontFamily: BODY_FONT_FAMILY }} data-testid="home-command-deck-focus-summary" testID="home-command-deck-focus-summary">
            {currentActionSummary}
          </Text>

          <View style={{ marginTop: 18 }} data-testid="home-command-deck-focus-progress" testID="home-command-deck-focus-progress">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', fontFamily: BODY_FONT_FAMILY }}>{tx('home.commandDeck.focusCard.progress', 'Today progress')}</Text>
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', fontFamily: MONO_FONT_FAMILY }}>{focusProgress}%</Text>
            </View>
            <View style={{ height: 10, borderRadius: 999, backgroundColor: `${colors.primary}18`, overflow: 'hidden' }}>
              <View style={{ width: `${Math.max(10, focusProgress)}%`, height: '100%', backgroundColor: colors.primary, borderRadius: 999 }} />
            </View>
          </View>

          <View style={{ gap: 9, marginTop: 18 }}>
            {focusSteps.map((step: any, idx: number) => {
              const isCurrent = idx === resumeIndex;
              return (
                <View key={step.id || idx} style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }} data-testid={`home-command-deck-focus-inline-step-${idx}`} testID={`home-command-deck-focus-inline-step-${idx}`}>
                  <View style={{ width: 24, height: 24, borderRadius: 999, backgroundColor: isCurrent ? colors.primary : `${colors.primary}16`, borderWidth: 1, borderColor: `${colors.primary}34`, alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ color: isCurrent ? colors.primaryText : colors.primary, fontSize: 10, fontWeight: '800', fontFamily: MONO_FONT_FAMILY }}>{idx + 1}</Text>
                  </View>
                  <Text style={{ flex: 1, color: colors.textSec, fontSize: 12, lineHeight: 18, fontFamily: BODY_FONT_FAMILY }} numberOfLines={2}>{String(step.title || 'Action step')}</Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={{ flex: 1.1, gap: 8 }} data-testid="home-command-deck-actions" testID="home-command-deck-actions">
          {actions.map((action: any, idx: number) => (
            <TouchableOpacity accessibilityLabel="On navigate in home enterprise command deck button"
              key={action.id || idx}
              onPress={() => onNavigate(String(action.route || '/dashboard'))}
              style={{
                borderRadius: 16,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.surface,
                paddingHorizontal: 14,
                paddingVertical: 12,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 10,
              }}
              data-testid={`home-command-deck-action-${idx}`}
              testID={`home-command-deck-action-${idx}`}
            >
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }} data-testid={`home-command-deck-action-title-${idx}`} testID={`home-command-deck-action-title-${idx}`}>
                  {String(action.title || 'Action')}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4, lineHeight: 17, fontFamily: BODY_FONT_FAMILY }} numberOfLines={2}>
                  {String(action.description || '')}
                </Text>
              </View>
              <Ionicons name="arrow-forward" size={15} color={colors.primary} />
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <Modal
        visible={focusModeOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setFocusModeOpen(false)}
      >
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.42)', justifyContent: 'center', padding: 20 }} data-testid="home-daily-focus-mode-modal" testID="home-daily-focus-mode-modal">
          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }} data-testid="home-daily-focus-mode-title" testID="home-daily-focus-mode-title">
              {modalFocusTitle}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="home-daily-focus-mode-subtitle" testID="home-daily-focus-mode-subtitle">
              {modalFocusSubtitle}
            </Text>

            <Text style={{ color: colors.primary, fontSize: 11, marginTop: 5 }} data-testid="home-daily-focus-mode-plan-template" testID="home-daily-focus-mode-plan-template">
              {tx('home.commandDeck.planTemplate', 'Plan template')}: {subscriptionPlan.toUpperCase()} · {String(focusTemplate?.template_id || 'focus-core')}
            </Text>

            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} data-testid="home-daily-focus-mode-conversion-nudge" testID="home-daily-focus-mode-conversion-nudge">
              {String(focusTemplate?.conversion_nudge || tx('home.commandDeck.conversionNudge', 'Keep your streak active daily for better outcomes.'))}
            </Text>

            <View style={{ marginTop: 12, gap: 8 }} data-testid="home-daily-focus-mode-steps" testID="home-daily-focus-mode-steps">
              {focusSteps.map((step: any, idx: number) => {
                const isActive = idx === focusIndex;
                const isDone = idx < focusIndex;
                return (
                  <View
                    key={step.id || idx}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isActive ? colors.primary : colors.border,
                      backgroundColor: isDone ? `${colors.success}14` : colors.surface,
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                    }}
                    data-testid={`home-daily-focus-mode-step-${idx}`}
                    testID={`home-daily-focus-mode-step-${idx}`}
                  >
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>
                      {idx + 1}. {String(step.title || 'Action step')}
                    </Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} numberOfLines={2}>
                      {String(step.description || '')}
                    </Text>
                  </View>
                );
              })}
            </View>

            <View style={{ marginTop: 14, flexDirection: 'row', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={() => setFocusModeOpen(false)}
                style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="home-daily-focus-mode-close-button"
                testID="home-daily-focus-mode-close-button"
              >
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('home.commandDeck.close', 'Close')}</Text>
              </TouchableOpacity>

              <TouchableOpacity accessibilityLabel="Home daily focus mode open current button"
                onPress={() => {
                  if (currentFocusStep?.route) {
                    onNavigate(String(currentFocusStep.route));
                  }
                }}
                style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}16`, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="home-daily-focus-mode-open-current-button"
                testID="home-daily-focus-mode-open-current-button"
              >
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{tx('home.commandDeck.openCurrent', 'Open current workflow')}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={advanceFocusStep}
                style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.success}66`, backgroundColor: `${colors.success}18`, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="home-daily-focus-mode-next-button"
                testID="home-daily-focus-mode-next-button"
              >
                <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>
                  {focusIndex >= focusSteps.length - 1 ? tx('home.commandDeck.finish', 'Finish') : tx('home.commandDeck.completeNext', 'Complete & Next')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {celebrationVisible ? (
        <View
          pointerEvents="none"
          style={{ position: 'absolute', left: 0, right: 0, bottom: 16, alignItems: 'center' }}
          data-testid="home-focus-mode-celebration-wrap"
          testID="home-focus-mode-celebration-wrap"
        >
          <Animated.View
            style={{
              transform: [{ scale: celebrationScale }],
              borderRadius: 999,
              borderWidth: 1,
              borderColor: `${colors.success}66`,
              backgroundColor: `${colors.success}F0`,
              paddingHorizontal: 16,
              paddingVertical: 10,
            }}
            data-testid="home-focus-mode-celebration-banner"
            testID="home-focus-mode-celebration-banner"
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '900' }}>
              🎉 {tx('home.commandDeck.celebration', 'Daily Focus complete!')} {tx('home.commandDeck.streak', 'Streak')} {focusStreakDays}d
            </Text>
          </Animated.View>
        </View>
      ) : null}
    </View>
  );
}
