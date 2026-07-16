import React, { useEffect, useRef, useState } from 'react';
import { View, Animated, StyleSheet, useWindowDimensions } from 'react-native';
import { useTheme } from '@/src/context/ThemeContext';
import { PERFORMANCE_STANDARDS } from '@/src/config/performanceStandards';
import { resolveRuntimeBaseUrl } from '@/src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

// Skeleton shimmer fill — a fixed deep slate that works across themes and
// avoids flashing when the real surface paints. Theme-exempt by design.
const SKELETON_SHIMMER_BG = 'var(--app-primary)';

function ShimmerBar({ width = '100%', height = 14, radius = 8, delay = 0 }: { width?: string | number; height?: number; radius?: number; delay?: number }) {
  const { _colors } = useTheme();
  const anim = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(anim, { toValue: 0.7, duration: 800, delay, useNativeDriver: false }),
        Animated.timing(anim, { toValue: 0.3, duration: 800, useNativeDriver: false }),
      ])
    );
    loop.start();
    return () => loop.stop();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View
      style={{
        width: width as any,
        height,
        borderRadius: radius,
        backgroundColor: SKELETON_SHIMMER_BG,
        opacity: anim,
      }}
    />
  );
}

export function HomeSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-home" testID="skeleton-home">
      {/* Hero skeleton */}
      <View style={[sk.section, { paddingTop: 28 }]}>
        <ShimmerBar width="40%" height={12} delay={0} />
        <View style={{ height: 10 }} />
        <ShimmerBar width="80%" height={28} delay={50} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="60%" height={28} delay={100} />
        <View style={{ height: 16 }} />
        <ShimmerBar width="90%" height={14} delay={150} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="70%" height={14} delay={200} />
      </View>
      {/* Stats skeleton */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="50%" height={22} delay={i * 80} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="70%" height={10} delay={i * 80 + 40} />
          </View>
        ))}
      </View>
      {/* Chart skeleton */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ShimmerBar width="30%" height={14} />
        <View style={{ height: 16 }} />
        <View style={sk.chartBars}>
          {[60, 80, 45, 95, 70, 55, 85].map((h, i) => (
            <View key={i} style={sk.chartBarCol}>
              <ShimmerBar width="100%" height={h} radius={4} delay={i * 60} />
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

export function GallerySkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const isTablet = width >= 768 && width < 1024;
  const cols = isDesktop ? 4 : isTablet ? 3 : width >= 600 ? 2 : 1;

  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-gallery" testID="skeleton-gallery">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="50%" height={24} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="70%" height={12} />
      </View>
      {/* KPI row */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={28} height={28} radius={10} delay={i * 80} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="60%" height={18} delay={i * 80 + 40} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="50%" height={10} delay={i * 80 + 80} />
          </View>
        ))}
      </View>
      {/* Search */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={46} radius={14} />
        <View style={{ height: 12 }} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[80, 100, 70, 90, 60].map((w, i) => (
            <ShimmerBar key={i} width={w} height={34} radius={10} delay={i * 50} />
          ))}
        </View>
      </View>
      {/* Cards grid */}
      <View style={[sk.grid, isDesktop && sk.gridDesktop]}>
        {Array.from({ length: cols * 2 }).map((_, i) => (
          <View key={i} style={[sk.galleryCard, { backgroundColor: colors.card, borderColor: colors.border }, isDesktop && { width: '23.5%' }]}>
            <ShimmerBar width={46} height={46} radius={14} delay={i * 60} />
            <View style={{ height: 14 }} />
            <ShimmerBar width="70%" height={16} delay={i * 60 + 30} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="50%" height={10} delay={i * 60 + 60} />
            <View style={{ height: 10 }} />
            <ShimmerBar width="100%" height={12} delay={i * 60 + 90} />
            <ShimmerBar width="85%" height={12} delay={i * 60 + 120} />
            <View style={{ height: 14 }} />
            <ShimmerBar width="100%" height={28} radius={4} delay={i * 60 + 150} />
            <View style={{ height: 12 }} />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <ShimmerBar width="30%" height={14} delay={i * 60 + 180} />
              <ShimmerBar width="30%" height={14} delay={i * 60 + 200} />
              <ShimmerBar width="30%" height={14} delay={i * 60 + 220} />
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

export function ModalSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.modalInner, { backgroundColor: colors.bg }]} data-testid="skeleton-modal" testID="skeleton-modal">
      <View style={{ flexDirection: 'row', gap: 14, padding: 20 }}>
        <ShimmerBar width={48} height={48} radius={14} />
        <View style={{ flex: 1, gap: 6 }}>
          <ShimmerBar width="60%" height={18} />
          <ShimmerBar width="40%" height={12} />
        </View>
      </View>
      <View style={{ padding: 20, gap: 12 }}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {[0, 1, 2, 3, 4, 5].map(i => (
            <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border, width: '31%' }]}>
              <ShimmerBar width={16} height={16} radius={4} delay={i * 60} />
              <View style={{ height: 4 }} />
              <ShimmerBar width="60%" height={18} delay={i * 60 + 30} />
              <View style={{ height: 2 }} />
              <ShimmerBar width="50%" height={10} delay={i * 60 + 60} />
            </View>
          ))}
        </View>
        <ShimmerBar width="100%" height={120} radius={16} delay={200} />
      </View>
    </View>
  );
}

export function AgendaSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-agenda" testID="skeleton-agenda">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <View style={{ gap: 6 }}>
          <ShimmerBar width="50%" height={22} />
          <ShimmerBar width="35%" height={11} delay={60} />
        </View>
        <ShimmerBar width={120} height={38} radius={10} delay={100} />
      </View>
      {/* Stats row */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={20} height={20} radius={6} delay={i * 60} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="60%" height={22} delay={i * 60 + 30} />
            <ShimmerBar width="80%" height={10} delay={i * 60 + 60} />
          </View>
        ))}
      </View>
      {/* Calendar + Sidebar */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 16 }}>
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 2 }]}>
          {/* Calendar header */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
            <ShimmerBar width={30} height={30} radius={8} />
            <ShimmerBar width="30%" height={18} delay={50} />
            <ShimmerBar width={30} height={30} radius={8} delay={100} />
          </View>
          {/* Day labels */}
          <View style={{ flexDirection: 'row', gap: 4, marginBottom: 8 }}>
            {[0, 1, 2, 3, 4, 5, 6].map(i => (
              <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                <ShimmerBar width="80%" height={12} delay={i * 30} />
              </View>
            ))}
          </View>
          {/* Calendar grid */}
          {[0, 1, 2, 3, 4].map(row => (
            <View key={row} style={{ flexDirection: 'row', gap: 4, marginBottom: 4 }}>
              {[0, 1, 2, 3, 4, 5, 6].map(col => (
                <View key={col} style={{ flex: 1, aspectRatio: 1.2, justifyContent: 'center', alignItems: 'center' }}>
                  <ShimmerBar width="60%" height={14} delay={(row * 7 + col) * 15} />
                </View>
              ))}
            </View>
          ))}
        </View>
        {/* Sidebar */}
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 1 }]}>
          <ShimmerBar width="50%" height={14} />
          <View style={{ height: 14 }} />
          {[0, 1, 2, 3].map(i => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }}>
              <ShimmerBar width={8} height={40} radius={4} delay={i * 80} />
              <View style={{ flex: 1, gap: 4 }}>
                <ShimmerBar width="70%" height={14} delay={i * 80 + 30} />
                <ShimmerBar width="50%" height={10} delay={i * 80 + 60} />
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

