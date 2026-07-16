/**
 * Enterprise-styled feature index tab.
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFeatures } from '../../context/FeaturesContext';
import { type ThemeColors } from './helpTypes';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

interface FeatureIndexTabProps {
  C: ThemeColors;
  darkMode: boolean;
  isWide: boolean;
  isTablet?: boolean;
  featureSearch: string;
  setFeatureSearch: (v: string) => void;
  featureCat: string | null;
  setFeatureCat: (v: string | null) => void;
  filteredFeatures: any[];
  onFeaturePress: (route: string) => void;
}

export default function FeatureIndexTab({ C, darkMode, isWide, isTablet, featureSearch, setFeatureSearch, featureCat, setFeatureCat, filteredFeatures, onFeaturePress }: FeatureIndexTabProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const normalizeFeatureDescription = (feature: any) => {
    const raw = String(feature?.description || '').trim();
    if (!raw || ['description', 'subtitle'].includes(raw.toLowerCase())) {
      return tx('features.card.descriptionFallback', 'Open this feature and continue your workflow with AI-guided support.');
    }
    return raw;
  };
  const inactiveChipBg = C.bgSoft;
  const inactiveChipBorder = C.border;
  const inactiveChipText = darkMode ? C.textMuted : C.textSec;
  const selectedChipText = colors.primaryText;

  // @autofix-moved: was module-level const s
  const s = StyleSheet.create({
    faqHeader: { borderRadius: 18, borderWidth: 1, padding: 18, marginBottom: 18 },
    faqHeaderIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    faqHeaderTitle: { fontSize: 18, fontWeight: '800' },
    searchWrap: { flexDirection: 'row', alignItems: 'center', borderRadius: 14, paddingHorizontal: 14, borderWidth: 1, marginBottom: 14 },
    searchInput: { flex: 1, paddingVertical: 12, marginLeft: 10, fontSize: 15 },
    chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 12 },
    chipText: { fontSize: 12, fontWeight: '600' },
    featureGrid: { gap: 12 },
    featureTile: { borderRadius: 14, borderWidth: 1, overflow: 'hidden', marginBottom: 2, minHeight: 176 },
    featureTileTop: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, paddingBottom: 10 },
    featureTileIcon: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    featureTileName: { fontSize: 14, fontWeight: '700' },
    featureTileDesc: { fontSize: 12, lineHeight: 18, paddingHorizontal: 14, paddingBottom: 12 },
    featureTileCta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderTopWidth: 1 },
    newBadge: { backgroundColor: colors.success, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    newBadgeText: { fontSize: 9, fontWeight: '800', color: colors.primaryText },
    proBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    proBadgeText: { fontSize: 9, fontWeight: '800' },
  });
  const { features, totalCount } = useFeatures();
  const displayCount = totalCount || filteredFeatures.length;
  const categoryMap = Object.fromEntries(
    Array.from(new Set((features || []).map((f) => f.category).filter(Boolean))).map((category) => {
      const first = (features || []).find((f) => f.category === category);
      return [
        category,
        {
          label: String(category).replace(/-/g, ' ').replace(/\b\w/g, (s) => s.toUpperCase()),
          color: first?.color || C.primary,
          icon: first?.icon || 'apps',
        },
      ];
    }),
  ) as Record<string, { label: string; color: string; icon: string }>;
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
      {/* Feature Index Header */}
      <View style={[s.faqHeader, { backgroundColor: C.card, borderColor: C.border }]} data-testid="feature-index-header" testID="feature-index-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <View style={[s.faqHeaderIcon, { backgroundColor: colors.infoSoft }]}> 
            <Ionicons name="apps" size={20} color={colors.info} />
          </View>
          <View>
            <Text style={[s.faqHeaderTitle, { color: C.text }]}>{tx('features.help.header.title', 'Feature Index')}</Text>
            <Text style={{ fontSize: 12, color: C.textMuted }}>{displayCount} {tx('features.help.header.countSuffix', 'AI copilots & mini-apps')}</Text>
          </View>
        </View>
        <Text style={{ fontSize: 13, color: C.textSec, lineHeight: 20 }}>
          {tx('features.help.header.subtitle', 'Enterprise catalog for every AI tool and mini-app. Use categories or search to quickly jump into any capability.')}
        </Text>
      </View>

      {/* Search */}
      <View style={[s.searchWrap, { backgroundColor: C.card, borderColor: C.border }]}>
        <Ionicons name="search" size={18} color={C.textMuted} />
        <TextInput data-testid="feature-search-input" testID="feature-search-input" style={[s.searchInput, { color: C.text }]}
          placeholder={tx('features.search.placeholder.fallback', 'Search features')} placeholderTextColor={C.textMuted}
          value={featureSearch} onChangeText={setFeatureSearch} />
        {featureSearch.length > 0 && (
          <TouchableOpacity data-testid="feature-search-clear" testID="feature-search-clear" onPress={() => setFeatureSearch('')}>
            <Ionicons name="close-circle" size={18} color={C.textMuted} />
          </TouchableOpacity>
        )}
      </View>

      {/* Category chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }} contentContainerStyle={{ gap: 8, paddingRight: 8 }}>
        <TouchableOpacity data-testid="feature-chip-all" testID="feature-chip-all" style={[s.chip, { backgroundColor: !featureCat ? C.primary : inactiveChipBg, borderWidth: 1, borderColor: !featureCat ? C.primary : inactiveChipBorder }]} onPress={() => setFeatureCat(null)}>
          <Ionicons name="apps" size={14} color={!featureCat ? selectedChipText : inactiveChipText} />
          <Text style={[s.chipText, { color: !featureCat ? selectedChipText : inactiveChipText }]}>{tx('features.category.all', 'All')} ({displayCount})</Text>
        </TouchableOpacity>
        {Object.entries(categoryMap).map(([key, meta]) => {
          const count = features.filter(f => f.category === key).length;
          if (count === 0) return null;
          return (
            <TouchableOpacity key={key} data-testid={`feature-chip-${key}`} testID={`feature-chip-${key}`}
              style={[s.chip, { backgroundColor: featureCat === key ? meta.color : inactiveChipBg, borderWidth: 1, borderColor: featureCat === key ? meta.color : inactiveChipBorder }]}
              onPress={() => setFeatureCat(featureCat === key ? null : key)}>
              <Ionicons name={meta.icon as any} size={14} color={featureCat === key ? selectedChipText : inactiveChipText} />
              <Text style={[s.chipText, { color: featureCat === key ? selectedChipText : inactiveChipText }]}>{meta.label} ({count})</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Feature Grid */}
      <View style={[s.featureGrid, isWide && { flexDirection: 'row', flexWrap: 'wrap' }]}>
        {filteredFeatures.map((feature) => {
          const catMeta = categoryMap[feature.category];
          return (
            <TouchableOpacity key={feature.id} data-testid={`feature-tile-${feature.id}`} testID={`feature-tile-${feature.id}`}
              style={[s.featureTile, { backgroundColor: C.bgSoft, borderColor: C.border }, isWide && { width: isTablet ? '48%' : '31.5%' }]}
              onPress={() => onFeaturePress(feature.route)} activeOpacity={0.7}>
              <View style={s.featureTileTop}>
                <View style={[s.featureTileIcon, { backgroundColor: (globalThis as any).__alphaColor(feature.color, '15') }]}>
                  <Ionicons name={feature.icon as any} size={20} color={feature.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.featureTileName, { color: C.text }]}>{feature.title}</Text>
                  {catMeta && <Text style={{ fontSize: 10, color: catMeta.color, fontWeight: '700', marginTop: 1 }}>{tx(`features.category.${feature.category}`, catMeta.label)}</Text>}
                </View>
                {feature.isNew && <View style={s.newBadge}><Text style={s.newBadgeText}>{tx('features.badge.new', 'NEW')}</Text></View>}
                {feature.premium && <View style={[s.proBadge, { backgroundColor: (globalThis as any).__alphaColor(C.warning, '20') }]}><Text style={[s.proBadgeText, { color: C.warningText }]}>{tx('features.badge.pro', 'PRO')}</Text></View>}
              </View>
              <Text style={[s.featureTileDesc, { color: C.textMuted }]}>{normalizeFeatureDescription(feature)}</Text>
              <View style={[s.featureTileCta, { borderTopColor: C.border }]}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>{tx('features.cta.open', 'Open')}</Text>
                <Ionicons name="arrow-forward" size={14} color={C.primary} />
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      {filteredFeatures.length === 0 && (
        <View style={{ alignItems: 'center', paddingVertical: 40 }} data-testid="feature-empty" testID="feature-empty">
          <Ionicons name="search-outline" size={40} color={C.textMuted} />
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginTop: 12 }}>{tx('features.empty.title', 'No features found')}</Text>
          <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4 }}>{tx('features.empty.subtitle', 'Try a different search term or category.')}</Text>
        </View>
      )}
    </ScrollView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
