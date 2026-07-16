import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, useWindowDimensions, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import PublicPageShell from '../src/components/PublicPageLayout';
import { StaticContentSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import {
  PRESS_CATEGORY_FILTERS,
  type PressCategory,
  listPressArticlesByCategory,
  getLatestMediaMentions,
} from '../src/content/pressArticles';

const FEATURED_COVERAGE = [
  { source: 'TechCrunch', headline: 'Top 10 AI Startups to Watch', angle: 'Category leadership in AI-guided professional growth.' },
  { source: 'Forbes', headline: 'Enterprise Coaching, Reimagined', angle: 'How global teams are scaling role-based coaching outcomes.' },
  { source: 'VentureBeat', headline: 'From Learning Content to Action', angle: 'Signal-driven nudges and measurable behavioral change.' },
];

const EXECUTIVE_SPOKESPEOPLE = [
  { name: 'Ava Reynolds', role: 'Chief Executive Officer', focus: 'Vision, market expansion, and enterprise strategy' },
  { name: 'Liam Ortega', role: 'Chief Product Officer', focus: 'AI coaching roadmap, product design, and responsible UX' },
  { name: 'Maya Singh', role: 'VP, Customer Outcomes', focus: 'Customer stories, adoption data, and ROI narratives' },
];

const PRODUCT_HIGHLIGHTS = [
  { label: 'AI Coaching Journeys', detail: 'Context-aware pathways that adapt to role, goal, and pace.' },
  { label: 'Enterprise Insights', detail: 'Team-level progression, risk signals, and coaching impact analytics.' },
  { label: 'Workflow Integrations', detail: 'Seamless adoption with practical nudges inside daily tools.' },
];

const MEDIA_ASSETS = [
  'Company boilerplate and fact sheet',
  'Executive bios and approved headshots',
  'Product UI screenshots and usage scenarios',
  'Logo package and visual identity guidance',
];

export default function PressPage() {
  const router = useRouter();
  const { t } = useTranslation();
  t('i18n.route.press.probe');
  const pageReady = usePageReady();
  const { width } = useWindowDimensions();
  const { colors: C } = useTheme();
  const m = width < 640;
  const gridTwo = width >= 900;
  const [activeFilter, setActiveFilter] = useState<'All' | PressCategory>('All');

  const filteredArticles = useMemo(() => listPressArticlesByCategory(activeFilter), [activeFilter]);
  const latestMentions = useMemo(() => getLatestMediaMentions(4), []);

  const openMail = async () => {
    try {
      await Linking.openURL('mailto:press@realaicoach.app?subject=Media%20Inquiry%20-%20RealAICoach');
    } catch {
      // no-op
    }
  };

  if (!pageReady) return <PublicPageShell><StaticContentSkeleton /></PublicPageShell>;
  return (
    <PublicPageShell>
      <View style={{ gap: 14 }} data-testid="press-page" testID="press-page">
        <View
          style={{
            borderRadius: 20,
            borderWidth: 1,
            borderColor: C.border,
            backgroundColor: C.card,
            padding: m ? 16 : 24,
            overflow: 'hidden',
            gap: 12,
          }}
          data-testid="press-hero"
          testID="press-hero"
        >
          <View style={{ position: 'absolute', right: -26, top: -28, width: 140, height: 140, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.primary, '18') }} />
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' }} data-testid="press-hero-badge" testID="press-hero-badge">
            Press & Media
          </Text>
          <Text style={{ color: C.text, fontSize: m ? 30 : 42, lineHeight: m ? 36 : 48, fontWeight: '900', letterSpacing: -0.8 }} data-testid="press-hero-title" testID="press-hero-title">
            RealAICoach newsroom for enterprise credibility.
          </Text>
          <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 22, maxWidth: 880 }} data-testid="press-hero-subtitle" testID="press-hero-subtitle">
            Company announcements, trusted coverage, executive narratives, and media resources to support interviews, investor briefings, and industry stories.
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {['857k+ active users', '140+ countries', 'Enterprise-ready platform'].map((fact, idx) => (
              <View key={fact} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 12, paddingVertical: 7 }} data-testid={`press-hero-fact-${idx}`} testID={`press-hero-fact-${idx}`}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{fact}</Text>
              </View>
            ))}
          </View>

          <View style={{ flexDirection: m ? 'column' : 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={openMail}
              style={{ borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 8, justifyContent: 'center' }}
              data-testid="press-contact-primary-button"
              testID="press-contact-primary-button"
            >
              <Ionicons name="mail-outline" size={15} color={C.primaryText} />
              <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>Contact Media Team</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => router.push('/press' as any)}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 8, justifyContent: 'center' }}
              data-testid="press-request-briefing-button"
              testID="press-request-briefing-button"
            >
              <Ionicons name="newspaper-outline" size={15} color={C.textSec} />
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>Browse Newsroom</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ gap: 10 }} data-testid="press-latest-mentions" testID="press-latest-mentions">
          <Text style={{ color: C.text, fontSize: 17, fontWeight: '800' }} data-testid="press-latest-mentions-title" testID="press-latest-mentions-title">Latest media mentions</Text>
          <View style={{ flexDirection: gridTwo ? 'row' : 'column', gap: 8, flexWrap: 'wrap' }}>
            {latestMentions.map((item, idx) => (
              <TouchableOpacity
                key={`${item.slug}-${idx}`}
                onPress={() => router.push(`/press/${item.slug}` as any)}
                style={{ flex: 1, minWidth: 220, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 11, gap: 5 }}
                data-testid={`press-latest-mention-card-${idx}`}
                testID={`press-latest-mention-card-${idx}`}
              >
                <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{item.source}</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', lineHeight: 19 }}>{item.title}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>{item.date_label} • {item.category}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={{ gap: 10 }} data-testid="press-featured-coverage" testID="press-featured-coverage">
          <Text style={{ color: C.text, fontSize: 19, fontWeight: '800' }} data-testid="press-featured-coverage-title" testID="press-featured-coverage-title">Featured coverage</Text>
          <View style={{ flexDirection: gridTwo ? 'row' : 'column', flexWrap: 'wrap', gap: 10 }}>
            {FEATURED_COVERAGE.map((item, idx) => (
              <View key={`${item.source}-${idx}`} style={{ flex: 1, minWidth: 230, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14, gap: 8 }} data-testid={`press-featured-coverage-card-${idx}`} testID={`press-featured-coverage-card-${idx}`}>
                <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{item.source}</Text>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '800', lineHeight: 22 }}>{item.headline}</Text>
                <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 19 }}>{item.angle}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ gap: 10 }} data-testid="press-releases-section" testID="press-releases-section">
          <Text style={{ color: C.text, fontSize: 19, fontWeight: '800' }} data-testid="press-releases-title" testID="press-releases-title">Press releases</Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="press-filter-row" testID="press-filter-row">
            {PRESS_CATEGORY_FILTERS.map((filter, idx) => {
              const active = activeFilter === filter;
              return (
                <TouchableOpacity
                  key={`${filter}-${idx}`}
                  onPress={() => setActiveFilter(filter)}
                  style={{
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '16') : C.bg,
                    paddingHorizontal: 12,
                    paddingVertical: 7,
                  }}
                  data-testid={`press-filter-${String(filter).toLowerCase()}`}
                  testID={`press-filter-${String(filter).toLowerCase()}`}
                >
                  <Text style={{ color: active ? C.primary : C.textSec, fontSize: 11, fontWeight: '800' }}>{filter}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <View style={{ gap: 10 }}>
            {filteredArticles.map((r, i) => (
              <TouchableOpacity
                key={r.slug}
                onPress={() => router.push(`/press/${r.slug}` as any)}
                style={{ backgroundColor: C.card, borderRadius: 14, padding: m ? 14 : 18, borderWidth: 1, borderColor: C.border }}
                data-testid={`press-release-${i}`}
                testID={`press-release-${i}`}
              >
                <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{r.date_label} • {r.category}</Text>
                <Text style={{ color: C.text, fontSize: m ? 16 : 18, fontWeight: '800', marginBottom: 7, lineHeight: m ? 23 : 26 }}>{r.title}</Text>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21 }}>{r.excerpt}</Text>
                <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', marginTop: 8 }}>Read full story</Text>
              </TouchableOpacity>
            ))}
            {filteredArticles.length === 0 ? (
              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, padding: 12 }} data-testid="press-filter-empty-state" testID="press-filter-empty-state">
                <Text style={{ color: C.textSec, fontSize: 12 }}>No stories in this category yet.</Text>
              </View>
            ) : null}
          </View>
        </View>

        <View style={{ flexDirection: gridTwo ? 'row' : 'column', gap: 10 }}>
          <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 18, gap: 10 }} data-testid="press-executive-section" testID="press-executive-section">
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="press-executive-title" testID="press-executive-title">Executive spokespeople</Text>
            {EXECUTIVE_SPOKESPEOPLE.map((p, idx) => (
              <View key={`${p.name}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, padding: 10 }} data-testid={`press-executive-card-${idx}`} testID={`press-executive-card-${idx}`}>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{p.name}</Text>
                <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', marginTop: 3 }}>{p.role}</Text>
                <Text style={{ color: C.textSec, fontSize: 11, marginTop: 4 }}>{p.focus}</Text>
              </View>
            ))}
          </View>

          <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: m ? 14 : 18, gap: 10 }} data-testid="press-product-highlights-section" testID="press-product-highlights-section">
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="press-product-highlights-title" testID="press-product-highlights-title">Product highlights for stories</Text>
            {PRODUCT_HIGHLIGHTS.map((item, idx) => (
              <View key={`${item.label}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, padding: 10 }} data-testid={`press-product-highlight-card-${idx}`} testID={`press-product-highlight-card-${idx}`}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{item.label}</Text>
                <Text style={{ color: C.textSec, fontSize: 11, marginTop: 4, lineHeight: 18 }}>{item.detail}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ backgroundColor: C.card, borderRadius: 16, padding: m ? 16 : 22, borderWidth: 1, borderColor: C.border, gap: 10 }} data-testid="press-media-kit-section" testID="press-media-kit-section">
          <Text style={{ color: C.text, fontSize: 17, fontWeight: '800' }} data-testid="press-media-kit-title" testID="press-media-kit-title">Media resources available on request</Text>
          <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21 }} data-testid="press-media-kit-subtitle" testID="press-media-kit-subtitle">
            We provide complete media packs tailored for editorial, analyst, and partner narratives. Request access to receive curated resources.
          </Text>
          <View style={{ gap: 7 }} data-testid="press-media-assets-list" testID="press-media-assets-list">
            {MEDIA_ASSETS.map((item, idx) => (
              <View key={`${item}-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`press-media-asset-item-${idx}`} testID={`press-media-asset-item-${idx}`}>
                <Ionicons name="checkmark-circle" size={16} color={C.primary} />
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{item}</Text>
              </View>
            ))}
          </View>
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="press-contact-email-row" testID="press-contact-email-row">
            <Ionicons name="mail" size={15} color={C.primary} />
            <Text style={{ color: C.textSec, fontSize: 12 }}>press@realaicoach.app · Typical response time: under 1 business day</Text>
          </View>
        </View>
      </View>
    </PublicPageShell>
  );
}