// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);
const TOPIC_COLORS: any = { billing: C.green, technical: C.blue, account: C.indigo, feature_request: C.purple, bug_report: C.red, general: C.muted };
const TOPIC_ICONS: any = { billing: 'card', technical: 'code-slash', account: 'person', feature_request: 'bulb', bug_report: 'bug', general: 'help-circle' };
const MOOD_COLORS: any = { happy: C.green, neutral: C.sec, confused: C.yellow, frustrated: C.orange, angry: C.red, desperate: C.red, disappointed: C.orange };
const PRIORITY_COLORS: any = { low: C.sec, medium: C.blue, high: C.yellow, urgent: C.orange, critical: C.red };

// ── Horizontal Bar ──
function HBar({ label, value, max, color, suffix }: { label: string; value: number; max: number; color: string; suffix?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <View style={{ marginBottom: 8 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
        <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }}>{label}</Text>
        <Text style={{ fontSize: 11, fontWeight: '700', color }}>{value}{suffix || ''}</Text>
      </View>
      <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: 3 }} />
      </View>
    </View>
  );
}

// ── Mini Stat Card ──
function StatCard({ icon, label, value, sub, color }: { icon: string; label: string; value: string | number; sub?: string; color: string }) {
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: (globalThis as any).__alphaColor(color, '08'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '18') }}>
      <Ionicons name={icon as any} size={18} color={color} style={{ marginBottom: 8 }} />
      <Text style={{ fontSize: 24, fontWeight: '800', color, letterSpacing: -0.5 }}>{value}</Text>
      <Text style={{ fontSize: 11, fontWeight: '600', color: C.text, marginTop: 2 }}>{label}</Text>
      {sub && <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{sub}</Text>}
    </View>
  );
}

// ── Volume Chart (Bar chart using Views) ──
function VolumeChart({ data }: { data: any[] }) {
  if (!data?.length) return null;
  const maxVal = Math.max(...data.map(d => d.count), 1);
  return (
    <View data-testid="volume-chart" testID="volume-chart">
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 100, paddingTop: 8 }}>
        {data.map((d, i) => {
          const h = (d.count / maxVal) * 80;
          const escH = (d.escalated / maxVal) * 80;
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
              <Text style={{ fontSize: 8, color: C.muted, marginBottom: 2 }}>{d.count}</Text>
              <View style={{ width: '80%', borderRadius: 3, overflow: 'hidden' }}>
                <View style={{ height: Math.max(h, 2), backgroundColor: C.blue, borderRadius: 3 }} />
                {escH > 0 && <View style={{ height: escH, backgroundColor: (globalThis as any).__alphaColor(C.red, '60'), borderRadius: 3, marginTop: 1 }} />}
              </View>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', gap: 3, marginTop: 4 }}>
        {data.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ fontSize: 7, color: C.muted }}>{d.date?.slice(5)}</Text>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: 12, marginTop: 8, justifyContent: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: C.blue }} />
          <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.aIResolutionDashboard.auto.text.001', 'Tickets')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.red, '60') }} />
          <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.aIResolutionDashboard.auto.text.002', 'Escalated')}</Text>
        </View>
      </View>
    </View>
  );
}

// ── Confidence Distribution ──
function ConfidenceChart({ buckets }: { buckets: any[] }) {
  if (!buckets?.length) return null;
  const labels = ['< 50%', '50-70%', '70-85%', '85-100%'];
  const colors = [C.red, C.orange, C.yellow, C.green];
  const total = buckets.reduce((s, b) => s + b.count, 0);
  return (
    <View data-testid="confidence-chart" testID="confidence-chart">
      {buckets.map((b, i) => (
        <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Text style={{ fontSize: 10, fontWeight: '600', color: C.muted, width: 50 }}>{labels[i] || `${b.min}`}</Text>
          <View style={{ flex: 1, height: 10, backgroundColor: C.border, borderRadius: 5, overflow: 'hidden' }}>
            <View style={{ width: `${total > 0 ? (b.count / total) * 100 : 0}%`, height: '100%', backgroundColor: colors[i] || C.blue, borderRadius: 5 }} />
          </View>
          <Text style={{ fontSize: 10, fontWeight: '700', color: colors[i] || C.blue, width: 30, textAlign: 'right' }}>{b.count}</Text>
        </View>
      ))}
    </View>
  );
}

