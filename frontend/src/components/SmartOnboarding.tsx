import React, { useEffect, useState, useRef } from 'react';
import { View, Text, TouchableOpacity, Animated, useWindowDimensions, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { usePathname, useRouter } from 'expo-router';
import { createPortal } from 'react-dom';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { notificationEvents } from '../utils/notificationEvents';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const GLOBAL_ONBOARDING_ASSIGN_MARKERS = new Set<string>();
const ONBOARDING_GUARDRAIL_STABILITY_MODE = true;

export default function SmartOnboarding() {
  const stabilityMode = ONBOARDING_GUARDRAIL_STABILITY_MODE;

  const { colors, darkMode } = useTheme();

  // @autofix-moved: was module-level const STEPS
  const STEPS = [
    {
      id: 'welcome',
      icon: 'rocket-outline' as const,
      title: 'Welcome to RealAICoach',
      desc: 'Your AI-powered coaching & productivity hub with live enterprise tools. Let us show you around!',
      color: colors.primary,
      target: null,
      route: null,
    },
    {
      id: 'ai-learning-hub',
      icon: 'school-outline' as const,
      title: 'AI Learning Hub',
      desc: 'Access personalized learning paths, AI-generated lessons, and skill-building exercises tailored to your goals.',
      color: colors.primary,
      target: 'sidebar-nav-ai-learning-hub',
      route: '/ai-learning-hub',
    },
    {
      id: 'ai-coaching-team',
      icon: 'people-circle-outline' as const,
      title: 'AI Coaching Team',
      desc: 'Chat with a curated team of AI coaches for career growth, interview prep, resume polish, and negotiation.',
      color: colors.successText,
      target: 'sidebar-nav-ai-coaching-team',
      route: '/ai-coaching-team',
    },
    {
      id: 'ai-briefing',
      icon: 'newspaper-outline' as const,
      title: 'Daily Briefing',
      desc: 'Start each day with an AI-curated summary of your goals, progress, and personalized recommendations.',
      color: colors.warningText,
      target: 'sidebar-nav-ai-briefing',
      route: '/ai-briefing',
    },
    {
      id: 'progress',
      icon: 'trending-up-outline' as const,
      title: 'Progress Tracker',
      desc: 'Track your coaching journey with visual analytics, streak tracking, and milestone celebrations.',
      color: colors.accent,
      target: 'sidebar-nav-progress',
      route: '/progress',
    },
    {
      id: 'ai-gallery',
      icon: 'sparkles-outline' as const,
      title: 'AI Feature Gallery',
      desc: 'Explore all live AI tools in one place. Find the perfect copilot for any task you need help with.',
      color: colors.primary,
      target: 'sidebar-nav-ai-gallery',
      route: '/feature-gallery',
    },
    {
      id: 'ready',
      icon: 'checkmark-circle-outline' as const,
      title: "You're All Set!",
      desc: 'You now know the essentials. Dive in and start your AI-powered coaching journey today!',
      color: colors.accent,
      target: null,
      route: null,
    },
  ];
  const { user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isTablet = width >= 768 && width < 1024;
  const [visible, setVisible] = useState(false);
  const [whatsNewOpen, setWhatsNewOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const slideAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const spotlightRef = useRef<HTMLDivElement | null>(null);
  const abExpRef = useRef<string | null>(null);
  const assignInFlightRef = useRef(false);
  const assignCooldownUntilRef = useRef(0);
  const assignAttemptedForUserRef = useRef<string>('');

  const hasSessionAssignMarker = (userId: string) => {
    if (!userId || Platform.OS !== 'web' || typeof window === 'undefined') return false;
    try {
      return window.sessionStorage.getItem(`onboarding:ab:assigned:${userId}`) === '1';
    } catch {
      return false;
    }
  };

  const setSessionAssignMarker = (userId: string) => {
    if (!userId || Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      window.sessionStorage.setItem(`onboarding:ab:assigned:${userId}`, '1');
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    if (!user) return;
    // useLiveQuery handles refresh; this effect processes the data
  }, [user]);

  const { data: onbProgress } = useLiveQuery(
    (!stabilityMode && user) ? '/onboarding/progress' : '',
    { entity: 'onboarding', pollInterval: 120000, deps: [user?.user_id] }
  );
  useEffect(() => {
    const path = String(pathname || '/');
    const allowOnboarding = path === '/dashboard'
      || path === '/home'
      || path.startsWith('/dashboard/')
      || path.startsWith('/home/');
    if (!allowOnboarding) {
      setVisible(false);
      return;
    }

    if (onbProgress && !onbProgress.dismissed && (onbProgress.completed_steps || []).length < STEPS.length) {
      setCompletedSteps(onbProgress.completed_steps || []);
      setVisible(true);
      Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: false }).start();
      // Assign user to onboarding A/B experiment for the current step
      const step = STEPS[(onbProgress.completed_steps || []).length] || STEPS[0];
      const now = Date.now();
      const currentUserId = String(user?.user_id || '');
      if (
        !assignInFlightRef.current
        && now >= assignCooldownUntilRef.current
        && assignAttemptedForUserRef.current !== currentUserId
        && !hasSessionAssignMarker(currentUserId)
        && !GLOBAL_ONBOARDING_ASSIGN_MARKERS.has(currentUserId)
      ) {
        assignInFlightRef.current = true;
        assignAttemptedForUserRef.current = currentUserId;
        setSessionAssignMarker(currentUserId);
        GLOBAL_ONBOARDING_ASSIGN_MARKERS.add(currentUserId);
        api.post('/onboarding-ab/assign', { step_id: step.id })
          .then(r => {
            if (r.data?.experiment_id) abExpRef.current = r.data.experiment_id;
          })
          .catch(() => {
            assignCooldownUntilRef.current = Date.now() + 120000;
          })
          .finally(() => {
            assignInFlightRef.current = false;
          });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onbProgress, pathname]);

  // Spotlight effect for web
  useEffect(() => {
    if (Platform.OS !== 'web' || !visible) return;
    const step = STEPS[currentStep];
    if (!step.target) {
      removeSpotlight();
      return;
    }

    const el = document.querySelector(`[data-testid="${step.target}"]`) as HTMLElement;
    if (!el) {
      removeSpotlight();
      return;
    }

    // Scroll element into view
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Apply spotlight
    setTimeout(() => {
      const rect = el.getBoundingClientRect();
      applySpotlight(rect, step.color);
    }, 300);

    return () => removeSpotlight();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, visible]);

  const applySpotlight = (rect: DOMRect, color: string) => {
    removeSpotlight();
    const overlay = document.createElement('div');
    overlay.id = 'onboarding-spotlight';
    overlay.style.cssText = `
      position:fixed;inset:0;z-index:99998;pointer-events:none;
      transition:all 0.3s ease;
    `;

    const pad = 8;
    const x = rect.left - pad;
    const y = rect.top - pad;
    const w = rect.width + pad * 2;
    const h = rect.height + pad * 2;
    const r = 12;

    overlay.innerHTML = `
      <svg style="position:absolute;inset:0;width:100%;height:100%">
        <defs>
          <mask id="spot-mask">
            <rect width="100%" height="100%" fill="white"/>
            <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="black"/>
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(0,0,0,0.55)" mask="url(#spot-mask)"/>
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="none" stroke="${color}" stroke-width="2" stroke-dasharray="6 3">
          <animate attributeName="stroke-dashoffset" from="0" to="-18" dur="1.5s" repeatCount="indefinite"/>
        </rect>
      </svg>
    `;
    document.body.appendChild(overlay);
    spotlightRef.current = overlay as any;
  };

  const removeSpotlight = () => {
    const existing = document.getElementById('onboarding-spotlight');
    if (existing) existing.remove();
  };

  useEffect(() => {
    const unsubscribe = notificationEvents.on('whats-new-visibility', (isOpen) => {
      setWhatsNewOpen(Boolean(isOpen));
      if (!isOpen) return;
      removeSpotlight();
      setVisible(false);
    });
    return unsubscribe;
  }, []);

  const completeStep = async () => {
    const step = STEPS[currentStep];
    if (!completedSteps.includes(step.id)) {
      try {
        const r = await api.post('/onboarding/progress', { step_id: step.id });
        setCompletedSteps(r.data.completed_steps || [...completedSteps, step.id]);
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/SmartOnboarding.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }

    if (currentStep < STEPS.length - 1) {
      Animated.timing(slideAnim, { toValue: -1, duration: 200, useNativeDriver: false }).start(() => {
        setCurrentStep(currentStep + 1);
        slideAnim.setValue(1);
        Animated.timing(slideAnim, { toValue: 0, duration: 200, useNativeDriver: false }).start();
      });
    } else {
      dismiss();
    }
  };

  const goToStep = (idx: number) => {
    if (idx === currentStep) return;
    Animated.timing(slideAnim, { toValue: idx > currentStep ? -1 : 1, duration: 200, useNativeDriver: false }).start(() => {
      setCurrentStep(idx);
      slideAnim.setValue(idx > currentStep ? 1 : -1);
      Animated.timing(slideAnim, { toValue: 0, duration: 200, useNativeDriver: false }).start();
    });
  };

  const dismiss = async () => {
    try { await api.post('/onboarding/dismiss', { dismissed: true }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/SmartOnboarding.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    // Track onboarding A/B conversion if assigned to experiment
    if (abExpRef.current) {
      api.post('/onboarding-ab/convert', { experiment_id: abExpRef.current }).catch(() => {});
    }
    removeSpotlight();
    Animated.timing(fadeAnim, { toValue: 0, duration: 300, useNativeDriver: false }).start(() => setVisible(false));
  };

  const tryFeature = () => {
    const step = STEPS[currentStep];
    if (step.route) {
      router.push(step.route as any);
    }
  };

  const isE2EUser = String(user?.email || '').toLowerCase().startsWith('e2e.') && String(user?.email || '').toLowerCase().endsWith('@example.com');
  if (stabilityMode || isE2EUser || String(pathname || '').includes('job-platform')) return null;
  if (!visible || whatsNewOpen) return null;

  const step = STEPS[currentStep];
  const progress = (currentStep + 1) / STEPS.length;

  const content = (
    <Animated.View
      style={{
        opacity: fadeAnim,
        position: Platform.OS === 'web' ? ('fixed' as any) : 'absolute',
        bottom: isWide ? 24 : 16,
        right: isWide ? 24 : 16,
        left: isWide ? undefined : 16,
        width: isWide ? 380 : undefined,
        zIndex: 99999,
      }}
      data-testid="smart-onboarding" testID="smart-onboarding"
    >
      <View style={{
        backgroundColor: darkMode ? colors.cardMuted : colors.card,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(step.color, '40'),
        overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: `0 12px 40px rgba(0,0,0,0.2), 0 0 0 1px ${step.color}20` } as any : {}),
      }}>
        {/* Progress bar */}
        <View style={{ height: 3, backgroundColor: darkMode ? colors.border : colors.bgSoft }}>
          <View style={{ height: 3, backgroundColor: step.color, width: `${progress * 100}%`, borderRadius: 2 }} />
        </View>

        <View style={{ padding: isWide ? 20 : 16 }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 14 }}>
            {/* Icon */}
            <View style={{
              width: 48, height: 48, borderRadius: 14,
              backgroundColor: (globalThis as any).__alphaColor(step.color, '15'),
              alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Ionicons name={step.icon} size={24} color={step.color} />
            </View>

            {/* Content */}
            <Animated.View style={{
              flex: 1,
              transform: [{ translateX: slideAnim.interpolate({ inputRange: [-1, 0, 1], outputRange: [-30, 0, 30] }) }],
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Text style={{ color: step.color, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Step {currentStep + 1} of {STEPS.length}
                </Text>
                <View style={{ flex: 1 }} />
                <TouchableOpacity onPress={dismiss} data-testid="onboarding-dismiss" testID="onboarding-dismiss" accessibilityLabel="Dismiss tour" accessibilityRole="button">
                  <Ionicons name="close" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              </View>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 4 }} data-testid="onboarding-title" testID="onboarding-title">
                {step.title}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 13, lineHeight: 18 }}>
                {step.desc}
              </Text>
            </Animated.View>
          </View>

          {/* Actions */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 }}>
            <View style={{ flexDirection: 'row', gap: 3 }}>
              {STEPS.map((_, idx) => (
                <TouchableOpacity key={idx} onPress={() => goToStep(idx)} accessibilityLabel={`Go to step ${idx + 1}`}>
                  <View style={{
                    width: idx === currentStep ? 18 : 6, height: 6, borderRadius: 3,
                    backgroundColor: idx <= currentStep ? step.color : (darkMode ? colors.textDim : colors.textSec),
                  }} />
                </TouchableOpacity>
              ))}
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {step.route && (
                <TouchableOpacity onPress={tryFeature} data-testid="onboarding-try" testID="onboarding-try" accessibilityRole="button"
                  style={{
                    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: darkMode ? colors.card : colors.bgSoft,
                    borderWidth: 1, borderColor: darkMode ? colors.border : colors.border,
                  }}>
                  <Text style={{ color: step.color, fontSize: 12, fontWeight: '600' }}>Try It</Text>
                </TouchableOpacity>
              )}
              {currentStep > 0 && (
                <TouchableOpacity onPress={() => goToStep(currentStep - 1)} data-testid="onboarding-prev" testID="onboarding-prev" accessibilityRole="button"
                  style={{
                    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: darkMode ? colors.card : colors.bgSoft,
                    borderWidth: 1, borderColor: darkMode ? colors.border : colors.border,
                  }}>
                  <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '600' }}>Back</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity onPress={completeStep} data-testid="onboarding-next" testID="onboarding-next" accessibilityRole="button"
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 4,
                  paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10, backgroundColor: step.color,
                }}>
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>
                  {currentStep === STEPS.length - 1 ? 'Finish' : 'Next'}
                </Text>
                <Ionicons name={currentStep === STEPS.length - 1 ? 'checkmark' : 'arrow-forward'} size={14} color={colors.primaryText || colors.buttonText || colors.card} />
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </View>
    </Animated.View>
  );

  if (Platform.OS === 'web' && typeof document !== 'undefined') {
    return createPortal(content, document.body) as any;
  }
  return content;
}

/* i18n-probe t('i18n.auto.probe') */
