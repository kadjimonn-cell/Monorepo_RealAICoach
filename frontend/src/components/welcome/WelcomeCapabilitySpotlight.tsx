import React, { useMemo } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { withAlpha } from '../../utils/colorAlpha';
import { getShadow } from '../../utils/themeShadows';
import type { HydratedCapability } from './welcomeCapabilityCatalog';

type WelcomeCapabilitySpotlightProps = {
  colors: any;
  isDark: boolean;
  isDesktop: boolean;
  isTablet: boolean;
  compact: boolean;
  wideLayout: boolean;
  title: string;
  subtitle: string;
  planLabel: string;
  selectedCapability: HydratedCapability;
  badgeLabel: string;
  categoryLabel: string;
  tierLabel: string;
  accessibleNowLabel: string;
  lockedLabel: string;
  spotlightSummary: string;
  primaryCtaLabel: string;
  secondaryCtaLabel: string;
  onPrimaryPress: () => void;
  onSecondaryPress: () => void;
  accessibleCount: number;
  lockedCount: number;
  totalCount: number;
  playbooksLabel: string;
  playbooksValue: string;
  workflowLabel: string;
  workflowValue: string;
  trackItems: { id: string; label: string; state: 'live' | 'locked' }[];
  trackLiveLabel: string;
  trackLockedLabel: string;
};