export function AnalyticsSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-analytics" testID="skeleton-analytics">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="40%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="55%" height={12} delay={50} />
      </View>
      {/* Stats row */}
      <View style={sk.row}>
        {[0, 1, 2, 3, 4].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={22} height={22} radius={6} delay={i * 50} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="50%" height={24} delay={i * 50 + 25} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 50} />
          </View>
        ))}
      </View>
      {/* Chart */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ShimmerBar width="30%" height={14} />
        <View style={{ height: 16 }} />
        <ShimmerBar width="100%" height={160} radius={12} delay={100} />
      </View>
      {/* Recommendations */}
      <View style={sk.section}>
        <ShimmerBar width="35%" height={14} />
        <View style={{ height: 12 }} />
        {[0, 1, 2].map(i => (
          <View key={i} style={{ flexDirection: 'row', gap: 12, backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10 }}>
            <ShimmerBar width={40} height={40} radius={10} delay={i * 80} />
            <View style={{ flex: 1, gap: 6 }}>
              <ShimmerBar width="60%" height={14} delay={i * 80 + 30} />
              <ShimmerBar width="85%" height={10} delay={i * 80 + 60} />
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

export function LeaderboardSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-leaderboard" testID="skeleton-leaderboard">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="35%" height={22} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[0, 1, 2].map(i => <ShimmerBar key={i} width={70} height={32} radius={8} delay={i * 50} />)}
        </View>
      </View>
      {/* Rank Hero */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flexDirection: 'row', gap: 20, alignItems: 'center' }]}>
        <ShimmerBar width={90} height={90} radius={45} />
        <View style={{ flex: 1, gap: 8 }}>
          <ShimmerBar width="50%" height={18} delay={60} />
          <ShimmerBar width="70%" height={12} delay={90} />
          <ShimmerBar width="100%" height={8} radius={4} delay={120} />
        </View>
      </View>
      {/* Table */}
      {[0, 1, 2, 3, 4, 5, 6].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <ShimmerBar width={28} height={14} delay={i * 40} />
          <ShimmerBar width={36} height={36} radius={18} delay={i * 40 + 20} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="50%" height={14} delay={i * 40 + 40} />
            <ShimmerBar width="30%" height={10} delay={i * 40 + 60} />
          </View>
          <ShimmerBar width={50} height={14} delay={i * 40 + 80} />
        </View>
      ))}
    </View>
  );
}

export function NotificationsSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-notifications" testID="skeleton-notifications">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="40%" height={22} />
        <ShimmerBar width={100} height={32} radius={8} delay={50} />
      </View>
      {/* Filter tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
        {[0, 1, 2, 3].map(i => <ShimmerBar key={i} width={80} height={34} radius={10} delay={i * 40} />)}
      </View>
      {/* Notification items */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10 }}>
          <ShimmerBar width={40} height={40} radius={12} delay={i * 50} />
          <View style={{ flex: 1, gap: 6 }}>
            <ShimmerBar width="65%" height={14} delay={i * 50 + 20} />
            <ShimmerBar width="90%" height={11} delay={i * 50 + 40} />
            <ShimmerBar width="30%" height={10} delay={i * 50 + 60} />
          </View>
        </View>
      ))}
    </View>
  );
}

export function ReferralsSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-referrals" testID="skeleton-referrals">
      {/* Hero */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, alignItems: 'center', paddingVertical: 28 }]}>
        <ShimmerBar width="50%" height={22} />
        <View style={{ height: 12 }} />
        <ShimmerBar width="80%" height={40} radius={10} delay={60} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="40%" height={12} delay={100} />
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="40%" height={22} delay={i * 60} />
            <ShimmerBar width="60%" height={10} delay={i * 60 + 30} />
          </View>
        ))}
      </View>
      {/* Tiers */}
      <View style={sk.section}>
        <ShimmerBar width="30%" height={14} />
        <View style={{ height: 12 }} />
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          {[0, 1, 2, 3].map(i => (
            <View key={i} style={{ flex: 1, minWidth: 140, backgroundColor: colors.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.border }}>
              <ShimmerBar width={28} height={28} radius={14} delay={i * 60} />
              <View style={{ height: 8 }} />
              <ShimmerBar width="60%" height={16} delay={i * 60 + 30} />
              <ShimmerBar width="80%" height={10} delay={i * 60 + 60} />
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

export function ProgressSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-progress" testID="skeleton-progress">
      {/* Level Ring */}
      <View style={{ alignItems: 'center', marginBottom: 20, paddingVertical: 20 }}>
        <ShimmerBar width={100} height={100} radius={50} />
        <View style={{ height: 10 }} />
        <ShimmerBar width="30%" height={14} delay={80} />
        <View style={{ height: 4 }} />
        <ShimmerBar width="20%" height={12} delay={120} />
      </View>
      {/* Stats Row */}
      <View style={sk.row}>
        {[0, 1, 2, 3, 4].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={18} height={18} radius={6} delay={i * 50} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="50%" height={20} delay={i * 50 + 25} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 50} />
          </View>
        ))}
      </View>
      {/* Chart */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ShimmerBar width="35%" height={14} />
        <View style={{ height: 14 }} />
        <View style={sk.chartBars}>
          {[50, 70, 40, 85, 60, 45, 75].map((h, i) => (
            <View key={i} style={sk.chartBarCol}>
              <ShimmerBar width="100%" height={h} radius={4} delay={i * 50} />
            </View>
          ))}
        </View>
      </View>
      {/* Session history */}
      {[0, 1, 2].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10 }}>
          <ShimmerBar width={44} height={44} radius={12} delay={i * 70} />
          <View style={{ flex: 1, gap: 6 }}>
            <ShimmerBar width="55%" height={14} delay={i * 70 + 30} />
            <ShimmerBar width="80%" height={10} delay={i * 70 + 60} />
          </View>
        </View>
      ))}
    </View>
  );
}

