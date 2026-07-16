// Public async video-QA page — candidate records 3 role-specific video answers.
// Route: /careers/video-qa/[token]
import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

const API = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '');

export default function VideoQAPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primary: colors.primary,
    success: colors.success,
    error: colors.error,
    warning: colors.warning,
    onPrimary: colors.primaryText,
    videoSurface: colors.bgCard || colors.cardAlt || colors.surface,
  }), [colors]);

  const params = useLocalSearchParams<{ token: string }>();
  const token = String(params?.token || '');
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState('');
  const [current, setCurrent] = useState(0);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [previewBlob, setPreviewBlob] = useState<Blob | null>(null);
  const videoRef = useRef<any>(null);
  const mediaRecorderRef = useRef<any>(null);
  const chunksRef = useRef<any[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const previewObjectUrlRef = useRef<string | null>(null);
  const autoStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordStartedAtRef = useRef<number>(0);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/careers/video-qa/${token}`, { credentials: 'omit' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e: any) {
      setErr(e?.message || tx('videoQa.errors.inviteNotFound', 'Invite not found'));
    }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const startRecording = async () => {
    setErr('');
    setUploadProgress(0);
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setPreviewBlob(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (videoRef.current) (videoRef.current as any).srcObject = stream;
      const mr = new (window as any).MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9,opus' });
      chunksRef.current = [];
      mr.ondataavailable = (e: any) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'video/webm' });
        setPreviewBlob(blob);
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }
        if (videoRef.current) {
          (videoRef.current as any).srcObject = null;
          if (previewObjectUrlRef.current) {
            URL.revokeObjectURL(previewObjectUrlRef.current);
            previewObjectUrlRef.current = null;
          }
          previewObjectUrlRef.current = URL.createObjectURL(blob);
          (videoRef.current as any).src = previewObjectUrlRef.current;
        }
      };
      mediaRecorderRef.current = mr;
      mr.start();
      recordStartedAtRef.current = Date.now();
      setRecording(true);
      // 120s cap
      if (autoStopTimerRef.current) {
        clearTimeout(autoStopTimerRef.current);
      }
      autoStopTimerRef.current = setTimeout(() => {
        try {
          mr.state === 'recording' && mr.stop();
          setRecording(false);
        } catch (error) {
          handleAppRecoverableError({ scope: 'careers/video-qa/[token].tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
        }
      }, 120_000);
    } catch (e: any) {
      setErr(e?.message || tx('videoQa.errors.cameraAccessDenied', 'Camera access denied'));
    }
  };

  const stopRecording = () => {
    try { mediaRecorderRef.current?.stop(); } catch (error) { handleAppRecoverableError({ scope: 'careers/video-qa/[token].tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    setRecording(false);
  };

  const submit = async () => {
    if (!previewBlob) return;
    setUploading(true);
    setUploadProgress(0);
    setErr('');
    try {
      const durationSeconds = Math.max(0, Math.min(120, Math.round(((Date.now() - recordStartedAtRef.current) / 1000) * 10) / 10));
      const formData = new FormData();
      formData.append('question_index', String(current));
      formData.append('duration_seconds', String(durationSeconds));
      formData.append('video_file', previewBlob, `answer-${current + 1}.webm`);

      const responseData = await new Promise<any>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API}/api/careers/video-qa/${token}/answer`);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            setUploadProgress(Math.round((event.loaded / event.total) * 100));
          }
        };
        xhr.onload = () => {
          try {
            const parsed = xhr.responseText ? JSON.parse(xhr.responseText) : {};
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(parsed);
            } else {
              reject(new Error(parsed?.detail || `HTTP ${xhr.status}`));
            }
          } catch (error) {
            reject(error);
          }
        };
        xhr.onerror = () => reject(new Error(tx('videoQa.errors.uploadFailed', 'Upload failed')));
        xhr.send(formData);
      });
      void responseData;
      setUploadProgress(100);
      setPreviewBlob(null);
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
      if (videoRef.current) {
        (videoRef.current as any).src = '';
      }
      await load();
      if (data && current < (data.questions?.length || 0) - 1) setCurrent(current + 1);
    } catch (e: any) {
      setErr(e?.message || tx('videoQa.errors.uploadFailed', 'Upload failed'));
    }
    setUploading(false);
    setUploadProgress(0);
  };

  useEffect(() => {
    return () => {
      if (autoStopTimerRef.current) {
        clearTimeout(autoStopTimerRef.current);
        autoStopTimerRef.current = null;
      }
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, []);

  if (err && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 30 }} data-testid="vqa-error" testID="vqa-error">
        <Ionicons name="alert-circle" size={48} color={C.error} />
        <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', marginTop: 12 }}>{tx('videoQa.states.inviteNotAvailable', 'Invite not available')}</Text>
        <Text style={{ color: C.textSec, fontSize: 13, marginTop: 6, textAlign: 'center' }}>{err}</Text>
      </View>
    );
  }
  if (!data) {
    return <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator size="large" color={C.primary} /></View>;
  }

  const q = (data.questions || [])[current] || {};
  const done = data.status === 'submitted';

  return (
    <>
      <Stack.Screen options={{ title: tx('videoQa.page.title', 'Video pre-screen'), headerShown: false }} />
      <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 24, alignItems: 'center' }}>
        <View style={{ maxWidth: 960, width: '100%' }} data-testid="video-qa-page" testID="video-qa-page">
          <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{tx('videoQa.labels.preScreen', 'VIDEO PRE-SCREEN')}</Text>
          <Text style={{ color: C.text, fontSize: 22, fontWeight: '800', marginTop: 6 }}>
            {data.candidate_name} · {data.role_title}
          </Text>
          <Text style={{ color: C.textSec, fontSize: 13, marginTop: 8 }}>
            {tx('videoQa.instructions.summary', 'Record short answers (≤120s each) to the questions below. You can retake any answer before submitting.')}
          </Text>

          {done ? (
            <View style={{ marginTop: 24, padding: 20, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, alignItems: 'center' }} data-testid="video-qa-done" testID="video-qa-done">
              <Ionicons name="checkmark-circle" size={48} color={C.success} />
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginTop: 8 }}>{tx('videoQa.states.allAnswersSubmitted', 'All answers submitted')}</Text>
              <Text style={{ color: C.textSec, fontSize: 12, marginTop: 6 }}>{tx('videoQa.states.reviewByHiringTeam', 'The hiring team will review your video responses.')}</Text>
            </View>
          ) : (
            <>
              <View style={{ flexDirection: 'row', gap: 4, marginTop: 16 }}>
                {(data.questions || []).map((qq: any, i: number) => (
                  <TouchableOpacity
                    key={i}
                    onPress={() => setCurrent(i)}
                    style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: qq.answered ? C.success : i === current ? C.primary : C.border }}
                    data-testid={`vqa-pill-${i}`} testID={`vqa-pill-${i}`}
                  />
                ))}
              </View>
              <View style={{ marginTop: 18, padding: 16, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border }} data-testid="vqa-question" testID="vqa-question">
                <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('videoQa.labels.questionProgress', 'QUESTION {current} OF {total}').replace('{current}', String(current + 1)).replace('{total}', String(data.questions.length))}</Text>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginTop: 6 }}>{q.prompt}</Text>
                {q.answered && !previewBlob && (
                  <Text style={{ color: C.success, fontSize: 11, fontWeight: '700', marginTop: 8 }}>
                    {tx('videoQa.states.alreadyAnsweredHint', '✓ Already answered — record again to replace.')}
                  </Text>
                )}
              </View>

              <View style={{ marginTop: 16, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: C.border, backgroundColor: C.videoSurface, aspectRatio: 16 / 9 }}>
                {/* @ts-ignore */}
                <video ref={videoRef} autoPlay muted={recording} controls={!!previewBlob} style={{ width: '100%', height: '100%', background: C.videoSurface }} />
              </View>

              {err ? <Text style={{ color: C.error, fontSize: 12, marginTop: 10 }} data-testid="vqa-err" testID="vqa-err">{err}</Text> : null}

              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                {!recording && !previewBlob && (
                  <TouchableOpacity onPress={startRecording} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.primary }} data-testid="vqa-start" testID="vqa-start">
                    <Ionicons name="videocam" size={16} color={C.onPrimary} /><Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('videoQa.actions.startRecording', 'Start recording')}</Text>
                  </TouchableOpacity>
                )}
                {recording && (
                  <TouchableOpacity onPress={stopRecording} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.error }} data-testid="vqa-stop" testID="vqa-stop">
                    <Ionicons name="stop-circle" size={16} color={C.onPrimary} /><Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('videoQa.actions.stop', 'Stop')}</Text>
                  </TouchableOpacity>
                )}
                {previewBlob && !uploading && (
                  <>
                    <TouchableOpacity onPress={submit} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.success }} data-testid="vqa-submit" testID="vqa-submit">
                      <Ionicons name="cloud-upload" size={16} color={C.onPrimary} /><Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('videoQa.actions.submitAnswer', 'Submit answer')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => {
                      setPreviewBlob(null);
                      if (previewObjectUrlRef.current) {
                        URL.revokeObjectURL(previewObjectUrlRef.current);
                        previewObjectUrlRef.current = null;
                      }
                      if (videoRef.current) (videoRef.current as any).src = '';
                    }} style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: C.border }} data-testid="vqa-retake" testID="vqa-retake">
                      <Text style={{ color: C.textSec, fontSize: 13, fontWeight: '700' }}>{tx('videoQa.actions.retake', 'Retake')}</Text>
                    </TouchableOpacity>
                  </>
                )}
                {uploading && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 10 }} data-testid="vqa-uploading" testID="vqa-uploading">
                    <ActivityIndicator size="small" color={C.primary} />
                    <Text style={{ color: C.textSec, fontSize: 13 }} data-testid="vqa-upload-progress-text" testID="vqa-upload-progress-text">
                      {tx('videoQa.states.uploadingProgress', 'Uploading… {progress}%').replace('{progress}', String(uploadProgress || 0))}
                    </Text>
                  </View>
                )}
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </>
  );
}
