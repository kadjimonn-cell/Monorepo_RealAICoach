import React, { useMemo, useState } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import PublicPageShell from '../src/components/PublicPageLayout';
import { PricingSkeleton, FadeSlideIn, usePageReady } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useGlobalPlatformState } from '../src/hooks/useGlobalPlatformState';
import { useTranslation } from '../src/hooks/useTranslation';
import { buildWelcomePricingSurfaceTarget, resolveVisitorCtaPath } from '../src/utils/visitorCtaPolicy';
import { PricingBottomCta } from '../src/components/pricing/PricingBottomCta';
import { PricingFaqSection } from '../src/components/pricing/PricingFaqSection';
import { PricingHeroSection } from '../src/components/pricing/PricingHeroSection';
import { PricingMatrixSection } from '../src/components/pricing/PricingMatrixSection';
import { PricingPlansSection } from '../src/components/pricing/PricingPlansSection';
import { PricingRoiSection } from '../src/components/pricing/PricingRoiSection';
import { buildDisplayTiers, buildMatrixRows, buildPricingFaq, getMaxAnnualSavingsPct, TierId } from '../src/components/pricing/pricingModels';

export default function PricingPage() {
  const { width } = useWindowDimensions();
  const m = width < 720;
  const d = width >= 1180;
  const router = useRouter();
  const { tx } = useTranslation();
  const { colors: C, darkMode } = useTheme();
  const { state: gpsState } = useGlobalPlatformState();
  const pageReady = usePageReady(true);

  const [isYearly, setIsYearly] = useState(true);
  const [activeTier, setActiveTier] = useState<TierId>('basic');
  const [teamSize, setTeamSize] = useState('30');
  const [toolSpend, setToolSpend] = useState('2500');

  const tiers = useMemo(() => buildDisplayTiers(Array.isArray(gpsState?.plans) ? gpsState.plans : [], tx), [gpsState?.plans, tx]);

  const activeTierConfig = useMemo(() => tiers.find((tier) => tier.id === activeTier) || tiers[1] || tiers[0], [activeTier, tiers]);
  const matrixRows = useMemo(() => buildMatrixRows(tiers, tx), [tiers, tx]);
  const maxAnnualSavingsPct = useMemo(() => getMaxAnnualSavingsPct(tiers), [tiers]);
  const pricingFaq = useMemo(() => buildPricingFaq(tx), [tx]);

  const annualSavingsPct = useMemo(() => {
    if (!activeTierConfig || activeTierConfig.monthly <= 0 || activeTierConfig.yearly <= 0) return 0;
    const yearlyFromMonthly = activeTierConfig.monthly * 12;
    const saved = yearlyFromMonthly - activeTierConfig.yearly;
    if (saved <= 0) return 0;
    return Math.round((saved / yearlyFromMonthly) * 100);
  }, [activeTierConfig]);

  const roi = useMemo(() => {
    const team = Math.max(1, Number(teamSize || 0));
    const currentMonthly = Math.max(0, Number(toolSpend || 0));
    const selectedSeatMonthly = isYearly ? activeTierConfig.yearly / 12 : activeTierConfig.monthly;
    const projectedMonthly = selectedSeatMonthly * team;
    const currentAnnual = currentMonthly * 12;
    const projectedAnnual = projectedMonthly * 12;
    const savings = currentAnnual - projectedAnnual;
    const savingsPct = currentAnnual > 0 ? Math.round((savings / currentAnnual) * 100) : 0;
    return {
      currentAnnual,
      projectedAnnual,
      savings,
      savingsPct,
    };
  }, [activeTierConfig, isYearly, teamSize, toolSpend]);

  const roiLabel = useMemo(() => {
    if (roi.savings >= 0) {
      return `${tx('pricing.page.roiPositive.prefix', 'Estimated impact: Save')} $${Math.round(roi.savings).toLocaleString()} (${Math.max(0, roi.savingsPct)}%)`;
    }
    return `${tx('pricing.page.roiNegative.prefix', 'Estimated impact:')} +${Math.abs(Math.round(roi.savingsPct))}% ${tx('pricing.page.roiNegative.suffix', 'spend for higher output velocity')}`;
  }, [roi.savings, roi.savingsPct, tx]);

  if (!pageReady) {
    return (
      <PublicPageShell maxWidth={1320}>
        <PricingSkeleton />
      </PublicPageShell>
    );
  }

  const handleRegister = () => router.push('/auth/register');
  const handleSales = () => router.push('/contact?intent=sales');
  const handleCompareInApp = () => {
    const canonicalTarget = buildWelcomePricingSurfaceTarget('pricing-compare');
    const safeTarget = resolveVisitorCtaPath(canonicalTarget, {
      isAuthenticated: false,
      surface: 'public',
      fallbackPath: buildWelcomePricingSurfaceTarget('pricing-compare'),
    });

    router.push(safeTarget as any);
  };

  return (
    <PublicPageShell maxWidth={1320}>
      <FadeSlideIn>
        <View style={{ gap: 22 }} data-testid="pricing-page" testID="pricing-page">
          <PricingHeroSection
            activeTierConfig={activeTierConfig}
            annualSavingsPct={annualSavingsPct}
            colors={C}
            darkMode={darkMode}
            isDesktop={d}
            isMobile={m}
            maxAnnualSavingsPct={maxAnnualSavingsPct}
            onStartFree={handleRegister}
            onTalkSales={handleSales}
          />

          <PricingPlansSection
            activeTier={activeTier}
            annualSavingsPct={maxAnnualSavingsPct}
            colors={C}
            darkMode={darkMode}
            isDesktop={d}
            isMobile={m}
            isYearly={isYearly}
            onRegister={handleRegister}
            onSelectTier={setActiveTier}
            setIsYearly={setIsYearly}
            tiers={tiers}
          />

          <PricingRoiSection
            activeTierConfig={activeTierConfig}
            colors={C}
            isDesktop={d}
            isMobile={m}
            roi={roi}
            roiLabel={roiLabel}
            setTeamSize={setTeamSize}
            setToolSpend={setToolSpend}
            teamSize={teamSize}
            toolSpend={toolSpend}
          />

          <PricingMatrixSection colors={C} matrixRows={matrixRows} tiers={tiers} />

          <PricingFaqSection colors={C} faq={pricingFaq} isMobile={m} />

          <PricingBottomCta
            colors={C}
            darkMode={darkMode}
            isDesktop={d}
            isMobile={m}
            onCompare={handleCompareInApp}
            onStart={handleRegister}
            onTalkSales={handleSales}
          />
        </View>
      </FadeSlideIn>
    </PublicPageShell>
  );
}
