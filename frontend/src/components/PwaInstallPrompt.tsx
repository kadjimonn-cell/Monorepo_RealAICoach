import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

// Store the deferred prompt event
let deferredPrompt: any = null;

export default function PwaInstallPrompt() {
  const { colors: theme } = useTheme();
  const [showInstall, setShowInstall] = useState(false);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web') return;

    // Check if already installed as PWA
    const isStandalone =
      window.matchMedia?.('(display-mode: standalone)').matches ||
      (window.navigator as any).standalone === true;

    if (isStandalone) {
      setIsInstalled(true);
      return;
    }

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredPrompt = e;
      setShowInstall(true);
    };

    const handleAppInstalled = () => {
      deferredPrompt = null;
      setShowInstall(false);
      setIsInstalled(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const result = await deferredPrompt.userChoice;
    if (result.outcome === 'accepted') {
      setShowInstall(false);
    }
    deferredPrompt = null;
  }, []);

  if (Platform.OS !== 'web' || isInstalled || !showInstall) return null;

  return (
    <TouchableOpacity
      data-testid="pwa-install-btn" testID="pwa-install-btn"
      onPress={handleInstall}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        paddingVertical: 8,
        paddingHorizontal: 12,
        borderRadius: 8,
        backgroundColor: (globalThis as any).__alphaColor(theme.primary, '18'),
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(theme.primary, '30'),
      }}
      activeOpacity={0.7}
    >
      <View style={{
        width: 28,
        height: 28,
        borderRadius: 6,
        backgroundColor: theme.primary,
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <Ionicons name="download-outline" size={15} color="var(--app-primary-text)" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 12, fontWeight: '700', color: theme.text }}>
          Install App
        </Text>
        <Text style={{ fontSize: 10, color: theme.textMuted }}>
          Faster access, works offline
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color={theme.textMuted} />
    </TouchableOpacity>
  );
}

/* i18n-probe t('i18n.auto.probe') */