export function LibrarySkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const cols = width >= 1024 ? 3 : width >= 768 ? 2 : 1;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-library" testID="skeleton-library">
      {/* Search */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={44} radius={12} />
        <View style={{ height: 12 }} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[90, 80, 100, 70, 85].map((w, i) => (
            <ShimmerBar key={i} width={w} height={32} radius={10} delay={i * 40} />
          ))}
        </View>
      </View>
      {/* Grid */}
      <View style={[sk.grid, width >= 768 && sk.gridDesktop]}>
        {Array.from({ length: cols * 2 }).map((_, i) => (
          <View key={i} style={[sk.galleryCard, { backgroundColor: colors.card, borderColor: colors.border, minWidth: 250 }]}>
            <ShimmerBar width="100%" height={120} radius={10} delay={i * 50} />
            <View style={{ height: 12 }} />
            <ShimmerBar width="70%" height={16} delay={i * 50 + 25} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="50%" height={11} delay={i * 50 + 50} />
            <View style={{ height: 10 }} />
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <ShimmerBar width={60} height={20} radius={6} delay={i * 50 + 75} />
              <ShimmerBar width={50} height={20} radius={6} delay={i * 50 + 100} />
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Executive / Admin Dashboard Skeleton ─── */
export function ExecutiveDashboardSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-exec-dashboard" testID="skeleton-exec-dashboard">
      {/* Header bar */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <View style={{ gap: 6 }}>
          <ShimmerBar width="45%" height={24} />
          <ShimmerBar width="65%" height={12} delay={40} />
        </View>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <ShimmerBar width={100} height={36} radius={10} delay={80} />
          <ShimmerBar width={36} height={36} radius={10} delay={100} />
        </View>
      </View>
      {/* KPI cards */}
      <View style={sk.row}>
        {[0, 1, 2, 3, 4].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={22} height={22} radius={8} delay={i * 50} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="55%" height={26} delay={i * 50 + 20} />
            <ShimmerBar width="75%" height={10} delay={i * 50 + 40} />
          </View>
        ))}
      </View>
      {/* Two-column: chart + sidebar */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 2 }]}>
          <ShimmerBar width="30%" height={16} />
          <View style={{ height: 14 }} />
          <ShimmerBar width="100%" height={180} radius={12} delay={100} />
        </View>
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 1 }]}>
          <ShimmerBar width="40%" height={14} />
          <View style={{ height: 14 }} />
          {[0, 1, 2, 3].map(i => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }}>
              <ShimmerBar width={10} height={10} radius={5} delay={i * 60} />
              <View style={{ flex: 1, gap: 4 }}>
                <ShimmerBar width="65%" height={12} delay={i * 60 + 20} />
                <ShimmerBar width="40%" height={10} delay={i * 60 + 40} />
              </View>
            </View>
          ))}
        </View>
      </View>
      {/* Table */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ShimmerBar width="25%" height={14} />
        <View style={{ height: 14 }} />
        {[0, 1, 2, 3, 4].map(i => (
          <View key={i} style={{ flexDirection: 'row', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <ShimmerBar width="20%" height={12} delay={i * 30} />
            <ShimmerBar width="30%" height={12} delay={i * 30 + 15} />
            <ShimmerBar width="25%" height={12} delay={i * 30 + 30} />
            <ShimmerBar width="15%" height={12} delay={i * 30 + 45} />
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Table / List Skeleton (Activity Log, Session History, Payments, Scans) ─── */
export function TableListSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-table-list" testID="skeleton-table-list">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="35%" height={22} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <ShimmerBar width={120} height={38} radius={10} />
          <ShimmerBar width={38} height={38} radius={10} delay={40} />
        </View>
      </View>
      {/* Filter/Search bar */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={42} radius={12} />
        <View style={{ height: 10 }} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[80, 90, 70, 100].map((w, i) => (
            <ShimmerBar key={i} width={w} height={30} radius={8} delay={i * 40} />
          ))}
        </View>
      </View>
      {/* Table rows */}
      {[0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 14, alignItems: 'center', paddingVertical: 12, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: i % 2 === 0 ? colors.card : 'transparent', borderRadius: i === 0 ? 12 : 0 }}>
          <ShimmerBar width={32} height={32} radius={10} delay={i * 30} />
          <View style={{ flex: 2, gap: 4 }}>
            <ShimmerBar width="70%" height={13} delay={i * 30 + 10} />
            <ShimmerBar width="45%" height={10} delay={i * 30 + 20} />
          </View>
          <ShimmerBar width="20%" height={12} delay={i * 30 + 30} />
          <ShimmerBar width={60} height={24} radius={6} delay={i * 30 + 40} />
        </View>
      ))}
    </View>
  );
}

/* ─── Tickets / Support Skeleton ─── */
export function TicketsSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-tickets" testID="skeleton-tickets">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="30%" height={22} />
        <ShimmerBar width={140} height={38} radius={10} delay={50} />
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="50%" height={24} delay={i * 50} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 25} />
          </View>
        ))}
      </View>
      {/* Search + filters */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={42} radius={12} />
      </View>
      {/* Ticket cards */}
      {[0, 1, 2, 3, 4].map(i => (
        <View key={i} style={{ backgroundColor: colors.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 12, gap: 10 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <ShimmerBar width="55%" height={16} delay={i * 60} />
            <ShimmerBar width={70} height={22} radius={6} delay={i * 60 + 20} />
          </View>
          <ShimmerBar width="85%" height={11} delay={i * 60 + 40} />
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 4 }}>
            <ShimmerBar width={80} height={10} delay={i * 60 + 60} />
            <ShimmerBar width={60} height={10} delay={i * 60 + 80} />
          </View>
        </View>
      ))}
    </View>
  );
}

/* ─── Chat / Messages Skeleton ─── */
export function ChatSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-chat" testID="skeleton-chat">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', gap: 12, alignItems: 'center' }]}>
        <ShimmerBar width={42} height={42} radius={21} />
        <View style={{ flex: 1, gap: 4 }}>
          <ShimmerBar width="40%" height={16} />
          <ShimmerBar width="25%" height={10} delay={30} />
        </View>
      </View>
      {/* Message bubbles */}
      {[
        { align: 'flex-start', w1: '65%', w2: '45%' },
        { align: 'flex-end', w1: '55%', w2: '35%' },
        { align: 'flex-start', w1: '70%', w2: '50%' },
        { align: 'flex-end', w1: '60%', w2: '40%' },
        { align: 'flex-start', w1: '75%', w2: '55%' },
        { align: 'flex-end', w1: '50%', w2: '30%' },
      ].map((m, i) => (
        <View key={i} style={{ alignSelf: m.align as any, maxWidth: '75%', backgroundColor: colors.card, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10, gap: 6 }}>
          <ShimmerBar width={m.w1} height={12} delay={i * 60} />
          <ShimmerBar width={m.w2} height={12} delay={i * 60 + 25} />
          <ShimmerBar width={50} height={9} delay={i * 60 + 50} />
        </View>
      ))}
      {/* Input bar */}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 'auto', paddingTop: 14 }}>
        <ShimmerBar width="85%" height={44} radius={22} delay={200} />
        <ShimmerBar width={44} height={44} radius={22} delay={240} />
      </View>
    </View>
  );
}

