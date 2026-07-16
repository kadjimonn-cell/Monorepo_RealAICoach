import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, Animated, Dimensions, Image, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../AppShell';
import { ReferralsSkeleton, FadeSlideIn } from '../SkeletonLoaders';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { getFrontendPlanName, getFrontendPlanPrice } from '../../config/pricingPolicy';

const STATUS_COLORS: Record<string, string> = {
  clicked: 'var(--app-text)', signed_up: 'var(--app-warning)', subscribed: 'var(--app-success)', churned: 'var(--app-error)', // @theme-ok brand/role/state identifier
};

const TIER_COLORS: Record<string, string> = {
  starter: 'var(--app-text)', bronze: 'var(--app-primary)', silver: 'var(--app-primary)', gold: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

const CONFETTI_COLORS = ['var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-error)', 'var(--app-primary)'];
const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');
// 'var(--app-primary)' removed - using 'var(--app-primary)'
// 'var(--app-text)' removed - using 'var(--app-text)'
// 'var(--app-text)'Soft removed - using 'var(--app-text)'Soft

function ConfettiPiece({ delay, color }: { delay: number; color: string }) {
  const fall = useRef(new Animated.Value(0)).current;
  const spin = useRef(new Animated.Value(0)).current;
  const x = useRef(Math.random() * SCREEN_W).current;
  const size = useRef(6 + Math.random() * 8).current;
  const drift = useRef((Math.random() - 0.5) * 120).current;

  useEffect(() => {
    const t = setTimeout(() => {
      Animated.parallel([
        Animated.timing(fall, { toValue: 1, duration: 2200 + Math.random() * 1000, useNativeDriver: true }),
        Animated.timing(spin, { toValue: 1, duration: 1500 + Math.random() * 1000, useNativeDriver: true }),
      ]).start();
    }, delay);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: 'absolute', left: x, top: -20, width: size, height: size * 1.4,
        backgroundColor: color, borderRadius: 2,
        transform: [
          { translateY: fall.interpolate({ inputRange: [0, 1], outputRange: [0, SCREEN_H + 40] }) },
          { translateX: fall.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, drift, drift * 0.6] }) },
          { rotate: spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', `${360 + Math.random() * 360}deg`] }) },
          { scaleX: spin.interpolate({ inputRange: [0, 0.5, 1], outputRange: [1, 0.3, 1] }) },
        ],
        opacity: fall.interpolate({ inputRange: [0, 0.7, 1], outputRange: [1, 1, 0] }),
      }}
    />
  );
}

function TierCelebrationModal({ tier, onClose }: { tier: any; onClose: () => void }) {
  const { colors } = useTheme();
  const scale = useRef(new Animated.Value(0)).current;
  const glow = useRef(new Animated.Value(0)).current;
  const tierColor = TIER_COLORS[tier?.id] || 'var(--app-primary)';

  useEffect(() => {
    Animated.sequence([
      Animated.spring(scale, { toValue: 1.08, friction: 4, tension: 60, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true }),
    ]).start();
    Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 1, duration: 1200, useNativeDriver: true }),
        Animated.timing(glow, { toValue: 0, duration: 1200, useNativeDriver: true }),
      ])
    ).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const confettiPieces = Array.from({ length: 50 }, (_, i) => (
    <ConfettiPiece key={i} delay={i * 40} color={CONFETTI_COLORS[i % CONFETTI_COLORS.length]} />
  ));

  return (
    <View style={{ position: 'fixed' as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999, backgroundColor: 'rgba(0,0,0,0.75)', alignItems: 'center', justifyContent: 'center' }} data-testid="tier-celebration-modal" testID="tier-celebration-modal">
      {confettiPieces}
      <Animated.View style={{
        transform: [{ scale }],
        backgroundColor: colors.card,
        borderRadius: 28, padding: 40, alignItems: 'center', maxWidth: 420, width: '90%',
        borderWidth: 2, borderColor: tierColor,
        shadowColor: tierColor, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 30,
      }}>
        <Animated.View style={{
          width: 100, height: 100, borderRadius: 50, alignItems: 'center', justifyContent: 'center',
          backgroundColor: (globalThis as any).__alphaColor(tierColor, '20'), borderWidth: 3, borderColor: tierColor,
          opacity: glow.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] }),
          transform: [{ scale: glow.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] }) }],
        }}>
          <Ionicons name="shield-checkmark" size={52} color={tierColor} />
        </Animated.View>
        <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 24 }}>
          TIER UNLOCKED
        </Text>
        <Text style={{ color: tierColor, fontSize: 38, fontWeight: '900', letterSpacing: -1, marginTop: 8 }}>
          {tier?.name}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: 15, textAlign: 'center', marginTop: 12, lineHeight: 22 }}>
          Congratulations! You've reached {tier?.name} tier.{'\n'}Your commission rate is now <Text style={{ fontWeight: '800', color: tierColor }}>{Math.round((tier?.commission || 0) * 100)}%</Text>
        </Text>
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 20,
          backgroundColor: (globalThis as any).__alphaColor(tierColor, '15'), paddingHorizontal: 20, paddingVertical: 10, borderRadius: 12,
        }}>
          <Ionicons name="trending-up" size={18} color={tierColor} />
          <Text style={{ color: tierColor, fontSize: 14, fontWeight: '700' }}>
            +{Math.round(((tier?.commission || 0.3) - 0.3) * 100)}% commission boost
          </Text>
        </View>
        <TouchableOpacity accessibilityLabel="Tier celebration close button"
          onPress={onClose}
          style={{
            marginTop: 28, backgroundColor: tierColor, paddingHorizontal: 36, paddingVertical: 14,
            borderRadius: 14, flexDirection: 'row', alignItems: 'center', gap: 8,
          }}
          data-testid="tier-celebration-close" testID="tier-celebration-close"
        >
          <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>Awesome!</Text>
          <Ionicons name="arrow-forward" size={16} color={colors.primaryText} />
        </TouchableOpacity>
      </Animated.View>
    </View>
  );
}

