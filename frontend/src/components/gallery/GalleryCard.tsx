import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

// Dark-mode surface keeps the gallery readable while still letting shell imagery show through.
const GALLERY_CARD_DARK_BG = 'rgba(15, 23, 42, 0.72)';

interface Metrics {
  usage_count: number;
  active_users: number;
  performance_score: number;
  confidence_score: number;
  status: string;
  last_updated: string;
  sparkline: number[];
  trend: string;
  trend_pct: number;
  efficiency: number;
}

interface Props {
  feature: { id: string; title: string; description: string; icon: string; color: string; category: string; isNew?: boolean; premium?: boolean };
  metrics: Metrics | null;
  onPress: () => void;
  onLongPress?: () => void;
  colors: any;
  accentColor: string;
  cardWidth?: string;
  darkMode?: boolean;
}

function Sparkline({ data, color, height = 32 }: { data: number[]; color: string; height?: number }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 2 }}>
      {data.map((v, i) => {
        const h = Math.max(3, ((v - min) / range) * height);
        const isLast = i >= data.length - 2;
        return (
          <View
            key={i}
            style={{
              flex: 1,
              height: h,
              borderRadius: 2,
              backgroundColor: (globalThis as any).__alphaColor(isLast ? color : color, '40'),
            }}
          />
        );
      })}
    </View>
  );
}

