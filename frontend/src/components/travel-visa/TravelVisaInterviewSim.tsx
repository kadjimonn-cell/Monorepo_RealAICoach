import React, { useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import CountryFlag from '../CountryFlag';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaInterviewSim({ userId, plan, countries }: { userId: string; plan: string; countries: any[] }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedCountry, setSelectedCountry] = useState('');
  const [selectedVisa, setSelectedVisa] = useState('');
  const [difficulty, setDifficulty] = useState('medium');
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentQ, setCurrentQ] = useState(0);
  const [totalQ, setTotalQ] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [answerText, setAnswerText] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  const startInterview = useCallback(async () => {
    if (!selectedCountry || !selectedVisa) return;
    setLoading(true);
    try {
      const res = await api.post('/travel-visa/interview/start', {
        user_id: userId, country: selectedCountry, visa_type: selectedVisa, difficulty,
      });
      setSessionId(res.data?.session_id);
      setMessages([{ role: 'interviewer', content: res.data?.question }]);
      setCurrentQ(res.data?.question_number || 1);
      setTotalQ(res.data?.total_questions || 8);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || tx('travelVisa.interview.errors.startFailed', 'Failed to start interview');
      setMessages([{ role: 'system', content: detail }]);
    }
    setLoading(false);
  }, [userId, selectedCountry, selectedVisa, difficulty]);

  const submitAnswer = useCallback(async () => {
    if (!answerText.trim() || !sessionId || loading) return;
    const myAnswer = answerText.trim();
    setAnswerText('');
    setMessages(prev => [...prev, { role: 'applicant', content: myAnswer }]);
    setLoading(true);
    try {
      const res = await api.post('/travel-visa/interview/answer', {
        user_id: userId, session_id: sessionId, question_id: String(currentQ), answer: myAnswer,
      });
      setMessages(prev => [...prev, { role: 'interviewer', content: res.data?.response }]);
      setCurrentQ(res.data?.question_number || currentQ + 1);
      if (res.data?.is_complete) setIsComplete(true);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'system', content: tx('travelVisa.interview.errors.submitFailed', 'Error submitting answer.') }]);
    }
    setLoading(false);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [answerText, sessionId, loading, userId, currentQ]);

  if (!sessionId) {
    return (
      <View data-testid="tv-interview-setup" style={{
        padding: 24, borderRadius: 16, backgroundColor: colors.card,
        borderWidth: 1, borderColor: colors.border,
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="videocam" size={18} color={colors.primary} />
          </View>
          <View>
            <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('travelVisa.interview.header.title', 'AI Interview Simulator')}</Text>
            <Text style={{ fontSize: 12, color: colors.textMuted }}>{tx('travelVisa.interview.header.subtitle', 'Practice embassy interviews with AI')}</Text>
          </View>
        </View>
        <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.interview.fields.selectCountry', 'Select Country')}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginBottom: 14 }}>
          {countries.slice(0, 15).map((c: any) => (
            <TouchableOpacity key={c.code} data-testid={`tv-sim-country-${c.code}`}
              onPress={() => { setSelectedCountry(c.name); setSelectedVisa(''); }}
              style={{
                paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, flexDirection: 'row', gap: 6,
                backgroundColor: selectedCountry === c.name ? colors.primary : colors.surfaceHover,
                borderWidth: 1, borderColor: selectedCountry === c.name ? colors.primary : colors.border,
                alignItems: 'center', ...WEB_TRANSITION,
              }}>
              <CountryFlag code={c.code} emoji={c.flag} size={14} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: selectedCountry === c.name ? colors.primaryText : colors.text }}>{c.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        {selectedCountry && (
          <>
            <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.interview.fields.selectVisaType', 'Select Visa Type')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
              {(countries.find(c => c.name === selectedCountry)?.visa_types || []).map((vt: string) => (
                <TouchableOpacity key={vt} accessibilityLabel="Set selected visa in travel visa interview sim button"
                  onPress={() => setSelectedVisa(vt)}
                  style={{
                    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8,
                    backgroundColor: selectedVisa === vt ? colors.primary : colors.surfaceHover,
                    borderWidth: 1, borderColor: selectedVisa === vt ? colors.primary : colors.border,
                    ...WEB_TRANSITION,
                  }}>
                  <Text style={{ fontSize: 12, fontWeight: '500', color: selectedVisa === vt ? colors.primaryText : colors.text }}>{vt}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}
        <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.interview.fields.difficulty', 'Difficulty')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 18 }}>
          {['easy', 'medium', 'hard'].map(d => (
            <TouchableOpacity key={d} data-testid={`tv-sim-difficulty-${d}`}
              onPress={() => setDifficulty(d)}
              style={{
                flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
                backgroundColor: difficulty === d ? colors.primary : colors.surfaceHover,
                borderWidth: 1, borderColor: difficulty === d ? colors.primary : colors.border,
                ...WEB_TRANSITION,
              }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: difficulty === d ? colors.primaryText : colors.text, textTransform: 'capitalize' }}>{d}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity data-testid="tv-sim-start-btn"
          onPress={startInterview}
          disabled={!selectedCountry || !selectedVisa || loading}
          style={{
            paddingVertical: 13, borderRadius: 10, backgroundColor: colors.primary, alignItems: 'center',
            opacity: !selectedCountry || !selectedVisa ? 0.5 : 1,
          }}>
          {loading ? <ActivityIndicator size="small" color={colors.primaryText} /> :
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{tx('travelVisa.interview.actions.beginInterview', 'Begin Interview')}</Text>}
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View data-testid="tv-interview-session" style={{
      borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
      overflow: 'hidden',
    }}>
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14,
        borderBottomWidth: 1, borderBottomColor: colors.border,
      }}>
        <Ionicons name="videocam" size={18} color={colors.primary} />
        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, flex: 1 }}>
          {selectedCountry} - {selectedVisa}
        </Text>
        <View style={{
          paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
          backgroundColor: isComplete ? colors.successSoft : colors.primarySoft,
        }}>
          <Text style={{ fontSize: 11, fontWeight: '600', color: isComplete ? colors.successText : colors.primary }}>
            {isComplete ? tx('travelVisa.interview.states.complete', 'Complete') : `${tx('travelVisa.interview.labels.questionPrefix', 'Q')} ${Math.min(currentQ, totalQ)}/${totalQ}`}
          </Text>
        </View>
      </View>
      <ScrollView ref={scrollRef} style={{ maxHeight: 400, padding: 14 }} contentContainerStyle={{ gap: 10 }}>
        {messages.map((msg, i) => (
          <View key={i} style={{
            alignSelf: msg.role === 'applicant' ? 'flex-end' : 'flex-start',
            maxWidth: '85%', padding: 12, borderRadius: 12,
            backgroundColor: msg.role === 'applicant' ? colors.primary :
              msg.role === 'system' ? colors.errorSoft : colors.surfaceHover,
          }}>
            <Text style={{ fontSize: 10, fontWeight: '600', color: msg.role === 'applicant' ? colors.primaryText + '80' : colors.textMuted, marginBottom: 4, textTransform: 'uppercase' }}>
              {msg.role === 'applicant' ? tx('travelVisa.interview.chat.you', 'You') : msg.role === 'interviewer' ? tx('travelVisa.interview.chat.officer', 'Officer') : tx('travelVisa.interview.chat.system', 'System')}
            </Text>
            <Text style={{ fontSize: 13, lineHeight: 20, color: msg.role === 'applicant' ? colors.primaryText : colors.text }}>{msg.content}</Text>
          </View>
        ))}
        {loading && <ActivityIndicator size="small" color={colors.primary} style={{ padding: 12 }} />}
      </ScrollView>
      {!isComplete && (
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12,
          borderTopWidth: 1, borderTopColor: colors.border,
        }}>
          <View style={{
            flex: 1, height: 40, borderRadius: 10, paddingHorizontal: 14,
            backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder,
            justifyContent: 'center',
          }}>
            {Platform.OS === 'web' ? (
              <input data-testid="tv-sim-answer-input"
                type="text" value={answerText}
                onChange={(e: any) => setAnswerText(e.target.value)}
                onKeyDown={(e: any) => { if (e.key === 'Enter') submitAnswer(); }}
                placeholder={tx('travelVisa.interview.fields.answerPlaceholder', 'Type your answer...')}
                style={{
                  border: 'none', outline: 'none', backgroundColor: 'transparent',
                  fontSize: 13, color: colors.inputText, width: '100%',
                } as any}
              />
            ) : null}
          </View>
          <TouchableOpacity data-testid="tv-sim-submit-btn" onPress={submitAnswer} disabled={loading || !answerText.trim()}
            style={{
              width: 40, height: 40, borderRadius: 10, backgroundColor: colors.primary,
              alignItems: 'center', justifyContent: 'center', opacity: loading || !answerText.trim() ? 0.5 : 1,
            }}>
            <Ionicons name="send" size={16} color={colors.primaryText} />
          </TouchableOpacity>
        </View>
      )}
      {isComplete && (
        <TouchableOpacity data-testid="tv-sim-restart-btn"
          onPress={() => { setSessionId(null); setMessages([]); setIsComplete(false); setCurrentQ(0); }}
          style={{ padding: 14, alignItems: 'center', borderTopWidth: 1, borderTopColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primary }}>{tx('travelVisa.interview.actions.startNew', 'Start New Interview')}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}
