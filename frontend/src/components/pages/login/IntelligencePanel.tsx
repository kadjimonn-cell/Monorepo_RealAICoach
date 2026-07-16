import React, { useMemo } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../../context/ThemeContext';

/**
 * Static branding panel for the login page (desktop right side).
 * Shows enterprise capabilities — NO live data, NO API calls.
 * This replaces the old IntelligencePanel that leaked real system metrics.
 */
export const IntelligencePanel = () => {
  const { _darkMode, colors } = useTheme();
  const T = useMemo(() => ({
    bg: colors.bg,
    text: colors.text,
    text3: colors.textMuted,
    cyan: colors.accent,
    success: colors.success,
    purple: colors.purple,
    warning: colors.warning,
    teal: colors.accent,
    glassBorder: colors.glassBorder,
    glassSurface: colors.glassSurface,
    // WCAG-AA icon color variants — required for contrast against dark panel.
    // Missing keys here left Ionicons with `color={undefined}` → invisible
    // icons on Enterprise Security / Team Intelligence / Smart Automations
    // rows. Defaults fall back to the base color for older themes.
    successText: colors.successText || colors.success,
    purpleText: colors.purpleText || colors.purple,
    warningText: colors.warningText || colors.warning,
  }), [colors]);
  const st = useMemo(() => makeStyles(T), [T]);

  const capabilities = [
    { icon: 'analytics-outline' as const, label: 'AI Performance Analytics', desc: 'Real-time coaching insights', color: T.cyan },
    { icon: 'shield-checkmark-outline' as const, label: 'Enterprise Security', desc: 'SOC 2 compliant infrastructure', color: T.successText },
    { icon: 'people-outline' as const, label: 'Team Intelligence', desc: 'Collaborative growth tracking', color: T.purpleText },
    { icon: 'flash-outline' as const, label: 'Smart Automations', desc: 'Live AI-driven coaching tools', color: T.warningText },
    { icon: 'globe-outline' as const, label: 'Global Platform', desc: 'Multi-language, multi-currency', color: T.teal },
  ];

  const stats = [
    { value: '99.9%', label: 'Uptime SLA' },
    { value: 'Live', label: 'AI Tools' },
    { value: '<50ms', label: 'Avg Latency' },
    { value: '256-bit', label: 'Encryption' },
  ];

  return (
    <View style={st.panel} data-testid="intel-panel" testID="intel-panel">
      {Platform.OS === 'web' && (
        <div style={{ position: 'absolute', inset: 0, opacity: 0.03, backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)', backgroundSize: '40px 40px', pointerEvents: 'none' as any, zIndex: 2 }} />
      )}

      {/* Header */}
      <View style={st.header}>
        <View style={st.statusDot} />
        <Text style={st.headerLabel}>ENTERPRISE AI PLATFORM</Text>
      </View>

      {/* Capability Cards */}
      <View style={st.capList}>
        {capabilities.map((cap, i) => (
          <View key={i} style={st.capCard}>
            <View style={[st.capIcon, { backgroundColor: (globalThis as any).__alphaColor(cap.color, '18') }]}>
              <Ionicons name={cap.icon} size={18} color={cap.color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={st.capTitle}>{cap.label}</Text>
              <Text style={st.capDesc}>{cap.desc}</Text>
            </View>
          </View>
        ))}
      </View>

      {/* Stats Grid */}
      <View style={st.statsGrid}>
        {stats.map((s, i) => (
          <View key={i} style={st.statCard}>
            <Text style={st.statValue}>{s.value}</Text>
            <Text style={st.statLabel}>{s.label}</Text>
          </View>
        ))}
      </View>

      {/* Footer */}
      <View style={st.footer}>
        <Ionicons name="shield-checkmark" size={13} color={T.successText} />
        <Text style={st.footerText}>Enterprise Security  ·  ISO 27001  ·  GDPR Compliant</Text>
      </View>
    </View>
  );
};

function makeStyles(T: { bg: string; text: string; text3: string; cyan: string; success: string; glassBorder: string; glassSurface: string }) {
  return StyleSheet.create({
    panel: {
      flex: 1,
      backgroundColor: T.bg,
      padding: 32,
      justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      marginBottom: 28,
    },
    statusDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: T.success,
    },
    headerLabel: {
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.5,
      color: T.text3,
    },
    capList: {
      gap: 10,
      marginBottom: 28,
    },
    capCard: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 14,
      padding: 14,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: T.glassBorder,
      backgroundColor: T.glassSurface,
    },
    capIcon: {
      width: 40,
      height: 40,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
    },
    capTitle: {
      fontSize: 13,
      fontWeight: '700',
      color: T.text,
    },
    capDesc: {
      fontSize: 11,
      color: T.text3,
      marginTop: 2,
    },
    statsGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
      marginBottom: 24,
    },
    statCard: {
      flex: 1,
      minWidth: '40%' as any,
      padding: 14,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: T.glassBorder,
      backgroundColor: T.glassSurface,
      alignItems: 'center',
    },
    statValue: {
      fontSize: 18,
      fontWeight: '800',
      color: T.cyan,
    },
    statLabel: {
      fontSize: 10,
      fontWeight: '600',
      color: T.text3,
      marginTop: 4,
      letterSpacing: 0.5,
    },
    footer: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
    },
    footerText: {
      fontSize: 11,
      fontWeight: '600',
      color: T.text3,
    },
  });
}

/* i18n-probe t('i18n.auto.probe') */
