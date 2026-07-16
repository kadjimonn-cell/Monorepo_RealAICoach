import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import PublicPageShell from '../../../src/components/PublicPageLayout';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { BlogAuthorPayload, getBlogAuthor, parseBlogError } from '../../../src/services/blogV2';
import { BlogPostCard } from '../../../src/components/blog/BlogPostCard';

export default function BlogAuthorProfilePage() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.blog.index.probe');

  const [payload, setPayload] = useState<BlogAuthorPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  const authorSlug = String(slug || '').trim();

  const loadAuthor = useCallback(async () => {
    if (!authorSlug) return;
    setLoading(true);
    setErrorMessage('');
    try {
      const data = await getBlogAuthor(authorSlug);
      setPayload(data);
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Unable to load author profile');
    } finally {
      setLoading(false);
    }
  }, [authorSlug]);

  useEffect(() => {
    loadAuthor();
  }, [loadAuthor]);

  return (
    <PublicPageShell
      title={payload?.author?.name || 'Author'}
      subtitle={payload?.author?.role || 'Editorial Profile'}
      testID="blog-author-profile-page"
      data-testid="blog-author-profile-page"
    >
      {loading ? (
        <View style={{ paddingVertical: 32 }} data-testid="blog-author-loading" testID="blog-author-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : errorMessage || !payload ? (
        <View style={{ borderWidth: 1, borderColor: colors.error, borderRadius: 12, backgroundColor: colors.errorSoft, padding: 14 }} data-testid="blog-author-error" testID="blog-author-error">
          <Text style={{ color: colors.errorText, fontWeight: '700', fontSize: 13 }}>{errorMessage || 'Author profile unavailable'}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: 48 }} data-testid="blog-author-scroll" testID="blog-author-scroll">
          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.card, padding: 16, gap: 8, marginBottom: 16 }} data-testid="blog-author-summary-card" testID="blog-author-summary-card">
            <Text style={{ color: colors.text, fontWeight: '900', fontSize: 22 }} data-testid="blog-author-name" testID="blog-author-name">
              {payload.author.name}
            </Text>
            <Text style={{ color: colors.textSecondary, fontWeight: '700', fontSize: 13 }} data-testid="blog-author-role" testID="blog-author-role">
              {payload.author.role}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 14, lineHeight: 22 }} data-testid="blog-author-bio" testID="blog-author-bio">
              {payload.author.bio}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="blog-author-stats" testID="blog-author-stats">
              {payload.author.stats?.posts || 0} posts · {(payload.author.stats?.total_views || 0).toLocaleString()} views
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(payload.author.focus_areas || []).map((focus, index) => (
                <View key={`${focus}-${index}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 999, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 6 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }} data-testid={`blog-author-focus-${index}`} testID={`blog-author-focus-${index}`}>
                    {focus}
                  </Text>
                </View>
              ))}
            </View>
          </View>

          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 22, marginBottom: 12 }} data-testid="blog-author-posts-title" testID="blog-author-posts-title">
            Latest from {payload.author.name}
          </Text>

          <View style={{ gap: 12 }} data-testid="blog-author-posts-list" testID="blog-author-posts-list">
            {(payload.posts || []).map((post) => (
              <BlogPostCard key={post.post_id} post={post} onOpen={(nextSlug) => router.push(`/blog/${nextSlug}`)} />
            ))}
          </View>

          <TouchableOpacity
            data-testid="blog-author-back-button"
            testID="blog-author-back-button"
            onPress={() => router.push('/blog')}
            style={{ marginTop: 18, alignSelf: 'flex-start', borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 9 }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>Back to Blog Hub</Text>
          </TouchableOpacity>
        </ScrollView>
      )}
    </PublicPageShell>
  );
}
