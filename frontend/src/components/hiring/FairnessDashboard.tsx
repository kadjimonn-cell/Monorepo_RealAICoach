import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Props = { C: any; isWide: boolean };

export const FairnessDashboard = ({ C, isWide }: Props) => {
  const [activeView, setActiveView] = useState<'report' | 'audit' | 'flags'>('report');
  const [reviewNotes, setReviewNotes] = useState('');

  const { data: report, loading: rptLoading, refetch: refetchRpt } = useLiveQuery('/fairness/report', { entity: 'fairness', pollInterval: 60000 });
  const { data: audit, refetch: refetchAudit } = useLiveQuery('/fairness/bias-audit', { entity: 'fairness', pollInterval: 60000 });
  const { data: flagData, refetch: refetchFlags } = useLiveQuery('/fairness/flagged', { entity: 'fairness', pollInterval: 60000 });
  const flagged = flagData?.flags || [];
  const loading = rptLoading;

  const load = useCallback(async () => { await Promise.all([refetchRpt(), refetchAudit(), refetchFlags()]); }, [refetchRpt, refetchAudit, refetchFlags]);

  const reviewFlag = async (pipelineId: string, action: string) => {
    try {
      await api.post(`/fairness/flag/${pipelineId}/review`, { action, notes: reviewNotes });
      setReviewNotes('');
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/FairnessDashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>Analyzing fairness metrics...</Text>
    </View>
  );

  const gradeColor = (g: string) => {
    const map: Record<string, string> = { A: 'var(--app-success)', B: 'var(--app-primary)', C: 'var(--app-warning)', D: 'var(--app-error)', F: 'var(--app-error)' };
    return map[g] || C.muted;
  };

  return (
    <View data-testid="fairness-dashboard" testID="fairness-dashboard">
      {/* Tab Switcher */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {[
          { key: 'report', label: 'Report', icon: 'document-text-outline' },
          { key: 'audit', label: 'Bias Audit', icon: 'search-outline' },
          { key: 'flags', label: `Flags (${flagged.filter(f => f.status === 'pending').length})`, icon: 'flag-outline' },
        ].map(tab => (
          <TouchableOpacity key={tab.key} data-testid={`fairness-tab-${tab.key}`} testID={`fairness-tab-${tab.key}`}
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

      {/* REPORT VIEW */}
      {activeView === 'report' && report && (
        <View>
          {/* Grade Card */}
          <View style={{
            backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16,
            borderWidth: 1, borderColor: C.border, alignItems: 'center',
          }}>
            <Text style={{ color: C.muted, fontSize: 13, marginBottom: 8 }}>Overall Fairness Grade</Text>
            <View style={{
              width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center',
              backgroundColor: (globalThis as any).__alphaColor(gradeColor(report.grade), '22'), borderWidth: 3, borderColor: gradeColor(report.grade),
            }}>
              <Text style={{ color: gradeColor(report.grade), fontSize: 32, fontWeight: '800' }}>{report.grade}</Text>
            </View>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>{report.total_pipelines} pipelines analyzed</Text>
          </View>

          {/* Equal Opportunity */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Equal Opportunity Metrics</Text>
            {Object.entries(report.equal_opportunity || {}).map(([key, val]) => (
              <View key={key} style={{ marginBottom: 8 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Text style={{ color: C.text, fontSize: 13, textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</Text>
                  <Text style={{ color: C.accent, fontSize: 13, fontWeight: '700' }}>{String(val)}%</Text>
                </View>
                <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
                  <View style={{
                    height: 6, borderRadius: 3, width: `${Math.min(Number(val), 100)}%`,
                    backgroundColor: Number(val) > 80 ? C.success : Number(val) > 50 ? C.warning : C.error,
                  }} />
                </View>
              </View>
            ))}
          </View>

          {/* Confidence Distribution */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Confidence Distribution</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              {Object.entries(report.confidence_distribution || {}).map(([bucket, count]) => (
                <View key={bucket} style={{ alignItems: 'center', flex: 1 }}>
                  <Text style={{ color: C.accent, fontSize: 20, fontWeight: '700' }}>{String(count)}</Text>
                  <Text style={{ color: C.muted, fontSize: 10 }}>{bucket}%</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Decision Distribution */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Decision Distribution</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {Object.entries(report.decision_distribution || {}).map(([k, v]) => {
                const decColor = k.includes('hire') && !k.includes('no') ? C.success : k.includes('no') ? C.error : C.warning;
                return (
                  <View key={k} style={{ alignItems: 'center', minWidth: 60 }}>
                    <Text style={{ color: decColor, fontSize: 22, fontWeight: '700' }}>{String(v)}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        </View>
      )}

      {/* AUDIT VIEW */}
      {activeView === 'audit' && audit && (
        <View>
          {/* Risk Level */}
          <View style={{
            backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12,
            borderWidth: 1, borderColor: C.border,
            borderLeftWidth: 4, borderLeftColor: audit.risk_level === 'high' ? C.error : audit.risk_level === 'medium' ? C.warning : C.success,
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>Bias Risk Level</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{audit.total_pipelines} pipelines audited</Text>
              </View>
              <View style={{
                paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20,
                backgroundColor: (globalThis as any).__alphaColor((audit.risk_level === 'high' ? C.error : audit.risk_level === 'medium' ? C.warning : C.success), '22'),
              }}>
                <Text style={{
                  color: audit.risk_level === 'high' ? C.error : audit.risk_level === 'medium' ? C.warning : C.success,
                  fontSize: 14, fontWeight: '700', textTransform: 'uppercase',
                }}>{audit.risk_level}</Text>
              </View>
            </View>
          </View>

          {/* Patterns */}
          {(audit.patterns || []).length > 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Detected Patterns</Text>
              {audit.patterns.map((p: any, i: number) => (
                <View key={i} data-testid={`pattern-${i}`} testID={`pattern-${i}`} style={{
                  padding: 12, borderRadius: 8, marginBottom: 8,
                  backgroundColor: p.severity === 'high' ? (globalThis as any).__alphaColor(C.error, '15') : C.warning + '15',
                  borderLeftWidth: 3, borderLeftColor: p.severity === 'high' ? C.error : C.warning,
                }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{(p.type || '').replace(/_/g, ' ')}</Text>
                    <View style={{
                      paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4,
                      backgroundColor: p.severity === 'high' ? (globalThis as any).__alphaColor(C.error, '33') : C.warning + '33',
                    }}>
                      <Text style={{
                        color: p.severity === 'high' ? C.error : C.warning,
                        fontSize: 10, fontWeight: '700', textTransform: 'uppercase',
                      }}>{p.severity}</Text>
                    </View>
                  </View>
                  <Text style={{ color: C.muted, fontSize: 12 }}>{p.description}</Text>
                </View>
              ))}
            </View>
          ) : (
            <View style={{
              backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderRadius: 12, padding: 20, alignItems: 'center',
              marginBottom: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '33'),
            }}>
              <Ionicons name="shield-checkmark" size={32} color={C.successText} />
              <Text style={{ color: C.successText, fontSize: 15, fontWeight: '700', marginTop: 8 }}>No Bias Patterns Detected</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>Your hiring process appears fair and balanced</Text>
            </View>
          )}

          {/* AI Recommendations */}
          {(audit.recommendations || []).length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>AI Recommendations</Text>
              {audit.recommendations.map((r: any, i: number) => (
                <View key={i} style={{
                  padding: 12, borderRadius: 8, marginBottom: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '10'),
                  borderLeftWidth: 3, borderLeftColor: r.priority === 'high' ? C.error : r.priority === 'medium' ? C.warning : C.success,
                }}>
                  <Text style={{ color: C.text, fontSize: 13 }}>{r.recommendation}</Text>
                  {r.impact && <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>Impact: {r.impact}</Text>}
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* FLAGS VIEW */}
      {activeView === 'flags' && (
        <View>
          {flagged.length === 0 ? (
            <View style={{
              backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderRadius: 12, padding: 24, alignItems: 'center',
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '33'),
            }}>
              <Ionicons name="checkmark-circle" size={40} color={C.successText} />
              <Text style={{ color: C.successText, fontSize: 15, fontWeight: '700', marginTop: 8 }}>No Flagged Decisions</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>All hiring decisions passed fairness checks</Text>
            </View>
          ) : (
            flagged.map((f, i) => (
              <View key={f.pipeline_id || i} data-testid={`flag-card-${i}`} testID={`flag-card-${i}`} style={{
                backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
                borderWidth: 1, borderColor: f.status === 'pending' ? C.warning : C.border,
                borderLeftWidth: 3, borderLeftColor: f.status === 'pending' ? C.warning : C.success,
              }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>Pipeline: {f.pipeline_id?.slice(0, 15)}...</Text>
                  <View style={{
                    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
                    backgroundColor: f.status === 'pending' ? (globalThis as any).__alphaColor(C.warning, '22') : C.success + '22',
                  }}>
                    <Text style={{
                      color: f.status === 'pending' ? C.warning : C.success,
                      fontSize: 10, fontWeight: '700', textTransform: 'uppercase',
                    }}>{f.status}</Text>
                  </View>
                </View>
                <Text style={{ color: C.muted, fontSize: 12 }}>{f.reason}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>
                  Decision: {f.decision} | Confidence: {f.confidence}%
                </Text>

                {f.status === 'pending' && (
                  <View style={{ marginTop: 10 }}>
                    <TextInput
                      placeholder="Review notes (optional)"
                      placeholderTextColor={C.muted}
                      value={reviewNotes}
                      onChangeText={setReviewNotes}
                      style={{
                        backgroundColor: C.bg, borderRadius: 8, padding: 10, marginBottom: 8,
                        color: C.text, fontSize: 12, borderWidth: 1, borderColor: C.border,
                      }}
                    />
                    <View style={{ flexDirection: 'row', gap: 6 }}>
                      <TouchableOpacity data-testid={`review-flag-${i}`} testID={`review-flag-${i}`}
                        onPress={() => reviewFlag(f.pipeline_id, 'reviewed')}
                        style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: C.success, alignItems: 'center' }}>
                        <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '600' }}>Reviewed</Text>
                      </TouchableOpacity>
                      <TouchableOpacity data-testid={`dismiss-flag-${i}`} testID={`dismiss-flag-${i}`}
                        onPress={() => reviewFlag(f.pipeline_id, 'dismissed')}
                        style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: C.border, alignItems: 'center' }}>
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }}>Dismiss</Text>
                      </TouchableOpacity>
                      <TouchableOpacity data-testid={`escalate-flag-${i}`} testID={`escalate-flag-${i}`}
                        onPress={() => reviewFlag(f.pipeline_id, 'escalated')}
                        style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: C.error, alignItems: 'center' }}>
                        <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '600' }}>Escalate</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {f.reviewed_by && (
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 6 }}>
                    Reviewed by {f.reviewer_name} at {f.reviewed_at?.slice(0, 16)}
                  </Text>
                )}
              </View>
            ))
          )}
        </View>
      )}

      {/* Refresh */}
      <TouchableOpacity data-testid="refresh-fairness" testID="refresh-fairness" onPress={load}
        style={{ marginTop: 12, padding: 12, borderRadius: 10, backgroundColor: C.border, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
        <Ionicons name="refresh" size={16} color={C.text} />
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>Refresh Analysis</Text>
      </TouchableOpacity>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
