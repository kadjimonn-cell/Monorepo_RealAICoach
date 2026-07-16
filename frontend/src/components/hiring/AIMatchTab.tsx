// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, scoreColor } from './shared';

interface Props { C: HColors; }

export function AIMatchTab({ C }: Props) {
  const router = useRouter();
  const { data: aiJobsData, loading: aiJobsLoading } = useLiveQuery('/aris/match/jobs-for-me', { entity: 'ai_matches', pollInterval: 60000 });
  const aiJobs = aiJobsData?.jobs || [];
  const loading = aiJobsLoading;

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12, fontSize: 14 }}>AI is analyzing your profile against available jobs...</Text>
    </View>
  );

  return (
    <View data-testid="ai-match-tab" testID="ai-match-tab">
      {aiJobs.map((j, i) => (
        <View key={j.job_id} data-testid={`ai-job-${i}`} testID={`ai-job-${i}`} style={{
          backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
          borderWidth: 1, borderColor: C.border,
          borderLeftWidth: 3, borderLeftColor: j.match_score >= 75 ? C.success : j.match_score >= 50 ? C.warning : C.border,
        }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '600' }}>{j.title}</Text>
              <Text style={{ color: C.muted, fontSize: 12 }}>{j.company_name} - {j.location}</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={{ color: scoreColor(j.match_score || 0, C), fontSize: 22, fontWeight: '700' }}>{j.match_score || 0}%</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>match</Text>
            </View>
          </View>
          {j.match_reason && <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, fontStyle: 'italic' }}>{j.match_reason}</Text>}
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {j.remote && <Badge label="Remote" color={C.successText} bg={C.success + '22'} />}
            <Badge label={j.job_type?.replace('_', ' ') || 'N/A'} color={C.primary} bg={C.primary + '22'} />
            {j.growth_potential && <Badge label={`Growth: ${j.growth_potential}`} color={C.warningText} bg={C.warning + '22'} />}
          </View>
          <TouchableOpacity data-testid={`view-job-${j.job_id}`} testID={`view-job-${j.job_id}`} onPress={() => router.push(`/career?tab=discover&job=${j.job_id}`)}
            style={{ marginTop: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: C.accent, alignItems: 'center' }}>
            <Text style={{ color: C.primaryText || C.buttonText || C.text, fontSize: 13, fontWeight: '600' }}>View & Apply</Text>
          </TouchableOpacity>
        </View>
      ))}
      {!aiJobs.length && (
        <View style={{ alignItems: 'center', paddingVertical: 32 }}>
          <Ionicons name="search-outline" size={40} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 14, marginTop: 12 }}>Complete your profile to get AI job matches</Text>
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
