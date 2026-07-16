import React, { useMemo } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import { getShadow } from '../../utils/themeShadows';
import { withAlpha } from '../../utils/colorAlpha';
import type { GLSTokens } from '../../context/GLSContext';

type SummaryBandTone = 'public' | 'syncing' | 'live' | 'degraded';

type SummarySourceItem = {
  id: string;
  label: string;
  onPress: () => void;
};

type SummarySignalItem = {
  emphasis?: boolean;
  id: string;
  label: string;
  value: string;
  tone: 'primary' | 'success' | 'warning' | 'accent';
};

type SummaryInterestMemory = {
  actionLabel: string;
  copy: string;
  onPress: () => void;
  title: string;
};

type SummaryMention = {
  source: string;
  title: string;
  onPress: () => void;
};

interface WelcomeHeroSummaryBandProps {
  lastRefreshLabel: string;
  onOpenNewsroom: () => void;
  rememberedInterest: SummaryInterestMemory | null;
  signalItems: SummarySignalItem[];
  sourceItems: SummarySourceItem[];
  statusLabel: string;
  statusTone: SummaryBandTone;
  topMention: SummaryMention | null;
}

const blurCard = Platform.OS === 'web'
  ? { backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' } as any
  : {};

export function WelcomeHeroSummaryBand({
  lastRefreshLabel,
  onOpenNewsroom,
  rememberedInterest,
  signalItems,
  sourceItems,
  statusLabel,
  statusTone,
  topMention,
}: WelcomeHeroSummaryBandProps) {
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const useWideSummaryLayout = width >= 1180;
  const shouldCenterBandContent = !useWideSummaryLayout;
  const useStackedHeaderLayout = !useWideSummaryLayout;
  const useCompactSignalStack = width < 640;
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const toneColor = useMemo(() => {
    if (statusTone === 'live') return WC.success;
    if (statusTone === 'degraded') return WC.warning;
    return WC.primary;
  }, [WC.primary, WC.success, WC.warning, statusTone]);

  const styles = useMemo(
    () => makeStyles(WC, isDark, padding, tokens, isDesktop, useStackedHeaderLayout, shouldCenterBandContent, useCompactSignalStack),
    [WC, isDark, padding, tokens, isDesktop, shouldCenterBandContent, useCompactSignalStack, useStackedHeaderLayout],
  );

  return (
    <View style={styles.wrap} data-testid="welcome-hero-summary-band" testID="welcome-hero-summary-band">
      <View style={styles.statusCard} data-testid="welcome-hero-summary-status-card" testID="welcome-hero-summary-status-card">
        <View style={[styles.cardHeaderRow, shouldCenterBandContent && styles.cardHeaderRowCentered]}>
          <View style={[styles.cardHeaderCopy, shouldCenterBandContent && styles.cardHeaderCopyCentered]}>
            <Text style={[styles.overline, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-overline" testID="welcome-hero-summary-overline">
              {tx('welcome.hero.summary.overline', 'Executive welcome summary')}
            </Text>
            <Text style={[styles.title, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-title" testID="welcome-hero-summary-title">
              {tx('welcome.hero.summary.title', 'Everything above the fold now behaves like a serious enterprise entry point.')}
            </Text>
          </View>

          <View
            style={[
              styles.statusPill,
              shouldCenterBandContent && styles.statusPillCentered,
              {
                borderColor: withAlpha(toneColor, '36'),
                backgroundColor: withAlpha(toneColor, isDark ? '1A' : '12'),
              },
            ]}
            data-testid="welcome-hero-summary-status-pill"
            testID="welcome-hero-summary-status-pill"
          >
            <View style={[styles.statusDot, { backgroundColor: toneColor }]} />
            <Text style={[styles.statusPillText, { color: toneColor }]}>{statusLabel}</Text>
          </View>
        </View>

        <Text style={[styles.description, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-description" testID="welcome-hero-summary-description">
          {tx('welcome.hero.summary.description', 'Responsive hierarchy, plan-aware routing, and buyer trust signals now align before a visitor even reaches pricing.')}
        </Text>

        {rememberedInterest ? (
          <View style={[styles.memoryCard, shouldCenterBandContent && styles.memoryCardCentered]} data-testid="welcome-hero-summary-memory-card" testID="welcome-hero-summary-memory-card">
            <Text style={[styles.memoryLabel, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-memory-label" testID="welcome-hero-summary-memory-label">
              {tx('welcome.hero.summary.memory.label', 'Returning interest')}
            </Text>
            <Text style={[styles.memoryTitle, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-memory-title" testID="welcome-hero-summary-memory-title">
              {rememberedInterest.title}
            </Text>
            <Text style={[styles.memoryCopy, shouldCenterBandContent && styles.textCentered]} data-testid="welcome-hero-summary-memory-copy" testID="welcome-hero-summary-memory-copy">
              {rememberedInterest.copy}
            </Text>
            <TouchableOpacity
              onPress={rememberedInterest.onPress}
              style={[styles.memoryButton, shouldCenterBandContent && styles.centeredSelf]}
              data-testid="welcome-hero-summary-memory-action"
              testID="welcome-hero-summary-memory-action"
            >
              <Text style={styles.memoryButtonText}>{rememberedInterest.actionLabel}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={[styles.statusMetaRow, shouldCenterBandContent && styles.statusMetaRowCentered]} data-testid="welcome-hero-summary-meta" testID="welcome-hero-summary-meta">
          <Text style={[styles.statusMetaLabel, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.systemLabel', 'System posture')}</Text>
          <Text style={[styles.statusMetaValue, shouldCenterBandContent && styles.textCentered]}>{lastRefreshLabel}</Text>
        </View>

        {topMention ? (
          <TouchableOpacity
            onPress={topMention.onPress}
            style={[styles.mentionCard, shouldCenterBandContent && styles.mentionCardCentered]}
            data-testid="welcome-hero-summary-mention-button"
            testID="welcome-hero-summary-mention-button"
          >
            <View style={[styles.mentionHeader, shouldCenterBandContent && styles.mentionHeaderCentered]}>
              <Text style={[styles.mentionLabel, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.mentionLabel', 'Live newsroom signal')}</Text>
              <Ionicons name="arrow-forward" size={14} color={WC.primary} />
            </View>
            <Text style={[styles.mentionSource, shouldCenterBandContent && styles.textCentered]}>{topMention.source}</Text>
            <Text style={[styles.mentionTitle, shouldCenterBandContent && styles.textCentered]} numberOfLines={3}>{topMention.title}</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      <View style={styles.sourcesCard} data-testid="welcome-hero-summary-sources-card" testID="welcome-hero-summary-sources-card">
        <View style={[styles.cardHeaderRow, shouldCenterBandContent && styles.cardHeaderRowCentered]}>
          <View style={[styles.cardHeaderCopy, shouldCenterBandContent && styles.cardHeaderCopyCentered]}>
            <Text style={[styles.cardTitle, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.sourcesTitle', 'Trust + visibility signals')}</Text>
            <Text style={[styles.cardCopy, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.sourcesCopy', 'Recognizable sources help the opening experience feel credible before the deeper product story unfolds.')}</Text>
          </View>
          <TouchableOpacity
            onPress={onOpenNewsroom}
            style={[styles.newsroomButton, shouldCenterBandContent && styles.centeredSelf]}
            data-testid="welcome-hero-summary-newsroom-button"
            testID="welcome-hero-summary-newsroom-button"
          >
            <Text style={styles.newsroomButtonText}>{tx('welcome.hero.summary.newsroomButton', 'View newsroom')}</Text>
          </TouchableOpacity>
        </View>

        <View style={[styles.sourceGrid, shouldCenterBandContent && styles.sourceGridCentered]} data-testid="welcome-hero-summary-sources-grid" testID="welcome-hero-summary-sources-grid">
          {sourceItems.map((item, idx) => (
            <TouchableOpacity
              key={item.id}
              onPress={item.onPress}
              style={styles.sourceChip}
              data-testid={`welcome-hero-summary-source-${idx}`}
              testID={`welcome-hero-summary-source-${idx}`}
            >
              <Text style={styles.sourceChipText}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.signalCard} data-testid="welcome-hero-summary-signals-card" testID="welcome-hero-summary-signals-card">
        <Text style={[styles.cardTitle, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.signalsTitle', 'Top-of-page operating signals')}</Text>
        <Text style={[styles.cardCopy, shouldCenterBandContent && styles.textCentered, { marginBottom: 2 }]}>{tx('welcome.hero.summary.signalsCopy', 'A concise snapshot of the product depth, commercial structure, and proof density a buyer sees immediately.')}</Text>

        <View style={[styles.signalGrid, shouldCenterBandContent && styles.signalGridCentered]} data-testid="welcome-hero-summary-signals-grid" testID="welcome-hero-summary-signals-grid">
          {signalItems.map((item) => {
            const valueColor = item.tone === 'success'
              ? WC.successText
              : item.tone === 'warning'
                ? WC.warningText
                : item.tone === 'accent'
                  ? WC.accentText
                  : WC.primary;

            return (
              <View
                key={item.id}
                style={[
                  styles.signalItem,
                  shouldCenterBandContent && styles.signalItemCentered,
                  item.emphasis ? styles.signalItemActive : null,
                ]}
                data-testid={`welcome-hero-summary-signal-${item.id}`}
                testID={`welcome-hero-summary-signal-${item.id}`}
              >
                {item.emphasis ? (
                  <Text style={[styles.signalFocusTag, shouldCenterBandContent && styles.textCentered]}>{tx('welcome.hero.summary.memory.signalFocus', 'Remembered interest')}</Text>
                ) : null}
                <Text style={[styles.signalLabel, shouldCenterBandContent && styles.textCentered]}>{item.label}</Text>
                <Text style={[styles.signalValue, shouldCenterBandContent && styles.textCentered, { color: valueColor }]}>{item.value}</Text>
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}

function makeStyles(
  WC: any,
  isDark: boolean,
  horizontalPadding: number,
  tokens: GLSTokens,
  isDesktop: boolean,
  useStackedHeaderLayout: boolean,
  shouldCenterBandContent: boolean,
  useCompactSignalStack: boolean,
) {
  return StyleSheet.create({
    wrap: {
      width: '100%',
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      gap: 14,
      paddingHorizontal: isDesktop ? 10 : horizontalPadding,
      paddingTop: isDesktop ? 22 : 8,
      paddingBottom: isDesktop ? 18 : 10,
      ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}),
    },
    statusCard: {
      borderRadius: 24,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.card, isDark ? 'E8' : 'FB'),
      padding: shouldCenterBandContent ? 18 : 22,
      gap: 14,
      ...blurCard,
      ...getShadow('md', isDark),
    },
    sourcesCard: {
      borderRadius: 22,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.surface, isDark ? 'E4' : 'F8'),
      padding: useCompactSignalStack ? 16 : 20,
      gap: 14,
      ...blurCard,
      ...getShadow('sm', isDark),
    },
    signalCard: {
      borderRadius: 22,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.bgSoft, isDark ? 'D4' : 'F7'),
      padding: useCompactSignalStack ? 16 : 20,
      gap: 12,
      ...blurCard,
      ...getShadow('sm', isDark),
    },
    cardHeaderRow: {
      flexDirection: useStackedHeaderLayout ? 'column' : 'row',
      justifyContent: 'space-between',
      alignItems: useStackedHeaderLayout ? 'center' : 'flex-start',
      gap: 12,
    },
    cardHeaderRowCentered: {
      alignItems: 'center',
    },
    cardHeaderCopy: {
      flex: 1,
      minWidth: 0,
      gap: 6,
    },
    cardHeaderCopyCentered: {
      alignItems: 'center',
    },
    overline: {
      color: WC.textMuted,
      fontSize: 10,
      fontWeight: '800',
      letterSpacing: 1.6,
      textTransform: 'uppercase',
    },
    title: {
      color: WC.text,
      fontSize: isDesktop ? 28 : 24,
      lineHeight: isDesktop ? 34 : 30,
      fontWeight: '900',
      letterSpacing: -0.8,
    },
    textCentered: {
      textAlign: 'center',
    },
    description: {
      color: WC.textSec,
      fontSize: 14,
      lineHeight: 22,
    },
    memoryCard: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: withAlpha(WC.primary, '34'),
      backgroundColor: withAlpha(WC.primary, isDark ? '18' : '10'),
      padding: 14,
      gap: 8,
    },
    memoryCardCentered: {
      alignItems: 'center',
    },
    memoryLabel: {
      color: WC.primary,
      fontSize: 10,
      fontWeight: '800',
      letterSpacing: 0.9,
      textTransform: 'uppercase',
    },
    memoryTitle: {
      color: WC.text,
      fontSize: 14,
      lineHeight: 20,
      fontWeight: '900',
    },
    memoryCopy: {
      color: WC.textSec,
      fontSize: 12,
      lineHeight: 19,
    },
    memoryButton: {
      alignSelf: 'flex-start',
      borderRadius: 999,
      borderWidth: 1,
      borderColor: withAlpha(WC.primary, '36'),
      backgroundColor: withAlpha(WC.bg, isDark ? '8E' : 'EE'),
      paddingHorizontal: 12,
      paddingVertical: 8,
    },
    memoryButtonText: {
      color: WC.text,
      fontSize: 11,
      fontWeight: '800',
    },
    statusPill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 7,
      borderRadius: 999,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 8,
      alignSelf: shouldCenterBandContent ? 'center' : 'center',
    },
    statusPillCentered: {
      alignSelf: 'center',
    },
    statusDot: {
      width: 8,
      height: 8,
      borderRadius: 999,
    },
    statusPillText: {
      fontSize: 10,
      fontWeight: '900',
      letterSpacing: 0.8,
      textTransform: 'uppercase',
    },
    statusMetaRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 10,
      flexWrap: 'wrap',
      borderTopWidth: 1,
      borderTopColor: WC.border,
      paddingTop: 12,
    },
    statusMetaRowCentered: {
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
    },
    statusMetaLabel: {
      color: WC.textMuted,
      fontSize: 11,
      fontWeight: '700',
    },
    statusMetaValue: {
      color: WC.text,
      fontSize: 11,
      fontWeight: '800',
    },
    mentionCard: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.bgSoft, isDark ? 'BE' : 'F2'),
      padding: 14,
      gap: 6,
    },
    mentionCardCentered: {
      alignItems: 'center',
    },
    mentionHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
    },
    mentionHeaderCentered: {
      width: '100%',
      flexDirection: 'column',
      justifyContent: 'center',
    },
    mentionLabel: {
      color: WC.primary,
      fontSize: 10,
      fontWeight: '800',
      textTransform: 'uppercase',
      letterSpacing: 0.9,
    },
    mentionSource: {
      color: WC.textMuted,
      fontSize: 11,
      fontWeight: '700',
    },
    mentionTitle: {
      color: WC.text,
      fontSize: 13,
      lineHeight: 20,
      fontWeight: '800',
    },
    cardTitle: {
      color: WC.text,
      fontSize: 15,
      lineHeight: 21,
      fontWeight: '900',
    },
    cardCopy: {
      color: WC.textMuted,
      fontSize: 12,
      lineHeight: 19,
    },
    newsroomButton: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.bg, isDark ? '82' : 'E8'),
      paddingHorizontal: 12,
      paddingVertical: 8,
      alignSelf: shouldCenterBandContent ? 'center' : 'center',
    },
    centeredSelf: {
      alignSelf: 'center',
    },
    newsroomButtonText: {
      color: WC.text,
      fontSize: 11,
      fontWeight: '800',
    },
    sourceGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    sourceGridCentered: {
      justifyContent: 'center',
    },
    sourceChip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.bgSoft, isDark ? 'B6' : 'EE'),
      paddingHorizontal: 12,
      paddingVertical: 8,
      flexGrow: useCompactSignalStack ? 1 : 0,
      flexBasis: useCompactSignalStack ? '48%' as any : undefined,
      minWidth: 0,
      alignItems: 'center',
      justifyContent: 'center',
    },
    sourceChipText: {
      color: WC.textSec,
      fontSize: 11,
      fontWeight: '800',
      textAlign: 'center',
    },
    signalGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
    },
    signalGridCentered: {
      justifyContent: 'center',
    },
    signalItem: {
      borderRadius: 16,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.surface, isDark ? 'D0' : 'FC'),
      padding: 14,
      gap: 6,
      flexGrow: 1,
      flexBasis: useCompactSignalStack ? '100%' as any : '48%' as any,
      minWidth: 0,
    },
    signalItemCentered: {
      alignItems: 'center',
    },
    signalItemActive: {
      borderColor: withAlpha(WC.primary, '38'),
      backgroundColor: withAlpha(WC.primary, isDark ? '16' : '0D'),
    },
    signalFocusTag: {
      color: WC.primary,
      fontSize: 9,
      fontWeight: '800',
      letterSpacing: 0.7,
      textTransform: 'uppercase',
    },
    signalLabel: {
      color: WC.textMuted,
      fontSize: 10,
      fontWeight: '700',
      textTransform: 'uppercase',
      letterSpacing: 0.8,
    },
    signalValue: {
      fontSize: 17,
      lineHeight: 22,
      fontWeight: '900',
      letterSpacing: -0.4,
    },
  });
}