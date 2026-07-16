import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Animated, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { getShadow } from '../../utils/themeShadows';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import type { GLSTokens } from '../../context/GLSContext';
import { withAlpha } from '../../utils/colorAlpha';
import type { WelcomeDecisionPathAreaId } from './welcomeWorkflowMemory';
import { WELCOME_CENTERED_LAYOUT_BREAKPOINT, WELCOME_CENTERED_SECTION_MAX_WIDTH } from './welcomeSectionContract';

interface Props {
  onRegister: () => void;
  onLogin: () => void;
  onOpenAbout: () => void;
  decisionPath: {
    areaId: WelcomeDecisionPathAreaId;
    scores: Record<WelcomeDecisionPathAreaId, number>;
  } | null;
}

const cardBlur = Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {};

export function WelcomeCTA({ onRegister, onLogin, onOpenAbout, decisionPath }: Props) {
  const { width, isDesktop, isTablet, padding, tokens } = useGLSBreakpoint();
  const isCompactMobile = width < 560;
  const useWideCloseLayout = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT;
  const useBalancedDecisionGrid = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT;
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const s = useMemo(() => makeStyles(WC, isDark, padding, tokens, isDesktop, isTablet, isCompactMobile), [WC, isDark, padding, tokens, isDesktop, isTablet, isCompactMobile]);

  const decisionPathContent = useMemo(() => {
    if (!decisionPath) {
      return {
        areaId: 'features' as WelcomeDecisionPathAreaId,
        title: tx('welcome.summary.path.default.title', 'The strongest next move is to open a clean first workspace.'),
        copy: tx('welcome.summary.path.default.copy', 'If you are still evaluating the platform broadly, start free now and keep the rest of the Welcome journey available as your upgrade and review path.'),
        action: tx('welcome.summary.path.default.action', 'Open free workspace'),
        supportTitle: tx('welcome.summary.path.default.supportTitle', 'Need the strategic context first?'),
        supportCopy: tx('welcome.summary.path.default.supportCopy', 'Open the About story for the platform narrative, leadership context, and customer outcomes behind the product experience.'),
        supportAction: tx('welcome.summary.path.default.supportAction', 'Review About RealAICoach'),
      };
    }

    if (decisionPath.areaId === 'pricing') {
      return {
        areaId: 'pricing' as WelcomeDecisionPathAreaId,
        title: tx('welcome.summary.path.pricing.title', 'Your strongest signal suggests commercial clarity will move the decision forward fastest.'),
        copy: tx('welcome.summary.path.pricing.copy', 'Start free now to preserve pricing momentum, revisit the plan tradeoffs that mattered most, and continue into upgrade review without losing context.'),
        action: tx('welcome.summary.path.pricing.action', 'Open free workspace with pricing context'),
        supportTitle: tx('welcome.summary.path.pricing.supportTitle', 'Need stakeholder-ready material?'),
        supportCopy: tx('welcome.summary.path.pricing.supportCopy', 'Use the About page to equip stakeholders with the platform story, reliability posture, and customer outcome narrative behind the pricing decision.'),
        supportAction: tx('welcome.summary.path.pricing.supportAction', 'Review About proof pack'),
      };
    }

    if (decisionPath.areaId === 'social-proof') {
      return {
        areaId: 'social-proof' as WelcomeDecisionPathAreaId,
        title: tx('welcome.summary.path.social.title', 'Your strongest signal suggests trust validation is the final decision unlock.'),
        copy: tx('welcome.summary.path.social.copy', 'Open a free workspace while the customer outcomes are still fresh, then return to the proof trail with saved momentum instead of restarting the review.'),
        action: tx('welcome.summary.path.social.action', 'Open free workspace from proof'),
        supportTitle: tx('welcome.summary.path.social.supportTitle', 'Want the deeper company narrative?'),
        supportCopy: tx('welcome.summary.path.social.supportCopy', 'The About page gives you the leadership, milestones, and enterprise reliability context behind the proof stories you just reviewed.'),
        supportAction: tx('welcome.summary.path.social.supportAction', 'Review About story'),
      };
    }

    return {
      areaId: 'features' as WelcomeDecisionPathAreaId,
      title: tx('welcome.summary.path.features.title', 'Your strongest signal suggests workflow depth is the clearest route to value.'),
      copy: tx('welcome.summary.path.features.copy', 'Open a free workspace now so the capability path you explored becomes a saved activation path rather than a one-time visit.'),
      action: tx('welcome.summary.path.features.action', 'Open free workspace from capabilities'),
      supportTitle: tx('welcome.summary.path.features.supportTitle', 'Still validating the company behind the workflows?'),
      supportCopy: tx('welcome.summary.path.features.supportCopy', 'Visit the About page for the product story, leadership context, and operating posture behind the workflow depth you explored.'),
      supportAction: tx('welcome.summary.path.features.supportAction', 'Review About story'),
    };
  }, [decisionPath, tx]);

  const decisionPathScorePills = useMemo(() => ([
    {
      id: 'features' as WelcomeDecisionPathAreaId,
      label: tx('welcome.summary.path.score.features', 'Capabilities'),
      value: decisionPath?.scores.features || 0,
    },
    {
      id: 'pricing' as WelcomeDecisionPathAreaId,
      label: tx('welcome.summary.path.score.pricing', 'Commercial'),
      value: decisionPath?.scores.pricing || 0,
    },
    {
      id: 'social-proof' as WelcomeDecisionPathAreaId,
      label: tx('welcome.summary.path.score.social', 'Proof'),
      value: decisionPath?.scores['social-proof'] || 0,
    },
  ]), [decisionPath, tx]);

  const recapItems = useMemo(() => ([
    {
      id: 'features',
      icon: 'sparkles-outline',
      title: tx('welcome.summary.recaps.features.title', 'Capability depth that supports enterprise adoption.'),
      copy: tx('welcome.summary.recaps.features.copy', 'From the Capability Command Center to workflow memory, the platform now turns explored value into repeatable operational value.'),
    },
    {
      id: 'pricing',
      icon: 'card-outline',
      title: tx('welcome.summary.recaps.pricing.title', 'Commercial clarity that supports confident review.'),
      copy: tx('welcome.summary.recaps.pricing.copy', 'Visitors can compare Free, Basic, and Premium with clear tradeoffs and a sharper understanding of what each tier unlocks next.'),
    },
    {
      id: 'proof',
      icon: 'shield-checkmark-outline',
      title: tx('welcome.summary.recaps.proof.title', 'Trust proof that strengthens buying confidence.'),
      copy: tx('welcome.summary.recaps.proof.copy', 'Proof stories, segment filters, and visible outcomes position the Welcome page as a credible decision surface for serious buyers.'),
    },
  ]), [tx]);

  const readinessItems = useMemo(() => ([
    tx('welcome.summary.readiness.one', 'Designed for polished delivery on phone, tablet, and desktop'),
    tx('welcome.summary.readiness.two', 'Consistent V2 contrast and hierarchy in light and dark modes'),
    tx('welcome.summary.readiness.three', 'Localization-safe messaging for enterprise environments'),
  ]), [tx]);

  const decisionItems = useMemo(() => ([
    {
      id: 'start',
      tone: 'primary',
      title: decisionPathContent.title,
      copy: decisionPathContent.copy,
      action: decisionPathContent.action,
      onPress: onRegister,
    },
    {
      id: 'about',
      tone: 'secondary',
      title: decisionPathContent.supportTitle,
      copy: decisionPathContent.supportCopy,
      action: decisionPathContent.supportAction,
      onPress: onOpenAbout,
    },
    {
      id: 'return',
      tone: 'secondary',
      title: tx('welcome.summary.decision.return.title', 'Resume your workspace without friction.'),
      copy: tx('welcome.summary.decision.return.copy', 'Already in an active review? Sign in and continue from your saved decision context.'),
      action: tx('welcome.summary.decision.return.action', 'Sign in'),
      onPress: onLogin,
    },
  ]), [decisionPathContent, onLogin, onOpenAbout, onRegister, tx]);

  const fadeA = useRef(new Animated.Value(0)).current;
  const slideA = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeA, { toValue: 1, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideA, { toValue: 0, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [fadeA, slideA]);

  return (
    <Animated.View style={[s.wrap, { opacity: fadeA, transform: [{ translateY: slideA }] }]} data-testid="welcome-cta-section" testID="welcome-cta-section">
      {Platform.OS === 'web' ? (
        <style dangerouslySetInnerHTML={{ __html: `
          .welcome-close-grid {
            display: grid;
            grid-template-columns: ${useWideCloseLayout ? 'minmax(0, 0.95fr) minmax(0, 1.05fr)' : 'minmax(0, 1fr)'};
            gap: ${useWideCloseLayout ? '24px' : '20px'};
            width: 100%;
            align-items: stretch;
          }
          .welcome-close-decision:hover {
            transform: translateY(-4px);
            transition: transform 0.24s ease;
          }
        ` }} />
      ) : null}

      <View style={s.headerBlock} data-testid="welcome-summary-header" testID="welcome-summary-header">
        <Text style={s.overline}>{tx('welcome.summary.overline', 'Decision-ready close')}</Text>
        <Text style={s.headline} data-testid="welcome-summary-headline" testID="welcome-summary-headline">{tx('welcome.summary.title', 'Everything above now answers the real buyer question: why act now, and what happens next?')}</Text>
        <Text style={s.description} data-testid="welcome-summary-description" testID="welcome-summary-description">{tx('welcome.summary.description', 'This final surface closes the Welcome story with a clean enterprise summary, the right next action, and the reassurance serious teams expect before they commit.')}</Text>
      </View>

      {Platform.OS === 'web' ? (
        <div className="welcome-close-grid">
          <View style={s.summaryZone} data-testid="welcome-summary-zone" testID="welcome-summary-zone">
            <View style={s.summaryCard} data-testid="welcome-summary-card" testID="welcome-summary-card">
              <Text style={s.summaryCardTitle}>{tx('welcome.summary.cardTitle', 'What this Welcome experience now proves')}</Text>
              <View style={s.recapList}>
                {recapItems.map((item, idx) => (
                  <View key={item.id} style={s.recapItem} data-testid={`welcome-summary-recap-${idx}`} testID={`welcome-summary-recap-${idx}`}>
                    <View style={s.recapIcon}><Ionicons name={item.icon as any} size={16} color={WC.primary} /></View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.recapTitle}>{item.title}</Text>
                      <Text style={s.recapCopy}>{item.copy}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            <View style={s.readinessCard} data-testid="welcome-summary-readiness-card" testID="welcome-summary-readiness-card">
              <Text style={s.readinessTitle}>{tx('welcome.summary.readiness.title', 'Enterprise readiness snapshot')}</Text>
              <View style={s.readinessList} data-testid="welcome-trust-badges-container" testID="welcome-trust-badges-container">
                {readinessItems.map((item, idx) => (
                  <View key={`${item}-${idx}`} style={s.readinessRow} data-testid={`welcome-summary-readiness-${idx}`} testID={`welcome-summary-readiness-${idx}`}>
                    <Ionicons name="checkmark-circle" size={15} color={WC.successText} />
                    <Text style={s.readinessText}>{item}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>

          <View style={s.decisionStrip} data-testid="welcome-decision-strip" testID="welcome-decision-strip">
            <Text style={s.decisionOverline}>{tx('welcome.cta.headline', 'Recommended next step')}</Text>
            <Text style={s.decisionTitle}>{tx('welcome.cta.title', 'Turn evaluation into a confident next action.')}</Text>
            <Text style={s.decisionCopy}>{tx('welcome.cta.subtitle', 'Whether you are opening a free workspace or resuming an active review, the next step should feel clear, deliberate, and easy to act on.')}</Text>

            <View style={s.pathCard} data-testid="welcome-decision-path-card" testID="welcome-decision-path-card">
              <View style={s.pathHeaderRow}>
                <Text style={s.pathLabel}>{tx('welcome.summary.path.label', 'Recommended decision path')}</Text>
                <View style={s.pathFocusChip} data-testid={`welcome-decision-path-focus-${decisionPathContent.areaId}`} testID={`welcome-decision-path-focus-${decisionPathContent.areaId}`}>
                  <Text style={s.pathFocusChipText}>{tx(`welcome.summary.path.focus.${decisionPathContent.areaId}`, decisionPathContent.areaId)}</Text>
                </View>
              </View>
              <Text style={s.pathTitle} data-testid="welcome-decision-path-title" testID="welcome-decision-path-title">{decisionPathContent.title}</Text>
              <Text style={s.pathDescription} data-testid="welcome-decision-path-copy" testID="welcome-decision-path-copy">{decisionPathContent.copy}</Text>
              <View style={s.pathScoreRow} data-testid="welcome-decision-path-score-row" testID="welcome-decision-path-score-row">
                {decisionPathScorePills.map((pill) => {
                  const active = pill.id === decisionPathContent.areaId;
                  return (
                    <View key={pill.id} style={[s.pathScorePill, active ? s.pathScorePillActive : null]} data-testid={`welcome-decision-path-score-${pill.id}`} testID={`welcome-decision-path-score-${pill.id}`}>
                      <Text style={[s.pathScorePillLabel, active ? s.pathScorePillLabelActive : null]}>{pill.label}</Text>
                      <Text style={[s.pathScorePillValue, active ? s.pathScorePillValueActive : null]}>{pill.value}</Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={[s.decisionGrid, useBalancedDecisionGrid && s.decisionGridWide]}>
              {decisionItems.map((item, idx) => {
                const primary = item.tone === 'primary';
                return (
                  <TouchableOpacity accessibilityLabel={tx(`welcome.cta.accessibility.${item.id}`, item.action)}
                    key={item.id}
                    onPress={item.onPress}
                    style={[
                      s.decisionCard,
                      primary ? s.decisionCardPrimary : s.decisionCardSecondary,
                      useBalancedDecisionGrid && primary ? s.decisionCardHero : null,
                      useBalancedDecisionGrid && !primary ? s.decisionCardSplit : null,
                    ]}
                    data-testid={idx === 0 ? 'welcome-primary-cta-button' : idx === 1 ? 'welcome-about-cta-button' : 'welcome-secondary-cta-button'}
                    testID={idx === 0 ? 'welcome-primary-cta-button' : idx === 1 ? 'welcome-about-cta-button' : 'welcome-secondary-cta-button'}
                  >
                    <View style={s.decisionCardHeader}>
                      <Text style={[s.decisionCardTitle, primary ? s.decisionCardTitlePrimary : null]}>{item.title}</Text>
                      <Ionicons name={primary ? 'arrow-forward' : item.id === 'about' ? 'information-circle-outline' : 'log-in-outline'} size={16} color={primary ? WC.primaryText : WC.text} />
                    </View>
                    <Text style={[s.decisionCardCopy, primary ? s.decisionCardCopyPrimary : null]}>{item.copy}</Text>
                    <View style={[s.decisionAction, primary ? s.decisionActionPrimary : s.decisionActionSecondary]}>
                      <Text style={[s.decisionActionText, primary ? s.decisionActionTextPrimary : null]}>{item.action}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>

            <View style={s.finalTrustRow} data-testid="welcome-cta-trust-row" testID="welcome-cta-trust-row">
              <View style={s.finalTrustChip}><Text style={s.finalTrustChipText}>{tx('welcome.summary.trust.one', 'Free workspace access starts without a credit card')}</Text></View>
              <View style={s.finalTrustChip}><Text style={s.finalTrustChipText}>{tx('welcome.summary.trust.two', 'A plan-aware upgrade path is already structured for scale')}</Text></View>
            </View>
          </View>
        </div>
      ) : (
        <View style={s.mobileStack}>
          <View style={s.summaryZone} data-testid="welcome-summary-zone" testID="welcome-summary-zone">
            <View style={s.summaryCard} data-testid="welcome-summary-card" testID="welcome-summary-card">
              <Text style={s.summaryCardTitle}>{tx('welcome.summary.cardTitle', 'What this Welcome experience now proves')}</Text>
              <View style={s.recapList}>{recapItems.map((item, idx) => <View key={item.id} style={s.recapItem} data-testid={`welcome-summary-recap-${idx}`} testID={`welcome-summary-recap-${idx}`}><View style={s.recapIcon}><Ionicons name={item.icon as any} size={16} color={WC.primary} /></View><View style={{ flex: 1, minWidth: 0 }}><Text style={s.recapTitle}>{item.title}</Text><Text style={s.recapCopy}>{item.copy}</Text></View></View>)}</View>
            </View>
            <View style={s.readinessCard} data-testid="welcome-summary-readiness-card" testID="welcome-summary-readiness-card"><Text style={s.readinessTitle}>{tx('welcome.summary.readiness.title', 'Enterprise readiness snapshot')}</Text><View style={s.readinessList} data-testid="welcome-trust-badges-container" testID="welcome-trust-badges-container">{readinessItems.map((item, idx) => <View key={`${item}-${idx}`} style={s.readinessRow} data-testid={`welcome-summary-readiness-${idx}`} testID={`welcome-summary-readiness-${idx}`}><Ionicons name="checkmark-circle" size={15} color={WC.successText} /><Text style={s.readinessText}>{item}</Text></View>)}</View></View>
          </View>
          <View style={s.decisionStrip} data-testid="welcome-decision-strip" testID="welcome-decision-strip"><Text style={s.decisionOverline}>{tx('welcome.cta.headline', 'Recommended next step')}</Text><Text style={s.decisionTitle}>{tx('welcome.cta.title', 'Turn evaluation into a confident next action.')}</Text><Text style={s.decisionCopy}>{tx('welcome.cta.subtitle', 'Whether you are opening a free workspace or resuming an active review, the next step should feel clear, deliberate, and easy to act on.')}</Text><View style={s.pathCard} data-testid="welcome-decision-path-card" testID="welcome-decision-path-card"><View style={s.pathHeaderRow}><Text style={s.pathLabel}>{tx('welcome.summary.path.label', 'Recommended decision path')}</Text><View style={s.pathFocusChip} data-testid={`welcome-decision-path-focus-${decisionPathContent.areaId}`} testID={`welcome-decision-path-focus-${decisionPathContent.areaId}`}><Text style={s.pathFocusChipText}>{tx(`welcome.summary.path.focus.${decisionPathContent.areaId}`, decisionPathContent.areaId)}</Text></View></View><Text style={s.pathTitle} data-testid="welcome-decision-path-title" testID="welcome-decision-path-title">{decisionPathContent.title}</Text><Text style={s.pathDescription} data-testid="welcome-decision-path-copy" testID="welcome-decision-path-copy">{decisionPathContent.copy}</Text><View style={s.pathScoreRow} data-testid="welcome-decision-path-score-row" testID="welcome-decision-path-score-row">{decisionPathScorePills.map((pill) => { const active = pill.id === decisionPathContent.areaId; return <View key={pill.id} style={[s.pathScorePill, active ? s.pathScorePillActive : null]} data-testid={`welcome-decision-path-score-${pill.id}`} testID={`welcome-decision-path-score-${pill.id}`}><Text style={[s.pathScorePillLabel, active ? s.pathScorePillLabelActive : null]}>{pill.label}</Text><Text style={[s.pathScorePillValue, active ? s.pathScorePillValueActive : null]}>{pill.value}</Text></View>; })}</View></View><View style={s.decisionGrid}>{decisionItems.map((item, idx) => { const primary = item.tone === 'primary'; return <TouchableOpacity key={item.id} accessibilityRole="button" tabIndex={0} onPress={item.onPress} style={[s.decisionCard, primary ? s.decisionCardPrimary : s.decisionCardSecondary]} data-testid={idx === 0 ? 'welcome-primary-cta-button' : idx === 1 ? 'welcome-about-cta-button' : 'welcome-secondary-cta-button'} testID={idx === 0 ? 'welcome-primary-cta-button' : idx === 1 ? 'welcome-about-cta-button' : 'welcome-secondary-cta-button'}><View style={s.decisionCardHeader}><Text style={[s.decisionCardTitle, primary ? s.decisionCardTitlePrimary : null]}>{item.title}</Text><Ionicons name={primary ? 'arrow-forward' : item.id === 'about' ? 'information-circle-outline' : 'log-in-outline'} size={16} color={primary ? WC.primaryText : WC.text} /></View><Text style={[s.decisionCardCopy, primary ? s.decisionCardCopyPrimary : null]}>{item.copy}</Text><View style={[s.decisionAction, primary ? s.decisionActionPrimary : s.decisionActionSecondary]}><Text style={[s.decisionActionText, primary ? s.decisionActionTextPrimary : null]}>{item.action}</Text></View></TouchableOpacity>; })}</View><View style={s.finalTrustRow} data-testid="welcome-cta-trust-row" testID="welcome-cta-trust-row"><View style={s.finalTrustChip}><Text style={s.finalTrustChipText}>{tx('welcome.summary.trust.one', 'Free workspace access starts without a credit card')}</Text></View><View style={s.finalTrustChip}><Text style={s.finalTrustChipText}>{tx('welcome.summary.trust.two', 'A plan-aware upgrade path is already structured for scale')}</Text></View></View></View>
        </View>
      )}
    </Animated.View>
  );
}

function makeStyles(WC: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens, isDesktop: boolean, isTablet: boolean, isCompactMobile: boolean) {
  return StyleSheet.create({
    wrap: { paddingHorizontal: horizontalPadding, paddingBottom: isCompactMobile ? 76 : 92, maxWidth: tokens.maxWidth, alignSelf: 'center', width: '100%', gap: isDesktop ? 28 : 22, ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}) },
    headerBlock: { alignItems: 'center', gap: 14, marginBottom: isDesktop ? 14 : 10 },
    overline: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 2.2, textTransform: 'uppercase', textAlign: 'center' },
    headline: { color: WC.text, fontSize: isDesktop ? 40 : 30, lineHeight: isDesktop ? 46 : 36, fontWeight: '900', letterSpacing: -1, textAlign: 'center', maxWidth: 920 },
    description: { color: WC.textSec, fontSize: 15, lineHeight: 24, textAlign: 'center', maxWidth: 760 },
    mobileStack: { gap: 20, width: '100%', maxWidth: WELCOME_CENTERED_SECTION_MAX_WIDTH, alignSelf: 'center' },
    summaryZone: {
      gap: 18,
      borderRadius: 28,
      borderWidth: 1,
      borderColor: withAlpha(WC.primary, isDark ? '24' : '18'),
      backgroundColor: withAlpha(WC.surface, isDark ? 'F2' : 'FE'),
      padding: isCompactMobile ? 18 : isDesktop ? 22 : 20,
      justifyContent: 'space-between',
      ...cardBlur,
      ...getShadow('lg', isDark),
    },
    summaryCard: { borderRadius: 22, borderWidth: 1, borderColor: withAlpha(WC.borderStrong, isDark ? '88' : '72'), backgroundColor: withAlpha(WC.card, isDark ? 'C8' : 'FA'), padding: isCompactMobile ? 16 : 18, gap: 18 },
    summaryCardTitle: { color: WC.text, fontSize: 17, fontWeight: '900', letterSpacing: -0.3 },
    recapList: { gap: 14 },
    recapItem: { flexDirection: 'row', gap: 12, alignItems: 'flex-start', paddingVertical: 2 },
    recapIcon: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: withAlpha(WC.primary, '14'), borderWidth: 1, borderColor: withAlpha(WC.primary, '30') },
    recapTitle: { color: WC.text, fontSize: 15, fontWeight: '800', lineHeight: 21 },
    recapCopy: { color: WC.textMuted, fontSize: 12, lineHeight: 20, marginTop: 4 },
    readinessCard: { borderRadius: 22, borderWidth: 1, borderColor: withAlpha(WC.successText, isDark ? '38' : '26'), backgroundColor: withAlpha(WC.card, isDark ? 'F0' : 'FC'), padding: isCompactMobile ? 16 : 18, gap: 14 },
    readinessTitle: { color: WC.text, fontSize: 16, fontWeight: '800', letterSpacing: -0.2 },
    readinessList: { gap: 12 },
    readinessRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
    readinessText: { color: WC.textSec, fontSize: 13, lineHeight: 20, flex: 1 },
    decisionStrip: { borderRadius: 28, borderWidth: 1, borderColor: withAlpha(WC.warningText, isDark ? '2C' : '22'), backgroundColor: withAlpha(WC.card, isDark ? 'F4' : 'FE'), padding: isCompactMobile ? 18 : isDesktop ? 26 : 24, gap: 20, ...cardBlur, ...getShadow('lg', isDark) },
    decisionOverline: { color: WC.warningText, fontSize: 11, fontWeight: '800', letterSpacing: 1.6, textTransform: 'uppercase' },
    decisionTitle: { color: WC.text, fontSize: isDesktop ? 34 : 28, lineHeight: isDesktop ? 40 : 34, fontWeight: '900', letterSpacing: -0.8 },
    decisionCopy: { color: WC.textSec, fontSize: 15, lineHeight: 24, maxWidth: 620 },
    pathCard: { borderRadius: 20, borderWidth: 1, borderColor: withAlpha(WC.warningText, '30'), backgroundColor: withAlpha(WC.warningText, isDark ? '12' : '09'), padding: isCompactMobile ? 14 : 18, gap: 14 },
    pathHeaderRow: { flexDirection: isCompactMobile ? 'column' : 'row', alignItems: isCompactMobile ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 10 },
    pathLabel: { color: WC.warningText, fontSize: 10, fontWeight: '900', letterSpacing: 1.3, textTransform: 'uppercase' },
    pathFocusChip: { borderRadius: 999, borderWidth: 1, borderColor: withAlpha(WC.warningText, '34'), backgroundColor: withAlpha(WC.warningText, isDark ? '1C' : '16'), paddingHorizontal: 12, paddingVertical: 7 },
    pathFocusChipText: { color: WC.warningText, fontSize: 11, fontWeight: '800' },
    pathTitle: { color: WC.text, fontSize: isDesktop ? 20 : 18, lineHeight: isDesktop ? 26 : 24, fontWeight: '900' },
    pathDescription: { color: WC.textMuted, fontSize: 13, lineHeight: 21 },
    pathScoreRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    pathScorePill: { borderRadius: 14, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.surface, isDark ? 'D8' : 'F8'), paddingHorizontal: 11, paddingVertical: 9, minWidth: isCompactMobile ? 92 : 100, gap: 2 },
    pathScorePillActive: { borderColor: withAlpha(WC.primary, '38'), backgroundColor: withAlpha(WC.primary, isDark ? '1A' : '12') },
    pathScorePillLabel: { color: WC.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 },
    pathScorePillLabelActive: { color: WC.primary },
    pathScorePillValue: { color: WC.text, fontSize: 16, fontWeight: '900' },
    pathScorePillValueActive: { color: WC.primary },
    decisionGrid: { gap: 14 },
    decisionGridWide: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'stretch', justifyContent: 'center' },
    decisionCard: { borderRadius: 18, borderWidth: 1, padding: 18, gap: 12, justifyContent: 'space-between', ...(Platform.OS === 'web' ? { transition: 'transform 180ms ease, border-color 180ms ease, background-color 180ms ease', cursor: 'pointer' } as any : {}) },
    decisionCardPrimary: { borderColor: WC.primary, backgroundColor: WC.primary },
    decisionCardSecondary: { borderColor: WC.borderStrong, backgroundColor: withAlpha(WC.surface, isDark ? 'D8' : 'F8') },
    decisionCardHero: { width: '100%' },
    decisionCardSplit: { width: '48.6%' },
    decisionCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 },
    decisionCardTitle: { color: WC.text, fontSize: 16, lineHeight: 22, fontWeight: '900', flex: 1 },
    decisionCardTitlePrimary: { color: WC.primaryText },
    decisionCardCopy: { color: WC.textMuted, fontSize: 13, lineHeight: 21 },
    decisionCardCopyPrimary: { color: withAlpha(WC.primaryText, 'D5') },
    decisionAction: { borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, alignSelf: 'flex-start' },
    decisionActionPrimary: { backgroundColor: withAlpha(WC.primaryText, '18') },
    decisionActionSecondary: { borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.bgSoft, isDark ? 'C0' : 'F3') },
    decisionActionText: { color: WC.text, fontSize: 12, fontWeight: '800' },
    decisionActionTextPrimary: { color: WC.primaryText },
    finalTrustRow: { flexDirection: isCompactMobile ? 'column' : 'row', gap: 10, flexWrap: 'wrap', paddingTop: 12, marginTop: 4, borderTopWidth: 1, borderTopColor: withAlpha(WC.border, '78') },
    finalTrustChip: { borderRadius: 999, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.bgSoft, isDark ? 'C8' : 'F5'), paddingHorizontal: 14, paddingVertical: 9 },
    finalTrustChipText: { color: WC.textMuted, fontSize: 11, fontWeight: '700' },
  });
}
