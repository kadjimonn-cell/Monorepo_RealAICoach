export type PressCategory = 'Announcements' | 'Funding' | 'Enterprise' | 'Product';

export type PressArticle = {
  slug: string;
  title: string;
  date_label: string;
  published_at: string;
  category: PressCategory;
  source: string;
  excerpt: string;
  angle: string;
  seo_description: string;
  key_points: string[];
  body: string[];
};

export const PRESS_CATEGORY_FILTERS: ('All' | PressCategory)[] = [
  'All',
  'Announcements',
  'Funding',
  'Enterprise',
  'Product',
];

export const PRESS_ARTICLES: PressArticle[] = [
  {
    slug: 'active-users-global-expansion-2026',
    title: 'RealAICoach Surpasses 857,000 Active Users, Expands to 140+ Countries',
    date_label: 'February 15, 2026',
    published_at: '2026-02-15T09:00:00.000Z',
    category: 'Announcements',
    source: 'RealAICoach Newsroom',
    excerpt: 'RealAICoach reached 857,000 active users across 140+ countries, accelerating its mission to democratize professional growth at enterprise scale.',
    angle: 'Global momentum and adoption velocity across enterprise and professional cohorts.',
    seo_description: 'RealAICoach announces 857,000 active users and expansion to 140+ countries, highlighting strong enterprise adoption and market momentum.',
    key_points: [
      '857,000+ active users worldwide',
      'Presence in 140+ countries',
      'Strong enterprise and team adoption growth',
    ],
    body: [
      'RealAICoach announced a major growth milestone, surpassing 857,000 active users globally. The company now supports professionals and teams in more than 140 countries.',
      'This momentum reflects increased enterprise demand for AI-assisted coaching experiences that combine measurable outcomes, role-specific guidance, and operational simplicity.',
      'Leadership noted that upcoming roadmap investments will focus on deeper enterprise analytics, broader multilingual support, and stronger workflow integrations for global teams.',
    ],
  },
  {
    slug: 'enterprise-ai-coaching-suite-launch',
    title: 'RealAICoach Launches Enterprise AI Coaching Suite for L&D Teams',
    date_label: 'January 20, 2026',
    published_at: '2026-01-20T10:00:00.000Z',
    category: 'Enterprise',
    source: 'Forbes',
    excerpt: 'The new Enterprise Suite enables L&D leaders to deploy personalized coaching at scale with governance-ready analytics and controls.',
    angle: 'Enterprise enablement and measurable coaching outcomes for distributed organizations.',
    seo_description: 'RealAICoach launches enterprise AI coaching suite for L&D teams with analytics, governance controls, and scalable rollout support.',
    key_points: [
      'Enterprise-grade dashboards for coaching performance',
      'Flexible governance for compliance-driven teams',
      'Rollout support for distributed organizations',
    ],
    body: [
      'The Enterprise AI Coaching Suite gives learning teams centralized visibility into engagement, progression, and behavior trends across departments and geographies.',
      'Built-in controls support compliance-sensitive environments, enabling organizations to tailor experiences while preserving consistent standards and auditability.',
      'Early enterprise adopters report faster program activation and improved completion rates when compared with legacy coaching workflows.',
    ],
  },
  {
    slug: 'series-a-growth-acceleration',
    title: 'RealAICoach Raises Series A to Accelerate Global Expansion',
    date_label: 'December 10, 2025',
    published_at: '2025-12-10T08:30:00.000Z',
    category: 'Funding',
    source: 'VentureBeat',
    excerpt: 'The Series A round supports accelerated hiring, AI engine improvements, and deeper regional expansion across Europe and Asia.',
    angle: 'Capital-backed execution focused on product depth and global market expansion.',
    seo_description: 'RealAICoach closes Series A funding to accelerate global expansion, AI product development, and enterprise market growth.',
    key_points: [
      'Series A closed to fuel expansion',
      'Investment in core AI coaching engine',
      'Regional growth focus in Europe and Asia',
    ],
    body: [
      'RealAICoach closed its Series A financing round to expand product capabilities and strengthen market execution in strategic international regions.',
      'The company plans to scale engineering capacity, broaden enterprise onboarding resources, and accelerate delivery of advanced coaching intelligence features.',
      'Leadership confirmed the funding will be deployed with a disciplined focus on customer outcomes, platform reliability, and operational scalability.',
    ],
  },
  {
    slug: 'top-ai-startups-techcrunch-watchlist',
    title: 'RealAICoach Named “Top 10 AI Startups to Watch” by TechCrunch',
    date_label: 'November 5, 2025',
    published_at: '2025-11-05T07:45:00.000Z',
    category: 'Announcements',
    source: 'TechCrunch',
    excerpt: 'TechCrunch highlighted RealAICoach for its practical enterprise application of language models in professional development.',
    angle: 'Category recognition and market validation for applied AI coaching.',
    seo_description: 'TechCrunch names RealAICoach among top AI startups to watch, citing practical enterprise use cases and measurable outcomes.',
    key_points: [
      'Recognized by TechCrunch watchlist',
      'Praised for practical enterprise AI value',
      'Validation of category leadership trajectory',
    ],
    body: [
      'TechCrunch recognized RealAICoach as one of the top AI startups to watch, citing its execution in real-world, enterprise-ready use cases.',
      'Coverage emphasized the platform’s ability to translate AI capabilities into measurable coaching outcomes instead of novelty experiences.',
      'The recognition reinforces RealAICoach’s position as a trusted solution for organizations modernizing workforce development strategies.',
    ],
  },
  {
    slug: 'product-integration-workflow-intelligence',
    title: 'Workflow Intelligence Upgrades Improve Coaching Adoption in Daily Tools',
    date_label: 'October 14, 2025',
    published_at: '2025-10-14T09:30:00.000Z',
    category: 'Product',
    source: 'Product Update',
    excerpt: 'New workflow intelligence upgrades increase adoption by embedding contextual coaching prompts into day-to-day execution paths.',
    angle: 'Product innovation aimed at reducing friction and increasing behavior change completion.',
    seo_description: 'RealAICoach product update introduces workflow intelligence upgrades to improve coaching adoption and execution consistency.',
    key_points: [
      'Contextual prompts aligned with daily workflows',
      'Lower friction from guidance to action',
      'Higher completion in pilot cohorts',
    ],
    body: [
      'RealAICoach introduced workflow intelligence upgrades designed to place contextual coaching prompts directly where users make decisions and execute work.',
      'The update reduces handoff friction between planning and action, helping teams sustain momentum and turn guidance into repeatable behavior.',
      'Internal pilot data showed improved completion and follow-through rates in cohorts using the upgraded workflow surface.',
    ],
  },
  {
    slug: 'enterprise-sso-and-governance-controls',
    title: 'Enterprise SSO and Governance Controls Expanded for Regulated Teams',
    date_label: 'September 2, 2025',
    published_at: '2025-09-02T08:15:00.000Z',
    category: 'Enterprise',
    source: 'Enterprise Brief',
    excerpt: 'Enhanced SSO and governance controls improve compliance-readiness for teams operating in highly regulated environments.',
    angle: 'Platform readiness for organizations requiring strict access, policy, and oversight controls.',
    seo_description: 'RealAICoach expands enterprise SSO and governance controls to better support regulated environments and compliance operations.',
    key_points: [
      'Expanded identity and access control options',
      'Improved policy enforcement controls',
      'Better fit for regulated operational contexts',
    ],
    body: [
      'RealAICoach expanded enterprise identity and governance capabilities to support organizations with complex compliance requirements.',
      'Enhancements include broader SSO compatibility, stronger access boundaries, and improved control surfaces for operational administrators.',
      'The release strengthens readiness for regulated industries that require clear oversight, traceability, and policy consistency.',
    ],
  },
];

export function getPressArticleBySlug(slug: string): PressArticle | null {
  const normalized = String(slug || '').trim().toLowerCase();
  if (!normalized) return null;
  return PRESS_ARTICLES.find((item) => item.slug === normalized) || null;
}

export function listPressArticlesByCategory(category: 'All' | PressCategory): PressArticle[] {
  const sorted = [...PRESS_ARTICLES].sort((a, b) => String(b.published_at).localeCompare(String(a.published_at)));
  if (category === 'All') return sorted;
  return sorted.filter((item) => item.category === category);
}

export function getLatestMediaMentions(limit: number = 5): PressArticle[] {
  return listPressArticlesByCategory('All').slice(0, Math.max(1, Math.min(limit, 12)));
}
