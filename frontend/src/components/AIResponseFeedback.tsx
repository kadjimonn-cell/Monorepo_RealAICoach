import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface AIResponseFeedbackProps {
  featureKey: string;
  responseText?: string;
  sessionId?: string;
  contextLabel?: string;
  testId?: string;
}

export default function AIResponseFeedback({
  featureKey,
  responseText,
  sessionId,
  contextLabel = 'Was this response helpful?',
  testId = 'ai-response-feedback',
}: AIResponseFeedbackProps) {
  const { user } = useAuth();
  const { colors } = useTheme();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    container: {
      borderWidth: 1,
      borderRadius: 16,
      padding: 14,
      gap: 12,
      marginTop: 14,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
    },
    title: {
      fontSize: 13,
      fontWeight: '700',
    },
    statusPill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 10,
      paddingVertical: 6,
      borderRadius: 999,
    },
    statusText: {
      fontSize: 11,
      fontWeight: '600',
    },
    actions: {
      flexDirection: 'row',
      gap: 10,
    },
    actionBtn: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      paddingVertical: 10,
      borderRadius: 12,
      borderWidth: 1,
    },
    actionText: {
      fontSize: 12,
      fontWeight: '600',
    },
    form: {
      gap: 10,
    },
    input: {
      minHeight: 80,
      borderRadius: 12,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 10,
      fontSize: 13,
    },
    submitBtn: {
      paddingVertical: 12,
      borderRadius: 12,
      alignItems: 'center',
    },
    submitText: {
      color: colors.primaryText,
      fontWeight: '700',
      fontSize: 13,
    },
  });
  const [rating, setRating] = useState<null | 1 | -1>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const excerpt = useMemo(() => (responseText ? responseText.slice(0, 600) : ''), [responseText]);

  const submitFeedback = async () => {
    if (!rating || submitted || submitting) return;
    setSubmitting(true);
    try {
      await api.post('/ai-feedback', {
        user_id: user?.user_id || 'guest',
        feature_key: featureKey,
        rating,
        comment: comment.trim() || undefined,
        response_excerpt: excerpt || undefined,
        session_id: sessionId,
      });
      setSubmitted(true);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIResponseFeedback.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSubmitting(false);
    }
  };

  if (!responseText) return null;

  return (
    <View style={[styles.container, { borderColor: colors.border, backgroundColor: colors.card }]} data-testid={testId} testID={testId}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>{contextLabel}</Text>
        {submitted ? (
          <View style={[styles.statusPill, { backgroundColor: (globalThis as any).__alphaColor(colors.success, '18') }]}>
            <Ionicons name="checkmark-circle" size={14} color={'var(--app-success)'} />
            <Text style={[styles.statusText, { color: colors.successText }]}>Thanks for the feedback</Text>
          </View>
        ) : null}
      </View>
      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.actionBtn, { borderColor: colors.border, backgroundColor: rating === 1 ? colors.primarySoft : 'var(--app-text-muted)' }]}
          onPress={() => setRating(1)}
          data-testid={`${testId}-thumbs-up`} testID={`${testId}-thumbs-up`}
          accessibilityRole="button"
        >
          <Ionicons name="thumbs-up" size={16} color={rating === 1 ? 'var(--app-primary)' : 'var(--app-text-muted)'} />
          <Text style={[styles.actionText, { color: rating === 1 ? 'var(--app-primary)' : 'var(--app-text-muted)' }]}>Helpful</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, { borderColor: colors.border, backgroundColor: rating === -1 ? colors.errorSoft : 'var(--app-text-muted)' }]}
          onPress={() => setRating(-1)}
          data-testid={`${testId}-thumbs-down`} testID={`${testId}-thumbs-down`}
          accessibilityRole="button"
        >
          <Ionicons name="thumbs-down" size={16} color={rating === -1 ? 'var(--app-error)' : 'var(--app-text-muted)'} />
          <Text style={[styles.actionText, { color: rating === -1 ? 'var(--app-error)' : 'var(--app-text-muted)' }]}>Needs work</Text>
        </TouchableOpacity>
      </View>
      {rating ? (
        <View style={styles.form}>
          <TextInput
            style={[styles.input, { borderColor: colors.border, color: colors.text }]}
            placeholder="Tell us what could be improved..."
            placeholderTextColor={'var(--app-text-muted)'}
            value={comment}
            onChangeText={setComment}
            multiline
            data-testid={`${testId}-comment-input`} testID={`${testId}-comment-input`}
          />
          <TouchableOpacity
            style={[styles.submitBtn, { backgroundColor: colors.primary, opacity: submitted ? 0.6 : 1 }]}
            onPress={submitFeedback}
            disabled={submitted || submitting}
            data-testid={`${testId}-submit`} testID={`${testId}-submit`}
            accessibilityRole="button"
          >
            {submitting ? (
              <ActivityIndicator color="var(--app-primary-text)" />
            ) : (
              <Text style={styles.submitText}>{submitted ? 'Submitted' : 'Submit Feedback'}</Text>
            )}
          </TouchableOpacity>
        </View>
      ) : null}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
