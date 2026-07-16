import type { GPSFeature } from '../../hooks/useGlobalPlatformState';

export type CapabilityCategoryId = 'growth' | 'operations' | 'intelligence' | 'enterprise';
export type CapabilityTier = 'free' | 'basic' | 'premium';
export type CapabilityBadgeId = 'most-used' | 'fastest-win' | 'highest-impact' | 'team-favorite';

export type CapabilityDefinition = {
  featureId: string;
  routeFallback: string;
  categoryId: CapabilityCategoryId;
  tier: CapabilityTier;
  badgeId: CapabilityBadgeId;
  icon: string;
  color: string;
  titleKey: string;
  titleFallback: string;
  summaryKey: string;
  summaryFallback: string;
};

export type HydratedCapability = CapabilityDefinition & {
  route: string;
  live: boolean;
  isNew: boolean;
};

export const CAPABILITY_CATEGORY_ORDER: CapabilityCategoryId[] = ['growth', 'operations', 'intelligence', 'enterprise'];

export const CAPABILITY_CATALOG: CapabilityDefinition[] = [
  {
    featureId: 'ai-writer',
    routeFallback: '/features/ai-writer',
    categoryId: 'growth',
    tier: 'basic',
    badgeId: 'fastest-win',
    icon: 'create-outline',
    color: '#38BDF8',
    titleKey: 'welcome.features.catalog.aiWriter.title',
    titleFallback: 'AI Writer',
    summaryKey: 'welcome.features.catalog.aiWriter.summary',
    summaryFallback: 'Turn rough ideas into launch-ready copy, briefs, and executive updates in one workflow.',
  },
  {
    featureId: 'ai-chatbot',
    routeFallback: '/features/ai-chatbot',
    categoryId: 'growth',
    tier: 'free',
    badgeId: 'most-used',
    icon: 'chatbubble-ellipses-outline',
    color: '#22C55E',
    titleKey: 'welcome.features.catalog.aiChatbot.title',
    titleFallback: 'AI Chatbot',
    summaryKey: 'welcome.features.catalog.aiChatbot.summary',
    summaryFallback: 'Give teams an always-on thinking partner for questions, decisions, and rapid coaching loops.',
  },
  {
    featureId: 'ai-search',
    routeFallback: '/features/ai-search',
    categoryId: 'growth',
    tier: 'basic',
    badgeId: 'highest-impact',
    icon: 'search-outline',
    color: '#A855F7',
    titleKey: 'welcome.features.catalog.aiSearch.title',
    titleFallback: 'AI Search',
    summaryKey: 'welcome.features.catalog.aiSearch.summary',
    summaryFallback: 'Find answers, patterns, and buried context without slowing down your execution rhythm.',
  },
  {
    featureId: 'ai-automations',
    routeFallback: '/features/ai-automations',
    categoryId: 'operations',
    tier: 'basic',
    badgeId: 'most-used',
    icon: 'git-network-outline',
    color: '#F97316',
    titleKey: 'welcome.features.catalog.aiAutomations.title',
    titleFallback: 'AI Automations',
    summaryKey: 'welcome.features.catalog.aiAutomations.summary',
    summaryFallback: 'Remove repetitive work with guided automations that keep operations moving without extra headcount.',
  },
  {
    featureId: 'bill-generator',
    routeFallback: '/features/bill-generator',
    categoryId: 'operations',
    tier: 'basic',
    badgeId: 'fastest-win',
    icon: 'receipt-outline',
    color: '#EAB308',
    titleKey: 'welcome.features.catalog.billGenerator.title',
    titleFallback: 'Bill Generator',
    summaryKey: 'welcome.features.catalog.billGenerator.summary',
    summaryFallback: 'Create polished billing documents and reduce admin drag across finance-heavy workflows.',
  },
  {
    featureId: 'book-meeting',
    routeFallback: '/book-meeting',
    categoryId: 'operations',
    tier: 'basic',
    badgeId: 'team-favorite',
    icon: 'calendar-outline',
    color: '#14B8A6',
    titleKey: 'welcome.features.catalog.bookMeeting.title',
    titleFallback: 'Book Meeting',
    summaryKey: 'welcome.features.catalog.bookMeeting.summary',
    summaryFallback: 'Move from interest to booked action with fewer scheduling gaps and cleaner handoffs.',
  },
  {
    featureId: 'ai-cognitive',
    routeFallback: '/features/ai-cognitive',
    categoryId: 'intelligence',
    tier: 'basic',
    badgeId: 'team-favorite',
    icon: 'sparkles-outline',
    color: '#60A5FA',
    titleKey: 'welcome.features.catalog.aiCognitive.title',
    titleFallback: 'AI Cognitive',
    summaryKey: 'welcome.features.catalog.aiCognitive.summary',
    summaryFallback: 'Break down complex thinking tasks into clear, coachable next steps your team can act on fast.',
  },
  {
    featureId: 'ai-coaching-team',
    routeFallback: '/ai-coaching-team',
    categoryId: 'intelligence',
    tier: 'premium',
    badgeId: 'highest-impact',
    icon: 'people-circle-outline',
    color: '#EF4444',
    titleKey: 'welcome.features.catalog.aiCoachingTeam.title',
    titleFallback: 'AI Coaching Team',
    summaryKey: 'welcome.features.catalog.aiCoachingTeam.summary',
    summaryFallback: 'Chat with a curated team of AI coaches for career growth, interviews, resumes, and negotiation.',
  },
  {
    featureId: 'lexicon-intelligence',
    routeFallback: '/features/lexicon-intelligence',
    categoryId: 'intelligence',
    tier: 'basic',
    badgeId: 'most-used',
    icon: 'library-outline',
    color: '#8B5CF6',
    titleKey: 'welcome.features.catalog.lexiconIntelligence.title',
    titleFallback: 'Lexicon Intelligence',
    summaryKey: 'welcome.features.catalog.lexiconIntelligence.summary',
    summaryFallback: 'Normalize messy language, align terminology, and keep your organization speaking with one voice.',
  },
  {
    featureId: 'ai-enterprise',
    routeFallback: '/features/ai-enterprise',
    categoryId: 'enterprise',
    tier: 'premium',
    badgeId: 'highest-impact',
    icon: 'business-outline',
    color: '#06B6D4',
    titleKey: 'welcome.features.catalog.aiEnterprise.title',
    titleFallback: 'AI Enterprise',
    summaryKey: 'welcome.features.catalog.aiEnterprise.summary',
    summaryFallback: 'Coordinate high-trust AI workflows with premium visibility, governance cues, and cross-team control.',
  },
  {
    featureId: 'integrations',
    routeFallback: '/integrations',
    categoryId: 'enterprise',
    tier: 'premium',
    badgeId: 'team-favorite',
    icon: 'layers-outline',
    color: '#84CC16',
    titleKey: 'welcome.features.catalog.integrations.title',
    titleFallback: 'Integrations',
    summaryKey: 'welcome.features.catalog.integrations.summary',
    summaryFallback: 'Connect the workflows your teams already use so AI value compounds across the stack.',
  },
  {
    featureId: 'id-checker',
    routeFallback: '/id-checker',
    categoryId: 'enterprise',
    tier: 'premium',
    badgeId: 'fastest-win',
    icon: 'shield-checkmark-outline',
    color: '#F59E0B',
    titleKey: 'welcome.features.catalog.idChecker.title',
    titleFallback: 'ID Checker',
    summaryKey: 'welcome.features.catalog.idChecker.summary',
    summaryFallback: 'Add identity-aware verification to sensitive flows without breaking speed or trust.',
  },
];

export const CAPABILITY_TIER_RANK: Record<CapabilityTier, number> = {
  free: 0,
  basic: 1,
  premium: 2,
};

export function hydrateCapabilityCatalog(features: GPSFeature[] | undefined): HydratedCapability[] {
  const liveById = new Map(
    (features || []).map((feature: any) => [String(feature?.feature_id || '').trim(), feature]),
  );

  return CAPABILITY_CATALOG.map((definition) => {
    const live = liveById.get(definition.featureId);
    const route = String(live?.route || definition.routeFallback || '').trim() || definition.routeFallback;
    const icon = String(live?.icon || definition.icon || 'sparkles-outline');
    const color = String(live?.color || definition.color || '#38BDF8');
    const softDeactivated = Boolean((live as any)?.soft_deactivated);
    const enabled = live ? live.enabled !== false && !softDeactivated : true;

    return {
      ...definition,
      route,
      icon,
      color,
      live: enabled,
      isNew: Boolean((live as any)?.is_new),
    };
  });
}
