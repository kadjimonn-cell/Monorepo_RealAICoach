import React from 'react';
import { LinearGradient } from 'expo-linear-gradient';
import { Text, View } from 'react-native';
import { BillingHeroPill } from '../paymentHistory/BillingRoutePrimitives';

type Props = {
  colors: any;
  isWide: boolean;
  tx: (key: string, fallback: string) => string;
  t: (key: string) => string;
  roleMode: string;
  activeTabLabel: string;
  activeTabDesc: string;
};

export const JobsPortalHeroSection = ({
  colors,
  isWide,
  tx,
  t,
  roleMode,
  activeTabLabel,
  activeTabDesc,
}: Props) => {
  return (
    <LinearGradient
      colors={[colors.primary, colors.info]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ borderRadius: 22, padding: isWide ? 24 : 20 }}
      data-testid="jobs-portal-hero"
      testID="jobs-portal-hero"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: colors.primaryText + 'D9', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>
            {tx('jobsPortal.hero.eyebrow', 'Enterprise hiring workspace')}
          </Text>
          <Text style={{ color: colors.primaryText, fontSize: isWide ? 34 : 28, fontWeight: '900', letterSpacing: -0.9, marginTop: 10 }} data-testid="jobs-portal-title" testID="jobs-portal-title">
            {t('nav.employerPortal')}
          </Text>
          <Text style={{ color: colors.primaryText + 'D9', fontSize: 13, lineHeight: 20, marginTop: 8 }}>
            {tx('jobsPortal.hero.subtitle', 'Operate candidate tracking, job discovery, and employer hiring workflows from one live platform route.')}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <BillingHeroPill label={tx('jobsPortal.hero.roleMode', 'Role mode')} value={roleMode} colors={colors} testId="jobs-portal-role-pill" />
          <BillingHeroPill label={tx('jobsPortal.hero.activeTab', 'Active tab')} value={activeTabLabel} colors={colors} testId="jobs-portal-active-tab-pill" />
        </View>
      </View>

      <View style={{ marginTop: 18, borderRadius: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primaryText, '24'), backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '10'), padding: 14 }} data-testid="jobs-portal-active-tab-card" testID="jobs-portal-active-tab-card">
        <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>
          {tx('jobsPortal.hero.activeWorkspace', 'Active workspace')}
        </Text>
        <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800', marginTop: 6 }}>{activeTabLabel}</Text>
        <Text style={{ color: colors.primaryText + 'D9', fontSize: 12, lineHeight: 18, marginTop: 6 }}>{activeTabDesc}</Text>
      </View>
    </LinearGradient>
  );
};
