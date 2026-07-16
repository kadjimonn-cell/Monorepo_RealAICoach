import React, { useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAiInsight, AIInsightPanel, FindingItem, PriorityItem, QuickWinItem } from './AIInsightHelpers';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
}; }

interface Props { colors: any; }

type TabId = 'overview' | 'ml-analysis' | 'history';

export default function FraudDetectionPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data, loading, refetch: load } = useLiveQuery('/admin/fraud/dashboard', { entity: 'fraud', pollInterval: 30000 });
  const [scanning, setScanning] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const error = !data && !loading ? 'Failed to load' : null;

  const runScan = async () => {
    setScanning(true);
    try {
      await api.post('/admin/fraud/run-scan');
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/FraudDetectionPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setScanning(false); }
  };

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (error) return <Text style={{ color: T.error, padding: 20 }}>Error: {error}</Text>;
  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.fraudDetectionPanel.auto.text.001', 'Failed to load fraud data')}</Text>;

  const riskDist = data.risk_distribution || {};
  const criticalCount = riskDist.critical || 0;
  const highCount = riskDist.high || 0;
  const mediumCount = riskDist.medium || 0;
  const lowCount = riskDist.low || 0;
  const totalRisk = criticalCount + highCount;
  const threatLevel = totalRisk === 0 ? 'SECURE' : totalRisk < 3 ? 'LOW RISK' : totalRisk < 10 ? 'ELEVATED' : 'HIGH ALERT';
  const threatColor = totalRisk === 0 ? T.success : totalRisk < 3 ? T.primary : totalRisk < 10 ? T.warning : T.error;

  const topRiskUsers = data.top_risk_users || [];
  const securityEvents = Array.isArray(data.security_events) ? data.security_events : [];
  const signalBreakdown = data.signal_breakdown || {};
  const scanHistory = data.scan_history || [];
  const mlStatus = data.ml_status || {};
  const lastScan = data.last_scan;

  const totalSecEvents = securityEvents.reduce((s: number, e: any) => s + (e.count || 0), 0);
  const loginFailures = securityEvents.find((e: any) => e.event === 'login_failed')?.count || 0;
  const accountLocks = securityEvents.find((e: any) => e.event === 'account_locked')?.count || 0;

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: 'overview', label: 'Overview', icon: 'shield' },
    { id: 'ml-analysis', label: 'ML Analysis', icon: 'analytics' },
    { id: 'history', label: 'Scan History', icon: 'time' },
  ];

  return (
    <View data-testid="fraud-detection-panel" testID="fraud-detection-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="fraud-detection-title" testID="fraud-detection-title">{tx('admin.fraudDetectionPanel.auto.text.002', 'Fraud Detection')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.fraudDetectionPanel.auto.text.003', 'ML-powered risk scoring engine (Isolation Forest)')}</Text>
        </View>
        <TouchableOpacity onPress={runScan} disabled={scanning} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: scanning ? T.bgSoft : T.primary }} data-testid="run-scan-btn" testID="run-scan-btn">
          <Ionicons name={scanning ? 'hourglass' : 'shield-checkmark'} size={14} color="var(--app-primary-text)" />
          <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{scanning ? 'Scanning...' : 'Run Scan'}</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {tabs.map(tab => (
          <TouchableOpacity
            key={tab.id}
            onPress={() => setActiveTab(tab.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: activeTab === tab.id ? T.primary : T.card, borderWidth: 1, borderColor: activeTab === tab.id ? T.primary : T.border }}
            data-testid={`fraud-tab-${tab.id}`} testID={`fraud-tab-${tab.id}`}
          >
            <Ionicons name={tab.icon as any} size={13} color={activeTab === tab.id ? 'var(--app-primary-text)' : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === tab.id ? 'var(--app-primary-text)' : T.textMuted }}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <View>
          {/* Threat Level Badge */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center', marginBottom: 16 }} data-testid="threat-level-card" testID="threat-level-card">
            <View style={{ width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: (globalThis as any).__alphaColor(threatColor, '40'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
              <Ionicons name="shield" size={32} color={threatColor} />
            </View>
            <Text style={{ color: threatColor, fontSize: 18, fontWeight: '900', letterSpacing: 2 }}>{threatLevel}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>
              Last scan: {lastScan?.timestamp?.slice(0, 16)?.replace('T', ' ') || lastScan?.scan_time?.slice(0, 16)?.replace('T', ' ') || 'Never'}
            </Text>
          </View>

          {/* Risk Distribution KPIs */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }} data-testid="risk-kpis" testID="risk-kpis">
            <RiskKPI label="Critical" value={criticalCount} color={T.error} icon="alert-circle" />
            <RiskKPI label="High" value={highCount} color={T.warningText} icon="warning" />
            <RiskKPI label="Medium" value={mediumCount} color={T.primary} icon="information-circle" />
            <RiskKPI label="Low" value={lowCount} color={T.successText} icon="checkmark-circle" />
          </View>

          {/* Security Events */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="security-events-card" testID="security-events-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.fraudDetectionPanel.auto.text.004', 'Security Events (7 days)')}</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1, alignItems: 'center', paddingVertical: 8, backgroundColor: T.bgSoft, borderRadius: 10 }}>
                <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }}>{totalSecEvents}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.005', 'Total Events')}</Text>
              </View>
              <View style={{ flex: 1, alignItems: 'center', paddingVertical: 8, backgroundColor: T.bgSoft, borderRadius: 10 }}>
                <Text style={{ color: T.warningText, fontSize: 20, fontWeight: '800' }}>{loginFailures}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.006', 'Login Failures')}</Text>
              </View>
              <View style={{ flex: 1, alignItems: 'center', paddingVertical: 8, backgroundColor: T.bgSoft, borderRadius: 10 }}>
                <Text style={{ color: T.error, fontSize: 20, fontWeight: '800' }}>{accountLocks}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.007', 'Account Locks')}</Text>
              </View>
            </View>
          </View>

          {/* Signal Breakdown */}
          {Object.keys(signalBreakdown).length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="signal-breakdown-card" testID="signal-breakdown-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.fraudDetectionPanel.auto.text.008', 'Risk Signal Types')}</Text>
              {Object.entries(signalBreakdown).map(([key, count]: [string, any], i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Ionicons name="alert" size={12} color={T.warningText} />
                  <Text style={{ color: T.text, fontSize: 12, flex: 1 }}>{key.replace(/_/g, ' ')}</Text>
                  <Text style={{ color: T.warningText, fontSize: 13, fontWeight: '700' }}>{count}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Top Risk Users */}
          {topRiskUsers.length > 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="top-risk-users-card" testID="top-risk-users-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.fraudDetectionPanel.auto.text.009', 'Flagged Users')}</Text>
              {topRiskUsers.slice(0, 10).map((u: any, i: number) => {
                const rc = u.risk_level === 'critical' ? T.error : u.risk_level === 'high' ? T.warning : T.primary;
                return (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`risk-user-${i}`} testID={`risk-user-${i}`}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: rc }} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{u.name || u.email || u.user_id}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{u.risk_signals?.length || 0} signals</Text>
                    </View>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(rc, '20') }}>
                      <Text style={{ color: rc, fontSize: 10, fontWeight: '700' }}>SCORE: {u.risk_score}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <View style={{ paddingVertical: 20, alignItems: 'center' }}>
              <Ionicons name="shield-checkmark" size={32} color={T.successText} />
              <Text style={{ color: T.textSec, fontSize: 13, marginTop: 8 }}>{tx('admin.fraudDetectionPanel.auto.text.010', 'No flagged users detected')}</Text>
            </View>
          )}
        </View>
      )}

      {/* ML Analysis Tab */}
      {activeTab === 'ml-analysis' && (
        <View>
          {/* ML Model Status */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="ml-model-status" testID="ml-model-status">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: mlStatus.trained ? colors.successSoft : colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={mlStatus.trained ? 'hardware-chip' : 'alert-circle'} size={20} color={mlStatus.trained ? T.success : T.error} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.fraudDetectionPanel.auto.text.011', 'Isolation Forest Model')}</Text>
                <Text style={{ color: mlStatus.trained ? T.success : T.error, fontSize: 12, fontWeight: '600' }}>
                  {mlStatus.trained ? 'Trained & Active' : 'Not Yet Trained'}
                </Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <MlStat label="Trees" value={mlStatus.n_trees || 0} color={T.primary} />
              <MlStat label="Features" value={mlStatus.feature_dimensions || 0} color={T.purpleText} />
              <MlStat label="Method" value={data.scoring_method === 'isolation_forest_hybrid' ? 'Hybrid' : 'Rule'} color={T.cyan} />
            </View>
          </View>

          {/* Feature Vector Breakdown */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="feature-vector-breakdown" testID="feature-vector-breakdown">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 14 }}>{tx('admin.fraudDetectionPanel.auto.text.012', 'Feature Vector Dimensions')}</Text>
            {(mlStatus.features || []).map((feat: string, i: number) => {
              const featureIcons: Record<string, { icon: string; color: string }> = {
                login_failures: { icon: 'key', color: T.error },
                event_volume: { icon: 'pulse', color: T.warningText },
                distinct_ips: { icon: 'globe', color: T.primary },
                failed_payments: { icon: 'card', color: T.purpleText },
                account_age: { icon: 'time', color: T.cyan },
              };
              const fi = featureIcons[feat] || { icon: 'ellipse', color: T.textMuted };
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: i < (mlStatus.features?.length || 0) - 1 ? 1 : 0, borderBottomColor: T.border }}>
                  <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(fi.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={fi.icon as any} size={14} color={fi.color} />
                  </View>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '600', flex: 1 }}>{feat.replace(/_/g, ' ')}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(fi.color, '15') }}>
                    <Text style={{ color: fi.color, fontSize: 10, fontWeight: '700' }}>DIM {i + 1}</Text>
                  </View>
                </View>
              );
            })}
          </View>

          {/* Anomaly Score Visualization */}
          {topRiskUsers.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="anomaly-score-chart" testID="anomaly-score-chart">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.fraudDetectionPanel.auto.text.013', 'Anomaly Score Distribution')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 14 }}>{tx('admin.fraudDetectionPanel.auto.text.014', 'ML anomaly scores for flagged users (higher = more anomalous)')}</Text>
              {/* Bar Chart Visualization */}
              <View style={{ gap: 8 }}>
                {topRiskUsers.slice(0, 8).map((u: any, i: number) => {
                  const mlScore = u.anomaly_scores?.ml_isolation_forest || 0;
                  const barWidth = Math.max(mlScore * 100, 5);
                  const barColor = mlScore > 0.65 ? T.error : mlScore > 0.55 ? T.warning : T.primary;
                  return (
                    <View key={i} data-testid={`anomaly-bar-${i}`} testID={`anomaly-bar-${i}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                        <Text style={{ color: T.textSec, fontSize: 11, flex: 1 }} numberOfLines={1}>{u.name || u.email || u.user_id}</Text>
                        <Text style={{ color: barColor, fontSize: 11, fontWeight: '700', marginLeft: 8 }}>{(mlScore * 100).toFixed(0)}%</Text>
                      </View>
                      <View style={{ height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden', flexDirection: 'row' }}>
                        <View style={{ height: 8, flex: barWidth, backgroundColor: barColor, borderRadius: 4 }} />
                        <View style={{ flex: 100 - barWidth }} />
                      </View>
                    </View>
                  );
                })}
              </View>
              {/* Threshold Legend */}
              <View style={{ flexDirection: 'row', gap: 16, marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: T.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.error }} />
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.015', '&gt;65% Critical')}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.warning }} />
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.016', '55-65% Elevated')}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.primary }} />
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.017', '&lt;55% Normal')}</Text>
                </View>
              </View>
            </View>
          )}

          {/* Z-Score Thresholds */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="zscore-thresholds" testID="zscore-thresholds">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.fraudDetectionPanel.auto.text.018', 'Z-Score Thresholds')}</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, alignItems: 'center', borderLeftWidth: 3, borderLeftColor: T.warning }}>
                <Text style={{ color: T.warningText, fontSize: 22, fontWeight: '800' }}>{data.z_score_thresholds?.warning || 2.0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{tx('admin.fraudDetectionPanel.auto.text.019', 'Warning Threshold')}</Text>
              </View>
              <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, alignItems: 'center', borderLeftWidth: 3, borderLeftColor: T.error }}>
                <Text style={{ color: T.error, fontSize: 22, fontWeight: '800' }}>{data.z_score_thresholds?.critical || 3.0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{tx('admin.fraudDetectionPanel.auto.text.020', 'Critical Threshold')}</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Scan History Tab */}
      {activeTab === 'history' && (
        <View>
          {scanHistory.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 30, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="time-outline" size={36} color={T.textMuted} />
              <Text style={{ color: T.textSec, fontSize: 14, marginTop: 10 }}>{tx('admin.fraudDetectionPanel.auto.text.021', 'No scan history yet')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.fraudDetectionPanel.auto.text.022', 'Run a scan to generate history')}</Text>
            </View>
          ) : (
            <View style={{ gap: 10 }}>
              {scanHistory.map((scan: any, idx: number) => (
                <View key={idx} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid={`scan-history-${idx}`} testID={`scan-history-${idx}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: scan.flagged > 0 ? T.warning : T.success }} />
                      <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>
                        Scan #{scanHistory.length - idx}
                      </Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>
                      {scan.timestamp?.slice(0, 16)?.replace('T', ' ') || scan.scan_time?.slice(0, 16)?.replace('T', ' ')}
                    </Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, alignItems: 'center' }}>
                      <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{scan.total_scanned || 0}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.fraudDetectionPanel.auto.text.023', 'Scanned')}</Text>
                    </View>
                    <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, alignItems: 'center' }}>
                      <Text style={{ color: scan.flagged > 0 ? T.warning : T.success, fontSize: 16, fontWeight: '800' }}>{scan.flagged || 0}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.fraudDetectionPanel.auto.text.024', 'Flagged')}</Text>
                    </View>
                    <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 10, alignItems: 'center' }}>
                      <Text style={{ color: T.successText, fontSize: 16, fontWeight: '800' }}>{scan.cleared || 0}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.fraudDetectionPanel.auto.text.025', 'Cleared')}</Text>
                    </View>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    <Ionicons name="hardware-chip" size={12} color={scan.ml_model_trained ? T.success : T.textMuted} />
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>
                      {scan.method || 'unknown'} {scan.ml_model_trained ? '(ML active)' : '(rules only)'}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* AI Fraud Analysis */}
      <FraudAISection />
    </View>
  );
}

