/**
 * InvitationQRModal
 * ─────────────────
 * Small centered modal that shows a QR code for a pending invitation URL.
 * Admin can scan with a phone camera to share the signup link in-person.
 */
import React from 'react';
import { Platform, Text, TouchableOpacity, View, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// react-qr-code is a pure-SVG component that works on RN Web.
 
import QRCode from 'react-qr-code';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

interface Props {
  visible: boolean;
  url: string;
  email: string;
  role: string;
  onClose: () => void;
  onCopy?: () => void;
}

export default function InvitationQRModal({ visible, url, email, role, onClose, onCopy }: Props) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View
        style={{ flex: 1, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center', padding: 20 }}
        data-testid="invitation-qr-modal" testID="invitation-qr-modal"
      >
        <View
          style={{
            width: '100%', maxWidth: 380,
            borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
            padding: 22,
          }}
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 }}>
                {tx('admin.invitationQr.title', 'Invitation QR')}
              </Text>
              <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', marginTop: 4, letterSpacing: -0.3 }}>
                {tx('admin.invitationQr.subtitle', 'Scan to accept')}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 2 }} numberOfLines={1}>
                {email} · {role}
              </Text>
            </View>
            <TouchableOpacity
              onPress={onClose}
              data-testid="invitation-qr-close-button" testID="invitation-qr-close-button"
              style={{ padding: 4 }}
            >
              <Ionicons name="close" size={20} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          <View
            style={{
              backgroundColor: colors.primaryText,
              borderRadius: 12,
              padding: 18,
              alignItems: 'center',
              justifyContent: 'center',
              alignSelf: 'center',
            }}
            data-testid="invitation-qr-canvas" testID="invitation-qr-canvas"
          >
            {Platform.OS === 'web' && url ? (
              // @ts-ignore — react-qr-code renders SVG, valid in RN Web
              <QRCode value={url} size={220} level="M" />
            ) : (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.invitationQr.states.previewUnavailable', 'QR preview unavailable')}</Text>
            )}
          </View>

          <Text
            style={{ color: colors.textMuted, fontSize: 10, marginTop: 12, textAlign: 'center', fontFamily: Platform.OS === 'web' ? ('ui-monospace, Menlo, monospace' as any) : undefined }}
            numberOfLines={2}
            data-testid="invitation-qr-url" testID="invitation-qr-url"
          >
            {url}
          </Text>

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 16 }}>
            {onCopy ? (
              <TouchableOpacity
                onPress={onCopy}
                data-testid="invitation-qr-copy-button" testID="invitation-qr-copy-button"
                style={{
                  flex: 1, borderRadius: 8, borderWidth: 1, borderColor: colors.border,
                  backgroundColor: colors.bg, paddingVertical: 10, flexDirection: 'row',
                  alignItems: 'center', justifyContent: 'center', gap: 6,
                }}
              >
                <Ionicons name="copy-outline" size={13} color={colors.textSec} />
                <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{tx('admin.invitationQr.actions.copyLink', 'Copy link')}</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity
              onPress={onClose}
              data-testid="invitation-qr-done-button" testID="invitation-qr-done-button"
              style={{
                flex: 1, borderRadius: 8, backgroundColor: colors.primary,
                paddingVertical: 10, alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{tx('admin.invitationQr.actions.done', 'Done')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
