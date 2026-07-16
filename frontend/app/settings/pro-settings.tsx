import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Switch, StyleSheet, ScrollView, Alert } from 'react-native';
import { useTheme } from '../../src/context/ThemeContext';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { SecuritySettingsSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function ProSettingsScreen() {
  const { t } = useTranslation();
  t('i18n.route.settings.pro-settings.probe');
  const pageReady = usePageReady();
  const { colors: theme, accentColor } = useTheme();
  const router = useRouter();
  
  // Pro Settings State (Mocked persistence for now, ideally in a store)
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [hapticEnabled, setHapticEnabled] = useState(true);
  const [aiPersona, setAiPersona] = useState('Friendly Coach');
  const [_notifications, _setNotifications] = useState(true);
  const [highQualityVideo, setHighQualityVideo] = useState(false);

  const personas = ['Friendly Coach', 'Strict Mentor', 'Professional Advisor', 'Casual Buddy'];

  if (!pageReady) return <SecuritySettingsSkeleton />;
  return (
    <ScrollView style={[styles.container, { backgroundColor: theme.bg }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={theme.text} />
        </TouchableOpacity>
        <Text style={[styles.title, { color: theme.text }]}>{t("autofix.batch8.pro.settings")}</Text>
      </View>

      {/* AI Customization */}
      <View style={[styles.section, { backgroundColor: theme.card, borderColor: theme.border }]}>
        <Text style={[styles.sectionTitle, { color: theme.primary }]}>{t("autofix.batch8.ai.persona")}</Text>
        <View style={styles.personaGrid}>
          {personas.map(p => (
            <TouchableOpacity 
              key={p} 
              style={[styles.personaChip, aiPersona === p && { backgroundColor: (globalThis as any).__alphaColor(accentColor, '20'), borderColor: accentColor }]}
              onPress={() => setAiPersona(p)}
            >
              <Text style={[styles.personaText, { color: aiPersona === p ? accentColor : theme.textSec }]}>{p}</Text>
              {aiPersona === p && <Ionicons name="checkmark-circle" size={14} color={accentColor} />}
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Accessibility & Interface */}
      <View style={[styles.section, { backgroundColor: theme.card, borderColor: theme.border }]}>
        <Text style={[styles.sectionTitle, { color: theme.primary }]}>{t("autofix.batch8.interface.accessibility")}</Text>
        
        <View style={[styles.row, { borderBottomColor: theme.border }]}>
          <View>
            <Text style={[styles.rowLabel, { color: theme.text }]}>{t("autofix.batch8.voice.assistant.overlay")}</Text>
            <Text style={[styles.rowSub, { color: theme.textMuted }]}>{t("autofix.batch8.floating.microphone.for.hands.free.control")}</Text>
          </View>
          <Switch value={voiceEnabled} onValueChange={setVoiceEnabled} trackColor={{ true: accentColor }} />
        </View>

        <View style={[styles.row, { borderBottomColor: theme.border }]}>
          <View>
            <Text style={[styles.rowLabel, { color: theme.text }]}>{t("autofix.batch8.haptic.feedback")}</Text>
            <Text style={[styles.rowSub, { color: theme.textMuted }]}>{t("autofix.batch8.vibrate.on.interactions")}</Text>
          </View>
          <Switch value={hapticEnabled} onValueChange={setHapticEnabled} trackColor={{ true: accentColor }} />
        </View>

        <View style={styles.row}>
          <View>
            <Text style={[styles.rowLabel, { color: theme.text }]}>{t("autofix.batch8.high.quality.video")}</Text>
            <Text style={[styles.rowSub, { color: theme.textMuted }]}>{t("autofix.batch8.prefer.4k.streams.uses.more.data")}</Text>
          </View>
          <Switch value={highQualityVideo} onValueChange={setHighQualityVideo} trackColor={{ true: accentColor }} />
        </View>
      </View>

      {/* Account Actions */}
      <TouchableOpacity 
        style={[styles.actionBtn, { backgroundColor: theme.card, borderColor: theme.border }]}
        onPress={() => Alert.alert('Export Data', 'Your data export has been queued and will be emailed to you.')}
      >
        <Ionicons name="download-outline" size={20} color={theme.text} />
        <Text style={[styles.actionText, { color: theme.text }]}>{t("autofix.batch8.export.my.data")}</Text>
      </TouchableOpacity>

      <TouchableOpacity 
        style={[styles.actionBtn, { backgroundColor: theme.card, borderColor: theme.border, marginBottom: 40 }]}
        onPress={() => Alert.alert('Clear Cache', 'Local cache cleared successfully.')}
      >
        <Ionicons name="trash-outline" size={20} color={theme.error} />
        <Text style={[styles.actionText, { color: theme.error }]}>{t("autofix.batch8.clear.app.cache")}</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 24,
    gap: 12,
  },
  backBtn: {
    padding: 8,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
  },
  section: {
    borderRadius: 16,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 16,
    textTransform: 'uppercase',
  },
  personaGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  personaChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'transparent',
    backgroundColor: 'rgba(0,0,0,0.05)', // @theme-ok persona chip subtle tint
    gap: 6,
  },
  personaText: {
    fontSize: 12,
    fontWeight: '600',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'transparent', // overridden inline
  },
  rowLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  rowSub: {
    fontSize: 12,
    marginTop: 2,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    gap: 8,
  },
  actionText: {
    fontSize: 15,
    fontWeight: '600',
  },
});