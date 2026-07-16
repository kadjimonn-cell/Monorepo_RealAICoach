import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity } from 'react-native';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, ScoreBar, scoreColor } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; }

export function MockInterviewTab({ C }: Props) {
  const [mockSession, setMockSession] = useState<any>(null);
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [mockAnswer, setMockAnswer] = useState('');
  const [mockEvaluation, setMockEvaluation] = useState<any>(null);
  const [mockReport, setMockReport] = useState<any>(null);
  const [mockConfig, setMockConfig] = useState({ job_title: 'Software Engineer', mode: 'mixed', difficulty: 'medium' });
  const [aiLoading, setAiLoading] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: histData, refetch: _refetchHist } = useLiveQuery('/career-tools/mock-interview/history', { entity: 'mock_interview', pollInterval: 60000 });
  const mockHistory = histData?.sessions || [];

  const startMockInterview = async () => {
    setAiLoading(true); setMockReport(null); setCurrentQuestion(0); setMockAnswer(''); setMockEvaluation(null);
    try { const res = await api.post('/career-tools/mock-interview/start', mockConfig); setMockSession(res.data?.session || null); } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/MockInterviewTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAiLoading(false);
  };

  const submitMockAnswer = async () => {
    if (!mockSession || !mockAnswer.trim()) return;
    const questions = mockSession.plan?.questions || [];
    const q = questions[currentQuestion];
    if (!q) return;
    setAiLoading(true);
    try {
      const res = await api.post(`/career-tools/mock-interview/${mockSession.session_id}/answer`, { question_id: q.id, answer: mockAnswer });
      setMockEvaluation(res.data?.evaluation || null);
      if (res.data?.is_complete) {
        const rpt = await api.post(`/career-tools/mock-interview/${mockSession.session_id}/finish`);
        setMockReport(rpt.data?.report || null);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/MockInterviewTab.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAiLoading(false);
  };

  const nextMockQuestion = () => { setCurrentQuestion(prev => prev + 1); setMockAnswer(''); setMockEvaluation(null); };

  if (!mockSession) return (
    <View data-testid="mock-interview-tab" testID="mock-interview-tab">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>AI Mock Interview</Text>
        <TextInput data-testid="mock-job-title" testID="mock-job-title" placeholder="Job title" placeholderTextColor={C.muted}
          value={mockConfig.job_title} onChangeText={v => setMockConfig(p => ({ ...p, job_title: v }))}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
          {['mixed', 'behavioral', 'technical'].map(m => (
            <TouchableOpacity key={m} data-testid={`mock-mode-${m}`} testID={`mock-mode-${m}`} onPress={() => setMockConfig(p => ({ ...p, mode: m }))}
              style={{ flex: 1, padding: 10, borderRadius: 8, alignItems: 'center', backgroundColor: mockConfig.mode === m ? C.accent : C.bgSoft, borderWidth: 1, borderColor: mockConfig.mode === m ? C.accent : C.border }}>
              <Text style={{ color: mockConfig.mode === m ? 'var(--app-primary-text)' : C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{m}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
          {['easy', 'medium', 'hard'].map(d => (
            <TouchableOpacity key={d} data-testid={`mock-diff-${d}`} testID={`mock-diff-${d}`} onPress={() => setMockConfig(p => ({ ...p, difficulty: d }))}
              style={{ flex: 1, padding: 10, borderRadius: 8, alignItems: 'center', backgroundColor: mockConfig.difficulty === d ? C.primary : C.bgSoft, borderWidth: 1, borderColor: mockConfig.difficulty === d ? C.primary : C.border }}>
              <Text style={{ color: mockConfig.difficulty === d ? 'var(--app-primary-text)' : C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{d}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity data-testid="start-mock-btn" testID="start-mock-btn" onPress={startMockInterview} disabled={aiLoading}
          style={{ padding: 14, borderRadius: 12, backgroundColor: C.accent, alignItems: 'center' }}>
          <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>{aiLoading ? 'Setting up...' : 'Start Mock Interview'}</Text>
        </TouchableOpacity>
      </View>
      {mockHistory.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Previous Sessions</Text>
          {mockHistory.map((s) => (
            <View key={s.session_id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <View>
                <Text style={{ color: C.text, fontSize: 13 }}>{s.job_title} ({s.mode})</Text>
                <Text style={{ color: C.muted, fontSize: 11 }}>{s.created_at?.slice(0, 10)}</Text>
              </View>
              <Badge label={s.status} color={s.status === 'completed' ? C.success : C.warning} bg={(s.status === 'completed' ? C.success : C.warning) + '22'} />
            </View>
          ))}
        </View>
      )}
    </View>
  );

  if (mockReport) return (
    <View data-testid="mock-report" testID="mock-report">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.accent, alignItems: 'center' }}>
        <Text style={{ color: scoreColor(mockReport.overall_score || 0, C), fontSize: 48, fontWeight: '700' }}>{mockReport.overall_score || 0}</Text>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '600' }}>Overall Score - Grade: {mockReport.grade}</Text>
        <Badge label={mockReport.interview_readiness || 'unknown'} color={mockReport.interview_readiness === 'ready' ? C.success : C.warning}
          bg={(mockReport.interview_readiness === 'ready' ? C.success : C.warning) + '22'} />
      </View>
      {mockReport.detailed_feedback && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 13 }}>{mockReport.detailed_feedback}</Text>
        </View>
      )}
      {mockReport.top_strengths?.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.successText, fontSize: 14, fontWeight: '600', marginBottom: 8 }}>Strengths</Text>
          {mockReport.top_strengths.map((s: string, i: number) => <Text key={i} style={{ color: C.text, fontSize: 12, marginBottom: 4 }}>+ {s}</Text>)}
        </View>
      )}
      {mockReport.areas_to_improve?.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.warningText, fontSize: 14, fontWeight: '600', marginBottom: 8 }}>Areas to Improve</Text>
          {mockReport.areas_to_improve.map((s: string, i: number) => <Text key={i} style={{ color: C.text, fontSize: 12, marginBottom: 4 }}>- {s}</Text>)}
        </View>
      )}
      <TouchableOpacity data-testid="new-mock-btn" testID="new-mock-btn" onPress={() => { setMockSession(null); setMockReport(null); }}
        style={{ padding: 14, borderRadius: 12, backgroundColor: C.accent, alignItems: 'center' }}>
        <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>Start New Session</Text>
      </TouchableOpacity>
    </View>
  );

  const questions = mockSession.plan?.questions || [];
  const q = questions[currentQuestion];

  return (
    <View data-testid="mock-in-progress" testID="mock-in-progress">
      {!q ? <Text style={{ color: C.muted }}>No more questions</Text> : (
        <View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 }}>
            <Text style={{ color: C.muted, fontSize: 13 }}>Question {currentQuestion + 1} of {questions.length}</Text>
            <Badge label={q.type || 'general'} color={C.accent} bg={C.accent + '22'} />
          </View>
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.accent }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', lineHeight: 22 }}>{q.question}</Text>
          </View>
          <TextInput data-testid="mock-answer-input" testID="mock-answer-input" placeholder="Type your answer..." placeholderTextColor={C.muted}
            value={mockAnswer} onChangeText={setMockAnswer} multiline numberOfLines={4}
            style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, minHeight: 120, color: C.text, textAlignVertical: 'top', borderWidth: 1, borderColor: C.border, marginBottom: 12 }} />
          {!mockEvaluation ? (
            <TouchableOpacity data-testid="submit-mock-answer" testID="submit-mock-answer" onPress={submitMockAnswer} disabled={aiLoading || !mockAnswer.trim()}
              style={{ padding: 14, borderRadius: 12, backgroundColor: !mockAnswer.trim() ? C.border : C.accent, alignItems: 'center' }}>
              <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>{aiLoading ? 'AI Evaluating...' : 'Submit Answer'}</Text>
            </TouchableOpacity>
          ) : (
            <View>
              <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.success }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>AI Evaluation</Text>
                  <Text style={{ color: scoreColor(mockEvaluation.score || 0, C), fontSize: 18, fontWeight: '700' }}>{mockEvaluation.score}%</Text>
                </View>
                <ScoreBar C={C} score={mockEvaluation.clarity || 0} label="Clarity" color={C.primary} />
                <ScoreBar C={C} score={mockEvaluation.relevance || 0} label="Relevance" color={C.accent} />
                <ScoreBar C={C} score={mockEvaluation.depth || 0} label="Depth" color={C.successText} />
                {mockEvaluation.feedback && <Text style={{ color: C.muted, fontSize: 12, marginTop: 6 }}>{mockEvaluation.feedback}</Text>}
                {mockEvaluation.improvement_tip && (
                  <View style={{ marginTop: 8, padding: 8, backgroundColor: (globalThis as any).__alphaColor(C.warning, '15'), borderRadius: 8 }}>
                    <Text style={{ color: C.warningText, fontSize: 12, fontWeight: '600' }}>Tip: {mockEvaluation.improvement_tip}</Text>
                  </View>
                )}
              </View>
              <TouchableOpacity data-testid="next-mock-question" testID="next-mock-question" onPress={currentQuestion < questions.length - 1 ? nextMockQuestion : async () => {
                setAiLoading(true);
                const rpt = await api.post(`/career-tools/mock-interview/${mockSession.session_id}/finish`);
                setMockReport(rpt.data?.report || null);
                setAiLoading(false);
              }}
                style={{ padding: 14, borderRadius: 12, backgroundColor: C.accent, alignItems: 'center' }}>
                <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>
                  {currentQuestion < questions.length - 1 ? 'Next Question' : aiLoading ? 'Generating Report...' : 'Finish & Get Report'}
                </Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
