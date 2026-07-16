import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  surfaceName: string;
  missingKeys: string[];
  colors: any;
}

export default function GpsLabelBlocker({ surfaceName, missingKeys, colors }: Props) {
  const router = useRouter();
  return (
    <View
      style={[styles.wrap, { backgroundColor: colors.bg, borderColor: colors.error || colors.error }]}
      data-testid={`gps-label-blocker-${surfaceName}`}
      testID={`gps-label-blocker-${surfaceName}`}
    >
      <Ionicons name="warning" size={22} color={colors.error || 'var(--app-error)'} />
      <Text style={[styles.title, { color: colors.text }]}>GPS label pack missing — surface blocked</Text>
      <Text style={[styles.body, { color: colors.textSec }]}>This page is in strict label-required mode.</Text>
      <Text style={[styles.body, { color: colors.textSec }]}>Missing keys:</Text>
      <Text style={[styles.keys, { color: colors.textMuted }]}>{missingKeys.join(', ')}</Text>

      <TouchableOpacity
        style={[styles.btn, { backgroundColor: colors.primary }]}
        onPress={() => router.push('/admin-console?category=operations&tab=gps-state-management')}
        data-testid={`gps-label-blocker-open-control-center-${surfaceName}`}
        testID={`gps-label-blocker-open-control-center-${surfaceName}`}
      >
        <Text style={[styles.btnText, { color: colors.primaryText }]}>Open GPS Control Center</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    margin: 16,
    borderRadius: 16,
    borderWidth: 1,
    padding: 16,
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '800',
  },
  body: {
    fontSize: 13,
  },
  keys: {
    fontSize: 12,
    lineHeight: 18,
  },
  btn: {
    marginTop: 8,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignSelf: 'flex-start',
  },
  btnText: {
    fontSize: 12,
    fontWeight: '800',
  },
});

/* i18n-probe t('i18n.auto.probe') */
