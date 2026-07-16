import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Linking, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import PublicPageShell from '../../src/components/PublicPageLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import {
  addBlogBookmark,
  BlogCard,
  BlogEngagementLoop,
  BlogHomePayload,
  BlogNextBestItem,
  BlogShareVariantOptimizer,
  claimBlogReferralBonus,
  getBlogEngagementLoop,
  getBlogHistory,
  getBlogHome,
  getBlogNextBest,
  getBlogPosts,
  getBlogRecommendations,
  getBlogRewards,
  getBlogWeeklyDigest,
  isUnauthorized,
  parseBlogError,
  removeBlogBookmark,
  trackBlogFunnelEvent,
  sendBlogReminderAction,
  updateBlogReminderSettings,
} from '../../src/services/blogV2';
import { BlogPostCard } from '../../src/components/blog/BlogPostCard';
import { BlogSectionTitle } from '../../src/components/blog/BlogSectionTitle';
import { BlogAuthorPill } from '../../src/components/blog/BlogAuthorPill';
import { BlogFilterBar } from '../../src/components/blog/BlogFilterBar';
import { SHARE_CHANNELS, SHARE_VARIANT_OPTIONS, ShareChannelKey, ShareVariantKey, shareVariantLabel, shareVariantMessage } from '../../src/utils/referralShareChannels';

type FeedSort = 'latest' | 'popular' | 'bookmarked';
type ShareVariantMode = ShareVariantKey | 'auto';

const SHARE_CHANNEL_KEYS = SHARE_CHANNELS.map((item) => item.key);

function isShareChannelKey(value: string): value is ShareChannelKey {
  return SHARE_CHANNEL_KEYS.includes(value as ShareChannelKey);
}

