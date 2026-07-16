import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { Ionicons } from '@expo/vector-icons';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY, MONO_FONT_FAMILY } from '../../constants/appTypography';

const GRADIENT_CSS = `
@keyframes heroGradient {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
@keyframes pulse-glow {
  0%, 100% { opacity: 0.4; transform: scale(1); }
  50% { opacity: 0.85; transform: scale(1.06); }
}
@keyframes float-orb {
  0%, 100% { transform: translateY(0px) rotate(0deg); }
  33% { transform: translateY(-12px) rotate(120deg); }
  66% { transform: translateY(6px) rotate(240deg); }
}
@keyframes slide-up {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes live-dot {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16,185,129,0.7); }
  50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(16,185,129,0); }
}
`;

function AnimatedCounter({ end, duration = 800, prefix = '', suffix = '', color }: { end: number; duration?: number; prefix?: string; suffix?: string; color?: string }) {
  const [display, setDisplay] = useState(0);
  const prevRef = useRef(0);
  const rafRef = useRef<any>(null);

  useEffect(() => {
    if (Platform.OS !== 'web') {
      setDisplay(end);
      prevRef.current = end;
      return;
    }
    const from = prevRef.current;
    const diff = end - from;
    if (diff === 0) return;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + diff * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(animate);
      else {
        setDisplay(end);
        prevRef.current = end;
      }
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [end, duration]);

  return (
    <Text style={{
      fontSize: 28,
      fontWeight: '900',
      color,
      letterSpacing: -1,
      fontFamily: DISPLAY_FONT_FAMILY,
    }}>
      {prefix}{display.toLocaleString()}{suffix}
    </Text>
  );
}

interface HeroProps {
  responsiveWidth?: number;
  stats: {
    active_users: number;
    ai_sessions_today: number;
    performance_boost: number;
    global_coaches: number;
    total_users: number;
    ai_status: string;
  };
  userName: string;
  onStartJourney: () => void;
  onExploreTools: () => void;
}

export default function HomeHero({ responsiveWidth, stats, userName, onStartJourney, onExploreTools }: HeroProps) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 1024;
  const isTablet = width >= 768 && width < 1024;
  const isWide = width >= 1380;
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'hero-gradient-css';
      if (!document.getElementById(id)) {
        const style = document.createElement('style');
        style.id = id;
        style.textContent = GRADIENT_CSS;
        document.head.appendChild(style);
      }
    }
  }, []);

  const statCards = [
    { label: t('home.dashboard.statActiveUsers'), value: stats.active_users, suffix: '+', color: colors.primary },
    { label: t('home.dashboard.statAiSessions'), value: stats.ai_sessions_today, suffix: '+', color: colors.accent },
    { label: t('home.dashboard.statPerfBoost'), value: stats.performance_boost, suffix: '%', color: colors.successText },
    { label: t('home.dashboard.statCoaches'), value: stats.global_coaches, suffix: '+', color: colors.warningText },
  ].filter((s) => Number(s.value) > 0);

  const { data: pulseData } = useLiveQuery('/home/today-pulse', { entity: 'today_pulse', pollInterval: 60000 });

  const pulseSignals = useMemo(() => ([
    {
      id: 'streak',
      icon: 'flame' as const,
      label: tx('home.hero.signal.streak', 'Day streak'),
      value: `${Number(pulseData?.streak_days || 0).toLocaleString()} ${tx('home.hero.signal.streakUnit', 'days')}`,
      tone: colors.warningText,
    },
    {
      id: 'sessions',
      icon: 'chatbubbles' as const,
      label: tx('home.hero.signal.sessions', 'Sessions today'),
      value: `${Number(pulseData?.sessions_today || 0).toLocaleString()} ${tx('home.hero.signal.today', 'today')}`,
      tone: colors.primary,
    },
    {
      id: 'badges',
      icon: 'trophy' as const,
      label: tx('home.hero.signal.badges', 'Badges earned'),
      value: `${Number(pulseData?.badges_earned || 0)}/${Number(pulseData?.badges_total || 6)}`,
      tone: colors.successText,
    },
    {
      id: 'setup',
      icon: 'rocket' as const,
      label: tx('home.hero.signal.setup', 'Setup progress'),
      value: `${Number(pulseData?.checklist_percent || 0)}%`,
      tone: colors.purpleText || colors.purple,
    },
  ]), [colors.primary, colors.purple, colors.purpleText, colors.successText, colors.warningText, pulseData, tx]);

  const momentumSteps = useMemo(() => ([
    tx('home.hero.momentum.step1', 'Review Nova guidance and lock the top priority.'),
    tx('home.hero.momentum.step2', 'Launch one revenue or learning action within the first 10 minutes.'),
    tx('home.hero.momentum.step3', 'Come back for the next recommendation when you complete a step.'),
  ]), [tx]);

  const returnLoopChips = useMemo(() => ([
    tx('home.hero.loop.one', 'Daily brief'),
    tx('home.hero.loop.two', 'Focus mode'),
    tx('home.hero.loop.three', 'Nova follow-up'),
  ]), [tx]);

  const heroGradient = darkMode
    ? 'linear-gradient(135deg, rgba(4,10,20,0.96) 0%, rgba(10,24,48,0.94) 38%, rgba(4,18,24,0.96) 100%)'
    : 'linear-gradient(135deg, rgba(255,255,255,0.96) 0%, rgba(236,244,255,0.98) 44%, rgba(239,252,247,0.95) 100%)';
  const frameBg = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'B8' : 'F0')
    : colors.card;
  const frameBorder = colors.border;
  const frameShadow = darkMode ? '0 28px 60px rgba(2,6,23,0.34)' : '0 24px 54px rgba(15,23,42,0.12)';
  const titleColor = colors.text;
  const subtitleColor = colors.textSecondary;
  const secondaryBg = colors.bgSoft;
  const secondaryBorder = colors.borderMd;
  const secondaryText = colors.textSecondary;
  const statCardBg = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, darkMode ? '7E' : 'D8')
    : frameBg;

  return (
    <View data-testid="home-hero-section" testID="home-hero-section" style={{ position: 'relative', overflow: 'hidden', marginBottom: 0, paddingHorizontal: isDesktop ? 20 : 14 }}>
      {Platform.OS === 'web' && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 0, background: heroGradient, backgroundSize: '400% 400%', animation: 'heroGradient 15s ease infinite' } as any}>
          <div style={{ position: 'absolute', top: '8%', left: '3%', width: 220, height: 220, borderRadius: '50%', background: `radial-gradient(circle, ${colors.primarySoft} 0%, transparent 70%)`, animation: 'float-orb 8s ease-in-out infinite', filter: 'blur(48px)' } as any} />
          <div style={{ position: 'absolute', bottom: '12%', right: '6%', width: 260, height: 260, borderRadius: '50%', background: `radial-gradient(circle, ${colors.accentSoft} 0%, transparent 72%)`, animation: 'float-orb 10s ease-in-out infinite 2s', filter: 'blur(54px)' } as any} />
          <div style={{ position: 'absolute', top: '40%', right: '26%', width: 150, height: 150, borderRadius: '50%', background: `radial-gradient(circle, ${colors.successSoft} 0%, transparent 72%)`, animation: 'float-orb 12s ease-in-out infinite 4s', filter: 'blur(38px)' } as any} />
          <div style={{ position: 'absolute', inset: 0, opacity: darkMode ? 0.03 : 0.025, backgroundImage: darkMode ? `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)` : `linear-gradient(rgba(15,23,42,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.08) 1px, transparent 1px)`, backgroundSize: '40px 40px' } as any} />
        </div>
      )}

      <View style={{ position: 'relative', zIndex: 1, paddingTop: isDesktop ? 24 : 20, paddingBottom: isDesktop ? 20 : 16, overflow: 'hidden' }}>
        <View style={{ maxWidth: 1400, width: '100%', alignSelf: 'center', backgroundColor: frameBg, borderWidth: 1, borderColor: frameBorder, borderRadius: isDesktop ? 30 : 24, paddingHorizontal: isTablet ? 20 : isDesktop ? 30 : 18, paddingVertical: isTablet ? 20 : isDesktop ? 28 : 18, overflow: 'hidden', ...(Platform.OS === 'web' ? { backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)', boxShadow: frameShadow } as any : {}) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 18 }}>
            {Platform.OS === 'web' ? (
              <div data-testid="ai-status-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderRadius: 999, background: colors.successSoft, border: `1px solid ${colors.success}40`, animation: 'slide-up 0.6s ease' } as any}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: colors.success, animation: 'live-dot 2s ease-in-out infinite' } as any} />
                <span style={{ color: colors.successText, fontSize: 11, fontWeight: 800, letterSpacing: 1.2, textTransform: 'uppercase' } as any}>{tx('home.hero.status', 'AI System Live')}</span>
              </div>
            ) : (
              <View data-testid="ai-status-badge" testID="ai-status-badge" style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 7, borderRadius: 999, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.success }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success }} />
                <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800', letterSpacing: 1.2 }}>{tx('home.hero.status', 'AI System Live').toUpperCase()}</Text>
              </View>
            )}
          </View>

          <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 18 }}>
            <View style={{ flex: isDesktop ? (isWide ? 1.35 : 1.15) : undefined, minWidth: 0, justifyContent: isDesktop ? 'space-between' : undefined }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }} data-testid="home-hero-kicker" testID="home-hero-kicker">
                {tx('home.hero.kicker', 'Personal command center')}
              </Text>
              <Text style={{ fontSize: isWide ? 56 : isDesktop ? 46 : 34, fontWeight: '900', color: titleColor, letterSpacing: -2.4, lineHeight: isWide ? 60 : isDesktop ? 50 : 40, marginTop: 12, fontFamily: DISPLAY_FONT_FAMILY }} data-testid="home-hero-title" testID="home-hero-title">
                {t('home.dashboard.welcomeBack')}{' '}
                <Text style={{ color: colors.primary }}>{userName}</Text>
              </Text>
              <Text style={{ fontSize: isDesktop ? 16 : 14, color: subtitleColor, lineHeight: isDesktop ? 27 : 22, marginTop: 14, maxWidth: 660, fontFamily: BODY_FONT_FAMILY }} data-testid="home-hero-description" testID="home-hero-description">
                {tx('home.hero.description', 'Your dashboard now behaves like an AI operating room: it highlights what changed, what matters next, and how Nova can accelerate the next win.')}
              </Text>

              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 18 }} data-testid="home-hero-loop-chips" testID="home-hero-loop-chips">
                {returnLoopChips.map((chip, index) => (
                  <View key={`${chip}-${index}`} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}30`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 12, paddingVertical: 7 }} data-testid={`home-hero-loop-chip-${index}`} testID={`home-hero-loop-chip-${index}`}>
                    <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700', fontFamily: BODY_FONT_FAMILY }}>{chip}</Text>
                  </View>
                ))}
              </View>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12, marginTop: 26 }}>
                <TouchableOpacity onPress={onStartJourney} data-testid="cta-start-journey" testID="cta-start-journey" accessibilityRole="button" accessibilityLabel="Start your journey" style={{ paddingHorizontal: 18, paddingVertical: 15, borderRadius: 16, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minWidth: isDesktop ? 240 : undefined }}>
                  <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>{t('home.dashboard.ctaStart')}</Text>
                  <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800' }}>→</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={onExploreTools} data-testid="cta-explore-tools" testID="cta-explore-tools" accessibilityRole="button" accessibilityLabel="Explore AI tools" style={{ paddingHorizontal: 18, paddingVertical: 15, borderRadius: 16, borderWidth: 1, borderColor: secondaryBorder, backgroundColor: secondaryBg, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minWidth: isDesktop ? 220 : undefined }}>
                  <Text style={{ color: secondaryText, fontSize: 15, fontWeight: '700', fontFamily: BODY_FONT_FAMILY }}>{t('home.dashboard.ctaExplore')}</Text>
                </TouchableOpacity>
              </View>

              {statCards.length > 0 ? (
              <View data-testid="hero-stats-grid" testID="hero-stats-grid" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 26 }}>
                {statCards.map((s) => (
                  <View key={s.label} data-testid={`hero-stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`} testID={`hero-stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`} style={{ flexGrow: 1, minWidth: isDesktop ? 180 : 150, padding: isDesktop ? 18 : 14, borderRadius: 18, backgroundColor: statCardBg, borderWidth: 1, borderColor: frameBorder, overflow: 'hidden' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 10, minWidth: 0 }}>
                      <View style={{ width: 9, height: 9, borderRadius: 999, backgroundColor: s.color }} />
                      <Text style={{ color: subtitleColor, fontSize: 10, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }} numberOfLines={1}>{s.label}</Text>
                    </View>
                    <AnimatedCounter end={s.value} suffix={s.suffix} color={titleColor} />
                  </View>
                ))}
              </View>
              ) : null}
            </View>

            <View style={{ flex: isDesktop ? 0.92 : undefined, minWidth: 0, gap: 14 }}>
              <View style={{ borderRadius: 22, borderWidth: 1, borderColor: `${colors.primary}2E`, backgroundColor: darkMode ? 'rgba(7,12,20,0.72)' : 'rgba(255,255,255,0.78)', padding: 18 }} data-testid="home-hero-pulse-card" testID="home-hero-pulse-card">
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>
                  {tx('home.hero.pulse.label', 'Today pulse')}
                </Text>
                <Text style={{ color: titleColor, fontSize: 24, fontWeight: '900', letterSpacing: -1.2, marginTop: 10, fontFamily: DISPLAY_FONT_FAMILY }} data-testid="home-hero-pulse-title" testID="home-hero-pulse-title">
                  {tx('home.hero.pulse.title', 'A premium command view that rewards daily return behavior.')}
                </Text>
                <View style={{ gap: 12, marginTop: 18 }} data-testid="home-hero-pulse-signals" testID="home-hero-pulse-signals">
                  {pulseSignals.map((signal) => (
                    <View key={signal.id} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderRadius: 16, borderWidth: 1, borderColor: `${signal.tone}26`, backgroundColor: `${signal.tone}10`, paddingHorizontal: 14, paddingVertical: 12 }} data-testid={`home-hero-pulse-signal-${signal.id}`} testID={`home-hero-pulse-signal-${signal.id}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                        <Ionicons name={signal.icon} size={13} color={signal.tone} />
                        <Text style={{ color: subtitleColor, fontSize: 12, fontWeight: '600', flexShrink: 1, fontFamily: BODY_FONT_FAMILY }}>{signal.label}</Text>
                      </View>
                      <Text style={{ color: signal.tone, fontSize: 12, fontWeight: '800', textAlign: 'right', fontFamily: MONO_FONT_FAMILY }}>{signal.value}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={{ borderRadius: 22, borderWidth: 1, borderColor: frameBorder, backgroundColor: darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.68)', padding: 18 }} data-testid="home-hero-momentum-card" testID="home-hero-momentum-card">
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>
                  {tx('home.hero.momentum.label', 'Momentum protocol')}
                </Text>
                <Text style={{ color: titleColor, fontSize: 20, fontWeight: '900', letterSpacing: -0.8, marginTop: 10, fontFamily: DISPLAY_FONT_FAMILY }}>
                  {tx('home.hero.momentum.title', 'Three actions that keep the dashboard habit-forming.')}
                </Text>
                <View style={{ gap: 12, marginTop: 16 }}>
                  {momentumSteps.map((step, index) => (
                    <View key={`${step}-${index}`} style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }} data-testid={`home-hero-momentum-step-${index}`} testID={`home-hero-momentum-step-${index}`}>
                      <View style={{ width: 28, height: 28, borderRadius: 999, backgroundColor: `${colors.primary}18`, borderWidth: 1, borderColor: `${colors.primary}32`, alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', fontFamily: MONO_FONT_FAMILY }}>{index + 1}</Text>
                      </View>
                      <Text style={{ flex: 1, color: subtitleColor, fontSize: 13, lineHeight: 20, fontFamily: BODY_FONT_FAMILY }}>{step}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          </View>
        </View>
      </View>
    </View>
  );
}