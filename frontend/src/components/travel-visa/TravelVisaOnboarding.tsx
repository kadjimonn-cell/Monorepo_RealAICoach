import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import CountryFlag from '../CountryFlag';

type OnboardingStep = 'country' | 'visa-type' | 'experience';

interface OnboardingData {
  country: string;
  visaType: string;
  experienceLevel: string;
}

interface TravelVisaOnboardingProps {
  onComplete: (data: OnboardingData) => void;
  onSkip: () => void;
}

const POPULAR_COUNTRIES = [
  { code: 'US', name: 'United States' },
  { code: 'CA', name: 'Canada' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'DE', name: 'Germany' },
  { code: 'AU', name: 'Australia' },
  { code: 'FR', name: 'France' },
  { code: 'JP', name: 'Japan' },
  { code: 'AE', name: 'UAE' },
];

const VISA_TYPES = [
  { id: 'tourist', label: 'Tourist / Visitor', icon: 'airplane', desc: 'Short-term travel, tourism' },
  { id: 'student', label: 'Student', icon: 'school', desc: 'Study at university/college' },
  { id: 'work', label: 'Work / Employment', icon: 'briefcase', desc: 'Job offer, work permit' },
  { id: 'family', label: 'Family / Spouse', icon: 'people', desc: 'Join family members' },
  { id: 'business', label: 'Business', icon: 'trending-up', desc: 'Business meetings, conferences' },
  { id: 'pr', label: 'Permanent Residency', icon: 'home', desc: 'Long-term immigration' },
];

const EXPERIENCE_LEVELS = [
  { id: 'beginner', label: 'Beginner', icon: 'leaf', desc: 'First time applying for a visa', colorKey: 'success' },
  { id: 'intermediate', label: 'Intermediate', icon: 'flash', desc: 'Applied for visas before', colorKey: 'warning' },
  { id: 'expert', label: 'Expert', icon: 'star', desc: 'Multiple visa applications', colorKey: 'info' },
];

