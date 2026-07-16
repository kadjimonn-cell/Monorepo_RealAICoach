// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const T = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  cardHover: 'var(--app-surface-hover)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  primarySoft: 'var(--app-primary-soft)' as any,
  success: 'var(--app-success)' as any,
  successSoft: 'var(--app-success-soft)' as any,
  warning: 'var(--app-warning)' as any,
  warningSoft: 'var(--app-warning-soft)' as any,
  error: 'var(--app-error)' as any,
  errorSoft: 'var(--app-error-soft)' as any,
  purple: 'var(--app-info)' as any,
  purpleSoft: 'var(--app-primary-soft)' as any,
  cyan: 'var(--app-info)' as any,
  cyanSoft: 'var(--app-info-soft)' as any,
  pink: 'var(--app-primary)', pinkSoft: 'var(--app-primary-soft)',
  orange: 'var(--app-warning)' as any,
  orangeSoft: 'var(--app-warning-soft)' as any,
  teal: 'var(--app-primary)', tealSoft: 'var(--app-primary-soft)',
  successText: 'var(--app-success)' as any,
  purpleText: 'var(--app-info)' as any,
};

const tx = (_key: string, fallback: string) => fallback;

const CAT_COLORS: Record<string, string> = {
  social: 'var(--app-primary)', email: 'var(--app-success)', blog: 'var(--app-warning)', business: 'var(--app-primary)', unknown: 'var(--app-text)', // @theme-ok brand/role/state identifier
};

const TONE_COLORS: Record<string, string> = {
  professional: 'var(--app-primary)', casual: 'var(--app-success)', persuasive: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  friendly: 'var(--app-primary)', formal: 'var(--app-primary)', humorous: 'var(--app-warning)', // @theme-ok brand/role/state identifier
};

interface Props { colors?: any; }

/* ─── Sparkline Bar Chart ─── */
function SparkBars({ data, color, height = 48 }: { data: number[]; color: string; height?: number }) {
  if (!data || data.length < 2) return <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.001', 'No data')}</Text>;
  const max = Math.max(...data, 1);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 1, height }} data-testid="spark-bars" testID="spark-bars">
      {data.map((v, i) => (
        <View key={i} style={{
          flex: 1, borderRadius: 2,
          height: Math.max(2, (v / max) * height),
          backgroundColor: color,
          opacity: 0.35 + (i / data.length) * 0.65,
        }} />
      ))}
    </View>
  );
}

