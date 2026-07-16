import React from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export type HColors = {
  bg: string; card: string; text: string; muted: string;
  border: string; primary: string; success: string;
  warning: string; error: string; accent: string;
  bgSoft: string;
};

export const scoreColor = (s: number, C: HColors) =>
  s >= 75 ? C.success : s >= 50 ? C.warning : C.error;

export const Badge = ({ label, color, bg }: { label: string; color: string; bg: string }) => (
  <View style={{ backgroundColor: bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 }}>
    <Text style={{ color, fontSize: 11, fontWeight: '600' }}>{label}</Text>
  </View>
);

export const MetricCard = ({ icon, label, value, color, C }: { icon: string; label: string; value: string | number; color: string; C: HColors }) => (
  <View data-testid={`metric-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`metric-${label.toLowerCase().replace(/\s/g, '-')}`} style={{
    backgroundColor: C.card, borderRadius: 12, padding: 16, flex: 1, minWidth: 140,
    borderWidth: 1, borderColor: C.border,
  }}>
    <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
      <Ionicons name={icon as any} size={18} color={color} />
      <Text style={{ color: C.muted, fontSize: 12, marginLeft: 6 }}>{label}</Text>
    </View>
    <Text style={{ color: C.text, fontSize: 24, fontWeight: '700' }}>{value}</Text>
  </View>
);

export const ScoreBar = ({ score, label, color, C }: { score: number; label: string; color: string; C: HColors }) => (
  <View style={{ marginBottom: 10 }}>
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
      <Text style={{ color: C.text, fontSize: 13 }}>{label}</Text>
      <Text style={{ color, fontSize: 13, fontWeight: '700' }}>{score}%</Text>
    </View>
    <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
      <View style={{ height: 6, backgroundColor: color, borderRadius: 3, width: `${Math.min(score, 100)}%` }} />
    </View>
  </View>
);

export const StageIndicator = ({ stage, C, isWide }: { stage: string; C: HColors; isWide: boolean }) => {
  const stages = [
    'application_received', 'ai_screening', 'skill_validation', 'interview_readiness',
    'interview_scheduling', 'interview_analysis', 'hiring_prediction', 'offer_recommendation',
  ];
  const idx = stages.indexOf(stage);
  return (
    <View data-testid="pipeline-stage-indicator" testID="pipeline-stage-indicator" style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
      {stages.map((s, i) => (
        <View key={s} style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={{
            width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
            backgroundColor: i <= idx ? C.accent : C.border,
          }}>
            {i < idx ? (
              <Ionicons name="checkmark" size={14} color="var(--app-primary-text)" />
            ) : (
              <Text style={{ color: i === idx ? 'var(--app-primary-text)' : C.muted, fontSize: 10, fontWeight: '700' }}>{i + 1}</Text>
            )}
          </View>
          {i < stages.length - 1 && (
            <View style={{ width: isWide ? 16 : 6, height: 2, backgroundColor: i < idx ? C.accent : C.border }} />
          )}
        </View>
      ))}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