/* ─── Security / Settings Skeleton ─── */
export function SecuritySettingsSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-security" testID="skeleton-security">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="35%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="55%" height={12} delay={40} />
      </View>
      {/* Security score */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, alignItems: 'center', paddingVertical: 24 }]}>
        <ShimmerBar width={80} height={80} radius={40} />
        <View style={{ height: 10 }} />
        <ShimmerBar width="30%" height={16} delay={80} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="50%" height={10} delay={120} />
      </View>
      {/* Settings sections */}
      {[0, 1, 2, 3, 4].map(i => (
        <View key={i} style={{ backgroundColor: colors.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 12, flexDirection: 'row', gap: 14, alignItems: 'center' }}>
          <ShimmerBar width={40} height={40} radius={12} delay={i * 60} />
          <View style={{ flex: 1, gap: 6 }}>
            <ShimmerBar width="50%" height={14} delay={i * 60 + 20} />
            <ShimmerBar width="75%" height={10} delay={i * 60 + 40} />
          </View>
          <ShimmerBar width={48} height={28} radius={14} delay={i * 60 + 60} />
        </View>
      ))}
    </View>
  );
}

/* ─── Achievements / Badges Skeleton ─── */
export function AchievementsSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const cols = width >= 1024 ? 4 : width >= 768 ? 3 : 2;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-achievements" testID="skeleton-achievements">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="40%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="55%" height={12} delay={40} />
      </View>
      {/* Progress bar */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
          <ShimmerBar width="30%" height={14} />
          <ShimmerBar width="15%" height={14} delay={30} />
        </View>
        <ShimmerBar width="100%" height={10} radius={5} delay={60} />
      </View>
      {/* Badge grid */}
      <View style={[sk.grid, sk.gridDesktop]}>
        {Array.from({ length: cols * 2 }).map((_, i) => (
          <View key={i} style={[sk.galleryCard, { backgroundColor: colors.card, borderColor: colors.border, alignItems: 'center', minWidth: 140 }]}>
            <ShimmerBar width={56} height={56} radius={28} delay={i * 50} />
            <View style={{ height: 10 }} />
            <ShimmerBar width="65%" height={14} delay={i * 50 + 20} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="80%" height={10} delay={i * 50 + 40} />
            <View style={{ height: 8 }} />
            <ShimmerBar width="100%" height={6} radius={3} delay={i * 50 + 60} />
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Team Management Skeleton ─── */
export function TeamSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-team" testID="skeleton-team">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="30%" height={22} />
        <ShimmerBar width={130} height={38} radius={10} delay={50} />
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="50%" height={24} delay={i * 50} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 25} />
          </View>
        ))}
      </View>
      {/* Team member cards */}
      {[0, 1, 2, 3, 4].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 14, backgroundColor: colors.card, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10, alignItems: 'center' }}>
          <ShimmerBar width={46} height={46} radius={23} delay={i * 50} />
          <View style={{ flex: 1, gap: 5 }}>
            <ShimmerBar width="45%" height={14} delay={i * 50 + 15} />
            <ShimmerBar width="35%" height={10} delay={i * 50 + 30} />
          </View>
          <ShimmerBar width={70} height={26} radius={8} delay={i * 50 + 45} />
        </View>
      ))}
    </View>
  );
}

/* ─── Career / Hiring Skeleton ─── */
export function CareerSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-career" testID="skeleton-career">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="40%" height={24} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="70%" height={12} delay={40} />
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={24} height={24} radius={8} delay={i * 50} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="55%" height={22} delay={i * 50 + 20} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 40} />
          </View>
        ))}
      </View>
      {/* Filters */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {[90, 80, 70, 100].map((w, i) => (
          <ShimmerBar key={i} width={w} height={32} radius={8} delay={i * 40} />
        ))}
      </View>
      {/* Job cards */}
      <View style={isWide ? { flexDirection: 'row', flexWrap: 'wrap', gap: 14 } : { gap: 12 }}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={{ backgroundColor: colors.card, borderRadius: 18, padding: 18, borderWidth: 1, borderColor: colors.border, flex: isWide ? undefined : 1, width: isWide ? '48%' : '100%', gap: 10 }}>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <ShimmerBar width={48} height={48} radius={12} delay={i * 70} />
              <View style={{ flex: 1, gap: 6 }}>
                <ShimmerBar width="65%" height={16} delay={i * 70 + 20} />
                <ShimmerBar width="45%" height={11} delay={i * 70 + 40} />
              </View>
            </View>
            <ShimmerBar width="90%" height={10} delay={i * 70 + 60} />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {[60, 80, 50].map((w, j) => (
                <ShimmerBar key={j} width={w} height={22} radius={6} delay={i * 70 + 80 + j * 20} />
              ))}
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Help / FAQ Skeleton ─── */
export function HelpSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-help" testID="skeleton-help">
      {/* Header */}
      <View style={[sk.section, { alignItems: 'center' }]}>
        <ShimmerBar width="40%" height={24} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="60%" height={12} delay={40} />
      </View>
      {/* Search */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={46} radius={14} />
      </View>
      {/* Category tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {[90, 110, 80, 100, 70].map((w, i) => (
          <ShimmerBar key={i} width={w} height={34} radius={10} delay={i * 40} />
        ))}
      </View>
      {/* FAQ accordion items */}
      {[0, 1, 2, 3, 4, 5, 6].map(i => (
        <View key={i} style={{ backgroundColor: colors.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 10, flexDirection: 'row', gap: 12, alignItems: 'center' }}>
          <ShimmerBar width={28} height={28} radius={8} delay={i * 40} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="70%" height={14} delay={i * 40 + 15} />
            <ShimmerBar width="50%" height={10} delay={i * 40 + 30} />
          </View>
          <ShimmerBar width={20} height={20} radius={4} delay={i * 40 + 45} />
        </View>
      ))}
    </View>
  );
}

