import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, ScoreBar, scoreColor } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; myJobs: any[]; selectedJobId: string; onSelectJob: (id: string) => void; }

export function RankingsTab({ C, myJobs, selectedJobId, onSelectJob }: Props) {
  const [selectedPipelines, setSelectedPipelines] = useState<string[]>([]);
  const [comparison, setComparison] = useState<any>(null);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: rankings, loading: _rankLoading } = useLiveQuery(
    selectedJobId ? `/aris/copilot/rankings/${selectedJobId}` : '',
    { entity: 'rankings', pollInterval: 60000, deps: [selectedJobId] }
  );
  const [loading, setLoading] = useState(false);

  const compareCandidates = async () => {
    if (selectedPipelines.length < 2) return;
    setLoading(true);
    try {
      const res = await api.get(`/aris/copilot/compare?ids=${selectedPipelines.join(',')}`);
      setComparison(res.data?.comparison || null);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/RankingsTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setLoading(false);
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
    <View data-testid="rankings-tab" testID="rankings-tab">
      <JobSelector />
      {loading ? (
        <ActivityIndicator size="large" color={C.accent} style={{ marginTop: 40 }} />
      ) : rankings ? (
        <View>
          {rankings.insight && (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), borderRadius: 12, padding: 14, marginBottom: 16, borderLeftWidth: 3, borderLeftColor: C.accent }}>
              <Text style={{ color: C.text, fontSize: 13, lineHeight: 20 }}>
                <Text style={{ fontWeight: '700' }}>AI Insight: </Text>{rankings.insight}
              </Text>
            </View>
          )}
          {(rankings.rankings || []).map((r: any, i: number) => (
            <View key={r.pipeline_id} data-testid={`ranking-${i}`} testID={`ranking-${i}`} style={{
              backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
              borderWidth: 1, borderColor: i === 0 ? C.success : C.border,
              borderLeftWidth: 3, borderLeftColor: i === 0 ? C.success : i === 1 ? C.warning : C.border,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                <View style={{
                  width: 28, height: 28, borderRadius: 14, backgroundColor: i === 0 ? C.success : i === 1 ? C.warning : C.border,
                  alignItems: 'center', justifyContent: 'center', marginRight: 10,
                }}>
                  <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '700' }}>#{i + 1}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '600' }}>{r.candidate_name}</Text>
                  <Text style={{ color: C.muted, fontSize: 11 }}>{r.stage_label}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: scoreColor(r.hire_confidence, C), fontSize: 20, fontWeight: '700' }}>{r.hire_confidence}%</Text>
                  <Badge
                    label={r.decision?.replace('_', ' ') || 'pending'}
                    color={r.decision === 'strong_hire' ? C.success : r.decision === 'hire' ? C.primary : C.warning}
                    bg={(r.decision === 'strong_hire' ? C.success : r.decision === 'hire' ? C.primary : C.warning) + '22'}
                  />
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <ScoreBar score={r.skill_match_pct || 0} label="Skills" color={C.primary} C={C} />
                <ScoreBar score={r.culture_compatibility || 0} label="Culture" color={C.accent} C={C} />
                <ScoreBar score={r.resume_relevance || 0} label="Resume" color={C.warningText} C={C} />
              </View>
              {r.reasoning && <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, fontStyle: 'italic' }}>{r.reasoning}</Text>}
              <TouchableOpacity data-testid={`select-compare-${r.pipeline_id}`} testID={`select-compare-${r.pipeline_id}`}
                onPress={() => setSelectedPipelines(prev => prev.includes(r.pipeline_id) ? prev.filter(id => id !== r.pipeline_id) : [...prev, r.pipeline_id])}
                style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8, paddingVertical: 4 }}>
                <Ionicons name={selectedPipelines.includes(r.pipeline_id) ? 'checkbox' : 'square-outline'} size={18} color={C.accent} />
                <Text style={{ color: C.muted, fontSize: 12, marginLeft: 6 }}>Select for comparison</Text>
              </TouchableOpacity>
            </View>
          ))}
          {selectedPipelines.length >= 2 && (
            <TouchableOpacity data-testid="compare-candidates-btn" testID="compare-candidates-btn" onPress={compareCandidates}
              style={{ backgroundColor: C.accent, padding: 14, borderRadius: 12, alignItems: 'center', marginTop: 8 }}>
              <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>Compare {selectedPipelines.length} Candidates</Text>
            </TouchableOpacity>
          )}
          {comparison && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: C.accent }}>
              <Text style={{ color: C.accent, fontSize: 16, fontWeight: '700', marginBottom: 8 }}>AI Comparison</Text>
              {comparison.winner && <Text style={{ color: C.successText, fontSize: 14, fontWeight: '600', marginBottom: 8 }}>Recommended: {comparison.winner}</Text>}
              {comparison.recommendation && <Text style={{ color: C.text, fontSize: 13, marginBottom: 8 }}>{comparison.recommendation}</Text>}
              {comparison.trade_offs?.map((t: string, i: number) => (
                <Text key={i} style={{ color: C.muted, fontSize: 12, marginLeft: 8 }}>- {t}</Text>
              ))}
            </View>
          )}
        </View>
      ) : (
        <Text style={{ color: C.muted, textAlign: 'center', paddingVertical: 32 }}>Select a job to see AI rankings</Text>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