/* ─── Horizontal Distribution Bar ─── */
function DistBar({ items, colors }: { items: { label: string; value: number }[]; colors: Record<string, string> }) {
  const total = items.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <View style={{ gap: 8 }}>
      {/* Stacked bar */}
      <View style={{ flexDirection: 'row', height: 20, borderRadius: 6, overflow: 'hidden', backgroundColor: T.bgSoft }}>
        {items.map((item, i) => {
          const pct = (item.value / total) * 100;
          if (pct < 1) return null;
          return <View key={i} style={{ width: `${pct}%` as any, height: '100%', backgroundColor: colors[item.label] || T.primary }} />;
        })}
      </View>
      {/* Legend */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {items.map((item, i) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors[item.label] || T.primary }} />
            <Text style={{ color: T.textSec, fontSize: 11 }}>{item.label}</Text>
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{item.value}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>({Math.round((item.value / total) * 100)}%)</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Heatmap Row ─── */
function HourlyHeatmap({ data }: { data: { hour: string; count: number }[] }) {
  const max = Math.max(...data.map(d => d.count), 1);
  return (
    <View data-testid="hourly-heatmap" testID="hourly-heatmap">
      <View style={{ flexDirection: 'row', gap: 3, flexWrap: 'wrap' }}>
        {data.map((d, i) => {
          const intensity = d.count / max;
          return (
            <View key={i} style={{
              width: 28, height: 28, borderRadius: 6, alignItems: 'center', justifyContent: 'center',
              backgroundColor: intensity > 0.7 ? T.primary : intensity > 0.3 ? T.primarySoft : intensity > 0 ? T.bgSoft : T.bg,
              borderWidth: 1, borderColor: T.border,
            }}>
              <Text style={{ color: intensity > 0.7 ? 'var(--app-primary-text)' : T.textMuted, fontSize: 9, fontWeight: '700' }}>
                {parseInt(d.hour)}
              </Text>
              {d.count > 0 && (
                <Text style={{ color: intensity > 0.7 ? 'var(--app-primary)' : T.textMuted, fontSize: 7 }}>{d.count}</Text>
              )}
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.002', '12 AM')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.003', '6 AM')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.004', '12 PM')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.005', '6 PM')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.006', '11 PM')}</Text>
      </View>
    </View>
  );
}

/* ─── KPI Card ─── */
function KPI({ label, value, sub, icon, color, trend }: {
  label: string; value: string | number; sub?: string;
  icon: keyof typeof Ionicons.glyphMap; color: string; trend?: number;
}) {
  return (
    <View style={{
      backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border,
      flex: 1, minWidth: 160, gap: 10,
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={18} color={color} />
        </View>
        {trend !== undefined && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: trend >= 0 ? T.successSoft : T.errorSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
            <Ionicons name={trend >= 0 ? 'trending-up' : 'trending-down'} size={12} color={trend >= 0 ? T.success : T.error} />
            <Text style={{ color: trend >= 0 ? T.success : T.error, fontSize: 11, fontWeight: '700' }}>{Math.abs(trend)}%</Text>
          </View>
        )}
      </View>
      <Text style={{ color: T.text, fontSize: 26, fontWeight: '800', letterSpacing: -0.5 }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      {sub && <Text style={{ color: T.textSec, fontSize: 11 }}>{sub}</Text>}
    </View>
  );
}

/* ─── Card Wrapper ─── */
function Card({ title, icon, children, rightEl }: {
  title: string; icon: keyof typeof Ionicons.glyphMap; children: React.ReactNode; rightEl?: React.ReactNode;
}) {
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 14, borderBottomWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name={icon} size={16} color={T.primary} />
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{title}</Text>
        </View>
        {rightEl}
      </View>
      <View style={{ padding: 18 }}>{children}</View>
    </View>
  );
}

/* ─── Main Panel ─── */
export default function ContentStudioAnalyticsPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const _AC = useAdminTheme();
  const { data, loading, refetch } = useLiveQuery('/admin/content-studio/analytics', {
    entity: 'content-studio',
    pollInterval: 30000,
  });
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  const isMobile = width < 640;

  if (loading && !data) {
    return (
      <View style={{ paddingVertical: 60, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.007', 'Loading Content Studio Analytics...')}</Text>
      </View>
    );
  }

  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.008', 'Failed to load analytics')}</Text>;

  const summary = data.summary || {};
  const dailyVol = data.daily_volume || [];
  const templateDist = data.template_distribution || [];
  const toneDist = data.tone_distribution || [];
  const catDist = data.category_distribution || [];
  const hourly = data.hourly_heatmap || [];
  const topUsers = data.top_users || [];

  const dailyGens = dailyVol.map((d: any) => d.generations);
  const dailyWords = dailyVol.map((d: any) => d.words);

  return (
    <View data-testid="content-studio-analytics-panel" testID="content-studio-analytics-panel" style={{ gap: 20 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: T.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="create" size={20} color={T.purpleText} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.009', 'Content Studio Analytics')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.010', 'Real-time AI content generation metrics')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.successSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.success }} />
            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '600' }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.011', 'Live')}</Text>
          </View>
          <TouchableOpacity onPress={refetch} style={{ padding: 8, backgroundColor: T.bgSoft, borderRadius: 8 }} data-testid="cs-analytics-refresh" testID="cs-analytics-refresh">
            <Ionicons name="refresh" size={16} color={T.textSec} />
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Row */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
        <KPI label="Total Generations" value={summary.total_generations || 0} sub="All time" icon="document-text" color={T.purpleText} trend={summary.trend_7d_pct} />
        <KPI label="Last 7 Days" value={summary.last_7d_generations || 0} sub="This week" icon="calendar" color={T.primary} />
        <KPI label="Last 30 Days" value={summary.last_30d_generations || 0} sub="This month" icon="bar-chart" color={T.cyan} />
        <KPI label="Total Words" value={summary.word_stats?.total_words?.toLocaleString() || '0'} sub={`Avg: ${summary.word_stats?.avg_words || 0} per generation`} icon="text" color={T.teal} />
      </View>

      {/* Charts Row 1: Daily Volume + Template Popularity */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        <View style={{ flex: isWide ? 3 : 1 }}>
          <Card title="30-Day Generation Volume" icon="pulse">
            <View style={{ gap: 12 }}>
              <SparkBars data={dailyGens} color={T.purpleText} height={60} />
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{dailyVol[0]?.date || ''}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{dailyVol[dailyVol.length - 1]?.date || ''}</Text>
              </View>
              <View style={{ height: 1, backgroundColor: T.border, marginVertical: 4 }} />
              <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.012', 'Word Output')}</Text>
              <SparkBars data={dailyWords} color={T.cyan} height={40} />
            </View>
          </Card>
        </View>
        <View style={{ flex: isWide ? 2 : 1 }}>
          <Card title="Template Popularity" icon="podium">
            <View style={{ gap: 8 }}>
              {templateDist.slice(0, 8).map((item: any, i: number) => {
                const maxVal = templateDist[0]?.count || 1;
                const pct = Math.max(4, (item.count / maxVal) * 100);
                return (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: T.textSec, fontSize: 11, width: isMobile ? 80 : 120 }} numberOfLines={1}>{item.template}</Text>
                    <View style={{ flex: 1, height: 20, backgroundColor: T.bgSoft, borderRadius: 5, overflow: 'hidden' }}>
                      <View style={{ width: `${pct}%` as any, height: '100%', backgroundColor: (globalThis as any).__alphaColor(T.purple, '50'), borderRadius: 5 }} />
                    </View>
                    <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', minWidth: 28, textAlign: 'right' }}>{item.count}</Text>
                  </View>
                );
              })}
            </View>
          </Card>
        </View>
      </View>

      {/* Charts Row 2: Category + Tone */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        <View style={{ flex: 1 }}>
          <Card title="Category Distribution" icon="grid">
            <DistBar
              items={catDist.map((d: any) => ({ label: d.category, value: d.count }))}
              colors={CAT_COLORS}
            />
          </Card>
        </View>
        <View style={{ flex: 1 }}>
          <Card title="Tone Usage" icon="color-palette">
            <DistBar
              items={toneDist.map((d: any) => ({ label: d.tone, value: d.count }))}
              colors={TONE_COLORS}
            />
          </Card>
        </View>
      </View>

      {/* Charts Row 3: Heatmap + Top Users */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        <View style={{ flex: 1 }}>
          <Card title="Generation Heatmap (by Hour)" icon="time">
            <HourlyHeatmap data={hourly} />
          </Card>
        </View>
        <View style={{ flex: 1 }}>
          <Card title="Top Content Creators" icon="people">
            {topUsers.length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.contentStudioAnalyticsPanel.auto.text.013', 'No users yet')}</Text>
            ) : (
              <View style={{ gap: 8 }}>
                {topUsers.slice(0, 8).map((u: any, i: number) => (
                  <View key={i} style={{
                    flexDirection: 'row', alignItems: 'center', gap: 10,
                    paddingVertical: 8, paddingHorizontal: 10, borderRadius: 10,
                    backgroundColor: i === 0 ? T.purpleSoft : 'transparent',
                  }} data-testid={`top-user-${i}`} testID={`top-user-${i}`}>
                    <View style={{
                      width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center',
                      backgroundColor: i === 0 ? T.purple : i < 3 ? T.primarySoft : T.bgSoft,
                    }}>
                      <Text style={{ color: i < 3 ? 'var(--app-primary-text)' : T.textMuted, fontSize: 11, fontWeight: '800' }}>
                        {i === 0 ? '\u2605' : `${i + 1}`}
                      </Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{u.name}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{u.email}</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{u.generations}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }}>{(u.total_words || 0).toLocaleString()} words</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </Card>
        </View>
      </View>

      {/* Footer */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8 }}>
        <Ionicons name="sync" size={12} color={T.textMuted} />
        <Text style={{ color: T.textMuted, fontSize: 10 }}>Auto-refreshes every 30s &middot; Last: {data.generated_at ? new Date(data.generated_at).toLocaleTimeString() : 'N/A'}</Text>
      </View>
    </View>
  );
}
