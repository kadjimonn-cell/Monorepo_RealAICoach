import React from 'react';
import { ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface TypeMeta {
  icon: string;
  color: string;
}

interface LibraryFilterPanelProps {
  C: any;
  colors: any;
  isMobile: boolean;
  tr: (k: string) => string;
  searchInput: string;
  setSearchInput: (value: string) => void;
  handleSearch: () => void;
  handleResetFilters: () => void;
  categories: string[];
  types: string[];
  catFilter: string;
  typeFilter: string;
  sortBy: 'recommended' | 'newest' | 'oldest';
  viewMode: 'all' | 'bookmarked';
  setCatFilter: (value: string) => void;
  setTypeFilter: (value: string) => void;
  setSortBy: (value: 'recommended' | 'newest' | 'oldest') => void;
  setViewMode: (value: 'all' | 'bookmarked') => void;
  setQuery: (value: string) => void;
  setPage: (value: number) => void;
  activeFiltersCount: number;
  page: number;
  totalPages: number;
  catColors: Record<string, string>;
  typeIcons: Record<string, TypeMeta>;
  toTitle: (v: string) => string;
  onLayoutY: (y: number) => void;
}

export const LibraryFilterPanel: React.FC<LibraryFilterPanelProps> = ({
  C,
  colors,
  isMobile,
  tr,
  searchInput,
  setSearchInput,
  handleSearch,
  handleResetFilters,
  categories,
  types,
  catFilter,
  typeFilter,
  sortBy,
  viewMode,
  setCatFilter,
  setTypeFilter,
  setSortBy,
  setViewMode,
  setQuery,
  setPage,
  activeFiltersCount,
  page,
  totalPages,
  catColors,
  typeIcons,
  toTitle,
  onLayoutY,
}) => {
  return (
    <View
      onLayout={(e) => onLayoutY(e.nativeEvent.layout.y)}
      style={{
        backgroundColor: C.card,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: C.border,
        padding: isMobile ? 12 : 16,
        marginBottom: 14,
        gap: 12,
      }}
      data-testid="content-library-search-filter-panel"
      testID="content-library-search-filter-panel"
    >
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
        <View
          style={{
            flex: 1,
            flexDirection: 'row',
            alignItems: 'center',
            backgroundColor: C.bgSoft,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: C.border,
            height: 46,
            paddingHorizontal: 12,
          }}
          data-testid="content-library-search"
          testID="content-library-search"
        >
          <Ionicons name="search" size={16} color={C.textMuted} />
          <TextInput
            style={{ flex: 1, marginLeft: 8, color: C.text, fontSize: 14 }}
            placeholder={tr('Search by title, category, or type')}
            placeholderTextColor={C.textMuted}
            value={searchInput}
            onChangeText={setSearchInput}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
            data-testid="content-library-search-input"
            testID="content-library-search-input"
          />
          {searchInput !== '' && (
            <TouchableOpacity
              accessibilityLabel={tr('Clear search')}
              onPress={() => {
                setSearchInput('');
                setQuery('');
                setPage(1);
              }}
              data-testid="content-library-search-clear"
              testID="content-library-search-clear"
              accessibilityRole="button"
            >
              <Ionicons name="close-circle" size={18} color={C.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity
            accessibilityLabel={tr('Search')}
            style={{
              height: 46,
              paddingHorizontal: 16,
              borderRadius: 12,
              backgroundColor: C.primary,
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'row',
              gap: 6,
            }}
            onPress={handleSearch}
            data-testid="content-library-search-btn"
            testID="content-library-search-btn"
            accessibilityRole="button"
          >
            <Ionicons name="search" size={15} color={colors.primaryText} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{tr('Apply')}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            accessibilityLabel={tr('Reset filters')}
            style={{
              height: 46,
              paddingHorizontal: 16,
              borderRadius: 12,
              backgroundColor: C.bgSoft,
              borderWidth: 1,
              borderColor: C.border,
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'row',
              gap: 6,
            }}
            onPress={handleResetFilters}
            data-testid="content-library-reset-filters-btn"
            testID="content-library-reset-filters-btn"
            accessibilityRole="button"
          >
            <Ionicons name="close" size={15} color={C.textMuted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.textMuted }}>{tr('Reset')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="content-library-mode-row" testID="content-library-mode-row">
        {(['all', 'bookmarked'] as const).map(mode => {
          const isActive = viewMode === mode;
          return (
            <TouchableOpacity
              accessibilityLabel={tr('Set view mode')}
              key={mode}
              style={{
                paddingHorizontal: 14,
                paddingVertical: 9,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: isActive ? C.primary : C.border,
                backgroundColor: isActive ? C.primary : C.bgSoft,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
              }}
              onPress={() => {
                setViewMode(mode);
                setPage(1);
              }}
              data-testid={`content-library-tab-${mode}`}
              testID={`content-library-tab-${mode}`}
              accessibilityRole="button"
            >
              <Ionicons
                name={mode === 'all' ? 'layers-outline' : 'bookmark-outline'}
                size={14}
                color={isActive ? colors.primaryText : C.textMuted}
              />
              <Text style={{ fontSize: 11, fontWeight: '700', color: isActive ? colors.primaryText : C.textMuted }}>
                {mode === 'all' ? tr('All Content') : tr('Bookmarked')}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={{ gap: 10 }} data-testid="content-library-filters" testID="content-library-filters">
        <View>
          <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 }}>{tr('Category')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingBottom: 4 }}>
            {['all', ...categories].map(cat => {
              const active = catFilter === cat;
              const color = catColors[cat] || C.primary;
              return (
                <TouchableOpacity
                  accessibilityLabel={tr('Filter by category')}
                  key={cat}
                  style={{
                    paddingHorizontal: 12,
                    paddingVertical: 7,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? color : C.border,
                    backgroundColor: active ? color : C.bgSoft,
                  }}
                  onPress={() => {
                    setCatFilter(cat);
                    setPage(1);
                  }}
                  data-testid={`content-filter-cat-${cat}`}
                  testID={`content-filter-cat-${cat}`}
                  accessibilityRole="button"
                >
                  <Text style={{ fontSize: 11, fontWeight: '700', color: active ? 'var(--app-primary-text)' : C.textMuted }}>
                    {cat === 'all' ? tr('All Categories') : toTitle(cat)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        <View>
          <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 }}>{tr('Type')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingBottom: 4 }}>
            {['all', ...types].map(typ => {
              const active = typeFilter === typ;
              const meta = typeIcons[typ] || { icon: 'ellipse', color: C.primary };
              return (
                <TouchableOpacity
                  accessibilityLabel={tr('Filter by type')}
                  key={typ}
                  style={{
                    paddingHorizontal: 12,
                    paddingVertical: 7,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? meta.color : C.border,
                    backgroundColor: active ? meta.color : C.bgSoft,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 5,
                  }}
                  onPress={() => {
                    setTypeFilter(typ);
                    setPage(1);
                  }}
                  data-testid={`content-filter-type-${typ}`}
                  testID={`content-filter-type-${typ}`}
                  accessibilityRole="button"
                >
                  {typ !== 'all' && <Ionicons name={meta.icon as any} size={12} color={active ? 'var(--app-primary-text)' : meta.color} />}
                  <Text style={{ fontSize: 11, fontWeight: '700', color: active ? 'var(--app-primary-text)' : C.textMuted }}>
                    {typ === 'all' ? tr('All Types') : toTitle(typ)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Sort')}</Text>
          <TouchableOpacity
            accessibilityLabel={tr('Sort content')}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: sortBy === 'recommended' ? colors.success : C.border,
              backgroundColor: sortBy === 'recommended' ? colors.success : C.bgSoft,
            }}
            onPress={() => {
              setSortBy('recommended');
              setPage(1);
            }}
            data-testid="content-sort-recommended"
            testID="content-sort-recommended"
            accessibilityRole="button"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: sortBy === 'recommended' ? 'var(--app-primary-text)' : C.textMuted }}>
              {tr('Recommended')}
            </Text>
          </TouchableOpacity>

          {(['newest', 'oldest'] as const).map(sort => {
            const active = sortBy === sort;
            return (
              <TouchableOpacity
                accessibilityLabel={tr('Sort content')}
                key={sort}
                style={{
                  paddingHorizontal: 12,
                  paddingVertical: 6,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: active ? colors.success : C.border,
                  backgroundColor: active ? colors.success : C.bgSoft,
                }}
                onPress={() => {
                  setSortBy(sort);
                  setPage(1);
                }}
                data-testid={`content-sort-${sort}`}
                testID={`content-sort-${sort}`}
                accessibilityRole="button"
              >
                <Text style={{ fontSize: 11, fontWeight: '700', color: active ? 'var(--app-primary-text)' : C.textMuted }}>
                  {sort === 'recommended' ? tr('Recommended') : sort === 'newest' ? tr('Newest') : tr('Oldest')}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="content-library-results-meta" testID="content-library-results-meta">
          {tr('Active filters')}: {activeFiltersCount} • {tr('Page')} {page} / {Math.max(totalPages, 1)}
        </Text>
        {activeFiltersCount > 0 && (
          <TouchableOpacity
            onPress={handleResetFilters}
            style={{ paddingVertical: 4, paddingHorizontal: 10, borderRadius: 999, backgroundColor: colors.warningSoft }}
            data-testid="content-library-clear-active-filters-btn"
            testID="content-library-clear-active-filters-btn"
            accessibilityRole="button"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.warningText }}>{tr('Clear active filters')}</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
};
