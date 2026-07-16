import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Props = {
  C: any;
  interviewId: string;
  interviewStatus: string;
  onClose: () => void;
};

export const InterviewSummaryModal = ({ C, interviewId, interviewStatus, onClose }: Props) => {
  const [generating, setGenerating] = useState(false);
  const [generatingPerf, setGeneratingPerf] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingContentPdf, setDownloadingContentPdf] = useState(false);
  const [emailingAdmin, setEmailingAdmin] = useState(false);
  const [emailingSuite, setEmailingSuite] = useState(false);
  const [actionMsg, setActionMsg] = useState('');

  const { data: summaryRaw, loading, refetch: loadSummary } = useLiveQuery(
    interviewId ? `/interview-summary/${interviewId}` : '',
    { entity: 'interviews', pollInterval: 60000, deps: [interviewId] }
  );
  const summary = summaryRaw?.summary || null;
  const { data: perfRaw, loading: perfLoading, refetch: loadPerformance } = useLiveQuery(
    interviewId ? `/interview-performance/${interviewId}` : '',
    { entity: 'interviews', pollInterval: 60000, deps: [interviewId] }
  );
  const performance = perfRaw?.report || null;

  const generateSummary = async () => {
    setGenerating(true);
    try {
      await api.post(`/interview-summary/${interviewId}/generate`);
      await loadSummary();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/InterviewSummary.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setGenerating(false);
  };

  const generatePerformance = async () => {
    setGeneratingPerf(true);
    try {
      await api.post(`/interview-performance/${interviewId}/analyze`);
      await loadPerformance();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/InterviewSummary.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setGeneratingPerf(false);
  };

  const downloadPerformancePdf = async () => {
    setDownloadingPdf(true);
    setActionMsg('');
    try {
      const res = await api.get(`/interview-performance/${interviewId}/export/pdf`, { responseType: 'blob' as any });
      if (typeof window !== 'undefined') {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pdf-v15-for-attachment-interview-performance_${interviewId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
      setActionMsg('PDF downloaded (v1.4 policy enforced).');
    } catch {
      setActionMsg('Unable to download PDF right now.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const downloadInterviewContentPdf = async () => {
    setDownloadingContentPdf(true);
    setActionMsg('');
    try {
      const res = await api.get(`/interview-content/${interviewId}/export/pdf`, { responseType: 'blob' as any });
      if (typeof window !== 'undefined') {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pdf-v15-for-attachment-interview-content_${interviewId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
      setActionMsg('Interview content PDF downloaded.');
    } catch {
      setActionMsg('Unable to download interview content PDF right now.');
    } finally {
      setDownloadingContentPdf(false);
    }
  };

  const emailAdminVerification = async () => {
    setEmailingAdmin(true);
    setActionMsg('');
    try {
      const res = await api.post(`/interview-performance/${interviewId}/email-admin-verification`, {});
      setActionMsg(`Admin verification email sent to ${res.data?.sent_count || 0} recipient(s).`);
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || 'Unable to send admin verification email.');
    } finally {
      setEmailingAdmin(false);
    }
  };

  const emailPdfSuite = async () => {
    setEmailingSuite(true);
    setActionMsg('');
    try {
      const res = await api.post('/admin/pdf-v15/email-verification-suite', {});
      setActionMsg(`Full PDF verification suite sent to ${res.data?.sent_count || 0} admin recipient(s).`);
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || 'Unable to send full PDF suite.');
    } finally {
      setEmailingSuite(false);
    }
  };

  const recColor = (r: string) => {
    const map: Record<string, string> = { strong_hire: C.successText, hire: C.primary, maybe: C.warning, pass: C.error };
    return map[r] || C.muted;
  };

  return (
    <View data-testid="interview-summary-modal" testID="interview-summary-modal" style={{
      backgroundColor: C.card, borderRadius: 16, padding: 20,
      borderWidth: 1, borderColor: C.border, maxWidth: 600,
    }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>AI Interview Summary</Text>
        <TouchableOpacity onPress={onClose} accessibilityLabel="close button">
          <Ionicons name="close" size={22} color={C.muted} />
        </TouchableOpacity>
      </View>

      {loading && (
        <View style={{ alignItems: 'center', paddingVertical: 20 }}>
          <ActivityIndicator size="large" color={C.accent} />
        </View>
      )}

      {!loading && !summary && (
        <View style={{ alignItems: 'center', paddingVertical: 20 }}>
          <Ionicons name="document-text-outline" size={40} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 14, marginTop: 8, textAlign: 'center' }}>
            No summary generated yet
          </Text>
          <TouchableOpacity data-testid="generate-summary-btn" testID="generate-summary-btn" onPress={generateSummary}
            disabled={generating}
            style={{
              marginTop: 16, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12,
              backgroundColor: C.accent, flexDirection: 'row', alignItems: 'center', gap: 8,
            }}>
            <Ionicons name="sparkles" size={16} color={C.primaryText} />
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>
              {generating ? 'Generating...' : 'Generate AI Summary'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="generate-performance-btn" testID="generate-performance-btn" onPress={generatePerformance}
            disabled={generatingPerf}
            style={{
              marginTop: 10, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12,
              backgroundColor: C.primary, flexDirection: 'row', alignItems: 'center', gap: 8,
            }}>
            <Ionicons name="analytics" size={16} color={C.primaryText} />
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>
              {generatingPerf ? 'Analyzing...' : 'Generate Performance Analytics'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {summary && (
        <View>
          {/* Executive Summary */}
          <View style={{ marginBottom: 12 }}>
            <Text style={{ color: C.text, fontSize: 14, lineHeight: 20 }}>{summary.executive_summary}</Text>
          </View>

          {/* Recommendation Badge */}
          {summary.hiring_recommendation && (
            <View style={{
              flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12,
              padding: 10, borderRadius: 10,
              backgroundColor: (globalThis as any).__alphaColor(recColor(summary.hiring_recommendation), '15'),
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(recColor(summary.hiring_recommendation), '33'),
            }}>
              <Text style={{
                color: recColor(summary.hiring_recommendation),
                fontSize: 13, fontWeight: '700', textTransform: 'uppercase',
              }}>{summary.hiring_recommendation.replace('_', ' ')}</Text>
              {summary.confidence_level && (
                <Text style={{ color: C.muted, fontSize: 11 }}>({summary.confidence_level}% confidence)</Text>
              )}
            </View>
          )}

          {/* Key Points */}
          {(summary.key_discussion_points || []).length > 0 && (
            <Section title="Key Discussion Points" C={C}>
              {summary.key_discussion_points.map((p: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', gap: 6, marginBottom: 4 }}>
                  <Text style={{ color: C.accent }}>-</Text>
                  <Text style={{ color: C.text, fontSize: 12, flex: 1 }}>{p}</Text>
                </View>
              ))}
            </Section>
          )}

          {/* Strengths & Weaknesses */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 10 }}>
            {(summary.candidate_strengths || []).length > 0 && (
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.successText, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>Strengths</Text>
                {summary.candidate_strengths.map((s: string, i: number) => (
                  <Text key={i} style={{ color: C.muted, fontSize: 11, marginBottom: 2 }}>+ {s}</Text>
                ))}
              </View>
            )}
            {(summary.candidate_weaknesses || []).length > 0 && (
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.warning, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>Areas to Improve</Text>
                {summary.candidate_weaknesses.map((w: string, i: number) => (
                  <Text key={i} style={{ color: C.muted, fontSize: 11, marginBottom: 2 }}>- {w}</Text>
                ))}
              </View>
            )}
          </View>

          {/* Next Steps */}
          {(summary.next_steps || []).length > 0 && (
            <Section title="Next Steps" C={C}>
              {summary.next_steps.map((s: string, i: number) => (
                <Text key={i} style={{ color: C.text, fontSize: 12, marginBottom: 2 }}>{i + 1}. {s}</Text>
              ))}
            </Section>
          )}

          {/* Meta */}
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 8 }}>
            {summary.duration_seconds && (
              <Text style={{ color: C.muted, fontSize: 10 }}>
                Duration: {Math.round(summary.duration_seconds / 60)}min
              </Text>
            )}
            {summary.chat_message_count > 0 && (
              <Text style={{ color: C.muted, fontSize: 10 }}>{summary.chat_message_count} chat messages</Text>
            )}
            <Text style={{ color: C.muted, fontSize: 10 }}>{summary.generated_at?.slice(0, 16)}</Text>
          </View>
        </View>
      )}

      <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border }} data-testid="interview-performance-block" testID="interview-performance-block">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>Performance & Behavioral Analytics</Text>
          <TouchableOpacity onPress={generatePerformance} disabled={generatingPerf} data-testid="refresh-performance-btn" testID="refresh-performance-btn">
            <Ionicons name="refresh" size={18} color={C.accent} />
          </TouchableOpacity>
        </View>
        {perfLoading && <ActivityIndicator size="small" color={C.accent} />}
        {!perfLoading && !performance && (
          <Text style={{ color: C.muted, fontSize: 12 }}>No performance report yet. Generate one after interview completion.</Text>
        )}
        {performance && (
          <View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              {[['Communication', performance.communication_score], ['Confidence', performance.confidence_score], ['Relevance', performance.relevance_score], ['Overall', performance.overall_score]].map(([label, value]) => (
                <View key={String(label)} style={{ width: '48%', borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 8, padding: 8 }}>
                  <Text style={{ color: C.muted, fontSize: 10 }}>{label}</Text>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{value as number}</Text>
                </View>
              ))}
            </View>
            <Text style={{ color: C.text, fontSize: 12 }}>Recommendation: <Text style={{ fontWeight: '700' }}>{String(performance.hiring_recommendation || '').replace('_', ' ')}</Text></Text>
            {(performance.behavioral_insights || []).map((insight: string, i: number) => (
              <Text key={i} style={{ color: C.muted, fontSize: 11, marginTop: 3 }}>• {insight}</Text>
            ))}

            <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
              <TouchableOpacity onPress={downloadPerformancePdf} disabled={downloadingPdf}
                style={{ flex: 1, backgroundColor: C.primary, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: downloadingPdf ? 0.7 : 1 }}
                data-testid="download-performance-pdf-btn" testID="download-performance-pdf-btn">
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{downloadingPdf ? 'Preparing...' : 'Download PDF Summary'}</Text>
              </TouchableOpacity>

              <TouchableOpacity onPress={downloadInterviewContentPdf} disabled={downloadingContentPdf}
                style={{ flex: 1, backgroundColor: C.warning, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: downloadingContentPdf ? 0.7 : 1 }}
                data-testid="download-interview-content-pdf-btn" testID="download-interview-content-pdf-btn">
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{downloadingContentPdf ? 'Preparing...' : 'Download Content PDF'}</Text>
              </TouchableOpacity>

              <TouchableOpacity onPress={emailAdminVerification} disabled={emailingAdmin}
                style={{ flex: 1, backgroundColor: C.success, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: emailingAdmin ? 0.7 : 1 }}
                data-testid="email-admin-verification-btn" testID="email-admin-verification-btn">
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{emailingAdmin ? 'Sending...' : 'Email Admin Verification'}</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity onPress={emailPdfSuite} disabled={emailingSuite}
              style={{ marginTop: 8, backgroundColor: C.accent, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: emailingSuite ? 0.7 : 1 }}
              data-testid="email-full-pdf-v15-suite-btn" testID="email-full-pdf-v15-suite-btn">
              <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{emailingSuite ? 'Sending...' : 'Email Full PDF Suite'}</Text>
            </TouchableOpacity>
            {!!actionMsg && <Text style={{ color: C.muted, fontSize: 11, marginTop: 8 }}>{actionMsg}</Text>}
          </View>
        )}
      </View>
    </View>
  );
};

const Section = ({ title, C, children }: { title: string; C: any; children: React.ReactNode }) => (
  <View style={{ marginBottom: 10 }}>
    <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 4 }}>{title}</Text>
    {children}
  </View>
);

// Candidate Experience Rating Form
export const CandidateExperienceForm = ({ C, interviewId, onClose }: { C: any; interviewId: string; onClose: () => void }) => {
  const [form, setForm] = useState({
    overall_rating: 4, communication_rating: 4, professionalism_rating: 4,
    timeliness_rating: 4, feedback_quality_rating: 4, would_recommend: true, comment: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.post(`/candidate-experience/${interviewId}/rate`, form);
      setSubmitted(true);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/InterviewSummary.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSubmitting(false);
  };

  if (submitted) {
    return (
      <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
        <Ionicons name="checkmark-circle" size={40} color={C.successText} />
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginTop: 8 }}>Thanks for your feedback!</Text>
        <TouchableOpacity onPress={onClose} accessibilityLabel="Close"
          style={{ marginTop: 12, paddingHorizontal: 20, paddingVertical: 8, borderRadius: 8, backgroundColor: C.accent }}>
          <Text style={{ color: C.primaryText, fontSize: 13 }}>Close</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const StarRow = ({ label, value, key: k }: { label: string; value: number; key: string }) => (
    <View style={{ marginBottom: 10 }}>
      <Text style={{ color: C.text, fontSize: 12, marginBottom: 4 }}>{label}</Text>
      <View style={{ flexDirection: 'row', gap: 4 }}>
        {[1, 2, 3, 4, 5].map(star => (
          <TouchableOpacity key={star} data-testid={`rate-${k}-${star}`} testID={`rate-${k}-${star}`}
            onPress={() => setForm(f => ({ ...f, [k]: star }))}>
            <Ionicons
              name={star <= value ? 'star' : 'star-outline'}
              size={24}
              color={star <= value ? C.warning : C.muted}
            />
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  return (
    <View data-testid="candidate-experience-form" testID="candidate-experience-form" style={{
      backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, maxWidth: 500,
    }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>Rate Your Experience</Text>
        <TouchableOpacity onPress={onClose}  accessibilityLabel="close button"><Ionicons name="close" size={22} color={C.muted} /></TouchableOpacity>
      </View>

      <StarRow label="Overall Experience" value={form.overall_rating} key="overall_rating" />
      <StarRow label="Communication" value={form.communication_rating} key="communication_rating" />
      <StarRow label="Professionalism" value={form.professionalism_rating} key="professionalism_rating" />
      <StarRow label="Timeliness" value={form.timeliness_rating} key="timeliness_rating" />
      <StarRow label="Feedback Quality" value={form.feedback_quality_rating} key="feedback_quality_rating" />

      <TextInput data-testid="cx-comment" testID="cx-comment"
        placeholder="Any additional comments? (optional)"
        placeholderTextColor={C.muted}
        multiline
        value={form.comment}
        onChangeText={v => setForm(f => ({ ...f, comment: v }))}
        style={{
          backgroundColor: C.bg, borderRadius: 8, padding: 12, marginBottom: 12,
          color: C.text, minHeight: 60, borderWidth: 1, borderColor: C.border,
        }}
      />

      <TouchableOpacity data-testid="submit-cx-rating" testID="submit-cx-rating" onPress={submit}
        disabled={submitting}
        style={{
          padding: 14, borderRadius: 12, backgroundColor: C.accent,
          alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
        }}>
        <Ionicons name="send" size={16} color={C.primaryText} />
        <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>
          {submitting ? 'Submitting...' : 'Submit Rating'}
        </Text>
      </TouchableOpacity>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
