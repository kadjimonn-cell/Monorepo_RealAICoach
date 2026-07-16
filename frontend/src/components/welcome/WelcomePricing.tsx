import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { StaggerChildren } from '../StaggerChildren';
import { getShadow } from '../../utils/themeShadows';
import { useLanguage } from '../../i18n/LanguageContext';
import { useIsClient } from '../../hooks/useIsClient';
import api from '../../services/api';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import type { GLSTokens } from '../../context/GLSContext';
import { buildFrontendPricingSaveLabel, getFrontendYearlyDiscountPct } from '../../config/pricingPolicy';
import { withAlpha } from '../../utils/colorAlpha';
import { loadWelcomeWorkflowMemory } from './welcomeWorkflowMemory';
import { CAPABILITY_CATALOG } from './welcomeCapabilityCatalog';
import { WELCOME_CENTERED_LAYOUT_BREAKPOINT, WELCOME_CENTERED_SECTION_MAX_WIDTH } from './welcomeSectionContract';

interface Props {
  onRegister: (planInfo?: { planId: string; planName: string; planPrice: string; billingPeriod: string }) => void;
  plans?: {
    plan_id: string;
    name: string;
    description?: string;
    monthly_price?: number;
    yearly_price?: number;
    currency?: string;
    features?: string[];
    limitations?: string[];
    status?: string;
  }[];
  recommendedWorkflowName?: string;
  recommendedWorkflowCategory?: string;
  recommendedWorkflowRecency?: string;
  onDecisionPathSignal?: (areaId: 'features' | 'pricing' | 'social-proof', weight?: number) => void;
}

type PricingPlanView = {
  id: string;
  name: string;
  monthlyPrice: string;
  yearlyPrice: string;
  rawMonthlyUsd: string;
  rawYearlyUsd: string;
  monthlyPeriod: string;
  yearlyPeriod: string;
  savePct: number;
  description: string;
  cta: string;
  badge?: string;
  recommended: boolean;
  proof: string;
  outcome: string;
  tierNote: string;
  upgradeWhy: string;
  features: { text: string; included: boolean }[];
};

const cardBlur = Platform.OS === 'web' ? { backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)' } as any : {};

