import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../../hooks/useTranslation';
import type { MergeHubDefinition, MergeLegacyTab } from '../../config/phaseBTabConsolidation';

interface TabMergeHubPanelProps {
  colors: any;
  hub: MergeHubDefinition;
  onOpenLegacyTab: (tab: MergeLegacyTab) => void;
}

const phaseTone = (phase: string, colors: any) => {
  if (phase === 'P0') return colors.error || 'var(--app-error)';
  if (phase === 'P1') return colors.warning || 'var(--app-warning)';
  return colors.info || colors.primary || 'var(--app-primary)';
};

export default function TabMergeHubPanel({ colors, hub, onOpenLegacyTab }: TabMergeHubPanelProps) {
  const { width } = useWindowDimensions();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const cardsPerRow = useMemo(() => {
    if (width >= 1440) return 4;
    if (width >= 1024) return 3;
    if (width >= 640) return 2;
    return 1;
  }, [width]);

  const tone = phaseTone(hub.phase, colors);

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 16,
        gap: 12,
      }}
      data-testid={`tab-merge-hub-panel-${hub.id}`}
      testID={`tab-merge-hub-panel-${hub.id}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name={hub.icon as any} size={16} color={colors.primary} />
            <Text
              style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}
              data-testid={`tab-merge-hub-title-${hub.id}`}
              testID={`tab-merge-hub-title-${hub.id}`}
            >
              {hub.label}
            </Text>
          </View>
          <Text
            style={{ color: colors.textMuted, fontSize: 12, marginTop: 6, lineHeight: 18 }}
            data-testid={`tab-merge-hub-description-${hub.id}`}
            testID={`tab-merge-hub-description-${hub.id}`}
          >
            {hub.description}
          </Text>
        </View>

        <View
          style={{
            borderRadius: 999,
            borderWidth: 1,
            borderColor: `${tone}66`,
            backgroundColor: `${tone}16`,
            paddingHorizontal: 10,
            paddingVertical: 5,
          }}
          data-testid={`tab-merge-hub-phase-pill-${hub.id}`}
          testID={`tab-merge-hub-phase-pill-${hub.id}`}
        >
          <Text style={{ color: tone, fontSize: 10, fontWeight: '800' }}>{hub.phase}</Text>
        </View>
      </View>

      <Text
        style={{ color: colors.textSec || colors.textMuted, fontSize: 11, fontWeight: '700' }}
        data-testid={`tab-merge-hub-links-title-${hub.id}`}
        testID={`tab-merge-hub-links-title-${hub.id}`}
      >
        {tx('operationsConsole.mergeHub.linksTitle', 'Modules consolidated in this hub')}
      </Text>

      <View
        style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}
        data-testid={`tab-merge-hub-links-grid-${hub.id}`}
        testID={`tab-merge-hub-links-grid-${hub.id}`}
      >
        {hub.legacyTabs.map((tab, index) => (
          <TouchableOpacity accessibilityLabel="On open legacy tab in tab merge hub panel"
            key={`${hub.id}-${tab.id}`}
            onPress={() => onOpenLegacyTab(tab)}
            style={{
              width: cardsPerRow === 1 ? '100%' : cardsPerRow === 2 ? '48%' : cardsPerRow === 3 ? '31%' : '23%',
              minWidth: 210,
              flexGrow: 1,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.bg,
              paddingHorizontal: 12,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
            }}
            data-testid={`tab-merge-hub-open-${hub.id}-${tab.id}`}
            testID={`tab-merge-hub-open-${hub.id}-${tab.id}`}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
              <Ionicons name={tab.icon as any} size={14} color={colors.primary} />
              <Text numberOfLines={1} style={{ color: colors.text, fontSize: 12, fontWeight: '700', flexShrink: 1 }}>
                {tab.label}
              </Text>
            </View>
            <Ionicons name="arrow-forward" size={13} color={colors.textMuted} />
          </TouchableOpacity>
        ))}
      </View>

      <Text
        style={{ color: colors.textMuted, fontSize: 10 }}
        data-testid={`tab-merge-hub-footer-${hub.id}`}
        testID={`tab-merge-hub-footer-${hub.id}`}
      >
        {tx('operationsConsole.mergeHub.footerHint', 'Legacy module routes remain available and mapped under this consolidated hub.')}
      </Text>
    </View>
  );
}