/* ─── Mini App Skeleton ─── */
export function MiniAppSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-mini-app" testID="skeleton-mini-app">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', gap: 14, alignItems: 'center' }]}>
        <ShimmerBar width={48} height={48} radius={14} />
        <View style={{ flex: 1, gap: 6 }}>
          <ShimmerBar width="50%" height={18} />
          <ShimmerBar width="35%" height={11} delay={30} />
        </View>
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="50%" height={22} delay={i * 50} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 25} />
          </View>
        ))}
      </View>
      {/* Main content area */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ShimmerBar width="40%" height={14} />
        <View style={{ height: 14 }} />
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={{ flexDirection: 'row', gap: 12, marginBottom: 14, alignItems: 'center' }}>
            <ShimmerBar width={40} height={40} radius={10} delay={i * 60} />
            <View style={{ flex: 1, gap: 5 }}>
              <ShimmerBar width="60%" height={13} delay={i * 60 + 20} />
              <ShimmerBar width="80%" height={10} delay={i * 60 + 40} />
            </View>
            <ShimmerBar width={56} height={28} radius={8} delay={i * 60 + 60} />
          </View>
        ))}
      </View>
      {/* Action button */}
      <ShimmerBar width="100%" height={48} radius={14} delay={300} />
    </View>
  );
}

/* ─── Profile / Edit Form Skeleton ─── */
export function ProfileFormSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-profile-form" testID="skeleton-profile-form">
      {/* Avatar */}
      <View style={{ alignItems: 'center', marginBottom: 24 }}>
        <ShimmerBar width={90} height={90} radius={45} />
        <View style={{ height: 10 }} />
        <ShimmerBar width="25%" height={12} delay={60} />
      </View>
      {/* Form fields */}
      {[0, 1, 2, 3, 4, 5].map(i => (
        <View key={i} style={{ marginBottom: 18, gap: 6 }}>
          <ShimmerBar width="25%" height={11} delay={i * 40} />
          <ShimmerBar width="100%" height={44} radius={12} delay={i * 40 + 20} />
        </View>
      ))}
      {/* Submit button */}
      <ShimmerBar width="100%" height={48} radius={14} delay={300} />
    </View>
  );
}

/* ─── AI Feature Skeleton (Briefing, Learning Hub, Problem Solver) ─── */
export function AIFeatureSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-ai-feature" testID="skeleton-ai-feature">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="45%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="65%" height={12} delay={40} />
      </View>
      {/* AI summary card */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', marginBottom: 14 }}>
          <ShimmerBar width={40} height={40} radius={12} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="50%" height={16} delay={30} />
            <ShimmerBar width="35%" height={10} delay={50} />
          </View>
        </View>
        <ShimmerBar width="95%" height={11} delay={70} />
        <View style={{ height: 5 }} />
        <ShimmerBar width="80%" height={11} delay={90} />
        <View style={{ height: 5 }} />
        <ShimmerBar width="60%" height={11} delay={110} />
      </View>
      {/* Action cards */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border, minWidth: 150 }]}>
            <ShimmerBar width={28} height={28} radius={10} delay={i * 60} />
            <View style={{ height: 8 }} />
            <ShimmerBar width="60%" height={14} delay={i * 60 + 25} />
            <ShimmerBar width="80%" height={10} delay={i * 60 + 50} />
          </View>
        ))}
      </View>
      {/* Content list */}
      {[0, 1, 2, 3].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 10 }}>
          <ShimmerBar width={36} height={36} radius={10} delay={i * 50} />
          <View style={{ flex: 1, gap: 5 }}>
            <ShimmerBar width="55%" height={14} delay={i * 50 + 15} />
            <ShimmerBar width="80%" height={10} delay={i * 50 + 30} />
          </View>
        </View>
      ))}
    </View>
  );
}

/* ─── Payment History Skeleton ─── */
export function PaymentHistorySkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-payment-history" testID="skeleton-payment-history">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="35%" height={22} />
        <ShimmerBar width={100} height={34} radius={10} delay={40} />
      </View>
      {/* Summary cards */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={20} height={20} radius={6} delay={i * 50} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="55%" height={22} delay={i * 50 + 20} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 40} />
          </View>
        ))}
      </View>
      {/* Transaction list */}
      {[0, 1, 2, 3, 4, 5].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <ShimmerBar width={38} height={38} radius={10} delay={i * 40} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="50%" height={13} delay={i * 40 + 10} />
            <ShimmerBar width="30%" height={10} delay={i * 40 + 25} />
          </View>
          <View style={{ alignItems: 'flex-end', gap: 4 }}>
            <ShimmerBar width={70} height={16} delay={i * 40 + 35} />
            <ShimmerBar width={50} height={10} delay={i * 40 + 50} />
          </View>
        </View>
      ))}
    </View>
  );
}

/* ─── usePageReady hook — guarantees < 1s skeleton, prevents flash, auto-reports perf ─── */
// Global optimization cache (loaded once per session)
let _optCache: Record<string, any> | null = null;
let _optFetching = false;

const _normalizedBackendBase = () => {
  return resolveRuntimeBaseUrl();
};

