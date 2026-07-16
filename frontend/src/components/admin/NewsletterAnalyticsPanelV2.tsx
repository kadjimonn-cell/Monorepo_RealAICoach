import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AutoFixBanner from './AutoFixBanner';
import { useAiInsight, AIInsightPanel, PriorityItem, QuickWinItem } from './AIInsightHelpers';
import NewsletterSubjectABWidget from './NewsletterSubjectABWidget';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface Analytics {
  subscribers: { total: number; active: number; unsubscribed: number; last_30d: number; sources: Record<string, number> };
  engagement: { total_opens: number; total_clicks: number; unique_openers: number; unique_clickers: number; open_rate: number; click_rate: number };
  top_articles: { slug: string; clicks: number; unique_readers: number }[];
  digests: { digest_id: string; sent_at: string; total_recipients: number; post_slugs?: string[] }[];
  opens_by_digest: { digest_id: string; opens: number; unique_opens: number }[];
  clicks_by_digest: { digest_id: string; clicks: number; unique_clicks: number }[];
  category_preferences: Record<string, number>;
}

const tx = (_key: string, fallback: string) => fallback;

const CAT_COLORS: Record<string, string> = {
  'Industry Insights': 'var(--app-primary)', // @theme-ok brand/role/state identifier
  'Product Update': 'var(--app-success)', // @theme-ok brand/role/state identifier
  'Tips & Tricks': 'var(--app-warning)', // @theme-ok brand/role/state identifier
  Research: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  'Company News': 'var(--app-primary)', // @theme-ok brand/role/state identifier
  Enterprise: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

const defaultAnalytics: Analytics = {
  subscribers: { total: 0, active: 0, unsubscribed: 0, last_30d: 0, sources: {} },
  engagement: { total_opens: 0, total_clicks: 0, unique_openers: 0, unique_clickers: 0, open_rate: 0, click_rate: 0 },
  top_articles: [],
  digests: [],
  opens_by_digest: [],
  clicks_by_digest: [],
  category_preferences: {},
};

function MetricCard({
  label,
  value,
  sub,
  icon,
  accent,
  bg,
  border,
  text,
  muted,
  testId,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: string;
  accent: string;
  bg: string;
  border: string;
  text: string;
  muted: string;
  testId: string;
}) {
  return (
    <View
      style={{
        flex: 1,
        minWidth: 170,
        backgroundColor: bg,
        borderRadius: 14,
        padding: 14,
        borderWidth: 1,
        borderColor: border,
        gap: 6,
      }}
      data-testid={testId}
      testID={testId}
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: `${accent}20`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={15} color={accent} />
        </View>
      </View>
      <Text style={{ color: text, fontSize: 22, fontWeight: '800' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
      <Text style={{ color: muted, fontSize: 11, fontWeight: '600' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label}</Text>
      {sub ? <Text style={{ color: accent, fontSize: 10, fontWeight: '700' }} data-testid={`${testId}-sub`} testID={`${testId}-sub`}>{sub}</Text> : null}
    </View>
  );
}

function SectionCard({ title, icon, iconColor, children, testId, bg, border, text }: any) {
  return (
    <View
      style={{ flex: 1, minWidth: 300, backgroundColor: bg, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: border, gap: 12 }}
      data-testid={testId}
      testID={testId}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={icon} size={16} color={iconColor} />
        <Text style={{ color: text, fontSize: 14, fontWeight: '700' }} data-testid={`${testId}-title`} testID={`${testId}-title`}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function BarList({ data, maxVal, muted, text, track }: { data: { label: string; value: number; color: string }[]; maxVal: number; muted: string; text: string; track: string }) {
  return (
    <View style={{ gap: 8 }}>
      {data.map((item) => (
        <View key={item.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Text style={{ width: 120, color: muted, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{item.label}</Text>
          <View style={{ flex: 1, height: 22, borderRadius: 7, backgroundColor: track, overflow: 'hidden' }}>
            <View style={{ width: `${maxVal ? (item.value / maxVal) * 100 : 0}%` as any, minWidth: item.value > 0 ? 8 : 0, height: '100%', backgroundColor: item.color, borderRadius: 7 }} />
          </View>
          <Text style={{ width: 38, textAlign: 'right', color: text, fontSize: 11, fontWeight: '700' }}>{item.value}</Text>
        </View>
      ))}
    </View>
  );
}

export default function NewsletterAnalyticsPanelV2({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors: themeColors } = useTheme();
  const palette = colors || themeColors;
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const [data, setData] = useState<Analytics>(defaultAnalytics);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<string>('');
  const [actionStatus, setActionStatus] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  const cardBg = palette.card;
  const border = palette.border;
  const text = palette.text;
  const muted = palette.textMuted;
  const soft = palette.bgSoft || palette.cardMuted || palette.bg;

  const normalizePayload = (raw: any): Analytics => {
    if (raw?.subscribers && raw?.engagement) {
      return {
        subscribers: {
          total: Number(raw.subscribers.total || 0),
          active: Number(raw.subscribers.active || 0),
          unsubscribed: Number(raw.subscribers.unsubscribed || 0),
          last_30d: Number(raw.subscribers.last_30d || 0),
          sources: raw.subscribers.sources || {},
        },
        engagement: {
          total_opens: Number(raw.engagement.total_opens || 0),
          total_clicks: Number(raw.engagement.total_clicks || 0),
          unique_openers: Number(raw.engagement.unique_openers || 0),
          unique_clickers: Number(raw.engagement.unique_clickers || 0),
          open_rate: Number(raw.engagement.open_rate || 0),
          click_rate: Number(raw.engagement.click_rate || 0),
        },
        top_articles: Array.isArray(raw.top_articles) ? raw.top_articles : [],
        digests: Array.isArray(raw.digests) ? raw.digests : [],
        opens_by_digest: Array.isArray(raw.opens_by_digest) ? raw.opens_by_digest : [],
        clicks_by_digest: Array.isArray(raw.clicks_by_digest) ? raw.clicks_by_digest : [],
        category_preferences: raw.category_preferences || {},
      };
    }

    return {
      ...defaultAnalytics,
      subscribers: {
        total: Number(raw?.total_subscribers || 0),
        active: Number(raw?.total_subscribers || 0),
        unsubscribed: 0,
        last_30d: Number(raw?.this_week_signups || 0),
        sources: Array.isArray(raw?.source_breakdown)
          ? raw.source_breakdown.reduce((acc: Record<string, number>, item: any) => {
              if (item?.source) acc[item.source] = Number(item.count || 0);
              return acc;
            }, {})
          : {},
      },
    };
  };

  const load = async (mode: 'initial' | 'manual' | 'silent' = 'silent') => {
    if (mode === 'initial') setLoading(true);
    if (mode === 'manual') setRefreshing(true);
    try {
      const response = await api.get('/newsletter/analytics');
      setData(normalizePayload(response?.data || {}));
      setLastLoadedAt(new Date().toISOString());
      if (mode === 'manual') {
        setActionStatus({ type: 'success', message: 'Analytics refreshed successfully.' });
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.response?.data?.message || 'Unable to refresh analytics right now.';
      setActionStatus({ type: 'error', message: msg });
    } finally {
      if (mode === 'initial') setLoading(false);
      if (mode === 'manual') setRefreshing(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load('initial'); }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/newsletter-analytics-v2/hybrid-refresh',
    onTick: () => load('silent'),
    runOnMount: false,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const triggerDigest = async () => {
    setTriggering(true);
    try {
      const response = await api.post('/newsletter/trigger-digest');
      const payload = response?.data || {};
      if (payload.success) {
        const sent = Number(payload.sent || 0);
        setActionStatus({
          type: sent > 0 ? 'success' : 'info',
          message: sent > 0 ? `Digest sent successfully to ${sent} recipients.` : 'Digest completed, but no eligible recipients were found.',
        });
        await load('silent');
      } else {
        setActionStatus({ type: 'error', message: payload.error || 'Digest send failed.' });
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.response?.data?.message || 'Digest send failed.';
      setActionStatus({ type: 'error', message: msg });
    } finally {
      setTriggering(false);
    }
  };

  const sourceData = useMemo(
    () => Object.entries(data.subscribers.sources || {}).map(([label, value]) => ({ label, value, color: colors.primary })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.subscribers.sources],
  );
  const categoryData = useMemo(
    () => Object.entries(data.category_preferences || {}).map(([label, value]) => ({ label, value, color: CAT_COLORS[label] || muted })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.category_preferences],
  );
  const articleData = useMemo(
    () => (data.top_articles || []).map((a) => ({ label: String(a.slug || '').replace(/-/g, ' ').slice(0, 40), value: Number(a.clicks || 0), color: colors.successText })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.top_articles],
  );
  const maxSource = Math.max(1, ...sourceData.map((d) => d.value));
  const maxCategory = Math.max(1, ...categoryData.map((d) => d.value));
  const maxArticle = Math.max(1, ...articleData.map((d) => d.value));

  const newsletterHealth = Math.max(0, Math.min(100, Math.round((data.engagement.open_rate * 0.6) + (data.engagement.click_rate * 0.4) + (data.subscribers.active > 0 ? 8 : 0))));
  const digestComparison = useMemo(() => {
    const sorted = [...(data.digests || [])].sort((a, b) => {
      const aTs = a?.sent_at ? new Date(a.sent_at).getTime() : 0;
      const bTs = b?.sent_at ? new Date(b.sent_at).getTime() : 0;
      return bTs - aTs;
    });
    if (sorted.length < 2) return null;

    const current = sorted[0];
    const previous = sorted[1];
    const metricFor = (digest: any) => {
      const recipients = Number(digest?.total_recipients || 0);
      const openData = data.opens_by_digest.find((o) => o.digest_id === digest.digest_id);
      const clickData = data.clicks_by_digest.find((c) => c.digest_id === digest.digest_id);
      const uniqueOpens = Number(openData?.unique_opens || 0);
      const uniqueClicks = Number(clickData?.unique_clicks || 0);
      return {
        recipients,
        uniqueOpens,
        uniqueClicks,
        openRate: recipients > 0 ? Number(((uniqueOpens / recipients) * 100).toFixed(1)) : 0,
        clickRate: recipients > 0 ? Number(((uniqueClicks / recipients) * 100).toFixed(1)) : 0,
      };
    };

    return {
      current,
      previous,
      currentMetrics: metricFor(current),
      previousMetrics: metricFor(previous),
    };
  }, [data.digests, data.opens_by_digest, data.clicks_by_digest]);

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 48, backgroundColor: palette.bg }} data-testid="newsletter-analytics-panel" testID="newsletter-analytics-panel">
        <AutoFixBanner domain="newsletter" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: muted, marginTop: 10, fontSize: 13 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.001', 'Loading newsletter analytics...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: palette.bg }} contentContainerStyle={{ padding: isMobile ? 14 : 20, gap: 14 }} data-testid="newsletter-analytics-panel" testID="newsletter-analytics-panel">
      <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 16, padding: isMobile ? 14 : 18, gap: 12 }}>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 10 }}>
          <View style={{ gap: 5 }}>
            <Text style={{ color: text, fontSize: 20, fontWeight: '800' }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.002', 'Newsletter Analytics')}</Text>
            <Text style={{ color: muted, fontSize: 12 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.003', 'Rebuilt dashboard for subscriptions, engagement, digests, and AI recommendations.')}</Text>
            <Text style={{ color: muted, fontSize: 10 }} data-testid="newsletter-analytics-last-updated" testID="newsletter-analytics-last-updated">
              Last updated: {lastLoadedAt ? lastLoadedAt.replace('T', ' ').slice(0, 19) : 'just now'}
            </Text>
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="newsletter-health-pill" testID="newsletter-health-pill">
              <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '800' }}>HEALTH {newsletterHealth}</Text>
            </View>
          </View>
        </View>

        {actionStatus ? (
          <View
            style={{
              backgroundColor: actionStatus.type === 'error' ? 'var(--app-error-soft)' : actionStatus.type === 'success' ? 'var(--app-primary-soft)' : 'var(--app-primary-soft)',
              borderWidth: 1,
              borderColor: actionStatus.type === 'error' ? 'var(--app-error-soft)' : actionStatus.type === 'success' ? 'var(--app-success-soft)' : 'var(--app-primary-soft)',
              borderRadius: 10,
              paddingHorizontal: 10,
              paddingVertical: 7,
            }}
            data-testid="newsletter-analytics-action-status"
            testID="newsletter-analytics-action-status"
          >
            <Text style={{ color: actionStatus.type === 'error' ? 'var(--app-error)' : actionStatus.type === 'success' ? 'var(--app-success)' : 'var(--app-primary-soft)', fontSize: 11, fontWeight: '700' }}>
              {actionStatus.message}
            </Text>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity onPress={() => { void load('manual'); }} disabled={refreshing || triggering} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, backgroundColor: soft, borderWidth: 1, borderColor: border, opacity: refreshing ? 0.7 : 1 }} data-testid="newsletter-analytics-refresh-btn" testID="newsletter-analytics-refresh-btn">
            {refreshing ? <ActivityIndicator size="small" color={muted} /> : <Ionicons name="refresh" size={14} color={muted} />}
            <Text style={{ color: muted, fontSize: 12, fontWeight: '700' }}>{refreshing ? 'Refreshing...' : 'Refresh'}</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={triggerDigest} disabled={triggering || refreshing} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, backgroundColor: colors.accent, opacity: triggering ? 0.65 : 1 }} data-testid="newsletter-analytics-send-digest-btn" testID="newsletter-analytics-send-digest-btn">
            {triggering ? <ActivityIndicator size="small" color={palette.primaryText} /> : <Ionicons name="send" size={14} color={palette.primaryText} />}
            <Text style={{ color: palette.primaryText, fontSize: 12, fontWeight: '800' }}>{triggering ? 'Sending...' : 'Send Digest'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <MetricCard label="Active Subscribers" value={data.subscribers.active} sub={`+${data.subscribers.last_30d} last 30 days`} icon="people" accent={'var(--app-primary)'} bg={cardBg} border={border} text={text} muted={muted} testId="stat-active-subscribers" />
        <MetricCard label="Open Rate" value={`${data.engagement.open_rate}%`} sub={`${data.engagement.unique_openers} unique openers`} icon="mail-open" accent={'var(--app-success)'} bg={cardBg} border={border} text={text} muted={muted} testId="stat-open-rate" />
        <MetricCard label="Click Rate" value={`${data.engagement.click_rate}%`} sub={`${data.engagement.unique_clickers} unique clickers`} icon="finger-print" accent={'var(--app-warning)'} bg={cardBg} border={border} text={text} muted={muted} testId="stat-click-rate" />
        <MetricCard label="Unsubscribed" value={data.subscribers.unsubscribed} sub={`of ${data.subscribers.total} total`} icon="person-remove" accent={'var(--app-error)'} bg={cardBg} border={border} text={text} muted={muted} testId="stat-unsubscribed" />
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <SectionCard title="Top Articles by Clicks" icon="trending-up" iconColor={'var(--app-success)'} testId="top-articles-section" bg={cardBg} border={border} text={text}>
          {articleData.length > 0 ? <BarList data={articleData} maxVal={maxArticle} muted={muted} text={text} track={palette.bgSoft} /> : <Text style={{ color: muted, fontSize: 12 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.004', 'No click data yet. Send a digest to start tracking.')}</Text>}
        </SectionCard>

        <SectionCard title="Category Preferences" icon="pie-chart" iconColor={'var(--app-primary)'} testId="category-prefs-section" bg={cardBg} border={border} text={text}>
          {categoryData.length > 0 ? <BarList data={categoryData} maxVal={maxCategory} muted={muted} text={text} track={palette.bgSoft} /> : <Text style={{ color: muted, fontSize: 12 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.005', 'No preference data yet.')}</Text>}
        </SectionCard>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <SectionCard title="Subscription Sources" icon="git-network" iconColor={'var(--app-primary)'} testId="sub-sources-section" bg={cardBg} border={border} text={text}>
          {sourceData.length > 0 ? <BarList data={sourceData} maxVal={maxSource} muted={muted} text={text} track={palette.bgSoft} /> : <Text style={{ color: muted, fontSize: 12 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.006', 'No source data available.')}</Text>}
        </SectionCard>

        <SectionCard title="Digest History" icon="calendar" iconColor={'var(--app-warning)'} testId="digest-history-section" bg={cardBg} border={border} text={text}>
          {data.digests.length > 0 ? (
            <View style={{ gap: 8 }}>
              {data.digests.slice(0, 6).map((d) => {
                const openData = data.opens_by_digest.find((o) => o.digest_id === d.digest_id);
                const clickData = data.clicks_by_digest.find((c) => c.digest_id === d.digest_id);
                const recipients = Number(d.total_recipients || 0);
                const openRate = recipients > 0 ? Math.round(((openData?.unique_opens || 0) / recipients) * 100) : 0;
                const sentLabel = d.sent_at ? new Date(d.sent_at).toLocaleDateString() : 'n/a';
                return (
                  <View key={d.digest_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: border, backgroundColor: soft, padding: 10, flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: text, fontSize: 11, fontWeight: '700' }}>{d.digest_id}</Text>
                      <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>{sentLabel} · {recipients} recipients</Text>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ color: colors.successText, fontSize: 13, fontWeight: '800' }}>{openRate}%</Text>
                        <Text style={{ color: muted, fontSize: 9 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.007', 'Opens')}</Text>
                      </View>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '800' }}>{clickData?.unique_clicks || 0}</Text>
                        <Text style={{ color: muted, fontSize: 9 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.008', 'Clicks')}</Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={{ color: muted, fontSize: 12 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.009', 'No digests sent yet. Click “Send Digest” to send the first one.')}</Text>
          )}
        </SectionCard>
      </View>

      <NewsletterSubjectABWidget colors={colors} />

      <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 16, gap: 10 }} data-testid="newsletter-digest-comparison-section" testID="newsletter-digest-comparison-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="swap-horizontal" size={16} color={'var(--app-warning)'} />
          <Text style={{ color: text, fontSize: 14, fontWeight: '700' }} data-testid="newsletter-digest-comparison-title" testID="newsletter-digest-comparison-title">{tx('admin.newsletterAnalyticsPanelV2.auto.text.010', 'What changed since last digest')}</Text>
        </View>

        {digestComparison ? (
          <>
            <Text style={{ color: muted, fontSize: 11 }} data-testid="newsletter-digest-comparison-subtitle" testID="newsletter-digest-comparison-subtitle">
              Comparing {digestComparison.current?.digest_id} vs {digestComparison.previous?.digest_id}
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {[
                {
                  key: 'recipients',
                  label: 'Recipients',
                  current: digestComparison.currentMetrics.recipients,
                  previous: digestComparison.previousMetrics.recipients,
                  suffix: '',
                },
                {
                  key: 'open_rate',
                  label: 'Open Rate',
                  current: digestComparison.currentMetrics.openRate,
                  previous: digestComparison.previousMetrics.openRate,
                  suffix: '%',
                },
                {
                  key: 'click_rate',
                  label: 'Click Rate',
                  current: digestComparison.currentMetrics.clickRate,
                  previous: digestComparison.previousMetrics.clickRate,
                  suffix: '%',
                },
              ].map((metric) => {
                const delta = Number((metric.current - metric.previous).toFixed(1));
                const positive = delta >= 0;
                const deltaColor = positive ? 'var(--app-success)' : 'var(--app-error)';
                const deltaIcon = positive ? 'arrow-up' : 'arrow-down';
                return (
                  <View key={metric.key} style={{ minWidth: 132, flex: 1, borderRadius: 10, borderWidth: 1, borderColor: border, backgroundColor: soft, padding: 10 }} data-testid={`newsletter-digest-comparison-${metric.key}`} testID={`newsletter-digest-comparison-${metric.key}`}>
                    <Text style={{ color: muted, fontSize: 10, fontWeight: '700' }} data-testid={`newsletter-digest-comparison-${metric.key}-label`} testID={`newsletter-digest-comparison-${metric.key}-label`}>{metric.label}</Text>
                    <Text style={{ color: text, fontSize: 18, fontWeight: '800', marginTop: 4 }} data-testid={`newsletter-digest-comparison-${metric.key}-current`} testID={`newsletter-digest-comparison-${metric.key}-current`}>
                      {metric.current}{metric.suffix}
                    </Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 3 }}>
                      <Ionicons name={deltaIcon as any} size={12} color={deltaColor} />
                      <Text style={{ color: deltaColor, fontSize: 10, fontWeight: '700' }} data-testid={`newsletter-digest-comparison-${metric.key}-delta`} testID={`newsletter-digest-comparison-${metric.key}-delta`}>
                        {delta >= 0 ? '+' : ''}{delta}{metric.suffix} vs previous
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          </>
        ) : (
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: border, backgroundColor: soft, padding: 10 }} data-testid="newsletter-digest-comparison-empty" testID="newsletter-digest-comparison-empty">
            <Text style={{ color: muted, fontSize: 11 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.011', 'At least two digest runs are needed to show comparison insights.')}</Text>
          </View>
        )}
      </View>

      <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 16 }} data-testid="engagement-summary-section" testID="engagement-summary-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Ionicons name="pulse" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: text, fontSize: 14, fontWeight: '700' }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.012', 'Engagement Summary')}</Text>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {[
            { label: 'Total Opens', value: data.engagement.total_opens, color: colors.successText },
            { label: 'Unique Openers', value: data.engagement.unique_openers, color: colors.primary },
            { label: 'Total Clicks', value: data.engagement.total_clicks, color: colors.warningText },
            { label: 'Unique Clickers', value: data.engagement.unique_clickers, color: colors.accent },
            { label: 'Total Subscribers', value: data.subscribers.total, color: colors.accent },
            { label: 'Active', value: data.subscribers.active, color: colors.successText },
          ].map((metric) => (
            <View key={metric.label} style={{ minWidth: 110, borderRadius: 10, borderWidth: 1, borderColor: border, backgroundColor: soft, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`engagement-metric-${metric.label.toLowerCase().replace(/\s+/g, '-')}`} testID={`engagement-metric-${metric.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <Text style={{ color: metric.color, fontSize: 16, fontWeight: '800' }}>{metric.value}</Text>
              <Text style={{ color: muted, fontSize: 10, marginTop: 1 }}>{metric.label}</Text>
            </View>
          ))}
        </View>
      </View>

      <NewsletterAISection cardBg={cardBg} border={border} text={text} muted={muted} />
      <View style={{ height: 8 }} />
    </ScrollView>
  );
}

function NewsletterAISection({ cardBg, border, text, muted }: { cardBg: string; border: string; text: string; muted: string }) {
  const ai = useAiInsight('newsletter_suggestions', 'newsletter-suggestions');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 2 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="newsletter-ai-toggle" testID="newsletter-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <View>
            <Text style={{ color: text, fontSize: 13, fontWeight: '700' }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.013', 'AI Content Suggestions')}</Text>
            <Text style={{ color: muted, fontSize: 10 }}>{tx('admin.newsletterAnalyticsPanelV2.auto.text.014', 'Subject lines, content ideas, and optimization tips')}</Text>
          </View>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>

      {show ? (
        <View style={{ marginTop: 10 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'newsletter_suggestions',
              postEndpoint: 'newsletter-suggestions',
              title: 'AI Content Suggestions',
              subtitle: 'newsletter performance',
              scoreKey: 'newsletter_health',
              scoreLabel: 'Newsletter Health',
              summaryKey: 'executive_summary',
              sections: [
                { key: 'content_suggestions', title: 'Content Ideas', icon: 'bulb', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'subject_line_ideas', title: 'Subject Line Ideas', icon: 'mail', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'optimization_tips', title: 'Optimization Tips', icon: 'trending-up', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
                {
                  key: 'optimal_send_times',
                  title: 'Best Send Times',
                  icon: 'time',
                  renderItem: (item, idx, total) => <QuickWinItem key={idx} item={{ ...item, action: `${item.day} at ${item.time}`, expected_impact: item.reason }} idx={idx} total={total} />,
                },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      ) : null}
    </View>
  );
}
