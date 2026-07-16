import React, { useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useAiInsight, AIInsightPanel, PriorityItem, FunnelItem, QuickWinItem } from './AIInsightHelpers';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface StepFunnel {
  step_id: string;
  label: string;
  count: number;
  rate: number;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface AnalyticsData {
  total_users: number;
  started: number;
  completed: number;
  dismissed: number;
  activation_rate: number;
  completion_rate: number;
  drop_off_rate: number;
  avg_completion_minutes: number;
  step_funnel: StepFunnel[];
  recent_7d: { starts: number; completions: number };
}

const tx = (_key: string, fallback: string) => fallback;

function KPITile({ label, value, icon, color, subtext }: { label: string; value: string | number; icon: string; color: string; subtext?: string }) {
  const T = useExecTheme();
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 12, padding: 16, borderLeftWidth: 3, borderLeftColor: color }} data-testid={`onboarding-kpi-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`onboarding-kpi-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 24, fontWeight: '800' }}>{value}</Text>
      {subtext && <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{subtext}</Text>}
    </View>
  );
}

function FunnelChart({ steps, maxCount }: { steps: StepFunnel[]; maxCount: number }) {
  const T = useExecTheme();
  // V2 Teal Enterprise funnel palette — cool → warm gradient that reads as
  // "progression with drop-off risk". Replaces the previously undefined
  // `colors` identifier that caused a latent ReferenceError when this chart
  // was rendered.
  const palette = [T.primary, T.info || T.primary, T.purple, T.warning, T.error];

  return (
    <View data-testid="onboarding-funnel-chart" testID="onboarding-funnel-chart">
      {steps.map((step, i) => {
        const barWidth = maxCount > 0 ? Math.max((step.count / maxCount) * 100, 4) : 4;
        const color = palette[i % palette.length];
        const dropOff = i > 0 && steps[i - 1].count > 0
          ? Math.round(((steps[i - 1].count - step.count) / steps[i - 1].count) * 100)
          : null;

        return (
          <View key={step.step_id} style={{ marginBottom: 10 }} data-testid={`funnel-step-${step.step_id}`} testID={`funnel-step-${step.step_id}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(color, '25'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color, fontSize: 9, fontWeight: '800' }}>{i + 1}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{step.label}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{step.count} users</Text>
                <Text style={{ color, fontSize: 11, fontWeight: '700' }}>{step.rate}%</Text>
              </View>
            </View>
            <View style={{ height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
              <View style={{ width: `${barWidth}%` as any, height: '100%', backgroundColor: color, borderRadius: 4 }} />
            </View>
            {dropOff !== null && dropOff > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 3, paddingLeft: 26 }}>
                <Ionicons name="arrow-down" size={10} color={T.error} />
                <Text style={{ color: T.error, fontSize: 9, fontWeight: '600' }}>{dropOff}% drop-off</Text>
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}

export default function OnboardingAnalyticsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const _colors = useAdminTheme();
  const T = useExecTheme();
  const { data, loading, refetch } = useLiveQuery('/onboarding/analytics', { entity: 'onboarding', pollInterval: 60000 });

  if (loading && !data) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 12 }}>{tx('admin.onboardingAnalyticsPanel.auto.text.001', 'Loading onboarding analytics...')}</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }}>
        <Ionicons name="alert-circle-outline" size={32} color={T.error} />
        <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 12 }}>{tx('admin.onboardingAnalyticsPanel.auto.text.002', 'Failed to load analytics')}</Text>
        <TouchableOpacity onPress={refetch} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, backgroundColor: T.primarySoft, borderRadius: 8 }} accessibilityLabel={tx('admin.onboardingAnalyticsPanel.auto.accessibility.001', 'Retry')}>
          <Text style={{ color: T.primary, fontSize: 12, fontWeight: '600' }}>{tx('admin.onboardingAnalyticsPanel.auto.text.003', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const maxFunnel = Math.max(...data.step_funnel.map(s => s.count), 1);

  return (
    <View data-testid="onboarding-analytics-panel" testID="onboarding-analytics-panel">
      {/* Header */}
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="rocket" size={18} color={T.primary} />
            <Text style={s.chartTitle}>{tx('admin.onboardingAnalyticsPanel.auto.text.004', 'Onboarding Analytics')}</Text>
          </View>
          <TouchableOpacity onPress={refetch} style={{ padding: 8, backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border }} data-testid="onboarding-refresh-btn" testID="onboarding-refresh-btn">
            <Ionicons name="refresh" size={14} color={T.textMuted} />
          </TouchableOpacity>
        </View>

        {/* KPI Row */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }} data-testid="onboarding-kpi-row" testID="onboarding-kpi-row">
          <KPITile label="Total Users" value={data.total_users} icon="people" color={T.primary} />
          <KPITile label="Started Tour" value={data.started} icon="play" color={T.cyan} subtext={`${data.total_users > 0 ? Math.round((data.started / data.total_users) * 100) : 0}% of users`} />
          <KPITile label="Completed" value={data.completed} icon="checkmark-circle" color={T.successText} subtext={`${data.completion_rate}% completion rate`} />
          <KPITile label="Dismissed" value={data.dismissed} icon="close-circle" color={T.warningText} subtext={`${data.drop_off_rate}% drop-off rate`} />
          <KPITile label="Activation Rate" value={`${data.activation_rate}%`} icon="trending-up" color={T.purpleText} subtext="Completed / Total Users" />
          <KPITile label="Avg. Time" value={data.avg_completion_minutes > 0 ? `${data.avg_completion_minutes}m` : 'N/A'} icon="time" color={T.teal} subtext="Average completion time" />
        </View>

        {/* 7-Day Trend */}
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, marginBottom: 24, borderWidth: 1, borderColor: T.border }} data-testid="onboarding-7d-trend" testID="onboarding-7d-trend">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <Ionicons name="calendar" size={14} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.onboardingAnalyticsPanel.auto.text.005', 'Last 7 Days')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 20 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.cyan }} />
              <Text style={{ color: T.textSec, fontSize: 12 }}>
                <Text style={{ fontWeight: '700', color: T.text }}>{data.recent_7d.starts}</Text> started
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success }} />
              <Text style={{ color: T.textSec, fontSize: 12 }}>
                <Text style={{ fontWeight: '700', color: T.text }}>{data.recent_7d.completions}</Text> completed
              </Text>
            </View>
          </View>
        </View>

        {/* Step Funnel */}
        <View style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }}>
            <Ionicons name="filter" size={14} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.onboardingAnalyticsPanel.auto.text.006', 'Step-by-Step Funnel')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10, marginLeft: 'auto' as any }}>
              {data.step_funnel.length} steps
            </Text>
          </View>
          <FunnelChart steps={data.step_funnel} maxCount={maxFunnel} />
        </View>

        {/* AI Onboarding Coach */}
        <OnboardingAISection />
      </View>
    </View>
  );
}

function OnboardingAISection() {
  const colors = useAdminTheme();
  const ai = useAiInsight('onboarding_coach', 'onboarding-coach');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="onboarding-ai-toggle" testID="onboarding-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.onboardingAnalyticsPanel.auto.text.007', 'AI Onboarding Coach')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'onboarding_coach', postEndpoint: 'onboarding-coach',
              title: 'AI Onboarding Coach', subtitle: 'onboarding patterns',
              scoreKey: 'onboarding_health', scoreLabel: 'Onboarding Health',
              summaryKey: 'executive_summary',
              sections: [
                { key: 'drop_off_analysis', title: 'Drop-off Analysis', icon: 'trending-down', renderItem: (item, idx, total) => <FunnelItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'ux_improvements', title: 'UX Improvements', icon: 'color-palette', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'engagement_boosters', title: 'Engagement Boosters', icon: 'flash', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={item} idx={idx} total={total} /> },
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
