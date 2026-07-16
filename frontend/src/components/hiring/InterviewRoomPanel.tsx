import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { HColors } from './shared';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Props = {
  C: HColors;
  interviewId: string;
  onClose: () => void;
};

export const InterviewRoomPanel = ({ C, interviewId, onClose }: Props) => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [room, setRoom] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [aiContext, setAiContext] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [endingRoom, setEndingRoom] = useState(false);
  const [performance, setPerformance] = useState<any>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingContentPdf, setDownloadingContentPdf] = useState(false);
  const [emailingAdmin, setEmailingAdmin] = useState(false);
  const [emailingPdfSuite, setEmailingPdfSuite] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [micOn, setMicOn] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineEvents, setTimelineEvents] = useState<any[]>([]);
  const [timelineAnnotations, setTimelineAnnotations] = useState<any[]>([]);
  const [annotationSecond, setAnnotationSecond] = useState('0');
  const [annotationCategory, setAnnotationCategory] = useState('general');
  const [annotationSeverity, setAnnotationSeverity] = useState<'low' | 'medium' | 'high'>('low');
  const [annotationNote, setAnnotationNote] = useState('');
  const [addingAnnotation, setAddingAnnotation] = useState(false);

  const localVideoRef = useRef<any>(null);
  const localStreamRef = useRef<MediaStream | null>(null);

  const canUseMedia = useMemo(() => Platform.OS === 'web' && typeof navigator !== 'undefined', []);

  const loadReplayTimeline = useCallback(async (roomId: string) => {
    setTimelineLoading(true);
    try {
      const res = await api.get(`/interview-room/${roomId}/replay-timeline`);
      setTimelineEvents(res.data?.events || []);
      setTimelineAnnotations(res.data?.annotations || []);
    } catch {
      setTimelineEvents([]);
      setTimelineAnnotations([]);
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  const refreshRoom = useCallback(async (roomId: string) => {
    try {
      const res = await api.get(`/interview-room/${roomId}`);
      setRoom(res.data?.room || null);
      await loadReplayTimeline(roomId);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/InterviewRoomPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [loadReplayTimeline]);

  const loadPerformance = useCallback(async () => {
    try {
      const res = await api.get(`/interview-performance/${interviewId}`);
      setPerformance(res.data?.report || null);
    } catch {
      setPerformance(null);
    }
  }, [interviewId]);

  const initialize = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const createRes = await api.post('/interview-room/create', { interview_id: interviewId });
      const roomId = createRes.data?.room?.room_id;
      if (!roomId) throw new Error('Failed to create room');
      await api.post(`/interview-room/${roomId}/join`, {});
      await refreshRoom(roomId);
      await loadPerformance();

      if (canUseMedia) {
        const mediaDevices = (navigator as any)?.mediaDevices;
        if (mediaDevices?.getUserMedia) {
          const stream = await mediaDevices.getUserMedia({ video: true, audio: true });
          localStreamRef.current = stream;
          if (localVideoRef.current) localVideoRef.current.srcObject = stream;
        }
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Unable to initialize interview room');
    } finally {
      setLoading(false);
    }
  }, [canUseMedia, interviewId, loadPerformance, refreshRoom]);

  useEffect(() => {
    initialize();
    return () => {
      if (room?.room_id) api.post(`/interview-room/${room.room_id}/leave`, {}).catch(() => undefined);
      if (localStreamRef.current) localStreamRef.current.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!localStreamRef.current) return;
    localStreamRef.current.getAudioTracks().forEach((track) => {
      track.enabled = micOn;
    });
  }, [micOn]);

  useEffect(() => {
    if (!room?.room_id) return;
    const t = setInterval(() => refreshRoom(room.room_id), 5000);
    return () => clearInterval(t);
  }, [refreshRoom, room?.room_id]);

  const sendChat = async () => {
    if (!room?.room_id || !message.trim()) return;
    setSendingMessage(true);
    try {
      await api.post(`/interview-room/${room.room_id}/chat`, { message: message.trim() });
      setMessage('');
      await refreshRoom(room.room_id);
    } finally {
      setSendingMessage(false);
    }
  };

  const runAiAssist = async (action: 'suggest_question' | 'evaluate_response' | 'coaching_tip' | 'summarize') => {
    if (!room?.room_id) return;
    setAiLoading(true);
    try {
      await api.post(`/interview-room/${room.room_id}/ai-assist`, { action, context: aiContext });
      setAiContext('');
      await refreshRoom(room.room_id);
    } finally {
      setAiLoading(false);
    }
  };

  const endInterviewAndAnalyze = async () => {
    if (!room?.room_id) return;
    setEndingRoom(true);
    try {
      await api.post(`/interview-room/${room.room_id}/end`, {});
      await api.post(`/interview-performance/${interviewId}/analyze`, {});
      await refreshRoom(room.room_id);
      await loadPerformance();
    } finally {
      setEndingRoom(false);
    }
  };

  const downloadPerformancePdf = async () => {
    setDownloadingPdf(true);
    setStatusMsg('');
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
      setStatusMsg('PDF downloaded (v1.4 policy enforced).');
    } catch {
      setStatusMsg('Unable to download PDF summary.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const downloadInterviewContentPdf = async () => {
    setDownloadingContentPdf(true);
    setStatusMsg('');
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
      setStatusMsg('Interview content PDF downloaded.');
    } catch {
      setStatusMsg('Unable to download interview content PDF.');
    } finally {
      setDownloadingContentPdf(false);
    }
  };

  const emailAdminVerification = async () => {
    setEmailingAdmin(true);
    setStatusMsg('');
    try {
      const res = await api.post(`/interview-performance/${interviewId}/email-admin-verification`, {});
      setStatusMsg(`Admin verification email sent to ${res.data?.sent_count || 0} recipient(s).`);
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail || 'Unable to send admin verification email.');
    } finally {
      setEmailingAdmin(false);
    }
  };

  const emailPdfV15Suite = async () => {
    setEmailingPdfSuite(true);
    setStatusMsg('');
    try {
      const res = await api.post('/admin/pdf-v15/email-verification-suite', {});
      setStatusMsg(`PDF verification suite emailed to ${res.data?.sent_count || 0} admin recipient(s).`);
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail || 'Unable to send PDF verification suite.');
    } finally {
      setEmailingPdfSuite(false);
    }
  };

  const addAnnotation = async () => {
    if (!room?.room_id || !annotationNote.trim()) return;
    setAddingAnnotation(true);
    setStatusMsg('');
    try {
      await api.post(`/interview-room/${room.room_id}/replay-annotations`, {
        second_offset: Number(annotationSecond || '0') || 0,
        category: annotationCategory || 'general',
        severity: annotationSeverity,
        note: annotationNote.trim(),
      });
      setAnnotationNote('');
      await loadReplayTimeline(room.room_id);
      setStatusMsg('Evaluator annotation saved.');
    } catch (e: any) {
      setStatusMsg(e?.response?.data?.detail || 'Unable to save annotation.');
    } finally {
      setAddingAnnotation(false);
    }
  };

  if (loading) {
    return (
      <View style={{ width: '100%', maxWidth: 960, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 24, alignItems: 'center' }} data-testid="interview-room-panel-loading" testID="interview-room-panel-loading">
        <ActivityIndicator color={C.primary} />
      </View>
    );
  }

  return (
    <View style={{ width: '100%', maxWidth: 1240, maxHeight: '92%', backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, overflow: 'hidden' }} data-testid="interview-room-panel" testID="interview-room-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: C.border }}>
        <View>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Video Interview Room</Text>
          <Text style={{ color: C.muted, fontSize: 11 }}>Interview: {interviewId}</Text>
        </View>
        <TouchableOpacity onPress={onClose} style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center' }} data-testid="close-interview-room-panel" testID="close-interview-room-panel">
          <Ionicons name="close" size={16} color={C.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, gap: 10 }}>
        {!!error && <Text style={{ color: C.error, fontSize: 12 }}>{error}</Text>}

        <View style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Room Status: {String(room?.status || 'waiting').toUpperCase()}</Text>
          <Text style={{ color: C.muted, fontSize: 11, marginTop: 3 }}>Participants: {(room?.participants || []).length}</Text>
          <View style={{ marginTop: 8, borderWidth: 1, borderColor: C.border, borderRadius: 10, overflow: 'hidden', backgroundColor: C.card, height: 220, alignItems: 'center', justifyContent: 'center' }}>
            {canUseMedia ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video ref={localVideoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} data-testid="interview-room-local-video" />
            ) : <Text style={{ color: C.muted, fontSize: 12 }}>Video preview optimized for web.</Text>}
          </View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            <TouchableOpacity onPress={() => setMicOn((v) => !v)} style={{ flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingVertical: 9, alignItems: 'center' }} data-testid="toggle-room-mic-btn" testID="toggle-room-mic-btn">
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{micOn ? 'Mute Mic' : 'Unmute Mic'}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={endInterviewAndAnalyze} disabled={endingRoom} style={{ flex: 1, backgroundColor: C.error, borderRadius: 8, paddingVertical: 9, alignItems: 'center', opacity: endingRoom ? 0.7 : 1 }} data-testid="end-and-analyze-btn" testID="end-and-analyze-btn">
              <Text style={{ color: C.primaryText || C.text, fontSize: 12, fontWeight: '800' }}>{endingRoom ? 'Ending...' : 'End + Analyze'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10 }} data-testid="replay-timeline-section" testID="replay-timeline-section">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Replay Timeline + Evaluator Annotations</Text>
            <TouchableOpacity onPress={() => room?.room_id && loadReplayTimeline(room.room_id)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card }} data-testid="refresh-replay-timeline-btn" testID="refresh-replay-timeline-btn">
              <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>{timelineLoading ? '...' : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginTop: 8, maxHeight: 180 }} data-testid="replay-timeline-events-list" testID="replay-timeline-events-list">
            <ScrollView>
              {(timelineEvents || []).slice(-16).map((ev: any) => (
                <View key={ev.event_id} style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8, marginBottom: 6 }} data-testid={`replay-event-${ev.event_id}`} testID={`replay-event-${ev.event_id}`}>
                  <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{String(ev.event_type || 'event').replace('_', ' ')} • T+{ev.second_offset || 0}s</Text>
                  <Text style={{ color: C.text, fontSize: 11, marginTop: 2 }}>{ev.message || ''}</Text>
                </View>
              ))}
              {(timelineEvents || []).length === 0 && <Text style={{ color: C.muted, fontSize: 11 }}>No replay events yet.</Text>}
            </ScrollView>
          </View>

          <View style={{ marginTop: 8, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8 }}>
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>Add Evaluator Annotation</Text>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TextInput value={annotationSecond} onChangeText={setAnnotationSecond} keyboardType="numeric" placeholder="Second" placeholderTextColor={C.muted}
                style={{ flex: 0.32, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 8, color: C.text, fontSize: 12 } as any}
                data-testid="annotation-second-input" testID="annotation-second-input" />
              <TextInput value={annotationCategory} onChangeText={setAnnotationCategory} placeholder="Category" placeholderTextColor={C.muted}
                style={{ flex: 0.68, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 8, color: C.text, fontSize: 12 } as any}
                data-testid="annotation-category-input" testID="annotation-category-input" />
            </View>

            <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
              {(['low', 'medium', 'high'] as const).map((level) => (
                <TouchableOpacity key={level} onPress={() => setAnnotationSeverity(level)}
                  style={{ flex: 1, borderRadius: 8, paddingVertical: 7, alignItems: 'center', borderWidth: 1, borderColor: annotationSeverity === level ? C.primary : C.border, backgroundColor: annotationSeverity === level ? (globalThis as any).__alphaColor(C.primary, '22') : C.card }}
                  data-testid={`annotation-severity-${level}-btn`} testID={`annotation-severity-${level}-btn`}>
                  <Text style={{ color: annotationSeverity === level ? C.primary : C.textSec, fontSize: 11, fontWeight: '700' }}>{level.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput value={annotationNote} onChangeText={setAnnotationNote} multiline placeholder="Annotation note" placeholderTextColor={C.muted}
              style={{ minHeight: 56, marginTop: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 8, color: C.text, fontSize: 12 } as any}
              data-testid="annotation-note-input" testID="annotation-note-input" />

            <TouchableOpacity onPress={addAnnotation} disabled={addingAnnotation || !annotationNote.trim()}
              style={{ marginTop: 8, borderRadius: 8, paddingVertical: 9, alignItems: 'center', backgroundColor: C.primary, opacity: addingAnnotation || !annotationNote.trim() ? 0.6 : 1 }}
              data-testid="save-annotation-btn" testID="save-annotation-btn">
              <Text style={{ color: C.primaryText || C.text, fontSize: 12, fontWeight: '700' }}>{addingAnnotation ? 'Saving...' : 'Save Annotation'}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginTop: 8 }} data-testid="replay-annotations-list" testID="replay-annotations-list">
            {(timelineAnnotations || []).slice(-10).map((ann: any) => (
              <View key={ann.annotation_id} style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8, marginBottom: 6 }} data-testid={`replay-annotation-${ann.annotation_id}`} testID={`replay-annotation-${ann.annotation_id}`}>
                <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>T+{ann.second_offset || 0}s • {String(ann.category || 'general').toUpperCase()} • {String(ann.severity || 'low').toUpperCase()}</Text>
                <Text style={{ color: C.text, fontSize: 11, marginTop: 2 }}>{ann.note || ''}</Text>
              </View>
            ))}
            {(timelineAnnotations || []).length === 0 && <Text style={{ color: C.muted, fontSize: 11 }}>No evaluator annotations yet.</Text>}
          </View>
        </View>

        <View style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 6 }}>Chat</Text>
          <View style={{ maxHeight: 140 }}>
            <ScrollView>
              {(room?.chat_messages || []).map((msg: any) => (
                <View key={msg.id} style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8, marginBottom: 6 }} data-testid={`room-msg-${msg.id}`}>
                  <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{msg.name}</Text>
                  <Text style={{ color: C.text, fontSize: 12 }}>{msg.message}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 8 }}>
            <TextInput value={message} onChangeText={setMessage} placeholder="Send message" placeholderTextColor={C.muted}
              style={{ flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 8, color: C.text, fontSize: 12 } as any}
              data-testid="room-chat-input" testID="room-chat-input" />
            <TouchableOpacity onPress={sendChat} disabled={!message.trim() || sendingMessage} style={{ backgroundColor: C.primary, borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center', opacity: !message.trim() || sendingMessage ? 0.5 : 1 }} data-testid="room-chat-send-btn" testID="room-chat-send-btn">
              <Ionicons name="send" size={15} color={C.primaryText || C.text} />
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>AI Interview Assist</Text>
          <TextInput value={aiContext} onChangeText={setAiContext} multiline placeholder="Context for AI assist" placeholderTextColor={C.muted}
            style={{ minHeight: 64, marginTop: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 8, color: C.text, fontSize: 12 } as any}
            data-testid="room-ai-context-input" testID="room-ai-context-input" />
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
            {[
              { key: 'suggest', label: 'Suggest', action: 'suggest_question' as const },
              { key: 'evaluate', label: 'Evaluate', action: 'evaluate_response' as const },
              { key: 'coach', label: 'Coach', action: 'coaching_tip' as const },
              { key: 'summary', label: 'Summarize', action: 'summarize' as const },
            ].map((btn) => (
              <TouchableOpacity key={btn.key} onPress={() => runAiAssist(btn.action)} disabled={aiLoading} style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, opacity: aiLoading ? 0.7 : 1 }} data-testid={`room-ai-${btn.key}-btn`} testID={`room-ai-${btn.key}-btn`}>
                <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>{aiLoading ? '...' : btn.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {performance && (
          <View style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10 }} data-testid="room-performance-report" testID="room-performance-report">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>Performance Report</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[['Communication', performance.communication_score], ['Confidence', performance.confidence_score], ['Relevance', performance.relevance_score], ['Overall', performance.overall_score]].map(([label, value]) => (
                <View key={String(label)} style={{ width: '48%', backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8 }}>
                  <Text style={{ color: C.muted, fontSize: 10 }}>{label}</Text>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{value as number}</Text>
                </View>
              ))}
            </View>
            <Text style={{ color: C.textSec, fontSize: 12, marginTop: 8 }}>Recommendation: {String(performance.hiring_recommendation || '').replace('_', ' ')}</Text>
            {(performance.behavioral_insights || []).map((insight: string, idx: number) => (
              <Text key={idx} style={{ color: C.muted, fontSize: 11, marginTop: 3 }}>• {insight}</Text>
            ))}

            <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
              <TouchableOpacity onPress={downloadPerformancePdf} disabled={downloadingPdf}
                style={{ flex: 1, backgroundColor: C.primary, borderRadius: 8, paddingVertical: 9, alignItems: 'center', opacity: downloadingPdf ? 0.7 : 1 }}
                data-testid="room-download-pdf-btn" testID="room-download-pdf-btn">
                <Text style={{ color: C.primaryText || C.text, fontSize: 11, fontWeight: '700' }}>{downloadingPdf ? 'Preparing...' : 'Download PDF'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={downloadInterviewContentPdf} disabled={downloadingContentPdf}
                style={{ flex: 1, backgroundColor: C.warning, borderRadius: 8, paddingVertical: 9, alignItems: 'center', opacity: downloadingContentPdf ? 0.7 : 1 }}
                data-testid="room-download-content-pdf-btn" testID="room-download-content-pdf-btn">
                <Text style={{ color: C.primaryText || C.text, fontSize: 11, fontWeight: '700' }}>{downloadingContentPdf ? 'Preparing...' : 'Content PDF'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={emailAdminVerification} disabled={emailingAdmin}
                style={{ flex: 1, backgroundColor: C.success, borderRadius: 8, paddingVertical: 9, alignItems: 'center', opacity: emailingAdmin ? 0.7 : 1 }}
                data-testid="room-email-admin-btn" testID="room-email-admin-btn">
                <Text style={{ color: C.primaryText || C.text, fontSize: 11, fontWeight: '700' }}>{emailingAdmin ? 'Sending...' : 'Email Admin'}</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity onPress={emailPdfV15Suite} disabled={emailingPdfSuite}
              style={{ marginTop: 8, backgroundColor: C.accent, borderRadius: 8, paddingVertical: 9, alignItems: 'center', opacity: emailingPdfSuite ? 0.7 : 1 }}
              data-testid="room-email-v15-suite-btn" testID="room-email-v15-suite-btn">
              <Text style={{ color: C.primaryText || C.text, fontSize: 11, fontWeight: '700' }}>{emailingPdfSuite ? 'Sending...' : 'Email Full PDF Suite'}</Text>
            </TouchableOpacity>
            {!!statusMsg && <Text style={{ color: C.muted, fontSize: 11, marginTop: 8 }}>{statusMsg}</Text>}
          </View>
        )}
      </ScrollView>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
