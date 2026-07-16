import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AutoFixBanner from './AutoFixBanner';
import { useAiInsight, AIInsightPanel, PriorityItem, QuickWinItem } from './AIInsightHelpers';
import api from '../../services/api';
import { useHybridPolling } from '../../hooks/useHybridPolling';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const AC = {
  bg: 'transparent', bgAlt: 'rgba(15,23,42,0.12)', card: 'rgba(15,23,42,0.08)', surface: 'rgba(15,23,42,0.08)', surfaceHover: 'rgba(15,23,42,0.12)', border: 'rgba(148,163,184,0.22)', borderStrong: 'var(--app-border-strong)',
  text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', textDim: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)',
};
interface Analytics {
  subscribers: { total: number; active: number; unsubscribed: number; last_30d: number; sources: Record<string, number> };
  engagement: { total_opens: number; total_clicks: number; unique_openers: number; unique_clickers: number; open_rate: number; click_rate: number };
  top_articles: { slug: string; clicks: number; unique_readers: number }[];
  digests: { digest_id: string; sent_at: string; total_recipients: number; post_slugs: string[] }[];
  opens_by_digest: { digest_id: string; opens: number; unique_opens: number }[];
  clicks_by_digest: { digest_id: string; clicks: number; unique_clicks: number }[];
  category_preferences: Record<string, number>;
}

const tx = (_key: string, fallback: string) => fallback;

