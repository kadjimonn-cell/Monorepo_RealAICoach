import React from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

const GRADE_COLORS: Record<string, string> = { A: C.green, B: 'var(--app-success)', C: C.yellow, D: 'var(--app-warning)', F: C.red };

function MiniRing({ score, grade }: { score: number; grade: string }) {
  const color = GRADE_COLORS[grade] || C.muted;
  const circ = 2 * Math.PI * 18;
  const offset = circ * (1 - score / 100);
  if (Platform.OS !== 'web') return <Text style={{ fontSize: 20, fontWeight: '900', color }}>{score}</Text>;
  return (
    <View style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}>
      <svg width="48" height="48" viewBox="0 0 48 48" style={{ position: 'absolute' } as any}>
        <circle cx="24" cy="24" r="18" fill="none" stroke={C.border} strokeWidth="4" />
        <circle cx="24" cy="24" r="18" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset} transform="rotate(-90 24 24)" />
      </svg>
      <Text style={{ fontSize: 13, fontWeight: '900', color }}>{grade}</Text>
    </View>
  );
}

export default function SecurityScoreWidget({ colors, onNavigate }: { colors: any; onNavigate?: () => void }) {
  const { data, loading } = useLiveQuery('/admin/security-posture/scan', { entity: 'security-posture-widget', pollInterval: 300000 });

  if (loading || !data) {
    return (
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.muted }} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.securityScoreWidget.auto.text.001', 'Security Posture')}</Text>
        </View>
        <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.securityScoreWidget.auto.text.002', 'Scanning...')}</Text>
      </View>
    );
  }

  const score = data.score || 0;
  const grade = data.grade || 'F';
  const color = GRADE_COLORS[grade] || C.muted;
  const threats = data.threat_summary || {};
  const totalThreats = (threats.waf_blocks_24h || 0) + (threats.login_failures_24h || 0) + (threats.bot_detections_24h || 0);
  const hardening = data.hardening || { active: 0, total: 0, checks: [] };

  return (
    <TouchableOpacity accessibilityLabel={tx('admin.securityScoreWidget.auto.accessibility.001', 'Open security posture details')}
      activeOpacity={0.8}
      onPress={onNavigate}
      style={{
        backgroundColor: C.card,
        borderRadius: 14,
        padding: 20,
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(color, '30'),
        ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
      }}
      data-testid="security-score-widget" testID="security-score-widget"
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-checkmark" size={18} color={color} />
          </View>
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.securityScoreWidget.auto.text.003', 'Security Posture')}</Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 1 }}>{data.total_checks} checks | {data.passed} passed</Text>
          </View>
        </View>
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '18'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
          <Text style={{ fontSize: 11, fontWeight: '700', color }} data-testid="security-score-widget-grade" testID="security-score-widget-grade">{score}/100</Text>
        </View>
      </View>

      {/* Metrics row */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <MiniRing score={score} grade={grade} />
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 4 }}>{tx('admin.securityScoreWidget.auto.text.004', 'Grade')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <Ionicons name="checkmark-circle" size={16} color={C.green} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: C.green, marginTop: 4 }}>{data.passed}</Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.securityScoreWidget.auto.text.005', 'Passed')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <Ionicons name="warning" size={16} color={(data.warnings || 0) > 0 ? C.yellow : C.green} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: (data.warnings || 0) > 0 ? C.yellow : C.green, marginTop: 4 }}>{data.warnings || 0}</Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.securityScoreWidget.auto.text.006', 'Warnings')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <Ionicons name="flash" size={16} color={totalThreats > 0 ? C.red : C.purple} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: totalThreats > 0 ? C.red : C.purple, marginTop: 4 }}>{totalThreats}</Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.securityScoreWidget.auto.text.007', 'Threats 24h')}</Text>
        </View>
      </View>

      {/* Hardening Shield */}
      {hardening.total > 0 && (
        <View style={{ marginTop: 12, backgroundColor: C.bg, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: hardening.active === hardening.total ? (globalThis as any).__alphaColor(C.green, '30') : C.yellow + '30' }} data-testid="hardening-shield-section" testID="hardening-shield-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="lock-closed" size={14} color={hardening.active === hardening.total ? C.green : C.yellow} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{tx('admin.securityScoreWidget.auto.text.008', 'Platform Hardening')}</Text>
            </View>
            <View style={{ backgroundColor: hardening.active === hardening.total ? (globalThis as any).__alphaColor(C.green, '18') : C.yellow + '18', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: hardening.active === hardening.total ? C.green : C.yellow }} data-testid="hardening-shield-count" testID="hardening-shield-count">{hardening.active}/{hardening.total}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
            {hardening.checks.map((check: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: check.status === 'pass' ? (globalThis as any).__alphaColor(C.green, '10') : C.red + '10', paddingHorizontal: 6, paddingVertical: 3, borderRadius: 5 }}>
                <Ionicons name={check.status === 'pass' ? 'checkmark-circle' : 'close-circle'} size={10} color={check.status === 'pass' ? C.green : C.red} />
                <Text style={{ fontSize: 9, color: check.status === 'pass' ? C.green : C.red, fontWeight: '600' }}>{check.name.replace('(', '').replace(')', '').split(' ').slice(0, 3).join(' ')}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {onNavigate && (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: 12, gap: 4 }}>
          <Text style={{ fontSize: 11, color: C.blue, fontWeight: '600' }}>{tx('admin.securityScoreWidget.auto.text.009', 'View Details')}</Text>
          <Ionicons name="chevron-forward" size={12} color={C.blue} />
        </View>
      )}
    </TouchableOpacity>
  );
}

/* i18n-probe t('i18n.auto.probe') */
