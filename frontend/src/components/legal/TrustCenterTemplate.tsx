import React, { useMemo, useState } from 'react';
import { Image, Platform, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';

type TrustFact = {
  id: string;
  title: string;
  body: string;
  icon: keyof typeof Ionicons.glyphMap;
};

type TrustSection = {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  summary: string;
  paragraphs: string[];
  bullets?: string[];
  facts?: { label: string; value: string }[];
};

type ActionCard = {
  id: string;
  title: string;
  body: string;
  icon: keyof typeof Ionicons.glyphMap;
  href: string;
  tone?: string;
};

type ContactItem = {
  id: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
};

type FamilyLink = {
  id: string;
  label: string;
  href: string;
  active?: boolean;
};

type TrustCenterTemplateProps = {
  testIdPrefix: string;
  heroImage: string;
  heroImageAlt: string;
  badge: string;
  version: string;
  title: string;
  subtitle: string;
  metaItems: string[];
  heroPrimaryCta: { label: string; href: string; testId: string };
  heroSecondaryCta?: { label: string; href: string; testId: string };
  familyLinks: FamilyLink[];
  summaryTitle: string;
  trustFacts: TrustFact[];
  changeLogTitle: string;
  changeLogItems: string[];
  trustPanelTitle: string;
  trustPanelItems: string[];
  sidebarTitle: string;
  sidebarSearchPlaceholder: string;
  sidebarCtaTitle: string;
  sidebarCtaBody: string;
  sidebarCtaLabel: string;
  sidebarCtaHref: string;
  sections: TrustSection[];
  pinSectionLabel: string;
  actionHubTitle: string;
  actionHubSubtitle: string;
  actionHubOpenLabel: string;
  actionCards: ActionCard[];
  contactTitle: string;
  contactBody: string;
  contactItems: ContactItem[];
};

export const TrustCenterTemplate = ({
  testIdPrefix,
  heroImage,
  heroImageAlt,
  badge,
  version,
  title,
  subtitle,
  metaItems,
  heroPrimaryCta,
  heroSecondaryCta,
  familyLinks,
  summaryTitle,
  trustFacts,
  changeLogTitle,
  changeLogItems,
  trustPanelTitle,
  trustPanelItems,
  sidebarTitle,
  sidebarSearchPlaceholder,
  sidebarCtaTitle,
  sidebarCtaBody,
  sidebarCtaLabel,
  sidebarCtaHref,
  sections,
  pinSectionLabel,
  actionHubTitle,
  actionHubSubtitle,
  actionHubOpenLabel,
  actionCards,
  contactTitle,
  contactBody,
  contactItems,
}: TrustCenterTemplateProps) => {
  const { t } = useLanguage();
  const { width } = useWindowDimensions();
  const { darkMode, colors } = useTheme();
  const [activeSection, setActiveSection] = useState(sections[0]?.id || '');
  const [searchQuery, setSearchQuery] = useState('');

  const C = {
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

  const filteredSections = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sections;
    const matches = sections.filter((section) => {
      const haystack = [section.title, section.summary, ...section.paragraphs, ...(section.bullets || []), ...(section.facts || []).map((fact) => `${fact.label} ${fact.value}`)].join(' ').toLowerCase();
      return haystack.includes(query);
    });
    return matches.length ? matches : sections;
  }, [searchQuery, sections]);

  const activeSectionData = filteredSections.find((section) => section.id === activeSection) || filteredSections[0] || sections[0];
  const stickyStyle = Platform.OS === 'web' ? { position: 'sticky' as any, top: 92, alignSelf: 'flex-start' as const } : undefined;

  return (
    <View style={{ gap: isMobile ? 20 : 28 }} data-testid={`${testIdPrefix}-page`} testID={`${testIdPrefix}-page`}>
      <View style={{ overflow: 'hidden', borderRadius: isMobile ? 24 : 32, borderWidth: 1, borderColor: C.border, backgroundColor: C.card }} data-testid={`${testIdPrefix}-hero`} testID={`${testIdPrefix}-hero`}>
        <View style={{ position: 'relative', minHeight: heroHeight, justifyContent: 'flex-end' }}>
          <Image source={{ uri: heroImage }} resizeMode="cover" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} accessibilityLabel={heroImageAlt} />
          <View style={{ position: 'absolute', inset: 0, backgroundColor: darkMode ? 'rgba(2,6,23,0.76)' : 'rgba(248,249,250,0.72)' }} />
          <View style={{ padding: pad, gap: 14 }}>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: `${C.primary}18`, borderWidth: 1, borderColor: `${C.primary}40` }} data-testid={`${testIdPrefix}-badge`} testID={`${testIdPrefix}-badge`}>
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.4 }}>{badge}</Text>
                </View>
                <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: `${C.text}08`, borderWidth: 1, borderColor: C.border }} data-testid={`${testIdPrefix}-version`} testID={`${testIdPrefix}-version`}>
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{version}</Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <TouchableOpacity onPress={() => router.push(heroPrimaryCta.href as any)} style={{ paddingHorizontal: 16, paddingVertical: 11, borderRadius: 999, backgroundColor: C.primary }} data-testid={heroPrimaryCta.testId} testID={heroPrimaryCta.testId}>
                  <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>{heroPrimaryCta.label}</Text>
                </TouchableOpacity>
                {heroSecondaryCta ? (
                  <TouchableOpacity onPress={() => router.push(heroSecondaryCta.href as any)} style={{ paddingHorizontal: 16, paddingVertical: 11, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: `${C.card}B8` }} data-testid={heroSecondaryCta.testId} testID={heroSecondaryCta.testId}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{heroSecondaryCta.label}</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>

            <View style={{ maxWidth: 780, gap: 10 }}>
              <Text style={{ color: C.text, fontSize: isMobile ? 34 : isTablet ? 48 : 60, fontWeight: '900', letterSpacing: -2.2, lineHeight: isMobile ? 38 : isTablet ? 52 : 64 }} data-testid={`${testIdPrefix}-title`} testID={`${testIdPrefix}-title`}>
                {title}
              </Text>
              <Text style={{ color: C.textSec, fontSize: isMobile ? 14 : 16, lineHeight: isMobile ? 22 : 26, maxWidth: 700 }} data-testid={`${testIdPrefix}-subtitle`} testID={`${testIdPrefix}-subtitle`}>
                {subtitle}
              </Text>
            </View>

            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, flexWrap: 'wrap' }} data-testid={`${testIdPrefix}-meta-strip`} testID={`${testIdPrefix}-meta-strip`}>
              {metaItems.map((item, idx) => (
                <View key={item} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: `${C.card}C4` }} data-testid={`${testIdPrefix}-meta-item-${idx}`} testID={`${testIdPrefix}-meta-item-${idx}`}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{item}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid={`${testIdPrefix}-family-links`} testID={`${testIdPrefix}-family-links`}>
        {familyLinks.map((link) => (
          <TouchableOpacity accessibilityLabel={t('common.interactiveElement')}
            key={link.id}
            disabled={link.active}
            onPress={() => router.push(link.href as any)}
            style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999, borderWidth: 1, borderColor: link.active ? `${C.primary}55` : C.border, backgroundColor: link.active ? `${C.primary}12` : C.card }}
            data-testid={`${testIdPrefix}-family-link-${link.id}`}
            testID={`${testIdPrefix}-family-link-${link.id}`}
          >
            <Text style={{ color: link.active ? C.primary : C.text, fontSize: 12, fontWeight: '800' }}>{link.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ gap: 12 }} data-testid={`${testIdPrefix}-summary-grid`} testID={`${testIdPrefix}-summary-grid`}>
        <Text style={{ color: C.text, fontSize: isMobile ? 20 : 26, fontWeight: '800' }}>{summaryTitle}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {trustFacts.map((fact) => (
            <View key={fact.id} style={{ flexBasis: isMobile ? '100%' : isTablet ? '48%' : '24%', flexGrow: 1, minWidth: isMobile ? 0 : 220, borderWidth: 1, borderColor: C.border, borderRadius: 20, padding: 18, backgroundColor: C.card }} data-testid={`${testIdPrefix}-summary-card-${fact.id}`} testID={`${testIdPrefix}-summary-card-${fact.id}`}>
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
        <View style={{ flex: isMobile ? undefined : 1.2, borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad }} data-testid={`${testIdPrefix}-whats-new`} testID={`${testIdPrefix}-whats-new`}>
          <Text style={{ color: C.text, fontSize: 19, fontWeight: '800', marginBottom: 10 }}>{changeLogTitle}</Text>
          <View style={{ gap: 10 }}>
            {changeLogItems.map((item, idx) => (
              <View key={item} style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }} data-testid={`${testIdPrefix}-changelog-item-${idx}`} testID={`${testIdPrefix}-changelog-item-${idx}`}>
                <View style={{ width: 24, height: 24, borderRadius: 999, alignItems: 'center', justifyContent: 'center', backgroundColor: `${C.success}18`, marginTop: 1 }}>
                  <Ionicons name="checkmark" size={14} color={C.success} />
                </View>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, flex: 1 }}>{item}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad }} data-testid={`${testIdPrefix}-trust-panel`} testID={`${testIdPrefix}-trust-panel`}>
          <Text style={{ color: C.text, fontSize: 19, fontWeight: '800', marginBottom: 10 }}>{trustPanelTitle}</Text>
          <View style={{ gap: 12 }}>
            {trustPanelItems.map((item, idx) => (
              <View key={item} style={{ flexDirection: 'row', gap: 10 }} data-testid={`${testIdPrefix}-trust-item-${idx}`} testID={`${testIdPrefix}-trust-item-${idx}`}>
                <Ionicons name="arrow-forward-circle-outline" size={18} color={C.primary} style={{ marginTop: 2 }} />
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, flex: 1 }}>{item}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 18, alignItems: 'flex-start' }}>
        <View style={[{ width: isMobile ? '100%' : 280, gap: 14 }, stickyStyle]} data-testid={`${testIdPrefix}-sidebar`} testID={`${testIdPrefix}-sidebar`}>
          <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 16 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }}>{sidebarTitle}</Text>
            <TextInput
              value={searchQuery}
              onChangeText={setSearchQuery}
              placeholder={sidebarSearchPlaceholder}
              placeholderTextColor={C.textMuted}
              style={{ borderWidth: 1, borderColor: C.border, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, color: C.text, backgroundColor: C.cardSoft, marginBottom: 12 }}
              data-testid={`${testIdPrefix}-search-input`}
              testID={`${testIdPrefix}-search-input`}
            />
            <View style={{ gap: 8 }}>
              {filteredSections.map((section) => {
                const active = activeSectionData?.id === section.id;
                return (
                  <TouchableOpacity key={section.id} onPress={() => setActiveSection(section.id)} style={{ borderRadius: 14, paddingHorizontal: 12, paddingVertical: 11, borderWidth: 1, borderColor: active ? `${C.primary}66` : C.border, backgroundColor: active ? `${C.primary}14` : C.card }} data-testid={`${testIdPrefix}-nav-${section.id}`} testID={`${testIdPrefix}-nav-${section.id}`}>
                    <Text style={{ color: active ? C.primary : C.text, fontSize: 13, fontWeight: '700', marginBottom: 4 }}>{section.title}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 11, lineHeight: 17 }}>{section.summary}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 16 }} data-testid={`${testIdPrefix}-sticky-cta-card`} testID={`${testIdPrefix}-sticky-cta-card`}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '800', marginBottom: 8 }}>{sidebarCtaTitle}</Text>
            <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 20, marginBottom: 12 }}>{sidebarCtaBody}</Text>
            <TouchableOpacity onPress={() => router.push(sidebarCtaHref as any)} style={{ borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: C.primary }} data-testid={`${testIdPrefix}-sidebar-cta`} testID={`${testIdPrefix}-sidebar-cta`}>
              <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>{sidebarCtaLabel}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flex: 1, gap: 16 }} data-testid={`${testIdPrefix}-reading-pane`} testID={`${testIdPrefix}-reading-pane`}>
          {filteredSections.map((section) => (
            <View key={section.id} style={{ borderRadius: 24, borderWidth: 1, borderColor: activeSectionData?.id === section.id ? `${C.primary}55` : C.border, backgroundColor: C.card, padding: pad }} data-testid={`${testIdPrefix}-section-${section.id}`} testID={`${testIdPrefix}-section-${section.id}`}>
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
                <TouchableOpacity onPress={() => setActiveSection(section.id)} style={{ alignSelf: isMobile ? 'flex-start' : 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardSoft }} data-testid={`${testIdPrefix}-focus-${section.id}`} testID={`${testIdPrefix}-focus-${section.id}`}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{pinSectionLabel}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ gap: 12 }}>
                {section.paragraphs.map((paragraph, idx) => (
                  <Text key={`${section.id}-paragraph-${idx}`} style={{ color: C.textSec, fontSize: 14, lineHeight: 24 }} data-testid={`${testIdPrefix}-section-${section.id}-paragraph-${idx}`} testID={`${testIdPrefix}-section-${section.id}-paragraph-${idx}`}>
                    {paragraph}
                  </Text>
                ))}

                {section.bullets?.length ? (
                  <View style={{ gap: 8, marginTop: 4 }}>
                    {section.bullets.map((bullet, idx) => (
                      <View key={`${section.id}-bullet-${idx}`} style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }} data-testid={`${testIdPrefix}-section-${section.id}-bullet-${idx}`} testID={`${testIdPrefix}-section-${section.id}-bullet-${idx}`}>
                        <Ionicons name="checkmark-circle" size={18} color={C.success} style={{ marginTop: 2 }} />
                        <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 22, flex: 1 }}>{bullet}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}

                {section.facts?.length ? (
                  <View style={{ marginTop: 8, borderRadius: 18, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid={`${testIdPrefix}-section-${section.id}-facts`} testID={`${testIdPrefix}-section-${section.id}-facts`}>
                    {section.facts.map((fact, idx) => (
                      <View key={`${section.id}-fact-${idx}`} style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, paddingHorizontal: 16, paddingVertical: 14, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border, backgroundColor: idx % 2 === 0 ? C.card : C.cardSoft }} data-testid={`${testIdPrefix}-section-${section.id}-fact-${idx}`} testID={`${testIdPrefix}-section-${section.id}-fact-${idx}`}>
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

      <View style={{ borderRadius: 28, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, overflow: 'hidden' }} data-testid={`${testIdPrefix}-action-hub`} testID={`${testIdPrefix}-action-hub`}>
        <View style={{ padding: pad, gap: 12, backgroundColor: `${C.primary}0F` }}>
          <Text style={{ color: C.text, fontSize: isMobile ? 22 : 28, fontWeight: '900', letterSpacing: -0.8 }}>{actionHubTitle}</Text>
          <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 24, maxWidth: 760 }}>{actionHubSubtitle}</Text>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, padding: pad }}>
          {actionCards.map((card) => {
            const tone = ({ error: C.error, warning: C.warning, success: C.success } as Record<string, string>)[card.tone || ''] || card.tone || C.primary;
            return (
              <TouchableOpacity key={card.id} onPress={() => router.push(card.href as any)} style={{ flexBasis: isMobile ? '100%' : isTablet ? '48%' : '31%', flexGrow: 1, minWidth: isMobile ? 0 : 240, borderWidth: 1, borderColor: `${tone}44`, backgroundColor: `${tone}10`, borderRadius: 20, padding: 18 }} data-testid={`${testIdPrefix}-action-card-${card.id}`} testID={`${testIdPrefix}-action-card-${card.id}`}>
                <View style={{ width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: `${tone}18`, marginBottom: 14 }}>
                  <Ionicons name={card.icon} size={20} color={tone} />
                </View>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 8 }}>{card.title}</Text>
                <Text style={{ color: C.textSec, fontSize: 13, lineHeight: 21, marginBottom: 14 }}>{card.body}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: tone, fontSize: 12, fontWeight: '800' }}>{actionHubOpenLabel}</Text>
                  <Ionicons name="arrow-forward" size={14} color={tone} />
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: pad, gap: 14 }} data-testid={`${testIdPrefix}-contact-panel`} testID={`${testIdPrefix}-contact-panel`}>
        <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{contactTitle}</Text>
        <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 24 }}>{contactBody}</Text>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', flexWrap: 'wrap', gap: 12 }}>
          {contactItems.map((item) => (
            <View key={item.id} style={{ flex: isMobile ? undefined : 1, minWidth: isMobile ? 0 : 220, borderRadius: 16, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardSoft, padding: 14 }} data-testid={`${testIdPrefix}-contact-item-${item.id}`} testID={`${testIdPrefix}-contact-item-${item.id}`}>
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
  );
};