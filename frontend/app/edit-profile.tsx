import React, { useState, useEffect, useMemo } from 'react';
import { KeyboardAvoidingView, Platform } from 'react-native';

// Native-only keyboard avoidance wrapper (Fragment on web = zero DOM change).
const FormKeyboardWrap: any = Platform.OS === 'web' ? React.Fragment : KeyboardAvoidingView;
const formKeyboardWrapProps: any = Platform.OS === 'web'
  ? {}
  : { behavior: Platform.OS === 'ios' ? 'padding' : undefined, style: { flex: 1 } };
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  Image,
  _Platform,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Redirect, useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';
import { useProfilePhoto } from '../src/components/profile/useProfilePhoto';
import { ProfilePhotoCropper } from '../src/components/profile/ProfilePhotoCropper';
import { AvatarGalleryModal } from '../src/components/profile/AvatarGalleryModal';

const staticColors = {
  success: '#10B981', // @theme-ok brand/role/state identifier
  error: '#EF4444', // @theme-ok brand/role/state identifier
};

export default function EditProfileScreen() {
  const router = useRouter();
  const { user, refreshUser, isAuthenticated } = useAuth();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [phone, setPhone] = useState((user as any)?.phone || '');
  const [loading, setLoading] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const photo = useProfilePhoto({
    initialImage: (user as any)?.profile_image || null,
    refreshUser,
  });
  const { profileImage, uploading, uploadProgress, showImageOptions, removePhoto,
    cropModalVisible, rawImageSrc, canvasRef, zoom, setZoom, rotation, setRotation,
    handleCropApply, handleCropCancel } = photo;

  const [showAvatarGallery, setShowAvatarGallery] = useState(false);

  const handleAvatarSelect = async (url: string) => {
    if (url.startsWith('initials:')) return;
    photo.setProfileImage?.(url);
    await refreshUser();
  };

  const COLORS = useMemo(() => ({
    ...staticColors,
    primary: colors.primary,
    primaryDark: colors.primary,
    background: colors.bg,
    backgroundSecondary: colors.bgSoft,
    surface: colors.card,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  useEffect(() => {
    if (user) {
      setName(user.name || '');
      setEmail(user.email || '');
      setPhone((user as any).phone || '');
    }
  }, [user]);

  useEffect(() => {
    const changed = 
      name !== (user?.name || '') ||
      phone !== ((user as any)?.phone || '') ||
      profileImage !== ((user as any)?.profile_image || null);
    setHasChanges(changed);
  }, [name, phone, profileImage, user]);

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert(
        tx('common.error', 'Error'),
        tx('editProfile.alerts.nameRequired', 'Name cannot be empty')
      );
      return;
    }

    setLoading(true);
    try {
      await api.put('/auth/profile', {
        name: name.trim(),
        phone: phone.trim(),
      });

      await refreshUser();
      Alert.alert(tx('editProfile.alerts.successTitle', 'Success'), tx('editProfile.alerts.profileUpdated', 'Profile updated successfully!'), [
        { text: tx('editProfile.alerts.ok', 'OK'), onPress: () => router.back() }
      ]);
    } catch (error: any) {
      Alert.alert(
        tx('common.error', 'Error'),
        error.response?.data?.detail || tx('editProfile.alerts.profileUpdateFailed', 'Failed to update profile')
      );
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return <Redirect href="/welcome?return_to=%2Fedit-profile&auth_reason=unauthenticated" />;
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{tx('editProfile.page.title', 'Edit Profile')}</Text>
        <TouchableOpacity 
          style={[styles.saveButton, !hasChanges && styles.saveButtonDisabled]}
          onPress={handleSave}
          disabled={!hasChanges || loading}
        >
          {loading ? (
            <ActivityIndicator size="small" color={COLORS.surface} />
          ) : (
            <Text style={[styles.saveButtonText, !hasChanges && styles.saveButtonTextDisabled]}>
              {tx('common.save', 'Save')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      <FormKeyboardWrap {...formKeyboardWrapProps}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={[styles.scrollContent, { maxWidth: 960, alignSelf: 'center' as any, width: '100%' as any, paddingHorizontal: isWide ? 32 : 20 }]}>
        {/* Profile Photo Section */}
        <View style={styles.photoSection}>
          <TouchableOpacity style={styles.photoContainer} onPress={showImageOptions} disabled={uploading} data-testid="photo-upload-button" testID="photo-upload-button">
            {profileImage ? (
              <Image source={{ uri: profileImage }} style={styles.profileImage} />
            ) : (
              <View style={styles.photoPlaceholder}>
                <Ionicons name="person" size={48} color={COLORS.textMuted} />
              </View>
            )}
            <View style={styles.editBadge}>
              <Ionicons name={uploading ? "cloud-upload" : "camera"} size={16} color={COLORS.surface} />
            </View>
          </TouchableOpacity>
          {uploading && (
            <View style={styles.progressContainer} data-testid="upload-progress-bar" testID="upload-progress-bar">
              <View style={styles.progressBar}>
                <View style={[styles.progressFill, { width: `${uploadProgress}%` }]} />
              </View>
              <Text style={styles.progressText}>{tx('editProfile.photo.uploadingProgress', '{percent}% uploading...').replace('{percent}', String(uploadProgress))}</Text>
            </View>
          )}

          {/* Photo Action Buttons */}
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
            <TouchableOpacity
              onPress={showImageOptions}
              disabled={uploading}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(COLORS.primary, '40'), backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '10') }}
              data-testid="upload-photo-btn" testID="upload-photo-btn"
            >
              <Ionicons name="cloud-upload-outline" size={14} color={COLORS.primary} />
              <Text style={{ color: COLORS.primary, fontSize: 12, fontWeight: '700' }}>{profileImage ? tx('editProfile.photo.changePhoto', 'Change Photo') : tx('editProfile.photo.uploadPhoto', 'Upload Photo')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setShowAvatarGallery(true)}
              disabled={uploading}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.purple, '40'), backgroundColor: (globalThis as any).__alphaColor(colors.purple, '10') }}
              data-testid="choose-avatar-btn" testID="choose-avatar-btn"
            >
              <Ionicons name="people-outline" size={14} color={colors.purpleText} />
              <Text style={{ color: colors.purpleText, fontSize: 12, fontWeight: '700' }}>{tx('editProfile.photo.chooseAvatar', 'Choose Avatar')}</Text>
            </TouchableOpacity>

            {profileImage && !uploading && (
              <TouchableOpacity
                onPress={removePhoto}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(COLORS.error, '40'), backgroundColor: (globalThis as any).__alphaColor(COLORS.error, '10') }}
                data-testid="remove-photo-button" testID="remove-photo-button"
              >
                <Ionicons name="trash-outline" size={14} color={COLORS.error} />
                <Text style={{ color: COLORS.error, fontSize: 12, fontWeight: '700' }}>{tx('editProfile.photo.removePhoto', 'Remove')}</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Form Fields */}
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>{tx('editProfile.sections.personalInformation', 'Personal Information')}</Text>
          
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>{tx('editProfile.fields.fullName', 'Full Name')}</Text>
            <View style={styles.inputContainer}>
              <Ionicons name="person-outline" size={20} color={COLORS.textMuted} />
              <TextInput
                style={styles.textInput}
                value={name}
                onChangeText={setName}
                placeholder={tx('editProfile.placeholders.enterName', 'Enter your name')}
                placeholderTextColor={COLORS.textMuted}
              />
            </View>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>{tx('editProfile.fields.emailAddress', 'Email Address')}</Text>
            <View style={[styles.inputContainer, styles.inputDisabled]}>
              <Ionicons name="mail-outline" size={20} color={COLORS.textMuted} />
              <TextInput
                style={[styles.textInput, styles.textInputDisabled]}
                value={email}
                editable={false}
                placeholder={tx('editProfile.placeholders.email', 'Email')}
                placeholderTextColor={COLORS.textMuted}
              />
              <View style={styles.verifiedBadge}>
                <Ionicons name="checkmark-circle" size={16} color={COLORS.successText} />
              </View>
            </View>
            <Text style={styles.inputHint}>{tx('editProfile.fields.emailImmutable', 'Email cannot be changed')}</Text>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>{tx('editProfile.fields.phoneOptional', 'Phone Number (Optional)')}</Text>
            <View style={styles.inputContainer}>
              <Ionicons name="call-outline" size={20} color={COLORS.textMuted} />
              <TextInput
                style={styles.textInput}
                value={phone}
                onChangeText={setPhone}
                placeholder={tx('editProfile.placeholders.enterPhone', 'Enter your phone number')}
                placeholderTextColor={COLORS.textMuted}
                keyboardType="phone-pad"
              />
            </View>
          </View>
        </View>

        {/* Account Info */}
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>{tx('editProfile.sections.accountInformation', 'Account Information')}</Text>
          
          <View style={styles.infoCard}>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>{tx('editProfile.account.memberSince', 'Member Since')}</Text>
              <Text style={styles.infoValue}>
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : tx('editProfile.common.notAvailable', 'N/A')}
              </Text>
            </View>
            <View style={styles.infoDivider} />
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>{tx('editProfile.account.subscriptionPlan', 'Subscription Plan')}</Text>
              <View style={styles.planBadge}>
                <Text style={styles.planBadgeText}>
                  {(user?.subscription_plan || 'free').charAt(0).toUpperCase() + (user?.subscription_plan || 'free').slice(1)}
                </Text>
              </View>
            </View>
            <View style={styles.infoDivider} />
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>{tx('editProfile.account.userId', 'User ID')}</Text>
              <Text style={styles.infoValueSmall}>{user?.user_id?.slice(0, 20) || tx('editProfile.common.notAvailable', 'N/A')}...</Text>
            </View>
          </View>
        </View>

        {/* Danger Zone */}
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>{tx('editProfile.sections.accountActions', 'Account Actions')}</Text>
          
          <TouchableOpacity 
            style={styles.dangerButton}
            onPress={() => router.push('/privacy-security')}
          >
            <Ionicons name="shield-outline" size={20} color={COLORS.primary} />
            <Text style={styles.dangerButtonText}>{tx('editProfile.actions.privacySecurity', 'Privacy & Security Settings')}</Text>
            <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity 
            style={[styles.dangerButton, styles.dangerButtonRed]}
            onPress={() => {
              Alert.alert(
                tx('editProfile.delete.title', 'Delete Account'),
                tx('editProfile.delete.confirmMessage', 'This action cannot be undone. All your data will be permanently deleted.'),
                [
                  { text: tx('common.cancel', 'Cancel'), style: 'cancel' },
                  { text: tx('common.delete', 'Delete'), style: 'destructive', onPress: () => {
                    Alert.alert(tx('editProfile.delete.contactSupportTitle', 'Contact Support'), tx('editProfile.delete.contactSupportMessage', 'Please contact support@realaicoach.app to delete your account.'));
                  }}
                ]
              );
            }}
          >
            <Ionicons name="trash-outline" size={20} color={COLORS.error} />
            <Text style={[styles.dangerButtonText, { color: COLORS.error }]}>{tx('editProfile.actions.deleteAccount', 'Delete Account')}</Text>
            <Ionicons name="chevron-forward" size={18} color={COLORS.error} />
          </TouchableOpacity>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>{tx('editProfile.footer.copyright', '© 2026-2030 RealAICoach LLC. All rights reserved. (USA)')}</Text>
        </View>
      </ScrollView>
      </FormKeyboardWrap>

      {/* Crop Modal (Web only) */}
      <ProfilePhotoCropper
        visible={cropModalVisible}
        rawImageSrc={rawImageSrc}
        canvasRef={canvasRef}
        zoom={zoom}
        setZoom={setZoom}
        rotation={rotation}
        setRotation={setRotation}
        onApply={handleCropApply}
        onCancel={handleCropCancel}
        primaryColor={COLORS.primary}
      />
      <AvatarGalleryModal
        visible={showAvatarGallery}
        onClose={() => setShowAvatarGallery(false)}
        onSelectAvatar={handleAvatarSelect}
        currentImage={profileImage}
        userName={user?.name || tx('editProfile.common.user', 'User')}
      />
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
    backgroundColor: COLORS.backgroundSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
  },
  saveButton: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  saveButtonDisabled: {
    backgroundColor: COLORS.border,
  },
  saveButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.surface,
  },
  saveButtonTextDisabled: {
    color: COLORS.textMuted,
  },
  headerSpacer: {
    width: 60,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  authPrompt: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
  },
  authPromptTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.text,
    marginTop: 16,
  },
  authPromptText: {
    fontSize: 14,
    color: COLORS.textMuted,
    marginTop: 8,
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
    color: COLORS.surface,
  },
  photoSection: {
    alignItems: 'center',
    marginBottom: 32,
  },
  photoContainer: {
    position: 'relative',
    marginBottom: 12,
  },
  profileImage: {
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 3,
    borderColor: COLORS.primary,
  },
  photoPlaceholder: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.backgroundSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: COLORS.border,
    borderStyle: 'dashed',
  },
  editBadge: {
    position: 'absolute',
    bottom: 4,
    right: 4,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: COLORS.surface,
  },
  changePhotoText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.primary,
  },
  progressContainer: {
    width: '100%',
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 4,
  },
  progressBar: {
    width: 120,
    height: 4,
    backgroundColor: COLORS.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 2,
  },
  progressText: {
    fontSize: 11,
    color: COLORS.textMuted,
    marginTop: 4,
  },
  formSection: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 16,
  },
  inputGroup: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.backgroundSecondary,
    borderRadius: 12,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  inputDisabled: {
    backgroundColor: (globalThis as any).__alphaColor(COLORS.border, '40'),
  },
  textInput: {
    flex: 1,
    paddingVertical: 14,
    marginLeft: 12,
    fontSize: 15,
    color: COLORS.text,
  },
  textInputDisabled: {
    color: COLORS.textMuted,
  },
  verifiedBadge: {
    marginLeft: 8,
  },
  inputHint: {
    fontSize: 11,
    color: COLORS.textMuted,
    marginTop: 6,
    marginLeft: 4,
  },
  infoCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  infoDivider: {
    height: 1,
    backgroundColor: COLORS.border,
  },
  infoLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  infoValue: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  infoValueSmall: {
    fontSize: 12,
    fontWeight: '500',
    color: COLORS.textMuted,
  },
  planBadge: {
    backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '15'),
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 8,
  },
  planBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
  },
  dangerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    gap: 12,
  },
  dangerButtonRed: {
    borderColor: (globalThis as any).__alphaColor(COLORS.error, '30'),
    backgroundColor: (globalThis as any).__alphaColor(COLORS.error, '05'),
  },
  dangerButtonText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  footer: {
    alignItems: 'center',
    marginTop: 24,
  },
  footerText: {
    fontSize: 12,
    color: COLORS.textMuted,
  },
});
