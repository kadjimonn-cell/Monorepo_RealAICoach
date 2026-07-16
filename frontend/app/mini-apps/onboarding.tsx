import React, { useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../../src/components/AppShell';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import { GallerySkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

const ROLE_MAP: Record<string, string[]> = {
  employer: ['ai-accounting'],
  creator: ['local-music'],
  premium_user: ['ai-accounting'],
};

export default function MiniAppsOnboarding() {
  const pageReady = usePageReady();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const MINI_APPS
  const MINI_APPS = [
    { id: 'ai-accounting', title: 'AI Accounting', description: 'Income, expenses, and AI-powered profit forecasts.', route: '/mini-apps/ai-accounting', icon: 'calculator' as const, color: colors.warningText, category: 'Finance' },
    { id: 'local-music', title: 'Local Music Player', description: 'Upload, organize, and play your offline tracks.', route: '/mini-apps/local-music', icon: 'headset' as const, color: colors.accent, category: 'Entertainment' },
  ];
  const { user } = useAuth();
  const router = useRouter();

  const recommended = useMemo(() => {
    const roles = user?.roles || [];
    const ids = roles.includes('employer') ? ROLE_MAP.employer : roles.includes('creator') ? ROLE_MAP.creator : roles.includes('premium_user') ? ROLE_MAP.premium_user : ['ai-accounting'];
    return MINI_APPS.filter(a => ids.includes(a.id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const otherApps = MINI_APPS.filter(a => !recommended.find(r => r.id === a.id));

  if (!pageReady) return <AppShell><GallerySkeleton /></AppShell>;
  return (
    <AppShell>
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: 20, paddingBottom: 80 }} data-testid="onboarding-page" testID="onboarding-page">
        {/* Hero Section */}
        <View style={{ marginBottom: 28 }}>
          <Text style={{ fontSize: 11, fontWeight: '800', letterSpacing: 1.5, textTransform: 'uppercase', color: colors.primary, marginBottom: 8 }} data-testid="onboarding-kicker" testID="onboarding-kicker">{tx('miniAppsOnboarding.kicker', 'Personalized for You')}</Text>
          <Text style={{ fontSize: 26, fontWeight: '800', color: colors.text, marginBottom: 8 }} data-testid="onboarding-title" testID="onboarding-title">{tx('miniAppsOnboarding.title', 'Your Recommended Apps')}</Text>
          <Text style={{ fontSize: 14, color: colors.textMuted, lineHeight: 20, maxWidth: 500 }} data-testid="onboarding-subtitle" testID="onboarding-subtitle">
            {tx('miniAppsOnboarding.subtitle', 'Based on your profile, these apps will create the most value for you right now.')}
          </Text>
        </View>

        {/* Recommended Apps */}
        <View style={{ gap: 12, marginBottom: 28 }}>
          {recommended.map((app, i) => (
            <TouchableOpacity key={app.id} onPress={() => router.push(app.route)}
              style={{ backgroundColor: colors.card, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', gap: 14 }}
              data-testid={`onboarding-card-${app.id}`} testID={`onboarding-card-${app.id}`}>
              <View style={{ width: 50, height: 50, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(app.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={app.icon} size={24} color={app.color} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{app.title}</Text>
                  {i === 0 && (
                    <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                      <Text style={{ fontSize: 9, fontWeight: '800', color: colors.warningText }}>TOP PICK</Text>
                    </View>
                  )}
                </View>
                <Text style={{ fontSize: 12, color: colors.textMuted }}>{app.description}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Other Apps */}
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>Explore More</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
          {otherApps.map(app => (
            <TouchableOpacity key={app.id} onPress={() => router.push(app.route)}
              style={{ width: '47%', backgroundColor: colors.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }}
              data-testid={`onboarding-explore-${app.id}`} testID={`onboarding-explore-${app.id}`}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(app.color, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
                <Ionicons name={app.icon} size={18} color={app.color} />
              </View>
              <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, marginBottom: 2 }}>{app.title}</Text>
              <Text style={{ fontSize: 10, color: colors.textMuted }} numberOfLines={2}>{app.description}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity onPress={() => router.push('/mini-apps')}
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingVertical: 14, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 }}
          data-testid="onboarding-view-all" testID="onboarding-view-all">
          <Ionicons name="grid" size={16} color={colors.text} />
          <Text style={{ color: colors.text, fontWeight: '600', fontSize: 14 }}>View All Mini-Apps</Text>
        </TouchableOpacity>
      </ScrollView>
    </AppShell>
  );
}
