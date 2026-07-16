import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system';
import { Ionicons } from '@expo/vector-icons';
import AppShell from './AppShell';
import { useTheme } from '../context/ThemeContext';

const DOWNLOADS_KEY = 'downloaded_media_v1';
const SETTINGS_KEY = 'downloads_cleanup_settings';

export default function DownloadsManagerView() {
  const { colors, darkMode } = useTheme();
  const [downloads, setDownloads] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalSize, setTotalSize] = useState(0);
  const [settings, setSettings] = useState({ autoCleanup: true, maxStorageMB: 500 });
  const [cleanupRunning, setCleanupRunning] = useState(false);

  const totalSizeMB = useMemo(() => (totalSize / (1024 * 1024)).toFixed(1), [totalSize]);

  const loadSettings = useCallback(async () => {
    try {
      const raw = await AsyncStorage.getItem(SETTINGS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setSettings({
          autoCleanup: parsed.autoCleanup ?? true,
          maxStorageMB: parsed.maxStorageMB ?? 500,
        });
      }
    } catch (err) {
      console.error(err);
    }
  }, []);

  const persistSettings = useCallback(async (next: any) => {
    setSettings(next);
    try {
      await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    } catch (err) {
      console.error(err);
    }
  }, []);

  const calculateStorage = useCallback(async (items: any[]) => {
    let total = 0;
    for (const item of items) {
      if (!item.file_uri) continue;
      try {
        const info = await FileSystem.getInfoAsync(item.file_uri);
        if (info.exists) {
          total += info.size || 0;
        }
      } catch (err) {
        console.error(err);
      }
    }
    setTotalSize(total);
    return total;
  }, []);

  const loadDownloads = useCallback(async () => {
    try {
      setLoading(true);
      const raw = await AsyncStorage.getItem(DOWNLOADS_KEY);
      const list = raw ? JSON.parse(raw) : [];
      const items = Array.isArray(list) ? list : [];
      setDownloads(items);
      await calculateStorage(items);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [calculateStorage]);

  const removeDownload = async (videoId: string) => {
    const target = downloads.find(d => d.video_id === videoId);
    if (target?.file_uri) {
      try {
        await FileSystem.deleteAsync(target.file_uri, { idempotent: true });
      } catch (err) {
        console.error(err);
      }
    }
    const updated = downloads.filter(d => d.video_id !== videoId);
    await AsyncStorage.setItem(DOWNLOADS_KEY, JSON.stringify(updated));
    setDownloads(updated);
    await calculateStorage(updated);
  };

  const runCleanup = async () => {
    if (!downloads.length) return;
    setCleanupRunning(true);
    try {
      const maxBytes = settings.maxStorageMB * 1024 * 1024;
      let currentSize = await calculateStorage(downloads);
      if (currentSize <= maxBytes) return;
      const sorted = [...downloads].sort((a, b) => new Date(a.downloaded_at || 0).getTime() - new Date(b.downloaded_at || 0).getTime());
      const toKeep = [...sorted];
      while (currentSize > maxBytes && toKeep.length > 0) {
        const item = toKeep.shift();
        if (item?.file_uri) {
          await FileSystem.deleteAsync(item.file_uri, { idempotent: true });
        }
        currentSize = await calculateStorage(toKeep);
      }
      await AsyncStorage.setItem(DOWNLOADS_KEY, JSON.stringify(toKeep));
      setDownloads(toKeep);
    } catch (err) {
      console.error(err);
      Alert.alert('Cleanup failed', 'Please try again.');
    } finally {
      setCleanupRunning(false);
    }
  };

  useEffect(() => {
    loadSettings();
    loadDownloads();
  }, [loadDownloads, loadSettings]);

  useEffect(() => {
    if (settings.autoCleanup) {
      runCleanup();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.autoCleanup]);

  return (
    <AppShell>
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 80 }}>
        <View style={{ marginBottom: 20 }} data-testid="downloads-manager-header" testID="downloads-manager-header">
          <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text }}>Downloads Manager</Text>
          <Text style={{ color: colors.textMuted, marginTop: 4 }}>Manage offline storage and auto-cleanup rules.</Text>
        </View>

        {Platform.OS === 'web' && (
          <View style={{ backgroundColor: darkMode ? colors.card : colors.bgSoft, padding: 16, borderRadius: 12, marginBottom: 16 }}>
            <Text style={{ color: colors.warningText, fontWeight: '700' }}>Offline downloads are available on mobile devices.</Text>
          </View>
        )}

        <View style={{ backgroundColor: darkMode ? colors.cardMuted : colors.card, padding: 16, borderRadius: 14, marginBottom: 16 }} data-testid="downloads-storage-card" testID="downloads-storage-card">
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>Storage Used</Text>
          <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', marginTop: 6 }}>{totalSizeMB} MB</Text>
          <Text style={{ color: colors.textDim, fontSize: 12, marginTop: 6 }}>Limit: {settings.maxStorageMB} MB</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
            <TouchableOpacity
              style={{ backgroundColor: colors.primary, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10 }}
              onPress={runCleanup}
              data-testid="downloads-cleanup-now" testID="downloads-cleanup-now"
            >
              {cleanupRunning ? (
                <ActivityIndicator color={colors.primaryText || colors.buttonText || colors.card} />
              ) : (
                <Text style={{ color: colors.primaryText || colors.buttonText || colors.text, fontWeight: '700' }}>Run Cleanup Now</Text>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              style={{ borderWidth: 1, borderColor: colors.borderStrong, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10 }}
              onPress={() => persistSettings({ ...settings, autoCleanup: !settings.autoCleanup })}
              data-testid="downloads-toggle-autocleanup" testID="downloads-toggle-autocleanup"
            >
              <Text style={{ color: colors.text, fontWeight: '700' }}>{settings.autoCleanup ? 'Auto Cleanup: On' : 'Auto Cleanup: Off'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: darkMode ? colors.cardMuted : colors.card, padding: 16, borderRadius: 14, marginBottom: 16 }}>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 8 }}>Set Max Storage (MB)</Text>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {[250, 500, 1000].map(value => (
              <TouchableOpacity
                key={value}
                style={{ backgroundColor: settings.maxStorageMB === value ? colors.primary : (darkMode ? colors.card : colors.bgSoft), paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10 }}
                onPress={() => persistSettings({ ...settings, maxStorageMB: value })}
                data-testid={`downloads-storage-${value}`} testID={`downloads-storage-${value}`}
              >
                <Text style={{ color: settings.maxStorageMB === value ? (colors.primaryText || colors.buttonText || colors.text) : colors.text, fontWeight: '700' }}>{value} MB</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={{ marginTop: 10 }}>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>Downloaded Titles</Text>
          {loading ? (
            <ActivityIndicator color={colors.accent} />
          ) : downloads.length === 0 ? (
            <View style={{ alignItems: 'center', padding: 24 }} data-testid="downloads-empty" testID="downloads-empty">
              <Ionicons name="download-outline" size={40} color="var(--app-primary)" />
              <Text style={{ color: colors.textMuted, marginTop: 8 }}>No downloads yet.</Text>
            </View>
          ) : (
            downloads.map(item => (
              <View key={item.video_id} style={{ backgroundColor: darkMode ? colors.card : colors.bgSoft, padding: 12, borderRadius: 12, marginBottom: 10 }} data-testid={`download-item-${item.video_id}`} testID={`download-item-${item.video_id}`}>
                <Text style={{ color: colors.text, fontWeight: '700' }}>{item.title}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>Saved for offline playback</Text>
                <TouchableOpacity
                  style={{ marginTop: 8, alignSelf: 'flex-start' }}
                  onPress={() => removeDownload(item.video_id)}
                  data-testid={`download-remove-${item.video_id}`} testID={`download-remove-${item.video_id}`}
                >
                  <Text style={{ color: colors.error, fontWeight: '700' }}>Remove</Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </AppShell>
  );
}

/* i18n-probe t('i18n.auto.probe') */
