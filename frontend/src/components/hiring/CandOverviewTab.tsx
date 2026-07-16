// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useRouter } from 'expo-router';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, MetricCard, Badge } from './shared';

interface Props { C: HColors; onSwitchTab: (tab: string) => void; }

export function CandOverviewTab({ C, onSwitchTab }: Props) {
  const { data: candDash } = useLiveQuery('/aris/dashboard/candidate', { entity: 'candidate', pollInterval: 60000 });

  if (!candDash) return <ActivityIndicator size="large" color={C.accent} style={{ marginTop: 40 }} />;
  return (
    <View data-testid="candidate-overview" testID="candidate-overview">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <MetricCard C={C} icon="document-text-outline" label="Applications" value={candDash.total_applications} color={C.primary} />
        <MetricCard C={C} icon="chatbubbles-outline" label="Interview Rate" value={`${candDash.interview_rate}%`} color={C.successText} />
        <MetricCard C={C} icon="star-outline" label="Resume Score" value={candDash.resume_score || 0} color={C.warningText} />
        <MetricCard C={C} icon="notifications-outline" label="Alerts" value={candDash.unread_alerts} color={C.error} />
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 12 }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 8 }}>Your Skills</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {(candDash.skills || []).map((s: string) => <Badge key={s} label={s} color={C.accent} bg={C.accent + '22'} />)}
          {!(candDash.skills || []).length && <Text style={{ color: C.muted, fontSize: 13 }}>Update your profile to add skills</Text>}
        </View>
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 8 }}>Application Status</Text>
        {Object.entries(candDash.application_statuses || {}).map(([k, v]) => (
          <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 13, textTransform: 'capitalize' }}>{k}</Text>
            <Text style={{ color: C.accent, fontWeight: '600', fontSize: 13 }}>{String(v)}</Text>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
        <TouchableOpacity data-testid="quick-ai-match" testID="quick-ai-match" onPress={() => onSwitchTab('ai-match')}
          style={{ flex: 1, backgroundColor: C.accent, padding: 14, borderRadius: 12, alignItems: 'center' }}>
          <Ionicons name="flash" size={20} color={C.primaryText} />
          <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '600', marginTop: 4 }}>Find AI Matches</Text>
        </TouchableOpacity>
        <TouchableOpacity data-testid="quick-career-coach" testID="quick-career-coach" onPress={() => onSwitchTab('career-coach')}
          style={{ flex: 1, backgroundColor: C.primary, padding: 14, borderRadius: 12, alignItems: 'center' }}>
          <Ionicons name="school" size={20} color={C.primaryText} />
          <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '600', marginTop: 4 }}>Career Coach</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