export function WelcomePricing({
  onRegister,
  plans = [],
  recommendedWorkflowName,
  recommendedWorkflowCategory,
  recommendedWorkflowRecency,
  onDecisionPathSignal,
}: Props) {
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const isCompactMobile = width < 560;
  const isNarrowMobile = width <= 360;
  const useDenseMobilePricingCards = width < 430;
  const useWidePricingLayout = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT;
  const isClient = useIsClient();
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const s = useMemo(() => makeStyles(WC, isDark, padding, tokens, isCompactMobile, isNarrowMobile, useWidePricingLayout, useDenseMobilePricingCards), [WC, isDark, padding, tokens, isCompactMobile, isNarrowMobile, useWidePricingLayout, useDenseMobilePricingCards]);

  const [isYearly, setIsYearly] = useState(true);
  const [selectedCurrency, setSelectedCurrency] = useState('USD');
  const [currencies, setCurrencies] = useState<{code: string; symbol: string; name: string; rate: number}[]>([]);
  const [memoryFallback, setMemoryFallback] = useState<{ workflow: string; category: string; recency: string }>({ workflow: '', category: '', recency: '' });

  useEffect(() => {
    let cancelled = false;
    const loadCurrencies = async () => {
      try {
        const data = (await api.get('/payments/currencies', { silentLoading: true })).data;
        if (!cancelled && data?.currencies) setCurrencies(data.currencies);
      } catch {
        // silent
      }
    };
    void loadCurrencies();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (currencies.length === 0) return;
    if (Platform.OS !== 'web' || typeof navigator === 'undefined') return;

    const locale = navigator.language || 'en-US';
    const region = locale.split('-')[1]?.toUpperCase();
    const regionCurrencyMap: Record<string, string> = {
      US: 'USD', GB: 'GBP', CA: 'CAD', AU: 'AUD', IN: 'INR', NG: 'NGN', KE: 'KES', ZA: 'ZAR', BR: 'BRL', MX: 'MXN', JP: 'JPY', KR: 'KRW', CH: 'CHF', SG: 'SGD', HK: 'HKD', FR: 'EUR', DE: 'EUR', ES: 'EUR', IT: 'EUR', NL: 'EUR', PT: 'EUR', IE: 'EUR', AT: 'EUR', FI: 'EUR', GR: 'EUR',
    };
    const guessedCurrency = region ? regionCurrencyMap[region] : undefined;
    if (guessedCurrency && guessedCurrency !== 'USD') {
      const supported = currencies.find((c) => c.code === guessedCurrency);
      if (supported) {
        setSelectedCurrency(guessedCurrency);
        return;
      }
    }
    // Geo fallback: generic locales (e.g. plain "en") carry no region — resolve via IP.
    let cancelled = false;
    api.get('/geo/detect', { silentLoading: true })
      .then(({ data }) => {
        if (cancelled) return;
        const geoCurrency = String(data?.default_currency || '').toUpperCase();
        if (geoCurrency && geoCurrency !== 'USD' && currencies.some((c) => c.code === geoCurrency)) {
          setSelectedCurrency(geoCurrency);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currencies]);

  useEffect(() => {
    if (recommendedWorkflowName) return;
    let cancelled = false;
    const restoreMemory = async () => {
      const memory = await loadWelcomeWorkflowMemory();
      if (!memory || cancelled) return;
      const match = CAPABILITY_CATALOG.find((item) => item.featureId === memory.featureId);
      const timestamp = Date.parse(memory.updatedAt || '');
      const recency = Number.isFinite(timestamp)
        ? (() => {
            const deltaMin = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
            if (deltaMin < 1) return tx('welcome.features.memory.justNow', 'just now');
            if (deltaMin < 60) return tx('welcome.features.memory.minutesAgo', '{count}m ago').replace('{count}', String(deltaMin));
            return tx('welcome.features.memory.hoursAgo', '{count}h ago').replace('{count}', String(Math.floor(deltaMin / 60)));
          })()
        : '';
      setMemoryFallback({
        workflow: match ? tx(match.titleKey, match.titleFallback) : '',
        category: memory.categoryId ? tx(`welcome.features.categories.${memory.categoryId}`, memory.categoryId) : '',
        recency,
      });
    };
    void restoreMemory();
    return () => { cancelled = true; };
  }, [recommendedWorkflowName, tx]);

  const currentCurrency = useMemo(
    () => currencies.find((c) => c.code === selectedCurrency) || { code: 'USD', symbol: '$', name: 'US Dollar', rate: 1 },
    [currencies, selectedCurrency],
  );

  const convertPrice = useCallback((usdValue: number) => {
    if (!usdValue) return `${currentCurrency.symbol}0`;
    const converted = usdValue * currentCurrency.rate;
    const noDecimal = ['JPY', 'KRW', 'XOF', 'XAF'].includes(selectedCurrency);
    const formatted = noDecimal ? Math.round(converted).toLocaleString() : converted.toFixed(2);
    return `${currentCurrency.symbol}${formatted}`;
  }, [currentCurrency.rate, currentCurrency.symbol, selectedCurrency]);

  const plansView = useMemo<PricingPlanView[]>(() => {
    return (plans || [])
      .filter((plan) => plan.status !== 'deprecated')
      .map((plan) => {
        const monthlyUsd = Number(plan.monthly_price || 0);
        const yearlyUsd = Number(plan.yearly_price || 0) || monthlyUsd * 12;
        const savePct = monthlyUsd > 0 ? Math.max(0, Math.round((1 - yearlyUsd / (monthlyUsd * 12)) * 100)) : 0;
        const features = (plan.features || []).map((item) => ({ text: item, included: true }));
        const limitations = (plan.limitations || []).map((item) => ({ text: item, included: false }));
        const id = String(plan.plan_id || '').trim();

        return {
          id,
          name: plan.name,
          monthlyPrice: convertPrice(monthlyUsd),
          yearlyPrice: convertPrice(yearlyUsd),
          rawMonthlyUsd: String(monthlyUsd),
          rawYearlyUsd: String(yearlyUsd),
          monthlyPeriod: tx('welcome.pricing.perMonth', '/month'),
          yearlyPeriod: tx('welcome.pricing.perYear', '/year'),
          savePct,
          description: plan.description || '',
          cta: id === 'free'
            ? tx('welcome.pricing.getStarted', 'Get started')
            : id === 'basic'
              ? tx('welcome.pricing.goBasic', 'Go Basic')
              : tx('welcome.pricing.goPremium', 'Go Premium'),
          badge: id === 'basic' ? tx('welcome.pricing.bestValue', 'Best Value') : id === 'premium' ? tx('welcome.pricing.executiveChoice', 'Executive Choice') : undefined,
          recommended: id === 'basic',
          proof: id === 'free'
            ? tx('welcome.pricing.proof.free', 'Launch with the platform layer your team can adopt immediately.')
            : id === 'basic'
              ? tx('welcome.pricing.proof.basic', 'Most teams land here when they want recurring workflow traction fast.')
              : tx('welcome.pricing.proof.premium', 'Best for teams that need full control, governance, and premium command depth.'),
          outcome: id === 'free'
            ? tx('welcome.pricing.outcome.free', 'Validate adoption before procurement friction appears.')
            : id === 'basic'
              ? tx('welcome.pricing.outcome.basic', 'Move from curiosity to repeatable operating rhythm.')
              : tx('welcome.pricing.outcome.premium', 'Turn AI from a helpful tool into a defensible operating system.'),
          tierNote: id === 'free'
            ? tx('welcome.pricing.tierNote.free', 'Best for first workflows')
            : id === 'basic'
              ? tx('welcome.pricing.tierNote.basic', 'Best for active teams')
              : tx('welcome.pricing.tierNote.premium', 'Best for executive rollout'),
          upgradeWhy: id === 'free'
            ? tx('welcome.pricing.upgradeWhy.free', 'Start free, save interest, and remove friction from your first activation.')
            : id === 'basic'
              ? tx('welcome.pricing.upgradeWhy.basic', 'Unlock the workflow bench most paying teams need to stay in motion.')
              : tx('welcome.pricing.upgradeWhy.premium', 'Unlock every trust, control, and intelligence layer together.'),
          features: [...features, ...limitations],
        };
      });
  }, [convertPrice, plans, tx]);

  const maxSaveLabel = useMemo(() => {
    const maxSavePct = plansView.reduce((best, plan) => Math.max(best, Number(plan.savePct || 0)), 0);
    return buildFrontendPricingSaveLabel(tx('welcome.pricing.saveDynamic', 'SAVE {pct}%'), 'SAVE {pct}%').replace(
      String(getFrontendYearlyDiscountPct()),
      String(maxSavePct || getFrontendYearlyDiscountPct()),
    );
  }, [plansView, tx]);

  const activeRecommendation = useMemo(() => {
    const workflow = recommendedWorkflowName || memoryFallback.workflow;
    const categoryName = recommendedWorkflowCategory || memoryFallback.category;
    const recencyLabel = recommendedWorkflowRecency || memoryFallback.recency;
    if (!workflow) return tx('welcome.pricing.recommendationFallback', 'Choose the plan that matches your next workflow depth.');
    const category = categoryName ? `${categoryName} • ` : '';
    const recency = recencyLabel ? ` • ${recencyLabel}` : '';
    return tx('welcome.pricing.recommendationValue', '{category}{workflow}{recency}')
      .replace('{category}', category)
      .replace('{workflow}', workflow)
      .replace('{recency}', recency);
  }, [memoryFallback.category, memoryFallback.recency, memoryFallback.workflow, recommendedWorkflowCategory, recommendedWorkflowName, recommendedWorkflowRecency, tx]);

  const fadeA = useRef(new Animated.Value(0)).current;
  const slideA = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeA, { toValue: 1, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideA, { toValue: 0, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [fadeA, slideA]);

  useEffect(() => {
    onDecisionPathSignal?.('pricing', 1);
  }, [isYearly, onDecisionPathSignal, selectedCurrency]);

  return (
    <Animated.View style={[s.wrap, { opacity: fadeA, transform: [{ translateY: slideA }] }]} data-testid="welcome-pricing" testID="welcome-pricing">
      {Platform.OS === 'web' ? (
        <style dangerouslySetInnerHTML={{ __html: `
          .welcome-pricing-card {
            transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.28s ease, box-shadow 0.28s ease;
          }
          .welcome-pricing-card:hover {
            transform: translateY(-6px);
            box-shadow: ${isDark ? `0 26px 54px ${withAlpha(WC.shadowColor, '94')}` : `0 24px 54px ${withAlpha(WC.shadowColor, '1A')}`};
          }
          .welcome-pricing-grid {
            display: grid;
            grid-template-columns: ${useWidePricingLayout ? 'repeat(3, minmax(0, 1fr))' : width >= 768 ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)'};
            gap: 16px;
            width: 100%;
          }
        ` }} />
      ) : null}

      <View style={s.heroShell} data-testid="welcome-pricing-command-shell" testID="welcome-pricing-command-shell">
        <View style={s.heroCard} data-testid="welcome-pricing-hero-card" testID="welcome-pricing-hero-card">
          <Text style={s.label} data-testid="welcome-pricing-label" testID="welcome-pricing-label">{tx('welcome.pricing.commandLabel', 'Pricing command surface')}</Text>
          <Text style={[s.title, isDesktop && { fontSize: 38 }]} data-testid="welcome-pricing-title" testID="welcome-pricing-title">{tx('welcome.pricing.commandTitle', 'Choose the plan that matches your workflow depth, not just your seat count.')}</Text>
          <Text style={s.sub} data-testid="welcome-pricing-subtitle" testID="welcome-pricing-subtitle">{tx('welcome.pricing.commandSubtitle', 'Compare outcome velocity, upgrade leverage, and the operational depth each plan unlocks for serious teams.')}</Text>

          <View style={s.recommendationCard} data-testid="welcome-pricing-workflow-memory-card" testID="welcome-pricing-workflow-memory-card">
            <View style={s.recommendationIcon}><Ionicons name="flash-outline" size={18} color={WC.warningText} /></View>
            <View style={{ flex: 1, minWidth: 0, gap: 4, alignItems: isCompactMobile ? 'center' : 'flex-start' }}>
              <Text style={s.recommendationLabel}>{tx('welcome.pricing.recommendationLabel', 'Recommended next workflow')}</Text>
              <Text style={s.recommendationValue} data-testid="welcome-pricing-workflow-memory-value" testID="welcome-pricing-workflow-memory-value">{activeRecommendation}</Text>
            </View>
          </View>
        </View>

        <View style={s.controlCard} data-testid="welcome-pricing-control-card" testID="welcome-pricing-control-card">
          <Text style={s.controlLabel}>{tx('welcome.pricing.controlLabel', 'Commercial controls')}</Text>
          <View style={s.toggleWrap} data-testid="billing-toggle" testID="billing-toggle">
            <TouchableOpacity onPress={() => { onDecisionPathSignal?.('pricing', 2); setIsYearly(false); }} style={[s.toggleBtn, !isYearly && s.toggleBtnActive]} data-testid="billing-toggle-monthly" testID="billing-toggle-monthly">
              <Text style={[s.toggleText, !isYearly && s.toggleTextActive]}>{tx('welcome.pricing.monthly', 'Monthly')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { onDecisionPathSignal?.('pricing', 2); setIsYearly(true); }} style={[s.toggleBtn, isYearly && s.toggleBtnActive]} data-testid="billing-toggle-yearly" testID="billing-toggle-yearly">
              <Text style={[s.toggleText, isYearly && s.toggleTextActive]}>{tx('welcome.pricing.yearly', 'Yearly')}</Text>
              <View style={s.saveBadge}><Text style={s.saveBadgeText}>{maxSaveLabel}</Text></View>
            </TouchableOpacity>
          </View>

          {isClient && currencies.length > 0 ? (
            <View style={s.currencyCard} data-testid="currency-selector-wrapper" testID="currency-selector-wrapper">
              <Text style={s.currencyLabel}>{tx('welcome.pricing.currencyLabel', 'Display')}</Text>
              {Platform.OS === 'web' ? (
                <select
                  data-testid="currency-selector"
                  value={selectedCurrency}
                  onChange={(e: any) => { onDecisionPathSignal?.('pricing', 1); setSelectedCurrency(e.target.value); }}
                  style={{ background: 'transparent', color: WC.text, border: 'none', outline: 'none', fontWeight: 700, fontSize: 13 } as any}
                >
                  {currencies.map((currency) => (
                    <option key={currency.code} value={currency.code} style={{ background: WC.card } as any}>
                      {currency.symbol} {currency.code} - {currency.name}
                    </option>
                  ))}
                </select>
              ) : (
                <Text style={s.currencyValue}>{currentCurrency.symbol} {currentCurrency.code}</Text>
              )}
            </View>
          ) : null}

          {selectedCurrency !== 'USD' ? (
            <Text style={s.currencyApproximation} data-testid="currency-approx-note" testID="currency-approx-note">
              {tx('welcome.pricing.currencyApproximation', 'Prices shown in {symbol} {currency} are approximate. You will be charged in {currency} at checkout.')
                .replace('{symbol}', currentCurrency.symbol)
                .replaceAll('{currency}', selectedCurrency)}
            </Text>
          ) : null}

          <View style={s.controlStatsRow}>
            <View style={s.controlStat} data-testid="welcome-pricing-control-stat-roi" testID="welcome-pricing-control-stat-roi">
              <Text style={s.controlStatLabel}>{tx('welcome.pricing.controlStat.one.label', 'Fastest value')}</Text>
              <Text style={s.controlStatValue}>{tx('welcome.pricing.controlStat.one.value', 'Basic')}</Text>
            </View>
            <View style={s.controlStat} data-testid="welcome-pricing-control-stat-depth" testID="welcome-pricing-control-stat-depth">
              <Text style={s.controlStatLabel}>{tx('welcome.pricing.controlStat.two.label', 'Deepest control')}</Text>
              <Text style={s.controlStatValue}>{tx('welcome.pricing.controlStat.two.value', 'Premium')}</Text>
            </View>
          </View>
        </View>
      </View>

      <StaggerChildren staggerMs={120} distance={34}>
        {plansView.length === 0 ? (
          <View style={s.emptyCard} data-testid="welcome-pricing-empty" testID="welcome-pricing-empty">
            <Text style={s.emptyTitle}>{tx('welcome.pricing.empty', 'No pricing available')}</Text>
            <Text style={s.emptyHint}>{tx('welcome.pricing.emptyHint', 'Pricing details will appear here once plans are configured.')}</Text>
          </View>
        ) : Platform.OS === 'web' ? (
          <div className="welcome-pricing-grid" data-testid="welcome-pricing-card-grid">
            {plansView.map((plan, index) => {
              const price = isYearly ? plan.yearlyPrice : plan.monthlyPrice;
              const period = isYearly ? plan.yearlyPeriod : plan.monthlyPeriod;
              return (
                <div key={plan.id} className="welcome-pricing-card" data-testid={`welcome-pricing-card-shell-${index}`}>
                  <View style={[s.planCard, plan.recommended ? s.planCardRecommended : null, plan.id === 'premium' ? s.planCardPremium : null]} data-testid={`welcome-plan-${plan.id}`} testID={`welcome-plan-${plan.id}`}>
                    <View style={s.planTopRow}>
                      <View style={{ gap: 6, flex: 1, minWidth: 0, alignItems: isCompactMobile ? 'center' : 'flex-start' }}>
                        <Text style={[s.planName, plan.recommended ? { color: WC.accent } : null]}>{plan.name}</Text>
                        <Text style={s.planTierNote}>{plan.tierNote}</Text>
                      </View>
                      {plan.badge ? (
                        <View style={[s.badge, plan.id === 'premium' ? s.badgePremium : null]} data-testid={`welcome-pricing-card-badge-${plan.id}`} testID={`welcome-pricing-card-badge-${plan.id}`}>
                          <Text style={s.badgeText}>{plan.badge}</Text>
                        </View>
                      ) : null}
                    </View>

                    <View style={s.priceRow}>
                      <Text style={s.price} data-testid={`plan-price-${plan.id}`} testID={`plan-price-${plan.id}`}>{price}</Text>
                      <Text style={s.period}>{period}</Text>
                    </View>
                    {isYearly && plan.savePct > 0 ? <Text style={s.yearlySaving} data-testid={`plan-saving-${plan.id}`} testID={`plan-saving-${plan.id}`}>{tx('welcome.pricing.saveVsMonthly', 'Save {pct}% vs monthly').replace('{pct}', String(plan.savePct))}</Text> : null}
                    <Text style={s.planDesc}>{plan.description}</Text>

                    <View style={s.planNarrative} data-testid={`welcome-pricing-proof-${plan.id}`} testID={`welcome-pricing-proof-${plan.id}`}>
                      <Text style={s.planNarrativeLabel}>{tx('welcome.pricing.proofLabel', 'Why teams choose it')}</Text>
                      <Text style={s.planNarrativeText}>{plan.proof}</Text>
                    </View>

                    <View style={s.planOutcome} data-testid={`welcome-pricing-outcome-${plan.id}`} testID={`welcome-pricing-outcome-${plan.id}`}>
                      <Ionicons name="trending-up-outline" size={14} color={plan.id === 'premium' ? WC.warningText : WC.accent} />
                      <Text style={s.planOutcomeText}>{plan.outcome}</Text>
                    </View>

                    {!useDenseMobilePricingCards ? <View style={s.divider} /> : null}

                    <TouchableOpacity accessibilityLabel={tx('welcome.pricing.accessibility.planCta', 'Choose pricing plan')}
                      onPress={() => {
                        onDecisionPathSignal?.('pricing', 3);
                        if (plan.id === 'free') {
                          onRegister();
                          return;
                        }
                        onRegister({
                          planId: plan.id,
                          planName: plan.name,
                          planPrice: isYearly ? plan.rawYearlyUsd : plan.rawMonthlyUsd,
                          billingPeriod: isYearly ? 'yearly' : 'monthly',
                        });
                      }}
                      style={[s.planCTA, plan.recommended ? s.planCTARecommended : null, plan.id === 'premium' ? s.planCTAPremium : null]}
                      data-testid={`welcome-plan-${plan.id}-cta`}
                      testID={`welcome-plan-${plan.id}-cta`}
                    >
                      <Text style={[s.planCTAText, plan.recommended ? s.planCTATextRecommended : null, plan.id === 'premium' ? s.planCTATextPremium : null]}>{plan.cta}</Text>
                    </TouchableOpacity>

                    <View style={s.divider} />

                    <View style={s.featureList}>
                      {(useDenseMobilePricingCards ? plan.features.slice(0, 4) : plan.features).map((feature, featureIdx) => (
                        <View key={`${plan.id}-${featureIdx}`} style={s.featureItem} data-testid={`welcome-pricing-feature-${plan.id}-${featureIdx}`} testID={`welcome-pricing-feature-${plan.id}-${featureIdx}`}>
                          <Ionicons name={feature.included ? 'checkmark-circle' : 'remove-circle-outline'} size={16} color={feature.included ? WC.successText : WC.textDisabled} />
                          <Text style={[s.featureText, !feature.included ? s.featureDisabled : null]}>{feature.text}</Text>
                        </View>
                      ))}
                    </View>

                    <Text style={s.upgradeWhy}>{useDenseMobilePricingCards ? plan.upgradeWhy.split('. ')[0] : plan.upgradeWhy}</Text>
                  </View>
                </div>
              );
            })}
          </div>
        ) : (
          <View style={s.grid} data-testid="welcome-pricing-card-grid" testID="welcome-pricing-card-grid">
            {plansView.map((plan) => {
              const price = isYearly ? plan.yearlyPrice : plan.monthlyPrice;
              const period = isYearly ? plan.yearlyPeriod : plan.monthlyPeriod;
              return (
                <View key={plan.id} style={[s.planCard, plan.recommended ? s.planCardRecommended : null, plan.id === 'premium' ? s.planCardPremium : null]} data-testid={`welcome-plan-${plan.id}`} testID={`welcome-plan-${plan.id}`}>
                  <View style={s.planTopRow}>
                    <View style={{ gap: 6, flex: 1, minWidth: 0, alignItems: isCompactMobile ? 'center' : 'flex-start' }}>
                      <Text style={[s.planName, plan.recommended ? { color: WC.accent } : null]}>{plan.name}</Text>
                      <Text style={s.planTierNote}>{plan.tierNote}</Text>
                    </View>
                    {plan.badge ? <View style={[s.badge, plan.id === 'premium' ? s.badgePremium : null]}><Text style={s.badgeText}>{plan.badge}</Text></View> : null}
                  </View>
                  <View style={s.priceRow}>
                    <Text style={s.price}>{price}</Text>
                    <Text style={s.period}>{period}</Text>
                  </View>
                  {isYearly && plan.savePct > 0 ? <Text style={s.yearlySaving}>{tx('welcome.pricing.saveVsMonthly', 'Save {pct}% vs monthly').replace('{pct}', String(plan.savePct))}</Text> : null}
                  <Text style={s.planDesc}>{plan.description}</Text>
                  <View style={s.planNarrative}><Text style={s.planNarrativeLabel}>{tx('welcome.pricing.proofLabel', 'Why teams choose it')}</Text><Text style={s.planNarrativeText}>{plan.proof}</Text></View>
                  <View style={s.planOutcome}><Ionicons name="trending-up-outline" size={14} color={plan.id === 'premium' ? WC.warningText : WC.accent} /><Text style={s.planOutcomeText}>{plan.outcome}</Text></View>
                  {!useDenseMobilePricingCards ? <View style={s.divider} /> : null}
                  <TouchableOpacity accessibilityLabel={tx('welcome.pricing.accessibility.planCta', 'Choose pricing plan')}
                    onPress={() => {
                      onDecisionPathSignal?.('pricing', 3);
                      if (plan.id === 'free') {
                        onRegister();
                        return;
                      }
                      onRegister({
                        planId: plan.id,
                        planName: plan.name,
                        planPrice: isYearly ? plan.rawYearlyUsd : plan.rawMonthlyUsd,
                        billingPeriod: isYearly ? 'yearly' : 'monthly',
                      });
                    }}
                    style={[s.planCTA, plan.recommended ? s.planCTARecommended : null, plan.id === 'premium' ? s.planCTAPremium : null]}
                    data-testid={`welcome-plan-${plan.id}-cta`}
                    testID={`welcome-plan-${plan.id}-cta`}
                  >
                    <Text style={[s.planCTAText, plan.recommended ? s.planCTATextRecommended : null, plan.id === 'premium' ? s.planCTATextPremium : null]}>{plan.cta}</Text>
                  </TouchableOpacity>
                  <View style={s.divider} />
                  <View style={s.featureList}>{(useDenseMobilePricingCards ? plan.features.slice(0, 4) : plan.features).map((feature, featureIdx) => <View key={`${plan.id}-${featureIdx}`} style={s.featureItem}><Ionicons name={feature.included ? 'checkmark-circle' : 'remove-circle-outline'} size={16} color={feature.included ? WC.successText : WC.textDisabled} /><Text style={[s.featureText, !feature.included ? s.featureDisabled : null]}>{feature.text}</Text></View>)}</View>
                  <Text style={s.upgradeWhy}>{useDenseMobilePricingCards ? plan.upgradeWhy.split('. ')[0] : plan.upgradeWhy}</Text>
                </View>
              );
            })}
          </View>
        )}
      </StaggerChildren>

      <Text style={s.guarantee} data-testid="welcome-pricing-guarantee" testID="welcome-pricing-guarantee">
        <Ionicons name="shield-checkmark" size={13} color={WC.successText} />{'  '}
        {tx('welcome.pricing.guarantee', 'Secure checkout. Cancel anytime. Upgrade paths remain policy-aware.')}
      </Text>
    </Animated.View>
  );
}

function makeStyles(WC: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens, isCompactMobile: boolean, isNarrowMobile: boolean, useWidePricingLayout: boolean, useDenseMobilePricingCards: boolean) {
  return StyleSheet.create({
    wrap: {
      paddingHorizontal: horizontalPadding,
      paddingVertical: 80,
      maxWidth: tokens.maxWidth,
      width: '100%',
      alignSelf: 'center',
      gap: 18,
      ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}),
    },
    heroShell: {
      flexDirection: useWidePricingLayout ? 'row' : 'column',
      gap: 16,
      alignItems: 'stretch',
      width: '100%',
      maxWidth: WELCOME_CENTERED_SECTION_MAX_WIDTH,
      alignSelf: 'center',
    },
    heroCard: {
      flex: useWidePricingLayout ? 1.15 : undefined,
      width: useWidePricingLayout ? undefined : '100%',
      borderRadius: 24,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.surface, isDark ? 'F0' : 'FB'),
      padding: isCompactMobile ? 18 : 24,
      gap: 14,
      ...cardBlur,
      ...getShadow('md', isDark),
      alignItems: isCompactMobile ? 'center' : 'stretch',
    },
    label: { color: WC.warningText, fontSize: 11, fontWeight: '800', letterSpacing: 2, textTransform: 'uppercase', textAlign: isCompactMobile ? 'center' : 'left' },
    title: { color: WC.text, fontSize: isNarrowMobile ? 28 : 34, lineHeight: isNarrowMobile ? 34 : 40, fontWeight: '900', letterSpacing: -1, textAlign: isCompactMobile ? 'center' : 'left' },
    sub: { color: WC.textMuted, fontSize: 15, lineHeight: 24, maxWidth: 720, textAlign: isCompactMobile ? 'center' : 'left' },
    recommendationCard: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: withAlpha(WC.warningText, '36'),
      backgroundColor: withAlpha(WC.warningText, isDark ? '12' : '08'),
      padding: 14,
      flexDirection: isCompactMobile ? 'column' : 'row',
      gap: 12,
      alignItems: 'center',
    },
    recommendationIcon: {
      width: 38,
      height: 38,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: withAlpha(WC.warningText, '16'),
    },
    recommendationLabel: { color: WC.warningText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.1, textAlign: isCompactMobile ? 'center' : 'left' },
    recommendationValue: { color: WC.text, fontSize: 14, lineHeight: 21, fontWeight: '700', textAlign: isCompactMobile ? 'center' : 'left' },
    controlCard: {
      flex: useWidePricingLayout ? 0.85 : undefined,
      width: useWidePricingLayout ? undefined : '100%',
      borderRadius: 24,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.card, isDark ? 'F0' : 'FD'),
      padding: isCompactMobile ? 16 : 20,
      gap: 14,
      ...cardBlur,
      ...getShadow('md', isDark),
      alignItems: isCompactMobile ? 'center' : 'stretch',
    },
    controlLabel: { color: WC.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.4, textAlign: isCompactMobile ? 'center' : 'left' },
    toggleWrap: { flexDirection: isCompactMobile ? 'column' : 'row', gap: 6, borderRadius: 16, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.surface, isDark ? 'D8' : 'F7'), padding: 4 },
    toggleBtn: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 11, flex: isCompactMobile ? undefined : 1 },
    toggleBtnActive: { backgroundColor: withAlpha(WC.accent, '15') },
    toggleText: { color: WC.textDim, fontSize: 13, fontWeight: '700' },
    toggleTextActive: { color: WC.accent },
    saveBadge: { backgroundColor: WC.accent, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
    saveBadgeText: { color: WC.bg, fontSize: 9, fontWeight: '800', letterSpacing: 0.4 },
    currencyCard: { flexDirection: isCompactMobile ? 'column' : 'row', alignItems: 'center', justifyContent: 'space-between', borderRadius: 14, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.surface, isDark ? 'D8' : 'F7'), paddingHorizontal: 14, paddingVertical: 10, gap: 12 },
    currencyLabel: { color: WC.textMuted, fontSize: 12, fontWeight: '700', textAlign: isCompactMobile ? 'center' : 'left' },
    currencyValue: { color: WC.text, fontSize: 13, fontWeight: '700', textAlign: isCompactMobile ? 'center' : 'left' },
    currencyApproximation: { color: WC.textDisabled, fontSize: 11, lineHeight: 17, fontStyle: 'italic', textAlign: isCompactMobile ? 'center' : 'left' },
    controlStatsRow: { flexDirection: isCompactMobile ? 'column' : 'row', gap: 10 },
    controlStat: { flex: 1, borderRadius: 16, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.bgSoft, isDark ? 'C8' : 'F3'), padding: 12, gap: 6, alignItems: isCompactMobile ? 'center' : 'flex-start' },
    controlStatLabel: { color: WC.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.1, textAlign: isCompactMobile ? 'center' : 'left' },
    controlStatValue: { color: WC.text, fontSize: 16, fontWeight: '900', textAlign: isCompactMobile ? 'center' : 'left' },
    grid: { gap: useDenseMobilePricingCards ? 14 : 16, width: '100%' },
    planCard: {
      borderRadius: 24,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.surface, isDark ? 'F0' : 'FC'),
      padding: useDenseMobilePricingCards ? 16 : isCompactMobile ? 18 : 24,
      gap: useDenseMobilePricingCards ? 12 : 14,
      width: '100%',
      minWidth: 0,
      ...cardBlur,
      ...getShadow('md', isDark),
      alignItems: isCompactMobile ? 'center' : 'stretch',
    },
    planCardRecommended: { borderColor: withAlpha(WC.accent, '45'), backgroundColor: withAlpha(WC.accent, isDark ? '0C' : '08') },
    planCardPremium: { borderColor: withAlpha(WC.warningText, '46'), backgroundColor: withAlpha(WC.warningText, isDark ? '0F' : '08') },
    planTopRow: { flexDirection: isCompactMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: 'center', gap: useDenseMobilePricingCards ? 8 : 10 },
    badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: withAlpha(WC.accent, '40'), backgroundColor: withAlpha(WC.accent, '12') },
    badgePremium: { borderColor: withAlpha(WC.warningText, '44'), backgroundColor: withAlpha(WC.warningText, '12') },
    badgeText: { color: WC.text, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.7 },
    planName: { color: WC.text, fontSize: 19, fontWeight: '900', textAlign: isCompactMobile ? 'center' : 'left' },
    planTierNote: { color: WC.textMuted, fontSize: useDenseMobilePricingCards ? 11 : 12, fontWeight: '700', textAlign: isCompactMobile ? 'center' : 'left' },
    priceRow: { flexDirection: 'row', alignItems: 'flex-end', gap: useDenseMobilePricingCards ? 4 : 6, flexWrap: 'wrap', justifyContent: isCompactMobile ? 'center' : 'flex-start' },
    price: { color: WC.text, fontSize: useDenseMobilePricingCards ? 30 : isNarrowMobile ? 34 : 42, fontWeight: '900', letterSpacing: -1.4, textAlign: isCompactMobile ? 'center' : 'left' },
    period: { color: WC.textDim, fontSize: 13, fontWeight: '700', marginBottom: 6, textAlign: isCompactMobile ? 'center' : 'left' },
    yearlySaving: { color: WC.successText, fontSize: 12, fontWeight: '700', marginTop: -6, textAlign: isCompactMobile ? 'center' : 'left' },
    planDesc: { color: WC.textSec, fontSize: useDenseMobilePricingCards ? 13 : 14, lineHeight: useDenseMobilePricingCards ? 20 : 22, textAlign: isCompactMobile ? 'center' : 'left' },
    planNarrative: { borderRadius: 16, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.bgSoft, isDark ? 'BC' : 'F3'), padding: useDenseMobilePricingCards ? 10 : 12, gap: useDenseMobilePricingCards ? 4 : 6, alignItems: isCompactMobile ? 'center' : 'flex-start' },
    planNarrativeLabel: { color: WC.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, textAlign: isCompactMobile ? 'center' : 'left' },
    planNarrativeText: { color: WC.textSec, fontSize: useDenseMobilePricingCards ? 12 : 13, lineHeight: useDenseMobilePricingCards ? 18 : 20, textAlign: isCompactMobile ? 'center' : 'left' },
    planOutcome: { flexDirection: isCompactMobile ? 'column' : 'row', gap: useDenseMobilePricingCards ? 8 : 10, alignItems: 'center', borderRadius: 14, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.bgSoft, isDark ? 'C0' : 'F5'), paddingHorizontal: useDenseMobilePricingCards ? 10 : 12, paddingVertical: useDenseMobilePricingCards ? 8 : 10 },
    planOutcomeText: { color: WC.text, fontSize: useDenseMobilePricingCards ? 11 : 12, lineHeight: useDenseMobilePricingCards ? 17 : 18, flex: isCompactMobile ? undefined : 1, textAlign: isCompactMobile ? 'center' : 'left' },
    planCTA: { borderRadius: 14, borderWidth: 1, borderColor: WC.borderStrong, backgroundColor: withAlpha(WC.card, isDark ? 'E2' : 'F6'), paddingVertical: useDenseMobilePricingCards ? 12 : 14, alignItems: 'center', justifyContent: 'center' },
    planCTARecommended: { backgroundColor: WC.accent, borderColor: WC.accent },
    planCTAPremium: { backgroundColor: WC.warningText, borderColor: WC.warningText },
    planCTAText: { color: WC.text, fontSize: 13, fontWeight: '800' },
    planCTATextRecommended: { color: WC.bg },
    planCTATextPremium: { color: WC.bg },
    divider: { height: 1, backgroundColor: WC.border },
    featureList: { gap: useDenseMobilePricingCards ? 8 : 10 },
    featureItem: { flexDirection: 'row', gap: useDenseMobilePricingCards ? 8 : 10, alignItems: 'flex-start' },
    featureText: { color: WC.textSec, fontSize: useDenseMobilePricingCards ? 12 : 13, lineHeight: useDenseMobilePricingCards ? 18 : 19, flex: 1 },
    featureDisabled: { color: WC.textDisabled },
    upgradeWhy: { color: WC.textMuted, fontSize: useDenseMobilePricingCards ? 10 : 11, lineHeight: useDenseMobilePricingCards ? 16 : 18, textAlign: isCompactMobile ? 'center' : 'left' },
    guarantee: { color: WC.textMuted, fontSize: 13, textAlign: 'center', marginTop: 10 },
    emptyCard: { borderRadius: 24, borderWidth: 1, borderColor: WC.border, backgroundColor: withAlpha(WC.surface, isDark ? 'EF' : 'FB'), padding: 22, gap: 8 },
    emptyTitle: { color: WC.text, fontSize: 18, fontWeight: '800', textAlign: 'center' },
    emptyHint: { color: WC.textMuted, fontSize: 14, lineHeight: 22, textAlign: 'center' },
  });
}