async function _getOptimizations(): Promise<Record<string, any>> {
  if (_optCache) return _optCache;
  if (_optFetching) return {};
  _optFetching = true;
  try {
    const backendUrl = _normalizedBackendBase();
    if (backendUrl) {
      const res = await fetch(`${backendUrl}/api/vitals/page-optimizations`);
      const data = await res.json();
      if (data.ok) _optCache = data.optimizations || {};
    }
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/SkeletonLoaders.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  _optFetching = false;
  return _optCache || {};
}

export function usePageReady(isDataLoaded: boolean = true, minMs = 180): boolean {
  const [ready, setReady] = useState(false);
  const startRef = useRef(Date.now());
  const reportedRef = useRef(false);
  const page = typeof window !== 'undefined' ? window.location.pathname : 'unknown';

  // Load optimizations on mount
  const [opts, setOpts] = useState<any>(null);
  useEffect(() => {
    _getOptimizations().then(o => {
      const pageOpt = o[page];
      if (pageOpt) setOpts(pageOpt);
    });
  }, [page]);

  // Determine effective timing from auto-fix config
  const effectiveMin = opts?.min_ms ?? minMs;
  const effectiveCap = opts?.cap_ms ?? 800;

  useEffect(() => {
    if (isDataLoaded) {
      const t = setTimeout(() => setReady(true), effectiveMin);
      return () => clearTimeout(t);
    }
  }, [isDataLoaded, effectiveMin]);
  // Hard cap — never show skeleton beyond this
  useEffect(() => {
    const cap = setTimeout(() => setReady(true), effectiveCap);
    return () => clearTimeout(cap);
  }, [effectiveCap]);
  // Auto-report perf when content becomes ready
  useEffect(() => {
    if (ready && !reportedRef.current) {
      reportedRef.current = true;
      const duration = Date.now() - startRef.current;
      try {
        const backendUrl = _normalizedBackendBase();
        if (backendUrl) {
          const payload = JSON.stringify({ page, duration_ms: duration, skeleton: 'auto', release_version: PERFORMANCE_STANDARDS.telemetryRelease });
          // Use sendBeacon for fire-and-forget telemetry to avoid ERR_ABORTED on navigation
          if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
            navigator.sendBeacon(`${backendUrl}/api/vitals/page-perf`, payload);
          } else {
            fetch(`${backendUrl}/api/vitals/page-perf`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: payload,
              keepalive: true,
            }).catch(() => {});
          }
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/SkeletonLoaders.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, [ready, page]);
  return ready;
}

/* ─── Pricing / Plans Skeleton ─── */
export function PricingSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const cols = width >= 1024 ? 3 : width >= 768 ? 2 : 1;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-pricing" testID="skeleton-pricing">
      {/* Hero */}
      <View style={[sk.section, { alignItems: 'center', paddingVertical: 24 }]}>
        <ShimmerBar width="35%" height={24} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="55%" height={12} delay={40} />
        <View style={{ height: 18 }} />
        <ShimmerBar width={200} height={38} radius={20} delay={80} />
      </View>
      {/* Plan cards */}
      <View style={cols > 1 ? { flexDirection: 'row', gap: 16, flexWrap: 'wrap' } : { gap: 16 }}>
        {[0, 1, 2].map(i => (
          <View key={i} style={{ flex: cols > 1 ? 1 : undefined, backgroundColor: colors.card, borderRadius: 20, padding: 22, borderWidth: i === 1 ? 2 : 1, borderColor: i === 1 ? colors.primary : colors.border, minWidth: cols > 1 ? 240 : undefined }}>
            {i === 1 && <ShimmerBar width={80} height={20} radius={10} delay={50} />}
            <View style={{ height: i === 1 ? 10 : 0 }} />
            <ShimmerBar width="40%" height={18} delay={i * 60} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="60%" height={11} delay={i * 60 + 20} />
            <View style={{ height: 14 }} />
            <ShimmerBar width="50%" height={28} delay={i * 60 + 40} />
            <View style={{ height: 16 }} />
            {[0, 1, 2, 3, 4].map(j => (
              <View key={j} style={{ flexDirection: 'row', gap: 8, marginBottom: 10, alignItems: 'center' }}>
                <ShimmerBar width={16} height={16} radius={8} delay={i * 60 + j * 25} />
                <ShimmerBar width="75%" height={11} delay={i * 60 + j * 25 + 10} />
              </View>
            ))}
            <View style={{ height: 14 }} />
            <ShimmerBar width="100%" height={44} radius={12} delay={i * 60 + 160} />
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Static / Legal Content Skeleton ─── */
export function StaticContentSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-static-content" testID="skeleton-static-content">
      {/* Hero */}
      <View style={[sk.section, { alignItems: 'center', paddingVertical: 20 }]}>
        <ShimmerBar width={90} height={22} radius={12} />
        <View style={{ height: 12 }} />
        <ShimmerBar width="55%" height={26} delay={40} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="70%" height={12} delay={80} />
      </View>
      {/* Paragraphs */}
      {[0, 1, 2, 3].map(i => (
        <View key={i} style={[sk.section, { gap: 6 }]}>
          <ShimmerBar width="30%" height={16} delay={i * 50} />
          <View style={{ height: 6 }} />
          <ShimmerBar width="100%" height={11} delay={i * 50 + 15} />
          <ShimmerBar width="95%" height={11} delay={i * 50 + 25} />
          <ShimmerBar width="85%" height={11} delay={i * 50 + 35} />
          <ShimmerBar width="60%" height={11} delay={i * 50 + 45} />
        </View>
      ))}
    </View>
  );
}

/* ─── Integrations Page Skeleton ─── */
export function IntegrationsSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-integrations" testID="skeleton-integrations">
      <View style={sk.section}>
        <ShimmerBar width="40%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="60%" height={12} delay={40} />
      </View>
      {/* Filter chips */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {[90, 80, 100, 70, 85].map((w, i) => (
          <ShimmerBar key={i} width={w} height={32} radius={10} delay={i * 35} />
        ))}
      </View>
      {/* Integration cards */}
      <View style={isWide ? { flexDirection: 'row', flexWrap: 'wrap', gap: 14 } : { gap: 12 }}>
        {[0, 1, 2, 3, 4, 5].map(i => (
          <View key={i} style={{ backgroundColor: colors.card, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: colors.border, width: isWide ? '48%' : '100%', gap: 10 }}>
            <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
              <ShimmerBar width={44} height={44} radius={12} delay={i * 50} />
              <View style={{ flex: 1, gap: 4 }}>
                <ShimmerBar width="55%" height={15} delay={i * 50 + 15} />
                <ShimmerBar width="75%" height={10} delay={i * 50 + 30} />
              </View>
              <ShimmerBar width={60} height={28} radius={8} delay={i * 50 + 45} />
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Feature Index / Gallery Skeleton ─── */
export function FeatureIndexSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const cols = width >= 1024 ? 3 : width >= 768 ? 2 : 1;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-feature-index" testID="skeleton-feature-index">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="45%" height={24} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="65%" height={12} delay={40} />
      </View>
      {/* Search */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={44} radius={12} />
        <View style={{ height: 12 }} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[80, 90, 70, 100, 60].map((w, i) => (
            <ShimmerBar key={i} width={w} height={32} radius={10} delay={i * 35} />
          ))}
        </View>
      </View>
      {/* Feature cards grid */}
      <View style={cols > 1 ? { flexDirection: 'row', flexWrap: 'wrap', gap: 14 } : { gap: 12 }}>
        {Array.from({ length: cols * 3 }).map((_, i) => (
          <View key={i} style={{ backgroundColor: colors.card, borderRadius: 18, padding: 18, borderWidth: 1, borderColor: colors.border, width: cols > 1 ? `${(100 / cols) - 2}%` as any : '100%', gap: 10 }}>
            <ShimmerBar width={42} height={42} radius={12} delay={i * 40} />
            <ShimmerBar width="65%" height={15} delay={i * 40 + 15} />
            <ShimmerBar width="85%" height={10} delay={i * 40 + 30} />
            <ShimmerBar width="50%" height={10} delay={i * 40 + 45} />
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Feature Detail Skeleton (single feature page) ─── */
export function FeatureDetailSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-feature-detail" testID="skeleton-feature-detail">
      {/* Hero */}
      <View style={[sk.section, { alignItems: 'center', paddingVertical: 24 }]}>
        <ShimmerBar width={64} height={64} radius={18} />
        <View style={{ height: 14 }} />
        <ShimmerBar width="50%" height={22} delay={40} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="70%" height={12} delay={70} />
      </View>
      {/* Info cards */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={24} height={24} radius={8} delay={i * 50} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="55%" height={16} delay={i * 50 + 20} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 40} />
          </View>
        ))}
      </View>
      {/* Content sections */}
      {[0, 1, 2].map(i => (
        <View key={i} style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <ShimmerBar width="35%" height={14} delay={i * 60} />
          <View style={{ height: 10 }} />
          <ShimmerBar width="95%" height={11} delay={i * 60 + 20} />
          <ShimmerBar width="80%" height={11} delay={i * 60 + 35} />
          <ShimmerBar width="60%" height={11} delay={i * 60 + 50} />
        </View>
      ))}
      {/* CTA button */}
      <ShimmerBar width="100%" height={48} radius={14} delay={250} />
    </View>
  );
}

/* ─── Onboarding / Welcome Slides Skeleton ─── */
export function OnboardingSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }]} data-testid="skeleton-onboarding" testID="skeleton-onboarding">
      <ShimmerBar width={80} height={80} radius={20} />
      <View style={{ height: 28 }} />
      <ShimmerBar width="55%" height={24} delay={60} />
      <View style={{ height: 12 }} />
      <ShimmerBar width="75%" height={12} delay={100} />
      <View style={{ height: 6 }} />
      <ShimmerBar width="60%" height={12} delay={130} />
      <View style={{ height: 40 }} />
      {/* Dots */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {[0, 1, 2, 3].map(i => (
          <ShimmerBar key={i} width={i === 0 ? 24 : 8} height={8} radius={4} delay={160 + i * 30} />
        ))}
      </View>
      <View style={{ height: 30 }} />
      <ShimmerBar width="80%" height={48} radius={14} delay={280} />
    </View>
  );
}

/* ─── Feedback Form Skeleton ─── */
export function FeedbackFormSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-feedback-form" testID="skeleton-feedback-form">
      {/* Header */}
      <View style={sk.section}>
        <ShimmerBar width="35%" height={22} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="55%" height={12} delay={40} />
      </View>
      {/* Rating stars */}
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, alignItems: 'center' }]}>
        <ShimmerBar width="30%" height={14} delay={60} />
        <View style={{ height: 14 }} />
        <View style={{ flexDirection: 'row', gap: 10 }}>
          {[0, 1, 2, 3, 4].map(i => (
            <ShimmerBar key={i} width={36} height={36} radius={18} delay={80 + i * 30} />
          ))}
        </View>
      </View>
      {/* Text area */}
      <View style={{ marginBottom: 18, gap: 6 }}>
        <ShimmerBar width="20%" height={11} delay={180} />
        <ShimmerBar width="100%" height={120} radius={14} delay={200} />
      </View>
      {/* Submit */}
      <ShimmerBar width="100%" height={48} radius={14} delay={260} />
    </View>
  );
}

