import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { FadeSlideIn, LibrarySkeleton } from '../SkeletonLoaders';

interface ContentItem {
  url: string;
  title: string;
  type: string;
  category: string;
  added_date: string;
  source?: string;
  ai_categorized?: boolean;
  content?: string;
  score?: number;
  recency_rank?: number;
  affinity_rank?: number;
  bookmark_rank?: number;
  recommendation_reasons?: string[];
}

interface TypeMeta {
  icon: string;
  color: string;
}

interface LibraryContentGridProps {
  C: any;
  colors: any;
  tr: (k: string) => string;
  loading: boolean;
  items: ContentItem[];
  viewMode: 'all' | 'bookmarked';
  bookmarkedSet: Set<string>;
  columns: number;
  cardWidth: number;
  typeIcons: Record<string, TypeMeta>;
  catColors: Record<string, string>;
  formatDate: (iso: string) => string;
  handleToggleBookmark: (item: ContentItem) => void;
  handleOpenItem: (item: ContentItem) => void;
  handleShareItem: (item: ContentItem) => void;
  onRecommendationReasonPress: (item: ContentItem, reason: string) => void;
  onExplainRecommendation: (item: ContentItem) => void;
  toTitle: (v: string) => string;
  sortBy: 'recommended' | 'newest' | 'oldest';
  onLayoutY: (y: number) => void;
}

