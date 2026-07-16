import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ImageBackground, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getShadow } from '../../utils/themeShadows';
import { type ThemeColors, type TabKey } from './helpTypes';
import { useFeatures } from '../../context/FeaturesContext';
import { useTheme } from '../../context/ThemeContext';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';

interface SupportHeroTabProps {
  C: ThemeColors;
  darkMode: boolean;
  isWide: boolean;
  L: (key: string, fallback?: string) => string;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  setActiveTab: (tab: TabKey) => void;
  setActiveCategory: (cat: string | null) => void;
  openNovaChat: () => void;
  openSupportEmail: () => void;
}

export default function SupportHeroTab({ C, darkMode, isWide, L, searchQuery, setSearchQuery, setActiveTab, setActiveCategory, openNovaChat, openSupportEmail }: SupportHeroTabProps) {
  const { colors } = useTheme();
  const { counts, state: gpsState } = useGlobalPlatformState();
  const HERO_BG = 'https://static.prod-images.emergentagent.com/jobs/059e794e-68ab-4310-a71c-8f17ea3e2d2d/images/a6cc0fea69150c89bc9e96e959e4adb023897bfb95d6f6594629773200959f63.png';
  const AVATARS = [
    'https://images.pexels.com/photos/7682342/pexels-photo-7682342.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940',
    'https://images.pexels.com/photos/7709237/pexels-photo-7709237.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940',
  ];

  // @autofix-moved: was module-level const s
  const s = StyleSheet.create({
    heroCard: { borderRadius: 20, borderWidth: 1, overflow: 'hidden', marginBottom: 18 },
    heroBg: { ...StyleSheet.absoluteFillObject },
    heroContent: { padding: 22 },
    heroBadge: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, marginBottom: 12, borderWidth: 1 },
    heroBadgeText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.8 },
    heroTitle: { fontSize: 30, fontWeight: '800', letterSpacing: -0.8, marginBottom: 6 },
    heroSubtitle: { fontSize: 14, lineHeight: 22, maxWidth: 960 },
    heroSearch: { flexDirection: 'row', alignItems: 'center', borderRadius: 14, paddingHorizontal: 14, borderWidth: 1, marginTop: 16 },
    heroSearchInput: { flex: 1, paddingVertical: 12, marginLeft: 10, fontSize: 15 },
    heroMetaRow: { marginTop: 14, flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    heroMetaPill: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, flexDirection: 'row', alignItems: 'center', gap: 6 },
    statsRow: { gap: 10, marginBottom: 22, flexDirection: 'row', flexWrap: 'wrap' },
    statCard: { borderRadius: 14, borderWidth: 1, padding: 14, minHeight: 108 },
    statTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    statIcon: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    statValue: { fontSize: 20, fontWeight: '800', marginTop: 12 },
    statLabel: { fontSize: 12, fontWeight: '600', marginTop: 4 },
    sectionTitle: { fontSize: 17, fontWeight: '800', letterSpacing: -0.2, marginBottom: 12 },
    actionsGrid: { gap: 10, marginBottom: 22, flexDirection: 'row', flexWrap: 'wrap' },
    actionCard: { borderRadius: 14, borderWidth: 1, padding: 16, minHeight: 122, justifyContent: 'space-between' },
    actionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    actionIconWrap: { width: 38, height: 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    actionTitle: { fontSize: 14, fontWeight: '800', marginTop: 12 },
    actionDesc: { fontSize: 12, lineHeight: 18, marginTop: 4 },
    topicsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 22 },
    topicCard: { borderRadius: 16, borderWidth: 1, padding: 16, minHeight: 174 },
    topicTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
    topicIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    topicTitle: { fontSize: 14, fontWeight: '800' },
    topicDesc: { fontSize: 12, lineHeight: 18, marginBottom: 10 },
    topicLinkRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6 },
    topicLinkText: { fontSize: 12, fontWeight: '600' },
    supportEntryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 10 },
    supportEntryCard: { borderRadius: 16, borderWidth: 1, padding: 16, minHeight: 152 },
    supportIconWrap: { width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
    supportEntryTitle: { fontSize: 15, fontWeight: '800', marginBottom: 4 },
    supportEntryDesc: { fontSize: 12, lineHeight: 18, marginBottom: 12 },
    supportCta: { borderRadius: 10, paddingVertical: 10, paddingHorizontal: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
    supportCtaText: { fontSize: 12, fontWeight: '800' },
    avatarStack: { flexDirection: 'row', marginTop: 14 },
    avatarWrap: { width: 30, height: 30, borderRadius: 15, borderWidth: 2, overflow: 'hidden', marginLeft: -8 },
    avatar: { width: '100%', height: '100%' },
  });

  const { totalCount } = useFeatures();
  const featureCount = totalCount || counts.features || 0;
  const platformStats = [
    { value: String(featureCount), label: L('stats_features', 'Features'), icon: 'sparkles', color: colors.accent },
    { value: String(counts.plans || 0), label: L('stats_plans', 'Plans'), icon: 'card', color: colors.primary },
    { value: String(counts.faq || 0), label: L('stats_faq', 'FAQ'), icon: 'help-circle', color: colors.success },
  ];
  const topicCategories = React.useMemo(() => {
    const keys = Array.from(new Set((gpsState?.faq || []).filter((faq) => faq.active !== false).map((faq) => faq.category).filter(Boolean)));
    return keys.map((key) => ({ key, label: String(key).replace(/[-_]/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()), icon: 'ellipse', color: colors.accent }));
  }, [colors.accent, gpsState?.faq]);

  const quickActions = [
    { key: 'chat', title: L('chat_nova', 'Chat with Nova'), desc: L('chat_nova_desc', 'Instant AI-powered answers with escalation to human support.'), icon: 'chatbubbles', color: colors.success, onPress: openNovaChat },
    { key: 'faq', title: L('browse_faq', 'Browse FAQ'), desc: L('browse_faq_desc', 'Get vetted answers for policy, billing, and platform operations.'), icon: 'help-circle', color: colors.info, onPress: () => setActiveTab('faq') },
    { key: 'features', title: L('feature_index', 'Feature Index'), desc: L('feature_index_desc', `Explore all ${featureCount} AI copilots and capability guides.`), icon: 'apps', color: colors.accent, onPress: () => setActiveTab('features') },
    { key: 'billing', title: L('plans_billing', 'Plans & Billing'), desc: L('plans_billing_desc', 'Manage invoices, subscriptions, and payment operations.'), icon: 'card', color: colors.purple, onPress: () => { setActiveCategory('billing'); setActiveTab('faq'); } },
  ];

  const articleSeeds = [
    L('help_article_seed_1', 'Setup Checklist'),
    L('help_article_seed_2', 'Troubleshooting Guide'),
    L('help_article_seed_3', 'Best Practices'),
  ];

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
      <View data-testid="support-hero" testID="support-hero" style={[s.heroCard, { backgroundColor: C.card, borderColor: C.border }, getShadow('md', darkMode)]}>
        <ImageBackground source={{ uri: HERO_BG }} resizeMode="cover" imageStyle={{ opacity: darkMode ? 0.16 : 0.1 }} style={s.heroBg} />
        <View style={s.heroContent}>
          <View style={[s.heroBadge, { backgroundColor: colors.infoSoft, borderColor: (globalThis as any).__alphaColor(colors.info, '42') }]}>
            <Text data-testid="support-hero-badge" style={[s.heroBadgeText, { color: colors.infoText }]}>{L('help_center', 'HELP CENTER')}</Text>
          </View>
          <Text data-testid="support-hero-title" style={[s.heroTitle, { color: C.text }]}>{L('how_help', 'Enterprise Help & Support')}</Text>
          <Text style={[s.heroSubtitle, { color: C.textSec }]}>
            {L('hero_desc', 'Resolve platform issues faster with structured playbooks, assisted guidance, and direct support channels.')}
          </Text>
          <View style={[s.heroSearch, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
            <Ionicons name="search" size={20} color={C.textMuted} />
            <TextInput
              data-testid="support-hero-search" testID="support-hero-search"
              style={[s.heroSearchInput, { color: C.text }]}
              placeholder={L('search_help', 'Search policies, billing, integrations, or troubleshooting...')}
              placeholderTextColor={C.textMuted}
              value={searchQuery}
              onChangeText={(t) => { setSearchQuery(t); if (t.trim()) setActiveTab('faq'); }}
            />
          </View>
          <View style={s.heroMetaRow}>
            <View data-testid="support-hero-sla-pill" style={[s.heroMetaPill, { borderColor: (globalThis as any).__alphaColor(colors.success, '44'), backgroundColor: colors.successSoft }]}>
              <Ionicons name="time-outline" size={14} color={colors.successText} />
              <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{L('avg_response', 'Avg. response < 2h')}</Text>
            </View>
            <View data-testid="support-hero-coverage-pill" style={[s.heroMetaPill, { borderColor: (globalThis as any).__alphaColor(colors.primary, '44'), backgroundColor: colors.primarySoft }]}>
              <Ionicons name="shield-checkmark-outline" size={14} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{L('enterprise_coverage', 'Enterprise-grade coverage')}</Text>
            </View>
          </View>
        </View>
      </View>

      <View style={s.statsRow} data-testid="support-stats" testID="support-stats">
        {platformStats.map((stat) => {
          const value = stat.value;
          return (
            <View key={stat.label} style={[s.statCard, { backgroundColor: C.card, borderColor: C.border }, isWide ? { flex: 1, minWidth: 0 } : { width: '48%' }, getShadow('sm', darkMode)]} data-testid={`stat-${stat.label.toLowerCase().replace(/\s/g, '-')}`} testID={`stat-${stat.label.toLowerCase().replace(/\s/g, '-')}`}>
              <View style={s.statTop}>
                <View style={[s.statIcon, { backgroundColor: (globalThis as any).__alphaColor(stat.color, '18') }]}>
                  <Ionicons name={stat.icon as any} size={18} color={stat.color} />
                </View>
                <Ionicons name="trending-up-outline" size={14} color={C.textMuted} />
              </View>
              <Text style={[s.statValue, { color: C.text }]}>{value}</Text>
              <Text style={[s.statLabel, { color: C.textMuted }]}>{stat.label}</Text>
            </View>
          );
        })}
      </View>

      <Text data-testid="quick-actions-title" style={[s.sectionTitle, { color: C.text }]}>{L('quick_actions', 'Quick Actions')}</Text>
      <View style={s.actionsGrid}>
        {quickActions.map((item) => (
          <TouchableOpacity
            key={item.key}
            data-testid={`action-${item.key}`}
            testID={`action-${item.key}`}
            style={[s.actionCard, { backgroundColor: C.card, borderColor: C.border }, isWide ? { width: '23.5%' } : { width: '48%' }, getShadow('sm', darkMode)]}
            onPress={item.onPress}
          >
            <View style={s.actionHead}>
              <View style={[s.actionIconWrap, { backgroundColor: (globalThis as any).__alphaColor(item.color, '16') }]}>
                <Ionicons name={item.icon as any} size={20} color={item.color} />
              </View>
              <Ionicons name="arrow-forward-outline" size={16} color={C.textMuted} />
            </View>
            <Text style={[s.actionTitle, { color: C.text }]}>{item.title}</Text>
            <Text style={[s.actionDesc, { color: C.textMuted }]}>{item.desc}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text data-testid="popular-topics-title" style={[s.sectionTitle, { color: C.text }]}>{L('popular_topics', 'Popular Topics')}</Text>
      <View style={s.topicsGrid}>
        {topicCategories.map((meta) => (
          <TouchableOpacity key={meta.key} data-testid={`topic-${meta.key}`} testID={`topic-${meta.key}`} style={[s.topicCard, { backgroundColor: C.bgSoft, borderColor: C.border }, isWide ? { width: '31.8%' } : { width: '48%' }, getShadow('sm', darkMode)]}
            onPress={() => { setActiveCategory(meta.key); setActiveTab('faq'); }}>
            <View style={s.topicTitleRow}>
              <View style={[s.topicIcon, { backgroundColor: (globalThis as any).__alphaColor(meta.color, '16') }]}> 
                <Ionicons name={meta.icon as any} size={18} color={meta.color} />
              </View>
              <Text style={[s.topicTitle, { color: C.text }]}>{meta.label}</Text>
            </View>
            <Text style={[s.topicDesc, { color: C.textMuted }]}>{L(`topic_${meta.key}_desc`, '')}</Text>
            {articleSeeds.map((article, idx) => (
              <View key={`${meta.key}-${idx}`} style={s.topicLinkRow}>
                <Text data-testid={`topic-link-${meta.key}-${idx}`} style={[s.topicLinkText, { color: C.textSec }]}>{article}</Text>
                <Ionicons name="chevron-forward" size={13} color={C.textMuted} />
              </View>
            ))}
          </TouchableOpacity>
        ))}
      </View>

      <Text data-testid="support-access-title" style={[s.sectionTitle, { color: C.text }]}>{L('support_access', 'Direct Support Access')}</Text>
      <View style={s.supportEntryGrid}>
        <View data-testid="support-entry-chat" style={[s.supportEntryCard, { backgroundColor: C.card, borderColor: C.border }, isWide ? { width: '49%' } : { width: '100%' }, getShadow('sm', darkMode)]}>
          <View style={[s.supportIconWrap, { backgroundColor: colors.successSoft }]}>
            <Ionicons name="chatbubbles" size={22} color={colors.successText} />
          </View>
          <Text style={[s.supportEntryTitle, { color: C.text }]}>{L('chat_with_team', 'Chat with Support Team')}</Text>
          <Text style={[s.supportEntryDesc, { color: C.textMuted }]}>{L('chat_with_team_desc', 'Start a live assistance thread for incidents, account blockers, and urgent platform issues.')}</Text>
          <TouchableOpacity data-testid="support-entry-chat-button" testID="support-entry-chat-button" style={[s.supportCta, { backgroundColor: colors.success }]} onPress={openNovaChat}>
            <Ionicons name="flash-outline" size={15} color={colors.primaryText} />
            <Text style={[s.supportCtaText, { color: colors.primaryText }]}>{L('start_live_chat', 'Start Live Chat')}</Text>
          </TouchableOpacity>
          <View style={s.avatarStack} data-testid="support-entry-chat-avatars">
            {AVATARS.map((avatar, idx) => (
              <View key={`chat-avatar-${idx}`} style={[s.avatarWrap, { borderColor: C.card, marginLeft: idx === 0 ? 0 : -8 }]}>
                <Image accessibilityLabel="Decorative image"
                  source={{ uri: avatar }}
                  style={s.avatar}
                  resizeMode="cover"
                />
              </View>
            ))}
          </View>
        </View>

        <View data-testid="support-entry-email" style={[s.supportEntryCard, { backgroundColor: C.card, borderColor: C.border }, isWide ? { width: '49%' } : { width: '100%' }, getShadow('sm', darkMode)]}>
          <View style={[s.supportIconWrap, { backgroundColor: colors.primarySoft }]}>
            <Ionicons name="mail" size={22} color={colors.primary} />
          </View>
          <Text style={[s.supportEntryTitle, { color: C.text }]}>{L('email_support', 'Email Enterprise Support')}</Text>
          <Text style={[s.supportEntryDesc, { color: C.textMuted }]}>{L('email_support_enterprise_desc', 'Route billing, compliance, or account requests directly to our support desk.')}</Text>
          <TouchableOpacity data-testid="support-entry-email-button" testID="support-entry-email-button" style={[s.supportCta, { backgroundColor: colors.primary }]} onPress={openSupportEmail}>
            <Ionicons name="send-outline" size={15} color={colors.primaryText} />
            <Text style={[s.supportCtaText, { color: colors.primaryText }]}>{L('open_email_form', 'Open Email Form')}</Text>
          </TouchableOpacity>
          <Text data-testid="support-entry-email-address" style={{ marginTop: 12, fontSize: 12, color: C.textSec, fontWeight: '700' }}>support@realaicoach.app</Text>
        </View>
      </View>
    </ScrollView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
