import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useSubscription } from '../context/SubscriptionContext';

interface UpgradeBannerProps {
  usagePercent?: number;
  featureName?: string;
  variant?: 'inline' | 'banner' | 'locked';
  requiredPlan?: 'basic' | 'premium';
}

export default function UpgradeBanner({ usagePercent, featureName, variant = 'banner', requiredPlan = 'premium' }: UpgradeBannerProps) {
  const { colors } = useTheme();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { canAccess, _plan, dailyUsagePercent } = useSubscription();
  const router = useRouter();

  if (canAccess(requiredPlan)) return null;

  const effectiveUsage = usagePercent ?? dailyUsagePercent;
  const isBasicRequired = requiredPlan === 'basic';
  const planLabel = isBasicRequired ? 'Basic' : 'Premium';

  if (variant === 'locked') {
    return (
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.warningSoft,
          borderRadius: 12,
          padding: 12,
        }}
        data-testid="upgrade-locked-banner" testID="upgrade-locked-banner"
      >
        <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="lock-closed" size={16} color={'var(--app-warning)'} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
            {featureName || 'This feature'} requires upgrade
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
            Upgrade to {planLabel} to unlock
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => router.push('/subscription/plans')}
          style={{ backgroundColor: colors.warning, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}
          data-testid="upgrade-locked-btn" testID="upgrade-locked-btn"
        >
          <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '800' }}>Upgrade</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (variant === 'inline') {
    return (
      <TouchableOpacity accessibilityLabel="Upgrade inline button"
        onPress={() => router.push('/subscription/plans')}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 6,
          paddingVertical: 6,
          paddingHorizontal: 10,
          borderRadius: 8,
          backgroundColor: colors.accentSoft,
          borderWidth: 1,
          borderColor: colors.accentSoft,
        }}
        data-testid="upgrade-inline-btn" testID="upgrade-inline-btn"
      >
        <Ionicons name="arrow-up-circle" size={14} color={'var(--app-primary)'} />
        <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '700' }}>Upgrade to unlock</Text>
      </TouchableOpacity>
    );
  }

  const showUsageWarning = effectiveUsage && effectiveUsage >= 80;

  return (
    <View
      style={{
        backgroundColor: showUsageWarning ? colors.warningSoft : colors.accentSoft,
        borderWidth: 1,
        borderColor: showUsageWarning ? colors.warningSoft : colors.accentSoft,
        borderRadius: 14,
        padding: 14,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
      }}
      data-testid="upgrade-banner" testID="upgrade-banner"
    >
      <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: showUsageWarning ? colors.warningSoft : colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons
          name={showUsageWarning ? 'warning' : 'rocket'}
          size={20}
          color={showUsageWarning ? 'var(--app-warning)' : 'var(--app-primary)'}
        />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
          {showUsageWarning
            ? `You've used ${effectiveUsage}% of your daily limit`
            : 'Unlock unlimited access'
          }
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
          {showUsageWarning
            ? 'Upgrade for unlimited access'
            : `Get ${planLabel} for all features, exports & automation`
          }
        </Text>
      </View>
      <TouchableOpacity accessibilityLabel="Upgrade banner button"
        onPress={() => router.push('/subscription/plans')}
        style={{
          backgroundColor: showUsageWarning ? colors.warning : colors.accent,
          paddingHorizontal: 14,
          paddingVertical: 8,
          borderRadius: 10,
        }}
        data-testid="upgrade-banner-btn" testID="upgrade-banner-btn"
      >
        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>Upgrade</Text>
      </TouchableOpacity>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
