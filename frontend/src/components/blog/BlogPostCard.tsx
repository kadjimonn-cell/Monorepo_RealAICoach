import React from 'react';
import { View, Text, TouchableOpacity, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { BlogCard } from '../../services/blogV2';
import { useLanguage } from '../../i18n/LanguageContext';

interface BlogPostCardProps {
  post: BlogCard;
  onOpen: (slug: string) => void;
  onToggleBookmark?: (post: BlogCard) => void;
  compact?: boolean;
}

export function BlogPostCard({ post, onOpen, onToggleBookmark, compact = false }: BlogPostCardProps) {
  const { t } = useLanguage();
  const { colors } = useTheme();

  return (
    <TouchableOpacity
      data-testid={`blog-post-card-${post.slug}`}
      testID={`blog-post-card-${post.slug}`}
      onPress={() => onOpen(post.slug)}
      activeOpacity={0.9}
      style={{
        width: compact ? 300 : '100%',
        borderRadius: 18,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        overflow: 'hidden',
      }}
    >
      {post.cover_image ? (
        <Image accessibilityLabel="Decorative image"
          source={{ uri: post.cover_image }}
          style={{ width: '100%', height: compact ? 136 : 196 }}
          resizeMode="cover"
          accessibilityLabel={post.category}
        />
      ) : null}

      <View style={{ padding: 16, gap: 10 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: colors.primary, fontWeight: '800', fontSize: 11, textTransform: 'uppercase' }} data-testid={`blog-post-category-${post.slug}`} testID={`blog-post-category-${post.slug}`}>
            {post.category}
          </Text>
          <TouchableOpacity
            data-testid={`blog-post-bookmark-btn-${post.slug}`}
            testID={`blog-post-bookmark-btn-${post.slug}`}
            onPress={() => onToggleBookmark?.(post)}
            style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: post.bookmarked ? colors.primary : colors.surfaceHover }}
          >
            <Ionicons name={post.bookmarked ? 'bookmark' : 'bookmark-outline'} size={14} color={post.bookmarked ? colors.primaryText : colors.text} />
          </TouchableOpacity>
        </View>

        <Text style={{ color: colors.text, fontSize: compact ? 17 : 20, fontWeight: '800', lineHeight: compact ? 23 : 28 }} numberOfLines={2} data-testid={`blog-post-title-${post.slug}`} testID={`blog-post-title-${post.slug}`}>
          {post.title}
        </Text>

        <Text style={{ color: colors.textSecondary, fontSize: 14, lineHeight: 20 }} numberOfLines={compact ? 2 : 3} data-testid={`blog-post-excerpt-${post.slug}`} testID={`blog-post-excerpt-${post.slug}`}>
          {post.excerpt}
        </Text>

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid={`blog-post-meta-${post.slug}`} testID={`blog-post-meta-${post.slug}`}>
            {post.author_name} · {post.read_time_minutes}{t("autofix.precision12.min")}</Text>
          {post.premium_required ? (
            <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: post.premium_locked ? colors.warningSoft : colors.successSoft }}>
              <Text style={{ color: post.premium_locked ? colors.warningText : colors.successText, fontWeight: '700', fontSize: 10 }} data-testid={`blog-post-premium-chip-${post.slug}`} testID={`blog-post-premium-chip-${post.slug}`}>
                {post.premium_locked ? 'Member Content' : 'Unlocked'}
              </Text>
            </View>
          ) : null}
        </View>
      </View>
    </TouchableOpacity>
  );
}
