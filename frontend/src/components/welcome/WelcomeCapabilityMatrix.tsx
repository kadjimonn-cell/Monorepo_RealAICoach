import React, { useMemo } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { withAlpha } from '../../utils/colorAlpha';
import { getShadow } from '../../utils/themeShadows';
import type { CapabilityCategoryId, HydratedCapability } from './welcomeCapabilityCatalog';

type MatrixCard = HydratedCapability & {
  title: string;
  summary: string;
  badgeLabel: string;
  tierLabel: string;
  accessLabel: string;
  isAccessibleNow: boolean;
  isSelected: boolean;
};

type WelcomeCapabilityMatrixProps = {
  colors: any;
  isDark: boolean;
  isDesktop: boolean;
  isTablet: boolean;
  compact: boolean;
  denseMobile: boolean;
  roomyDesktop: boolean;
  title: string;
  subtitle: string;
  categories: { id: CapabilityCategoryId; label: string }[];
  activeCategory: CapabilityCategoryId;
  items: MatrixCard[];
  liveLabel: string;
  lockedHint: string;
  ctaLabel: string;
  onCategoryChange: (next: CapabilityCategoryId) => void;
  onFocusItem: (featureId: string) => void;
  onActionItem: (featureId: string) => void;
};

export function WelcomeCapabilityMatrix({
  colors,
  isDark,
  isDesktop,
  isTablet,
  compact,
  denseMobile,
  roomyDesktop,
  title,
  subtitle,
  categories,
  activeCategory,
  items,
  liveLabel,
  lockedHint,
  ctaLabel,
  onCategoryChange,
  onFocusItem,
  onActionItem,
}: WelcomeCapabilityMatrixProps) {
  const s = useMemo(() => makeStyles(colors, isDark, isDesktop, isTablet, compact, denseMobile, roomyDesktop), [colors, isDark, isDesktop, isTablet, compact, denseMobile, roomyDesktop]);
  const bodyFont = Platform.OS === 'web' ? { fontFamily: 'IBM Plex Sans, sans-serif' as any } : null;
  const webGridColumns = roomyDesktop
    ? 'repeat(3, minmax(0, 1fr))'
    : (isDesktop || isTablet)
      ? 'repeat(2, minmax(0, 1fr))'
      : 'minmax(0, 1fr)';
  const webGridGap = roomyDesktop ? 20 : isDesktop ? 16 : 14;

  const renderCard = (item: MatrixCard) => {
    const locked = !item.isAccessibleNow;

    return (
      <View style={[s.card, item.isSelected ? s.cardSelected : null, locked ? s.cardLocked : null]} data-testid={`welcome-capability-card-${item.featureId}`} testID={`welcome-capability-card-${item.featureId}`}>
        <TouchableOpacity
          onPress={() => onFocusItem(item.featureId)}
          style={s.cardMainAction}
          data-testid={`welcome-capability-card-focus-${item.featureId}`}
          testID={`welcome-capability-card-focus-${item.featureId}`}
        >
          <View style={s.cardHeader} data-testid={`welcome-capability-card-header-${item.featureId}`} testID={`welcome-capability-card-header-${item.featureId}`}>
            <View style={s.cardHeaderLead} data-testid={`welcome-capability-card-header-lead-${item.featureId}`} testID={`welcome-capability-card-header-lead-${item.featureId}`}>
              <View style={[s.cardIconShell, { backgroundColor: withAlpha(item.color, '14'), borderColor: withAlpha(item.color, '30') }]} data-testid={`welcome-capability-card-icon-${item.featureId}`} testID={`welcome-capability-card-icon-${item.featureId}`}>
                <Ionicons name={item.icon as any} size={18} color={item.color} />
              </View>
              <View style={s.cardHeadlineGroup}>
                <Text style={s.cardTitle} data-testid={`welcome-capability-card-title-${item.featureId}`} testID={`welcome-capability-card-title-${item.featureId}`}>{item.title}</Text>
                <Text style={[s.cardSummary, bodyFont]} data-testid={`welcome-capability-card-summary-${item.featureId}`} testID={`welcome-capability-card-summary-${item.featureId}`}>{item.summary}</Text>
              </View>
            </View>
            <View style={s.cardTopMeta} data-testid={`welcome-capability-card-meta-${item.featureId}`} testID={`welcome-capability-card-meta-${item.featureId}`}>
              <View style={[s.badgePill, { backgroundColor: withAlpha(item.color, '12'), borderColor: withAlpha(item.color, '30') }]} data-testid={`welcome-capability-card-badge-${item.featureId}`} testID={`welcome-capability-card-badge-${item.featureId}`}>
                <Text style={[s.badgePillText, { color: item.color }, bodyFont]}>{item.badgeLabel}</Text>
              </View>
              <View style={s.accessPill} data-testid={`welcome-capability-card-state-${item.featureId}`} testID={`welcome-capability-card-state-${item.featureId}`}>
                <Text style={[s.accessPillText, bodyFont]}>{item.isAccessibleNow ? liveLabel : item.tierLabel}</Text>
              </View>
            </View>
          </View>
        </TouchableOpacity>

        <View style={s.cardFooter}>
          <View style={{ gap: 4, flex: 1, minWidth: 0, alignItems: compact ? 'center' : 'flex-start' }}>
            <Text style={[s.cardTierLabel, bodyFont]}>{item.tierLabel}</Text>
            <Text style={[s.cardTierHint, bodyFont]}>{locked ? lockedHint : item.accessLabel}</Text>
          </View>
          <TouchableOpacity
            onPress={() => onActionItem(item.featureId)}
            style={[s.cardCta, locked ? s.cardCtaLocked : s.cardCtaLive]}
            data-testid={`welcome-capability-card-cta-${item.featureId}`}
            testID={`welcome-capability-card-cta-${item.featureId}`}
          >
            <Text style={[s.cardCtaText, locked ? s.cardCtaTextLocked : s.cardCtaTextLive, bodyFont]}>{item.isAccessibleNow ? ctaLabel : item.tierLabel}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <View style={s.wrap} data-testid="welcome-capability-matrix" testID="welcome-capability-matrix">
      {Platform.OS === 'web' ? (
        <style dangerouslySetInnerHTML={{ __html: `
          .welcome-capability-card {
            transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.28s ease, box-shadow 0.28s ease;
          }
          .welcome-capability-card:hover {
            transform: translateY(-5px);
            box-shadow: ${isDark ? `0 18px 48px ${withAlpha(colors.shadowColor, '80')}` : `0 22px 48px ${withAlpha(colors.shadowColor, '1A')}`};
          }
        ` }} />
      ) : null}

      <View style={s.headerRow}>
        <View style={{ flex: 1, gap: 6, minWidth: 0 }}>
          <Text style={[s.title, bodyFont]} data-testid="welcome-capability-matrix-title" testID="welcome-capability-matrix-title">{title}</Text>
          <Text style={[s.subtitle, bodyFont]} data-testid="welcome-capability-matrix-subtitle" testID="welcome-capability-matrix-subtitle">{subtitle}</Text>
        </View>
      </View>

      <View style={s.tabsRow} data-testid="welcome-capability-category-tabs" testID="welcome-capability-category-tabs">
        {categories.map((category) => {
          const active = category.id === activeCategory;
          return (
            <TouchableOpacity
              key={category.id}
              onPress={() => onCategoryChange(category.id)}
              style={[s.tab, active ? s.tabActive : null]}
              data-testid={`welcome-capability-category-tab-${category.id}`}
              testID={`welcome-capability-category-tab-${category.id}`}
            >
              <Text style={[s.tabText, active ? s.tabTextActive : null, bodyFont]}>{category.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {Platform.OS === 'web' ? (
        <div
          className="welcome-capability-grid-web"
          data-testid="welcome-capability-card-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: webGridColumns,
            gap: `${webGridGap}px`,
            width: '100%',
            alignItems: 'stretch',
          }}
        >
          {items.map((item, index) => (
            <div key={item.featureId} className="welcome-capability-card" style={{ minWidth: 0, height: '100%' }} data-testid={`welcome-capability-card-shell-${index}`}>
              {renderCard(item)}
            </div>
          ))}
        </div>
      ) : (
        <View style={s.grid} data-testid="welcome-capability-card-grid" testID="welcome-capability-card-grid">
          {items.map((item) => <React.Fragment key={item.featureId}>{renderCard(item)}</React.Fragment>)}
        </View>
      )}
    </View>
  );
}

function makeStyles(colors: any, isDark: boolean, isDesktop: boolean, isTablet: boolean, compact: boolean, denseMobile: boolean, roomyDesktop: boolean) {
  const useRoomyDesktopCards = roomyDesktop;
  return StyleSheet.create({
    wrap: {
      borderRadius: 22,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.surface, isDark ? 'F2' : 'FB'),
      padding: useRoomyDesktopCards ? 26 : compact ? 18 : 22,
      gap: useRoomyDesktopCards ? 18 : 16,
      ...getShadow('md', isDark),
    },
    headerRow: {
      flexDirection: compact ? 'column' : 'row',
      justifyContent: 'space-between',
      alignItems: compact ? 'center' : 'flex-start',
      gap: 12,
      flexWrap: 'wrap',
    },
    title: {
      color: colors.textMuted,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.6,
      textTransform: 'uppercase',
    },
    subtitle: {
      color: colors.text,
      fontSize: 18,
      lineHeight: 26,
      fontWeight: '800',
      maxWidth: 640,
      textAlign: compact ? 'center' : 'left',
    },
    tabsRow: {
      flexDirection: 'row',
      gap: 8,
      flexWrap: 'wrap',
      justifyContent: compact ? 'center' : 'flex-start',
    },
    tab: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'B4' : 'EF'),
      paddingHorizontal: 14,
      paddingVertical: 10,
    },
    tabActive: {
      borderColor: withAlpha(colors.primary, '44'),
      backgroundColor: withAlpha(colors.primary, '12'),
    },
    tabText: {
      color: colors.textSec,
      fontSize: 12,
      fontWeight: '700',
      textAlign: 'center',
    },
    tabTextActive: {
      color: colors.primary,
    },
    grid: {
      flexDirection: isDesktop || isTablet ? 'row' : 'column',
      flexWrap: 'wrap',
      gap: 14,
      width: '100%',
    },
    card: {
      width: '100%',
      maxWidth: '100%',
      minWidth: 0,
      borderRadius: 20,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.card, isDark ? 'EC' : 'FC'),
      padding: useRoomyDesktopCards ? 20 : denseMobile ? 14 : 16,
      gap: useRoomyDesktopCards ? 16 : denseMobile ? 12 : 14,
      position: 'relative',
      overflow: 'hidden',
      alignItems: compact ? 'center' : 'stretch',
      minHeight: useRoomyDesktopCards ? 278 : undefined,
      justifyContent: 'flex-start',
      height: '100%',
    },
    cardMainAction: {
      width: '100%',
      gap: useRoomyDesktopCards ? 14 : denseMobile ? 10 : 12,
      minWidth: 0,
    },
    cardSelected: {
      borderColor: withAlpha(colors.primary, '4E'),
      backgroundColor: withAlpha(colors.primary, isDark ? '0F' : '08'),
    },
    cardLocked: {
      backgroundColor: withAlpha(colors.card, isDark ? 'DA' : 'F4'),
    },
    cardHeader: {
      flexDirection: compact ? 'column' : 'row',
      alignItems: compact ? 'stretch' : 'center',
      justifyContent: 'space-between',
      gap: useRoomyDesktopCards ? 12 : denseMobile ? 10 : 12,
      width: '100%',
      minWidth: 0,
    },
    cardHeaderLead: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: useRoomyDesktopCards ? 14 : 12,
      flex: 1,
      minWidth: 0,
    },
    cardIconShell: {
      width: 42,
      height: 42,
      borderRadius: 14,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
    },
    cardHeadlineGroup: {
      gap: useRoomyDesktopCards ? 6 : 6,
      flex: 1,
      minWidth: 0,
      justifyContent: 'flex-start',
    },
    cardTopMeta: {
      flexDirection: compact ? 'row' : 'column',
      alignItems: compact ? 'center' : 'flex-end',
      gap: useRoomyDesktopCards ? 6 : denseMobile ? 6 : 8,
      flexShrink: 1,
      width: compact ? '100%' : undefined,
      justifyContent: 'flex-start',
      flexWrap: compact ? 'wrap' : 'nowrap',
      alignSelf: compact ? 'flex-start' : 'center',
      maxWidth: compact ? '100%' : undefined,
    },
    badgePill: {
      borderRadius: 999,
      borderWidth: 1,
      paddingHorizontal: useRoomyDesktopCards ? 8 : 10,
      paddingVertical: useRoomyDesktopCards ? 5 : 6,
      maxWidth: compact ? '100%' : undefined,
      alignSelf: compact ? 'center' : 'auto',
    },
    badgePillText: {
      fontSize: useRoomyDesktopCards ? 9 : 10,
      fontWeight: '800',
      letterSpacing: useRoomyDesktopCards ? 0.45 : 0.7,
      textTransform: 'uppercase',
      textAlign: 'center',
      flexShrink: 1,
    },
    accessPill: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.bgSoft, isDark ? 'C2' : 'F2'),
      paddingHorizontal: useRoomyDesktopCards ? 8 : 10,
      paddingVertical: useRoomyDesktopCards ? 5 : 6,
      alignSelf: compact ? 'center' : 'auto',
    },
    accessPillText: {
      color: colors.textSec,
      fontSize: useRoomyDesktopCards ? 9 : 10,
      fontWeight: '800',
      textTransform: 'uppercase',
      letterSpacing: useRoomyDesktopCards ? 0.45 : 0.7,
      textAlign: 'center',
    },
    cardTitle: {
      color: colors.text,
      fontSize: useRoomyDesktopCards ? 17 : denseMobile ? 17 : 18,
      fontWeight: '800',
      letterSpacing: -0.3,
      textAlign: compact ? 'center' : 'left',
    },
    cardSummary: {
      color: colors.textSec,
      fontSize: useRoomyDesktopCards ? 13 : denseMobile ? 13 : 14,
      lineHeight: useRoomyDesktopCards ? 21 : denseMobile ? 20 : 22,
      textAlign: compact ? 'center' : 'left',
    },
    cardFooter: {
      flexDirection: compact ? 'column' : 'row',
      alignItems: compact ? 'stretch' : 'flex-end',
      gap: useRoomyDesktopCards ? 12 : denseMobile ? 8 : 10,
      minWidth: 0,
      width: '100%',
      marginTop: 'auto',
    },
    cardTierLabel: {
      color: colors.text,
      fontSize: 12,
      fontWeight: '800',
      textAlign: compact ? 'center' : 'left',
    },
    cardTierHint: {
      color: colors.textMuted,
      fontSize: denseMobile ? 10 : 11,
      lineHeight: denseMobile ? 16 : 17,
      textAlign: compact ? 'center' : 'left',
    },
    cardCta: {
      borderRadius: 12,
      paddingHorizontal: useRoomyDesktopCards ? 14 : 12,
      paddingVertical: useRoomyDesktopCards ? 11 : denseMobile ? 9 : 10,
      minWidth: compact ? 110 : useRoomyDesktopCards ? 132 : 124,
      width: compact ? '100%' : undefined,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
    },
    cardCtaLive: {
      borderColor: withAlpha(colors.primary, '44'),
      backgroundColor: withAlpha(colors.primary, '12'),
    },
    cardCtaLocked: {
      borderColor: withAlpha(colors.warning, '40'),
      backgroundColor: withAlpha(colors.warning, '12'),
    },
    cardCtaText: {
      fontSize: 11,
      fontWeight: '800',
    },
    cardCtaTextLive: {
      color: colors.primary,
    },
    cardCtaTextLocked: {
      color: colors.warningText,
    },
  });
}
