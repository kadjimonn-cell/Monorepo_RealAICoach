import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../hooks/useTranslation';

interface GlobalPlatformRouteStatusBannerProps {
  phase: 'C';
  routePath: string;
  clusterLabel: string;
  clusterId: string;
  recommendedLiveRoute: string;
  colors: any;
  compact?: boolean;
  onOpenVerifiedRoute: () => void;
}

const slugify = (value: string) =>
  String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'route';

export const GlobalPlatformRouteStatusBanner: React.FC<GlobalPlatformRouteStatusBannerProps> = ({
  phase,
  routePath,
  clusterLabel,
  clusterId,
  recommendedLiveRoute,
  colors,
  compact = false,
  onOpenVerifiedRoute,
}) => {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const accent = colors.info;
  const bannerId = slugify(`${phase}-${clusterId}-${routePath}`);

  return (
    <View
      style={{
        borderRadius: 12,
        borderWidth: 1,
        borderColor: accent,
        backgroundColor: `${accent}12`,
        paddingHorizontal: compact ? 10 : 12,
        paddingVertical: compact ? 9 : 11,
        gap: 6,
      }}
      data-testid={`global-route-phase-banner-${bannerId}`}
      testID={`global-route-phase-banner-${bannerId}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <View
          style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: `${accent}22` }}
          data-testid={`global-route-phase-badge-${bannerId}`}
          testID={`global-route-phase-badge-${bannerId}`}
        >
          <Text style={{ color: accent, fontSize: 10, fontWeight: '900' }}>
            PHASE C (SAFE MODE · E2E PENDING)
          </Text>
        </View>
        <Text
          style={{ color: colors.text, fontSize: compact ? 11 : 12, fontWeight: '800', flexShrink: 1 }}
          data-testid={`global-route-phase-title-${bannerId}`}
          testID={`global-route-phase-title-${bannerId}`}
        >
          {tx('globalRoutePolicy.phaseC.title', 'Route is live-wired but still pending route-level full E2E evidence tag.')}
        </Text>
      </View>

      <Text
        style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16 }}
        data-testid={`global-route-phase-context-${bannerId}`}
        testID={`global-route-phase-context-${bannerId}`}
      >
        {tx('globalRoutePolicy.context', 'Cluster')}: {clusterLabel} ({clusterId}) · {tx('globalRoutePolicy.route', 'Route')}: {routePath}
      </Text>

      <TouchableOpacity accessibilityLabel="On open verified route in global platform route status banner"
        onPress={onOpenVerifiedRoute}
        style={{
          alignSelf: 'flex-start',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 6,
          borderRadius: 9,
          borderWidth: 1,
          borderColor: colors.primary,
          backgroundColor: `${colors.primary}12`,
          paddingHorizontal: 10,
          paddingVertical: 7,
        }}
        data-testid={`global-route-open-verified-button-${bannerId}`}
        testID={`global-route-open-verified-button-${bannerId}`}
      >
        <Ionicons name="checkmark-done-circle" size={13} color={colors.primary} />
        <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>
          {tx('globalRoutePolicy.openVerified', 'Open verified live-data route')} → {recommendedLiveRoute}
        </Text>
      </TouchableOpacity>
    </View>
  );
};
