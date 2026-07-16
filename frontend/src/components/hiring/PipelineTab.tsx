import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, ScoreBar, StageIndicator, scoreColor } from './shared';
import { PredictiveTimeline } from './PredictiveTimeline';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; isWide: boolean; myJobs: any[]; selectedJobId: string; onSelectJob: (id: string) => void; }

export function PipelineTab({ C, isWide, myJobs, selectedJobId, onSelectJob }: Props) {
  const [pipelineDetail, setPipelineDetail] = useState<any>(null);
  const [advancing, setAdvancing] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);

  const { data: pipelineData, refetch: load } = useLiveQuery(
    selectedJobId ? `/aris/pipeline/job/${selectedJobId}` : '',
    { entity: 'pipelines', pollInterval: 30000, deps: [selectedJobId] }
  );
  const pipelines = pipelineData?.pipelines || [];

  const advancePipeline = async (pipelineId: string, auto = false) => {
    setAdvancing(true);
    try {
      const url = auto ? `/aris/pipeline/${pipelineId}/auto-advance` : `/aris/pipeline/${pipelineId}/advance`;
      const res = await api.post(url);
      if (res.data?.pipeline) {
        setPipelineDetail(res.data.pipeline);
        load();
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/PipelineTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAdvancing(false);
  };

  const JobSelector = () => (
    <ScrollView data-testid="job-selector" testID="job-selector" horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
      {myJobs.map(j => (
        <TouchableOpacity key={j.job_id} data-testid={`job-select-${j.job_id}`} testID={`job-select-${j.job_id}`}
          onPress={() => onSelectJob(j.job_id)}
          style={{
            paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginRight: 8,
            backgroundColor: selectedJobId === j.job_id ? C.primary : C.card,
            borderWidth: 1, borderColor: selectedJobId === j.job_id ? C.primary : C.border,
          }}>
          <Text style={{ color: selectedJobId === j.job_id ? C.primaryText : C.text, fontSize: 12, fontWeight: '500' }}>
            {j.title} ({j.applications_count || 0})
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  return (
    <View data-testid="pipeline-tab" testID="pipeline-tab">
      <JobSelector />
      {!selectedJobId ? (
        <Text style={{ color: C.muted, textAlign: 'center', paddingVertical: 32 }}>Select a job to view pipeline</Text>
      ) : (
        <View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>Hiring Pipeline ({pipelines.length})</Text>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity data-testid="toggle-timeline" testID="toggle-timeline" onPress={() => setShowTimeline(!showTimeline)}
                style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: showTimeline ? C.accent : C.card, borderWidth: 1, borderColor: showTimeline ? C.accent : C.border }}>
                <Text style={{ color: showTimeline ? C.primaryText : C.text, fontSize: 12 }}>Timeline</Text>
              </TouchableOpacity>
              <TouchableOpacity data-testid="refresh-pipelines" testID="refresh-pipelines" onPress={load}
                style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: C.accent }}>
                <Text style={{ color: C.primaryText, fontSize: 12 }}>Refresh</Text>
              </TouchableOpacity>
            </View>
          </View>
          {showTimeline && (
            <PredictiveTimeline C={C} jobId={selectedJobId} />
          )}
          {pipelines.length === 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 24, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="git-branch-outline" size={40} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 14, marginTop: 12, textAlign: 'center' }}>
                No candidates in pipeline for this job yet.{'\n'}Applicants are auto-processed when they apply.
              </Text>
            </View>
          )}
          {pipelines.map(p => (
            <TouchableOpacity key={p.pipeline_id} data-testid={`pipeline-card-${p.pipeline_id}`} testID={`pipeline-card-${p.pipeline_id}`}
              onPress={() => setPipelineDetail(pipelineDetail?.pipeline_id === p.pipeline_id ? null : p)}
              style={{
                backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
                borderWidth: 1, borderColor: pipelineDetail?.pipeline_id === p.pipeline_id ? C.accent : C.border,
              }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '600' }}>{p.candidate_name || 'Unknown'}</Text>
                  <Text style={{ color: C.muted, fontSize: 12 }}>{p.candidate_email}</Text>
                </View>
                <Badge
                  label={p.prediction?.decision || p.current_stage?.replace(/_/g, ' ') || 'pending'}
                  color={p.prediction?.decision === 'strong_hire' ? C.success : p.prediction?.decision === 'pass' ? C.error : C.accent}
                  bg={p.prediction?.decision === 'strong_hire' ? C.success + '22' : p.prediction?.decision === 'pass' ? C.error + '22' : C.accent + '22'}
                />
              </View>
              <StageIndicator stage={p.current_stage} C={C} isWide={isWide} />
              {p.prediction && (
                <View style={{ flexDirection: 'row', gap: 12, marginTop: 8 }}>
                  <Text style={{ color: scoreColor(p.prediction.hire_confidence || 0, C), fontSize: 12, fontWeight: '600' }}>
                    Confidence: {p.prediction.hire_confidence}%
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 12 }}>Risk: {p.prediction.performance_risk || 'N/A'}</Text>
                </View>
              )}
              {pipelineDetail?.pipeline_id === p.pipeline_id && (
                <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border }}>
                  {Object.entries(p.ai_scores || {}).map(([stage, scores]: [string, any]) => (
                    <View key={stage} style={{ marginBottom: 8 }}>
                      <Text style={{ color: C.accent, fontSize: 12, fontWeight: '600', marginBottom: 4, textTransform: 'capitalize' }}>
                        {stage.replace(/_/g, ' ')}
                      </Text>
                      {typeof scores === 'object' && !scores.error && Object.entries(scores).filter(([k]) => typeof scores[k] === 'number').slice(0, 4).map(([k, v]) => (
                        <ScoreBar key={k} label={k.replace(/_/g, ' ')} score={Number(v)} color={scoreColor(Number(v), C)} C={C} />
                      ))}
                    </View>
                  ))}
                  {p.prediction?.reasoning && (
                    <Text style={{ color: C.muted, fontSize: 12, fontStyle: 'italic', marginTop: 8 }}>{p.prediction.reasoning}</Text>
                  )}
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                    <TouchableOpacity data-testid={`advance-${p.pipeline_id}`} testID={`advance-${p.pipeline_id}`}
                      onPress={() => advancePipeline(p.pipeline_id)} disabled={advancing}
                      style={{ flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: C.primary, alignItems: 'center' }}>
                      <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '600' }}>{advancing ? 'Processing...' : 'Next Stage'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity data-testid={`auto-advance-${p.pipeline_id}`} testID={`auto-advance-${p.pipeline_id}`}
                      onPress={() => advancePipeline(p.pipeline_id, true)} disabled={advancing}
                      style={{ flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: C.accent, alignItems: 'center' }}>
                      <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '600' }}>{advancing ? 'AI Working...' : 'Full AI Analysis'}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
