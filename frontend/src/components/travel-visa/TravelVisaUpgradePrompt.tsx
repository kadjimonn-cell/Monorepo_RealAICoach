import React from 'react';
import { View, Text, TouchableOpacity, Modal, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { router } from 'expo-router';
import { getFrontendPlanPrice } from '../../config/pricingPolicy';

interface UpgradePromptModalProps {
  visible: boolean;
  onClose: () => void;
  trigger: 'daily_limit' | 'locked_content' | 'feature_teaser' | 'quiz_limit';
  currentPlan: string;
}

const TRIGGER_CONFIG = {
  daily_limit: {
    icon: 'hourglass-outline',
    title: 'Daily Limit Reached',
    subtitle: 'You have used all your free AI coaching credits for today',
    colorKey: 'warning',
  },
  locked_content: {
    icon: 'lock-closed-outline',
    title: 'Premium Content',
    subtitle: 'Unlock advanced lessons and interview simulations',
    colorKey: 'info',
  },
  feature_teaser: {
    icon: 'star-outline',
    title: 'Upgrade to Premium',
    subtitle: 'Get unlimited access to all visa preparation tools',
    colorKey: 'primary',
  },
  quiz_limit: {
    icon: 'help-circle-outline',
    title: 'Quiz Limit Reached',
    subtitle: 'Upgrade to take unlimited practice quizzes',
    colorKey: 'success',
  },
};

export default function TravelVisaUpgradePrompt({ visible, onClose, trigger, currentPlan }: UpgradePromptModalProps) {
  const { colors } = useTheme();
  
  const config = TRIGGER_CONFIG[trigger];
  const configColor = (colors as any)?.[config.colorKey] || colors.primary;
  const targetPlan = currentPlan === 'free' ? 'basic' : 'premium';

  const features = currentPlan === 'free' ? {
    basic: [
      { icon: 'chatbubble-ellipses', text: '25 AI coaching credits per day', highlight: true },
      { icon: 'book', text: '50 lessons per day', highlight: true },
      { icon: 'help-circle', text: '20 quizzes per day', highlight: true },
      { icon: 'videocam', text: '3 interview simulations per day', highlight: false },
      { icon: 'flash', text: 'Priority support', highlight: false },
    ],
    premium: [
      { icon: 'infinite', text: 'Unlimited AI coaching', highlight: true },
      { icon: 'book', text: 'Unlimited lessons & content', highlight: true },
      { icon: 'help-circle', text: 'Unlimited quizzes', highlight: true },
      { icon: 'videocam', text: 'Unlimited interview simulations', highlight: true },
      { icon: 'trophy', text: 'Exclusive achievements & rewards', highlight: false },
      { icon: 'people', text: 'Community access', highlight: false },
    ],
  } : {
    premium: [
      { icon: 'infinite', text: 'Unlimited AI coaching', highlight: true },
      { icon: 'book', text: 'Unlimited lessons & content', highlight: true },
      { icon: 'help-circle', text: 'Unlimited quizzes', highlight: true },
      { icon: 'videocam', text: 'Unlimited interview simulations', highlight: true },
      { icon: 'trophy', text: 'Exclusive achievements & rewards', highlight: false },
      { icon: 'people', text: 'Community access', highlight: false },
    ],
  };

  const handleUpgrade = () => {
    onClose();
    router.push('/features/subscription');
  };

  return (
    <Modal
      testID="tv-v2-upgrade-modal"
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View data-testid="tv-v2-upgrade-overlay" testID="tv-v2-upgrade-overlay" style={{
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.6)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
      }}>
        <View style={{
          width: '100%',
          maxWidth: 440,
          backgroundColor: colors.card,
          borderRadius: 20,
          overflow: 'hidden',
          ...(Platform.OS === 'web' ? {
            maxHeight: '90vh',
          } : {}),
        }}>
          {/* Header */}
          <View style={{
            padding: 20,
            backgroundColor: configColor,
            position: 'relative',
          }}>
            <TouchableOpacity
              data-testid="tv-v2-upgrade-close"
              testID="tv-v2-upgrade-close"
              onPress={onClose}
              style={{
                position: 'absolute',
                top: 16,
                right: 16,
                width: 32,
                height: 32,
                borderRadius: 16,
                backgroundColor: 'rgba(255,255,255,0.2)',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 10,
              }}
            >
              <Ionicons name="close" size={20} color={colors.primaryText} />
            </TouchableOpacity>

            <View style={{ alignItems: 'center', paddingTop: 10 }}>
              <View style={{
                width: 64,
                height: 64,
                borderRadius: 32,
                backgroundColor: 'rgba(255,255,255,0.2)',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
              }}>
                <Ionicons name={config.icon as any} size={32} color={colors.primaryText} />
              </View>
              <Text style={{
                fontSize: 22,
                fontWeight: '800',
                color: colors.primaryText,
                marginBottom: 6,
                textAlign: 'center',
              }}>
                {config.title}
              </Text>
              <Text style={{
                fontSize: 14,
                color: 'rgba(255,255,255,0.9)',
                textAlign: 'center',
              }}>
                {config.subtitle}
              </Text>
            </View>
          </View>

          <ScrollView style={{ maxHeight: 400 }} contentContainerStyle={{ padding: 20 }}>
            {/* Current Plan Badge */}
            <View style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 20,
            }}>
              <View style={{
                paddingHorizontal: 14,
                paddingVertical: 6,
                borderRadius: 20,
                backgroundColor: colors.border,
              }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: colors.textMuted }}>
                  Current: {currentPlan.toUpperCase()}
                </Text>
              </View>
            </View>

            {/* Features List */}
            <View style={{
              padding: 18,
              borderRadius: 14,
              backgroundColor: colors.background,
              marginBottom: 16,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 14 }}>
                <Ionicons name="diamond" size={20} color={configColor} style={{ marginRight: 8 }} />
                <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>
                  {targetPlan === 'basic' ? 'Basic Plan' : 'Premium Plan'} Features
                </Text>
              </View>
              
              {features[targetPlan].map((feature, index) => (
                <View
                  key={index}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    paddingVertical: 10,
                    borderBottomWidth: index < features[targetPlan].length - 1 ? 1 : 0,
                    borderBottomColor: colors.border,
                  }}
                >
                  <View style={{
                    width: 32,
                    height: 32,
                    borderRadius: 10,
                    backgroundColor: feature.highlight ? configColor + '15' : colors.border,
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginRight: 12,
                  }}>
                    <Ionicons
                      name={feature.icon as any}
                      size={16}
                      color={feature.highlight ? configColor : colors.textMuted}
                    />
                  </View>
                  <Text style={{
                    flex: 1,
                    fontSize: 14,
                    fontWeight: feature.highlight ? '600' : '500',
                    color: feature.highlight ? colors.text : colors.textMuted,
                  }}>
                    {feature.text}
                  </Text>
                  {feature.highlight && (
                    <View style={{
                      paddingHorizontal: 8,
                      paddingVertical: 3,
                      borderRadius: 6,
                      backgroundColor: configColor + '15',
                    }}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: configColor }}>
                        NEW
                      </Text>
                    </View>
                  )}
                </View>
              ))}
            </View>

            {/* Social Proof */}
            <View style={{
              padding: 16,
              borderRadius: 14,
              backgroundColor: colors.primarySoft,
              borderWidth: 1,
              borderColor: colors.primary,
              marginBottom: 16,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
                <Ionicons name="people" size={18} color={colors.primary} style={{ marginRight: 6 }} />
                <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>
                  Join 10,000+ successful visa applicants
                </Text>
              </View>
              <Text style={{ fontSize: 12, color: colors.text, lineHeight: 18 }}>
                &quot;Premium gave me the confidence to ace my interview. Best investment for my visa journey!&quot; - Sarah M.
              </Text>
            </View>

            {/* Pricing - Platform canonical pricing from /app/backend/routes/iap.py:61-64 */}
            {targetPlan === 'basic' && (
              <Text data-testid="tv-v2-upgrade-basic-price" testID="tv-v2-upgrade-basic-price" style={{ fontSize: 14, textAlign: 'center', color: colors.textMuted, marginBottom: 16 }}>
                Starting at <Text style={{ fontWeight: '700', color: colors.text }}>${getFrontendPlanPrice('basic', 'monthly').toFixed(2)}/month</Text>
              </Text>
            )}
            {targetPlan === 'premium' && (
              <Text data-testid="tv-v2-upgrade-premium-price" testID="tv-v2-upgrade-premium-price" style={{ fontSize: 14, textAlign: 'center', color: colors.textMuted, marginBottom: 16 }}>
                Starting at <Text style={{ fontWeight: '700', color: colors.text }}>${getFrontendPlanPrice('premium', 'monthly').toFixed(2)}/month</Text>
              </Text>
            )}
          </ScrollView>

          {/* Footer Actions */}
          <View style={{
            padding: 20,
            borderTopWidth: 1,
            borderTopColor: colors.border,
          }}>
            <TouchableOpacity
              data-testid="tv-v2-upgrade-primary-cta"
              testID="tv-v2-upgrade-primary-cta"
              onPress={handleUpgrade}
              style={{
                paddingVertical: 16,
                borderRadius: 14,
                backgroundColor: configColor,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                marginBottom: 12,
              }}
            >
              <Text style={{ fontSize: 16, fontWeight: '700', color: colors.primaryText }}>
                Upgrade to {targetPlan === 'basic' ? 'Basic' : 'Premium'}
              </Text>
              <Ionicons name="arrow-forward" size={18} color={colors.primaryText} />
            </TouchableOpacity>

            <TouchableOpacity data-testid="tv-v2-upgrade-later" testID="tv-v2-upgrade-later" onPress={onClose} style={{ paddingVertical: 12, alignItems: 'center' }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.textMuted }}>
                Maybe Later
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
