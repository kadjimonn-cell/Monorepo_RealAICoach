import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, StatCard, RateBar, Badge } from './shared';
import PerformanceChartsView from './PerformanceChartsView';
import { useTranslation } from '../../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';

interface Props {
  onResult: (result: { ok: boolean; msg: string }) => void;
}

export default function AbTestsView({ onResult }: Props) {
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [abTests, setAbTests] = useState<any[]>([]);
  const [abSummary, setAbSummary] = useState<any>(null);
  const [abLoading, setAbLoading] = useState(false);
  const [expandedTest, setExpandedTest] = useState<string | null>(null);
  const [stoppingTest, setStoppingTest] = useState<string | null>(null);
  const [applyingWinner, setApplyingWinner] = useState<string | null>(null);
  const [deletingTest, setDeletingTest] = useState<string | null>(null);
  const [rotationConfig, setRotationConfig] = useState<any>(null);
  const [rotationHistory, setRotationHistory] = useState<any>(null);
  const [rotationRunning, setRotationRunning] = useState(false);
  const [rotationSaving, setRotationSaving] = useState(false);

  const loadAbTests = useCallback(async () => {
    setAbLoading(true);
    try {
      const res = await api.get('/ab-testing/analytics');
      setAbTests(res.data?.tests || []); setAbSummary(res.data?.summary || null);
    } catch { setAbTests([]); setAbSummary(null); }
    finally { setAbLoading(false); }
  }, []);

  const loadRotationData = useCallback(async () => {
    try {
      const [cfgRes, histRes] = await Promise.all([
        api.get('/ab-testing/rotation/config'),
        api.get('/ab-testing/rotation/history'),
      ]);
      setRotationConfig(cfgRes.data);
      setRotationHistory(histRes.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AbTestsView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAbTests(); loadRotationData(); }, []);

  const toggleRotation = useCallback(async (enabled: boolean) => {
    setRotationSaving(true);
    try {
      const res = await api.put('/ab-testing/rotation/config', { enabled });
      setRotationConfig(res.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AbTestsView.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setRotationSaving(false); }
  }, []);

  const updateRotationConfig = useCallback(async (updates: any) => {
    setRotationSaving(true);
    try {
      const res = await api.put('/ab-testing/rotation/config', updates);
      setRotationConfig(res.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AbTestsView.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setRotationSaving(false); }
  }, []);

  const runRotationNow = useCallback(async () => {
    setRotationRunning(true);
    try {
      await api.post('/ab-testing/rotation/run-now');
      await Promise.all([loadAbTests(), loadRotationData()]);
      onResult({ ok: true, msg: tx('admin.abTestsView.actions.rotationCompleted', 'Rotation cycle completed! Check the tests list.') });
    } catch (e: any) { onResult({ ok: false, msg: e?.response?.data?.detail || tx('admin.abTestsView.errors.rotationFailed', 'Rotation failed') }); }
    finally { setRotationRunning(false); }
  }, [loadAbTests, loadRotationData, onResult, tx]);

  const stopAbTest = useCallback(async (testId: string) => {
    setStoppingTest(testId);
    try {
      await api.post(`/ab-testing/tests/${testId}/stop`);
      await loadAbTests();
    } catch (e: any) { onResult({ ok: false, msg: e?.response?.data?.detail || tx('admin.abTestsView.errors.stopFailed', 'Failed to stop test') }); }
    finally { setStoppingTest(null); }
  }, [loadAbTests, onResult, tx]);

  const applyAbWinner = useCallback(async (testId: string) => {
    setApplyingWinner(testId);
    try {
      await api.post(`/ab-testing/tests/${testId}/apply-winner`);
      await loadAbTests();
      onResult({ ok: true, msg: tx('admin.abTestsView.actions.winnerAppliedDefault', 'Winner applied as default!') });
    } catch (e: any) { onResult({ ok: false, msg: e?.response?.data?.detail || tx('admin.abTestsView.errors.applyWinnerFailed', 'Failed to apply winner') }); }
    finally { setApplyingWinner(null); }
  }, [loadAbTests, onResult, tx]);

  const deleteAbTest = useCallback(async (testId: string) => {
    setDeletingTest(testId);
    try {
      await api.delete(`/ab-testing/tests/${testId}`);
      await loadAbTests();
    } catch (e: any) { onResult({ ok: false, msg: e?.response?.data?.detail || tx('admin.abTestsView.errors.deleteFailed', 'Failed to delete test') }); }
    finally { setDeletingTest(null); }
  }, [loadAbTests, onResult, tx]);

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="abtests-section" testID="abtests-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{tx('admin.abTestsView.header.title', 'A/B Test Results')}</Text>
          <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.abTestsView.header.subtitle', 'Email subject line and content variant experiments')}</Text>
        </View>
        <TouchableOpacity onPress={loadAbTests} style={{ padding: 8, borderRadius: 8, backgroundColor: C.bg }} data-testid="ab-refresh-btn" testID="ab-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.muted} />
        </TouchableOpacity>
      </View>

      {abLoading ? (
        <ActivityIndicator size="large" color={C.blue} style={{ marginVertical: 40 }} />
      ) : !abSummary || abSummary.total_tests === 0 ? (
        <View style={{ alignItems: 'center', padding: 40 }}>
          <Ionicons name="git-compare-outline" size={48} color={C.border} />
          <Text style={{ fontSize: 14, color: C.muted, marginTop: 12 }}>{tx('admin.abTestsView.states.noTests', 'No A/B tests found')}</Text>
          <Text style={{ fontSize: 12, color: C.muted, marginTop: 4, textAlign: 'center' }}>{tx('admin.abTestsView.states.noTestsHint', 'Create A/B tests from the A/B Testing panel to see results here.')}</Text>
        </View>
      ) : (
        <View>
          {/* Summary KPIs */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            <StatCard val={abSummary.total_tests} label={tx('admin.abTestsView.stats.totalTests', 'Total Tests')} color={C.indigoText} />
            <StatCard val={abSummary.active} label={tx('admin.abTestsView.stats.active', 'Active')} color={C.green} />
            <StatCard val={abSummary.completed} label={tx('admin.abTestsView.stats.completed', 'Completed')} color={C.blue} />
            <StatCard val={abSummary.total_sends} label={tx('admin.abTestsView.stats.totalSends', 'Total Sends')} color={C.muted} />
          </View>

          {/* Tests List */}
          {abTests.map((test: any) => {
            const isExpanded = expandedTest === test.test_id;
            const statusColor = test.status === 'active' ? C.green : test.status === 'completed' ? C.blue : test.status === 'scheduled' ? C.warning : C.muted;
            const metricsA = test.metrics_a || { sent: 0, opened: 0, clicked: 0, open_rate: 0, click_rate: 0 };
            const metricsB = test.metrics_b || { sent: 0, opened: 0, clicked: 0, open_rate: 0, click_rate: 0 };
            const winner = test.winner;

            return (
              <View key={test.test_id} style={{ backgroundColor: C.bg, borderRadius: 12, marginBottom: 10, borderWidth: 1, borderColor: isExpanded ? (globalThis as any).__alphaColor(C.indigo, '40') : C.border, overflow: 'hidden' }} data-testid={`ab-test-${test.test_id}`} testID={`ab-test-${test.test_id}`}>
                {/* Test Header */}
                <TouchableOpacity
                  onPress={() => setExpandedTest(isExpanded ? null : test.test_id)}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14 }}
                  data-testid={`ab-test-toggle-${test.test_id}`} testID={`ab-test-toggle-${test.test_id}`}
                >
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.indigo, '18'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="git-compare" size={15} color={C.indigoText} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }} numberOfLines={1}>{test.name || test.template_type?.replace(/_/g, ' ') || tx('admin.abTestsView.states.unnamedTest', 'Unnamed Test')}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                        <Badge text={test.status} color={statusColor} />
                        {test.template_type && <Text style={{ fontSize: 10, color: C.muted }}>{test.template_type.replace(/_/g, ' ')}</Text>}
                        {winner && <Badge text={tx('admin.abTestsView.badges.winnerWithValue', 'Winner: {winner}').replace('{winner}', winner.toUpperCase())} color={C.green} />}
                      </View>
                    </View>
                  </View>
                  <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={C.muted} />
                </TouchableOpacity>

                {/* Expanded Details */}
                {isExpanded && (
                  <View style={{ padding: 14, borderTopWidth: 1, borderTopColor: C.border }}>
                    <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12, marginBottom: 12 }}>
                      {/* Variant A */}
                      <View style={{ flex: 1, padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: winner === 'a' ? (globalThis as any).__alphaColor(C.green, '50') : C.border }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <View style={{ width: 20, height: 20, borderRadius: 5, backgroundColor: (globalThis as any).__alphaColor(C.blue, '25'), alignItems: 'center', justifyContent: 'center' }}>
                              <Text style={{ fontSize: 10, fontWeight: '800', color: C.blue }}>A</Text>
                            </View>
                            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.abTestsView.variants.aTitle', 'Variant A')}</Text>
                          </View>
                          {winner === 'a' && <Badge text={tx('admin.abTestsView.badges.winner', 'Winner')} color={C.green} />}
                        </View>
                        {test.variant_a?.subject_line && (
                          <Text style={{ fontSize: 11, color: C.muted, marginBottom: 4 }} numberOfLines={2}>{tx('admin.abTestsView.variants.subject', 'Subject')}: "{test.variant_a.subject_line}"</Text>
                        )}
                        {test.variant_a?.strategy && (
                          <Text style={{ fontSize: 10, color: C.indigoText, marginBottom: 8, fontStyle: 'italic' }} numberOfLines={1}>{tx('admin.abTestsView.variants.strategy', 'Strategy')}: {test.variant_a.strategy}</Text>
                        )}
                        <View style={{ gap: 6 }}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.sent', 'Sent')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{metricsA.sent}</Text>
                          </View>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.openRate', 'Open Rate')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.green }}>{metricsA.open_rate}%</Text>
                          </View>
                          <RateBar rate={metricsA.open_rate} color={C.green} />
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.clickRate', 'Click Rate')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.blue }}>{metricsA.click_rate}%</Text>
                          </View>
                          <RateBar rate={metricsA.click_rate} color={C.blue} />
                        </View>
                      </View>

                      {/* Variant B */}
                      <View style={{ flex: 1, padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: winner === 'b' ? (globalThis as any).__alphaColor(C.green, '50') : C.border }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <View style={{ width: 20, height: 20, borderRadius: 5, backgroundColor: (globalThis as any).__alphaColor(C.purple, '25'), alignItems: 'center', justifyContent: 'center' }}>
                              <Text style={{ fontSize: 10, fontWeight: '800', color: C.purpleText }}>B</Text>
                            </View>
                            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.abTestsView.variants.bTitle', 'Variant B')}</Text>
                          </View>
                          {winner === 'b' && <Badge text={tx('admin.abTestsView.badges.winner', 'Winner')} color={C.green} />}
                        </View>
                        {test.variant_b?.subject_line && (
                          <Text style={{ fontSize: 11, color: C.muted, marginBottom: 4 }} numberOfLines={2}>{tx('admin.abTestsView.variants.subject', 'Subject')}: "{test.variant_b.subject_line}"</Text>
                        )}
                        {test.variant_b?.strategy && (
                          <Text style={{ fontSize: 10, color: C.indigoText, marginBottom: 8, fontStyle: 'italic' }} numberOfLines={1}>{tx('admin.abTestsView.variants.strategy', 'Strategy')}: {test.variant_b.strategy}</Text>
                        )}
                        <View style={{ gap: 6 }}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.sent', 'Sent')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{metricsB.sent}</Text>
                          </View>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.openRate', 'Open Rate')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.green }}>{metricsB.open_rate}%</Text>
                          </View>
                          <RateBar rate={metricsB.open_rate} color={C.green} />
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.metrics.clickRate', 'Click Rate')}</Text>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.blue }}>{metricsB.click_rate}%</Text>
                          </View>
                          <RateBar rate={metricsB.click_rate} color={C.blue} />
                        </View>
                      </View>
                    </View>

                    {/* Test Metadata + Actions */}
                    <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border, alignItems: 'center' }}>
                      <View style={{ flex: 1, flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
                        {test.created_at && <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.abTestsView.meta.created', 'Created')}: {new Date(test.created_at).toLocaleDateString()}</Text>}
                        {test.started_at && <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.abTestsView.meta.started', 'Started')}: {new Date(test.started_at).toLocaleDateString()}</Text>}
                        {test.completed_at && <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.abTestsView.meta.completed', 'Completed')}: {new Date(test.completed_at).toLocaleDateString()}</Text>}
                        {test.ends_at && test.status === 'active' && <Text style={{ fontSize: 10, color: C.warningText }}>{tx('admin.abTestsView.meta.ends', 'Ends')}: {new Date(test.ends_at).toLocaleDateString()}</Text>}
                        {test.confidence && <Text style={{ fontSize: 10, color: C.warningText }}>{tx('admin.abTestsView.meta.confidence', 'Confidence')}: {test.confidence}%</Text>}
                        {test.ai_generated && <Badge text={tx('admin.abTestsView.badges.aiGenerated', 'AI Generated')} color={C.purpleText} />}
                      </View>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        {test.status === 'active' && (
                          <TouchableOpacity onPress={() => stopAbTest(test.test_id)} disabled={stoppingTest === test.test_id}
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.warning, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '30') }}
                            data-testid={`ab-stop-${test.test_id}`} testID={`ab-stop-${test.test_id}`}
                          >
                            {stoppingTest === test.test_id ? <ActivityIndicator size={10} color={C.warningText} /> : <Ionicons name="pause" size={12} color={C.warningText} />}
                            <Text style={{ fontSize: 10, fontWeight: '700', color: C.warningText }}>{tx('admin.abTestsView.actions.stop', 'Stop')}</Text>
                          </TouchableOpacity>
                        )}
                        {test.status === 'completed' && test.winner && !test.auto_promoted && (
                          <TouchableOpacity onPress={() => applyAbWinner(test.test_id)} disabled={applyingWinner === test.test_id}
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '30') }}
                            data-testid={`ab-apply-${test.test_id}`} testID={`ab-apply-${test.test_id}`}
                          >
                            {applyingWinner === test.test_id ? <ActivityIndicator size={10} color={C.green} /> : <Ionicons name="checkmark-circle" size={12} color={C.green} />}
                            <Text style={{ fontSize: 10, fontWeight: '700', color: C.green }}>{tx('admin.abTestsView.actions.applyWinner', 'Apply Winner')}</Text>
                          </TouchableOpacity>
                        )}
                        {test.auto_promoted && <Badge text={tx('admin.abTestsView.badges.winnerApplied', 'Winner Applied')} color={C.green} />}
                        <TouchableOpacity onPress={() => deleteAbTest(test.test_id)} disabled={deletingTest === test.test_id}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '20') }}
                          data-testid={`ab-delete-${test.test_id}`} testID={`ab-delete-${test.test_id}`}
                        >
                          {deletingTest === test.test_id ? <ActivityIndicator size={10} color={C.red} /> : <Ionicons name="trash" size={12} color={C.red} />}
                        </TouchableOpacity>
                      </View>
                    </View>
                  </View>
                )}
              </View>
            );
          })}
        </View>
      )}

      {/* Auto-Rotation Section */}
      <View style={{ marginTop: 24, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 20 }} data-testid="rotation-section" testID="rotation-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.error, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="sync" size={16} color={C.error} />
            </View>
            <View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.abTestsView.rotation.title', 'Auto-Rotation')}</Text>
              <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.abTestsView.rotation.subtitle', 'Weekly AI-powered A/B test cycling across all templates')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity
              onPress={() => toggleRotation(!rotationConfig?.enabled)}
              disabled={rotationSaving}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: rotationConfig?.enabled ? (globalThis as any).__alphaColor(C.green, '15') : C.border + '40', borderWidth: 1, borderColor: rotationConfig?.enabled ? (globalThis as any).__alphaColor(C.green, '40') : C.border }}
              data-testid="rotation-toggle" testID="rotation-toggle"
            >
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: rotationConfig?.enabled ? C.green : C.muted }} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: rotationConfig?.enabled ? C.green : C.muted }}>
                {rotationSaving
                  ? tx('admin.abTestsView.common.saving', 'Saving...')
                  : rotationConfig?.enabled
                    ? tx('admin.abTestsView.common.enabled', 'Enabled')
                    : tx('admin.abTestsView.common.disabled', 'Disabled')}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runRotationNow} disabled={rotationRunning}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: rotationRunning ? C.border : C.error, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10 }}
              data-testid="rotation-run-now" testID="rotation-run-now"
            >
              {rotationRunning ? <ActivityIndicator size={10} color="var(--app-primary-text)" /> : <Ionicons name="play" size={12} color="var(--app-primary-text)" />}
              <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 11 }}>{rotationRunning ? tx('admin.abTestsView.common.running', 'Running...') : tx('admin.abTestsView.actions.runNow', 'Run Now')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Config Settings */}
        {rotationConfig && (
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 120, padding: 12, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>{tx('admin.abTestsView.rotation.settings.frequency', 'FREQUENCY')}</Text>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {(['weekly', 'biweekly'] as const).map(f => (
                  <TouchableOpacity key={f} accessibilityLabel="Update rotation config in ab tests view button" onPress={() => updateRotationConfig({ frequency: f })}
                    style={{ paddingVertical: 4, paddingHorizontal: 10, borderRadius: 6, backgroundColor: rotationConfig.frequency === f ? (globalThis as any).__alphaColor(C.error, '20') : 'transparent', borderWidth: 1, borderColor: rotationConfig.frequency === f ? (globalThis as any).__alphaColor(C.error, '40') : C.border }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: rotationConfig.frequency === f ? C.error : C.muted, textTransform: 'capitalize' }}>
                      {tx(`admin.abTestsView.rotation.frequency.${f}`, f)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={{ flex: 1, minWidth: 120, padding: 12, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>{tx('admin.abTestsView.rotation.settings.maxConcurrent', 'MAX CONCURRENT')}</Text>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {[3, 5, 10].map(n => (
                  <TouchableOpacity key={n} accessibilityLabel="Update rotation config in ab tests view button" onPress={() => updateRotationConfig({ max_concurrent: n })}
                    style={{ paddingVertical: 4, paddingHorizontal: 10, borderRadius: 6, backgroundColor: rotationConfig.max_concurrent === n ? (globalThis as any).__alphaColor(C.error, '20') : 'transparent', borderWidth: 1, borderColor: rotationConfig.max_concurrent === n ? (globalThis as any).__alphaColor(C.error, '40') : C.border }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: rotationConfig.max_concurrent === n ? C.error : C.muted }}>{n}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={{ flex: 1, minWidth: 120, padding: 12, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>{tx('admin.abTestsView.rotation.settings.evalPeriod', 'EVAL PERIOD')}</Text>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {[3, 7, 14].map(d => (
                  <TouchableOpacity key={d} accessibilityLabel="Update rotation config in ab tests view button" onPress={() => updateRotationConfig({ evaluation_days: d })}
                    style={{ paddingVertical: 4, paddingHorizontal: 10, borderRadius: 6, backgroundColor: rotationConfig.evaluation_days === d ? (globalThis as any).__alphaColor(C.error, '20') : 'transparent', borderWidth: 1, borderColor: rotationConfig.evaluation_days === d ? (globalThis as any).__alphaColor(C.error, '40') : C.border }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: rotationConfig.evaluation_days === d ? C.error : C.muted }}>{d}d</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={{ flex: 1, minWidth: 120, padding: 12, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>{tx('admin.abTestsView.rotation.settings.autoPromote', 'AUTO-PROMOTE')}</Text>
              <TouchableOpacity accessibilityLabel="checkmark button" onPress={() => updateRotationConfig({ auto_apply_winner: !rotationConfig.auto_apply_winner })}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ width: 16, height: 16, borderRadius: 4, borderWidth: 1.5, borderColor: rotationConfig.auto_apply_winner ? C.green : C.muted, backgroundColor: rotationConfig.auto_apply_winner ? (globalThis as any).__alphaColor(C.green, '20') : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                  {rotationConfig.auto_apply_winner && <Ionicons name="checkmark" size={10} color={C.green} />}
                </View>
                <Text style={{ fontSize: 11, fontWeight: '600', color: rotationConfig.auto_apply_winner ? C.green : C.muted }}>
                  {rotationConfig.auto_apply_winner ? tx('admin.abTestsView.common.enabled', 'Enabled') : tx('admin.abTestsView.common.disabled', 'Disabled')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Rotation History */}
        <View data-testid="rotation-history" testID="rotation-history">
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.abTestsView.rotation.history.title', 'Rotation History')}</Text>
          {!rotationHistory || rotationHistory.runs?.length === 0 ? (
            <View style={{ padding: 20, alignItems: 'center', backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="time-outline" size={24} color={C.border} />
              <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.abTestsView.rotation.history.empty', 'No rotation runs yet. Enable auto-rotation or click "Run Now".')}</Text>
            </View>
          ) : (
            <View>
              {rotationHistory.cumulative_improvement && Object.keys(rotationHistory.cumulative_improvement).length > 0 && (
                <View style={{ padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.green, '08'), borderRadius: 10, marginBottom: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '18') }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <Ionicons name="trending-up" size={14} color={C.green} />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.green }}>{tx('admin.abTestsView.rotation.history.cumulativeImprovement', 'Cumulative Improvement')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                    {Object.entries(rotationHistory.cumulative_improvement).sort(([,a]: any,[,b]: any) => b - a).slice(0, 6).map(([tpl, pct]: any) => (
                      <View key={tpl} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, padding: 6, backgroundColor: C.bg, borderRadius: 6 }}>
                        <Text style={{ fontSize: 10, color: C.text, fontWeight: '600' }}>{tpl.replace(/_/g, ' ')}</Text>
                        <Text style={{ fontSize: 10, color: C.green, fontWeight: '800' }}>+{pct}%</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}
              {rotationHistory.runs?.slice(0, 8).map((run: any, idx: number) => (
                <View key={idx} style={{ padding: 12, backgroundColor: C.bg, borderRadius: 10, marginBottom: 6, borderWidth: 1, borderColor: C.border }} data-testid={`rotation-run-${idx}`} testID={`rotation-run-${idx}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="sync-circle" size={14} color={C.error} />
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.abTestsView.rotation.history.cycle', 'Rotation Cycle')}</Text>
                      {run.manual && <Badge text={tx('admin.abTestsView.rotation.history.manual', 'Manual')} color={C.warningText} />}
                    </View>
                    <Text style={{ fontSize: 10, color: C.muted }}>{run.run_at ? new Date(run.run_at).toLocaleString() : ''}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 16 }}>
                    <Text style={{ fontSize: 11, color: C.blue }}><Text style={{ fontWeight: '700' }}>{run.evaluated || 0}</Text> {tx('admin.abTestsView.rotation.history.evaluated', 'evaluated')}</Text>
                    <Text style={{ fontSize: 11, color: C.green }}><Text style={{ fontWeight: '700' }}>{run.promoted || 0}</Text> {tx('admin.abTestsView.rotation.history.promoted', 'promoted')}</Text>
                    <Text style={{ fontSize: 11, color: C.error }}><Text style={{ fontWeight: '700' }}>{run.created || 0}</Text> {tx('admin.abTestsView.rotation.history.created', 'created')}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* Performance Trend Charts */}
      <PerformanceChartsView onResult={onResult} />
    </View>
  );
}
