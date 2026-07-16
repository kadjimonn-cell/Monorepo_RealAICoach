import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRealtime } from '../context/RealtimeContext';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';

export function RealtimeReconnectBanner() {
  const { connectionHealth, reconnectNow } = useRealtime();
  const { colors } = useTheme();
  const { t } = useTranslation();

  if (!connectionHealth.autoReconnectPaused) return null;

  const titleRaw = t('realtime.reconnectPaused.title');
  const subtitleRaw = t('realtime.reconnectPaused.subtitle');
  const buttonRaw = t('realtime.reconnectPaused.button');
  const title = titleRaw !== 'realtime.reconnectPaused.title' ? titleRaw : 'Live updates paused';
  const subtitle = subtitleRaw !== 'realtime.reconnectPaused.subtitle'
    ? subtitleRaw
    : 'Auto-reconnect stopped after repeated failures. Tap to reconnect.';
  const buttonLabel = buttonRaw !== 'realtime.reconnectPaused.button' ? buttonRaw : 'Reconnect';

  return (
    <View style={styles.wrap} data-testid="realtime-reconnect-banner" testID="realtime-reconnect-banner">
      <View style={[styles.card, { backgroundColor: colors.cardAlt, borderColor: colors.warning }]}> 
        <Text style={[styles.title, { color: colors.primaryText }]} data-testid="realtime-reconnect-banner-title" testID="realtime-reconnect-banner-title">{title}</Text>
        <Text style={[styles.subtitle, { color: colors.textSec }]} data-testid="realtime-reconnect-banner-subtitle" testID="realtime-reconnect-banner-subtitle">{subtitle}</Text>
        <Pressable
          onPress={reconnectNow}
          style={[styles.button, { backgroundColor: colors.primary }]}
          data-testid="realtime-reconnect-button"
          testID="realtime-reconnect-button"
        >
          <Text style={[styles.buttonLabel, { color: colors.primaryText }]}>{buttonLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    right: 20,
    bottom: 108,
    zIndex: 10001,
  },
  card: {
    width: '100%',
    maxWidth: 960,
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
  },
  title: {
    fontSize: 13,
    fontWeight: '800',
  },
  subtitle: {
    marginTop: 4,
    fontSize: 11,
    lineHeight: 16,
  },
  button: {
    marginTop: 10,
    borderRadius: 999,
    paddingVertical: 8,
    alignItems: 'center',
  },
  buttonLabel: {
    fontSize: 12,
    fontWeight: '700',
  },
});
