import React, { useCallback, useMemo, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import { getShadow } from '../../utils/themeShadows';
import type { WelcomeTestimonialEntry } from '../../content/welcomeTrustContent';
import { resolveVisitorCtaPath } from '../../utils/visitorCtaPolicy';
import { withAlpha } from '../../utils/colorAlpha';

interface WelcomeSocialProps {
  testimonials?: WelcomeTestimonialEntry[];
  activeSegment?: string;
  onActiveSegmentChange?: (segment: string) => void;
  onDecisionPathSignal?: (areaId: 'features' | 'pricing' | 'social-proof', weight?: number) => void;
}

const PAGE_SIZE = 6;

export function WelcomeSocial({ testimonials = [], activeSegment, onActiveSegmentChange, onDecisionPathSignal }: WelcomeSocialProps) {
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { t } = useLanguage();
  const ALL_FILTER_VALUE = '__all__';
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const [internalSegment, setInternalSegment] = useState(ALL_FILTER_VALUE);
  const [page, setPage] = useState(0);
  const [sortMode, setSortMode] = useState<'top-outcomes' | 'highest-rating'>('top-outcomes');
  const isCompactMobile = width < 560;
  const isTablet = width >= tokens.breakpoints.tablet && width < tokens.breakpoints.desktop;
  const useWideSocialLayout = width >= 1180;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const segments = useMemo(() => {
    const unique = Array.from(new Set(testimonials.map((item) => String(item.segment || 'General').trim()).filter(Boolean)));
    return [ALL_FILTER_VALUE, ...unique];
  }, [ALL_FILTER_VALUE, testimonials]);

  const resolvedSegment = useMemo(() => {
    if (activeSegment && segments.includes(activeSegment)) return activeSegment;
    return internalSegment;
  }, [activeSegment, internalSegment, segments]);

  const applySegment = (segment: string) => {
    onDecisionPathSignal?.('social-proof', 2);
    if (onActiveSegmentChange) onActiveSegmentChange(segment);
    else setInternalSegment(segment);
    setPage(0);
  };

  const filtered = useMemo(() => {
    const base = testimonials.filter((item) => resolvedSegment === ALL_FILTER_VALUE || item.segment === resolvedSegment);
    if (sortMode === 'highest-rating') {
      return [...base].sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0));
    }
    const extractOutcomeScore = (value: string) => {
      const match = String(value || '').match(/(\d+(?:\.\d+)?)\s*%/);
      if (match?.[1]) return Number(match[1]);
      const fallbackNumber = String(value || '').match(/\d+/);
      return fallbackNumber?.[0] ? Number(fallbackNumber[0]) : 0;
    };
    return [...base].sort((a, b) => extractOutcomeScore(b.outcome) - extractOutcomeScore(a.outcome));
  }, [ALL_FILTER_VALUE, resolvedSegment, sortMode, testimonials]);

  const localizeSegment = useCallback((segment: string) => {
    if (segment === ALL_FILTER_VALUE) return tx('common.all', 'All');
    return tx(`welcome.social.segment.${segment.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, segment);
  }, [ALL_FILTER_VALUE, tx]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const activePage = Math.min(page, totalPages - 1);
  const visible = useMemo(() => filtered.slice(activePage * PAGE_SIZE, activePage * PAGE_SIZE + PAGE_SIZE), [activePage, filtered]);
  const featured = filtered[0] || testimonials[0] || null;
  const trustCompanies = useMemo(() => Array.from(new Set(testimonials.map((item) => String(item.company || '').trim()).filter(Boolean))).slice(0, 8), [testimonials]);
  const trustStats = useMemo(() => ([
    { id: 'proof', label: tx('welcome.social.trust.proofStories', 'Proof stories'), value: String(testimonials.length || 10) },
    { id: 'segments', label: tx('welcome.social.trust.segments', 'Functional lenses'), value: String(Math.max(segments.length - 1, 6)) },
    { id: 'impact', label: tx('welcome.social.trust.impact', 'Visible outcomes'), value: tx('welcome.social.trust.impactValue', '24–47%') },
  ]), [segments.length, testimonials.length, tx]);

  const s = useMemo(() => makeStyles(colors, darkMode, isDesktop, isTablet, isCompactMobile, padding, tokens, width), [colors, darkMode, isCompactMobile, isDesktop, isTablet, padding, tokens, width]);

  return (
    <View style={s.wrap} data-testid="welcome-social" testID="welcome-social">
      {Platform.OS === 'web' ? (
        <style dangerouslySetInnerHTML={{ __html: `
          .welcome-social-grid-web {
            display: grid;
            grid-template-columns: ${useWideSocialLayout ? '1.05fr 0.95fr' : 'minmax(0, 1fr)'};
            gap: 16px;
            width: 100%;
          }
          .welcome-social-card-grid-web {
            display: grid;
            grid-template-columns: ${isDesktop ? 'repeat(2, minmax(0, 1fr))' : isTablet ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)'};
            gap: 12px;
            width: 100%;
          }
        ` }} />
      ) : null}

      <View style={s.headerCard} data-testid="welcome-social-header-card" testID="welcome-social-header-card">
        <Text style={s.label} data-testid="welcome-testimonials-label" testID="welcome-testimonials-label">{tx('welcome.social.commandLabel', 'Enterprise trust engine')}</Text>
        <Text style={s.title} data-testid="welcome-testimonials-title" testID="welcome-testimonials-title">{tx('welcome.social.commandTitle', 'Give buyers the proof, signals, and outcomes that make upgrade decisions easier.')}</Text>
        <Text style={s.subtitle} data-testid="welcome-testimonials-subtitle" testID="welcome-testimonials-subtitle">{tx('welcome.social.commandSubtitle', 'See who trusts the platform, what changed for them, and which team lens matches your own operating context.')}</Text>

        <View style={s.statsRow} data-testid="welcome-social-trust-stats" testID="welcome-social-trust-stats">
          {trustStats.map((item) => (
            <View key={item.id} style={s.statCard} data-testid={`welcome-social-trust-stat-${item.id}`} testID={`welcome-social-trust-stat-${item.id}`}>
              <Text style={s.statLabel}>{item.label}</Text>
              <Text style={s.statValue}>{item.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={s.logoStrip} data-testid="welcome-social-logo-strip" testID="welcome-social-logo-strip">
        {trustCompanies.map((company, idx) => (
          <View key={`${company}-${idx}`} style={s.logoChip} data-testid={`welcome-social-logo-chip-${idx}`} testID={`welcome-social-logo-chip-${idx}`}>
            <Text style={s.logoChipText}>{company}</Text>
          </View>
        ))}
      </View>

      <View style={s.controlsCard} data-testid="welcome-social-controls-card" testID="welcome-social-controls-card">
        <View style={s.segmentRow} data-testid="welcome-testimonials-segment-chips" testID="welcome-testimonials-segment-chips">
          {segments.map((segment, idx) => {
            const active = segment === resolvedSegment;
            return (
              <TouchableOpacity key={`${segment}-${idx}`} onPress={() => applySegment(segment)} style={[s.segmentChip, active ? s.segmentChipActive : null]} data-testid={`welcome-testimonials-segment-chip-${idx}`} testID={`welcome-testimonials-segment-chip-${idx}`}>
                <Text style={[s.segmentChipText, active ? s.segmentChipTextActive : null]}>{localizeSegment(segment)}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={s.sortRow} data-testid="welcome-testimonials-sort-toggle" testID="welcome-testimonials-sort-toggle">
          <TouchableOpacity onPress={() => { onDecisionPathSignal?.('social-proof', 1); setSortMode('top-outcomes'); }} style={[s.sortChip, sortMode === 'top-outcomes' ? s.sortChipActive : null]} data-testid="welcome-testimonials-sort-top-outcomes" testID="welcome-testimonials-sort-top-outcomes">
            <Text style={[s.sortChipText, sortMode === 'top-outcomes' ? s.sortChipTextActive : null]}>{tx('welcome.social.sort.topOutcomes', 'Top outcomes')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { onDecisionPathSignal?.('social-proof', 1); setSortMode('highest-rating'); }} style={[s.sortChip, sortMode === 'highest-rating' ? s.sortChipActive : null]} data-testid="welcome-testimonials-sort-highest-rating" testID="welcome-testimonials-sort-highest-rating">
            <Text style={[s.sortChipText, sortMode === 'highest-rating' ? s.sortChipTextActive : null]}>{tx('welcome.social.sort.highestRating', 'Highest rating')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {Platform.OS === 'web' ? (
        <div className="welcome-social-grid-web">
          <View style={s.featuredCard} data-testid="welcome-social-featured-card" testID="welcome-social-featured-card">
            {featured ? <FeaturedTrustCard featured={featured} colors={colors} tx={tx} isCompactMobile={isCompactMobile} /> : null}
          </View>
          <div className="welcome-social-card-grid-web" data-testid="welcome-testimonials-grid">
            {visible.map((item, idx) => (
              <div key={`${item.name}-${idx}`}>
                <TrustMiniCard item={item} idx={idx} colors={colors} tx={tx} isCompactMobile={isCompactMobile} />
              </div>
            ))}
            {visible.length === 0 ? (
              <div>
                <View style={s.miniCard} data-testid="welcome-testimonials-empty" testID="welcome-testimonials-empty"><Text style={s.emptyText}>{tx('welcome.social.noTestimonials', 'No testimonials available right now.')}</Text></View>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <View style={s.stackWrap}>
          <View style={s.featuredCard} data-testid="welcome-social-featured-card" testID="welcome-social-featured-card">{featured ? <FeaturedTrustCard featured={featured} colors={colors} tx={tx} isCompactMobile={isCompactMobile} /> : null}</View>
          <View style={s.cardGrid} data-testid="welcome-testimonials-grid" testID="welcome-testimonials-grid">
            {visible.map((item, idx) => <TrustMiniCard key={`${item.name}-${idx}`} item={item} idx={idx} colors={colors} tx={tx} isCompactMobile={isCompactMobile} />)}
            {visible.length === 0 ? <View style={s.miniCard} data-testid="welcome-testimonials-empty" testID="welcome-testimonials-empty"><Text style={s.emptyText}>{tx('welcome.social.noTestimonials', 'No testimonials available right now.')}</Text></View> : null}
          </View>
        </View>
      )}

      <View style={s.footer} data-testid="welcome-testimonials-footer" testID="welcome-testimonials-footer">
        <Text style={s.footerMeta} data-testid="welcome-testimonials-results-count" testID="welcome-testimonials-results-count">
          {tx('welcome.social.resultsCount', 'Showing {shown} of {total} testimonials').replace('{shown}', String(visible.length)).replace('{total}', String(filtered.length))}
        </Text>

        <View style={s.footerActions}>
          <View style={s.paginationRow}>
            <TouchableOpacity onPress={() => { onDecisionPathSignal?.('social-proof', 1); setPage((prev) => Math.max(0, prev - 1)); }} disabled={activePage <= 0} style={[s.paginationButton, activePage <= 0 ? s.paginationButtonDisabled : null]} data-testid="welcome-testimonials-prev-button" testID="welcome-testimonials-prev-button"><Text style={s.paginationButtonText}>{tx('welcome.social.previous', 'Previous')}</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => { onDecisionPathSignal?.('social-proof', 1); setPage((prev) => Math.min(totalPages - 1, prev + 1)); }} disabled={activePage >= totalPages - 1} style={[s.paginationButton, activePage >= totalPages - 1 ? s.paginationButtonDisabled : null]} data-testid="welcome-testimonials-next-button" testID="welcome-testimonials-next-button"><Text style={s.paginationButtonText}>{tx('welcome.social.next', 'Next')}</Text></TouchableOpacity>
          </View>

          <View style={s.ctaRow}>
            <TouchableOpacity accessibilityLabel={tx('welcome.social.accessibility.startTrial', 'Start free trial from testimonials')}
              onPress={() => {
                onDecisionPathSignal?.('social-proof', 2);
                const target = resolveVisitorCtaPath('/auth/register', { isAuthenticated: Boolean(user), surface: 'welcome', fallbackPath: '/welcome' });
                router.push(target as any);
              }}
              style={s.primaryCta}
              data-testid="welcome-testimonials-start-trial-button"
              testID="welcome-testimonials-start-trial-button"
            >
              <Text style={s.primaryCtaText}>{tx('welcome.social.startTrial', 'Start free trial')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel={tx('welcome.social.accessibility.explorePlatform', 'Explore platform from testimonials')}
              onPress={() => {
                onDecisionPathSignal?.('social-proof', 2);
                const target = resolveVisitorCtaPath('/auth/login', { isAuthenticated: Boolean(user), surface: 'welcome', fallbackPath: '/welcome' });
                router.push(target as any);
              }}
              style={s.secondaryCta}
              data-testid="welcome-testimonials-explore-platform-button"
              testID="welcome-testimonials-explore-platform-button"
            >
              <Text style={s.secondaryCtaText}>{tx('welcome.social.explorePlatform', 'Explore platform')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </View>
  );
}

function FeaturedTrustCard({ featured, colors, tx, isCompactMobile }: { featured: WelcomeTestimonialEntry; colors: any; tx: (key: string, fallback: string) => string; isCompactMobile: boolean }) {
  const initials = featured.name.split(' ').map((token) => token[0]).join('').slice(0, 2).toUpperCase();
  return (
    <View style={{ gap: 14 }}>
      <View style={{ flexDirection: isCompactMobile ? 'column' : 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <View style={{ flexDirection: isCompactMobile ? 'column' : 'row', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
          <View style={{ width: 46, height: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: withAlpha(colors.primary, '18'), borderWidth: 1, borderColor: withAlpha(colors.primary, '30') }}>
            <Text style={{ color: colors.primary, fontWeight: '800', fontSize: 14 }}>{initials}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0, alignItems: isCompactMobile ? 'center' : 'flex-start' }}>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800', textAlign: isCompactMobile ? 'center' : 'left' }}>{featured.name}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, textAlign: isCompactMobile ? 'center' : 'left' }}>{featured.role} • {featured.company}</Text>
          </View>
        </View>
        <View style={{ borderRadius: 999, borderWidth: 1, borderColor: withAlpha(colors.warningText, '38'), backgroundColor: withAlpha(colors.warningText, '12'), paddingHorizontal: 10, paddingVertical: 6 }}>
          <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{featured.segment}</Text>
        </View>
      </View>

      <Text style={{ color: colors.text, fontSize: 23, lineHeight: 31, fontWeight: '900', letterSpacing: -0.5, textAlign: isCompactMobile ? 'center' : 'left' }} data-testid="welcome-social-featured-quote" testID="welcome-social-featured-quote">“{featured.quote}”</Text>
      <Text style={{ color: colors.textSec, fontSize: 14, lineHeight: 22, textAlign: isCompactMobile ? 'center' : 'left' }}>{tx('welcome.social.featuredNarrative', 'This is the kind of proof that reduces buying risk and makes internal alignment easier for real teams.')}</Text>

      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.bgSoft, 'D8'), padding: 14, gap: 6, alignItems: isCompactMobile ? 'center' : 'flex-start' }} data-testid="welcome-social-featured-outcome" testID="welcome-social-featured-outcome">
        <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, textAlign: isCompactMobile ? 'center' : 'left' }}>{tx('welcome.social.outcomeLabel', 'Outcome')}</Text>
        <Text style={{ color: colors.text, fontSize: 14, lineHeight: 21, fontWeight: '700', textAlign: isCompactMobile ? 'center' : 'left' }}>{featured.outcome}</Text>
      </View>
    </View>
  );
}

function TrustMiniCard({ item, idx, colors, tx, isCompactMobile }: { item: WelcomeTestimonialEntry; idx: number; colors: any; tx: (key: string, fallback: string) => string; isCompactMobile: boolean }) {
  return (
    <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.surface, 'F2'), padding: 14, gap: 10, minWidth: 0, alignItems: isCompactMobile ? 'center' : 'stretch', ...getShadow('sm', false) }} data-testid={`welcome-testimonial-${idx}`} testID={`welcome-testimonial-${idx}`}>
      <View style={{ flexDirection: isCompactMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
        <View style={{ flex: 1, minWidth: 0, alignItems: isCompactMobile ? 'center' : 'flex-start' }}>
          <Text numberOfLines={1} style={{ color: colors.text, fontSize: 13, fontWeight: '800', textAlign: isCompactMobile ? 'center' : 'left' }}>{item.name}</Text>
          <Text numberOfLines={2} style={{ color: colors.textMuted, fontSize: 11, lineHeight: 17, textAlign: isCompactMobile ? 'center' : 'left' }}>{item.role} • {item.company}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 2, flexShrink: 0 }}>
          {Array.from({ length: item.rating }).map((_, starIdx) => <Ionicons key={starIdx} name="star" size={11} color={colors.warningText} />)}
        </View>
      </View>
      <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 19, textAlign: isCompactMobile ? 'center' : 'left' }} data-testid={`welcome-testimonial-quote-${idx}`} testID={`welcome-testimonial-quote-${idx}`}>“{item.quote}”</Text>
      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8, alignItems: isCompactMobile ? 'center' : 'flex-start', width: '100%' }} data-testid={`welcome-testimonial-outcome-${idx}`} testID={`welcome-testimonial-outcome-${idx}`}>
        <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', textAlign: isCompactMobile ? 'center' : 'left' }}>{tx('welcome.social.outcomeLabel', 'Outcome')}</Text>
        <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4, textAlign: isCompactMobile ? 'center' : 'left' }}>{item.outcome}</Text>
      </View>
    </View>
  );
}

function makeStyles(colors: any, darkMode: boolean, isDesktop: boolean, isTablet: boolean, isCompactMobile: boolean, padding: number, tokens: any, width: number) {
  const useWideSocialLayout = width >= 1180;
  return StyleSheet.create({
    wrap: { paddingHorizontal: padding, paddingTop: 20, paddingBottom: 78, maxWidth: tokens.maxWidth, width: '100%', alignSelf: 'center', gap: 14 },
    headerCard: { borderRadius: 22, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.card, darkMode ? 'F0' : 'FC'), padding: isDesktop ? 20 : 16, gap: 12, ...getShadow('sm', darkMode), alignItems: isCompactMobile ? 'center' : 'stretch' },
    label: { color: colors.warningText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.6, textAlign: isCompactMobile ? 'center' : 'left' },
    title: { color: colors.text, fontSize: isDesktop ? 32 : 25, lineHeight: isDesktop ? 38 : 31, fontWeight: '900', letterSpacing: -0.6, textAlign: isCompactMobile ? 'center' : 'left' },
    subtitle: { color: colors.textSec, fontSize: 14, lineHeight: 22, maxWidth: 760, textAlign: isCompactMobile ? 'center' : 'left' },
    statsRow: { flexDirection: isCompactMobile ? 'column' : 'row', gap: 10 },
    statCard: { flex: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.bgSoft, darkMode ? 'C3' : 'F5'), padding: 12, gap: 6, alignItems: isCompactMobile ? 'center' : 'flex-start' },
    statLabel: { color: colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, textAlign: isCompactMobile ? 'center' : 'left' },
    statValue: { color: colors.text, fontSize: 17, fontWeight: '900', textAlign: isCompactMobile ? 'center' : 'left' },
    logoStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.surface, darkMode ? 'EE' : 'F9'), padding: 14, alignItems: 'center', justifyContent: 'center' },
    logoChip: { borderRadius: 999, borderWidth: 1, borderColor: withAlpha(colors.border, 'C8'), backgroundColor: withAlpha(colors.bgSoft, darkMode ? 'AB' : 'EF'), paddingHorizontal: 12, paddingVertical: 8, opacity: 0.88 },
    logoChipText: { color: colors.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase' },
    controlsCard: { borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.surface, darkMode ? 'EA' : 'FB'), padding: 14, gap: 12, alignItems: isCompactMobile ? 'center' : 'stretch' },
    segmentRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: isCompactMobile ? 'center' : 'flex-start' },
    segmentChip: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 11, paddingVertical: 7 },
    segmentChipActive: { borderColor: colors.warningText, backgroundColor: withAlpha(colors.warningText, '12') },
    segmentChipText: { color: colors.textSec, fontSize: 11, fontWeight: '700' },
    segmentChipTextActive: { color: colors.warningText },
    sortRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: isCompactMobile ? 'center' : 'flex-start' },
    sortChip: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.card, darkMode ? 'D8' : 'F5'), paddingHorizontal: 10, paddingVertical: 7 },
    sortChipActive: { borderColor: colors.primary, backgroundColor: withAlpha(colors.primary, '14') },
    sortChipText: { color: colors.textSec, fontSize: 10, fontWeight: '800' },
    sortChipTextActive: { color: colors.primary },
    stackWrap: { gap: 16 },
    featuredCard: { borderRadius: 24, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.card, darkMode ? 'F0' : 'FD'), padding: isCompactMobile ? 18 : 22, ...getShadow('md', darkMode) },
    cardGrid: { gap: 12 },
    miniCard: { borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: withAlpha(colors.surface, 'F2'), padding: 14, ...getShadow('sm', darkMode) },
    emptyText: { color: colors.textSec, fontSize: 12 },
    footer: { flexDirection: useWideSocialLayout ? 'column' : 'column', justifyContent: 'center', alignItems: 'center', gap: 12 },
    footerMeta: { color: colors.textMuted, fontSize: 11 },
    footerActions: { gap: 10, alignItems: 'center', width: '100%' },
    paginationRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' },
    paginationButton: { borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, paddingHorizontal: 12, paddingVertical: 7 },
    paginationButtonDisabled: { opacity: 0.55 },
    paginationButtonText: { color: colors.textSec, fontSize: 11, fontWeight: '700' },
    ctaRow: { flexDirection: isCompactMobile ? 'column' : 'row', gap: 8, flexWrap: 'wrap', justifyContent: 'center', alignItems: isCompactMobile ? 'stretch' : 'center', width: '100%' },
    primaryCta: { borderRadius: 12, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, minWidth: isCompactMobile ? undefined : 160, width: isCompactMobile ? '100%' : undefined },
    primaryCtaText: { color: colors.primaryText, fontSize: 12, fontWeight: '800', textAlign: 'center' },
    secondaryCta: { borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 14, paddingVertical: 10, minWidth: isCompactMobile ? undefined : 160, width: isCompactMobile ? '100%' : undefined },
    secondaryCtaText: { color: colors.textSec, fontSize: 12, fontWeight: '800', textAlign: 'center' },
  });
}