export function WelcomeCapabilitySpotlight({
  colors,
  isDark,
  isDesktop,
  isTablet,
  compact,
  wideLayout,
  title,
  subtitle,
  planLabel,
  selectedCapability,
  badgeLabel,
  categoryLabel,
  tierLabel,
  accessibleNowLabel,
  lockedLabel,
  spotlightSummary,
  primaryCtaLabel,
  secondaryCtaLabel,
  onPrimaryPress,
  onSecondaryPress,
  accessibleCount,
  lockedCount,
  totalCount,
  playbooksLabel,
  playbooksValue,
  workflowLabel,
  workflowValue,
  trackItems,
  trackLiveLabel,
  trackLockedLabel,
}: WelcomeCapabilitySpotlightProps) {
  const s = useMemo(() => makeStyles(colors, isDark, isDesktop, isTablet, compact, wideLayout), [colors, isDark, isDesktop, isTablet, compact, wideLayout]);
  const headingFont = Platform.OS === 'web' ? { fontFamily: 'Outfit, sans-serif' as any } : null;
  const bodyFont = Platform.OS === 'web' ? { fontFamily: 'IBM Plex Sans, sans-serif' as any } : null;

  return (
    <View style={s.wrap} data-testid="welcome-capability-spotlight" testID="welcome-capability-spotlight">
      <View style={s.copyColumn}>
        <View style={s.kickerRow}>
          <Text style={[s.kicker, bodyFont]} data-testid="welcome-capability-command-label" testID="welcome-capability-command-label">{title}</Text>
          <View style={s.planPill} data-testid="welcome-capability-plan-pill" testID="welcome-capability-plan-pill">
            <Text style={[s.planPillText, bodyFont]}>{planLabel}</Text>
          </View>
        </View>

        <Text style={[s.headline, headingFont]} data-testid="welcome-capability-spotlight-title" testID="welcome-capability-spotlight-title">
          {workflowValue}
        </Text>
        <Text style={[s.subheadline, bodyFont]} data-testid="welcome-capability-spotlight-summary" testID="welcome-capability-spotlight-summary">
          {spotlightSummary}
        </Text>

        <View style={s.metaRow}>
          <View style={[s.metaPill, { backgroundColor: withAlpha(selectedCapability.color, '15'), borderColor: withAlpha(selectedCapability.color, '38') }]} data-testid="welcome-capability-badge-pill" testID="welcome-capability-badge-pill">
            <Text style={[s.metaPillText, { color: selectedCapability.color }, bodyFont]}>{badgeLabel}</Text>
          </View>
          <View style={s.metaPill} data-testid="welcome-capability-category-pill" testID="welcome-capability-category-pill">
            <Text style={[s.metaPillText, bodyFont]}>{categoryLabel}</Text>
          </View>
          <View style={s.metaPill} data-testid="welcome-capability-tier-pill" testID="welcome-capability-tier-pill">
            <Text style={[s.metaPillText, bodyFont]}>{tierLabel}</Text>
          </View>
        </View>

        <View style={s.metricRow}>
          {[
            { id: 'available', label: accessibleNowLabel, value: String(accessibleCount) },
            { id: 'locked', label: lockedLabel, value: String(lockedCount) },
            { id: 'catalog', label: subtitle, value: String(totalCount) },
          ].map((item) => (
            <View key={item.id} style={s.metricCard} data-testid={`welcome-capability-spotlight-metric-${item.id}`} testID={`welcome-capability-spotlight-metric-${item.id}`}>
              <Text style={[s.metricLabel, bodyFont]}>{item.label}</Text>
              <Text style={[s.metricValue, headingFont]}>{item.value}</Text>
            </View>
          ))}
        </View>

        <View style={s.ctaRow}>
          <TouchableOpacity onPress={onPrimaryPress} style={s.primaryCta} data-testid="welcome-capability-primary-cta" testID="welcome-capability-primary-cta">
            <Text style={[s.primaryCtaText, bodyFont]}>{primaryCtaLabel}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onSecondaryPress} style={s.secondaryCta} data-testid="welcome-capability-secondary-cta" testID="welcome-capability-secondary-cta">
            <Text style={[s.secondaryCtaText, bodyFont]}>{secondaryCtaLabel}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={s.boardColumn} data-testid="welcome-capability-command-board" testID="welcome-capability-command-board">
        <View style={s.boardHero}>
          <View style={s.boardIconShell}><Ionicons name={selectedCapability.icon as any} size={22} color={selectedCapability.color} /></View>
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={[s.boardHeroLabel, bodyFont]}>{playbooksLabel}</Text>
            <Text style={[s.boardHeroValue, headingFont]}>{playbooksValue}</Text>
          </View>
        </View>

        <View style={s.boardStatsRow}>
          <View style={s.boardStatCard} data-testid="welcome-capability-board-stat-workflow" testID="welcome-capability-board-stat-workflow">
            <Text style={[s.boardStatLabel, bodyFont]}>{workflowLabel}</Text>
            <Text style={[s.boardStatValue, headingFont]}>{workflowValue}</Text>
          </View>
          <View style={s.boardStatCard} data-testid="welcome-capability-board-stat-tier" testID="welcome-capability-board-stat-tier">
            <Text style={[s.boardStatLabel, bodyFont]}>{tierLabel}</Text>
            <Text style={[s.boardStatValue, headingFont]}>{selectedCapability.tier.toUpperCase()}</Text>
          </View>
        </View>

        <View style={s.trackWrap} data-testid="welcome-capability-track-list" testID="welcome-capability-track-list">
          {trackItems.map((item, index) => (
            <View key={item.id} style={s.trackRow} data-testid={`welcome-capability-track-item-${index}`} testID={`welcome-capability-track-item-${index}`}>
              <View style={[s.trackDot, { backgroundColor: item.state === 'live' ? colors.success : colors.warning }]} />
              <Text style={[s.trackLabel, bodyFont]} numberOfLines={1}>{item.label}</Text>
              <Text style={[s.trackState, bodyFont]}>{item.state === 'live' ? trackLiveLabel : trackLockedLabel}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

function makeStyles(colors: any, isDark: boolean, isDesktop: boolean, isTablet: boolean, compact: boolean, wideLayout: boolean) {
  const split = wideLayout;
  const stackedMetrics = compact || !wideLayout;

  return StyleSheet.create({
    wrap: {
      flexDirection: split ? 'row' : 'column',
      gap: 16,
      alignItems: 'stretch',
      width: '100%',
    },
    copyColumn: {
      flex: split ? 1.15 : undefined,
      width: split ? undefined : '100%',
      minWidth: 0,
      borderRadius: 24,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.surface, isDark ? 'F0' : 'FA'),
      padding: compact ? 18 : 24,
      gap: 16,
      ...getShadow('md', isDark),
      alignItems: compact ? 'center' : 'stretch',
    },
    kickerRow: {
      flexDirection: compact ? 'column' : 'row',
      alignItems: compact ? 'center' : 'center',
      justifyContent: 'space-between',
      gap: 10,
      flexWrap: 'wrap',
    },
    kicker: {
      color: colors.textMuted,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.8,
      textTransform: 'uppercase',
      textAlign: compact ? 'center' : 'left',
    },
    planPill: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: withAlpha(colors.primary, '36'),
      backgroundColor: withAlpha(colors.primary, '12'),
      paddingHorizontal: 10,
      paddingVertical: 6,
      maxWidth: compact ? '100%' : undefined,
      alignSelf: compact ? 'center' : 'auto',
    },
    planPillText: {
      color: colors.primary,
      fontSize: 11,
      fontWeight: '800',
      textAlign: 'center',
      flexShrink: 1,
    },
    headline: {
      color: colors.text,
      fontSize: compact ? 26 : (wideLayout ? 36 : 32),
      lineHeight: compact ? 32 : (wideLayout ? 42 : 38),
      fontWeight: '900',
      letterSpacing: -1.2,
      textAlign: compact ? 'center' : 'left',
    },
    subheadline: {
      color: colors.textSec,
      fontSize: 15,
      lineHeight: 25,
      maxWidth: split ? 660 : '100%',
      textAlign: compact ? 'center' : 'left',
    },
    metaRow: {
      flexDirection: 'row',
      gap: 8,
      flexWrap: 'wrap',
      justifyContent: compact ? 'center' : 'flex-start',
    },
    metaPill: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'B6' : 'EE'),
      paddingHorizontal: 10,
      paddingVertical: 6,
      maxWidth: compact ? '100%' : undefined,
    },
    metaPillText: {
      color: colors.textSec,
      fontSize: 11,
      fontWeight: '700',
      textAlign: 'center',
      flexShrink: 1,
    },
    metricRow: {
      flexDirection: stackedMetrics ? 'column' : 'row',
      gap: 10,
    },
    metricCard: {
      flex: stackedMetrics ? undefined : 1,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'C8' : 'F4'),
      padding: 14,
      gap: 8,
      alignItems: compact ? 'center' : 'stretch',
    },
    metricLabel: {
      color: colors.textMuted,
      fontSize: 10,
      fontWeight: '800',
      textTransform: 'uppercase',
      letterSpacing: 1.1,
      textAlign: compact ? 'center' : 'left',
    },
    metricValue: {
      color: colors.text,
      fontSize: 26,
      fontWeight: '900',
      letterSpacing: -0.8,
      textAlign: compact ? 'center' : 'left',
    },
    ctaRow: {
      flexDirection: stackedMetrics ? 'column' : 'row',
      gap: 10,
      width: '100%',
    },
    primaryCta: {
      borderRadius: 14,
      backgroundColor: colors.primary,
      paddingHorizontal: 18,
      paddingVertical: 14,
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: compact ? undefined : 190,
      width: compact ? '100%' : undefined,
    },
    primaryCtaText: {
      color: colors.primaryText,
      fontSize: 13,
      fontWeight: '800',
    },
    secondaryCta: {
      borderRadius: 14,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      backgroundColor: withAlpha(colors.card, isDark ? 'D9' : 'F2'),
      paddingHorizontal: 18,
      paddingVertical: 14,
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: compact ? undefined : 170,
      width: compact ? '100%' : undefined,
    },
    secondaryCtaText: {
      color: colors.text,
      fontSize: 13,
      fontWeight: '800',
    },
    boardColumn: {
      flex: split ? 0.9 : undefined,
      width: split ? undefined : '100%',
      borderRadius: 24,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.card, isDark ? 'F0' : 'FC'),
      padding: compact ? 16 : 20,
      gap: 14,
      minWidth: 0,
      ...getShadow('md', isDark),
    },
    boardHero: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'CA' : 'EE'),
      padding: 14,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
    },
    boardIconShell: {
      width: 42,
      height: 42,
      borderRadius: 14,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: withAlpha(colors.primary, '14'),
      borderWidth: 1,
      borderColor: withAlpha(colors.primary, '28'),
    },
    boardHeroLabel: {
      color: colors.textMuted,
      fontSize: 10,
      fontWeight: '800',
      textTransform: 'uppercase',
      letterSpacing: 1.1,
    },
    boardHeroValue: {
      color: colors.text,
      fontSize: 18,
      fontWeight: '900',
      letterSpacing: -0.5,
    },
    boardStatsRow: {
      flexDirection: stackedMetrics ? 'column' : 'row',
      gap: 10,
    },
    boardStatCard: {
      flex: 1,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'BF' : 'F6'),
      padding: 12,
      gap: 6,
      minWidth: 0,
    },
    boardStatLabel: {
      color: colors.textMuted,
      fontSize: 10,
      fontWeight: '800',
      textTransform: 'uppercase',
      letterSpacing: 1,
    },
    boardStatValue: {
      color: colors.text,
      fontSize: 16,
      fontWeight: '900',
    },
    trackWrap: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'B8' : 'F3'),
      padding: 12,
      gap: 10,
    },
    trackRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      minWidth: 0,
    },
    trackDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      flexShrink: 0,
    },
    trackLabel: {
      color: colors.textSec,
      fontSize: 12,
      fontWeight: '700',
      flex: 1,
      minWidth: 0,
    },
    trackState: {
      color: colors.textMuted,
      fontSize: 11,
      fontWeight: '700',
      flexShrink: 0,
    },
  });
}
