import React, { useMemo, useState } from 'react';
import { Image, Platform, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import PublicPageShell from '../src/components/PublicPageLayout';
import { StaticContentSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

type PolicySection = {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  summary: string;
  paragraphs: string[];
  bullets?: string[];
  facts?: { label: string; value: string }[];
};

const HERO_IMAGE = 'https://images.unsplash.com/photo-1650327034304-a78be54cb60d?auto=format&fit=crop&w=1600&q=80';

export default function PrivacyPolicyPage() {
  const { t } = useTranslation();
  t('i18n.route.privacy-policy.probe');
  const pageReady = usePageReady();
  const { width } = useWindowDimensions();
  const { darkMode, colors } = useTheme();
  const [activeSection, setActiveSection] = useState('overview');
  const [searchQuery, setSearchQuery] = useState('');

  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const C = {
    bg: colors.bg,
    card: colors.card,
    cardSoft: colors.cardSoft || colors.surfaceHover,
    border: colors.glassBorder,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primary: colors.primary,
    primaryText: colors.primaryText,
    success: colors.success,
    warning: colors.warning,
    accent: colors.accent,
  };

  const isMobile = width < 768;
  const isTablet = width >= 768 && width < 1180;
  const heroHeight = isMobile ? 280 : isTablet ? 360 : 420;
  const pad = isMobile ? 16 : isTablet ? 24 : 32;

  const trustFacts = useMemo(() => [
    {
      id: 'data',
      title: tx('privacyPolicy.fact.collect.title', 'What we collect'),
      body: tx('privacyPolicy.fact.collect.body', 'Only the account, coaching, support, and connected-service data required to run the platform.'),
      icon: 'layers-outline' as const,
    },
    {
      id: 'usage',
      title: tx('privacyPolicy.fact.use.title', 'How we use it'),
      body: tx('privacyPolicy.fact.use.body', 'To authenticate you, personalize coaching, support operations, billing, and platform safety.'),
      icon: 'analytics-outline' as const,
    },
    {
      id: 'sharing',
      title: tx('privacyPolicy.fact.share.title', 'Who sees it'),
      body: tx('privacyPolicy.fact.share.body', 'Controlled processors only — never sold, never shared for third-party advertising, never used for model training from Google user data.'),
      icon: 'people-outline' as const,
    },
    {
      id: 'rights',
      title: tx('privacyPolicy.fact.rights.title', 'Your controls'),
      body: tx('privacyPolicy.fact.rights.body', 'Export, delete, correct, object, or contact the privacy team from one self-service path.'),
      icon: 'shield-checkmark-outline' as const,
    },
  ], [tx]);

  const rightsCards = useMemo(() => [
    {
      id: 'export',
      title: tx('privacyPolicy.actions.export.title', 'Export my data'),
      body: tx('privacyPolicy.actions.export.body', 'Request a machine-readable copy of your account, support, and platform activity records.'),
      icon: 'download-outline' as const,
      href: '/privacy-request',
      tone: C.primary,
    },
    {
      id: 'delete',
      title: tx('privacyPolicy.actions.delete.title', 'Delete my data'),
      body: tx('privacyPolicy.actions.delete.body', 'Trigger the verified deletion flow for account and linked privacy records.'),
      icon: 'trash-outline' as const,
      href: '/privacy-request',
      tone: C.warning,
    },
    {
      id: 'help',
      title: tx('privacyPolicy.actions.help.title', 'Contact privacy team'),
      body: tx('privacyPolicy.actions.help.body', 'Escalate a privacy, consent, retention, or legal clarification request to our operations team.'),
      icon: 'mail-open-outline' as const,
      href: '/help',
      tone: C.accent,
    },
  ], [C.accent, C.primary, C.warning, tx]);

  const sections = useMemo<PolicySection[]>(() => [
    {
      id: 'overview',
      icon: 'compass-outline',
      title: tx('privacyPolicy.section.overview.title', 'Overview and scope'),
      summary: tx('privacyPolicy.section.overview.summary', 'A plain-English summary of what this policy covers and when it applies.'),
      paragraphs: [
        tx('privacyPolicy.section.overview.p1', 'This Privacy Policy explains how RealAICoach collects, uses, stores, secures, and deletes personal information across our website, apps, support systems, billing operations, AI coaching tools, and connected third-party integrations.'),
        tx('privacyPolicy.section.overview.p2', 'It applies to visitors, registered users, subscribers, support requestors, and people who connect services such as Google to enable scheduling and productivity workflows. We aim to make this policy understandable before it is merely comprehensive.'),
      ],
      bullets: [
        tx('privacyPolicy.section.overview.b1', 'Applies to public visitors, signed-in users, paid subscribers, and support interactions'),
        tx('privacyPolicy.section.overview.b2', 'Explains platform data, Google-connected data, support records, and operational telemetry'),
        tx('privacyPolicy.section.overview.b3', 'Links directly to self-service rights and request channels'),
      ],
    },
    {
      id: 'collection',
      icon: 'server-outline',
      title: tx('privacyPolicy.section.collection.title', 'Data we collect'),
      summary: tx('privacyPolicy.section.collection.summary', 'We collect only the information required to operate your account, coaching workflows, support, safety, and compliance obligations.'),
      paragraphs: [
        tx('privacyPolicy.section.collection.p1', 'Information can come directly from you, automatically from platform usage, or from connected providers you authorize. Data categories include registration details, subscription state, support records, AI conversation context, product telemetry, and lawful security logs.'),
        tx('privacyPolicy.section.collection.p2', 'For connected Google experiences, we limit access to the minimum data needed for calendar syncing, scheduling context, and account identity. Google user data is not used for advertising and is not used to train generalized AI models.'),
      ],
      facts: [
        { label: tx('privacyPolicy.table.collection.account', 'Account data'), value: tx('privacyPolicy.table.collection.accountValue', 'Name, email, profile settings, plan state') },
        { label: tx('privacyPolicy.table.collection.product', 'Product usage'), value: tx('privacyPolicy.table.collection.productValue', 'Feature usage, error diagnostics, session patterns') },
        { label: tx('privacyPolicy.table.collection.support', 'Support records'), value: tx('privacyPolicy.table.collection.supportValue', 'Tickets, feedback, legal/privacy requests') },
        { label: tx('privacyPolicy.table.collection.connected', 'Connected services'), value: tx('privacyPolicy.table.collection.connectedValue', 'Calendar events, OAuth tokens, profile identity metadata') },
      ],
    },
    {
      id: 'usage',
      icon: 'flash-outline',
      title: tx('privacyPolicy.section.usage.title', 'How we use your data'),
      summary: tx('privacyPolicy.section.usage.summary', 'We use data to deliver the service you requested, protect the platform, and comply with legal obligations.'),
      paragraphs: [
        tx('privacyPolicy.section.usage.p1', 'Core uses include account creation, authentication, subscription management, platform personalization, coaching delivery, scheduling, support, fraud prevention, abuse detection, and service analytics. Each use should connect back to a legitimate business or legal purpose.'),
        tx('privacyPolicy.section.usage.p2', 'Where consent is the basis, you may withdraw it. Where contract performance or legitimate interest is the basis, we aim to explain what that means in operational terms so users are not left guessing.'),
      ],
      bullets: [
        tx('privacyPolicy.section.usage.b1', 'Authenticate and secure your account'),
        tx('privacyPolicy.section.usage.b2', 'Deliver AI coaching and product workflows you explicitly use'),
        tx('privacyPolicy.section.usage.b3', 'Operate support, billing, compliance, and trust communications'),
        tx('privacyPolicy.section.usage.b4', 'Detect abuse, monitor incidents, and maintain reliability'),
      ],
    },
    {
      id: 'sharing',
      icon: 'git-network-outline',
      title: tx('privacyPolicy.section.sharing.title', 'Sharing and processors'),
      summary: tx('privacyPolicy.section.sharing.summary', 'We use tightly scoped service providers to host, secure, email, and support the platform — not to resell or exploit your data.'),
      paragraphs: [
        tx('privacyPolicy.section.sharing.p1', 'We may share information with infrastructure providers, transactional email services, analytics or monitoring tools, and payment processors strictly to operate the platform. Each processor is limited by contractual and technical controls.'),
        tx('privacyPolicy.section.sharing.p2', 'We do not sell personal information. We do not share Google user data with advertisers, data brokers, or unrelated third parties. We aim to disclose sharing by category so this page remains useful to real users and to compliance reviewers.'),
      ],
      facts: [
        { label: tx('privacyPolicy.table.sharing.hosting', 'Hosting & storage'), value: tx('privacyPolicy.table.sharing.hostingValue', 'Application hosting and encrypted data persistence') },
        { label: tx('privacyPolicy.table.sharing.email', 'Email delivery'), value: tx('privacyPolicy.table.sharing.emailValue', 'Transactional notices, privacy verification, and legal updates') },
        { label: tx('privacyPolicy.table.sharing.payments', 'Payments'), value: tx('privacyPolicy.table.sharing.paymentsValue', 'Subscription billing, refunds, payment status verification') },
        { label: tx('privacyPolicy.table.sharing.support', 'Support & compliance'), value: tx('privacyPolicy.table.sharing.supportValue', 'Request tracking, audits, and incident response') },
      ],
    },
    {
      id: 'retention',
      icon: 'time-outline',
      title: tx('privacyPolicy.section.retention.title', 'Retention, deletion, and storage'),
      summary: tx('privacyPolicy.section.retention.summary', 'Retention windows exist so the product works, legal duties are met, and stale personal data does not live forever.'),
      paragraphs: [
        tx('privacyPolicy.section.retention.p1', 'We retain different categories of data for different periods depending on account state, legal duty, security obligations, and whether you have requested deletion. Connected-service caches are purged more aggressively than core account records.'),
        tx('privacyPolicy.section.retention.p2', 'Deletion requests are verified before execution. Some records may be retained longer where necessary for fraud prevention, billing reconciliation, audit requirements, or dispute defense, but we aim to document those exceptions clearly.'),
      ],
      facts: [
        { label: tx('privacyPolicy.table.retention.account', 'Account profile'), value: tx('privacyPolicy.table.retention.accountValue', 'Retained while active, then deleted or anonymized per request and legal duties') },
        { label: tx('privacyPolicy.table.retention.google', 'Google calendar cache'), value: tx('privacyPolicy.table.retention.googleValue', 'Refreshed during sync, removed after disconnect or account deletion workflow') },
        { label: tx('privacyPolicy.table.retention.privacy', 'Privacy requests'), value: tx('privacyPolicy.table.retention.privacyValue', 'Retained as audit records for compliance and request verification') },
        { label: tx('privacyPolicy.table.retention.logs', 'Security logs'), value: tx('privacyPolicy.table.retention.logsValue', 'Retained for abuse prevention, investigations, and service integrity') },
      ],
    },
    {
      id: 'rights',
      icon: 'shield-checkmark-outline',
      title: tx('privacyPolicy.section.rights.title', 'Your rights and controls'),
      summary: tx('privacyPolicy.section.rights.summary', 'You can request access, correction, export, deletion, restriction, objection, or consent withdrawal using our privacy pathways.'),
      paragraphs: [
        tx('privacyPolicy.section.rights.p1', 'Depending on your jurisdiction, you may have rights to access, correct, delete, export, restrict, or object to processing of your personal data. We also provide channels to manage consent, disconnect integrations, and contact our privacy operations team.'),
        tx('privacyPolicy.section.rights.p2', 'Our goal is to make rights practical, not symbolic. That is why this page links directly into self-service actions and support escalation paths instead of forcing users to decode legal language on their own.'),
      ],
      bullets: [
        tx('privacyPolicy.section.rights.b1', 'Use the Manage My Data flow for export or deletion verification'),
        tx('privacyPolicy.section.rights.b2', 'Disconnect integrations in settings to stop future connected-service syncing'),
        tx('privacyPolicy.section.rights.b3', 'Contact privacy@realaicoach.app for jurisdiction-specific questions or appeals'),
      ],
    },
  ], [tx]);

  const filteredSections = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sections;
    return sections.filter((section) => {
      const haystack = [section.title, section.summary, ...section.paragraphs, ...(section.bullets || []), ...(section.facts || []).map((fact) => `${fact.label} ${fact.value}`)].join(' ').toLowerCase();
      return haystack.includes(query);
    });
  }, [searchQuery, sections]);

  const activeSectionData = filteredSections.find((section) => section.id === activeSection) || filteredSections[0] || sections[0];

  const changeLog = useMemo(() => [
    tx('privacyPolicy.changelog.1', 'Clarified connected Google data handling and limited-use obligations.'),
    tx('privacyPolicy.changelog.2', 'Expanded retention windows and deletion workflow details for self-service requests.'),
    tx('privacyPolicy.changelog.3', 'Added a clearer privacy operations path for export, deletion, and escalation requests.'),
  ], [tx]);

  if (!pageReady) {
    return (
      <PublicPageShell maxWidth={1320} testID="privacy-policy-shell" data-testid="privacy-policy-shell">
        <StaticContentSkeleton />
      </PublicPageShell>
    );
  }

  const chromeStyle = Platform.OS === 'web'
    ? { position: 'sticky' as any, top: 92, alignSelf: 'flex-start' as const }
    : undefined;

  return (
    <PublicPageShell maxWidth={1320} testID="privacy-policy-shell" data-testid="privacy-policy-shell">
      <View style={{ gap: isMobile ? 20 : 28 }} data-testid="privacy-policy-page" testID="privacy-policy-page">
        <View style={{ overflow: 'hidden', borderRadius: isMobile ? 24 : 32, borderWidth: 1, borderColor: C.border, backgroundColor: C.card }} data-testid="privacy-policy-hero" testID="privacy-policy-hero">
          <View style={{ position: 'relative', minHeight: heroHeight, justifyContent: 'flex-end' }}>
            <Image source={{ uri: HERO_IMAGE }} resizeMode="cover" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} accessibilityLabel={tx('privacyPolicy.hero.imageAlt', 'Abstract encrypted data flow background')} />
            <View style={{ position: 'absolute', inset: 0, backgroundColor: darkMode ? 'rgba(2,6,23,0.76)' : 'rgba(248,249,250,0.72)' }} />
            <View style={{ padding: pad, gap: 14 }}>
              <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: `${C.primary}18`, borderWidth: 1, borderColor: `${C.primary}40` }} data-testid="privacy-policy-badge" testID="privacy-policy-badge">
                    <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.4 }}>{tx('privacyPolicy.hero.badge', 'PRIVACY TRUST CENTER')}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: `${C.text}08`, borderWidth: 1, borderColor: `${C.border}` }} data-testid="privacy-policy-version" testID="privacy-policy-version">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{tx('privacyPolicy.hero.version', 'Version 2026.3')}</Text>
                  </View>
                </View>

                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <TouchableOpacity onPress={() => router.push('/privacy-request')} style={{ paddingHorizontal: 16, paddingVertical: 11, borderRadius: 999, backgroundColor: C.primary }} data-testid="privacy-policy-manage-data-hero-cta" testID="privacy-policy-manage-data-hero-cta">
                    <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>{tx('privacyPolicy.hero.cta.manage', 'Manage My Data')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => router.push('/help')} style={{ paddingHorizontal: 16, paddingVertical: 11, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: `${C.card}B8` }} data-testid="privacy-policy-contact-hero-cta" testID="privacy-policy-contact-hero-cta">
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('privacyPolicy.hero.cta.contact', 'Contact Privacy Team')}</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ maxWidth: 780, gap: 10 }}>
                <Text style={{ color: C.text, fontSize: isMobile ? 34 : isTablet ? 48 : 60, fontWeight: '900', letterSpacing: -2.2, lineHeight: isMobile ? 38 : isTablet ? 52 : 64 }} data-testid="privacy-policy-title" testID="privacy-policy-title">
                  {tx('privacyPolicy.hero.title', 'Privacy Policy built for trust, action, and transparency.')}
                </Text>
                <Text style={{ color: C.textSec, fontSize: isMobile ? 14 : 16, lineHeight: isMobile ? 22 : 26, maxWidth: 700 }} data-testid="privacy-policy-subtitle" testID="privacy-policy-subtitle">
                  {tx('privacyPolicy.hero.subtitle', 'This page explains what we collect, why we collect it, how long we keep it, and what you can do about it — without forcing you to decode a wall of legal text first.')}
                </Text>
              </View>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, flexWrap: 'wrap' }} data-testid="privacy-policy-meta-strip" testID="privacy-policy-meta-strip">
                {[
                  tx('privacyPolicy.hero.meta.updated', 'Last updated: March 18, 2026'),
                  tx('privacyPolicy.hero.meta.effective', 'Effective: March 18, 2026'),
                  tx('privacyPolicy.hero.meta.response', 'Privacy operations SLA: 72 hours for first response'),
                ].map((item, idx) => (
                  <View key={item} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14, borderWidth: 1, borderColor: `${C.border}`, backgroundColor: `${C.card}C4` }} data-testid={`privacy-policy-meta-item-${idx}`} testID={`privacy-policy-meta-item-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{item}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        </View>

        <View style={{ gap: 12 }} data-testid="privacy-policy-summary-grid" testID="privacy-policy-summary-grid">
          <Text style={{ color: C.text, fontSize: isMobile ? 20 : 26, fontWeight: '800' }}>{tx('privacyPolicy.summary.title', 'TL;DR — what matters most')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {trustFacts.map((fact) => (
              <View key={fact.id} style={{ flexBasis: isMobile ? '100%' : isTablet ? '48%' : '24%', flexGrow: 1, minWidth: isMobile ? 0 : 220, borderWidth: 1, borderColor: C.border, borderRadius: 20, padding: 18, backgroundColor: C.card }} data-testid={`privacy-policy-summary-card-${fact.id}`} testID={`privacy-policy-summary-card-${fact.id}`}>
                <View style={{ width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: `${C.primary}14`, marginBottom: 14 }}>
                  <Ionicons name={fact.icon} size={20} color={C.primary} />
                </View>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 8 }}>{fact.title}</Text>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21 }}>{fact.body}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 14 }}>
          <View style={{ flex: isMobile ? undefined : 1.2, borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad }} data-testid="privacy-policy-whats-new" testID="privacy-policy-whats-new">
            <Text style={{ color: C.text, fontSize: 19, fontWeight: '800', marginBottom: 10 }}>{tx('privacyPolicy.changelog.title', 'What changed in this version')}</Text>
            <View style={{ gap: 10 }}>
              {changeLog.map((item, idx) => (
                <View key={item} style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }} data-testid={`privacy-policy-changelog-item-${idx}`} testID={`privacy-policy-changelog-item-${idx}`}>
                  <View style={{ width: 24, height: 24, borderRadius: 999, alignItems: 'center', justifyContent: 'center', backgroundColor: `${C.success}18`, marginTop: 1 }}>
                    <Ionicons name="checkmark" size={14} color={C.success} />
                  </View>
                  <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, flex: 1 }}>{item}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ flex: 1, borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad }} data-testid="privacy-policy-trust-panel" testID="privacy-policy-trust-panel">
            <Text style={{ color: C.text, fontSize: 19, fontWeight: '800', marginBottom: 10 }}>{tx('privacyPolicy.trustPanel.title', 'What this means for you')}</Text>
            <View style={{ gap: 12 }}>
              {[
                tx('privacyPolicy.trustPanel.item1', 'You can review, export, or delete data through a single verified path.'),
                tx('privacyPolicy.trustPanel.item2', 'Connected Google data stays limited to the workflows you explicitly enable.'),
                tx('privacyPolicy.trustPanel.item3', 'Privacy updates can be communicated by compliant legal notice email and on-page version history.'),
              ].map((item, idx) => (
                <View key={item} style={{ flexDirection: 'row', gap: 10 }} data-testid={`privacy-policy-trust-item-${idx}`} testID={`privacy-policy-trust-item-${idx}`}>
                  <Ionicons name="arrow-forward-circle-outline" size={18} color={C.primary} style={{ marginTop: 2 }} />
                  <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, flex: 1 }}>{item}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>

        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 18, alignItems: 'flex-start' }}>
          <View style={[{ width: isMobile ? '100%' : 280, gap: 14 }, chromeStyle]} data-testid="privacy-policy-sidebar" testID="privacy-policy-sidebar">
            <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 16 }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }}>{tx('privacyPolicy.sidebar.title', 'Navigate the policy')}</Text>
              <TextInput
                value={searchQuery}
                onChangeText={setSearchQuery}
                placeholder={tx('privacyPolicy.sidebar.search', 'Search this policy')}
                placeholderTextColor={C.textMuted}
                style={{ borderWidth: 1, borderColor: C.border, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, color: C.text, backgroundColor: C.cardSoft, marginBottom: 12 }}
                data-testid="privacy-policy-search-input"
                testID="privacy-policy-search-input"
              />
              <View style={{ gap: 8 }}>
                {filteredSections.map((section) => {
                  const active = activeSectionData?.id === section.id;
                  return (
                    <TouchableOpacity key={section.id} onPress={() => setActiveSection(section.id)} style={{ borderRadius: 14, paddingHorizontal: 12, paddingVertical: 11, borderWidth: 1, borderColor: active ? `${C.primary}66` : C.border, backgroundColor: active ? `${C.primary}14` : C.card }} data-testid={`privacy-policy-nav-${section.id}`} testID={`privacy-policy-nav-${section.id}`}>
                      <Text style={{ color: active ? C.primary : C.text, fontSize: 13, fontWeight: '700', marginBottom: 4 }}>{section.title}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 11, lineHeight: 17 }}>{section.summary}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 16 }} data-testid="privacy-policy-sticky-cta-card" testID="privacy-policy-sticky-cta-card">
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '800', marginBottom: 8 }}>{tx('privacyPolicy.sidebar.ctaTitle', 'Need to take action?')}</Text>
              <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 20, marginBottom: 12 }}>{tx('privacyPolicy.sidebar.ctaBody', 'Use our verified self-service request path for export or deletion, or contact privacy operations for deeper questions.')}</Text>
              <TouchableOpacity onPress={() => router.push('/privacy-request')} style={{ borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: C.primary }} data-testid="privacy-policy-sidebar-manage-data" testID="privacy-policy-sidebar-manage-data">
                <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>{tx('privacyPolicy.sidebar.ctaButton', 'Open Manage My Data')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={{ flex: 1, gap: 16 }} data-testid="privacy-policy-reading-pane" testID="privacy-policy-reading-pane">
            {(filteredSections.length ? filteredSections : sections).map((section) => (
              <View key={section.id} style={{ borderRadius: 24, borderWidth: 1, borderColor: activeSectionData?.id === section.id ? `${C.primary}55` : C.border, backgroundColor: C.card, padding: pad }} data-testid={`privacy-policy-section-${section.id}`} testID={`privacy-policy-section-${section.id}`}>
                <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 14, marginBottom: 14 }}>
                  <View style={{ flexDirection: 'row', gap: 12, flex: 1 }}>
                    <View style={{ width: 46, height: 46, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: `${C.primary}14` }}>
                      <Ionicons name={section.icon} size={20} color={C.primary} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 22, fontWeight: '800', marginBottom: 6 }}>{section.title}</Text>
                      <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 23 }}>{section.summary}</Text>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => setActiveSection(section.id)} style={{ alignSelf: isMobile ? 'flex-start' : 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardSoft }} data-testid={`privacy-policy-focus-${section.id}`} testID={`privacy-policy-focus-${section.id}`}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('privacyPolicy.section.focus', 'Pin section')}</Text>
                  </TouchableOpacity>
                </View>

                <View style={{ gap: 12 }}>
                  {section.paragraphs.map((paragraph, idx) => (
                    <Text key={`${section.id}-paragraph-${idx}`} style={{ color: C.textSec, fontSize: 14, lineHeight: 24 }} data-testid={`privacy-policy-section-${section.id}-paragraph-${idx}`} testID={`privacy-policy-section-${section.id}-paragraph-${idx}`}>
                      {paragraph}
                    </Text>
                  ))}

                  {section.bullets?.length ? (
                    <View style={{ gap: 8, marginTop: 4 }}>
                      {section.bullets.map((bullet, idx) => (
                        <View key={`${section.id}-bullet-${idx}`} style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }} data-testid={`privacy-policy-section-${section.id}-bullet-${idx}`} testID={`privacy-policy-section-${section.id}-bullet-${idx}`}>
                          <Ionicons name="checkmark-circle" size={18} color={C.success} style={{ marginTop: 2 }} />
                          <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 22, flex: 1 }}>{bullet}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}

                  {section.facts?.length ? (
                    <View style={{ marginTop: 8, borderRadius: 18, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid={`privacy-policy-section-${section.id}-facts`} testID={`privacy-policy-section-${section.id}-facts`}>
                      {section.facts.map((fact, idx) => (
                        <View key={`${section.id}-fact-${idx}`} style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, paddingHorizontal: 16, paddingVertical: 14, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border, backgroundColor: idx % 2 === 0 ? C.card : C.cardSoft }} data-testid={`privacy-policy-section-${section.id}-fact-${idx}`} testID={`privacy-policy-section-${section.id}-fact-${idx}`}>
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', width: isMobile ? '100%' : 190 }}>{fact.label}</Text>
                          <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, flex: 1 }}>{fact.value}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        </View>

        <View style={{ borderRadius: 28, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, overflow: 'hidden' }} data-testid="privacy-policy-action-hub" testID="privacy-policy-action-hub">
          <View style={{ padding: pad, gap: 12, backgroundColor: `${C.primary}0F` }}>
            <Text style={{ color: C.text, fontSize: isMobile ? 22 : 28, fontWeight: '900', letterSpacing: -0.8 }}>{tx('privacyPolicy.actionHub.title', 'Manage your data without opening a support ticket first')}</Text>
            <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 24, maxWidth: 760 }}>{tx('privacyPolicy.actionHub.subtitle', 'Our privacy operations flow is designed so real users can take action immediately: export data, request deletion, review rights, or contact the privacy team with context already attached.')}</Text>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, padding: pad }}>
            {rightsCards.map((card) => (
              <TouchableOpacity key={card.id} onPress={() => router.push(card.href as any)} style={{ flexBasis: isMobile ? '100%' : isTablet ? '48%' : '31%', flexGrow: 1, minWidth: isMobile ? 0 : 240, borderWidth: 1, borderColor: `${card.tone}44`, backgroundColor: `${card.tone}10`, borderRadius: 20, padding: 18 }} data-testid={`privacy-policy-action-card-${card.id}`} testID={`privacy-policy-action-card-${card.id}`}>
                <View style={{ width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: `${card.tone}18`, marginBottom: 14 }}>
                  <Ionicons name={card.icon} size={20} color={card.tone} />
                </View>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 8 }}>{card.title}</Text>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, marginBottom: 14 }}>{card.body}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: card.tone, fontSize: 12, fontWeight: '800' }}>{tx('privacyPolicy.actionHub.open', 'Open flow')}</Text>
                  <Ionicons name="arrow-forward" size={14} color={card.tone} />
                </View>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad, gap: 14 }} data-testid="privacy-policy-contact-panel" testID="privacy-policy-contact-panel">
          <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{tx('privacyPolicy.contact.title', 'Questions, complaints, or legal notices')}</Text>
          <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 24 }}>{tx('privacyPolicy.contact.body', 'If you need help interpreting this policy, want to escalate a privacy concern, or need a documented response for compliance review, contact our privacy operations team or use the self-service request path.')}</Text>
          <View style={{ flexDirection: isMobile ? 'column' : 'row', flexWrap: 'wrap', gap: 12 }}>
            {[
              { id: 'email', label: tx('privacyPolicy.contact.email', 'privacy@realaicoach.app'), icon: 'mail-outline' as const },
              { id: 'help', label: tx('privacyPolicy.contact.help', 'Help & Support workspace'), icon: 'help-buoy-outline' as const },
              { id: 'sla', label: tx('privacyPolicy.contact.sla', 'First response target: 72 hours'), icon: 'time-outline' as const },
            ].map((item) => (
              <View key={item.id} style={{ flex: isMobile ? undefined : 1, minWidth: isMobile ? 0 : 220, borderRadius: 16, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardSoft, padding: 14 }} data-testid={`privacy-policy-contact-item-${item.id}`} testID={`privacy-policy-contact-item-${item.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <Ionicons name={item.icon} size={16} color={C.primary} />
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{item.id.toUpperCase()}</Text>
                </View>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 20 }}>{item.label}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>
    </PublicPageShell>
  );
}