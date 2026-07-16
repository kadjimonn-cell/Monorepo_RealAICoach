import React, { useEffect, useMemo, useRef } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { usePathname, useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { getShadow } from '../utils/themeShadows';
import { withAlpha } from '../utils/colorAlpha';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { getCurrentLanguageOption, getLanguageOptionByCode } from '../i18n/languageOptions';
import { useAutoTranslate } from '../hooks/useAutoTranslate';
import { useAuth } from '../context/AuthContext';

// Detect web platform using browser APIs (more reliable for Expo Web bundling)
const isWeb = typeof window !== 'undefined' && typeof document !== 'undefined';

// Helper function to get test props for automated testing
const getTestPropsLocal = (id: string): any => {
  if (isWeb) {
    return { testID: id, 'data-testid': id };
  }
  return { testID: id };
};

export default function LanguageSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { colors, darkMode, language, languageCode, setLanguage } = useTheme();
  const { user } = useAuth();
  const { data: langPref } = useLiveQuery('/i18n/user-preference', { entity: 'i18n', pollInterval: 120000, skip: !user?.user_id });
  const hasServerLanguagePreference = Boolean(langPref?.has_preference);
  const { tt } = useAutoTranslate();
  const initialServerSyncDoneRef = useRef(false);
  const lastAppliedServerCodeRef = useRef('');

  useEffect(() => {
    if (!hasServerLanguagePreference) return;
    const preferred = getLanguageOptionByCode(langPref?.language);
    if (!preferred) {
      return;
    }

    // Only hydrate from server preference on first load (or when server value changes).
    // Avoid forcing stale server snapshot values after user manually switches language.
    const serverChanged = lastAppliedServerCodeRef.current !== preferred.code;
    const shouldHydrateFromServer = !initialServerSyncDoneRef.current || serverChanged;

    if (!shouldHydrateFromServer) {
      return;
    }

    initialServerSyncDoneRef.current = true;
    lastAppliedServerCodeRef.current = preferred.code;

    if (preferred.code === languageCode) {
      return;
    }

    setLanguage(preferred.label);
  }, [hasServerLanguagePreference, langPref?.language, languageCode, setLanguage]);

  const current = useMemo(
    () => (hasServerLanguagePreference ? getLanguageOptionByCode(langPref?.language) : null) || getCurrentLanguageOption(language, languageCode),
    [hasServerLanguagePreference, langPref?.language, language, languageCode]
  );

  return (
    <View
      style={{ marginTop: 6 }}
      {...getTestPropsLocal('language-switcher')}
    >
      <TouchableOpacity accessibilityLabel="Push in language switcher button"
        accessibilityRole="button"
        onPress={() => router.push({ pathname: '/language-selector', params: { returnTo: pathname || '/dashboard' } } as any)}
        {...getTestPropsLocal('language-switcher-btn')}
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 10,
          paddingVertical: 10, paddingHorizontal: 12, borderRadius: 12,
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.border,
          ...(isWeb ? getShadow('sm', darkMode) : {}),
        }}
      >
        <View
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: withAlpha(colors.primary, '12'),
          }}
          {...getTestPropsLocal('language-switcher-icon-wrap')}
        >
          <Ionicons name="language-outline" size={16} color={colors.primary} />
        </View>

        <View style={{ flex: 1, minWidth: 0 }} {...getTestPropsLocal('language-switcher-copy')}>
          <Text
            style={{ fontSize: 10, fontWeight: '700', letterSpacing: 0.7, color: colors.textMuted, textTransform: 'uppercase' }}
            {...getTestPropsLocal('language-switcher-label')}
          >
            {tt('Language')}
          </Text>
          <Text
            numberOfLines={1}
            style={{ fontSize: 13, fontWeight: '700', color: colors.text, marginTop: 2 }}
            {...getTestPropsLocal('language-switcher-current')}
          >
            {current?.native || 'English'}
          </Text>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View
            style={{
              minWidth: 34,
              paddingHorizontal: 8,
              paddingVertical: 5,
              borderRadius: 999,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: colors.bgSoft,
            }}
            {...getTestPropsLocal('language-switcher-badge')}
          >
            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.textSec }}>
              {current?.short || 'EN'}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
        </View>
      </TouchableOpacity>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
