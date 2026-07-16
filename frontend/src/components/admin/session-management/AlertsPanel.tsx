import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';
import api from '../../../services/api';
import { RISK_COLORS, fmtDate } from './types';

interface AlertsPanelProps {
  alertLoading: boolean;
  editAlerts: any;
  setEditAlerts: (fn: (p: any) => any) => void;
  alertHistory: any[];
  savingAlerts: boolean;
  setSavingAlerts: (b: boolean) => void;
  loadAlerts: () => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function AlertsPanel({
  alertLoading, editAlerts, setEditAlerts,
  alertHistory, savingAlerts, setSavingAlerts, loadAlerts,
}: AlertsPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  if (alertLoading) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;

  const saveSettings = async () => {
    setSavingAlerts(true);
    try {
      await api.put('/admin/session-alerts/settings', editAlerts);
      await loadAlerts();
    } catch (e) { console.error(e); }
    finally { setSavingAlerts(false); }
  };

  const levels = ['critical', 'high', 'medium', 'low'];
  const emailStr = (editAlerts?.notify_emails || []).join(', ');

  return (
    <View data-testid="alert-settings-panel" testID="alert-settings-panel">
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="notifications" size={18} color={T.warningText} />
          <Text style={s.chartTitle}>{tx('admin.alertsPanel.auto.text.001', 'Email Alert Settings')}</Text>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 16 }}>{tx('admin.alertsPanel.auto.text.002', 'Get notified via email when suspicious sessions are detected during scans.')}</Text>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{tx('admin.alertsPanel.auto.text.003', 'Enable Alerts')}</Text>
          <TouchableOpacity onPress={() => setEditAlerts((p: any) => ({ ...p, enabled: !p?.enabled }))}
            style={{ width: 44, height: 24, borderRadius: 12, backgroundColor: editAlerts?.enabled ? T.success : T.border, justifyContent: 'center', padding: 2 }}
            data-testid="alert-toggle" testID="alert-toggle"
          >
            <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: T.card, alignSelf: editAlerts?.enabled ? 'flex-end' : 'flex-start' }} />
          </TouchableOpacity>
        </View>

        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 6 }}>{tx('admin.alertsPanel.auto.text.004', 'Minimum Risk Level to Alert')}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
          {levels.map(lvl => {
            const rc = RISK_COLORS[lvl];
            const sel = editAlerts?.min_risk_level === lvl;
            return (
              <TouchableOpacity key={lvl} onPress={() => setEditAlerts((p: any) => ({ ...p, min_risk_level: lvl }))}
                style={{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                  backgroundColor: sel ? (globalThis as any).__alphaColor(rc.text, '20') : T.bgSoft, borderWidth: 2, borderColor: sel ? rc.text : T.border }}
                data-testid={`alert-level-${lvl}`} testID={`alert-level-${lvl}`}
              >
                <Ionicons name={rc.icon as any} size={16} color={sel ? rc.text : T.textMuted} />
                <Text style={{ color: sel ? rc.text : T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'capitalize', marginTop: 2 }}>{lvl}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{tx('admin.alertsPanel.auto.text.005', 'Notification Emails (comma-separated)')}</Text>
        <TextInput
          value={emailStr}
          onChangeText={t => setEditAlerts((p: any) => ({ ...p, notify_emails: t.split(',').map((e: string) => e.trim()).filter(Boolean) }))}
          placeholder={tx('admin.alertsPanel.auto.placeholder.001', 'admin@example.com, security@example.com')}
          placeholderTextColor={T.textMuted}
          style={{ backgroundColor: T.bgSoft, color: T.text, borderRadius: 8, padding: 10, fontSize: 12, marginBottom: 16, borderWidth: 1, borderColor: T.border }}
          data-testid="alert-emails-input" testID="alert-emails-input"
        />

        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{tx('admin.alertsPanel.auto.text.006', 'Cooldown Between Alerts (minutes)')}</Text>
        <TextInput accessibilityLabel={tx('admin.alertsPanel.auto.accessibility.001', 'Text input')}
          value={String(editAlerts?.cooldown_minutes || 60)}
          onChangeText={t => setEditAlerts((p: any) => ({ ...p, cooldown_minutes: parseInt(t) || 60 }))}
          keyboardType="numeric"
          style={{ backgroundColor: T.bgSoft, color: T.text, borderRadius: 8, padding: 10, fontSize: 12, marginBottom: 16, borderWidth: 1, borderColor: T.border }}
          data-testid="alert-cooldown-input" testID="alert-cooldown-input"
        />

        <TouchableOpacity onPress={saveSettings} disabled={savingAlerts}
          style={{ backgroundColor: T.primary, paddingVertical: 12, borderRadius: 10, alignItems: 'center' }}
          data-testid="alert-save-btn" testID="alert-save-btn"
        >
          <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 13 }}>{savingAlerts ? 'Saving...' : 'Save Settings'}</Text>
        </TouchableOpacity>
      </View>

      <View style={s.panel}>
        <Text style={[s.chartTitle, { marginBottom: 12 }]}>{tx('admin.alertsPanel.auto.text.007', 'Alert History')}</Text>
        {alertHistory.length === 0 ? (
          <Text style={{ color: T.textMuted, textAlign: 'center', paddingVertical: 20, fontSize: 12 }}>{tx('admin.alertsPanel.auto.text.008', 'No alerts sent yet')}</Text>
        ) : alertHistory.map((a: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`alert-history-${i}`} testID={`alert-history-${i}`}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: T.errorSoft, alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
              <Ionicons name="mail" size={16} color={T.error} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{a.flagged_count} user(s) flagged ({a.min_risk_level}+)</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>Sent to {a.recipients?.join(', ')}</Text>
            </View>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{fmtDate(a.sent_at)}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
