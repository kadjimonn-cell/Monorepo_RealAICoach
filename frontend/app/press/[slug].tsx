import React, { useMemo } from 'react';
import { ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import PublicPageShell from '../../src/components/PublicPageLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { PRESS_ARTICLES, getPressArticleBySlug, listPressArticlesByCategory } from '../../src/content/pressArticles';

export function generateStaticParams() {
  return PRESS_ARTICLES.map((item) => ({ slug: item.slug }));
}

export default function PressArticleDetailPage() {
  const router = useRouter();
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const { width } = useWindowDimensions();
  const { colors: C } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.press.probe');

  const m = width < 640;
  const article = useMemo(() => getPressArticleBySlug(String(slug || '')), [slug]);
  const related = useMemo(() => {
    if (!article) return [];
    return listPressArticlesByCategory(article.category)
      .filter((item) => item.slug !== article.slug)
      .slice(0, 3);
  }, [article]);

  if (!article) {
    return (
      <PublicPageShell>
        <View style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.card, borderRadius: 14, padding: 18, gap: 10 }} data-testid="press-article-not-found" testID="press-article-not-found">
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '900' }}>Press story not found</Text>
          <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 20 }}>The newsroom story you requested is unavailable.</Text>
          <TouchableOpacity
            onPress={() => router.push('/press' as any)}
            style={{ alignSelf: 'flex-start', borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }}
            data-testid="press-article-back-to-newsroom"
            testID="press-article-back-to-newsroom"
          >
            <Ionicons name="arrow-back" size={14} color={C.primaryText} />
            <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>Back to newsroom</Text>
          </TouchableOpacity>
        </View>
      </PublicPageShell>
    );
  }

  return (
    <PublicPageShell>
      <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 50 }} data-testid="press-article-scroll" testID="press-article-scroll">
        <View style={{ borderRadius: 16, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 20, gap: 10 }} data-testid="press-article-hero" testID="press-article-hero">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }} data-testid="press-article-meta" testID="press-article-meta">
              {article.source} • {article.category}
            </Text>
            <TouchableOpacity
              onPress={() => router.push('/press' as any)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="press-article-back-button"
              testID="press-article-back-button"
            >
              <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>Back to newsroom</Text>
            </TouchableOpacity>
          </View>
          <Text style={{ color: C.text, fontSize: m ? 26 : 38, lineHeight: m ? 32 : 44, fontWeight: '900', letterSpacing: -0.8 }} data-testid="press-article-title" testID="press-article-title">
            {article.title}
          </Text>
          <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 22 }} data-testid="press-article-seo-description" testID="press-article-seo-description">
            {article.seo_description}
          </Text>
          <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700' }} data-testid="press-article-date" testID="press-article-date">
            Published {article.date_label}
          </Text>
        </View>

        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 18, gap: 9 }} data-testid="press-article-key-points" testID="press-article-key-points">
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Key points</Text>
          {article.key_points.map((point, idx) => (
            <View key={`${point}-${idx}`} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }} data-testid={`press-article-key-point-${idx}`} testID={`press-article-key-point-${idx}`}>
              <Ionicons name="checkmark-circle" size={16} color={C.primary} style={{ marginTop: 2 }} />
              <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 20, flex: 1 }}>{point}</Text>
            </View>
          ))}
        </View>

        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 18, gap: 10 }} data-testid="press-article-body" testID="press-article-body">
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Story</Text>
          {article.body.map((paragraph, idx) => (
            <Text key={`paragraph-${idx}`} style={{ color: C.textSec, fontSize: 14, lineHeight: 23 }} data-testid={`press-article-paragraph-${idx}`} testID={`press-article-paragraph-${idx}`}>
              {paragraph}
            </Text>
          ))}
        </View>

        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 18, gap: 10 }} data-testid="press-article-related" testID="press-article-related">
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Related stories</Text>
          {related.map((item, idx) => (
            <TouchableOpacity
              key={`${item.slug}-${idx}`}
              onPress={() => router.push(`/press/${item.slug}` as any)}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, padding: 10 }}
              data-testid={`press-article-related-item-${idx}`}
              testID={`press-article-related-item-${idx}`}
            >
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{item.title}</Text>
              <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 3 }}>{item.date_label} • {item.category}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </PublicPageShell>
  );
}
