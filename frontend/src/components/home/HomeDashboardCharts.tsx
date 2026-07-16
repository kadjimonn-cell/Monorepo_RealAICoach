import React, { useEffect, useMemo } from 'react';
import { View, Text, Platform, useWindowDimensions } from 'react-native';
import { useTheme } from '../../context/ThemeContext';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

let Recharts: any = null;
if (Platform.OS === 'web') {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    Recharts = require('recharts');
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/home/HomeDashboardCharts.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

const CHART_CSS = `
@keyframes chart-fade-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.home-chart-card {
  animation: chart-fade-in 0.6s ease both;
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
}
.home-chart-card:hover {
  transform: translateY(-4px);
}
[data-theme-active="dark"] .home-chart-card:hover {
  border-color: rgba(255,255,255,0.12) !important;
}
[data-theme-active="light"] .home-chart-card:hover {
  border-color: rgba(59,130,246,0.25) !important;
  box-shadow: 0 18px 40px rgba(15,23,42,0.12) !important;
}
`;

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface ChartData {
  labels: string[];
  ai_performance: number[];
  user_growth: number[];
  categories: { name: string; value: number; color: string }[];
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface ActivityItem {
  type: string;
  title: string;
  message: string;
  time: string;
}

export default function HomeDashboardCharts({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const isWide = width >= 1200;
  const { colors, darkMode, languageCode } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const langParam = languageCode && languageCode !== 'en' ? `?lang=${languageCode}` : '';
  const { data: chartRawData, loading: chartLoading } = useLiveQuery(`/home/chart-data${langParam}`, { entity: 'home_charts', pollInterval: 30000, deps: [languageCode] });

  const chartData = chartRawData || null;
  const loading = chartLoading;

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-chart-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = CHART_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _pieColors = useMemo(() => [colors.primary, colors.success, colors.warning, colors.error, colors.purple, colors.indigo], [colors.error, colors.indigo, colors.primary, colors.purple, colors.success, colors.warning]);

  if (Platform.OS !== 'web' || !Recharts) {
    return (
      <View data-testid="dashboard-charts-section" testID="dashboard-charts-section" style={{ padding: 20 }}>
        <Text style={{ color: colors.textMuted, fontSize: 14 }}>{t('home.charts.webOnly')}</Text>
      </View>
    );
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _LineChart, _Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } = Recharts;

  if (loading || !chartData) {
    return (
      <View data-testid="dashboard-charts-section" testID="dashboard-charts-section" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingVertical: 24 }}>
        <SkeletonCards isDesktop={isDesktop} />
      </View>
    );
  }

  const surfaceBg = colors.card;
  const surfaceBorder = darkMode ? 'rgba(255,255,255,0.06)' : colors.border;
  const cardShadow = darkMode ? '0 18px 40px rgba(0,0,0,0.26)' : '0 14px 30px rgba(15,23,42,0.08)';
  const labelMuted = darkMode ? colors.textMuted : colors.textMuted;
  const strongText = colors.text;
  const cardTitle = colors.text;
  const gridStroke = darkMode ? 'rgba(255,255,255,0.04)' : colors.chartGrid;
  const tooltipStyle = { backgroundColor: colors.chartTooltipBg, border: `1px solid ${colors.chartTooltipBorder}`, borderRadius: 10, color: colors.text, fontSize: 12 };

  const lineData = chartData.labels.map((label: string, i: number) => ({
    name: label,
    sessions: chartData.ai_performance[i],
  }));

  const barChartData = chartData.labels.map((label: string, i: number) => ({
    name: label,
    users: chartData.user_growth[i],
  }));

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _chartW = isWide ? (width - 120) / 3 - 20 : isTablet ? (width - 80) / 2 - 16 : isDesktop ? (width - 100) / 2 - 20 : width - 60;

  return (
    <View data-testid="dashboard-charts-section" testID="dashboard-charts-section" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingTop: 8, paddingBottom: 32 }}>
      {/* Section Header */}
      <View style={{ flexDirection: isDesktop ? 'row' : 'column', alignItems: isDesktop ? 'center' : 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 24 }}>
        <View>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>
            {tx('home.charts.kicker', 'Performance signals')}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 }}>
            <View style={{ width: 3, height: 20, borderRadius: 2, backgroundColor: colors.primary }} />
            <Text style={{ fontSize: 18, fontWeight: '800', color: strongText, letterSpacing: -0.5, fontFamily: DISPLAY_FONT_FAMILY }}>
              {t('home.charts.title')}
            </Text>
          </View>
          <Text style={{ color: labelMuted, fontSize: 12, marginTop: 8, fontFamily: BODY_FONT_FAMILY }}>
            {tx('home.charts.subtitle', 'Usage, growth, and activity surfaces that explain why users return.')}
          </Text>
        </View>
        <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: 'rgba(16,185,129,0.1)', borderWidth: 1, borderColor: 'rgba(16,185,129,0.22)' }} data-testid="home-charts-live-chip" testID="home-charts-live-chip">
          <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>{t('home.charts.live')}</Text>
        </View>
      </View>

      {/* Charts Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isWide ? '1fr 1fr 1fr' : isDesktop ? '1fr 1fr' : '1fr',
        gap: 16,
      } as any}>
        {/* _Line Chart - AI Performance */}
        <div className="home-chart-card" data-testid="chart-ai-performance" style={{
          padding: 22, borderRadius: 18,
          background: surfaceBg,
          border: `1px solid ${surfaceBorder}`,
          boxShadow: cardShadow,
          backdropFilter: 'blur(12px)',
          animationDelay: '0.1s',
        } as any}>
          <div style={{ marginBottom: 16 } as any}>
            <span style={{ color: labelMuted, fontSize: 11, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' } as any}>{t('home.charts.aiSessions')}</span>
            <div style={{ color: cardTitle, fontSize: 22, fontWeight: 800, marginTop: 4, letterSpacing: -0.5 } as any}>
              {chartData.ai_performance.reduce((a: number, b: number) => a + b, 0)}
              <span style={{ color: colors.successText, fontSize: 12, fontWeight: 600, marginLeft: 8 } as any}>+12%</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={lineData}>
              <defs>
                <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={colors.primary} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={colors.primary} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
              <XAxis dataKey="name" tick={{ fill: colors.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: colors.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: colors.chartLinePrimary }}
              />
              <Area type="monotone" dataKey="sessions" stroke={colors.chartLinePrimary} strokeWidth={2.5} fill="url(#blueGrad)" dot={{ r: 4, fill: colors.chartLinePrimary, stroke: colors.bg, strokeWidth: 2 }} activeDot={{ r: 6, stroke: colors.chartLinePrimary, strokeWidth: 2, fill: colors.chartSurface }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Bar Chart - User Growth */}
        <div className="home-chart-card" data-testid="chart-user-growth" style={{
          padding: 22, borderRadius: 18,
          background: surfaceBg,
          border: `1px solid ${surfaceBorder}`,
          boxShadow: cardShadow,
          backdropFilter: 'blur(12px)',
          animationDelay: '0.2s',
        } as any}>
          <div style={{ marginBottom: 16 } as any}>
            <span style={{ color: labelMuted, fontSize: 11, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' } as any}>{t('home.charts.userGrowth')}</span>
            <div style={{ color: cardTitle, fontSize: 22, fontWeight: 800, marginTop: 4, letterSpacing: -0.5 } as any}>
              {barChartData.reduce((a: any, b: any) => a + b.users, 0)}
              <span style={{ color: colors.successText, fontSize: 12, fontWeight: 600, marginLeft: 8 } as any}>+8%</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={barChartData}>
              <defs>
                <linearGradient id="purpleBarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.primary} stopOpacity={0.92} />
                  <stop offset="100%" stopColor={colors.accent} stopOpacity={0.68} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
              <XAxis dataKey="name" tick={{ fill: colors.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: colors.chartAxis, fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: colors.chartLineSecondary }}
              />
              <Bar dataKey="users" fill="url(#purpleBarGrad)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Pie Chart + Activity Feed */}
        <div className="home-chart-card" data-testid="chart-categories" style={{
          padding: 22, borderRadius: 18,
          background: surfaceBg,
          border: `1px solid ${surfaceBorder}`,
          boxShadow: cardShadow,
          backdropFilter: 'blur(12px)',
          animationDelay: '0.3s',
          ...(isDesktop && !isWide ? { gridColumn: 'span 2' } : {}),
        } as any}>
          <div style={{ marginBottom: 16 } as any}>
            <span style={{ color: labelMuted, fontSize: 11, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' } as any}>{t('home.charts.coachingCategories')}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: isDesktop && !isWide ? 'row' : 'column', alignItems: 'center', gap: 16 } as any}>
            <ResponsiveContainer width={isDesktop && !isWide ? '50%' : '100%'} height={160}>
              <PieChart>
                <Pie
                  data={chartData.categories}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={70}
                  paddingAngle={3}
                  dataKey="value"
                  stroke="none"
                >
                  {chartData.categories.map((entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={tooltipStyle}
                />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: isDesktop && !isWide ? '50%' : '100%' } as any}>
              {chartData.categories.map((cat: any) => (
                <div key={cat.name} style={{ display: 'flex', alignItems: 'center', gap: 8 } as any}>
                  <div style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: cat.color } as any} />
                  <span style={{ color: colors.textSec, fontSize: 12, flex: 1 } as any}>{cat.name}</span>
                  <span style={{ color: colors.text, fontSize: 12, fontWeight: 700 } as any}>{cat.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </View>
  );
}

function SkeletonCards({ isDesktop }: { isDesktop: boolean }) {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const skBg = darkMode
    ? `linear-gradient(90deg, ${colors.cardMuted} 25%, ${colors.card} 50%, ${colors.cardMuted} 75%)`
    : `linear-gradient(90deg, ${colors.bgSoft} 25%, ${colors.card} 50%, ${colors.bgSoft} 75%)`;
  const skBorder = `1px solid ${colors.border}`;
  return (
    <View style={{ gap: 16 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <View style={{ width: 3, height: 20, borderRadius: 2, backgroundColor: colors.primary }} />
        <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }}>{t('home.charts.title')}</Text>
      </View>
      {Platform.OS === 'web' ? (
        <div style={{
          display: 'grid',
          gridTemplateColumns: isDesktop ? '1fr 1fr' : '1fr',
          gap: 16,
        } as any}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{
              height: 240, borderRadius: 18,
              background: skBg,
              backgroundSize: '200% 100%',
              animation: 'shimmer 1.5s ease-in-out infinite',
              border: skBorder,
            } as any} />
          ))}
        </div>
      ) : (
        <View style={{ gap: 16 }}>
          {[1, 2].map(i => (
            <View key={i} style={{ height: 200, borderRadius: 18, backgroundColor: colors.card }} />
          ))}
        </View>
      )}
    </View>
  );
}
