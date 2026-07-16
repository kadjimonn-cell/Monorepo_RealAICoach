import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C } from './shared';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';
import { useLanguage } from '../../../i18n/LanguageContext';

const onPrimary = 'rgb(255,255,255)';

export default function ReliabilityView() {
  const { t } = useLanguage();
  const { width } = useWindowDimensions();
  const reliabilityMinWidth = width < 640 ? width - 40 : 760;
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [copying, setCopying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/email-notifications/reliability/overview?window_days=7');
      setData(res.data || null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const copyTemplate = useCallback(async () => {
    setCopying(true);
    try {
      const res = await api.get('/email-notifications/reliability/weekly-report-template?window_days=7');
      const markdown = res?.data?.report_template?.template_markdown || '';
      if (typeof navigator !== 'undefined' && navigator.clipboard && markdown) {
        await navigator.clipboard.writeText(markdown);
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/components/admin/email-templates/ReliabilityView.tsx#copyTemplate',
        error,
        message: 'Failed to copy weekly template. Please retry.',
        notifyMode: 'silent',
      });
    } finally {
      setCopying(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="feature32-reliability-view" testID="feature32-reliability-view">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="feature32-reliability-title" testID="feature32-reliability-title">{t("adopt.feature.32.reliability")}</Text>
          <Text style={{ color: C.muted, fontSize: 11 }} data-testid="feature32-reliability-subtitle" testID="feature32-reliability-subtitle">{t("adopt.post.launch.monitoring.pack.uno.integrity.policy.guardrails")}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={copyTemplate} disabled={copying} style={{ backgroundColor: copying ? C.border : C.purple, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 5 }} data-testid="feature32-copy-weekly-template-button" testID="feature32-copy-weekly-template-button">
            <Ionicons name="document-text" size={12} color={onPrimary} />
            <Text style={{ color: onPrimary, fontSize: 11, fontWeight: '700' }}>{copying ? 'Copying...' : 'Copy Weekly Template'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={load} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 8 }} data-testid="feature32-reliability-refresh-button" testID="feature32-reliability-refresh-button">
            <Ionicons name="refresh" size={14} color={C.muted} />
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={C.blue} style={{ marginVertical: 20 }} />
      ) : data ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="feature32-reliability-content" testID="feature32-reliability-content">
          <View style={{ minWidth: reliabilityMinWidth, width: '100%' }}>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
              {[
                { key: 'Dispatch Success', value: `${data?.kpis?.uno_dispatch_success_rate_pct ?? 0}%`, color: C.green },
                { key: 'Duplicate Collisions', value: data?.kpis?.duplicate_key_collisions ?? 0, color: C.red },
                { key: 'Policy Blocks', value: data?.kpis?.policy_blocked_writes ?? 0, color: C.warningText },
                { key: 'Expired Policies', value: data?.kpis?.expired_policy_count ?? 0, color: C.blue },
              ].map((item) => (
                <View key={item.key} style={{ backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '20'), minWidth: 170, padding: 12 }} data-testid={`feature32-reliability-kpi-${item.key.toLowerCase().replace(/\s+/g, '-')}`} testID={`feature32-reliability-kpi-${item.key.toLowerCase().replace(/\s+/g, '-')}`}>
                  <Text style={{ color: item.color, fontSize: 20, fontWeight: '800' }}>{item.value}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{item.key}</Text>
                </View>
              ))}
            </View>

            <View style={{ backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 10 }} data-testid="feature32-reliability-alerts" testID="feature32-reliability-alerts">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{t("adopt.active.alerts")}</Text>
              {(data?.alerts || []).length === 0 ? (
                <Text style={{ color: C.muted, fontSize: 11 }}>{t("adopt.no.active.alerts")}</Text>
              ) : (
                (data?.alerts || []).map((a: any, idx: number) => (
                  <View key={`${a.code || 'alert'}-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }} data-testid={`feature32-reliability-alert-${idx}`} testID={`feature32-reliability-alert-${idx}`}>
                    <Ionicons name={a?.severity === 'critical' ? 'alert-circle' : a?.severity === 'warning' ? 'warning' : 'information-circle'} size={12} color={a?.severity === 'critical' ? C.red : a?.severity === 'warning' ? C.warning : C.blue} />
                    <Text style={{ color: C.text, fontSize: 11 }}>{a?.message || ''}</Text>
                  </View>
                ))
              )}
            </View>

            <View style={{ backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="feature32-reliability-failed-events" testID="feature32-reliability-failed-events">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>{t("adopt.top.failed.event.types")}</Text>
              {(data?.top_failed_events || []).length === 0 ? (
                <Text style={{ color: C.muted, fontSize: 11 }}>{t("adopt.no.failed.dispatch.events.in.selected.window")}</Text>
              ) : (
                (data?.top_failed_events || []).map((row: any, idx: number) => (
                  <View key={`${row?.event_type || 'unknown'}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }} data-testid={`feature32-reliability-failed-event-${idx}`} testID={`feature32-reliability-failed-event-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 11 }}>{String(row?.event_type || 'unknown').replace(/_/g, ' ')}</Text>
                    <Text style={{ color: C.red, fontSize: 11, fontWeight: '700' }}>{row?.count || 0}</Text>
                  </View>
                ))
              )}
            </View>
          </View>
        </ScrollView>
      ) : (
        <View style={{ backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 14 }} data-testid="feature32-reliability-empty" testID="feature32-reliability-empty">
          <Text style={{ color: C.muted, fontSize: 12 }}>{t("adopt.no.reliability.data.available.right.now")}</Text>
        </View>
      )}
    </View>
  );
}
