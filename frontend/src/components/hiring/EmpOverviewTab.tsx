import React, { useEffect } from 'react';
import { View, Text } from 'react-native';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, MetricCard } from './shared';

interface Props { C: HColors; onJobsLoaded: (jobs: any[]) => void; }

export function EmpOverviewTab({ C, onJobsLoaded }: Props) {
  const { data: empDash } = useLiveQuery('/aris/dashboard/employer', { entity: 'employer', pollInterval: 60000 });
  const { data: jobsRes } = useLiveQuery('/jobs/my-posted', { entity: 'jobs', pollInterval: 60000 });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (empDash || jobsRes) onJobsLoaded(empDash?.jobs || jobsRes?.jobs || []); }, [empDash, jobsRes]);

  if (!empDash) return null;
  return (
    <View data-testid="employer-overview" testID="employer-overview">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <MetricCard C={C} icon="briefcase-outline" label="Active Jobs" value={empDash.active_jobs} color={C.accent} />
        <MetricCard C={C} icon="people-outline" label="Applications" value={empDash.total_applications} color={C.primary} />
        <MetricCard C={C} icon="git-branch-outline" label="In Pipeline" value={empDash.total_pipelines} color={C.successText} />
        <MetricCard C={C} icon="analytics-outline" label="Avg Confidence" value={`${empDash.avg_hire_confidence}%`} color={C.warningText} />
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>AI Decision Summary</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {Object.entries(empDash.decision_breakdown || {}).map(([k, v]) => (
            <View key={k} style={{ alignItems: 'center', minWidth: 70 }}>
              <Text style={{ color: k === 'strong_hire' ? C.success : k === 'hire' ? C.primary : k === 'maybe' ? C.warning : C.error, fontSize: 22, fontWeight: '700' }}>{String(v)}</Text>
              <Text style={{ color: C.muted, fontSize: 11, textTransform: 'capitalize' }}>{k.replace('_', ' ')}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>Pipeline Stages</Text>
        {Object.entries(empDash.stage_breakdown || {}).map(([k, v]) => (
          <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 13, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</Text>
            <Text style={{ color: C.accent, fontSize: 13, fontWeight: '600' }}>{String(v)}</Text>
          </View>
        ))}
        {!Object.keys(empDash.stage_breakdown || {}).length && (
          <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', paddingVertical: 16 }}>
            No candidates in pipeline yet. Go to Pipeline tab to process applicants.
          </Text>
        )}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
