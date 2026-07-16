export type UpgradeCopy = {
  title: string;
  benefit: string;
  cta: string;
  recommendedPlan: 'basic' | 'premium';
};

const DEFAULT_COPY: UpgradeCopy = {
  title: 'Unlock this premium workflow with Basic',
  benefit: 'Upgrade now to remove route limits and access advanced execution tools.',
  cta: 'Upgrade to Basic',
  recommendedPlan: 'basic',
};

const ROUTE_COPY: { prefix: string; copy: UpgradeCopy }[] = [
  {
    prefix: '/features/decision-coach',
    copy: {
      title: 'Unlock Decision Coach with Basic',
      benefit: 'Run deeper strategy simulations and speed up high-stakes decisions.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/features/ai-automations',
    copy: {
      title: 'Unlock AI Automations with Basic',
      benefit: 'Automate repetitive workflows and compound productivity every day.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/features/analytics-reports',
    copy: {
      title: 'Unlock Analytics Reports with Basic',
      benefit: 'Track performance trends and act on clearer revenue and growth signals.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/features/ai-enterprise',
    copy: {
      title: 'Unlock AI Enterprise with Basic',
      benefit: 'Access enterprise-grade AI operations to scale faster and safer.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/mini-apps/ai-accounting',
    copy: {
      title: 'Unlock AI Accounting with Basic',
      benefit: 'Move from manual tracking to automated financial intelligence.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/mini-apps/creator-exchange',
    copy: {
      title: 'Unlock Creator Exchange with Basic',
      benefit: 'Get faster access to growth opportunities and creator monetization tools.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/subscription/mobile-money',
    copy: {
      title: 'Unlock Mobile Money Checkout with Basic',
      benefit: 'Activate a smoother payment path with higher completion reliability.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
  {
    prefix: '/features/content-studio',
    copy: {
      title: 'Unlock Content Studio with Premium',
      benefit: 'Generate production-ready, high-converting content assets at scale.',
      cta: 'Upgrade to Premium',
      recommendedPlan: 'premium',
    },
  },
  {
    prefix: '/workspace',
    copy: {
      title: 'Unlock Workspace with Premium',
      benefit: 'Coordinate advanced AI workflows across your full operating stack.',
      cta: 'Upgrade to Premium',
      recommendedPlan: 'premium',
    },
  },
  {
    prefix: '/job-platform-employer',
    copy: {
      title: 'Unlock Employer Portal with Basic',
      benefit: 'Post roles, manage applicants, and run hiring operations from one panel.',
      cta: 'Upgrade to Basic',
      recommendedPlan: 'basic',
    },
  },
];

export function getUpgradeCopyForPath(path: string): UpgradeCopy {
  const normalized = String(path || '/').trim() || '/';
  for (const row of ROUTE_COPY) {
    if (normalized.startsWith(row.prefix)) {
      return row.copy;
    }
  }
  return DEFAULT_COPY;
}
