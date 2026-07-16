import React from 'react';
import { Modal, View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { Ionicons } from '@expo/vector-icons';

// Soft error tint for the icon badge — ties to danger action on the modal.
// Theme-exempt by design (alpha-tinted brand red).
const SIGNOUT_DANGER_TINT = 'var(--app-error-soft)';

type Props = {
  visible: boolean;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  darkMode?: boolean;
  testIdPrefix?: string;
};

export default function EnterpriseSignOutConfirmModal({
  visible,
  loading = false,
  onCancel,
  onConfirm,
  darkMode: darkModeOverride,
  testIdPrefix = 'signout',
}: Props) {
  const { colors, darkMode: themeDarkMode } = useTheme();
  const { t } = useTranslation();
  // Default: follow the app's current theme. A caller may override via prop
  // (e.g., a sign-in-page variant that wants to force dark), but the norm
  // is to render in whichever mode the user has selected.
  const darkMode = darkModeOverride ?? themeDarkMode;
  const palette = darkMode
    ? {
        overlay: 'rgba(2, 6, 23, 0.78)',
        card: colors.surfaceElevated,
        border: colors.borderStrong,
        text: colors.text,
        muted: colors.textMuted,
        dangerBg: colors.error,
        dangerBorder: colors.errorSoft,
        dangerText: colors.primaryText,
        neutralBg: colors.surface,
        neutralBorder: colors.borderStrong,
      }
    : {
        overlay: 'rgba(15, 23, 42, 0.45)',
        card: colors.surface,
        border: colors.border,
        text: colors.text,
        muted: colors.textMuted,
        dangerBg: colors.error,
        dangerBorder: colors.errorSoft,
        dangerText: colors.primaryText,
        neutralBg: colors.surfaceHover,
        neutralBorder: colors.border,
      };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onCancel}
      data-testid={`${testIdPrefix}-confirm-modal`}
      testID={`${testIdPrefix}-confirm-modal`}
    >
      <View
        style={{
          flex: 1,
          backgroundColor: palette.overlay,
          alignItems: 'center',
          justifyContent: 'center',
          paddingHorizontal: 18,
          ...(Platform.OS === 'web' ? { position: 'fixed' as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999 } : {}),
        }}
        data-testid={`${testIdPrefix}-confirm-overlay`}
        testID={`${testIdPrefix}-confirm-overlay`}
      >
        <View
          style={{
            width: '100%',
            maxWidth: 430,
            borderRadius: 18,
            backgroundColor: palette.card,
            borderWidth: 1,
            borderColor: palette.border,
            padding: 18,
            shadowColor: 'var(--app-text)',
            shadowOpacity: Platform.OS === 'web' ? 0.2 : 0.28,
            shadowRadius: 22,
            shadowOffset: { width: 0, height: 10 },
            elevation: 10,
          }}
          data-testid={`${testIdPrefix}-confirm-card`}
          testID={`${testIdPrefix}-confirm-card`}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: SIGNOUT_DANGER_TINT,
                borderWidth: 1,
                borderColor: SIGNOUT_DANGER_TINT,
              }}
            >
              <Ionicons name="log-out-outline" size={18} color={'var(--app-error)'} />
            </View>
            <View style={{ flex: 1 }}>
              <Text
                style={{ color: palette.text, fontSize: 17, fontWeight: '900', letterSpacing: -0.2 }}
                data-testid={`${testIdPrefix}-confirm-title`}
                testID={`${testIdPrefix}-confirm-title`}
              >
                {t('signoutConfirm.title')}
              </Text>
              <Text
                style={{ color: palette.muted, fontSize: 12, marginTop: 3, lineHeight: 18 }}
                data-testid={`${testIdPrefix}-confirm-subtitle`}
                testID={`${testIdPrefix}-confirm-subtitle`}
              >
                {t('signoutConfirm.subtitle')}
              </Text>
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
            <TouchableOpacity accessibilityLabel="On cancel in enterprise sign out confirm modal button"
              onPress={onCancel}
              disabled={loading}
              style={{
                flex: 1,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: palette.neutralBorder,
                backgroundColor: palette.neutralBg,
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: 42,
                opacity: loading ? 0.6 : 1,
              }}
              data-testid={`${testIdPrefix}-confirm-no-btn`}
              testID={`${testIdPrefix}-confirm-no-btn`}
            >
              <Text style={{ color: palette.text, fontSize: 12, fontWeight: '800' }}>{t('signoutConfirm.stay')}</Text>
            </TouchableOpacity>

            <TouchableOpacity accessibilityLabel="On confirm in enterprise sign out confirm modal button"
              onPress={onConfirm}
              disabled={loading}
              style={{
                flex: 1,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: palette.dangerBorder,
                backgroundColor: palette.dangerBg,
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: 42,
                opacity: loading ? 0.85 : 1,
              }}
              data-testid={`${testIdPrefix}-confirm-yes-btn`}
              testID={`${testIdPrefix}-confirm-yes-btn`}
            >
              {loading ? (
                <ActivityIndicator size="small" color={palette.dangerText} />
              ) : (
                <Text style={{ color: palette.dangerText, fontSize: 12, fontWeight: '900' }}>{t('signoutConfirm.confirm')}</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

/* i18n-probe t('i18n.auto.probe') */
