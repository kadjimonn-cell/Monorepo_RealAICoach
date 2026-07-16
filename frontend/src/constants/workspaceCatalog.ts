export type WorkspaceApp = {
  id: string;
  name: string;
  tagline: string;
  tags: string[];
};

export type WorkspaceFeatureConfig = {
  title: string;
  count: number;
  modules: string[];
  tagPool: string[];
  prefixPool: string[];
  suffixPool: string[];
  tagline: string;
};

const SUFFIX_POOL = ['Labs', 'Studio', 'Cloud', 'Flow', 'Pulse', 'Core', 'Bridge', 'Works', 'Hub', 'AI'];

const BASE_WORKSPACE_FEATURES: Record<string, WorkspaceFeatureConfig> = {
  medimate: {
    title: 'MediMate',
    count: 15,
    modules: ['Symptom Triage', 'Medication Plan', 'Wellness Check', 'Care Follow-Up'],
    tagPool: ['triage', 'medication', 'care-plan', 'alerts', 'insights', 'telehealth'],
    prefixPool: ['Care', 'Pulse', 'Vital', 'Halo', 'Lumen', 'Well', 'Nexa', 'Sage', 'Sym', 'Apex'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Clinical-grade triage and proactive care pathways.',
  },
  pennypilot: {
    title: 'PennyPilot',
    count: 16,
    modules: ['Budget Builder', 'Debt Payoff', 'Savings Strategy', 'Investment Pulse'],
    tagPool: ['budget', 'savings', 'debt', 'investing', 'cashflow', 'alerts'],
    prefixPool: ['Ledger', 'Nova', 'Beacon', 'Minted', 'Clover', 'Summit', 'Prism', 'Foundry', 'Atlas', 'Quanta'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Smart finance workflows with live market context.',
  },
  assistant: {
    title: 'TaskTool',
    count: 15,
    modules: ['Focus Sprint', 'Weekly Planner', 'Meeting Concierge', 'Habit Builder'],
    tagPool: ['tasks', 'planning', 'habits', 'focus', 'calendar', 'automation'],
    prefixPool: ['Flow', 'Tempo', 'Orbit', 'Nova', 'Signal', 'Sprint', 'Vanta', 'Zen', 'Vector', 'Pilot'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Productivity copilots that orchestrate your week.',
  },
  smartbuy: {
    title: 'SmartBuy',
    count: 19,
    modules: ['Deal Scout', 'Price Watch', 'Cart Optimizer', 'Rewards Finder'],
    tagPool: ['deals', 'price', 'rewards', 'shopping', 'inventory', 'alerts'],
    prefixPool: ['Scout', 'Bargain', 'Vista', 'Flash', 'Crest', 'Market', 'Nova', 'Orbit', 'Pulse', 'Halo'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Commerce intelligence with real-time savings signals.',
  },
  fitness: {
    title: 'Fitness',
    count: 16,
    modules: ['Workout Builder', 'Recovery Coach', 'Nutrition Plan', 'Performance Check'],
    tagPool: ['training', 'recovery', 'nutrition', 'habits', 'strength', 'mobility'],
    prefixPool: ['Stride', 'Core', 'Nova', 'Apex', 'Pulse', 'Forge', 'Vigor', 'Zen', 'Tempo', 'Lift'],
    suffixPool: SUFFIX_POOL,
    tagline: 'AI-led fitness plans and recovery guidance.',
  },
  travelpal: {
    title: 'TravelPal',
    count: 15,
    modules: ['Trip Builder', 'Flight Radar', 'Stay Curator', 'Local Guide'],
    tagPool: ['itinerary', 'flights', 'stays', 'local', 'budget', 'alerts'],
    prefixPool: ['Voyage', 'Atlas', 'Wander', 'Drift', 'Summit', 'Sky', 'Nova', 'Roam', 'Lumen', 'Terra'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Curated itineraries with live travel intel.',
  },
  'ai-writer': {
    title: 'AI Writer',
    count: 16,
    modules: ['Draft Studio', 'Tone Editor', 'Summaries', 'Outline Builder'],
    tagPool: ['writing', 'tone', 'summaries', 'blogs', 'seo', 'editing'],
    prefixPool: ['Word', 'Lumen', 'Script', 'Nova', 'Scribe', 'Muse', 'Ink', 'Halo', 'Quill', 'Vivid'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Writing copilots for high-quality drafts.',
  },
  'ai-copywriter': {
    title: 'AI Copywriter',
    count: 15,
    modules: ['Ad Generator', 'Landing Copy', 'Email Sequences', 'Brand Voice'],
    tagPool: ['marketing', 'ads', 'email', 'landing', 'conversion', 'branding'],
    prefixPool: ['Launch', 'Echo', 'Bright', 'Nova', 'Signal', 'Vibe', 'Spark', 'Prism', 'Orbit', 'Aura'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Conversion-ready copy with campaign structure.',
  },
  'ai-photo': {
    title: 'AI Photo Editor',
    count: 17,
    modules: ['Enhance', 'Background Swap', 'Retouch', 'Style Pack'],
    tagPool: ['editing', 'retouch', 'styles', 'background', 'resolution', 'design'],
    prefixPool: ['Pixel', 'Luma', 'Prism', 'Nova', 'Aura', 'Vista', 'Focus', 'Halo', 'Radiant', 'Studio'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Pro-grade edits and photo transformations.',
  },
  'ai-vision': {
    title: 'AI Vision',
    count: 15,
    modules: ['Object Detection', 'Scene Insight', 'Safety Scan', 'Image QA'],
    tagPool: ['vision', 'detection', 'compliance', 'safety', 'labels', 'analysis'],
    prefixPool: ['Lens', 'Vector', 'Sight', 'Nimbus', 'Apex', 'Nova', 'Halo', 'Pulse', 'Orbit', 'Signal'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Computer vision intelligence at scale.',
  },
  'ai-automations': {
    title: 'AI Automations',
    count: 15,
    modules: ['Workflow Builder', 'Trigger Map', 'Ops Sync', 'Data Handoff'],
    tagPool: ['automation', 'workflows', 'ops', 'triggers', 'integrations', 'sync'],
    prefixPool: ['Flow', 'Relay', 'Pulse', 'Atlas', 'Nova', 'Circuit', 'Bridge', 'Orbit', 'Vector', 'Signal'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Automations that link every system.',
  },
  'ai-chatbot': {
    title: 'AI Chatbot',
    count: 20,
    modules: ['Support Desk', 'Sales Concierge', 'Knowledge Bot', 'Persona Builder'],
    tagPool: ['chat', 'support', 'sales', 'knowledge', 'persona', 'handoff'],
    prefixPool: ['Echo', 'Nova', 'Pulse', 'Halo', 'Relay', 'Vibe', 'Signal', 'Lumen', 'Apex', 'Persona'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Conversational assistants for every channel.',
  },
  'ai-cognitive': {
    title: 'AI Cognitive',
    count: 15,
    modules: ['Decision Trees', 'Reasoning Stack', 'Insight Engine', 'Risk Radar'],
    tagPool: ['reasoning', 'decisions', 'insights', 'risk', 'analysis', 'strategy'],
    prefixPool: ['Mind', 'Apex', 'Nova', 'Logic', 'Pulse', 'Beacon', 'Signal', 'Cortex', 'Lumen', 'Vector'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Decision intelligence and reasoning layers.',
  },
  'ai-enterprise': {
    title: 'AI Enterprise',
    count: 15,
    modules: ['Ops Copilot', 'Revenue Planner', 'Customer 360', 'Forecast Lab'],
    tagPool: ['enterprise', 'ops', 'forecast', 'customer', 'revenue', 'governance'],
    prefixPool: ['Summit', 'Atlas', 'Beacon', 'Nova', 'Pulse', 'Enterprise', 'Lumen', 'Prime', 'Apex', 'Bridge'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Enterprise-grade AI platforms and governance.',
  },
  'ai-private-search': {
    title: 'AI Private Search',
    count: 15,
    modules: ['Private Search', 'Source Verifier', 'Citation Builder', 'Policy Shield'],
    tagPool: ['privacy', 'search', 'citations', 'security', 'research', 'shield'],
    prefixPool: ['Shadow', 'Cloak', 'Nova', 'Aegis', 'Silent', 'Pulse', 'Nimbus', 'Signal', 'Vanta', 'Cipher'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Privacy-first search intelligence.',
  },
  'ai-speech': {
    title: 'AI Speech & Vision',
    count: 17,
    modules: ['Speech Studio', 'Voice Tuner', 'Transcription Hub', 'Audio QA'],
    tagPool: ['speech', 'audio', 'voice', 'transcription', 'studio', 'analysis'],
    prefixPool: ['Echo', 'Voice', 'Pulse', 'Aural', 'Nova', 'Signal', 'Vox', 'Lumen', 'Nimbus', 'Aura'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Voice intelligence and speech pipelines.',
  },
  'ai-search': {
    title: 'AI Search',
    count: 15,
    modules: ['Answer Engine', 'Deep Research', 'Knowledge Graph', 'Source Map'],
    tagPool: ['search', 'research', 'citations', 'insights', 'knowledge', 'browse'],
    prefixPool: ['Query', 'Nova', 'Atlas', 'Signal', 'Pulse', 'Orbit', 'Lumen', 'Nimbus', 'Vector', 'Sage'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Next-gen search with structured answers.',
  },
  'ai-video': {
    title: 'AI Video Platform',
    count: 15,
    modules: ['Video Gen', 'Script Builder', 'Edit Suite', 'Studio Export'],
    tagPool: ['video', 'editing', 'studio', 'render', 'script', 'marketing'],
    prefixPool: ['Frame', 'Nova', 'Vivid', 'Pulse', 'Studio', 'Lumen', 'Crest', 'Orbit', 'Signal', 'Aura'],
    suffixPool: SUFFIX_POOL,
    tagline: 'Video creation pipelines for modern teams.',
  },
};

export const WORKSPACE_FEATURES: Record<string, WorkspaceFeatureConfig> = {
  ...BASE_WORKSPACE_FEATURES,
  grammarly: BASE_WORKSPACE_FEATURES['ai-writer'],
  jasper: BASE_WORKSPACE_FEATURES['ai-copywriter'],
  picsart: BASE_WORKSPACE_FEATURES['ai-photo'],
  bemyai: BASE_WORKSPACE_FEATURES['ai-vision'],
  speech: BASE_WORKSPACE_FEATURES['ai-speech'],
  privatesearch: BASE_WORKSPACE_FEATURES['ai-private-search'],
  enterprise: BASE_WORKSPACE_FEATURES['ai-enterprise'],
  cognitive: BASE_WORKSPACE_FEATURES['ai-cognitive'],
  zapier: BASE_WORKSPACE_FEATURES['ai-automations'],
  chatgpt: BASE_WORKSPACE_FEATURES['ai-chatbot'],
};

export const buildWorkspaceApps = (featureKey: string): WorkspaceApp[] => {
  const config = WORKSPACE_FEATURES[featureKey];
  if (!config) return [];
  const apps: WorkspaceApp[] = [];
  const prefixes = config.prefixPool;
  const suffixes = config.suffixPool;
  for (let i = 0; i < config.count; i += 1) {
    const prefix = prefixes[i % prefixes.length];
    const suffix = suffixes[Math.floor(i / prefixes.length) % suffixes.length];
    const name = `${prefix}${suffix}`;
    const tags = [
      config.tagPool[i % config.tagPool.length],
      config.tagPool[(i + 2) % config.tagPool.length],
      config.tagPool[(i + 4) % config.tagPool.length],
    ];
    apps.push({
      id: `${featureKey}-${i}`,
      name,
      tagline: config.tagline,
      tags,
    });
  }
  return apps;
};
