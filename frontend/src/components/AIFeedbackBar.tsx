/**
 * AIFeedbackBar — Reusable feedback bar for all AI feature responses.
 * Shows disclaimer, thumbs up/down, and optional text feedback.
 */
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface AIFeedbackBarProps {
  feature: string;
  response?: string;
  showDisclaimer?: boolean;
  disclaimerText?: string;
  compact?: boolean;
}

const DISCLAIMERS: Record<string, string> = {
  medimate: 'AI health info is for guidance only. Always consult a licensed healthcare professional.',
  pennypilot: 'AI financial insights are informational. Consult a financial advisor before investing.',
  travelpal: 'Travel information may not reflect real-time changes. Verify with official sources.',
  'ai-chat': 'AI responses may be inaccurate. Verify important information independently.',
  default: 'AI-generated content. Results may vary. Use your judgement and consult experts when needed.',
};

export default function AIFeedbackBar({
  feature,
  response = '',
  showDisclaimer = true,
  disclaimerText,
  compact = false,
}: AIFeedbackBarProps) {
  const { user } = useAuth();
  const { colors } = useTheme();
  const [rating, setRating] = useState<'up' | 'down' | null>(null);
  const [comment, setComment] = useState('');
  const [showInput, setShowInput] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const disclaimer = disclaimerText || DISCLAIMERS[feature] || DISCLAIMERS.default;

  const submitFeedback = async (r: 'up' | 'down') => {
    setRating(r);
    if (r === 'down') {
      setShowInput(true);
      return;
    }
    try {
      await api.post('/ai-feature-feedback', {
        user_id: user?.user_id || 'guest',
        feature,
        rating: r,
        response,
      });
      setSubmitted(true);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIFeedbackBar.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const submitComment = async () => {
    try {
      await api.post('/ai-feature-feedback', {
        user_id: user?.user_id || 'guest',
        feature,
        rating: 'down',
        comment,
        response,
      });
      setSubmitted(true);
      setShowInput(false);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIFeedbackBar.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  return (
    <View
      style={{ marginTop: 12 }}
      testID={`ai-feedback-bar-${feature}`}
      accessible
      accessibilityLabel="AI feedback section"
    >
      {showDisclaimer && (
        <View style={{
          flexDirection: 'row', alignItems: 'flex-start', gap: 6,
          backgroundColor: colors.warningSoft, borderRadius: 10,
          paddingHorizontal: 10, paddingVertical: 7, marginBottom: 8,
          borderWidth: 1, borderColor: colors.warningSoft,
        }}>
          <Ionicons name="information-circle-outline" size={14} color={'var(--app-warning)'} style={{ marginTop: 1 }} />
          <Text style={{ fontSize: 11, color: colors.warningText, flex: 1, lineHeight: 16 }} testID={`ai-disclaimer-${feature}`}>
            {disclaimer}
          </Text>
        </View>
      )}

      {!submitted ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={{ fontSize: 11, color: colors.textMuted, flex: 1 }}>Was this helpful?</Text>
          <TouchableOpacity onPress={() => submitFeedback('up')} accessibilityLabel="Submit feedback in aifeedback bar button"
            style={{
              width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
              backgroundColor: rating === 'up' ? 'var(--app-success-soft)' : colors.card,
              borderWidth: 1, borderColor: rating === 'up' ? 'var(--app-success)' : colors.border,
            }}
            testID={`feedback-up-${feature}`}
            accessibilityLabel="Helpful"
          >
            <Ionicons name="thumbs-up" size={13} color={rating === 'up' ? 'var(--app-success)' : 'var(--app-text-muted)'} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => submitFeedback('down')} accessibilityLabel="Submit feedback in aifeedback bar button"
            style={{
              width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
              backgroundColor: rating === 'down' ? 'var(--app-error-soft)' : colors.card,
              borderWidth: 1, borderColor: rating === 'down' ? 'var(--app-error)' : colors.border,
            }}
            testID={`feedback-down-${feature}`}
            accessibilityLabel="Not helpful"
          >
            <Ionicons name="thumbs-down" size={13} color={rating === 'down' ? 'var(--app-error)' : 'var(--app-text-muted)'} />
          </TouchableOpacity>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primarySoft, borderRadius: 20, paddingHorizontal: 7, paddingVertical: 3 }}>
            <Ionicons name="sparkles" size={9} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 9, color: colors.primary, fontWeight: '700' }}>AI</Text>
          </View>
        </View>
      ) : (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="checkmark-circle" size={14} color={'var(--app-success)'} />
          <Text style={{ fontSize: 11, color: colors.successText }}>Thanks for your feedback!</Text>
        </View>
      )}

      {showInput && !submitted && (
        <View style={{ marginTop: 8, gap: 6 }}>
          <TextInput
            value={comment}
            onChangeText={setComment}
            placeholder="What went wrong? (optional)"
            placeholderTextColor="var(--app-primary)"
            style={{
              backgroundColor: FEEDBACK_INPUT_BG, borderRadius: 10, padding: 10,
              color: colors.primaryText, fontSize: 12, borderWidth: 1, borderColor: colors.border,
            }}
            testID={`feedback-comment-${feature}`}
            multiline
            numberOfLines={2}
          />
          <TouchableOpacity accessibilityLabel="Submit Report"
            onPress={submitComment}
            style={{ backgroundColor: colors.primary, borderRadius: 10, padding: 8, alignItems: 'center' }}
            testID={`feedback-submit-${feature}`}
          >
            <Text style={{ fontSize: 12, color: colors.primaryText, fontWeight: '700' }}>Submit Report</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
