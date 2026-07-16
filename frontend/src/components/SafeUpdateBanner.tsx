import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useConfig } from '../context/ConfigContext';
import { router } from 'expo-router';

const SILENT_SAFE_UPDATE_UI = true;

export default function SafeUpdateBanner() {
  const { config } = useConfig();
  const { colors: theme } = useTheme();
  // const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [update, setUpdate] = useState<any>(null);
  const slideAnim = useState(new Animated.Value(-100))[0];

  useEffect(() => {
    if (config?.updates && config.updates.length > 0) {
      // Show the latest update
      setUpdate(config.updates[0]);
      setVisible(true);
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 500,
        useNativeDriver: Platform.OS !== 'web',
      }).start();

      // Auto-dismiss after 2 seconds
      const timer = setTimeout(() => {
        Animated.timing(slideAnim, {
          toValue: -100,
          duration: 300,
          useNativeDriver: Platform.OS !== 'web',
        }).start(() => setVisible(false));
      }, 2000);
      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  if (!visible || !update || SILENT_SAFE_UPDATE_UI) return null;

  const handlePress = () => {
    if (update.action_link) {
      router.push(update.action_link as any);
    }
    setVisible(false);
  };

  const getIcon = () => {
    switch (update.type) {
      case 'success': return 'checkmark-circle';
      case 'warning': return 'warning';
      default: return 'information-circle';
    }
  };

  const getColor = () => {
    switch (update.type) {
      case 'success': return theme.success;
      case 'warning': return theme.warning;
      default: return theme.primary;
    }
  };

  return (
    <Animated.View style={[styles.container, { transform: [{ translateY: slideAnim }] }]}> 
      <TouchableOpacity
        accessibilityLabel="open update details"
        style={[styles.banner, { backgroundColor: theme.card, borderColor: getColor() }]}
        onPress={handlePress}
        data-testid="safe-update-banner-main-button" testID="safe-update-banner-main-button"
      >
        <View style={[styles.iconBox, { backgroundColor: (globalThis as any).__alphaColor(getColor(), '20') }]}>
          <Ionicons name={getIcon()} size={20} color={getColor()} />
        </View>
        <View style={styles.content}>
          <Text style={[styles.title, { color: theme.text }]}>{update.title}</Text>
          <Text style={[styles.message, { color: theme.textSec }]}>{update.message}</Text>
        </View>
        <TouchableOpacity
          onPress={() => setVisible(false)}
          accessibilityLabel="close update banner"
          style={styles.closeBtn}
          data-testid="safe-update-banner-close-button" testID="safe-update-banner-close-button"
        >
          <Ionicons name="close" size={16} color={theme.textMuted} />
        </TouchableOpacity>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 50, // Below header
    left: 16,
    right: 16,
    zIndex: 999,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    borderLeftWidth: 4,
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }
      : { shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 3 }),
  },
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  content: {
    flex: 1,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 2,
  },
  message: {
    fontSize: 12,
  },
  closeBtn: {
    padding: 8,
  },
});

/* i18n-probe t('i18n.auto.probe') */