/* ─── Subscription Flow Skeleton (payment-result, success) ─── */
export function SubscriptionFlowSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }]} data-testid="skeleton-subscription-flow" testID="skeleton-subscription-flow">
      <ShimmerBar width={72} height={72} radius={36} />
      <View style={{ height: 20 }} />
      <ShimmerBar width="45%" height={22} delay={60} />
      <View style={{ height: 10 }} />
      <ShimmerBar width="65%" height={12} delay={100} />
      <View style={{ height: 6 }} />
      <ShimmerBar width="50%" height={12} delay={130} />
      <View style={{ height: 28 }} />
      <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, width: '100%', maxWidth: 400 }]}>
        {[0, 1, 2].map(i => (
          <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14 }}>
            <ShimmerBar width="35%" height={12} delay={160 + i * 30} />
            <ShimmerBar width="25%" height={12} delay={170 + i * 30} />
          </View>
        ))}
      </View>
      <ShimmerBar width="80%" height={46} radius={14} delay={280} />
    </View>
  );
}

/* ─── Welcome / Landing Page Skeleton ─── */
export function WelcomeLandingSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-welcome" testID="skeleton-welcome">
      {/* Navbar */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <ShimmerBar width={120} height={28} radius={8} />
        <View style={{ flexDirection: 'row', gap: 14 }}>
          {[80, 70, 90].map((w, i) => (
            <ShimmerBar key={i} width={w} height={14} delay={i * 30} />
          ))}
        </View>
        <ShimmerBar width={100} height={36} radius={10} delay={120} />
      </View>
      {/* Hero */}
      <View style={{ alignItems: 'center', paddingVertical: isWide ? 48 : 28, marginBottom: 32 }}>
        <ShimmerBar width={100} height={24} radius={12} delay={40} />
        <View style={{ height: 16 }} />
        <ShimmerBar width={isWide ? '50%' : '80%'} height={isWide ? 38 : 28} delay={80} />
        <View style={{ height: 10 }} />
        <ShimmerBar width={isWide ? '35%' : '65%'} height={isWide ? 38 : 28} delay={110} />
        <View style={{ height: 18 }} />
        <ShimmerBar width={isWide ? '40%' : '85%'} height={14} delay={140} />
        <View style={{ height: 24 }} />
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <ShimmerBar width={140} height={46} radius={14} delay={180} />
          <ShimmerBar width={120} height={46} radius={14} delay={210} />
        </View>
      </View>
      {/* Stats row */}
      <View style={sk.row}>
        {[0, 1, 2, 3].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width="50%" height={22} delay={i * 50} />
            <ShimmerBar width="65%" height={10} delay={i * 50 + 25} />
          </View>
        ))}
      </View>
      {/* Features grid */}
      <View style={isWide ? { flexDirection: 'row', gap: 16 } : { gap: 14 }}>
        {[0, 1, 2].map(i => (
          <View key={i} style={{ flex: 1, backgroundColor: colors.card, borderRadius: 18, padding: 20, borderWidth: 1, borderColor: colors.border }}>
            <ShimmerBar width={40} height={40} radius={12} delay={i * 60} />
            <View style={{ height: 12 }} />
            <ShimmerBar width="60%" height={16} delay={i * 60 + 25} />
            <View style={{ height: 6 }} />
            <ShimmerBar width="85%" height={10} delay={i * 60 + 45} />
            <ShimmerBar width="70%" height={10} delay={i * 60 + 60} />
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Language Selector Skeleton ─── */
export function LanguageSelectorSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-language-selector" testID="skeleton-language-selector">
      <View style={[sk.section, { alignItems: 'center' }]}>
        <ShimmerBar width={48} height={48} radius={14} />
        <View style={{ height: 12 }} />
        <ShimmerBar width="40%" height={20} delay={40} />
        <View style={{ height: 6 }} />
        <ShimmerBar width="55%" height={12} delay={70} />
      </View>
      {/* Search */}
      <View style={sk.section}>
        <ShimmerBar width="100%" height={44} radius={12} delay={100} />
      </View>
      {/* Language items */}
      {[0, 1, 2, 3, 4, 5, 6, 7].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 14, alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <ShimmerBar width={36} height={24} radius={4} delay={i * 30} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="45%" height={14} delay={i * 30 + 10} />
            <ShimmerBar width="30%" height={10} delay={i * 30 + 20} />
          </View>
          <ShimmerBar width={20} height={20} radius={10} delay={i * 30 + 30} />
        </View>
      ))}
    </View>
  );
}

