import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

const METRIC_LABELS: Record<string, string> = {
  errors: 'Errors',
  signups: 'New Signups',
  payments_success: 'Successful Payments',
  payments_failed: 'Failed Payments',
  tickets: 'Support Tickets',
  ttfb: 'Avg. TTFB (ms)',
  sessions: 'Active Sessions',
  security_events: 'Security Events',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--app-error)', // @theme-ok brand/role/state identifier
  warning: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  info: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

const OPERATOR_LABELS: Record<string, string> = {
  '>=': 'greater than or equal',
  '>': 'greater than',
  '==': 'equal to',
  '<': 'less than',
  '<=': 'less than or equal',
};

interface RuleCondition {
  metric: string;
  operator: string;
  threshold: number;
  time_window_minutes: number;
}

interface NotificationRule {
  rule_id: string;
  name: string;
  condition: RuleCondition;
  severity: string;
  cooldown_minutes: number;
  enabled: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export default function NotificationRulesPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingRule, setEditingRule] = useState<NotificationRule | null>(null);
  const [testResult, setTestResult] = useState<{ rule_id: string; message: string; triggered: boolean } | null>(null);
  const [validMetrics, setValidMetrics] = useState<string[]>([]);
  const [validOperators, setValidOperators] = useState<string[]>([]);
  const [validSeverities, setValidSeverities] = useState<string[]>([]);

  const fetchRules = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/admin/notification-rules');
      setRules(res.data.rules || []);
      setValidMetrics(res.data.valid_metrics || []);
      setValidOperators(res.data.valid_operators || []);
      setValidSeverities(res.data.valid_severities || []);
    } catch (e) {
      console.error('Failed to fetch rules:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const handleToggle = async (ruleId: string) => {
    try {
      await api.put(`/admin/notification-rules/${ruleId}/toggle`);
      setRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, enabled: !r.enabled } : r));
    } catch (e) { console.error('Toggle failed:', e); }
  };

  const handleDelete = async (ruleId: string) => {
    try {
      await api.delete(`/admin/notification-rules/${ruleId}`);
      setRules(prev => prev.filter(r => r.rule_id !== ruleId));
    } catch (e) { console.error('Delete failed:', e); }
  };

  const handleTest = async (ruleId: string) => {
    try {
      const res = await api.post(`/admin/notification-rules/test/${ruleId}`);
      setTestResult({ rule_id: ruleId, message: res.data.message, triggered: res.data.triggered });
      setTimeout(() => setTestResult(null), 5000);
    } catch (e) { console.error('Test failed:', e); }
  };

  const card = { backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.border };
  const dim = colors.textSecondary || colors.subText || colors.textMuted;

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={colors.tint || colors.primary} />
        <Text style={{ color: dim, marginTop: 12, fontSize: 13 }}>{tx('admin.notificationRulesPanel.auto.text.001', 'Loading notification rules...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 40 }} data-testid="notification-rules-panel" testID="notification-rules-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }} data-testid="notification-rules-title" testID="notification-rules-title">{tx('admin.notificationRulesPanel.auto.text.002', 'Notification Rules')}</Text>
          <Text style={{ fontSize: 13, color: dim, marginTop: 2 }}>{rules.length} rules configured</Text>
        </View>
        <TouchableOpacity
          data-testid="create-rule-btn" testID="create-rule-btn"
          onPress={() => { setEditingRule(null); setShowCreate(true); }}
          style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, gap: 6 }}
        >
          <Ionicons name="add-circle" size={16} color={colors.buttonText} />
          <Text style={{ color: colors.buttonText, fontWeight: '600', fontSize: 13 }}>{tx('admin.notificationRulesPanel.auto.text.003', 'New Rule')}</Text>
        </TouchableOpacity>
      </View>

      {/* Stats Row */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { label: 'Total', value: rules.length, color: colors.primary },
          { label: 'Active', value: rules.filter(r => r.enabled).length, color: colors.successText },
          { label: 'Critical', value: rules.filter(r => r.severity === 'critical').length, color: colors.error },
          { label: 'Default', value: rules.filter(r => r.is_default).length, color: colors.purpleText },
        ].map(s => (
          <View key={s.label} style={{ ...card, flex: 1, minWidth: 120, flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 0, padding: 12 }}>
            <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(s.color, '18'), justifyContent: 'center', alignItems: 'center' }}>
              <Text style={{ fontSize: 16, fontWeight: '800', color: s.color }}>{s.value}</Text>
            </View>
            <Text style={{ fontSize: 12, fontWeight: '600', color: dim }}>{s.label}</Text>
          </View>
        ))}
      </View>

      {/* Create/Edit Form */}
      {showCreate && (
        <RuleForm
          colors={colors}
          dim={dim}
          card={card}
          validMetrics={validMetrics}
          validOperators={validOperators}
          validSeverities={validSeverities}
          editingRule={editingRule}
          onSave={async (data) => {
            try {
              if (editingRule) {
                await api.put(`/admin/notification-rules/${editingRule.rule_id}`, data);
              } else {
                await api.post('/admin/notification-rules', data);
              }
              setShowCreate(false);
              setEditingRule(null);
              fetchRules();
            } catch (e) { console.error('Save failed:', e); }
          }}
          onCancel={() => { setShowCreate(false); setEditingRule(null); }}
        />
      )}

      {/* Rules List */}
      {rules.map(rule => (
        <View key={rule.rule_id} style={{ ...card, opacity: rule.enabled ? 1 : 0.6 }} data-testid={`rule-${rule.rule_id}`} testID={`rule-${rule.rule_id}`}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: SEVERITY_COLORS[rule.severity] || colors.primary }} />
                <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{rule.name}</Text>
                {rule.is_default && (
                  <View style={{ backgroundColor: colors.purpleSoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: colors.purpleText }}>{tx('admin.notificationRulesPanel.auto.text.004', 'DEFAULT')}</Text>
                  </View>
                )}
                <View style={{ backgroundColor: (globalThis as any).__alphaColor((SEVERITY_COLORS[rule.severity] || colors.primary), '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: SEVERITY_COLORS[rule.severity] || colors.primary, textTransform: 'uppercase' }}>{rule.severity}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 13, color: dim, marginTop: 4 }}>
                Alert when <Text style={{ fontWeight: '600', color: colors.text }}>{METRIC_LABELS[rule.condition.metric] || rule.condition.metric}</Text> is {OPERATOR_LABELS[rule.condition.operator] || rule.condition.operator}{' '}
                <Text style={{ fontWeight: '700', color: SEVERITY_COLORS[rule.severity] || colors.primary }}>{rule.condition.threshold}</Text>
                {rule.condition.time_window_minutes > 0 ? ` within ${rule.condition.time_window_minutes} min` : ''}
              </Text>
              <Text style={{ fontSize: 11, color: dim, marginTop: 4 }}>Cooldown: {rule.cooldown_minutes} min</Text>
            </View>

            <Switch
              value={rule.enabled}
              onValueChange={() => handleToggle(rule.rule_id)}
              trackColor={{ false: colors.textSec, true: colors.successSoft }}
              thumbColor={rule.enabled ? colors.success : colors.textMuted}
              data-testid={`toggle-${rule.rule_id}`} testID={`toggle-${rule.rule_id}`}
            />
          </View>

          {/* Test result banner */}
          {testResult && testResult.rule_id === rule.rule_id && (
            <View style={{
              marginTop: 8, padding: 8, borderRadius: 6,
              backgroundColor: testResult.triggered ? colors.errorSoft : colors.successSoft,
            }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: testResult.triggered ? colors.error : colors.success }}>
                {testResult.message}
              </Text>
            </View>
          )}

          {/* Action buttons */}
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10 }}>
            <TouchableOpacity
              onPress={() => handleTest(rule.rule_id)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.primarySoft }}
              data-testid={`test-${rule.rule_id}`} testID={`test-${rule.rule_id}`}
            >
              <Ionicons name="play-circle" size={14} color={colors.primary} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: colors.primary }}>{tx('admin.notificationRulesPanel.auto.text.005', 'Test')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { setEditingRule(rule); setShowCreate(true); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.warningSoft }}
              data-testid={`edit-${rule.rule_id}`} testID={`edit-${rule.rule_id}`}
            >
              <Ionicons name="create" size={14} color={colors.warningText} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: colors.warningText }}>{tx('admin.notificationRulesPanel.auto.text.006', 'Edit')}</Text>
            </TouchableOpacity>
            {!rule.is_default && (
              <TouchableOpacity
                onPress={() => handleDelete(rule.rule_id)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.errorSoft }}
                data-testid={`delete-${rule.rule_id}`} testID={`delete-${rule.rule_id}`}
              >
                <Ionicons name="trash" size={14} color={colors.error} />
                <Text style={{ fontSize: 11, fontWeight: '600', color: colors.error }}>{tx('admin.notificationRulesPanel.auto.text.007', 'Delete')}</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

/* ── Rule Create/Edit Form ── */
function RuleForm({
  colors, dim, card, validMetrics, validOperators, validSeverities,
  editingRule, onSave, onCancel
}: {
  colors: any; dim: string; card: any;
  validMetrics: string[]; validOperators: string[]; validSeverities: string[];
  editingRule: NotificationRule | null;
  onSave: (data: any) => void; onCancel: () => void;
}) {
  const [name, setName] = useState(editingRule?.name || '');
  const [metric, setMetric] = useState(editingRule?.condition.metric || 'errors');
  const [operator, setOperator] = useState(editingRule?.condition.operator || '>=');
  const [threshold, setThreshold] = useState(String(editingRule?.condition.threshold ?? '5'));
  const [timeWindow, setTimeWindow] = useState(String(editingRule?.condition.time_window_minutes ?? '5'));
  const [severity, setSeverity] = useState(editingRule?.severity || 'warning');
  const [cooldown, setCooldown] = useState(String(editingRule?.cooldown_minutes ?? '5'));

  const input = {
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 10,
    color: colors.text,
    fontSize: 14,
    minHeight: 40,
  };

  const selectBtn = (isActive: boolean, color: string) => ({
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: isActive ? color : colors.border,
    backgroundColor: isActive ? (globalThis as any).__alphaColor(color, '18') : 'transparent',
    marginRight: 6,
    marginBottom: 6,
  });

  return (
    <View style={{ ...card, marginBottom: 16, borderColor: (globalThis as any).__alphaColor(colors.primary, '15') }} data-testid="rule-form" testID="rule-form">
      <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text, marginBottom: 12 }}>
        {editingRule ? 'Edit Rule' : 'Create New Rule'}
      </Text>

      {/* Name */}
      <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.008', 'Rule Name')}</Text>
      <TextInput
        value={name}
        onChangeText={setName}
        placeholder={tx('admin.notificationRulesPanel.auto.placeholder.001', 'e.g., High Error Rate')}
        placeholderTextColor={dim}
        style={input}
        data-testid="rule-name-input" testID="rule-name-input"
      />

      {/* Metric */}
      <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginTop: 12, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.009', 'Metric')}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {validMetrics.map(m => (
          <TouchableOpacity key={m} onPress={() => setMetric(m)} style={selectBtn(metric === m, 'var(--app-primary)')} data-testid={`metric-${m}`} testID={`metric-${m}`}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: metric === m ? 'var(--app-primary)' : dim }}>
              {METRIC_LABELS[m] || m}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Operator + Threshold Row */}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.010', 'Operator')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {validOperators.map(op => (
              <TouchableOpacity key={op} onPress={() => setOperator(op)} style={selectBtn(operator === op, 'var(--app-primary)')} data-testid={`operator-${op}`} testID={`operator-${op}`}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: operator === op ? 'var(--app-primary)' : dim }}>{op}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
        <View style={{ width: 100 }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.011', 'Threshold')}</Text>
          <TextInput accessibilityLabel={tx('admin.notificationRulesPanel.auto.accessibility.001', 'Text input')}
            value={threshold}
            onChangeText={setThreshold}
            keyboardType="numeric"
            style={input}
            data-testid="rule-threshold-input" testID="rule-threshold-input"
          />
        </View>
      </View>

      {/* Time Window + Cooldown Row */}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.012', 'Time Window (min)')}</Text>
          <TextInput accessibilityLabel={tx('admin.notificationRulesPanel.auto.accessibility.002', 'Text input')}
            value={timeWindow}
            onChangeText={setTimeWindow}
            keyboardType="numeric"
            style={input}
            data-testid="rule-window-input" testID="rule-window-input"
          />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.013', 'Cooldown (min)')}</Text>
          <TextInput accessibilityLabel={tx('admin.notificationRulesPanel.auto.accessibility.003', 'Text input')}
            value={cooldown}
            onChangeText={setCooldown}
            keyboardType="numeric"
            style={input}
            data-testid="rule-cooldown-input" testID="rule-cooldown-input"
          />
        </View>
      </View>

      {/* Severity */}
      <Text style={{ fontSize: 12, fontWeight: '600', color: dim, marginTop: 12, marginBottom: 4 }}>{tx('admin.notificationRulesPanel.auto.text.014', 'Severity')}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {validSeverities.map(s => (
          <TouchableOpacity key={s} onPress={() => setSeverity(s)} style={selectBtn(severity === s, SEVERITY_COLORS[s] || 'var(--app-primary)')} data-testid={`severity-${s}`} testID={`severity-${s}`}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: severity === s ? (SEVERITY_COLORS[s] || 'var(--app-primary)') : dim, textTransform: 'uppercase' }}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
        <TouchableOpacity
          data-testid="rule-save-btn" testID="rule-save-btn"
          onPress={() => {
            if (!name.trim()) return;
            onSave({
              name: name.trim(),
              condition: {
                metric,
                operator,
                threshold: parseFloat(threshold) || 0,
                time_window_minutes: parseInt(timeWindow) || 5,
              },
              severity,
              cooldown_minutes: parseInt(cooldown) || 5,
              enabled: editingRule?.enabled ?? true,
            });
          }}
          style={{ flex: 1, backgroundColor: colors.primary, paddingVertical: 10, borderRadius: 8, alignItems: 'center' }}
        >
          <Text style={{ color: colors.buttonText, fontWeight: '700', fontSize: 14 }}>{editingRule ? 'Update Rule' : 'Create Rule'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          data-testid="rule-cancel-btn" testID="rule-cancel-btn"
          onPress={onCancel}
          style={{ flex: 1, backgroundColor: colors.border, paddingVertical: 10, borderRadius: 8, alignItems: 'center' }}
        >
          <Text style={{ color: colors.text, fontWeight: '600', fontSize: 14 }}>{tx('admin.notificationRulesPanel.auto.text.015', 'Cancel')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}
