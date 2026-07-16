import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Image, Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import AppShell from '../AppShell';
import { FadeSlideIn, ReferralsSkeleton } from '../SkeletonLoaders';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import { getTestProps } from '../../utils/testProps';
import { BillingActionButton, BillingHeroPill, BillingMetricCard, BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { getFrontendPlanName, getFrontendPlanPrice } from '../../config/pricingPolicy';

const REFERRAL_REFRESH_MS = 60000;

const formatCurrency = (value: number) => `$${Number(value || 0).toFixed(2)}`;

export default function ReferralsV2() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);
  const [referrals, setReferrals] = useState<any[]>([]);
  const [credits, setCredits] = useState<any>(null);
  const [milestones, setMilestones] = useState<any>(null);
  const [sharingKit, setSharingKit] = useState<any>(null);
  const [channelAnalytics, setChannelAnalytics] = useState<any>(null);
  const [challenges, setChallenges] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [templateCopied, setTemplateCopied] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState('twitter');
  const [workspace, setWorkspace] = useState<'growth' | 'earnings' | 'missions' | 'history'>('growth');

  const palette = useMemo(() => ({
    ...colors,
    heroStart: colors.text,
    heroMid: colors.primary,
    heroEnd: colors.info,
  }), [colors]);

  const loadData = useCallback(async (refreshMode = false) => {
    try {
      if (!refreshMode) setLoading(true);
      const [statsRes, refsRes, creditsRes, milestonesRes, sharingRes, channelRes, challengeRes] = await Promise.all([
        api.get('/referrals/my-stats', { skipDedupe: true }),
        api.get('/referrals/my-referrals', { skipDedupe: true }),
        api.get('/referrals/my-credits', { skipDedupe: true }),
        api.get('/referrals/my-milestones', { skipDedupe: true }),
        api.get('/referrals/sharing-kit', { skipDedupe: true }).catch(() => ({ data: null })),
        api.get('/referrals/my-channel-analytics', { skipDedupe: true }).catch(() => ({ data: null })),
        api.get('/referrals/my-challenges', { skipDedupe: true }).catch(() => ({ data: null })),
      ]);
      setStats(statsRes.data || null);
      setReferrals(refsRes.data?.referrals || []);
      setCredits(creditsRes.data || null);
      setMilestones(milestonesRes.data || null);
      setSharingKit(sharingRes.data || null);
      setChannelAnalytics(channelRes.data || null);
      setChallenges(challengeRes.data || null);
    } catch (error) {
      console.warn('Referral data error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (Platform.OS === 'web' && typeof document !== 'undefined' && document.hidden) return;
      void loadData(true);
    }, REFERRAL_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadData]);

  const copyText = async (value: string, onDone: () => void) => {
    if (!value) return;
    try {
      if (Platform.OS === 'web' && navigator.clipboard) {
        await navigator.clipboard.writeText(value);
      }
      onDone();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsV2.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const copyLink = async () => {
    await copyText(stats?.referral_link || '', () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    });
  };

  const copyTemplate = async (text: string) => {
    await copyText(text, () => {
      setTemplateCopied(true);
      window.setTimeout(() => setTemplateCopied(false), 2200);
    });
  };

  const openShareUrl = (url: string) => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.open(url, '_blank');
    }
  };

  const tier = stats?.tier;
  const nextTier = stats?.next_tier;
  const tierTone = tier?.color || colors.primary;
  const activeTemplateData = sharingKit?.templates?.[activeTemplate];
  const trackedChannels = (channelAnalytics?.channels || []).filter((channel: any) => channel.signups > 0 || channel.clicks > 0);
  const bestTrackedVolume = Math.max(...trackedChannels.map((channel: any) => channel.signups), 1);
  const challengeCount = Number((challenges?.challenges || []).length || 0);
  const sectionVisible = useCallback((section: 'tier' | 'sharing' | 'missions' | 'commission' | 'history') => {
    const map: Record<string, string[]> = {
      growth: ['sharing', 'history'],
      earnings: ['tier', 'commission', 'history'],
      missions: ['missions', 'history'],
      history: ['history'],
    };
    return (map[workspace] || []).includes(section);
  }, [workspace]);

  if (loading) {
    return (
      <AppShell>
        <ReferralsSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <FadeSlideIn>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: isMobile ? 16 : 24, paddingBottom: 56 }} {...getTestProps('referrals-v2-scroll')}>
          <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', gap: 12 }}>
            <LinearGradient colors={[palette.heroStart, palette.heroMid, palette.heroEnd]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ borderRadius: 24, padding: isMobile ? 18 : 22, borderWidth: 1, borderColor: palette.border }} {...getTestProps('referral-page-header')}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 220 }}>
                  <Text style={{ color: palette.primaryText + 'D9', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('referrals.hero.eyebrow', 'Enterprise referral program')}</Text>
                  <Text style={{ color: palette.primaryText, fontSize: isMobile ? 28 : 34, fontWeight: '900', letterSpacing: -0.9, marginTop: 10 }} {...getTestProps('referral-hero-title')}>
                    {tx('referrals.hero.title', 'Referral Program')}
                  </Text>
                  <Text style={{ color: palette.primaryText + 'D9', fontSize: 13, lineHeight: 20, marginTop: 8 }} {...getTestProps('referral-hero-subtitle')}>
                    {tx('referrals.hero.subtitle', 'Share your verified referral link, track pipeline health, and monitor credits, milestones, and recurring commission with platform data only.')}
                  </Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                  <BillingHeroPill label={tx('referrals.hero.discount', 'Friend discount')} value={`${Math.round(Number(stats?.discount_rate || 0) * 100)}%`} colors={palette} testId="referral-hero-discount-pill" />
                  <BillingHeroPill label={tx('referrals.hero.commission', 'Commission rate')} value={`${Math.round(Number(stats?.commission_rate || 0) * 100)}%`} colors={palette} testId="referral-hero-commission-pill" />
                </View>
              </View>

              <View style={{ marginTop: 18, borderRadius: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(palette.primaryText, '24'), backgroundColor: (globalThis as any).__alphaColor(palette.primaryText, '10'), padding: 14 }} {...getTestProps('referral-link-panel')}>
                <Text style={{ color: palette.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('referrals.hero.yourReferralLink', 'Your Referral Link')}</Text>
                <Text style={{ color: palette.primaryText, fontSize: 14, fontWeight: '800', marginTop: 6 }} numberOfLines={1} {...getTestProps('referral-link-text')}>
                  {stats?.referral_link || tx('referrals.common.loading', 'Loading...')}
                </Text>
                <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
                  <BillingActionButton label={copied ? tx('referrals.actions.copied', 'Copied!') : tx('referrals.actions.copy', 'Copy Link')} onPress={() => { void copyLink(); }} icon={copied ? 'checkmark' : 'copy-outline'} colors={palette} testId="copy-referral-link-btn" variant="secondary" />
                  {sharingKit?.templates?.twitter && <BillingActionButton label={tx('referrals.channels.twitter', 'Twitter')} onPress={() => openShareUrl(sharingKit.templates.twitter.share_url)} icon="logo-twitter" colors={palette} testId="share-twitter" variant="subtle" />}
                  {sharingKit?.templates?.linkedin && <BillingActionButton label={tx('referrals.channels.linkedin', 'LinkedIn')} onPress={() => openShareUrl(sharingKit.templates.linkedin.share_url)} icon="logo-linkedin" colors={palette} testId="share-linkedin" variant="subtle" />}
                  {sharingKit?.templates?.whatsapp && <BillingActionButton label={tx('referrals.channels.whatsapp', 'WhatsApp')} onPress={() => openShareUrl(sharingKit.templates.whatsapp.share_url)} icon="logo-whatsapp" colors={palette} testId="share-whatsapp" variant="subtle" />}
                </View>
              </View>
            </LinearGradient>

            <BillingSectionCard colors={palette} testId="referral-workspace-switcher">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 220 }}>
                  <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.workspace.title', 'Referral Command Center')}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>
                    {tx('referrals.workspace.subtitle', 'Switch between Growth, Earnings, Missions, and History workspaces for focused execution.')}
                  </Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  {[
                    { id: 'growth', label: tx('referrals.workspace.growth', 'Growth Hub') },
                    { id: 'earnings', label: tx('referrals.workspace.earnings', 'Earnings Wallet') },
                    { id: 'missions', label: tx('referrals.workspace.missions', 'Missions') },
                    { id: 'history', label: tx('referrals.workspace.history', 'History') },
                  ].map((tab) => {
                    const active = workspace === tab.id;
                    return (
                      <TouchableOpacity
                        key={tab.id}
                        onPress={() => setWorkspace(tab.id as any)}
                        style={{
                          borderRadius: 999,
                          borderWidth: 1,
                          borderColor: active ? `${palette.primary}55` : palette.border,
                          backgroundColor: active ? `${palette.primary}18` : palette.bgSoft,
                          paddingHorizontal: 14,
                          paddingVertical: 8,
                        }}
                        {...getTestProps(`referral-workspace-tab-${tab.id}`)}
                      >
                        <Text style={{ color: active ? palette.primary : palette.text, fontSize: 12, fontWeight: '800' }}>{tab.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>

              <View style={{ marginTop: 14, borderRadius: 14, borderWidth: 1, borderColor: `${palette.info}44`, backgroundColor: `${palette.info}12`, padding: 12 }} {...getTestProps('referral-growth-loop-panel')}>
                <Text style={{ color: palette.text, fontSize: 12, fontWeight: '900' }}>
                  {tx('referrals.workspace.loopTitle', 'Growth Loop Status')}: {stats?.active_subscribers || 0} {tx('referrals.workspace.liveSubscribers', 'active subscribers')}
                </Text>
                <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 6 }}>
                  {tx('referrals.workspace.loopBody', 'Next boost unlocked when you hit your next milestone. Keep sharing daily to compound recurring commission.')}
                </Text>
                <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 6 }} {...getTestProps('referral-growth-loop-meta')}>
                  {challengeCount} {tx('referrals.workspace.activeChallenges', 'active challenges')} · {stats?.conversion_rate || 0}% {tx('referrals.workspace.currentConversion', 'current conversion')}
                </Text>
              </View>
            </BillingSectionCard>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <BillingMetricCard label={tx('referrals.kpi.totalReferrals', 'Total referrals')} value={String(stats?.total_signups || 0)} helper={`${stats?.total_clicks || 0} ${tx('referrals.kpi.linkClicks', 'link clicks')}`} colors={palette} icon="people-outline" testId="referral-kpi-total-referrals" />
              <BillingMetricCard label={tx('referrals.kpi.activeSubscribers', 'Active subscribers')} value={String(stats?.active_subscribers || 0)} helper={`${stats?.conversion_rate || 0}% ${tx('referrals.kpi.conversion', 'conversion')}`} colors={palette} icon="checkmark-done-outline" testId="referral-kpi-active-subscribers" />
              <BillingMetricCard label={tx('referrals.kpi.totalEarnings', 'Total earnings')} value={formatCurrency(stats?.total_earnings || 0)} helper={`${formatCurrency(stats?.monthly_earnings || 0)}/${tx('referrals.kpi.perMonth', 'mo')} ${tx('referrals.kpi.recurring', 'recurring')}`} colors={palette} icon="wallet-outline" testId="referral-kpi-total-earnings" />
              <BillingMetricCard label={tx('referrals.kpi.nextTier', 'Next tier')} value={nextTier?.name || tx('referrals.tier.maxTier', 'Top tier reached')} helper={nextTier ? `${nextTier.referrals_needed} ${tx('referrals.tier.referralsNeeded', 'referrals needed')}` : tx('referrals.tier.noFurtherTier', 'No higher tier available')} colors={palette} icon="trending-up-outline" testId="referral-kpi-next-tier" />
            </View>

            {sectionVisible('tier') && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <BillingSectionCard colors={palette} testId="referral-tier-status-card" style={{ flex: 1.2, minWidth: 320 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.tier.yourTier', 'Tier status')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 16 }}>
                  <View style={{ width: 54, height: 54, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(tierTone, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(tierTone, '44') }}>
                    <Ionicons name="shield-outline" size={24} color={tierTone} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: tier?.color || palette.text, fontSize: 24, fontWeight: '900' }} {...getTestProps('referral-tier-name')}>{tier?.name || tx('referrals.tier.starter', 'Starter')}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 4 }}>{Math.round(Number(tier?.commission || 0.3) * 100)}% {tx('referrals.tier.commissionRate', 'commission rate')}</Text>
                  </View>
                  {nextTier && (
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('referrals.tier.nextTier', 'Next tier')}</Text>
                      <Text style={{ color: nextTier.color || palette.text, fontSize: 14, fontWeight: '800', marginTop: 4 }}>{nextTier.name}</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>{nextTier.referrals_needed} {tx('referrals.tier.moreReferrals', 'more referrals')}</Text>
                    </View>
                  )}
                </View>

                <View style={{ marginTop: 18, gap: 10 }}>
                  {stats?.all_tiers?.map((item: any) => {
                    const isCurrent = tier?.id === item.id;
                    const achieved = Number(stats?.total_signups || 0) >= Number(item.min_referrals || 0);
                    return (
                      <View key={item.id} style={{ borderRadius: 14, borderWidth: 1, borderColor: isCurrent ? `${item.color}55` : palette.border, backgroundColor: isCurrent ? `${item.color}14` : palette.bgSoft, padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }} {...getTestProps(`tier-card-${item.id}`)}>
                        <View>
                          <Text style={{ color: isCurrent ? item.color : palette.text, fontSize: 13, fontWeight: '800' }}>{item.name}</Text>
                          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 4 }}>{item.min_referrals}+ {tx('referrals.tier.referrals', 'referrals')}</Text>
                        </View>
                        <View style={{ alignItems: 'flex-end' }}>
                          <Text style={{ color: isCurrent ? item.color : palette.text, fontSize: 16, fontWeight: '900' }}>{Math.round(Number(item.commission || 0) * 100)}%</Text>
                          <Text style={{ color: achieved ? colors.successText : palette.textMuted, fontSize: 10, marginTop: 2 }}>{achieved ? tx('referrals.tier.unlocked', 'Unlocked') : tx('referrals.tier.locked', 'Locked')}</Text>
                        </View>
                      </View>
                    );
                  })}
                </View>
              </BillingSectionCard>

              <BillingSectionCard colors={palette} testId="referral-credits-section" style={{ flex: 1, minWidth: 320 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.credits.title', 'Referral credits')}</Text>
                <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
                  <BillingMetricCard label={tx('referrals.credits.balance', 'Available balance')} value={formatCurrency(credits?.balance || 0)} helper={tx('referrals.credits.balanceHelper', 'Ready for future subscription renewals.')} colors={palette} icon="wallet-outline" testId="credit-balance-card" />
                  <BillingMetricCard label={tx('referrals.credits.earned', 'Total earned')} value={formatCurrency(credits?.total_earned || 0)} helper={tx('referrals.credits.earnedHelper', 'Commission and milestone bonuses earned so far.')} colors={palette} icon="cash-outline" testId="credit-earned-card" />
                  <BillingMetricCard label={tx('referrals.credits.applied', 'Applied to renewals')} value={formatCurrency(credits?.total_applied || 0)} helper={tx('referrals.credits.appliedHelper', 'Credits already applied to subscription billing.')} colors={palette} icon="swap-horizontal-outline" testId="credit-applied-card" />
                </View>

                {!!credits?.renewal_info && (
                  <View style={{ marginTop: 16, borderRadius: 16, borderWidth: 1, borderColor: credits.renewal_info.fully_covered ? `${colors.success}44` : palette.border, backgroundColor: credits.renewal_info.fully_covered ? `${colors.success}12` : palette.bgSoft, padding: 14 }} {...getTestProps('renewal-savings-card')}>
                    <Text style={{ color: palette.text, fontSize: 13, fontWeight: '900' }}>{credits.renewal_info.fully_covered ? tx('referrals.credits.covered', 'Next renewal fully covered') : tx('referrals.credits.renewalPreview', 'Upcoming renewal preview')}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: 12 }}>
                      <View><Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('referrals.credits.plan', 'Plan')}</Text><Text style={{ color: palette.text, fontSize: 15, fontWeight: '800', marginTop: 4 }}>{credits.renewal_info.plan}</Text></View>
                      <View><Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('referrals.credits.coverAmount', 'Credits cover')}</Text><Text style={{ color: colors.successText, fontSize: 15, fontWeight: '800', marginTop: 4 }}>{formatCurrency(credits.renewal_info.credits_will_cover)}</Text></View>
                      <View><Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('referrals.credits.remaining', 'You pay')}</Text><Text style={{ color: palette.text, fontSize: 15, fontWeight: '800', marginTop: 4 }}>{credits.renewal_info.fully_covered ? tx('referrals.credits.free', 'FREE') : formatCurrency(credits.renewal_info.remaining_after_credits)}</Text></View>
                    </View>
                  </View>
                )}
              </BillingSectionCard>
            </View>
            )}

            {sectionVisible('sharing') && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <BillingSectionCard colors={palette} testId="sharing-kit-section" style={{ flex: 1.3, minWidth: 340 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.sharingKit.title', 'Sharing Kit')}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('referrals.sharingKit.subtitle', 'Ready-to-share templates generated from your real referral code and link.')}</Text>

                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
                  {Object.entries(sharingKit?.templates || {}).map(([key, template]: [string, any]) => {
                    const active = activeTemplate === key;
                    return (
                      <TouchableOpacity key={key} onPress={() => { setActiveTemplate(key); setTemplateCopied(false); }} accessibilityLabel={template.platform} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: active ? `${template.color}16` : palette.bgSoft, borderWidth: 1, borderColor: active ? `${template.color}44` : palette.border, flexDirection: 'row', alignItems: 'center', gap: 6 }} {...getTestProps(`sharing-tab-${key}`)}>
                        <Ionicons name={template.icon as any} size={15} color={active ? template.color : palette.textMuted} />
                        <Text style={{ color: active ? template.color : palette.text, fontSize: 12, fontWeight: '800' }}>{template.platform}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                {activeTemplateData && (
                  <View style={{ marginTop: 16 }}>
                    <View style={{ borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.bgSoft, padding: 16 }} {...getTestProps('sharing-template-preview')}>
                      {!!activeTemplateData.subject && (
                        <View style={{ paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: palette.border, marginBottom: 10 }}>
                          <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('referrals.sharingKit.subject', 'Subject')}</Text>
                          <Text style={{ color: palette.text, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{activeTemplateData.subject}</Text>
                        </View>
                      )}
                      <Text style={{ color: palette.text, fontSize: 13, lineHeight: 20 }}>{activeTemplateData.text}</Text>
                      {!!activeTemplateData.char_limit && <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: 'right', marginTop: 8 }}>{activeTemplateData.text.length}/{activeTemplateData.char_limit}</Text>}
                    </View>

                    <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
                      <BillingActionButton label={templateCopied ? tx('referrals.actions.copied', 'Copied!') : tx('referrals.actions.copyText', 'Copy text')} onPress={() => { void copyTemplate(activeTemplateData.text); }} icon={templateCopied ? 'checkmark' : 'copy-outline'} colors={palette} testId="sharing-copy-btn" variant="subtle" />
                      <BillingActionButton label={tx('referrals.actions.openChannel', 'Open channel')} onPress={() => openShareUrl(activeTemplateData.share_url)} icon="open-outline" colors={palette} testId="sharing-open-btn" variant="secondary" />
                    </View>
                  </View>
                )}

                {!!sharingKit?.qr_code && (
                  <View style={{ marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: palette.border, flexDirection: isMobile ? 'column' : 'row', gap: 16, alignItems: isMobile ? 'flex-start' : 'center' }} {...getTestProps('sharing-qr-section')}>
                    <View style={{ borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 10 }}>
                      <Image source={{ uri: sharingKit.qr_code }} style={{ width: isMobile ? 100 : 120, height: isMobile ? 100 : 120 }} {...{ 'data-testid': 'sharing-qr-image', testID: 'sharing-qr-image' }} accessibilityLabel="QR Code" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.sharingKit.qrTitle', 'QR Code')}</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('referrals.sharingKit.qrSubtitle', 'Perfect for in-person sharing. Scan to open your referral link directly.')}</Text>
                      {Platform.OS === 'web' && (
                        <View style={{ marginTop: 12 }}>
                          <BillingActionButton label={tx('referrals.sharingKit.downloadQr', 'Download PNG')} onPress={() => {
                            const anchor = document.createElement('a');
                            anchor.href = sharingKit.qr_code;
                            anchor.download = `referral-qr-${sharingKit.referral_code}.png`;
                            anchor.click();
                          }} icon="download-outline" colors={palette} testId="qr-download-btn" variant="subtle" />
                        </View>
                      )}
                    </View>
                  </View>
                )}
              </BillingSectionCard>

              <BillingSectionCard colors={palette} testId="channel-performance-section" style={{ flex: 1, minWidth: 320 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.analytics.title', 'Channel Performance')}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('referrals.analytics.subtitle', 'See which sharing channels are driving clicks, signups, and revenue.')}</Text>
                {trackedChannels.length === 0 ? (
                  <View style={{ alignItems: 'center', paddingVertical: 28 }}>
                    <Ionicons name="bar-chart-outline" size={30} color={palette.textMuted} />
                    <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 10, textAlign: 'center' }}>{tx('referrals.analytics.empty', 'Share using the Sharing Kit to start tracking channel performance.')}</Text>
                  </View>
                ) : (
                  <View style={{ gap: 12, marginTop: 16 }}>
                    {trackedChannels.map((channel: any) => (
                      <View key={channel.channel} {...getTestProps(`channel-bar-${channel.channel}`)}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <View style={{ width: 30, height: 30, borderRadius: 10, backgroundColor: `${channel.color}18`, alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name={channel.icon as any} size={15} color={channel.color} />
                            </View>
                            <Text style={{ color: palette.text, fontSize: 13, fontWeight: '800' }}>{channel.label}</Text>
                          </View>
                          <Text style={{ color: palette.textMuted, fontSize: 11 }}>{channel.clicks} {tx('referrals.analytics.clicks', 'clicks')} · {channel.signups} {tx('referrals.analytics.signups', 'signups')}</Text>
                        </View>
                        <View style={{ height: 8, borderRadius: 999, backgroundColor: palette.bgSoft, overflow: 'hidden', marginTop: 8 }}>
                          <View style={{ width: `${Math.max((channel.signups / bestTrackedVolume) * 100, 3)}%` as any, height: '100%', borderRadius: 999, backgroundColor: channel.color }} />
                        </View>
                      </View>
                    ))}
                  </View>
                )}
              </BillingSectionCard>
            </View>
            )}

            {sectionVisible('missions') && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <BillingSectionCard colors={palette} testId="milestone-tracker-section" style={{ flex: 1, minWidth: 320 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.milestones.title', 'Milestone Rewards')}</Text>
                {!!milestones?.next_milestone && (
                  <View style={{ marginTop: 16, borderRadius: 16, borderWidth: 1, borderColor: `${colors.warning}44`, backgroundColor: `${colors.warning}12`, padding: 14 }} {...getTestProps('next-milestone-card')}>
                    <Text style={{ color: palette.text, fontSize: 13, fontWeight: '900' }}>{tx('referrals.milestones.next', 'Next milestone')}: {milestones.next_milestone.label}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 6 }}>{milestones.next_milestone.referrals_remaining} {tx('referrals.milestones.remaining', 'referrals remaining')} · {formatCurrency(milestones.next_milestone.bonus)} {tx('referrals.milestones.bonus', 'bonus')}</Text>
                  </View>
                )}
                <View style={{ gap: 10, marginTop: 16 }}>
                  {(milestones?.milestones || []).map((milestone: any) => (
                    <View key={milestone.id} style={{ borderRadius: 14, borderWidth: 1, borderColor: milestone.achieved ? `${colors.success}44` : palette.border, backgroundColor: milestone.achieved ? `${colors.success}12` : palette.bgSoft, padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }} {...getTestProps(`milestone-${milestone.id}`)}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                        <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: `${milestone.color}18`, alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name={milestone.achieved ? (milestone.icon as any) : 'lock-closed-outline'} size={18} color={milestone.achieved ? milestone.color : palette.textMuted} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: palette.text, fontSize: 13, fontWeight: '800' }}>{milestone.label}</Text>
                          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 4 }}>{milestone.referrals_required} {tx('referrals.milestones.referralsRequired', 'referrals')} · {milestone.referrals_remaining} {tx('referrals.milestones.remainingShort', 'remaining')}</Text>
                        </View>
                      </View>
                      <Text style={{ color: milestone.achieved ? colors.successText : milestone.color, fontSize: 15, fontWeight: '900' }}>{formatCurrency(milestone.bonus)}</Text>
                    </View>
                  ))}
                </View>
              </BillingSectionCard>

              <BillingSectionCard colors={palette} testId="challenge-program-section" style={{ flex: 1, minWidth: 320 }}>
                <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.challenges.title', 'Active Challenges')}</Text>
                {(challenges?.challenges || []).length === 0 ? (
                  <View style={{ alignItems: 'center', paddingVertical: 28 }} {...getTestProps('referral-challenges-empty')}>
                    <Ionicons name="flame-outline" size={30} color={palette.textMuted} />
                    <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 10, textAlign: 'center' }}>{tx('referrals.challenges.empty', 'No active challenges right now.')}</Text>
                  </View>
                ) : (
                  <View style={{ gap: 12, marginTop: 16 }}>
                    {challenges.challenges.map((challenge: any) => (
                      <View key={challenge.challenge_id} style={{ borderRadius: 14, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.bgSoft, padding: 12 }} {...getTestProps(`challenge-card-${challenge.challenge_id}`)}>
                        <Text style={{ color: palette.text, fontSize: 13, fontWeight: '800' }}>{challenge.title}</Text>
                        <Text style={{ color: palette.textMuted, fontSize: 11, lineHeight: 16, marginTop: 6 }}>{challenge.description}</Text>
                      </View>
                    ))}
                  </View>
                )}
              </BillingSectionCard>
            </View>
            )}

            {sectionVisible('commission') && (
            <BillingSectionCard colors={palette} testId="referral-commission-info">
              <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.commission.title', 'Commission Structure')}</Text>
              <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('referrals.commission.subtitle', 'Your current rate is applied to eligible subscription revenue according to your tier.')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 16 }}>
                {[
                  { testId: 'commission-basic-plan-card', plan: `${getFrontendPlanName('basic')} Plan`, price: getFrontendPlanPrice('basic', 'monthly'), accent: palette.primary },
                  { testId: 'commission-premium-plan-card', plan: `${getFrontendPlanName('premium')} Plan`, price: getFrontendPlanPrice('premium', 'monthly'), accent: palette.purpleText || palette.primary },
                ].map((item) => (
                  <View key={item.plan} style={{ flex: 1, minWidth: 220, borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.bgSoft, padding: 16 }} {...getTestProps(item.testId)}>
                    <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{item.plan}</Text>
                    <Text style={{ color: item.accent, fontSize: 24, fontWeight: '900', marginTop: 8 }}>{formatCurrency(item.price * Number(stats?.commission_rate || 0.3))}/{tx('referrals.commission.perMonth', 'mo')}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 6 }}>{Math.round(Number(stats?.commission_rate || 0.3) * 100)}% {tx('referrals.commission.ofPlan', 'of')} {formatCurrency(item.price)}/{tx('referrals.commission.perMonth', 'mo')}</Text>
                  </View>
                ))}
              </View>
            </BillingSectionCard>
            )}

            {sectionVisible('history') && (
            <BillingSectionCard colors={palette} testId="referral-history">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <View>
                  <Text style={{ color: palette.text, fontSize: 15, fontWeight: '900' }}>{tx('referrals.history.title', 'Referral History')}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{tx('referrals.history.subtitle', 'Track every referred account and its lifecycle status from click to subscription.')}</Text>
                </View>
                <BillingActionButton label={tx('referrals.actions.refresh', 'Refresh')} onPress={() => { setLoading(true); loadData(); }} icon="refresh-outline" colors={palette} testId="refresh-referrals-btn" variant="subtle" />
              </View>

              {referrals.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 40 }} {...getTestProps('referral-history-empty')}>
                  <Ionicons name="people-outline" size={32} color={palette.textMuted} />
                  <Text style={{ color: palette.text, fontSize: 16, fontWeight: '800', marginTop: 12 }}>{tx('referrals.history.emptyTitle', 'No Referrals Yet')}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: 'center', marginTop: 8, maxWidth: 420 }}>{tx('referrals.history.emptySubtitle', 'Share your referral link to start earning recurring commission on every subscription.')}</Text>
                </View>
              ) : (
                <View style={{ marginTop: 16 }}>
                  <View style={{ flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: palette.border }}>
                    {['User', 'Status', 'Plan', 'Earned'].map((label) => (
                      <Text key={label} style={{ flex: 1, color: palette.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{label}</Text>
                    ))}
                  </View>
                  {referrals.map((referral, index) => (
                    <View key={referral.referral_id || index} style={{ flexDirection: 'row', paddingVertical: 12, borderBottomWidth: index === referrals.length - 1 ? 0 : 1, borderBottomColor: palette.border, alignItems: 'center' }} {...getTestProps(`referral-row-${index}`)}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: palette.text, fontSize: 12, fontWeight: '800' }}>{referral.referred_name || tx('referrals.history.anonymous', 'Anonymous')}</Text>
                        <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 4 }}>{referral.referred_email}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: `${palette.primary}14`, borderWidth: 1, borderColor: `${palette.primary}33` }}>
                          <Text style={{ color: palette.primary, fontSize: 10, fontWeight: '800', textTransform: 'capitalize' }}>{String(referral.status || '').replace('_', ' ')}</Text>
                        </View>
                      </View>
                      <Text style={{ flex: 1, color: palette.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{referral.plan}</Text>
                      <Text style={{ flex: 1, color: Number(referral.commission_earned || 0) > 0 ? colors.successText : palette.textMuted, fontSize: 12, fontWeight: '800', textAlign: 'right' }}>{Number(referral.commission_earned || 0) > 0 ? formatCurrency(referral.commission_earned) : '-'}</Text>
                    </View>
                  ))}
                </View>
              )}
            </BillingSectionCard>
            )}
          </View>
        </ScrollView>
      </FadeSlideIn>
    </AppShell>
  );
}
