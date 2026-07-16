import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import api from '../src/services/api';
import { useTranslation } from '../src/hooks/useTranslation';
import { useManagedWebSocket } from '../src/hooks/useManagedWebSocket';
import { handleRecoverableError } from '../src/utils/handleRecoverableError';
import { reportClientCrash } from '../src/services/clientErrorReporter';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type PerformanceReport = {
  communication_score: number;
  confidence_score: number;
  relevance_score: number;
  overall_score: number;
  talk_time_balance_est: number;
  duration_minutes: number;
  behavioral_insights: string[];
  hiring_recommendation: string;
};

const RETRYABLE_HTTP_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const WS_MAX_RECONNECT_ATTEMPTS = 3;
const INITIALIZE_MAX_RETRIES = 2;

const waitFor = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const isRetryableRequestError = (error: any) => {
  const status = Number(error?.response?.status || 0);
  if (RETRYABLE_HTTP_STATUS.has(status)) return true;
  const code = String(error?.code || '').toLowerCase();
  return code.includes('timeout') || code.includes('network') || code.includes('econnaborted');
};

const getRequestErrorMessage = (error: any, fallback: string) => (
  error?.response?.data?.detail
  || error?.message
  || fallback
);

const reportInterviewRecoverableError = (scope: string, error: any, message: string) => {
  reportClientCrash({
    panelId: `interview-room:${scope}`,
    panelName: 'InterviewRoom',
    message,
    stack: String(error?.stack || error?.message || ''),
  });
};

