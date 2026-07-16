import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Switch,
  Alert,
  ActivityIndicator,
  Modal,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Redirect, useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import api from '../src/services/api';
import { useAutoRefresh } from '../src/hooks/useAutoRefresh';
import { useAutoSave } from '../src/hooks/useAutoSave';
import { useTheme } from '../src/context/ThemeContext';
import * as LocalAuthentication from 'expo-local-authentication';
import TrustedDevicesPanel from '../src/components/admin/TrustedDevicesPanel';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import {
  isPasskeySupportedOnWeb,
  normalizeRegistrationOptions,
  serializeWebAuthnCredential,
} from '../src/utils/webauthn';

const staticColors = {
  success: '#10B981', // @theme-ok brand/role/state identifier
  warning: '#F59E0B', // @theme-ok brand/role/state identifier
  error: '#EF4444', // @theme-ok brand/role/state identifier
};

export default function PrivacySecurityScreen() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  }, [t]);

  const COLORS = useMemo(() => ({
    ...staticColors,
    primary: colors.primary,
    primaryLight: colors.primary + '20',
    background: colors.bg,
    surface: colors.card,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  
  // Password change state
  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showPinModal, setShowPinModal] = useState(false);
  const [pinInput, setPinInput] = useState('');
  
  // Security settings
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const [loginAlerts, setLoginAlerts] = useState(true);
  const [backupCodesRemaining, setBackupCodesRemaining] = useState(0);
  const [showBackupCodes, setShowBackupCodes] = useState(false);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [twoFaLoading, setTwoFaLoading] = useState(false);
  const [loginHistory, setLoginHistory] = useState<any[]>([]);
  const [showLoginHistory, setShowLoginHistory] = useState(false);
  const [show2FAConfirm, setShow2FAConfirm] = useState(false);
  
  // Privacy settings
  const [profileVisible, setProfileVisible] = useState(true);
  const [activityVisible, setActivityVisible] = useState(false);
  const [dataCollection, setDataCollection] = useState(true);
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  // Load saved settings from backend
  React.useEffect(() => {
    if (user?.user_id) {
      // Load general security settings
      api.get(`/security/settings/${user.user_id}`)
        .then(res => {
          const s = res.data;
          setBiometricEnabled(s.biometric_enabled ?? false);
          setLoginAlerts(s.login_alerts ?? true);
          setProfileVisible(s.profile_visible ?? true);
          setActivityVisible(s.activity_visible ?? false);
          setDataCollection(s.data_collection ?? true);
          setSettingsLoaded(true);
        })
        .catch((error) => {
          handleAppRecoverableError({
            scope: 'privacy-security.load-settings',
            error,
            message: 'Could not load security settings right now.',
            onRetry: () => { if (user?.user_id) { void api.get(`/security/settings/${user.user_id}`); } },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
          setSettingsLoaded(true);
        });

      // Load 2FA status from auth endpoint
      api.get('/auth/2fa/status')
        .then(res => {
          setTwoFactorEnabled(res.data.two_fa_enabled ?? false);
          setBackupCodesRemaining(res.data.backup_codes_remaining ?? 0);
          setBiometricEnabled(res.data.biometric_enabled ?? false);
        })
        .catch((error) => {
          handleAppRecoverableError({
            scope: 'privacy-security.load-2fa-status',
            error,
            message: 'Could not load 2FA status right now.',
          
        notifyMode: 'silent',
      });
        });
    }
  }, [user?.user_id]);

  // Auto-save security preferences
  const securityPrefs = React.useMemo(() => ({
    biometric_enabled: biometricEnabled,
    login_alerts: loginAlerts,
  }), [biometricEnabled, loginAlerts]);
  useAutoSave(user?.user_id ? `/security/settings/${user.user_id}` : '', securityPrefs, { enabled: !!user?.user_id && settingsLoaded, method: 'put' });

  // Auto-refresh security settings every 30s
  useAutoRefresh(() => {
    if (!user?.user_id) return;
    api.get(`/security/settings/${user.user_id}`).then(res => {
      const s = res.data;
      setBiometricEnabled(s.biometric_enabled ?? false);
      setLoginAlerts(s.login_alerts ?? true);
    }).catch((error) => {
      handleAppRecoverableError({
        scope: 'privacy-security.auto-refresh-settings',
        error,
        message: 'Could not refresh security settings.',
      
        notifyMode: 'silent',
      });
    });
  }, { intervalMs: 30000 });

  // Save a specific setting to backend
  const saveSetting = (key: string, value: boolean) => {
    if (user?.user_id) {
      api.put(`/security/settings/${user.user_id}`, { [key]: value }).catch((error) => {
        handleAppRecoverableError({
          scope: 'privacy-security.save-setting',
          error,
          message: 'Could not save security preference.',
          onRetry: () => { if (user?.user_id) { void api.put(`/security/settings/${user.user_id}`, { [key]: value }); } },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      });
    }
  };

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      Alert.alert('Error', 'Please fill in all password fields');
      return;
    }
    
    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'New passwords do not match');
      return;
    }
    
    if (newPassword.length < 8) {
      Alert.alert('Error', 'Password must be at least 8 characters');
      return;
    }
    
    setPasswordLoading(true);
    try {
      await api.post('/auth/change-password', {
        user_id: user?.user_id,
        current_password: currentPassword,
        new_password: newPassword,
      });
      Alert.alert('Success', 'Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowPasswordSection(false);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'privacy-security.change-password',
        error,
        message: (error as any).response?.data?.detail || 'Failed to change password. Please try again.',
        onRetry: () => { void handleChangePassword(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Error', (error as any).response?.data?.detail || 'Failed to change password. Please try again.');
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleSetup2FA = () => {
    setShow2FAConfirm(true);
  };

  const execute2FAToggle = async () => {
    setShow2FAConfirm(false);
    setTwoFaLoading(true);
    try {
      if (twoFactorEnabled) {
        const res = await api.post('/auth/2fa/disable');
        setTwoFactorEnabled(false);
        setBackupCodesRemaining(0);
        setBackupCodes([]);
        Alert.alert('2FA Disabled', res.data.message || '2FA has been disabled.');
      } else {
        const res = await api.post('/auth/2fa/enable');
        if (res.data.exempt) {
          Alert.alert('Info', res.data.message);
          return;
        }
        setTwoFactorEnabled(true);
        setBackupCodes(res.data.backup_codes || []);
        setBackupCodesRemaining(res.data.backup_codes?.length || 0);
        setShowBackupCodes(true);
        Alert.alert('2FA Enabled', 'Save your backup codes! They can be used if you lose access to your email.');
      }
    } catch (e: any) {
      handleAppRecoverableError({
        scope: 'privacy-security.toggle-2fa',
        error: e,
        message: e.response?.data?.detail || 'Failed to update 2FA settings',
        onRetry: () => { void execute2FAToggle(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Error', e.response?.data?.detail || 'Failed to update 2FA settings');
    } finally {
      setTwoFaLoading(false);
    }
  };

  const handleRegenerateBackupCodes = async () => {
    Alert.alert('Regenerate Codes', 'This will invalidate all existing backup codes. Continue?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Regenerate', onPress: async () => {
        try {
          const res = await api.post('/auth/2fa/backup-codes/regenerate');
          setBackupCodes(res.data.backup_codes || []);
          setBackupCodesRemaining(res.data.backup_codes?.length || 0);
          setShowBackupCodes(true);
          Alert.alert('Success', 'New backup codes generated.');
        } catch (e: any) {
          handleAppRecoverableError({
            scope: 'privacy-security.regenerate-backup-codes',
            error: e,
            message: e.response?.data?.detail || 'Failed to regenerate codes',
            onRetry: () => { void handleRegenerateBackupCodes(); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
          Alert.alert('Error', e.response?.data?.detail || 'Failed to regenerate codes');
        }
      }},
    ]);
  };

  const handleLoadLoginHistory = async () => {
    if (showLoginHistory) { setShowLoginHistory(false); return; }
    try {
      const res = await api.get('/auth/security/login-history');
      setLoginHistory(res.data.events || []);
      setShowLoginHistory(true);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'privacy-security.load-login-history',
        error,
        message: 'Failed to load login history',
        onRetry: () => { void handleLoadLoginHistory(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Error', 'Failed to load login history');
    }
  };

  const handleBiometricToggle = async (val: boolean) => {
    if (!val) {
      setBiometricEnabled(false);
      saveSetting('biometric_enabled', false);
      Alert.alert('Disabled', 'Biometric login has been disabled.');
      return;
    }

    // Step 1: Try native biometrics (FaceID/fingerprint) on mobile
    if (Platform.OS !== 'web') {
      try {
        const hasHardware = await LocalAuthentication.hasHardwareAsync();
        const isEnrolled = await LocalAuthentication.isEnrolledAsync();
        if (hasHardware && isEnrolled) {
          const result = await LocalAuthentication.authenticateAsync({
            promptMessage: 'Authenticate to enable biometric login',
            fallbackLabel: 'Use PIN instead',
            cancelLabel: 'Cancel',
          });
          if (result.success) {
            await api.post('/auth/biometric/set-pin', { user_id: user?.user_id, pin: '0000' });
            setBiometricEnabled(true);
            saveSetting('biometric_enabled', true);
            Alert.alert('Success', 'Biometric login enabled! You can use FaceID or fingerprint to sign in.');
            return;
          } else {
            return;
          }
        }
      } catch (error) { handleAppRecoverableError({ scope: 'privacy-security.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }

    // Step 2: Try WebAuthn (FaceID/fingerprint on web browsers)
    if (isPasskeySupportedOnWeb()) {
      try {
        const available = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
        if (available) {
          const optRes = await api.post('/auth/biometric/webauthn-register-options', { user_id: user?.user_id });
          const opts = normalizeRegistrationOptions(optRes.data);
          const credential = await navigator.credentials.create({
            publicKey: opts,
          }) as any;
          if (credential) {
            await api.post('/auth/biometric/webauthn-register-complete', {
              user_id: user?.user_id,
              challenge_id: optRes.data?.challenge_id,
              credential: serializeWebAuthnCredential(credential),
            });
            setBiometricEnabled(true);
            Alert.alert('Success', 'Biometric login enabled via FaceID/fingerprint!');
            return;
          }
        }
      } catch (e: any) {
        if (e.name === 'NotAllowedError') return;
      }
    }

    // Step 3: Fallback to PIN setup
    setPinInput('');
    setShowPinModal(true);
  };

  const handlePinSubmit = async () => {
    if (pinInput.length !== 4 || !/^\d{4}$/.test(pinInput)) {
      Alert.alert('Error', 'PIN must be exactly 4 digits');
      return;
    }
    try {
      await api.post('/auth/biometric/set-pin', { user_id: user?.user_id, pin: pinInput });
      setBiometricEnabled(true);
      setShowPinModal(false);
      setPinInput('');
      Alert.alert('Success', 'PIN set! You can now use your PIN for quick unlock.');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'privacy-security.set-pin',
        error,
        message: 'Failed to set PIN. Please try again.',
        onRetry: () => { void handlePinSubmit(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Error', 'Failed to set PIN. Please try again.');
    }
  };

  const handleLoginAlertsToggle = (val: boolean) => {
    setLoginAlerts(val);
    saveSetting('login_alerts', val);
  };

  const handleProfileVisibleToggle = (val: boolean) => {
    setProfileVisible(val);
    saveSetting('profile_visible', val);
  };

  const handleActivityVisibleToggle = (val: boolean) => {
    setActivityVisible(val);
    saveSetting('activity_visible', val);
  };

  const handleDataCollectionToggle = (val: boolean) => {
    setDataCollection(val);
    saveSetting('data_collection', val);
  };

  const handleDownloadData = () => {
    Alert.alert(
      'Download Your Data',
      'We will prepare a copy of your data and send it to your email address. This may take up to 24 hours.',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Request Download',
          onPress: () => Alert.alert('Request Sent', 'You will receive an email with your data within 24 hours.')
        }
      ]
    );
  };

  const handleDeleteData = () => {
    Alert.alert(
      'Delete All Data',
      'This will permanently delete all your data including conversations, progress, and settings. This action cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Delete',
          style: 'destructive',
          onPress: () => Alert.alert('Contact Support', 'Please contact support@realaicoach.app to delete your data.')
        }
      ]
    );
  };

  if (!isAuthenticated) {
    return <Redirect href="/welcome?return_to=%2Fprivacy-security&auth_reason=unauthenticated" />;
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{tx('privacySecurity.title', 'Privacy & Security')}</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView 
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {/* Security Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{tx('privacySecurity.sections.security', 'Security')}</Text>
          <View style={styles.sectionCard}>
            {/* Change Password */}
            <TouchableOpacity 
              style={styles.settingItem}
              onPress={() => setShowPasswordSection(!showPasswordSection)}
            >
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(COLORS.error, '15') }]}>
                <Ionicons name="key-outline" size={20} color={COLORS.error} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.password.changeTitle', 'Change Password')}</Text>
                  <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.updatePassword', 'Update your account password')}</Text>
              </View>
              <Ionicons 
                name={showPasswordSection ? "chevron-up" : "chevron-down"} 
                size={18} 
                color={COLORS.textMuted} 
              />
            </TouchableOpacity>
            
            {showPasswordSection && (
              <View style={styles.passwordSection}>
                <View style={styles.inputContainer}>
                  <Text style={styles.inputLabel}>{tx('privacySecurity.password.currentLabel', 'Current Password')}</Text>
                  <View style={styles.passwordInput}>
                    <TextInput
                      style={styles.textInput}
                      placeholder={tx('privacySecurity.password.currentPlaceholder', 'Enter current password')}
                      placeholderTextColor={COLORS.textMuted}
                      secureTextEntry={!showCurrentPassword}
                      value={currentPassword}
                      onChangeText={setCurrentPassword}
                    />
                    <TouchableOpacity onPress={() => setShowCurrentPassword(!showCurrentPassword)}>
                      <Ionicons 
                        name={showCurrentPassword ? "eye-off" : "eye"} 
                        size={20} 
                        color={COLORS.textMuted} 
                      />
                    </TouchableOpacity>
                  </View>
                </View>
                
                <View style={styles.inputContainer}>
                  <Text style={styles.inputLabel}>{tx('privacySecurity.password.newLabel', 'New Password')}</Text>
                  <View style={styles.passwordInput}>
                    <TextInput
                      style={styles.textInput}
                      placeholder={tx('privacySecurity.password.newPlaceholder', 'Enter new password')}
                      placeholderTextColor={COLORS.textMuted}
                      secureTextEntry={!showNewPassword}
                      value={newPassword}
                      onChangeText={setNewPassword}
                    />
                    <TouchableOpacity onPress={() => setShowNewPassword(!showNewPassword)}>
                      <Ionicons 
                        name={showNewPassword ? "eye-off" : "eye"} 
                        size={20} 
                        color={COLORS.textMuted} 
                      />
                    </TouchableOpacity>
                  </View>
                </View>
                
                <View style={styles.inputContainer}>
                  <Text style={styles.inputLabel}>{tx('privacySecurity.password.confirmLabel', 'Confirm New Password')}</Text>
                  <TextInput
                    style={[styles.textInput, styles.textInputFull]}
                    placeholder={tx('privacySecurity.password.confirmPlaceholder', 'Confirm new password')}
                    placeholderTextColor={COLORS.textMuted}
                    secureTextEntry={!showNewPassword}
                    value={confirmPassword}
                    onChangeText={setConfirmPassword}
                  />
                </View>
                
                <TouchableOpacity 
                  style={styles.changePasswordButton}
                  onPress={handleChangePassword}
                  disabled={passwordLoading}
                >
                  {passwordLoading ? (
                    <ActivityIndicator color="#FFFFFF" />
                  ) : (
                    <Text style={styles.changePasswordButtonText}>{tx('privacySecurity.password.update', 'Update Password')}</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}

            {/* Two-Factor Authentication */}
            <TouchableOpacity style={styles.settingItem} onPress={handleSetup2FA} activeOpacity={0.7} data-testid="2fa-toggle-row" testID="2fa-toggle-row">
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }]}>
                <Ionicons name="shield-checkmark-outline" size={20} color={colors.primary} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.twoFactor.title', 'Two-Factor Authentication')}</Text>
                <Text style={styles.settingSubtitle}>
                  {twoFactorEnabled ? tx('privacySecurity.twoFactor.enabled').replace('{count}', String(backupCodesRemaining)) : tx('privacySecurity.twoFactor.disabled', 'Add extra security via email OTP')}
                </Text>
              </View>
              {twoFaLoading ? <ActivityIndicator size="small" color={COLORS.primary} /> : (
                <View style={{
                  width: 48, height: 28, borderRadius: 14, justifyContent: 'center',
                  backgroundColor: twoFactorEnabled ? COLORS.primary : COLORS.border,
                  paddingHorizontal: 2,
                }}>
                  <View style={{
                    width: 24, height: 24, borderRadius: 12, backgroundColor: colors.card,
                    alignSelf: twoFactorEnabled ? 'flex-end' : 'flex-start',
                    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.2, shadowRadius: 2,
                  }} />
                </View>
              )}
            </TouchableOpacity>

            {/* Backup Codes Section */}
            {twoFactorEnabled && (
              <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                <TouchableOpacity
                  onPress={() => setShowBackupCodes(!showBackupCodes)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6 }}
                  data-testid="toggle-backup-codes" testID="toggle-backup-codes"
                >
                  <Ionicons name="key-outline" size={16} color={COLORS.primary} />
                  <Text style={{ color: COLORS.primary, fontSize: 13, fontWeight: '600' }}>
                    {showBackupCodes ? tx('privacySecurity.backup.hide', 'Hide Backup Codes') : tx('privacySecurity.backup.view', 'View Backup Codes')}
                  </Text>
                </TouchableOpacity>

                {showBackupCodes && backupCodes.length > 0 && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '10'), borderRadius: 10, padding: 12, marginTop: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(COLORS.primary, '20') }}>
                    <Text style={{ color: COLORS.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }}>{tx('privacySecurity.backup.recoveryTitle', 'Recovery Backup Codes')}</Text>
                    <Text style={{ color: COLORS.textMuted, fontSize: 11, marginBottom: 10 }}>{tx('privacySecurity.backup.help', 'Save these codes securely. Each can be used once if you lose email access.')}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                      {backupCodes.map((code, i) => (
                        <View key={i} style={{ backgroundColor: COLORS.surface, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: COLORS.border }}>
                          <Text style={{ color: COLORS.text, fontSize: 14, fontWeight: '700', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', letterSpacing: 2 }} data-testid={`backup-code-${i}`} testID={`backup-code-${i}`}>{code}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                <TouchableOpacity
                  onPress={handleRegenerateBackupCodes}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6, marginTop: 4 }}
                  data-testid="regenerate-backup-codes" testID="regenerate-backup-codes"
                >
                  <Ionicons name="refresh-outline" size={16} color={COLORS.warningText} />
                  <Text style={{ color: COLORS.warningText, fontSize: 13, fontWeight: '600' }}>{tx('privacySecurity.backup.regenerate', 'Regenerate Backup Codes')}</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Login History */}
            <TouchableOpacity style={styles.settingItem} onPress={handleLoadLoginHistory}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.indigo, '15') }]}>
                <Ionicons name="time-outline" size={20} color={colors.indigoText} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.loginHistory.title', 'Login History')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.loginHistory', 'View recent sign-in activity')}</Text>
              </View>
              <Ionicons name={showLoginHistory ? 'chevron-up' : 'chevron-down'} size={18} color={COLORS.textMuted} />
            </TouchableOpacity>

            {showLoginHistory && (
              <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                {loginHistory.length === 0 ? (
                  <Text style={{ color: COLORS.textMuted, fontSize: 12, paddingVertical: 8 }}>{tx('privacySecurity.loginHistory.empty', 'No recent login activity')}</Text>
                ) : loginHistory.slice(0, 10).map((ev, i) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: i < Math.min(loginHistory.length, 10) - 1 ? 1 : 0, borderBottomColor: COLORS.border }}>
                    <Ionicons
                      name={ev.event_type === 'login_success' ? 'checkmark-circle' : ev.event_type === 'login_failed' ? 'close-circle' : 'log-out'}
                      size={18}
                      color={ev.event_type === 'login_success' ? COLORS.success : ev.event_type === 'login_failed' ? COLORS.error : COLORS.textMuted}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: COLORS.text, fontSize: 13, fontWeight: '600' }}>
                        {ev.event_type === 'login_success' ? tx('privacySecurity.loginHistory.success', 'Successful Login') : ev.event_type === 'login_failed' ? tx('privacySecurity.loginHistory.failed', 'Failed Login') : ev.event_type === 'logout' ? tx('privacySecurity.loginHistory.loggedOut', 'Logged Out') : ev.event_type?.replace(/_/g, ' ')}
                      </Text>
                      <Text style={{ color: COLORS.textMuted, fontSize: 11 }}>
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleString() : tx('privacySecurity.loginHistory.unknownTime', 'Unknown time')}
                        {ev.ip_address ? ` | ${ev.ip_address}` : ''}
                      </Text>
                    </View>
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: ev.risk_level === 'high' ? (globalThis as any).__alphaColor(COLORS.error, '15') : ev.risk_level === 'medium' ? colors.warning + '15' : COLORS.success + '15' }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: ev.risk_level === 'high' ? COLORS.error : ev.risk_level === 'medium' ? COLORS.warning : COLORS.success }}>{ev.risk_level?.toUpperCase() || 'LOW'}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}

            {/* Biometric Login */}
            <TouchableOpacity style={styles.settingItem} onPress={handleBiometricToggle} activeOpacity={0.7} data-testid="biometric-toggle-row" testID="biometric-toggle-row">
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(COLORS.success, '15') }]}>
                <Ionicons name="finger-print-outline" size={20} color={COLORS.successText} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.biometrics.title', 'Biometric Login')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.biometrics', 'Use Face ID or fingerprint')}</Text>
              </View>
              <View style={{
                width: 48, height: 28, borderRadius: 14, justifyContent: 'center',
                backgroundColor: biometricEnabled ? COLORS.primary : COLORS.border,
                paddingHorizontal: 2,
              }}>
                <View style={{
                  width: 24, height: 24, borderRadius: 12, backgroundColor: colors.card,
                  alignSelf: biometricEnabled ? 'flex-end' : 'flex-start',
                  shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.2, shadowRadius: 2,
                }} />
              </View>
            </TouchableOpacity>

            {/* Login Alerts */}
            <View style={[styles.settingItem, { borderBottomWidth: 0 }]}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15') }]}>
                <Ionicons name="alert-circle-outline" size={20} color={COLORS.warningText} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.loginAlerts.title', 'Login Alerts')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.loginAlerts', 'Get notified of new logins')}</Text>
              </View>
              <Switch
                value={loginAlerts}
                onValueChange={handleLoginAlertsToggle}
                trackColor={{ false: COLORS.border, true: COLORS.primary }}
                thumbColor="#FFFFFF"
              />
            </View>
          </View>
        </View>

        {/* Trusted Devices Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{tx('privacySecurity.sections.trustedDevices', 'Trusted Devices')}</Text>
          <View style={styles.sectionCard}>
            <View style={{ padding: 16 }}>
              <TrustedDevicesPanel />
            </View>
          </View>
        </View>

        {/* Privacy Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{tx('privacySecurity.sections.privacy', 'Privacy')}</Text>
          <View style={styles.sectionCard}>
            <View style={styles.settingItem}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.indigo, '15') }]}>
                <Ionicons name="person-outline" size={20} color={colors.indigoText} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.profile.title', 'Profile Visibility')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.profileVisible', 'Allow others to see your profile')}</Text>
              </View>
              <Switch
                value={profileVisible}
                onValueChange={handleProfileVisibleToggle}
                trackColor={{ false: COLORS.border, true: COLORS.primary }}
                thumbColor="#FFFFFF"
              />
            </View>

            <View style={styles.settingItem}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.accent, '15') }]}> 
                <Ionicons name="analytics-outline" size={20} color={colors.accent} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.activity.title', 'Activity Status')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.activityVisible', "Show when you're active")}</Text>
              </View>
              <Switch
                value={activityVisible}
                onValueChange={handleActivityVisibleToggle}
                trackColor={{ false: COLORS.border, true: COLORS.primary }}
                thumbColor="#FFFFFF"
              />
            </View>

            <View style={[styles.settingItem, { borderBottomWidth: 0 }]}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(COLORS.success, '15') }]}>
                <Ionicons name="bar-chart-outline" size={20} color={COLORS.successText} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.analytics.title', 'Usage Analytics')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.dataCollection', 'Help improve RealAICoach')}</Text>
              </View>
              <Switch
                value={dataCollection}
                onValueChange={handleDataCollectionToggle}
                trackColor={{ false: COLORS.border, true: COLORS.primary }}
                thumbColor="#FFFFFF"
              />
            </View>
          </View>
        </View>

        {/* Data Management Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{tx('privacySecurity.sections.dataManagement', 'Data Management')}</Text>
          <View style={styles.sectionCard}>
            <TouchableOpacity style={styles.settingItem} onPress={handleDownloadData}>
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }]}>
                <Ionicons name="download-outline" size={20} color={colors.primary} />
              </View>
              <View style={styles.settingContent}>
                <Text style={styles.settingTitle}>{tx('privacySecurity.data.downloadTitle', 'Download My Data')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.exportData', 'Get a copy of your data')}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>

            <TouchableOpacity 
              style={[styles.settingItem, { borderBottomWidth: 0 }]} 
              onPress={handleDeleteData}
            >
              <View style={[styles.settingIcon, { backgroundColor: (globalThis as any).__alphaColor(COLORS.error, '15') }]}>
                <Ionicons name="trash-outline" size={20} color={COLORS.error} />
              </View>
              <View style={styles.settingContent}>
                <Text style={[styles.settingTitle, { color: COLORS.error }]}>{tx('privacySecurity.data.deleteTitle', 'Delete All Data')}</Text>
                <Text style={styles.settingSubtitle}>{tx('privacySecurity.settings.deleteData', 'Permanently remove your data')}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Info Card */}
        <View style={styles.infoCard}>
          <Ionicons name="shield-checkmark" size={24} color={COLORS.successText} />
          <View style={styles.infoContent}>
            <Text style={styles.infoTitle}>{tx('privacySecurity.info.title', 'Your data is protected')}</Text>
            <Text style={styles.infoText}>
              {tx('privacySecurity.info.subtitle', 'We use industry-standard encryption to keep your information safe and secure.')}
            </Text>
          </View>
        </View>

        {/* Footer */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>{tx('privacySecurity.footer', '© 2026-2030 RealAICoach LLC. All rights reserved. (USA)')}</Text>
        </View>
      </ScrollView>

      {/* PIN Setup Modal */}
      <Modal visible={showPinModal} transparent animationType="fade">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
          <View style={{ backgroundColor: COLORS.surface, borderRadius: 20, padding: 24, width: '100%', maxWidth: 360, borderWidth: 1, borderColor: COLORS.border }}>
            <View style={{ alignItems: 'center', marginBottom: 20 }}>
              <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: (globalThis as any).__alphaColor(COLORS.success, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                <Ionicons name="finger-print" size={28} color={COLORS.successText} />
              </View>
              <Text style={{ fontSize: 18, fontWeight: '700', color: COLORS.text }}>{tx('privacySecurity.pin.title', 'Set Unlock PIN')}</Text>
              <Text style={{ fontSize: 13, color: COLORS.textSecondary, textAlign: 'center', marginTop: 4 }}>
                {tx('privacySecurity.pin.subtitle', 'Enter a 4-digit PIN for quick unlock')}
              </Text>
            </View>
            <TextInput
              value={pinInput}
              onChangeText={(t) => setPinInput(t.replace(/[^0-9]/g, '').slice(0, 4))}
              placeholder={tx('privacySecurity.pin.placeholder', 'Enter 4-digit PIN')}
              placeholderTextColor={COLORS.textMuted}
              keyboardType="number-pad"
              maxLength={4}
              secureTextEntry
              autoFocus
              style={{
                fontSize: 24, textAlign: 'center', letterSpacing: 12,
                padding: 14, borderRadius: 12, borderWidth: 1,
                borderColor: COLORS.border, backgroundColor: COLORS.background,
                color: COLORS.text, fontWeight: '700', marginBottom: 16,
              }}
            />
            <TouchableOpacity
              onPress={handlePinSubmit}
              style={{ backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: 12, alignItems: 'center' }}
            >
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 15 }}>{tx('privacySecurity.pin.action', 'Set PIN')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { setShowPinModal(false); setPinInput(''); }}
              style={{ alignItems: 'center', marginTop: 12 }}
            >
              <Text style={{ color: COLORS.textSecondary, fontSize: 14 }}>{tx('common.cancel', 'Cancel')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* 2FA Confirmation Modal */}
      <Modal visible={show2FAConfirm} transparent animationType="fade">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
          <View style={{ backgroundColor: COLORS.surface, borderRadius: 20, padding: 24, width: '100%', maxWidth: 400, borderWidth: 1, borderColor: COLORS.border }}>
            <View style={{ alignItems: 'center', marginBottom: 20 }}>
              <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                <Ionicons name="shield-checkmark" size={28} color={colors.primary} />
              </View>
              <Text style={{ fontSize: 18, fontWeight: '700', color: COLORS.text }}>
                {twoFactorEnabled ? tx('privacySecurity.twoFactor.disableTitle', 'Disable Two-Factor Authentication') : tx('privacySecurity.twoFactor.enableTitle', 'Enable Two-Factor Authentication')}
              </Text>
              <Text style={{ fontSize: 13, color: COLORS.textSecondary, textAlign: 'center', marginTop: 8, lineHeight: 20 }}>
                {twoFactorEnabled
                  ? tx('privacySecurity.twoFactor.disableDesc', 'Are you sure you want to disable 2FA? This will make your account less secure. You will no longer need an email verification code when logging in.')
                  : tx('privacySecurity.twoFactor.enableDesc', 'Enable 2FA to add an extra layer of security. Each time you log in, you will receive a one-time verification code via email that you must enter to complete sign-in.')}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => setShow2FAConfirm(false)}
                style={{ flex: 1, paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center' }}
              >
                <Text style={{ color: COLORS.textSecondary, fontWeight: '700', fontSize: 15 }}>{tx('common.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={execute2FAToggle}
                style={{ flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: 'center', backgroundColor: twoFactorEnabled ? COLORS.error : colors.primary }}
              >
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 15 }}>{twoFactorEnabled ? tx('common.disable', 'Disable') : tx('common.enable', 'Enable')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const createStyles = (COLORS: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
  },
  headerSpacer: {
    width: 40,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  notAuthContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  notAuthIcon: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: COLORS.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  notAuthTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 8,
  },
  notAuthText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: 24,
  },
  signInButton: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 12,
  },
  signInButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textMuted,
    marginBottom: 10,
    marginLeft: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  sectionCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  settingIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  settingContent: {
    flex: 1,
    marginLeft: 12,
  },
  settingTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: COLORS.text,
  },
  settingSubtitle: {
    fontSize: 12,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  passwordSection: {
    padding: 16,
    backgroundColor: COLORS.background,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  inputContainer: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.text,
    marginBottom: 8,
  },
  passwordInput: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingRight: 12,
  },
  textInput: {
    flex: 1,
    padding: 12,
    fontSize: 14,
    color: COLORS.text,
  },
  textInputFull: {
    backgroundColor: COLORS.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  changePasswordButton: {
    backgroundColor: COLORS.primary,
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  changePasswordButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: 'rgba(16, 185, 129, 0.08)',
    borderRadius: 12,
    padding: 16,
    alignItems: 'flex-start',
    gap: 12,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.15)',
  },
  infoContent: {
    flex: 1,
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 4,
  },
  infoText: {
    fontSize: 13,
    color: COLORS.textSecondary,
    lineHeight: 18,
  },
  footer: {
    alignItems: 'center',
    paddingTop: 24,
  },
  footerText: {
    fontSize: 12,
    color: COLORS.textMuted,
  },
});
