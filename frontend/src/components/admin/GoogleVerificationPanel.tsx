import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface VerificationDashboard {
  current_status: { status: string; checked_at: string; client_id?: string; note?: string };
  submission_date: string;
  timeline: { step: string; status: string; date: string | null; estimate?: string }[];
  history: { status: string; checked_at: string; manual?: boolean; note?: string }[];
  settings: { email_alerts_enabled: boolean; alert_email: string; check_interval_hours: number };
  checklist: Record<string, { status: string; label: string }>;
}

export default function GoogleVerificationPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: string; label: string }> = {
    under_review: { color: colors.warningText, bg: 'var(--app-warning-soft)', icon: 'time', label: 'Under Review' },
    verified: { color: colors.successText, bg: 'var(--app-success-soft)', icon: 'shield-checkmark', label: 'Verified' },
    rejected: { color: colors.error, bg: 'var(--app-error-soft)', icon: 'close-circle', label: 'Rejected' },
    action_required: { color: colors.accent, bg: 'var(--app-primary-soft)', icon: 'alert-circle', label: 'Action Required' },
    not_configured: { color: colors.textMuted, bg: 'var(--app-bg)', icon: 'help-circle', label: 'Not Configured' },
  };
  const STEP_CONFIG: Record<string, { color: string; icon: string }> = {
    completed: { color: colors.successText, icon: 'checkmark-circle' },
    in_progress: { color: colors.warningText, icon: 'time' },
    pending: { color: colors.textMuted, icon: 'ellipse-outline' },
  };
  const [data, setData] = useState<VerificationDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [alertsEnabled, setAlertsEnabled] = useState(true);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/admin/google-verification/dashboard');
      setData(res.data);
      setAlertsEnabled(res.data.settings?.email_alerts_enabled ?? true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load verification data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchDashboard(); }, [fetchDashboard]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/google-verification/hybrid-refresh',
    onTick: fetchDashboard,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });
  const runCheck = async () => {
    setChecking(true);
    try {
      await api.post('/admin/google-verification/check');
      await fetchDashboard();
    } catch (e: any) {
      setError('Check failed: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setChecking(false);
    }
  };

  const updateStatus = async (status: string) => {
    try {
      await api.post('/admin/google-verification/update-status', { status });
      setShowUpdateModal(false);
      await fetchDashboard();
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) {
      setError('Update failed');
    }
  };

  const toggleAlerts = async () => {
    const newVal = !alertsEnabled;
    setAlertsEnabled(newVal);
    try {
      await api.post('/admin/google-verification/settings', { email_alerts_enabled: newVal });
    } catch { setAlertsEnabled(!newVal); }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
      <AutoFixBanner domain="google_verification" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 12 }}>{tx('admin.googleVerificationPanel.auto.text.001', 'Loading verification monitor...')}</Text>
      </View>
    );
  }

  if (error && !data) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
        <Ionicons name="alert-circle" size={32} color={'var(--app-error)'} />
        <Text style={{ color: colors.error, fontSize: 14, marginTop: 8 }}>{error}</Text>
        <TouchableOpacity onPress={fetchDashboard} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: colors.primary, borderRadius: 8 }} accessibilityLabel={tx('admin.googleVerificationPanel.auto.accessibility.001', 'Retry')}>
          <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '600' }}>{tx('admin.googleVerificationPanel.auto.text.002', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const status = data?.current_status?.status || 'under_review';
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.under_review;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 16 }} data-testid="google-verification-panel" testID="google-verification-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }} data-testid="verification-title" testID="verification-title">{tx('admin.googleVerificationPanel.auto.text.003', 'Google OAuth Verification')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>{tx('admin.googleVerificationPanel.auto.text.004', 'Monitor your Google Cloud branding verification status')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity
            onPress={runCheck}
            disabled={checking}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: colors.primary, borderRadius: 8, opacity: checking ? 0.6 : 1 }}
            data-testid="check-now-btn" testID="check-now-btn"
          >
            {checking ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="refresh" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{tx('admin.googleVerificationPanel.auto.text.005', 'Check Now')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setShowUpdateModal(!showUpdateModal)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: colors.surface, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}
            data-testid="manual-update-btn" testID="manual-update-btn"
          >
            <Ionicons name="create" size={14} color={colors.textMuted} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{tx('admin.googleVerificationPanel.auto.text.006', 'Update Status')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Status Banner */}
      <View style={{ backgroundColor: cfg.bg, borderRadius: 12, padding: 20, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(cfg.color, '30'), flexDirection: 'row', alignItems: 'center', gap: 16 }} data-testid="status-banner" testID="status-banner">
        <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: (globalThis as any).__alphaColor(cfg.color, '20'), justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name={cfg.icon as any} size={28} color={cfg.color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: cfg.color }} data-testid="status-label" testID="status-label">{cfg.label}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
            Last checked: {data?.current_status?.checked_at ? new Date(data.current_status.checked_at).toLocaleString() : 'Never'}
          </Text>
          {data?.current_status?.client_id && (
            <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2, fontFamily: 'monospace' }}>
              Client ID: {data.current_status.client_id}
            </Text>
          )}
        </View>
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.googleVerificationPanel.auto.text.007', 'Submitted')}</Text>
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>
            {data?.submission_date ? new Date(data.submission_date).toLocaleDateString() : 'N/A'}
          </Text>
        </View>
      </View>

      {/* Manual Update Modal */}
      {showUpdateModal && (
        <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: 12 }}>{tx('admin.googleVerificationPanel.auto.text.008', 'Manually Update Verification Status')}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 12 }}>{tx('admin.googleVerificationPanel.auto.text.009', 'Update when you receive an email from Google\'s Trust & Safety team:')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(STATUS_CONFIG).filter(([k]) => k !== 'not_configured').map(([key, val]) => (
              <TouchableOpacity
                key={key}
                onPress={() => updateStatus(key)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: status === key ? (globalThis as any).__alphaColor(val.color, '20') : colors.background, borderRadius: 8, borderWidth: 1, borderColor: status === key ? val.color : colors.border }}
                data-testid={`update-status-${key}`} testID={`update-status-${key}`}
              >
                <Ionicons name={val.icon as any} size={14} color={val.color} />
                <Text style={{ fontSize: 12, fontWeight: '600', color: val.color }}>{val.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* Two-Column Layout */}
      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
        {/* Timeline */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 14 }}>{tx('admin.googleVerificationPanel.auto.text.010', 'Verification Timeline')}</Text>
          {data?.timeline?.map((step, i) => {
            const sCfg = STEP_CONFIG[step.status] || STEP_CONFIG.pending;
            const isLast = i === (data?.timeline?.length || 0) - 1;
            return (
              <View key={i} style={{ flexDirection: 'row', gap: 12, marginBottom: isLast ? 0 : 4 }}>
                <View style={{ alignItems: 'center', width: 24 }}>
                  <Ionicons name={sCfg.icon as any} size={18} color={sCfg.color} />
                  {!isLast && <View style={{ width: 2, flex: 1, backgroundColor: (globalThis as any).__alphaColor(sCfg.color, '30'), marginVertical: 4 }} />}
                </View>
                <View style={{ flex: 1, paddingBottom: isLast ? 0 : 14 }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{step.step}</Text>
                  <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>
                    {step.date ? new Date(step.date).toLocaleDateString() : step.estimate ? `Est: ${step.estimate}` : 'Pending'}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        {/* Checklist */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 14 }}>{tx('admin.googleVerificationPanel.auto.text.011', 'Requirements Checklist')}</Text>
          {data?.checklist && Object.entries(data.checklist).map(([key, item]) => {
            const done = item.status === 'done';
            const inProg = item.status === 'in_progress';
            const iconName = done ? 'checkmark-circle' : inProg ? 'time' : 'ellipse-outline';
            const iconColor = done ? 'var(--app-success)' : inProg ? 'var(--app-warning)' : colors.border;
            return (
              <View key={key} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7 }}>
                <Ionicons name={iconName as any} size={16} color={iconColor} />
                <Text style={{ fontSize: 13, color: done ? colors.text : colors.textMuted, flex: 1 }}>{item.label}</Text>
                <Text style={{ fontSize: 10, fontWeight: '600', color: iconColor, textTransform: 'uppercase' }}>
                  {item.status === 'done' ? 'Done' : item.status === 'in_progress' ? 'In Progress' : 'Pending'}
                </Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Alert Settings */}
      <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Ionicons name="notifications" size={18} color={alertsEnabled ? 'var(--app-success)' : colors.border} />
            <View>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{tx('admin.googleVerificationPanel.auto.text.012', 'Email Alerts')}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted }}>
                {alertsEnabled ? `Alerts sent to ${data?.settings?.alert_email || 'admin'}` : 'Disabled'}
              </Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={toggleAlerts}
            style={{ width: 48, height: 28, borderRadius: 14, backgroundColor: alertsEnabled ? 'var(--app-success)' : colors.surface, justifyContent: 'center', padding: 2 }}
            data-testid="toggle-alerts" testID="toggle-alerts"
          >
            <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: colors.primaryText, alignSelf: alertsEnabled ? 'flex-end' : 'flex-start' }} />
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="time" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 12, color: colors.textMuted }}>
              Checks every {data?.settings?.check_interval_hours || 6} hours
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="mail" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 12, color: colors.textMuted }}>{tx('admin.googleVerificationPanel.auto.text.013', 'Notifies on status changes')}</Text>
          </View>
        </View>
      </View>

      {/* Recent History */}
      {data?.history && data.history.length > 0 && (
        <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('admin.googleVerificationPanel.auto.text.014', 'Check History')}</Text>
          {data.history.slice(0, 10).map((entry, i) => {
            const eCfg = STATUS_CONFIG[entry.status] || STATUS_CONFIG.under_review;
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: i < Math.min(data.history.length - 1, 9) ? 1 : 0, borderBottomColor: colors.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: eCfg.color }} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: eCfg.color }}>{eCfg.label}</Text>
                  {entry.manual && <Text style={{ fontSize: 10, color: colors.textMuted, fontStyle: 'italic' }}>{tx('admin.googleVerificationPanel.auto.text.015', '(manual)')}</Text>}
                </View>
                <Text style={{ fontSize: 11, color: colors.textMuted }}>
                  {new Date(entry.checked_at).toLocaleString()}
                </Text>
              </View>
            );
          })}
        </View>
      )}
    </ScrollView>
  );
}
