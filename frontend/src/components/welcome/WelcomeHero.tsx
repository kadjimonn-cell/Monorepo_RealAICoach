import React, { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Platform,
  Animated, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { getShadow } from '../../utils/themeShadows';
import { useLiveMetrics } from '../../hooks/useLiveMetrics';
import { useLanguage } from '../../i18n/LanguageContext';
import WelcomeLiveTickertape from './WelcomeLiveTickertape';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import type { GLSTokens } from '../../context/GLSContext';
import { NOVA_INTRO_FALLBACK } from '../../constants/novaPersona';
import { NovaIdentityCallout } from '../common/NovaIdentityBadge';
import { withAlpha } from '../../utils/colorAlpha';
import { WELCOME_CENTERED_LAYOUT_BREAKPOINT } from './welcomeSectionContract';

function useCounter(target: number, duration = 2200) {
  // Animate from the PREVIOUS target to the new target; seed to `target` on
  // first mount so SSR never paints a "0 → N" flash with hydrated data.
  const [val, setVal] = useState(() => target || 0);
  const prevTargetRef = useRef<number>(target || 0);
  const initialAnimRef = useRef<boolean>(true);
  useEffect(() => {
    const from = initialAnimRef.current && target > 0 ? 0 : prevTargetRef.current;
    const to = target;
    initialAnimRef.current = false;
    if (from === to) {
      setVal(to);
      return;
    }
    prevTargetRef.current = to;
    let frame: number;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      setVal(Math.floor(from + (to - from) * ease));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return Math.max(0, val);
}

/** Staggered entrance driver: returns animated style for a given stage. */
function useStagger(stages: number, baseDelay = 90) {
  const values = useRef(Array.from({ length: stages }, () => new Animated.Value(0))).current;
  useEffect(() => {
    Animated.stagger(
      baseDelay,
      values.map((v) => Animated.timing(v, { toValue: 1, duration: 420, useNativeDriver: Platform.OS !== 'web' })),
    ).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (i: number) => ({
    opacity: values[i],
    transform: [{ translateY: values[i].interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) }],
  });
}

/** Pulsing live indicator dot (badge + mockup header). */
function PulseDot({ color, size = 7 }: { color: string; size?: number }) {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(pulse, { toValue: 0, duration: 900, useNativeDriver: Platform.OS !== 'web' }),
    ]));
    loop.start();
    return () => loop.stop();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={{ width: size + 6, height: size + 6, alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View
        style={{
          position: 'absolute',
          width: size + 6,
          height: size + 6,
          borderRadius: (size + 6) / 2,
          backgroundColor: color,
          opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0] }),
          transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1.4] }) }],
        }}
      />
      <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />
    </View>
  );
}

