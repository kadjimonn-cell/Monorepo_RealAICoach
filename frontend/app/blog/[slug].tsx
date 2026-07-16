import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, ScrollView, Text, TouchableOpacity, View, Linking } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import PublicPageShell from '../../src/components/PublicPageLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import {
  addBlogBookmark,
  BlogDetailPayload,
  getAiSummary,
  getBlogPost,
  isUnauthorized,
  parseBlogError,
  removeBlogBookmark,
  trackBlogFunnelEvent,
  unlockBlogPremiumWithToken,
  writeBlogHistory,
} from '../../src/services/blogV2';
import { BlogPostCard } from '../../src/components/blog/BlogPostCard';
import { BlogSectionTitle } from '../../src/components/blog/BlogSectionTitle';
import { SHARE_CHANNELS, ShareChannelKey } from '../../src/utils/referralShareChannels';

export default function BlogDetailPage() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.blog.index.probe');

  const [detail, setDetail] = useState<BlogDetailPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiSummary, setAiSummary] = useState<null | {
    summary: string;
    key_takeaways: string[];
    action_plan: string[];
    upgrade_required?: boolean;
  }>(null);
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockTokens, setUnlockTokens] = useState<number | null>(null);

  const postSlug = useMemo(() => String(slug || '').trim(), [slug]);

  const loadDetail = useCallback(async () => {
    if (!postSlug) return;
    setLoading(true);
    setErrorMessage('');
    try {
      const payload = await getBlogPost(postSlug);
      setDetail(payload);
      try {
        await trackBlogFunnelEvent('link_shown', { slug: postSlug, post_id: payload.post_id });
      } catch {
        // non-blocking
      }
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unable to load article');
    } finally {
      setLoading(false);
    }
  }, [postSlug]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    if (!detail?.post_id) return;
    const timer = setTimeout(() => {
      writeBlogHistory(detail.post_id, 12, 45).catch(() => {
        // no-op for unauthenticated users
      });
    }, 1200);
    return () => clearTimeout(timer);
  }, [detail?.post_id]);

  const onToggleBookmark = useCallback(async () => {
    if (!detail || bookmarkBusy) return;
    setBookmarkBusy(true);
    try {
      if (detail.bookmarked) {
        await removeBlogBookmark(detail.post_id);
        setDetail({ ...detail, bookmarked: false });
      } else {
        await addBlogBookmark(detail.post_id);
        setDetail({ ...detail, bookmarked: true });
      }
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setErrorMessage('Please sign in to save bookmarks.');
      } else {
        const parsed = parseBlogError(error);
        setErrorMessage(parsed.message || 'Bookmark update failed');
      }
    } finally {
      setBookmarkBusy(false);
    }
  }, [detail, bookmarkBusy]);

  const onGenerateAiSummary = useCallback(async () => {
    if (!detail || aiBusy) return;
    setAiBusy(true);
    try {
      const payload = await getAiSummary(detail.slug);
      setAiSummary({
        summary: payload.summary,
        key_takeaways: payload.key_takeaways || [],
        action_plan: payload.action_plan || [],
        upgrade_required: payload.upgrade_required,
      });
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'AI summary unavailable right now');
    } finally {
      setAiBusy(false);
    }
  }, [detail, aiBusy]);

  const onUnlockPremiumInsight = useCallback(async () => {
    if (!detail || unlockBusy) return;
    setUnlockBusy(true);
    try {
      const result = await unlockBlogPremiumWithToken(detail.post_id);
      setUnlockTokens(result.remaining_tokens);
      await trackBlogFunnelEvent('premium_unlock_cta_click', { post_id: detail.post_id, slug: detail.slug, status: result.status });
      const refreshed = await getBlogPost(detail.slug);
      setDetail(refreshed);
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unlock failed. Earn more tokens from streak milestones.');
    } finally {
      setUnlockBusy(false);
    }
  }, [detail, unlockBusy]);

  const onShareDetailByChannel = useCallback(async (channel: ShareChannelKey) => {
    if (!detail) return;
    const link = typeof window !== 'undefined' && window?.location?.origin
      ? `${window.location.origin}/blog/${detail.slug}`
      : `/blog/${detail.slug}`;
    const message = `Read this insight: ${detail.title}`;
    const channelSpec = SHARE_CHANNELS.find((c) => c.key === channel);
    if (!channelSpec) return;

    try {
      if (channel === 'copy') {
        await Clipboard.setStringAsync(link);
      } else {
        const url = channelSpec.buildUrl(link, message);
        const canOpen = await Linking.canOpenURL(url);
        await Linking.openURL(canOpen ? url : link);
      }
      await trackBlogFunnelEvent(channel === 'copy' ? 'copy_clicked' : 'share_clicked', {
        channel,
        link,
        post_id: detail.post_id,
        slug: detail.slug,
        surface: 'blog_detail',
      });
    } catch {
      // non-blocking on sharing surface
    }
  }, [detail]);

  if (loading) {
    return (
      <PublicPageShell title="Blog" subtitle="Loading article" testID="blog-detail-loading-page" data-testid="blog-detail-loading-page">
        <View style={{ paddingVertical: 40 }} data-testid="blog-detail-loading" testID="blog-detail-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      </PublicPageShell>
    );
  }

  if (!detail) {
    return (
      <PublicPageShell title="Blog" subtitle="Article unavailable" testID="blog-detail-empty-page" data-testid="blog-detail-empty-page">
        <View style={{ borderWidth: 1, borderColor: colors.error, borderRadius: 14, backgroundColor: colors.errorSoft, padding: 16 }} data-testid="blog-detail-empty" testID="blog-detail-empty">
          <Text style={{ color: colors.errorText, fontWeight: '700', fontSize: 14 }}>
            {errorMessage || 'This article could not be loaded.'}
          </Text>
          <TouchableOpacity
            data-testid="blog-detail-back-home-button"
            testID="blog-detail-back-home-button"
            onPress={() => router.push('/blog')}
            style={{ marginTop: 10, alignSelf: 'flex-start', backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>Back to Blog</Text>
          </TouchableOpacity>
        </View>
      </PublicPageShell>
    );
  }

  const visibleBlocks = detail.premium_gate?.unlocked ? detail.content_blocks : detail.preview_blocks;

  return (
    <PublicPageShell title={detail.title} subtitle={detail.excerpt} testID="blog-detail-page" data-testid="blog-detail-page">
      <ScrollView contentContainerStyle={{ paddingBottom: 56 }} data-testid="blog-detail-scroll" testID="blog-detail-scroll">
        {detail.cover_image ? (
          <Image source={{ uri: detail.cover_image }} style={{ width: '100%', height: 300, borderRadius: 18, marginBottom: 16 }} resizeMode="cover" />
        ) : null}

        <View style={{ marginBottom: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.primary, textTransform: 'uppercase', fontWeight: '800', fontSize: 11 }} data-testid="blog-detail-category" testID="blog-detail-category">
              {detail.category}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }} data-testid="blog-detail-meta" testID="blog-detail-meta">
              {detail.author_name} · {detail.read_time_minutes} min · {detail.date_display || 'Recently updated'}
            </Text>
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity
              data-testid="blog-detail-bookmark-button"
              testID="blog-detail-bookmark-button"
              disabled={bookmarkBusy}
              onPress={onToggleBookmark}
              style={{ backgroundColor: detail.bookmarked ? colors.primary : colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }}
            >
              <Text style={{ color: detail.bookmarked ? colors.primaryText : colors.text, fontWeight: '700', fontSize: 12 }}>
                {bookmarkBusy ? 'Saving...' : detail.bookmarked ? 'Saved' : 'Save'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              data-testid="blog-detail-ai-summary-button"
              testID="blog-detail-ai-summary-button"
              disabled={aiBusy}
              onPress={onGenerateAiSummary}
              style={{ backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }}
            >
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>{aiBusy ? 'Generating…' : 'AI Summary'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {errorMessage ? (
          <View style={{ marginBottom: 14, borderWidth: 1, borderColor: colors.error, borderRadius: 12, backgroundColor: colors.errorSoft, padding: 12 }} data-testid="blog-detail-error" testID="blog-detail-error">
            <Text style={{ color: colors.errorText, fontWeight: '700', fontSize: 13 }}>{errorMessage}</Text>
          </View>
        ) : null}

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 18, backgroundColor: colors.card, padding: 20, gap: 14 }} data-testid="blog-detail-content-panel" testID="blog-detail-content-panel">
          <Text style={{ color: colors.text, fontSize: 34, fontWeight: '900', lineHeight: 40 }} data-testid="blog-detail-title" testID="blog-detail-title">
            {detail.title}
          </Text>

          {visibleBlocks.map((block, index) => {
            const isHeading = block.type === 'heading';
            const isQuote = block.type === 'quote';
            return (
              <Text
                key={`${index}-${block.type}`}
                data-testid={`blog-detail-block-${index}`}
                testID={`blog-detail-block-${index}`}
                style={{
                  color: isHeading ? colors.text : isQuote ? colors.textSecondary : colors.text,
                  fontSize: isHeading ? 24 : 16,
                  lineHeight: isHeading ? 30 : 27,
                  fontWeight: isHeading ? '800' : isQuote ? '600' : '500',
                  fontStyle: isQuote ? 'italic' : 'normal',
                }}
              >
                {block.text}
              </Text>
            );
          })}

          {detail.premium_gate?.required && !detail.premium_gate.unlocked ? (
            <View style={{ borderWidth: 1, borderColor: colors.warning, backgroundColor: colors.warningSoft, borderRadius: 14, padding: 14, gap: 8 }} data-testid="blog-detail-premium-gate" testID="blog-detail-premium-gate">
              <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 14 }}>Member-only deep insights are locked</Text>
              {(detail.premium_preview || []).map((item, idx) => (
                <View key={`${item.heading}-${idx}`}>
                  <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '700' }} data-testid={`blog-detail-premium-preview-heading-${idx}`} testID={`blog-detail-premium-preview-heading-${idx}`}>
                    {item.heading}
                  </Text>
                  <Text style={{ color: colors.warningText, fontSize: 13, marginTop: 2 }} data-testid={`blog-detail-premium-preview-content-${idx}`} testID={`blog-detail-premium-preview-content-${idx}`}>
                    {item.content}
                  </Text>
                </View>
              ))}
              <TouchableOpacity
                data-testid="blog-detail-premium-upgrade-button"
                testID="blog-detail-premium-upgrade-button"
                onPress={() => router.push('/pricing')}
                style={{ marginTop: 4, alignSelf: 'flex-start', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.primary }}
              >
                <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>Unlock Member Insights</Text>
              </TouchableOpacity>
              <TouchableOpacity
                data-testid="blog-detail-token-unlock-button"
                testID="blog-detail-token-unlock-button"
                onPress={onUnlockPremiumInsight}
                disabled={unlockBusy}
                style={{ marginTop: 2, alignSelf: 'flex-start', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.warning }}
              >
                <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 12 }}>
                  {unlockBusy ? 'Unlocking…' : 'Unlock this premium insight (1 token)'}
                </Text>
              </TouchableOpacity>
              {unlockTokens !== null ? (
                <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '700' }} data-testid="blog-detail-token-balance" testID="blog-detail-token-balance">
                  Remaining unlock tokens: {unlockTokens}
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, gap: 8 }} data-testid="blog-detail-share-channels" testID="blog-detail-share-channels">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 13 }}>Share this article</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {SHARE_CHANNELS.map((channel) => (
                <TouchableOpacity
                  key={channel.key}
                  data-testid={`blog-detail-share-channel-${channel.key}`}
                  testID={`blog-detail-share-channel-${channel.key}`}
                  onPress={() => onShareDetailByChannel(channel.key)}
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
                  }}
                >
                  <Ionicons name={channel.icon as any} size={12} color={colors.textMuted} />
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{channel.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {detail.premium_gate?.required && detail.premium_gate.unlocked && detail.premium_sections?.length ? (
            <View style={{ marginTop: 4, gap: 10 }} data-testid="blog-detail-premium-sections" testID="blog-detail-premium-sections">
              <BlogSectionTitle title="Deep Insights" subtitle="Member-exclusive implementation layer" testId="blog-detail-deep-insights-title" />
              {detail.premium_sections.map((section, idx) => (
                <View key={`${section.heading}-${idx}`} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.success, backgroundColor: colors.successSoft, padding: 12 }}>
                  <Text style={{ color: colors.successText, fontWeight: '800', fontSize: 14 }} data-testid={`blog-detail-premium-heading-${idx}`} testID={`blog-detail-premium-heading-${idx}`}>
                    {section.heading}
                  </Text>
                  <Text style={{ color: colors.successText, marginTop: 4, fontSize: 13, lineHeight: 20 }} data-testid={`blog-detail-premium-content-${idx}`} testID={`blog-detail-premium-content-${idx}`}>
                    {section.content}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        {aiSummary ? (
          <View style={{ marginTop: 16, borderWidth: 1, borderColor: colors.info, backgroundColor: colors.infoSoft, borderRadius: 14, padding: 14, gap: 8 }} data-testid="blog-detail-ai-summary-panel" testID="blog-detail-ai-summary-panel">
            <Text style={{ color: colors.infoText, fontSize: 16, fontWeight: '800' }} data-testid="blog-detail-ai-summary-title" testID="blog-detail-ai-summary-title">
              GPT-5.2 Summary
            </Text>
            <Text style={{ color: colors.infoText, fontSize: 14, lineHeight: 22 }} data-testid="blog-detail-ai-summary-text" testID="blog-detail-ai-summary-text">
              {aiSummary.summary}
            </Text>

            {(aiSummary.key_takeaways || []).length ? (
              <View>
                <Text style={{ color: colors.infoText, fontWeight: '800', fontSize: 13, marginBottom: 4 }}>Key Takeaways</Text>
                {aiSummary.key_takeaways.map((item, idx) => (
                  <Text key={`${item}-${idx}`} style={{ color: colors.infoText, fontSize: 13, lineHeight: 20 }} data-testid={`blog-detail-ai-takeaway-${idx}`} testID={`blog-detail-ai-takeaway-${idx}`}>
                    • {item}
                  </Text>
                ))}
              </View>
            ) : null}

            {(aiSummary.action_plan || []).length ? (
              <View>
                <Text style={{ color: colors.infoText, fontWeight: '800', fontSize: 13, marginBottom: 4 }}>Action Plan</Text>
                {aiSummary.action_plan.map((item, idx) => (
                  <Text key={`${item}-${idx}`} style={{ color: colors.infoText, fontSize: 13, lineHeight: 20 }} data-testid={`blog-detail-ai-action-${idx}`} testID={`blog-detail-ai-action-${idx}`}>
                    {idx + 1}. {item}
                  </Text>
                ))}
              </View>
            ) : null}

            {aiSummary.upgrade_required ? (
              <Text style={{ color: colors.infoText, fontWeight: '700', fontSize: 12 }} data-testid="blog-detail-ai-upgrade-note" testID="blog-detail-ai-upgrade-note">
                Upgrade for full AI depth, full takeaways, and extended implementation plans.
              </Text>
            ) : null}
          </View>
        ) : null}

        {detail.author ? (
          <View style={{ marginTop: 18, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="blog-detail-author-card" testID="blog-detail-author-card">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14 }}>About the author</Text>
            <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }} data-testid="blog-detail-author-name" testID="blog-detail-author-name">
              {detail.author.name}
            </Text>
            <Text style={{ color: colors.textSecondary, fontSize: 13 }} data-testid="blog-detail-author-role" testID="blog-detail-author-role">
              {detail.author.role}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 13, lineHeight: 20 }} data-testid="blog-detail-author-bio" testID="blog-detail-author-bio">
              {detail.author.bio}
            </Text>
            <TouchableOpacity
              data-testid="blog-detail-open-author-button"
              testID="blog-detail-open-author-button"
              onPress={() => router.push(`/blog/authors/${detail.author?.author_slug}`)}
              style={{ alignSelf: 'flex-start', borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: colors.surfaceHover }}
            >
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>View Author Profile</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={{ marginTop: 24 }}>
          <BlogSectionTitle title="Related reads" subtitle="Continue with aligned topics and implementation examples" testId="blog-detail-related-title" />
          <View style={{ gap: 12 }} data-testid="blog-detail-related-list" testID="blog-detail-related-list">
            {(detail.related_posts || []).map((row) => (
              <BlogPostCard key={row.post_id} post={row} onOpen={(nextSlug) => router.push(`/blog/${nextSlug}`)} />
            ))}
          </View>
        </View>
      </ScrollView>
    </PublicPageShell>
  );
}