export const LibraryContentGrid: React.FC<LibraryContentGridProps> = ({
  C,
  colors,
  tr,
  loading,
  items,
  viewMode,
  bookmarkedSet,
  columns,
  cardWidth,
  typeIcons,
  catColors,
  formatDate,
  handleToggleBookmark,
  handleOpenItem,
  handleShareItem,
  onRecommendationReasonPress,
  onExplainRecommendation,
  toTitle,
  sortBy,
  onLayoutY,
}) => {
  return (
    <View onLayout={(e) => onLayoutY(e.nativeEvent.layout.y)}>
      {loading ? (
        <LibrarySkeleton />
      ) : items.length === 0 ? (
        <FadeSlideIn>
          <View
            style={{
              backgroundColor: C.card,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              paddingVertical: 44,
              alignItems: 'center',
              gap: 8,
            }}
            data-testid="content-library-empty"
            testID="content-library-empty"
          >
            <Ionicons name={viewMode === 'bookmarked' ? 'bookmark-outline' : 'search-outline'} size={34} color={C.textMuted} />
            <Text style={{ color: C.text, fontSize: 17, fontWeight: '800' }} data-testid="content-library-empty-title" testID="content-library-empty-title">
              {viewMode === 'bookmarked' ? tr('No bookmarks yet') : tr('No content found')}
            </Text>
            <Text style={{ color: C.textMuted, fontSize: 13 }} data-testid="content-library-empty-description" testID="content-library-empty-description">
              {viewMode === 'bookmarked'
                ? tr('Bookmark items to find them quickly in this enterprise view.')
                : tr('Try adjusting your filters or search criteria.')}
            </Text>
          </View>
        </FadeSlideIn>
      ) : (
        <FadeSlideIn>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between' }} data-testid="content-library-grid" testID="content-library-grid">
            {items.map((item, index) => {
              const isBookmarked = bookmarkedSet.has(item.url);
              const typeMeta = typeIcons[item.type] || { icon: 'document-text', color: C.primary };
              const categoryColor = catColors[item.category] || C.primary;
              const isGenerated = item.source === 'generated' || item.url.startsWith('generated:');

              return (
                <View
                  key={`${item.url}-${index}`}
                  style={{
                    width: cardWidth as any,
                    minWidth: columns === 1 ? '100%' : undefined,
                    backgroundColor: C.card,
                    borderRadius: 14,
                    borderWidth: 1,
                    borderColor: C.border,
                    padding: 14,
                    gap: 10,
                  }}
                  data-testid={`content-item-${index}`}
                  testID={`content-item-${index}`}
                >
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    <View
                      style={{
                        width: 38,
                        height: 38,
                        borderRadius: 10,
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: `${typeMeta.color}20`,
                      }}
                    >
                      <Ionicons name={typeMeta.icon as any} size={16} color={typeMeta.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, lineHeight: 20 }} numberOfLines={2} data-testid={`content-title-${index}`} testID={`content-title-${index}`}>
                        {item.title}
                      </Text>
                      <Text style={{ marginTop: 2, fontSize: 10, color: C.textMuted }} data-testid={`content-date-${index}`} testID={`content-date-${index}`}>
                        {formatDate(item.added_date)}
                      </Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => handleToggleBookmark(item)}
                      style={{ padding: 2 }}
                      data-testid={`content-bookmark-${index}`}
                      testID={`content-bookmark-${index}`}
                      accessibilityRole="button"
                      accessibilityLabel={isBookmarked ? tr('Remove bookmark') : tr('Add bookmark')}
                    >
                      <Ionicons name={isBookmarked ? 'bookmark' : 'bookmark-outline'} size={20} color={isBookmarked ? colors.warning : C.textMuted} />
                    </TouchableOpacity>
                  </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid={`content-tags-${index}`} testID={`content-tags-${index}`}>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: `${categoryColor}20` }}>
                      <Text style={{ fontSize: 9, fontWeight: '800', color: categoryColor }}>{toTitle(item.category)}</Text>
                    </View>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: `${typeMeta.color}20` }}>
                      <Text style={{ fontSize: 9, fontWeight: '800', color: typeMeta.color }}>{toTitle(item.type)}</Text>
                    </View>
                    {isGenerated && (
                      <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.infoSoft }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: colors.info }}>{tr('Saved')}</Text>
                      </View>
                    )}
                    {item.ai_categorized && (
                      <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.purpleSoft }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: colors.purpleText }}>{tr('AI tagged')}</Text>
                      </View>
                    )}
                  </View>

                  {sortBy === 'recommended' && (
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid={`content-recommendation-badges-${index}`} testID={`content-recommendation-badges-${index}`}>
                      <TouchableOpacity
                        onPress={() => onExplainRecommendation(item)}
                        style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.successSoft }}
                        data-testid={`content-recommendation-score-chip-${index}`}
                        testID={`content-recommendation-score-chip-${index}`}
                        accessibilityRole="button"
                      >
                        <Text style={{ fontSize: 9, fontWeight: '800', color: colors.successText }} data-testid={`content-recommendation-score-${index}`} testID={`content-recommendation-score-${index}`}>
                          {tr('Score')}: {Number(item.score || 0).toFixed(1)}
                        </Text>
                      </TouchableOpacity>

                      {!!(item.recommendation_reasons || []).length && (item.recommendation_reasons || []).map((reason) => (
                        <TouchableOpacity
                          key={`${item.url}-${reason}`}
                          onPress={() => onRecommendationReasonPress(item, reason)}
                          style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: colors.infoSoft }}
                          data-testid={`content-recommendation-reason-${reason}-${index}`}
                          testID={`content-recommendation-reason-${reason}-${index}`}
                          accessibilityRole="button"
                        >
                          <Text style={{ fontSize: 9, fontWeight: '800', color: colors.info }}>
                            {reason === 'fresh'
                              ? tr('Fresh')
                              : reason === 'matches_activity'
                                ? tr('Matches activity')
                                : reason === 'bookmarked'
                                  ? tr('Bookmarked signal')
                                  : reason === 'saved_generated'
                                    ? tr('Saved item')
                                    : tr('Recommended')}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  )}

                  {isGenerated && !!item.content && (
                    <Text style={{ fontSize: 12, color: C.textSec, lineHeight: 17 }} numberOfLines={3} data-testid={`content-preview-${index}`} testID={`content-preview-${index}`}>
                      {item.content}
                    </Text>
                  )}

                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity
                      accessibilityLabel={tr('Open item')}
                      style={{
                        flex: 1,
                        minHeight: 38,
                        borderRadius: 10,
                        backgroundColor: C.primary,
                        borderWidth: 1,
                        borderColor: C.primary,
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexDirection: 'row',
                        gap: 6,
                      }}
                      onPress={() => handleOpenItem(item)}
                      data-testid={`content-open-${index}`}
                      testID={`content-open-${index}`}
                      accessibilityRole="button"
                    >
                      <Ionicons name={isGenerated ? 'eye-outline' : 'open-outline'} size={13} color={colors.primaryText} />
                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{isGenerated ? tr('View') : tr('Open')}</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      accessibilityLabel={tr('Share item')}
                      style={{
                        flex: 1,
                        minHeight: 38,
                        borderRadius: 10,
                        backgroundColor: colors.primarySoft,
                        borderWidth: 1,
                        borderColor: colors.primarySoft,
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexDirection: 'row',
                        gap: 6,
                      }}
                      onPress={() => handleShareItem(item)}
                      data-testid={`content-share-${index}`}
                      testID={`content-share-${index}`}
                      accessibilityRole="button"
                    >
                      <Ionicons name="share-social-outline" size={13} color={colors.primary} />
                      <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tr('Share')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}
          </View>
        </FadeSlideIn>
      )}
    </View>
  );
};
