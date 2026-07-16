import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Animated, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useConfig } from '../context/ConfigContext';
import { useFeatures } from '../context/FeaturesContext';
import { useTheme } from '../context/ThemeContext';
import { recordShellHealthEvent } from '../services/shellHealthMonitor';
import {
  DEFAULT_STARTUP_RECOVERY_DELAY_MS,
  STARTUP_RECOVERY_DELAY_KEY,
  normalizeStartupRecoveryDelay,
} from '../constants/startupRecovery';

const SILENT_STARTUP_RECOVERY_UI = true;

export default function StartupRecoveryBanner() {
  const { refreshConfig, recoveryActive: configRecoveryActive, source: configSource } = useConfig();
  const { refreshFeatures, recoveryActive: featuresRecoveryActive, source: featuresSource } = useFeatures();
  const { colors } = useTheme();
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [autoRefreshTriggered, setAutoRefreshTriggered] = useState(false);
  const [autoRefreshDelayMs, setAutoRefreshDelayMs] = useState(DEFAULT_STARTUP_RECOVERY_DELAY_MS);
  const slideAnim = useState(new Animated.Value(-120))[0];

  const activeSources = useMemo(() => {
    const items: string[] = [];
    if (configRecoveryActive) items.push(`Config: ${configSource}`);
    if (featuresRecoveryActive) items.push(`Features: ${featuresSource}`);
    return items;
  }, [configRecoveryActive, configSource, featuresRecoveryActive, featuresSource]);

  const visible = activeSources.length > 0 && !dismissed;

  useEffect(() => {
    if (visible) {
      Animated.timing(slideAnim, { toValue: 0, duration: 260, useNativeDriver: Platform.OS !== 'web' }).start();
      recordShellHealthEvent('startup_recovery_banner_visible', { config_source: configSource, features_source: featuresSource });
      return;
    }
    Animated.timing(slideAnim, { toValue: -120, duration: 220, useNativeDriver: Platform.OS !== 'web' }).start();
  }, [configSource, featuresSource, slideAnim, visible]);

  useEffect(() => {
    if (activeSources.length === 0) {
      setDismissed(false);
      setAutoRefreshTriggered(false);
    }
  }, [activeSources.length]);

  useEffect(() => {
    let mounted = true;
    const loadDelay = async () => {
      try {
        const localValue = Platform.OS === 'web' && typeof window !== 'undefined'
          ? window.localStorage.getItem(STARTUP_RECOVERY_DELAY_KEY)
          : null;
        const stored = localValue || (await AsyncStorage.getItem(STARTUP_RECOVERY_DELAY_KEY));
        if (mounted) setAutoRefreshDelayMs(normalizeStartupRecoveryDelay(stored));
      } catch {
        if (mounted) setAutoRefreshDelayMs(DEFAULT_STARTUP_RECOVERY_DELAY_MS);
      }
    };

    loadDelay();

    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      return () => {
        mounted = false;
      };
    }

    const onDelayUpdate = (event: any) => {
      const next = normalizeStartupRecoveryDelay(event?.detail?.delayMs);
      setAutoRefreshDelayMs(next);
    };
    window.addEventListener('startup-recovery-delay-changed', onDelayUpdate as any);
    return () => {
      mounted = false;
      window.removeEventListener('startup-recovery-delay-changed', onDelayUpdate as any);
    };
  }, []);

  const handleRefresh = useCallback(async (trigger: 'manual' | 'auto' = 'manual') => {
    setBusy(true);
    recordShellHealthEvent('startup_recovery_banner_refresh_clicked', {
      trigger,
      config_source: configSource,
      features_source: featuresSource,
    });
    try {
      await Promise.all([refreshConfig(), refreshFeatures()]);
      recordShellHealthEvent('startup_recovery_banner_refresh_completed', {
        trigger,
        config_source: configSource,
        features_source: featuresSource,
      });
    } finally {
      setBusy(false);
      setDismissed(true);
      recordShellHealthEvent('startup_recovery_banner_auto_dismissed', {
        trigger,
        auto_refresh_delay_ms: autoRefreshDelayMs,
        config_source: configSource,
        features_source: featuresSource,
      });
    }
  }, [autoRefreshDelayMs, configSource, featuresSource, refreshConfig, refreshFeatures]);

  useEffect(() => {
    if (!visible || busy || autoRefreshTriggered) return;
    const timer = setTimeout(() => {
      setAutoRefreshTriggered(true);
      void handleRefresh('auto');
    }, autoRefreshDelayMs);
    return () => clearTimeout(timer);
  }, [autoRefreshDelayMs, autoRefreshTriggered, busy, handleRefresh, visible]);

  if (!visible || SILENT_STARTUP_RECOVERY_UI) return null;

  return (
    <Animated.View style={[styles.wrap, { transform: [{ translateY: slideAnim }] }]}>
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: `${colors.warning}66` }]} data-testid="startup-recovery-banner" testID="startup-recovery-banner">
        <View style={[styles.iconBox, { backgroundColor: `${colors.warning}18` }]}>
          <Ionicons name="shield-checkmark" size={16} color={colors.warningText} />
        </View>
        <View style={styles.content}>
          <Text style={[styles.title, { color: colors.text }]} data-testid="startup-recovery-banner-title" testID="startup-recovery-banner-title">Startup recovery mode is active</Text>
          <Text style={[styles.copy, { color: colors.textSec }]} data-testid="startup-recovery-banner-copy" testID="startup-recovery-banner-copy">
            Loaded safely from cached startup data while live services reconnect. Route monitoring is running in the background.
          </Text>
          <View style={styles.pillRow} data-testid="startup-recovery-banner-sources" testID="startup-recovery-banner-sources">
            {activeSources.map((item) => (
              <View key={item} style={[styles.pill, { backgroundColor: colors.bgAlt, borderColor: colors.border }]} data-testid={`startup-recovery-source-${item.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`} testID={`startup-recovery-source-${item.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`}>
                <Text style={[styles.pillText, { color: colors.textSec }]}>{item}</Text>
              </View>
            ))}
          </View>
        </View>
        <View style={styles.actions}>
          <TouchableOpacity onPress={() => void handleRefresh('manual')} disabled={busy} style={[styles.primaryBtn, { backgroundColor: colors.warning }]} data-testid="startup-recovery-refresh-button" testID="startup-recovery-refresh-button">
            <Text style={styles.primaryBtnText}>{busy ? 'Refreshing…' : 'Refresh now'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setDismissed(true)} style={[styles.dismissBtn, { borderColor: colors.border }]} data-testid="startup-recovery-dismiss-button" testID="startup-recovery-dismiss-button">
            <Text style={[styles.dismissBtnText, { color: colors.textMuted }]}>Dismiss</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: 96,
    left: 16,
    right: 16,
    zIndex: 998,
  },
  card: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 16px 48px rgba(15,23,42,0.18)' }
      : { shadowColor: 'var(--app-text)', shadowOpacity: 0.12, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 6 }),
  },
  iconBox: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    flex: 1,
    gap: 6,
  },
  title: {
    fontSize: 14,
    fontWeight: '800',
  },
  copy: {
    fontSize: 12,
    lineHeight: 18,
  },
  pillRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 2,
  },
  pill: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  pillText: {
    fontSize: 10,
    fontWeight: '700',
  },
  actions: {
    gap: 8,
    alignItems: 'stretch',
  },
  primaryBtn: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  primaryBtnText: {
    fontSize: 11,
    fontWeight: '900',
  },
  dismissBtn: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  dismissBtnText: {
    fontSize: 11,
    fontWeight: '800',
  },
});
/* i18n-probe t('i18n.auto.probe') */
