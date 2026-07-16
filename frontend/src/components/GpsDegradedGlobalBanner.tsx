import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useGlobalPlatformState } from '../hooks/useGlobalPlatformState';
import { useTranslation } from '../hooks/useTranslation';
import { shouldShowDiagnosticsBanners } from '../utils/diagnosticsVisibility';
import { useTheme } from '../context/ThemeContext';

export const GpsDegradedGlobalBanner = () => {
  const showDiagnosticsBanners = shouldShowDiagnosticsBanners();
  if (!showDiagnosticsBanners) return null;

  const { t } = useTranslation();
  const { colors } = useTheme();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const { gpsStatus, error, refetch, diagnostics } = useGlobalPlatformState();

  if (gpsStatus === 'healthy') return null;

  return (
    <View
      style={{
        marginHorizontal: 12,
        marginTop: 8,
        marginBottom: 6,
        borderWidth: 1,
        borderColor: colors.warning,
        backgroundColor: colors.warningSoft,
        borderRadius: 10,
        paddingHorizontal: 12,
        paddingVertical: 10,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
      }}
      data-testid="global-gps-degraded-banner"
      testID="global-gps-degraded-banner"
    >
      <Ionicons name="warning-outline" size={16} color={colors.warningText} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '800' }} data-testid="global-gps-degraded-banner-title" testID="global-gps-degraded-banner-title">
          {tx('globalGpsBanner.title', 'Platform is in degraded mode')}
        </Text>
        <Text style={{ color: colors.warningText, fontSize: 11, marginTop: 2 }} data-testid="global-gps-degraded-banner-message" testID="global-gps-degraded-banner-message">
          {error || tx('globalGpsBanner.message', 'Using fallback snapshot while GPS recovers.')}
        </Text>
        <Text style={{ color: colors.warningText, fontSize: 10, marginTop: 2 }} data-testid="global-gps-degraded-banner-last-success" testID="global-gps-degraded-banner-last-success">
          {tx('globalGpsBanner.lastSuccess', 'Last GPS success:')} {diagnostics?.lastSuccessAt || '—'}
        </Text>
      </View>
      <TouchableOpacity accessibilityLabel="Global gps degraded banner retry button"
        onPress={refetch}
        style={{
          backgroundColor: colors.warning,
          borderRadius: 8,
          paddingHorizontal: 10,
          paddingVertical: 7,
        }}
        data-testid="global-gps-degraded-banner-retry-button"
        testID="global-gps-degraded-banner-retry-button"
      >
        <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>
          {tx('globalGpsBanner.retryNow', 'Retry')}
        </Text>
      </TouchableOpacity>
    </View>
  );
};
