import React from 'react';
import { LinearGradient } from 'expo-linear-gradient';
import { Text, View } from 'react-native';
import { BillingHeroPill } from '../paymentHistory/BillingRoutePrimitives';

type Props = {
  colors: any;
  isWide: boolean;
  tx: (key: string, fallback: string) => string;
  t: (key: string) => string;
  activeStepLabel: string;
  activeStepDesc: string;
  openJobs: number | null;
};

export const JobSearchHero = ({ colors, isWide, tx, t, activeStepLabel, activeStepDesc, openJobs }: Props) => {
  return (
    <LinearGradient
      colors={[colors.primary, colors.info]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={{ borderRadius: 22, padding: isWide ? 24 : 20 }}
      data-testid="job-search-hero"
      testID="job-search-hero"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: colors.primaryText + 'D9', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>
            {tx('jobSearch.hero.eyebrow', 'AI career workspace')}
          </Text>
          <Text style={{ color: colors.primaryText, fontSize: isWide ? 34 : 28, fontWeight: '900', letterSpacing: -0.9, marginTop: 10 }} data-testid="job-search-title" testID="job-search-title">
            {t('nav.jobSearch')}
          </Text>
          <Text style={{ color: colors.primaryText + 'D9', fontSize: 13, lineHeight: 20, marginTop: 8 }}>
            {tx('jobSearch.hero.subtitle', 'Evaluate your fit, generate tailored CVs and cover letters, validate against ATS parsers, and track every application.')}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <BillingHeroPill label={tx('jobSearch.hero.openJobs', 'Open jobs')} value={openJobs == null ? '—' : String(openJobs)} colors={colors} testId="job-search-open-jobs-pill" />
          <BillingHeroPill label={tx('jobSearch.hero.activeStep', 'Active step')} value={activeStepLabel} colors={colors} testId="job-search-active-step-pill" />
        </View>
      </View>

      <View style={{ marginTop: 18, borderRadius: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primaryText, '24'), backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '10'), padding: 14 }} data-testid="job-search-active-step-card" testID="job-search-active-step-card">
        <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>
          {tx('jobSearch.hero.activeWorkspace', 'Active workspace')}
        </Text>
        <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800', marginTop: 6 }}>{activeStepLabel}</Text>
        <Text style={{ color: colors.primaryText + 'D9', fontSize: 12, lineHeight: 18, marginTop: 6 }}>{activeStepDesc}</Text>
      </View>
    </LinearGradient>
  );
};
