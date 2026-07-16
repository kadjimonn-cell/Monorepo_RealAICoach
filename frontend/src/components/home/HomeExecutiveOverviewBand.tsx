import React from 'react';
import { Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

interface HomeSectionItem {
  id: string;
  label: string;
  icon: string;
}

interface HomeExecutiveOverviewBandProps {
  responsiveWidth?: number;
  stats: {
    active_users: number;
    ai_sessions_today: number;
    performance_boost: number;
    global_coaches: number;
  };
  featureCount: number;
  commandActionCount: number;
  onNavigate: (route: string) => void;
  onSectionSelect: (id: string) => void;
  sections: HomeSectionItem[];
  isAdmin: boolean;
}

export default function HomeExecutiveOverviewBand({
  responsiveWidth,
  stats,
  featureCount,
  commandActionCount,
  onNavigate,
  onSectionSelect,
  sections,
  isAdmin,
}: HomeExecutiveOverviewBandProps) {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 1120;

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const executiveTitle = isAdmin ? 'Executive Operations Command Center' : 'Personal AI Command Center';
  const executiveSubtitle = isAdmin
    ? 'Monitor operational readiness, activate priority workflows, and move across mission-critical systems from one command surface.'
    : 'Track your learning progress, launch priority workflows, and navigate your personal AI stack from one command surface.';

  const bandBg = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'EA')
    : colors.card;

  const kpis = [
    {
      id: 'sessions',
      label: tx('home.enterpriseBand.sessions', 'AI sessions today'),
      value: Number(stats.ai_sessions_today || 0),
      icon: 'sparkles-outline',
      tone: colors.primary,
    },
    {
      id: 'users',
      label: tx('home.enterpriseBand.activeUsers', 'Active users'),
      value: Number(stats.active_users || 0),
      icon: 'people-outline',
      tone: colors.accent,
    },
    {
      id: 'features',
      label: tx('home.enterpriseBand.liveFeatures', 'Live features'),
      value: Number(featureCount || 0),
      icon: 'apps-outline',
      tone: colors.success,
    },
    {
      id: 'actions',
      label: tx('home.enterpriseBand.priorityActions', 'Priority actions'),
      value: Number(commandActionCount || 0),
      icon: 'flash-outline',
      tone: colors.warning,
    },
  ];

  const commandSignals = [
    {
      id: 'live',
      icon: 'pulse-outline',
      label: tx('home.enterpriseBand.signal.live', 'Workspace live'),
      value: tx('home.enterpriseBand.signal.online', 'online'),
      tone: colors.successText,
      bg: `${colors.success}14`,
    },
    {
      id: 'features',
      icon: 'grid-outline',
      label: tx('home.enterpriseBand.signal.features', 'Feature coverage'),
      value: String(Number(featureCount || 0)),
      tone: colors.primary,
      bg: `${colors.primary}12`,
    },
    {
      id: 'actions',
      icon: 'flash-outline',
      label: tx('home.enterpriseBand.signal.actions', 'Action queue'),
      value: String(Number(commandActionCount || 0)),
      tone: colors.warningText,
      bg: `${colors.warning}12`,
    },
  ];

  return (
    <View
      style={{
        marginHorizontal: 20,
        marginTop: 12,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: bandBg,
        padding: isDesktop ? 20 : 16,
        gap: 14,
        ...(Platform.OS === 'web'
          ? {
              backdropFilter: 'blur(14px)',
              WebkitBackdropFilter: 'blur(14px)',
              boxShadow: darkMode ? '0 18px 42px rgba(2,6,23,0.28)' : '0 16px 38px rgba(15,23,42,0.10)',
            } as any
          : {}),
      }}
      data-testid="home-executive-overview-band"
      testID="home-executive-overview-band"
    >
      <View style={{ flexDirection: isDesktop ? 'row' : 'column', justifyContent: 'space-between', gap: 14 }}>
        <View style={{ flex: 1.15 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }} data-testid="home-executive-overview-band-kicker" testID="home-executive-overview-band-kicker">
            {tx('home.enterpriseBand.kicker', 'Daily briefing')}
          </Text>
          <Text
            style={{ color: colors.text, fontSize: isDesktop ? 24 : 19, fontWeight: '900', letterSpacing: -1, marginTop: 8, fontFamily: DISPLAY_FONT_FAMILY }}
            data-testid="home-executive-overview-band-title"
            testID="home-executive-overview-band-title"
          >
            {executiveTitle}
          </Text>
          <Text
            style={{ color: colors.textSec, fontSize: 12, marginTop: 6, lineHeight: 20, maxWidth: 700, fontFamily: BODY_FONT_FAMILY }}
            data-testid="home-executive-overview-band-subtitle"
            testID="home-executive-overview-band-subtitle"
          >
            {executiveSubtitle}
          </Text>

          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 14 }} data-testid="home-executive-overview-band-signals" testID="home-executive-overview-band-signals">
            {commandSignals.map((signal) => (
              <View key={signal.id} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${signal.tone}26`, backgroundColor: signal.bg, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid={`home-executive-overview-band-signal-${signal.id}`} testID={`home-executive-overview-band-signal-${signal.id}`}>
                <Ionicons name={signal.icon as any} size={13} color={signal.tone} />
                <Text style={{ color: signal.tone, fontSize: 11, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>{signal.label}: {signal.value}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'flex-start' }}>
          <TouchableOpacity
            accessibilityLabel="Home executive band open features button"
            onPress={() => onNavigate('/feature-gallery')}
            style={{
              borderRadius: 14,
              borderWidth: 1,
              borderColor: `${colors.primary}66`,
              backgroundColor: `${colors.primary}16`,
              paddingHorizontal: 14,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
            data-testid="home-executive-band-open-features"
            testID="home-executive-band-open-features"
          >
            <Ionicons name="rocket-outline" size={14} color={colors.primary} />
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>
              {tx('home.enterpriseBand.openFeatures', 'Open Feature Hub')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            accessibilityLabel="Home executive band open learning button"
            onPress={() => onNavigate('/ai-learning-hub')}
            style={{
              borderRadius: 14,
              borderWidth: 1,
              borderColor: `${colors.accent}66`,
              backgroundColor: `${colors.accent}14`,
              paddingHorizontal: 14,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
            data-testid="home-executive-band-open-learning"
            testID="home-executive-band-open-learning"
          >
            <Ionicons name="school-outline" size={14} color={colors.accent} />
            <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>
              {tx('home.enterpriseBand.openLearning', 'Open Learning Hub')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="home-executive-overview-kpis" testID="home-executive-overview-kpis">
        {kpis.map((kpi) => (
          <View
            key={kpi.id}
            style={{
              flex: 1,
              minWidth: isDesktop ? 180 : 148,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: `${kpi.tone}33`,
              backgroundColor: `${kpi.tone}10`,
              padding: 13,
            }}
            data-testid={`home-executive-overview-kpi-${kpi.id}`}
            testID={`home-executive-overview-kpi-${kpi.id}`}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name={kpi.icon as any} size={13} color={kpi.tone} />
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 0.9, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>{kpi.label}</Text>
            </View>
            <Text style={{ color: colors.text, fontSize: 28, fontWeight: '900', marginTop: 8, letterSpacing: -1, fontFamily: DISPLAY_FONT_FAMILY }} data-testid={`home-executive-overview-kpi-value-${kpi.id}`} testID={`home-executive-overview-kpi-value-${kpi.id}`}>
              {kpi.value}
            </Text>
          </View>
        ))}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ flexDirection: 'row', gap: 8 }} data-testid="home-executive-overview-section-jump" testID="home-executive-overview-section-jump">
        {sections.map((section) => (
          <TouchableOpacity
            accessibilityLabel="On section select in home executive overview band button"
            key={section.id}
            onPress={() => onSectionSelect(section.id)}
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.surface,
              paddingHorizontal: 12,
              paddingVertical: 8,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
            data-testid={`home-executive-overview-section-${section.id}`}
            testID={`home-executive-overview-section-${section.id}`}
          >
            <Ionicons name={section.icon as any} size={12} color={colors.primary} />
            <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700', fontFamily: BODY_FONT_FAMILY }}>{section.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}