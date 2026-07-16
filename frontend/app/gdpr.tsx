import React, { useMemo } from 'react';
import PublicPageShell from '../src/components/PublicPageLayout';
import { StaticContentSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { TrustCenterTemplate } from '../src/components/legal/TrustCenterTemplate';
import { useTranslation } from '../src/hooks/useTranslation';

const HERO_IMAGE = 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1600&q=80';

export default function GDPRPage() {
  const { t } = useTranslation();
  t('i18n.route.gdpr.probe');
  const pageReady = usePageReady();

  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const familyLinks = useMemo(() => [
    { id: 'privacy', label: tx('trustCenter.family.privacy', 'Privacy'), href: '/privacy-policy' },
    { id: 'terms', label: tx('trustCenter.family.terms', 'Terms'), href: '/terms' },
    { id: 'security', label: tx('trustCenter.family.security', 'Security'), href: '/security' },
    { id: 'gdpr', label: tx('trustCenter.family.gdpr', 'GDPR'), href: '/gdpr', active: true },
    { id: 'cookies', label: tx('trustCenter.family.cookies', 'Cookies'), href: '/cookies' },
  ], [tx]);

  const sections = useMemo(() => [
    {
      id: 'controller',
      icon: 'business-outline' as const,
      title: tx('gdprCenter.section.controller.title', 'Controller, scope, and lawful framework'),
      summary: tx('gdprCenter.section.controller.summary', 'Explains our role as controller, what data categories fall into scope, and why GDPR applies.'),
      paragraphs: [
        tx('gdprCenter.section.controller.p1', 'RealAICoach acts as a controller for platform account, product, support, and connected-service data to the extent that we decide the purposes and means of processing. Some processors act on our instructions under contractual controls.'),
        tx('gdprCenter.section.controller.p2', 'This page summarizes our GDPR-facing commitments for access, correction, deletion, portability, objection, restriction, and privacy contact pathways in a more practical format than a traditional legal memo.'),
      ],
      bullets: [
        tx('gdprCenter.section.controller.b1', 'Applies to EEA/UK data rights and related trust obligations'),
        tx('gdprCenter.section.controller.b2', 'Connects legal rights to real product and support workflows'),
        tx('gdprCenter.section.controller.b3', 'Built to help both users and compliance reviewers understand the system quickly'),
      ],
    },
    {
      id: 'lawful-basis',
      icon: 'scale-outline' as const,
      title: tx('gdprCenter.section.lawful.title', 'Lawful basis for processing'),
      summary: tx('gdprCenter.section.lawful.summary', 'Personal data is processed only where a lawful basis supports the purpose.'),
      paragraphs: [
        tx('gdprCenter.section.lawful.p1', 'Our primary lawful bases include contract performance, legitimate interest, consent, and legal obligation depending on the data category and workflow involved.'),
        tx('gdprCenter.section.lawful.p2', 'Where consent is used, users can withdraw it. Where legitimate interest is used, we aim to keep processing proportionate, explainable, and limited to the stated operational need.'),
      ],
      facts: [
        { label: tx('gdprCenter.table.lawful.contract', 'Contract'), value: tx('gdprCenter.table.lawful.contractValue', 'Running accounts, subscriptions, support, and product workflows') },
        { label: tx('gdprCenter.table.lawful.legitimate', 'Legitimate interest'), value: tx('gdprCenter.table.lawful.legitimateValue', 'Security, service improvement, abuse prevention, and reliability') },
        { label: tx('gdprCenter.table.lawful.consent', 'Consent'), value: tx('gdprCenter.table.lawful.consentValue', 'Optional communications, some connected features, and preference-driven controls') },
        { label: tx('gdprCenter.table.lawful.legal', 'Legal obligation'), value: tx('gdprCenter.table.lawful.legalValue', 'Audit, tax, security, and dispute-handling duties') },
      ],
    },
    {
      id: 'rights',
      icon: 'shield-checkmark-outline' as const,
      title: tx('gdprCenter.section.rights.title', 'Your GDPR rights'),
      summary: tx('gdprCenter.section.rights.summary', 'Access, rectification, erasure, portability, objection, restriction, and consent withdrawal are connected to real request flows.'),
      paragraphs: [
        tx('gdprCenter.section.rights.p1', 'Users may request access to personal data, correction of inaccurate data, deletion where permitted, portability, restriction, objection, and review of consent-related choices. We also provide a self-service path for export and deletion verification.'),
        tx('gdprCenter.section.rights.p2', 'Where a request cannot be completed exactly as submitted, we aim to explain why, what legal or operational limit applies, and what alternative path is available.'),
      ],
      bullets: [
        tx('gdprCenter.section.rights.b1', 'Export or delete through the verified privacy request portal'),
        tx('gdprCenter.section.rights.b2', 'Contact the privacy team for rectification, objection, or restriction requests'),
        tx('gdprCenter.section.rights.b3', 'Escalate to a supervisory authority where required by law'),
      ],
    },
    {
      id: 'transfers',
      icon: 'globe-outline' as const,
      title: tx('gdprCenter.section.transfers.title', 'International transfers, retention, and safeguards'),
      summary: tx('gdprCenter.section.transfers.summary', 'Cross-border processing and retention are controlled through contractual, technical, and operational safeguards.'),
      paragraphs: [
        tx('gdprCenter.section.transfers.p1', 'Where personal data is processed outside the EEA or UK, we rely on appropriate safeguards such as contractual protections, provider obligations, and security controls matched to the processing context.'),
        tx('gdprCenter.section.transfers.p2', 'Retention depends on product necessity, legal obligation, security needs, and verified deletion requests. Our goal is to keep retention understandable rather than hidden inside vague legal generalities.'),
      ],
      facts: [
        { label: tx('gdprCenter.table.transfers.hosting', 'Cross-border hosting'), value: tx('gdprCenter.table.transfers.hostingValue', 'Controlled through provider and contractual safeguards') },
        { label: tx('gdprCenter.table.transfers.retention', 'Retention logic'), value: tx('gdprCenter.table.transfers.retentionValue', 'Based on service operation, audits, security, and verified rights requests') },
        { label: tx('gdprCenter.table.transfers.deletion', 'Deletion execution'), value: tx('gdprCenter.table.transfers.deletionValue', 'Verified request workflow linked to privacy operations') },
      ],
    },
  ], [tx]);

  if (!pageReady) {
    return <PublicPageShell maxWidth={1320} testID="gdpr-center-shell"><StaticContentSkeleton /></PublicPageShell>;
  }

  return (
    <PublicPageShell maxWidth={1320} testID="gdpr-center-shell">
      <TrustCenterTemplate
        testIdPrefix="gdpr-center"
        heroImage={HERO_IMAGE}
        heroImageAlt={tx('gdprCenter.hero.imageAlt', 'Abstract cross-border data and compliance background')}
        badge={tx('gdprCenter.hero.badge', 'GDPR TRUST CENTER')}
        version={tx('gdprCenter.hero.version', 'Version 2026.2')}
        title={tx('gdprCenter.hero.title', 'GDPR explained in operational terms, not just legal labels.')}
        subtitle={tx('gdprCenter.hero.subtitle', 'This page turns GDPR rights, lawful basis, retention, and transfer language into a real trust and action surface for users and reviewers.')}
        metaItems={[
          tx('gdprCenter.hero.meta.updated', 'Last updated: March 20, 2026'),
          tx('gdprCenter.hero.meta.effective', 'Effective: March 20, 2026'),
          tx('gdprCenter.hero.meta.sla', 'Privacy operations target: first response within 72 hours'),
        ]}
        heroPrimaryCta={{ label: tx('gdprCenter.hero.cta.manage', 'Manage My Data'), href: '/privacy-request', testId: 'gdpr-center-manage-data-cta' }}
        heroSecondaryCta={{ label: tx('gdprCenter.hero.cta.contact', 'Contact Privacy Team'), href: '/help', testId: 'gdpr-center-contact-cta' }}
        familyLinks={familyLinks}
        summaryTitle={tx('gdprCenter.summary.title', 'TL;DR — your GDPR position on this platform')}
        trustFacts={[
          { id: 'rights', title: tx('gdprCenter.fact.rights.title', 'Rights available'), body: tx('gdprCenter.fact.rights.body', 'Access, correction, deletion, portability, objection, and restriction pathways are available.'), icon: 'shield-checkmark-outline' },
          { id: 'lawful', title: tx('gdprCenter.fact.lawful.title', 'Lawful basis'), body: tx('gdprCenter.fact.lawful.body', 'Contract, legitimate interest, consent, and legal obligation apply depending on workflow.'), icon: 'scale-outline' },
          { id: 'retention', title: tx('gdprCenter.fact.retention.title', 'Retention clarity'), body: tx('gdprCenter.fact.retention.body', 'Data is retained only as long as necessary for service, safety, or legal duties.'), icon: 'time-outline' },
          { id: 'transfer', title: tx('gdprCenter.fact.transfer.title', 'Transfer safeguards'), body: tx('gdprCenter.fact.transfer.body', 'Cross-border processing relies on contractual and technical protection layers.'), icon: 'globe-outline' },
        ]}
        changeLogTitle={tx('gdprCenter.changelog.title', 'What changed in this GDPR experience')}
        changeLogItems={[
          tx('gdprCenter.changelog.1', 'Reframed GDPR rights into clearer user and operator language.'),
          tx('gdprCenter.changelog.2', 'Connected lawful-basis and retention explanations to live product flows.'),
          tx('gdprCenter.changelog.3', 'Unified GDPR with the Trust Center family and privacy request actions.'),
        ]}
        trustPanelTitle={tx('gdprCenter.trustPanel.title', 'What this means for you')}
        trustPanelItems={[
          tx('gdprCenter.trustPanel.item1', 'You can move from legal rights language to direct privacy action without friction.'),
          tx('gdprCenter.trustPanel.item2', 'We explain lawful basis and retention in ways users can actually understand.'),
          tx('gdprCenter.trustPanel.item3', 'Escalation paths stay visible when self-service is not enough.'),
        ]}
        sidebarTitle={tx('gdprCenter.sidebar.title', 'Navigate GDPR topics')}
        sidebarSearchPlaceholder={tx('gdprCenter.sidebar.search', 'Search GDPR topics')}
        sidebarCtaTitle={tx('gdprCenter.sidebar.ctaTitle', 'Need to exercise a right?')}
        sidebarCtaBody={tx('gdprCenter.sidebar.ctaBody', 'Use the verified privacy request path for export or deletion, or contact privacy operations for more specific GDPR requests.')}
        sidebarCtaLabel={tx('gdprCenter.sidebar.ctaButton', 'Open privacy request flow')}
        sidebarCtaHref="/privacy-request"
        sections={sections}
        pinSectionLabel={tx('gdprCenter.section.focus', 'Pin section')}
        actionHubTitle={tx('gdprCenter.actionHub.title', 'Turn GDPR rights into real actions')}
        actionHubSubtitle={tx('gdprCenter.actionHub.subtitle', 'These paths are built so users can act on rights immediately instead of sending vague legal emails without context.')}
        actionHubOpenLabel={tx('gdprCenter.actionHub.open', 'Open flow')}
        actionCards={[
          { id: 'export', title: tx('gdprCenter.actions.export.title', 'Export personal data'), body: tx('gdprCenter.actions.export.body', 'Request a machine-readable export through the verified privacy flow.'), icon: 'download-outline', href: '/privacy-request' },
          { id: 'delete', title: tx('gdprCenter.actions.delete.title', 'Delete personal data'), body: tx('gdprCenter.actions.delete.body', 'Begin the verified deletion process and receive completion updates through privacy operations.'), icon: 'trash-outline', href: '/privacy-request', tone: 'error' },
          { id: 'privacy', title: tx('gdprCenter.actions.privacy.title', 'Review Privacy Policy'), body: tx('gdprCenter.actions.privacy.body', 'Move from GDPR-specific rights into the full Privacy Trust Center.'), icon: 'shield-checkmark-outline', href: '/privacy-policy' },
        ]}
        contactTitle={tx('gdprCenter.contact.title', 'GDPR questions, objections, or authority escalation')}
        contactBody={tx('gdprCenter.contact.body', 'If you need a rights clarification, want to object to processing, or need a documented response for a supervisory authority, use the privacy path below.')}
        contactItems={[
          { id: 'privacy', label: tx('gdprCenter.contact.privacy', 'privacy@realaicoach.app'), icon: 'mail-outline' },
          { id: 'help', label: tx('gdprCenter.contact.help', 'Help & Support workspace'), icon: 'help-buoy-outline' },
          { id: 'request', label: tx('gdprCenter.contact.request', 'Verified privacy request workflow for export or deletion'), icon: 'document-text-outline' },
        ]}
      />
    </PublicPageShell>
  );
}