function KpiCard({ icon, label, value, sub, accent }: any) {
  const { colors } = useTheme();
  return (
    <View style={{
      flex: 1, minWidth: 130, backgroundColor: colors.card,
      borderRadius: 14, padding: 14, borderWidth: 1,
      borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: accent,
    }} data-testid={`ref-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`} testID={`ref-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(accent, '15'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={15} color={accent} />
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3, flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

export default function ReferralsPage() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _user } = useAuth();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width: winW } = useWindowDimensions();
  const isMobile = winW < 768;
  const accent = colors.primary;
  const heroTitle = t('referrals.hero.title');

  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);
  const [referrals, setReferrals] = useState<any[]>([]);
  const [copied, setCopied] = useState(false);
  const [credits, setCredits] = useState<any>(null);
  const [milestones, setMilestones] = useState<any>(null);
  const [sharingKit, setSharingKit] = useState<any>(null);
  const [channelAnalytics, setChannelAnalytics] = useState<any>(null);
  const [challenges, setChallenges] = useState<any>(null);
  const [activeTemplate, setActiveTemplate] = useState('twitter');
  const [templateCopied, setTemplateCopied] = useState(false);
  const [celebration, setCelebration] = useState<any>(() => {
    if (Platform.OS === 'web') {
      try {
        const stored = sessionStorage.getItem('tier_celebration');
        return stored ? JSON.parse(stored) : null;
      } catch { return null; }
    }
    return null;
  });

  const dismissCelebration = useCallback(async () => {
    setCelebration(null);
    if (Platform.OS === 'web') {
      try { sessionStorage.removeItem('tier_celebration'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    try { await api.post('/referrals/acknowledge-tier'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [statsRes, refsRes, creditsRes, milestonesRes] = await Promise.all([
        api.get('/referrals/my-stats'),
        api.get('/referrals/my-referrals'),
        api.get('/referrals/my-credits'),
        api.get('/referrals/my-milestones'),
      ]);
      setStats(statsRes.data);
      setReferrals(refsRes.data.referrals || []);
      setCredits(creditsRes.data);
      setMilestones(milestonesRes.data);
      // Fetch sharing kit separately to avoid blocking main data
      try {
        const sharingRes = await api.get('/referrals/sharing-kit');
        setSharingKit(sharingRes.data);
      } catch (e) { console.warn('Sharing kit fetch error:', e); }
      try {
        const channelRes = await api.get('/referrals/my-channel-analytics');
        setChannelAnalytics(channelRes.data);
      } catch (e) { console.warn('Channel analytics fetch error:', e); }
      try {
        const challengeRes = await api.get('/referrals/my-challenges');
        setChallenges(challengeRes.data);
      } catch (e) { console.warn('Challenges fetch error:', e); }
      if (statsRes.data.tier_unlocked) {
        setCelebration(statsRes.data.tier_unlocked);
        if (Platform.OS === 'web') {
          try { sessionStorage.setItem('tier_celebration', JSON.stringify(statsRes.data.tier_unlocked)); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }
      }
    } catch (e) { console.warn('Referral data error:', e); }
    finally { setLoading(false); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, []);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { loadData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const copyLink = async () => {
    if (!stats?.referral_link) return;
    try {
      if (Platform.OS === 'web' && navigator.clipboard) {
        await navigator.clipboard.writeText(stats.referral_link);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const copyTemplate = async (text: string) => {
    try {
      if (Platform.OS === 'web' && navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      }
      setTemplateCopied(true);
      setTimeout(() => setTemplateCopied(false), 2500);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/ReferralsInner.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const openShareUrl = (url: string) => {
    if (Platform.OS === 'web') window.open(url, '_blank');
  };

  const getCountdown = (endDate: string) => {
    const diff = new Date(endDate).getTime() - Date.now();
    if (diff <= 0) return 'Expired';
    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    if (days > 0) return `${days}d ${hours}h left`;
    const mins = Math.floor((diff % 3600000) / 60000);
    return `${hours}h ${mins}m left`;
  };

  const shareUrl = stats?.referral_link || '';
  const shareText = `Join RealAICoach and get 15% off your subscription! Use my referral link:`;
  const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(shareUrl)}`;
  const linkedinUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`;
  const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(shareText + ' ' + shareUrl)}`;

  const cardBg = darkMode ? colors.bg : colors.card;
  const border = darkMode ? colors.cardSoft : 'var(--app-primary)';
  const textPrimary = darkMode ? colors.text : 'var(--app-text)';
  const textSec = darkMode ? colors.textMuted : 'var(--app-text-muted)';
  const textMuted = darkMode ? colors.textMuted : 'var(--app-text-muted)';

  if (loading) return (
    <AppShell>
      <ReferralsSkeleton />
    </AppShell>
  );

  return (
    <View style={{ flex: 1 }}>
      {celebration && (
        <TierCelebrationModal
          tier={celebration}
          onClose={dismissCelebration}
        />
      )}
      <AppShell>
        <FadeSlideIn>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: isMobile ? 14 : 24, paddingBottom: 60 }}>
        <View style={{ maxWidth: 960, width: '100%', alignSelf: 'center' }}>

          {/* Hero Banner */}
          <View style={{
            borderRadius: isMobile ? 16 : 20, padding: isMobile ? 18 : 32, marginBottom: isMobile ? 16 : 24, overflow: 'hidden',
            backgroundColor: accent,
          }} data-testid="referral-hero" testID="referral-hero">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: isMobile ? 10 : 14, marginBottom: isMobile ? 12 : 16 }}>
              <View style={{ width: isMobile ? 40 : 52, height: isMobile ? 40 : 52, borderRadius: isMobile ? 10 : 14, backgroundColor: 'rgba(255,255,255,0.2)', alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="gift" size={isMobile ? 22 : 28} color={colors.primaryText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.primaryText, fontSize: isMobile ? 18 : 24, fontWeight: '800', letterSpacing: -0.8 }}>{heroTitle === 'referrals.hero.title' ? 'Earn Up to $1,000' : heroTitle}</Text>
                <Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: isMobile ? 12 : 14, marginTop: 2 }}>{tx('referrals.hero.subtitle', 'Share RealAICoach with your network')}</Text>
              </View>
            </View>
            <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 15, lineHeight: 24, marginBottom: 20 }}>
              Offer your friends a <Text style={{ fontWeight: '800', color: colors.primaryText }}>15% discount</Text> on their subscription, and earn up to <Text style={{ fontWeight: '800', color: colors.primaryText }}>40% commission</Text> on every monthly payment. Level up through Bronze, Silver, and Gold tiers!
            </Text>

            {/* Referral Link */}
            <View style={{
              backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 12, padding: 4,
              flexDirection: 'row', alignItems: 'center',
            }}>
              <View style={{ flex: 1, paddingHorizontal: 14 }}>
                <Text style={{ color: 'rgba(255,255,255,0.6)', fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('referrals.hero.yourReferralLink', 'Your Referral Link')}</Text>
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '600', marginTop: 2 }} numberOfLines={1} data-testid="referral-link-text" testID="referral-link-text">
                  {stats?.referral_link || tx('referrals.common.loading', 'Loading...')}
                </Text>
              </View>
              <TouchableOpacity onPress={copyLink} data-testid="copy-referral-link-btn" testID="copy-referral-link-btn"
                style={{
                  backgroundColor: copied ? colors.success : colors.primaryText, borderRadius: 10,
                  paddingHorizontal: 20, paddingVertical: 12,
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                }}>
                <Ionicons name={copied ? 'checkmark' : 'copy'} size={16} color={copied ? colors.primaryText : accent} />
                <Text style={{ color: copied ? colors.primaryText : accent, fontSize: 13, fontWeight: '700' }}>{copied ? tx('referrals.actions.copied', 'Copied!') : tx('referrals.actions.copy', 'Copy')}</Text>
              </TouchableOpacity>
            </View>

            {/* Social Share */}
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
              {Platform.OS === 'web' && (
                <>
                  <TouchableOpacity onPress={() => window.open(twitterUrl, '_blank')} data-testid="share-twitter" testID="share-twitter"
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
                    <Ionicons name="logo-twitter" size={16} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{tx('referrals.channels.twitter', 'Twitter')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => window.open(linkedinUrl, '_blank')} data-testid="share-linkedin" testID="share-linkedin"
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
                    <Ionicons name="logo-linkedin" size={16} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{tx('referrals.channels.linkedin', 'LinkedIn')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => window.open(whatsappUrl, '_blank')} data-testid="share-whatsapp" testID="share-whatsapp"
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
                    <Ionicons name="logo-whatsapp" size={16} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{tx('referrals.channels.whatsapp', 'WhatsApp')}</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </View>

          {/* Tier Status Card */}
          {stats?.tier && (
            <View style={{
              backgroundColor: cardBg, borderRadius: 16, padding: isMobile ? 16 : 24, borderWidth: 1, borderColor: border,
              marginBottom: isMobile ? 16 : 24, overflow: 'hidden',
            }} data-testid="referral-tier-card" testID="referral-tier-card">
              <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'flex-start', marginBottom: 20, gap: isMobile ? 12 : 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
                  <View style={{
                    width: 56, height: 56, borderRadius: 16, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: (globalThis as any).__alphaColor((TIER_COLORS[stats.tier.id] || colors.skeleton), '18'),
                    borderWidth: 2, borderColor: (globalThis as any).__alphaColor((TIER_COLORS[stats.tier.id] || colors.borderStrong), '40'),
                  }}>
                    <Ionicons name="shield" size={28} color={TIER_COLORS[stats.tier.id] || colors.textDim} />
                  </View>
                  <View>
                    <Text style={{ color: textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('referrals.tier.yourTier', 'Your Tier')}</Text>
                    <Text style={{ color: TIER_COLORS[stats.tier.id] || textPrimary, fontSize: 24, fontWeight: '800', letterSpacing: -0.5 }}>{stats.tier.name}</Text>
                    <Text style={{ color: textMuted, fontSize: 12, marginTop: 2 }}>{Math.round(stats.tier.commission * 100)}% commission rate</Text>
                  </View>
                </View>
                {stats.next_tier && (
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('referrals.tier.nextTier', 'Next Tier')}</Text>
                    <Text style={{ color: TIER_COLORS[stats.next_tier.id] || textPrimary, fontSize: 15, fontWeight: '700' }}>{stats.next_tier.name}</Text>
                    <Text style={{ color: textMuted, fontSize: 11 }}>{stats.next_tier.referrals_needed} more referral{stats.next_tier.referrals_needed !== 1 ? 's' : ''}</Text>
                  </View>
                )}
              </View>

              {/* Progress Bar */}
              {stats.all_tiers && (() => {
                const tiers = stats.all_tiers;
                const maxRef = tiers[tiers.length - 1]?.min_referrals || 16;
                const progress = Math.min((stats.total_signups || 0) / maxRef, 1);
                return (
                  <View style={{ marginBottom: 16 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text style={{ color: textSec, fontSize: 12, fontWeight: '600' }}>{stats.total_signups || 0} referrals</Text>
                      <Text style={{ color: textMuted, fontSize: 11 }}>{maxRef} for Gold</Text>
                    </View>
                    <View style={{ height: 10, backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)', borderRadius: 5, overflow: 'hidden', position: 'relative' }}>
                      <View style={{
                        height: '100%', width: `${Math.max(progress * 100, 2)}%`,
                        backgroundColor: TIER_COLORS[stats.tier.id] || colors.skeleton, borderRadius: 5,
                      }} />
                      {/* Tier markers */}
                      {tiers.map((t: any) => {
                        const pos = (t.min_referrals / maxRef) * 100;
                        return (
                          <View key={t.id} style={{
                            position: 'absolute', top: -3, left: `${pos}%`, width: 3, height: 16,
                            backgroundColor: TIER_COLORS[t.id] || colors.skeleton, borderRadius: 2, marginLeft: -1,
                          }} />
                        );
                      })}
                    </View>
                    {/* Tier labels */}
                    <View style={{ flexDirection: 'row', marginTop: 6 }}>
                      {tiers.map((t: any, i: number) => (
                        <Text key={t.id} style={{
                          position: 'absolute', left: `${(t.min_referrals / maxRef) * 100}%`,
                          color: stats.tier.id === t.id ? TIER_COLORS[t.id] : textMuted,
                          fontSize: 9, fontWeight: stats.tier.id === t.id ? '700' : '500',
                          transform: [{ translateX: -12 }],
                        }}>{t.name}</Text>
                      ))}
                    </View>
                  </View>
                );
              })()}

              {/* Tier Roadmap */}
              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8, marginTop: 12 }}>
                {(stats.all_tiers || []).map((t: any) => {
                  const isActive = stats.tier.id === t.id;
                  const isCompleted = (stats.total_signups || 0) >= t.min_referrals;
                  return (
                    <View key={t.id} style={{
                      flex: isMobile ? undefined : 1, padding: isMobile ? 12 : 14, borderRadius: 12, borderWidth: isActive ? 2 : 1,
                      borderColor: isActive ? TIER_COLORS[t.id] : border,
                      backgroundColor: isActive ? (globalThis as any).__alphaColor(TIER_COLORS[t.id], '10') : (darkMode ? colors.cardSoft : colors.card),
                      flexDirection: isMobile ? 'row' : 'column', alignItems: isMobile ? 'center' : 'flex-start', gap: isMobile ? 10 : 0,
                    }} data-testid={`tier-card-${t.id}`} testID={`tier-card-${t.id}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: isMobile ? 0 : 6 }}>
                        <Ionicons name={isCompleted ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={isCompleted ? TIER_COLORS[t.id] : textMuted} />
                        <Text style={{ color: isActive ? TIER_COLORS[t.id] : textSec, fontSize: 13, fontWeight: '700' }}>{t.name}</Text>
                      </View>
                      {isMobile ? (
                        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <Text style={{ color: textMuted, fontSize: 11 }}>{t.min_referrals}+ referrals</Text>
                          <Text style={{ color: isActive ? TIER_COLORS[t.id] : textSec, fontSize: 16, fontWeight: '800' }}>{Math.round(t.commission * 100)}%</Text>
                        </View>
                      ) : (
                        <>
                          <Text style={{ color: textMuted, fontSize: 11 }}>{t.min_referrals}+ referrals</Text>
                          <Text style={{ color: isActive ? TIER_COLORS[t.id] : textSec, fontSize: 16, fontWeight: '800', marginTop: 4 }}>{Math.round(t.commission * 100)}%</Text>
                          <Text style={{ color: textMuted, fontSize: 10 }}>commission</Text>
                        </>
                      )}
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* How It Works */}
          <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: isMobile ? 16 : 24, borderWidth: 1, borderColor: border, marginBottom: isMobile ? 16 : 24 }} data-testid="referral-how-it-works" testID="referral-how-it-works">
            <Text style={{ color: textPrimary, fontSize: isMobile ? 16 : 18, fontWeight: '800', letterSpacing: -0.5, marginBottom: isMobile ? 14 : 20 }}>How It Works</Text>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', flexWrap: 'wrap', gap: isMobile ? 12 : 16 }}>
              {[
                { step: '1', title: 'Share Your Link', desc: 'Copy your unique referral link and share it with friends, colleagues, or on social media.', icon: 'share-social', color: accent },
                { step: '2', title: 'Friends Sign Up', desc: 'When they use your link, they automatically get 15% off their first subscription.', icon: 'person-add', color: colors.purpleText },
                { step: '3', title: 'Earn Commission', desc: 'You earn 30% of their monthly subscription fee as long as they remain subscribed.', icon: 'cash', color: colors.successText },
              ].map(s => (
                <View key={s.step} style={{ flex: isMobile ? undefined : 1, minWidth: isMobile ? undefined : 200, flexDirection: 'row', gap: 12 }}>
                  <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(s.color, '12'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={s.icon as any} size={18} color={s.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: textPrimary, fontSize: 14, fontWeight: '700' }}>{s.title}</Text>
                    <Text style={{ color: textMuted, fontSize: 12, lineHeight: 18, marginTop: 2 }}>{s.desc}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>

          {/* Sharing Kit */}
          {sharingKit && Platform.OS === 'web' && (
            <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: isMobile ? 16 : 24, borderWidth: 1, borderColor: border, marginBottom: isMobile ? 16 : 24 }} data-testid="sharing-kit-section" testID="sharing-kit-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: isMobile ? 14 : 20 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.indigo, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="megaphone" size={18} color={colors.indigoText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: isMobile ? 16 : 18, fontWeight: '800', letterSpacing: -0.5 }}>Sharing Kit</Text>
                  <Text style={{ color: textMuted, fontSize: 11 }}>Ready-to-share templates for every platform</Text>
                </View>
              </View>

              {/* Platform Tabs */}
              <View style={{ flexDirection: 'row', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
                {Object.entries(sharingKit.templates).map(([key, tmpl]: [string, any]) => {
                  const isActive = activeTemplate === key;
                  return (
                    <TouchableOpacity key={key} onPress={() => { setActiveTemplate(key); setTemplateCopied(false); }}
                      data-testid={`sharing-tab-${key}`} testID={`sharing-tab-${key}`}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(tmpl.color, '18') : (darkMode ? colors.cardSoft : 'var(--app-primary)'),
                        borderWidth: 1.5, borderColor: isActive ? (globalThis as any).__alphaColor(tmpl.color, '50') : 'transparent',
                      }}>
                      <Ionicons name={tmpl.icon} size={15} color={isActive ? tmpl.color : textMuted} />
                      <Text style={{ color: isActive ? tmpl.color : textSec, fontSize: 12, fontWeight: isActive ? '700' : '500' }}>
                        {tmpl.platform}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Active Template Preview */}
              {(() => {
                const tmpl = sharingKit.templates[activeTemplate];
                if (!tmpl) return null;
                return (
                  <View>
                    {/* Template Text Box */}
                    <View style={{
                      backgroundColor: darkMode ? colors.card : colors.card, borderRadius: 14,
                      padding: 18, borderWidth: 1, borderColor: border,
                      borderLeftWidth: 3, borderLeftColor: tmpl.color,
                    }} data-testid="sharing-template-preview" testID="sharing-template-preview">
                      {tmpl.subject && (
                        <View style={{ marginBottom: 10, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: border }}>
                          <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3 }}>Subject</Text>
                          <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '600', marginTop: 2 }}>{tmpl.subject}</Text>
                        </View>
                      )}
                      <Text style={{ color: textSec, fontSize: 13, lineHeight: 21 }}>{tmpl.text}</Text>
                      {tmpl.char_limit && (
                        <Text style={{
                          color: tmpl.text.length > tmpl.char_limit ? colors.error : textMuted,
                          fontSize: 10, marginTop: 10, textAlign: 'right',
                        }}>
                          {tmpl.text.length}/{tmpl.char_limit} characters
                        </Text>
                      )}
                    </View>

                    {/* Action Buttons */}
                    <View style={{ flexDirection: 'row', gap: 10, marginTop: 14 }}>
                      <TouchableOpacity onPress={() => copyTemplate(tmpl.text)}
                        data-testid="sharing-copy-btn" testID="sharing-copy-btn"
                        style={{
                          flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
                          backgroundColor: templateCopied ? colors.success : (darkMode ? colors.cardSoft : 'var(--app-primary)'),
                          borderRadius: 12, paddingVertical: 12, borderWidth: 1,
                          borderColor: templateCopied ? colors.success : border,
                        }}>
                        <Ionicons name={templateCopied ? 'checkmark' : 'copy'} size={16} color={templateCopied ? colors.primaryText : textSec} />
                        <Text style={{ color: templateCopied ? colors.primaryText : textSec, fontSize: 13, fontWeight: '600' }}>
                          {templateCopied ? 'Copied!' : 'Copy Text'}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => openShareUrl(tmpl.share_url)}
                        data-testid="sharing-open-btn" testID="sharing-open-btn"
                        style={{
                          flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
                          backgroundColor: tmpl.color, borderRadius: 12, paddingVertical: 12,
                        }}>
                        <Ionicons name="open-outline" size={16} color={colors.primaryText} />
                        <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>
                          {activeTemplate === 'email' ? 'Open Email' : activeTemplate === 'sms' ? 'Open SMS' : `Share on ${tmpl.platform.split(' /')[0]}`}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })()}

              {/* QR Code Section */}
              {sharingKit.qr_code && (
                <View style={{
                  marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: border,
                  flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'center' : 'center', gap: isMobile ? 14 : 20,
                }} data-testid="sharing-qr-section" testID="sharing-qr-section">
                  <View style={{
                    backgroundColor: colors.card, borderRadius: 14, padding: 10,
                    borderWidth: 1, borderColor: colors.border,
                    shadowColor: colors.text, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 8,
                  }}>
                    <Image source={{ uri: sharingKit.qr_code }} style={{ width: isMobile ? 100 : 120, height: isMobile ? 100 : 120 }} data-testid="sharing-qr-image" testID="sharing-qr-image" accessibilityLabel="QR Code" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: textPrimary, fontSize: 15, fontWeight: '700', marginBottom: 4 }}>QR Code</Text>
                    <Text style={{ color: textMuted, fontSize: 12, lineHeight: 18, marginBottom: 12 }}>
                      Perfect for in-person sharing. Scan to open your referral link directly.
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <TouchableOpacity
                        data-testid="qr-download-btn" testID="qr-download-btn"
                        onPress={() => {
                          const a = document.createElement('a');
                          a.href = sharingKit.qr_code;
                          a.download = `referral-qr-${sharingKit.referral_code}.png`;
                          a.click();
                        }}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 6,
                          backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)',
                          paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                          borderWidth: 1, borderColor: border,
                        }}>
                        <Ionicons name="download-outline" size={14} color={textSec} />
                        <Text style={{ color: textSec, fontSize: 12, fontWeight: '600' }}>Download PNG</Text>
                      </TouchableOpacity>
                    </View>
                    <View style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10,
                      backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
                    }}>
                      <Ionicons name="link" size={12} color={accent} />
                      <Text style={{ color: textMuted, fontSize: 11, flex: 1 }} numberOfLines={1}>{sharingKit.referral_link}</Text>
                    </View>
                  </View>
                </View>
              )}
            </View>
          )}

          {/* Active Challenges */}
          {challenges && challenges.challenges?.length > 0 && (
            <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border, marginBottom: 24 }} data-testid="challenges-section" testID="challenges-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.error, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="flame" size={20} color={colors.error} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 }}>Active Challenges</Text>
                  <Text style={{ color: textMuted, fontSize: 12 }}>Complete challenges to earn bonus credits</Text>
                </View>
                {challenges.total_rewards_earned > 0 && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 }}>
                    <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>${challenges.total_rewards_earned} earned</Text>
                  </View>
                )}
              </View>

              {challenges.challenges.map((ch: any) => {
                const isActive = ch.status === 'active';
                const isCompleted = ch.status === 'completed';
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                const _isExpired = ch.status === 'expired';
                const statusColor = isCompleted ? colors.success : isActive ? colors.warning : colors.textMuted;
                const statusIcon = isCompleted ? 'checkmark-circle' : isActive ? 'time' : 'close-circle';
                const statusLabel = isCompleted ? 'Completed' : isActive ? getCountdown(ch.end_date) : 'Expired';

                return (
                  <View key={ch.challenge_id} style={{
                    backgroundColor: darkMode ? colors.card : colors.card, borderRadius: 14, padding: 18,
                    borderWidth: 1, borderColor: isCompleted ? (globalThis as any).__alphaColor(colors.success, '30') : border,
                    marginBottom: 12, borderLeftWidth: 3, borderLeftColor: statusColor,
                  }} data-testid={`challenge-card-${ch.challenge_id}`} testID={`challenge-card-${ch.challenge_id}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                      <View style={{ flex: 1, marginRight: 12 }}>
                        <Text style={{ color: textPrimary, fontSize: 15, fontWeight: '700' }}>{ch.title}</Text>
                        <Text style={{ color: textSec, fontSize: 12, marginTop: 2, lineHeight: 18 }}>{ch.description}</Text>
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(statusColor, '15'), paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                          <Ionicons name={statusIcon} size={12} color={statusColor} />
                          <Text style={{ color: statusColor, fontSize: 10, fontWeight: '700' }}>{statusLabel}</Text>
                        </View>
                        <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '800', marginTop: 6 }}>${ch.reward_value} bonus</Text>
                      </View>
                    </View>

                    {/* Progress Bar */}
                    <View style={{ marginTop: 4 }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                        <Text style={{ color: textMuted, fontSize: 11 }}>
                          {ch.progress}/{ch.goal_count} referrals
                        </Text>
                        <Text style={{ color: isCompleted ? colors.success : textSec, fontSize: 11, fontWeight: '600' }}>
                          {ch.progress_pct}%
                        </Text>
                      </View>
                      <View style={{ height: 8, backgroundColor: darkMode ? colors.cardSoft : colors.textDim, borderRadius: 4, overflow: 'hidden' }}>
                        <View style={{
                          width: `${Math.min(ch.progress_pct, 100)}%` as any, height: '100%', borderRadius: 4,
                          backgroundColor: isCompleted ? colors.success : isActive ? colors.warning : colors.textMuted,
                        }} />
                      </View>
                      {isActive && ch.goal_count - ch.progress > 0 && (
                        <Text style={{ color: accent, fontSize: 11, fontWeight: '600', marginTop: 6 }}>
                          {ch.goal_count - ch.progress} more to go!
                        </Text>
                      )}
                      {isCompleted && ch.rewarded && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6 }}>
                          <Ionicons name="wallet" size={12} color={colors.successText} />
                          <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '600' }}>
                            ${ch.reward_value} credited to your wallet
                          </Text>
                        </View>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Channel Performance */}
          {channelAnalytics && channelAnalytics.channels?.length > 0 && (
            <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border, marginBottom: 24 }} data-testid="channel-performance-section" testID="channel-performance-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="analytics" size={20} color={colors.warningText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 }}>Channel Performance</Text>
                  <Text style={{ color: textMuted, fontSize: 12 }}>See which sharing channels bring the most referrals</Text>
                </View>
                {channelAnalytics.best_channel_label ? (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), paddingHorizontal: 12, paddingVertical: 6, borderRadius: 10 }}>
                    <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>Best: {channelAnalytics.best_channel_label}</Text>
                  </View>
                ) : null}
              </View>

              {/* Channel Bars */}
              {channelAnalytics.channels.filter((c: any) => c.signups > 0 || c.clicks > 0).map((ch: any) => {
                const maxSignups = Math.max(...channelAnalytics.channels.map((c: any) => c.signups), 1);
                const barWidth = Math.max((ch.signups / maxSignups) * 100, 2);
                const isBest = ch.channel === channelAnalytics.best_channel;
                return (
                  <View key={ch.channel} style={{ marginBottom: 14 }} data-testid={`channel-bar-${ch.channel}`} testID={`channel-bar-${ch.channel}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(ch.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name={ch.icon} size={14} color={ch.color} />
                        </View>
                        <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '600' }}>{ch.label}</Text>
                        {isBest && <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} />}
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                        <Text style={{ color: textMuted, fontSize: 11 }}>{ch.clicks} clicks</Text>
                        <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '700' }}>{ch.signups} signups</Text>
                        {ch.conversion_rate > 0 && (
                          <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '600' }}>{ch.conversion_rate}%</Text>
                        )}
                      </View>
                    </View>
                    <View style={{ height: 8, backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)', borderRadius: 4, overflow: 'hidden' }}>
                      <View style={{ width: `${barWidth}%` as any, height: '100%', backgroundColor: ch.color, borderRadius: 4, opacity: isBest ? 1 : 0.7 }} />
                    </View>
                  </View>
                );
              })}

              {/* Empty state */}
              {channelAnalytics.channels.filter((c: any) => c.signups > 0 || c.clicks > 0).length === 0 && (
                <View style={{ alignItems: 'center', paddingVertical: 20, opacity: 0.6 }}>
                  <Ionicons name="bar-chart-outline" size={28} color={textMuted} />
                  <Text style={{ color: textMuted, fontSize: 13, marginTop: 8 }}>Share using the Sharing Kit above to start tracking channel performance</Text>
                </View>
              )}

              {/* Summary Row */}
              {channelAnalytics.total_signups > 0 && (
                <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: border }}>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800' }}>{channelAnalytics.total_clicks}</Text>
                    <Text style={{ color: textMuted, fontSize: 11 }}>Total Clicks</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800' }}>{channelAnalytics.total_signups}</Text>
                    <Text style={{ color: textMuted, fontSize: 11 }}>Total Signups</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800' }}>
                      {channelAnalytics.total_clicks > 0 ? Math.round(channelAnalytics.total_signups / channelAnalytics.total_clicks * 100) : 0}%
                    </Text>
                    <Text style={{ color: textMuted, fontSize: 11 }}>Avg. Conversion</Text>
                  </View>
                </View>
              )}
            </View>
          )}

          {/* KPI Cards */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
            <KpiCard icon="people" label="Total Referrals" value={stats?.total_signups ?? 0} sub={`${stats?.total_clicks ?? 0} link clicks`} accent={accent} />
            <KpiCard icon="checkmark-done" label="Active Subscribers" value={stats?.active_subscribers ?? 0} sub={`${stats?.conversion_rate ?? 0}% conversion`} accent={colors.success} />
            <KpiCard icon="wallet" label="Total Earnings" value={`$${(stats?.total_earnings ?? 0).toFixed(2)}`} sub={`$${(stats?.monthly_earnings ?? 0).toFixed(2)}/mo recurring`} accent={colors.purple} />
            <KpiCard icon="trending-up" label="Monthly Income" value={`$${(stats?.monthly_earnings ?? 0).toFixed(2)}`} sub="Recurring commission" accent={colors.warning} />
          </View>

          {/* Referral Credits & Wallet */}
          {credits && (
            <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border, marginBottom: 24 }} data-testid="referral-credits-section" testID="referral-credits-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.purple, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="wallet" size={20} color={colors.purpleText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 }}>Referral Credits</Text>
                  <Text style={{ color: textMuted, fontSize: 12 }}>Automatically applied to your subscription renewals</Text>
                </View>
              </View>

              {/* Balance Cards */}
              <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: darkMode ? colors.cardSoft : colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: border, borderLeftWidth: 3, borderLeftColor: colors.purple }} data-testid="credit-balance-card" testID="credit-balance-card">
                  <Text style={{ color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3 }}>Available Balance</Text>
                  <Text style={{ color: colors.purpleText, fontSize: 30, fontWeight: '900', letterSpacing: -0.5, marginTop: 4 }}>${credits.balance.toFixed(2)}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: border, borderLeftWidth: 3, borderLeftColor: colors.success }} data-testid="credit-earned-card" testID="credit-earned-card">
                  <Text style={{ color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3 }}>Total Earned</Text>
                  <Text style={{ color: colors.successText, fontSize: 30, fontWeight: '900', letterSpacing: -0.5, marginTop: 4 }}>${credits.total_earned.toFixed(2)}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: border, borderLeftWidth: 3, borderLeftColor: accent }} data-testid="credit-applied-card" testID="credit-applied-card">
                  <Text style={{ color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3 }}>Applied to Renewals</Text>
                  <Text style={{ color: accent, fontSize: 30, fontWeight: '900', letterSpacing: -0.5, marginTop: 4 }}>${credits.total_applied.toFixed(2)}</Text>
                </View>
              </View>

              {/* Renewal Savings Preview */}
              {credits.renewal_info && (
                <View style={{
                  backgroundColor: credits.renewal_info.fully_covered ? (globalThis as any).__alphaColor(colors.success, '12') : (darkMode ? colors.cardSoft : 'var(--app-primary)'),
                  borderRadius: 14, padding: 18, borderWidth: 1,
                  borderColor: credits.renewal_info.fully_covered ? (globalThis as any).__alphaColor(colors.success, '40') : (darkMode ? colors.primarySoft : colors.primarySoft),
                  marginBottom: 20,
                }} data-testid="renewal-savings-card" testID="renewal-savings-card">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name={credits.renewal_info.fully_covered ? 'shield-checkmark' : 'calendar'} size={16} color={credits.renewal_info.fully_covered ? colors.success : accent} />
                    <Text style={{ color: textPrimary, fontSize: 14, fontWeight: '700' }}>
                      {credits.renewal_info.fully_covered ? 'Next Renewal Fully Covered!' : 'Upcoming Renewal Savings'}
                    </Text>
                  </View>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
                    <View>
                      <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{credits.renewal_info.plan} Plan</Text>
                      <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginTop: 2 }}>${credits.renewal_info.cost.toFixed(2)}/mo</Text>
                    </View>
                    <View>
                      <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>Credits Will Cover</Text>
                      <Text style={{ color: colors.successText, fontSize: 18, fontWeight: '800', marginTop: 2 }}>-${credits.renewal_info.credits_will_cover.toFixed(2)}</Text>
                    </View>
                    <View>
                      <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>You'll Pay</Text>
                      <Text style={{ color: credits.renewal_info.fully_covered ? colors.success : textPrimary, fontSize: 18, fontWeight: '800', marginTop: 2 }}>
                        {credits.renewal_info.fully_covered ? 'FREE' : `$${credits.renewal_info.remaining_after_credits.toFixed(2)}`}
                      </Text>
                    </View>
                    {credits.renewal_info.renewal_date && (
                      <View>
                        <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>Renewal Date</Text>
                        <Text style={{ color: textSec, fontSize: 14, fontWeight: '600', marginTop: 4 }}>{new Date(credits.renewal_info.renewal_date).toLocaleDateString()}</Text>
                      </View>
                    )}
                  </View>
                </View>
              )}

              {/* Transaction History */}
              {credits.transactions && credits.transactions.length > 0 && (
                <View>
                  <Text style={{ color: textPrimary, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>Credit History</Text>
                  {credits.transactions.map((txn: any, i: number) => (
                    <View key={i} style={{
                      flexDirection: 'row', alignItems: 'center', paddingVertical: 12, gap: 12,
                      borderTopWidth: i > 0 ? 1 : 0, borderTopColor: border,
                    }} data-testid={`credit-txn-${i}`} testID={`credit-txn-${i}`}>
                      <View style={{
                        width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
                        backgroundColor: txn.type === 'credit' ? (globalThis as any).__alphaColor(colors.success, '15') : accent + '15',
                      }}>
                        <Ionicons
                          name={txn.type === 'credit' ? 'arrow-down' : 'arrow-up'}
                          size={16}
                          color={txn.type === 'credit' ? colors.success : accent}
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '600' }}>
                          {txn.type === 'credit' ? 'Commission Earned' : 'Applied to Renewal'}
                        </Text>
                        <Text style={{ color: textMuted, fontSize: 11 }}>
                          {txn.source === 'referral_subscription'
                            ? `From ${txn.details?.referred_name || 'referral'} (${txn.details?.plan || ''} plan)`
                            : txn.source === 'subscription_renewal'
                              ? `Subscription renewal${txn.details?.fully_covered ? ' (fully covered)' : ''}`
                              : txn.source}
                        </Text>
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <Text style={{
                          color: txn.type === 'credit' ? colors.success : accent,
                          fontSize: 15, fontWeight: '800',
                        }}>
                          {txn.type === 'credit' ? '+' : '-'}${txn.amount.toFixed(2)}
                        </Text>
                        <Text style={{ color: textMuted, fontSize: 10 }}>
                          {txn.created_at ? new Date(txn.created_at).toLocaleDateString() : ''}
                        </Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {credits.transactions && credits.transactions.length === 0 && (
                <View style={{ alignItems: 'center', paddingVertical: 24 }}>
                  <Ionicons name="receipt-outline" size={28} color={textMuted} />
                  <Text style={{ color: textMuted, fontSize: 13, marginTop: 8 }}>No credit transactions yet. Earn commissions from referrals!</Text>
                </View>
              )}
            </View>
          )}

          {/* Milestone Rewards Tracker */}
          {milestones && (
            <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border, marginBottom: 24 }} data-testid="milestone-tracker-section" testID="milestone-tracker-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="trophy" size={20} color={colors.warningText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 }}>Milestone Rewards</Text>
                  <Text style={{ color: textMuted, fontSize: 12 }}>Earn bonus credits for hitting referral milestones</Text>
                </View>
                {milestones.total_bonus_earned > 0 && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 }}>
                    <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>${milestones.total_bonus_earned} earned</Text>
                  </View>
                )}
              </View>

              {/* Next Milestone Highlight */}
              {milestones.next_milestone && (
                <View style={{
                  backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)',
                  borderRadius: 14, padding: 16, borderWidth: 1,
                  borderColor: darkMode ? colors.warningSoft : 'var(--app-primary)',
                  marginBottom: 18,
                }} data-testid="next-milestone-card" testID="next-milestone-card">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Ionicons name="flag" size={14} color={colors.warningText} />
                    <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '700' }}>
                      Next: {milestones.next_milestone.label}
                    </Text>
                    <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '800' }}>
                      +${milestones.next_milestone.bonus} bonus
                    </Text>
                  </View>
                  <View style={{ height: 8, backgroundColor: darkMode ? colors.surfaceHover : 'var(--app-surface-hover)', borderRadius: 4, overflow: 'hidden', marginBottom: 6 }}>
                    <View style={{
                      height: '100%', borderRadius: 4,
                      width: `${Math.max(milestones.next_milestone.progress * 100, 3)}%`,
                      backgroundColor: colors.warning,
                    }} />
                  </View>
                  <Text style={{ color: textMuted, fontSize: 11 }}>
                    {milestones.next_milestone.referrals_remaining} more referral{milestones.next_milestone.referrals_remaining !== 1 ? 's' : ''} to go ({milestones.total_signups}/{milestones.next_milestone.referrals_required})
                  </Text>
                </View>
              )}

              {/* All Milestones Grid */}
              <View style={{ gap: 10 }}>
                {milestones.milestones.map((m: any) => (
                  <View key={m.id} style={{
                    flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, paddingHorizontal: 14,
                    backgroundColor: m.achieved ? (darkMode ? colors.cardSoft : 'var(--app-primary)') : (darkMode ? colors.card : colors.card),
                    borderRadius: 12, borderWidth: 1,
                    borderColor: m.achieved ? (globalThis as any).__alphaColor(colors.success, '30') : border,
                  }} data-testid={`milestone-${m.id}`} testID={`milestone-${m.id}`}>
                    <View style={{
                      width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
                      backgroundColor: m.achieved ? (globalThis as any).__alphaColor(m.color, '20') : (darkMode ? colors.card : colors.textDim),
                    }}>
                      <Ionicons
                        name={m.achieved ? (m.icon as any) : 'lock-closed'}
                        size={20}
                        color={m.achieved ? m.color : textMuted}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Text style={{ color: m.achieved ? textPrimary : textSec, fontSize: 14, fontWeight: '700' }}>{m.label}</Text>
                        {m.achieved && <Ionicons name="checkmark-circle" size={14} color={colors.successText} />}
                      </View>
                      <Text style={{ color: textMuted, fontSize: 11 }}>
                        {m.referrals_required} referrals {m.achieved ? '- Completed!' : `(${m.referrals_remaining} remaining)`}
                      </Text>
                      {!m.achieved && (
                        <View style={{ height: 4, backgroundColor: darkMode ? colors.surfaceHover : colors.textDim, borderRadius: 2, marginTop: 6, overflow: 'hidden' }}>
                          <View style={{ height: '100%', borderRadius: 2, width: `${Math.max(m.progress * 100, 2)}%`, backgroundColor: m.color }} />
                        </View>
                      )}
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: m.achieved ? colors.success : m.color, fontSize: 16, fontWeight: '800' }}>+${m.bonus}</Text>
                      {m.achieved && m.achieved_at && (
                        <Text style={{ color: textMuted, fontSize: 9 }}>{new Date(m.achieved_at).toLocaleDateString()}</Text>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Commission Breakdown */}
          <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border, marginBottom: 24 }} data-testid="referral-commission-info" testID="referral-commission-info">
            <Text style={{ color: textPrimary, fontSize: 16, fontWeight: '800', marginBottom: 4, letterSpacing: -0.3 }}>Commission Structure</Text>
            <Text style={{ color: textMuted, fontSize: 12, marginBottom: 16 }}>Your rate: <Text style={{ color: TIER_COLORS[stats?.tier?.id] || accent, fontWeight: '700' }}>{Math.round((stats?.commission_rate || 0.3) * 100)}%</Text> ({stats?.tier?.name || 'Starter'} tier)</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {[
                { plan: `${getFrontendPlanName('basic')} Plan`, priceNum: getFrontendPlanPrice('basic', 'monthly'), priceLabel: `$${getFrontendPlanPrice('basic', 'monthly').toFixed(2)}/mo`, rate: stats?.commission_rate || 0.3, color: accent },
                { plan: `${getFrontendPlanName('premium')} Plan`, priceNum: getFrontendPlanPrice('premium', 'monthly'), priceLabel: `$${getFrontendPlanPrice('premium', 'monthly').toFixed(2)}/mo`, rate: stats?.commission_rate || 0.3, color: colors.purpleText },
              ].map(p => (
                <View key={p.plan} style={{
                  flex: 1, minWidth: 200, backgroundColor: colors.card,
                  borderRadius: 12, padding: 18, borderWidth: 1, borderColor: border,
                }}>
                  <Text style={{ color: textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3 }}>{p.plan}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
                    <Text style={{ color: p.color, fontSize: 24, fontWeight: '800' }}>${(p.priceNum * p.rate).toFixed(2)}/mo</Text>
                    <Text style={{ color: textMuted, fontSize: 12 }}>per referral</Text>
                  </View>
                  <Text style={{ color: textMuted, fontSize: 11, marginTop: 6 }}>{Math.round(p.rate * 100)}% of {p.priceLabel} subscription</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Referral History */}
          <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: border }} data-testid="referral-history" testID="referral-history">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text style={{ color: textPrimary, fontSize: 16, fontWeight: '800', letterSpacing: -0.3 }}>Referral History</Text>
              <TouchableOpacity onPress={loadData} data-testid="refresh-referrals-btn" testID="refresh-referrals-btn"
                style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: darkMode ? colors.cardSoft : 'var(--app-primary)', alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="refresh" size={16} color={accent} />
              </TouchableOpacity>
            </View>

            {referrals.length === 0 ? (
              <View style={{ alignItems: 'center', padding: 40 }}>
                <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(accent, '10'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                  <Ionicons name="people-outline" size={32} color={accent} />
                </View>
                <Text style={{ color: textPrimary, fontSize: 16, fontWeight: '700', marginBottom: 6 }}>No Referrals Yet</Text>
                <Text style={{ color: textMuted, fontSize: 13, textAlign: 'center', maxWidth: 300 }}>Share your referral link to start earning commission on every subscription.</Text>
              </View>
            ) : (
              <View>
                {/* Header */}
                <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: border }}>
                  <Text style={{ flex: 2, color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>User</Text>
                  <Text style={{ flex: 1, color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>Status</Text>
                  <Text style={{ flex: 1, color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>Plan</Text>
                  <Text style={{ flex: 1, color: textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>Earned</Text>
                </View>
                {referrals.map((r, i) => (
                  <View key={r.referral_id || i} style={{ flexDirection: 'row', paddingVertical: 12, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: border, alignItems: 'center' }}
                    data-testid={`referral-row-${i}`} testID={`referral-row-${i}`}>
                    <View style={{ flex: 2 }}>
                      <Text style={{ color: textPrimary, fontSize: 13, fontWeight: '600' }}>{r.referred_name || 'Anonymous'}</Text>
                      <Text style={{ color: textMuted, fontSize: 11 }}>{r.referred_email}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor((STATUS_COLORS[r.status] || colors.skeleton), '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, alignSelf: 'flex-start' }}>
                        <Text style={{ color: STATUS_COLORS[r.status] || colors.textDim, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{r.status?.replace('_', ' ')}</Text>
                      </View>
                    </View>
                    <Text style={{ flex: 1, color: textSec, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{r.plan}</Text>
                    <Text style={{ flex: 1, color: r.commission_earned > 0 ? colors.success : textMuted, fontSize: 14, fontWeight: '700', textAlign: 'right' }}>
                      {r.commission_earned > 0 ? `$${r.commission_earned.toFixed(2)}` : '-'}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>
      </ScrollView>
        </FadeSlideIn>
    </AppShell>
    </View>
  );
}