// ── Main Panel ──
export default function AIResolutionDashboard({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const { data, loading, refetch: loadData } = useLiveQuery('/admin/manage/ai-resolution/analytics', { entity: 'ai-resolution', pollInterval: 60000 });

  if (loading) return <ActivityIndicator color={C.purpleText} style={{ padding: 40 }} />;
  if (!data) return <Text style={{ color: C.muted, textAlign: 'center', padding: 40 }}>{tx('admin.aIResolutionDashboard.auto.text.003', 'Failed to load analytics')}</Text>;

  const o = data.overview || {};
  const topTags = data.top_tags || [];
  const maxTagCount = Math.max(...topTags.map((t: any) => t.count), 1);

  return (
    <View data-testid="ai-resolution-dashboard" testID="ai-resolution-dashboard">
      <AutoFixBanner domain="ai_resolution" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="sparkles" size={18} color={C.purpleText} />
          </View>
          <View>
            <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{tx('admin.aIResolutionDashboard.auto.text.004', 'AI Resolution Intelligence')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.aIResolutionDashboard.auto.text.005', 'Automated ticket routing performance & analytics')}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={loadData} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }} data-testid="refresh-analytics-btn" testID="refresh-analytics-btn">
          <Ionicons name="refresh" size={16} color={C.purpleText} />
        </TouchableOpacity>
      </View>

      {/* ═══ Scorecard Row ═══ */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }} data-testid="ai-resolution-scorecard-wrap" testID="ai-resolution-scorecard-wrap">
        <StatCard icon="analytics" label="Total Tickets" value={o.total_tickets} sub="all time" color={C.blue} />
        <StatCard icon="sparkles" label="AI Classified" value={`${o.ai_classification_rate}%`} sub={`${o.ai_classified} tickets`} color={C.purpleText} />
        <StatCard icon="warning" label="Auto-Escalated" value={`${o.escalation_rate}%`} sub={`${o.auto_escalated} tickets`} color={C.red} />
        <StatCard icon="checkmark-circle" label="Resolution Rate" value={`${o.resolution_rate}%`} sub={`${o.resolved} resolved`} color={C.green} />
        <StatCard icon="chatbubbles" label="Avg Replies" value={o.avg_replies_to_resolve} sub="to resolve" color={C.cyan} />
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        {/* ═══ Left Column ═══ */}
        <View style={{ flex: isWide ? 1 : undefined }}>
          {/* Daily Volume */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="daily-volume-card" testID="daily-volume-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.006', 'Ticket Volume (14 days)')}</Text>
            <VolumeChart data={data.daily_volume || []} />
          </View>

          {/* Topic Distribution */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="topic-distribution-card" testID="topic-distribution-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.007', 'Topic Distribution')}</Text>
            {Object.entries(data.by_topic || {}).sort((a: any, b: any) => b[1] - a[1]).map(([topic, count]: any) => (
              <HBar key={topic} label={topic.replace(/_/g, ' ')} value={count} max={o.total_tickets} color={TOPIC_COLORS[topic] || C.muted} />
            ))}
          </View>

          {/* SLA Compliance */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="sla-compliance-card" testID="sla-compliance-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.008', 'SLA Compliance')}</Text>
            {(data.sla_compliance || []).length === 0 ? (
              <Text style={{ color: C.muted, fontSize: 12, textAlign: 'center', padding: 10 }}>{tx('admin.aIResolutionDashboard.auto.text.009', 'No resolved ticket data yet')}</Text>
            ) : (data.sla_compliance || []).map((s: any) => (
              <View key={s.priority} style={{ marginBottom: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: PRIORITY_COLORS[s.priority] || C.muted }} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{s.priority}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={{ fontSize: 10, color: C.muted }}>{s.avg_hours}h avg</Text>
                    <View style={{ backgroundColor: s.compliance_pct >= 80 ? (globalThis as any).__alphaColor(C.green, '18') : s.compliance_pct >= 50 ? C.yellow + '18' : C.red + '18', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                      <Text style={{ fontSize: 10, fontWeight: '800', color: s.compliance_pct >= 80 ? C.green : s.compliance_pct >= 50 ? C.yellow : C.red }}>{s.compliance_pct}%</Text>
                    </View>
                  </View>
                </View>
                <View style={{ height: 5, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
                  <View style={{ width: `${s.compliance_pct}%`, height: '100%', backgroundColor: s.compliance_pct >= 80 ? C.green : s.compliance_pct >= 50 ? C.yellow : C.red, borderRadius: 3 }} />
                </View>
              </View>
            ))}
          </View>
        </View>

        {/* ═══ Right Column ═══ */}
        <View style={{ flex: isWide ? 1 : undefined }}>
          {/* Sentiment Analysis */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="sentiment-card" testID="sentiment-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.010', 'Sentiment Analysis')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              {Object.entries(data.sentiment || {}).map(([mood, info]: any) => (
                <View key={mood} style={{ backgroundColor: (globalThis as any).__alphaColor((MOOD_COLORS[mood] || C.muted), '10'), borderRadius: 10, padding: 10, minWidth: 90, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor((MOOD_COLORS[mood] || C.muted), '20') }}>
                  <Text style={{ fontSize: 18, fontWeight: '800', color: MOOD_COLORS[mood] || C.muted }}>{info.count}</Text>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: MOOD_COLORS[mood] || C.muted, marginTop: 2 }}>{mood}</Text>
                  <Text style={{ fontSize: 9, color: C.muted, marginTop: 1 }}>frustration: {info.avg_frustration}/10</Text>
                </View>
              ))}
            </View>
          </View>

          {/* AI Confidence Distribution */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="confidence-card" testID="confidence-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.011', 'AI Confidence Distribution')}</Text>
            <ConfidenceChart buckets={data.confidence_buckets || []} />
          </View>

          {/* Priority Breakdown */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="priority-card" testID="priority-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.012', 'Priority Breakdown')}</Text>
            {Object.entries(data.by_priority || {}).sort((a: any, b: any) => b[1] - a[1]).map(([prio, count]: any) => (
              <HBar key={prio} label={prio} value={count} max={o.total_tickets} color={PRIORITY_COLORS[prio] || C.muted} />
            ))}
          </View>

          {/* Top Tags */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="top-tags-card" testID="top-tags-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.013', 'Top AI Tags')}</Text>
            {topTags.length === 0 ? (
              <Text style={{ color: C.muted, fontSize: 12, textAlign: 'center', padding: 10 }}>{tx('admin.aIResolutionDashboard.auto.text.014', 'No tags yet')}</Text>
            ) : topTags.slice(0, 10).map((t: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                <Text style={{ fontSize: 10, color: C.muted, width: 16, textAlign: 'right' }}>#{i + 1}</Text>
                <View style={{ flex: 1, height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden' }}>
                  <View style={{ width: `${(t.count / maxTagCount) * 100}%`, height: '100%', backgroundColor: C.accent, borderRadius: 4 }} />
                </View>
                <Text style={{ fontSize: 10, fontWeight: '600', color: C.accent, width: 80 }} numberOfLines={1}>{t.tag}</Text>
                <Text style={{ fontSize: 10, fontWeight: '700', color: C.text, width: 24, textAlign: 'right' }}>{t.count}</Text>
              </View>
            ))}
          </View>

          {/* Resolution by Topic */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="resolution-by-topic-card" testID="resolution-by-topic-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.aIResolutionDashboard.auto.text.015', 'Resolution by Topic')}</Text>
            {Object.entries(data.resolution_by_topic || {}).length === 0 ? (
              <Text style={{ color: C.muted, fontSize: 12, textAlign: 'center', padding: 10 }}>{tx('admin.aIResolutionDashboard.auto.text.016', 'No resolution data yet')}</Text>
            ) : Object.entries(data.resolution_by_topic || {}).map(([topic, info]: any) => (
              <View key={topic} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8, backgroundColor: C.bg, borderRadius: 8, padding: 10 }}>
                <Ionicons name={(TOPIC_ICONS[topic] || 'help-circle') as any} size={14} color={TOPIC_COLORS[topic] || C.muted} />
                <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: C.text }}>{topic.replace(/_/g, ' ')}</Text>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: TOPIC_COLORS[topic] || C.muted }}>{info.count}</Text>
                  <Text style={{ fontSize: 9, color: C.muted }}>{info.avg_replies} avg replies</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      </View>
    </View>
  );
}