const CAT_COLORS: Record<string, string> = {
  'Industry Insights': 'var(--app-primary)', 'Product Update': 'var(--app-success)', 'Tips & Tricks': 'var(--app-warning)', // @theme-ok brand/role/state identifier
  'Research': 'var(--app-primary)', 'Company News': 'var(--app-primary)', 'Enterprise': 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

function StatCard({ label, value, sub, icon, color }: { label: string; value: string | number; sub?: string; icon: string; color: string }) {
  return (
    <View style={{ flex: 1, minWidth: 160, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: AC.border }} data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
      </View>
      <Text style={{ fontSize: 26, fontWeight: '800', color: AC.text, letterSpacing: -0.5 }}>{value}</Text>
      <Text style={{ fontSize: 12, color: AC.textDim, marginTop: 2, fontWeight: '500' }}>{label}</Text>
      {sub && <Text style={{ fontSize: 11, color: color, marginTop: 4, fontWeight: '600' }}>{sub}</Text>}
    </View>
  );
}

function BarChart({ data, maxVal }: { data: { label: string; value: number; color: string }[]; maxVal: number }) {
  return (
    <View style={{ gap: 8 }}>
      {data.map(d => (
        <View key={d.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Text style={{ width: 120, fontSize: 12, color: AC.textMuted, fontWeight: '500' }} numberOfLines={1}>{d.label}</Text>
          <View style={{ flex: 1, height: 24, backgroundColor: AC.border, borderRadius: 6, overflow: 'hidden' }}>
            <View style={{ width: `${maxVal ? (d.value / maxVal) * 100 : 0}%` as any, height: '100%', backgroundColor: d.color, borderRadius: 6, minWidth: d.value > 0 ? 8 : 0 }} />
          </View>
          <Text style={{ width: 36, fontSize: 12, color: AC.text, fontWeight: '700', textAlign: 'right' }}>{d.value}</Text>
        </View>
      ))}
    </View>
  );
}

export default function NewsletterAnalyticsPanel({ colors }: { colors: any }) {
  const onPrimary = 'rgb(255,255,255)';
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [actionStatus, setActionStatus] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  const normalizeAnalyticsPayload = (raw: any): Analytics => {
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
      engagement: {
        total_opens: 0,
        total_clicks: 0,
        unique_openers: 0,
        unique_clickers: 0,
        open_rate: 0,
        click_rate: 0,
      },
      top_articles: [],
      digests: [],
      opens_by_digest: [],
      clicks_by_digest: [],
      category_preferences: {},
    };
  };

  const load = async (initial = false) => {
    if (initial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      const resp = await api.get('/newsletter/analytics');
      const normalized = normalizeAnalyticsPayload(resp?.data || {});
      setData(normalized);
      if (!initial) {
        setActionStatus({ type: 'success', message: 'Analytics refreshed successfully.' });
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.response?.data?.message || 'Unable to refresh analytics right now.';
      setActionStatus({ type: 'error', message: msg });
    } finally {
      if (initial) setLoading(false);
      setRefreshing(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load(true); }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/newsletter-analytics/hybrid-refresh',
    onTick: () => load(false),
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const triggerDigest = async () => {
    setTriggering(true);
    try {
      const response = await api.post('/newsletter/trigger-digest');
      const d = response?.data || {};
      if (d.success) {
        if (Number(d.sent || 0) > 0) {
          setActionStatus({ type: 'success', message: `Digest sent successfully to ${d.sent} recipients.` });
        } else {
          setActionStatus({ type: 'info', message: 'Digest completed, but no eligible recipients were found.' });
        }
        await load(false);
      } else {
        setActionStatus({ type: 'error', message: d.error || 'Digest send failed.' });
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.response?.data?.message || 'Digest send failed.';
      setActionStatus({ type: 'error', message: msg });
    }
    setTriggering(false);
  };

  if (loading || !data) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 60 }}>
      <AutoFixBanner domain="newsletter" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: AC.textDim, marginTop: 12, fontSize: 13 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.001', 'Loading newsletter analytics...')}</Text>
      </View>
    );
  }

  const { subscribers: subs, engagement: eng, top_articles, category_preferences } = data;
  const sourceData = Object.entries(subs.sources).map(([k, v]) => ({ label: k, value: v, color: colors.primary }));
  const maxSource = Math.max(...sourceData.map(d => d.value), 1);
  const catData = Object.entries(category_preferences).map(([k, v]) => ({ label: k, value: v, color: CAT_COLORS[k] || AC.textMuted }));
  const maxCat = Math.max(...catData.map(d => d.value), 1);
  const articleData = top_articles.map(a => ({ label: a.slug.replace(/-/g, ' ').slice(0, 40), value: a.clicks, color: colors.successText }));
  const maxArticle = Math.max(...articleData.map(d => d.value), 1);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }} data-testid="newsletter-analytics-panel" testID="newsletter-analytics-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: AC.text, letterSpacing: -0.3 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.002', 'Newsletter Analytics')}</Text>
          <Text style={{ fontSize: 13, color: AC.textDim, marginTop: 2 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.003', 'Track email performance, engagement, and subscriber behavior')}</Text>
          {actionStatus && (
            <View
              style={{
                marginTop: 10,
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderRadius: 8,
                backgroundColor: actionStatus.type === 'error' ? 'var(--app-error-soft)' : actionStatus.type === 'success' ? 'var(--app-primary-soft)' : 'var(--app-primary-soft)',
                borderWidth: 1,
                borderColor: actionStatus.type === 'error' ? colors.errorSoft : actionStatus.type === 'success' ? colors.successSoft : colors.primarySoft,
                alignSelf: 'flex-start',
                maxWidth: 560,
              }}
              data-testid="newsletter-analytics-action-status"
              testID="newsletter-analytics-action-status"
            >
              <Text style={{ color: actionStatus.type === 'error' ? 'var(--app-error)' : actionStatus.type === 'success' ? colors.success : colors.primarySoft, fontSize: 11, fontWeight: '700' }}>
                {actionStatus.message}
              </Text>
            </View>
          )}
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={() => { void load(false); }} disabled={refreshing || triggering} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: AC.border, borderWidth: 1, borderColor: AC.borderStrong, opacity: refreshing ? 0.7 : 1 }} data-testid="newsletter-analytics-refresh-btn" testID="newsletter-analytics-refresh-btn">
            {refreshing ? <ActivityIndicator size="small" color={AC.textMuted} /> : <Ionicons name="refresh" size={14} color={AC.textMuted} />}
            <Text style={{ color: AC.textMuted, fontSize: 12, fontWeight: '600' }}>{refreshing ? 'Refreshing...' : 'Refresh'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={triggerDigest} disabled={triggering || refreshing} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.accent, opacity: triggering ? 0.6 : 1 }} data-testid="newsletter-analytics-send-digest-btn" testID="newsletter-analytics-send-digest-btn">
            {triggering ? <ActivityIndicator size="small" color={onPrimary} /> : <Ionicons name="send" size={14} color={onPrimary} />}
            <Text style={{ color: onPrimary, fontSize: 12, fontWeight: '700' }}>{triggering ? 'Sending...' : 'Send Digest'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <StatCard label="Active Subscribers" value={subs.active} sub={`+${subs.last_30d} last 30 days`} icon="people" color={'var(--app-primary)'} />
        <StatCard label="Open Rate" value={`${eng.open_rate}%`} sub={`${eng.unique_openers} unique openers`} icon="mail-open" color={'var(--app-success)'} />
        <StatCard label="Click Rate" value={`${eng.click_rate}%`} sub={`${eng.unique_clickers} unique clickers`} icon="finger-print" color={'var(--app-warning)'} />
        <StatCard label="Unsubscribed" value={subs.unsubscribed} sub={`of ${subs.total} total`} icon="person-remove" color={'var(--app-error)'} />
      </View>

      {/* Two column layout */}
      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
        {/* Top Articles */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="top-articles-section" testID="top-articles-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="trending-up" size={16} color={'var(--app-success)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.newsletterAnalyticsPanel.auto.text.004', 'Top Articles by Clicks')}</Text>
          </View>
          {articleData.length > 0 ? (
            <BarChart data={articleData} maxVal={maxArticle} />
          ) : (
            <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.005', 'No click data yet. Send a digest to start tracking.')}</Text>
          )}
        </View>

        {/* Category Preferences */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="category-prefs-section" testID="category-prefs-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="pie-chart" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.newsletterAnalyticsPanel.auto.text.006', 'Category Preferences')}</Text>
          </View>
          {catData.length > 0 ? (
            <BarChart data={catData} maxVal={maxCat} />
          ) : (
            <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.007', 'No preference data yet.')}</Text>
          )}
        </View>
      </View>

      {/* Second row */}
      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
        {/* Subscription Sources */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="sub-sources-section" testID="sub-sources-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="git-network" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.newsletterAnalyticsPanel.auto.text.008', 'Subscription Sources')}</Text>
          </View>
          <BarChart data={sourceData} maxVal={maxSource} />
        </View>

        {/* Digest History */}
        <View style={{ flex: 1, minWidth: 300, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: AC.border }} data-testid="digest-history-section" testID="digest-history-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="calendar" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.newsletterAnalyticsPanel.auto.text.009', 'Digest History')}</Text>
          </View>
          {data.digests.length > 0 ? (
            <View style={{ gap: 8 }}>
              {data.digests.slice(0, 5).map(d => {
                const openData = data.opens_by_digest.find(o => o.digest_id === d.digest_id);
                const clickData = data.clicks_by_digest.find(c => c.digest_id === d.digest_id);
                const openRate = d.total_recipients > 0 ? Math.round(((openData?.unique_opens || 0) / d.total_recipients) * 100) : 0;
                return (
                  <View key={d.digest_id} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: AC.border, borderRadius: 8, gap: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '600', color: AC.text }}>{d.digest_id}</Text>
                      <Text style={{ fontSize: 11, color: AC.textDim, marginTop: 2 }}>{new Date(d.sent_at).toLocaleDateString()} - {d.total_recipients} recipients</Text>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 12 }}>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.successText }}>{openRate}%</Text>
                        <Text style={{ fontSize: 9, color: AC.textDim }}>{tx('admin.newsletterAnalyticsPanel.auto.text.010', 'Opens')}</Text>
                      </View>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.warningText }}>{clickData?.unique_clicks || 0}</Text>
                        <Text style={{ fontSize: 9, color: AC.textDim }}>{tx('admin.newsletterAnalyticsPanel.auto.text.011', 'Clicks')}</Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={{ color: AC.textDim, fontSize: 13, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.newsletterAnalyticsPanel.auto.text.012', 'No digests sent yet. Click "Send Digest" to send the first one.')}</Text>
          )}
        </View>
      </View>

      {/* Engagement Summary */}
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: AC.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="pulse" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: AC.text }}>{tx('admin.newsletterAnalyticsPanel.auto.text.013', 'Engagement Summary')}</Text>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 20 }}>
          {[
            { label: 'Total Opens', value: eng.total_opens, color: colors.successText },
            { label: 'Unique Openers', value: eng.unique_openers, color: colors.primary },
            { label: 'Total Clicks', value: eng.total_clicks, color: colors.warningText },
            { label: 'Unique Clickers', value: eng.unique_clickers, color: colors.accent },
            { label: 'Total Subscribers', value: subs.total, color: colors.accent },
            { label: 'Active', value: subs.active, color: colors.successText },
          ].map(m => (
            <View key={m.label} style={{ alignItems: 'center', minWidth: 100 }}>
              <Text style={{ fontSize: 22, fontWeight: '800', color: m.color }}>{m.value}</Text>
              <Text style={{ fontSize: 11, color: AC.textDim, marginTop: 2 }}>{m.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* AI Newsletter Suggestions */}
      <NewsletterAISection />

      <View style={{ height: 20 }} />
    </ScrollView>
  );
}

function NewsletterAISection() {
  const colors = useAdminTheme();
  const ai = useAiInsight('newsletter_suggestions', 'newsletter-suggestions');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="newsletter-ai-toggle" testID="newsletter-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.newsletterAnalyticsPanel.auto.text.014', 'AI Content Suggestions')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'newsletter_suggestions', postEndpoint: 'newsletter-suggestions',
              title: 'AI Content Suggestions', subtitle: 'newsletter performance',
              scoreKey: 'newsletter_health', scoreLabel: 'Newsletter Health',
              summaryKey: 'executive_summary',
              sections: [
                { key: 'content_suggestions', title: 'Content Ideas', icon: 'bulb', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'subject_line_ideas', title: 'Subject Line Ideas', icon: 'mail', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'optimization_tips', title: 'Optimization Tips', icon: 'trending-up', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'optimal_send_times', title: 'Best Send Times', icon: 'time', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={{...item, action: `${item.day} at ${item.time}`, expected_impact: item.reason}} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}
    </View>
  );
}
