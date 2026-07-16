import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const tx = (_key: string, fallback: string) => fallback;

const palette = {
  card: 'var(--app-card-bg)',
  border: 'var(--app-border)',
  text: 'var(--app-text)',  // @theme-ok admin-always-dark widget  
  textMuted: 'var(--app-text-muted)',
  success: 'var(--app-success)',
  warning: 'var(--app-warning)',
  danger: 'var(--app-error)',
  cyan: 'var(--app-primary)',
  soft: 'var(--app-primary)',
};

const scoreTone = (score) => (score >= 85 ? palette.success : score >= 65 ? palette.warning : palette.danger);

export const CIATrustScoreWidget = () => {
  const colors = useAdminTheme();
  const [runningHeal, setRunningHeal] = useState(false);
  const [healMessage, setHealMessage] = useState('');

  const { data: overview, loading, refetch } = useLiveQuery('/admin/cia-trust/overview', {
    entity: 'cia-trust-overview',
    pollInterval: 20000,
  });

  const { data: healLogs, refetch: refetchHealLogs } = useLiveQuery('/admin/cia-trust/self-heal/logs?limit=6', {
    entity: 'cia-self-heal-logs',
    pollInterval: 30000,
  });

  const runSelfHeal = useCallback(async (manual = false) => {
    if (runningHeal) return;
    setRunningHeal(true);
    try {
      const response = await api.post('/admin/cia-trust/self-heal/heartbeat', { source: manual ? 'manual' : 'auto' });
      const trust = Number(response?.data?.overview?.trust_score || 0).toFixed(1);
      setHealMessage(`Self-heal cycle complete. CIA trust ${trust}.`);
      await refetch();
      await refetchHealLogs();
    } catch (error) {
      setHealMessage(error?.response?.data?.detail || 'Self-heal cycle failed.');
    }
    setRunningHeal(false);
  }, [refetch, refetchHealLogs, runningHeal]);

  useEffect(() => {
    void runSelfHeal(false);
  }, [runSelfHeal]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/cia-trust/hybrid-refresh',
    onTick: () => runSelfHeal(false),
    runOnMount: false,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const trustScore = Number(overview?.trust_score || 0);
  const trustColor = scoreTone(trustScore);
  const cia = overview?.cia || {};
  const providers = Array.isArray(overview?.providers) ? overview.providers : [];
  const risks = Array.isArray(overview?.top_risks) ? overview.top_risks : [];
  const logs = Array.isArray(healLogs?.logs) ? healLogs.logs : [];
  const forecast = overview?.trust_forecast || {};
  const forecastTrajectory = Array.isArray(forecast?.trajectory) ? forecast.trajectory : [];
  const forecastBreach = forecast?.projected_breach || {};

  return (
    <View style={{ marginBottom: 16, borderRadius: 14, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 14 }} data-testid="cia-trust-widget" testID="cia-trust-widget">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: palette.text, fontSize: 14, fontWeight: '800' }} data-testid="cia-trust-widget-title" testID="cia-trust-widget-title">{tx('admin.cIATrustScoreWidget.auto.text.001', 'Executive CIA Trust Score')}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 3 }}>{tx('admin.cIATrustScoreWidget.auto.text.002', 'Confidentiality • Integrity • Availability + provider readiness + self-heal engine')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => { void runSelfHeal(true); }}
          style={{ borderRadius: 10, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.soft, paddingHorizontal: 10, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
          data-testid="cia-trust-run-self-heal-button" testID="cia-trust-run-self-heal-button"
        >
          {runningHeal ? <ActivityIndicator size="small" color={palette.cyan} /> : <Ionicons name="sparkles" size={13} color={palette.cyan} />}
          <Text style={{ color: palette.cyan, fontSize: 11, fontWeight: '700' }}>{tx('admin.cIATrustScoreWidget.auto.text.003', 'Run Self-Heal')}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ width: 108, height: 108, borderRadius: 54, borderWidth: 3, borderColor: `${trustColor}88`, backgroundColor: `${trustColor}1F`, alignItems: 'center', justifyContent: 'center' }} data-testid="cia-trust-score-ring" testID="cia-trust-score-ring">
          <Text style={{ color: trustColor, fontSize: 30, fontWeight: '900' }}>{loading ? '--' : Math.round(trustScore)}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.cIATrustScoreWidget.auto.text.004', 'TRUST')}</Text>
        </View>

        <View style={{ flex: 1, minWidth: 220, gap: 8 }}>
          <CIACard label="Confidentiality" score={Number(cia?.confidentiality?.score || 0)} testId="cia-confidentiality-score" />
          <CIACard label="Integrity" score={Number(cia?.integrity?.score || 0)} testId="cia-integrity-score" />
          <CIACard label="Availability" score={Number(cia?.availability?.score || 0)} testId="cia-availability-score" />
        </View>
      </View>

      <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.soft, padding: 10 }} data-testid="cia-provider-readiness-strip" testID="cia-provider-readiness-strip">
        <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700', marginBottom: 8 }}>{tx('admin.cIATrustScoreWidget.auto.text.005', 'Provider Readiness Health')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {providers.map((provider) => {
            const tone = provider?.state === 'live_ready' ? palette.success : provider?.state === 'degraded' ? palette.warning : palette.danger;
            return (
              <View key={provider.provider} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${tone}77`, backgroundColor: `${tone}22`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid={`cia-provider-${provider.provider}`} testID={`cia-provider-${provider.provider}`}>
                <Text style={{ color: tone, fontSize: 10, fontWeight: '800' }}>{provider.label}: {String(provider.state || '').toUpperCase()}</Text>
              </View>
            );
          })}
        </View>
      </View>

      <View style={{ marginTop: 10, flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 230, borderRadius: 10, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.soft, padding: 10 }} data-testid="cia-top-risks-panel" testID="cia-top-risks-panel">
          <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.cIATrustScoreWidget.auto.text.006', 'AI-driven Threat Detection')}</Text>
          {(risks.length ? risks : [{ type: 'none', severity: 'normal', value: 0 }]).slice(0, 4).map((risk, idx) => (
            <Text key={`${risk.type}-${idx}`} style={{ color: risk.severity === 'high' ? palette.danger : palette.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`cia-risk-${idx}`} testID={`cia-risk-${idx}`}>
              • {String(risk.type || 'none').replace(/_/g, ' ')} ({risk.severity || 'normal'})
            </Text>
          ))}
        </View>

        <View style={{ flex: 1, minWidth: 230, borderRadius: 10, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.soft, padding: 10 }} data-testid="cia-self-heal-log-panel" testID="cia-self-heal-log-panel">
          <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.cIATrustScoreWidget.auto.text.007', 'Self-Heal Execution Log')}</Text>
          {(logs.length ? logs : [{ ran_at: null, trust_score: null }]).slice(0, 4).map((log, idx) => (
            <Text key={`heal-log-${idx}`} style={{ color: palette.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`cia-self-heal-log-${idx}`} testID={`cia-self-heal-log-${idx}`}>
              • {(log?.ran_at ? new Date(log.ran_at).toLocaleTimeString() : '--')} — trust {log?.trust_score ?? '--'}
            </Text>
          ))}
        </View>
      </View>

      <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.soft, padding: 10 }} data-testid="cia-trust-forecast-panel" testID="cia-trust-forecast-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700' }}>{tx('admin.cIATrustScoreWidget.auto.text.008', 'Predictive Trust Forecast (Next 6h)')}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>Slope/h: {Number(forecast?.slope_per_hour || 0).toFixed(2)}</Text>
        </View>
        <View style={{ marginTop: 8, gap: 6 }}>
          {forecastTrajectory.map((point, idx) => {
            const score = Number(point?.predicted_trust_score || 0);
            const tone = scoreTone(score);
            return (
              <View key={`forecast-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`cia-trust-forecast-row-${idx}`} testID={`cia-trust-forecast-row-${idx}`}>
                <Text style={{ color: palette.textMuted, fontSize: 10, width: 28 }}>+{point?.hour_offset}h</Text>
                <View style={{ flex: 1, height: 8, borderRadius: 999, backgroundColor: colors.bg, borderWidth: 1, borderColor: palette.border }}>
                  <View style={{ width: `${Math.max(2, Math.min(100, score))}%`, height: '100%', borderRadius: 999, backgroundColor: tone }} />
                </View>
                <Text style={{ color: tone, fontSize: 10, fontWeight: '800', width: 34, textAlign: 'right' }}>{Math.round(score)}</Text>
              </View>
            );
          })}
          {forecastTrajectory.length === 0 ? (
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>{tx('admin.cIATrustScoreWidget.auto.text.009', 'Forecast is calibrating…')}</Text>
          ) : null}
        </View>
        {forecastBreach?.level ? (
          <Text style={{ color: forecastBreach.level === 'critical' ? palette.danger : palette.warning, fontSize: 10, marginTop: 8 }} data-testid="cia-trust-forecast-breach" testID="cia-trust-forecast-breach">
            Projected {forecastBreach.level.toUpperCase()} breach in ~{forecastBreach.eta_hours}h.
          </Text>
        ) : (
          <Text style={{ color: palette.successText, fontSize: 10, marginTop: 8 }} data-testid="cia-trust-forecast-stable" testID="cia-trust-forecast-stable">{tx('admin.cIATrustScoreWidget.auto.text.010', 'Forecast stable — no trust breach projected in next 6h.')}</Text>
        )}
      </View>

      {healMessage ? (
        <Text style={{ color: palette.cyan, fontSize: 10, marginTop: 10 }} data-testid="cia-self-heal-message" testID="cia-self-heal-message">{healMessage}</Text>
      ) : null}
    </View>
  );
};

function CIACard({ label, score, testId }) {
  const tone = scoreTone(score);
  return (
    <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${tone}66`, backgroundColor: `${tone}1A`, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '700' }}>{label}</Text>
        <Text style={{ color: tone, fontSize: 12, fontWeight: '900' }}>{Math.round(score)}</Text>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
