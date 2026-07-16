import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type Props = {
  colors: any;
};

type InsightsPayload = {
  generated_at?: string;
  employees_analyzed?: number;
  anomalies?: any[];
  risk_scores?: any[];
  smart_access_recommendations?: any[];
  approval_suggestions?: any[];
  security_alerts?: any[];
  auto_audit_summary?: { summary?: string };
};

type AccessRequest = {
  request_id: string;
  email?: string;
  requested_role?: string;
  requested_features?: string[];
  reason?: string;
};

export default function EmployeeAIControlPanel({ colors: _colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [insights, setInsights] = useState<InsightsPayload>({});
  const [command, setCommand] = useState('show high risk employees');
  const [executeMode, setExecuteMode] = useState(false);
  const [commandNotice, setCommandNotice] = useState('');
  const [accessRequests, setAccessRequests] = useState<AccessRequest[]>([]);
  const [decisionLoading, setDecisionLoading] = useState<string>('');

  const loadInsights = useCallback(async () => {
    try {
      const [{ data }, { data: reqData }] = await Promise.all([
        api.get('/admin/employees/ai-insights', { params: { hours: 24 } }),
        api.get('/admin/employees/access-requests', { params: { status: 'pending', limit: 20 } }),
      ]);
      setInsights(data || {});
      setAccessRequests(reqData?.requests || []);
    } catch {
      setCommandNotice('Unable to load employee AI insights right now.');
    }
    setLoading(false);
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/employee-ai-control/hybrid-refresh',
    onTick: loadInsights,
    runOnMount: true,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const runCommand = async () => {
    if (!command.trim()) return;
    setExecuting(true);
    try {
      const { data } = await api.post('/admin/employees/ai-command', {
        command,
        execute: executeMode,
      });
      const msg = data?.message || (data?.performed ? 'Command completed.' : 'Command processed.');
      setCommandNotice(msg);
      await loadInsights();
    } catch (e: any) {
      setCommandNotice(e?.response?.data?.detail || 'Command failed.');
    }
    setExecuting(false);
  };

  const highRisk = (insights.risk_scores || []).filter((r) => r.risk_level === 'high');
  const mediumRisk = (insights.risk_scores || []).filter((r) => r.risk_level === 'medium');
  const recommendations = insights.smart_access_recommendations || [];
  const approvals = insights.approval_suggestions || [];
  const alerts = insights.security_alerts || [];

  const decideRequest = async (requestId: string, action: 'approve' | 'deny') => {
    setDecisionLoading(`${requestId}:${action}`);
    try {
      await api.post(`/admin/employees/access-requests/${requestId}/decision`, {
        action,
        reason: `Actioned from Employee AI Security Center (${action})`,
      });
      setCommandNotice(`Request ${requestId} ${action}d successfully.`);
      await loadInsights();
    } catch (e: any) {
      setCommandNotice(e?.response?.data?.detail || `Unable to ${action} request right now.`);
    }
    setDecisionLoading('');
  };

  const dispatchAlerts = async () => {
    setExecuting(true);
    try {
      const { data } = await api.post('/admin/employees/anomaly-alerts/dispatch', null, { params: { min_risk_score: 70 } });
      setCommandNotice(`Alert dispatch complete: ${data?.in_app_notifications_sent || 0} in-app, ${data?.email_notifications_sent || 0} email.`);
    } catch {
      setCommandNotice('Unable to dispatch anomaly alerts right now.');
    }
    setExecuting(false);
  };

  return (
    <View
      style={{ backgroundColor: colors.surface, borderRadius: 16, padding: 20, marginBottom: 24, borderWidth: 1, borderColor: colors.primarySoft }}
      data-testid="employee-ai-control-panel" testID="employee-ai-control-panel"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="employee-ai-control-title" testID="employee-ai-control-title">{tx('admin.employeeAIControlPanel.auto.text.001', 'Employee AI Security Center')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 3 }} data-testid="employee-ai-control-subtitle" testID="employee-ai-control-subtitle">{tx('admin.employeeAIControlPanel.auto.text.002', 'Smart access control, anomaly detection, predictive roles, and natural-language commands.')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => { void loadInsights(); }}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primarySoft, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 }}
          data-testid="employee-ai-refresh-button" testID="employee-ai-refresh-button"
        >
          <Ionicons name="refresh" size={14} color={'var(--app-primary)'} />
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{tx('admin.employeeAIControlPanel.auto.text.003', 'Refresh AI')}</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={{ paddingVertical: 24, alignItems: 'center' }} data-testid="employee-ai-loading-state" testID="employee-ai-loading-state">
          <ActivityIndicator color={'var(--app-primary)'} />
          <Text style={{ color: colors.textMuted, marginTop: 8, fontSize: 12 }}>{tx('admin.employeeAIControlPanel.auto.text.004', 'Loading AI insights...')}</Text>
        </View>
      ) : (
        <>
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            <Metric label="Employees" value={insights.employees_analyzed || 0} color={'var(--app-primary)'} testId="employee-ai-metric-employees" />
            <Metric label="High Risk" value={highRisk.length} color={'var(--app-error)'} testId="employee-ai-metric-high-risk" />
            <Metric label="Medium Risk" value={mediumRisk.length} color={'var(--app-warning)'} testId="employee-ai-metric-medium-risk" />
            <Metric label="Pending Approvals" value={approvals.length} color={'var(--app-success)'} testId="employee-ai-metric-approvals" />
          </View>

          <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 12 }} data-testid="employee-ai-summary-text" testID="employee-ai-summary-text">
            {insights.auto_audit_summary?.summary || 'AI summary unavailable.'}
          </Text>

          <View style={{ marginBottom: 12 }} data-testid="employee-ai-recommendations-list" testID="employee-ai-recommendations-list">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employeeAIControlPanel.auto.text.005', 'Predictive Role Assignments')}</Text>
            {recommendations.slice(0, 3).map((r: any) => (
              <Text key={`rec-${r.user_id}`} style={{ color: colors.textMuted, fontSize: 12, marginBottom: 4 }}>
                {r.email}: {r.current_role} → {r.recommended_role} ({Math.round((r.confidence || 0) * 100)}%)
              </Text>
            ))}
            {recommendations.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.employeeAIControlPanel.auto.text.006', 'No role drift detected.')}</Text> : null}
          </View>

          <View style={{ marginBottom: 14 }} data-testid="employee-ai-alerts-list" testID="employee-ai-alerts-list">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employeeAIControlPanel.auto.text.007', 'Security Alerts')}</Text>
            {alerts.slice(0, 3).map((a: any, idx: number) => (
              <Text key={`alert-${idx}`} style={{ color: a.severity === 'high' ? 'var(--app-error)' : 'var(--app-warning)', fontSize: 12, marginBottom: 4 }}>
                {a.email}: risk {a.risk_score} · {a.message}
              </Text>
            ))}
            {alerts.length === 0 ? <Text style={{ color: colors.successText, fontSize: 12 }}>{tx('admin.employeeAIControlPanel.auto.text.008', 'No active employee security alerts.')}</Text> : null}

            <TouchableOpacity
              onPress={() => { void dispatchAlerts(); }}
              disabled={executing}
              style={{ marginTop: 8, alignSelf: 'flex-start', backgroundColor: colors.errorSoft, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8 }}
              data-testid="employee-ai-dispatch-alerts-button" testID="employee-ai-dispatch-alerts-button"
            >
              <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{executing ? 'Dispatching...' : 'Dispatch Alerts (Email + In-App)'}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginBottom: 14 }} data-testid="employee-ai-approval-actions-list" testID="employee-ai-approval-actions-list">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employeeAIControlPanel.auto.text.009', 'Pending Access Approvals')}</Text>
            {accessRequests.slice(0, 5).map((req) => (
              <View key={req.request_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{req.email || req.request_id}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
                  Role: {req.requested_role || 'No role change'} · Features: {(req.requested_features || []).slice(0, 4).join(', ') || 'None'}
                </Text>
                {!!req.reason && <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>Reason: {req.reason}</Text>}
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                  <TouchableOpacity
                    onPress={() => { void decideRequest(req.request_id, 'approve'); }}
                    disabled={decisionLoading === `${req.request_id}:approve`}
                    style={{ backgroundColor: colors.successSoft, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7 }}
                    data-testid={`employee-ai-approve-request-${req.request_id}`} testID={`employee-ai-approve-request-${req.request_id}`}
                  >
                    <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{tx('admin.employeeAIControlPanel.auto.text.010', 'Approve')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => { void decideRequest(req.request_id, 'deny'); }}
                    disabled={decisionLoading === `${req.request_id}:deny`}
                    style={{ backgroundColor: colors.errorSoft, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7 }}
                    data-testid={`employee-ai-deny-request-${req.request_id}`} testID={`employee-ai-deny-request-${req.request_id}`}
                  >
                    <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{tx('admin.employeeAIControlPanel.auto.text.011', 'Deny')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
            {accessRequests.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.employeeAIControlPanel.auto.text.012', 'No pending approval actions.')}</Text> : null}
          </View>

          <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12 }} data-testid="employee-ai-command-box" testID="employee-ai-command-box">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{tx('admin.employeeAIControlPanel.auto.text.013', 'Natural Language Admin Command')}</Text>
            <TextInput
              value={command}
              onChangeText={setCommand}
              placeholder={tx('admin.employeeAIControlPanel.auto.placeholder.001', 'Try: grant premium to user@example.com')}
              placeholderTextColor={colors.textMuted}
              style={{ color: colors.text, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 12 }}
              data-testid="employee-ai-command-input" testID="employee-ai-command-input"
            />

            <View style={{ flexDirection: 'row', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={() => setExecuteMode((v) => !v)}
                style={{ backgroundColor: executeMode ? 'var(--app-error-soft)' : 'var(--app-success-soft)', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}
                data-testid="employee-ai-execute-toggle" testID="employee-ai-execute-toggle"
              >
                <Text style={{ color: executeMode ? 'var(--app-error)' : 'var(--app-success)', fontSize: 12, fontWeight: '700' }}>
                  {executeMode ? 'Execute Mode: ON' : 'Dry Run: ON'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => { void runCommand(); }}
                disabled={executing}
                style={{ backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}
                data-testid="employee-ai-run-command-button" testID="employee-ai-run-command-button"
              >
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{executing ? 'Running...' : 'Run Command'}</Text>
              </TouchableOpacity>
            </View>

            {commandNotice ? (
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }} data-testid="employee-ai-command-notice" testID="employee-ai-command-notice">
                {commandNotice}
              </Text>
            ) : null}
          </View>
        </>
      )}
    </View>
  );
}
function Metric({ label, value, color, testId }: { label: string; value: number; color: string; testId: string }) {
  return (
    <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '18'), borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, minWidth: 120 }} data-testid={testId} testID={testId}>
      <Text style={{ color, fontSize: 18, fontWeight: '800' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
      <Text style={{ color, fontSize: 11, fontWeight: '700' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label}</Text>
    </View>
  );
}
