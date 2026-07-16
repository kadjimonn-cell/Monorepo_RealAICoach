import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaQuiz({ userId, plan }: { userId: string; plan: string }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [quizzes, setQuizzes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [actionError, setActionError] = useState('');
  const [activeQuiz, setActiveQuiz] = useState<any>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);

  const loadQuizzes = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const res = await api.get('/travel-visa/quizzes');
      setQuizzes(res.data?.quizzes || []);
    } catch (e: any) {
      setPageError(e?.response?.data?.detail || tx('travelVisa.quiz.errors.loadFailed', 'Unable to load quizzes right now.'));
      setQuizzes([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadQuizzes();
  }, [loadQuizzes]);

  const startQuiz = useCallback(async (quizId: string) => {
    setActionError('');
    try {
      const res = await api.get(`/travel-visa/quizzes/${quizId}`);
      setActiveQuiz(res.data?.quiz);
      setCurrentIdx(0);
      setAnswers({});
      setResult(null);
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.quiz.errors.openFailed', 'Failed to open quiz. Please retry.'));
    }
  }, []);

  const selectAnswer = useCallback((questionIdx: number, answerIdx: number) => {
    setAnswers(prev => ({ ...prev, [String(questionIdx)]: answerIdx }));
  }, []);

  const submitQuiz = useCallback(async () => {
    if (!activeQuiz) return;
    setSubmitting(true);
    try {
      const res = await api.post('/travel-visa/quizzes/submit', {
        user_id: userId, quiz_id: activeQuiz.quiz_id, answers,
      });
      setResult(res.data);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || tx('travelVisa.quiz.errors.submitFailed', 'Error submitting quiz');
      setResult({ error: detail });
    }
    setSubmitting(false);
  }, [activeQuiz, userId, answers]);

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (result) {
    return (
      <View data-testid="tv-quiz-result" style={{
        padding: 24, borderRadius: 16, backgroundColor: colors.card,
        borderWidth: 1, borderColor: colors.border, alignItems: 'center',
      }}>
        {result.error ? (
          <Text style={{ fontSize: 14, color: colors.error, textAlign: 'center' }}>{result.error}</Text>
        ) : (
          <>
            <View style={{
              width: 80, height: 80, borderRadius: 40, borderWidth: 4,
              borderColor: result.passed ? colors.success : colors.error,
              alignItems: 'center', justifyContent: 'center', marginBottom: 16,
            }}>
              <Text style={{ fontSize: 24, fontWeight: '800', color: colors.text }}>{result.percentage}%</Text>
            </View>
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 4 }}>
              {result.passed ? tx('travelVisa.quiz.results.congratulations', 'Congratulations!') : tx('travelVisa.quiz.results.keepPracticing', 'Keep Practicing!')}
            </Text>
            <Text style={{ fontSize: 13, color: colors.textMuted, marginBottom: 8 }}>
              {result.score}/{result.total} {tx('travelVisa.quiz.results.correct', 'correct')} | {result.xp_earned} XP {tx('travelVisa.quiz.results.xpEarned', 'earned')}
            </Text>
            <View style={{
              paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8,
              backgroundColor: result.passed ? colors.successSoft : colors.errorSoft,
            }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: result.passed ? colors.successText : colors.errorText }}>
                {result.passed ? tx('travelVisa.quiz.results.passed', 'PASSED') : tx('travelVisa.quiz.results.needsImprovement', 'NEEDS IMPROVEMENT')}
              </Text>
            </View>
            {/* Show Results */}
            {result.results?.map((r: any, i: number) => (
              <View key={i} style={{
                width: '100%', marginTop: 12, padding: 12, borderRadius: 10,
                backgroundColor: r.is_correct ? colors.successSoft : colors.errorSoft,
                borderWidth: 1, borderColor: r.is_correct ? (globalThis as any).__alphaColor(colors.success, '30') : colors.error + '30',
              }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 4 }}>{r.question}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={r.is_correct ? 'checkmark-circle' : 'close-circle'} size={14}
                    color={r.is_correct ? colors.success : colors.error} />
                  <Text style={{ fontSize: 11, color: r.is_correct ? colors.successText : colors.errorText }}>
                    {r.is_correct ? tx('travelVisa.quiz.results.correctShort', 'Correct') : tx('travelVisa.quiz.results.incorrectShort', 'Incorrect')}
                  </Text>
                </View>
              </View>
            ))}
          </>
        )}
        <TouchableOpacity data-testid="tv-quiz-back-btn"
          onPress={() => { setActiveQuiz(null); setResult(null); }}
          style={{ marginTop: 20, paddingVertical: 12, paddingHorizontal: 24, borderRadius: 10, backgroundColor: colors.primary }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.quiz.actions.backToQuizzes', 'Back to Quizzes')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (activeQuiz) {
    const questions = activeQuiz.questions || [];
    const question = questions[currentIdx];
    const totalQuestions = questions.length;
    const answered = Object.keys(answers).length;

    return (
      <View data-testid="tv-quiz-active" style={{
        borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
        overflow: 'hidden',
      }}>
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14,
          borderBottomWidth: 1, borderBottomColor: colors.border,
        }}>
          <Ionicons name="help-circle" size={18} color={colors.primary} />
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, flex: 1 }}>{activeQuiz.title}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted }}>{currentIdx + 1}/{totalQuestions}</Text>
        </View>
        {/* Progress Bar */}
        <View style={{ height: 4, backgroundColor: colors.surfaceHover }}>
          <View style={{
            height: 4, backgroundColor: colors.primary,
            width: `${((currentIdx + 1) / totalQuestions) * 100}%` as any,
            borderRadius: 2, ...WEB_TRANSITION,
          }} />
        </View>
        <View style={{ padding: 20 }}>
          {question && (
            <>
              <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text, marginBottom: 16, lineHeight: 22 }}>
                {question.q}
              </Text>
              {question.options?.map((opt: string, i: number) => {
                const selected = answers[String(currentIdx)] === i;
                return (
                  <TouchableOpacity key={i} data-testid={`tv-quiz-option-${i}`}
                    onPress={() => selectAnswer(currentIdx, i)}
                    style={{
                      padding: 14, borderRadius: 10, marginBottom: 8,
                      backgroundColor: selected ? colors.primarySoft : colors.surfaceHover,
                      borderWidth: 1.5, borderColor: selected ? colors.primary : colors.border,
                      flexDirection: 'row', alignItems: 'center', gap: 10,
                      ...WEB_TRANSITION,
                    }}>
                    <View style={{
                      width: 24, height: 24, borderRadius: 12, borderWidth: 2,
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? colors.primary : 'transparent',
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      {selected && <Ionicons name="checkmark" size={14} color={colors.primaryText} />}
                    </View>
                    <Text style={{ flex: 1, fontSize: 13, color: colors.text }}>{opt}</Text>
                  </TouchableOpacity>
                );
              })}
            </>
          )}
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
            {currentIdx > 0 && (
              <TouchableOpacity accessibilityLabel="Set current idx in travel visa quiz button" onPress={() => setCurrentIdx(prev => prev - 1)}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{tx('travelVisa.quiz.actions.previous', 'Previous')}</Text>
              </TouchableOpacity>
            )}
            {currentIdx < totalQuestions - 1 ? (
              <TouchableOpacity data-testid="tv-quiz-next-btn" onPress={() => setCurrentIdx(prev => prev + 1)}
                disabled={answers[String(currentIdx)] === undefined}
                style={{
                  flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center',
                  backgroundColor: colors.primary, opacity: answers[String(currentIdx)] === undefined ? 0.5 : 1,
                }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.quiz.actions.next', 'Next')}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity data-testid="tv-quiz-submit-btn" onPress={submitQuiz}
                disabled={answered < totalQuestions || submitting}
                style={{
                  flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center',
                  backgroundColor: colors.primary, opacity: answered < totalQuestions ? 0.5 : 1,
                }}>
                {submitting ? <ActivityIndicator size="small" color={colors.primaryText} /> :
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.quiz.actions.submitQuiz', 'Submit Quiz')}</Text>}
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>
    );
  }

  return (
    <View data-testid="tv-quiz-list">
      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('travelVisa.quiz.header.title', 'Knowledge Quizzes')}</Text>
      {!!pageError && (
        <View data-testid="tv-quiz-load-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 10 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
          <TouchableOpacity data-testid="tv-quiz-retry-load-btn" onPress={() => void loadQuizzes()} style={{ alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.error }}>
            <Text style={{ fontSize: 11, color: colors.errorTextInverse || colors.primaryText, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}
      {!!actionError && (
        <View data-testid="tv-quiz-action-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 10 }}>
          <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }}>{actionError}</Text>
        </View>
      )}
      {quizzes.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="help-circle-outline" size={40} color={colors.textMuted} />
          <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 10 }}>{tx('travelVisa.quiz.states.noneAvailable', 'No quizzes available yet')}</Text>
        </View>
      ) : (
        quizzes.map((q, i) => (
          <TouchableOpacity data-testid={`tv-quiz-card-${i}`} key={q.quiz_id || i}
            onPress={() => startQuiz(q.quiz_id)}
            style={{
              padding: 16, borderRadius: 14, backgroundColor: colors.card,
              borderWidth: 1, borderColor: colors.border, marginBottom: 10,
              flexDirection: 'row', alignItems: 'center', gap: 12,
              ...WEB_TRANSITION,
            }}>
            <View style={{
              width: 44, height: 44, borderRadius: 12, backgroundColor: colors.primarySoft,
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name="help-circle" size={22} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{q.title}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                {q.question_count} {tx('travelVisa.quiz.labels.questions', 'questions')} | {tx('travelVisa.quiz.labels.pass', 'Pass')}: {q.passing_score}% | {q.xp_reward} XP
              </Text>
            </View>
            {q.tier && q.tier !== 'free' && (
              <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '20') }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: colors.warning, textTransform: 'uppercase' }}>{q.tier}</Text>
              </View>
            )}
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}
