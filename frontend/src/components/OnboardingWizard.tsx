import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Animated,
  Modal, useWindowDimensions, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import api from '../services/api';

interface Props {
  visible: boolean;
  onClose: () => void;
}

/**
 * OnboardingWizard — Enterprise-pro 3-step onboarding.
 * Fully v2 theme compliant — uses only colors.* tokens, no hardcoded values.
 */
export default function OnboardingWizard({ visible, onClose }: Props) {
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { width } = useWindowDimensions();
  const isDesktop = width >= 768;

  const STEPS = [
    {
      title: tx('onboardingWizard.step1.title', "What's your primary goal?"),
      subtitle: tx('onboardingWizard.step1.subtitle', 'Select the area that matters most to you right now. We\'ll tailor your experience accordingly.'),
      key: 'goal',
      options: [
        { id: 'career', label: tx('onboardingWizard.step1.options.career.label', 'Career Growth'), desc: tx('onboardingWizard.step1.options.career.desc', 'Accelerate your professional trajectory'), icon: 'briefcase', color: colors.primary },
        { id: 'health', label: tx('onboardingWizard.step1.options.health.label', 'Health & Fitness'), desc: tx('onboardingWizard.step1.options.health.desc', 'Build sustainable wellness habits'), icon: 'fitness', color: colors.success },
        { id: 'finance', label: tx('onboardingWizard.step1.options.finance.label', 'Financial Freedom'), desc: tx('onboardingWizard.step1.options.finance.desc', 'Master your money and investments'), icon: 'wallet', color: colors.info },
        { id: 'learning', label: tx('onboardingWizard.step1.options.learning.label', 'Learning & Education'), desc: tx('onboardingWizard.step1.options.learning.desc', 'Upskill with structured learning paths'), icon: 'school', color: colors.warning },
        { id: 'creative', label: tx('onboardingWizard.step1.options.creative.label', 'Creative Projects'), desc: tx('onboardingWizard.step1.options.creative.desc', 'Bring ideas to life with AI tools'), icon: 'color-palette', color: colors.purple },
        { id: 'relationships', label: tx('onboardingWizard.step1.options.relationships.label', 'Relationships'), desc: tx('onboardingWizard.step1.options.relationships.desc', 'Strengthen personal connections'), icon: 'heart', color: colors.error },
      ],
    },
    {
      title: tx('onboardingWizard.step2.title', 'What do you need most help with?'),
      subtitle: tx('onboardingWizard.step2.subtitle', 'This helps us assign the right AI copilots to your workflow from day one.'),
      key: 'need',
      options: [
        { id: 'writing', label: tx('onboardingWizard.step2.options.writing.label', 'Writing & Content'), desc: tx('onboardingWizard.step2.options.writing.desc', 'Drafts, editing, and content creation'), icon: 'create', color: colors.success },
        { id: 'planning', label: tx('onboardingWizard.step2.options.planning.label', 'Planning & Organization'), desc: tx('onboardingWizard.step2.options.planning.desc', 'Scheduling, goals, and task management'), icon: 'calendar', color: colors.warning },
        { id: 'research', label: tx('onboardingWizard.step2.options.research.label', 'Research & Analysis'), desc: tx('onboardingWizard.step2.options.research.desc', 'Data-driven insights and deep dives'), icon: 'search', color: colors.primary },
        { id: 'creativity', label: tx('onboardingWizard.step2.options.creativity.label', 'Creativity & Design'), desc: tx('onboardingWizard.step2.options.creativity.desc', 'Visual thinking and ideation'), icon: 'image', color: colors.purple },
        { id: 'wellness', label: tx('onboardingWizard.step2.options.wellness.label', 'Health & Wellness'), desc: tx('onboardingWizard.step2.options.wellness.desc', 'Fitness plans, nutrition, and mindfulness'), icon: 'medkit', color: colors.error },
        { id: 'communication', label: tx('onboardingWizard.step2.options.communication.label', 'Communication'), desc: tx('onboardingWizard.step2.options.communication.desc', 'Email, messaging, and presentations'), icon: 'chatbubble', color: colors.info },
      ],
    },
    {
      title: tx('onboardingWizard.step3.title', 'How do you prefer to work?'),
      subtitle: tx('onboardingWizard.step3.subtitle', "We'll match your interaction style to the right tools and interfaces."),
      key: 'style',
      options: [
        { id: 'quick', label: tx('onboardingWizard.step3.options.quick.label', 'Quick Answers'), desc: tx('onboardingWizard.step3.options.quick.desc', 'Fast responses, minimal setup'), icon: 'flash', color: colors.warning },
        { id: 'deep', label: tx('onboardingWizard.step3.options.deep.label', 'Deep Conversations'), desc: tx('onboardingWizard.step3.options.deep.desc', 'Thoughtful, multi-turn dialogue'), icon: 'chatbubbles', color: colors.primary },
        { id: 'stepbystep', label: tx('onboardingWizard.step3.options.stepByStep.label', 'Step-by-Step Guidance'), desc: tx('onboardingWizard.step3.options.stepByStep.desc', 'Structured walkthroughs and checklists'), icon: 'list', color: colors.success },
        { id: 'visual', label: tx('onboardingWizard.step3.options.visual.label', 'Visual Tools'), desc: tx('onboardingWizard.step3.options.visual.desc', 'Charts, diagrams, and visual outputs'), icon: 'image', color: colors.purple },
        { id: 'voice', label: tx('onboardingWizard.step3.options.voice.label', 'Voice Interaction'), desc: tx('onboardingWizard.step3.options.voice.desc', 'Hands-free voice commands and dictation'), icon: 'mic', color: colors.info },
      ],
    },
  ];

  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const fadeAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (visible) { setStep(0); setAnswers({}); setRecommendations([]); }
  }, [visible]);

  const animateTransition = (cb: () => void) => {
    Animated.timing(fadeAnim, { toValue: 0, duration: 120, useNativeDriver: Platform.OS !== 'web' }).start(() => {
      cb();
      Animated.timing(fadeAnim, { toValue: 1, duration: 200, useNativeDriver: Platform.OS !== 'web' }).start();
    });
  };

  const selectOption = (optionId: string) => {
    const currentStep = STEPS[step];
    const newAnswers = { ...answers, [currentStep.key]: optionId };
    setAnswers(newAnswers);
    if (step < STEPS.length - 1) {
      animateTransition(() => setStep(step + 1));
    } else {
      submitWizard(newAnswers);
    }
  };

  const submitWizard = async (finalAnswers: Record<string, string>) => {
    setLoading(true);
    try {
      const res = await api.post('/onboarding-wizard/submit', finalAnswers);
      animateTransition(() => {
        setRecommendations(res.data.recommendations || []);
        setStep(STEPS.length);
      });
    } catch (e) {
      console.error('Wizard submit error:', e);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const goBack = () => {
    if (step > 0) animateTransition(() => setStep(step - 1));
  };

  const goToFeature = (featureId: string) => {
    onClose();
    router.push((`/features/${featureId}`) as any);
  };

  const isResults = step === STEPS.length;
  const currentStep = STEPS[step] || STEPS[0];
  const useGrid = isDesktop && !isResults;

  /* Segmented progress */
  const SegmentedProgress = () => (
    <View style={{ flexDirection: 'row', gap: 6, paddingHorizontal: 32, paddingTop: 16 }} data-testid="segmented-progress">
      {STEPS.map((_, i) => (
        <View key={i} style={{
          flex: 1, height: 4, borderRadius: 2,
          backgroundColor: i <= step || isResults ? colors.primary : colors.border,
        }} />
      ))}
    </View>
  );

  return (
    <Modal visible={visible} transparent animationType="fade" data-testid="onboarding-wizard-modal" testID="onboarding-wizard-modal">
      <View style={{
        flex: 1,
        backgroundColor: colors.overlay,
        justifyContent: 'center', alignItems: 'center',
        padding: 20,
      }}>
        <View style={{
          backgroundColor: colors.card,
          borderRadius: 16,
          width: '100%',
          maxWidth: useGrid ? 640 : 520,
          maxHeight: '92%',
          overflow: 'hidden',
          borderWidth: 1, borderColor: colors.border,
          ...(Platform.OS === 'web' ? {
            boxShadow: `0 25px 50px -12px ${colors.shadowColor}`,
          } : {
            shadowColor: colors.shadowColor, shadowOffset: { width: 0, height: 12 },
            shadowOpacity: 0.15, shadowRadius: 24, elevation: 12,
          }),
        } as any} data-testid="onboarding-wizard-card" testID="onboarding-wizard-card">

          {/* Header */}
          <View style={{
            flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
            paddingHorizontal: 32, paddingTop: 24, paddingBottom: 0,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              {step > 0 && !isResults && (
                <TouchableOpacity accessibilityLabel="Wizard back button"
                  onPress={goBack}
                  style={{
                    width: 32, height: 32, borderRadius: 8,
                    backgroundColor: colors.surfaceHover,
                    alignItems: 'center', justifyContent: 'center',
                  }}
                  data-testid="wizard-back-btn" testID="wizard-back-btn"
                  accessibilityRole="button" accessibilityLabel="Go back"
                >
                  <Ionicons name="chevron-back" size={16} color={colors.textMuted} />
                </TouchableOpacity>
              )}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{
                  width: 28, height: 28, borderRadius: 8,
                  backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center',
                }}>
                  <Ionicons name="sparkles" size={14} color={colors.primary} />
                </View>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.5, textTransform: 'uppercase' }}>
                  {isResults ? tx('onboardingWizard.header.yourAiTeam', 'Your AI Team') : `${tx('onboardingWizard.header.step', 'Step')} ${step + 1} ${tx('onboardingWizard.header.of', 'of')} ${STEPS.length}`}
                </Text>
              </View>
            </View>
            <TouchableOpacity accessibilityLabel="Wizard close button"
              onPress={onClose}
              style={{
                width: 32, height: 32, borderRadius: 8,
                backgroundColor: colors.surfaceHover,
                alignItems: 'center', justifyContent: 'center',
              }}
              data-testid="wizard-close-btn" testID="wizard-close-btn"
              accessibilityRole="button" accessibilityLabel="Close wizard"
            >
              <Ionicons name="close" size={16} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          {/* Segmented Progress */}
          <SegmentedProgress />

          {/* Content */}
          <ScrollView contentContainerStyle={{ padding: 32, paddingTop: 24 }} showsVerticalScrollIndicator={false}>
            <Animated.View style={{ opacity: fadeAnim }}>

              {loading ? (
                <View style={{ alignItems: 'center', paddingVertical: 56, gap: 20 }} data-testid="wizard-loading">
                  <View style={{
                    width: 64, height: 64, borderRadius: 16,
                    backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Ionicons name="sparkles" size={28} color={colors.primary} />
                  </View>
                  <View style={{ alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, letterSpacing: -0.3 }}>
                      {tx('onboardingWizard.loading.title', 'Analyzing your preferences')}
                    </Text>
                    <Text style={{ fontSize: 14, color: colors.textMuted }}>
                      {tx('onboardingWizard.loading.subtitle', 'Finding the best AI copilots for you')}
                    </Text>
                  </View>
                  <View style={{ width: 140, height: 4, borderRadius: 2, backgroundColor: colors.border, marginTop: 8, overflow: 'hidden' }}>
                    <View style={{ width: '60%', height: 4, borderRadius: 2, backgroundColor: colors.primary }} />
                  </View>
                </View>

              ) : isResults ? (
                <View data-testid="wizard-results" testID="wizard-results">
                  <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text, letterSpacing: -0.5, marginBottom: 6 }}>
                    {tx('onboardingWizard.results.title', 'Your Top AI Copilots')}
                  </Text>
                  <Text style={{ fontSize: 15, color: colors.textMuted, marginBottom: 28, lineHeight: 22 }}>
                    {tx('onboardingWizard.results.subtitle', 'Based on your goals and preferences, here are the best tools to get started with.')}
                  </Text>
                  <View style={{ gap: 8 }}>
                    {recommendations.map((rec, i) => (
                      <TouchableOpacity accessibilityLabel="Go to to feature in onboarding wizard button"
                        key={rec.feature_id}
                        onPress={() => goToFeature(rec.feature_id)}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 14,
                          backgroundColor: colors.surfaceHover,
                          borderRadius: 12, padding: 14,
                          borderWidth: 1, borderColor: colors.border,
                        }}
                        data-testid={`wizard-rec-${rec.feature_id}`} testID={`wizard-rec-${rec.feature_id}`}
                        accessibilityRole="button" accessibilityLabel={`Open ${rec.title}`}
                      >
                        <View style={{
                          width: 8, height: 8, borderRadius: 4,
                          backgroundColor: colors.primary, opacity: 1 - i * 0.15,
                        }} />
                        <View style={{
                          width: 44, height: 44, borderRadius: 12,
                          backgroundColor: (globalThis as any).__alphaColor((rec.color || colors.primary), '0C'),
                          alignItems: 'center', justifyContent: 'center',
                          borderWidth: 1, borderColor: (globalThis as any).__alphaColor((rec.color || colors.primary), '18'),
                        }}>
                          <Ionicons name={rec.icon as any} size={20} color={rec.color || colors.primary} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{rec.title}</Text>
                          <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }} numberOfLines={1}>{rec.description}</Text>
                        </View>
                        <Ionicons name="arrow-forward" size={16} color={colors.textMuted} />
                      </TouchableOpacity>
                    ))}
                  </View>
                  <View style={{ marginTop: 32, paddingTop: 24, borderTopWidth: 1, borderTopColor: colors.border }}>
                    <TouchableOpacity
                      style={{ backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 14, alignItems: 'center' }}
                      onPress={onClose}
                      data-testid="wizard-done-btn" testID="wizard-done-btn"
                      accessibilityRole="button" accessibilityLabel="Go to Dashboard"
                    >
                      <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '600', letterSpacing: 0.2 }}>
                        {tx('onboardingWizard.results.goToDashboard', 'Go to Dashboard')}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>

              ) : (
                <View data-testid={`wizard-step-${step}`} testID={`wizard-step-${step}`}>
                  <Text style={{
                    fontSize: isDesktop ? 26 : 22, fontWeight: '700', color: colors.text,
                    letterSpacing: -0.5, marginBottom: 8,
                  }}>
                    {currentStep.title}
                  </Text>
                  <Text style={{ fontSize: 15, color: colors.textMuted, marginBottom: 28, lineHeight: 22 }}>
                    {currentStep.subtitle}
                  </Text>

                  {/* Bento Grid / List */}
                  <View style={useGrid ? {
                    flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 12,
                  } : { gap: 10 }}>
                    {currentStep.options.map(opt => {
                      const selected = answers[currentStep.key] === opt.id;
                      return (
                        <TouchableOpacity accessibilityLabel="Select option in onboarding wizard"
                          key={opt.id}
                          onPress={() => selectOption(opt.id)}
                          style={{
                            ...(useGrid ? { width: '48%' as any } : {}),
                            backgroundColor: selected ? colors.primarySoft : colors.surfaceHover,
                            borderRadius: 12,
                            padding: useGrid ? 20 : 16,
                            borderWidth: 1.5,
                            borderColor: selected ? colors.primary : colors.border,
                            ...(useGrid ? { alignItems: 'flex-start' as any } : { flexDirection: 'row' as any, alignItems: 'center' as any, gap: 14 }),
                          }}
                          data-testid={`wizard-option-${opt.id}`} testID={`wizard-option-${opt.id}`}
                          accessibilityRole="button" accessibilityLabel={opt.label}
                        >
                          <View style={{
                            width: useGrid ? 44 : 42, height: useGrid ? 44 : 42,
                            borderRadius: 12,
                            backgroundColor: selected ? (globalThis as any).__alphaColor(opt.color, '22') : opt.color + '0C',
                            alignItems: 'center', justifyContent: 'center',
                            ...(useGrid ? { marginBottom: 14 } : {}),
                          }}>
                            <Ionicons name={opt.icon as any} size={useGrid ? 22 : 20} color={opt.color} />
                          </View>
                          <View style={useGrid ? {} : { flex: 1 }}>
                            <Text style={{
                              fontSize: useGrid ? 15 : 14, fontWeight: '600', color: colors.text,
                              ...(useGrid ? { marginBottom: 4 } : {}),
                            }}>
                              {opt.label}
                            </Text>
                            {useGrid && opt.desc && (
                              <Text style={{ fontSize: 12, color: colors.textMuted, lineHeight: 17 }} numberOfLines={2}>
                                {opt.desc}
                              </Text>
                            )}
                          </View>
                          {selected && !useGrid && (
                            <Ionicons name="checkmark-circle" size={20} color={colors.primary} />
                          )}
                          {selected && useGrid && (
                            <View style={{ position: 'absolute', top: 12, right: 12 }}>
                              <Ionicons name="checkmark-circle" size={18} color={colors.primary} />
                            </View>
                          )}
                        </TouchableOpacity>
                      );
                    })}
                  </View>

                  {/* Footer */}
                  <View style={{
                    marginTop: 28, paddingTop: 20,
                    borderTopWidth: 1, borderTopColor: colors.border,
                    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  }}>
                    <Text style={{ fontSize: 13, color: colors.textMuted }}>
                      {step < STEPS.length - 1 ? tx('onboardingWizard.footer.selectToContinue', 'Select to continue') : tx('onboardingWizard.footer.selectToFinish', 'Select to finish')}
                    </Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name="shield-checkmark" size={14} color={colors.primary} />
                      <Text style={{ fontSize: 12, color: colors.textMuted }}>
                        {tx('onboardingWizard.footer.changeLater', 'You can change this later')}
                      </Text>
                    </View>
                  </View>
                </View>
              )}
            </Animated.View>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
