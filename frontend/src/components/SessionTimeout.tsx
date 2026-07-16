import React, { useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, Modal, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useSessionRefresh } from '../hooks/useSessionRefresh';
import { notificationEvents } from '../utils/notificationEvents';

export default function SessionTimeout() {
  const { user, logout } = useAuth();
  const { colors } = useTheme();

  const handleSessionExpiry = useCallback(async () => {
    await logout();
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.href = '/auth/login';
    }
  }, [logout]);

  const {
    secondsRemaining,
    isWarningVisible,
    isCriticalVisible,
    refreshing,
    refreshError,
    refreshSession,
    dismissWarning,
    clearRefreshError,
  } = useSessionRefresh(user?.user_id || null, handleSessionExpiry);

  const handleLogout = useCallback(async () => {
    await logout();
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.href = '/auth/login';
    }
  }, [logout]);

  const handleStaySignedIn = useCallback(async () => {
    clearRefreshError();
    const refreshed = await refreshSession();
    if (refreshed) {
      notificationEvents.emit('toast', {
        title: 'Session extended',
        message: 'You are signed in and your timer has been refreshed.',
        type: 'success',
      });
      return;
    }
    notificationEvents.emit('toast', {
      title: 'Session refresh failed',
      message: 'Please try Stay Signed In again before the timer ends.',
      type: 'warning',
    });
  }, [refreshSession, clearRefreshError]);

  const formattedCountdown = useMemo(() => {
    const safeSeconds = Math.max(secondsRemaining ?? 0, 0);
    const mins = Math.floor(safeSeconds / 60);
    const secs = safeSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }, [secondsRemaining]);

  if (!user || (!isWarningVisible && !isCriticalVisible)) return null;

  return (
    <>
      {isWarningVisible && (
        <View
          style={{
            marginHorizontal: 16,
            marginTop: 10,
            marginBottom: 8,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: colors.warningSoft,
            backgroundColor: colors.warningSoft,
            paddingVertical: 12,
            paddingHorizontal: 14,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 10,
          }}
          data-testid="session-timeout-warning-banner" testID="session-timeout-warning-banner"
        >
          <Ionicons name="time-outline" size={20} color={colors.warningText} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }} data-testid="session-timeout-warning-title" testID="session-timeout-warning-title">
              Session expires in {formattedCountdown}
            </Text>
            <Text style={{ fontSize: 11, marginTop: 2, color: colors.textMuted }} data-testid="session-timeout-warning-subtitle" testID="session-timeout-warning-subtitle">
              Stay signed in now to keep working without interruption.
            </Text>
          </View>
          <TouchableOpacity accessibilityLabel="Session timeout stay signed in button"
            onPress={handleStaySignedIn}
            disabled={refreshing}
            style={{
              backgroundColor: colors.warning,
              borderRadius: 9,
              paddingVertical: 7,
              paddingHorizontal: 12,
              opacity: refreshing ? 0.65 : 1,
            }}
            data-testid="session-timeout-stay-signed-in-button" testID="session-timeout-stay-signed-in-button"
          >
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
              {refreshing ? 'Refreshing…' : 'Stay Signed In'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={dismissWarning} data-testid="session-timeout-banner-dismiss-button" testID="session-timeout-banner-dismiss-button">
            <Ionicons name="close" size={16} color={colors.textMuted} />
          </TouchableOpacity>
        </View>
      )}

      <Modal visible={isCriticalVisible} transparent animationType="fade" data-testid="session-timeout-critical-modal" testID="session-timeout-critical-modal">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
          <View style={{ backgroundColor: colors.card, borderRadius: 20, padding: 28, width: '100%', maxWidth: 390, alignItems: 'center', borderWidth: 1, borderColor: colors.border }}>
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Ionicons name="warning-outline" size={32} color={colors.error} />
            </View>
            <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 8 }} data-testid="session-timeout-critical-title" testID="session-timeout-critical-title">
              Session ending soon
            </Text>
            <Text style={{ fontSize: 14, color: colors.textMuted, textAlign: 'center', marginBottom: 18 }} data-testid="session-timeout-critical-description" testID="session-timeout-critical-description">
              For security, you will be signed out when this countdown reaches zero.
            </Text>
            <View style={{ backgroundColor: colors.errorSoft, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 24, marginBottom: 16, borderWidth: 1, borderColor: colors.errorSoft }}>
              <Text style={{ fontSize: 30, fontWeight: '800', color: colors.error, textAlign: 'center', fontVariant: ['tabular-nums'] }} data-testid="session-timeout-warning-countdown" testID="session-timeout-warning-countdown">
                {formattedCountdown}
              </Text>
            </View>

            {refreshError ? (
              <Text style={{ color: colors.error, fontSize: 12, marginBottom: 12, textAlign: 'center' }} data-testid="session-timeout-refresh-error" testID="session-timeout-refresh-error">
                {refreshError}
              </Text>
            ) : null}

            <View style={{ flexDirection: 'row', gap: 12, width: '100%' }}>
              <TouchableOpacity
                onPress={handleLogout}
                style={{ flex: 1, paddingVertical: 14, borderRadius: 12, backgroundColor: colors.border, alignItems: 'center' }}
                data-testid="session-timeout-sign-out-button" testID="session-timeout-sign-out-button"
              >
                <Text style={{ color: colors.text, fontWeight: '600', fontSize: 14 }}>Sign Out</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={handleStaySignedIn}
                disabled={refreshing}
                style={{ flex: 1, paddingVertical: 14, borderRadius: 12, backgroundColor: colors.primary, alignItems: 'center', opacity: refreshing ? 0.7 : 1 }}
                data-testid="session-timeout-modal-stay-signed-in-button" testID="session-timeout-modal-stay-signed-in-button"
              >
                <Text style={{ color: colors.primaryText || colors.buttonText || colors.text, fontWeight: '600', fontSize: 14 }}>
                  {refreshing ? 'Refreshing…' : 'Stay Signed In'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