function FraudAISection() {
  const colors = useAdminTheme();
  const ai = useAiInsight('fraud_narrative', 'fraud-narrative');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="fraud-ai-toggle" testID="fraud-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.fraudDetectionPanel.auto.text.026', 'AI Fraud Risk Narrative')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'fraud_narrative', postEndpoint: 'fraud-narrative',
              title: 'AI Fraud Narrative', subtitle: 'fraud patterns',
              scoreKey: 'fraud_risk_score', scoreLabel: 'Fraud Risk Score',
              summaryKey: 'narrative',
              sections: [
                { key: 'risk_factors', title: 'Risk Factors', icon: 'warning', renderItem: (item, idx, total) => <FindingItem key={idx} item={{...item, finding: item.factor}} idx={idx} total={total} /> },
                { key: 'anomalies_detected', title: 'Anomalies Detected', icon: 'search', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={{action: item.anomaly, expected_impact: item.significance}} idx={idx} total={total} /> },
                { key: 'recommendations', title: 'Recommendations', icon: 'shield-checkmark', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}
    </View>
  );
}

function RiskKPI({ label, value, color, icon }: { label: string; value: number; color: string; icon: string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color, minWidth: 120, flex: 1 }} data-testid={`risk-kpi-${label.toLowerCase()}`} testID={`risk-kpi-${label.toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Ionicons name={icon as any} size={14} color={color} />
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color: value > 0 ? color : T.text, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}

function MlStat({ label, value, color }: { label: string; value: string | number; color: string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: T.border, minWidth: 80, alignItems: 'center' }}>
      <Text style={{ color, fontSize: 18, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{label}</Text>
    </View>
  );
}
