export type TierId = 'free' | 'basic' | 'premium';

export type DisplayTier = {
  id: TierId;
  name: string;
  subtitle: string;
  monthly: number;
  yearly: number;
  badge?: string;
  cta: string;
  featured?: boolean;
  unlocks: string[];
  audience: string;
  rollout: string;
  support: string;
  valueLabel: string;
  emphasis: string;
};

type TranslateWithFallback = (key: string, fallback: string) => string;

function withTranslationFallback(tx: TranslateWithFallback, key: string, fallback: string) {
  return tx(key, fallback);
}

export function toNumber(value: any, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return parsed;
}

export function normalizeTierId(raw: string): TierId {
  const candidate = String(raw || '').trim().toLowerCase();
  if (candidate === 'premium') return 'premium';
  if (candidate === 'basic') return 'basic';
  return 'free';
}

export function getDefaultTiers(tx: TranslateWithFallback): DisplayTier[] {
  return [
    {
      id: 'free',
      name: withTranslationFallback(tx, 'welcome.pricing.free', 'Free'),
      subtitle: withTranslationFallback(tx, 'pricing.tier.free.subtitle', 'Start fast with core capability and a clean upgrade path.'),
      monthly: 0,
      yearly: 0,
      cta: withTranslationFallback(tx, 'welcome.pricing.getStarted', 'Get Started'),
      unlocks: [
        withTranslationFallback(tx, 'welcome.pricing.3aiPerDay', '3 AI conversations per day'),
        withTranslationFallback(tx, 'welcome.pricing.progressTracking', 'Progress tracking'),
        withTranslationFallback(tx, 'welcome.pricing.communitySupport', 'Community support'),
        withTranslationFallback(tx, 'pricing.tier.free.feature4', 'Launch-ready fundamentals'),
      ],
      audience: withTranslationFallback(tx, 'pricing.tier.free.audience', 'Individuals validating fit and early momentum.'),
      rollout: withTranslationFallback(tx, 'pricing.tier.free.rollout', 'Activate instantly with zero procurement friction.'),
      support: withTranslationFallback(tx, 'pricing.tier.free.support', 'Community support'),
      valueLabel: withTranslationFallback(tx, 'pricing.tier.free.valueLabel', 'Launch'),
      emphasis: withTranslationFallback(tx, 'pricing.tier.free.emphasis', 'Ideal for proving value before standardizing workflows.'),
    },
    {
      id: 'basic',
      name: withTranslationFallback(tx, 'welcome.pricing.basic', 'Basic'),
      subtitle: withTranslationFallback(tx, 'pricing.tier.basic.subtitle', 'The operating tier for teams building repeatable weekly execution.'),
      monthly: 6,
      yearly: 58,
      cta: withTranslationFallback(tx, 'welcome.pricing.goBasic', 'Go Basic'),
      badge: withTranslationFallback(tx, 'pricing.tier.basic.badge', 'Recommended'),
      featured: true,
      unlocks: [
        withTranslationFallback(tx, 'welcome.pricing.10aiPerDay', '10 AI conversations per day'),
        withTranslationFallback(tx, 'welcome.pricing.aiDetailedAnalytics', 'AI-powered detailed analytics'),
        withTranslationFallback(tx, 'welcome.pricing.emailSupport', 'Email support'),
        withTranslationFallback(tx, 'pricing.tier.basic.feature4', 'Clear value proof for weekly reviews'),
      ],
      audience: withTranslationFallback(tx, 'pricing.tier.basic.audience', 'Operators and small teams building durable habits.'),
      rollout: withTranslationFallback(tx, 'pricing.tier.basic.rollout', 'Strong fit for managers who need visible weekly output.'),
      support: withTranslationFallback(tx, 'pricing.tier.basic.support', 'Email support'),
      valueLabel: withTranslationFallback(tx, 'pricing.tier.basic.valueLabel', 'Operate'),
      emphasis: withTranslationFallback(tx, 'pricing.tier.basic.emphasis', 'Balances cost control, throughput, and upgrade confidence.'),
    },
    {
      id: 'premium',
      name: withTranslationFallback(tx, 'welcome.pricing.premium', 'Premium'),
      subtitle: withTranslationFallback(tx, 'pricing.tier.premium.subtitle', 'Enterprise-grade depth for leaders, power users, and high-stakes work.'),
      monthly: 16,
      yearly: 154,
      cta: withTranslationFallback(tx, 'welcome.pricing.goPremium', 'Go Premium'),
      badge: withTranslationFallback(tx, 'pricing.tier.premium.badge', 'Most capable'),
      featured: true,
      unlocks: [
        withTranslationFallback(tx, 'welcome.pricing.unlimitedAI', 'Unlimited AI conversations'),
        withTranslationFallback(tx, 'welcome.pricing.unlimitedHistory', 'Unlimited history & downloads'),
        withTranslationFallback(tx, 'welcome.pricing.prioritySupport', 'Priority support'),
        withTranslationFallback(tx, 'pricing.tier.premium.feature4', 'Advanced operating coverage for scaled use'),
      ],
      audience: withTranslationFallback(tx, 'pricing.tier.premium.audience', 'Leaders and power users running high-accountability workflows.'),
      rollout: withTranslationFallback(tx, 'pricing.tier.premium.rollout', 'Designed for deeper usage intensity and faster response needs.'),
      support: withTranslationFallback(tx, 'pricing.tier.premium.support', 'Priority support'),
      valueLabel: withTranslationFallback(tx, 'pricing.tier.premium.valueLabel', 'Accelerate'),
      emphasis: withTranslationFallback(tx, 'pricing.tier.premium.emphasis', 'For teams that need depth, speed, and stronger executive confidence.'),
    },
  ];
}

