import React from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface KeywordAlertSettingsProps {
  alertSettings: any;
  setAlertSettings: (fn: (prev: any) => any) => void;
  showAlertSettings: boolean;
  setShowAlertSettings: (v: boolean) => void;
  saveAlertSettings: () => void;
  savingAlerts: boolean;
}

export function KeywordAlertSettings({ alertSettings, setAlertSettings, showAlertSettings, setShowAlertSettings, saveAlertSettings, savingAlerts }: KeywordAlertSettingsProps) {
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  return (
    <>
      {/* Alert Toggle Bar */}
      <View
        style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: alertSettings.enabled ? 'rgba(16,185,129,0.1)' : T.bg, borderRadius: 10, borderWidth: 1, borderColor: alertSettings.enabled ? 'rgba(16,185,129,0.3)' : T.border }}
        data-testid="keyword-alerts-toggle" testID="keyword-alerts-toggle">
        <Ionicons name={alertSettings.enabled ? 'notifications' : 'notifications-outline'} size={15} color={alertSettings.enabled ? 'var(--app-success)' : T.textMuted} />
        <TouchableOpacity accessibilityLabel={tx('admin.keywordAlertSettings.auto.accessibility.001', 'Toggle ranking change alerts')} onPress={() => setShowAlertSettings(!showAlertSettings)} style={{ flex: 1, flexDirection: 'row', alignItems: 'center' }}>
          <Text style={{ color: alertSettings.enabled ? 'var(--app-success)' : T.textSec, fontSize: 11, fontWeight: '600', flex: 1 }}>
            {alertSettings.enabled ? `Email alerts active — threshold: ${alertSettings.threshold}+ positions` : 'Email alerts off — tap to configure ranking change notifications'}
          </Text>
          <Ionicons name={showAlertSettings ? 'chevron-up' : 'chevron-down'} size={14} color={T.textMuted} />
        </TouchableOpacity>
      </View>

      {/* Alert Settings Panel */}
      {showAlertSettings && (
        <View style={{ marginBottom: 12, padding: 14, backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: alertSettings.enabled ? (globalThis as any).__alphaColor(colors.success, '30') : T.border }}
          data-testid="alert-settings-panel" testID="alert-settings-panel">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="notifications" size={16} color={alertSettings.enabled ? 'var(--app-success)' : T.textMuted} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', flex: 1 }}>{tx('admin.keywordAlertSettings.auto.text.001', 'Ranking Change Alerts')}</Text>
            <TouchableOpacity
              onPress={() => setAlertSettings((p: any) => ({ ...p, enabled: !p.enabled }))}
              style={{ width: 44, height: 24, borderRadius: 12, backgroundColor: alertSettings.enabled ? 'var(--app-success)' : T.border, justifyContent: 'center', padding: 2 }}
              data-testid="alert-enable-toggle" testID="alert-enable-toggle">
              <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText, alignSelf: alertSettings.enabled ? 'flex-end' : 'flex-start' }} />
            </TouchableOpacity>
          </View>

          {alertSettings.enabled && (
            <View style={{ gap: 10 }}>
              <View>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.keywordAlertSettings.auto.text.002', 'Alert Email')}</Text>
                <TextInput
                  value={alertSettings.alert_email}
                  onChangeText={(t: string) => setAlertSettings((p: any) => ({ ...p, alert_email: t }))}
                  placeholder={tx('admin.keywordAlertSettings.auto.placeholder.001', 'admin@example.com')}
                  placeholderTextColor={T.textMuted}
                  style={{ backgroundColor: T.bg, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: T.text, fontSize: 12 } as any}
                  data-testid="alert-email-input" testID="alert-email-input"
                />
              </View>
              <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.keywordAlertSettings.auto.text.003', 'Threshold (positions)')}</Text>
                  <TextInput accessibilityLabel={tx('admin.keywordAlertSettings.auto.accessibility.002', 'Text input')}
                    value={String(alertSettings.threshold)}
                    onChangeText={(t: string) => setAlertSettings((p: any) => ({ ...p, threshold: parseInt(t) || 10 }))}
                    keyboardType="numeric"
                    style={{ backgroundColor: T.bg, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: T.text, fontSize: 12, width: 80 } as any}
                    data-testid="alert-threshold-input" testID="alert-threshold-input"
                  />
                </View>
                <TouchableOpacity
                  onPress={() => setAlertSettings((p: any) => ({ ...p, notify_on_improvement: !p.notify_on_improvement }))}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 4 }}
                  data-testid="alert-improvement-toggle" testID="alert-improvement-toggle">
                  <View style={{ width: 16, height: 16, borderRadius: 4, borderWidth: 2, borderColor: alertSettings.notify_on_improvement ? 'var(--app-success)' : T.border, backgroundColor: alertSettings.notify_on_improvement ? 'var(--app-success)' : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                    {alertSettings.notify_on_improvement && <Ionicons name="checkmark" size={10} color="var(--app-primary-text)" />}
                  </View>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.keywordAlertSettings.auto.text.004', 'Improvements')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setAlertSettings((p: any) => ({ ...p, notify_on_decline: !p.notify_on_decline }))}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 4 }}
                  data-testid="alert-decline-toggle" testID="alert-decline-toggle">
                  <View style={{ width: 16, height: 16, borderRadius: 4, borderWidth: 2, borderColor: alertSettings.notify_on_decline ? 'var(--app-error)' : T.border, backgroundColor: alertSettings.notify_on_decline ? 'var(--app-error)' : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                    {alertSettings.notify_on_decline && <Ionicons name="checkmark" size={10} color="var(--app-primary-text)" />}
                  </View>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.keywordAlertSettings.auto.text.005', 'Declines')}</Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity onPress={saveAlertSettings} disabled={savingAlerts}
                style={{ alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: T.primary }}
                data-testid="alert-save-btn" testID="alert-save-btn">
                {savingAlerts ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="save" size={13} color="var(--app-primary-text)" />}
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.keywordAlertSettings.auto.text.006', 'Save Alert Settings')}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </>
  );
}
