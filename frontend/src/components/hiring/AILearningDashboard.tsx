import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Props = { C: any; isWide: boolean };

export const AILearningDashboard = ({ C, isWide }: Props) => {
  const [activeView, setActiveView] = useState<'accuracy' | 'calibration' | 'record'>('accuracy');
  const [outcomeForm, setOutcomeForm] = useState({ pipeline_id: '', outcome: 'hired', performance_rating: '', notes: '' });
  const [recording, setRecording] = useState(false);

  const { data: accuracy, loading: accLoading, refetch: refetchAcc } = useLiveQuery('/ai-learning/accuracy', { entity: 'ai_learning', pollInterval: 60000 });
  const { data: calibration, refetch: refetchCal } = useLiveQuery('/ai-learning/calibration', { entity: 'ai_learning', pollInterval: 60000 });
  const { data: insData, refetch: refetchIns } = useLiveQuery('/ai-learning/insights', { entity: 'ai_learning', pollInterval: 60000 });
  const insights = insData?.insights || [];
  const loading = accLoading;
  const load = useCallback(async () => { await Promise.all([refetchAcc(), refetchCal(), refetchIns()]); }, [refetchAcc, refetchCal, refetchIns]);

  const recordOutcome = async () => {
    if (!outcomeForm.pipeline_id || !outcomeForm.outcome) return;
    setRecording(true);
    try {
      await api.post('/ai-learning/record-outcome', {
        pipeline_id: outcomeForm.pipeline_id,
        outcome: outcomeForm.outcome,
        performance_rating: outcomeForm.performance_rating ? parseInt(outcomeForm.performance_rating) : undefined,
        notes: outcomeForm.notes,
      });
      setOutcomeForm({ pipeline_id: '', outcome: 'hired', performance_rating: '', notes: '' });
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/AILearningDashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setRecording(false);
  };

  const recalibrate = async () => {
    try {
      await api.post('/ai-learning/recalibrate');
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/AILearningDashboard.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>Loading AI learning data...</Text>
    </View>
  );

  return (
    <View data-testid="ai-learning-dashboard" testID="ai-learning-dashboard">
      {/* Tab Switcher */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {[
          { key: 'accuracy', label: 'Accuracy', icon: 'analytics-outline' },
          { key: 'calibration', label: 'Calibration', icon: 'speedometer-outline' },
          { key: 'record', label: 'Record Outcome', icon: 'add-circle-outline' },
        ].map(tab => (
          <TouchableOpacity key={tab.key} data-testid={`learning-tab-${tab.key}`} testID={`learning-tab-${tab.key}`}
            onPress={() => setActiveView(tab.key as any)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 4,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
              backgroundColor: activeView === tab.key ? C.accent : C.card,
              borderWidth: 1, borderColor: activeView === tab.key ? C.accent : C.border,
            }}>
            <Ionicons name={tab.icon as any} size={14} color={activeView === tab.key ? C.primaryText : C.muted} />
            <Text style={{ color: activeView === tab.key ? C.primaryText : C.muted, fontSize: 12, fontWeight: '600' }}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ACCURACY VIEW */}
      {activeView === 'accuracy' && accuracy && (
        <View>
          {accuracy.total_outcomes === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 24, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="school-outline" size={40} color={C.accent} />
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginTop: 12 }}>AI is Learning</Text>
              <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', marginTop: 8 }}>
                Record hiring outcomes to train the AI. Each outcome helps improve prediction accuracy.
              </Text>
              <TouchableOpacity data-testid="go-record-outcome" testID="go-record-outcome" onPress={() => setActiveView('record')}
                style={{ marginTop: 16, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10, backgroundColor: C.accent }}>
                <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '600' }}>Record First Outcome</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View>
              {/* Overall Accuracy */}
              <View style={{
                backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16,
                borderWidth: 1, borderColor: C.border, alignItems: 'center',
              }}>
                <Text style={{ color: C.muted, fontSize: 13, marginBottom: 8 }}>AI Prediction Accuracy</Text>
                <Text style={{
                  color: (accuracy.accuracy || 0) >= 70 ? C.successText : (accuracy.accuracy || 0) >= 50 ? C.warning : C.error,
                  fontSize: 40, fontWeight: '800',
                }}>{accuracy.accuracy != null ? `${accuracy.accuracy}%` : 'N/A'}</Text>
                <View style={{ flexDirection: 'row', gap: 16, marginTop: 12 }}>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: C.successText, fontSize: 20, fontWeight: '700' }}>{accuracy.correct}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>Correct</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: C.error, fontSize: 20, fontWeight: '700' }}>{accuracy.incorrect}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>Wrong</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: C.muted, fontSize: 20, fontWeight: '700' }}>{accuracy.neutral}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>Neutral</Text>
                  </View>
                </View>
              </View>

              {/* By Decision */}
              {Object.keys(accuracy.by_decision || {}).length > 0 && (
                <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Accuracy by Decision Type</Text>
                  {Object.entries(accuracy.by_decision).map(([dec, stats]: [string, any]) => (
                    <View key={dec} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
                      <Text style={{ color: C.text, fontSize: 13, textTransform: 'capitalize' }}>{dec.replace(/_/g, ' ')}</Text>
                      <View style={{ flexDirection: 'row', gap: 12 }}>
                        <Text style={{ color: C.muted, fontSize: 12 }}>{stats.total} total</Text>
                        <Text style={{
                          color: stats.accuracy != null ? (stats.accuracy >= 70 ? C.successText : stats.accuracy >= 50 ? C.warning : C.error) : C.muted,
                          fontSize: 12, fontWeight: '700',
                        }}>{stats.accuracy != null ? `${stats.accuracy}%` : '-'}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* Outcome Distribution */}
              {Object.keys(accuracy.outcome_distribution || {}).length > 0 && (
                <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Outcome Distribution</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                    {Object.entries(accuracy.outcome_distribution).map(([k, v]) => {
                      const oc = k === 'hired' ? C.successText : k === 'rejected' ? C.error : C.warning;
                      return (
                        <View key={k} style={{ alignItems: 'center', minWidth: 60 }}>
                          <Text style={{ color: oc, fontSize: 22, fontWeight: '700' }}>{String(v)}</Text>
                          <Text style={{ color: C.muted, fontSize: 10, textTransform: 'capitalize' }}>{k}</Text>
                        </View>
                      );
                    })}
                  </View>
                </View>
              )}

              {/* Performance & Retention */}
              <View style={{ flexDirection: 'row', gap: 10, marginBottom: 12 }}>
                {accuracy.performance?.avg_rating && (
                  <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                    <Text style={{ color: C.accent, fontSize: 24, fontWeight: '700' }}>{accuracy.performance.avg_rating}/10</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>Avg Performance</Text>
                  </View>
                )}
                {accuracy.retention?.avg_months && (
                  <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                    <Text style={{ color: C.successText, fontSize: 24, fontWeight: '700' }}>{accuracy.retention.avg_months}mo</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>Avg Retention</Text>
                  </View>
                )}
              </View>
            </View>
          )}

          {/* AI Insights */}
          {insights.length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginTop: 4, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>AI Insights</Text>
              {insights.map((ins: any, i: number) => (
                <View key={i} style={{
                  padding: 12, borderRadius: 8, marginBottom: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '10'),
                  borderLeftWidth: 3, borderLeftColor: ins.priority === 'high' ? C.error : ins.priority === 'medium' ? C.warning : C.successText,
                }}>
                  <Text style={{ color: C.text, fontSize: 13 }}>{ins.insight}</Text>
                  {ins.action && <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>Action: {ins.action}</Text>}
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* CALIBRATION VIEW */}
      {activeView === 'calibration' && calibration && (
        <View>
          {/* Calibration Score */}
          <View style={{
            backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16,
            borderWidth: 1, borderColor: C.border, alignItems: 'center',
          }}>
            <Text style={{ color: C.muted, fontSize: 13, marginBottom: 8 }}>Calibration Health</Text>
            {calibration.calibration_score != null ? (
              <>
                <Text style={{
                  color: calibration.calibration_score >= 85 ? C.successText : calibration.calibration_score >= 70 ? C.warning : C.error,
                  fontSize: 40, fontWeight: '800',
                }}>{calibration.calibration_score}</Text>
                <View style={{
                  paddingHorizontal: 12, paddingVertical: 4, borderRadius: 20, marginTop: 8,
                  backgroundColor: (globalThis as any).__alphaColor((calibration.health === 'excellent' ? C.successText : calibration.health === 'good' ? C.primary : C.warning), '22'),
                }}>
                  <Text style={{
                    color: calibration.health === 'excellent' ? C.successText : calibration.health === 'good' ? C.primary : C.warning,
                    fontSize: 12, fontWeight: '700', textTransform: 'uppercase',
                  }}>{calibration.health}</Text>
                </View>
              </>
            ) : (
              <Text style={{ color: C.muted, fontSize: 14, textAlign: 'center' }}>
                Record more outcomes to calculate calibration score
              </Text>
            )}
          </View>

          {/* Calibration Buckets */}
          {(calibration.buckets || []).length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Confidence vs Actual Accuracy</Text>
              {calibration.buckets.map((b: any, i: number) => (
                <View key={i} style={{ marginBottom: 8 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ color: C.text, fontSize: 13 }}>Confidence {b.range}%</Text>
                    <Text style={{
                      color: b.status === 'well_calibrated' ? C.successText : b.status === 'needs_adjustment' ? C.warning : C.error,
                      fontSize: 12, fontWeight: '600',
                    }}>{b.actual_accuracy}% actual ({b.predictions} predictions)</Text>
                  </View>
                  <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
                    <View style={{
                      height: 6, borderRadius: 3,
                      width: `${Math.min(b.actual_accuracy, 100)}%`,
                      backgroundColor: b.status === 'well_calibrated' ? C.successText : b.status === 'needs_adjustment' ? C.warning : C.error,
                    }} />
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* Recalibrate */}
          <TouchableOpacity data-testid="recalibrate-btn" testID="recalibrate-btn" onPress={recalibrate}
            style={{
              padding: 14, borderRadius: 12, backgroundColor: C.accent,
              alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
            }}>
            <Ionicons name="refresh-circle" size={18} color={C.primaryText} />
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>Recalibrate AI Weights</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* RECORD VIEW */}
      {activeView === 'record' && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>Record Hiring Outcome</Text>
          <Text style={{ color: C.muted, fontSize: 13, marginBottom: 12 }}>
            Track actual outcomes to improve AI predictions
          </Text>

          <TextInput data-testid="outcome-pipeline-id" testID="outcome-pipeline-id"
            placeholder="Pipeline ID (e.g. pipe_abc123)"
            placeholderTextColor={C.muted}
            value={outcomeForm.pipeline_id}
            onChangeText={v => setOutcomeForm(f => ({...f, pipeline_id: v}))}
            style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }}
          />

          <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
            {['hired', 'rejected', 'withdrew', 'no_show'].map(oc => (
              <TouchableOpacity key={oc} data-testid={`outcome-${oc}`} testID={`outcome-${oc}`}
                onPress={() => setOutcomeForm(f => ({...f, outcome: oc}))}
                style={{
                  paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                  backgroundColor: outcomeForm.outcome === oc ? (oc === 'hired' ? C.successText : oc === 'rejected' ? C.error : C.warning) : C.border,
                }}>
                <Text style={{
                  color: outcomeForm.outcome === oc ? C.primaryText : C.text,
                  fontSize: 12, fontWeight: '600', textTransform: 'capitalize',
                }}>{oc.replace('_', ' ')}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput data-testid="outcome-rating" testID="outcome-rating"
            placeholder="Performance rating (1-10, optional)"
            placeholderTextColor={C.muted}
            keyboardType="numeric"
            value={outcomeForm.performance_rating}
            onChangeText={v => setOutcomeForm(f => ({...f, performance_rating: v}))}
            style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }}
          />

          <TextInput data-testid="outcome-notes" testID="outcome-notes"
            placeholder="Notes (optional)"
            placeholderTextColor={C.muted}
            multiline
            value={outcomeForm.notes}
            onChangeText={v => setOutcomeForm(f => ({...f, notes: v}))}
            style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, marginBottom: 12, color: C.text, minHeight: 60, borderWidth: 1, borderColor: C.border }}
          />

          <TouchableOpacity data-testid="submit-outcome" testID="submit-outcome" onPress={recordOutcome}
            disabled={!outcomeForm.pipeline_id || recording}
            style={{
              padding: 14, borderRadius: 12,
              backgroundColor: !outcomeForm.pipeline_id ? C.border : C.accent,
              alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
            }}>
            <Ionicons name="checkmark-circle" size={18} color={C.primaryText} />
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>
              {recording ? 'Recording...' : 'Record Outcome'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Refresh */}
      <TouchableOpacity data-testid="refresh-learning" testID="refresh-learning" onPress={load}
        style={{ marginTop: 12, padding: 12, borderRadius: 10, backgroundColor: C.border, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
        <Ionicons name="refresh" size={16} color={C.text} />
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>Refresh</Text>
      </TouchableOpacity>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
