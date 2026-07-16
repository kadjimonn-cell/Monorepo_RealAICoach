export const GLOBAL_PRICING_POLICY = {
  currency: 'USD',
  yearlyDiscountPct: 20,
  plans: {
    free: { id: 'free', name: 'Free', monthly: 0, yearly: 0 },
    basic: { id: 'basic', name: 'Basic', monthly: 5.99, yearly: 57.5 },
    premium: { id: 'premium', name: 'Premium', monthly: 15.99, yearly: 153.5 },
  },
} as const;

export type PricingPlanId = keyof typeof GLOBAL_PRICING_POLICY.plans;

export function getFrontendPlanPrice(planId: string, billingPeriod: 'monthly' | 'yearly' = 'monthly') {
  const normalized = String(planId || '').toLowerCase() as PricingPlanId;
  const plan = GLOBAL_PRICING_POLICY.plans[normalized] || GLOBAL_PRICING_POLICY.plans.basic;
  return billingPeriod === 'yearly' ? plan.yearly : plan.monthly;
}

export function getFrontendPlanName(planId: string) {
  const normalized = String(planId || '').toLowerCase() as PricingPlanId;
  return (GLOBAL_PRICING_POLICY.plans[normalized] || GLOBAL_PRICING_POLICY.plans.basic).name;
}

export function getFrontendYearlyDiscountPct() {
  return GLOBAL_PRICING_POLICY.yearlyDiscountPct;
}

export function buildFrontendPricingSaveLabel(template: string | undefined, fallback: string = 'SAVE {pct}%') {
  const safeTemplate = String(template || fallback || '').trim() || fallback;
  return safeTemplate.replace('{pct}', String(getFrontendYearlyDiscountPct()));
}