import React from 'react';
import { ActivityIndicator, Modal, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SegmentedOtpInput } from './SegmentedOtpInput';

type LoginTwoFactorModalProps = { ctx: any };

export function LoginTwoFactorModal({ ctx }: LoginTwoFactorModalProps) {
  const {
    show2FA, s, blur, T, otpHint, tx, error, otpCode, setOtpCode, loading, colors, handle2FAVerify, handleResendOTP, resending, setShow2FA, setError, setPendingAuthPassword
  } = ctx;

  return (
    <>
      {/* ─── 2FA Modal ─── */}
      <Modal visible={show2FA} transparent animationType="fade" testID="2fa-modal">
        <View style={s.modalOverlay} data-testid="2fa-modal-overlay" testID="2fa-modal-overlay">
          <View style={[s.modalCard, blur]} data-testid="2fa-modal-card" testID="2fa-modal-card">
            <View style={{ alignItems: 'center', marginBottom: 24 }} data-testid="2fa-modal-header" testID="2fa-modal-header">
              <View style={s.modalIconWrap} data-testid="2fa-modal-icon" testID="2fa-modal-icon">
                <Ionicons name="shield-checkmark" size={28} color={T.cyan} />
              </View>
              <Text style={s.modalTitle} data-testid="2fa-modal-title" testID="2fa-modal-title">Two-Factor Authentication</Text>
              <Text style={s.modalSub} data-testid="2fa-modal-subtitle" testID="2fa-modal-subtitle">Enter the 8-digit verification code</Text>
            </View>

            <View style={s.otpDisplay} data-testid="2fa-otp-display" testID="2fa-otp-display">
              <Text style={{ fontSize: 13, color: T.text2, textAlign: 'center' }} data-testid="2fa-otp-message" testID="2fa-otp-message">
                {otpHint || tx('login.otp.checkEmailCode', 'Check your email for the 8-digit verification code.')}
              </Text>
              <Text style={{ fontSize: 10, color: T.text3, textAlign: 'center', marginTop: 6 }} data-testid="2fa-otp-expiry-note" testID="2fa-otp-expiry-note">
                {tx('login.otp.codeExpiresInTenMinutes', 'Code expires in about 10 minutes')}
              </Text>
            </View>

            {error ? (
              <View style={[s.errBox, { marginBottom: 12 }]} data-testid="2fa-error-box" testID="2fa-error-box">
                <Ionicons name="alert-circle" size={14} color={T.error} />
                <Text style={s.errText} data-testid="2fa-error-text" testID="2fa-error-text">{error}</Text>
              </View>
            ) : null}

            <SegmentedOtpInput
              length={8}
              value={otpCode}
              onChange={(val) => setOtpCode(val)}
              autoFocus
              testIdPrefix="2fa"
              themeTokens={T}
            />

            <TouchableOpacity className="login-btn-primary" style={s.primaryBtn} onPress={handle2FAVerify} disabled={loading} data-testid="2fa-verify-button" testID="2fa-verify-button" accessibilityRole="button">
              {loading ? <ActivityIndicator color={colors.primaryText} /> : <Text style={s.primaryBtnText}>VERIFY & SIGN IN</Text>}
            </TouchableOpacity>

            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 20, marginTop: 18 }}>
              <TouchableOpacity onPress={handleResendOTP} disabled={resending} data-testid="2fa-resend-button" testID="2fa-resend-button" accessibilityRole="button">
                <Text style={{ color: T.cyan, fontSize: 13, fontWeight: '600' }}>{resending ? 'Sending...' : 'Resend Code'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { setShow2FA(false); setOtpCode(''); setError(''); setPendingAuthPassword(''); }} accessibilityRole="button" data-testid="2fa-cancel-button" testID="2fa-cancel-button">
                <Text style={{ color: T.text2, fontSize: 13 }}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