export function buildDisplayTiers(source: any[], tx: TranslateWithFallback): DisplayTier[] {
  const baseTiers = getDefaultTiers(tx);
  const byId = new Map<TierId, DisplayTier>(baseTiers.map((tier) => [tier.id, tier]));

  const allowedPlans = Array.isArray(source)
    ? source
      .filter((plan) => ['free', 'basic', 'premium'].includes(normalizeTierId((plan as any)?.plan_id || (plan as any)?.id)))
      .filter((plan) => String((plan as any)?.status || 'active').toLowerCase() !== 'deprecated')
    : [];

  allowedPlans.forEach((plan) => {
    const id = normalizeTierId((plan as any)?.plan_id || (plan as any)?.id);
    const fallback = byId.get(id) || baseTiers[0];
    const monthly = toNumber((plan as any)?.monthly_price, fallback.monthly);
    const yearlyRaw = toNumber((plan as any)?.yearly_price, monthly * 12);
    const yearly = yearlyRaw > 0 ? yearlyRaw : monthly * 12;
    const apiFeatures = Array.isArray((plan as any)?.features)
      ? (plan as any).features.map((item: any) => String(item || '').trim()).filter(Boolean).slice(0, 4)
      : [];

    byId.set(id, {
      ...fallback,
      name: String((plan as any)?.name || '').trim() || fallback.name,
      subtitle: String((plan as any)?.description || '').trim() || fallback.subtitle,
      monthly,
      yearly,
      unlocks: apiFeatures.length > 0 ? apiFeatures : fallback.unlocks,
    });
  });

  return baseTiers.map((tier) => byId.get(tier.id) || tier);
}

export function buildMatrixRows(tiers: DisplayTier[], tx: TranslateWithFallback) {
  const free = tiers.find((tier) => tier.id === 'free') || tiers[0];
  const basic = tiers.find((tier) => tier.id === 'basic') || tiers[1] || tiers[0];
  const premium = tiers.find((tier) => tier.id === 'premium') || tiers[2] || tiers[tiers.length - 1];

  return [
    { label: tx('pricing.matrix.row.capacity', 'Daily AI capacity'), values: { free: free.unlocks[0] || tx('pricing.matrix.fallback.core', 'Core'), basic: basic.unlocks[0] || tx('pricing.matrix.fallback.expanded', 'Expanded'), premium: premium.unlocks[0] || tx('pricing.matrix.fallback.unlimited', 'Unlimited') } },
    { label: tx('pricing.matrix.row.analytics', 'Analytics depth'), values: { free: free.unlocks[1] || tx('pricing.matrix.fallback.foundational', 'Foundational'), basic: basic.unlocks[1] || tx('pricing.matrix.fallback.operational', 'Operational'), premium: premium.unlocks[1] || tx('pricing.matrix.fallback.advanced', 'Advanced') } },
    { label: tx('pricing.matrix.row.support', 'Support path'), values: { free: free.support, basic: basic.support, premium: premium.support } },
    { label: tx('pricing.matrix.row.bestFit', 'Best fit'), values: { free: free.audience, basic: basic.audience, premium: premium.audience } },
    { label: tx('pricing.matrix.row.rollout', 'Rollout posture'), values: { free: free.rollout, basic: basic.rollout, premium: premium.rollout } },
    { label: tx('pricing.matrix.row.motion', 'Commercial motion'), values: { free: free.valueLabel, basic: basic.valueLabel, premium: premium.valueLabel } },
  ];
}