export function GalleryCard({ feature, metrics, onPress, colors, accentColor, cardWidth, darkMode }: Props) {
  const trendColor = metrics?.trend === 'up' ? 'var(--app-success)' : metrics?.trend === 'down' ? 'var(--app-error)' : 'var(--app-primary)';
  const trendIcon = metrics?.trend === 'up' ? 'trending-up' : metrics?.trend === 'down' ? 'trending-down' : 'remove';
  const statusColor = metrics?.status === 'active' ? 'var(--app-success)' : metrics?.status === 'beta' ? 'var(--app-warning)' : 'var(--app-primary)';

  const blur = Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {};
  const hoverShadow = Platform.OS === 'web' ? { transition: 'transform 0.2s ease, box-shadow 0.2s ease' } as any : {};

  const darkCardOverride = darkMode ? {
    backgroundColor: GALLERY_CARD_DARK_BG,
    borderColor: (globalThis as any).__alphaColor(feature.color, '35'),
    ...(Platform.OS === 'web' ? { boxShadow: `0 4px 20px ${feature.color}10`, backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}),
  } : {};

  return (
    <TouchableOpacity accessibilityLabel="On press in gallery card"
      style={[
        s.card,
        { backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'B0' : 'E2') : colors.card, borderColor: colors.border, width: cardWidth },
        darkCardOverride,
        blur,
        hoverShadow,
      ]}
      onPress={onPress}
      activeOpacity={0.85}
      data-testid={`gallery-card-${feature.id}`} testID={`gallery-card-${feature.id}`}
    >
      {/* Accent line */}
      <View style={[s.accentLine, { backgroundColor: feature.color }]} />

      {/* Header row */}
      <View style={s.headerRow}>
        <View style={[s.iconBox, { backgroundColor: feature.color + (darkMode ? '1C' : '14'), borderColor: feature.color + (darkMode ? '35' : '25') }]}>
          <Ionicons name={feature.icon as any} size={22} color={feature.color} />
        </View>
        <View style={s.headerRight}>
          <View style={[s.statusDot, { backgroundColor: statusColor }]} />
          {feature.isNew && (
            <View style={[s.newBadge, { backgroundColor: (globalThis as any).__alphaColor(colors.primary, '18') }]}>
              <Text style={[s.newBadgeText, { color: colors.primary }]}>NEW</Text>
            </View>
          )}
        </View>
      </View>

      {/* Title & Category */}
      <Text style={[s.title, { color: colors.text }]} numberOfLines={1} data-testid={`gallery-title-${feature.id}`} testID={`gallery-title-${feature.id}`}>
        {feature.title}
      </Text>
      <View style={s.categoryRow}>
        <View style={[s.categoryChip, { backgroundColor: feature.color + (darkMode ? '14' : '0C'), borderColor: feature.color + (darkMode ? '28' : '18') }]}>
          <Text style={[s.categoryText, { color: feature.color }]}>{feature.category}</Text>
        </View>
      </View>

      {/* Description */}
      <Text style={[s.desc, { color: colors.textSec }]} numberOfLines={2} data-testid={`gallery-desc-${feature.id}`} testID={`gallery-desc-${feature.id}`}>
        {feature.description}
      </Text>

      {/* Sparkline */}
      {metrics && (
        <View style={s.sparkBox}>
          <Sparkline data={metrics.sparkline} color={feature.color} height={28} />
        </View>
      )}

      {/* Metrics row */}
      {metrics && (
        <View style={s.metricsRow}>
          <View style={s.metricItem}>
            <Text style={[s.metricValue, { color: colors.text }]}>{metrics.usage_count >= 1000 ? (metrics.usage_count / 1000).toFixed(1) + 'K' : metrics.usage_count}</Text>
            <Text style={[s.metricLabel, { color: colors.textSec }]}>Uses</Text>
          </View>
          <View style={[s.metricDivider, { backgroundColor: colors.border }]} />
          <View style={s.metricItem}>
            <Text style={[s.metricValue, { color: colors.text }]}>{metrics.performance_score}%</Text>
            <Text style={[s.metricLabel, { color: colors.textSec }]}>Perf</Text>
          </View>
          <View style={[s.metricDivider, { backgroundColor: colors.border }]} />
          <View style={s.metricItem}>
            <Text style={[s.metricValue, { color: colors.text }]}>{metrics.confidence_score}</Text>
            <Text style={[s.metricLabel, { color: colors.textSec }]}>Score</Text>
          </View>
        </View>
      )}

      {/* Footer */}
      <View style={s.footer}>
        <View style={s.footerLeft}>
          {metrics && (
            <>
              <Ionicons name={trendIcon as any} size={12} color={trendColor} />
              <Text style={[s.trendText, { color: trendColor }]}>{metrics.trend_pct > 0 ? '+' : ''}{metrics.trend_pct}%</Text>
            </>
          )}
          {metrics && <Text style={[s.updatedText, { color: colors.textMuted }]}>{metrics.last_updated}</Text>}
        </View>
        <View style={s.launchRow}>
          <Text style={[s.launchText, { color: accentColor }]}>Open</Text>
          <Ionicons name="arrow-forward" size={13} color={accentColor} />
        </View>
      </View>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  card: { borderRadius: 18, borderWidth: 1, padding: 18, overflow: 'hidden', position: 'relative' },
  accentLine: { position: 'absolute', top: 0, left: 0, right: 0, height: 3, borderTopLeftRadius: 18, borderTopRightRadius: 18 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  iconBox: { width: 46, height: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  newBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  newBadgeText: { fontSize: 9, fontWeight: '800', letterSpacing: 0.8 },
  title: { fontSize: 16, fontWeight: '700', letterSpacing: -0.2, marginBottom: 6 },
  categoryRow: { marginBottom: 8 },
  categoryChip: { alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  categoryText: { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  desc: { fontSize: 12, lineHeight: 18, marginBottom: 12 },
  sparkBox: { marginBottom: 12, paddingVertical: 4 },
  metricsRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  metricItem: { flex: 1, alignItems: 'center' },
  metricValue: { fontSize: 14, fontWeight: '800', letterSpacing: -0.3 },
  metricLabel: { fontSize: 9, fontWeight: '600', marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 },
  metricDivider: { width: 1, height: 24 },
  footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  footerLeft: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  trendText: { fontSize: 11, fontWeight: '700' },
  updatedText: { fontSize: 10 },
  launchRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  launchText: { fontSize: 12, fontWeight: '700' },
});

/* i18n-probe t('i18n.auto.probe') */
