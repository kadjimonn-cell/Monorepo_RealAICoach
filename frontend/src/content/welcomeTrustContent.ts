export type WelcomeFaqEntry = {
  question: string;
  answer: string;
  category: string;
  lang?: string;
};

export type WelcomeTestimonialEntry = {
  name: string;
  role: string;
  company: string;
  rating: number;
  quote: string;
  outcome: string;
  segment: string;
  seeded?: boolean;
  source: 'gps' | 'fallback';
};

export const FALLBACK_WELCOME_FAQ: WelcomeFaqEntry[] = [
  { category: 'Getting Started', question: 'How quickly can we launch the platform for a new team?', answer: 'Most teams launch in less than one week using guided onboarding, role templates, and readiness checklists.' },
  { category: 'Getting Started', question: 'Can we run a pilot before company-wide rollout?', answer: 'Yes. You can launch a scoped pilot with selected departments, then promote successful journeys to broader teams.' },
  { category: 'Pricing', question: 'Is there a free trial before committing to a paid plan?', answer: 'Yes. Teams can start with a free trial to validate adoption, engagement, and outcome quality before upgrading.' },
  { category: 'Pricing', question: 'Do you support annual billing and procurement workflows?', answer: 'Yes. Annual plans, procurement support, and enterprise invoicing are available for larger organizations.' },
  { category: 'Pricing', question: 'Can we adjust seats as our team grows?', answer: 'Absolutely. Seat allocation can be scaled up or down as teams evolve, with transparent billing visibility.' },
  { category: 'Security', question: 'How is customer data protected at rest and in transit?', answer: 'All sensitive traffic is encrypted in transit and protected at rest with strict access controls and operational guardrails.' },
  { category: 'Security', question: 'Do you provide role-based access controls for admins?', answer: 'Yes. Admin controls support scoped permissions for operations, analytics, and platform governance roles.' },
  { category: 'Security', question: 'Can we enforce internal policy controls and content boundaries?', answer: 'Yes. You can apply policy-aware constraints and governance controls aligned with organizational requirements.' },
  { category: 'Compliance', question: 'How does the platform support compliance-focused teams?', answer: 'The platform includes auditable activity tracking, operational diagnostics, and controls designed for compliance workflows.' },
  { category: 'Compliance', question: 'Can legal and security teams review platform behavior?', answer: 'Yes. Governance logs and diagnostics provide transparency for internal risk, legal, and security stakeholders.' },
  { category: 'Integrations', question: 'Can we integrate this with existing tools and workflows?', answer: 'Yes. Integration patterns support common collaboration and operational ecosystems used by modern teams.' },
  { category: 'Integrations', question: 'Do you support SSO and enterprise authentication patterns?', answer: 'Enterprise environments can use standardized authentication patterns for secure access and lifecycle control.' },
  { category: 'Integrations', question: 'Can we connect platform usage to internal analytics?', answer: 'Yes. Teams can operationalize platform insights alongside internal metrics to track adoption and outcomes.' },
  { category: 'Performance', question: 'How do you ensure platform reliability during peak usage?', answer: 'System safeguards and live diagnostics are designed to maintain responsiveness and operational stability.' },
  { category: 'Performance', question: 'What metrics should leaders track for success?', answer: 'Most teams track activation velocity, journey completion, behavior consistency, and team-level performance shifts.' },
  { category: 'Adoption', question: 'How do you make the experience sticky for users?', answer: 'Role-aware prompts, contextual journeys, and progressive milestone feedback help sustain recurring engagement.' },
  { category: 'Adoption', question: 'Can managers monitor team progress without micromanaging?', answer: 'Yes. Aggregated analytics provide strategic visibility while preserving healthy autonomy at the individual level.' },
  { category: 'Support', question: 'What support model is available for enterprise customers?', answer: 'Enterprise customers get priority support paths, guided onboarding assistance, and strategic success check-ins.' },
  { category: 'Support', question: 'Can we request custom enablement sessions for our teams?', answer: 'Yes. Enablement sessions can be tailored for functional roles, leadership cohorts, and rollout phases.' },
  { category: 'Roadmap', question: 'How frequently are features and guidance models improved?', answer: 'Enhancements are shipped continuously, with quality controls to maintain reliability and user trust.' },
  { category: 'ROI', question: 'How do customers justify subscription value internally?', answer: 'Customers typically measure reduced coaching friction, improved completion rates, and stronger performance outcomes.' },
  { category: 'ROI', question: 'Can we align the platform to department-specific goals?', answer: 'Yes. Journeys and insights can be adapted to leadership, IC, and cross-functional outcomes.' },
];

