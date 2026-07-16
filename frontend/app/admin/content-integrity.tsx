import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../../src/components/AppShell';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import api from '../../src/services/api';
import { useLanguage } from '../../src/i18n/LanguageContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const W = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function ContentIntegrityPage() {
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { t } = useLanguage();
  const tt = (value: string) => t(value, value);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const [dashboard, setDashboard] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [gsAudit, setGsAudit] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [tab, setTab] = useState<'overview' | 'alerts' | 'games'>('overview');
  const [recoverableError, setRecoverableError] = useState('');

  useEffect(() => {
    router.replace('/admin-console?category=platform&tab=content-integrity');
  }, [router]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, alertsRes, gsRes] = await Promise.all([
        api.get('/admin/content-integrity/dashboard'),
        api.get('/admin/content-integrity/alerts?limit=50'),
        api.get('/admin/content-integrity/games-station/audit'),
      ]);
      setDashboard(dashRes.data);
      setAlerts(alertsRes.data?.alerts || []);
      setGsAudit(gsRes.data);
      setRecoverableError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.content-integrity.load-data',
        error,
        message: tt('Could not load content integrity data right now.'),
        setError: setRecoverableError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const runScan = useCallback(async () => {
    setScanning(true);
    try {
      const res = await api.post('/admin/content-integrity/scan', { scope: 'all', limit: 500 });
      if (res.data?.alerts_generated > 0) loadData();
      setRecoverableError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.content-integrity.run-scan',
        error,
        message: tt('Scan failed. Please retry.'),
        setError: setRecoverableError,
        onRetry: () => { void runScan(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    setScanning(false);
  }, [loadData]);

  const bulkResolve = useCallback(async (severity: string) => {
    try {
      await api.post('/admin/content-integrity/alerts/bulk-resolve', { severity, resolution: 'dismissed' });
      loadData();
      setRecoverableError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.content-integrity.bulk-resolve',
        error,
        message: tt('Bulk resolve failed. Please retry.'),
        setError: setRecoverableError,
        onRetry: () => { void bulkResolve(severity); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [loadData]);

  const severityColor = (s: string) => {
    if (s === 'critical') return colors.error;
    if (s === 'high') return colors.warning;
    if (s === 'medium') return colors.primary;
    return colors.textMuted;
  };

  const riskColor = (level: string) => {
    if (level === 'critical') return colors.error;
    if (level === 'high') return colors.warning;
    if (level === 'medium') return colors.primary;
    return colors.success;
  };

  if (loading) {
    return (
      <AppShell>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </AppShell>
    );
  }

  const TABS = [
    { key: 'overview', label: tt('Overview'), icon: 'shield-checkmark-outline' },
    { key: 'alerts', label: `${tt('Alerts')} (${dashboard?.alerts?.unresolved || 0})`, icon: 'warning-outline' },
    { key: 'games', label: tt('Games Audit'), icon: 'game-controller-outline' },
  ] as const;

  return (
    <AppShell>
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Header */}
        <View testID="integrity-header" style={{
          padding: isMobile ? 20 : 32, backgroundColor: colors.surface,
          borderBottomWidth: 1, borderBottomColor: colors.border,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield-checkmark" size={20} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text }}>{tt('Content Integrity Audit')}</Text>
              <Text style={{ fontSize: 13, color: colors.textMuted }}>{tt('Real-time contamination detection & moderation')}</Text>
            </View>
            <TouchableOpacity testID="integrity-scan-btn" onPress={runScan} disabled={scanning}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
                borderRadius: 10, backgroundColor: colors.primary, opacity: scanning ? 0.6 : 1,
              }}>
              {scanning ? <ActivityIndicator size="small" color={colors.primaryText} /> :
                <Ionicons name="scan" size={16} color={colors.primaryText} />}
              <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>{tt('Run Scan')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Tabs */}
        {recoverableError ? (
          <View
            style={{ marginHorizontal: isMobile ? 16 : 28, marginTop: 14, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.error + '35', backgroundColor: colors.errorSoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
            data-testid="content-integrity-recoverable-error-banner"
            testID="content-integrity-recoverable-error-banner"
          >
            <Text style={{ color: colors.errorText, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="content-integrity-recoverable-error-text" testID="content-integrity-recoverable-error-text">{recoverableError}</Text>
            <TouchableOpacity
              onPress={() => { void loadData(); }}
              style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
              data-testid="content-integrity-recoverable-error-retry"
              testID="content-integrity-recoverable-error-retry"
            >
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tt('Retry')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 4, padding: isMobile ? 16 : 28, paddingBottom: 0 }}>
          {TABS.map(t => (
            <TouchableOpacity key={t.key} data-testid={`integrity-tab-${t.key}`}
              onPress={() => setTab(t.key as any)}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10,
                backgroundColor: tab === t.key ? colors.primary : colors.surfaceHover,
                borderWidth: 1, borderColor: tab === t.key ? colors.primary : colors.border, ...W,
              }}>
              <Ionicons name={t.icon as any} size={15} color={tab === t.key ? colors.primaryText : colors.textMuted} />
              <Text style={{ fontSize: 12, fontWeight: tab === t.key ? '700' : '500', color: tab === t.key ? colors.primaryText : colors.text }}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ padding: isMobile ? 16 : 28, paddingTop: 16 }}>
          {/* OVERVIEW TAB */}
          {tab === 'overview' && dashboard && (
            <View style={{ gap: 16 }}>
              {/* Health Score */}
              <View testID="integrity-health" style={{
                padding: 20, borderRadius: 16, alignItems: 'center',
                backgroundColor: dashboard.health_score >= 80 ? colors.successSoft : dashboard.health_score >= 50 ? colors.warningSoft : colors.errorSoft,
                borderWidth: 1, borderColor: dashboard.health_score >= 80 ? (globalThis as any).__alphaColor(colors.success, '30') : dashboard.health_score >= 50 ? colors.warning + '30' : colors.error + '30',
              }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tt('Platform Health')}</Text>
                <Text style={{ fontSize: 48, fontWeight: '900', color: dashboard.health_score >= 80 ? colors.success : dashboard.health_score >= 50 ? colors.warning : colors.error }}>
                  {dashboard.health_score}%
                </Text>
                <Text style={{ fontSize: 12, color: colors.textMuted }}>
                  {dashboard.health_score >= 90 ? tt('Excellent — No issues') : dashboard.health_score >= 70 ? tt('Good — Minor issues') : tt('Needs Attention')}
                </Text>
              </View>

              {/* Stats Grid */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                {[
                  { label: tt('Total Alerts'), value: dashboard.alerts.total, icon: 'warning', color: colors.error },
                  { label: tt('Last 24h'), value: dashboard.alerts.last_24h, icon: 'time', color: colors.warning },
                  { label: tt('Last 7d'), value: dashboard.alerts.last_7d, icon: 'calendar', color: colors.primary },
                  { label: tt('Unresolved'), value: dashboard.alerts.unresolved, icon: 'alert-circle', color: colors.error },
                ].map((s, i) => (
                  <View key={i} style={{
                    flex: 1, minWidth: isMobile ? '45%' as any : 140, padding: 14, borderRadius: 12,
                    backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                  }}>
                    <Ionicons name={(s.icon + '-outline') as any} size={18} color={s.color} />
                    <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text, marginTop: 6 }}>{s.value}</Text>
                    <Text style={{ fontSize: 11, color: colors.textMuted }}>{s.label}</Text>
                  </View>
                ))}
              </View>

              {/* Content Sources */}
              <View style={{ padding: 16, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
                <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tt('Content Sources')}</Text>
                {Object.entries(dashboard.content_sources || {}).map(([key, val]: any) => (
                  <View key={key} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Text style={{ fontSize: 12, color: colors.textMuted, textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</Text>
                    <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{val.toLocaleString()}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* ALERTS TAB */}
          {tab === 'alerts' && (
            <View style={{ gap: 10 }}>
              {alerts.length === 0 ? (
                <View style={{ padding: 40, alignItems: 'center', borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
                  <Ionicons name="checkmark-circle-outline" size={48} color={colors.success} />
                  <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginTop: 12 }}>{tt('All Clear')}</Text>
                  <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>{tt('No content integrity alerts found')}</Text>
                </View>
              ) : (
                <>
                  <View style={{ flexDirection: 'row', gap: 6, marginBottom: 8 }}>
                    {['critical', 'high', 'medium'].map(sev => {
                      const count = alerts.filter(a => a.severity === sev && a.status === 'open').length;
                      return count > 0 ? (
                        <TouchableOpacity key={sev} onPress={() => bulkResolve(sev)}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6,
                            borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(severityColor(sev), '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(severityColor(sev), '30'),
                          }}>
                          <Text style={{ fontSize: 11, fontWeight: '600', color: severityColor(sev), textTransform: 'capitalize' }}>{tt('Dismiss')} {count} {tt(sev)}</Text>
                        </TouchableOpacity>
                      ) : null;
                    })}
                  </View>
                  {alerts.map((alert, i) => (
                    <View data-testid={`integrity-alert-${i}`} key={i} style={{
                      padding: 14, borderRadius: 12, backgroundColor: colors.card, borderWidth: 1,
                      borderColor: alert.status === 'open' ? (globalThis as any).__alphaColor(severityColor(alert.severity), '30') : colors.border,
                      borderLeftWidth: 3, borderLeftColor: severityColor(alert.severity), opacity: alert.status === 'open' ? 1 : 0.6,
                    }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(severityColor(alert.severity), '20') }}>
                          <Text style={{ fontSize: 10, fontWeight: '700', color: severityColor(alert.severity), textTransform: 'uppercase' }}>{alert.severity}</Text>
                        </View>
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: colors.surfaceHover }}>
                          <Text style={{ fontSize: 10, fontWeight: '600', color: colors.textMuted, textTransform: 'capitalize' }}>{alert.category?.replace(/_/g, ' ')}</Text>
                        </View>
                        <Text style={{ fontSize: 10, color: colors.textMuted, marginLeft: 'auto' as any }}>{alert.source}</Text>
                      </View>
                      <Text style={{ fontSize: 12, color: colors.text, lineHeight: 18 }} numberOfLines={2}>{alert.excerpt}</Text>
                    </View>
                  ))}
                </>
              )}
            </View>
          )}

          {/* GAMES AUDIT TAB */}
          {tab === 'games' && gsAudit && (
            <View style={{ gap: 12 }}>
              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                {Object.entries(gsAudit.summary || {}).map(([level, count]: any) => (
                  <View key={level} style={{
                    flex: 1, minWidth: 80, padding: 12, borderRadius: 10, alignItems: 'center',
                    backgroundColor: (globalThis as any).__alphaColor(riskColor(level), '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(riskColor(level), '25'),
                  }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: riskColor(level) }}>{count}</Text>
                    <Text style={{ fontSize: 10, fontWeight: '600', color: colors.textMuted, textTransform: 'capitalize' }}>{level}</Text>
                  </View>
                ))}
              </View>

              {gsAudit.contamination_alerts?.length > 0 && (
                <View style={{ padding: 14, borderRadius: 12, backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '25') }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: colors.error, marginBottom: 6 }}>{tt('Contamination Alerts')}</Text>
                  {gsAudit.contamination_alerts.map((ca: any, i: number) => (
                    <Text key={i} style={{ fontSize: 12, color: colors.errorText, lineHeight: 18 }}>
                      User {ca.user_id?.slice(-8)}: {ca.risk_level} risk (score {ca.risk_score}) — {ca.reason}
                    </Text>
                  ))}
                </View>
              )}

              {gsAudit.audit_rows?.length === 0 ? (
                <View style={{ padding: 30, alignItems: 'center', borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
                  <Ionicons name="game-controller-outline" size={40} color={colors.textMuted} />
                  <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 10 }}>{tt('No games activity in the last 7 days')}</Text>
                </View>
              ) : (
                gsAudit.audit_rows?.slice(0, 20).map((row: any, i: number) => (
                  <View data-testid={`gs-audit-row-${i}`} key={i} style={{
                    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 10,
                    backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                    borderLeftWidth: 3, borderLeftColor: riskColor(row.risk_level),
                  }}>
                    <Text style={{ fontSize: 11, color: colors.textMuted, width: 80 }} numberOfLines={1}>{row.user_id?.slice(-10)}</Text>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, width: 50 }}>{row.events} evt</Text>
                    <Text style={{ fontSize: 12, color: colors.textMuted, width: 60 }}>avg {row.avg_score}</Text>
                    <Text style={{ fontSize: 12, color: colors.textMuted, width: 50 }}>max {row.max_score}</Text>
                    <View style={{ flex: 1, alignItems: 'flex-end' }}>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(riskColor(row.risk_level), '20') }}>
                        <Text style={{ fontSize: 10, fontWeight: '700', color: riskColor(row.risk_level), textTransform: 'capitalize' }}>{row.risk_level} ({row.risk_score})</Text>
                      </View>
                    </View>
                  </View>
                ))
              )}
            </View>
          )}
        </View>
      </ScrollView>
    </AppShell>
  );
}
