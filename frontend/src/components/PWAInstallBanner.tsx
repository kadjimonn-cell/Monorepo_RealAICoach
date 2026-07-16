import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, Platform, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { usePathname } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { usePWAInstall } from '../hooks/usePWAInstall';
import { useTranslation } from '../hooks/useTranslation';

const DISMISS_KEY = 'pwa_install_dismissed';

export default function PWAInstallBanner() {
  const { colors, darkMode } = useTheme();
  const { canInstall, isInstalled, promptInstall } = usePWAInstall();
  const { t } = useTranslation();
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [isNarrowMobile, setIsNarrowMobile] = useState(false);
  const fadeAnim = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const syncViewport = () => setIsNarrowMobile(window.innerWidth < 560);
    syncViewport();
    window.addEventListener('resize', syncViewport);
    return () => window.removeEventListener('resize', syncViewport);
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || isInstalled || !canInstall) return;
    AsyncStorage.getItem(DISMISS_KEY).then((val) => {
      if (!val) {
        setVisible(true);
        Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: false }).start();
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canInstall, isInstalled]);

  const dismiss = async () => {
    await AsyncStorage.setItem(DISMISS_KEY, Date.now().toString());
    Animated.timing(fadeAnim, { toValue: 0, duration: 300, useNativeDriver: false }).start(() => setVisible(false));
  };

  const install = async () => {
    const accepted = await promptInstall();
    if (accepted) {
      Animated.timing(fadeAnim, { toValue: 0, duration: 300, useNativeDriver: false }).start(() => setVisible(false));
    }
  };

  const suppressOnWelcome = pathname === '/welcome';
  if (!visible || suppressOnWelcome) return null;

  return (
    <Animated.View
      style={{
        opacity: fadeAnim,
        position: 'fixed' as any,
        bottom: isNarrowMobile ? 12 : 20,
        left: isNarrowMobile ? 12 : 20,
        right: isNarrowMobile ? 12 : 20,
        maxWidth: isNarrowMobile ? undefined : 420,
        zIndex: 9999,
        ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } : {}),
      }}
      data-testid="pwa-install-banner" testID="pwa-install-banner"
    >
      <View style={{
        backgroundColor: darkMode ? colors.cardMuted : colors.card,
        borderRadius: 16,
        padding: isNarrowMobile ? 14 : 16,
        flexDirection: isNarrowMobile ? 'column' : 'row',
        alignItems: 'center',
        gap: 14,
        borderWidth: 1,
        borderColor: colors.border,
        ...(Platform.OS === 'web' ? { boxShadow: '0 8px 32px rgba(0,0,0,0.18)' } as any : {}),
      }}>
        <View style={{
          width: isNarrowMobile ? 40 : 44,
          height: isNarrowMobile ? 40 : 44,
          borderRadius: 12,
          backgroundColor: colors.primarySoft,
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <Ionicons name="download-outline" size={22} color={colors.primary} />
        </View>

        <View style={{ flex: 1, alignItems: isNarrowMobile ? 'center' : 'flex-start' }}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 2, textAlign: isNarrowMobile ? 'center' : 'left' }}>
            {t('pwa.installApp')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 16, textAlign: isNarrowMobile ? 'center' : 'left' }}>
            {t('pwa.installPrompt')}
          </Text>
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexShrink: 0, width: isNarrowMobile ? '100%' : undefined, justifyContent: isNarrowMobile ? 'center' : 'flex-start' }}>
          <TouchableOpacity onPress={dismiss} data-testid="pwa-install-dismiss" testID="pwa-install-dismiss">
            <Ionicons name="close" size={20} color={colors.textMuted} />
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Pwa install button"
            onPress={install}
            style={{
              backgroundColor: colors.primary,
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 8,
            }}
            data-testid="pwa-install-button" testID="pwa-install-button"
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{t('pwa.install')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Animated.View>
  );
}
