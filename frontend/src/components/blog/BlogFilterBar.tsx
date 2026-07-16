import React from 'react';
import { View, TextInput, TouchableOpacity, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';

interface BlogFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  activeCategory: string;
  onCategoryChange: (value: string) => void;
  categories: string[];
}

export function BlogFilterBar({
  search,
  onSearchChange,
  onSearchSubmit,
  activeCategory,
  onCategoryChange,
  categories,
}: BlogFilterBarProps) {
  const { t } = useLanguage();
  const { colors } = useTheme();

  return (
    <View style={{ gap: 14 }} data-testid="blog-filter-bar" testID="blog-filter-bar">
      <View style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        borderRadius: 14,
        paddingHorizontal: 14,
        paddingVertical: 10,
      }}>
        <Ionicons name="search" size={16} color={colors.textMuted} />
        <TextInput accessibilityLabel="Search articles, tags, authors"
          data-testid="blog-search-input"
          testID="blog-search-input"
          value={search}
          onChangeText={onSearchChange}
          onSubmitEditing={onSearchSubmit}
          placeholder="Search articles, tags, authors"
          placeholderTextColor={colors.textMuted}
          style={{ flex: 1, color: colors.text, fontSize: 15 }}
        />
        <TouchableOpacity
          data-testid="blog-search-submit-button"
          testID="blog-search-submit-button"
          onPress={onSearchSubmit}
          style={{ backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 }}
        >
          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>{t("common.search")}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {categories.map((category) => {
          const active = activeCategory === category;
          return (
            <TouchableOpacity
              key={category}
              data-testid={`blog-category-chip-${category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              testID={`blog-category-chip-${category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              onPress={() => onCategoryChange(category)}
              style={{
                borderRadius: 999,
                paddingHorizontal: 12,
                paddingVertical: 8,
                backgroundColor: active ? colors.primary : colors.card,
                borderWidth: 1,
                borderColor: active ? colors.primary : colors.border,
              }}
            >
              <Text style={{ color: active ? colors.primaryText : colors.text, fontWeight: '700', fontSize: 12 }}>{category}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}
