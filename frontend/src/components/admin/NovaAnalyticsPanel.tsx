import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecTheme} from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const API_URL = resolveRuntimeBaseUrl();

/* ── Sparkline mini chart ── */
function MiniChart({ data, color, height = 50 }: { data: number[]; color: string; height?: number }) {
  const _T = useExecTheme();
  const max = Math.max(...data, 1);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _w = 100 / Math.max(data.length, 1);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 1 }}>
      {data.map((v, i) => (
        <View key={i} style={{ flex: 1, height: Math.max((v / max) * height, 2), backgroundColor: color, borderRadius: 2, opacity: i >= data.length - 3 ? 1 : 0.6 }} />
      ))}
    </View>
  );
}

/* ── Star display ── */
function Stars({ rating, size = 14 }: { rating: number; size?: number }) {
  const T = useExecTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 2 }}>
      {[1, 2, 3, 4, 5].map(s => (
        <Ionicons key={s} name={s <= Math.round(rating) ? 'star' : 'star-outline'} size={size} color={s <= Math.round(rating) ? 'var(--app-warning)' : T.textMuted} />
      ))}
    </View>
  );
}

export default function NovaAnalyticsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const T = useExecTheme();
  const { data, loading: dataLoading, refetch: loadData } = useLiveQuery('/support/nova/analytics', { entity: 'nova', pollInterval: 30000 });
  const { data: uptimeTelemetry } = useLiveQuery('/support/nova/uptime?hours=24', { entity: 'nova_uptime', pollInterval: 30000 });
  const { data: convData, loading: convLoading } = useLiveQuery('/support/nova/conversations?limit=20', { entity: 'nova', pollInterval: 30000 });
  const loading = dataLoading || convLoading;
  const conversations = convData?.conversations || [];
  const [refreshing, setRefreshing] = useState(false);
  const [autoFaqLoading, setAutoFaqLoading] = useState(false);
  const [autoFaqResult, setAutoFaqResult] = useState<string>('');
  const [exporting, setExporting] = useState(false);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;

  const refresh = () => { setRefreshing(true); loadData(); };

  const handleExportCSV = useCallback(async () => {
    setExporting(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const _token = await api.get('/auth/me').then(() => '').catch(() => '');
      window.open(`${API_URL}/api/support/nova/export/csv?days=30`, '_blank');
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/NovaAnalyticsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setExporting(false); }
  }, []);

  const handleExportPDF = useCallback((convId: string) => {
    window.open(`${API_URL}/api/support/nova/export/pdf/${convId}`, '_blank');
  }, []);

  const handleAutoFaq = useCallback(async () => {
    setAutoFaqLoading(true);
    setAutoFaqResult('');
    try {
      const res = await api.post('/support/nova/auto-faq');
      setAutoFaqResult(res.data.message || 'Done');
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) {
      setAutoFaqResult('Failed to generate FAQs');
    } finally { setAutoFaqLoading(false); }
  }, []);

  if (loading) return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <AutoFixBanner domain="nova_analytics" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.001', 'Loading Nova Analytics...')}</Text>
    </View>
  );

  if (!data) return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <Ionicons name="alert-circle" size={36} color={T.error} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.002', 'Failed to load analytics')}</Text>
      <TouchableOpacity onPress={loadData} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: T.primary, borderRadius: 8 }} accessibilityLabel={tx('admin.novaAnalyticsPanel.auto.accessibility.001', 'Retry')}>
        <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.003', 'Retry')}</Text>
      </TouchableOpacity>
    </View>
  );

  const o = data.overview || {};
  const trendData = (data.daily_trend || []).map((d: any) => d.conversations);
  const ratingDist = data.rating_distribution || {};
  const maxRating = Math.max(...Object.values(ratingDist).map(Number), 1);
  const topics = data.top_topics || [];
  const feedback = data.recent_feedback || [];

  const kpiCards = [
    { label: 'Total Conversations', value: o.total_conversations || 0, icon: 'chatbubbles', color: T.primary, bg: T.primarySoft },
    { label: 'Avg Satisfaction', value: `${o.avg_rating || 0}/5`, icon: 'star', color: colors.warningText, bg: colors.warningSoft },
    { label: 'Satisfaction Rate', value: `${o.satisfaction_rate || 0}%`, icon: 'happy', color: T.successText, bg: T.successSoft },
    { label: 'Active Sessions', value: o.active_sessions || 0, icon: 'pulse', color: T.cyan, bg: T.cyanSoft },
    { label: 'Unique Users', value: o.unique_users || 0, icon: 'people', color: T.purpleText, bg: T.purpleSoft },
    { label: 'Total Feedback', value: o.total_feedback || 0, icon: 'chatbox-ellipses', color: T.pink, bg: T.pinkSoft },
    { label: 'Attachments', value: o.attachments_sent || 0, icon: 'attach', color: T.orangeText, bg: T.orangeSoft },
    { label: 'Audio Messages', value: o.audio_messages || 0, icon: 'mic', color: T.teal, bg: T.tealSoft },
  ];

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }} data-testid="nova-analytics-header" testID="nova-analytics-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="sparkles" size={22} color={T.primary} />
          </View>
          <View>
            <Text style={{ fontSize: 20, fontWeight: '800', color: T.text, letterSpacing: -0.5 }}>{tx('admin.novaAnalyticsPanel.auto.text.004', 'Nova AI Analytics')}</Text>
            <Text style={{ fontSize: 12, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.005', 'Real-time assistant performance')}</Text>
          </View>
        </View>
      </View>

      {/* Action Bar: Export + Auto-FAQ */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10, marginBottom: 20, backgroundColor: T.bgSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="nova-action-bar" testID="nova-action-bar">
        <TouchableOpacity data-testid="export-csv-btn" testID="export-csv-btn" onPress={handleExportCSV} disabled={exporting}
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.primary, paddingVertical: 12, borderRadius: 10, opacity: exporting ? 0.5 : 1 }}>
          {exporting ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="download" size={16} color="var(--app-primary-text)" />}
          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.006', 'Export All (CSV)')}</Text>
        </TouchableOpacity>
        <TouchableOpacity data-testid="auto-faq-btn" testID="auto-faq-btn" onPress={handleAutoFaq} disabled={autoFaqLoading}
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.purple, paddingVertical: 12, borderRadius: 10, opacity: autoFaqLoading ? 0.5 : 1 }}>
          {autoFaqLoading ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="bulb" size={16} color="var(--app-primary-text)" />}
          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.007', 'Auto-Generate FAQs')}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={refresh} data-testid="nova-analytics-refresh" testID="nova-analytics-refresh"
          style={{ flex: isWide ? 0.5 : 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.card, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: T.border }}>
          {refreshing ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh" size={16} color={T.primary} />}
          <Text style={{ color: T.primary, fontWeight: '700', fontSize: 13 }}>{tx('admin.novaAnalyticsPanel.auto.text.008', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>
      {autoFaqResult ? (
        <View style={{ marginBottom: 16, padding: 12, backgroundColor: autoFaqResult.includes('Failed') ? T.errorSoft : T.successSoft, borderRadius: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="auto-faq-result" testID="auto-faq-result">
          <Ionicons name={autoFaqResult.includes('Failed') ? 'alert-circle' : 'checkmark-circle'} size={16} color={autoFaqResult.includes('Failed') ? T.error : T.success} />
          <Text style={{ color: autoFaqResult.includes('Failed') ? T.error : T.success, fontSize: 13, fontWeight: '600', flex: 1 }}>{autoFaqResult}</Text>
          <TouchableOpacity accessibilityLabel={tx('admin.novaAnalyticsPanel.auto.accessibility.002', 'close button')} onPress={() => setAutoFaqResult('')}><Ionicons name="close" size={14} color={T.textMuted} /></TouchableOpacity>
        </View>
      ) : null}

      {/* Nova Uptime Telemetry */}
      <View
        style={{
          marginBottom: 20,
          backgroundColor: T.bgSoft,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: T.border,
          padding: 16,
        }}
        data-testid="nova-uptime-telemetry-tile"
        testID="nova-uptime-telemetry-tile"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="pulse" size={16} color={T.teal} />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>
              {tx('admin.novaAnalyticsPanel.uptime.title', 'Nova Reliability (24h)')}
            </Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid="nova-uptime-generated-at" testID="nova-uptime-generated-at">
            {uptimeTelemetry?.generated_at ? new Date(uptimeTelemetry.generated_at).toLocaleTimeString() : '—'}
          </Text>
        </View>

        <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10 }}>
          <View style={{ flex: 1, borderRadius: 10, padding: 12, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.uptime.successRatio', 'Success Ratio')}</Text>
            <Text style={{ color: T.successText, fontSize: 24, fontWeight: '900', marginTop: 3 }} data-testid="nova-uptime-success-ratio" testID="nova-uptime-success-ratio">
              {uptimeTelemetry?.success_ratio ?? 0}%
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.novaAnalyticsPanel.uptime.successHint', 'Assistant replies vs user prompts')}</Text>
          </View>

          <View style={{ flex: 1, borderRadius: 10, padding: 12, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.uptime.errorRatio', 'Error Ratio')}</Text>
            <Text style={{ color: T.error, fontSize: 24, fontWeight: '900', marginTop: 3 }} data-testid="nova-uptime-error-ratio" testID="nova-uptime-error-ratio">
              {uptimeTelemetry?.error_ratio ?? 0}%
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.novaAnalyticsPanel.uptime.errorHint', 'Nova-tagged client errors vs prompts')}</Text>
          </View>

          <View style={{ flex: 1, borderRadius: 10, padding: 12, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.uptime.uptimeScore', 'Uptime Score')}</Text>
            <Text style={{ color: T.primary, fontSize: 24, fontWeight: '900', marginTop: 3 }} data-testid="nova-uptime-score" testID="nova-uptime-score">
              {uptimeTelemetry?.uptime_ratio ?? 0}%
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>
              {tx('admin.novaAnalyticsPanel.uptime.window', 'Window')}: {uptimeTelemetry?.window_hours ?? 24}h
            </Text>
          </View>
        </View>
      </View>

      {/* KPI Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }} data-testid="nova-kpi-grid" testID="nova-kpi-grid">
        {kpiCards.map(k => (
          <View key={k.label} style={{ flex: 1, minWidth: isWide ? 160 : 140, backgroundColor: T.bgSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <View style={{ width: 32, height: 32, borderRadius: 9, backgroundColor: k.bg, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={k.icon as any} size={16} color={k.color} />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', flex: 1 }}>{k.label}</Text>
            </View>
            <Text style={{ fontSize: 26, fontWeight: '800', color: T.text, letterSpacing: -0.5 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* Row: Trend + Satisfaction */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Conversation Trend */}
        <View style={{ flex: 2, minWidth: 300, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-conversation-trend" testID="nova-conversation-trend">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="trending-up" size={16} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.009', 'Conversation Volume (30 days)')}</Text>
          </View>
          <MiniChart data={trendData} color={T.primary} height={80} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.010', '30 days ago')}</Text>
            <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.011', 'Today')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 12 }}>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 8, padding: 10, alignItems: 'center' }}>
              <Text style={{ fontSize: 16, fontWeight: '800', color: T.text }}>{o.total_messages || 0}</Text>
              <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.012', 'Total Messages')}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 8, padding: 10, alignItems: 'center' }}>
              <Text style={{ fontSize: 16, fontWeight: '800', color: T.text }}>{o.avg_msgs_per_conv || 0}</Text>
              <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.013', 'Avg per Conv')}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 8, padding: 10, alignItems: 'center' }}>
              <Text style={{ fontSize: 16, fontWeight: '800', color: T.primary }}>{o.user_messages || 0}</Text>
              <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.novaAnalyticsPanel.auto.text.014', 'User Msgs')}</Text>
            </View>
          </View>
        </View>

        {/* Satisfaction Distribution */}
        <View style={{ flex: 1, minWidth: 240, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-satisfaction-dist" testID="nova-satisfaction-dist">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="star" size={16} color={colors.warningText} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.015', 'Satisfaction')}</Text>
          </View>
          <View style={{ alignItems: 'center', marginBottom: 16 }}>
            <Text style={{ fontSize: 40, fontWeight: '800', color: T.text }}>{o.avg_rating || 0}</Text>
            <Stars rating={o.avg_rating || 0} size={18} />
            <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{o.total_feedback || 0} reviews</Text>
          </View>
          {[5, 4, 3, 2, 1].map(star => {
            const count = ratingDist[star] || 0;
            return (
              <View key={star} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: T.textSec, width: 16, textAlign: 'right' }}>{star}</Text>
                <Ionicons name="star" size={10} color={colors.warningText} />
                <View style={{ flex: 1, height: 8, backgroundColor: T.card, borderRadius: 4, overflow: 'hidden' }}>
                  <View style={{ height: '100%', width: `${(count / maxRating) * 100}%`, backgroundColor: star >= 4 ? T.success : star === 3 ? T.warning : T.error, borderRadius: 4 }} />
                </View>
                <Text style={{ fontSize: 11, fontWeight: '600', color: T.textMuted, width: 24, textAlign: 'right' }}>{count}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Row: Topics + Message Types */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Top Topics */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-top-topics" testID="nova-top-topics">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="chatbox" size={16} color={T.purpleText} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.016', 'Top Topics')}</Text>
          </View>
          {topics.length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.novaAnalyticsPanel.auto.text.017', 'No conversation data yet')}</Text>
          ) : (
            topics.map((t: any, i: number) => {
              const maxCount = topics[0]?.count || 1;
              const topicColors = [T.primary, T.purple, T.success, T.warning, T.cyan, T.pink, T.orange, T.teal, T.error, T.textSec];
              return (
                <View key={t.topic} style={{ marginBottom: 10 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{t.topic}</Text>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: topicColors[i % topicColors.length] }}>{t.count}</Text>
                  </View>
                  <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                    <View style={{ height: '100%', width: `${(t.count / maxCount) * 100}%`, backgroundColor: topicColors[i % topicColors.length], borderRadius: 3 }} />
                  </View>
                </View>
              );
            })
          )}
        </View>

        {/* Message Type Breakdown */}
        <View style={{ flex: 1, minWidth: 240, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-message-types" testID="nova-message-types">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="layers" size={16} color={T.cyan} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.018', 'Interaction Types')}</Text>
          </View>
          {[
            { label: 'Text Messages', value: (o.user_messages || 0) + (o.nova_messages || 0), icon: 'chatbubble-ellipses', color: T.primary },
            { label: 'Attachments Sent', value: o.attachments_sent || 0, icon: 'attach', color: T.orangeText },
            { label: 'Audio Messages', value: o.audio_messages || 0, icon: 'mic', color: T.teal },
            { label: 'Feedback Given', value: o.total_feedback || 0, icon: 'star', color: colors.warningText },
          ].map(item => (
            <View key={item.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <View style={{ width: 32, height: 32, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor(item.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={item.icon as any} size={16} color={item.color} />
              </View>
              <Text style={{ flex: 1, fontSize: 13, fontWeight: '600', color: T.text }}>{item.label}</Text>
              <Text style={{ fontSize: 18, fontWeight: '800', color: item.color }}>{item.value}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Recent Feedback Table */}
      {feedback.length > 0 && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-recent-feedback" testID="nova-recent-feedback">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="chatbox-ellipses" size={16} color={T.pink} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.019', 'Recent Feedback')}</Text>
            <View style={{ backgroundColor: T.pinkSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: T.pink }}>{feedback.length}</Text>
            </View>
          </View>
          <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, overflow: 'hidden' }}>
            <View style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.novaAnalyticsPanel.auto.text.020', 'User')}</Text>
              <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.novaAnalyticsPanel.auto.text.021', 'Rating')}</Text>
              <Text style={{ flex: 2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.novaAnalyticsPanel.auto.text.022', 'Comment')}</Text>
              <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.novaAnalyticsPanel.auto.text.023', 'Date')}</Text>
            </View>
            {feedback.slice(0, 10).map((f: any, i: number) => (
              <View key={f.feedback_id || i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: i < Math.min(feedback.length, 10) - 1 ? 1 : 0, borderBottomColor: T.border }}
                data-testid={`feedback-row-${i}`} testID={`feedback-row-${i}`}>
                <Text style={{ flex: 1, fontSize: 11, color: T.textSec, fontWeight: '600' }}>{(f.user_id || 'anonymous').slice(0, 12)}</Text>
                <View style={{ flex: 0.8, alignItems: 'center' }}><Stars rating={f.rating || 0} size={10} /></View>
                <Text style={{ flex: 2, fontSize: 11, color: T.text }} numberOfLines={2}>{f.comment || '—'}</Text>
                <Text style={{ flex: 0.8, fontSize: 10, color: T.textMuted, textAlign: 'right' }}>
                  {f.created_at ? new Date(f.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Conversation Export Table */}
      {conversations.length > 0 && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginTop: 20, borderWidth: 1, borderColor: T.border }} data-testid="nova-conversation-export" testID="nova-conversation-export">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="document-text" size={16} color={T.cyan} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.novaAnalyticsPanel.auto.text.024', 'Conversation Transcripts')}</Text>
            <View style={{ backgroundColor: T.cyanSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: T.cyan }}>{conversations.length}</Text>
            </View>
          </View>
          <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, overflow: 'hidden' }}>
            <View style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ flex: 1.2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.novaAnalyticsPanel.auto.text.025', 'User')}</Text>
              <Text style={{ flex: 2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.novaAnalyticsPanel.auto.text.026', 'First Message')}</Text>
              <Text style={{ flex: 0.6, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.novaAnalyticsPanel.auto.text.027', 'Msgs')}</Text>
              <Text style={{ flex: 0.6, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.novaAnalyticsPanel.auto.text.028', 'Rating')}</Text>
              <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.novaAnalyticsPanel.auto.text.029', 'Date')}</Text>
              <Text style={{ flex: 0.5, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.novaAnalyticsPanel.auto.text.030', 'PDF')}</Text>
            </View>
            {conversations.slice(0, 15).map((c: any, i: number) => (
              <View key={c.conversation_id} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: i < Math.min(conversations.length, 15) - 1 ? 1 : 0, borderBottomColor: T.border }}
                data-testid={`conv-row-${i}`} testID={`conv-row-${i}`}>
                <Text style={{ flex: 1.2, fontSize: 11, color: T.textSec, fontWeight: '600' }} numberOfLines={1}>{(c.user_id || 'anonymous').slice(0, 14)}</Text>
                <Text style={{ flex: 2, fontSize: 11, color: T.text }} numberOfLines={1}>{c.first_message || '—'}</Text>
                <Text style={{ flex: 0.6, fontSize: 12, color: T.primary, fontWeight: '700', textAlign: 'center' }}>{c.message_count}</Text>
                <View style={{ flex: 0.6, alignItems: 'center' }}>
                  {c.rating ? <Stars rating={c.rating} size={8} /> : <Text style={{ fontSize: 10, color: T.textMuted }}>—</Text>}
                </View>
                <Text style={{ flex: 0.8, fontSize: 10, color: T.textMuted, textAlign: 'center' }}>
                  {c.last_timestamp ? new Date(c.last_timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'}
                </Text>
                <View style={{ flex: 0.5, alignItems: 'center' }}>
                  <TouchableOpacity data-testid={`export-pdf-${i}`} testID={`export-pdf-${i}`} onPress={() => handleExportPDF(c.conversation_id)}
                    style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: T.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="document" size={12} color={T.error} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}
