import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import { useAppStore } from '../src/store/appStore';
import AppShell from '../src/components/AppShell';
import { AchievementsSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import api from '../src/services/api';
import { useTranslation } from '../src/hooks/useTranslation';

interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  xp_reward: number;
}

export default function AchievementsScreen() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { userId, hasHydrated, initializeUser } = useAppStore();
  const { t } = useTranslation();
  const [earned, setEarned] = useState<Achievement[]>([]);
  const [unearned, setUnearned] = useState<Achievement[]>([]);
  const [loading, setLoading] = useState(true);

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, card: colors.card, border: colors.border,
    text: colors.text, muted: colors.textMuted, primary: colors.primary,
    success: colors.success, bgSoft: colors.bgSoft,
  }), [colors]);
  const onPrimary = colors.primaryText || colors.buttonText || colors.card;

  const effectiveUserId = user?.user_id || userId;

  const loadAchievements = useCallback(async () => {
    if (!effectiveUserId) return;
    try {
      const response = await api.get(`/achievements/${effectiveUserId}`);
      setEarned(response.data.earned || []);
      setUnearned(response.data.unearned || []);
    } catch (error) {
      console.error('Error loading achievements:', error);
    } finally {
      setLoading(false);
    }
  }, [effectiveUserId]);

  useEffect(() => {
    if (!hasHydrated) return;
    void initializeUser();
  }, [hasHydrated, initializeUser]);

  useEffect(() => { void loadAchievements(); }, [loadAchievements]);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { void loadAchievements(); }, 30000);
    return () => clearInterval(_autoRefresh);
  }, [loadAchievements]);

  const getIconName = (iconName: string): keyof typeof Ionicons.glyphMap => {
    const iconMap: Record<string, keyof typeof Ionicons.glyphMap> = {
      'chatbubble': 'chatbubble', 'trending-up': 'trending-up', 'star': 'star',
      'ribbon': 'ribbon', 'trophy': 'trophy', 'heart': 'heart', 'briefcase': 'briefcase',
      'people': 'people', 'home': 'home', 'globe': 'globe', 'shield-checkmark': 'shield-checkmark',
      'flame': 'flame', 'medal': 'medal', 'rocket': 'rocket', 'diamond': 'diamond',
      'heart-circle': 'heart-circle', 'apps': 'apps',
    };
    return iconMap[iconName] || 'star';
  };

  if (!hasHydrated || loading) {
    return (
      <AppShell>
        <AchievementsSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <FadeSlideIn>
      <View style={{ flex: 1 }}>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: isWide ? 32 : 16, paddingBottom: 60 }} data-testid="achievements-page" testID="achievements-page">
          {/* Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 24 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: isWide ? 28 : 22, fontWeight: '800', color: C.text, letterSpacing: -0.5 }} data-testid="achievements-title" testID="achievements-title">{t('achievements.title')}</Text>
              <Text style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>{t('achievements.subtitle')}</Text>
            </View>
            <View style={{ backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 12 }} data-testid="achievements-count-badge" testID="achievements-count-badge">
              <Text style={{ color: onPrimary, fontWeight: '700', fontSize: 14 }}>{earned.length}/{earned.length + unearned.length}</Text>
            </View>
          </View>

          {/* Earned Section */}
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>{t('achievements.earned')}</Text>
          {earned.length === 0 ? (
            <View style={{ backgroundColor: C.card, padding: 24, borderRadius: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
              <Ionicons name="trophy-outline" size={28} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 14, marginTop: 8 }}>{t('achievements.empty')}</Text>
            </View>
          ) : (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              {earned.map((a) => (
                <View key={a.id} style={{
                  width: isWide ? '48%' : '47%', backgroundColor: C.card, borderRadius: 14, padding: 16,
                  alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '40'),
                }} data-testid={`achievement-earned-${a.id}`} testID={`achievement-earned-${a.id}`}>
                  <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: (globalThis as any).__alphaColor(C.primary, '18'), alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
                    <Ionicons name={getIconName(a.icon)} size={24} color={C.primary} />
                  </View>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, textAlign: 'center', marginBottom: 4 }}>{a.name}</Text>
                  <Text style={{ fontSize: 11, color: C.muted, textAlign: 'center', marginBottom: 8 }}>{a.description}</Text>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '18'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                    <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>+{a.xp_reward} XP</Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* Locked Section */}
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12, marginTop: 12 }}>{t('achievements.locked')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {unearned.map((a) => (
              <View key={a.id} style={{
                width: isWide ? '48%' : '47%', backgroundColor: C.card, borderRadius: 14, padding: 16,
                alignItems: 'center', opacity: 0.6, borderWidth: 1, borderColor: C.border,
              }} data-testid={`achievement-locked-${a.id}`} testID={`achievement-locked-${a.id}`}>
                <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
                  <Ionicons name={getIconName(a.icon)} size={24} color={C.muted} />
                </View>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.muted, textAlign: 'center', marginBottom: 4 }}>{a.name}</Text>
                <Text style={{ fontSize: 11, color: C.muted, textAlign: 'center', marginBottom: 8 }}>{a.description}</Text>
                <View style={{ backgroundColor: C.bgSoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                  <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700' }}>+{a.xp_reward} XP</Text>
                </View>
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
      </FadeSlideIn>
    </AppShell>
  );
}
