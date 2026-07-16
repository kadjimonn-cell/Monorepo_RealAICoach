import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useAppStore } from '../../src/store/appStore';
import { useAuth } from '../../src/context/AuthContext';
import { getScenario, startConversation } from '../../src/services/api';
import { AIFeatureSkeleton } from '../../src/components/SkeletonLoaders';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

const scenarioColors = {
  primary: '#14B8A6',
  primaryLight: '#14B8A6',
  background: '#0F0A1A', // @theme-ok residual semantic hex (reviewed)
  cardBg: '#1A1225',
  text: '#0F172A', // @theme-ok dark-text-on-light-card
  textMuted: '#9CA3AF',
  success: '#10B981',
  warning: '#F59E0B',
  dating: '#F472B6',
  workplace: '#0F766E',
  friendship: '#10B981',
};

const COLORS = scenarioColors;

const CATEGORY_ICONS: { [key: string]: keyof typeof Ionicons.glyphMap } = {
  dating: 'heart',
  workplace: 'briefcase',
  friendship: 'people',
};

export default function ScenarioDetailScreen() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: COLORS.background,
    },
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    errorText: {
      color: COLORS.textMuted,
      fontSize: 16,
      marginBottom: 16,
    },
    backButton: {
      paddingHorizontal: 20,
      paddingVertical: 10,
      backgroundColor: COLORS.primary,
      borderRadius: 8,
    },
    backButtonText: {
      color: COLORS.text,
      fontWeight: '600',
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingVertical: 12,
    },
    backIcon: {
      width: 40,
      height: 40,
      justifyContent: 'center',
      alignItems: 'center',
    },
    headerTitle: {
      fontSize: 18,
      fontWeight: '600',
      color: COLORS.text,
    },
    heroSection: {
      alignItems: 'center',
      paddingVertical: 32,
      paddingHorizontal: 20,
      marginHorizontal: 20,
      borderRadius: 24,
      marginBottom: 24,
    },
    iconContainer: {
      width: 100,
      height: 100,
      borderRadius: 30,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 16,
    },
    title: {
      fontSize: 24,
      fontWeight: 'bold',
      color: COLORS.text,
      textAlign: 'center',
      marginBottom: 16,
    },
    badgesRow: {
      flexDirection: 'row',
      gap: 10,
    },
    badge: {
      paddingHorizontal: 14,
      paddingVertical: 6,
      borderRadius: 16,
    },
    badgeText: {
      fontSize: 13,
      fontWeight: '600',
      color: COLORS.text,
      textTransform: 'capitalize',
    },
    difficultyBeginner: {
      backgroundColor: colors.successSoft,
    },
    difficultyIntermediate: {
      backgroundColor: colors.warningSoft,
    },
    difficultyAdvanced: {
      backgroundColor: colors.errorSoft,
    },
    section: {
      paddingHorizontal: 20,
      marginBottom: 24,
    },
    sectionTitle: {
      fontSize: 18,
      fontWeight: 'bold',
      color: COLORS.text,
      marginBottom: 12,
    },
    description: {
      fontSize: 15,
      color: COLORS.textMuted,
      lineHeight: 24,
    },
    personaCard: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: COLORS.cardBg,
      borderRadius: 16,
      padding: 16,
      marginBottom: 12,
    },
    personaAvatar: {
      marginRight: 14,
    },
    personaInfo: {
      flex: 1,
    },
    personaName: {
      fontSize: 18,
      fontWeight: 'bold',
      color: COLORS.text,
      marginBottom: 4,
    },
    personaDescription: {
      fontSize: 14,
      color: COLORS.textMuted,
      lineHeight: 20,
    },
    personalityBox: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      backgroundColor: (globalThis as any).__alphaColor(COLORS.warning, '15'),
      borderRadius: 12,
      padding: 14,
      gap: 10,
    },
    personalityText: {
      flex: 1,
      fontSize: 14,
      color: COLORS.textMuted,
      lineHeight: 20,
    },
    personalityLabel: {
      fontWeight: '600',
      color: COLORS.text,
    },
    objectiveItem: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: 12,
    },
    objectiveNumber: {
      width: 28,
      height: 28,
      borderRadius: 14,
      backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '30'),
      justifyContent: 'center',
      alignItems: 'center',
      marginRight: 12,
    },
    objectiveNumberText: {
      fontSize: 14,
      fontWeight: 'bold',
      color: COLORS.primary,
    },
    objectiveText: {
      flex: 1,
      fontSize: 15,
      color: COLORS.text,
    },
    tipsContainer: {
      backgroundColor: COLORS.cardBg,
      borderRadius: 16,
      padding: 16,
    },
    tipItem: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      marginBottom: 12,
      gap: 10,
    },
    tipText: {
      flex: 1,
      fontSize: 14,
      color: COLORS.textMuted,
      lineHeight: 20,
    },
    expectCard: {
      backgroundColor: COLORS.cardBg,
      borderRadius: 16,
      padding: 16,
    },
    expectItem: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: 14,
      gap: 12,
    },
    expectText: {
      fontSize: 14,
      color: COLORS.text,
    },
    bottomSpacing: {
      height: 100,
    },
    startButtonContainer: {
      position: 'absolute',
      bottom: 0,
      left: 0,
      right: 0,
      paddingHorizontal: 20,
      paddingVertical: 16,
      backgroundColor: COLORS.background,
      borderTopWidth: 1,
      borderTopColor: COLORS.cardBg,
    },
    startButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 16,
      borderRadius: 14,
      gap: 10,
    },
    startButtonText: {
      fontSize: 17,
      fontWeight: 'bold',
      color: COLORS.text,
    },
  });
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { user, _isAuthenticated } = useAuth();
  const { userId, hasHydrated, setCurrentConversation, setCurrentScenario, initializeUser } = useAppStore();
  const [scenario, setScenario] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  // Initialize user ID on mount
  useEffect(() => {
    if (!hasHydrated) return;
    void initializeUser();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated]);

  // Get the effective user ID (prefer auth user, fallback to app store)
  const effectiveUserId = user?.user_id || userId;

  useEffect(() => {
    loadScenario();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadScenario = async () => {
    if (!id) return;
    try {
      const data = await getScenario(id);
      setScenario(data);
    } catch (error) {
      console.error('Error loading scenario:', error);
      Alert.alert(tx('scenario.alerts.errorTitle', 'Error'), tx('scenario.alerts.loadFailed', 'Failed to load scenario'));
    } finally {
      setLoading(false);
    }
  };

  const handleStartPractice = async () => {
    if (!effectiveUserId || !scenario) {
      Alert.alert(tx('scenario.alerts.errorTitle', 'Error'), tx('scenario.alerts.waitForInit', 'Please wait while we initialize your session'));
      return;
    }
    
    setStarting(true);
    try {
      const result = await startConversation(effectiveUserId, scenario.id);
      setCurrentConversation(result.conversation.id);
      setCurrentScenario(scenario);
      router.push(`/chat/${result.conversation.id}`);
    } catch (error: any) {
      console.error('Error starting conversation:', error);
      Alert.alert(tx('scenario.alerts.errorTitle', 'Error'), error.response?.data?.detail || tx('scenario.alerts.startFailed', 'Failed to start practice session'));
    } finally {
      setStarting(false);
    }
  };

  if (!hasHydrated || loading) {
    return (
      <SafeAreaView style={styles.container}>
        <AIFeatureSkeleton />
      </SafeAreaView>
    );
  }

  if (!scenario) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <Text style={styles.errorText}>{tx('scenario.errors.notFound', 'Scenario not found')}</Text>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>{tx('scenario.actions.goBack', 'Go Back')}</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const categoryColor = COLORS[scenario.category as keyof typeof COLORS] || COLORS.primary;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backIcon} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{tx('scenario.page.detailsTitle', 'Scenario Details')}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Hero Section */}
        <View style={[styles.heroSection, { backgroundColor: (globalThis as any).__alphaColor(categoryColor, '15') }]}>
          <View style={[styles.iconContainer, { backgroundColor: (globalThis as any).__alphaColor(categoryColor, '30') }]}>
            <Ionicons
              name={CATEGORY_ICONS[scenario.category] || 'chatbubbles'}
              size={48}
              color={categoryColor}
            />
          </View>
          <Text style={styles.title}>{scenario.title}</Text>
          <View style={styles.badgesRow}>
            <View style={[styles.badge, { backgroundColor: (globalThis as any).__alphaColor(categoryColor, '30') }]}>
              <Text style={[styles.badgeText, { color: categoryColor }]}>
                {scenario.category.charAt(0).toUpperCase() + scenario.category.slice(1)}
              </Text>
            </View>
            <View
              style={[
                styles.badge,
                scenario.difficulty === 'beginner' && styles.difficultyBeginner,
                scenario.difficulty === 'intermediate' && styles.difficultyIntermediate,
                scenario.difficulty === 'advanced' && styles.difficultyAdvanced,
              ]}
            >
              <Text style={styles.badgeText}>{scenario.difficulty}</Text>
            </View>
          </View>
        </View>

        {/* Description */}
        <View style={styles.section}>
          <Text style={styles.description}>{scenario.description}</Text>
        </View>

        {/* Persona Card */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Who You'll Practice With</Text>
          <View style={styles.personaCard}>
            <View style={styles.personaAvatar}>
              <Ionicons name="person-circle" size={50} color={categoryColor} />
            </View>
            <View style={styles.personaInfo}>
              <Text style={styles.personaName}>{scenario.persona_name}</Text>
              <Text style={styles.personaDescription}>{scenario.persona_description}</Text>
            </View>
          </View>
          <View style={styles.personalityBox}>
            <Ionicons name="sparkles" size={18} color={COLORS.warningText} />
            <Text style={styles.personalityText}>
              <Text style={styles.personalityLabel}>Personality: </Text>
              {scenario.persona_personality}
            </Text>
          </View>
        </View>

        {/* Objectives */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your Objectives</Text>
          {scenario.objectives?.map((objective: string, index: number) => (
            <View key={index} style={styles.objectiveItem}>
              <View style={styles.objectiveNumber}>
                <Text style={styles.objectiveNumberText}>{index + 1}</Text>
              </View>
              <Text style={styles.objectiveText}>{objective}</Text>
            </View>
          ))}
        </View>

        {/* Tips */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Pro Tips</Text>
          <View style={styles.tipsContainer}>
            {scenario.tips?.map((tip: string, index: number) => (
              <View key={index} style={styles.tipItem}>
                <Ionicons name="bulb" size={18} color={COLORS.warningText} />
                <Text style={styles.tipText}>{tip}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* What to Expect */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>What to Expect</Text>
          <View style={styles.expectCard}>
            <View style={styles.expectItem}>
              <Ionicons name="chatbubble-ellipses" size={24} color={COLORS.primary} />
              <Text style={styles.expectText}>Interactive conversation practice</Text>
            </View>
            <View style={styles.expectItem}>
              <Ionicons name="analytics" size={24} color={COLORS.successText} />
              <Text style={styles.expectText}>Real-time feedback on your responses</Text>
            </View>
            <View style={styles.expectItem}>
              <Ionicons name="trophy" size={24} color={COLORS.warningText} />
              <Text style={styles.expectText}>Score and improvement suggestions</Text>
            </View>
          </View>
        </View>

        <View style={styles.bottomSpacing} />
      </ScrollView>

      {/* Start Button */}
      <View style={styles.startButtonContainer}>
        <TouchableOpacity
          style={[styles.startButton, { backgroundColor: categoryColor }]}
          onPress={handleStartPractice}
          disabled={starting}
        >
          {starting ? (
            <ActivityIndicator color={COLORS.text} />
          ) : (
            <>
              <Text style={styles.startButtonText}>Start Practice Session</Text>
              <Ionicons name="arrow-forward" size={20} color={COLORS.text} />
            </>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}
