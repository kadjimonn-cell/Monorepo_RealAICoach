import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaChallenge({ userId, plan }: { userId: string; plan: string }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [challenges, setChallenges] = useState<any[]>([]);
  const [quizzes, setQuizzes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [friendId, setFriendId] = useState('');
  const [selectedQuiz, setSelectedQuiz] = useState('');
  const [creating, setCreating] = useState(false);
  const [activeChallenge, setActiveChallenge] = useState<any>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [pageError, setPageError] = useState('');
  const [actionError, setActionError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const [chRes, qRes] = await Promise.all([
        api.get(`/travel-visa/challenge/list/${userId}`),
        api.get('/travel-visa/quizzes'),
      ]);
      setChallenges(chRes.data?.challenges || []);
      setQuizzes(qRes.data?.quizzes || []);
    } catch (e: any) {
      setPageError(e?.response?.data?.detail || tx('travelVisa.challenge.errors.loadFailed', 'Unable to load challenge data.'));
      setChallenges([]);
      setQuizzes([]);
    }
    setLoading(false);
  }, [userId]);

  useEffect(() => { loadData(); }, [loadData]);

  const createChallenge = useCallback(async () => {
    if (!friendId.trim() || !selectedQuiz) return;
    setCreating(true);
    setActionError('');
    try {
      await api.post('/travel-visa/challenge/create', {
        challenger_id: userId, challenged_id: friendId.trim(), quiz_id: selectedQuiz,
      });
      setShowCreate(false);
      setFriendId('');
      setSelectedQuiz('');
      await loadData();
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.challenge.errors.createFailed', 'Could not create challenge.'));
    }
    setCreating(false);
  }, [userId, friendId, selectedQuiz, loadData]);

  const acceptChallenge = useCallback(async (challenge: any) => {
    setActionError('');
    try {
      const res = await api.get(`/travel-visa/quizzes/${challenge.quiz_id}`);
      setActiveChallenge({ ...challenge, quiz: res.data?.quiz });
      setCurrentIdx(0);
      setAnswers({});
      setResult(null);
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.challenge.errors.openQuizFailed', 'Unable to open this challenge quiz.'));
    }
  }, []);

  const submitChallenge = useCallback(async () => {
    if (!activeChallenge) return;
    setSubmitting(true);
    setActionError('');
    try {
      const res = await api.post('/travel-visa/challenge/submit', {
        user_id: userId, challenge_id: activeChallenge.challenge_id, answers,
      });
      setResult(res.data);
      await loadData();
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.challenge.errors.submitFailed', 'Challenge submission failed.'));
    }
    setSubmitting(false);
  }, [activeChallenge, userId, answers, loadData]);

  const statusColor = (status: string) => {
    if (status === 'completed') return colors.success;
    if (status === 'in_progress') return colors.warning;
    return colors.primary;
  };

  if (loading) {
    return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={colors.primary} /></View>;
  }

  if (result) {
    return (
      <View data-testid="tv-challenge-result" style={{
        padding: 24, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, alignItems: 'center',
      }}>
        <Ionicons name="trophy" size={48} color={colors.primary} />
        <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginTop: 12 }}>{tx('travelVisa.challenge.result.submitted', 'Challenge Submitted!')}</Text>
        <Text style={{ fontSize: 28, fontWeight: '900', color: colors.primary, marginTop: 8 }}>{result.score}%</Text>
        <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
          {result.status === 'completed' ? (
            result.winner_id === userId ? tx('travelVisa.challenge.result.youWon', 'You won! +100 bonus XP') :
            result.winner_id === 'tie' ? tx('travelVisa.challenge.result.tie', "It's a tie! +50 bonus XP") : tx('travelVisa.challenge.result.friendWon', 'Your friend won! +50 bonus XP')
          ) : tx('travelVisa.challenge.result.waitingFriend', 'Waiting for your friend to complete...')}
        </Text>
        <TouchableOpacity accessibilityLabel="Set active challenge in travel visa challenge button" onPress={() => { setActiveChallenge(null); setResult(null); }}
          style={{ marginTop: 16, paddingVertical: 12, paddingHorizontal: 24, borderRadius: 10, backgroundColor: colors.primary }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.backToChallenges', 'Back to Challenges')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (activeChallenge?.quiz) {
    const questions = activeChallenge.quiz.questions || [];
    const question = questions[currentIdx];
    const totalQ = questions.length;
    return (
      <View data-testid="tv-challenge-quiz" style={{
        borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, overflow: 'hidden',
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <Ionicons name="flash" size={18} color={colors.primary} />
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, flex: 1 }}>Challenge: {activeChallenge.quiz_title}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted }}>{currentIdx + 1}/{totalQ}</Text>
        </View>
        <View style={{ height: 4, backgroundColor: colors.surfaceHover }}>
          <View style={{ height: 4, backgroundColor: colors.primary, width: `${((currentIdx + 1) / totalQ) * 100}%` as any, borderRadius: 2, ...WEB_TRANSITION }} />
        </View>
        <View style={{ padding: 20 }}>
          {question && (
            <>
              <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text, marginBottom: 16, lineHeight: 22 }}>{question.q}</Text>
              {question.options?.map((opt: string, i: number) => {
                const selected = answers[String(currentIdx)] === i;
                return (
                  <TouchableOpacity key={i} accessibilityLabel="Set answers in travel visa challenge button" onPress={() => setAnswers(prev => ({ ...prev, [String(currentIdx)]: i }))}
                    style={{
                      padding: 14, borderRadius: 10, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 10,
                      backgroundColor: selected ? colors.primarySoft : colors.surfaceHover,
                      borderWidth: 1.5, borderColor: selected ? colors.primary : colors.border, ...WEB_TRANSITION,
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
              <TouchableOpacity accessibilityLabel="Set current idx in travel visa challenge button" onPress={() => setCurrentIdx(p => p - 1)}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{tx('travelVisa.challenge.actions.previous', 'Previous')}</Text>
              </TouchableOpacity>
            )}
            {currentIdx < totalQ - 1 ? (
              <TouchableOpacity accessibilityLabel="Set current idx in travel visa challenge button" onPress={() => setCurrentIdx(p => p + 1)}
                disabled={answers[String(currentIdx)] === undefined}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.primary, opacity: answers[String(currentIdx)] === undefined ? 0.5 : 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.next', 'Next')}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity data-testid="tv-challenge-submit-btn" onPress={submitChallenge}
                disabled={Object.keys(answers).length < totalQ || submitting}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.primary, opacity: Object.keys(answers).length < totalQ ? 0.5 : 1 }}>
                {submitting ? <ActivityIndicator size="small" color={colors.primaryText} /> :
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.submitChallenge', 'Submit Challenge')}</Text>}
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>
    );
  }

  return (
    <View data-testid="tv-challenge-list">
      {!!pageError && (
        <View data-testid="tv-challenge-load-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 10 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
          <TouchableOpacity data-testid="tv-challenge-retry-load-btn" onPress={() => void loadData()} style={{ alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.error }}>
            <Text style={{ fontSize: 11, color: colors.errorTextInverse || colors.primaryText, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}
      {!!actionError && (
        <View data-testid="tv-challenge-action-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 10 }}>
          <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }}>{actionError}</Text>
        </View>
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('travelVisa.challenge.header.title', 'Challenge a Friend')}</Text>
        <TouchableOpacity data-testid="tv-challenge-create-btn" onPress={() => setShowCreate(!showCreate)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.primary }}>
          <Ionicons name="add" size={16} color={colors.primaryText} />
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.newChallenge', 'New Challenge')}</Text>
        </TouchableOpacity>
      </View>

      {showCreate && (
        <View style={{
          padding: 16, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, marginBottom: 16,
        }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 6 }}>{tx('travelVisa.challenge.fields.friendUserId', "Friend's User ID")}</Text>
          <TextInput data-testid="tv-challenge-friend-input" value={friendId} onChangeText={setFriendId}
            placeholder={tx('travelVisa.challenge.fields.friendPlaceholder', "Enter your friend's user ID")} placeholderTextColor={colors.placeholder}
            style={{
              height: 42, borderRadius: 10, paddingHorizontal: 14, fontSize: 14, marginBottom: 12,
              backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder, color: colors.inputText,
              ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
            }} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.challenge.fields.selectQuiz', 'Select Quiz')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginBottom: 14 }}>
            {quizzes.map((q: any) => (
              <TouchableOpacity key={q.quiz_id} accessibilityLabel="q.title" onPress={() => setSelectedQuiz(q.quiz_id)}
                style={{
                  paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                  backgroundColor: selectedQuiz === q.quiz_id ? colors.primary : colors.surfaceHover,
                  borderWidth: 1, borderColor: selectedQuiz === q.quiz_id ? colors.primary : colors.border, ...WEB_TRANSITION,
                }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: selectedQuiz === q.quiz_id ? colors.primaryText : colors.text }}>{q.title}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <TouchableOpacity data-testid="tv-challenge-send-btn" onPress={createChallenge}
            disabled={!friendId.trim() || !selectedQuiz || creating}
            style={{
              paddingVertical: 12, borderRadius: 10, alignItems: 'center', backgroundColor: colors.primary,
              opacity: !friendId.trim() || !selectedQuiz ? 0.5 : 1,
            }}>
            {creating ? <ActivityIndicator size="small" color={colors.primaryText} /> :
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.sendChallenge', 'Send Challenge')}</Text>}
          </TouchableOpacity>
        </View>
      )}

      {challenges.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center', borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="flash-outline" size={48} color={colors.textMuted} />
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginTop: 12 }}>{tx('travelVisa.challenge.states.noneYet', 'No challenges yet')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4, textAlign: 'center' }}>
            {tx('travelVisa.challenge.states.noneYetDescription', 'Challenge a friend to a quiz and earn bonus XP together!')}
          </Text>
        </View>
      ) : (
        challenges.map((ch, i) => {
          const isChallenger = ch.challenger_id === userId;
          const canPlay = !isChallenger && ch.status === 'pending' && ch.challenged_score === null;
          const canPlayChallenger = isChallenger && ch.challenger_score === null;
          return (
            <View data-testid={`tv-challenge-card-${i}`} key={ch.challenge_id || i} style={{
              padding: 16, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, marginBottom: 10,
              ...(Platform.OS === 'web' ? { boxShadow: `0 1px 4px ${colors.shadowColor}` } as any : {}),
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <Ionicons name="flash" size={20} color={statusColor(ch.status)} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{ch.quiz_title}</Text>
                  <Text style={{ fontSize: 11, color: colors.textMuted }}>
                    {ch.challenger_name} vs {ch.challenged_name}
                  </Text>
                </View>
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(statusColor(ch.status), '20') }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: statusColor(ch.status), textTransform: 'uppercase' }}>{ch.status}</Text>
                </View>
              </View>
              {ch.status === 'completed' && (
                <View style={{ flexDirection: 'row', gap: 12, marginTop: 4 }}>
                  <Text style={{ fontSize: 12, color: colors.textMuted }}>
                    {ch.challenger_name}: {ch.challenger_score ?? '-'}%
                  </Text>
                  <Text style={{ fontSize: 12, color: colors.textMuted }}>
                    {ch.challenged_name}: {ch.challenged_score ?? '-'}%
                  </Text>
                  {ch.winner_id && ch.winner_id !== 'tie' && (
                    <Text style={{ fontSize: 12, fontWeight: '600', color: colors.success }}>
                      {tx('travelVisa.challenge.labels.winner', 'Winner')}: {ch.winner_id === userId ? tx('travelVisa.challenge.labels.you', 'You!') : ch.winner_id === ch.challenger_id ? ch.challenger_name : ch.challenged_name}
                    </Text>
                  )}
                  {ch.winner_id === 'tie' && <Text style={{ fontSize: 12, fontWeight: '600', color: colors.warning }}>{tx('travelVisa.challenge.labels.tie', 'Tie!')}</Text>}
                </View>
              )}
              {(canPlay || canPlayChallenger) && (
                <TouchableOpacity accessibilityLabel="Accept challenge in travel visa challenge button" onPress={() => acceptChallenge(ch)}
                  style={{ marginTop: 8, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: colors.primary }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tx('travelVisa.challenge.actions.takeQuiz', 'Take Quiz')}</Text>
                </TouchableOpacity>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}
