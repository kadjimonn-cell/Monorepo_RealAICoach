import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import AppShell from '../../src/components/AppShell';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

export function InterviewCoachContent() {
  const { colors: theme, accentColor } = useTheme();

  // @autofix-moved: was module-level const PRACTICE_CATEGORIES
  const PRACTICE_CATEGORIES = [
    { 
      id: 'roleplay', title: 'Roleplay Arena', desc: 'Real-world AI simulations', icon: 'people', color: theme.primary,
      scenarios: [
        { id: 'interview', title: 'Job Interview', subtitle: 'Tech & Behavioral', icon: 'briefcase', xp: 50 },
        { id: 'salary', title: 'Salary Negotiation', subtitle: 'Business Skills', icon: 'cash', xp: 40 },
        { id: 'dating', title: 'First Date', subtitle: 'Social Skills', icon: 'heart', xp: 30 },
        { id: 'presentation', title: 'Sales Pitch', subtitle: 'Persuasion', icon: 'megaphone', xp: 45 },
      ]
    },
    { 
      id: 'language', title: 'Language Lab', desc: 'Immersive language practice', icon: 'language', color: theme.successText,
      scenarios: [
        { id: 'spanish_cafe', title: 'Order Coffee', subtitle: 'Spanish', icon: 'cafe', xp: 25 },
        { id: 'french_hotel', title: 'Hotel Check-in', subtitle: 'French', icon: 'bed', xp: 30 },
        { id: 'mandarin_market', title: 'Market Bargaining', subtitle: 'Mandarin', icon: 'cart', xp: 35 },
      ]
    },
    { 
      id: 'debate', title: 'Debate Club', desc: 'Critical thinking mastery', icon: 'chatbubbles', color: theme.warningText,
      scenarios: [
        { id: 'ai_ethics', title: 'AI Ethics', subtitle: 'Philosophy', icon: 'hardware-chip', xp: 40 },
        { id: 'climate', title: 'Climate Change', subtitle: 'Science', icon: 'leaf', xp: 35 },
        { id: 'economy', title: 'Economic Policy', subtitle: 'Politics', icon: 'stats-chart', xp: 45 },
      ]
    },
    {
      id: 'wellness', title: 'Wellness Coach', desc: 'Mental health & mindfulness', icon: 'flower', color: 'var(--app-primary)', // @theme-ok residual semantic hex (reviewed)
      scenarios: [
        { id: 'stress', title: 'Stress Relief', subtitle: 'Guided Session', icon: 'leaf', xp: 20 },
        { id: 'confidence', title: 'Build Confidence', subtitle: 'Self-Improvement', icon: 'trophy', xp: 30 },
      ]
    },
  ];
  const router = useRouter();
  const { user } = useAuth();
  const [streak, setStreak] = useState(0);
  const [totalXP, setTotalXP] = useState(0);
  const performanceScore = Math.min(100, 60 + streak * 4);
  const adaptiveTip = streak >= 3
    ? 'Increase difficulty for a stronger score jump.'
    : 'Complete one guided scenario to stabilize your streak.';
  const [refreshing, setRefreshing] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      const uid = user?.user_id;
      if (uid) {
        const res = await api.get(`/progress/${uid}`);
        setStreak(res.data?.streak_days || 0);
        setTotalXP(res.data?.total_xp || 0);
      }
    } catch (error) { handleAppRecoverableError({ scope: '(tabs)/practice.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setRefreshing(false); }
  }, [user?.user_id]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { void loadStats(); } catch (error) { handleAppRecoverableError({ scope: '(tabs)/practice.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  }, [loadStats]);

  const handleScenarioPress = (category: string, scenarioId: string) => {
    if (category === 'language') {
      router.push(`/features/school-tutor`);
    } else {
      router.push(`/features/ai-chatbot`);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.bg }} edges={['top']} >
    <ScrollView contentContainerStyle={{ paddingBottom: 100 }} showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadStats(); }} tintColor={accentColor} />}>
        
        {/* Header */}
        <View style={{ paddingHorizontal: 20, paddingTop: 16, paddingBottom: 20 }} accessibilityRole="header">
          <Text style={{ fontSize: 28, fontWeight: '800', color: theme.text, letterSpacing: -0.5 }} data-testid="practice-title" testID="practice-title">Practice Arena</Text>
          <Text style={{ fontSize: 14, color: theme.textSec, marginTop: 4 }}>Master skills through AI-powered simulations</Text>
        </View>

        {/* Stats Bar */}
        <View style={{ flexDirection: 'row', paddingHorizontal: 20, gap: 10, marginBottom: 20 }}>
          <View style={{ flex: 1, backgroundColor: theme.warningSoft, borderRadius: 14, padding: 14, alignItems: 'center' }} data-testid="practice-streak" testID="practice-streak">
            <Ionicons name="flame" size={22} color={theme.warningText} />
            <Text style={{ fontSize: 20, fontWeight: '800', color: theme.warningText, marginTop: 4 }}>{streak}</Text>
            <Text style={{ fontSize: 10, fontWeight: '600', color: theme.warningText }}>Day Streak</Text>
          </View>
          <View style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(accentColor, '18'), borderRadius: 14, padding: 14, alignItems: 'center' }} data-testid="practice-xp" testID="practice-xp">
            <Ionicons name="star" size={22} color={accentColor} />
            <Text style={{ fontSize: 20, fontWeight: '800', color: accentColor, marginTop: 4 }}>{totalXP}</Text>
            <Text style={{ fontSize: 10, fontWeight: '600', color: accentColor }}>Total XP</Text>
          </View>
          <View style={{ flex: 1, backgroundColor: theme.successSoft, borderRadius: 14, padding: 14, alignItems: 'center' }} data-testid="practice-scenarios" testID="practice-scenarios">
            <Ionicons name="layers" size={22} color={theme.successText} />
            <Text style={{ fontSize: 20, fontWeight: '800', color: theme.successText, marginTop: 4 }}>12</Text>
            <Text style={{ fontSize: 10, fontWeight: '600', color: theme.successText }}>Scenarios</Text>
          </View>
        </View>

        {/* AI Coach Panel */}
        <View style={{ marginHorizontal: 20, marginBottom: 24, backgroundColor: theme.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: theme.border }} data-testid="practice-ai-coach" testID="practice-ai-coach">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(accentColor, '12'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="sparkles" size={20} color={accentColor} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: theme.text }}>AI Coach Live</Text>
              <Text style={{ fontSize: 12, color: theme.textMuted, marginTop: 2 }}>Real-time guidance • adaptive plans</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 14 }}>
            <View style={{ flex: 1, backgroundColor: theme.bgSoft, borderRadius: 12, padding: 12 }}>
              <Text style={{ fontSize: 11, color: theme.textMuted }}>Performance score</Text>
              <Text style={{ fontSize: 18, fontWeight: '800', color: theme.text, marginTop: 4 }}>{performanceScore}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: theme.bgSoft, borderRadius: 12, padding: 12 }}>
              <Text style={{ fontSize: 11, color: theme.textMuted }}>Next focus</Text>
              <Text style={{ fontSize: 13, fontWeight: '700', color: theme.text, marginTop: 4 }}>Scenario depth</Text>
            </View>
          </View>
          <View style={{ marginTop: 12, padding: 12, backgroundColor: theme.bgSoft, borderRadius: 12 }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: theme.text }}>Adaptive recommendation</Text>
            <Text style={{ fontSize: 12, color: theme.textMuted, marginTop: 4 }}>{adaptiveTip}</Text>
          </View>
        </View>

        {/* Daily Challenge */}
        <TouchableOpacity 
          style={{ marginHorizontal: 20, marginBottom: 24, padding: 18, borderRadius: 16, backgroundColor: theme.card, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(accentColor, '30'), flexDirection: 'row', alignItems: 'center', gap: 14 }}
          onPress={() => router.push('/features/ai-speech')}
          data-testid="practice-daily-challenge" testID="practice-daily-challenge"
          accessibilityLabel="Daily Challenge: Public Speaking Elevator Pitch"
          accessibilityRole="button"
        >
          <View style={{ width: 50, height: 50, borderRadius: 15, backgroundColor: accentColor, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="trophy" size={24} color={theme.primaryText} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: accentColor, textTransform: 'uppercase', letterSpacing: 0.5 }}>Daily Challenge</Text>
            <Text style={{ fontSize: 16, fontWeight: '700', color: theme.text, marginTop: 2 }}>Public Speaking: Elevator Pitch</Text>
            <View style={{ backgroundColor: theme.warning, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, marginTop: 6 }}>
              <Text style={{ color: theme.primaryText, fontSize: 10, fontWeight: '800' }}>+50 XP</Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={18} color={theme.textMuted} />
        </TouchableOpacity>

        {/* Categories */}
        {PRACTICE_CATEGORIES.map((cat) => (
          <View key={cat.id} style={{ marginBottom: 24 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, marginBottom: 14, gap: 12 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(cat.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={cat.icon as any} size={20} color={cat.color} />
              </View>
              <View>
                <Text style={{ fontSize: 17, fontWeight: '700', color: theme.text }}>{cat.title}</Text>
                <Text style={{ fontSize: 12, color: theme.textMuted }}>{cat.desc}</Text>
              </View>
            </View>

            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 20, gap: 12 }}>
              {cat.scenarios.map((scene) => (
                <TouchableOpacity 
                  key={scene.id} 
                  style={{ width: 150, padding: 16, borderRadius: 16, backgroundColor: theme.card, borderWidth: 1, borderColor: theme.border, gap: 10 }}
                  onPress={() => handleScenarioPress(cat.id, scene.id)}
                  data-testid={`practice-scenario-${scene.id}`} testID={`practice-scenario-${scene.id}`}
                  accessibilityLabel={`${scene.title} - ${scene.subtitle}`}
                  accessibilityRole="button"
                >
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(cat.color, '12'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={scene.icon as any} size={20} color={cat.color} />
                  </View>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: theme.text }}>{scene.title}</Text>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ fontSize: 11, color: theme.textMuted }}>{scene.subtitle}</Text>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: theme.warningText }}>+{scene.xp} XP</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        ))}
    </ScrollView>
  </SafeAreaView>
  );
}

export default function PracticeScreen() {
  const { t } = useTranslation();
  t('i18n.route.(tabs).practice.probe');
  return (
    <AppShell>
      <InterviewCoachContent />
    </AppShell>
  );
}