export function getMaxAnnualSavingsPct(tiers: DisplayTier[]) {
  return tiers.reduce((best, tier) => {
    if (tier.monthly <= 0 || tier.yearly <= 0) return best;
    const saved = tier.monthly * 12 - tier.yearly;
    const pct = saved > 0 ? Math.round((saved / (tier.monthly * 12)) * 100) : 0;
    return Math.max(best, pct);
  }, 0);
}

export function getHeroProofPoints(tx: TranslateWithFallback) {
  return [
    tx('pricing.hero.proof.1', 'Three live entitlement tiers'),
    tx('pricing.hero.proof.2', 'Monthly or annual billing visibility'),
    tx('pricing.hero.proof.3', 'Upgrade-safe transitions'),
    tx('pricing.hero.proof.4', 'Community to priority support'),
  ];
}

export function getCommercialLanes(tx: TranslateWithFallback) {
  return [
    {
      title: tx('pricing.hero.lane.1.title', 'Operations teams'),
      body: tx('pricing.hero.lane.1.body', 'Standardize a predictable plan structure without over-buying on day one.'),
    },
    {
      title: tx('pricing.hero.lane.2.title', 'Coaching & enablement'),
      body: tx('pricing.hero.lane.2.body', 'Move from launch to weekly execution with clearer analytics and support paths.'),
    },
    {
      title: tx('pricing.hero.lane.3.title', 'Managers & leaders'),
      body: tx('pricing.hero.lane.3.body', 'Compare cost, capability, and support posture with executive-friendly clarity.'),
    },
    {
      title: tx('pricing.hero.lane.4.title', 'Procurement reviewers'),
      body: tx('pricing.hero.lane.4.body', 'Understand upgrade logic and annual savings without decoding a complex catalog.'),
    },
  ];
}

export function getDecisionPrinciples(tx: TranslateWithFallback) {
  return [
    {
      title: tx('pricing.roi.principle.1.title', 'Clear commercial progression'),
      body: tx('pricing.roi.principle.1.body', 'Free, Basic, and Premium step up in a way decision-makers can explain quickly to teams and approvers.'),
    },
    {
      title: tx('pricing.roi.principle.2.title', 'Upgrade without workflow reset'),
      body: tx('pricing.roi.principle.2.body', 'Users can start small and expand later without changing the route structure or entitlement model.'),
    },
    {
      title: tx('pricing.roi.principle.3.title', 'Budget visibility up front'),
      body: tx('pricing.roi.principle.3.body', 'Monthly and annual views make trade-offs visible before anyone reaches the checkout step.'),
    },
  ];
}

export function buildPricingFaq(tx: TranslateWithFallback) {
  return [
    {
      q: tx('pricing.faq.1.q', 'Can I move from Free to Basic or Premium anytime?'),
      a: tx('pricing.faq.1.a', 'Yes. The pricing flow is designed for clean progression, so teams can upgrade when they need more capacity, support, or analytics depth.'),
    },
    {
      q: tx('pricing.faq.2.q', 'Do Basic and Premium support annual billing?'),
      a: tx('pricing.faq.2.a', 'Yes. Annual pricing helps budget owners lock in savings and makes longer planning cycles easier to manage.'),
    },
    {
      q: tx('pricing.faq.3.q', 'How should I choose between Basic and Premium?'),
      a: tx('pricing.faq.3.a', 'Choose Basic for disciplined weekly execution and Premium when throughput, support responsiveness, and usage depth become more business-critical.'),
    },
    {
      q: tx('pricing.faq.4.q', 'Can I start on Free before committing to a paid plan?'),
      a: tx('pricing.faq.4.a', 'Absolutely. Free is intentionally practical, so users can validate value first and scale only when their workflow calls for it.'),
    },
  ];
}