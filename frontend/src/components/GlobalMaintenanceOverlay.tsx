import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { fetchPlatformControlPublicState } from '../services/platformControl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

function formatCountdown(seconds: number | null) {
  if (seconds == null || Number.isNaN(seconds) || seconds < 0) return null;
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export const GlobalMaintenanceOverlay = () => {
  const router = useRouter();
  const { user } = useAuth();
  const { colors } = useTheme();

  const [publicState, setPublicState] = useState<Record<string, any> | null>(null);
  const [eventPayload, setEventPayload] = useState<Record<string, any> | null>(null);
  const [countdownSeconds, setCountdownSeconds] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadPublicState = useCallback(async () => {
    try {
      const data = await fetchPlatformControlPublicState();
      setPublicState(data || null);
      if (!data?.is_blocking) {
        setEventPayload(null);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/GlobalMaintenanceOverlay.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => {
    loadPublicState();
    const interval = setInterval(loadPublicState, 20000);
    return () => clearInterval(interval);
  }, [loadPublicState]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handler = (event: Event) => {
      const payload = (event as CustomEvent)?.detail || null;
      if (payload) setEventPayload(payload);
    };
    window.addEventListener('app-platform-control-blocked', handler as EventListener);
    return () => window.removeEventListener('app-platform-control-blocked', handler as EventListener);
  }, []);

  const isAdmin = Boolean(user?.is_admin);
  const isStaff = !isAdmin && Boolean((user as any)?.employee_permissions?.length);

  const mergedPayload = useMemo(() => {
    if (eventPayload?.code?.startsWith?.('PLATFORM_')) return eventPayload;
    if (publicState?.gate_payload) return publicState.gate_payload;
    return null;
  }, [eventPayload, publicState]);

  const activeMode = String(mergedPayload?.active_mode || publicState?.active_mode || 'ONLINE').toUpperCase();
  const isBlocking = Boolean(publicState?.is_blocking) || activeMode === 'MAINTENANCE' || activeMode === 'EMERGENCY_SHUTDOWN';
  const staffReadOnlyAllowed = Boolean(publicState?.maintenance?.allow_staff_read_only);
  const showStaffBanner = !isAdmin && isStaff && isBlocking && staffReadOnlyAllowed;
  const showOverlay = !isAdmin && isBlocking && !showStaffBanner;

  useEffect(() => {
    const endsAtRaw = mergedPayload?.ends_at || publicState?.maintenance?.ends_at;
    if (!endsAtRaw) {
      setCountdownSeconds(null);
      return;
    }

    const targetMs = new Date(String(endsAtRaw)).getTime();
    if (!Number.isFinite(targetMs)) {
      setCountdownSeconds(null);
      return;
    }

    const tick = () => {
      const remaining = Math.max(0, Math.floor((targetMs - Date.now()) / 1000));
      setCountdownSeconds(remaining);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [mergedPayload?.ends_at, publicState?.maintenance?.ends_at]);

  if (!showOverlay && !showStaffBanner) return null;

  const title = String(mergedPayload?.title || (activeMode === 'EMERGENCY_SHUTDOWN' ? 'Emergency Shutdown Active' : 'Platform Maintenance Active'));
  const reason = String(
    mergedPayload?.reason
    || publicState?.maintenance?.reason
    || publicState?.emergency_shutdown?.reason
    || 'We are currently performing platform operations. Please check back shortly.'
  );
  const countdownText = formatCountdown(countdownSeconds);
  const tone = activeMode === 'EMERGENCY_SHUTDOWN' ? colors.error : colors.warningText;

  if (showStaffBanner) {
    return (
      <View
        style={{
          position: 'absolute',
          left: 12,
          right: 12,
          top: 12,
          zIndex: 2400,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: `${tone}66`,
          backgroundColor: `${tone}1A`,
          paddingHorizontal: 12,
          paddingVertical: 10,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
        }}
        data-testid="platform-control-staff-banner"
        testID="platform-control-staff-banner"
      >
        <Text style={{ color: tone, fontSize: 12, fontWeight: '800', flex: 1 }} data-testid="platform-control-staff-banner-text" testID="platform-control-staff-banner-text">
          Maintenance active: Staff read-only access allowed.
        </Text>
        <TouchableOpacity
          onPress={() => router.push('/system-status' as any)}
          data-testid="platform-control-staff-banner-status-button"
          testID="platform-control-staff-banner-status-button"
        >
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Status</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: 0,
        bottom: 0,
        zIndex: 2600,
        backgroundColor: 'rgba(4,10,24,0.82)',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 20,
      }}
      data-testid="global-maintenance-overlay"
      testID="global-maintenance-overlay"
    >
      <View
        style={{
          width: '100%',
          maxWidth: 580,
          borderRadius: 20,
          borderWidth: 1,
          borderColor: `${tone}55`,
          backgroundColor: colors.card,
          padding: 22,
          gap: 12,
        }}
        data-testid="global-maintenance-overlay-card"
        testID="global-maintenance-overlay-card"
      >
        <Text style={{ color: tone, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' }} data-testid="global-maintenance-mode-label" testID="global-maintenance-mode-label">
          {activeMode}
        </Text>
        <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800' }} data-testid="global-maintenance-title" testID="global-maintenance-title">
          {title}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 13, lineHeight: 20 }} data-testid="global-maintenance-reason" testID="global-maintenance-reason">
          {reason}
        </Text>

        {countdownText ? (
          <View
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: `${colors.primary}55`,
              backgroundColor: `${colors.primary}16`,
              paddingHorizontal: 12,
              paddingVertical: 10,
            }}
            data-testid="global-maintenance-countdown-box"
            testID="global-maintenance-countdown-box"
          >
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>Estimated time remaining</Text>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900', marginTop: 2 }} data-testid="global-maintenance-countdown" testID="global-maintenance-countdown">
              {countdownText}
            </Text>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <TouchableOpacity accessibilityLabel="Global maintenance retry button"
            style={{
              borderRadius: 999,
              backgroundColor: colors.primary,
              paddingHorizontal: 14,
              paddingVertical: 10,
              minWidth: 130,
              alignItems: 'center',
              justifyContent: 'center',
              opacity: refreshing ? 0.7 : 1,
            }}
            onPress={async () => {
              setRefreshing(true);
              await loadPublicState();
              setRefreshing(false);
            }}
            disabled={refreshing}
            data-testid="global-maintenance-retry-button"
            testID="global-maintenance-retry-button"
          >
            {refreshing ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>Retry now</Text>}
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Global maintenance status page button"
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.bgSoft,
              paddingHorizontal: 14,
              paddingVertical: 10,
              minWidth: 130,
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onPress={() => router.push('/system-status' as any)}
            data-testid="global-maintenance-status-page-button"
            testID="global-maintenance-status-page-button"
          >
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>View status page</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
