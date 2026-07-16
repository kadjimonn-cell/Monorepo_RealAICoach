import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AppShell from './AppShell';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const ACCENTS = { primary: 'var(--app-primary)', accent: 'var(--app-primary)', success: 'var(--app-success)', error: 'var(--app-error)', warning: 'var(--app-warning)' };

export function MockInterviewContent() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const C = { bg: colors.bg, card: colors.card, text: colors.text, muted: colors.textMuted, border: colors.border, ...ACCENTS };
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const scrollRef = useRef<ScrollView>(null);

  const [view, setView] = useState<'home' | 'interview'>('home');
  const [personas, setPersonas] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPersona, setSelectedPersona] = useState('');
  const [jobRole, setJobRole] = useState('Software Engineer');
  const [starting, setStarting] = useState(false);

  // Interview state
  const [session, setSession] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [answer, setAnswer] = useState('');
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [report, setReport] = useState<any>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Personas don't require auth
      const pRes = await api.get('/mock-interview/personas');
      setPersonas(pRes.data.personas || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    try {
      // Sessions require auth
      if (user) {
        const sRes = await api.get('/mock-interview/sessions');
        setSessions(sRes.data.sessions || []);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setLoading(false);
  }, [user]);

  useEffect(() => { loadData(); }, [loadData]);

  const startInterview = async () => {
    if (!selectedPersona) return;
    setStarting(true);
    try {
      const res = await api.post('/mock-interview/start', {
        persona: selectedPersona,
        job_role: jobRole.trim() || 'Software Engineer',
      });
      if (res.data?.session) {
        setSession(res.data.session);
        setMessages(res.data.session.messages || []);
        setView('interview');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setStarting(false);
  };

  const sendAnswer = async () => {
    if (!answer.trim() || !session) return;
    const myAnswer = answer.trim();
    setAnswer('');
    setSending(true);

    // Optimistically add candidate message
    const now = new Date().toISOString();
    setMessages(prev => [...prev, { role: 'candidate', content: myAnswer, timestamp: now }]);

    try {
      const res = await api.post(`/mock-interview/${session.session_id}/answer`, {
        answer: myAnswer,
      });
      if (res.data?.response) {
        setMessages(prev => [...prev, {
          role: 'interviewer', content: res.data.response,
          timestamp: new Date().toISOString(), rating: res.data.rating, score: res.data.score,
        }]);
        setSession((s: any) => ({ ...s, question_count: res.data.question_count }));
      }
    } catch {
      setMessages(prev => [...prev, {
        role: 'interviewer', content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString(),
      }]);
    }
    setSending(false);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 200);
  };

  const endInterview = async () => {
    if (!session) return;
    setEnding(true);
    try {
      const res = await api.post(`/mock-interview/${session.session_id}/end`);
      if (res.data) {
        setMessages(prev => [...prev, {
          role: 'interviewer', content: res.data.final_feedback,
          timestamp: new Date().toISOString(), is_final: true,
        }]);
        setSession((s: any) => ({
          ...s, status: 'completed',
          average_score: res.data.average_score,
          final_feedback: res.data.final_feedback,
        }));
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setEnding(false);
  };

  const resumeSession = async (sid: string) => {
    try {
      const res = await api.get(`/mock-interview/${sid}`);
      if (res.data) {
        setSession(res.data);
        setMessages(res.data.messages || []);
        setView('interview');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const deleteSession = async (sid: string) => {
    try {
      await api.delete(`/mock-interview/${sid}`);
      loadData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const backToHome = () => {
    setSession(null);
    setMessages([]);
    setReport(null);
    setView('home');
    loadData();
  };

  const generateReport = async () => {
    if (!session) return;
    setGeneratingReport(true);
    try {
      const res = await api.post(`/mock-interview/${session.session_id}/report`);
      if (res.data?.report) setReport(res.data.report);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/MockInterviewContent.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setGeneratingReport(false);
  };

  const downloadReport = () => {
    if (!session) return;
    const backendUrl = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.REACT_APP_BACKEND_URL || '');
    const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') || '' : '';
    window.open(`${backendUrl}/api/mock-interview/${session.session_id}/report/download?token=${token}`, '_blank');
  };

  const getRatingColor = (r: string) => {
    if (r === 'Excellent') return C.success;
    if (r === 'Needs Improvement') return C.warning;
    return C.primary;
  };

  // ── HOME VIEW ──
  if (view === 'home') {
    return (
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 100, backgroundColor: colors.bg }} data-testid="mock-interview-page" testID="mock-interview-page">
          <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }} data-testid="mock-interview-title" testID="mock-interview-title">
            Mock Interview Simulator
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4, marginBottom: 24 }}>
            Practice with AI interviewers and get instant feedback
          </Text>

          {/* Start New Interview */}
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 20, marginBottom: 24, borderWidth: 1, borderColor: colors.border }} data-testid="start-interview-section" testID="start-interview-section">
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700', marginBottom: 14 }}>Choose Your Interviewer</Text>

            {loading ? <ActivityIndicator color={C.primary} /> : (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
                {personas.map(p => (
                  <TouchableOpacity key={p.id} onPress={() => setSelectedPersona(p.id)} data-testid={`persona-${p.id}`} testID={`persona-${p.id}`}
                    style={{
                      flex: isWide ? undefined : 1, minWidth: isWide ? 180 : '45%',
                      padding: 14, borderRadius: 12,
                      backgroundColor: selectedPersona === p.id ? (globalThis as any).__alphaColor(p.color, '15') : colors.bg,
                      borderWidth: 2, borderColor: selectedPersona === p.id ? p.color : colors.border,
                    }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(p.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={p.icon as any} size={16} color={p.color} />
                      </View>
                      <View>
                        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{p.name}</Text>
                        <Text style={{ color: p.color, fontSize: 10, fontWeight: '600' }}>{p.role}</Text>
                      </View>
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            <Text style={{ color: C.muted, fontSize: 11, marginBottom: 6 }}>Target Role</Text>
            <TextInput value={jobRole} onChangeText={setJobRole} data-testid="job-role-input" testID="job-role-input"
              placeholder="e.g., Senior Software Engineer"
              placeholderTextColor={C.muted}
              style={{
                backgroundColor: C.bg, color: C.text, borderRadius: 10, padding: 12, fontSize: 14,
                borderWidth: 1, borderColor: C.border, marginBottom: 14,
              }} />

            <TouchableOpacity onPress={startInterview} disabled={!selectedPersona || starting} data-testid="start-interview-btn" testID="start-interview-btn"
              style={{
                backgroundColor: selectedPersona ? C.primary : C.border,
                borderRadius: 10, paddingVertical: 14, alignItems: 'center',
                flexDirection: 'row', justifyContent: 'center', gap: 8,
              }}>
              {starting ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="play" size={18} color="var(--app-primary-text)" />}
              <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '700' }}>
                {starting ? 'Starting Interview...' : 'Start Mock Interview'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Past Sessions */}
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>Past Sessions</Text>
          {sessions.length === 0 ? (
            <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 30, alignItems: 'center', borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="chatbubbles-outline" size={36} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>No interview sessions yet</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {sessions.map(s => (
                <TouchableOpacity key={s.session_id} onPress={() => resumeSession(s.session_id)} data-testid={`session-${s.session_id}`} testID={`session-${s.session_id}`}
                  style={{
                    backgroundColor: colors.card, borderRadius: 12, padding: 14,
                    borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center',
                  }}>
                  <View style={{
                    width: 36, height: 36, borderRadius: 9,
                    backgroundColor: (globalThis as any).__alphaColor((PERSONA_COLORS[s.persona_id] || C.primary), '15'),
                    alignItems: 'center', justifyContent: 'center', marginRight: 12,
                  }}>
                    <Ionicons name={s.status === 'completed' ? 'checkmark-circle' : 'time'} size={18}
                      color={s.status === 'completed' ? C.success : C.warning} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{s.persona_name} - {s.job_role}</Text>
                    <Text style={{ color: C.muted, fontSize: 10 }}>
                      {s.question_count} questions | {s.status === 'completed' ? `Score: ${s.average_score}/10` : 'In Progress'}
                      {' | '}{new Date(s.created_at).toLocaleDateString()}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={(e) => { e.stopPropagation(); deleteSession(s.session_id); }} data-testid={`delete-session-${s.session_id}`} testID={`delete-session-${s.session_id}`}>
                    <Ionicons name="trash-outline" size={16} color={C.error} />
                  </TouchableOpacity>
                </TouchableOpacity>
              ))}
            </View>
          )}
      </ScrollView>
    );
  }

  // -- INTERVIEW VIEW --
  const persona = personas.find(p => p.id === session?.persona_id);
  const isCompleted = session?.status === 'completed';

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="interview-session-page" testID="interview-session-page">
        {/* Header */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: 16, paddingVertical: 10, backgroundColor: colors.card,
          borderBottomWidth: 1, borderBottomColor: colors.border,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <TouchableOpacity onPress={backToHome} data-testid="back-to-home" testID="back-to-home">
              <Ionicons name="arrow-back" size={20} color={colors.text} />
            </TouchableOpacity>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((persona?.color || C.primary), '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={(persona?.icon || 'person') as any} size={16} color={persona?.color || C.primary} />
            </View>
            <View>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{session?.persona_name}</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>{session?.job_role} | Q{session?.question_count || 0}</Text>
            </View>
          </View>
          {!isCompleted && (
            <TouchableOpacity onPress={endInterview} disabled={ending} data-testid="end-interview-btn" testID="end-interview-btn"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.error, '20'), paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.error }}>
              {ending ? <ActivityIndicator size="small" color={C.error} /> : <Ionicons name="stop-circle" size={14} color={C.error} />}
              <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }}>End Interview</Text>
            </TouchableOpacity>
          )}
          {isCompleted && session?.average_score > 0 && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                <Text style={{ color: C.successText, fontSize: 12, fontWeight: '700' }}>Score: {session.average_score}/10</Text>
              </View>
              {!report ? (
                <TouchableOpacity onPress={generateReport} disabled={generatingReport} data-testid="generate-report-btn" testID="generate-report-btn"
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.accent, '20'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.accent }}>
                  {generatingReport ? <ActivityIndicator size="small" color={C.accent} /> : <Ionicons name="document-text" size={14} color={C.accent} />}
                  <Text style={{ color: C.accent, fontSize: 11, fontWeight: '700' }}>{generatingReport ? 'Generating...' : 'Generate Report'}</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity onPress={downloadReport} data-testid="download-report-btn" testID="download-report-btn"
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.primary, '20'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.primary }}>
                  <Ionicons name="download" size={14} color={C.primary} />
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>Download PDF</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>

        {/* Messages */}
        <ScrollView ref={scrollRef} style={{ flex: 1, padding: 16 }}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
          {messages.map((msg, i) => (
            <View key={i} style={{
              alignSelf: msg.role === 'candidate' ? 'flex-end' : 'flex-start',
              maxWidth: isWide ? '70%' : '85%', marginBottom: 12,
            }}>
              {msg.role === 'interviewer' && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                  <Text style={{ color: persona?.color || C.primary, fontSize: 10, fontWeight: '700' }}>{session?.persona_name}</Text>
                  {msg.rating && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(getRatingColor(msg.rating), '15'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                      <Text style={{ color: getRatingColor(msg.rating), fontSize: 9, fontWeight: '600' }}>{msg.rating}</Text>
                    </View>
                  )}
                  {msg.is_final && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                      <Text style={{ color: C.accent, fontSize: 9, fontWeight: '600' }}>FINAL FEEDBACK</Text>
                    </View>
                  )}
                </View>
              )}
              <View style={{
                backgroundColor: msg.role === 'candidate' ? (globalThis as any).__alphaColor(C.primary, '20') : colors.card,
                borderRadius: 14,
                borderTopLeftRadius: msg.role === 'interviewer' ? 4 : 14,
                borderTopRightRadius: msg.role === 'candidate' ? 4 : 14,
                padding: 14, borderWidth: 1,
                borderColor: msg.role === 'candidate' ? (globalThis as any).__alphaColor(C.primary, '30') : colors.border,
              }}>
                <Text style={{ color: colors.text, fontSize: 13, lineHeight: 20 }} selectable>{msg.content}</Text>
              </View>
              <Text style={{ color: C.muted, fontSize: 9, marginTop: 3, alignSelf: msg.role === 'candidate' ? 'flex-end' : 'flex-start' }}>
                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''}
              </Text>
            </View>
          ))}
          {sending && (
            <View style={{ alignSelf: 'flex-start', marginBottom: 12 }}>
              <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <ActivityIndicator size="small" color={persona?.color || C.primary} />
                <Text style={{ color: C.muted, fontSize: 12, fontStyle: 'italic' }}>Thinking...</Text>
              </View>
            </View>
          )}

          {/* Report Summary Card */}
          {report && (
            <View data-testid="report-summary-card" testID="report-summary-card" style={{
              backgroundColor: (globalThis as any).__alphaColor(C.accent, '08'), borderRadius: 16, padding: 18, marginTop: 8,
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '30'),
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Ionicons name="document-text" size={18} color={C.accent} />
                <Text style={{ color: C.accent, fontSize: 14, fontWeight: '800' }}>Interview Performance Report</Text>
              </View>

              {report.readiness && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, alignSelf: 'flex-start', marginBottom: 10 }}>
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>{report.readiness}</Text>
                </View>
              )}

              {report.executive_summary && (
                <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18, marginBottom: 12 }}>{report.executive_summary}</Text>
              )}

              {report.strengths?.length > 0 && (
                <View style={{ marginBottom: 10 }}>
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>Strengths</Text>
                  {report.strengths.map((s: string, i: number) => (
                    <Text key={i} style={{ color: colors.text, fontSize: 11, lineHeight: 16, marginLeft: 8 }}>- {s}</Text>
                  ))}
                </View>
              )}

              {report.improvements?.length > 0 && (
                <View style={{ marginBottom: 10 }}>
                  <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>Areas to Improve</Text>
                  {report.improvements.map((s: string, i: number) => (
                    <Text key={i} style={{ color: colors.text, fontSize: 11, lineHeight: 16, marginLeft: 8 }}>- {s}</Text>
                  ))}
                </View>
              )}

              {report.tips?.length > 0 && (
                <View style={{ marginBottom: 10 }}>
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>Actionable Tips</Text>
                  {report.tips.map((s: string, i: number) => (
                    <Text key={i} style={{ color: colors.text, fontSize: 11, lineHeight: 16, marginLeft: 8 }}>{i + 1}. {s}</Text>
                  ))}
                </View>
              )}

              <TouchableOpacity onPress={downloadReport} data-testid="report-download-btn" testID="report-download-btn"
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: C.primary, paddingVertical: 10, borderRadius: 10, marginTop: 6 }}>
                <Ionicons name="download" size={16} color="var(--app-primary-text)" />
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>Download Full PDF Report</Text>
              </TouchableOpacity>
            </View>
          )}

          <View style={{ height: 20 }} />
        </ScrollView>

        {/* Input Bar */}
        {!isCompleted && (
          <View style={{
            flexDirection: 'row', alignItems: 'flex-end', gap: 8,
            paddingHorizontal: 16, paddingVertical: 12,
            backgroundColor: colors.card, borderTopWidth: 1, borderTopColor: colors.border,
          }}>
            <TextInput
              value={answer} onChangeText={setAnswer} multiline
              data-testid="answer-input" testID="answer-input"
              placeholder="Type your answer..."
              placeholderTextColor={C.muted}
              style={{
                flex: 1, backgroundColor: colors.bg, color: colors.text,
                borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
                fontSize: 14, maxHeight: 120, borderWidth: 1, borderColor: colors.border,
              }}
              onSubmitEditing={sendAnswer}
            />
            <TouchableOpacity onPress={sendAnswer} disabled={!answer.trim() || sending} data-testid="send-answer-btn" testID="send-answer-btn"
              style={{
                width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center',
                backgroundColor: answer.trim() ? C.primary : C.border,
              }}>
              <Ionicons name="send" size={18} color="var(--app-primary-text)" />
            </TouchableOpacity>
          </View>
        )}
    </View>
  );
}

export default function MockInterviewPage() {
  return (
    <AppShell>
      <MockInterviewContent />
    </AppShell>
  );
}

const PERSONA_COLORS: Record<string, string> = {
  technical: 'var(--app-primary)', behavioral: 'var(--app-primary)', hr: 'var(--app-success)', case: 'var(--app-warning)', // @theme-ok brand/role/state identifier
};

/* i18n-probe t('i18n.auto.probe') */
