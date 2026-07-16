import React from 'react';
import { View, Text, TextInput, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { ThemeColors } from './helpTypes';
import { useTheme } from '../../context/ThemeContext';

interface NovaFeedbackCardProps {
  C: ThemeColors;
  t: (key: string) => string;
  showFeedback: boolean;
  setShowFeedback: (v: boolean) => void;
  feedbackRating: number;
  setFeedbackRating: (v: number) => void;
  feedbackComment: string;
  setFeedbackComment: (v: string) => void;
  feedbackSent: boolean;
  submitFeedback: () => void;
  isEmbedded: boolean;
  isFloating: boolean;
}

export const NovaFeedbackCard = ({
  C, t, showFeedback, setShowFeedback, feedbackRating, setFeedbackRating,
  feedbackComment, setFeedbackComment, feedbackSent, submitFeedback, isEmbedded, isFloating,
}: NovaFeedbackCardProps) => {
  const { colors } = useTheme();

  return (
    <>
      {showFeedback && !feedbackSent && (
        <View style={{ marginTop: isEmbedded || isFloating ? 10 : 12, marginBottom: 8, padding: isEmbedded || isFloating ? 12 : 16, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border }} data-testid="chat-feedback-panel" testID="chat-feedback-panel">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ionicons name="chatbox-ellipses" size={16} color={C.primary} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{t('help.feedback.title')}</Text>
            <TouchableOpacity aria-label="close button" onPress={() => setShowFeedback(false)} style={{ marginLeft: 'auto' }}>
              <Ionicons name="close" size={16} color={C.textMuted} />
            </TouchableOpacity>
          </View>
          <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 12 }}>{t('help.feedback.subtitle')}</Text>
          <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginBottom: 12 }}>
            {[1, 2, 3, 4, 5].map(star => (
              <TouchableOpacity key={star} data-testid={`feedback-star-${star}`} testID={`feedback-star-${star}`} onPress={() => setFeedbackRating(star)} style={{ padding: 4 }}>
                <Ionicons name={star <= feedbackRating ? 'star' : 'star-outline'} size={28} color={star <= feedbackRating ? colors.warning : C.textMuted} />
              </TouchableOpacity>
            ))}
          </View>
          {feedbackRating > 0 && (
            <>
              <TextInput data-testid="feedback-comment" testID="feedback-comment" style={{ backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, color: C.text, fontSize: 13, borderWidth: 1, borderColor: C.border, marginBottom: 10, minHeight: 50 }}
                placeholder={t('help.feedback.placeholder')} placeholderTextColor={C.textMuted}
                value={feedbackComment} onChangeText={setFeedbackComment} multiline />
              <TouchableOpacity data-testid="feedback-submit-btn" testID="feedback-submit-btn" onPress={submitFeedback} style={{ backgroundColor: C.primary, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}>
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{t('help.feedback.submit')}</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      )}
      {feedbackSent && (
        <View style={{ marginTop: 8, padding: 12, backgroundColor: (globalThis as any).__alphaColor(colors.success, '10'), borderRadius: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="feedback-success" testID="feedback-success">
          <Ionicons name="checkmark-circle" size={18} color={colors.successText} />
          <Text style={{ fontSize: 13, color: colors.successText, fontWeight: '600' }}>{t('help.feedback.thanks')}</Text>
        </View>
      )}
    </>
  );
};
