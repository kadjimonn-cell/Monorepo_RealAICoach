import React, { useMemo } from 'react';
import PublicPageShell from '../src/components/PublicPageLayout';
import { StaticContentSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { TrustCenterTemplate } from '../src/components/legal/TrustCenterTemplate';
import { useTranslation } from '../src/hooks/useTranslation';

const HERO_IMAGE = 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1600&q=80';

export default function TermsPage() {
  const { t } = useTranslation();
  t('i18n.route.terms.probe');
  const pageReady = usePageReady();

  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const familyLinks = useMemo(() => [
    { id: 'privacy', label: tx('trustCenter.family.privacy', 'Privacy'), href: '/privacy-policy' },
    { id: 'terms', label: tx('trustCenter.family.terms', 'Terms'), href: '/terms', active: true },
    { id: 'security', label: tx('trustCenter.family.security', 'Security'), href: '/security' },
    { id: 'gdpr', label: tx('trustCenter.family.gdpr', 'GDPR'), href: '/gdpr' },
    { id: 'cookies', label: tx('trustCenter.family.cookies', 'Cookies'), href: '/cookies' },
  ], [tx]);

  const sections = useMemo(() => [
    {
      id: 'acceptance',
      icon: 'document-text-outline' as const,
      title: tx('termsCenter.section.acceptance.title', 'Acceptance and scope'),
      summary: tx('termsCenter.section.acceptance.summary', 'The legal agreement that governs access to the platform, subscriptions, and service use.'),
      paragraphs: [
        tx('termsCenter.section.acceptance.p1', 'These Terms of Service govern your access to RealAICoach, including public pages, authenticated product surfaces, subscription workflows, AI features, support operations, and connected service experiences.'),
        tx('termsCenter.section.acceptance.p2', 'By accessing or using the platform, you agree to these Terms, our Privacy Policy, and any product-specific notices that apply to the features you choose to use.'),
      ],
      bullets: [
        tx('termsCenter.section.acceptance.b1', 'Applies to visitors, registered users, subscribers, and trial users'),
        tx('termsCenter.section.acceptance.b2', 'Works alongside privacy, security, and data-rights commitments'),
        tx('termsCenter.section.acceptance.b3', 'Sets the baseline contract before paid or authenticated use begins'),
      ],
    },
    {
      id: 'account',
      icon: 'person-circle-outline' as const,
      title: tx('termsCenter.section.account.title', 'Accounts, identity, and user responsibilities'),
      summary: tx('termsCenter.section.account.summary', 'You must provide accurate information, protect your credentials, and use the platform lawfully.'),
      paragraphs: [
        tx('termsCenter.section.account.p1', 'You are responsible for maintaining the accuracy of your account information, controlling access to your credentials, and ensuring activity under your account complies with applicable law and these Terms.'),
        tx('termsCenter.section.account.p2', 'We may suspend or restrict access where misuse, abuse, fraud risk, or security issues threaten the platform, other users, or our service providers.'),
      ],
      facts: [
        { label: tx('termsCenter.table.account.identity', 'Identity accuracy'), value: tx('termsCenter.table.account.identityValue', 'Use current and truthful registration information') },
        { label: tx('termsCenter.table.account.security', 'Credential security'), value: tx('termsCenter.table.account.securityValue', 'Protect passwords, passkeys, and linked provider access') },
        { label: tx('termsCenter.table.account.behavior', 'Acceptable behavior'), value: tx('termsCenter.table.account.behaviorValue', 'No unlawful use, abuse, scraping, or harmful automation') },
      ],
    },
    {
      id: 'commercial',
      icon: 'card-outline' as const,
      title: tx('termsCenter.section.commercial.title', 'Subscriptions, billing, and commercial terms'),
      summary: tx('termsCenter.section.commercial.summary', 'Explains paid access, recurring billing, plan limits, and what changes when you upgrade or cancel.'),
      paragraphs: [
        tx('termsCenter.section.commercial.p1', 'Some services require an active paid plan. Pricing, renewal cadence, and plan entitlements are disclosed before purchase. Continued paid use depends on valid billing status and compliance with route access rules.'),
        tx('termsCenter.section.commercial.p2', 'If billing fails, access may be limited or suspended according to the applicable plan contract and payment recovery workflow. Canceling a subscription stops future billing but may not retroactively refund prior periods unless required by law or policy.'),
      ],
      bullets: [
        tx('termsCenter.section.commercial.b1', 'Recurring subscriptions continue until canceled'),
        tx('termsCenter.section.commercial.b2', 'Plan-specific feature access is enforced at platform level'),
        tx('termsCenter.section.commercial.b3', 'Billing, refunds, and recovery flows may involve trusted payment processors'),
      ],
    },
    {
      id: 'ai',
      icon: 'sparkles-outline' as const,
      title: tx('termsCenter.section.ai.title', 'AI usage, outputs, and platform limitations'),
      summary: tx('termsCenter.section.ai.summary', 'AI features are designed to assist, not replace, professional judgment, legal review, or critical decision-making.'),
      paragraphs: [
        tx('termsCenter.section.ai.p1', 'AI-generated outputs may be incomplete, inaccurate, or unsuitable for your exact use case. You remain responsible for reviewing and validating outputs before relying on them for legal, financial, compliance, medical, or safety-critical decisions.'),
        tx('termsCenter.section.ai.p2', 'We may refine prompts, delivery patterns, guardrails, and feature behavior to improve reliability, reduce abuse, or meet legal and platform requirements over time.'),
      ],
      facts: [
        { label: tx('termsCenter.table.ai.role', 'AI role'), value: tx('termsCenter.table.ai.roleValue', 'Assistive product intelligence, not guaranteed professional advice') },
        { label: tx('termsCenter.table.ai.review', 'User duty'), value: tx('termsCenter.table.ai.reviewValue', 'Validate outputs before operational or legal reliance') },
        { label: tx('termsCenter.table.ai.controls', 'Guardrails'), value: tx('termsCenter.table.ai.controlsValue', 'Rate limits, policy enforcement, and feature gating may apply') },
      ],
    },
    {
      id: 'liability',
      icon: 'shield-half-outline' as const,
      title: tx('termsCenter.section.liability.title', 'Liability, termination, and governing law'),
      summary: tx('termsCenter.section.liability.summary', 'Describes the risk boundary of the service, account suspension powers, and the governing legal framework.'),
      paragraphs: [
        tx('termsCenter.section.liability.p1', 'To the extent permitted by law, RealAICoach is not liable for indirect, consequential, incidental, or speculative damages arising from platform use, interruptions, or dependence on AI-generated outputs.'),
        tx('termsCenter.section.liability.p2', 'We may suspend or terminate access for violations, abuse, security risk, or legal necessity. These Terms are governed by the laws of Texas, USA, unless a specific local right overrides that baseline.'),
      ],
      bullets: [
        tx('termsCenter.section.liability.b1', 'We can restrict access for fraud, abuse, or severe policy violations'),
        tx('termsCenter.section.liability.b2', 'Platform availability is not guaranteed to be uninterrupted at all times'),
        tx('termsCenter.section.liability.b3', 'Questions or disputes can be escalated through legal and support channels'),
      ],
    },
  ], [tx]);

  if (!pageReady) {
    return <PublicPageShell maxWidth={1320} testID="terms-center-shell"><StaticContentSkeleton /></PublicPageShell>;
  }

  return (
    <PublicPageShell maxWidth={1320} testID="terms-center-shell">
      <TrustCenterTemplate
        testIdPrefix="terms-center"
        heroImage={HERO_IMAGE}
        heroImageAlt={tx('termsCenter.hero.imageAlt', 'Abstract contract and trust background')}
        badge={tx('termsCenter.hero.badge', 'TERMS TRUST CENTER')}
        version={tx('termsCenter.hero.version', 'Version 2026.2')}
        title={tx('termsCenter.hero.title', 'Terms that explain the product clearly — before they protect it legally.')}
        subtitle={tx('termsCenter.hero.subtitle', 'This trust-centered Terms experience makes it easier to understand platform responsibilities, subscription boundaries, and how AI usage fits into the product contract.')}
        metaItems={[
          tx('termsCenter.hero.meta.updated', 'Last updated: March 20, 2026'),
          tx('termsCenter.hero.meta.effective', 'Effective: March 20, 2026'),
          tx('termsCenter.hero.meta.notice', 'Material legal updates may be communicated by product and email notice'),
        ]}
        heroPrimaryCta={{ label: tx('termsCenter.hero.cta.reviewPlans', 'Review Plans'), href: '/pricing', testId: 'terms-center-review-plans-cta' }}
        heroSecondaryCta={{ label: tx('termsCenter.hero.cta.contact', 'Contact Legal Team'), href: '/help', testId: 'terms-center-contact-cta' }}
        familyLinks={familyLinks}
        summaryTitle={tx('termsCenter.summary.title', 'TL;DR — the contract in practical terms')}
        trustFacts={[
          { id: 'scope', title: tx('termsCenter.fact.scope.title', 'What this governs'), body: tx('termsCenter.fact.scope.body', 'Account use, subscriptions, AI workflows, and platform responsibilities.'), icon: 'layers-outline' },
          { id: 'billing', title: tx('termsCenter.fact.billing.title', 'Commercial boundary'), body: tx('termsCenter.fact.billing.body', 'Paid plans unlock additional access and remain subject to billing status and platform gating.'), icon: 'card-outline' },
          { id: 'ai', title: tx('termsCenter.fact.ai.title', 'AI caveat'), body: tx('termsCenter.fact.ai.body', 'AI outputs assist your work but still require human review and judgment.'), icon: 'sparkles-outline' },
          { id: 'enforcement', title: tx('termsCenter.fact.enforcement.title', 'Policy enforcement'), body: tx('termsCenter.fact.enforcement.body', 'We can limit or suspend use to protect the service, users, and compliance posture.'), icon: 'shield-checkmark-outline' },
        ]}
        changeLogTitle={tx('termsCenter.changelog.title', 'What changed in this Terms experience')}
        changeLogItems={[
          tx('termsCenter.changelog.1', 'Clarified subscription enforcement and product-access boundaries.'),
          tx('termsCenter.changelog.2', 'Expanded AI usage disclaimers into a more practical operator-facing explanation.'),
          tx('termsCenter.changelog.3', 'Aligned legal, privacy, and support pathways into a unified trust-center family.'),
        ]}
        trustPanelTitle={tx('termsCenter.trustPanel.title', 'What this means for you')}
        trustPanelItems={[
          tx('termsCenter.trustPanel.item1', 'You can understand the service contract faster before choosing a plan.'),
          tx('termsCenter.trustPanel.item2', 'Subscription rules, AI usage boundaries, and account duties are now more explicit.'),
          tx('termsCenter.trustPanel.item3', 'Legal surfaces now connect more clearly to privacy, security, and support actions.'),
        ]}
        sidebarTitle={tx('termsCenter.sidebar.title', 'Navigate these Terms')}
        sidebarSearchPlaceholder={tx('termsCenter.sidebar.search', 'Search Terms')}
        sidebarCtaTitle={tx('termsCenter.sidebar.ctaTitle', 'Need contract or billing clarity?')}
        sidebarCtaBody={tx('termsCenter.sidebar.ctaBody', 'Review pricing, contact support, or compare the related legal trust pages before you proceed.')}
        sidebarCtaLabel={tx('termsCenter.sidebar.ctaButton', 'Open Help & Support')}
        sidebarCtaHref="/help"
        sections={sections}
        pinSectionLabel={tx('termsCenter.section.focus', 'Pin section')}
        actionHubTitle={tx('termsCenter.actionHub.title', 'Take the next step with context, not guesswork')}
        actionHubSubtitle={tx('termsCenter.actionHub.subtitle', 'From pricing review to privacy follow-up, these actions keep the legal and commercial journey connected.')}
        actionHubOpenLabel={tx('termsCenter.actionHub.open', 'Open flow')}
        actionCards={[
          { id: 'pricing', title: tx('termsCenter.actions.pricing.title', 'Review plan terms'), body: tx('termsCenter.actions.pricing.body', 'See how plan-level access and billing fit the legal agreement.'), icon: 'pricetags-outline', href: '/pricing' },
          { id: 'privacy', title: tx('termsCenter.actions.privacy.title', 'Review privacy commitments'), body: tx('termsCenter.actions.privacy.body', 'Move from contract language into the Privacy Trust Center and data-rights actions.'), icon: 'shield-checkmark-outline', href: '/privacy-policy' },
          { id: 'support', title: tx('termsCenter.actions.support.title', 'Contact support or legal'), body: tx('termsCenter.actions.support.body', 'Escalate billing, legal, or usage questions with product context attached.'), icon: 'mail-open-outline', href: '/help' },
        ]}
        contactTitle={tx('termsCenter.contact.title', 'Questions, disputes, or legal clarification')}
        contactBody={tx('termsCenter.contact.body', 'If you need help understanding plan obligations, AI usage limits, or your legal relationship to the service, contact our support or legal operations pathway.')}
        contactItems={[
          { id: 'legal', label: tx('termsCenter.contact.legal', 'legal@realaicoach.app'), icon: 'mail-outline' },
          { id: 'support', label: tx('termsCenter.contact.support', 'Help & Support workspace'), icon: 'help-buoy-outline' },
          { id: 'billing', label: tx('termsCenter.contact.billing', 'Billing and subscription workflows remain linked to these Terms'), icon: 'card-outline' },
        ]}
      />
    </PublicPageShell>
  );
}