export default function BlogIndexPage() {
  const router = useRouter();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const { t } = useTranslation();
  t('i18n.route.blog.index.probe');

  const guestEngagementFallback: BlogEngagementLoop = useMemo(
    () => ({
      streak: {
        current: 0,
        longest: 0,
        last_read_date: '',
        days_to_keep_streak: 0,
      },
      reminder: {
        enabled: false,
        mode: 'adaptive',
        status: 'signin_required',
        message: 'Sign in to track your reading streak and unlock smart reminders.',
        next_reminder_at: '',
        snoozed_until: '',
        recommended_action: 'signin',
      },
      conversion_trigger: {
        show_upgrade_nudge: false,
        reason: 'signin_required',
        streak_threshold: 3,
        locked_premium_available: true,
      },
    }),
    []
  );

  const [home, setHome] = useState<BlogHomePayload | null>(null);
  const [posts, setPosts] = useState<BlogCard[]>([]);
  const [recommendations, setRecommendations] = useState<BlogCard[]>([]);
  const [history, setHistory] = useState<BlogCard[]>([]);
  const [engagementLoop, setEngagementLoop] = useState<BlogEngagementLoop | null>(guestEngagementFallback);
  const [nextBest, setNextBest] = useState<BlogNextBestItem[]>([]);
  const [digestHeadline, setDigestHeadline] = useState('');
  const [rewardSnapshot, setRewardSnapshot] = useState<any>(null);

  const [loadingHome, setLoadingHome] = useState(true);
  const [loadingPosts, setLoadingPosts] = useState(true);
  const [loadingRecommendations, setLoadingRecommendations] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [errorMessage, setErrorMessage] = useState('');
  const [authHint, setAuthHint] = useState('');
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [sort, setSort] = useState<FeedSort>('latest');
  const [reminderBusy, setReminderBusy] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);
  const [referralCodeInput, setReferralCodeInput] = useState('');
  const [referralBusy, setReferralBusy] = useState(false);
  const [shareVariantMode, setShareVariantMode] = useState<ShareVariantMode>('auto');
  const [sharePreviewChannel, setSharePreviewChannel] = useState<ShareChannelKey>('whatsapp');

  const categoryOptions = useMemo(() => {
    const rows = home?.categories?.map((item) => item.name).filter(Boolean) || [];
    return ['All', ...rows];
  }, [home]);

  const cardWidth = width > 1320 ? '32%' : width > 960 ? '48.5%' : '100%';
  const shareOptimizer = rewardSnapshot?.share_variant_optimizer as BlogShareVariantOptimizer | undefined;

  const sortedOptimizerChannels = useMemo(() => {
    return Object.entries(shareOptimizer?.channels || {})
      .filter(([channel]) => isShareChannelKey(channel))
      .map(([channel, stats]) => ({ channel: channel as ShareChannelKey, stats }))
      .sort((a, b) => (b.stats?.sample_size || 0) - (a.stats?.sample_size || 0));
  }, [shareOptimizer]);

  const topOptimizerChannel = useMemo(() => {
    return sortedOptimizerChannels.find((item) => item.stats?.sample_size > 0)?.channel || 'whatsapp';
  }, [sortedOptimizerChannels]);

  useEffect(() => {
    if (!sharePreviewChannel || !isShareChannelKey(sharePreviewChannel)) {
      setSharePreviewChannel(topOptimizerChannel);
    }
  }, [sharePreviewChannel, topOptimizerChannel]);

  const resolveShareVariantForChannel = useCallback((channel: ShareChannelKey): ShareVariantKey => {
    if (shareVariantMode !== 'auto') {
      return shareVariantMode;
    }
    const optimizerVariant = shareOptimizer?.channels?.[channel]?.recommended_variant;
    if (optimizerVariant === 'short' || optimizerVariant === 'long' || optimizerVariant === 'benefit') {
      return optimizerVariant;
    }
    const globalVariant = shareOptimizer?.global_top_variant;
    if (globalVariant === 'short' || globalVariant === 'long' || globalVariant === 'benefit') {
      return globalVariant;
    }
    return 'benefit';
  }, [shareOptimizer, shareVariantMode]);

  const previewResolvedVariant = useMemo(() => resolveShareVariantForChannel(sharePreviewChannel), [resolveShareVariantForChannel, sharePreviewChannel]);
  const previewMessage = useMemo(
    () => shareVariantMessage(previewResolvedVariant, rewardSnapshot?.referral?.invite_link || engagementLoop?.rewards?.invite_link || '[invite-link]'),
    [engagementLoop, previewResolvedVariant, rewardSnapshot]
  );

  const loadHome = useCallback(async () => {
    setLoadingHome(true);
    setErrorMessage('');
    try {
      const payload = await getBlogHome();
      setHome(payload);
      setEngagementLoop(payload.engagement_loop || guestEngagementFallback);
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unable to load blog home');
    } finally {
      setLoadingHome(false);
    }
  }, [guestEngagementFallback]);

  const loadEngagementLoop = useCallback(async () => {
    try {
      const payload = await getBlogEngagementLoop();
      setEngagementLoop(payload.engagement_loop || guestEngagementFallback);
    } catch {
      setEngagementLoop(guestEngagementFallback);
    }
  }, [guestEngagementFallback]);

  const loadPosts = useCallback(async () => {
    setLoadingPosts(true);
    setErrorMessage('');
    try {
      const payload = await getBlogPosts({
        q: search,
        category: activeCategory === 'All' ? '' : activeCategory,
        sort,
        page: 1,
        page_size: 12,
      });
      setPosts(payload.items || []);
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unable to load blog posts');
    } finally {
      setLoadingPosts(false);
    }
  }, [search, activeCategory, sort]);

  const loadDigestAndSequencing = useCallback(async () => {
    try {
      const digest = await getBlogWeeklyDigest(false, false);
      setDigestHeadline(digest?.digest?.headline || 'Your weekly reading momentum digest');
      const next = await getBlogNextBest(5, false);
      setNextBest(next?.items || []);
    } catch {
      setDigestHeadline('Your weekly reading momentum digest');
      setNextBest([]);
    }
  }, []);

  const loadRewards = useCallback(async () => {
    try {
      const payload = await getBlogRewards();
      setRewardSnapshot(payload);
    } catch {
      setRewardSnapshot(null);
    }
  }, []);

  const loadRecommendations = useCallback(async () => {
    setLoadingRecommendations(true);
    try {
      const payload = await getBlogRecommendations(8);
      setRecommendations(payload.items || []);
    } catch {
      setRecommendations([]);
    } finally {
      setLoadingRecommendations(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setAuthHint('');
    try {
      const payload = await getBlogHistory();
      setHistory(payload.items || []);
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthHint('Sign in to unlock reading history and saved progress.');
      }
      setHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHome();
    loadRecommendations();
    loadHistory();
    loadEngagementLoop();
    loadDigestAndSequencing();
    loadRewards();
  }, [loadHome, loadRecommendations, loadHistory, loadEngagementLoop, loadDigestAndSequencing, loadRewards]);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  const applyBookmarkMutation = useCallback((postId: string, nextBookmarked: boolean) => {
    const mutate = (rows: BlogCard[]) => rows.map((item) => (item.post_id === postId ? { ...item, bookmarked: nextBookmarked } : item));
    setPosts((prev) => mutate(prev));
    setRecommendations((prev) => mutate(prev));
    setHistory((prev) => mutate(prev));
    setHome((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        latest: mutate(prev.latest || []),
        trending: mutate(prev.trending || []),
        featured: prev.featured?.post_id === postId ? { ...prev.featured, bookmarked: nextBookmarked } : prev.featured,
      };
    });
  }, []);

  const onToggleBookmark = useCallback(async (post: BlogCard) => {
    try {
      if (post.bookmarked) {
        await removeBlogBookmark(post.post_id);
        applyBookmarkMutation(post.post_id, false);
      } else {
        await addBlogBookmark(post.post_id);
        applyBookmarkMutation(post.post_id, true);
      }
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthHint('Please sign in to save bookmarks and member insights.');
        return;
      }
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Bookmark update failed');
    }
  }, [applyBookmarkMutation]);

  const onReminderModeChange = useCallback(async () => {
    if (reminderBusy) return;
    if (!engagementLoop) return;
    setReminderBusy(true);
    try {
      const order: ('adaptive' | 'daily' | 'three_per_week')[] = ['adaptive', 'daily', 'three_per_week'];
      const idx = Math.max(0, order.indexOf((engagementLoop.reminder.mode as any) || 'adaptive'));
      const nextMode = order[(idx + 1) % order.length];
      const payload = await updateBlogReminderSettings({ mode: nextMode });
      setEngagementLoop(payload.engagement_loop || null);
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthHint('Sign in to manage smart reminders.');
      }
    } finally {
      setReminderBusy(false);
    }
  }, [engagementLoop, reminderBusy]);

  const onToggleDigestSettings = useCallback(async (kind: 'in_app' | 'email') => {
    if (!engagementLoop || reminderBusy) return;
    const digest = engagementLoop.reminder.digest || { in_app_enabled: true, email_enabled: true, last_digest_at: '', last_email_digest_at: '' };
    const payload = await updateBlogReminderSettings({
      digest_in_app_enabled: kind === 'in_app' ? !digest.in_app_enabled : digest.in_app_enabled,
      digest_email_enabled: kind === 'email' ? !digest.email_enabled : digest.email_enabled,
    });
    setEngagementLoop(payload.engagement_loop || null);
  }, [engagementLoop, reminderBusy]);

  const onReminderSnooze = useCallback(async () => {
    if (reminderBusy) return;
    setReminderBusy(true);
    try {
      const payload = await sendBlogReminderAction('snooze_24h');
      setEngagementLoop(payload.engagement_loop || null);
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthHint('Sign in to snooze reminders.');
      }
    } finally {
      setReminderBusy(false);
    }
  }, [reminderBusy]);

  const onSendDigestNow = useCallback(async () => {
    if (digestBusy) return;
    setDigestBusy(true);
    try {
      const payload = await getBlogWeeklyDigest(true, true);
      setDigestHeadline(payload?.digest?.headline || 'Your weekly reading momentum digest');
      await loadDigestAndSequencing();
      await loadRewards();
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthHint('Sign in to send your weekly digest.');
      }
    } finally {
      setDigestBusy(false);
    }
  }, [digestBusy, loadDigestAndSequencing, loadRewards]);

  const onClaimReferral = useCallback(async () => {
    if (!referralCodeInput.trim() || referralBusy) return;
    setReferralBusy(true);
    try {
      await trackBlogFunnelEvent('claim_attempt', { invite_code: referralCodeInput.trim().toUpperCase() });
      await claimBlogReferralBonus(referralCodeInput.trim().toUpperCase());
      await trackBlogFunnelEvent('claim_success', { invite_code: referralCodeInput.trim().toUpperCase(), channel: 'referral_claim' });
      setReferralCodeInput('');
      await loadEngagementLoop();
      await loadRewards();
      await loadDigestAndSequencing();
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unable to claim referral code');
    } finally {
      setReferralBusy(false);
    }
  }, [referralCodeInput, referralBusy, loadEngagementLoop, loadRewards, loadDigestAndSequencing]);

  const onCopyReferralLink = useCallback(async () => {
    const link = rewardSnapshot?.referral?.invite_link || engagementLoop?.rewards?.invite_link || '';
    if (!link) {
      setAuthHint('Sign in to generate your referral link.');
      return;
    }
    await Clipboard.setStringAsync(link);
    setAuthHint('Referral link copied to clipboard.');
    try {
      await trackBlogFunnelEvent('copy_clicked', { link });
    } catch {
      // non-blocking
    }
  }, [rewardSnapshot, engagementLoop]);

  const onShareReferralLink = useCallback(async () => {
    const link = rewardSnapshot?.referral?.invite_link || engagementLoop?.rewards?.invite_link || '';
    if (!link) {
      setAuthHint('Sign in to generate your referral link.');
      return;
    }

    try {
      const navigatorAny = (globalThis as any)?.navigator;
      if (navigatorAny?.share) {
        await navigatorAny.share({
          title: 'Join me on RealAICoach Blog',
          text: 'Use my invite link to start your streak and unlock rewards.',
          url: link,
        });
      } else {
        await Clipboard.setStringAsync(link);
      }
      setAuthHint(`Share this invite link: ${link}`);
      await trackBlogFunnelEvent('share_clicked', { link });
    } catch {
      setAuthHint(`Share this invite link: ${link}`);
    }
  }, [rewardSnapshot, engagementLoop]);

  const onShareByChannel = useCallback(async (channel: ShareChannelKey) => {
    const link = rewardSnapshot?.referral?.invite_link || engagementLoop?.rewards?.invite_link || '';
    if (!link) {
      setAuthHint('Sign in to generate your referral link.');
      return;
    }

    const resolvedVariant = resolveShareVariantForChannel(channel);
    const optimizerChannel = shareOptimizer?.channels?.[channel];
    const message = shareVariantMessage(resolvedVariant, link);
    const channelSpec = SHARE_CHANNELS.find((c) => c.key === channel);
    if (!channelSpec) return;
    setSharePreviewChannel(channel);

    try {
      if (channel === 'copy') {
        await Clipboard.setStringAsync(link);
        setAuthHint('Referral link copied to clipboard.');
      } else {
        const url = channelSpec.buildUrl(link, message);
        const canOpen = await Linking.canOpenURL(url);
        if (canOpen) {
          await Linking.openURL(url);
        } else {
          await Linking.openURL(link);
        }
        setAuthHint(`Opening share via ${channelSpec.label}…`);
      }
      const track = await trackBlogFunnelEvent(channel === 'copy' ? 'copy_clicked' : 'share_clicked', {
        channel,
        link,
        surface: 'blog_home_referral',
        share_variant: resolvedVariant,
        share_variant_source: shareVariantMode === 'auto' ? 'optimizer_auto' : 'manual_override',
        optimizer_strategy: shareVariantMode === 'auto' ? optimizerChannel?.strategy || 'fallback' : 'manual_override',
      });
      if (track?.status === 'cooldown_suppressed') {
        setAuthHint(`Hold on—${channelSpec.label} share is on 30s cooldown.`);
      } else if (track?.status === 'dedupe_suppressed') {
        setAuthHint(`Duplicate ${channelSpec.label} share suppressed within 5-minute window.`);
      }
      await loadRewards();
    } catch {
      setAuthHint(`Share this invite link: ${link}`);
    }
  }, [rewardSnapshot, engagementLoop, resolveShareVariantForChannel, shareOptimizer, shareVariantMode, loadRewards]);

  return (
    <PublicPageShell
      title="Blog"
      subtitle="Enterprise-grade insights, member playbooks, and AI-assisted recommendations"
      testID="blog-index-page"
      data-testid="blog-index-page"
    >
      <ScrollView contentContainerStyle={{ paddingBottom: 64 }} data-testid="blog-index-scroll" testID="blog-index-scroll">
        <View
          style={{
            borderWidth: 1,
            borderColor: colors.border,
            borderRadius: 24,
            backgroundColor: colors.card,
            padding: 24,
            gap: 14,
            marginBottom: 22,
          }}
          data-testid="blog-hero-panel"
          testID="blog-hero-panel"
        >
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <Text style={{ color: colors.text, fontSize: width > 900 ? 38 : 30, fontWeight: '900', lineHeight: width > 900 ? 44 : 36 }} data-testid="blog-hero-title" testID="blog-hero-title">
              RealAICoach Pro Blog
            </Text>
            <TouchableOpacity
              data-testid="blog-open-bookmarks-button"
              testID="blog-open-bookmarks-button"
              onPress={() => router.push('/blog/bookmarks')}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 8,
                borderRadius: 999,
                paddingHorizontal: 14,
                paddingVertical: 10,
                backgroundColor: colors.primary,
              }}
            >
              <Ionicons name="bookmark" size={14} color={colors.primaryText} />
              <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>My Bookmarks</Text>
            </TouchableOpacity>
          </View>

          <Text style={{ color: colors.textSecondary, fontSize: 15, lineHeight: 22 }} data-testid="blog-hero-subtitle" testID="blog-hero-subtitle">
            From tactical checklists to premium implementation playbooks — designed for professionals who ship outcomes.
          </Text>

          {home?.featured ? (
            <BlogPostCard post={home.featured} onOpen={(slug) => router.push(`/blog/${slug}`)} onToggleBookmark={onToggleBookmark} />
          ) : null}
        </View>

        {engagementLoop ? (
          <View style={{
            borderWidth: 1,
            borderColor: colors.border,
            borderRadius: 20,
            backgroundColor: colors.card,
            padding: 18,
            gap: 12,
            marginBottom: 18,
          }} data-testid="blog-engagement-loop-card" testID="blog-engagement-loop-card">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="blog-streak-title" testID="blog-streak-title">
                Read Streak
              </Text>
              <View style={{ borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: colors.primarySoft }}>
                <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }} data-testid="blog-streak-current" testID="blog-streak-current">
                  {engagementLoop.streak.current} day streak
                </Text>
              </View>
            </View>

            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Longest</Text>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="blog-streak-longest" testID="blog-streak-longest">{engagementLoop.streak.longest} days</Text>
              </View>
              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Reminder Mode</Text>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', textTransform: 'capitalize' }} data-testid="blog-reminder-mode" testID="blog-reminder-mode">
                  {String(engagementLoop.reminder.mode || 'adaptive').replace('_', ' ')}
                </Text>
              </View>
              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Reminder Status</Text>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', textTransform: 'capitalize' }} data-testid="blog-reminder-status" testID="blog-reminder-status">
                  {engagementLoop.reminder.status.replace('_', ' ')}
                </Text>
              </View>
            </View>

            <Text style={{ color: colors.textSecondary, fontSize: 13, lineHeight: 20 }} data-testid="blog-reminder-message" testID="blog-reminder-message">
              {engagementLoop.reminder.message}
            </Text>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {engagementLoop.reminder.status === 'signin_required' ? (
                <TouchableOpacity
                  data-testid="blog-streak-signin-cta-button"
                  testID="blog-streak-signin-cta-button"
                  onPress={() => router.push('/auth/login?return_to=%2Fblog')}
                  style={{ borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 9 }}
                >
                  <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>Sign in to activate reminders</Text>
                </TouchableOpacity>
              ) : (
                <>
                  <TouchableOpacity
                    data-testid="blog-reminder-cycle-mode-button"
                    testID="blog-reminder-cycle-mode-button"
                    disabled={reminderBusy}
                    onPress={onReminderModeChange}
                    style={{ borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 9 }}
                  >
                    <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{reminderBusy ? 'Updating…' : 'Cycle Reminder Mode'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    data-testid="blog-reminder-snooze-button"
                    testID="blog-reminder-snooze-button"
                    disabled={reminderBusy}
                    onPress={onReminderSnooze}
                    style={{ borderRadius: 10, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 9 }}
                  >
                    <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{reminderBusy ? 'Please wait…' : 'Snooze 24h'}</Text>
                  </TouchableOpacity>
                </>
              )}
              {engagementLoop.conversion_trigger.show_upgrade_nudge ? (
                <TouchableOpacity
                  data-testid="blog-streak-upgrade-cta-button"
                  testID="blog-streak-upgrade-cta-button"
                  onPress={() => router.push('/pricing')}
                  style={{ borderRadius: 10, backgroundColor: colors.warning, paddingHorizontal: 12, paddingVertical: 9 }}
                >
                  <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 12 }}>Unlock Premium Streak Boosters</Text>
                </TouchableOpacity>
              ) : null}
            </View>

            <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, gap: 8 }}>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="blog-weekly-digest-headline" testID="blog-weekly-digest-headline">
                {digestHeadline || 'Your weekly reading momentum digest'}
              </Text>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  data-testid="blog-digest-toggle-inapp-button"
                  testID="blog-digest-toggle-inapp-button"
                  onPress={() => onToggleDigestSettings('in_app')}
                  style={{ borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: (engagementLoop.reminder.digest?.in_app_enabled ?? true) ? colors.successSoft : colors.card }}
                >
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>In-app digest {(engagementLoop.reminder.digest?.in_app_enabled ?? true) ? 'ON' : 'OFF'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  data-testid="blog-digest-toggle-email-button"
                  testID="blog-digest-toggle-email-button"
                  onPress={() => onToggleDigestSettings('email')}
                  style={{ borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: (engagementLoop.reminder.digest?.email_enabled ?? true) ? colors.successSoft : colors.card }}
                >
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Email digest {(engagementLoop.reminder.digest?.email_enabled ?? true) ? 'ON' : 'OFF'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  data-testid="blog-send-digest-now-button"
                  testID="blog-send-digest-now-button"
                  onPress={onSendDigestNow}
                  style={{ borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8 }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{digestBusy ? 'Sending…' : 'Send digest now'}</Text>
                </TouchableOpacity>
              </View>

              {(rewardSnapshot?.streak?.badges || []).length ? (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="blog-milestone-badges" testID="blog-milestone-badges">
                  {(rewardSnapshot?.streak?.badges || []).map((badge: string) => (
                    <View key={badge} style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.infoSoft }}>
                      <Text style={{ color: colors.infoText, fontSize: 11, fontWeight: '800' }} data-testid={`blog-milestone-badge-${badge}`} testID={`blog-milestone-badge-${badge}`}>
                        {badge.replace('_', ' ').toUpperCase()}
                      </Text>
                    </View>
                  ))}
                </View>
              ) : null}

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="blog-referral-code-display" testID="blog-referral-code-display">
                  Your invite code: {rewardSnapshot?.referral?.invite_code || engagementLoop.rewards?.invite_code || 'N/A'}
                </Text>
                <TouchableOpacity
                  data-testid="blog-copy-referral-link-button"
                  testID="blog-copy-referral-link-button"
                  onPress={onCopyReferralLink}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: colors.card }}
                >
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Copy invite link</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  data-testid="blog-share-referral-link-button"
                  testID="blog-share-referral-link-button"
                  onPress={onShareReferralLink}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: colors.card }}
                >
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Share invite link</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="blog-share-variant-group" testID="blog-share-variant-group">
                {([{ key: 'auto', label: 'Auto-optimize' }, ...SHARE_VARIANT_OPTIONS] as { key: ShareVariantMode; label: string }[]).map((variant) => {
                  const active = shareVariantMode === variant.key;
                  return (
                    <TouchableOpacity
                      key={variant.key}
                      data-testid={`blog-share-variant-${variant.key}`}
                      testID={`blog-share-variant-${variant.key}`}
                      onPress={() => setShareVariantMode(variant.key)}
                      style={{
                        borderRadius: 999,
                        borderWidth: 1,
                        borderColor: active ? colors.primary : colors.border,
                        backgroundColor: active ? colors.primary : colors.card,
                        paddingHorizontal: 10,
                        paddingVertical: 7,
                      }}
                    >
                      <Text style={{ color: active ? colors.primaryText : colors.text, fontWeight: '700', fontSize: 11 }}>{variant.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {shareOptimizer ? (
                <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surfaceHover, padding: 12, gap: 8 }} data-testid="blog-share-auto-optimizer-card" testID="blog-share-auto-optimizer-card">
                  <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="blog-share-auto-optimizer-title" testID="blog-share-auto-optimizer-title">
                    AI auto-optimizer live
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }} data-testid="blog-share-auto-optimizer-strategy" testID="blog-share-auto-optimizer-strategy">
                    {shareVariantMode === 'auto'
                      ? `Auto mode is active. ${shareVariantLabel(previewResolvedVariant)} is currently rotating for ${SHARE_CHANNELS.find((item) => item.key === sharePreviewChannel)?.label || sharePreviewChannel}.`
                      : `Manual override is active. Switch back to Auto-optimize to rotate the winning variant per channel.`}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="blog-share-auto-optimizer-window" testID="blog-share-auto-optimizer-window">
                    Rolling window: {shareOptimizer.window_days} days · Global leader: {shareOptimizer.global_top_variant_label}
                  </Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {sortedOptimizerChannels.slice(0, 4).map(({ channel, stats }) => (
                      <TouchableOpacity
                        key={channel}
                        onPress={() => setSharePreviewChannel(channel)}
                        style={{
                          borderRadius: 12,
                          borderWidth: 1,
                          borderColor: sharePreviewChannel === channel ? colors.primary : colors.border,
                          backgroundColor: sharePreviewChannel === channel ? colors.primarySoft : colors.card,
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                          minWidth: 132,
                          gap: 2,
                        }}
                        data-testid={`blog-share-auto-optimizer-channel-${channel}`}
                        testID={`blog-share-auto-optimizer-channel-${channel}`}
                      >
                        <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', textTransform: 'capitalize' }}>
                          {SHARE_CHANNELS.find((item) => item.key === channel)?.label || channel}
                        </Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                          {stats?.recommended_label || 'Benefit-first'} · {stats?.strategy?.replace(/_/g, ' ') || 'warmup'}
                        </Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                          {stats?.sample_size || 0} shares · {stats?.winner_share_pct || 0}% winner share
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ) : null}

              <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }} data-testid="blog-share-variant-preview" testID="blog-share-variant-preview">
                Preview ({shareVariantMode === 'auto' ? `Auto • ${SHARE_CHANNELS.find((item) => item.key === sharePreviewChannel)?.label || sharePreviewChannel}` : shareVariantLabel(previewResolvedVariant)}): {previewMessage}
              </Text>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="blog-share-channels-grid" testID="blog-share-channels-grid">
                {SHARE_CHANNELS.map((channel) => (
                  <TouchableOpacity
                    key={channel.key}
                    data-testid={`blog-share-channel-${channel.key}`}
                    testID={`blog-share-channel-${channel.key}`}
                    onPress={() => onShareByChannel(channel.key)}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: colors.border,
                      backgroundColor: colors.card,
                      paddingHorizontal: 10,
                      paddingVertical: 7,
                      minWidth: 112,
                    }}
                  >
                    <Ionicons name={channel.icon as any} size={12} color={colors.textMuted} />
                    <View style={{ minWidth: 0, flex: 1 }}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{channel.label}</Text>
                      {shareVariantMode === 'auto' ? (
                        <Text style={{ color: colors.textMuted, fontSize: 9 }} numberOfLines={1} data-testid={`blog-share-channel-hint-${channel.key}`} testID={`blog-share-channel-hint-${channel.key}`}>
                          {shareOptimizer?.channels?.[channel.key]?.recommended_label || shareOptimizer?.global_top_variant_label || 'Benefit-first'}
                        </Text>
                      ) : null}
                    </View>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <TextInput
                  data-testid="blog-referral-code-input"
                  testID="blog-referral-code-input"
                  value={referralCodeInput}
                  onChangeText={(v) => setReferralCodeInput(v.toUpperCase())}
                  placeholder="Enter invite code (e.g., BLOG-AB12CD34)"
                  placeholderTextColor={colors.textMuted}
                  style={{ minWidth: 280, flex: 1, color: colors.text, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8, fontSize: 12 }}
                />
                <TouchableOpacity
                  data-testid="blog-referral-claim-button"
                  testID="blog-referral-claim-button"
                  onPress={onClaimReferral}
                  style={{ borderRadius: 10, backgroundColor: colors.warning, paddingHorizontal: 12, paddingVertical: 8 }}
                >
                  <Text style={{ color: colors.buttonText, fontSize: 12, fontWeight: '800' }}>{referralBusy ? 'Claiming…' : 'Claim referral bonus'}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.surfaceHover, padding: 12, gap: 8 }} data-testid="blog-channel-attribution-dashboard" testID="blog-channel-attribution-dashboard">
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Channel Attribution (7d)</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="blog-channel-attribution-top" testID="blog-channel-attribution-top">
                  Top channel: {rewardSnapshot?.channel_attribution?.top_channel || 'none'}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="blog-channel-attribution-totals" testID="blog-channel-attribution-totals">
                  Clicks: {rewardSnapshot?.channel_attribution?.totals?.clicks || 0} · Unique: {rewardSnapshot?.channel_attribution?.totals?.unique_clicks || 0} · Claim-attributed: {rewardSnapshot?.channel_attribution?.totals?.claim_attributed_clicks || 0}
                </Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {Object.entries(rewardSnapshot?.channel_attribution?.channels || {}).map(([channel, stats]: any) => (
                    <View key={channel} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', textTransform: 'capitalize' }} data-testid={`blog-channel-stat-${channel}`} testID={`blog-channel-stat-${channel}`}>
                        {channel}
                      </Text>
                      <Text style={{ color: colors.textMuted, fontSize: 11 }}>
                        {stats?.clicks || 0} clicks · {stats?.unique_clicks || 0} unique
                      </Text>
                    </View>
                  ))}
                </View>

                <View style={{ gap: 4 }}>
                  {(rewardSnapshot?.channel_attribution?.trend || []).slice(-7).map((row: any) => (
                    <Text key={row.date} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`blog-channel-trend-${row.date}`} testID={`blog-channel-trend-${row.date}`}>
                      {row.date}: {row.clicks} clicks
                    </Text>
                  ))}
                </View>
              </View>
            </View>
          </View>
        ) : null}

        <BlogFilterBar
          search={search}
          onSearchChange={setSearch}
          onSearchSubmit={loadPosts}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
          categories={categoryOptions}
        />

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, marginBottom: 20, flexWrap: 'wrap' }} data-testid="blog-sort-bar" testID="blog-sort-bar">
          {(['latest', 'popular', 'bookmarked'] as FeedSort[]).map((key) => {
            const active = sort === key;
            return (
              <TouchableOpacity
                key={key}
                data-testid={`blog-sort-${key}`}
                testID={`blog-sort-${key}`}
                onPress={() => setSort(key)}
                style={{
                  borderRadius: 999,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  backgroundColor: active ? colors.primary : colors.card,
                  borderWidth: 1,
                  borderColor: active ? colors.primary : colors.border,
                }}
              >
                <Text style={{ color: active ? colors.primaryText : colors.text, fontWeight: '700', fontSize: 12, textTransform: 'capitalize' }}>{key}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {errorMessage ? (
          <View style={{ marginBottom: 16, borderWidth: 1, borderColor: colors.error, borderRadius: 12, backgroundColor: colors.errorSoft, padding: 12 }} data-testid="blog-error-alert" testID="blog-error-alert">
            <Text style={{ color: colors.errorText, fontSize: 13, fontWeight: '700' }}>{errorMessage}</Text>
          </View>
        ) : null}

        {authHint ? (
          <View style={{ marginBottom: 16, borderWidth: 1, borderColor: colors.warning, borderRadius: 12, backgroundColor: colors.warningSoft, padding: 12 }} data-testid="blog-auth-hint" testID="blog-auth-hint">
            <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '700' }}>{authHint}</Text>
          </View>
        ) : null}

        <BlogSectionTitle title="Latest Insights" subtitle="Searchable, categorized, and optimized for execution" testId="blog-latest-section-title" />

        {loadingPosts ? (
          <View style={{ paddingVertical: 36 }} data-testid="blog-posts-loading" testID="blog-posts-loading">
            <ActivityIndicator color={colors.primary} />
          </View>
        ) : posts.length === 0 ? (
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.card, padding: 18 }} data-testid="blog-posts-empty" testID="blog-posts-empty">
            <Text style={{ color: colors.text, fontWeight: '700', fontSize: 16 }}>No matching articles found.</Text>
            <Text style={{ color: colors.textMuted, marginTop: 6 }}>Try another keyword or category to continue exploring.</Text>
          </View>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 14 }} data-testid="blog-posts-grid" testID="blog-posts-grid">
            {posts.map((post) => (
              <View key={post.post_id} style={{ width: cardWidth }}>
                <BlogPostCard post={post} onOpen={(slug) => router.push(`/blog/${slug}`)} onToggleBookmark={onToggleBookmark} />
              </View>
            ))}
          </View>
        )}

        <View style={{ marginTop: 26 }}>
          <BlogSectionTitle title="Editors & Analysts" subtitle="Follow domain specialists and their latest playbooks" testId="blog-authors-section-title" />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="blog-authors-strip" testID="blog-authors-strip">
            {(home?.authors || []).map((author) => (
              <BlogAuthorPill key={author.author_slug} author={author} onOpen={(slug) => router.push(`/blog/authors/${slug}`)} />
            ))}
          </View>
        </View>

        <View style={{ marginTop: 28 }}>
          <BlogSectionTitle title="Next Best Sequence" subtitle="Contextual progression powered by rules + GPT reranking" testId="blog-next-best-section-title" />
          {nextBest.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }} data-testid="blog-next-best-strip" testID="blog-next-best-strip">
              {nextBest.map((item) => (
                <View key={`next-${item.post_id}`} style={{ width: width > 900 ? '42%' : '78%' }}>
                  <BlogPostCard post={{ ...item, tags: [], author_slug: '', author_role: '', date_display: '', published_at: '', premium_locked: false, bookmarked: false }} compact onOpen={(slug) => router.push(`/blog/${slug}`)} />
                  <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6, lineHeight: 18 }} data-testid={`blog-next-best-reason-${item.post_id}`} testID={`blog-next-best-reason-${item.post_id}`}>
                    {item.sequence_reason}
                  </Text>
                </View>
              ))}
            </ScrollView>
          ) : (
            <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 12 }} data-testid="blog-next-best-empty" testID="blog-next-best-empty">
              <Text style={{ color: colors.textMuted, fontSize: 13 }}>Sign in and read articles to activate next-best sequencing.</Text>
            </View>
          )}
        </View>

        <View style={{ marginTop: 28 }}>
          <BlogSectionTitle title="Because You Read" subtitle="Personalized recommendations from your behavior and priorities" testId="blog-recommendations-section-title" />
          {loadingRecommendations ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }} data-testid="blog-recommendations-strip" testID="blog-recommendations-strip">
              {recommendations.map((item) => (
                <BlogPostCard
                  key={`rec-${item.post_id}`}
                  post={item}
                  compact
                  onOpen={(slug) => router.push(`/blog/${slug}`)}
                  onToggleBookmark={onToggleBookmark}
                />
              ))}
            </ScrollView>
          )}
        </View>

        <View style={{ marginTop: 28 }}>
          <BlogSectionTitle title="Continue Reading" subtitle="Your recent reading timeline with persistent progress" testId="blog-history-section-title" />
          {loadingHistory ? (
            <ActivityIndicator color={colors.primary} />
          ) : history.length === 0 ? (
            <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.card, padding: 18 }} data-testid="blog-history-empty" testID="blog-history-empty">
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 16 }}>No history yet.</Text>
              <Text style={{ color: colors.textMuted, marginTop: 6 }}>Open any article to start tracking progress and personalized picks.</Text>
            </View>
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }} data-testid="blog-history-strip" testID="blog-history-strip">
              {history.map((item) => (
                <BlogPostCard
                  key={`history-${item.post_id}`}
                  post={item}
                  compact
                  onOpen={(slug) => router.push(`/blog/${slug}`)}
                  onToggleBookmark={onToggleBookmark}
                />
              ))}
            </ScrollView>
          )}
        </View>

        <View
          style={{
            marginTop: 32,
            borderWidth: 1,
            borderColor: colors.border,
            borderRadius: 20,
            backgroundColor: colors.card,
            padding: 20,
            gap: 10,
          }}
          data-testid="blog-membership-panel"
          testID="blog-membership-panel"
        >
          <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="blog-membership-title" testID="blog-membership-title">
            Member-only Deep Insights
          </Text>
          <Text style={{ color: colors.textSecondary, fontSize: 14, lineHeight: 21 }} data-testid="blog-membership-copy" testID="blog-membership-copy">
            Free users get high-signal previews. Members unlock full implementation playbooks, AI summaries, and action plans.
          </Text>
          <TouchableOpacity
            data-testid="blog-membership-upgrade-button"
            testID="blog-membership-upgrade-button"
            onPress={() => router.push('/pricing')}
            style={{
              alignSelf: 'flex-start',
              marginTop: 4,
              backgroundColor: colors.primary,
              borderRadius: 12,
              paddingHorizontal: 14,
              paddingVertical: 10,
            }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>See Member Plans</Text>
          </TouchableOpacity>
        </View>

        {loadingHome ? (
          <View style={{ marginTop: 18, paddingVertical: 16 }} data-testid="blog-home-loading" testID="blog-home-loading">
            <ActivityIndicator color={colors.primary} />
          </View>
        ) : null}
      </ScrollView>
    </PublicPageShell>
  );
}