export default function InterviewRoomPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { user } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ interviewId?: string }>();
  const interviewId = String(params.interviewId || '');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [room, setRoom] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [aiContext, setAiContext] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [micOn, setMicOn] = useState(true);
  const [endingRoom, setEndingRoom] = useState(false);
  const [performance, setPerformance] = useState<PerformanceReport | null>(null);

  const localVideoRef = useRef<any>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const unmountedRef = useRef(false);

  const wsBase = useMemo(() => {
    const backend = resolveRuntimeBaseUrl().replace(/\/$/, '');
    if (!backend) return '';
    return backend.replace(/^http/, 'ws');
  }, []);

  const applyLocalMediaState = useCallback(() => {
    if (!localStreamRef.current) return;
    const tracks = localStreamRef.current.getAudioTracks();
    tracks.forEach((t) => {
      t.enabled = micOn;
    });
  }, [micOn]);

  const startLocalPreview = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    try {
      const mediaDevices = (navigator as any)?.mediaDevices;
      if (!mediaDevices?.getUserMedia) return;
      const stream = await mediaDevices.getUserMedia({ video: true, audio: true });
      localStreamRef.current = stream;
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
      setCameraOn(true);
      applyLocalMediaState();
    } catch (error) {
      reportInterviewRecoverableError('local-preview', error, 'Unable to access camera preview.');
      handleAppRecoverableError({
        scope: 'interview-room.local-preview',
        error,
        message: tx('interviewRoom.errors.cameraPreviewFailed', 'Unable to access camera preview.'),
        setError,
        onRetry: () => { void startLocalPreview(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setCameraOn(false);
    }
  }, [applyLocalMediaState]);

  const activeRoomId = String(room?.room_id || '');
  const wsEnabled = Boolean(activeRoomId && wsBase && user?.user_id && room?.status !== 'ended');

  const buildRoomWsUrl = useCallback(() => {
    if (!wsBase || !user?.user_id || !activeRoomId) return '';
    return `${wsBase}/api/interview-room/ws/${activeRoomId}/${user.user_id}`;
  }, [activeRoomId, user?.user_id, wsBase]);

  const { socketRef: wsRef, lastError: roomWsLastError } = useManagedWebSocket({
    enabled: wsEnabled,
    buildUrl: buildRoomWsUrl,
    errorScope: 'interview-room/ws',
    maxReconnectAttempts: WS_MAX_RECONNECT_ATTEMPTS,
    baseReconnectDelayMs: 900,
    onOpen: () => {
      if (unmountedRef.current) return;
      setError('');
    },
    onClose: () => {
      if (unmountedRef.current || room?.status === 'ended') return;
      setError(tx('interviewRoom.errors.reconnecting', 'Reconnecting live channel...'));
    },
    onError: () => {
      if (unmountedRef.current) return;
      setError((prev) => prev || tx('interviewRoom.errors.liveUnstable', 'Live connection unstable. Reconnecting...'));
    },
    onReconnectAttempt: () => {
      if (unmountedRef.current || room?.status === 'ended') return;
      setError(tx('interviewRoom.errors.reconnecting', 'Reconnecting live channel...'));
    },
    onMessage: (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'chat_message') {
          setRoom((prev: any) => ({
            ...(prev || {}),
            chat_messages: [...(prev?.chat_messages || []), payload.data],
          }));
        }
        if (payload.type === 'data_change') {
          api.get(`/interview-room/${activeRoomId}`).then((res) => {
            setRoom(res.data?.room || null);
          }).catch((error) => {
            reportInterviewRecoverableError('room-refresh', error, 'Failed to refresh room state from live event.');
            handleRecoverableError(error, {
              scope: 'interview-room/ws-room-refresh',
              fallbackMessage: 'Failed to refresh room state from live event.',
              setMessage: setError,
            });
          });
          if (interviewId) {
            api.get(`/interview-performance/${interviewId}`).then((res) => {
              if (res.data?.report) setPerformance(res.data.report);
            }).catch((error) => {
              reportInterviewRecoverableError('performance-refresh', error, 'Failed to refresh interview performance from live event.');
              handleRecoverableError(error, {
                scope: 'interview-room/ws-performance-refresh',
                fallbackMessage: 'Failed to refresh interview performance from live event.',
                setMessage: setError,
              });
            });
          }
        }
        if (payload.type === 'room_ended') {
          setRoom((prev: any) => ({ ...(prev || {}), status: 'ended' }));
        }
      } catch (error) {
        reportInterviewRecoverableError('ws-parse', error, 'Received malformed realtime payload.');
        handleRecoverableError(error, {
          scope: 'interview-room/ws-parse',
          fallbackMessage: 'Received malformed realtime payload.',
          setMessage: setError,
        });
      }
    },
  });

  useEffect(() => {
    if (!roomWsLastError) return;
    const message = getRequestErrorMessage({ message: roomWsLastError }, tx('interviewRoom.errors.liveDisconnected', 'Live connection lost. Please retry.'));
    reportInterviewRecoverableError('ws-last-error', roomWsLastError, message);
    setError(message);
  }, [roomWsLastError, tx]);

  const refreshRoom = useCallback(async (roomId: string) => {
    try {
      const res = await api.get(`/interview-room/${roomId}`);
      setRoom(res.data?.room || null);
    } catch (error) {
      reportInterviewRecoverableError('room-refresh-api', error, 'Failed to refresh interview room.');
      handleAppRecoverableError({
        scope: 'interview-room.room-refresh-api',
        error,
        message: tx('interviewRoom.errors.refreshRoomFailed', 'Failed to refresh interview room.'),
        setError,
        onRetry: () => { void refreshRoom(roomId); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [tx]);

  const loadPerformance = useCallback(async () => {
    if (!interviewId) return;
    try {
      const res = await api.get(`/interview-performance/${interviewId}`);
      if (res.data?.report) setPerformance(res.data.report);
    } catch (error) {
      reportInterviewRecoverableError('performance-load', error, 'Failed to load interview performance.');
      handleAppRecoverableError({
        scope: 'interview-room.performance-load',
        error,
        message: tx('interviewRoom.errors.performanceLoadFailed', 'Failed to load interview performance.'),
        setError,
        onRetry: () => { void loadPerformance(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [interviewId, tx]);

  const initialize = useCallback(async () => {
    if (!interviewId) {
      setError(tx('interviewRoom.errors.missingId', 'Missing interview ID'));
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      let lastError: any = null;
      for (let attempt = 0; attempt <= INITIALIZE_MAX_RETRIES; attempt += 1) {
        try {
          const createRes = await api.post('/interview-room/create', { interview_id: interviewId });
          const roomData = createRes.data?.room;
          if (!roomData?.room_id) {
            throw new Error('Interview room not created');
          }

          await api.post(`/interview-room/${roomData.room_id}/join`, {});
          setRoom(roomData);
          await refreshRoom(roomData.room_id);
          await startLocalPreview();
          await loadPerformance();
          setError('');
          return;
        } catch (error: any) {
          lastError = error;
          if (!isRetryableRequestError(error) || attempt === INITIALIZE_MAX_RETRIES) {
            break;
          }
          await waitFor((attempt + 1) * 900);
        }
      }
      const message = getRequestErrorMessage(lastError, tx('interviewRoom.errors.initFailed', 'Unable to initialize interview room'));
      reportInterviewRecoverableError('initialize', lastError, message);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [interviewId, loadPerformance, refreshRoom, startLocalPreview, tx]);

  useEffect(() => {
    unmountedRef.current = false;
    initialize();
    return () => {
      unmountedRef.current = true;
      if (room?.room_id) {
        api.post(`/interview-room/${room.room_id}/leave`, {}).catch(() => undefined);
      }
      if (wsRef.current) wsRef.current.close();
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    applyLocalMediaState();
  }, [applyLocalMediaState, micOn]);

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
    if (!room?.room_id || !interviewId) return;
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

  if (loading) {
    return (
      <AppShell>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }} data-testid="interview-room-loading" testID="interview-room-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80, gap: 12 }} data-testid="interview-room-page" testID="interview-room-page">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }}>{tx('interviewRoom.page.title', 'Video Interview Room')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>{tx('interviewRoom.labels.interviewId', 'Interview ID:')} {interviewId || '—'}</Text>
          </View>
          <TouchableOpacity onPress={() => router.back()} style={{ backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="interview-room-back-btn" testID="interview-room-back-btn">
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{tx('common.back', 'Back')}</Text>
          </TouchableOpacity>
        </View>

        {!!error && (
          <View style={{ backgroundColor: colors.error + '14', borderWidth: 1, borderColor: colors.error + '45', borderRadius: 10, padding: 10, gap: 8 }} data-testid="interview-room-error-banner" testID="interview-room-error-banner">
            <Text style={{ color: colors.error, fontSize: 12 }} data-testid="interview-room-error" testID="interview-room-error">{error}</Text>
            <TouchableOpacity onPress={initialize} style={{ alignSelf: 'flex-start', backgroundColor: colors.card, borderWidth: 1, borderColor: colors.error + '45', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="interview-room-retry-button" testID="interview-room-retry-button">
              <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{tx('common.retry', 'Retry')}</Text>
            </TouchableOpacity>
          </View>
        )}

        <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="interview-room-core-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('interviewRoom.sections.liveSession', 'Live Session')}</Text>
            <Text style={{ color: room?.status === 'ended' ? colors.error : colors.successText, fontSize: 11, fontWeight: '700' }}>{String(room?.status || 'waiting').toUpperCase()}</Text>
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('interviewRoom.labels.participants', 'Participants: {count}').replace('{count}', String((room?.participants || []).length))}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {(room?.participants || []).map((p: any) => (
              <View key={p.user_id} style={{ backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}>
                <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{p.name} ({p.role})</Text>
              </View>
            ))}
          </View>

          <View style={{ marginTop: 10, borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden', backgroundColor: colors.bgSoft, height: 220, alignItems: 'center', justifyContent: 'center' }}>
            {Platform.OS === 'web' ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video ref={localVideoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} data-testid="interview-room-local-video" />
            ) : (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('interviewRoom.labels.localPreviewWebOnly', 'Local video preview is optimized for web.')}</Text>
            )}
          </View>

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
            <TouchableOpacity onPress={() => setMicOn((v) => !v)} style={{ flex: 1, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }} data-testid="interview-room-mic-toggle" testID="interview-room-mic-toggle">
              <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{micOn ? tx('interviewRoom.actions.muteMic', 'Mute Mic') : tx('interviewRoom.actions.unmuteMic', 'Unmute Mic')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={endInterviewAndAnalyze} disabled={endingRoom} style={{ flex: 1, backgroundColor: colors.error, borderRadius: 10, paddingVertical: 10, alignItems: 'center', opacity: endingRoom ? 0.7 : 1 }} data-testid="interview-room-end-btn" testID="interview-room-end-btn">
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{endingRoom ? tx('interviewRoom.actions.ending', 'Ending...') : tx('interviewRoom.actions.endAndAnalyze', 'End + Analyze')}</Text>
            </TouchableOpacity>
          </View>
          {!cameraOn && <Text style={{ color: colors.warningText, fontSize: 11, marginTop: 8 }}>{tx('interviewRoom.errors.cameraPermissionUnavailable', 'Camera permission unavailable — chat and AI analytics still work.')}</Text>}
        </View>

        <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="interview-room-chat-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>{tx('interviewRoom.sections.interviewChat', 'Interview Chat')}</Text>
          <View style={{ maxHeight: 180 }}>
            <ScrollView>
              {(room?.chat_messages || []).map((msg: any) => (
                <View key={msg.id} style={{ marginBottom: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 8 }} data-testid={`interview-chat-${msg.id}`}>
                  <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}>{msg.name}</Text>
                  <Text style={{ color: colors.text, fontSize: 12, marginTop: 2 }}>{msg.message}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 8 }}>
            <TextInput value={message} onChangeText={setMessage} placeholder={tx('interviewRoom.placeholders.typeMessage', 'Type message')} placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 9, color: colors.text }} data-testid="interview-chat-input" />
            <TouchableOpacity onPress={sendChat} disabled={!message.trim() || sendingMessage} style={{ backgroundColor: colors.primary, borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center', opacity: !message.trim() || sendingMessage ? 0.5 : 1 }} data-testid="interview-chat-send-btn" testID="interview-chat-send-btn">
              <Ionicons name="send" size={16} color={colors.primaryText} />
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="interview-room-ai-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('interviewRoom.sections.aiCopilot', 'AI Interview Copilot')}</Text>
          <TextInput value={aiContext} onChangeText={setAiContext} placeholder={tx('interviewRoom.placeholders.aiContext', 'Paste answer context, discussion notes, or question topic')} placeholderTextColor={colors.textMuted} multiline style={{ minHeight: 72, marginTop: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: colors.text }} data-testid="interview-ai-context-input" />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {[
              { key: 'suggest', label: tx('interviewRoom.aiActions.suggestQuestions', 'Suggest Questions'), action: 'suggest_question' as const },
              { key: 'evaluate', label: tx('interviewRoom.aiActions.evaluateResponse', 'Evaluate Response'), action: 'evaluate_response' as const },
              { key: 'coach', label: tx('interviewRoom.aiActions.coachingTip', 'Coaching Tip'), action: 'coaching_tip' as const },
              { key: 'summary', label: tx('interviewRoom.aiActions.summarize', 'Summarize'), action: 'summarize' as const },
            ].map((btn) => (
              <TouchableOpacity key={btn.key} onPress={() => runAiAssist(btn.action)} disabled={aiLoading} style={{ backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, opacity: aiLoading ? 0.7 : 1 }} data-testid={`interview-ai-${btn.key}-btn`} testID={`interview-ai-${btn.key}-btn`}>
                <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{aiLoading ? tx('interviewRoom.states.aiLoading', '...') : btn.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {(room?.ai_suggestions || []).length > 0 && (
            <View style={{ marginTop: 10, gap: 8 }}>
              {(room.ai_suggestions || []).slice(-3).reverse().map((ai: any) => (
                <View key={ai.id} style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), borderRadius: 8, padding: 8 }} data-testid={`interview-ai-response-${ai.id}`}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', marginBottom: 3 }}>{String(ai.action || 'ai').toUpperCase()}</Text>
                  <Text style={{ color: colors.text, fontSize: 12 }}>{ai.message}</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        {performance && (
          <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="interview-performance-report">
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>{tx('interviewRoom.sections.performanceReport', 'AI Interview Performance Report')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[[tx('interviewRoom.metrics.communication', 'Communication'), performance.communication_score], [tx('interviewRoom.metrics.confidence', 'Confidence'), performance.confidence_score], [tx('interviewRoom.metrics.relevance', 'Relevance'), performance.relevance_score], [tx('interviewRoom.metrics.overall', 'Overall'), performance.overall_score]].map(([label, value]) => (
                <View key={String(label)} style={{ width: '48%', backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 9 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }}>{label}</Text>
                  <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{value as number}</Text>
                </View>
              ))}
            </View>
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 10 }}>{tx('interviewRoom.labels.hiringRecommendation', 'Hiring Recommendation: {value}').replace('{value}', String(performance.hiring_recommendation))}</Text>
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 4 }}>{tx('interviewRoom.labels.talkTimeBalance', 'Talk-Time Balance Estimate: {value}%').replace('{value}', String(performance.talk_time_balance_est))}</Text>
            <View style={{ marginTop: 8 }}>
              {(performance.behavioral_insights || []).map((insight, idx) => (
                <Text key={idx} style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>• {insight}</Text>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </AppShell>
  );
}
