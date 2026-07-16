import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';
const AC = {
  bg: 'var(--app-bg)' as any, bgAlt: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any, borderStrong: 'var(--app-border-strong)' as any,
  text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any, textDim: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
};
const API = typeof window !== 'undefined' && (`https://${window.location.host}`) ? '' : (process.env.EXPO_PUBLIC_API_URL || process.env.REACT_APP_BACKEND_URL || '');

interface GrowthData {
  summary: {
    total_subscribers: number;
    active_subscribers: number;
    new_this_week: number;
    unsubscribed_this_week: number;
    growth_rate: number;
    churn_rate: number;
  };
  by_type: Record<string, { total: number; active: number; unsubscribed: number }>;
  growth_timeline: { date: string; platform: number; blog: number; all: number }[];
  campaigns: {
    digest_id: string;
    type: string;
    sent_at: string;
    total_recipients: number;
    opens: number;
    unique_opens: number;
    clicks: number;
    unique_clicks: number;
    open_rate: number;
    click_rate: number;
  }[];
  top_content: { slug: string; clicks: number; unique_readers: number }[];
  unsubscribe_trend: { date: string; count: number }[];
}

const tx = (_key: string, fallback: string) => fallback;

function KPICard({ label, value, sub, icon, color, trend }: {
  label: string; value: string | number; sub?: string; icon: string; color: string; trend?: 'up' | 'down' | 'flat';
}) {
  const trendIcon = trend === 'up' ? 'arrow-up' : trend === 'down' ? 'arrow-down' : 'remove';
  const trendColor = trend === 'up' ? 'var(--app-success)' : trend === 'down' ? 'var(--app-error)' : AC.textDim;
  return (
    <View style={{ flex: 1, minWidth: 180, backgroundColor: AC.bgAlt, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid={`growth-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`} testID={`growth-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(color, '1A'), justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name={icon as any} size={18} color={color} />
        </View>
        {trend && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(trendColor, '18') }}>
            <Ionicons name={trendIcon as any} size={10} color={trendColor} />
            <Text style={{ fontSize: 10, fontWeight: '700', color: trendColor }}>{trend === 'up' ? 'Growing' : trend === 'down' ? 'Declining' : 'Stable'}</Text>
          </View>
        )}
      </View>
      <Text style={{ fontSize: 28, fontWeight: '800', color: AC.text, letterSpacing: -1 }}>{value}</Text>
      <Text style={{ fontSize: 12, color: AC.textDim, marginTop: 3, fontWeight: '500' }}>{label}</Text>
      {sub && <Text style={{ fontSize: 11, color: color, marginTop: 5, fontWeight: '600' }}>{sub}</Text>}
    </View>
  );
}

function MiniBarChart({ data, color, height = 100 }: { data: number[]; color: string; height?: number }) {
  const max = Math.max(...data, 1);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height }} data-testid="mini-bar-chart" testID="mini-bar-chart">
      {data.map((v, i) => (
        <View key={i} style={{
          flex: 1, backgroundColor: (globalThis as any).__alphaColor(color, '30'), borderRadius: 4, minHeight: 4,
          height: `${(v / max) * 100}%` as any, position: 'relative',
        }}>
          <View style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            height: '100%', backgroundColor: color, borderRadius: 4, opacity: 0.8,
          }} />
        </View>
      ))}
    </View>
  );
}

// Module-scope types list used by TypeBreakdown (module-level helper).
// Digest category brand accents are theme-invariant on purpose — they
// communicate which newsletter an audience belongs to in both light and
// dark themes. @theme-ok
const types = [
  { key: 'platform', label: 'Platform Newsletter', color: 'var(--app-primary)', icon: 'rocket' },  /* @theme-ok brand accent */
  { key: 'blog', label: 'Blog Digest', color: 'var(--app-success)', icon: 'book' },  /* @theme-ok brand accent */
  { key: 'all', label: 'Both', color: 'var(--app-primary)', icon: 'layers' },  /* @theme-ok brand accent */
];

function TypeBreakdown({ byType }: { byType: GrowthData['by_type'] }) {
  const total = Object.values(byType).reduce((s, t) => s + t.total, 0) || 1;

  return (
    <View style={{ gap: 12 }} data-testid="type-breakdown" testID="type-breakdown">
      {types.map(t => {
        const d = byType[t.key] || { total: 0, active: 0, unsubscribed: 0 };
        const pct = Math.round((d.total / total) * 100);
        return (
          <View key={t.key} style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(t.color, '1A'), justifyContent: 'center', alignItems: 'center' }}>
                  <Ionicons name={t.icon as any} size={14} color={t.color} />
                </View>
                <Text style={{ fontSize: 13, fontWeight: '600', color: AC.text }}>{t.label}</Text>
              </View>
              <Text style={{ fontSize: 18, fontWeight: '800', color: t.color }}>{d.total}</Text>
            </View>
            <View style={{ height: 6, backgroundColor: AC.bgAlt, borderRadius: 3, overflow: 'hidden' }}>
              <View style={{ width: `${pct}%` as any, height: '100%', backgroundColor: t.color, borderRadius: 3 }} />
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
              <Text style={{ fontSize: 11, color: AC.textDim }}>{d.active} active</Text>
              <Text style={{ fontSize: 11, color: 'var(--app-error)' as any }}>{d.unsubscribed} unsub</Text>
              <Text style={{ fontSize: 11, color: AC.textMuted }}>{pct}% of total</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

function CampaignTable({ campaigns }: { campaigns: GrowthData['campaigns'] }) {
  if (!campaigns.length) {
    return <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 24 }}>{tx('admin.subscriberGrowthPanel.auto.text.001', 'No campaigns sent yet.')}</Text>;
  }
  return (
    <View style={{ gap: 6 }} data-testid="campaign-table" testID="campaign-table">
      <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: AC.border }}>
        {['Campaign', 'Type', 'Sent', 'Recipients', 'Opens', 'Clicks'].map(h => (
          <Text key={h} style={{ flex: h === 'Campaign' ? 2 : 1, fontSize: 10, fontWeight: '700', color: AC.textDim, textTransform: 'uppercase', letterSpacing: 0.5 }}>{h}</Text>
        ))}
      </View>
      {campaigns.slice(0, 8).map(c => {
        const typeColor = c.type === 'weekly_newsletter' ? 'var(--app-primary)' : 'var(--app-success)';
        const typeLabel = c.type === 'weekly_newsletter' ? 'Platform' : 'Blog';
        return (
          <View key={c.digest_id} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: AC.bgAlt, borderRadius: 8 }}>
            <Text style={{ flex: 2, fontSize: 12, fontWeight: '600', color: AC.textSec }} numberOfLines={1}>{c.digest_id}</Text>
            <View style={{ flex: 1 }}>
              <View style={{ alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(typeColor, '1A') }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: typeColor }}>{typeLabel}</Text>
              </View>
            </View>
            <Text style={{ flex: 1, fontSize: 11, color: AC.textMuted }}>{c.sent_at ? new Date(c.sent_at).toLocaleDateString() : '-'}</Text>
            <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: AC.text }}>{c.total_recipients}</Text>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: 'var(--app-success)' as any }}>{c.open_rate}%</Text>
              <Text style={{ fontSize: 9, color: AC.textDim }}>{c.unique_opens} unique</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: 'var(--app-warning)' as any }}>{c.click_rate}%</Text>
              <Text style={{ fontSize: 9, color: AC.textDim }}>{c.unique_clicks} unique</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

export default function SubscriberGrowthPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };


  const AC = useAdminTheme();
  const [data, setData] = useState<GrowthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggeringWeekly, setTriggeringWeekly] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/newsletter/subscriber-growth`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/subscriber-growth/hybrid-refresh',
    onTick: load,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });
  const triggerWeekly = async () => {
    setTriggeringWeekly(true);
    try {
      await fetch(`${API}/api/newsletter/trigger-weekly`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      setTimeout(load, 1500);
    } catch { /* noop */ }
    setTriggeringWeekly(false);
  };

  if (loading || !data) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 60 }}>
      <AutoFixBanner domain="subscriber_growth" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: AC.textDim, marginTop: 12, fontSize: 13 }}>{tx('admin.subscriberGrowthPanel.auto.text.002', 'Loading subscriber growth data...')}</Text>
      </View>
    );
  }

  const { summary, by_type, growth_timeline, campaigns, top_content } = data;
  const growthTrend = summary.growth_rate > 2 ? 'up' : summary.growth_rate < 0 ? 'down' : 'flat';
  const churnTrend = summary.churn_rate > 3 ? 'down' : summary.churn_rate > 0 ? 'flat' : 'up';
  const timelineValues = growth_timeline.map(g => g.platform + g.blog + g.all);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }} data-testid="subscriber-growth-panel" testID="subscriber-growth-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: AC.text, letterSpacing: -0.3 }}>{tx('admin.subscriberGrowthPanel.auto.text.003', 'Subscriber Growth Dashboard')}</Text>
          <Text style={{ fontSize: 13, color: AC.textDim, marginTop: 2 }}>{tx('admin.subscriberGrowthPanel.auto.text.004', 'Track growth trends, campaign performance, and subscriber engagement')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={load} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: AC.border, borderWidth: 1, borderColor: AC.borderStrong }} data-testid="refresh-growth-btn" testID="refresh-growth-btn">
            <Ionicons name="refresh" size={14} color={AC.textMuted} />
            <Text style={{ color: AC.textMuted, fontSize: 12, fontWeight: '600' }}>{tx('admin.subscriberGrowthPanel.auto.text.005', 'Refresh')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={triggerWeekly} disabled={triggeringWeekly} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primary, opacity: triggeringWeekly ? 0.6 : 1 }} data-testid="trigger-weekly-btn" testID="trigger-weekly-btn">
            {triggeringWeekly ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="paper-plane" size={14} color="var(--app-primary-text)" />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriberGrowthPanel.auto.text.006', 'Send Weekly')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <KPICard label="Total Subscribers" value={summary.total_subscribers} sub={`${summary.active_subscribers} currently active`} icon="people" color={'var(--app-primary)'} trend={growthTrend} />
        <KPICard label="New This Week" value={summary.new_this_week} sub={`${summary.growth_rate}% growth rate`} icon="trending-up" color={'var(--app-success)'} trend={growthTrend} />
        <KPICard label="Unsubscribed This Week" value={summary.unsubscribed_this_week} sub={`${summary.churn_rate}% churn rate`} icon="person-remove" color={'var(--app-error)'} trend={churnTrend} />
        <KPICard label="Active Campaigns" value={campaigns.length} sub="Total campaigns sent" icon="mail" color={'var(--app-primary)'} />
      </View>

      {/* Growth Timeline + Type Breakdown */}
      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
        {/* Growth Chart */}
        <View style={{ flex: 2, minWidth: 340, backgroundColor: AC.bgAlt, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="growth-chart-section" testID="growth-chart-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="bar-chart" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.subscriberGrowthPanel.auto.text.007', 'Subscriber Growth (30 Days)')}</Text>
          </View>
          {growth_timeline.length > 0 ? (
            <>
              <MiniBarChart data={timelineValues} color={'var(--app-primary)'} height={120} />
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                <Text style={{ fontSize: 10, color: AC.textDim }}>{growth_timeline[0]?.date}</Text>
                <Text style={{ fontSize: 10, color: AC.textDim }}>{growth_timeline[growth_timeline.length - 1]?.date}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 16, marginTop: 12 }}>
                {[
                  { label: 'Platform', color: colors.primary, total: growth_timeline.reduce((s, g) => s + g.platform, 0) },
                  { label: 'Blog', color: colors.successText, total: growth_timeline.reduce((s, g) => s + g.blog, 0) },
                ].map(l => (
                  <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: l.color }} />
                    <Text style={{ fontSize: 11, color: AC.textMuted }}>{l.label}: {l.total}</Text>
                  </View>
                ))}
              </View>
            </>
          ) : (
            <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 30 }}>{tx('admin.subscriberGrowthPanel.auto.text.008', 'No subscription data in the last 30 days.')}</Text>
          )}
        </View>

        {/* Type Breakdown */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: AC.bgAlt, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="type-breakdown-section" testID="type-breakdown-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="git-branch" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.subscriberGrowthPanel.auto.text.009', 'Subscription Types')}</Text>
          </View>
          <TypeBreakdown byType={by_type} />
        </View>
      </View>

      {/* Campaign Performance */}
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="campaign-performance-section" testID="campaign-performance-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="stats-chart" size={16} color={'var(--app-warning)'} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.subscriberGrowthPanel.auto.text.010', 'Campaign Performance')}</Text>
        </View>
        <CampaignTable campaigns={campaigns} />
      </View>

      {/* Top Content */}
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="top-content-section" testID="top-content-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="flame" size={16} color="var(--app-primary)" />
          <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.subscriberGrowthPanel.auto.text.011', 'Top Performing Content')}</Text>
        </View>
        {top_content.length > 0 ? (
          <View style={{ gap: 8 }}>
            {top_content.map((c, i) => (
              <View key={c.slug} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 14, backgroundColor: AC.border, borderRadius: 8, gap: 12 }}>
                <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: i < 3 ? 'var(--app-warning-soft)' : AC.border, justifyContent: 'center', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: i < 3 ? 'var(--app-warning)' : AC.textDim }}>#{i + 1}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: AC.textSec }} numberOfLines={1}>{c.slug.replace(/-/g, ' ')}</Text>
                  <Text style={{ fontSize: 11, color: AC.textDim, marginTop: 2 }}>{c.unique_readers} unique readers</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: colors.successText }}>{c.clicks}</Text>
                  <Text style={{ fontSize: 9, color: AC.textDim }}>{tx('admin.subscriberGrowthPanel.auto.text.012', 'clicks')}</Text>
                </View>
              </View>
            ))}
          </View>
        ) : (
          <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 24 }}>{tx('admin.subscriberGrowthPanel.auto.text.013', 'No content engagement data yet. Click tracking begins after the first campaign is sent.')}</Text>
        )}
      </View>
    </ScrollView>
  );
}
