import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Image, TextInput, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

export default function MFASettingsPanel({ colors: _colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth >= 768 && screenWidth < 1024;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: mfaStatus, loading, refetch: _checkStatus } = useLiveQuery('/auth/mfa/status', { pollInterval: 30000, entity: 'mfa' });
  const mfaEnabled = mfaStatus?.mfa_enabled || false;
  const [setupData, setSetupData] = useState<any>(null);
  const [code, setCode] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [step, setStep] = useState<'status' | 'setup' | 'verify' | 'complete' | 'disable'>('status');

  const startSetup = async () => {
    setError('');
    try {
      const res = await api.post('/auth/mfa/setup');
      setSetupData(res.data);
      setStep('setup');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to start MFA setup');
    }
  };

  const verifyCode = async () => {
    setError('');
    if (!code || code.length < 6) { setError('Enter a 6-digit code'); return; }
    try {
      const res = await api.post('/auth/mfa/verify', { code });
      setBackupCodes(res.data.backup_codes || []);
      setMfaEnabled(true);
      setStep('complete');
      setSuccess('MFA enabled successfully!');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Verification failed');
    }
  };

  const disableMFA = async () => {
    setError('');
    if (!disableCode || disableCode.length < 6) { setError('Enter your current TOTP code'); return; }
    try {
      await api.post('/auth/mfa/disable', { code: disableCode });
      setMfaEnabled(false);
      setStep('status');
      setDisableCode('');
      setSuccess('MFA has been disabled');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to disable MFA');
    }
  };

  if (loading) return <View style={{ padding: 20, alignItems: 'center' }}><ActivityIndicator color={'var(--app-primary)'} /></View>;

  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: 16, padding: isTablet ? 24 : 20, borderWidth: 1, borderColor: colors.border }} data-testid="mfa-settings-panel" testID="mfa-settings-panel" role="region" aria-label="MFA Settings">
      <AutoFixBanner domain="mfa" />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: mfaEnabled ? 'var(--app-success-soft)' : 'var(--app-warning-soft)', alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={mfaEnabled ? 'shield-checkmark' : 'shield-half'} size={18} color={mfaEnabled ? 'var(--app-success)' : 'var(--app-warning)'} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('admin.mFASettingsPanel.auto.text.001', 'Two-Factor Authentication')}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
            {mfaEnabled ? 'MFA is active — your account is protected' : 'Add an extra layer of security to your account'}
          </Text>
        </View>
        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: mfaEnabled ? 'var(--app-success-soft)' : 'var(--app-warning-soft)' }}>
          <Text style={{ fontSize: 10, fontWeight: '700', color: mfaEnabled ? 'var(--app-success)' : 'var(--app-warning)' }}>{mfaEnabled ? 'ENABLED' : 'DISABLED'}</Text>
        </View>
      </View>

      {error ? (
        <View style={{ backgroundColor: colors.errorSoft, borderRadius: 8, padding: 10, marginBottom: 12 }}>
          <Text style={{ color: colors.error, fontSize: 12, fontWeight: '600' }}>{error}</Text>
        </View>
      ) : null}

      {success ? (
        <View style={{ backgroundColor: colors.successSoft, borderRadius: 8, padding: 10, marginBottom: 12 }}>
          <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '600' }}>{success}</Text>
        </View>
      ) : null}

      {/* Status View */}
      {step === 'status' && !mfaEnabled && (
        <TouchableOpacity onPress={startSetup}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary }}
          data-testid="mfa-enable-btn" testID="mfa-enable-btn">
          <Ionicons name="key" size={16} color={colors.primaryText} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{tx('admin.mFASettingsPanel.auto.text.002', 'Enable MFA')}</Text>
        </TouchableOpacity>
      )}

      {step === 'status' && mfaEnabled && (
        <View>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 12 }}>{tx('admin.mFASettingsPanel.auto.text.003', 'Your account is secured with TOTP-based two-factor authentication.')}</Text>
          <TouchableOpacity onPress={() => { setStep('disable'); setError(''); setSuccess(''); }}
            style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: colors.errorSoft }}
            data-testid="mfa-disable-start-btn" testID="mfa-disable-start-btn">
            <Ionicons name="close-circle" size={16} color={'var(--app-error)'} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.error }}>{tx('admin.mFASettingsPanel.auto.text.004', 'Disable MFA')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Setup QR Code */}
      {step === 'setup' && setupData && (
        <View>
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text, marginBottom: 10 }}>{tx('admin.mFASettingsPanel.auto.text.005', '1. Scan this QR code with your authenticator app')}</Text>
          {setupData.qr_code && Platform.OS === 'web' && (
            <View style={{ alignItems: 'center', marginBottom: 14 }}>
              <Image source={{ uri: setupData.qr_code }} style={{ width: 180, height: 180, borderRadius: 12 }} data-testid="mfa-qr-code" testID="mfa-qr-code" accessibilityLabel={tx('admin.mFASettingsPanel.auto.accessibility.001', 'Manual entry key:')} />
            </View>
          )}
          <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 8, padding: 10, marginBottom: 14 }}>
            <Text style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4 }}>{tx('admin.mFASettingsPanel.auto.text.006', 'Manual entry key:')}</Text>
            <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text, fontFamily: 'monospace', letterSpacing: 2 }} selectable data-testid="mfa-secret" testID="mfa-secret">{setupData.secret}</Text>
          </View>
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('admin.mFASettingsPanel.auto.text.007', '2. Enter the 6-digit code from your app')}</Text>
          <TextInput
            value={code}
            onChangeText={(t) => { setCode(t.replace(/\D/g, '').slice(0, 6)); setError(''); }}
            placeholder="000000"
            placeholderTextColor={colors.textMuted}
            keyboardType="number-pad"
            maxLength={6}
            style={{ backgroundColor: colors.surfaceHover, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16, fontSize: 20, fontWeight: '700', color: colors.text, textAlign: 'center', letterSpacing: 8, borderWidth: 1, borderColor: colors.border, marginBottom: 14 }}
            data-testid="mfa-verify-input" testID="mfa-verify-input"
          />
          <TouchableOpacity onPress={verifyCode} disabled={code.length < 6}
            style={{ paddingVertical: 12, borderRadius: 10, backgroundColor: code.length >= 6 ? 'var(--app-primary)' : colors.border, alignItems: 'center' }}
            data-testid="mfa-verify-btn" testID="mfa-verify-btn">
            <Text style={{ fontSize: 14, fontWeight: '700', color: code.length >= 6 ? colors.primaryText : colors.textMuted }}>{tx('admin.mFASettingsPanel.auto.text.008', 'Verify & Enable')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Complete — Show Backup Codes */}
      {step === 'complete' && backupCodes.length > 0 && (
        <View>
          <View style={{ backgroundColor: colors.warningSoft, borderRadius: 10, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.warningSoft }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <Ionicons name="warning" size={16} color={'var(--app-warning)'} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: colors.warningText }}>{tx('admin.mFASettingsPanel.auto.text.009', 'Save Your Backup Codes')}</Text>
            </View>
            <Text style={{ fontSize: 11, color: colors.textMuted, lineHeight: 16 }}>{tx('admin.mFASettingsPanel.auto.text.010', 'These codes can be used to access your account if you lose your authenticator. Each code can only be used once.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {backupCodes.map((c, i) => (
              <View key={i} style={{ backgroundColor: colors.surfaceHover, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, borderWidth: 1, borderColor: colors.border }}>
                <Text selectable style={{ fontSize: 13, fontWeight: '700', color: colors.text, fontFamily: 'monospace' }} data-testid={`mfa-backup-${i}`} testID={`mfa-backup-${i}`}>{c}</Text>
              </View>
            ))}
          </View>
          <TouchableOpacity accessibilityLabel={tx('admin.mFASettingsPanel.auto.accessibility.002', 'Confirm backup codes saved')} onPress={() => { setStep('status'); setBackupCodes([]); setSuccess(''); }}
            style={{ paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primary, alignItems: 'center' }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primaryText }}>{tx('admin.mFASettingsPanel.auto.text.011', 'I\'ve Saved My Codes')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Disable MFA */}
      {step === 'disable' && (
        <View>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 12 }}>{tx('admin.mFASettingsPanel.auto.text.012', 'Enter your current authenticator code to disable MFA.')}</Text>
          <TextInput
            value={disableCode}
            onChangeText={(t) => { setDisableCode(t.replace(/\D/g, '').slice(0, 6)); setError(''); }}
            placeholder="000000"
            placeholderTextColor={colors.textMuted}
            keyboardType="number-pad"
            maxLength={6}
            style={{ backgroundColor: colors.surfaceHover, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16, fontSize: 20, fontWeight: '700', color: colors.text, textAlign: 'center', letterSpacing: 8, borderWidth: 1, borderColor: colors.border, marginBottom: 14 }}
            data-testid="mfa-disable-input" testID="mfa-disable-input"
          />
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <TouchableOpacity accessibilityLabel={tx('admin.mFASettingsPanel.auto.accessibility.003', 'Cancel')} onPress={() => { setStep('status'); setDisableCode(''); setError(''); }}
              style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.surface, alignItems: 'center', borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: colors.textSec }}>{tx('admin.mFASettingsPanel.auto.text.013', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={disableMFA} disabled={disableCode.length < 6}
              style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: disableCode.length >= 6 ? 'var(--app-error)' : colors.border, alignItems: 'center' }}
              data-testid="mfa-disable-confirm-btn" testID="mfa-disable-confirm-btn">
              <Text style={{ fontSize: 13, fontWeight: '700', color: disableCode.length >= 6 ? colors.primaryText : colors.textMuted }}>{tx('admin.mFASettingsPanel.auto.text.014', 'Disable MFA')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}
