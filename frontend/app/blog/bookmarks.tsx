import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import PublicPageShell from '../../src/components/PublicPageLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import {
  addBlogBookmark,
  BlogCard,
  getBlogBookmarks,
  isUnauthorized,
  parseBlogError,
  removeBlogBookmark,
} from '../../src/services/blogV2';
import { BlogPostCard } from '../../src/components/blog/BlogPostCard';

export default function BlogBookmarksPage() {
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.blog.index.probe');

  const [items, setItems] = useState<BlogCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const loadBookmarks = useCallback(async () => {
    setLoading(true);
    setAuthRequired(false);
    setErrorMessage('');
    try {
      const payload = await getBlogBookmarks();
      setItems(payload.items || []);
    } catch (error: any) {
      if (isUnauthorized(error)) {
        setAuthRequired(true);
      } else {
        const parsed = parseBlogError(error);
        setErrorMessage(parsed.message || 'Unable to load bookmarks');
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBookmarks();
  }, [loadBookmarks]);

  const onToggleBookmark = useCallback(async (post: BlogCard) => {
    try {
      if (post.bookmarked) {
        await removeBlogBookmark(post.post_id);
        setItems((prev) => prev.filter((row) => row.post_id !== post.post_id));
      } else {
        await addBlogBookmark(post.post_id);
        setItems((prev) => prev.map((row) => (row.post_id === post.post_id ? { ...row, bookmarked: true } : row)));
      }
    } catch (error: any) {
      const parsed = parseBlogError(error);
      setErrorMessage(parsed.message || 'Bookmark update failed');
    }
  }, []);

  return (
    <PublicPageShell
      title="Bookmarks"
      subtitle="Your saved articles and premium reading queue"
      testID="blog-bookmarks-page"
      data-testid="blog-bookmarks-page"
    >
      {loading ? (
        <View style={{ paddingVertical: 32 }} data-testid="blog-bookmarks-loading" testID="blog-bookmarks-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : authRequired ? (
        <View style={{ borderWidth: 1, borderColor: colors.warning, borderRadius: 12, backgroundColor: colors.warningSoft, padding: 14 }} data-testid="blog-bookmarks-auth-required" testID="blog-bookmarks-auth-required">
          <Text style={{ color: colors.warningText, fontWeight: '700', fontSize: 13 }}>Sign in to access your saved bookmarks.</Text>
          <TouchableOpacity
            data-testid="blog-bookmarks-signin-button"
            testID="blog-bookmarks-signin-button"
            onPress={() => router.push('/login')}
            style={{ marginTop: 10, alignSelf: 'flex-start', backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>Go to Sign In</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: 56 }} data-testid="blog-bookmarks-scroll" testID="blog-bookmarks-scroll">
          {errorMessage ? (
            <View style={{ borderWidth: 1, borderColor: colors.error, borderRadius: 12, backgroundColor: colors.errorSoft, padding: 12, marginBottom: 12 }} data-testid="blog-bookmarks-error" testID="blog-bookmarks-error">
              <Text style={{ color: colors.errorText, fontWeight: '700', fontSize: 13 }}>{errorMessage}</Text>
            </View>
          ) : null}

          {items.length === 0 ? (
            <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="blog-bookmarks-empty" testID="blog-bookmarks-empty">
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 15 }}>No bookmarks yet</Text>
              <Text style={{ color: colors.textMuted, marginTop: 4 }}>Save posts from the blog to build your personal reading stack.</Text>
              <TouchableOpacity
                data-testid="blog-bookmarks-open-blog-button"
                testID="blog-bookmarks-open-blog-button"
                onPress={() => router.push('/blog')}
                style={{ marginTop: 10, alignSelf: 'flex-start', borderRadius: 10, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8 }}
              >
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>Open Blog Hub</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={{ gap: 12 }} data-testid="blog-bookmarks-list" testID="blog-bookmarks-list">
              {items.map((post) => (
                <BlogPostCard
                  key={post.post_id}
                  post={post}
                  onOpen={(slug) => router.push(`/blog/${slug}`)}
                  onToggleBookmark={onToggleBookmark}
                />
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </PublicPageShell>
  );
}