/** Spring pop-in wrapper for the live "+N since you landed" delta pills. */
function SpringIn({ children }: { children: React.ReactNode }) {
  const scale = useRef(new Animated.Value(0.4)).current;
  const fade = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.spring(scale, { toValue: 1, friction: 4, tension: 120, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <Animated.View style={{ opacity: fade, transform: [{ scale }] }}>{children}</Animated.View>;
}

/** Animated "Nova is typing" dots for the live-session mockup. */
function TypingDots({ color }: { color: string }) {
  const dots = useRef([new Animated.Value(0), new Animated.Value(0), new Animated.Value(0)]).current;
  useEffect(() => {
    const anims = dots.map((d, i) => Animated.loop(Animated.sequence([
      Animated.delay(i * 180),
      Animated.timing(d, { toValue: 1, duration: 360, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(d, { toValue: 0, duration: 360, useNativeDriver: Platform.OS !== 'web' }),
      Animated.delay((2 - i) * 180),
    ])));
    anims.forEach((a) => a.start());
    return () => anims.forEach((a) => a.stop());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center' }}>
      {dots.map((d, i) => (
        <Animated.View
          key={i}
          style={{
            width: 6, height: 6, borderRadius: 3, backgroundColor: color,
            opacity: d.interpolate({ inputRange: [0, 1], outputRange: [0.25, 1] }),
            transform: [{ translateY: d.interpolate({ inputRange: [0, 1], outputRange: [0, -3] }) }],
          }}
        />
      ))}
    </View>
  );
}

interface Props {
  onLogin: () => void;
  onRegister: () => void;
  featureCount?: number;
}

export function WelcomeHero({ onLogin, onRegister, featureCount = 0 }: Props) {
  const { width, isTablet, padding, tokens } = useGLSBreakpoint();
  const isPhone = width < 480;
  const isCompactPhone = width < 380;
  const useWideHeroLayout = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT;
  const shouldCenterComposition = !useWideHeroLayout;
  const shouldUseNarrowCenteredShell = !useWideHeroLayout && width >= 620 && width < 900;
  const centeredShellMaxWidth = useWideHeroLayout
    ? 620
    : width >= 900
      ? 720
      : shouldUseNarrowCenteredShell
        ? 560
        : 620;
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t, languageCode } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return !value || value === key ? fallback : value;
  }, [t]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const s = useMemo(() => makeStyles(WC, isDark, padding, tokens, useWideHeroLayout, isPhone), [isDark, isPhone, languageCode, padding, tokens, useWideHeroLayout]);

  const stagger = useStagger(6);
  const [hoveredCard, setHoveredCard] = useState('');
  const phoneCardWidth = Math.min(Math.max(width - 96, 218), 300);

  // Mirror the Home dashboard's live stats (SSE + polling) and keep hero dynamic.
  const { vanity } = useLiveMetrics(3000);
  const liveActive = useCounter(vanity?.active_users ?? 0);
  const liveSessions = useCounter(vanity?.ai_sessions_today ?? 0);
  const livePerfBoost = useCounter(vanity?.performance_boost ?? 0);
  const liveCoaches = useCounter(vanity?.global_coaches ?? 0);

  // "+N since you landed" — snapshot on first positive SSE tick.
  const landedRef = useRef<null | { a: number; s: number; p: number; c: number }>(null);
  useEffect(() => {
    if (landedRef.current) return;
    if (!vanity || !(vanity.active_users && vanity.active_users > 0)) return;
    landedRef.current = {
      a: vanity.active_users || 0,
      s: vanity.ai_sessions_today || 0,
      p: vanity.performance_boost || 0,
      c: vanity.global_coaches || 0,
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vanity?.active_users, vanity?.ai_sessions_today, vanity?.performance_boost, vanity?.global_coaches]);
  const baseline = landedRef.current;
  const deltaActive = baseline ? Math.max(0, (vanity?.active_users ?? 0) - baseline.a) : 0;
  const deltaSessions = baseline ? Math.max(0, (vanity?.ai_sessions_today ?? 0) - baseline.s) : 0;
  const deltaCoaches = baseline ? Math.max(0, (vanity?.global_coaches ?? 0) - baseline.c) : 0;

  const valueCards = useMemo(() => ([
    {
      id: 'precision',
      icon: 'locate' as const,
      title: tx('welcome.hero.value.precision.title', 'Precision Intelligence'),
      copy: tx('welcome.hero.value.precision.copy', 'AI fit scores, mock interviews, and career calibration tuned to your exact role, market, and goals.'),
    },
    {
      id: 'roi',
      icon: 'trending-up' as const,
      title: tx('welcome.hero.value.roi.title', 'Measurable ROI'),
      copy: tx('welcome.hero.value.roi.copy', 'Promotion-trajectory analytics and live growth metrics that prove your progress week over week.'),
    },
    {
      id: 'global',
      icon: 'globe-outline' as const,
      title: tx('welcome.hero.value.global.title', 'Global Scale'),
      copy: tx('welcome.hero.value.global.copy', 'Coaching in 23 languages with a worldwide network of professionals levelling up alongside you.'),
    },
  ]), [tx]);

  const heroHighlights = useMemo(() => ([
    tx('welcome.hero.highlights.one', 'Responsive across phone, tablet, and desktop'),
    tx('welcome.hero.highlights.two', 'Live metrics tied to platform activity'),
    tx('welcome.hero.highlights.three', 'Enterprise-safe access control already enforced'),
  ]), [tx]);

  const renderValueCard = (item: typeof valueCards[number], idx: number, phoneCard = false) => (
    <View
      key={item.id}
      style={[
        s.signalCard,
        phoneCard && s.signalCardPhone,
        phoneCard && { width: phoneCardWidth },
        hoveredCard === item.id && s.signalCardHover,
      ]}
      data-testid={`welcome-hero-signal-card-${idx}`}
      testID={`welcome-hero-signal-card-${idx}`}
      {...(Platform.OS === 'web' ? { onMouseEnter: () => setHoveredCard(item.id), onMouseLeave: () => setHoveredCard('') } as any : {})}
    >
      <View style={s.signalIconWrap}>
        <Ionicons name={item.icon} size={17} color={WC.accent} />
      </View>
      <Text style={s.signalCardTitle}>{item.title}</Text>
      <Text style={s.signalCardCopy}>{item.copy}</Text>
    </View>
  );

  return (
    <View
      style={s.wrap}
      data-testid="welcome-hero" testID="welcome-hero" accessibilityRole="header" accessibilityLabel={tx('welcome.hero.accessibilityLabel', 'Welcome to RealAICoach')}
    >
      <View style={[s.row, useWideHeroLayout && s.rowDesktop]}>
        <View
          style={[
            s.left,
            !useWideHeroLayout && s.leftMobileCard,
            useWideHeroLayout && !isDark && s.leftDesktopLightPanel,
            useWideHeroLayout && { flex: 1, maxWidth: 960 },
            shouldCenterComposition && s.leftCentered,
          ]}
        >
          <View style={[s.contentShell, shouldCenterComposition && { maxWidth: centeredShellMaxWidth }]}>
            <Animated.View style={[s.badge, shouldCenterComposition && { alignSelf: 'center' }, stagger(0)]} data-testid="welcome-hero-badge" testID="welcome-hero-badge">
              <PulseDot color={WC.accent} />
              <Text style={s.badgeText}>{t('welcome.hero.badge')}</Text>
            </Animated.View>

            <Animated.Text
              style={[
                s.title,
                isCompactPhone && { fontSize: 31, lineHeight: 39, letterSpacing: -0.8 },
                isPhone && !isCompactPhone && { fontSize: 35, lineHeight: 43, letterSpacing: -1 },
                shouldCenterComposition && s.titleCenteredText,
                !useWideHeroLayout && width >= 900 && { fontSize: 52, lineHeight: 60 },
                isTablet && { fontSize: 44, lineHeight: 52 },
                useWideHeroLayout && { fontSize: 62, lineHeight: 72 },
                stagger(1),
              ]}
              data-testid="welcome-hero-title" testID="welcome-hero-title"
              accessibilityRole="header"
            >
              {t('welcome.hero.title1')}{'\n'}
              <Text style={s.titleAccent}>{t('welcome.hero.title2')}</Text>
            </Animated.Text>

            <Animated.View style={stagger(2)}>
              <View style={[s.featurePillRow, shouldCenterComposition && { justifyContent: 'center' }]}>
                <View style={s.featurePill} data-testid="welcome-hero-feature-pill" testID="welcome-hero-feature-pill">
                  <Ionicons name="flash" size={13} color={WC.accent} />
                  <Text style={s.featurePillText}>
                    {(featureCount || 0) > 0 ? `${featureCount}+ ` : ''}{tx('welcome.hero.featurePill', 'AI coaching tools live today')}
                  </Text>
                </View>
              </View>
              <Text
                style={[
                  s.sub,
                  isPhone && s.subPhone,
                  shouldCenterComposition && s.subCenteredText,
                  isTablet && { fontSize: 16, lineHeight: 26 },
                  useWideHeroLayout && { fontSize: 18, lineHeight: 30 },
                ]}
                data-testid="welcome-hero-subtitle"
                testID="welcome-hero-subtitle"
              >
                {tx('welcome.hero.subtitleV2', 'AI-driven coaching, live performance intelligence, and precision growth plans — engineered for professionals who turn ambition into measurable, compounding results.')}
              </Text>
            </Animated.View>

            <Animated.View style={[s.highlightRow, shouldCenterComposition && s.highlightRowCentered, stagger(3)]} data-testid="welcome-hero-highlights" testID="welcome-hero-highlights">
              {heroHighlights.map((item, idx) => (
                <View key={`${item}-${idx}`} style={s.highlightChip} data-testid={`welcome-hero-highlight-${idx}`} testID={`welcome-hero-highlight-${idx}`}>
                  <Ionicons name="checkmark-circle" size={14} color={WC.successText} />
                  <Text style={s.highlightChipText}>{item}</Text>
                </View>
              ))}
            </Animated.View>

            <Animated.View style={stagger(4)}>
              {isPhone ? (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  snapToInterval={phoneCardWidth + 10}
                  decelerationRate="fast"
                  style={s.signalScroller}
                  contentContainerStyle={s.signalScrollerContent}
                  data-testid="welcome-hero-signal-grid" testID="welcome-hero-signal-grid"
                >
                  {valueCards.map((item, idx) => renderValueCard(item, idx, true))}
                </ScrollView>
              ) : (
                <View style={[s.signalGrid, shouldCenterComposition && s.signalGridCentered]} data-testid="welcome-hero-signal-grid" testID="welcome-hero-signal-grid">
                  {valueCards.map((item, idx) => renderValueCard(item, idx))}
                </View>
              )}
            </Animated.View>

            <View style={[s.novaWrap, shouldCenterComposition && s.novaWrapCentered]}>
              <NovaIdentityCallout
                prefix="welcome-hero-nova"
                kicker={tx('welcome.hero.nova.kicker', 'Platform guide')}
                introText={tx('welcome.hero.nova.intro', NOVA_INTRO_FALLBACK)}
                introTestId="welcome-hero-nova-intro"
                borderColor={WC.warningText}
                backgroundColor={`${WC.warningText}17`}
                kickerColor={WC.warningText}
                textColor={WC.text}
                avatarRingColor={WC.error}
                avatarSurfaceColor={WC.surface}
                avatarSize={46}
                avatarAnimationPreset="subtle"
                centered={shouldCenterComposition}
              />
            </View>

            <View style={[s.ctas, shouldCenterComposition && s.ctasCentered, (isTablet || width >= 900) && { flexDirection: 'row' }]}>
              <WelcomeLiveTickertape dark={isDark} onPress={onRegister} centered={shouldCenterComposition} />
            </View>

            <Animated.View style={[s.ctas, shouldCenterComposition && s.ctaButtonsCentered, (isTablet || width >= 900) && { flexDirection: 'row' }, stagger(5)]}>
              <TouchableOpacity style={s.ctaPrimary} onPress={onRegister} data-testid="welcome-hero-signup-btn" testID="welcome-hero-signup-btn" accessibilityRole="button">
                <Text style={s.ctaPrimaryText}>{t('welcome.hero.cta.start')}</Text>
                <Ionicons name="arrow-forward" size={15} color={WC.bg} />
              </TouchableOpacity>
              <TouchableOpacity style={s.ctaGhost} onPress={onLogin} data-testid="welcome-hero-signin-btn" testID="welcome-hero-signin-btn" accessibilityRole="button">
                <Ionicons name="play-circle-outline" size={18} color={WC.accent} />
                <Text style={s.ctaGhostText}>{t('welcome.hero.cta.explore')}</Text>
              </TouchableOpacity>
            </Animated.View>
          </View>

          <View style={[s.statsShell, shouldCenterComposition && { maxWidth: centeredShellMaxWidth + 36 }]}>
            <View style={[s.stats, !useWideHeroLayout && s.statsWrap, shouldCenterComposition && { justifyContent: 'center', alignSelf: 'center' }, isPhone && s.statsPhone, isTablet && { gap: 20 }, useWideHeroLayout && { gap: 24 }]} data-testid="welcome-hero-stats" testID="welcome-hero-stats">
              <View style={[s.stat, isPhone && s.statPhone]}>
                <View style={[s.statValRow, isPhone && s.statValRowPhone]}>
                  <Text style={[s.statVal, isTablet && { fontSize: 20 }, useWideHeroLayout && { fontSize: 24 }]} data-testid="welcome-hero-stat-active-users" testID="welcome-hero-stat-active-users">{liveActive.toLocaleString()}+</Text>
                  {deltaActive > 0 && (
                    <SpringIn>
                      <View style={s.deltaPill} data-testid="welcome-hero-delta-active-users" testID="welcome-hero-delta-active-users">
                        <Text style={s.deltaPillText}>+{deltaActive.toLocaleString()}</Text>
                      </View>
                    </SpringIn>
                  )}
                </View>
                <Text style={[s.statLbl, isPhone && s.statLblPhone, isPhone && s.statLblPhoneCentered, (isTablet || useWideHeroLayout) && { fontSize: 11 }]}>{t('home.dashboard.statActiveUsers')}</Text>
              </View>
              <View style={[s.stat, !isPhone && s.statBorder, isPhone && s.statPhone, (isTablet || useWideHeroLayout) && { paddingLeft: 28 }]}>
                <View style={[s.statValRow, isPhone && s.statValRowPhone]}>
                  <Text style={[s.statVal, isTablet && { fontSize: 20 }, useWideHeroLayout && { fontSize: 24 }]} data-testid="welcome-hero-stat-ai-sessions" testID="welcome-hero-stat-ai-sessions">{liveSessions.toLocaleString()}+</Text>
                  {deltaSessions > 0 && (
                    <SpringIn>
                      <View style={s.deltaPill} data-testid="welcome-hero-delta-ai-sessions" testID="welcome-hero-delta-ai-sessions">
                        <Text style={s.deltaPillText}>+{deltaSessions.toLocaleString()}</Text>
                      </View>
                    </SpringIn>
                  )}
                </View>
                <Text style={[s.statLbl, isPhone && s.statLblPhone, isPhone && s.statLblPhoneCentered, (isTablet || useWideHeroLayout) && { fontSize: 11 }]}>{t('home.dashboard.statAiSessions')}</Text>
              </View>
              <View style={[s.stat, !isPhone && s.statBorder, isPhone && s.statPhone, (isTablet || useWideHeroLayout) && { paddingLeft: 28 }]}>
                <Text style={[s.statVal, isPhone && { textAlign: 'center' }, isTablet && { fontSize: 20 }, useWideHeroLayout && { fontSize: 24 }]} data-testid="welcome-hero-stat-perf-boost" testID="welcome-hero-stat-perf-boost">{livePerfBoost}%</Text>
                <Text style={[s.statLbl, isPhone && s.statLblPhone, isPhone && s.statLblPhoneCentered, (isTablet || useWideHeroLayout) && { fontSize: 11 }]}>{t('home.dashboard.statPerfBoost')}</Text>
              </View>
              <View style={[s.stat, !isPhone && s.statBorder, isPhone && s.statPhone, (isTablet || useWideHeroLayout) && { paddingLeft: 28 }]}>
                <View style={[s.statValRow, isPhone && s.statValRowPhone]}>
                  <Text style={[s.statVal, isTablet && { fontSize: 20 }, useWideHeroLayout && { fontSize: 24 }]} data-testid="welcome-hero-stat-coaches" testID="welcome-hero-stat-coaches">{liveCoaches.toLocaleString()}+</Text>
                  {deltaCoaches > 0 && (
                    <SpringIn>
                      <View style={s.deltaPill} data-testid="welcome-hero-delta-coaches" testID="welcome-hero-delta-coaches">
                        <Text style={s.deltaPillText}>+{deltaCoaches.toLocaleString()}</Text>
                      </View>
                    </SpringIn>
                  )}
                </View>
                <Text style={[s.statLbl, isPhone && s.statLblPhone, isPhone && s.statLblPhoneCentered, (isTablet || useWideHeroLayout) && { fontSize: 11 }]}>{t('home.dashboard.statCoaches')}</Text>
              </View>
            </View>
          </View>
        </View>

        {useWideHeroLayout && (
          <View style={s.right} data-testid="welcome-hero-mockup" testID="welcome-hero-mockup">
            <View style={s.mockShell}>
              <View style={s.mockNav}>
                <View style={s.mockDots}>
                  <View style={[s.dot, { backgroundColor: WC.error }]} />
                  <View style={[s.dot, { backgroundColor: WC.warning }]} />
                  <View style={[s.dot, { backgroundColor: WC.success }]} />
                </View>
                <Text style={s.mockNavText}>{t('welcome.hero.mock.title')}</Text>
                <View style={s.mockLiveTag} data-testid="welcome-hero-mockup-live-tag" testID="welcome-hero-mockup-live-tag">
                  <PulseDot color={WC.successText} size={5} />
                  <Text style={s.mockLiveTagText}>{tx('welcome.hero.mock.liveSession', 'Live session')}</Text>
                </View>
              </View>
              <View style={s.mockBody}>
                <View style={s.mockChat}>
                  <View style={s.bubbleAI}>
                    <Text style={s.bubbleAIText}>{t('welcome.hero.mock.ai1')}</Text>
                  </View>
                  <View style={s.bubbleUser}>
                    <Text style={s.bubbleUserText}>{t('welcome.hero.mock.user1')}</Text>
                  </View>
                  <View style={s.bubbleAI}>
                    <Text style={s.bubbleAIText}>{t('welcome.hero.mock.ai2')}</Text>
                  </View>
                  <View style={s.typingRow} data-testid="welcome-hero-mockup-typing" testID="welcome-hero-mockup-typing">
                    <TypingDots color={WC.accent} />
                    <Text style={s.typingRowText}>{tx('welcome.hero.mock.typing', 'Nova is preparing your next milestone…')}</Text>
                  </View>
                </View>
                <View style={s.mockMetrics}>
                  {[
                    { label: t('welcome.hero.mock.goalsHit'), val: `${Math.min(99, Math.max(70, livePerfBoost))}%`, color: WC.accentText },
                    {
                      label: t('welcome.hero.mock.growth'),
                      val: `+${Math.max(1, Math.round((liveSessions / Math.max(1, liveActive)) * 100))}%`,
                      color: WC.successText,
                    },
                    { label: t('welcome.hero.mock.sessions'), val: `${liveSessions}`, color: WC.warningText },
                  ].map((m, i) => (
                    <View key={i} style={s.metric}>
                      <Text style={[s.metricVal, { color: m.color }]}>{m.val}</Text>
                      <Text style={s.metricLbl}>{m.label}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}

const makeGlow = (WC: any) => Platform.OS === 'web'
  ? { boxShadow: `0 0 120px ${withAlpha(WC.success, '0F')}, 0 0 60px ${withAlpha(WC.accent, '0A')}` } as any
  : {};
const cardBlur = Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {};
const cardLift = Platform.OS === 'web' ? { transition: 'transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease' } as any : {};

function makeStyles(WC: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens, useWideHeroLayout: boolean, isPhone: boolean) {
  return StyleSheet.create({
    wrap: {
      paddingHorizontal: horizontalPadding,
      paddingTop: 54,
      paddingBottom: 42,
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      width: '100%',
      ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}),
    },

    row: {},
    rowDesktop: { flexDirection: 'row', alignItems: 'center', gap: 54, justifyContent: 'center' },
    left: { width: '100%' },
    leftCentered: { alignItems: 'center' },
    leftMobileCard: {
      backgroundColor: WC.glassSurface,
      borderWidth: 1,
      borderColor: isDark ? WC.borderMd : WC.border,
      borderRadius: 18,
      paddingHorizontal: 16,
      paddingTop: 20,
      paddingBottom: 22,
      ...cardBlur,
      ...getShadow('sm', isDark),
    },
    leftDesktopLightPanel: {
      backgroundColor: `${WC.surface}9E`,
      borderWidth: 1,
      borderColor: WC.border,
      borderRadius: 18,
      paddingHorizontal: 30,
      paddingVertical: 30,
      ...cardBlur,
      ...getShadow('md', false),
    },
    right: { flex: 1, maxWidth: 520, width: '100%' },

    badge: { flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', paddingHorizontal: 13, paddingVertical: 7, borderRadius: 999, backgroundColor: isDark ? withAlpha(WC.accent, '12') : `${WC.surface}E8`, borderWidth: 1, borderColor: withAlpha(WC.accent, '30'), marginBottom: 26 },
    badgeText: { color: WC.accent, fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },

    contentShell: { width: '100%', alignSelf: 'center' },
    title: { color: WC.text, fontSize: 40, fontWeight: '900', letterSpacing: -1.5, lineHeight: 50, maxWidth: '100%' },
    titleCenteredText: { textAlign: 'center' },
    titleAccent: { color: WC.accent },

    featurePillRow: { flexDirection: 'row', marginTop: 22 },
    featurePill: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 999, borderWidth: 1, borderColor: withAlpha(WC.accent, '38'), backgroundColor: withAlpha(WC.accent, isDark ? '1A' : '0F'), paddingHorizontal: 12, paddingVertical: 6 },
    featurePillText: { color: WC.accent, fontSize: 12, fontWeight: '800', letterSpacing: 0.2 },

    sub: { color: WC.textSec, fontSize: 17, lineHeight: 28, marginTop: 14, maxWidth: 520 },
    subCenteredText: { textAlign: 'center', maxWidth: '100%' },
    subPhone: {
      color: WC.text,
      fontSize: 14,
      lineHeight: 22,
      marginTop: 12,
      maxWidth: '100%',
      letterSpacing: 0.1,
    },

    novaWrap: { marginTop: 16, maxWidth: 560 },
    novaWrapCentered: { alignSelf: 'center', width: '100%', maxWidth: '100%' },
    highlightRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 18 },
    highlightRowCentered: { justifyContent: 'center' },
    highlightChip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 7,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: isDark ? WC.borderMd : WC.border,
      backgroundColor: isDark ? `${WC.surface}D8` : `${WC.bgSoft}F0`,
      paddingHorizontal: 12,
      paddingVertical: 8,
      maxWidth: '100%',
    },
    highlightChipText: { color: WC.textSec, fontSize: 11, lineHeight: 16, fontWeight: '700', flexShrink: 1 },

    signalScroller: { marginTop: 18, marginHorizontal: -4 },
    signalScrollerContent: { gap: 10, paddingHorizontal: 4, paddingVertical: 2 },
    signalGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 18, width: '100%' },
    signalGridCentered: { justifyContent: 'center' },
    signalCard: {
      borderRadius: 16,
      borderWidth: 1,
      borderColor: isDark ? WC.borderMd : WC.border,
      backgroundColor: isDark ? `${WC.surface}D2` : `${WC.card}F2`,
      padding: 14,
      gap: 7,
      flexGrow: 1,
      flexBasis: useWideHeroLayout ? '31%' as any : isPhone ? '100%' as any : '48%' as any,
      minWidth: 0,
      ...cardBlur,
      ...cardLift,
      ...getShadow('sm', isDark),
    },
    signalCardPhone: { flexBasis: 'auto' as any, flexGrow: 0 },
    signalCardHover: Platform.OS === 'web' ? {
      borderColor: withAlpha(WC.accent, '66'),
      transform: [{ translateY: -3 }],
      boxShadow: `0 10px 30px ${withAlpha(WC.accent, '1F')}`,
    } as any : {},
    signalIconWrap: {
      width: 32,
      height: 32,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: withAlpha(WC.accent, isDark ? '1C' : '12'),
      borderWidth: 1,
      borderColor: withAlpha(WC.accent, '30'),
    },
    signalCardTitle: { color: WC.text, fontSize: 13, lineHeight: 18, fontWeight: '800' },
    signalCardCopy: { color: WC.textMuted, fontSize: 11, lineHeight: 18 },

    ctas: { gap: 12, marginTop: 32, width: '100%' },
    ctasCentered: { alignItems: 'center', justifyContent: 'center' },
    ctaButtonsCentered: { alignItems: 'center', justifyContent: 'center' },
    ctaPrimary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: WC.accent, paddingVertical: 16, paddingHorizontal: 22, borderRadius: 10, maxWidth: '100%', ...(typeof window !== 'undefined' ? { boxShadow: `0 8px 32px ${WC.accent}1F` } as any : {}), ...getShadow('md', isDark) },
    ctaPrimaryText: { color: WC.bg, fontSize: 15, fontWeight: '800' },
    ctaGhost: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 16, paddingHorizontal: 22, borderRadius: 10, borderWidth: 1, borderColor: isDark ? WC.borderMd : WC.borderBright, backgroundColor: isDark ? WC.surface : `${WC.surface}F5`, maxWidth: '100%', ...getShadow('sm', isDark) },
    ctaGhostText: { color: WC.accent, fontSize: 15, fontWeight: '700' },

    statsShell: { width: '100%', alignSelf: 'center' },
    stats: { flexDirection: 'row', gap: 12, marginTop: 38, paddingTop: 20, borderTopWidth: 1, borderTopColor: isDark ? WC.border : WC.borderMd, width: '100%' },
    statsWrap: { flexWrap: 'wrap' },
    statsPhone: { gap: 10, marginTop: 30 },
    stat: { flex: 1, minWidth: 0 },
    statPhone: { flexGrow: 1, flexShrink: 1, flexBasis: '47.5%' as any, minWidth: 0, padding: 12, borderRadius: 12, backgroundColor: WC.surface, borderWidth: 1, borderColor: WC.border, alignItems: 'center', justifyContent: 'center' },
    statBorder: { borderLeftWidth: 1, borderLeftColor: WC.border, paddingLeft: 12 },
    statVal: { color: WC.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 },
    statValRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
    statValRowPhone: { justifyContent: 'center', alignSelf: 'center' },
    deltaPill: { backgroundColor: withAlpha(WC.successText, '1F'), borderWidth: 1, borderColor: withAlpha(WC.successText, '40'), paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999 },
    deltaPillText: { color: WC.successText, fontSize: 10, fontWeight: '800', letterSpacing: 0.2 },
    statLbl: { color: WC.textDim, fontSize: 10, fontWeight: '600', marginTop: 4, letterSpacing: 0.4, textTransform: 'uppercase' },
    statLblPhone: { fontSize: 9, lineHeight: 12, letterSpacing: 0.2 },
    statLblPhoneCentered: { textAlign: 'center', width: '100%' },

    mockShell: { borderRadius: 16, backgroundColor: WC.surface, borderWidth: 1, borderColor: WC.borderMd, overflow: 'hidden', ...makeGlow(WC), ...cardBlur, ...getShadow('md', isDark) },
    mockNav: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderBottomWidth: 1, borderBottomColor: WC.border },
    mockDots: { flexDirection: 'row', gap: 6 },
    dot: { width: 10, height: 10, borderRadius: 5 },
    mockNavText: { color: WC.textDim, fontSize: 12, fontWeight: '600', flex: 1 },
    mockLiveTag: { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 999, borderWidth: 1, borderColor: withAlpha(WC.successText, '40'), backgroundColor: withAlpha(WC.successText, '14'), paddingHorizontal: 9, paddingVertical: 4 },
    mockLiveTagText: { color: WC.successText, fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
    mockBody: { padding: 18 },
    mockChat: { gap: 10, marginBottom: 18 },
    bubbleAI: { backgroundColor: withAlpha(WC.accent, '0C'), borderRadius: 14, borderTopLeftRadius: 4, padding: 12, maxWidth: '88%' },
    bubbleAIText: { color: WC.textSec, fontSize: 12, lineHeight: 18 },
    bubbleUser: { backgroundColor: withAlpha(WC.accent, '12'), borderRadius: 14, borderTopRightRadius: 4, padding: 12, maxWidth: '88%', alignSelf: 'flex-end' },
    bubbleUserText: { color: WC.accentText, fontSize: 12, lineHeight: 18, fontWeight: '600' },
    typingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 4, paddingTop: 2 },
    typingRowText: { color: WC.textDim, fontSize: 11, fontStyle: 'italic' },
    mockMetrics: { flexDirection: 'row', gap: 10 },
    metric: { flex: 1, backgroundColor: WC.surface, borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: WC.border, ...getShadow('sm', isDark) },
    metricVal: { fontSize: 20, fontWeight: '800' },
    metricLbl: { color: WC.textDim, fontSize: 10, fontWeight: '600', marginTop: 3 },
  });
}
