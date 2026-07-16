import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { FeedbackFormSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

export default function FeedbackScreen() {
  const { t } = useTranslation();
  t('i18n.route.feedback.probe');
  const pageReady = usePageReady();
  const router = useRouter();
  const { user } = useAuth();
  const { colors } = useTheme();
  const [rating, setRating] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const onPrimary = colors.primaryText || colors.buttonText || colors.card;

  const submitFeedback = async () => {
    if (!message.trim()) {
      Alert.alert('Feedback required', 'Please add your feedback before sending.');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/support/feedback', {
        user_id: user?.user_id || 'guest',
        email: user?.email,
        type: 'product-feedback',
        message: message.trim(),
        rating: rating || undefined,
      });
      Alert.alert('Thank you!', 'Your feedback was submitted successfully.');
      setMessage('');
      setRating(null);
    } catch (_e) {
      Alert.alert('Error', 'Unable to submit feedback right now.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!pageReady) return <AppShell><FeedbackFormSkeleton /></AppShell>;
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']}>
        <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <TouchableOpacity onPress={() => router.back()} style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.bgSoft, alignItems: 'center', justifyContent: 'center' }} data-testid="feedback-back" testID="feedback-back" accessibilityRole="button">
            <Ionicons name="arrow-back" size={20} color={colors.text} />
          </TouchableOpacity>
          <Text style={{ flex: 1, textAlign: 'center', fontSize: 16, fontWeight: '700', color: colors.text }} data-testid="feedback-title" testID="feedback-title">{t("ticketFeedbackIntel.tabs.feedback")}</Text>
          <View style={{ width: 40 }} />
        </View>
        <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }} showsVerticalScrollIndicator={false}>
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border }} data-testid="feedback-card" testID="feedback-card">
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{t("help.feedback.title")}</Text>
            <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 6 }}>{t("autofix.batch8.your.feedback.helps.us.refine.ai.coaching.and")}</Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 14 }}>
              {[1, 2, 3, 4, 5].map((value) => (
                <TouchableOpacity
                  key={value}
                  style={{ flex: 1, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: rating === value ? colors.primary : colors.border, backgroundColor: rating === value ? (globalThis as any).__alphaColor(colors.primary, '14') : colors.bgSoft, alignItems: 'center' }}
                  onPress={() => setRating(value)}
                  data-testid={`feedback-rating-${value}`} testID={`feedback-rating-${value}`}
                  accessibilityRole="button"
                >
                  <Text style={{ fontSize: 12, fontWeight: '700', color: rating === value ? colors.primary : colors.textSec }}>{value}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{t("settings.item.rateApp.subtitle")}</Text>
            <TextInput
              style={{ minHeight: 140, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12, marginTop: 12, color: colors.text }}
              placeholder="Tell us what we should improve or add..."
              placeholderTextColor={colors.textMuted}
              multiline
              value={message}
              onChangeText={setMessage}
              data-testid="feedback-message-input" testID="feedback-message-input"
            />
          </View>

          <TouchableOpacity
            style={{ paddingVertical: 14, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', opacity: submitting ? 0.7 : 1 }}
            onPress={submitFeedback}
            disabled={submitting}
            data-testid="feedback-submit" testID="feedback-submit"
            accessibilityRole="button"
          >
            <Text style={{ color: onPrimary, fontWeight: '700' }}>{submitting ? 'Submitting...' : 'Send Feedback'}</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}