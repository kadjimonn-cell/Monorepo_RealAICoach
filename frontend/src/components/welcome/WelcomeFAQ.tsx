import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import { getShadow } from '../../utils/themeShadows';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { resolveVisitorCtaPath } from '../../utils/visitorCtaPolicy';

interface WelcomeFaqItem {
  question: string;
  answer: string;
  category?: string;
}

interface WelcomeFAQProps {
  faqItems?: WelcomeFaqItem[];
  activeCategory?: string;
  onActiveCategoryChange?: (category: string) => void;
  recommenderSegments?: string[];
  recommenderPlans?: string[];
}

const INITIAL_VISIBLE = 8;
const LOAD_MORE_STEP = 6;

export function WelcomeFAQ({
  faqItems = [],
  activeCategory,
  onActiveCategoryChange,
  recommenderSegments = [],
  recommenderPlans = ['Free', 'Basic', 'Premium', 'Enterprise'],
}: WelcomeFAQProps) {
  const router = useRouter();
  const { darkMode, colors } = useTheme();
  const { t } = useLanguage();
  const ALL_FILTER_VALUE = '__all__';
  const { user } = useAuth();
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const isCompactMobile = width < 560;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [query, setQuery] = useState('');
  const [internalCategory, setInternalCategory] = useState(ALL_FILTER_VALUE);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);
  const [openId, setOpenId] = useState<string | null>(faqItems[0]?.question || null);
  const [viewCounts, setViewCounts] = useState<Record<string, number>>({});
  const [selectedPlan, setSelectedPlan] = useState('Enterprise');
  const [selectedSegment, setSelectedSegment] = useState(ALL_FILTER_VALUE);
  const [topViewedTelemetry, setTopViewedTelemetry] = useState<{ question: string; views: number; category: string }[]>([]);
  const [openConfidenceTooltipId, setOpenConfidenceTooltipId] = useState<string | null>(null);
  const telemetryDebounceRef = useRef<Record<string, number>>({});

  const categories = useMemo(() => {
    const base = faqItems.map((item) => String(item.category || 'General').trim()).filter(Boolean);
    const unique = Array.from(new Set(base));
    return [ALL_FILTER_VALUE, ...unique];
  }, [ALL_FILTER_VALUE, faqItems]);

  const resolvedCategory = useMemo(() => {
    if (activeCategory && categories.includes(activeCategory)) {
      return activeCategory;
    }
    return internalCategory;
  }, [activeCategory, categories, internalCategory]);

  const applyCategory = (category: string) => {
    if (onActiveCategoryChange) {
      onActiveCategoryChange(category);
    } else {
      setInternalCategory(category);
    }
    setVisibleCount(INITIAL_VISIBLE);
  };

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return faqItems.filter((item) => {
      const category = String(item.category || 'General').trim() || 'General';
      const categoryMatch = resolvedCategory === ALL_FILTER_VALUE || category === resolvedCategory;
      const text = `${item.question} ${item.answer}`.toLowerCase();
      const queryMatch = !normalizedQuery || text.includes(normalizedQuery);
      return categoryMatch && queryMatch;
    });
  }, [ALL_FILTER_VALUE, faqItems, query, resolvedCategory]);

  const displayed = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);
  const hasMore = filtered.length > visibleCount;

  const telemetrySessionId = useMemo(() => {
    try {
      if (typeof window === 'undefined') return '';
      const existing = window.sessionStorage.getItem('welcome_faq_telemetry_session_id');
      if (existing) return existing;
      const generated = `wfq_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      window.sessionStorage.setItem('welcome_faq_telemetry_session_id', generated);
      return generated;
    } catch {
      return '';
    }
  }, [tx]);

  const localTopViewedItems = useMemo(() => {
    const ranked = [...faqItems]
      .map((item) => ({ item, views: Number(viewCounts[item.question] || 0) }))
      .sort((a, b) => b.views - a.views)
      .slice(0, 3)
      .filter((entry) => entry.views > 0)
      .map((entry) => entry.item);
    return ranked;
  }, [faqItems, viewCounts]);

  const topViewedItems = useMemo(() => {
    if (!topViewedTelemetry.length) return localTopViewedItems;
    const questionMap = new Map(faqItems.map((item) => [String(item.question || '').trim().toLowerCase(), item]));
    const hydrated = topViewedTelemetry
      .map((row) => questionMap.get(String(row.question || '').trim().toLowerCase()) || null)
      .filter(Boolean) as WelcomeFaqItem[];
    return hydrated.length ? hydrated.slice(0, 3) : localTopViewedItems;
  }, [faqItems, localTopViewedItems, topViewedTelemetry]);

  const refreshTopViewedTelemetry = useCallback(async () => {
    try {
      const response = await api.get('/gps/faq/telemetry/top?window_days=30&limit=6', { silentLoading: true });
      const rows = Array.isArray(response?.data?.top_faq) ? response.data.top_faq : [];
      setTopViewedTelemetry(
        rows.map((row: any) => ({
          question: String(row?.question || ''),
          views: Number(row?.views || 0),
          category: String(row?.category || tx('welcome.faq.defaultCategory', 'General')),
        })),
      );
    } catch {
      setTopViewedTelemetry([]);
    }
  }, []);

  useEffect(() => {
    void refreshTopViewedTelemetry();
  }, [refreshTopViewedTelemetry]);

  const recordFaqView = useCallback(
    async (item: WelcomeFaqItem) => {
      setViewCounts((prev) => ({ ...prev, [item.question]: Number(prev[item.question] || 0) + 1 }));
      try {
        const key = String(item.question || '').trim().toLowerCase();
        const nowMs = Date.now();
        if (!key) return;
        const lastSent = Number(telemetryDebounceRef.current[key] || 0);
        if (nowMs - lastSent < 5 * 60 * 1000) {
          return;
        }
        telemetryDebounceRef.current[key] = nowMs;

        await api.post(
          '/gps/faq/telemetry/view',
          {
            question: item.question,
            category: item.category || tx('welcome.faq.defaultCategory', 'General'),
            segment: selectedSegment,
            plan: selectedPlan,
            context: 'welcome_faq',
            session_id: telemetrySessionId || undefined,
          },
          { silentLoading: true },
        );
        void refreshTopViewedTelemetry();
      } catch {
        // keep local fallback ranking
      }
    },
    [refreshTopViewedTelemetry, selectedPlan, selectedSegment, telemetrySessionId, tx],
  );

  const aiRecommendedFaqs = useMemo(() => {
    const planCategoryHints: Record<string, string[]> = {
      free: ['Getting Started', 'Pricing', 'Adoption'],
      basic: ['Adoption', 'Integrations', 'Performance'],
      premium: ['Integrations', 'Performance', 'ROI', 'Security'],
      enterprise: ['Security', 'Compliance', 'ROI', 'Support'],
    };

    const segmentCategoryHints: Record<string, string[]> = {
      'L&D': ['Adoption', 'Support', 'Performance'],
      Executive: ['ROI', 'Performance', 'Roadmap'],
      Compliance: ['Compliance', 'Security', 'Support'],
      Engineering: ['Integrations', 'Performance', 'Security'],
      Revenue: ['Adoption', 'ROI', 'Performance'],
    };

    const hints = new Set<string>([
      ...(planCategoryHints[String(selectedPlan || '').toLowerCase()] || []),
      ...(segmentCategoryHints[selectedSegment] || []),
    ]);

    const scored = faqItems
      .map((faq) => {
        const category = String(faq.category || 'General');
        const base = hints.has(category) ? 3 : 0;
        const text = `${faq.question} ${faq.answer}`.toLowerCase();
        const planBonus = text.includes(String(selectedPlan || '').toLowerCase()) ? 1 : 0;
        const segmentBonus = selectedSegment !== ALL_FILTER_VALUE && text.includes(String(selectedSegment || '').toLowerCase()) ? 1 : 0;
        const score = base + planBonus + segmentBonus;
        const confidence = score >= 4
          ? tx('welcome.faq.confidence.high', 'High')
          : score >= 2
            ? tx('welcome.faq.confidence.medium', 'Medium')
            : tx('welcome.faq.confidence.low', 'Low');
        const reasons: string[] = [];
        if (base > 0) reasons.push(tx('welcome.faq.recommender.reason.plan', 'Aligned with {plan} priorities').replace('{plan}', selectedPlan));
        if (segmentBonus > 0 && selectedSegment !== ALL_FILTER_VALUE) reasons.push(tx('welcome.faq.recommender.reason.segment', 'Strong fit for {segment} teams').replace('{segment}', selectedSegment));
        if (planBonus > 0) reasons.push(tx('welcome.faq.recommender.reason.mentions', 'Mentions {plan} context').replace('{plan}', selectedPlan));
        return {
          faq,
          score,
          confidence,
          reason: reasons.length > 0 ? reasons.join(' • ') : tx('welcome.faq.recommender.reason.general', 'General high-value recommendation for your selected context'),
        };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 3);

    return scored;
  }, [ALL_FILTER_VALUE, faqItems, selectedPlan, selectedSegment, tx]);

  const localizeCategory = useCallback((category: string) => {
    if (category === ALL_FILTER_VALUE) return tx('common.all', 'All');
    return tx(`welcome.faq.category.${category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, category);
  }, [ALL_FILTER_VALUE, tx]);

  const localizeSegment = useCallback((segment: string) => {
    if (segment === ALL_FILTER_VALUE) return tx('common.all', 'All');
    return tx(`welcome.social.segment.${segment.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, segment);
  }, [ALL_FILTER_VALUE, tx]);

  const s = useMemo(
    () =>
      StyleSheet.create({
        wrap: {
          paddingHorizontal: padding,
          paddingTop: 14,
          paddingBottom: 78,
          width: '100%',
          maxWidth: tokens.maxWidth,
          alignSelf: 'center',
          gap: 14,
        },
        headerCard: {
          borderRadius: 16,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.card,
          padding: isDesktop ? 18 : 14,
          gap: 10,
          ...getShadow('sm', darkMode),
        },
        label: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.5 },
        title: { color: colors.text, fontSize: isDesktop ? 32 : 24, lineHeight: isDesktop ? 38 : 30, fontWeight: '900', letterSpacing: -0.6 },
        subtitle: { color: colors.textSec, fontSize: 13, lineHeight: 20 },
        recommenderCard: {
          borderRadius: 12,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.bg,
          padding: 10,
          gap: 8,
        },
        searchRow: {
          flexDirection: 'row',
          alignItems: 'center',
          borderRadius: 12,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.bg,
          paddingHorizontal: 10,
          paddingVertical: 8,
          gap: 8,
        },
        searchInput: { flex: 1, color: colors.text, fontSize: 13, paddingVertical: 0 },
        chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
        chip: {
          borderRadius: 999,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.bg,
          paddingHorizontal: 10,
          paddingVertical: 6,
        },
        chipActive: {
          borderColor: colors.primary,
          backgroundColor: (globalThis as any).__alphaColor(colors.primary, '16'),
        },
        list: { gap: 8 },
        item: {
          borderRadius: 14,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.surface,
          overflow: 'hidden',
          ...getShadow('sm', darkMode),
        },
        itemQ: {
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          paddingHorizontal: 14,
          paddingVertical: 13,
        },
        qText: { color: colors.text, fontSize: 13, lineHeight: 19, fontWeight: '700', flex: 1 },
        aWrap: { paddingHorizontal: 14, paddingBottom: 13, paddingTop: 2 },
        aText: { color: colors.textSec, fontSize: 12, lineHeight: 20 },
        footer: { flexDirection: isDesktop ? 'row' : 'column', alignItems: isDesktop ? 'center' : 'stretch', gap: 8, justifyContent: 'space-between' },
        ctaRow: {
          flexDirection: isCompactMobile ? 'column' : 'row',
          flexWrap: 'wrap',
          gap: 8,
          justifyContent: 'center',
          alignItems: isCompactMobile ? 'stretch' : 'center',
          width: '100%',
        },
        footerButtonBase: {
          borderRadius: 10,
          paddingHorizontal: 13,
          paddingVertical: 8,
          alignItems: 'center',
          justifyContent: 'center',
        },
        footerButtonSecondary: {
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.card,
        },
        footerButtonMuted: {
          backgroundColor: colors.bg,
        },
        footerButtonPrimary: {
          backgroundColor: colors.primary,
        },
        footerButtonCompactWidth: {
          width: isCompactMobile ? '100%' : undefined,
        },
        footerButtonText: {
          fontSize: 11,
          fontWeight: '800',
          textAlign: 'center',
        },
      }),
    [colors, darkMode, isCompactMobile, isDesktop, padding, tokens],
  );

  return (
    <View style={s.wrap} data-testid="welcome-faq" testID="welcome-faq">
      <View style={s.headerCard} data-testid="welcome-faq-header-card" testID="welcome-faq-header-card">
        <Text style={s.label} data-testid="welcome-faq-label" testID="welcome-faq-label">{tx('welcome.faq.enterpriseLabel', 'Enterprise FAQ intelligence')}</Text>
        <Text style={s.title} data-testid="welcome-faq-title" testID="welcome-faq-title">{tx('welcome.faq.enterpriseTitle', 'Get instant answers before your team commits.')}</Text>
        <Text style={s.subtitle} data-testid="welcome-faq-subtitle" testID="welcome-faq-subtitle">
          {tx('welcome.faq.enterpriseSubtitle', '20+ high-intent FAQ entries tailored for enterprise buyers, admins, and operational teams.')}
        </Text>

        <View style={s.recommenderCard} data-testid="welcome-faq-ai-recommender" testID="welcome-faq-ai-recommender">
          <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.2 }}>
            {tx('welcome.faq.recommender.kicker', 'AI-guided recommender')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="welcome-faq-ai-recommender-label" testID="welcome-faq-ai-recommender-label">
            {tx('welcome.faq.recommender.subtitle', 'You might ask next…')}
          </Text>

          <View style={s.chipRow}>
            {recommenderPlans.map((plan, idx) => {
              const active = selectedPlan === plan;
              return (
                <TouchableOpacity
                  key={`${plan}-${idx}`}
                  onPress={() => setSelectedPlan(plan)}
                  style={[s.chip, active && s.chipActive]}
                  data-testid={`welcome-faq-plan-chip-${idx}`}
                  testID={`welcome-faq-plan-chip-${idx}`}
                >
                  <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 10, fontWeight: '700' }}>{plan}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <View style={s.chipRow}>
            {[ALL_FILTER_VALUE, ...recommenderSegments].slice(0, 8).map((segment, idx) => {
              const active = selectedSegment === segment;
              return (
                <TouchableOpacity
                  key={`${segment}-${idx}`}
                  onPress={() => setSelectedSegment(segment)}
                  style={[s.chip, active && s.chipActive]}
                  data-testid={`welcome-faq-segment-chip-${idx}`}
                  testID={`welcome-faq-segment-chip-${idx}`}
                >
                  <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 10, fontWeight: '700' }}>{localizeSegment(segment)}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <View style={{ gap: 6 }} data-testid="welcome-faq-ai-recommendations" testID="welcome-faq-ai-recommendations">
            {aiRecommendedFaqs.map((entry, idx) => {
              const item = entry.faq;
              const id = item.question;
              return (
                <TouchableOpacity accessibilityLabel={tx('welcome.faq.accessibility.aiRecommendation', 'Open AI recommended FAQ')}
                  key={id}
                  onPress={() => {
                    const category = String(item.category || 'General');
                    applyCategory(category);
                    setOpenId(id);
                    void recordFaqView(item);
                  }}
                  style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8 }}
                  data-testid={`welcome-faq-ai-recommendation-${idx}`}
                  testID={`welcome-faq-ai-recommendation-${idx}`}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700', flex: 1 }}>{item.question}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '16'), paddingHorizontal: 7, paddingVertical: 3 }}
                        data-testid={`welcome-faq-ai-confidence-badge-${idx}`}
                        testID={`welcome-faq-ai-confidence-badge-${idx}`}
                      >
                        <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '800' }}>{entry.confidence}</Text>
                      </View>
                      <TouchableOpacity
                        onPress={() => setOpenConfidenceTooltipId(openConfidenceTooltipId === id ? null : id)}
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, width: 18, height: 18, alignItems: 'center', justifyContent: 'center' }}
                        data-testid={`welcome-faq-ai-confidence-info-${idx}`}
                        testID={`welcome-faq-ai-confidence-info-${idx}`}
                      >
                        <Ionicons name="information" size={10} color={colors.textMuted} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  {openConfidenceTooltipId === id ? (
                    <View
                      style={{ marginTop: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 8, paddingVertical: 6 }}
                      data-testid={`welcome-faq-ai-confidence-tooltip-${idx}`}
                      testID={`welcome-faq-ai-confidence-tooltip-${idx}`}
                    >
                      <Text style={{ color: colors.textSec, fontSize: 10, lineHeight: 15 }}>{entry.reason}</Text>
                    </View>
                  ) : null}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={s.searchRow} data-testid="welcome-faq-search-row" testID="welcome-faq-search-row">
          <Ionicons name="search" size={15} color={colors.textMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={tx('welcome.faq.searchPlaceholder', 'Search policies, pricing, security, adoption…')}
            placeholderTextColor={colors.textMuted}
            style={s.searchInput}
            data-testid="welcome-faq-search-input"
            testID="welcome-faq-search-input"
          />
        </View>

        <View style={s.chipRow} data-testid="welcome-faq-category-chips" testID="welcome-faq-category-chips">
          {categories.map((category, idx) => {
            const active = category === resolvedCategory;
            return (
              <TouchableOpacity accessibilityLabel={tx('welcome.faq.accessibility.categoryChip', 'Filter FAQ category')}
                key={`${category}-${idx}`}
                onPress={() => {
                  applyCategory(category);
                }}
                style={[s.chip, active && s.chipActive]}
                data-testid={`welcome-faq-category-chip-${idx}`}
                testID={`welcome-faq-category-chip-${idx}`}
              >
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{localizeCategory(category)}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {topViewedItems.length > 0 ? (
          <View style={{ gap: 6 }} data-testid="welcome-faq-most-viewed" testID="welcome-faq-most-viewed">
            <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('welcome.faq.mostViewed', 'Most viewed')}</Text>
            <View style={s.chipRow}>
              {topViewedItems.map((item, idx) => (
                <TouchableOpacity accessibilityLabel={tx('welcome.faq.accessibility.mostViewed', 'Open most viewed FAQ item')}
                  key={`${item.question}-${idx}`}
                  onPress={() => {
                    setOpenId(item.question);
                    const category = String(item.category || 'General');
                    applyCategory(category);
                  }}
                  style={[s.chip, s.chipActive]}
                  data-testid={`welcome-faq-most-viewed-item-${idx}`}
                  testID={`welcome-faq-most-viewed-item-${idx}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{item.question.slice(0, 42)}…</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ) : null}
      </View>

      <View style={s.list} data-testid="welcome-faq-list" testID="welcome-faq-list">
        {displayed.map((item, idx) => {
          const id = item.question;
          const isOpen = openId === id;
          return (
            <View key={id} style={s.item} data-testid={`welcome-faq-item-${idx}`} testID={`welcome-faq-item-${idx}`}>
              <TouchableOpacity
                onPress={() => setOpenId(isOpen ? null : id)}
                style={s.itemQ}
                data-testid={`welcome-faq-toggle-${idx}`}
                testID={`welcome-faq-toggle-${idx}`}
                onPressIn={() => {
                  void recordFaqView(item);
                }}
              >
                <Text style={s.qText}>{item.question}</Text>
                <Ionicons name={isOpen ? 'remove-circle-outline' : 'add-circle-outline'} size={18} color={isOpen ? colors.primary : colors.textMuted} />
              </TouchableOpacity>
              {isOpen ? (
                <View style={s.aWrap} data-testid={`welcome-faq-answer-${idx}`} testID={`welcome-faq-answer-${idx}`}>
                  <Text style={s.aText}>{item.answer}</Text>
                </View>
              ) : null}
            </View>
          );
        })}

        {filtered.length === 0 ? (
          <View style={s.item} data-testid="welcome-faq-empty" testID="welcome-faq-empty">
            <View style={s.itemQ}>
              <Text style={s.qText}>{t('welcome.faq.empty', 'No matching FAQ entries found.')}</Text>
            </View>
          </View>
        ) : null}
      </View>

      <View style={s.footer} data-testid="welcome-faq-footer" testID="welcome-faq-footer">
        <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="welcome-faq-results-count" testID="welcome-faq-results-count">
          {tx('welcome.faq.resultsCount', 'Showing {shown} of {total} entries')
            .replace('{shown}', String(Math.min(displayed.length, filtered.length)))
            .replace('{total}', String(filtered.length))}
        </Text>

        <View style={s.ctaRow}>
          {hasMore ? (
            <TouchableOpacity
              onPress={() => setVisibleCount((prev) => prev + LOAD_MORE_STEP)}
              style={[s.footerButtonBase, s.footerButtonSecondary, s.footerButtonMuted, s.footerButtonCompactWidth]}
              data-testid="welcome-faq-load-more-button"
              testID="welcome-faq-load-more-button"
            >
              <Text style={[s.footerButtonText, { color: colors.textSec, fontWeight: '700' }]}>{tx('welcome.faq.loadMore', 'Load more FAQ')}</Text>
            </TouchableOpacity>
          ) : null}

          <TouchableOpacity accessibilityLabel={tx('welcome.faq.accessibility.startTrial', 'Start free trial from FAQ')}
            onPress={() => {
              const target = resolveVisitorCtaPath('/auth/register', {
                isAuthenticated: Boolean(user),
                surface: 'welcome',
                fallbackPath: '/welcome',
              });
              router.push(target as any);
            }}
            style={[s.footerButtonBase, s.footerButtonPrimary, s.footerButtonCompactWidth]}
            data-testid="welcome-faq-start-trial-button"
            testID="welcome-faq-start-trial-button"
          >
            <Text style={[s.footerButtonText, { color: colors.primaryText }]}>{tx('welcome.faq.startTrial', 'Start free trial')}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel={tx('welcome.faq.accessibility.explorePlatform', 'Explore platform from FAQ')}
            onPress={() => {
              const target = resolveVisitorCtaPath('/auth/login', {
                isAuthenticated: Boolean(user),
                surface: 'welcome',
                fallbackPath: '/welcome',
              });
              router.push(target as any);
            }}
            style={[s.footerButtonBase, s.footerButtonSecondary, s.footerButtonCompactWidth]}
            data-testid="welcome-faq-explore-platform-button"
            testID="welcome-faq-explore-platform-button"
          >
            <Text style={[s.footerButtonText, { color: colors.textSec }]}>{tx('welcome.faq.explorePlatform', 'Explore platform')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}