export const FALLBACK_WELCOME_TESTIMONIALS: WelcomeTestimonialEntry[] = [
  { source: 'fallback', seeded: true, name: 'Sophia Bennett', role: 'Director of L&D', company: 'Northbridge Financial', rating: 5, segment: 'L&D', outcome: '42% faster onboarding readiness', quote: 'RealAICoach helped us standardize coaching quality across regions without slowing team execution.' },
  { source: 'fallback', seeded: true, name: 'Daniel Kim', role: 'VP People Operations', company: 'Vertex Systems', rating: 5, segment: 'People Ops', outcome: '31% improvement in manager follow-through', quote: 'The platform turned coaching from an ad-hoc activity into a repeatable operating rhythm.' },
  { source: 'fallback', seeded: true, name: 'Amelia Rivera', role: 'Chief Operating Officer', company: 'Aquila Commerce', rating: 5, segment: 'Executive', outcome: '28% increase in team execution velocity', quote: 'We finally have visibility into behavior change, not just completion metrics.' },
  { source: 'fallback', seeded: true, name: 'Marcus Holt', role: 'Head of Revenue Enablement', company: 'Peakline SaaS', rating: 5, segment: 'Revenue', outcome: '35% uplift in ramp consistency', quote: 'Coaching moments now happen in workflow, exactly where reps need support.' },
  { source: 'fallback', seeded: true, name: 'Priya Nair', role: 'Global Program Manager', company: 'Helios Manufacturing', rating: 5, segment: 'Program', outcome: '47% more cross-team completion', quote: 'The guided journeys made complex initiatives easier to execute across departments.' },
  { source: 'fallback', seeded: true, name: 'Noah Alvarez', role: 'Head of Customer Success', company: 'Brightwell Cloud', rating: 5, segment: 'Customer Success', outcome: '24% improvement in retention-focused coaching', quote: 'Our CSM teams now get practical prompts tied directly to business outcomes.' },
  { source: 'fallback', seeded: true, name: 'Elena Novak', role: 'Chief Compliance Officer', company: 'Stratos Health', rating: 5, segment: 'Compliance', outcome: 'Audit prep time reduced by 33%', quote: 'The governance and diagnostics layer gave our risk team confidence from day one.' },
  { source: 'fallback', seeded: true, name: 'Jared Collins', role: 'Engineering Director', company: 'SignalForge', rating: 5, segment: 'Engineering', outcome: '26% faster project handoff quality', quote: 'The coaching workflows improved decision clarity across technical leads.' },
  { source: 'fallback', seeded: true, name: 'Mina Park', role: 'Head of Talent Strategy', company: 'Silverline Retail Group', rating: 5, segment: 'Talent', outcome: '39% increase in growth-path engagement', quote: 'Employees actually return to the platform because the guidance feels timely and relevant.' },
  { source: 'fallback', seeded: true, name: 'Oliver Grant', role: 'Regional Operations Lead', company: 'Nexon Logistics', rating: 5, segment: 'Operations', outcome: '30% increase in execution predictability', quote: 'This is one of the few platforms our teams genuinely adopted without enforcement.' },
];

function normalizeString(value: unknown): string {
  return String(value || '').trim();
}

function normalizeCategory(value: unknown): string {
  const raw = normalizeString(value);
  return raw || 'General';
}

export function buildCanonicalWelcomeFaq(rawFaq: any[], languageCode: string, minCount: number = 20): WelcomeFaqEntry[] {
  const list = Array.isArray(rawFaq) ? rawFaq : [];
  const normalizedLang = String(languageCode || 'en').toLowerCase();
  const activeFaq = list.filter((item) => item?.active !== false);

  const localized = activeFaq.filter((item) => {
    const lang = normalizeString(item?.lang || 'en').toLowerCase();
    return lang === normalizedLang;
  });

  const englishFallback = activeFaq.filter((item) => {
    const lang = normalizeString(item?.lang || 'en').toLowerCase();
    return lang === 'en';
  });

  const primary = localized.length > 0 ? localized : englishFallback;
  const gpsNormalized: WelcomeFaqEntry[] = primary
    .map((item) => {
      const question = normalizeString(item?.question);
      const answer = normalizeString(item?.answer);
      if (!question || !answer) return null;
      return {
        question,
        answer,
        category: normalizeCategory(item?.category || item?.topic || item?.group),
        lang: normalizeString(item?.lang || 'en').toLowerCase(),
      } as WelcomeFaqEntry;
    })
    .filter(Boolean) as WelcomeFaqEntry[];

  const merged = [...gpsNormalized, ...FALLBACK_WELCOME_FAQ];
  const seen = new Set<string>();
  const deduped: WelcomeFaqEntry[] = [];
  merged.forEach((item) => {
    const key = normalizeString(item.question).toLowerCase();
    if (!key || seen.has(key)) return;
    seen.add(key);
    deduped.push(item);
  });

  if (deduped.length >= minCount) {
    return deduped;
  }

  return [...deduped, ...FALLBACK_WELCOME_FAQ].slice(0, minCount);
}

export function buildCanonicalWelcomeTestimonials(rawTestimonials: any[], minCount: number = 10): WelcomeTestimonialEntry[] {
  const list = Array.isArray(rawTestimonials) ? rawTestimonials : [];
  const gpsNormalized: WelcomeTestimonialEntry[] = list
    .map((item) => {
      const name = normalizeString(item?.name);
      const quote = normalizeString(item?.quote || item?.text);
      if (!name || !quote) return null;
      const role = normalizeString(item?.role || 'Team Lead');
      const company = normalizeString(item?.company || 'Enterprise Customer');
      const ratingRaw = Number(item?.rating || 5);
      const rating = Number.isFinite(ratingRaw) ? Math.max(1, Math.min(5, Math.round(ratingRaw))) : 5;
      return {
        source: 'gps',
        seeded: Boolean(item?.seeded),
        name,
        role,
        company,
        rating,
        quote,
        outcome: normalizeString(item?.outcome || 'Improved team consistency and execution quality'),
        segment: normalizeString(item?.segment || item?.persona || role || 'General'),
      } as WelcomeTestimonialEntry;
    })
    .filter(Boolean) as WelcomeTestimonialEntry[];

  const merged = [...gpsNormalized, ...FALLBACK_WELCOME_TESTIMONIALS];
  const seen = new Set<string>();
  const deduped: WelcomeTestimonialEntry[] = [];
  merged.forEach((item) => {
    const key = `${normalizeString(item.name).toLowerCase()}|${normalizeString(item.quote).toLowerCase()}`;
    if (!key || seen.has(key)) return;
    seen.add(key);
    deduped.push(item);
  });

  if (deduped.length >= minCount) {
    return deduped;
  }

  return [...deduped, ...FALLBACK_WELCOME_TESTIMONIALS].slice(0, minCount);
}
