import React from 'react';
import { View, Text, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

let Recharts: any = {};
if (Platform.OS === 'web') {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    Recharts = require('recharts');
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABPerformanceDashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

const tx = (_key: string, fallback: string) => fallback;

const { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } = Recharts;

type ThemePalette = {
  surface: string;
  surfaceHover: string;
  border: string;
  text: string;
  textMuted: string;
  primaryText: string;
  primary: string;
  success: string;
  warning: string;
  info: string;
};

function KPI({ label, value, sub, color, icon, palette }: { label: string; value: string | number; sub?: string; color: string; icon: any; palette: ThemePalette }) {
  return (
    <View style={{ flex: 1, minWidth: 140, padding: 16, borderRadius: 14, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${color}15`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={14} color={color} />
        </View>
        <Text style={{ fontSize: 10, fontWeight: '700', color: palette.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      </View>
      <Text style={{ fontSize: 24, fontWeight: '800', color: palette.text, letterSpacing: -0.5 }} data-testid={`perf-kpi-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`perf-kpi-${label.toLowerCase().replace(/\s/g, '-')}`}>
        {value}
      </Text>
      {sub ? <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 2 }}>{sub}</Text> : null}
    </View>
  );
}

function TestCard({ test, palette }: { test: any; palette: ThemePalette }) {
  const totalsA = test.totals?.a || {};
  const totalsB = test.totals?.b || {};
  const ts = test.time_series || [];
  const statusColor = test.status === 'active' ? palette.success : palette.info;

  const chartData: any[] = [];
  const dateMap: Record<string, any> = {};
  for (const entry of ts) {
    if (!dateMap[entry.date]) {
      dateMap[entry.date] = { date: entry.date.slice(5) };
    }
    const prefix = entry.variant === 'a' ? 'a_' : 'b_';
    dateMap[entry.date][prefix + 'open'] = entry.open_rate;
    dateMap[entry.date][prefix + 'click'] = entry.click_rate;
    dateMap[entry.date][prefix + 'sent'] = entry.sent;
  }
  Object.values(dateMap).forEach((item: any) => chartData.push(item));

  return (
    <View style={{ padding: 18, borderRadius: 14, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border, marginBottom: 16, borderLeftWidth: 4, borderLeftColor: statusColor }} data-testid={`perf-test-${test.test_id}`} testID={`perf-test-${test.test_id}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: palette.text }}>{test.name}</Text>
          <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 2 }}>
            {test.tier || test.template_type} · Created {test.created_at ? new Date(test.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
          </Text>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: `${statusColor}15` }}>
            <Text style={{ fontSize: 9, fontWeight: '800', color: statusColor }}>{String(test.status || 'unknown').toUpperCase()}</Text>
          </View>
          {test.winner ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: `${palette.warning}15` }}>
              <Ionicons name="trophy" size={10} color={palette.warningText} />
              <Text style={{ fontSize: 9, fontWeight: '800', color: palette.warningText }}>WINNER: {String(test.winner).toUpperCase()}</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }}>
        {['a', 'b'].map((variant) => {
          const current = variant === 'a' ? totalsA : totalsB;
          const subject = variant === 'a' ? test.variant_a_subject : test.variant_b_subject;
          const isWinner = test.winner === variant;
          const variantColor = variant === 'a' ? palette.primary : palette.info;

          return (
            <View key={variant} style={{ flex: 1, padding: 12, borderRadius: 10, backgroundColor: isWinner ? `${variantColor}08` : palette.surfaceHover, borderWidth: 1, borderColor: isWinner ? `${variantColor}30` : palette.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 8 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: variantColor }} />
                <Text style={{ fontSize: 10, fontWeight: '800', color: variantColor }}>VARIANT {variant.toUpperCase()}</Text>
                {isWinner ? <Ionicons name="trophy" size={10} color={palette.warningText} /> : null}
              </View>
              <Text style={{ fontSize: 9, color: palette.textMuted, marginBottom: 6 }} numberOfLines={1}>{subject || 'No subject'}</Text>

              <View style={{ flexDirection: 'row', gap: 10 }}>
                <VariantStat label="Opens" value={`${current.open_rate || 0}%`} palette={palette} />
                <VariantStat label="Clicks" value={`${current.click_rate || 0}%`} palette={palette} />
                <VariantStat label="Sent" value={current.sent || 0} palette={palette} />
              </View>
            </View>
          );
        })}
      </View>

      {Platform.OS === 'web' && chartData.length > 0 && ResponsiveContainer ? (
        <>
          <View style={{ height: 160, marginTop: 4 }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: palette.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBPerformanceDashboard.auto.text.001', 'Open Rate Trend')}</Text>
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id={`gradA_${test.test_id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={palette.primary} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={palette.primary} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id={`gradB_${test.test_id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={palette.info} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={palette.info} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: palette.textMuted }} />
                <YAxis tick={{ fontSize: 9, fill: palette.textMuted }} unit="%" />
                <Tooltip contentStyle={{ backgroundColor: palette.surface, border: `1px solid ${palette.border}`, borderRadius: 8, fontSize: 11 }} />
                <Area type="monotone" dataKey="a_open" name="Variant A" stroke={palette.primary} fill={`url(#gradA_${test.test_id})`} strokeWidth={2} />
                <Area type="monotone" dataKey="b_open" name="Variant B" stroke={palette.info} fill={`url(#gradB_${test.test_id})`} strokeWidth={2} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </AreaChart>
            </ResponsiveContainer>
          </View>

          <View style={{ height: 160, marginTop: 12 }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: palette.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBPerformanceDashboard.auto.text.002', 'Sends Volume')}</Text>
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: palette.textMuted }} />
                <YAxis tick={{ fontSize: 9, fill: palette.textMuted }} />
                <Tooltip contentStyle={{ backgroundColor: palette.surface, border: `1px solid ${palette.border}`, borderRadius: 8, fontSize: 11 }} />
                <Bar dataKey="a_sent" name="Variant A" fill={palette.primary} radius={[4, 4, 0, 0]} />
                <Bar dataKey="b_sent" name="Variant B" fill={palette.info} radius={[4, 4, 0, 0]} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </BarChart>
            </ResponsiveContainer>
          </View>
        </>
      ) : null}

      {chartData.length === 0 ? (
        <View style={{ padding: 16, borderRadius: 10, backgroundColor: palette.surfaceHover, alignItems: 'center' }}>
          <Ionicons name="bar-chart-outline" size={20} color={palette.textMuted} />
          <Text style={{ fontSize: 11, color: palette.textMuted, marginTop: 6 }}>{tx('admin.aBPerformanceDashboard.auto.text.003', 'No send data yet. Charts will appear once emails are sent.')}</Text>
        </View>
      ) : null}
    </View>
  );
}

function VariantStat({ label, value, palette }: { label: string; value: string | number; palette: ThemePalette }) {
  return (
    <View>
      <Text style={{ fontSize: 16, fontWeight: '800', color: palette.text }}>{value}</Text>
      <Text style={{ fontSize: 8, color: palette.textMuted }}>{label}</Text>
    </View>
  );
}

export default function ABPerformanceDashboard({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { data, loading } = useLiveQuery('/ab-testing/performance', { entity: 'ab-testing', pollInterval: 60000 });
  const tests = data?.tests || [];
  const pm = data?.platform_metrics || {};

  const palette: ThemePalette = {
    surface: colors.surface,
    surfaceHover: colors.surfaceHover,
    border: colors.border,
    text: colors.text,
    textMuted: colors.textMuted,
    primaryText: colors.primaryText,
    primary: colors.primary,
    success: colors.success,
    warning: colors.warning,
    info: colors.info || 'var(--app-primary)',
  };

  if (loading && !data) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <Text style={{ color: palette.textMuted, fontSize: 12 }}>{tx('admin.aBPerformanceDashboard.auto.text.004', 'Loading performance data...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }} data-testid="ab-performance-dashboard" testID="ab-performance-dashboard">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${palette.primary}15`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="stats-chart" size={18} color={palette.primary} />
        </View>
        <View>
          <Text style={{ fontSize: 16, fontWeight: '800', color: palette.text }}>{tx('admin.aBPerformanceDashboard.auto.text.005', 'A/B Performance Dashboard')}</Text>
          <Text style={{ fontSize: 11, color: palette.textMuted }}>{tx('admin.aBPerformanceDashboard.auto.text.006', 'Track open rates, click rates, and conversion trends across all tests')}</Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <KPI label="Total Sends" value={pm.total_sends?.toLocaleString() || '0'} icon="mail" color={palette.primary} palette={palette} />
        <KPI label="Avg Open Rate" value={`${pm.avg_open_rate || 0}%`} sub={`${pm.total_opens || 0} opens`} icon="eye" color={palette.successText} palette={palette} />
        <KPI label="Avg Click Rate" value={`${pm.avg_click_rate || 0}%`} sub={`${pm.total_clicks || 0} clicks`} icon="hand-left" color={palette.warningText} palette={palette} />
        <KPI label="Active Tests" value={tests.filter((test: any) => test.status === 'active').length} sub={`${tests.length} total`} icon="flask" color={palette.info} palette={palette} />
      </View>

      {tests.length > 0 ? (
        tests.map((test: any) => <TestCard key={test.test_id} test={test} palette={palette} />)
      ) : (
        <View style={{ padding: 40, borderRadius: 16, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border, alignItems: 'center' }}>
          <Ionicons name="analytics-outline" size={32} color={palette.textMuted} />
          <Text style={{ fontSize: 13, fontWeight: '600', color: palette.textMuted, marginTop: 10 }}>{tx('admin.aBPerformanceDashboard.auto.text.007', 'No A/B tests with data yet')}</Text>
          <Text style={{ fontSize: 11, color: palette.textMuted, marginTop: 4, textAlign: 'center' }}>{tx('admin.aBPerformanceDashboard.auto.text.008', 'Create and run an A/B test to see performance metrics and trends here.')}</Text>
        </View>
      )}
    </ScrollView>
  );
}