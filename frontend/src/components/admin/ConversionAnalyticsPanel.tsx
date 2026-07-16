import React, { useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, ScrollView, TouchableOpacity, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAiInsight, AIInsightPanel, PriorityItem, FunnelItem, QuickWinItem } from './AIInsightHelpers';

// Theme-aware palette bound to --app-* CSS vars so module-scope helpers
// (KPI / FunnelBar / BarChart) render correctly in both light and dark
// modes without needing to hoist into the component tree.
const C = {
  accent: 'var(--app-primary)',
  orangeText: 'var(--app-warning)',
  purpleText: 'var(--app-info)',
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  muted: 'var(--app-text-muted)' as any,
  sec: 'var(--app-text-sec)' as any,
  green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)' as any,
  yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)' as any,
  teal: 'var(--app-primary)', orange: 'var(--app-warning)',
};

function makeC(AC: any) { return {
  bg: 'var(--app-bg)', card: 'var(--app-card-bg)', border: 'var(--app-border)',
  text: 'var(--app-text)', muted: 'var(--app-text-muted)', sec: 'var(--app-text-muted)',
  green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)',
  yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  teal: 'var(--app-primary)', orange: 'var(--app-warning)',
}; }

function KPI({ label, value, icon, color, sub }: any) {
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        <Ionicons name={icon} size={16} color={color} />
      </View>
      <Text style={{ fontSize: 28, fontWeight: '800', color, letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ fontSize: 11, color: C.sec, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

function FunnelBar({ stage, count, maxCount, color }: any) {
  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
  return (
    <View style={{ marginBottom: 12 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ fontSize: 12, color: C.text, fontWeight: '600' }}>{stage}</Text>
        <Text style={{ fontSize: 12, color, fontWeight: '700' }}>{count}</Text>
      </View>
      <View style={{ height: 10, backgroundColor: C.border, borderRadius: 5, overflow: 'hidden' }}>
        <View style={{ width: `${Math.max(pct, 2)}%`, height: '100%', backgroundColor: color, borderRadius: 5 }} />
      </View>
    </View>
  );
}

function DailyChart({ data, height = 120 }: { data: any[]; height?: number }) {
  if (!data?.length) return <Text style={{ color: C.muted, fontSize: 12 }}>{tx('admin.conversionAnalyticsPanel.auto.text.001', 'No data yet')}</Text>;
  const max = Math.max(...data.map((d: any) => d.opens || 0), 1);
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 6 }}>
        {data.map((d: any, i: number) => {
          const openH = Math.max(3, (d.opens / max) * (height - 35));
          const signH = d.signups > 0 ? Math.max(3, (d.signups / max) * (height - 35)) : 0;
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center', gap: 2 }}>
              <Text style={{ fontSize: 9, color: C.blue, fontWeight: '700' }}>{d.opens > 0 ? d.opens : ''}</Text>
              <View style={{ width: '70%', maxWidth: 32 }}>
                <View style={{ height: openH, backgroundColor: (globalThis as any).__alphaColor(C.blue, '50'), borderTopLeftRadius: 5, borderTopRightRadius: 5, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '25') }} />
                {signH > 0 && <View style={{ height: signH, backgroundColor: (globalThis as any).__alphaColor(C.green, '50'), borderBottomLeftRadius: 5, borderBottomRightRadius: 5, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '25'), borderTopWidth: 0 }} />}
              </View>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
        {data.map((d: any, i: number) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ fontSize: 10, color: C.muted }}>{d.day}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

const EVENT_ICONS: Record<string, { icon: string; color: string; label: string }> = {
  opened: { icon: 'eye', color: C.blue, label: 'Viewed' },
  signup_click: { icon: 'rocket', color: C.green, label: 'Sign Up' },
  dismiss: { icon: 'close-circle', color: C.muted, label: 'Dismissed' },
  backdrop_close: { icon: 'arrow-back', color: C.sec, label: 'Backdrop' },
};

export default function ConversionAnalyticsPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { data, loading, error: fetchError } = useLiveQuery('/newsletter/modal/analytics', { entity: 'newsletter', pollInterval: 60000 });
  const error = fetchError ? 'Failed to load' : '';
  const [showAi, setShowAi] = useState(false);
  const ai = useAiInsight('conversion_optimizer', 'conversion-optimizer');

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.accent} /></View>;
  if (error) return <View style={{ padding: 24 }}><Text style={{ color: C.red }}>{error}</Text></View>;
  if (!data) return null;

  const maxFunnel = Math.max(...(data.funnel?.map((f: any) => f.count) || [1]));

  return (
    <ScrollView style={{ flex: 1 }} {...getTestProps('conversion-analytics-panel')}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.blue, '20'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="analytics" size={18} color={C.blue} />
        </View>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{tx('admin.conversionAnalyticsPanel.auto.text.002', 'Conversion Analytics')}</Text>
          <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.conversionAnalyticsPanel.auto.text.003', 'Footer modal engagement and conversion tracking')}</Text>
        </View>
      </View>

      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }} {...getTestProps('conversion-kpi-row')}>
        <KPI label="Modal Opens" value={data.total_opens} icon="eye" color={C.blue} sub="All-time" />
        <KPI label="Sign Up Clicks" value={data.total_signups} icon="rocket" color={C.green} sub="Conversions" />
        <KPI label="Conversion Rate" value={`${data.conversion_rate}%`} icon="trending-up" color={C.accent} sub="Opens to signup" />
        <KPI label="Dismiss Rate" value={`${data.dismiss_rate}%`} icon="close-circle" color={C.orangeText} sub="Closed without action" />
      </View>

      {/* Charts Row */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Daily Trend */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} {...getTestProps('conversion-daily-chart')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="bar-chart" size={16} color={C.blue} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.conversionAnalyticsPanel.auto.text.004', 'Daily Activity')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginLeft: 'auto' }}>{tx('admin.conversionAnalyticsPanel.auto.text.005', 'Last 7 days')}</Text>
          </View>
          <DailyChart data={data.daily_trend} />
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.blue, '50') }} />
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.conversionAnalyticsPanel.auto.text.006', 'Opens')}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.green, '50') }} />
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.conversionAnalyticsPanel.auto.text.007', 'Sign Ups')}</Text>
            </View>
          </View>
        </View>

        {/* Conversion Funnel */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} {...getTestProps('conversion-funnel')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="funnel" size={16} color={C.purpleText} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.conversionAnalyticsPanel.auto.text.008', 'Conversion Funnel')}</Text>
          </View>
          {data.funnel?.map((f: any, i: number) => (
            <FunnelBar key={f.stage} stage={f.stage} count={f.count} maxCount={maxFunnel} color={f.color} />
          ))}
        </View>
      </View>

      {/* Bottom Row: Feature Stats + Recent Events */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Feature Popularity */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} {...getTestProps('conversion-features')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="star" size={16} color={C.yellow} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.conversionAnalyticsPanel.auto.text.009', 'Feature Performance')}</Text>
          </View>
          {data.feature_stats?.length > 0 ? data.feature_stats.map((f: any, i: number) => {
            const maxOpens = Math.max(...data.feature_stats.map((x: any) => x.opens), 1);
            return (
              <View key={i} style={{ paddingVertical: 8, borderBottomWidth: i < data.feature_stats.length - 1 ? 1 : 0, borderBottomColor: C.border }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Text style={{ fontSize: 12, color: C.text, fontWeight: '600', flex: 1 }} numberOfLines={1}>{f.feature}</Text>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <Text style={{ fontSize: 11, color: C.blue, fontWeight: '700' }}>{f.opens} opens</Text>
                    <Text style={{ fontSize: 11, color: C.green, fontWeight: '700' }}>{f.signups} clicks</Text>
                    <View style={{ backgroundColor: f.conversion_rate >= 50 ? (globalThis as any).__alphaColor(C.green, '20') : C.yellow + '20', paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: f.conversion_rate >= 50 ? C.green : C.yellow }}>{f.conversion_rate}%</Text>
                    </View>
                  </View>
                </View>
                <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, overflow: 'hidden' }}>
                  <View style={{ width: `${(f.opens / maxOpens) * 100}%`, height: '100%', backgroundColor: (globalThis as any).__alphaColor(C.blue, '40'), borderRadius: 2 }} />
                </View>
              </View>
            );
          }) : <Text style={{ color: C.muted, fontSize: 12 }}>{tx('admin.conversionAnalyticsPanel.auto.text.010', 'No modal interactions yet')}</Text>}
        </View>

        {/* Recent Events */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} {...getTestProps('conversion-recent')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="time" size={16} color={C.cyan} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.conversionAnalyticsPanel.auto.text.011', 'Recent Events')}</Text>
          </View>
          {data.recent_events?.length > 0 ? data.recent_events.slice(0, 10).map((ev: any, i: number) => {
            const info = EVENT_ICONS[ev.event] || { icon: 'ellipse', color: C.muted, label: ev.event };
            const ts = ev.created_at ? new Date(ev.created_at) : null;
            const timeStr = ts ? formatTimeAgo(ts) : '';
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderBottomWidth: i < Math.min(data.recent_events.length, 10) - 1 ? 1 : 0, borderBottomColor: C.border }}>
                <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(info.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={info.icon as any} size={12} color={info.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, color: C.text, fontWeight: '500' }} numberOfLines={1}>{ev.feature}</Text>
                  <Text style={{ fontSize: 10, color: info.color, fontWeight: '600' }}>{info.label}</Text>
                </View>
                <Text style={{ fontSize: 10, color: C.muted }}>{timeStr}</Text>
              </View>
            );
          }) : <Text style={{ color: C.muted, fontSize: 12 }}>{tx('admin.conversionAnalyticsPanel.auto.text.012', 'No events yet')}</Text>}
        </View>
      </View>

      <View style={{ height: 16 }} />

      {/* AI Insights Toggle */}
      <TouchableOpacity onPress={() => setShowAi(!showAi)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="conversion-ai-toggle" testID="conversion-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.conversionAnalyticsPanel.auto.text.013', 'AI Conversion Optimizer')}</Text>
        </View>
        <Ionicons name={showAi ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>

      {showAi && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'conversion_optimizer', postEndpoint: 'conversion-optimizer',
              title: 'AI Conversion Optimizer', subtitle: 'conversion funnels',
              scoreKey: 'conversion_health', scoreLabel: 'Conversion Health',
              summaryKey: 'executive_summary',
              sections: [
                { key: 'funnel_analysis', title: 'Funnel Analysis', icon: 'funnel', renderItem: (item, idx, total) => <FunnelItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'optimization_strategies', title: 'Optimization Strategies', icon: 'rocket', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'quick_wins', title: 'Quick Wins', icon: 'flash', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

function formatTimeAgo(date: Date): string {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}
