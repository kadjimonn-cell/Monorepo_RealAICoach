import React from 'react';
import { View, Text, TouchableOpacity, Image } from 'react-native';
import { useTheme } from '../../context/ThemeContext';
import { BlogAuthor } from '../../services/blogV2';

interface BlogAuthorPillProps {
  author: BlogAuthor;
  onOpen: (slug: string) => void;
}

export function BlogAuthorPill({ author, onOpen }: BlogAuthorPillProps) {
  const { colors } = useTheme();

  return (
    <TouchableOpacity
      data-testid={`blog-author-pill-${author.author_slug}`}
      testID={`blog-author-pill-${author.author_slug}`}
      onPress={() => onOpen(author.author_slug)}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
      }}
    >
      {author.avatar_url ? (
        <Image accessibilityLabel="Decorative image"
          source={{ uri: author.avatar_url }}
          style={{ width: 30, height: 30, borderRadius: 15 }}
          resizeMode="cover"
          accessibilityLabel={author.name}
        />
      ) : (
        <View style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: colors.primarySoft }} />
      )}
      <View>
        <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }} data-testid={`blog-author-pill-name-${author.author_slug}`} testID={`blog-author-pill-name-${author.author_slug}`}>
          {author.name}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 11 }}>{author.role}</Text>
      </View>
    </TouchableOpacity>
  );
}
