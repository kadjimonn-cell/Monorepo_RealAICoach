// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, MetricCard } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; }

export function AdminAIOversightTab({ C }: Props) {
  const { data: aiOversight, refetch: refetchOversight } = useLiveQuery('/smart-scheduler/admin/ai-oversight', { entity: 'ai_oversight', pollInterval: 30000 });

  const triggerAutomation = async (task: string) => {
    try {
      await api.post(`/smart-scheduler/admin/trigger-automation/${task}`);
      await refetchOversight();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/AdminAIOversightTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (!aiOversight) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>Loading AI Oversight...</Text>
    </View>
  );

  const ov = aiOversight.ai_overview || {};
  const ce = aiOversight.candidate_engagement || {};
  const im = aiOversight.interview_metrics || {};
  const funnel = aiOversight.hiring_funnel || {};
  const auto = aiOversight.automation || {};
  const empAct = aiOversight.employer_activity?.top_employers || [];

  return (
    <View data-testid="admin-ai-oversight" testID="admin-ai-oversight">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <MetricCard C={C} icon="git-branch-outline" label="Active Pipelines" value={ov.active_pipelines} color={C.accent} />
        <MetricCard C={C} icon="checkmark-done-outline" label="Completed" value={ov.completed_pipelines} color={C.successText} />
        <MetricCard C={C} icon="analytics-outline" label="Avg Confidence" value={`${ov.avg_hire_confidence}%`} color={C.warningText} />
        <MetricCard C={C} icon="alert-circle-outline" label="Stale Pipelines" value={ov.stale_pipelines} color={C.error} />
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>AI Decision Distribution</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {Object.entries(ov.ai_decisions || {}).map(([k, v]) => (
            <View key={k} style={{ alignItems: 'center', minWidth: 70 }}>
              <Text style={{ color: k === 'strong_hire' ? C.success : k === 'hire' ? C.primary : k === 'maybe' ? C.warning : C.error, fontSize: 22, fontWeight: '700' }}>{String(v)}</Text>
              <Text style={{ color: C.muted, fontSize: 11, textTransform: 'capitalize' }}>{k.replace('_', ' ')}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Hiring Funnel</Text>
        {['applications', 'screened', 'interviewed', 'offered', 'hired'].map((stage) => {
          const val = (funnel as any)[stage] || 0;
          const maxVal = Math.max(funnel.applications || 1, 1);
          return (
            <View key={stage} style={{ marginBottom: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                <Text style={{ color: C.text, fontSize: 13, textTransform: 'capitalize' }}>{stage}</Text>
                <Text style={{ color: C.accent, fontSize: 13, fontWeight: '700' }}>{val}</Text>
              </View>
              <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
                <View style={{ height: 6, backgroundColor: C.accent, borderRadius: 3, width: `${Math.min((val / maxVal) * 100, 100)}%` }} />
              </View>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <MetricCard C={C} icon="videocam-outline" label="Total Interviews" value={im.total} color={C.primary} />
        <MetricCard C={C} icon="checkmark-circle-outline" label="Completed" value={im.completed} color={C.successText} />
        <MetricCard C={C} icon="close-circle-outline" label="Cancelled" value={im.cancelled} color={C.error} />
        <MetricCard C={C} icon="flash-outline" label="Smart Scheduled" value={im.smart_scheduled} color={C.accent} />
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Candidate Engagement</Text>
        <View style={{ flexDirection: 'row', gap: 20 }}>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.accent, fontSize: 28, fontWeight: '700' }}>{ce.total_profiles}</Text>
            <Text style={{ color: C.muted, fontSize: 12 }}>Profiles</Text>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.successText, fontSize: 28, fontWeight: '700' }}>{ce.active_candidates}</Text>
            <Text style={{ color: C.muted, fontSize: 12 }}>Active</Text>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.warningText, fontSize: 28, fontWeight: '700' }}>{ce.engagement_rate}%</Text>
            <Text style={{ color: C.muted, fontSize: 12 }}>Engagement</Text>
          </View>
        </View>
      </View>
      {empAct.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Top Employers</Text>
          {empAct.map((e: any, i: number) => (
            <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <View>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '500' }}>{e.name}</Text>
                <Text style={{ color: C.muted, fontSize: 11 }}>{e.email}</Text>
              </View>
              <Text style={{ color: C.accent, fontSize: 13, fontWeight: '600' }}>{e.interviews} interviews</Text>
            </View>
          ))}
        </View>
      )}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Automation Controls</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[
            { key: 'interview_reminders', label: 'Send Reminders', icon: 'notifications-outline', color: C.primary },
            { key: 'daily_suggestions', label: 'Job Suggestions', icon: 'bulb-outline', color: C.warningText },
            { key: 'hiring_delays', label: 'Check Delays', icon: 'alert-outline', color: C.error },
            { key: 'new_candidates', label: 'Notify Employers', icon: 'people-outline', color: C.successText },
          ].map(btn => (
            <TouchableOpacity key={btn.key} data-testid={`trigger-${btn.key}`} testID={`trigger-${btn.key}`} onPress={() => triggerAutomation(btn.key)}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10,
                backgroundColor: (globalThis as any).__alphaColor(btn.color, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(btn.color, '44'),
              }}>
              <Ionicons name={btn.icon as any} size={16} color={btn.color} />
              <Text style={{ color: btn.color, fontSize: 12, fontWeight: '600' }}>{btn.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: auto.interview_reminders_active ? C.success : C.error }} />
            <Text style={{ color: C.muted, fontSize: 11 }}>Reminders</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: auto.hiring_delay_detection ? C.success : C.error }} />
            <Text style={{ color: C.muted, fontSize: 11 }}>Delay Detection</Text>
          </View>
          <Text style={{ color: C.muted, fontSize: 11 }}>Suggestions sent: {auto.daily_suggestions_sent || 0}</Text>
        </View>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
