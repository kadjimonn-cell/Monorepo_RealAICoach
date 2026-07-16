import React, { useMemo } from 'react';
import PublicPageShell from '../src/components/PublicPageLayout';
import { StaticContentSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { TrustCenterTemplate } from '../src/components/legal/TrustCenterTemplate';
import { useTranslation } from '../src/hooks/useTranslation';

const HERO_IMAGE = 'https://images.unsplash.com/photo-1510511459019-5dda7724fd87?auto=format&fit=crop&w=1600&q=80';

export default function CookiePolicyPage() {
  const { t } = useTranslation();
  t('i18n.route.cookies.probe');
  const pageReady = usePageReady();

  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const familyLinks = useMemo(() => [
    { id: 'privacy', label: tx('trustCenter.family.privacy', 'Privacy'), href: '/privacy-policy' },
    { id: 'terms', label: tx('trustCenter.family.terms', 'Terms'), href: '/terms' },
    { id: 'security', label: tx('trustCenter.family.security', 'Security'), href: '/security' },
    { id: 'gdpr', label: tx('trustCenter.family.gdpr', 'GDPR'), href: '/gdpr' },
    { id: 'cookies', label: tx('trustCenter.family.cookies', 'Cookies'), href: '/cookies', active: true },
  ], [tx]);

  const sections = useMemo(() => [
    {
      id: 'overview',
      icon: 'browsers-outline' as const,
      title: tx('cookieCenter.section.overview.title', 'What cookies are and why they exist'),
      summary: tx('cookieCenter.section.overview.summary', 'A clear explanation of how cookies, local storage, and device preferences support authentication, usability, and trust continuity.'),
      paragraphs: [
        tx('cookieCenter.section.overview.p1', 'Cookies and similar browser storage technologies help RealAICoach keep sessions secure, remember selected preferences, maintain language and theme continuity, and understand aggregate service behavior.'),
        tx('cookieCenter.section.overview.p2', 'We aim to explain cookies in practical terms so users can understand what is essential for the service to function, what is optional, and how browser-level control affects the product experience.'),
      ],
      bullets: [
        tx('cookieCenter.section.overview.b1', 'Includes cookies, local storage, and preference-related browser data'),
        tx('cookieCenter.section.overview.b2', 'Separates essential service continuity from optional preference or measurement use'),
        tx('cookieCenter.section.overview.b3', 'Connects cookie explanations to privacy and legal trust surfaces'),
      ],
    },
    {
      id: 'types',
      icon: 'layers-outline' as const,
      title: tx('cookieCenter.section.types.title', 'The categories of cookies we use'),
      summary: tx('cookieCenter.section.types.summary', 'Authentication, preference, consent, and limited measurement categories each serve a different purpose.'),
      paragraphs: [
        tx('cookieCenter.section.types.p1', 'Some cookies are essential for signing in, maintaining your session, and protecting the platform. Others help remember settings such as language and theme. Certain limited analytics or preference tools may also rely on browser storage.'),
        tx('cookieCenter.section.types.p2', 'We try to keep cookie usage proportionate and explainable so the Cookie Policy remains useful to real users instead of becoming a technical appendix no one can act on.'),
      ],
      facts: [
        { label: tx('cookieCenter.table.types.session', 'Session/authentication'), value: tx('cookieCenter.table.types.sessionValue', 'Supports sign-in continuity, route access, and verified session state') },
        { label: tx('cookieCenter.table.types.preferences', 'Preferences'), value: tx('cookieCenter.table.types.preferencesValue', 'Remembers theme, language, and selected display preferences') },
        { label: tx('cookieCenter.table.types.consent', 'Consent records'), value: tx('cookieCenter.table.types.consentValue', 'Stores privacy/cookie consent state and related trust choices') },
        { label: tx('cookieCenter.table.types.measurement', 'Service measurement'), value: tx('cookieCenter.table.types.measurementValue', 'Helps us understand aggregate service use and reliability patterns') },
      ],
    },
    {
      id: 'controls',
      icon: 'settings-outline' as const,
      title: tx('cookieCenter.section.controls.title', 'How you can manage cookies and preferences'),
      summary: tx('cookieCenter.section.controls.summary', 'Users can control cookies through browser settings and platform preference surfaces, though blocking some categories can change product behavior.'),
      paragraphs: [
        tx('cookieCenter.section.controls.p1', 'You can usually review, block, or delete cookies through your browser settings. You can also manage some platform-level preferences directly through product settings or privacy-control surfaces.'),
        tx('cookieCenter.section.controls.p2', 'Blocking essential cookies may affect sign-in, route continuity, localization, or security workflows. We therefore explain the consequences rather than presenting cookie controls as consequence-free toggles.'),
      ],
      bullets: [
        tx('cookieCenter.section.controls.b1', 'Use browser controls to clear or block stored cookies'),
        tx('cookieCenter.section.controls.b2', 'Use platform settings and privacy pathways for theme/language or consent-related preferences'),
        tx('cookieCenter.section.controls.b3', 'Review Privacy Policy and GDPR pages for related data-rights implications'),
      ],
    },
    {
      id: 'third-party',
      icon: 'git-network-outline' as const,
      title: tx('cookieCenter.section.thirdParty.title', 'Third-party and connected-service implications'),
      summary: tx('cookieCenter.section.thirdParty.summary', 'Some third-party service providers and connected experiences may rely on their own controlled storage or consent-related behavior.'),
      paragraphs: [
        tx('cookieCenter.section.thirdParty.p1', 'Where third-party infrastructure, payments, analytics, or connected-service providers are used, they may set or rely on browser storage according to their limited operational role. We aim to avoid hidden or unexplained dependency chains.'),
        tx('cookieCenter.section.thirdParty.p2', 'Connected services such as Google-linked experiences should always be understood alongside the Privacy Policy, because cookies and tokens can work together to preserve authenticated workflows.'),
      ],
      facts: [
        { label: tx('cookieCenter.table.thirdParty.infrastructure', 'Infrastructure'), value: tx('cookieCenter.table.thirdParty.infrastructureValue', 'Hosting, session continuity, and reliability support') },
        { label: tx('cookieCenter.table.thirdParty.payments', 'Payments'), value: tx('cookieCenter.table.thirdParty.paymentsValue', 'Payment and billing processors may rely on secure browser/session continuity') },
        { label: tx('cookieCenter.table.thirdParty.connected', 'Connected services'), value: tx('cookieCenter.table.thirdParty.connectedValue', 'Some connected workflows may pair browser state with provider authorization state') },
      ],
    },
  ], [tx]);

  if (!pageReady) {
    return <PublicPageShell maxWidth={1320} testID="cookie-center-shell"><StaticContentSkeleton /></PublicPageShell>;
  }

  return (
    <PublicPageShell maxWidth={1320} testID="cookie-center-shell">
      <TrustCenterTemplate
        testIdPrefix="cookie-center"
        heroImage={HERO_IMAGE}
        heroImageAlt={tx('cookieCenter.hero.imageAlt', 'Abstract browser privacy and preference background')}
        badge={tx('cookieCenter.hero.badge', 'COOKIE TRUST CENTER')}
        version={tx('cookieCenter.hero.version', 'Version 2026.2')}
        title={tx('cookieCenter.hero.title', 'Cookie Policy that explains trade-offs clearly, not just consent mechanics.')}
        subtitle={tx('cookieCenter.hero.subtitle', 'This page explains the browser-level technologies that keep sessions secure, preferences persistent, and trust choices understandable across the platform.')}
        metaItems={[
          tx('cookieCenter.hero.meta.updated', 'Last updated: March 20, 2026'),
          tx('cookieCenter.hero.meta.scope', 'Covers cookies, browser storage, and preference continuity'),
          tx('cookieCenter.hero.meta.linkage', 'Connected to Privacy, Security, and GDPR trust pages'),
        ]}
        heroPrimaryCta={{ label: tx('cookieCenter.hero.cta.privacy', 'Review Privacy Policy'), href: '/privacy-policy', testId: 'cookie-center-privacy-cta' }}
        heroSecondaryCta={{ label: tx('cookieCenter.hero.cta.manage', 'Manage My Data'), href: '/privacy-request', testId: 'cookie-center-manage-data-cta' }}
        familyLinks={familyLinks}
        summaryTitle={tx('cookieCenter.summary.title', 'TL;DR — what cookies mean here')}
        trustFacts={[
          { id: 'essential', title: tx('cookieCenter.fact.essential.title', 'Essential continuity'), body: tx('cookieCenter.fact.essential.body', 'Some browser storage is required for sign-in, session continuity, and account safety.'), icon: 'shield-checkmark-outline' },
          { id: 'preferences', title: tx('cookieCenter.fact.preferences.title', 'Preference memory'), body: tx('cookieCenter.fact.preferences.body', 'Theme, language, and some display choices rely on preference storage.'), icon: 'color-palette-outline' },
          { id: 'consent', title: tx('cookieCenter.fact.consent.title', 'Consent records'), body: tx('cookieCenter.fact.consent.body', 'Consent-related browser state helps us respect prior trust choices.'), icon: 'document-text-outline' },
          { id: 'control', title: tx('cookieCenter.fact.control.title', 'User control'), body: tx('cookieCenter.fact.control.body', 'Browser settings and privacy flows give you meaningful control over cookie behavior.'), icon: 'settings-outline' },
        ]}
        changeLogTitle={tx('cookieCenter.changelog.title', 'What changed in this Cookie Policy experience')}
        changeLogItems={[
          tx('cookieCenter.changelog.1', 'Rebuilt Cookie Policy into the same Trust Center family as Privacy, Terms, Security, and GDPR.'),
          tx('cookieCenter.changelog.2', 'Clarified the difference between essential session continuity and optional preference storage.'),
          tx('cookieCenter.changelog.3', 'Connected cookie explanations to privacy rights and related legal trust surfaces.'),
        ]}
        trustPanelTitle={tx('cookieCenter.trustPanel.title', 'What this means for you')}
        trustPanelItems={[
          tx('cookieCenter.trustPanel.item1', 'You can understand what breaks if essential cookies are blocked.'),
          tx('cookieCenter.trustPanel.item2', 'Preference storage is explained in a user-facing way rather than buried in legal jargon.'),
          tx('cookieCenter.trustPanel.item3', 'Cookie understanding now connects cleanly to privacy and GDPR rights pages.'),
        ]}
        sidebarTitle={tx('cookieCenter.sidebar.title', 'Navigate cookie topics')}
        sidebarSearchPlaceholder={tx('cookieCenter.sidebar.search', 'Search Cookie Policy')}
        sidebarCtaTitle={tx('cookieCenter.sidebar.ctaTitle', 'Need the full data view?')}
        sidebarCtaBody={tx('cookieCenter.sidebar.ctaBody', 'Cookie controls explain browser behavior, but privacy rights and data requests live in the Privacy Trust Center and privacy workflow.')}
        sidebarCtaLabel={tx('cookieCenter.sidebar.ctaButton', 'Open Privacy Trust Center')}
        sidebarCtaHref="/privacy-policy"
        sections={sections}
        pinSectionLabel={tx('cookieCenter.section.focus', 'Pin section')}
        actionHubTitle={tx('cookieCenter.actionHub.title', 'Continue the trust journey from browser controls to data rights')}
        actionHubSubtitle={tx('cookieCenter.actionHub.subtitle', 'Users checking cookies often need the next linked trust surface immediately, so those pathways stay visible here.')}
        actionHubOpenLabel={tx('cookieCenter.actionHub.open', 'Open flow')}
        actionCards={[
          { id: 'privacy', title: tx('cookieCenter.actions.privacy.title', 'Review Privacy Policy'), body: tx('cookieCenter.actions.privacy.body', 'See how cookie behavior connects to data collection, retention, and rights.'), icon: 'shield-checkmark-outline', href: '/privacy-policy' },
          { id: 'gdpr', title: tx('cookieCenter.actions.gdpr.title', 'Review GDPR rights'), body: tx('cookieCenter.actions.gdpr.body', 'Understand the rights and lawful basis implications behind browser-level consent and storage.'), icon: 'globe-outline', href: '/gdpr' },
          { id: 'request', title: tx('cookieCenter.actions.request.title', 'Open privacy request flow'), body: tx('cookieCenter.actions.request.body', 'Export or delete personal data through the verified privacy pathway.'), icon: 'download-outline', href: '/privacy-request' },
        ]}
        contactTitle={tx('cookieCenter.contact.title', 'Cookie, consent, or browser-state questions')}
        contactBody={tx('cookieCenter.contact.body', 'If you need help understanding how browser storage affects your account, privacy controls, or sign-in continuity, use our privacy and support pathways below.')}
        contactItems={[
          { id: 'privacy', label: tx('cookieCenter.contact.privacy', 'privacy@realaicoach.app'), icon: 'mail-outline' },
          { id: 'support', label: tx('cookieCenter.contact.support', 'Help & Support workspace'), icon: 'help-buoy-outline' },
          { id: 'policy', label: tx('cookieCenter.contact.policy', 'Privacy and GDPR Trust Centers remain linked for full rights context'), icon: 'document-text-outline' },
        ]}
      />
    </PublicPageShell>
  );
}