import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C } from './shared';
import { useTranslation } from '../../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';

export default function DeliverabilityView() {
  const onPrimary = 'rgb(255,255,255)';
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [delivData, setDelivData] = useState<any>(null);
  const [delivLoading, setDelivLoading] = useState(false);
  const [delivSimulating, setDelivSimulating] = useState(false);
  const [digestSending, setDigestSending] = useState(false);

  const loadDeliverability = useCallback(async () => {
    setDelivLoading(true);
    try {
      const res = await api.get('/email-notifications/deliverability');
      setDelivData(res.data);
    } catch { setDelivData(null); }
    finally { setDelivLoading(false); }
  }, []);

  const simulateDelivData = useCallback(async () => {
    setDelivSimulating(true);
    try {
      await api.post('/email-notifications/deliverability/simulate');
      await loadDeliverability();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/DeliverabilityView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setDelivSimulating(false); }
  }, [loadDeliverability]);

  const sendDigestNow = useCallback(async () => {
    setDigestSending(true);
    try {
      await api.post('/email-notifications/heatmap-digest/send-now');
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/DeliverabilityView.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setDigestSending(false); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadDeliverability(); }, []);

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="deliverability-section" testID="deliverability-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{tx('admin.emailTemplates.deliverability.header.title', 'Email Deliverability')}</Text>
          <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.emailTemplates.deliverability.header.subtitle', 'Bounce rates, spam complaints, and sender reputation (30-day window)')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={sendDigestNow} disabled={digestSending} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: digestSending ? C.border : C.purple, borderWidth: 1, borderColor: digestSending ? C.border : C.purple }} data-testid="send-digest-btn" testID="send-digest-btn">
            {digestSending ? <ActivityIndicator size="small" color={onPrimary} /> : <Ionicons name="mail" size={12} color={onPrimary} />}
            <Text style={{ fontSize: 11, fontWeight: '700', color: onPrimary }}>{digestSending ? 'Sending...' : 'Send Digest'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={loadDeliverability} style={{ padding: 8, borderRadius: 8, backgroundColor: C.bg }} data-testid="deliv-refresh-btn" testID="deliv-refresh-btn">
            <Ionicons name="refresh" size={14} color={C.muted} />
          </TouchableOpacity>
        </View>
      </View>

      {delivLoading ? (
        <ActivityIndicator size="large" color={C.blue} style={{ marginVertical: 30 }} />
      ) : delivData ? (
        <View>
          {/* Reputation Score */}
          <View style={{ alignItems: 'center', padding: 20, marginBottom: 20, backgroundColor: C.bg, borderRadius: 14, borderWidth: 1, borderColor: C.border }}>
            <View style={{ width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: delivData.reputation?.color === 'green' ? C.green : delivData.reputation?.color === 'blue' ? C.blue : delivData.reputation?.color === 'amber' ? C.warning : C.red, alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
              <Text style={{ fontSize: 28, fontWeight: '900', color: delivData.reputation?.color === 'green' ? C.green : delivData.reputation?.color === 'blue' ? C.blue : delivData.reputation?.color === 'amber' ? C.warning : C.red }}>{delivData.reputation?.score}</Text>
            </View>
            <Text style={{ fontSize: 14, fontWeight: '800', color: delivData.reputation?.color === 'green' ? C.green : delivData.reputation?.color === 'blue' ? C.blue : delivData.reputation?.color === 'amber' ? C.warning : C.red }}>{delivData.reputation?.label}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{tx('admin.emailTemplates.deliverability.reputation.label', 'Sender Reputation Score')}</Text>
          </View>

          {/* Alerts */}
          {delivData.alerts && delivData.alerts.length > 0 && (
            <View style={{ marginBottom: 16 }}>
              {delivData.alerts.map((a: any, idx: number) => (
                <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, marginBottom: 6, borderRadius: 10, backgroundColor: a.severity === 'critical' ? (globalThis as any).__alphaColor(C.red, '10') : C.warning + '10', borderWidth: 1, borderColor: a.severity === 'critical' ? (globalThis as any).__alphaColor(C.red, '25') : C.warning + '25' }} data-testid={`deliv-alert-${idx}`} testID={`deliv-alert-${idx}`}>
                  <Ionicons name={a.severity === 'critical' ? 'alert-circle' : 'warning'} size={16} color={a.severity === 'critical' ? C.red : C.warning} />
                  <Text style={{ flex: 1, fontSize: 12, color: a.severity === 'critical' ? C.red : C.warning, fontWeight: '600' }}>{a.message}</Text>
                </View>
              ))}
            </View>
          )}

          {/* KPI Cards */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Delivered', value: delivData.delivered, rate: delivData.delivery_rate + '%', color: C.green },
              { label: 'Bounced', value: delivData.bounced, rate: delivData.bounce_rate + '%', color: C.red },
              { label: 'Complaints', value: delivData.complained, rate: delivData.complaint_rate + '%', color: C.warningText },
              { label: 'Deferred', value: delivData.deferred, rate: '', color: C.muted },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 80, padding: 14, backgroundColor: (globalThis as any).__alphaColor(k.color, '08'), borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(k.color, '18'), alignItems: 'center' }}>
                <Text style={{ fontSize: 22, fontWeight: '800', color: k.color }}>{k.value}</Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{k.label}</Text>
                {k.rate ? <Text style={{ fontSize: 10, color: k.color, fontWeight: '700', marginTop: 2 }}>{k.rate}</Text> : null}
              </View>
            ))}
          </View>

          {/* Delivery Rate Bar */}
          <View style={{ marginBottom: 20, padding: 14, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.emailTemplates.deliverability.deliveryRate.title', 'Delivery Rate')}</Text>
              <Text style={{ fontSize: 14, fontWeight: '800', color: C.green }}>{delivData.delivery_rate}%</Text>
            </View>
            <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden' }}>
              <View style={{ width: `${delivData.delivery_rate}%`, height: '100%', backgroundColor: C.green, borderRadius: 4 }} />
            </View>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{delivData.total_sent} emails sent in last 30 days</Text>
          </View>

          {/* Daily Trend */}
          {delivData.daily_trend && delivData.daily_trend.length > 0 && (
            <View style={{ marginBottom: 20 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.emailTemplates.deliverability.trend.title', '7-Day Trend')}</Text>
              <View style={{ flexDirection: 'row', paddingVertical: 6, paddingHorizontal: 10, borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.bg, borderRadius: 8 }}>
                <Text style={{ flex: 1.2, fontSize: 9, fontWeight: '700', color: C.muted }}>{tx('admin.emailTemplates.deliverability.trend.columns.date', 'DATE')}</Text>
                <Text style={{ flex: 1, fontSize: 9, fontWeight: '700', color: C.green, textAlign: 'center' }}>{tx('admin.emailTemplates.deliverability.trend.columns.delivered', 'DELIVERED')}</Text>
                <Text style={{ flex: 1, fontSize: 9, fontWeight: '700', color: C.red, textAlign: 'center' }}>{tx('admin.emailTemplates.deliverability.trend.columns.bounced', 'BOUNCED')}</Text>
                <Text style={{ flex: 1, fontSize: 9, fontWeight: '700', color: C.warningText, textAlign: 'center' }}>{tx('admin.emailTemplates.deliverability.trend.columns.complaints', 'COMPLAINTS')}</Text>
              </View>
              {delivData.daily_trend.map((d: any) => (
                <View key={d.date} style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 10, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30') }}>
                  <Text style={{ flex: 1.2, fontSize: 11, color: C.muted }}>{d.date?.slice(5)}</Text>
                  <Text style={{ flex: 1, fontSize: 11, color: C.green, textAlign: 'center', fontWeight: '600' }}>{d.delivered}</Text>
                  <Text style={{ flex: 1, fontSize: 11, color: d.bounced > 0 ? C.red : C.muted, textAlign: 'center', fontWeight: d.bounced > 0 ? '700' : '400' }}>{d.bounced}</Text>
                  <Text style={{ flex: 1, fontSize: 11, color: d.complained > 0 ? C.warning : C.muted, textAlign: 'center', fontWeight: d.complained > 0 ? '700' : '400' }}>{d.complained}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Recent Issues */}
          {delivData.recent_issues && delivData.recent_issues.length > 0 && (
            <View>
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.emailTemplates.deliverability.recentIssues.title', 'Recent Issues (7d)')}</Text>
              {delivData.recent_issues.slice(0, 10).map((issue: any, idx: number) => (
                <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, marginBottom: 4, backgroundColor: C.bg, borderRadius: 8, borderWidth: 1, borderColor: C.border }} data-testid={`recent-issue-${idx}`} testID={`recent-issue-${idx}`}>
                  <Ionicons name={issue.event_type === 'bounced' ? 'arrow-undo' : 'flag'} size={12} color={issue.event_type === 'bounced' ? C.red : C.warning} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 11, color: C.text, fontWeight: '600' }} numberOfLines={1}>{issue.email}</Text>
                    <Text style={{ fontSize: 9, color: C.muted }}>{issue.reason?.replace(/_/g, ' ')} ({issue.template_type?.replace(/_/g, ' ')})</Text>
                  </View>
                  <Text style={{ fontSize: 9, color: C.muted }}>{issue.timestamp?.slice(5, 16)}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      ) : (
        <View style={{ alignItems: 'center', padding: 30, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="shield-outline" size={36} color={C.border} />
          <Text style={{ fontSize: 13, color: C.muted, marginTop: 10 }}>{tx('admin.emailTemplates.deliverability.empty.title', 'No deliverability data yet')}</Text>
          <Text style={{ fontSize: 11, color: C.muted, marginTop: 4, textAlign: 'center', maxWidth: 300 }}>{tx('admin.emailTemplates.deliverability.empty.subtitle', 'Deliverability metrics will populate as email bounce/complaint events are recorded.')}</Text>
          <TouchableOpacity onPress={simulateDelivData} disabled={delivSimulating} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8, backgroundColor: delivSimulating ? C.border : C.blue }} data-testid="simulate-deliv-btn" testID="simulate-deliv-btn">
            <Text style={{ fontSize: 12, fontWeight: '700', color: onPrimary }}>{delivSimulating ? 'Simulating...' : 'Generate Sample Data'}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}