export default function TravelVisaOnboarding({ onComplete, onSkip }: TravelVisaOnboardingProps) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;
  const isTablet = width >= 600;
  const container = { width: '100%' as const, maxWidth: 960, alignSelf: 'center' as const };
  const [currentStep, setCurrentStep] = useState<OnboardingStep>('country');
  const [data, setData] = useState<OnboardingData>({
    country: '',
    visaType: '',
    experienceLevel: '',
  });

  const stepIndex = { 'country': 1, 'visa-type': 2, 'experience': 3 }[currentStep];
  const progress = (stepIndex / 3) * 100;
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ y: 0, animated: false });
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.scrollTo(0, 0);
      setTimeout(() => {
        const outer = document.querySelector('[data-testid="tv-v2-root"]');
        if (outer && (outer as HTMLElement).scrollTop > 0) (outer as HTMLElement).scrollTop = 0;
      }, 0);
    }
  }, [currentStep]);

  const handleNext = () => {
    if (currentStep === 'country' && data.country) setCurrentStep('visa-type');
    else if (currentStep === 'visa-type' && data.visaType) setCurrentStep('experience');
    else if (currentStep === 'experience' && data.experienceLevel) onComplete(data);
  };

  const handleBack = () => {
    if (currentStep === 'visa-type') setCurrentStep('country');
    else if (currentStep === 'experience') setCurrentStep('visa-type');
  };

  const canProceed =
    (currentStep === 'country' && data.country) ||
    (currentStep === 'visa-type' && data.visaType) ||
    (currentStep === 'experience' && data.experienceLevel);

  const twoColWidth = isTablet ? '48.6%' : '100%';
  const threeColWidth = isDesktop ? '31.8%' : isTablet ? '48.6%' : '100%';

  return (
    <View
      data-testid="tv-v2-onboarding-root"
      testID="tv-v2-onboarding-root"
      style={{
      flex: 1,
      backgroundColor: colors.background,
      ...(Platform.OS === 'web' ? { minHeight: '100vh' } : {})
    }}>
      {/* Header */}
      <View style={{
        paddingTop: Platform.OS === 'web' ? 24 : 60,
        paddingBottom: 20,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
      }}>
        <View style={[container, { paddingHorizontal: 20 }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{
                width: 40,
                height: 40,
                borderRadius: 12,
                backgroundColor: colors.primarySoft,
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <Ionicons name="airplane" size={22} color={colors.primary} />
              </View>
              <View>
                <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>
                  Welcome to Travel Visa
                </Text>
                <Text style={{ fontSize: 13, color: colors.textMuted }}>
                  Step {stepIndex} of 3
                </Text>
              </View>
            </View>
            <TouchableOpacity data-testid="tv-v2-onboarding-skip" testID="tv-v2-onboarding-skip" onPress={onSkip} style={{ padding: 8 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.textMuted }}>Skip</Text>
            </TouchableOpacity>
          </View>

          {/* Progress Bar */}
          <View style={{
            height: 4,
            backgroundColor: colors.border,
            borderRadius: 2,
            overflow: 'hidden',
          }}>
            <View style={{
              height: '100%',
              width: `${progress}%`,
              backgroundColor: colors.primary,
              ...(Platform.OS === 'web' ? { transition: 'width 300ms ease' } as any : {}),
            }} />
          </View>
        </View>
      </View>

      <ScrollView key={currentStep} ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ flexGrow: 1, padding: 20, paddingBottom: 40 }}>
       <View style={container}>
        {/* Step 1: Country Selection */}
        {currentStep === 'country' && (
          <View>
            <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text, marginBottom: 8 }}>
              Where are you planning to go?
            </Text>
            <Text style={{ fontSize: 15, color: colors.textMuted, marginBottom: 24, lineHeight: 22 }}>
              Select your target country to get personalized visa preparation guidance.
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {POPULAR_COUNTRIES.map((country) => (
                <TouchableOpacity
                  data-testid={`tv-v2-onboarding-country-${country.code.toLowerCase()}`}
                  testID={`tv-v2-onboarding-country-${country.code.toLowerCase()}`}
                  key={country.code}
                  onPress={() => setData({ ...data, country: country.name })}
                  style={{
                    width: twoColWidth as any,
                    flexDirection: 'row',
                    alignItems: 'center',
                    padding: 16,
                    borderRadius: 14,
                    backgroundColor: data.country === country.name ? colors.primarySoft : colors.card,
                    borderWidth: 2,
                    borderColor: data.country === country.name ? colors.primary : colors.border,
                    ...(Platform.OS === 'web' ? {
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
                    } as any : {}),
                  }}
                >
                  <CountryFlag code={country.code} size={22} style={{ marginRight: 12 }} />
                  <Text style={{
                    fontSize: 16,
                    fontWeight: '600',
                    color: data.country === country.name ? colors.primary : colors.text,
                    flex: 1,
                  }}>
                    {country.name}
                  </Text>
                  {data.country === country.name && (
                    <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Step 2: Visa Type Selection */}
        {currentStep === 'visa-type' && (
          <View>
            <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text, marginBottom: 8 }}>
              What type of visa do you need?
            </Text>
            <Text style={{ fontSize: 15, color: colors.textMuted, marginBottom: 24, lineHeight: 22 }}>
              Choose the visa category that matches your travel purpose.
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {VISA_TYPES.map((visa) => (
                <TouchableOpacity
                  data-testid={`tv-v2-onboarding-visa-${visa.id}`}
                  testID={`tv-v2-onboarding-visa-${visa.id}`}
                  key={visa.id}
                  onPress={() => setData({ ...data, visaType: visa.id })}
                  style={{
                    width: twoColWidth as any,
                    padding: 16,
                    borderRadius: 14,
                    backgroundColor: data.visaType === visa.id ? colors.primarySoft : colors.card,
                    borderWidth: 2,
                    borderColor: data.visaType === visa.id ? colors.primary : colors.border,
                    ...(Platform.OS === 'web' ? {
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
                    } as any : {}),
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <View style={{
                      width: 36,
                      height: 36,
                      borderRadius: 10,
                      backgroundColor: data.visaType === visa.id ? colors.primary : colors.border,
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginRight: 12,
                    }}>
                      <Ionicons
                        name={visa.icon as any}
                        size={18}
                        color={data.visaType === visa.id ? colors.primaryText : colors.textMuted}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{
                        fontSize: 16,
                        fontWeight: '600',
                        color: data.visaType === visa.id ? colors.primary : colors.text,
                      }}>
                        {visa.label}
                      </Text>
                      <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>
                        {visa.desc}
                      </Text>
                    </View>
                    {data.visaType === visa.id && (
                      <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                    )}
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Step 3: Experience Level */}
        {currentStep === 'experience' && (
          <View>
            <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text, marginBottom: 8 }}>
              What's your experience level?
            </Text>
            <Text style={{ fontSize: 15, color: colors.textMuted, marginBottom: 24, lineHeight: 22 }}>
              We'll tailor content and guidance to match your experience.
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {EXPERIENCE_LEVELS.map((level) => (
                <TouchableOpacity
                  data-testid={`tv-v2-onboarding-level-${level.id}`}
                  testID={`tv-v2-onboarding-level-${level.id}`}
                  key={level.id}
                  onPress={() => setData({ ...data, experienceLevel: level.id })}
                  style={{
                    width: threeColWidth as any,
                    padding: 20,
                    borderRadius: 14,
                    backgroundColor: data.experienceLevel === level.id ? colors.primarySoft : colors.card,
                    borderWidth: 2,
                    borderColor: data.experienceLevel === level.id ? colors.primary : colors.border,
                    alignItems: 'center',
                    ...(Platform.OS === 'web' ? {
                      cursor: 'pointer',
                      transition: 'all 150ms ease',
                    } as any : {}),
                  }}
                >
                  <View style={{
                    width: 56,
                    height: 56,
                    borderRadius: 28,
                    backgroundColor: data.experienceLevel === level.id ? ((colors as any)[level.colorKey] || colors.primary) : colors.border,
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: 12,
                  }}>
                    <Ionicons
                      name={level.icon as any}
                      size={28}
                      color={colors.primaryText}
                    />
                  </View>
                  <Text style={{
                    fontSize: 18,
                    fontWeight: '700',
                    color: data.experienceLevel === level.id ? colors.primary : colors.text,
                    marginBottom: 6,
                  }}>
                    {level.label}
                  </Text>
                  <Text style={{ fontSize: 14, color: colors.textMuted, textAlign: 'center' }}>
                    {level.desc}
                  </Text>
                  {data.experienceLevel === level.id && (
                    <View style={{ position: 'absolute', top: 12, right: 12 }}>
                      <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}
       </View>
      </ScrollView>

      {/* Footer Actions */}
      <View style={{
        paddingVertical: 16,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.card,
      }}>
        <View style={[container, { paddingHorizontal: 20 }]}>
          <View style={{ flexDirection: 'row', gap: 12 }}>
            {currentStep !== 'country' && (
              <TouchableOpacity
                data-testid="tv-v2-onboarding-back"
                testID="tv-v2-onboarding-back"
                onPress={handleBack}
                style={{
                  flex: 1,
                  paddingVertical: 14,
                  borderRadius: 12,
                  backgroundColor: colors.border,
                  alignItems: 'center',
                  flexDirection: 'row',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <Ionicons name="arrow-back" size={18} color={colors.text} />
                <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text }}>Back</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              data-testid="tv-v2-onboarding-continue"
              testID="tv-v2-onboarding-continue"
              onPress={handleNext}
              disabled={!canProceed}
              style={{
                flex: 2,
                paddingVertical: 14,
                borderRadius: 12,
                backgroundColor: canProceed ? colors.primary : colors.border,
                alignItems: 'center',
                flexDirection: 'row',
                justifyContent: 'center',
                gap: 6,
                opacity: canProceed ? 1 : 0.5,
              }}
            >
              <Text style={{
                fontSize: 15,
                fontWeight: '700',
                color: canProceed ? colors.primaryText : colors.textMuted,
              }}>
                {currentStep === 'experience' ? 'Get Started' : 'Continue'}
              </Text>
              <Ionicons
                name={currentStep === 'experience' ? 'checkmark-circle' : 'arrow-forward'}
                size={18}
                color={canProceed ? colors.primaryText : colors.textMuted}
              />
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </View>
  );
}
