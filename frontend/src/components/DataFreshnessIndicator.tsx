import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface Props {
  lastUpdated: Date | null;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  accentColor?: string;
  textColor?: string;
  mutedColor?: string;
}

export default function DataFreshnessIndicator({
  lastUpdated,
  onRefresh,
  isRefreshing,
  accentColor,
  textColor,
  mutedColor,
}: Props) {
  const { colors } = useTheme();
  const [timeAgo, setTimeAgo] = useState('');
  const resolvedAccent = accentColor || colors.primary;
  const resolvedText = textColor || colors.textSec;
  const resolvedMuted = mutedColor || colors.textMuted;

  useEffect(() => {
    if (!lastUpdated) return;
    const update = () => {
      const diff = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
      if (diff < 5) setTimeAgo('just now');
      else if (diff < 60) setTimeAgo(`${diff}s ago`);
      else if (diff < 3600) setTimeAgo(`${Math.floor(diff / 60)}m ago`);
      else setTimeAgo(`${Math.floor(diff / 3600)}h ago`);
    };
    update();
    const id = setInterval(update, 10000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  const isStale = lastUpdated && (Date.now() - lastUpdated.getTime()) > 120000;

  return (
    <View style={s.container} data-testid="data-freshness-indicator" testID="data-freshness-indicator">
      <View style={[s.dot, { backgroundColor: isRefreshing ? colors.warning : isStale ? colors.error : colors.success }]} />
      <Text style={[s.label, { color: resolvedMuted || resolvedText }]}>
        {isRefreshing ? 'Updating...' : lastUpdated ? `Updated ${timeAgo}` : 'Loading...'}
      </Text>
      {onRefresh && !isRefreshing && (
        <TouchableOpacity onPress={onRefresh} style={s.refreshBtn} data-testid="freshness-refresh-btn" testID="freshness-refresh-btn">
          <Ionicons name="refresh" size={12} color={resolvedAccent} />
        </TouchableOpacity>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { fontSize: 11, fontWeight: '500' },
  refreshBtn: { padding: 4 },
});

/* i18n-probe t('i18n.auto.probe') */
