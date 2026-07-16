import React, { useEffect, useMemo, useState } from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../hooks/useTranslation';
import { shouldShowDiagnosticsBanners } from '../utils/diagnosticsVisibility';
import { useTheme } from '../context/ThemeContext';

type Diagnostics = {
  lastAttemptAt?: string | null;
  lastSuccessAt?: string | null;
  lastErrorAt?: string | null;
  nextRetryAt?: number | null;
  gpsEndpoint?: string;
};

type Props = {
  surfaceName: string;
  loading: boolean;
  error?: string | null;
  onRetry: () => void;
  colors: {
    bg: string;
    card?: string;
    text: string;
    textSec?: string;
    textMuted?: string;
    border?: string;
    borderSoft?: string;
    primary: string;
    primaryText?: string;
    error?: string;
    success?: string;
    warning?: string;
  };
  diagnostics?: Diagnostics;
  testIdPrefix: string;
};

function formatIso(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

export const GpsDataStatusCard = ({
  surfaceName,
  loading,
  error,
  onRetry,
  colors,
  diagnostics,
  testIdPrefix,
}: Props) => {
  const { colors: themeColors } = useTheme();
  const showDiagnosticsBanners = shouldShowDiagnosticsBanners();
  if (!showDiagnosticsBanners) return null;

  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [nowMs, setNowMs] = useState<number>(Date.now());

  useEffect(() => {
    if (!diagnostics?.nextRetryAt) return;
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [diagnostics?.nextRetryAt]);

  const retrySeconds = useMemo(() => {
    if (!diagnostics?.nextRetryAt) return null;
    return Math.max(0, Math.ceil((diagnostics.nextRetryAt - nowMs) / 1000));
  }, [diagnostics?.nextRetryAt, nowMs]);

  let statusLabel = tx('gpsStatusCard.status.healthy', 'Healthy');
  let statusColor = colors.success || colors.primary;
  let subtitle = tx('gpsStatusCard.subtitleHealthyWithSurface', '{surface} is synced with live GlobalPlatformState data.').replace('{surface}', surfaceName);

  if (loading) {
    statusLabel = tx('gpsStatusCard.status.loading', 'Loading');
    statusColor = colors.warning || colors.primary;
    subtitle = tx('gpsStatusCard.subtitleLoadingWithSurface', '{surface} is waiting for GPS readiness.').replace('{surface}', surfaceName);
  } else if (error) {
    statusLabel = tx('gpsStatusCard.status.degraded', 'Degraded');
    statusColor = colors.error || colors.primary;
    subtitle = tx('gpsStatusCard.subtitleDegradedWithSurface', '{surface} is running in degraded mode with fallback data.').replace('{surface}', surfaceName);
  }

  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: colors.borderSoft || colors.border || themeColors.border || colors.primary,
        borderRadius: 14,
        backgroundColor: colors.card || colors.bg || themeColors.card,
        padding: 16,
      }}
      data-testid={`${testIdPrefix}-gps-status-card`}
      testID={`${testIdPrefix}-gps-status-card`}
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <View style={{ flex: 1 }}>
          <Text
            style={{ color: colors.text, fontSize: 18, fontWeight: '900' }}
            data-testid={`${testIdPrefix}-gps-status-title`}
            testID={`${testIdPrefix}-gps-status-title`}
          >
            {tx('gpsStatusCard.title', 'Global Platform Data Status')}
          </Text>
          <Text
            style={{ color: colors.textSec || colors.text, fontSize: 12, marginTop: 6, lineHeight: 18 }}
            data-testid={`${testIdPrefix}-gps-status-subtitle`}
            testID={`${testIdPrefix}-gps-status-subtitle`}
          >
            {subtitle}
          </Text>
        </View>
        <View style={{ borderWidth: 1, borderColor: statusColor, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`${testIdPrefix}-gps-status-pill`} testID={`${testIdPrefix}-gps-status-pill`}>
          <Text style={{ color: statusColor, fontSize: 10, fontWeight: '800' }}>{statusLabel.toUpperCase()}</Text>
        </View>
      </View>

      <View style={{ marginTop: 12, borderWidth: 1, borderColor: colors.border || colors.primary, borderRadius: 10, padding: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name={loading ? 'sync-outline' : error ? 'warning-outline' : 'checkmark-circle-outline'} size={14} color={statusColor} />
          <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }} data-testid={`${testIdPrefix}-gps-status-message`} testID={`${testIdPrefix}-gps-status-message`}>
            {loading
              ? tx('gpsStatusCard.loadingMessage', 'Fetching Global Platform State...')
              : error
                ? tx('gpsStatusCard.errorMessage', 'Unable to load GPS data. Automatic retry is active.')
                : tx('gpsStatusCard.healthyMessage', 'GPS data is healthy.')}
          </Text>
        </View>
        {error ? (
          <Text style={{ color: colors.textMuted || colors.textSec || colors.text, fontSize: 11, marginTop: 8 }} data-testid={`${testIdPrefix}-gps-status-error-text`} testID={`${testIdPrefix}-gps-status-error-text`}>
            {error}
          </Text>
        ) : null}
      </View>

      <View style={{ marginTop: 10, gap: 5 }}>
        <Text style={{ color: colors.textMuted || colors.textSec || colors.text, fontSize: 11 }} data-testid={`${testIdPrefix}-gps-status-last-attempt`} testID={`${testIdPrefix}-gps-status-last-attempt`}>
          {tx('gpsStatusCard.lastAttemptWithValue', 'Last attempt: {value}').replace('{value}', formatIso(diagnostics?.lastAttemptAt))}
        </Text>
        <Text style={{ color: colors.textMuted || colors.textSec || colors.text, fontSize: 11 }} data-testid={`${testIdPrefix}-gps-status-last-success`} testID={`${testIdPrefix}-gps-status-last-success`}>
          {tx('gpsStatusCard.lastSuccessWithValue', 'Last success: {value}').replace('{value}', formatIso(diagnostics?.lastSuccessAt))}
        </Text>
        <Text style={{ color: colors.textMuted || colors.textSec || colors.text, fontSize: 11 }} data-testid={`${testIdPrefix}-gps-status-endpoint`} testID={`${testIdPrefix}-gps-status-endpoint`}>
          {tx('gpsStatusCard.endpointWithValue', 'Endpoint: {value}').replace('{value}', diagnostics?.gpsEndpoint || '—')}
        </Text>
        {retrySeconds !== null ? (
          <Text style={{ color: colors.textMuted || colors.textSec || colors.text, fontSize: 11 }} data-testid={`${testIdPrefix}-gps-status-retry-countdown`} testID={`${testIdPrefix}-gps-status-retry-countdown`}>
            {tx('gpsStatusCard.nextRetryWithSeconds', 'Next automatic retry in {seconds}s').replace('{seconds}', String(retrySeconds))}
          </Text>
        ) : null}
      </View>

      <View style={{ marginTop: 12, flexDirection: 'row', justifyContent: 'flex-start' }}>
        <TouchableOpacity
          onPress={onRetry}
          style={{ backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}
          data-testid={`${testIdPrefix}-gps-status-retry-button`}
          testID={`${testIdPrefix}-gps-status-retry-button`}
        >
          <Text style={{ color: colors.primaryText || colors.text, fontSize: 11, fontWeight: '800' }}>
            {tx('gpsStatusCard.retryNow', 'Retry now')}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};
