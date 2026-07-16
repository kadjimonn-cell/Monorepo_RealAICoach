import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useABVariant } from '../hooks/useABVariant';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const POLL_INTERVAL = 60_000; // refresh every 60s

function getBarColor(ratio: number): string {
  if (ratio < 0.5) return 'var(--app-success)';   // green
  if (ratio < 0.8) return 'var(--app-warning)';   // amber
  return 'var(--app-error)';                     // red
}

export default function UsageLimitIndicator({ compact }: { compact?: boolean }) {
  const { colors } = useTheme();
  const { user, isAuthenticated } = useAuth();
  const router = useRouter();
  const [used, setUsed] = useState(0);
  const [limit, setLimit] = useState(3);
  const [loaded, setLoaded] = useState(false);
  const barAnim = useRef(new Animated.Value(0)).current;
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // A/B testing integration
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { getConfig, trackEvent, isActive: _hasABTest } = useABVariant('usage_indicator');

  const fetchUsage = useCallback(async () => {
    try {
      const res = await api.get('/subscriptions/status');
      const d = res.data;
      setUsed(d.daily_conversations_used ?? 0);
      setLimit(d.daily_conversation_limit ?? 3);
      setLoaded(true);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/UsageLimitIndicator.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchUsage();
    timerRef.current = setInterval(fetchUsage, POLL_INTERVAL);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isAuthenticated, fetchUsage]);

  useEffect(() => {
    if (!loaded) return;
    const isUnlimited = limit === -1;
    const target = isUnlimited ? 0.15 : Math.min(used / Math.max(limit, 1), 1);
    Animated.timing(barAnim, { toValue: target, duration: 500, useNativeDriver: false }).start();
  }, [used, limit, loaded, barAnim]);

  if (!isAuthenticated || !loaded) return null;

  const isUnlimited = limit === -1;
  const ratio = isUnlimited ? 0 : used / Math.max(limit, 1);
  const barColor = isUnlimited ? 'var(--app-success)' : getBarColor(ratio);
  const atLimit = !isUnlimited && used >= limit;
  const nearLimit = !isUnlimited && ratio >= 0.8 && !atLimit;
  const plan = user?.subscription_plan || 'free';
  const showUpgrade = plan !== 'premium' && (nearLimit || atLimit);

  // A/B variant overrides
  const upgradeLabel = getConfig('upgrade_text', 'Upgrade');
  const limitText = getConfig('limit_text', atLimit ? 'Limit reached' : `${limit - used} left today`);

  const barWidth = barAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  return (
    <View
      data-testid="usage-limit-indicator" testID="usage-limit-indicator"
      style={[
        styles.container,
        { backgroundColor: colors.surfaceHover, borderColor: atLimit ? colors.errorSoft : colors.border },
      ]}
    >
      {/* Top row: icon + label + count */}
      <View style={styles.topRow}>
        <Ionicons
          name={isUnlimited ? 'infinite' : atLimit ? 'alert-circle' : 'chatbubble-ellipses-outline'}
          size={14}
          color={atLimit ? colors.error : colors.textMuted}
        />
        <Text
          style={[styles.label, { color: colors.textSec }]}
          data-testid="usage-limit-label" testID="usage-limit-label"
        >
          {isUnlimited ? 'Unlimited' : 'Conversations'}
        </Text>
        <Text
          style={[styles.count, { color: atLimit ? colors.error : colors.text }]}
          data-testid="usage-limit-count" testID="usage-limit-count"
        >
          {isUnlimited ? (
            <>{used} today</>
          ) : (
            <>{used}<Text style={{ color: colors.textMuted, fontWeight: '500' }}>/{limit}</Text></>
          )}
        </Text>
      </View>

      {/* Progress bar */}
      <View style={[styles.barTrack, { backgroundColor: colors.bgAlt }]}>
        <Animated.View
          style={[
            styles.barFill,
            { backgroundColor: barColor, width: barWidth },
          ]}
          data-testid="usage-limit-bar" testID="usage-limit-bar"
        />
      </View>

      {/* Bottom row: status message + upgrade link */}
      {(showUpgrade || atLimit) && (
        <View style={styles.bottomRow}>
          <Text style={[styles.statusText, { color: atLimit ? colors.error : colors.warning }]}>
            {limitText}
          </Text>
          <TouchableOpacity
            onPress={() => { trackEvent('click', { plan, used, limit }); router.push('/subscription/plans'); }}
            data-testid="usage-upgrade-link" testID="usage-upgrade-link"
            activeOpacity={0.7}
            style={[styles.upgradeChip, { backgroundColor: (globalThis as any).__alphaColor(barColor, '18') }]}
          >
            <Ionicons name="arrow-up-circle" size={12} color={barColor} />
            <Text style={[styles.upgradeText, { color: barColor }]}>{upgradeLabel}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 5,
  },
  label: {
    fontSize: 11,
    fontWeight: '600',
    flex: 1,
  },
  count: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: -0.2,
  },
  barTrack: {
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 2,
    ...(Platform.OS === 'web' ? { transition: 'background-color 0.3s ease' } as any : {}),
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 5,
  },
  statusText: {
    fontSize: 10,
    fontWeight: '600',
  },
  upgradeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 6,
  },
  upgradeText: {
    fontSize: 10,
    fontWeight: '700',
  },
});

/* i18n-probe t('i18n.auto.probe') */