/* ─── Admin Console Skeleton ─── */
export function AdminConsoleSkeleton() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-admin-console" testID="skeleton-admin-console">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <View style={{ gap: 6 }}>
          <ShimmerBar width="40%" height={24} />
          <ShimmerBar width="60%" height={12} delay={40} />
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <ShimmerBar width={36} height={36} radius={10} delay={60} />
          <ShimmerBar width={36} height={36} radius={10} delay={80} />
        </View>
      </View>
      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20 }}>
        {[90, 80, 100, 70, 85, 75].map((w, i) => (
          <ShimmerBar key={i} width={w} height={34} radius={10} delay={i * 30} />
        ))}
      </View>
      {/* KPI cards */}
      <View style={sk.row}>
        {[0, 1, 2, 3, 4].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={22} height={22} radius={8} delay={i * 40} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="55%" height={22} delay={i * 40 + 15} />
            <ShimmerBar width="70%" height={10} delay={i * 40 + 30} />
          </View>
        ))}
      </View>
      {/* Chart + Table */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 2 }]}>
          <ShimmerBar width="30%" height={14} />
          <View style={{ height: 14 }} />
          <ShimmerBar width="100%" height={160} radius={12} delay={80} />
        </View>
        <View style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border, flex: 1 }]}>
          <ShimmerBar width="40%" height={14} />
          <View style={{ height: 14 }} />
          {[0, 1, 2, 3].map(i => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, marginBottom: 12 }}>
              <ShimmerBar width={32} height={32} radius={8} delay={i * 40} />
              <View style={{ flex: 1, gap: 4 }}>
                <ShimmerBar width="60%" height={12} delay={i * 40 + 15} />
                <ShimmerBar width="40%" height={10} delay={i * 40 + 30} />
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

/* ─── Downloads Page Skeleton ─── */
export function DownloadsSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-downloads" testID="skeleton-downloads">
      {/* Header */}
      <View style={[sk.section, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}>
        <ShimmerBar width="30%" height={22} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <ShimmerBar width={100} height={34} radius={10} />
          <ShimmerBar width={34} height={34} radius={10} delay={30} />
        </View>
      </View>
      {/* Stats */}
      <View style={sk.row}>
        {[0, 1, 2].map(i => (
          <View key={i} style={[sk.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <ShimmerBar width={20} height={20} radius={6} delay={i * 50} />
            <View style={{ height: 4 }} />
            <ShimmerBar width="55%" height={20} delay={i * 50 + 20} />
            <ShimmerBar width="70%" height={10} delay={i * 50 + 40} />
          </View>
        ))}
      </View>
      {/* Download items */}
      {[0, 1, 2, 3, 4, 5].map(i => (
        <View key={i} style={{ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 14, paddingHorizontal: 10, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <ShimmerBar width={40} height={40} radius={10} delay={i * 35} />
          <View style={{ flex: 1, gap: 4 }}>
            <ShimmerBar width="55%" height={14} delay={i * 35 + 10} />
            <ShimmerBar width="35%" height={10} delay={i * 35 + 20} />
          </View>
          <ShimmerBar width={70} height={28} radius={8} delay={i * 35 + 35} />
        </View>
      ))}
    </View>
  );
}

/* ─── Safe Deployment / Info Page Skeleton ─── */
export function InfoPageSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[sk.root, { backgroundColor: colors.bg }]} data-testid="skeleton-info-page" testID="skeleton-info-page">
      <View style={sk.section}>
        <ShimmerBar width="45%" height={24} />
        <View style={{ height: 8 }} />
        <ShimmerBar width="65%" height={12} delay={40} />
      </View>
      {[0, 1, 2, 3].map(i => (
        <View key={i} style={[sk.chartBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', marginBottom: 10 }}>
            <ShimmerBar width={32} height={32} radius={10} delay={i * 50} />
            <ShimmerBar width="50%" height={16} delay={i * 50 + 20} />
          </View>
          <ShimmerBar width="90%" height={11} delay={i * 50 + 35} />
          <View style={{ height: 4 }} />
          <ShimmerBar width="75%" height={11} delay={i * 50 + 50} />
          <View style={{ height: 10 }} />
          {[0, 1, 2].map(j => (
            <View key={j} style={{ flexDirection: 'row', gap: 8, marginBottom: 6 }}>
              <ShimmerBar width={6} height={6} radius={3} delay={i * 50 + 60 + j * 15} />
              <ShimmerBar width="80%" height={10} delay={i * 50 + 65 + j * 15} />
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const sk = StyleSheet.create({
  root: { flex: 1, padding: 20 },
  section: { marginBottom: 20 },
  row: { flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' },
  statCard: { flex: 1, minWidth: 120, borderRadius: 16, padding: 16, borderWidth: 1, alignItems: 'center', gap: 4 },
  chartBox: { borderRadius: 18, padding: 20, borderWidth: 1, marginBottom: 20 },
  chartBars: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, height: 100 },
  chartBarCol: { flex: 1 },
  grid: { gap: 14 },
  gridDesktop: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  galleryCard: { borderRadius: 18, padding: 18, borderWidth: 1, flex: 1 },
  modalInner: { borderRadius: 22, overflow: 'hidden' },
});

// Animated content reveal - fade in + slide up when content replaces skeleton
export function FadeSlideIn({ children, duration = 350, delay = 0, slideDistance = 14 }: { children: React.ReactNode; duration?: number; delay?: number; slideDistance?: number }) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(slideDistance)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration, delay, useNativeDriver: false }),
      Animated.timing(translateY, { toValue: 0, duration, delay, useNativeDriver: false }),
    ]).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View style={{ opacity, transform: [{ translateY }], flex: 1 }}>
      {children}
    </Animated.View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
