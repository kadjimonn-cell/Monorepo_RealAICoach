import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, scoreColor } from './shared';

interface Props { C: HColors; jobId: string; }

export function PredictiveTimeline({ C, jobId }: Props) {
  const ON_ACCENT = 'rgb(255,255,255)';
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, loading: dataLoading } = useLiveQuery(
    jobId ? `/aris/predict-timeline/${jobId}` : '',
    { entity: 'predictive', pollInterval: 60000, deps: [jobId] }
  );
  const { data: globalData } = useLiveQuery('/aris/predict-timeline/global', { entity: 'predictive', pollInterval: 60000 });
  const loading = dataLoading;

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 20 }}>
      <ActivityIndicator size="small" color={C.accent} />
      <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>Loading timeline predictions...</Text>
    </View>
  );

  if (!data?.candidates?.length) return (
    <View data-testid="predictive-timeline-empty" testID="predictive-timeline-empty" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
      <Ionicons name="time-outline" size={32} color={C.muted} />
      <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>No pipeline data to predict timelines</Text>
    </View>
  );

  const statusColor = (s: string) => {
    if (s === 'completed') return C.success;
    if (s === 'in_progress') return C.accent;
    return C.border;
  };

  return (
    <View data-testid="predictive-timeline" testID="predictive-timeline">
      {/* Global avg bar */}
      {globalData && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="timer-outline" size={16} color={C.accent} />
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>Avg Time-to-Hire</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Text style={{ color: C.accent, fontSize: 16, fontWeight: '700' }}>{globalData.total_label}</Text>
              <Badge label={`${globalData.confidence} confidence`}
                color={globalData.confidence === 'high' ? C.success : globalData.confidence === 'medium' ? C.warning : C.muted}
                bg={(globalData.confidence === 'high' ? C.success : globalData.confidence === 'medium' ? C.warning : C.muted) + '22'} />
            </View>
          </View>
          <View style={{ flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', gap: 1 }}>
            {globalData.stages.map((s: any) => (
              <View key={s.stage} style={{
                flex: s.pct_of_total, height: 8, borderRadius: 2,
                backgroundColor: `hsl(${240 + (globalData.stages.indexOf(s) * 15)}, 70%, 60%)`,
              }} />
            ))}
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {globalData.stages.map((s: any, i: number) => (
              <Text key={s.stage} style={{ color: C.muted, fontSize: 10 }}>
                {s.label.split(' ').slice(-1)}: {s.duration_label}
              </Text>
            ))}
          </View>
        </View>
      )}

      {/* Per-candidate timelines */}
      {data.candidates.map((cand: any) => (
        <TouchableOpacity key={cand.pipeline_id} data-testid={`timeline-${cand.pipeline_id}`} testID={`timeline-${cand.pipeline_id}`}
          onPress={() => setExpanded(expanded === cand.pipeline_id ? null : cand.pipeline_id)}
          activeOpacity={0.8}
          style={{
            backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
            borderWidth: 1, borderColor: expanded === cand.pipeline_id ? C.accent : C.border,
          }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>{cand.candidate_name}</Text>
              <Text style={{ color: C.muted, fontSize: 11 }}>{cand.current_stage_label}</Text>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text style={{ color: C.accent, fontSize: 16, fontWeight: '700' }}>{cand.progress_pct}%</Text>
              {cand.hire_confidence != null && (
                <Text style={{ color: scoreColor(cand.hire_confidence, C), fontSize: 11 }}>
                  Conf: {cand.hire_confidence}%
                </Text>
              )}
            </View>
          </View>

          {/* Progress bar */}
          <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, marginBottom: 8 }}>
            <View style={{ height: 6, backgroundColor: C.accent, borderRadius: 3, width: `${cand.progress_pct}%` }} />
          </View>

          {/* Time metrics */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View style={{ alignItems: 'center' }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{cand.elapsed_label}</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>Elapsed</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={{ color: C.warningText, fontSize: 13, fontWeight: '600' }}>{cand.remaining_label}</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>Remaining</Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Text style={{ color: C.primary, fontSize: 13, fontWeight: '600' }}>{cand.estimated_total_label}</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>Est. Total</Text>
            </View>
          </View>

          {/* Expanded stage detail */}
          {expanded === cand.pipeline_id && (
            <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border }}>
              {cand.timeline.map((stage: any, i: number) => (
                <View key={stage.stage} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                  <View style={{
                    width: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: statusColor(stage.status),
                  }}>
                    {stage.status === 'completed' ? (
                      <Ionicons name="checkmark" size={12} color={ON_ACCENT} />
                    ) : stage.status === 'in_progress' ? (
                      <Ionicons name="ellipsis-horizontal" size={10} color={ON_ACCENT} />
                    ) : (
                      <Text style={{ color: ON_ACCENT, fontSize: 8, fontWeight: '700' }}>{i + 1}</Text>
                    )}
                  </View>
                  {i < cand.timeline.length - 1 && (
                    <View style={{ position: 'absolute', left: 9, top: 20, width: 2, height: 12, backgroundColor: C.border, zIndex: -1 }} />
                  )}
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ color: stage.status === 'predicted' ? C.muted : C.text, fontSize: 12, fontWeight: '500' }}>
                        {stage.label}
                      </Text>
                      <Text style={{
                        color: stage.status === 'completed' ? C.success : stage.status === 'in_progress' ? C.accent : C.muted,
                        fontSize: 11, fontWeight: '600',
                      }}>
                        {stage.duration_label}
                        {stage.status === 'predicted' && ' (est)'}
                      </Text>
                    </View>
                  </View>
                </View>
              ))}
            </View>
          )}
        </TouchableOpacity>
      ))}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
