import { useCallback, useRef, useState } from 'react';
import { Platform } from 'react-native';

/**
 * Phase 2B — Native voice recording for the coaching chat (iOS/Android only).
 * Uses expo-av for capture and returns base64 audio ready for
 * POST /api/conversations/voice-message. No-op on web.
 */
export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const recordingRef = useRef<any>(null);

  const startRecording = useCallback(async (): Promise<boolean> => {
    if (Platform.OS === 'web') return false;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { Audio } = require('expo-av');
      const permission = await Audio.requestPermissionsAsync();
      if (!permission?.granted) return false;
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      recordingRef.current = recording;
      setIsRecording(true);
      return true;
    } catch (e) {
      console.warn('Voice recording failed to start:', e);
      recordingRef.current = null;
      setIsRecording(false);
      return false;
    }
  }, []);

  const stopRecording = useCallback(async (): Promise<{ base64: string; format: string } | null> => {
    const recording = recordingRef.current;
    recordingRef.current = null;
    setIsRecording(false);
    if (!recording) return null;
    try {
      await recording.stopAndUnloadAsync();
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { Audio } = require('expo-av');
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
      const uri: string | null = recording.getURI();
      if (!uri) return null;
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const FileSystem = require('expo-file-system/legacy');
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType?.Base64 ?? 'base64',
      });
      const format = uri.split('.').pop()?.toLowerCase() || 'm4a';
      return { base64, format };
    } catch (e) {
      console.warn('Voice recording failed to stop:', e);
      return null;
    }
  }, []);

  const cancelRecording = useCallback(async () => {
    const recording = recordingRef.current;
    recordingRef.current = null;
    setIsRecording(false);
    if (recording) {
      try {
        await recording.stopAndUnloadAsync();
      } catch {
        // already unloaded
      }
    }
  }, []);

  return { isRecording, startRecording, stopRecording, cancelRecording };
}
